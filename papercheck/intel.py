"""Open-intelligence data layer: local cache of free open-source datasets.

PaperEngine stays local-first and offline-capable. This module manages a
small on-disk cache (default ~/.papercheck, override with PAPERCHECK_HOME)
of two open datasets the engines read:

1. **Tortured phrases** (Problematic Paper Screener, Cabanac et al.).
   A curated built-in list works offline from day one; ``download_phrases``
   refreshes/extends it from a configurable JSON URL (default: the PPS
   project page, overridable with PAPERCHECK_PHRASES_URL).
2. **Retraction Watch database** (CC-BY 4.0 via retractionwatch.com).
   ``rwdb.download_db`` handles this; ``sync_all`` runs both.

Nothing here ever raises on network failure — engines fall back to the
built-in seeds so a check always works offline.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Dict, List, Optional, Tuple

_PPS_PAGE = "https://www.irit.fr/~Guillaume.Cabanac/problematic-paper-screener/tortured/"
_TIMEOUT = 20.0

# ---------------------------------------------------------------------------
# Curated tortured phrases (tortured -> intended). Documented in Cabanac,
# Labbé & Magazinov 2021 and successor papers; kept in code so the engine
# works with zero network access. The downloaded dataset extends this list.
# ---------------------------------------------------------------------------
CURATED_PHRASES: List[Tuple[str, str]] = [
    ("counterfeit consciousness", "artificial intelligence"),
    ("man-made reasoning", "artificial intelligence"),
    ("profound learning", "deep learning"),
    ("deep acquiring", "deep learning"),
    ("deep mastery", "deep learning"),
    ("profound neural networks", "deep neural networks"),
    ("profound neural organisation", "deep neural networks"),
    ("irregular timberland", "random forest"),
    ("irregular woods", "random forest"),
    ("colossal information", "big data"),
    ("neural organization", "neural network"),
    ("neural organisation", "neural network"),
    ("counterfeit neural networks", "artificial neural networks"),
    ("bosom malignancy", "breast cancer"),
    ("bosom disease", "breast cancer"),
    ("malignancy therapy", "cancer therapy"),
    ("lung malignancy", "lung cancer"),
    ("prostate malignancy", "prostate cancer"),
    ("gastric malignancy", "gastric cancer"),
    ("constant infection", "chronic disease"),
    ("constant kidney disease", "chronic kidney disease"),
    ("artery sickness", "artery disease"),
    ("coronary illness", "coronary disease"),
    ("malady mending", "disease curing"),
    ("poisonous substance", "toxic substance"),
    ("logical fallout", "logical fallacy"),
    ("research missing", "research gap"),
]


def cache_dir() -> str:
    env = os.environ.get("PAPERCHECK_HOME")
    base = env if env else os.path.join(os.path.expanduser("~"), ".papercheck")
    os.makedirs(base, exist_ok=True)
    return base


def phrases_cache_path() -> str:
    return os.path.join(cache_dir(), "tortured_phrases.json")


def _parse_phrases(raw: str) -> List[Tuple[str, str]]:
    """Accept JSON of shape {"phrases": [{"tortured": .., "intended": ..}]}
    or a flat list of pairs, or an HTML page containing JSON. Best effort."""
    # try direct JSON first
    candidates = [raw]
    # extract the largest JSON object embedded in HTML if needed
    if "<" in raw[:200]:
        blocks = re.findall(r"\{.*\}|\[.*\]", raw, re.DOTALL)
        blocks.sort(key=len, reverse=True)
        candidates = blocks[:3]
    for blob in candidates:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        pairs: List[Tuple[str, str]] = []
        if isinstance(data, dict):
            data = data.get("phrases") or data.get("tortured") or data
        if isinstance(data, dict):
            # {"tortured phrase": "intended term", ...}
            for k, v in data.items():
                if isinstance(v, str) and v.strip() and v.strip().lower() != k.strip().lower():
                    pairs.append((k.strip().lower(), v.strip().lower()))
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    t = item.get("tortured") or item.get("phrase") or item.get("tortured_phrase")
                    i = item.get("intended") or item.get("intended_term") or item.get("correct")
                    if t and i and str(i).strip().lower() != str(t).strip().lower():
                        pairs.append((str(t).strip().lower(), str(i).strip().lower()))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    t, i = str(item[0]).strip().lower(), str(item[1]).strip().lower()
                    if t and i and i != t:
                        pairs.append((t, i))
        if pairs:
            return pairs
    return []


def download_phrases(url: Optional[str] = None) -> Tuple[bool, int]:
    """Download the tortured-phrases dataset into the local cache.

    Returns (success, phrase_count). Never raises."""
    src = url or os.environ.get("PAPERCHECK_PHRASES_URL") or _PPS_PAGE
    try:
        req = urllib.request.Request(src, headers={"User-Agent": "papercheck/1.9"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
        pairs = _parse_phrases(raw)
        if not pairs:
            return False, 0
        # merge with curated so a partial download never shrinks coverage
        merged = dict(CURATED_PHRASES)
        merged.update(pairs)
        tmp = phrases_cache_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sorted(merged.items()), fh)
        os.replace(tmp, phrases_cache_path())
        return True, len(merged)
    except Exception:
        return False, 0


def load_phrases() -> List[Tuple[str, str]]:
    """Curated + cached tortured phrases. Offline-safe, never raises."""
    pairs = dict(CURATED_PHRASES)
    path = phrases_cache_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                cached = json.load(fh)
            for item in cached:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    t, i = str(item[0]).strip().lower(), str(item[1]).strip().lower()
                    if t and i and i != t:
                        pairs[t] = i
        except Exception:
            pass
    return sorted(pairs.items())


def db_status() -> Dict[str, object]:
    """What's in the local intelligence cache (for --sync-all reporting).

    Memoized on file mtime+size so the GUI can call it per page render
    without re-reading a multi-MB cache file."""
    status: Dict[str, object] = {}
    ppath = phrases_cache_path()
    from . import rwdb as _rwdb
    rpath = _rwdb.default_cache_path()

    def _fkey(p):
        try:
            st = os.stat(p)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    key = (_fkey(ppath), _fkey(rpath))
    cached = _STATUS_CACHE.get(key)
    if cached is not None:
        return dict(cached)

    status["tortured_phrases"] = len(load_phrases())
    status["tortured_phrases_source"] = "curated" if not os.path.isfile(ppath) else "curated+downloaded"
    if os.path.isfile(rpath):
        try:
            with open(rpath, encoding="utf-8") as fh:
                status["retraction_db"] = len(json.load(fh))
            status["retraction_db_source"] = "downloaded"
        except Exception:
            status["retraction_db"] = "corrupt"
            status["retraction_db_source"] = "seeds"
    else:
        status["retraction_db"] = len(_rwdb.load_db())
        status["retraction_db_source"] = "seed list"
    status["cache_dir"] = cache_dir()
    _STATUS_CACHE[key] = dict(status)
    return status


_STATUS_CACHE: Dict[tuple, Dict[str, object]] = {}


def sync_all() -> Dict[str, object]:
    """Refresh both open datasets into the local cache. Never raises."""
    from . import rwdb as _rwdb
    out: Dict[str, object] = {}
    ok, n = download_phrases()
    out["tortured_phrases"] = (f"updated: {n} phrases" if ok
                               else "download failed — curated list still active")
    out["tortured_phrases_ok"] = ok
    out["retraction_watch"] = ("updated" if _rwdb.download_db()
                               else "download failed — seed list still active")
    out.update({k: v for k, v in db_status().items() if k not in out})
    return out
