import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { ApiError } from "./apiClient.js";

const governance = await import("./governanceSettings.js").catch(() => ({}));
const {
  buildAuditLogsPath,
  createGovernanceSettingsController,
  getGovernanceErrorMessage,
  normalizeAuditRecord,
  normalizeRetentionPolicy,
  releaseGovernanceSettingsSubscription,
} = governance;

const policy = {
  id: "policy-1",
  version: 7,
  terminal_days: 730,
  talent_pool_days: 1095,
  backup_window_days: 90,
  updated_at: "2026-07-14T01:00:00Z",
  updated_by: { id: "user-1", display_name: "系统管理员", email: "private@example.com" },
  raw_metadata: { secret: true },
};

function requireFunction(value, name) {
  assert.equal(typeof value, "function", `${name} should be implemented`);
}

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

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test("audit URL encodes only documented filters and cursor", () => {
  requireFunction(buildAuditLogsPath, "buildAuditLogsPath");
  const path = buildAuditLogsPath({
    from: "2026-07-01T00:00:00+08:00",
    to: "2026-07-14T12:00:00+08:00",
    actorId: "actor/id",
    eventType: "candidate.created & reviewed",
    resourceType: "candidate",
    resourceId: "resource?1",
    outcome: "success",
    ignored: "must-not-leak",
  }, { cursor: "cursor+/=", limit: 25 });

  const url = new URL(path, "https://example.test");
  assert.equal(url.pathname, "/api/v1/audit-logs");
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    from: "2026-07-01T00:00:00+08:00",
    to: "2026-07-14T12:00:00+08:00",
    actor_id: "actor/id",
    event_type: "candidate.created & reviewed",
    resource_type: "candidate",
    resource_id: "resource?1",
    outcome: "success",
    cursor: "cursor+/=",
    limit: "25",
  });
});

test("normalization retains only the documented safe audit and retention projection", () => {
  requireFunction(normalizeAuditRecord, "normalizeAuditRecord");
  requireFunction(normalizeRetentionPolicy, "normalizeRetentionPolicy");
  const row = normalizeAuditRecord({
    id: "audit-1",
    created_at: "2026-07-14T02:00:00Z",
    actor: { id: "actor-1", display_name: "周明", email: "secret@example.com" },
    category: "recruiting",
    event_type: "candidate.created",
    resource: { type: "candidate", id: "candidate-1", label: "授权候选人", contacts: ["13800000000"] },
    outcome: "success",
    network_ref: "abcdef012345",
    trace_id: "trace-1",
    summary: "创建候选人",
    metadata: { resume_text: "raw resume", ip: "10.0.0.1" },
    detail: "private server detail",
  });

  assert.deepEqual(row, {
    id: "audit-1",
    createdAt: "2026-07-14T02:00:00Z",
    actor: { id: "actor-1", displayName: "周明" },
    category: "recruiting",
    eventType: "candidate.created",
    resource: { type: "candidate", id: "candidate-1", label: "授权候选人" },
    outcome: "success",
    networkRef: "abcdef012345",
    traceId: "trace-1",
    summary: "创建候选人",
  });
  assert.deepEqual(normalizeRetentionPolicy(policy), {
    id: "policy-1",
    version: 7,
    terminalDays: 730,
    talentPoolDays: 1095,
    backupWindowDays: 90,
    updatedAt: "2026-07-14T01:00:00Z",
    updatedBy: { id: "user-1", displayName: "系统管理员" },
  });
  assert.equal(JSON.stringify(row).includes("resume"), false);
  assert.equal(JSON.stringify(normalizeRetentionPolicy(policy)).includes("private@example.com"), false);
});

test("audit reload clears old scope immediately and exposes loading then empty", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const second = deferred();
  const client = createClient((_path, _options, count) => count === 1
    ? { data: [{ id: "audit-1", actor: { display_name: "周明" } }], meta: { next_cursor: null, limit: 50 } }
    : second.promise);
  const controller = createGovernanceSettingsController({ client });
  await controller.loadAudit({ outcome: "success" });
  assert.equal(controller.getState().audit.status, "ready");
  assert.equal(controller.getState().audit.rows.length, 1);

  const loading = controller.loadAudit({ outcome: "denied" });
  assert.equal(controller.getState().audit.status, "loading");
  assert.deepEqual(controller.getState().audit.rows, []);
  second.resolve({ data: [], meta: { next_cursor: null, limit: 50 } });
  await loading;
  assert.equal(controller.getState().audit.status, "empty");
});

