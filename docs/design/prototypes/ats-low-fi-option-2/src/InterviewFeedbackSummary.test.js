import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./InterviewViews.jsx", import.meta.url), "utf8");

test("non-participant reviewers load submitted feedback summaries instead of my-feedback", () => {
  assert.match(source, /ownsFeedback \? controller\.getMyFeedback\(record\.id, requestOptions\) : controller\.listFeedbacks\(record\.id, requestOptions\)/);
  assert.match(source, /summaryFeedbacks\.map/);
  assert.match(source, /暂无已提交反馈/);
});
