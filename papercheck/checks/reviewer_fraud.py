"""Reviewer-fraud pattern engine: fake-reviewer tells in suggested-reviewer blocks (self-review, free-mail, conflicts)."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_FREE = r'@(gmail|yahoo|outlook|hotmail|rediff|live|aol|ymail|icloud|protonmail|qq|163)\.'
_REV_BLOCK = r'suggested?\s+reviewers?|potential\s+reviewers?|reviewers?\s*(?:list|block|suggestions?)|recommended?\s+reviewers?'


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    head = "\n".join((doc.paragraphs or [])[:10]) if doc.paragraphs else body[:6000]
    out = []
    if not re.search(_REV_BLOCK, body, re.IGNORECASE):
        return out

    # Emails that appear inside / right after a reviewer block.
    idx = re.search(_REV_BLOCK, body, re.IGNORECASE)
    block = body[idx.start(): idx.start() + 1500] if idx else ""
    rev_emails = re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', block)
    auth_emails = set(re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', head))
    if not rev_emails:
        return out

    free = [e for e in rev_emails if re.search(_FREE, e, re.IGNORECASE)]
    if len(free) / float(len(rev_emails)) > 0.5:
        out.append(Finding("Integrity", Severity.HIGH,
                           "Suggested reviewers mostly on free-mail",
                           "Fake-reviewer networks use consumer email addresses; >50% free-mail is a strong tell.",
                           "Free-mail reviewers: " + ", ".join(free[:4]), "Suggest reviewers with institutional emails, verified via their publications",
                           0.80))

    same = [e for e in rev_emails if e in auth_emails]
    if same:
        out.append(Finding("Integrity", Severity.CRITICAL,
                           "Suggested reviewer shares the authors' email",
                           "A suggested reviewer email matches the authors' own email - self-review fraud pattern.",
                           "Email: " + same[0], "Remove this suggestion; reviewer suggestions must be independent of the authors",
                           0.95))

    auth_domains = {e.split("@")[1].lower() for e in auth_emails if "@" in e}
    conflict = [e for e in rev_emails if e.split("@")[1].lower() in auth_domains]
    if conflict:
        out.append(Finding("Integrity", Severity.MEDIUM,
                           "Suggested reviewers share the authors' email domain",
                           "Reviewers from the same institution/domain as the authors create an obvious conflict of interest.",
                           "Shared domain: " + conflict[0].split("@")[1], "Suggest reviewers from different institutions/domains",
                           0.75))

    if len(rev_emails) < 3:
        out.append(Finding("Submission", Severity.LOW,
                           "Very few suggested reviewers",
                           "Most venues expect 3-5 qualified reviewer suggestions.",
                           str(len(rev_emails)) + " suggested", "Provide 3-5 reviewers with stated expertise, no conflicts",
                           0.65))
    return out
