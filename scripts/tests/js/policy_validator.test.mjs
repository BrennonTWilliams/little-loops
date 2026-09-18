// FEAT-2301 node:test — exercises the JS policy core against the shared
// conformance corpus (same JSON the Python tests pin) and the golden YAML.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

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
  validateBuilderModel,
  evaluateModel,
  reconcilePredicateForDim,
  opsForType,
  BUILDER_PROJECT_SCHEMA_VERSION,
  validateProjectStructure,
  serializeBuilderProject,
  parseBuilderProject,
  applyDraftEdit,
  taskPresets,
  summarizeTransitions,
  LIFECYCLE_DESTINATIONS,
  _dispatchedDestinations,
  _requiredTerminalBlocks,
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

test("serializeLoopYaml matches golden issue-lifecycle-destinations fixture (ENH-3492)", () => {
  const model = JSON.parse(
    readFileSync(join(FIXT, "sample-issue-lifecycle-destinations.model.json"), "utf8")
  );
  const golden = readFileSync(join(FIXT, "sample-issue-lifecycle-destinations.yaml"), "utf8");
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

test("RESERVED_STATE_NAMES exposes the runtime sets documented by BUG-3489/BUG-3486/ENH-3492", () => {
  assert.deepEqual(
    [...RESERVED_STATE_NAMES.decision_table].sort(),
    ["error", "failed", "finished", "needs_attention", "parse_scores", "policy_dispatch", "score"]
  );
  assert.deepEqual(
    [...RESERVED_STATE_NAMES.issue_lifecycle].sort(),
    [
      "done",
      "error",
      "failed",
      "issue_id",
      "needs_attention",
      "policy_dispatch",
      "score",
      "skipped",
      "stopped",
    ]
  );
  assert.deepEqual(
    [...RESERVED_STATE_NAMES.rubric].sort(),
    ["done", "needs_attention", "parse_scores", "route_high", "route_medium", "score"]
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
  assert.match(yaml, /on_max_steps: needs_attention/);
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

// ---------------------------------------------------------------------------
// BUG-3486: parseRuleTable/parsePredicate parity, parseFrontmatterBlock's
// comment/quoted-comma/reject-unsupported handling, validateBuilderModel,
// evaluateModel, reconcilePredicateForDim, opsForType.
// ---------------------------------------------------------------------------

test("parseRuleTable rejects a non-numeric value on an ordered operator (parity with policy_rules.py)", () => {
  assert.throws(() => parseRuleTable("confidence_score:>=high -> implement"), /numeric/);
});

test("parseRuleTable rejects a malformed target name (parity with policy_rules.py)", () => {
  assert.throws(() => parseRuleTable("quality:>=90 -> bad/target"), /invalid target/);
});

test("conformance_corpus parse_error_cases raise the documented substring", () => {
  for (const c of corpus.parse_error_cases) {
    assert.throws(
      () => parseRuleTable(c.rules),
      (err) => err.message.includes(c.expected_error_substring),
      c.name
    );
  }
});

test("parseFrontmatterBlock strips a # comment at line-start or after whitespace, outside quotes", () => {
  const fm = parseFrontmatterBlock("confidence_score: 40 # not yet verified\ntitle: 'uses a # inside quotes'");
  assert.equal(fm.confidence_score, "40");
  assert.equal(fm.title, "uses a # inside quotes");
});

test("parseFrontmatterBlock keeps a quoted comma inside one flow-list element", () => {
  const fm = parseFrontmatterBlock('blocked_by: [BUG-1, "BUG-2, see note"]');
  assert.deepEqual(fm.blocked_by, ["BUG-1", "BUG-2, see note"]);
});

test("parseFrontmatterBlock rejects a nested mapping", () => {
  assert.throws(() => parseFrontmatterBlock("meta:\n  nested: value"), /Can't read line 2/);
});

test("parseFrontmatterBlock rejects a YAML anchor", () => {
  assert.throws(() => parseFrontmatterBlock("status: &anchor open"), /Can't read line 1/);
});

test("parseFrontmatterBlock rejects a multi-line block-scalar continuation", () => {
  assert.throws(() => parseFrontmatterBlock("description: |\n  line one\n  line two"), /Can't read line 2/);
});

test("frontmatter_encoding_corpus js_reject_cases raise the documented substring", () => {
  const fmCorpus = JSON.parse(readFileSync(join(FIXT, "frontmatter_encoding_corpus.json"), "utf8"));
  for (const c of fmCorpus.js_reject_cases) {
    assert.throws(
      () => parseFrontmatterBlock(c.frontmatter_text),
      (err) => err.message.includes(c.expected_error_substring),
      c.name
    );
  }
});

test("encodeFrontmatterScores derives priority_rank from raw_key === 'priority_rank', not a dim named 'priority'", () => {
  // No "priority" dimension declared at all — priority_rank still derives
  // from the literal frontmatter "priority" key (parity with
  // frontmatter_scores.py's encode_frontmatter_scores).
  const fm = parseFrontmatterBlock("priority: P3");
  const scores = encodeFrontmatterScores(fm, [{ name: "priority_rank", type: "numeric" }]);
  assert.deepEqual(scores, { priority_rank: "3" });
});

test("opsForType returns the legal operator set per dimension type, default first", () => {
  assert.deepEqual(opsForType("boolean"), ["==true", "==false"]);
  assert.deepEqual(opsForType("string"), ["==", "!="]);
  assert.deepEqual(opsForType("numeric"), ["==", "!=", ">=", "<=", "<", ">"]);
  assert.deepEqual(opsForType("list"), ["==", "!=", ">=", "<=", "<", ">"]);
});

test("reconcilePredicateForDim preserves a still-legal op/value unchanged", () => {
  const pred = { dim: "quality", op: ">=", value: "50" };
  assert.deepEqual(reconcilePredicateForDim(pred, "numeric"), pred);
});

test("reconcilePredicateForDim resets op/value/draft when the op is illegal for the new type", () => {
  const pred = { dim: "quality", op: ">=", value: "50", draft: { text: "5", error: "" } };
  const reconciled = reconcilePredicateForDim(pred, "boolean");
  assert.equal(reconciled.op, "==true");
  assert.equal(reconciled.value, "");
  assert.equal(reconciled.draft, null);
});

test("evaluateModel returns the winning rule's index for a repeated target (identity, not name lookup)", () => {
  const model = seedExample("decision_table");
  model.rules.push({
    predicates: [{ dim: "quality", op: "<", value: "50" }],
    target: "done",
    isCatchall: false,
  });
  const result = evaluateModel(model, { quality: 10, "has-citations": 0 });
  assert.equal(result.ruleIndex, 2);
  assert.equal(result.target, "done");
  assert.equal(result.isFallback, false);
});

test("evaluateModel marks a derived-fallback match with isFallback and no authored ruleIndex", () => {
  const model = seedExample("decision_table");
  const result = evaluateModel(model, { quality: 0, "has-citations": 0 });
  assert.equal(result.target, "deep-repair");
  assert.equal(result.isFallback, true);
  assert.equal(result.ruleIndex, -1);
});

test("evaluateModel evaluates compiled boolean predicates, not raw ==true/==false tokens", () => {
  const model = {
    mode: "decision_table",
    dimensions: [{ name: "flag", type: "boolean" }],
    rules: [{ predicates: [{ dim: "flag", op: "==false", value: "" }], target: "on", isCatchall: false }],
    fallback: "off",
    outcomes: [{ name: "on" }, { name: "off" }],
  };
  // flag scored 100 (true) must NOT match ==false once compiled.
  const result = evaluateModel(model, { flag: 100 });
  assert.equal(result.target, "off");
  assert.equal(result.isFallback, true);
});

test("evaluateModel returns a no-winner result (not a throw) for an incomplete/malformed rule table", () => {
  const model = {
    mode: "decision_table",
    dimensions: [{ name: "quality", type: "numeric" }],
    rules: [{ predicates: [{ dim: "quality", op: ">=", value: "" }], target: "x", isCatchall: false }],
    fallback: "y",
    outcomes: [{ name: "x" }, { name: "y" }],
  };
  assert.doesNotThrow(() => evaluateModel(model, { quality: 10 }));
  const result = evaluateModel(model, { quality: 10 });
  assert.equal(result.target, null);
});

test("validateBuilderModel reports zero error diagnostics for every seeded and blank model", () => {
  for (const mode of ["decision_table", "rubric", "issue_lifecycle"]) {
    for (const model of [seedExample(mode), blankModel(mode)]) {
      const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
      assert.deepEqual(errors, [], `${mode}: ${JSON.stringify(errors)}`);
    }
  }
});

test("validateBuilderModel reports zero error diagnostics for the three golden fixtures", () => {
  for (const fixture of [
    "sample-decision-table.model.json",
    "sample-rubric.model.json",
    "sample-issue-lifecycle.model.json",
  ]) {
    const model = JSON.parse(readFileSync(join(FIXT, fixture), "utf8"));
    const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
    assert.deepEqual(errors, [], `${fixture}: ${JSON.stringify(errors)}`);
  }
});

test("validateBuilderModel flags a reserved outcome/rule-target/fallback as an error (non-throwing)", () => {
  const model = seedExample("decision_table");
  model.outcomes[0].name = "score";
  model.rules[0].target = "score";
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /reserved/.test(d.message) && /score/.test(d.message)));
});

test("validateBuilderModel flags a dimension normalizing to the reserved 'aggregate' name", () => {
  const model = seedExample("rubric");
  model.dimensions.push({ name: "Aggregate", type: "numeric" });
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /aggregate/.test(d.message)));
});

test("validateBuilderModel flags a duplicate outcome name", () => {
  const model = seedExample("decision_table");
  model.outcomes.push({ ...model.outcomes[0] });
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /defined more than once/.test(d.message)));
});

test("validateBuilderModel flags a rule target, fallback, and goto target that reference an undefined outcome", () => {
  const model = seedExample("decision_table");
  model.rules[0].target = "nope";
  model.fallback = "also-nope";
  model.outcomes[1].transition = { kind: "goto", target: "still-nope" };
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => d.message.includes('"nope"')));
  assert.ok(errors.some((d) => d.message.includes('"also-nope"')));
  assert.ok(errors.some((d) => d.message.includes('"still-nope"')));
});

