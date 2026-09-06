"""Language engine: readability, grammar heuristics, passive voice, punctuation.

This is *not* a full grammar engine (that needs LanguageTool or similar).
These are conservative, deterministic heuristics that catch the problems
reviewers most often cite: hard-to-read prose, informal tone, punctuation
issues, run-ons/fragments, and excessive passives. Each carries an honest
confidence and a "confirm with a real editor" action where appropriate.
"""

from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..metrics import (
    AI_TEMPLATES,
    HEDGES,
    INFORMAL,
    count_terms,
    flesch_kincaid_grade,
    flesch_reading_ease,
    mean,
    punctuation_profile,
    repeated_phrase_density,
    sentences,
    words,
)
from ..risk import Finding, Severity
from . import CheckContext


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    text = doc.body_text
    findings: List[Finding] = []
    cat = "Language"
    wc = doc.word_count
    if wc < 30:
        return findings

    # --- Readability -----------------------------------------------------------
    ease = flesch_reading_ease(text)
    grade = flesch_kincaid_grade(text)
    if grade > 14 or ease < 25:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Prose is very hard to read",
            detail=f"Flesch-Kincaid grade {grade:.1f} / reading ease {ease:.0f} — typical scientific text is grade 12-14.",
            evidence=f"readability: FK grade {grade:.1f}, FRE {ease:.1f}",
            action="Break up long sentences, prefer concrete verbs over nominalizations, and simplify subordinate clauses.",
            confidence=0.6,
            location="whole document",
        ))

    # --- Passive voice -----------------------------------------------------------
    from ..metrics import passive_voice_ratio

    pv = passive_voice_ratio(text)
    if pv > 0.35:
        findings.append(Finding(
            category=cat,
            severity=Severity.LOW,
            title="Heavy passive voice",
            detail=f"~{pv*100:.0f}% of inflected verb forms look passive.",
            evidence=f"passive_voice_ratio = {pv:.2f} (heuristic)",
            action="Rewrite key methodological sentences in active voice; keep passive where the action is the subject (allowed in methods).",
            confidence=0.5,
            location="whole document",
        ))

    # --- Sentence-level problems ---------------------------------------------------
    # Numbered-list labels ('1.'), section headings, and citation-field tokens are
    # not prose fragments — drop them before judging run-ons/short sentences.
    from ..ingestion import normalize_heading

    _numeric_label = re.compile(r"^\d+(?:\.\d+)*(?:[.)]?)$")
    _heading_norms = {normalize_heading(s.heading) for s in doc.sections}

    def _is_label(snt):
        t = snt.strip().lower()
        return (not t) or bool(_numeric_label.match(t)) or normalize_heading(t) in _heading_norms

    sents = [s for s in sentences(text) if not _is_label(s)]
    lens = [len(words(s)) for s in sents]
    if lens:
        avg = mean(lens)
        runs = sum(1 for n in lens if n > 45)
        frags = sum(1 for n in lens if 1 <= n <= 3)
        if runs / len(lens) > 0.12:
            findings.append(Finding(
                category=cat,
                severity=Severity.MEDIUM,
                title="Excessive run-on sentences",
                detail=f"{runs} of {len(lens)} sentences exceed 45 words (avg {avg:.1f}).",
                evidence=f"run-ons >45w = {runs}, total sentences = {len(lens)}",
                action="Split long sentences; reviewers flag dense, unreadable prose.",
                confidence=0.7,
            ))
        if frags > 3:
            findings.append(Finding(
                category=cat,
                severity=Severity.LOW,
                title="Sentence fragments detected",
                detail=f"{frags} sentences of ≤3 words — possible fragments or note-style text.",
                evidence=f"short sentences (1-3w) = {frags}",
                action="Turn fragments into complete sentences or merge them.",
                confidence=0.5,
            ))

    # --- Punctuation hygiene ---------------------------------------------------------
    prof = punctuation_profile(text)
    if prof["exclamation"] > 0:
        findings.append(Finding(
            category=cat,
            severity=Severity.LOW,
            title="Exclamation marks in academic text",
            detail=f"{prof['exclamation']} '!' found. Academic prose avoids exclamation marks.",
            evidence="punctuation_profile: exclamation > 0",
            action="Remove exclamation marks and rephrase emphatically.",
            confidence=0.9,
        ))
    # Missing space after punctuation
    missing_space = re.findall(r"[.!?][A-Za-z]", text)
    if missing_space:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Missing space after punctuation",
            detail=f"{len(missing_space)} occurrences of '.X' style (e.g. 'end.Start').",
            evidence="regex [.!?][A-Za-z] matches: " + str(len(missing_space)),
            action="Insert spaces after sentence-ending punctuation; also check for double spaces.",
            confidence=0.9,
        ))
    dbl_space = re.findall(r"[^ ]  +[^ ]", text)
    if dbl_space:
        findings.append(Finding(
            category=cat,
            severity=Severity.LOW,
            title="Double spaces detected",
            detail=f"{len(dbl_space)} double-space occurrences.",
            evidence="regex '  +' matches",
            action="Normalize to single spaces (some venues auto-reject sloppy whitespace).",
            confidence=0.9,
        ))
    # Duplicate-word typos live *inside* a line/sentence. A regex over the whole
    # text would also match a heading word repeated as the next paragraph's first
    # word ("8.1 Compression\nCompression may ..."), so scan line by line.
    rep_word = []
    for _line in text.splitlines():
        rep_word.extend(re.findall(r"\b(\w+)[ \t]+\1\b", _line.lower()))
    if rep_word:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Repeated words (typos)",
            detail=f"{len(rep_word)} repeated-word pairs like 'the the'.",
            evidence="regex word-duplicate matches: " + str(len(rep_word)),
            action="Fix the duplicated words.",
            confidence=0.9,
        ))

    # --- Informal / conversational tone -------------------------------------------------
    informal = [t for t in INFORMAL if t in text.lower()]
    if informal:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Informal / conversational language",
            detail="Found: " + ", ".join(informal[:6]),
            evidence="informal lexicon hits",
            action="Replace informal phrasing with formal academic register.",
            confidence=0.85,
        ))

    # --- Hedging / weak claims --------------------------------------------------------
    hedge_hits = count_terms(text, HEDGES)
    n_hedges = sum(hedge_hits.values())
    if n_hedges > 0:
        findings.append(Finding(
            category=cat,
            severity=Severity.INFO,
            title="Frequent hedging language",
            detail=f"{n_hedges} hedging phrases found (e.g. 'suggests that', 'may indicate').",
            evidence="hedging lexicon hits = " + str(n_hedges),
            action="Keep hedging where justified; convert weak claims into concrete, evidence-backed statements in the conclusion.",
            confidence=0.6,
        ))

    # --- Template phrases (weak AI-signal, also common in human drafts) ---------------------
    templ = count_terms(text, AI_TEMPLATES)
    n_templ = sum(templ.values())
    if n_templ >= 5:
        findings.append(Finding(
            category=cat,
            severity=Severity.LOW,
            title="Generic template phrasing",
            detail=f"{n_templ} generic transitions/boilerplate phrases ('in this paper, we', 'furthermore', ...).",
            evidence="template lexicon hits = " + str(n_templ),
            action="Vary transitions and make claims specific; dense boilerplate reads as low-effort.",
            confidence=0.55,
        ))

    # --- Repetition ----------------------------------------------------------------------
    rep = repeated_phrase_density(text)
    if rep > 0.05:
        findings.append(Finding(
            category=cat,
            severity=Severity.MEDIUM,
            title="Repeated phrases / redundant prose",
            detail=f"~{rep*100:.0f}% of distinctive phrases repeat verbatim across the document.",
            evidence=f"repeated_phrase_density = {rep:.3f}",
            action="Rewrite repeated passages; self-repetition between abstract, intro, and conclusion is a common reviewer complaint.",
            confidence=0.65,
        ))
    return findings