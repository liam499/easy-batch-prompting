"""The ``aieasybatch/v1`` provenance record — one JSON object per output.

This is the single unifier of the whole tool: every answer, whether produced by a
live call or pulled from a provider's async batch job, lands as the *same* flat
record, keyed by a content-addressed ``custom_id``. See ``SCHEMA.md`` for the
written spec; this module is the conformant Python implementation (``record.ts`` is
the JavaScript twin, and a shared golden fixture keeps them honest).

Nothing here is research-specific: a record describes *which model answered which
prompt, how, and at what cost* — and carries two open dicts (``prompt_meta`` /
``model_meta``) plus a ``raw`` catch-all so you never have to fork the schema to
attach your own fields.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SCHEMA = "aieasybatch/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def custom_id(provider: str, model: str, prompt: str,
              system: str | None = None, repeat: int = 0) -> str:
    """A stable, content-addressed cell identity.

    The same ``(provider, model, prompt, system, repeat)`` always hashes to the same
    id, so it does triple duty: the resume key for the live path, the ``custom_id``
    every provider batch API requires for out-of-order reassembly, and the merge/dedup
    key across parallel run files. Hex + length 32 keeps it inside the strictest
    provider rule (Anthropic: ``^[a-zA-Z0-9_-]{1,64}$``).
    """
    h = hashlib.sha256()
    h.update(provider.encode("utf-8")); h.update(b"\x00")
    h.update(model.encode("utf-8")); h.update(b"\x00")
    h.update((prompt or "").encode("utf-8")); h.update(b"\x00")
    h.update((system or "").encode("utf-8")); h.update(b"\x00")
    h.update(str(repeat).encode("utf-8"))
    return h.hexdigest()[:32]


@dataclass(frozen=True)
class Sampling:
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 512
    seed: int | None = 0
    reasoning_effort: str | None = None   # "minimal"|"low"|"medium"|"high" (reasoning models)


# Field order for the emitted JSON — purely cosmetic, but it makes the JSONL pleasant
# to read (identity first, the answer in the middle, bookkeeping last).
_ORDER = (
    "schema", "custom_id", "run_id", "ts",
    "provider", "model", "model_returned", "served_by",
    "prompt_id", "prompt", "system", "messages",
    "sampling", "repeat",
    "output", "finish_reason", "error",
    "usage", "cost_usd", "latency_ms",
    "prompt_meta", "model_meta", "raw",
)


@dataclass
class Record:
    # --- identity (required) ---
    custom_id: str
    run_id: str
    provider: str
    model: str
    prompt_id: str
    prompt: str
    sampling: Sampling
    # --- everything else has a default ---
    repeat: int = 0
    system: str | None = None
    messages: list | None = None          # set only for multi-turn; else prompt is canonical
    output: str | None = None             # raw text, unjudged; None on failure
    finish_reason: str | None = None
    error: dict | None = None             # None on success; {type, message, attempts} on failure
    model_returned: str | None = None     # what the API actually served
    served_by: str | None = None          # backend (e.g. OpenRouter route); auditable
    usage: dict | None = None             # normalized {input_tokens, output_tokens, total_tokens}
    cost_usd: float | None = None         # best-effort; None when the model isn't priced
    latency_ms: int | None = None
    prompt_meta: dict = field(default_factory=dict)
    model_meta: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    schema: str = SCHEMA
    ts: str = field(default_factory=now_iso)

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        d = asdict(self)                  # also converts the nested Sampling dataclass
        return {k: d[k] for k in _ORDER if k in d}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
