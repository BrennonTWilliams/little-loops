#!/usr/bin/env node
// Browser-persistence probes for FEAT-3488 / ENH-3487 (policy-router builder).
//
// Drives the *generated* policy-router-builder.html with Playwright and checks
// the acceptance criteria that ENH-3487 (Option B) left to a manual browser
// checklist: reload persistence, mode-switch draft preservation, undo/redo,
// Start blank + preset + undo, Save/Open round trip, corrupt project file,
// corrupt stored draft, storage-disabled degradation, FEAT-3488's
// scenario-suite persistence once its DOM lands, and FEAT-3503's local
// issue-file import (split out of FEAT-3488 on 2026-09-17).
//
// Dev-only tooling. Deliberately NOT part of scripts/tests/ or pyproject.toml:
// it uses whatever Playwright is already installed on the invoking machine
// (LL_PLAYWRIGHT_ROOT, NODE_PATH, or `npm root -g`) and reports clearly when
// none is present. Run via .loops/verify-feat-3488-browser-persistence.yaml.
//
// Usage: node feat-3488-browser-probes.mjs <path/to/policy-router-builder.html> <report.json>
// Exit: 0 = all probes passed, 2 = no failures but some probes BLOCKED
//       (FEAT-3488 surface not present yet), 1 = at least one FAIL, 3 = infra.
// stdout ends with exactly one marker line:
//   BROWSER_PROBES_PASSED | BROWSER_PROBES_BLOCKED | BROWSER_PROBES_FAILED
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

// ---- FEAT-3488 / FEAT-3503 DOM contract ------------------------------------
// Fill these in once FEAT-3488 lands (import* once FEAT-3503 lands). While any
// selector a probe needs is null, that probe reports BLOCKED (not FAIL) so the
// loop can distinguish "feature not implemented yet" from "feature broken".
const SCENARIO_SELECTORS = {
  addCaseBtn: null,        // e.g. "#scenario-add-case"
  caseNameInput: null,     // e.g. "#scenario-case-name"
  caseList: null,          // e.g. "#scenario-case-list" (children = cases)
  runAllBtn: null,         // e.g. "#scenario-run-all"
  totals: null,            // e.g. "#scenario-totals" (text with pass/fail/unasserted/error)
  importIssueInput: null,  // e.g. "#scenario-import-issue-input" (input[type=file])
  importDiagnostics: null, // e.g. "#scenario-import-diagnostics"
};

