"""Paragraph structure engine: topic sentences, paragraph length, single-sentence paragraphs."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_SKIP = re.compile(r"^(?:abstract|keywords?|references?|acknowledg|table\s|figure\s)", re.IGNORECASE)


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Paragraphs", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    paragraphs = doc.paragraphs or []
    if not paragraphs:
        text = doc.text or ""
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    body_paras = [p.strip() for p in paragraphs if len(p.split()) >= 5 and not _SKIP.match(p.strip())]
    if not body_paras:
        return out
    long_paras = [p for p in body_paras if len(p.split()) > 200]
    if long_paras:
        out.append(_f(Severity.MEDIUM, "Paragraphs longer than 200 words", str(len(long_paras)) + " paragraph(s) exceed 200 words; reviewers skim and lose the thread.",
                      "Longest: " + str(max(len(p.split()) for p in long_paras)) + " words", 0.80, "Split long paragraphs; give each one idea with a topic sentence"))
    single = [p for p in body_paras if len(p.split()) < 25 and not re.search(r"[.!?]\s+[A-Z]", p)]
    if len(single) >= 3:
        out.append(_f(Severity.LOW, "Many one-sentence paragraphs", str(len(single)) + " very short paragraphs read as bullet-like fragments in prose.",
                      str(len(single)) + " short paragraphs", 0.60, "Merge fragment paragraphs or expand them with analysis"))
    # topic sentences: first word of paragraph is a connective or pronoun w/o antecedent
    weak_openers = [p for p in body_paras if re.match(r"^(?:This|These|It|They|Such|However|Moreover|Also)\b", p) and len(p.split()) < 12]
    if len(weak_openers) >= 2:
        out.append(_f(Severity.LOW, "Paragraphs starting with vague references", str(len(weak_openers)) + " paragraph(s) open with 'This/It/They' without restating the subject; topic sentences should stand alone.",
                      "Examples: " + " | ".join(p[:60] for p in weak_openers[:2]), 0.55, "Open paragraphs with a full topic sentence naming the subject"))
    return out