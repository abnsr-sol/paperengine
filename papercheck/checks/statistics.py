"""Statistics engine: p-values, effect sizes, impossible stats, sample sizes."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def _has_stats(text: str) -> bool:
    patterns = [r'\bp\s*[<>=]\s*0\.\d', r'\bt\s*\(\s*\d+', r'\bF\s*\(\s*\d+', r'\br\s*[=]\s*[-\d]', r'\bOR\s*[=]', r'\bCI\b', r'\bstatistically\b', r'\bsignificant\b', r'\beffect\s+size', r'\bregression\b', r'\bsample\s+size']
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)

def run(doc: Document, ctx: object) -> List[Finding]:
    findings: List[Finding] = []
    body = doc.body_text or doc.text
    if not _has_stats(body):
        return findings
    # p = 0.000
    if re.search(r'p\s*[=<>]\s*0\.000\b', body, re.IGNORECASE):
        findings.append(Finding(category="Statistics", severity=Severity.HIGH, title="p-value reported as 0.000", detail="Should be 'p < .001' per APA/AMA guidelines.", evidence="p = 0.000 found", confidence=0.98, action="Replace 'p = 0.000' with 'p < .001'"))
    # significant without p
    for m in re.finditer(r'(?:is|was|are|were)\s+statistically\s+significant', body, re.IGNORECASE):
        ctx_text = body[max(0,m.start()-80):min(len(body),m.end()+80)]
        if not re.search(r'p\s*[<>=]\s*0?\.\d', ctx_text):
            findings.append(Finding(category="Statistics", severity=Severity.HIGH, title="'Significant' without exact p-value", detail="Add exact p-value next to significance claim.", evidence=f"Context: ...{ctx_text.strip()[:100]}...", confidence=0.95, action="Add p-value (e.g., p = 0.03)"))
            break
    # Missing effect sizes
    has_effect = bool(re.search(r"cohen'?s?\s*d\s*[=<>]|\bOR\s*[=<>]\s*[\d.]|\bodds\s+ratio|R[_²]*squared|beta\b|eta|\bη", body, re.IGNORECASE))
    if not has_effect and re.search(r'\bregression\b', body, re.IGNORECASE):
        findings.append(Finding(category="Statistics", severity=Severity.HIGH, title="No effect sizes reported", detail="Regression found but no Cohen's d, OR, or R-squared.", evidence="No effect-size metrics found", confidence=0.90, action="Report effect sizes for every statistical test"))
    # Impossible r
    for val in re.findall(r'\br\s*[=]\s*([-\d.]+)', body):
        try:
            if abs(float(val)) > 1.0:
                findings.append(Finding(category="Statistics", severity=Severity.CRITICAL, title="Impossible correlation coefficient", detail=f"r = {val} is outside [-1, 1].", evidence=f"r = {val}", confidence=0.99, action="Verify r-value"))
        except ValueError: pass
    # Multiple comparisons
    sig_count = len(re.findall(r'\bp\s*<\s*0?\.\d+', body))
    if sig_count >= 3 and not re.search(r'bonferroni|fdr|holm|sidak|tukey|benjamini|hochberg', body, re.IGNORECASE):
        findings.append(Finding(category="Statistics", severity=Severity.HIGH, title="Multiple comparisons without correction", detail=f"{sig_count} significant p-values but no correction mentioned.", evidence=f"Sig p-values: {sig_count}", confidence=0.85, action="Apply Bonferroni/FDR/Holm correction"))
    # Inconsistent n
    ns = sorted(set(int(n) for n in re.findall(r'[nN]\s*=\s*(\d+)', body)))
    if len(ns) >= 2:
        findings.append(Finding(category="Statistics", severity=Severity.MEDIUM, title="Multiple sample sizes reported", detail=f"Different n values: {ns}. Explain if subsets/exclusions.", evidence=f"n = {ns}", confidence=0.70, action="State n for each table/figure and explain differences"))
    # Regression without R-squared
    if re.search(r'\bregression\b', body, re.IGNORECASE) and not re.search(r'R[_\s²]*squared\s*[=]', body, re.IGNORECASE):
        findings.append(Finding(category="Statistics", severity=Severity.MEDIUM, title="Regression without R-squared", detail="Report model fit (R-squared).", evidence="Regression found, no R-squared", confidence=0.80, action="Report R-squared"))
    return findings
