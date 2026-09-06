"""Venue scope-matching engine: manuscript topic keywords vs the venue's aims-and-scope domain terms."""
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
        return out
    pat = re.compile(_SCOPE[key], re.IGNORECASE)
    hits = set(pat.findall(body))
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