test("validateBuilderModel flags an incomplete prompt/slash_command action", () => {
  const model = seedExample("decision_table");
  model.outcomes[1].body = "";
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /has no prompt text/.test(d.message)));
});

test("validateBuilderModel flags an incomplete shell action (ENH-3491)", () => {
  const model = seedExample("issue_lifecycle");
  const verify = model.outcomes.find((o) => o.name === "verify");
  verify.actionType = "shell";
  verify.body = "";
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /"verify" has no command/.test(d.message)));
});

test("validateBuilderModel flags a non-positive or non-integer step budget", () => {
  const model = seedExample("decision_table");
  for (const bad of [0, -5, 1.5, NaN]) {
    model.maxSteps = bad;
    const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
    assert.ok(
      errors.some((d) => d.field === "maxSteps"),
      `expected a maxSteps error for ${bad}`
    );
  }
});

test("validateBuilderModel flags inverted rubric thresholds", () => {
  const model = seedExample("rubric");
  model.thresholdHigh = 50;
  model.thresholdMedium = 65;
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /threshold/.test(d.message)));
});

test("validateBuilderModel flags a predicate with a non-null draft", () => {
  const model = seedExample("decision_table");
  model.rules[0].predicates[0].draft = { text: "9", error: "bad" };
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /unsaved edit/.test(d.message)));
});

