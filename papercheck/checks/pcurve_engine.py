"""p-curve analysis engine — detects p-hacking via suspicious p-value distributions.

The p-curve method (Simonsohn, Nelson & Simmons 2014) examines the distribution
of statistically significant p-values (p < .05). When studies have a true
effect, the p-curve is right-skewed (more p-values near .01 than near .049).
When studies are p-hacked (selectively reporting just-significant results),
the p-curve is flat or left-skewed.

Based on: Simonsohn, Nelson & Simmons (2014, JPSP) and PaperGuard B7.
Severity: MEDIUM for suspicious distributions, INFO for healthy distributions.
"""
from __future__ import annotations
import re, math
from typing import List, Optional
from ..ingestion import Document
from ..risk import Finding, Severity


def _extract_pvalues(text: str) -> List[float]:
    """Extract exact p-values from text."""
    pvals = []
    for m in re.finditer(r"p\s*[=<]\s*\.?(\d+\.?\d*)", text, re.IGNORECASE):
        try:
            v = float(m.group(1))
            if 0 < v < 1:
                pvals.append(v)
        except ValueError:
            pass
    return pvals


def _normal_cdf(x: float) -> float:
    """Standard normal CDF approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _binomial_right_skew_test(pvals: List[float]) -> Optional[dict]:
    """Test if the p-curve is significantly right-skewed."""
    if len(pvals) < 5:
        return None
    low = sum(1 for p in pvals if p < 0.025)
    high = sum(1 for p in pvals if 0.025 <= p < 0.05)
    n = low + high
    if n < 5:
        return None
    expected = n * 0.5
    if expected == 0:
        return None
    z = (low - expected) / math.sqrt(expected * 0.5)
    skew_p = 2 * (1 - _normal_cdf(abs(z)))
    prop_below = low / n if n > 0 else 0.5
    return {
        "n_significant": n,
        "low": low,
        "high": high,
        "prop_below_025": prop_below,
        "z": z,
        "skew_p": skew_p,
        "direction": "right-skewed" if z > 0 else "left-skewed",
    }


def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return findings
    pvals = _extract_pvalues(body)
    sig_pvals = [p for p in pvals if p < 0.05]
    if len(sig_pvals) < 5:
        return findings
    result = _binomial_right_skew_test(sig_pvals)
    if result is None:
        return findings
    n = result["n_significant"]
    prop = result["prop_below_025"]
    direction = result["direction"]
    skew_p = result["skew_p"]
    if direction == "left-skewed" and skew_p < 0.10:
        findings.append(Finding(
            category="Statistics", severity=Severity.MEDIUM,
            title="p-curve: Suspicious distribution of significant p-values",
            detail=f"The p-curve is {direction} (z={result['z']:.2f}, p={skew_p:.3f}). "
                   f"{prop:.0%} of significant p-values are below .025 (expected >50% for true effects). "
                   "This pattern is consistent with selective reporting or p-hacking.",
            evidence=f"{n} significant p-values: {result['low']} < .025, {result['high']} in .025-.05",
            confidence=0.60,
            action="Consider pre-registering analyses and reporting all conducted tests"))
    elif direction == "right-skewed" and skew_p < 0.05:
        findings.append(Finding(
            category="Statistics", severity=Severity.INFO,
            title="p-curve: Healthy distribution (right-skewed)",
            detail=f"The p-curve is significantly right-skewed (z={result['z']:.2f}, p={skew_p:.3f}), "
                   "indicating the reported effects likely reflect true effects rather than p-hacking.",
            evidence=f"{n} significant p-values: {result['low']} < .025, {result['high']} in .025-.05",
            confidence=0.70,
            action="The statistical evidence is consistent with genuine effects"))
    return findings
