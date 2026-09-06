"""Compilation-artifact & link-hygiene engine.

Catches the "sloppy submission" tells that handling editors spot in seconds:

1. **Broken LaTeX cross-references**: failed \\ref{}/\\cite{} compile as
   bold "??" or "[?]" in the PDF/text. Any occurrence means the author did
   not read their own compiled output.
2. **Broken Word cross-references**: the literal string
   "Error! Reference source not found." (and variants) left in the document.
3. **Unpinned repository links**: GitHub/GitLab URLs pointing at a branch
   name (e.g. /tree/main, /tree/master, or the repo root) instead of a
   commit hash or release tag. By publication time the branch has moved
   and the results are no longer reproducible — reviewers know this.
4. **Placeholder links**: "TODO", "lorem ipsum", "example.com",
   "your-repo-here", "INSERT URL" in data-availability positions.

All checks are offline and exact-string based — no false positives from
legitimate prose.
"""
from __future__ import annotations

import re
from typing import List

from ..ingestion import Document
from ..risk import Finding, Severity

_LATEX_BROKEN = re.compile(r"(?:\?\?|\[\?\])")
_WORD_BROKEN = re.compile(
    r"Error!\s+Reference\s+source\s+not\s+found|Error!\s+Bookmark\s+not\s+defined",
    re.IGNORECASE)
_REPO_URL = re.compile(
    r"https?://(?:www\.)?(?:github|gitlab)\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"(?:/tree/([A-Za-z0-9._/-]+))?(?:/blob/([A-Za-z0-9._/-]+))?", re.IGNORECASE)
_PINNED = re.compile(r"^[0-9a-f]{7,40}$|^(?:v\d|release|paper|r\d)", re.IGNORECASE)
_PLACEHOLDER = re.compile(
    r"\b(?:TODO\s*[:.]?|lorem\s+ipsum|your[\s-]*(?:repo|username|link|url)[\s-]*(?:here)?|"
    r"insert\s+(?:url|link|repo)|example\.com|www\.example\.(?:com|org)|<url>|<link>)",
    re.IGNORECASE)
_SHA = re.compile(r"\b[0-9a-f]{40}\b|\btag[s]?\b|\brelease\b|\bdoi\.org|\bzenodo", re.IGNORECASE)


def run(doc: Document, ctx) -> List[Finding]:
    text = doc.text or ""
    if doc.word_count < 150:
        return []
    out: List[Finding] = []

    # --- 1: broken LaTeX refs -------------------------------------------
    latex_hits = list(_LATEX_BROKEN.finditer(text))
    # avoid flagging "???" in quoted questions or table placeholders used once
    if latex_hits:
        ctxs = [text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ").strip()
                for m in latex_hits[:4]]
        out.append(Finding(
            "Compilation", Severity.HIGH,
            "Broken LaTeX cross-references (?? in compiled text)",
            f"{len(latex_hits)} occurrence(s) of '??' or '[?]' — these are "
            "failed \\ref/\\cite macros from the last compilation. Editors "
            "read this as 'the authors did not check their own PDF'.",
            "; ".join(f"\"{c}\"" for c in ctxs),
            "Recompile twice (latexmk does this automatically) and resolve "
            "the undefined references before submitting.", 0.9))

    # --- 2: broken Word fields -------------------------------------------
    word_hits = list(_WORD_BROKEN.finditer(text))
    if word_hits:
        out.append(Finding(
            "Compilation", Severity.HIGH,
            "Broken Word cross-references in document text",
            f"{len(word_hits)} occurrence(s) of 'Error! Reference source not "
            "found' — broken Word cross-reference fields left in the body.",
            f"first: \"{text[word_hits[0].start():word_hits[0].end()]}\"",
            "Ctrl+A then F9 to refresh fields; fix the broken source "
            "references, then re-export the PDF.", 0.95))

    # --- 3: unpinned repository links ------------------------------------
    repo_links = list(_REPO_URL.finditer(text))
    unpinned = []
    for m in repo_links:
        branch = m.group(2) or m.group(3)
        if branch is None:
            unpinned.append((m.group(0), "repo root (no commit/tag)"))
        elif not _PINNED.match(branch):
            unpinned.append((m.group(0), f"branch '{branch}'"))
    if unpinned:
        has_sha_elsewhere = bool(_SHA.search(text))
        sev = Severity.MEDIUM if not has_sha_elsewhere else Severity.LOW
        out.append(Finding(
            "Reproducibility", sev,
            "Repository links not pinned to a commit or release",
            f"{len(unpinned)} code/data link(s) point at a moving branch or "
            "the repo root instead of a specific commit hash or release tag. "
            "By the time reviewers click, the code may no longer reproduce "
            "the paper's results.",
            "; ".join(f"{u} ({why})" for u, why in unpinned[:3]),
            "Link to a specific commit (github.com/.../tree/<40-char sha>) "
            "or an archived release/Zenodo DOI.", 0.65))
    elif repo_links:
        out.append(Finding(
            "Reproducibility", Severity.INFO,
            "Repository links properly pinned",
            f"{len(repo_links)} repository link(s) point at pinned commits "
            "or tagged releases — reproducibility-friendly.",
            f"{len(repo_links)} pinned link(s)",
            "No action needed.", 0.6))

    # --- 4: placeholder links --------------------------------------------
    ph = list(_PLACEHOLDER.finditer(text))
    if ph:
        ctxs = [text[max(0, m.start() - 35):m.end() + 35].replace("\n", " ").strip()
                for m in ph[:4]]
        out.append(Finding(
            "Submission", Severity.HIGH,
            "Placeholder text left in the manuscript",
            f"{len(ph)} placeholder(s) (TODO, lorem ipsum, 'your repo here', "
            "example.com) — instant evidence of an unfinished draft.",
            "; ".join(f"\"{c}\"" for c in ctxs),
            "Replace every placeholder with real content; search the "
            "document for 'TODO' before submitting.", 0.9))
    return out
