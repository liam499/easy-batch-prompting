"""Anthropic Messages API adapter.

Differs from the OpenAI dialect in the ways that bite: ``x-api-key`` (not Bearer), a
required ``anthropic-version`` header, ``max_tokens`` is required and top-level, the
system prompt is a top-level field (not a message), and the response is a list of
content blocks.
"""
from __future__ import annotations

import os

from .base import Provider
from .http import HttpError, request_json

_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model, *, base_url=None, key_env=None,
                 timeout=90.0, max_retries=4, api_key=None):
        self.model = model.split("/", 1)[1] if model.startswith("anthropic/") else model
        self.base_url = (base_url or "https://api.anthropic.com/v1").rstrip("/")
        self.endpoint = self.base_url + "/messages"
        self.key_env = key_env or "ANTHROPIC_API_KEY"
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = api_key or os.environ.get(self.key_env)
        if not self.api_key:
            raise ValueError(f"set {self.key_env} to use the anthropic provider (model {model!r})")

    def _payload(self, messages, sampling):
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        convo = [{"role": m["role"], "content": m["content"]}
                 for m in messages if m["role"] != "system"]
        body = {"model": self.model, "max_tokens": sampling.max_tokens,
                "temperature": sampling.temperature, "messages": convo}
        if system:
            body["system"] = system
        if sampling.top_p != 1.0:
            body["top_p"] = sampling.top_p
        return body

    def chat(self, messages, sampling):
        headers = {"x-api-key": self.api_key, "anthropic-version": _VERSION,
                   "Content-Type": "application/json"}
        body = request_json(self.endpoint, headers=headers,
                            body=self._payload(messages, sampling),
                            timeout=self.timeout, max_retries=self.max_retries)
        if "content" not in body:
            err = body.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or str(body)[:300]
            raise HttpError(f"no content in response: {msg}", transient=False)
        text = "".join(b.get("text", "") for b in body.get("content", [])
                       if b.get("type") == "text")
        usage = body.get("usage") or {}
        meta = {
            "usage": {"input_tokens": usage.get("input_tokens"),
                      "output_tokens": usage.get("output_tokens")},
            "served_by": "anthropic",
            "model_returned": body.get("model"),
            "response_id": body.get("id"),
            "finish_reason": body.get("stop_reason"),
        }
        return text, meta
