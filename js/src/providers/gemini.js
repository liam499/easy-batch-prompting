// Google Gemini adapter — mirror of gemini.py.
import { HttpError, requestJson } from "../http.js";

export class GeminiProvider {
  constructor({ model, baseUrl = null, keyEnv = null, apiKey = null, timeout = 90000, maxRetries = 4 }) {
    this.model = model.startsWith("models/") ? model.slice("models/".length) : model;
    this.base = (baseUrl || "https://generativelanguage.googleapis.com/v1beta").replace(/\/+$/, "");
    this.keyEnv = keyEnv || "GEMINI_API_KEY";
    this.timeout = timeout;
    this.maxRetries = maxRetries;
    this.apiKey = apiKey ?? process.env[this.keyEnv] ?? process.env.GOOGLE_API_KEY;
    if (!this.apiKey) throw new Error(`set ${this.keyEnv} to use the gemini provider (model '${model}')`);
  }

  body(messages, sampling) {
    const contents = [];
    const system = [];
    for (const m of messages) {
      if (m.role === "system") { system.push(m.content); continue; }
      contents.push({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] });
    }
    const cfg = { temperature: sampling.temperature, maxOutputTokens: sampling.max_tokens };
    if (sampling.top_p !== 1.0) cfg.topP = sampling.top_p;
    const b = { contents, generationConfig: cfg };
    if (system.length) b.systemInstruction = { parts: [{ text: system.join(" ") }] };
    return b;
  }

  async chat(messages, sampling) {
    const url = `${this.base}/models/${this.model}:generateContent`;
    const headers = { "x-goog-api-key": this.apiKey };
    const body = await requestJson(url, { headers, body: this.body(messages, sampling), timeout: this.timeout, maxRetries: this.maxRetries });
    const cands = body.candidates;
    if (!cands || !cands.length) {
      const err = body.error;
      throw new HttpError(`no candidates in response: ${(err && err.message) || JSON.stringify(body).slice(0, 300)}`, { transient: false });
    }
    const parts = (cands[0].content && cands[0].content.parts) || [];
    const text = parts.filter((p) => "text" in p).map((p) => p.text || "").join("");
    const um = body.usageMetadata || {};
    return {
      text,
      meta: { usage: { promptTokenCount: um.promptTokenCount, candidatesTokenCount: um.candidatesTokenCount, totalTokenCount: um.totalTokenCount }, served_by: "gemini", model_returned: body.modelVersion || this.model, response_id: body.responseId, finish_reason: cands[0].finishReason },
    };
  }
}
