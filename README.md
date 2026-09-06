# PaperCheck — Manuscript Rejection-Risk Engine

A pre-submission intelligence engine for academic papers. It ingests a manuscript
(DOCX / TXT / Markdown / LaTeX / PDF), checks **every angle that can get a paper
rejected**, and produces a `Risk | Finding | Evidence | Confidence | Action` report
plus a readiness score.

> **The core idea (from the research):** do not build "an AI detector + a plagiarism
> checker + a grammar checker". Build an engine that answers: *"What could cause this
> manuscript to be rejected at this venue, what evidence suggests that risk, how
> serious is it, and what should the researcher fix?"*
>
> Similarity is **not** plagiarism. An AI-risk score is **not** proof of AI
> authorship. This engine reports risk signals with confidence and evidence, and
> leaves final judgment to humans — exactly how editors are trained to use
> iThenticate/Similarity Check and Turnitin's AI writing assessment.

---

## Quickstart

### Option A — Web GUI (no terminal skills needed)

```bash
papercheck --gui
# → opens http://localhost:8765 in your browser
```

Drag-and-drop your manuscript (.docx/.txt/.md/.tex/.pdf), pick
**International** or **National (India)** plus the venue preset, and get the
full report in the browser. 100% local — the file never leaves your machine.

### Option B — CLI

```bash
# No install needed (pure Python stdlib; pypdf only for PDFs)
python -m papercheck sample_paper.txt --venue elsevier

# Full report to a file
python -m papercheck sample_paper.txt --venue ieee_conference --format markdown --out report.md
python -m papercheck sample_paper.docx --venue mdpi --format html --out report.html

# With online lookups (Crossref): duplicate-publication + DOI validation
python -m papercheck paper.docx --venue springer --online --mailto you@university.edu

# Compare against your already-published papers (duplicate / "no new content" check)
python -m papercheck paper.docx --corpus ./my_prior_papers/
```

Run the tests:

```bash
python -m unittest discover -s tests -v
```

---

## What the engine checks (the full angle map)

Every rejection angle from the research maps to a check engine. "Auto" means the
engine checks it now; "Manual" means the engine flags it for human review.

