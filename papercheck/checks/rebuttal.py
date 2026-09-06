"""Rebuttal / response-letter analyzer: detects a response-to-reviewers document and checks structure, tone, evidence, completeness."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_DETECT = r'response\s+to\s+reviewers?|point-?by-?point|reviewer\s+[1-9]|comments?\s+of\s+the\s+reviewers?|rebuttal|we\s+(?:thank|appreciate)\s+the\s+reviewers?'
_REVIEWER = re.compile(r'\breviewer\s+([1-9])\b', re.IGNORECASE)
_COMMENT = re.compile(r'(?:comment|point|concern|issue|question)\s*#?\s*(\d+)', re.IGNORECASE)
_RESPONSE = re.compile(r'\bresponse\s*[:.]|we\s+(?:thank|agree|have\s+(?:revised|added|modified|clarified|included|updated|changed))|done\s*[:.]|fixed\s*[:.]', re.IGNORECASE)
_DEFENSIVE = r'\b(reviewer\s+(?:is\s+)?(?:wrong|incorrect|mistaken|misunderstands?|misread))|(?:we\s+)?disagree\s+strongly|that\s+is\s+not\s+true|the\s+reviewer\s+fails?'
_EVIDENCE = r'new\s+(?:experiment|analysis|data|figure|table|results?|evaluation)|added\s+(?:an?\s+)?(?:experiment|analysis|section|figure|table)|additional\s+(?:experiment|analysis|evidence)|revised\s+(?:the\s+)?(?:manuscript|section|figure|table)|we\s+now\s+(?:show|report|include|provide)'
_APOLOGY = r'we\s+(?:sincerely\s+)?(?:thank|apologize)|we\s+appreciate'


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Rebuttal", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body or not re.search(_DETECT, body[:6000], re.IGNORECASE):
        return []
    out = []
    paras = [p.strip() for p in (doc.paragraphs or []) if p.strip()]

    reviewers = set(_REVIEWER.findall(body))
    if not reviewers:
        out.append(_f(Severity.MEDIUM, "No reviewer sections identified",
                      "A response letter should organize answers per reviewer (Reviewer 1, 2, ...).",
                      "No 'Reviewer N' headers found", 0.85,
                      "Organize the response by reviewer, then by comment number"))

    comments = _COMMENT.findall(body)
    responses = _RESPONSE.findall(body)
    if reviewers and len(responses) == 0:
        out.append(_f(Severity.HIGH, "No explicit responses found",
                      "Comments/points appear but no 'Response:' or 'We thank/revised' statements follow them.",
                      "Comments: " + str(len(comments)) + ", responses: 0", 0.80,
                      "Add an explicit response after every comment"))

    if reviewers and comments:
        n_comments = len(set(comments))
        if n_comments > len(responses) * 2:
            out.append(_f(Severity.MEDIUM, "Several comments may be unaddressed",
                          "Only " + str(len(responses)) + " response markers for ~" + str(n_comments) + " comments.",
                          "comments=" + str(n_comments) + ", responses=" + str(len(responses)), 0.65,
                          "Ensure every single comment has a direct response"))

    if re.search(_DEFENSIVE, body, re.IGNORECASE):
        out.append(_f(Severity.HIGH, "Defensive tone toward reviewers",
                      "Phrases like 'the reviewer is wrong/misunderstands' read as hostile; editors dislike dismissive rebuttals.",
                      "Defensive phrasing found", 0.80,
                      "Rephrase as 'We clarify that...' / 'We respectfully note that...' even when disagreeing"))

    if re.search(_EVIDENCE, body, re.IGNORECASE):
        out.append(_f(Severity.INFO, "New evidence present in response",
                      "The response cites added experiments/analyses - strong rebuttal practice.",
                      "Evidence keywords found", 0.90,
                      "Keep pointing each added item to its location in the revised manuscript (line/section)"))
    else:
        out.append(_f(Severity.MEDIUM, "Response shows little new evidence",
                      "No added experiments/analyses mentioned. Reviewers expect concrete changes, not just explanations.",
                      "No evidence keywords found", 0.70,
                      "Add at least one new experiment/analysis per major criticism, or state clearly why it is infeasible"))

    return out
