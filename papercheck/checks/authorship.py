"""CRediT authorship engine: contributor-role taxonomy, funding role-of-funders, COI completeness."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_CREDIT_ROLES = ["conceptualization", "methodology", "software", "validation", "formal analysis", "investigation",
                 "resources", "data curation", "writing - original draft", "writing - review & editing",
                 "visualization", "supervision", "project administration", "funding acquisition"]
_FUNDER_ROLES = r"role\s+of\s+(?:the\s+)?funding\s+source|funders?\s+had\s+no\s+role|funding\s+sources?\s+(?:had|played)"
_COI = r"conflict\s+of\s+interest|competing\s+interests?|declaration\s+of\s+interests?"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Authorship", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    has_coi = re.search(_COI, low)
    has_funding = re.search(r"funding|grant|supported\s+by|financial\s+support", low)
    # CRediT for multi-author papers
    if has_coi or has_funding:
        # a journal-style paper: CRediT expected
        roles_found = [r for r in _CREDIT_ROLES if r in low]
        if not roles_found:
            out.append(_f(Severity.MEDIUM, "No CRediT contributor-role statement", "Most publishers (Elsevier, Springer, Wiley, PLOS) require a CRediT taxonomy statement mapping authors to roles.",
                          "None of the 14 CRediT roles found", 0.75, "Add an author-contributions section using the 14 CRediT roles"))
        elif len(roles_found) < 4:
            out.append(_f(Severity.LOW, "Thin CRediT coverage", "Only " + str(len(roles_found)) + " CRediT role(s) listed; typical papers map 5-8 roles across authors.",
                          "Roles: " + ", ".join(roles_found[:5]), 0.60, "Map all contributing authors to appropriate CRediT roles"))
    # funding present but role of funders missing
    if has_funding and not re.search(_FUNDER_ROLES, low):
        out.append(_f(Severity.LOW, "Funding declared without role-of-funders", "ICMJE requires stating whether funders had any role in study design, analysis, or publication.",
                      "Funding keywords, no role-of-funder statement", 0.60, "Add: 'The funders had no role in study design, analysis, or decision to publish'"))
    # 'The authors declare no conflict' style completeness
    if has_coi and re.search(r"no\s+conflict|no\s+competing", low) and re.search(r"patent|equity|stock|consult(ant|ing)|royalt", low):
        out.append(_f(Severity.MEDIUM, "COI 'none declared' but commercial terms present", "Commercial terms (patents/equity/consulting) appear in the text while COI says none; check for undisclosed interests.",
                      "COI 'none' + commercial terms", 0.55, "Verify and correctly disclose any commercial interests"))
    return out