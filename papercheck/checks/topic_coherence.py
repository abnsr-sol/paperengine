"""Topic coherence: does the body actually contain what the title promises?

Why this engine exists
----------------------
Scope/fit is the number-one desk-rejection reason (35% of desk rejects in the
Elsevier transport-portfolio dataset, Wu et al. 2024; the top desk reason in
Menon et al. 2020, n=898), and an editor's first read is *title + abstract +
keywords* — a median of 3 days before the decision.

Until now no engine compared the manuscript's front matter against its own
body. `structure.py` only measures title length; `scope_match` compares the
body to a *venue's* vocabulary and is silent when no venue preset is chosen.
A manuscript whose body is about something other than its title therefore
passed the offline default path untouched — while being simultaneously a
desk-reject and a review-reject.

What this checks
----------------
* title content words that never appear in the body
* keywords that never appear in the body (an author-declared topic list)
* abstract content words with no support in the body

Severity discipline: this is a lexical signal, not a semantic judgement, so
findings cap at MEDIUM with moderate confidence and the wording always tells
the author *which* words are unsupported. A paper is allowed to be about
something its title words do not literally repeat — the finding says so.
"""
from __future__ import annotations

import re
from typing import List, Set

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

# Light stopword set: function words plus the generic academic filler that
# appears in every title and would make every title "unsupported".
_STOP = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "of", "to", "in", "on", "at", "by", "for", "with", "from",
    "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "we",
    "our", "us", "they", "their", "he", "she", "his", "her", "you", "your",
    "into", "over", "under", "between", "via", "using", "use", "used", "based",
    "study", "studies", "paper", "proposes", "proposed", "propose", "presents",
    "present", "method", "methods", "approach", "approaches", "analysis",
    "research", "results", "result", "effect", "effects", "new", "novel",
    "using", "based", "toward", "towards", "via", "case", "role", "level",
    "data", "model", "models", "system", "systems", "application", "applications",
    "high", "more", "most", "between", "among", "during", "after", "before",
    "how", "what", "why", "when", "where", "which", "who", "can", "may",
    "such", "very", "also", "both", "each", "all", "any", "some", "one", "two",
}

_TOKEN = re.compile(r"[a-z][a-z0-9\-]{2,}")


def _content(text: str, limit: int = 4000) -> Set[str]:
    """Distinct content words, lightly stemmed so 'screening' meets 'screen'."""
    out: Set[str] = set()
    for tok in _TOKEN.findall((text or "").lower()[:limit]):
        if tok in _STOP:
            continue
        # crude but symmetric: strip the same suffixes on both sides
        for suf in ("ations", "ation", "ing", "ers", "er", "ies", "es", "s"):
            if len(tok) > len(suf) + 3 and tok.endswith(suf):
                tok = tok[: -len(suf)]
                break
        if len(tok) >= 4:
            out.add(tok)
    return out


def _title(doc: Document) -> str:
    if not doc.paragraphs:
        return ""
    t = doc.paragraphs[0].strip().splitlines()[0].strip()
    # Drop a literal "Title:" label — it is markup, not a topic term, and
    # leaving it in would report 'title' as an unsupported word.
    return re.sub(r"^titles?\s*:\s*", "", t, flags=re.IGNORECASE)


def _abstract(text: str) -> str:
    m = re.search(r"abstract\s*[:\n]", text, re.IGNORECASE)
    if not m:
        return ""
    nxt = re.search(
        r"\n(?:1\.?\s*)?(?:introduction|keywords?|1\s+introduction)\b",
        text[m.end():], re.IGNORECASE)
    end = m.end() + (nxt.start() if nxt else min(len(text), m.end() + 3000))
    return text[m.end():end]


def _keywords(text: str) -> str:
    m = re.search(
        r"(?im)^keywords?\s*[:.\-\u2014\u2013\u2012\u2010]?\s*(.+)$", text)
    if not m:
        return ""
    # stop at the first section heading, not the whole document tail
    tail = m.group(1)
    cut = re.search(r"\n\s*\n?\s*(?:\d+\.?\s*)?(?:introduction|background)\b",
                    tail, re.IGNORECASE)
    return tail[: cut.start()] if cut else tail


