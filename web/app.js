// aieasybatch — BYOK browser engine + UI. Zero dependencies. Everything runs client-side:
// your key lives in localStorage and is sent only to the endpoint you pick. Records use the
// same aieasybatch/v1 schema (incl. a Web-Crypto custom_id) as the CLI, so downloaded JSONL
// is interchangeable with the Python/JS tools and the standalone viewer.
const $ = (s) => document.querySelector(s);
const SCHEMA = "aieasybatch/v1";
const LS = "aieasybatch.config.v1";
const CHEAP = "meta-llama/llama-3.1-8b-instruct\nmistralai/mistral-nemo\nqwen/qwen-2.5-7b-instruct\ngoogle/gemma-3-12b-it\nopenai/gpt-4o-mini";

const PRICES = {
  "gpt-4o-mini":[0.15,0.6],"gpt-4.1-mini":[0.4,1.6],"gpt-4o":[2.5,10],"gpt-5-mini":[0.25,2],"gpt-5":[1.25,10],
  "o4-mini":[1.1,4.4],"claude-3-5-haiku":[0.8,4],"claude-haiku-4":[1,5],"claude-3-5-sonnet":[3,15],
  "claude-sonnet-4":[3,15],"gemini-2.0-flash":[0.1,0.4],"gemini-1.5-flash":[0.075,0.3],"gemma-3":[0.05,0.1],
  "gemma-2":[0.05,0.1],"llama-3.1-8b":[0.05,0.08],"llama-3.3-70b":[0.12,0.3],"mistral-nemo":[0.02,0.04],
  "mistral-7b":[0.05,0.1],"qwen-2.5-7b":[0.05,0.1],"deepseek-chat":[0.27,1.1],
};
const esc = (s) => (s == null ? "" : String(s)).replace(/[&<>"]/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
const fmtCost = (c) => c == null ? "" : "$" + (Math.abs(c) < 0.01 ? c.toFixed(6) : c.toFixed(4));
const fmtMs = (m) => m == null ? "" : (m >= 1000 ? (m/1000).toFixed(1)+"s" : m+"ms");

// ---- crypto: custom_id identical to record.py / record.js (sha256 of NUL-joined parts) ----
async function customId(provider, model, prompt, system, repeat) {
  const enc = new TextEncoder();
  const segs = [provider, model, prompt || "", system || "", String(repeat)].map((s) => enc.encode(s));
  let len = segs.reduce((a, s) => a + s.length, 0) + (segs.length - 1);
  const buf = new Uint8Array(len); let o = 0;
  segs.forEach((s, i) => { if (i) buf[o++] = 0; buf.set(s, o); o += s.length; });
  if (crypto?.subtle) {
    const d = await crypto.subtle.digest("SHA-256", buf);
    return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
  }
  let h = 0x811c9dc5 >>> 0; for (const b of buf) { h = Math.imul(h ^ b, 16777619) >>> 0; } // insecure-context fallback
  return (h.toString(16) + "00000000").slice(0, 32);
}

function normalizeUsage(raw) {
  if (!raw) return null;
  const i = raw.input_tokens ?? raw.prompt_tokens ?? raw.promptTokenCount ?? null;
  const o = raw.output_tokens ?? raw.completion_tokens ?? raw.candidatesTokenCount ?? null;
  let t = raw.total_tokens ?? raw.totalTokenCount ?? null;
  if (t == null && (i != null || o != null)) t = (i || 0) + (o || 0);
  return (i == null && o == null && t == null) ? null : { input_tokens: i, output_tokens: o, total_tokens: t };
}
function estimateCost(model, u) {
  if (!u) return null;
  const k = Object.keys(PRICES).find((k) => model.toLowerCase().includes(k));
  if (!k) return null;
  return Math.round(((u.input_tokens||0)/1e6*PRICES[k][0] + (u.output_tokens||0)/1e6*PRICES[k][1]) * 1e8) / 1e8;
}

// ---- providers ----
const REASONING = ["gpt-5", "o1", "o3", "o4"];
const isReasoning = (m) => REASONING.some((p) => m.toLowerCase().split("/").pop().startsWith(p));
function buildBody(model, messages, s) {
  const b = { model, messages };
  if (isReasoning(model)) { b.max_completion_tokens = s.maxTokens; if (s.effort) b.reasoning_effort = s.effort; }
  else { b.temperature = s.temperature; b.max_tokens = s.maxTokens; }
  return b;
}
async function chat(cfg, model, messages, s, signal) {
  if (cfg.provider === "mock") return mockChat(cfg, model, messages, s);
  let delay = 1500, last;
  for (let attempt = 0; attempt < 4; attempt++) {
    let resp;
    try {
      resp = await fetch(cfg.baseUrl.replace(/\/+$/, "") + "/chat/completions", {
        method: "POST", signal,
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + cfg.apiKey },
        body: JSON.stringify(buildBody(model, messages, s)),
      });
    } catch (e) {
      if (signal?.aborted) throw e;
      last = new Error("network/CORS error (this provider may block browser calls — try via OpenRouter)");
      last.transient = true;
    }
    if (resp) {
      const text = await resp.text();
      if (resp.ok) {
        const body = JSON.parse(text);
        if (!body.choices) { const e = new Error("no choices: " + (body.error?.message || text.slice(0,200))); throw e; }
        const ch = body.choices[0] || {};
        return { text: ch.message?.content || "", meta: { usage: body.usage, finish_reason: ch.finish_reason, model_returned: body.model, served_by: body.provider || cfg.provider } };
      }
      const transient = resp.status === 429 || resp.status >= 500;
      last = new Error("HTTP " + resp.status + ": " + text.slice(0, 240)); last.transient = transient; last.status = resp.status;
      if (!transient) throw last;
    }
    if (attempt < 3) { await new Promise((r) => setTimeout(r, delay)); delay *= 2; }
  }
  throw last;
}
let _mockSeed = 0;
function mockChat(cfg, model, messages) {
  const prompt = [...messages].reverse().find((m) => m.role === "user")?.content || "";
  const bits = ["A concise take:", "Consider three angles.", "Yes, with caveats.", "It depends on context.", "Two things matter here."];
  const text = `[${model}] ` + bits[(prompt.length + model.length + _mockSeed++) % bits.length] + " " + bits[(prompt.length * 3) % bits.length];
  return Promise.resolve({ text, meta: { usage: { prompt_tokens: (prompt.length/4)|0, completion_tokens: (text.length/4)|0 }, finish_reason: "stop", model_returned: model, served_by: "mock" } });
}

// ---- concurrency ----
class Sem { constructor(n){ this.n=n; this.q=[]; } async acquire(){ if(this.n>0){this.n--;return;} return new Promise(r=>this.q.push(r)); } release(){ const r=this.q.shift(); if(r) r(); else this.n++; } }
async function pool(items, n, worker) {
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) await worker(items[i++]); }));
}

