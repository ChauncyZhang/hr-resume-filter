import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("./InterviewViews.jsx", import.meta.url), "utf8");
const helpersSource = source.match(/\/\* feedback-draft-helpers:start \*\/([\s\S]*?)\/\* feedback-draft-helpers:end \*\//)?.[1];
assert.ok(helpersSource, "InterviewViews.jsx must expose the feedback draft helper block");
const {
  clearInterviewFeedbackDraft,
  getInterviewFeedbackDraftKey,
  loadInterviewFeedbackDraft,
  saveInterviewFeedbackDraft,
} = vm.runInNewContext(`(() => { ${helpersSource.replaceAll("export ", "")} return { clearInterviewFeedbackDraft, getInterviewFeedbackDraftKey, loadInterviewFeedbackDraft, saveInterviewFeedbackDraft }; })()`);

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
  saveInterviewFeedbackDraft("INT-001", form, storage);

  assert.equal(JSON.stringify(loadInterviewFeedbackDraft({ id: "INT-001" }, storage)), JSON.stringify(form));
  assert.equal(loadInterviewFeedbackDraft({ id: "INT-002" }, storage), null);
});

test("submitted feedback never loads a local draft", () => {
  const storage = createStorage();
  saveInterviewFeedbackDraft("INT-001", form, storage);

  assert.equal(loadInterviewFeedbackDraft({ id: "INT-001", feedback: { canEdit: false } }, storage), null);
});

test("invalid or unavailable storage falls back without throwing", () => {
  const invalidStorage = createStorage({ [getInterviewFeedbackDraftKey("INT-001")]: "not-json" });
  const unavailableStorage = { getItem() { throw new Error("blocked"); } };

  assert.equal(loadInterviewFeedbackDraft({ id: "INT-001" }, invalidStorage), null);
  assert.equal(loadInterviewFeedbackDraft({ id: "INT-001" }, unavailableStorage), null);
});

test("clearing a submitted draft removes only that interview draft", () => {
  const storage = createStorage();
  saveInterviewFeedbackDraft("INT-001", form, storage);
  saveInterviewFeedbackDraft("INT-002", { ...form, conclusion: "保留" }, storage);

  clearInterviewFeedbackDraft("INT-001", storage);

  assert.equal(loadInterviewFeedbackDraft({ id: "INT-001" }, storage), null);
  assert.equal(loadInterviewFeedbackDraft({ id: "INT-002" }, storage).conclusion, "保留");
});
