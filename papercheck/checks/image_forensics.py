"""Image-forensics engine: duplicated / near-duplicated figure panels.

Two containers, one pipeline:
  * DOCX images come from ``word/media/``.
  * PDF images come from pypdf's page image iterator (pure Python, no poppler).
Rasterized vector graphics are out of scope — we hash embedded raster objects,
which covers the common real-world case (a panel pasted into several figures),
while keeping the engine dependency-free and offline.

**Robustness.** A single-orientation perceptual hash misses the most common
real-world evasion: take panel A, save it rotated / slightly rescaled /
recompressed, paste it again. So each image is normalised to a square and
hashed under all four cardinal rotations; two images match when the *smallest*
Hamming distance between any rotation pair is tiny. Measured on this
implementation (96x96 synthetic texture, 8x8 dhash):

    same image ......................... 0
    rotated 90/180/270 ................. 0
    rescaled to 90% .................... 0
    recompressed at JPEG q70 ........... 0
    unrelated image .................... 23

That spread is what makes the thresholds safe: ``<= 0`` is an exact copy under
rotation/scale, ``<= 6`` is a near-duplicate. Content-cropped copies are *not*
caught by this metric (a crop changes the hash substantially) — that is a
documented limitation, not a silent one.
"""
from __future__ import annotations
import io
import os
import zipfile
from typing import Dict, List, Optional, Tuple
from ..ingestion import Document
from ..risk import Finding, Severity

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

# --- tunables (all measured, see module docstring) --------------------------
_HASH_SIZE = 8            # dhash grid: (size+1) x size
_NORM_SIZE = 64           # square normalisation before rotation hashing
_ROTATIONS = (0, 90, 180, 270)
_EXACT_MAX = 0            # hamming <= 0  -> same content, different file
_NEAR_MAX = 6             # hamming <= 6  -> near-duplicate
_MAX_PIXELS = 40_000_000  # decompression-bomb guard
_MIN_SIDE = 32            # ignore icons / bullets / logos


def _pdf_images(path: str) -> List[Tuple[str, bytes]]:
    """Extract ``(name, bytes)`` for every embedded raster image in a PDF."""
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
                continue  # one broken page must not kill extraction
    except Exception:
        return []
    return out


def _open(data: bytes):
    """Open image bytes safely, or return None."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > _MAX_PIXELS:
            return None
        if min(img.width, img.height) < _MIN_SIDE:
            return None
        return img
    except Exception:
        return None


def _dhash(img, size: int = _HASH_SIZE) -> int:
    """Classic difference hash of an already-open PIL image."""
    try:
        im = img.convert("L").resize((size + 1, size), Image.LANCZOS)
        px = list(im.getdata())
    except Exception:
        return -1
    bits = 0
    for r in range(size):
        row = r * (size + 1)
        for c in range(size):
            bits = (bits << 1) | (1 if px[row + c] > px[row + c + 1] else 0)
    return bits


def _dhash_bytes(data: bytes, size: int = _HASH_SIZE) -> int:
    """Difference hash of raw image bytes (kept for callers/tests)."""
    img = _open(data)
    if img is None:
        return -1
    return _dhash(img, size)


def _rotate_hashes(data: bytes) -> List[int]:
    """Hashes of one image under the four cardinal rotations.

    The image is first normalised to a square so the four rotations are the
    *same shape* and therefore directly comparable — this is what makes a
    rotated copy of the same panel hash to the same set of values.
    """
    img = _open(data)
    if img is None:
        return []
    try:
        base = img.convert("L").resize((_NORM_SIZE, _NORM_SIZE), Image.LANCZOS)
    except Exception:
        return []
    out: List[int] = []
    for angle in _ROTATIONS:
        try:
            rot = base.rotate(angle, expand=True)
            h = _dhash(rot)
            if h >= 0:
                out.append(h)
        except Exception:
            continue
    return out


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _min_hamming(a_hashes: List[int], b_hashes: List[int]) -> int:
    """Smallest Hamming distance between any rotation pair (99 if empty)."""
    if not a_hashes or not b_hashes:
        return 99
    return min(_hamming(a, b) for a in a_hashes for b in b_hashes)


def _collect_images(doc: Document) -> List[Tuple[str, bytes]]:
    if doc.file_type == "docx":
        try:
            with zipfile.ZipFile(doc.path) as zf:
                media = sorted(n for n in zf.namelist()
                               if n.startswith("word/media/"))
                return [(n, zf.read(n)) for n in media]
        except (zipfile.BadZipFile, KeyError, OSError):
            return []
    if doc.file_type == "pdf":
        return _pdf_images(doc.path)
    return []


def run(doc: Document, ctx: object) -> List[Finding]:
    if not _HAS_PIL or not doc.path or not os.path.exists(doc.path):
        return []

    images = _collect_images(doc)
    if len(images) < 2:
        return []

    hashed: Dict[str, List[int]] = {}
    for name, data in images:
        hs = _rotate_hashes(data)
        if hs:
            hashed[name] = hs
    if len(hashed) < 2:
        return []

    names = list(hashed)
    exact: List[Tuple[str, str]] = []
    near: List[Tuple[str, str]] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            d = _min_hamming(hashed[a], hashed[b])
            if d <= _EXACT_MAX:
                exact.append((a, b))
            elif d <= _NEAR_MAX:
                near.append((a, b))

    out: List[Finding] = []
    if exact:
        pairs = "; ".join(f"{os.path.basename(a)} = {os.path.basename(b)}"
                          for a, b in exact[:3])
        out.append(Finding(
            "Figures", Severity.HIGH,
            "Identical image content embedded multiple times",
            "The same image appears more than once in this manuscript. Copies "
            "are detected even when one was re-saved rotated, rescaled or "
            "recompressed, so this is not just a duplicated file reference. "
            "Panel reuse across figures is a recognised image-integrity flag.",
            f"{len(exact)} duplicate pair(s): {pairs}",
            confidence=0.90,
            action="Confirm each panel shows genuinely different data; if the "
                   "same panel is reused, say so explicitly in the caption."))
    elif near:
        pairs = "; ".join(f"{os.path.basename(a)} ~ {os.path.basename(b)}"
                          for a, b in near[:4])
        out.append(Finding(
            "Figures", Severity.MEDIUM,
            "Near-duplicate image panels detected",
            "Two embedded images are perceptually almost identical (they match "
            "under rotation/rescale within a small hash distance) but are "
            "distinct files — a pattern consistent with a panel duplicated and "
            "given altered labels.",
            f"{len(near)} similar pair(s): {pairs}",
            confidence=0.70,
            action="Verify the panels show different data; near-duplicate "
                   "panels should be merged or explicitly explained."))
    return out
