"""Batch mode: scan a folder of manuscripts, produce a comparison CSV ranked
by readiness score.

    python -m papercheck --batch papers/ --venue ugc_care --format csv --out summary.csv

For every supported manuscript in the folder, runs all engines and records:
file, venue, standard, readiness score, per-severity counts, and the top
findings (highest severity/confidence first) for a quick triage view.
"""
from __future__ import annotations

import csv
import os
from typing import List, Optional

from .checks import ALL_ENGINES, CheckContext
from .ingestion import (Document, PdfExtractionError, UnsupportedFormatError,
                        load_document)
from .risk import RiskReport
from .venues import describe, get_rules


def _top_findings(report: RiskReport, n: int = 3) -> str:
    ranked = report.by_severity()
    parts = []
    for f in ranked[:n]:
        parts.append(f"{f.severity.value}: {f.title}")
    return " | ".join(parts)


def scan_folder(folder: str, venue: str, online: bool = False,
                mailto: str = "", max_online: int = 10) -> List[dict]:
    """Run every engine over every supported file in `folder`.

    Returns a list of row dicts sorted by readiness score ascending (worst
    first). Files that fail to parse are reported with readiness=-1 and an
    error note in the top-findings column.
    """
    rules = get_rules(venue)
    ctx = CheckContext(venue=describe(venue), rules=rules, online=online,
                       mailto=mailto, max_online_checks=max_online)
    rows: List[dict] = []
    for name in sorted(os.listdir(folder)):
        full = os.path.join(folder, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in (".docx", ".txt", ".md", ".markdown", ".tex", ".pdf"):
            continue
        row = {
            "file": name,
            "venue": venue,
            "readiness": -1,
            "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
            "findings": 0,
            "top_findings": "",
        }
        try:
            doc = load_document(full)
            report = RiskReport(document_name=doc.name, venue=describe(venue))
            report.stats = {"words": doc.word_count}
            for engine in ALL_ENGINES:
                report.extend(engine(doc, ctx))
            counts = report.counts()
            row["readiness"] = report.readiness_score
            row["critical"] = counts.get("Critical", 0)
            row["high"] = counts.get("High", 0)
            row["medium"] = counts.get("Medium", 0)
            row["low"] = counts.get("Low", 0)
            row["info"] = counts.get("Info", 0)
            row["findings"] = len(report.findings)
            row["top_findings"] = _top_findings(report)
        except (UnsupportedFormatError, PdfExtractionError) as exc:
            row["top_findings"] = f"parse error: {exc}"
        except Exception as exc:  # noqa: BLE001 - batch must survive one bad file
            row["top_findings"] = f"error: {exc}"
        rows.append(row)
    rows.sort(key=lambda r: r["readiness"])
    return rows


def write_csv(rows: List[dict], out_path: str) -> None:
    if not rows:
        raise ValueError("no rows to write")
    fieldnames = ["file", "venue", "readiness", "critical", "high", "medium",
                  "low", "info", "findings", "top_findings"]
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_console_table(rows: List[dict]) -> str:
    if not rows:
        return "No supported manuscripts found."
    lines = [
        f"{'file':<32} {'score':>5} {'crit':>4} {'high':>4} {'med':>4} {'low':>4}  top findings",
        "-" * 100,
    ]
    for r in rows:
        score = r["readiness"] if r["readiness"] >= 0 else "ERR"
        lines.append(
            f"{r['file'][:31]:<32} {score!s:>5} {r['critical']:>4} {r['high']:>4} "
            f"{r['medium']:>4} {r['low']:>4}  {r['top_findings'][:60]}"
        )
    lines.append("-" * 100)
    lines.append("Sorted worst-first. Score is informational, not a verdict.")
    return "\n".join(lines)
