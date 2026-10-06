"""Venue hijack & predatory journal detection engine.

Uses bundled venue_intel.json for:
- Known hijacked journal list (Retraction Watch entries)
- Legitimate publisher ISSN prefix mapping
- Weighted predatory indicator scoring

Based on: Retraction Watch Hijacked Journal Checker, Think.Check.Submit,
Cabell's Predatory Reports (offline subset).
"""
from __future__ import annotations
import json
import os
import re
from typing import Dict, List, Optional, Tuple
from ..ingestion import Document
from ..risk import Finding, Severity

# Load bundled venue intelligence
_INTEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "venue_intel.json")
_INTEL: Optional[Dict] = None


def _load_intel() -> Dict:
    global _INTEL
    if _INTEL is None:
        try:
            with open(_INTEL_PATH, "r", encoding="utf-8") as f:
                _INTEL = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _INTEL = {"hijacked_journals": [], "legitimate_publishers": {}, "predatory_indicators": []}
    return _INTEL


def _normalize_title(title: str) -> str:
    """Normalize journal title for matching: lowercase, strip non-alphanumerics."""
    return re.sub(r"[^a-z0-9\s]", "", title.lower().strip())


# venues.describe() renders a label as "NAME (Standard -- Publisher)".
_VENUE_LABEL_SUFFIX = re.compile(r"\s*\(.*--.*\)\s*$")
# A captured venue name must stop at the first sentence boundary.
_SENTENCE_TAIL = re.compile(r"\.\s+")


def _clean_venue_label(raw: str) -> str:
    """Reduce a described venue label back to the bare journal name.

    ctx.venue carries a human-readable label, e.g.
    "elsevier (International -- Elsevier)". Matching that label against a
    journal-title list can never succeed — and its injected words
    ("international") also tripped the generic-title predatory indicator, so
    legitimate presets were reported as predatory. Always match the bare name.
    """
    return _VENUE_LABEL_SUFFIX.sub("", (raw or "").strip()).strip()


def _trim_sentence_tail(candidate: str) -> str:
    """Cut a captured venue name at the first sentence boundary.

    The extraction patterns capture greedily, so
    "submitted to Journal of X. We used 42 epochs." yielded
    "Journal of X. We used 42 epochs" — which never equals a real title.
    """
    return _SENTENCE_TAIL.split(candidate, 1)[0].strip(" \t\n.,;:")


def _extract_issn(text: str) -> Optional[str]:
    """Extract ISSN-8 pattern from text."""
    m = re.search(r"\b(\d{4}-\d{3}[\dxX])\b", text)
    return m.group(1).upper() if m else None


def _extract_venue_name(doc: Document, body: str) -> Optional[str]:
    """Extract target journal name from document."""
    # Priority 1: metadata
    meta = doc.metadata or {}
    for key in ("journal", "publication", "title"):
        if meta.get(key):
            return str(meta[key]).strip()

    # Priority 2: explicit intent lines in text
    for pat in [
        r"submitted\s+to\s+([A-Z][\w&.,'\- ]{3,60})",
        r"target\s+journal\s*[:\-]\s*([A-Z][\w&.,'\- ]{3,60})",
        r"under\s+review\s+at\s+([A-Z][\w&.,'\- ]{3,60})",
        r"published\s+in\s+([A-Z][\w&.,'\- ]{3,60})",
        r"journal\s+of\s+([\w&.,'\- ]{3,60})",
    ]:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            return _trim_sentence_tail(m.group(1))

    return None


def _resolve_venue_name(ctx: object, doc: Document, body: str) -> Optional[str]:
    """Resolve the *bare* target-venue name, never the display label.

    get_rules() stores the raw name the user typed under rules["_name"], which
    is the only faithful source when the venue is a preset key. ctx.venue is a
    rendered label and is used only as a cleaned fallback.
    """
    rules = getattr(ctx, "rules", None) or {}
    raw = rules.get("_name")
    if raw and str(raw).strip().lower() not in ("", "generic"):
        return _clean_venue_label(str(raw))
    ctx_venue = getattr(ctx, "venue", None)
    if ctx_venue and str(ctx_venue).strip().lower() != "generic":
        cleaned = _clean_venue_label(str(ctx_venue))
        if cleaned:
            return cleaned
    return _extract_venue_name(doc, body)


