"""Reference completeness engine: missing year/volume/pages, secondary-source citations ('as cited in')."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Ref Completeness", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    refs = doc.references or []
    if not refs:
        return []
    out = []
    n = len(refs)
    no_year = [i for i, r in enumerate(refs) if not re.search(r"(?:19[5-9]\d|20[0-3]\d)", r)]
    if n >= 5 and len(no_year) / n > 0.3:
        out.append(_f(Severity.MEDIUM, "Many references missing a year", str(len(no_year)) + " of " + str(n) + " references contain no year; incomplete metadata frustrates verification.",
                      "Refs without year: " + str([i + 1 for i in no_year[:8]]), 0.85, "Complete the year for every reference"))
    no_vol = [i for i, r in enumerate(refs) if not re.search(r"\b(?:vol|volume|v)\.?\s*\d+|\b\d+\s*\(\d+\)|\b\d+,\s*no\.?\s*\d+", r, re.IGNORECASE) and not re.search(r"arxiv|preprint|doi\.org|http", r, re.IGNORECASE)]
    if n >= 8 and len(no_vol) / n > 0.5:
        out.append(_f(Severity.LOW, "Many references missing volume/issue", str(len(no_vol)) + " of " + str(n) + " journal-style references lack volume/issue data.",
                      str(len(no_vol)) + " refs without volume info", 0.60, "Add volume(issue) and page range to journal references"))
    no_pages = [i for i, r in enumerate(refs) if not re.search(r"\b\d+\s*[-–]\s*\d+\b|:\s*\d+|p+p?\.\s*\d+", r)]
    if n >= 8 and len(no_pages) / n > 0.6:
        out.append(_f(Severity.LOW, "Many references missing page numbers", str(len(no_pages)) + " of " + str(n) + " references lack page ranges.",
                      str(len(no_pages)) + " refs without pages", 0.55, "Add page ranges (or article numbers) to references"))
    # secondary citations: 'as cited in' / 'cited by' — reviewing the primary source is expected
    body = doc.body_text or doc.text or ""
    secondary = re.findall(r"as\s+cited\s+in\s+[A-Z][a-zA-Z]+(?:\s+et\s+al\.?)?\s*,?\s*\(?(\d{4})", body, re.IGNORECASE)
    if len(secondary) >= 2:
        out.append(_f(Severity.MEDIUM, "Secondary-source citations ('as cited in')", str(len(secondary)) + " citations borrow via another paper; reviewers expect the primary source.",
                      "Years in secondary cites: " + ", ".join(secondary[:5]), 0.80, "Find, read, and cite the original sources directly"))
    return out