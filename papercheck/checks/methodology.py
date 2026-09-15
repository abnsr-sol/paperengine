"""Methodology & research-design: ethics, consent, trials, datasets, benchmarks, ablation, compute."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_CLINICAL = r'patient|participant|human\s+subject|clinical|trial|survey|cohort|hospital|volunteer'
_ANIMAL = r'\bmice\b|\brats\b|zebrafish|animal\s+model|rodent'
_TRIAL = r'trial|randomized|randomised|intervention'
_STUDY = r'\bstudy\b|cohort|case-control|observational'
_METHOD = r'we\s+(?:propose|present|introduce)|our\s+(?:method|model|framework|approach)|proposed\s+method'
# Non-human-subject research signals: a CS/engineering paper that merely
# mentions "hospital sites" or "clinical data" is not human-subjects
# research and must not be told to obtain IRB approval (vector-eval FP).
_NON_HUMAN = (r'simulation[- ]only|computer\s+simulation|in\s+silico|'
              r'synthetic\s+(?:data|dataset)|no\s+human\s+(?:subjects|participants)|'
              r'did\s+not\s+involve\s+(?:humans?|patients?|animals?)|'
              r'publicly\s+available\s+(?:dataset|benchmark)|\bpublic\s+datasets?\b')

def _f(sev, title, detail, evidence, conf, action):
    return Finding("Methodology", sev, title, detail, evidence, action, conf)

def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []
    clinical = bool(re.search(_CLINICAL, body, re.IGNORECASE))
    animal = bool(re.search(_ANIMAL, body, re.IGNORECASE))
    trial = bool(re.search(_TRIAL, body, re.IGNORECASE))
    study = bool(re.search(_STUDY, body, re.IGNORECASE))

    # Suppress only for genuinely non-human work: a paper that recruits or
    # enrolls people is human-subjects research even if it also uses
    # public datasets alongside.
    if clinical and not (re.search(_NON_HUMAN, body, re.IGNORECASE)
                         and not re.search(r'recruit|enrol|consent|questionnair|interview', body, re.IGNORECASE)):
        if not re.search(r'ethics\s+(?:committee|board|approval)|IRB|IEC\b|institutional\s+review|approval\s+(?:number|no\.?|ref)|protocol\s+(?:no\.?|number)', body, re.IGNORECASE):
            out.append(_f(Severity.CRITICAL if trial else Severity.HIGH,
                          "No ethics approval statement (IRB/IEC)",
                          "Human-subjects research requires institutional review board / ethics committee approval with a reference number.",
                          "Clinical keywords found, no ethics/IRB/IEC mention", 0.88,
                          "Add an ethics-approval statement with the committee name and approval number"))
        if not re.search(r'informed\s+consent|consent\s+(?:form|statement)|written\s+consent|provided\s+consent|signed\s+consent', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "No informed-consent statement",
                          "Human-subjects research must state how informed consent was obtained.",
                          "Clinical keywords found, no consent statement", 0.85,
                          "Add an informed-consent statement (add consent-for-publication if patients are identifiable)"))
        if trial:
            if not re.search(r'\bNCT\d+|clinicaltrials\.gov|registered\s+(?:in|with)|trial\s+registration', body, re.IGNORECASE):
                out.append(_f(Severity.HIGH, "Trial not registered (no registration number)",
                              "Interventional trials must be registered before enrollment and the number reported.",
                              "Trial keywords found, no registration number", 0.85,
                              "Register the trial (ClinicalTrials.gov or ICMJE registry) and report the number"))
            if not re.search(r'random(?:ly|ization|ized)|allocat|assign(?:ed|ment)', body, re.IGNORECASE):
                out.append(_f(Severity.MEDIUM, "Randomization method not described",
                              "Trial reports must describe how participants were randomized/allocated.",
                              "Trial keywords found, no randomization terms", 0.75,
                              "Describe randomization and allocation concealment"))
            if not re.search(r'blind(?:ed|ing)?|mask(?:ed|ing)?', body, re.IGNORECASE):
                out.append(_f(Severity.MEDIUM, "Blinding not described",
                              "Trial reports should state who was blinded (participants, clinicians, assessors).",
                              "Trial keywords found, no blinding terms", 0.70,
                              "State which parties were blinded and how"))

    if animal:
        if not re.search(r'IACUC|ARRIVE|animal\s+(?:care|welfare|ethics)|ethics\s+(?:approval|committee)|3Rs\b|replacement|refinement', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "No animal-ethics approval (IACUC/ARRIVE)",
                          "Animal research requires institutional animal-care approval and ARRIVE-compliant reporting.",
                          "Animal keywords found, no IACUC/ARRIVE/ethics mention", 0.85,
                          "Add animal-ethics approval statement and follow ARRIVE 2.0"))

    if study and not re.search(r'inclusion\s+(?:criteria|and\s+exclusion)|exclusion\s+criteria', body, re.IGNORECASE):
        out.append(_f(Severity.MEDIUM, "No inclusion/exclusion criteria",
                      "Study reports should pre-specify who/what was included and excluded.",
                      "Study keywords found, no criteria", 0.70,
                      "State explicit inclusion and exclusion criteria"))

    if re.search(r'\bdatasets?\b|benchmark', body, re.IGNORECASE) and re.search(r'\btrain|test|val(?:idation)?', body, re.IGNORECASE):
        if not re.search(r'\d[\d,]*\s*(?:samples?|images?|videos?|instances?|patients?|subjects?|clips?|frames?)|N\s*=\s*\d', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Dataset size not stated",
                          "Datasets should report their size (count of samples/images/patients).",
                          "Dataset keywords found, no explicit size", 0.75,
                          "Report the number of samples/instances per dataset"))
        if not re.search(r'train(?:ing)?\s*[/-]\s*(?:test|val)|80/20|70/30|90/10|k-fold|split', body, re.IGNORECASE):
            out.append(_f(Severity.LOW, "No explicit data split described",
                          "Mention the train/test/validation split so experiments are reproducible.",
                          "Dataset keywords found, no split ratio", 0.65,
                          "Describe the data split (e.g., 80/10/10, k-fold)"))

    # NOTE: "no comparison with existing methods" and "no ablation study" are
    # owned by `reproducibility` (single ownership — they were double-fired
    # here under different titles, confirmed on a live sample run).

    if re.search(r'train(?:ed|ing)?\b|model\s+was\s+trained', body, re.IGNORECASE):
        if not re.search(r'GPU|TPU|NVIDIA|A100|V100|RTX|CUDA|hours?\s+of\s+(?:training|compute)|compute\s+time|FLOPs|memory\s+usage|batch\s+size', body, re.IGNORECASE):
            out.append(_f(Severity.LOW, "Computational resources not reported",
                          "Reviewers expect a statement of hardware/training time for reproducibility.",
                          "Training keywords found, no hardware/time terms", 0.60,
                          "Report GPU/CPU hardware, training time, model size"))
    return out
