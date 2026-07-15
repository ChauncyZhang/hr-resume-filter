const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..", "..");
const runnerPath = path.join(__dirname, "f01-f06.cjs");
const libraryPath = path.join(__dirname, "final-runner-lib.cjs");
const powershellPath = path.join(root, "deploy", "e2e", "run-final.ps1");
const composePath = path.join(root, "deploy", "e2e", "compose-final.yaml");
const preparePath = path.join(root, "deploy", "e2e", "prepare-final.py");

test("final runner exposes all six named real-UI flows in both required viewports", () => {
  assert.ok(fs.existsSync(runnerPath), "tests/e2e/f01-f06.cjs must exist");
  const source = fs.readFileSync(runnerPath, "utf8");

  for (const flow of ["F-01", "F-02", "F-03", "F-04", "F-05", "F-06"]) {
    assert.match(source, new RegExp(`name:\\s*[\"']${flow}[\"']`));
  }
  assert.match(source, /desktop:\s*\{\s*width:\s*1280,\s*height:\s*720\s*\}/);
  assert.match(source, /mobile:\s*\{\s*width:\s*390,\s*height:\s*844\s*\}/);
  assert.match(source, /getByRole|getByLabel/);
  assert.match(source, /getByRole\(\"heading\",\s*\{\s*name:\s*\"工作台\",\s*exact:\s*true\s*\}\)/);
  assert.match(source, /waitForResponse[\s\S]*job-definitions/);
  assert.match(source, /getByRole\("button",\s*\{\s*name:\s*"保存修改",\s*exact:\s*true\s*\}\)/);
  assert.match(source, /nonRetryableFailures/);
  assert.match(source, /launchPersistentContext[\s\S]*E2E_BROWSER_PROFILE/);
  const flow05Source = source.slice(source.indexOf("async function flow05"), source.indexOf("async function flow06"));
  assert.match(flow05Source, /tracing\.stop[\s\S]*E2E_INTERVIEWER_PASSWORD[\s\S]*tracing\.start/);
  assert.doesNotMatch(source, /page\.waitForTimeout|setTimeout\s*\(/);
});

test("PowerShell entrypoint creates and validates disposable isolation and cleanup policy", () => {
  assert.ok(fs.existsSync(powershellPath), "deploy/e2e/run-final.ps1 must exist");
  const source = fs.readFileSync(powershellPath, "utf8");

  assert.match(source, /DISPOSABLE_E2E_CONFIRMED/);
  assert.match(source, /ux09-final-e2e-/);
  assert.match(source, /New-FreeTcpPort/);
  assert.match(source, /RandomNumberGenerator\]::Create\(\)\.GetBytes/);
  assert.doesNotMatch(source, /RandomNumberGenerator\]::Fill/);
  assert.match(source, /E2E_ARTIFACT_DIR/);
  assert.match(source, /E2E_BROWSER_PROFILE/);
  assert.match(source, /KeepOnFailure/);
  assert.match(source, /down --volumes --remove-orphans/);
  assert.match(source, /docker image inspect/);
  assert.match(source, /e2e-final-prepare[\s\S]*provision-app-role\.sh[\s\S]*up -d api worker proxy/);
  for (const name of ["APP_DB_USER", "GOVERNANCE_DB_USER", "APP_OBJECT_STORAGE_ACCESS_KEY", "GOVERNANCE_DELETE_ACCESS_KEY", "GOVERNANCE_LEDGER_ACCESS_KEY"]) {
    assert.match(source, new RegExp(`env:${name}`));
  }
  assert.match(source, /production|prod/i);
  assert.doesNotMatch(source, /Start-Sleep\s+-Seconds\s+[1-9]\d*/);
});

test("final Compose and preparation remain synthetic and isolated from production names", () => {
  for (const file of [composePath, preparePath]) assert.ok(fs.existsSync(file), `${path.relative(root, file)} must exist`);
  const compose = fs.readFileSync(composePath, "utf8");
  const prepare = fs.readFileSync(preparePath, "utf8");

  assert.doesNotMatch(compose, /^name:/m);
  assert.match(compose, /ports:\s*!override/);
  assert.match(compose, /E2E_API_PORT/);
  assert.match(compose, /prepare-final\.py/);
  assert.match(compose, /build:\s*\n\s+context:\s+\.\.\s*\n/);
  assert.doesNotMatch(compose, /context:\s+\.\.\/\.\./);
  assert.doesNotMatch(compose, /^\s+(?:postgres|minio):\s*\n(?:.|\n)*?^\s+ports:/m);
  assert.match(prepare, /example\.test/);
  assert.match(prepare, /synthetic/i);
  assert.doesNotMatch(prepare, /app\/sample\/candidates\.csv/);
});

test("artifact helper redacts every required canary class", () => {
  assert.ok(fs.existsSync(libraryPath), "tests/e2e/final-runner-lib.cjs must exist");
  const { sanitizeArtifact, validateDisposableProject } = require(libraryPath);
  const canaries = {
    resumeBody: "RESUME_BODY_CANARY_ux09",
    contact: "candidate.secret@example.test",
    cookie: "session=COOKIE_CANARY_ux09",
    csrf: "CSRF_CANARY_ux09",
    apiKey: "API_KEY_CANARY_ux09",
    objectKey: "tenant/private/OBJECT_KEY_CANARY_ux09.txt",
    credential: "CREDENTIAL_CANARY_ux09",
  };
  const sanitized = sanitizeArtifact(JSON.stringify(canaries), Object.values(canaries));

  for (const value of Object.values(canaries)) assert.doesNotMatch(sanitized, new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(sanitized, /\[REDACTED\]/);
  assert.doesNotThrow(() => validateDisposableProject("ux09-final-e2e-0123456789ab", true));
  assert.throws(() => validateDisposableProject("ux09", true));
  assert.throws(() => validateDisposableProject("ux09-final-e2e-prod", true));
  assert.throws(() => validateDisposableProject("ux09-final-e2e-0123456789ab", false));
});

test("failure evidence contract includes trace screenshot DOM console network URL and redaction", () => {
  assert.ok(fs.existsSync(runnerPath), "tests/e2e/f01-f06.cjs must exist");
  const source = fs.readFileSync(runnerPath, "utf8");

  for (const term of ["tracing.start", "tracing.stop", "screenshot", "dom", "console", "pageerror", "requestfailed", "response", "currentUrl", "sanitizeArtifact"]) {
    assert.match(source, new RegExp(term.replace(".", "\\.")));
  }
  assert.match(source, /scrollWidth/);
  assert.match(source, /Tab/);
  assert.match(source, /waitFor(?:Response|URL|LoadState|Function)|\.waitFor\(/);
});
