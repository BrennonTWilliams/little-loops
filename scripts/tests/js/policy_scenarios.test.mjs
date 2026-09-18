// FEAT-3488 node:test — offline scenario suites: normalizeScenarioInput,
// traceModel, evaluateScenario, runScenarioSuite, rulesFingerprint. Exercises
// the shared compiled-rule trace path, the mode-specific input contracts, the
// explicit verdict precedence, and routing-vs-assertion coverage identities.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  seedExample,
  rulesFingerprint,
  normalizeScenarioInput,
  traceModel,
  evaluateScenario,
  runScenarioSuite,
  evaluateModel,
  parseFrontmatterBlock,
  validateProjectStructure,
  BUILDER_PROJECT_SCHEMA_VERSION,
} from "../../little_loops/templates/policy_builder_core.mjs";

// A decision-table model with two authored rules, a repeated target, and a
// derived fallback (no authored catch-all — `deep-repair` is only reachable
// via `model.fallback`, so it is the derived-fallback identity, ruleIndex -1).
function _dtModel() {
  return {
    mode: "decision_table",
    name: "t",
    subject: "x",
    maxSteps: 20,
    thresholdHigh: 85,
    thresholdMedium: 65,
    dimensions: [
      { name: "quality", type: "numeric" },
      { name: "has-citations", type: "boolean" },
    ],
    rules: [
      {
        predicates: [
          { dim: "quality", op: ">=", value: "95" },
          { dim: "has-citations", op: "==true", value: "" },
        ],
        target: "done",
        isCatchall: false,
      },
      { predicates: [{ dim: "quality", op: ">=", value: "80" }], target: "light-repair", isCatchall: false },
    ],
    fallback: "deep-repair",
    outcomes: [
      { name: "done", actionType: "none", body: "", transition: { kind: "finish" } },
      { name: "light-repair", actionType: "prompt", body: "x", transition: { kind: "rescore" } },
      { name: "deep-repair", actionType: "prompt", body: "y", transition: { kind: "rescore" } },
    ],
  };
}

// A decision-table model whose *authored* last rule is itself a catch-all —
// so a win there is an authored catch-all (ruleIndex >= 0, isFallback true
// on the inner MatchResult), never the derived-fallback identity.
function _dtModelWithAuthoredCatchall() {
  const model = _dtModel();
  model.rules.push({ predicates: [], target: "deep-repair", isCatchall: true });
  return model;
}

function _rubricModel() {
  return { mode: "rubric", name: "r", subject: "artifact.md", maxSteps: 10, thresholdHigh: 85, thresholdMedium: 65, dimensions: [], rules: [], fallback: "", outcomes: [] };
}

function _lifecycleModel() {
  return seedExample("issue_lifecycle");
}

// ===========================================================================
// normalizeScenarioInput
// ===========================================================================

test("normalizeScenarioInput (decision_table): booleans encode to 100/0, missing keys stay absent", () => {
  const model = _dtModel();
  const { scores, provenance, diagnostics } = normalizeScenarioInput(model, {
    values: { quality: 90, "has-citations": true },
  });
  assert.deepEqual(diagnostics, []);
  assert.equal(scores.quality, 90);
  assert.equal(scores["has-citations"], 100);
  assert.equal(provenance.quality.rawPresent, true);
  assert.equal(provenance.quality.encodedValue, 90);
});

test("normalizeScenarioInput (decision_table): null, wrong type, out-of-range, and unknown keys are errors", () => {
  const model = _dtModel();
  const nullCase = normalizeScenarioInput(model, { values: { quality: null } });
  assert.ok(nullCase.diagnostics.some((d) => /null/.test(d.message)));

  const wrongType = normalizeScenarioInput(model, { values: { quality: "90" } });
  assert.ok(wrongType.diagnostics.some((d) => /finite number/.test(d.message)));

  const outOfRange = normalizeScenarioInput(model, { values: { quality: 150 } });
  assert.ok(outOfRange.diagnostics.some((d) => /finite number/.test(d.message)));

  const boolWrongType = normalizeScenarioInput(model, { values: { "has-citations": "true" } });
  assert.ok(boolWrongType.diagnostics.some((d) => /must be a boolean/.test(d.message)));

  const unknown = normalizeScenarioInput(model, { values: { bogus: 1 } });
  assert.ok(unknown.diagnostics.some((d) => /not a declared dimension/.test(d.message)));
});

