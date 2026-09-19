"""BibTeX export engine.

After running reference verification, this engine generates a corrected
BibTeX file with verified references for direct import into Zotero, Mendeley,
or LaTeX documents. This is a utility engine that produces a supplementary
output file, not a finding.

The export is triggered by --format bibtex or --export-bibtex FILE.

This engine itself returns no findings — it's a post-processing step.
The actual export logic lives in the CLI layer.
"""
from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity


def _parse_reference(ref: str) -> dict:
    """Parse a real-world numbered reference into author/title/year parts.

    Handles the common IEEE-ish shapes:
      [1] K. Author, "Cloud computing for big data analytics," IEEE
          Transactions..., 2021.
      2. J. Doe and A. Smith, Title without quotes. Journal, 2019.
    """
    clean = re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", ref.strip())

    year_m = re.search(r"\b(?:19|20)\d{2}\b", clean)
    year = year_m.group(0) if year_m else ""

    # Title: the first quoted segment (straight or curly quotes).
    title_m = re.search(r'["\u201c]([^"\u201d]{8,300})["\u201d]', clean)
    if title_m:
        title = title_m.group(1).strip().rstrip(",").strip()
        author = clean[:title_m.start()].strip().rstrip(",").strip()
    else:
        # No quotes: author is the leading comma-separated phrase, title is
        # the remainder up to the first period (best effort).
        head, sep, tail = clean.partition(",")
        author = head.strip()
        title = tail.strip().split(".")[0].strip() if sep else ""

    return {"author": author, "title": title, "year": year}


def _format_bibtex_entry(ref: str, index: int) -> str:
    """Convert a reference string to a BibTeX entry."""
    parts = _parse_reference(ref)
    author = parts["author"] or f"Author{index}"
    title = parts["title"] or re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", ref.strip())
    year = parts["year"] or "n.d."

    # Citation key: last author token + year, letters/digits only.
    last_name = re.split(r"\s+(?:and|&)\s+|,", author)[0].strip().split()[-1] \
        if author else f"ref{index}"
    safe_name = re.sub(r"[^A-Za-z0-9]", "", last_name).lower() or f"ref{index}"
    safe_year = re.sub(r"[^0-9]", "", year) or "nd"
    key = f"{safe_name}{safe_year}_{index}"

    return (
        f"@article{{{key},\n"
        f"  author = {{{author}}},\n"
        f"  title = {{{title}}},\n"
        f"  year = {{{year}}}\n"
        f"}}"
    )


def generate_bibtex(references: List[str]) -> str:
    """Generate a BibTeX file from a list of references."""
    entries = []
    for i, ref in enumerate(references, 1):
        if ref.strip():
            entries.append(_format_bibtex_entry(ref, i))
    return "\n\n".join(entries)


def run(doc: Document, ctx: object) -> List[Finding]:
    """This engine produces no findings — it's a utility for export."""
    return []
