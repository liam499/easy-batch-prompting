"""The batch bridge — run the SAME roster × prompts config on providers' native
async batch APIs (OpenAI, Anthropic) for the ~50% discount.

It is a complementary *mode*, not the headline: provider batch jobs are async (hours),
single-model-per-job, and only some providers offer them — so the roster maps to one
native job per eligible model, and everything else can run live with ``--live-fallback``.
Either way the results normalise back into the very same ``aieasybatch/v1`` JSONL as the
live path, aligned by the same ``custom_id`` — a live run and a batch run of one config
are diffable.
"""
from __future__ import annotations

from .common import (collect_batch, eligible, get_backend, register_backend,
                     submit_batch)

__all__ = ["submit_batch", "collect_batch", "eligible", "get_backend",
           "register_backend", "add_cli"]


def add_cli(sub):
    from .cli import add_cli as _add
    _add(sub)
