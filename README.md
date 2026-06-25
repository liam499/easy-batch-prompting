# aieasybatch

**Brain-dead-simple batch prompting.** Pour in a list of prompts and a roster of models;
get out one JSONL with every answer — concurrent, resumable, with full provenance. One
function, one CLI verb, **zero dependencies**, runs anywhere Python (or Node) runs.

```python
import aieasybatch as ab

r = ab.run(
    prompts=["Summarize the French Revolution.", "Write a haiku about TCP."],
    models=["openai:gpt-4o-mini", "anthropic:claude-haiku-4.5", "groq:llama-3.1-8b-instant"],
    out="answers.jsonl",
)
print(r.ok, r.failed)          # 6 0
```

That's the whole idea: **the same prompts fanned across many models in one run, collecting
every response** — the thing the provider batch APIs can't do (they're one model per job)
and the big frameworks make heavy (LiteLLM, Curator). No client to construct, no chains,
no `pip install` tax.

---

## Install

No registry account needed — install straight from the public GitHub repo:

```bash
# Python:
pip install git+https://github.com/liam499/easy-batch-prompting

# JavaScript (Node 18+):
npm install github:liam499/easy-batch-prompting
```

Or **just grab the one file** — `aieasybatch.py` *is* the entire Python tool (standard-library
only, nothing to install):

```bash
curl -O https://raw.githubusercontent.com/liam499/easy-batch-prompting/HEAD/aieasybatch.py
python aieasybatch.py run examples/prompts.txt -m mock:a -o run.jsonl
```

> PyPI/npm publishing is also wired up (`pip install aieasybatch` / `npm install aieasybatch`
> once released — see [RELEASING.md](RELEASING.md)), but the GitHub install above works today
> with no signup.

## 30-second quickstart (no API key)

The offline `mock` provider runs the whole pipeline with no keys and no network:

```bash
aieasybatch run examples/prompts.txt -m mock:fast -m mock:smart -o run.jsonl
aieasybatch view run.jsonl -o report.html      # open the comparison grid
```

```python
import aieasybatch as ab
r = ab.run(prompts=["hello?", "why is the sky blue?"], models=["mock:a", "mock:b"], out="")
for rec in r.records():
    print(rec["model"], "→", rec["output"])
```

## What you get out

One JSON object per line, the same shape across every provider (and across the Python and
JS ports). Errors are records too, so "did model X refuse or time out?" is answerable:

```jsonc
{
  "schema": "aieasybatch/v1",
  "custom_id": "143648113b45c28c1c41074591b5c79d",   // content-addressed: the resume + dedup key
  "provider": "openai", "model": "gpt-4o-mini", "served_by": "openai",
  "prompt_id": "0", "prompt": "Summarize the French Revolution.",
  "output": "The French Revolution (1789–1799)…", "finish_reason": "stop", "error": null,
  "usage": {"input_tokens": 14, "output_tokens": 92, "total_tokens": 106},
  "cost_usd": 0.0000573, "latency_ms": 840,
  "prompt_meta": {}, "model_meta": {}, "raw": {}
}
```

See [SCHEMA.md](SCHEMA.md) for the full record spec.

## The CLI — one verb, plus a few helpers

```bash
# fan prompts across a roster (live calls), resumable, with a per-model 429 guard:
aieasybatch run prompts.txt -m openai:gpt-4o-mini -m anthropic:claude-haiku-4.5 \
    --concurrency 24 --per-model 4 -o answers.jsonl --resume

cat prompts.txt | aieasybatch run - --roster roster.json > run.jsonl   # pipes like any Unix tool

aieasybatch view answers.jsonl -o report.html      # standalone HTML comparison grid
aieasybatch lock --roster roster.json --out roster.locked.json   # pin OpenRouter backends
aieasybatch batch submit prompts.txt --roster roster.json --handle run.batch.json   # 50%-off path
aieasybatch batch collect run.batch.json -o answers.jsonl --wait
```

A model is just the string `provider:model_id`. Supported out of the box: `openai`,
`anthropic`, `gemini`, `openrouter`, `groq`, `together`, `fireworks`, `deepinfra`,
`deepseek`, `xai`, `mistral`, local `ollama` / `vllm` / `lmstudio`, and `mock`. Set the
matching `*_API_KEY` env var. Add your own backend in one line: `ab.register("name", factory)`.

