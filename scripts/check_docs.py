#!/usr/bin/env python3
"""Doc-consistency gate: fail if the docs advertise counts that are not real.

The engine and test counts in README.md / pyproject.toml / COVERAGE_MATRIX.md
are hand-maintained and have repeatedly gone stale (65 -> 85 -> 86 -> 89 -> 94
-> 96 -> 97 engines; 150+ -> 292 -> 301 -> 315 -> 319 tests). Rather than keep
chasing them by hand, this script derives the truth from the registry and the
test loader and asserts every advertised number matches.

Usage:
    python scripts/check_docs.py          # human-readable, exit 1 on mismatch
    python scripts/check_docs.py --json   # machine-readable
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.checks import ALL_ENGINES  # noqa: E402


def real_counts() -> tuple[int, int]:
    engines = len(ALL_ENGINES)
    suite = unittest.TestLoader().discover(os.path.join(ROOT, "tests"))
    return engines, suite.countTestCases()


# (file, regex, which-count, human label)
# `which` is "engines" or "tests"; group 1 is the number to compare.
RULES = [
    ("README.md", r"badge/tests-(\d+)%20passing", "tests", "README test badge"),
    ("README.md", r"(\d+) engines incl\.", "engines", "README headline"),
    ("README.md", r"\*\*(\d+) specialized engines\*\*", "engines", "README intro"),
    ("README.md", r"checked by the same (\d+) engines", "engines", "README GUI section"),
    ("README.md", r"checks/\s+(\d+) engines", "engines", "README tree"),
    ("README.md", r"# (\d+) tests,", "tests", "README dev section"),
    ("pyproject.toml", r"\((\d+) check engines", "engines", "pyproject description"),
    ("COVERAGE_MATRIX.md", r"(\d+) engines live", "engines", "coverage matrix header"),
    ("COVERAGE_MATRIX.md", r"(\d+)/(\d+) tests green", "tests", "coverage matrix tests"),
]


def check() -> list[dict]:
    engines, tests = real_counts()
    truth = {"engines": engines, "tests": tests}
    results = []
    for fname, pattern, which, label in RULES:
        path = os.path.join(ROOT, fname)
        if not os.path.exists(path):
            results.append({"file": fname, "label": label, "ok": False,
                            "found": None, "expected": truth[which],
                            "note": "file missing"})
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        # COVERAGE_MATRIX prints tests twice (n/n); compare the first number.
        found = None
        for m in re.finditer(pattern, text):
            found = int(m.group(1))
            break
        ok = found == truth[which]
        results.append({"file": fname, "label": label, "ok": ok,
                        "found": found, "expected": truth[which], "note": ""})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = check()
    bad = [r for r in results if not r["ok"]]

    if args.json:
        print(json.dumps({"results": results, "failures": len(bad)}, indent=2))
    else:
        print("DOC CONSISTENCY CHECK")
        print("=" * 60)
        for r in results:
            mark = "ok  " if r["ok"] else "FAIL"
            found = "missing" if r["found"] is None else r["found"]
            line = f"  [{mark}] {r['label']:26} {str(found):>6} (expected {r['expected']})"
            print(line + (f"  {r['note']}" if r["note"] else ""))
        print("=" * 60)
        if bad:
            print(f"{len(bad)} stale count(s). Update the docs (or this script's rules).")
        else:
            print("All advertised counts match the registry and test loader.")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
