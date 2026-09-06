#!/usr/bin/env python3
"""Weekly maintenance: verify the suite, refresh the retraction cache, summarize.

Runs anywhere (CI or a maintainer's laptop):
    python scripts/maintenance.py            # tests + RWDB refresh
    python scripts/maintenance.py --skip-tests
    python scripts/maintenance.py --no-network

Exit code 0 only if the test suite passed (the RWDB refresh failing offline is
a warning, not an error — the built-in seed list keeps screening active).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_tests() -> bool:
    print("== Running the offline test suite ==")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
    )
    return proc.returncode == 0


def refresh_rwdb() -> bool:
    print("\n== Refreshing the Retraction Watch DB cache ==")
    proc = subprocess.run(
        [sys.executable, "-m", "papercheck", "--update-rwdb"],
        cwd=ROOT,
    )
    return proc.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-tests", action="store_true", help="only refresh caches")
    ap.add_argument("--no-network", action="store_true", help="skip the RWDB download")
    args = ap.parse_args()

    tests_ok = True
    if not args.skip_tests:
        tests_ok = run_tests()

    rwdb_ok = True
    if not args.no_network:
        try:
            rwdb_ok = refresh_rwdb()
        except Exception as exc:  # noqa: BLE001 — offline machines must not crash the job
            print(f"RWDB refresh failed: {exc}")
            rwdb_ok = False

    print("\n== Maintenance summary ==")
    print(f"  tests passed:  {tests_ok}")
    print(f"  rwdb refreshed: {rwdb_ok}")
    return 0 if tests_ok else 1


if __name__ == "__main__":
    sys.exit(main())
