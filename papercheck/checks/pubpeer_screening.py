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
from typing import List, Optional
from ..ingestion import Document
from ..risk import Finding, Severity

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;)]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs/)?([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s,;)]+", re.IGNORECASE)

# (pattern, URL prefix, capture group) — a reference line may carry any of them.
_RESOLVABLE = (
    (_DOI_RE, "https://doi.org/", 0),
    (_ARXIV_RE, "https://arxiv.org/abs/", 1),
)


def _candidates(ref_text: str) -> List[str]:
    """Resolvable URLs mentioned in one reference line, order preserved."""
    out: List[str] = []
    for pattern, prefix, group in _RESOLVABLE:
        for m in pattern.finditer(ref_text):
            url = (prefix + m.group(group)).rstrip(".,;)")
            if url not in out:
                out.append(url)
    for m in _URL_RE.finditer(ref_text):
        url = m.group(0).rstrip(".,;)")
        if url not in out:
            out.append(url)
    return out


def _pubpeer_comment_count(doi_url: str):
    """``(count_or_None, checked)`` for a DOI.

    ``checked=False`` means the lookup never produced an answer (throttled,
    blocked, or offline). Absence of a PubPeer thread and failure to ask are
    different facts, and conflating them would hide reduced coverage.
    """
    from ..net import get_json, is_definitive
    quoted = urllib.parse.quote(doi_url, safe="")
    status, body = get_json(f"https://www.pubpeer.com/json/{quoted}", timeout=10.0)
    if not is_definitive(status):
        return None, False
    if isinstance(body, dict):
        for key in ("comment_count", "comments", "count", "n_comments"):
            val = body.get(key)
            if isinstance(val, int):
                return val, True
    return None, True


def run(doc: Document, ctx: object) -> List[Finding]:
    if not ctx or not getattr(ctx, "online", False):
        return []
    # 0 means "do not go online" (as in integrity.py), not "no limit".
    max_checks = getattr(ctx, "max_online_checks", 10)
    if max_checks <= 0 or not doc.references:
        return []
    results: List[tuple] = []
    looked_up = 0
    answered = 0
    for ref in doc.references:
        if looked_up >= max_checks:
            break
        text = (ref or "").strip()
        cands = _candidates(text)
        if not cands:
            continue
        count: Optional[int] = None
        for c in cands:
            if looked_up >= max_checks:
                break
            looked_up += 1
            count, checked = _pubpeer_comment_count(c)
            if checked:
                answered += 1
            if count is not None:
                break
        if count is None:
            continue
        results.append((text or "(untitled reference)", count))

    if not results:
        if looked_up and not answered:
            # Disclose reduced coverage instead of looking like a clean result.
            return [Finding(
                category="References", severity=Severity.INFO,
                title="PubPeer could not be reached - citations not screened",
                detail="Every PubPeer lookup failed at the network layer, so no "
                       "cited work was actually screened for community "
                       "discussion. This is a connectivity result, not a clean "
                       "bill of health.",
                evidence=f"{looked_up} lookup(s) failed, 0 completed",
                action="Re-run with a working connection to screen citations on PubPeer.",
                confidence=0.95,
                source="pubpeer_screening")]
        return []

    threshold = getattr(ctx, "pubpeer_threshold", 2)
    flagged = [(t, c) for t, c in results if c >= threshold]
    if not flagged:
        return []

    flagged.sort(key=lambda x: -x[1])
    summary = "; ".join(f"{t} ({c})" for t, c in flagged[:6])
    return [Finding(
        category="References", severity=Severity.LOW,
        title="References with PubPeer discussion",
        detail="The following cited works have been discussed on PubPeer (a "
               "post-publication peer-review platform). Discussion does not imply "
               "misconduct, but it is a legitimate screening signal - many "
               "retracted or corrected papers were first raised there.",
        evidence=summary + (f" - {len(flagged)} total" if len(flagged) > 6 else ""),
        action="Read the discussion; decide whether the cited work is still "
               "suitable to rely on.",
        confidence=0.55,
        source="pubpeer_screening")]
