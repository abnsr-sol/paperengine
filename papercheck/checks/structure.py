"""Structure / completeness engine.

Desk rejections are dominated by *preventable* problems: out of scope, weak
novelty, and failure to follow author guidelines (Wu 2024 — 55% of desk
rejections were scope-related; Menon 2020 content analysis — novelty and scope
lead desk-rejection reasons). Most journals now *require* formal statements
(data availability, funding, conflicts of interest, author contributions);
missing statements are an instant compliance failure.

Scope matching itself needs human judgment, so this engine checks everything
else that is machine-verifiable: title, author block, abstract content,
keywords, and required statements.
"""

from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..metrics import words
from ..risk import Finding, Severity
from . import CheckContext

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_GENERIC_TITLE = [
    "a study of", "a study on", "an investigation of", "an analysis of",
    "analysis of", "on the", "towards", "toward", "a review of", "study of",
    "some notes on",
]
_STRONG_ABSTRACT_WORDS = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:%|percent)|p\s*[<>=]\s*0?\.\d+|accuracy|precision|recall|f1|improvement|outperform)", re.IGNORECASE)


def _title(doc: Document) -> str:
    if not doc.paragraphs:
        return ""
    return doc.paragraphs[0].strip().splitlines()[0].strip()


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    cat = "Structure"
    full = doc.text
    rules = ctx.rules
    # Sub-manuscript fragments (empty uploads, previews, garbage) get no
    # structural verdicts — "no title" on a 2-word file is noise, not signal.
    if doc.word_count < 100:
        return findings

    # --- Title -------------------------------------------------------------------
    title = _title(doc)
    tw = len(words(title))
    if tw == 0:
        findings.append(Finding(
            category=cat, severity=Severity.CRITICAL,
            title="No title detected",
            detail="The first paragraph does not look like a title.",
            evidence="first paragraph: '" + (doc.paragraphs[0][:60] if doc.paragraphs else "none") + "'",
            action="Add a clear, informative title at the top of the manuscript.",
            confidence=0.85,
        ))
    else:
        if tw < 5:
            findings.append(Finding(
                category=cat, severity=Severity.LOW,
                title="Title is very short",
                detail=f"Title has only {tw} words; too vague to signal the contribution.",
                evidence="title word count = " + str(tw),
                action="Expand the title to state the topic, method, and contribution.",
                confidence=0.7,
            ))
        elif tw > 25:
            findings.append(Finding(
                category=cat, severity=Severity.LOW,
                title="Title is very long",
                detail=f"Title has {tw} words — many venues cap titles at ~20 words.",
                evidence="title word count = " + str(tw),
                action="Shorten the title to its essence.",
                confidence=0.7,
            ))
        low = title.lower()
        generic = [g for g in _GENERIC_TITLE if low.startswith(g) or (" " + g) in low]
        if generic:
            findings.append(Finding(
                category=cat, severity=Severity.LOW,
                title="Generic title opener",
                detail="Title starts with a weak opener: " + generic[0],
                evidence="title = '" + title[:80] + "'",
                action="Start the title with the actual contribution, not 'A study of...'.",
                confidence=0.8,
            ))

    # --- Author block & contact ----------------------------------------------------
    if len(doc.paragraphs) > 1:
        authors_block = doc.paragraphs[1].strip()
        if not authors_block or len(authors_block) < 5:
            findings.append(Finding(
                category=cat, severity=Severity.MEDIUM,
                title="Author block missing or unparsable",
                detail="No author names detected after the title.",
                evidence="paragraph 2 = '" + authors_block[:60] + "'",
                action="List all authors with affiliations and ORCIDs in the venue's format.",
                confidence=0.8,
            ))
    if not _EMAIL_RE.search(full):
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="No corresponding-author email found",
            detail="Many submission systems and journals require the corresponding author's email.",
            evidence="email regex scan = 0 matches",
            action="Add the corresponding author email and affiliation.",
            confidence=0.75,
        ))

    # --- Abstract quality ------------------------------------------------------------
    from .compliance import _abstract_text

    abstract = _abstract_text(doc)
    if abstract:
        if not _STRONG_ABSTRACT_WORDS.search(abstract):
            findings.append(Finding(
                category=cat, severity=Severity.MEDIUM,
                title="Abstract lacks quantitative results",
                detail="No numbers, percentages, p-values, or performance claims found in the abstract.",
                evidence="abstract quantitative scan = none",
                action="Put the key quantitative result in the abstract — editors scan it first.",
                confidence=0.7,
            ))

    # --- Keywords ---------------------------------------------------------------------
    # Accept 'Keywords—deepfake, ...' (em/en dash) as well as 'Keywords:' styles.
    kw = re.search(r"(?im)^keywords?\s*[:.\-\u2014\u2013\u2012\u2010]?\s*(.+)$", full)
    if not kw:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Keywords missing",
            detail="No 'Keywords:' section found (required by most venues, used for indexing).",
            evidence="keywords section scan = not found",
            action="Add 4-6 keywords after the abstract.",
            confidence=0.85,
        ))
    else:
        kws = [k.strip() for k in re.split(r"[;,]", kw.group(1)) if k.strip()]
        if len(kws) < 3:
            findings.append(Finding(
                category=cat, severity=Severity.LOW,
                title="Too few keywords",
                detail=f"Only {len(kws)} keyword(s) found.",
                evidence="keywords parsed = " + str(kws),
                action="Add at least 4-6 distinct keywords.",
                confidence=0.7,
            ))

    # --- Required statements -------------------------------------------------------------
    def _stmt_pattern(stmt: str):
        """Case-insensitive literal match; 'Acknowledg...' accepts both spellings
        (Acknowledgment / Acknowledgement, singular or plural) so a venue preset
        written in one variant never false-flags a paper using the other."""
        m = re.match(r"^(acknowledg)(e?)(ment)(s?)$", stmt.strip(), re.IGNORECASE)
        if m:
            pat = re.escape(m.group(1)) + "(e?)" + re.escape(m.group(3)) + "(s?)"
        else:
            pat = re.escape(stmt)
        return re.compile(pat, re.IGNORECASE)

    required = rules.get("required_statements", [])
    missing_stmts = []
    for stmt in required:
        pattern = _stmt_pattern(stmt)
        if not pattern.search(full):
            missing_stmts.append(stmt)
    if missing_stmts:
        findings.append(Finding(
            category=cat,
            severity=Severity.HIGH if len(missing_stmts) >= 2 else Severity.MEDIUM,
            title="Missing required statement(s)",
            detail="Not found: " + ", ".join(missing_stmts),
            evidence="venue required_statements = " + ", ".join(required),
            action="Add each missing statement section (even a one-line 'no conflict' declaration — absence is not equivalent to none).",
            confidence=0.9,
            location=", ".join(missing_stmts),
        ))
    return findings