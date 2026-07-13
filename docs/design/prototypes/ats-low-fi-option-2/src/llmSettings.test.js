import test from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "./apiClient.js";
import {
  createLlmSettingsController,
  getLlmSettingsErrorMessage,
  getTestDisabledReason,
  releaseLlmSettingsSubscription,
} from "./llmSettings.js";

const systemConfig = {
  configured: true,
  enabled: true,
  provider_id: "approved",
  model: "model-a",
  version: 7,
  key_configured: true,
  allowed_job_ids: ["job-1", "job-2"],
  available_providers: { approved: ["model-a", "model-b"], internal: ["model-c"] },
  last_test_status: "succeeded",
  last_test_error_code: null,
  last_test_latency_ms: 320,
  last_tested_at: "2026-07-13T01:00:00Z",
};

function createClient(handler) {
  const calls = [];
  return {
    calls,
    async request(path, options = {}) {
      calls.push({ path, options });
      return handler(path, options, calls.length);
    },
  };
}

test("load enters loading then exposes the server config without an API key", async () => {
  let resolveRequest;
  const client = createClient(() => new Promise((resolve) => { resolveRequest = resolve; }));
  const controller = createLlmSettingsController({ client });

  const loading = controller.load();
  assert.equal(controller.getState().status, "loading");
  resolveRequest({ data: systemConfig });
  await loading;

  assert.equal(client.calls[0].path, "/api/v1/settings/llm");
  assert.equal(controller.getState().status, "ready");
  assert.deepEqual(controller.getState().draft, {
    provider_id: "approved",
    model: "model-a",
    enabled: true,
  });
  assert.equal("api_key" in controller.getState().config, false);
  assert.equal(controller.getState().dirty, false);
});

test("save preserves loaded job IDs and only sends a replacement key while replacing", async () => {
  const client = createClient((path, options) => {
    if (options.method === "PUT") return { data: { ...systemConfig, model: "model-b", version: 8 } };
    return { data: systemConfig };
  });
  const keys = ["save-key"];
  const controller = createLlmSettingsController({ client, createIdempotencyKey: () => keys.shift() });
  await controller.load();
  controller.updateDraft({ model: "model-b" });
  controller.startKeyReplacement();
  controller.setReplacementKey("sk-never-persist");

  await controller.save();

  const save = client.calls[1];
  assert.equal(save.path, "/api/v1/settings/llm");
  assert.equal(save.options.method, "PUT");
  assert.equal(save.options.ifMatch, '"7"');
  assert.equal(save.options.idempotencyKey, "save-key");
  assert.deepEqual(save.options.body, {
    provider_id: "approved",
    model: "model-b",
    enabled: true,
    api_key: "sk-never-persist",
    allowed_job_ids: ["job-1", "job-2"],
  });
  assert.equal(controller.getState().replacementKey, "");
  assert.equal(controller.getState().replacingKey, false);
  assert.equal(controller.getState().dirty, false);
});

test("save omits api_key when the saved key is retained", async () => {
  const client = createClient((path, options) => options.method === "PUT"
    ? { data: { ...systemConfig, enabled: false, version: 8 } }
    : { data: systemConfig });
  const controller = createLlmSettingsController({ client, createIdempotencyKey: () => "save-key" });
  await controller.load();
  controller.updateDraft({ enabled: false });
  await controller.save();

  assert.equal("api_key" in client.calls[1].options.body, false);
});

test("a failed save clears the replacement key and keeps a safe error", async () => {
  const client = createClient((path, options) => {
    if (options.method === "PUT") {
      throw new ApiError({ status: 503, code: "persistence_failed", detail: "secret backend detail" });
    }
    return { data: systemConfig };
  });
  const controller = createLlmSettingsController({ client, createIdempotencyKey: () => "save-key" });
  await controller.load();
  controller.startKeyReplacement();
  controller.setReplacementKey("sk-clear-after-attempt");

  await controller.save();

  assert.equal(client.calls[1].options.body.api_key, "sk-clear-after-attempt");
  assert.equal(controller.getState().replacementKey, "");
  assert.equal(controller.getState().replacingKey, false);
  assert.equal(controller.getState().error, getLlmSettingsErrorMessage({ code: "persistence_failed" }));
  assert.equal(controller.getState().error.includes("secret backend detail"), false);
});

test("cancel replacement clears the key and restores the clean state when it was the only change", async () => {
  const client = createClient(() => ({ data: systemConfig }));
  const controller = createLlmSettingsController({ client });
  await controller.load();
  controller.startKeyReplacement();
  controller.setReplacementKey("temporary-secret");
  assert.equal(controller.getState().dirty, true);

  controller.cancelKeyReplacement();

  assert.equal(controller.getState().replacementKey, "");
  assert.equal(controller.getState().replacingKey, false);
  assert.equal(controller.getState().dirty, false);
});

