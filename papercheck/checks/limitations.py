"""Limitations / threats-to-validity section detector.

The #1 reviewer complaint across disciplines is "no limitations discussed" or
"weak discussion of limitations." This engine detects whether the manuscript
contains a dedicated limitations section and flags its absence.

Based on: Wiley 2024 "Rejected papers" study, Emerald 2025, sita-pub 2026.
Severity: MEDIUM (reviewer friction, not fraud).
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

# Limitations section detection patterns
_LIMITATIONS_SECTION = re.compile(
    r"(?:^|\n)\s*#*\s*"
    r"(?:"
    r"(?:study\s+)?limitations?"
    r"|threats?\s+to\s+(?:internal|external|construct|statistical)\s+validity"
    r"|limitations?\s+and\s+(?:future\s+)?(?:work|directions?|research)"
    r"|discussion\s+of\s+limitations?"
    r"|strengths?\s+and\s+limitations?"
    r"|study\s+(?:strengths?\s+and\s+)?limitations?"
    r"|methodological\s+limitations?"
    r"|acknowledged\s+limitations?"
    r")\s*(?::|—|–|-|$)",
    re.IGNORECASE | re.MULTILINE
)

# Inline limitations mentions (not a dedicated section)
_LIMITATIONS_INLINE = re.compile(
    r"(?:"
    r"(?:one|a|the|our|this|the\s+main|the\s+primary|a\s+key|a\s+major|the\s+major)\s+"
    r"(?:limitation|weakness|shortcoming|constraint|drawback|caveat|concern)"
    r"|limitations?\s+(?:of\s+(?:this|the|our|these|the\s+current|the\s+present)\s+"
    r"(?:study|work|analysis|approach|method|paper|research|investigation))"
    r"|should\s+(?:be\s+)?(?:noted|acknowledged|mentioned|recognized)\s+that"
    r"|it\s+is\s+(?:important|worthwhile|necessary)\s+to\s+(?:note|acknowledge|mention)"
    r")",
    re.IGNORECASE
)

# Section heading detection for context
_SECTION_HEADINGS = re.compile(
    r"(?:^|\n)\s*#*\s*"
    r"(?:"
    r"discussion|conclusion|conclusions|summary|final\s+remarks|closing\s+remarks"
    r"|general\s+discussion|overall\s+discussion"
    r")\s*(?::|—|–|-|$)",
    re.IGNORECASE | re.MULTILINE
)


def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return findings

    # Check for dedicated limitations section
    has_limitations_section = bool(_LIMITATIONS_SECTION.search(body))

    # Check for inline limitations mentions
    inline_mentions = len(_LIMITATIONS_INLINE.findall(body))

    # Check if there's a discussion section (required for limitations to be expected)
    has_discussion = bool(_SECTION_HEADINGS.search(body))

    # Only flag if there's a discussion section but no limitations
    if has_discussion and not has_limitations_section and inline_mentions < 2:
        findings.append(Finding(
            category="Discussion", severity=Severity.MEDIUM,
            title="No limitations section detected",
            detail="Reviewer studies consistently rank 'no limitations discussed' among the top "
                   "rejection reasons. A dedicated 'Limitations' or 'Threats to Validity' section "
                   "is expected in all empirical papers.",
            evidence=f"Discussion section detected but no limitations section or subsection found; "
                     f"only {inline_mentions} inline limitation mention(s)",
            confidence=0.75,
            action="Add a dedicated 'Limitations' subsection before the Conclusion, addressing "
                   "at minimum: (1) internal validity threats, (2) external validity/generalizability, "
                   "(3) measurement limitations"))

    elif not has_limitations_section and inline_mentions >= 2:
        # Has inline mentions but no dedicated section — low severity nudge
        findings.append(Finding(
            category="Discussion", severity=Severity.LOW,
            title="Limitations discussed inline but no dedicated section",
            detail=f"Found {inline_mentions} inline limitation mention(s) but no dedicated "
                   "'Limitations' section/heading. Reviewers often miss inline limitations.",
            evidence=f"{inline_mentions} inline limitation mentions; no section heading",
            confidence=0.55,
            action="Consider consolidating limitations into a dedicated subsection for visibility"))

    return findings
