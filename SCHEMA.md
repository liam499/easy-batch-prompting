# The `aieasybatch/v1` record

The output of every run is **JSONL** — one of these objects per line. The schema is the
single source of truth shared by the Python package (`record.py`), the JS port
(`record.js`), and the batch bridge; both test suites pin it against the same fixtures.
One line means the same thing whether it came from a live call, a 50%-off provider batch,
the Python tool, or the JS tool.

## Fields

| field            | type                | notes |
| ---------------- | ------------------- | ----- |
| `schema`         | string              | always `"aieasybatch/v1"` |
| `custom_id`      | string              | **content-addressed cell id** — see below. The resume key, the batch-API `custom_id`, and the cross-run merge/dedup key, all in one. |
| `run_id`         | string              | per-run id (the run that produced this record) |
| `ts`             | string              | ISO-8601 UTC timestamp |
| `provider`       | string              | e.g. `openai`, `anthropic`, `gemini`, `openrouter`, `mock` |
| `model`          | string              | the model id you requested |
| `model_returned` | string \| null      | what the API actually served (e.g. a dated snapshot) |
| `served_by`      | string \| null      | backend that served it (e.g. an OpenRouter route) — auditable |
| `prompt_id`      | string              | your prompt id, or its index if unlabeled |
| `prompt`         | string              | the prompt text |
| `system`         | string \| null      | system prompt, if any |
| `messages`       | array \| null       | populated only for multi-turn; otherwise `prompt` is canonical |
| `sampling`       | object              | `{temperature, top_p, max_tokens, seed, reasoning_effort}` |
| `repeat`         | int                 | repeat index (`0 … repeats-1`) |
| `output`         | string \| null      | the raw answer text; `null` on failure |
| `finish_reason`  | string \| null      | provider stop reason |
| `error`          | object \| null      | `null` on success; else `{type: "transient"\|"permanent", message, attempts}` |
| `usage`          | object \| null      | normalized `{input_tokens, output_tokens, total_tokens}` |
| `cost_usd`       | number \| null      | best-effort estimate; `null` when the model isn't priced |
| `latency_ms`     | int \| null         | wall-clock for the call |
| `prompt_meta`    | object              | free-form, passed through from the prompt |
| `model_meta`     | object              | free-form, passed through from the model spec |
| `raw`            | object              | provider extras (`response_id`, `empty_reason`, batch flags, …) |

There are exactly these fields, plus the three open dicts (`prompt_meta`, `model_meta`,
`raw`) for anything you want to attach — so you never have to fork the schema.

## `custom_id`

```
custom_id = sha256( provider \0 model \0 prompt \0 system \0 repeat )  [first 32 hex chars]
```

(`\0` is a single NUL byte separator; `system` is the empty string when absent.) Properties
that make it load-bearing:

- **Deterministic & content-addressed.** Same inputs → same id, in Python and JS alike
  (verified by `tests/fixtures/custom_ids.json`). 32 hex chars satisfy the strictest
  provider rule (Anthropic's `^[a-zA-Z0-9_-]{1,64}$`).
- **Resume.** A re-run computes the ids it would produce and skips the ones already complete
  in the output (a record is *complete* when `error` is `null`, or a permanent error unless
  `retry_errors`).
- **Batch alignment.** It's the exact `custom_id` provider batch APIs use to reassemble
  out-of-order results — so a live run and a batch run of the same config are diffable.

## Errors are records too

A failed call still writes a record, with `output: null` and a structured `error`. This is
deliberate: it keeps the comparison grid honest (a refusal/timeout is visible, not a silent
gap) and lets `--resume` retry exactly the failed cells.
