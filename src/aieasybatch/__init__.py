"""aieasybatch — brain-dead-simple batch prompting.

A list of prompts × a roster of models -> concurrent live calls -> one JSONL file with
every answer and full provenance. Resumable, per-model concurrency caps, zero
dependencies (standard library only).

    import aieasybatch as ab
    r = ab.run(prompts=["Hello?", "Why is the sky blue?"],
               models=["mock:fast", "mock:smart"], out="run.jsonl")
    print(r.ok, r.failed)
"""
from __future__ import annotations

from .core import RunResult, run
from .prompts import Prompt, load_prompts
from .record import Record, Sampling
from .registry import register
from .roster import ModelSpec, load_roster

__version__ = "0.1.0"
__all__ = [
    "run", "RunResult",
    "load_prompts", "Prompt",
    "load_roster", "ModelSpec",
    "Record", "Sampling",
    "register",
]
