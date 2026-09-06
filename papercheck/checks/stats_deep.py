"""Deep statistics engine: survival analysis, Bayesian reporting, QRP/p-hacking indicators, error bars, normality."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_SURVIVAL = r'Kaplan-?Meier|survival\s+(?:analysis|curve|rate)|time-to-event|hazard\s+ratio|Cox\s+(?:proportional|regression)|log-?rank|censored'
_BAYES = r'Bayesian|Bayes\s+factor|posterior|MCMC|Stan|JAGS|BUGS|credible\s+interval'
_PARAM = r'\bt[- ]test\b|ANOVA|Pearson|linear\s+regression|parametric'
_STATS_WORDS = r'p\s*[<>=]\s*0?\.\d+|statistically\s+significant|effect\s+size|\bCI\b|standard\s+(?:deviation|error)|Â±|confidence\s+interval'


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Statistics", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body:
        return []
    out = []

    # --- Survival analysis -------------------------------------------------
    if re.search(_SURVIVAL, body, re.IGNORECASE):
        if not re.search(r'censored|censoring|withdrawn|lost\s+to\s+follow', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "Survival analysis without censoring description",
                          "Time-to-event analyses must describe the censoring mechanism (loss to follow-up, study end).",
                          "Survival keywords found, no censoring terms", 0.85,
                          "Describe how censoring was handled (right-censoring, withdrawals)"))
        if re.search(r'Kaplan-?Meier|survival\s+curve', body, re.IGNORECASE) and not re.search(r'log-?rank|Mantel-?Cox', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Kaplan-Meier curves without log-rank comparison",
                          "Comparing survival curves requires a log-rank test (or its variant).",
                          "KM keywords found, no log-rank", 0.75,
                          "Add a log-rank test when comparing two or more survival curves"))
        if re.search(r'hazard\s+ratio', body, re.IGNORECASE) and not re.search(r'95%\s*(?:CI|confidence|confidence\s+interval)|CI\s*[:\[]', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Hazard ratios without confidence intervals",
                          "Cox model results should report hazard ratios with 95% CIs.",
                          "HR keywords found, no CI", 0.75,
                          "Report HR with 95% CI and p-value"))

    # --- Bayesian reporting ------------------------------------------------
    if re.search(_BAYES, body, re.IGNORECASE):
        if not re.search(r'prior(?:s)?\b', body, re.IGNORECASE):
            out.append(_f(Severity.HIGH, "Bayesian analysis without prior justification",
                          "Bayesian reporting guidelines require stating and justifying every prior distribution.",
                          "Bayesian keywords found, no 'prior' mention", 0.85,
                          "State each prior (distribution + parameters) and why it was chosen"))
        if re.search(r'credible', body, re.IGNORECASE) and not re.search(r'confidence\s+interval|frequentist', body, re.IGNORECASE):
            pass
        if re.search(r'confidence\s+interval', body, re.IGNORECASE) and re.search(r'Bayesian|posterior', body, re.IGNORECASE):
            if not re.search(r'credible', body, re.IGNORECASE):
                out.append(_f(Severity.MEDIUM, "Bayesian results reported as confidence intervals",
                              "Bayesian analyses produce credible intervals (CrI), not confidence intervals (CI) - using 'CI' is a reporting error.",
                              "Bayesian + 'confidence interval' but no 'credible'", 0.80,
                              "Report credible intervals and never call them confidence intervals"))
        if not re.search(r'sensitivity\s+analysis|robustness|alternative\s+prior', body, re.IGNORECASE):
            out.append(_f(Severity.LOW, "No prior-sensitivity analysis reported",
                          "Bayesian reporting guidelines recommend checking that conclusions hold across reasonable priors.",
                          "Bayesian keywords found, no sensitivity analysis", 0.65,
                          "Add a sensitivity analysis across prior choices"))

    # --- QRP / p-hacking indicators ----------------------------------------
    pvals = [float(m) for m in re.findall(r'p\s*=\s*(0?\.\d{2,3})', body, re.IGNORECASE)]
    pvals += [float(m) for m in re.findall(r'p\s*<\s*(0?\.\d{2,3})', body, re.IGNORECASE)]
    just_below = [pv for pv in pvals if 0.04 <= pv < 0.05]
    if len(just_below) >= 3 and len(pvals) >= 5:
        out.append(_f(Severity.MEDIUM, "Suspicious p-value clustering near 0.05",
                      str(len(just_below)) + " of " + str(len(pvals)) + " reported p-values sit in [0.04, 0.05) - a p-hacking signature when excessive.",
                      "p-values in [0.04,0.05): " + str(just_below[:6]), 0.60,
                      "Report all analyses run (including non-significant ones) and pre-register hypotheses"))
    if re.search(r'p\s*=\s*0?\.0{2,}\s*\d', body, re.IGNORECASE) and not re.search(r'<', body[:4000]):
        pass

    # --- Parametric tests without normality check --------------------------
    if re.search(_PARAM, body, re.IGNORECASE) and re.search(_STATS_WORDS, body, re.IGNORECASE):
        if not re.search(r'normality|Shapiro-?Wilk|Kolmogorov-?Smirnov|normal\s+distribution|log-?transform', body, re.IGNORECASE):
            out.append(_f(Severity.MEDIUM, "Parametric tests without normality check",
                          "t-tests/ANOVA/regression assume normality; reviewers expect a Shapiro-Wilk/KS test or a justification.",
                          "Parametric keywords found, no normality test", 0.70,
                          "Test and report normality (Shapiro-Wilk) or justify robustness (large n, CLT)"))

    # --- Error bars / variability reporting --------------------------------
    if re.search(r'error\s+bars?', body, re.IGNORECASE) and not re.search(r'SD|SE|standard\s+(?:deviation|error)|95%\s*CI|confidence\s+interval', body, re.IGNORECASE):
        out.append(_f(Severity.LOW, "Error bars without definition",
                      "Figure error bars must state whether they show SD, SE, or 95% CI.",
                      "Error-bar keywords found, no SD/SE/CI definition", 0.70,
                      "State what error bars represent in each figure caption"))

    # --- Statistical software version ---------------------------------------
    if re.search(_STATS_WORDS, body, re.IGNORECASE) and not re.search(r'\b(R|SPSS|SAS|Stata|GraphPad|Matlab|SciPy|scikit-learn)\b\s*(?:version|v?\d)', body, re.IGNORECASE):
        if not re.search(r'analy(?:zed|sis)|statistical\s+(?:analysis|software)|computed\s+using', body, re.IGNORECASE):
            out.append(_f(Severity.LOW, "Statistical software not reported",
                          "Most journals want the software + version used for analysis.",
                          "Stats present, no software/version", 0.60,
                          "State the software and version (e.g., R 4.3.2, SPSS 29)"))

    return out
