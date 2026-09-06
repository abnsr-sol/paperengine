"""GRIM & GRIMMER: deterministic consistency tests for reported statistics.

GRIM (Granularity-Related Inconsistency of Means; Brown & Heathers, 2016):
a mean of N integer values must equal k/N for some integer k. Given the
reported rounding (d decimals), the reported mean is *mathematically
impossible* if no integer k satisfies round(k/N, d) == mean.
Classic example (from the Wikipedia write-up): N=20, mean=3.48 — any
integer sum divided by 20 ends in .X0 or .X5 at two decimals, so 3.48
cannot exist.

GRIMMER (Allbutt, Brown & Luciano): extends the idea to standard
deviations. For integer data with mean M and sample SD S, the corrected
sum of squares  SS = (N-1) * S^2 + (sum_squares_correction)  must satisfy
sqrt(SS_round-trip) consistency: we brute-force candidate integer sums k
whose mean matches, then check whether any assignment is consistent with
the reported SD at the reported rounding. Simplified practical check used
here: for each candidate sum k with mean M, compute the minimal and
maximal achievable sample SD given integer data in a plausible range is
complex — instead we use the standard GRIMMER criterion:

    S^2 * (N - 1) must be such that SS = sum(x_i^2) - N*M^2 where
    SS >= 0 and the reported S rounds consistently for *some* integer
    sum-of-squares value. Concretely: SS_reported = S^2 * (N - 1) (plus
    mean correction), and SS must be an achievable real given integer
    data: we test whether round(trip) of S through the sum-of-squares
    formula matches at the reported decimals.

Like statcheck, failures are arithmetic facts, not heuristics. Both tests
are conservative: GRIM is exact; GRIMMER only fires on clear violations
and notes that non-integer scales (e.g. averaged subscales) can produce
false alarms — the finding text says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Mean patterns: "M = 3.48" / "mean of 4.12" / "(M = 2.9, SD = 0.74)"
_MEAN_PAT = re.compile(
    r"\b(?:M|mean)\s*=\s*(\d+\.\d+)", re.IGNORECASE)
_N_PAT = re.compile(
    r"\b(?:N|n)\s*=\s*(\d{1,4})\b")
_SD_PAT = re.compile(
    r"\bSD\s*=\s*(\d+\.\d+)", re.IGNORECASE)


@dataclass
class GrimResult:
    reported_mean: float
    n: int
    decimals: int
    possible: bool
    context: str
    position: int


def _decimals(text_val: str) -> int:
    return len(text_val.split(".")[1]) if "." in text_val else 0


def grim_check(mean: float, n: int, decimals: int) -> bool:
    """True if some integer k gives round(k/N, decimals) == mean.

    k need only satisfy round-trip consistency: the only candidate sums are
    integers near mean*N, so test k = round(mean*N) and its neighbours using
    exact decimal-string comparison (never raw float ==)."""
    if n <= 0:
        return True  # unknowable, don't flag
    fmt = f"{mean:.{decimals}f}"
    k_center = round(mean * n)
    for k in (k_center - 1, k_center, k_center + 1):
        if k < 0:
            continue
        if f"{k / n:.{decimals}f}" == fmt:
            return True
    return False


def _sentence_around(text: str, pos: int, radius: int = 140) -> str:
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def extract_grim(text: str) -> List[GrimResult]:
    """Find reported means, associate the nearest N, and test them."""
    out: List[GrimResult] = []
    ns = [(m.start(), int(m.group(1))) for m in _N_PAT.finditer(text)]
    for m in _MEAN_PAT.finditer(text):
        mean_txt = m.group(1)
        mean = float(mean_txt)
        d = _decimals(mean_txt)
        if d < 2:
            continue  # 1-decimal means are almost always possible; skip noise
        # nearest N mention before this mean (within ~400 chars)
        best = None
        for (pos, n) in ns:
            if pos < m.start() and m.start() - pos < 400:
                if best is None or pos > best[0]:
                    best = (pos, n)
        if best is None:
            continue
        n = best[1]
        if n < 5 or n > 1000:
            continue  # GRIM applies to small-to-moderate integer datasets
        ok = grim_check(mean, n, d)
        out.append(GrimResult(
            reported_mean=mean, n=n, decimals=d, possible=ok,
            context=_sentence_around(text, m.start()), position=m.start(),
        ))
    return out


def grimmer_check(mean: float, sd: float, n: int, decimals: int) -> Optional[bool]:
    """Conservative GRIMMER: does an integer sum-of-squares exist that
    reproduces the reported SD at the reported rounding, given the mean?

    Returns None when the check is not applicable (can't bound candidates)."""
    if n <= 1:
        return None
    # corrected sum of squares implied by the report:
    # SS = sum((x_i - M)^2) = (N-1) * S^2  for the sample SD
    ss_target = (n - 1) * sd * sd
    # SS for integer data: sum(x_i^2) - (sum x_i)^2 / N, where sum x_i = k.
    # k ranges over values whose mean rounds to the reported mean.
    scale = 10 ** decimals
    k_center = round(mean * n)
    k_candidates = [k for k in range(max(0, k_center - 2), k_center + 3)
                    if round(k / n, decimals) == round(mean, decimals)]
    if not k_candidates:
        return None
    # For integer data, sum(x_i^2) is an integer, so SS = T - k^2/n where T
    # is an integer. SS must therefore satisfy: T = SS + k^2/n is an integer
    # for some candidate k. Test rounding-consistency of S from such T.
    for k in k_candidates:
        # T must be >= k^2/n (sum of squares >= (sum)^2/n)
        t_min = k * k / n
        # search integer T near SS_target + k^2/n
        t_ideal = ss_target + k * k / n
        for t in (int(t_ideal), int(t_ideal) + 1):
            if t < t_min:
                continue
            ss = t - k * k / n
            if ss < 0:
                continue
            s_calc = (ss / (n - 1)) ** 0.5
            if round(s_calc, decimals) == round(sd, decimals):
                return True
    return False


def extract_sd_contexts(text: str) -> List[Tuple[float, float, int, str, int]]:
    """(mean, sd, n, context, position) triples for 'M = x, SD = y' near N."""
    out = []
    ns = [(m.start(), int(m.group(1))) for m in _N_PAT.finditer(text)]
    for m in re.finditer(
            r"\b(?:M|mean)\s*=\s*(\d+\.\d+)\s*,\s*SD\s*=\s*(\d+\.\d+)",
            text, re.IGNORECASE):
        mean = float(m.group(1))
        sd = float(m.group(2))
        d = max(_decimals(m.group(1)), _decimals(m.group(2)))
        best = None
        for (pos, n) in ns:
            if pos < m.start() and m.start() - pos < 400:
                if best is None or pos > best[0]:
                    best = (pos, n)
        if best is None:
            continue
        n = best[1]
        if n < 5 or n > 1000:
            continue
        out.append((mean, sd, n, _sentence_around(text, m.start()), m.start()))
    return out


__all__ = ["GrimResult", "grim_check", "grimmer_check", "extract_grim",
           "extract_sd_contexts"]