// ---- the run ----
const state = { records: [], running: false, ctrl: null };

async function runFanout(cfg, prompts, models, s, onRecord) {
  const tasks = [];
  models.forEach((model, mi) => prompts.forEach((prompt, pi) => {
    for (let r = 0; r < s.repeats; r++) tasks.push({ model, mi, prompt, pi, repeat: r });
  }));
  const sems = new Map();
  const sem = (m) => { if (!sems.has(m)) sems.set(m, new Sem(s.perModel || s.concurrency)); return sems.get(m); };
  state.records = []; let ok = 0, failed = 0;
  await pool(tasks, s.concurrency, async (t) => {
    if (state.ctrl?.signal.aborted) return;
    const messages = [];
    if (s.system) messages.push({ role: "system", content: s.system });
    messages.push({ role: "user", content: t.prompt });
    const cid = await customId(cfg.provider, t.model, t.prompt, s.system, t.repeat);
    const rec = {
      schema: SCHEMA, custom_id: cid, run_id: state.runId, ts: new Date().toISOString(),
      provider: cfg.provider, model: t.model, model_returned: null, served_by: null,
      prompt_id: String(t.pi), prompt: t.prompt, system: s.system || null, messages: null,
      sampling: { temperature: s.temperature, top_p: 1, max_tokens: s.maxTokens, seed: 0, reasoning_effort: s.effort || null },
      repeat: t.repeat, output: null, finish_reason: null, error: null,
      usage: null, cost_usd: null, latency_ms: null, prompt_meta: {}, model_meta: {}, raw: {},
    };
    const t0 = performance.now();
    const sm = sem(t.model); await sm.acquire();
    try {
      const { text, meta } = await chat(cfg, t.model, messages, s, state.ctrl?.signal);
      rec.output = text; rec.finish_reason = meta.finish_reason ?? null; rec.model_returned = meta.model_returned ?? null;
      rec.served_by = meta.served_by ?? null; rec.usage = normalizeUsage(meta.usage); rec.cost_usd = estimateCost(t.model, rec.usage);
      ok++;
    } catch (e) {
      rec.error = { type: e.transient ? "transient" : "permanent", message: String(e.message).slice(0, 300), attempts: null };
      failed++;
    } finally { sm.release(); }
    rec.latency_ms = Math.round(performance.now() - t0);
    state.records.push(rec);
    onRecord(rec, t, { ok, failed, total: tasks.length });
  });
  return { ok, failed };
}

