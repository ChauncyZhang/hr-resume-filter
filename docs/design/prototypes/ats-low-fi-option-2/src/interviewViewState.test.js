import test from "node:test";
import assert from "node:assert/strict";
import { buildWorkweekColumns, isInWorkweek, isMyInterview } from "./interviewViewState.js";

test("workweek columns follow the current Monday through Friday across month boundaries", () => {
  const columns = buildWorkweekColumns(new Date("2026-08-01T09:00:00+08:00"));
  assert.deepEqual(columns.map((item) => item[0]), ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]);
  assert.equal(isInWorkweek("2026-07-31", columns), true);
  assert.equal(isInWorkweek("2026-08-01", columns), false);
});

test("my interview filtering uses the immutable user id instead of a display name", () => {
  const record = { interviewerIds: ["user-1"], interviewers: ["同名用户"] };
  assert.equal(isMyInterview(record, "user-1"), true);
  assert.equal(isMyInterview(record, "user-2"), false);
  assert.equal(isMyInterview(record, ""), false);
});