test("validateBuilderModel warns (not errors) on a rubric outcome other than light_repair/deep_repair", () => {
  const model = seedExample("rubric");
  model.outcomes.push({ name: "unexpected", actionType: "none", transition: { kind: "finish" } });
  const diagnostics = validateBuilderModel(model);
  assert.ok(diagnostics.some((d) => d.severity === "warning" && /rubric mode ignores it/.test(d.message)));
  assert.ok(!diagnostics.some((d) => d.severity === "error"));
});

test("validateBuilderModel absorbs detectShadows as warning diagnostics", () => {
  const model = seedExample("decision_table");
  model.rules.unshift({ predicates: [], target: model.rules[0].target, isCatchall: true });
  const diagnostics = validateBuilderModel(model);
  assert.ok(diagnostics.some((d) => d.severity === "warning" && /never fires/.test(d.message)));
});

// ===========================================================================
// ENH-3487: draft/project persistence and undo/redo
// ===========================================================================

function _projectFor(model) {
  return {
    schemaVersion: BUILDER_PROJECT_SCHEMA_VERSION,
    generatorVersion: "0.0.0-test",
    projectId: "test-project-id",
    activeMode: model.mode,
    drafts: { [model.mode]: { model } },
  };
}

test("serializeBuilderProject/parseBuilderProject round-trip a golden .project.json fixture byte-equal, for every supported mode", () => {
  for (const fixture of [
    "sample-decision-table.project.json",
    "sample-rubric.project.json",
    "sample-issue-lifecycle.project.json",
  ]) {
    const text = readFileSync(join(FIXT, fixture), "utf8");
    const project = parseBuilderProject(text);
    assert.equal(serializeBuilderProject(project), text, fixture);
  }
});

test("parseBuilderProject accepts a structurally valid draft with unfinished predicates, empty action bodies, missing references, and an invalid step budget", () => {
  const model = seedExample("decision_table");
  model.rules[0].predicates[0].draft = { text: "9", error: "bad" };
  model.outcomes[0].body = "";
  model.rules[0].target = "does-not-exist";
  model.maxSteps = -5;
  // Sanity: this really is semantically broken (validateBuilderModel's job).
  assert.ok(validateBuilderModel(model).some((d) => d.severity === "error"));
  const project = _projectFor(model);
  const text = serializeBuilderProject(project);
  const parsed = parseBuilderProject(text);
  assert.deepEqual(parsed, project);
});

test("validateProjectStructure and parseBuilderProject reject malformed project shapes", () => {
  const good = _projectFor(seedExample("decision_table"));
  const cases = [
    ["not JSON", "{not valid json", /parse/],
    ["JSON array, not an object", "[]", /object/],
    ["missing schemaVersion", JSON.stringify({ ...good, schemaVersion: undefined }), /schemaVersion/],
    [
      "newer schemaVersion",
      JSON.stringify({ ...good, schemaVersion: BUILDER_PROJECT_SCHEMA_VERSION + 1 }),
      /newer/,
    ],
    ["drafts not an object", JSON.stringify({ ...good, drafts: "nope" }), /drafts/],
    ["unknown activeMode", JSON.stringify({ ...good, activeMode: "bogus_mode" }), /activeMode/],
    [
      "draft missing model key",
      JSON.stringify({ ...good, drafts: { decision_table: {} } }),
      /model/,
    ],
    [
      "mismatched draft-key/model.mode",
      JSON.stringify({
        ...good,
        drafts: { decision_table: { model: { ...seedExample("decision_table"), mode: "rubric" } } },
      }),
      /does not match/,
    ],
    [
      "non-array dimensions/rules/outcomes",
      JSON.stringify({
        ...good,
        drafts: { decision_table: { model: { ...seedExample("decision_table"), rules: "nope" } } },
      }),
      /arrays/,
    ],
    [
      "missing projectId",
      JSON.stringify({ ...good, projectId: "" }),
      /projectId/,
    ],
    [
      "no draft for activeMode",
      JSON.stringify({ ...good, activeMode: "rubric" }),
      /no draft exists/,
    ],
  ];
  for (const [label, text, pattern] of cases) {
    assert.throws(() => parseBuilderProject(text), pattern, `parseBuilderProject: ${label}`);
  }
  // validateProjectStructure mirrors the same rejections without throwing.
  assert.deepEqual(validateProjectStructure(good), []);
  assert.ok(validateProjectStructure({ ...good, activeMode: "bogus_mode" }).length > 0);
  assert.ok(validateProjectStructure(null).length > 0);
  assert.ok(validateProjectStructure([]).length > 0);
});

test("parseBuilderProject preserves unknown JSON-compatible draft metadata (forward compatibility)", () => {
  const model = seedExample("rubric");
  const project = _projectFor(model);
  project.drafts.rubric.scenarios = [{ name: "case-1" }]; // FEAT-3488-shaped sibling key
  const text = serializeBuilderProject(project);
  const parsed = parseBuilderProject(text);
  assert.deepEqual(parsed.drafts.rubric.scenarios, [{ name: "case-1" }]);
});

