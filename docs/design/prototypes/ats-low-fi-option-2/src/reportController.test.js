import test from "node:test";
import assert from "node:assert/strict";

import { createReportController, normalizeReportData } from "./reportController.js";


test("report normalization maps server stages and rates without fixture-derived metrics", () => {
  const report = normalizeReportData({
    funnel: {
      total_applications: 4,
      stages: [
        { stage: "new", current_count: 2, average_time_in_stage_seconds: 86400 },
        { stage: "interviewing", current_count: 1, average_time_in_stage_seconds: 129600 },
        { stage: "rejected", current_count: 1, average_time_in_stage_seconds: 3600 },
      ],
      interviews: {
        count: 3,
        required_feedback_completed: 2,
        required_feedback_total: 3,
        required_feedback_completion_rate: 0.666667,
        average_feedback_turnaround_seconds: 5400,
      },
    },
    quality: {
      resume_parsing: { succeeded: 8, total: 10, success_rate: 0.8 },
      rule_screening: { passed: 5, total: 8, pass_rate: 0.625 },
      llm: { succeeded: 3, total: 4, success_rate: 0.75 },
    },
  });

  assert.equal(report.totalApplications, 4);
  assert.deepEqual(report.stages.map((item) => [item.stage, item.currentCount, item.averageDays]), [
    ["新简历", 2, 1],
    ["面试中", 1, 1.5],
    ["已淘汰", 1, 0],
  ]);
  assert.equal(report.interviews.feedbackCompletionRate, 66.7);
  assert.equal(report.interviews.averageFeedbackHours, 1.5);
  assert.equal(report.quality.parseSuccessRate, 80);
  assert.equal(report.quality.rulePassRate, 62.5);
  assert.equal(report.quality.llmSuccessRate, 75);
});


test("report controller loads both authorized report projections with identical filters", async () => {
  const calls = [];
  const client = { async request(path, options) {
    calls.push({ path, options });
    if (path.startsWith("/api/v1/reports/recruiting-funnel")) return { data: { total_applications: 0, stages: [], interviews: {} } };
    if (path.startsWith("/api/v1/reports/screening-quality")) return { data: {} };
    throw new Error(`unexpected request ${path}`);
  } };
  const signal = new AbortController().signal;
  const controller = createReportController({ client });

  const report = await controller.load({ jobId: "job-1", from: "2026-07-01T00:00:00.000Z", to: "2026-07-31T23:59:59.999Z" }, { signal });

  assert.equal(report.totalApplications, 0);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].path, "/api/v1/reports/recruiting-funnel?job_id=job-1&from=2026-07-01T00%3A00%3A00.000Z&to=2026-07-31T23%3A59%3A59.999Z");
  assert.equal(calls[1].path, "/api/v1/reports/screening-quality?job_id=job-1&from=2026-07-01T00%3A00%3A00.000Z&to=2026-07-31T23%3A59%3A59.999Z");
  assert.equal(calls[0].options.signal, signal);
  assert.equal(calls[1].options.signal, signal);
});


test("export controller creates, checks, and downloads through a one-time ticket", async () => {
  const calls = [];
  const client = {
    async request(path, options = {}) {
      calls.push({ type: "request", path, options });
      if (path === "/api/v1/exports") return { data: { id: "export-1", status: "queued", format: "csv", row_count: 0 } };
      if (path === "/api/v1/exports/export-1") return { data: { id: "export-1", status: "succeeded", format: "csv", row_count: 7 } };
      if (path === "/api/v1/exports/export-1/download-tickets") return { data: { token: "opaque-download-token", expires_in: 60 } };
      throw new Error(`unexpected request ${path}`);
    },
    async download(path, options = {}) {
      calls.push({ type: "download", path, options });
      return { blob: new Blob(["candidate_id\n1\n"], { type: "text/csv" }), filename: "report.csv" };
    },
  };
  const controller = createReportController({ client, idSource: () => "export-idempotency" });

  const created = await controller.createExport({ jobId: "job-1" });
  const ready = await controller.getExport(created.id);
  const file = await controller.downloadExport(ready.id);

  assert.equal(created.status, "queued");
  assert.equal(ready.rowCount, 7);
  assert.equal(file.filename, "report.csv");
  assert.equal(calls[0].options.idempotencyKey, "export-idempotency");
  assert.deepEqual(calls[0].options.body, { job_id: "job-1", from: null, to: null });
  assert.equal(calls[2].options.method, "POST");
  assert.deepEqual(calls[3].options.body, { token: "opaque-download-token" });
});


test("export controller supplies safe defaults and polls until the export succeeds", async () => {
  let checks = 0;
  const client = { async request(path) {
    assert.equal(path, "/api/v1/exports/export-2");
    checks += 1;
    if (checks <= 2) return { data: { id: "export-2" } };
    return { data: { id: "export-2", status: "succeeded", format: "csv", row_count: 2 } };
  } };
  const controller = createReportController({ client });
  const delays = [];

  const pending = await controller.getExport("export-2");
  assert.equal(pending.status, "queued");
  assert.equal(pending.format, "csv");

  const ready = await controller.waitForExport("export-2", {
    delay: async (milliseconds) => delays.push(milliseconds),
    intervalMs: 25,
    maxAttempts: 3,
  });

  assert.equal(checks, 3);
  assert.deepEqual(delays, [25]);
  assert.equal(ready.status, "succeeded");
  assert.equal(ready.format, "csv");
});
