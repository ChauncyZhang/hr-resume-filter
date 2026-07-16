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
const requiredEnvironment = ["E2E_WEB_URL", "E2E_BASE_URL", "E2E_ARTIFACT_DIR", "E2E_BROWSER_PROFILE", "E2E_PROJECT_NAME", "E2E_ADMIN_EMAIL", "E2E_ADMIN_PASSWORD", "E2E_INTERVIEWER_EMAIL", "E2E_INTERVIEWER_PASSWORD", "E2E_UNASSIGNED_INTERVIEWER_EMAIL", "E2E_UNASSIGNED_INTERVIEWER_PASSWORD", "E2E_RECRUITER_EMAIL", "E2E_RECRUITER_PASSWORD", "E2E_JOB_TITLE"];
for (const name of requiredEnvironment) assert.ok(process.env[name], `${name} is required`);
validateDisposableProject(process.env.E2E_PROJECT_NAME, process.env.DISPOSABLE_E2E_CONFIRMED === "1");

const canaries = [process.env.E2E_ADMIN_EMAIL, process.env.E2E_ADMIN_PASSWORD, process.env.E2E_INTERVIEWER_EMAIL, process.env.E2E_INTERVIEWER_PASSWORD, process.env.E2E_UNASSIGNED_INTERVIEWER_EMAIL, process.env.E2E_UNASSIGNED_INTERVIEWER_PASSWORD, process.env.E2E_RECRUITER_EMAIL, process.env.E2E_RECRUITER_PASSWORD, "RESUME_BODY_CANARY_ux09", "CSRF_CANARY_ux09", "API_KEY_CANARY_ux09", "OBJECT_KEY_CANARY_ux09"];
const results = [];

function blocker(message) {
  const error = new Error(message);
  error.code = "PRODUCT_BLOCKER";
  return error;
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function responsePath(response) {
  return new URL(response.url()).pathname;
}

function futureDate(days) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

async function responseData(response) {
  const body = await response.json();
  assert.ok(body?.data, `HTTP ${response.status()} response did not include data`);
  return body.data;
}

async function login(page, email = process.env.E2E_ADMIN_EMAIL, password = process.env.E2E_ADMIN_PASSWORD) {
  const authConfigResponsePromise = page.waitForResponse((response) => response.request().method() === "GET" && responsePath(response).endsWith("/api/v1/auth/config"));
  await page.goto(process.env.E2E_WEB_URL, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "登录工作台", exact: true }).waitFor({ timeout: 30_000 });
  const authConfigResponse = await authConfigResponsePromise;
  assert.equal(authConfigResponse.status(), 200, `auth config returned HTTP ${authConfigResponse.status()}`);
  const authConfig = await responseData(authConfigResponse);
  assert.equal(authConfig?.default_organization?.slug, "final-e2e");
  assert.equal(await page.locator('input[name="organization_slug"]').count(), 0, "dedicated deployment exposed the organization slug field");
  await page.getByLabel("工作邮箱").fill(email);
  await page.getByLabel("密码").fill(password);
  const loginResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith("/api/v1/auth/login"));
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const loginResponse = await loginResponsePromise;
  assert.equal(loginResponse.status(), 200, `login returned HTTP ${loginResponse.status()}`);
  assert.equal(loginResponse.request().postDataJSON()?.organization_slug, "final-e2e");
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor({ timeout: 30_000 });
}

async function switchAccount(page, email, password) {
  await page.getByRole("button", { name: /退出登录|正在退出/ }).click();
  await page.getByLabel("工作邮箱").waitFor();
  await login(page, email, password);
}

async function navigate(page, label) {
  const navigation = page.getByRole("navigation", { name: "主导航" });
  const target = navigation.getByRole("button", { name: label, exact: true });
  if (!await target.isVisible()) {
    const menu = page.getByRole("button", { name: "打开主导航", exact: true });
    if (await menu.isVisible()) await menu.click();
  }
  await target.waitFor({ state: "visible" });
  await target.click();
  await page.getByRole("heading", { name: label, exact: true }).first().waitFor();
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

async function captureFailure(page, label, telemetry) {
  const directory = path.join(process.env.E2E_ARTIFACT_DIR, label);
  fs.mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, "screenshot.png"), fullPage: true }).catch(() => {});
  const dom = await page.locator("body").innerText().catch(() => "DOM unavailable");
  const evidence = { currentUrl: page.url(), dom: dom.slice(0, 12000), console: telemetry.console, pageerror: telemetry.pageerror, requestfailed: telemetry.requestfailed, response: telemetry.response };
  fs.writeFileSync(path.join(directory, "evidence.json"), sanitizeArtifact(evidence, canaries));
}

function observe(page, telemetry = { console: [], pageerror: [], requestfailed: [], response: [] }) {
  page.on("console", (message) => { if (["error", "warning"].includes(message.type())) telemetry.console.push({ type: message.type(), text: message.text() }); });
  page.on("pageerror", (error) => telemetry.pageerror.push(error.message));
  page.on("requestfailed", (request) => telemetry.requestfailed.push({ method: request.method(), path: new URL(request.url()).pathname, error: request.failure()?.errorText }));
  page.on("response", (response) => { if (response.status() >= 400) telemetry.response.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() }); });
  return telemetry;
}

function telemetryCheckpoint(telemetry) {
  return Object.fromEntries(Object.entries(telemetry).map(([name, entries]) => [name, entries.length]));
}

function telemetryDelta(telemetry, checkpoint) {
  return Object.fromEntries(Object.entries(telemetry).map(([name, entries]) => [name, entries.slice(checkpoint[name])]));
}

