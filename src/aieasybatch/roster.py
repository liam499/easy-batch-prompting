"""Roster — the model side of the grid.

The whole ergonomic bet is that a model is a *string* you can type:
``"provider:model_id"`` (e.g. ``"openai:gpt-4o-mini"``,
``"openrouter:meta-llama/llama-3.1-8b-instruct"``). When you need knobs, use the dict
form and only the keys you care about::

    {"provider": "openai", "model": "gpt-5", "reasoning_effort": "low",
     "max_tokens": 2000, "meta": {"tier": "frontier"}}

Anything not recognised (e.g. OpenRouter ``routing``) is tucked into ``extra`` and
passed straight through to the provider adapter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_KNOWN = ("base_url", "key_env", "reasoning_effort", "max_tokens", "meta")


@dataclass
class ModelSpec:
    provider: str
    model: str
    base_url: str | None = None
    key_env: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = None       # per-model override of the run's max_tokens
    extra: dict = field(default_factory=dict)   # routing etc., passed to the adapter
    meta: dict = field(default_factory=dict)    # free-form -> model_meta in every record

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_model(spec) -> ModelSpec:
    if isinstance(spec, ModelSpec):
        return spec
    if isinstance(spec, str):
        if ":" not in spec:
            raise ValueError(
                f"model selector must be 'provider:model_id' (e.g. 'openai:gpt-4o-mini'), got {spec!r}"
            )
        provider, model = spec.split(":", 1)        # split once: model ids may contain ':'
        return ModelSpec(provider=provider.strip(), model=model.strip())
    if isinstance(spec, dict):
        d = dict(spec)
        provider = d.pop("provider", None)
        model = d.pop("model", None) or d.pop("model_id", None)
        if not provider or not model:
            raise ValueError(f"model object needs 'provider' and 'model': {spec!r}")
        fields = {k: d.pop(k) for k in _KNOWN if k in d}
        extra = dict(fields.pop("extra", {})) if "extra" in fields else {}
        extra.update(d)                              # leftover keys (routing, ...) -> extra
        return ModelSpec(provider=provider, model=model, extra=extra, **fields)
    raise TypeError(f"unsupported model spec: {spec!r}")


def load_roster(source) -> list[ModelSpec]:
    """Load a roster from a list of selectors/dicts, or a JSON file.

    A roster file is ``{"models": [...]}`` or a bare ``[...]`` of selectors/dicts.
    """
    if isinstance(source, (list, tuple)):
        return [parse_model(s) for s in source]
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    models = data["models"] if isinstance(data, dict) else data
    return [parse_model(m) for m in models]
