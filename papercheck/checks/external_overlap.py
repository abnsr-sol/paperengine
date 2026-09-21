"""External-corpus overlap: verbatim reuse from *published* literature.

Every other similarity engine here compares the manuscript against a corpus
the author supplies (``--corpus``) or against itself. Neither answers the
question iThenticate exists to answer — *does this text already exist in the
published record?* — so this engine exists to close that gap, without owning
an index: two free services supply one.

* **Europe PMC** indexes the full text of open-access literature and supports
  exact-phrase search, so a sentence from the manuscript can be looked up in
  the published corpus directly.
* **OpenAlex** (key optional; raises rate limits) confirms candidates whose
  full text is not open and reports the abstract that matched, which catches
  abstract recycling from paywalled journals.

The design rests on one free signal: *how many publications contain the
phrase*. Measured against the live index, shared methods prose returns
thousands of hits while a distinctive sentence returns single digits::

    "in this study we investigated the effect of"    -> 20,044
    "the data were analyzed using spss version"      -> 17,361
    a distinctive methods sentence                   ->      0-3

So wording counts as evidence only when it is *rare* — which is what makes the
check usable with no reference corpus, and what stops it flagging every paper
that writes "SPSS version 22".

Three limits are stated in the findings themselves, not hidden:

* Coverage is open-access literature, not the paywalled iThenticate index.
* Paraphrase is invisible here; that is ``semantic_similarity``'s job against
  a supplied corpus.
* Overlap is evidence for a human, never a verdict: methods boilerplate
  legitimately repeats, and a match may be a cited quotation. A source the
  manuscript already cites is therefore reported as INFO, never as a finding
  against the author.

Offline is a silent no-op. Online but unreachable yields an INFO that says
coverage was reduced — this engine never builds an accusation on a request
that never completed (see ``papercheck.net``).
"""
from __future__ import annotations

import html
import os
import re
import time
import urllib.parse
from typing import Dict, List, Tuple

from .. import net
from ..ingestion import Document
from ..metrics import sentences
from ..risk import Finding, Severity

_API_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_API_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
_API_OPENALEX = "https://api.openalex.org/works/doi:"
_TIMEOUT = 15.0

_MAX_QUERIES = 6           # distinctive phrases looked up per manuscript
_BOILERPLATE_HITS = 25     # more hits than this = shared wording, not reuse
_MAX_SOURCES_PER_PHRASE = 5
_MAX_FINDINGS = 3
_LONG_MATCH_WORDS = 30     # contiguous words shared with one source -> HIGH
_SUSTAINED_RATIO = 0.10    # share of the manuscript's phrases found in one source
_SHINGLE = 8
_MIN_PHRASE_WORDS = 12
_MAX_PHRASE_WORDS = 45
_MIN_BODY_WORDS = 120
# A passage is *queried* as its first 20 words. Extracted text routinely runs
# two sentences together (a heading, a table cell, or a sentence that ends in a
# bracketed citation with no full stop), and a run-on passage matches nothing at
# all; a bounded window still matches while keeping the query URL short. The
# whole passage is still what gets reported, and the full-text comparison below
# measures the true shared run.
_QUERY_WORDS = 20
# Europe PMC is a free public service; space the lookups out so a batch run of
# manuscripts does not turn into the request burst that gets an IP throttled.
_PAUSE = 0.3


def _query_window(passage: str) -> str:
    """The bounded leading window of a passage that actually gets queried."""
    return " ".join(passage.split()[:_QUERY_WORDS])


def _phrase_url(phrase: str) -> str:
    quoted = urllib.parse.quote(f'"{phrase}"')
    return (f"{_API_SEARCH}?query={quoted}&format=json"
            f"&pageSize={_MAX_SOURCES_PER_PHRASE}&resultType=core")


