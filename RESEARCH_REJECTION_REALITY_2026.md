# RESEARCH — Where Papers Actually Fail (2026 Reality) vs What PaperEngine Checks

**Date: 2026-10-12 · Status: live research + line-by-line code audit · Repo: v1.13.x, 98 engines**

Purpose: ground the next engine wave in *observed editorial outcomes*, not in
internally-invented coverage angles. Every claim below carries a source; every
gap carries the probe that proved it is a gap.

---

## PART 1 — The real world: why manuscripts die

### 1.1 Desk rejection is the dominant failure mode

| Fact | Number | Source |
|---|---|---|
| Median desk-rejection rate across 88 journals that publish a figure | **50%** | Manusights desk-rejection table, 88 journals, read 2 Oct 2026 |
| Range | 6.5% (Geosci. Model Dev.) → ~90% (Am. J. Public Health) | same |
| Medicine, median across 23 journals | **70%** | same |
| Nature / Science / Nature Communications | 79.1% / 82.6% / 72.5% | same (peer-reviewed sources) |
| PLOS ONE (megajournal, "sound science" bar) | 30.8% | PLOS ONE journal information, Jan–Jun 2023 |
| Time to desk rejection, median (IJPM, n=898 rejection reports) | **3 days** | Menon et al. 2020, *Ind J Psych Med*, PMC9022928 |
| Share of rejections that were desk rejections (IJPM) | **69.8%** | same |
| Transport portfolio, Elsevier transfer system (n=5,036) | **83.6%** of rejections were desk | Wu et al. 2024, *Commun Transp Res* 4:100129 |

**Consequence:** a pre-submission tool must optimise for the *editor's first
read*, because most manuscripts never get a second one.

### 1.2 The ranked reasons editors actually give

**Desk stage (editor only, minutes to days):**

| Rank | Reason | Evidence |
|---|---|---|
| 1 | **Out of scope / no journal fit** | Menon 2020: top desk reason; TRD 2023 annual summary: **35% of desk rejects = out of scope**, 7% = poor writing (cited in Wu 2024) |
| 2 | **No novelty / insufficient significance** | Menon 2020; Edmans, "Learnings from 1,000 Rejections" (*Rev Finance*, 2025): lack of novel contribution, importance of findings, scope alignment |
| 3 | Format / technical non-compliance | journals reject in minutes for predictable format failures (CheckMyManuscript; Editage) |
| 4 | Poor writing visible in title/abstract | TRD: 7% of desk rejects explicitly "poor writing" |

**Peer-review stage (reviewer, ~42 days median):**

| Rank | Reason | Evidence |
|---|---|---|
| 1 | **Inappropriate study design** | Menon 2020 (top post-review reason) |
| 2 | **Poor methodological description** | Menon 2020 |
| 3 | **Weak study rationale** ("why does this matter?") | Menon 2020 |
| 4 | **Poor writing quality** | Menon 2020 |
| 5 | Statistical errors | Makin & Freud 2019 "Ten common statistical mistakes" (PMC6785265, 309 cites); Green et al. 2025 "Top 10 statistical pitfalls" |
| 6 | Missing reporting-guideline items | 86% of studies show suboptimal EQUATOR adherence (Samaan 2013, PMC3649856) |

**Relevance to us:** design/rationale/writing are *argument-structure* checks,
not regex checks on numbers. That is where our coverage thins out.

### 1.3 Why papers get retracted (the post-publication mirror)

Okyay et al. 2025, *J Korean Med Sci* 40:e300 — 16,041 retracted medical papers,
1975–2024, Retraction Watch Database, 68 reason categories:

| Reason | Share |
|---|---|
| **Data concerns** (unreliable results 39.3%, data 32.0%, results 18.0%, image 4.3%) | **31.47%** |
| **Fraud** (paper mill 63.1% of this bucket, falsification 13.7%, forged authorship 6.9%) | **11.37%** |
| **Peer-review issues** (fake peer review 36.0%) | **11.21%** |
| **Referencing issues** (97.6% "concerns with referencing"; cites retracted work 2.4%) | **7.54%** |
| **Ethical issues** (lack of IRB 47.6%, no informed consent 27.5%) | **7.09%** |
| Duplication (article 32.9%, **image 30.5%**) | 6.31% |
| Error (data 25.6%, analyses 16.6%, methods 16.4%) | 5.76% |
| Plagiarism | 4.61% |
| **Randomly generated content** (AI, unverified) | now a standing top-10 category |

Misconduct accounts for ~60% of retractions as of April 2026 (The Scientist,
2026-05-07). Data concerns double every ~5.5 years.

### 1.4 The 2026 shock: fabricated references

Lancet systematic review + audit, May 2026 (Topaz et al.; reported by STAT
2026-05-07, Retraction Watch 2026-05-07, CIDRAP 2026-05-08):

