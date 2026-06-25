// run() — the JS engine, a faithful mirror of core.py. Build the grid (models ×
// prompts × repeats), fan it out with a bounded pool + a per-model semaphore, write
// each answer to JSONL as it lands, resume by skipping finished custom_ids, and record
// errors as records too. Single-threaded, so writes need no lock.
import { closeSync, existsSync, openSync, readFileSync, writeSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { loadPrompts } from "./prompts.js";
import { loadRoster, label } from "./roster.js";
import { customId, makeRecord, recordToJson } from "./record.js";
import { getProvider } from "./registry.js";
import { estimateCost, normalizeUsage } from "./usage.js";

class Semaphore {
  constructor(n) { this.n = n; this.q = []; }
  async acquire() { if (this.n > 0) { this.n--; return; } return new Promise((res) => this.q.push(res)); }
  release() { const res = this.q.shift(); if (res) res(); else this.n++; }
}

function seededRng(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619) >>> 0;
  let a = h >>> 0;
  return () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

function shuffle(arr, seed) {
  const rng = seededRng("shuffle|" + seed);
  for (let i = arr.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [arr[i], arr[j]] = [arr[j], arr[i]]; }
}

function completedIds(path, retryErrors) {
  const done = new Set();
  if (!existsSync(path)) return done;
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    if (!line.trim()) continue;
    let r; try { r = JSON.parse(line); } catch { continue; }
    if (!r.custom_id) continue;
    if (r.error == null) done.add(r.custom_id);
    else if (!retryErrors && r.error.type === "permanent") done.add(r.custom_id);
  }
  return done;
}

async function pool(items, concurrency, worker) {
  let i = 0;
  const runner = async () => { while (i < items.length) { const idx = i++; await worker(items[idx]); } };
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, runner));
}

export async function run(prompts, models, out = "run.jsonl", opts = {}) {
  const {
    repeats = 1, temperature = 1.0, top_p = 1.0, max_tokens = 512, seed = 0,
    concurrency = 16, per_model_concurrency = null, resume = false, retry_errors = false,
    system = null, on_record = null, registry = null, prices = null,
  } = opts;

  const promptList = loadPrompts(prompts);
  const roster = loadRoster(models);
  const runId = randomUUID().replace(/-/g, "").slice(0, 12);

  const providers = new Map();
  const sems = new Map();
  for (const spec of roster) {
    const lab = label(spec);
    if (providers.has(lab)) continue;
    try { providers.set(lab, registry ? registry(spec) : getProvider(spec)); }
    catch (e) { process.stderr.write(`[skip] ${lab}: ${e.message}\n`); providers.set(lab, null); }
    if (per_model_concurrency) sems.set(lab, new Semaphore(per_model_concurrency));
  }

  const done = (resume && typeof out === "string" && out !== "-" && out !== "")
    ? completedIds(out, retry_errors) : new Set();

  const tasks = [];
  for (const spec of roster) {
    if (!providers.get(label(spec))) continue;
    const specMax = spec.max_tokens || max_tokens;
    for (const p of promptList) {
      for (let r = 0; r < repeats; r++) {
        const cid = customId(spec.provider, spec.model, p.text, system, r);
        if (done.has(cid)) continue;
        const sampling = { temperature, top_p, max_tokens: specMax, seed: seed == null ? null : seed + r, reasoning_effort: spec.reasoning_effort || null };
        tasks.push({ spec, p, r, cid, sampling });
      }
    }
  }
  shuffle(tasks, seed || 0);

  // output sink
  let path = null, write = null, collected = null, close = null;
  if (out === "-") write = (line) => process.stdout.write(line + "\n");
  else if (out === "" || out == null) collected = [];
  else { path = String(out); const fd = openSync(path, resume ? "a" : "w"); write = (line) => writeSync(fd, line + "\n"); close = () => closeSync(fd); }

  let ok = 0, failed = 0;

  const work = async ({ spec, p, r, cid, sampling }) => {
    const provider = providers.get(label(spec));
    const sem = sems.get(label(spec));
    const rec = makeRecord({ custom_id: cid, run_id: runId, provider: spec.provider, model: spec.model, prompt_id: p.id, prompt: p.text, system, sampling, repeat: r, prompt_meta: p.meta, model_meta: spec.meta });
    const t0 = Date.now();
    let success = false;
    try {
      const messages = [];
      if (system) messages.push({ role: "system", content: system });
      messages.push({ role: "user", content: p.text });
      if (sem) await sem.acquire();
      let res;
      try { res = await provider.chat(messages, sampling); } finally { if (sem) sem.release(); }
      const meta = res.meta || {};
      rec.output = res.text;
      rec.finish_reason = meta.finish_reason ?? null;
      rec.model_returned = meta.model_returned ?? null;
      rec.served_by = meta.served_by ?? null;
      rec.usage = normalizeUsage(spec.provider, meta.usage);
      rec.cost_usd = estimateCost(spec.model, rec.usage, prices);
      for (const k of ["empty_reason", "response_id", "reasoning_effort"]) if (meta[k] != null) rec.raw[k] = meta[k];
      success = true;
    } catch (e) {
      rec.error = { type: e && e.transient ? "transient" : "permanent", message: String((e && e.message) || e).slice(0, 600), attempts: (e && e.attempts) ?? null };
    }
    rec.latency_ms = Date.now() - t0;
    const line = recordToJson(rec);
    if (write) write(line);
    if (collected) collected.push(JSON.parse(line));
    if (success) ok++; else failed++;
    if (on_record) { try { on_record(rec); } catch { /* ignore */ } }
  };

  await pool(tasks, concurrency, work);
  if (close) close();

  const records = () => collected
    ? collected
    : (path ? readFileSync(path, "utf8").split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l)) : []);
  return { path, ok, failed, run_id: runId, records };
}
