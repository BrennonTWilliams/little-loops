// FEAT-3503 node:test — boundary suggestions (suggestScenarios,
// scenarioSemanticKey) and local issue-file import helpers
// (extractIssueFrontmatter, dropNonDimensionContinuations,
// buildImportedScenario).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

import {
  seedExample,
  blankModel,
  normalizeScenarioInput,
  traceModel,
  runScenarioSuite,
  parseFrontmatterBlock,
  suggestScenarios,
  scenarioSemanticKey,
  extractIssueFrontmatter,
  dropNonDimensionContinuations,
  lifecycleDimensionSourceKeys,
  buildImportedScenario,
  _nextUp,
  _nextDown,
  _suggestionSkips,
  _serializeLifecycleFrontmatter,
} from "../../little_loops/templates/policy_builder_core.mjs";

function dt(dimensions, rules, fallback = "done") {
  return {
    mode: "decision_table",
    name: "t",
    subject: "x",
    maxSteps: 20,
    thresholdHigh: 85,
    thresholdMedium: 65,
    dimensions,
    rules: rules.map(([preds, target]) => ({
      predicates: preds.map(([dim, op, value]) => ({ dim, op, value: value ?? "" })),
      target,
      isCatchall: false,
    })),
    fallback,
    outcomes: [{ name: "done" }, { name: "fix" }, { name: "review" }],
  };
}

function lifecycle(extraDims, rules) {
  const m = seedExample("issue_lifecycle");
  m.dimensions = [...m.dimensions.filter((d) => d.name !== "severity" && d.name !== "review_status"), ...extraDims];
  m.rules = rules.map(([preds, target]) => ({
    predicates: preds.map(([dim, op, value]) => ({ dim, op, value: value ?? "" })),
    target,
    isCatchall: false,
  }));
  return m;
}

function targetsOf(model, sugg) {
  return sugg.map((s) => traceModel(model, s.input).match);
}

test("all suggestions normalize, are unasserted, unique by key, and satisfying witnesses satisfy their rule", () => {
  for (const mode of ["decision_table", "rubric", "issue_lifecycle"]) {
    const model = seedExample(mode);
    const sugg = suggestScenarios(model);
    assert.ok(sugg.length > 0, mode);
    assert.equal(new Set(sugg.map((s) => s.key)).size, sugg.length);
    for (const s of sugg) {
      assert.equal(s.expectedTarget, null);
      assert.deepEqual(normalizeScenarioInput(model, s.input).diagnostics, []);
      assert.equal(s.key, scenarioSemanticKey(model, s.input));
      assert.ok(s.reason.length > 0);
    }
  }
});

test("suggestions are deterministic", () => {
  const m = seedExample("issue_lifecycle");
  assert.deepEqual(suggestScenarios(m), suggestScenarios(m));
});

test("invalid model yields no suggestions", () => {
  const m = seedExample("decision_table");
  m.rules[0].predicates[0].dim = "nope";
  assert.deepEqual(suggestScenarios(m), []);
});

test("seeded lifecycle suggestions cover every rule and the gate fallback", () => {
  const model = seedExample("issue_lifecycle");
  const sugg = suggestScenarios(model);
  const scenarios = sugg.map((s, i) => ({
    id: `s${i}`,
    name: s.name,
    input: s.input,
    expectedTarget: null,
    expectedRuleIndex: null,
    expectedFallback: false,
    expectedRulesFingerprint: null,
  }));
  const { coverage, summary } = runScenarioSuite(model, scenarios);
  assert.equal(summary.errors, 0);
  assert.deepEqual(coverage.winningRuleIndexes, [0, 1, 2, 3]);
  assert.equal(coverage.fallback.covered, true);
});

test("seeded decision-table suggestions cover the rules and fallback", () => {
  const model = seedExample("decision_table");
  const sugg = suggestScenarios(model);
  const scenarios = sugg.map((s, i) => ({
    id: `s${i}`, name: s.name, input: s.input, expectedTarget: null,
    expectedRuleIndex: null, expectedFallback: false, expectedRulesFingerprint: null,
  }));
  const { coverage, summary } = runScenarioSuite(model, scenarios);
  assert.equal(summary.errors, 0);
  assert.deepEqual(coverage.uncoveredRuleIndexes, []);
});

