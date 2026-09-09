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


def severity_from_string(value: str) -> Severity:
    norm = value.strip().lower()
    for sev in Severity:
        if sev.value.lower() == norm or norm in ("critical", "high", "medium", "low", "info"):
            if sev.value.lower() == norm:
                return sev
    return Severity.INFO


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
        """100 minus risk, with diminishing penalties per severity tier.

        Each tier's raw weighted risk saturates (1 - e^(-raw/scale)) and is
        capped at a tier maximum, so a couple of critical findings drive the
        score down sharply while a long tail of low-severity notes cannot by
        itself zero it. A clean paper scores 100; the worst possible paper
        approaches 0. Informational only, never a verdict.
        """
        tier_sums: Dict[Severity, float] = {sev: 0.0 for sev in Severity}
        for f in self.findings:
            tier_sums[f.severity] += f.severity.weight * f.confidence
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
            penalty += max_contrib[sev] * (1.0 - math.exp(-raw / scale[sev]))
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


def fmt_confidence(value: float) -> str:
    pct = int(round(value * 100.0))
    if pct < 50:
        return f"{pct}% (uncertain)"
    return f"{pct}%"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))