function expectedResponse(flowName, entry) {
  if (flowName === "F-02" && entry.status === 422 && entry.method === "POST" && /\/screening-runs\/[^/]+\/items$/.test(entry.path)) return true;
  if (flowName === "F-05" && entry.status === 401 && entry.method === "GET" && entry.path.endsWith("/api/v1/me")) return true;
  if (flowName === "F-05" && entry.status === 401 && entry.method === "GET" && entry.path.endsWith("/my-feedback")) return true;
  if (flowName === "F-05" && entry.status === 404 && entry.method === "GET" && entry.path.endsWith("/my-feedback")) return true;
  if (entry.status !== 409 || entry.method !== "POST") return false;
  if (flowName === "F-03") return /\/applications\/[^/]+\/transitions$/.test(entry.path) || /\/jobs\/[^/]+\/applications$/.test(entry.path);
  if (flowName === "F-06") return entry.path.endsWith("/reactivations");
  return false;
}

function expectedRequestFailure(flowName, entry) {
  if (entry.method === "GET" && /ERR_ABORTED/i.test(entry.error || "")) return true;
  if (flowName === "F-01" && entry.method === "GET" && /ERR_NETWORK_CHANGED/i.test(entry.error || "")) return true;
  if (flowName === "F-05" && entry.method === "POST" && entry.path.endsWith("/api/v1/auth/logout") && /ERR_ABORTED/i.test(entry.error || "")) return true;
  return flowName === "F-05"
    && entry.method === "POST"
    && entry.path.endsWith("/my-feedback/submit")
    && /connectionfailed|ERR_(?:CONNECTION_)?FAILED/i.test(entry.error || "");
}

function assertNoUnexpectedTelemetry(telemetry, checkpoint, flowName) {
  const delta = telemetryDelta(telemetry, checkpoint);
  const unexpectedResponses = delta.response.filter((entry) => !expectedResponse(flowName, entry));
  const unexpectedRequestFailures = delta.requestfailed.filter((entry) => !expectedRequestFailure(flowName, entry));
  const expectedResponseStatuses = new Set(delta.response.filter((entry) => expectedResponse(flowName, entry)).map((entry) => entry.status));
  const hasExpectedDisconnect = delta.requestfailed.some((entry) => expectedRequestFailure(flowName, entry));
  const unexpectedConsole = delta.console.filter((entry) => {
    if (entry.type !== "error") return false;
    if (/Failed to load resource/i.test(entry.text) && [...expectedResponseStatuses].some((status) => entry.text.includes(String(status)))) return false;
    if (hasExpectedDisconnect && /Failed to load resource.*ERR_/i.test(entry.text)) return false;
    return true;
  });

  assert.deepEqual(delta.pageerror, [], `${flowName} raised page errors`);
  assert.deepEqual(unexpectedResponses, [], `${flowName} received unexpected HTTP errors`);
  assert.deepEqual(unexpectedRequestFailures, [], `${flowName} had unexpected request failures`);
  assert.deepEqual(unexpectedConsole, [], `${flowName} wrote unexpected console errors`);
}

async function openCandidateFromList(page, candidateName) {
  await navigate(page, "候选人");
  await page.getByPlaceholder(/搜索姓名/).fill(candidateName);
  const row = page.locator(".candidate-table-row", { hasText: candidateName }).first();
  await row.waitFor({ state: "visible" });
  await row.click();
  await page.getByRole("heading", { name: "候选人详情", exact: true }).waitFor();
  await page.getByRole("heading", { name: new RegExp(`^${escapeRegex(candidateName)}$`) }).waitFor();
}

async function transitionCandidate(page, target, reason = "") {
  await page.getByRole("button", { name: "推进候选人", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "推进候选人状态" });
  await dialog.getByLabel("下一状态").selectOption({ label: target });
  if (reason) await dialog.getByPlaceholder(/操作原因|淘汰原因|状态变更说明/).fill(reason);
  const responsePromise = page.waitForResponse((response) => response.request().method() === "POST" && /\/applications\/[^/]+\/transitions$/.test(responsePath(response)));
  await dialog.getByRole("button", { name: "确认推进", exact: true }).click();
  const response = await responsePromise;
  assert.equal(response.status(), 200, `candidate transition to ${target} returned HTTP ${response.status()}`);
  const data = await responseData(response);
  await page.locator(".candidate-detail-hero").getByText(target, { exact: true }).waitFor();
  return data;
}

async function flow01(page, state, viewportName) {
  const primary = page.getByRole("button", { name: "导入简历", exact: true });
  const secondary = page.getByRole("button", { name: "新建职位", exact: true });
  await primary.waitFor({ state: "visible" });
  await secondary.waitFor({ state: "visible" });
  assert.ok((await primary.getAttribute("class")).includes("primary"), "导入简历 must be the primary workbench action");
  assert.ok((await secondary.getAttribute("class")).includes("secondary"), "新建职位 must remain secondary on the workbench");
  const secondaryElement = await secondary.elementHandle();
  assert.ok(await primary.evaluate((node, other) => Boolean(node.compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING), secondaryElement), "primary action must precede the secondary action in DOM and keyboard order");
  const primaryBox = await primary.boundingBox();
  assert.ok(primaryBox && primaryBox.y >= 0 && primaryBox.y + primaryBox.height <= viewports[viewportName].height, "primary workbench action must be in the first viewport");
  await assertNoOverflow(page);
  await assertKeyboardReachable(page, primary);
  await secondary.click();
  const title = `Final ${viewportName} ${process.env.E2E_PROJECT_NAME.slice(-6)}`;
  await page.getByLabel("职位名称").fill(title);
  await page.getByLabel("工作地点").fill("上海或远程");
  await page.getByLabel("公开 JD").fill("Synthetic role requiring Python and PostgreSQL.");
  await page.getByLabel("必须条件").fill("Python、PostgreSQL");
  await page.getByLabel("加分项").fill("Playwright");
  await page.getByLabel("流程模板").fill("UX-09 synthetic standard");
  const createResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith("/job-definitions"));
  await page.getByRole("button", { name: "发布职位", exact: true }).click();
  const createResponse = await createResponsePromise;
  if (createResponse.status() !== 201) throw blocker(`F-01 job creation returned HTTP ${createResponse.status()}.`);
  const created = await responseData(createResponse);
  state.jobId = created.job.id;
  assert.match(state.jobId, /^[0-9a-f-]{36}$/i, "F-01 job definition response must expose a real job UUID");
  state.jobTitle = title;
  await page.getByRole("heading", { name: title, exact: true }).waitFor();
  await page.getByRole("button", { name: /编辑职位/ }).click();
  await page.getByLabel("工作地点").fill("北京、上海或远程");
  const updateResponsePromise = page.waitForResponse((response) => response.request().method() === "PUT" && /\/job-definitions\/[^/]+$/.test(responsePath(response)));
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  const updateResponse = await updateResponsePromise;
  if (updateResponse.status() !== 200) throw blocker(`F-01 immediate edit returned HTTP ${updateResponse.status()}; create/publish succeeded but edit persistence cannot be accepted.`);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor();
  await navigate(page, "职位");
  const jobRow = page.locator(".job-table-row", { hasText: title }).first();
  await jobRow.waitFor({ state: "visible" });
  await jobRow.getByText("招聘中", { exact: true }).waitFor();
  await jobRow.click();
  await page.getByRole("heading", { name: "职位详情", exact: true }).waitFor();
  await page.getByRole("heading", { name: title, exact: true }).waitFor();
  await page.getByText(/北京、上海或远程/).waitFor();
  await page.getByText("招聘中", { exact: true }).first().waitFor();
  await assertNoOverflow(page);
}

