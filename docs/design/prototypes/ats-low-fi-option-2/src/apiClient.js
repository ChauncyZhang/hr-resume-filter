const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function safeString(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

export class ApiError extends Error {
  constructor({ status = 0, code = "request_failed", title = "请求失败", detail = "", kind = "request" } = {}) {
    super(kind === "unavailable" ? "服务暂时不可用" : "请求未能完成");
    this.name = "ApiError";
    this.status = Number.isInteger(status) ? status : 0;
    this.code = safeString(code, "request_failed");
    this.title = safeString(title, "请求失败");
    this.detail = safeString(detail);
    this.kind = kind;
  }
}

async function parseResponse(response) {
  if (response.status === 204) return null;
  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.toLowerCase().includes("json")) return null;
  try {
    return await response.json();
  } catch {
    throw new ApiError({ kind: "unavailable", code: "invalid_response" });
  }
}

export function createApiClient({ fetchImpl = globalThis.fetch } = {}) {
  let csrfToken = null;

  async function request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const isLogin = path === "/api/v1/auth/login";
    const refreshesCsrf = isLogin || path === "/api/v1/me";
    const headers = new Headers(options.headers || {});

    if (isLogin) csrfToken = null;
    if (STATE_CHANGING_METHODS.has(method) && !isLogin && csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
    if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
    if (options.ifMatch) headers.set("If-Match", options.ifMatch);

    let body = options.body;
    if (body !== undefined && body !== null && !(body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetchImpl(path, { method, headers, body, credentials: "include" });
    } catch {
      throw new ApiError({ kind: "unavailable", code: "service_unavailable" });
    }

    if (refreshesCsrf && response.ok) {
      const responseCsrf = response.headers.get("X-CSRF-Token");
      if (responseCsrf) csrfToken = responseCsrf;
    } else if (response.status === 401) {
      csrfToken = null;
    }

    const payload = await parseResponse(response);
    if (!response.ok) {
      const isProblem = (response.headers.get("Content-Type") || "").toLowerCase().includes("application/problem+json");
      throw new ApiError({
        status: response.status,
        code: isProblem ? safeString(payload?.code, "request_failed") : "request_failed",
        title: isProblem ? safeString(payload?.title, "请求失败") : "请求失败",
        detail: isProblem ? safeString(payload?.detail) : "",
        kind: response.status >= 500 ? "unavailable" : "request",
      });
    }
    return payload;
  }

  return {
    request,
    async login(credentials) {
      const response = await request("/api/v1/auth/login", { method: "POST", body: credentials });
      return response?.data ?? null;
    },
    async getMe() {
      const response = await request("/api/v1/me");
      return response?.data ?? null;
    },
    async logout() {
      return request("/api/v1/auth/logout", { method: "POST" });
    },
    clearCsrf() {
      csrfToken = null;
    },
  };
}

export const apiClient = createApiClient();
