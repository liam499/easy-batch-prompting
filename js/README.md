# aieasybatch (JavaScript)

The zero-dependency JS sibling of [aieasybatch](../README.md). Same idea, same output: a
list of prompts × a roster of models → one JSONL with every answer, full provenance,
resumable, per-model concurrency caps. Node 18+ (uses the global `fetch`); **no
dependencies**.

```js
import { run } from "aieasybatch";

// offline quickstart — no key needed:
const r = await run(
  ["Summarize the French Revolution.", "Write a haiku about TCP."],
  ["mock:fast", "mock:smart"],
  "run.jsonl",
);
console.log(r.path, r.ok, r.failed);

// live, multi-model, one run:
await run(
  ["Why is the sky blue?"],
  ["openai:gpt-4o-mini", "anthropic:claude-haiku-4.5", "groq:llama-3.1-8b-instant"],
  "answers.jsonl",
  { per_model_concurrency: 4, concurrency: 24 },
);
```

CLI (after `npm i -g aieasybatch`, or `node src/cli.js`):

```bash
aieasybatch run prompts.txt -m mock:a -m mock:b -o run.jsonl
cat prompts.txt | aieasybatch run - --roster roster.json > run.jsonl
```

## Parity with the Python tool

The record schema and the `customId` hashing are **identical** across the two ports
(enforced by a shared fixture, `tests/fixtures/custom_ids.json`, that both test suites
check). So a run — or a provider batch — produced by either side can be read, merged,
resumed, or viewed by the other. The HTML viewer (`aieasybatch view`) and the 50%-off
batch bridge (`aieasybatch batch`) currently live in the Python package; point them at a
JSONL produced here and they just work.

## API

- `run(prompts, models, out?, opts?) → Promise<{ path, ok, failed, run_id, records() }>`
- `loadPrompts(source)`, `loadRoster(source)`, `register(name, factory)`, `customId(...)`

Providers: one OpenAI-compatible adapter (`openai`, `openrouter`, `groq`, `together`,
`fireworks`, `deepinfra`, `deepseek`, `xai`, `mistral`, `ollama`, `vllm`, `lmstudio`),
plus `anthropic`, `gemini`, and the offline `mock`. TypeScript types ship in
`index.d.ts` (no build step).
