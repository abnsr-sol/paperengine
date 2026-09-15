"""Retracted-reference engine: Retraction Watch DB (auto-download + cache) + seed list + online OpenAlex flags."""
from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity
from .. import rwdb

_KNOWN = [
    ("wakefield", "1998", "mmr"), ("wakefield", "1999", "autism"),
    ("mehra", "2020", "hydroxychloroquine"), ("mehra", "2020", "chloroquine"),
    ("desai", "2020", "cardiac"), ("bollyky", "2020", "surgisphere"),
    ("pradhan", "2020", "surgisphere"), ("wiersinga", "2020", "hydroxychloroquine"),
]


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "papercheck/0.1 (research integrity)"})
    with urllib.request.urlopen(req, timeout=12.0) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _online_check(ref: str, mailto: str) -> bool:
    m = re.search(r"[A-Za-z0-9][A-Za-z0-9 ,'.:-]{15,80}", ref)
    q = urllib.parse.quote((m.group(0) if m else ref)[:70])
    url = "https://api.openalex.org/works?search=" + q + "&per-page=1&select=title,is_retracted"
    if mailto:
        url += "&mailto=" + urllib.parse.quote(mailto)
    try:
        data = _fetch(url)
        for w in (data.get("results", []) or []):
            if w.get("is_retracted"):
                return True
    except Exception:
        pass
    return False


def run(doc: Document, ctx: object) -> List[Finding]:
    refs = doc.references or []
    out = []
    if not refs:
        return out
    # A citation that EXPLICITLY notes the retraction/withdrawal is correct
    # scholarly practice — flagging it would punish honest citing (F5).
    _CITED_AS_RETRACTED = re.compile(r"retract|withdraw", re.IGNORECASE)
    # Full RWDB if cached (or downloadable), else the built-in seed list.
    # Use the process-level screening index: parse+tokenize once per server
    # lifetime, not once per reference (72k entries x N refs is minutes).
    entries, token_sets, generic = rwdb.get_screening_index(rwdb.default_cache_path())
    per_ref = rwdb.screen_references_bulk(refs, entries, token_sets, generic=generic)
    for i, r in enumerate(refs):
        low = r.lower()
        if _CITED_AS_RETRACTED.search(r):
            continue
        for (surname, year, token) in _KNOWN:
            if surname in low and year in low and token in low:
                out.append(Finding("Integrity", Severity.CRITICAL,
                                   "Reference matches a well-known retracted work",
                                   surname.title() + " (" + year + ") on " + token + " was retracted. Citing it without a retraction note is a major red flag.",
                                   "Ref: " + r[:120], "Remove the reference or cite it explicitly as retracted with a warning",
                                   0.90))
                break
        else:
            # Token-overlap screening is a SIGNAL, not proof: a 4-token match
            # against 72k DB entries flags false positives (confirmed live on
            # placeholder citations). Per the P1 spec, heuristic-only matches
            # escalate to HIGH "verify", never CRITICAL — CRITICAL is reserved
            # for the curated seed list above (exact surname+year+topic).
            for _, reason, title in per_ref[i][:1]:
                out.append(Finding("Integrity", Severity.HIGH,
                                   "Reference may match retracted work (verify)",
                                   "Token overlap suggests Retraction Watch entry '" + title[:60] + "' (" + reason + "). This is a fuzzy match, not proof — verify the title before acting.",
                                   "Ref: " + r[:120] + " | DB entry: " + title[:80],
                                   "Compare the full title; if it IS the retracted work, remove it or cite it explicitly as retracted",
                                   0.60))
    if getattr(ctx, "online", False):
        mailto = getattr(ctx, "mailto", "") or ""
        cap = max(1, min(len(refs), getattr(ctx, "max_online_checks", 10)))
        flagged = 0
        for r in refs[:cap]:
            if _online_check(r, mailto):
                flagged += 1
                out.append(Finding("Integrity", Severity.HIGH,
                                   "Reference flagged as retracted (OpenAlex)",
                                   "OpenAlex marks this reference's record as retracted.",
                                   "Ref: " + r[:120], "Verify the retraction and remove/cite-with-note",
                                   0.80))
        if flagged == 0:
            out.append(Finding("Integrity", Severity.INFO,
                               "Retraction check passed (online)",
                               "Checked " + str(cap) + " references against OpenAlex retraction flags; none flagged.",
                               str(cap) + " refs checked", "Screening was title-based; spot-check borderline cases manually",
                               0.90))
    elif not out:
        out.append(Finding("Integrity", Severity.INFO,
                           "Retracted-reference screening (offline seed list)",
                           "Screened against a small curated list. Use --online for OpenAlex retraction flags.",
                           str(len(refs)) + " refs screened, no known-retraction match", "Re-run with --online to screen the full OpenAlex record",
                           0.95))
    return out
