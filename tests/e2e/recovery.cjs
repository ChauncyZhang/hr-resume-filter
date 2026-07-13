const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

const REQUIRED_ENVIRONMENT = [
  "E2E_WEB_URL",
  "E2E_BASE_URL",
  "E2E_ADMIN_EMAIL",
  "E2E_ADMIN_PASSWORD",
  "E2E_JOB_TITLE",
  "E2E_PROJECT_NAME",
  "E2E_COMPOSE_BASE",
  "E2E_COMPOSE_OVERRIDE",
  "E2E_BROWSER_PROFILE",
];

for (const name of REQUIRED_ENVIRONMENT) {
  assert.ok(process.env[name], `${name} is required`);
}

const expectedCount = 100;
const terminalStatuses = new Set(["completed", "partial", "failed", "cancelled"]);

function compose(...args) {
  return execFileSync(
    "docker",
    [
      "compose",
      "-p",
      process.env.E2E_PROJECT_NAME,
      "-f",
      process.env.E2E_COMPOSE_BASE,
      "-f",
      process.env.E2E_COMPOSE_OVERRIDE,
      ...args,
    ],
    { encoding: "utf8", env: process.env, stdio: ["ignore", "pipe", "pipe"] },
  );
}

async function waitForReady() {
  const deadline = Date.now() + 90_000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${process.env.E2E_BASE_URL}/health/ready`);
      if (response.ok) return;
      lastError = new Error(`readiness returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`API did not recover: ${lastError?.message || "unknown error"}`);
}

async function login(page) {
  await page.goto(process.env.E2E_WEB_URL, { waitUntil: "domcontentloaded" });
  await page.getByLabel("组织标识").fill("phase3-e2e");
  await page.getByLabel("工作邮箱").fill(process.env.E2E_ADMIN_EMAIL);
  await page.getByLabel("密码").fill(process.env.E2E_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("heading", { name: "工作台", exact: true }).waitFor({ timeout: 30_000 });
}

async function createRun(page) {
  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导入并筛选简历" });
  await dialog.getByLabel("目标职位").selectOption({ label: process.env.E2E_JOB_TITLE });
  await dialog.getByRole("button", { name: "下一步" }).click();
  const files = Array.from({ length: expectedCount }, (_, index) => ({
    name: `phase3-candidate-${String(index + 1).padStart(3, "0")}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Candidate ${String(index + 1).padStart(3, "0")} Python PostgreSQL Docker ${index + 1} years`),
  }));
  await dialog.locator('input[type="file"]').setInputFiles(files);
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByRole("button", { name: "创建筛选任务" }).click();
  await page.getByRole("heading", { name: /简历筛选任务/ }).waitFor({ timeout: 30_000 });

  const recentTask = await page.evaluate(() => {
    const entry = Object.entries(window.localStorage)
      .find(([key]) => key.startsWith("ats_recent_screening_task:user:"));
    return entry ? JSON.parse(entry[1]) : null;
  });
  assert.ok(recentTask?.id, "the real client must persist a recent screening run ID");
  await page.getByText(recentTask.id, { exact: false }).waitFor();
  return recentTask.id;
}

