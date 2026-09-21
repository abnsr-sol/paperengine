"""External-corpus overlap engine: published-literature reuse.

Fixtures come from ``tests/_fixtures.py`` where they are shared; the literature
double below is local because only this engine talks to Europe PMC.

Filler sentences are deliberately shorter than the engine's 12-word query floor,
so each test's distinctive sentence is the only thing that can be looked up —
which makes the assertions about *what was queried* exact rather than incidental.
"""
from __future__ import annotations
import json
import os
import urllib.parse
from unittest import TestCase, mock

from papercheck.checks import CheckContext
from papercheck.checks import external_overlap as eo
from papercheck.ingestion import Document

# Filler must be *varied*: the ratio signal is computed over unique 8-word
# phrases, so 22 copies of one sentence would collapse to ~25 phrases and
# inflate every share. Each sentence also stays under the 12-word query floor,
# so only a test's own sentence can ever be looked up.
_FILLER = " ".join(f"We thank reviewer number {i} for their time and attention."
                   for i in range(1, 26))

_DISTINCT = ("The carboxylate derivatives of tributyltin complexes exhibit selective "
             "antileishmanial activity against the promastigote stage of the parasite.")

_LONG = ("Organometallics including pentavalent antimonials and platinum derivatives have been "
         "used for over three decades for the management of leishmaniasis and several solid "
         "tumours respectively in clinical practice worldwide today, as our own laboratory "
         "recently reviewed.")


def _doc(*sentences: str, references=None) -> Document:
    return Document(path="m.txt", name="m.txt", file_type="txt",
                    text=_FILLER + " " + " ".join(sentences),
                    references=list(references or []))


def _hit(doi="10.1234/prior.2020", pmcid="PMC123", oa="Y",
         title="Prior organometallic antileishmanial study", journal="J Test", year="2020"):
    return {"doi": doi, "pmcid": pmcid, "isOpenAccess": oa, "title": title,
            "journalTitle": journal, "pubYear": year}


def _search(hits, results=None):
    return {"hitCount": hits, "resultList": {"result": results or []}}


def _abstract_index(text: str) -> dict:
    out: dict = {}
    for pos, word in enumerate(text.split()):
        out.setdefault(word, []).append(pos)
    return out


class _FakeNet:
    """Routes by URL substring, recording every lookup the engine makes."""

    def __init__(self, search=(), fulltext=(), openalex=()):
        self.search, self.fulltext, self.openalex = list(search), list(fulltext), list(openalex)
        self.calls: list = []

    @staticmethod
    def _match(needle, url):
        return needle in url

    def get_json(self, url, **kwargs):
        self.calls.append(url)
        for needle, response in self.search:
            if self._match(needle, url):
                return response
        for needle, response in self.openalex:
            if self._match(needle, url):
                return response
        return 404, None

    def get(self, url, **kwargs):
        self.calls.append(url)
        for needle, response in self.fulltext:
            if self._match(needle, url):
                return response
        return 404, None

    @property
    def searches(self):
        return [c for c in self.calls if "/search?" in c]


class _Base(TestCase):
    def setUp(self):
        self._pause = mock.patch.object(eo, "_PAUSE", 0)
        self._pause.start()
        self.addCleanup(self._pause.stop)

    @staticmethod
    def _patch(fake):
        return mock.patch.multiple("papercheck.net", get=fake.get, get_json=fake.get_json)


def _query_of(sentence: str) -> str:
    """The URL the engine builds for ``sentence`` (punctuation stripped, windowed)."""
    return eo._phrase_url(eo._query_window(sentence.rstrip(". ")))


class TestQueryWindows(_Base):
    def test_a_run_on_passage_is_queried_as_a_bounded_window(self):
        # Extracted text often glues two sentences together; querying the whole
        # run-on matches nothing, so only the leading window is looked up.
        run_on = ("The antitumour activity of the platinum complexes was measured in vitro "
                  "against three separate cell lines and then confirmed by a second laboratory "
                  "We thank the funding agency for the generous support that made this possible")
        fake = _FakeNet()
        with self._patch(fake):
            eo.run(_doc(run_on), CheckContext(online=True))
        self.assertTrue(fake.searches)
        for call in fake.searches:
            queried = urllib.parse.unquote(call.split("query=")[1].split("&")[0]).strip('""')
            self.assertLessEqual(len(queried.split()), eo._QUERY_WORDS)
            self.assertIn("antitumour activity", queried)
            self.assertNotIn("funding agency", queried)


