"""Deep writing-quality engine: weasel words, filler phrases, nominalization, tense mixing, sentence/paragraph complexity, weak transitions."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_WEASEL = r'\b(?:clearly|obviously|undoubtedly|unquestionably|basically|essentially|evidently|presumably|arguably|notably|interestingly|importantly|simply|merely|quite|rather|somewhat|relatively|comparatively)\b'
_FILLER = r'\b(?:in\s+order\s+to|due\s+to\s+the\s+fact\s+that|with\s+regard\s+to|with\s+respect\s+to|in\s+terms\s+of|at\s+this\s+point\s+in\s+time|it\s+is\s+important\s+to\s+note\s+that|it\s+should\s+be\s+noted\s+that|in\s+the\s+event\s+that)\b'
_NOMINAL = r'\b(?:utilization|operationalization|prioritization|conceptualization|maximization|minimization|implementation|characterization|normalization|optimization|generalization)\b'
_TRANS = r'\b(?:however|therefore|furthermore|moreover|in\s+contrast|additionally|consequently|nevertheless|nonetheless|meanwhile|finally|firstly|secondly|thirdly|in\s+addition|as\s+a\s+result|on\s+the\s+other\s+hand)\b'


def _f(title, detail, evidence, conf, action):
    return Finding("Writing Depth", Severity.MEDIUM, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []
    wc = len(body.split())

    w = re.findall(_WEASEL, body, re.IGNORECASE)
    if len(w) >= 4:
        out.append(_f("Weasel words overused (" + str(len(w)) + " instances)",
                      "Words like 'clearly/obviously/importantly' add no evidence and read as weak argumentation.",
                      "Found: " + ", ".join(sorted(set(x.lower() for x in w))[:8]), 0.85,
                      "Delete or replace with concrete evidence for each instance"))

    fl = re.findall(_FILLER, body, re.IGNORECASE)
    if fl:
        out.append(_f("Filler phrases (" + str(len(fl)) + " instances)",
                      "Phrases like 'due to the fact that' / 'with respect to' pad the text; journals prefer direct phrasing.",
                      "Found: " + ", ".join(sorted(set(x.lower() for x in fl))[:6]), 0.90,
                      "Replace with direct forms: 'because', 'about', 'to', 'in'"))

    nm = re.findall(_NOMINAL, body, re.IGNORECASE)
    if len(nm) >= 3:
        out.append(_f("Nominalization density (" + str(len(nm)) + " instances)",
                      "Heavy noun-phrase style ('utilization of X') is harder to read than verb style ('using X').",
                      "Found: " + ", ".join(sorted(set(x.lower() for x in nm))[:6]), 0.75,
                      "Prefer verb forms: 'use', 'operate', 'prioritize', 'implement'"))

    present = bool(re.search(r'\bwe\s+(?:propose|present|introduce|design|develop)\b', body, re.IGNORECASE))
    past = bool(re.search(r'\bwe\s+(?:proposed|presented|introduced|designed|developed)\b', body, re.IGNORECASE))
    if present and past:
        out.append(_f("Mixed verb tense for own contributions",
                      "Both 'we propose' (present) and 'we proposed' (past) appear. Pick present for the paper itself, past for what you did.",
                      "Present + past forms both found", 0.70,
                      "Normalize tense: present for claims about the paper, past for actions during the work"))

    try:
        from ..metrics import sentences
        sents = sentences(body)
        lens = [len(s.split()) for s in sents if s.split()]
        if lens:
            avg = sum(lens) / float(len(lens))
            long_cnt = sum(1 for n in lens if n > 40)
            if avg > 30:
                out.append(_f("Very long sentences (avg " + str(int(avg)) + " words)",
                              "Sentences averaging over 30 words are hard to follow; " + str(long_cnt) + " exceed 40 words.",
                              "avg=" + str(round(avg, 1)) + " words/sentence", 0.85,
                              "Split the longest sentences into two"))
    except Exception:
        pass

    paras = [p.strip() for p in (doc.paragraphs or []) if len(p.strip().split()) > 40]
    long_p = [n for n in paras if len(n.split()) > 200]
    if len(long_p) >= 2:
        out.append(_f("Overlong paragraphs (" + str(len(long_p)) + ")",
                      "Paragraphs over ~200 words reduce readability; break them at topic shifts.",
                      str(len(long_p)) + " paragraphs > 200 words", 0.75,
                      "Split each into 2-3 paragraphs with topic sentences"))

    if paras:
        opened = sum(1 for p in paras if re.match(_TRANS, p, re.IGNORECASE))
        if opened < max(1, int(len(paras) * 0.15)):
            out.append(_f("Weak paragraph transitions (" + str(opened) + "/" + str(len(paras)) + ")",
                          "Few paragraphs open with a connector; the text may read as disconnected statements.",
                          str(opened) + " of " + str(len(paras)) + " paragraphs open with a transition", 0.65,
                          "Open more paragraphs with logical connectors (However, Therefore, In contrast...)"))

    if wc > 0 and len(nm) / float(wc) * 1000 > 8:
        out.append(_f("Very high nominalization rate",
                      "More than 8 '-ization' nouns per 1000 words signals a dense bureaucratic style.",
                      str(round(len(nm) / float(wc) * 1000, 1)) + " per 1000 words", 0.70,
                      "Rewrite key sentences with active verbs"))
    return out
