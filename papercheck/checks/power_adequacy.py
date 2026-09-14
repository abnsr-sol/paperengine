"""Power / sample-size adequacy engine — top peer-review rejection cause.

The 2026 desk-rejection and peer-review audits both rank "underpowered study /
no sample-size justification" among the top rejection reasons, yet PaperEngine
had no check for it. This engine is deterministic text analysis, not mind
reading. It fires only when it can *see* the contradiction:

  1. Human-subject study without any sample-size / power language at all.
  2. Small n claimed as a positive ("robust", "conclusive") — small samples
     cannot support those adjectives.
  3. Unequal group sizes stated without attrition explanation (unexplained
     imbalance after "randomly assigned" is a selective-dropout tell).
  4. Power-analysis vocabulary present but no numbers (naming power without
     stating the effect size, alpha, and power is checklist theater).

Severity stays at MEDIUM unless arithmetic impossibility is involved, so a
reviewer-friction finding never dominates a report. Correlational/big-data
studies are exempt from (1) — sample-size logic differs there.
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_HUMAN_SUBJ = (
    r"participants?\s+(?:were|was)|patients?\s+(?:were|was|enrolled|recruited)|subjects?\s+(?:were|was)|"
    r"respondents?|undergraduate|surveyed|enrolled|recruited|consecutive\s+(?:patients|cases)"
)
_HUMAN_ANY = r"\bparticipants?\b|\bpatients?\b|\bsubjects?\b|respondents?|undergraduates?"
_HUMAN_ACTION = r"enrolled|recruited|surveyed|assigned|allocated|consented|followed|completed|randomi[sz]ed"
_POWER_LANG = (
    r"power\s+(?:calculation|analysis|of)|a\s+priori\s+power|sample[- ]size\s+(?:calculation|justification|determination|was)\b|"
    r"G\*?Power|statistical\s+power|powered\s+to\s+detect|adequate\s+(?:statistical\s+)?power|"
    r"calculated\s+(?:a\s+)?sample\s+size|effect\s+size\s+(?:of|assumed|expected)"
)
_SMALL_N = r"\bn\s*=\s*(?:[1-9]|1\d|2\d)\b(?:\s*per\s*(?:group|arm|condition|site))?"
_ROBUST_CLAIM = r"robust|conclusive|definitive|well[- ]powered|sufficient\s+power|strong\s+evidence"
_RANDOMIZED = r"random(?:ly|ized|ised|ization|isation)\s+(?:assigned|allocated|divided)"
_GROUP_N = r"(?:n|N)\s*=\s*(\d+)\s*(?:and|\+|vs\.?|versus|,)\s*(?:n|N)?\s*=\s*(\d+)"
_ATTRITION = r"attrition|dropout|drop-out|withdraw|lost\s+to\s+follow-?up|excluded\s+(?:because|due)|discontinued"
_CORRELATIONAL = (
    r"corpus|benchmark|dataset\s+(?:of|with)\s+\d{3,}|large[- ]scale|log\s+data|telemetry|"
    r"secondary\s+(?:data|analysis)|registry\s+data|administrative\s+data"
)


def _f(sev, title, detail, evidence, conf, action):
    f = Finding("Power & Sample Size", sev, title, detail, evidence, action, conf)
    f.source = "power_adequacy"
    return f


def run(doc: Document, ctx: object) -> List[Finding]:
    body = doc.body_text or doc.text or ""
    if not body or len(body.split()) < 200:
        return []
    low = body.lower()
    human = bool(re.search(_HUMAN_SUBJ, low)) or (
        bool(re.search(_HUMAN_ANY, low)) and bool(re.search(_HUMAN_ACTION, low)))
    if not human:
        return []
    out: List[Finding] = []
    correlational = bool(re.search(_CORRELATIONAL, low))
    has_power = bool(re.search(_POWER_LANG, low))

    # 1. No sample-size reasoning at all
    if not has_power and not correlational:
        out.append(_f(
            Severity.MEDIUM,
            "No sample-size justification found in a participant study",
            "A priori power/sample-size justification is a CONSORT and ARRIVE "
            "requirement and a top cited reason in peer-review rejections. State "
            "the target effect size, alpha, desired power, and the resulting n "
            "before the results \u2014 or, for exploratory work, say explicitly why "
            "the sample was opportunistic and interpret effect sizes with CIs.",
            "Participant-study vocabulary found; no power/sample-size language anywhere",
            0.80,
            "Add a sample-size / power justification to the Methods section",
            ))

    # 2. Small n + big claims
    m_small = re.search(_SMALL_N, low)
    if m_small:
        strong = re.search(_ROBUST_CLAIM, low)
        if strong:
            out.append(_f(
                Severity.MEDIUM,
                "Small sample framed with high-certainty language",
                "n below ~30 (especially per-group) cannot support words like "
                "'robust', 'conclusive', or 'definitive'. Reviewers treat this "
                "pairing as evidence of overstating \u2014 and small samples only "
                "detect large effects, which should be stated as a limitation.",
                f"Found \u201c{m_small.group(0)}\u201d alongside strong-certainty wording "
                f"(\u201c{strong.group(0)}\u201d)",
                0.75,
                "Soften the certainty language and add small-sample limitations, or justify the n via power analysis",
                ))

    # 3. Unexplained group imbalance after randomization
    m_grp = re.search(_GROUP_N, low)
    if m_grp and re.search(_RANDOMIZED, low) and not re.search(_ATTRITION, low):
        try:
            n1, n2 = int(m_grp.group(1)), int(m_grp.group(2))
            bigger = max(n1, n2)
            smaller = max(1, min(n1, n2))
            if bigger / smaller >= 1.5 and bigger >= 20:
                out.append(_f(
                    Severity.LOW,
                    "Group sizes differ by >50% after randomization with no attrition note",
                    f"Randomized allocation reported with very unequal group sizes "
                    f"(n={n1} vs n={n2}). Without documented dropout/withdrawals "
                    "this pattern reads as selective reporting or post-hoc "
                    "exclusion \u2014 exactly what integrity reviewers look for.",
                    f"Reported \u201cn={n1}\u201d vs \u201cn={n2}\u201d; no attrition/dropout language found",
                    0.65,
                    "Report attrition per group and analyze per protocol / ITT as pre-specified",
                    ))
        except (ValueError, TypeError):
            pass

    # 4. Power vocabulary without numbers
    if re.search(r"power\s+(?:calculation|analysis)|G\*?Power|statistical\s+power", low):
        if not re.search(r"0?\.\d{1,2}\b\s*(?:power|\u03b2)|power\s*(?:of)?\s*0?\.\d{1,2}|\u03b1\s*=\s*0?\.\d{1,2}|alpha\s*=\s*0?\.\d{1,2}|d\s*=\s*0?\.\d{1,2}|effect\s+size\s*(?:of)?\s*0?\.\d{1,2}", low):
            out.append(_f(
                Severity.LOW,
                "Power analysis named but its parameters are missing",
                "A power analysis without the assumed effect size, alpha, and "
                "target power cannot be checked or reproduced \u2014 reviewers ask "
                "for these three numbers by reflex.",
                "Power-analysis vocabulary present; no numeric alpha/power/effect-size parameters found",
                0.70,
                "State the assumed effect size, alpha, power, and the software used (e.g., G*Power 3.1.9.7)",
                ))

    return out
