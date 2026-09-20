"""Citation-fraud engine: self-citation ratio, publisher/reference stacking, reciprocal citation rings."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_FREE_MAIL = r'@(gmail|yahoo|outlook|hotmail|rediff|live|aol|ymail|icloud)\.'


def _author_surnames(doc: Document) -> List[str]:
    """Best-effort surnames from the author block (paragraph with names + email/orcid or short comma list)."""
    names = []
    for p in (doc.paragraphs or [])[:4]:
        if re.search(r'@|orcid', p, re.IGNORECASE) or (len(p.split(',')) >= 2 and len(p) < 300):
            for part in re.split(r'[,;]', p):
                part = part.strip()
                m = re.match(r'^([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+){0,2})', part)
                if m and not re.search(r'@|orcid|university|institute|college|department|email', part, re.IGNORECASE):
                    surname = part.split()[-1] if part.split() else ""
                    if surname and len(surname) > 1 and surname.lower() not in ("of", "the", "and", "for"):
                        names.append(surname.lower())
            if names:
                break
    return names


def _ref_author(ref: str) -> str:
    """First token before comma = surname (IEEE/APA refs)."""
    m = re.match(r'^\s*([A-Za-z\'\-]+)', ref)
    return m.group(1).lower() if m else ""


def run(doc: Document, ctx: object) -> List[Finding]:
    refs = doc.references or []
    body = doc.body_text or doc.text or ""
    out = []
    if not refs:
        return out

    surnames = _author_surnames(doc)
    if len(surnames) >= 2:
        self_cites = [r for r in refs if _ref_author(r) in surnames]
        ratio = len(self_cites) / float(len(refs))
        if ratio > 0.30:
            out.append(Finding("Citation Integrity", Severity.HIGH,
                               "Excessive self-citation (" + str(len(self_cites)) + "/" + str(len(refs)) + " = " + str(int(ratio * 100)) + "%)",
                               "Self-citation above 30% is treated as citation manipulation by COPE and can cost a journal its impact factor.",
                               "Author surnames: " + ", ".join(surnames[:5]) + " | matching refs: " + str(len(self_cites)),
                               "Trim self-citations to what is genuinely required; cite the field, not just your own work", 0.85))
        elif ratio > 0.20:
            out.append(Finding("Citation Integrity", Severity.MEDIUM,
                               "High self-citation ratio (" + str(int(ratio * 100)) + "%)",
                               "Self-citation above ~20% attracts scrutiny from editors and Clarivate.",
                               "Matching refs: " + str(len(self_cites)) + " of " + str(len(refs)), "Review whether each self-citation is necessary",
                               0.75))

    # Reciprocal rings: refs A-cites-B and B-cites-A within the same list (first-author surnames).
    authors_in_refs = [_ref_author(r) for r in refs]
    pairs = set()
    for i in range(len(refs)):
        a = authors_in_refs[i]
        if not a:
            continue
        for j in range(i + 1, len(refs)):
            b = authors_in_refs[j]
            if not b or a == b:
                continue
            if (b, a) in pairs:
                pass
            pairs.add((a, b))
    # Detect A..B and B..A adjacency among top-level refs (weak but cheap signal).
    ring = []
    for i in range(len(refs) - 1):
        a, b = authors_in_refs[i], authors_in_refs[i + 1]
        if a and b and re.search(r'\b' + re.escape(b) + r'[^,]{0,60}' + re.escape(a), refs[i + 1] + refs[i], re.IGNORECASE):
            if (a, b) not in ring and (b, a) not in ring:
                ring.append((a, b))
    if len(ring) >= 3:
        out.append(Finding("Citation Integrity", Severity.MEDIUM,
                           "Possible reciprocal-citation ring pattern",
                           "Several consecutive reference pairs cite each other's first authors - a known citation-ring signal.",
                           "Adjacent reciprocal pairs: " + str(ring[:4]), "Verify the citations are substantive, not mutual-padding",
                           0.55))

    # Publisher/reference stacking: one source dominating the list (heuristic on identical journal token).
    from collections import Counter
    jrn = []
    for r in refs:
        m = re.search(r'\b(?:IEEE\s+Trans|Nature|Science|Lancet|BMJ|PLoS|MDPI|Elsevier|Springer|arXiv)\b', r, re.IGNORECASE)
        if m:
            jrn.append(m.group(0).lower())
    if jrn:
        top, cnt = Counter(jrn).most_common(1)[0]
        if cnt / float(len(refs)) > 0.5:
            out.append(Finding("Citation Integrity", Severity.MEDIUM,
                               "Reference list dominated by one source (" + top + ")",
                               "More than half the references share one venue/publisher token - low citation diversity.",
                               top + " in " + str(cnt) + "/" + str(len(refs)) + " refs", "Diversify sources; a single-venue reference list signals stacking or narrow coverage",
                               0.65))

    # Coercive-citation tell: reference list heavy in the target venue's own journal.
    # Editors pressuring authors to add citations to their own journal is a documented
    # integrity problem (COPE guidance). A submission whose reference list cites the
    # target venue far above field-normal rates reads as coercion compliance - and
    # editors notice it during triage. Flag it so the author can trim to what is
    # genuinely substantive before submission.
    venue_raw = str(getattr(ctx, 'venue', '') or '')
    rules = getattr(ctx, 'rules', None) or {}
    venue_label = venue_raw if venue_raw and venue_raw != 'generic' else str(rules.get('_name', '') or '')
    venue_label = venue_label.replace('_', ' ').replace('-', ' ').strip().lower()
    if venue_label and venue_label != 'generic' and len(refs) >= 10:
        # Word-boundary match so short tokens ("acm") cannot hit inside unrelated
        # words ("Macmillan"); multi-word labels ("ieee access") still substring-match.
        pattern = re.compile(r'\b' + re.escape(venue_label) + r'\b') if ' ' not in venue_label else None
        if pattern is not None:
            venue_cites = [r for r in refs if pattern.search(r.lower())]
        else:
            venue_cites = [r for r in refs if venue_label in r.lower()]
        cnt = len(venue_cites)
        if cnt >= 3:
            ratio = cnt / float(len(refs))
            if ratio >= 0.35:
                sev, conf = Severity.HIGH, 0.75
            elif ratio >= 0.18:
                sev, conf = Severity.MEDIUM, 0.65
            else:
                sev = None
            if sev is not None:
                out.append(Finding("Citation Integrity", sev,
                                   "Reference list heavy in the target venue (" + str(cnt) + "/" + str(len(refs)) + " = " + str(int(ratio * 100)) + "%)",
                                   "Far more citations to the target venue than field-normal rates signal coercive-citation compliance (editors requesting citations to their own journal - a COPE-flagged practice) or venue-stacking. Editors increasingly screen for this during triage.",
                                   venue_label + " cited in " + str(cnt) + " of " + str(len(refs)) + " refs; e.g. " + (venue_cites[0][:80] if venue_cites else ""),
                                   "Keep only venue citations that are genuinely indispensable; a bloated venue share invites a manipulation query before review even starts",
                                   conf))
    return out
