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
  _serializeRulesText,
  _emittedVerbs,
  _doneStateName,
  serializeFrontmatterDimensions,
  parseFrontmatterBlock,
  encodeFrontmatterScores,
  BUILTIN_FRONTMATTER_DIMENSIONS,
  LIFECYCLE_VERBS,
  RESERVED_STATE_NAMES,
  isReservedOutcomeToken,
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

// ---------------------------------------------------------------------------
// FEAT-3474: issue_lifecycle mode
// ---------------------------------------------------------------------------

test("seedExample('issue_lifecycle') seeds the Use Case rules with a verb-only fallback", () => {
  const model = seedExample("issue_lifecycle");
  assert.equal(model.mode, "issue_lifecycle");
  assert.equal(model.fallback, "gate");
  assert.ok(BUILTIN_FRONTMATTER_DIMENSIONS.every((bd) => model.dimensions.some((d) => d.name === bd.name)));
  assert.equal(model.outcomes.length, LIFECYCLE_VERBS.length);
});

test("blankModel('issue_lifecycle') seeds fallback: gate, never the decision-table default 'done'", () => {
  const model = blankModel("issue_lifecycle");
  assert.equal(model.fallback, "gate");
  assert.deepEqual(
    model.dimensions.map((d) => d.name),
    BUILTIN_FRONTMATTER_DIMENSIONS.map((d) => d.name)
  );
  assert.equal(model.rules.length, 0);
  assert.equal(model.outcomes.length, LIFECYCLE_VERBS.length);
});

test("blankModel()/seedExample() zero-arg calls are unaffected (decision_table default preserved)", () => {
  assert.equal(blankModel().mode, "decision_table");
  assert.equal(seedExample().mode, "decision_table");
});

test("serializeLoopYaml matches golden issue-lifecycle fixture", () => {
  const model = JSON.parse(readFileSync(join(FIXT, "sample-issue-lifecycle.model.json"), "utf8"));
  const golden = readFileSync(join(FIXT, "sample-issue-lifecycle.yaml"), "utf8");
  assert.equal(serializeLoopYaml(model), golden);
});

// BUG-3489: reserved-name guard.
test("isReservedOutcomeToken rejects the decision_table runtime set", () => {
  for (const tok of ["score", "parse_scores", "policy_dispatch", "failed", "error"]) {
    assert.equal(isReservedOutcomeToken("decision_table", tok), true, tok);
  }
  assert.equal(isReservedOutcomeToken("decision_table", "done"), false);
});

test("isReservedOutcomeToken rejects the issue_lifecycle runtime set", () => {
  for (const tok of ["score", "policy_dispatch", "done", "failed", "error"]) {
    assert.equal(isReservedOutcomeToken("issue_lifecycle", tok), true, tok);
  }
});

test("isReservedOutcomeToken rejects every underscore-prefixed token in both modes", () => {
  for (const mode of ["decision_table", "issue_lifecycle"]) {
    assert.equal(isReservedOutcomeToken(mode, "_"), true);
    assert.equal(isReservedOutcomeToken(mode, "_error"), true);
    assert.equal(isReservedOutcomeToken(mode, "_custom"), true);
  }
});

test("isReservedOutcomeToken accepts an ordinary authored token", () => {
  assert.equal(isReservedOutcomeToken("decision_table", "escalate"), false);
});

test("RESERVED_STATE_NAMES exposes the runtime sets documented by BUG-3489", () => {
  assert.deepEqual(
    [...RESERVED_STATE_NAMES.decision_table].sort(),
    ["error", "failed", "parse_scores", "policy_dispatch", "score"]
  );
  assert.deepEqual(
    [...RESERVED_STATE_NAMES.issue_lifecycle].sort(),
    ["done", "error", "failed", "policy_dispatch", "score"]
  );
});

test("serializeLoopYaml(decision_table) throws naming a reserved outcome name", () => {
  const model = seedExample("decision_table");
  model.outcomes[0].name = "score";
  model.rules[0].target = "score";
  assert.throws(() => serializeLoopYaml(model), /score/);
});

