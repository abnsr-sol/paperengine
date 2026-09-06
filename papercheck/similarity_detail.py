"""Similarity detail report: show exactly WHAT matched, not just how much.

Addresses the "similarity ≠ plagiarism" limitation head-on. When a corpus of
prior documents is supplied (--corpus), this module produces a neutral,
evidence-first report: every overlapping passage is quoted side-by-side with
interpretation guidance modeled on how editors are trained to read
iThenticate/Similarity Check reports — never a verdict, always the text plus
what to do about it.

CLI:   papercheck paper.docx --corpus ./prior_papers/ --format similarity
       papercheck paper.docx --corpus ./prior/ --format similarity --out detail.md
"""
from __future__ import annotations

import difflib
import html as _html
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .ingestion import Document
from .metrics import words

# Word-window size for passage matching (same scale as the integrity engine).
_N = 8


@dataclass
class MatchedPassage:
    """One contiguous near-match between the manuscript and a source."""

    source_name: str
    manuscript_text: str
    source_text: str
    similarity: float  # 0..1 SequenceMatcher ratio of the two passages


@dataclass
class SimilarityDetail:
    """Result of the passage-level similarity analysis."""

    document_name: str
    overall_fraction: float  # fraction of manuscript 8-grams found in the corpus
    sources: List[str] = field(default_factory=list)
    passages: List[MatchedPassage] = field(default_factory=list)

    def summary(self) -> dict:
        by_source = {}
        for p in self.passages:
            by_source[p.source_name] = by_source.get(p.source_name, 0) + 1
        return {
            "document": self.document_name,
            "overall_overlap_pct": round(self.overall_fraction * 100, 1),
            "sources": len(self.sources),
            "passages": len(self.passages),
            "passages_by_source": by_source,
        }


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def _tokens(text: str) -> List[str]:
    return [w.lower() for w in words(text)]


def _ngram_set(text: str, n: int = _N):
    toks = _tokens(text)
    return {tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)}


def _passage_matches(doc: Document, other: Document,
                     max_passages: int = 8) -> List[MatchedPassage]:
    """Find near-verbatim passages of `doc` inside `other` via n-gram anchors
    expanded with SequenceMatcher confirmation."""
    doc_words = [w for w in words(doc.text)]
    low = [w.lower() for w in doc_words]
    other_low = _tokens(other.text)

    anchors: List[Tuple[int, int]] = []  # (start, end) word indices in doc
    i = 0
    while i + _N <= len(low):
        gram = tuple(low[i : i + _N])
        if gram and " ".join(gram) in " ".join(other_low):
            j = i + _N
            # extend the match forward while words keep matching
            other_text = " ".join(other_low)
            while j < len(low) and " ".join(low[i : j + 1]) in other_text:
                j += 1
            if not anchors or i > anchors[-1][1]:
                anchors.append((i, j))
            i = j
        else:
            i += 1

    out: List[MatchedPassage] = []
    for (a, b) in anchors[: max_passages * 3]:
        text = " ".join(doc_words[a:b])
        # locate best corresponding source span for a true side-by-side view
        sm = difflib.SequenceMatcher(None, " ".join(low), " ".join(other_low))
        block = sm.find_longest_match(a, b, 0, len(other_low))
        src_text = " ".join(other_low[block.a : block.a + block.size]) if block.size else text
        ratio = difflib.SequenceMatcher(None, text.lower(), src_text.lower()).ratio()
        out.append(MatchedPassage(other.name, text, src_text, ratio))
        if len(out) >= max_passages:
            break
    return out


def analyze(doc: Document, corpus: Sequence[Document]) -> SimilarityDetail:
    doc_grams = _ngram_set(doc.text)
    total = len(doc_grams)
    detail = SimilarityDetail(document_name=doc.name, overall_fraction=0.0)
    if not total or not corpus:
        return detail

    corpus_grams = set()
    for other in corpus:
        corpus_grams |= _ngram_set(other.text)
    detail.overall_fraction = len(doc_grams & corpus_grams) / total

    for other in corpus:
        matches = _passage_matches(doc, other)
        if matches:
            detail.sources.append(other.name)
            detail.passages.extend(matches)
    return detail


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_BENIGN = (
    "statistical procedures", "standard laboratory", "commonly used",
    "manufacturer's instructions", "institutional review board",
    "informed consent", "ethics committee", "data availability statement",
    "conflict of interest", "author contributions", "acknowledged",
    "the authors declare", "was performed according to",
)


def _interpretation(p: MatchedPassage) -> str:
    low = p.manuscript_text.lower()
    if any(k in low for k in _BENIGN):
        return ("Boilerplate / standard-phrasing match — usually acceptable, but "
                "quote-and-cite if the wording is distinctive to one source.")
    if p.similarity >= 0.95:
        return ("Near-verbatim run. If this is your own prior paper: rewrite in "
                "fresh words and/or cite, per the venue's text-recycling policy. "
                "If it is someone else's: quote, cite, and keep quotes minimal.")
    if p.similarity >= 0.8:
        return "Substantial overlap — rework the passage in your own words and cite the source."
    return "Partial overlap — check whether citation or rewording is needed."


