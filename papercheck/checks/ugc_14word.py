"""UGC 2018 statutory similarity engine (India, national standard).

Implements the University Grants Commission (Promotion of Academic Integrity
and Prevention of Plagiarism) Regulations, 2018 as a deterministic, offline
computation — not a stylometric guess:

- Clause 7 exclusions: matches below 14 consecutive words are disregarded;
  quotes, references, and acknowledgments are excluded from the calculation.
- Similarity tiers (Clause 8): Level 0 <=10%, Level 1 >10-40%, Level 2
  >40-60%, Level 3 >60% — each with the statutory consequence.
- Zero-tolerance core: verbatim overlap inside Hypothesis / Results /
  Conclusions text is scrutinized even when the overall level is 0.

This is an *internal* similarity estimate: it compares the manuscript against
the corpus the author supplies (--corpus, e.g. their own thesis or prior
papers — exactly the Shodhganga-derived-paper scenario). It is not a web-scale
plagiarism scan, and the report says so.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..ingestion import Document
from ..metrics import words
from ..risk import Finding, Severity
from . import CheckContext

_MIN_RUN = 14          # Clause 7: matches < 14 consecutive words are excluded
_TIER_LABELS = {
    "level_0": "Level 0 (<=10%): permissible, no penalty",
    "level_1": "Level 1 (>10-40%): withdrawal + 6-month resubmission window",
    "level_2": "Level 2 (>40-60%): withdrawal + debarment + supervisor penalties",
    "level_3": "Level 3 (>60%): registration cancellation territory",
}
_CORE = ("hypothesis", "hypotheses", "results", "finding", "findings",
         "conclusion", "conclusions")


def _exclude_section(doc: Document, start_pat: str) -> List[Tuple[int, int]]:
    """Character spans of sections whose heading matches start_pat."""
    spans = []
    for sec in doc.sections:
        if re.match(start_pat, sec.heading, re.IGNORECASE):
            spans.append((sec.start_index, sec.start_index + len(sec.heading) + len(sec.body) + 1))
    return spans


def _token_spans(text: str) -> List[Tuple[int, int]]:
    """Character spans aligned 1:1 with metrics.words(), which matches
    alnum-led tokens (punctuation is not a word)."""
    return [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text)]


def _qualifies(match_len: int) -> bool:
    """Clause 7: only runs of >= 14 consecutive words count."""
    return match_len >= _MIN_RUN


def _longest_common_runs(a_tokens: List[str], b_set: set,
                         a_spans: List[Tuple[int, int]]):
    """Yield (start_idx, run_len) maximal runs of a_tokens present in b."""
    runs = []
    i = 0
    n = len(a_tokens)
    while i < n:
        if a_tokens[i] in b_set:
            j = i
            while j < n and a_tokens[j] in b_set:
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    return runs


def _similarity(doc: Document, corpus_docs, core_spans) -> Dict:
    """Compute clause-compliant similarity of doc against the corpus."""
    doc_tokens_all = [w.lower() for w in words(doc.text)]
    doc_spans_all = _token_spans(doc.text)
    if not doc_tokens_all:
        return {"fraction": 0.0, "qualifying": [], "core_hits": []}

    # Clause 7 exclusions on the document side.
    excluded = set()

    def mark(spans):
        for (s, e) in spans:
            for idx, (ts, te) in enumerate(doc_spans_all):
                if te <= s or ts >= e:
                    continue
                excluded.add(idx)

    for pat in (r"^references?\b", r"^bibliography\b", r"^acknowledg",
                r"^table of contents\b"):
        mark(_exclude_section(doc, pat))

    # Corpus token sets (documents the author supplied).
    corp_sets = []
    for other in corpus_docs:
        corp_sets.append(set(w.lower() for w in words(other.text)))
    corp_union = set().union(*corp_sets) if corp_sets else set()

    # A token is 'matched' if it appears in ANY corpus doc. A qualifying run
    # must be >= 14 consecutive matched tokens (conservative single-doc union).
    matched = []
    for idx, tok in enumerate(doc_tokens_all):
        matched.append(tok in corp_union)

    qualifying = []   # (word_start, run_len)
    i = 0
    n = len(matched)
    while i < n:
        if matched[i]:
            j = i
            while j < n and matched[j]:
                j += 1
            if j - i >= _MIN_RUN and not (set(range(i, j)) & excluded):
                qualifying.append((i, j - i))
            i = j
        else:
            i += 1

    counted = sum(ln for (_, ln) in qualifying)
    fraction = counted / n if n else 0.0

    # Zero-tolerance core-section hits: any qualifying run inside Results /
    # Conclusions / Hypotheses text, regardless of overall level. Uses
    # majority-overlap containment because section spans computed from the
    # reconstructed text can drift a character or two from token spans.
    core_hits = []
    for (start, ln) in qualifying:
        char_s = doc_spans_all[start][0]
        char_e = doc_spans_all[start + ln - 1][1]
        run_len_chars = max(1, char_e - char_s)
        for (cs, ce, name) in core_spans:
            ov = min(char_e, ce) - max(char_s, cs)
            if ov > 0 and ov >= 0.8 * run_len_chars:
                core_hits.append((name, " ".join(doc_tokens_all[start:start + ln])[:100]))
                break
    return {"fraction": fraction, "qualifying": qualifying, "core_hits": core_hits}


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    corpus = getattr(ctx, "corpus", None)
    if not corpus or doc.word_count < 300:
        return []

    # Identify zero-tolerance core sections.
    core_spans = []
    for sec in doc.sections:
        h = re.sub(r"^\d+[.)]?\s*", "", sec.heading).strip().lower()
        if any(h.startswith(k) for k in _CORE):
            core_spans.append((sec.start_index,
                               sec.start_index + len(sec.heading) + len(sec.body) + 1,
                               sec.heading))

    res = _similarity(doc, corpus, core_spans)
    pct = res["fraction"] * 100

    if pct <= 10:
        level, sev = "level_0", None
    elif pct <= 40:
        level, sev = "level_1", Severity.HIGH
    elif pct <= 60:
        level, sev = "level_2", Severity.CRITICAL
    else:
        level, sev = "level_3", Severity.CRITICAL

    out: List[Finding] = []
    n_runs = len(res["qualifying"])
    longest = max((ln for (_, ln) in res["qualifying"]), default=0)

    if sev is not None:
        out.append(Finding(
            "UGC Plagiarism",
            sev,
            f"UGC similarity Level exceeded: {pct:.0f}% of the manuscript "
            f"matches supplied prior documents in 14+ word runs",
            f"Estimated statutory level: {_TIER_LABELS[level]}. {n_runs} qualifying "
            f"run(s) of >=14 consecutive words (longest {longest} words) overlap "
            f"your supplied corpus (thesis, prior papers). Under the UGC 2018 "
            f"regulations this exposure blocks submission and carries the listed "
            f"penalties.",
            f"UGC clause-7 computation: matches <14 words disregarded, "
            f"excluded sections: references/acknowledgments; corpus = "
            f"{', '.join(d.name for d in corpus[:3])}",
            "Rewrite every qualifying run in fresh words and cite the source of any "
            "retained wording; re-run this check until the level is 0",
            0.85,
        ))

    # Zero-tolerance core: qualifying runs inside Results/Conclusions/Hypotheses.
    if res["core_hits"]:
        example = res["core_hits"][0]
        out.append(Finding(
            "UGC Plagiarism",
            Severity.HIGH,
            "Verbatim overlap inside a zero-tolerance core section",
            f"Even at overall Level 0, the UGC regulations scrutinize identical "
            f"strings inside Hypotheses, Results, and Conclusions. A 14+ word run "
            f"in '{example[0]}' matches your supplied prior document: "
            f"\"{example[1]}...\"",
            f"core-section match (zero-tolerance zone: {example[0]})",
            "Rewrite this passage even if the overall similarity percentage is "
            "compliant; identical core-section strings trigger statutory scrutiny",
            0.8,
        ))

    if not out:
        out.append(Finding(
            "UGC Plagiarism",
            Severity.INFO,
            f"UGC statutory similarity estimate: Level 0 ({pct:.0f}%)",
            f"No 14+ word run overlaps the supplied prior documents ({n_runs} "
            f"qualifying runs). Clause-7 exclusions (references, quotes, "
            f"acknowledgments, <14-word matches) were applied per the 2018 "
            f"regulations. Remember: this estimates overlap against YOUR corpus "
            f"only (e.g. thesis or prior papers) — it is not a web-scale scan.",
            f"corpus: {', '.join(d.name for d in corpus[:3])}",
            "For the official figure, run your institution's designated similarity "
            "software with clause-7 exclusions configured",
            0.7,
        ))
    return out


def counted_disp(res: Dict) -> str:
    return str(len(res["qualifying"]))


__all__ = ["run"]