## Why this exists (and how it compares)

Every provider now has a batch API, and there are big frameworks for fan-out — but there
was a gap right in the middle. Provider batch APIs are **async (~24h), one model per job**.
LiteLLM's multi-model call is a *race that cancels the losers* (you keep the first
response, not all of them; the collecting variant is a differently-named function), and it
pulls in a large dependency. Curator can do batch, but drags in `litellm + pydantic +
datasets + pandas` and a `curator.LLM` subclass returning a HuggingFace Dataset.

|                                            | **aieasybatch** | Provider Batch APIs | LiteLLM | Curator |
| ------------------------------------------ | :---: | :---: | :---: | :---: |
| Many models in **one run**, collect **all** | ✅ | ❌ one model/job | ⚠️ race cancels losers | ✅ |
| Dependencies                                | **none** | provider SDK | large | litellm+pydantic+pandas… |
| Latency                                     | live (seconds) | async (~24h) | live | live or batch |
| Resumable (crash → top-up)                  | ✅ `custom_id` | manual | ❌ | ✅ cache |
| Unified provenance JSONL                    | ✅ cross-provider | per-job ids | ❌ | dataset |
| Drop-in single file / vendor               | ✅ | ❌ | ❌ | ❌ |
| 50% batch discount                          | via the bridge | ✅ | ❌ | ✅ |

**Honest positioning:** we are **live fan-out** — reach for it when you want to compare
many models *right now* with zero setup. If you can wait ~24 hours and want the 50%
discount, that's what the provider batch APIs are for — and the `batch` bridge drives them
for you from the same config (see below). We don't claim the discount as ours.

## Features

- **The throughput trick.** Raise total `--concurrency` high and cap `--per-model` so no
  single shared endpoint trips its 429 — the right primitive for live fan-out.
- **Resumable.** Every cell has a content-addressed `custom_id`; re-run with `--resume` and
  only the missing/failed cells run. Point many workers at distinct `run_<id>.jsonl` files
  and merge with zero conflict.
- **Provider quirks handled.** Reasoning models (gpt-5/o-series) get `max_completion_tokens`,
  no temperature, `reasoning_effort`; empty-due-to-hidden-reasoning is flagged as
  `raw.empty_reason` instead of a mystery blank.
- **Cost & usage**, normalized across providers, on every record (best-effort, overridable).
- **The viewer.** `aieasybatch view` writes a single self-contained HTML file — a
  prompts × models grid, badges, per-model aggregates — no server, no framework.
- **The bridge.** `aieasybatch batch` runs the same roster × prompts on OpenAI/Anthropic
  native batch APIs (~50% off) and normalizes results back into the *same* JSONL, aligned by
  the same `custom_id`; `--live-fallback` runs the rest live and merges into one file.
- **Reproducibility.** `aieasybatch lock` pins each OpenRouter model to one backend +
  quantization so "the same model" means the same weights every call.
- **A JS/TS twin.** `js/` is a zero-dependency Node port with the identical schema and
  `custom_id` hashing — a run, batch, or report from one side is readable by the other.

## Use it as a library

```python
import aieasybatch as ab

result = ab.run(
    prompts=ab.load_prompts("prompts.txt"),        # list | file | "-" (stdin)
    models=[
        "openai:gpt-4o-mini",
        {"provider": "openai", "model": "gpt-5", "reasoning_effort": "low", "max_tokens": 2000},
        {"provider": "openai", "model": "llama-3.1-8b", "base_url": "https://api.groq.com/openai/v1",
         "key_env": "GROQ_API_KEY", "meta": {"tier": "fast"}},   # any OpenAI-compatible endpoint
    ],
    out="answers.jsonl",
    repeats=1, concurrency=24, per_model_concurrency=4, resume=True,
    on_record=lambda r: print(r.model, r.ok),       # optional live callback
)
print(result.ok, result.failed, result.path)
```

## Design

One job, done well: `prompts × models → collect all → JSONL`. No chains, no agents, no
Pydantic/Dataset pipeline, no vector stores, no hosted service — and no dependency you have
to audit. The core is standard-library only, enforced in CI, which is what lets the whole
thing collapse into one vendorable file.

## License

MIT — see [LICENSE](LICENSE).
