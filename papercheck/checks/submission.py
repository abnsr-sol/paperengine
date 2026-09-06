"""Submission readiness: missing sections, keywords, ORCID, required elements."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text
    if not body:
        return findings
    rules = ctx.rules if hasattr(ctx, 'rules') else {}
    # Limitations section
    has_limitations = bool(re.search(r'(?:limitations?|\d+\.?\s*limitations?)', body, re.IGNORECASE))
    if not has_limitations:
        findings.append(Finding(category="Submission", severity=Severity.MEDIUM, title='No Limitations section', detail='Most journals expect a dedicated Limitations section. Reviewers look for self-awareness.', evidence='No Limitations heading found', confidence=0.80, action='Add a Limitations section discussing threats to validity'))
    # Future work
    has_future = bool(re.search(r'(?:future\s+work|future\s+direction|future\s+research|conclusion)', body, re.IGNORECASE))
    if not has_future:
        findings.append(Finding(category="Submission", severity=Severity.LOW, title='No Future Work mentioned', detail='Consider adding future directions in the Conclusion.', evidence='No future work keywords found', confidence=0.60, action='Add future work directions to Conclusion'))
    # ORCID
    has_orcid = bool(re.search(r'(?:orcid|0000[- ]000[0-9][- ]000[0-9])', body, re.IGNORECASE))
    require_orcid = rules.get('require_orcid', False)
    if require_orcid and not has_orcid:
        findings.append(Finding(category="Submission", severity=Severity.HIGH, title='ORCID required but not found', detail='This venue requires ORCID iD for authors.', evidence='No ORCID found', confidence=0.90, action='Add ORCID iD for all authors'))
    elif not has_orcid:
        findings.append(Finding(category="Submission", severity=Severity.LOW, title='No ORCID iD found', detail='ORCID is recommended by most publishers for author identification.', evidence='No ORCID found', confidence=0.60, action='Add ORCID iD for corresponding author'))
    # Keywords
    has_keywords = bool(re.search(r'(?:keywords?|index\s+terms?)\s*[:\-—]', body, re.IGNORECASE))
    if not has_keywords:
        findings.append(Finding(category="Submission", severity=Severity.MEDIUM, title='No keywords/index terms found', detail='Most journals require 4-6 keywords for indexing.', evidence='No keywords heading found', confidence=0.85, action='Add 4-6 discipline-specific keywords'))
    # Author email
    has_email = bool(re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body))
    if not has_email:
        findings.append(Finding(category="Submission", severity=Severity.HIGH, title='No corresponding author email', detail='A valid email address is required for correspondence.', evidence='No email found in manuscript', confidence=0.95, action='Add corresponding author email'))
    # Novelty/contribution statement
    has_contribution = bool(re.search(r'(?:contribut|novelty|what\s+this|we\s+(?:propose|present|introduce|develop)|our\s+(?:contribut|key))', body, re.IGNORECASE))
    if not has_contribution:
        findings.append(Finding(category="Submission", severity=Severity.HIGH, title='No explicit contribution statement', detail='Reviewers need a clear statement of what is new. State your contribution explicitly.', evidence='No contribution/novelty statement found', confidence=0.85, action='Add an explicit contribution statement (e.g., "The contributions are: 1)... 2)... 3)...")'))
    # Acknowledgment section
    has_ack = bool(re.search(r'(?:acknowledgment|acknowledgement|\d+\.?\s*acknowledgment)', body, re.IGNORECASE))
    required_stmts = rules.get('required_statements', [])
    if 'Acknowledgment' in required_stmts and not has_ack:
        findings.append(Finding(category="Submission", severity=Severity.HIGH, title='Missing Acknowledgment section', detail='This venue requires an Acknowledgment section.', evidence='Acknowledgment not found', confidence=0.90, action='Add Acknowledgment section'))
    # Clinical trial registration (medical papers)
    if re.search(r'(?:clinical\s+trial|patient|participant|cohort|randomiz)', body, re.IGNORECASE):
        has_reg = bool(re.search(r'(?:ClinicalTrials\.gov|ISRCTN|ISRCTN|registered|registration\s+(?:number|no))', body, re.IGNORECASE))
        if not has_reg:
            findings.append(Finding(category="Submission", severity=Severity.HIGH, title='Clinical research without trial registration', detail='Clinical/patient research should have a trial registration number.', evidence='Clinical keywords found, no registration', confidence=0.80, action='Register the trial at ClinicalTrials.gov or equivalent and include the registration number'))
    # Limitations < 3 sentences (superficial)
    lim_match = re.search(r'(?:limitations?|\d+\.?\s*limitations?)\s*[:\.]?\s*(.*?)(?:\d+\.\s|conclusion|future\s+work|references)', body, re.IGNORECASE | re.DOTALL)
    if lim_match:
        lim_text = lim_match.group(1)
        lim_sentences = [s for s in re.split(r'[.!?]', lim_text) if len(s.strip()) > 10]
        if 0 < len(lim_sentences) < 3:
            findings.append(Finding(category="Submission", severity=Severity.MEDIUM, title='Superficial Limitations section', detail=f'Only {len(lim_sentences)} sentence(s). Reviewers expect thorough discussion of limitations.', evidence=f'{len(lim_sentences)} sentence(s) in Limitations', confidence=0.75, action='Expand Limitations: discuss validity threats, generalizability, methodological constraints'))
    return findings