def _check_hijacked(title_norm: str, issn: Optional[str], hijacked_list: List[Dict]) -> Optional[Dict]:
    """Check title/ISSN against known hijacked journals.
    
    Uses exact match after normalization (not substring/superset) to avoid
    false positives on legitimate journals that merely contain a hijack phrase.
    ISSN match remains exact.
    """
    for entry in hijacked_list:
        entry_title = entry.get("title_norm", "")
        # Exact match only (both directions would be redundant since normalized)
        if title_norm and entry_title and title_norm == entry_title:
            return entry
        if issn:
            # Refreshed entries carry every ISSN the checker lists; the seed
            # entries carry a single "issn".
            candidates = entry.get("issns") or (
                [entry["issn"]] if entry.get("issn") else [])
            if issn in candidates:
                return entry
    return None


def _check_publisher_issn(issn: str, publishers: Dict) -> Optional[str]:
    """Check if ISSN prefix belongs to a known legitimate publisher."""
    prefix = issn[:4]
    for publisher, info in publishers.items():
        if prefix in info.get("issn_prefixes", []):
            return publisher
    return None


def _matches_known_publisher(venue_name: str, publishers: Dict) -> bool:
    """True if the venue name IS a known legitimate publisher (e.g. 'Frontiers').

    Several real publishers have names built from common words that the
    generic-title heuristic treats as invented-journal tells. Without this
    guard, a preset like `frontiers` was reported as predatory on a clean paper.
    """
    norm = _normalize_title(venue_name)
    if not norm:
        return False
    return any(_normalize_title(pub) == norm for pub in publishers)


def _count_predatory_indicators(text: str, venue_name: Optional[str], publishers: Dict, indicators: List[Dict]) -> List[Dict]:
    """Count predatory indicators and return matched ones."""
    low = text.lower()
    matched = []

    for ind in indicators:
        iid = ind["id"]
        if iid == "free_email":
            if re.search(r"@(gmail|outlook|yahoo|163|qq|hotmail|protonmail|aol)\b", low):
                matched.append(ind)
        elif iid == "generic_title" and venue_name:
            if _matches_known_publisher(venue_name, publishers):
                continue
            generic_words = {"international", "journal", "advanced", "modern", "innovative",
                           "world", "global", "universal", "excel", "premier", "supreme",
                           "excellence", "frontier", "frontiers", "discovery", "insight",
                           "scientific", "current", "new", "american", "european", "asian",
                           "african", "research", "science", "engineering", "technology"}
            words = _normalize_title(venue_name).split()
            if words:
                generic_count = sum(1 for w in words if w in generic_words)
                if generic_count / len(words) > 0.3:
                    matched.append(ind)
        elif iid == "fast_track":
            if re.search(r"accepted\s+(?:within|in)\s+\d+\s+(?:hours|days)|guaranteed\s+(?:publication|acceptance)|quick\s+peer\s+review", low):
                matched.append(ind)
        elif iid == "spam_solicitation":
            if re.search(r"submit\s+(?:now|today)\s+and\s+(?:get|receive)|article\s+processing\s+charge|APC\s+(?:waived|free|discount)", low):
                matched.append(ind)

    return matched


