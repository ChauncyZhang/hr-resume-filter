const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const configuredUrl = process.env.UX09_PRODUCTION_URL;
assert.ok(configuredUrl, "UX09_PRODUCTION_URL is required");
const baseUrl = new URL(configuredUrl);
assert.equal(baseUrl.protocol !== "https:", false, "UX09_PRODUCTION_URL must use HTTPS");
assert.equal(baseUrl.username, "", "UX09_PRODUCTION_URL must not contain credentials");
assert.equal(baseUrl.password, "", "UX09_PRODUCTION_URL must not contain credentials");
assert.equal(baseUrl.search, "", "UX09_PRODUCTION_URL must not contain a query string");
assert.equal(baseUrl.hash, "", "UX09_PRODUCTION_URL must not contain a fragment");

const artifactDir = path.resolve(
  process.env.UX09_PRODUCTION_SMOKE_ARTIFACT_DIR || ".tmp/production-smoke",
);
const telemetry = [];
let browser;
let page;

function safePath(value) {
  try {
    const url = new URL(value);
    return `${url.origin}${url.pathname}`;
  } catch {
    return "invalid-url";
  }
}

async function run() {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  page = await context.newPage();
  page.on("pageerror", (error) => telemetry.push({ type: "pageerror", message: error.message }));
  page.on("requestfailed", (request) => telemetry.push({
    type: "requestfailed",
    path: safePath(request.url()),
    reason: request.failure()?.errorText || "unknown",
  }));

  const navigation = await page.goto(baseUrl.href, { waitUntil: "domcontentloaded" });
  assert.equal(navigation?.status(), 200, "HTTPS root must return 200");
  const finalUrl = new URL(page.url());
  assert.equal(finalUrl.origin, baseUrl.origin, "production smoke must not cross origins");
  await page.getByRole("heading", { name: "登录工作台", exact: true }).waitFor();
  await page.getByRole("button", { name: "登录", exact: true }).waitFor();

  const boundary = await page.evaluate(async () => {
    const readinessResponse = await fetch("/health/ready", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const meResponse = await fetch("/api/v1/me", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    return {
      readiness: {
        status: readinessResponse.status,
        contentType: readinessResponse.headers.get("content-type") || "",
      },
      me: {
        status: meResponse.status,
        contentType: meResponse.headers.get("content-type") || "",
      },
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
  });

  assert.equal(boundary.readiness.status, 200, "/health/ready must return 200");
  assert.match(boundary.readiness.contentType, /application\/json/i);
  assert.equal(boundary.me.status, 401, "/api/v1/me must return unauthenticated JSON");
  assert.match(boundary.me.contentType, /application\/(?:problem\+)?json/i);
  assert.equal(boundary.overflow, false, "login page must not overflow horizontally");
  assert.deepEqual(telemetry, [], "production smoke observed browser runtime failures");
  process.stdout.write("production browser smoke: HTTPS frontend and API boundary passed\n");
}

run()
  .catch(async (error) => {
    fs.mkdirSync(artifactDir, { recursive: true });
    if (page) {
      await page.screenshot({ path: path.join(artifactDir, "failure.png"), fullPage: true }).catch(() => {});
    }
    fs.writeFileSync(
      path.join(artifactDir, "failure.json"),
      `${JSON.stringify({
        message: String(error?.message || error),
        url: `${baseUrl.origin}${baseUrl.pathname}`,
        telemetry,
      }, null, 2)}\n`,
      "utf8",
    );
    process.stderr.write(`production browser smoke failed; evidence: ${artifactDir}\n`);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
  });
