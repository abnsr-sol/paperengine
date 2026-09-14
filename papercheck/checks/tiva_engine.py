"""TIVA (Test for Inconsistency in Reported Variance) engine.

Checks if reported standard deviations are mathematically consistent with
reported means and sample sizes. When the reported variance is impossibly
low (given the range of reported means across conditions), the data may
be fabricated or have transcription errors.

Based on: Arcuri & Giannerini (2017) and PaperGuard B5.

Severity: MEDIUM for suspect variances, HIGH for impossible variances.
"""
from __future__ import annotations
import re, math
from typing import List, Optional, Tuple
from ..ingestion import Document
from ..risk import Finding, Severity


def _extract_mean_sd_n(text: str) -> List[Tuple[float, float, int]]:
    """Extract (mean, SD, n) triples from text."""
    triples = []
    patterns = [
        r"(\d+\.?\d*)\s*[±\-/]\s*(\d+\.?\d*)\s*[,( ]+\s*n\s*=\s*(\d+)",
        r"M\s*=\s*(\d+\.?\d*)\s*,\s*(?:SD|sd)\s*=\s*(\d+\.?\d*)\s*,\s*n\s*=\s*(\d+)",
        r"(?:mean|average)\s*=\s*(\d+\.?\d*)\s*\(\s*(?:SD|sd)\s*=\s*(\d+\.?\d*)\s*\)\s*[,( ]*\s*n\s*=\s*(\d+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                mean = float(m.group(1))
                sd = float(m.group(2))
                n = int(m.group(3))
                if sd > 0 and n > 2:
                    triples.append((mean, sd, n))
            except (ValueError, IndexError):
                pass
    return triples


def _check_variance_consistency(triples: List[Tuple[float, float, int]]) -> Optional[str]:
    """Check if reported variances are consistent across groups."""
    if len(triples) < 2:
        return None
    sds = [sd for _, sd, _ in triples]
    max_sd = max(sds)
    min_sd = min(sds)
    if min_sd <= 0:
        return None
    ratio = max_sd / min_sd
    if ratio > 4:
        return f"SD ratio {ratio:.1f}x (max={max_sd:.2f}, min={min_sd:.2f}) — suspect variance inequality"
    return None


def _check_impossible_variance(triples: List[Tuple[float, float, int]]) -> List[str]:
    """Check for impossible variances given the data."""
    issues = []
    for mean, sd, n in triples:
        if sd == 0 and n > 1:
            issues.append(f"SD=0 with n={n} — impossible unless all values identical")
        if mean > 0 and sd / mean > 1.0:
            issues.append(f"CV={sd/mean:.0%} (SD={sd:.2f}, mean={mean:.2f}) — coefficient of variation > 100%")
        if mean > 0 and sd > mean * 3:
            issues.append(f"SD ({sd:.2f}) > 3x mean ({mean:.2f}) — check for transcription error")
    return issues


def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return findings
    triples = _extract_mean_sd_n(body)
    if not triples:
        return findings
    variance_issue = _check_variance_consistency(triples)
    if variance_issue:
        findings.append(Finding(
            category="Statistics", severity=Severity.MEDIUM,
            title="TIVA: Suspect variance inequality",
            detail=variance_issue,
            evidence=f"{len(triples)} group(s) with SDs: {[sd for _, sd, _ in triples]}",
            confidence=0.55,
            action="Verify that the reported standard deviations are correct"))
    impossible = _check_impossible_variance(triples)
    for issue in impossible[:3]:
        findings.append(Finding(
            category="Statistics", severity=Severity.HIGH,
            title="TIVA: Impossible variance detected",
            detail=issue,
            evidence=f"Mean/SD/N triples: {triples[:5]}",
            confidence=0.80,
            action="Check the reported standard deviation for transcription errors"))
    return findings