def _distinctive_passages(body: str, limit: int) -> List[str]:
    """The manuscript's most distinctive sentences, rarest-longest first.

    Scarcity is scored by word length and digit content rather than a stopword
    list: a sentence full of long technical words and numbers is exactly the
    kind of sentence that cannot be shared by accident.
    """
    scored: List[Tuple[float, str]] = []
    seen: set = set()
    for raw in sentences(body):
        s = " ".join(raw.split()).rstrip(". ")
        words = s.split()
        if not _MIN_PHRASE_WORDS <= len(words) <= _MAX_PHRASE_WORDS:
            continue
        # Quoted material and bibliographic text are legitimately reused.
        if '"' in s or "“" in s or "”" in s:
            continue
        if re.search(r"https?://|doi:|et al\.", s, re.IGNORECASE):
            continue
        key = s.lower()
        if key in seen:      # repeated sentences cost a lookup and add nothing
            continue
        seen.add(key)
        score = sum(len(w) for w in words if len(w) >= 6) + 8 * sum(w.isdigit() for w in words)
        scored.append((score, s))
    scored.sort(key=lambda t: -t[0])
    return [s for _, s in scored[:limit]]


def _shingles(words: List[str], n: int = _SHINGLE) -> set:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _shared_run(manuscript: List[str], source: List[str], n: int) -> int:
    """Length of the longest contiguous word run shared by both texts.

    Anchored on n-grams so it never compares the whole texts pairwise; returns
    0 when nothing as long as ``n`` words is shared.
    """
    if len(manuscript) < n or len(source) < n:
        return 0
    index: Dict[Tuple[str, ...], int] = {}
    for j in range(len(source) - n + 1):
        index.setdefault(tuple(w.lower() for w in source[j:j + n]), j)
    for i in range(len(manuscript) - n + 1):
        j = index.get(tuple(w.lower() for w in manuscript[i:i + n]))
        if j is None:
            continue
        lo, mid = i, j
        while lo > 0 and mid > 0 and manuscript[lo - 1].lower() == source[mid - 1].lower():
            lo -= 1
            mid -= 1
        end, src_end = i + n, j + n
        while (end < len(manuscript) and src_end < len(source)
               and manuscript[end].lower() == source[src_end].lower()):
            end += 1
            src_end += 1
        return end - lo
    return 0


