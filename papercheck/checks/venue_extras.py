"""Venue extras engine: ACM CCS concepts, Elsevier highlights, graphical abstract, lay summary, suggested reviewers, pre-submission inquiry."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Venue Extras", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    venue = str(getattr(ctx, 'venue', '') or '').lower()
    rules = getattr(ctx, 'rules', {}) or {}

    # ACM CCS concepts
    if "acm" in venue and not re.search(r"CCS\s+concepts?|computing\s+classification", low, re.IGNORECASE):
        out.append(_f(Severity.MEDIUM, "ACM paper without CCS concepts", "ACM submissions require Computing Classification System concepts on page 1.",
                      "ACM venue, no CCS section", 0.85, "Add CCS concepts from the ACM CSS tool in the template slot"))
    # highlights (Elsevier)
    if "elsevier" in venue and not re.search(r"highlights?", low):
        out.append(_f(Severity.MEDIUM, "Elsevier paper without Highlights", "Elsevier journals require 3-5 bullet-point Highlights (<=85 chars each).",
                      "Elsevier venue, no highlights section", 0.80, "Add a Highlights file with 3-5 short bullets"))
    # graphical abstract
    ga_required = bool(rules.get('graphical_abstract')) or "mdpi" in venue or "elsevier" in venue
    if ga_required and not re.search(r"graphical\s+abstract", low):
        out.append(_f(Severity.LOW, "Graphical abstract not evident", "This venue typically expects a graphical abstract summarizing the finding visually.",
                      "No graphical-abstract mention", 0.60, "Prepare a graphical abstract per the venue's size/format spec"))
    # plain-language / lay summary
    if not re.search(r"plain\s+language|lay\s+summary|non-?specialist|general\s+audience", low):
        if re.search(r"clinical|public\s+health|medical", low):
            out.append(_f(Severity.LOW, "Medical paper without plain-language summary", "Medical journals and funders increasingly require a lay/plain-language summary.",
                          "Medical topic, no lay-summary wording", 0.55, "Add a plain-language summary of the findings"))
    # suggested reviewers / pre-submission inquiry reminders
    if not re.search(r"suggested\s+reviewers?|preferred\s+reviewers?", low):
        out.append(_f(Severity.LOW, "No suggested-reviewer list reminder", "Most submission systems ask for 3+ suggested reviewers without conflicts of interest.",
                      "No suggested-reviewer wording", 0.45, "Prepare a list of 3-5 qualified, conflict-free reviewers for the submission portal"))
    if re.search(r"presubmission|pre-?submission\s+inquir", low) is None and "nature" in venue:
        out.append(_f(Severity.LOW, "Pre-submission inquiry may be required", "Nature-family venues often encourage (or require) a pre-submission inquiry before full submission.",
                      "Nature venue, no inquiry wording", 0.50, "Consider a pre-submission inquiry with a brief pitch to the editor"))
    return out