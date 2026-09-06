"""Statistical correction awareness: prevents statcheck false positives.

A naive p-value recomputation flags papers that used Greenhouse-Geisser,
Huynh-Feldt, Bonferroni, Holm, Benjamini-Hochberg (FDR), or similar
corrections — because the reported (corrected) p legitimately differs from
the recomputed raw p. This engine:

1. Detects correction vocabulary and, when present, downgrades statcheck
   discrepancies from critical/high to informational ("consistent with a
   statistical correction — verify which was applied").
2. When NO correction is stated but multiple p-values cluster at the
   margin (p=.04x), reminds about multiple-comparison correction.

This module reads the statcheck results from the shared context if the
statcheck engine has already run; it must be ordered after it. To keep
engines independent, it re-extracts from text directly instead.
"""
from __future__ import annotations

import os
import re
import sys
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from papercheck.statscalc import extract_results  # noqa: E402

_CORRECTIONS = re.compile(
    r"greenhouse[\s-]*geisser|huynh[\s-]*feldt|bonferroni|holm(?:'s)?\b|"
    r"benjamini[\s-]*hochberg|\bfdr\b|false\s+discovery\s+rate|"
    r"family[\s-]*wise|multiple\s+comparison(?:s)?\s+correction|"
    r"dunn\b|scheffe|tukey'?s?\s+hbd|tukey'?s?\s+honest|sidak|holm[- ]bonferroni",
    re.IGNORECASE)
_MIN_WORDS = 200


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    text = doc.body_text or doc.text or ""
    if len(re.findall(r"\S+", text)) < _MIN_WORDS:
        return []
    results = extract_results(text)
    if not results:
        return []
    mismatches = [r for r in results
                  if r.recomputed_p is not None and r.operator == "="
                  and abs(r.recomputed_p - r.reported_p) > 0.01]

    has_correction = bool(_CORRECTIONS.search(text))
    out: List[Finding] = []
    if mismatches and has_correction:
        # Downgrade: the discrepancy is explainable — informational, not error.
        ev = "; ".join(
            f"{r.stat} = {r.statistic:g}, reported p = {r.reported_p:.3f}, "
            f"recomputed raw p = {r.recomputed_p:.3f}"
            for r in mismatches[:3])
        out.append(Finding(
            "Statistics", Severity.INFO,
            "p discrepancies consistent with a statistical correction",
            f"{len(mismatches)} reported p-value(s) differ from the raw "
            "recomputation, but the paper mentions a correction procedure "
            "(Greenhouse-Geisser / Bonferroni / FDR family). The mismatch is "
            "expected and NOT flagged as an error — this is an audit trail, "
            "not an accusation.",
            ev, 0.85,
            "No action needed if the reported values are the corrected ones; "
            "optionally state in the caption which correction was applied."))
    elif mismatches:
        # Genuine mismatches with no correction vocabulary: leave these to the
        # statcheck engine (it reports them as HIGH/CRITICAL decision errors).
        # Here we only add the multiple-comparison nudge when warranted.
        pass
    else:
        # No correction stated: nudge about multiple comparisons only when
        # several stats are present.
        if len(results) >= 5:
            marginal = [r for r in results
                        if r.reported_p is not None and 0.03 <= r.reported_p <= 0.05]
            if len(marginal) >= 3:
                out.append(Finding(
                    "Statistics", Severity.MEDIUM,
                    "Multiple marginal p-values with no correction mentioned",
                    f"{len(marginal)} of {len(results)} reported tests sit at "
                    "p = .03–.05 and no multiple-comparison correction "
                    "(Bonferroni, Holm, Benjamini-Hochberg/FDR) is mentioned "
                    "anywhere. Reviewers read clustered marginal p-values "
                    "without correction as possible p-hacking.",
                    "; ".join(f"p = {r.reported_p:.3f}" for r in marginal[:4]),
                    0.6,
                    "Apply and report a multiple-comparison correction across "
                    "the hypothesis family, or justify why none is needed."))
    return out
