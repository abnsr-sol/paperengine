"""Redundancy engine: how much of the abstract/intro/conclusion/results is repeated verbatim across sections."""
from __future__ import annotations
import re
from typing import List, Tuple
from ..ingestion import Document
from ..risk import Finding, Severity

_STOP = set("the a an and or of to in on for with by from as at that this these those is are was were be been has have had it its we our you your not no but so if then than very can will would should may might".split())


def _section(doc: Document, names: Tuple[str, ...]) -> str:
    for sec in getattr(doc, "sections", []) or []:
        h = (sec.heading or "").lower()
        if any(n in h for n in names):
            return sec.body or ""
    return ""


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in _STOP}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def run(doc: Document, ctx: object) -> List[Finding]:
    out = []
    abst = _section(doc, ("abstract",))
    intro = _section(doc, ("introduction", "background", "related work"))
    concl = _section(doc, ("conclusion", "discussion", "summary"))
    results = _section(doc, ("results", "experimental", "evaluation", "findings"))

    def check(a_text, b_text, a_name, b_name, threshold, sev):
        if not a_text or not b_text:
            return
        sim = _jaccard(_words(a_text), _words(b_text))
        if sim >= threshold:
            out.append(Finding("Language", sev,
                               a_name + " repeats " + b_name + " (" + str(int(sim * 100)) + "% word overlap)",
                               "Heavy verbatim reuse across sections reads as padding and wastes the word budget.",
                               "Jaccard overlap: " + str(round(sim, 2)), 0.75,
                               "Rewrite the later section: keep the abstract self-contained, give the intro the gap, and let the conclusion interpret rather than restate"))

    check(abst, intro, "Abstract", "Introduction", 0.55, Severity.MEDIUM)
    check(abst, concl, "Abstract", "Conclusion", 0.55, Severity.MEDIUM)
    check(intro, concl, "Introduction", "Conclusion", 0.60, Severity.LOW)
    if results and concl:
        check(results, concl, "Results", "Conclusion", 0.65, Severity.LOW)
    return out
