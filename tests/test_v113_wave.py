"""Tests for the v1.13.0 resource-integration wave:

- semantic_similarity: TF-IDF cosine overlap against a corpus (paraphrase-grade)
- image_deep_forensics: ELA decision logic + copy-move clone detection
- author_info: ORCID ISO 7064 MOD 11-2 checksum validation
- explain: Ollama explainer degrades gracefully when the server is absent
"""
import io
import os
import random
import sys
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document
from papercheck.checks import CheckContext
from papercheck.checks.semantic_similarity import run as semsim_run
from papercheck.checks import image_deep_forensics as idf
from papercheck.checks.author_info import _orcid_checksum_ok, run as author_info_run
from papercheck import explain


def _doc(text, name="t.txt", refs=None):
    return Document(path=name, name=name, file_type="txt",
                    text=text, references=refs or [])


PARAPHRASED_ORIGINAL = (
    "Deep learning models require large labeled datasets to achieve high accuracy. "
    "We present a novel augmentation strategy that synthesizes training examples "
    "by interpolating features in a learned embedding space. Experiments on three "
    "benchmark vision datasets show consistent improvements over strong baselines. "
    "Ablation studies confirm that the gains come from the embedding interpolation "
    "rather than the additional parameters. "
) * 4

REWORDING_COPY = (
    "To reach high accuracy, deep learning models require large annotated datasets. "
    "This work proposes a new augmentation strategy that synthesizes training examples "
    "via interpolation of features in a learned embedding space. Trials on three "
    "benchmark vision datasets show consistent gains over strong baselines. "
    "Ablation studies confirm the improvements come from embedding interpolation "
    "rather than from the added parameters. "
) * 4

# Aggressive synonym-for-synonym swap: deliberately beyond lexical matching.
# Embedding models (roadmap) close this gap; the engine must NOT fire here.
HARD_PARAPHRASE = (
    "Neural networks need abundant annotated data to reach strong performance. "
    "We introduce a fresh augmentation method that creates training samples "
    "through interpolation of features inside a learned representation space. "
    "Trials across three standard image benchmarks demonstrate stable gains over "
    "competitive baselines. Removal experiments verify that improvements stem "
    "from the representation interpolation, not from extra parameters. "
) * 4

UNRELATED = (
    "Soil salinity affects crop yield in arid regions. We surveyed 240 farms "
    "across two growing seasons and measured electrical conductivity at three "
    "depths. Regression analysis links salinity to irrigation water quality. "
    "Gypsum amendments reduced topsoil sodium concentration in field trials. "
    "Policy recommendations target fertilizer subsidy reform and drainage "
    "investment for smallholder cooperatives in the affected districts. "
) * 4


class TestSemanticSimilarity(unittest.TestCase):
    def _ctx(self, corpus):
        return CheckContext(corpus=corpus)

    def test_no_corpus_is_silent(self):
        self.assertEqual(semsim_run(_doc(PARAPHRASED_ORIGINAL), self._ctx([])), [])

    def test_short_text_is_silent(self):
        ctx = self._ctx([_doc(UNRELATED, name="c1.txt")])
        self.assertEqual(semsim_run(_doc("Too short to vectorize."), ctx), [])

    def test_reworded_copy_flags(self):
        corpus = [_doc(UNRELATED, name="soil.txt"), _doc(PARAPHRASED_ORIGINAL, name="prior.txt")]
        fs = semsim_run(_doc(REWORDING_COPY), self._ctx(corpus))
        self.assertTrue(fs, "reworded reuse must be flagged")
        self.assertIn("prior.txt", fs[0].evidence)

    def test_hard_paraphrase_is_documented_limitation(self):
        # Full synonym-swap evades lexical matching by design; the finding text
        # says embedding models close this gap. No false promise, no fire.
        corpus = [_doc(PARAPHRASED_ORIGINAL, name="prior.txt")]
        self.assertEqual(semsim_run(_doc(HARD_PARAPHRASE), self._ctx(corpus)), [])

    def test_unrelated_document_is_clean(self):
        corpus = [_doc(PARAPHRASED_ORIGINAL, name="prior.txt"), _doc(PARAPHRASED_ORIGINAL, name="p2.txt")]
        fs = semsim_run(_doc(UNRELATED), self._ctx(corpus))
        self.assertFalse(any(f.severity.value in ("High", "Critical") for f in fs))

    def test_verbatim_copy_flags_high(self):
        corpus = [_doc(PARAPHRASED_ORIGINAL, name="prior.txt")]
        fs = semsim_run(_doc(PARAPHRASED_ORIGINAL), self._ctx(corpus))
        self.assertTrue(fs)
        self.assertEqual(fs[0].severity.value, "High")


