// The aieasybatch/v1 provenance record — the JavaScript twin of record.py.
// The schema (field names + customId hashing) is identical across languages, so a
// run produced by either side is the same shape and the same custom_ids — see
// SCHEMA.md and the cross-language fixture test.
import { createHash } from "node:crypto";

export const SCHEMA = "aieasybatch/v1";

export const nowIso = () => new Date().toISOString();

const NUL = Buffer.from([0]);

/** Content-addressed cell id: identical bytes to record.py.customId, so resume keys
 *  and batch custom_ids line up across Python and JS. */
export function customId(provider, model, prompt, system = null, repeat = 0) {
  const h = createHash("sha256");
  h.update(provider, "utf8"); h.update(NUL);
  h.update(model, "utf8"); h.update(NUL);
  h.update(prompt || "", "utf8"); h.update(NUL);
  h.update(system || "", "utf8"); h.update(NUL);
  h.update(String(repeat), "utf8");
  return h.digest("hex").slice(0, 32);
}

const ORDER = [
  "schema", "custom_id", "run_id", "ts",
  "provider", "model", "model_returned", "served_by",
  "prompt_id", "prompt", "system", "messages",
  "sampling", "repeat",
  "output", "finish_reason", "error",
  "usage", "cost_usd", "latency_ms",
  "prompt_meta", "model_meta", "raw",
];

/** Build a fully-populated record object (every field present, in spec order). */
export function makeRecord(f) {
  return {
    schema: SCHEMA,
    custom_id: f.custom_id,
    run_id: f.run_id,
    ts: f.ts ?? nowIso(),
    provider: f.provider,
    model: f.model,
    model_returned: f.model_returned ?? null,
    served_by: f.served_by ?? null,
    prompt_id: f.prompt_id,
    prompt: f.prompt,
    system: f.system ?? null,
    messages: f.messages ?? null,
    sampling: f.sampling,
    repeat: f.repeat ?? 0,
    output: f.output ?? null,
    finish_reason: f.finish_reason ?? null,
    error: f.error ?? null,
    usage: f.usage ?? null,
    cost_usd: f.cost_usd ?? null,
    latency_ms: f.latency_ms ?? null,
    prompt_meta: f.prompt_meta ?? {},
    model_meta: f.model_meta ?? {},
    raw: f.raw ?? {},
  };
}

export function recordToJson(rec) {
  const ordered = {};
  for (const k of ORDER) ordered[k] = rec[k];
  return JSON.stringify(ordered);
}