def render_markdown(rep: SimilarityDetail) -> str:
    s = rep.summary()
    lines: List[str] = []
    lines.append("# Similarity detail report")
    lines.append("")
    lines.append(f"**Manuscript:** {rep.document_name}")
    lines.append("")
    lines.append(f"**Overall n-gram overlap with the supplied corpus: "
                 f"{s['overall_overlap_pct']}%** across {s['sources']} source "
                 f"document(s), {s['passages']} matched passage(s).")
    lines.append("")
    lines.append("> **How to read this:** overlap is a *measurement*, not a "
                 "judgment. Editors use reports like this to ask three "
                 "questions — is the matched text (1) your own prior work, "
                 "(2) properly quoted/cited material, or (3) boilerplate "
                 "methods phrasing? Each match below is classified to help "
                 "you answer those questions before a reviewer does.")
    lines.append("")
    if not rep.passages:
        lines.append("No passage-level matches found in the supplied corpus. "
                     "This does not prove originality beyond the corpus — "
                     "add more of your prior papers to `--corpus` to widen the check.")
        return "\n".join(lines)

    for i, p in enumerate(rep.passages, 1):
        lines.append(f"## Match {i} — vs `{p.source_name}` "
                     f"(passage similarity {p.similarity * 100:.0f}%)")
        lines.append("")
        lines.append("**Your manuscript:**")
        lines.append(f"> {p.manuscript_text[:600]}")
        lines.append("")
        lines.append("**Source document:**")
        lines.append(f"> {p.source_text[:600]}")
        lines.append("")
        lines.append(f"**Reading:** {_interpretation(p)}")
        lines.append("")
    lines.append("---")
    lines.append("*Generated locally by PaperEngine. Nothing in this report "
                 "was uploaded anywhere; the corpus documents were read from "
                 "your own disk.*")
    return "\n".join(lines)


def render_html(rep: SimilarityDetail) -> str:
    s = rep.summary()
    e = _html.escape
    cards: List[str] = []
    for i, p in enumerate(rep.passages, 1):
        cards.append(f"""
  <div class="card">
    <div class="cardhead">Match {i} — vs <code>{e(p.source_name)}</code>
      <span class="pct">{p.similarity * 100:.0f}% passage similarity</span></div>
    <table><tr><th>Your manuscript</th><th>Source document</th></tr>
      <tr><td>{e(p.manuscript_text[:600])}</td>
          <td>{e(p.source_text[:600])}</td></tr></table>
    <p class="interp"><b>Reading:</b> {e(_interpretation(p))}</p>
  </div>""")
    body = "\n".join(cards) if cards else (
        '<p class="none">No passage-level matches found in the supplied corpus. '
        'This does not prove originality beyond the corpus — widen <code>--corpus</code>.</p>')
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Similarity detail — {e(rep.document_name)}</title>
<style>
  body {{ font-family:Georgia,'Times New Roman',serif; margin:0; background:#f4f4ef; color:#1a2233; }}
  header {{ background:#1a2233; color:#fff; padding:18px 28px; }}
  header h1 {{ margin:0; font-size:1.3rem; }}
  main {{ max-width:980px; margin:0 auto; padding:24px; }}
  .metric {{ background:#fff; border:1px solid #e2e4ea; border-radius:10px; padding:14px 18px; margin:14px 0; }}
  .metric b {{ font-size:1.5rem; }}
  .guide {{ background:#eef3ff; border:1px solid #c8d6f5; border-radius:10px; padding:12px 16px; font-size:.92rem; }}
  .card {{ background:#fff; border:1px solid #e2e4ea; border-radius:10px; padding:14px 18px; margin:16px 0; }}
  .cardhead {{ font-weight:bold; margin-bottom:8px; }}
  .pct {{ float:right; background:#fff3cd; color:#8a6d00; border-radius:12px; padding:2px 10px; font-size:.8rem; }}
  table {{ border-collapse:collapse; width:100%; }}
  th {{ background:#eef1f6; text-align:left; padding:6px 10px; font-size:.8rem; text-transform:uppercase; }}
  td {{ padding:8px 10px; border:1px solid #eef0f4; font-size:.86rem; width:50%; font-style:italic; }}
  .interp {{ font-size:.88rem; color:#445; }}
  .none {{ color:#778; }}
</style></head>
<body>
<header><h1>Similarity detail report</h1></header>
<main>
  <div class="metric">Overall corpus overlap: <b>{s['overall_overlap_pct']}%</b>
    · {s['sources']} source(s) · {s['passages']} matched passage(s)</div>
  <div class="guide"><b>How to read this:</b> overlap is a <i>measurement</i>, not a judgment.
    Editors use reports like this to ask three questions — is the matched text (1) your own prior work,
    (2) properly quoted/cited material, or (3) boilerplate methods phrasing? Each match below is
    classified to help you answer those questions before a reviewer does.</div>
  {body}
  <p style="color:#889;font-size:.8rem">Generated locally by PaperEngine — the corpus documents were read from your own disk; nothing was uploaded.</p>
</main>
</body></html>"""


__all__ = ["MatchedPassage", "SimilarityDetail", "analyze",
           "render_markdown", "render_html"]
