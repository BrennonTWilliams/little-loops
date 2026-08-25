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
