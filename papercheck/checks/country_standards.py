"""Country standards & integrity-system profile engine.

Six national/regional research-integrity systems, each detected by funder or
jurisdiction signals in the manuscript itself (so unrelated papers are never
flagged):

  India   - UGC (Promotion of Academic Integrity) Regulations 2018 tiers,
            NIRF 2025 retraction penalty, ANRF/UGC-CARE context
  China   - MOE early-warning journal list policy, national retraction review
            disclosure, punishment for predatory-venue publishing
  USA     - OSTP Nelson Memo (2022) immediate open access, NIH Data Management
            & Sharing (2023) policy
  EU      - Plan S / cOAlition S rights-retention strategy, Horizon Europe OA
            mandate
  Japan   - MEXT misconduct guidelines (2014): fabrication/falsification/
            plagiarism definitions + due process, JSPS/JST integrity training
  Korea   - KCI similarity screening, KISTI R&D registration, national ethics
            training

Fires MEDIUM/LOW informational findings telling the author which national
obligations their funder/jurisdiction triggers. Never a fraud signal.
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    f = Finding("Country Standards", sev, title, detail, evidence, action, conf)
    f.source = "country_standards"
    return f


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return []
    low = body.lower()
    out: List[Finding] = []

    # ---------------- India ----------------
    if re.search(
        r"university\s+grants\s+commission|\bUGC\b|ANRF|SERB\b|DST\s+India|DBT\s+India|ICMR|CSIR\b|"
        r"Ministry\s+of\s+Education\s+\(India\)|MHRD|AICTE|Indian\s+(?:Council|Institute|National)\s+",
        body):
        out.append(_f(
            Severity.MEDIUM,
            "Indian funder detected: UGC 2018 plagiarism tiers + NIRF retraction penalty apply",
            "Work funded/affiliated with Indian agencies falls under the UGC "
            "(Promotion of Academic Integrity and Prevention of Plagiarism) "
            "Regulations 2018: similarity <10% no penalty, 10-40% warning, "
            "40-60% debarment, >60% debarment 5-10 yrs + registration "
            "cancellation. Since NIRF 2025, retractions negatively mark "
            "institutional rankings \u2014 retract nothing silently; a retraction "
            "now costs the institution directly.",
            "Indian funder/agencies cited in acknowledgments or affiliations",
            0.75,
            "Run the similarity check against the UGC tiers (engine: ugc_plagiarism) and declare any AI use per UGC 2026 policy"))

    # ---------------- China ----------------
    if re.search(
        r"National\s+Natural\s+Science\s+Foundation\s+of\s+China|\bNSFC\b|Chinese\s+Ministry\s+of\s+(?:Science|Education)|"
        r"MOST\s+grant|China\s+Scholarship\s+Council|\bCSC\b\s+grant|Chinese\s+Academy\s+of\s+Sciences",
        body):
        out.append(_f(
            Severity.MEDIUM,
            "Chinese funder detected: MOE early-warning list + national retraction-review disclosure apply",
            "Funding from NSFC/MOE/MOST implies compliance with the 2024-2026 "
            "national research-integrity rules: publishing in a Ministry "
            "early-warning-listed journal is punishable (funding bans, salary "
            "cuts), retraction audits require institutional disclosure, and "
            "misconduct findings can be reported to the funding agency.",
            "Chinese funder cited in acknowledgments or affiliations",
            0.75,
            "Verify the target venue is not on the MOE early-warning list before submission (predatory_journal engine cross-checks synced lists)"))

    # ---------------- USA ----------------
    if re.search(
        r"National\s+(?:Institutes?\s+of\s+Health|Science\s+Foundation)|\bNIH\b\s+(?:grant|funding|award)|\bNSF\b\s+(?:grant|funding|award)|"
        r"DOE\s+(?:grant|award|funding)|NASA\s+(?:grant|award)|\bDARPA\b|\bONR\b|department\s+of\s+energy\s+(?:grant|award)",
        body):
        us_findings = []
        if not re.search(r"creative\s+commons|open\s+access|accepted\s+manuscript|public\s+access|repository|PubMed\s+Central|arXiv|Zenodo|deposit", low):
            us_findings.append("no OA/public-access statement")
        if not re.search(r"data\s+(?:management|sharing)|data\s+availab|supplementary\s+data|deposited\s+(?:in|at)|available\s+at\s+https?://", low):
            us_findings.append("no data-sharing statement")
        ev = "; ".join(us_findings) if us_findings else "funder detected, OA/data statements present"
        if us_findings:
            out.append(_f(
                Severity.MEDIUM,
                "US federal funder detected: Nelson Memo / NIH DMS compliance gaps",
                "The 2022 OSTP 'Nelson Memo' requires immediate (no-embargo) "
                "public access for federally funded work, and the 2023 NIH Data "
                "Management & Sharing policy requires a DMS plan and a "
                "data-availability statement. Journals enforce this at "
                "acceptance; catching it now avoids a post-acceptance delay.",
                f"US federal funder cited; missing: {ev}",
                0.75,
                "Add an immediate-OA statement and a data-availability statement naming a repository (PubMed Central, Zenodo, etc.)"))

    # ---------------- EU / Plan S ----------------
    if re.search(
        r"European\s+(?:Research\s+Council|Commission|Union)|\bERC\b\s+(?:grant|funding|award)|Horizon\s+(?:2020|Europe)|"
        r"FET\s+Open|Marie\s+(?:Sklodowska|Curie)|cOAlition\s+S|Wellcome\s+Trust|Templeton\s+World\s+Charity|Robert\s+Bosch\s+Stiftung|"
        r"Austrian\s+Science\s+Fund|FWF\s+grant|Dutch\s+Research\s+Council|NWO|Swiss\s+National\s+Science\s+Foundation|\bSNSF\b|Finnish\s+Academy|Research\s+Council\s+of\s+Norway",
        body):
        if not re.search(r"rights\s+retention|CC\s*BY|creative\s+commons\s+attribution|open\s+access|preprint", low):
            out.append(_f(
                Severity.MEDIUM,
                "cOAlition S funder detected: Rights Retention Strategy not evident",
                "Plan S funders require the Rights Retention Strategy: the "
                "acknowledgments must carry the exact statement ('For the "
                "purpose of open access, the author has applied a CC BY public "
                "copyright licence...') and the work must be OA on publication. "
                "Editors desk-check this string for Horizon Europe/ERC/Wellcome "
                "papers.",
                "Plan S funder cited; no rights-retention/OA wording found",
                0.75,
                "Add the RRS acknowledgment string verbatim and plan Gold OA (or compliant Green) deposit"))

    # ---------------- Japan ----------------
    if re.search(
        r"Japan\s+(?:Society\s+for\s+the\s+Promotion\s+of\s+Science|Science\s+and\s+Technology\s+Agency)|\bJSPS\b\s+(?:grant|KAKENHI)|"
        r"KAKENHI|JST\s+(?:grant|funding)|MEXT\s+(?:grant|funding)|Japan\s+Agency\s+for\s+Medical\s+Research|AMED\s+grant",
        body):
        out.append(_f(
            Severity.LOW,
            "Japanese funder detected: MEXT misconduct-guideline definitions apply",
            "JSPS/JST/MEXT-funded research is governed by the MEXT "
            "'Guidelines for Responding to Misconduct in Research' (2014): "
            "fabrication, falsification, and plagiarism are defined "
            "specifically, and the handling process requires institutional "
            "due process. PIs on JSPS/JST grants are also expected to have "
            "completed research-integrity training \u2014 worth stating in the "
            "acknowledgments if asked.",
            "Japanese funder cited in acknowledgments",
            0.70,
            "Keep raw-data retention and authorship documentation per MEXT rules; confirm all co-authors approved the submission (ICMJE)"))

    # ---------------- Korea ----------------
    if re.search(
        r"National\s+Research\s+Foundation\s+of\s+Korea|\bNRF\b\s+grant\s*\(?(?:Korea|Republic)|Ministry\s+of\s+(?:Education|Science\s+and\s+ICT)\s+of\s+Korea|"
        r"Korea\s+Institute\s+of\s+(?:Science\s+and\s+Technology\s+Evaluation|Advancement\s+of\s+Technology)|\bKISTE\b|\bKISTI\b|Korea\s+Health\s+Industry\s+Development\s+Institute|\bKHIDI\b",
        body):
        out.append(_f(
            Severity.LOW,
            "Korean funder detected: KCI similarity screening + KISTI registration context",
            "NRF/KISTI-funded work is typically screened through the KCI "
            "similarity service and R&D projects are registered in KISTI's "
            "NRMS/RPMS. Report publications against the registered project "
            "number, and expect KCI-level similarity screening (stricter than "
            "many international journals).",
            "Korean funder cited in acknowledgments",
            0.70,
            "Cite the NRF project number exactly as registered and pre-screen similarity at KCI-level thresholds (<20% typical)"))

    return out
