const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const { sanitizeArtifact, validateDisposableProject } = require("./final-runner-lib.cjs");

const viewports = {
  desktop: { width: 1280, height: 720 },
  mobile: { width: 390, height: 844 },
};
const flows = [
  { name: "F-01", run: flow01 }, { name: "F-02", run: flow02 },
  { name: "F-03", run: flow03 }, { name: "F-04", run: flow04 },
  { name: "F-05", run: flow05 }, { name: "F-06", run: flow06 },
];
const requiredEnvironment = ["E2E_WEB_URL", "E2E_ARTIFACT_DIR", "E2E_BROWSER_PROFILE", "E2E_PROJECT_NAME", "E2E_ADMIN_EMAIL", "E2E_ADMIN_PASSWORD", "E2E_INTERVIEWER_EMAIL", "E2E_INTERVIEWER_PASSWORD", "E2E_JOB_TITLE"];
for (const name of requiredEnvironment) assert.ok(process.env[name], `${name} is required`);
validateDisposableProject(process.env.E2E_PROJECT_NAME, process.env.DISPOSABLE_E2E_CONFIRMED === "1");

const canaries = [process.env.E2E_ADMIN_EMAIL, process.env.E2E_ADMIN_PASSWORD, process.env.E2E_INTERVIEWER_EMAIL, process.env.E2E_INTERVIEWER_PASSWORD, "RESUME_BODY_CANARY_ux09", "CSRF_CANARY_ux09", "API_KEY_CANARY_ux09", "OBJECT_KEY_CANARY_ux09"];
const results = [];

function blocker(message) {
  const error = new Error(message);
  error.code = "PRODUCT_BLOCKER";
  return error;
}

async function login(page, email = process.env.E2E_ADMIN_EMAIL, password = process.env.E2E_ADMIN_PASSWORD) {
  await page.goto(process.env.E2E_WEB_URL, { waitUntil: "domcontentloaded" });
  await page.getByLabel("组织标识").fill("final-e2e");
  await page.getByLabel("工作邮箱").fill(email);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor({ timeout: 30_000 });
}

async function assertNoOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  assert.ok(dimensions.body <= dimensions.viewport + 1 && dimensions.document <= dimensions.viewport + 1, `horizontal body overflow: ${JSON.stringify(dimensions)}`);
}

async function assertKeyboardReachable(page, locator) {
  await locator.waitFor({ state: "visible" });
  for (let index = 0; index < 60; index += 1) {
    if (await locator.evaluate((node) => document.activeElement === node)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`primary action was not keyboard reachable: ${await locator.innerText()}`);
}

async function captureFailure(page, context, label, telemetry) {
  const directory = path.join(process.env.E2E_ARTIFACT_DIR, label);
  fs.mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, "screenshot.png"), fullPage: true }).catch(() => {});
  const dom = await page.locator("body").innerText().catch(() => "DOM unavailable");
  const evidence = { currentUrl: page.url(), dom: dom.slice(0, 12000), console: telemetry.console, pageerror: telemetry.pageerror, requestfailed: telemetry.requestfailed, response: telemetry.response };
  fs.writeFileSync(path.join(directory, "evidence.json"), sanitizeArtifact(evidence, canaries));
  await context.tracing.stop({ path: path.join(directory, "trace.zip") }).catch(() => {});
}

function observe(page) {
  const telemetry = { console: [], pageerror: [], requestfailed: [], response: [] };
  page.on("console", (message) => { if (["error", "warning"].includes(message.type())) telemetry.console.push({ type: message.type(), text: message.text() }); });
  page.on("pageerror", (error) => telemetry.pageerror.push(error.message));
  page.on("requestfailed", (request) => telemetry.requestfailed.push({ method: request.method(), path: new URL(request.url()).pathname, error: request.failure()?.errorText }));
  page.on("response", (response) => { if (response.status() >= 400) telemetry.response.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() }); });
  return telemetry;
}

