"""OpenAI-compatible chat-completions adapter — one adapter covers most of the world.

Parameterised by ``base_url`` + ``key_env``, this one class talks to OpenAI, OpenRouter,
Groq, Together, Fireworks, DeepInfra, DeepSeek, xAI, Mistral, and any local server that
speaks the OpenAI dialect (Ollama, vLLM, LM Studio). It also carries the reasoning-model
handling that is genuinely painful to rediscover:

- gpt-5 / o-series want ``max_completion_tokens`` (not ``max_tokens``), reject a
  non-default ``temperature``, and 400 on ``top_p``;
- they take a ``reasoning_effort`` knob ("minimal"|"low"|"medium"|"high");
- they will return **empty** visible content if the whole token budget is spent on
  hidden reasoning (the "null problem") — we flag that as ``meta.empty_reason`` so a
  blank cell is diagnosable in the JSONL instead of mysteriously empty.
"""
from __future__ import annotations

import os

from .base import Provider
from .http import HttpError, request_json

# Bare model names (after any vendor prefix) that use the reasoning interface.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


class OpenAICompatProvider(Provider):
    name = "openai_compat"

    def __init__(self, model, *, base_url, key_env=None, reasoning_effort=None,
                 routing=None, extra_headers=None, provider_name=None,
                 timeout=90.0, max_retries=4, api_key=None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.endpoint = self.base_url + "/chat/completions"
        self.key_env = key_env
        self.reasoning_effort = reasoning_effort
        self.routing = routing                       # OpenRouter provider-routing block
        self.extra_headers = dict(extra_headers or {})
        self.provider_name = provider_name or "openai_compat"
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = api_key or (os.environ.get(key_env) if key_env else None)
        if key_env and not self.api_key:
            raise ValueError(f"set {key_env} to use provider {self.provider_name!r} (model {model!r})")

    def _is_reasoning(self):
        tail = self.model.lower().split("/")[-1]      # tolerate vendor-prefixed slugs
        return tail.startswith(_REASONING_PREFIXES)

    def _payload(self, messages, sampling):
        body = {"model": self.model, "messages": messages}
        if self._is_reasoning():
            body["max_completion_tokens"] = sampling.max_tokens
            if self.reasoning_effort:
                body["reasoning_effort"] = self.reasoning_effort
            # temperature + top_p omitted: reasoning models only accept the defaults
        else:
            body["temperature"] = sampling.temperature
            body["max_tokens"] = sampling.max_tokens
            if sampling.top_p != 1.0:
                body["top_p"] = sampling.top_p
        if sampling.seed is not None:
            body["seed"] = sampling.seed
        if self.routing:
            body["provider"] = self.routing
        return body

    def chat(self, messages, sampling):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        body = request_json(self.endpoint, headers=headers,
                            body=self._payload(messages, sampling),
                            timeout=self.timeout, max_retries=self.max_retries)
        if "choices" not in body:                     # some backends return errors as HTTP 200
            err = body.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or str(body)[:300]
            raise HttpError(f"no choices in response: {msg}", transient=False)
        choice = (body.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        finish = choice.get("finish_reason")
        meta = {
            "usage": body.get("usage"),
            "served_by": body.get("provider") or self.provider_name,
            "model_returned": body.get("model"),
            "response_id": body.get("id"),
            "finish_reason": finish,
            "reasoning_effort": self.reasoning_effort,
        }
        if not text and self._is_reasoning() and finish in ("length", None):
            meta["empty_reason"] = "reasoning_starved"
        return text, meta
