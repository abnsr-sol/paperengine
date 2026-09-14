"""Data fabrication detector: Benford Law, terminal-digit analysis, impossible stats, internal consistency.

Extends the basic Benford check with PaperGuard-inspired numeric forensics:
- Terminal-digit analysis (last digit of rounded numbers should be uniform)
- Last-digit 0/5 clustering (fabricators favor round numbers)
- Decimal-fraction anomaly (too many exact .0 or .5 endings)
"""
from __future__ import annotations
import re, math, collections
from typing import List, Optional
from ..ingestion import Document
from ..risk import Finding, Severity

BENFORD = {1:0.301, 2:0.176, 3:0.125, 4:0.097, 5:0.079, 6:0.067, 7:0.058, 8:0.051, 9:0.046}

def _extract_numbers(text: str) -> List[float]:
    """Extract all positive numbers from text."""
    return [float(x) for x in re.findall(r"(?<!\d)(\d+\.?\d*)(?!\d)", text) if float(x) > 0]

def _extract_reported_stats(text: str) -> List[float]:
    """Extract numbers that appear in statistical reporting (mean, SD, t, F, r, p, n)."""
    stats = []
    for pat in [
        r"(?:mean|M|m)\s*[=:]\s*([\d.]+)",
        r"(?:SD|sd|std)\s*[=:]\s*([\d.]+)",
        r"\bt\s*[\(（]\s*\d+\s*[)）]\s*[=]\s*[-]?([\d.]+)",
        r"\bF\s*[\(（]\s*\d+\s*,\s*\d+\s*[)）]\s*[=]\s*([\d.]+)",
        r"\br\s*=\s*([\d.]+)",
        r"\bn\s*=\s*(\d+)",
    ]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                v = float(m.group(1))
                if v > 0:
                    stats.append(v)
            except (ValueError, IndexError):
                pass
    return stats

def _benford_test(nums: List[float]) -> Optional[float]:
    """Chi-square test against Benford's Law. Returns chi2 or None if insufficient data."""
    if len(nums) < 50:
        return None
    first_digits = []
    for n in nums:
        s = str(abs(n)).lstrip("0").lstrip(".")
        if s and s[0].isdigit() and s[0] != '0':
            d = int(s[0])
            if 1 <= d <= 9:
                first_digits.append(d)
    if len(first_digits) < 50:
        return None
    total = len(first_digits)
    chi2 = 0.0
    for d in range(1, 10):
        obs = first_digits.count(d) / total
        exp = BENFORD[d]
        chi2 += ((obs - exp) ** 2) / exp
    return chi2

def _terminal_digit_test(nums: List[float]) -> Optional[float]:
    """Terminal-digit analysis: last significant digit should be ~uniform.
    Fabricated data often has non-uniform terminal digits.
    Returns chi2 or None if insufficient data."""
    # Only consider numbers that have been rounded to integer or 1 decimal
    rounded = [n for n in nums if n == int(n) or (n * 10) == int(n * 10)]
    if len(rounded) < 40:
        return None
    terminals = [int(abs(n)) % 10 for n in rounded]
    total = len(terminals)
    observed = collections.Counter(terminals)
    chi2 = 0.0
    for d in range(10):
        obs = observed.get(d, 0) / total
        exp = 0.1  # uniform
        chi2 += ((obs - exp) ** 2) / exp
    return chi2

def _last_digit_05_test(nums: List[float]) -> Optional[float]:
    """Test for over-representation of numbers ending in 0 or 5.
    Fabricators disproportionately choose round numbers."""
    if len(nums) < 30:
        return None
    # Get last significant digit
    last_digits = []
    for n in nums:
        s = str(abs(n)).rstrip('0').rstrip('.')
        if s:
            last_digits.append(int(s[-1]) % 10)
    if len(last_digits) < 30:
        return None
    total = len(last_digits)
    zeros_fives = sum(1 for d in last_digits if d in (0, 5))
    proportion = zeros_fives / total
    # Expected: ~20% (digits 0 and 5 out of 10)
    # Threshold: >35% is suspicious
    if proportion > 0.35:
        return proportion
    return None

