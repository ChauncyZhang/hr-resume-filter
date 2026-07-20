const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = new URL(process.env.UX08_URL || "http://127.0.0.1:4174/");
const evidenceDir = path.resolve(process.env.UX08_EVIDENCE_DIR || path.join(__dirname, "../ux-08-evidence"));
const results = [];

const ids = Object.freeze({
  run: "run-llm-only-audit",
  job: "job-llm-platform",
  reviewCandidate: "candidate-score-60",
  reviewApplication: "application-score-60",
  failedCandidate: "candidate-ai-unavailable",
  failedApplication: "application-ai-unavailable",
  deferredCandidate: "candidate-score-59",
  deferredApplication: "application-score-59",
  deferredPool: "pool-ai-screening-deferred",
  deferredMembership: "membership-score-59",
});

function record(id, status, detail = "") {
  results.push({ id, status, detail });
  process.stdout.write(`${status === "passed" ? "PASS" : "FAIL"} ${id}${detail ? `: ${detail}` : ""}\n`);
}

async function runCase(page, id, fn) {
  try {
    await fn();
    record(id, "passed");
  } catch (error) {
    const filename = `task8-failure-${id.replace(/[^a-z0-9-]+/gi, "-")}.png`;
    await page.screenshot({ path: path.join(evidenceDir, filename), fullPage: true }).catch(() => {});
    record(id, "failed", `${error.message}; screenshot=${filename}`);
    throw error;
  }
}

async function assertVisible(locator, description) {
  try {
    await locator.first().waitFor({ state: "visible", timeout: 8_000 });
  } catch {
    throw new Error(`${description}不可见`);
  }
}

async function assertTextAbsent(locator, pattern, description) {
  const text = await locator.innerText();
  assert.doesNotMatch(text, pattern, description);
}

async function assertNoBodyOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  assert.ok(
    dimensions.document <= dimensions.viewport + 1 && dimensions.body <= dimensions.viewport + 1,
    `${label}横向溢出 ${JSON.stringify(dimensions)}`,
  );
}

async function assertRendered(page, label) {
  await assertVisible(page.locator("main"), `${label}主内容`);
  const state = await page.locator("main").evaluate((element) => ({
    textLength: element.innerText.trim().length,
    width: element.getBoundingClientRect().width,
    height: element.getBoundingClientRect().height,
  }));
  assert.ok(state.textLength > 20 && state.width > 0 && state.height > 0, `${label}疑似白屏 ${JSON.stringify(state)}`);
}

async function screenshot(page, filename) {
  await page.screenshot({ path: path.join(evidenceDir, filename), fullPage: true });
}

function dimensionsFor(score) {
  const limits = [
    ["core_capability", 35, "核心能力证据"],
    ["experience_depth", 25, "经验深度证据"],
    ["role_seniority", 20, "职级证据"],
    ["transferability", 10, "迁移能力证据"],
    ["explicit_constraints", 10, "明确约束证据"],
  ];
  let remaining = score;
  return limits.map(([key, limit, evidence]) => {
    const value = Math.min(remaining, limit);
    remaining -= value;
    return {
      key,
      score: value,
      evidence: value ? [evidence] : [],
      gaps: value === limit ? [] : [`${key}仍需核验`],
    };
  });
}

function screeningEvaluation(score, recommendation) {
  return {
    score,
    recommendation,
    summary: score >= 60 ? "达到用人经理评审边界。" : "当前匹配度不足，进入暂缓人才池。",
    dimensions: dimensionsFor(score),
    evidence: ["合成简历中的可验证项目经历"],
    gaps: score >= 60 ? ["到岗时间待确认"] : ["系统设计深度不足", "缺少带队经验"],
    strengths: ["具备可迁移的平台研发经验"],
    risks: score >= 60 ? ["项目规模待确认"] : ["岗位级别匹配不足"],
    questions: ["请说明最近项目中的职责边界"],
  };
}

