"""Crossref deep verification (online): resolve each reference, flag hallucinated entries and year/volume/issue mismatches."""
from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "papercheck/0.1 (research integrity; mailto:research@example.org)"})
    with urllib.request.urlopen(req, timeout=12.0) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _claimed_year(ref: str):
    m = re.search(r'\b(19\d{2}|20\d{2})\b', ref)
    return int(m.group(1)) if m else None


def _claimed_vol(ref: str):
    m = re.search(r'\bvol(?:ume)?\.?\s*(\d+)', ref, re.IGNORECASE)
    if not m:
        m = re.search(r';(\d+)\(', ref)
    return m.group(1) if m else None


def _claimed_pages(ref: str):
    m = re.search(r'[:;]\s*(\d{1,4}(?:[-â€“]\d{1,4})?)', ref)
    return m.group(1) if m else None


def run(doc: Document, ctx: object) -> List[Finding]:
    if not getattr(ctx, "online", False):
        return []
    refs = doc.references or []
    if not refs:
        return []
    out = []
    cap = max(1, min(len(refs), getattr(ctx, "max_online_checks", 10)))
    mailto = getattr(ctx, "mailto", "") or ""
    checked = 0
    for r in refs[:cap]:
        m = re.search(r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+', r, re.IGNORECASE)
        if m:
            doi = m.group(0).rstrip(".,;)")
            try:
                data = _fetch("https://api.crossref.org/works/" + urllib.parse.quote(doi))
                item = data.get("message", {})
                checked += 1
                cy = _claimed_year(r)
                ay = None
                for k in ("published-print", "published-online", "issued"):
                    if item.get(k, {}).get("date-parts"):
                        ay = item[k]["date-parts"][0][0]
                        break
                if cy and ay and cy != ay:
                    out.append(Finding("References", Severity.MEDIUM,
                                       "Reference year mismatch vs Crossref (" + str(cy) + " vs " + str(ay) + ")",
                                       "The year in your reference list differs from the Crossref record - verification flag.",
                                       "Ref: " + r[:90], "Correct the year to " + str(ay),
                                       0.85))
            except Exception:
                out.append(Finding("References", Severity.HIGH,
                                   "DOI does not resolve in Crossref",
                                   "The DOI in this reference could not be found - a classic hallucinated/fake reference signal.",
                                   "Ref: " + r[:90], "Verify the DOI; if the paper does not exist, remove the reference",
                                   0.85))
            continue
        q = urllib.parse.quote(re.sub(r'[^a-z0-9 ]', " ", r[:80]))
        url = "https://api.crossref.org/works?query.bibliographic=" + q + "&rows=1&select=title,DOI,volume,issue,page,issued"
        if mailto:
            url += "&mailto=" + urllib.parse.quote(mailto)
        try:
            data = _fetch(url)
            items = (data.get("message", {}) or {}).get("items", [])
        except Exception:
            continue
        if not items:
            out.append(Finding("References", Severity.HIGH,
                               "Reference not found in Crossref (possible hallucination)",
                               "No Crossref record matched this reference's bibliographic query.",
                               "Ref: " + r[:90], "Verify the paper exists (author, title, year); remove it if it does not",
                               0.70))
            continue
        checked += 1
        item = items[0]
        cy = _claimed_year(r)
        ay = None
        for k in ("published-print", "published-online", "issued"):
            if item.get(k, {}).get("date-parts"):
                ay = item[k]["date-parts"][0][0]
                break
        if cy and ay and abs(cy - ay) > 1:
            out.append(Finding("References", Severity.MEDIUM,
                               "Reference year mismatch vs Crossref (" + str(cy) + " vs " + str(ay) + ")",
                               "The listed year is off by more than a year from the Crossref record.",
                               "Ref: " + r[:90], "Correct the year to " + str(ay),
                               0.80))
    if checked == 0:
        out.append(Finding("References", Severity.INFO,
                           "Crossref verification skipped",
                           "No references were resolvable for online verification this run.",
                           "checked=0 of " + str(len(refs)), "Add DOIs to references for full verification",
                           0.90))
    return out