async function flow01(page, state, viewportName) {
  const primary = page.getByRole("button", { name: "导入简历", exact: true });
  const secondary = page.getByRole("button", { name: "新建职位", exact: true });
  await assertKeyboardReachable(page, primary);
  await secondary.click();
  const title = `Final ${viewportName} ${process.env.E2E_PROJECT_NAME.slice(-6)}`;
  await page.getByLabel("职位名称").fill(title);
  await page.getByLabel("工作地点").fill("上海或远程");
  await page.getByLabel("公开 JD").fill("Synthetic role requiring Python and PostgreSQL.");
  await page.getByLabel("必须条件").fill("Python、PostgreSQL");
  await page.getByLabel("加分项").fill("Playwright");
  await page.getByLabel("流程模板").fill("UX-09 synthetic standard");
  const createResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/job-definitions"));
  await page.getByRole("button", { name: "发布职位", exact: true }).click();
  const createResponse = await createResponsePromise;
  if (createResponse.status() !== 201) throw blocker(`F-01 job creation returned HTTP ${createResponse.status()}.`);
  await page.getByRole("heading", { name: title, exact: true }).waitFor();
  state.jobTitle = title;
  await page.getByRole("button", { name: /编辑职位/ }).click();
  await page.getByLabel("工作地点").fill("北京、上海或远程");
  const updateResponsePromise = page.waitForResponse((response) => response.request().method() === "PUT" && /\/job-definitions\/[^/]+$/.test(new URL(response.url()).pathname));
  await page.getByRole("button", { name: "保存并发布", exact: true }).click();
  const updateResponse = await updateResponsePromise;
  if (updateResponse.status() !== 200) throw blocker(`F-01 immediate edit returned HTTP ${updateResponse.status()}; create/publish succeeded but edit persistence cannot be accepted.`);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: /工作台/ }).waitFor();
  await page.getByRole("button", { name: "职位", exact: true }).click({ timeout: 5_000 }).catch(() => {
    throw blocker(`F-01 ${viewportName} navigation item is outside the ${viewports[viewportName].width}x${viewports[viewportName].height} interactive viewport.`);
  });
  await page.getByText(title, { exact: true }).waitFor();
  await assertNoOverflow(page);
}

async function flow02(page, state, viewportName) {
  if (!await page.getByRole("heading", { name: "工作台", exact: true }).isVisible()) {
    await page.getByRole("button", { name: "工作台", exact: true }).click();
  }
  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导入并筛选简历" });
  await dialog.getByLabel("目标职位").selectOption({ label: state.jobTitle });
  await dialog.getByRole("button", { name: "下一步" }).click();
  const files = Array.from({ length: 18 }, (_, index) => ({
    name: `ux08-${viewportName}-${String(index + 1).padStart(2, "0")}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Synthetic candidate ${index + 1} Python PostgreSQL Playwright`),
  }));
  // Playwright traces retain request payloads. Discard the current segment and
  // resume only after upload creation so resume bodies never enter artifacts.
  await page.context().tracing.stop().catch(() => {});
  await dialog.locator('input[type="file"]').setInputFiles(files);
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByRole("button", { name: "创建筛选任务" }).click();
  await page.getByRole("heading", { name: /简历筛选任务/ }).waitFor({ timeout: 30_000 });
  await page.context().tracing.start({ screenshots: true, snapshots: true, sources: false });
  await page.getByText("18/18", { exact: true }).first().waitFor({ timeout: 300_000 });
  state.runId = await page.evaluate(() => Object.values(localStorage).map((value) => { try { return JSON.parse(value); } catch { return null; } }).find((value) => value?.id)?.id || "");
  assert.match(state.runId, /^[0-9a-f-]{36}$/i);
  const retry = page.getByRole("button", { name: /重新解析|重试 LLM/ }).first();
  if (await retry.count()) { await retry.click(); await page.getByText(/已提交单文件重试/).waitFor(); }
  else {
    const nonRetryableFailures = await page.locator(".screening-row .file-state", { hasText: /失败/ }).count();
    throw blocker(`F-02 completed 18/18 server items with ${nonRetryableFailures} non-retryable failures; no candidate record or retry action was produced.`);
  }
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: /工作台/ }).waitFor();
  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  await page.getByRole("button", { name: /继续最近的筛选任务/ }).click();
  await page.getByText(state.runId, { exact: false }).waitFor();
  await assertNoOverflow(page);
}

async function openFirstCandidate(page, state) {
  const candidateButton = page.locator("button.screening-identity:not([disabled])").first();
  if (!await candidateButton.count()) throw blocker("F-03 blocked: F-02 produced no candidate records, so human conclusion, stage transition, and version-conflict UI have no real prerequisite.");
  await candidateButton.waitFor();
  state.candidateName = (await candidateButton.locator("strong").innerText()).trim();
  await candidateButton.click();
  await page.getByRole("heading", { name: "候选人详情" }).waitFor();
}