function screeningRun() {
  return {
    id: ids.run,
    job_id: ids.job,
    job_title: "LLM 平台工程师",
    created_by_name: "合成验收账号",
    source: "upload",
    status: "partial",
    processed_count: 4,
    total_count: 4,
    succeeded_count: 3,
    failed_count: 1,
    manager_review_count: 2,
    deferred_count: 1,
    ai_unavailable_count: 1,
    file_failed_count: 1,
    created_at: "2026-07-20T06:00:00Z",
  };
}

function screeningItems() {
  return [
    {
      id: "item-score-60",
      filename: "score-60-review.pdf",
      candidate_id: ids.reviewCandidate,
      candidate_name: "林界（60分）",
      status: "scored",
      route_result: "review",
      llm_status: "succeeded",
      ai_score: 60,
      ai_recommendation: "建议评审",
      llm_evaluation: screeningEvaluation(60, "建议评审"),
      rule_score: 99,
      rule_recommendation: "规则强制通过（旧数据，不得展示）",
    },
    {
      id: "item-score-59",
      filename: "score-59-deferred.pdf",
      candidate_id: ids.deferredCandidate,
      candidate_name: "韩松（59分）",
      status: "scored",
      route_result: "deferred",
      llm_status: "succeeded",
      ai_score: 59,
      ai_recommendation: "暂缓",
      llm_evaluation: screeningEvaluation(59, "暂缓"),
      rule_score: 100,
      rule_recommendation: "规则强制通过（旧数据，不得展示）",
    },
    {
      id: "item-ai-unavailable",
      filename: "provider-final-failure.pdf",
      candidate_id: ids.failedCandidate,
      candidate_name: "周旻（AI不可用）",
      status: "scored",
      route_result: "review",
      llm_status: "failed",
      llm_error_code: "provider_unavailable",
      ai_score: null,
      ai_recommendation: null,
      llm_evaluation: {
        score: 92,
        recommendation: "陈旧模型结论（不得展示）",
        dimensions: dimensionsFor(92),
        strengths: ["陈旧优势（不得展示）"],
        risks: [],
      },
      rule_score: 97,
      rule_recommendation: "陈旧规则建议（不得展示）",
    },
    {
      id: "item-parse-failed",
      filename: "broken-resume.pdf",
      candidate_id: null,
      candidate_name: "",
      status: "failed",
      error_code: "parse_failed",
      retryable: false,
      route_result: "review",
      llm_status: "failed",
      ai_score: 88,
      ai_recommendation: "陈旧技术失败结论（不得展示）",
    },
  ];
}

function workbenchCandidate({ candidateId, applicationId, name }) {
  return {
    application_id: applicationId,
    candidate_id: candidateId,
    job_id: ids.job,
    display_name: name,
    current_title: "平台工程师",
    location: "上海",
    source: "upload",
    stage: "review",
    updated_at: "2026-07-20T06:05:00Z",
  };
}

function reviewTask(candidate, { taskId, aiStatus }) {
  return {
    ...candidate,
    task_id: taskId,
    ai_status: aiStatus,
    config_warning: false,
    candidate_link: `/candidates/${candidate.candidate_id}?tab=evidence&application=${candidate.application_id}&job=${candidate.job_id}`,
  };
}

function workbenchEnvelope() {
  const scored = workbenchCandidate({
    candidateId: ids.reviewCandidate,
    applicationId: ids.reviewApplication,
    name: "林界（60分）",
  });
  const unavailable = workbenchCandidate({
    candidateId: ids.failedCandidate,
    applicationId: ids.failedApplication,
    name: "周旻（AI不可用）",
  });
  const empty = () => ({ count: 0, items: [] });
  return {
    data: {
      generated_at: "2026-07-20T06:10:00Z",
      jobs: [{
        id: ids.job,
        title: "LLM 平台工程师",
        department_name: "研发中心",
        status: "open",
        updated_at: "2026-07-20T06:10:00Z",
        active_count: 2,
        stages: {
          new: empty(),
          review: { count: 2, items: [scored, unavailable] },
          contact: empty(),
          interview_pending: empty(),
          interviewing: empty(),
          decision: empty(),
          passed: empty(),
        },
      }],
      tasks: {
        review: {
          count: 2,
          items: [
            reviewTask(scored, { taskId: "review-task-score-60", aiStatus: "succeeded" }),
            reviewTask(unavailable, { taskId: "review-task-ai-unavailable", aiStatus: "failed" }),
          ],
        },
        interview_pending: empty(),
        decision: empty(),
        passed: empty(),
      },
      interviews: { available: false, upcoming: [], pending_feedback: [] },
    },
  };
}

