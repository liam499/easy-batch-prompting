"""Live smoke tests — skipped automatically unless the matching API key is in the env.

These hit the real APIs with a tiny 1-prompt run, so they cost a fraction of a cent
and prove the adapters round-trip against production. Run e.g.::

    OPENAI_API_KEY=sk-... python -m pytest tests/test_live.py -q
"""
import os

import pytest

import aieasybatch as ab

_CASES = [
    ("OPENAI_API_KEY", "openai:gpt-4o-mini"),
    ("ANTHROPIC_API_KEY", "anthropic:claude-3-5-haiku-latest"),
    ("GEMINI_API_KEY", "gemini:gemini-2.0-flash"),
    ("OPENROUTER_API_KEY", "openrouter:meta-llama/llama-3.1-8b-instruct"),
    ("GROQ_API_KEY", "groq:llama-3.1-8b-instant"),
]


@pytest.mark.parametrize("env_key,model", _CASES)
def test_live_smoke(env_key, model, tmp_path):
    if not os.environ.get(env_key):
        pytest.skip(f"{env_key} not set")
    res = ab.run(prompts=["Reply with exactly the word: OK"], models=[model],
                 out=str(tmp_path / "live.jsonl"), max_tokens=16, temperature=0)
    rec = next(iter(res.records()))
    assert rec["error"] is None, rec["error"]
    assert rec["output"], "empty output"
    assert rec["usage"] and rec["usage"]["output_tokens"] is not None
