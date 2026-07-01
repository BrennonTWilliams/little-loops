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
