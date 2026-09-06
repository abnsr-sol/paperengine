"""Before/after comparison: run the same checks on a revised manuscript and
show what improved, what is still open, and what is new.

Signature design: findings are keyed by (category, normalized title) so that
line-number or evidence-string drift between revisions still matches. Titles
like "Missing statement: Data availability" stay stable across revisions,
while cosmetic detail lives in evidence/detail (not part of the key).
"""
from __future__ import annotations

import html as _html
import re
from typing import Dict, List, Optional, Sequence

from .ingestion import PdfExtractionError, UnsupportedFormatError, load_document
from .risk import Finding, RiskReport, Severity, severity_from_string
from .venues import describe, get_rules

from .checks import ALL_ENGINES, CheckContext

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    return _NORM_RE.sub(" ", (text or "").lower()).strip()


def _key(f: Finding) -> tuple:
    return (f.category, _norm(f.title))


def _severity_key(f: Finding) -> int:
    return f.severity.sort_rank


def _run_full(path: str, venue: str, standard: str) -> RiskReport:
    doc = load_document(path)
    rules = get_rules(venue)
    ctx = CheckContext(venue=describe(venue), rules=rules, online=False, max_online_checks=0)
    report = RiskReport(document_name=doc.name, venue=describe(venue))
    report.stats = {
        "words": f"{doc.word_count:,}",
        "standard": "National (Indian)" if standard == "national" else "International",
    }
    for engine in ALL_ENGINES:
        report.extend(engine(doc, ctx))
    return report


class Comparison:
    """Result of comparing a revised manuscript against the original."""

    def __init__(self, before: RiskReport, after: RiskReport,
                 fixed: List[Finding], still_open: List[Finding], new: List[Finding]):
        self.before = before
        self.after = after
        self.fixed = fixed
        self.still_open = still_open
        self.new = new

    @property
    def score_before(self) -> int:
        return self.before.readiness_score

    @property
    def score_after(self) -> int:
        return self.after.readiness_score

    @property
    def delta(self) -> int:
        return self.score_after - self.score_before

    def summary(self) -> Dict[str, int]:
        return {
            "before": self.score_before,
            "after": self.score_after,
            "delta": self.delta,
            "fixed": len(self.fixed),
            "still_open": len(self.still_open),
            "new": len(self.new),
        }


def compare(original_path: str, revised_path: str, venue: str = "generic",
            standard: str = "international") -> Comparison:
    """Run the full engine set on both files and diff the findings."""
    before = _run_full(original_path, venue, standard)
    after = _run_full(revised_path, venue, standard)

    b_map: Dict[tuple, Finding] = {}
    for f in before.findings:
        b_map.setdefault(_key(f), f)  # keep highest-severity occurrence via setdefault order
    a_map: Dict[tuple, Finding] = {}
    for f in after.findings:
        a_map.setdefault(_key(f), f)

    fixed = sorted((f for k, f in b_map.items() if k not in a_map),
                   key=_severity_key)
    still_open = sorted((f for k, f in b_map.items() if k in a_map),
                        key=_severity_key)
    new = sorted((f for k, f in a_map.items() if k not in b_map),
                 key=_severity_key)
    return Comparison(before, after, fixed, still_open, new)


def _bar(score: int, width: int = 20) -> str:
    filled = max(0, min(width, round(score / 100 * width)))
    return "#" * filled + "." * (width - filled)


def render_console(cmp: Comparison) -> str:
    s = cmp.summary()
    lines: List[str] = []
    lines.append("BEFORE / AFTER COMPARISON")
    lines.append(f"  original: {cmp.before.document_name}")
    lines.append(f"  revised:  {cmp.after.document_name}")
    lines.append("")
    arrow = "+" if s["delta"] >= 0 else "-"
    lines.append(f"  readiness score: {s['before']:>3} -> {s['after']:>3}  ({arrow}{abs(s['delta'])})")
    lines.append(f"  [{_bar(s['before'])}] -> [{_bar(s['after'])}]")
    lines.append("")
    lines.append(f"  fixed:      {s['fixed']}")
    lines.append(f"  still open: {s['still_open']}")
    lines.append(f"  new:        {s['new']}")
    lines.append("")

    def block(title: str, items: Sequence[Finding], show_action: bool) -> None:
        lines.append(f"{title} ({len(items)}):")
        if not items:
            lines.append("  (none)")
        for f in items[:25]:
            lines.append(f"  [{f.severity.value.upper()}] {f.title}")
            if show_action and f.action:
                lines.append(f"        -> {f.action}")
        if len(items) > 25:
            lines.append(f"  ... and {len(items) - 25} more")
        lines.append("")

    block("FIXED since last version", cmp.fixed, show_action=False)
    block("STILL OPEN - work on these next", cmp.still_open, show_action=True)
    block("NEW in this revision (check carefully)", cmp.new, show_action=False)
    return "\n".join(lines)


