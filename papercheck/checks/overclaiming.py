"""Overclaiming engine: detects unsupported superlatives and hedging overuse."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

# Superlatives that need justification
SUPERLATIVES = [
    (r'\bnovel\b', "novel"),
    (r'\bfirst\b.*(?:to|in|we|this|our)', "first"),
    (r'\bunprecedented\b', "unprecedented"),
    (r'\bunique\b', "unique"),
    (r'\bbreakthrough\b', "breakthrough"),
    (r'\bgroundbreaking\b', "groundbreaking"),
    (r'\bpioneer', "pioneer"),
    (r'\bstate-of-the-art\b', "state-of-the-art"),
    (r'\bcutting.edge\b', "cutting-edge"),
    (r'\brevolutionary\b', "revolutionary"),
    (r'\btransformative\b', "transformative"),
]

# Hedging overuse markers
HEDGE_WORDS = [r'\bmay\b', r'\bmight\b', r'\bcould\b', r'\bpossibly\b',
               r'\bpotentially\b', r'\bsuggests?\b', r'\bappears?\b',
               r'\bseems?\b', r'\blikely\b', r'\bperhaps\b']

def run(doc: Document, ctx: object) -> List[Finding]:
    findings: List[Finding] = []
    body = doc.body_text or doc.text
    if not body:
        return findings

    # --- Overclaiming ---
    for pattern, label in SUPERLATIVES:
        matches = re.findall(pattern, body, re.IGNORECASE)
        if len(matches) >= 3:
            findings.append(Finding(category="Claims", 
                severity=Severity.MEDIUM,
                title=f"Frequent use of '{label}' ({len(matches)} times)",
                detail=f"'{label}' appears {len(matches)} times. Overclaiming is a major reviewer concern — ensure every superlative is backed by evidence.",
                evidence=f"'{label}': {len(matches)} occurrences",
                confidence=0.80,
                action=f"Justify every use of '{label}' or soften language (e.g., 'novel' → 'a new')",
                location="Full manuscript",
            ))

    # --- Hedging overuse ---
    hedge_count = sum(len(re.findall(p, body, re.IGNORECASE)) for p in HEDGE_WORDS)
    word_count = doc.word_count or len(body.split())
    if word_count > 0:
        hedge_density = hedge_count / (word_count / 1000)
        if hedge_density > 15:
            findings.append(Finding(category="Claims", 
                severity=Severity.MEDIUM,
                title=f"Excessive hedging language ({hedge_count} instances)",
                detail=f"~{hedge_density:.1f} hedge words per 1000 words (high: >15). Too much hedging weakens your claims and frustrates reviewers.",
                evidence=f"{hedge_count} hedge words in {word_count} words",
                confidence=0.75,
                action="Reduce hedging — state findings directly where evidence supports them",
                location="Full manuscript",
            ))

    # --- "Novel" in abstract without "first" or comparison ---
    abstract = ""
    for sec in getattr(doc, 'sections', []) or []:
        if sec.heading and 'abstract' in sec.heading.lower():
            abstract = sec.body or ""
            break
    if not abstract and getattr(doc, 'paragraphs', None):
        abstract = doc.paragraphs[0] or ""
    if abstract:
        novel_count = len(re.findall(r'\bnovel\b', abstract, re.IGNORECASE))
        if novel_count >= 2:
            findings.append(Finding(category="Claims", 
                severity=Severity.HIGH,
                title=f"'Novel' used {novel_count} times in abstract",
                detail="The abstract should demonstrate novelty, not just claim it. Multiple uses of 'novel' in the abstract is a red flag for reviewers.",
                evidence=f"'novel' in abstract: {novel_count} times",
                confidence=0.85,
                action="Remove 'novel' from the abstract; let the contribution speak for itself",
                location="Abstract",
            ))

    # --- "We" not used (passive/impersonal overuse in methods) ---
    methods_match = re.search(r'(?:methods?|methodology)\s*(?:and|&)?\s*(?:materials?|experiments?)?', body, re.IGNORECASE)
    if methods_match:
        methods_section = body[methods_match.start():min(len(body), methods_match.start()+2000)]
        we_count = len(re.findall(r'\bwe\b', methods_section, re.IGNORECASE))
        passive_count = len(re.findall(r'\b(?:was|were|is|are)\s+(?:performed|conducted|used|applied|evaluated|implemented|developed|proposed)\b', methods_section, re.IGNORECASE))
        if passive_count > we_count + 3 and passive_count >= 5:
            findings.append(Finding(category="Claims", 
                severity=Severity.LOW,
                title="Heavy passive voice in Methods section",
                detail=f"Passive constructions ({passive_count}) far outnumber active 'we' ({we_count}) in Methods. Active voice is preferred for describing your own work.",
                evidence=f"Passive: {passive_count}, Active 'we': {we_count}",
                confidence=0.70,
                action="Use active voice: 'We performed X' instead of 'X was performed'",
                location="Methods",
            ))

    return findings
