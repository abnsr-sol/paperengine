"""Opt-in plain-language explainer powered by a local Ollama server.

Keeps the offline promise: everything stays on the machine. When Ollama is
not running (or the model is missing) every entry point returns ``None`` and
the CLI prints a one-line hint — the check run itself is never affected.

Usage:
    papercheck paper.docx --explain              # default model llama3.2
    PAPERCHECK_OLLAMA=http://127.0.0.1:11434     # custom host (env var)
    PAPERCHECK_OLLAMA_MODEL=qwen2.5              # custom model (env var)

The explainer never makes verdicts: the prompt pins it to plain-language
restatement of the finding plus concrete fix steps, mirroring the engine's
own action field. Findings remain the source of truth; the LLM only
rewrites them for a non-native-English or first-time author.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from .risk import Finding

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2"
_TIMEOUT = 20.0  # seconds per request; a slow/absent server must not hang the CLI

_SYSTEM = (
    "You are a manuscript pre-submission assistant. For each finding you are "
    "given, reply with: (1) one plain-language sentence saying what the issue "
    "is, (2) why an editor might care, (3) the single most useful fix. "
    "Never claim the manuscript is fraudulent or retracted; never invent "
    "facts beyond the finding text. Reply for each finding as "
    "'<n>. <explanation>' with no extra preamble."
)


def _host() -> str:
    return (os.environ.get("PAPERCHECK_OLLAMA") or DEFAULT_HOST).rstrip("/")


def _model() -> str:
    return os.environ.get("PAPERCHECK_OLLAMA_MODEL") or DEFAULT_MODEL


def ollama_available() -> bool:
    """True if a local Ollama server answers /api/tags within the timeout."""
    try:
        req = urllib.request.Request(_host() + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2.0):
            return True
    except Exception:
        return False


def explain_findings(findings: List[Finding], limit: int = 12) -> Optional[str]:
    """Return plain-language explanations for the top findings, or None.

    Returns None when Ollama is unreachable/errored so callers can fall back
    to the standard report with a one-line hint. Findings are truncated to
    ``limit`` to keep the prompt small and the reply readable.
    """
    if not findings:
        return None
    items = findings[:limit]
    prompt_lines = []
    for i, f in enumerate(items, 1):
        prompt_lines.append(
            f"{i}. [{f.severity.value}] {f.title} — {f.detail} "
            f"Evidence: {f.evidence}. Suggested action: {f.action}"
        )
    payload = json.dumps({
        "model": _model(),
        "system": _SYSTEM,
        "prompt": "\n".join(prompt_lines),
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 700},
    }).encode("utf-8")
    req = urllib.request.Request(
        _host() + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None
    text = (data.get("response") or "").strip()
    return text or None