| Year | Papers containing ≥1 fabricated reference |
|---|---|
| 2023 | 1 in **2,828** |
| 2025 | 1 in **458** |
| 2026 | 1 in **277** (12-fold rise in two years; 97.1M references checked; >4,000 nonexistent citations found) |

Frontiers: *"Around 5% of manuscripts show potential reference-related issues
flagged through our checks"* (Elena Vicario, cited Apr 2026).
Picazo-Sanchez et al. 2026 (*Data*, 11:122): 127,063 citations from 3,541 papers.

**This is now the single highest-frequency integrity failure that a
*pre-submission, offline* tool can act on** — and, as §2.1 shows, we do not
check it offline at all.

### 1.5 The 2026 rules that kill submissions outright

- **AI declaration is mandatory almost everywhere; AI as author is banned
  everywhere.** Undisclosed AI use → delay, rejection, or ethics action
  (Elsevier / Wiley / T&F / Springer Nature policies; Enago May 2026;
  Apporya Jul 2026; JOMS Sept 2026).
- **Similarity thresholds are numeric and enforced:** <15% overall is the
  effective norm (UGC-CARE, most Indian journals, many Elsevier titles), with
  **no single source >3–5%**; AJR uses 35% total / 10% single-source as the
  "major plagiarism" line.
- **arXiv now rate-limits to 2 submissions/person/month explicitly to make
  moderator rejection of AI slop easier** (arXiv blog, 2026-10-01).
- **Wiley ships ImageTwin image screening; Springer Nature ships the PPS
  tortured-phrase tool** — publishers screen *before* review now (Jun/Jul 2026).

---

## PART 2 — The audit: what we check, probed against that reality

Method: registry dump (`ALL_ENGINES` → 98 engines, 0 orphans) + targeted live
probes through `run_all_engines` with deliberately flawed manuscripts.

### 2.1 ❌ GAP 1 — Offline fabricated-reference detection does not exist

**Reality:** 1-in-277 papers (2026), 5% of Frontiers submissions, 7.54% of
retractions, and the only integrity failure rising 12-fold.

**Probe:** six references — future-dated (2031, 2027), reversed page range
(88–55), author-less, all DOIs missing:

```
[1] A. Smith, B. Jones. Nature 599, 120-135 (2031).
[2] J. Doe. Science 380, 1-4 (2027).
[3] K. Lee, R. Patel. Lancet 401, 88-55 (2025).
[4] Retrieved from https://example.com on 12 March 2024.
[5] Anonymous. Journal of Advanced Research 12, 1-9 (2024).
[6] X. Wang, Y. Chen, Z. Liu, et al. PLOS ONE 19, e0280001 (2024).
```

**Result: exactly one finding** — `Medium · reference_verify · Most references
lack DOIs`. Nothing noticed a citation dated **2031**. Nothing noticed a page
range that runs backwards.

**Why:** hallucination detection lives only in `crossref_verify` /
`openalex_verify`, both hard-gated behind `--online`. The offline path — which
is the *default* path, and the one the whole project is built around — has no
reference-forensics engine at all.

`reference_completeness` only checks that *metadata is present* (year exists,
volume exists); `reference_verify` only checks *structure* (numbering, style,
duplicate). Neither asks **"is this metadata physically possible?"**

### 2.2 ❌ GAP 2 — `scope_match` returns zero findings on the default venue

**Reality:** out-of-scope is the **#1 desk-rejection reason** (35% of desk
rejects in the TRD dataset; top desk reason in Menon 2020).

**Probe:**

```python
for v in ['generic', 'ugc_care', 'ieee_conference']:
    len(scope_run(doc, CheckContext(venue=v)))
# → generic 0, ugc_care 1, ieee_conference 1
```

`describe('generic')` returns `"International -- unknown"`, which matches no
key in `_SCOPE`, so the engine returns `[]` immediately. **The bare command
`papercheck paper.docx` — our documented default, and what the GUI does when
no preset is chosen — performs no scope check whatsoever**, while
`venue_hijack` dutifully prints "No target venue detected · venue vetting
skipped". The single most common reason for rejection is silently uncovered in
the default run.

Secondary defect: `_SCOPE` only scans `body_text`. Scope is judged from
**title + abstract + keywords** — exactly what an editor reads in 3 days.

### 2.3 ❌ GAP 3 — No title ↔ abstract ↔ keywords ↔ body coherence check

**Reality:** an editor's first read *is* title + abstract; "weak/unclear
research objectives" and "poor writing" are named desk-reject reasons.

**Probe:** a manuscript titled *"Deep Learning for Diabetic Retinopathy
Screening"* with matching abstract/keywords, followed by a body — ran all 98
engines. **Nothing compared the title's topic to the body's topic.** The only
title handling anywhere is `structure.py` (length/generic-opener) and
`forensics.py` (encoding). Two engines read `doc.metadata` at all.

