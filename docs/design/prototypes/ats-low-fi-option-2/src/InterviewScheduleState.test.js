import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("./InterviewViews.jsx", import.meta.url), "utf8");
const helpersSource = source.match(/\/\* interview-schedule-helpers:start \*\/([\s\S]*?)\/\* interview-schedule-helpers:end \*\//)?.[1];

test("new schedules run the same conflict check as reschedules", () => {
  assert.doesNotMatch(source, /if \(!record\) \{ setStep\(3\); return; \}/);
  assert.match(source, /await onCheckConflicts\(record,/);
  assert.match(source, /controller\.checkConflicts\(record\?\.id, form\)/);
});

test("hard conflicts block while soft conflicts require an explicit override", () => {
  assert.ok(helpersSource, "InterviewViews.jsx must expose the interview schedule helper block");
  const { getScheduleConflictType } = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { getScheduleConflictType }; })()`);

  assert.equal(getScheduleConflictType({ hard: ["INT-1"], soft: ["INT-2"] }, true), "hard");
  assert.equal(getScheduleConflictType({ hard: [], soft: ["INT-2"] }, false), "soft");
  assert.equal(getScheduleConflictType({ hard: [], soft: ["INT-2"] }, true), null);
});

test("saved schedule message describes downloadable invitation and pending notifications", () => {
  assert.ok(helpersSource, "InterviewViews.jsx must expose the interview schedule helper block");
  const { getScheduleSavedMessage } = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { getScheduleSavedMessage }; })()`);

  assert.equal(getScheduleSavedMessage(null), "面试安排已保存；邀请文件可下载；通知待发送");
  assert.equal(getScheduleSavedMessage({ id: "INT-1" }), "面试改期已保存；新的邀请文件可下载；通知待发送");
  assert.match(source, /onNotify\(getScheduleSavedMessage\(record\)\)/);
  assert.doesNotMatch(source, /通知已发送/);
});

test("copy helper writes the invitation text to the clipboard", async () => {
  assert.ok(helpersSource, "InterviewViews.jsx must expose the interview schedule helper block");
  const { copyInterviewText } = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { copyInterviewText }; })()`);
  let copied = "";

  await copyInterviewText("邀请内容", { async writeText(value) { copied = value; } });

  assert.equal(copied, "邀请内容");
  assert.match(source, /await copyInterviewText\(text,/);
  assert.match(source, /copyInvitation\(form\.candidateMessage,/);
  assert.match(source, /copyInvitation\(form\.interviewerMessage,/);
});

test("copy helper rejects when clipboard access is unavailable or fails", async () => {
  assert.ok(helpersSource, "InterviewViews.jsx must expose the interview schedule helper block");
  const { copyInterviewText } = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { copyInterviewText }; })()`);

  await assert.rejects(copyInterviewText("邀请内容", null), /clipboard unavailable/);
  await assert.rejects(copyInterviewText("邀请内容", { async writeText() { throw new Error("denied"); } }), /denied/);
});

test("confirmed soft conflicts are sent as an explicit save override", () => {
  assert.match(source, /allowSoftConflict: overrideSoft/);
  assert.match(source, /setOverrideSoft\(false\)/);
});

test("reschedules keep the existing candidate visible and immutable", () => {
  assert.match(source, /const recordCandidate = record \? \{ id: record\.candidateId, candidateId: record\.candidateId, name: record\.candidate/);
  assert.match(source, /disabled=\{Boolean\(record\)\}/);
  assert.match(source, /candidateOptions\.map/);
});

test("HR can cancel eligible interviews and mark arrived interviews as no-show", () => {
  assert.ok(helpersSource, "InterviewViews.jsx must expose the interview schedule helper block");
  const { getInterviewTerminalActions } = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { getInterviewTerminalActions }; })()`);

  assert.equal(JSON.stringify(getInterviewTerminalActions({ status: "待确认" }, true)), JSON.stringify([{ target: "cancelled", label: "取消面试" }]));
  assert.equal(JSON.stringify(getInterviewTerminalActions({ status: "已安排" }, true)), JSON.stringify([{ target: "cancelled", label: "取消面试" }, { target: "no_show", label: "标记未到场" }]));
  assert.equal(JSON.stringify(getInterviewTerminalActions({ status: "已确认" }, true)), JSON.stringify([{ target: "cancelled", label: "取消面试" }, { target: "no_show", label: "标记未到场" }]));
  assert.equal(JSON.stringify(getInterviewTerminalActions({ status: "已完成" }, true)), "[]");
  assert.equal(JSON.stringify(getInterviewTerminalActions({ status: "已安排" }, false)), "[]");
  assert.match(source, /请填写操作原因/);
  assert.match(source, /onTransition\(transitionDraft\.record, transitionDraft\.target, reason\.trim\(\)\)/);
});
