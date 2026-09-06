"""Transitions engine: logical flow, section signposting, abrupt topic changes."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_SKIP = re.compile(r"^(?:abstract|keywords?|references?|acknowledg)", re.IGNORECASE)
_TRANS = re.compile(r"^(?:however|moreover|furthermore|additionally|in addition|consequently|therefore|thus|hence|nevertheless|nonetheless|meanwhile|subsequently|finally|first|second|third|next|then|in contrast|by contrast|similarly|accordingly|building on|following this|in summary|to summarize|as a result)\b", re.IGNORECASE)


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Flow", sev, title, detail, evidence, action, conf)


def _words(p: str):
    return set(w.lower() for w in re.findall(r"[a-z]{4,}", p))


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    sections = [s for s in (doc.sections or []) if not _SKIP.match(s.heading or "")]
    out = []
    # section signposting: consecutive sections with zero lexical overlap
    if len(sections) >= 3:
        gaps = []
        for a, b in zip(sections, sections[1:]):
            wa, wb = _words(getattr(a, 'body', '') or getattr(a, 'text', '') or ''), _words(getattr(b, 'body', '') or getattr(b, 'text', '') or '')
            if wa and wb and not (wa & wb):
                gaps.append((a.heading, b.heading))
        if len(gaps) >= 2:
            out.append(_f(Severity.MEDIUM, "Abrupt topic shifts between sections", str(len(gaps)) + " adjacent section pairs share no content words, suggesting weak logical flow.",
                          "Gaps: " + " -> ".join(f"{a}>{b}" for a, b in gaps[:3]), 0.60, "Add linking sentences at section ends/beginnings to bridge sections"))
    # roadmap in introduction
    low = text.lower()
    if re.search(r"\bintroduction\b", low) and len(text.split()) > 2000:
        if not re.search(r"(?:organized|structured|remainder|rest)\s+of\s+(?:this|the)\s+(?:paper|article|manuscript)|paper\s+is\s+organized|as\s+follows", low):
            out.append(_f(Severity.LOW, "No roadmap in Introduction", "Long papers typically end the Introduction with a 'the rest of this paper is organized as follows' paragraph.",
                          "No roadmap phrasing found", 0.60, "Add a short roadmap paragraph at the end of the Introduction"))
    # paragraph transitions inside body
    paragraphs = doc.paragraphs or [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    body = [p.strip() for p in paragraphs if len(p.split()) >= 30 and not _SKIP.match(p.strip())]
    if len(body) >= 6:
        no_link = [p for p in body[1:] if not _TRANS.match(p) and not re.match(r"^(?:this|these|such)\b", p, re.IGNORECASE)]
        share = len(no_link) / len(body)
        if share > 0.9:
            out.append(_f(Severity.LOW, "Few explicit paragraph transitions", str(round(share * 100)) + "% of paragraphs lack connective openings; heavy use is not required, but zero reads as choppy.",
                          str(len(no_link)) + "/" + str(len(body)) + " paragraphs without connectives", 0.45, "Add occasional connective phrases (However, Building on this, Consequently) to guide the reader"))
    return out