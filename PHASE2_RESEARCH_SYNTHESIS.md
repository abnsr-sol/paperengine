# Phase-2 research synthesis — what exists across the surface / deep / dark web, academic and commercial integrity tooling (2026)

> Purpose: capture the real landscape so the next build phase is not invented from memory. This doc is the "deep research done, now plan then build" artifact the user asked for. It is a *working note*, not a marketing page.

---

## 1. The landscape, as it actually is right now

### 1.1 Commercial / institutional platforms (the "big names" the field keeps naming)

- **iThenticate / Turnitin Similarity Check** — still the reference implementation for the "does this text exist in a huge corpus?" question. Paid, institutional, paywalled index. The honest gap is not that PaperEngine is bad at similarity — it is that no free tool can legally mirror that corpus.
- **Proofig / ImageTwin / Figcheck** — image-integrity specialists. Rotation/scale/flip-invariant duplication, splice localization, cross-paper image recycling, Western-blot/gel/microscopy-awareness. Proofig is the strongest "pre-submission image screen" brand; Figcheck has a free monthly tier. They are the reason our image line (dhash + ELA + in-panel clone) is screening-grade, not proof-grade.
- **Penelope.ai, Writefull, Paperpal Preflight, Trinka, Grammarly** — submission preflight / language polish. Penelope does structured checklists; Writefull/Trinka do language + some technical-consistency signals. These overlap with our submission/writing/language lines; the moat is mostly scale + brand, not magic.
- **Scite, Semantic Scholar, OpenAlex** — citation-context / evidence-tracing APIs. Scite's "citation statements" is the closest to the "does the cited paper actually support the claim?" gap; OpenAlex gives you metadata + abstract + concepts at scale; Semantic Scholar gives citation graph + corpus.
- **STM Integrity Hub / Papermill Alarm** — publisher-side shared screening infrastructure for paper mills, duplicate submissions, integrity signals across publishers. This is the "dark/deep web" angle made real and legit: pooled signals across submission systems. Not user-accessible; a benchmark and signature source, not a dependency we can call.
- **AI detectors (GPTZero, Copyleaks, Turnitin AI, etc.)** — probabilistic, contested, low-trust for high-stakes use. The field is moving away from "AI percentage" toward disclosure + artifact heuristics, which is exactly how `ai_risk` is designed.
- **Wiley Research Exchange Screening, Elsevier, Springer Nature integrity tooling** — publisher-internal; relevant as behavior to emulate and as evidence of where rejection triage is heading (desk-reject rates climbing, integrity screening before review).

### 1.2 Free / open / researcher-facing tools that actually exist

- **statcheck** (R) — p-value recomputation from APA-style reporting; deterministic, well-known, honest about limits. We already own this space (statcheck engine).
- **GRIM / GRIMMER / SPRITE** — forensic reconstruction of impossible reported means/SDs/N. SPRITE extends beyond small-N GRIM. Peter Wilschut's work on GRO-stream / GRO-bites is the relevant newer thread on *ingested-data consistency*: the idea that if you have the dataset behind a figure/table, you can spot inconsistencies the paper text alone cannot show. That is the "out of the box" expansion line — move from text forensics to data/figure forensics.
- **Retraction Watch, Crossref, OpenAlex, Europe PMC, DOAJ, ORCID, ROR, ICLAC, RRID, ClinicalTrials.gov, PubMed/PMC** — the real free corpus we already tap in part. These are the legitimate "surface + deep" sources; the "dark web" angle in this domain is mostly myth-stuff (shadow libraries, paper-mill supply chains) that we should treat as *signals* (signatures, behaviors, email/affiliation patterns, temporal velocity) rather than as a place we crawl.
- **PubPeer** — free JSON API, post-publication critique, comment counts on DOIs. A genuinely high-signal, low-cost addition we do not yet wire (it is in the roadmap as D1).

### 1.3 Where "deep web / dark web / social media" actually matters for a paper engine

Literally scraping dark web is mostly noise and legal/safety risk for this product. What actually moves rejection risk and integrity detection:

