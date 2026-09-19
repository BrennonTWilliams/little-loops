#!/usr/bin/env node
// Served-page probes for ENH-3507 (policy-router builder connected storage).
//
// Starts `ll-artifact serve --policy-builder`, loads the printed builder URL
// over http://127.0.0.1 (secure context) with Playwright, and checks that the
// stamped CONNECTED_CONTEXT matches an independently computed workspace id and
// that connected edits persist only workspace-namespaced keys. FEAT-3505
// extends this file with the connected-panel probes: real-server coverage
// (issues, review -> submit -> awaiting_approval, reload recovery, cancel ->
// requeue via `ll-queue`) is reported apart from `stub:` probes that fulfil
// readback through page.route to cover running/done, every status label,
// run identity after requeue, and untrusted result rendering. A real-server
// probe leaves one `awaiting_approval`/`cancelled` row in the project queue;
// it never approves or executes a loop.
//
// Dev-only, on-demand (never a pytest gate). Playwright resolves from
// LL_PLAYWRIGHT_ROOT / NODE_PATH / `npm root -g` (e.g. ~/.npm-global).
// Run via .loops/verify-enh-3507-served-page.yaml.
//
// Usage: node enh-3507-served-page-probes.mjs [--check | <report.json> [port]]
// Exit: 0 = all passed, 2 = no failures but some BLOCKED (needs unmet or no
//       Playwright), 1 = at least one FAIL, 3 = infra (server never printed a
//       builder URL). stdout ends with one marker line:
//   SERVED_PROBES_PASSED | SERVED_PROBES_BLOCKED | SERVED_PROBES_FAILED
import { createRequire } from "node:module";
import { execSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { realpathSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const DEFAULT_PORT = 8797; // non-default: 8766 collides with a developer's running server
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
if (!firstArg) {
  console.error("usage: enh-3507-served-page-probes.mjs [--check | <report.json> [port]]");
  process.exit(3);
}
const REPORT_PATH = resolve(firstArg);
const PORT = Number(portArg) || DEFAULT_PORT;

// Mirrors derive_workspace_id (serve.py): first 16 hex of sha256(realpath(cwd)).
const CWD = realpathSync(process.cwd());
const EXPECTED_WS = createHash("sha256").update(CWD).digest("hex").slice(0, 16);

let server = null;
function killServer() { if (server && !server.killed) server.kill("SIGTERM"); }
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { killServer(); process.exit(130); });

function startServer() {
  return new Promise((resolveUrl, reject) => {
    server = spawn("ll-artifact", ["serve", "--policy-builder", "--port", String(PORT)], {
      cwd: CWD,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let buf = "";
    let stderr = "";
    const timer = setTimeout(() => reject(new Error(`no builder URL within ${URL_WAIT_MS}ms; stderr: ${stderr.slice(0, 300)}`)), URL_WAIT_MS);
    server.stderr.on("data", (d) => { stderr += d; });
    server.stdout.on("data", (d) => {
      buf += d;
      // Second printed line is bridge.url + "policy-builder".
      const m = buf.match(/^(http:\/\/\S+\/policy-builder)\s*$/m);
      if (m) { clearTimeout(timer); resolveUrl(m[1]); }
    });
    server.on("error", (e) => { clearTimeout(timer); reject(e); });
    server.on("exit", (code) => { clearTimeout(timer); reject(new Error(`server exited early (${code}); stderr: ${stderr.slice(0, 300)}`)); });
  });
}

// A probe result: "pass" | "fail" | "blocked"; throwing => fail.
const PROBES = [
  {
    id: "context",
    needs: [],
    acs: ["stamped CONNECTED_CONTEXT.workspaceId equals sha256(realpath(cwd))[:16]"],
    async run({ page, url }) {
      await page.goto(url);
      // Top-level const in a classic script: not a window property.
      const ws = await page.evaluate("CONNECTED_CONTEXT.workspaceId");
      if (ws !== EXPECTED_WS) return { status: "fail", reason: `page workspaceId ${ws} != expected ${EXPECTED_WS}` };
      return { status: "pass" };
    },
  },
  {
    id: "connected-storage",
    needs: ["storage-rebind"],
    acs: ["a committed edit writes only workspace-namespaced draft + meta keys, no unscoped keys"],
    async run({ page, url }) {
      await page.goto(url);
      await page.click("#add-scenario-btn"); // committed edit
      const keys = await page.evaluate("Object.keys(localStorage)");
      // `state` lives in a module script (not global): derive the mode from the stored meta.
      const metaRaw = await page.evaluate((k) => localStorage.getItem(k), `ll-policy-builder-meta-${EXPECTED_WS}`);
      const mode = metaRaw ? JSON.parse(metaRaw).activeMode : "?";
      const want = [`ll-policy-builder-draft-${EXPECTED_WS}-${mode}`, `ll-policy-builder-meta-${EXPECTED_WS}`];
      const missing = want.filter((k) => !keys.includes(k));
      if (missing.length) return { status: "fail", reason: `missing keys ${missing.join(", ")}; have ${keys.join(", ")}` };
      const unscoped = keys.filter((k) => /^ll-policy-builder-(draft-[a-z_]+|meta)$/.test(k));
      if (unscoped.length) return { status: "fail", reason: `unscoped keys written: ${unscoped.join(", ")}` };
      return { status: "pass" };
    },
  },
];

// ---- FEAT-3505 helpers -------------------------------------------------------
const QUEUE_ID_RE = /queue ([0-9a-f-]{8,})/;
async function toLifecycle(page) {
  await page.selectOption("#mode-switch", "issue_lifecycle");
  await page.waitForSelector("#conn-body:not([hidden])");
}
async function pickFirstIssue(page) {
  await page.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1);
  const v = await page.$eval("#conn-issue option:nth-child(2)", (o) => o.value);
  await page.selectOption("#conn-issue", v);
  return v;
}
async function reviewAndSubmit(page) {
  await page.click("#conn-review-btn");
  await page.waitForFunction(() => !document.querySelector("#conn-submit-btn").disabled);
  await page.click("#conn-submit-btn");
}
const statusText = (page) => page.$eval("#conn-status", (e) => e.textContent);
function ll(cmd) { return execSync(`ll-queue ${cmd}`, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }); }
function stubReadback(page, get) {
  return page.route("**/run-request/*", (route) => route.fulfill({
    status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" },
    body: JSON.stringify(get()),
  }));
}
// Readback bindings must echo the POSTed issue/revision or the page (correctly) reports a conflict.
const posted = { bindings: {} };
function stubPost(page, warnings = []) {
  return page.route("**/run-request", (route) => route.request().method() === "POST"
    ? (() => {
      const b = route.request().postDataJSON();
      posted.bindings = { issueId: b.issueId, revisionId: b.revisionId };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ requestId: "x", queueId: "qstub0001", created: true, warnings }) });
    })()
    : route.continue());
}
async function stubbedSubmit(page, url, get, warnings) {
  await page.goto(url);
  await stubPost(page, warnings);
  await stubReadback(page, get);
  await toLifecycle(page);
  await pickFirstIssue(page);
  await reviewAndSubmit(page);
}
const rbBody = (over) => ({ requestId: "x", queueId: "qstub0001", status: "running", bindings: posted.bindings, loopInstanceId: "loop-9", runDir: "/runs/9", result: null, ...over });

