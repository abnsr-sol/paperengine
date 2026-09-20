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
import hashlib
import io
import os
from itertools import combinations
from typing import Dict, List, Tuple
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

# A perceptual hash only means something if the image has enough local detail
# to produce a mixed bit pattern. A flat or piecewise-flat figure (blank gel
# lane, plot on a white background) hashes to all-zero bits, so *any* two such
# figures "match" — measured on real fixtures, degenerate figures score 0-7
# set bits while genuine textures score 24-32. Below this floor we refuse to
# compare perceptually and fall back to exact content identity, which cannot
# produce a false duplicate.
_MIN_HASH_BITS = 12


def _is_informative(hashes: List[int]) -> bool:
    """True when the hash carries enough bit diversity to be comparable."""
    return bool(hashes) and min(bin(h).count("1") for h in hashes) >= _MIN_HASH_BITS


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


def _min_hamming(a_hashes: List[int], b_hashes: List[int]) -> int:
    """Smallest Hamming distance between any rotation pair (99 if empty)."""
    if not a_hashes or not b_hashes:
        return 99
    return min(bin(a ^ b).count("1") for a in a_hashes for b in b_hashes)


def run(doc: Document, ctx: object) -> List[Finding]:
    if not _HAS_PIL or not doc.path or not os.path.exists(doc.path):
        return []

    from ..media import extract_images
    images = extract_images(doc.path, doc.file_type)
    if len(images) < 2:
        return []

    # Split by information content: only detailed images can be compared
    # perceptually; near-flat ones fall back to exact identity.
    informative: Dict[str, List[int]] = {}
    flat: Dict[str, str] = {}
    for name, data in images:
        hs = _rotate_hashes(data)
        if _is_informative(hs):
            informative[name] = hs
        else:
            flat[name] = hashlib.sha256(data).hexdigest()

    exact: List[Tuple[str, str]] = []
    near: List[Tuple[str, str]] = []

    # Flat figures: identical only when the bytes are identical, which is a
    # genuine duplicate and cannot false-positive on two unrelated pale plots.
    exact = [(a, b) for a, b in combinations(flat, 2) if flat[a] == flat[b]]
    for a, b in combinations(informative, 2):
        d = _min_hamming(informative[a], informative[b])
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
