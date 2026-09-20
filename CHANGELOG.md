# Changelog

All notable changes to PaperEngine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).## [1.12.0] — 2026-09-20

### Fixed
- **Finding action/confidence transposition (14 engines).** Several engines
  passed the numeric confidence into the `action` slot and the advice text into
  `confidence`, so reports showed `action: 0.95` and the confidence was silently
  coerced to 0.5 — understating the readiness score (`weight × confidence`).
  `Finding.__post_init__` now detects and repairs the transposed pair before
  coercion, covering all 44 call-sites and any future ones. Added
  `tests/test_action_confidence.py` as a regression guard.

### Changed
- **CI now gates on calibration:** `.github/workflows/ci.yml` runs
  `scripts/benchmark.py` (monotonicity + zero CRITICAL on the clean paper) and
  `scripts/vector_eval.py` (labeled real-world vectors) on every push/PR.
- Refreshed stale counts: `pyproject.toml` description and README test badge
  now reflect the real engine count and 315 tests. Version 1.11.0 → 1.12.0.

### Added
- **Parallel engine pipeline.** `run_all_engines` now runs the 97 engines
  through a small thread pool (default 4 workers, `PAPERCHECK_WORKERS`
  override; ~3.7× faster on a representative manuscript). Output is
  byte-for-byte identical to the sequential path — results are re-ordered by
  engine index, so reports and scores never depend on thread scheduling.
  Offline runs keep sequential semantics; a shared fault-isolation helper
  covers both paths. Regression-guarded by `tests/test_parallel_pipeline.py`.
- **Coercive-citation / venue-stacking detection (`citation_cartel`).** The
  engine had a dead stub where the target-venue reference-share check should
  be; it now measures how heavily the reference list cites the target venue
  (word-boundary matched, skipped for the generic venue, needs ≥10 refs and
  ≥3 venue citations) and flags ≥18% share as Medium / ≥35% as High — a
  COPE-flagged coercion signal editors screen for during triage.
- Code hygiene: the two bare `except: pass` handlers in `fabrication.py`
  (impossible-% and impossible-r loops) now catch only `ValueError` so real
  bugs can no longer be silently masked.

## [1.11.0] — 2026-09-15

### Added — evaluation harness, EQUATOR 40+, PDF image forensics

- **Real-world vector evaluation harness (`scripts/vector_eval.py`)**: a labeled
  corpus (10 positive vectors embedding known flaw archetypes + 2 negative
  controls) with a declarative manifest. Exits non-zero on regression, so
  real-world detection can no longer silently break. Runs alongside the
  synthetic benchmark (which stays untouched and green).
- **EQUATOR expansion: 13 → 40 guideline families** in `reporting_guidelines`:
  PRISMA-ScR/NMA/IPD/DTA + MOOSE + PRISMA-SearchAI/TIE, STROBE-GWAS/ME +
  STREGA + RECORD, REMARK + CLAIM + STARD-AI, TRIPOD+AI + DECIDE-AI,
  CONSORT-Cluster/Pragmatic, SPIRIT-extensions, ARRIVE-Abstract, TIDieR,
  MIBBI, MIAME, dMIQE, SAMP, COREQ, ENTREQ, CHEERS-SIM. Each family is
  keyword-triggered by study-type vocabulary and verifies named checklist
  items (missing items → HIGH findings).
- **PDF image forensics**: `image_forensics` now extracts embedded raster
  images from PDFs via pypdf (pure Python, offline) and runs the same
  duplicate/near-duplicate perceptual-hash analysis as DOCX. Verified on a
  synthetic PDF with a duplicated panel. Rasterized vector graphics remain
  out of scope (documented).
- **Engine fixes surfaced by the vector harness**: retraction-screening
  generic-token false positives (IDF-style filter), consent-statement
  phrasing, non-human-subject suppression for CS papers mentioning clinical
  sites, TRIPOD no longer firing on pre-validated model deployments,
  duplicate-reference detection on numbered reference lists.
- Sample run improved 46/100 → 69/100 with the false-positive fixes; flawed
  detection unchanged.

## [1.10.1] — 2026-09-15

### Fixed — trust-pass: false positives & duplicate findings (live-run verified)

