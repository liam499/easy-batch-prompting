"""Provider interface — one adapter per model-serving backend.

The contract is deliberately tiny and unchanged from the engine this tool grew out
of: ``chat(messages, sampling) -> (text, meta)``. ``meta`` is a free-form dict; the
core reads a few well-known keys off it (``usage``, ``served_by``, ``model_returned``,
``finish_reason``, and the optional diagnostic ``empty_reason``) and files the rest
under the record's ``raw``. Adapters only ever retain raw text — they never judge,
parse, or reduce an output.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Provider(ABC):
    name: str

    @abstractmethod
    def chat(self, messages: list, sampling) -> tuple:
        """Return ``(output_text, meta)`` for a list of chat messages."""
        raise NotImplementedError

    def generate(self, prompt: str, sampling, system: str | None = None) -> tuple:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, sampling)
