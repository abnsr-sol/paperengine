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


def _format_bibtex_entry(ref: str, index: int) -> str:
    """Convert a reference string to a BibTeX entry."""
    # Try to extract author, year, title
    # Pattern: [Author, Year] Title. Journal, Volume, Pages.
    author_match = re.match(r"\[([^\]]+)\]", ref)
    author = author_match.group(1) if author_match else f"Author{index}"

    year_match = re.search(r"\b(19|20)\d{2}\b", ref)
    year = year_match.group(0) if year_match else "2024"

    # Generate a citation key
    last_name = author.split(",")[0].strip().split()[-1] if author else f"ref{index}"
    key = f"{last_name.lower()}{year}_{index}"

    # Clean up the reference text
    clean_ref = ref.strip()
    if clean_ref.startswith("["):
        clean_ref = clean_ref[clean_ref.index("]") + 1:].strip()
    if clean_ref.endswith("."):
        clean_ref = clean_ref[:-1]

    return (
        f"@article{{{key},\n"
        f"  author = {{{author}}},\n"
        f"  title = {{{clean_ref}}},\n"
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
