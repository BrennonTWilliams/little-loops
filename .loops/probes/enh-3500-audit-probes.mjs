#!/usr/bin/env node
// Evidence collector for ENH-3500 (policy-router builder cross-mode design/UX audit).
//
// Collects screenshots + DOM JSON for a case manifest (fixture x mode x theme x
// width, plus 601px comparisons and connected-state cases) under <run_dir>. A
// successful run means EVIDENCE COLLECTION completed — it is not a UX verdict;
// review dispositions live in the issue's ## Audit Coverage ledger.
//
// Dev-only, on-demand (never a pytest gate). Playwright resolves like the
// enh-3507 probe (LL_PLAYWRIGHT_ROOT / NODE_PATH / `npm root -g`).
// Usage: node enh-3500-audit-probes.mjs [--check | <run_dir> [port]]
// stdout ends with AUDIT_EVIDENCE_COLLECTED | AUDIT_EVIDENCE_INCOMPLETE.
import { createRequire } from "node:module";
import { execSync, spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { resolve, join } from "node:path";

const URL_WAIT_MS = 20000;
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

const [, , firstArg, portArg] = process.argv;
if (firstArg === "--check") {
  const found = loadPlaywright();
  if (!found || !found.mod.chromium) { console.log("PLAYWRIGHT_MISSING"); process.exit(2); }
  try { const b = await found.mod.chromium.launch({ headless: true }); await b.close(); }
  catch (e) { console.log(`PLAYWRIGHT_MISSING: chromium launch failed: ${e.message.split("\n")[0]}`); process.exit(2); }
  console.log(`PLAYWRIGHT_OK ${found.from}`); process.exit(0);
}
if (!firstArg) { console.error("usage: enh-3500-audit-probes.mjs [--check | <run_dir> [port]]"); process.exit(3); }
const RUN_DIR = resolve(firstArg);
const PORT = Number(portArg) || 8799;
const SHOTS = join(RUN_DIR, "evidence");
mkdirSync(SHOTS, { recursive: true });

const pw = loadPlaywright();
if (!pw) { console.log("PLAYWRIGHT_MISSING"); console.log("AUDIT_EVIDENCE_INCOMPLETE"); process.exit(2); }

// ---- surfaces ----------------------------------------------------------------
const OFFLINE_DIR = join(RUN_DIR, "offline");
execSync(`ll-artifact policy-builder -o ${JSON.stringify(OFFLINE_DIR)}`, { stdio: "ignore" });
const OFFLINE_URL = "file://" + execSync(`ls ${JSON.stringify(OFFLINE_DIR)}/*.html | head -1`, { encoding: "utf8", shell: "/bin/bash" }).trim();

let server = null;
function startServer() {
  return new Promise((res, rej) => {
    server = spawn("ll-artifact", ["serve", "--policy-builder", "--port", String(PORT)], { env: { ...process.env, PYTHONUNBUFFERED: "1" }, stdio: ["ignore", "pipe", "pipe"] });
    let buf = "";
    const t = setTimeout(() => rej(new Error("no builder URL")), URL_WAIT_MS);
    server.stdout.on("data", (d) => { buf += d; const m = buf.match(/^(http:\/\/\S+\/policy-builder)\s*$/m); if (m) { clearTimeout(t); res(m[1]); } });
    server.on("exit", (c) => { clearTimeout(t); rej(new Error(`server exited ${c}`)); });
  });
}
process.on("exit", () => { if (server && !server.killed) server.kill("SIGTERM"); });

// ---- in-page collector -------------------------------------------------------
const COLLECT = () => {
  const vis = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const q = (s) => [...document.querySelectorAll(s)];
  const outline = q("h1,h2,h3,legend,summary").filter(vis).map((e) => `${e.tagName.toLowerCase()}:${e.textContent.trim().slice(0, 60)}`);
  const disabled = q("button,input,select,textarea").filter((e) => e.disabled && vis(e)).map((e) => ({
    id: e.id || e.className || e.tagName, text: (e.textContent || e.value || "").trim().slice(0, 40), title: e.title || null,
    ariaDescribedby: e.getAttribute("aria-describedby"), ariaDisabled: e.getAttribute("aria-disabled"),
  }));
  const aria = q("[role],[aria-live],[aria-label],[aria-describedby],[aria-disabled],[aria-invalid]").map((e) => ({
    el: e.id || e.tagName.toLowerCase(), role: e.getAttribute("role"), live: e.getAttribute("aria-live"), label: e.getAttribute("aria-label"),
  }));
  const lists = {};
  for (const id of ["dim-list", "rule-list", "outcome-list", "scenario-list"]) {
    const e = document.getElementById(id);
    lists[id] = e ? { visible: vis(e), children: e.children.length, text: e.textContent.trim().slice(0, 80) } : null;
  }
  lists.scenarioSummary = document.getElementById("scenario-summary")?.textContent.trim();
  lists.scenarioCoverage = document.getElementById("scenario-coverage")?.textContent.trim().slice(0, 120);
  const classes = {};
  for (const e of q("[class]")) for (const c of e.classList) if (/^(msg-|is-)/.test(c)) classes[c] = (classes[c] || 0) + 1;
  const messages = q("#messages li").map((e) => ({ cls: e.className, text: e.textContent.trim().slice(0, 100) }));
  const vw = document.documentElement.clientWidth;
  const overflow = { docScrollWidth: document.documentElement.scrollWidth, clientWidth: vw, horizontalScroll: document.documentElement.scrollWidth > vw + 1,
    clipped: q("button,input,select,textarea,pre,li").filter(vis).filter((e) => e.getBoundingClientRect().right > vw + 1).slice(0, 8).map((e) => e.id || e.tagName.toLowerCase()) };
  const live = { importDiagnostics: document.getElementById("import-diagnostics")?.textContent.trim(), liveStatus: document.getElementById("live-status")?.textContent.trim() };
  const conn = document.getElementById("connected-panel");
  const connected = conn ? {
    panelVisible: vis(conn), unavailable: document.getElementById("conn-unavailable")?.textContent.trim() || null,
    unavailableVisible: vis(document.getElementById("conn-unavailable")), bodyVisible: vis(document.getElementById("conn-body")),
    status: document.getElementById("conn-status")?.textContent.trim().slice(0, 300), statusClass: document.getElementById("conn-status")?.className,
    notices: q("#conn-notices li").map((e) => e.textContent.trim().slice(0, 120)), reviewInfo: document.getElementById("conn-review-info")?.textContent.trim(),
    issueNote: document.getElementById("conn-issue-note")?.textContent.trim(),
    buttons: ["conn-review-btn", "conn-submit-btn", "conn-again-btn", "conn-retry-btn", "conn-refresh-btn", "conn-issues-reload"].map((id) => { const e = document.getElementById(id); return { id, visible: vis(e), disabled: e.disabled }; }),
  } : null;
  const focused = document.activeElement ? (document.activeElement.id || document.activeElement.tagName.toLowerCase()) : null;
  return { outline, disabled, aria, lists, classes, messages, overflow, live, connected, focused, theme: document.documentElement.getAttribute("data-theme") };
};

const LONG = "Extremely-long-unbroken-identifier-".repeat(6) + " and a long descriptive sentence that should wrap across several lines in every narrow layout without clipping.";
const MODES = ["decision_table", "rubric", "issue_lifecycle"];
const THEMES = ["light", "dark"];
const WIDTHS = [375, 600, 601, 1280];
// 601px is only a targeted comparison for populated/long-content layouts and the connected panel.
// Mutate the saved project JSON and re-open it through the supported Open-project UI path.
async function mutateProject(p, mode, fn) {
  const [dl] = await Promise.all([p.waitForEvent("download"), p.click("#save-project-btn")]);
  const proj = JSON.parse(readFileSync(await dl.path(), "utf8"));
  fn(proj.drafts[mode]);
  await p.setInputFiles("#open-project-input", { name: "audit.project.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(proj)) });
  await p.waitForFunction(() => /Project opened/.test(document.getElementById("live-status").textContent), null, { timeout: 5000 });
}
const FIXTURES = {
  populated: async () => {},
  "start-blank": async (p) => { await p.click("#start-blank-btn"); },
  "empty-dimensions": async (p, m) => { await mutateProject(p, m, (d) => { d.model.dimensions = []; }); },
  "empty-rules": async (p, m) => { await mutateProject(p, m, (d) => { d.model.rules = []; }); },
  "empty-outcomes": async (p, m) => { await mutateProject(p, m, (d) => { d.model.outcomes = []; }); },
  "invalid-model": async (p, m) => { await mutateProject(p, m, (d) => { d.model.dimensions[0].type = "bogus"; }); },
  "long-content": async (p) => {
    await p.fill("#f-name", LONG.slice(0, 120)); await p.dispatchEvent("#f-name", "change");
    await p.fill("#f-desc", LONG); await p.dispatchEvent("#f-desc", "change");
    await p.fill("#dim-name", LONG.slice(0, 80)); await p.click("#add-dim");
  },
  "scenarios-empty": async () => {}, // default seed has no scenarios: the empty-suite state itself
  "scenarios-populated": async (p) => { await p.click("#add-scenario-btn"); await p.click("#add-scenario-btn"); },
  "scenarios-run": async (p) => { await p.click("#add-scenario-btn"); await p.click("#run-all-btn"); await p.waitForTimeout(150); },
};
const WIDE_ONLY_FIXTURES = new Set(["populated", "long-content"]);

const manifest = [];
const results = [];
function pad(w) { return `w${w}`; }

async function withPage(browser, url, { mode, theme, width }, fn) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } }); // fresh storage per case
  const page = await ctx.newPage();
  try {
    await page.goto(url);
    await page.evaluate((t) => { localStorage.setItem("ll-policy-builder-theme", t); document.documentElement.setAttribute("data-theme", t); }, theme);
    if (mode) { await page.selectOption("#mode-switch", mode); await page.waitForTimeout(50); }
    return await fn(page);
  } finally { await ctx.close(); }
}

