"""Statistical recomputation core: recompute p-values from reported test
statistics — a pure-Python, stdlib-only port of the statcheck idea
(Nuijten et al.). No scipy, no numpy.

Supported APA-style results:
    t(df) = 2.45, p = .01        (two-tailed t)
    F(df1, df2) = 5.31, p = .02  (F, right tail)
    chi2(df) = 9.12, p = .01     (chi-square, right tail; also χ²)
    r(df) = .38, p = .002        (Pearson r via t conversion)
    z = 2.61, p = .009           (normal)

Everything runs offline; results are deterministic and reproducible, which
is the point: a recomputed p-value is arithmetic, not opinion.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# --------------------------------------------------------------------------
# Special functions (stdlib only)
# --------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float, itmax: int = 300, eps: float = 3e-12) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(ln_beta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _gser(a: float, x: float, itmax: int = 500, eps: float = 3e-12) -> float:
    """Regularized lower incomplete gamma P(a, x) by series (small x)."""
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(itmax):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * eps:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float, itmax: int = 500, eps: float = 3e-12) -> float:
    """Regularized upper incomplete gamma Q(a, x) by continued fraction."""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, itmax + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gammainc_lower(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x)."""
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        return _gser(a, x)
    return 1.0 - _gcf(a, x)


# --------------------------------------------------------------------------
# Distribution tails
# --------------------------------------------------------------------------

def t_p_two_tailed(t: float, df: float) -> float:
    """Two-tailed p for Student's t."""
    if df <= 0:
        return float("nan")
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def f_p(f_val: float, df1: float, df2: float) -> float:
    """Upper-tail p for the F distribution."""
    if f_val <= 0 or df1 <= 0 or df2 <= 0:
        return float("nan")
    x = df2 / (df2 + df1 * f_val)
    return betainc(df2 / 2.0, df1 / 2.0, x)


def chi2_p(x: float, df: float) -> float:
    """Upper-tail p for chi-square."""
    if x <= 0 or df <= 0:
        return float("nan")
    return 1.0 - gammainc_lower(df / 2.0, x / 2.0)


