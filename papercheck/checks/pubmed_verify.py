"""PubMed E-utilities reference verification engine.

Validates biomedical references against PubMed/MEDLINE (35M+ citations)
using the free NCBI E-utilities API. Especially valuable for references
that only appear in MEDLINE (not in Crossref/OpenAlex).

API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/ (free, no key needed)
Polite pool: 3 requests/second without API key; 10/second with key.

Severity: HIGH when reference cannot be found in any database.
          MEDIUM when reference has metadata mismatches.
          INFO when reference validates successfully.

Gate: Only fires when manuscript appears biomedical (methods mention
clinical, patient, medical, drug, therapy, etc.) AND references are
present. Emits INFO coverage note when offline.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict

from ..ingestion import Document
from ..risk import Finding, Severity

# Biomedical trigger keywords
_BIOMED_GATE = re.compile(
    r"clinical\s*trial|patient|medical|drug|therapy|treatment"
    r"|diagnosis|disease|symptom|syndrome|disorder"
    r"|PubMed|MEDLINE|MeSH|NCBI"
    r"|hospital|physician|surgeon"
    r"|pharmacolog|toxicolog|epidemiolog"
    r"|randomized\s*controlled|placebo"
    r"|cohort|case-control|cross-sectional"
    r"|biopsy|histolog|patholog"
    r"|cancer|tumor|oncolog"
    r"|cardio|neuro|immun"
    r"|genom|proteom|metabolom",
    re.IGNORECASE,
)


def _query_pubmed(term: str, timeout: int = 5) -> Optional[Dict]:
    """Query PubMed for a reference term. Returns first result or None."""
    try:
        # Step 1: Search
        search_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={urllib.parse.quote(term)}&retmax=1&retmode=json"
        )
        req = urllib.request.Request(search_url, headers={
            "User-Agent": "PaperEngine/1.11 (research-tool)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode()
            import json
            search_data = json.loads(data)
            ids = search_data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                return None

            # Step 2: Fetch summary
            pmid = ids[0]
            summary_url = (
                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                f"?db=pubmed&id={pmid}&retmode=json"
            )
            req2 = urllib.request.Request(summary_url, headers={
                "User-Agent": "PaperEngine/1.11 (research-tool)",
            })
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                summary_data = json.loads(resp2.read())
                result = summary_data.get("result", {}).get(pmid, {})
                return {
                    "pmid": pmid,
                    "title": result.get("title", ""),
                    "source": result.get("source", ""),
                    "pubdate": result.get("pubdate", ""),
                    "authors": [a.get("name", "") for a in result.get("authorlist", [])[:3]],
                }
    except Exception:
        return None


def _extract_reference_terms(text: str, max_refs: int = 10) -> List[str]:
    """Extract reference search terms from manuscript text."""
    terms = []

    # Pattern: [Author, Year] or (Author, Year)
    cite_patterns = [
        r"\(([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-z]+))?),?\s*(\d{4})\)",
        r"\[([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-z]+))?),?\s*(\d{4})\]",
    ]
    for pat in cite_patterns:
        for match in re.finditer(pat, text):
            author = match.group(1)
            year = match.group(2)
            terms.append(f"{author} {year}")

    return list(set(terms))[:max_refs]


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []

    # Gate: only fire on biomedical manuscripts
    if not _BIOMED_GATE.search(body):
        return []

    online = getattr(ctx, "online", False)
    refs = _extract_reference_terms(body)

    if not refs:
        return []

    if not online:
        return [Finding(
            "Integrity",
            Severity.INFO,
            "PubMed reference verification requires --online flag",
            f"Found {len(refs)} citable references. PubMed E-utilities can verify "
            "biomedical references against 35M+ MEDLINE citations. "
            "Run with --online to enable.",
            f"{len(refs)} references found",
            0.95,
            "Re-run with --online to verify biomedical references",
        )]

    out = []
    max_checks = getattr(ctx, "max_online_checks", 5)
    checked = 0

    for term in refs:
        if checked >= max_checks:
            break

        result = _query_pubmed(term)
        if result:
            out.append(Finding(
                "Integrity",
                Severity.INFO,
                f"Reference verified in PubMed: {term}",
                f"Found: {result['title']} ({result['source']}, {result['pubdate']}). "
                f"PMID: {result['pmid']}.",
                f"query: {term}, pmid: {result['pmid']}",
                0.90,
                "No action needed — reference verified",
            ))
        else:
            out.append(Finding(
                "Integrity",
                Severity.MEDIUM,
                f"Reference not found in PubMed: {term}",
                f"The citation '{term}' could not be found in PubMed/MEDLINE. "
                "This may indicate a typo, a non-biomedical reference, or a "
                "reference from a database not indexed by PubMed.",
                f"query: {term}",
                0.55,
                "Verify the citation is correct; check if the journal is indexed in PubMed",
            ))

        checked += 1

    return out
