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

test("the system deferred pool is selected by system key and exposes recovery evidence", () => {
  assert.match(source, /pool\.systemKey === "ai_screening_deferred"/);
  assert.match(source, /原岗位/);
  assert.match(source, /最终分/);
  assert.match(source, /暂缓时间/);
  assert.match(source, /主要缺口/);
  assert.match(source, /跟进负责人/);
  assert.doesNotMatch(source, /pool\.name === [^\n]*ai_screening_deferred/);
});

test("deferred rows refer once while ordinary pools keep reactivation", () => {
  assert.match(source, /转交用人经理/);
  assert.match(source, /已转交用人经理/);
  assert.match(source, /member\.sourceStage === "用人经理复核"/);
  assert.match(source, /disabled=\{[^}]*referringMemberId === member\.id/);
  assert.match(source, /重新激活/);
});

test("referral replaces the membership in place and refreshes the workbench without changing route state", () => {
  assert.match(source, /controller\.referToReview\(member\.id, member\.version\)/);
  assert.match(source, /memberships: current\.memberships\.map\(\(item\) => item\.id === result\.membership\.id \? result\.membership : item\)/);
  assert.match(source, /onReferralComplete\(result\.application\)/);
  assert.doesNotMatch(source, /referToReview[\s\S]{0,500}setSelectedPoolId/);
  assert.doesNotMatch(source, /referToReview[\s\S]{0,500}setMode/);
});

test("referral status is perceivable and the primary action does not depend on hover", () => {
  assert.match(source, /role="status"/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /aria-label=\{`转交用人经理：\$\{candidate\.name\}`\}/);
  assert.doesNotMatch(source, /onMouseEnter|onMouseLeave/);
});
