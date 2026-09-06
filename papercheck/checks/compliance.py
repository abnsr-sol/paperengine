"""Compliance engine: venue rules, page/word limits, sections, figures, refs.

Hard counts have ~100% confidence. Anything derived from the rough page
estimate (500 words/page) is flagged as an estimate. Every rule is read from
the venue rules dict, so adding a venue = adding a dict.
"""

from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..metrics import word_count
from ..risk import Finding, Severity
from . import CheckContext


def _find_section(doc: Document, name: str) -> bool:
    """True if any heading normalizes to (or starts with) the required name.
    Handles '1. Introduction', '6. Conclusion and Future Work', etc."""
    target = name.strip().lower()
    for s in doc.sections:
        norm = _normalize(s.heading)
        if norm == target or norm.startswith(target):
            return True
    return False


def _normalize(heading: str) -> str:
    from ..ingestion import normalize_heading

    return normalize_heading(heading)


def _abstract_text(doc: Document) -> str:
    for s in doc.sections:
        if re.match(r"^abstract\b", s.heading, re.IGNORECASE):
            return s.body
    # Fallback: text between the title/start and the Introduction heading.
    for s in doc.sections:
        if re.match(r"^introduction\b", s.heading, re.IGNORECASE):
            return doc.text[: s.start_index].strip()
    return ""


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    rules = ctx.rules
    findings: List[Finding] = []
    cat = "Compliance"

    # --- Word limit ---------------------------------------------------------
    limit = rules.get("word_limit")
    wc = doc.word_count
    if limit:
        if wc > limit:
            findings.append(Finding(
                category=cat,
                severity=Severity.CRITICAL,
                title="Over venue word limit",
                detail=f"Manuscript has {wc:,} words; venue limit is {limit:,}.",
                evidence=f"word count = {wc:,}, venue word_limit = {limit:,}",
                action=f"Trim to ≤ {limit:,} words. Many venues desk-reject over-length submissions without review.",
                confidence=1.0,
                location="whole document",
            ))

    # --- Page limit ----------------------------------------------------------
    plimit = rules.get("page_limit")
    if plimit:
        est = doc.page_estimate
        if est > plimit:
            findings.append(Finding(
                category=cat,
                severity=Severity.CRITICAL if est > plimit * 1.1 else Severity.HIGH,
                title="Page limit likely exceeded",
                detail=f"Estimated {est:.0f} pages (~{wc:,} words); venue allows {plimit} pages.",
                evidence=f"estimate = words/500 = {est:.1f}; this is an estimate — check the typeset PDF",
                action="Format to the venue template and confirm page count; trim figures/tables/text as needed.",
                confidence=0.85,
                location="whole document",
            ))

    # --- Abstract length ------------------------------------------------------
    alimit = rules.get("abstract_word_limit")
    abstract = _abstract_text(doc)
    if alimit and abstract:
        awc = word_count(abstract)
        if awc > alimit:
            findings.append(Finding(
                category=cat,
                severity=Severity.HIGH,
                title="Abstract over limit",
                detail=f"Abstract is {awc} words; venue allows {alimit}.",
                evidence=f"abstract_word_count = {awc}, venue abstract_word_limit = {alimit}",
                action=f"Condense the abstract to ≤ {alimit} words.",
                confidence=0.95,
                location="Abstract",
            ))
    elif alimit and not abstract:
        findings.append(Finding(
            category=cat,
            severity=Severity.HIGH,
            title="Abstract not detected",
            detail="No 'Abstract' heading/section found.",
            evidence="sections found: " + (", ".join(s.heading for s in doc.sections[:8]) or "none"),
            action="Add a structured abstract matching the venue's required style.",
            confidence=0.9,
            location="top of document",
        ))

    # --- Required sections ----------------------------------------------------
    missing = [s for s in rules.get("required_sections", []) if not _find_section(doc, s)]
    if missing:
        findings.append(Finding(
            category=cat,
            severity=Severity.HIGH,
            title="Missing required section(s)",
            detail="Required sections not found: " + ", ".join(missing),
            evidence="venue required_sections = " + ", ".join(rules.get("required_sections", [])),
            action="Add the missing sections in the venue's standard order.",
            confidence=0.9,
            location=", ".join(missing),
        ))

    # --- Figures / tables ------------------------------------------------------
    mfig = rules.get("max_figures")
    if mfig and doc.figures > mfig:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Too many figures",
            detail=f"{doc.figures} figures found; venue allows {mfig}.",
            evidence=f"figures = {doc.figures}, venue max_figures = {mfig}",
            action="Move extra figures to supplementary material or merge panels.",
            confidence=0.9,
        ))
    mtbl = rules.get("max_tables")
    if mtbl and doc.tables > mtbl:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Too many tables",
            detail=f"{doc.tables} tables found; venue allows {mtbl}.",
            evidence=f"tables = {doc.tables}, venue max_tables = {mtbl}",
            action="Move extra tables to supplementary material.",
            confidence=0.9,
        ))

    # --- References ------------------------------------------------------------
    nrefs = len(doc.references)
    minrefs = rules.get("min_references")
    if minrefs and nrefs < minrefs:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Too few references",
            detail=f"{nrefs} references detected; venue expects at least {minrefs}.",
            evidence=f"references detected = {nrefs}, venue min_references = {minrefs}",
            action="Expand the related-work coverage; missing seminal or recent work is a common rejection reason.",
            confidence=0.8,
            location="References",
        ))
    maxrefs = rules.get("max_references")
    if maxrefs and nrefs > maxrefs:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Too many references",
            detail=f"{nrefs} references detected; venue allows {maxrefs}.",
            evidence=f"references = {nrefs}, venue max_references = {maxrefs}",
            action="Trim to the venue's reference limit.",
            confidence=0.8,
            location="References",
        ))
    if nrefs == 0 and "References" in doc.text:
        findings.append(Finding(
            category=cat,
            severity=Severity.HIGH,
            title="References unparseable",
            detail="A references section exists but no entries could be parsed.",
            evidence="references section found, 0 entries parsed",
            action="Format references with a standard style ([1] ..., numbered) so they can be validated.",
            confidence=0.7,
            location="References",
        ))

    # --- Font compliance (DOCX only) ----------------------------------------------
    font_required = rules.get("font_required")
    size_required = rules.get("font_size_required")
    if (font_required or size_required) and doc.file_type == "docx":
        if not doc.font_warnings:
            findings.append(Finding(
                category=cat,
                severity=Severity.INFO,
                title="Font check passed (single font family)",
                detail="No mixed-font signals detected in the DOCX run properties.",
                evidence="one dominant font in w:rPr",
                action="Still verify against the venue template (embedded fonts can hide).",
                confidence=0.6,
            ))
        else:
            for warn in doc.font_warnings:
                findings.append(Finding(
                    category=cat,
                    severity=Severity.MEDIUM,
                    title="Mixed fonts detected",
                    detail=warn,
                    evidence="DOCX run-level font analysis",
                    action="Normalize all text to the venue's required font/size.",
                    confidence=0.8,
                ))
    return findings