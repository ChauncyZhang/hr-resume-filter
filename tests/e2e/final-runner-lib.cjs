const assert = require("node:assert/strict");

const DISPOSABLE_PROJECT = /^ux09-final-e2e-[0-9a-f]{12}$/;
const FORBIDDEN_PROJECT = /(?:^|[-_])(prod|production|stage|staging|shared)(?:$|[-_])/i;

function validateDisposableProject(projectName, confirmed) {
  assert.equal(confirmed, true, "DISPOSABLE_E2E_CONFIRMED=1 is required");
  assert.match(projectName || "", DISPOSABLE_PROJECT, "Compose project must use the disposable final-E2E pattern");
  assert.doesNotMatch(projectName, FORBIDDEN_PROJECT, "production-like Compose project names are refused");
  return projectName;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function sanitizeArtifact(value, canaries = []) {
  let text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  for (const canary of canaries.filter((item) => typeof item === "string" && item)) {
    text = text.replace(new RegExp(escapeRegExp(canary), "g"), "[REDACTED]");
  }
  return text
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[REDACTED_EMAIL]")
    .replace(/\b(?:\+?86[- ]?)?1[3-9]\d{9}\b/g, "[REDACTED_PHONE]")
    .replace(/\b(?:bearer|basic)\s+[A-Za-z0-9._~+\/-]+=*/gi, "[REDACTED_AUTH]")
    .replace(/\b(?:session|csrf|cookie|password|secret|api[_-]?key|access[_-]?key)\b\s*[:=]\s*[^\s,;\"}]+/gi, "$1=[REDACTED]")
    .replace(/(?:tenant|organization|org)\/[A-Za-z0-9._\/-]+/gi, "[REDACTED_OBJECT_KEY]");
}

module.exports = { sanitizeArtifact, validateDisposableProject };
