# Changelog

All notable changes to PaperEngine are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [SemVer](https://semver.org/).

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