- **Author identity / affiliation / network signals** — institutional email vs free mail, same-domain reviewers, surname overlap, co-author clusters, temporal publishing velocity, affiliation–ROR mismatch. This is "social account / metadata" territory, but it is *trust-graph* work, not "fetch every profile" work.
- **Venue legitimacy signals** — is the journal really indexed (DOAJ, Scopus, WoS lists), is it hijacked (Retraction Watch), does it solicit, does it claim impact factors it does not have. This is where the "national + international + predatory" surface really lives.
- **Post-publication reputation** — PubPeer threads, retraction status, correction history. These are the " reputation layer" the paper will carry after submission, and they change how a venue sees the same manuscript.
- **Citation context** — not just "is it cited" but "is it cited in a way that supports the claim." That is the Scite/semantic layer.

So the advanced, realistic, real-time direction is: *trust-graph + reputation + evidence-tracing + structured forensics*, not "crawl everything."

---

## 2. What a paper is actually evaluated on in 2026 — the real rejection map

The consistent signals from desk-reject data and editor/integrity writing in 2025–2026:

1. **Scope / novelty / "so what" is the dominant early filter.** Desk rejects cluster around poor fit, weak/novelty framing, and unclear contribution. That is why `scope_match`, `rationale`, `novelty`, `design_claims`, `claims`, `redundancy`, `topic_coherence` matter so much. A paper can be technically clean and still get bounced here.
2. **Integrity flags before review are rising.** Desk-reject rates have risen materially; publishers are screening earlier and sharing signals (STM Integrity Hub, papermill alarms). Reference fabrication, image integrity, coercion, reviewer fraud, salami, paper-mill signatures all land here.
3. **Statistical / methodological impossibility is a hard fail class.** statcheck decision errors, GRIM/GRIMMER impossible means/SDs, SPRITE, Carlisle baseline forensics, TIVA, p-curve — these are not "style," they are arithmetic contradictions. This is the highest-confidence layer we have, and it is already ahead of most free tools.
4. **Compliance / completeness is the boring rejection.** Missing required statements, ORCID, ethics, data availability, trial registration, EQUATOR essentials, venue formatting. Reviewers do not love these, but editors do not skip them, and missing pieces get papers returned or desk-rejected.
5. **Writing / readability / coherence is the reviewer patience tax.** Poor language, incoherent structure, overclaiming, undefined acronyms, inconsistent terminology, weak transitions — not always fatal alone, but they raise the chance that a real problem gets missed or that a reviewer disengages.
6. **Venue trust is its own axis.** Submitting to a hijacked/predatory venue or one that does not actually index the work is a career/retrieval risk independent of manuscript quality. Indian national standards (UGC/AICTE/NAAC, NIRF retraction penalty, statutory similarity) are a separate compliance universe from international ones.

So the "how it is evaluated" answer is: **fit + integrity + statistics + compliance + readability + venue trust**, in roughly that priority order at the desk stage.

---

## 3. What PaperEngine already covers well

- **Arithmetically hard checks** — statcheck, GRIM/GRIMMER, SPRITE, Carlisle baseline balance, consistency/conflicting numbers, ref forensics, fabrication/Benford signals. This is the strongest differentiator against free tools.
- **Venue + standard breadth** — 24 presets today (17 international + 6 national Indian + extras in code), dual standard path, UGC statutory similarity, EQUATOR all 15, funder compliance across US/EU/UK/India.
- **Offline-first integrity screen** — forensic text signals, image screening, predatory/hijack checks, retraction seed list, tortured phrases, LLM artifact heuristics, all runnable offline with optional online enrichment.
- **Report discipline** — evidence + confidence + action on every finding, readiness score as informational aggregate, limitations stated openly.
- **UX surface** — CLI + local web GUI, formats console/markdown/html/fixplan/csv/similarity/json, compare mode, batch mode.

The honest gap table is also already written (IMPROVEMENT_ROADMAP.md §1). The single biggest real gap is **external-corpus similarity** — the iThenticate question — which we cannot fully close without a corpus, but we *can* close partially and honestly with Europe PMC + OpenAlex + user corpus + optional embeddings.

---

## 4. Where we are still weak / missing — the exact gaps

