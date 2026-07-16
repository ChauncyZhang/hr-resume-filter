import test from "node:test";
import assert from "node:assert/strict";
import { createAppHistory } from "./appHistory.js";

function createFakeBrowserHistory() {
  const listeners = new Set();
  const history = {
    state: null,
    pushes: [],
    backCalls: 0,
    pushState(state) {
      this.state = state;
      this.pushes.push(state);
    },
    back() {
      this.backCalls += 1;
      listeners.forEach((listener) => listener({ state: null }));
    },
  };
  const eventTarget = {
    addEventListener(type, listener) { if (type === "popstate") listeners.add(listener); },
    removeEventListener(type, listener) { if (type === "popstate") listeners.delete(listener); },
  };
  return { history, eventTarget };
}

test("browser back restores the most recent in-app view instead of leaving the site", () => {
  const browser = createFakeBrowserHistory();
  const restored = [];
  const appHistory = createAppHistory(browser);
  appHistory.start();

  appHistory.push(() => restored.push("candidate-detail"));
  appHistory.push(() => restored.push("interview-schedule"));

  assert.equal(appHistory.requestBack(), true);
  assert.deepEqual(restored, ["interview-schedule"]);
  assert.equal(appHistory.requestBack(), true);
  assert.deepEqual(restored, ["interview-schedule", "candidate-detail"]);
  assert.equal(browser.history.backCalls, 2);

  appHistory.stop();
});

test("in-app back uses its fallback only when there is no internal history", () => {
  const browser = createFakeBrowserHistory();
  const appHistory = createAppHistory(browser);
  let fallbackCalls = 0;

  assert.equal(appHistory.requestBack(() => { fallbackCalls += 1; }), false);
  assert.equal(fallbackCalls, 1);
  assert.equal(browser.history.backCalls, 0);
});
