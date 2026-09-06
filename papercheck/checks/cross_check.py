"""Cross-checks engine: cross-representation consistency (figure vs table vs text).

Covers the two angles no other engine handled:
  - #7  Inconsistent n: different sample sizes quoted for the same quantity
  - #56 Duplicate data: the same numbers presented as both a figure and a table
Plus numeric-vs-word contradictions adjacent to stats claims.
"""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Cross-Check", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.body_text or doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []

    # --- #7 Inconsistent n: 'n = X' values differing across the paper -------
    n_vals = set()
    for m in re.finditer(r"\bn\s*=\s*(\d{1,5})\b", low):
        n_vals.add(int(m.group(1)))
    # multiple distinct large n values is normal (per-group n); flag only
    # when several differ by a little AND the text never says per-group
    if len(n_vals) >= 3:
        big = sorted(v for v in n_vals if v >= 10)
        if len(big) >= 3:
            spread = big[-1] - big[0]
            if 0 < spread <= 5 and not re.search(r"per\s+(?:group|arm|site)|respectively|each\s+(?:group|arm)", low):
                out.append(_f(Severity.LOW, "Possible inconsistent sample sizes (n)",
                              "Several slightly different n values (" + ", ".join(map(str, big[:6])) + ") appear without per-group framing; dropouts explained? Reviewers check n consistency across tables/figures.",
                              "n values seen: " + ", ".join(map(str, big[:8])), 0.55,
                              "Explain n differences (dropouts, exclusions) or state per-group n explicitly"))

    # --- #56 Duplicate data: same numbers in both a figure and a table ------
    # heuristic: a number that is immediately introduced by BOTH 'figure N'
    # and 'table N' contexts in the same paper.
    if doc.figures and doc.tables:
        fig_nums = set()
        for m in re.finditer(r"figure\s+(\d{1,2})", low):
            fig_nums.add(m.group(1))
        tbl_nums = set()
        for m in re.finditer(r"table\s+(\d{1,2})", low):
            tbl_nums.add(m.group(1))
        # find a number embedded in a figure caption-ish sentence and table-ish sentence
        fig_context = re.findall(r"figure\s+\d{1,2}[^.]{0,120}?(\d{2,6}(?:\.\d+)?)\b", low)
        tbl_context = re.finditer(r"table\s+\d{1,2}[^.]{0,120}?(\d{2,6}(?:\.\d+)?)\b", low)
        tbl_vals = [m.group(1) for m in tbl_context]
        shared = [v for v in fig_context if v in tbl_vals][:4]
        if shared:
            out.append(_f(Severity.MEDIUM, "Possible duplicate data (same values in figure and table)",
                          "The same value(s) appear in figure-adjacent and table-adjacent text; journals discourage showing identical data twice (redundant presentation).",
                          "Values in both contexts: " + ", ".join(shared), 0.55,
                          "Show the data once (figure OR table) and cross-reference the other"))

    # --- numeric-vs-word contradictions near stats claims -------------------
    contradictions = []
    for m in re.finditer(r"(?:increase|decrease|rose|fell|higher|lower|improved|reduced)[^.]{0,80}?(\d{1,3}(?:\.\d+)?)\s*%[^.]{0,40}?(?:compared|versus|vs\.?|than)[^.]{0,40}?(\d{1,3}(?:\.\d+)?)\s*%", low):
        a, b = float(m.group(1)), float(m.group(2))
        verb = m.group(0)
        # 'increased ... 30% vs 10%' is fine if direction matches magnitude
        if any(w in verb for w in ("increase", "rose", "higher", "improved")) and a < b:
            contradictions.append(f"{a}% vs {b}% (increase)")
        elif any(w in verb for w in ("decrease", "fell", "lower", "reduced")) and a > b:
            contradictions.append(f"{a}% vs {b}% (decrease)")
    if contradictions:
        out.append(_f(Severity.LOW, "Possible numeric-word contradictions",
                      "Comparison wording may contradict the numbers (direction vs magnitude). Verify each.",
                      "; ".join(contradictions[:3]), 0.50,
                      "Check that each comparison's wording matches its numbers"))
    return out