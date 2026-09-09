"""SPRITE engine: dataset feasibility for reported (M, SD, N, scale).

Wraps `papercheck.sprite`. Fires only on mathematically impossible
combinations — same evidence class as GRIM/statcheck. The finding always
states the bounded-integer-scale assumption so continuous scales are not
mis-flagged (they are skipped by the extractor).
"""
from __future__ import annotations

import os
import re
import sys
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from papercheck.sprite import extract_sprite  # noqa: E402


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.body_text or doc.text or ""
    if not text or len(text.split()) < 200:
        return []
    results = extract_sprite(text)
    violations = [r for r in results if not r.feasible]
    out: List[Finding] = []
    for r in violations[:3]:
        out.append(Finding(
            "Statistics", Severity.CRITICAL,
            f"Reported mean/SD combination is mathematically impossible (SPRITE)",
            f"No dataset of N={r.n} integers on the {r.scale_min}-{r.scale_max} "
            f"scale can produce M={r.reported_mean} with SD={r.reported_sd} at "
            "the reported rounding. The same certainty class as GRIM: this is "
            "arithmetic, not a heuristic. Non-integer scales (averaged "
            "subscales) are excluded by the extractor, but verify the scale "
            "assumption before acting.",
            r.context,
            "Recheck the raw data and recompute the descriptive statistics; "
            "impossible M/SD pairs trigger integrity scrutiny from reviewers.",
            0.9, source="sprite"))
    if results and not violations:
        tested = len(results)
        out.append(Finding(
            "Statistics", Severity.INFO,
            f"SPRITE feasibility passed on {tested} M/SD/N triple(s)",
            "All reported mean/SD combinations are achievable by integer "
            "datasets on the declared scale — a clean integrity signal.",
            f"{tested} triple(s) tested against bounded-integer reconstruction",
            "No action needed — this is what reviewers' forensic checks look "
            "for and find nothing.", 0.9, source="sprite"))
    return out
