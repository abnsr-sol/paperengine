"""Abstract quality engine: structured-abstract labels, abstract word limit, keyword count and specificity."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_GENERIC = {"analysis", "study", "method", "methods", "results", "research", "paper", "system", "model", "data", "approach", "application", "effect", "based", "using", "new", "novel"}
_STRUCT = ["background", "objective", "methods", "results", "conclusions?", "findings", "introduction", "materials and methods"]


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Abstract", sev, title, detail, evidence, action, conf)


def _abstract(text: str) -> str:
    m = re.search(r"abstract\s*[:\n]", text, re.IGNORECASE)
    if not m:
        return ""
    nxt = re.search(r"\n(?:1\.\s*)?(?:introduction|keywords?|1\s+introduction)\b", text[m.end():], re.IGNORECASE)
    end = m.end() + (nxt.start() if nxt else min(len(text), m.end() + 3000))
    return text[m.end():end]


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    out = []
    ab = _abstract(body)
    if not ab:
        return out
    words = len(ab.split())
    # structured-abstract labels for clinical work
    if re.search(r"(?:clinical|medical|trial|patient|cohort|observational)", low):
        hits = [s for s in _STRUCT if re.search(r"\b" + s + r"\b", ab.lower())]
        if len(hits) < 3:
            out.append(_f(Severity.MEDIUM, "Clinical abstract may need structured format", "Medical journals require labeled sections (Background/Methods/Results/Conclusions).", "Structured labels found: " + str(hits), 0.65, "Format the abstract with labeled sections per the venue's requirements"))
    # abstract word limit from venue rules
    limit = None
    rules = getattr(ctx, 'rules', {}) or {}
    if rules:
        lim = rules.get('abstract_max_words') or (rules.get('abstract') or {}).get('max_words')
        if lim:
            limit = int(lim)
    if limit and words > limit:
        out.append(_f(Severity.HIGH, "Abstract over venue limit", str(words) + " words vs limit " + str(limit) + ".", "Abstract: " + str(words) + " words", 0.95, "Trim the abstract to the venue's limit"))
    # keywords
    kw_m = re.search(r"keywords?\s*[:\n]", low)
    if kw_m:
        kw_line = body[kw_m.end():].split("\n")[0]
        kws = [k.strip().strip(',.;') for k in re.split(r"[,;]", kw_line) if k.strip()]
        if len(kws) < 3:
            out.append(_f(Severity.LOW, "Too few keywords", str(len(kws)) + " keywords; journals usually expect 4-6.", "Keywords: " + str(kws), 0.80, "Add 4-6 discipline-specific keywords"))
        generic = [k for k in kws if k.lower() in _GENERIC]
        if generic:
            out.append(_f(Severity.LOW, "Generic keywords", "Keywords like " + ", ".join(generic) + " are too broad for indexing.", "Generic: " + str(generic), 0.70, "Replace generic terms with MeSH/discipline-specific keywords"))
        if len(kws) > 10:
            out.append(_f(Severity.LOW, "Too many keywords", str(len(kws)) + " keywords exceeds typical journal limits.", str(len(kws)) + " keywords", 0.70, "Reduce to the venue's keyword limit"))
    return out
