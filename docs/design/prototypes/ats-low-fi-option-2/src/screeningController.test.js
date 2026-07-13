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

test("lists job options from GET /jobs with only id and title", async () => {
  const client = createClient([{ data: [{ id: "job-1", title: "AI 工程师", status: "open" }] }]);
  const controller = createScreeningController({ client });

  assert.deepEqual(await controller.listJobs(), [{ id: "job-1", title: "AI 工程师" }]);
  assert.equal(client.calls[0].path, "/api/v1/jobs?limit=100");
  assert.deepEqual(client.calls[0].options, {});
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

test("maps candidate, rule, LLM, risk, and application fields while retaining rule facts on LLM failure", () => {
  const task = normalizeScreeningTask(run({ status: "partial", processed_count: 1, total_count: 1 }), [item({
    status: "scored",
    llm_status: "failed",
    llm_error_code: "provider_rate_limited",
    candidate_name: "林启舟",
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

test("polling fetches paired snapshots immediately, waits between rounds, and stops terminally without overlap", async () => {
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
  assert.equal(maxActive, 2);
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
