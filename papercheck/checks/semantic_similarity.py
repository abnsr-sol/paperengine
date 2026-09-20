"""Semantic-similarity engine: corpus overlap beyond exact 8-word shingles.

Two complementary signals, both standard-library only (offline promise holds):

1. **Sentence-level stemmed Jaccard** — every long enough manuscript sentence
   is compared against every corpus sentence as a set of stemmed content
   words. Catches restructured and lightly-reworded reuse (word order changed,
   connectives swapped, a synonym here and there) that contiguous shingles
   miss. This is the most common real self-plagiarism pattern.

2. **Document-level TF-IDF cosine** — near-verbatim reuse of a whole corpus
   document still lands near 1.0 even after light editing; reported HIGH only
   at >= 0.75 where false-positive risk is negligible.

Honest scope (flag-not-verdict): aggressive full-synonym paraphrase evades
lexical matching by design — that needs embedding models (the local-ML
roadmap item), and this finding says so. Overlap is evidence for a human,
never proof: identical Methods boilerplate legitimately repeats.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Set, Tuple

from ..ingestion import Document
from ..metrics import sentences as split_sentences
from ..risk import Finding, Severity

_STOP = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can",
    "had", "her", "was", "one", "our", "out", "day", "get", "has", "him",
    "his", "how", "its", "new", "now", "old", "see", "two", "way", "who",
    "did", "that", "this", "these", "those", "with", "from", "have", "been",
    "were", "their", "they", "which", "than", "then", "into", "also", "such",
    "may", "might", "will", "would", "should", "could", "shall", "must",
    "each", "both", "more", "most", "some", "only", "very", "between",
    "among", "within", "about", "after", "before", "during", "under",
    "over", "above", "below", "there", "here", "when", "where", "while",
    "because", "although", "however", "therefore", "thus", "hence",
}

_TOKEN = re.compile(r"[a-z][a-z\-]{2,}")

# Sentence match: Jaccard of stemmed content-word sets.
_SENT_JACCARD = 0.55
# Fraction of the manuscript's sentences matched that triggers a finding.
_MATCH_FRACTION_MED = 0.15
_MATCH_FRACTION_HIGH = 0.40
# Document-level cosine thresholds (near-verbatim territory).
_COS_MED = 0.55
_COS_HIGH = 0.75
_MIN_SENT_TOKENS = 6
_MIN_TOTAL_TOKENS = 60

_SUFFIXES = ("ing", "edly", "ed", "es", "s", "ly")


def _stem(word: str) -> str:
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[: len(word) - len(suf)]
    return word


def _content_set(text: str) -> Set[str]:
    return {_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP}


def _tfidf_vector(counter: Counter, idf: Dict[str, float]) -> Dict[str, float]:
    vec = {t: cnt * idf.get(t, 1.0) for t, cnt in counter.items()}
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {t: w / norm for t, w in vec.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(b) < len(a):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def _best_sentence_matches(query_sents: List[Set[str]],
                           corpus_by_doc: List[Tuple[str, List[Set[str]]]]) -> Tuple[int, str]:
    """Count query sentences matching the corpus at >= threshold Jaccard.

    Also returns the corpus document name with the most matching sentences so
    the finding can point at a concrete source instead of a vague corpus."""
    matched = 0
    per_doc: List[Tuple[int, str]] = []
    for doc_name, corpus_sents in corpus_by_doc:
        doc_hits = 0
        for q in query_sents:
            for c in corpus_sents:
                union = q | c
                if not union:
                    continue
                if len(q & c) / len(union) >= _SENT_JACCARD:
                    doc_hits += 1
                    break
        per_doc.append((doc_hits, doc_name))
    # A sentence matching multiple corpus docs counts once toward the total.
    seen: List[Set[str]] = []
    all_sents = [s for _, sents in corpus_by_doc for s in sents]
    for q in query_sents:
        for c in all_sents:
            union = q | c
            if union and len(q & c) / len(union) >= _SENT_JACCARD:
                matched += 1
                break
    per_doc.sort(reverse=True)
    top_name = per_doc[0][1] if per_doc and per_doc[0][0] else ""
    return matched, top_name


def run(doc: Document, ctx: object) -> List[Finding]:
    corpus = getattr(ctx, "corpus", None) or []
    if not corpus:
        return []
    body = doc.body_text or doc.text or ""
    q_tokens = _TOKEN.findall(body.lower())
    if len([t for t in q_tokens if t not in _STOP]) < _MIN_TOTAL_TOKENS:
        return []

    out: List[Finding] = []
    best_label, best_metric, best_kind = "", 0.0, ""

    # --- Signal 1: sentence-level stemmed Jaccard --------------------------------
    q_sents = [s for s in (_content_set(x) for x in split_sentences(body))
               if len(s) >= _MIN_SENT_TOKENS]
    if q_sents:
        corpus_by_doc: List[Tuple[str, List[Set[str]]]] = []
        for cdoc in corpus:
            ctext = cdoc.body_text or cdoc.text or ""
            sents = [s for s in (_content_set(x) for x in split_sentences(ctext))
                     if len(s) >= _MIN_SENT_TOKENS]
            if sents:
                corpus_by_doc.append((getattr(cdoc, "name", "") or "corpus document", sents))
        if corpus_by_doc:
            matched, top_doc = _best_sentence_matches(q_sents, corpus_by_doc)
            frac = matched / len(q_sents)
            if frac >= _MATCH_FRACTION_MED:
                best_label, best_metric, best_kind = (
                    "sentence-reuse", frac,
                    f"{matched}/{len(q_sents)} sentences" +
                    (f" (most vs '{top_doc}')" if top_doc else ""))

    # --- Signal 2: document-level TF-IDF cosine ----------------------------------
    corpus_counters = [Counter(_TOKEN.findall((c.body_text or c.text or "").lower()))
                       for c in corpus]
    corpus_counters = [c for c in corpus_counters if c]
    if corpus_counters:
        q_counter = Counter(q_tokens)
        df: Counter = Counter()
        for c in corpus_counters + [q_counter]:
            for t in set(c):
                df[t] += 1
        n_docs = len(corpus_counters) + 1
        idf = {t: math.log(n_docs / d) + 1.0 for t, d in df.items()}
        qvec = _tfidf_vector(q_counter, idf)
        for cdoc, ccounter in zip(corpus, corpus_counters):
            cos = _cosine(qvec, _tfidf_vector(ccounter, idf))
            name = getattr(cdoc, "name", "") or "corpus document"
            if cos >= _COS_MED and cos > best_metric:
                best_label, best_metric, best_kind = (
                    "document-overlap", cos, f"cosine {cos:.2f} vs '{name}'")

    if not best_label:
        return out

    if best_kind.startswith("cosine") or best_metric >= _MATCH_FRACTION_HIGH:
        sev, conf, title = Severity.HIGH, 0.75, "Extremely high reuse of a corpus document"
    else:
        sev, conf, title = Severity.MEDIUM, 0.65, "Substantial sentence-level reuse of corpus documents"

    out.append(Finding(
        category="Similarity", severity=sev, title=title,
        detail=(
            f"{best_kind} exceeds field-normal overlap — passages of this "
            "manuscript restate text from your supplied corpus. Overlap is not "
            "proof of plagiarism: Methods-style boilerplate legitimately "
            "repeats, and heavy synonym-for-synonym paraphrase evades lexical "
            "matching (embedding models close that gap). Read the passages and "
            "confirm every reuse is quoted or cited."
        ),
        evidence=best_label + ": " + best_kind,
        action="Open the matching corpus document side by side; quote or cite "
               "every overlapping passage and rewrite anything that merely "
               "rewords prior work",
        confidence=conf, source="semantic_similarity",
    ))
    return out
