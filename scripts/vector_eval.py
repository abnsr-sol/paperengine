#!/usr/bin/env python3
"""Real-world vector evaluation harness (additive; the synthetic benchmark stays).

For every file in papercheck/data/vectors/ with a manifest entry, runs the
full engine set and scores the outcome against the declared expectations:

  positive vectors  — expect_any: (category, keyword) pairs; PASS when at
                      least one pair matches a finding (category equal and
                      keyword found in title+detail, case-insensitive)
  negative controls — expect_none_serious: PASS when zero CRITICAL+HIGH
                      findings fire (LOW/INFO style calls are tolerated)

Reports per-vector results, per-category precision/recall across the whole
corpus, and exits non-zero if any vector fails — so regressions in real-world
detection break CI, not just users.

Usage:
    python scripts/vector_eval.py
    python scripts/vector_eval.py --json
    python scripts/vector_eval.py --verbose   # list firing engines per vector
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.checks import ALL_ENGINES, CheckContext  # noqa: E402
from papercheck.ingestion import load_document  # noqa: E402
from papercheck.risk import RiskReport, Severity  # noqa: E402
from papercheck.venues import describe, get_rules  # noqa: E402

VECTOR_DIR = os.path.join(ROOT, "papercheck", "data", "vectors")
MANIFEST = os.path.join(VECTOR_DIR, "manifest.json")


def run_all(path: str, venue: str = "elsevier") -> Tuple[RiskReport, list]:
    doc = load_document(path)
    ctx = CheckContext(venue=describe(venue), rules=get_rules(venue),
                       online=False, max_online_checks=0)
    report = RiskReport(document_name=doc.name, venue=describe(venue))
    errors = []
    for engine in ALL_ENGINES:
        name = getattr(engine, "__module__", "engine").rsplit(".", 1)[-1]
        try:
            report.extend(engine(doc, ctx) or [])
        except Exception as exc:  # engines must never abort the eval
            errors.append(f"{name}: {exc}")
    return report, errors


def matches(finding, category: str, keyword: str) -> bool:
    if finding.category != category:
        return False
    blob = (finding.title + " " + finding.detail).lower()
    return keyword.lower() in blob


def evaluate_vector(path: str, spec: dict) -> dict:
    report, errors = run_all(path)
    findings = report.findings
    serious = [f for f in findings
               if f.severity in (Severity.CRITICAL, Severity.HIGH)]

    fired_sources = sorted({f.source for f in serious if getattr(f, "source", "")})

    if spec.get("expect_none_serious"):
        passed = len(serious) == 0
        return {
            "file": os.path.basename(path),
            "label": spec.get("label", ""),
            "type": "negative",
            "passed": passed,
            "serious": [f"{f.severity.name}|{f.category}|{f.title}" for f in serious],
            "engines": fired_sources,
            "engine_errors": errors,
            "n_findings": len(findings),
        }

    hits, misses = [], []
    for cat, kw in spec.get("expect_any", []):
        hit = next((f for f in findings if matches(f, cat, kw)), None)
        (hits if hit else misses).append(
            (cat, kw, f"{hit.severity.name}|{hit.title}" if hit else None))
    passed = len(hits) > 0
    return {
        "file": os.path.basename(path),
        "label": spec.get("label", ""),
        "type": "positive",
        "passed": passed,
        "hits": [f"{c}|{k} -> {h}" for c, k, h in hits],
        "misses": [f"{c}|{k}" for c, k, h in misses],
        "_pairs": [(c, k, h) for c, k, h in hits] + [(c, k, None) for c, k, h in misses],
        "engines": fired_sources,
        "engine_errors": errors,
        "n_findings": len(findings),
    }


def per_category_metrics(results: List[dict]) -> dict:
    """Coarse per-category precision/recall across all vectors.

    Recall side: for positive vectors, did any finding in the category match
    an expectation. Precision side: for negative controls, zero serious
    findings in the category. Deliberately coarse — the point is a tripwire,
    not a leaderboard.
    """
    cats = defaultdict(lambda: {"expected_hit": 0, "got_hit": 0,
                                "clean_serious": 0})
    for r in results:
        if r["type"] == "positive":
            for c, k, h in r["_pairs"]:
                cats[c]["expected_hit"] += 1
                if h:
                    cats[c]["got_hit"] += 1
        else:
            for line in r["serious"]:
                cat = line.split("|")[1]
                cats[cat]["clean_serious"] += 1
    out = {}
    for cat, v in sorted(cats.items()):
        recall = v["got_hit"] / v["expected_hit"] if v["expected_hit"] else None
        out[cat] = {**v, "recall": round(recall, 2) if recall is not None else None}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)

    results = []
    for fname, spec in manifest.items():
        if fname.startswith("_"):
            continue
        path = os.path.join(VECTOR_DIR, fname)
        if not os.path.isfile(path):
            results.append({"file": fname, "label": spec.get("label", ""),
                            "type": "missing", "passed": False,
                            "serious": [], "engines": [], "engine_errors": [],
                            "n_findings": 0})
            continue
        results.append(evaluate_vector(path, spec))

    total = len(results)
    ok = sum(1 for r in results if r["passed"])
    failures = [r for r in results if not r["passed"]]

    if args.json:
        print(json.dumps({"passed": ok, "total": total, "results": results},
                         indent=2))
        return 0 if ok == total else 1

    print("=" * 64)
    print(f"VECTOR EVALUATION  —  {ok}/{total} vectors pass")
    print("=" * 64)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        kind = "neg" if r["type"] == "negative" else "pos"
        print(f"[{mark}] ({kind}) {r['file']}: {r['label']}")
        if r["type"] == "positive":
            for h in r.get("hits", []):
                print(f"        hit:  {h}")
            for m in r.get("misses", []):
                print(f"        miss: {m}")
        else:
            for line in r.get("serious", []):
                print(f"        serious on clean: {line}")
        if r.get("engine_errors"):
            print(f"        engine errors: {r['engine_errors']}")
        if args.verbose and r.get("engines"):
            print(f"        engines fired: {', '.join(r['engines'])}")

    print("-" * 64)
    metrics = per_category_metrics(results)
    print("Per-category recall on positive vectors / clean-serious on controls:")
    for cat, v in metrics.items():
        rec = f"{v['recall']:.0%}" if v.get("recall") is not None else "n/a"
        print(f"  {cat:24s} recall {rec:>5}  ({v['got_hit']}/{v['expected_hit']})"
              + (f"  clean-serious: {v['clean_serious']}" if v["clean_serious"] else ""))

    print("=" * 64)
    if failures:
        print(f"FAIL: {len(failures)} vector(s) failed:")
        for f in failures:
            print(f"  - {f['file']}: {f['label']}")
        return 1
    print("PASS: all evaluation vectors behave as labeled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