test("normalizeScenarioInput (issue_lifecycle): absent boolean/list source fields stay visibly absent though encoded 0; present-null differs from absent", () => {
  const model = _lifecycleModel();
  const r = normalizeScenarioInput(model, { frontmatterText: "status: open" });
  assert.equal(r.scores.decision_needed, "0");
  assert.equal(r.provenance.decision_needed.rawPresent, false);
  assert.equal(r.provenance.decision_needed.encodedValue, "0");

  const r2 = normalizeScenarioInput(model, { frontmatterText: "status: open\ndecision_needed:" });
  assert.equal(r2.provenance.decision_needed.rawPresent, true);
  assert.equal(r2.provenance.decision_needed.rawValue, null);
});

test("normalizeScenarioInput (issue_lifecycle): priority_rank retains the raw 'priority' source key", () => {
  const model = _lifecycleModel();
  const { provenance, scores } = normalizeScenarioInput(model, { frontmatterText: "priority: P2" });
  assert.equal(provenance.priority_rank.sourceKey, "priority");
  assert.equal(provenance.priority_rank.rawValue, "P2");
  assert.equal(scores.priority_rank, "2");
});

test("normalizeScenarioInput (issue_lifecycle): unsupported parser syntax and a non-string text are errors", () => {
  const model = _lifecycleModel();
  const bad = normalizeScenarioInput(model, { frontmatterText: "x: {a: b}" });
  assert.ok(bad.diagnostics.length > 0);
  const wrongShape = normalizeScenarioInput(model, { frontmatterText: 5 });
  assert.ok(wrongShape.diagnostics.some((d) => /frontmatterText/.test(d.message)));
});

test("normalizeScenarioInput (rubric): integer in range only; string/null/nonfinite/non-integer/out-of-range are errors", () => {
  const model = _rubricModel();
  assert.equal(normalizeScenarioInput(model, { aggregate: 50 }).diagnostics.length, 0);
  for (const bad of ["50", null, NaN, 50.5, -1, 101]) {
    const r = normalizeScenarioInput(model, { aggregate: bad });
    assert.ok(r.diagnostics.length > 0, `expected error for aggregate=${bad}`);
  }
});

// ===========================================================================
// traceModel — full trace, routing-relevant invalid-model definition
// ===========================================================================

test("traceModel: visited-but-failing rule is fully evaluated (for explanation) but not_evaluated after the winner", () => {
  const model = _dtModel();
  const trace = traceModel(model, { values: { quality: 50 } });
  assert.equal(trace.diagnostics.length, 0);
  assert.equal(trace.rules[0].status, "failed");
  assert.equal(trace.rules[0].conditions.length, 2); // both predicates evaluated despite failing
  assert.equal(trace.rules[1].status, "failed");
  // derived fallback row (appended, not authored) is the winner
  const winnerRow = trace.rules[trace.rules.length - 1];
  assert.equal(winnerRow.status, "matched");
  assert.equal(trace.match.ruleIndex, -1);
  assert.equal(trace.match.target, "deep-repair");
  assert.equal(trace.match.isFallback, true);
});

test("traceModel: rule 0 wins, rule 1 is not_evaluated", () => {
  const model = _dtModel();
  const trace = traceModel(model, { values: { quality: 96, "has-citations": true } });
  assert.equal(trace.match.ruleIndex, 0);
  assert.equal(trace.rules[1].status, "not_evaluated");
  assert.deepEqual(trace.rules[1].conditions, []);
});

test("traceModel: authored catch-all win is ruleIndex >= 0, not the derived-fallback identity", () => {
  const model = _dtModelWithAuthoredCatchall();
  const trace = traceModel(model, { values: { quality: 1 } });
  assert.equal(trace.match.ruleIndex, 2); // the authored catch-all's own index
  assert.equal(trace.match.isFallback, true); // MatchResult still reports isFallback for an authored catch-all
});