def _decimal_fraction_test(nums: List[float]) -> Optional[float]:
    """Test for suspiciously exact decimal fractions (.0, .5).
    Real measurements rarely land exactly on round decimals."""
    if len(nums) < 30:
        return None
    decimals = [n for n in nums if '.' in str(n) and not n == int(n)]
    if len(decimals) < 20:
        return None
    exact_round = sum(1 for n in decimals if n % 1.0 == 0 or n % 0.5 == 0)
    proportion = exact_round / len(decimals)
    # Expected: ~20-30% for real data; >50% is suspicious
    if proportion > 0.50:
        return proportion
    return None

def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text
    if not body: return findings
    nums = _extract_numbers(body)
    if nums:
        # Benford's Law
        chi2 = _benford_test(nums)
        if chi2 and chi2 > 20:
            findings.append(Finding(category="Integrity", severity=Severity.HIGH, title="Benford Law anomaly in numerical data", detail=f"Chi-square={chi2:.1f} (threshold=20). Fabricated data often deviates from Benford expected distribution.", evidence=f"{len(nums)} numbers, chi2={chi2:.1f}", confidence=0.65, action="Manual review of numerical data recommended"))
        # Terminal-digit analysis
        td_chi2 = _terminal_digit_test(nums)
        if td_chi2 and td_chi2 > 20:
            findings.append(Finding(category="Integrity", severity=Severity.MEDIUM, title="Terminal-digit non-uniformity", detail=f"Chi-square={td_chi2:.1f} (threshold=20). Fabricated data often shows non-uniform terminal digits.", evidence=f"Terminal-digit chi2={td_chi2:.1f}", confidence=0.55, action="Check if numbers were rounded or fabricated"))
        # Last-digit 0/5 clustering
        cluster_prop = _last_digit_05_test(nums)
        if cluster_prop:
            findings.append(Finding(category="Integrity", severity=Severity.MEDIUM, title="Last-digit 0/5 clustering detected", detail=f"{cluster_prop:.0%} of numbers end in 0 or 5 (expected ~20%). Fabricators disproportionately choose round numbers.", evidence=f"{cluster_prop:.0%} round endings", confidence=0.60, action="Verify that round-number concentrations are expected in this data"))
        # Decimal-fraction anomaly
        dec_prop = _decimal_fraction_test(nums)
        if dec_prop:
            findings.append(Finding(category="Integrity", severity=Severity.MEDIUM, title="Suspicious decimal-fraction pattern", detail=f"{dec_prop:.0%} of decimal numbers land exactly on .0 or .5. Real measurements rarely cluster this precisely.", evidence=f"{dec_prop:.0%} exact-round decimals", confidence=0.50, action="Check if measurement precision justifies these exact values"))
    # Impossible percentages
    for val in re.findall(r"(\d+\.?\d*)\s*%", body):
        try:
            v = float(val)
            if v > 100 and v < 9999:
                findings.append(Finding(category="Integrity", severity=Severity.CRITICAL, title=f"Impossible percentage: {val}%", detail="Percentage exceeds 100%.", evidence=f"{val}%", confidence=0.95, action="Verify percentage calculation"))
                break
        except: pass
    # Impossible correlation
    for val in re.findall(r"r\s*=\s*([-.\d]+)", body):
        try:
            if abs(float(val)) > 1.0:
                findings.append(Finding(category="Integrity", severity=Severity.CRITICAL, title=f"Impossible r={val}", detail="Correlation must be [-1,1].", evidence=f"r={val}", confidence=0.99, action="Verify r-value"))
        except: pass
    # Table vs text number mismatches (n= in different places)
    ns = sorted(set(int(n) for n in re.findall(r"[nN]\s*=\s*(\d+)", body)))
    if len(ns) >= 2:
        findings.append(Finding(category="Integrity", severity=Severity.MEDIUM, title=f"Multiple sample sizes: {ns}", detail="Different n values found. Ensure each table/figure states its n.", evidence=f"n = {ns}", confidence=0.70, action="State n for each table/figure"))
    # p = 0.000
    if re.search(r"p\s*[=<>]\s*0\.000", body, re.IGNORECASE):
        findings.append(Finding(category="Integrity", severity=Severity.HIGH, title="p=0.000 reported", detail="Should be p < .001 per APA/AMA.", evidence="p=0.000 found", confidence=0.98, action="Replace with p < .001"))
    return findings