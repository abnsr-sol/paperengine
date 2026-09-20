"""Check engines. Each exposes run(doc, ctx) -> List[Finding].
To add a rejection angle: create a module with run(), register in ALL_ENGINES.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from ..ingestion import Document

CheckFn = Callable[[Document, "CheckContext"], List["Finding"]]

@dataclass
class CheckContext:
    venue: str = "generic"
    rules: Dict = field(default_factory=dict)
    corpus: List[Document] = field(default_factory=list)
    online: bool = False
    mailto: str = ""
    max_online_checks: int = 10
    online_cache: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Library callers (GUIs, scripts, notebooks) sometimes pass None for
        # the optional fields. Normalize here — one boundary — so no engine
        # ever sees None where a str/dict is contracted (the v1.8.0 crash
        # class was exactly this kind of assumption).
        if self.venue is None:
            self.venue = "generic"
        if self.rules is None:
            self.rules = {}
        if self.corpus is None:
            self.corpus = []
        if self.online_cache is None:
            self.online_cache = {}


def _run_engine(engine: CheckFn, doc: Document, ctx: CheckContext):
    """Run one engine and never raise.

    Returns (name, findings, error_or_None). Fault isolation lives here so the
    pipeline has exactly one implementation — a bad engine is reported, not
    fatal (the GUI crash of v1.8.0 was that failure class).
    """
    name = getattr(engine, "__module__", "engine").rsplit(".", 1)[-1]
    try:
        engine_findings = engine(doc, ctx) or []
    except Exception as exc:  # noqa: BLE001
        return name, [], f"{name}: {type(exc).__name__}: {exc}"
    for f in engine_findings:
        if not f.source:
            f.source = name
    return name, engine_findings, None


def run_all_engines(doc: Document, ctx: CheckContext) -> Tuple[List["Finding"], List[str]]:
    """Run every registered engine with fault isolation.

    Returns (findings, engine_errors): an engine that raises is skipped and
    its name + error appended to engine_errors instead of aborting the whole
    check — one bad engine must never blank a report (the GUI crash of
    v1.8.0 was exactly this failure class).

    Engines run sequentially, in registration order. A thread-pool variant was
    implemented and measured, then deliberately rejected: the workload is
    CPU-bound pure Python under the GIL (profiling shows ~24% of runtime in a
    single engine), so threads added overhead instead of removing it
    (wall-clock 0.67x-0.92x on real-size documents). Keep this loop sequential
    unless the engines become genuinely I/O-bound.
    """
    from ..risk import Finding, Severity

    findings: List[Finding] = []
    errors: List[str] = []
    for engine in ALL_ENGINES:
        _name, engine_findings, err = _run_engine(engine, doc, ctx)
        findings.extend(engine_findings)
        if err:
            errors.append(err)

    # Deduplicate: if two findings share (category, title), keep the higher-confidence one
    seen: Dict[str, Finding] = {}
    deduped: List[Finding] = []
    for f in findings:
        key = f"{f.category}|{f.title}|{f.source}" if f.source else f"{f.category}|{f.title}"
        if key in seen:
            if f.confidence > seen[key].confidence:
                deduped.remove(seen[key])
                seen[key] = f
                deduped.append(f)
        else:
            seen[key] = f
            deduped.append(f)
    findings = deduped
    for err in errors:
        findings.append(Finding(
            "Engine", Severity.LOW,
            f"Engine '{err.split(':')[0]}' could not run on this document",
            "The engine was skipped so the rest of the report stays valid.",
            err, "Report this at github.com/abnsr-sol/paperengine/issues",
            1.0, source="pipeline"))
    return findings, errors

def _import_engines() -> List[CheckFn]:
    from . import (
        compliance, structure, language, citations, claims,
        ai_risk, integrity, novelty, consistency, figures,
        forensics, policy, statistics, overclaiming,
        self_plagiarism, citation_integrity, reproducibility,
        submission, ugc_plagiarism, reference_verify, fabrication,
        methodology, reporting_guidelines, writing_depth, legal_ethics,
        citation_cartel, paper_mill, predatory_journal, retracted_refs,
        submission_package, image_forensics, stats_deep, design_claims,
        redundancy, domain_checklists, literature_search, scope_match,
        rebuttal, crossref_verify, author_network, reviewer_fraud,
        image_manipulation, llm_artifacts, supplementary, data_license,
        abstract_quality, citation_age, sex_gender, stats_plan,
        editorial_format, author_info, figure_quality, venue_extras,
        ai_disclosure_deep, safety_ethics, authorship, repro_env,
        paragraph_structure, transitions, reference_completeness,
        funder_compliance, peer_review, domain_checklists2,
        grammar_tool, cross_check, statcheck, ugc_14word,
        grim_engine, openalex_verify,
        physical_plausibility, ml_fairness, corrections, proof_gaps,
        compilation_hygiene, tortured_phrases, sprite_engine,
        asa_pvalues, power_adequacy, engineering_vv, country_standards,
        tiva_engine, pcurve_engine, venue_hijack, trial_ethics, limitations,
        carlisle_engine,
        compression_ai, iclac_celllines, author_identity,
        rrid_validate, pubmed_verify, clinicaltrials_gov,
        bibtex_export, citation_graph,
        semantic_similarity, image_deep_forensics,
    )
    return [
        compliance.run, structure.run, language.run, citations.run,
        claims.run, ai_risk.run, integrity.run, novelty.run,
        consistency.run, figures.run, forensics.run, policy.run,
        statistics.run, overclaiming.run, self_plagiarism.run,
        citation_integrity.run, reproducibility.run, submission.run,
        ugc_plagiarism.run, reference_verify.run, fabrication.run,
        methodology.run, reporting_guidelines.run, writing_depth.run,
        legal_ethics.run, citation_cartel.run, paper_mill.run,
        predatory_journal.run, retracted_refs.run, submission_package.run,
        image_forensics.run, stats_deep.run, design_claims.run,
        redundancy.run, domain_checklists.run, literature_search.run,
        scope_match.run, rebuttal.run, crossref_verify.run,
        author_network.run, reviewer_fraud.run, image_manipulation.run,
        llm_artifacts.run, supplementary.run, data_license.run,
        abstract_quality.run, citation_age.run, sex_gender.run,
        stats_plan.run, editorial_format.run, author_info.run,
        figure_quality.run, venue_extras.run, ai_disclosure_deep.run,
        safety_ethics.run, authorship.run, repro_env.run,
        paragraph_structure.run, transitions.run, reference_completeness.run,
        funder_compliance.run, peer_review.run, domain_checklists2.run,
        grammar_tool.run, cross_check.run,
        statcheck.run, ugc_14word.run, grim_engine.run, openalex_verify.run,
        physical_plausibility.run, ml_fairness.run, corrections.run,
        proof_gaps.run,        compilation_hygiene.run, tortured_phrases.run,
        sprite_engine.run,
        asa_pvalues.run, power_adequacy.run, engineering_vv.run,
        country_standards.run,
        tiva_engine.run, pcurve_engine.run,
        venue_hijack.run, trial_ethics.run, limitations.run,
        carlisle_engine.run,
        compression_ai.run, iclac_celllines.run, author_identity.run,
        rrid_validate.run, pubmed_verify.run, clinicaltrials_gov.run,
        bibtex_export.run, citation_graph.run,
        semantic_similarity.run, image_deep_forensics.run,
    ]

ALL_ENGINES: List[CheckFn] = _import_engines()
__all__ = ["CheckContext", "ALL_ENGINES", "Document", "run_all_engines"]
