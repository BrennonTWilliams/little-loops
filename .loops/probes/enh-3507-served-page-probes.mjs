#!/usr/bin/env node
// Served-page probes for ENH-3507 (policy-router builder connected storage).
//
// Starts `ll-artifact serve --policy-builder`, loads the printed builder URL
// over http://127.0.0.1 (secure context) with Playwright, and checks that the
// stamped CONNECTED_CONTEXT matches an independently computed workspace id and
// that connected edits persist only workspace-namespaced keys. FEAT-3505
// extends this file.
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