test("audit cursor paging appends and deduplicates by audit id", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const client = createClient((_path, _options, count) => count === 1
    ? { data: [{ id: "audit-1" }, { id: "audit-2" }], meta: { next_cursor: "next token", limit: 2 } }
    : { data: [{ id: "audit-2" }, { id: "audit-3" }], meta: { next_cursor: null, limit: 2 } });
  const controller = createGovernanceSettingsController({ client });
  await controller.loadAudit({ eventType: "candidate.created" });
  await controller.loadMoreAudit();

  assert.deepEqual(controller.getState().audit.rows.map((row) => row.id), ["audit-1", "audit-2", "audit-3"]);
  assert.equal(controller.getState().audit.nextCursor, null);
  assert.equal(client.calls[1].path.includes("cursor=next+token"), true);
});

test("audit reload aborts the previous request and stale success or failure cannot replace current state", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const first = deferred();
  const second = deferred();
  const client = createClient((_path, _options, count) => count === 1 ? first.promise : second.promise);
  const controller = createGovernanceSettingsController({ client });
  const oldLoad = controller.loadAudit({ outcome: "failure" });
  const oldSignal = client.calls[0].options.signal;
  const newLoad = controller.loadAudit({ outcome: "success" });
  assert.equal(oldSignal.aborted, true);

  second.resolve({ data: [{ id: "new" }], meta: { next_cursor: null, limit: 50 } });
  await newLoad;
  first.reject(new ApiError({ code: "service_unavailable", detail: "stale private detail" }));
  await oldLoad;
  assert.deepEqual(controller.getState().audit.rows.map((row) => row.id), ["new"]);
  assert.equal(controller.getState().audit.error, "");
});

test("audit and retention independently expose denied and safe retryable error states", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const client = createClient((path) => {
    if (path.includes("audit-logs")) throw new ApiError({ status: 404, code: "resource_not_found", detail: "private row scope" });
    throw new ApiError({ status: 503, code: "service_unavailable", detail: "database password" });
  });
  const controller = createGovernanceSettingsController({ client });
  await Promise.all([controller.loadAudit(), controller.loadRetention()]);

  assert.equal(controller.getState().audit.status, "denied");
  assert.equal(controller.getState().retention.status, "error");
  assert.equal(controller.getState().retention.error.includes("password"), false);
  assert.equal(getGovernanceErrorMessage({ code: "unexpected", detail: "secret" }).includes("secret"), false);
});

test("audit and retention latest-operation generations do not abort each other", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const audit = deferred();
  const retention = deferred();
  const client = createClient((path) => path.includes("audit-logs") ? audit.promise : retention.promise);
  const controller = createGovernanceSettingsController({ client });
  const auditLoad = controller.loadAudit();
  const auditSignal = client.calls[0].options.signal;
  const retentionLoad = controller.loadRetention();
  assert.equal(auditSignal.aborted, false);
  retention.resolve({ data: policy });
  audit.resolve({ data: [], meta: { next_cursor: null, limit: 50 } });
  await Promise.all([auditLoad, retentionLoad]);
  assert.equal(controller.getState().retention.status, "ready");
  assert.equal(controller.getState().audit.status, "empty");
});

test("unchanged or increased retention saves directly with quoted If-Match and exact body", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const client = createClient((path, options) => {
    if (options.method === "PATCH") return { data: { ...policy, version: 8, terminal_days: 800 } };
    return { data: policy };
  });
  const controller = createGovernanceSettingsController({ client, createIdempotencyKey: () => "save-key-1" });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 800 });
  const result = await controller.saveRetention();

  assert.equal(result, true);
  assert.deepEqual(client.calls[1], {
    path: "/api/v1/settings/retention-policy",
    options: {
      method: "PATCH",
      body: { terminal_days: 800, talent_pool_days: 1095, backup_window_days: 90 },
      ifMatch: '"7"',
      idempotencyKey: "save-key-1",
      signal: client.calls[1].options.signal,
    },
  });
  assert.equal(controller.getState().retention.policy.version, 8);
});