def _plain(xml: bytes) -> str:
    """Full-text XML (or HTML) to words. Structure tags become whitespace."""
    text = xml.decode("utf-8", "replace")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.IGNORECASE)
    text = re.sub(r"</(p|td|tr|div|sec|title|abstract|fig|table|caption|list-item)>",
                  " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


class _Enquirer:
    """The single place that spends the online budget, caches, and counts failures.

    ``max_online_checks`` bounds *every* request (Phrase searches, full texts
    and OpenAlex lookups alike), so an online run cannot fan out. A budget of
    zero means no online work at all — the same reading ``integrity.py`` uses.
    """

    def __init__(self, ctx: object) -> None:
        self.budget = max(0, int(getattr(ctx, "max_online_checks", 10) or 0))
        self.cache = getattr(ctx, "online_cache", None)
        self.used = 0
        self.unreachable = 0
        self.skipped = 0

    def _cached(self, url: str):
        if self.cache is None:
            return None
        return self.cache.get(url)

    def _spend(self) -> bool:
        if self.used >= self.budget:
            self.skipped += 1
            return False
        if self.used:            # pause between requests, not before the first
            time.sleep(_PAUSE)
        self.used += 1
        return True

    def json(self, url: str):
        hit = self._cached(url)
        if hit is not None:
            return hit
        if not self._spend():
            return None, None
        status, obj = net.get_json(url, timeout=_TIMEOUT)
        if not net.is_definitive(status):
            self.unreachable += 1
        if self.cache is not None:
            self.cache[url] = (status, obj)
        return status, obj

    def text(self, url: str):
        hit = self._cached(url)
        if hit is not None:
            return hit
        if not self._spend():
            return None, ""
        status, body = net.get(url, timeout=_TIMEOUT)
        if not net.is_definitive(status):
            self.unreachable += 1
        out = _plain(body) if body else ""
        if self.cache is not None:
            self.cache[url] = (status, out)
        return status, out


def _abstract(doi: str, enq: "_Enquirer") -> str:
    """Reconstructed abstract from OpenAlex, or '' — uses the configured key."""
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    url = f"{_API_OPENALEX}{urllib.parse.quote(doi)}"
    if key:
        url += f"?api_key={urllib.parse.quote(key)}"
    _, data = enq.json(url)
    inv = (data or {}).get("abstract_inverted_index") if isinstance(data, dict) else None
    if not inv:
        return ""
    positions: Dict[int, str] = {}
    for word, spots in inv.items():
        for pos in spots or []:
            positions[pos] = word
    return " ".join(positions[k] for k in sorted(positions))


def _label(meta: Dict) -> str:
    title = (meta.get("title") or "untitled").strip().rstrip(".")
    journal = (meta.get("journalTitle") or meta.get("bookOrReportDetails") or "").strip()
    year = str(meta.get("pubYear") or "").strip()
    cite = " ".join(part for part in (journal, year) if part)
    doi = (meta.get("doi") or "").strip()
    out = f'"{title[:110]}"'
    if cite:
        out += f" — {cite}"
    if doi:
        out += f" (doi:{doi})"
    return out


def _cited(meta: Dict, manuscript: str) -> bool:
    """True when the manuscript already cites this source.

    Reusing a cited source's wording is a quotation, not concealment, so this
    is the difference between INFO and a finding against the author.
    """
    doi = (meta.get("doi") or "").strip().lower()
    if doi and doi in manuscript:
        return True
    title = (meta.get("title") or "").strip().lower().rstrip(".")
    return len(title) > 25 and title[:60] in manuscript


def _finding_for(src: Dict, body: str, manuscript: str, enq: "_Enquirer") -> Finding:
    meta = src["meta"]
    phrases: List[str] = src["phrases"]
    quote = phrases[0]
    label = _label(meta)
    words = body.lower().split()

    # Quantify against the published full text where it is open access, and
    # against the OpenAlex abstract otherwise (which is what a non-OA hit is).
    ratio, run = 0.0, 0
    source_text = ""
    pmcid = meta.get("pmcid")
    doi = (meta.get("doi") or "").strip()
    if pmcid and str(meta.get("isOpenAccess") or "").upper() == "Y":
        _, source_text = enq.text(_API_FULLTEXT.format(pmcid=pmcid))
    elif doi:
        source_text = _abstract(doi, enq)
    if source_text:
        source_words = source_text.lower().split()
        mine = _shingles(words)
        theirs = _shingles(source_words)
        ratio = len(mine & theirs) / max(1, len(mine))
        run = _shared_run(words, source_words, _SHINGLE)

    if _cited(meta, manuscript):
        return Finding(
            "External similarity", Severity.INFO,
            "Wording matches a source this manuscript already cites",
            f"Published wording overlaps with {label}, which this manuscript cites — "
            "consistent with a quotation or a methods description of cited work. "
            "Confirm the citation is present at the point of reuse.",
            f'Manuscript: "{quote[:200]}"',
            "Confirm the source is cited where the wording appears", 0.55)

    if run >= _LONG_MATCH_WORDS:
        severity = Severity.HIGH
        title = "Verbatim passage reused from a published source"
        detail = (f"{run} consecutive words of this manuscript also appear in {label}. "
                  "Text of this length rarely coincides by chance; confirm it is quoted and "
                  "cited, or rewritten in your own words.")
    elif len(phrases) >= 2 or ratio >= _SUSTAINED_RATIO:
        # "Sustained" means volume, not one sentence: either several distinct
        # passages from the same source, or a tenth of the manuscript's phrase
        # set. A single shared sentence is LOW however short the manuscript is.
        severity = Severity.MEDIUM
        title = "Sustained text overlap with a published source"
        detail = (f"{len(phrases)} distinctive passage(s) of this manuscript also occur in "
                  f"{label} ({ratio * 100:.1f}% of the manuscript's 8-word phrases). "
                  "Typical of reworded or recycled text from the same source.")
    else:
        severity = Severity.LOW
        title = "Distinctive text found in a published source"
        detail = (f"A rare sentence of this manuscript occurs verbatim in {label}. "
                  "One sentence is usually shared methods wording or a translated "
                  "formulation; check it is not unattributed reuse.")

    evidence = f'Manuscript: "{quote[:200]}" | Matched: {label}'
    if run:
        evidence += f" | longest identical run: {run} words"
    if ratio:
        evidence += f" | {ratio * 100:.1f}% of manuscript phrases found in this source"
    return Finding("External similarity", severity, title, detail, evidence,
                   "Quote and cite the source, or rewrite the passage in your own words; "
                   "if it is your own prior work, disclose the reuse",
                   0.7 if run else 0.6)


def run(doc: Document, ctx: object) -> List[Finding]:
    if not getattr(ctx, "online", False):
        return []
    body = (doc.body_text or "").strip()
    if len(body.split()) < _MIN_BODY_WORDS:
        return []
    limit = min(_MAX_QUERIES, int(getattr(ctx, "max_online_checks", 10) or 0))
    if limit <= 0:
        return []
    phrases = _distinctive_passages(body, limit)
    if not phrases:
        return []
    enq = _Enquirer(ctx)
    manuscript = (body + " " + " ".join(doc.references or [])).lower()

    sources: Dict[str, Dict] = {}
    common = 0
    for passage in phrases:
        _, data = enq.json(_phrase_url(_query_window(passage)))
        if not isinstance(data, dict):
            continue
        hits = int(data.get("hitCount") or 0)
        if hits == 0:
            continue
        if hits > _BOILERPLATE_HITS:
            common += 1          # shared wording: no information about reuse
            continue
        for result in (data.get("resultList") or {}).get("result", []) or []:
            key = str(result.get("doi") or result.get("pmcid")
                      or result.get("title") or "").lower()
            if not key:
                continue
            sources.setdefault(key, {"meta": result, "phrases": []})["phrases"].append(passage)

    findings: List[Finding] = []
    ranked = sorted(sources.values(), key=lambda s: -len(s["phrases"]))
    for src in ranked[:_MAX_FINDINGS]:
        findings.append(_finding_for(src, body, manuscript, enq))
    if len(ranked) > _MAX_FINDINGS:
        findings.append(Finding(
            "External similarity", Severity.INFO,
            "Further external matches not itemised",
            f"{len(ranked) - _MAX_FINDINGS} more published source(s) share distinctive wording "
            "with this manuscript than are listed above.",
            "; ".join(_label(s["meta"]) for s in ranked[_MAX_FINDINGS:])[:400],
            "Review the full overlap report before submitting", 0.5))

    if enq.unreachable or enq.skipped:
        findings.append(Finding(
            "External similarity", Severity.INFO,
            "External overlap check incomplete",
            "Part of the published-literature comparison could not be completed "
            f"({enq.unreachable} lookup(s) unreachable, {enq.skipped} beyond the online budget). "
            "Absence of a match here is therefore not evidence of originality.",
            f"{enq.used} lookup(s) attempted against Europe PMC / OpenAlex",
            "Re-run online (or raise --max-online-checks) for full coverage", 0.9))

    if not findings:
        findings.append(Finding(
            "External similarity", Severity.INFO,
            "No significant external text overlap found",
            f"{len(phrases)} distinctive passage(s) were looked up in the open-access "
            "literature; none matched a published source closely enough to report."
            + (f" {common} passage(s) were too common to be evidence either way." if common else ""),
            f"Corpus searched: Europe PMC full text, {enq.used} lookup(s)",
            "No action needed", 0.6))
    return findings