test("traceModel: 'invalid model' is routing-relevant only — export-readiness errors (empty action body) still route normally", () => {
  const model = _dtModel();
  model.outcomes[1].body = ""; // export-readiness error, not routing-relevant
  const trace = traceModel(model, { values: { quality: 90 } });
  assert.equal(trace.diagnostics.length, 0);
  assert.equal(trace.match.target, "light-repair");
});

test("traceModel: a non-compiling rule table (unfinished predicate) is a routing-relevant invalid-model diagnostic", () => {
  const model = _dtModel();
  model.rules[0].predicates[0].value = ""; // empty value fails to compile
  const trace = traceModel(model, { values: { quality: 90 } });
  assert.ok(trace.diagnostics.some((d) => /does not compile/.test(d.message)));
  assert.equal(trace.match, null);
});

test("traceModel: duplicate normalized dimension names are a routing-relevant invalid-model diagnostic", () => {
  const model = _dtModel();
  model.dimensions.push({ name: "Quality", type: "numeric" }); // normalizes to the same "quality"
  const trace = traceModel(model, { values: { quality: 90 } });
  assert.ok(trace.diagnostics.some((d) => /Duplicate normalized dimension/.test(d.message)));
});

test("traceModel (rubric): inverted or non-finite thresholds are a routing-relevant invalid-model diagnostic", () => {
  const model = _rubricModel();
  model.thresholdHigh = 50;
  model.thresholdMedium = 60; // inverted
  const trace = traceModel(model, { aggregate: 55 });
  assert.ok(trace.diagnostics.some((d) => /threshold/.test(d.message)));
});

test("traceModel (rubric): high/medium/low branches, inclusive at both thresholds", () => {
  const model = _rubricModel();
  assert.equal(traceModel(model, { aggregate: 84 }).rubricBranch, "medium");
  assert.equal(traceModel(model, { aggregate: 85 }).rubricBranch, "high"); // at threshold_high -> high
  assert.equal(traceModel(model, { aggregate: 64 }).rubricBranch, "low");
  assert.equal(traceModel(model, { aggregate: 65 }).rubricBranch, "medium"); // at threshold_medium -> medium
});

test("evaluateModel's legacy MatchResult shape is unaffected by the shared trace refactor", () => {
  const model = _dtModel();
  const result = evaluateModel(model, { quality: 96, "has-citations": 100 });
  assert.deepEqual(result, { ruleIndex: 0, target: "done", isFallback: false, conditionResults: [true, true] });
});

// ===========================================================================
// rulesFingerprint
// ===========================================================================

test("rulesFingerprint: changing only the fallback target leaves the fingerprint unchanged", () => {
  const model = _dtModel();
  const fp1 = rulesFingerprint(model);
  model.fallback = "some-other-outcome";
  assert.equal(rulesFingerprint(model), fp1);
});

test("rulesFingerprint: reordering or editing an authored rule changes the fingerprint", () => {
  const model = _dtModel();
  const fp1 = rulesFingerprint(model);
  const reordered = { ...model, rules: [model.rules[1], model.rules[0]] };
  assert.notEqual(rulesFingerprint(reordered), fp1);
  const edited = _dtModel();
  edited.rules[0].predicates[0].value = "96";
  assert.notEqual(rulesFingerprint(edited), fp1);
});

// ===========================================================================
// evaluateScenario — verdict precedence
// ===========================================================================

test("evaluateScenario: target-only pass/fail", () => {
  const model = _dtModel();
  const pass = evaluateScenario(model, { id: "s", input: { values: { quality: 90 } }, expectedTarget: "light-repair" });
  assert.equal(pass.verdict, "pass");
  const fail = evaluateScenario(model, { id: "s", input: { values: { quality: 90 } }, expectedTarget: "done" });
  assert.equal(fail.verdict, "fail");
});

