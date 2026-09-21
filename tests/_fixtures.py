"""Shared fixture builders for the engine tests.

One owner for the synthetic containers, images and HTTP stubs, because three
test modules used to carry their own copy of the same machinery — and a fix to
one copy silently missed the others.

Deliberately stdlib + Pillow only: the project ships no numpy dependency (see
``statscalc.py``), so an import of it here would fail in CI, which installs
only ``.[all]`` (pypdf + Pillow).
"""
from __future__ import annotations
import io
import json
import random
import urllib.error
import zipfile


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------
def flat(size: int = 128, value: int = 128):
    """Uniform greyscale panel — the shape that makes a hash meaningless."""
    from PIL import Image

    return Image.new("L", (size, size), value)


def texture(seed: int, size: int = 128, lo: int = 0, hi: int = 255):
    """Deterministic high-entropy panel."""
    from PIL import Image

    rnd = random.Random(seed)
    if (lo, hi) == (0, 255):
        data = rnd.randbytes(size * size)
    else:
        span = hi - lo
        data = bytes(lo + (b * span) // 255 for b in rnd.randbytes(size * size))
    return Image.frombytes("L", (size, size), data)


def png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def texture_png(seed: int, size: int = 96) -> bytes:
    return png(texture(seed, size))


def texture_jpeg(seed: int, size: int = 96) -> bytes:
    buf = io.BytesIO()
    texture(seed, size).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def rotated(data: bytes, angle: int = 90) -> bytes:
    """The panel re-saved rotated — the common real-world evasion."""
    from PIL import Image

    return png(Image.open(io.BytesIO(data)).rotate(angle, expand=True))


def rescaled(data: bytes, factor: float = 0.9) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    return png(img.resize((int(img.width * factor), int(img.height * factor)),
                          Image.LANCZOS))


# --------------------------------------------------------------------------
# containers
# --------------------------------------------------------------------------
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOC_XML = (
    f'<w:document xmlns:w="{_W_NS}"><w:body>'
    "<w:p><w:r><w:t>Methods and results text for the check pipeline.</w:t></w:r></w:p>"
    "</w:body></w:document>"
)
_CT_XML = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="png" ContentType="image/png"/>'
    '<Default Extension="jpeg" ContentType="image/jpeg"/></Types>'
)


def write_docx(path: str, media) -> None:
    """Minimal DOCX holding just the entries the engines actually read."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _CT_XML)
        z.writestr("word/document.xml", _DOC_XML)
        for name, data in media:
            z.writestr(f"word/media/{name}", data)


def write_pdf(path: str, images) -> None:
    """Minimal valid PDF, one 96x96 JPEG image XObject per page (stdlib only)."""
    n = len(images)
    page_ids = [3 + i for i in range(n)]
    img_ids = [3 + n + i for i in range(n)]
    cont_ids = [3 + 2 * n + i for i in range(n)]
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: ("<< /Type /Pages /Kids [%s] /Count %d >>"
            % (" ".join(f"{p} 0 R" for p in page_ids), n)).encode(),
    }
    for i in range(n):
        content = b"q 200 0 0 200 0 0 cm /Im0 Do Q"
        objs[cont_ids[i]] = (b"<< /Length %d >>\nstream\n" % len(content)
                             + content + b"\nendstream")
        objs[page_ids[i]] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            f"/Resources << /XObject << /Im0 {img_ids[i]} 0 R >> >> "
            f"/Contents {cont_ids[i]} 0 R >>").encode()
        data = images[i]
        objs[img_ids[i]] = (
            b"<< /Type /XObject /Subtype /Image /Width 96 /Height 96 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode "
            b"/Length %d >>\nstream\n" % len(data)) + data + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
    xref = len(out)
    top = max(objs)
    out += f"xref\n0 {top + 1}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, top + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {top + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as fh:
        fh.write(bytes(out))


# --------------------------------------------------------------------------
# network
# --------------------------------------------------------------------------
class Response(io.BytesIO):
    """Context-manager response stub (a real ``urlopen`` result used as one)."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def json_response(payload, status: int = 200) -> Response:
    resp = Response(json.dumps(payload).encode())
    resp.status = status
    return resp


def http_error(code: int, retry_after=None) -> urllib.error.HTTPError:
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("http://x", code, "err", headers, io.BytesIO(b""))


def replay(payload):
    """``side_effect`` answering every request with a *fresh* response.

    Returning one shared stream would leave it exhausted after the first read,
    which turns every later lookup into a fake transport failure — a trap that
    makes a working engine look unreachable.
    """
    def _open(req, timeout=None):
        return json_response(payload)

    return _open
