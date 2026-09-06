"""Statistical analysis plan engine: missing-data handling, outlier rules, pre-specified analysis."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_STATS = r"statistical\s+analysis|analy(?:zed|sis)|\bp\s*[<>=]|regression|t[- ]test|ANOVA|chi-?square|mean|median|SD|CI\b"
_MISSING = r"missing\s+data|incomplete\s+data|non-?response|loss\s+to\s+follow-?up|attrition|imputation|multiple\s+imputation|complete-?case"
_OUTLIER = r"outlier|extreme\s+value|trimmed|winsor|robust\s+(?:estimat|regression)"
_PLAN = r"pre-?specified|pre-?registered|analysis\s+plan|primary\s+outcome|secondary\s+outcome|hypothes[ei]s\s+(?:was|were)\s+stated"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Stats Plan", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    if not re.search(_STATS, low):
        return []
    out = []
    if re.search(r"participants?|patients?|subjects?|survey|questionnaire", low) and not re.search(_MISSING, low):
        out.append(_f(Severity.MEDIUM, "Missing-data handling not described", "Studies with participants/surveys must describe how missing data were handled (imputation, complete-case).",
                      "Population keywords found, no missing-data terms", 0.70, "Describe missing-data handling and compare results under alternative approaches"))
    if re.search(r"mean|regression|t[- ]test|ANOVA|outlier", low) and not re.search(_OUTLIER, low):
        out.append(_f(Severity.LOW, "Outlier handling not described", "Pre-specified outlier rules are expected; post-hoc exclusion is a QRP flag.",
                      "Stats present, no outlier terms", 0.55, "State outlier definition and handling a priori"))
    if re.search(r"explor|post-?hoc|secondary\s+analys", low) and not re.search(_PLAN, low):
        out.append(_f(Severity.LOW, "No pre-specified analysis plan evident", "Distinguish pre-specified from exploratory analyses; post-hoc framing of primary outcomes is a HARKing risk.",
                      "Exploratory/post-hoc terms, no plan wording", 0.55, "State which analyses were pre-specified vs exploratory"))
    return out