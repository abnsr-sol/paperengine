"""Legal & ethical engine: consent, privacy/de-identification, copyright permission, dual-use, prior publication, licenses."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_CLINICAL = r'patient|participant|human\s+subject|clinical|hospital|cohort|medical\s+record|biopsy|tissue\s+sample|survey\s+of'
_SENSITIVE = r'medical\s+record|health\s+data|biometric|genetic\s+data|diagnos|clinical\s+data|personal\s+data|location\s+data|video\s+of\s+(?:people|subjects)|facial\s+(?:images?|data)|patient\s+images?'
_DUAL_USE = r'CRISPR|pathogen|virus\s+(?:strain|engineering)|toxin|bioweapon|bioterror|explosive|chemical\s+synthesis|nerve\s+agent|biosecurity'
_ADAPTED = r'adapted\s+from|reprinted\s+from|reproduced\s+from|with\s+permission\s+from|taken\s+from\s+\[|used\s+with\s+permission|reproduced\s+with'


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Legal & Ethics", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []

    if re.search(_CLINICAL, body, re.IGNORECASE):
        if not re.search(r'consent\s+(?:for\s+publication|to\s+publish|was\s+obtained)|written\s+(?:informed\s+)?consent|signed\s+consent', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "No patient consent-for-publication statement",
                          "Journals require written informed consent for identifiable patient material.",
                          "Clinical keywords found, no consent-for-publication", 0.85,
                          "Add an informed-consent statement (and consent-for-publication if any patient is identifiable)"))

    if re.search(_SENSITIVE, body, re.IGNORECASE):
        if not re.search(r'anonymiz|de-identif|removed\s+(?:all\s+)?identif|pseudonymiz|no\s+identifying|privacy', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "No de-identification/privacy statement",
                          "Sensitive personal data requires a de-identification statement (HIPAA/GDPR-aware).",
                          "Sensitive-data keywords found, no anonymization terms", 0.85,
                          "State how identifiers were removed/anonymized (HIPAA Safe Harbor, GDPR pseudonymization, etc.)"))

    if re.search(_ADAPTED, body, re.IGNORECASE):
        if not re.search(r'permission|licensed\s+under|CC BY|copyright\s+(?:holder|owner)|obtained\s+permission|granted\s+permission', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "Reused figures/tables without permission statement",
                          "Material adapted/reprinted from other sources must carry a permission or license note.",
                          "Adapted-from keywords found, no permission/license mention", 0.85,
                          "Add 'Reprinted/adapted with permission from [source]' or switch to openly licensed material"))

    if re.search(r'creative\s+commons|CC BY', body, re.IGNORECASE) and re.search(r'CC BY-NC|CC BY-ND|CC BY-NC-SA', body, re.IGNORECASE):
        rules = getattr(ctx, 'rules', {}) or {}
        if str(rules.get('standard', '')).lower() == 'national' or 'mdpi' in str(getattr(ctx, 'venue', '')):
            out.append(_f(Severity.MEDIUM, "Restrictive CC license for open-access venue",
                          "Fully open venues (MDPI, Plan S, UGC OA) require CC BY; NC/ND variants can fail compliance.",
                          "CC BY-NC/ND found in OA venue context", 0.70,
                          "Confirm the venue accepts CC BY-NC/ND, or switch to CC BY"))

    if re.search(_DUAL_USE, body, re.IGNORECASE):
        if not re.search(r'dual-?use|misuse|responsible\s+research|biosecurity|ethical\s+considerations?', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Dual-use research without statement",
                          "Pathogen/toxicology/security-relevant work should acknowledge potential misuse.",
                          "Dual-use keywords found, no statement", 0.70,
                          "Add a dual-use/responsible-research statement"))

    if re.search(r'arXiv|bioRxiv|medRxiv|SSRN|preprint', body, re.IGNORECASE):
        out.append(_f(Severity.INFO, "Preprint mentioned - check journal preprint policy",
                      "If a preprint was posted, confirm the target venue allows it and disclose it at submission.",
                      "Preprint keyword found", 0.90,
                      "Verify the journal's preprint policy and disclose any posted version in the cover letter"))

    if re.search(r'conference|workshop|presented\s+at|accepted\s+at', body, re.IGNORECASE):
        if not re.search(r'extended\s+(?:version|from)|substantially\s+(?:extended|revised)|earlier\s+version', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Prior conference/preprint version without extension note",
                          "Journal submissions derived from conference papers need an explicit extension statement.",
                          "Conference keywords found, no extension note", 0.70,
                          "State how this manuscript extends the earlier version (typically 30-50% new content)"))

    return out
