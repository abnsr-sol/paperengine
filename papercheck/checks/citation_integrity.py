"""Citation integrity: self-citation ratio, citation age, format mixing, gaps."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text
    refs = doc.references or []
    if not body:
        return findings
    # Reference numbering gaps
    nums = sorted(set(int(m) for m in re.findall(r'\[(\d+)\]', body)))
    if nums:
        expected = set(range(1, max(nums)+1))
        missing = sorted(expected - set(nums))
        if missing:
            findings.append(Finding(category="Citations", severity=Severity.HIGH, title=f'Reference numbering gaps: [{', '.join(str(x) for x in missing)}]', detail='References [1]..[N] should be consecutive. Missing numbers look sloppy.', evidence=f'Found: {nums[:10]}... Missing: {missing}', confidence=0.95, action='Renumber references consecutively or verify missing citations'))
    # Citation format mixing ([1] vs (Author, Year))
    has_numeric = bool(re.search(r'\[\d+\]', body))
    has_author = bool(re.search(r'\([A-Z][a-z]+(?:\s+(?:et\s+al|and|&))?\s*,?\s*\d{4}\)', body))
    if has_numeric and has_author:
        findings.append(Finding(category="Citations", severity=Severity.HIGH, title='Mixed citation formats', detail='Both [1] (numeric) and (Author, Year) formats detected. Pick one style.', evidence='Numeric [n] and author-year (Name, Year) both present', confidence=0.95, action='Use consistent citation format throughout'))
    # Reference list: check for DOIs/URLs
    refs_with_doi = sum(1 for r in refs if re.search(r'doi|http|10\.\d{4,}', r, re.IGNORECASE))
    if refs and refs_with_doi == 0:
        findings.append(Finding(category="Citations", severity=Severity.HIGH, title='No DOIs or URLs in any reference', detail=f'All {len(refs)} references lack DOIs. Editors use DOIs to verify reference validity.', evidence=f'0/{len(refs)} refs have DOI/URL', confidence=0.95, action='Add DOI to every reference (use CrossRef or DOI lookup)'))
    elif refs and refs_with_doi < len(refs) * 0.3:
        findings.append(Finding(category="Citations", severity=Severity.MEDIUM, title='Most references lack DOIs', detail=f'Only {refs_with_doi}/{len(refs)} references have DOIs.', evidence=f'{refs_with_doi}/{len(refs)} with DOI', confidence=0.85, action='Add DOIs to remaining references'))
    # Citation density: intro should have many, results few
    intro_match = re.search(r'(?:1\s*\.?\s*)?[Ii]ntroduction', body)
    results_match = re.search(r'(?:[Rr]esults?|[Ee]xperimental?)', body)
    if intro_match and results_match:
        intro_text = body[intro_match.start():results_match.start()]
        results_text = body[results_match.start():min(len(body), results_match.start()+3000)]
        intro_cites = len(re.findall(r'\[\d+\]', intro_text))
        results_cites = len(re.findall(r'\[\d+\]', results_text))
        if intro_cites < 3 and len(intro_text) > 200:
            findings.append(Finding(category="Citations", severity=Severity.MEDIUM, title='Low citation density in Introduction', detail=f'Only {intro_cites} citations in Introduction. Literature should be well-cited.', evidence=f'{intro_cites} citations in intro', confidence=0.70, action='Add citations to support claims in the Introduction'))
    # Reference count vs body size
    word_count = doc.word_count or len(body.split())
    if refs and word_count > 0:
        ratio = word_count / len(refs)
        if ratio > 500:
            findings.append(Finding(category="Citations", severity=Severity.MEDIUM, title='Low reference density', detail=f'{len(refs)} references for {word_count} words (1 ref per {ratio:.0f} words). Reviewers expect adequate literature coverage.', evidence=f'{len(refs)} refs / {word_count} words', confidence=0.70, action='Add more references, especially to recent and foundational work'))
    # Duplicate references (same title appearing twice)
    titles = {}
    for i, r in enumerate(refs):
        # Extract first ~30 chars as title proxy
        t = r[:60].lower().strip()
        if t in titles:
            findings.append(Finding(category="Citations", severity=Severity.HIGH, title='Duplicate reference detected', detail=f'References [{titles[t]+1}] and [{i+1}] appear identical.', evidence=f'Positions {titles[t]+1} and {i+1}', confidence=0.80, action='Remove the duplicate reference'))
        else:
            titles[t] = i
    return findings