1. **External-corpus similarity is partial, not complete.** `external_overlap` uses Europe PMC full text + OpenAlex abstracts with the rare-phrase heuristic, which is the right *honest* design, but it is not the paywalled index. Real-time-ish, online-only, rate-limited.
2. **PDF figure extraction is missing.** The most common real image-integrity source — scanned gels, microscopy, plots inside PDFs — is not fed to the image engines for PDFs. DOCX media works; PDF media does not yet.
3. **Image duplication is not rotation/scale/flip invariant.** dhash + ELA + clone is useful screening, but a rotated/scaled copy can evade it. That is a concrete, cheap precision win (probe 0/90/180/270 + downscaled hash variant).
4. **Reputation layer is thin.** No PubPeer comment-count screening, no ORCID/ROR name/disambiguation + affiliation verification, no DOAJ indexing confirmation as a first-class online signal. These are free/online and high-signal.
5. **Ingested-data forensics (the GRO-stream / SPRITE-next frontier) is not really here.** We check *reported* statistics well; we do not yet take the actual dataset/figure and test whether the figure is consistent with the data the paper claims to have. That is the deeper, more "real" forensics line: table/figure data extraction + consistency + reconstruction plausibility.
6. **Claim↔evidence tracing is only a hook.** We flag overclaiming and missing support, but we do not yet trace a specific claim to whether the cited literature supports it. That is the Scite-style semantic gap; honest design: online-only, evidence-tracing signals, never a truth verdict.
7. **Author/trust-graph depth is shallow.** Author identity, email-hospital rule, paper-mill heuristics, reviewer-fraud logic exist, but the richer graph (velocity, cross-submission clustering, institutional affiliation verification) is partial.
8. **Online hygiene is still imperfect.** OpenAlex now requires/encourages a free key with meaningful rate limits, and the polite-pool / UA story still needs tightening across calls; a batch run can still 429. This matters for "real-time working" credibility.
9. **Coverage is broad but not uniformly deep.** Some engines are thin because they are heuristics; some are strong because they are arithmetic. The weakest spots are exactly the ones that require external corpus, semantic reasoning, or heavy CV — which is the honest truth, not a surprise.

---

## 5. What "advanced / real-time / national + international" should mean here

Advanced does **not** mean "claim everything." It means:

- **Real-time-ish where the data actually exists in real time:** online lookups against live free APIs when a key/connection exists, with backoff and honest "coverage reduced" findings when it does not.
- **Deterministic forensics first, probabilistic signals second and labeled as such.** Arithmetic contradictions stay HIGH/CRITICAL with high confidence; heuristics stay lower and clearly labeled.
- **National + international as first-class, not an afterthought.** Indian statutory similarity and standards already are; the expansion is to keep parity as rules change and to make the "which rule set applies" path obvious in the report.
- **Reputation + trust-graph enrichment** as the modern "deep/dark/social" equivalent that actually moves the needle: PubPeer, retraction/reputation layers, venue indexing confirmation, author/affiliation verification, submission-signal patterns.
- **Data/figure forensics** as the deeper layer beyond text forensics: take the actual figure/table/data where extractable and test consistency with the claim — the GRO-stream / SPRITE-next direction.

---

## 6. Concrete next-phase build plan (research → plan → build)

### Phase 2A — tighten the live-data plumbing (small, high value, do first)

- Make every online call polite and rate-limit-aware: correct User-Agent/contact where relevant, OpenAlex key threaded clearly, backoff on 429, budget caps that never fan out, "coverage reduced" findings that are honest.
- Add a real **reputation/retrieval layer hook**: PubPeer comment-count screening on resolved DOIs (free JSON), and a venue-indexing confirmation hook (DOAJ + known indexing lists) behind `--online`.
- Add ORCID/ROR verification hook (online): checksum already exists; extend to "does this ORCID/name/affiliation line up?" as a signal, not a verdict.

### Phase 2B — close the PDF figure extraction blind spot

- Feed PDF-embedded images into the same `(name, bytes)` path the DOCX path already uses, so ELA + clone + dhash get the scanned-gel/microscopy/plots source they are missing.
- Keep it offline-capable and graceful when the PDF has no extractable images.

