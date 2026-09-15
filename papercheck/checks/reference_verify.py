"""Reference verification engine."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def run(doc: Document, ctx: object) -> List[Finding]:
    findings: List[Finding] = []
    body = doc.body_text or doc.text
    refs = doc.references or []
    if not body or not refs:
        return findings
    # Reference numbering gaps
    nums = sorted(set(int(m) for m in re.findall(r"\[(\d+)\]", body)))
    if nums:
        mx = max(nums)
        missing = sorted(set(range(1, mx+1)) - set(nums))
        if missing:
            ms = ", ".join(str(x) for x in missing)
            findings.append(Finding(category="References", severity=Severity.HIGH, title=f"Ref gaps: [{ms}]", detail=f"Refs should be 1..{mx}. Missing numbers look sloppy.", evidence=f"Missing: {missing}", confidence=0.95, action="Renumber references consecutively"))
    # Mixed citation formats
    has_num = bool(re.search(r"\[\d+\]", body))
    has_ay = bool(re.search(r"\([A-Z][a-z]+\s*,?\s*\d{4}\)", body))
    if has_num and has_ay:
        findings.append(Finding(category="References", severity=Severity.HIGH, title="Mixed citation formats", detail="Both [1] and (Author, Year) found. Use one style.", evidence="Numeric + author-year", confidence=0.95, action="Use consistent citation format"))
    # DOIs
    dw = sum(1 for r in refs if re.search(r"doi|http|10\.\d{4,}", r, re.IGNORECASE))
    if refs and dw == 0:
        findings.append(Finding(category="References", severity=Severity.HIGH, title="No DOIs in any reference", detail=f"All {len(refs)} refs lack DOIs.", evidence=f"0/{len(refs)} with DOI", confidence=0.95, action="Add DOI to every reference"))
    elif refs and dw < len(refs) * 0.3:
        findings.append(Finding(category="References", severity=Severity.MEDIUM, title="Most references lack DOIs", detail=f"Only {dw}/{len(refs)} have DOIs.", evidence=f"{dw}/{len(refs)}", confidence=0.85, action="Add DOIs to remaining references"))
    # Non-peer-reviewed
    bad = [i+1 for i,r in enumerate(refs) if re.search(r"wikipedia|blog|reddit|medium|news|twitter|youtube", r, re.IGNORECASE)]
    if bad:
        findings.append(Finding(category="References", severity=Severity.HIGH, title=f"Non-peer-reviewed sources: refs {bad[:5]}", detail="Blogs/Wikipedia/news not acceptable.", evidence=str(bad[:5]), confidence=0.90, action="Replace with peer-reviewed sources"))
    # Duplicate refs (numbering-insensitive: strip a leading [n] / 'n.'
    # and normalize whitespace so identical entries are caught even when
    # the list is numbered with different positions)
    seen = {}
    for i,r in enumerate(refs):
        k = re.sub(r'^\s*(?:\[\d+\]|\d+[.)])\s*', '', r)[:60].lower().strip()
        k = re.sub(r'\s+', ' ', k)
        if k in seen:
            findings.append(Finding(category="References", severity=Severity.HIGH, title=f"Duplicate reference", detail=f"Refs [{seen[k]+1}] and [{i+1}] identical.", evidence=f"Positions {seen[k]+1},{i+1}", confidence=0.80, action="Remove duplicate"))
        else: seen[k] = i
    # Reference density
    wc = doc.word_count or len(body.split())
    if refs and wc > 0 and wc / len(refs) > 500:
        findings.append(Finding(category="References", severity=Severity.MEDIUM, title="Low reference density", detail=f"{len(refs)} refs for {wc} words.", evidence=f"{len(refs)}/{wc}", confidence=0.70, action="Add more references"))
    return findings