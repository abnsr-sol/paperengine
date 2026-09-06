"""Reproducibility engine: dataset links, code availability, protocol, hyperparameters."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

REPO_PATTERNS = r'github\.com|gitlab\.com|bitbucket\.org|zenodo|figshare|dryad|osf\.io|protocols\.io|kaggle|paperswithcode|hdl\.handle\.net|doi\.org'
DATA_STATEMENT = r'(?:data\s+(?:availab|deposited|available|repository|set)|dataset|code\s+(?:availab|repository|available)|github\.com|zenodo|figshare|dryad|osf\.io|supplementary)'

def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text
    if not body:
        return findings
    # Data/code availability statement
    has_data_stmt = bool(re.search(DATA_STATEMENT, body, re.IGNORECASE))
    has_repo_link = bool(re.search(REPO_PATTERNS, body, re.IGNORECASE))
    if not has_data_stmt:
        findings.append(Finding(category="Reproducibility", severity=Severity.HIGH, title='No data/code availability statement', detail='No mention of datasets, code repositories, or data availability. Most major publishers require this.', evidence='No data/code/repo keywords found', confidence=0.90, action='Add a Data Availability Statement with links to datasets and code'))
    elif not has_repo_link:
        findings.append(Finding(category="Reproducibility", severity=Severity.MEDIUM, title='Data mentioned but no repository link', detail='Data/code mentioned but no link to a repository (GitHub, Zenodo, Figshare, etc.).', evidence='Data keywords present, no repo URLs', confidence=0.80, action='Add a URL to your data/code repository'))
    # Hyperparameters / training details (CS/ML papers)
    if re.search(r'(?:neural\s+network|deep\s+learn|train|epoch|batch|optimiz|model|architecture|layer)', body, re.IGNORECASE):
        has_hyper = bool(re.search(r'(?:hyperparameter|learning\s+rate|batch\s+size|epoch|optimizer|weight\s+decay|dropout|Adam|SGD)', body, re.IGNORECASE))
        if not has_hyper:
            findings.append(Finding(category="Reproducibility", severity=Severity.HIGH, title='No hyperparameters or training details', detail='ML/AI paper detected but no hyperparameters (learning rate, batch size, epochs, optimizer). Reviewers expect reproducibility details.', evidence='ML keywords found, no hyperparameter terms', confidence=0.85, action='Report all hyperparameters, optimizer settings, and training details'))
    # Random seed
    if re.search(r'(?:random|shuffle|split|cross.valid)', body, re.IGNORECASE):
        has_seed = bool(re.search(r'(?:random\s+seed|seed\s*=|reproducib)', body, re.IGNORECASE))
        if not has_seed:
            findings.append(Finding(category="Reproducibility", severity=Severity.MEDIUM, title='No random seed mentioned', detail='Random splitting/shuffling mentioned but no random seed reported. Essential for reproducibility.', evidence='Randomness mentioned, no seed', confidence=0.75, action='Report random seed for all stochastic processes'))
    # Computational resources
    if re.search(r'(?:train|GPU|CUDA|epoch|batch)', body, re.IGNORECASE):
        has_compute = bool(re.search(r'(?:GPU|TPU|CUDA|V100|A100|RTX|compute|hardware|memory|hours)', body, re.IGNORECASE))
        if not has_compute:
            findings.append(Finding(category="Reproducibility", severity=Severity.LOW, title='No computational resources reported', detail='No mention of GPU, hardware, or computation time. Helps reviewers assess feasibility.', evidence='No hardware/compute terms found', confidence=0.60, action='Report GPU type, memory, and training time'))
    # Dataset description
    if re.search(r'(?:dataset|benchmark|corpus|evaluation)', body, re.IGNORECASE):
        has_desc = bool(re.search(r'(?:\d+\s*(?:samples|images|subjects|patients|participants|instances|videos)|split\s+(?:train|test|valid)|preprocess)', body, re.IGNORECASE))
        if not has_desc:
            findings.append(Finding(category="Reproducibility", severity=Severity.MEDIUM, title='No dataset description', detail='Dataset/benchmark mentioned but no description of size, source, preprocessing, or splits.', evidence='Dataset keywords found, no description', confidence=0.75, action='Describe dataset: size, source, preprocessing, train/test split'))
    # Ablation study (CS/AI papers)
    if re.search(r'(?:our\s+(?:method|approach|model|framework)|proposed\s+(?:method|approach|model))', body, re.IGNORECASE):
        has_ablation = bool(re.search(r'(?:ablation|component\s+analysis|without\s+(?:component|module|layer|branch))', body, re.IGNORECASE))
        if not has_ablation:
            findings.append(Finding(category="Reproducibility", severity=Severity.MEDIUM, title='No ablation study', detail='Proposed method claimed but no ablation study to justify design choices. Reviewers expect component analysis.', evidence='Proposed method found, no ablation', confidence=0.70, action='Add ablation study showing contribution of each component'))
    # Baseline comparison
    if re.search(r'(?:our\s+(?:method|approach|model|framework)|proposed\s+(?:method|approach))', body, re.IGNORECASE):
        has_baseline = bool(re.search(r'(?:baseline|SOTA|state.of.the.art|compared\s+to|outperform)', body, re.IGNORECASE))
        if not has_baseline:
            findings.append(Finding(category="Reproducibility", severity=Severity.HIGH, title='No baseline comparison', detail='Proposed method but no comparison with existing baselines or SOTA. Essential for establishing contribution.', evidence='No baseline/SOTA comparison found', confidence=0.85, action='Compare with at least 3 relevant baselines'))
    return findings