class TestOfflineAndBudget(_Base):
    def test_offline_is_a_silent_noop(self):
        fake = _FakeNet()
        with self._patch(fake):
            self.assertEqual(eo.run(_doc(_DISTINCT), CheckContext(online=False)), [])
        self.assertEqual(fake.calls, [], "offline must not touch the network")

    def test_zero_budget_means_no_lookups(self):
        fake = _FakeNet()
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True, max_online_checks=0))
        self.assertEqual(out, [])
        self.assertEqual(fake.calls, [])

    def test_budget_bounds_the_number_of_lookups(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(7, [_hit()]))),
                                (_query_of(_LONG), (200, _search(9, [_hit()]))),
                                (_query_of("Our reproducibility analysis across laboratories "
                                           "was performed independently by a second group."),
                                 (200, _search(3, [])))])
        third = "Our reproducibility analysis across laboratories was performed independently by a second group."
        with self._patch(fake):
            eo.run(_doc(_DISTINCT, _LONG, third),
                   CheckContext(online=True, max_online_checks=2))
        self.assertLessEqual(len(fake.calls), 2)

    def test_short_document_is_skipped(self):
        fake = _FakeNet()
        doc = Document(path="s.txt", name="s.txt", file_type="txt", text=_DISTINCT)
        with self._patch(fake):
            self.assertEqual(eo.run(doc, CheckContext(online=True)), [])
        self.assertEqual(fake.calls, [])

    def test_identical_sentences_are_queried_once(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(1, [_hit()])))])
        with self._patch(fake):
            eo.run(_doc(_DISTINCT, _DISTINCT, _DISTINCT), CheckContext(online=True))
        self.assertEqual(len(fake.searches), 1, "a repeated sentence costs one lookup")


class TestWhatCountsAsEvidence(_Base):
    def test_boilerplate_phrasing_is_not_evidence(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(20044, [_hit()])))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertEqual([f.severity.value for f in out], ["Info"])
        self.assertIn("too common", out[0].detail)
        self.assertNotIn("Prior organometallic", out[0].evidence)

    def test_distinctive_match_names_the_source(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(1, [_hit()])))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity.value, "Low")
        self.assertIn("10.1234/prior.2020", out[0].evidence)
        self.assertIn("carboxylate derivatives", out[0].evidence)

    def test_cited_source_is_info_not_an_accusation(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(1, [_hit()])))])
        doc = _doc(_DISTINCT, references=["Smith J. Prior work. J Test. 2020. doi:10.1234/prior.2020"])
        with self._patch(fake):
            out = eo.run(doc, CheckContext(online=True))
        self.assertEqual(out[0].severity.value, "Info")
        self.assertIn("cites", out[0].title.lower())

    def test_long_verbatim_run_is_high(self):
        source = f"Introduction {_LONG} Materials and methods follow."
        fake = _FakeNet(
            search=[(_query_of(_LONG), (200, _search(1, [_hit()])))],
            fulltext=[("PMC123/fullTextXML",
                       (200, f"<article><body><p>{source}</p></body></article>".encode()))],
        )
        with self._patch(fake):
            out = eo.run(_doc(_LONG), CheckContext(online=True))
        self.assertEqual(out[0].severity.value, "High")
        self.assertIn("longest identical run", out[0].evidence)
        self.assertGreater(int(out[0].evidence.split("longest identical run: ")[1].split()[0]), 30)

    def test_repeated_passages_with_one_source_are_medium(self):
        second = ("Platinum derivatives of the same series were evaluated for cytotoxicity "
                  "against the promastigote stage of the parasite.")
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(2, [_hit()]))),
                                (_query_of(second), (200, _search(3, [_hit()])))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT, second), CheckContext(online=True))
        self.assertEqual(out[0].severity.value, "Medium")
        self.assertIn("2 distinctive passage", out[0].detail)

    def test_no_match_is_reported_as_info_not_silence(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(0)))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertEqual([f.severity.value for f in out], ["Info"])
        self.assertIn("No significant external text overlap", out[0].title)

    def test_extra_sources_are_summarised_not_dropped(self):
        results = [_hit(doi=f"10.1/{i}", pmcid=None, oa="N") for i in range(5)]
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(5, results)))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        titles = [f.title for f in out]
        self.assertEqual(len([t for t in titles if t == "Further external matches not itemised"]), 1)


class TestUnreachableNeverAccuses(_Base):
    def test_dead_network_is_disclosed_not_evidence(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (None, None))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertEqual([f.severity.value for f in out], ["Info"])
        self.assertIn("incomplete", out[0].title.lower())
        self.assertIn("not evidence of originality", out[0].detail)

    def test_throttling_is_disclosed_not_evidence(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (429, None))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertEqual([f.severity.value for f in out], ["Info"])
        self.assertIn("incomplete", out[0].title.lower())

    def test_a_real_404_on_the_search_is_not_a_network_failure(self):
        # 404 from the search endpoint is an answer; it must not be reported as
        # reduced coverage, because that would be a false disclosure.
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (404, None))])
        with self._patch(fake):
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertNotIn("incomplete", out[0].title.lower())

    def test_real_network_failure_path_is_integrated(self):
        """The real ``papercheck.net`` path, unmocked: a request that never
        completes must disclose reduced coverage, never accuse the manuscript."""
        def boom(*args, **kwargs):
            raise OSError("no network")

        with mock.patch("urllib.request.urlopen", side_effect=boom), \
                mock.patch("papercheck.net.time.sleep"):   # no real backoff waits
            out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertEqual([f.severity.value for f in out], ["Info"])
        self.assertIn("incomplete", out[0].title.lower())


