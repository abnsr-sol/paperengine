"""Risk model shared by every check engine.

A `Finding` is one evidence-linked risk. Severity expresses how likely the
issue is to contribute to rejection at a typical venue; confidence expresses
how sure the engine is that the finding is real (hard counts = high
confidence, heuristics = lower). The readiness score is a transparent
aggregation, never a definitive verdict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Severity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"

    @property
    def weight(self) -> float:
        return {
            Severity.CRITICAL: 40.0,
            Severity.HIGH: 20.0,
            Severity.MEDIUM: 8.0,
            Severity.LOW: 3.0,
            Severity.INFO: 0.0,
        }[self]

    @property
    def sort_rank(self) -> int:
        return {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }[self]


@dataclass
class Finding:
    category: str          # e.g. "Compliance", "Language", "AI-risk", ...
    severity: Severity
    title: str             # short headline, e.g. "Over venue word limit"
    detail: str            # what was found
    evidence: str          # the specific numbers / locations that back it
    action: str            # what the researcher should do
    confidence: float      # 0.0-1.0, how sure the engine is this finding is real
    location: str = ""     # section / paragraph hint
    source: str = ""       # which engine produced it

    def __post_init__(self) -> None:
        """Defensive coercion: a transposed positional argument in any of the
        94 engines can produce a string confidence or a string severity.
        Repair it at construction so sorting/scoring can never crash on bad
        types (e.g. 'bad operand type for unary -: str' in by_severity)."""
        # Repair a transposed (confidence, action) pair FIRST. Several engines
        # pass the numeric confidence into the `action` slot and the advice
        # text into `confidence`; without this, _as_confidence() would silently
        # coerce the advice text to 0.5 and the readiness score (weight x
        # confidence) would be understated. Detect by shape: numeric action
        # with non-numeric confidence is always the transposition.
        if _looks_numeric(self.action) and not _looks_numeric(self.confidence):
            self.action, self.confidence = self.confidence, self.action
        self.severity = severity_from_string(self.severity)
        self.confidence = _as_confidence(self.confidence)
        for name in ("category", "title", "detail", "evidence", "action",
                     "location", "source"):
            val = getattr(self, name)
            if val is None:
                setattr(self, name, "")
            elif not isinstance(val, str):
                setattr(self, name, str(val))


def severity_from_string(value: object) -> Severity:
    """Coerce anything (Severity, str, None) into a Severity — never raises."""
    if isinstance(value, Severity):
        return value
    norm = str(value).strip().lower() if value is not None else ""
    for sev in Severity:
        if sev.value.lower() == norm or sev.name.lower() == norm:
            return sev
    return Severity.INFO


def _as_confidence(value: object) -> float:
    """Coerce anything into a 0.0-1.0 float — never raises."""
    try:
        conf = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5
    if conf != conf:  # NaN
        return 0.5
    return max(0.0, min(1.0, conf))


def _looks_numeric(value: object) -> bool:
    """True if value is a number or a numeric-looking string (e.g. '0.95').

    Used to detect a transposed (confidence, action) pair at construction so a
    numeric action slot can be repaired back into confidence."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
            return True
        except (TypeError, ValueError):
            return False
    return False


@dataclass
class RiskReport:
    document_name: str
    venue: str
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: List[Finding]) -> None:
        self.findings.extend(findings)

    @property
    def readiness_score(self) -> int:
        """100 minus risk, with cluster-aware diminishing penalties.

        Each tier's raw weighted risk saturates (1 - e^(-raw/scale)) and is
        capped at a tier maximum. A cluster bonus applies: findings in the
        same category that appear together suggest a real problem, not noise,
        so isolated findings get a mild discount while clustered findings
        get full weight.

        A clean paper scores 100; one critical ≈ 77; a realistic messy draft
        (20 medium + 10 high) scores ~62. The worst possible paper
        approaches 0. Informational only, never a verdict.
        """
        tier_sums: Dict[Severity, float] = {sev: 0.0 for sev in Severity}
        for f in self.findings:
            tier_sums[f.severity] += f.severity.weight * f.confidence
        # Cluster bonus: count how many categories have ≥2 findings
        cat_counts: Dict[str, int] = {}
        for f in self.findings:
            cat_counts[f.category] = cat_counts.get(f.category, 0) + 1
        n_clustered = sum(1 for c, n in cat_counts.items() if n >= 2)
        n_cats = len(cat_counts) if cat_counts else 1
        cluster_ratio = min(1.0, n_clustered / max(1, n_cats))  # 0-1
        # Scale factor: isolated findings get 70% weight, clustered get 100%
        cluster_factor = 0.70 + 0.30 * cluster_ratio
        scale = {
            Severity.CRITICAL: 60.0,
            Severity.HIGH: 150.0,
            Severity.MEDIUM: 300.0,
            Severity.LOW: 200.0,
            Severity.INFO: 1.0,
        }
        max_contrib = {
            Severity.CRITICAL: 60.0,
            Severity.HIGH: 45.0,
            Severity.MEDIUM: 25.0,
            Severity.LOW: 18.0,
            Severity.INFO: 0.0,
        }
        penalty = 0.0
        for sev in Severity:
            raw = tier_sums[sev]
            if raw <= 0 or max_contrib[sev] <= 0:
                continue
            contrib = max_contrib[sev] * (1.0 - math.exp(-raw / scale[sev]))
            penalty += contrib * cluster_factor
        return max(0, min(100, int(round(100.0 - penalty))))

    def by_severity(self) -> List[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (f.severity.sort_rank, -f.confidence),
        )

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.severity.value] = out.get(f.severity.value, 0) + 1
        return out

    def by_severity_counts(self) -> List[tuple]:
        """Severity counts as (label, n) ordered CRITICAL..INFO."""
        counts = self.counts()
        order = [s.value for s in Severity]
        return [(k, counts[k]) for k in order if k in counts]


def fmt_confidence(value: float) -> str:
    pct = int(round(value * 100.0))
    if pct < 50:
        return f"{pct}% (uncertain)"
    return f"{pct}%"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))