test("applyDraftEdit commit pushes the current present onto past and clears future", () => {
  const snapA = { activeMode: "decision_table", drafts: { decision_table: { model: seedExample("decision_table") } } };
  const history0 = { past: [], present: snapA, future: [{ activeMode: "rubric", drafts: {} }] };
  const modelB = seedExample("decision_table");
  modelB.name = "renamed-loop";
  const history1 = applyDraftEdit(history0, {
    type: "commit",
    activeMode: "decision_table",
    drafts: { decision_table: { model: modelB } },
  });
  assert.equal(history1.past.length, 1);
  assert.deepEqual(history1.past[0], snapA);
  assert.equal(history1.present.drafts.decision_table.model.name, "renamed-loop");
  assert.deepEqual(history1.future, []);
});

test("applyDraftEdit undo/redo restores rules, fields, actions, transitions, and activeMode across a mode switch", () => {
  let history = null;
  const push = (activeMode, drafts) => {
    history = applyDraftEdit(history, { type: "commit", activeMode, drafts });
  };

  // 1. Seed decision_table.
  const m1 = seedExample("decision_table");
  push("decision_table", { decision_table: { model: m1 } });

  // 2. Field edit.
  const m2 = JSON.parse(JSON.stringify(m1));
  m2.name = "edited-name";
  push("decision_table", { decision_table: { model: m2 } });

  // 3. Rule-target edit (routing) + action edit (outcome body).
  const m3 = JSON.parse(JSON.stringify(m2));
  m3.rules[0].target = m3.outcomes[1].name;
  m3.outcomes[1].body = "a different action body";
  push("decision_table", { decision_table: { model: m3 } });

  // 4. Transition edit.
  const m4 = JSON.parse(JSON.stringify(m3));
  m4.outcomes[1].transition = { kind: "finish" };
  push("decision_table", { decision_table: { model: m4 } });

  // 5. Mode switch to rubric — a history entry in its own right.
  const rubricModel = seedExample("rubric");
  push("rubric", { decision_table: { model: m4 }, rubric: { model: rubricModel } });

  assert.equal(history.present.activeMode, "rubric");
  assert.equal(history.past.length, 4);

  // Undo the mode switch: back to decision_table with m4's transition edit.
  history = applyDraftEdit(history, { type: "undo" });
  assert.equal(history.present.activeMode, "decision_table");
  assert.deepEqual(history.present.drafts.decision_table.model.outcomes[1].transition, { kind: "finish" });

  // Undo the transition edit: m3's action/rule-target edit.
  history = applyDraftEdit(history, { type: "undo" });
  assert.equal(history.present.drafts.decision_table.model.outcomes[1].body, "a different action body");
  assert.equal(history.present.drafts.decision_table.model.rules[0].target, m3.outcomes[1].name);

  // Undo the action/rule-target edit: m2's field edit.
  history = applyDraftEdit(history, { type: "undo" });
  assert.equal(history.present.drafts.decision_table.model.name, "edited-name");
  assert.equal(history.present.drafts.decision_table.model.outcomes[1].body, m1.outcomes[1].body);

  // Undo the field edit: back to the initial seed.
  history = applyDraftEdit(history, { type: "undo" });
  assert.equal(history.present.drafts.decision_table.model.name, m1.name);
  assert.equal(history.past.length, 0);

  // Undo at the boundary is a no-op.
  const atStart = applyDraftEdit(history, { type: "undo" });
  assert.deepEqual(atStart, history);

  // Redo all the way back to the mode switch.
  history = applyDraftEdit(history, { type: "redo" });
  history = applyDraftEdit(history, { type: "redo" });
  history = applyDraftEdit(history, { type: "redo" });
  history = applyDraftEdit(history, { type: "redo" });
  assert.equal(history.present.activeMode, "rubric");
  assert.deepEqual(history.present.drafts.rubric.model, rubricModel);
  assert.equal(history.future.length, 0);

  // Redo at the boundary is a no-op.
  const atEnd = applyDraftEdit(history, { type: "redo" });
  assert.deepEqual(atEnd, history);
});

test("applyDraftEdit caps past at 100 entries, dropping the oldest first", () => {
  let history = applyDraftEdit(null, {
    type: "commit",
    activeMode: "decision_table",
    drafts: { decision_table: { model: { ...seedExample("decision_table"), name: "seed" } } },
  });
  for (let i = 0; i < 150; i++) {
    history = applyDraftEdit(history, {
      type: "commit",
      activeMode: "decision_table",
      drafts: { decision_table: { model: { ...seedExample("decision_table"), name: `edit-${i}` } } },
    });
  }
  assert.equal(history.past.length, 100);
  // The oldest surviving entry is edit-49 (seed + edit-0..48 = 50 entries dropped).
  assert.equal(history.past[0].drafts.decision_table.model.name, "edit-49");
  assert.equal(history.present.drafts.decision_table.model.name, "edit-149");
});

test("applyDraftEdit deep-copies snapshots so later mutation of the caller's live object cannot alter history", () => {
  const originalName = seedExample("decision_table").name;
  const model = seedExample("decision_table");
  let history = applyDraftEdit(null, {
    type: "commit",
    activeMode: "decision_table",
    drafts: { decision_table: { model } },
  });
  const editedModel = JSON.parse(JSON.stringify(model));
  editedModel.name = "second";
  history = applyDraftEdit(history, {
    type: "commit",
    activeMode: "decision_table",
    drafts: { decision_table: { model: editedModel } },
  });
  // Mutate the object that was pushed into `past` via the live reference.
  model.name = "mutated-after-the-fact";
  assert.equal(history.past[0].drafts.decision_table.model.name, originalName);
});