- **retracted_refs no longer fires CRITICAL on fuzzy matches**: token-overlap
  screening against the 72k-entry Retraction Watch cache is a *signal*, not proof —
  a placeholder citation in the sample paper matched a DB entry and fired CRITICAL.
  Fuzzy matches now escalate to HIGH "verify" with innocent-explanation language;
  CRITICAL is reserved for the curated seed list. Citations that explicitly note a
  retraction/withdrawal are no longer flagged (honest citing is correct practice).
- **Cross-engine duplicate findings removed (single ownership)**: "Most references
  lack DOIs" fired 3× (integrity, citation_integrity, reference_verify); reference
  numbering/mixed-format/duplicate-ref checks fired 2× (citation_integrity +
  reference_verify); ablation/baseline checks fired 2× (methodology +
  reproducibility). Each check now has exactly one owning engine.
- Sample run: 61 → 56 findings, duplicates NONE, engine errors 0, CRITICAL 0.

### Added — Carlisle baseline-balance engine (#86, `carlisle_engine`)

The text-only, offline subset of the method Carlisle used to expose fabricated RCTs:
extracts mean(SD) vs mean(SD) baseline comparisons from running text, computes
standardized differences, and flags (a) implausible single-variable baseline
differences (z>4, p<6e-5 — real randomization almost never produces these) and
(b) "too-perfect" balance (p-value pile-up above 0.6 across ≥8 baseline variables —
the fabricated-RCT signature). Flag-not-verdict: findings list innocent causes
(SD/SE transcription, matched designs) and require ≥4 baseline comparisons.

- Docs corrected to 86 engines.

## [1.10.0] — 2026-09-09

### Added — global standards wave (engines #77–#80 + EQUATOR expansion)
Built from the verified open-source research sweep (`RESEARCH_GLOBAL_2000_2026.md`,
Appendix 10): refchecker's multi-source reference consensus, aclpubcheck's camera-ready
preflight, Aletheia-Probe's multi-source venue verdicts, and the z-curve/p-curve
family — plus the four highest-impact gaps from the country-by-country gap analysis.

