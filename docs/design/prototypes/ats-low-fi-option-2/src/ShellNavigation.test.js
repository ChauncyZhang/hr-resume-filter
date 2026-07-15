import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
const stylesSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

test("global navigation exposes its current destination and drawer state", () => {
  assert.match(appSource, /<nav id="primary-navigation" aria-label="主导航">/);
  assert.match(appSource, /aria-current=\{activeNav === label \? "page" : undefined\}/);
  assert.match(appSource, /aria-controls="primary-navigation"/);
  assert.match(appSource, /aria-expanded=\{menuOpen\}/);
  assert.match(appSource, /label=\{menuOpen \? "关闭主导航" : "打开主导航"\}/);
});

test("390px keeps the single global navigation in the viewport without body overflow", () => {
  assert.match(stylesSource, /body \{[^}]*overflow-x: hidden;/s);
  assert.match(stylesSource, /@media \(max-width: 600px\) \{[\s\S]*?\.app-shell \{ display: block; \}[\s\S]*?\.sidebar \{[^}]*position: static;[^}]*width: 100%;[^}]*transform: none;[^}]*visibility: visible;/);
  assert.match(stylesSource, /@media \(max-width: 600px\) \{[\s\S]*?\.sidebar nav \{[^}]*display: flex;[^}]*overflow-x: auto;/);
  assert.match(stylesSource, /@media \(max-width: 600px\) \{[\s\S]*?\.nav-item \{[^}]*flex: 0 0 auto;/);
});