function candidateRecord(candidateId) {
  const unavailable = candidateId === ids.failedCandidate;
  return {
    id: candidateId,
    display_name: unavailable ? "周旻（AI不可用）" : "林界（60分）",
    current_title: "平台工程师",
    location: "上海",
    owner_id: "fixture-user",
    version: 2,
    updated_at: "2026-07-20T06:05:00Z",
    contacts: [
      { kind: "phone", value: "138****0000" },
      { kind: "email", value: "synthetic***@example.test" },
    ],
  };
}

function candidateApplication(candidateId) {
  const unavailable = candidateId === ids.failedCandidate;
  return {
    id: unavailable ? ids.failedApplication : ids.reviewApplication,
    candidate_id: candidateId,
    job_id: ids.job,
    job_title: "LLM 平台工程师",
    resume_id: unavailable ? "resume-ai-unavailable" : "resume-score-60",
    owner_id: "fixture-user",
    stage: "review",
    source: "upload",
    human_conclusion: null,
    version: 2,
    updated_at: "2026-07-20T06:05:00Z",
    rule_score: 98,
    recommendation: "陈旧规则建议",
    ai_score: unavailable ? null : 60,
    ai_recommendation: unavailable ? "AI评分不可用" : "建议评审",
    llm_status: unavailable ? "failed" : "succeeded",
    llm_evaluation: unavailable
      ? { score: 92, recommendation: "陈旧模型结论", dimensions: dimensionsFor(92) }
      : screeningEvaluation(60, "建议评审"),
  };
}

function candidateResume(candidateId) {
  return {
    id: candidateId === ids.failedCandidate ? "resume-ai-unavailable" : "resume-score-60",
    candidate_id: candidateId,
    version_number: 1,
    created_at: "2026-07-20T05:55:00Z",
    profile: {
      summary: "仅用于 Task 8 浏览器验收的合成候选人。",
      skills: ["平台工程", "Python"],
      experience: "合成项目经验",
      education: "合成教育经历",
      status: "ready",
    },
  };
}

function deferredPool() {
  return {
    id: ids.deferredPool,
    name: "AI 初筛暂缓",
    purpose: "承接 LLM 最终分低于 60 的候选人",
    visibility: "recruiting_team",
    system_key: "ai_screening_deferred",
    owner: { id: "fixture-user", display_name: "招聘负责人" },
    suitable_roles: ["平台工程师"],
    retention_days: 730,
    member_count: 1,
    version: 2,
    updated_at: "2026-07-20T06:00:00Z",
  };
}

function deferredMembership(referred = false) {
  return {
    id: ids.deferredMembership,
    pool_id: ids.deferredPool,
    candidate: {
      id: ids.deferredCandidate,
      display_name: "韩松（59分）",
      current_title: "后端工程师",
      location: "杭州",
    },
    source_application: {
      id: ids.deferredApplication,
      job_id: ids.job,
      job_title: "LLM 平台工程师",
      stage: referred ? "review" : "deferred",
      human_conclusion: null,
    },
    deferred_screening: {
      final_score: 59,
      deferred_at: "2026-07-20T06:00:00Z",
      main_gaps: ["系统设计深度不足", "缺少带队经验"],
    },
    owner: { id: "fixture-user", display_name: "招聘负责人" },
    suitable_roles: ["平台工程师"],
    tags: ["LLM 59分"],
    reason: "LLM 初筛分低于 60",
    status: "active",
    version: referred ? 4 : 3,
    retention_until: "2028-07-20T00:00:00Z",
    created_at: "2026-07-20T06:00:00Z",
    updated_at: referred ? "2026-07-20T06:20:00Z" : "2026-07-20T06:00:00Z",
  };
}

function fixtureState() {
  return { referred: false, referralRequests: 0, unknownRequests: [] };
}

