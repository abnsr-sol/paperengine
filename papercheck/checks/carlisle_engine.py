"""Carlisle baseline-balance engine: RCT integrity via baseline-table forensics.

Implements the method Carlisle used to expose fabricated RCTs (Fujii 2017,
Anaesthesia): for each baseline variable, the standardized difference between
groups converts to a two-tailed p-value; across many baseline variables those
p-values must look uniform(0,1). Real randomization shows the full spread;
fabricated data shows implausible single-variable differences or "too perfect"
balance (p-values piled at the high end).

Text-only, offline heuristic subset: we need (mean, SD) pairs for two groups
of the same variable from the running text. Tables flatten in plain-text
extraction, so "45.2 (11.3) vs 44.8 (10.9)" / "45.2 +/- 11.3 vs ..." patterns
are matched conservatively. Flag-not-verdict: every finding lists innocent
explanations (transcription error, genuinely balanced covariates).
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from ..ingestion import Document
from ..risk import Finding, Severity

# RCT context required — Carlisle logic only applies to randomized trials.
_RCT = re.compile(
    r"randomi[sz]ed|randomly\s+assigned|random\s+allocation|placebo[\s-]controlled"
    r"|double[\s-]blind|controlled\s+trial",
    re.IGNORECASE)

# "45.2 (11.3) vs 44.8 (10.9)" — mean (SD) vs mean (SD), optionally ± form,
# optionally preceded by a variable-ish word context. Two "vs"/"versus"/";"
# separated mean(SD) pairs is the smallest comparable unit.
_PAIR = re.compile(
    r"(\d{1,4}(?:\.\d+)?)\s*[([{]?\s*(?:\u00b1|plus/?minus|\+/-)?\s*(\d{1,4}(?:\.\d+)?)\s*[)\]}]?"
    r"\s*(?:vs\.?|versus|;|and)\s*"
    r"(\d{1,4}(?:\.\d+)?)\s*[([{]?\s*(?:\u00b1|plus/?minus|\+/-)?\s*(\d{1,4}(?:\.\d+)?)\s*[)\]}]?")

# SD of zero (or tiny) makes the z computation meaningless.
_MIN_SD = 0.05


def _two_tailed_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def _extract_pairs(body: str) -> List[Tuple[float, float, float, float]]:
    """Extract (m1, sd1, m2, sd2) candidate baseline comparisons."""
    out = []
    for m in _PAIR.finditer(body):
        m1, sd1, m2, sd2 = (float(m.group(i)) for i in range(1, 5))
        if sd1 >= _MIN_SD and sd2 >= _MIN_SD:
            out.append((m1, sd1, m2, sd2))
    return out


def _standardized_z(m1: float, sd1: float, m2: float, sd2: float) -> Optional[float]:
    """Large-sample z for the difference of two means (pooled SD denominator)."""
    denom = math.sqrt((sd1 * sd1 + sd2 * sd2) / 2.0)
    if denom < _MIN_SD:
        return None
    return abs(m1 - m2) / denom


def run(doc: Document, ctx: object) -> List[Finding]:
    findings: List[Finding] = []
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200 or not _RCT.search(body):
        return findings
    pairs = _extract_pairs(body)
    if len(pairs) < 4:
        return findings  # need a baseline table's worth of comparisons

    # (a) Implausible single-variable difference: |z| > 4 is p < 6e-5 —
    # virtually never occurs in real randomized baselines; classic sign of a
    # transcribed SD or non-random "grouping".
    for (m1, sd1, m2, sd2) in pairs:
        z = _standardized_z(m1, sd1, m2, sd2)
        if z is not None and z > 4.0:
            p = _two_tailed_p(z)
            findings.append(Finding(
                category="Statistics", severity=Severity.HIGH,
                title="Carlisle: implausible baseline difference",
                detail=(
                    f"Two baseline groups differ by {z:.1f} SD "
                    f"(p={p:.1e}) — real randomized baselines almost never "
                    "differ this much. Common innocent causes: transcribed "
                    "SD, swapped SD/SE, or summarizing a non-random subgroup. "
                    "Verify the source table before submission."),
                evidence=f"{m1} ({sd1}) vs {m2} ({sd2}) -> z={z:.2f}, p={p:.2e}",
                confidence=0.70,
                action="Re-check the baseline table: is the SD an SE in "
                       "disguise? Do the groups genuinely come from one "
                       "randomized pool?"))
            break  # one concrete example is enough; don't spam the report

    # (b) Too-consistent balance: with >=8 baseline comparisons, real
    # randomization yields some low p-values; >=5/8 above 0.6 is the pile-up
    # Carlisle used to flag fabrication. Weak signal on its own — MEDIUM/0.5.
    if len(pairs) >= 8:
        ps = []
        for (m1, sd1, m2, sd2) in pairs:
            z = _standardized_z(m1, sd1, m2, sd2)
            if z is not None:
                ps.append(_two_tailed_p(z))
        high = sum(1 for p in ps if p > 0.6)
        if len(ps) >= 8 and high >= max(5, int(0.6 * len(ps))):
            findings.append(Finding(
                category="Statistics", severity=Severity.MEDIUM,
                title="Carlisle: suspiciously uniform baseline balance",
                detail=(
                    f"{high}/{len(ps)} baseline comparisons have p>0.6 — "
                    "real randomized baselines show the full p-value spread. "
                    "A pile-up near 1.0 was the signature in Carlisle's "
                    "fabricated-RCT analyses, but can also occur with "
                    "frequency-matched or paired designs."),
                evidence=f"p-values: {[round(p, 2) for p in ps[:12]]}",
                confidence=0.50,
                action="If groups were matched/paired, say so in Methods; "
                       "otherwise re-verify the baseline statistics "
                       "against the raw data"))
    return findings
