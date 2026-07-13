import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, createApiClient } from "./apiClient.js";

function jsonResponse(body, { status = 200, headers = {} } = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

test("API 请求携带会话凭据，并仅在登录后为写请求附加内存 CSRF", async () => {
  const calls = [];
  const responses = [
    jsonResponse({ data: { authenticated: true } }, { headers: { "X-CSRF-Token": "login-csrf" } }),
    new Response(null, { status: 204 }),
  ];
  const client = createApiClient({ fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return responses.shift();
  } });

  await client.login({ organization_slug: "acme", email: "hr@example.test", password: "secret" });
  await client.logout();

  assert.equal(calls[0].options.credentials, "include");
  assert.equal(calls[0].options.headers.get("X-CSRF-Token"), null);
  assert.equal(calls[1].options.credentials, "include");
  assert.equal(calls[1].options.headers.get("X-CSRF-Token"), "login-csrf");
});

test("GET /me 轮换 CSRF，后续请求支持幂等键与 If-Match", async () => {
  const calls = [];
  const responses = [
    jsonResponse({ data: { display_name: "林岚", roles: ["recruiter"] } }, { headers: { "X-CSRF-Token": "rotated-csrf" } }),
    jsonResponse({ data: { ok: true } }),
  ];
  const client = createApiClient({ fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return responses.shift();
  } });

  await client.getMe();
  await client.request("/api/v1/screening-runs", {
    method: "POST",
    body: { job_id: "job-1" },
    idempotencyKey: "request-1",
    ifMatch: '"7"',
  });

  const headers = calls[1].options.headers;
  assert.equal(headers.get("X-CSRF-Token"), "rotated-csrf");
  assert.equal(headers.get("Idempotency-Key"), "request-1");
  assert.equal(headers.get("If-Match"), '"7"');
});

test("成功的 /me 缺少响应头时保留已有 CSRF", async () => {
  const calls = [];
  const responses = [
    jsonResponse({ data: { display_name: "林岚" } }, { headers: { "X-CSRF-Token": "existing-csrf" } }),
    jsonResponse({ data: { display_name: "林岚" } }),
    jsonResponse({ data: { ok: true } }),
  ];
  const client = createApiClient({ fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return responses.shift();
  } });

  await client.getMe();
  await client.getMe();
  await client.request("/api/v1/jobs", { method: "POST", body: {} });

  assert.equal(calls[2].options.headers.get("X-CSRF-Token"), "existing-csrf");
});

test("登录尝试仍会在请求前清除已有 CSRF", async () => {
  const calls = [];
  const responses = [
    jsonResponse({ data: { display_name: "林岚" } }, { headers: { "X-CSRF-Token": "old-csrf" } }),
    jsonResponse({ data: { authenticated: true } }),
    jsonResponse({ data: { ok: true } }),
  ];
  const client = createApiClient({ fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return responses.shift();
  } });

  await client.getMe();
  await client.login({ organization_slug: "acme", email: "hr@example.test", password: "secret" });
  await client.request("/api/v1/jobs", { method: "POST", body: {} });

  assert.equal(calls[1].options.headers.get("X-CSRF-Token"), null);
  assert.equal(calls[2].options.headers.get("X-CSRF-Token"), null);
});

test("application/problem+json 被限制为安全的类型化错误字段", async () => {
  const client = createApiClient({ fetchImpl: async () => new Response(JSON.stringify({
    type: "about:blank",
    title: "Request denied",
    status: 401,
    detail: "Invalid credentials or account unavailable.",
    code: "authentication_failed",
    trace_id: "internal-trace",
    stack: "secret internals",
  }), { status: 401, headers: { "Content-Type": "application/problem+json" } }) });

  await assert.rejects(client.getMe(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 401);
    assert.equal(error.code, "authentication_failed");
    assert.equal(error.detail, "Invalid credentials or account unavailable.");
    assert.equal("trace_id" in error, false);
    assert.equal("stack" in error, true);
    assert.equal(error.stack.includes("secret internals"), false);
    return true;
  });
});

test("网络失败被标记为服务不可用错误且不透传底层消息", async () => {
  const client = createApiClient({ fetchImpl: async () => { throw new Error("connect ECONNREFUSED 127.0.0.1"); } });

  await assert.rejects(client.getMe(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.kind, "unavailable");
    assert.equal(error.message.includes("ECONNREFUSED"), false);
    return true;
  });
});

test("fetch AbortError 原样向调用方抛出", async () => {
  const expected = new DOMException("request cancelled", "AbortError");
  const client = createApiClient({ fetchImpl: async () => { throw expected; } });

  await assert.rejects(client.getMe(), (error) => {
    assert.equal(error, expected);
    return true;
  });
});

test("request 将 AbortSignal 原样传给 fetch", async () => {
  const controller = new AbortController();
  let receivedSignal;
  const client = createApiClient({ fetchImpl: async (_url, options) => {
    receivedSignal = options.signal;
    return jsonResponse({ data: [] });
  } });

  await client.request("/api/v1/jobs?limit=100", { signal: controller.signal });

  assert.equal(receivedSignal, controller.signal);
});
