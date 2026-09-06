<div align="center">

# PaperEngine

**Pre-submission rejection-risk analysis for academic manuscripts —
74 engines incl. deterministic p-value verification (statcheck) · dual
international / Indian standards · 100% local**

[![CI](https://github.com/abnsr-sol/paperengine/actions/workflows/ci.yml/badge.svg)](https://github.com/abnsr-sol/paperengine/actions/workflows/ci.yml)
[![Weekly maintenance](https://github.com/abnsr-sol/paperengine/actions/workflows/maintenance.yml/badge.svg)](https://github.com/abnsr-sol/paperengine/actions/workflows/maintenance.yml)
[![PyPI](https://img.shields.io/pypi/v/paperengine?color=8b5cf6&label=PyPI)](https://pypi.org/project/paperengine/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-179%20passing-brightgreen)](#development)

*What could cause this manuscript to be rejected at this venue, what evidence
suggests that risk, how serious is it, and what should the researcher fix?*

</div>

---

## Why PaperEngine exists

Most tools answer one narrow question: *"Is this text copied?"* or *"Does this
look AI-written?"*. Rejection happens for **dozens of other reasons** — missing
ethics statements, impossible statistics, unreferenced figures, template
violations, predatory venue traps, retracted citations. PaperEngine runs
**74 specialized engines** against your manuscript and returns every finding as:

```
Severity | Finding | Evidence (quoted from your paper) | Confidence | How to fix it
```

> **The honesty principle (by design, not marketing):**
> Similarity is **not** plagiarism. An AI-risk score is **not** proof of AI
> authorship. Every finding carries evidence + confidence, and the readiness
> score is informational — final judgment stays with humans, exactly how
> editors are trained to use iThenticate/Similarity Check.

---

## How to use

### Step 1 — Install (one time, under a minute)

Requirements: [Python 3.10+](https://www.python.org/downloads/). PDF support
needs `pypdf`, image forensics needs `Pillow` — both come with the `[all]` extra.

**Option A — straight from PyPI (simplest):**

```bash
pip install paperengine[all]
papercheck --list-venues    # verify: prints all 19 venue presets
```

**Option B — clone the source repo (development / latest changes):**

```bash
git clone https://github.com/abnsr-sol/paperengine.git
cd paperengine
pip install -e .[all]       # editable install — every git pull is picked up automatically
```

> **Windows tip:** if `pip` isn't on PATH, use `py -m pip install paperengine[all]`.
>
> **No-install option:** from the cloned folder, replace `papercheck` with
> `python -m papercheck` in any command below.

### Step 2 — Use the Desktop version (web GUI)

```bash
papercheck --gui                 # launches the server and opens your browser
papercheck --gui --port 9000     # custom port if 8765 is already taken
```

Then, in the browser:

1. **Drag your manuscript** (.docx / .txt / .md / .tex / .pdf) onto the upload zone — or click to browse
2. **Choose the standard** — International (IEEE/Elsevier/ACM…) or National (India: UGC/AICTE/NAAC)
3. **Pick the venue preset** — e.g. `ieee_conference`, `ugc_care`, `mdpi` (the list filters by standard)
4. Click **Check my paper** → the full report renders in the browser:
   readiness score + findings table (severity · finding · evidence · confidence · how to fix)

**Privacy / no retention:** the GUI runs on your machine only (localhost).
The file is parsed in memory, checked by the same 74 engines as the CLI, and
the temporary copy is **deleted the moment your report is rendered — every
time, no exceptions**. Nothing is stored, nothing leaves the machine.

> 💡 Before/after comparison is a **CLI feature**: `papercheck v1.docx
> --compare v2.docx` gives you fixed / still-open / new findings plus the
> score delta.

### Step 3 — Use the CLI version

Basic pattern:

```bash
papercheck <file> [--standard international|national] [--venue <preset>] [--format <format>] [--out <file>]
```

Common tasks:

| You want to… | Command |
|---|---|
| Check a paper (international) | `papercheck paper.docx --venue ieee_conference` |
| Check a thesis (Indian national) | `papercheck thesis.docx --standard national --venue ugc_care` |
| Save a styled HTML report | `papercheck paper.docx --venue mdpi --format html --out report.html` |
| Get the prioritized fix plan | `papercheck paper.docx --venue ieee_conference --format fixplan` |
| Compare two revisions | `papercheck v1.docx --compare v2.docx --venue elsevier --format html --out diff.html` |
| Batch-scan a whole folder | `papercheck --batch papers/ --venue ugc_care --format csv --out summary.csv` |
| Crossref + OpenAlex online lookups | `papercheck paper.docx --venue springer --online --mailto you@university.edu --openalex-key YOUR_KEY` |
| Compare vs your prior papers | `papercheck paper.docx --corpus ./my_prior_papers/` |
| List all venue presets | `papercheck --list-venues` |

Without installing, run from the cloned folder with `python -m papercheck …` instead:

```bash
python -m papercheck sample_paper.txt --venue elsevier

# Full report to a file (console | markdown | html | fixplan | csv)
python -m papercheck paper.docx --venue mdpi --format html --out report.html

# Indian national standards (UGC/AICTE/NAAC)
python -m papercheck thesis.docx --standard national --venue ugc_care

# Prioritized fix plan (criticals first, effort-estimated)
python -m papercheck paper.docx --venue ieee_conference --format fixplan

# Batch-scan a folder, worst-first summary table or CSV
python -m papercheck --batch papers/ --venue ugc_care --format csv --out summary.csv

# Before/after revision comparison
python -m papercheck v1.docx --compare v2.docx --venue elsevier --format html --out diff.html

# With online lookups (Crossref): duplicate-publication + DOI validation
python -m papercheck paper.docx --venue springer --online --mailto you@university.edu --openalex-key YOUR_KEY

# Compare against your already-published papers (duplicate / "no new content")
python -m papercheck paper.docx --corpus ./my_prior_papers/
```

### One-time retraction database (optional, recommended)

```bash
papercheck --update-rwdb
# caches 70k+ retraction records (CC-BY 4.0, Crossref) at
# %TEMP%/papercheck_rwdb.json (Linux/macOS: /tmp/papercheck_rwdb.json).
# From then on, retracted-reference screening runs against the full DB offline.
```

---

## What the engines check

| Cluster | Engines | Sample findings |
|---|---|---|
| **Statistics & methodology** | `statistics`, `stats_deep`, `stats_plan`, `fabrication`, **`statcheck`**, **`grim_engine`** | p>0.05 called significant, missing effect sizes, impossible r/n/%, no power analysis, normality untested, p-hacking clusters, Benford's-law anomalies — plus **deterministic p-value recomputation** (decision errors flagged, a CRITICAL) and **GRIM/GRIMMER mean/SD impossibility checks** (M = 3.48 with N = 20 is arithmetic that cannot exist) |
| **Research design** | `methodology`, `repro_env`, `reproducibility` | no ethics/IRB approval, unregistered trials, missing benchmarks/ablation, no hyperparameters/seeds, no Docker/conda env |
| **EQUATOR guidelines (all 15)** | `reporting_guidelines`, `domain_checklists`, `domain_checklists2` | CONSORT, PRISMA, PRISMA-ScR, STROBE, ARRIVE, STARD, SPIRIT, CARE, TRIPOD, SRQR, COREQ, MOOSE, TREND, STREGA, CHEERS essentials |
| **Writing quality** | `language`, `writing_depth`, `paragraph_structure`, `transitions`, `redundancy` | weasel words, nominalization, >200-word paragraphs, no topic sentences, missing roadmap, abstract/intro/conclusion overlap |
| **Claims & novelty** | `claims`, `overclaiming`, `design_claims`, `novelty` | "novel/first" without justification, causal claims from observational data, abstract ≈ conclusion |
| **Figures & tables** | `figures`, `figure_quality`, `image_forensics`, `image_manipulation` | uncited figures, low DPI, blots without markers, microscopy without scale bars, duplicated panels (perceptual hash), ELA splicing |
| **Citations** | `citations`, `citation_integrity`, `reference_verify`, `reference_completeness`, `citation_age` | never-cited refs, numbering gaps, mixed styles, broken DOIs, missing volume/pages, "as cited in" secondary cites, stale lists |
| **Integrity & fraud** | `integrity`, `self_plagiarism`, `paper_mill`, `citation_cartel`, `author_network`, `peer_review`, `reviewer_fraud`, `predatory_journal`, `retracted_refs` | self-citation rings, coerced citations, free-mail reviewers, same-domain reviewer conflicts, salami slicing, retracted work (70k-record DB) |
| **AI-specific** | `ai_risk`, `llm_artifacts`, `ai_disclosure_deep`, `policy` | stylometric signals, template phrasing, tortured phrases, fake-ref signatures, per-tool disclosure gaps, EU AI Act, AI-as-author (critical) |
| **Submission & editorial** | `submission`, `submission_package`, `editorial_format`, `author_info`, `venue_extras`, `abstract_quality`, `scope_match` | missing statements, no ORCID, keyword count, line numbers, running head, ACM CCS, Elsevier highlights, scope mismatch |
| **Authorship & ethics** | `authorship`, `legal_ethics`, `safety_ethics`, **`ugc_14word`** | CRediT roles, ghost/gift authorship signals, patient consent, HIPAA/GDPR, biosafety levels, DSMB, dual-use — plus the **UGC 2018 statutory similarity computation**: clause-7 exclusions (14-word window, references/quotes/acknowledgments), Level 0–3 bands with the actual statutory penalties, and the zero-tolerance Hypothesis/Results/Conclusions check |
| **Data & FAIR** | `data_license`, `funder_compliance` | no dataset DOI, proprietary formats, missing licenses, NIH/Plan S/Horizon obligations |
| **Venue compliance** | `compliance`, `consistency`, `forensics` | word/page/figure limits, mixed fonts, hidden text, lookalike characters, conflicting numbers, acronym drift |
| **Post-submission** | `rebuttal`, `cross_check` | response-letter tone/evidence/completeness, inconsistent n across tables, figure/table duplicate data |

**The full 48-angle rejection map** (with engine-by-engine status) is in
[`COVERAGE_MATRIX.md`](COVERAGE_MATRIX.md); every engine is listed with its
exact checks in the architecture section below.

---

## Venue presets (dual standard)

```bash
papercheck --list-venues
```

| International | National (India) |
|---|---|
| `ieee_conference`, `ieee_journal`, `ieee_letters` | `ugc_care` (UGC-CARE / plagiarism levels) |
| `acm` (CCS concepts required) | `aicte` (AICTE norms) |
| `elsevier` (highlights, CRediT, data availability) | `naac` (NAAC research criteria) |
| `springer`, `nature`, `science`, `mdpi` | `scopus_indian` (Scopus-indexed Indian journals) |
| `wiley`, `tandf`, `plos`, `frontiers` | `indian_1col` (single-column university format) |
| `generic` (no venue rules) | `ugc_thesis` (Shodhganga, thesis rules) |

Every preset works in both the CLI and the web GUI; `--venue-json rules.json`
accepts exact limits for any venue not yet preset.

---

## Output formats

| Format | Flag | What you get |
|---|---|---|
| Console | `--format console` | color-graded terminal table (default) |
| Markdown | `--format markdown` | for repos, PRs, and lab notebooks |
| HTML | `--format html` | standalone styled report, shareable file |
| **Fix plan** | `--format fixplan` | prioritized to-do list, criticals first, effort estimates ("~30 min", "~2 h"), near-duplicates deduplicated |
| **Similarity detail** | `--format similarity` (+`-html`) | with `--corpus`: every matched passage quoted **side-by-side** with the source and editor-style reading guidance — what matched, not just how much |
| CSV | `--format csv` | batch summaries for spreadsheets |

Every finding, in every format, carries: **severity · finding · evidence ·
confidence · concrete action**.

---

## Architecture

```
papercheck/
├── __main__.py        CLI entry point (single file, batch, compare, gui modes)
├── ingestion.py       DOCX (stdlib zip+XML), TXT/MD/TeX, PDF (optional pypdf)
├── metrics.py         text statistics (readability, burstiness, n-grams, …)
├── venues.py          19 venue rule presets + --venue-json override
├── risk.py            Finding / Severity / RiskReport / readiness score
├── report.py          console, Markdown, and HTML renderers
├── fixplan.py         prioritized, effort-estimated fix-plan renderer
├── compare.py         before/after revision diff (fixed / still open / new)
├── batch.py           folder scanning, worst-first ranking, CSV writer
├── rwdb.py            Retraction Watch DB download/cache/screening
├── webui.py           local drag-and-drop GUI (stdlib http.server)
└── checks/            74 engines — one per rejection angle
    compliance · structure · language · citations · claims · ai_risk ·
    integrity · novelty · consistency · figures · forensics · policy ·
    statistics · overclaiming · self_plagiarism · citation_integrity ·
    reproducibility · submission · ugc_plagiarism · reference_verify ·
    fabrication · methodology · reporting_guidelines · writing_depth ·
    legal_ethics · citation_cartel · paper_mill · predatory_journal ·
    retracted_refs · submission_package · image_forensics · stats_deep ·
    design_claims · redundancy · domain_checklists · literature_search ·
    scope_match · rebuttal · crossref_verify · author_network ·
    reviewer_fraud · image_manipulation · llm_artifacts · supplementary ·
    data_license · abstract_quality · citation_age · sex_gender ·
    stats_plan · editorial_format · author_info · figure_quality ·
    venue_extras · ai_disclosure_deep · safety_ethics · authorship ·
    repro_env · paragraph_structure · transitions ·
    reference_completeness · funder_compliance · peer_review ·
    domain_checklists2 · grammar_tool (optional LanguageTool) · cross_check ·
    statcheck (p-value recomputation) · grim_engine (GRIM/GRIMMER) · ugc_14word (UGC 2018 clause-7/8)
    physical_plausibility (speed-of-light & VRAM math) · ml_fairness (strawman baselines,
    metric masking) · corrections (GG/Bonferroni/FDR awareness) · proof_gaps (dismissal phrases)
```

**Extending:** add `checks/my_angle.py` with `run(doc, ctx) -> [Finding]`,
register it in `checks/__init__.py`, add tests. New venue: one dict in
`venues.PRESETS`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules
(evidence + confidence + action on every finding, offline-first, dual standard).

Plug-in points already in the code: LanguageTool server (`grammar_tool`),
Crossref/OpenAlex (`--online`), Retraction Watch DB (`rwdb.py`), AI-detector
APIs (`checks/ai_risk.py` — documented hook, no verdicts).

---

## Project layout

| File | Purpose |
|---|---|
| [`README.md`](README.md) | this overview |
| [`USER_GUIDE.md`](USER_GUIDE.md) | 5-minute researcher walkthrough (every flag explained) |
| [`COVERAGE_MATRIX.md`](COVERAGE_MATRIX.md) | the full standards-coverage audit, angle by angle |
| [`CHANGELOG.md`](CHANGELOG.md) | release history (Keep a Changelog format) |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | engineering ground rules + PR checklist |
| [`LICENSE`](LICENSE) | MIT |
| `scripts/` | sample-document generator, weekly maintenance script |

---

## Development

```bash
python -m unittest discover -s tests        # 150+ tests, offline, no services needed
python scripts/maintenance.py               # tests + retraction-cache refresh
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the full
suite on **Python 3.10 – 3.13** on every push and PR. A weekly scheduled job
refreshes the retraction database and re-runs the suite. Tagging `vX.Y.Z`
triggers the PyPI publish workflow (tag/version match is verified first).

> **To enable PyPI uploads:** already done — the package lives at
> [pypi.org/project/paperengine](https://pypi.org/project/paperengine).
> Every future `v*` tag publishes automatically via the trusted publisher.

---

## Honest limitations — and what we built to overcome them

Every tool has limits. Most hide them; we ship **mitigations and measurement**
for ours:

| # | Limitation | Mitigation shipped in the tool |
|---|---|---|
| 1 | **Similarity ≠ plagiarism.** Overlap requires human interpretation (Crossref itself warns against automatic rejection thresholds). | **Passage-level similarity detail** (`--format similarity`): every matched passage quoted side-by-side with the source document and classified (own prior work / quotable / boilerplate) — the same three questions editors are trained to ask. Never a verdict, always evidence. |
| 2 | **AI detection is probabilistic.** Low burstiness and template transitions occur naturally in non-native and technical writing. | **Calibrated in the open** (`scripts/benchmark.py`): a shipped clean-vs-flawed corpus measures what the stylometric engines actually fire on; the AI-risk engine reports an uncertainty band, never a single verdict, and deliberately refuses typography myths ("em dash = AI") that have no scientific support. |
| 3 | **Grammar heuristics ≠ a real grammar engine.** | **Discoverable upgrade path**: when no LanguageTool server is found, the report says so (INFO) with the exact one-line docker command; start one and full grammar checking is picked up automatically next run. |
| 4 | **Venue rules change** without notice. | **Freshness surfaced in every report**: each run states when the preset's numbers were last verified against the publisher's guidelines, and `--venue-json` overrides any limit with exact current values. |
| 5 | **The readiness score is informational** — it is not a prediction of acceptance. | **Monotonicity is enforced**: the benchmark harness fails CI if the flawed corpus paper ever outscores the clean one — the score must discriminate, or the release doesn't ship. |
| 6 | **What no software can check:** whether the science is *true*, whether ideas match paywalled prior work, and the reviewer's subjective "so what?". | Nothing — and we won't pretend otherwise. Tools that claim to check these are selling overconfidence. |

Run the benchmark yourself: `python scripts/benchmark.py` (or `--json` for
machine-readable output). It exits non-zero if calibration regresses.

---

## License

[MIT](LICENSE) — free for research, commercial products, and institutions.
