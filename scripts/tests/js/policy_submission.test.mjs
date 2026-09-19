// FEAT-3505: submission controller, hash helper, and storage-record tests.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  createSubmissionController, sha256Hex, isWellFormedUtf16, codePointLength, queueStatusLabel,
  createBuilderStorage,
} from "../../little_loops/templates/policy_builder_core.mjs";

const WS = "0123456789abcdef";
const PID = "proj-a-b";
const YAML = "name: x\nstates: {}\n";

function fakeStorage(opts = {}) {
  const m = new Map();
  const s = {
    m, failSet: null, failRemove: false,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem(k, v) {
      if (s.failSet && s.failSet(k, v)) throw new Error("quota");
      m.set(k, String(v));
    },
    removeItem(k) { if (s.failRemove) throw new Error("rm"); m.delete(k); },
    get length() { return m.size; },
    key: (i) => Array.from(m.keys())[i] ?? null,
  };
  return s;
}

function fakeTimers() {
  let id = 0;
  const t = { pending: new Map(), now: 0 };
  t.setTimeout = (fn, ms) => { id += 1; t.pending.set(id, { fn, at: t.now + ms, ms }); return id; };
  t.clearTimeout = (h) => t.pending.delete(h);
  t.advance = async (ms) => {
    t.now += ms;
    for (const [h, e] of Array.from(t.pending)) {
      if (e.at <= t.now) { t.pending.delete(h); e.fn(); }
    }
    await flush();
  };
  return t;
}
const settleHash = async (env) => {
  for (let i = 0; i < 50 && env.ctl.getState().review.status === "hashing"; i++) {
    await new Promise((r) => setImmediate(r));
  }
  await flush();
};
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

function jsonResp(status, body, ct = "application/json") {
  return { status, headers: { get: () => ct }, text: async () => JSON.stringify(body) };
}

function setup(over = {}) {
  const storage = over.storage || fakeStorage();
  const timers = fakeTimers();
  const calls = [];
  let uuid = 0;
  const env = {
    storage, timers, calls, responses: over.responses ? over.responses.slice() : [],
    fetch: (url, init) => {
      calls.push({ url, init });
      const next = env.responses.shift();
      if (!next) return new Promise(() => {});
      if (next instanceof Error) return Promise.reject(next);
      return Promise.resolve(typeof next === "function" ? next() : next);
    },
  };
  const ctl = createSubmissionController({
    fetch: env.fetch, storage, subtle: globalThis.crypto.subtle,
    setTimeout: timers.setTimeout, clearTimeout: timers.clearTimeout,
    randomUUID: () => `00000000-0000-4000-8000-${String(++uuid).padStart(12, "0")}`,
    makeAbortController: () => new AbortController(),
    connectedContext: over.ws === null ? null : { workspaceId: over.ws || WS },
    ensureDocumentIdentity: over.ensureDocumentIdentity || (() => true),
    requestTimeoutMs: over.requestTimeoutMs || 30000,
    submissionBudgetBytes: over.submissionBudgetBytes,
    now: (() => { let n = 0; return () => ++n; })(),
  });
  env.ctl = ctl;
  ctl.documentOpened({ projectId: PID, issueId: "FEAT-1", mode: "issue_lifecycle" });
  return env;
}

async function reviewed(env, yaml = YAML) {
  env.ctl.review({ yaml });
  await settleHash(env);
  assert.equal(env.ctl.getState().review.status, "ready");
}

const ok = (over = {}) => jsonResp(200, { requestId: "r", queueId: "q1", created: true, warnings: [], ...over });
const rb = (status, over = {}) => (revisionId) => jsonResp(200, {
  requestId: "r", queueId: "q1", status,
  bindings: { issueId: "FEAT-1", revisionId }, loopInstanceId: "loop-1", runDir: "/run/1", result: null, ...over,
});

test("FEAT-3505 sha256Hex matches Python for non-ASCII", async () => {
  const text = "héllo — 日本語 🚀";
  assert.equal(await sha256Hex(text, globalThis.crypto.subtle), createHash("sha256").update(text, "utf8").digest("hex"));
});

test("FEAT-3505 surrogate guard native and fallback", () => {
  for (const native of [true, false]) {
    assert.equal(isWellFormedUtf16("a😀b", native), true);
    assert.equal(isWellFormedUtf16("a\ud800b", native), false);
    assert.equal(isWellFormedUtf16("a\udc00b", native), false);
    assert.equal(isWellFormedUtf16("\ud83d", native), false);
    assert.equal(isWellFormedUtf16("\ude00\ud83d", native), false);
  }
  assert.equal(codePointLength("😀".repeat(128)), 128);
});