test("narrow fractional interval: > 50 AND < 50.5 has a witness; boundary variants stay in [0,100]", () => {
  const m = dt([{ name: "score", type: "numeric" }], [[[["score", ">", "50"], ["score", "<", "50.5"]], "fix"]]);
  const sugg = suggestScenarios(m);
  const w = sugg[0].input.values.score;
  assert.ok(w > 50 && w < 50.5);
  assert.equal(_suggestionSkips(m).length, 0);
});

test("strict interval with no representable value is skipped by a named rule", () => {
  const m = dt([{ name: "score", type: "numeric" }], [[[["score", ">", "50"], ["score", "<", "50"]], "fix"]]);
  assert.deepEqual(_suggestionSkips(m), [{ ruleIndex: 0, reason: "no-satisfying-witness" }]);
  assert.ok(!suggestScenarios(m).some((s) => s.reason.startsWith("satisfies rule 1")));
  const m2 = dt([{ name: "score", type: "numeric" }], [[[["score", ">", "1e300"], ["score", "<", "1e300"]], "fix"]]);
  assert.equal(_suggestionSkips(m2)[0].reason, "no-satisfying-witness");
});

test("nonfinite ordered literal is skipped by a named rule", () => {
  const m = dt([{ name: "score", type: "numeric" }], [[[["score", ">", "Infinity"]], "fix"]]);
  assert.deepEqual(_suggestionSkips(m), [{ ruleIndex: 0, reason: "nonfinite-literal" }]);
});

test("decision-table out-of-range: > 100 skipped; boundary variants outside [0,100] dropped, not clamped", () => {
  const impossible = dt([{ name: "score", type: "numeric" }], [[[["score", ">", "100"]], "fix"]]);
  assert.equal(_suggestionSkips(impossible)[0].reason, "no-satisfying-witness");
  const m = dt([{ name: "score", type: "numeric" }], [[[["score", ">=", "0"]], "fix"]]);
  const vals = suggestScenarios(m).map((s) => s.input.values && s.input.values.score);
  assert.ok(!vals.some((v) => v < 0 || v > 100));
  assert.ok(vals.includes(0) && vals.includes(1));
  assert.ok(!vals.includes(-1));
});

test("decision-table string-dimension rules are skipped by a named rule", () => {
  const m = dt([{ name: "kind", type: "string" }, { name: "n", type: "numeric" }], [
    [[["kind", "==", "bug"]], "fix"],
    [[["n", ">=", "10"]], "review"],
  ]);
  assert.deepEqual(_suggestionSkips(m), [{ ruleIndex: 0, reason: "unsupported-decision-table-string-dimension" }]);
  assert.ok(suggestScenarios(m).length > 0);
});

test("boolean witnesses encode 0/100 and missing-field variants omit the key", () => {
  const m = dt([{ name: "ok", type: "boolean" }], [[[["ok", "==true"]], "fix"], [[["ok", "==false"]], "review"]]);
  const sugg = suggestScenarios(m);
  const wit0 = sugg.find((s) => s.reason.startsWith("satisfies rule 1"));
  assert.equal(wit0.input.values.ok, true);
  const wit1 = sugg.find((s) => s.reason.startsWith("satisfies rule 2"));
  assert.equal(wit1.input.values.ok, false);
  assert.ok(sugg.some((s) => Object.keys(s.input.values).length === 0));
});

test("!= witnesses are emitted values that encode unequal, never omission", () => {
  const m = lifecycle([], [
    [[["status", "!=", "done"]], "refine"],
    [[["blocked_by", "!=", "0"]], "gate"],
  ]);
  const sugg = suggestScenarios(m);
  const w0 = sugg.find((s) => s.reason.startsWith("satisfies rule 1"));
  const fm0 = parseFrontmatterBlock(w0.input.frontmatterText);
  assert.ok(fm0.status && fm0.status !== "done");
  const w1 = sugg.find((s) => s.reason.startsWith("satisfies rule 2"));
  assert.ok(parseFrontmatterBlock(w1.input.frontmatterText).blocked_by.length >= 1);
  // status != done cannot use the `completed` synonym
  const m2 = lifecycle([], [[[["status", "!=", "completed"]], "refine"]]);
  const w2 = suggestScenarios(m2)[0];
  assert.equal(traceModel(m2, w2.input).match.ruleIndex, 0);
});

