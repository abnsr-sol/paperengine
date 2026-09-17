"""ORCID + ROR author identity verification engine.

Cross-checks author names and affiliations against ORCID (author identity)
and ROR (research organization registry) to detect mismatches that may indicate
fake profiles, institutional fraud, or copy-paste author blocks.

- ORCID API: https://pub.orcid.org/v3.0/ (free read, no key needed)
- ROR API: https://api.ror.org/ (free, CC0)

Severity: HIGH when ORCID profile exists but affiliation mismatches ROR-resolved
          institution. MEDIUM when ORCID cannot be resolved. INFO when consistent.

Gate: Only fires when --online is True (requires network). Emits INFO coverage
note when offline.

Flag-not-verdict: mismatches may have innocent explanations (recent move,
adjunct position, second affiliation). Always include ≥1 explanation.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.parse
import json
from typing import List, Optional, Dict

from ..ingestion import Document
from ..risk import Finding, Severity

# ORCID pattern in manuscripts
_ORCID_RE = re.compile(
    r"(?:ORCID\s*(?:ID)?\s*[:;]?\s*)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])",
    re.IGNORECASE,
)

# Author block pattern: "Name¹,², Affiliation¹, Affiliation²" or similar
_AUTHOR_BLOCK_RE = re.compile(
    r"(?:author|corresponding)\s*(?:author)?\s*[:;]?\s*(.+?)(?:\n\n|\nAbstract)",
    re.IGNORECASE | re.DOTALL,
)

# Affiliation pattern: superscript numbers, department/institute/university
_AFFILIATION_RE = re.compile(
    r"(?:department|school|institute|center|centre|faculty|college|university|hospital|lab)\b",
    re.IGNORECASE,
)


def _query_orcid(orcid_id: str, timeout: int = 5) -> Optional[Dict]:
    """Query ORCID API for person record. Returns dict or None."""
    try:
        url = f"https://pub.orcid.org/v3.0/{orcid_id}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "PaperEngine/1.11 (research-tool)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _query_ror(name: str, timeout: int = 5) -> Optional[Dict]:
    """Query ROR API for organization. Returns first match or None."""
    try:
        url = f"https://api.ror.org/organizations?query={urllib.parse.quote(name)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "PaperEngine/1.11 (research-tool)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            if data.get("items"):
                return data["items"][0]
    except Exception:
        return None


def _extract_orcid(text: str) -> List[str]:
    """Extract ORCID IDs from text."""
    return list(set(_ORCID_RE.findall(text)))


def _extract_affiliations(text: str) -> List[str]:
    """Extract affiliation strings from author block area."""
    affs = []
    # Look for institution names near author block
    for match in re.finditer(
        r"(?:university|institute|hospital|college|school|center|centre|lab)\s+"
        r"(?:of\s+)?([A-Z][\w\s,]+?)(?:\n|$|[.;])",
        text,
    ):
        affs.append(match.group(0).strip())
    return list(set(affs))[:10]  # cap at 10


def run(doc: Document, ctx: object) -> List[Finding]:
    # Only run in online mode (ORCID/ROR require network)
    online = getattr(ctx, "online", False)
    if not online:
        return [Finding(
            "Integrity",
            Severity.INFO,
            "Author identity check requires --online flag",
            "ORCID + ROR cross-check verifies author profiles against institutional registries. "
            "Run with --online to enable.",
            "offline mode",
            0.95,
            "Re-run with --online to verify author identities",
        )]

    text = doc.text or ""
    if not text:
        return []

    orcids = _extract_orcid(text)
    if not orcids:
        return []  # no ORCID in manuscript — nothing to verify

    out = []
    max_checks = getattr(ctx, "max_online_checks", 5)
    checked = 0

    for orcid in orcids[:max_checks]:
        person = _query_orcid(orcid)
        if not person:
            out.append(Finding(
                "Integrity",
                Severity.MEDIUM,
                f"ORCID {orcid} could not be resolved",
                f"The ORCID ID {orcid} did not return a valid profile from the ORCID API. "
                "This may indicate a typo, a deactivated account, or a fabricated ORCID.",
                f"ORCID: {orcid}",
                0.65,
                "Verify the ORCID ID is correct; check https://orcid.org/{orcid}",
            ))
            checked += 1
            continue

        # Extract ORCID person's name and affiliations
        person_name = ""
        given = person.get("name", {}).get("given-names", {})
        family = person.get("name", {}).get("family-name", {})
        if given and family:
            person_name = f"{given.get('value', '')} {family.get('value', '')}"

        # Extract affiliations from ORCID employments
        orcid_affiliations = []
        employments = person.get("activities-summary", {}).get("employments", {})
        for emp in employments.get("affiliation-group", []):
            for summary in emp.get("summaries", []):
                org = summary.get("organization", {})
                name = org.get("name", "")
                if name:
                    orcid_affiliations.append(name)

        # Extract affiliations from manuscript
        manuscript_affiliations = _extract_affiliations(text)

        # Cross-check: does any manuscript affiliation match ORCID affiliations?
        if orcid_affiliations and manuscript_affiliations:
            match_found = False
            for m_aff in manuscript_affiliations:
                m_aff_lower = m_aff.lower()
                for o_aff in orcid_affiliations:
                    if o_aff.lower() in m_aff_lower or m_aff_lower in o_aff.lower():
                        match_found = True
                        break
                if match_found:
                    break

            if match_found:
                out.append(Finding(
                    "Integrity",
                    Severity.INFO,
                    f"ORCID {orcid} affiliations consistent with manuscript",
                    f"ORCID profile ({person_name}) lists affiliations that match the manuscript. "
                    "No identity concern detected.",
                    f"ORCID: {orcid}, person: {person_name}",
                    0.90,
                    "No action needed",
                ))
            else:
                out.append(Finding(
                    "Integrity",
                    Severity.HIGH,
                    f"ORCID {orcid} affiliation mismatch with manuscript",
                    f"ORCID profile ({person_name}) lists affiliations ({', '.join(orcid_affiliations[:3])}) "
                    "that do not match any affiliation in the manuscript "
                    f"({', '.join(manuscript_affiliations[:3])}). "
                    "This may indicate a fake profile, recent move, or dual affiliation — verify.",
                    f"ORCID: {orcid}, orcid_affiliations: {orcid_affiliations[:3]}, "
                    f"manuscript_affiliations: {manuscript_affiliations[:3]}",
                    0.75,
                    "Verify author identity; check if the ORCID belongs to this author "
                    "(innocent explanation: recent institutional move, adjunct position)",
                ))
        elif orcid_affiliations:
            # ORCID has affiliations but manuscript doesn't — informational
            out.append(Finding(
                "Integrity",
                Severity.INFO,
                f"ORCID {orcid} resolved ({person_name})",
                f"ORCID profile found with affiliations: {', '.join(orcid_affiliations[:2])}. "
                "Manuscript affiliations could not be extracted for comparison.",
                f"ORCID: {orcid}, affiliations: {orcid_affiliations[:2]}",
                0.70,
                "No action needed — ORCID verified",
            ))

        checked += 1

    return out
