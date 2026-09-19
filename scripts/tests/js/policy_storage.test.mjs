// ENH-3507: createBuilderStorage — injected-storage draft/meta/issue persistence.
import { test } from "node:test";
import assert from "node:assert/strict";

import { createBuilderStorage } from "../../little_loops/templates/policy_builder_core.mjs";

const WS_A = "0123456789abcdef";
const WS_B = "fedcba9876543210";
const MODES = ["decision_table", "rubric", "issue_lifecycle"];

function memStorage() {
  const m = new Map();
  return {
    m,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
  };
}
function make(storage, ctx = null) {
  let warns = 0;
  const api = createBuilderStorage({ storage, connectedContext: ctx, warn: () => { warns += 1; } });
  return { api, warns: () => warns };
}
const META = { projectId: "p1", activeMode: "rubric", schemaVersion: 1, generatorVersion: "g" };

test("offline keys and shapes are byte-identical to the legacy format", () => {
  const st = memStorage();
  const { api } = make(st);
  api.persistDraft("rubric", { a: 1 }, [{ id: "s" }]);
  api.persistMeta(META);
  assert.deepEqual([...st.m.keys()].sort(), ["ll-policy-builder-draft-rubric", "ll-policy-builder-meta"]);
  assert.equal(st.m.get("ll-policy-builder-draft-rubric"), JSON.stringify({ model: { a: 1 }, scenarios: [{ id: "s" }] }));
  assert.equal(st.m.get("ll-policy-builder-meta"), JSON.stringify(META));
  assert.deepEqual(api.readDraft("rubric"), { model: { a: 1 }, scenarios: [{ id: "s" }] });
  assert.deepEqual(api.readMeta(), META);
});

test("connected keys are workspace-namespaced", () => {
  const st = memStorage();
  const { api } = make(st, { workspaceId: WS_A });
  api.persistDraft("rubric", {}, []);
  api.persistMeta(META);
  api.writeIssueSelection("ENH-1");
  assert.deepEqual([...st.m.keys()].sort(), [
    `ll-policy-builder-draft-${WS_A}-rubric`,
    `ll-policy-builder-issue-${WS_A}`,
    `ll-policy-builder-meta-${WS_A}`,
  ]);
  assert.deepEqual(api.readIssueSelection(), { issueId: "ENH-1" });
  api.writeIssueSelection(null);
  assert.equal(api.readIssueSelection(), null);
  assert.equal(st.m.has(`ll-policy-builder-issue-${WS_A}`), false);
});

test("workspaces are mutually invisible and unscoped data is not migrated", () => {
  const st = memStorage();
  make(st).api.persistDraft("rubric", { off: 1 }, []);
  make(st).api.persistMeta(META);
  const a = make(st, { workspaceId: WS_A }).api;
  const b = make(st, { workspaceId: WS_B }).api;
  assert.equal(a.readDraft("rubric"), null);
  assert.equal(a.readMeta(), null);
  a.persistDraft("rubric", { a: 1 }, []);
  a.persistMeta(META);
  a.writeIssueSelection("BUG-2");
  assert.equal(b.readDraft("rubric"), null);
  assert.equal(b.readMeta(), null);
  assert.equal(b.readIssueSelection(), null);
  assert.deepEqual(make(st).api.readDraft("rubric"), { model: { off: 1 }, scenarios: [] });
});

test("offline issue selection is a no-op returning null", () => {
  const st = memStorage();
  const { api } = make(st);
  api.writeIssueSelection("ENH-1");
  assert.equal(api.readIssueSelection(), null);
  assert.equal(st.m.size, 0);
});

test("clearDraftsExcept removes only modes not kept; persistAllDrafts writes each", () => {
  const st = memStorage();
  const { api } = make(st);
  api.persistAllDrafts({ decision_table: { model: 1 }, rubric: { model: 2, scenarios: [1] } });
  assert.equal(st.m.size, 2);
  api.clearDraftsExcept(new Set(["rubric"]), MODES);
  assert.deepEqual([...st.m.keys()], ["ll-policy-builder-draft-rubric"]);
});

function throwingStorage() {
  const boom = () => { throw new Error("blocked"); };
  return { getItem: boom, setItem: boom, removeItem: boom };
}

test("warn fires once per instance, only for persistDraft failures", () => {
  const { api, warns } = make(throwingStorage());
  api.persistMeta(META);
  api.clearDraftsExcept(new Set(), MODES);
  api.writeIssueSelection("X");
  assert.equal(api.readDraft("rubric"), null);
  assert.equal(api.readMeta(), null);
  assert.equal(warns(), 0);
  api.persistDraft("rubric", {}, []);
  api.persistAllDrafts({ rubric: { model: {} }, decision_table: { model: {} } });
  assert.equal(warns(), 1);
  const other = make(throwingStorage());
  other.api.persistDraft("rubric", {}, []);
  assert.equal(other.warns(), 1);
});

test("storage: null never throws; reads null; persistDraft warns once", () => {
  const { api, warns } = make(null, { workspaceId: WS_A });
  assert.equal(api.readDraft("rubric"), null);
  assert.equal(api.readMeta(), null);
  assert.equal(api.readIssueSelection(), null);
  api.persistMeta(META);
  api.clearDraftsExcept(new Set(), MODES);
  api.writeIssueSelection("X");
  api.persistDraft("rubric", {}, []);
  api.persistDraft("rubric", {}, []);
  assert.equal(warns(), 1);
});

test("corrupt stored JSON reads as null", () => {
  const st = memStorage();
  st.m.set("ll-policy-builder-meta", "{nope");
  assert.equal(make(st).api.readMeta(), null);
});
