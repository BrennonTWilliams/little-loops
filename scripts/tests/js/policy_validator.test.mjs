// FEAT-2301 node:test — exercises the JS policy core against the shared
// conformance corpus (same JSON the Python tests pin) and the golden YAML.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  parseRuleTable,
  evaluateRules,
  detectShadows,
  serializeLoopYaml,
  compileBooleanPredicate,
  normalizeDimName,
  isCatchall,
  moveRule,
  seedExample,
  blankModel,
} from "../../little_loops/templates/policy_builder_core.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXT = join(__dirname, "..", "fixtures", "policy_builder");

const corpus = JSON.parse(readFileSync(join(FIXT, "conformance_corpus.json"), "utf8"));

// Grammar mirroring grammar_spec().pred_pattern (Python source). parseRuleTable
// translates the named-group syntax internally; pass the Python pattern to prove
// the translation path works.
const grammar = {
  pred_pattern: "^(?P<dim>[\\w][\\w\\s\\-]*?)\\s*:\\s*(?P<op>>=|<=|==|!=|<|>)\\s*(?P<value>\\S.*?)$",
};

test("evaluate_cases match canonical semantics", () => {
  for (const c of corpus.evaluate_cases) {
    const rules = parseRuleTable(c.rules, grammar);
    const got = evaluateRules(rules, c.scores);
    assert.equal(got, c.expected_target, `${c.name}: got ${JSON.stringify(got)}`);
  }
});

test("shadow_cases match canonical detection", () => {
  for (const c of corpus.shadow_cases) {
    const rules = parseRuleTable(c.rules, grammar);
    const got = detectShadows(rules)
      .map((s) => s.ruleNumber)
      .sort((a, b) => a - b);
    const want = [...c.expected_shadowed_rule_numbers].sort((a, b) => a - b);
    assert.deepEqual(got, want, `${c.name}: got ${JSON.stringify(got)}`);
  }
});

test("parseRuleTable works without an explicit grammar (default regex)", () => {
  const rules = parseRuleTable("security:<65 -> escalate\n* -> done");
  assert.equal(rules.length, 2);
  assert.equal(rules[0].predicates[0].dim, "security");
  assert.equal(rules[0].predicates[0].op, "<");
  assert.ok(isCatchall(rules[1]));
});

test("compileBooleanPredicate maps true/false to numeric", () => {
  assert.deepEqual(compileBooleanPredicate("==true"), { op: ">=", value: "50" });
  assert.deepEqual(compileBooleanPredicate("==false"), { op: "<", value: "50" });
});

test("normalizeDimName lowercases and hyphenates", () => {
  assert.equal(normalizeDimName("  Has  Tests "), "has-tests");
});

test("serializeLoopYaml matches golden decision-table fixture", () => {
  const model = JSON.parse(readFileSync(join(FIXT, "sample-decision-table.model.json"), "utf8"));
  const golden = readFileSync(join(FIXT, "sample-decision-table.yaml"), "utf8");
  assert.equal(serializeLoopYaml(model), golden);
});

test("serializeLoopYaml matches golden rubric fixture", () => {
  const model = JSON.parse(readFileSync(join(FIXT, "sample-rubric.model.json"), "utf8"));
  const golden = readFileSync(join(FIXT, "sample-rubric.yaml"), "utf8");
  assert.equal(serializeLoopYaml(model), golden);
});

// ---------------------------------------------------------------------------
// FEAT-2301: reorder + seed/blank pure-model helpers
// ---------------------------------------------------------------------------

test("moveRule moves a rule up, swapping with its predecessor", () => {
  const model = { rules: [{ target: "a" }, { target: "b" }, { target: "c" }] };
  const moved = moveRule(model, 1, "up");
  assert.deepEqual(
    moved.rules.map((r) => r.target),
    ["b", "a", "c"]
  );
  // original untouched (pure).
  assert.deepEqual(
    model.rules.map((r) => r.target),
    ["a", "b", "c"]
  );
});

test("moveRule moves a rule down, swapping with its successor", () => {
  const model = { rules: [{ target: "a" }, { target: "b" }, { target: "c" }] };
  const moved = moveRule(model, 1, "down");
  assert.deepEqual(
    moved.rules.map((r) => r.target),
    ["a", "c", "b"]
  );
});

test("moveRule accepts numeric -1/1 direction as an alias for up/down", () => {
  const model = { rules: [{ target: "a" }, { target: "b" }] };
  assert.deepEqual(
    moveRule(model, 1, -1).rules.map((r) => r.target),
    ["b", "a"]
  );
  assert.deepEqual(
    moveRule(model, 0, 1).rules.map((r) => r.target),
    ["b", "a"]
  );
});

test("moveRule is a no-op at the top boundary (moving rule 0 up)", () => {
  const model = { rules: [{ target: "a" }, { target: "b" }] };
  const moved = moveRule(model, 0, "up");
  assert.deepEqual(
    moved.rules.map((r) => r.target),
    ["a", "b"]
  );
});

test("moveRule is a no-op at the bottom boundary (moving the last rule down)", () => {
  const model = { rules: [{ target: "a" }, { target: "b" }] };
  const moved = moveRule(model, 1, "down");
  assert.deepEqual(
    moved.rules.map((r) => r.target),
    ["a", "b"]
  );
});

test("seedExample returns a non-empty, serializable model", () => {
  const model = seedExample();
  assert.ok(model.dimensions.length > 0, "expected at least one dimension");
  assert.ok(model.rules.length > 0, "expected at least one rule");
  assert.ok(model.outcomes.length > 0, "expected at least one outcome");
  assert.ok(model.fallback, "expected a non-empty fallback");
  // Must round-trip through the serializer without throwing.
  assert.doesNotThrow(() => serializeLoopYaml(model));
});

test("blankModel returns an empty model", () => {
  const model = blankModel();
  assert.equal(model.dimensions.length, 0);
  assert.equal(model.rules.length, 0);
  assert.equal(model.outcomes.length, 0);
  assert.equal(model.fallback, "");
});
