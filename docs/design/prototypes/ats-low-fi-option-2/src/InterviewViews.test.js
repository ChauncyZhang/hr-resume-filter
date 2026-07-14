import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("./InterviewViews.jsx", import.meta.url), "utf8");
const appSource = readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
const helpersSource = source.match(/\/\* feedback-draft-helpers:start \*\/([\s\S]*?)\/\* feedback-draft-helpers:end \*\//)?.[1];
assert.ok(helpersSource, "InterviewViews.jsx must expose the feedback draft helper block");
const {
  clearInterviewFeedbackDraft,
  getFeedbackSubmitError,
  getInterviewFeedbackDraftKey,
  loadInterviewFeedbackDraft,
  resolveInterviewFeedbackDraft,
  saveInterviewFeedbackDraft,
} = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { clearInterviewFeedbackDraft, getFeedbackSubmitError, getInterviewFeedbackDraftKey, loadInterviewFeedbackDraft, resolveInterviewFeedbackDraft, saveInterviewFeedbackDraft }; })()`);

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, value); },
    removeItem(key) { values.delete(key); },
  };
}

const form = {
  ratings: { professional: "优秀", problem: "良好", communication: "良好", fit: "优秀" },
  strengths: "技术基础扎实",
  risks: "管理经验待确认",
  conclusion: "推荐",
  notes: "进入下一轮",
};

test("feedback drafts are isolated by interview id", () => {
  const storage = createStorage();
  saveInterviewFeedbackDraft("USER-001", "INT-001", form, storage);

  assert.equal(JSON.stringify(loadInterviewFeedbackDraft("USER-001", { id: "INT-001" }, storage)), JSON.stringify(form));
  assert.equal(loadInterviewFeedbackDraft("USER-001", { id: "INT-002" }, storage), null);
  assert.equal(loadInterviewFeedbackDraft("USER-002", { id: "INT-001" }, storage), null);
});

test("submitted feedback never loads a local draft", () => {
  const storage = createStorage();
  saveInterviewFeedbackDraft("USER-001", "INT-001", form, storage);

  assert.equal(loadInterviewFeedbackDraft("USER-001", { id: "INT-001", feedback: { canEdit: false } }, storage), null);
});

test("invalid or unavailable storage falls back without throwing", () => {
  const invalidStorage = createStorage({ [getInterviewFeedbackDraftKey("USER-001", "INT-001")]: "not-json" });
  const unavailableStorage = { getItem() { throw new Error("blocked"); } };

  assert.equal(loadInterviewFeedbackDraft("USER-001", { id: "INT-001" }, invalidStorage), null);
  assert.equal(loadInterviewFeedbackDraft("USER-001", { id: "INT-001" }, unavailableStorage), null);
});

test("clearing a submitted draft removes only that interview draft", () => {
  const storage = createStorage();
  saveInterviewFeedbackDraft("USER-001", "INT-001", form, storage);
  saveInterviewFeedbackDraft("USER-001", "INT-002", { ...form, conclusion: "保留" }, storage);

  clearInterviewFeedbackDraft("USER-001", "INT-001", storage);

  assert.equal(loadInterviewFeedbackDraft("USER-001", { id: "INT-001" }, storage), null);
  assert.equal(loadInterviewFeedbackDraft("USER-001", { id: "INT-002" }, storage).conclusion, "保留");
});

test("a versioned server draft wins over a stale local draft", () => {
  const local = { ...form, conclusion: "保留" };
  const server = { ...form, id: "FDB-001", version: 3, conclusion: "推荐" };

  const resolved = resolveInterviewFeedbackDraft(local, server);

  assert.equal(resolved.source, "server");
  assert.equal(resolved.form.conclusion, "推荐");
  assert.equal(resolveInterviewFeedbackDraft(local, { status: "draft", version: 0 }).source, "local");
});

test("feedback version conflicts explain that the local draft was preserved", () => {
  assert.equal(
    getFeedbackSubmitError({ code: "resource_version_conflict" }),
    "服务端草稿已在其他页面或设备更新。本机内容已保留，请刷新后核对再提交。",
  );
  assert.equal(getFeedbackSubmitError({ code: "service_unavailable" }), "网络请求失败，表单和本机草稿均已保留。请重试提交。");
});

test("schedule workspace loads pending applications from the server without fixture fallback", () => {
  assert.match(appSource, /candidateController\.listCandidates\(\{ stage: "待安排", limit: 100, cursor: cursor \|\| undefined \}/);
  assert.match(appSource, /selectSchedulableCandidates\(interviewCandidateRecords\)/);
  assert.doesNotMatch(appSource, /if \(!selectedCandidateWithInterviews\) return candidateRecords/);
});
