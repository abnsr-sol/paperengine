"""v1.14 wave: rotation/scale-invariant image duplication, PubPeer screening
contract, API-key config plumbing, and the engine-registry self-check.

Fixtures come from ``tests/_fixtures.py`` — the single owner of the synthetic
containers, images and HTTP stubs, so no module carries a private copy.
"""
from __future__ import annotations
import os
import tempfile
from unittest import TestCase, mock

from papercheck.checks import ALL_ENGINES, CheckContext, run_all_engines
from papercheck.ingestion import Document, load_document
from tests._fixtures import (flat, png, replay, rescaled, rotated, texture_jpeg,
                             texture_png, write_docx, write_pdf)


def _figure_findings(path):
    findings, errors = run_all_engines(load_document(path), CheckContext())
    return [f for f in findings if f.category == "Figures"], errors


class TestImageDuplication(TestCase):
    def _run_docx(self, second: bytes):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "paper.docx")
            write_docx(path, [("a.png", texture_png(7)), ("b.png", second)])
            return _figure_findings(path)

    def test_exact_duplicate_fires_high(self):
        figs, errors = self._run_docx(texture_png(7))
        self.assertEqual(errors, [])
        self.assertTrue(figs, "identical images must be reported")
        self.assertEqual(figs[0].severity.value, "High")

    def test_rotated_duplicate_fires(self):
        # the real-world evasion the old single-orientation hash missed
        figs, errors = self._run_docx(rotated(texture_png(7), 90))
        self.assertEqual(errors, [])
        self.assertTrue(figs, "a 90-degree rotated copy must still be caught")

    def test_rotated_270_duplicate_fires(self):
        figs, _ = self._run_docx(rotated(texture_png(7), 270))
        self.assertTrue(figs, "a 270-degree rotated copy must still be caught")

    def test_rescaled_duplicate_fires(self):
        figs, _ = self._run_docx(rescaled(texture_png(7)))
        self.assertTrue(figs, "a rescaled copy must still be caught")

    def test_different_images_are_silent(self):
        figs, errors = self._run_docx(texture_png(99))
        self.assertEqual(errors, [])
        self.assertEqual(figs, [], "unrelated panels must not be flagged")

    def test_single_image_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "one.docx")
            write_docx(path, [("a.png", texture_png(7))])
            figs, errors = _figure_findings(path)
        self.assertEqual(figs, [])
        self.assertEqual(errors, [])

    def test_tiny_icons_are_ignored(self):
        figs, _ = self._run_docx(png(flat(16, 0)))
        self.assertEqual(figs, [], "16px icons are not figure panels")

    def test_identical_pdfs_fire(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "two.pdf")
            write_pdf(path, [texture_jpeg(7), texture_jpeg(7)])
            figs, errors = _figure_findings(path)
        self.assertEqual(errors, [])
        self.assertTrue(figs, "duplicate embedded PDF images must fire")

    def test_different_pdfs_silent(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "diff.pdf")
            write_pdf(path, [texture_jpeg(7), texture_jpeg(99)])
            figs, errors = _figure_findings(path)
        self.assertEqual(errors, [])
        self.assertEqual(figs, [])

    def test_min_hamming_separates_cleanly(self):
        from papercheck.checks.image_forensics import _min_hamming, _rotate_hashes

        same_a = _rotate_hashes(texture_png(7))
        same_b = _rotate_hashes(texture_png(7))
        other = _rotate_hashes(texture_png(99))
        self.assertEqual(_min_hamming(same_a, same_b), 0)
        self.assertGreater(_min_hamming(same_a, other), 6)


class TestPubPeerScreening(TestCase):
    """The online path is this engine's whole purpose, so it is pinned here.

    It used to raise ``AttributeError`` on every document with references
    (``ref.text`` on what is in fact a plain string), so the engine never once
    produced a finding online — and both original tests were offline, so
    nothing caught it.
    """

    _REF = ("Smith J. A real published paper. Journal of Things. 2020. "
            "doi:10.1234/real.2020")

    def _doc(self):
        return Document(path="x.txt", name="x.txt", file_type="txt",
                        text="Body text.", references=[self._REF])

    def _online(self, payload):
        with mock.patch("urllib.request.urlopen", side_effect=replay(payload)):
            return run_all_engines(self._doc(), CheckContext(online=True))

    @staticmethod
    def _pp(findings):
        return [f for f in findings if getattr(f, "source", "") == "pubpeer_screening"]

    def test_offline_is_a_silent_noop(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "paper.docx")
            write_docx(path, [])
            findings, errors = run_all_engines(
                load_document(path), CheckContext(online=False))
        self.assertEqual(errors, [])
        self.assertEqual(self._pp(findings), [],
                         "no network work may happen when offline")

    def test_engine_does_not_touch_network_when_offline(self):
        import papercheck.checks.pubpeer_screening as pp

        doc = load_document(os.path.join(os.path.dirname(__file__), "..",
                                         "sample_paper.txt"))
        with mock.patch("urllib.request.urlopen") as m:
            pp.run(doc, CheckContext(online=False))
            m.assert_not_called()

    def test_discussed_reference_is_reported(self):
        findings, errors = self._online({"comment_count": 5})
        self.assertEqual(errors, [], "the online path must not crash")
        pp = self._pp(findings)
        self.assertEqual([f.severity.value for f in pp], ["Low"])
        self.assertIn("10.1234/real.2020", pp[0].evidence)

    def test_undiscussed_reference_is_silent(self):
        findings, errors = self._online({"comment_count": 0})
        self.assertEqual(errors, [])
        self.assertEqual(self._pp(findings), [])

    def test_unreachable_discloses_coverage_not_silence(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("down")):
            findings, errors = run_all_engines(self._doc(), CheckContext(online=True))
        self.assertEqual(errors, [])
        self.assertEqual([f.severity.value for f in self._pp(findings)], ["Info"])

    def test_candidate_extraction_finds_doi(self):
        import papercheck.checks.pubpeer_screening as pp

        cands = pp._candidates("Smith 2020. doi 10.1234/example.2020 and more text")
        self.assertIn("https://doi.org/10.1234/example.2020", cands)

    def test_comment_count_parsed_from_json(self):
        import papercheck.checks.pubpeer_screening as pp

        with mock.patch("urllib.request.urlopen",
                        side_effect=replay({"comment_count": 3})):
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
