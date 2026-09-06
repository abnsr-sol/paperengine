"""ML-fairness engine: baseline parity and metric masking on imbalanced data.

Catches two of the most common ML-paper reviewer objections deterministically:

1. **Strawman baseline tell**: heavy hyperparameter vocabulary for the
   proposed model (grid search, tuning, sweeps) with zero tuning language
   for baselines — plus no "fair comparison" statement. Reviewers read
   this as the proposed model being tuned against out-of-the-box baselines.
2. **Metric masking on imbalanced classes**: accuracy reported (>=90%) on
   data described as imbalanced (class imbalance, minority class, ratio
   language) without any imbalance-robust metric (balanced accuracy,
   macro F1, MCC, PR-AUC, AUC-PR, Cohen's kappa, G-mean).

Both checks are phrase-level and conservative: they only fire when the
trigger vocabulary is explicit in the paper.
"""
from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity

_TUNING_SELF = re.compile(
    r"(?:grid\s*search|hyperparameter\s*(?:search|tuning|optimization)|"
    r"(?:we\s+)?tun(?:e|ed|ing)\s+(?:the|our)|random\s*search|bayesian\s*optimization|"
    r"sweep(?:s|ed)?\s+over|learning[\s-]*rate\s*(?:search|sweep))", re.IGNORECASE)
_TUNING_BASELINE = re.compile(
    r"(?:baseline[s]?\s+(?:are|were|is)\s+tuned|tuned\s+baselines?|"
    r"identical\s+(?:tuning|hyperparameter|budget)|fair\s+comparison|"
    r"same\s+(?:tuning|search)\s+budget|baselines?\s+under\s+the\s+same)", re.IGNORECASE)
_ML_SIGNAL = re.compile(
    r"\b(?:accurac(?:y|ies)|f1[- ]?scores?|precisions?|recalls?|neurals?|"
    r"transformers?|classifiers?|training\s+sets?|benchmarks?|datasets?|"
    r"convolutional|neural\s+network)", re.IGNORECASE)

_IMBALANCE = re.compile(
    r"(?:class[\s-]*imbalance|imbalanc(?:ed?|es)|minority\s+class|"
    r"skew(?:ed)?\s+(?:class|distribution)|\d+\s*[:%]\s*\d+\s*(?:ratio|split)|"
    r"rare\s+class|long[- ]tailed\s+distribution)", re.IGNORECASE)
_ACC = re.compile(r"(\d{2}(?:\.\d+)?)\s*%\s*(?:accuracy|acc\b)|(?:accuracy|acc\b)\s*(?:of|=)\s*(\d{2}(?:\.\d+)?)\s*%", re.IGNORECASE)
_ROBUST_METRIC = re.compile(
    r"balanced\s+accuracy|macro[\s-]*f1|macro\s*averaged|mcc|matthews|"
    r"pr[\s-]*auc|area\s+under\s+the\s+precision|cohen'?s?\s+kappa|"
    r"g[\s-]*mean|sensitivity\s+and\s+specificity|auc\b|roc[\s-]*auc", re.IGNORECASE)


def _f(sev, title, detail, evidence, conf, action):
    return Finding("ML Fairness", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if doc.word_count < 200 or not _ML_SIGNAL.search(body):
        return []

    out: List[Finding] = []

    # --- 1: strawman-baseline tell ---------------------------------------
    tuned_self = len(_TUNING_SELF.findall(body))
    tuned_both = _TUNING_BASELINE.search(body)
    if tuned_self >= 2 and not tuned_both:
        out.append(_f(
            Severity.MEDIUM,
            "Baselines appear untuned (fair-comparison risk)",
            f"The paper describes tuning its own model {tuned_self}x "
            "(grid/random search, hyperparameter optimization) but never "
            "states that baselines received the same tuning budget or that a "
            "'fair comparison' protocol was used. The Baseline Purist "
            "reviewer archetype rejects on exactly this.",
            f"{tuned_self} self-tuning mentions; no baseline-tuning/fair-"
            "comparison statement", 0.6,
            "Add an explicit fair-comparison statement: identical tuning "
            "budgets, seeds, and hardware for every baseline, or tune the "
            "baselines too."))
    elif tuned_self and tuned_both:
        out.append(_f(
            Severity.INFO,
            "Fair-comparison protocol present",
            "Both model tuning and baseline tuning/fair-comparison language "
            "found — the strawman-baseline objection is pre-empted.",
            "tuning + fair-comparison statements", 0.55,
            "No action needed."))

    # --- 2: metric masking on imbalanced data -----------------------------
    if _IMBALANCE.search(body):
        accs = [g1 or g2 for g1, g2 in _ACC.findall(body)]
        high_acc = [a for a in accs if float(a) >= 90.0]
        has_robust = _ROBUST_METRIC.search(body)
        if high_acc and not has_robust:
            out.append(_f(
                Severity.MEDIUM,
                "Accuracy-only reporting on imbalanced data",
                f"The paper reports high accuracy ({', '.join(high_acc[:3])}%) "
                "on data described as imbalanced, but no imbalance-robust "
                "metric (balanced accuracy, macro F1, MCC, PR-AUC, kappa) "
                "appears anywhere. A 98:2 split makes 98% accuracy trivial; "
                "reviewers treat accuracy-only reporting here as metric "
                "masking.",
                f"accuracy {high_acc[:3]}% + imbalance language, no robust "
                "metric", 0.65,
                "Report balanced accuracy, macro F1, MCC, or PR-AUC "
                "alongside accuracy; state the class distribution "
                "explicitly."))
    return out
