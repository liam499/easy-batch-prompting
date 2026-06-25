import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { customId } from "../src/record.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(join(here, "../../tests/fixtures/custom_ids.json"), "utf8"));

test("customId matches the Python-generated fixture (cross-language hash parity)", () => {
  assert.ok(fixture.length >= 5);
  for (const c of fixture) {
    assert.equal(
      customId(c.provider, c.model, c.prompt, c.system, c.repeat),
      c.custom_id,
      `custom_id mismatch for ${c.provider}:${c.model} (repeat ${c.repeat})`,
    );
  }
});