class TestWhatIsNeverQueried(_Base):
    def test_quoted_material_is_not_queried(self):
        quoted = ('"The carboxylate derivatives of tributyltin complexes exhibit selective '
                  'antileishmanial activity in vitro"')
        fake = _FakeNet()
        with self._patch(fake):
            eo.run(_doc(_DISTINCT, quoted), CheckContext(online=True))
        self.assertTrue(all("carboxylate derivatives of tributyltin complexes exhibit selective "
                            "antileishmanial activity in vitro" not in urllib.parse.unquote(c)
                            for c in fake.searches))

    def test_bibliographic_sentences_are_not_queried(self):
        biblio = "Smith J, Jones A. doi:10.1234/prior.2020. Journal of Testing 2020;5:1-9."
        fake = _FakeNet()
        with self._patch(fake):
            eo.run(_doc(_DISTINCT, biblio), CheckContext(online=True))
        self.assertTrue(all("doi:" not in urllib.parse.unquote(c) for c in fake.searches))

    def test_the_references_block_is_never_queried(self):
        from papercheck.ingestion import Section

        body = _FILLER + " " + _DISTINCT
        refs = "Prior organometallic antileishmanial study 2020 with a very long distinctive title"
        doc = Document(path="m.txt", name="m.txt", file_type="txt", text=body + "\nReferences\n" + refs,
                       references=[refs],
                       sections=[Section(heading="References", body=refs, level=1,
                                         start_index=len(body))])
        fake = _FakeNet()
        with self._patch(fake):
            eo.run(doc, CheckContext(online=True))
        self.assertTrue(all("very%20long%20distinctive%20title" not in c for c in fake.searches))


class TestOpenAlexKey(_Base):
    def test_abstract_of_a_closed_source_is_checked_with_the_key(self):
        abstract = f"Abstract. {_DISTINCT}"
        other = _hit(doi="10.9999/closed.2021", pmcid=None, oa="N",
                     title="Closed access report on organotin chemistry")
        fake = _FakeNet(
            search=[(_query_of(_DISTINCT), (200, _search(1, [other])))],
            openalex=[("10.9999/closed.2021", (200, {"abstract_inverted_index":
                                                     _abstract_index(abstract)}))],
        )
        with mock.patch.dict(os.environ, {"OPENALEX_API_KEY": "test-key"}):
            with self._patch(fake):
                out = eo.run(_doc(_DISTINCT), CheckContext(online=True))
        self.assertTrue(any("api_key=test-key" in c for c in fake.calls),
                        "the configured OpenAlex key must be used")
        self.assertEqual(out[0].severity.value, "Low")
        self.assertIn("10.9999/closed.2021", out[0].evidence)

    def test_without_a_key_openalex_is_still_queried(self):
        other = _hit(doi="10.9999/closed.2021", pmcid=None, oa="N")
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(1, [other])))],
                        openalex=[("10.9999/closed.2021", (404, None))])
        env = {k: v for k, v in os.environ.items() if k != "OPENALEX_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self._patch(fake):
                eo.run(_doc(_DISTINCT), CheckContext(online=True))
        called = [c for c in fake.calls if "api.openalex.org" in c]
        self.assertEqual(len(called), 1)
        self.assertNotIn("api_key", called[0])


class TestEnquirer(_Base):
    def test_the_online_cache_prevents_a_second_lookup(self):
        fake = _FakeNet(search=[(_query_of(_DISTINCT), (200, _search(0)))])
        ctx = CheckContext(online=True)
        with self._patch(fake):
            eo.run(_doc(_DISTINCT), ctx)
            first = len(fake.calls)
            eo.run(_doc(_DISTINCT), ctx)
        self.assertEqual(len(fake.calls), first, "a cached URL must not be requested twice")

    def test_urls_are_well_formed(self):
        url = eo._phrase_url('a phrase with "quotes" and spaces')
        self.assertIn("%22", url)
        self.assertIn("format=json", url)
        self.assertNotIn(" ", url)

    def test_longest_shared_run_finds_the_real_overlap(self):
        manuscript = "alpha beta gamma delta epsilon zeta eta theta iota kappa".split()
        source = "xx yy " .split() + manuscript + "zz".split()
        self.assertEqual(eo._shared_run(manuscript, source, 3), 10)
        self.assertEqual(eo._shared_run(manuscript, ["nothing", "shared"], 3), 0)

    def test_plain_strips_markup(self):
        xml = b"<article><body><p>Hello <italic>world</italic>.</p></body></article>"
        self.assertEqual(eo._plain(xml), "Hello world .")
