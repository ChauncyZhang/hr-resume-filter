import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("./App.jsx", import.meta.url), "utf8");

test("schedule candidate loading follows every server cursor", () => {
  assert.match(appSource, /let cursor = ""/);
  assert.match(appSource, /cursor: cursor \|\| undefined/);
  assert.match(appSource, /cursor = page\.nextCursor \|\| ""/);
  assert.match(appSource, /while \(cursor\)/);
});

test("interview pagination appends the next server page without replacing existing rows", () => {
  assert.match(appSource, /nextCursor: page\.nextCursor/);
  assert.match(appSource, /append \? \[\.\.\.current\.records, \.\.\.page\.records\]/);
  assert.match(appSource, /cursor: interviewState\.nextCursor/);
  assert.match(appSource, /onLoadMore/);
});
