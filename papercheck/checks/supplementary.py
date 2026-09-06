"""Supplementary material engine: missing supp section, unnumbered supp items, data 'not shown', legend quality."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_SUPP = r"supplementary|supporting\s+(?:information|material)|supplemental|SI\s*(?:section|material)|e-?component|additional\s+(?:figures|files)"
_SUPP_NUM = r"(?:supplementary|supporting|supplemental|additional)\s+(?:figure|table|fig|tab)\.?\s*[A-Z]?\d|Fig\.?\s*S\d|Table\s*S\d|Figure\s*S\d"
_NOT_SHOWN = r"data\s+(?:not\s+shown|not\s+presented|omitted)|results?\s+(?:not\s+shown|not\s+presented)|figure\s+not\s+shown|not\s+shown\s+here"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Supplementary", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    out = []
    has_supp = re.search(_SUPP, low)
    if re.search(_NOT_SHOWN, low):
        out.append(_f(Severity.HIGH, "Data reported as 'not shown'", "Reviewers reject papers that omit supporting data; put it in supplementary or supply on request statements only for large raw data.",
                      "Matched: " + str(set(re.findall(_NOT_SHOWN, low))), 0.85, "Move 'not shown' data into supplementary material with a legend"))
    if not has_supp:
        out.append(_f(Severity.MEDIUM, "No supplementary material section", "Journals expect a Supplementary/Supporting Information statement even when none is provided ('No supplementary data').",
                      "No supplementary keywords found", 0.65, "Add a supplementary section or state explicitly that none is provided"))
        return out
    num = re.findall(_SUPP_NUM, low)
    if has_supp and not num:
        out.append(_f(Severity.LOW, "Supplementary items not numbered", "Supplementary figures/tables should be numbered (Fig. S1, Table S1) and cited in text.",
                      "Supplementary mentioned, no S-numbered items", 0.70, "Number supplementary items S1, S2, ... and cite each in the main text"))
    return out