### Phase 2C — make image duplication rotation/scale aware

- Add rotation probes (0/90/180/270) and a downscaled/hash-variant duplicate check so a rotated or rescaled panel is not invisible. Cheap, big precision improvement, stays screening-grade.

### Phase 2D — deepen the reputation + trust graph

- PubPeer screening as a first-class online signal.
- Author-network + affiliation verification signals strengthened (ROR, institutional email vs free mail, same-domain reviewer conflict, co-author velocity where corpus/author data exists).
- Venue trust signals strengthened (DOAJ indexing confirmation, indexing/IF claim verification against official lists, hijacked-list refresh path).

### Phase 2E — start the ingested-data / figure-data forensics line (the genuinely deeper layer)

- Where a table or figure can be parsed, test whether the reported summary statistics are *consistent with the presented data*, not just whether the reported statistics are internally consistent.
- This is the GRO-stream / SPRITE-next idea: the paper text gave us reported M/SD/N; the next layer is "here is the actual figure/table/dataset the paper shows — does it match?" Start with table/figure numeric extraction + cross-check against reported summaries, and with reconstruction plausibility where the data is available.
- Keep this honest and offline-capable where possible, online-enriched where needed; never claim proof.

### Phase 2F — expand external-corpus similarity honestly, not magically

- Do not pretend to own the paywalled index. Instead: improve the rare-phrase + sustained-overlap logic, add the optional embeddings upgrade path behind the same `run()` interface, make the limitations explicit in-report, and make the user corpus + published-literature path both usable.
- This is the one place where "real-time" mainly means "live API lookups when online," not "we have everything."

### Phase 2G — keep the discipline that makes the engine credible

- Every new signal: category + severity + evidence + confidence + action.
- Arithmetical hard facts stay high-confidence; heuristics stay lower and labeled.
- Reputation/trust signals are risk signals, not accusations.
- New engines registered in the registry; registry self-check stays green; tests added for new behavior; coverage threshold respected.

---

## 7. What would actually make this "super advanced" rather than "more checks bolted on"

- **A real reputation + evidence layer**, not just text checks: PubPeer, retraction/reputation, venue indexing, author/affiliation trust signals, citation-context tracing.
- **A real data/figure forensics layer**, not just reported-statistics forensics: extract the presented data where possible and test consistency with the claim — the GRO-stream/SPRITE-next frontier.
- **Rotation/scale-invariant image integrity**, PDF figure extraction, and a credible external-corpus similarity path that is honest about being partial.
- **Live, rate-aware enrichment on the free backbone** (Crossref, OpenAlex with key, Europe PMC, DOAJ, PubPeer, ORCID, ROR, Retraction Watch) so the tool is "real-time where the world is real-time," never pretending it has what it cannot legally/honestly have.
- **National + international parity maintained as rules move**, with the rule-set path obvious in the report and freshness surfaced.

---

## 8. What I would not chase (to keep the tool credible)

- Do not claim a paywalled iThenticate-class index or an AI "percentage verdict." The field is already moving away from that; faking it would undercut the honest-positioning moat.
- Do not turn this into "scrape every social/dark/community source." The valuable signals here are trust-graph and reputation signals, not bulk scraping; bulk scraping of non-public or abusive sources is not the right engine strategy.
- Do not bolt on heavy CV/deep-learning deps and break the offline, low-dependency posture; keep those as opt-in extras.

---

## 9. Immediate next action

The next concrete step is **Phase 2A + 2B + 2C + 2D** as the buildable slice: tighten live-data hygiene, wire PubPeer + venue-indexing + ORCID/ROR hooks, extract PDF figures into the image path, and make image duplication rotation/scale-aware. That slice is the most credible "advanced + real-time + national/international" expansion from the *existing* free backbone, and it does not require pretending to have data we cannot have. Phase 2E (ingested-data/figure-data forensics) is the deeper research-to-build thread after that.

---

*Document status: research complete; plan formed; build priority set. Symbols: ✅ already live · ⚙️ hook exists · 🌐 online-only · ⚠️ needs data/API/ML · ❌ human-judgment-only*
