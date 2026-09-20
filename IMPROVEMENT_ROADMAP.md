# PaperEngine — Improvement Roadmap (Deep-Dive, 2026-09-20)

Sources: repo audit at v1.13.0 (96 engines / 336 tests) + live web research on the commercial
and open-source landscape (Turnitin/iThenticate, Paperpal, Proofig, ImageTwin, Penelope,
Writefull, Trinka, Scribbr, Scite, PubPeer, STM Integrity Hub, Crossref/Retraction Watch,
OpenAlex, DOAJ, ORCID, ROR, ORI forensic tools, GitHub forensics ecosystem).

---

## 1. Where we stand vs the market

| Capability | Commercial tools | PaperEngine today | Verdict |
|---|---|---|---|
| Text similarity vs published corpus | iThenticate $125–300/paper; Turnitin institutional | TF-IDF + sentence Jaccard vs **user's own corpus** only | **Biggest feature gap** — everything else below is polish by comparison |
| AI-generated text detection | Turnitin, Paperpal, GPTZero (paid, closed) | Phrase/artifact heuristics (tortured phrases, LLM artifacts) | Gap, partially covered |
| Image integrity | Proofig / ImageTwin — rotation/scale/flip-invariant duplication, splice localization, AI-generated figure detection | dhash cross-panel + ELA + in-panel clone (rotation/scale NOT invariant) | Behind, but screening-grade useful |
| Statistical verification | statcheck (free, R), publishers' internal GRIM/SPRITE | statcheck + GRIM/GRIMMER + SPRITE + TIVA + p-curve + Carlisle | **Ahead of most free tools** |
| Journal-fit / submission preflight | Penelope.ai ($9.50/report) | scope_match, EQUATOR 40+ families, venue standards | At parity for a general audience |
| Reference reality | Crossref/OpenAlex/PubMed APIs (paid tiers elsewhere) | crossref/openalex/pubmed verify + retracted refs | At parity |
| Retraction data | STM Integrity Hub (paid) | Retraction Watch via Crossref + local `rwdb` | At parity |
| Post-publication critique | PubPeer links in Zotero/WoS | none | **Free, easy win** (§3.2) |
| Author-identity fraud | paid | ORCID checksum, author-network, paper-mill heuristics | Good |
| Language polish | Writefull, Trinka, Paperpal (paid) | grammar_tool (optional local LanguageTool), language engine | Behind, but out of scope for an integrity screener |

**Positioning sentence:** we are the only fully-offline, zero-dependency, 96-engine
pre-submission screener — nobody in the free tier matches breadth; the paid tier's moat is
*external corpora* (published-text plagiarism, publisher image databases). That gap needs a
crawler/index, not new engines.

## 2. Internal audit — mistakes and weak spots found this pass

1. **Crossref User-Agent is still `papercheck/0.1`** (`crossref_verify.py:13`) — Crossref
   explicitly asks for real contact UA/mailto; we should send `paperengine/{version}` with the
   user's `--mailto`. Also the polite-pool `mailto` param exists on crossref_verify but not on
   every online call.
2. **Uncommitted working-tree churn is accumulating again** (8 modified tracked files +
   6 untracked) — the exact failure mode from the last audit. Needs triage into commits or
   restore before the next release.
3. **Engine pipeline is single-pass per engine, sequential by design** — v1.13 added a parallel
   pipeline test, but the per-engine cache (`ctx.online_cache`) is dict-mutation-shared across
   threads if engines mutate it; verify thread-safety or document engines as read-only over it.
4. **No API-key for OpenAlex is validated/rotated** — key is threaded through
   (`--openalex-key`, env var), but there is no rate-limit backoff; a big batch run could 429.
5. **webui server_version string still says `PaperEngine/1.4`** (cosmetic drift, 9 versions old).
6. **ingestion.py extracts zero media** for engines to consume from PDFs (dhash path works for
   DOCX zip media and `--images` dir only) — PDF figures (scanned gels!) are the most common
   real-world image-integrity source and we skip them.
7. **GUI has no engine-list / version endpoint**; the fixplan format exists but the GUI doesn't
   offer it.
8. **`scripts/refresh_data.py` (new, untracked) writes into `papercheck/data/`** — must be
   reviewed before anyone wires it into maintenance.yml, or a bad run corrupts shipped vectors.

## 3. Resource integration plan (free first, opt-in online)

