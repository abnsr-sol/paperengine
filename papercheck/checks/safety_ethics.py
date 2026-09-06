"""Safety & regulatory ethics engine: biosafety levels, DSMB, adverse events, HIPAA/GDPR compliance wording."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Safety Ethics", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    # biosafety for pathogen/cell work
    if re.search(r"pathogen|virus|bacteria|culture|infectious|bsl-?\d", low):
        if not re.search(r"bsl-?\d|biosafety\s+level|institutional\s+biosafety", low):
            out.append(_f(Severity.HIGH, "Pathogen/infectious work without biosafety level", "Work with pathogens must state the biosafety level (BSL-1/2/3) and approval.",
                          "Pathogen keywords, no BSL mention", 0.80, "State the biosafety level and committee approval in Methods"))
    # clinical safety oversight
    if re.search(r"clinical\s+trial|randomized|intervention|drug|vaccine|dos", low):
        if not re.search(r"data\s+safety\s+monitoring|DSMB|safety\s+committee|adverse\s+event", low):
            out.append(_f(Severity.MEDIUM, "Trial without safety-monitoring statement", "Interventional trials need a DSMB or equivalent safety oversight described.",
                          "Trial keywords, no DSMB/adverse-event terms", 0.65, "Describe the DSMB and adverse-event reporting in Methods"))
        if not re.search(r"adverse\s+(?:event|effect)|side\s+effect|complication", low):
            out.append(_f(Severity.MEDIUM, "No adverse-event reporting", "Trials must report adverse events even if none occurred.",
                          "Trial keywords, no adverse-event wording", 0.60, "Add an adverse-events subsection to Results"))
    # HIPAA / patient privacy (US context)
    if re.search(r"hipaa|protected\s+health\s+information|PHI\b", text) and not re.search(r"de-?identif|anonymiz|limited\s+data\s+set|waiver", low):
        out.append(_f(Severity.MEDIUM, "HIPAA data without de-identification statement", "US patient data requires de-identification or a documented waiver.",
                      "HIPAA/PHI mentioned, no de-identification", 0.70, "State the de-identification method (Safe Harbor/Expert Determination)"))
    # GDPR (EU context)
    if re.search(r"GDPR|personal\s+data|EU\s+patients|european\s+patients", text) and not re.search(r"consent|anonymiz|pseudonymiz|ethical\s+approval|data\s+protection", low):
        out.append(_f(Severity.MEDIUM, "EU personal data without GDPR safeguards", "GDPR requires consent/lawful basis and data-protection measures for personal data.",
                      "GDPR/personal-data mention, no safeguards", 0.70, "State the lawful basis, consent, and data-protection measures"))
    return out