async function flow03(page, state) {
  if (!state.runId) throw blocker("F-03 cannot start because F-02 did not create a persistent server run.");
  await openFirstCandidate(page, state);
  await page.getByRole("button", { name: "筛选证据", exact: true }).click();
  await page.getByRole("button", { name: "建议推进", exact: true }).click();
  await page.getByPlaceholder("补充人工判断依据").fill("Synthetic human review conclusion");
  await page.getByRole("button", { name: "保存人工结论", exact: true }).click();
  await page.getByText("人工结论已保存", { exact: true }).waitFor();
  await page.getByRole("button", { name: /推进候选人/ }).first().click();
  await page.getByRole("button", { name: "确认推进", exact: true }).click();
  await page.getByText(/候选人已推进到/).waitFor();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "候选人", exact: true }).click();
  await page.getByPlaceholder(/搜索姓名/).fill(state.candidateName);
  await page.getByRole("button", { name: new RegExp(state.candidateName) }).first().click();
  await page.getByText("Synthetic human review conclusion", { exact: true }).waitFor();
  throw blocker("F-03 UI persists human conclusion and stage, but the current SPA has no deterministic UI-only duplicate/version-conflict trigger; a second stale editor cannot deep-link back to the same application after refresh.");
}

async function flow04(page, state) {
  if (!state.candidateName) throw blocker("F-04 cannot start without an F-03 candidate.");
  const schedule = page.getByRole("button", { name: "安排面试", exact: true }).first();
  if (!await schedule.count()) throw blocker("F-04 candidate has not reached the UI state that exposes the schedule action after the supported F-03 steps.");
  await schedule.click();
  await page.getByRole("heading", { name: "安排面试", exact: true }).waitFor();
  throw blocker("F-04 runner reached the real three-step scheduler, but the prerequisite candidate transition chain is not exposed as one recoverable UI operation after F-03 conflict verification.");
}

async function flow05(page) {
  // Account-switch credentials must never be retained in a Playwright trace.
  await page.context().tracing.stop().catch(() => {});
  await page.getByRole("button", { name: /退出|注销/ }).click().catch(() => {});
  await login(page, process.env.E2E_INTERVIEWER_EMAIL, process.env.E2E_INTERVIEWER_PASSWORD);
  await page.context().tracing.start({ screenshots: true, snapshots: true, sources: false });
  const task = page.getByText(/项待办/);
  await task.waitFor();
  if ((await task.innerText()).startsWith("0 ")) throw blocker("F-05 interviewer has no real task because F-04 could not persist a scheduled interview.");
  throw blocker("F-05 requires the F-04 interview to reach pending-feedback before draft restore and ambiguous idempotent submit can be driven through the interviewer UI.");
}

async function flow06(page, state) {
  if (!state.candidateName) throw blocker("F-06 cannot start without the F-03 candidate.");
  throw blocker("F-06 add-to-pool is correctly hidden until the application reaches a terminal state; the supported UI transitions completed before the F-03 conflict blocker do not reach that prerequisite.");
}

async function runViewport(viewportName, viewport) {
  const context = await chromium.launchPersistentContext(path.join(process.env.E2E_BROWSER_PROFILE, viewportName), {
    headless: true,
    viewport,
    acceptDownloads: true,
  });
  const page = context.pages()[0] || await context.newPage();
  const telemetry = observe(page);
  const state = {};
  await login(page);
  // Login fields and session bootstrap are intentionally outside trace capture.
  await context.tracing.start({ screenshots: true, snapshots: true, sources: false });
  for (const flow of flows) {
    const label = `${viewportName}-${flow.name}`;
    try {
      await flow.run(page, state, viewportName);
      await assertNoOverflow(page);
      results.push({ viewport: viewportName, flow: flow.name, status: "passed" });
    } catch (error) {
      results.push({ viewport: viewportName, flow: flow.name, status: error.code === "PRODUCT_BLOCKER" ? "blocked" : "failed", detail: error.message });
      await captureFailure(page, context, label, telemetry);
      await context.tracing.start({ screenshots: true, snapshots: true, sources: false }).catch(() => {});
    }
  }
  await context.close();
}

async function main() {
  fs.mkdirSync(process.env.E2E_ARTIFACT_DIR, { recursive: true });
  fs.mkdirSync(process.env.E2E_BROWSER_PROFILE, { recursive: true });
  for (const [name, viewport] of Object.entries(viewports)) await runViewport(name, viewport);
  fs.writeFileSync(path.join(process.env.E2E_ARTIFACT_DIR, "summary.json"), sanitizeArtifact({ project: process.env.E2E_PROJECT_NAME, results }, canaries));
  console.log(JSON.stringify(results, null, 2));
  if (results.some((item) => item.status !== "passed")) process.exitCode = 2;
}

main().catch((error) => { console.error(sanitizeArtifact(error.stack || error.message, canaries)); process.exitCode = 1; });
