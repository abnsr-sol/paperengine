"""Document ingestion: DOCX (stdlib), TXT/Markdown, and PDF (optional pypdf).

DOCX parsing uses the standard library only: a .docx is a zip of XML, so we
extract paragraph text plus run-level font names/sizes to support font and
formatting checks. PDF extraction requires `pypdf`; without it, PDF files are
reported with a clear message instead of silently producing empty text.

PDF extraction is **layout-aware**: naive extractors read glyph operators in
stream order, which interleaves the two columns of IEEE/ACM papers and
corrupts every downstream check (sentences, headings, statistics). Here each
page's words are positioned via pypdf's word boxes, rows are reconstructed,
full-width bands (titles/abstracts) are separated from column bands, and text
is emitted in true reading order. Typographic ligatures (fi/fl/ffi), soft
hyphens, and end-of-line hyphenation are normalized afterwards.
"""

from __future__ import annotations

import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

W_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}

_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+)?"                       # markdown ATX headings (## Abstract)
    r"(?:(?:\d+(?:\.\d+){0,3})\s*[.)]?\s+|"
    r"(abstract|introduction|background|related work|methodology?|methods?|"
    r"experiments?|evaluation|results?|discussion|conclusion|conclusions|"
    r"references|acknowledg?ments?|appendix|limitations|future work|"
    r"threats? to validity|data availability|availability of data|"
    r"author contributions|conflict of interest|conflicts of interest|funding)\b[\s:]*$)",
    re.IGNORECASE,
)

# IEEE/Elsevier front-matter labels that share a line with their content:
# "Abstract—Deepfake detection ...", "Keywords—deepfake, ...", "Index Terms—...".
_INLINE_HEADING_RE = re.compile(
    r"^(abstract|keywords|index terms)\b\s*[\u2014\u2013\u2012\u2010\-:]\s*(.*)$",
    re.IGNORECASE,
)


@dataclass
class Section:
    heading: str
    level: int
    body: str
    start_index: int  # character offset in full text


@dataclass
class Document:
    path: str
    name: str
    file_type: str
    text: str
    paragraphs: List[str] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    figures: int = 0
    tables: int = 0
    font_warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)
    extraction_notes: List[str] = field(default_factory=list)
    cite_field_count: int = 0  # unrendered Word/Zotero citation-field placeholders

    # --- convenience properties -------------------------------------------------
    @property
    def word_count(self) -> int:
        from .metrics import word_count

        return word_count(self.text)

    @property
    def page_estimate(self) -> float:
        """Rough estimate: ~500 words per typeset page. Use venue rules for truth."""
        return max(1.0, self.word_count / 500.0)

    @property
    def body_text(self) -> str:
        """Full text excluding the references block.

        References are full of 'vol. 5', 'et al.', DOIs etc. which pollute
        sentence-level and style statistics — analyse the body only.
        """
        for s in self.sections:
            if normalize_heading(s.heading).startswith("reference"):
                return self.text[: s.start_index]
        return self.text


class UnsupportedFormatError(ValueError):
    pass


class PdfExtractionError(RuntimeError):
    pass


def load_document(path: str) -> Document:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _load_docx(path)
    if ext in (".txt", ".md", ".markdown", ".tex"):
        return _load_text(path)
    if ext == ".pdf":
        return _load_pdf(path)
    raise UnsupportedFormatError(
        f"Unsupported file type '{ext}'. Supported: .docx, .txt, .md, .markdown, .tex, .pdf"
    )


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------

