"""v1.14b hardening wave.

Covers the three failure classes fixed together:

1. **Network behaviour** — ``papercheck.net`` retries throttling, and never
   turns a 429 or a dead network into a fabricated "this DOI does not exist"
   finding.
2. **Container coverage** — ``papercheck.media`` is the single owner of image
   extraction; ``image_manipulation`` used to skip PDFs entirely.
3. **Image false positives** — a perceptual hash carries no information on a
   near-flat figure, so blank/pale figures must not be reported as duplicates;
   the inverted quadrant "copy-move" heuristic must stay deleted, and clone
   detection must stay owned by one engine.

Fixtures come from ``tests/_fixtures.py``.
"""
from __future__ import annotations
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from papercheck import media, net
from tests._fixtures import (Response, flat, http_error, png, texture,
                             texture_jpeg, write_docx, write_pdf)


# --------------------------------------------------------------------------
# 1. network behaviour
# --------------------------------------------------------------------------
class TestHttpRetryLayer(unittest.TestCase):
    def test_retries_429_then_succeeds(self):
        sleeps = []
        side = [http_error(429), Response(b'{"ok":true}')]
        with mock.patch("urllib.request.urlopen", side_effect=side):
            result = net.get("http://x", sleep=sleeps.append)
        self.assertEqual(result, (200, b'{"ok":true}'))
        self.assertEqual(len(sleeps), 1, "should have backed off exactly once")

    def test_exhausted_throttle_is_reported_not_silent(self):
        """A 429 is information ("we were throttled"), never "not found"."""
        with mock.patch("urllib.request.urlopen", side_effect=http_error(429)) as m:
            result = net.get("http://x", retries=2, sleep=lambda s: None)
        self.assertEqual(result, (429, None))
        self.assertEqual(m.call_count, 3, "initial attempt + 2 retries")

    def test_honours_retry_after_header(self):
        sleeps = []
        side = [http_error(429, retry_after="2.5"), Response(b"{}")]
        with mock.patch("urllib.request.urlopen", side_effect=side):
            net.get("http://x", sleep=sleeps.append)
        self.assertEqual(sleeps, [2.5])

    def test_404_is_terminal_and_not_retried(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)) as m:
            result = net.get("http://x", sleep=lambda s: None)
        self.assertEqual(result, (404, None))
        self.assertEqual(m.call_count, 1, "a missing resource must not be retried")

    def test_5xx_is_retried(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(503)) as m:
            net.get("http://x", retries=1, sleep=lambda s: None)
        self.assertEqual(m.call_count, 2)

    def test_transport_error_never_raises(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("dns fail")):
            self.assertEqual(net.get("http://x", sleep=lambda s: None), (None, None))

    def test_backoff_grows(self):
        sleeps = []
        with mock.patch("urllib.request.urlopen", side_effect=http_error(500)):
            net.get("http://x", retries=3, sleep=sleeps.append)
        self.assertEqual(len(sleeps), 3)
        # jitter is added, but the schedule must still be increasing overall
        self.assertLess(sleeps[0], sleeps[2])

    def test_malformed_json_on_a_200_is_not_a_finding(self):
        with mock.patch("urllib.request.urlopen", return_value=Response(b"not json")):
            self.assertEqual(net.get_json("http://x", sleep=lambda s: None), (200, None))

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
            write_docx(p, [("z.png", png(flat(64, 0))), ("a.png", png(flat(64, 1)))])
            names = [n for n, _ in media.extract_images(p, "docx")]
            self.assertEqual(names, sorted(names))

    def test_reads_pdf_images(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.pdf")
            write_pdf(p, [texture_jpeg(1), texture_jpeg(1)])
            self.assertEqual(len(media.extract_images(p, "pdf")), 2)

    def test_limit_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.docx")
            write_docx(p, [(f"{i}.png", png(flat(64, i))) for i in range(5)])
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
            write_pdf(p, [texture_jpeg(4)])
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
            write_docx(p, items)
            findings, errors = run_all_engines(load_document(p), CheckContext())
        self.assertEqual(errors, [])
        return [f for f in findings if f.category == "Figures"]

    def test_pale_uniform_figures_are_not_duplicates(self):
        # a plot on a white background + a pale gel lane: both hash to ~zero bits
        diag = flat(128, 255)
        diag.paste(200, (0, 64, 128, 128))
        figs = self._figures([("a.png", png(diag)), ("b.png", png(flat(128, 230)))])
        self.assertEqual(figs, [],
                         "uniform figures must not be reported as duplicates")

    def test_byte_identical_flat_figure_is_reported(self):
        same = png(flat(128, 230))
        figs = self._figures([("a.png", same), ("b.png", same)])
        self.assertTrue(figs, "the same flat file twice is a real duplicate")

    def test_informative_hash_gate(self):
        from papercheck.checks.image_forensics import _is_informative, _rotate_hashes

        self.assertFalse(_is_informative(_rotate_hashes(png(flat(128, 128)))))
        self.assertTrue(_is_informative(_rotate_hashes(png(texture(0)))))

    def test_inverted_quadrant_detector_is_gone(self):
        """Guard against reintroducing the heuristic that flagged flat figures."""
        import papercheck.checks.image_manipulation as IM

        self.assertFalse(hasattr(IM, "_copy_move"),
                         "the quadrant copy-move heuristic is inverted; do not reintroduce it")

    def test_clone_detection_owned_by_deep_forensics(self):
        import papercheck.checks.image_deep_forensics as DEEP

        img = texture(3, lo=60, hi=200)
        block = texture(9, size=32, lo=40, hi=220)
        img.paste(block, (16, 16))
        img.paste(block, (80, 80))           # duplicated region
        out = []
        DEEP._clone_findings("x.png", img, out)
        self.assertTrue(out, "the real clone must still be detected")

    def test_blank_image_is_not_a_clone(self):
        import papercheck.checks.image_deep_forensics as DEEP

        out = []
        DEEP._clone_findings("x.png", flat(128, 128), out)
        self.assertEqual(out, [], "a uniform panel has no clone signature")


if __name__ == "__main__":
    unittest.main()
