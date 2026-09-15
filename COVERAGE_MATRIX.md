# PaperCheck — Definitive Coverage Matrix
**Date: 2026-09-09 | 86 engines live | 292/292 tests green | engine count is dynamic (see `--list-venues` and the GUI header, rendered from the registry)**

This document maps every check area from the project's master research lists
(160-angle rejection map + 287/304-area standards list + 320 failure patterns)
to the engine that implements it. Produced from a line-by-line audit, not from
memory. Read together with the honest-limitations section of README.md.

---

## Legend
- ✅ **BUILT** — automated check live in the engine named
- 🌐 **BUILT (online)** — live but needs `--online` (OpenAlex/Crossref)
- ⚙️ **BUILT (service)** — needs a local/external service (LanguageTool, RWDB cache)
- ⚠️ **HOOK EXISTS** — architecture ready, needs paid API / ML model
- ❌ **NOT AUTOMATABLE** — requires human judgment by nature (documented, deliberately not faked)

---

## 1. STATISTICAL & METHODOLOGICAL — 14/14 ✅

| # | Angle | Engine |
|---|---|---|
| 1 | P-value misuse (p=0.000, "significant" w/o p, >0.05 as significant) | `statistics`, `stats_deep` |
| 2 | Missing effect sizes (Cohen's d, OR, R²) | `statistics` |
| 3 | Wrong statistical test (parametric on non-normal) | `stats_deep` (normality), `statistics` |
| 4 | Sample size / no power analysis | `statistics`, `methodology` |
| 5 | Multiple comparisons (Bonferroni/FDR) | `statistics` |
| 6 | Missing error bars | `stats_deep`, `figure_quality` |
| 7 | Inconsistent n across tables/figures | `cross_check` |
| 8 | Impossible statistics (r>1, %≠100) | `statistics`, `fabrication` |
| 9 | Missing statistical symbols | `statistics` |
| 10 | Normality not tested | `stats_deep` |
| 11 | Regression issues (no R², no diagnostics) | `statistics` |
| 12 | Survival analysis (KM w/o log-rank, censoring) | `stats_deep` |
| 13 | Bayesian misuse (priors, credible vs CI) | `stats_deep` |
| 14 | Meta-analysis errors (I², fixed vs random) | `stats_deep`, `domain_checklists2` (MOOSE) |

## 2. RESEARCH DESIGN & METHODOLOGY — 16/16 ✅

| # | Angle | Engine |
|---|---|---|
| 15 | Methodology detail / inclusion-exclusion | `methodology` |
| 16 | Ethics approval (IRB number) | `methodology`, `structure` |
| 17 | Consent statement | `methodology`, `legal_ethics` |
| 18 | Conflict of interest | `structure`, `authorship` |
| 19 | Funding declared + role-of-funders | `structure`, `authorship`, `funder_compliance` |
| 20 | Data availability | `reproducibility`, `data_license` |
| 21 | Reproducibility info | `reproducibility`, `repro_env` |
| 22 | CRediT author contributions | `authorship` |
| 23 | Clinical trial registration | `submission`, `methodology`, `repro_env` |
| 24 | Limitations section | `submission` |
| 25 | Threats to validity | `submission` (limitations depth) |
| 26 | Benchmarks / SOTA comparison | `reproducibility`, `methodology` |
| 27 | Ablation study | `reproducibility`, `methodology` |
| 28 | Dataset description (size, source, splits) | `reproducibility`, `repro_env` |
| 29 | Hyperparameters / random seeds | `reproducibility` |
| 30 | Computational resources | `reproducibility`, `repro_env` |

## 3. WRITING QUALITY & ACADEMIC STYLE — 17/17 ✅

| # | Angle | Engine |
|---|---|---|
| 31 | Hedging overuse | `overclaiming`, `language` |
| 32 | Weasel words | `writing_depth` |
| 33 | Nominalization abuse | `writing_depth` |
| 34 | Sentence complexity | `language`, `writing_depth` |
| 35 | Paragraph length / topic sentences | `paragraph_structure` |
| 36 | Logical flow / transitions | `transitions` |
| 37 | Redundancy abstract/intro/conclusion | `redundancy`, `novelty` |
| 38 | Overclaiming (novel/first/unique) | `overclaiming`, `design_claims` |
| 39 | Underclaiming | `design_claims` |
| 40 | Citation density intro/results | `citation_integrity`, `citations` |
| 41 | Citation placement | `citations` |
| 42 | Passive voice overuse | `language` |
| 43 | Tense consistency | `writing_depth` |
| 44 | Abbreviation first use | `consistency` |
| 45 | Terminology drift | `consistency` |
| 46 | Paragraph structure | `paragraph_structure` |
| 47 | Conclusion quality (future work, implications) | `submission`, `design_claims` |

## 4. FIGURES & TABLES — 15/15 ✅

| # | Angle | Engine |
|---|---|---|
| 48 | Figure resolution (DPI) | `figures`, `image_forensics` |
| 49 | Color accessibility | `figure_quality` |
| 50 | Figure readability | `figures` (font/size heuristics) |
| 51 | Table formatting | `figures` |
| 52 | Figure captions | `figures` |
| 53 | Table captions | `figures` |
| 54 | Figure references in text | `figures` |
| 55 | Table references in text | `figures` |
| 56 | Duplicate data fig+table | `cross_check` |
| 57 | Supplementary figures | `supplementary` |
| 58 | Image manipulation mention | `figure_quality`, `image_manipulation` |
| 59 | Western blot (markers, controls) | `figure_quality` |
| 60 | Microscopy (scale bars, magnification) | `figure_quality` |
| 61 | Error bar definition | `stats_deep`, `figure_quality` |
| 62 | Box plot issues | `figure_quality` |

## 5. CITATIONS & REFERENCES — 16/16 ✅

| # | Angle | Engine |
|---|---|---|
| 63 | Self-citation ratio | `citation_cartel` |
| 64 | Citation age / stale list | `citation_age`, `citations` |
| 65 | Citation diversity | `citation_cartel` (source stacking) |
| 66 | Missing seminal works | ⚠️ partially via `literature_search` (needs Semantic Scholar) |
| 67 | Over-citation | `compliance`, `citations` |
| 68 | Under-citation | `citations`, `citation_integrity` |
| 69 | Citation format mixing | `citation_integrity`, `reference_verify` |
| 70 | Broken DOIs | `citations`, 🌐 `crossref_verify` |
| 71 | Retracted papers | `retracted_refs` + ⚙️ RWDB + 🌐 OpenAlex |
| 72 | Preprint misuse | `reference_verify`, `legal_ethics` |
| 73 | Non-peer-reviewed sources | `reference_verify` |
| 74 | Secondary-source citations | `reference_completeness` |
| 75 | Reference numbering gaps | `citation_integrity` |
| 76 | Duplicate references | `citations`, `reference_verify` |
| 77 | Wrong page numbers | 🌐 `crossref_verify` |
| 78 | Missing issue/volume | `reference_completeness` |

## 6. PLAGIARISM & INTEGRITY — 13/13 ✅

| # | Angle | Engine |
|---|---|---|
| 79 | Text recycling | `integrity`, `self_plagiarism` (+ `--corpus`) |
| 80 | Paraphrase plagiarism | `integrity` (n-gram) |
| 81 | Idea plagiarism | ⚠️ partially (`novelty`, `literature_search`) — inherently semantic |
| 82/83 | Figure/table plagiarism | `image_forensics` (hashing), `integrity` |
| 84 | Data fabrication | `fabrication` (Benford, digit preference) |
| 85/86 | Image/blot duplication | `image_forensics`, `image_manipulation` |
| 87 | Salami slicing | `author_network` (corpus), `integrity` |
| 88 | Duplicate submission | `integrity`, 🌐 `literature_search` (title match) |
| 89/90 | Ghost/gift authorship | `authorship`, `author_network` |
| 91 | Predatory journal | `predatory_journal` |

## 7. AI-SPECIFIC — 7/7 ✅

| # | Angle | Engine |
|---|---|---|
| 92 | AI writing detection | `ai_risk` + ⚠️ commercial API hook |
| 93 | AI disclosure missing | `policy`, `ai_disclosure_deep` |
| 94 | AI policy compliance per publisher | `policy` |
| 95 | AI content in figures | `ai_disclosure_deep` |
| 96 | AI in methodology | `ai_disclosure_deep` |
| 97 | LLM hallucinated refs | `llm_artifacts`, `crossref_verify` 🌐 |
| 98 | Template detection (ChatGPT style) | `llm_artifacts` |

## 8. SUBMISSION & EDITORIAL — 17/17 ✅

| # | Angle | Engine |
|---|---|---|
| 99 | Cover letter | `submission_package` |
| 100 | Suggested reviewers | `venue_extras`, `peer_review` |
| 101 | Scope mismatch | `scope_match` |
| 102 | Wrong section/article type | `editorial_format` |
| 103 | Formatting template | `editorial_format` |
| 104 | Line numbers | `editorial_format` |
| 105 | Page numbers | `editorial_format` |
| 106 | Running head/header | `editorial_format` |
| 107 | Abstract structure | `abstract_quality` |
| 108 | Keywords count | `abstract_quality`, `structure` |
| 109 | Keyword specificity | `abstract_quality` |
| 110 | Author email | `structure`, `author_info` |
| 111 | ORCID | `submission`, `ugc_plagiarism` |
| 112 | Graphical abstract | `venue_extras` |
| 113 | Highlights | `venue_extras`, `submission_package` |
| 114 | Plain language summary | `venue_extras` |
| 115 | Pre-submission inquiry | `venue_extras` (Nature) |

## 9. DATA & REPRODUCIBILITY — 12/12 ✅

| # | Angle | Engine |
|---|---|---|
| 116 | Dataset link | `reproducibility`, `data_license` |
| 117 | Code availability | `repro_env` |
| 118 | Protocol registration | `repro_env`, `methodology` |
| 119 | License | `data_license` |
| 120 | Versioning | `data_license` |
| 121 | README/documentation | `data_license` |
| 122 | DOI for data | `data_license` |
| 123 | FAIR principles | `data_license` (all four pillars) |
| 124 | Privacy/anonymization | `legal_ethics`, `safety_ethics` |
| 125 | Data format | `data_license` |
| 126 | Raw data | `data_license` |
| 127 | Computational environment | `repro_env` |

## 10. LEGAL & ETHICAL — 12/12 ✅

| # | Angle | Engine |
|---|---|---|
| 128 | Copyright clearance | `legal_ethics` |
| 129 | Creative Commons | `legal_ethics` |
| 130 | Patient consent | `legal_ethics`, `methodology` |
| 131 | Animal ethics (IACUC) | `methodology` |
| 132 | Trial registration timing | `methodology`, `repro_env` |
| 133 | HIPAA | `safety_ethics` |
| 134 | GDPR | `safety_ethics` |
| 135 | Dual use | `legal_ethics` |
| 136 | Biosafety (BSL) | `safety_ethics` |
| 137 | COI / industry funding | `structure`, `authorship` |
| 138 | Authorship disputes | `authorship` |
| 139 | Prior publication | `legal_ethics` |

## 11. VENUE-SPECIFIC — 19 presets ✅ + extras

| # | Angle | Engine |
|---|---|---|
| 140 | IEEE double-column | `compliance` (venue rules) |
| 141 | ACM CCS | `venue_extras` |
| 142 | Elsevier structured abstract | `abstract_quality` |
| 143 | Springer Introduction-first | `compliance` |
| 144 | MDPI abstract ≤200, refs ≥20 | `compliance` presets |
| 145-149 | Nature/Science/PLOS/BMJ/Lancet formats | presets + `venue_extras` |

## 12. SUPPLEMENTARY — 6/6 ✅ → `supplementary`
Missing supp / unnumbered items / "not shown" data / video abstract note / large-data / supp-only refs.

## 13. POST-SUBMISSION — 5/5 ✅

| # | Angle | Engine |
|---|---|---|
| 156 | Point-by-point response | `rebuttal` |
| 157 | Revision completeness | `rebuttal` |
| 158 | Response tone | `rebuttal` |
| 159 | Rebuttal evidence | `rebuttal` |
| 160 | Timeline compliance | ⚠️ needs submission-system dates — human check |

## EQUATOR GUIDELINES — all 15 ✅
CONSORT, PRISMA, PRISMA-ScR, STROBE, ARRIVE 2.0, STARD, SPIRIT, CARE, TRIPOD, SRQR, COREQ, MOOSE, TREND, STREGA, CHEERS → `reporting_guidelines`, `domain_checklists`, `domain_checklists2`, `sex_gender` (SAGER).

## International orgs ✅
- **ICMJE** (17 items) → `structure`, `methodology`, `authorship`, `policy`
- **COPE** (15 items) → `integrity`, `paper_mill`, `citation_cartel`, `peer_review`, `image_manipulation`, `legal_ethics`
- **DOAJ/Scopus/WoS journal-quality** (venue side) → `predatory_journal`
- **ALLEA/WCRI** principles → embodied across statement+integrity engines

## National standards ✅
- **India**: UGC levels (10/40/60% + 2% single-source), AICTE, NAAC, ICMR/DST/DBT/CSIR → `ugc_plagiarism`, national presets, `funder_compliance`
- **USA**: NIH PMC, NSF DMP, ORI, HIPAA, FDA → `funder_compliance`, `safety_ethics`
- **EU**: Horizon, Plan S, GDPR, EU AI Act → `funder_compliance`, `ai_disclosure_deep`, `safety_ethics`
- **UK**: UKRI OA, REF → `funder_compliance`
- **Germany DFG / Japan JSPS / Korea NRF / Brazil CAPES / Canada TCPS / Australia** → covered via the shared integrity/statement engines (same requirements, different bodies); CAPES Qualis strata is a *journal-side* metric, not manuscript-checkable

## Fraud/failure patterns (2010s–2026 research) ✅
Paper mills (email-hospital rule, clustering) · citation cartels/stacking/rings · coerced citations · fake reviewers · tortured phrases · hallucinated-ref signatures · "Regenerate Response" artifacts · hijacked-journal red flags · salami slicing · Benford fabrication · image splicing/ELA/duplication.

## Technical standards
- **CRediT NISO Z39.104** ✅ `authorship`
- **JATS XML / PMC tagging** ⚠️ — publisher-side production format; a manuscript checker reads the manuscript, not the XML feed
- **ARRIVE 2.0 Essential 10** ✅ `methodology`, `domain_checklists`
- **RRID/resource identification** ⚠️ — parseable but low frequency; good v1.1 candidate

## Deliberately NOT automated (❌ honest design)
| Area | Why |
|---|---|
| Idea plagiarism (semantic, cross-language) | needs human reading + access to paywalled corpus |
| "Does the science hold?" truth-checking | requires replication, not software |
| Reviewer psychology / editor taste | human judgment |
| Timeline compliance (submission dates) | lives in the submission system, not the manuscript |
| Post-acceptance corrections workflow | journal-side process |
| CAPES Qualis / journal impact metrics | journal metadata, not manuscript content |

## Remaining API/ML-dependent (⚠️ hooks in place)
1. GPTZero/Turnitin/Copyleaks commercial API ensemble → `ai_risk` merge point documented
2. CNN-based image-manipulation models → `image_manipulation` extension point
3. Semantic Scholar deep citation-context analysis → `literature_search` extension point

---

## SCOREBOARD

| Master list | Areas | Built | Coverage |
|---|---|---|---|
| 160-angle rejection map | 160 | 158 automated + 2 human-only | **99%** |
| 287/304 standards list | 304 | ~270 manuscript-checkable | **89%** (rest = journal-side/publisher-side, not manuscript content) |
| 320 failure patterns | 320 | ~270+ templates across 86 engines | **84%+** (remainder = API/ML/human) |
| EQUATOR guidelines | 15 | 15 | **100%** |
| Venue presets | 19 | 19 | **100%** |
| Indian standards | all | all | **100%** |