- **ASA p-value misuse engine (#77, `asa_pvalues`)**: the ASA 2016 statement's six
  principles as mechanical checks — significance claimed with no effect size (P3),
  threshold-only p-values (P2), magnitude rhetoric ("highly significant", P4),
  nonsignificance read as no effect (P5), p-as-proof (P1), significance euphemisms
  (P6). Papers that report effect sizes/CIs get a pass on the matching principles.
- **Power & sample-size engine (#78, `power_adequacy`)**: the top cited peer-review
  rejection cause — participant studies with no power/sample-size language, small-n
  framed with "robust/conclusive" language, unexplained group imbalance after
  randomization, power analysis named without alpha/power/effect-size parameters.
- **EQUATOR expansion 4 → 13 families** (`reporting_guidelines`): CONSORT and PRISMA
  (existing) joined by CONSORT-AI, SPIRIT, STROBE, STARD, TRIPOD/TRIPOD+AI,
  ARRIVE 2.0, CARE, SRQR/COREQ, CHEERS 2022, SQUIRE 2.0, and MIQE. Families are
  detected by study type and compose (an AI-RCT gets CONSORT + CONSORT-AI).
  SPIRIT's gate is IRB-boilerplate-proof ("the study protocol was approved by..."
  no longer triggers a false protocol-paper check — caught by the benchmark audit).
- **Engineering V&V engine (#79, `engineering_vv`)**: simulation/FEA/CFD papers are
  audited against ASME V&V / NAFEMS / NASA-STD-7009 expectations — mesh/grid
  independence, validation against experiment, solver + scheme identification,
  boundary conditions, uncertainty quantification, sourced material properties,
  compute environment. Silent on non-simulation papers.
- **Country standards engine (#80, `country_standards`)**: funder/jurisdiction
  signals trigger the matching national regime — India (UGC 2018 tiers + NIRF 2025
  retraction penalty), China (MOE early-warning list + national retraction review),
  USA (Nelson Memo immediate OA + NIH DMS data sharing), EU (Plan S Rights
  Retention Strategy), Japan (MEXT misconduct guidelines), Korea (KCI screening /
  KISTI registration). Informational by design.
- **29 new tests** (`test_standards_wave.py`); benchmark gate: clean paper 90/100
  with zero serious findings, flawed paper 30, monotonicity PASS.

### Research
- `RESEARCH_GLOBAL_2000_2026.md` Appendix 10: verified deep dive on
  markrussinovich/refchecker (borrow: DBLP/ACL Anthology consensus),
  acl-org/aclpubcheck (borrow: Type-3-font preflight), Aletheia-Probe
  (borrow: per-source venue verdicts), FBartos/zcurve (borrow: p-curve
  right-skew signal); plus a corrected free-data-layer map (the "Retraction
  Watch API costs $500/yr" claim circulating in community dumps is false —
  the DB is free for research use and already cached offline).

## [1.9.0] — 2026-09-09

### Added — open-source intelligence integration + efficiency wave
- **`papercheck --sync-all`**: one command refreshes the local open-data
  cache — the **Retraction Watch database** (now via its official Crossref
  Labs home; the old retractionwatch.com URL 404s, which silently broke
  the previous `--update-rwdb` flow) and the **PPS tortured-phrases
  catalogue** (Cabanac et al.). Engines read the caches automatically;
  everything still works fully offline from curated fallbacks.
- **72,187 retracted papers** now screen every reference (up from a 14-entry
  seed list), surfaced in the GUI as a live cache-status chip.
- **SPRITE fabrication forensics** (engine #76): reconstructs whether ANY
  integer dataset of N responses on a declared scale can produce a reported
  M/SD pair — deterministic, same certainty class as GRIM/statcheck, with
  proper GRIM handoff (impossible means are GRIM's finding, not SPRITE's).
- **Tortured-phrase engine #75**: Aho-Corasick word-trie scanning of the PPS
  catalogue (O(words × phrase depth)) with escalation by distinct-phrase
  count and a translation-disclaimer escape hatch.

### Fixed
- **Retraction screening false positive** the real 72k-DB immediately
  surfaced: generic same-year titles ("load balancing…for…models…networks")
  collided with retracted works via stopwords + a year bonus. Tokens are now
  filtered to distinctive words, the year can corroborate but never create a
  match, and a short-title coverage rule keeps genuine seed-list matches
  firing. Benchmark clean paper back to 90 with zero serious FPs.
- **Efficiency: retraction screening index** — the 16 MB DB was re-parsed and
  all 72k titles re-tokenized *per reference*; now a process-level index
  pays 1.13 s once per server/CLI lifetime and re-accesses in 0.4 ms.
- **Efficiency: LanguageTool probe TTL cache** — the 1.5–3 s connect
  timeout was paid by every GUI check when no LT server runs; now cached
  for 10 minutes (subsequent probes: 0.01 ms).

## [1.8.1] — 2026-09-09

### Fixed — the GUI 'bad operand type for unary -: str' crash class
- **Finding type coercion at construction**: any engine argument
  transposition (a string landing in the confidence slot, a raw string
  severity, `None` fields) is now repaired inside `Finding.__post_init__`
  instead of crashing the whole report during severity sorting.
- **Per-engine fault isolation** (`run_all_engines`): an engine that raises
  is skipped and logged as a LOW-severity note ("Engine X could not run")
  instead of aborting the entire check — shared by the CLI, GUI, and batch
  modes. One bad engine can no longer blank a report.
- **Venue/standard coherence**: the server now follows the venue's own
  standard when the form's standard select disagrees (stale UI state), and
  the GUI resets a stale venue selection on standard switch, so the applied
  ruleset and the displayed standard can never diverge.

### Added
- **Live rule hints in the venue dropdown**: selecting any venue shows its
  page/word/abstract limits, reference floor, blinding policy, UGC similarity
  band, required statements, and the date its limits were last verified —
  before you upload.
- **Preset-matrix regression suite**: every venue preset renders a valid
  report (international matrix + national coherence + DOCX spot-check),
  locking the v1.8.0 crash class out of future releases.

## [1.8.0] — 2026-09-09

### Fixed — correctness and trust hardening (external audit adopted)
- **`__version__` mismatch fixed**: the package reported 0.1.0 while PyPI
  metadata said 1.7.x. A regression test now asserts `papercheck.__version__`
  always equals `pyproject.toml`'s version, so they can never diverge again.
- **`papercheck --version` flag added** to the CLI.
- **Readiness score recalibrated.** The old saturation curves zeroed a
  realistic messy draft (20 medium + 10 high findings, no criticals → 0/100),
  which read as noise. Medium/High tier penalties now scale so the same draft
  scores ~62 while two critical findings still drop below 65 and a clean
  paper still scores 100. Benchmark monotonicity holds (clean 90 / flawed 32).
- **Acknowledgment spelling flexibility**: venue required-statement matching
  now accepts Acknowledgment/Acknowledgement(s) interchangeably, so presets
  and papers written in either variant stop false-flagging each other.
- **Stale docs corrected**: COVERAGE_MATRIX header (65→74 engines, live
  counts), requirements.txt pypdf pin re-synced with pyproject.

### Added — five new venue standards (19 → 24 presets)
- **`lncs_springer`** — Springer LNCS proceedings: 16pp, A4, single column,
  Times 10pt, keywords required.
- **`science_journal`** — AAAS Science-class: 125-word abstract, ~11.5k words,
  Materials and Methods + Supplementary Materials sections.
- **`medical_journal`** — ICMJE-aligned (Lancet-class): double-blind, trial
  registration + CONSORT flags, ethics statement required.
- **`cell_journal`** — Cell Press: 150-word Summary, Experimental Procedures,
  50-reference floor.
- **`arxiv_preprint`** — minimal preprint sanity profile (abstract-only
  structure, generous limits).

## [1.7.0] — 2026-09-09

### Fixed — the accuracy problem that mattered most: PDF extraction
- **Layout-aware, two-column PDF reading order.** Naive `extract_text()` reads
  glyph operators in stream order, which interleaves the two columns of
  IEEE/ACM-style papers line-by-line and silently corrupts *every* downstream
  engine (sentences, headings, statistics, similarity). PDF pages are now
  reconstructed from positioned text fragments: visual rows are grouped,
  split into runs at the column gutter, classified as full-width bands vs.
  left/right column runs, and emitted title-first, then left column, then
  right column. Pages that are not two-column fall back to plain order.
- **Running heads/footers removed cross-page, not per-page.** The previous
  blanket top/bottom band filter could silently delete the title of a short
  first page. Now a line is dropped only if it repeats identically on ≥60%
  of pages *and* the document has 3+ pages — single-page and short papers
  keep every line.
- **Typographic normalization**: ligatures (ﬁ/ﬂ/ﬃ → fi/fl/ffi), zero-width
  characters, soft hyphens, U+FFFD replacement chars, and end-of-line
  hyphenation ('sig-\nnificant' → 'significant') are repaired before any
  engine sees the text.
- An extraction note is recorded when a two-column layout was reconstructed,
  so users know the reading order was inferred.

### Added
- 9 ingestion tests (built with real generated PDFs): column separation,
  title preservation, running-head stripping, single-page protection,
  ligature/hyphen normalization. Suite at 225 tests.

## [1.6.1] — 2026-09-07

### Added — compilation-hygiene engine (#74)
- **`compilation_hygiene`** — the "sloppy submission" tells handling editors
  spot in seconds: broken LaTeX cross-references (`??` / `[?]` from failed
  `\ref`/`\cite` macros), broken Word fields ("Error! Reference source not
  found"), repository links not pinned to a commit hash or release tag
  (branch pointers rot; reviewers know it), and placeholder text (TODO,
  lorem ipsum, example.com, "your repo here"). All offline, exact-string
  based. Pinned links earn an INFO trust signal.

### Fixed
- Constructor arg-order bug in the engine's Finding calls (evidence/action/
  confidence transposed) caught by the compare test before it could ship.

## [1.6.0] — 2026-09-07

### Added — adversarial-review wave (#70–#73)
Four engines targeting the failure modes in the deep-dive research:
- **`physical_plausibility` (#70)** — deterministic physics/hardware math:
  claimed latencies below the speed-of-light RTT floor for the stated
  distance (US-EU ≈ 60 ms minimum), and training claims whose VRAM needs
  (12 bytes/param for AdamW fp16) exceed the declared GPU fleet without any
  offloading/quantization/parallelism escape hatch.
- **`ml_fairness` (#71)** — the two most common ML-reviewer objections:
  strawman-baseline detection (self-tuning vocabulary with no fair-comparison
  statement) and metric masking (high accuracy on explicitly imbalanced data
  with no balanced-accuracy/macro-F1/MCC/PR-AUC anywhere).
- **`corrections` (#72)** — statcheck false-positive prevention: papers using
  Greenhouse-Geisser / Bonferroni / Holm / BH-FDR corrections legitimately
  report corrected p-values that differ from raw recomputation; when
  correction vocabulary is present, discrepancies downgrade to INFO with an
  audit-trail note instead of an error. Also nudges about multiple-comparison
  corrections when ≥3 marginal (p=.03–.05) stats appear with no correction
  mentioned.
- **`proof_gaps` (#73)** — proof-dismissal phrase detection in formal
  sections ("trivially", "details omitted", "by simple algebra") that invites
  the Nitpicker reviewer attack; density-scored, math-context gated.
- 12 new tests. 209 total. Benchmark gate green (clean 80 / flawed 15,
  zero clean-paper false positives).

## [1.5.0] — 2026-09-07

### Added — OpenAlex research-graph engine (#69)
- **`openalex_verify`** — online reference-health verification against the
  OpenAlex open scholarly graph (250M+ works), enabled with `--online`:
  - **Reference resolution**: cited works unresolvable by DOI or title are
    flagged as hallucination candidates (HIGH when >25% unresolved).
  - **Retraction flags**: cited works carrying OpenAlex's `is_retracted`
    flag → **CRITICAL**.
  - **Venue scope mismatch**: the manuscript's keyword profile vs the
    venue's historical top concepts — disjoint profiles flagged MEDIUM
    (the classic desk-reject signal).
  - **Seminal-work gap**: no overlap with the venue's most-cited recent
    works → LOW informational nudge.
- **API key support**: `--openalex-key` CLI flag or `OPENALEX_API_KEY`
  environment variable; the key is sent per OpenAlex's `api_key` parameter
  spec. Works without a key too (polite-pool rate limits).
- Privacy note: only reference DOIs/titles and the venue name are sent as
  query parameters — never manuscript text.
- 6 new tests (mocked HTTP; offline stays a strict no-op). 197 total.

## [1.4.1] — 2026-09-07

### Changed — web GUI redesign
- **Full visual overhaul of the local web GUI**: gradient header with feature
  chips, card-based layout, modern system font stack, em-scale responsive
  typography (`html { font-size: clamp(...) }` — the entire UI scales smoothly
  from phone to 4K), hover/active states, full-width gradient action button.
- **Before/after comparison removed from the GUI** (per user request) — it
  remains fully available in the CLI: `papercheck --compare REVISED`.
- **Engine count now rendered dynamically** from the registry (`len(ALL_ENGINES)`)
  everywhere in the page — stale "67 engines" strings can never appear again.
- **Explicit no-retention notice** in the UI: "Nothing is stored — the temporary
  copy is deleted the moment your report is rendered, every time."

### Removed
- `revised` upload field, second drop zone, and the GUI comparison code path
  (`_run_compare`/`_save_temp`) — comparison is CLI-only now.

## [1.4.0] — 2026-09-07

### Added — GRIM/GRIMMER wave (#68)
- **`grim_engine` (#68)** — deterministic arithmetic verification of every
  reported `(M, SD, N)` triple, implementing the **GRIM test** (Brown &
  Heathers 2016): a mean of N integer values must equal `k/N` for some
  integer k — impossible values (e.g. M = 3.48 with N = 20, where k/20 can
  only end in .X0 or .X5) are flagged HIGH as arithmetic facts, not
  heuristics. **GRIMMER** extends the check to standard deviations via the
  integer sum-of-squares constraint, flagged MEDIUM with the integer-scale
  caveat stated in the finding text. Fully possible means earn an INFO
  "machine-verified" trust signal. The engine deliberately skips documents
  under 200 words and label-free scales are covered by the caveat language.
- Competitive-landscape research (Penelope.ai, Paperpal, Ripeta, Statcheck,
  GRIM implementations, ImageTwin, Proofig) translated into shipped engines;
  GRIM was the last deterministic stat check from that survey missing here.

### Fixed
- Float-equality bug in the GRIM core (`round(k/n) == round(mean)` on raw
  floats) — replaced with exact decimal-string comparison and candidate sums
  centred on `mean*N` instead of scanning `0..N`.

## [1.3.0] — 2026-09-06

### Added — deterministic verification wave
- **`statcheck` engine (#66)** — pure-Python recomputation of p-values from
  reported APA-style test statistics (t/F/χ²/r/z with df; stdlib-only special
  functions, no scipy). Flags: **decision errors** (reported and recomputed p
  on opposite sides of .05 — CRITICAL, the conclusion itself is wrong), gross
  mismatches (HIGH), inconsistency clusters (MEDIUM), and confirms
  fully-consistent result sets (INFO). Arithmetic, not heuristics.
- **`ugc_14word` engine (#67)** — the UGC 2018 (India) statutory similarity
  computation as specified in the Gazette regulations: clause-7 exclusions
  (<14-consecutive-word matches disregarded; references, acknowledgments,
  quotes excluded), clause-8 Level 0–3 bands with the actual statutory
  consequences, and the zero-tolerance Hypothesis/Results/Conclusions
  check. Runs against the author's own corpus (`--corpus`, e.g. thesis or
  prior papers — the Shodhganga-derived-paper scenario), fully offline.
- **Benchmark upgrade**: the flawed corpus paper now embeds a decision error
  (`t(58) = 1.20, p = .04`) that statcheck must catch on every run — the
  calibration gate now also verifies the deterministic layer.
- 9 new tests (179 total): distribution reference points, decision-error
  detection, clause-7 exclusion behavior, tier escalation, core-section
  zero tolerance.

### Fixed
- GUI startup messages: Ctrl+C explained, fallback URL printed, port-in-use
  hint suggests `--port`.
- `ugc_14word` token-span alignment with the metrics tokenizer and
  majority-overlap containment for core-section matching.

## [1.2.0] — 2026-09-06

### Added — limitation mitigations
- **Passage-level similarity detail** (`--format similarity|similarity-html`,
  requires `--corpus`): every matched passage quoted side-by-side with the
  source, passage-similarity percentage, and editor-style interpretation
  guidance — addressing "similarity ≠ plagiarism" with evidence instead of
  bare scores.
- **Benchmark harness** (`scripts/benchmark.py`) + shipped clean/flawed
  corpus (`papercheck/data/benchmark/`): measures stylometric-engine
  sensitivity, enforces score monotonicity (flawed must score strictly worse
  than clean), and audits false positives on the clean control. Exits
  non-zero on calibration regressions.
- **Venue-rules freshness**: presets carry a `rules_last_verified` date and
  every report surfaces it so users know what to re-check; `--venue-json`
  remains the override for exact current values.
- **Grammar discoverability**: without a LanguageTool server the report now
  includes an INFO finding with the one-line docker setup command (previously
  fully silent).

### Fixed — real engine bugs the benchmark exposed
- `conflicting_numbers`: distributor/hedge phrases no longer create false
  conflicts ("34 nodes *per group*" vs "120 nodes", "approximately 30");
  kept values carry quoted context evidence.
- Reproducibility ML trigger: a stray "models" in a reference title no
  longer demands hyperparameters (trigger requires explicit ML terms).
- Fake-reference signature: real DOIs (e.g. Zenodo `10.5281/...`) are no
  longer flagged as hallucination patterns; only placeholders (`doi: N/A`),
  `n.d.` citations, and page-numbered no-date entries match.
- Markdown ATX headings (`## Abstract`) are now parsed as sections and the
  `#` prefix is stripped from section names.
- AI-signal calibration: "dense template transitions" now responds to a
  realistic templated intro (~4-8 phrases) instead of requiring ~12; added
  "it was observed that"-family templates.

### Tests
- 14 new tests (170 total): similarity detail, conflicting-numbers logic,
  ML-trigger precision, fake-ref signature, markdown headings, freshness,
  grammar discoverability, and the benchmark gate.

## [1.1.2] — 2026-09-06

### Changed
- **Web GUI file-selection UX:** after picking a file, the drop zone itself
  turns green and shows the filename prominently (with a ✕ change button) —
  the selected file is no longer displayed as small text below the button.
  Both zones (manuscript + optional revised version) get the same treatment.

### Fixed
- Removed a duplicated drag-and-drop event listener from the GUI script.

## [1.1.1] — 2026-09-06

### Changed
- **PyPI distribution renamed `papercheck` → `paperengine`** — the name
  `papercheck` is already taken on PyPI by an unrelated project. The GitHub
  repo, the `papercheck` CLI command, and the Python import name are all
  unchanged; only the pip-installable distribution name now matches the repo.
  Install remains `pip install -e .` from a clone until the first PyPI upload.

## [1.1.0] — 2026-09-06

### Added
- **Before/after revision comparison** (`--compare REVISED` in the CLI; an
  optional second drop zone in the web GUI). Findings are matched across
  revisions by `(category, normalized title)` signature and classified as
  **fixed / still open / new**, with a readiness-score delta. Renderers for
  console and HTML (rich report with per-finding fix actions).
- **Repository hygiene:** MIT `LICENSE`, this changelog, `CONTRIBUTING.md`
  with engineering ground rules, and an overhauled README (badges, honest
  engine-status table, architecture map, feature index).
- **Release automation:** tag-triggered PyPI publish workflow (verifies the
  tag matches the package version before uploading) and a weekly scheduled
  maintenance job (offline test suite + `--update-rwdb` retraction-cache
  refresh, artifact upload, failure notification).

### Changed
- The web-UI multipart parser now returns all uploaded files by field name,
  enabling the optional "revised version" upload alongside the main file.
- CLI `--compare` accepts `--format html` for a rich side-by-side report and
  `--out FILE` to save it.

### Notes
- The readiness score, confidence model, and the "similarity ≠ plagiarism"
  framing are unchanged.

## [1.0.0] — 2026-09-06

### Added
- **65 check engines** covering ~300 distinct finding templates across 30
  categories: statistical/methodological, research design, EQUATOR reporting
  guidelines (all 15: CONSORT, PRISMA, PRISMA-ScR, STROBE, ARRIVE, STARD,
  SPIRIT, CARE, TRIPOD, SRQR, COREQ, MOOSE, TREND, STREGA, CHEERS + SAGER),
  writing quality, figures/tables, citations, integrity/fraud (paper mills,
  citation cartels, coerced citations, fake reviewers), AI-specific checks,
  submission/editorial, reproducibility/FAIR data, legal/ethical/safety,
  and post-submission (rebuttal, review-manipulation) analysis.
- **Dual standard:** 19 venue presets — international (IEEE ×3, ACM, Elsevier,
  Springer, Nature, MDPI, Wiley, T&F, PLOS, Frontiers) and national Indian
  (UGC-CARE, AICTE, NAAC, Scopus-Indian, single-column, thesis rules).
- **Web GUI** (`papercheck --gui`): drag-and-drop upload, standard + venue
  pickers, full report in the browser. Localhost-only, 25 MB cap, no network
  egress.
- **CLI:** `papercheck paper.docx [--standard national] [--venue ugc_care]`
  with `--batch` folder scanning (worst-first table + CSV), `--format
  console|markdown|html|fixplan|csv`, `--corpus` prior-papers overlap checks,
  `--online` Crossref lookups, `--update-rwdb` Retraction Watch DB cache
  (70k+ records), `--list-venues`.
- **Fix-plan generator:** prioritized, effort-estimated pre-submission
  checklist with deduplication of near-duplicate findings.
- **Readiness score:** saturating per-severity penalty model — a clean paper
  scores 100, one critical ≈ 77, and a long tail of LOW notes cannot zero it.
- **Packaging & CI:** installable package (`pip install -e .[all]`), global
  `papercheck` command, GitHub Actions CI on Python 3.10–3.13.
- **Docs:** README, USER_GUIDE.md, COVERAGE_MATRIX.md with the full
  standards-coverage audit.
- **150 tests** covering all engines, the web UI over real HTTP, and the
  scoring model.