// ===========================================================================
// Task presets + transition summary (ENH-3491)
// ===========================================================================

test("taskPresets returns the five documented presets with correct modes", () => {
  const presets = taskPresets();
  const byId = Object.fromEntries(presets.map((p) => [p.id, p]));
  assert.equal(byId["document-improvement"].mode, "rubric");
  assert.equal(byId["condition-based-routing"].mode, "decision_table");
  assert.equal(byId["preparation"].mode, "issue_lifecycle");
  assert.equal(byId["implementation"].mode, "issue_lifecycle");
  assert.equal(byId["implementation-with-verification"].mode, "issue_lifecycle");
  assert.equal(presets.length, 5);
});

test("taskPresets().build() returns a fresh model every call (no shared references)", () => {
  const preset = taskPresets().find((p) => p.id === "preparation");
  const a = preset.build();
  const b = preset.build();
  a.outcomes[0].body = "mutated";
  assert.notEqual(b.outcomes[0].body, "mutated");
});

test("every preset except unconfigured implementation-with-verification validates cleanly", () => {
  for (const preset of taskPresets()) {
    if (preset.id === "implementation-with-verification") continue;
    const model = preset.build();
    const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
    assert.deepEqual(errors, [], `preset ${preset.id} should have no error diagnostics`);
    assert.doesNotThrow(() => serializeLoopYaml(model), `preset ${preset.id} should serialize`);
  }
});

test("implementation-with-verification preset is unconfigured until a command is set", () => {
  const preset = taskPresets().find((p) => p.id === "implementation-with-verification");
  const model = preset.build();
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /"verify" has no command/.test(d.message)));
  assert.equal(summarizeTransitions(model).verification, "unconfigured");

  model.outcomes.find((o) => o.name === "verify").body = "scripts/check-acceptance.sh";
  assert.deepEqual(validateBuilderModel(model).filter((d) => d.severity === "error"), []);
  assert.equal(summarizeTransitions(model).verification, "acceptance");
});

test("implementation-with-verification preset's emitted verify state carries on_error: failed", () => {
  const preset = taskPresets().find((p) => p.id === "implementation-with-verification");
  const model = preset.build();
  model.outcomes.find((o) => o.name === "verify").body = "scripts/check-acceptance.sh";
  const yaml = serializeLoopYaml(model);
  const verifyBlock = yaml.slice(yaml.indexOf("\n  verify:"));
  assert.match(verifyBlock.split(/\n\n/)[0], /on_error: failed/);
});

test("summarizeTransitions: editing body/args preserves the contract; changing actionType off shell clears it", () => {
  const preset = taskPresets().find((p) => p.id === "implementation-with-verification");
  const model = preset.build();
  const verify = model.outcomes.find((o) => o.name === "verify");
  verify.body = "scripts/check-acceptance.sh";
  verify.args = "--strict";
  assert.equal(summarizeTransitions(model).verification, "acceptance");

  verify.actionType = "slash_command";
  verify.body = "/ll:verify-issues";
  delete verify.verificationContract;
  assert.equal(summarizeTransitions(model).verification, "issue_validation");
});

test("summarizeTransitions never reports acceptance verification for an unreachable verify state", () => {
  const model = taskPresets()
    .find((p) => p.id === "implementation")
    .build();
  // "implementation" preset never routes to verify — even if verify itself
  // were configured as a shell acceptance check, it is unreachable.
  const verify = model.outcomes.find((o) => o.name === "verify");
  verify.actionType = "shell";
  verify.body = "scripts/check-acceptance.sh";
  verify.verificationContract = "acceptance_exit_code";
  assert.equal(summarizeTransitions(model).verification, "none");
  assert.ok(!summarizeTransitions(model).steps.includes("verify"));
});

test("summarizeTransitions computes stepsPerAttempt/attempts from the reachable goto chain", () => {
  const model = taskPresets()
    .find((p) => p.id === "implementation-with-verification")
    .build();
  model.outcomes.find((o) => o.name === "verify").body = "scripts/check-acceptance.sh";
  model.maxSteps = 20;
  // fallback "prepare" -> refine -> gate -> implement -> verify: chain of 5 verbs.
  const summary = summarizeTransitions(model);
  assert.equal(summary.stepsPerAttempt, 7);
  assert.equal(summary.attempts, Math.floor(20 / 7));
  assert.match(summary.maxStepsNote, /max steps 20/);
});

test("summarizeTransitions marks implement as stopping when its transition is finish", () => {
  const model = taskPresets()
    .find((p) => p.id === "implementation")
    .build();
  assert.equal(summarizeTransitions(model).stopsAfterImplement, true);
});

test("summarizeTransitions handles a goto cycle without infinite recursion", () => {
  const model = blankModel("issue_lifecycle");
  model.rules = [{ predicates: [], target: "refine", isCatchall: true }];
  model.fallback = "refine";
  const refine = model.outcomes.find((o) => o.name === "refine");
  const gate = model.outcomes.find((o) => o.name === "gate");
  refine.transition = { kind: "goto", target: "gate" };
  gate.transition = { kind: "goto", target: "refine" }; // cycle
  assert.doesNotThrow(() => summarizeTransitions(model));
  const summary = summarizeTransitions(model);
  assert.ok(summary.stepsPerAttempt > 0);
});

