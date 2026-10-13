"""Venue scope-matching engine: manuscript topic vs the venue's aims-and-scope.

Why the default-venue branch matters
------------------------------------
Scope/fit is the single most common desk-rejection reason: 35% of desk rejects
in the Elsevier transport portfolio (Wu et al. 2024, n=5,036) and the top desk
reason in Menon et al. 2020 (n=898). Before 2026-10-12 this engine returned
``[]`` whenever the venue string matched no preset key — which includes
``describe('generic')``, i.e. **the documented default invocation**
(`papercheck paper.docx`) and the GUI with no preset selected. The most common
reason for rejection was silently uncovered in the run most people actually do.

Now the unknown-venue case emits an INFO naming the gap and the fix (pass
``--venue``), which costs nothing on the score (INFO weight = 0) but stops the
report from looking clean where it is merely unmeasured.

Scope is judged on **title + abstract + body**, because that is the material an
editor reads before deciding — not the reference list, which is excluded by
``body_text``.
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

# Domain vocabulary per venue preset key. Heuristic - editors apply aims-and-scope strictly.
_SCOPE = {
    "ieee_conference": r"\b(signal|image|video|speech|network|wireless|circuit|chip|embedded|sensor|radar|deep\s+learning|neural|processing|communication|antenna|power|control|robotics)\b",
    "ieee_journal": r"\b(signal|image|video|network|circuit|embedded|sensor|deep\s+learning|neural|processing|communication|control|robotics|security|forensics)\b",
    "ieee_access": r"\b(technology|engineering|computing|deep\s+learning|neural|network|data|system|sensor|image|signal|application)\b",
    "acm": r"\b(computing|algorithm|software|system|data|machine\s+learning|human-computer|programming|distributed|database|security|network|interface|theory)\b",
    "elsevier": r"\b(science|engineering|medicine|clinical|molecular|materials|energy|environment|computational|data)\b",
    "springer": r"\b(science|engineering|mathematics|physics|chemistry|biology|medicine|computational|data|machine\s+learning)\b",
    "nature": r"\b(science|biology|physics|chemistry|medicine|earth|astronomy|neuroscience|genetics|ecology)\b",
    "mdpi": r"\b(science|engineering|materials|energy|environment|medicine|biology|chemistry|sustainability|physics)\b",
    "plos": r"\b(biology|medicine|genetics|ecology|public\s+health|clinical|evolution|neuroscience|microbiology)\b",
    "wiley": r"\b(chemistry|biology|medicine|materials|physics|engineering|energy|polymer|catalysis)\b",
    "frontiers": r"\b(biology|medicine|psychology|neuroscience|public\s+health|nutrition|environment|physics|engineering)\b",
    "ugc_care": r"\b(science|engineering|social\s+sciences|humanities|management|economics|education|technology|medicine|law)\b",
    "scopus_indian": r"\b(science|engineering|technology|management|medicine|agriculture|mathematics|computer)\b",
    "naac_journal": r"\b(science|social\s+sciences|humanities|management|education|technology|medicine)\b",
}

_WORDS = r"[a-z][a-z-]{3,}"


def _preset_key(venue: str) -> str:
    v = venue.lower()
    for k in _SCOPE:
        if k in v:
            return k
    return ""


def run(doc: Document, ctx: object) -> List[Finding]:
    out = []
    body = doc.body_text or doc.text or ""
    if not body:
        return out
    key = _preset_key(str(getattr(ctx, "venue", "")))
    if not key:
        out.append(Finding("Submission", Severity.INFO,
                           "Scope check skipped — no venue selected",
                           "Aims-and-scope fit is the most common reason editors reject a paper before peer review (35% of desk rejects in one 5,000-paper study), but it can only be judged against a named venue. None was given, so this run makes no scope claim either way.",
                           "venue = '" + str(getattr(ctx, "venue", ""))[:60] + "' matched no scope preset",
                           "Re-run with --venue <preset> (see --list-venues) to get the scope check; if the journal is not preset, use --venue-json with its aims-and-scope terms",
                           1.0))
        return out
    # Title + abstract are what an editor reads first, so scope is measured on
    # the front matter *and* the body, not the body alone.
    front = "\n".join((doc.paragraphs or [])[:4])
    hay = front + "\n" + body
    pat = re.compile(_SCOPE[key], re.IGNORECASE)
    hits = set(pat.findall(hay))
    if not hits:
        out.append(Finding("Submission", Severity.MEDIUM,
                           "Possible scope mismatch with target venue",
                           "None of the venue's domain terms (aims-and-scope vocabulary) appear in the manuscript - editors desk-reject 17-25% for scope mismatch.",
                           "Venue domain: " + key, "Re-read the venue's aims-and-scope; if this paper truly fits, make the fit explicit in the intro and cover letter",
                           0.60))
    elif len(hits) <= 2:
        out.append(Finding("Submission", Severity.LOW,
                           "Thin topical overlap with venue scope",
                           "Only " + str(len(hits)) + " domain terms from the venue's scope appear; borderline fit.",
                           "Terms: " + ", ".join(sorted(hits)[:6]), "Frame the contribution using the venue's vocabulary where honest",
                           0.55))
    return out
