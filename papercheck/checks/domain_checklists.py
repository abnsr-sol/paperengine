"""Domain-specific reporting checklists: STARD, TRIPOD, CARE, SRQR/COREQ (qualitative), SPIRIT (protocols)."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_DIAG = r'diagnostic\s+(?:accuracy|test)|sensitivity\s+and\s+specificity|ROC|AUC\b|receiver\s+operating'
_PREDICT = r'predict(?:ion|ive)?\s+model|risk\s+score|prognostic\s+model|nomogram|machine\s+learning\s+model.*predict'
_CASE = r'case\s+report|we\s+report\s+a\s+(?:case|patient)'
_QUAL = r'qualitative\s+(?:study|research|analysis)|semi-?structured\s+interviews|focus\s+groups|thematic\s+analysis|grounded\s+theory|phenomenolog'
_PROTOCOL = r'study\s+protocol|trial\s+protocol|SPIRIT'


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Reporting Guidelines", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []

    if re.search(_DIAG, body, re.IGNORECASE):
        checks = [
            (r'reference\s+standard|gold\s+standard', "Reference standard defined",
             "STARD requires naming the reference standard (and blinding to it)."),
            (r'\bsample\s+size|patients?\s+(?:included|recruited)|N\s*=\s*\d', "Sample size stated",
             "STARD requires the number of participants/lesions analyzed."),
            (r'sensitivity|specificity|accuracy|AUC|ROC', "Accuracy measures reported",
             "Report sensitivity/specificity (or AUC) with confidence intervals."),
        ]
        for pat, name, why in checks:
            if not re.search(pat, body, re.IGNORECASE):
                out.append(_f(Severity.MEDIUM, "Diagnostic study missing " + name,
                              "STARD item missing: " + why,
                              "Diagnostic keywords found, not found: " + name, 0.75,
                              "Add " + name + " per STARD 2015"))

    if re.search(_PREDICT, body, re.IGNORECASE):
        checks = [
            (r'validat(?:ed|ion)|external|test\s+set|hold-?out', "Model validation",
             "TRIPOD requires reporting discrimination and calibration, ideally externally."),
            (r'AUC|C-?statistic|calibration|Brier|discrimination', "Discrimination/calibration",
             "Prediction models must report discrimination (C-statistic/AUC) and calibration."),
            (r'predict(?:ors?|ive)\s+(?:variables?|features?)|covariates', "Predictors defined",
             "All predictors and how they were measured must be listed."),
        ]
        for pat, name, why in checks:
            if not re.search(pat, body, re.IGNORECASE):
                out.append(_f(Severity.MEDIUM, "Prediction model missing " + name,
                              "TRIPOD item missing: " + why,
                              "Prediction keywords found, not found: " + name, 0.75,
                              "Add " + name + " per TRIPOD"))

    if re.search(_CASE, body, re.IGNORECASE) and not re.search(r'CARE\b|case\s+report\s+guidelines', body, re.IGNORECASE):
        if not re.search(r'consent\s+(?:for\s+publication|to\s+publish|was\s+obtained)', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Case report without consent-for-publication",
                          "CARE requires patient consent for publication.",
                          "Case-report keywords found, no consent", 0.80,
                          "Add written informed consent-for-publication (per CARE)"))

    if re.search(_QUAL, body, re.IGNORECASE):
        checks = [
            (r'reflexiv|positionalit|researcher\s+(?:role|background)|the\s+author', "Reflexivity statement",
             "COREQ/SRQR require disclosing the researcher's position and assumptions."),
            (r'saturat(?:ed|ion)', "Data saturation discussed",
             "Qualitative work should justify when/why data collection stopped."),
            (r'member\s+checking|participant\s+validation|respondent\s+validation', "Member checking",
             "COREQ recommends participants validating findings."),
            (r'cod(?:ing|es?)|thematic|framework|software\s+\(?NVivo|MAXQDA', "Coding process described",
             "Describe how data were coded and themes derived."),
        ]
        for pat, name, why in checks:
            if not re.search(pat, body, re.IGNORECASE):
                out.append(_f(Severity.MEDIUM, "Qualitative study missing " + name,
                              "COREQ/SRQR item missing: " + why,
                              "Qualitative keywords found, not found: " + name, 0.70,
                              "Add " + name + " per COREQ (32 items) / SRQR (21 items)"))

    if re.search(_PROTOCOL, body, re.IGNORECASE):
        if not re.search(r'\bNCT\d+|clinicaltrials\.gov|registration|registered', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Trial protocol without registration",
                          "SPIRIT requires reporting trial registration and the protocol version.",
                          "Protocol keywords found, no registration", 0.80,
                          "Register the protocol and cite the registration number (SPIRIT)"))

    return out
