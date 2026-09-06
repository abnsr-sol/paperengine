"""CLI: python -m papercheck paper.docx [--standard national] [--venue ugc_care] [--corpus DIR] [--online]

Runs every registered check engine and renders the report.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from .batch import render_console_table, scan_folder, write_csv
from .checks import ALL_ENGINES, CheckContext
from .compare import compare as compare_reports
from .compare import render_console as render_compare_console
from .compare import render_html as render_compare_html
from .fixplan import render_fix_plan
from . import rwdb
from .ingestion import Document, PdfExtractionError, UnsupportedFormatError, load_document
from .report import render_console, render_html, render_markdown
from .risk import RiskReport
from .venues import PRESETS, describe, get_rules, list_venues


def _load_corpus(path: str) -> List[Document]:
    docs: List[Document] = []
    if not os.path.isdir(path):
        print(f"Warning: corpus path '{path}' is not a directory — skipping corpus checks.", file=sys.stderr)
        return docs
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        ext = os.path.splitext(name)[1].lower()
        if ext not in (".docx", ".txt", ".md", ".markdown", ".tex", ".pdf"):
            continue
        try:
            docs.append(load_document(full))
        except (UnsupportedFormatError, PdfExtractionError) as exc:
            print(f"Warning: skipping corpus file {name}: {exc}", file=sys.stderr)
    return docs


def _venue_standard(venue: str) -> Optional[str]:
    key = venue.lower().replace("-", "_").replace(" ", "_") if venue else "generic"
    preset = PRESETS.get(key)
    if preset:
        return preset.get("standard", "international")
    return None


def build_report(path: str, venue: str, venue_json: Optional[str], corpus: Optional[str],
                 online: bool, mailto: str, max_online: int,
                 standard: Optional[str] = None) -> RiskReport:
    doc = load_document(path)
    rules = get_rules(venue, venue_json)
    std = standard or _venue_standard(venue) or rules.get("standard", "international")
    ctx = CheckContext(
        venue=describe(venue),
        rules=rules,
        corpus=_load_corpus(corpus) if corpus else [],
        online=online,
        mailto=mailto,
        max_online_checks=max_online,
    )
    report = RiskReport(document_name=doc.name, venue=describe(venue))
    report.stats = {
        "words": f"{doc.word_count:,}",
        "estimated pages": f"{doc.page_estimate:.1f} (500 words/page)",
        "sentences": len(_sentence_count(doc)),
        "sections": len(doc.sections),
        "figures": doc.figures,
        "tables": doc.tables,
        "references parsed": len(doc.references),
        "file type": doc.file_type,
        "standard": "National (Indian)" if std == "national" else "International",
    }
    if doc.metadata:
        report.stats["doc metadata"] = ", ".join(f"{k}={v}" for k, v in doc.metadata.items())
    for engine in ALL_ENGINES:
        report.extend(engine(doc, ctx))
    return report


def _sentence_count(doc: Document) -> List[str]:
    from .metrics import sentences

    return sentences(doc.text)


def _utf8_streams() -> None:
    """Windows consoles default to cp1252 and crash on '≥', '—', math glyphs.
    Force UTF-8 with lossy fallback so reports always print."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _utf8_streams()
    parser = argparse.ArgumentParser(
        prog="papercheck",
        description="Pre-submission rejection-risk engine for academic manuscripts.",
    )
    parser.add_argument("file", nargs="?", help="manuscript: .docx, .txt, .md, .markdown, .tex, or .pdf")
    parser.add_argument("--standard", choices=["international", "national"], default=None,
                        help="checking standard: international (IEEE/Elsevier/ACM...) or national (UGC/AICTE/NAAC Indian rules)")
    parser.add_argument("--venue", default="generic",
                        help="venue ruleset (see --list-venues): ieee_conference, ugc_care, scopus_indian, ...")
    parser.add_argument("--venue-json", default=None,
                        help="JSON file with exact venue rules (overrides presets)")
    parser.add_argument("--corpus", default=None,
                        help="directory of known/already-published papers for overlap checks")
    parser.add_argument("--online", action="store_true",
                        help="enable online lookups (Crossref + OpenAlex: reference resolution, retraction flags, venue scope) — requires network")
    parser.add_argument("--openalex-key", default=None,
                        help="OpenAlex API key (or set OPENALEX_API_KEY env var) — raises rate limits; free at openalex.org")
    parser.add_argument("--update-rwdb", action="store_true",
                        help="download/refresh the Retraction Watch database cache and exit")
    parser.add_argument("--gui", action="store_true",
                        help="launch the local drag-and-drop web interface (http://localhost:8765) and exit when closed")
    parser.add_argument("--port", type=int, default=8765,
                        help="port for --gui (default 8765)")
    parser.add_argument("--mailto", default="",
                        help="contact email for the Crossref polite pool (recommended with --online)")
    parser.add_argument("--max-online-checks", type=int, default=10,
                        help="cap on network lookups per run (default 10)")
    parser.add_argument("--list-venues", action="store_true",
                        help="list available venue presets by standard and exit")
    parser.add_argument("--batch", default=None,
                        help="scan every supported manuscript in this folder and exit (use with --format csv)")
    parser.add_argument("--compare", default=None, metavar="REVISED",
                        help="compare this ORIGINAL against REVISED: shows fixed / still-open / new findings (use --format html for a rich report)")
    parser.add_argument("--format", choices=["console", "markdown", "html", "fixplan", "csv", "similarity", "similarity-html"], default="console")
    parser.add_argument("--out", default=None, help="write report to this file (default: print to stdout)")
    args = parser.parse_args(argv)

    if args.openalex_key:
        os.environ["OPENALEX_API_KEY"] = args.openalex_key

    if args.gui:
        from .webui import serve
        serve(port=args.port, open_browser=True)
        return 0

    if args.update_rwdb:
        ok = rwdb.download_db(rwdb.default_cache_path())
        if ok:
            n = len(rwdb.load_db(rwdb.default_cache_path()))
            print(f"Retraction Watch DB cached: {n} entries at {rwdb.default_cache_path()}")
            return 0
        print("RWDB download failed (offline?); the built-in seed list remains active.", file=sys.stderr)
        return 2

    if args.list_venues:
        groups = list_venues()
        for std, names in groups.items():
            label = "NATIONAL (Indian)" if std == "national" else "INTERNATIONAL"
            print(f"{label}:")
            for name in names:
                print(f"  {name:<22} {describe(name)}")
        return 0

    # Batch mode: scan a folder, write CSV / print table, exit.
    if args.batch:
        rows = scan_folder(args.batch, args.venue, args.online, args.mailto,
                           args.max_online_checks)
        if args.format == "csv":
            out_path = args.out or "papercheck_batch.csv"
            write_csv(rows, out_path)
            print(f"Batch CSV written to {out_path} ({len(rows)} papers)")
        else:
            print(render_console_table(rows))
        return 0

    # Before/after comparison mode.
    if args.compare:
        if not args.file:
            parser.error("--compare also needs the ORIGINAL manuscript as the main file argument")
        if not os.path.exists(args.compare):
            print(f"Error: revised file not found: {args.compare}", file=sys.stderr)
            return 2
        try:
            cmp = compare_reports(args.file, args.compare, venue=args.venue,
                                  standard=args.standard or "international")
        except (UnsupportedFormatError, PdfExtractionError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        output = render_compare_html(cmp) if args.format == "html" else render_compare_console(cmp)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                print(output, file=fh)
            print(f"Comparison written to {args.out}")
        else:
            print(output)
        return 0

    # Similarity detail report: WHAT matched, side by side (needs --corpus).
    if args.format in ("similarity", "similarity-html"):
        if not args.file:
            parser.error("the following arguments are required: file")
        if not args.corpus:
            parser.error("--format similarity requires --corpus DIRECTORY (prior documents to compare against)")
        from .similarity_detail import analyze
        from .similarity_detail import render_html as _sim_html
        from .similarity_detail import render_markdown as _sim_md
        try:
            doc = load_document(args.file)
            rep = analyze(doc, _load_corpus(args.corpus))
        except (UnsupportedFormatError, PdfExtractionError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        output = _sim_html(rep) if args.format == "similarity-html" else _sim_md(rep)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                print(output, file=fh)
            print(f"Similarity detail written to {args.out}")
        else:
            print(output)
        return 0

    if not args.file:
        parser.error("the following arguments are required: file (or use --list-venues)")

    # Validate venue belongs to the requested standard (informational).
    if args.standard:
        vs = _venue_standard(args.venue)
        if vs and vs != args.standard:
            print(f"Warning: venue '{args.venue}' is a {vs} preset, but --standard {args.standard} was given.",
                  file=sys.stderr)

    try:
        report = build_report(
            args.file, args.venue, args.venue_json, args.corpus,
            args.online, args.mailto, args.max_online_checks, args.standard,
        )
    except (UnsupportedFormatError, PdfExtractionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 2

    if args.format == "markdown":
        output = render_markdown(report)
    elif args.format == "html":
        output = render_html(report)
    elif args.format == "fixplan":
        output = render_fix_plan(report)
    else:
        output = render_console(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            print(output, file=fh)
        print(f"Report written to {args.out}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
