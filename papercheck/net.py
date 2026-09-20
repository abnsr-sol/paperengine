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
* **Never raise.** Callers get a ``(status, body)`` pair; a network fault can
  never crash a check or silently become a finding.
* **Identify ourselves.** A single User-Agent carrying the caller's contact
  address, because Crossref's polite pool gates on it.
* **Stay bounded.** Retries are capped so a hung endpoint cannot stall a report.
"""
from __future__ import annotations
import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Optional

from . import __version__

DEFAULT_TIMEOUT = 12.0
DEFAULT_RETRIES = 2          # 3 attempts total
_BASE_BACKOFF = 0.6          # seconds; doubles each retry
_MAX_BACKOFF = 8.0
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}

# Statuses that mean "we could not find out", as opposed to "the answer is no".
# A throttle, a block, or a server fault says nothing about whether a reference
# exists, so no engine may turn one into a finding about the manuscript.
_INDETERMINATE_STATUS = {401, 402, 403, 407, 408, 425, 429, 451}


def is_definitive(status: Optional[int]) -> bool:
    """True when ``status`` carries real information about the resource.

    ``None`` (never reached the server), throttling, blocking and 5xx are all
    indeterminate. 404/410 mean absent; 2xx means present.
    """
    if status is None:
        return False
    if status in _INDETERMINATE_STATUS or status >= 500:
        return False
    return True


def user_agent() -> str:
    """Identify the tool, with the caller's contact address for polite pools."""
    who = os.environ.get("PAPERCHECK_MAILTO", "").strip()
    tail = f"; mailto:{who}" if who else ""
    return f"paperengine/{__version__} (research integrity screener{tail})"


def _retry_after(headers) -> Optional[float]:
    """Seconds to wait, from a Retry-After header (integer-seconds form only)."""
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


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter, so a retry storm cannot synchronise."""
    return min(_BASE_BACKOFF * (2 ** (attempt - 1)), _MAX_BACKOFF) + random.uniform(0, 0.25)


def get(url: str, *, timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES, sleep=time.sleep):
    """GET ``url``. Returns ``(status, body)``.

    The distinction this exists to preserve:

    * ``(None, None)``  — the request never completed (DNS, timeout, TLS).
      We learned **nothing**; a caller must not treat this as a negative
      result. Engines that did treat it as one branded real references as
      "possible hallucination" whenever the network hiccuped.
    * ``(404, None)``   — the server answered: the thing really is absent.
      That *is* evidence.
    * ``(200, body)``   — a real response; body may still be empty.

    ``sleep`` is injectable so tests assert the backoff schedule without
    waiting.
    """
    headers = {"User-Agent": user_agent(), "Accept": "*/*"}
    attempt = 0
    while True:
        attempt += 1
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", None) or getattr(resp, "code", 200)
                return int(status), resp.read()
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", 0)
            if status in _RETRY_STATUS and attempt <= retries:
                wait = _retry_after(getattr(exc, "headers", None))
                sleep(wait if wait is not None else _backoff(attempt))
                continue
            # the server answered — that is information, not silence
            return int(status), None
        except Exception:  # URLError, timeout, DNS, TLS...
            if attempt <= retries:
                sleep(_backoff(attempt))
                continue
            return None, None


def get_json(url: str, *, timeout: float = DEFAULT_TIMEOUT,
             retries: int = DEFAULT_RETRIES, sleep=time.sleep):
    """``get`` plus a JSON decode. Returns ``(status, obj_or_None)``.

    ``(None, None)`` means the request never completed: callers must not read
    it as "not found". Malformed JSON on a 200 is reported as ``(200, None)``.
    """
    status, body = get(url, timeout=timeout, retries=retries, sleep=sleep)
    if body is None:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return status, None