async function capture(page, id, extra = {}) {
  const data = await page.evaluate(COLLECT);
  const dims = page.viewportSize();
  writeFileSync(join(SHOTS, `${id}.json`), JSON.stringify({ id, viewport: dims, ...extra, ...data }, null, 2));
  await page.screenshot({ path: join(SHOTS, `${id}.png`), fullPage: true });
  return data;
}

// CASE_ONLY=<regex> re-runs matching cases only and merges them into an existing case-manifest.json.
const CASE_ONLY = process.env.CASE_ONLY ? new RegExp(process.env.CASE_ONLY) : null;
async function record(entry, run) {
  if (CASE_ONLY && !CASE_ONLY.test(entry.id)) return;
  manifest.push(entry);
  // One retry: a cold first connected case can outlast the issue-list wait; a repeat failure is recorded.
  for (let attempt = 1; attempt <= 2; attempt++) {
    try { await run(); results.push({ id: entry.id, status: "collected", attempts: attempt }); console.log(`CASE ${entry.id} collected`); return; }
    catch (e) {
      if (attempt === 2) { results.push({ id: entry.id, status: "error", reason: e.message.split("\n")[0] }); console.log(`CASE ${entry.id} ERROR ${e.message.split("\n")[0]}`); }
    }
  }
}

