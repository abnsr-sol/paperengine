"""Retraction Watch database (RWDB) integration.

On first use, tries to download the public Retraction Watch database CSV
(via the Crossref-hosted mirror) and cache it as JSON. If the download fails
or `PAPERCHECK_RWDB` points at a local export, falls back to a built-in seed
list so screening always works offline.

The RWDB is published under CC-BY 4.0 by Crossref / Retraction Watch.
See: https://retractionwatch.com/the-retraction-watch-database/
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.request
from typing import List, Optional

# The Retraction Watch database moved to Crossref hosting (Crossref acquired
# it in 2023; bulk file served from Crossref Labs). Keep fallbacks in case
# the primary moves again.
_RWDB_URLS = (
    "https://api.labs.crossref.org/data/retractionwatch",      # primary (verified 2026-09)
    "https://retractionwatch.com/wp-content/uploads/rwdb.csv",  # legacy
    "https://api.crossref.org/works?filter=has-retraction:true&rows=1000&select=DOI,title,issued",  # last-resort API slice
)
# Cap the raw download at 64 MB — the full RWDB CSV is ~60-80 MB; the
# token-overlap screen never needs more than a large prefix of it.
_MAX_BYTES = 64 * 1024 * 1024
_TIMEOUT = 20.0

# (surname, year, token) triples: the historically most-cited retractions.
_SEED = [
    {"title": "wakefield mmr autism lancet", "year": 1998, "reason": "fraud"},
    {"title": "wakefield rett syndrome autism", "year": 1999, "reason": "fraud"},
    {"title": "mehra hydroxychloroquine covid surgisphere", "year": 2020, "reason": "data integrity"},
    {"title": "mehra chloroquine covid surgisphere", "year": 2020, "reason": "data integrity"},
    {"title": "desai cardiovascular outcomes surgisphere", "year": 2020, "reason": "data integrity"},
    {"title": "bollyky hydroxychloroquine surgisphere", "year": 2020, "reason": "data integrity"},
    {"title": "pradhan sars-cov-2 hiv-like insertions", "year": 2020, "reason": "methodology"},
    {"title": "wiersinga hydroxychloroquine covid", "year": 2020, "reason": "data integrity"},
    {"title": "schon superconductivity papers", "year": 2002, "reason": "fabrication"},
    {"title": "stapel social psychology priming", "year": 2011, "reason": "fabrication"},
    {"title": "hauser cognition rhesus monkey", "year": 2010, "reason": "data problems"},
    {"title": "carlo croce cancer genetics", "year": 2024, "reason": "multiple concerns"},
    {"title": "lu cervical cancer hela contamination", "year": 2002, "reason": "contamination"},
    {"title": "cass cell membrane current", "year": 2011, "reason": "misconduct"},
]


def default_cache_path() -> str:
    env = os.environ.get("PAPERCHECK_RWDB")
    if env:
        return env
    return os.path.join(tempfile_dir(), "papercheck_rwdb.json")


def tempfile_dir() -> str:
    import tempfile
    return tempfile.gettempdir()


def load_db(path: Optional[str] = None) -> List[dict]:
    """Load the retraction DB from cache/disk, else fall back to seeds.

    Never raises: a missing/corrupt cache silently yields the seed list.
    """
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return [dict(e) for e in _SEED]


def download_db(path: Optional[str] = None) -> bool:
    """Download + normalize the RWDB CSV into `path` as JSON. Returns success.

    Tries each mirror in turn; a large DB is capped at a sane parse size so a
    multi-hundred-MB CSV cannot exhaust memory (tail is as informative as
    the head for token-overlap screening of a manuscript's reference list)."""
    if not path:
        path = default_cache_path()
    for url in _RWDB_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "papercheck/1.9"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                raw = resp.read(_MAX_BYTES).decode("utf-8", "replace")
            entries = _parse_csv(raw)
            if not entries:
                continue
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(entries, fh)
            os.replace(tmp, path)
            return True
        except Exception:
            continue
    return False


def _parse_csv(raw: str) -> List[dict]:
    out: List[dict] = []
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        title = (row.get("Title") or row.get("title") or "").strip()
        if not title:
            continue
        try:
            year = int(re.search(r"(19|20)\d{2}", row.get("RetractionDate", "") or row.get("RetractionPubDate", "") or "").group(0))
        except Exception:
            year = None
        reason = (row.get("RetractionReason") or row.get("Reason") or "").strip()[:120]
        out.append({"title": title.lower(), "year": year, "reason": reason})
    return out


# Academic stopword filter: token overlap is only evidence when it shares
# DISTINCTIVE words. Generic filler ("for", "models", "system") plus the
# year bonus otherwise collides legit references with same-year DB entries
# sharing only common words (the v1.9.0 benchmark false positive).
_STOPWORDS = frozenset(
    """for and the with using based from into over under between among via
    their this that these those its our model models method methods approach
    approaches system systems analysis novel framework frameworks study
    performance based new improved effective efficient algorithm algorithms
    data results paper research are was were has have had not but can could
    may might will would shall should one two three four five six ten""".split())


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower())
            if t not in _STOPWORDS}


