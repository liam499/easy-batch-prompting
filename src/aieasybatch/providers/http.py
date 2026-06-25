"""Shared HTTP for provider adapters — standard library only (``urllib``).

This is the one place the network lives, so every adapter inherits the same three
hard-won behaviours:

1. **Proxy bypass.** Some egress proxies strip the ``Authorization`` header, and every
   provider authenticates with it — so we build an opener that ignores any ambient
   ``HTTPS_PROXY`` and connects directly.
2. **Smart retry.** Exponential backoff, but *only* on transient failures (429 and 5xx
   and network/timeout). A permanent 4xx (bad model id, bad params, bad key) raises
   immediately — never burn a worker slot retrying something that cannot succeed. (The
   original engine only got this right in one of its three adapters; centralising it
   fixes it everywhere at once.)
3. **Useful errors.** The response body is surfaced in the exception message, and the
   exception carries ``.code``, ``.transient`` and ``.attempts`` so the core can record
   *why* a cell failed and whether a later ``--resume`` should retry it.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

# Connect directly, bypassing any ambient HTTPS_PROXY (see note 1 above).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class HttpError(RuntimeError):
    def __init__(self, message, *, code=None, transient=False, attempts=None):
        super().__init__(message)
        self.code = code
        self.transient = transient
        self.attempts = attempts


def request_bytes(url, *, headers=None, data=None, method="POST",
                  timeout=60.0, max_retries=4) -> bytes:
    """Send a request and return the raw response bytes (the base for everything else).

    ``data`` is sent verbatim (already-encoded body, or ``None`` for GET). Raises
    ``HttpError`` on failure, after exhausting retries for transient errors. Used
    directly by the batch bridge for multipart uploads and JSONL downloads.
    """
    hdrs = dict(headers or {})
    delay, last = 2.0, None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with _OPENER.open(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            code = e.code
            transient = (code == 429 or 500 <= code < 600)
            try:
                detail = e.read().decode("utf-8", "replace")[:600]
            except Exception:
                detail = ""
            last = HttpError(f"HTTP {code}: {detail}", code=code,
                             transient=transient, attempts=attempt + 1)
            if not transient:
                raise last                          # permanent — give up now
        except (urllib.error.URLError, TimeoutError) as e:
            last = HttpError(f"network error: {e}", transient=True, attempts=attempt + 1)
        if attempt == max_retries - 1:
            break
        time.sleep(delay)
        delay *= 2
    raise last


def request_json(url, *, headers=None, body=None, method="POST",
                 timeout=60.0, max_retries=4):
    """Send a JSON request and return the parsed JSON response.

    ``body`` is JSON-encoded when present (for GET, pass ``body=None``).
    """
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    raw = request_bytes(url, headers=hdrs, data=data, method=method,
                        timeout=timeout, max_retries=max_retries)
    return json.loads(raw.decode("utf-8")) if raw else {}


def get_json(url, *, headers=None, timeout=60.0, max_retries=4):
    return request_json(url, headers=headers, body=None, method="GET",
                        timeout=timeout, max_retries=max_retries)