def _front_free_body(doc: Document) -> str:
    """Body text with the front matter removed.

    ``Document.body_text`` excludes only the *references* block, so title,
    abstract and keywords are still inside it. Comparing the title against
    that would always "match" — the title is literally in the string — and
    the check could never fire. Front-matter sections are dropped here so the
    comparison is falsifiable.
    """
    from ..ingestion import normalize_heading

    keep: List[str] = []
    for s in doc.sections:
        h = normalize_heading(s.heading)
        if re.match(r"^(abstract|keywords?|title)\b", h):
            continue
        keep.append(s.body)
    if keep:
        return "\n".join(keep)
    # No sections parsed: strip the front matter by pattern instead.
    text = doc.body_text or doc.text or ""
    text = re.sub(r"abstract\s*[:\n].*?(?=\n(?:\d+\.?\s*)?introduction)", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"(?im)^keywords?\s*[:.\-\u2014\u2013\u2012\u2010].*$", " ", text)
    if doc.paragraphs:
        text = text.replace(doc.paragraphs[0].strip(), " ", 1)
    return text


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 300:
        return findings
    body = _front_free_body(doc)
    # The body must be substantial or "no support" is just a short document.
    if len(body.split()) < 250:
        return findings

    body_words = _content(body)
    if not body_words:
        return findings

    cat = "Topic coherence"
    title = _title(doc)

    # --- title vs body ---------------------------------------------------------
    tw = _content(title, limit=400)
    if len(tw) >= 4:
        missing = sorted(tw - body_words)
        # A title is allowed one or two words the body never repeats verbatim
        # (a rephrased concept, a subtitle term). Everything missing at once
        # is what an editor notices as "this is not the paper I read".
        if len(missing) >= max(3, int(0.75 * len(tw))):
            findings.append(Finding(
                category=cat, severity=Severity.MEDIUM,
                title="Title terms never appear in the manuscript body",
                detail=("The title introduces " + str(len(tw)) + " content terms, "
                        "of which " + str(len(missing)) + " occur nowhere in the "
                        "body. Either the body dropped the promised topic or the "
                        "title oversells it — editors read the title first and "
                        "reject on mismatch."),
                evidence="unsupported title terms: " + ", ".join(missing[:8]),
                action=("Realign: rename the paper to what it actually shows, or "
                        "make the title's promise explicit in the abstract and "
                        "introduction."),
                confidence=0.6,
            ))

    # --- keywords vs body ------------------------------------------------------
    kw = _keywords(doc.text)
    if kw:
        kws = [k.strip() for k in re.split(r"[,;]| and ", kw) if len(k.strip()) > 3]
        if len(kws) >= 3:
            unsupported = []
            for k in kws:
                kw_content = _content(k, limit=60)
                if kw_content and not (kw_content & body_words):
                    unsupported.append(k.strip())
            if len(unsupported) >= max(2, int(0.5 * len(kws))):
                findings.append(Finding(
                    category=cat, severity=Severity.MEDIUM,
                    title="Declared keywords with no support in the body",
                    detail=(str(len(unsupported)) + " of " + str(len(kws)) +
                            " keywords never appear in the manuscript text. "
                            "Keywords drive the journal's search index and the "
                            "reviewer's expectation; mismatched keywords read as "
                            "keyword-stuffing."),
                    evidence="unsupported keywords: " + ", ".join(unsupported[:6]),
                    action=("Replace each flagged keyword with a term the paper "
                            "actually uses, or add the missing term where it is "
                            "genuinely discussed."),
                    confidence=0.7,
                ))

    # --- abstract vs body ------------------------------------------------------
    ab = _abstract(doc.text)
    if len(ab.split()) >= 60:
        aw = _content(ab)
        if len(aw) >= 8:
            missing = sorted(aw - body_words)
            if len(missing) >= max(5, int(0.6 * len(aw))):
                findings.append(Finding(
                    category=cat, severity=Severity.MEDIUM,
                    title="Abstract promises content the body never delivers",
                    detail=("The abstract introduces " + str(len(aw)) +
                            " content terms, of which " + str(len(missing)) +
                            " never appear in the body. This is the "
                            "abstract-vs-paper gap reviewers raise first, and it "
                            "is what a desk-rejecting editor sees in the first "
                            "minute."),
                    evidence="abstract terms absent from body: " + ", ".join(missing[:8]),
                    action=("Either write those results into the body or narrow "
                            "the abstract to what the body actually reports."),
                    confidence=0.6,
                ))

    return findings