test("evaluateScenario: null expectedTarget is unasserted (never manufactures its own oracle)", () => {
  const model = _dtModel();
  const r = evaluateScenario(model, { id: "s", input: { values: { quality: 90 } }, expectedTarget: null });
  assert.equal(r.verdict, "unasserted");
  assert.equal(r.needsReview, false);
});

test("evaluateScenario: current index + target match/mismatch behave as ordinary pass/fail", () => {
  const model = _dtModel();
  const fp = rulesFingerprint(model);
  const pass = evaluateScenario(model, {
    id: "s", input: { values: { quality: 96, "has-citations": true } },
    expectedTarget: "done", expectedRuleIndex: 0, expectedRulesFingerprint: fp,
  });
  assert.equal(pass.verdict, "pass");
  const fail = evaluateScenario(model, {
    id: "s", input: { values: { quality: 96, "has-citations": true } },
    expectedTarget: "done", expectedRuleIndex: 1, expectedRulesFingerprint: fp,
  });
  assert.equal(fail.verdict, "fail");
});

test("evaluateScenario: a stale or missing fingerprint on an index expectation needs review, regardless of target match", () => {
  const model = _dtModel();
  const staleFp = evaluateScenario(model, {
    id: "s", input: { values: { quality: 96, "has-citations": true } },
    expectedTarget: "done", expectedRuleIndex: 0, expectedRulesFingerprint: "stale-value",
  });
  assert.equal(staleFp.verdict, "unasserted");
  assert.equal(staleFp.needsReview, true);

  const missingFp = evaluateScenario(model, {
    id: "s", input: { values: { quality: 96, "has-citations": true } },
    expectedTarget: "done", expectedRuleIndex: 0,
  });
  assert.equal(missingFp.verdict, "unasserted");
  assert.equal(missingFp.needsReview, true);
});

test("evaluateScenario: reordering rules stales a rule-index expectation (needs review) even though the target still matches", () => {
  const model = _dtModel();
  const fp = rulesFingerprint(model);
  const reordered = { ...model, rules: [model.rules[1], model.rules[0]] };
  const r = evaluateScenario(reordered, {
    id: "s", input: { values: { quality: 96, "has-citations": true } },
    expectedTarget: "done", expectedRuleIndex: 0, expectedRulesFingerprint: fp,
  });
  assert.equal(r.verdict, "unasserted");
  assert.equal(r.needsReview, true);
});

test("evaluateScenario: an out-of-range index claiming a current fingerprint is an error", () => {
  const model = _dtModel();
  const fp = rulesFingerprint(model);
  const r = evaluateScenario(model, {
    id: "s", input: { values: { quality: 96, "has-citations": true } },
    expectedTarget: "done", expectedRuleIndex: 99, expectedRulesFingerprint: fp,
  });
  assert.equal(r.verdict, "error");
});

test("evaluateScenario: invalid input combined with a stale fingerprint — error wins over needs-review", () => {
  const model = _dtModel();
  const r = evaluateScenario(model, {
    id: "s", input: { values: { quality: "not-a-number" } },
    expectedTarget: "done", expectedRuleIndex: 0, expectedRulesFingerprint: "stale",
  });
  assert.equal(r.verdict, "error");
});

test("evaluateScenario: a removed expected target (not in the current policy) is an error", () => {
  const model = _dtModel();
  const r = evaluateScenario(model, { id: "s", input: { values: { quality: 90 } }, expectedTarget: "no-longer-exists" });
  assert.equal(r.verdict, "error");
});

test("evaluateScenario: a null target combined with expectedRuleIndex is invalid (error), not an implicit index-only assertion", () => {
  const model = _dtModel();
  const r = evaluateScenario(model, { id: "s", input: { values: { quality: 90 } }, expectedTarget: null, expectedRuleIndex: 0 });
  assert.equal(r.verdict, "error");
});