def _load_docx(path: str) -> Document:
    text_parts: List[str] = []
    paragraphs: List[str] = []
    size_counts: Dict[float, int] = {}
    family_counts: Dict[str, int] = {}
    figure_count = 0
    table_count = 0
    notes: List[str] = []
    metadata: Dict[str, str] = {}

    try:
        with zipfile.ZipFile(path) as zf:
            core_names = [n for n in zf.namelist() if n.startswith("docProps/core.xml")]
            if core_names:
                try:
                    root = ET.fromstring(zf.read(core_names[0]))
                    for child in root:
                        tag = child.tag.split("}")[-1]
                        if tag in ("title", "creator", "lastModifiedBy", "created", "modified") and child.text:
                            metadata[tag] = child.text
                except ET.ParseError:
                    pass

            if "word/document.xml" not in zf.namelist():
                raise PdfExtractionError(f"{path} does not contain word/document.xml (not a valid .docx?)")

            root = ET.fromstring(zf.read("word/document.xml"))
            body = root.find("w:body", W_NS)
            if body is None:
                body = root

            for para in body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                texts: List[str] = []
                for r in para.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r"):
                    t = "".join(
                        el.text or ""
                        for el in r.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                    )
                    if t:
                        texts.append(t)
                    sz = r.find(".//w:sz", W_NS)
                    rfonts = r.find(".//w:rFonts", W_NS)
                    size_pt = int(sz.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")) / 2.0 if sz is not None else None
                    font_name = rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii") if rfonts is not None else None
                    if size_pt:
                        size_counts[size_pt] = size_counts.get(size_pt, 0) + len(t)
                    if font_name:
                        family_counts[font_name] = family_counts.get(font_name, 0) + len(t)
                # drawings / picts count as figures
                figure_count += len(list(para.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline")))
                figure_count += len(list(para.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}anchor")))
                ptext = "".join(texts).strip()
                if ptext:
                    paragraphs.append(ptext)
                    text_parts.append(ptext)

            table_count = len(list(body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl")))
    except zipfile.BadZipFile:
        raise PdfExtractionError(f"{path} is not a valid zip/.docx file")
    except ET.ParseError as exc:
        raise PdfExtractionError(f"Could not parse {path}: {exc}")

    # Font/size consistency notes (DOCX run properties, tracked separately so a
    # family mix is not conflated with a size mix)
    def _variants(counter, fmt):
        items = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
        if len(items) < 2:
            return None
        dom, dom_cnt = items[0]
        others = [k for k, c in items[1:] if c / max(1, dom_cnt) > 0.02]
        if not others:
            return None
        return fmt(dom), [fmt(o) for o in others[:5]]

    sz = _variants(size_counts, lambda v: f"{v:g}pt")
    if sz:
        notes.append(
            f"Multiple font sizes in DOCX runs: dominant {sz[0]} but also "
            + ", ".join(sz[1])
            + " — normalize to the venue template's body size."
        )
    fam = _variants(family_counts, str)
    if fam:
        notes.append(
            f"Mixed font families in DOCX runs: dominant '{fam[0]}' but also "
            + ", ".join(f"'{f}'" for f in fam[1])
            + " — normalize to the venue template."
        )

    text = "\n".join(text_parts)
    doc = Document(
        path=path,
        name=os.path.basename(path),
        file_type="docx",
        text=text,
        paragraphs=paragraphs,
        figures=figure_count,
        tables=table_count,
        font_warnings=notes,
        metadata=metadata,
    )
    _annotate_structure(doc)
    return doc


# --------------------------------------------------------------------------
# Plain text / Markdown / LaTeX
# --------------------------------------------------------------------------

def _load_text(path: str) -> Document:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    text = "\n".join(paragraphs)

    # Count markdown figures/tables
    figures = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", raw)) + len(re.findall(r"\\includegraphics", raw))
    tables = len(re.findall(r"^\s*\|.*\|\s*$", raw, re.MULTILINE))

    # LaTeX: strip commands/braces crudely for word counting
    if path.lower().endswith(".tex"):
        plain = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", raw)
        plain = re.sub(r"\\(?:cite|ref|label|textbf|textit|emph|section|subsection|paragraph)\{[^}]*\}", " ", plain)
        plain = re.sub(r"\\[a-zA-Z]+", " ", plain)
        paragraphs = [p.strip() for p in plain.splitlines() if p.strip()]
        text = "\n".join(paragraphs)

    doc = Document(
        path=path,
        name=os.path.basename(path),
        file_type=os.path.splitext(path)[1].lstrip(".").lower(),
        text=text,
        paragraphs=paragraphs,
        figures=figures,
        tables=tables,
    )
    _annotate_structure(doc)
    return doc


# --------------------------------------------------------------------------
# PDF (optional pypdf)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# PDF: layout-aware extraction
# --------------------------------------------------------------------------

_LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
}
_INVISIBLES = ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\xad")


def _normalize_pdf_text(text: str) -> str:
    """Repair the typographic damage extractors leave behind.

    - ligatures (fi/fl/ffi...) -> plain ASCII, so spelling/word metrics see
      real words instead of U+FB01 glyphs
    - zero-width characters, soft hyphens, U+FFFD replacement chars removed
    - end-of-line hyphenation rejoined: 'sig-\\nificant' -> 'significant'
    """
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    for ch in _INVISIBLES:
        text = text.replace(ch, "")
    text = text.replace("\u00a0", " ").replace("\ufffd", "")
    # de-hyphenate: hyphen at end of line + lowercase continuation
    text = re.sub(r"(\w)-\s*\n\s*([a-z])", r"\1\2", text)
    return text


def _rows_from_frags(frags: List[dict]) -> List[List[dict]]:
    """Group positioned text fragments into visual rows (4pt vertical tolerance)."""
    if not frags:
        return []
    fs = sorted(frags, key=lambda f: (f["top"], f["x0"]))
    rows: List[List[dict]] = []
    cur = [fs[0]]
    for f in fs[1:]:
        if abs(f["top"] - cur[-1]["top"]) <= 4.0:
            cur.append(f)
        else:
            rows.append(cur)
            cur = [f]
    rows.append(cur)
    return rows


def _split_row_runs(row: List[dict], gap: float = 15.0) -> List[List[dict]]:
    """Split a visual row into horizontal runs at large x-gaps (the column gutter).

    Fragment end-x is estimated as x0 + len(text) * size * 0.5 (average glyph
    width); real gutters are far wider than any within-sentence space.
    """
    runs: List[List[dict]] = []
    cur = [row[0]]
    for f in row[1:]:
        prev = cur[-1]
        prev_end = prev["x0"] + len(prev["text"]) * max(prev["size"], 1.0) * 0.5
        if f["x0"] - prev_end > gap:
            runs.append(cur)
            cur = [f]
        else:
            cur.append(f)
    runs.append(cur)
    return runs


def _page_text_layout(page) -> Tuple[str, str]:
    """Extract one page's text in reading order.

    Returns (text, layout) where layout is 'two-column' or 'single-column'.
    Uses pypdf's visitor_text hook to get the x/y position of every text-show
    operation, groups fragments into visual rows, splits rows into horizontal
    runs at the column gutter, then classifies runs: a wide run crossing the
    center is a full-width band (title/abstract); otherwise it belongs to the
    left or right column. Two-column pages emit top full-width bands first,
    then the entire left column, then the right column.
    """
    frags: List[dict] = []

    def _visit(text: str, cm, tm, font_dict, font_size) -> None:
        t = text.strip()
        if not t:
            return
        try:
            x = float(tm[4])
            y = float(tm[5])
            size = float(font_size) if font_size and float(font_size) > 0 else 10.0
        except (TypeError, ValueError, IndexError):
            return
        frags.append({"x0": x, "y": y, "text": t, "size": size})

    try:
        page.extract_text(visitor_text=_visit)
    except Exception:
        try:
            return (page.extract_text() or "", "single-column")
        except Exception:
            return ("", "single-column")
    if not frags:
        return ("", "single-column")

    y_max = max(f["y"] for f in frags)
    for f in frags:
        f["top"] = y_max - f["y"]  # PDF y grows upward; top-down reading order

    page_h = max(f["top"] for f in frags) or 1.0
    # Running heads/footers are NOT filtered here: a blanket top/bottom band cut
    # silently eats the title of short pages (the first page of a paper is
    # mostly title). They are removed cross-page in _load_pdf via
    # _strip_repeated_lines, which drops only lines repeated on most pages.
    body = frags

    left_x = min(f["x0"] for f in body)
    right_x = max(
        f["x0"] + len(f["text"]) * max(f["size"], 1.0) * 0.5 for f in body
    )
    width = max(1.0, right_x - left_x)
    mid_lo = left_x + width * 0.42
    mid_hi = left_x + width * 0.58
    gutter_mid = (mid_lo + mid_hi) / 2.0

    def _run_text(run: List[dict]) -> str:
        return " ".join(f["text"] for f in sorted(run, key=lambda f: f["x0"]))

    def _classify(run: List[dict]) -> str:
        x0 = min(f["x0"] for f in run)
        x1 = max(f["x0"] + len(f["text"]) * max(f["size"], 1.0) * 0.5 for f in run)
        if x0 < mid_lo and x1 > mid_hi and (x1 - x0) > width * 0.6:
            return "full"
        return "left" if (x0 + x1) / 2.0 < gutter_mid else "right"

    rows = _rows_from_frags(body)
    full_runs, left_frags, right_frags = [], [], []
    for row in rows:
        for run in _split_row_runs(row):
            kind = _classify(run)
            if kind == "full":
                full_runs.append(run)
            elif kind == "left":
                left_frags.append(run)
            else:
                right_frags.append(run)

    n_frag = len(full_runs) + len(left_frags) + len(right_frags)
    two_col = (
        bool(left_frags) and bool(right_frags)
        and len(left_frags) / n_frag >= 0.25
        and len(right_frags) / n_frag >= 0.25
    )
    if not two_col:
        everything = [(min(f["top"] for f in r), r) for r in full_runs + left_frags + right_frags]
        everything.sort(key=lambda t: t[0])
        return ("\n".join(_run_text(r) for _, r in everything), "single-column")

    # full-width bands near the top (title/abstract) come first in y order
    top_full = [r for r in full_runs if min(f["top"] for f in r) < page_h * 0.35]
    rest_full = [r for r in full_runs if r not in top_full]
    lines = [_run_text(r) for r in sorted(top_full, key=lambda r: min(f["top"] for f in r))]
    lines += [_run_text(r) for r in left_frags]
    lines += [_run_text(r) for r in right_frags]
    lines += [_run_text(r) for r in rest_full]
    return ("\n".join(lines), "two-column")


def _strip_repeated_lines(pages: List[str], min_pages: int = 3) -> List[str]:
    """Remove running heads/footers across pages.

    A line is a running head only if it appears (identically) on >=60% of
    pages AND the document has at least `min_pages` pages — single-page and
    short documents keep every line, so titles are never lost.
    """
    if len(pages) < min_pages:
        return pages
    line_pages: Dict[str, set] = {}
    for i, page in enumerate(pages):
        for line in set(page.splitlines()):
            t = line.strip()
            if t:
                line_pages.setdefault(t, set()).add(i)
    cutoff = 0.6 * len(pages)
    repeat = {t for t, ps in line_pages.items() if len(ps) >= cutoff}
    if not repeat:
        return pages
    out = []
    for page in pages:
        out.append("\n".join(l for l in page.splitlines() if l.strip() not in repeat))
    return out


def _load_pdf(path: str) -> Document:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise PdfExtractionError(
            "PDF extraction requires the optional 'pypdf' package. "
            "Install it with: pip install pypdf  (or convert the PDF to DOCX/TXT)"
        )

    reader = PdfReader(path)
    pages: List[str] = []
    layouts = set()
    for page in reader.pages:
        page_text, layout = _page_text_layout(page)
        layouts.add(layout)
        pages.append(page_text)
    pages = _strip_repeated_lines(pages)
    text = _normalize_pdf_text("\n".join(pages))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    notes = []
    if "two-column" in layouts:
        notes.append(
            "Two-column PDF layout detected; reading order was reconstructed "
            "(title/abstract bands first, then each column)."
        )
    doc = Document(
        path=path,
        name=os.path.basename(path),
        file_type="pdf",
        text=text,
        paragraphs=paragraphs,
        figures=len(re.findall(r"(?i)\bfigure\s+\d+", text)),
        tables=len(re.findall(r"(?i)\btable\s+\d+", text)),
        metadata={"pages": str(len(reader.pages))},
        extraction_notes=notes,
    )
    _annotate_structure(doc)
    return doc


# --------------------------------------------------------------------------
# Structural annotation (shared)
# --------------------------------------------------------------------------

_CITE_FIELD_RE = re.compile(r"\ue200(?:file)?cite\ue202|\b(?:CITATION|ADDIN ZOTERO|Mendeley|EndNote)\b", re.IGNORECASE)


def normalize_heading(heading: str) -> str:
    """'1. Introduction' -> 'introduction'; '3.2 Proposed Model' -> 'proposed model'."""
    h = re.sub(r"^\s*\d+(?:\.\d+)*\s*[.)]?\s*", "", heading.strip()).lower()
    return h.strip(":")


def _annotate_structure(doc: Document) -> None:
    """Find headings / sections, the references block, and heading numbering gaps.

    Handles standalone heading paragraphs, 'heading\nbody' paragraphs (common in
    plain-text submissions), and inline front-matter labels such as IEEE-style
    'Abstract—<text>' / 'Keywords—<terms>' that share a line with their content.
    """
    sections: List[Section] = []
    current: Optional[Section] = None
    offset = 0

    for para in doc.paragraphs:
        lines = para.strip().splitlines()
        first = lines[0].strip() if lines else ""
        heading_text: Optional[str] = None
        inline_body = ""
        m = _HEADING_RE.match(first)
        if m is not None and len(first) < 120:
            # strip markdown ATX hashes so sections match as 'Abstract', not '## Abstract'
            heading_text = re.sub(r"^#{1,6}\s+", "", first)
        else:
            im = _INLINE_HEADING_RE.match(first)
            if im is not None:
                heading_text = im.group(1)
                inline_body = (im.group(2) or "").strip()
        if heading_text:
            text = heading_text
            level = 2 if re.match(r"^\d+\.\d+", text) else 1
            rest = "\n".join(l.strip() for l in lines[1:]).strip()
            body = "\n".join(p for p in (inline_body, rest) if p)
            current = Section(heading=text, level=level, body=body, start_index=offset)
            sections.append(current)
        else:
            if current is not None:
                current.body += ("\n" if current.body else "") + para
        offset += len(para) + 1

    doc.sections = sections

    # References block
    for idx, sec in enumerate(sections):
        if re.match(r"^(references|bibliography)\b", sec.heading, re.IGNORECASE):
            ref_text = sec.body + "\n" + "\n".join(
                s.body for s in sections[idx + 1 :] if s.level >= 2
            )
            doc.references = _split_references(ref_text)
            break
    if not doc.references and "references" in doc.text.lower():
        tail = doc.text[doc.text.lower().rfind("references"):]
        doc.references = _split_references(tail)

    # Unrendered citation fields (Word/Zotero placeholders) — these are real
    # in-text citations structurally, but they render as blank/garbage text.
    doc.cite_field_count = len(_CITE_FIELD_RE.findall(doc.text))

    # Heading numbering gaps within a subsection family (e.g. 2.1, 2.2, 2.4).
    # Each parent resets its own counter, so '6.9 → 8.1' is not flagged when
    # section 7 simply has no subsections.
    family_last: Dict[str, Section] = {}
    for sec in sections:
        mn = re.match(r"^(\d+(?:\.\d+)*)\.(\d+)\b", sec.heading)
        if not mn:
            continue
        family, sub = mn.group(1), int(mn.group(2))
        prev = family_last.get(family)
        if prev is not None:
            sub_prev = int(re.match(r"^(\d+(?:\.\d+)*)\.(\d+)\b", prev.heading).group(2))
            if sub != sub_prev + 1:
                doc.extraction_notes.append(
                    f"Possible section-numbering gap: '{prev.heading}' is followed "
                    f"by '{sec.heading}' (expected {family}.{sub_prev + 1})"
                )
        family_last[family] = sec


def _split_references(text: str) -> List[str]:
    """Split a references block into individual entries.

    Handles: [1] Author..., 1. Author..., 1) Author..., Author (Year)..., and
    Author et al. (Year)... formats.
    """
    entries = re.split(
        r"\n(?="
        r"[\[\d+]"          # [1] numbered
        r"|\d+[.)]\s+[A-Z]"  # 1. Author or 1) Author
        r"|\w+\s+et\s+al\." # Author et al.
        r"|\w+\s+\(\d{4}\)" # Author (2024)
        r"|\w+,\s+\w+\s+\(\d{4}\)" # Author, A. (2024)
        r")", text.strip())
    out = []
    for e in entries:
        e = e.strip()
        if len(e) > 15:
            out.append(e)
    return out