"""Trial registration + IRB/consent + data availability engine.

Detects the three most common medical/life-science desk-reject triggers:
1. RCTs without trial registration IDs (NCT, ISRCTN, ChiCTR, etc.)
2. Human/animal studies without ethics approval or informed consent
3. Funded work without data/code availability statements

Based on: ICMJE 2024, WMA Helsinki 2024, COPE 2024, PLAN S, OSTP Nelson Memo.
Severity: HIGH for trial registration + ethics, MEDIUM for availability.
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

# Trial registry ID patterns
_REGISTRY_IDS = re.compile(
    r"\b(?:NCT\d{8}|ISRCTN\d{8,10}|ChiCTR[\w-]+\d+|ACTRN\d{14}|"
    r"EudraCT\s*\d{4}-\d{6}-\d{2}|DRKS\d{6}|UTRN[A-Z]?\d+|"
    r"PACTR[\w-]+\d+|JPRN-[A-Z]+-\d+|IRCT\d{8,12}|"
    r"CHICTR[\w-]+\d+|NCTR\d+|TCTR[\w-]+\d+)",
    re.IGNORECASE
)

# Ethics/IRB approval patterns
_ETHICS_PATTERNS = [
    r"(?:ethics|IRB|IEC|institutional\s+review\s+board|ethics\s+committee|"
    r"review\s+board|ethical\s+approval|approved\s+by)\s+(?:committee|board|approval|review)",
    r"(?:was|were)\s+(?:approved|reviewed|authorized)\s+by\s+(?:the\s+)?(?:ethics|IRB|IEC|institutional\s+review)",
    # Real-world phrasing: the IRB usually follows an institution name
    # ("approved by the Example University IRB (Protocol #2024-118)").
    r"approved\s+by\s+(?:the\s+)?[a-z][\w\s,&\-]{0,60}?(?:irb|iec|institutional\s+review\s+board|ethics\s+committee)\b",
    r"ethical\s+(?:approval|clearance|permit)",
    r"institutional\s+review\s+board\s+\((?:IRB|IEC)\)",
    r"experiment(?:s)?\s+were\s+performed\s+(?:in\s+accordance|according)\s+with",
]

# Informed consent patterns
_CONSENT_PATTERNS = [
    r"informed\s+consent",
    r"written\s+consent",
    r"oral\s+consent",
    r"consent\s+(?:was\s+)?(?:obtained|received|collected|given|provided)",
    r"consent\s+(?:form|document|process)",
    r"participant(?:s)?\s+(?:gave|provided|signed|gave\s+written)\s+(?:informed\s+)?consent",
]

# Animal welfare patterns
_ANIMAL_WELFARE_PATTERNS = [
    r"(?:IACUC|institutional\s+animal\s+(?:care|committee))",
    r"animal\s+(?:care|use|welfare)\s+(?:committee|board)",
    r"ARRIVE\s+(?:guidelines|checklist)",
    r"approved\s+by\s+(?:the\s+)?(?:animal|veterinary)",
]

# Data/code availability patterns
_AVAILABILITY_PATTERNS = [
    r"data\s+(?:availability|sharing|access)\s+statement",
    r"code\s+(?:availability|sharing|access)\s+statement",
    r"(?:data|code)\s+(?:is|are)\s+(?:available|accessible|deposited)",
    r"(?:available|obtainable)\s+(?:from|upon|on)\s+(?:the\s+)?(?:corresponding\s+author|first\s+author|request)",
    r"available\s+on\s+reasonable\s+request",
    r"supplementary\s+(?:data|material|information)\s+(?:is\s+)?(?:available|attached)",
    r"github\.com|zenodo\.org|figshare\.com|dryad\.org|osf\.io",
]

# Study type detection
_RCT_PATTERNS = [
    r"randomized\s+controlled\s+trial|randomised\s+controlled\s+trial|\bRCT\b",
    r"randomly\s+(?:assigned|allocated|allocated\s+to)",
    r"random\s+(?:assignment|allocation|ization)",
]

_HUMAN_PATTERNS = [
    r"participants?\s+(?:were|was|enrolled|recruited)",
    r"patients?\s+(?:were|was|enrolled|recruited|included)",
    r"subjects?\s+(?:were|was|enrolled|recruited)",
    r"informed\s+consent",
    r"human\s+(?:subjects?|participants?)",
]

_ANIMAL_PATTERNS = [
    r"\bmice\b|\brats?\b|\bzebrafish\b|\bmouse\b|\brat\b",
    r"animal\s+(?:model|study|experiment)",
    r"rodents?\b",
]

# Funding detection
_FUNDER_PATTERNS = [
    r"(?:funded|supported|financed)\s+by",
    r"(?:grant|contract|award)\s+(?:number|no\.?|#|ID)",
    r"funding\s+(?:source|agency|body|organization)",
]


def _detect_study_type(body: str) -> dict:
    """Detect the type of study from manuscript text."""
    low = body.lower()
    return {
        "is_rct": any(re.search(p, low) for p in _RCT_PATTERNS),
        "is_human": any(re.search(p, low) for p in _HUMAN_PATTERNS),
        "is_animal": any(re.search(p, low) for p in _ANIMAL_PATTERNS),
        "has_funder": any(re.search(p, low) for p in _FUNDER_PATTERNS),
        "has_registry": bool(_REGISTRY_IDS.search(body)),
        "has_ethics": any(re.search(p, low) for p in _ETHICS_PATTERNS),
        "has_consent": any(re.search(p, low) for p in _CONSENT_PATTERNS),
        "has_animal_welfare": any(re.search(p, low) for p in _ANIMAL_WELFARE_PATTERNS),
        "has_availability": any(re.search(p, low) for p in _AVAILABILITY_PATTERNS),
    }


def run(doc: Document, ctx: object) -> List[Finding]:
    findings = []
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return findings

    study = _detect_study_type(body)

    # 1. RCT without trial registration
    if study["is_rct"] and not study["has_registry"]:
        findings.append(Finding(
            category="Trial Registration", severity=Severity.HIGH,
            title="RCT detected without trial registration ID",
            detail="Randomized controlled trials must be registered before enrollment (ICMJE 2024, WHO). "
                   "No trial registration ID (NCT, ISRCTN, ChiCTR, ACTRN, EudraCT, DRKS) was found.",
            evidence="RCT vocabulary detected; no registry ID found",
            confidence=0.85,
            action="Register the trial at ClinicalTrials.gov (NCT), ISRCTN, or a WHO ICTRP primary registry, "
                   "and include the registration ID in the abstract and methods"))

    # 2. Human study without ethics approval
    if study["is_human"] and not study["has_ethics"]:
        findings.append(Finding(
            category="Ethics", severity=Severity.HIGH,
            title="Human study detected without ethics approval statement",
            detail="Research involving human participants requires explicit ethics/IRB approval "
                   "statement (WMA Helsinki 2024, ICMJE). No ethics approval language was found.",
            evidence="Human participant vocabulary detected; no ethics/IRB approval statement found",
            confidence=0.80,
            action="Add an ethics approval statement including the IRB/IEC name, approval number, "
                   "and date of approval to the Methods section"))

    # 3. Human study without informed consent
    if study["is_human"] and not study["has_consent"]:
        findings.append(Finding(
            category="Ethics", severity=Severity.HIGH,
            title="Human study detected without informed consent statement",
            detail="Research involving human participants requires documented informed consent "
                   "(WMA Helsinki 2024). No informed consent language was found.",
            evidence="Human participant vocabulary detected; no informed consent statement found",
            confidence=0.80,
            action="Add a statement confirming informed consent was obtained from all participants, "
                   "or explain why consent was waived"))

    # 4. Animal study without welfare statement
    if study["is_animal"] and not study["has_animal_welfare"]:
        findings.append(Finding(
            category="Ethics", severity=Severity.MEDIUM,
            title="Animal study detected without welfare compliance statement",
            detail="Animal research requires IACUC/animal ethics committee approval and ARRIVE "
                   "guidelines compliance. No animal welfare statement was found.",
            evidence="Animal vocabulary detected; no IACUC/ARRIVE statement found",
            confidence=0.70,
            action="Add IACUC/animal ethics approval and confirm ARRIVE guidelines compliance"))

    # 5. Funded work without data availability
    if study["has_funder"] and not study["has_availability"]:
        findings.append(Finding(
            category="Data Availability", severity=Severity.MEDIUM,
            title="Funded work without data/code availability statement",
            detail="Many funders (NIH, ERC, Wellcome Trust) now require data/code availability "
                   "statements. No data or code availability language was found.",
            evidence="Funding detected; no data/code availability statement found",
            confidence=0.65,
            action="Add a Data Availability Statement indicating where data/code can be accessed, "
                   "or state any restrictions"))

    return findings
