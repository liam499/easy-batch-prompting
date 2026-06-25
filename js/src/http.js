// Shared HTTP for the JS adapters — global fetch (Node 18+), zero dependencies.
// Same retry policy as the Python http.py: back off only on transient failures (429,
// 5xx, network/timeout); give up immediately on a permanent 4xx. Node's fetch does not
// honour HTTPS_PROXY, so the proxy-bypass the Python side needs is unnecessary here.

export class HttpError extends Error {
  constructor(message, { code = null, transient = false, attempts = null } = {}) {
    super(message);
    this.name = "HttpError";
    this.code = code;
    this.transient = transient;
    this.attempts = attempts;
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function requestJson(url, { headers = {}, body = null, method = "POST", timeout = 60000, maxRetries = 4 } = {}) {
  let delay = 2000;
  let last = null;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const opts = { method, headers: { ...headers }, signal: ctrl.signal };
      if (body !== null) {
        opts.body = JSON.stringify(body);
        opts.headers["Content-Type"] = opts.headers["Content-Type"] || "application/json";
      }
      const resp = await fetch(url, opts);
      const text = await resp.text();
      if (resp.ok) return text ? JSON.parse(text) : {};
      const transient = resp.status === 429 || (resp.status >= 500 && resp.status < 600);
      last = new HttpError(`HTTP ${resp.status}: ${text.slice(0, 600)}`, { code: resp.status, transient, attempts: attempt + 1 });
      if (!transient) throw last;
    } catch (e) {
      if (e instanceof HttpError) {
        if (!e.transient) throw e;
        last = e;
      } else {
        last = new HttpError(`network error: ${e.message}`, { transient: true, attempts: attempt + 1 });
      }
    } finally {
      clearTimeout(timer);
    }
    if (attempt === maxRetries - 1) break;
    await sleep(delay);
    delay *= 2;
  }
  throw last;
}