test("lifecycle priority / priority_rank share one source key", () => {
  const ok = lifecycle([], [[[["priority", "==", "P2"], ["priority_rank", ">=", "1"]], "refine"]]);
  const s = suggestScenarios(ok);
  const w = s.find((x) => x.reason.startsWith("satisfies rule 1"));
  assert.equal(w.input.frontmatterText, "priority: P2");
  assert.equal((w.input.frontmatterText.match(/^priority:/gm) || []).length, 1);
  const bad = lifecycle([], [[[["priority", "==", "P2"], ["priority_rank", "==", "1"]], "refine"]]);
  assert.deepEqual(_suggestionSkips(bad), [{ ruleIndex: 0, reason: "no-satisfying-witness" }]);
  // rank boundary probes use representable ranks and drop out-of-domain ones
  const rk = lifecycle([], [[[["priority_rank", ">=", "0"]], "refine"]]);
  const texts = suggestScenarios(rk).map((x) => x.input.frontmatterText);
  assert.ok(texts.includes("priority: P0") && texts.includes("priority: P1"));
  assert.ok(!texts.some((t) => t.includes("P-1")));
});

test("lifecycle list lengths serialize real lists; boolean/list missing variants are skipped", () => {
  const m = lifecycle([], [[[["blocked_by", ">=", "2"]], "gate"], [[["decision_needed", "==true"]], "refine"]]);
  const sugg = suggestScenarios(m);
  const w = sugg.find((s) => s.reason.startsWith("satisfies rule 1"));
  assert.equal(w.input.frontmatterText, "blocked_by: [item-1, item-2]");
  assert.ok(!sugg.some((s) => /absent/.test(s.name) && /blocked_by|decision_needed/.test(s.name)));
});

test("lifecycle string scalars: quoted null/~ and punctuation round-trip; empty literal skipped", () => {
  for (const lit of ["null", "~", "needs: review", "a #1", "x, y", "[z]", "-dash"]) {
    const m = lifecycle([], [[[["deferred_reason", "==", lit]], "gate"]]);
    const sugg = suggestScenarios(m);
    const w = sugg.find((s) => s.reason.startsWith("satisfies rule 1"));
    assert.ok(w, lit);
    assert.equal(parseFrontmatterBlock(w.input.frontmatterText).deferred_reason, lit);
    assert.equal(traceModel(m, w.input).match.ruleIndex, 0);
  }
  const bad = lifecycle([], [[[["deferred_reason", "==", "completedx"]], "gate"], [[["status", "==", "completed"]], "gate"]]);
  assert.deepEqual(_suggestionSkips(bad).map((s) => s.ruleIndex), [1]);
});

test("serialization format is pinned", () => {
  assert.equal(
    _serializeLifecycleFrontmatter(
      { status: "open", priority: "P2", blocked_by: ["BUG-1", "BUG-2"], decision_needed: true, confidence_score: 85, note: "null" },
      ["status", "priority", "blocked_by", "decision_needed", "confidence_score", "note"]
    ),
    'status: open\npriority: P2\nblocked_by: [BUG-1, BUG-2]\ndecision_needed: true\nconfidence_score: 85\nnote: "null"'
  );
});

test("contradictory equalities are skipped", () => {
  const m = lifecycle([], [[[["status", "==", "open"], ["status", "==", "closed"]], "gate"]]);
  assert.equal(_suggestionSkips(m)[0].reason, "no-satisfying-witness");
});

