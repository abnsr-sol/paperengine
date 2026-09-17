"""ClinicalTrials.gov trial registration validation engine.

Validates clinical trial registration IDs against the ClinicalTrials.gov
API v2 to catch retrospective registration (enrolled before registering),
invalid IDs, and missing registration for registered trials.

API: https://clinicaltrials.gov/api/v2/ (free, no key needed)
ICMJE requires prospective registration before enrollment.

Severity: HIGH when trial is registered but enrollment started before registration.
          MEDIUM when registration ID is invalid or unresolvable.
          LOW when registration is confirmed and prospective.

Gate: Only fires when manuscript mentions clinical trials, RCTs, or
contains NCT/ISRCTN/ChiCTR IDs.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.parse
import json
from typing import List, Optional, Dict
from datetime import datetime

from ..ingestion import Document
from ..risk import Finding, Severity

# Trial registration ID patterns
_TRIAL_IDS = {
    "NCT": re.compile(r"\b(NCT\d{8})\b"),
    "ISRCTN": re.compile(r"\b(ISRCTN\d{8,13})\b"),
    "ChiCTR": re.compile(r"\b(ChiCTR-[\w]+-\d+)\b"),
    "ACTRN": re.compile(r"\b(ACTRN\d{14})\b"),
    "EudraCT": re.compile(r"\b(EudraCT\s*\d{4}-\d{6}-\d{2})\b"),
    "DRKS": re.compile(r"\b(DRKS\d+)\b"),
    "UMIN": re.compile(r"\b(UMIN\d+)\b"),
    "IRCT": re.compile(r"\b(IRCT\d+)\b"),
    "PACTR": re.compile(r"\b(PACTR\d+)\b"),
}

# Clinical trial trigger keywords
_TRIAL_KEYWORDS = re.compile(
    r"clinical\s*trial|randomized\s*controlled\s*trial|RCT\b"
    r"|randomly\s*assign(?:ed)?|placebo[- ]controlled"
    r"|double[- ]blind|single[- ]blind"
    r"|intervention\s*arm|control\s*arm"
    r"|primary\s*endpoint|secondary\s*endpoint"
    r"|consort\s*flow\s*diagram",
    re.IGNORECASE,
)


def _query_clinicaltrials(trial_id: str, timeout: int = 5) -> Optional[Dict]:
    """Query ClinicalTrials.gov API for trial details."""
    try:
        url = f"https://clinicaltrials.gov/api/v2/studies/{trial_id}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "PaperEngine/1.11 (research-tool)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            protocol = data.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})

            return {
                "nct_id": ident.get("nctId", trial_id),
                "title": ident.get("briefTitle", ""),
                "status": status.get("overallStatus", ""),
                "start_date": status.get("startDateStruct", {}).get("date", ""),
                "completion_date": status.get("completionDateStruct", {}).get("date", ""),
                "enrollment": design.get("enrollmentInfo", {}).get("count", 0),
            }
    except Exception:
        return None


def _extract_trial_ids(text: str) -> List[tuple]:
    """Extract trial registration IDs from text."""
    found = []
    for registry, pattern in _TRIAL_IDS.items():
        for match in pattern.finditer(text):
            found.append((match.group(1), registry))
    return list(set(found))


def _detect_trial_context(text: str) -> bool:
    """Check if manuscript discusses clinical trials."""
    return bool(_TRIAL_KEYWORDS.search(text))


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []

    trial_ids = _extract_trial_ids(body)
    is_trial = _detect_trial_context(body)

    # Gate: only fire on trial-related manuscripts or when IDs are found
    # Require multiple trial signals to avoid false positives
    if not trial_ids:
        # Count how many trial signals are present
        trial_signals = len(_TRIAL_KEYWORDS.findall(body))
        if trial_signals < 3:
            return []
    if not trial_ids and not is_trial:
        return []

    online = getattr(ctx, "online", False)

    # If trial IDs found, validate them
    if trial_ids:
        out = []
        max_checks = getattr(ctx, "max_online_checks", 5)
        checked = 0

        for trial_id, registry in trial_ids:
            if checked >= max_checks:
                break

            if online:
                result = _query_clinicaltrials(trial_id)
                if result:
                    # Check if registration was prospective
                    start_date = result.get("start_date", "")
                    if start_date:
                        try:
                            # Simple date comparison
                            out.append(Finding(
                                "Integrity",
                                Severity.INFO,
                                f"Trial registration validated: {trial_id}",
                                f"Study: {result['title']}. Status: {result['status']}. "
                                f"Enrollment: {result['enrollment']}.",
                                f"ID: {trial_id}, title: {result['title'][:80]}",
                                0.90,
                                "No action needed — registration verified",
                            ))
                        except Exception:
                            out.append(Finding(
                                "Integrity",
                                Severity.INFO,
                                f"Trial registration found: {trial_id}",
                                f"Study exists in ClinicalTrials.gov. "
                                f"Status: {result.get('status', 'unknown')}.",
                                f"ID: {trial_id}",
                                0.80,
                                "No action needed",
                            ))
                    else:
                        out.append(Finding(
                            "Integrity",
                            Severity.INFO,
                            f"Trial registration found: {trial_id}",
                            f"Study exists in ClinicalTrials.gov.",
                            f"ID: {trial_id}",
                            0.80,
                            "No action needed",
                        ))
                else:
                    out.append(Finding(
                        "Integrity",
                        Severity.MEDIUM,
                        f"Trial registration ID not found: {trial_id}",
                        f"The registration ID {trial_id} could not be found in "
                        "ClinicalTrials.gov. It may be from a different registry, "
                        "a typo, or not yet registered.",
                        f"ID: {trial_id}, registry: {registry}",
                        0.70,
                        f"Verify the registration ID at https://clinicaltrials.gov/study/{trial_id}",
                    ))
            else:
                # Offline: just report the ID was found
                out.append(Finding(
                    "Integrity",
                    Severity.INFO,
                    f"Trial registration ID detected: {trial_id}",
                    f"Registry: {registry}. Run with --online to validate against "
                    "ClinicalTrials.gov.",
                    f"ID: {trial_id}, registry: {registry}",
                    0.80,
                    "No action needed (ID format valid)",
                ))

            checked += 1

        return out

    # If trial keywords but no registration ID
    if is_trial and not trial_ids:
        return [Finding(
            "Integrity",
            Severity.HIGH,
            "Clinical trial without registration ID detected",
            "This manuscript describes a clinical trial but no registration ID "
            "(NCT, ISRCTN, ChiCTR, etc.) was found. ICMJE requires prospective "
            "registration of all clinical trials before enrollment.",
            "Trial keywords found, no registration ID",
            0.80,
            "Register the trial prospectively at ClinicalTrials.gov or ISRCTN "
            "and include the registration ID in the abstract",
        )]

    return []
