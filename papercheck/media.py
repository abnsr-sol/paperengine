"""Embedded-image extraction — the single owner of "where do figures come from".

Three engines need the images inside a manuscript (duplicate detection,
error-level analysis, clone detection), and each used to open the container
itself. That duplication meant a fix to one path silently missed the others:
the PDF branch existed in two engines and was missing entirely from the third,
so PDF submissions got less image scrutiny than DOCX ones for no good reason.

Everything returns ``List[(name, bytes)]``, never raises, and is ordered
deterministically so reports stay reproducible. Vector artwork is not
rasterised, so it is out of scope for every engine by construction rather than
by accident.
"""
from __future__ import annotations
import os
import zipfile
from typing import List, Tuple

# how many images any one engine will analyse (bounded work on huge theses)
DEFAULT_LIMIT = 24


def extract_images(path, file_type: str, limit: int = 0) -> List[Tuple[str, bytes]]:
    """Embedded images for a manuscript, whatever the container.

    DOCX images are the ``word/media/*`` zip entries; PDF images come from
    pypdf's page image iterator (pure Python, no poppler). ``limit`` caps how
    many are returned (0 = all) — callers doing per-pixel work pass a limit,
    duplicate hashing does not need to.
    """
    if not path or not os.path.exists(path):
        return []
    ft = (file_type or "").lower().lstrip(".")

    images: List[Tuple[str, bytes]] = []
    if ft == "docx":
        try:
            with zipfile.ZipFile(path) as zf:
                names = sorted(n for n in zf.namelist()
                               if n.startswith("word/media/"))
                for n in names:
                    try:
                        images.append((n, zf.read(n)))
                    except Exception:
                        continue  # one unreadable part must not kill the rest
        except (zipfile.BadZipFile, KeyError, OSError):
            return []
    elif ft == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
        except Exception:
            return []
        for pnum, page in enumerate(reader.pages, 1):
            try:
                for img in page.images:
                    images.append((f"page{pnum}:{img.name}", img.data))
            except Exception:
                continue  # a broken page must not lose the other pages

    return images[:limit] if limit else images