| # | Rejection angle (from research) | Engine | Status |
|---|--------------------------------|--------|--------|
| 1 | Word / page / abstract limits | `compliance` | Auto (hard counts, 100% confidence; page count is an estimate) |
| 2 | Missing / wrong sections, heading numbering | `compliance` + `consistency` | Auto |
| 3 | Figure / table counts, captions, in-text refs, numbering, image DPI | `compliance` + `figures` | Auto (counts + DOCX image analysis) |
| 4 | Reference count, DOI presence, resolvable DOIs | `compliance` + `integrity` | Auto (+ online Crossref) |
| 5 | Font / mixed-font / template compliance (DOCX) | `compliance` | Auto (run-level) |
| 6 | Readability, grade level, run-ons, fragments | `language` | Auto (heuristic) |
| 7 | Grammar: double spaces, missing spaces, repeated words, typos | `language` | Auto (heuristic — see Limitations) |
| 8 | Punctuation hygiene (exclamation, spacing) | `language` | Auto |
| 9 | Passive voice, informal tone, hedging | `language` | Auto (heuristic) |
| 10 | Repetition / redundant prose (self) | `language` + `integrity` | Auto |
| 11 | Identical / near-identical paragraphs (copy-paste, spacing tricks) | `integrity` + `forensics` | Auto (verbatim + whitespace-normalized) |
| 12 | Overlap vs already-published papers ("no new content") | `integrity` + `novelty` | Auto with `--corpus` |
| 13 | Duplicate publication / close prior work (online) | `integrity` | Auto with `--online` (Crossref) |
| 14 | Reference sanity: DOIs, identifiers, hallucination red flags | `integrity` | Auto + online DOI resolution |
| 15 | Citation mechanics: never-cited refs, broken [n], density, style mixing, outdated refs | `citations` | Auto |
| 16 | Title quality, author block, email, keywords, abstract content | `structure` | Auto |
| 17 | Required statements (data availability, funding, COI, contributions, ethics) | `structure` | Auto (presence/absence) |
| 18 | AI-style writing signals (burstiness, lexical diversity, templates) | `ai_risk` | Auto (probabilistic — see Limitations) |
| 19 | AI-detection via real detectors (Turnitin/GPTZero/…) | `ai_risk` | Manual — plug-in point (API) |
| 20 | AI-policy compliance per publisher (disclosure requirements) | `policy` | Auto checklist per publisher matrix |
| 21 | Novelty: explicit contribution statement | `novelty` | Auto (presence/absence) |
| 22 | Novelty: abstract ≈ conclusion (nothing new in body) | `novelty` | Auto |
| 23 | Novelty: similarity to prior work / prior art search | `novelty` + `integrity` | Auto (`--corpus` / `--online`) |
| 24 | Internal consistency: conflicting numbers (n=, %, epochs…) | `consistency` | Auto (high confidence) |
| 25 | Internal consistency: undefined / inconsistent acronyms | `consistency` | Auto |
| 26 | Internal consistency: terminology drift | `consistency` | Auto |
| 27 | Overstated conclusions, significance without stats, missing effect sizes | `claims` | Auto (heuristic) |
| 28 | Document forensics: hidden text, lookalike chars, zero-width chars, tracked changes | `forensics` | Auto (DOCX XML + character scan) |
| 29 | Claim–evidence consistency (abstract vs results) | `consistency` + Manual | Partial — flagged, human verifies |
| 30 | Deep statistics: survival (censoring/KM/log-rank/Cox), Bayesian (priors/CrI), p-hacking clusters, normality, error bars, software | `statistics` + `stats_deep` | Auto (heuristic) |
| 31 | Methodology: ethics approval, consent, trial registration, randomization, blinding, animal IACUC/ARRIVE, datasets, benchmarks, ablation, compute | `methodology` | Auto (presence/absence, design-aware) |
| 32 | Reporting guidelines: CONSORT / PRISMA 2020 / STROBE / ARRIVE + STARD / TRIPOD / CARE / SRQR / COREQ / SPIRIT essentials | `reporting_guidelines` + `domain_checklists` | Auto (checklist essentials) |
| 33 | Writing depth: weasel words, filler phrases, nominalization, tense mixing, sentence/paragraph length, transitions | `writing_depth` | Auto (heuristic) |
| 34 | Legal & ethics: patient consent, de-identification, copyright permission, dual-use, prior-conference note, CC licenses | `legal_ethics` | Auto |
| 35 | Citation fraud: self-citation ratio, reciprocal rings, single-source stacking | `citation_cartel` | Auto (heuristic) |
| 36 | Paper-mill tells: email-hospital rule, glued email/name, free-mail density, author/email mismatch | `paper_mill` | Auto (heuristic) |
| 37 | Predatory / hijacked venue vetting (Think.Check.Submit, fast-track red flags) | `predatory_journal` | Auto checklist |
| 38 | Retracted references (curated seed list; full Retraction Watch with `--online`) | `retracted_refs` | Auto + online |
| 39 | Submission package: cover-letter leaks, reviewer blocks, highlights, package checklist | `submission_package` | Auto |
| 40 | Image forensics: duplicated / near-duplicate figure panels via perceptual hashing (DOCX) | `image_forensics` | Auto (Pillow) |
| 41 | Design-aware claims: causal overclaim from observational data, abstract front-loading, conclusion quality | `design_claims` | Auto (heuristic) |
| 42 | Cross-section redundancy (abstract/intro/conclusion/results overlap) | `redundancy` | Auto (Jaccard) |
| 43 | Venue fit / scope mismatch + dual standard (international vs Indian national) | `venues` | Auto rulesets + manual venue pick |
| 44 | UGC/AICTE/NAAC Indian compliance: plagiarism thresholds, ORCID, Shodhganga, 20% novelty | `ugc_plagiarism` | Auto (national standard) |
| 45 | Reviewer psychology (presentation → perceived quality) | README | Design principle — polished, readable papers score better |
| 46 | Similar published work / duplicate title (OpenAlex) | `literature_search` | Auto with `--online` |
| 47 | Venue scope fit (aims-and-scope keywords) | `scope_match` | Auto (heuristic) |
| 48 | Revision: response-to-reviewers letter quality (tone, evidence, completeness) | `rebuttal` | Auto when a response letter is detected |

---

## Architecture

