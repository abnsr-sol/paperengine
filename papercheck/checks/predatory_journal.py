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
    # Only fire venue vetting checklist when a journal is mentioned AND has predatory signals
    # Don't fire on every paper just because ISSN/DOAJ/COPE aren't mentioned (they rarely are)
    has_journal_mention = re.search(r'journal|proceedings|review|transactions|letters', body, re.IGNORECASE)
    has_predatory_signal = re.search(
        r'accepted\s+(?:within|in)\s+\d+\s+(?:hours|days)|guaranteed\s+(?:publication|acceptance)|'
        r'quick\s+peer\s+review|submit\s+(?:now|today)|no\s+peer\s+review\s+fee|APC\s+(?:waived|free)',
        body, re.IGNORECASE
    )
    if missing and (has_predatory_signal or (has_journal_mention and len(missing) >= 3)):
        out.append(Finding("Submission", Severity.MEDIUM,
                           "Venue vetting recommended (Think.Check.Submit)",
                           "Some venue metadata could not be verified from the manuscript. Before paying or submitting, verify the journal.",
                           "Not verified: " + "; ".join(missing), "Check: ISSN (issn.org), DOAJ (if OA), COPE membership, APC transparency",
                           0.60))

    # Hijack check cue: journal name claiming big-name publisher + regional venue mismatch.
    if publisher and re.search(r'claims?\s+(?:to\s+be|indexed)|scopus|web\s+of\s+science|impact\s+factor', body, re.IGNORECASE):
        out.append(Finding("Submission", Severity.LOW,
                           "Indexing/impact-factor claims - verify them",
                           "Claims of Scopus/WoS indexing or an impact factor should be checked against the official lists (hijacked journals fake these).",
                           "Indexing/IF claim found for venue: " + venue, "Confirm indexing on the official Scopus/Clarivate lists, not the journal's own site",
                           0.70))
    return out