test("summarizeTransitions reflects only the branch reachable from rules/fallback", () => {
  const model = seedExample("issue_lifecycle");
  // Seeded rules route to verify/implement/refine with fallback "gate" — "prepare"
  // is not targeted by any rule or the fallback, so it is not reachable.
  const summary = summarizeTransitions(model);
  assert.ok(!summary.steps.includes("prepare"));
  assert.ok(summary.steps.includes("verify"));
  assert.ok(summary.steps.includes("implement"));
});

// ===========================================================================
// ENH-3492: explicit terminal destinations, scoring instructions/anchors,
// gate stamping (transition summary + serializer/validator pieces).
// ===========================================================================

function _lifecycleModel({ rules, fallback, outcomeOverrides = {} } = {}) {
  const model = blankModel("issue_lifecycle");
  model.rules = rules || [{ predicates: [], target: "prepare", isCatchall: true }];
  model.fallback = fallback || "prepare";
  for (const [name, patch] of Object.entries(outcomeOverrides)) {
    const oc = model.outcomes.find((o) => o.name === name);
    Object.assign(oc, patch);
  }
  return model;
}

test("LIFECYCLE_DESTINATIONS declares stopped/skipped as non-failure and needs_attention as failure", () => {
  const byName = Object.fromEntries(LIFECYCLE_DESTINATIONS.map((d) => [d.name, d]));
  assert.equal(byName.stopped.failure, false);
  assert.equal(byName.skipped.failure, false);
  assert.equal(byName.needs_attention.failure, true);
});

test("a rule may target a destination directly: dispatch route + terminal block emitted, failure flag correct", () => {
  const model = _lifecycleModel({
    rules: [{ predicates: [], target: "skipped", isCatchall: true }],
    fallback: "skipped",
  });
  assert.deepEqual(_dispatchedDestinations(model), ["skipped"]);
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /\n {6}skipped: skipped\n/);
  assert.match(yaml, /\n {2}skipped:\n {4}terminal: true\n\n/);
  assert.doesNotMatch(yaml, /\n {2}skipped:\n {4}terminal: true\n {4}failure: true/);
});

test("a verb's transition.kind may route straight to stopped/skipped/needs_attention", () => {
  const model = _lifecycleModel({
    outcomeOverrides: { prepare: { transition: { kind: "stop" } } },
  });
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /prepare:\n {4}action_type: slash_command\n {4}action: [^\n]+\n {4}next: stopped\n/);
  assert.match(yaml, /\n {2}stopped:\n {4}terminal: true\n\n/);
});

test("on_max_steps alone never adds a needs_attention dispatch route (AC 2)", () => {
  const model = seedExample("issue_lifecycle");
  // No authored reference to needs_attention anywhere in the seeded model.
  assert.deepEqual(_dispatchedDestinations(model), []);
  assert.deepEqual(_requiredTerminalBlocks(model), ["needs_attention"]);
  const yaml = serializeLoopYaml(model);
  assert.doesNotMatch(yaml, /\n {6}needs_attention: needs_attention\n/);
  assert.match(yaml, /\n {2}needs_attention:\n {4}terminal: true\n {4}failure: true\n\n/);
  assert.match(yaml, /on_max_steps: needs_attention/);
});

test("rubric and decision_table reject stop/skip/attention transition kinds, both diagnostically and at emission", () => {
  for (const mode of ["rubric", "decision_table"]) {
    const model = seedExample(mode);
    if (mode === "rubric") {
      model.outcomes.push({
        name: "light_repair",
        actionType: "prompt",
        body: "x",
        transition: { kind: "stop" },
      });
    } else {
      model.outcomes[0].transition = { kind: "stop" };
    }
    const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
    assert.ok(
      errors.some((d) => /only available in issue_lifecycle mode/.test(d.message)),
      `${mode}: ${JSON.stringify(errors)}`
    );
    assert.throws(() => serializeLoopYaml(model), /reserved for issue_lifecycle mode/);
  }
});

test("an actionless lifecycle outcome combined with stop/skip/attention is rejected by validateBuilderModel", () => {
  const model = _lifecycleModel({
    outcomeOverrides: { prepare: { actionType: "none", body: "", transition: { kind: "skip" } } },
  });
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /combines no action with "skip"/.test(d.message)));
});

test("the serializer still emits next: <destination> (never bare terminal: true) for an actionless stop/skip/attention outcome", () => {
  const model = _lifecycleModel({
    outcomeOverrides: { prepare: { actionType: "none", body: "", transition: { kind: "skip" } } },
  });
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /prepare:\n {4}next: skipped\n/);
  assert.doesNotMatch(yaml, /prepare:\n {4}terminal: true\n/);
});

test("_serializeRubric now guards reserved outcome names (parity with the other two serializers)", () => {
  const model = seedExample("rubric");
  model.outcomes = [{ name: "score", actionType: "prompt", body: "x", transition: { kind: "rescore" } }];
  assert.throws(() => serializeLoopYaml(model), /score/);
});

test("validateBuilderModel flags dimension anchors: out-of-range score, duplicate score, empty meaning, non-0/100 boolean anchor", () => {
  const model = seedExample("rubric");
  model.dimensions[0].anchors = [
    { score: 150, meaning: "too high" },
    { score: 10, meaning: "" },
    { score: 10, meaning: "duplicate" },
  ];
  model.dimensions[1].type = "boolean";
  model.dimensions[1].anchors = [{ score: 50, meaning: "not 0 or 100" }];
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /outside 0-100/.test(d.message)));
  assert.ok(errors.some((d) => /no meaning/.test(d.message)));
  assert.ok(errors.some((d) => /duplicate anchor score/.test(d.message)));
  assert.ok(errors.some((d) => /boolean; anchors must be 0 or 100/.test(d.message)));
});

