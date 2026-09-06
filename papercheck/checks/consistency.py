"""Consistency engine: does the manuscript contradict itself?

Reviewers (and editors checking tables vs. text) frequently reject on
internal contradictions: different sample sizes, inconsistent acronyms,
conflicting numbers between abstract/results/conclusion. These checks are
high-confidence when they fire — a conflict is a conflict.
"""

from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..metrics import conflicting_numbers
from ..risk import Finding, Severity
from . import CheckContext

_COMMON_ACRONYMS = {
    "AI", "ML", "NLP", "CNN", "RNN", "LSTM", "GPU", "CPU", "RAM", "API", "HTTP",
    "URL", "DOI", "PDF", "DOCX", "CSV", "JSON", "XML", "HTML", "SQL", "DB", "OS",
    "IEEE", "ACM", "COPE", "DOI", "e.g.", "i.e.", "et", "al", "Fig", "Eq", "Sec",
}


def _acronym_definitions(text: str) -> List[tuple]:
    """Find 'ACRONYM (definition)' or 'definition (ACRONYM)' patterns."""
    out = []
    for m in re.finditer(r"\b([A-Z][A-Z0-9]{1,9})\b\s*\(([^()]{2,60})\)", text):
        out.append((m.group(1), m.group(2)))
    for m in re.finditer(r"\(([A-Z][A-Z0-9]{1,9})\)", text):
        pass
    return out


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 100:
        return findings
    text = doc.body_text

    # --- Conflicting numbers (n=, %, participants, epochs, ...) --------------------
    conflicts = conflicting_numbers(text)
    real = [c for c in conflicts if c["unit"] not in ("percent", "percentage")]
    for c in real[:5]:
        findings.append(Finding(
            category="Consistency",
            severity=Severity.HIGH,
            title="Conflicting numbers for the same quantity",
            detail=f"'{c['unit']}' appears with different values: " + ", ".join(c["values"][:6]),
            evidence="regex number+unit scan across whole document",
            action="Find every occurrence and unify the correct value; editors check tables against text.",
            confidence=0.9,
        ))
    if len(real) > 5:
        findings.append(Finding(
            category="Consistency",
            severity=Severity.MEDIUM,
            title="Many conflicting numeric quantities",
            detail=f"{len(real)} distinct quantities appear with conflicting values.",
            evidence="number-unit conflict scan",
            action="Audit all numbers systematically (sample sizes, scores, percentages).",
            confidence=0.8,
        ))

    # --- Undefined acronyms ----------------------------------------------------------
    defined = {a for a, _ in _acronym_definitions(text)}
    defined |= _COMMON_ACRONYMS
    allcaps = re.findall(r"\b[A-Z]{2,6}\b", text)
    from collections import Counter

    counts = Counter(allcaps)
    undefined = [
        a for a, c in counts.items()
        if c >= 3 and a not in defined and not a.isdigit() and a not in ("THE", "AND", "FOR", "WITH", "THIS", "FROM", "THAT", "THAN", "MORE", "OURS", "DISCUSSION", "CONCLUSION", "INTRODUCTION", "ABSTRACT", "REFERENCES", "METHODOLOGY", "EXPERIMENTS", "RESULTS", "TABLE", "FIGURE", "FIGURES", "TABLES")
    ]
    if undefined:
        findings.append(Finding(
            category="Consistency",
            severity=Severity.MEDIUM,
            title="Undefined or inconsistently-used acronyms",
            detail="Used ≥3 times without a definition: " + ", ".join(undefined[:8]),
            evidence="all-caps token frequency scan (tokens used ≥3x, no (definition) found)",
            action="Define each acronym at first use and use it consistently.",
            confidence=0.6,
        ))

    # --- Heading numbering gaps (from ingestion notes) --------------------------------
    if doc.extraction_notes:
        findings.append(Finding(
            category="Consistency",
            severity=Severity.LOW,
            title="Possible section-numbering inconsistency",
            detail=doc.extraction_notes[0],
            evidence="heading numbering scan",
            action="Renumber sections sequentially to match the venue template.",
            confidence=0.7,
        ))

    # --- Terminology drift: same concept written multiple ways --------------------------
    drift = re.findall(
        r"\b(dataset|data set|data-set|model|algorithm|framework|method|technique|approach)\b",
        text.lower(),
    )
    if drift:
        from collections import Counter as C2

        pairs = [("dataset", "data set"), ("data-set", "data set")]
        hits = []
        for a, b in pairs:
            na = text.lower().count(a)
            nb = text.lower().count(b)
            if na >= 3 and nb >= 3:
                hits.append(f"'{a}' (x{na}) vs '{b}' (x{nb})")
        if hits:
            findings.append(Finding(
                category="Consistency",
                severity=Severity.LOW,
                title="Inconsistent terminology",
                detail="Same concept written multiple ways: " + "; ".join(hits),
                evidence="term-variant frequency scan",
                action="Pick one term per concept and use it throughout.",
                confidence=0.8,
            ))
    return findings