# Process-level screening index: (mtime, size) -> (entries, token_sets).
# Parsing a 16 MB JSON and tokenizing 72k titles per *check* is the single
# biggest hot-path cost once the real DB is downloaded; this cache pays it
# once per server/CLI lifetime instead.
_INDEX_CACHE: dict = {}


def get_screening_index(path: Optional[str] = None):
    """Return (entries, token_sets) for the DB at `path`, cached by mtime.

    Falls back to the seed list (also cached) when no file exists. The
    token_sets list parallels `entries` so screening never re-tokenizes."""
    if not path:
        path = default_cache_path()
    key = None
    if path and os.path.isfile(path):
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    cached = _INDEX_CACHE.get(path)
    if cached and cached[0] == key:
        return cached[1], cached[2]
    entries = load_db(path)
    token_sets = [_tokens(e.get("title", "")) for e in entries]
    _INDEX_CACHE[path] = (key, entries, token_sets)
    return entries, token_sets


def screen_references_bulk(refs: List[str], entries: List[dict],
                           token_sets: Optional[List[set]] = None,
                           min_overlap: int = 4) -> List[List[tuple]]:
    """Screen many references against a pre-tokenized DB efficiently.

    Returns, for each ref, a list of (ref_index, reason, db_title) hits
    (at most one per ref — first match wins, same as screen_references).
    """
    if token_sets is None:
        token_sets = [_tokens(e.get("title", "")) for e in entries]
    per_ref: List[List[tuple]] = [[] for _ in refs]
    for i, ref in enumerate(refs):
        rt = _tokens(ref)
        if not rt:
            continue
        for j, et in enumerate(token_sets):
            if not et:
                continue
            # Two ways to be evidence of the same work:
            #  1) >=min_overlap distinctive tokens (long titles), or
            #  2) 3+ tokens covering >=50% of a short DB title
            #     (e.g. 3 of 4 tokens in 'wakefield mmr autism lancet').
            # A generic same-year collision shares few of MANY tokens and
            # fails the coverage test (the v1.9.0 benchmark false positive).
            overlap = len(rt & et)
            if overlap >= min_overlap or (
                    overlap >= 3 and overlap * 2 >= len(et)):
                per_ref[i] = [(i, entries[j].get("reason", "unspecified"),
                               entries[j].get("title", ""))]
                break
    return per_ref


def screen_references(refs: List[str], db: List[dict], min_overlap: int = 4) -> List[tuple]:
    """Return [(ref_index, reason, db_title), ...] for references whose tokens
    overlap a DB entry's title by >= min_overlap significant tokens."""
    hits: List[tuple] = []
    for i, ref in enumerate(refs):
        rt = _tokens(ref)
        if not rt:
            continue
        for entry in db:
            et = _tokens(entry.get("title", ""))
            if not et:
                continue
            # Same dual rule as screen_references_bulk.
            overlap = len(rt & et)
            if overlap >= min_overlap or (
                    overlap >= 3 and overlap * 2 >= len(et)):
                hits.append((i, entry.get("reason", "unspecified"), entry.get("title", "")))
                break
    return hits
