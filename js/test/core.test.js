import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";

const FIELDS = ["schema", "custom_id", "run_id", "ts", "provider", "model", "model_returned",
  "served_by", "prompt_id", "prompt", "system", "messages", "sampling", "repeat", "output",
  "finish_reason", "error", "usage", "cost_usd", "latency_ms", "prompt_meta", "model_meta", "raw"];

test("run() mock grid -> JSONL with provenance", async () => {
  const out = join(mkdtempSync(join(tmpdir(), "aeb-")), "r.jsonl");
  const res = await run(["a", "b"], ["mock:x", "mock:y"], out);
  assert.equal(res.ok, 4);
  assert.equal(res.failed, 0);
  const recs = readFileSync(out, "utf8").trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(recs.length, 4);
  for (const r of recs) {
    assert.equal(r.schema, "aieasybatch/v1");
    assert.ok(r.custom_id && r.output.startsWith("["));
    assert.equal(r.error, null);
    assert.ok(r.usage.total_tokens >= 0);
    for (const f of FIELDS) assert.ok(f in r, `missing field ${f}`);
  }
  assert.equal(new Set(recs.map((r) => r.custom_id)).size, 4);
});

test("run() is deterministic under a seed", async () => {
  const a = await run(["a", "b"], ["mock:x"], "", { seed: 1 });
  const b = await run(["a", "b"], ["mock:x"], "", { seed: 1 });
  assert.deepEqual(a.records().map((r) => r.output), b.records().map((r) => r.output));
});

test("resume tops up only the gap", async () => {
  const out = join(mkdtempSync(join(tmpdir(), "aeb-")), "r.jsonl");
  await run(["a"], ["mock:x"], out);
  const res = await run(["a", "b"], ["mock:x"], out, { resume: true });
  assert.equal(res.ok, 1);
  assert.equal(readFileSync(out, "utf8").trim().split("\n").length, 2);
});

test("record field set is the canonical schema (cross-language)", async () => {
  const res = await run(["x"], ["mock:x"], "");
  assert.deepEqual(Object.keys(res.records()[0]).sort(), [...FIELDS].sort());
});

test("in-memory out keeps records without a file", async () => {
  const res = await run(["a"], ["mock:x"], "");
  assert.equal(res.path, null);
  assert.equal(res.records().length, 1);
});
