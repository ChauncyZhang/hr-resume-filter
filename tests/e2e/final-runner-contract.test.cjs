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
  assert.match(source, /name:\s*\"登录工作台\"[\s\S]*waitForResponse[\s\S]*\/api\/v1\/auth\/login[\s\S]*loginResponse\.status\(\),\s*200/);
  assert.match(source, /waitForResponse[\s\S]*job-definitions/);
  assert.match(source, /getByRole\("button",\s*\{\s*name:\s*"保存修改",\s*exact:\s*true\s*\}\)/);
  const flow01Source = source.slice(source.indexOf("async function flow01"), source.indexOf("async function flow02"));
  assert.match(flow01Source, /class[\s\S]*primary/);
  assert.match(flow01Source, /compareDocumentPosition/);
  assert.match(flow01Source, /北京、上海或远程/);
  assert.match(flow01Source, /招聘中/);
  assert.match(source, /nonRetryableFailures/);
  assert.match(source, /file_type_mismatch/);
  assert.match(source, /file_magic_mismatch/);
  assert.match(source, /file_too_large/);
  assert.match(source, /EICAR-STANDARD-ANTIVIRUS-TEST-FILE/);
  assert.match(source, /malware_detected/);
  assert.match(source, /candidateCount,\s*17/);
  assert.match(source, /LLM 未启用/);
  assert.match(source, /launchPersistentContext[\s\S]*E2E_BROWSER_PROFILE/);
  const flow05Source = source.slice(source.indexOf("async function flow05"), source.indexOf("async function flow06"));
  const switchAccountSource = source.slice(source.indexOf("async function switchAccount"), source.indexOf("async function navigate"));
  assert.doesNotMatch(switchAccountSource, /tracing\./);
  assert.match(flow05Source, /switchAccount\([\s\S]*E2E_INTERVIEWER_PASSWORD/);
  assert.doesNotMatch(source, /page\.waitForTimeout|setTimeout\s*\(/);
});

test("final runner has no intentional product-blocker placeholders", () => {
  const source = fs.readFileSync(runnerPath, "utf8");

  for (const placeholder of [
    "no candidate record or retry action was produced",
    "current SPA has no deterministic UI-only duplicate/version-conflict trigger",
    "candidate has not reached the UI state that exposes the schedule action",
    "requires the F-04 interview to reach pending-feedback",
    "add-to-pool is correctly hidden until the application reaches a terminal state",
  ]) {
    assert.doesNotMatch(source, new RegExp(placeholder.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(source, /candidateCount/);
  assert.match(source, /escapeRegex/);
  assert.match(source, /staleResponse\.status\(\),\s*409/);
  assert.match(source, /刷新最新详情/);
  assert.match(source, /撤销批量推进/);
  assert.match(source, /undo_advance_to_new/);
  assert.doesNotMatch(source, /候选人已推进到\$\{target\}/);
  assert.match(source, /active_application_exists/);
  assert.match(source, /waitForEvent\("download"\)/);
  assert.match(source, /BEGIN:VCALENDAR/);
  assert.match(source, /calendar_sequence/);
  assert.match(source, /localStorage/);
  assert.match(source, /route\.fetch\(\)[\s\S]*route\.abort\("connectionfailed"\)/);
  assert.match(source, /idempotency-key/);
  assert.match(source, /\/reactivations/);
  const flow06Source = source.slice(source.indexOf("async function flow06"), source.indexOf("async function runViewport"));
  assert.match(flow06Source, /launchPersistentContext/);
  assert.match(flow06Source, /Promise\.all/);
  assert.match(flow06Source, /\[201,\s*409\]/);
  assert.match(flow06Source, /talent_pool_reactivation/);
  assert.match(flow06Source, /applications-table/);
  assert.match(source, /getByRole\("button",\s*\{\s*name:\s*"去新申请"/);
  assert.match(source, /reactivatedApplicationId/);
  assert.doesNotMatch(source, /task hierarchy remains a product blocker/);
});

test("final runner reads the privacy-minimized recent server task metadata", () => {
  const source = fs.readFileSync(runnerPath, "utf8");

  assert.match(source, /state\.jobId\s*=\s*created\.job\.id/);
  assert.match(source, /assert\.match\(state\.jobId,\s*\/\^\[0-9a-f-\]/);
  assert.match(source, /ats_recent_screening_task:user:/);
  assert.match(source, /serverBacked\s*===\s*true/);
  assert.doesNotMatch(source, /value\?\.files[\s\S]{0,80}length\s*===\s*18/);
});

test("final runner separates display-only identity hints and stale sessions", () => {
  const source = fs.readFileSync(runnerPath, "utf8");

  assert.match(source, /replace\(\/（待核验）\$\/,\s*""\)/);
  assert.match(source, /launchPersistentContext\([\s\S]*stale/);
  assert.match(source, /login\(stalePage/);
  assert.doesNotMatch(source, /page\.context\(\)\.newPage\(\)/);
});

test("final runner proves dedicated deployments do not ask users for an organization slug", () => {
  const runner = fs.readFileSync(runnerPath, "utf8");
  const powershell = fs.readFileSync(powershellPath, "utf8");

  assert.match(runner, /\/api\/v1\/auth\/config/);
  assert.match(runner, /default_organization[\s\S]*final-e2e/);
  assert.match(runner, /postDataJSON\(\)[\s\S]*organization_slug/);
  assert.doesNotMatch(runner, /getByLabel\("组织标识"\)/);
  assert.match(powershell, /DEFAULT_ORGANIZATION_SLUG\s*=\s*"final-e2e"/);
  assert.match(powershell, /DEFAULT_ORGANIZATION_NAME/);
});

test("final runner waits for feedback hydration and isolates later account state", () => {
  const source = fs.readFileSync(runnerPath, "utf8");
  const flow03Source = source.slice(source.indexOf("async function flow03"), source.indexOf("async function advanceScheduleCollaboration"));
  const flow05Source = source.slice(source.indexOf("async function flow05"), source.indexOf("async function openTalentMember"));
  const flow06Source = source.slice(source.indexOf("async function flow06"), source.indexOf("async function runViewport"));

  assert.match(flow03Source, /reload[\s\S]*筛选证据[\s\S]*Synthetic human review conclusion/);
  assert.match(flow03Source, /duplicateApplicationContext\.request\.post[\s\S]*\/api\/v1\/auth\/login[\s\S]*loginResponse\.headers\(\)\["x-csrf-token"\]/);
  assert.match(flow03Source, /E2E_RECRUITER_EMAIL[\s\S]*recruiterMeResponse[\s\S]*owner_id:\s*recruiterId/);
  assert.match(flow05Source, /waitForResponse[\s\S]*\/my-feedback[\s\S]*task\.click/);
  assert.doesNotMatch(flow05Source, /rail-item"\)\.count\(\),\s*1/);
  assert.match(flow05Source, /E2E_UNASSIGNED_INTERVIEWER_EMAIL/);
  assert.match(flow05Source, /my-feedback[\s\S]*status\(\),\s*404/);
  assert.match(source, /flowName === \"F-05\"[\s\S]*entry\.status === 401[\s\S]*\/api\/v1\/me/);
  assert.match(source, /flowName === \"F-05\"[\s\S]*entry\.status === 401[\s\S]*\/my-feedback/);
  assert.match(source, /flowName === \"F-01\"[\s\S]*ERR_NETWORK_CHANGED/);
  assert.match(source, /flowName === \"F-05\"[\s\S]*\/api\/v1\/auth\/logout[\s\S]*ERR_ABORTED/);
  assert.match(source, /ERR_\(\?:CONNECTION_\)\?FAILED/);
  assert.match(flow05Source, /rail-item[\s\S]*toHaveCount|rail-item[\s\S]*count\(\)/);
  assert.match(flow05Source, /switchAccount\([\s\S]*E2E_ADMIN_EMAIL/);
  assert.doesNotMatch(flow06Source, /switchAccount\(/);
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
  assert.match(prepare, /E2E_UNASSIGNED_INTERVIEWER_EMAIL/);
  assert.match(fs.readFileSync(powershellPath, "utf8"), /E2E_UNASSIGNED_INTERVIEWER_EMAIL/);
  assert.match(prepare, /E2E_RECRUITER_EMAIL[\s\S]*"recruiter"/);
  assert.match(fs.readFileSync(powershellPath, "utf8"), /E2E_RECRUITER_EMAIL/);
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

test("failure evidence is sanitized and successful flows reject runtime telemetry", () => {
  assert.ok(fs.existsSync(runnerPath), "tests/e2e/f01-f06.cjs must exist");
  const source = fs.readFileSync(runnerPath, "utf8");

  for (const term of ["screenshot", "dom", "console", "pageerror", "requestfailed", "response", "currentUrl", "sanitizeArtifact", "assertNoUnexpectedTelemetry"]) {
    assert.match(source, new RegExp(term.replace(".", "\\.")));
  }
  assert.doesNotMatch(source, /trace\.zip|tracing\.stop\(\{\s*path/);
  assert.match(source, /flow\.run[\s\S]*assertNoUnexpectedTelemetry/);
  assert.match(source, /scrollWidth/);
  assert.match(source, /Tab/);
  assert.match(source, /waitFor(?:Response|URL|LoadState|Function)|\.waitFor\(/);
});
