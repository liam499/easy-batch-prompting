"""Prompts — the list side of the grid.

A prompt is just *text* plus an *id* plus an optional *meta* dict. ``load_prompts``
accepts whatever you have lying around — a Python list, a ``.txt`` file (one prompt
per line), a ``.jsonl`` / ``.json`` file, or ``"-"`` for stdin — so you never have to
massage your inputs into a special shape first.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Prompt:
    text: str
    id: str
    meta: dict = field(default_factory=dict)


def _read_text(source) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text(encoding="utf-8")


def _coerce(row, i: int) -> Prompt:
    """Turn a raw row (str or dict) into a Prompt with a stable id."""
    if isinstance(row, Prompt):
        return row
    if isinstance(row, str):
        return Prompt(text=row, id=str(i))
    if isinstance(row, dict):
        text = row.get("text", row.get("prompt"))
        if text is None:
            raise ValueError(f"prompt object needs a 'text' (or 'prompt') field: {row!r}")
        return Prompt(text=str(text), id=str(row.get("id", i)), meta=dict(row.get("meta", {})))
    raise TypeError(f"unsupported prompt row: {row!r}")


def load_prompts(source) -> list[Prompt]:
    """Load prompts from a list, a file path, or stdin.

    - list ``[str | dict | Prompt]`` -> coerced directly
    - ``*.txt`` (or unknown extension) -> one non-blank line per prompt
    - ``*.jsonl`` -> one JSON value (string or object) per line
    - ``*.json``  -> a JSON array of strings or objects
    - ``"-"``     -> read stdin (treated as newline-delimited text)
    """
    if isinstance(source, (list, tuple)):
        return [_coerce(r, i) for i, r in enumerate(source)]

    name = str(source)
    text = _read_text(source)
    if name.endswith(".jsonl"):
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif name.endswith(".json"):
        rows = json.loads(text)
        if isinstance(rows, dict):                 # tolerate {"prompts": [...]}
            rows = rows.get("prompts", rows)
    else:
        rows = [line for line in text.splitlines() if line.strip()]
    return [_coerce(r, i) for i, r in enumerate(rows)]
