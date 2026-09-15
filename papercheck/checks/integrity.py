"""Integrity engine: overlap/duplication and reference validity.

Guiding principle from the research: similarity is NOT plagiarism. Crossref
Similarity Check reports overlap for human editorial interpretation, and
editors are warned against automatic rejection thresholds. This engine reports
overlap as a risk with the matching passages as evidence — and never uses a
single magic threshold without showing what matched.

Online checks (Crossref) are opt-in via `--online`.
"""

from __future__ import annotations

import difflib
import re
import urllib.parse
from typing import Dict, List, Tuple

from ..ingestion import Document
from ..metrics import words
from ..risk import Finding, Severity
from . import CheckContext


# --------------------------------------------------------------------------
# n-gram helpers
# --------------------------------------------------------------------------

def _ngrams(tokens: List[str], n: int):
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _distinctive_ngrams(text: str, n: int = 8) -> List[Tuple[str, ...]]:
    toks = [w.lower() for w in words(text)]
    seen = set()
    out = []
    for g in _ngrams(toks, n):
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


def _overlap_fraction(a_text: str, b_text: str, n: int = 8) -> Tuple[float, str]:
    """Fraction of A's distinctive n-grams that appear in B, with a sample match."""
    a_grams = _distinctive_ngrams(a_text, n)
    if not a_grams:
        return 0.0, ""
    b_set = set(_ngrams([w.lower() for w in words(b_text)], n))
    hits = [g for g in a_grams if g in b_set]
    if not hits:
        return 0.0, ""
    sample = " ".join(hits[0])
    return len(hits) / len(a_grams), sample


# --------------------------------------------------------------------------
# Self-overlap
# --------------------------------------------------------------------------

