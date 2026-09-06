"""Document ingestion: DOCX (stdlib), TXT/Markdown, and PDF (optional pypdf).

DOCX parsing uses the standard library only: a .docx is a zip of XML, so we
extract paragraph text plus run-level font names/sizes to support font and
formatting checks. PDF extraction requires `pypdf`; without it, PDF files are
reported with a clear message instead of silently producing empty text.
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
    r"^(?:(?:\d+(?:\.\d+){0,3})\s*[.)]?\s+|"
    r"(abstract|introduction|background|related work|methodology?|methods?|"
    r"experiments?|evaluation|results?|discussion|conclusion|conclusions|"
    r"references|acknowledg?ments?|appendix|limitations|future work|"
    r"threats? to validity|data availability|availability of data|"
    r"author contributions|conflict of interest|funding)\b[\s:]*$)",
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

def _load_pdf(path: str) -> Document:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise PdfExtractionError(
            "PDF extraction requires the optional 'pypdf' package. "
            "Install it with: pip install pypdf  (or convert the PDF to DOCX/TXT)"
        )

    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    doc = Document(
        path=path,
        name=os.path.basename(path),
        file_type="pdf",
        text=text,
        paragraphs=paragraphs,
        figures=len(re.findall(r"(?i)\bfigure\s+\d+", text)),
        tables=len(re.findall(r"(?i)\btable\s+\d+", text)),
        metadata={"pages": str(len(reader.pages))},
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
            heading_text = first
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
    """Split a references block into individual entries."""
    entries = re.split(r"\n(?=\[\d+\]|\d+[.)]\s+[A-Z])", text.strip())
    out = []
    for e in entries:
        e = e.strip()
        if len(e) > 15:
            out.append(e)
    return out