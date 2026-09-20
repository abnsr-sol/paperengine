"""Image deep-forensics: Error-Level Analysis (ELA) + in-panel clone detection.

Complements `image_forensics` (duplicate/near-duplicate panels across the
document) with two within-image checks:

1. **Error-Level Analysis** — the image is re-saved at a uniform JPEG quality
   and the per-block difference against the original is measured. Regions that
   were pasted in from another photo (splices) or locally enhanced carry a
   different error level than their surroundings.

2. **Clone detection** — near-identical textured patches *inside one image*
   (copy-move forgery: the same cells/blots duplicated within a panel).
   Block hashing on a 128x128 grid; flat blocks are ignored so uniform
   backgrounds (gels, sky, tissue) do not trigger.

Both are screening signals with honest confidence — lighting/compression can
fool ELA, so findings stay LOW/MEDIUM and never claim proof of manipulation
(flag-not-verdict, COPE image-integrity guidance).
"""
from __future__ import annotations

import io
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

_ELA_QUALITY = 90
_ELA_RATIO_MED = 1.8     # max-region / median error to flag at all
_ELA_RATIO_HIGH = 2.5    # stronger ratio -> MEDIUM instead of LOW
_MAX_DIM = 512           # downscale cap: screening speed over forensic purity
_MIN_IMG = 64            # skip tiny images
_GRID = 128              # clone-detection working grid
_CELL = 16               # clone-detection block size on that grid
_FLAT_DELTA = 8          # blocks with max-min < this are "flat" and skipped


def _media_images(path: str, file_type: str) -> List[Tuple[str, bytes]]:
    """(name, bytes) for embedded images — delegated to the shared layer."""
    from ..media import extract_images
    return extract_images(path, file_type)


def _error_level_grid(img: "Image.Image") -> List[List[int]]:
    """Per-block mean absolute RGB error between img and a uniform-quality re-save."""
    rgb = img.convert("RGB")
    rgb.thumbnail((_MAX_DIM, _MAX_DIM), Image.LANCZOS)
    buffer = io.BytesIO()
    rgb.save(buffer, "JPEG", quality=_ELA_QUALITY)
    buffer.seek(0)
    resaved = Image.open(buffer).convert("RGB")

    w, h = rgb.size
    orig = list(rgb.getdata())
    re_px = list(resaved.getdata())
    bw, bh = w // _CELL, h // _CELL
    sums = [[0] * bw for _ in range(bh)]
    counts = [[0] * bw for _ in range(bh)]
    for idx in range(min(len(orig), len(re_px))):
        x, y = idx % w, idx // w
        bx, by = x // _CELL, y // _CELL
        if bx >= bw or by >= bh:
            continue
        po, pr = orig[idx], re_px[idx]
        d = abs(po[0] - pr[0]) + abs(po[1] - pr[1]) + abs(po[2] - pr[2])
        sums[by][bx] += d
        counts[by][bx] += 1
    grid: List[List[int]] = []
    for by in range(bh):
        row = []
        for bx in range(bw):
            row.append(sums[by][bx] // counts[by][bx] if counts[by][bx] else 0)
        grid.append(row)
    return grid


def _ela_findings(name: str, img: "Image.Image", out: List[Finding]) -> None:
    try:
        grid = _error_level_grid(img)
    except Exception:
        return
    vals = [v for row in grid for v in row if v > 0]
    if len(vals) < 4:
        return  # tiny or degenerate image
    vals_sorted = sorted(vals)
    median = vals_sorted[len(vals_sorted) // 2]
    if median == 0:
        return  # cannot normalize against a zero baseline
    top = vals_sorted[-1]
    ratio = top / median
    if ratio < _ELA_RATIO_MED:
        return
    sev = Severity.MEDIUM if ratio >= _ELA_RATIO_HIGH else Severity.LOW
    out.append(Finding(
        "Figures", sev,
        "Uneven error-level pattern in an embedded image",
        "Error-Level Analysis shows one region of this image carries a far "
        "stronger JPEG-compression error than the rest — consistent with a "
        "locally pasted/enhanced patch, but also produced by flat backgrounds "
        "and mixed-source composites. A screening signal to review, not proof "
        "of manipulation.",
        os.path.basename(name) + f": max/median error ratio {ratio:.1f} "
        f"(region {top} vs median {median})",
        "Review the panel at full resolution; confirm every region shares the "
        "same acquisition history. If a patch was added, disclose it.",
        0.55, source="image_deep_forensics",
    ))


def _clone_findings(name: str, img: "Image.Image", out: List[Finding]) -> None:
    """Copy-move detection: identical textured blocks, non-adjacent, one image."""
    try:
        g = img.convert("L").resize((_GRID, _GRID), Image.LANCZOS)
    except Exception:
        return
    px = list(g.getdata())
    blocks: Dict[int, List[Tuple[int, int]]] = {}
    for by in range(0, _GRID, _CELL):
        for bx in range(0, _GRID, _CELL):
            patch = [px[(by + r) * _GRID + bx + c] for r in range(_CELL) for c in range(_CELL)]
            lo, hi = min(patch), max(patch)
            if hi - lo < _FLAT_DELTA:
                continue  # flat block: uniform background, not evidence
            h = 0
            for v in patch:
                h = (h * 31 + v) & 0xFFFFFFFF
            blocks.setdefault(h, []).append((bx, by))
    matches = 0
    sample = None
    for members in blocks.values():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                (x1, y1), (x2, y2) = members[i], members[j]
                if abs(x1 - x2) >= 2 * _CELL or abs(y1 - y2) >= 2 * _CELL:
                    matches += 1
                    if sample is None:
                        sample = (x1, y1, x2, y2)
    if matches == 0:
        return
    out.append(Finding(
        "Figures", Severity.LOW,
        "Repeated texture pattern inside one panel",
        "Two or more non-adjacent textured patches of this image are "
        "pixel-identical — the copy-move signature. Repetitive legitimate "
        "texture (grids, gel lanes, architecture) can trigger this too, so "
        "treat it as a prompt to look, not as evidence.",
        os.path.basename(name) + f": {matches} identical patch pair(s), "
        f"e.g. blocks {sample}",
        "Visually compare the flagged regions; duplicated cells/blots/animals "
        "within a panel is a COPE image-integrity concern.",
        0.50, source="image_deep_forensics",
    ))


def run(doc: Document, ctx: object) -> List[Finding]:
    out: List[Finding] = []
    if not _HAS_PIL or not doc.path or not os.path.exists(doc.path):
        return out
    for name, data in _media_images(doc.path, doc.file_type):
        if len(data) < 512:
            continue
        try:
            img = Image.open(io.BytesIO(data))
            w, h = img.size
        except Exception:
            continue
        if w < _MIN_IMG or h < _MIN_IMG:
            continue
        _ela_findings(name, img, out)
        _clone_findings(name, img, out)
    return out
