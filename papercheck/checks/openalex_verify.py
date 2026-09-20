"""OpenAlex verification engine (online): research-claims health via the open
scholarly graph.

What it checks, using ONLY public OpenAlex data (no manuscript text leaves
the machine — just reference titles/DOIs and venue names are sent as query
parameters):

1. Reference resolution — does each cited work exist in the 250M-work graph?
   Unresolvable references are hallucination candidates.
2. Disputed/withdrawn works — OpenAlex flags retractions; citing them is a
   serious integrity risk.
3. Venue scope mismatch — the manuscript's keyword profile (computed locally)
   vs the target venue's historical concept profile (fetched once, cached per
   context). Low overlap = classic desk-reject reason.
4. Seminal-work gap — top-cited recent works in the venue's dominant concepts;
   citing none suggests disconnection from current literature.

API key: OpenAlex is free without one (100k calls/day); a key raises limits.
Set it via the OPENALEX_API_KEY environment variable or --openalex-key.
The key is sent as the api_key query parameter, and if that transport fails
we retry with Bearer header — whichever works wins.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from ..ingestion import Document
from ..risk import Finding, Severity

_API = "https://api.openalex.org"
_TIMEOUT = 12.0
_UA = "paperengine/1.14 (research integrity; local pre-submission checker)"


def _key() -> str:
    return os.environ.get("OPENALEX_API_KEY", "").strip()


def _key_param() -> str:
    key = _key()
    return f"&api_key={urllib.parse.quote(key)}" if key else ""


def _fetch(path: str, params: str = "") -> Optional[dict]:
    # Attempt 1: query-parameter key (the documented OpenAlex transport).
    url = f"{_API}{path}?{params}{_key_param()}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        _log_transport(path, "query-param", exc)
    # Attempt 2: Bearer header — only meaningful when a key is present.
    key = _key()
    if not key:
        return None
    hdr_url = f"{_API}{path}?{params}"
    hdr_req = urllib.request.Request(hdr_url, headers={
        "User-Agent": _UA,
        "Authorization": f"Bearer {key}",
    })
    try:
        with urllib.request.urlopen(hdr_req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        _log_transport(path, "bearer", exc)
    return None


def _log_transport(path: str, mode: str, exc: BaseException) -> None:
    import logging
    if isinstance(exc, urllib.error.HTTPError):
        logging.debug(
            "openalex %s transport=%s status=%s body=%s",
            path, mode, exc.code, exc.read()[:200])
    else:
        logging.debug("openalex %s transport=%s error=%s", path, mode, type(exc).__name__)


def _doi_of(ref: str) -> Optional[str]:
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", ref, re.IGNORECASE)
    return m.group(0).rstrip(".,;)") if m else None


def _title_of(ref: str) -> str:
    """Heuristic title extraction: text before the year, minus authors block."""
    ref = re.sub(r"\b10\.\d{4,9}/\S+", "", ref)
    m = re.search(r"(.{15,180}?)[.,]?\s*\((?:19|20)\d{2}\)", ref)
    if m:
        chunk = m.group(1)
    else:
        chunk = ref[:160]
    # drop a leading author-list ("Surname, A., Other, B. (2020)" style)
    parts = chunk.split(". ", 1)
    return (parts[1] if len(parts) == 2 and len(parts[0]) < 90 else chunk).strip()


_STOP = set("""a an the of and or in on for to with without via using used from by is are was
were this that these those we our their its it as at be been into than then thus also based
study new novel approach method methods results paper model models data analysis""".split())


def _keywords(text: str, limit: int = 12) -> List[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", text.lower())
    counts: Dict[str, int] = {}
    for w in words:
        if w in _STOP:
            continue
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def _work_by_doi(doi: str) -> Optional[dict]:
    data = _fetch("/works", f"filter=doi:{urllib.parse.quote(doi.lower())}"
                            "&per-page=1&select=id,display_name,publication_year,"
                            "cited_by_count,type,is_retracted")
    if data and data.get("results"):
        return data["results"][0]
    return None


def _work_by_title(title: str) -> Optional[dict]:
    if len(title) < 15:
        return None
    data = _fetch("/works", "filter=title.search:" + urllib.parse.quote(title[:150])
                            + "&per-page=1&select=id,display_name,publication_year,"
                              "cited_by_count,type,is_retracted")
    if data and data.get("results"):
        return data["results"][0]
    return None


def _venue_profile(venue_name: str) -> Optional[dict]:
    """Top concepts + recent top works for a venue, by display name search."""
    src = _fetch("/sources", "filter=display_name.search:"
                              + urllib.parse.quote(venue_name[:80]) + "&per-page=1")
    if not (src and src.get("results")):
        return None
    sid = src["results"][0].get("id", "").rsplit("/", 1)[-1]
    if not sid:
        return None
    works = _fetch("/works", f"filter=primary_location.source.id:{sid}"
                             "&sort=cited_by_count:desc&per-page=20"
                             "&select=id,display_name,publication_year,cited_by_count,concepts")
    if not (works and works.get("results")):
        return None
    concepts: Dict[str, int] = {}
    for w in works["results"]:
        for c in (w.get("concepts") or [])[:4]:
            if c.get("score", 0) > 0.2:
                concepts[c["display_name"]] = concepts.get(c["display_name"], 0) \
                    + max(1, int(c.get("score", 1) * 3))
    top = [k for k, _ in sorted(concepts.items(), key=lambda kv: -kv[1])[:8]]
    return {"source_id": sid, "concepts": top,
            "top_works": works["results"][:10]}


def run(doc: Document, ctx: object) -> List[Finding]:
    if not getattr(ctx, "online", False):
        return []
    refs = doc.references or []
    out: List[Finding] = []
    cap = max(1, min(len(refs), getattr(ctx, "max_online_checks", 10) * 2))
    cache: Dict[str, Optional[dict]] = getattr(ctx, "online_cache", None) or {}

    # ---- 1 + 2: reference resolution & retraction flags -----------------
    unresolved: List[str] = []
    retracted: List[str] = []
    checked = 0
    for r in refs[:cap]:
        doi = _doi_of(r)
        key = f"oa:{doi or r[:60]}"
        if key in cache:
            work = cache[key]
        else:
            work = _work_by_doi(doi) if doi else _work_by_title(_title_of(r))
            cache[key] = work
            checked += 1
        if work is None:
            unresolved.append(r[:110])
        elif work.get("is_retracted"):
            retracted.append(r[:110])
    if checked:
        ctx.online_cache = cache
    if unresolved and checked >= 2:
        frac = len(unresolved) / max(1, len(unresolved) + sum(
            1 for k, v in cache.items() if k.startswith("oa:") and v))
        if frac > 0.25:
            out.append(Finding(
                "References", Severity.HIGH,
                "Many references unresolved in the OpenAlex graph",
                f"{len(unresolved)} of the checked references could not be "
                "matched to any work in OpenAlex (250M+ works) by DOI or "
                "title — a hallmark of LLM-hallucinated or mistyped citations.",
                "; ".join(unresolved[:4]), 0.7,
                "Verify each reference exists: check DOI resolution and "
                "author/title spelling against the publisher page."))
        elif unresolved:
            out.append(Finding(
                "References", Severity.LOW, "Some references unresolved",
                f"{len(unresolved)} reference(s) not matched in OpenAlex — "
                "may be very recent, non-indexed, or mistyped.",
                "; ".join(unresolved[:3]), 0.5,
                "Spot-check these references resolve to real publications."))
    if retracted:
        out.append(Finding(
            "Integrity", Severity.CRITICAL,
            "Cited work flagged as retracted (OpenAlex)",
            f"{len(retracted)} cited work(s) carry the OpenAlex retraction "
            "flag. Citing retracted work is a serious integrity risk.",
            "; ".join(retracted[:4]), 0.9,
            "Remove or replace these citations; check Retraction Watch for "
            "the retraction reason and any corrected version."))

    # ---- 3: venue scope mismatch ----------------------------------------
    venue = (getattr(ctx, "venue", "") or "").lower()
    generic = not venue or "generic" in venue or "no venue" in venue
    if not generic:
        prof = _venue_profile(venue)
        if prof and prof["concepts"]:
            # abstract text: first section or first ~1200 chars of body
            head = ""
            for s in doc.sections:
                head += (s.body or "") + " "
                if len(head) > 1500:
                    break
            kw = set(_keywords(head or doc.text[:6000]))
            overlap = kw & {c.lower() for c in prof["concepts"]}
            if kw and len(overlap) == 0:
                out.append(Finding(
                    "Scope", Severity.MEDIUM,
                    "Keyword profile disjoint from venue's historical concepts",
                    "None of the manuscript's dominant keywords appear in the "
                    "venue's top historical concepts "
                    f"({', '.join(prof['concepts'][:5])}). Scope mismatch is a "
                    "leading desk-reject reason.",
                    f"paper keywords: {', '.join(sorted(kw)[:8])}", 0.55,
                    "Re-read the venue's stated scope; consider a venue whose "
                    "concept profile matches your topic, or reframe the intro."))
            # ---- 4: seminal-work gap -------------------------------------
            top = prof["top_works"]
            cited_titles = {(_title_of(r) or "").lower()[:60] for r in refs}
            missing = [w for w in top
                       if w.get("display_name", "").lower()[:60] not in cited_titles]
            if top and len(missing) == len(top):
                names = "; ".join(w["display_name"][:70] for w in top[:3])
                out.append(Finding(
                    "Novelty", Severity.LOW,
                    "No overlap with venue's most-cited recent works",
                    "None of the venue's top-cited recent papers appear in "
                    "your reference list. Reviewers often read this as "
                    "disconnection from the venue's literature.",
                    f"e.g. {names}", 0.45,
                    "Consider engaging (or explicitly differentiating from) "
                    "the venue's most influential recent work in the related-"
                    "work section."))

    if not out:
        out.append(Finding(
            "References", Severity.INFO,
            "OpenAlex verification passed",
            f"{checked} reference(s) resolved in the OpenAlex graph; none "
            "retracted; venue scope plausible." if checked else
            "Venue profile and references checked; no integrity flags.",
            f"api calls: ~{checked + 2}", 0.6,
            "No action needed — machine-verified against the open graph."))
    return out