def _self_duplication(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    paras = [p for p in doc.paragraphs if len(words(p)) >= 30]
    seen: Dict[str, int] = {}
    dupes: List[str] = []
    for p in paras:
        key = " ".join(w.lower() for w in words(p))
        if key in seen:
            dupes.append(p[:110] + "...")
        else:
            seen[key] = 1
    if dupes:
        findings.append(Finding(
            category="Integrity",
            severity=Severity.HIGH,
            title="Identical paragraphs duplicated within the document",
            detail=f"{len(dupes)} paragraph(s) appear verbatim more than once.",
            evidence="verbatim paragraph match: " + (dupes[0] if dupes else ""),
            action="Remove or rewrite the duplicated passage; accidental copy-paste is a common submission error.",
            confidence=0.95,
        ))
    return findings


# --------------------------------------------------------------------------
# Corpus overlap ("already published" check)
# --------------------------------------------------------------------------

def _corpus_overlap(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if not ctx.corpus:
        return findings
    for other in ctx.corpus:
        frac, sample = _overlap_fraction(doc.text, other.text, n=8)
        if frac >= 0.45:
            findings.append(Finding(
                category="Integrity",
                severity=Severity.CRITICAL,
                title="High overlap with an existing document",
                detail=f"{frac*100:.0f}% of the manuscript's distinctive 8-grams appear in '{other.name}'.",
                evidence="sample overlap: '" + sample + "'",
                action="Determine whether this is duplicate publication, self-plagiarism, or reuse of shared methods text; rewrite and disclose as required.",
                confidence=0.9,
            ))
        elif frac >= 0.25:
            findings.append(Finding(
                category="Integrity",
                severity=Severity.MEDIUM,
                title="Substantial overlap with an existing document",
                detail=f"{frac*100:.0f}% of distinctive 8-grams appear in '{other.name}'.",
                evidence="sample overlap: '" + sample + "'",
                action="Rewrite overlapping passages; similarity ≠ plagiarism, but high overlap triggers editorial scrutiny.",
                confidence=0.8,
            ))
    return findings


# --------------------------------------------------------------------------
# Crossref duplicate-publication / prior-art lookups (opt-in)
# --------------------------------------------------------------------------

def _title_lookup(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if not ctx.online:
        return findings
    title = _extract_title(doc)
    if not title or len(words(title)) < 3:
        return findings
    cached = ctx.online_cache.get("title_lookup")
    import json
    import urllib.request

    query = urllib.parse.quote(title)
    url = (
        "https://api.crossref.org/works?query.title=" + query
        + "&rows=5&select=title,published,DOI,container-title"
        + ("&mailto=" + urllib.parse.quote(ctx.mailto) if ctx.mailto else "")
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PaperCheck/0.1 (manuscript pre-submission check)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("message", {}).get("items", [])
    except Exception as exc:  # network down, rate limit, etc.
        findings.append(Finding(
            category="Integrity",
            severity=Severity.INFO,
            title="Crossref duplicate-check skipped",
            detail=f"Could not query Crossref: {exc}",
            evidence="online lookup failed",
            action="Re-run with network access or check manually via Google Scholar/Scopus.",
            confidence=1.0,
        ))
        return findings

    best = None
    best_ratio = 0.0
    for item in items:
        titles = item.get("title") or []
        if not titles:
            continue
        ratio = difflib.SequenceMatcher(None, title.lower(), titles[0].lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = item
    if best is not None and best_ratio >= 0.92:
        findings.append(Finding(
            category="Integrity",
            severity=Severity.CRITICAL,
            title="Very close existing publication found",
            detail=f"Crossref returns '{best['title'][0]}' ({best_ratio*100:.0f}% title match).",
            evidence="DOI: " + str(best.get("DOI", "?")) + "; published: " + str(best.get("published", {}).get("date-parts"))
            if best.get("DOI") else "title match only",
            action="Check for duplicate publication. If this is your own prior work, disclose and ensure substantial new content per venue policy.",
            confidence=0.85,
        ))
    elif best is not None and best_ratio >= 0.75:
        findings.append(Finding(
            category="Novelty",
            severity=Severity.MEDIUM,
            title="Similar prior work found (novelty risk)",
            detail=f"Crossref returns '{best['title'][0]}' ({best_ratio*100:.0f}% title match).",
            evidence="DOI: " + str(best.get("DOI", "?")) if best.get("DOI") else "title match only",
            action="Cite this work, position your contribution against it explicitly, and strengthen the novelty argument.",
            confidence=0.7,
        ))
    return findings


def _extract_title(doc: Document) -> str:
    if doc.paragraphs:
        first = doc.paragraphs[0].strip()
        if len(words(first)) <= 25:
            return first
    return ""


# --------------------------------------------------------------------------
# Reference sanity / validity
# --------------------------------------------------------------------------

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")


def _reference_checks(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    refs = doc.references
    if not refs:
        return findings

    # NOTE: "references lack DOI/URL" coverage is owned by `reference_verify`
    # (it was triple-fired across integrity/citation_integrity/reference_verify,
    # confirmed on a live sample run).

    if ctx.online and ctx.max_online_checks > 0 and refs:
        findings.extend(_verify_dois_online(refs[: ctx.max_online_checks], ctx))
    return findings


def _verify_dois_online(refs: List[str], ctx: CheckContext) -> List[Finding]:
    """Resolve DOIs against doi.org for the first N references."""
    import json
    import urllib.request

    findings: List[Finding] = []
    ok = 0
    failed: List[str] = []
    for ref in refs:
        m = _DOI_RE.search(ref)
        if not m:
            continue
        doi = m.group(0).rstrip(".,;)")
        try:
            url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/")
            req = urllib.request.Request(url, headers={"User-Agent": "PaperCheck/0.1 (manuscript check)"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("message", {}).get("DOI"):
                ok += 1
        except Exception:
            failed.append(doi)
        if ok + len(failed) >= ctx.max_online_checks:
            break
    if failed:
        findings.append(Finding(
            category="Integrity",
            severity=Severity.HIGH,
            title="References with unresolvable DOIs",
            detail=f"{len(failed)} DOI(s) did not resolve on Crossref: " + ", ".join(failed[:5]),
            evidence="doi.org/Crossref resolution failed for " + str(len(failed)) + " of " + str(len(refs)) + " references",
            action="Manually verify each DOI; unresolvable DOIs often mean fabricated/hallucinated references.",
            confidence=0.9,
        ))
    return findings


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    findings.extend(_self_duplication(doc))
    findings.extend(_corpus_overlap(doc, ctx))
    findings.extend(_title_lookup(doc, ctx))
    findings.extend(_reference_checks(doc, ctx))
    return findings