A manuscript whose body is about something other than its title is a
desk-reject and a review-reject simultaneously, and it is trivially checkable
offline with information we already parse.

### 2.4 ❌ GAP 4 — No rationale / research-gap / "so what?" engine

**Reality:** Menon 2020 names **weak study rationale** a top-3 post-review
rejection reason; Edmans 2025 lists "importance of the findings" among the
primary reasons for rejection across 1,000 rejections.

**Probe:** grep across all 98 engines for `research gap`, `research question`,
`rationale`, `so what` → hits only in `reporting_guidelines.py` (an EQUATOR
item, not a general rationale check), `domain_checklists2.py`. `design_claims`
and `redundancy` contain the word "gap" only in unrelated contexts.

**Probe:** a manuscript whose introduction states only background ("Retinal
imaging is widely used. Many datasets exist. Prior work is abundant.") with no
gap, no question, no hypothesis → **no engine fired**. `novelty.py` only checks
that a *contribution* lexicon exists somewhere; it never asks whether the
introduction establishes **why the work was needed**.

### 2.5 ✅ Verified as already strong (do not rebuild)

Confirmed present and working — these are the parts where we are ahead of the
free tier:

- **Statistics:** `statcheck` (deterministic p-value recomputation),
  `grim_engine`, `sprite_engine`, `tiva_engine`, `pcurve_engine`,
  `carlisle_engine`, `asa_pvalues`, `power_adequacy`, `corrections` (GG /
  Bonferroni / FDR). *Ahead of most free tools.*
- **EQUATOR:** 40+ families in `reporting_guidelines`, plus
  `domain_checklists`/`domain_checklists2`.
- **Ethics/IRB/consent:** `trial_ethics` fires HIGH on human-study-without-IRB
  and without consent (probe-verified).
- **AI disclosure:** `policy`, `ai_disclosure_deep` fire on a missing
  disclosure (probe-verified).
- **Retraction screening:** `retracted_refs` with 70k+ RWDB + OpenAlex online.
- **Venue integrity:** `venue_hijack` (post-fix: 412 hijacked journals,
  CRITICAL fires), `predatory_journal`.
- **Image integrity:** `image_forensics`, `image_deep_forensics` (ELA +
  copy-move), `image_manipulation`.
- **India-specific:** `ugc_14word` computes the actual UGC 2018 statutory
  Level 0–3 bands; `ugc_plagiarism` reads `plagiarism_threshold`.

### 2.6 ⚠️ Partially covered — worth an honest note, not a new engine

| Reality | Status |
|---|---|
| Overall similarity vs 15% norm (international venues) | Only UGC computes a statutory %. Every other preset ships `plagiarism_threshold: None` and nothing warns. **We cannot compute a real similarity % without a corpus** — say so, rather than fake a number. |
| AI-generated text detection | Correctly flag-only; science doesn't support a verdict. Keep. |
| Image manipulation | Heuristic-grade (dhash/ELA); Proofig/ImageTwin are rotation/scale-invariant. Documented in IMPROVEMENT_ROADMAP §1. |

---

## PART 3 — The build plan (this wave)

Ranked by *(real-world frequency) × (offline feasibility) × (non-duplication)*.

| # | Engine | Closes | Evidence |
|---|---|---|---|
| **1** | `ref_forensics` | **GAP 1** — future/impossible reference metadata, offline, default path | 1-in-277 papers; 7.54% of retractions |
| **2** | `scope_match` fix + `topic_coherence` | **GAP 2 + 3** — default-venue blind spot, and title/abstract/keywords vs body | #1 desk-reject reason |
| **3** | `rationale` | **GAP 4** — research gap / question / hypothesis / significance stated in the introduction | top-3 post-review reason |

### Design rules carried over from the codebase (CONTRIBUTING.md, MEMORY.md)

- `run(doc, ctx) -> List[Finding]`; register in `checks/__init__.py` is
  **automatic** (pkgutil discovery + `_registry_self_check` — just add the file).
- Finding positional order: `(category, severity, title, detail, evidence,
  action, confidence, location="", source="")`. Never transpose action/confidence.
- **flag-not-verdict**: evidence + confidence + action on every finding.
- Severity caps: heuristics stay LOW/MEDIUM unless the evidence is a hard
  arithmetic contradiction (a citation dated 2031 *is* one → HIGH).
- No new dependencies. Offline-first; never accuse on network failure.
- One owner per angle — no cross-engine duplicates (the repo has fought this
  battle twice).

### What we deliberately will NOT build

- A numeric "similarity %" without a corpus — it would be a fabricated number.
- An AI-authorship verdict — the evidence base doesn't support it.
- Anything requiring torch/heavy CV — breaks zero-dependency.