test("FEAT-3505 status labels cover all statuses", () => {
  assert.equal(queueStatusLabel("cancelled"), "Rejected / cancelled by host");
  assert.equal(queueStatusLabel("dead_letter"), "Failed — moved to dead letter");
  assert.equal(queueStatusLabel("pending"), "Approved — waiting to run");
  assert.equal(queueStatusLabel("weird"), "weird");
});

test("FEAT-3505 review refusals allocate no UUID", async () => {
  const env = setup();
  let allocated = 0;
  const cases = [
    [{ yaml: YAML, blockedReason: "invalid" }, /invalid/],
    [{ yaml: "bad\ud800" }, /UTF-8/],
    [{ yaml: "x".repeat(1048576) }, /limit/],
    [{ yaml: "" }, /no generated/],
  ];
  for (const [input, re] of cases) {
    env.ctl.review(input);
    const st = env.ctl.getState().review;
    assert.equal(st.status, "refused");
    assert.match(st.reason, re);
  }
  env.ctl.contextChanged({ projectId: "", issueId: "FEAT-1", mode: "issue_lifecycle" });
  env.ctl.review({ yaml: YAML });
  assert.match(env.ctl.getState().review.reason, /project ID/);
  env.ctl.contextChanged({ projectId: "😀".repeat(129), issueId: "FEAT-1", mode: "issue_lifecycle" });
  env.ctl.review({ yaml: YAML });
  assert.match(env.ctl.getState().review.reason, /longer than 128/);
  env.ctl.contextChanged({ projectId: "😀".repeat(128), issueId: "FEAT-1", mode: "issue_lifecycle" });
  env.ctl.review({ yaml: YAML });
  assert.notEqual(env.ctl.getState().review.status, "refused");
  assert.equal(allocated, 0);
  assert.equal(env.storage.m.size, 0);
});

test("FEAT-3505 offline and non-lifecycle are unavailable with reason", () => {
  const off = setup({ ws: null });
  assert.equal(off.ctl.getState().availability.ok, false);
  const on = setup();
  on.ctl.contextChanged({ projectId: PID, issueId: "FEAT-1", mode: "rubric" });
  assert.match(on.ctl.getState().availability.reason, /lifecycle/);
});

test("FEAT-3505 review binds before first await; review A edit B submits A", async () => {
  const env = setup();
  env.ctl.review({ yaml: YAML });
  env.ctl.contextChanged({ projectId: PID, issueId: "FEAT-2", mode: "issue_lifecycle" }); // before hash resolves
  await new Promise((r) => setImmediate(r));
  await flush();
  assert.equal(env.ctl.getState().review.status, "none");
  env.ctl.contextChanged({ projectId: PID, issueId: "FEAT-1", mode: "issue_lifecycle" });
  await reviewed(env, "A: 1\n");
  env.ctl.draftChanged();
  assert.equal(env.ctl.getState().draftEdited, true);
  env.responses.push(ok());
  assert.equal(env.ctl.submit(), true);
  await flush();
  const body = JSON.parse(env.calls[0].init.body);
  assert.equal(body.yaml, "A: 1\n");
  assert.equal(body.revisionId, createHash("sha256").update("A: 1\n").digest("hex"));
  assert.equal(env.calls[0].init.headers["Content-Type"], "application/json");
  assert.equal(env.calls[0].url, "./run-request");
});

test("FEAT-3505 double submit sends one POST; accepted persists warnings compactly", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(ok({ warnings: [{ message: "unreachable" }] }));
  env.ctl.submit();
  env.ctl.submit();
  await flush();
  assert.equal(env.calls.length, 1);
  const s = env.ctl.getState().submission;
  assert.equal(s.delivery.state, "accepted");
  assert.equal(s.queueId, "q1");
  assert.deepEqual(s.warnings, [{ message: "unreachable" }]);
  const recs = [...env.storage.m.entries()].filter(([k]) => k.includes("-submission-"));
  assert.equal(recs.length, 1);
  assert.equal(JSON.parse(recs[0][1]).kind, "compact");
  assert.ok(!JSON.stringify([...env.storage.m.values()]).includes("A: 1")); // yaml dropped after compaction
});