async function flow02(page, state, viewportName) {
  if (!await page.getByRole("heading", { name: "工作台", exact: true }).isVisible()) await navigate(page, "工作台");
  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "导入并筛选简历" });
  await dialog.getByLabel("目标职位").selectOption({ label: state.jobTitle });
  await dialog.getByRole("button", { name: "下一步" }).click();

  const validationResponses = [];
  const captureValidation = async (response) => {
    if (response.request().method() !== "POST" || !/\/screening-runs\/[^/]+\/items$/.test(responsePath(response)) || response.status() !== 422) return;
    const body = await response.json();
    validationResponses.push(body.code);
  };
  page.on("response", captureValidation);
  const preflightFiles = [
    { name: `preflight-valid-${viewportName}.txt`, mimeType: "text/plain", buffer: Buffer.from("Synthetic preflight candidate Python") },
    { name: `preflight-mime-${viewportName}.txt`, mimeType: "application/pdf", buffer: Buffer.from("Synthetic MIME mismatch") },
    { name: `preflight-magic-${viewportName}.pdf`, mimeType: "application/pdf", buffer: Buffer.from("not a PDF") },
    { name: `preflight-size-${viewportName}.txt`, mimeType: "text/plain", buffer: Buffer.alloc(10 * 1024 * 1024 + 1, "x") },
  ];
  await dialog.locator('input[type="file"]').setInputFiles(preflightFiles);
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByRole("button", { name: "创建筛选任务" }).click();
  await page.getByRole("status").filter({ hasText: "3 份简历上传失败" }).waitFor();
  await page.getByRole("heading", { name: /简历筛选任务/ }).waitFor({ timeout: 30_000 });
  await page.getByText("1/1", { exact: true }).first().waitFor({ timeout: 300_000 });
  page.off("response", captureValidation);
  assert.deepEqual(new Set(validationResponses), new Set(["file_type_mismatch", "file_magic_mismatch", "file_too_large"]));
  await page.getByRole("button", { name: "返回来源页面", exact: true }).click();
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor();

  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "导入并筛选简历" });
  await dialog.getByLabel("目标职位").selectOption({ label: state.jobTitle });
  await dialog.getByRole("button", { name: "下一步" }).click();
  const files = Array.from({ length: 17 }, (_, index) => ({
    name: `ux08-${viewportName}-${String(index + 1).padStart(2, "0")}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Synthetic candidate ${index + 1} Python PostgreSQL Playwright`),
  })).concat([{
    name: `ux08-${viewportName}-malware.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from("X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"),
  }]);
  await dialog.locator('input[type="file"]').setInputFiles(files);
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByRole("button", { name: "创建筛选任务" }).click();
  await page.getByRole("heading", { name: /简历筛选任务/ }).waitFor({ timeout: 30_000 });
  await page.getByText("18/18", { exact: true }).first().waitFor({ timeout: 300_000 });
  state.runId = await page.evaluate((jobId) => Object.entries(localStorage)
    .filter(([key]) => key.startsWith("ats_recent_screening_task:user:"))
    .map(([, value]) => { try { return JSON.parse(value); } catch { return null; } })
    .find((value) => value?.serverBacked === true && value.jobId === jobId && typeof value.id === "string")?.id || "", state.jobId);
  assert.match(state.runId, /^[0-9a-f-]{36}$/i);

  const candidateButtons = page.locator("button.screening-identity:not([disabled])");
  const candidateCount = await candidateButtons.count();
  const nonRetryableFailures = await page.locator(".screening-row .file-state", { hasText: /失败/ }).count();
  assert.equal(candidateCount, 17, "F-02 must preserve all 17 clean candidates");
  assert.equal(nonRetryableFailures, 1, "F-02 must retain one visible malicious-file rejection");
  const malwareRow = page.locator(".screening-row", { hasText: `ux08-${viewportName}-malware.txt` });
  await malwareRow.getByText(/恶意文件.*已拒绝/).waitFor();
  assert.equal(await malwareRow.getByRole("button", { name: "重新解析", exact: true }).count(), 0);
  const itemPayload = await page.evaluate(async (runId) => (await fetch(`/api/v1/screening-runs/${runId}/items?limit=100`)).json(), state.runId);
  const malwareItem = itemPayload.data.find((item) => item.filename === `ux08-${viewportName}-malware.txt`);
  assert.equal(malwareItem?.error_code, "malware_detected");
  await page.getByText(/LLM 未启用，规则评分已保留/).first().waitFor();
  const firstCandidateRow = page.locator(".screening-row", { has: candidateButtons.first() });
  assert.notEqual((await firstCandidateRow.locator(".score-source strong").first().innerText()).trim(), "—", "rules-only success must retain its rule score");
  state.candidateName = (await candidateButtons.first().locator("strong").innerText()).trim().replace(/（待核验）$/, "");
  assert.match(state.candidateName, new RegExp(`${escapeRegex(viewportName)}-\\d{2}$`), "candidate name must retain the synthetic filename suffix used for deterministic lookup");

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor();
  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  await page.getByRole("button", { name: /继续最近的筛选任务/ }).click();
  await page.getByText(state.runId, { exact: false }).waitFor();
  await page.locator("button.screening-identity:not([disabled])", { hasText: state.candidateName }).waitFor();
  await assertNoOverflow(page);
}

async function openFirstCandidate(page, state) {
  const candidateButton = page.locator("button.screening-identity:not([disabled])", { hasText: state.candidateName }).first();
  if (!await candidateButton.count()) throw blocker("F-03 has no candidate record from the completed F-02 server run.");
  await candidateButton.click();
  await page.getByRole("heading", { name: "候选人详情", exact: true }).waitFor();
}

async function flow03(page, state, viewportName, telemetry) {
  if (!state.runId || !state.candidateName) throw blocker("F-03 cannot start because F-02 did not persist a candidate.");
  const screeningRow = page.locator(".screening-row", { hasText: state.candidateName }).first();
  const screeningCheckbox = screeningRow.getByRole("checkbox", { name: `选择 ${state.candidateName}` });
  await screeningCheckbox.check();
  const bulkAdvancePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith(`/screening-runs/${state.runId}/bulk-actions`));
  await page.getByRole("button", { name: "推进到待复核", exact: true }).click();
  const bulkAdvanceResponse = await bulkAdvancePromise;
  assert.equal(bulkAdvanceResponse.status(), 200);
  assert.equal((await responseData(bulkAdvanceResponse)).command, "advance_to_review");
  const undoBulk = page.getByRole("button", { name: "撤销批量推进", exact: true });
  await undoBulk.waitFor({ state: "visible" });
  const bulkUndoPromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith(`/screening-runs/${state.runId}/bulk-actions`));
  await undoBulk.click();
  const bulkUndoResponse = await bulkUndoPromise;
  assert.equal(bulkUndoResponse.status(), 200);
  assert.equal((await responseData(bulkUndoResponse)).command, "undo_advance_to_new");
  await page.waitForFunction((candidateName) => [...document.querySelectorAll(".screening-row")].some((row) => row.textContent.includes(candidateName) && row.querySelector('input[type="checkbox"]')?.disabled === false), state.candidateName);

  await openFirstCandidate(page, state);
  await page.getByText("新简历", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "筛选证据", exact: true }).click();
  await page.getByRole("button", { name: "建议推进", exact: true }).click();
  await page.getByPlaceholder("补充人工判断依据").fill("Synthetic human review conclusion");
  const conclusionResponsePromise = page.waitForResponse((response) => response.request().method() === "PATCH" && /\/applications\/[^/]+$/.test(responsePath(response)));
  await page.getByRole("button", { name: "保存人工结论", exact: true }).click();
  const conclusionResponse = await conclusionResponsePromise;
  assert.equal(conclusionResponse.status(), 200);
  const conclusion = await responseData(conclusionResponse);
  state.applicationId = conclusion.id;
  state.candidateId = conclusion.candidate_id;
  state.resumeId = conclusion.resume_id;
  assert.match(conclusion.human_conclusion, /^建议推进：Synthetic human review conclusion$/);

  const duplicateApplicationContext = await chromium.launchPersistentContext(path.join(process.env.E2E_BROWSER_PROFILE, `${viewportName}-duplicate-application`), {
    headless: true,
    viewport: viewports[viewportName],
  });
  const duplicateApplicationPage = duplicateApplicationContext.pages()[0] || await duplicateApplicationContext.newPage();
  try {
    const recruiterLoginResponse = await duplicateApplicationContext.request.post(`${process.env.E2E_BASE_URL}/api/v1/auth/login`, {
      headers: { Origin: process.env.E2E_WEB_URL },
      data: { organization_slug: "final-e2e", email: process.env.E2E_RECRUITER_EMAIL, password: process.env.E2E_RECRUITER_PASSWORD },
    });
    assert.equal(recruiterLoginResponse.status(), 200);
    const recruiterMeResponse = await duplicateApplicationContext.request.get(`${process.env.E2E_BASE_URL}/api/v1/me`, {
      headers: { Origin: process.env.E2E_WEB_URL, "Sec-Fetch-Site": "same-site" },
    });
    assert.equal(recruiterMeResponse.status(), 200);
    const recruiterId = (await recruiterMeResponse.json()).data?.id;
    assert.ok(recruiterId);
    const loginResponse = await duplicateApplicationContext.request.post(`${process.env.E2E_BASE_URL}/api/v1/auth/login`, {
      headers: { Origin: process.env.E2E_WEB_URL },
      data: { organization_slug: "final-e2e", email: process.env.E2E_ADMIN_EMAIL, password: process.env.E2E_ADMIN_PASSWORD },
    });
    assert.equal(loginResponse.status(), 200);
    const csrf = loginResponse.headers()["x-csrf-token"];
    assert.ok(csrf);
    const duplicateApplication = await duplicateApplicationContext.request.post(`${process.env.E2E_BASE_URL}/api/v1/jobs/${state.jobId}/applications`, {
      headers: {
        "Idempotency-Key": `${process.env.E2E_PROJECT_NAME}-${viewportName}-duplicate-application`,
        "X-CSRF-Token": csrf,
        Origin: process.env.E2E_WEB_URL,
      },
      data: { candidate_id: state.candidateId, resume_id: state.resumeId, owner_id: recruiterId, source: "manual_duplicate_probe" },
    });
    assert.equal(duplicateApplication.status(), 409);
    assert.equal((await duplicateApplication.json()).code, "active_application_exists");
  } finally {
    await duplicateApplicationContext.close();
  }

  const staleContext = await chromium.launchPersistentContext(path.join(process.env.E2E_BROWSER_PROFILE, `${viewportName}-stale`), {
    headless: true,
    viewport: viewports[viewportName],
  });
  const stalePage = staleContext.pages()[0] || await staleContext.newPage();
  try {
    await login(stalePage);
    observe(stalePage, telemetry);
    await openCandidateFromList(stalePage, state.candidateName);

    const firstTransition = await transitionCandidate(page, "待复核");
    assert.equal(firstTransition.stage, "review");

    await stalePage.getByRole("button", { name: "推进候选人", exact: true }).first().click();
    const staleDialog = stalePage.getByRole("dialog", { name: "推进候选人状态" });
    await staleDialog.getByLabel("下一状态").selectOption({ label: "待复核" });
    const staleResponsePromise = stalePage.waitForResponse((response) => response.request().method() === "POST" && /\/applications\/[^/]+\/transitions$/.test(responsePath(response)));
    await staleDialog.getByRole("button", { name: "确认推进", exact: true }).click();
    const staleResponse = await staleResponsePromise;
    assert.equal(staleResponse.status(), 409, "the second page must prove a real stale-version conflict");
    await staleDialog.getByRole("heading", { name: "候选人状态已被其他成员更新" }).waitFor();
    await staleDialog.getByRole("button", { name: "刷新最新详情", exact: true }).click();
    await stalePage.getByText("待复核", { exact: true }).first().waitFor();
  } finally {
    await staleContext.close();
  }

  const contact = await transitionCandidate(page, "待沟通");
  assert.equal(contact.stage, "contact");
  const pending = await transitionCandidate(page, "待安排");
  assert.equal(pending.stage, "interview_pending");
  state.applicationVersion = pending.version;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor();
  await openCandidateFromList(page, state.candidateName);
  await page.getByText("待安排", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "筛选证据", exact: true }).click();
  await page.getByText("Synthetic human review conclusion", { exact: true }).waitFor();
}

async function advanceScheduleCollaboration(page) {
  const check = page.getByRole("button", { name: /检查时间并继续|确认覆盖并继续/ });
  const responsePromise = page.waitForResponse((response) => response.request().method() === "POST" && /\/interview(?:-conflicts|s\/[^/]+\/conflicts)$/.test(responsePath(response)));
  await check.click();
  const response = await responsePromise;
  assert.equal(response.status(), 200, `interview conflict check returned HTTP ${response.status()}`);
  const override = page.getByRole("checkbox", { name: /确认保留该时间并继续/ });
  if (await override.isVisible()) {
    await override.check();
    const overrideResponsePromise = page.waitForResponse((item) => item.request().method() === "POST" && /\/interview(?:-conflicts|s\/[^/]+\/conflicts)$/.test(responsePath(item)));
    await page.getByRole("button", { name: "确认覆盖并继续", exact: true }).click();
    assert.equal((await overrideResponsePromise).status(), 200);
  }
  await page.getByRole("heading", { name: "确认邀请", exact: true }).waitFor();
}

async function readDownload(download) {
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

function parseIcs(text) {
  assert.match(text, /BEGIN:VCALENDAR/);
  assert.match(text, /BEGIN:VEVENT/);
  const unfolded = text.replace(/\r?\n[ \t]/g, "");
  const fields = {};
  for (const line of unfolded.split(/\r?\n/)) {
    const separator = line.indexOf(":");
    if (separator < 0) continue;
    const key = line.slice(0, separator).split(";")[0];
    if (["UID", "DTSTART", "DTEND", "SUMMARY", "SEQUENCE"].includes(key)) fields[key] = line.slice(separator + 1);
  }
  for (const field of ["UID", "DTSTART", "DTEND", "SUMMARY", "SEQUENCE"]) assert.ok(fields[field], `ICS field ${field} is required`);
  return fields;
}

async function interviewRow(page, candidateName) {
  await page.getByLabel("日期筛选").selectOption({ label: "全部日期" });
  const row = page.locator(".interview-table-row", { hasText: candidateName }).first();
  await row.waitFor({ state: "visible" });
  return row;
}

async function downloadInterviewCalendar(page, row) {
  const downloadPromise = page.waitForEvent("download");
  await row.getByRole("button", { name: "日历", exact: true }).click();
  return parseIcs(await readDownload(await downloadPromise));
}

async function flow04(page, state, viewportName) {
  if (!state.candidateName || !state.applicationId) throw blocker("F-04 cannot start without the persisted F-03 application.");
  await page.getByRole("button", { name: "面试与反馈", exact: true }).click();
  const schedule = page.getByRole("button", { name: "安排面试", exact: true }).first();
  await schedule.waitFor({ state: "visible" });
  await schedule.click();
  await page.getByRole("heading", { name: "安排面试", exact: true }).first().waitFor();

  const firstDate = futureDate(viewportName === "desktop" ? 30 : 40);
  await page.getByLabel("日期").fill(firstDate);
  await page.getByLabel("开始时间（小时）").selectOption("10");
  await page.getByLabel("开始时间（分钟）").selectOption("00");
  await page.getByRole("button", { name: /下一步：面试协同/ }).click();
  const interviewer = page.getByRole("checkbox", { name: /Final E2E Interviewer/ });
  await interviewer.waitFor({ state: "visible" });
  if (!await interviewer.isChecked()) await interviewer.check();
  await page.getByLabel("会议链接").fill(`https://meeting.example.test/${viewportName}`);
  await advanceScheduleCollaboration(page);
  const createResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith("/api/v1/interviews"));
  await page.getByRole("button", { name: "确认并保存", exact: true }).click();
  const createResponse = await createResponsePromise;
  assert.equal(createResponse.status(), 201);
  const created = await responseData(createResponse);
  assert.equal(created.application_id, state.applicationId);
  state.interviewId = created.id;
  state.interviewVersion = created.version;
  state.interviewSequence = created.calendar_sequence;
  await page.getByRole("heading", { name: "面试", exact: true }).first().waitFor();
  let row = await interviewRow(page, state.candidateName);
  const firstCalendar = await downloadInterviewCalendar(page, row);
  assert.equal(Number(firstCalendar.SEQUENCE), created.calendar_sequence);

  await row.getByRole("button", { name: "改期", exact: true }).click();
  await page.getByRole("heading", { name: "改期面试", exact: true }).first().waitFor();
  const secondDate = futureDate(viewportName === "desktop" ? 31 : 41);
  await page.getByLabel("日期").fill(secondDate);
  await page.getByRole("button", { name: /下一步：面试协同/ }).click();
  await page.getByRole("checkbox", { name: /Final E2E Interviewer/ }).waitFor({ state: "visible" });
  await advanceScheduleCollaboration(page);
  const patchResponsePromise = page.waitForResponse((response) => response.request().method() === "PATCH" && responsePath(response).endsWith(`/interviews/${state.interviewId}`));
  await page.getByRole("button", { name: "确认并保存", exact: true }).click();
  const patchResponse = await patchResponsePromise;
  assert.equal(patchResponse.status(), 200);
  const rescheduled = await responseData(patchResponse);
  assert.ok(rescheduled.version > state.interviewVersion);
  assert.ok(rescheduled.calendar_sequence > state.interviewSequence, "reschedule must preserve history by advancing calendar_sequence");
  row = await interviewRow(page, state.candidateName);
  const secondCalendar = await downloadInterviewCalendar(page, row);
  assert.notEqual(secondCalendar.DTSTART, firstCalendar.DTSTART);
  assert.equal(Number(secondCalendar.SEQUENCE), rescheduled.calendar_sequence);

  let transitionResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith(`/interviews/${state.interviewId}/transitions`));
  await row.getByRole("button", { name: "确认", exact: true }).click();
  let transitionResponse = await transitionResponsePromise;
  assert.equal(transitionResponse.status(), 200);
  assert.equal((await responseData(transitionResponse)).status, "confirmed");
  row = await interviewRow(page, state.candidateName);
  transitionResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith(`/interviews/${state.interviewId}/transitions`));
  await row.getByRole("button", { name: "完成面试", exact: true }).click();
  transitionResponse = await transitionResponsePromise;
  assert.equal(transitionResponse.status(), 200);
  assert.equal((await responseData(transitionResponse)).status, "pending_feedback");
  row = await interviewRow(page, state.candidateName);
  await row.getByText("待反馈", { exact: true }).waitFor();
}

