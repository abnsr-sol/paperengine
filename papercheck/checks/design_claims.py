"""Design-aware claim engine: causal overclaim by study design, abstract front-loading, conclusion quality."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_CAUSAL = r'\b(causes?|leads?\s+to|results?\s+in|improves?|reduces?|prevents?|proves?|demonstrates?\s+that|guarantees?|drives?)\b'
_OBS = r'cross-?sectional|cohort|observational|correlation|associat(?:ed|ion)|retrospective|survey'
_RCT = r'randomized\s+controlled\s+trial|randomised\s+controlled\s+trial|\bRCT\b|double-?blind'
_ABSOLUTE = r'\balways\b|\bnever\b|\bperfect\b|\bguaranteed\b|\ball\s+cases\b|\bdefinitively\b|\bproven\b|\bunambiguously\b'


def _abstract(doc: Document) -> str:
    for sec in getattr(doc, "sections", []) or []:
        if sec.heading and "abstract" in sec.heading.lower():
            return sec.body or ""
    if getattr(doc, "paragraphs", None):
        return doc.paragraphs[0] or ""
    return ""


def _conclusion(doc: Document) -> str:
    for sec in getattr(doc, "sections", []) or []:
        if sec.heading and ("conclusion" in sec.heading.lower() or "discussion" in sec.heading.lower()):
            return sec.body or ""
    return ""


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Claims", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []
    abst = _abstract(doc)
    concl = _conclusion(doc)

    is_obs = bool(re.search(_OBS, body, re.IGNORECASE))
    is_rct = bool(re.search(_RCT, body, re.IGNORECASE))

    # Causal language from observational designs (top peer-review rejection cause).
    if is_obs and not is_rct:
        causal_hits = re.findall(r'[^.]*' + _CAUSAL + r'[^.]*\.', body, re.IGNORECASE)
        if causal_hits:
            out.append(_f(Severity.HIGH, "Causal claims from observational data",
                          "Observational designs show association, not causation. Causal verbs ('causes', 'improves', 'leads to') overclaim.",
                          "Example: " + causal_hits[0].strip()[:120], 0.85,
                          "Replace causal verbs with association language ('is associated with', 'correlates with') or qualify as hypothesis-generating"))

    # Absolute/conclusive claims.
    abs_hits = re.findall(r'[^.]*' + _ABSOLUTE + r'[^.]*\.', concl if concl else body, re.IGNORECASE)
    if abs_hits:
        out.append(_f(Severity.MEDIUM, "Absolute/conclusive claims in conclusion",
                      "Words like 'always/never/perfect/proven' overstate; reviewers flag unsupported certainty.",
                      "Example: " + abs_hits[0].strip()[:120], 0.80,
                      "Qualify conclusions ('in this setting', 'suggests', 'may') unless truly proven"))

    # Abstract front-loading: does the FIRST sentence state the finding/contribution?
    if abst:
        first = abst.split(". ")[0] if abst else ""
        if len(first.split()) >= 25 and not re.search(r'we\s+(?:propose|present|introduce|show|demonstrate)|results?\s+(?:show|demonstrate)|found\s+that|improved|outperform', first, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Abstract does not front-load the finding",
                          "The abstract's first sentence should state the finding/contribution; leading with generic background is the #1 desk-rejection signal (51.8%).",
                          "First sentence: " + first[:120], 0.75,
                          "Open the abstract with the gap + key result, then context"))

    # Conclusion: interpretation + future work + implications.
    if concl:
        words = len(concl.split())
        if words < 40:
            out.append(_f(Severity.LOW, "Very thin conclusion",
                          "The conclusion restates little and interprets nothing.",
                          "Conclusion length: " + str(words) + " words", 0.70,
                          "Summarize findings, interpret them, state implications and limitations"))
        elif not re.search(r'future|further\s+work|implications?|recommend|should|limitations?', concl, re.IGNORECASE):
            out.append(_f(Severity.LOW, "Conclusion lacks interpretation or future work",
                          "Strong conclusions interpret results, note implications, and point to next steps.",
                          "No implications/future-work terms in conclusion", 0.65,
                          "Add a closing paragraph on implications and future work"))

    # 'Significant' in conclusions without p-value/stats nearby.
    if concl and re.search(r'\bsignificant(?:ly)?\b', concl, re.IGNORECASE) and not re.search(r'p\s*[<>=]|CI\b|confidence|effect\s+size|\d+\.\d+\s*Â±', concl, re.IGNORECASE):
        out.append(_f(Severity.MEDIUM, "'Significant' in conclusion without statistics",
                      "Statistical significance claims need numbers (p, CI) to be meaningful.",
                      "Conclusion contains 'significant' without stats", 0.80,
                      "Quote the p-value/CI next to any significance claim"))

    return out
