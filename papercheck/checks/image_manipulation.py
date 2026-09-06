"""Image-manipulation heuristics (DOCX): copy-move quadrant hashing + ELA splicing-anomaly detection."""
from __future__ import annotations
import io
import os
import zipfile
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

try:
    from PIL import Image, ImageChops, ImageStat
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def _dhash_img(img, size=8):
    img = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(img.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (1 if px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] else 0)
    return bits


def _hamming(a, b):
    return bin(a ^ b).count("1")


def _ela_anomaly(data: bytes) -> bool:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        recomp = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        diff = ImageChops.difference(img, recomp).convert("L")
        w, h = diff.size
        if w < 64 or h < 64:
            return False
        means = []
        for gy in range(8):
            for gx in range(8):
                box = (gx * w // 8, gy * h // 8, (gx + 1) * w // 8, (gy + 1) * h // 8)
                means.append(ImageStat.Stat(diff.crop(box)).mean[0])
        avg = sum(means) / float(len(means))
        if avg < 1.0:
            return False
        high = [m for m in means if m > avg * 2.5]
        return len(high) >= 2
    except Exception:
        return False


def _copy_move(data: bytes) -> bool:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = img.size
        if w < 96 or h < 96:
            return False
        quads = [(0, 0, w // 2, h // 2), (w // 2, 0, w, h // 2),
                 (0, h // 2, w // 2, h), (w // 2, h // 2, w, h)]
        hs = [_dhash_img(img.crop(q)) for q in quads]
        for i in range(4):
            for j in range(i + 1, 4):
                if _hamming(hs[i], hs[j]) <= 3:
                    return True
        return False
    except Exception:
        return False


def run(doc: Document, ctx: object) -> List[Finding]:
    out = []
    if not _HAS_PIL or doc.file_type != "docx" or not doc.path or not os.path.exists(doc.path):
        return out
    try:
        with zipfile.ZipFile(doc.path) as zf:
            media = sorted(n for n in zf.namelist() if n.startswith("word/media/"))
    except (zipfile.BadZipFile, KeyError, OSError):
        return out
    if not media:
        return out
    ela_hits, cm_hits = [], []
    for name in media[:24]:
        try:
            with zipfile.ZipFile(doc.path) as zf:
                data = zf.read(name)
        except Exception:
            continue
        if _ela_anomaly(data):
            ela_hits.append(os.path.basename(name))
        if _copy_move(data):
            cm_hits.append(os.path.basename(name))
    if ela_hits:
        out.append(Finding("Figures", Severity.MEDIUM,
                           "ELA anomaly in embedded images (possible splicing/editing)",
                           "Regions with abnormally high recompression error suggest localized edits (splicing, pasted content).",
                           "Images: " + ", ".join(ela_hits[:4]), 0.55,
                           "Confirm no inappropriate manipulation; keep original captures as backup (COPE image-integrity rule)"))
    if cm_hits:
        out.append(Finding("Figures", Severity.LOW,
                           "Possible copied regions within a figure",
                           "Two quadrants of one image are perceptually identical - copied/repeated content inside a panel.",
                           "Images: " + ", ".join(cm_hits[:4]), 0.50,
                           "Verify panels show distinct data; duplicated regions are an image-integrity flag"))
    return out
