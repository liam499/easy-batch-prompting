// Provider registry — mirror of registry.py. Shorthands carry base_url + key env.
import { MockProvider } from "./providers/mock.js";
import { OpenAICompatProvider } from "./providers/openaiCompat.js";
import { AnthropicProvider } from "./providers/anthropic.js";
import { GeminiProvider } from "./providers/gemini.js";

const OPENAI_COMPAT = {
  openai: ["https://api.openai.com/v1", "OPENAI_API_KEY", {}],
  openrouter: ["https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", { headers: { "HTTP-Referer": "https://github.com/liam499/easy-batch-prompting", "X-Title": "aieasybatch" }, routing: true }],
  groq: ["https://api.groq.com/openai/v1", "GROQ_API_KEY", {}],
  together: ["https://api.together.xyz/v1", "TOGETHER_API_KEY", {}],
  fireworks: ["https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", {}],
  deepinfra: ["https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY", {}],
  deepseek: ["https://api.deepseek.com", "DEEPSEEK_API_KEY", {}],
  xai: ["https://api.x.ai/v1", "XAI_API_KEY", {}],
  mistral: ["https://api.mistral.ai/v1", "MISTRAL_API_KEY", {}],
  ollama: ["http://localhost:11434/v1", null, {}],
  lmstudio: ["http://localhost:1234/v1", null, {}],
  vllm: ["http://localhost:8000/v1", null, {}],
};

const custom = new Map();

export function register(name, factory) { custom.set(name, factory); }

export function knownProviders() {
  return [...new Set([...Object.keys(OPENAI_COMPAT), "anthropic", "gemini", "mock", ...custom.keys()])].sort();
}

export function getProvider(spec) {
  const name = spec.provider;
  if (custom.has(name)) return custom.get(name)(spec);
  if (name === "mock") return new MockProvider(spec.model);
  if (name in OPENAI_COMPAT) {
    const [baseUrl, keyEnv, opts] = OPENAI_COMPAT[name];
    return new OpenAICompatProvider({
      model: spec.model,
      baseUrl: spec.base_url || baseUrl,
      keyEnv: spec.key_env || keyEnv,
      reasoningEffort: spec.reasoning_effort || null,
      routing: opts.routing ? (spec.extra && spec.extra.routing) || null : null,
      extraHeaders: opts.headers || {},
      providerName: name,
    });
  }
  if (name === "anthropic") return new AnthropicProvider({ model: spec.model, baseUrl: spec.base_url, keyEnv: spec.key_env });
  if (name === "gemini") return new GeminiProvider({ model: spec.model, baseUrl: spec.base_url, keyEnv: spec.key_env });
  throw new Error(`unknown provider '${name}'. Known: ${knownProviders().join(", ")}. Add one with register('${name}', factory).`);
}
