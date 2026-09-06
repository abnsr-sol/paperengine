"""Fix-plan generator: converts a RiskReport's findings into a prioritized,
effort-estimated pre-submission checklist.

Ordering: severity first (critical -> low), then confidence descending within
a tier. Effort is estimated from the finding's action text length and the
category (statement additions are quick; restructuring is slower).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .risk import Finding, RiskReport, Severity

_QUICK_CATEGORIES = {
    "Statement", "Submission", "Author Info", "Authorship", "AI Disclosure",
    "Compliance", "Abstract", "Supplementary", "Data License", "Peer Review",
    "Venue Extras",
}
_SLOW_CATEGORIES = {"Language", "Flow", "Paragraphs", "Writing Depth", "Redundancy",
                    "Figure Quality", "Editorial Format"}


@dataclass
class FixStep:
    order: int
    severity: Severity
    title: str
    action: str
    evidence: str
    effort: str          # "5 min" | "30 min" | "1-2 h" | "2+ h"
    confidence: float

    def as_line(self) -> str:
        flag = {Severity.CRITICAL: "[CRITICAL]", Severity.HIGH: "[HIGH]",
                Severity.MEDIUM: "[MED]", Severity.LOW: "[LOW]",
                Severity.INFO: "[info]"}[self.severity]
        return f"{self.order:>2}. {flag} {self.title}  ({self.effort})\n     -> {self.action}"


def _effort(f: Finding) -> str:
    words = len(f.action.split())
    if f.category in _QUICK_CATEGORIES:
        return "5 min" if words <= 18 else "30 min"
    if f.category in _SLOW_CATEGORIES:
        return "1-2 h"
    if words <= 12:
        return "30 min"
    if re.search(r"add|state|include|declare|provide|register|deposit|report", f.action, re.IGNORECASE):
        return "30 min"
    if re.search(r"rewrite|restructure|expand|re-analy|collect|conduct", f.action, re.IGNORECASE):
        return "2+ h"
    return "1-2 h"


def _dedup(findings: List[Finding]) -> List[Finding]:
    """Drop near-duplicate findings across engines (same title or same
    normalized title). Keeps the first (highest-severity/confidence) copy."""
    seen: set = set()
    out: List[Finding] = []
    for f in findings:
        key = re.sub(r"[^a-z0-9]+", "", f.title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def build_fix_plan(report: RiskReport) -> List[FixStep]:
    ranked = _dedup(report.by_severity())   # severity asc-rank, confidence desc within tier
    steps: List[FixStep] = []
    for i, f in enumerate(ranked, 1):
        steps.append(FixStep(
            order=i,
            severity=f.severity,
            title=f.title,
            action=f.action,
            evidence=f.evidence,
            effort=_effort(f),
            confidence=f.confidence,
        ))
    return steps


def render_fix_plan(report: RiskReport) -> str:
    steps = build_fix_plan(report)
    if not steps:
        return "No fixable findings - paper looks clean."
    counts = report.counts()
    total_min = 0
    for s in steps:
        if s.effort == "5 min":
            total_min += 5
        elif s.effort == "30 min":
            total_min += 30
        elif s.effort == "1-2 h":
            total_min += 90
        else:
            total_min += 150
    hours = total_min / 60.0
    lines = [
        f"PRE-SUBMISSION FIX PLAN - {report.document_name} ({report.venue})",
        f"Findings: {len(steps)}  " + "  ".join(f"{k}:{v}" for k, v in counts.items()),
        f"Estimated total effort: ~{hours:.1f} h (mechanical estimates, real work varies)",
        "=" * 64,
    ]
    lines.extend(s.as_line() for s in steps)
    lines.append("=" * 64)
    lines.append("Work the CRITICAL and HIGH items first; they drive most desk rejects.")
    lines.append("Every finding is a risk signal, not a verdict - use judgment.")
    return "\n".join(lines)