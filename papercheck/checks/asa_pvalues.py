"""ASA p-value misuse engine — the 2016 ASA statement's six principles as checks.

The American Statistical Association's "Statement on p-values" (Wasserstein &
Lazar 2016) codified six principles; each maps to a mechanical, offline check
against the manuscript text. This engine flags *rhetoric* around p-values, not
their arithmetic (statcheck/GRIM/SPRITE own that layer):

  P1  p-values can indicate incompatibility with a model, not the probability
      the hypothesis is true            -> "p proves/confirms" language
  P2  decisions should not be based on a p threshold alone
                                        -> threshold-only claims with no exact p
  P3  scientific significance requires context, not just p
                                        -> "significant" with no effect size anywhere
  P4  p-values do not measure effect size / importance
                                        -> "highly significant" magnitude rhetoric
  P5  a large p does not imply absence of effect
                                        -> "no difference" from nonsignificance
  P6  by itself a p gives no good evidence about the model
                                        -> "tendency/marginal significance" euphemisms

Signal-only severity: these are reviewer-friction findings, never integrity
verdicts. Papers that already report effect sizes and CIs globally get a pass
on the corresponding principles (guards against false positives on good stats).
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_SIG_CLAIMS = (
    r"statistically\s+significant|significant(?:ly)?\s+(?:differ|increase|decrease|effect|improv|reduc|correlat)|"
    r"\bsignificance\b"
)
_PROOF = r"p(?:-|\s)value?s?\s+(?:proves?|confirms?|establishes?|demonstrates?|validates?)|proves?\s+(?:the\s+)?(?:hypothesis|effect|association)"
_HIGH_MAG = r"highly\s+significant|very\s+significant|extremely\s+significant|strongly\s+significant|more\s+significant"
_NO_EFFECT = (
    r"(?:no|not)\s+significant(?:ly)?\s+(?:difference|effect|association|correlation|change|differ)|"
    r"(?:were|was)\s+not\s+significant.{0,40}(?:no|therefore|thus|hence).{0,60}(?:no\s+difference|equivalent|same|absent|absence)"
)
_THRESHOLD_ONLY = r"p\s*<\s*0\.0\d|p\s*<\s*\.0\d"
_EUPHEMISM = r"marginal(?:ly)?\s+significant|tenden(?:cy|d)\s+toward\s+significance|approach(?:ed|ing)?\s+significance|borderline\s+significant|trending\s+towards?\s+significance"
_EFFECT_SIZE = (
    r"cohen'?s?\s+d|hedges'?s?\s*g|odds\s+ratio|risk\s+ratio|hazard\s+ratio|\u03b7\s*2|eta\s*(?:squared)?|"
    r"effect\s+size|r\s*2\b|partial\s+\u03b7|glass'?s?\s+\u0394|percent(?:age)?\s+(?:difference|improvement|change|increase|reduction)|"
    r"mean\s+difference|standardi[sz]ed\s+(?:beta|coefficient)"
)
_CI = r"95\s*%\s*CI|confidence\s+interval|CI\s*[\[(]\s*[\d.]+\s*[,\u2013-]"
_EXACT_P = r"p\s*=\s*0?\.\d+"


def _f(sev, title, detail, evidence, conf, action, principle):
    f = Finding("ASA p-values", sev, title, detail, evidence, action, conf)
    f.source = "asa_pvalues"
    return f


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return []
    if not re.search(r"\bp\s*[<>=]\s*0?\.\d|p-?value", body, re.IGNORECASE):
        return []  # no p-values reported -> ASA principles not engaged

    low = body.lower()
    has_effect_size = bool(re.search(_EFFECT_SIZE, low, re.IGNORECASE))
    has_ci = bool(re.search(_CI, low, re.IGNORECASE))
    has_exact_p = bool(re.search(_EXACT_P, low, re.IGNORECASE))
    out: List[Finding] = []

    # P3: significance claimed, but no effect size anywhere in the paper
    if re.search(_SIG_CLAIMS, low) and not has_effect_size:
        out.append(_f(
            Severity.HIGH,
            "Significance claimed with no effect size reported (ASA principle 3)",
            "The ASA statement is explicit: a p-value alone does not measure the "
            "size or importance of an effect. Report a standardized effect size "
            "(Cohen's d, Hedges' g, odds/risk/hazard ratio, \u03b7\u00b2, R\u00b2, or a mean "
            "difference with units) next to every significant claim. Reviewers at "
            "APA-signing venues treat this as a mandatory revision item.",
            "Significance language present; no effect-size statistics found in the full text",
            0.85,
            "Add effect sizes (with CIs) for every primary comparison",
            "P3"))

    # P2: threshold-only inference
    if re.search(_THRESHOLD_ONLY, low) and not has_exact_p:
        out.append(_f(
            Severity.MEDIUM,
            "Only threshold p-values reported (ASA principle 2)",
            "Reporting only p < 0.05 / p < 0.01 style thresholds forces readers to "
            "accept a binary decision. The ASA recommends reporting exact p-values "
            "so readers can apply their own standard (APA 7th ed. also requires "
            "exact p to 3 decimals, p < .001 excepted).",
            "Threshold inequalities found; no exact p = values found",
            0.75,
            "Report exact p-values (e.g., p = .032) rather than thresholds only",
            "P2"))

    # P4: magnitude rhetoric
    m_mag = re.search(_HIGH_MAG, low)
    if m_mag:
        out.append(_f(
            Severity.MEDIUM,
            "p-value used as a magnitude claim (ASA principle 4)",
            "\"Highly/very significant\" conflates evidence strength with effect "
            "size. A tiny effect can be highly significant with large N; the "
            "adjective should describe the effect size, never the p-value.",
            "Found rhetoric: \u201c" + m_mag.group(0) + "\u201d",
            0.85,
            "Replace magnitude adjectives with the measured effect size",
            "P4"))

    # P5: nonsignificance != no effect
    m_no = re.search(_NO_EFFECT, low)
    if m_no and not has_ci and not has_effect_size:
        out.append(_f(
            Severity.MEDIUM,
            "Absence of significance read as absence of effect (ASA principle 5)",
            "A nonsignificant result is only evidence of 'no detectable effect at "
            "this sample size', never proof of equivalence. Without CIs or "
            "equivalence testing (TOST), this claim overreaches \u2014 and underpowered "
            "negative results are a top reviewer-rejection trigger.",
            "Nonsignificance framing found; no CIs or effect sizes to support it",
            0.75,
            "Report CIs around the estimate, or run equivalence testing before claiming 'no effect'",
            "P5"))

    # P1: p as proof of hypothesis
    m_proof = re.search(_PROOF, low)
    if m_proof:
        out.append(_f(
            Severity.MEDIUM,
            "p-value framed as proof of the hypothesis (ASA principle 1)",
            "The ASA: p-values indicate how incompatible the data are with a "
            "specified model \u2014 they are not the probability the hypothesis is true. "
            "Phrases like 'the p-value proves the hypothesis' misstate the logic "
            "of NHST and invite a methods reviewer correction.",
            "Found rhetoric: \u201c" + m_proof.group(0) + "\u201d",
            0.8,
            "Rephrase as evidence against the null model, not proof of the hypothesis",
            "P1"))

    # P6: significance-euphemism language (borderline cherry-picking tell)
    m_euph = re.search(_EUPHEMISM, low)
    if m_euph:
        out.append(_f(
            Severity.LOW,
            "Significance euphemism for a nonsignificant result (ASA principle 6)",
            "\"Marginally significant\" / \"trending towards significance\" for "
            "p > 0.05 is a well-known QRP tell; reviewers read it as wanting the "
            "result to be significant. Report the exact p and interpret it honestly.",
            "Found rhetoric: \u201c" + m_euph.group(0) + "\u201d",
            0.7,
            "Report the exact p-value and interpret the result as nonsignificant (or pre-register a one-sided test)",
            "P6"))

    return out
