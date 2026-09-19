#!/usr/bin/env python3
"""Realism & robustness probe.

Runs every registered engine against a battery of hostile/minimal inputs
plus the realistic fixtures, and reports:
  - crashes (exceptions escaping engines)          -> hard defects
  - CRITICAL/HIGH findings on clean/minimal inputs -> false positives
  - per-fixture full findings for eyeballing

Usage: python scripts/realism_probe.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))

from papercheck.ingestion import Document          # noqa: E402
from papercheck.checks import ALL_ENGINES, CheckContext  # noqa: E402
from papercheck.risk import Severity               # noqa: E402

FIXTURE_DIR = os.path.join(ROOT, "realism_fixtures")

EDGE_INPUTS = {
    "empty": "",
    "one_word": "hello",
    "whitespace": "   \n\t  \n",
    "unicode_only": "αβγδ ☃ 一二三",
    "abstract_only": ("## Abstract\n\nWe show a small improvement over "
                      "baselines on a benchmark.\n"),
    "binary_garbage": ("\x00\x01\x02MZR\x93 partial \x7f text \ufffd with "
                       "embedded junk \x00\x00 end"),
    "hyper_repetition": ("We repeat the same sentence. " * 400),
    "extremely_long_word": "A" * 5000 + " end",
    "stat_flood": ("We report t(30) = 2.04, p = 0.05. We report F(2, 57) = "
                   "3.16, p = .05. We report r = .31, p = .01. " * 30),
}

# Degenerate-but-coherent inputs where serious findings are CORRECT (the
# input truly lacks a title/email/statements): findings expected, not noise.
DEGENERATE_INPUTS = {"hyper_repetition", "stat_flood"}


def make_doc(name: str, text: str, refs=None) -> Document:
    return Document(path=f"{name}.txt", name=name, file_type="txt",
                    text=text, references=refs or [])


def run_battery(label: str, doc: Document, expect_serious: bool = False) -> dict:
    ctx = CheckContext(venue=None, rules=None, online=False, max_online_checks=0)
    crashes, serious = [], []
    for eng in ALL_ENGINES:
        mod = getattr(eng, "__module__", "engine").rsplit(".", 1)[-1]
        try:
            for f in (eng(doc, ctx) or []):
                if f.severity in (Severity.CRITICAL, Severity.HIGH):
                    serious.append(f"{mod}: [{f.severity.name}] {f.title}")
        except Exception as exc:
            crashes.append(f"{mod}: {type(exc).__name__}: {exc}")
    status = "OK"
    if crashes:
        status = "CRASHES"
    elif serious and not expect_serious:
        status = "FALSE-POSITIVES"
    print(f"[{status}] {label}")
    for c in crashes:
        print(f"    CRASH  {c}")
    for s in serious[:8]:
        print(f"    SERIOUS {s}")
    if len(serious) > 8:
        print(f"    ... and {len(serious) - 8} more serious findings")
    return {"label": label, "crashes": crashes, "serious": serious}


def main() -> int:
    total_crashes, total_fps = 0, 0
    print("=" * 64)
    print("PART 1 — hostile / minimal edge inputs")
    print("=" * 64)
    for name, text in EDGE_INPUTS.items():
        degenerate = name in DEGENERATE_INPUTS
        r = run_battery(name, make_doc(name, text), expect_serious=degenerate)
        total_crashes += len(r["crashes"])
        if not degenerate:
            total_fps += len(r["serious"])

    print("=" * 64)
    print("PART 2 — realistic fixtures (expect serious findings = OK)")
    print("=" * 64)
    from papercheck.ingestion import load_document
    for fname in sorted(os.listdir(FIXTURE_DIR)):
        path = os.path.join(FIXTURE_DIR, fname)
        doc = load_document(path)
        r = run_battery(fname, doc, expect_serious=True)
        total_crashes += len(r["crashes"])

    print("=" * 64)
    print(f"TOTAL crashes: {total_crashes}   unexpected serious on "
          f"minimal inputs: {total_fps}")
    return 1 if total_crashes else 0


if __name__ == "__main__":
    sys.exit(main())
