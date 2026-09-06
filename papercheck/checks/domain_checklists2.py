"""Extended EQUATOR checklists: MOOSE (observational meta-analyses), TREND (non-randomized
interventions), STREGA (genetic association), CHEERS (health economics), PRISMA-ScR (scoping)."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_META_OBS = r"meta-?analysis\s+of\s+(?:observational|cohort|case-?control)|pooled\s+(?:odds\s+ratio|risk\s+ratio|relative\s+risk)"
_TREND = r"(?:non-?randomi[sz]ed|quasi-?experimental|pre-?post|before-?after)\s+(?:trial|study|design|intervention)|stepped-?wedge"
_GENETIC = r"genome-?wide|SNPs?\b|genetic\s+association|GWAS|alleles?\b|genotypes?\b|polymorphism"
_ECON = r"cost-?(?:effectiveness|utility|benefit)|QALY|ICER\b|incremental\s+cost|economic\s+evaluation"
_SCOPING = r"scoping\s+review"


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Reporting Guidelines", sev, title, detail, evidence, action, conf)


def _check(low: str, prefix: str, guideline: str, items, out: List[Finding], conf: float) -> None:
    for pat, name, why in items:
        if not re.search(pat, low):
            out.append(_f(Severity.MEDIUM, prefix + " missing " + name,
                          guideline + " item missing: " + why,
                          prefix + " keywords found, not found: " + name, conf,
                          "Add " + name + " per " + guideline))


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    low = body.lower()
    out = []
    if re.search(_META_OBS, low):
        _check(low, "Observational meta-analysis", "MOOSE", [
            (r"i-?squared|heterogeneity", "Heterogeneity quantified (I2)",
             "MOOSE requires reporting between-study heterogeneity."),
            (r"funnel|egger|publication\s+bias", "Publication bias assessed",
             "MOOSE requires assessing publication bias (funnel plot/Egger)."),
            (r"fixed\s+effects|random-?effects?", "Pooling model stated",
             "State the fixed- or random-effects pooling model (MOOSE)."),
            (r"subgroup|sensitivity\s+anal", "Subgroup/sensitivity analyses",
             "MOOSE recommends prespecified subgroup and sensitivity analyses."),
        ], out, 0.75)
    if re.search(_TREND, low):
        _check(low, "Non-randomized intervention", "TREND", [
            (r"baseline\s+(?:equivalence|characteristics|compar)", "Baseline equivalence",
             "TREND requires baseline comparability of groups."),
            (r"confound", "Confounder handling",
             "TREND requires describing confounder adjustment."),
            (r"theory\s+of\s+change|behavioral\s+(?:theory|change)|intervention\s+theory", "Intervention rationale",
             "TREND asks for the theory behind the intervention."),
        ], out, 0.70)
    if re.search(_GENETIC, low):
        _check(low, "Genetic association study", "STREGA", [
            (r"hardy[- ]weinberg|hwe\b", "Hardy-Weinberg equilibrium",
             "STREGA requires reporting HWE testing of genotypes."),
            (r"ancestry|population\s+stratification|ethnic", "Ancestry/stratification",
             "STREGA requires describing ancestry and stratification control."),
            (r"call\s+rate|quality\s+control|qc\b|genotyping\s+error", "Genotyping QC",
             "STREGA requires laboratory methods and genotype quality control."),
        ], out, 0.70)
    if re.search(_ECON, low):
        _check(low, "Health-economic evaluation", "CHEERS", [
            (r"time\s+horizon|perspective\s+(?:of|:)", "Perspective & time horizon",
             "CHEERS requires stating the analytical perspective and time horizon."),
            (r"discount(?:ing|ed)?\b", "Discounting",
             "CHEERS requires the discount rate for costs/outcomes."),
            (r"uncertainty|probabilistic|sensitivity\s+anal", "Uncertainty analysis",
             "CHEERS requires uncertainty analysis (PSA/one-way sensitivity)."),
            (r"currency|usd|eur|inr|\$", "Currency & price date",
             "CHEERS requires currency and price-reference year."),
        ], out, 0.70)
    if re.search(_SCOPING, low):
        _check(low, "Scoping review", "PRISMA-ScR", [
            (r"protocol|registered|a\s+priori", "A-priori protocol",
             "PRISMA-ScR recommends stating whether a protocol exists."),
            (r"data\s+chart(?:ing)?|extraction\s+form", "Charting process",
             "PRISMA-ScR requires describing the data-charting process."),
        ], out, 0.65)
    return out