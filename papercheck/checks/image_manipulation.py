"""Error-level analysis (ELA): splicing/editing screening via recompression error.

Scope note — this engine used to also run a "copy-move" check that compared the
four quadrants of an image. That heuristic was inverted in practice: it required
two quadrants to be *similar*, so a blank or half-uniform figure (a plot on a
white background, a pale gel lane) matched itself and was reported as "possible
copied regions", while a genuine localized clone — a small block duplicated on
a busy background — left the quadrants different and was missed entirely.
Measured on fixtures: clone -> False, blank -> True, half-uniform -> True.

Copy-move detection now has exactly one owner, ``image_deep_forensics``, which
matches textured non-adjacent blocks and skips flat regions, so it catches the
real clone and stays silent on uniform figures.
"""
from __future__ import annotations
import io
import os
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

try:
    from PIL import Image, ImageChops, ImageStat
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


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


def run(doc: Document, ctx: object) -> List[Finding]:
    out = []
    if not _HAS_PIL or not doc.path:
        return out
    # Container knowledge lives in media.py — this engine used to be DOCX-only,
    # so PDF submissions silently received no manipulation analysis at all.
    from ..media import extract_images, DEFAULT_LIMIT
    images = extract_images(doc.path, doc.file_type, limit=DEFAULT_LIMIT)
    if not images:
        return out
    ela_hits = []
    for name, data in images:
        if _ela_anomaly(data):
            ela_hits.append(os.path.basename(name))
    if ela_hits:
        out.append(Finding("Figures", Severity.MEDIUM,
                           "ELA anomaly in embedded images (possible splicing/editing)",
                           "Regions with abnormally high recompression error suggest localized edits (splicing, pasted content).",
                           "Images: " + ", ".join(ela_hits[:4]), 0.55,
                           "Confirm no inappropriate manipulation; keep original captures as backup (COPE image-integrity rule)"))
    return out