def _run(doc: Document, ctx: object) -> List[Finding]:
    """Internal engine logic."""
    findings = []
    body = doc.body_text or doc.text or ""
    if not body:
        return findings

    intel = _load_intel()
    hijacked_list = intel.get("hijacked_journals", [])
    publishers = intel.get("legitimate_publishers", {})
    indicators = intel.get("predatory_indicators", [])

    # Extract venue signals — the BARE name, never the rendered label
    venue_name = _resolve_venue_name(ctx, doc, body)
    issn = _extract_issn(body)

    title_norm = _normalize_title(venue_name) if venue_name else ""

    # Step 0: No venue signal
    if not venue_name and not issn:
        findings.append(Finding(
            category="Venue Integrity", severity=Severity.INFO,
            title="No target venue detected — venue vetting skipped",
            detail="Could not detect a target journal name or ISSN in the manuscript. "
                   "Venue integrity checks require a target venue.",
            evidence="No venue signal found in text or metadata",
            confidence=0.95,
            action="Specify the target journal via --venue flag or include it in the manuscript"))
        return findings

    # Step 1: Check hijacked list
    hijack_match = _check_hijacked(title_norm, issn, hijacked_list)
    if hijack_match:
        clone_of = hijack_match.get("clone_of", "unknown legitimate journal")
        source = hijack_match.get("source", "Retraction Watch")
        findings.append(Finding(
            category="Venue Integrity", severity=Severity.CRITICAL,
            title="Venue matches a known hijacked/clone journal",
            detail=f"The journal '{venue_name}' matches a known hijacked journal entry. "
                   f"This title clones '{clone_of}'. Hijacked journals charge APCs but provide "
                   "no legitimate peer review or indexing.",
            evidence=f"Matched hijacked entry: {clone_of} (source: {source})",
            confidence=0.95,
            action="Do NOT submit. Verify via Think.Check.Submit (thinkchecksubmit.org) and "
                   "the Retraction Watch Hijacked Journal Checker. This title clones "
                   f"{clone_of}."))
        return findings  # Don't check further — this is definitive

    # Step 2: ISSN/publisher mismatch
    if issn:
        found_publisher = _check_publisher_issn(issn, publishers)
        if found_publisher:
            # ISSN belongs to a known publisher — that's good
            pass
        else:
            # ISSN not recognized — could be new or suspicious
            # Only flag if we have other indicators too
            pass

    # Step 3: Predatory indicators
    matched_indicators = _count_predatory_indicators(body, venue_name, publishers, indicators)
    weight_sum = sum(ind.get("weight", 1) for ind in matched_indicators)

    if weight_sum >= 3:
        indicator_names = [ind["id"] for ind in matched_indicators]
        findings.append(Finding(
            category="Venue Integrity", severity=Severity.HIGH,
            title="Multiple predatory-publishing indicators detected",
            detail=f"Weighted indicator score: {weight_sum} (threshold: 3). "
                   f"Indicators found: {', '.join(indicator_names)}. "
                   "These patterns are associated with predatory publishing practices.",
            evidence=f"Indicators: {', '.join(indicator_names)}; venue: '{venue_name}'",
            confidence=0.75,
            action="Verify the journal against Think.Check.Submit checklist and "
                   "check DOAJ for legitimate indexing"))
    elif weight_sum >= 1:
        indicator_names = [ind["id"] for ind in matched_indicators]
        findings.append(Finding(
            category="Venue Integrity", severity=Severity.MEDIUM,
            title="Some predatory-publishing indicators detected",
            detail=f"Weighted indicator score: {weight_sum}. "
                   f"Indicators found: {', '.join(indicator_names)}. "
                   "This may indicate a predatory publisher, but verification is recommended.",
            evidence=f"Indicators: {', '.join(indicator_names)}; venue: '{venue_name}'",
            confidence=0.65,
            action="Check Think.Check.Submit and verify the journal's indexing status"))

    # Step 4: Venue not in legitimate publisher list (online would check Crossref/DOAJ)
    if venue_name and not matched_indicators and not hijack_match:
        # Check if venue matches any known publisher's domain patterns
        in_known = False
        for pub, info in publishers.items():
            if any(word in venue_name.lower() for word in pub.lower().split()):
                in_known = True
                break
        # Only flag if we have strong evidence — don't accuse without data
        if not in_known and len(title_norm.split()) > 3:
            # Long generic title not matching any known publisher — low-confidence flag
            findings.append(Finding(
                category="Venue Integrity", severity=Severity.LOW,
                title="Venue not found in bundled publisher index",
                detail=f"'{venue_name}' does not match any bundled legitimate publisher. "
                       "This may be a new legitimate journal not yet indexed, or it may "
                       "require verification.",
                evidence=f"Venue: '{venue_name}'; not in bundled publisher list",
                confidence=0.50,
                action="Verify the journal at DOAJ (doaj.org) and Crossref (crossref.org) "
                       "when online. Re-run with --online for live verification."))

    return findings


def run(doc: Document, ctx: object) -> List[Finding]:
    return _run(doc, ctx)
