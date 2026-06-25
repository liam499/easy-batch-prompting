#!/usr/bin/env node
// aieasybatch CLI (JS) — mirrors `aieasybatch run`. Zero deps; a tiny hand-rolled parser.
import { run } from "./core.js";
import { loadRoster } from "./roster.js";

const HELP = `aieasybatch — brain-dead-simple batch prompting (JS)

Usage: aieasybatch run [PROMPTS] -m provider:model [options]

  PROMPTS              prompts file, or - for stdin (or use -p)
  -p, --prompt TEXT    inline prompt (repeatable)
  -m, --model M        provider:model, e.g. openai:gpt-4o-mini (repeatable)
  --roster FILE        roster JSON file
  -o, --out FILE       output JSONL, or - for stdout (default: -)
  --system TEXT        system prompt for every call
  --repeats N  --temperature F  --top-p F  --max-tokens N  --seed N
  --concurrency N      total in-flight calls (default 16)
  --per-model N        max simultaneous calls to one model (429 guard)
  --resume             skip cells already complete in --out
  --retry-errors       on resume, also retry errored cells
  -q, --quiet          don't print the summary
`;

async function main(argv) {
  const args = argv.slice(2);
  if (!args.length || args[0] === "-h" || args[0] === "--help") { process.stdout.write(HELP); return 0; }
  let i = args[0] === "run" ? 1 : 0;
  const o = { models: [], prompts: [], promptFile: null, roster: null, out: "-", system: null,
              repeats: 1, temperature: 1.0, top_p: 1.0, max_tokens: 512, seed: 0,
              concurrency: 16, per_model: null, resume: false, retry_errors: false, quiet: false };
  const next = () => args[++i];
  for (; i < args.length; i++) {
    const a = args[i];
    if (a === "-m" || a === "--model") o.models.push(next());
    else if (a === "-p" || a === "--prompt") o.prompts.push(next());
    else if (a === "--roster") o.roster = next();
    else if (a === "-o" || a === "--out") o.out = next();
    else if (a === "--system") o.system = next();
    else if (a === "--repeats") o.repeats = +next();
    else if (a === "--temperature") o.temperature = +next();
    else if (a === "--top-p") o.top_p = +next();
    else if (a === "--max-tokens") o.max_tokens = +next();
    else if (a === "--seed") o.seed = +next();
    else if (a === "--concurrency") o.concurrency = +next();
    else if (a === "--per-model") o.per_model = +next();
    else if (a === "--resume") o.resume = true;
    else if (a === "--retry-errors") o.retry_errors = true;
    else if (a === "-q" || a === "--quiet") o.quiet = true;
    else if (!a.startsWith("-") && !o.promptFile) o.promptFile = a;
    else { process.stderr.write(`unknown argument: ${a}\n`); return 2; }
  }

  const prompts = o.prompts.length ? o.prompts : o.promptFile;
  if (!prompts) { process.stderr.write("error: provide prompts (a file, -, or one or more -p)\n"); return 2; }
  let models = [...o.models];
  if (o.roster) models = models.concat(loadRoster(o.roster));
  if (!models.length) { process.stderr.write("error: provide at least one -m provider:model or a --roster file\n"); return 2; }
  if (o.resume && (o.out === "-" || o.out === "")) { process.stderr.write("error: --resume needs a file --out (not stdout)\n"); return 2; }

  const res = await run(prompts, models, o.out, {
    repeats: o.repeats, temperature: o.temperature, top_p: o.top_p, max_tokens: o.max_tokens, seed: o.seed,
    concurrency: o.concurrency, per_model_concurrency: o.per_model, resume: o.resume,
    retry_errors: o.retry_errors, system: o.system,
  });
  if (!o.quiet) process.stderr.write(`wrote ${res.ok + res.failed} records (${res.ok} ok, ${res.failed} failed) to ${res.path || "stdout"}\n`);
  return 0;
}

main(process.argv).then((c) => process.exit(c)).catch((e) => { process.stderr.write(String((e && e.stack) || e) + "\n"); process.exit(1); });
