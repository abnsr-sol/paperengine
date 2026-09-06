"""AI-risk engine: stylometric signals, reported as *risk, never proof*.

Why the caution matters (research findings baked into the design):
- AI detectors are probabilistic; Turnitin itself warns its AI assessment can
  misidentify human and AI text and must not be the sole basis for action.
- Low burstiness, low lexical diversity, template transitions, and uniform
  sentences occur naturally in non-native and highly technical writing.
- There is no scientifically supported rule like "em dash = AI" or
  "underscore = AI". This engine deliberately does NOT treat typography as
  evidence; it reports measurable text statistics and an uncertainty band.

A detector like GPTZero/Originality.ai can be plugged in later via API; this
module defines the interface (see README "Plug in real detectors").
"""

from __future__ import annotations

from typing import Dict, List

from ..ingestion import Document
from ..metrics import (
    AI_TEMPLATES,
    count_terms,
    mean,
    punctuation_profile,
    repeated_phrase_density,
    sentence_burstiness,
    sentence_lengths,
    type_token_ratio,
)
from ..risk import Finding, Severity, clamp01
from . import CheckContext

DISCLAIMER = (
    "AI-risk scores are probabilistic stylometric signals, not proof of AI authorship. "
    "Human technical/non-native writing is frequently misflagged; treat any elevated "
    "signal as a reason to revise for natural, varied prose — never as an accusation."
)


def _signal_contributions(doc: Document) -> Dict[str, float]:
    """Each signal in [0,1] plus a brief why. Heuristics calibrated conservatively."""
    text = doc.body_text
    contrib: Dict[str, float] = {}

    burst = sentence_burstiness(text)
    contrib["uniform sentence rhythm (low burstiness)"] = clamp01((0.45 - burst) / 0.35) if burst > 0 else 0.0

    ttr = type_token_ratio(text)
    contrib["low lexical diversity"] = clamp01((0.5 - ttr) / 0.25) if ttr > 0 else 0.0

    lens = sentence_lengths(text)
    if lens:
        avg = mean(lens)
        contrib["very long average sentence"] = clamp01((avg - 24) / 16) if avg > 24 else 0.0

    templ = count_terms(text, AI_TEMPLATES)
    nt = sum(templ.values())
    contrib["dense template transitions"] = clamp01((nt - 3) / 25)

    rep = repeated_phrase_density(text)
    contrib["high phrase repetition"] = clamp01((rep - 0.04) / 0.10)

    prof = punctuation_profile(text)
    n_sents = max(1, len(lens))
    semicolons_per_sent = prof["semicolon"] / n_sents
    contrib["heavy semicolon use"] = clamp01((semicolons_per_sent - 0.5) / 1.5)

    return contrib


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    if doc.word_count < 100:
        return []

    contribs = _signal_contributions(doc)
    active = {k: v for k, v in contribs.items() if v >= 0.35}
    if not active:
        return []

    raw = sum(v * v for v in contribs.values()) ** 0.5
    score = clamp01(raw / 1.8)  # heuristic calibration
    n_active = len(active)

    findings: List[Finding] = []

    if n_active >= 2 and score >= 0.55:
        top = sorted(active.items(), key=lambda kv: kv[1], reverse=True)[:4]
        signal_desc = "; ".join(f"{k} ({v*100:.0f}%)" for k, v in top)
        findings.append(Finding(
            category="AI-risk",
            severity=Severity.MEDIUM,
            title="Elevated AI-style writing signals (probabilistic)",
            detail=(
                f"{n_active} stylometric signals are elevated. Aggregate AI-risk {score*100:.0f}% "
                f"with an uncertainty band of ±{30} pts. This is NOT proof of AI authorship."
            ),
            evidence=signal_desc,
            action=(
                "Vary sentence length and structure, add human-specific detail and examples, "
                "reduce mechanical transitions, and keep your own voice. If you used AI tools, "
                "disclose per the venue's policy and keep human accountability."
            ),
            confidence=0.5,  # deliberately low — stylometry alone is unreliable
            location="whole document",
        ))
        findings.append(Finding(
            category="AI-risk",
            severity=Severity.INFO,
            title="AI-detection disclaimer",
            detail=DISCLAIMER,
            evidence="stylometric heuristics only; no commercial detector used",
            action="For high-stakes venues, run an actual detector ensemble (Turnitin/GPTZero/Copyleaks) and reconcile results manually.",
            confidence=1.0,
        ))

    # Feature-level flags with individual explanations
    for name, val in active.items():
        if val >= 0.6:
            findings.append(Finding(
                category="AI-risk",
                severity=Severity.LOW,
                title=f"Signal: {name}",
                detail=f"Measured value contributes {val*100:.0f}% to the aggregate AI-risk score.",
                evidence=f"{name} = {val:.2f} (heuristic, may occur naturally in technical writing)",
                action="Review the affected passages and vary the writing style; confirm with a human editor.",
                confidence=0.4,
                location="whole document",
            ))
    return findings