async function fulfillJson(route, payload, status = 200, extraHeaders = {}) {
  await route.fulfill({
    status,
    contentType: "application/json; charset=utf-8",
    headers: extraHeaders,
    body: JSON.stringify(payload),
  });
}

async function installApiFixture(page, state) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const { pathname } = url;
    const method = request.method();

    if (method === "GET" && pathname === "/api/v1/me") {
      return fulfillJson(route, {
        data: {
          id: "fixture-user",
          display_name: "Task 8 验收账号",
          roles: ["recruiting_admin"],
        },
      }, 200, { "X-CSRF-Token": "synthetic-csrf-token" });
    }
    if (method === "GET" && pathname === "/api/v1/workbench") return fulfillJson(route, workbenchEnvelope());
    if (method === "GET" && pathname === `/api/v1/screening-runs/${ids.run}`) return fulfillJson(route, { data: screeningRun() });
    if (method === "GET" && pathname === `/api/v1/screening-runs/${ids.run}/items`) return fulfillJson(route, { data: screeningItems(), meta: { next_cursor: null } });
    if (method === "GET" && pathname === "/api/v1/interviews") return fulfillJson(route, { data: [], meta: { count: 0, next_cursor: null } });
    if (method === "GET" && pathname === "/api/v1/me/tasks") return fulfillJson(route, { data: [] });
    if (method === "GET" && pathname === "/api/v1/candidates" && url.searchParams.get("stage") === "interview_pending") {
      return fulfillJson(route, { data: [], meta: { next_cursor: null, owners: [] } });
    }
    if (method === "GET" && pathname === "/api/v1/jobs") {
      return fulfillJson(route, { data: [], meta: { next_cursor: null } });
    }
    if (method === "GET" && pathname === "/api/v1/candidates") {
      return fulfillJson(route, { data: [], meta: { next_cursor: null, owners: [] } });
    }
    if (method === "GET" && pathname === "/api/v1/talent-pools") {
      return fulfillJson(route, { data: [deferredPool()], meta: { next_cursor: null } });
    }
    if (method === "GET" && pathname === `/api/v1/talent-pools/${ids.deferredPool}/memberships`) {
      return fulfillJson(route, { data: [deferredMembership(state.referred)], meta: { next_cursor: null } });
    }
    if (method === "POST" && pathname === `/api/v1/talent-pool-memberships/${ids.deferredMembership}/review-referrals`) {
      assert.equal(request.headers()["if-match"], '"3"', "转交评审必须携带当前人才关系版本");
      assert.deepEqual(request.postDataJSON(), {}, "转交评审不应携带手工 stage");
      state.referred = true;
      state.referralRequests += 1;
      return fulfillJson(route, {
        data: {
          application: { id: ids.deferredApplication, stage: "review", version: 4 },
          membership: deferredMembership(true),
        },
      });
    }
    if (method === "GET" && pathname === "/api/v1/reports/recruiting-funnel") {
      return fulfillJson(route, {
        data: {
          can_export: false,
          total_applications: 4,
          stages: [
            { stage: "review", current_count: 2, average_time_in_stage_seconds: 3_600 },
            { stage: "deferred", current_count: 1, average_time_in_stage_seconds: 7_200 },
            { stage: "new", current_count: 1, average_time_in_stage_seconds: 1_800 },
          ],
          interviews: {
            count: 0,
            required_feedback_completed: 0,
            required_feedback_total: 0,
            required_feedback_completion_rate: 0,
            average_feedback_turnaround_seconds: 0,
          },
        },
      });
    }
    if (method === "GET" && pathname === "/api/v1/reports/screening-quality") {
      return fulfillJson(route, {
        data: {
          resume_parsing: { succeeded: 3, total: 4, success_rate: 0.75 },
          llm: { succeeded: 2, total: 3, success_rate: 2 / 3 },
          rule_screening: { passed: 973, total: 1_000, pass_rate: 0.973 },
        },
      });
    }

    const candidateMatch = pathname.match(/^\/api\/v1\/candidates\/([^/]+)(?:\/(applications|resumes|timeline|notes|governance-status))?$/);
    if (method === "GET" && candidateMatch) {
      const candidateId = decodeURIComponent(candidateMatch[1]);
      const resource = candidateMatch[2] || "candidate";
      if (![ids.failedCandidate, ids.reviewCandidate].includes(candidateId)) {
        state.unknownRequests.push(`${method} ${pathname}${url.search}`);
        return fulfillJson(route, { code: "fixture_candidate_missing", title: "Fixture candidate missing" }, 404);
      }
      if (resource === "candidate") return fulfillJson(route, { data: candidateRecord(candidateId) });
      if (resource === "applications") return fulfillJson(route, { data: [candidateApplication(candidateId)] });
      if (resource === "resumes") return fulfillJson(route, { data: [candidateResume(candidateId)] });
      if (resource === "timeline" || resource === "notes") return fulfillJson(route, { data: [] });
      if (resource === "governance-status") {
        return fulfillJson(route, { data: { deletion_status: null, deletion_request_id: null, legal_hold_active: false } });
      }
    }

    state.unknownRequests.push(`${method} ${pathname}${url.search}`);
    return fulfillJson(route, { code: "fixture_route_missing", title: "Fixture route missing" }, 404);
  });
}

