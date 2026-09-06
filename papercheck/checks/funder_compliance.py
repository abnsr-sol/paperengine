"""Funder compliance engine: NIH, NSF, Horizon Europe, Wellcome, Plan S, DMP expectations."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_FUNDERS = {
    "NIH": r"\bNIH\b|National\s+Institutes\s+of\s+Health|R\d{2}[A-Z]{2}\d*|K\d{2}[A-Z]{2}",
    "NSF": r"\bNSF\b|National\s+Science\s+Foundation",
    "Horizon Europe": r"Horizon\s+(?:Europe|2020)|European\s+Research\s+Council|\bERC\b",
    "Wellcome": r"Wellcome\s+Trust",
    "UKRI": r"\bUKRI\b|UK\s+Research\s+and\s+Innovation|EPSRC|ESRC|BBSRC|MRC\b",
    "DST/DBT/ICMR (India)": r"\bDST\b|\bDBT\b|\bICMR\b|\bCSIR\b|Science\s+and\s+Engineering\s+Research\s+Board|\bSERB\b",
}


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Funder Compliance", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    acknowledged = re.search(r"acknowledg", low)
    funders = [name for name, pat in _FUNDERS.items() if re.search(pat, text)]
    if not funders:
        return out
    # open-access requirement for cOAlition S funders
    plan_s = [f for f in funders if f in ("Horizon Europe", "Wellcome", "UKRI")]
    if plan_s and not re.search(r"open\s+access|creative\s+commons|CC[- ]?BY|repository|green\s+OA|gold\s+OA", low):
        out.append(_f(Severity.MEDIUM, "cOAlition S funder without open-access mention", "Papers from " + ", ".join(plan_s) + " funding must be open access (Plan S) - state OA route or license.",
                      "Funders: " + ", ".join(plan_s), 0.65, "Plan for immediate OA (gold/green) with a CC BY license"))
    # NIH public access
    if "NIH" in funders and not re.search(r"PMC|PubMed\s+Central|public\s+access", low):
        out.append(_f(Severity.LOW, "NIH-funded work without PMC deposit mention", "NIH public-access policy requires deposit in PubMed Central.",
                      "NIH grant terms found", 0.60, "Note the NIH manuscript submission (NIHMS) / PMC deposit"))
    # grant numbers format
    grants = re.findall(r"(?:grant|award|contract)\s+(?:no\.?|number[s]?|#)?\s*([A-Z0-9][A-Z0-9-]{3,})", text)
    if funders and not grants and re.search(r"fund|support", low):
        out.append(_f(Severity.LOW, "Funding acknowledged without grant numbers", "Funders require full award numbers in the acknowledgments.",
                      "Funder named, no grant number pattern", 0.55, "Add complete grant/award numbers for every funder"))
    # data management plan for major funders
    if funders and re.search(r"dataset|data\s+available|data\s+shar", low) and not re.search(r"data\s+management\s+plan|\bDMP\b", low):
        out.append(_f(Severity.LOW, "Funder data policy without DMP reference", "Major funders expect a data management plan; reference it if one exists.",
                      "Funders: " + ", ".join(funders[:3]), 0.45, "Mention the DMP or data-stewardship arrangement"))
    return out