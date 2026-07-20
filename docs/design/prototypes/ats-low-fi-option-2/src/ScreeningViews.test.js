import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, before, test } from "node:test";
import { createServer } from "vite";

let helpers;
let candidateHelpers;
let vite;

before(async () => {
  vite = await createServer({
    root: process.cwd(),
    logLevel: "silent",
    server: { middlewareMode: true },
    appType: "custom",
  });
  helpers = await vite.ssrLoadModule("/src/ScreeningViews.jsx");
  candidateHelpers = await vite.ssrLoadModule("/src/CandidateViews.jsx");
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
  assert.equal(helpers.candidateDisplayName({ candidate: "张三" }, true), "张三（姓名待核验）");
  assert.equal(helpers.candidateDisplayName({ candidate: "" }, true), "候选人姓名待核验");
  assert.equal(helpers.candidateDisplayName({ candidate: "张三" }, false), "张三");
});

test("screening keeps a single-file LLM retry only when the server marks it retryable", () => {
  assert.deepEqual(helpers.screeningRetryAction({ status: "partial", llmRetryable: true }), { kind: "llm", label: "重试 LLM" });
  assert.equal(helpers.screeningRetryAction({ status: "partial", llmRetryable: false }), null);
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1"], [
    { id: "item-1", status: "partial", llmRetryable: true },
  ]), ["item-1"]);
  assert.deepEqual(helpers.reconcileRetryingIds(["item-1"], [
    { id: "item-1", status: "partial", llmRetryable: false },
  ]), []);
});

test("screening keeps a single-file parser retry only for retryable file failures", () => {
  assert.deepEqual(helpers.screeningRetryAction({ status: "failed", retryable: true }), { kind: "parse", label: "重新解析" });
  assert.equal(helpers.screeningRetryAction({ status: "failed", retryable: false }), null);
  assert.equal(helpers.screeningRetryAction({ status: "success", retryable: true }), null);
});

test("server task metadata uses persisted source and creator context", () => {
  const line = helpers.taskMetadataLine({ id: "run-1", source: "BOSS 直聘", creator: "张小北", createdAt: "刚刚", serverBacked: true });

  assert.match(line, /来源 BOSS 直聘/);
  assert.match(line, /发起人 张小北/);
});

test("screening task status ends with automatic processing instead of a review phase", () => {
  assert.equal(helpers.taskLifecycleLabel({ status: "running", reviewTotal: 5, reviewed: 0 }), "处理中");
  assert.equal(helpers.taskLifecycleLabel({ status: "complete", reviewTotal: 5, reviewed: 0 }), "已完成");
  assert.equal(helpers.taskLifecycleLabel({ status: "complete", reviewTotal: 5, reviewed: 2 }), "已完成");
});

test("screening renders the controller automatic outcome instead of the historical rule score", () => {
  assert.deepEqual(helpers.screeningDisplayOutcome({
    ruleScore: 12,
    score: 72,
    recommendation: "建议评审",
    routeResult: "review",
    routeLabel: "已转交用人经理",
  }), { score: 72, recommendation: "建议评审", routeLabel: "已转交用人经理" });
  assert.equal(helpers.screeningRouteLabel({ routeResult: "review" }), "已转交用人经理");
  assert.equal(helpers.screeningRouteLabel({ routeResult: "deferred" }), "已暂缓");
});

test("screening final AI failure stays neutral and retains manager handoff", () => {
  assert.deepEqual(helpers.screeningDisplayOutcome({
    status: "partial",
    score: null,
    recommendation: "AI评分不可用",
    routeResult: "review",
    routeLabel: "已转交用人经理",
  }), { score: null, recommendation: "AI评分不可用", routeLabel: "已转交用人经理" });
  assert.doesNotMatch(JSON.stringify(helpers.screeningDisplayOutcome({ status: "failed", score: null })), /候选人失败/);
});

test("screening dimensions render five valid scores and malformed optional data degrades safely", () => {
  const dimensions = ["岗位匹配", "技能经验", "项目深度", "成长潜力", "稳定性"].map((label, index) => ({
    label,
    score: 80 - index,
    evidence: [`证据 ${index + 1}`],
    gaps: index === 0 ? [] : [`缺口 ${index}`],
  }));

  assert.deepEqual(helpers.normalizeScreeningDimensions(dimensions).map(({ label, score }) => ({ label, score })), dimensions.map(({ label, score }) => ({ label, score })));
  assert.deepEqual(helpers.normalizeScreeningDimensions([null, { label: "技能经验", score: "bad", evidence: "错误", gaps: 7 }]), [
    { label: "技能经验", score: null, evidence: [], gaps: [] },
  ]);
  assert.deepEqual(helpers.normalizeScreeningDimensions("bad"), []);
});

test("screening summary uses the four server counters without recomputing rows", () => {
  assert.deepEqual(helpers.screeningSummaryCounts({
    serverCounts: { managerHandoff: 8, deferred: 3, aiUnavailable: 2, fileFailed: 1 },
    files: [{ routeResult: "deferred", status: "failed" }],
  }), [
    { label: "已转交用人经理", value: 8 },
    { label: "已暂缓", value: 3 },
    { label: "AI评分不可用", value: 2 },
    { label: "文件处理失败", value: 1 },
  ]);
});

