"""Outbound HTTP — one owner for every online request PaperEngine makes.

Before this module each engine called ``urllib.request.urlopen`` directly, so
"how do we behave when the network is unhappy" was answered differently (or
not at all) in each place. The failure that matters in the real world is the
rate limit: with a free OpenAlex key a batch run of a few hundred manuscripts
*will* meet ``429``, and the previous code treated that exactly like "this DOI
does not exist" — turning a throttle into a fabricated integrity finding.

Rules enforced here, uniformly:

* **Retry what is retryable.** ``429`` and ``5xx`` are retried with exponential
  backoff and jitter, honouring ``Retry-After`` when the server sends it.
  ``404``/``400`` are terminal — the resource really is absent.
* **Never raise.** Callers get ``bytes``/``dict`` or ``None``; a network fault
  can never crash a check or silently become a finding.
* **Identify ourselves.** A single User-Agent with the caller's contact address,
  because Crossref's polite pool gates on it.
* **Stay bounded.** Retries are capped so a hung endpoint cannot stall a report.

Set ``PAPERCHECK_HTTP_TRACE=1`` to log every attempt to stderr when diagnosing.
"""
from __future__ import annotations
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional

VERSION = "1.14"
DEFAULT_TIMEOUT = 12.0
DEFAULT_RETRIES = 2          # 3 attempts total
_BASE_BACKOFF = 0.6          # seconds; doubles each retry
_MAX_BACKOFF = 8.0
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def contact() -> str:
    """Contact address for polite API pools (Crossref asks for one)."""
    return os.environ.get("PAPERCHECK_MAILTO", "").strip()


def user_agent() -> str:
    who = contact()
    tail = f"; mailto:{who}" if who else ""
    return f"paperengine/{VERSION} (research integrity screener{tail})"


def _trace(msg: str) -> None:
    if os.environ.get("PAPERCHECK_HTTP_TRACE"):
        print(f"[net] {msg}", file=sys.stderr)


def _retry_after(headers) -> Optional[float]:
    """Seconds to wait, from a Retry-After header (int seconds form only)."""
    try:
        raw = headers.get("Retry-After")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except ValueError:
        return None  # HTTP-date form: fall back to exponential backoff


def fetch(url: str, headers: Optional[Dict[str, str]] = None, *,
          timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES,
          sleep=time.sleep) -> Optional[bytes]:
    """GET ``url`` with retry/backoff. Returns body bytes, or None.

    ``sleep`` is injectable so tests can assert the backoff schedule without
    actually waiting.
    """
    merged = {"User-Agent": user_agent(), "Accept": "*/*"}
    if headers:
        merged.update(headers)
    attempt = 0
    while True:
        attempt += 1
        try:
            req = urllib.request.Request(url, headers=merged)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", 0)
            if status in _RETRY_STATUS and attempt <= retries:
                wait = _retry_after(getattr(exc, "headers", None))
                if wait is None:
                    wait = min(_BASE_BACKOFF * (2 ** (attempt - 1)), _MAX_BACKOFF)
                    wait += random.uniform(0, 0.25)  # jitter: avoid thundering herd
                _trace(f"{status} on attempt {attempt}, retrying in {wait:.2f}s: {url}")
                sleep(wait)
                continue
            _trace(f"{status} terminal: {url}")
            return None
        except Exception as exc:  # URLError, timeout, DNS, TLS...
            if attempt <= retries:
                wait = min(_BASE_BACKOFF * (2 ** (attempt - 1)), _MAX_BACKOFF)
                wait += random.uniform(0, 0.25)
                _trace(f"{type(exc).__name__} on attempt {attempt}, "
                       f"retrying in {wait:.2f}s: {url}")
                sleep(wait)
                continue
            _trace(f"{type(exc).__name__} terminal: {url}")
            return None


def fetch_json(url: str, headers: Optional[Dict[str, str]] = None, *,
               timeout: float = DEFAULT_TIMEOUT,
               retries: int = DEFAULT_RETRIES, sleep=time.sleep) -> Optional[dict]:
    """``fetch`` + JSON decode. Malformed JSON yields None, not an exception."""
    body = fetch(url, headers, timeout=timeout, retries=retries, sleep=sleep)
    if body is None:
        return None
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None


def with_query(url: str, params: Dict[str, str]) -> str:
    """Append query parameters, skipping empty values."""
    parts = [(k, v) for k, v in params.items() if v not in (None, "")]
    if not parts:
        return url
    sep = "&" if "?" in url else "?"
    return url + sep + urllib.parse.urlencode(parts)