// ---- grid (mirrors the standalone viewer) ----
let cells = [];
function buildGrid(prompts, models) {
  cells = prompts.map(() => models.map(() => []));
  let head = '<thead><tr><th class="cornercell">' + prompts.length + " × " + models.length + "</th>";
  models.forEach((m, mi) => head += `<th id="h_${mi}"><div>${esc(m)}</div><div class="agg" id="agg_${mi}">—</div></th>`);
  head += "</tr></thead><tbody>";
  let body = "";
  prompts.forEach((p, pi) => {
    body += `<tr><th>${esc(p)}</th>`;
    models.forEach((_, mi) => body += `<td id="c_${pi}_${mi}" class="pending"><div class="out">…</div></td>`);
    body += "</tr>";
  });
  $("#grid").innerHTML = "<table>" + head + body + "</tbody></table>";
  $("#resultsWrap").hidden = false;
}
function paintCell(rec, t) {
  cells[t.pi][t.mi].push(rec);
  const td = $(`#c_${t.pi}_${t.mi}`); if (!td) return;
  td.className = cells[t.pi][t.mi].some((r) => r.error) ? "error" : (cells[t.pi][t.mi].every((r) => !r.output) ? "empty" : "");
  td.innerHTML = cells[t.pi][t.mi].map((r) => {
    const body = r.error ? "⚠ " + (r.error.message || r.error.type) : (r.output || "(empty)");
    const badges = [];
    if (r.usage?.total_tokens != null) badges.push(`<span class="badge">${r.usage.total_tokens} tok</span>`);
    if (r.cost_usd != null) badges.push(`<span class="badge">${fmtCost(r.cost_usd)}</span>`);
    if (r.latency_ms != null) badges.push(`<span class="badge">${fmtMs(r.latency_ms)}</span>`);
    if (r.error) badges.unshift(`<span class="badge err">${esc(r.error.type)}</span>`);
    return `<div class="out">${esc(body)}</div><div class="badges">${badges.join("")}</div>`;
  }).join("<hr>");
  // header aggregate
  const flat = cells.flatMap((row) => row[t.mi]);
  const errs = flat.filter((r) => r.error).length, cost = flat.reduce((a, r) => a + (r.cost_usd || 0), 0);
  const lat = flat.filter((r) => r.latency_ms != null); const mean = lat.length ? Math.round(lat.reduce((a, r) => a + r.latency_ms, 0) / lat.length) : null;
  $(`#agg_${t.mi}`).textContent = `${flat.length} calls` + (errs ? ` · ${errs} err` : "") + (mean != null ? ` · ~${fmtMs(mean)}` : "") + (cost ? ` · ${fmtCost(cost)}` : "");
}

// ---- config / endpoint ----
function currentCfg() {
  const [baseUrl, provider] = $("#endpoint").value.split("|");
  return { provider, baseUrl: provider === "custom" ? $("#baseUrl").value.trim() : baseUrl, apiKey: $("#apiKey").value.trim() };
}
function onEndpointChange() {
  const [, provider] = $("#endpoint").value.split("|");
  $("#baseWrap").hidden = provider !== "custom";
  $("#keyWrap").hidden = provider === "mock";
  if (provider === "mock" && !$("#models").value.trim()) $("#models").value = "fast\nsmart\ncreative";
  if (provider !== "mock" && !$("#models").value.trim()) $("#models").value = CHEAP;
}
function saveCfg() {
  localStorage.setItem(LS, JSON.stringify({
    endpoint: $("#endpoint").value, baseUrl: $("#baseUrl").value, apiKey: $("#apiKey").value,
    prompts: $("#prompts").value, models: $("#models").value,
    maxTokens: $("#maxTokens").value, temperature: $("#temperature").value, repeats: $("#repeats").value,
    concurrency: $("#concurrency").value, perModel: $("#perModel").value, system: $("#system").value,
  }));
}
function loadCfg() {
  let c = {}; try { c = JSON.parse(localStorage.getItem(LS) || "{}"); } catch {}
  for (const [k, id] of [["endpoint","#endpoint"],["baseUrl","#baseUrl"],["apiKey","#apiKey"],["prompts","#prompts"],["models","#models"],["maxTokens","#maxTokens"],["temperature","#temperature"],["repeats","#repeats"],["concurrency","#concurrency"],["perModel","#perModel"],["system","#system"]])
    if (c[k] != null && $(id)) $(id).value = c[k];
  if (!$("#models").value.trim()) $("#models").value = CHEAP;
  onEndpointChange();
}

