"""Embedded-image extraction — the single owner of "where do figures come from".

Three engines need the images inside a manuscript (duplicate detection,
error-level analysis, clone detection), and each used to open the container
itself. That duplication meant a fix to one path silently missed the others:
the PDF branch existed in two engines and was missing entirely from the third,
so PDF submissions got less image scrutiny than DOCX ones for no good reason.

Container knowledge lives here now:

* **DOCX** — ``word/media/*`` entries of the OOXML zip.
* **PDF** — embedded raster XObjects via pypdf's page image iterator (pure
  Python, no poppler). Vector artwork is not rasterised, so it is out of scope
  for every engine by construction rather than by accident.

Everything returns ``List[(name, bytes)]``, never raises, and is ordered
deterministically so reports stay reproducible.
"""
from __future__ import annotations
import os
import zipfile
from typing import List, Tuple

# how many images any one engine will analyse (bounded work on huge theses)
DEFAULT_LIMIT = 24


def docx_images(path: str) -> List[Tuple[str, bytes]]:
    """Embedded images from a DOCX container, in deterministic order."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = sorted(n for n in zf.namelist()
                           if n.startswith("word/media/"))
            out: List[Tuple[str, bytes]] = []
            for n in names:
                try:
                    out.append((n, zf.read(n)))
                except Exception:
                    continue  # one unreadable part must not kill the rest
            return out
    except (zipfile.BadZipFile, KeyError, OSError):
        return []


def pdf_images(path: str) -> List[Tuple[str, bytes]]:
    """Embedded raster images from a PDF, in page order."""
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    out: List[Tuple[str, bytes]] = []
    try:
        reader = PdfReader(path)
    except Exception:
        return []
    for pnum, page in enumerate(reader.pages, 1):
        try:
            for img in page.images:
                out.append((f"page{pnum}:{img.name}", img.data))
        except Exception:
            continue  # a broken page must not lose the other pages
    return out


def extract_images(path, file_type: str, limit: int = 0) -> List[Tuple[str, bytes]]:
    """Embedded images for a manuscript, whatever the container.

    ``limit`` caps how many are returned (0 = all). Callers that do per-pixel
    work pass a limit; duplicate hashing does not need to.
    """
    if not path or not os.path.exists(path):
        return []
    ft = (file_type or "").lower().lstrip(".")
    images: List[Tuple[str, bytes]] = []
    if ft == "docx":
        images = docx_images(path)
    elif ft == "pdf":
        images = pdf_images(path)
    if limit and len(images) > limit:
        return images[:limit]
    return images