test("shortening requires a server preview and explicit confirmation before PATCH", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const client = createClient((path, options) => {
    if (path.endsWith("/previews")) return { data: { current_version: 7, shortening: true, affected_candidate_count: 23, impact_token: "token-secret", expires_at: "2026-07-14T02:10:00Z" } };
    if (options.method === "PATCH") return { data: { ...policy, version: 8, terminal_days: 365 } };
    return { data: policy };
  });
  const controller = createGovernanceSettingsController({ client, createIdempotencyKey: () => "shorten-key" });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 365 });
  const prepared = await controller.saveRetention();

  assert.equal(prepared, false);
  assert.equal(client.calls.some((call) => call.options.method === "PATCH"), false);
  assert.deepEqual(controller.getState().retention.preview, {
    affectedCandidateCount: 23,
    expiresAt: "2026-07-14T02:10:00Z",
  });
  assert.equal(JSON.stringify(controller.getState()).includes("token-secret"), false);

  const confirmed = await controller.confirmRetentionSave();
  assert.equal(confirmed, true);
  const patch = client.calls.find((call) => call.options.method === "PATCH");
  assert.equal(patch.options.body.impact_token, "token-secret");
});

test("draft change after preview invalidates the token and confirmation gate", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const client = createClient((path) => path.endsWith("/previews")
    ? { data: { current_version: 7, shortening: true, affected_candidate_count: 4, impact_token: "token", expires_at: "2026-07-14T02:10:00Z" } }
    : { data: policy });
  const controller = createGovernanceSettingsController({ client });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 365 });
  await controller.saveRetention();
  controller.updateRetentionDraft({ terminalDays: 364 });

  assert.equal(controller.getState().retention.preview, null);
  assert.equal(await controller.confirmRetentionSave(), false);
  assert.equal(client.calls.some((call) => call.options.method === "PATCH"), false);
});

test("stale or expired preview failure clears confirmation and requires a fresh preview", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  let previews = 0;
  const client = createClient((path, options) => {
    if (path.endsWith("/previews")) {
      previews += 1;
      return { data: { current_version: 7, shortening: true, affected_candidate_count: 5, impact_token: `token-${previews}`, expires_at: "2026-07-14T02:10:00Z" } };
    }
    if (options.method === "PATCH") throw new ApiError({ status: 409, code: "retention_preview_stale", detail: "candidate private data" });
    return { data: policy };
  });
  const controller = createGovernanceSettingsController({ client });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 365 });
  await controller.saveRetention();
  await controller.confirmRetentionSave();

  assert.equal(controller.getState().retention.preview, null);
  assert.equal(controller.getState().retention.error.includes("private"), false);
  await controller.saveRetention();
  assert.equal(previews, 2);
});

test("ambiguous save failure reuses key and body while terminal failure creates a fresh intent", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const keys = ["key-1", "key-2", "key-3"];
  let attempts = 0;
  const client = createClient((_path, options) => {
    if (options.method !== "PATCH") return { data: policy };
    attempts += 1;
    if (attempts === 1) throw new ApiError({ status: 503, code: "service_unavailable", kind: "unavailable" });
    if (attempts === 2) throw new ApiError({ status: 422, code: "validation_failed" });
    return { data: { ...policy, version: 8, terminal_days: 800 } };
  });
  const controller = createGovernanceSettingsController({ client, createIdempotencyKey: () => keys.shift() });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 800 });
  await controller.saveRetention();
  await controller.saveRetention();
  await controller.saveRetention();

  const patches = client.calls.filter((call) => call.options.method === "PATCH");
  assert.equal(patches[0].options.idempotencyKey, "key-1");
  assert.equal(patches[1].options.idempotencyKey, "key-1");
  assert.deepEqual(patches[1].options.body, patches[0].options.body);
  assert.equal(patches[2].options.idempotencyKey, "key-2");
  assert.equal(controller.getState().retention.status, "ready");
});