// ---- connected helpers (stubs mirror enh-3507 probe) ----------------------------
const posted = { bindings: {} };
const rbBody = (over) => ({ requestId: "x", queueId: "qstub0001", status: "awaiting_approval", bindings: posted.bindings, loopInstanceId: "loop-9", runDir: "/runs/9", result: null, ...over });
async function stubIssues(page, mode) {
  await page.route("**/issues", (route) => {
    if (mode === "fail") return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { code: "server_error", message: "Audit issue-list failure" } }) });
    if (mode === "empty") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ issues: [] }) });
    return route.continue();
  });
}
async function stubPost(page, kind, warnings) {
  await page.route("**/run-request", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const b = route.request().postDataJSON();
    posted.bindings = { issueId: b.issueId, revisionId: b.revisionId };
    if (kind === "abort") return route.abort();
    if (kind === "reject") return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: { code: "validation_failed", message: "Audit validation failure" } }) });
    const body = { requestId: "x", queueId: "qstub0001", created: kind !== "existing" };
    if (kind === "accepted") body.warnings = warnings || [];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}
async function stubReadback(page, get) {
  await page.route("**/run-request/*", (route) => route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(get()) }));
}
async function pickIssue(page) {
  await page.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1, null, { timeout: 90000 }); // the real issue scan takes seconds
  const v = await page.$eval("#conn-issue option:nth-child(2)", (o) => o.value);
  await page.selectOption("#conn-issue", v);
}
async function review(page) { await page.click("#conn-review-btn"); await page.waitForFunction(() => !document.querySelector("#conn-submit-btn").disabled); }

