"""Predatory/hijacked-journal vetting: Think.Check.Submit checklist + red-flag solicitation signals in the manuscript."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_RED_FLAGS = r'fast\s+(?:track|review|publication)|quick\s+review|guaranteed\s+acceptance|acceptance\s+within\s+\d+\s+(?:days|weeks)|waiv(?:er|ed)\s+(?:fee|apc)|discount\s+on\s+publication'
_INVITATION = r'invited?\s+(?:to|by)|solicit|we\s+are\s+pleased\s+to\s+invite|call\s+for\s+papers|special\s+issue\s+invitation'


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    out = []
    venue = str(getattr(ctx, 'venue', ''))
    rules = getattr(ctx, 'rules', {}) or {}
    publisher = rules.get('publisher', '')

    if re.search(_RED_FLAGS, body, re.IGNORECASE):
        out.append(Finding("Submission", Severity.HIGH,
                           "Venue red flag: fast-track/guaranteed acceptance language",
                           "Phrases promising fast review or guaranteed acceptance are predatory-journal tells.",
                           "Red-flag phrase found in manuscript", "Re-verify the venue with Think.Check.Submit before submitting",
                           0.85))

    if re.search(_INVITATION, body, re.IGNORECASE):
        out.append(Finding("Submission", Severity.MEDIUM,
                           "Submission may originate from an unsolicited invitation",
                           "Manuscript mentions a solicitation/invitation to submit - a common predatory pipeline.",
                           "Invitation language found", "If you were invited via spam email, run the venue through Think.Check.Submit first",
                           0.60))

    # Checklist: remind the researcher what to verify for ANY venue (esp. national/Indian targets).
    missing = []
    if 'issn' not in body.lower():
        missing.append("ISSN verified against issn.org")
    if 'doaj' not in body.lower() and 'directory of open access' not in body.lower():
        missing.append("DOAJ listing (if OA)")
    if 'cope' not in body.lower():
        missing.append("COPE membership")
    if 'apc' not in body.lower() and 'article processing charge' not in body.lower():
        missing.append("APC transparency")
    if missing:
        out.append(Finding("Submission", Severity.INFO,
                           "Venue vetting checklist (Think.Check.Submit)",
                           "Before paying anything or submitting, verify these. Predatory journals cost money, time, and publishability.",
                           "Not verified in manuscript: " + "; ".join(missing), "Check: ISSN (issn.org), DOAJ (if OA), COPE membership, APC transparency, real editorial board, indexed in Scopus/WoS",
                           0.95))

    # Hijack check cue: journal name claiming big-name publisher + regional venue mismatch.
    if publisher and re.search(r'claims?\s+(?:to\s+be|indexed)|scopus|web\s+of\s+science|impact\s+factor', body, re.IGNORECASE):
        out.append(Finding("Submission", Severity.LOW,
                           "Indexing/impact-factor claims - verify them",
                           "Claims of Scopus/WoS indexing or an impact factor should be checked against the official lists (hijacked journals fake these).",
                           "Indexing/IF claim found for venue: " + venue, "Confirm indexing on the official Scopus/Clarivate lists, not the journal's own site",
                           0.70))
    return out