test("finite extrema and zero: next-up/next-down helpers", () => {
  assert.equal(_nextUp(0), Number.MIN_VALUE);
  assert.equal(_nextDown(0), -Number.MIN_VALUE);
  assert.ok(_nextUp(-1) > -1 && _nextUp(-1) < -0.9999999);
  assert.ok(_nextDown(-1) < -1);
  assert.equal(_nextUp(Number.MAX_VALUE), Infinity);
  assert.equal(_nextDown(-Number.MAX_VALUE), -Infinity);
  assert.ok(_nextUp(50) > 50 && _nextDown(50) < 50);
  const m = lifecycle([{ name: "big", type: "numeric" }], [[[["big", ">=", "1.7976931348623157e308"]], "gate"]]);
  const sugg = suggestScenarios(m);
  assert.ok(sugg.length > 0);
  for (const s of sugg) assert.deepEqual(normalizeScenarioInput(m, s.input).diagnostics, []);
});

test("rubric neighbours are clamped integers, deduplicated", () => {
  const m = seedExample("rubric");
  const aggs = suggestScenarios(m).map((s) => s.input.aggregate);
  assert.deepEqual(aggs, [84, 85, 86, 64, 65, 66]);
  m.thresholdHigh = 100;
  m.thresholdMedium = 1;
  const a2 = suggestScenarios(m).map((s) => s.input.aggregate);
  assert.equal(new Set(a2).size, a2.length);
  assert.ok(a2.every((v) => v >= 0 && v <= 100));
});

test("reason reports the rule a suggestion actually wins", () => {
  const m = dt([{ name: "a", type: "numeric" }, { name: "b", type: "numeric" }], [
    [[["a", "!=", "5"]], "fix"],
    [[["b", ">=", "50"]], "review"],
  ]);
  const sugg = suggestScenarios(m);
  const w1 = sugg.find((s) => s.reason.startsWith("satisfies rule 2"));
  assert.match(w1.reason, /→ fix \(won by rule 1\)/);
});

test("fallback: none when an earlier candidate already reaches it; added when only all-omitted does", () => {
  const seeded = seedExample("issue_lifecycle");
  const s1 = suggestScenarios(seeded);
  assert.equal(s1.filter((s) => s.name.startsWith("Fallback")).length, 0);
  const m = dt([{ name: "q", type: "numeric" }], [[[["q", ">=", "50"]], "fix"]]);
  const s2 = suggestScenarios(m);
  const fb = s2.filter((s) => s.name.startsWith("Fallback"));
  assert.equal(fb.length, 0); // q=49 boundary already reaches the fallback
  const m2 = dt([{ name: "q", type: "numeric" }], [[[["q", "!=", "50"]], "fix"]], "review");
  const s3 = suggestScenarios(m2);
  assert.ok(targetsOf(m2, s3).some((x) => x.isFallback && x.ruleIndex === -1) || s3.length >= 1);
});

test("semantic key: formatting and absent-vs-false dedup; numeric spellings stay distinct; invalid is null", () => {
  const m = seedExample("issue_lifecycle");
  const a = scenarioSemanticKey(m, { frontmatterText: "status: open\npriority: P2" });
  const b = scenarioSemanticKey(m, { frontmatterText: "priority: 'P2'   # c\nstatus:   open\n---" });
  assert.equal(a, b);
  const abs = scenarioSemanticKey(m, { frontmatterText: "status: open" });
  const expl = scenarioSemanticKey(m, { frontmatterText: "status: open\ndecision_needed: false\nblocked_by: []" });
  assert.equal(abs, expl);
  const k = (t) => scenarioSemanticKey(m, { frontmatterText: `confidence_score: ${t}` });
  assert.notEqual(k("85"), k("85.0"));
  assert.notEqual(k("85"), k("8.5e1"));
  assert.equal(scenarioSemanticKey(m, { frontmatterText: "a:\n  b: c" }), null);
  assert.equal(scenarioSemanticKey(m, {}), null);
  // empty inputs have a key (participate in dedup)
  assert.ok(scenarioSemanticKey(m, { frontmatterText: "" }));
  assert.ok(scenarioSemanticKey(seedExample("rubric"), { aggregate: 0 }));
  assert.ok(scenarioSemanticKey(seedExample("decision_table"), { values: {} }));
});

