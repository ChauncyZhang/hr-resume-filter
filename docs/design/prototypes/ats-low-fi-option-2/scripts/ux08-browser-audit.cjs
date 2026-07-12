const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = process.env.UX08_URL || "http://127.0.0.1:4174/";
const evidenceDir = path.resolve(__dirname, "../ux-08-evidence");
const results = [];

function record(id, status, detail = "") {
  results.push({ id, status, detail });
  process.stdout.write(`${status === "passed" ? "PASS" : "FAIL"} ${id}${detail ? `: ${detail}` : ""}\n`);
}

async function assertVisible(locator, description) {
  try {
    await locator.first().waitFor({ state: "visible", timeout: 5000 });
  } catch {
    throw new Error(`${description} 不可见`);
  }
}

async function assertNoBodyOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  if (dimensions.document > dimensions.viewport + 1 || dimensions.body > dimensions.viewport + 1) {
    throw new Error(`${label} 横向溢出 ${JSON.stringify(dimensions)}`);
  }
}

async function switchScenario(page, value) {
  const trigger = page.getByRole("button", { name: "验收场景" });
  if (!(await page.getByLabel("当前场景").count())) await trigger.click();
  await page.getByLabel("当前场景").selectOption(value);
  const dialog = page.getByRole("dialog", { name: "切换验收场景" });
  await assertVisible(dialog, "场景切换确认框");
  await dialog.getByRole("button", { name: "确认切换" }).click();
  await page.waitForTimeout(100);
}

async function screenshot(page, filename) {
  await page.screenshot({ path: path.join(evidenceDir, filename), fullPage: true });
}

async function runCase(id, fn) {
  try {
    await fn();
    record(id, "passed");
  } catch (error) {
    record(id, "failed", error.message);
    throw error;
  }
}

