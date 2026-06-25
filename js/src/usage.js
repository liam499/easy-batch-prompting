// Usage normalisation + best-effort cost — mirror of usage.py.

export function normalizeUsage(provider, raw) {
  if (!raw) return null;
  const inp = raw.input_tokens ?? raw.prompt_tokens ?? raw.promptTokenCount ?? null;
  const out = raw.output_tokens ?? raw.completion_tokens ?? raw.candidatesTokenCount ?? null;
  let tot = raw.total_tokens ?? raw.totalTokenCount ?? null;
  if (tot == null && (inp != null || out != null)) tot = (inp || 0) + (out || 0);
  if (inp == null && out == null && tot == null) return null;
  return { input_tokens: inp, output_tokens: out, total_tokens: tot };
}

// USD per 1,000,000 tokens, [input, output]. More specific keys first.
export const DEFAULT_PRICES = {
  "gpt-4o-mini": [0.15, 0.60],
  "gpt-4.1-mini": [0.40, 1.60],
  "gpt-4.1": [2.00, 8.00],
  "gpt-4o": [2.50, 10.00],
  "gpt-5-mini": [0.25, 2.00],
  "gpt-5": [1.25, 10.00],
  "o4-mini": [1.10, 4.40],
  "claude-3-5-haiku": [0.80, 4.00],
  "claude-haiku-4": [1.00, 5.00],
  "claude-3-5-sonnet": [3.00, 15.00],
  "claude-sonnet-4": [3.00, 15.00],
  "claude-opus-4": [15.00, 75.00],
  "gemini-2.0-flash": [0.10, 0.40],
  "gemini-1.5-flash": [0.075, 0.30],
  "gemini-1.5-pro": [1.25, 5.00],
  "llama-3.1-8b": [0.05, 0.08],
  "llama-3.3-70b": [0.12, 0.30],
  "mistral-7b": [0.05, 0.10],
  "qwen-2.5-7b": [0.05, 0.10],
  "deepseek-chat": [0.27, 1.10],
};

export function estimateCost(model, usage, prices = null) {
  if (!usage) return null;
  const table = { ...DEFAULT_PRICES, ...(prices || {}) };
  const ml = model.toLowerCase();
  const key = Object.keys(table).find((k) => ml.includes(k));
  if (!key) return null;
  const [pin, pout] = table[key];
  const inp = usage.input_tokens || 0;
  const out = usage.output_tokens || 0;
  return Math.round((inp / 1e6 * pin + out / 1e6 * pout) * 1e8) / 1e8;
}
