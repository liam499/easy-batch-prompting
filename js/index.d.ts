// Type definitions for aieasybatch (JS). Hand-written so there is no build step.

export interface Sampling {
  temperature: number;
  top_p: number;
  max_tokens: number;
  seed: number | null;
  reasoning_effort: string | null;
}

export interface Usage {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
}

export interface BatchRecord {
  schema: string;
  custom_id: string;
  run_id: string;
  ts: string;
  provider: string;
  model: string;
  model_returned: string | null;
  served_by: string | null;
  prompt_id: string;
  prompt: string;
  system: string | null;
  messages: unknown[] | null;
  sampling: Sampling;
  repeat: number;
  output: string | null;
  finish_reason: string | null;
  error: { type: string; message: string; attempts: number | null } | null;
  usage: Usage | null;
  cost_usd: number | null;
  latency_ms: number | null;
  prompt_meta: { [k: string]: unknown };
  model_meta: { [k: string]: unknown };
  raw: { [k: string]: unknown };
}

export type ModelSpec = {
  provider: string;
  model: string;
  base_url?: string;
  key_env?: string;
  reasoning_effort?: string;
  max_tokens?: number;
  meta?: { [k: string]: unknown };
  [k: string]: unknown;
};

export type ModelSelector = string | ModelSpec;
export type PromptInput = string | { text?: string; prompt?: string; id?: string | number; meta?: object };

export interface RunOptions {
  repeats?: number;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  seed?: number | null;
  concurrency?: number;
  per_model_concurrency?: number | null;
  resume?: boolean;
  retry_errors?: boolean;
  system?: string | null;
  on_record?: (rec: BatchRecord) => void;
  registry?: (spec: ModelSpec) => unknown;
  prices?: { [model: string]: [number, number] };
}

export interface RunResult {
  path: string | null;
  ok: number;
  failed: number;
  run_id: string;
  records(): BatchRecord[];
}

export function run(prompts: PromptInput[] | string, models: ModelSelector[] | string,
                    out?: string, opts?: RunOptions): Promise<RunResult>;
export function loadPrompts(source: PromptInput[] | string): { text: string; id: string; meta: object }[];
export function loadRoster(source: ModelSelector[] | string): ModelSpec[];
export function parseModel(spec: ModelSelector): ModelSpec;
export function label(spec: ModelSpec): string;
export function register(name: string, factory: (spec: ModelSpec) => unknown): void;
export function getProvider(spec: ModelSpec): unknown;
export function knownProviders(): string[];
export function customId(provider: string, model: string, prompt: string,
                         system?: string | null, repeat?: number): string;
export function normalizeUsage(provider: string, raw: object | null): Usage | null;
export function estimateCost(model: string, usage: Usage | null,
                             prices?: { [model: string]: [number, number] }): number | null;
export const SCHEMA: string;
export const version: string;
