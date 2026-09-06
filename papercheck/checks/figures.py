"""Figures & tables engine.

Reviewers complain about (and editors desk-reject for): figures never
referenced in the text, missing or useless captions, broken numbering, and
unreadable (low-resolution) images. Image resolution checks only apply to
DOCX, where embedded images can be inspected directly from the zip.
"""

from __future__ import annotations

import io
import os
import re
import struct
import zipfile
from typing import Dict, List, Tuple

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

_FIG_CAPTION = re.compile(r"\bfigure\s+(\d{1,2})\b", re.IGNORECASE)
_TBL_CAPTION = re.compile(r"\btable\s+(\d{1,2})\b", re.IGNORECASE)
_FIG_REF = re.compile(r"\bfigure\s+(\d{1,2})\b", re.IGNORECASE)
_TBL_REF = re.compile(r"\btable\s+(\d{1,2})\b", re.IGNORECASE)


def _caption_groups(text: str, rx) -> List[int]:
    return [int(m) for m in rx.findall(text)]


def _referenced_groups(text: str, rx) -> List[int]:
    return [int(m) for m in rx.findall(text)]


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    if doc.word_count < 100:
        return findings
    cat = "Figures"
    text = doc.text

    # --- Numbering gaps (Figure 1, 2, 4) ----------------------------------------------
    fig_nums = sorted(set(_caption_groups(text, _FIG_CAPTION)))
    tbl_nums = sorted(set(_caption_groups(text, _TBL_CAPTION)))
    for nums, kind in ((fig_nums, "Figure"), (tbl_nums, "Table")):
        if len(nums) >= 2:
            expected = list(range(min(nums), max(nums) + 1))
            missing = [n for n in expected if n not in nums]
            if missing:
                findings.append(Finding(
                    category=cat, severity=Severity.MEDIUM,
                    title=f"{kind} numbering gap",
                    detail=f"{kind}s {', '.join(str(n) for n in nums)} found; missing number(s): {', '.join(str(n) for n in missing)}.",
                    evidence=f"{kind.lower()} caption numbers parsed = {nums}",
                    action="Renumber sequentially; broken numbering signals an incomplete manuscript.",
                    confidence=0.9,
                ))

    # --- Figures mentioned but no caption ------------------------------------------------
    all_fig_mentions = _referenced_groups(text, _FIG_REF)
    if all_fig_mentions and not fig_nums:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Figures mentioned but no captions found",
            detail=f"{len(all_fig_mentions)} 'Figure N' mentions in text, no caption lines detected.",
            evidence="figure mentions = " + str(sorted(set(all_fig_mentions))[:10]),
            action="Add a caption under every figure (Figure N: description).",
            confidence=0.7,
        ))
    if fig_nums and not all_fig_mentions:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Figures never referenced in the text",
            detail=f"{len(fig_nums)} figure caption(s) but zero in-text references.",
            evidence="captions = " + str(fig_nums) + ", in-text 'Figure N' mentions = 0",
            action="Reference every figure in the text ('as shown in Figure N') — orphan figures are a reviewer complaint.",
            confidence=0.85,
        ))

    # --- Tables referenced but no caption ------------------------------------------------
    tbl_mentions = _referenced_groups(text, _TBL_REF)
    if tbl_mentions and not tbl_nums:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Tables mentioned but no captions found",
            detail=f"{len(tbl_mentions)} 'Table N' mentions, no table captions detected.",
            evidence="table mentions = " + str(sorted(set(tbl_mentions))[:10]),
            action="Add a caption to every table.",
            confidence=0.7,
        ))

    # --- Short captions ------------------------------------------------------------------
    for kind, rx in (("Figure", _FIG_CAPTION), ("Table", _TBL_CAPTION)):
        for m in rx.finditer(text):
            tail = text[m.end() : m.end() + 160].strip()
            n_words = len(tail.split())
            if 0 < n_words < 4:
                findings.append(Finding(
                    category=cat, severity=Severity.LOW,
                    title=f"Very short {kind.lower()} caption",
                    detail=f"{kind} {m.group(1)} caption is only {n_words} word(s).",
                    evidence=f"'{kind} {m.group(1)}: {tail[:80]}'",
                    action="Make captions self-contained: what is shown, what to notice, units.",
                    confidence=0.7,
                ))

    # --- Image resolution (DOCX) -------------------------------------------------------------
    if doc.file_type == "docx" and os.path.exists(doc.path):
        findings.extend(_docx_image_checks(doc, cat))
    return findings


def _docx_image_checks(doc: Document, cat: str) -> List[Finding]:
    findings: List[Finding] = []
    try:
        with zipfile.ZipFile(doc.path) as zf:
            media = [n for n in zf.namelist() if n.startswith("word/media/")]
            if not media:
                return findings
            low_res = []
            for name in media:
                dims = _image_dimensions(zf.read(name))
                if dims is None:
                    continue
                w, h = dims
                if max(w, h) < 400:
                    low_res.append((name, w, h))
            if low_res:
                samples = ", ".join(f"{os.path.basename(n)} ({w}x{h})" for n, w, h in low_res[:4])
                findings.append(Finding(
                    category=cat, severity=Severity.MEDIUM,
                    title="Low-resolution images",
                    detail=f"{len(low_res)} embedded image(s) under 400px on the long edge — likely blurry when printed.",
                    evidence="word/media dimensions: " + samples,
                    action="Export figures at ≥300 DPI (or vector PDF/SVG) at the final print size.",
                    confidence=0.75,
                ))
    except (zipfile.BadZipFile, KeyError):
        pass
    return findings


def _image_dimensions(data: bytes) -> Tuple[int, int] | None:
    """Width/height in pixels for PNG/JPEG/GIF/BMP, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:3] == b"\xff\xd8\xff":  # JPEG: walk markers to SOF
        pos = 2
        while pos < len(data) - 9:
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[pos + 5 : pos + 9])
                return w, h
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                pos += 2
            else:
                length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
                pos += 2 + length
        return None
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data[:2] == b"BM" and len(data) >= 26:
        w, h = struct.unpack("<ii", data[18:26])
        return w, abs(h)
    return None