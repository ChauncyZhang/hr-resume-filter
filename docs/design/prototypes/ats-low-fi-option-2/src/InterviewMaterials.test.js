import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./InterviewViews.jsx", import.meta.url), "utf8");

test("feedback page loads interview-scoped materials and opens a redacted preview", () => {
  assert.match(source, /controller\.getMaterials\(record\.id/);
  assert.match(source, /function FeedbackMaterials/);
  assert.match(source, /materialsState\.data\?\.resume\?\.previewText/);
  assert.match(source, /脱敏简历预览/);
  assert.doesNotMatch(source, /onNotify\("候选人简历已打开"\)/);
});

test("materials failures are retryable without hiding the feedback form", () => {
  assert.match(source, /材料加载失败/);
  assert.match(source, /onRetry/);
});
