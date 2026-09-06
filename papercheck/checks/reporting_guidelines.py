"""EQUATOR reporting-guideline compliance: CONSORT (RCT), PRISMA (reviews), STROBE (observational), ARRIVE (animal)."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

def _f(cat, sev, title, detail, evidence, conf, action):
    return Finding(cat, sev, title, detail, evidence, action, conf)

def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []
    is_rct = bool(re.search(r'randomized\s+controlled\s+trial|randomised\s+controlled\s+trial|\bRCT\b', body, re.IGNORECASE))
    is_sr = bool(re.search(r'systematic\s+review|meta-?analysis|\bPRISMA\b', body, re.IGNORECASE))
    is_obs = bool(re.search(r'\bcohort\b|case-?control|case\s+series|cross-?sectional|observational', body, re.IGNORECASE))
    is_animal = bool(re.search(r'\bmice\b|\brats\b|zebrafish|animal\s+(?:model|study)', body, re.IGNORECASE))

    if is_rct:
        checks = [
            (r'consort|participant\s+flow|flow\s+diagram', "CONSORT flow diagram",
             "RCT reports need a participant-flow diagram (CONSORT item 13)."),
            (r'\bNCT\d+|trial\s+registration|clinicaltrials\.gov|registered', "Trial registration number",
             "CONSORT requires the trial registration number and registry name."),
            (r'random(?:ization|ly|ized)|allocat', "Randomization method",
             "Describe the randomization and allocation-concealment method."),
            (r'blind(?:ed|ing)?|mask(?:ed|ing)?', "Blinding",
             "State who was blinded: participants, clinicians, outcome assessors."),
            (r'sample\s+size|power\s+(?:calculation|analysis)|a\s+priori', "Sample-size justification",
             "Provide the sample-size calculation / power analysis."),
        ]
        for pat, name, why in checks:
            if not re.search(pat, body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.HIGH, "RCT missing " + name,
                              "CONSORT checklist item missing: " + why,
                              "RCT detected, not found: " + name, 0.80,
                              "Add the missing " + name + " to comply with CONSORT"))
    if is_sr:
        checks = [
            (r'PROSPERO|registered|protocol', "Protocol registration (PROSPERO)",
             "Systematic reviews should be registered on PROSPERO before data extraction."),
            (r'search(?:ed)?\s+(?:the|in|across)|database(?:s)?\s+search|PubMed|Scopus|Web\s+of\s+Science|Embase|Cochrane',
             "Search strategy", "Report databases searched, dates, and the full search string."),
            (r'risk\s+of\s+bias|ROB|Newcastle|NOS|QUADAS|GRADE|Cochrane', "Risk-of-bias assessment",
             "PRISMA requires a risk-of-bias assessment with the tool named."),
            (r'flow\s+diagram|PRISMA\s+flow|study\s+selection|screening|excluded', "PRISMA flow diagram",
             "Include the PRISMA 2020 flow diagram of study selection."),
        ]
        for pat, name, why in checks:
            if not re.search(pat, body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.HIGH, "Systematic review missing " + name,
                              "PRISMA 2020 item missing: " + why,
                              "Review detected, not found: " + name, 0.80,
                              "Add the missing " + name + " per PRISMA 2020"))
        if re.search(r'meta-?analysis|pooled|effect\s+size|forest\s+plot', body, re.IGNORECASE):
            if not re.search(r'I\s*2|I-squared|heterogeneity|tau|tau', body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.MEDIUM, "Heterogeneity (I2) not reported",
                              "Meta-analyses should report between-study heterogeneity (I2, tau).",
                              "Meta-analysis detected, no heterogeneity terms", 0.75,
                              "Report I2 / tau and state the model (fixed vs random)"))
            if not re.search(r'funnel\s+plot|publication\s+bias|Egger|trim-and-fill', body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.MEDIUM, "Publication bias not assessed",
                              "Meta-analyses should assess publication bias (funnel plot, Egger test).",
                              "Meta-analysis detected, no publication-bias terms", 0.70,
                              "Add a funnel plot or Egger test"))
    if is_obs and not is_rct and not is_sr:
        out.append(_f("Reporting Guidelines", Severity.INFO, "Observational study - consider STROBE",
                      "Observational designs should follow the STROBE 22-item checklist.",
                      "Observational keywords detected", 0.80,
                      "Run the STROBE checklist (strobe-statement.org) before submission"))
    if is_animal:
        checks = [
            (r'IACUC|ethics\s+(?:approval|committee)|animal\s+(?:care|welfare)|ARRIVE', "Ethics approval (IACUC/ARRIVE)",
             "Animal studies need institutional animal-care approval."),
            (r'random(?:ization|ly|ized)', "Randomization",
             "ARRIVE requires reporting of randomization to groups."),
            (r'blind(?:ed|ing)?|mask(?:ed|ing)?', "Blinding",
             "ARRIVE requires reporting of blinding (who was blinded to what)."),
            (r'sample\s+size|power\s+(?:calculation|analysis)', "Sample-size justification",
             "ARRIVE requires a sample-size justification."),
        ]
        for pat, name, why in checks:
            if not re.search(pat, body, re.IGNORECASE):
                out.append(_f("Reporting Guidelines", Severity.HIGH, "Animal study missing " + name,
                              "ARRIVE 2.0 item missing: " + why,
                              "Animal study detected, not found: " + name, 0.80,
                              "Add " + name + " per ARRIVE 2.0 (Essential 10)"))
    return out
