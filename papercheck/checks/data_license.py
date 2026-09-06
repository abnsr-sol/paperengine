"""Data licensing and FAIR engine: dataset license, versioning, raw data, formats, provenance."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_CC = r"creative\s+commons|CC[- ]?BY|CC0|open\s+license|license[d]?\s+under"
_REPO = r"zenodo|figshare|dryad|github|gitlab|kaggle|osf\.io|ieee\s+dataport|mendeley|data\s+in\s+brief|4TU"
_RAW = r"raw\s+data|original\s+measurements|underlying\s+data|source\s+data|individual\s+(?:participant|patient)\s+data"
_FORMAT = r"\.(?:csv|tsv|json|xml|parquet|hdf5?|mat|npy|nc)|machine-?readable|open\s+format"
_PROP = r"proprietary\s+format|password-?protected|encrypted\s+file|licensed\s+software\s+(?:format|file)"
_DOI = r"doi\s*[:/]|https?://doi\.org|data\.dryad|zenodo\.org/records"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Data License", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    out = []
    has_data_stmt = re.search(r"data\s+availability|availability\s+of\s+data|data\s+sharing", low)
    if not has_data_stmt and not re.search(_REPO, low):
        out.append(_f(Severity.MEDIUM, "No data availability or sharing statement", "FAIR/open-science policies and most funders require stating where data live.",
                      "No data availability keywords or repository links", 0.75, "Add a Data Availability statement naming the repository and identifier"))
    if re.search(_REPO, low) and not re.search(_CC + r"|public\s+domain|open\s+(?:access|data)", low):
        out.append(_f(Severity.LOW, "Shared data without an open license", "Repositories require a license (CC0/CC-BY) for reuse; FAIR requires a clear reuse license.",
                      "Repository link found, no license terms", 0.65, "State the license (e.g., CC BY 4.0) in the data availability statement"))
    if re.search(_REPO, low) and not re.search(r"version|v\d+(?:\.\d+)?|released\s+(?:on|in)|updated", low):
        out.append(_f(Severity.LOW, "Dataset without version indication", "Versioned datasets are required for reproducibility.",
                      "Repository found, no version mention", 0.55, "Cite the dataset version (e.g., v1.2) and release date"))
    if re.search(_DOI, low) and not re.search(r"cite(?:d| this| the)|citation:\s*\[?\d|please\s+cite", low):
        out.append(_f(Severity.LOW, "Data DOI present but not cited", "FAIR 'Findable' requires a citable identifier cited in the paper.",
                      "DOI found, no citation instruction", 0.55, "Add the recommended citation for the dataset"))
    if re.search(_PROP, low):
        out.append(_f(Severity.MEDIUM, "Proprietary or protected data format mentioned", "Reviewers flag non-machine-readable or locked data formats.",
                      "Matched: " + str(set(re.findall(_PROP, low))), 0.70, "Convert data to open formats (CSV/JSON) and remove access barriers"))
    if not re.search(_RAW + r"|" + _FORMAT, low) and re.search(r"dataset|collected\s+data|our\s+data", low):
        out.append(_f(Severity.LOW, "No raw data or format description", "Papers describing datasets should say what raw form the data take and in what format.",
                      "Dataset mentioned, no raw-data/format terms", 0.60, "Describe the raw data and file formats"))
    return out