const FEAT_3505_PROBES = [
  {
    id: "connected-panel-real",
    needs: [],
    acs: ["panel renders, real ./issues populates the selector, no absolute path leaks into storage or DOM"],
    async run({ page, url }) {
      await page.goto(url);
      await toLifecycle(page);
      await page.waitForFunction(() => document.querySelectorAll("#conn-issue option").length > 1);
      const html = await page.evaluate("document.querySelector('#connected-panel').outerHTML + JSON.stringify(Object.entries(localStorage))");
      if (/"?path"?:\s*"\//.test(html) || html.includes(CWD)) return { status: "fail", reason: "absolute issue path leaked" };
      return { status: "pass" };
    },
  },
  {
    id: "review-edit-submit-real",
    needs: [],
    acs: ["review A, edit, submit sends A (draft-edited shown); awaiting approval; reload restores request; storage keys workspace-scoped"],
    async run({ page, url }) {
      await page.goto(url);
      await toLifecycle(page);
      await pickFirstIssue(page);
      await page.click("#conn-review-btn");
      await page.waitForFunction(() => !document.querySelector("#conn-submit-btn").disabled);
      const revBefore = await page.$eval("#conn-review-info", (e) => e.textContent.match(/snapshot ([0-9a-f]{12})/)[1]);
      await page.fill("#f-name", "probe-edited-name");
      await page.dispatchEvent("#f-name", "change");
      // Editing bumps the template session revision but keeps the reviewed snapshot.
      const info = await page.$eval("#conn-review-info", (e) => e.textContent);
      if (!/Draft edited since review/.test(info)) return { status: "fail", reason: "draft-edited indicator missing" };
      await page.click("#conn-submit-btn");
      await page.waitForFunction(() => /Awaiting approval/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      const st = await statusText(page);
      if (!st.includes(revBefore)) return { status: "fail", reason: "submitted revision differs from reviewed" };
      await page.reload();
      await page.waitForFunction(() => /Awaiting approval/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      const keys = await page.evaluate("Object.keys(localStorage)");
      const sub = keys.filter((k) => k.startsWith(`ll-policy-builder-submission-${EXPECTED_WS}-`));
      const idx = keys.filter((k) => k.startsWith(`ll-policy-builder-submissions-${EXPECTED_WS}-`));
      if (sub.length !== 1 || idx.length !== 1) return { status: "fail", reason: `expected 1 record+1 index, have ${sub.length}/${idx.length}` };
      return { status: "pass" };
    },
  },
  {
    id: "cancel-requeue-real",
    needs: [],
    acs: ["ll-queue cancel -> page shows cancelled and stops polling; requeue + Refresh status resumes; reload re-reads terminal rows"],
    async run({ page, url }) {
      await page.goto(url);
      await toLifecycle(page);
      await pickFirstIssue(page);
      await reviewAndSubmit(page);
      await page.waitForFunction(() => /queue [0-9a-f-]{8,}/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      const qid = (await statusText(page)).match(QUEUE_ID_RE)[1];
      ll(`cancel ${qid}`);
      await page.click("#conn-refresh-btn");
      await page.waitForFunction(() => /Rejected \/ cancelled by host/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      try { ll(`requeue ${qid}`); }
      catch (e) { return { status: "blocked", reason: `ll-queue requeue refused a cancelled row: ${String(e.stderr || e.message).split("\n")[0]}` }; }
      await page.click("#conn-refresh-btn");
      await page.waitForFunction(() => /Awaiting approval/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      ll(`cancel ${qid}`); // leave the row terminal; never approve/execute
      await page.reload();
      await page.waitForFunction(() => /Rejected \/ cancelled by host/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      return { status: "pass" };
    },
  },
  {
    id: "stub:status-labels-and-run-identity",
    needs: [],
    acs: ["stubbed readback: running shows run identity; awaiting_approval after requeue labels it Previous run; every status label renders"],
    async run({ page, url }) {
      let body = null;
      await stubbedSubmit(page, url, () => body || rbBody({ status: "running" }));
      await page.click("#conn-refresh-btn");
      await page.waitForFunction(() => /Status: Running/.test(document.querySelector("#conn-status").textContent));
      if (!/Run: loop-9/.test(await statusText(page))) return { status: "fail", reason: "run identity missing while running" };
      const labels = { awaiting_approval: "Awaiting approval", pending: "Approved — waiting to run", done: "Done", failed: "Failed", dead_letter: "Failed — moved to dead letter", cancelled: "Rejected / cancelled by host" };
      for (const [status, label] of Object.entries(labels)) {
        body = rbBody({ status });
        await page.click("#conn-refresh-btn");
        await page.waitForFunction((l) => document.querySelector("#conn-status").textContent.includes(`Status: ${l}`), label);
      }
      body = rbBody({ status: "awaiting_approval" });
      await page.click("#conn-refresh-btn");
      await page.waitForFunction(() => /Previous run: loop-9/.test(document.querySelector("#conn-status").textContent));
      return { status: "pass" };
    },
  },
  {
    id: "stub:untrusted-result-and-warnings",
    needs: [],
    acs: ["untrusted stdout renders as text only, is never stored; warnings from the accepted response are shown non-blocking"],
    async run({ page, url }) {
      const evil = "<img src=x onerror=\"window.__pwned=1\">";
      const body = () => rbBody({ status: "done", result: { exit_code: 0, timed_out: false, error: null, stdout: evil, stderr: "" } });
      await stubbedSubmit(page, url, body, [{ message: "State is not reachable from initial state" }]);
      await page.click("#conn-refresh-btn");
      await page.waitForFunction(() => /Status: Done/.test(document.querySelector("#conn-status").textContent));
      if ((await page.$$("#conn-status img")).length) return { status: "fail", reason: "img element created from result" };
      if (await page.evaluate("window.__pwned")) return { status: "fail", reason: "result executed" };
      if (!/Warning \(non-blocking\): State is not reachable/.test(await statusText(page))) return { status: "fail", reason: "warning not shown" };
      const stored = await page.evaluate("JSON.stringify(Object.entries(localStorage))");
      if (stored.includes("onerror")) return { status: "fail", reason: "result persisted to storage" };
      return { status: "pass" };
    },
  },
];
PROBES.push(...FEAT_3505_PROBES);

// Serve a workspace from `cwd` on `port`; resolves {url, stop()} once the builder URL prints.
function serveAt(cwd, port) {
  return new Promise((resolveUrl, reject) => {
    const child = spawn("ll-artifact", ["serve", "--policy-builder", "--port", String(port)], {
      cwd, env: { ...process.env, PYTHONUNBUFFERED: "1" }, stdio: ["ignore", "pipe", "pipe"],
    });
    let buf = "";
    const timer = setTimeout(() => { child.kill("SIGTERM"); reject(new Error("no builder URL")); }, URL_WAIT_MS);
    child.stdout.on("data", (d) => {
      buf += d;
      const m = buf.match(/^(http:\/\/\S+\/policy-builder)\s*$/m);
      if (m) {
        clearTimeout(timer);
        resolveUrl({ url: m[1], stop: () => new Promise((r) => { child.once("exit", r); child.kill("SIGTERM"); }) });
      }
    });
    child.on("error", (e) => { clearTimeout(timer); reject(e); });
  });
}

PROBES.push({
  id: "two-workspaces-same-origin",
  needs: [],
  acs: ["two workspaces served sequentially at one origin never restore each other's draft, selection, or submission"],
  async run({ page }) {
    const port = PORT + 1;
    const other = realpathSync(execSync("mktemp -d", { encoding: "utf8" }).trim());
    execSync("git init -q .", { cwd: other });
    const otherWs = createHash("sha256").update(other).digest("hex").slice(0, 16);
    let a = null;
    let b = null;
    let qid = null;
    try {
      a = await serveAt(CWD, port);
      await page.goto(a.url);
      await toLifecycle(page);
      await pickFirstIssue(page);
      await page.fill("#f-name", "ws-a-draft");
      await page.dispatchEvent("#f-name", "change");
      await reviewAndSubmit(page);
      await page.waitForFunction(() => /queue [0-9a-f-]{8,}/.test(document.querySelector("#conn-status").textContent), null, { timeout: 15000 });
      qid = (await statusText(page)).match(QUEUE_ID_RE)[1];
      await a.stop();
      a = null;
      b = await serveAt(other, port); // same origin, different workspace + new token
      await page.goto(b.url);
      const wsB = await page.evaluate("CONNECTED_CONTEXT.workspaceId");
      if (wsB !== otherWs) return { status: "fail", reason: `workspace B id ${wsB} != ${otherWs}` };
      await page.waitForTimeout(500);
      if ((await statusText(page)).trim()) return { status: "fail", reason: "workspace B restored a submission from A" };
      const name = await page.$eval("#f-name", (e) => e.value);
      if (name === "ws-a-draft") return { status: "fail", reason: "workspace B restored A's draft" };
      const sel = await page.$eval("#conn-issue", (e) => e.value);
      if (sel) return { status: "fail", reason: "workspace B restored A's issue selection" };
      const keys = await page.evaluate("Object.keys(localStorage)");
      if (!keys.some((k) => k.includes(`-submission-${EXPECTED_WS}-`))) return { status: "fail", reason: "workspace A's record was removed" };
      if (keys.some((k) => k.includes(`-submission-${otherWs}-`))) return { status: "fail", reason: "workspace B wrote a submission" };
      return { status: "pass" };
    } finally {
      if (a) await a.stop();
      if (b) await b.stop();
      if (qid) { try { ll(`cancel ${qid}`); } catch { /* already terminal */ } }
    }
  },
});

const CAPABILITIES = {
  "storage-rebind": (page) => page.evaluate("typeof PolicyBuilderCore !== 'undefined' && typeof PolicyBuilderCore.createBuilderStorage === 'function' && document.documentElement.outerHTML.includes('createBuilderStorage(')"),
};

const pw = loadPlaywright();
if (!pw || !pw.mod.chromium) {
  console.log("PLAYWRIGHT_MISSING: set LL_PLAYWRIGHT_ROOT or NODE_PATH to a directory containing `playwright`");
  console.log("SERVED_PROBES_BLOCKED");
  process.exit(2);
}

let builderUrl;
try { builderUrl = await startServer(); }
catch (e) {
  killServer();
  console.log(`SERVER_START_FAILED: ${e.message}`);
  process.exit(3);
}

const results = [];
let browser;
try {
  browser = await pw.mod.chromium.launch({ headless: true });
  for (const probe of PROBES) {
    const ctx = await browser.newContext(); // fresh localStorage per probe
    const page = await ctx.newPage();
    let res;
    try {
      await page.goto(builderUrl);
      const unmet = [];
      for (const need of probe.needs) {
        if (!(await CAPABILITIES[need](page))) unmet.push(need);
      }
      res = unmet.length
        ? { status: "blocked", reason: `unmet needs: ${unmet.join(", ")}` }
        : await probe.run({ page, url: builderUrl });
    } catch (e) {
      res = { status: "fail", reason: e.message.split("\n")[0] };
    }
    await ctx.close();
    results.push({ id: probe.id, needs: probe.needs, acs: probe.acs, ...res });
    console.log(`PROBE ${probe.id} [${probe.needs}] ${res.status}${res.reason ? " — " + res.reason : ""}`);
  }
} catch (e) {
  console.log(`PLAYWRIGHT_LAUNCH_FAILED: ${e.message.split("\n")[0]}`);
  killServer();
  process.exit(3);
} finally {
  if (browser) await browser.close();
  killServer();
}

const summary = { pass: 0, fail: 0, blocked: 0 };
for (const r of results) summary[r.status] += 1;
mkdirSync(dirname(REPORT_PATH), { recursive: true });
writeFileSync(REPORT_PATH, JSON.stringify({ expectedWorkspaceId: EXPECTED_WS, builderUrl, summary, results }, null, 2));
console.log(`SERVED_PROBES: pass=${summary.pass} fail=${summary.fail} blocked=${summary.blocked} report=${REPORT_PATH}`);
if (summary.fail > 0) { console.log("SERVED_PROBES_FAILED"); process.exit(1); }
if (summary.blocked > 0) { console.log("SERVED_PROBES_BLOCKED"); process.exit(2); }
console.log("SERVED_PROBES_PASSED");
