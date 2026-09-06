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

_RWDB_URL = "https://retractionwatch.com/wp-content/uploads/rwdb.csv"
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
    """Download + normalize the RWDB CSV into `path` as JSON. Returns success."""
    if not path:
        path = default_cache_path()
    try:
        req = urllib.request.Request(_RWDB_URL, headers={"User-Agent": "papercheck/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
        entries = _parse_csv(raw)
        if not entries:
            return False
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entries, fh)
        os.replace(tmp, path)
        return True
    except Exception:
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


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


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
            overlap = len(rt & et)
            # year agreement strengthens a weak overlap
            year = entry.get("year")
            if year and str(year) in ref:
                overlap += 1
            if overlap >= min_overlap:
                hits.append((i, entry.get("reason", "unspecified"), entry.get("title", "")))
                break
    return hits