const CONNECTED_STATES = {
  "issues-loading": async (p) => { await p.route("**/issues", () => new Promise(() => {})); await p.reload(); await p.selectOption("#mode-switch", "issue_lifecycle"); await p.waitForTimeout(300); },
  "issues-empty": async (p) => { await stubIssues(p, "empty"); await p.reload(); await p.selectOption("#mode-switch", "issue_lifecycle"); await p.waitForTimeout(400); },
  "issues-failed": async (p) => { await stubIssues(p, "fail"); await p.reload(); await p.selectOption("#mode-switch", "issue_lifecycle"); await p.waitForTimeout(400); },
  "issue-selected": async (p) => { await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); },
  "review-none": async (p) => { await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); },
  "review-ready": async (p) => { await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); },
  "review-refused": async (p) => { await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await mutateProject(p, "issue_lifecycle", (d) => { d.model.dimensions[0].type = "bogus"; }); await p.selectOption("#conn-issue", { index: 1 }); await p.click("#conn-review-btn"); await p.waitForTimeout(600); },
  "review-draft-edited": async (p) => { await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.fill("#f-name", "audit-edited"); await p.dispatchEvent("#f-name", "change"); },
  "delivery-rejected": async (p) => { await stubPost(p, "reject"); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.waitForTimeout(500); },
  "delivery-outcome-unknown": async (p) => { await stubPost(p, "abort"); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.waitForTimeout(600); },
  "accepted-no-warnings": async (p) => { await stubPost(p, "accepted", []); await stubReadback(p, () => rbBody({})); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.waitForTimeout(600); },
  "accepted-warnings": async (p) => { await stubPost(p, "accepted", [{ message: "State is not reachable from initial state" }]); await stubReadback(p, () => rbBody({})); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.waitForTimeout(600); },
  "accepted-warnings-unavailable": async (p) => { await stubPost(p, "existing"); await stubReadback(p, () => rbBody({})); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.waitForTimeout(600); },
  "readback-awaiting_approval": async (p) => { await stubPost(p, "accepted", []); await stubReadback(p, () => rbBody({ status: "awaiting_approval" })); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.waitForTimeout(600); },
  "readback-done": async (p) => { await stubPost(p, "accepted", []); await stubReadback(p, () => rbBody({ status: "done", result: { exit_code: 0, timed_out: false, error: null, stdout: LONG, stderr: "" } })); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.click("#conn-refresh-btn"); await p.waitForTimeout(400); },
  "readback-failed": async (p) => { await stubPost(p, "accepted", []); await stubReadback(p, () => rbBody({ status: "failed", result: { exit_code: 1, timed_out: false, error: LONG, stdout: "", stderr: LONG } })); await p.selectOption("#mode-switch", "issue_lifecycle"); await pickIssue(p); await review(p); await p.click("#conn-submit-btn"); await p.click("#conn-refresh-btn"); await p.waitForTimeout(400); },
};

