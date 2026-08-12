const INTERNAL_ERROR_MESSAGES = new Map([
  ["there are no due Subject Wakes to freeze", "当前这一刻没有需要你处理的下一步。"],
  ["freeze the current logical moment before staging intent", "当前这一刻还没有可以落笔的下一步。"],
  ["freeze the current logical moment before staging tool", "当前这一刻还没有可以落笔的下一步。"],
]);

const INTERNAL_ERROR_WORDS = /\b(?:Subject|Wake|Profile|MCP|Worldline|Lifetime|logical moment|worldline_id)\b/i;

export function userFacingErrorMessage(detail, status) {
  const raw = typeof detail === "object" && detail !== null ? detail.message : detail;
  if (typeof raw !== "string" || !raw.trim()) {
    return status === 503 ? "卷册暂时无法回应，请稍后再试。" : "请求没有完成，请稍后再试。";
  }
  const known = INTERNAL_ERROR_MESSAGES.get(raw.trim());
  if (known) return known;
  if (/[一-鿿]/.test(raw) && !INTERNAL_ERROR_WORDS.test(raw)) return raw;
  return status === 503 ? "卷册暂时无法回应，请稍后再试。" : "请求没有完成，请稍后再试。";
}

export async function api(path, options = {}) {
  const { timeoutMs = 180000, ...requestOptions } = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...requestOptions,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(requestOptions.headers || {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      const error = new Error(userFacingErrorMessage(detail, response.status));
      error.status = response.status;
      if (typeof detail === "object" && detail !== null) Object.assign(error, detail);
      throw error;
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}
