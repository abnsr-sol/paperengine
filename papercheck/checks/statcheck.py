"""Statcheck engine: verify reported p-values against their own test statistics.

A pure-arithmetic integrity check (Nuijten et al.'s statcheck idea, ported
to stdlib-only Python): every APA-style result (t/F/chi2/r/z with df and p)
is recomputed from the statistic and degrees of freedom, then compared to
the reported p. Discrepancies are arithmetic facts, not heuristics:

- decision error  — reported and recomputed p fall on opposite sides of .05
                    (the reviewer-visible conclusion is wrong)
- gross mismatch  — |reported - recomputed| > 0.05
- inconsistencies — 2+ smaller mismatches suggest sloppy or hand-edited stats

Every finding quotes the result so authors can fix the exact sentence.
"""
from __future__ import annotations

from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity
from ..statscalc import extract_results
from . import CheckContext

_TOL = 0.02  # covers APA rounding of the statistic to 2 decimals


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Statistics", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    text = doc.body_text or doc.text or ""
    if doc.word_count < 200:
        return []
    results = extract_results(text)
    if not results:
        return []

    decision = [r for r in results if r.decision_error]
    gross = [r for r in results if not r.decision_error and r.abs_error > 0.05]
    minor = [r for r in results
             if not r.decision_error and _TOL < r.abs_error <= 0.05]
    checked = len(results)

    out: List[Finding] = []

    for r in decision[:3]:
        out.append(_f(
            Severity.CRITICAL,
            "P-value contradicts its own test statistic (decision error)",
            f"Reported '{r.context}' — the statistic implies p = {r.recomputed_p:.3f}, "
            f"but the paper reports p {r.operator} {r.reported_p:g}. The significance "
            f"conclusion flips. This is exactly what automated statistical screening "
            f"(statcheck-style) flags and reviewers treat as a credibility blow.",
            f"recomputed p = {r.recomputed_p:.4f} vs reported {r.reported_p:g} "
            f"({r.stat} = {r.statistic:g})",
            0.9,
            "Re-run the analysis or correct the reported p; a significance/non-significance "
            "flip changes the paper's conclusions and must be fixed before submission",
        ))

    for r in gross[:2]:
        out.append(_f(
            Severity.HIGH,
            "Statistical reporting inconsistency (large mismatch)",
            f"Reported '{r.context}' — recomputed p = {r.recomputed_p:.3f} vs reported "
            f"p {r.operator} {r.reported_p:g}. Even without a decision flip, a mismatch "
            f"this large suggests the statistic or p was edited after the fact.",
            f"recomputed {r.recomputed_p:.4f} vs reported {r.reported_p:g}",
            0.85,
            "Recompute and report the exact p-value from the final analysis output",
        ))

    if len(minor) >= 2:
        examples = "; ".join(
            f"{r.stat} -> reported {r.reported_p:g} vs recomputed {r.recomputed_p:.3f}"
            for r in minor[:3])
        out.append(_f(
            Severity.MEDIUM,
            f"{len(minor)} minor statistical reporting inconsistencies",
            f"{len(minor)} of {checked} reported results differ from their recomputed "
            f"p-values by more than APA rounding tolerance ({examples}). Individually "
            f"small, but a pattern reviewers increasingly check with automated tools.",
            f"{len(minor)}/{checked} results mismatch (tolerance {_TOL})",
            0.7,
            "Regenerate every statistic from the final analysis output; do not hand-edit p-values",
        ))

    if not out and checked >= 5:
        out.append(_f(
            Severity.INFO,
            f"Statistical reporting verified ({checked} results recomputed)",
            f"All {checked} APA-style results match their recomputed p-values within "
            f"rounding tolerance. Deterministic checks like this build reviewer trust.",
            f"{checked} t/F/chi2/r/z results verified, 0 mismatches",
            1.0,
            "No action needed — consider stating in the methods that statistics were "
            "machine-verified before submission",
        ))
    return out
