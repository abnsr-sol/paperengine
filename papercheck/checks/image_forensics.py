"""Image-forensics engine: duplicated/near-duplicated figure panels via
perceptual hashing (DOCX and PDF).

DOCX images come from word/media/; PDF images are extracted with pypdf's
image iterator (pure Python, no poppler). Rasterized vector graphics are
out of scope — we hash the embedded raster objects, which covers the common
real-world case (duplicate panels pasted into figure composites) while
keeping the engine dependency-free and offline.
"""
from __future__ import annotations
import os
import zipfile
from typing import Dict, List, Tuple
from ..ingestion import Document
from ..risk import Finding, Severity

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def _pdf_images(path: str) -> List[Tuple[str, bytes]]:
    """Extract (name, bytes) for every embedded raster image in a PDF."""
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    out: List[Tuple[str, bytes]] = []
    try:
        reader = PdfReader(path)
        for pnum, page in enumerate(reader.pages, 1):
            try:
                for img in page.images:
                    out.append((f"page{pnum}:{img.name}", img.data))
            except Exception:
                continue  # single broken page must not kill extraction
    except Exception:
        return []
    return out


def _dhash(data: bytes, size: int = 8) -> int:
    try:
        img = Image.open(__import__("io").BytesIO(data))
    except Exception:
        return -1
    try:
        img = img.convert("L").resize((size + 1, size), Image.LANCZOS)
        px = list(img.getdata())
    except Exception:
        return -1
    bits = 0
    for r in range(size):
        for c in range(size):
            left = px[r * (size + 1) + c]
            right = px[r * (size + 1) + c + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def run(doc: Document, ctx: object) -> List[Finding]:
    out = []
    if not _HAS_PIL or not doc.path or not os.path.exists(doc.path):
        return out

    # Collect (name, data) pairs from either container format.
    if doc.file_type == "docx":
        try:
            with zipfile.ZipFile(doc.path) as zf:
                media = sorted(n for n in zf.namelist() if n.startswith("word/media/"))
        except (zipfile.BadZipFile, KeyError, OSError):
            return out
        images: List[Tuple[str, bytes]] = []
        for name in media:
            try:
                with zipfile.ZipFile(doc.path) as zf:
                    images.append((name, zf.read(name)))
            except Exception:
                continue
    elif doc.file_type == "pdf":
        images = _pdf_images(doc.path)
    else:
        return out

    if len(images) < 2:
        return out

    hashes: Dict[int, List[Tuple[str, int, int]]] = {}
    for name, data in images:
        h = _dhash(data)
        if h < 0:
            continue
        try:
            import struct as _st
            dims = None
            if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
                dims = _st.unpack(">II", data[16:24])
            elif data[:3] == b"\xff\xd8\xff":
                p = 2
                while p < len(data) - 9:
                    if data[p] != 0xFF:
                        p += 1
                        continue
                    m = data[p + 1]
                    if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        hh, ww = _st.unpack(">HH", data[p + 5:p + 9])
                        dims = (ww, hh)
                        break
                    if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                        pass
                    p += 2
            hashes.setdefault(h, []).append((name, dims[0] if dims else 0, dims[1] if dims else 0))
        except Exception:
            hashes.setdefault(h, []).append((name, 0, 0))

    exact = [v for v in hashes.values() if len(v) >= 2]
    if exact:
        samples = "; ".join(
            os.path.basename(n) for group in exact[:3] for n, _, _ in group[:3])
        out.append(Finding("Figures", Severity.HIGH,
                           "Identical images embedded multiple times",
                           "The same image file appears more than once in the document - duplicated figures or reused panels.",
                           "Groups: " + str(len(exact)) + " | " + samples, 0.90,
                           "Check whether the same figure/panel was intentionally reused; give each unique content its own figure"))

    keys = list(hashes.keys())
    near = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if _hamming(keys[i], keys[j]) <= 3:
                for n1, w1, h1 in hashes[keys[i]]:
                    for n2, w2, h2 in hashes[keys[j]]:
                        if n1 != n2:
                            near.append((os.path.basename(n1), os.path.basename(n2)))
    if near:
        out.append(Finding("Figures", Severity.MEDIUM,
                           "Near-duplicate image panels detected",
                           "Two embedded images are perceptually almost identical (different file, same content) - possible panel duplication with altered labels.",
                           "Pairs: " + str(near[:4]), 0.70,
                           "Verify each panel shows genuinely different data; duplicates are an image-integrity flag (COPE)"))

    return out
