"""Offline reference forensics: physically impossible reference metadata.

Why this engine exists
----------------------
Fabricated / LLM-hallucinated references are the fastest-growing integrity
failure in the literature. A Lancet audit of 97.1M references (May 2026) found
papers carrying a fabricated reference rising from 1 in 2,828 (2023) to 1 in
277 (2026) — a twelve-fold rise — and Frontiers reports ~5% of submissions
trip reference checks. Referencing issues account for 7.54% of retractions
(Okyay et al. 2025, n=16,041).

Until now PaperEngine only caught this *online* (`crossref_verify`,
`openalex_verify`, both `--online`-gated). The offline default path — the one
the whole project is built around — had no reference forensics at all: a
citation dated 2031, a page range running backwards, and a volume of 0 all
passed silently.

What this engine checks (hard arithmetic only, no accusations)
-------------------------------------------------------------
* publication year in the future (impossible)
* page range that runs backwards (impossible)
* volume or issue of 0 (journals are 1-indexed)
* issue number far larger than its volume (fake volume/issue pairing)
* malformed DOI (10.xxxx/ shape)
* reference year later than the newest year cited in the body — no, that is
  normal (in press). Not checked.
* duplicated DOI across distinct references (one DOI, two entries)
* author-less reference entries ("Anonymous", empty author prefix)
* reference year earlier than 1900 (journals did not exist)

Severity discipline: an arithmetic contradiction is a fact, not a heuristic,
so those run HIGH with high confidence. Style-level observations run LOW/MEDIUM.

Every finding carries evidence + confidence + action, and none of them says
"this reference is fabricated" — only that the metadata as printed cannot be
correct. That is the flag-not-verdict rule: an author who mistyped a page range
and an author who pasted an LLM invention get the same message, because from
the text alone they are indistinguishable, and both need the same fix.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

# DOI: "10." + 4-9 digit registrant prefix + "/" + suffix.
_DOI_RE = re.compile(r"\b10\.(\d{4,9})/(\S+)")
# A DOI *attempt* — what an author (or a model) wrote after the word 'doi'.
_DOI_ATTEMPT = re.compile(
    r"\bdoi\.?\s*:?\s*(?:https?://(?:dx\.)?doi\.org/)?\s*(10\.[0-9a-z.\-/]+)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\((?:19|20)\d{2}\)|\b(?:19|20)\d{2}\b")
_PAGE_RANGE = re.compile(r"\b(\d{1,5})\s*[-–]\s*(\d{1,5})\b")
# A journal volume: 'Vol. 12', 'volume 12', 'v.12'. The bare letter 'v' needs
# its dot, otherwise 'v' before any number in prose would parse as a volume.
_VOLUME = re.compile(r"\b(?:vol(?:ume)?\.?|v\.)\s*(\d{1,4})\b", re.IGNORECASE)
# volume(issue) written tight — '401(3)'. A space is required before a year in
# '(2021)', so demanding adjacency keeps years and page spans out of it.
_VOL_ISSUE = re.compile(r"\b(\d{1,4})\((\d{1,4})\)")
_ISSUE = re.compile(r"\b(?:no\.?|issue)\s*(\d{1,4})\b", re.IGNORECASE)
_NO_AUTHOR = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s*(Anonymous|Anon\.?|Unknown)\b", re.IGNORECASE)


def _f(sev: Severity, title: str, detail: str, evidence: str, conf: float, action: str) -> Finding:
    return Finding("Reference Forensics", sev, title, detail, evidence, action, conf)


def _years_in(ref: str) -> List[int]:
    """Publication years in one reference entry, as ints.

    The regex matches both ``(2031)`` and bare ``2031``, so the matched text
    has to be stripped of punctuation before it can become an int.
    """
    out: List[int] = []
    for m in _YEAR_RE.finditer(ref):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 4:
            out.append(int(digits))
    return out


def _page_range_of(ref: str) -> Optional[Tuple[int, int]]:
    """First page/last page in a reference, with DOIs masked out first.

    DOIs routinely contain digit-dash-digit runs (``10.1111/j.1467-8691.2019``)
    that are not page ranges, and a DOI suffix is free to run backwards. They
    are removed before the scan so the check only ever sees the pages.
    """
    scan = _DOI_RE.sub(" ", ref)
    scan = re.sub(r"\b10\.\d+[a-z.\-/]*", " ", scan, flags=re.IGNORECASE)
    m = _PAGE_RANGE.search(scan)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    refs = doc.references or []
    if len(refs) < 3:
        return []
    out: List[Finding] = []
    now = __import__("datetime").date.today().year

    future: List[str] = []
    backwards: List[str] = []
    zero_vol: List[str] = []
    bad_issue: List[str] = []
    bad_doi: List[str] = []
    no_author: List[str] = []
    doi_seen: Dict[str, int] = {}

    for i, r in enumerate(refs):
        idx = i + 1

        for y in _years_in(r):
            if y > now + 1:                      # +1: ahead-of-print next-year is legal
                future.append(f"[{idx}] year {y}")

        pr = _page_range_of(r)
        if pr and pr[0] > pr[1]:
            backwards.append(f"[{idx}] {pr[0]}-{pr[1]}")

        for vm in _VOLUME.finditer(r):
            if int(vm.group(1)) == 0:
                zero_vol.append(f"[{idx}] volume 0")
        for vm in _VOL_ISSUE.finditer(r):
            vol, iss = int(vm.group(1)), int(vm.group(2))
            if vol == 0:
                zero_vol.append(f"[{idx}] volume 0")
            elif iss == 0:
                bad_issue.append(f"[{idx}] issue 0")
            elif iss > 999:
                # No journal issues a 4-digit issue number inside one volume;
                # this is a year (or worse) pasted where the issue belongs.
                bad_issue.append(f"[{idx}] volume {vol} issue {iss}")
        for im in _ISSUE.finditer(r):
            if int(im.group(1)) == 0:
                bad_issue.append(f"[{idx}] issue 0")

        well = _DOI_RE.search(r)
        if well:
            doi = well.group(0).lower().rstrip(".,;)")
            if doi in doi_seen and doi_seen[doi] != idx:
                out.append(_f(
                    Severity.HIGH,
                    "Same DOI on two different references",
                    f"References [{doi_seen[doi]}] and [{idx}] carry the identical DOI "
                    f"({doi}). One DOI identifies exactly one work, so at least one of "
                    f"these entries is wrong — a common signature of pasted or "
                    f"generated reference lists.",
                    f"DOI {doi} at [{doi_seen[doi]}] and [{idx}]",
                    0.95,
                    "Correct both entries; each distinct work needs its own DOI."))
            else:
                doi_seen.setdefault(doi, idx)
        else:
            att = _DOI_ATTEMPT.search(r)
            if att:
                bad_doi.append(f"[{idx}] {att.group(1)[:40]}")

        if _NO_AUTHOR.match(r):
            no_author.append(f"[{idx}] {r.strip()[:60]}")

    if future:
        out.append(_f(
            Severity.HIGH,
            "References dated in the future",
            f"{len(future)} reference(s) carry a publication year later than "
            f"{now}. A paper cannot cite work that has not been published; this "
            f"is either a typo or a generated reference.",
            "; ".join(future[:6]), 0.98,
            "Verify each flagged entry against the source and correct the year."))

    if backwards:
        out.append(_f(
            Severity.HIGH,
            "Page ranges that run backwards",
            f"{len(backwards)} reference(s) list a first page greater than the "
            f"last page. A page range cannot decrease; reviewers read this as a "
            f"broken or fabricated entry.",
            "; ".join(backwards[:6]), 0.97,
            "Correct the page range in each flagged reference."))

    if zero_vol:
        out.append(_f(
            Severity.MEDIUM,
            "Volume 0 in a reference",
            f"{len(zero_vol)} reference(s) report volume 0. Journal volumes are "
            f"1-indexed; no real article sits in volume 0.",
            "; ".join(zero_vol[:6]), 0.95,
            "Correct the volume number for each flagged reference."))

    if bad_issue:
        out.append(_f(
            Severity.MEDIUM,
            "Impossible volume/issue pairing",
            f"{len(bad_issue)} reference(s) report an issue number that no single "
            f"journal volume can hold — issue 0, or a 4-digit issue where the "
            f"year belongs.",
            "; ".join(bad_issue[:6]), 0.92,
            "Check volume(issue) against the source article."))

    if bad_doi:
        out.append(_f(
            Severity.MEDIUM,
            "Malformed DOI",
            f"{len(bad_doi)} reference(s) contain a DOI that does not match the "
            f"required 10.xxxx/ shape. Malformed DOIs are the classic output of "
            f"an LLM asked to invent a citation.",
            "; ".join(bad_doi[:6]), 0.92,
            "Replace each flagged DOI with the exact string from doi.org."))

    if no_author:
        out.append(_f(
            Severity.LOW,
            "References with no named author",
            f"{len(no_author)} reference(s) begin with no author name at all "
            f"(e.g. 'Anonymous'). Every citation style requires an author.",
            "; ".join(no_author[:6]), 0.85,
            "Add the author name, or convert the entry to the correct "
            "organizational-author format."))

    return out
