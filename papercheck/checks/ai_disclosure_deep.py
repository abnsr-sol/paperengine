"""Deep AI-disclosure engine: per-tool disclosure, AI-generated figures, AI in methodology, EU AI Act transparency."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_TOOLS = r"ChatGPT|GPT-?4|GPT-?5|Claude|Gemini|Bard|Copilot|LLaMA|Llama|Mistral|DeepSeek|Midjourney|DALL-?E|Stable\s+Diffusion|Grammarly|QuillBot|Writefull|Elicit|Consensus|Scite|Epsilon"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("AI Disclosure", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    tool_hits = set(re.findall(_TOOLS, text, re.IGNORECASE))
    has_disclosure = re.search(r"disclos|declared|decline|we\s+used\s+.+for\s+(?:language|grammar|writing)|assisted\s+(?:the\s+)?(?:drafting|writing|language)", low)
    # tool named but no disclosure framing
    if tool_hits and not has_disclosure:
        out.append(_f(Severity.HIGH, "AI tool named without disclosure statement", "Naming " + ", ".join(sorted(tool_hits)[:3]) + " without describing how it was used violates most publisher AI policies (ICMJE/COPE/Elsevier).",
                      "Tools: " + ", ".join(sorted(tool_hits)[:5]), 0.85, "Add an AI-use declaration: tool, version, purpose, and which sections were affected"))
    # AI-ish figure generation
    if re.search(r"midjourney|dall-?e|stable\s+diffusion|ai-?generated\s+(?:image|figure)", low) and not re.search(r"disclos|declar|noted\s+that", low):
        out.append(_f(Severity.HIGH, "AI-generated figures without disclosure", "AI-generated images must be disclosed and are banned outright by many journals (JAMA, Science).",
                      "AI-image tooling found, no disclosure", 0.90, "Disclose AI figure generation or replace with original images"))
    # AI used in analysis/methods without validation statement
    if re.search(r"(?:machine|deep)\s+learning.{0,40}(?:analyz|classif|predict)", low) and re.search(r"chatgpt|gpt-?4|gpt-?5|llm", low):
        if not re.search(r"validat|manual(?:ly)?\s+(?:verif|review|check)|human\s+(?:review|verification)", low):
            out.append(_f(Severity.MEDIUM, "AI-assisted analysis without human-verification statement", "When AI tools touch data analysis, journals want an explicit human-verification statement.",
                          "AI analysis + LLM mention, no human verification", 0.65, "State that humans verified all AI-assisted outputs"))
    # EU AI Act transparency (applies Aug 2026)
    if re.search(r"european|EU\s+funder|Horizon", text) and re.search(r"chatgpt|gpt-?4|gpt-?5|claude|gemini|llm", low) and not re.search(r"EU\s+AI\s+Act", text):
        out.append(_f(Severity.LOW, "EU-context paper without EU AI Act note", "The EU AI Act (Art. 50, applicable Aug 2026) requires disclosure of AI-generated content in EU-funded contexts.",
                      "EU funder context + AI tooling, no AI Act mention", 0.50, "Check EU AI Act transparency duties for AI-generated content"))
    # AI listed as author
    if re.search(r"(?:chatgpt|gpt-?4|gpt-?5|claude|gemini|llm)\s*(?:,|\band\b)?\s*[A-Z]?\s*[a-z]*\s*et\s+al|\bAI\b\s+(?:as\s+)?(?:co-?)?author", low):
        out.append(_f(Severity.CRITICAL, "AI appears to be listed as an author", "AI tools cannot be authors (ICMJE/COPE/universal policy); only humans can take authorship responsibility.",
                      "AI tool in authorship context", 0.80, "Remove any AI attribution from the author list; disclose tool use in Methods/Acknowledgments instead"))
    return out