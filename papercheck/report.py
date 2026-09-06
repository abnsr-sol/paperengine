"""Report rendering: console, Markdown, and standalone HTML.

The report structure follows the product design from the research:
a Risk | Finding | Evidence | Confidence | Action table, per-category
breakdown, readiness score, and an explicit limitations disclaimer.
"""

from __future__ import annotations

import html
from typing import List

from .risk import Finding, RiskReport, fmt_confidence

SEVERITY_COLORS = {
    "Critical": "\033[1;31m",
    "High": "\033[1;33m",
    "Medium": "\033[0;33m",
    "Low": "\033[0;36m",
    "Info": "\033[0;37m",
}
RESET = "\033[0m"


def _row_md(f: Finding) -> str:
    return (
        f"| {f.severity.value} | {f.title} | {f.evidence} | "
        f"{fmt_confidence(f.confidence)} | {f.action} |"
    )


def render_markdown(report: RiskReport) -> str:
    lines: List[str] = []
    lines.append(f"# PaperCheck Risk Report — {report.document_name}")
    lines.append("")
    lines.append(f"- **Venue:** {report.venue}")
    lines.append(f"- **Readiness score:** {report.readiness_score}/100  *(informational, not a verdict)*")
    counts = report.counts()
    lines.append(
        "- **Findings:** "
        + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -report.by_severity()[0].severity.weight if False else 0))
        if counts
        else "- **Findings:** none"
    )
    lines.append("")
    if report.stats:
        lines.append("## Manuscript stats")
        lines.append("")
        for k, v in report.stats.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.append("## Findings (sorted by severity)")
    lines.append("")
    lines.append("| Risk | Finding | Evidence | Confidence | Action |")
    lines.append("|------|---------|----------|------------|--------|")
    for f in report.by_severity():
        lines.append(_row_md(f))
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Similarity/overlap is a risk signal, **not plagiarism** — overlap must be interpreted by a human editor."
    )
    lines.append(
        "- AI-risk scores are probabilistic stylometry, **not proof of AI authorship**; human technical and "
        "non-native writing is frequently misflagged."
    )
    lines.append(
        "- Venue rules are typical published limits; always confirm against the venue's own author guidelines."
    )
    lines.append(
        "- Grammar checks are heuristic; run a real editor (LanguageTool/Grammarly/Paperpal) for a final pass."
    )
    lines.append("")
    return "\n".join(lines)


def render_html(report: RiskReport) -> str:
    counts = report.counts()
    rows = []
    for f in report.by_severity():
        rows.append(
            f"<tr class='sev-{f.severity.value.lower()}'>"
            f"<td><span class='badge'>{f.severity.value}</span></td>"
            f"<td><strong>{html.escape(f.title)}</strong><br><small>{html.escape(f.location)}</small></td>"
            f"<td>{html.escape(f.evidence)}</td>"
            f"<td>{fmt_confidence(f.confidence)}</td>"
            f"<td>{html.escape(f.action)}</td></tr>"
        )
    stats_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in report.stats.items()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PaperCheck Report — {html.escape(report.document_name)}</title>
<style>
 body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 2rem auto; max-width: 960px; color: #1a1a2e; }}
 h1 {{ color: #16213e; }} .score {{ font-size: 2.2rem; font-weight: 700; color: #0f3460; }}
 table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem; }}
 th, td {{ border: 1px solid #d5d5e5; padding: .55rem .65rem; text-align: left; vertical-align: top; }}
 th {{ background: #16213e; color: #fff; }}
 .sev-critical {{ background: #fdecec; }} .sev-high {{ background: #fdf6e3; }}
 .sev-medium {{ background: #fcf8ef; }} .sev-low {{ background: #f4f6fb; }}
 .badge {{ display: inline-block; padding: .12rem .5rem; border-radius: 999px; font-size: .75rem; font-weight: 700; }}
 .sev-critical .badge {{ background: #d64541; color: #fff; }}
 .sev-high .badge {{ background: #e67e22; color: #fff; }}
 .sev-medium .badge {{ background: #f39c12; color: #fff; }}
 .sev-low .badge {{ background: #16a085; color: #fff; }}
 .sev-info .badge {{ background: #7f8c8d; color: #fff; }}
 .limitations {{ background: #f4f6fb; border-left: 4px solid #0f3460; padding: 1rem 1.2rem; margin-top: 2rem; }}
 .stats {{ width: auto; }}
</style>
</head>
<body>
<h1>PaperCheck Risk Report</h1>
<p><strong>Document:</strong> {html.escape(report.document_name)} &nbsp;·&nbsp;
<strong>Venue:</strong> {html.escape(report.venue)}</p>
<div class="score">{report.readiness_score}<span style="font-size:1rem;color:#666">/100 readiness</span></div>
<p><em>Informational aggregate, not a verdict.</em></p>
<h2>Findings ({len(report.findings)})</h2>
<table>
<tr><th>Risk</th><th>Finding</th><th>Evidence</th><th>Confidence</th><th>Recommended action</th></tr>
{''.join(rows) or '<tr><td colspan="5">No findings — the manuscript passes the automated checks.</td></tr>'}
</table>
<h2>Manuscript stats</h2>
<table class="stats">
<tr><th>Metric</th><th>Value</th></tr>
{stats_rows}
</table>
<div class="limitations">
<strong>Limitations</strong>
<ul>
<li>Similarity/overlap is a risk signal, <b>not plagiarism</b> — overlap needs human editorial interpretation.</li>
<li>AI-risk scores are probabilistic stylometry, <b>not proof of AI authorship</b>; human technical/non-native writing is often misflagged.</li>
<li>Venue rules are typical published limits; confirm against the venue's own author guidelines.</li>
<li>Grammar checks are heuristic — run a real editor for the final pass.</li>
</ul>
</div>
</body>
</html>"""


def render_console(report: RiskReport) -> str:
    lines: List[str] = []
    lines.append(f"PaperCheck - {report.document_name}  (venue: {report.venue})")
    lines.append(f"Readiness: {report.readiness_score}/100   Findings: {len(report.findings)}")
    counts = report.counts()
    if counts:
        lines.append("  " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    lines.append("")
    for f in report.by_severity():
        color = SEVERITY_COLORS.get(f.severity.value, "")
        lines.append(f"{color}[{f.severity.value}]{RESET} {f.title}")
        if f.detail:
            lines.append(f"   detail   : {f.detail}")
        lines.append(f"   evidence : {f.evidence}")
        lines.append(f"   confidence: {fmt_confidence(f.confidence)}")
        lines.append(f"   action   : {f.action}")
        if f.location:
            lines.append(f"   location : {f.location}")
        lines.append("")
    lines.append("DISCLAIMERS: overlap is a signal, not plagiarism; AI-risk is probabilistic, not proof;")
    lines.append("venue rules are typical limits - confirm with the venue.")
    return "\n".join(lines)