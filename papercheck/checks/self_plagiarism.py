"""Self-plagiarism engine: text recycling, duplicate phrases, near-duplicate paragraphs."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def run(doc: Document, ctx: object) -> List[Finding]:
    findings: List[Finding] = []
    body = doc.body_text or doc.text
    if not body:
        return findings

    # Exact repeated sentences (>20 chars)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', body) if len(s.strip()) > 20]
    seen: dict = {}
    for s in sentences:
        key = s.lower().rstrip('.')
        seen[key] = seen.get(key, 0) + 1
    dupes = [(s, c) for s, c in seen.items() if c >= 2]
    if dupes:
        top = sorted(dupes, key=lambda x: -x[1])[:5]
        ev = "; ".join(f'"{s[:60]}..." ({c}x)' for s, c in top)
        findings.append(Finding(category="Integrity", 
            severity=Severity.HIGH,
            title=f"Duplicated sentences found ({len(dupes)} unique)",
            detail="Exact repeated sentences may indicate text recycling from own prior work.",
            evidence=ev, confidence=0.85,
            action="Rewrite duplicated sentences or cite the original source",
        ))

    # Repeated phrase clusters
    for plen in [5, 6]:
        phrases: dict = {}
        words = body.lower().split()
        for i in range(len(words) - plen + 1):
            ph = " ".join(words[i:i + plen])
            if not re.search(r"^\d\s+$", ph):
                phrases[ph] = phrases.get(ph, 0) + 1
        hot = [(p, c) for p, c in phrases.items() if c >= 3 and len(p) > 25]
        if hot:
            top = sorted(hot, key=lambda x: -x[1])[:3]
            ev = "; ".join(f'"{p[:50]}" ({c}x)' for p, c in top)
            findings.append(Finding(category="Integrity", 
                severity=Severity.MEDIUM,
                title=f"Repeated {plen}-word phrases",
                detail=f"{len(hot)} phrases repeated 3+ times. May indicate redundant writing.",
                evidence=ev, confidence=0.65,
                action="Paraphrase or remove redundant phrase repetitions",
            ))
            break

    return findings