async function resumeRun(page, runId) {
  await page.goto(process.env.E2E_WEB_URL, { waitUntil: "domcontentloaded" });
  const loginHeading = page.getByRole("heading", { name: "登录工作台", exact: true });
  const workbenchHeading = page.getByRole("heading", { name: "工作台", exact: true });
  let needsLogin = false;
  try {
    await loginHeading.waitFor({ timeout: 5_000 });
    needsLogin = true;
  } catch {
    // The session cookie survived; wait for the authenticated workbench below.
  }
  if (needsLogin) {
    await login(page);
  } else {
    await workbenchHeading.waitFor({ timeout: 30_000 });
  }
  await page.getByRole("button", { name: "导入简历", exact: true }).click();
  const banner = page.getByRole("button", { name: /继续最近的筛选任务/ });
  await banner.waitFor();
  await assert.doesNotReject(async () => {
    assert.match(await banner.innerText(), new RegExp(runId));
  });
  await banner.click();
  await page.getByText(runId, { exact: false }).waitFor();

  const deadline = Date.now() + 600_000;
  let run;
  while (Date.now() < deadline) {
    run = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/screening-runs/${id}`, { credentials: "include" });
      if (!response.ok) throw new Error(`run read returned ${response.status}`);
      return (await response.json()).data;
    }, runId);
    if (terminalStatuses.has(run.status)) break;
    await page.waitForTimeout(1_000);
  }
  assert.equal(run?.status, "completed", `expected completed run, received ${run?.status}`);
  assert.equal(run.total_count, expectedCount);
  assert.equal(run.processed_count, expectedCount);
  await page.getByText("已完成", { exact: true }).waitFor({ timeout: 10_000 });
}

function readDurableFacts(runId) {
  assert.match(runId, /^[0-9a-f-]{36}$/i, "run ID must be a UUID before SQL interpolation");
  const sql = `WITH facts AS (
    SELECT
      (SELECT count(*) FROM screening_items WHERE run_id = '${runId}')::int AS items,
      (SELECT count(DISTINCT id) FROM screening_items WHERE run_id = '${runId}')::int AS unique_items,
      (SELECT count(DISTINCT candidate_id) FROM screening_items WHERE run_id = '${runId}' AND candidate_id IS NOT NULL)::int AS candidates,
      (SELECT count(DISTINCT application_id) FROM screening_items WHERE run_id = '${runId}' AND application_id IS NOT NULL)::int AS applications,
      (SELECT count(*) FROM applications a JOIN screening_items i ON i.application_id = a.id WHERE i.run_id = '${runId}' AND a.stage = 'new')::int AS new_applications,
      (SELECT count(*) FROM applications a JOIN screening_items i ON i.application_id = a.id WHERE i.run_id = '${runId}' AND a.stage <> 'new')::int AS non_new_applications,
      (SELECT count(*) FROM screening_results r JOIN screening_items i ON i.id = r.item_id WHERE i.run_id = '${runId}')::int AS results,
      (SELECT count(*) FROM background_jobs j WHERE j.payload->>'screening_item_id' IN (SELECT id::text FROM screening_items WHERE run_id = '${runId}'))::int AS jobs,
      (SELECT count(DISTINCT dedupe_key) FROM background_jobs j WHERE j.payload->>'screening_item_id' IN (SELECT id::text FROM screening_items WHERE run_id = '${runId}'))::int AS unique_jobs
  ) SELECT row_to_json(facts) FROM facts;`;
  const output = compose(
    "exec", "-T", "postgres", "psql", "-U", process.env.POSTGRES_USER,
    "-d", process.env.POSTGRES_DB, "-At", "-c", sql,
  ).trim();
  return JSON.parse(output);
}

function verifyStoredObjects(runId) {
  const output = compose(
    "run", "--rm", "--no-deps", "e2e-prepare",
    "python", "/opt/ux09/e2e/verify_objects.py", runId, String(expectedCount),
  ).trim();
  return JSON.parse(output);
}

async function main() {
  let context;
  try {
    context = await chromium.launchPersistentContext(process.env.E2E_BROWSER_PROFILE, {
      headless: true,
      viewport: { width: 1440, height: 1024 },
    });
    let page = context.pages()[0] || await context.newPage();
    await login(page);
    compose("stop", "worker");
    const runId = await createRun(page);
    const queuedFacts = readDurableFacts(runId);
    assert.equal(queuedFacts.items, expectedCount);
    assert.equal(queuedFacts.candidates, 0, "worker must not process candidates before restart");
    assert.equal(queuedFacts.results, 0, "worker must not score items before restart");
    console.log(`Created screening run ${runId} with ${queuedFacts.items} durable items while worker is stopped; closing browser.`);
    await context.close();
    context = null;

    compose("restart", "api");
    await waitForReady();
    compose("start", "worker");

    context = await chromium.launchPersistentContext(process.env.E2E_BROWSER_PROFILE, {
      headless: true,
      viewport: { width: 1440, height: 1024 },
    });
    page = context.pages()[0] || await context.newPage();
    await resumeRun(page, runId);
    const facts = readDurableFacts(runId);
    assert.deepEqual(
      { items: facts.items, unique_items: facts.unique_items, candidates: facts.candidates, applications: facts.applications, results: facts.results },
      { items: expectedCount, unique_items: expectedCount, candidates: expectedCount, applications: expectedCount, results: expectedCount },
    );
    assert.equal(facts.new_applications, expectedCount, "all recovered applications must remain in stage=new");
    assert.equal(facts.non_new_applications, 0, "recovery must not advance application stages");
    assert.equal(facts.jobs, facts.unique_jobs, "queue dedupe keys must remain unique after restart");
    const objects = verifyStoredObjects(runId);
    assert.equal(objects.objects, expectedCount);
    console.log(`Recovered ${runId}: ${JSON.stringify(facts)}; MinIO=${JSON.stringify(objects)}`);
  } finally {
    await context?.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
