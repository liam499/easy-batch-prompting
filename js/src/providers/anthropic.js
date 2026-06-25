// Anthropic Messages API adapter — mirror of anthropic.py.
import { HttpError, requestJson } from "../http.js";

const VERSION = "2023-06-01";

export class AnthropicProvider {
  constructor({ model, baseUrl = null, keyEnv = null, apiKey = null, timeout = 90000, maxRetries = 4 }) {
    this.model = model.startsWith("anthropic/") ? model.slice("anthropic/".length) : model;
    this.endpoint = (baseUrl || "https://api.anthropic.com/v1").replace(/\/+$/, "") + "/messages";
    this.keyEnv = keyEnv || "ANTHROPIC_API_KEY";
    this.timeout = timeout;
    this.maxRetries = maxRetries;
    this.apiKey = apiKey ?? process.env[this.keyEnv];
    if (!this.apiKey) throw new Error(`set ${this.keyEnv} to use the anthropic provider (model '${model}')`);
  }

  body(messages, sampling) {
    const system = messages.filter((m) => m.role === "system").map((m) => m.content).join(" ");
    const convo = messages.filter((m) => m.role !== "system").map((m) => ({ role: m.role, content: m.content }));
    const b = { model: this.model, max_tokens: sampling.max_tokens, temperature: sampling.temperature, messages: convo };
    if (system) b.system = system;
    if (sampling.top_p !== 1.0) b.top_p = sampling.top_p;
    return b;
  }

  async chat(messages, sampling) {
    const headers = { "x-api-key": this.apiKey, "anthropic-version": VERSION };
    const body = await requestJson(this.endpoint, { headers, body: this.body(messages, sampling), timeout: this.timeout, maxRetries: this.maxRetries });
    if (!body.content) {
      const err = body.error;
      throw new HttpError(`no content in response: ${(err && err.message) || JSON.stringify(body).slice(0, 300)}`, { transient: false });
    }
    const text = (body.content || []).filter((b) => b.type === "text").map((b) => b.text || "").join("");
    const u = body.usage || {};
    return {
      text,
      meta: { usage: { input_tokens: u.input_tokens, output_tokens: u.output_tokens }, served_by: "anthropic", model_returned: body.model, response_id: body.id, finish_reason: body.stop_reason },
    };
  }
}
