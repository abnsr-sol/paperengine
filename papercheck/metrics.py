"""Pure text statistics used by the check engines.

All functions are deterministic, dependency-free, and operate on plain text.
Heuristic thresholds are deliberately conservative: academic/technical writing
naturally scores differently from casual prose, so every metric here feeds
*risk signals* with honest confidence values, never verdicts.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Counter as CounterT, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Tokenization / sentences
# --------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def sentences(text: str) -> List[str]:
    """Split text into sentences, keeping them trimmed and non-empty."""
    parts = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    # Split on explicit sentence breaks even without trailing whitespace.
    refined: List[str] = []
    for p in parts:
        for chunk in re.split(r"(?<=[.!?])\s+", p):
            chunk = chunk.strip()
            if chunk:
                refined.append(chunk)
    return refined


def words(text: str) -> List[str]:
    return [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text) if w]


def word_count(text: str) -> int:
    return len(words(text))


def sentence_lengths(text: str) -> List[int]:
    return [len(words(s)) for s in sentences(text)]


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math_sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def math_sqrt(x: float) -> float:
    import math

    return math.sqrt(max(0.0, x))


# --------------------------------------------------------------------------
# Readability
# --------------------------------------------------------------------------

_SYLLABLES_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)
_ED_SILENT = re.compile(r"e$", re.IGNORECASE)


def syllable_count(word: str) -> int:
    w = word.lower().strip(".,;:!?()[]{}")
    if not w:
        return 0
    count = len(_SYLLABLES_RE.findall(w))
    if count == 0:
        return 1
    # "silent e" heuristic: words ending in a vowel+e like "made"
    if _ED_SILENT.search(w) and len(w) > 3 and not re.search(r"[aeiou]e$", w):
        count = max(1, count - 1)
    return count


def flesch_reading_ease(text: str) -> float:
    """Higher = easier. ~0-30 very difficult, 60-70 plain English, 90+ easy."""
    n_words = len(words(text))
    n_sents = max(1, len(sentences(text)))
    n_syll = max(1, sum(syllable_count(w) for w in words(text)))
    return 206.835 - 1.015 * (n_words / n_sents) - 84.6 * (n_syll / n_words)


def flesch_kincaid_grade(text: str) -> float:
    n_words = len(words(text))
    n_sents = max(1, len(sentences(text)))
    n_syll = max(1, sum(syllable_count(w) for w in words(text)))
    return 0.39 * (n_words / n_sents) + 11.8 * (n_syll / n_words) - 15.59


# --------------------------------------------------------------------------
# Vocabulary / style fingerprints
# --------------------------------------------------------------------------

def type_token_ratio(text: str) -> float:
    """Lexical diversity. Technical writing naturally has a lower TTR than prose."""
    w = words(text)
    if len(w) < 50:
        return 0.0
    return len(set(w)) / len(w)


def sentence_burstiness(text: str) -> float:
    """Coefficient of variation of sentence length. Uniformly similar-length
    sentences (low burstiness) are a *weak* AI-writing signal, with heavy
    false-positive risk on technical writing."""
    lens = [float(x) for x in sentence_lengths(text) if x > 0]
    if len(lens) < 8:
        return 0.0
    m = mean(lens)
    if m == 0:
        return 0.0
    return stdev(lens) / m


def punctuation_profile(text: str) -> Dict[str, int]:
    return {
        "em_dash": text.count("\u2014") + text.count("—"),
        "semicolon": text.count(";"),
        "colon": text.count(":"),
        "exclamation": text.count("!"),
        "quotes": text.count('"') + text.count("“") + text.count("”"),
        "parentheses_pairs": len(re.findall(r"\([^)]*\)", text)),
        "comma": text.count(","),
    }


def repeated_ngrams(text: str, min_n: int = 4, max_n: int = 6, min_count: int = 2) -> CounterT[Tuple[str, ...]]:
    """Distinctive repeated phrases. Short common phrases are excluded."""
    stop = {"and", "the", "of", "to", "in", "a", "is", "for", "on", "with", "that", "this", "we", "as", "by", "are", "was", "were", "it", "an", "at", "be", "or", "from", "can", "our", "their", "its", "has", "have", "not", "but", "so", "if", "than", "then", "also", "such", "which", "these", "those", "using", "used", "based", "shown", "show", "results", "result", "data", "figure", "table"}
    counts: CounterT[Tuple[str, ...]] = Counter()
    w = words(text)
    lowered = [x.lower() for x in w]
    for n in range(min_n, max_n + 1):
        for i in range(len(lowered) - n + 1):
            gram = tuple(lowered[i : i + n])
            if any(tok in stop for tok in gram):
                continue
            counts[gram] += 1
    return Counter({g: c for g, c in counts.items() if c >= min_count})


def repeated_phrase_density(text: str) -> float:
    """Fraction of distinctive n-grams that repeat. High repetition raises
    redundancy / 'template writing' risk."""
    grams = repeated_ngrams(text)
    if not grams:
        return 0.0
    total = sum(grams.values())
    repeated_total = sum(c - 1 for c in grams.values())
    return repeated_total / max(1, total)


# --------------------------------------------------------------------------
# Style lexicons
# --------------------------------------------------------------------------

HEDGES = [
    "arguably", "somewhat", "generally", "largely", "broadly", "roughly",
    "approximately", "tends to", "appears to", "seems to", "suggests that",
    "may indicate", "could be", "might be", "potentially", "possibly",
    "to some extent", "in some cases", "in many cases",
]

INFORMAL = [
    "don't", "doesn't", "didn't", "can't", "won't", "isn't", "aren't",
    "wasn't", "weren't", "it's", "that's", "gonna", "wanna", "kinda",
    "a lot of", "lots of", "stuff", "things", "okay", "basically",
    "pretty good", "really good", "big deal", "by the way",
]

AI_TEMPLATES = [
    "in this paper, we", "in this study, we", "this paper presents",
    "this paper proposes", "this paper introduces", "we propose a novel",
    "it is important to note", "it is worth noting", "it should be noted",
    "in conclusion,", "furthermore,", "moreover,", "additionally,",
    "as a result,", "in other words,", "overall,", "lastly,",
    "in recent years", "plays a crucial role", "plays an important role",
    "has gained significant attention", "in the field of",
]

CONTRIBUTION_WORDS = [
    "novel", "first", "contribution", "we propose", "we introduce",
    "we present", "we develop", "we design", "we build", "our approach",
    "state-of-the-art", "outperform", "improves", "significantly",
]


def count_terms(text: str, terms: List[str]) -> Dict[str, int]:
    lowered = " " + text.lower() + " "
    out: Dict[str, int] = {}
    for term in terms:
        out[term] = lowered.count(" " + term) if " " not in term else lowered.count(term)
    return out


# --------------------------------------------------------------------------
# Passive voice (approximate)
# --------------------------------------------------------------------------

_BE_FORMS = re.compile(
    r"\b(am|is|are|was|were|been|being|be)\s+(?:\w+\s+){0,3}(\w+ed|\w+en)\b",
    re.IGNORECASE,
)
_ACTIVE_VERB = re.compile(r"\b(\w+(?:ed|ing|es|s))\b", re.IGNORECASE)


def passive_voice_ratio(text: str) -> float:
    """Approximate share of past-participle constructions that look passive."""
    matches = _BE_FORMS.findall(text)
    if not matches:
        return 0.0
    total = max(1, len(_ACTIVE_VERB.findall(text)))
    return len(matches) / total


# --------------------------------------------------------------------------
# Numbers / consistency helpers
# --------------------------------------------------------------------------

_NUM_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(%|percent|participants?|subjects?|samples?|patients?|nodes?|instances?|epochs?|layers?|features?|models?)?\b", re.IGNORECASE)


def number_mentions(text: str) -> List[Tuple[str, str]]:
    """(value, unit) pairs, e.g. ('42', 'participants')."""
    out: List[Tuple[str, str]] = []
    for m in _NUM_PATTERN.finditer(text):
        out.append((m.group(1), (m.group(2) or "").lower()))
    return out


def conflicting_numbers(text: str) -> List[Dict[str, str]]:
    """Same unit mentioned with different values anywhere in the text."""
    mentions = number_mentions(text)
    by_unit: Dict[str, set] = {}
    for value, unit in mentions:
        if unit:
            by_unit.setdefault(unit, set()).add(value)
    conflicts = []
    for unit, values in sorted(by_unit.items()):
        if len(values) > 1 and len(unit) > 2:
            conflicts.append({"unit": unit, "values": sorted(values, key=float)})
    return conflicts