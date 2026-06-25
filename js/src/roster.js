// Roster loader — mirror of roster.py. A model is the string "provider:model_id",
// or an object for knobs ({provider, model, base_url, key_env, reasoning_effort, ...}).
import { readFileSync } from "node:fs";

const KNOWN = ["base_url", "key_env", "reasoning_effort", "max_tokens", "meta"];

export function parseModel(spec) {
  if (typeof spec === "string") {
    const i = spec.indexOf(":");
    if (i < 0) throw new Error(`model selector must be 'provider:model_id', got '${spec}'`);
    return { provider: spec.slice(0, i).trim(), model: spec.slice(i + 1).trim(), extra: {}, meta: {} };
  }
  if (spec && typeof spec === "object") {
    const d = { ...spec };
    const provider = d.provider;
    const model = d.model ?? d.model_id;
    if (!provider || !model) throw new Error(`model object needs 'provider' and 'model': ${JSON.stringify(spec)}`);
    delete d.provider; delete d.model; delete d.model_id;
    const out = { provider, model, extra: { ...(d.extra || {}) }, meta: d.meta || {} };
    delete d.extra; delete d.meta;
    for (const k of KNOWN) if (k in d) { out[k] = d[k]; delete d[k]; }
    Object.assign(out.extra, d); // leftover keys (routing, ...) -> extra
    return out;
  }
  throw new Error(`unsupported model spec: ${spec}`);
}

export function loadRoster(source) {
  if (Array.isArray(source)) return source.map(parseModel);
  const data = JSON.parse(readFileSync(source, "utf8"));
  const models = Array.isArray(data) ? data : data.models;
  return models.map(parseModel);
}

export const label = (spec) => `${spec.provider}:${spec.model}`;
