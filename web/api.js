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
      const message = typeof detail === "object" && detail !== null ? detail.message : detail;
      const error = new Error(message || `请求失败（${response.status}）`);
      error.status = response.status;
      if (typeof detail === "object" && detail !== null) Object.assign(error, detail);
      throw error;
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}
