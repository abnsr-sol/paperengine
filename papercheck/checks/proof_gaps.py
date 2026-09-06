"""Proof-gap engine: dismissal phrases that substitute for mathematical steps.

Reviewer-visible tells in theory-heavy papers: "it is trivial to see",
"obviously", "it can easily be shown", "the proof is omitted", "by simple
algebra", "clearly holds". Each occurrence where a non-trivial step is
being waved through invites the Nitpicker archetype to attack. The engine
counts occurrences and reports density with every phrase as evidence —
it never claims the math is wrong, only that the *argumentation style*
invites scrutiny.
"""
from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity

_GAP_PHRASES = [
    r"it\s+is\s+(?:trivial|easy|straightforward|simple)\s+to\s+(?:see|show|verify|prove|check)",
    r"trivially[,]?",
    r"obviously[,]?",
    r"it\s+can\s+easily\s+be\s+shown",
    r"by\s+simple\s+(?:algebra|substitution|induction|inspection|calculation)",
    r"the\s+(?:proof|details)\s+are\s+(?:omitted|left\s+to\s+the\s+reader|straightforward)",
    r"we\s+omit\s+the\s+(?:proof|details)",
    r"clearly[,]?\s+(?:holds|satisfies|follows|converges)",
    r"immediately\s+(?:follows|gives|yields)",
    r"as\s+is\s+well\s+known",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _GAP_PHRASES]

# math-context signal: the paper actually contains formal math
_MATH = re.compile(
    r"\\begin\{(?:theorem|lemma|proposition|proof)\}|theorem\s+\d|lemma\s+\d|"
    r"proof\.|O\(n|big-O|\bwe\s+prove\b|\bproof\s+of\s+theorem", re.IGNORECASE)


def run(doc: Document, ctx) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if doc.word_count < 200 or not _MATH.search(body):
        return []

    hits: List[str] = []
    for pat in _COMPILED:
        for m in pat.finditer(body):
            start = max(0, m.start() - 45)
            ctx_text = re.sub(r"\s+", " ", body[start:m.end() + 45]).strip()
            hits.append(ctx_text)

    if not hits:
        return []
    out: List[Finding] = []
    if len(hits) >= 3:
        out.append(Finding(
            "Rigor", Severity.MEDIUM,
            "Proof-gap dismissal phrases invite the 'Nitpicker' objection",
            f"{len(hits)} dismissal phrase(s) (\"trivially\", \"it is easy to "
            "show\", \"details omitted\", ...) stand where reviewers expect "
            "steps. In formal sections these reads as hand-waving; each one "
            "becomes a cheap review attack target.",
            "; ".join(f"\"{h[:60]}\"" for h in hits[:4]), 0.6,
            "Replace each dismissal with the actual step, a short appendix "
            "proof, or a citation to where the step is proven."))
    elif len(hits) == 2 and _MATH.search(body):
        out.append(Finding(
            "Rigor", Severity.LOW,
            "Dismissal phrasing in formal sections",
            f"2 dismissal phrase(s) found. Isolated uses are acceptable, but "
            "verify each covers only a genuinely trivial step.",
            "; ".join(f"\"{h[:60]}\"" for h in hits), 0.45,
            "Spot-check that each 'trivially' corresponds to a step a "
            "reviewer can verify in one line."))
    return out