test("evaluateScenario: expectedFallback passes only for the derived fallback, fails for an authored catch-all with the same target, and is rejected alongside expectedRuleIndex", () => {
  const model = _dtModel();
  const passDerived = evaluateScenario(model, {
    id: "s", input: { values: { quality: 1 } }, expectedTarget: "deep-repair", expectedFallback: true,
  });
  assert.equal(passDerived.verdict, "pass");

  const authoredModel = _dtModelWithAuthoredCatchall();
  const failsOnAuthoredCatchall = evaluateScenario(authoredModel, {
    id: "s", input: { values: { quality: 1 } }, expectedTarget: "deep-repair", expectedFallback: true,
  });
  assert.equal(failsOnAuthoredCatchall.verdict, "fail");

  const mutuallyExclusive = evaluateScenario(model, {
    id: "s", input: { values: { quality: 1 } }, expectedTarget: "deep-repair",
    expectedFallback: true, expectedRuleIndex: 0,
  });
  assert.equal(mutuallyExclusive.verdict, "error");
});

test("evaluateScenario (rubric): unknown target, expectedRuleIndex, and expectedFallback all produce rubric expectation errors", () => {
  const model = _rubricModel();
  assert.equal(evaluateScenario(model, { id: "s", input: { aggregate: 90 }, expectedTarget: "not-a-rubric-target" }).verdict, "error");
  assert.equal(evaluateScenario(model, { id: "s", input: { aggregate: 90 }, expectedTarget: "done", expectedRuleIndex: 0 }).verdict, "error");
  assert.equal(evaluateScenario(model, { id: "s", input: { aggregate: 90 }, expectedTarget: "done", expectedFallback: true }).verdict, "error");
});

test("evaluateScenario (rubric): default rubric model with no authored outcomes still accepts done/light_repair/deep_repair assertions", () => {
  const model = _rubricModel();
  assert.equal(evaluateScenario(model, { id: "s", input: { aggregate: 90 }, expectedTarget: "done" }).verdict, "pass");
  assert.equal(evaluateScenario(model, { id: "s", input: { aggregate: 70 }, expectedTarget: "light_repair" }).verdict, "pass");
  assert.equal(evaluateScenario(model, { id: "s", input: { aggregate: 10 }, expectedTarget: "deep_repair" }).verdict, "pass");
});

test("evaluateScenario: explicit reconfirmation followed by undo — reconfirm never happens implicitly (contract check, not UI)", () => {
  // Core never manufactures an expectation on its own; a scenario's
  // expectation only ever changes via an explicit field the caller sets.
  const model = _dtModel();
  const untouched = { id: "s", input: { values: { quality: 96, "has-citations": true } }, expectedTarget: null };
  const before = evaluateScenario(model, untouched);
  assert.equal(before.verdict, "unasserted");
  assert.equal(untouched.expectedTarget, null); // evaluateScenario is read-only over the scenario
});

// ===========================================================================
// runScenarioSuite — totals, coverage, duplicate IDs
// ===========================================================================

test("runScenarioSuite: totals distinguish pass/fail/unasserted/error", () => {
  const model = _dtModel();
  const scenarios = [
    { id: "a", input: { values: { quality: 90 } }, expectedTarget: "light-repair" }, // pass
    { id: "b", input: { values: { quality: 90 } }, expectedTarget: "done" }, // fail
    { id: "c", input: { values: { quality: 90 } }, expectedTarget: null }, // unasserted
    { id: "d", input: { values: { bogus: 1 } }, expectedTarget: "done" }, // error
  ];
  const suite = runScenarioSuite(model, scenarios);
  assert.deepEqual(suite.summary, { passed: 1, failed: 1, unasserted: 1, errors: 1 });
});

test("runScenarioSuite: a visited-but-failing rule appears only in evaluated coverage, never winning coverage", () => {
  const model = _dtModel();
  const suite = runScenarioSuite(model, [
    { id: "a", input: { values: { quality: 50 } }, expectedTarget: null }, // both rules fail, fallback wins
  ]);
  assert.deepEqual(suite.coverage.evaluatedRuleIndexes, [0, 1]);
  assert.deepEqual(suite.coverage.winningRuleIndexes, []);
  assert.equal(suite.coverage.fallback.applicable, true);
  assert.equal(suite.coverage.fallback.covered, true);
});

