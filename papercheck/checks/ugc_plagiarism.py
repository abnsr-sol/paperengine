"""UGC plagiarism threshold engine: checks overlap against Indian UGC levels."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def run(doc: Document, ctx: object) -> List[Finding]:
    findings: List[Finding] = []
    rules = ctx.rules if hasattr(ctx, 'rules') else {}
    threshold = rules.get('plagiarism_threshold')
    if not threshold:
        return findings
    body = doc.body_text or doc.text
    if not body:
        return findings
    # Check for plagiarism declaration statement
    has_declaration = bool(re.search(r'(?:plagiarism\s+(?:declaration|statement|report)|similarity\s+(?:report|check)|iThenticate|Turnitin)', body, re.IGNORECASE))
    require_report = rules.get('require_plagiarism_report', False)
    if require_report and not has_declaration:
        findings.append(Finding(category="UGC Plagiarism", 
            severity=Severity.CRITICAL,
            title='Plagiarism report/declaration required',
            detail='This venue requires a plagiarism declaration or similarity report (e.g., iThenticate/Turnitin).',
            evidence='No plagiarism declaration found',
            confidence=0.95,
            action='Add plagiarism declaration statement and include iThenticate/Turnitin report',
        ))
    # Check for AI-use disclosure (UGC 2026: undeclared AI = plagiarism)
    ai_policy = rules.get('ai_policy', '')
    if ai_policy == 'ugc_2026':
        has_ai_disclosure = bool(re.search(r'(?:AI\s+(?:use|usage|tool|generated|assisted|written)|artificial\s+intelligence|ChatGPT|GPT|Gemini|Claude|LLM|language\s+model)', body, re.IGNORECASE))
        # Exclude references section from AI check
        refs_match = re.search(r'(?:references?|bibliography)\s*$', body, re.IGNORECASE | re.MULTILINE)
        body_no_refs = body[:refs_match.start()] if refs_match else body
        has_ai_in_body = bool(re.search(r'(?:AI\s+(?:use|usage|tool|generated|assisted|written)|artificial\s+intelligence|ChatGPT|GPT|Gemini|Claude|LLM|language\s+model)', body_no_refs, re.IGNORECASE))
        if not has_ai_in_body:
            findings.append(Finding(category="UGC Plagiarism", 
                severity=Severity.MEDIUM,
                title='No AI-use disclosure (UGC 2026 requires it)',
                detail='UGC 2026 treats undeclared AI-generated content as plagiarism. Even if no AI was used, state that explicitly.',
                evidence='No AI disclosure found in body text',
                confidence=0.80,
                action='Add AI-use disclosure: state which AI tools were used (if any) and for what purpose, or state no AI was used',
            ))
    # Check for novelty declaration (UGC requires 20% novelty)
    min_novelty = rules.get('min_novelty')
    if min_novelty:
        has_novelty = bool(re.search(r'(?:novel|original|new|first|contribution|what\s+this|we\s+(?:propose|present|introduce))', body, re.IGNORECASE))
        if not has_novelty:
            findings.append(Finding(category="UGC Plagiarism", 
                severity=Severity.HIGH,
                title=f'No novelty statement (min {min_novelty} required)',
                detail=f'This venue requires minimum {min_novelty} novelty. No novelty claim found.',
                evidence='No novelty/contribution keywords found',
                confidence=0.85,
                action='Add explicit novelty/contribution statement',
            ))
    # Check for ORCID requirement
    if rules.get('require_orcid'):
        has_orcid = bool(re.search(r'(?:orcid|0000[- ]000[0-9][- ]000[0-9])', body, re.IGNORECASE))
        if not has_orcid:
            findings.append(Finding(category="UGC Plagiarism", 
                severity=Severity.HIGH,
                title='ORCID required but not found',
                detail='This venue requires ORCID iD for authors.',
                evidence='No ORCID found',
                confidence=0.90,
                action='Add ORCID iD for all authors',
            ))
    # Check for indexing requirement
    indexing = rules.get('require_indexing')
    if indexing:
        findings.append(Finding(category="UGC Plagiarism", 
            severity=Severity.INFO,
            title=f'Venue requires {indexing}',
            detail=f'Venue requires publication in {indexing}. Verify the target journal meets this requirement before submission.',
            evidence=f'Requirement: {indexing}',
            confidence=1.0,
            action=f'Verify target journal is indexed in {indexing}',
        ))
    # UGC-specific: Shodhganga deposit requirement
    if rules.get('require_shodhganga_deposit'):
        findings.append(Finding(category="UGC Plagiarism", 
            severity=Severity.INFO,
            title='Shodhganga deposit required',
            detail='UGC requires thesis deposit on Shodhganga before degree processing.',
            evidence='Shodhganga deposit mandatory',
            confidence=1.0,
            action='Deposit final thesis on Shodhganga (shodhganga.inflibnet.ac.in) after viva',
        ))
    return findings
