"""OpenAI Batch API backend.

Lifecycle: build an input JSONL (one ``{custom_id, method, url, body}`` line per cell),
upload it to ``/v1/files`` (multipart), create a ``/v1/batches`` job, poll it, then
download the output (and error) file and map each line back by ``custom_id``. ~50%
cheaper, async (target 24h), and one model per job — which is exactly why the roster
becomes one job per model.
"""
from __future__ import annotations

import json
import uuid

from ..providers.http import get_json, request_bytes, request_json

_REASONING = ("gpt-5", "o1", "o3", "o4")


def build_request_body(model, messages, sampling):
    """The per-request ``body`` (chat-completions payload), reasoning quirks included."""
    tail = model.lower().split("/")[-1]
    body = {"model": model, "messages": messages}
    if tail.startswith(_REASONING):
        body["max_completion_tokens"] = sampling.max_tokens
        if sampling.reasoning_effort:
            body["reasoning_effort"] = sampling.reasoning_effort
    else:
        body["temperature"] = sampling.temperature
        body["max_tokens"] = sampling.max_tokens
        if sampling.top_p != 1.0:
            body["top_p"] = sampling.top_p
    return body


def parse_output_jsonl(text):
    """OpenAI batch output JSONL -> ``{custom_id: result}``."""
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get("custom_id")
        resp = row.get("response") or {}
        body = resp.get("body") or {}
        choices = body.get("choices")
        if resp.get("status_code") == 200 and choices:
            ch = choices[0]
            out[cid] = {
                "output": (ch.get("message") or {}).get("content") or "",
                "finish_reason": ch.get("finish_reason"),
                "usage": body.get("usage"),
                "model_returned": body.get("model"),
                "served_by": "openai", "error": None,
            }
        else:
            msg = row.get("error") or body.get("error") or body
            out[cid] = {"output": None, "served_by": "openai",
                        "error": {"type": "permanent", "message": str(msg)[:300], "attempts": 1}}
    return out


class OpenAIBatch:
    eligible = True

    def __init__(self, api_key, base_url=None, timeout=120.0, max_retries=4):
        self.api_key = api_key
        self.base = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.auth = {"Authorization": f"Bearer {api_key}"}

    def submit(self, model, cells, sampling, system):
        lines = [json.dumps({"custom_id": c["custom_id"], "method": "POST",
                             "url": "/v1/chat/completions",
                             "body": build_request_body(model, c["messages"], sampling)})
                 for c in cells]
        file_id = self._upload(("\n".join(lines) + "\n").encode("utf-8"))
        batch = request_json(self.base + "/batches", headers=dict(self.auth),
                             body={"input_file_id": file_id, "endpoint": "/v1/chat/completions",
                                   "completion_window": "24h"},
                             timeout=self.timeout, max_retries=self.max_retries)
        return {"batch_id": batch["id"], "status": batch.get("status", "validating"),
                "state": {"input_file_id": file_id}}

    def _upload(self, jsonl_bytes):
        boundary = "----aeb" + uuid.uuid4().hex
        pre = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
               f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"batch.jsonl\"\r\nContent-Type: application/jsonl\r\n\r\n").encode("utf-8")
        body = pre + jsonl_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        headers = dict(self.auth)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        raw = request_bytes(self.base + "/files", headers=headers, data=body,
                            method="POST", timeout=self.timeout, max_retries=self.max_retries)
        return json.loads(raw.decode("utf-8"))["id"]

    def poll(self, job):
        b = get_json(self.base + f"/batches/{job['batch_id']}", headers=dict(self.auth),
                     timeout=self.timeout, max_retries=self.max_retries)
        st = b.get("status")
        job.setdefault("state", {})["output_file_id"] = b.get("output_file_id")
        job["state"]["error_file_id"] = b.get("error_file_id")
        return {"status": st, "done": st == "completed",
                "failed": st in ("failed", "expired", "cancelled", "canceled")}

    def fetch(self, job):
        state = job.get("state", {})
        out = {}
        for fid in (state.get("output_file_id"), state.get("error_file_id")):
            if not fid:
                continue
            try:
                raw = request_bytes(self.base + f"/files/{fid}/content", headers=dict(self.auth),
                                    method="GET", timeout=self.timeout, max_retries=self.max_retries)
            except Exception:
                continue
            for cid, res in parse_output_jsonl(raw.decode("utf-8")).items():
                out.setdefault(cid, res)            # output file wins over error file
        return out