def _docx_with_images(images):
    """Minimal DOCX container: just the zip + word/media/* entries the engine reads."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for i, data in enumerate(images):
            zf.writestr(f"word/media/image{i}.png", data)
    return buf.getvalue()


def _png(img):
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


class TestImageDeepForensics(unittest.TestCase):
    def setUp(self):
        if not idf._HAS_PIL:
            self.skipTest("Pillow not installed")

    def _tmp_docx(self, images, tmpdir):
        path = os.path.join(tmpdir, "imgdoc.docx")
        with open(path, "wb") as fh:
            fh.write(_docx_with_images(images))
        return path

    def test_flat_image_produces_no_findings(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            flat = Image.new("L", (256, 256), 128)
            path = self._tmp_docx([_png(flat)], td)
            doc = Document(path=path, name="x.docx", file_type="docx", text="x")
            self.assertEqual(idf.run(doc, CheckContext()), [])

    def test_clone_detection_fires_on_periodic_texture(self):
        import tempfile
        from PIL import Image
        rng = random.Random(42)
        tile = bytes(rng.randrange(256) for _ in range(16 * 16))
        tiled = Image.frombytes("L", (256, 256),
                                bytes(tile * 16 * 16))
        with tempfile.TemporaryDirectory() as td:
            path = self._tmp_docx([_png(tiled)], td)
            doc = Document(path=path, name="x.docx", file_type="docx", text="x")
            fs = idf.run(doc, CheckContext())
        self.assertTrue(any("Repeated texture" in f.title for f in fs),
                        "periodic texture must trigger clone detection")

    def test_random_noise_image_is_clean(self):
        import tempfile
        from PIL import Image
        rng = random.Random(7)
        noise = Image.frombytes("L", (256, 256),
                                bytes(rng.randrange(256) for _ in range(256 * 256)))
        with tempfile.TemporaryDirectory() as td:
            path = self._tmp_docx([_png(noise)], td)
            doc = Document(path=path, name="x.docx", file_type="docx", text="x")
            fs = idf.run(doc, CheckContext())
        self.assertFalse(any("Repeated texture" in f.title for f in fs))

    def test_ela_decision_logic_high_ratio_fires_medium(self):
        from PIL import Image
        img = Image.new("L", (128, 128), 100)
        out = []
        original = idf._error_level_grid
        idf._error_level_grid = lambda _img: [[2, 2], [2, 10]]
        try:
            idf._ela_findings("splice.png", img, out)
        finally:
            idf._error_level_grid = original
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity.value, "Medium")

    def test_ela_decision_logic_low_ratio_silent(self):
        from PIL import Image
        img = Image.new("L", (128, 128), 100)
        out = []
        original = idf._error_level_grid
        idf._error_level_grid = lambda _img: [[5, 5], [6, 5]]
        try:
            idf._ela_findings("ok.png", img, out)
        finally:
            idf._error_level_grid = original
        self.assertEqual(out, [])


class TestOrcidChecksum(unittest.TestCase):
    def test_known_valid_orcid(self):
        # 0000-0002-1825-0097 is ORCID's canonical example (Josiah Carberry).
        self.assertTrue(_orcid_checksum_ok("0000-0002-1825-0097"))

    def test_single_digit_typo_fails(self):
        self.assertFalse(_orcid_checksum_ok("0000-0002-1825-0098"))

    def test_x_check_digit(self):
        # Find a valid iD ending in X by construction.
        self.assertTrue(_orcid_checksum_ok("0000-0002-1694-233X"))

    def test_wrong_length_fails(self):
        self.assertFalse(_orcid_checksum_ok("0000-0002-1825-009"))

    def test_engine_flags_invalid_orcid_in_document(self):
        text = ("Dr. Jane Doe\nDepartment of Biology, State University\n"
                "ORCID: 0000-0002-1825-0098\n jane@state.edu Corresponding author. " * 3)
        doc = Document(path="t.txt", name="t.txt", file_type="txt", text=text)
        fs = author_info_run(doc, CheckContext())
        self.assertTrue(any("ORCID" in f.title and "checksum" in f.title for f in fs))


class TestExplainDegradation(unittest.TestCase):
    def test_unreachable_server_returns_none(self):
        # Default host port 11434 is not running in CI; must return None, never raise.
        os.environ["PAPERCHECK_OLLAMA"] = "http://127.0.0.1:1"
        try:
            self.assertFalse(explain.ollama_available())
            self.assertIsNone(explain.explain_findings([]))
        finally:
            os.environ.pop("PAPERCHECK_OLLAMA", None)


if __name__ == "__main__":
    unittest.main()
