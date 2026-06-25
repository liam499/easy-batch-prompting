"""Token-usage normalisation and best-effort cost estimation.

Every provider names its token counts differently; ``normalize_usage`` maps them all
onto the canonical ``{input_tokens, output_tokens, total_tokens}`` so one column in the
JSONL means the same thing across providers. ``estimate_cost`` multiplies that by a
small, **overridable** price table — it is intentionally approximate, returns ``None``
for any model it doesn't recognise, and never becomes a dependency or a hard error.
"""
from __future__ import annotations


def normalize_usage(provider, raw):
    """Map a provider's raw usage dict onto ``{input,output,total}_tokens``."""
    if not raw:
        return None
    inp = raw.get("input_tokens", raw.get("prompt_tokens", raw.get("promptTokenCount")))
    out = raw.get("output_tokens", raw.get("completion_tokens", raw.get("candidatesTokenCount")))
    tot = raw.get("total_tokens", raw.get("totalTokenCount"))
    if tot is None and (inp is not None or out is not None):
        tot = (inp or 0) + (out or 0)
    if inp is None and out is None and tot is None:
        return None
    return {"input_tokens": inp, "output_tokens": out, "total_tokens": tot}


# USD per 1,000,000 tokens, (input, output). Best-effort and easy to override via
# run(prices=...). Order matters: list more specific keys first so the substring match
# prefers e.g. "gpt-4o-mini" over "gpt-4o".
DEFAULT_PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "o4-mini": (1.10, 4.40),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-haiku-4": (1.00, 5.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemma-3": (0.05, 0.10),
    "gemma-2": (0.05, 0.10),
    "llama-3.1-8b": (0.05, 0.08),
    "llama-3.3-70b": (0.12, 0.30),
    "mistral-nemo": (0.02, 0.04),
    "mistral-small": (0.20, 0.60),
    "mistral-7b": (0.05, 0.10),
    "qwen-2.5-7b": (0.05, 0.10),
    "deepseek-chat": (0.27, 1.10),
}


def estimate_cost(model, usage, prices=None):
    """Best-effort USD cost for one call; ``None`` if the model isn't priced."""
    if not usage:
        return None
    table = dict(DEFAULT_PRICES)
    if prices:
        table.update(prices)
    ml = model.lower()
    match = next((k for k in table if k in ml), None)
    if match is None:
        return None
    price_in, price_out = table[match]
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    return round(inp / 1e6 * price_in + out / 1e6 * price_out, 8)
