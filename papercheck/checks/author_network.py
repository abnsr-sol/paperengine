"""Author-network engine (corpus-aware): recurring teams, duplicate identities, salami-slicing author+content overlap."""
from __future__ import annotations
import re
from collections import Counter
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _surnames(doc: Document) -> List[str]:
    names = []
    for p in (doc.paragraphs or [])[:4]:
        if re.search(r'@|orcid', p, re.IGNORECASE) or (len(p.split(',')) >= 2 and len(p) < 300):
            for part in re.split(r'[,;]', p):
                part = part.strip()
                m = re.match(r'^([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+){0,2})', part)
                if m and not re.search(r'@|orcid|university|institute|college|department|email', part, re.IGNORECASE):
                    surname = part.split()[-1]
                    if surname and len(surname) > 1 and surname.lower() not in ("of", "the", "and", "for"):
                        names.append(surname.lower())
            if names:
                break
    return names


def _emails(doc: Document) -> List[str]:
    head = "\n".join((doc.paragraphs or [])[:6]) if doc.paragraphs else (doc.text or "")[:4000]
    return re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', head)


def _sig(doc: Document) -> set:
    return {w for w in re.findall(r"[a-z][a-z'-]{3,}", (doc.body_text or doc.text or "").lower())}


def run(doc: Document, ctx: object) -> List[Finding]:
    corpus = getattr(ctx, "corpus", []) or []
    out = []
    if not corpus:
        return out
    mine = set(_surnames(doc))
    me = _emails(doc)

    # Recurring author teams across the corpus.
    team_counter = Counter()
    for c in corpus:
        names = tuple(sorted(set(_surnames(c))))
        if names:
            team_counter[names] += 1
    for team, count in team_counter.most_common(3):
        if count >= 3:
            out.append(Finding("Integrity", Severity.MEDIUM,
                               "Recurring author team in corpus (" + str(count) + " docs)",
                               "The same author set appears in multiple documents in your corpus - expected for a research group, but a paper-mill/team signature if the content is near-identical.",
                               "Team: " + ", ".join(t.title() for t in team[:4]), "Confirm these are legitimate distinct studies, not sliced publications",
                               0.55))

    # Same email under different names across corpus + this document.
    email_names = {}
    for e in me:
        for n in set(mine):
            email_names.setdefault(e, set()).add(n)
    for c in corpus:
        for e in _emails(c):
            for n in set(_surnames(c)):
                email_names.setdefault(e, set()).add(n)
    for e, names in email_names.items():
        if len(names) >= 2:
            out.append(Finding("Integrity", Severity.HIGH,
                               "Duplicate author identity (same email, different names)",
                               "One email address is attached to " + str(len(names)) + " different author names across the corpus - fake-identity or paper-mill signal.",
                               "email " + e + " -> " + ", ".join(sorted(names)[:4]), "Verify author identities; each person should have one stable name + ORCID",
                               0.75))

    # Salami-slicing: heavy author overlap + heavy content overlap with a corpus doc.
    my_sig = _sig(doc)
    if my_sig:
        for c in corpus:
            shared_authors = len(mine & set(_surnames(c)))
            csig = _sig(c)
            if not csig:
                continue
            overlap = len(my_sig & csig) / float(len(my_sig | csig))
            if shared_authors >= 2 and overlap >= 0.5:
                out.append(Finding("Integrity", Severity.HIGH,
                                   "Author+content overlap with corpus document (salami-slicing risk)",
                                   "This manuscript shares authors AND ~" + str(int(overlap * 100)) + "% of its vocabulary with a corpus document - redundant/sliced publication risk.",
                                   "Corpus doc: " + c.name + " | shared authors: " + str(shared_authors), "Disclose the related work and ensure this manuscript is substantially new (typically 30-50%+ new content)",
                                   0.70))
                break
    return out
