"""Publisher AI-policy engine.

Publisher generative-AI policies are real, active, and inconsistent (Springer
Nature: human accountability, no AI authors, disclosure of substantive use;
Elsevier: disclosure required, AI authorship prohibited, AI images restricted;
MDPI: disclosure statement required; IEEE/ACM: disclosure + accountability).

This engine turns the venue's publisher into a compliance checklist. It cannot
verify what you actually did with AI — it ensures the required declarations
are present so the manuscript cannot be desk-rejected for a missing statement.
"""

from __future__ import annotations

from typing import Dict, List

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

# publisher -> (disclosure_required, ai_authorship_prohibited, ai_images_policy, note)
POLICY_MATRIX: Dict[str, Dict] = {
    "Springer Nature": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "restricted",
        "note": "Human accountability cannot be transferred to AI; AI may support but not replace scholarly work; disclose substantive AI use.",
    },
    "Elsevier": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "restricted",
        "note": "Disclose any use of AI tools in the manuscript; AI cannot be listed as author.",
    },
    "Wiley": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "allowed_with_disclosure",
        "note": "Disclose substantive AI-generated content; ordinary spelling/grammar assistance is excluded from disclosure scope.",
    },
    "Taylor & Francis": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "restricted",
        "note": "Disclose generative AI use; AI tools cannot be authors.",
    },
    "IEEE": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "allowed_with_disclosure",
        "note": "Disclose AI tool use in the acknowledgment section; AI cannot be an author.",
    },
    "ACM": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "allowed_with_disclosure",
        "note": "Disclose AI-generated text; authors remain accountable; AI cannot be an author.",
    },
    "MDPI": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "prohibited",
        "note": "AI tools cannot be authors; disclosure statement required; AI-generated images prohibited.",
    },
    "unknown": {
        "disclosure_required": True,
        "ai_authorship_prohibited": True,
        "ai_images": "unknown",
        "note": "Most publishers now require disclosure of substantive AI use — add a declaration to be safe.",
    },
}


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    publisher = ctx.rules.get("publisher", "unknown")
    pol = POLICY_MATRIX.get(publisher, POLICY_MATRIX["unknown"])
    findings: List[Finding] = []
    cat = "AI-policy"
    # Scan the body only — reference titles legitimately mention 'artificial intelligence'.
    full = doc.body_text

    has_decl = any(k in full.lower() for k in ("declaration of generative ai", "generative ai", "ai-assisted", "use of ai", "artificial intelligence", "chatgpt", "large language model", "llm", "ai tools"))
    if pol["disclosure_required"]:
        if not has_decl:
            findings.append(Finding(
                category=cat, severity=Severity.MEDIUM,
                title="Missing AI-use disclosure statement",
                detail=f"{publisher} requires disclosure of substantive AI-assisted writing. No AI declaration found in the manuscript.",
                evidence="publisher policy: " + pol["note"],
                action="Add a declaration (e.g. 'During the preparation of this work the author(s) used [tool] to [purpose]. The author(s) reviewed and edited the output and take full responsibility for the content.') even if you only used grammar tools.",
                confidence=0.85,
                location="end of manuscript",
            ))
        else:
            findings.append(Finding(
                category=cat, severity=Severity.INFO,
                title="AI disclosure mentions found — verify wording",
                detail="The manuscript contains AI-related language; confirm it matches the venue's required disclosure format.",
                evidence="publisher policy: " + pol["note"],
                action="Cross-check your disclosure against the venue's exact template and declaration form.",
                confidence=0.6,
            ))

    findings.append(Finding(
        category=cat, severity=Severity.INFO,
        title=f"AI-policy checklist — {publisher}",
        detail=pol["note"],
        evidence=f"AI authorship prohibited: {pol['ai_authorship_prohibited']}; AI-generated images: {pol['ai_images']}",
        action="Confirm with the venue's current author guidelines — policies change frequently.",
        confidence=1.0,
    ))
    return findings