_SEV_COLOR = {
    "critical": "#b71c1c",
    "high": "#c62828",
    "medium": "#b26a00",
    "low": "#5f6c7b",
}


def render_html(cmp: Comparison) -> str:
    s = cmp.summary()
    e = _html.escape

    def rows(items: Sequence[Finding], show_action: bool) -> str:
        if not items:
            return '<tr><td colspan="3" style="color:#778">(none)</td></tr>'
        out = []
        for f in items:
            color = _SEV_COLOR.get(f.severity.value, "#334")
            action = e(f.action) if (show_action and f.action) else ""
            out.append(
                f'<tr><td style="color:{color};font-weight:bold;white-space:nowrap">'
                f'{e(f.severity.value.upper())}</td><td>{e(f.title)}</td>'
                f"<td>{action}</td></tr>"
            )
        return "\n".join(out)

    arrow = "+" if s["delta"] >= 0 else "\u2212"
    delta_color = "var(--ok)" if s["delta"] >= 0 else "var(--bad)"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PaperEngine — revision comparison</title>
<style>
  body {{ font-family:Georgia,'Times New Roman',serif; margin:0; background:#f4f4ef; color:#1a2233; }}
  header {{ background:#1a2233; color:#fff; padding:18px 28px; }}
  header h1 {{ margin:0; font-size:1.35rem; }}
  main {{ max-width:960px; margin:0 auto; padding:24px; }}
  .scores {{ display:flex; gap:26px; align-items:center; margin:18px 0; flex-wrap:wrap; }}
  .score {{ font-size:2.4rem; font-weight:bold; }}
  .score small {{ font-size:.9rem; color:#667; font-weight:normal; display:block; }}
  .delta {{ font-size:1.5rem; color:{delta_color}; font-weight:bold; }}
  .chips span {{ display:inline-block; padding:6px 14px; border-radius:16px; margin-right:8px; font-size:.9rem; }}
  .chip-fixed {{ background:#e3f4e9; color:#1b7f4d; }}
  .chip-open  {{ background:#fdecea; color:#c62828; }}
  .chip-new   {{ background:#fff3cd; color:#8a6d00; }}
  h2 {{ border-bottom:2px solid #dde; padding-bottom:6px; margin-top:34px; font-size:1.1rem; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; border-radius:8px; overflow:hidden; }}
  th {{ background:#eef1f6; text-align:left; padding:8px 10px; font-size:.82rem; text-transform:uppercase; letter-spacing:.4px; }}
  td {{ padding:8px 10px; border-top:1px solid #eef0f4; font-size:.92rem; vertical-align:top; }}
  .disclaimer {{ background:#fffbe6; border:1px solid #eadfa0; padding:10px 14px; border-radius:8px; font-size:.82rem; color:#665c1e; margin-top:26px; }}
</style></head>
<body>
<header><h1>PaperEngine — revision comparison</h1></header>
<main>
  <div class="scores">
    <div class="score">{s['before']}<small>before</small></div>
    <div class="delta">&rarr; {arrow}{abs(s['delta'])}</div>
    <div class="score">{s['after']}<small>after</small></div>
  </div>
  <div class="chips">
    <span class="chip-fixed">{s['fixed']} fixed</span>
    <span class="chip-open">{s['still_open']} still open</span>
    <span class="chip-new">{s['new']} new</span>
  </div>

  <h2>Fixed since the last version</h2>
  <table><tr><th>Severity</th><th>Finding</th><th></th></tr>
  {rows(cmp.fixed, show_action=False)}
  </table>

  <h2>Still open — work on these next</h2>
  <table><tr><th>Severity</th><th>Finding</th><th>How to fix</th></tr>
  {rows(cmp.still_open, show_action=True)}
  </table>

  <h2>New in this revision (check carefully)</h2>
  <table><tr><th>Severity</th><th>Finding</th><th></th></tr>
  {rows(cmp.new, show_action=False)}
  </table>

  <div class="disclaimer"><b>Honest limits:</b> the readiness score is informational,
  never a prediction of acceptance. Findings match across revisions by category and
  normalized title, so wording-level duplicates may appear as "new".</div>
</main>
</body></html>"""


__all__ = ["Comparison", "compare", "render_console", "render_html"]
