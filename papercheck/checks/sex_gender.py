"""SAGER engine: sex and gender reporting in clinical, epidemiological and animal studies."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_STUDY = r"(?:participants?|patients?|subjects?|cohort|sample|animals?|mice|rats?|women|men)"
_SEX = r"\b(?:sex|gender)\b|male|female|\bf\b|\bm\b|men and women|boys and girls"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("SAGER", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    # only meaningful for studies of living subjects
    if not re.search(r"participants?|patients?|subjects?|cohort|clinical|women|men|animals?|mice|rats?", low):
        return []
    out = []
    has_sex = re.search(_SEX, low)
    if not has_sex:
        out.append(_f(Severity.MEDIUM, "Sex/gender not reported", "SAGER guidelines require reporting the sex/gender composition of participants/animals.",
                      "Study-population keywords found, no sex/gender terms", 0.65, "Report the sex/gender breakdown in Methods and Results"))
        return out
    # sex reported but no disaggregation of results
    if re.search(r"\b(?:male|female)\b", low) and not re.search(r"by (?:sex|gender)|sex-?stratified|stratified by|per (?:sex|gender)|separately for (?:male|female)|in (?:men|women)\b|in (?:males|females)\b", low):
        out.append(_f(Severity.LOW, "Sex reported but results not disaggregated", "SAGER recommends reporting results separately by sex where biologically plausible.",
                      "Sex terms found, no stratified-by-sex wording", 0.55, "Add sex-stratified analyses or justify why pooling is appropriate"))
    # sex vs gender confusion
    if re.search(r"\bgender\b", low) and re.search(r"biological|hormon|chromosom|XX|XY", low):
        out.append(_f(Severity.LOW, "Possible sex/gender terminology confusion", "Use 'sex' for biological attributes and 'gender' for socially constructed roles.",
                      "Both 'gender' and biological terms present", 0.50, "Check that 'sex' and 'gender' are used correctly per SAGER"))
    return out