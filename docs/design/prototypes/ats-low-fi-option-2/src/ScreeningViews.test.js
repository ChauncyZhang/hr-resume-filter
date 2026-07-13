import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let helpers;
let vite;

before(async () => {
  vite = await createServer({
    root: process.cwd(),
    logLevel: "silent",
    server: { middlewareMode: true },
    appType: "custom",
  });
  helpers = await vite.ssrLoadModule("/src/ScreeningViews.jsx");
});

after(async () => {
  await vite?.close();
});

test("target job is preselected only when its title has one exact match", () => {
  const jobs = [
    { id: "job-ai-001", title: "AI 工程师" },
    { id: "job-ai-002", title: "AI 工程师" },
    { id: "job-fe-001", title: "前端工程师" },
  ];

  assert.equal(helpers.resolveInitialJobId(jobs, "前端工程师"), "job-fe-001");
  assert.equal(helpers.resolveInitialJobId(jobs, "AI 工程师"), "");
  assert.equal(helpers.resolveInitialJobId(jobs, "不存在的职位"), "");
});

test("duplicate job titles include a short id while unique titles stay concise", () => {
  const jobs = [
    { id: "job-ai-0001", title: "AI 工程师" },
    { id: "job-ai-0002", title: "AI 工程师" },
    { id: "job-fe-0001", title: "前端工程师" },
  ];

  assert.equal(helpers.jobOptionLabel(jobs[0], jobs), "AI 工程师（ID: job-…0001）");
  assert.equal(helpers.jobOptionLabel(jobs[1], jobs), "AI 工程师（ID: job-…0002）");
  assert.equal(helpers.jobOptionLabel(jobs[2], jobs), "前端工程师");
});

test("format examples can never advance into the real task flow", () => {
  assert.equal(helpers.canAdvanceFromFiles([{ valid: true, sourceFile: {} }]), true);
  assert.equal(helpers.canAdvanceFromFiles([{ valid: true, sourceFile: {}, example: true }]), false);
  assert.equal(helpers.canAdvanceFromFiles([{ valid: false, sourceFile: {} }]), false);
});

test("server candidate labels never present a derived name as verified", () => {
  assert.equal(helpers.candidateDisplayName({ candidate: "张三" }, true), "张三（待核验）");
  assert.equal(helpers.candidateDisplayName({ candidate: "" }, true), "候选人姓名待核验");
  assert.equal(helpers.candidateDisplayName({ candidate: "张三" }, false), "张三");
});

test("server LLM partial failure preserves rule-result wording without promising retry", () => {
  const message = helpers.serverIssueMessage({ status: "partial", error: "LLM_PROVIDER_UNAVAILABLE" });

  assert.match(message, /规则结果已保留/);
  assert.match(message, /当前没有可用的 LLM 重试操作/);
  assert.doesNotMatch(message, /请重试|稍后重试/);
});

test("server LLM retry is offered only when the backend marks it retryable", () => {
  assert.match(helpers.serverIssueMessage({ status: "partial", llmRetryable: true }), /可使用下方“重试 LLM”/);
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1"], [
    { id: "item-1", status: "partial", llmRetryable: true },
  ]), ["item-1"]);
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1"], [
    { id: "item-1", status: "partial", llmRetryable: false },
  ]), []);
});

test("server task metadata is explicitly labeled as a local record", () => {
  const line = helpers.taskMetadataLine({ id: "run-1", source: "BOSS 直聘", creator: "张小北", createdAt: "刚刚", serverBacked: true });

  assert.match(line, /来源备注（本机）/);
  assert.match(line, /发起人记录（本机）/);
});

test("only completed server rows with a new positive-version application can advance", () => {
  const eligible = { status: "success", application_stage: "new", application_version: 2 };

  assert.equal(helpers.isAdvanceSelectable(eligible, true), true);
  assert.equal(helpers.isAdvanceSelectable({ ...eligible, status: "partial" }, true), true);
  assert.equal(helpers.isAdvanceSelectable({ ...eligible, status: "failed" }, true), false);
  assert.equal(helpers.isAdvanceSelectable({ ...eligible, application_stage: "review" }, true), false);
  assert.equal(helpers.isAdvanceSelectable({ ...eligible, application_version: 0 }, true), false);
  assert.equal(helpers.isAdvanceSelectable({ ...eligible, application_version: 1.5 }, true), false);
  assert.equal(helpers.isAdvanceSelectable(eligible, false), false);
});

test("advance payload and success notice use only selected server data", () => {
  const files = [
    { id: "item-1", status: "success", application_stage: "new", application_version: 3 },
    { id: "item-2", status: "partial", application_stage: "new", application_version: 4 },
    { id: "item-3", status: "success", application_stage: "review", application_version: 5 },
  ];

  assert.deepEqual(helpers.advanceItems(files, ["item-1", "item-2", "item-3"]), [
    { item_id: "item-1", expected_application_version: 3 },
    { item_id: "item-2", expected_application_version: 4 },
  ]);
  assert.equal(helpers.advanceSuccessMessage({ applied: 2, already_applied: 1 }), "已推进 3 位候选人到待复核（新推进 2 位，已在待复核 1 位）");
});

test("bulk failures expose safe messages without echoing server details", () => {
  const conflict = Object.assign(new Error("candidate alice@example.com version 8"), { status: 409 });
  const failure = new Error("database host internal.example failed");

  assert.equal(helpers.advanceErrorMessage(conflict), "推进未完成，候选人状态可能已变化；正在刷新服务端结果，请重新选择。");
  assert.equal(helpers.advanceErrorMessage(failure), "推进失败，请稍后重试。");
  assert.doesNotMatch(helpers.advanceErrorMessage(conflict), /alice|version|8/);
  assert.doesNotMatch(helpers.advanceErrorMessage(failure), /database|internal/);
});

test("cancelled tasks never describe progress as completed", () => {
  assert.equal(helpers.statusLabel("cancelled"), "已取消");
  assert.equal(helpers.progressSummary({ status: "cancelled", completed: 2, total: 5 }), "任务已取消：已处理 2/5 份简历");
  assert.equal(helpers.progressSummary({ status: "complete", completed: 5, total: 5 }), "处理完成：5/5 份简历");
});

test("server retry stays locked while the refreshed row remains failed and retryable", () => {
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1", "missing"], [
    { id: "item-1", status: "failed", retryable: true },
  ]), ["item-1"]);
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1"], [
    { id: "item-1", status: "running", retryable: false },
  ]), []);
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1"], [
    { id: "item-1", status: "failed", retryable: false },
  ]), []);
});
