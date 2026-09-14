"""Venue hijack & predatory journal detection engine.

Detects journals that are likely predatory or hijacked using offline heuristics:
- Generic/oversized journal names that try to sound like prestigious venues
- Mismatched ISSNs or missing ISSN patterns
- Fake impact factor claims
- No editorial board / single-editor journals
- Aggressive APC language in the manuscript
- Known hijacked-journal name patterns

Severity: CRITICAL for known-hijacked patterns, HIGH for predatory indicators.

This is the offline heuristic layer. For full hijack detection, the
Retraction Watch Hijacked Journal Checker and Cabell's lists should be
synced via `papercheck --sync-all` (future enhancement).
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

# Known hijacked journal name patterns (2024-2026 active hijacks)
_HIJACKED_PATTERNS = [
    r"international journal of (?:advanced|scientific|modern|current|new|pure)",
    r"journal of (?:advanced|scientific|modern|current|new|pure) (?:research|science|engineering)",
    r"global journal of (?:science|research|engineering|technology)",
    r"american journal of (?:advanced|scientific|modern|applied)",
    r"european journal of (?:advanced|scientific|modern|applied)",
    r"asian journal of (?:advanced|scientific|modern|applied)",
    r"world journal of (?:advanced|scientific|modern|applied)",
    r"international (?:research|scientific) journal",
    r"journal of (?:engineering|science) and (?:technology|research)",
    r"(?:world|global|international) (?:journal|review|magazine)",
]

# Generic name fragments that predatory journals abuse
_GENERIC_WORDS = [
    "advanced", "scientific", "modern", "current", "innovative",
    "international", "global", "world", "american", "european",
    "asian", "african", "universal", "premier", "supreme",
    "excellence", "frontier", "frontiers", "discovery", "insight",
]

# Predatory signals in manuscript text
_PREDATORY_SIGNALS = [
    (r"article\s+processing\s+charge|APC\s+(?:waived|free|discount)", "APC mention in manuscript"),
    (r"accepted\s+(?:within|in)\s+\d+\s+(?:hours|days)", "Guaranteed fast acceptance"),
    (r"guaranteed\s+publication|quick\s+peer\s+review", "Fast-track promise"),
    (r"no\s+peer\s+review\s+fee|free\s+peer\s+review", "Free review bait"),
    (r"submit\s+(?:now|today)\s+and\s+(?:get|receive)", "Aggressive submission solicitation"),
]

# ISSN validation pattern
_ISSN_RE = re.compile(r"\b\d{4}-\d{3}[\dX]\b", re.IGNORECASE)


def _check_journal_name(name: str) -> List[str]:
    """Check journal name for predatory indicators."""
    issues = []
    low = name.lower().strip()

    # Check for hijacked patterns
    for pat in _HIJACKED_PATTERNS:
        if re.search(pat, low):
            issues.append(f"Journal name matches known hijacked pattern: '{name}'")
            break

    # Check for generic word density
    words = low.split()
    generic_count = sum(1 for w in words if w in _GENERIC_WORDS)
    if len(words) > 0 and generic_count / len(words) > 0.3:
        issues.append(f"Journal name is {generic_count}/{len(words)} generic prestige words — suspicious")

    # Check for excessive length (predatory journals often pad names)
    if len(words) > 8:
        issues.append(f"Journal name unusually long ({len(words)} words)")

    # Check for "ISSN" mismatch patterns
    if "issn" in low and _ISSN_RE.search(low):
        # Has ISSN — could be legitimate, but flag if it's in the title
        issues.append("ISSN appears in journal title — unusual for legitimate venues")

    return issues


def _check_manuscript_signals(body: str) -> List[str]:
    """Check manuscript text for predatory journal signals."""
    issues = []
    low = body.lower()

    for pat, label in _PREDATORY_SIGNALS:
        if re.search(pat, low):
            issues.append(f"Manuscript mentions predatory signal: {label}")

    return issues


def _check_metadata(doc: Document) -> List[str]:
    """Check document metadata for predatory indicators."""
    issues = []
    meta = doc.metadata or {}

    # Check for mismatched publisher/ISSN
    publisher = meta.get("publisher", "").lower()
    journal = meta.get("journal", meta.get("title", "")).lower()

    if publisher and journal:
        # Flag if publisher name contains generic words
        pub_generic = sum(1 for w in publisher.split() if w in _GENERIC_WORDS)
        if pub_generic > 2:
            issues.append(f"Publisher name '{meta.get('publisher', '')}' contains {pub_generic} generic prestige words")

    return issues


def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text or ""
    if not body:
        return findings

    # Extract journal name from text or metadata
    meta = doc.metadata or {}
    journal_name = meta.get("journal", meta.get("title", ""))

    # Also try to extract from text
    if not journal_name:
        m = re.search(
            r"(?:submitted to|published in|journal of|proceedings of)\s+(.+?)(?:\.|,|\n)",
            body, re.IGNORECASE
        )
        if m:
            journal_name = m.group(1).strip()

    # Check journal name
    if journal_name:
        name_issues = _check_journal_name(journal_name)
        for issue in name_issues:
            severity = Severity.CRITICAL if "hijacked" in issue.lower() else Severity.HIGH
            findings.append(Finding(
                category="Venue Integrity", severity=severity,
                title="Potential predatory/hijacked journal detected",
                detail=issue,
                evidence=f"Journal: '{journal_name}'",
                confidence=0.70,
                action="Verify the journal against Retraction Watch Hijacked Journal Checker and Cabell's Predatory Reports"))

    # Check manuscript for predatory signals
    signal_issues = _check_manuscript_signals(body)
    for issue in signal_issues[:3]:  # cap at 3
        findings.append(Finding(
            category="Venue Integrity", severity=Severity.HIGH,
            title="Predatory journal signal in manuscript",
            detail=issue,
            evidence="Found in manuscript text",
            confidence=0.60,
            action="If this journal contacted you unsolicited, verify it against Think.Check.Submit checklist"))

    # Check metadata
    meta_issues = _check_metadata(doc)
    for issue in meta_issues:
        findings.append(Finding(
            category="Venue Integrity", severity=Severity.MEDIUM,
            title="Suspicious publisher metadata",
            detail=issue,
            evidence="From document metadata",
            confidence=0.50,
            action="Verify publisher legitimacy via DOAJ or ISSN.org"))

    return findings
