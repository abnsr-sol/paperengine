"""Peer-review misconduct engine: coerced citations in review responses, conflicted/fake reviewer suggestions."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_RESPONSE = r"response\s+to\s+(?:the\s+)?reviewers?|reviewer\s*#\s*\d|comment\s+\d|response\s+letter"
_DEMAND = r"(?:should|must|need(?:s)?\s+to)\s+(?:be\s+)?cite|please\s+cite|citing\s+.{0,30}(?:is\s+)?(?:needed|required|recommended)|include\s+the\s+following\s+references?"
_FREE_MAIL = r"gmail\.com|yahoo\.com|hotmail\.com|outlook\.com|aol\.com|protonmail\.com|qq\.com|163\.com"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Peer Review", sev, title, detail, evidence, action, conf)


def _emails(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    is_response = bool(re.search(_RESPONSE, low))
    # --- coerced citations inside a response letter -------------------------
    if is_response:
        demand_blocks = re.findall(r"(?:reviewer\s*#\s*\d|comment\s*\d).{0,1200}?(" + _DEMAND + r")", low, re.DOTALL)
        cited_in_demands = 0
        for m in re.finditer(_DEMAND, low):
            window = low[m.end():m.end() + 600]
            n_cites = len(re.findall(r"\[\d+\]|et\s+al|\(\d{4}\)", window))
            if n_cites >= 3:
                cited_in_demands += 1
        if cited_in_demands >= 2:
            out.append(_f(Severity.MEDIUM, "Possible coerced citations in review responses", str(cited_in_demands) + " reviewer demand(s) ask you to add 3+ specific papers. Legitimate suggestions exist, but mass citation demands are a known coercion pattern - verify the suggested papers are actually relevant.",
                          str(cited_in_demands) + " high-volume citation demands found", 0.55, "Cite only papers you judge relevant; flag coercive demands to the editor"))
        # defensive tone handled by rebuttal engine; here: pressure patterns
        if re.search(r"(?:we\s+(?:are\s+)?forced|no\s+choice\s+but\s+to\s+cite|to\s+satisfy\s+the\s+reviewer)", low):
            out.append(_f(Severity.HIGH, "Pressure-to-cite language present", "Phrases like 'to satisfy the reviewer' indicate citation coercion; report it to the journal (COPE guidance).",
                          "Pressure phrasing found", 0.70, "Remove forced citations and report coercion to the editor"))
    # --- suggested reviewers with conflicts --------------------------------
    if re.search(r"suggested\s+reviewers?|preferred\s+reviewers?|reviewer\s+suggestions?", low):
        emails = _emails(text)
        free_mail = [e for e in emails if re.search(_FREE_MAIL, e, re.IGNORECASE)]
        if free_mail:
            out.append(_f(Severity.MEDIUM, "Suggested reviewers use free-mail addresses", str(len(free_mail)) + " reviewer email(s) are free-mail (gmail/yahoo...). Fraudulent reviewer suggestions commonly hide behind free-mail; editors prefer institutional addresses.",
                          "Free-mail reviewers: " + ", ".join(free_mail[:3]), 0.65, "Suggest reviewers with verifiable institutional emails only"))
        # same-domain as author emails = hidden conflict
        sugg_m = re.search(r"suggested\s+reviewers?|preferred\s+reviewers?|reviewer\s+suggestions?", low)
        author_zone = low[:sugg_m.start()] if sugg_m else low[:3000]
        author_emails = [e for e in _emails(author_zone)]
        author_domains = {e.split("@")[-1] for e in author_emails}
        shared = [e for e in emails if e.split("@")[-1] in author_domains and e not in author_emails]
        if shared:
            out.append(_f(Severity.HIGH, "Suggested reviewers share the authors' domain", str(len(shared)) + " reviewer email(s) come from the authors' own institution - a hidden conflict of interest (COPE red flag).",
                          "Same-domain: " + ", ".join(shared[:3]), 0.70, "Do not suggest colleagues from your own institution; disclose any collaboration history"))
        # surname match between authors and suggested reviewers
        surnames = set()
        for e in author_emails:
            local = e.split("@")[0]
            parts = re.split(r"[._]", local)
            if len(parts) >= 2 and len(parts[-1]) >= 3:
                surnames.add(parts[-1].lower())
        if surnames:
            reviewer_zone = re.search(r"suggested\s+reviewers?(.{0,1500})", low, re.DOTALL)
            if reviewer_zone:
                zone = reviewer_zone.group(1)
                hits = [s for s in surnames if re.search(r"\b" + s + r"\b", zone)]
                if hits:
                    out.append(_f(Severity.HIGH, "Suggested reviewers share authors' surnames", "Reviewer suggestion(s) repeat author surname(s): " + ", ".join(hits[:3]) + ". Self-review rings use this pattern.",
                                  "Surname overlap: " + ", ".join(hits[:3]), 0.60, "Remove conflicted reviewer suggestions; editors cross-check names against authors"))
    return out