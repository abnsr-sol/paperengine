"""Document forensics engine.

Mirrors what iThenticate 2.0's Flags Panel does: hidden/replaced characters,
text manipulation, and sloppy submission artifacts. These are integrity-risk
*signals* — finding them means the document should be cleaned up, not that the
author cheated (hidden-text is also produced accidentally by copy-paste).

Only DOCX runs can be inspected structurally (via the zip XML); plain-text
files get the character-level checks.
"""

from __future__ import annotations

import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity
from . import CheckContext

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff\u2060]")
_CONFUSABLES = {
    "\u0430": "a",  # Cyrillic a
    "\u0435": "e",  # Cyrillic e
    "\u043e": "o",  # Cyrillic o
    "\u0440": "p",  # Cyrillic er
    "\u0441": "c",  # Cyrillic es
    "\u0445": "x",  # Cyrillic ha
    "\u03bf": "o",  # Greek omicron
    "\u03c3": "o",  # Greek sigma
}
_CONFUSABLE_RE = re.compile("[" + "".join(_CONFUSABLES) + "]")
_NON_ASCII_LATIN = re.compile(r"[\u00c0-\u024f\u2010-\u2015]")


def run(doc: Document, ctx: CheckContext) -> List[Finding]:
    findings: List[Finding] = []
    cat = "Forensics"
    text = doc.text

    # --- Invisible characters -------------------------------------------------------
    zw = _ZERO_WIDTH.findall(text)
    if zw:
        findings.append(Finding(
            category=cat, severity=Severity.HIGH,
            title="Invisible (zero-width) characters detected",
            detail=f"{len(zw)} zero-width / direction / BOM characters found — used to hide text from similarity checkers.",
            evidence="zero-width regex matches = " + str(len(zw)),
            action="Remove all invisible characters (search-replace in Word: ^u8203 etc.); they trigger integrity flags.",
            confidence=0.95,
        ))

    # --- Confusable / lookalike characters --------------------------------------------
    conf = _CONFUSABLE_RE.findall(text)
    if conf:
        sample_letters = {c: _CONFUSABLES[c] for c in set(conf[:8])}
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Lookalike (confusable) characters detected",
            detail=f"{len(conf)} non-Latin characters that mimic Latin letters (e.g. Cyrillic 'а' instead of 'a') — a text-manipulation red flag.",
            evidence="confusable chars: " + ", ".join(f"{k}->{v}" for k, v in sample_letters.items()),
            action="Normalize all text to ASCII/Latin; such characters are flagged by iThenticate's Flags Panel.",
            confidence=0.9,
        ))

    # --- DOCX structural checks ---------------------------------------------------------
    if doc.file_type == "docx" and os.path.exists(doc.path):
        try:
            with zipfile.ZipFile(doc.path) as zf:
                if "word/document.xml" in zf.namelist():
                    root = ET.fromstring(zf.read("word/document.xml"))
                    _docx_checks(root, doc, findings, cat)
        except (zipfile.BadZipFile, ET.ParseError):
            pass

    # --- Duplicate paragraphs with altered whitespace (evasion hint) ---------------------
    near_dups = _whitespace_variant_duplicates(doc)
    if near_dups:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Near-identical paragraphs with altered spacing",
            detail=f"{len(near_dups)} paragraph pair(s) match after whitespace normalization — looks like text-manipulation to dodge similarity checks.",
            evidence="sample: '" + near_dups[0][:90] + "...'",
            action="Rewrite the duplicated content properly; altered-spacing duplicates are flagged by integrity tools.",
            confidence=0.8,
        ))

    # --- Document metadata -----------------------------------------------------------------
    if doc.metadata:
        creator = doc.metadata.get("creator", "")
        last = doc.metadata.get("lastModifiedBy", "")
        if creator and last and creator.lower() != last.lower():
            findings.append(Finding(
                category=cat, severity=Severity.LOW,
                title="Document metadata inconsistency",
                detail=f"Creator '{creator}' differs from last editor '{last}' — confirm authorship metadata is clean before submission.",
                evidence="docProps/core.xml creator vs lastModifiedBy",
                action="Check 'File > Info' in Word and remove stale author metadata if needed.",
                confidence=0.8,
            ))
    return findings


def _docx_checks(root, doc: Document, findings: List[Finding], cat: str) -> None:
    """Hidden text, tiny/white runs, and tracked changes from DOCX XML."""
    hidden = 0
    tiny = 0
    white = 0
    for r in root.iter("{%s}r" % W_NS):
        rpr = r.find("{%s}rPr" % W_NS)
        if rpr is None:
            continue
        if rpr.find("{%s}vanish" % W_NS) is not None:
            hidden += 1
            continue
        sz = rpr.find("{%s}sz" % W_NS)
        if sz is not None:
            try:
                half_points = int(sz.get("{%s}val" % W_NS))
            except (TypeError, ValueError):
                half_points = 0
            if 0 < half_points <= 4:  # <= 2pt
                tiny += 1
        color = rpr.find("{%s}color" % W_NS)
        if color is not None:
            val = (color.get("{%s}val" % W_NS) or "").upper()
            if val in ("FFFFFF", "FFFFFE"):
                white += 1

    if hidden:
        findings.append(Finding(
            category=cat, severity=Severity.HIGH,
            title="Hidden (vanished) text in DOCX",
            detail=f"{hidden} run(s) are marked as hidden text.",
            evidence="w:vanish runs in word/document.xml = " + str(hidden),
            action="Reveal and remove or restore hidden text before submission.",
            confidence=0.95,
        ))
    if tiny:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Tiny (hidden-style) font runs",
            detail=f"{tiny} run(s) use font sizes of ~2pt or less.",
            evidence="w:sz <= 4 half-points runs = " + str(tiny),
            action="Check for invisible content tricks and remove them.",
            confidence=0.85,
        ))
    if white:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="White-colored text runs",
            detail=f"{white} run(s) use white font color (invisible on white background).",
            evidence="w:color val=FFFFFF runs = " + str(white),
            action="Remove or recolor invisible text; white-on-white is a classic manipulation flag.",
            confidence=0.9,
        ))

    # Tracked changes / comments
    ins = len(list(root.iter("{%s}ins" % W_NS)))
    dele = len(list(root.iter("{%s}del" % W_NS)))
    comments = len(list(root.iter("{%s}commentReference" % W_NS)))
    if ins + dele > 0 or comments > 0:
        findings.append(Finding(
            category=cat, severity=Severity.MEDIUM,
            title="Tracked changes or comments left in the manuscript",
            detail=f"tracked insertions: {ins}, deletions: {dele}, comments: {comments}.",
            evidence="w:ins / w:del / w:commentReference in document.xml",
            action="Accept all changes and delete all comments before submission.",
            confidence=0.9,
        ))


def _whitespace_variant_duplicates(doc: Document) -> List[str]:
    """Paragraphs that become identical after whitespace normalization."""
    from collections import defaultdict

    seen: dict = defaultdict(list)
    for p in doc.paragraphs:
        norm = re.sub(r"\s+", "", p.lower())
        if len(norm) >= 60:
            seen[norm].append(p)
    return [pairs[0] for pairs in seen.values() if len(pairs) > 1]