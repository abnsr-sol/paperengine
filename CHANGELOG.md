# Changelog

All notable changes to PaperEngine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

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
