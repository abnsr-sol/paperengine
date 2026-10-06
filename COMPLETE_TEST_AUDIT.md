# PaperEngine — Complete Test & Recon Audit
**Date:** 2026-09-20 · **Mode:** read/run only (nothing changed) · **Auditor hats:** developer, QA, PM, tech lead
**Repo:** `D:\perfectpapercheck` · **HEAD:** `cd04a19` (2026-09-19) · **Version:** 1.11.0 · **Engines:** 94 registered

---

## 0. Verdict
The tool is in **good shape and genuinely works** — 301 tests green, benchmark monotonic, 13/13 eval vectors pass, all CLI formats work, graceful error handling. The single most important defect is a **systematic argument-order bug in 14 engines** that silently corrupts the `action` field and the `confidence` used in scoring. Everything else is doc/version drift or polish.

---

## 1. What I actually ran (evidence)
| Check | Command | Result |
|---|---|---|
| Unit tests | `python -m unittest discover -s tests` | **301 pass, 0 fail, 5 skip** (127s) |
| Benchmark | `python scripts/benchmark.py` | clean **91** (42 findings, 0 serious) / flawed **42** (51 findings, 10 serious); **monotonic PASS**; **0 CRITICAL on clean** |
| Vector eval | `python scripts/vector_eval.py` | **13/13 PASS**, 100% recall on every positive category |
| CLI smoke | `papercheck sample_paper.docx/.txt` | exit 0, **0 engine errors**, 60 findings, readiness 69/100 |
| CLI formats | `--format json/markdown/csv/console/fixplan/similarity` | all produce valid output (JSON parses; keys `document,venue,readiness_score,stats,findings`) |
| `--list-venues` | `papercheck --list-venues` | 25 lines, International + National presets |
| Fuzzing | empty / whitespace / binary / CJK / refs-only / extreme-numbers / 660KB | **no crash, 0 engine errors** |
| Malformed input | `.docx` that isn't a zip | graceful `Error: … is not a valid zip/.docx file`, exit 2, **no traceback** |
| Missing file | nonexistent path | graceful `Error: file not found`, exit 2 |
| Static AST scan | all 94 engines | 44 numeric-`action` call-sites; 2 bare excepts |
| Import/profile | `-X importtime`, `cProfile` | see §4 |

---

## 2. Bugs & mistakes (ranked)

### 🔴 D1 — Systematic `action`/`confidence` argument swap (HIGH)
**44 `Finding(...)` call-sites across 14 engines** pass the confidence float into the `action` slot and the action text into the `confidence` slot.
- Engines: `author_identity`(5), `citation_graph`(4), `clinicaltrials_gov`(6), `compression_ai`(2), `corrections`(2), `iclac_celllines`(2), `image_forensics`(2), `image_manipulation`(2), `literature_search`(2), `openalex_verify`(6), `proof_gaps`(2), `pubmed_verify`(3), `redundancy`(1), `rrid_validate`(5).
- Confirmed at runtime: `author_identity` emits `action='0.95'`, `confidence=0.5`; `citation_graph` emits `action='0.5'` / `'0.55'`.
- **Why it matters:** `risk.py:125` scores `severity.weight × confidence`. The string confidence is coerced to **0.5** by `_as_confidence` (risk.py:90), so every affected finding is scored at 50% and **the readiness score is skewed**. Reports also display `action: 0.95` instead of advice text.
- **Root cause:** `Finding` field order is `(…, action, confidence, …)`; these engines use `(…, confidence, action)`. The `__post_init__` even documents this exact transposition — it crash-guards but never fixes the source.
- **Fix sketch:** swap the two arguments at each of the 44 sites (or add keyword args); add a regression test asserting `action` is non-numeric.

### 🟠 D2 — Doc / version drift (MEDIUM)
| Artifact | Says | Reality |
|---|---|---|
| `pyproject.toml` description | "65 check engines" | **94** |
| README badge | "tests-292 passing" | **301** |
| README body | "150+ tests" | **301** |
| `CHANGELOG.md` top entry | 1.11.0 (2026-09-15) | 6 newer commits (→2026-09-19) undocumented |
| `dist/` wheels | 1.1.0 / 1.1.1 / 1.4.0 | current **1.11.0** (stale) |
| PyPI `paperengine` | **1.9.0**, "65 check engines" | repo **1.11.0** (2 versions behind) |
| Local git branch | ahead of `origin/main` by **4 commits** | unpushed |

### 🟡 D3 — CI doesn't gate on calibration (MEDIUM)
`.github/workflows/ci.yml` runs `unittest` + a CLI smoke test on Python 3.10–3.13, but **not** `benchmark.py` or `vector_eval.py` — so a calibration/FP regression can merge green. Recent runs: latest `success`, but **2 of the last 3 failed** (2026-09-15).

### 🟢 D4 — Minor code hygiene (LOW)
- Two bare `except: pass` in `fabrication.py:151,158` (mask all errors silently).
- PyPI name **collision**: `papercheck` on PyPI (v0.3.4) belongs to a different author (`cgarryZA`); the project correctly publishes as `paperengine`, but `dist/papercheck-1.1.0.whl` is a stale/confusing artifact.

### ℹ️ D5 — Transient working-tree churn (observation)
During the audit the entire top level briefly showed as `deleted` in git, then restored (timestamps 20:15). Likely a parallel session doing a stash/checkout. **No data lost**; final `git status` clean. Worth knowing if you run tools concurrently.

---