// ---- model browser (OpenRouter /models — public, CORS-friendly) ----
let _models = null;
async function openBrowser() {
  $("#modal").hidden = false;
  if (!_models) {
    $("#modelList").innerHTML = '<div class="m">loading…</div>';
    try {
      const data = (await (await fetch("https://openrouter.ai/api/v1/models")).json()).data;
      _models = data.map((m) => ({ id: m.id, price: parseFloat(m.pricing?.prompt || "0") * 1e6 }))
        .sort((a, b) => a.price - b.price);
    } catch { $("#modelList").innerHTML = '<div class="m">could not load models</div>'; return; }
  }
  renderModels("");
}
function renderModels(q) {
  q = q.toLowerCase();
  $("#modelList").innerHTML = _models.filter((m) => m.id.toLowerCase().includes(q)).slice(0, 300)
    .map((m) => `<div class="m" data-id="${esc(m.id)}"><span>${esc(m.id)}</span><span class="price">$${m.price.toFixed(3)}/M</span></div>`).join("");
}

// ---- wire up ----
function setRunning(on) {
  state.running = on;
  $("#run").hidden = on; $("#stop").hidden = !on; $("#bar").hidden = !on;
}
async function doRun() {
  const cfg = currentCfg();
  const prompts = $("#prompts").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  const models = $("#models").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  if (!prompts.length || !models.length) { $("#status").textContent = "add at least one prompt and one model"; return; }
  if (cfg.provider !== "mock" && !cfg.apiKey) { $("#status").textContent = "enter your API key (or pick the offline mock)"; return; }
  if (cfg.provider === "custom" && !cfg.baseUrl) { $("#status").textContent = "enter a base URL"; return; }
  saveCfg();
  const s = {
    maxTokens: +$("#maxTokens").value, temperature: +$("#temperature").value, repeats: +$("#repeats").value,
    concurrency: +$("#concurrency").value, perModel: +$("#perModel").value, system: $("#system").value.trim(), effort: null,
  };
  state.runId = (crypto.randomUUID?.() || (Date.now() + "")).replace(/-/g, "").slice(0, 12);
  state.ctrl = new AbortController();
  buildGrid(prompts, models);
  setRunning(true); $("#download").hidden = true;
  const total = prompts.length * models.length * s.repeats;
  try {
    const { ok, failed } = await runFanout(cfg, prompts, models, s, (rec, t, prog) => {
      paintCell(rec, t);
      $("#status").textContent = `${prog.ok + prog.failed}/${total} · ${prog.ok} ok · ${prog.failed} failed`;
      $("#barFill").style.width = ((prog.ok + prog.failed) / total * 100) + "%";
    });
    $("#status").textContent = state.ctrl.signal.aborted ? `stopped (${ok + failed}/${total})` : `done · ${ok} ok · ${failed} failed`;
  } catch (e) {
    $("#status").textContent = "error: " + e.message;
  } finally {
    setRunning(false); $("#download").hidden = state.records.length === 0;
  }
}
function download() {
  const blob = new Blob([state.records.map((r) => JSON.stringify(r)).join("\n") + "\n"], { type: "application/x-ndjson" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "run_" + (state.runId || "out") + ".jsonl"; a.click();
}

window.addEventListener("DOMContentLoaded", () => {
  loadCfg();
  $("#endpoint").addEventListener("change", () => { onEndpointChange(); saveCfg(); });
  $("#saveKey").addEventListener("click", () => { saveCfg(); $("#status").textContent = "saved in this browser"; });
  $("#clearKey").addEventListener("click", () => { $("#apiKey").value = ""; saveCfg(); $("#status").textContent = "key forgotten"; });
  $("#run").addEventListener("click", doRun);
  $("#stop").addEventListener("click", () => state.ctrl?.abort());
  $("#download").addEventListener("click", download);
  $("#browse").addEventListener("click", openBrowser);
  $("#modalClose").addEventListener("click", () => { $("#modal").hidden = true; });
  $("#modelSearch").addEventListener("input", (e) => _models && renderModels(e.target.value));
  $("#modelList").addEventListener("click", (e) => {
    const id = e.target.closest(".m")?.dataset.id; if (!id) return;
    const ta = $("#models"); const lines = ta.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (!lines.includes(id)) { ta.value = (ta.value.trim() ? ta.value.trim() + "\n" : "") + id; saveCfg(); }
  });
  // PWA install
  let deferred;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; $("#install").hidden = false; });
  $("#install").addEventListener("click", async () => { if (deferred) { deferred.prompt(); deferred = null; $("#install").hidden = true; } });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js").catch(() => {});
});
