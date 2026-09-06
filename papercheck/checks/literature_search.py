"""OpenAlex literature search (online): flag similar published work, near-duplicate titles, missing prior work."""
from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def _fetch(url: str, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "papercheck/0.1 (research integrity; mailto:research@example.org)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))

def _title(doc: Document) -> str:
    for p in (doc.paragraphs or [])[:3]:
        if p and len(p.split()) < 25:
            return p.strip()
    return (doc.text or "")[:200]

def run(doc: Document, ctx: object) -> List[Finding]:
    if not getattr(ctx, "online", False):
        return []
    title = _title(doc)
    if not title or len(title.split()) < 3:
        return []
    mailto = getattr(ctx, "mailto", "") or ""
    words = re.sub(r'[^a-z ]', " ", title.lower())
    q = urllib.parse.quote(" ".join(words.split()[:8]))
    url = "https://api.openalex.org/works?search=" + q + "&per-page=6&select=id,title,publication_year,doi,is_retracted"
    if mailto:
        url += "&mailto=" + urllib.parse.quote(mailto)
    try:
        data = _fetch(url)
    except Exception:
        return []
    works = data.get("results", []) if isinstance(data, dict) else []
    out = []
    same = []
    for w in works:
        wt = (w.get("title") or "").lower()
        if not wt:
            continue
        # Near-duplicate title: high token overlap.
        t1 = set(re.findall(r"[a-z]{4,}", wt))
        t2 = set(re.findall(r"[a-z]{4,}", title.lower()))
        if t1 and t2:
            sim = len(t1 & t2) / float(len(t1 | t2))
            if sim >= 0.6:
                same.append((w.get("title"), w.get("publication_year"), w.get("doi"), sim))
    if same:
        for st, yr, doi, sim in same[:4]:
            out.append(Finding("Novelty", Severity.HIGH,
                               "Near-duplicate published work found (OpenAlex)",
                               "A published work shares ~" + str(int(sim * 100)) + "% of its title with yours - duplicate-submission or missing-prior-work risk.",
                               "Title: " + str(st)[:100] + " (" + str(yr) + ") " + (str(doi) or ""), 0.80,
                               "Confirm your manuscript is substantially different and cite this work if it is related"))
    else:
        cited = [w.get("title") for w in works[:2] if w.get("title")]
        out.append(Finding("Novelty", Severity.INFO,
                           "OpenAlex scan: no near-duplicate title found",
                           "Scanned OpenAlex for similar published work; none shares the title. Still verify novelty vs the field.",
                           "Top related: " + ("; ".join(cited[:2]) if cited else "none"), 0.70,
                           "Optionally review the top related works and cite any you build directly on"))
    return out