## 3. What is *solid* (don't touch)
- Fault-isolated pipeline (`run_all_engines`) — 0 engine errors across all fuzz inputs; a bad engine can't blank a report.
- `Finding.__post_init__` defensive coercion — no crashes on bad types (it *hides* D1, but the crash-safety is real).
- Reference numbering, retracted-citation, statcheck/GRIM/SPRITE/TIVA/p-curve/Carlisle, tortured-phrases, EQUATOR-40, trial/IRB/consent, predatory/venue-hijack, image dhash, Crossref/OpenAlex verify — all exercised by vectors and passing.
- CLI error handling is clean and non-zero on failure.

---

## 4. Performance reality (important — mostly *not* the project's fault)
- **Sandbox interpreter startup ≈ 11–13 s** — a *bare* `python -c "pass"` costs ~12 s here. That dominates the "29 s CLI" impression. **This is environmental, not your code.**
- **Actual project compute ≈ 3 s** (cProfile): engines ≈ 1.4 s; `grammar_tool` ≈ 0.6 s (it probes a local LanguageTool server at `127.0.0.1:8081` with a 1.5 s timeout even when offline — cached, once).
- **Scaling is linear but with a high constant:** a 660 KB document took ~45 s of compute. Normal papers (~30 KB) ≈ 2–3 s. Large theses will be slow.
- **No parallelism — and it is NOT the win it looks like (corrected).** An earlier version of this audit claimed a thread pool was "an easy 2–4× win". That was **measured and disproven**: the engines are CPU-bound pure Python under the GIL (profiling: one engine = 24% of runtime), so a `ThreadPoolExecutor(4)` made wall-clock **0.67–0.92× (slower)** with CPU time flat. The pipeline stays sequential by design. **The real wins were algorithmic, not concurrent:**
  - `compression_ai` used `lzma.compress()` at its default `preset=6`, allocating an ~8 MB dictionary **per paragraph** (~74 ms/para; 24% of runtime) → now `preset=1`, ~2× faster with identical ratios.
  - `design_claims` used `[^.]*VERB[^.]*\.` patterns that backtracked quadratically (613 ms on a 47 KB body; 13% of runtime) → replaced with a sentence split (21 ms, ~18× faster, identical hits).
  Together these cut the two hottest engines' cost by roughly an order of magnitude.

---

## 5. Free AI / ML & open-source you can add
### 5.1 Fully offline / local (fits the "100% offline, zero-dependency" promise)
| Tool / model | Adds | License |
|---|---|---|
| **LanguageTool** (self-host) | real grammar/style — already wired via `grammar_tool`; bundle/dockerize it | LGPL |
| **Ollama** + a small local LLM (Llama 3.x / Mistral / Qwen) | opt-in plain-language explainer of findings, fully offline | MIT/Apache |
| **sentence-transformers** (`all-MiniLM-L6-v2`) | semantic similarity → self-plagiarism, claim↔evidence, overlap | Apache-2.0 |
| **Hugging Face** `Hello-SimpleAI/chatgpt-detector-roberta`, `openai-community/roberta-base-openai-detector` | AI-text detection beyond phrase lists | MIT |
| **scispaCy / SciBERT** | scientific NER + better sentence/section segmentation | Apache/MIT |
| **GROBID** | high-quality PDF → structured TEI (references, sections) | Apache-2.0 |
| **Tesseract OCR** | read text inside figures (blot labels, axis numbers) | Apache-2.0 |
| **OpenCV / scikit-image** | image forensics: clone/splice detection, Error-Level Analysis | BSD |
| **pypdf / pdfplumber** | (already used) layout-aware extraction | BSD/MIT |

### 5.2 Free online APIs (opt-in, `--online`)
- **Crossref** (metadata + **Retraction Watch** now inside Crossref REST), **OpenAlex**, **DOAJ**, **PubMed/Europe PMC**, **ClinicalTrials.gov**, **ORCID**, **ROR**, **Semantic Scholar**, **arXiv**.
- **Free LLM tiers** for the opt-in explainer: **Google AI Studio (Gemini)**, **Groq**, **Mistral**, **Hugging Face Inference** — or keep it offline with Ollama.

### 5.3 Free datasets to bundle
Retraction Watch (via Crossref), DOAJ journal list, ICLAC cell lines, RRID, EQUATOR guidelines, Think.Check.Submit criteria.

### 5.4 Highest-value additions (in order)
1. **Fix D1** (the arg-order bug) — biggest correctness win, trivial effort.
2. **Wire benchmark + vector gates into CI** (D3) — locks in calibration.
3. **Parallelize engines** (§4) — 2–4× speedup, low risk.
4. **Local embeddings (sentence-transformers)** — unlocks external-similarity/plagiarism, the biggest missing *capability*.
5. **Opt-in local LLM explainer (Ollama)** — big UX win, stays offline.
6. **Image forensics upgrade** (OpenCV clone/splice) — beyond today's duplicate-panel dhash.
7. **Publish current version to PyPI** (1.9.0 → 1.11.0) + refresh docs/CHANGELOG.

---

## 6. One-line summary of every mistake
1. **44 findings show a number as "action" and lose their confidence → score skewed** (14 engines).
2. 2 silent `except: pass` in fabrication.
3. pyproject says "65 engines" (actually 94).
4. README test badge says 292 / body says 150+ (actually 301).
5. CHANGELOG stops at 1.11.0; 6 commits undocumented.
6. `dist/` wheels stale (1.1.0/1.1.1/1.4.0).
7. PyPI `paperengine` stuck at 1.9.0 (+ "65 engines" metadata).
8. 4 local commits unpushed.
9. CI doesn't run benchmark/vector gates; 2 of last 3 runs failed.
10. No engine parallelism; high regex constant → large docs slow.
11. `papercheck` PyPI name taken by another author (collision).
12. No external-corpus similarity / plagiarism engine yet.
13. Image forensics limited to duplicate-panel detection.
14. English-only text checks (CJK papers slip through).

*Read/run only — no files were modified. Report written to `COMPLETE_TEST_AUDIT.md`.*