```
papercheck/
├── __main__.py        CLI entry point
├── ingestion.py       DOCX (stdlib zip+XML), TXT/MD/TeX, PDF (optional pypdf)
├── metrics.py         text statistics (readability, burstiness, n-grams, …)
├── venues.py          venue rule presets (IEEE/ACM/Elsevier/Springer/MDPI/…) + publisher
├── risk.py            Finding / Severity / RiskReport / readiness score
├── report.py          console, Markdown, and HTML renderers
└── checks/            one engine per rejection angle
    65 check engines, one per rejection angle:
    compliance        limits, sections, figures, refs, fonts
    structure         title, authors, email, keywords, required statements
    language          readability, grammar heuristics, punctuation, tone
    citations         in-text vs list matching, density, style, outdated refs
    claims            overstated conclusions, significance without stats
    ai_risk           stylometric AI-risk signals (probabilistic)
    integrity         self/corpus overlap, duplicate publication, DOI checks
    novelty           contribution statement, abstract=conclusion, prior work
    consistency       numbers, acronyms, terminology, heading numbering
    figures           captions, in-text refs, numbering gaps, image DPI
    forensics         hidden text, lookalike chars, tracked changes, metadata
    policy            publisher AI-disclosure checklist
    statistics        p-values, effect sizes, impossible stats, multiple comparisons
    overclaiming      superlatives, hedging density, 'novel' in abstract
    self_plagiarism   duplicated sentences, repeated phrases
    citation_integrity  numbering gaps, mixed formats, DOIs, intro density
    reproducibility   data/code statements, hyperparameters, random seeds
    submission        limitations, ORCID, keywords, acknowledgment, trial reg
    ugc_plagiarism    UGC thresholds, AI disclosure (2026), ORCID, Shodhganga
    reference_verify  gaps, mixed styles, DOIs, non-peer-reviewed, dupes
    fabrication       Benford's law, impossible %, r, n, p=0.000
    methodology       ethics, consent, trials, datasets, benchmarks, ablation
    reporting_guidelines  CONSORT/PRISMA/STROBE/ARRIVE essentials
    writing_depth     weasel words, filler, nominalization, tense, length
    legal_ethics      consent, privacy, copyright, dual-use, prior publication
    citation_cartel   self-citation ratio, rings, source stacking
    paper_mill        email-hospital rule, glued emails, free-mail density
    predatory_journal Think.Check.Submit vetting, fast-track red flags
    retracted_refs    known retractions (seed list) + online Retraction Watch
    submission_package  cover-letter leaks, reviewer blocks, package checklist
    image_forensics   duplicated figure panels via perceptual hashing (Pillow)
    stats_deep        survival, Bayesian, p-hacking clusters, normality
    design_claims     causal overclaim vs design, abstract front-loading
    redundancy        abstract/intro/conclusion/results overlap (Jaccard)
    domain_checklists STARD, TRIPOD, CARE, SRQR/COREQ, SPIRIT
    literature_search OpenAlex similar-work / duplicate-title scan (--online)
    scope_match       venue aims-and-scope keyword fit (scope mismatch flag)
    rebuttal          response-letter analyzer (tone, evidence, completeness)
    crossref_verify   online Crossref metadata check (volume/issue/pages/year)
    author_network    recurring author teams, duplicate identities, salami overlap
    reviewer_fraud    self-review hints, same-institution reviewer clusters
    image_manipulation  copy-move quadrant hashing + ELA splicing heuristics
    llm_artifacts     ChatGPT-style template phrasing, tortured phrases, fake-ref signatures
    supplementary     missing supp section, unnumbered supp items, 'not shown' data
    data_license      FAIR: license, versioning, raw data, formats, data citation
    abstract_quality  structured abstract labels, abstract word limits, keyword quality
    citation_age      reference recency, stale lists, citation age span
    sex_gender        SAGER sex/gender reporting in clinical/animal studies
    stats_plan        missing-data handling, outlier rules, pre-specified analysis
    editorial_format  line numbers, running head, page numbers, LaTeX template checks
    author_info       affiliations, corresponding author, equal contribution, initials
    figure_quality    western blots, microscopy scale bars, box plots, colorblind, error bars
    venue_extras      ACM CCS, Elsevier highlights, graphical abstract, lay summary, reviewers
    ai_disclosure_deep  per-tool AI disclosure, AI figures, human verification, EU AI Act
    safety_ethics     biosafety levels, DSMB, adverse events, HIPAA/GDPR safeguards
    authorship        CRediT roles, role-of-funders, COI completeness
    repro_env         code availability, Docker/conda env, protocol registration, splits
    paragraph_structure  topic sentences, 200-word paragraphs, fragment paragraphs
    transitions       section-to-section flow, roadmap paragraph, connectives
    reference_completeness  missing years/volumes/pages, 'as cited in' secondary cites
    funder_compliance NIH/NSF/Horizon/Wellcome/Plan S/DMP obligations
    peer_review       coerced citations, free-mail/same-domain reviewer conflicts
    domain_checklists2  MOOSE, TREND, STREGA, CHEERS, PRISMA-ScR essentials
    grammar_tool      optional LanguageTool server integration (silent if absent)
    cross_check       inconsistent n, figure/table duplicate data, numeric contradictions
```

