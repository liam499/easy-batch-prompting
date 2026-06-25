// Prompts loader — mirror of prompts.py. Accepts an array, a file path, or "-" (stdin).
import { readFileSync } from "node:fs";

function readText(source) {
  if (source === "-") return readFileSync(0, "utf8"); // fd 0 = stdin
  return readFileSync(source, "utf8");
}

function coerce(row, i) {
  if (typeof row === "string") return { text: row, id: String(i), meta: {} };
  if (row && typeof row === "object") {
    const text = row.text ?? row.prompt;
    if (text == null) throw new Error(`prompt object needs a 'text' field: ${JSON.stringify(row)}`);
    return { text: String(text), id: String(row.id ?? i), meta: row.meta ?? {} };
  }
  throw new Error(`unsupported prompt row: ${row}`);
}

/** Load prompts from an array, a .txt/.jsonl/.json file, or "-" for stdin. */
export function loadPrompts(source) {
  if (Array.isArray(source)) return source.map(coerce);
  const name = String(source);
  const text = readText(source);
  let rows;
  if (name.endsWith(".jsonl")) {
    rows = text.split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l));
  } else if (name.endsWith(".json")) {
    rows = JSON.parse(text);
    if (!Array.isArray(rows)) rows = rows.prompts ?? [];
  } else {
    rows = text.split(/\r?\n/).filter((l) => l.trim());
  }
  return rows.map(coerce);
}
