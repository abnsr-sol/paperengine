"""RRID (Research Resource Identifier) validation engine.

Validates RRIDs against the SciCrunch resolver API to catch missing, invalid,
or incorrect identifiers for antibodies, cell lines, software, and other
research resources.

RRIDs are required by Nature, Cell, ASMB, and many other journals. They ensure
resource traceability and reproducibility.

Source: https://scicrunch.org/resolver (free API, no key needed)
RRID format: RRID:AB_XXXXXX (antibodies), RRID:SCR_XXXXXX (software),
             RRID:CVCL_XXXXXX (cell lines), etc.

Severity: MEDIUM when RRID is invalid/unresolvable.
          LOW when RRID format is present but not in required list.
          INFO when RRID validates successfully.

Gate: Only fires when manuscript mentions antibodies, cell lines, software,
or explicitly uses RRID patterns. Emits INFO coverage note when offline.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.parse
import json
from typing import List, Optional, Dict

from ..ingestion import Document
from ..risk import Finding, Severity

# RRID patterns
_RRID_PATTERN = re.compile(
    r"RRID\s*:\s*(AB|SCR|CVCL|IMG|CBRB|MGI|IMSR|JAX|RBRC|CRL|ECACC)\s*_?\s*(\d+)",
    re.IGNORECASE,
)

# Broader RRID mention (may not have specific ID)
_RRID_MENTION = re.compile(r"\bRRID\b", re.IGNORECASE)

# Biomedical/biological resource keywords
_RESOURCE_KEYWORDS = re.compile(
    r"antibod(?:y|ies)"
    r"|cell\s*line"
    r"|monoclonal|polyclonal"
    r"|western\s*blot|ELISA|flow\s*cytometry"
    r"|immunohistochemistry|immunofluorescence"
    r"|knockdown|knockout|siRNA|shRNA|CRISPR"
    r"|primer|oligonucleotide|probe"
    r"|software\s*(?:tool|package|version)"
    r"|MATLAB|R\s*(?:package|version|studio)"
    r"|ImageJ|Fiji|GraphPad|SPSS|R|Python",
    re.IGNORECASE,
)

# Required RRID contexts (journals that mandate RRIDs)
_RRID_REQUIRED_CONTEXTS = re.compile(
    r"nature|cell\s*journal|neuron|immunity|cancer\s*cell"
    r"|asmb|molecular\s*cell|cell\s*reports|cell\s*stem\s*cell",
    re.IGNORECASE,
)


def _validate_rrid(rrid: str, timeout: int = 5) -> Optional[Dict]:
    """Validate an RRID against SciCrunch API. Returns dict or None."""
    try:
        url = f"https://scicrunch.org/resolver/{rrid}.json"
        req = urllib.request.Request(url, headers={
            "User-Agent": "PaperEngine/1.11 (research-tool)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data
    except Exception:
        return None


def _extract_rrids(text: str) -> List[str]:
    """Extract all RRID patterns from text."""
    matches = _RRID_PATTERN.findall(text)
    return [f"RRID:{prefix}_{num}" for prefix, num in matches]


def _detect_resource_context(text: str) -> bool:
    """Check if manuscript mentions biological/biomedical resources."""
    return bool(_RESOURCE_KEYWORDS.search(text))


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []

    online = getattr(ctx, "online", False)
    rrids = _extract_rrids(text)

    # Gate: only fire when resources are mentioned or RRIDs are present
    if not rrids and not _detect_resource_context(text):
        return []

    # If RRIDs are present, validate them
    if rrids:
        out = []
        max_checks = getattr(ctx, "max_online_checks", 5)
        checked = 0

        for rrid in set(rrids):
            if online and checked >= max_checks:
                break

            if online:
                result = _validate_rrid(rrid)
                if result:
                    # RRID resolved successfully
                    name = result.get("data", {}).get("name", "unknown")
                    out.append(Finding(
                        "Integrity",
                        Severity.INFO,
                        f"RRID validated: {rrid}",
                        f"Resource identifier resolves to: {name}",
                        f"RRID: {rrid}, resource: {name}",
                        0.95,
                        "No action needed — RRID is valid",
                    ))
                else:
                    out.append(Finding(
                        "Integrity",
                        Severity.MEDIUM,
                        f"RRID could not be validated: {rrid}",
                        f"The RRID {rrid} did not resolve on SciCrunch. "
                        "It may be a typo, deprecated, or not yet registered.",
                        f"RRID: {rrid}",
                        0.70,
                        f"Verify the RRID at https://scicrunch.org/resolver/{rrid}",
                    ))
            else:
                # Offline: just check format validity
                prefix = rrid.split("_")[0].replace("RRID:", "")
                valid_prefixes = ["AB", "SCR", "CVCL", "IMG", "CBRB", "MGI", "IMSR", "JAX", "RBRC"]
                if prefix.upper() in valid_prefixes:
                    out.append(Finding(
                        "Integrity",
                        Severity.INFO,
                        f"RRID format valid: {rrid}",
                        "RRID follows valid format. Run with --online to validate against SciCrunch.",
                        f"RRID: {rrid}",
                        0.80,
                        "No action needed (format valid)",
                    ))
                else:
                    out.append(Finding(
                        "Integrity",
                        Severity.MEDIUM,
                        f"RRID has unusual prefix: {rrid}",
                        f"Prefix '{prefix}' is not a common RRID prefix (AB, SCR, CVCL). "
                        "It may be valid but is less common.",
                        f"RRID: {rrid}",
                        0.60,
                        "Verify the RRID prefix and format",
                    ))

            checked += 1

        return out

    # If no RRIDs but resources are mentioned, suggest adding them
    if _detect_resource_context(text):
        # Check if RRIDs are missing where expected
        has_rrid = _RRID_MENTION.search(text)
        if not has_rrid:
            # Check if the venue requires RRIDs
            venue = getattr(ctx, "venue", None) or ""
            requires_rrid = bool(venue and _RRID_REQUIRED_CONTEXTS.search(venue))

            if requires_rrid:
                return [Finding(
                    "Integrity",
                    Severity.MEDIUM,
                    "Research resources lack RRID identifiers",
                    "This venue requires Research Resource Identifiers (RRIDs) for "
                    "antibodies, cell lines, software, and other biological resources. "
                    "RRIDs ensure resource traceability and reproducibility.",
                    "No RRID patterns found in manuscript",
                    0.75,
                    "Add RRIDs for all biological resources (antibodies, cell lines, "
                    "software) using https://scicrunch.org/resolver",
                )]

    return []