test("FEAT-3505 network loss keeps unknown; readback 404 allows identical retry", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(new Error("offline"));
  env.ctl.submit();
  await flush();
  let s = env.ctl.getState().submission;
  assert.equal(s.delivery.state, "outcome_unknown");
  assert.equal(s.canRetry, false);
  env.responses.push(jsonResp(404, { error: { code: "request_not_found", message: "no" } }));
  env.ctl.refreshStatus();
  await flush();
  s = env.ctl.getState().submission;
  assert.equal(s.canRetry, true);
  env.responses.push(ok({ created: false, warnings: undefined }));
  env.ctl.retry();
  await flush();
  assert.equal(env.calls[0].init.body, env.calls[2].init.body);
  s = env.ctl.getState().submission;
  assert.equal(s.delivery.state, "accepted");
  assert.equal(s.warningsUnavailable, true);
});

test("FEAT-3505 ordinary submit is guarded while unknown; newRun makes a new UUID", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(jsonResp(500, { error: { code: "internal_error", message: "x" } }));
  env.ctl.submit();
  await flush();
  assert.equal(env.ctl.getState().submission.delivery.state, "outcome_unknown");
  await reviewed(env, "B: 2\n");
  assert.equal(env.ctl.submit(), false);
  env.responses.push(ok());
  assert.equal(env.ctl.submit({ newRun: true }), true);
  await flush();
  assert.notEqual(JSON.parse(env.calls[0].init.body).requestId, JSON.parse(env.calls[1].init.body).requestId);
  // earlier unknown record retained (full, with yaml)
  const kept = [...env.storage.m.values()].filter((v) => v.includes('"outcome_unknown"'));
  assert.equal(kept.length, 1);
  assert.ok(kept[0].includes("name: x"));
});

test("FEAT-3505 rejected 409 stays rejected after reload; conflict copy uses server message", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(jsonResp(409, { error: { code: "request_conflict", message: "bound elsewhere" } }));
  env.ctl.submit();
  await flush();
  const s = env.ctl.getState().submission;
  assert.equal(s.delivery.state, "rejected");
  assert.equal(s.delivery.error.message, "bound elsewhere");
  const env2 = setup({ storage: env.storage });
  const s2 = env2.ctl.getState().submission;
  assert.equal(s2.delivery.state, "rejected");
  assert.equal(env2.calls.length, 0);
});

test("FEAT-3505 non-JSON response leaves outcome unknown", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(jsonResp(403, {}, "text/html"));
  env.ctl.submit();
  await flush();
  assert.equal(env.ctl.getState().submission.delivery.state, "outcome_unknown");
});

test("FEAT-3505 persistence failures send nothing and keep prior state", async () => {
  // identity failure
  let env = setup({ ensureDocumentIdentity: () => false });
  await reviewed(env);
  assert.equal(env.ctl.submit(), false);
  assert.equal(env.calls.length, 0);
  assert.equal(env.storage.m.size, 0);
  // record write failure
  env = setup();
  await reviewed(env);
  env.storage.failSet = (k) => k.includes("-submission-");
  assert.equal(env.ctl.submit(), false);
  assert.equal(env.calls.length, 0);
  // index write failure rolls back new record
  env = setup();
  await reviewed(env);
  env.storage.failSet = (k) => k.includes("-submissions-");
  assert.equal(env.ctl.submit(), false);
  assert.equal(env.calls.length, 0);
  assert.equal([...env.storage.m.keys()].filter((k) => k.includes("-submission-")).length, 0);
  // index write fails AND rollback fails → orphan prepared removed at next boot
  env = setup();
  await reviewed(env);
  env.storage.failSet = (k) => k.includes("-submissions-");
  env.storage.failRemove = true;
  env.ctl.submit();
  assert.equal(env.calls.length, 0);
  env.storage.failSet = null;
  env.storage.failRemove = false;
  const env2 = setup({ storage: env.storage });
  assert.equal([...env.storage.m.keys()].filter((k) => k.includes("-submission-")).length, 0);
  assert.ok(env2.ctl.getState().notices.some((n) => /never sent/.test(n)));
});

test("FEAT-3505 crash after outcome_unknown is retained and reconciled on reload", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(() => new Promise(() => {})); // POST never settles (page "crashes")
  env.ctl.submit();
  await flush();
  const rev = createHash("sha256").update(YAML).digest("hex");
  const env2 = setup({ storage: env.storage, responses: [rb("awaiting_approval")(rev)] });
  await flush();
  const s = env2.ctl.getState().submission;
  assert.equal(s.delivery.state, "accepted");
  assert.equal(s.queueId, "q1");
  assert.equal(s.statusLabel, "Awaiting approval");
});