async function desktopAudit(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, locale: "zh-CN" });
  const page = await context.newPage();
  const runtimeErrors = [];
  page.on("pageerror", (error) => runtimeErrors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(`console: ${message.text()}`); });
  await page.goto(baseUrl, { waitUntil: "networkidle" });

  await runCase("F-01-default-workbench", async () => {
    await assertVisible(page.getByRole("heading", { name: "工作台" }), "工作台标题");
    await assertVisible(page.getByRole("button", { name: /导入简历/ }), "导入简历主操作");
    await assertNoBodyOverflow(page, "桌面工作台");
    await screenshot(page, "ux08-default-workbench-1280x720.png");
  });

  await runCase("F-01-create-and-publish-position", async () => {
    await page.getByRole("button", { name: /新建职位/ }).click();
    await page.getByLabel("职位名称").fill("UX-08 AI 平台工程师");
    await page.getByLabel("公开 JD").fill("负责企业级 RAG、Agent 与大模型应用平台建设，要求熟悉 Python、机器学习、深度学习和 LLM 工程化。");
    await page.getByRole("button", { name: /AI 提取筛选条件/ }).click();
    await assertVisible(page.getByText("已提取，可人工修改", { exact: true }), "JD 条件提取结果");
    await page.getByRole("button", { name: "发布职位", exact: true }).click();
    await assertVisible(page.getByRole("heading", { name: "职位详情" }), "发布后的职位详情");
    await assertVisible(page.getByText("UX-08 AI 平台工程师", { exact: true }).first(), "新发布职位名称");
    await screenshot(page, "ux08-position-published-1280x720.png");
  });

  await runCase("F-02-partial-screening-recovery", async () => {
    await switchScenario(page, "partial-screening");
    await assertVisible(page.getByText("8/8", { exact: true }), "筛选完成进度");
    const parseRetry = page.getByRole("button", { name: /重新解析/ });
    const llmRetry = page.getByRole("button", { name: /重试 LLM/ });
    if (await parseRetry.count()) await parseRetry.first().click();
    if (await llmRetry.count()) await llmRetry.first().click();
    await assertVisible(page.getByText("8", { exact: true }).first(), "筛选成功数量");
    await screenshot(page, "ux08-screening-recovered-1280x720.png");
  });

  await runCase("F-03-screening-undo-and-promote", async () => {
    const selectAll = page.locator(".screening-table-head input[type=checkbox]");
    await selectAll.check();
    await page.getByRole("button", { name: /推进到待复核/ }).click();
    await assertVisible(page.getByText(/已完成“推进到待复核”/), "批量操作撤销提示");
    await assertVisible(page.getByText(/影响 7 人/), "重复简历去重后的影响人数");
    await page.getByRole("button", { name: "撤销" }).click();
    await selectAll.check();
    await page.getByRole("button", { name: /推进到待复核/ }).click();
    await page.locator(".screening-identity").filter({ hasText: "林启舟" }).first().click();
    await assertVisible(page.getByRole("heading", { name: "候选人详情" }), "候选人详情");
    await page.getByRole("button", { name: "职位申请" }).click();
    const aiApplications = page.locator(".applications-table").getByText("AI 工程师", { exact: true });
    if (await aiApplications.count() !== 1) throw new Error(`重复候选人产生 ${await aiApplications.count()} 条 AI 工程师申请`);
    await screenshot(page, "ux08-candidate-single-application-1280x720.png");
  });

  await runCase("F-05-feedback-draft-and-retry", async () => {
    await switchScenario(page, "pending-feedback");
    const strengths = page.getByLabel(/候选人优点/);
    await strengths.fill("结构化表达清晰，能说明关键产品决策。");
    await page.getByRole("button", { name: /返回面试列表/ }).click();
    await page.getByRole("button", { name: /填写反馈/ }).first().click();
    if ((await page.getByLabel(/候选人优点/).inputValue()) !== "结构化表达清晰，能说明关键产品决策。") throw new Error("离开后反馈草稿未恢复");
    for (const row of await page.locator(".rating-row").all()) await row.getByRole("button", { name: "良好" }).click();
    await page.getByLabel(/风险与待确认项/).fill("商业化指标需要进一步确认。");
    await page.getByRole("button", { name: "推荐", exact: true }).click();
    await page.getByRole("button", { name: /提交反馈/ }).click();
    await assertVisible(page.getByText("反馈提交失败", { exact: true }), "首次提交失败提示");
    await page.getByRole("button", { name: /重试提交/ }).click();
    await assertVisible(page.getByText("已提交", { exact: true }).first(), "反馈提交完成状态");
    await screenshot(page, "ux08-feedback-submitted-1280x720.png");
  });

  await runCase("F-04-schedule-interview", async () => {
    await switchScenario(page, "default");
    await page.locator(".sidebar nav").getByRole("button", { name: "候选人", exact: true }).click();
    await page.locator(".candidate-table-row").filter({ hasText: "陈浩" }).click();
    await page.getByRole("button", { name: "面试与反馈", exact: true }).click();
    await page.getByRole("button", { name: /安排面试/ }).first().click();
    await page.getByRole("button", { name: /下一步：面试协同/ }).click();
    await page.locator(".schedule-full-field input").fill("https://meeting.example.com/ux08-final");
    await page.getByRole("button", { name: /检查时间并继续/ }).click();
    await page.getByRole("button", { name: /确认并保存/ }).click();
    await assertVisible(page.locator(".interview-table-row").filter({ hasText: "陈浩" }), "已保存的面试记录");
    await screenshot(page, "ux08-interview-scheduled-1280x720.png");
  });

  await runCase("F-06-talent-reactivation", async () => {
    await switchScenario(page, "talent-reactivation");
    await page.locator(".talent-table-row .button.primary.small").first().click();
    await page.locator(".talent-member-drawer > footer .button.primary").click();
    const targetPosition = page.locator(".reactivate-drawer select").first();
    await targetPosition.selectOption("JOB-JAVA-002");
    await page.locator(".reactivate-drawer > footer .button.primary").click();
    await assertVisible(page.getByText("已创建新的职位申请", { exact: true }), "人才重新激活结果");
    await assertVisible(page.getByText(/历史申请和人才库关系均已保留/), "历史关系保留说明");
    await screenshot(page, "ux08-talent-reactivated-1280x720.png");
    await page.locator(".reactivation-success .button.secondary").click();
    await page.locator(".talent-member-drawer .icon-button").click();
  });

  await runCase("ADMIN-settings-governance", async () => {
    await switchScenario(page, "default");
    await page.locator(".sidebar nav").getByRole("button", { name: "设置", exact: true }).click();
    await page.locator(".settings-table-row").filter({ hasText: "陈雨" }).click();
    await page.getByLabel("AI 工程师", { exact: true }).check();
    await page.getByRole("button", { name: "保存权限", exact: true }).click();
    await page.getByRole("dialog", { name: "确认扩大职位权限" }).getByRole("button", { name: "确认扩大权限" }).click();
    await page.locator(".settings-subnav").getByRole("button", { name: "AI 设置", exact: true }).click();
    await page.getByLabel("Base URL").fill("https://invalid.example.com/v1");
    await page.getByRole("button", { name: "测试连接", exact: true }).click();
    await assertVisible(page.getByText("连接失败", { exact: true }), "AI 连接失败状态");
    await page.getByLabel("Base URL").fill("https://open.example.com/v1");
    await page.getByRole("button", { name: "测试连接", exact: true }).click();
    await assertVisible(page.getByText("连接成功", { exact: true }), "AI 连接恢复状态");
    await page.locator(".settings-subnav").getByRole("button", { name: "审计与数据治理", exact: true }).click();
    const dirtyDialog = page.getByRole("dialog", { name: "AI 设置尚未保存" });
    if (await dirtyDialog.count()) await dirtyDialog.getByRole("button", { name: "保存草稿并离开" }).click();
    await page.locator(".retention-policy select").selectOption("365");
    await page.getByRole("button", { name: "保存保留策略", exact: true }).click();
    await page.getByRole("dialog", { name: "确认缩短候选人保留期限" }).getByRole("button", { name: "确认缩短期限" }).click();
    await screenshot(page, "ux08-admin-governance-1280x720.png");
  });

  await runCase("ROLE-interviewer-boundary", async () => {
    await switchScenario(page, "restricted");
    await assertVisible(page.getByText("暂无报表查看权限", { exact: true }), "报表无权限状态");
    const navText = await page.locator(".sidebar nav").innerText();
    if (navText.includes("职位") || navText.includes("候选人") || navText.includes("人才库") || navText.includes("设置")) throw new Error(`面试官导航越权：${navText}`);
    if (await page.locator(".role-switch").count()) throw new Error("无权限页面仍可切换为管理员");
    await screenshot(page, "ux08-interviewer-restricted-1280x720.png");
  });

  await runCase("EMPTY-empty-state", async () => {
    await switchScenario(page, "empty");
    await assertVisible(page.getByText("没有符合条件的候选人", { exact: true }), "候选人空态");
    await assertNoBodyOverflow(page, "桌面空态");
  });

  await runCase("A11Y-keyboard-focus", async () => {
    await switchScenario(page, "default");
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => ({ tag: document.activeElement?.tagName, text: document.activeElement?.textContent?.trim(), outline: getComputedStyle(document.activeElement).outlineStyle }));
    if (!focused.tag || focused.tag === "BODY") throw new Error("Tab 未进入可交互控件");
  });

  if (runtimeErrors.length) throw new Error(`桌面运行时错误：${runtimeErrors.join(" | ")}`);
  await context.close();
}

