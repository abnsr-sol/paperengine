"""Novelty engine: "is there new content, and is it presented as such?"

Reviewers reject for incremental/duplicate contribution more often than for
grammar. Automation cannot judge true novelty — it can only check whether the
manuscript *states and supports* a contribution and whether its claims differ
from known prior work (via corpus + optional online lookup). Everything here
is a signal for the author to strengthen, not an editorial verdict.
"""

from __future__ import annotations

import difflib
import re
from typing import List

from ..ingestion import Document
from ..metrics import CONTRIBUTION_WORDS, count_terms, words
from ..risk import Finding, Severity
from . import CheckContext


def _section_text(doc: Document, pattern: str) -> str:
    from ..ingestion import normalize_heading

    rx = re.compile(pattern, re.IGNORECASE)
    for s in doc.sections:
        if rx.match(normalize_heading(s.heading)):
            return s.body
    return ""


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 100:
        return findings

    intro = _section_text(doc, r"^(introduction|1)\b")
    abstract = _section_text(doc, r"^abstract\b")
    conclusion = _section_text(doc, r"^(conclusion|discussion|conclusions)\b")
    any_body = intro or abstract or conclusion or doc.text

    # --- Explicit contribution statement -----------------------------------------
    contrib_hits = count_terms(any_body, CONTRIBUTION_WORDS)
    strong = {
        k: v for k, v in contrib_hits.items()
        if k in ("novel", "first", "we propose", "we introduce", "we present", "contribution", "our approach", "outperform")
    }
    if not strong:
        findings.append(Finding(
            category="Novelty",
            severity=Severity.MEDIUM,
            title="No explicit novelty / contribution statement",
            detail="The manuscript does not clearly claim what is new (no 'we propose/introduce', 'novel', 'contribution', 'our approach').",
            evidence="contribution lexicon hits = 0 in intro/abstract",
            action="Add a bullet-style contribution list in the introduction and restate it in the abstract: what is new, what it enables, how it compares.",
            confidence=0.7,
        ))
    elif max(strong.values()) == 1 and len(strong) <= 2:
        findings.append(Finding(
            category="Novelty",
            severity=Severity.LOW,
            title="Contribution statement is thin",
            detail="Contribution keywords appear only once or twice — the novelty argument may be understated.",
            evidence="contribution lexicon hits: " + ", ".join(f"{k}={v}" for k, v in strong.items()),
            action="Reinforce the novelty claims with concrete comparisons against prior work.",
            confidence=0.55,
        ))

    # --- Abstract ≈ Conclusion (nothing new in the body) ---------------------------
    if abstract and conclusion and len(words(abstract)) > 30 and len(words(conclusion)) > 30:
        ratio = difflib.SequenceMatcher(None, abstract.lower(), conclusion.lower()).ratio()
        if ratio > 0.6:
            findings.append(Finding(
                category="Novelty",
                severity=Severity.MEDIUM,
                title="Conclusion nearly repeats the abstract",
                detail=f"Abstract/conclusion similarity {ratio*100:.0f}% — suggests the paper's new results are not presented as a distinct contribution.",
                evidence=f"SequenceMatcher ratio = {ratio:.2f} between abstract and conclusion",
                action="Make the conclusion synthesize *new* insight (implications, limitations, future work) rather than restating the abstract.",
                confidence=0.75,
            ))

    # --- Corpus-based novelty hints ---------------------------------------------------
    for other in ctx.corpus:
        from .integrity import _overlap_fraction

        frac, sample = _overlap_fraction(doc.text, other.text, n=8)
        if 0.15 <= frac < 0.25:
            findings.append(Finding(
                category="Novelty",
                severity=Severity.LOW,
                title="Moderate content overlap with prior document",
                detail=f"{frac*100:.0f}% of distinctive phrases appear in '{other.name}' — may look incremental.",
                evidence="sample overlap: '" + sample + "'",
                action="Explicitly differentiate this work: new experiments, new analysis, or new claims beyond the prior document.",
                confidence=0.7,
            ))
    return findings