Report formats: `--format console|markdown|html|fixplan|csv`. The **fixplan**
format converts findings into a prioritized, effort-estimated pre-submission
checklist (criticals first, near-duplicate findings deduplicated, ~total
effort estimated).

**Batch mode:** `python -m papercheck --batch papers/ --venue ugc_care
[--format csv --out summary.csv]` scans a whole folder and produces a
worst-first comparison table (or CSV) with per-severity counts and top
findings per paper.

**Retraction screening:** `python -m papercheck --update-rwdb` caches the
full Retraction Watch database (CC-BY 4.0, Crossref); retracted-reference
screening then runs against 70k+ records offline. Without the cache, a
built-in seed list of historically notable retractions is active. See
USER_GUIDE.md for the 5-minute walkthrough.

Every engine returns `Finding(category, severity, title, detail, evidence,
confidence, action, location)`. The risk engine aggregates into a readiness
score (informational) and the report renders the evidence-linked table.

## Install

```bash
pip install -e .            # core (zero required dependencies)
pip install -e .[all]       # + PDF ingestion and image forensics extras
papercheck paper.docx --standard national --venue ugc_care
```

CI runs the full test suite on Python 3.10–3.13 on every push/PR.

## Extending the engine

- **New rejection angle:** add `checks/my_angle.py` with `run(doc, ctx) -> [Finding]`
  and register it in `checks/__init__.py`. Nothing else changes.
- **New venue:** add a one-line dict to `venues.PRESETS`, or pass
  `--venue-json rules.json` with the venue's exact limits.
- **Plug in a real AI detector:** call the GPTZero / Originality.ai / Copyleaks
  APIs from `checks/ai_risk.py` and merge scores into the same `Finding` model —
  keep the uncertainty band and never return a single "AI%" verdict.
- **Plug in a real grammar engine:** LanguageTool (local HTTP or Python binding)
  replaces the heuristics in `checks/language.py` with true grammar rules.
- **Prior-art / literature coverage:** swap the `--online` Crossref call for
  OpenAlex or Semantic Scholar queries (both free, no key).

## Honest limitations (baked into the design)

1. **Similarity ≠ plagiarism.** Overlap requires human interpretation (Crossref
   itself warns against automatic rejection thresholds). The engine shows *what*
   matched as evidence.
2. **AI detection is probabilistic.** Turnitin warns its AI assessment can
   misidentify human and AI text. "Low burstiness", "low lexical diversity",
   "template transitions" occur naturally in non-native and highly technical
   writing. The AI-risk engine reports an uncertainty band, not a verdict, and
   deliberately refuses typography myths ("em dash = AI", "underscore = AI" —
   no scientific support).
3. **Grammar checks are heuristics**, not a full grammar engine. Run
   LanguageTool/Grammarly/Paperpal for the final pass.
4. **Venue rules are typical published limits** and change — confirm against the
   venue's author guidelines.
5. **Readiness score is informational.** It aggregates weighted, confidence-scaled
   findings; it is not a prediction of acceptance.

## Roadmap (from the 50-point research plan)

1. **Literature engine:** OpenAlex/Semantic Scholar lookup of the manuscript's
   topic + missing-seminal-work detection (angle 28).
2. **Claim–evidence checks:** LLM-assisted verification that abstract/conclusion
   claims are supported by the results section (angles 29–30).
3. **Statistical sanity:** automated checks for p-value misuse, impossible
   values, and table-text mismatches (angle 18).
4. **Detector ensemble:** GPTZero + Originality.ai + Copyleaks API integration
   with score reconciliation (angles 34, 44).
5. **Scope matching:** venue topic keywords in rules + topic classifier for
   out-of-scope desk-rejection risk (angle 48).
6. **Benchmark harness:** a controlled human/AI/edited corpus to measure
   precision/recall and publish honest accuracy numbers (angle 34).