test("valid anchors and instructions pass validateBuilderModel cleanly", () => {
  const model = seedExample("rubric");
  model.dimensions[0].instructions = "Weigh recency heavily.";
  model.dimensions[0].anchors = [
    { score: 0, meaning: "absent" },
    { score: 100, meaning: "exemplary" },
  ];
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.deepEqual(errors, []);
});

test("absent dimension metadata leaves the scoring prompt byte-for-byte unchanged", () => {
  const before = serializeLoopYaml(seedExample("rubric"));
  const model = seedExample("rubric");
  // Explicitly absent (undefined) instructions/anchors on every dimension.
  const after = serializeLoopYaml(model);
  assert.equal(after, before);
});

test("dimension instructions and anchor meanings are emitted as literal text in the grading prompt", () => {
  const model = seedExample("rubric");
  model.dimensions[0].instructions = "Focus on structure over prose style.";
  model.dimensions[0].anchors = [
    { score: 0, meaning: "no structure" },
    { score: 100, meaning: "excellent structure" },
  ];
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /Focus on structure over prose style\./);
  assert.match(yaml, /0=no structure, 100=excellent structure/);
});

test("a literal ${...} in scoring instructions/anchor meanings is escaped to $${...} so FSM interpolation never sees it", () => {
  const model = seedExample("rubric");
  model.dimensions[0].instructions = "Reward mentions of ${customer.name} verbatim.";
  model.dimensions[0].anchors = [{ score: 100, meaning: "cites ${customer.name}" }];
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /Reward mentions of \$\$\{customer\.name\} verbatim\./);
  assert.match(yaml, /100=cites \$\$\{customer\.name\}/);
  assert.doesNotMatch(yaml, /[^$]\$\{customer\.name\}/);
});

test("an already-escaped $${...} in instructions doubles to $$${...} (composes correctly)", () => {
  const model = seedExample("rubric");
  model.dimensions[0].instructions = "Literal token: $${x}.";
  const yaml = serializeLoopYaml(model);
  assert.match(yaml, /Literal token: \$\$\$\{x\}\./);
});

test("summarizeTransitions.stopDestination reports the terminal reached when implement stops/skips/flags", () => {
  const base = () => {
    const model = seedExample("issue_lifecycle");
    return model;
  };
  const finishModel = base();
  assert.equal(summarizeTransitions(finishModel).stopDestination, "done");

  const stopModel = base();
  stopModel.outcomes.find((o) => o.name === "implement").transition = { kind: "stop" };
  assert.equal(summarizeTransitions(stopModel).stopsAfterImplement, true);
  assert.equal(summarizeTransitions(stopModel).stopDestination, "stopped");

  const attentionModel = base();
  attentionModel.outcomes.find((o) => o.name === "implement").transition = { kind: "attention" };
  assert.equal(summarizeTransitions(attentionModel).stopDestination, "needs_attention");
});

test("summarizeTransitions.maxStepsNote never classifies the budget route as success", () => {
  const model = seedExample("issue_lifecycle");
  assert.match(summarizeTransitions(model).maxStepsNote, /needs_attention \(failure\)/);
});

// ---------------------------------------------------------------------------
// BUG-3502 — history.present must never alias live state/drafts.
//
// hydrateFromStorage/restoreFromSnapshot/the Open handler are template UI
// glue, not exported core functions, so these tests extract and execute the
// actual production source via node:vm (stubbing only DOM/storage/FileReader
// effects) rather than re-implementing the fix in test code. Reverting any
// one of the three clone boundaries must fail its corresponding test below.
// ---------------------------------------------------------------------------

const TEMPLATE_PATH = join(__dirname, "..", "..", "little_loops", "templates", "policy-router-builder.html.tmpl");
const _templateSrc = readFileSync(TEMPLATE_PATH, "utf8");
const CORE_PATH = join(__dirname, "..", "..", "little_loops", "templates", "policy_builder_core.mjs");
const _coreSrc = readFileSync(CORE_PATH, "utf8");

function _extractBetween(src, startMarker, endMarker, label) {
  const start = src.indexOf(startMarker);
  if (start === -1) {
    throw new Error(`BUG-3502 test harness: could not locate start marker for ${label} — template source moved`);
  }
  const end = src.indexOf(endMarker, start + startMarker.length);
  if (end === -1) {
    throw new Error(`BUG-3502 test harness: could not locate end marker for ${label} — template source moved`);
  }
  return src.slice(start, end);
}

function _extractFunctionSource(src, signature, label) {
  const start = src.indexOf(signature);
  if (start === -1) {
    throw new Error(`BUG-3502 test harness: could not locate "${signature}" (${label}) — source moved`);
  }
  let depth = 0;
  let i = src.indexOf("{", start);
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) {
        i++;
        break;
      }
    }
  }
  return src.slice(start, i);
}

// `_deepClone` is deliberately unexported (see policy_builder_core.mjs); the
// generator text-splices this file's raw source into the template's module
// script, so the template calls it directly. Mirror that splice here.
const _DEEP_CLONE_SRC = _extractFunctionSource(_coreSrc, "function _deepClone(value) {", "core _deepClone helper");

// state/drafts/history/projectId declarations plus hydrateFromStorage(),
// restoreFromSnapshot(), and commit() — the three clone boundaries live in
// this contiguous block, except Open's (extracted separately below).
const _BOOTSTRAP_SRC = _extractBetween(
  _templateSrc,
  "let state = seedExample();",
  "function buildModel() {",
  "state/drafts/history bootstrap block"
);

