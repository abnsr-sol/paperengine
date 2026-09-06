"""Optional real-grammar engine backed by a local LanguageTool server.

Silently skips unless a server responds at LT_URL (env var) or
http://localhost:8081 within 1.5 s. The probe result is cached per context so
batch runs only probe once. This is a *local* service: your paper never
leaves your machine unless you point LT_URL at a remote host.

Start a server (any of):
    docker run -d -p 8081:8010 ErikWegner/languagetool-http
    java -jar languagetool-server.jar --port 8081
    LT_URL=http://myhost:8010 papercheck paper.docx   (remote)

Findings are MEDIUM confidence by design: grammar engines over-flag academic
style; every hit is a suggestion, not an error.
"""
from __future__ import annotations
import json
import os
import re
import urllib.request
from typing import List
from ..ingestion import Document
from ..risk import Finding, Severity

_TIMEOUT = 1.5
_CHUNK = 15000  # characters per API call


def _f(title, detail, evidence, action):
    return Finding("Grammar", Severity.MEDIUM, title, detail, evidence, action, 0.60)


def _server_url() -> str:
    return os.environ.get("LT_URL", "http://localhost:8081").rstrip("/")


def _probe() -> bool:
    try:
        req = urllib.request.Request(_server_url() + "/v2/languages",
                                     headers={"User-Agent": "papercheck/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT):
            return True
    except Exception:
        return False


def _check_chunk(text: str, mailto: str) -> List[dict]:
    payload = json.dumps({
        "text": text,
        "language": "en-US",
        "level": "picky",
        "enabledOnly": False,
    }).encode("utf-8")
    url = _server_url() + "/v2/check"
    if mailto:
        url += "?username=" + urllib.parse.quote(mailto)
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "papercheck/1.0"})
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return json.loads(resp.read().decode("utf-8", "replace")).get("matches", [])


import urllib.parse  # noqa: E402  (used above)


def run(doc: Document, ctx: object) -> List[Finding]:
    text = doc.body_text or doc.text or ""
    if not text:
        return []
    cache = getattr(ctx, "online_cache", None)
    cache_key = "_lt_server_ok"
    if cache is not None and cache_key in cache:
        ok = cache[cache_key]
    else:
        ok = _probe()
        if cache is not None:
            cache[cache_key] = ok
    if not ok:
        # Discoverability (limitation fix): the heuristic language engine runs
        # regardless, but real grammar checking is strictly better. Surface a
        # one-line INFO with the fastest setup path instead of staying silent.
        return [Finding(
            "Grammar", Severity.INFO,
            "Deeper grammar check available (LanguageTool not detected)",
            "The built-in grammar heuristics ran, but a local LanguageTool server "
            "would add full grammar-rule checking (agreements, style, punctuation "
            "rules). One command, still 100% local:",
            "probe: " + _server_url() + " did not respond within " + str(_TIMEOUT) + "s",
            "docker run -d -p 8081:8010 ErikWegner/languagetool-http  "
            "then re-run papercheck — it is picked up automatically",
            0.95,
        )]

    out: List[Finding] = []
    counts: dict = {}
    examples: dict = {}
    mailto = getattr(ctx, "mailto", "") or ""
    for start in range(0, len(text), _CHUNK):
        chunk = text[start:start + _CHUNK]
        try:
            matches = _check_chunk(chunk, mailto)
        except Exception:
            return out  # server died mid-run: report what we have
        for m in matches:
            rule = (m.get("rule") or {})
            rid = rule.get("id", "UNKNOWN")
            cat = ((rule.get("category") or {}).get("name", "Grammar"))
            counts[cat] = counts.get(cat, 0) + 1
            if cat not in examples:
                off = m.get("offset", 0)
                length = m.get("length", 0)
                snippet = chunk[off:off + max(length, 40)].strip()
                examples[cat] = (rid, snippet[:80], (m.get("message") or "")[:200])
    if not counts:
        return out
    total = sum(counts.values())
    worst = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    detail = "; ".join(f"{name}: {n}" for name, n in worst)
    ev_parts = []
    for name, (rid, snippet, msg) in list(examples.items())[:3]:
        ev_parts.append(f"{name} [{rid}] '{snippet}' - {msg}")
    out.append(_f(
        "Real-grammar check found " + str(total) + " potential issues",
        "LanguageTool (" + detail + "). Grammar engines over-flag academic style; treat every hit as a suggestion to review.",
        " | ".join(ev_parts),
        "Review each LanguageTool hit in context and accept only those that genuinely improve clarity"))
    # one aggregated finding keeps the report readable; per-issue listing lives in evidence
    return out