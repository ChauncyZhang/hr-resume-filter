const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const repositoryRoot = path.resolve(__dirname, "..", "..");
const composePath = path.join(repositoryRoot, "deploy", "e2e", "compose.yaml");
const preparePath = path.join(repositoryRoot, "deploy", "e2e", "prepare.py");
const recoveryPath = path.join(repositoryRoot, "tests", "e2e", "recovery.cjs");
const objectVerifierPath = path.join(repositoryRoot, "deploy", "e2e", "verify_objects.py");

test("isolated compose gates runtime services on ephemeral preparation", () => {
  const compose = fs.readFileSync(composePath, "utf8");

  assert.doesNotMatch(compose, /^name:/m);
  assert.match(compose, /ports:\s*!override/);
  assert.match(compose, /E2E_API_PORT/);
  assert.match(compose, /e2e-prepare:/);
  assert.match(compose, /condition:\s*service_completed_successfully/);
  assert.match(compose, /e2e-prepare:(?:.|\n)*?networks:\s*\[private\]/);
  assert.match(compose, /PYTHONPATH:\s*\/opt\/ux09/);
  assert.doesNotMatch(compose, /^\s+(?:postgres|minio):\s*\n(?:.|\n)*?^\s+ports:/m);
});

test("preparation is synthetic, idempotent, and creates storage before seeding", () => {
  const source = fs.readFileSync(preparePath, "utf8");

  assert.match(source, /bucket_exists/);
  assert.match(source, /make_bucket/);
  assert.match(source, /recruiting_admin/);
  assert.match(source, /role\.role == "system_admin"/);
  assert.match(source, /db\.delete\(role\)/);
  assert.match(source, /JobJdVersion/);
  assert.match(source, /ScreeningRuleVersion/);
  assert.match(source, /status="open"/);
  assert.doesNotMatch(source, /status="published"/);
  assert.match(source, /"required_terms"/);
  assert.match(source, /"bonus_terms"/);
  assert.doesNotMatch(source, /"required":/);
  assert.doesNotMatch(source, /"bonus":/);
  assert.doesNotMatch(source, /change-me/);
});

test("recovery gate queues 100 files before the worker starts and proves durable storage", () => {
  const source = fs.readFileSync(recoveryPath, "utf8");

  assert.match(source, /expectedCount\s*=\s*100/);
  assert.match(source, /Array\.from\(\{ length: expectedCount \}/);
  assert.match(source, /compose\("stop",\s*"worker"\)/);
  assert.match(source, /compose\("restart",\s*"api"\)/);
  assert.match(source, /compose\("start",\s*"worker"\)/);
  assert.match(source, /new_applications/);
  assert.match(source, /verify_objects\.py/);
  assert.ok(fs.existsSync(objectVerifierPath));
});
