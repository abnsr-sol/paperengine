"""v1.14b hardening wave.

Covers the three failure classes fixed together:

1. **Network behaviour** — ``papercheck.net`` must retry throttling and never
   turn a 429 into a fabricated "this DOI does not exist" finding.
2. **Container coverage** — ``papercheck.media`` is the single owner of image
   extraction; ``image_manipulation`` used to skip PDFs entirely.
3. **Image false positives** — a perceptual hash carries no information on a
   near-flat figure, so blank/pale figures must not be reported as duplicates;
   and the inverted quadrant "copy-move" heuristic must stay deleted.
"""
from __future__ import annotations
import io
import os
import random
import tempfile
import unittest
import urllib.error
import zipfile
from unittest import mock

from papercheck import media, net


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
class _Resp(io.BytesIO):
    """Context-manager response stub."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, retry_after=None):
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("http://x", code, "err", headers, io.BytesIO(b""))


def _flat(size: int, value: int):
    """Uniform greyscale panel — the shape that makes a perceptual hash meaningless."""
    from PIL import Image

    return Image.new("L", (size, size), value)


def _texture(seed: int, size: int = 128, lo: int = 0, hi: int = 255):
    """Deterministic high-entropy panel, built with the stdlib RNG.

    Deliberately not numpy: the project ships no numpy dependency (see
    ``statscalc.py``), so a numpy import here breaks the CI environment.
    """
    from PIL import Image

    rnd = random.Random(seed)
    if (lo, hi) == (0, 255):
        data = rnd.randbytes(size * size)
    else:
        span = hi - lo
        data = bytes(lo + (b * span) // 255 for b in rnd.randbytes(size * size))
    return Image.frombytes("L", (size, size), data)


def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


_DOC_XML = (
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>Body text.</w:t></w:r></w:p></w:body></w:document>"
)
_CT_XML = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="png" ContentType="image/png"/></Types>'
)


def _write_docx(path, items):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _CT_XML)
        z.writestr("word/document.xml", _DOC_XML)
        for name, data in items:
            z.writestr(f"word/media/{name}", data)


def _write_pdf(path, payloads):
    """Minimal PDF, one JPEG image XObject per page."""
    n = len(payloads)
    pages = [3 + i for i in range(n)]
    imgids = [3 + n + i for i in range(n)]
    conts = [3 + 2 * n + i for i in range(n)]
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: ("<< /Type /Pages /Kids [%s] /Count %d >>"
            % (" ".join(f"{p} 0 R" for p in pages), n)).encode(),
    }
    for i in range(n):
        body = b"q 200 0 0 200 0 0 cm /Im0 Do Q"
        objs[conts[i]] = b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"
        objs[pages[i]] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            f"/Resources << /XObject << /Im0 {imgids[i]} 0 R >> >> "
            f"/Contents {conts[i]} 0 R >>").encode()
        d = payloads[i]
        objs[imgids[i]] = (
            b"<< /Type /XObject /Subtype /Image /Width 96 /Height 96 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode "
            b"/Length %d >>\nstream\n" % len(d)) + d + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offs = {}
    for k in sorted(objs):
        offs[k] = len(out)
        out += f"{k} 0 obj\n".encode() + objs[k] + b"\nendobj\n"
    xref = len(out)
    top = max(objs)
    out += f"xref\n0 {top + 1}\n".encode() + b"0000000000 65535 f \n"
    for k in range(1, top + 1):
        out += f"{offs[k]:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {top + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as fh:
        fh.write(bytes(out))


def _jpeg(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


# --------------------------------------------------------------------------
# 1. network behaviour
# --------------------------------------------------------------------------
class TestHttpRetryLayer(unittest.TestCase):
    def test_retries_429_then_succeeds(self):
        sleeps = []
        side = [_http_error(429), _Resp(b'{"ok":true}')]
        with mock.patch("urllib.request.urlopen", side_effect=side):
            body = net.fetch("http://x", sleep=sleeps.append)
        self.assertEqual(body, b'{"ok":true}')
        self.assertEqual(len(sleeps), 1, "should have backed off exactly once")

    def test_429_exhausted_returns_none_not_an_exception(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=_http_error(429)) as m:
            body = net.fetch("http://x", retries=2, sleep=lambda s: None)
        self.assertIsNone(body)
        self.assertEqual(m.call_count, 3, "initial attempt + 2 retries")

    def test_honours_retry_after_header(self):
        sleeps = []
        side = [_http_error(429, retry_after="2.5"), _Resp(b"{}")]
        with mock.patch("urllib.request.urlopen", side_effect=side):
            net.fetch("http://x", sleep=sleeps.append)
        self.assertEqual(sleeps, [2.5])

    def test_404_is_terminal_and_not_retried(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=_http_error(404)) as m:
            body = net.fetch("http://x", sleep=lambda s: None)
        self.assertIsNone(body)
        self.assertEqual(m.call_count, 1, "a missing resource must not be retried")

    def test_5xx_is_retried(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=_http_error(503)) as m:
            net.fetch("http://x", retries=1, sleep=lambda s: None)
        self.assertEqual(m.call_count, 2)

    def test_transport_error_never_raises(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("dns fail")):
            self.assertIsNone(net.fetch("http://x", sleep=lambda s: None))

    def test_backoff_grows(self):
        sleeps = []
        with mock.patch("urllib.request.urlopen", side_effect=_http_error(500)):
            net.fetch("http://x", retries=3, sleep=sleeps.append)
        self.assertEqual(len(sleeps), 3)
        # jitter is added, but the schedule must still be increasing overall
        self.assertLess(sleeps[0], sleeps[2])

    def test_fetch_json_tolerates_malformed_body(self):
        with mock.patch("urllib.request.urlopen", return_value=_Resp(b"not json")):
            self.assertIsNone(net.fetch_json("http://x", sleep=lambda s: None))

    def test_user_agent_identifies_the_project(self):
        self.assertIn("paperengine/", net.user_agent())

    def test_contact_address_used_when_set(self):
        with mock.patch.dict(os.environ, {"PAPERCHECK_MAILTO": "a@b.c"}, clear=False):
            self.assertIn("mailto:a@b.c", net.user_agent())


# --------------------------------------------------------------------------
# 2. container coverage
# --------------------------------------------------------------------------
class TestSharedMediaLayer(unittest.TestCase):
    def test_reads_docx_media_in_deterministic_order(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.docx")
            _write_docx(p, [("z.png", _png(_flat(64, 0))), ("a.png", _png(_flat(64, 1)))])
            names = [n for n, _ in media.extract_images(p, "docx")]
            self.assertEqual(names, sorted(names))

    def test_reads_pdf_images(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.pdf")
            img = _texture(1, size=96)
            _write_pdf(p, [_jpeg(img), _jpeg(img)])
            imgs = media.extract_images(p, "pdf")
            self.assertEqual(len(imgs), 2)

    def test_limit_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.docx")
            _write_docx(p, [(f"{i}.png", _png(_flat(64, i))) for i in range(5)])
            self.assertEqual(len(media.extract_images(p, "docx", limit=2)), 2)

    def test_missing_path_and_unknown_type_are_safe(self):
        self.assertEqual(media.extract_images("/nope/x.docx", "docx"), [])
        self.assertEqual(media.extract_images("/nope/x.rtf", "rtf"), [])

    def test_corrupt_container_does_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "bad.docx")
            with open(p, "wb") as fh:
                fh.write(b"not a zip")
            self.assertEqual(media.extract_images(p, "docx"), [])

    def test_pdf_images_are_seen_by_every_image_engine(self):
        """The regression: image_manipulation used to return early for PDFs."""
        from papercheck.checks import CheckContext
        from papercheck.ingestion import load_document
        import papercheck.checks.image_manipulation as IM

        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.pdf")
            img = _texture(4, size=128, lo=60, hi=200)
            _write_pdf(p, [_jpeg(img)])
            doc = load_document(p)
            self.assertEqual(doc.file_type, "pdf")
            # must execute the image loop rather than bail out on file type
            with mock.patch.object(IM, "_ela_anomaly", return_value=True) as spy:
                findings = IM.run(doc, CheckContext())
            self.assertTrue(spy.called, "engine never inspected the PDF images")
            self.assertTrue(findings, "an ELA hit on a PDF must be reported")


# --------------------------------------------------------------------------
# 3. image false positives
# --------------------------------------------------------------------------
class TestImageFalsePositives(unittest.TestCase):
    def _figures(self, items):
        from papercheck.checks import CheckContext, run_all_engines
        from papercheck.ingestion import load_document

        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.docx")
            _write_docx(p, items)
            findings, errors = run_all_engines(load_document(p), CheckContext())
        self.assertEqual(errors, [])
        return [f for f in findings if f.category == "Figures"]

    def test_pale_uniform_figures_are_not_duplicates(self):
        # a plot on a white background + a pale gel lane: both hash to ~zero bits
        diag = _flat(128, 255)
        diag.paste(200, (0, 64, 128, 128))
        pale = _flat(128, 230)
        figs = self._figures([("a.png", _png(diag)), ("b.png", _png(pale))])
        self.assertEqual(figs, [], "uniform figures must not be reported as duplicates")

    def test_different_textures_are_not_duplicates(self):
        figs = self._figures([
            ("a.png", _png(_texture(0, lo=60, hi=200))),
            ("b.png", _png(_texture(1))),
        ])
        self.assertEqual(figs, [])

    def test_identical_textures_still_reported(self):
        img = _texture(0, lo=60, hi=200)
        figs = self._figures([("a.png", _png(img)), ("b.png", _png(img))])
        self.assertTrue(figs, "genuine duplicate panels must still fire")
        self.assertEqual(figs[0].severity.value, "High")

    def test_rotated_duplicate_still_reported(self):
        from PIL import Image

        img = _texture(0, lo=60, hi=200)
        rot = Image.open(io.BytesIO(_png(img))).rotate(90, expand=True)
        buf = io.BytesIO()
        rot.save(buf, "PNG")
        figs = self._figures([("a.png", _png(img)), ("b.png", buf.getvalue())])
        self.assertTrue(figs, "rotation-invariant matching must still work")

    def test_byte_identical_flat_figure_is_reported(self):
        same = _png(_flat(128, 230))
        figs = self._figures([("a.png", same), ("b.png", same)])
        self.assertTrue(figs, "the same flat file twice is a real duplicate")

    def test_informative_hash_gate(self):
        from papercheck.checks.image_forensics import _is_informative, _rotate_hashes

        self.assertFalse(_is_informative(_rotate_hashes(_png(_flat(128, 128)))))
        self.assertTrue(_is_informative(_rotate_hashes(_png(_texture(0)))))

    def test_inverted_quadrant_detector_is_gone(self):
        """Guard against reintroducing the heuristic that flagged flat figures."""
        import papercheck.checks.image_manipulation as IM

        self.assertFalse(hasattr(IM, "_copy_move"),
                         "the quadrant copy-move heuristic is inverted; do not reintroduce it")

    def test_clone_detection_owned_by_deep_forensics(self):
        import papercheck.checks.image_deep_forensics as DEEP

        img = _texture(3, lo=60, hi=200)
        block = _texture(9, size=32, lo=40, hi=220)
        img.paste(block, (16, 16))
        img.paste(block, (80, 80))           # duplicated region
        out = []
        DEEP._clone_findings("x.png", img, out)
        self.assertTrue(out, "the real clone must still be detected")

    def test_blank_image_is_not_a_clone(self):
        import papercheck.checks.image_deep_forensics as DEEP

        out = []
        DEEP._clone_findings("x.png", _flat(128, 128), out)
        self.assertEqual(out, [], "a uniform panel has no clone signature")


if __name__ == "__main__":
    unittest.main()
