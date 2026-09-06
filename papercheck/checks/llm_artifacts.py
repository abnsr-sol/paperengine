"""LLM artifact engine: ChatGPT-style template phrasing, tortured phrases, hallucinated-reference signatures."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_TEMPLATES = [
    (r"as an AI (?:language model|assistant)", "Assistant-style leftover"),
    (r"in conclusion, it is (?:important|worth noting|essential) to note", "Template closer"),
    (r"it is (?:important|crucial|essential) to (?:note|remember|emphasize) that", "Template filler"),
    (r"delve(?:ing)? into", "GPT-ism ('delve')"),
    (r"in the realm of", "GPT-ism ('realm of')"),
    (r"a tapestry of", "GPT-ism ('tapestry')"),
    (r"(?:plays|play) a pivotal role", "GPT-ism ('pivotal role')"),
    (r"landscape of (?:the )?(?:research|modern)", "GPT-ism ('landscape')"),
    (r"unleash(?:ing)? the (?:power|potential)", "GPT-ism ('unleash')"),
    (r"at the end of the day", "Colloquial closer"),
    (r"it goes without saying", "Filler phrase"),
    (r"in today's (?:fast-?paced|digital|modern) world", "Clickbait opener"),
]

_FAKE_REF = r"doi\s*[:\s]*\s*(?:10\.[0-9]{4,}|[0-9]+\.[0-9]+|N/?A|none)|et al\.?\s*\(\s*n\.?d\.?\)|n\.?d\.?\s*,?\s*(?:p\.?|pp\.?)\s*[0-9]+"
_TORTURED = r"profound (?:learning|networks)|unseen (?:data|learning)|neural (?:organisation|networks)\b|deep (?:acquiring|mastery)|(?:computer|machine) (?:intelligence|vision) (?:methods|approaches)\b"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("LLM Artifacts", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    out = []
    hits = [label for pat, label in _TEMPLATES if re.search(pat, low)]
    if hits:
        out.append(_f(Severity.MEDIUM, "ChatGPT-style template phrasing detected", str(len(hits)) + " assistant-style phrase patterns found; journals increasingly screen for these before review.",
                      "; ".join(hits[:6]), 0.70, "Rewrite the flagged phrases in natural academic voice; disclose any AI writing assistance per venue policy"))
    if re.search(_TORTURED, low):
        out.append(_f(Severity.HIGH, "Tortured phrase detected (possible AI-generated or translated text)",
                      "Tortured phrases ('profound learning' for 'deep learning') are a known AI/translation artifact that reviewers flag.",
                      "Matched: " + str(set(re.findall(r"(profound (?:learning|networks)|deep (?:acquiring|mastery)|neural (?:organisation|networks))", low))), 0.85,
                      "Replace with the standard terminology and re-read the sentence for sense"))
    refs = doc.references or []
    if not refs:
        refs = []
        m = re.search(r"references", low)
        if m:
            refs = [body[m.end():]]
    if refs and re.search(_FAKE_REF, low, re.IGNORECASE):
        out.append(_f(Severity.HIGH, "Hallucinated-reference signature", "Patterns like 'doi: N/A', 'n.d.', or empty DOIs are associated with AI-generated reference lists.",
                      "Matched: " + str(list(set(re.findall(_FAKE_REF, low, re.IGNORECASE)))[:4]), 0.75, "Verify every reference resolves to a real DOI; delete any that do not"))
    if re.search(r"placeholder|\[insert|TBD\b|XXX|Lorem ipsum", low, re.IGNORECASE):
        out.append(_f(Severity.HIGH, "Placeholder text left in manuscript", "Placeholders are a desk-reject trigger.",
                      "Found: " + str(list(set(re.findall(r"placeholder|\[insert|TBD\b|XXX|lorem ipsum", low, re.IGNORECASE)))[:5]), 0.95, "Remove all placeholder text before submission"))
    return out
