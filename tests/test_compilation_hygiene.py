"""Tests for the compilation-hygiene engine (broken refs, unpinned repos, placeholders)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.ingestion import load_document  # noqa: E402
from papercheck.checks import compilation_hygiene  # noqa: E402

_PAD = ("We study the reproducibility of learned models on benchmark "
        "datasets with careful evaluation protocols. " * 12)


def _doc(body: str):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body)
        path = f.name
    try:
        return load_document(path)
    finally:
        os.unlink(path)


class TestCompilationHygiene(unittest.TestCase):
    def test_broken_latex_refs(self):
        doc = _doc(_PAD + "As shown in ??, accuracy improves; see Table [?].")
        finds = compilation_hygiene.run(doc, None)
        self.assertTrue(any("cross-references" in f.title for f in finds),
                        [f.title for f in finds])

    def test_broken_word_fields(self):
        doc = _doc(_PAD + "As discussed in Error! Reference source not found., "
                   "the method applies broadly.")
        finds = compilation_hygiene.run(doc, None)
        self.assertTrue(any("Word cross-references" in f.title for f in finds))

    def test_unpinned_repo(self):
        doc = _doc(_PAD + "Code: https://github.com/user/project/tree/main")
        finds = compilation_hygiene.run(doc, None)
        self.assertTrue(any("pinned" in f.title.lower() for f in finds))

    def test_unpinned_repo_root(self):
        doc = _doc(_PAD + "Code: https://github.com/user/project")
        finds = compilation_hygiene.run(doc, None)
        self.assertTrue(any("pinned" in f.title.lower() for f in finds))

    def test_pinned_commit_info(self):
        doc = _doc(_PAD + "Code: https://github.com/user/project/tree/"
                   "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")
        finds = compilation_hygiene.run(doc, None)
        self.assertTrue(any(f.severity.value == "Info" and "pinned" in f.title.lower()
                            for f in finds), [f.title for f in finds])
        self.assertFalse(any(f.severity.value == "Medium" for f in finds))

    def test_placeholders(self):
        doc = _doc(_PAD + "The dataset is available at TODO. Contact us at "
                   "someone@example.com for the link.")
        finds = compilation_hygiene.run(doc, None)
        self.assertTrue(any("Placeholder" in f.title for f in finds))

    def test_clean_document_no_compilation_findings(self):
        doc = _doc(_PAD + "Section 3 describes the method. Code is available "
                   "at https://github.com/user/project/tree/v1.0.0 (release tag).")
        finds = compilation_hygiene.run(doc, None)
        # may contain the INFO pinned finding, nothing worse
        self.assertFalse(any(f.severity.value in ("High", "Medium") for f in finds),
                         [f.title for f in finds])


if __name__ == "__main__":
    unittest.main()
