"""
StormDB-style ingested-data forensics — prototype / thought experiment.

The idea (from the next-phase research synthesis):
- So far PaperEngine checks *reported* statistics for internal consistency
  (statcheck, GRIM/GRIMMER, SPRITE, Carlisle, conflicting numbers).
- The deeper layer is: if the paper *shows* a table/figure/dataset, take the
  actual rows and test whether the reported summaries are even *possible* on
  those rows — not just arithmetically allowed by N/M/SD, but achievable by
  the actual data presented.

This stub is intentionally tiny and offline, and is NOT wired into the
engine registry. It exists to make the concept concrete and to prove the
shape of the check before any real table extraction is plugged in.

Real implementation would replace `SAMPLE_ROWS` with extracted table/figure
data (from PDFs via pypdf/pdftotext table parsing, DOCX tables, or a user-
supplied supplementary CSV), and would extend this into:
- per-table checksums against reported means/SDs/counts
- figure-data consistency (e.g., bar heights vs reported group means)
- reconstruction plausibility when only summaries survive

Run:  python scripts/storm_db_mock.py
"""

from __future__ import annotations

import statistics
from typing import List, Tuple


# ---------------------------------------------------------------------------
# A tiny stand-in for "the data behind Table 1"
# In a real pass this would come from extracted table cells, not be typed by
# hand. Using a real tiny dataset keeps the arithmetic honest.
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [12, 14, 15, 15, 16, 18, 20, 22, 24, 25]


def _reported() -> List[Tuple[str, float]]:
    """Reported summaries a paper might claim for this table.

    Two are consistent with the real rows; one is not. The job of the engine
    is to flag the impossible one with the actual evidence (the real rows),
    not merely say 'N/M/SD combination looks odd'.
    """
    mu = statistics.mean(SAMPLE_ROWS)
    sd = statistics.pstdev(SAMPLE_ROWS)  # population SD, as some papers report
    return [
        ("mean", round(mu, 2)),                       # consistent
        ("SD (population)", round(sd, 2)),            # consistent
        ("mean", round(mu + 3.0, 2)),                 # INCONSISTENT — deliberate
    ]


def _achievable_values(rows: List[float], stat: str, resolution: int = 2) -> set:
    """All values a given statistic can actually take on these exact rows.

    For mean on integer-ish data this is a small finite set once you fix the
    rounding rule; here we enumerate by rounding the true mean to `resolution`
    decimals and also show the +-1-ulp neighbourhood so a misreported mean
    that is *close* but not achievable can still be caught.
    """
    if not rows:
        return set()
    true_mean = statistics.mean(rows)
    base = round(true_mean, resolution)
    out = {base}
    # neighbourhood: a reported mean rounded to `resolution` decimals must be
    # within half a unit of the true mean at that resolution, otherwise it is
    # not achievable by *this* data.
    step = 10 ** (-resolution)
    lo = round(true_mean - step * 0.5, resolution)
    hi = round(true_mean + step * 0.5, resolution)
    v = lo
    while round(v, resolution) <= hi:
        out.add(round(v, resolution))
        v += step
    return out


def _std_achievable(rows: List[float], resolution: int = 2) -> set:
    """Values the (population) SD can round to at `resolution` on these rows."""
    if len(rows) < 2:
        return set()
    true_sd = statistics.pstdev(rows)
    step = 10 ** (-resolution)
    lo = round(true_sd - step * 0.5, resolution)
    hi = round(true_sd + step * 0.5, resolution)
    out = set()
    v = lo
    while round(v, resolution) <= hi:
        out.add(round(v, resolution))
        v += step
    return out


def check_table(
    rows: List[float],
    reported: List[Tuple[str, float]],
    resolution: int = 2,
) -> List[str]:
    """Return one line per reported summary that is NOT achievable on `rows`.

    This is the core idea: not 'mean/SD/N look odd', but 'here are the actual
    values behind the table, and this reported summary cannot be produced from
    them'. Flag-not-verdict: a mismatch may be a transcription error, a
    different summary definition (sample vs population SD), or a real problem.
    """
    warnings: List[str] = []
    for stat, reported_val in reported:
        if stat.lower().startswith("mean"):
            achievable = _achievable_values(rows, "mean", resolution)
        elif stat.lower().startswith("sd") or stat.lower().startswith("std"):
            achievable = _std_achievable(rows, resolution)
        else:
            continue  # extend here for count/min/max/quartiles etc.
        if reported_val not in achievable:
            warnings.append(
                f"{stat} = {reported_val} is not achievable from the "
                f"{len(rows)} values shown (true {stat} ~ "
                f"{statistics.mean(rows) if stat.lower().startswith('mean') else statistics.pstdev(rows):.3f})."
            )
    return warnings


def main() -> None:
    print("StormDB-style ingested-data forensics — prototype stub")
    print("=" * 60)
    print(f"Table rows (stand-in for extracted data): {SAMPLE_ROWS}")
    print(f"N = {len(SAMPLE_ROWS)}")
    print()
    reported = _reported()
    print("Reported summaries the paper claims:")
    for stat, val in reported:
        print(f"  {stat} = {val}")
    print()
    warnings = check_table(SAMPLE_ROWS, reported)
    if warnings:
        print("INCONSISTENCIES between reported summary and the data shown:")
        for w in warnings:
            print(f"  - {w}")
        print()
        print("Interpretation: this is where 'ingested-data forensics' differs")
        print("from pure reported-statistics checks. The data the paper contains")
        print("is itself the witness; a summary that cannot be produced from it")
        print("is a concrete, evidence-linked flag — not a heuristic.")
    else:
        print("All reported summaries are achievable on the shown data.")
    print()
    print("Next step (real implementation): replace SAMPLE_ROWS with extracted")
    print("table/figure data and extend _achievable_* for count/min/max/quartiles/")
    print("percentiles, plus figure-height consistency checks where extractable.")


if __name__ == "__main__":
    main()
