"""v1.14 wave: rotation/scale-invariant image duplication, PubPeer screening
contract, API-key config plumbing, and the engine-registry self-check.

Every fixture is built in-test with stdlib bytes (DOCX zip + minimal PDF) so the
suite needs no binary fixtures and no network.
"""
from __future__ import annotations
import io
import json
import os
import random
import tempfile
import zipfile
from unittest import TestCase, mock

from papercheck.checks import ALL_ENGINES, CheckContext, run_all_engines
from papercheck.ingestion import load_document

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


def _noise(seed: int, size: int = 96):
    """Deterministic high-entropy greyscale panel.

    Built from the stdlib RNG rather than numpy: the project ships no numpy
    dependency, so importing it here would fail the CI environment.
    """
    from PIL import Image

    return Image.frombytes("L", (size, size), random.Random(seed).randbytes(size * size))


def _texture_png(seed: int, size: int = 96) -> bytes:
    buf = io.BytesIO()
    _noise(seed, size).save(buf, "PNG")
    return buf.getvalue()


def _texture_jpeg(seed: int, size: int = 96) -> bytes:
    buf = io.BytesIO()
    _noise(seed, size).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _transform(data: bytes, kind: str) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if kind == "rotate90":
        img = img.rotate(90, expand=True)
    elif kind == "rotate270":
        img = img.rotate(270, expand=True)
    elif kind == "scale":
        img = img.resize((int(img.width * 0.9), int(img.height * 0.9)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _write_docx(path: str, media: list) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _CT_XML)
        z.writestr("word/document.xml", _DOC_XML)
        for name, data in media:
            z.writestr(f"word/media/{name}", data)


def _write_pdf(path: str, images: list) -> None:
    """Minimal valid PDF with one JPEG XObject per page (stdlib only)."""
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


def _figure_findings(path):
    doc = load_document(path)
    findings, errors = run_all_engines(doc, CheckContext())
    return [f for f in findings if f.category == "Figures"], errors


class TestImageDuplication(TestCase):
    def _run_docx(self, second: bytes):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "paper.docx")
            _write_docx(path, [("a.png", _texture_png(7)), ("b.png", second)])
            return _figure_findings(path)

    def test_exact_duplicate_fires_high(self):
        figs, errors = self._run_docx(_texture_png(7))
        self.assertEqual(errors, [])
        self.assertTrue(figs, "identical images must be reported")
        self.assertEqual(figs[0].severity.value, "High")

    def test_rotated_duplicate_fires(self):
        # the real-world evasion the old single-orientation hash missed
        figs, errors = self._run_docx(_transform(_texture_png(7), "rotate90"))
        self.assertEqual(errors, [])
        self.assertTrue(figs, "a 90-degree rotated copy must still be caught")

    def test_rotated_270_duplicate_fires(self):
        figs, _ = self._run_docx(_transform(_texture_png(7), "rotate270"))
        self.assertTrue(figs, "a 270-degree rotated copy must still be caught")

    def test_rescaled_duplicate_fires(self):
        figs, _ = self._run_docx(_transform(_texture_png(7), "scale"))
        self.assertTrue(figs, "a rescaled copy must still be caught")

    def test_different_images_are_silent(self):
        figs, errors = self._run_docx(_texture_png(99))
        self.assertEqual(errors, [])
        self.assertEqual(figs, [], "unrelated panels must not be flagged")

    def test_single_image_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "one.docx")
            _write_docx(path, [("a.png", _texture_png(7))])
            figs, errors = _figure_findings(path)
            self.assertEqual(figs, [])
            self.assertEqual(errors, [])

    def test_tiny_icons_are_ignored(self):
        from PIL import Image

        small = Image.new("L", (16, 16), 0)
        buf = io.BytesIO()
        small.save(buf, "PNG")
        figs, _ = self._run_docx(buf.getvalue())
        self.assertEqual(figs, [], "16px icons are not figure panels")

    def test_identical_pdfs_fire(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "two.pdf")
            _write_pdf(path, [_texture_jpeg(7), _texture_jpeg(7)])
            figs, errors = _figure_findings(path)
            self.assertEqual(errors, [])
            self.assertTrue(figs, "duplicate embedded PDF images must fire")

    def test_different_pdfs_silent(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "diff.pdf")
            _write_pdf(path, [_texture_jpeg(7), _texture_jpeg(99)])
            figs, errors = _figure_findings(path)
            self.assertEqual(errors, [])
            self.assertEqual(figs, [])

    def test_min_hamming_separates_cleanly(self):
        from papercheck.checks.image_forensics import _rotate_hashes, _min_hamming

        a = _rotate_hashes(_texture_png(7))
        b = _rotate_hashes(_texture_png(7))
        c = _rotate_hashes(_texture_png(99))
        self.assertEqual(_min_hamming(a, b), 0)
        self.assertGreater(_min_hamming(a, c), 6)