### 3.1 Datasets worth bundling (offline, all freely licensed)
| Dataset | Use | Where we plug it in |
|---|---|---|
| Retraction Watch (Crossref, CC0-ish) | already used; **add periodic `--sync-all` refresh + stale-date finding** | `rwdb.py` |
| DOAJ journal list | predatory-journal scoring vs known-good list | `predatory_journal.py` |
| ICLAC cell-line register (integrate already) | keep current, add misidentification tag per reference | `iclac_celllines.py` |
| RRID portal data | keep | `rrid_validate.py` |
| EQUATOR guideline checklist data | keep (40+ families) | `reporting_guidelines.py` |
| Think.Check.Submit criteria | already in venue scoring | `venues.py` |
| **Predatory Reports / tortured-phrase public collections** | broaden phrase list | `tortured_phrases.py` |

### 3.2 Free APIs to integrate (all opt-in behind `--online`, cached)
1. **PubPeer** — for every resolved reference DOI, fetch PubPeer comment count; a reference
   with an active PubPeer thread is a strong risk signal (free JSON API).
2. **Crossref** — already integrated; fix UA, add `mailto` polite pool everywhere.
3. **OpenAlex** — already integrated; **must add `api_key` support surface in CLI docs** +
   backoff, since Feb-2026 key requirement.
4. **DOAJ API** — venue legitimacy signal (is the journal actually indexed?).
5. **ORCID public API** — already have checksum; add name-disambiguation (author claims this
   ORCID? field matches?).
6. **ROR** — affiliation verification for author networks.
7. **Europe PMC / Semantic Scholar** — citation-context checks (does cited paper actually
   support claim?) — the "claim↔evidence tracing" gap, online-mode only.

### 3.3 Optional heavyweights (document, don't bundle)
- **Ollama** local LLM explainer — done (v1.13). Remaining: pull model docs in USER_GUIDE.
- **LanguageTool** self-host — already wired.
- **GROBID** (PDF→structured references) — would substantially improve reference extraction
  from PDFs; document a Docker one-liner and detect the endpoint.
- **Tesseract OCR** — read text inside figures (axis labels, blot labels) → statistical
  inconsistency between figure and text.
- **sentence-transformers** (opt-in, Apache-2.0) — the moment external-corpus similarity ships,
  swap TF-IDF for MiniLM embeddings behind the same `run()` interface.

## 4. Phased implementation plan

### Wave A — hardening + hygiene (small, high value, do first)
- A1 Fix Crossref UA + mailto polite-pool on all online engines; document OpenAlex key + rate-limit backoff.
- A2 Triage the 8 modified / 6 untracked files into clean commits (or restore) — release hygiene.
- A3 Registry self-check: engine files on disk == registered engines, surfaced in `--version` output (kills the recurring count-drift bug class).
- A4 webui server_version bump + fixplan format surfaced in GUI.

### Wave B — capability: external-corpus similarity (the headline gap)
- B1 **Corpus builder**: `python -m papercheck --sync-corpus <dir>` ingests open-access PDFs/txt (OpenAlex `open_access.oa_url`, DOAJ full-text, arXiv, PubMed Central OA set) into a local TF-IDF index (`papercheck/data/corpus_index.npz`-style, stdlib-serializable).
- B2 Semantic similarity engine consumes that index in addition to `--corpus`.
- B3 Honest limitations section in docs (lexical, not paraphrase-grade; embeddings optional upgrade path).

### Wave C — capability: image integrity, PDF figures
- C1 PDF media extraction in `ingestion.py` (pypdf image extraction — dependency already present) feeding the same `(name, bytes)` list the DOCX path produces.
- C2 Rotation/scale-invariant duplication: add 4 rotation probes (0/90/180/270) + downscaled dhash variant to `image_forensics.py` (cheap, big precision win).
- C3 Optional OCR hook (Tesseract if installed) for figure-text consistency.

### Wave D — capability: author/venue network trust
- D1 PubPeer reference screening (online).
- D2 ORCID/ROR affiliation verification (online).
- D3 DOAJ venue indexing check (online).

### Wave E — UX polish (GUI)
- E1 Batch mode in web UI (multi-file upload → ranked CSV).
- E2 Fix-plan view in GUI (`--format fixplan` parity).
- E3 Per-engine toggle checkboxes (run subset for speed).

## 5. What we deliberately will NOT do
- Bundle paid-API plagiarism (Turnitin/iThenticate) — not licensable.
- Ship an AI-writing "detector percentage" — the science doesn't support the number; our
  ai_risk engine stays flag-only with documented heuristics.
- Add heavyweight CV/deep-learning deps (torch) — breaks the zero-dependency promise;
  opt-in extras only.

## 6. Priority ranking (impact × effort)
1. A2 tree hygiene (blocks every release)
2. B1/B2 external corpus similarity (closes the single biggest market gap)
3. C1 PDF figure extraction (closes the most common real image-integrity blind spot)
4. A1/A3 online-engine hardening + registry self-check
5. D1 PubPeer screening (free, high signal)
6. C2 rotation-invariant image duplication
7. E1–E3 GUI parity