test("runScenarioSuite: authored catch-all coverage belongs to its own index, not the derived-fallback identity", () => {
  const model = _dtModelWithAuthoredCatchall();
  const suite = runScenarioSuite(model, [{ id: "a", input: { values: { quality: 1 } }, expectedTarget: null }]);
  assert.deepEqual(suite.coverage.winningRuleIndexes, [2]);
  assert.equal(suite.coverage.fallback.applicable, false); // no derived fallback emitted — authored catch-all supplies it
  assert.equal(suite.coverage.fallback.covered, false);
});

test("runScenarioSuite: invalid model/input cases (including duplicate scenario IDs) contribute no coverage", () => {
  const model = _dtModel();
  const scenarios = [
    { id: "dup", input: { values: { quality: 96, "has-citations": true } }, expectedTarget: "done" },
    { id: "dup", input: { values: { quality: 96, "has-citations": true } }, expectedTarget: "done" },
  ];
  const suite = runScenarioSuite(model, scenarios);
  assert.equal(suite.summary.errors, 2);
  assert.deepEqual(suite.coverage.winningRuleIndexes, []);
  assert.ok(suite.results.every((r) => r.diagnostics.some((d) => /Duplicate scenario id/.test(d.message))));
});

test("runScenarioSuite: uncoveredRuleIndexes reports authored rules no scenario won", () => {
  const model = _dtModel();
  const suite = runScenarioSuite(model, [
    { id: "a", input: { values: { quality: 96, "has-citations": true } }, expectedTarget: null },
  ]);
  assert.deepEqual(suite.coverage.winningRuleIndexes, [0]);
  assert.deepEqual(suite.coverage.uncoveredRuleIndexes, [1]);
});

// ===========================================================================
// parseFrontmatterBlock — quoted literal counterparts of the new reject fixtures
// ===========================================================================

test("parseFrontmatterBlock: quoted literal text containing {, !, |, or an unclosed [ remains valid (only unquoted constructs are rejected)", () => {
  assert.deepEqual(parseFrontmatterBlock('x: "{a: b}"'), { x: "{a: b}" });
  assert.deepEqual(parseFrontmatterBlock('x: "!!str 5"'), { x: "!!str 5" });
  assert.deepEqual(parseFrontmatterBlock('x: "|"'), { x: "|" });
  assert.deepEqual(parseFrontmatterBlock('x: "[a"'), { x: "[a" });
});

// ===========================================================================
// validateProjectStructure / parseBuilderProject — scenario shape rejection
// ===========================================================================

test("validateProjectStructure rejects a structurally invalid scenario (missing id/input) without touching the rest of the project", () => {
  const project = {
    schemaVersion: BUILDER_PROJECT_SCHEMA_VERSION,
    generatorVersion: "0.0.0-test",
    projectId: "p",
    activeMode: "decision_table",
    drafts: {
      decision_table: {
        model: seedExample("decision_table"),
        scenarios: [{ name: "no-id-or-input" }],
      },
    },
  };
  const errors = validateProjectStructure(project);
  assert.ok(errors.some((e) => /scenarios\[0\]\.id/.test(e)));
  assert.ok(errors.some((e) => /scenarios\[0\]\.input/.test(e)));
});

test("runScenarioSuite (rubric): non-applicable rule-coverage collections stay empty; rubric branches populate instead", () => {
  const model = _rubricModel();
  const suite = runScenarioSuite(model, [
    { id: "a", input: { aggregate: 90 }, expectedTarget: null },
    { id: "b", input: { aggregate: 10 }, expectedTarget: null },
  ]);
  assert.deepEqual(suite.coverage.winningRuleIndexes, []);
  assert.deepEqual(suite.coverage.evaluatedRuleIndexes, []);
  assert.deepEqual(suite.coverage.winningRubricBranches.sort(), ["high", "low"]);
  assert.deepEqual(suite.coverage.uncoveredRubricBranches, ["medium"]);
  assert.equal(suite.coverage.fallback.applicable, false);
});
