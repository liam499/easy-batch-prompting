// OpenAI-compatible adapter — mirror of openai_compat.py. Covers OpenAI/OpenRouter/
// Groq/Together/Fireworks/DeepInfra/DeepSeek/xAI/Mistral/Ollama/vLLM via base_url+key,
// including the reasoning-model quirks and the "null problem" diagnostic.
import { HttpError, requestJson } from "../http.js";

const REASONING = ["gpt-5", "o1", "o3", "o4"];

export class OpenAICompatProvider {
  constructor({ model, baseUrl, keyEnv = null, reasoningEffort = null, routing = null, extraHeaders = {}, providerName = "openai_compat", apiKey = null, timeout = 90000, maxRetries = 4 }) {
    this.model = model;
    this.base = baseUrl.replace(/\/+$/, "");
    this.endpoint = this.base + "/chat/completions";
    this.reasoningEffort = reasoningEffort;
    this.routing = routing;
    this.extraHeaders = extraHeaders || {};
    this.providerName = providerName;
    this.timeout = timeout;
    this.maxRetries = maxRetries;
    this.apiKey = apiKey ?? (keyEnv ? process.env[keyEnv] : null);
    if (keyEnv && !this.apiKey) throw new Error(`set ${keyEnv} to use provider '${providerName}' (model '${model}')`);
  }

  isReasoning() {
    const tail = this.model.toLowerCase().split("/").pop();
    return REASONING.some((p) => tail.startsWith(p));
  }

  body(messages, sampling) {
    const b = { model: this.model, messages };
    if (this.isReasoning()) {
      b.max_completion_tokens = sampling.max_tokens;
      if (this.reasoningEffort) b.reasoning_effort = this.reasoningEffort;
    } else {
      b.temperature = sampling.temperature;
      b.max_tokens = sampling.max_tokens;
      if (sampling.top_p !== 1.0) b.top_p = sampling.top_p;
    }
    if (sampling.seed != null) b.seed = sampling.seed;
    if (this.routing) b.provider = this.routing;
    return b;
  }

  async chat(messages, sampling) {
    const headers = { ...this.extraHeaders };
    if (this.apiKey) headers["Authorization"] = `Bearer ${this.apiKey}`;
    const body = await requestJson(this.endpoint, { headers, body: this.body(messages, sampling), timeout: this.timeout, maxRetries: this.maxRetries });
    if (!body.choices) {
      const err = body.error;
      throw new HttpError(`no choices in response: ${(err && err.message) || JSON.stringify(body).slice(0, 300)}`, { transient: false });
    }
    const choice = body.choices[0] || {};
    const text = (choice.message && choice.message.content) || "";
    const finish = choice.finish_reason;
    const meta = { usage: body.usage, served_by: body.provider || this.providerName, model_returned: body.model, response_id: body.id, finish_reason: finish, reasoning_effort: this.reasoningEffort };
    if (!text && this.isReasoning() && (finish === "length" || finish == null)) meta.empty_reason = "reasoning_starved";
    return { text, meta };
  }
}
