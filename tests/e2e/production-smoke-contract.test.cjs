const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");
const smokePath = path.join(
  root,
  "docs",
  "design",
  "prototypes",
  "ats-low-fi-option-2",
  "scripts",
  "production-browser-smoke.cjs",
);

test("production browser smoke is read-only, HTTPS-only, and checks the real frontend/API boundary", () => {
  assert.ok(fs.existsSync(smokePath), "production browser smoke runner must exist");
  const source = fs.readFileSync(smokePath, "utf8");

  assert.match(source, /UX09_PRODUCTION_URL/);
  assert.match(source, /protocol\s*!==\s*["']https:["']/);
  assert.doesNotMatch(source, /ignoreHTTPSErrors\s*:\s*true/);
  assert.match(source, /登录工作台/);
  assert.match(source, /getByRole\(["']button["'][\s\S]*登录/);
  assert.match(source, /page\.url\(\)/);
  assert.match(source, /finalUrl\.origin[\s\S]*baseUrl\.origin/);
  assert.match(source, /\/health\/ready/);
  assert.match(source, /\/api\/v1\/me/);
  assert.match(source, /status[\s\S]*401/);
  assert.match(source, /application\/json/);
  assert.match(source, /pageerror|requestfailed/);
  assert.match(source, /screenshot/);
  assert.doesNotMatch(source, /\.fill\(|auth\/login/i);
  assert.doesNotMatch(source, /process\.env\.[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|KEY)/);
});
