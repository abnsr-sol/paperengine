#!/usr/bin/env python3
"""Benchmark harness: measure engine behavior on a controlled synthetic corpus.

Confronts the "is this actually calibrated?" limitation with evidence. Ships
a clean control paper and a deliberately flawed paper inside the package, runs
all engines on both, and reports:

  1. per-category hit counts for each paper (the raw evidence)
  2. CRITICAL+HIGH recall — which serious flaw categories were caught
  3. false-positive audit — CRITICAL+HIGH findings on the clean control,
     each listed for review (heuristics legitimately flag things; the
     question is whether the flags are defensible)
  4. score monotonicity — the flawed paper must score strictly worse than
     the clean one
  5. AI-signal sensitivity — the stylometric engine's response to the
     template-heavy flawed intro

Exit code 0 only if monotonicity holds and clean-paper CRITICAL findings
are zero (HIGH findings on the clean paper are reported but tolerated,
since heuristics may flag defensible style calls).

Usage:
    python scripts/benchmark.py
    python scripts/benchmark.py --json            # machine-readable
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.checks import ALL_ENGINES, CheckContext  # noqa: E402
from papercheck.ingestion import load_document  # noqa: E402
from papercheck.risk import RiskReport, Severity  # noqa: E402
from papercheck.venues import describe, get_rules  # noqa: E402

BENCH_DIR = os.path.join(ROOT, "papercheck", "data", "benchmark")
CLEAN = os.path.join(BENCH_DIR, "benchmark_clean.txt")
FLAWED = os.path.join(BENCH_DIR, "benchmark_flawed.txt")


def run_all(path: str, venue: str = "elsevier") -> RiskReport:
    doc = load_document(path)
    ctx = CheckContext(venue=describe(venue), rules=get_rules(venue),
                       online=False, max_online_checks=0)
    report = RiskReport(document_name=doc.name, venue=describe(venue))
    for engine in ALL_ENGINES:
        report.extend(engine(doc, ctx))
    return report


def by_category(report: RiskReport) -> dict:
    out: dict = {}
    for f in report.findings:
        out.setdefault(f.category, []).append(f)
    return out


def serious(report: RiskReport):
    return [f for f in report.findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    clean = run_all(CLEAN)
    flawed = run_all(FLAWED)
    clean_score, flawed_score = clean.readiness_score, flawed.readiness_score

    clean_serious = serious(clean)
    flawed_cats = sorted({f.category for f in serious(flawed)})

    # AI-signal sensitivity: stylometric engines on the template-heavy flawed paper
    ai_hits = [f for f in flawed.findings
               if f.category in ("AI-risk", "LLM Artifacts")]

    result = {
        "scores": {"clean": clean_score, "flawed": flawed_score,
                   "monotonic": flawed_score < clean_score},
        "flawed_caught_categories": flawed_cats,
        "flawed_serious_findings": len(serious(flawed)),
        "clean_serious_findings": len(clean_serious),
        "clean_critical": [f.title for f in clean_serious
                           if f.severity == Severity.CRITICAL],
        "clean_high": [f.title for f in clean_serious
                       if f.severity == Severity.HIGH],
        "ai_risk_hits_on_flawed": len(ai_hits),
        "clean_categories": sorted({f.category for f in clean.findings}),
        "flawed_categories": sorted({f.category for f in flawed.findings}),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        w = 64
        print("PAPERENGINE BENCHMARK".center(w))
        print("=" * w)
        print(f"  clean  paper: score {clean_score:>3}  "
              f"({len(clean.findings)} findings, {len(clean_serious)} serious)")
        print(f"  flawed paper: score {flawed_score:>3}  "
              f"({len(flawed.findings)} findings, {len(serious(flawed))} serious)")
        mono = "PASS" if result["scores"]["monotonic"] else "FAIL"
        print(f"\n  [{mono}] score monotonicity: flawed ({flawed_score}) "
              f"< clean ({clean_score})")
        print(f"\n  serious flaw categories caught in the flawed paper:")
        for c in flawed_cats:
            print(f"    - {c}")
        print(f"\n  AI-risk engine response to template-heavy intro: "
              f"{len(ai_hits)} finding(s)")
        for f in ai_hits[:3]:
            print(f"    - {f.title}")
        print(f"\n  false-positive audit — serious findings on the CLEAN paper:")
        if not clean_serious:
            print("    none")
        for f in clean_serious:
            sev = f.severity.value.upper()
            print(f"    [{sev}] {f.title}")
            print(f"          evidence: {f.evidence[:90]}")
        print("=" * w)
        print("Note: HIGH findings on the clean paper are reported for review —")
        print("heuristics may make defensible style calls; CRITICALs must be zero.")

    ok = result["scores"]["monotonic"] and not result["clean_critical"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