test("screening source has the eight automatic columns and no removed manual path", () => {
  const source = readFileSync(new URL("./ScreeningViews.jsx", import.meta.url), "utf8");
  for (const heading of ["流转结果", "候选人/文件", "处理状态", "LLM结论", "最终分", "维度评分", "主要优势与风险", "查看候选人"]) assert.match(source, new RegExp(heading));
  const removed = ["待" + "HR审核", "HR初筛" + "进度", "待提交" + "用人经理", "advance" + "_to_review"];
  for (const text of removed) assert.equal(source.includes(text), false);
});

test("cancelled tasks never describe progress as completed", () => {
  assert.equal(helpers.statusLabel("cancelled"), "已取消");
  assert.equal(helpers.progressSummary({ status: "cancelled", completed: 2, total: 5 }), "任务已取消：已处理 2/5 份简历");
  assert.equal(helpers.progressSummary({ status: "complete", completed: 5, total: 5 }), "处理完成：5/5 份简历");
});

test("an interrupted empty upload offers abandonment instead of an ineffective retry", () => {
  assert.deepEqual(helpers.pollFailureAction({ code: "RECOVERED_RUN_EMPTY" }), {
    code: "RECOVERED_RUN_EMPTY",
    message: "该任务在上传前中断，没有可恢复的简历。可放弃此任务后重新导入。",
    action: "cancel",
    label: "放弃任务",
  });
  assert.equal(helpers.pollFailureAction(new Error("network")).action, "retry");
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

test("server result opens review only from a completed row with a candidate id", () => {
  assert.equal(helpers.canOpenCandidateReview({ status: "success", candidateId: "candidate-1" }, true), true);
  assert.equal(helpers.canOpenCandidateReview({ status: "partial", candidateId: "candidate-2" }, true), true);
  assert.equal(helpers.canOpenCandidateReview({ status: "failed", candidateId: "candidate-3" }, true), false);
  assert.equal(helpers.canOpenCandidateReview({ status: "success", candidateId: "" }, true), false);
  assert.equal(helpers.canOpenCandidateReview({ status: "success", candidate: "同名候选人" }, true), false);
  assert.equal(helpers.canOpenCandidateReview({ status: "success" }, false), true);
});

test("server candidate context keeps identity separate from automatic screening fields", () => {
  const context = helpers.candidateReviewContext({
    candidateId: "candidate-1", candidate: "未核验姓名", email: "derived@example.com",
    score: 78, recommendation: "建议评审", routeResult: "review", routeLabel: "已转交用人经理",
    dimensions: [{ label: "技能经验", score: 82, evidence: ["Python"], gaps: ["Kubernetes"] }], strengths: ["经验匹配"], risks: ["规模待确认"],
  }, { jobId: "job-1", position: "AI 工程师" });

  assert.deepEqual(context, {
    candidateId: "candidate-1",
    jobId: "job-1",
    position: "AI 工程师",
    evidence: {
      score: 78,
      recommendation: "建议评审",
      routeResult: "review",
      routeLabel: "已转交用人经理",
      dimensions: [{ label: "技能经验", score: 82, evidence: ["Python"], gaps: ["Kubernetes"] }],
      strengths: ["经验匹配"],
      risks: ["规模待确认"],
    },
  });
  assert.equal("email" in context, false);
  assert.equal("candidate" in context, false);
});

test("screening view context restores filters without row selection state", () => {
  assert.equal(typeof helpers.restoreScreeningViewState, "function");
  assert.deepEqual(helpers.restoreScreeningViewState({
    taskId: "task-1",
    query: "zhang",
    filter: "成功",
  }, {
    id: "task-1",
    serverBacked: true,
    files: [
      { id: "candidate-1", status: "success", application_stage: "new", application_version: 3 },
      { id: "candidate-2", status: "success", application_stage: "review", application_version: 4 },
    ],
  }), {
    query: "zhang",
    filter: "成功",
  });
});

test("server candidate detail exposes the connected interview path and reports conflicts safely", () => {
  assert.deepEqual(candidateHelpers.candidateDetailTabs(true), ["档案与简历", "职位申请", "筛选证据", "面试与反馈", "时间线"]);
  assert.match(candidateHelpers.candidateMutationError({ status: 409 }), /其他成员更新/);
  assert.doesNotMatch(candidateHelpers.candidateMutationError(new Error("database internal.example")), /database|internal/);
  assert.equal(candidateHelpers.resumeDisplayName({ original_filename: "真实简历.pdf" }), "真实简历.pdf");
  assert.equal(candidateHelpers.resumeDisplayName(null), "暂无可用简历");
  assert.deepEqual(candidateHelpers.candidateStageFilterOptions(), ["新简历", "待复核", "待沟通", "待安排", "面试中", "待决策", "已通过", "已录用", "已淘汰", "已撤回"]);
  assert.deepEqual(candidateHelpers.candidateWorkflowActions("待决策", "用人经理").map((item) => item.id), ["hiring_approved", "hiring_rejected"]);
  assert.deepEqual(candidateHelpers.candidateWorkflowActions("待安排", "HR 招聘专员"), []);
  assert.equal(candidateHelpers.candidateNextStep("面试中"), "等待面试官提交反馈");
  assert.equal(candidateHelpers.canScheduleCandidateInterview("待安排", "HR 招聘专员", true), true);
  assert.equal(candidateHelpers.canScheduleCandidateInterview("待复核", "HR 招聘专员", true), false);
  assert.equal(candidateHelpers.canScheduleCandidateInterview("待安排", "用人经理", true), false);
});
