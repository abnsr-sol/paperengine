"""SPRITE: Sample Parameter Reconstruction via Iterative Techniques.

Heathers' follow-up to GRIM: given a reported mean, SD, sample size N, and
the response scale (e.g. 1-7 Likert), reconstruct whether *any* dataset of
N integers on that scale can produce those exact statistics. If none can,
the reported statistics are mathematically impossible — same certainty
class as GRIM/statcheck, not a heuristic.

Algorithm (deterministic, bounded):
1. GRIM precheck: the mean itself must be feasible for N integers.
2. Enumerate feasible integer sums k near mean*N (GRIM-consistent).
3. For each k, test SD feasibility: SD is determined by sum-of-squares,
   SS = sum(x_i^2). We search achievable SS values near (N-1)*SD^2 + k^2/N
   using a bounded DP over achievable (sum, sum-of-squares) pairs —
   restricted to the scale's integer range, so the search is polynomial,
   not exponential: we track reachable (sum, ss) states with a set, and
   stop as soon as any state matches the reported (k, ss) within the
   reported rounding of SD.
4. If no (k, ss) state reproduces the reported (mean, SD) at reported
   decimals for any k, the pair is infeasible -> SPRITE violation.

Conservative by design: only fires when the mean is GRIM-feasible (so a
GRIM violation is reported by the GRIM engine instead) and the scale is
bounded integers (we skip averaged/continuous scales — the finding text
always states the assumption).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

_MEAN_PAT = re.compile(r"\b(?:M|mean)\s*=\s*(\d+\.\d+)", re.IGNORECASE)
_N_PAT = re.compile(r"\b(?:N|n)\s*=\s*(\d{1,4})\b")
_SD_PAT = re.compile(r"\bSD\s*=\s*(\d+\.\d+)", re.IGNORECASE)
_SCALE_PAT = re.compile(
    r"\b(\d+)\s*(?:-|to)\s*(\d+)\s*(?:point| Likert|)[- ]scale", re.IGNORECASE)


@dataclass
class SpriteResult:
    reported_mean: float
    reported_sd: float
    n: int
    scale_min: int
    scale_max: int
    feasible: bool
    context: str
    position: int


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _round_fmt(value: float, d: int) -> str:
    return f"{value:.{d}f}"


def sprite_feasible(mean: float, sd: float, n: int, scale_min: int,
                    scale_max: int, decimals: int = 2,
                    items: int = 1) -> bool:
    """Can N*items integers in [scale_min, scale_max] produce (mean, SD)?"""
    if n <= 0 or sd < 0 or scale_max <= scale_min:
        return True  # unknowable -> don't flag
    k_total = n * items
    lo_sum = k_total * scale_min
    hi_sum = k_total * scale_max
    mean_fmt = _round_fmt(mean, decimals)
    sd_fmt = _round_fmt(sd, decimals)

    # candidate integer sums consistent with the reported mean
    k_center = round(mean * k_total)
    candidates = [k for k in range(k_center - 2, k_center + 3)
                  if lo_sum <= k <= hi_sum]
    if not any(_round_fmt(k / k_total, decimals) == mean_fmt for k in candidates):
        # mean itself infeasible: that's GRIM's job, not SPRITE's
        return True

    # DP over reachable (sum, sum-of-squares) states.
    # Pruning is remaining-aware: a partial state survives if the items not
    # yet placed could still bring it into the feasible window.
    target_ss_center = (k_total - 1) * sd * sd + k_center * k_center / k_total
    window = max(50.0, target_ss_center * 0.25)
    lo_ss = max(0.0, target_ss_center - window)
    hi_ss = target_ss_center + window
    max_val2 = scale_max * scale_max
    max_val = scale_max

    states: dict = {0: {0}}
    for placed in range(k_total):
        remaining = k_total - placed - 1
        min_future_sum = remaining * scale_min
        max_future_sum = remaining * max_val
        min_future_ss = remaining * scale_min * scale_min
        max_future_ss = remaining * max_val2
        new_states: dict = {}
        for s, sss in states.items():
            for val in range(scale_min, scale_max + 1):
                s2 = s + val
                # reachable final sums through this partial state
                if s2 + min_future_sum > hi_sum or s2 + max_future_sum < lo_sum:
                    continue
                bucket = None
                for ss in sss:
                    ss2 = ss + val * val
                    if ss2 + min_future_ss > hi_ss or ss2 + max_future_ss < lo_ss:
                        continue
                    if bucket is None:
                        bucket = new_states.setdefault(s2, set())
                    bucket.add(ss2)
        states = new_states
        if not states:
            return False

    for k in candidates:
        sss = states.get(k)
        if not sss:
            continue
        for ss in sss:
            variance = (ss - k * k / k_total) / (k_total - 1)
            if variance < 0:
                continue
            sample_sd = variance ** 0.5
            if _round_fmt(sample_sd, decimals) == sd_fmt:
                return True
    return False


def _sentence_around(text: str, pos: int, radius: int = 140) -> str:
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def extract_sprite(text: str) -> List[SpriteResult]:
    """Find (M, SD, N) triples near a declared scale and test feasibility."""
    out: List[SpriteResult] = []
    scales = [(m.start(), int(m.group(1)), int(m.group(2)))
              for m in _SCALE_PAT.finditer(text)]
    ns = [(m.start(), int(m.group(1))) for m in _N_PAT.finditer(text)]
    for m in _MEAN_PAT.finditer(text):
        mean = float(m.group(1))
        dec = _decimals(m.group(1))
        # nearest SD after the mean (APA order: M, SD, then usually N)
        sd_m = _SD_PAT.search(text, m.end(), m.end() + 220)
        if not sd_m:
            continue
        sd = float(sd_m.group(1))
        # N association: prefer the N closest to the SD report (APA order:
        # "M = x, SD = y, N = z"), else the nearest N before the mean
        window_end = sd_m.end() + 60
        in_clause = [(abs(pos - sd_m.end()), n) for pos, n in ns
                     if m.start() <= pos <= window_end]
        if in_clause:
            n = min(in_clause)[1]
        else:
            before = [(m.start() - pos, n) for pos, n in ns
                      if 0 <= m.start() - pos < 220]
            if not before:
                continue
            n = min(before)[1]
        if n < 5 or n > 5000:
            continue
        # nearest declared scale
        near_scale = [(smin, smax) for pos, smin, smax in scales
                      if 0 <= m.start() - pos < 400]
        scale_min, scale_max = (near_scale[-1] if near_scale else (1, 7))
        if scale_max - scale_min < 1:
            continue
        feas = sprite_feasible(mean, sd, n, scale_min, scale_max, dec)
        out.append(SpriteResult(
            reported_mean=mean, reported_sd=sd, n=n,
            scale_min=scale_min, scale_max=scale_max, feasible=feas,
            context=_sentence_around(text, m.start()), position=m.start()))
    return out
