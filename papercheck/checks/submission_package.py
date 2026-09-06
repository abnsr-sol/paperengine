"""Submission-package engine: cover-letter artifacts, highlights, running head, package checklist."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_COVER = r'dear\s+(?:editor|professor|dr\.?|sir|madam)|we\s+are\s+(?:pleased|happy|excited)\s+to\s+submit|pleased\s+to\s+submit\s+our|this\s+manuscript\s+has\s+not\s+been\s+(?:published|submitted)|none\s+of\s+the\s+authors\s+have\s+(?:any\s+)?conflict|all\s+authors\s+(?:have\s+)?read\s+and\s+approved'
_HIGHLIGHT = r'highlights?\s*[:\-]|what\s+(?:this\s+paper|we)\s+(?:adds?|offer)|key\s+(?:points|findings|contributions)\s*[:\-]'


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    paras = doc.paragraphs or []
    out = []
    if not body:
        return out
    head = "\n".join(paras[:6]) if paras else body[:3000]

    if re.search(_COVER, head, re.IGNORECASE):
        out.append(Finding("Submission", Severity.HIGH,
                           "Cover-letter text found inside the manuscript",
                           "Cover-letter phrases ('Dear Editor', 'we are pleased to submit') belong in a separate file. Pasting them into the paper is a desk-reject error.",
                           "Cover-letter phrase in first paragraphs", "Remove cover-letter text from the manuscript; keep it as a separate file",
                           0.90))

    if re.search(r'@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\s*(?:\[|\().{0,30}(?:professor|department|hospital|university)', head, re.IGNORECASE):
        out.append(Finding("Submission", Severity.MEDIUM,
                           "Suggested-reviewer block left in manuscript",
                           "Reviewer suggestions/contact details should be in the submission system, not the manuscript.",
                           "Email + title/department pattern near author block", "Move reviewer suggestions to the submission form",
                           0.70))

    if not re.search(_HIGHLIGHT, body, re.IGNORECASE):
        rules = getattr(ctx, 'rules', {}) or {}
        pub = str(rules.get('publisher', ''))
        if 'elsevier' in pub.lower():
            out.append(Finding("Submission", Severity.MEDIUM,
                               "Highlights missing (Elsevier requires 3-5)",
                               "Elsevier submissions need a 'Highlights' list of 3-5 bullet points.",
                               "No Highlights section found", "Add 3-5 highlights (max 85 chars each) as a separate file or section",
                               0.85))

    missing = []
    if not re.search(r'running\s+head|short\s+title', body, re.IGNORECASE):
        missing.append("running head / short title")
    if not re.search(r'graphical\s+abstract', body, re.IGNORECASE):
        missing.append("graphical abstract (if venue requires)")
    if not re.search(r'plain\s+language\s+summary|lay\s+summary', body, re.IGNORECASE):
        missing.append("plain-language summary (if venue requires)")
    if missing:
        out.append(Finding("Submission", Severity.INFO,
                           "Submission-package checklist",
                           "Verify these package items are prepared for upload (they may not belong inside the PDF).",
                           "Not found in manuscript: " + "; ".join(missing), "Prepare: cover letter, suggested reviewers, ORCID links, line numbers, and the items listed",
                           0.90))

    if not re.search(r'\bline\s+number', body, re.IGNORECASE):
        pass  # line numbers are a Word feature, not detectable from extracted text
    return out
