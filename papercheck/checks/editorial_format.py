"""Editorial format engine: line numbers, running head, page numbers, template compliance, wrong-section submission."""
from __future__ import annotations
import re
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity


def _f(sev, title, detail, evidence, conf, action):
    return Finding("Editorial Format", sev, title, detail, evidence, action, conf)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.text or ""
    if not text:
        return []
    low = text.lower()
    out = []
    is_tex = doc.file_type == "tex" or r"\documentclass" in text
    # line numbers for review
    if is_tex and not re.search(r"\\linenumbers|lineno", low):
        out.append(_f(Severity.LOW, "No line numbers in LaTeX source", "Most journals require continuous line numbers for review (lineno package).",
                      r"No \linenumbers found", 0.85, r"Add \usepackage{lineno} and \linenumbers to the preamble"))
    # running head / short title
    if is_tex and not re.search(r"\\(?:markboth|runningtitle|shorttitle|runninghead)", low):
        out.append(_f(Severity.LOW, "No running head/short title", "Journals require a short running head defined in the template (markboth or class option).",
                      "No markboth/shorttitle found", 0.70, "Define the running head in the preamble per the venue template"))
    # page numbers
    if is_tex and not re.search(r"\\pagestyle|\\pagenumbering", low):
        out.append(_f(Severity.LOW, "Page numbering not configured", "Page numbers are expected for review and proofs.",
                      "No pagestyle/pagenumbering", 0.60, r"Ensure \pagestyle{plain} or the template default is active"))
    # template compliance hints
    if is_tex:
        cls = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", text)
        if cls:
            clsname = cls.group(1).lower()
            known = ["ieee", "acmart", "elsarticle", "svjour", "sn-jnl", "nature", "wiley", "mdpi", "article"]
            if clsname == "article":
                out.append(_f(Severity.MEDIUM, "Generic 'article' class instead of venue template", "Submitting in the venue's official template speeds processing and avoids format desk-rejects.",
                              "documentclass{article}", 0.80, "Switch to the venue's official LaTeX template"))
            elif not any(k in clsname for k in known):
                out.append(_f(Severity.LOW, "Unrecognized document class", "Class '" + clsname + "' is not a known journal template; verify the venue's requirements.",
                              clsname, 0.55, "Check the venue's author guidelines for the required template"))
    # wrong section: very short full-length-looking paper vs letters
    words = doc.word_count
    if words and words < 1500 and re.search(r"abstract|introduction|conclusion", low):
        out.append(_f(Severity.LOW, "Manuscript is very short - check article type", "Short manuscripts may belong in Letters/Short Communications rather than a full research article.",
                      str(words) + " words", 0.55, "Choose the correct article type or expand the manuscript"))
    # --- Type-3 bitmap font detection (PDF preflight) ---
    # IEEE/ACM/Elsevier camera-ready preflight rejects PDFs compiled with
    # bitmap (Type 3) fonts. Detectable by walking pypdf page resources.
    if doc.file_type == "pdf" and doc.path:
        try:
            from pypdf import PdfReader
            reader = PdfReader(doc.path)
            type3_fonts = set()
            for page in reader.pages:
                resources = page.get("/Resources")
                if not resources:
                    continue
                fonts = resources.get("/Font")
                if not fonts:
                    continue
                for fname in fonts:
                    try:
                        font_obj = fonts[fname].get_object()
                        if font_obj.get("/Subtype") == "/Type3":
                            type3_fonts.add(str(fname))
                    except Exception:
                        continue
            if type3_fonts:
                names = ", ".join(sorted(type3_fonts)[:5])
                out.append(_f(
                    Severity.HIGH,
                    "Type-3 bitmap fonts detected",
                    f"PDF contains bitmap (Type 3) fonts: {names}. "
                    "IEEE, ACM, and most publishers reject camera-ready PDFs with bitmap fonts. "
                    "Recompile using vector fonts (TrueType/OpenType).",
                    f"Type3 fonts: {names}",
                    0.95,
                    "Recompile the PDF with vector fonts (pdflatex/xelatex/lualatex with TTF/OTF)"
                ))
        except ImportError:
            pass  # pypdf not installed; skip silently
        except Exception:
            pass  # corrupt PDF; don't crash the engine
    return out