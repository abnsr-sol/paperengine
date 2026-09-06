"""Author info engine: affiliations, equal-contribution footnote, author-name formatting, corresponding-author marking."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Author Info", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    head = text[:3000]
    low = head.lower()
    out = []
    # affiliations: superscript-style or 'Department of' lines
    has_affil = re.search(r"department|university|institute|college|school of|laborator", low)
    if not has_affil:
        out.append(_f(Severity.MEDIUM, "No institutional affiliation detected", "Every author needs a current institutional affiliation; editors verify them.",
                      "No affiliation keywords in the first page", 0.75, "Add affiliations (department, institution, city, country) for all authors"))
    # corresponding author marked
    if re.search(r"email|@", low) and not re.search(r"corresponding", low):
        out.append(_f(Severity.LOW, "Email present but corresponding author not marked", "Journals require the corresponding author to be explicitly identified.",
                      "Email found, no 'corresponding' marker", 0.70, "Mark the corresponding author with an asterisk and a footnote"))
    # equal contribution
    n_authors = len(re.findall(r"and\s+[A-Z][a-z]+,?\s|,\s*[A-Z][a-z]+\s+[A-Z][a-z]+", head))
    if n_authors >= 3 and not re.search(r"equal(?:ly)?\s+contribut|contributed\s+equally|joint\s+first", low):
        out.append(_f(Severity.LOW, "Many authors without equal-contribution note", "For large teams, journals expect a note on whether the first two authors contributed equally.",
                      str(n_authors) + " authors detected, no equal-contribution note", 0.50, "Add an equal-contribution footnote if applicable"))
    # initials-only author names
    initials_only = re.findall(r"\b[A-Z]\.\s*[A-Z]\.\s*(?:[A-Z][a-z]+)", head)
    if len(initials_only) >= 2:
        out.append(_f(Severity.LOW, "Authors listed as initials only", "Most journals require full given names, not initials.",
                      "Found: " + ", ".join(initials_only[:4]), 0.60, "Expand initials to full given names"))
    return out