// ---- locate Playwright without a repo dependency ---------------------------
function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const roots = [];
  if (process.env.LL_PLAYWRIGHT_ROOT) roots.push(process.env.LL_PLAYWRIGHT_ROOT);
  if (process.env.NODE_PATH) roots.push(...process.env.NODE_PATH.split(":").filter(Boolean));
  try { roots.push(execSync("npm root -g", { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim()); } catch { /* ignore */ }
  const candidates = ["playwright", "playwright-core", "@playwright/test"];
  for (const name of candidates) {
    try { return { mod: require(name), from: name }; } catch { /* next */ }
    for (const root of roots) {
      try { return { mod: require(resolve(root, name)), from: resolve(root, name) }; } catch { /* next */ }
    }
  }
  return null;
}

const [, , htmlArg, reportArg] = process.argv;
if (htmlArg === "--check") {
  // Preflight: report whether a launchable Playwright + Chromium is available.
  const found = loadPlaywright();
  if (!found || !found.mod.chromium) { console.log("PLAYWRIGHT_MISSING"); process.exit(2); }
  try { const b = await found.mod.chromium.launch({ headless: true }); await b.close(); }
  catch (e) { console.log(`PLAYWRIGHT_MISSING: chromium launch failed: ${e.message.split("\n")[0]}`); process.exit(2); }
  console.log(`PLAYWRIGHT_OK ${found.from}`); process.exit(0);
}
if (!htmlArg || !reportArg) {
  console.error("usage: feat-3488-browser-probes.mjs <builder.html> <report.json>");
  process.exit(3);
}
const HTML_PATH = resolve(htmlArg);
const REPORT_PATH = resolve(reportArg);
const PAGE_URL = pathToFileURL(HTML_PATH).href;

class Blocked extends Error {}
const blocked = (why) => { throw new Blocked(why); };
const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
const needSelectors = (...keys) => {
  const missing = keys.filter((k) => !SCENARIO_SELECTORS[k]);
  if (missing.length) blocked(`FEAT-3488 selectors unset: ${missing.join(", ")}`);
};

// ---- page helpers ----------------------------------------------------------
async function newPage(browser, { initScript } = {}) {
  const context = await browser.newContext();
  if (initScript) await context.addInitScript(initScript);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(PAGE_URL);
  await page.waitForSelector("#rule-list", { state: "attached" });
  return { context, page, errors };
}
const ruleCount = (page) => page.locator("#rule-list .rule-card").count();
const liveStatus = (page) => page.locator("#live-status").textContent();
const mode = (page) => page.locator("#mode-switch").inputValue();
const name = (page) => page.locator("#f-name").inputValue();
async function commitName(page, value) {
  await page.fill("#f-name", value);
  await page.locator("#f-name").blur(); // settled edit → delegated `change` → commit()
}
async function undo(page) { await page.click("#undo-btn"); }
async function redo(page) { await page.click("#redo-btn"); }
async function saveProject(page) {
  const [download] = await Promise.all([page.waitForEvent("download"), page.click("#save-project-btn")]);
  return readFileSync(await download.path(), "utf8");
}
async function openProject(page, text, fname = "probe.project.json") {
  await page.setInputFiles("#open-project-input", { name: fname, mimeType: "application/json", buffer: Buffer.from(text) });
  await page.waitForTimeout(100); // FileReader is async
}

// ---- probes ----------------------------------------------------------------
const PROBES = [
  {
    id: "reload-persists-draft", needs: "ENH-3487", acs: ["ENH-3487 reload persistence", "FEAT-3488 AC-10 storage reload"],
    async run(browser) {
      const { page } = await newPage(browser);
      await commitName(page, "probe-reload");
      await page.click("#add-rule");
      const before = await ruleCount(page);
      await page.reload();
      await page.waitForSelector("#rule-list", { state: "attached" });
      assert((await name(page)) === "probe-reload", "loop name did not survive reload");
      assert((await ruleCount(page)) === before, "rule count did not survive reload");
    },
  },
  {
    id: "mode-switch-preserves-drafts", needs: "ENH-3487", acs: ["FEAT-3488 AC-10 active/inactive mode switches"],
    async run(browser) {
      const { page } = await newPage(browser);
      await commitName(page, "probe-dt");
      await page.selectOption("#mode-switch", "rubric");
      assert((await mode(page)) === "rubric", "mode did not switch");
      await commitName(page, "probe-rubric");
      await page.selectOption("#mode-switch", "decision_table");
      assert((await name(page)) === "probe-dt", "decision_table draft lost on switch");
      await page.selectOption("#mode-switch", "rubric");
      assert((await name(page)) === "probe-rubric", "rubric draft lost on switch");
      await page.reload();
      await page.waitForSelector("#rule-list", { state: "attached" });
      assert((await mode(page)) === "rubric", "active mode not restored after reload");
      assert((await name(page)) === "probe-rubric", "active draft not restored after reload");
    },
  },
  {
    id: "undo-redo-buttons-and-keys", needs: "ENH-3487", acs: ["FEAT-3488 AC-10 undo/redo"],
    async run(browser) {
      const { page } = await newPage(browser);
      const base = await ruleCount(page);
      assert(await page.locator("#undo-btn").isDisabled(), "undo enabled before any edit");
      await page.click("#add-rule");
      assert((await ruleCount(page)) === base + 1, "add-rule did not add");
      await undo(page);
      assert((await ruleCount(page)) === base, "undo button did not restore");
      await redo(page);
      assert((await ruleCount(page)) === base + 1, "redo button did not reapply");
      await page.locator("body").click({ position: { x: 1, y: 1 } });
      await page.keyboard.press(process.platform === "darwin" ? "Meta+z" : "Control+z");
      assert((await ruleCount(page)) === base, "keyboard undo did not fire outside editable");
      await page.keyboard.press(process.platform === "darwin" ? "Meta+Shift+z" : "Control+Shift+z");
      assert((await ruleCount(page)) === base + 1, "keyboard redo did not fire");
      await page.focus("#f-name");
      await page.keyboard.press(process.platform === "darwin" ? "Meta+z" : "Control+z");
      assert((await ruleCount(page)) === base + 1, "keyboard undo fired while focus in an input");
    },
  },
  {
    id: "start-blank-then-undo", needs: "ENH-3487", acs: ["FEAT-3488 AC-1 preset/clear + one undo", "AC-10 start-blank atomic + undo"],
    async run(browser) {
      const { page } = await newPage(browser);
      const rules = await ruleCount(page);
      const n = await name(page);
      assert(rules > 0, "seed example has no rules to clear");
      await page.click("#start-blank-btn");
      assert((await ruleCount(page)) === 0, "start blank left rules");
      await undo(page);
      assert((await ruleCount(page)) === rules && (await name(page)) === n, "one undo did not restore pre-blank draft");
    },
  },
  {
    id: "preset-then-one-undo", needs: "ENH-3487", acs: ["FEAT-3488 AC-1 applying a preset … one undo restores", "AC-10 preset clears only destination"],
    async run(browser) {
      const { page } = await newPage(browser);
      await commitName(page, "probe-before-preset");
      const m0 = await mode(page);
      const presets = page.locator("#preset-row button:not(#start-blank-btn)");
      assert((await presets.count()) > 0, "no preset buttons rendered");
      await presets.first().click();
      const changed = (await name(page)) !== "probe-before-preset" || (await mode(page)) !== m0;
      assert(changed, "preset applied nothing observable");
      await undo(page);
      assert((await mode(page)) === m0, "one undo did not restore active mode");
      assert((await name(page)) === "probe-before-preset", "one undo did not restore prior draft");
    },
  },
  {
    id: "save-open-roundtrip", needs: "ENH-3487", acs: ["FEAT-3488 AC-1 survive Save/Open", "AC-10 Save/Open"],
    async run(browser) {
      const { page } = await newPage(browser);
      await commitName(page, "probe-saved");
      await page.click("#add-rule");
      const rules = await ruleCount(page);
      const text = await saveProject(page);
      assert(/Project saved/.test(await liveStatus(page)), "no 'Project saved' feedback");
      const project = JSON.parse(text);
      assert(project.schemaVersion === 1, `schemaVersion must stay 1 (got ${project.schemaVersion})`);
      // Mutate, then Open the saved file and expect the saved state back.
      await page.click("#start-blank-btn");
      assert((await ruleCount(page)) === 0, "start blank precondition failed");
      await openProject(page, text);
      assert(/Project opened/.test(await liveStatus(page)), `open feedback: ${await liveStatus(page)}`);
      assert((await name(page)) === "probe-saved", "name not restored by Open");
      assert((await ruleCount(page)) === rules, "rules not restored by Open");
      // Persisted after Open, too.
      await page.reload();
      await page.waitForSelector("#rule-list", { state: "attached" });
      assert((await name(page)) === "probe-saved", "opened project not persisted across reload");
    },
  },
  {
    id: "open-corrupt-file-leaves-project", needs: "ENH-3487", acs: ["ENH-3487 corrupt/newer project file rejected without data loss"],
    async run(browser) {
      const { page } = await newPage(browser);
      await commitName(page, "probe-intact");
      await openProject(page, "{ not json");
      assert(/Could not open project/.test(await liveStatus(page)), `bad JSON: ${await liveStatus(page)}`);
      assert((await name(page)) === "probe-intact", "bad JSON altered project");
      await openProject(page, JSON.stringify({ schemaVersion: 99, projectId: "x", activeMode: "rubric", drafts: {} }));
      assert(/newer than supported/.test(await liveStatus(page)), `newer schema: ${await liveStatus(page)}`);
      assert((await name(page)) === "probe-intact", "newer schema altered project");
    },
  },
  {
    id: "open-project-with-unknown-sibling-metadata", needs: "FEAT-3488", acs: ["FEAT-3488 AC-1 project saved with scenarios opens in a pre-change page", "AC-10 unknown sibling metadata"],
    async run(browser) {
      const { page } = await newPage(browser);
      const text = await saveProject(page);
      const project = JSON.parse(text);
      for (const m of Object.keys(project.drafts)) {
        // Structurally valid per FEAT-3488's storage contract ({id, name, input,
        // expectedTarget}); the input is deliberately semantically empty so the
        // probe fails only on wrapper persistence, never on suite validation.
        project.drafts[m].scenarios = [{ id: "probe-case-1", name: "case-1", input: {}, expectedTarget: null }];
        project.drafts[m].futureKey = { keep: true };
      }
      await openProject(page, JSON.stringify(project));
      assert(/Project opened/.test(await liveStatus(page)), `open with siblings: ${await liveStatus(page)}`);
      const again = JSON.parse(await saveProject(page));
      const d = again.drafts[again.activeMode];
      assert(Array.isArray(d.scenarios) && d.scenarios.length === 1, "scenarios sibling dropped on Save/Open");
      assert(d.futureKey && d.futureKey.keep === true, "unknown sibling metadata dropped on Save/Open");
    },
  },
  {
    id: "corrupt-stored-draft-falls-back", needs: "ENH-3487", acs: ["ENH-3487 corrupt stored draft → seed + diagnostic, payload preserved"],
    async run(browser) {
      const junk = JSON.stringify({ model: { mode: 5, rules: "nope" } });
      const { page } = await newPage(browser, {
        initScript: `try { localStorage.setItem("ll-policy-builder-draft-decision_table", ${JSON.stringify(junk)});
                     localStorage.setItem("ll-policy-builder-meta", JSON.stringify({activeMode:"decision_table", schemaVersion:1})); } catch (e) {}`,
      });
      assert(/could not be restored/.test(await liveStatus(page)), `fallback status: ${await liveStatus(page)}`);
      assert((await ruleCount(page)) > 0, "seed example not shown after corrupt draft");
      const stillThere = await page.evaluate(() => localStorage.getItem("ll-policy-builder-draft-decision_table"));
      assert(stillThere === junk, "rejected payload was overwritten before any commit");
    },
  },
  {
    id: "storage-disabled-degrades", needs: "ENH-3487", acs: ["ENH-3487 storage unavailable → one live-region warning, authoring continues"],
    async run(browser) {
      const { page, errors } = await newPage(browser, {
        initScript: `Storage.prototype.setItem = function () { throw new Error("QuotaExceededError"); };`,
      });
      await commitName(page, "probe-nostorage");
      assert(/storage is unavailable/i.test(await liveStatus(page)), `no storage warning: ${await liveStatus(page)}`);
      await page.click("#add-rule");
      assert(errors.length === 0, `page errors with storage disabled: ${errors.join(" | ")}`);
      const text = await saveProject(page);
      assert(JSON.parse(text).drafts.decision_table.model.name === "probe-nostorage", "Save project broken with storage disabled");
    },
  },
  // ---- FEAT-3488 scenario-suite probes (BLOCKED until selectors are set) ----
  {
    id: "scenario-suite-survives-save-open-reload-undo", needs: "FEAT-3488", acs: ["FEAT-3488 AC-1", "AC-10"],
    async run(browser) {
      needSelectors("addCaseBtn", "caseNameInput", "caseList");
      const S = SCENARIO_SELECTORS;
      const { page } = await newPage(browser);
      await page.click(S.addCaseBtn);
      await page.fill(S.caseNameInput, "case-alpha");
      await page.locator(S.caseNameInput).blur();
      const cases = () => page.locator(`${S.caseList} > *`).count();
      assert((await cases()) === 1, "case not added");
      await page.reload(); await page.waitForSelector("#rule-list", { state: "attached" });
      assert((await cases()) === 1, "case lost on reload");
      const text = await saveProject(page);
      assert(JSON.parse(text).drafts.decision_table.scenarios.length === 1, "scenarios not in saved project");
      await page.click("#start-blank-btn");
      assert((await cases()) === 0, "start blank did not clear suite");
      await undo(page);
      assert((await cases()) === 1, "one undo did not restore suite");
      await page.selectOption("#mode-switch", "rubric");
      await page.selectOption("#mode-switch", "decision_table");
      assert((await cases()) === 1, "suite lost across mode switch");
      await openProject(page, text);
      assert((await cases()) === 1, "suite not restored by Open");
    },
  },
  {
    id: "preset-clears-only-destination-suite", needs: "FEAT-3488", acs: ["FEAT-3488 AC-1 preset clears only that draft's suite", "AC-10"],
    async run(browser) {
      needSelectors("addCaseBtn", "caseNameInput", "caseList");
      const S = SCENARIO_SELECTORS;
      const { page } = await newPage(browser);
      const cases = () => page.locator(`${S.caseList} > *`).count();
      await page.click(S.addCaseBtn); await page.fill(S.caseNameInput, "dt-case"); await page.locator(S.caseNameInput).blur();
      await page.selectOption("#mode-switch", "rubric");
      await page.click(S.addCaseBtn); await page.fill(S.caseNameInput, "rubric-case"); await page.locator(S.caseNameInput).blur();
      await page.selectOption("#mode-switch", "decision_table");
      const presets = page.locator("#preset-row button:not(#start-blank-btn)");
      await presets.first().click();
      const m = await mode(page);
      assert((await cases()) === 0, `preset did not clear destination (${m}) suite`);
      const other = m === "rubric" ? "decision_table" : "rubric";
      await page.selectOption("#mode-switch", other);
      assert((await cases()) === 1, `preset cleared the non-destination (${other}) suite`);
      await page.selectOption("#mode-switch", m);
      await undo(page);
      await undo(page); // second undo reverts our own mode switches; assert on the suite, not the count
      const restored = await page.evaluate(() => JSON.parse(localStorage.getItem("ll-policy-builder-draft-" + document.getElementById("mode-switch").value) || "{}"));
      assert(Array.isArray(restored.scenarios) && restored.scenarios.length === 1, "undo did not restore the cleared suite");
    },
  },
  {
    id: "run-all-totals-and-edit-invalidation", needs: "FEAT-3488", acs: ["FEAT-3488 AC-5 totals", "AC-9 editing invalidates results"],
    async run(browser) {
      needSelectors("addCaseBtn", "runAllBtn", "totals");
      const S = SCENARIO_SELECTORS;
      const { page } = await newPage(browser);
      await page.click(S.addCaseBtn);
      await page.click(S.runAllBtn);
      const t = await page.locator(S.totals).textContent();
      assert(/unasserted/i.test(t), `totals lack unasserted bucket: ${t}`);
      await page.click("#add-rule");
      const t2 = await page.locator(S.totals).textContent();
      assert(t2 !== t, "editing the policy did not invalidate displayed results");
    },
  },
  {
    id: "local-issue-import-offline", needs: "FEAT-3503", acs: ["FEAT-3503 issue-file import: BOM/CRLF, body ignored, fence diagnostics, atomic, undoable"],
    async run(browser) {
      needSelectors("importIssueInput", "importDiagnostics", "caseList");
      const S = SCENARIO_SELECTORS;
      const { page } = await newPage(browser);
      const cases = () => page.locator(`${S.caseList} > *`).count();
      const good = "﻿---\r\nid: BUG-1\r\ntype: BUG\r\npriority: P2\r\nstatus: open\r\n---\r\n# BUG-1\r\n\r\nbody { not: parsed }\r\n";
      await page.setInputFiles(S.importIssueInput, { name: "P2-BUG-1-x.md", mimeType: "text/markdown", buffer: Buffer.from(good) });
      await page.waitForTimeout(100);
      assert((await cases()) === 1, "BOM/CRLF issue file did not import one case");
      await page.setInputFiles(S.importIssueInput, { name: "bad.md", mimeType: "text/markdown", buffer: Buffer.from("---\nid: BUG-2\nno closing fence\n") });
      await page.waitForTimeout(100);
      assert(/fence|frontmatter/i.test(await page.locator(S.importDiagnostics).textContent()), "unclosed fence gave no diagnostic");
      assert((await cases()) === 1, "failed import altered the suite");
      await undo(page);
      assert((await cases()) === 0, "successful import was not undoable");
    },
  },
];

// ---- runner ----------------------------------------------------------------
const pw = loadPlaywright();
if (!pw || !pw.mod.chromium) {
  console.log("PLAYWRIGHT_MISSING: set LL_PLAYWRIGHT_ROOT or NODE_PATH to a directory containing `playwright`");
  console.log("BROWSER_PROBES_BLOCKED");
  process.exit(2);
}
const results = [];
let browser;
try {
  browser = await pw.mod.chromium.launch({ headless: true });
} catch (e) {
  console.log(`PLAYWRIGHT_LAUNCH_FAILED: ${e.message.split("\n")[0]} (try: npx playwright install chromium)`);
  console.log("BROWSER_PROBES_BLOCKED");
  process.exit(2);
}
for (const probe of PROBES) {
  const started = Date.now();
  let status = "PASS", reason = "";
  try { await probe.run(browser); }
  catch (e) { status = e instanceof Blocked ? "BLOCKED" : "FAIL"; reason = e.message.split("\n")[0]; }
  results.push({ id: probe.id, needs: probe.needs, acs: probe.acs, status, reason, ms: Date.now() - started });
  console.log(`PROBE ${probe.id} [${probe.needs}] ${status}${reason ? " — " + reason : ""}`);
}
await browser.close();
const count = (s) => results.filter((r) => r.status === s).length;
const summary = { html: HTML_PATH, playwright: pw.from, pass: count("PASS"), fail: count("FAIL"), blocked: count("BLOCKED"), results };
mkdirSync(dirname(REPORT_PATH), { recursive: true });
writeFileSync(REPORT_PATH, JSON.stringify(summary, null, 2) + "\n");
console.log(`BROWSER_PROBES: pass=${summary.pass} fail=${summary.fail} blocked=${summary.blocked} report=${REPORT_PATH}`);
if (summary.fail > 0) { console.log("BROWSER_PROBES_FAILED"); process.exit(1); }
if (summary.blocked > 0) { console.log("BROWSER_PROBES_BLOCKED"); process.exit(2); }
console.log("BROWSER_PROBES_PASSED");
