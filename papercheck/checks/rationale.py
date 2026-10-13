"""Rationale engine: does the introduction state *why this work was needed*?

Why this engine exists
----------------------
Menon et al. 2020 (n=898 rejection reports, *Indian Journal of Psychological
Medicine*) named **weak study rationale** one of the three most common reasons
for rejection after peer review — alongside inappropriate design and poor
methodological description. Edmans' *Learnings from 1,000 Rejections* (Review
of Finance, 2025) lists importance of findings among the primary reasons for
rejection. The question every reviewer asks is the one nobody automates: *so
what?*

Nothing in the 98-engine registry checked it. `novelty.py` asks whether a
*contribution* lexicon appears somewhere; `claims.py` asks whether the
conclusion overclaims; `reporting_guidelines.py` checks the EQUATOR item for
studies that have a checklist for it. A paper whose introduction is pure
background — "retinal imaging is widely used; many datasets exist; prior work
is abundant" — with no gap, no question, and no hypothesis fired nothing at
all (probe, 2026-10-12).

What this checks (in the introduction / opening only)
-----------------------------------------------------
* an explicit **research gap**: "however, little is known", "remains unclear",
  "has not been examined", "gap in the literature", ...
* a **research question** or **hypothesis**: "we ask", "we hypothesise",
  "RQ1", "H1", "the question is"
* a **motivation / significance statement**: "this matters because",
  "critically", "of particular importance", "enabling", "without which"
* the section's own length: a 1,000-word introduction with none of the above
  is background-reading, not a case for the paper

Severity discipline: MEDIUM at most, with confidence 0.6–0.7. Absence of the
*phrase* is not absence of the *idea* — some fields state the gap implicitly.
The action always names the sentence to add, so the fix is mechanical.

This engine owns "why was this work needed" end to end. `novelty` owns "what
is new"; `claims` owns "is the conclusion warranted". Do not add gap checks
elsewhere.
"""
from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

# An explicit statement that prior work leaves something open.
_GAP = re.compile(
    r"\b(?:"
    r"little\s+is\s+known|little\s+attention|remains?\s+(?:largely\s+)?(?:unknown|unclear|unexplored|unstudied|open)"
    r"|has?\s+not\s+been\s+(?:examined|studied|investigated|explored|addressed|evaluated|tested)"
    r"|have\s+not\s+been\s+(?:examined|studied|investigated|explored|addressed)"
    r"|gap\s+in\s+the\s+(?:literature|research|evidence)|research\s+gap|identified?\s+gap"
    r"|few\s+studies|no\s+study\s+has|no\s+prior\s+work|remains?\s+a\s+challenge"
    r"|yet\s+to\s+be\s+(?:determined|established|resolved)|underexplored|under-studied"
    r"|overlooked|unresolved|not\s+yet\s+(?:known|understood|addressed|clear)"
    r")\b", re.IGNORECASE)

# A question or hypothesis the paper commits to answering.
_QUESTION = re.compile(
    r"\b(?:"
    r"we\s+(?:ask|investigate|examine|set\s+out\s+to|aim\s+to\s+(?:answer|determine|establish))"
    r"|we\s+hypothesi[sz]e|our\s+hypothesis|test(?:ing)?\s+the\s+hypothesis"
    r"|research\s+questions?|RQ\s*\d|H\s*\d\b|the\s+question\s+(?:is|of)"
    r"|objective\s+of\s+(?:this|the)\s+(?:study|paper|work)|we\s+seek\s+to"
    r"|it\s+remains\s+(?:to\s+be\s+)?(?:seen|determined)"
    r")\b", re.IGNORECASE)

# Why it matters to anyone outside the lab.
_MOTIVATION = re.compile(
    r"\b(?:"
    r"this\s+matter|matters\s+because|of\s+(?:particular|considerable|critical|significant)\s+(?:importance|practical\s+importance)"
    r"|critically\s+important|practical(?:ly)?\s+significant|real-world\s+(?:impact|relevance|implications)"
    r"|enabl(?:es|ing)|without\s+which|has\s+direct\s+implications|so\s+what"
    r"|why\s+it\s+matters|consequence\s+for|of\s+widespread\s+concern"
    r"|cost(?:s)?\s+(?:the|society|industry)|affects\s+millions|globally"
    r")\b", re.IGNORECASE)


def _intro(doc: Document) -> str:
    from ..ingestion import normalize_heading
    for s in doc.sections:
        h = normalize_heading(s.heading)
        if re.match(r"^(introduction|background|1)\b", h) or h == "1":
            return s.body
    return ""


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 300:
        return findings
    intro = _intro(doc)
    if len(intro.split()) < 80:
        # No parseable introduction — `structure`/`submission` own missing
        # sections; a short or absent intro is not this engine's finding.
        return findings

    gaps = _GAP.findall(intro)
    questions = _QUESTION.findall(intro)
    motives = _MOTIVATION.findall(intro)

    if not gaps and not questions and not motives:
        findings.append(Finding(
            category="Rationale", severity=Severity.MEDIUM,
            title="Introduction states no research gap, question, or motivation",
            detail=("The introduction runs " + str(len(intro.split())) +
                    " words without once saying what is missing, what the paper "
                    "asks, or why it matters. Reviewers rank a weak study "
                    "rationale among the top reasons for rejection — the "
                    "'so what?' has to be answered before the methods are read."),
            evidence="gap markers = 0; question/hypothesis markers = 0; "
                     "motivation markers = 0 in the introduction",
            action=("Add two sentences: one naming the gap ('however, X remains "
                    "unknown'), one stating the question or hypothesis and why "
                    "answering it matters."),
            confidence=0.7,
        ))
        return findings

    if not gaps:
        findings.append(Finding(
            category="Rationale", severity=Severity.MEDIUM,
            title="No explicit research gap in the introduction",
            detail=("The introduction states a question or a motivation but "
                    "never says what prior work leaves open. Editors and "
                    "reviewers look for the gap first; without it the "
                    "contribution has nothing to be a contribution *relative to*."),
            evidence="gap markers = 0 (question/motivation markers present)",
            action=("Add an explicit gap sentence: 'However, ... remains "
                    "unclear / has not been examined / little is known about ...'"),
            confidence=0.65,
        ))

    if not questions:
        findings.append(Finding(
            category="Rationale", severity=Severity.LOW,
            title="No stated research question or hypothesis",
            detail=("Nothing in the introduction frames what the study asks or "
                    "predicts. Quantitative venues in particular expect a "
                    "testable hypothesis before the methods section."),
            evidence="question/hypothesis markers = 0 in the introduction",
            action=("State the research question (RQ1) or hypothesis (H1) "
                    "explicitly, and refer back to it in the results."),
            confidence=0.6,
        ))

    if not motives:
        findings.append(Finding(
            category="Rationale", severity=Severity.LOW,
            title="Significance of the work is not stated",
            detail=("The introduction never says why the finding matters "
                    "outside the paper. 'Importance of the findings' is one of "
                    "the named reasons for rejection across 1,000 editorial "
                    "rejections (Edmans 2025)."),
            evidence="motivation markers = 0 in the introduction",
            action=("Add one sentence on who is affected and how — clinical, "
                    "engineering, policy, or scientific consequence."),
            confidence=0.6,
        ))

    return findings
