"""GRIM / GRIMMER check engine.

Deterministic arithmetic on every reported (M, SD, N) triple in the paper.
An impossible mean is an arithmetic fact, like statcheck — reviewers who run
GRIM implementations can reproduce the exact finding, so confidence is high
with a documented caveat: GRIM assumes integer-item scales (Likert sums,
counts). Averaged subscales can legitimately violate it, so the finding
labels the assumption and recommends the author state the scale granularity.

Runs only on documents with enough statistical content to matter.
"""
from __future__ import annotations

import os
import re
import sys

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from papercheck.grim import extract_grim, extract_sd_contexts, grimmer_check  # noqa: E402

_MIN_WORDS = 200  # skip abstracts/letters, same gate as statcheck


def _f(sev, title, detail, evidence, conf, action):
    return Finding("GRIM", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: CheckContext):
    text = doc.text or ""
    if len(re.findall(r"\S+", text)) < _MIN_WORDS:
        return []

    findings = []

    # --- GRIM: impossible means -----------------------------------------
    results = extract_grim(text)
    impossible = [r for r in results if not r.possible]
    if impossible:
        ev = "; ".join(
            f"M = {r.reported_mean:.{r.decimals}f} with N = {r.n}"
            for r in impossible[:4])
        detail = (
            f"{len(impossible)} reported mean(s) are mathematically impossible "
            "for integer-item data at the declared sample size: no integer sum "
            "divided by N can produce the reported value at the reported "
            "rounding (Brown & Heathers 2016 GRIM test). This is arithmetic, "
            "not opinion — but it assumes the underlying items are integers "
            "(Likert sums, counts). If subscale averages were used, say so.")
        findings.append(_f(
            Severity.HIGH, "Impossible mean (GRIM test failure)", detail,
            ev, 0.85,
            "Recompute the mean from the raw data; either the mean, N, or the "
            "reported rounding is mistyped — or disclose the non-integer "
            "granularity of the scale."))

    # --- GRIMMER: impossible SDs paired with possible means --------------
    sd_hits = []
    for mean, sd, n, context, pos in extract_sd_contexts(text):
        if grimmer_check(mean, sd, n, 2) is False:
            sd_hits.append((mean, sd, n))
    if sd_hits:
        ev = "; ".join(f"M = {m}, SD = {s}, N = {n}" for m, s, n in sd_hits[:4])
        findings.append(_f(
            Severity.MEDIUM, "Standard deviation inconsistent with N (GRIMMER)",
            f"{len(sd_hits)} reported (mean, SD) pair(s) cannot arise from "
            "integer data of the declared size: no integer sum-of-squares "
            "reproduces the reported SD at the reported rounding. Same integer-"
            "scale caveat as GRIM applies.",
            ev, 0.75,
            "Recheck the SD computation and the declared N; verify the scale "
            "is integer-valued or disclose its granularity."))
    elif results and not impossible:
        findings.append(_f(
            Severity.INFO, "All reported means pass the GRIM test",
            f"{len(results)} reported mean(s) verified as mathematically "
            "possible given the nearest declared sample size.",
            f"checked: {len(results)} mean(s)", 0.7,
            "No action needed — machine-verified granularity consistency."))

    return findings