def z_p_two_tailed(z: float) -> float:
    """Two-tailed p for the standard normal."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def r_p_two_tailed(r: float, df: float) -> float:
    """Two-tailed p for a Pearson correlation (via t conversion)."""
    if df <= 0 or abs(r) >= 1.0:
        return float("nan")
    t = r * math.sqrt(df / (1.0 - r * r))
    return t_p_two_tailed(t, df)


# --------------------------------------------------------------------------
# APA result extraction
# --------------------------------------------------------------------------

# APA style: "t(28) = 2.45, p = .01" / "F(2, 46) = 5.31, p < .001" / etc.
_STAT_RES = [
    ("t", re.compile(
        r"\bt\s*\(\s*(\d+(?:\.\d+)?)\s*\)\s*=\s*(-?\d+(?:\.\d+)?)\s*,?\s*"
        r"p\s*(?:=|<|>|≤|≥)\s*(\.?\d+(?:\.\d+)?|0\.\d+)")),
    ("F", re.compile(
        r"\bF\s*\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)\s*=\s*"
        r"(\d+(?:\.\d+)?)\s*,?\s*p\s*(?:=|<|>|≤|≥)\s*(\.?\d+(?:\.\d+)?)")),
    ("chi2", re.compile(
        r"(?:\u03c7\u00b2|chi2|chi\u00b2|\u03c72)\s*\(\s*(\d+(?:\.\d+)?)\s*\)\s*=\s*"
        r"(\d+(?:\.\d+)?)\s*,?\s*p\s*(?:=|<|>|≤|≥)\s*(\.?\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("r", re.compile(
        r"\br\s*\(\s*(\d+(?:\.\d+)?)\s*\)\s*=\s*(?:-?)(\.\d+|0\.\d+)\s*,?\s*"
        r"p\s*(?:=|<|>|≤|≥)\s*(\.?\d+(?:\.\d+)?)")),
    ("z", re.compile(
        r"\bz\s*=\s*(-?\d+(?:\.\d+)?)\s*,?\s*p\s*(?:=|<|>|≤|≥)\s*(\.?\d+(?:\.\d+)?)")),
]


@dataclass
class StatResult:
    """One reported NHST result with its recomputed p-value."""

    stat: str            # t / F / chi2 / r / z
    statistic: float
    reported_p: float
    operator: str        # = < > ≤ ≥
    recomputed_p: Optional[float]
    context: str         # the matched sentence fragment
    position: int
    p_decimals: int = 3  # decimals in the RAW reported p (for rounding intervals)

    @property
    def decision_error(self) -> bool:
        """Reported and recomputed p fall on opposite sides of .05.

        Rounding-aware: the reported p is itself a rounded value — '.05'
        stands for any true p in [0.045, 0.055). If that interval straddles
        the alpha boundary, the report cannot contradict the statistic no
        matter which side the exact p lands on (e.g. F(2,57)=3.16, p=.05
        recomputes to 0.049948 — pure 2-decimal rounding, NOT an error).
        Only an interval entirely on one side can produce a decision error.
        """
        if self.recomputed_p is None or self.operator not in ("=",):
            return False
        half = 0.5 * 10 ** (-self.p_decimals)
        lo, hi = self.reported_p - half, self.reported_p + half
        if lo <= 0.05 <= hi:
            return False
        return (self.reported_p < 0.05) != (self.recomputed_p < 0.05)

    @property
    def abs_error(self) -> float:
        if self.recomputed_p is None:
            return float("nan")
        return abs(self.reported_p - self.recomputed_p)


def _norm_p(raw: str) -> float:
    """APA writes 'p = .01' — normalize to 0.01."""
    raw = raw.strip()
    if raw.startswith("."):
        raw = "0" + raw
    try:
        return float(raw)
    except ValueError:
        return float("nan")


def _p_decimals(raw: str) -> int:
    """Decimal places in the RAW reported p (e.g. '.05' -> 2, '0.013' -> 3).
    Defines the rounding interval a printed p legitimately covers."""
    raw = raw.strip().lstrip("0").lstrip(".")
    return max(2, len(raw)) if raw else 2


def extract_results(text: str) -> List[StatResult]:
    out: List[StatResult] = []
    taken: List[Tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(not (e <= a or s >= b) for a, b in taken)

    for stat, rx in _STAT_RES:
        for m in rx.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            taken.append((m.start(), m.end()))
            op_m = re.search(r"p\s*([=<>≤≥])", m.group(0))
            op = op_m.group(1) if op_m else "="
            try:
                if stat == "t":
                    df = float(m.group(1))
                    tval = float(m.group(2))
                    rep = _norm_p(m.group(3))
                    calc = t_p_two_tailed(tval, df)
                    statval, ncalc = tval, calc
                elif stat == "F":
                    df1, df2 = float(m.group(1)), float(m.group(2))
                    fval = float(m.group(3))
                    rep = _norm_p(m.group(4))
                    ncalc = f_p(fval, df1, df2)
                    statval = fval
                elif stat == "chi2":
                    df = float(m.group(1))
                    xval = float(m.group(2))
                    rep = _norm_p(m.group(3))
                    ncalc = chi2_p(xval, df)
                    statval = xval
                elif stat == "r":
                    df = float(m.group(1))
                    rval = float(m.group(2))
                    rep = _norm_p(m.group(3))
                    ncalc = r_p_two_tailed(rval, df)
                    statval = rval
                else:  # z
                    zval = float(m.group(1))
                    rep = _norm_p(m.group(2))
                    ncalc = z_p_two_tailed(zval)
                    statval = zval
            except (ValueError, OverflowError):
                continue
            if math.isnan(ncalc):
                continue
            pm = re.search(r"p\s*[=<>\u2264\u2265]\s*([.0-9]+)", m.group(0))
            p_raw = pm.group(1) if pm else ""
            out.append(StatResult(
                stat=stat, statistic=statval, reported_p=rep, operator=op,
                recomputed_p=round(ncalc, 6),
                p_decimals=_p_decimals(p_raw),
                context=re.sub(r"\s+", " ", m.group(0)).strip(),
                position=m.start(),
            ))
    out.sort(key=lambda r: r.position)
    return out


__all__ = ["StatResult", "extract_results", "t_p_two_tailed", "f_p",
           "chi2_p", "z_p_two_tailed", "r_p_two_tailed"]