function observeRuntime(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText || "unknown";
    if (!reason.includes("ERR_ABORTED")) errors.push(`requestfailed: ${request.method()} ${new URL(request.url()).pathname} ${reason}`);
  });
  return errors;
}

async function gotoApp(page, pathname, heading) {
  const response = await page.goto(new URL(pathname, baseUrl).href, { waitUntil: "domcontentloaded" });
  assert.equal(response?.status(), 200, `${pathname} 应返回前端入口`);
  await assertVisible(page.getByRole("heading", { name: heading, exact: true }), `${pathname} 标题`);
  await assertRendered(page, pathname);
}

function screeningRow(page, text) {
  return page.getByRole("row").filter({ hasText: text }).first();
}

async function auditScreening(page, viewportName) {
  await gotoApp(page, `/screening/tasks/${ids.run}`, "筛选任务");
  await assertVisible(page.getByRole("heading", { name: "逐文件结果", exact: true }), "逐文件结果");
  const headers = ["流转结果", "候选人/文件", "处理状态", "LLM结论", "最终分", "维度评分", "主要优势与风险", "查看候选人"];
  for (const header of headers) {
    const columnHeader = page.getByRole("columnheader", { name: header, exact: true, includeHidden: true });
    assert.equal(await columnHeader.count(), 1, `${header}列语义缺失`);
    if (viewportName === "desktop") await assertVisible(columnHeader, `${header}列`);
  }

  const score60 = screeningRow(page, "score-60-review.pdf");
  await assertVisible(score60, "60 分候选人行");
  assert.match(await score60.innerText(), /已转交用人经理/);
  assert.match(await score60.innerText(), /建议评审/);
  assert.equal((await score60.locator(".final-score").innerText()).trim(), "60");
  if (viewportName === "mobile") {
    const labels = await score60.locator("[role=cell]").evaluateAll((cells) => cells.map((cell) => cell.getAttribute("data-label")));
    assert.deepEqual(labels, headers, "移动端每个结果值必须保留字段标签");
  }

  const score59 = screeningRow(page, "score-59-deferred.pdf");
  await assertVisible(score59, "59 分候选人行");
  assert.match(await score59.innerText(), /已暂缓/);
  assert.match(await score59.innerText(), /暂缓/);
  assert.equal((await score59.locator(".final-score").innerText()).trim(), "59");

  const unavailable = screeningRow(page, "provider-final-failure.pdf");
  await assertVisible(unavailable, "最终 LLM 失败候选人行");
  assert.match(await unavailable.innerText(), /已转交用人经理/);
  assert.match(await unavailable.innerText(), /AI评分不可用/);
  assert.equal((await unavailable.locator(".final-score").innerText()).trim(), "—");
  await assertTextAbsent(unavailable, /陈旧模型结论|陈旧规则建议|陈旧优势/, "最终失败不得回退到陈旧决策");

  const technicalFailure = screeningRow(page, "broken-resume.pdf");
  await assertVisible(technicalFailure, "技术失败文件行");
  assert.match(await technicalFailure.innerText(), /未流转/);
  assert.match(await technicalFailure.innerText(), /未进入AI评分/);
  await assertTextAbsent(technicalFailure, /已转交用人经理|AI评分不可用|陈旧技术失败结论/, "技术失败不得伪装成 AI 路由结果");

  const summary = page.locator(".progress-stats");
  await assertVisible(summary, "自动路由汇总");
  for (const text of ["2已转交用人经理", "1已暂缓", "1AI评分不可用", "1文件处理失败"]) {
    assert.match((await summary.innerText()).replace(/\s/g, ""), new RegExp(text));
  }
  await assertTextAbsent(page.locator("main"), /规则通过率|规则分|规则强制通过|待HR审核|HR已审核|需人工复核|待提交用人经理/, "当前筛选决策不得展示规则或 HR 手工阶段");
  assert.equal(await page.locator('.screening-table input[type="checkbox"]').count(), 0, "LLM-only 结果表不得保留批量全选");
  assert.equal(await page.getByRole("button", { name: /推进到待复核|撤销/ }).count(), 0, "不得保留手工推进或撤销操作");
  await assertNoBodyOverflow(page, `${viewportName} 筛选任务`);
  await screenshot(page, `task8-llm-screening-${viewportName}.png`);
}

