"""PubPeer screening engine.

Screening-only. When --online is set, this engine attempts to look up each
resolvable reference on PubPeer (https://pubpeer.com) and reports any work that
already has community discussion threads. The threshold defaults to 2 threads.

When offline or blocked, the engine is a silent no-op: zero findings, zero
errors, no network traffic.

The default behavior does NOT contact PubPeer — the --online flag must be set
explicitly. That keeps the offline-first promise intact and avoids surprising
network traffic during normal use.
"""
from __future__ import annotations
import re
import urllib.parse
import urllib.request
from typing import List, Optional
from ..ingestion import Document
from ..risk import Finding, Severity

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;)]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs/)?([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s,;)]+", re.IGNORECASE)


def _candidates(ref_text: str) -> List[str]:
    out: List[str] = []
    seen: set = set()
    for m in _DOI_RE.finditer(ref_text):
        doi = "https://doi.org/" + m.group(0).rstrip(".,;)")
        if doi not in seen:
            seen.add(doi)
            out.append(doi)
    for m in _ARXIV_RE.finditer(ref_text):
        arxiv = "https://arxiv.org/abs/" + m.group(1)
        if arxiv not in seen:
            seen.add(arxiv)
            out.append(arxiv)
    for m in _URL_RE.finditer(ref_text):
        url = m.group(0).rstrip(".,;)")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _pubpeer_comment_count(doi_url: str) -> Optional[int]:
    """Comment-thread count for a DOI, or None when it cannot be determined.

    PubPeer's JSON endpoint is tried first; a missing/throttled/blocked response
    yields None so the engine stays silent rather than guessing. Uses the
    shared HTTP layer for consistent retry/backoff behaviour.
    """
    from ..net import fetch_json
    quoted = urllib.parse.quote(doi_url, safe="")
    body = fetch_json(f"https://www.pubpeer.com/json/{quoted}", timeout=10.0)
    if isinstance(body, dict):
        for key in ("comment_count", "comments", "count", "n_comments"):
            val = body.get(key)
            if isinstance(val, int):
                return val
    return None


def run(doc: Document, ctx: object) -> List[Finding]:
    if not ctx or not getattr(ctx, "online", False):
        return []
    max_checks = getattr(ctx, "max_online_checks", 10)
    if not doc.references:
        return []
    results: List[tuple] = []
    checked = 0
    for ref in doc.references:
        if max_checks and checked >= max_checks:
            break
        cands = _candidates(ref.text or "")
        if not cands:
            continue
        count: Optional[int] = None
        for c in cands:
            if max_checks and checked >= max_checks:
                break
            checked += 1
            count = _pubpeer_comment_count(c)
            if count is not None:
                break
        if count is None:
            continue
        results.append((ref.text or "(untitled reference)", count))

    if not results:
        return []

    threshold = getattr(ctx, "pubpeer_threshold", 2)
    flagged = [(t, c) for t, c in results if c >= threshold]
    if not flagged:
        return []

    flagged.sort(key=lambda x: -x[1])
    summary = "; ".join(f"{t} ({c})" for t, c in flagged[:6])
    return [Finding(
        "References", Severity.LOW,
        "References with PubPeer discussion",
        "The following cited works have been discussed on PubPeer (a post-publication peer-review platform). Discussion does not imply misconduct, but it is a legitimate screening signal — many retracted or corrected papers were first raised there.",
        summary + (f" — {len(flagged)} total" if len(flagged) > 6 else ""),
        0.55,
        "Read the discussion; decide whether the cited work is still suitable to rely on.",
        confidence=0.55,
        source="pubpeer_screening")]