test("connection testing uses the last saved config and a fresh idempotency key", async () => {
  const client = createClient((path, options) => {
    if (path.endsWith("/test")) return { data: { status: "succeeded", safe_error_code: null, latency_ms: 184 } };
    return { data: systemConfig };
  });
  const controller = createLlmSettingsController({
    client,
    createIdempotencyKey: () => "test-key",
    now: () => new Date("2026-07-13T03:04:05Z"),
  });
  await controller.load();
  await controller.testConnection();

  assert.deepEqual(client.calls[1], {
    path: "/api/v1/settings/llm/test",
    options: { method: "POST", idempotencyKey: "test-key" },
  });
  assert.equal(controller.getState().status, "ready");
  assert.equal(controller.getState().config.last_test_latency_ms, 184);
  assert.equal(controller.getState().config.last_tested_at, "2026-07-13T03:04:05.000Z");
});

test("a rejected connection test reloads the safe result recorded by the server", async () => {
  const failedConfig = {
    ...systemConfig,
    last_test_status: "failed",
    last_test_error_code: "provider_auth_failed",
    last_test_latency_ms: null,
    last_tested_at: "2026-07-13T03:05:00Z",
  };
  const client = createClient((path, options, count) => {
    if (path.endsWith("/test")) {
      throw new ApiError({ status: 422, code: "request_failed", detail: "provider response body" });
    }
    return { data: count === 1 ? systemConfig : failedConfig };
  });
  const controller = createLlmSettingsController({ client, createIdempotencyKey: () => "test-key" });
  await controller.load();

  await controller.testConnection();

  assert.equal(client.calls[2].path, "/api/v1/settings/llm");
  assert.equal(controller.getState().status, "error");
  assert.equal(controller.getState().config.last_test_status, "failed");
  assert.equal(controller.getState().config.last_test_error_code, "provider_auth_failed");
  assert.equal(controller.getState().error, "操作未完成，请稍后重试。");
  assert.equal(controller.getState().error.includes("provider response"), false);
});

test("connection testing is blocked until a configured saved key exists and while the draft is dirty", async () => {
  assert.equal(getTestDisabledReason({ dirty: true, config: systemConfig }), "请先保存当前修改，再测试已保存的配置。");
  assert.equal(getTestDisabledReason({ dirty: false, config: { ...systemConfig, configured: false } }), "请先保存模型配置。");
  assert.equal(getTestDisabledReason({ dirty: false, config: { ...systemConfig, key_configured: false } }), "请先保存 API Key。");
  assert.equal(getTestDisabledReason({ dirty: false, config: systemConfig }), "");
});

test("resource version conflict reloads the server config and asks for review without exposing detail", async () => {
  const latest = { ...systemConfig, model: "model-b", version: 8 };
  const client = createClient((path, options, count) => {
    if (options.method === "PUT") {
      throw new ApiError({ status: 409, code: "resource_version_conflict", detail: "sensitive backend detail" });
    }
    return { data: count === 1 ? systemConfig : latest };
  });
  const controller = createLlmSettingsController({ client, createIdempotencyKey: () => "save-key" });
  await controller.load();
  controller.updateDraft({ enabled: false });
  await controller.save();

  assert.equal(client.calls.length, 3);
  assert.equal(controller.getState().status, "ready");
  assert.equal(controller.getState().draft.model, "model-b");
  assert.equal(controller.getState().message, "配置已被其他管理员更新。已加载最新设置，请检查后重试。");
  assert.equal(controller.getState().message.includes("sensitive"), false);
});

test("safe error mapping uses only known codes and never response detail", () => {
  const known = new ApiError({ code: "provider_or_model_not_allowed", detail: "private provider host" });
  const unknown = new ApiError({ code: "unexpected_internal", detail: "database password" });

  assert.equal(getLlmSettingsErrorMessage(known), "所选 Provider 或模型不可用，请重新选择。");
  assert.equal(getLlmSettingsErrorMessage(unknown), "操作未完成，请稍后重试。");
  assert.equal(getLlmSettingsErrorMessage(unknown).includes("password"), false);
});

test("dispose prevents updates and notifications after an in-flight request settles", async () => {
  let resolveRequest;
  const client = createClient(() => new Promise((resolve) => { resolveRequest = resolve; }));
  const controller = createLlmSettingsController({ client });
  let notifications = 0;
  controller.subscribe(() => { notifications += 1; });
  const loading = controller.load();
  const stateBeforeDispose = controller.getState();
  controller.dispose();
  resolveRequest({ data: systemConfig });
  await loading;

  assert.equal(controller.getState(), stateBeforeDispose);
  assert.equal(notifications, 1);
});

test("React Strict Mode cleanup releases a subscription without permanently disposing the controller", async () => {
  const client = createClient(() => ({ data: systemConfig }));
  const controller = createLlmSettingsController({ client });
  const unsubscribe = controller.subscribe(() => {});

  await controller.load();
  controller.startKeyReplacement();
  controller.setReplacementKey("temporary-key");
  releaseLlmSettingsSubscription(controller, unsubscribe);

  const observed = [];
  controller.subscribe((state) => observed.push(state.status));
  await controller.load();

  assert.equal(controller.getState().status, "ready");
  assert.equal(controller.getState().replacementKey, "");
  assert.ok(observed.includes("loading"));
  assert.equal(client.calls.length, 2);
});
