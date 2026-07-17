import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./TalentPoolViews.jsx", import.meta.url), "utf8");

test("talent members select recommended jobs from real positions instead of entering free text", () => {
  assert.match(source, /aria-label="推荐岗位"/);
  assert.match(source, /type="checkbox"/);
  assert.doesNotMatch(source, /编辑适合岗位<input/);
});

test("talent tags can be removed and reactivation is exposed as a direct action", () => {
  assert.match(source, /aria-label={`移除标签：\$\{item\}`}/);
  assert.match(source, /重新激活到职位/);
  assert.match(source, /initialReactivateOpen/);
});