// The Open-project file handler — its own independent history reset.
const _OPEN_HANDLER_SRC = _extractBetween(
  _templateSrc,
  '$("open-project-input").onchange = (e) => {',
  '$("undo-btn").onclick = () => {',
  "open-project-input onchange handler"
);

function _newBug3502Sandbox() {
  const elements = {};
  const storageMap = new Map();
  const sandbox = {
    seedExample,
    validateProjectStructure,
    applyDraftEdit,
    parseBuilderProject,
    BUILDER_PROJECT_SCHEMA_VERSION,
    window: {},
    document: { getElementById: () => null },
    localStorage: {
      getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
      setItem: (k, v) => storageMap.set(k, String(v)),
      removeItem: (k) => storageMap.delete(k),
    },
    $: (id) => {
      if (!elements[id]) elements[id] = {};
      return elements[id];
    },
    applyStateToForm: () => {},
    applyModeVisibility: () => {},
    renderAll: () => {},
    FileReader: class {
      readAsText(file) {
        this.result = file.text;
        if (this.onload) this.onload();
      }
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(_DEEP_CLONE_SRC + "\n" + _BOOTSTRAP_SRC, context, { filename: "bug-3502-bootstrap.mjs" });
  return { context, elements };
}

function _bug3502Run(context, code) {
  return vm.runInContext(code, context, { filename: "bug-3502-driver.mjs" });
}

test("BUG-3502: hydrateFromStorage() isolates history.present from live state (first edit is undoable)", () => {
  const { context } = _newBug3502Sandbox();
  _bug3502Run(context, "hydrateFromStorage();");
  const seedName = _bug3502Run(context, "state.name;");
  const seedRuleCount = _bug3502Run(context, "state.rules.length;");

  // Mutate the live model in place before commit(), mirroring add-rule's
  // real button handler, then commit and undo once.
  _bug3502Run(context, "state.rules = [...state.rules, { ...state.rules[0] }]; commit();");
  _bug3502Run(
    context,
    'history = applyDraftEdit(history, { type: "undo" }); restoreFromSnapshot(history.present);'
  );

  assert.equal(_bug3502Run(context, "state.rules.length;"), seedRuleCount, "one Undo did not restore the seed rule count");
  assert.equal(_bug3502Run(context, "state.name;"), seedName, "one Undo did not restore the seed name");
});

test("BUG-3502: restoreFromSnapshot() clones the restored draft so a post-Undo edit cannot corrupt the recovered baseline", () => {
  const { context } = _newBug3502Sandbox();
  _bug3502Run(context, "hydrateFromStorage();");
  const seedName = _bug3502Run(context, "state.name;");

  // First edit + commit, then Undo back to the seed baseline.
  _bug3502Run(context, 'state.name = "edit-1"; commit();');
  _bug3502Run(
    context,
    'history = applyDraftEdit(history, { type: "undo" }); restoreFromSnapshot(history.present);'
  );
  assert.equal(_bug3502Run(context, "state.name;"), seedName, "first Undo did not restore the seed name");

  // A second, unrelated edit right after the restore must not corrupt the
  // baseline restoreFromSnapshot just handed back.
  _bug3502Run(context, 'state.name = "edit-after-undo"; commit();');
  _bug3502Run(
    context,
    'history = applyDraftEdit(history, { type: "undo" }); restoreFromSnapshot(history.present);'
  );
  assert.equal(
    _bug3502Run(context, "state.name;"),
    seedName,
    "editing right after an Undo corrupted the restored baseline (history.present aliased live state)"
  );
});

test("BUG-3502: Open resets history and clones its snapshot so the first post-Open edit is undoable", () => {
  const { context, elements } = _newBug3502Sandbox();
  _bug3502Run(context, "hydrateFromStorage();");

  const openedModel = seedExample("decision_table");
  openedModel.name = "opened-project";
  const openedRuleCount = openedModel.rules.length;
  const projectJson = JSON.stringify({
    schemaVersion: BUILDER_PROJECT_SCHEMA_VERSION,
    generatorVersion: "",
    projectId: "proj-bug-3502-test",
    activeMode: "decision_table",
    drafts: { decision_table: { model: openedModel } },
  });

  _bug3502Run(context, _OPEN_HANDLER_SRC);
  const onchange = elements["open-project-input"].onchange;
  assert.equal(typeof onchange, "function", "open-project-input.onchange was not wired");
  onchange({ target: { files: [{ text: projectJson }], value: "" } });

  assert.equal(_bug3502Run(context, "state.name;"), "opened-project", "Open did not load the opened project");

  // The first in-place edit after Open must be undoable back to what Open loaded.
  _bug3502Run(context, "state.rules = [...state.rules, { ...state.rules[0] }]; commit();");
  _bug3502Run(
    context,
    'history = applyDraftEdit(history, { type: "undo" }); restoreFromSnapshot(history.present);'
  );
  assert.equal(_bug3502Run(context, "state.name;"), "opened-project", "one Undo after Open+edit lost the opened name");
  assert.equal(
    _bug3502Run(context, "state.rules.length;"),
    openedRuleCount,
    "one Undo after Open+edit did not restore the opened rule count"
  );
});

test("a 'goto' transition may not target a destination — destinations are never actionable verb states", () => {
  const model = _lifecycleModel({
    outcomeOverrides: { prepare: { transition: { kind: "goto", target: "skipped" } } },
  });
  const errors = validateBuilderModel(model).filter((d) => d.severity === "error");
  assert.ok(errors.some((d) => /"Go to" target "skipped" is not a defined outcome/.test(d.message)));
});
