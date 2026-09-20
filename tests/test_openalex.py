"""Tests for the OpenAlex online verification engine (mocked HTTP; offline no-op)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.ingestion import load_document  # noqa: E402
from papercheck.checks import ALL_ENGINES, CheckContext  # noqa: E402
from papercheck.checks import openalex_verify as oa  # noqa: E402

_PAD = "We study the effect of training on recall performance across groups. " * 12
_REFS = ("\nReferences\n"
         "[1] Smith, J. (2020) A study of memory. Journal of Memory, 1(2), 3-4. "
         "https://doi.org/10.1000/real.2020\n"
         "[2] Jones, A. (2021) More memory studies. J. Memory II, 5(1), 1-9. "
         "https://doi.org/10.1000/real.2021\n")


def _doc():
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(_PAD + "\n" + _REFS)
        path = f.name
    try:
        return load_document(path)
    finally:
        os.unlink(path)


def _engine():
    for e in ALL_ENGINES:
        if getattr(e, "__module__", "").endswith("openalex_verify"):
            return e
    raise AssertionError("openalex engine not registered")


class TestOpenAlexOffline(unittest.TestCase):
    def test_offline_is_noop(self):
        self.assertEqual(_engine()(_doc(), CheckContext(online=False)), [])


class TestOpenAlexOnline(unittest.TestCase):
    def _run(self, fake_fetch, ctx=None):
        ctx = ctx or CheckContext(online=True, max_online_checks=5)
        with mock.patch.object(oa, "_fetch", side_effect=fake_fetch):
            return _engine()(_doc(), ctx)

    # _fetch yields (status, payload). The status is what separates "the graph
    # says this work is absent" from "we could not ask" — only the former may
    # become a finding about the manuscript.

    def test_retracted_reference_flags_critical(self):
        def fake(path, params=""):
            if path == "/works" and "doi:" in params:
                return 200, {"results": [{"display_name": "A study", "is_retracted": True,
                                           "publication_year": 2020, "cited_by_count": 5}]}
            return 200, {"results": []}
        finds = self._run(fake)
        self.assertTrue(any(f.severity.value == "Critical" and "retracted" in f.title.lower()
                            for f in finds), [f.title for f in finds])

    def test_unresolved_references_flag(self):
        def fake(path, params=""):
            return 200, {"results": []}   # authoritative: no such work
        finds = self._run(fake)
        self.assertTrue(any("unresolved" in f.title.lower() for f in finds),
                        [f.title for f in finds])

    def test_throttled_lookup_never_accuses_the_references(self):
        """A 429 is not evidence: it must not create a hallucination finding."""
        def fake(path, params=""):
            return 429, None              # throttled by the API
        finds = self._run(fake)
        self.assertFalse(
            any(f.severity.value in ("High", "Critical") for f in finds),
            "throttling must never be reported as an integrity problem: "
            + str([f.title for f in finds]))
        self.assertTrue(any("unreachable" in f.title.lower() for f in finds),
                        "reduced coverage must be disclosed: "
                        + str([f.title for f in finds]))

    def test_unreachable_lookup_never_accuses_the_references(self):
        def fake(path, params=""):
            return None, None             # network never answered
        finds = self._run(fake)
        self.assertFalse(any(f.severity.value in ("High", "Critical") for f in finds),
                         str([f.title for f in finds]))

    def test_clean_resolution_info(self):
        def fake(path, params=""):
            if path == "/works":
                return 200, {"results": [{"display_name": "A study of memory",
                                          "is_retracted": False, "publication_year": 2020,
                                          "cited_by_count": 12}]}
            return 404, None
        finds = self._run(fake)
        self.assertTrue(any(f.severity.value == "Info" for f in finds),
                        [f.title for f in finds])
        self.assertFalse(any(f.severity.value == "Critical" for f in finds))

    def test_api_key_from_env(self):
        os.environ["OPENALEX_API_KEY"] = "test-key-123"
        try:
            self.assertIn("api_key=test-key-123", oa._key_param())
        finally:
            del os.environ["OPENALEX_API_KEY"]
        self.assertEqual(oa._key_param(), "")

    def test_title_extraction(self):
        t = oa._title_of("Smith, J. (2020) A study of memory. Journal of Memory, 1(2), 3-4.")
        self.assertIn("study of memory", t.lower())


if __name__ == "__main__":
    unittest.main()
