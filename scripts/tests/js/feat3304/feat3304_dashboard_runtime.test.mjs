// Runtime proof for the FEAT-3304 dashboard page, run against a REAL generated
// artifact (path in LL_DASHBOARD_HTML, produced by the Python side of this gate:
// scripts/tests/test_feat3304_artifact_dashboard.py::TestDashboardNodeRuntimeGate).
//
// It lives in this subdirectory, not directly under scripts/tests/js/, because
// test_policy_builder_node_gate.py globs `js/*.test.mjs` and runs that set with
// no environment — this file needs LL_DASHBOARD_HTML and would fail there.
//
// The Python assertions on the page can only check that the mechanism is wired
// in; these exercise it. In particular they prove the case a leading-SELECT
// check was measured to miss — "SELECT 1; DELETE FROM loop_runs;" — is actually
// rejected by PRAGMA query_only = 1 in the page's own instantiation path.

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(process.env.LL_DASHBOARD_HTML, "utf-8");

function sliceFirstScript(source) {
  const open = source.indexOf("<script>");
  const close = source.indexOf("</scr" + "ipt>", open);
  return source.slice(open + "<script>".length, close);
}

function constantFrom(name) {
  const match = new RegExp(`var ${name} = "([^"]*)"`).exec(html);
  assert.ok(match, `${name} not found in the generated page`);
  return match[1];
}

function decodeBase64(b64) {
  const binary = Buffer.from(b64, "base64");
  return new Uint8Array(binary);
}

