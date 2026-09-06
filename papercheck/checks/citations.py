"""Citation/reference consistency engine.

Reviewers reject for weak or broken reference handling: references never
cited, citations with no entry, outdated literature, and mixed citation
styles. Reference *quality* (are the sources relevant/seminal?) needs expert
judgment; this engine verifies the machine-checkable mechanics.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Set

from ..ingestion import Document
from ..metrics import words
from ..risk import Finding, Severity
from . import CheckContext

_IEEE_MARKER = re.compile(r"\[(\d{1,3})\]")
# Non-capturing group: .findall() must return the full year, not just '19'/'20'.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_AUTHOR_YEAR = re.compile(r"\([A-Z][A-Za-z\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z\-]+)?,\s*(?:19|20)\d{2}\)")
_CURRENT_YEAR = datetime.now().year


def _body_refs(doc: Document) -> str:
    return doc.body_text


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 100:
        return findings
    cat = "Citations"
    body = _body_refs(doc)
    refs = doc.references
    n_refs = len(refs)
    wc = len(words(body))

    ieee_cited = _IEEE_MARKER.findall(body)
    author_year_cited = _AUTHOR_YEAR.findall(body)
    n_visible = len(ieee_cited) + len(author_year_cited)
    n_field = getattr(doc, "cite_field_count", 0) or 0

    # --- Unrendered citation fields (Word/Zotero placeholders) -----------------
    # The draft cites papers only as hidden field tokens (e.g. U+E200 'cite'
    # U+E202 'turn0academia38' U+E201). Nothing readable renders, so treat this
    # as broken citations rather than 'no citations' (a common DOCX export trap).
    if n_refs > 0 and n_visible == 0 and n_field > 0:
        findings.append(Finding(
            category=cat,
            severity=Severity.CRITICAL if n_field >= 5 else Severity.HIGH,
            title="Citations are unrendered field placeholders, not visible text",
            detail=(f"{n_field} citations exist only as hidden Word/reference-manager field tokens "
                    "(e.g. '\\ue200cite\\ue202...\\ue201'); nothing readable such as [1] or "
                    "(Author, 2024) appears in the rendered text. Reviewers and submission systems "
                    "see blank or garbled citations, and the reference list cannot be matched to claims."),
            evidence=f"citation field placeholders = {n_field}, rendered [n]/(Author, year) markers = 0",
            action="Update citation fields in Word (Ctrl+A then F9, or refresh Zotero/Mendeley), then re-export; "
                    "or convert to plain-text [n] markers ordered to match the reference list.",
            confidence=0.95,
            location="body text",
        ))

    # --- Never cited ------------------------------------------------------------
    if n_refs > 0 and not ieee_cited and not author_year_cited and n_field == 0:
        findings.append(Finding(
            category=cat, severity=Severity.HIGH,
            title="References never cited in the text",
            detail=f"{n_refs} reference entries exist but no in-text citations ([n] or (Author, year)) were found.",
            evidence=f"references = {n_refs}, in-text citation markers = 0",
            action="Cite each reference at the relevant claim; uncited entries are removed in production and look sloppy.",
            confidence=0.9,
            location="body text",
        ))
    elif n_refs > 0 and ieee_cited:
        # Numbers cited vs numbers in the list
        cited_nums: Set[int] = set()
        for m in ieee_cited:
            try:
                cited_nums.add(int(m))
            except ValueError:
                pass
        out_of_range = [n for n in cited_nums if n > n_refs]
        if out_of_range:
            findings.append(Finding(
                category=cat, severity=Severity.HIGH,
                title="Citations point to references that do not exist",
                detail="In-text citations beyond the reference list: " + ", ".join(f"[{n}]" for n in sorted(out_of_range)[:8]),
                evidence=f"reference list entries = {n_refs}, cited numbers out of range = {len(out_of_range)}",
                action="Fix the numbering; broken citation links are a known rejection and retraction trigger.",
                confidence=0.95,
            ))

    # --- Citation density -----------------------------------------------------------
    n_cites = n_visible + n_field
    all_placeholder = n_visible == 0 and n_field > 0  # density unknown until fields render
    if wc > 500 and n_cites == 0:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="No in-text citations at all",
            detail=f"{wc} words of body text with zero citations — the related-work position is missing.",
            evidence=f"body words = {wc}, citation markers = 0",
            action="Add a proper related-work section citing prior work at every claim you build on.",
            confidence=0.85,
        ))
    elif wc > 800 and not all_placeholder and n_cites / (wc / 1000.0) < 5:
        findings.append(Finding(
            category=cat, severity=Severity.LOW,
            title="Sparse citation density",
            detail=f"~{n_cites / (wc / 1000.0):.1f} citations per 1,000 words — related work may be under-covered.",
            evidence=f"citations = {n_cites}, body words = {wc}",
            action="Expand related work; thin citation coverage reads as weak literature grounding.",
            confidence=0.6,
        ))

    # --- Mixed citation styles ---------------------------------------------------------
    if ieee_cited and author_year_cited:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Mixed citation styles",
            detail="Both numeric [n] and author-year (Author, year) styles appear in the text.",
            evidence=f"[n] markers = {len(ieee_cited)}, (Author, year) markers = {len(author_year_cited)}",
            action="Convert everything to the venue's required style (e.g. IEEE numeric or APA author-year).",
            confidence=0.85,
        ))

    # --- Outdated references -------------------------------------------------------------
    if n_refs >= 5:
        # Per entry, take the *last* 19xx/20xx year: IEEE lists the publication
        # year near the end (after venue/volume/pages). This avoids false years
        # such as arXiv IDs ('arXiv:2006.07391' → 2006) or dataset years in titles.
        years = []
        for ref in refs:
            hits = [int(y) for y in _YEAR.findall(ref)]
            if hits:
                years.append(hits[-1])
        if years:
            years.sort()
            median = years[len(years) // 2]
            recent = sum(1 for y in years if y >= _CURRENT_YEAR - 3)
            if median < _CURRENT_YEAR - 8:
                findings.append(Finding(
                    category=cat, severity=Severity.MEDIUM,
                    title="Reference list looks outdated",
                    detail=f"Median reference year is {median} (current year {_CURRENT_YEAR}); only {recent}/{len(years)} references are from the last 3 years.",
                    evidence="years parsed from reference entries",
                    action="Add recent (last 2-3 years) references; reviewers check whether you know the current state of the art.",
                    confidence=0.7,
                ))
    return findings