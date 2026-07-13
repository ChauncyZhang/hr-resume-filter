import assert from "node:assert/strict";
import test from "node:test";
import {
  createScreeningWorkflow,
  mergeServerTaskMetadata,
  parseRecentScreeningTask,
  pollServerTask,
  serializeRecentScreeningTask,
} from "./screeningIntegration.js";

const metadata = {
  position: "AI 工程师",
  source: "本地上传",
  note: "校招批次",
  llmEnabled: true,
  creator: "张小北",
  createdAt: "刚刚",
};

test("recent task persistence keeps only safe server metadata", () => {
  const raw = serializeRecentScreeningTask({
    id: "run-1",
    jobId: "job-1",
    serverBacked: true,
    ...metadata,
    files: [{ id: "item-1", candidate: "敏感姓名" }],
    token: "secret",
  });

  assert.deepEqual(JSON.parse(raw), {
    id: "run-1",
    jobId: "job-1",
    serverBacked: true,
    ...metadata,
  });
  assert.deepEqual(parseRecentScreeningTask(raw), JSON.parse(raw));
  assert.equal(parseRecentScreeningTask(JSON.stringify({ ...JSON.parse(raw), files: [] })), null);
  assert.equal(parseRecentScreeningTask("not-json"), null);
  assert.equal(parseRecentScreeningTask(JSON.stringify({ id: "run-1", serverBacked: true })), null);
});

test("workflow creates once, uploads real files sequentially, tolerates partial failures, and reports progress", async () => {
  const first = new File(["first"], "first.pdf", { type: "application/pdf" });
  const second = new File(["second"], "second.pdf", { type: "application/pdf" });
  const calls = [];
  const progress = [];
  const controller = {
    async createRun(jobId) { calls.push(["create", jobId]); return { id: "run-1" }; },
    async uploadFiles(runId, files) {
      calls.push(["upload", runId, files[0]]);
      if (files[0] === first) throw new Error("upload failed");
      return [{ id: "item-2" }];
    },
    async startRun(runId) { calls.push(["start", runId]); },
    async getRun() { return { id: "run-1", job_id: "job-1", status: "running", processed_count: 0, total_count: 1 }; },
    async getItems() { return [{ id: "item-2", filename: "second.pdf", status: "queued" }]; },
  };

  const workflow = createScreeningWorkflow(controller);
  const result = await workflow.submit({ jobId: "job-1", files: [first, second], metadata, onProgress: (value) => progress.push(value) });

  assert.equal(calls.filter(([type]) => type === "create").length, 1);
  assert.deepEqual(calls.map(([type]) => type), ["create", "upload", "upload", "start"]);
  assert.equal(calls[1][2], first);
  assert.equal(calls[2][2], second);
  assert.deepEqual(progress, [{ completed: 0, total: 2 }, { completed: 1, total: 2 }, { completed: 2, total: 2 }]);
  assert.equal(result.failedCount, 1);
  assert.equal(result.task.id, "run-1");
  assert.equal(result.task.serverBacked, true);
  assert.equal(result.task.files[0].id, "item-2");
});

test("workflow does not start when every upload fails", async () => {
  let starts = 0;
  const controller = {
    async createRun() { return { id: "run-2" }; },
    async uploadFiles() { throw new Error("upload failed"); },
    async startRun() { starts += 1; },
  };
  const workflow = createScreeningWorkflow(controller);

  await assert.rejects(
    workflow.submit({ jobId: "job-1", files: [new File(["x"], "x.pdf")], metadata }),
    (error) => error?.code === "ALL_UPLOADS_FAILED",
  );
  assert.equal(starts, 0);
});

test("workflow exposes deterministic in-flight state and rejects duplicate submission", async () => {
  let release;
  const controller = {
    createRun: () => new Promise((resolve) => { release = resolve; }),
  };
  const workflow = createScreeningWorkflow(controller);
  const first = workflow.submit({ jobId: "job-1", files: [new File(["x"], "x.pdf")], metadata });

  assert.equal(workflow.isSubmitting(), true);
  await assert.rejects(
    workflow.submit({ jobId: "job-1", files: [new File(["y"], "y.pdf")], metadata }),
    (error) => error?.code === "SUBMISSION_IN_PROGRESS",
  );
  release({ id: "run-3" });
  await assert.rejects(first);
  assert.equal(workflow.isSubmitting(), false);
});

test("server snapshots retain authoritative fields and merge only allowed UI metadata", () => {
  const snapshot = { id: "server-run", jobId: "server-job", status: "running", completed: 2, total: 3, files: [{ id: "server-item" }], source: "server" };
  const merged = mergeServerTaskMetadata(snapshot, { ...metadata, id: "fake", jobId: "fake", files: [], completed: 99, status: "complete", unsafe: "no" });

  assert.deepEqual(merged, { ...snapshot, ...metadata, serverBacked: true });
  assert.equal("unsafe" in merged, false);
});

test("abort stops upload workflow quietly and never starts the run", async () => {
  const abortController = new AbortController();
  let starts = 0;
  const controller = {
    async createRun() { return { id: "run-4" }; },
    async uploadFiles() { abortController.abort(); throw new DOMException("Aborted", "AbortError"); },
    async startRun() { starts += 1; },
  };
  const workflow = createScreeningWorkflow(controller);

  const result = await workflow.submit({ jobId: "job-1", files: [new File(["x"], "x.pdf")], metadata, signal: abortController.signal });
  assert.equal(result, null);
  assert.equal(starts, 0);
});

test("server polling merges metadata, retries through the controller, and synthetic tasks stay local", async () => {
  const snapshots = [];
  let retries = 0;
  let polls = 0;
  const controller = {
    async pollRun(id, { onSnapshot }) {
      polls += 1;
      onSnapshot({ id, jobId: "job-1", status: "running", completed: 1, total: 2, files: [] });
      return null;
    },
    async retryItem(id) { retries += id === "item-1" ? 1 : 0; },
  };

  const lifecycle = pollServerTask({ task: { id: "run-5", jobId: "job-1", serverBacked: true, ...metadata }, controller, onTaskChange: (task) => snapshots.push(task) });
  await lifecycle.done;
  assert.equal(await lifecycle.retry("item-1"), true);
  assert.equal(polls, 2);
  assert.equal(retries, 1);
  assert.equal(snapshots[0].serverBacked, true);
  assert.equal(snapshots[0].position, metadata.position);

  const synthetic = pollServerTask({ task: { id: "fixture", serverBacked: false }, controller, onTaskChange() {} });
  await synthetic.done;
  await synthetic.retry("item-1");
  assert.equal(polls, 2);
  assert.equal(retries, 1);
});