async function auditWorkbenchDeepLink(page, viewportName) {
  await gotoApp(page, "/workbench", "工作台");
  await assertVisible(page.getByText("待用人经理评审（2）", { exact: false }), "用人经理待办分组");
  const task = page.locator(".dashboard-tasks .rail-item").filter({ hasText: "周旻（AI不可用）" });
  await assertVisible(task, "AI 不可用经理评审待办");
  await screenshot(page, `task8-manager-workbench-${viewportName}.png`);

  await task.click();
  await page.waitForURL((url) => url.pathname === `/candidates/${ids.failedCandidate}` && url.searchParams.get("tab") === "evidence" && url.searchParams.get("return") === "/workbench");
  await assertVisible(page.getByRole("heading", { name: "候选人详情", exact: true }), "候选人详情");
  await assertVisible(page.getByRole("button", { name: "筛选证据", exact: true }), "筛选证据页签");
  const evidence = page.locator(".llm-evidence");
  await assertVisible(evidence, "持久化筛选证据");
  assert.match(await evidence.innerText(), /AI评分不可用/);
  await assertTextAbsent(evidence, /陈旧模型结论|陈旧规则建议/, "AI 不可用提示不得回退到旧决策");
  const back = page.getByRole("button", { name: "返回工作台", exact: true });
  await assertVisible(back, "返回工作台操作");
  await assertNoBodyOverflow(page, `${viewportName} 筛选证据`);
  await screenshot(page, `task8-ai-unavailable-evidence-${viewportName}.png`);

  await back.click();
  await page.waitForURL((url) => url.pathname === "/workbench");
  await assertVisible(page.getByRole("heading", { name: "工作台", exact: true }), "返回后的工作台");
}

