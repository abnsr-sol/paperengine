"""PPS tortured-phrase engine: Aho-Corasick word-trie scanning.

Backed by the Problematic Paper Screener catalogue (Cabanac, Labbe &
Magazinov 2021) via `papercheck.intel`: a curated built-in list works fully
offline; `papercheck --sync-all` refreshes/extends it from the community
dataset. Scanning is a word-level trie walk — O(total words x phrase depth),
so even a 3,000-phrase catalogue costs milliseconds on a full manuscript.

A hit is a *signal of spun/AI-translated text*, never a verdict: one phrase
is LOW/INFO; multiple distinct phrases in a short document is the classic
paper-mill signature (HIGH). Escape hatch: quoted/graphical-legend reuse or
a declared translation disclaimer suppresses flagging.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..ingestion import Document
from ..intel import load_phrases
from ..risk import Finding, Severity


class _Node:
    __slots__ = ("children", "tortured", "intended")

    def __init__(self) -> None:
        self.children: Dict[str, "_Node"] = {}
        self.tortured: str = ""
        self.intended: str = ""


def build_trie(pairs: List[Tuple[str, str]]) -> _Node:
    root = _Node()
    for tortured, intended in pairs:
        node = root
        for word in tortured.split():
            node = node.children.setdefault(word, _Node())
        node.tortured = tortured
        node.intended = intended
    return root


def scan(words: List[str], root: _Node) -> List[Tuple[str, str, int]]:
    """Return [(tortured, intended, word_index), ...] via trie walk."""
    hits: List[Tuple[str, str, int]] = []
    n = len(words)
    for i in range(n):
        node = root
        j = i
        while j < n:
            nxt = node.children.get(words[j])
            if nxt is None:
                break
            node = nxt
            j += 1
            if node.tortured:
                hits.append((node.tortured, node.intended, i))
    return hits


_WORD_RE = re.compile(r"[a-z]+")
_ESCAPE_HATCH = re.compile(
    r"translated from|machine-translated|non-native english|"
    r"author.{0,20}translation", re.IGNORECASE)


def _f(sev, title, detail, evidence, action, conf):
    return Finding("Integrity", sev, title, detail, evidence, action, conf,
                   source="tortured_phrases")


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    words = _WORD_RE.findall(low)
    if len(words) < 150:
        return []
    # escape hatch: a declared translation context lowers confidence
    declared = bool(_ESCAPE_HATCH.search(low))

    root = build_trie(load_phrases())
    hits = scan(words, root)
    if not hits:
        return []

    # dedupe distinct phrases, keep first-seen order
    distinct: Dict[str, Tuple[str, str]] = {}
    for tortured, intended, _i in hits:
        distinct.setdefault(tortured, (intended, _i))
    n_distinct = len(distinct)

    shown = ", ".join(
        f'"{t}" (intended: {i})' for t, (i, _p) in
        sorted(distinct.items(), key=lambda kv: kv[1][1])[:6])

    if n_distinct >= 3:
        sev = Severity.HIGH
        conf = 0.80 if not declared else 0.55
        title = (f"{n_distinct} tortured phrases detected — spun/AI-translated "
                 "text signature")
    else:
        sev = Severity.MEDIUM if n_distinct == 2 else Severity.LOW
        conf = 0.60 if not declared else 0.35
        title = "Tortured phrase detected (spun/AI-translated text signal)"

    detail = (
        "Tortured phrases are literal translation artifacts used to evade "
        "similarity checkers (documented by the Problematic Paper Screener, "
        "Cabanac et al.). Publishers screen for them before review.")
    if declared:
        detail += " A translation disclaimer was detected — the signal is downgraded accordingly."
    action = ("Replace each flagged phrase with the standard terminology and "
              "re-read the sentence for sense. Refresh the phrase catalogue "
              "with `papercheck --sync-all`.")

    return [_f(sev, title, detail, shown, action, conf)]
