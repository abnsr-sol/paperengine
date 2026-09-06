# Contributing to PaperEngine

Thanks for helping improve pre-submission checks for researchers. This project
values **honest, evidence-linked signals** over impressive-looking numbers.

## Ground rules

1. **Every finding must carry evidence, confidence, and an action.** A check
   that says "this looks wrong" without showing *why* is not acceptable.
2. **No verdicts on intent.** Similarity ≠ plagiarism; AI-risk ≠ proof of AI
   authorship. Report signals, leave judgment to humans — this is how editors
   are trained to use iThenticate/Turnitin, and it keeps the tool defensible.
3. **Dual standard by default.** New checks must consider both international
   venues (IEEE/Elsevier/ACM/…) and Indian national rules (UGC/AICTE/NAAC).
   If a rule differs by standard, branch on `ctx.rules["standard"]`.
4. **Offline first.** Engines must run with zero network access. Anything that
   needs a service goes behind a probe-and-skip pattern (see
   `checks/grammar_tool.py` for the reference implementation).
5. **One engine per rejection angle.** Add `checks/my_angle.py` exposing
   `run(doc, ctx) -> list[Finding]`, register it in `checks/__init__.py`,
   then add tests with both a paper that triggers the finding and one that
   must not.

## Setting up

```bash
git clone https://github.com/abnsr-sol/paperengine
cd paperengine
pip install -e .[all]        # PDF + image extras
python -m unittest discover -s tests
```

Python 3.10+ — CI enforces 3.10 through 3.13, so avoid 3.12+-only syntax
(same-quote f-strings, etc.).

## Adding a venue preset

Venue rules live in `papercheck/venues.py`. Copy the closest existing preset,
change the limits, set `"standard"` to `"international"` or `"national"`, and
add a test asserting the new limits actually change the findings.

## Pull requests

- Keep PRs focused; one engine (or one fix) per PR is ideal.
- Run the full test suite — CI runs it on every push, and a red CI blocks merge.
- If your check adds a new finding template, document it in `README.md`
  (engine index table) and add the angle to `COVERAGE_MATRIX.md`.
- Update `CHANGELOG.md` under an "Unreleased" heading.

## Reporting bugs

Open an issue with: the engine (or CLI command), the finding text, the
expected behavior, and — ideally — a minimal synthetic manuscript that
reproduces it. Do **not** attach unpublished manuscripts you are not licensed
to share; a synthetic reducer is always enough.