test("serializeLoopYaml(decision_table) throws naming a reserved rule target", () => {
  const model = seedExample("decision_table");
  model.rules[0].target = "policy_dispatch";
  assert.throws(() => serializeLoopYaml(model), /policy_dispatch/);
});

test("serializeLoopYaml(decision_table) throws naming an underscore-prefixed fallback", () => {
  const model = seedExample("decision_table");
  model.fallback = "_custom";
  assert.throws(() => serializeLoopYaml(model), /_custom/);
});

test("serializeLoopYaml(decision_table) does not throw on ordinary authored tokens", () => {
  const model = seedExample("decision_table");
  assert.doesNotThrow(() => serializeLoopYaml(model));
});

test("serializeLoopYaml(issue_lifecycle) throws naming a reserved fallback", () => {
  const model = JSON.parse(readFileSync(join(FIXT, "sample-issue-lifecycle.model.json"), "utf8"));
  model.fallback = "done";
  assert.throws(() => serializeLoopYaml(model), /done/);
});

// BUG-3489: generated failure routing shape.
test("serializeLoopYaml(decision_table) emits a dedicated failed terminal and _error: failed", () => {
  const model = seedExample("decision_table");
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /\n {2}failed:\n {4}terminal: true\n {4}failure: true/);
  assert.match(yaml, /_error: failed/);
  assert.match(yaml, /on_max_steps: failed/);
  assert.match(yaml, /\n {2}score:\n[\s\S]*?on_error: failed/);
  assert.match(yaml, /\n {2}parse_scores:\n[\s\S]*?on_error: failed/);
  assert.match(yaml, /\n {2}policy_dispatch:\n[\s\S]*?on_error: failed/);
});

test("serializeLoopYaml(issue_lifecycle) emits dispatch on_error: failed and failure: true", () => {
  const model = JSON.parse(readFileSync(join(FIXT, "sample-issue-lifecycle.model.json"), "utf8"));
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /\n {2}policy_dispatch:\n[\s\S]*?on_error: failed/);
  assert.match(yaml, /\n {2}failed:\n {4}terminal: true\n {4}failure: true/);
});

test("_emittedVerbs is the transitive closure over rule targets, fallback, and goto targets", () => {
  const model = {
    mode: "issue_lifecycle",
    dimensions: [{ name: "status", type: "string" }],
    rules: [
      { predicates: [{ dim: "status", op: "==", value: "open" }], target: "refine", isCatchall: false },
    ],
    fallback: "refine",
    outcomes: LIFECYCLE_VERBS.map((v) => ({ ...v, transition: { ...v.transition } })),
  };
  // refine's default transition is goto -> gate; gate is not itself a rule
  // target or the fallback, so it is only reachable through the closure.
  const verbs = _emittedVerbs(model);
  assert.deepEqual(verbs, ["refine", "gate"]);

  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /\n {2}gate:\n/);
  assert.doesNotMatch(yaml, /\n {2}prepare:\n/);
  assert.doesNotMatch(yaml, /\n {2}implement:\n/);
  assert.doesNotMatch(yaml, /\n {2}verify:\n/);
});

test("a finish verb with an action emits next: done plus a bare done: terminal, never terminal: true alongside action", () => {
  const model = {
    mode: "issue_lifecycle",
    dimensions: [{ name: "status", type: "string" }],
    rules: [
      { predicates: [{ dim: "status", op: "==", value: "done" }], target: "verify", isCatchall: false },
    ],
    fallback: "verify",
    outcomes: LIFECYCLE_VERBS.map((v) => ({ ...v, transition: { ...v.transition } })),
  };
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /verify:\n {4}action_type: slash_command\n {4}action: [^\n]+\n {4}next: done\n/);
  assert.match(yaml, /\n {2}done:\n {4}terminal: true\n/);
  // No single state block (blank-line-separated in the serializer's output)
  // pairs `action:` with `terminal: true`.
  const blocks = yaml.split(/\n\n+/);
  for (const block of blocks) {
    if (block.includes("    action:") && block.includes("    terminal: true")) {
      assert.fail(`state block pairs action: with terminal: true:\n${block}`);
    }
  }
});