test("successful save resets idempotency and the next logical save gets a fresh key", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const keys = ["key-1", "key-2"];
  let version = 7;
  const client = createClient((_path, options) => {
    if (options.method !== "PATCH") return { data: { ...policy, version } };
    version += 1;
    return { data: { ...policy, version, terminal_days: options.body.terminal_days } };
  });
  const controller = createGovernanceSettingsController({ client, createIdempotencyKey: () => keys.shift() });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 800 });
  await controller.saveRetention();
  controller.updateRetentionDraft({ terminalDays: 900 });
  await controller.saveRetention();

  const patches = client.calls.filter((call) => call.options.method === "PATCH");
  assert.deepEqual(patches.map((call) => call.options.idempotencyKey), ["key-1", "key-2"]);
});

test("version conflict reloads the current policy and asks the user to review", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const latest = { ...policy, version: 8, terminal_days: 900 };
  const client = createClient((_path, options, count) => {
    if (options.method === "PATCH") throw new ApiError({ status: 409, code: "resource_version_conflict", detail: "private conflict detail" });
    return { data: count === 1 ? policy : latest };
  });
  const controller = createGovernanceSettingsController({ client });
  await controller.loadRetention();
  controller.updateRetentionDraft({ terminalDays: 800 });
  const saved = await controller.saveRetention();

  assert.equal(saved, false);
  assert.equal(controller.getState().retention.policy.version, 8);
  assert.equal(controller.getState().retention.draft.terminalDays, 900);
  assert.equal(controller.getState().retention.message.includes("检查"), true);
  assert.equal(controller.getState().retention.message.includes("private"), false);
});

test("Strict Mode release aborts requests and clears preview without permanently disposing the controller", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  requireFunction(releaseGovernanceSettingsSubscription, "releaseGovernanceSettingsSubscription");
  const pending = deferred();
  const client = createClient((_path, _options, count) => count === 1 ? pending.promise : { data: policy });
  const controller = createGovernanceSettingsController({ client });
  const unsubscribe = controller.subscribe(() => {});
  const loading = controller.loadAudit();
  const signal = client.calls[0].options.signal;
  releaseGovernanceSettingsSubscription(controller, unsubscribe);
  assert.equal(signal.aborted, true);
  pending.resolve({ data: [{ id: "late" }], meta: { next_cursor: null, limit: 50 } });
  await loading;

  const observed = [];
  controller.subscribe((state) => observed.push(state.retention.status));
  await controller.loadRetention();
  assert.equal(controller.getState().retention.status, "ready");
  assert.equal(observed.includes("ready"), true);
});

test("dispose aborts in-flight operations and suppresses late state updates", async () => {
  requireFunction(createGovernanceSettingsController, "createGovernanceSettingsController");
  const pending = deferred();
  const client = createClient(() => pending.promise);
  const controller = createGovernanceSettingsController({ client });
  let notifications = 0;
  controller.subscribe(() => { notifications += 1; });
  const loading = controller.loadRetention();
  const stateBeforeDispose = controller.getState();
  const signal = client.calls[0].options.signal;
  controller.dispose();
  assert.equal(signal.aborted, true);
  pending.resolve({ data: policy });
  await loading;
  assert.equal(controller.getState(), stateBeforeDispose);
  assert.equal(notifications, 1);
});

test("Settings UI uses the real governance controller and safe SET-04 projection", () => {
  const source = readFileSync(new URL("./SettingsViews.jsx", import.meta.url), "utf8");

  assert.match(source, /createGovernanceSettingsController/);
  assert.match(source, /loadMoreAudit/);
  assert.match(source, /terminalDays/);
  assert.match(source, /talentPoolDays/);
  assert.match(source, /backupWindowDays/);
  assert.match(source, /网络标识/);
  assert.match(source, /confirmDisabled/);
  assert.match(source, /<AuditSettings key=\{currentRole\}/);
  assert.doesNotMatch(source, /const auditRows/);
  assert.doesNotMatch(source, /来源 IP/);
  assert.doesNotMatch(source, /raw_metadata|error\.detail/);
});