async function flow05(page, state, viewportName, telemetry) {
  if (!state.interviewId) throw blocker("F-05 cannot start without the F-04 interview.");
  await switchAccount(page, process.env.E2E_INTERVIEWER_EMAIL, process.env.E2E_INTERVIEWER_PASSWORD);
  const task = page.locator(".interviewer-workbench .rail-item", { hasText: state.candidateName });
  await task.waitFor({ state: "visible" });
  const initialFeedbackPromise = page.waitForResponse((response) => response.request().method() === "GET" && responsePath(response).endsWith(`/interviews/${state.interviewId}/my-feedback`));
  await task.click();
  assert.equal((await initialFeedbackPromise).status(), 200);
  await page.getByRole("heading", { name: state.candidateName, exact: true }).waitFor();
  await page.getByRole("button", { name: "提交反馈", exact: true }).waitFor();

  await page.locator(".rating-row", { hasText: "专业能力" }).getByRole("button", { name: "良好", exact: true }).click();
  await page.getByPlaceholder("记录与岗位相关的优势和证据").fill("Synthetic draft strength restored");
  await page.waitForFunction(({ interviewId, marker }) => Object.entries(localStorage).some(([key, value]) => key.includes(interviewId) && value.includes(marker)), { interviewId: state.interviewId, marker: "Synthetic draft strength restored" });
  await page.getByRole("button", { name: "返回面试列表", exact: true }).click();
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor();
  const restoredFeedbackPromise = page.waitForResponse((response) => response.request().method() === "GET" && responsePath(response).endsWith(`/interviews/${state.interviewId}/my-feedback`));
  await page.locator(".interviewer-workbench .rail-item", { hasText: state.candidateName }).click();
  assert.equal((await restoredFeedbackPromise).status(), 200);
  await page.getByPlaceholder("记录与岗位相关的优势和证据").waitFor();
  assert.equal(await page.getByPlaceholder("记录与岗位相关的优势和证据").inputValue(), "Synthetic draft strength restored");

  const unassignedContext = await chromium.launchPersistentContext(path.join(process.env.E2E_BROWSER_PROFILE, `${viewportName}-unassigned`), {
    headless: true,
    viewport: viewports[viewportName],
  });
  const unassignedPage = unassignedContext.pages()[0] || await unassignedContext.newPage();
  try {
    await login(unassignedPage, process.env.E2E_UNASSIGNED_INTERVIEWER_EMAIL, process.env.E2E_UNASSIGNED_INTERVIEWER_PASSWORD);
    observe(unassignedPage, telemetry);
    assert.equal(await unassignedPage.locator(".interviewer-workbench .rail-item", { hasText: state.candidateName }).count(), 0, "unassigned interviewer must not enumerate the candidate task");
    const forbiddenFeedback = await unassignedContext.request.get(`${process.env.E2E_BASE_URL}/api/v1/interviews/${state.interviewId}/my-feedback`);
    assert.equal(forbiddenFeedback.status(), 404, "unassigned interviewer must not read another interviewer's feedback");
  } finally {
    await unassignedContext.close();
  }

  for (const label of ["问题解决", "沟通协作", "岗位匹配"]) await page.locator(".rating-row", { hasText: label }).getByRole("button", { name: "良好", exact: true }).click();
  await page.getByPlaceholder("记录风险、信息缺口或后续建议").fill("Synthetic risk for HR review");
  await page.getByRole("button", { name: "推荐", exact: true }).click();
  await page.getByPlaceholder(/给 HR 或下一轮面试官/).fill("Synthetic interviewer note");

  await page.route("**/api/v1/interviews/*/my-feedback/submit", async (route) => {
    await route.fetch();
    await route.abort("connectionfailed");
  }, { times: 1 });
  const firstRequestPromise = page.waitForRequest((request) => request.method() === "POST" && responsePath({ url: () => request.url() }).endsWith("/my-feedback/submit"));
  await page.getByRole("button", { name: "提交反馈", exact: true }).click();
  const firstRequest = await firstRequestPromise;
  const firstKey = await firstRequest.headerValue("idempotency-key");
  assert.ok(firstKey);
  await page.getByRole("alert").filter({ hasText: "反馈请求失败" }).waitFor();

  const retryResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith("/my-feedback/submit"));
  await page.getByRole("button", { name: "重试提交", exact: true }).click();
  const retryResponse = await retryResponsePromise;
  assert.equal(retryResponse.status(), 200);
  assert.equal(await retryResponse.request().headerValue("idempotency-key"), firstKey, "ambiguous feedback retry must reuse the first idempotency-key");
  const feedback = await responseData(retryResponse);
  assert.equal(feedback.status, "submitted");
  await page.getByText("已提交", { exact: true }).first().waitFor();

  await switchAccount(page, process.env.E2E_ADMIN_EMAIL, process.env.E2E_ADMIN_PASSWORD);
  await navigate(page, "面试");
  await page.getByLabel("日期筛选").selectOption({ label: "全部日期" });
  await page.getByLabel("搜索面试").fill(state.candidateName);
  const row = page.locator(".interview-table-row", { hasText: state.candidateName }).first();
  await row.waitFor({ state: "visible" });
  await row.getByRole("button", { name: "查看反馈", exact: true }).click();
  await page.getByText(/Synthetic draft strength restored/).waitFor();
  await page.getByText(/草稿对其他人不可见/).waitFor();
  await openCandidateFromList(page, state.candidateName);
  await page.getByText("待决策", { exact: true }).first().waitFor();
}