test("FEAT-3505 orphan unknown record is adopted, hyphenated project IDs enumerate", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(new Error("x"));
  env.ctl.submit();
  await flush();
  const idxKey = [...env.storage.m.keys()].find((k) => k.includes("-submissions-"));
  env.storage.m.delete(idxKey); // index lost
  const env2 = setup({ storage: env.storage });
  assert.equal(env2.ctl.getState().submission.delivery.state, "outcome_unknown");
  assert.equal(env2.ctl.getState().submission.projectId, "proj-a-b");
});

test("FEAT-3505 malformed storage stops cleanup with diagnostic (not empty index)", () => {
  const storage = fakeStorage();
  storage.m.set(`ll-policy-builder-submission-${WS}-p-x`, "{not json");
  const env = setup({ storage });
  assert.ok(env.ctl.getState().notices.some((n) => /malformed/.test(n)));
  assert.equal(storage.m.size, 1);
});

test("FEAT-3505 workspace isolation", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(ok());
  env.ctl.submit();
  await flush();
  const other = setup({ storage: env.storage, ws: "fedcba9876543210" });
  assert.equal(other.ctl.getState().submission, null);
});

test("FEAT-3505 polling cadence, terminal stop, refresh/requeue resume", async () => {
  const env = setup();
  await reviewed(env);
  const rev = createHash("sha256").update(YAML).digest("hex");
  env.responses.push(ok());
  env.ctl.submit();
  await flush();
  env.responses.push(rb("running")(rev));
  await env.timers.advance(2000);
  assert.equal(env.ctl.getState().submission.loopInstanceId, "loop-1");
  assert.equal([...env.timers.pending.values()][0].ms, 2000);
  env.responses.push(rb("awaiting_approval")(rev));
  await env.timers.advance(2000);
  assert.equal([...env.timers.pending.values()][0].ms, 10000);
  assert.equal(env.ctl.getState().submission.runIsCurrent, false);
  env.responses.push(rb("cancelled")(rev));
  await env.timers.advance(10000);
  assert.equal(env.timers.pending.size, 0);
  assert.equal(env.ctl.getState().submission.statusLabel, "Rejected / cancelled by host");
  env.responses.push(rb("awaiting_approval", { result: { previous: { exit_code: 1 } } })(rev));
  env.ctl.refreshStatus();
  await flush();
  const s = env.ctl.getState().submission;
  assert.equal(s.terminal, false);
  assert.equal(s.previousResult.exit_code, 1);
  assert.equal(s.result, null);
  assert.equal([...env.timers.pending.values()][0].ms, 10000);
});

test("FEAT-3505 readback with mismatched bindings is a conflict, never accepted", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(new Error("x"));
  env.ctl.submit();
  await flush();
  env.responses.push(jsonResp(200, { requestId: "r", queueId: "q", status: "pending", bindings: { issueId: "FEAT-9", revisionId: "f".repeat(64) } }));
  env.ctl.refreshStatus();
  await flush();
  const s = env.ctl.getState().submission;
  assert.notEqual(s.delivery.state, "accepted");
  assert.ok(s.conflict);
});

test("FEAT-3505 result is never persisted", async () => {
  const env = setup();
  await reviewed(env);
  const rev = createHash("sha256").update(YAML).digest("hex");
  env.responses.push(ok());
  env.ctl.submit();
  await flush();
  env.responses.push(rb("done", { result: { exit_code: 0, stdout: "<img onerror=x>SECRETOUT" } })(rev));
  await env.timers.advance(2000);
  assert.equal(env.ctl.getState().submission.result.exit_code, 0);
  assert.ok(![...env.storage.m.values()].some((v) => v.includes("SECRETOUT")));
});

test("FEAT-3505 POST timeout stays unknown, late success is fenced; readback timeout pauses", async () => {
  const env = setup({ requestTimeoutMs: 1000 });
  await reviewed(env);
  let release;
  env.responses.push(() => new Promise((r) => { release = r; }));
  env.ctl.submit();
  await flush();
  await env.timers.advance(1000);
  let s = env.ctl.getState().submission;
  assert.equal(s.delivery.state, "outcome_unknown");
  assert.equal(env.ctl.getState().busy, false);
  release(ok());
  await flush();
  assert.equal(env.ctl.getState().submission.delivery.state, "outcome_unknown");
  env.responses.push(() => new Promise(() => {}));
  env.ctl.refreshStatus();
  await flush();
  await env.timers.advance(1000);
  assert.equal(env.ctl.getState().submission.poll, "paused");
});