async function keyboardTrace(browser, url, name, setup) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const trace = [];
  try {
    await page.goto(url);
    await setup(page);
    await page.evaluate(() => {
      window.__liveLog = [];
      for (const id of ["conn-status", "conn-notices", "live-status", "import-diagnostics", "conn-review-info", "conn-issue-note"]) {
        const el = document.getElementById(id);
        if (el) new MutationObserver(() => window.__liveLog.push({ id, text: el.textContent.trim().slice(0, 160), live: el.closest("[aria-live]")?.getAttribute("aria-live") || null })).observe(el, { childList: true, subtree: true, characterData: true });
      }
    });
    const act = async (label, fn) => {
      const before = await page.evaluate(() => document.activeElement?.id || document.activeElement?.tagName);
      await fn();
      await page.waitForTimeout(400);
      const after = await page.evaluate(() => document.activeElement?.id || document.activeElement?.tagName);
      trace.push({ label, before, after });
    };
    await page.focus("#conn-issue");
    await act("keyboard: select issue (ArrowDown x2)", async () => { await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowDown"); });
    if (!(await page.$eval("#conn-issue", (e) => e.value))) {
      trace.push({ label: "keyboard ArrowDown did not select an issue in headless Chromium; used selectOption fallback" });
      await page.selectOption("#conn-issue", { index: 1 });
    }
    for (let i = 0; i < 4; i++) await act(`Tab #${i + 1}`, () => page.keyboard.press("Tab"));
    await page.focus("#conn-review-btn");
    await page.screenshot({ path: join(SHOTS, `${name}-focus-review.png`) });
    await act("keyboard: Enter on Review", () => page.keyboard.press("Enter"));
    await page.waitForTimeout(500);
    const ok = await page.evaluate(() => !document.querySelector("#conn-submit-btn").disabled);
    trace.push({ label: "submit enabled after review", value: ok });
    if (ok) {
      await page.focus("#conn-submit-btn");
      await page.screenshot({ path: join(SHOTS, `${name}-focus-submit.png`) });
      await act("keyboard: Enter on Submit", () => page.keyboard.press("Enter"));
    }
    for (const id of ["conn-again-btn", "conn-retry-btn", "conn-refresh-btn"]) {
      const shown = await page.evaluate((i) => !document.getElementById(i).hidden, id);
      if (shown) { await page.focus(`#${id}`); await act(`keyboard: Space on #${id}`, () => page.keyboard.press("Space")); }
    }
    const live = await page.evaluate(() => window.__liveLog);
    writeFileSync(join(SHOTS, `${name}-keyboard.json`), JSON.stringify({ name, label: "DOM announcement support only; no manual screen-reader check performed", trace, liveRegionChanges: live, final: await page.evaluate(COLLECT) }, null, 2));
  } finally { await ctx.close(); }
}

// ---- run -----------------------------------------------------------------------
let servedUrl;
try { servedUrl = await startServer(); } catch (e) { console.log(`SERVER_START_FAILED: ${e.message}`); console.log("AUDIT_EVIDENCE_INCOMPLETE"); process.exit(3); }
const browser = await pw.mod.chromium.launch({ headless: true });
// Warm the served issue list once: the first real /issues scan is slow enough to outlast a case's wait.
{
  const wctx = await browser.newContext();
  const wp = await wctx.newPage();
  await wp.goto(servedUrl);
  await wp.selectOption("#mode-switch", "issue_lifecycle");
  await wp.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1, null, { timeout: 180000 }).catch(() => {});
  await wctx.close();
}
const meta = { sourceRevision: execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim(), dirty: execSync("git status --porcelain scripts/ | wc -l", { encoding: "utf8" }).trim() !== "0",
  browser: `chromium ${browser.version()}`, playwright: pw.from, offlineUrl: OFFLINE_URL, servedUrl,
  tokenProfile: (() => { try { return JSON.parse(readFileSync(".ll/ll-config.json", "utf8")).artifacts?.design_tokens?.profile ?? "default (config not set)"; } catch { return "unknown"; } })(),
  widths: WIDTHS, themes: THEMES, startedAt: new Date().toISOString() };

