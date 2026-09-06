# PaperCheck — User Guide

A 5-minute guide for researchers preparing a paper for submission.

## 1. What PaperCheck is

PaperCheck reads your manuscript (DOCX, TXT, MD, TeX, PDF) and runs **63
check engines** covering every common rejection angle: formatting limits,
language, statistics, citations, ethics statements, images, AI-disclosure
rules, and more. It works for **international venues** (IEEE, Elsevier, ACM,
Springer, Nature, MDPI, Wiley, PLOS…) and **Indian national standards**
(UGC plagiarism levels, AICTE, NAAC) in the same run.

Everything runs **on your machine by default** — your paper never leaves
your laptop unless you pass `--online` (OpenAlex/Crossref lookups) or point
at your own LanguageTool server.

## 2. Install (one time)

**From PyPI (simplest):**

```bash
pip install paperengine[all]
```

**From a cloned checkout (development):**

```bash
cd paperengine
pip install -e .[all]
```

## 3. Run your first check

### Easiest way — the browser GUI

```bash
papercheck --gui
```

Your browser opens at `http://localhost:8765`. Drag your manuscript onto the
page, choose **International** or **National (India)** and the venue, and
read the report right there. Nothing is uploaded anywhere — the check runs
on your own machine.

### Terminal way (CLI)

```bash
# Indian venue (UGC-CARE rules):
papercheck mypaper.docx --standard national --venue ugc_care

# International venue:
papercheck mypaper.docx --standard international --venue ieee_conference
```

You get: a readiness score (informational!), every finding with
**evidence + confidence + a concrete fix**, and an honest-limits disclaimer.

## 4. The one command you'll use most: the fix plan

```bash
papercheck mypaper.docx --venue ugc_care --format fixplan
```

This prints a prioritized work list: CRITICAL items first, each with an
estimated effort ("5 min", "30 min", "1-2 h") and a total estimate. Work
top-down; re-run after each fix round.

## 5. Every flag worth knowing

| Flag | What it does |
|---|---|
| `--standard national\|international` | switches UGC vs IEEE/Elsevier rule sets |
| `--venue <name>` | picks the preset (`--list-venues` shows all 19) |
| `--venue-json my.json` | your venue's exact limits override presets |
| `--gui` | browser drag-and-drop mode (no terminal skills needed) | 
| `--format fixplan` | prioritized to-do list (start here!) |
| `--compare revised.docx` | before/after diff: fixed / still-open / new findings + score delta (add `--format html --out diff.html` for a shareable report) |
| `--format markdown --out r.md` | file reports for co-authors |
| `--format html --out r.html` | shareable web report |
| `--batch papers/ --format csv` | scan a whole folder → comparison CSV |
| `--online` | enables Crossref/OpenAlex lookups (network) |
| `--corpus published/` | compare against your own prior papers |

## 6. Reading the report

- **Readiness 100-70:** polish and submit.
- **70-40:** fix HIGH items before submitting.
- **Below 40:** desk-reject risk — work the fix plan from the top.
- **Confidence < 60%** findings are heuristic hints, not proof. Use judgment.
- Every finding shows *why* (evidence) and *what to do* (action).

## 7. What PaperCheck is NOT

- It is **not Turnitin**: overlap findings are signals, not plagiarism verdicts.
- It is **not an AI detector**: AI-risk is probabilistic; never accuse based on it.
- It cannot see figures' visual content (beyond hashing) or your raw data.
- Venue limits are typical values — always confirm the venue's current guide.

## 8. Optional: real grammar checking

PaperCheck uses a local LanguageTool server if one is running:

```bash
docker run -d -p 8081:8010 ErikWegner/languagetool-http
papercheck mypaper.docx --venue ieee_conference
```

No server → no grammar findings, zero noise. It's fully optional.

## 9. Quick troubleshooting

| Problem | Fix |
|---|---|
| `papercheck` command not found | `pip install paperengine[all]` (or `pip install -e .` in the project folder) |
| Score looks too harsh | It's informational; sort by severity, not score |
| Weird findings on LaTeX | Use `--file-type tex` (auto-detected usually) |
| Online checks slow | Lower `--max-online-checks` (default 10) |