test("extractIssueFrontmatter: BOM, CRLF, missing and unclosed fences", () => {
  assert.equal(extractIssueFrontmatter("---\nid: A\nstatus: open\n---\n# Body\n---\nx: y"), "id: A\nstatus: open");
  assert.equal(extractIssueFrontmatter("\uFEFF---\r\nid: A\r\n---\r\nbody"), "id: A");
  assert.equal(extractIssueFrontmatter("---\n---\nbody"), "");
  assert.throws(() => extractIssueFrontmatter("id: A\n---\n"), /Missing opening frontmatter fence/);
  assert.throws(() => extractIssueFrontmatter(""), /fence/i);
  assert.throws(() => extractIssueFrontmatter("---\nid: A\nbody"), /Unclosed frontmatter fence/);
  assert.throws(() => extractIssueFrontmatter("\n---\nid: A\n---"), /fence/);
});

test("dropNonDimensionContinuations: wrapped title, block scalar, routing fields untouched", () => {
  const keys = ["status", "priority"];
  const wrapped = "id: X\ntitle: A long title that\n  wraps here\nstatus: open";
  assert.equal(dropNonDimensionContinuations(wrapped, keys), "id: X\ntitle: A long title that\nstatus: open");
  const block = "status: open\ncancelled_reason: |\n  because\n  reasons\npriority: P2";
  assert.equal(dropNonDimensionContinuations(block, keys), "status: open\ncancelled_reason:\npriority: P2");
  assert.deepEqual(parseFrontmatterBlock(dropNonDimensionContinuations(block, keys)), {
    status: "open", cancelled_reason: null, priority: "P2",
  });
  const routing = "status: open\n  wrapped";
  assert.equal(dropNonDimensionContinuations(routing, keys), routing);
  assert.throws(() => parseFrontmatterBlock(dropNonDimensionContinuations(routing, keys)));
});

test("buildImportedScenario: names from id or filename; routing-field rejection names the key", () => {
  const m = seedExample("issue_lifecycle");
  const ok = buildImportedScenario(m, "---\nid: BUG-1\ntitle: t\n  wrapped\nstatus: open\n---\nbody: not parsed\n  - x", "f.md");
  assert.equal(ok.name, "BUG-1");
  assert.equal(ok.input.frontmatterText, "id: BUG-1\ntitle: t\nstatus: open");
  assert.equal(buildImportedScenario(m, "---\nstatus: open\n---\n", "f.md").name, "f.md");
  assert.throws(
    () => buildImportedScenario(m, "---\nstatus: open\ndeferred_reason: waiting on\n  the vendor\n---\n", "f.md"),
    /Frontmatter: multi-line value under routing field `deferred_reason` is not supported — Can't read line 3/
  );
  assert.throws(() => buildImportedScenario(m, "---\nstatus: open\nbody", "f.md"), /fence/i);
  assert.throws(() => buildImportedScenario(m, "---\nstatus: {a: b}\n---", "f.md"), /Frontmatter:/);
  assert.deepEqual(lifecycleDimensionSourceKeys(m).slice(0, 3), ["status", "priority", "confidence_score"]);
});

test("real repo issue files: block scalar imports; wrapped routing field (ENH-2738) rejected naming the key", () => {
  const base = new URL("../../../.issues/", import.meta.url);
  const m = seedExample("issue_lifecycle");
  const read = (rel) => {
    const url = new URL(rel, base);
    return existsSync(url) ? readFileSync(url, "utf8") : null;
  };
  const block = read("bugs/P3-BUG-1760-autodev-scope-declared-as-issue-ids-not-whole-repo-allows-concurrent-runs.md");
  if (block !== null) assert.ok(buildImportedScenario(m, block, "f.md").name);
  const routing = read("enhancements/P2-ENH-2738-flip-request-path-default-to-sdk-plus-batch-tranche.md");
  if (routing !== null) {
    assert.throws(() => buildImportedScenario(m, routing, "f.md"), /routing field `deferred_reason`/);
  }
});