// 1. Authoring matrix (offline) + served populated comparison
for (const [fx, setup] of Object.entries(FIXTURES)) {
  for (const mode of MODES) for (const theme of THEMES) for (const width of WIDTHS) {
    if (width === 601 && !WIDE_ONLY_FIXTURES.has(fx)) continue;
    const id = `auth-${fx}-${mode}-${theme}-${pad(width)}-offline`;
    await record({ id, surface: "offline", fixture: fx, mode, theme, width }, () => withPage(browser, OFFLINE_URL, { mode, theme, width }, async (p) => { await setup(p, mode); await capture(p, id, { surface: "offline", fixture: fx, mode }); }));
  }
}
for (const mode of MODES) for (const theme of THEMES) for (const width of WIDTHS) {
  const id = `auth-populated-${mode}-${theme}-${pad(width)}-served`;
  await record({ id, surface: "served", fixture: "populated", mode, theme, width }, () => withPage(browser, servedUrl, { mode, theme, width }, async (p) => { await capture(p, id, { surface: "served", fixture: "populated", mode }); }));
}
// 2. Connected panel: offline absence, served unavailable (non-lifecycle), states
for (const theme of THEMES) for (const width of WIDTHS) {
  const idOff = `conn-offline-absence-${theme}-${pad(width)}`;
  await record({ id: idOff, surface: "offline", fixture: "offline-panel-absence", mode: "issue_lifecycle", theme, width }, () => withPage(browser, OFFLINE_URL, { mode: "issue_lifecycle", theme, width }, (p) => capture(p, idOff, { surface: "offline" })));
  for (const mode of ["decision_table", "rubric"]) {
    const id = `conn-unavailable-${mode}-${theme}-${pad(width)}`;
    await record({ id, surface: "served", fixture: "served-unavailable", mode, theme, width }, () => withPage(browser, servedUrl, { mode, theme, width }, (p) => capture(p, id, { surface: "served" })));
  }
  for (const [state, setup] of Object.entries(CONNECTED_STATES)) {
    const id = `conn-${state}-${theme}-${pad(width)}`;
    await record({ id, surface: "served", fixture: state, mode: "issue_lifecycle", theme, width }, async () => {
      const ctx = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await ctx.newPage();
      try {
        await page.goto(servedUrl);
        await page.evaluate((t) => { localStorage.setItem("ll-policy-builder-theme", t); document.documentElement.setAttribute("data-theme", t); }, theme);
        await setup(page);
        await capture(page, id, { surface: "served", fixture: state });
      } finally { await ctx.close(); }
    });
  }
}
// 3. 601px connected panel comparison (both themes) for representative states
for (const theme of THEMES) for (const state of ["review-ready", "delivery-outcome-unknown", "accepted-warnings"]) {
  const id = `conn-${state}-${theme}-w601`;
  await record({ id, surface: "served", fixture: state, mode: "issue_lifecycle", theme, width: 601 }, async () => {
    const ctx = await browser.newContext({ viewport: { width: 601, height: 900 } });
    const page = await ctx.newPage();
    try { await page.goto(servedUrl); await page.evaluate((t) => { localStorage.setItem("ll-policy-builder-theme", t); document.documentElement.setAttribute("data-theme", t); }, theme); await CONNECTED_STATES[state](page); await capture(page, id, { surface: "served", fixture: state }); }
    finally { await ctx.close(); }
  });
}
// 4. Keyboard / focus / live-region traces
for (const [name, pre] of [
  ["kb-happy-path", async (p) => { await stubPost(p, "accepted", [{ message: "warn" }]); await stubReadback(p, () => rbBody({})); await p.selectOption("#mode-switch", "issue_lifecycle"); await p.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1); }],
  ["kb-outcome-unknown", async (p) => { await stubPost(p, "abort"); await p.selectOption("#mode-switch", "issue_lifecycle"); await p.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1); }],
  ["kb-rejected", async (p) => { await stubPost(p, "reject"); await p.selectOption("#mode-switch", "issue_lifecycle"); await p.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1); }],
]) {
  await record({ id: name, surface: "served", fixture: name, mode: "issue_lifecycle", theme: "light", width: 1280 }, () => keyboardTrace(browser, servedUrl, name, pre));
}
// 5. Shared-authoring live-region / disabled-reason interaction (offline)
await record({ id: "live-import-error-offline", surface: "offline", fixture: "import-error", mode: "issue_lifecycle", theme: "light", width: 1280 }, () => withPage(browser, OFFLINE_URL, { mode: "issue_lifecycle", theme: "light", width: 1280 }, async (p) => {
  await p.setInputFiles("#import-issue-input", { name: "bad.md", mimeType: "text/markdown", buffer: Buffer.from("not frontmatter at all") });
  await p.waitForTimeout(300);
  await capture(p, "live-import-error-offline", { surface: "offline" });
}));

await browser.close();
if (CASE_ONLY) {
  const prev = JSON.parse(readFileSync(join(RUN_DIR, "case-manifest.json"), "utf8"));
  const ids = new Set(manifest.map((m) => m.id));
  manifest.unshift(...prev.manifest.filter((m) => !ids.has(m.id)));
  results.unshift(...prev.results.filter((r) => !ids.has(r.id)));
}
const summary = { collected: results.filter((r) => r.status === "collected").length, error: results.filter((r) => r.status === "error").length };
meta.finishedAt = new Date().toISOString();
writeFileSync(join(RUN_DIR, "run-metadata.json"), JSON.stringify(meta, null, 2));
writeFileSync(join(RUN_DIR, "case-manifest.json"), JSON.stringify({ manifest, results, summary }, null, 2));
console.log(`AUDIT_CASES: collected=${summary.collected} error=${summary.error} manifest=${join(RUN_DIR, "case-manifest.json")}`);
console.log(summary.error ? "AUDIT_EVIDENCE_INCOMPLETE" : "AUDIT_EVIDENCE_COLLECTED");
process.exit(summary.error ? 1 : 0);