async function openTalentMember(page, state) {
  await navigate(page, "人才库");
  const poolRow = page.locator(".pool-table-row", { hasText: state.poolName }).first();
  await poolRow.waitFor({ state: "visible" });
  await poolRow.click();
  await page.getByRole("heading", { name: state.poolName, exact: true }).waitFor();
  await page.getByLabel("搜索人才").fill(state.candidateName);
  const person = page.locator("button.talent-person", { hasText: state.candidateName }).first();
  await person.waitFor({ state: "visible" });
  await person.click();
  await page.locator('aside[aria-label="人才详情"]').waitFor();
}

async function flow06(page, state, viewportName, telemetry) {
  if (!state.candidateName || !state.applicationId) throw blocker("F-06 cannot start without the reviewed application.");
  await navigate(page, "人才库");
  state.poolName = `Final Pool ${viewportName} ${process.env.E2E_PROJECT_NAME.slice(-6)}`;
  await page.getByRole("button", { name: "新建人才库", exact: true }).click();
  const poolDialog = page.getByRole("dialog", { name: "新建人才库" });
  await poolDialog.getByLabel("人才库名称").fill(state.poolName);
  await poolDialog.getByLabel("用途说明").fill("Synthetic F-06 reactivation evidence");
  await poolDialog.getByLabel("适合岗位").fill("Python 工程师");
  const poolResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith("/api/v1/talent-pools"));
  await poolDialog.getByRole("button", { name: "创建人才库", exact: true }).click();
  const poolResponse = await poolResponsePromise;
  assert.equal(poolResponse.status(), 201);
  const pool = await responseData(poolResponse);
  state.poolId = pool.id;

  await openCandidateFromList(page, state.candidateName);
  const rejected = await transitionCandidate(page, "已淘汰", "Synthetic terminal decision for talent reactivation");
  assert.equal(rejected.stage, "rejected");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor();
  await openCandidateFromList(page, state.candidateName);
  await page.getByText("已淘汰", { exact: true }).first().waitFor();

  await page.getByRole("button", { name: "加入人才库", exact: true }).click();
  const addDialog = page.getByRole("dialog", { name: "加入人才库" });
  await addDialog.getByLabel("目标人才库").selectOption({ label: state.poolName });
  const membershipResponsePromise = page.waitForResponse((response) => response.request().method() === "POST" && /\/talent-pools\/[^/]+\/memberships$/.test(responsePath(response)));
  await addDialog.getByRole("button", { name: "确认加入", exact: true }).click();
  const membershipResponse = await membershipResponsePromise;
  assert.equal(membershipResponse.status(), 201);
  const membership = await responseData(membershipResponse);
  assert.equal(membership.source_application?.id, state.applicationId);
  state.membershipId = membership.id;

  let concurrentContext;
  try {
  await openTalentMember(page, state);
  await page.locator('aside[aria-label="人才详情"]').getByRole("button", { name: "加入职位", exact: true }).click();
  const reactivate = page.locator('aside[aria-label="重新激活候选人"]');
  await reactivate.waitFor();
  assert.notEqual(process.env.E2E_JOB_TITLE, state.jobTitle);
  const targetJobOption = reactivate.getByLabel("目标职位").locator("option").filter({ hasText: new RegExp(`^${escapeRegex(process.env.E2E_JOB_TITLE)}\\s*·`) }).first();
  await reactivate.getByLabel("目标职位").selectOption(await targetJobOption.getAttribute("value"));

  concurrentContext = await chromium.launchPersistentContext(path.join(process.env.E2E_BROWSER_PROFILE, `${viewportName}-concurrent-reactivation`), {
    headless: true,
    viewport: viewports[viewportName],
  });
  const concurrentPage = concurrentContext.pages()[0] || await concurrentContext.newPage();
  await login(concurrentPage);
  observe(concurrentPage, telemetry);
  await openTalentMember(concurrentPage, state);
  await concurrentPage.locator('aside[aria-label="人才详情"]').getByRole("button", { name: "加入职位", exact: true }).click();
  const concurrentDrawer = concurrentPage.locator('aside[aria-label="重新激活候选人"]');
  await concurrentDrawer.waitFor();
  const concurrentTargetJobOption = concurrentDrawer.getByLabel("目标职位").locator("option").filter({ hasText: new RegExp(`^${escapeRegex(process.env.E2E_JOB_TITLE)}\\s*·`) }).first();
  await concurrentDrawer.getByLabel("目标职位").selectOption(await concurrentTargetJobOption.getAttribute("value"));

  const pages = [page, concurrentPage];
  const drawers = [reactivate, concurrentDrawer];
  const responsePromises = pages.map((candidatePage) => candidatePage.waitForResponse((response) => response.request().method() === "POST" && responsePath(response).endsWith("/reactivations")));
  await Promise.all(drawers.map((drawer) => drawer.getByRole("button", { name: "创建新申请", exact: true }).click()));
  const reactivationResponses = await Promise.all(responsePromises);
  assert.deepEqual(reactivationResponses.map((response) => response.status()).sort(), [201, 409], "concurrent reactivation must create exactly one active application");
  const winnerIndex = reactivationResponses.findIndex((response) => response.status() === 201);
  const loserIndex = winnerIndex === 0 ? 1 : 0;
  const reactivateResponse = reactivationResponses[winnerIndex];
  const activePage = pages[winnerIndex];
  const activeDrawer = drawers[winnerIndex];
  const duplicateDrawer = drawers[loserIndex];
  await duplicateDrawer.getByRole("alert").filter({ hasText: "已有进行中的申请" }).waitFor();
  const application = await responseData(reactivateResponse);
  assert.equal(application.candidate_id, state.candidateId);
  assert.equal(application.source_application_id, state.applicationId);
  assert.equal(application.source, "talent_pool_reactivation");
  assert.equal(application.stage, "new");
  state.reactivatedApplicationId = application.id;
  const success = activeDrawer.locator(".reactivation-success");
  await success.waitFor();
  const goToApplication = success.getByRole("button", { name: "去新申请", exact: true });
  assert.ok((await goToApplication.getAttribute("class")).includes("primary"), "去新申请 must remain the primary success action");
  assert.ok((await success.getByRole("button", { name: "返回人才库", exact: true }).getAttribute("class")).includes("secondary"), "返回人才库 must remain secondary");
  const applicationListPromise = activePage.waitForResponse((response) => response.request().method() === "GET" && responsePath(response).endsWith(`/candidates/${state.candidateId}/applications`));
  await goToApplication.click();
  const applicationListResponse = await applicationListPromise;
  assert.equal(applicationListResponse.status(), 200);
  const applicationList = await applicationListResponse.json();
  assert.ok(applicationList.data.some((item) => item.id === state.reactivatedApplicationId && item.stage === "new"), "去新申请 must load the newly reactivated application");
  await activePage.getByRole("heading", { name: "候选人详情", exact: true }).waitFor();
  await activePage.getByRole("button", { name: "职位申请", exact: true }).click();
  const applicationsTable = activePage.locator(".applications-table");
  await applicationsTable.getByText(process.env.E2E_JOB_TITLE, { exact: true }).waitFor();
  await applicationsTable.getByText(state.jobTitle, { exact: true }).waitFor();
  await applicationsTable.getByText("talent_pool_reactivation", { exact: true }).waitFor();
  await activePage.getByText("新简历", { exact: true }).first().waitFor();

  await activePage.reload({ waitUntil: "domcontentloaded" });
  await activePage.getByRole("heading", { name: "工作台", exact: true }).waitFor();
  await openCandidateFromList(activePage, state.candidateName);
  await activePage.getByRole("button", { name: "职位申请", exact: true }).click();
  const refreshedApplications = activePage.locator(".applications-table");
  await refreshedApplications.getByText(process.env.E2E_JOB_TITLE, { exact: true }).waitFor();
  await refreshedApplications.getByText(state.jobTitle, { exact: true }).waitFor();
  await refreshedApplications.getByText("talent_pool_reactivation", { exact: true }).waitFor();
  await assertNoOverflow(activePage);
  } finally {
    await concurrentContext?.close();
  }
}

async function runViewport(viewportName, viewport) {
  const context = await chromium.launchPersistentContext(path.join(process.env.E2E_BROWSER_PROFILE, viewportName), {
    headless: true,
    viewport,
    acceptDownloads: true,
  });
  const page = context.pages()[0] || await context.newPage();
  const state = {};
  await login(page);
  const telemetry = observe(page);
  for (const flow of flows) {
    const label = `${viewportName}-${flow.name}`;
    const checkpoint = telemetryCheckpoint(telemetry);
    try {
      await flow.run(page, state, viewportName, telemetry);
      await assertNoOverflow(page);
      assertNoUnexpectedTelemetry(telemetry, checkpoint, flow.name);
      results.push({ viewport: viewportName, flow: flow.name, status: "passed" });
    } catch (error) {
      const stackLocation = String(error.stack || "").split("\n").slice(1, 3).join("\n");
      results.push({ viewport: viewportName, flow: flow.name, status: error.code === "PRODUCT_BLOCKER" ? "blocked" : "failed", detail: `${error.message}${stackLocation ? `\n${stackLocation}` : ""}` });
      await captureFailure(page, label, telemetry);
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
