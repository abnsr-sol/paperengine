"""Citation age and diversity engine: recency distribution, all-old references, year coverage."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_REF_YEAR = r"\(?\b(19[5-9]\d|20[0-3]\d)\)?"
# full years inside parens or bare at end of a reference line


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Citation Age", sev, title, detail, evidence, action, conf)


def _years(refs) -> List[int]:
    out = []
    for r in refs:
        for m in re.findall(r"(?:19[5-9]\d|20[0-3]\d)", r):
            try:
                out.append(int(m))
            except ValueError:
                pass
    return out


def run(doc: Document, ctx: object) -> List[Finding]:
    refs = doc.references or []
    if not refs:
        return []
    years = _years(refs)
    if not years:
        return []
    import datetime
    now = datetime.datetime.now().year
    out = []
    recent = [y for y in years if y >= now - 5]
    decade_old = [y for y in years if y <= now - 10]
    share_recent = len(recent) / len(years)
    share_old = len(decade_old) / len(years)
    if share_old > 0.8:
        out.append(_f(Severity.HIGH, "Reference list is stale", str(round(share_old * 100)) + "% of references are older than 10 years; reviewers expect recent work.",
                      str(len(decade_old)) + "/" + str(len(years)) + " refs older than 10y", 0.80, "Add recent (last 5 years) references, especially to current SOTA"))
    elif share_recent < 0.15 and len(years) >= 10:
        out.append(_f(Severity.MEDIUM, "Very few recent references", "Only " + str(round(share_recent * 100)) + "% of references are from the last 5 years.",
                      str(len(recent)) + "/" + str(len(years)) + " refs within 5y", 0.70, "Cite recent work to show the literature review is current"))
    span = max(years) - min(years)
    if span > 40:
        out.append(_f(Severity.LOW, "Very wide citation age span", "References span " + str(span) + " years; ensure foundational citations are balanced with current work.",
                      "Range " + str(min(years)) + "-" + str(max(years)), 0.55, "Check for outdated citations that have newer authoritative versions"))
    return out