async function mobileAudit(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "zh-CN", isMobile: true });
  const page = await context.newPage();
  const runtimeErrors = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(message.text()); });
  await page.goto(baseUrl, { waitUntil: "networkidle" });

  await runCase("MOBILE-default", async () => {
    await assertNoBodyOverflow(page, "移动工作台");
    await page.getByRole("button", { name: "打开菜单" }).click();
    await assertVisible(page.locator(".sidebar.sidebar-open"), "移动导航");
    await screenshot(page, "ux08-default-workbench-390x844.png");
  });

  await runCase("MOBILE-partial-screening", async () => {
    await page.getByRole("button", { name: "关闭菜单" }).click();
    await switchScenario(page, "partial-screening");
    await assertNoBodyOverflow(page, "移动筛选页");
    await screenshot(page, "ux08-partial-screening-390x844.png");
  });

  await runCase("MOBILE-feedback", async () => {
    await switchScenario(page, "pending-feedback");
    await assertNoBodyOverflow(page, "移动反馈页");
    await screenshot(page, "ux08-feedback-390x844.png");
  });

  await runCase("MOBILE-restricted", async () => {
    await switchScenario(page, "restricted");
    await assertNoBodyOverflow(page, "移动权限页");
    await assertVisible(page.getByText("暂无报表查看权限", { exact: true }), "移动权限状态");
    await screenshot(page, "ux08-interviewer-restricted-390x844.png");
  });

  if (runtimeErrors.length) throw new Error(`移动运行时错误：${runtimeErrors.join(" | ")}`);
  await context.close();
}

(async () => {
  fs.mkdirSync(evidenceDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    await desktopAudit(browser);
    await mobileAudit(browser);
  } finally {
    await browser.close();
  }
  const failed = results.filter((item) => item.status === "failed");
  fs.writeFileSync(path.join(evidenceDir, "ux08-browser-audit-results.json"), `${JSON.stringify({ generatedAt: new Date().toISOString(), baseUrl, results }, null, 2)}\n`, "utf8");
  if (failed.length) process.exitCode = 1;
})().catch((error) => {
  record("AUDIT-runtime", "failed", error.stack || error.message);
  fs.mkdirSync(evidenceDir, { recursive: true });
  fs.writeFileSync(path.join(evidenceDir, "ux08-browser-audit-results.json"), `${JSON.stringify({ generatedAt: new Date().toISOString(), baseUrl, results }, null, 2)}\n`, "utf8");
  process.exitCode = 1;
});
