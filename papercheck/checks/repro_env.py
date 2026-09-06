"""Reproducibility environment engine: code availability, Docker/conda environment, seeds, protocol registration."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Repro Env", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    is_ml = bool(re.search(r"neural\s+network|deep\s+learning|machine\s+learning|trained\s+(?:our|the)\s+model|dataset|benchmark", low))
    # code availability
    if is_ml and not re.search(r"code\s+(?:is|are|will\s+be)?\s*(?:publicly\s+)?available|github\.com|gitlab\.com|zenodo|software\s+availability|code\s+repository|open\s+source", low):
        out.append(_f(Severity.MEDIUM, "ML paper without code-availability statement", "Reproducibility norms (and many venues) require a link to code.",
                      "ML keywords, no code availability", 0.75, "Release code (GitHub/Zenodo) and state availability"))
    # computational environment
    if is_ml and not re.search(r"docker|conda|pip\s+install|environment\.yml|requirements\.txt|virtual\s+environment|python\s+\d", low):
        out.append(_f(Severity.LOW, "No computational-environment specification", "FAIR/reproducibility requires stating the environment (Docker image, conda env, dependency versions).",
                      "No Docker/conda/version terms", 0.60, "Provide a Dockerfile/conda env and pin dependency versions"))
    # protocol registration for lab/clinical work
    if re.search(r"clinical\s+trial|randomized|protocol", low) and not re.search(r"registered|registration\s+number|ClinicalTrials\.gov|PROSPERO|OSF", low):
        out.append(_f(Severity.MEDIUM, "Study protocol not registered", "Prospective registration (ClinicalTrials.gov/PROSPERO/OSF) is required for trials and recommended for other studies.",
                      "Trial/protocol keywords, no registration", 0.70, "Register the study and include the registration number"))
    # unit-level: data split leakage
    if is_ml and re.search(r"train(?:ed|ing)\b.{0,80}(?:test|validation)|(?:test|validation)\s+set", low) and not re.search(r"hold-?out|cross-?validation|split|leakage|stratified", low):
        out.append(_f(Severity.LOW, "Train/test split not described", "Papers must describe the data split to rule out leakage and allow reproduction.",
                      "Training/test mentioned, no split description", 0.55, "Describe the train/validation/test split and stratification"))
    return out