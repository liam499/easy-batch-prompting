// Offline deterministic provider — the JS quickstart needs no key. Deterministic given
// (model, prompt, seed). Output text differs from the Python mock (different PRNG); what
// IS identical across languages is the schema and the custom_id (see record.js).
import { createHash } from "node:crypto";

const BITS = [
  "Here is a concise take:",
  "Consider it from three angles.",
  "The short answer is yes, with caveats.",
  "A small worked example follows.",
  "In one line: it depends on the context.",
  "Two things matter most here.",
];

function seeded(str) {
  // 32-bit FNV-1a seed -> mulberry32 PRNG
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619) >>> 0;
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class MockProvider {
  constructor(model = "mock") { this.model = model; }
  async chat(messages, sampling) {
    let prompt = "";
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "user") { prompt = messages[i].content; break; }
    const key = createHash("sha256").update(`${this.model}|${prompt}|${messages.length}|${sampling.seed}`).digest("hex");
    const rng = seeded(key);
    const n = 1 + Math.floor(rng() * 3);
    const body = Array.from({ length: n }, () => BITS[Math.floor(rng() * BITS.length)]).join(" ");
    const text = `[${this.model}] ${body}`;
    const usage = { prompt_tokens: Math.max(1, (prompt.length / 4) | 0), completion_tokens: Math.max(1, (text.length / 4) | 0) };
    return { text, meta: { usage, served_by: "mock", model_returned: this.model, finish_reason: "stop", synthetic: true } };
  }
}
