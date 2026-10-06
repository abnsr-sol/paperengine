#!/usr/bin/env python3
"""Refresh the bundled offline datasets from free, public, auto-updating sources.

The package ships snapshots so it stays 100% offline at run time; this script
is the *write-back* path that keeps those snapshots fresh. It is safe to run
anywhere: if a source is unreachable the existing snapshot is kept untouched and
the run is reported as a warning (exit 0) rather than a failure.

    python scripts/refresh_data.py              # refresh every dataset
    python scripts/refresh_data.py --check      # probe sources only, write nothing
    python scripts/refresh_data.py --only hijacked_journals
    python scripts/refresh_data.py --strict     # exit 1 if any source fails

Datasets
--------
hijacked_journals
    Retraction Watch Hijacked Journal Checker, published as a public Google
    Sheet. Exported as CSV (~460 entries). Replaces the hand-maintained
    20-entry seed in ``papercheck/data/venue_intel.json``.

retracted_articles
    Crossref retraction notices (``filter=update-type:retraction``).
    ~75k retraction notices mapped back to the original retracted DOI.
    Powers the ``retracted_refs`` engine offline instead of relying on
    the 8-entry seed that was previously bundled.

Every run rewrites ``papercheck/data/manifest.json`` with per-dataset
``last_updated`` / ``count`` / ``source`` so the freshness of bundled data is
auditable, in the same spirit as ``venues.RULES_LAST_VERIFIED``.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "papercheck", "data")
INTEL_PATH = os.path.join(DATA_DIR, "venue_intel.json")
RETRACTIONS_PATH = os.path.join(DATA_DIR, "retractions.json")
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")

UA = {"User-Agent": "papercheck-refresh/1.0 (+https://github.com/abnsr-sol/paperengine)"}
TIMEOUT = 45

# Retraction Watch Hijacked Journal Checker — public Google Sheet.
# The /gviz/tq?tqx=out:csv form is the reliable export endpoint; the
# /export?format=csv form returns HTTP 400 for this document.
_RW_SHEET_ID = "1ak985WGOgGbJRJbZFanoktAN_UFeExpE"
_RW_GID = "364865985"
HIJACK_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{_RW_SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&gid={_RW_GID}"
)
HIJACK_SOURCE = "Retraction Watch Hijacked Journal Checker"

# Crossref — retraction notices indexed with update-type:retraction.
# Cursor pagination is required for deep result sets (>10k).
# A 3-year sliding window keeps the bundle size sane (~55k entries,
# ~4-5 MB) while covering the vast majority of citations in new manuscripts.
_CROSSREF_SINCE = "2023-01-01"
CROSSREF_RETRACTION_URL = (
    "https://api.crossref.org/works"
    "?filter=update-type:retraction,from-update-date:{since}"
    "&select=DOI,update-to"
    "&rows=1000"
    "&cursor={cursor}"
    "&mailto=papercheck@localhost"
)
CROSSREF_SOURCE = "Crossref (update-type:retraction)"
CROSSREF_TIMEOUT = 90  # Crossref is slow; single pages can take 30-40s


def _fetch(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def normalize_title(title: str) -> str:
    """Must stay byte-identical to venue_hijack._normalize_title."""
    return re.sub(r"[^a-z0-9\s]", "", (title or "").lower().strip())


def _split_issns(cell: str) -> list[str]:
    """'1941-6520,  1941-6067' -> ['1941-6520', '1941-6067']."""
    out = []
    for part in re.split(r"[,;/\s]+", cell or ""):
        part = part.strip().upper()
        if re.fullmatch(r"\d{4}-\d{3}[\dX]", part) and part not in out:
            out.append(part)
    return out


def fetch_hijacked_journals() -> list[dict]:
    """Parse the Retraction Watch hijack sheet into venue_intel entries."""
    raw = _fetch(HIJACK_CSV_URL).decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(raw)))

    entries: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) < 5:
            continue
        # The sheet opens with two prose header rows; data rows start with an
        # integer index in column 0.
        if not row[0].strip().isdigit():
            continue
        hijacked_title = (row[1] or "").strip()
        if not hijacked_title:
            continue
        title_norm = normalize_title(hijacked_title)
        if not title_norm or title_norm in seen:
            continue
        seen.add(title_norm)
        issns = _split_issns(row[3] if len(row) > 3 else "")
        original = (row[4] or "").strip()
        entry = {
            "title": hijacked_title,
            "title_norm": title_norm,
            "issn": issns[0] if issns else None,
            "issns": issns,
            "clone_of": original or "unknown legitimate journal",
            "hijacked_url": (row[2] or "").strip() or None,
            "source": HIJACK_SOURCE,
        }
        entries.append(entry)
    return entries


def fetch_retracted_articles(check_only: bool = False, max_pages: int = 200) -> list[dict]:
    """Pull retraction notices from Crossref and map them to original DOIs.

    Crossref indexes ~75k retraction notices. Each notice carries an
    ``update-to`` array that points back to the original retracted work.
    We flatten that into a compact lookup table:
        {doi: <original>, retraction_doi: <notice>, retraction_date: <str>}

    Cursor pagination is used; ``max_pages`` caps runtime at ~200 pages
    (200k records, well above the current ~75k total).

    When ``check_only`` is True only the first page is fetched so the probe
    finishes in a few seconds.
    """
    entries: list[dict] = []
    seen_dois: set[str] = set()
    cursor = "*"
    page = 0

    while cursor and page < max_pages:
        url = CROSSREF_RETRACTION_URL.format(cursor=cursor)
        raw = _fetch(url, timeout=CROSSREF_TIMEOUT).decode("utf-8", "replace")
        data = json.loads(raw)
        msg = data.get("message", {})
        items = msg.get("items", [])

        for item in items:
            notice_doi = item.get("DOI", "").lower().strip()
            updates = item.get("update-to", [])
            for upd in updates:
                if upd.get("type") != "retraction":
                    continue
                orig = (upd.get("DOI") or "").lower().strip()
                if not orig or orig in seen_dois:
                    continue
                seen_dois.add(orig)
                # Extract date from updated struct if available
                date_parts = upd.get("updated", {}).get("date-parts", [[]])
                date_str = "-".join(str(p) for p in date_parts[0]) if date_parts and date_parts[0] else None
                entries.append({
                    "doi": orig,
                    "retraction_doi": notice_doi,
                    "retraction_date": date_str,
                    "source": upd.get("source", "publisher"),
                })

        if check_only:
            # One page is enough to prove the source is alive
            break

        next_cursor = msg.get("next-cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        page += 1
        # Polite delay between pages (polite pool allows faster pacing)
        time.sleep(0.2)

    return entries


DATASETS = {
    "hijacked_journals": fetch_hijacked_journals,
    "retracted_articles": fetch_retracted_articles,
}


def _load_json(path: str, default: dict) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def refresh(only: str | None, check_only: bool, strict: bool) -> int:
    names = [only] if only else sorted(DATASETS)
    unknown = [n for n in names if n not in DATASETS]
    if unknown:
        print(f"Unknown dataset(s): {', '.join(unknown)}")
        print(f"Available: {', '.join(sorted(DATASETS))}")
        return 2

    intel = _load_json(INTEL_PATH, {})
    manifest = _load_json(MANIFEST_PATH, {"datasets": {}})
    manifest.setdefault("datasets", {})
    failures: list[str] = []

    for name in names:
        before = len(intel.get(name, []) or [])
        try:
            fetcher = DATASETS[name]
            # Pass check_only to fetchers that support it
            if name == "retracted_articles":
                fetched = fetcher(check_only=check_only)
            else:
                fetched = fetcher()
        except Exception as exc:  # noqa: BLE001 — offline must never be fatal
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            failures.append(name)
            continue

        print(f"  OK    {name}: fetched {len(fetched)} entries (bundled: {before})")
        if check_only:
            continue
        if not fetched:
            print(f"        refusing to overwrite {name} with an empty result")
            failures.append(name)
            continue

        intel[name] = fetched
        _source_map = {
            "hijacked_journals": HIJACK_SOURCE,
            "retracted_articles": CROSSREF_SOURCE,
        }
        manifest["datasets"][name] = {
            "count": len(fetched),
            "last_updated": _now(),
            "source": _source_map.get(name, "unknown"),
        }

    if not check_only and not failures:
        intel.setdefault("_meta", {})
        intel["_meta"]["last_refreshed"] = _now()
        _write_json(INTEL_PATH, intel)
        _write_json(MANIFEST_PATH, manifest)
        print(f"\nWrote {os.path.relpath(INTEL_PATH, ROOT)} and "
              f"{os.path.relpath(MANIFEST_PATH, ROOT)}")

    if failures:
        print(f"\n{len(failures)} dataset(s) not refreshed: {', '.join(failures)}")
        return 1 if strict else 0
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="refresh a single dataset by name")
    ap.add_argument("--check", action="store_true", help="probe sources, write nothing")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any source fails")
    args = ap.parse_args()

    print("Refreshing bundled datasets from free public sources")
    print("=" * 60)
    return refresh(args.only, args.check, args.strict)


if __name__ == "__main__":
    sys.exit(main())