async function gunzip(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// The vendored glue is inlined verbatim as the page's first <script>. Evaluating
// that exact text is the point: it proves what ships, not what npm resolves.
//
// Caveat, stated rather than hidden: the universal glue branches on
// `globalThis.process`, so under Node it takes its Node branch, not the browser
// branch a file://-opened artifact runs. The Node CommonJS bindings below are
// supplied so that branch can initialize at all; they are never used, because
// `wasmBinary` short-circuits every filesystem/network read of the .wasm. The
// SQLite engine semantics under test (query_only, prepare/step, re-instantiation)
// are the compiled WASM's, identical across both branches. Browser-side proof
// remains a manual open-over-file:// step.
const initSqlJs = new Function(
  "require",
  "module",
  "exports",
  "__dirname",
  sliceFirstScript(html) + "\n;return initSqlJs;"
)(createRequire(import.meta.url), { exports: {} }, {}, process.cwd());

const wasmBytes = decodeBase64(constantFrom("WASM_B64"));
const snapshotBytes = await gunzip(decodeBase64(constantFrom("SNAPSHOT_B64")));
const SQL = await initSqlJs({ wasmBinary: wasmBytes });

function open() {
  const db = new SQL.Database(snapshotBytes);
  db.run("PRAGMA query_only = 1");
  return db;
}

test("the embedded snapshot opens and carries only the allowlisted columns", () => {
  const db = open();
  const stmt = db.prepare("SELECT * FROM loop_runs");
  stmt.step();
  const columns = stmt.getColumnNames();
  stmt.free();
  assert.ok(columns.includes("run_id"));
  assert.ok(!columns.includes("error"), "free-text column leaked into the snapshot");
  assert.ok(
    !columns.includes("diagnostics_path"),
    "absolute-path column leaked into the snapshot"
  );
  db.close();
});

test("a bare write is rejected at the engine level", () => {
  const db = open();
  assert.throws(() => db.run("DELETE FROM loop_runs"), /readonly database/);
  db.close();
});

test("a multi-statement write behind a SELECT is rejected too", () => {
  const db = open();
  const before = db.exec("SELECT COUNT(*) FROM loop_runs")[0].values[0][0];
  assert.throws(() => db.run("SELECT 1; DELETE FROM loop_runs;"), /readonly database/);
  const after = db.exec("SELECT COUNT(*) FROM loop_runs")[0].values[0][0];
  assert.equal(after, before, "rows were deleted by a multi-statement input");
  db.close();
});

test("re-instantiating restores a mutated snapshot (the reset action)", () => {
  const db = new SQL.Database(snapshotBytes); // no pragma: simulate a mutated session
  const before = db.exec("SELECT COUNT(*) FROM loop_runs")[0].values[0][0];
  db.run("DELETE FROM loop_runs");
  assert.equal(db.exec("SELECT COUNT(*) FROM loop_runs")[0].values[0][0], 0);
  db.close();
  const reset = open();
  assert.equal(reset.exec("SELECT COUNT(*) FROM loop_runs")[0].values[0][0], before);
  reset.close();
});

test("prepare/step caps collected rows while counting the true total", () => {
  const db = open();
  const CAP = 1;
  const stmt = db.prepare("SELECT run_id FROM loop_runs");
  const rows = [];
  let total = 0;
  while (stmt.step()) {
    total++;
    if (rows.length < CAP) {
      rows.push(stmt.getAsObject());
    }
  }
  stmt.free();
  assert.ok(total > CAP, "fixture must carry more rows than the cap for this to prove anything");
  assert.equal(rows.length, CAP, "more rows were materialized than the cap allows");
  db.close();
});

// ---------------------------------------------------------------------------
// ENH-3733: execute the generated page's OWN query/render loop.
//
// The engine-level checks above repeat prepare/step by hand; they cannot prove
// what the page does with a stored INTEGER. This evaluates the page's second
// <script> (the IIFE containing runQuery/renderTable) against a minimal DOM
// stub and the embedded snapshot, then reads the rendered cells back.
// ---------------------------------------------------------------------------

function sliceNthScript(source, n) {
  let from = 0;
  let open = -1;
  for (let i = 0; i <= n; i++) {
    open = source.indexOf("<script>", from);
    assert.ok(open !== -1, `script #${n} not found in the generated page`);
    from = source.indexOf("</scr" + "ipt>", open) + 1;
  }
  const close = source.indexOf("</scr" + "ipt>", open);
  return source.slice(open + "<script>".length, close);
}

class StubElement {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.className = "";
    this.value = "";
    this.type = "";
    this._text = "";
  }
  get textContent() {
    return this._text;
  }
  set textContent(value) {
    this._text = value;
    if (value === "") {
      this.children = [];
    }
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  addEventListener(name, fn) {
    this.listeners[name] = fn;
  }
}

async function loadPage() {
  const byId = new Map();
  const document = {
    getElementById(id) {
      if (!byId.has(id)) {
        byId.set(id, new StubElement("#" + id));
      }
      return byId.get(id);
    },
    createElement(tag) {
      return new StubElement(tag);
    },
  };
  new Function(
    "document",
    "initSqlJs",
    "atob",
    "Blob",
    "DecompressionStream",
    "Response",
    sliceNthScript(html, 1)
  )(document, initSqlJs, atob, Blob, DecompressionStream, Response);
  const status = document.getElementById("status");
  for (let i = 0; i < 200 && !/^Snapshot loaded/.test(status.textContent); i++) {
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  assert.match(status.textContent, /^Snapshot loaded/, "the page never finished loading");
  return {
    status,
    sqlBox: document.getElementById("sql"),
    runButton: document.getElementById("run"),
    viewButtons: document.getElementById("views").children,
    results: document.getElementById("results"),
  };
}

// Rendered rows as {column: cell text}, read back from the stub DOM.
function renderedRows(results) {
  const table = results.children[0].children[0];
  const [thead, tbody] = table.children;
  const columns = thead.children[0].children.map((th) => th.textContent);
  return tbody.children.map((tr) =>
    Object.fromEntries(columns.map((name, i) => [name, tr.children[i].textContent]))
  );
}

function runCustom(page, sql) {
  page.sqlBox.value = sql;
  page.runButton.listeners.click();
  return renderedRows(page.results);
}

const BOUNDARY = {
  "boundary-2p53m1": "9007199254740991",
  "boundary-2p53": "9007199254740992",
  "boundary-2p53p1": "9007199254740993",
  "boundary-2p63m1": "9223372036854775807",
};

test("the predefined usage view renders exact integers, zero, NULL and independent availability", async () => {
  const page = await loadPage();
  const usage = page.viewButtons.find((b) => b.textContent === "Usage by model and channel");
  assert.ok(usage, "predefined usage view button is missing");
  usage.listeners.click();
  const rows = renderedRows(page.results);
  const byModel = (name) => rows.filter((r) => r.model === name);

  for (const [name, exact] of Object.entries(BOUNDARY)) {
    const [row] = byModel(name);
    assert.equal(row.canonical_input_tokens, exact, `${name} lost precision in the page loop`);
    assert.equal(row.token_availability, "available");
  }
  const [zero] = byModel("zero-model");
  assert.equal(zero.canonical_input_tokens, "0", "zero must render as 0, never blank or 0n");
  assert.equal(zero.canonical_cost_usd, "0");
  assert.equal(zero.token_availability, "available");

  const [tiny] = byModel("tiny-cost-model");
  assert.equal(tiny.canonical_cost_usd, "0", "four-decimal presentation");
  assert.equal(tiny.cost_availability, "available", "availability uses the unrounded cost");

  const [unpriced] = byModel("unpriced-model");
  assert.equal(unpriced.canonical_cost_usd, "", "unavailable cost renders blank, not zero");
  assert.equal(unpriced.cost_availability, "unavailable");
  assert.equal(unpriced.cost_reason, "unpriced_contributor");
  assert.equal(unpriced.token_availability, "available");

  const [overflow] = byModel("overflow-model");
  assert.equal(overflow.canonical_input_tokens, "");
  assert.equal(overflow.token_reason, "snapshot_integer_overflow");
  assert.equal(overflow.cost_availability, "available");
  assert.equal(overflow.canonical_cost_usd, "0.5");

  for (const row of byModel("audit-only-model")) {
    assert.equal(row.token_availability, "unavailable");
    assert.equal(row.token_reason, "coverage_unknown");
  }
  assert.ok(byModel("(unknown model)").length === 1);
});

test("custom SQL reads exact integers and original REAL values through the shared loop", async () => {
  const page = await loadPage();
  const ints = runCustom(
    page,
    "SELECT model, canonical_input_tokens FROM usage_coverage_audit " +
      "WHERE model LIKE 'boundary-%' ORDER BY model"
  );
  assert.equal(ints.length, Object.keys(BOUNDARY).length);
  for (const row of ints) {
    assert.equal(row.canonical_input_tokens, BOUNDARY[row.model], row.model);
  }
  const [real] = runCustom(
    page,
    "SELECT canonical_cost_usd FROM usage_coverage_audit WHERE model = 'tiny-cost-model'"
  );
  assert.equal(real.canonical_cost_usd, "0.00001", "custom SQL exposes the original REAL value");
  const [zero] = runCustom(
    page,
    "SELECT canonical_input_tokens AS n, canonical_cost_usd AS c FROM usage_coverage_audit " +
      "WHERE model = 'zero-model'"
  );
  assert.deepEqual(zero, { n: "0", c: "0" });
  const [nulls] = runCustom(
    page,
    "SELECT canonical_input_tokens AS n FROM usage_coverage_audit WHERE model = 'overflow-model'"
  );
  assert.equal(nulls.n, "");
});

test("the render cap and unmodified SQL survive the exact-integer read", async () => {
  const page = await loadPage();
  const cap = Number(/var ROW_CAP = (\d+);/.exec(html)[1]);
  const total = cap + 7;
  const rows = runCustom(
    page,
    `WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c WHERE n < ${total}) ` +
      "SELECT n FROM c"
  );
  assert.equal(rows.length, cap, "more rows were rendered than the cap allows");
  assert.equal(page.status.textContent, `showing ${cap} of ${total} rows`);
  assert.equal(rows[0].n, "1");
  assert.ok(!/LIMIT/i.test(page.sqlBox.value), "the submitted SQL must not gain a LIMIT");
});
