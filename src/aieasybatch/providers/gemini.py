"""Google Gemini adapter (Generative Language API).

Its own shape again: the model goes in the URL (``/models/<model>:generateContent``),
auth is the ``x-goog-api-key`` header, turns are ``contents:[{role, parts:[{text}]}]``
with the assistant role spelled ``model``, sampling lives under ``generationConfig``,
and the system prompt is ``systemInstruction``.
"""
from __future__ import annotations

import os

from .base import Provider
from .http import HttpError, request_json


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, model, *, base_url=None, key_env=None,
                 timeout=90.0, max_retries=4, api_key=None):
        self.model = model.split("/", 1)[1] if model.startswith("models/") else model
        self.base_url = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.key_env = key_env or "GEMINI_API_KEY"
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = (api_key or os.environ.get(self.key_env)
                        or os.environ.get("GOOGLE_API_KEY"))
        if not self.api_key:
            raise ValueError(f"set {self.key_env} to use the gemini provider (model {model!r})")

    def _payload(self, messages, sampling):
        contents, system = [], []
        for m in messages:
            if m["role"] == "system":
                system.append(m["content"])
                continue
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        cfg = {"temperature": sampling.temperature, "maxOutputTokens": sampling.max_tokens}
        if sampling.top_p != 1.0:
            cfg["topP"] = sampling.top_p
        body = {"contents": contents, "generationConfig": cfg}
        if system:
            body["systemInstruction"] = {"parts": [{"text": " ".join(system)}]}
        return body

    def chat(self, messages, sampling):
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        body = request_json(url, headers=headers, body=self._payload(messages, sampling),
                            timeout=self.timeout, max_retries=self.max_retries)
        cands = body.get("candidates")
        if not cands:
            err = body.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or str(body)[:300]
            raise HttpError(f"no candidates in response: {msg}", transient=False)
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        um = body.get("usageMetadata") or {}
        meta = {
            "usage": {"promptTokenCount": um.get("promptTokenCount"),
                      "candidatesTokenCount": um.get("candidatesTokenCount"),
                      "totalTokenCount": um.get("totalTokenCount")},
            "served_by": "gemini",
            "model_returned": body.get("modelVersion") or self.model,
            "response_id": body.get("responseId"),
            "finish_reason": cands[0].get("finishReason"),
        }
        return text, meta
