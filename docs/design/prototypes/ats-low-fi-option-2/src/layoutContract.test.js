import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

function declarationsFor(selector, source = styles) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`));

  assert.ok(match, `missing CSS rule for ${selector}`);
  return match[1];
}

test("audit governance toolbar keeps controls aligned while allowing fields to wrap", () => {
  assert.match(declarationsFor(".audit-toolbar.governance-filters"), /align-items:\s*flex-end/);
  assert.match(declarationsFor(".audit-toolbar.governance-filters label"), /height:\s*auto/);
  assert.match(declarationsFor(".audit-toolbar.governance-filters label"), /min-height:\s*60px/);
  assert.match(declarationsFor(".audit-toolbar.governance-filters label"), /flex:\s*1 1 155px/);
  assert.match(declarationsFor(".audit-toolbar.governance-filters > span"), /align-self:\s*flex-end/);
  assert.match(declarationsFor(".audit-toolbar.governance-filters > span"), /min-height:\s*36px/);
});

test("import screening modal centers step markers and keeps paired fields top-aligned", () => {
  assert.match(declarationsFor(".wizard-steps > div"), /justify-content:\s*center/);
  assert.match(declarationsFor(".wizard-steps i"), /left:\s*calc\(50% \+ 17px\)/);
  assert.match(declarationsFor(".wizard-steps i"), /right:\s*calc\(-50% \+ 17px\)/);
  assert.match(declarationsFor(".wizard-grid"), /align-items:\s*start/);
  assert.match(declarationsFor(".wizard-grid label, .wizard-field"), /min-width:\s*0/);
  assert.match(declarationsFor(".wizard-grid label, .wizard-field"), /align-content:\s*start/);
});

test("schedule validation messages do not stretch the paired form control", () => {
  assert.match(declarationsFor(".schedule-grid > label"), /align-content:\s*start/);
});

test("audit toolbar remains full-width and step labels stay contained on mobile", () => {
  assert.match(styles, /\.field-state:empty\s*\{[^}]*display:\s*none/);
  assert.match(styles, /@media \(max-width: 900px\) \{[\s\S]*?\.audit-toolbar\.governance-filters label\s*\{[^}]*flex:\s*0 0 auto/);
  assert.match(styles, /@media \(max-width: 600px\) \{[\s\S]*?\.audit-toolbar\.governance-filters > \.button\s*\{[^}]*width:\s*100%/);
  assert.match(styles, /@media \(max-width: 600px\) \{[\s\S]*?\.audit-toolbar\.governance-filters > span\s*\{[^}]*width:\s*100%[^}]*min-height:\s*0/);
  assert.match(styles, /@media \(max-width: 600px\) \{[\s\S]*?\.wizard-steps strong\s*\{[^}]*min-width:\s*0[^}]*text-align:\s*center/);
  assert.match(styles, /@media \(max-width: 600px\) \{[\s\S]*?\.wizard-steps i\s*\{[^}]*right:\s*calc\(-50% \+ 17px\)/);
});
