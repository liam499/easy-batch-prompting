"""Anthropic Message Batches API backend.

Simpler lifecycle than OpenAI's: requests are submitted **inline** (no file upload) to
``/v1/messages/batches``, then when ``processing_status`` is ``ended`` the results are a
JSONL fetched from ``results_url``, each line keyed by ``custom_id``.
"""
from __future__ import annotations

import json

from ..providers.http import get_json, request_bytes, request_json

_VERSION = "2023-06-01"


def build_params(model, messages, sampling, system=None):
    """The per-request ``params`` (Messages payload). System is pulled to the top level."""
    sys_text = system or " ".join(m["content"] for m in messages if m["role"] == "system")
    convo = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
    params = {"model": model, "max_tokens": sampling.max_tokens,
              "temperature": sampling.temperature, "messages": convo}
    if sys_text:
        params["system"] = sys_text
    if sampling.top_p != 1.0:
        params["top_p"] = sampling.top_p
    return params


def parse_results_jsonl(text):
    """Anthropic batch results JSONL -> ``{custom_id: result}``."""
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get("custom_id")
        result = row.get("result") or {}
        if result.get("type") == "succeeded":
            msg = result.get("message") or {}
            text_out = "".join(b.get("text", "") for b in msg.get("content", [])
                               if b.get("type") == "text")
            usage = msg.get("usage") or {}
            out[cid] = {
                "output": text_out, "finish_reason": msg.get("stop_reason"),
                "usage": {"input_tokens": usage.get("input_tokens"),
                          "output_tokens": usage.get("output_tokens")},
                "model_returned": msg.get("model"), "served_by": "anthropic", "error": None,
            }
        else:
            msg = result.get("error") or result.get("type") or "errored"
            out[cid] = {"output": None, "served_by": "anthropic",
                        "error": {"type": "permanent", "message": str(msg)[:300], "attempts": 1}}
    return out


class AnthropicBatch:
    eligible = True

    def __init__(self, api_key, base_url=None, timeout=120.0, max_retries=4):
        self.api_key = api_key
        self.base = (base_url or "https://api.anthropic.com/v1").rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.auth = {"x-api-key": api_key or "", "anthropic-version": _VERSION}

    def submit(self, model, cells, sampling, system):
        requests = [{"custom_id": c["custom_id"],
                     "params": build_params(model, c["messages"], sampling, system)}
                    for c in cells]
        batch = request_json(self.base + "/messages/batches", headers=dict(self.auth),
                             body={"requests": requests},
                             timeout=self.timeout, max_retries=self.max_retries)
        return {"batch_id": batch["id"], "status": batch.get("processing_status", "in_progress"),
                "state": {}}

    def poll(self, job):
        b = get_json(self.base + f"/messages/batches/{job['batch_id']}", headers=dict(self.auth),
                     timeout=self.timeout, max_retries=self.max_retries)
        st = b.get("processing_status")
        job.setdefault("state", {})["results_url"] = b.get("results_url")
        return {"status": st, "done": st == "ended" and bool(b.get("results_url")),
                "failed": st in ("canceled", "cancelled", "expired")}

    def fetch(self, job):
        url = job.get("state", {}).get("results_url")
        if not url:
            return {}
        raw = request_bytes(url, headers=dict(self.auth), method="GET",
                            timeout=self.timeout, max_retries=self.max_retries)
        return parse_results_jsonl(raw.decode("utf-8"))