async function auditDeferredPool(page, state, viewportName) {
  await gotoApp(page, `/talent/${ids.deferredPool}`, "人才库详情");
  await assertVisible(page.getByRole("heading", { name: "AI 初筛暂缓", exact: true }), "系统暂缓人才池");
  const table = page.locator(".talent-table");
  await assertVisible(table, "暂缓人才列表");
  for (const label of ["原岗位", "最终分", "暂缓时间", "主要缺口", "跟进负责人", "状态", "操作"]) {
    assert.match(await table.locator(".talent-table-head").innerText(), new RegExp(label));
  }
  const row = table.locator(".talent-table-row").filter({ hasText: "韩松（59分）" });
  await assertVisible(row, "59 分暂缓人才");
  for (const value of ["LLM 平台工程师", "59", "2026-07-20", "系统设计深度不足", "缺少带队经验", "招聘负责人", "AI 初筛暂缓"]) {
    assert.match(await row.innerText(), new RegExp(value));
  }
  await screenshot(page, `task8-deferred-pool-before-referral-${viewportName}.png`);

  const routeBefore = new URL(page.url());
  const referralResponse = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith(`/talent-pool-memberships/${ids.deferredMembership}/review-referrals`));
  await row.getByRole("button", { name: "转交用人经理：韩松（59分）", exact: true }).click();
  assert.equal((await referralResponse).status(), 200);
  await assertVisible(row.getByRole("button", { name: "转交用人经理：韩松（59分）", exact: true }).filter({ hasText: "已转交用人经理" }), "转交完成状态");
  assert.equal(state.referralRequests, 1, "转交评审应只提交一次");
  assert.equal(new URL(page.url()).pathname, routeBefore.pathname, "转交后必须留在同一人才池路由");
  assert.equal(await table.locator(".talent-table-row").count(), 1, "转交后必须保留列表行");
  assert.match(await row.innerText(), /用人经理复核/);
  await assertNoBodyOverflow(page, `${viewportName} AI 初筛暂缓人才池`);
  await screenshot(page, `task8-deferred-pool-referred-${viewportName}.png`);
}

async function auditReports(page, viewportName) {
  await gotoApp(page, "/reports", "报表");
  await assertVisible(page.getByRole("heading", { name: "基础招聘报表", exact: true }), "基础招聘报表");
  const quality = page.getByRole("heading", { name: "筛选质量", exact: true }).locator("xpath=ancestor::section[1]");
  await assertVisible(quality, "筛选质量面板");
  assert.match(await quality.innerText(), /解析成功率/);
  assert.match(await quality.innerText(), /LLM 成功率/);
  await assertTextAbsent(page.locator("main"), /规则通过率|规则筛选通过率|97\.3%/, "当前报表不得展示旧规则指标");
  await assertNoBodyOverflow(page, `${viewportName} 报表`);
  await screenshot(page, `task8-llm-report-${viewportName}.png`);
}

async function runViewport(browser, viewportName, viewport, audits) {
  const context = await browser.newContext({ viewport, locale: "zh-CN", isMobile: viewportName === "mobile" });
  const page = await context.newPage();
  const state = fixtureState();
  const runtimeErrors = observeRuntime(page);
  await installApiFixture(page, state);
  try {
    for (const [id, audit] of audits) await runCase(page, `${viewportName}-${id}`, () => audit(page, state, viewportName));
    await runCase(page, `${viewportName}-runtime-integrity`, async () => {
      assert.deepEqual(state.unknownRequests, [], `fixture 缺少 API：${state.unknownRequests.join(" | ")}`);
      assert.deepEqual(runtimeErrors, [], `浏览器运行时错误：${runtimeErrors.join(" | ")}`);
    });
  } finally {
    await context.close();
  }
}

async function main() {
  fs.mkdirSync(evidenceDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    await runViewport(browser, "desktop", { width: 1280, height: 720 }, [
      ["screening-auto-routing", (page, _state, viewportName) => auditScreening(page, viewportName)],
      ["manager-review-deep-link", (page, _state, viewportName) => auditWorkbenchDeepLink(page, viewportName)],
      ["deferred-pool-referral", auditDeferredPool],
      ["reports-hide-rule-metrics", (page, _state, viewportName) => auditReports(page, viewportName)],
    ]);
    await runViewport(browser, "mobile", { width: 390, height: 844 }, [
      ["screening-layout", (page, _state, viewportName) => auditScreening(page, viewportName)],
      ["manager-review-layout", (page, _state, viewportName) => auditWorkbenchDeepLink(page, viewportName)],
      ["deferred-pool-layout", auditDeferredPool],
      ["report-layout", (page, _state, viewportName) => auditReports(page, viewportName)],
    ]);
  } finally {
    await browser.close();
    fs.writeFileSync(
      path.join(evidenceDir, "ux08-browser-audit-results.json"),
      `${JSON.stringify({ baseUrl: baseUrl.origin, fixture: "llm-only-controller-contract", results }, null, 2)}\n`,
      "utf8",
    );
  }
  process.stdout.write(`Browser audit passed (${results.length}/${results.length}); evidence: ${evidenceDir}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
