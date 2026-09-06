"""Paper-mill indicator engine: email-hospital rule, glued email/name artifacts, free-mail density, boilerplate tells."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_FREE_MAIL = r'@(gmail|yahoo|outlook|hotmail|rediff|live|aol|ymail|icloud|protonmail|zoho)\.'
_HOSPITAL = r'hospital|medical\s+(?:college|center|centre|institute)|clinic|health\s+science|nursing|pharm'


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    paras = doc.paragraphs or []
    out = []
    if not body:
        return out
    head = "\n".join(paras[:6]) if paras else body[:4000]

    emails = re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', head)
    free = [e for e in emails if re.search(_FREE_MAIL, e, re.IGNORECASE)]
    # Email-hospital rule: private free-mail + hospital/medical affiliation (85% sensitivity for paper-mill authors).
    if free and re.search(_HOSPITAL, head, re.IGNORECASE):
        out.append(Finding("Integrity", Severity.HIGH,
                           "Paper-mill tell: free-mail addresses with medical affiliation",
                           "The 'email-hospital rule' (free-mail + hospital) flags fabricated paper-mill author blocks in ~85% of confirmed cases.",
                           "Free-mail: " + ", ".join(free[:3]) + " | hospital keywords present", "Verify author identity and affiliation; require institutional emails and ORCID",
                           0.80))

    # Glued email->name (lost line break) - classic copy/paste artifact.
    glued = re.findall(r'@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}([A-Z][a-z]{2,})', body)
    if glued:
        out.append(Finding("Integrity", Severity.MEDIUM,
                           "Author block artifact: email glued to next name",
                           "An email runs directly into the next author's name (lost line break) - a formatting/authoring integrity flag.",
                           "Patterns: " + ", ".join(glued[:4]), "Fix the author block; verify all authors and emails are real and correctly matched",
                           0.90))

    # Free-mail density across authors.
    if len(emails) >= 3 and len(free) / float(len(emails)) > 0.5:
        out.append(Finding("Integrity", Severity.LOW,
                           "Majority free-mail author addresses",
                           "Over half the author emails are consumer addresses; institutional emails are expected.",
                           str(len(free)) + "/" + str(len(emails)) + " free-mail", "Use institutional email addresses and ORCID iDs",
                           0.70))

    # Author count vs email count mismatch.
    name_blocks = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}(?:\s+[A-Z]\.)?(?=\s*[,;]|\s+and\s+|\s*$)', head)
    authorish = [n for n in name_blocks if len(n) < 40 and not re.search(r'abstract|introduction|university|institute', n, re.IGNORECASE)]
    if len(authorish) >= 2 and emails and len(authorish) > len(emails):
        out.append(Finding("Integrity", Severity.MEDIUM,
                           "Author/email count mismatch",
                           "More author names than emails - incomplete or fabricated author block.",
                           str(len(authorish)) + " names vs " + str(len(emails)) + " emails", "Every author needs an affiliation and email (or state why not)",
                           0.65))

    # Boilerplate ethics/contribution tells.
    boiler = sum(1 for pat in [r'all\s+authors\s+(?:contributed|reviewed|approved)',
                               r'no\s+(?:conflict|competing)\s+of?\s+interest',
                               r'data\s+availability\s+statement'] if re.search(pat, body, re.IGNORECASE))
    if boiler == 3:
        out.append(Finding("Integrity", Severity.LOW,
                           "Textbook boilerplate statements",
                           "All three standard statements appear verbatim - fine if true, but paper-mill templates use identical phrasing.",
                           "3/3 boilerplate statements detected", "Ensure statements are accurate for this paper, not pasted from a template",
                           0.40))

    return out