test("seeded implement verb emits action_type: shell / action: ll-auto --only ${context.issue_id:shell}", () => {
  const model = seedExample("issue_lifecycle");
  const yaml = serializeLoopYaml(model);
  assert.match(
    yaml,
    /implement:\n {4}action_type: shell\n {4}action: ll-auto --only \$\{context\.issue_id:shell\}\n {4}next: done\n/
  );
});

test("seeded refine verb emits action: /ll:refine-issue ${context.issue_id} --auto with next: gate", () => {
  const model = seedExample("issue_lifecycle");
  const yaml = serializeLoopYaml(model);
  assert.match(
    yaml,
    /refine:\n {4}action_type: slash_command\n {4}action: \/ll:refine-issue \$\{context\.issue_id\} --auto\n {4}next: gate\n/
  );
});

test("_doneStateName avoids collision with a decision-table outcome literally named 'done'", () => {
  const model = {
    mode: "decision_table",
    rules: [{ predicates: [], target: "done", isCatchall: true }],
    outcomes: [{ name: "done", actionType: "prompt", body: "Ship it.", transition: { kind: "finish" } }],
    fallback: "done",
  };
  assert.equal(_doneStateName(model), "finished");

  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /\n {2}done:\n {4}action_type: prompt\n {4}action: \|\n {6}Ship it\.\n {4}next: finished\n/);
  assert.match(yaml, /\n {2}finished:\n {4}terminal: true\n/);
  // Never a self-loop, and no duplicate `done:` key.
  assert.equal((yaml.match(/^ {2}done:$/gm) || []).length, 1);
});

test("_doneStateName returns 'done' when no outcome/rule-target/fallback uses that name", () => {
  const model = {
    rules: [{ predicates: [], target: "ship", isCatchall: true }],
    outcomes: [{ name: "ship" }],
    fallback: "ship",
  };
  assert.equal(_doneStateName(model), "done");
});

test("serializeFrontmatterDimensions emits raw (non-normalized) name:type pairs", () => {
  const model = { dimensions: [{ name: "Review Status", type: "string" }, { name: "confidence_score", type: "numeric" }] };
  assert.equal(serializeFrontmatterDimensions(model), "Review Status:string|confidence_score:numeric");
});

test("Try-it evaluates compiled rules: decision_needed:==false does not fire against pasted decision_needed: true", () => {
  const model = {
    mode: "issue_lifecycle",
    dimensions: [{ name: "decision_needed", type: "boolean" }],
    rules: [
      { predicates: [{ dim: "decision_needed", op: "==false", value: "" }], target: "on", isCatchall: false },
    ],
    fallback: "off",
  };
  const fm = parseFrontmatterBlock("decision_needed: true");
  const scores = encodeFrontmatterScores(fm, model.dimensions);
  assert.deepEqual(scores, { "decision_needed": "100" });

  // The pre-existing decision-table Try-it bug (evaluating raw model.rules,
  // whose "==false" token evalPredicate treats as "!="): fires incorrectly.
  const rawWinner = evaluateRules(model.rules, scores);
  assert.equal(rawWinner, "on");

  // The fix: evaluate the *compiled* rule text instead.
  const compiled = parseRuleTable(_serializeRulesText(model));
  const compiledWinner = evaluateRules(compiled, scores);
  assert.equal(compiledWinner, "off");
});

test("parseFrontmatterBlock / encodeFrontmatterScores agree with the shared encoding corpus", () => {
  const corpus = JSON.parse(
    readFileSync(join(FIXT, "frontmatter_encoding_corpus.json"), "utf8")
  );
  for (const c of corpus.cases) {
    const fm = parseFrontmatterBlock(c.frontmatter_text);
    const got = encodeFrontmatterScores(fm, c.dims);
    assert.deepEqual(got, c.expected_scores, `${c.name}: got ${JSON.stringify(got)}`);
  }
});

test("parseFrontmatterBlock throws a 'Can't read line N' error on an unparseable line", () => {
  assert.throws(() => parseFrontmatterBlock("status open\n"), /Can't read line 1: status open/);
});

test("parseFrontmatterBlock tolerates --- fence lines", () => {
  const fm = parseFrontmatterBlock("---\nstatus: open\n---\n");
  assert.equal(fm.status, "open");
});
