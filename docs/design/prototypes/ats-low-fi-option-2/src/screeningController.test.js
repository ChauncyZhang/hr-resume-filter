import test from "node:test";
import assert from "node:assert/strict";
import {
  createScreeningController,
  normalizeScreeningTask,
} from "./screeningController.js";

function createClient(responses = []) {
  const calls = [];
  return {
    calls,
    async request(path, options = {}) {
      calls.push({ path, options });
      const response = responses.shift();
      return typeof response === "function" ? response(path, options) : response;
    },
  };
}

function run(overrides = {}) {
  return {
    id: "run-1",
    job_id: "job-1",
    source: "upload",
    status: "queued",
    total_count: 3,
    processed_count: 0,
    ...overrides,
  };
}

function item(overrides = {}) {
  return {
    id: "item-1",
    filename: "resume.pdf",
    status: "queued",
    llm_status: "not_requested",
    rule_result: null,
    llm_evaluation: null,
    ...overrides,
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

test("lists job options from GET /jobs with only id and title", async () => {
  const client = createClient([{ data: [{ id: "job-1", title: "AI 工程师", status: "open" }] }]);
  const controller = createScreeningController({ client });

  assert.deepEqual(await controller.listJobs(), [{ id: "job-1", title: "AI 工程师" }]);
  assert.equal(client.calls[0].path, "/api/v1/jobs?limit=100");
  assert.deepEqual(client.calls[0].options, {});
});

test("lists every job page using the server cursor and the same abort signal", async () => {
  const signal = new AbortController().signal;
  const client = createClient([
    {
      data: [{ id: "job-1", title: "AI 工程师" }],
      meta: { limit: 100, next_cursor: "opaque cursor/2" },
    },
    {
      data: [{ id: "job-101", title: "数据平台主管" }],
      meta: { limit: 100, next_cursor: null },
    },
  ]);
  const controller = createScreeningController({ client });

  assert.deepEqual(await controller.listJobs({ signal }), [
    { id: "job-1", title: "AI 工程师" },
    { id: "job-101", title: "数据平台主管" },
  ]);
  assert.deepEqual(client.calls, [
    { path: "/api/v1/jobs?limit=100", options: { signal } },
    { path: "/api/v1/jobs?limit=100&cursor=opaque%20cursor%2F2", options: { signal } },
  ]);
});

test("lists screening tasks from the server and preserves job and creator context", async () => {
  const client = createClient([{
    data: [{
      id: "run-1",
      job_id: "job-1",
      job_title: "AI 工程师",
      created_by_name: "张小北",
      source: "upload",
      status: "completed",
      total_count: 5,
      processed_count: 5,
      succeeded_count: 4,
      failed_count: 1,
      review_total_count: 5,
      reviewed_count: 2,
      review_pending_count: 3,
      review_approved_count: 1,
      review_rejected_count: 0,
      review_status: "in_progress",
      created_at: "2026-07-17T08:00:00+00:00",
    }],
    meta: { limit: 50, next_cursor: null },
  }]);
  const controller = createScreeningController({ client });

  assert.deepEqual(await controller.listRuns(), [{
    id: "run-1",
    jobId: "job-1",
    position: "AI 工程师",
    creator: "张小北",
    source: "本地上传",
    status: "complete",
    completed: 5,
    total: 5,
    succeeded: 4,
    failed: 1,
    reviewTotal: 5,
    reviewed: 2,
    reviewPending: 3,
    reviewApproved: 1,
    reviewRejected: 0,
    reviewStatus: "in_progress",
    createdAt: "2026-07-17T08:00:00+00:00",
    serverBacked: true,
  }]);
  assert.equal(client.calls[0].path, "/api/v1/screening-runs?limit=50");
});

test("drops malformed job and item records without creating blank UI rows", async () => {
  const client = createClient([{ data: [null, { id: 7, title: "bad" }, { id: "", title: "blank" }, { id: "job-1", title: "AI 工程师" }] }]);
  const controller = createScreeningController({ client });

  assert.deepEqual(await controller.listJobs(), [{ id: "job-1", title: "AI 工程师" }]);

  const task = normalizeScreeningTask(run(), [null, { id: 7, filename: "bad.pdf" }, item({ id: "item-2", llm_status: "unknown", status: "scored", rule_result: { score: 80 } })]);
  assert.equal(task.files.length, 1);
  assert.equal(task.files[0].id, "item-2");
  assert.equal(task.files[0].status, "running");
});

test("creates, uploads, and starts with exact contracts and a new key per command", async () => {
  const client = createClient([
    { data: { id: "run-1" } },
    { data: { id: "item-1" } },
    { data: { id: "item-2" } },
    { data: { id: "run-1", status: "parsing" } },
  ]);
  let key = 0;
  const controller = createScreeningController({ client, createIdempotencyKey: () => `key-${++key}` });
  const first = new File(["first"], "first.pdf", { type: "application/pdf" });
  const second = new File(["second"], "second.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });

  await controller.createRun("job-1");
  await controller.uploadFiles("run-1", [first, second]);
  await controller.startRun("run-1");

  assert.equal(client.calls[0].path, "/api/v1/jobs/job-1/screening-runs");
  assert.deepEqual(client.calls[0].options.body, { source: "upload" });
  assert.equal(client.calls[0].options.idempotencyKey, "key-1");
  assert.equal(client.calls[1].path, "/api/v1/screening-runs/run-1/items");
  assert.equal(client.calls[1].options.body instanceof FormData, true);
  assert.equal(client.calls[1].options.body.get("file"), first);
  assert.equal(client.calls[2].options.body.get("file"), second);
  assert.equal(client.calls[1].options.headers, undefined);
  assert.deepEqual(client.calls.slice(1).map(({ options }) => options.idempotencyKey), ["key-2", "key-3", "key-4"]);
  assert.equal(client.calls[3].path, "/api/v1/screening-runs/run-1/start");
  assert.equal(new Set(client.calls.map(({ options }) => options.idempotencyKey)).size, 4);
});

test("accepts and preserves a cross-realm-like File object", async () => {
  const client = createClient([{ data: { id: "item-1" } }]);
  const controller = createScreeningController({ client, createIdempotencyKey: () => "upload-key" });
  const file = new File(["resume"], "resume.pdf", { type: "application/pdf" });
  const OriginalFormData = globalThis.FormData;
  let appended;
  Object.defineProperty(file, "name", { value: file.name });
  Object.setPrototypeOf(file, Object.create(Blob.prototype, {
    [Symbol.toStringTag]: { value: "File" },
  }));
  globalThis.FormData = class RecordingFormData {
    append(name, value) { appended = { name, value }; }
  };

  try {
    assert.equal(file instanceof File, false);
    await controller.uploadFiles("run-1", [file]);
  } finally {
    globalThis.FormData = OriginalFormData;
  }

  assert.equal(appended.name, "file");
  assert.equal(appended.value, file);
});

test("normalizes run states and server counts without timer-derived progress", () => {
  const cases = [
    ["queued", "running"],
    ["llm_scoring", "running"],
    ["completed", "complete"],
    ["partial", "partial"],
    ["failed", "failed"],
    ["cancelled", "cancelled"],
  ];

  for (const [serverStatus, expected] of cases) {
    const task = normalizeScreeningTask(run({ status: serverStatus, processed_count: 2, total_count: 9 }), []);
    assert.equal(task.status, expected);
    assert.equal(task.completed, 2);
    assert.equal(task.total, 9);
    assert.equal(task.id, "run-1");
    assert.equal(task.jobId, "job-1");
  }
});

test("keeps cancelled file items distinct from failures", () => {
  const task = normalizeScreeningTask(run({ status: "cancelled", processed_count: 1, total_count: 1 }), [
    item({ status: "cancelled", error_code: "cancelled" }),
  ]);

  assert.equal(task.status, "cancelled");
  assert.equal(task.files[0].status, "cancelled");
  assert.equal(task.files[0].error, "");
});

test("maps candidate, rule, LLM, risk, and application fields while retaining rule facts on LLM failure", () => {
  const task = normalizeScreeningTask(run({ status: "partial", processed_count: 1, total_count: 1 }), [item({
    status: "scored",
    llm_status: "failed",
    llm_error_code: "provider_rate_limited",
    candidate_id: "candidate-1",
    candidate_name: "林启舟",
    retryable: true,
    llm_retryable: true,
    application_stage: "screening",
    application_version: 4,
    rule_result: {
      score: 88,
      recommendation: "优先沟通",
      required_hits: ["Python"],
      bonus_hits: ["PostgreSQL"],
      required_missing: ["Kubernetes"],
      risks: ["需确认到岗时间"],
    },
  })]);

  assert.deepEqual(task.files[0], {
    id: "item-1",
    name: "resume.pdf",
    candidateId: "candidate-1",
    candidate: "林启舟",
    status: "partial",
    ruleScore: 88,
    llmScore: null,
    matched: "Python、PostgreSQL",
    missing: "Kubernetes",
    recommendation: "优先沟通",
    risk: "需确认到岗时间",
    error: "provider_rate_limited",
    application_stage: "screening",
    application_version: 4,
    humanReviewed: false,
    llmStatus: "failed",
    retryable: true,
    llmRetryable: true,
  });
});

test("marks rule failures failed and completed rule/LLM combinations successful", () => {
  const files = normalizeScreeningTask(run({ status: "completed", processed_count: 4, total_count: 4 }), [
    item({ id: "failed", status: "failed", error_code: "parse_failed" }),
    item({ id: "succeeded", status: "scored", llm_status: "succeeded", rule_result: { score: 80 }, llm_evaluation: { score: 76 } }),
    item({ id: "skipped", status: "scored", llm_status: "skipped", rule_result: { score: 70 } }),
    item({ id: "rules-only", status: "scored", llm_status: "not_requested", rule_result: { score: 60 } }),
  ]).files;

  assert.deepEqual(files.map(({ status }) => status), ["failed", "success", "success", "success"]);
  assert.equal(files[0].error, "parse_failed");
  assert.equal(files[1].ruleScore, 80);
  assert.equal(files[1].llmScore, 76);
  assert.equal(files[2].llmStatus, "skipped");
  assert.equal(files[3].llmStatus, "not_requested");
});

test("normalizes the server human-review marker on each screening result", () => {
  const [pending, reviewed] = normalizeScreeningTask(run({ status: "completed", processed_count: 2, total_count: 2 }), [
    item({ id: "pending", status: "scored", rule_result: { score: 80 }, human_reviewed: false, application_stage: "new" }),
    item({ id: "reviewed", status: "scored", rule_result: { score: 82 }, human_reviewed: true, application_stage: "review" }),
  ]).files;

  assert.equal(pending.humanReviewed, false);
  assert.equal(reviewed.humanReviewed, true);
});

test("malformed optional result fields normalize to safe null and empty display values", () => {
  const normalized = normalizeScreeningTask(run({ total_count: "bad", processed_count: null }), [item({
    candidate_name: { unsafe: true },
    rule_result: { score: "88", required_hits: "Python", risks: [{ unsafe: true }] },
    llm_evaluation: [],
    application_version: "4",
  })]);

  assert.equal(normalized.completed, 0);
  assert.equal(normalized.total, 0);
  assert.equal(normalized.files[0].candidate, "");
  assert.equal(normalized.files[0].ruleScore, null);
  assert.equal(normalized.files[0].llmScore, null);
  assert.equal(normalized.files[0].matched, "");
  assert.equal(normalized.files[0].risk, "");
  assert.equal(normalized.files[0].application_version, null);
});

test("polling fetches ordered snapshots immediately, waits between rounds, and stops terminally without overlap", async () => {
  const calls = [];
  const waits = [];
  let round = 0;
  let active = 0;
  let maxActive = 0;
  const client = { async request(path, options) {
    calls.push({ path, options });
    active += 1;
    maxActive = Math.max(maxActive, active);
    await Promise.resolve();
    active -= 1;
    if (path.endsWith("?limit=100")) return { data: [item({ status: round ? "scored" : "queued", rule_result: round ? { score: 81 } : null })] };
    const response = { data: run(round ? { status: "completed", processed_count: 1, total_count: 1 } : { status: "parsing", total_count: 1 }) };
    round += 1;
    return response;
  } };
  const controller = createScreeningController({ client, wait: async (ms) => waits.push(ms) });
  const snapshots = [];

  const result = await controller.pollRun("run-1", { intervalMs: 25, onSnapshot: (snapshot) => snapshots.push(snapshot) });

  assert.deepEqual(calls.map(({ path }) => path), [
    "/api/v1/screening-runs/run-1",
    "/api/v1/screening-runs/run-1/items?limit=100",
    "/api/v1/screening-runs/run-1",
    "/api/v1/screening-runs/run-1/items?limit=100",
  ]);
  assert.deepEqual(waits, [25]);
  assert.deepEqual(snapshots.map(({ status }) => status), ["running", "complete"]);
  assert.equal(result.status, "complete");
  assert.equal(maxActive, 1);
});

test("polling reads terminal items after the terminal run and emits that final item state", async () => {
  const terminalRun = deferred();
  const events = [];
  const client = { request(path) {
    if (path.endsWith("?limit=100")) {
      events.push("items-requested");
      return Promise.resolve({ data: [item({ status: "scored", rule_result: { score: 92 } })] });
    }
    events.push("run-requested");
    return terminalRun.promise.then((response) => {
      events.push("run-resolved");
      return response;
    });
  } };
  const controller = createScreeningController({ client });
  const snapshots = [];

  const polling = controller.pollRun("run-1", { onSnapshot: (snapshot) => snapshots.push(snapshot) });
  await Promise.resolve();
  assert.deepEqual(events, ["run-requested"]);

  terminalRun.resolve({ data: run({ status: "completed", processed_count: 1, total_count: 1 }) });
  const result = await polling;

  assert.deepEqual(events, ["run-requested", "run-resolved", "items-requested"]);
  assert.equal(result.status, "complete");
  assert.equal(result.files[0].status, "success");
  assert.deepEqual(snapshots, [result]);
});

test("polling aborts quietly without a stale partial-pair emission", async () => {
  const abortController = new AbortController();
  const client = { async request(path) {
    if (path.endsWith("?limit=100")) {
      abortController.abort();
      throw new DOMException("Aborted", "AbortError");
    }
    return { data: run({ status: "parsing" }) };
  } };
  const controller = createScreeningController({ client });
  const snapshots = [];

  const result = await controller.pollRun("run-1", { signal: abortController.signal, onSnapshot: (snapshot) => snapshots.push(snapshot) });

  assert.equal(result, null);
  assert.deepEqual(snapshots, []);
});

test("a newer poll for the same run suppresses all later emissions from the older poll and stops it", async () => {
  const responses = Array.from({ length: 3 }, deferred);
  let requestIndex = 0;
  const client = { request: () => responses[requestIndex++].promise };
  const controller = createScreeningController({ client });
  const olderSnapshots = [];
  const newerSnapshots = [];

  const olderPoll = controller.pollRun("run-1", { onSnapshot: (snapshot) => olderSnapshots.push(snapshot) });
  await Promise.resolve();
  const newerPoll = controller.pollRun("run-1", { onSnapshot: (snapshot) => newerSnapshots.push(snapshot) });

  responses[1].resolve({ data: run({ status: "completed", processed_count: 1, total_count: 1 }) });
  await Promise.resolve();
  responses[2].resolve({ data: [item({ status: "scored", rule_result: { score: 90 } })] });
  assert.equal((await newerPoll).status, "complete");

  responses[0].resolve({ data: run({ status: "completed", processed_count: 1, total_count: 1 }) });

  assert.equal(await olderPoll, null);
  assert.deepEqual(olderSnapshots, []);
  assert.equal(newerSnapshots.length, 1);
  assert.equal(requestIndex, 3);
});

test("polls for different runs remain independent", async () => {
  const snapshots = { first: [], second: [] };
  const client = { async request(path) {
    if (path.endsWith("?limit=100")) return { data: [item()] };
    const runId = path.split("/").at(-1);
    return { data: run({ id: runId, status: "completed" }) };
  } };
  const controller = createScreeningController({ client });

  const [first, second] = await Promise.all([
    controller.pollRun("run-1", { onSnapshot: (snapshot) => snapshots.first.push(snapshot) }),
    controller.pollRun("run-2", { onSnapshot: (snapshot) => snapshots.second.push(snapshot) }),
  ]);

  assert.equal(first.id, "run-1");
  assert.equal(second.id, "run-2");
  assert.deepEqual(snapshots.first.map(({ id }) => id), ["run-1"]);
  assert.deepEqual(snapshots.second.map(({ id }) => id), ["run-2"]);
});

test("polling forwards non-abort API errors", async () => {
  const expected = new Error("safe API error");
  const controller = createScreeningController({ client: { request: async () => { throw expected; } } });

  await assert.rejects(controller.pollRun("run-1", { onSnapshot() {} }), expected);
});

test("retry uses its endpoint and a fresh idempotency key each time", async () => {
  const client = createClient([{ data: { item: { id: "item-1" } } }, { data: { item: { id: "item-1" } } }]);
  let key = 0;
  const controller = createScreeningController({ client, createIdempotencyKey: () => `retry-${++key}` });

  await controller.retryItem("item-1");
  await controller.retryItem("item-1");

  assert.deepEqual(client.calls.map(({ path }) => path), ["/api/v1/screening-items/item-1/retry", "/api/v1/screening-items/item-1/retry"]);
  assert.deepEqual(client.calls.map(({ options }) => options.idempotencyKey), ["retry-1", "retry-2"]);
});

test("bulk advance posts selected item versions with a fresh key and abort signal", async () => {
  const signal = new AbortController().signal;
  const client = createClient([
    { data: { applied_count: 1, already_applied_count: 1, applications: [
      { item_id: "item/1", version: 4, result: "applied" },
      { item_id: "item-2", version: 8, result: "already_applied" },
      { item_id: "unsafe", version: "9", result: "applied" },
    ] } },
    { data: { applied_count: 0, already_applied_count: 2 } },
    { data: { applied_count: 1, already_applied_count: 0 } },
  ]);
  let key = 0;
  const controller = createScreeningController({ client, createIdempotencyKey: () => `bulk-${++key}` });
  const items = [
    { item_id: "item/1", expected_application_version: 3 },
    { item_id: "item-2", expected_application_version: 7 },
  ];

  assert.deepEqual(await controller.bulkAction("run/1", items, { signal }), {
    applied: 1,
    already_applied: 1,
    undo_items: [{ item_id: "item/1", expected_application_version: 4 }],
  });
  await controller.bulkAction("run/1", items, { signal });
  await controller.undoBulkAction("run/1", [{ item_id: "item/1", expected_application_version: 4 }], { signal });

  assert.deepEqual(client.calls, [
    {
      path: "/api/v1/screening-runs/run%2F1/bulk-actions",
      options: {
        method: "POST",
        body: { command: "advance_to_review", items },
        idempotencyKey: "bulk-1",
        signal,
      },
    },
    {
      path: "/api/v1/screening-runs/run%2F1/bulk-actions",
      options: {
        method: "POST",
        body: { command: "advance_to_review", items },
        idempotencyKey: "bulk-2",
        signal,
      },
    },
    {
      path: "/api/v1/screening-runs/run%2F1/bulk-actions",
      options: {
        method: "POST",
        body: { command: "undo_advance_to_new", items: [{ item_id: "item/1", expected_application_version: 4 }] },
        idempotencyKey: "bulk-3",
        signal,
      },
    },
  ]);
});