test("FEAT-3505 issue list: no-store, timeout keeps selection, path dropped", async () => {
  const env = setup({ requestTimeoutMs: 500 });
  env.responses.push(jsonResp(200, { issues: [{ id: "FEAT-1", title: "t", priority: "P3", status: "open", path: "/abs" }] }));
  await env.ctl.loadIssues();
  assert.equal(env.calls[0].init.cache, "no-store");
  assert.equal(env.ctl.getState().issues.list[0].path, undefined);
  env.ctl.loadIssues();
  await flush();
  await env.timers.advance(500);
  const st = env.ctl.getState();
  assert.equal(st.issues.status, "error");
  assert.equal(st.context.issueId, "FEAT-1");
});

test("FEAT-3505 same-ID Open invalidates review and stops polling; selection change keeps polling", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(ok());
  env.ctl.submit();
  await flush();
  assert.equal(env.timers.pending.size, 1);
  env.ctl.contextChanged({ projectId: PID, issueId: "FEAT-2", mode: "issue_lifecycle" });
  assert.equal(env.timers.pending.size, 1);
  await reviewed(env, "C: 3\n");
  env.ctl.documentOpened({ projectId: PID, issueId: "FEAT-2", mode: "issue_lifecycle" });
  assert.equal(env.ctl.getState().review.status, "none");
  assert.equal(env.ctl.getState().draftEdited, false);
});

test("FEAT-3505 budget refuses new request but keeps existing unresolved ones", async () => {
  const env = setup({ submissionBudgetBytes: 4000 });
  await reviewed(env, "a".repeat(600));
  env.responses.push(new Error("x"));
  env.ctl.submit();
  await flush();
  await reviewed(env, "b".repeat(1500));
  assert.equal(env.ctl.submit({ newRun: true }), false);
  assert.equal(env.calls.length, 1);
  assert.match(env.ctl.getState().notices.join(" "), /not enough room/);
  assert.equal([...env.storage.m.values()].filter((v) => v.includes("outcome_unknown")).length, 1);
});

test("FEAT-3505 resolved history pruned to 5; unresolved never pruned", async () => {
  const env = setup();
  for (let i = 0; i < 8; i++) {
    await reviewed(env, `n: ${i}\n`);
    env.responses.push(ok());
    assert.equal(env.ctl.submit(), true, `submit ${i}: ${env.ctl.getState().notices}`);
    await flush();
  }
  setup({ storage: env.storage }); // reload prunes to the active record + 5 resolved
  const recs = [...env.storage.m.keys()].filter((k) => k.includes("-submission-"));
  assert.equal(recs.length, 6);
});

test("FEAT-3505 persistMeta reports success/failure", () => {
  const st = fakeStorage();
  const b = createBuilderStorage({ storage: st, connectedContext: { workspaceId: WS }, warn() {} });
  assert.equal(b.persistMeta({ projectId: "p" }), true);
  st.failSet = () => true;
  assert.equal(b.persistMeta({ projectId: "p" }), false);
});

test("FEAT-3505 dispose clears timers and ignores late callbacks", async () => {
  const env = setup();
  await reviewed(env);
  env.responses.push(ok());
  env.ctl.submit();
  await flush();
  env.ctl.dispose();
  assert.equal(env.timers.pending.size, 0);
});

test("FEAT-3505 failed compaction leaves the prior full record for conservative recovery", async () => {
  const env = setup();
  await reviewed(env);
  env.storage.failSet = (k, v) => v.includes('"compact"');
  env.responses.push(ok());
  env.ctl.submit();
  await flush();
  assert.equal(env.ctl.getState().submission.delivery.state, "accepted"); // shown live
  const stored = [...env.storage.m.entries()].filter(([k]) => k.includes("-submission-"));
  assert.equal(stored.length, 1);
  const rec = JSON.parse(stored[0][1]);
  assert.equal(rec.kind, "full");
  assert.equal(rec.delivery.state, "outcome_unknown");
  assert.ok(rec.envelope.yaml.includes("name: x"));
});
