"""Data fabrication detector: Benford Law, impossible stats, internal consistency."""
from __future__ import annotations
import re, math
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

BENFORD = {1:0.301, 2:0.176, 3:0.125, 4:0.097, 5:0.079, 6:0.067, 7:0.058, 8:0.051, 9:0.046}

def _extract_numbers(text):
    return [float(x) for x in re.findall(r"(?<!\d)(\d+\.?\d*)(?!\d)", text) if float(x) > 0]

def _benford_test(nums):
    if len(nums) < 50: return None
    first_digits = [int(str(abs(n)).lstrip("0").lstrip(".")[0]) for n in nums if str(abs(n)).lstrip("0").lstrip(".")]
    first_digits = [d for d in first_digits if 1 <= d <= 9]
    if len(first_digits) < 50: return None
    total = len(first_digits)
    chi2 = 0
    for d in range(1, 10):
        obs = first_digits.count(d) / total
        exp = BENFORD[d]
        chi2 += ((obs - exp) ** 2) / exp
    return chi2

def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text
    if not body: return findings
    nums = _extract_numbers(body)
    if nums:
        chi2 = _benford_test(nums)
        if chi2 and chi2 > 20:
            findings.append(Finding(category="Integrity", severity=Severity.HIGH, title="Benford Law anomaly in numerical data", detail=f"Chi-square={chi2:.1f} (threshold=20). Fabricated data often deviates from Benford expected distribution.", evidence=f"{len(nums)} numbers, chi2={chi2:.1f}", confidence=0.65, action="Manual review of numerical data recommended"))
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