class TestPubPeerScreening(TestCase):
    def test_offline_is_a_silent_noop(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "paper.docx")
            _write_docx(path, [])
            doc = load_document(path)
            findings, errors = run_all_engines(doc, CheckContext(online=False))
            self.assertEqual(errors, [])
            self.assertEqual(
                [f for f in findings
                 if getattr(f, "source", None) == "pubpeer_screening"],
                [], "no network work may happen when offline")

    def test_engine_does_not_touch_network_when_offline(self):
        import papercheck.checks.pubpeer_screening as pp

        doc = load_document(os.path.join(os.path.dirname(__file__), "..", "sample_paper.txt"))
        with mock.patch("urllib.request.urlopen") as m:
            pp.run(doc, CheckContext(online=False))
            m.assert_not_called()

    def test_candidate_extraction_finds_doi(self):
        import papercheck.checks.pubpeer_screening as pp

        cands = pp._candidates("Smith 2020. doi 10.1234/example.2020 and more text")
        self.assertIn("https://doi.org/10.1234/example.2020", cands)

    def test_comment_count_parsed_from_json(self):
        import papercheck.checks.pubpeer_screening as pp

        resp = io.BytesIO(json.dumps({"comment_count": 3}).encode())
        with mock.patch("urllib.request.urlopen", return_value=resp):
            count, checked = pp._pubpeer_comment_count("https://doi.org/10.1/x")
        self.assertEqual(count, 3)
        self.assertTrue(checked, "an answered lookup is not an unreachable one")

    def test_threshold_defaults_to_two(self):
        self.assertEqual(CheckContext().pubpeer_threshold, 2)


class TestApiKeyPlumbing(TestCase):
    """The config file documented [api_keys] but nothing ever applied them."""

    def test_config_keys_are_applied_to_environment(self):
        from papercheck.config import apply_api_keys

        with mock.patch.dict(os.environ, {}, clear=True):
            applied = apply_api_keys({"api_keys": {"openalex": "TESTKEY123"}})
            self.assertIn("OPENALEX_API_KEY", applied)
            self.assertEqual(os.environ["OPENALEX_API_KEY"], "TESTKEY123")

    def test_existing_environment_wins(self):
        from papercheck.config import apply_api_keys

        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": "REAL"}, clear=True):
            applied = apply_api_keys({"api_keys": {"openalex": "FROMFILE"}})
            self.assertEqual(applied, [])
            self.assertEqual(os.environ["OPENALEX_API_KEY"], "REAL")

    def test_blank_keys_are_ignored(self):
        from papercheck.config import apply_api_keys

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(apply_api_keys({"api_keys": {"openalex": "  "}}), [])

    def test_openalex_engine_sends_the_key(self):
        import papercheck.checks.openalex_verify as oa

        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": "K1"}, clear=True):
            self.assertEqual(oa._key_param(), "&api_key=K1")

    def test_openalex_engine_omits_param_without_key(self):
        import papercheck.checks.openalex_verify as oa

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(oa._key_param(), "")


class TestRegistrySelfCheck(TestCase):
    def test_registry_matches_files_on_disk(self):
        from pathlib import Path

        from papercheck.checks import __path__ as pkg_path

        base = Path(pkg_path[0])
        on_disk = {p.stem for p in base.glob("*.py")
                   if p.stem != "__init__" and not p.stem.startswith("_")}
        registered = {fn.__module__.rsplit(".", 1)[-1] for fn in ALL_ENGINES}
        self.assertEqual(on_disk, registered)

    def test_every_engine_is_callable(self):
        for engine in ALL_ENGINES:
            self.assertTrue(callable(engine), engine)
