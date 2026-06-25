"""Offline, deterministic provider — the reason the quickstart needs no API key.

Given ``(model, prompt, seed)`` it always returns the same text, so the whole
pipeline (grid build, concurrency, JSONL, resume, the viewer) is exercisable with no
keys and no network. It also fabricates plausible token ``usage`` so the cost/usage
plumbing has something real to normalise.
"""
from __future__ import annotations

import hashlib
import random

from .base import Provider

_BITS = [
    "Here is a concise take:",
    "Consider it from three angles.",
    "The short answer is yes, with caveats.",
    "A small worked example follows.",
    "In one line: it depends on the context.",
    "Two things matter most here.",
]


class MockProvider(Provider):
    name = "mock"

    def __init__(self, model: str = "mock", **_):
        self.model = model

    def chat(self, messages, sampling):
        prompt = next((m["content"] for m in reversed(messages)
                       if m.get("role") == "user"), "")
        key = f"{self.model}|{prompt}|{len(messages)}|{sampling.seed}".encode("utf-8")
        rng = random.Random(hashlib.sha256(key).hexdigest())
        body = " ".join(rng.choice(_BITS) for _ in range(rng.randint(1, 3)))
        text = f"[{self.model}] {body}"
        usage = {"prompt_tokens": max(1, len(prompt) // 4),
                 "completion_tokens": max(1, len(text) // 4)}
        meta = {"usage": usage, "served_by": "mock", "model_returned": self.model,
                "finish_reason": "stop", "synthetic": True}
        return text, meta
