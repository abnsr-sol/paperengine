"""Claims / evidence engine.

Peer-review rejections are driven by "overstated conclusions" and statistical
weakness (Manusights 2026 synthesis; PMC reviews). This engine checks the
machine-verifiable half: does the conclusion overclaim relative to the stats
actually reported? Significance claimed without any p-value, strong absolute
claims without hedging, and missing effect sizes are the classic patterns.
"""

from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..metrics import HEDGES, count_terms
from ..risk import Finding, Severity
from . import CheckContext

_STRONG_CLAIMS = [
    "proves", "proven", "guarantees", "guaranteed", "conclusively",
    "definitively", "undeniably", "unquestionably", "absolutely certain",
    "always", "never", "in all cases", "perfectly", "flawless",
]
_SIGNIFICANCE = re.compile(r"\bp\s*[<>=]\s*0?\.\d+|\bp-value", re.IGNORECASE)
_EFFECT_SIZE = re.compile(r"\b(cohen'?s?\s*d|d\s*=|eta.?squared|η2?|r\s*=|partial.?eta|hedges)", re.IGNORECASE)
_NUMERIC_RESULTS = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent)|accuracy|precision|recall|f1|score", re.IGNORECASE)


def _section(doc: Document, name: str) -> str:
    from ..ingestion import normalize_heading

    for s in doc.sections:
        if normalize_heading(s.heading).startswith(name):
            return s.body
    return ""


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 100:
        return findings
    cat = "Claims"
    body = doc.body_text
    conclusion = _section(doc, "conclusion") or _section(doc, "discussion")

    # --- Overstated conclusions ---------------------------------------------------------
    if conclusion:
        strong = count_terms(conclusion, _STRONG_CLAIMS)
        n_strong = sum(strong.values())
        hedge_hits = count_terms(conclusion, HEDGES)
        n_hedges = sum(hedge_hits.values())
        if n_strong >= 2 and n_hedges == 0:
            findings.append(Finding(
                category=cat, severity=Severity.HIGH,
                title="Overstated conclusion",
                detail=f"Conclusion uses {n_strong} absolute-claim word(s) ('proves', 'guarantees', 'always'...) with zero hedging.",
                evidence="strong claims = " + ", ".join(f"{k}" for k, v in strong.items() if v) + "; hedges = 0",
                action="Tone claims to match the evidence ('suggests', 'indicates', 'is consistent with'); overclaiming is a top peer-review rejection reason.",
                confidence=0.7,
                location="Conclusion",
            ))
        elif n_strong >= 4:
            findings.append(Finding(
                category=cat, severity=Severity.MEDIUM,
                title="Many absolute claims in conclusion",
                detail=f"{n_strong} absolute-claim words found in the conclusion.",
                evidence="strong claims = " + str(n_strong),
                action="Hedge claims that your experiments cannot fully support.",
                confidence=0.65,
                location="Conclusion",
            ))

    # --- Significance claimed without statistics -------------------------------------------
    if len(re.findall(r"\bsignifican\w*", body, re.IGNORECASE)) >= 3 and not _SIGNIFICANCE.search(body):
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="'Significant' used without reported statistics",
            detail="The word 'significant' appears ≥3 times but no p-values / confidence intervals are reported.",
            evidence="'significant*' count ≥ 3; p-value regex = 0 matches",
            action="Report actual p-values (or CIs/effect sizes) for every significance claim.",
            confidence=0.8,
        ))

    # --- p-values without effect sizes -----------------------------------------------------
    if _SIGNIFICANCE.search(body) and not _EFFECT_SIZE.search(body) and _NUMERIC_RESULTS.search(body):
        findings.append(Finding(
            category=cat, severity=Severity.LOW,
            title="Effect sizes missing",
            detail="p-values are reported but no effect-size measures (Cohen's d, eta-squared, r) found.",
            evidence="p-value regex hit; effect-size regex = 0 matches",
            action="Add effect sizes; 'p < 0.05' alone is considered weak reporting by many journals.",
            confidence=0.6,
        ))
    return findings