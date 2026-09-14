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
    (r"it is worth noting that", "Template filler"),
    (r"it (?:can|should) be (?:noted|observed|seen) that", "Template filler"),
    (r"it may be (?:suggested|observed|noted) that", "Template filler"),
    (r"it (?:was|is) (?:observed|found|shown|concluded) that", "Template filler"),
    (r"it can be concluded that", "Template closer"),
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

# Hallucination signatures. NOTE: a bare real DOI (10.xxxx/yyyy) is NOT a
# fake-ref signal — legitimate entries look exactly like that (e.g. Zenodo
# 10.5281/...). What IS suspicious: explicit placeholders (doi: N/A, doi: none,
# doi: TBD), 'n.d.' (no date) citations, and page-numbered n.d. entries.
_FAKE_REF = r"doi\s*[:\s]*\s*(?:N/?A|none|TBD|xxx|\?)\b|et al\.?\s*\(\s*n\.?d\.?\)|n\.?d\.?\s*,?\s*(?:p\.?|pp\.?)\s*[0-9]+"
# Comprehensive tortured-phrase list (Cabanac PPS + PaperGuard T4 catalogue).
# Each entry: (pattern, legitimate_term). Word-level matching for speed.
_TORTURED_PHRASES = {
    # AI/ML
    "profound learning": "deep learning",
    "deep mastery": "deep learning",
    "deep acquiring": "deep learning",
    "deep craft": "deep learning",
    "neural organisation": "neural network",
    "neural nets": "neural network",
    "artificial neurological": "artificial neural",
    "counterfeit consciousness": "artificial intelligence",
    "counterfeit brain": "artificial intelligence",
    "counterfeit intellect": "artificial intelligence",
    "spontaneous neural": "recurrent neural",
    "drawback neural": "recurrent neural",
    "long short-term memory": "LSTM",
    # NLP
    "regular water": "natural language",
    "normal water": "natural language",
    "typical water": "natural language",
    "processing of normal water": "natural language processing",
    "word processing of normal water": "natural language processing",
    "unseen data": "unseen data",
    "unobserved data": "unseen data",
    # Random Forest
    "irregular timberland": "random forest",
    "irregular woods": "random forest",
    "arbitrary woodland": "random forest",
    "arbitrary timberland": "random forest",
    "arbitrary forests": "random forest",
    # Big Data
    "colossal information": "big data",
    "colossal data": "big data",
    "huge information": "big data",
    "massive information": "big data",
    # Cancer
    "bosom malignancy": "breast cancer",
    "bosom disease": "breast cancer",
    "chest malignancy": "breast cancer",
    "bosom carcinoma": "breast cancer",
    # General
    "learning models": "machine learning",
    "training models": "machine learning",
    "computer intelligence": "artificial intelligence",
    "machine intelligence": "artificial intelligence",
    "they shall be moulded": "they shall be trained",
    "they shall be shaped": "they shall be trained",
    "they were moulded": "they were trained",
    "perturbations in the intestinal fortitude": "gut microbiome",
    "modifications in the intestinal fortitude": "gut microbiome",
    "transformations in the gut": "gut microbiome",
    "deep acquiring": "deep learning",
    "superior understanding": "deep learning",
    "convolution neural": "convolutional neural",
    "generative adversarial": "generative adversarial",
    "reinforced learning": "reinforcement learning",
    "reinforcement instruction": "reinforcement learning",
    "exchange learning": "transfer learning",
    "migration learning": "transfer learning",
    "transport learning": "transfer learning",
    "encoder-decoder": "encoder-decoder",
    "consciousness systems": "intelligent systems",
    "intelligent systems": "intelligent systems",
    "smart systems": "intelligent systems",
}

# Build regex from phrases
TORTURED_RE = "|".join(
    r"\b" + re.escape(p).replace(r" ", r"\s+") + r"\b"
    for p in _TORTURED_PHRASES
)

def _find_tortured_phrases(text: str) -> List[dict]:
    """Find tortured phrases and return list of {detected, intended}."""
    low = text.lower()
    findings = []
    for phrase, intended in _TORTURED_PHRASES.items():
        # Word-boundary match with flexible whitespace
        pat = r"\b" + re.escape(phrase).replace(r" ", r"\s+") + r"\b"
        if re.search(pat, low):
            findings.append({"detected": phrase, "intended": intended})
    return findings


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
    # Tortured phrases (expanded PPS/PaperGuard T4 list)
    tp_hits = _find_tortured_phrases(low)
    if tp_hits:
        unique_intended = set(h["intended"] for h in tp_hits)
        out.append(_f(Severity.HIGH, "Tortured phrases detected (possible AI-generated or translated text)",
                      f"{len(tp_hits)} tortured phrase(s) found — known AI/translation artifacts that reviewers flag. "
                      "Tortured phrases are synonyms generated by spinning software to evade plagiarism detection.",
                      "Matched: " + "; ".join(f"'{h['detected']}' → '{h['intended']}'" for h in tp_hits[:8]),
                      0.85,
                      "Replace each tortured phrase with its standard terminology and re-read for sense"))
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
