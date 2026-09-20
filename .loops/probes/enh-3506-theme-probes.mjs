#!/usr/bin/env node
// Theme/computed-style probes for ENH-3506 (policy-router builder design tokens).
//
// Drives the *generated* policy-router-builder.html with Playwright in both
// data-theme states under an OPPOSING OS colorScheme, across all three
// authoring modes, and checks: native-control color-scheme follows data-theme,
// and normal-text contrast >= 4.5:1 on primary buttons, status messages,
// winning-rule highlight (inherited text) and YAML <pre>.
//
// Dev-only, on-demand; not part of scripts/tests/. Playwright is resolved from
// LL_PLAYWRIGHT_ROOT / NODE_PATH / `npm root -g`. Run via
// .loops/verify-enh-3506-theme.yaml.
//
// Usage: node enh-3506-theme-probes.mjs <builder.html> <report.json>   |   --check
// Exit: 0 pass, 1 fail, 2 playwright missing, 3 usage. Final stdout marker:
//   THEME_PROBES_PASSED | THEME_PROBES_FAILED
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const roots = [];
  if (process.env.LL_PLAYWRIGHT_ROOT) roots.push(process.env.LL_PLAYWRIGHT_ROOT);
  if (process.env.NODE_PATH) roots.push(...process.env.NODE_PATH.split(":").filter(Boolean));
  try { roots.push(execSync("npm root -g", { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim()); } catch { /* ignore */ }
  for (const name of ["playwright", "playwright-core", "@playwright/test"]) {
    try { return { mod: require(name), from: name }; } catch { /* next */ }
    for (const root of roots) {
      try { return { mod: require(resolve(root, name)), from: resolve(root, name) }; } catch { /* next */ }
    }
  }
  return null;
}

const [, , htmlArg, reportArg] = process.argv;
if (htmlArg === "--check") {
  const found = loadPlaywright();
  if (!found || !found.mod.chromium) { console.log("PLAYWRIGHT_MISSING"); process.exit(2); }
  try { const b = await found.mod.chromium.launch({ headless: true }); await b.close(); }
  catch (e) { console.log(`PLAYWRIGHT_MISSING: chromium launch failed: ${e.message.split("\n")[0]}`); process.exit(2); }
  console.log(`PLAYWRIGHT_OK ${found.from}`); process.exit(0);
}
if (!htmlArg || !reportArg) { console.error("usage: enh-3506-theme-probes.mjs <builder.html> <report.json>"); process.exit(3); }
const PAGE_URL = pathToFileURL(resolve(htmlArg)).href;
const found = loadPlaywright();
if (!found) { console.log("PLAYWRIGHT_MISSING"); process.exit(2); }

const MODES = ["decision_table", "rubric", "issue_lifecycle"];
const results = [];

function measure() {
  const parse = (c) => (c.match(/[\d.]+/g) || []).slice(0, 4).map(Number);
  const lum = ([r, g, b]) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + 0.05) / (l + 0.05); };
  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; e.textContent = text; document.body.appendChild(e); return e; };
  const out = {};
  const pair = (name, el, bgEl = el) => {
    // Walk up until a non-transparent background is found.
    let n = bgEl, bg = parse(getComputedStyle(n).backgroundColor);
    while (bg.length === 4 && bg[3] === 0 && n.parentElement) { n = n.parentElement; bg = parse(getComputedStyle(n).backgroundColor); }
    out[name] = ratio(parse(getComputedStyle(el).color), bg);
  };
  const btn = mk("button", "", "primary"); pair("primary-button", btn);
  const ul = document.createElement("ul"); ul.className = "messages"; document.body.appendChild(ul);
  for (const k of ["warn", "error", "ok", "info"]) { const li = document.createElement("li"); li.className = `msg-${k}`; li.textContent = k; ul.appendChild(li); pair(`msg-${k}`, li); }
  for (const k of ["ok", "warn", "error"]) {
    const li = ul.querySelector(`.msg-${k}`), cs = mk("div", `conn-status msg-${k}`, k);
    const a = getComputedStyle(li), b = getComputedStyle(cs);
    out[`conn-status-msg-${k}-matches-li`] = (a.color === b.color && a.backgroundColor === b.backgroundColor) ? 21 : 0;
  }
  const rw = mk("div", "rule-card rule-winner", "winner"); pair("rule-winner", rw);
  const pre = mk("pre", "", "yaml: 1"); pair("yaml-pre", pre);
  const sel = document.querySelector("#mode-switch");
  out.selectColorScheme = getComputedStyle(sel).colorScheme;
  return out;
}

async function run() {
  const browser = await found.mod.chromium.launch({ headless: true });
  try {
    for (const theme of ["light", "dark"]) {
      const opposing = theme === "light" ? "dark" : "light";
      const ctx = await browser.newContext({ colorScheme: opposing });
      const page = await ctx.newPage();
      await page.goto(PAGE_URL);
      for (const mode of MODES) {
        await page.selectOption("#mode-switch", mode);
        await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
        const m = await page.evaluate(measure);
        const id = `${theme}/${mode}`;
        const bad = Object.entries(m).filter(([k, v]) => k !== "selectColorScheme" && v < 4.5);
        results.push({ id: `${id}/contrast`, status: bad.length ? "FAIL" : "PASS", detail: m });
        results.push({ id: `${id}/color-scheme`, status: m.selectColorScheme === theme ? "PASS" : "FAIL",
          detail: `select color-scheme=${m.selectColorScheme} expected ${theme} (OS=${opposing})` });
        await page.evaluate(() => document.querySelectorAll("body > button, body > ul.messages, body > .rule-winner, body > pre, body > .conn-status").forEach((e) => e.remove()));
      }
      await ctx.close();
    }
  } finally { await browser.close(); }
}

try { await run(); } catch (e) { results.push({ id: "infra", status: "FAIL", detail: String(e) }); }
const fail = results.filter((r) => r.status === "FAIL").length;
mkdirSync(dirname(resolve(reportArg)), { recursive: true });
writeFileSync(resolve(reportArg), JSON.stringify({ results }, null, 2));
for (const r of results) if (r.status === "FAIL") console.log(`PROBE ${r.id} FAIL ${JSON.stringify(r.detail)}`);
console.log(`THEME_PROBES: pass=${results.length - fail} fail=${fail}`);
console.log(fail ? "THEME_PROBES_FAILED" : "THEME_PROBES_PASSED");
process.exit(fail ? 1 : 0);
