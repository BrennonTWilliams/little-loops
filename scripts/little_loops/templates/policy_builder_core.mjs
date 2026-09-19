// policy_builder_core.mjs — FEAT-2301
//
// Pure (DOM-free) JS logic for the self-contained policy-router / rubric HTML
// builder. This module mirrors the canonical Python grammar/evaluation in
// little_loops/fsm/policy_rules.py (parse_rules, evaluate_rules, _eval_predicate)
// and little_loops/fsm/route_table.py (_detect_shadows). It is imported directly
// by node:test and inlined verbatim into the generated HTML page.
//
// ===========================================================================
// serializeLoopYaml(model) — model shape contract
// ===========================================================================
// The serializer accepts a plain object describing a builder session. Both the
// Python emit path and the browser UI build this shape. It is intentionally
// flat and JSON-friendly (no classes). Fields:
//
// {
//   mode: "decision_table" | "rubric",
//   name: string,                 // loop name (also the output filename stem)
//   description: string,          // optional; multi-line allowed
//   subject: string,              // context.subject value
//   maxSteps: number,             // max_steps (default 20 / 10)
//   thresholdHigh: number,        // rubric high threshold (slider)
//   thresholdMedium: number,      // rubric medium threshold (slider)
//   dimensions: [                 // rubric dimensions / scored axes
//     { name: string, type: "numeric" | "boolean" }
//   ],
//   rules: [                      // ordered decision-table rules (catch-all last)
//     {
//       predicates: [ { dim: string, op: string, value: string } ],
//       target: string,          // outcome token this rule routes to
//       isCatchall: boolean
//     }
//   ],
//   fallback: string,            // catch-all target when no rule supplies one
//                                // (decision_table only; the "Everything else"
//                                //  outcome). If a catch-all rule already exists
//                                //  in `rules`, that wins.
//   outcomes: [                  // per-outcome state authoring
//     {
//       name: string,            // outcome token (matches a rule target)
//       actionType: "prompt" | "slash_command" | "none",
//       body: string,            // prompt text OR "/ll:skill-name" command
//       transition: {            // Axis B
//         kind: "rescore" | "goto" | "finish",
//         target: string         // for kind==="goto": destination outcome/state
//       }
//     }
//   ]
// }
//
// Decision Table mode emits a policy-refine.yaml–shaped loop (imports
// lib/rubric-router.yaml then lib/policy-router.yaml; score → parse_scores →
// policy_dispatch route map → one state per outcome). Rubric mode emits a
// rubric-refine.yaml–shaped loop. The serializer hand-rolls YAML (block scalars
// `|` for multi-line actions) and is fully deterministic.
// ===========================================================================

// Canonical operator sets (kept in sync with policy_rules.grammar_spec()).
const ORDERED_OPS = [">=", "<=", "<", ">"];

// Valid state-name characters for a rule target — mirrors Python's
// _TARGET_PATTERN (policy_rules.py:37) exactly (BUG-3486 defect c).
const _TARGET_RE = /^[\w][\w-]*$/;

// Default JS predicate regex literal mirroring _PRED_PATTERN after
// _py_pattern_to_js translation: (?P<name>...) -> (?<name>...). Used when no
// `grammar` arg is supplied (e.g. node tests that don't shell out to Python).
const DEFAULT_PRED_RE = /^(?<dim>[\w][\w\s\-]*?)\s*:\s*(?<op>>=|<=|==|!=|<|>)\s*(?<value>\S.*?)$/;

function _predRegex(grammar) {
  if (grammar && typeof grammar.pred_pattern === "string") {
    // Accept either an already-JS pattern or a Python one. Translate the named
    // group syntax defensively; all other constructs are engine-identical.
    const src = grammar.pred_pattern.replace(/\(\?P<([^>]+)>/g, "(?<$1>");
    return new RegExp(src);
  }
  return DEFAULT_PRED_RE;
}

// ===========================================================================
// issue_lifecycle mode (FEAT-3474) — third grammar on the same builder shell.
// ===========================================================================
//
// Built-in Dimension Table: little-loops' own frontmatter fields, pre-typed
// and pre-populated whenever a builder session is in `issue_lifecycle` mode.
// `priority_rank` is the one entry that is not a raw frontmatter key — it is
// derived from `priority` (leading `P` stripped) by both the Python
// `frontmatter_scores` fragment and the `encodeFrontmatterScores` mirror below.
export const BUILTIN_FRONTMATTER_DIMENSIONS = [
  { name: "status", type: "string" },
  { name: "priority", type: "string" },
  { name: "priority_rank", type: "numeric" },
  { name: "confidence_score", type: "numeric" },
  { name: "outcome_confidence", type: "numeric" },
  { name: "decision_needed", type: "boolean" },
  { name: "spike_needed", type: "boolean" },
  { name: "blocked_by", type: "list" },
  { name: "deferred_reason", type: "string" },
];

// Verb Table: the five fixed lifecycle outcomes. `body` is the bare skill
// (matching the skill-catalog <select> and the unknown-skill check); the
// issue-id argument and `args` are appended at emit time by
// `_outcomeStateLines` when `issueArg` is set. `implement` is the one `shell`
// verb (manage-issue requires <type> <action> positionals unknowable at emit
// time; ll-auto --only mirrors rn-remediate/autodev's own per-issue implement
// state).
export const LIFECYCLE_VERBS = [
  {
    name: "prepare",
    actionType: "slash_command",
    body: "/ll:format-issue",
    args: "--auto",
    transition: { kind: "rescore" },
  },
  {
    name: "refine",
    actionType: "slash_command",
    body: "/ll:refine-issue",
    args: "--auto",
    transition: { kind: "goto", target: "gate" },
  },
  {
    name: "gate",
    actionType: "slash_command",
    body: "/ll:confidence-check",
    args: "--auto",
    transition: { kind: "rescore" },
  },
  {
    name: "implement",
    actionType: "shell",
    body: "ll-auto --only",
    args: "",
    transition: { kind: "finish" },
  },
  {
    name: "verify",
    actionType: "slash_command",
    body: "/ll:verify-issues",
    args: "--auto",
    transition: { kind: "finish" },
  },
];

/**
 * Lifecycle-only built-in terminal destinations (ENH-3492): explicit
 * stop-success (`stopped`), skip-success (`skipped`), and needs-attention
 * (`needs_attention`, a failure terminal) routes. Distinct from
 * `LIFECYCLE_VERBS` — these are never actionable states, only terminals a
 * rule/fallback/verb `transition.kind` may reference. `failure: true` marks
 * which ones emit the YAML `failure:` key; `stopped`/`skipped` do not.
 */
export const LIFECYCLE_DESTINATIONS = [
  { name: "stopped", failure: false },
  { name: "skipped", failure: false },
  { name: "needs_attention", failure: true },
];

// Outcome transition.kind -> LIFECYCLE_DESTINATIONS name, issue_lifecycle only.
const _KIND_TO_DESTINATION = { stop: "stopped", skip: "skipped", attention: "needs_attention" };
const _LIFECYCLE_ONLY_KINDS = new Set(Object.keys(_KIND_TO_DESTINATION));

/**
 * Runtime-reserved per-mode state names (BUG-3489): tokens the generated
 * pipeline itself uses as state names. An authored outcome name, rule
 * target, or fallback matching one of these collides with a generated
 * state key at emission; both serializers reject it before emission via
 * `isReservedOutcomeToken`. BUG-3486 extends this map in place: `finished`
 * (the only other name `_doneStateName()` can emit) joins decision_table;
 * `issue_id` (emitted by `_serializeIssueLifecycle()`) joins issue_lifecycle;
 * a new `rubric` key covers `_serializeRubric()`'s own state names. ENH-3492
 * adds the three new terminal destination names: all three in
 * `issue_lifecycle` (where they are directly referenceable), and
 * `needs_attention` alone in `rubric`/`decision_table` (reachable there only
 * via the automatic `on_max_steps` route, never an authored reference). The
 * `error`/underscore-prefix protections are unchanged.
 */
export const RESERVED_STATE_NAMES = {
  decision_table: new Set([
    "score",
    "parse_scores",
    "policy_dispatch",
    "failed",
    "error",
    "finished",
    "needs_attention",
  ]),
  issue_lifecycle: new Set([
    "score",
    "policy_dispatch",
    "done",
    "failed",
    "error",
    "issue_id",
    "stopped",
    "skipped",
    "needs_attention",
  ]),
  rubric: new Set([
    "score",
    "parse_scores",
    "route_high",
    "route_medium",
    "done",
    "needs_attention",
  ]),
};

/**
 * True if `token` is reserved for `mode` — either in that mode's runtime
 * set above, or underscore-prefixed. Every underscore-prefixed route key
 * (including `_` and `_error`) is stripped from explicit verdict routes by
 * `RouteConfig.from_dict()` at runtime, so an authored outcome/rule-target
 * token starting with `_` would silently vanish rather than route — a
 * finite reserved set alone cannot express this rule.
 * @param {string} mode
 * @param {string} token
 * @returns {boolean}
 */
export function isReservedOutcomeToken(mode, token) {
  if (typeof token !== "string" || token === "") return false;
  if (token.startsWith("_")) return true;
  const reserved = RESERVED_STATE_NAMES[mode] || RESERVED_STATE_NAMES.decision_table;
  return reserved.has(token);
}

/**
 * Reject any authored rule target, outcome name, or fallback in `model`
 * that collides with a reserved token for `mode` (BUG-3489). Throws an
 * `Error` naming every offending token and its source so the author can
 * rename it and its references; called by both serializers before any
 * YAML is emitted.
 * @param {string} mode
 * @param {{rules: Array, outcomes: Array, fallback: string}} model
 */
function _assertNoReservedTokens(mode, model) {
  // ENH-3492: a rule target/fallback naming a built-in lifecycle destination
  // is an allowed *reference*, not a shadowing *definition* — only outcome
  // names (which define a state) are checked against that exemption.
  const allowedDestinationRefs =
    mode === "issue_lifecycle" ? new Set(LIFECYCLE_DESTINATIONS.map((d) => d.name)) : new Set();
  const offenders = [];
  for (const r of model.rules || []) {
    if (r.target && !allowedDestinationRefs.has(r.target) && isReservedOutcomeToken(mode, r.target)) {
      offenders.push(`rule target "${r.target}"`);
    }
  }
  for (const o of model.outcomes || []) {
    if (o.name && isReservedOutcomeToken(mode, o.name)) {
      offenders.push(`outcome "${o.name}"`);
    }
  }
  if (
    model.fallback &&
    !allowedDestinationRefs.has(model.fallback) &&
    isReservedOutcomeToken(mode, model.fallback)
  ) {
    offenders.push(`fallback "${model.fallback}"`);
  }
  if (offenders.length > 0) {
    throw new Error(
      `Reserved outcome name(s): ${offenders.join(", ")}. These names — and any ` +
        `underscore-prefixed token — are reserved for the generated loop's own states ` +
        `and routing sentinels. Rename the outcome, rule target, or fallback and its references.`
    );
  }
}

/**
 * Reject any outcome whose `transition.kind` is `stop`/`skip`/`attention`
 * (the ENH-3492 lifecycle-only kinds) in a `mode` other than
 * `issue_lifecycle` — including a model reconstructed from an imported
 * project. Throws a defense-in-depth `Error`; `_checkLifecycleOnlyTransitions`
 * is the paired non-throwing UI diagnostic.
 * @param {string} mode
 * @param {{outcomes: Array}} model
 */
function _assertLifecycleOnlyTransitionsAllowed(mode, model) {
  if (mode === "issue_lifecycle") return;
  const offenders = (model.outcomes || []).filter(
    (o) => o.transition && _LIFECYCLE_ONLY_KINDS.has(o.transition.kind)
  );
  if (offenders.length > 0) {
    throw new Error(
      `Transition kind(s) reserved for issue_lifecycle mode: ` +
        `${offenders.map((o) => `"${o.name}" (${o.transition.kind})`).join(", ")}.`
    );
  }
}

// Mirrors little_loops.frontmatter.STATUS_SYNONYMS exactly (Try-it must agree
// with parse_frontmatter's canonicalization or status:==done disagrees with
// the emitted loop for an issue whose frontmatter says `status: completed`).
const STATUS_SYNONYMS_JS = {
  complete: "done",
  completed: "done",
  finished: "done",
  closed: "done",
  "in-progress": "in_progress",
  "in progress": "in_progress",
  wip: "in_progress",
  pending: "open",
};

/**
 * True if a rule is a catch-all (no predicates).
 * @param {{predicates: Array}} rule
 * @returns {boolean}
 */
export function isCatchall(rule) {
  return !rule.predicates || rule.predicates.length === 0;
}

/**
 * Normalize a dimension name: trim, lowercase, collapse whitespace runs to '-'.
 * @param {string} name
 * @returns {string}
 */
export function normalizeDimName(name) {
  return String(name).trim().toLowerCase().replace(/\s+/g, "-");
}

/**
 * Legal comparison operators for a dimension type (BUG-3486: moved from the
 * template's inline `opsForType()` so it can back both the rule editor and
 * `reconcilePredicateForDim`). The first entry in the returned array is that
 * type's default operator.
 * @param {string} type  one of "boolean" | "string" | "numeric" | "list"
 * @returns {string[]}
 */
export function opsForType(type) {
  if (type === "boolean") return ["==true", "==false"];
  if (type === "string") return ["==", "!="];
  return ["==", "!=", ">=", "<=", "<", ">"];
}

/**
 * Reconcile a predicate's `op`/`value` against a (possibly new) dimension
 * type — e.g. after the user retargets a rule condition's `dim` to a
 * dimension of a different type (BUG-3486 defect d). If the predicate's
 * current `op` is still legal for `newDimType`, returns a shallow copy
 * unchanged; otherwise resets `op` to that type's default and clears
 * `value`/`draft` so no stale, now-illegal value lingers in the model.
 * Pure: never mutates `pred`.
 * @param {{dim: string, op: string, value: string, draft?: {text: string, error: string}|null}} pred
 * @param {string} newDimType
 * @returns {{dim: string, op: string, value: string, draft: null}}
 */
export function reconcilePredicateForDim(pred, newDimType) {
  const legal = opsForType(newDimType);
  if (legal.includes(pred.op)) {
    return { ...pred };
  }
  return { ...pred, op: legal[0], value: "", draft: null };
}

/**
 * Compile a boolean predicate operator into a numeric {op, value} pair.
 * ==true -> >=50 ; ==false -> <50  (mirrors the 100/0 boolean encoding).
 * @param {string} op  one of "==true", "==false"
 * @returns {{op: string, value: string}}
 */
export function compileBooleanPredicate(op) {
  const norm = String(op).replace(/\s+/g, "").toLowerCase();
  if (norm === "==true") return { op: ">=", value: "50" };
  if (norm === "==false") return { op: "<", value: "50" };
  throw new Error(`compileBooleanPredicate: unsupported op ${op}`);
}

/**
 * Evaluate a single predicate against a scores object. Mirrors _eval_predicate.
 * @param {{dim: string, op: string, value: string}} pred
 * @param {Object} scores
 * @returns {boolean}
 */
function evalPredicate(pred, scores) {
  const raw =
    scores != null && Object.prototype.hasOwnProperty.call(scores, pred.dim)
      ? scores[pred.dim]
      : undefined;

  if (raw === undefined || raw === null) {
    // Missing dimension: only != matches.
    return pred.op === "!=";
  }

  const op = pred.op;

  if (ORDERED_OPS.includes(op)) {
    const lhs = Number(String(raw));
    const rhs = Number(String(pred.value));
    if (Number.isNaN(lhs) || Number.isNaN(rhs)) return false;
    if (op === ">") return lhs > rhs;
    if (op === "<") return lhs < rhs;
    if (op === ">=") return lhs >= rhs;
    return lhs <= rhs; // "<="
  }

  // == or != : numeric coercion first, fall back to string compare.
  const lhsF = Number(String(raw));
  const rhsF = Number(String(pred.value));
  // Python float() rejects "" and arbitrary strings; Number("") === 0 and
  // Number(" ") === 0, so guard against empty-string coercion to match Python.
  const lhsNumeric = !Number.isNaN(lhsF) && String(raw).trim() !== "";
  const rhsNumeric = !Number.isNaN(rhsF) && String(pred.value).trim() !== "";
  if (lhsNumeric && rhsNumeric) {
    if (op === "==") return lhsF === rhsF;
    return lhsF !== rhsF; // "!="
  }
  const lhsS = String(raw);
  const rhsS = String(pred.value);
  if (op === "==") return lhsS === rhsS;
  return lhsS !== rhsS; // "!="
}

/**
 * Return the target of the first matching rule, or null. Mirrors evaluate_rules.
 * @param {Array} rules  array of {predicates, target, isCatchall}
 * @param {Object} scores
 * @returns {string|null}
 */
export function evaluateRules(rules, scores) {
  for (const rule of rules) {
    if (isCatchall(rule)) return rule.target;
    if (rule.predicates.every((p) => evalPredicate(p, scores))) return rule.target;
  }
  return null;
}

/**
 * Evaluate a builder `model` against `scores`, preserving the identity of
 * the winning rule (BUG-3486 defects a/b). Unlike `evaluateRules` (which
 * takes an already-parsed rule array and returns only a target string),
 * this compiles the model's *authored* rules the same way the emitted YAML
 * does — via `parseRuleTable(_serializeRulesText(model))` — so boolean
 * predicates (`==true`/`==false`) are evaluated as their compiled numeric
 * form, never raw. Both Try-it panels share this one path.
 *
 * `ruleIndex` refers to `model.rules` (0-based): it is the index of the
 * matched rule when the match came from an authored row, or `-1` when the
 * winner is the derived fallback catch-all that `_serializeRulesText`
 * appends (no authored row to highlight). A malformed/incomplete rule
 * table (e.g. a freshly-added predicate with an empty value) fails to
 * compile; rather than throwing, this returns the same "no winner" shape
 * as a genuine no-match — `validateBuilderModel` is the surface that
 * reports the underlying defect.
 * @param {Object} model  a builder model (see file-header model-shape contract)
 * @param {Object} scores
 * @returns {{ruleIndex: number, target: string|null, isFallback: boolean, conditionResults: boolean[]}}
 */
export function evaluateModel(model, scores) {
  const noMatch = { ruleIndex: -1, target: null, isFallback: false, conditionResults: [] };
  let compiled;
  try {
    compiled = parseRuleTable(_serializeRulesText(model));
  } catch (err) {
    return noMatch;
  }
  const authoredCount = (model.rules || []).length;
  const { winner } = _traceCompiledRules(compiled, scores, authoredCount);
  if (!winner) return noMatch;
  return {
    ruleIndex: winner.ruleIndex,
    target: winner.target,
    isFallback: winner.isFallback,
    conditionResults: winner.conditions.map((c) => c.result),
  };
}

// ===========================================================================
// Shared compiled-rule trace walk (FEAT-3488)
// ===========================================================================
// One evaluation walk shared by evaluateModel (legacy MatchResult — winner's
// condition booleans only) and traceModel (full per-rule trace for scenario
// explanations). First-match routing is unchanged: only rules up to and
// including the winner are visited; every predicate *within* a visited rule
// is evaluated (not just until the first false) so a failed rule's later
// conditions still explain why it lost. Rules after the winner are
// "not_evaluated" and carry no conditions.

// One trace condition record: `provenance` (keyed by predicate dim) supplies
// the raw/encoded story from normalizeScenarioInput; evaluateModel calls
// this with no provenance, so raw fields stay absent and encoded fields fall
// back to the bare `scores` lookup — its MatchResult shape never surfaced
// provenance and must not start requiring it.
function _conditionRecord(p, scores, provenance) {
  const prov = (provenance && provenance[p.dim]) || {};
  const hasEncoded =
    prov.encodedPresent !== undefined
      ? prov.encodedPresent
      : scores != null && Object.prototype.hasOwnProperty.call(scores, p.dim);
  return {
    sourceKey: prov.sourceKey != null ? prov.sourceKey : p.dim,
    rawPresent: !!prov.rawPresent,
    rawValue: prov.rawValue,
    encodedPresent: hasEncoded,
    encodedValue: prov.encodedValue !== undefined ? prov.encodedValue : scores && scores[p.dim],
    predicate: { dim: p.dim, op: p.op, value: p.value },
    result: evalPredicate(p, scores),
  };
}

function _traceCompiledRules(compiled, scores, authoredCount, provenance) {
  const rules = [];
  let winner = null;
  for (let i = 0; i < compiled.length; i++) {
    const rule = compiled[i];
    const ruleIndex = i < authoredCount ? i : -1;
    if (winner) {
      rules.push({ ruleIndex, status: "not_evaluated", conditions: [] });
      continue;
    }
    if (isCatchall(rule)) {
      rules.push({ ruleIndex, status: "matched", conditions: [] });
      winner = { ruleIndex, target: rule.target, isFallback: true, conditions: [] };
      continue;
    }
    const conditions = rule.predicates.map((p) => _conditionRecord(p, scores, provenance));
    const allPass = conditions.every((c) => c.result);
    rules.push({ ruleIndex, status: allPass ? "matched" : "failed", conditions });
    if (allPass) winner = { ruleIndex, target: rule.target, isFallback: false, conditions };
  }
  return { rules, winner };
}

/**
 * Detect shadowed rules. Mirrors route_table._detect_shadows but returns
 * structured objects (1-based ruleNumber).
 * @param {Array} rules
 * @returns {Array<{ruleNumber: number, target: string, reason: string}>}
 */
export function detectShadows(rules) {
  const out = [];
  for (let i = 0; i < rules.length; i++) {
    const later = rules[i];
    if (isCatchall(later)) continue;
    const laterSet = new Set(later.predicates.map((p) => `${p.dim}\u0000${p.op}\u0000${p.value}`));
    for (let j = 0; j < i; j++) {
      const earlier = rules[j];
      if (isCatchall(earlier)) {
        out.push({
          ruleNumber: i + 1,
          target: later.target,
          reason: `Rule ${i + 1} (→ ${later.target}) is shadowed by catch-all rule ${j + 1}`,
        });
        break;
      }
      const earlierSet = earlier.predicates.map(
        (p) => `${p.dim}\u0000${p.op}\u0000${p.value}`
      );
      if (earlierSet.length > 0 && earlierSet.every((k) => laterSet.has(k))) {
        out.push({
          ruleNumber: i + 1,
          target: later.target,
          reason:
            `Rule ${i + 1} (→ ${later.target}) may be shadowed by rule ${j + 1} ` +
            `(→ ${earlier.target}): earlier rule has fewer/equal constraints`,
        });
        break;
      }
    }
  }
  return out;
}

const _VALID_ACTION_TYPES = new Set(["prompt", "slash_command", "shell", "none"]);
const _VALID_DIM_TYPES = new Set(["numeric", "boolean", "string", "list"]);

function _diag(severity, field, message) {
  return { severity, field, message };
}

function _checkReservedTokens(mode, model) {
  // ENH-3492: same reference-vs-definition exemption as _assertNoReservedTokens.
  const allowedDestinationRefs =
    mode === "issue_lifecycle" ? new Set(LIFECYCLE_DESTINATIONS.map((d) => d.name)) : new Set();
  const out = [];
  for (const r of model.rules || []) {
    if (r.target && !allowedDestinationRefs.has(r.target) && isReservedOutcomeToken(mode, r.target)) {
      out.push(
        _diag("error", "rules", `Rule target "${r.target}" is reserved for the generated loop's own states.`)
      );
    }
  }
  for (const o of model.outcomes || []) {
    if (o.name && isReservedOutcomeToken(mode, o.name)) {
      out.push(
        _diag("error", "outcomes", `Outcome "${o.name}" is reserved for the generated loop's own states.`)
      );
    }
  }
  if (
    model.fallback &&
    !allowedDestinationRefs.has(model.fallback) &&
    isReservedOutcomeToken(mode, model.fallback)
  ) {
    out.push(
      _diag("error", "fallback", `Fallback "${model.fallback}" is reserved for the generated loop's own states.`)
    );
  }
  return out;
}

// ENH-3492: `stop`/`skip`/`attention` transition kinds are lifecycle-only.
function _checkLifecycleOnlyTransitions(model) {
  if (model.mode === "issue_lifecycle") return [];
  const out = [];
  for (const o of model.outcomes || []) {
    const kind = o.transition && o.transition.kind;
    if (_LIFECYCLE_ONLY_KINDS.has(kind)) {
      out.push(
        _diag(
          "error",
          "outcomes",
          `Outcome "${o.name}"'s transition "${kind}" is only available in issue_lifecycle mode.`
        )
      );
    }
  }
  return out;
}

// ENH-3492: a lifecycle outcome with no action that routes straight to a
// terminal (stop/skip/attention) is never what an author means — the verb
// would do nothing and then stop/skip/flag.
function _checkActionlessNewTransitionKinds(model) {
  if (model.mode !== "issue_lifecycle") return [];
  const out = [];
  for (const o of model.outcomes || []) {
    const kind = o.transition && o.transition.kind;
    const at = o.actionType || "none";
    if (_LIFECYCLE_ONLY_KINDS.has(kind) && at === "none") {
      out.push(
        _diag(
          "error",
          "outcomes",
          `Outcome "${o.name}" combines no action with "${kind}" — add an action, or use ` +
            `"Score again"/"Go to…"/"Stop here" instead.`
        )
      );
    }
  }
  return out;
}

// ENH-3492: optional per-dimension scoring instructions/anchors. Anchors
// must be unique finite numeric scores in [0,100] with a nonempty meaning;
// boolean dimensions accept only 0/100 anchors.
function _checkDimensionMetadata(model) {
  const out = [];
  for (const d of model.dimensions || []) {
    if (d.anchors == null) continue;
    if (!Array.isArray(d.anchors)) {
      out.push(_diag("error", "dimensions", `Field "${d.name}" anchors must be a list.`));
      continue;
    }
    const seen = new Set();
    for (const a of d.anchors) {
      const score = Number(a && a.score);
      if (!Number.isFinite(score) || score < 0 || score > 100) {
        out.push(
          _diag("error", "dimensions", `Field "${d.name}" has an anchor score outside 0-100.`)
        );
        continue;
      }
      if (d.type === "boolean" && score !== 0 && score !== 100) {
        out.push(
          _diag("error", "dimensions", `Field "${d.name}" is boolean; anchors must be 0 or 100.`)
        );
      }
      if (seen.has(score)) {
        out.push(
          _diag("error", "dimensions", `Field "${d.name}" has a duplicate anchor score ${score}.`)
        );
      }
      seen.add(score);
      if (!a || !String(a.meaning || "").trim()) {
        out.push(_diag("error", "dimensions", `Field "${d.name}" has an anchor with no meaning.`));
      }
    }
  }
  return out;
}

// `aggregate` is a reserved *dimension* name (fsm/validation/reachability.py's
// `_RESERVED = {"aggregate"}`) — it is the overall rubric score, not a state
// name, so it does not belong in RESERVED_STATE_NAMES (see Decisions).
function _checkReservedDimensions(model) {
  const out = [];
  for (const d of model.dimensions || []) {
    if (normalizeDimName(d.name) === "aggregate") {
      out.push(
        _diag(
          "error",
          "dimensions",
          `Field "${d.name}" normalizes to "aggregate", which is reserved for the overall rubric score.`
        )
      );
    }
  }
  return out;
}

function _checkDuplicateOutcomes(model) {
  const out = [];
  const seen = new Set();
  for (const o of model.outcomes || []) {
    if (!o.name) continue;
    if (seen.has(o.name)) {
      out.push(_diag("error", "outcomes", `Outcome "${o.name}" is defined more than once.`));
    }
    seen.add(o.name);
  }
  return out;
}

function _checkMissingReferences(model) {
  const out = [];
  const outcomeNames = new Set((model.outcomes || []).map((o) => o.name));
  // ENH-3492: a rule/fallback reference to a built-in lifecycle destination
  // is legal without a matching `outcomes` definition — it's the reference-
  // vs-definition distinction: LIFECYCLE_DESTINATIONS entries are never
  // authored outcomes, only referenceable terminals. `names` (rule/fallback)
  // is deliberately a superset of `outcomeNames` ("Go to" target, below) —
  // "goto" jumps between actionable verb states, which a destination never
  // is, so it stays restricted to real outcomes.
  const names = new Set(outcomeNames);
  if (model.mode === "issue_lifecycle") {
    for (const d of LIFECYCLE_DESTINATIONS) names.add(d.name);
  }
  (model.rules || []).forEach((r, i) => {
    if (r.target && !names.has(r.target)) {
      out.push(
        _diag("error", `rules[${i}]`, `Rule ${i + 1} routes to "${r.target}", which is not a defined outcome.`)
      );
    }
  });
  if (model.fallback && !names.has(model.fallback)) {
    out.push(_diag("error", "fallback", `Fallback "${model.fallback}" is not a defined outcome.`));
  }
  for (const o of model.outcomes || []) {
    const t = o.transition;
    if (t && t.kind === "goto" && t.target && !outcomeNames.has(t.target)) {
      out.push(
        _diag("error", "outcomes", `Outcome "${o.name}"'s "Go to" target "${t.target}" is not a defined outcome.`)
      );
    }
  }
  return out;
}

function _checkModeTypeCombinations(model) {
  const out = [];
  for (const d of model.dimensions || []) {
    if (!_VALID_DIM_TYPES.has(d.type)) {
      out.push(_diag("error", "dimensions", `Field "${d.name}" has an unsupported type "${d.type}".`));
    } else if (model.mode === "rubric" && (d.type === "string" || d.type === "list")) {
      out.push(
        _diag("warning", "dimensions", `Field "${d.name}" is type "${d.type}", which rubric scoring does not use.`)
      );
    }
  }
  for (const o of model.outcomes || []) {
    const at = o.actionType || "none";
    if (!_VALID_ACTION_TYPES.has(at)) {
      out.push(_diag("error", "outcomes", `Outcome "${o.name}" has an unsupported action type "${at}".`));
    }
  }
  return out;
}

function _checkIncompleteActions(model) {
  const out = [];
  for (const o of model.outcomes || []) {
    const at = o.actionType || "none";
    if ((at === "prompt" || at === "slash_command" || at === "shell") && !(o.body && String(o.body).trim())) {
      const missing = at === "prompt" ? "prompt text" : at === "shell" ? "command" : "skill selected";
      out.push(_diag("error", "outcomes", `Outcome "${o.name}" has no ${missing}.`));
    }
  }
  return out;
}

function _checkStepBudget(model) {
  const steps = model.maxSteps;
  if (!(Number.isInteger(steps) && steps >= 1)) {
    return [_diag("error", "maxSteps", `Max steps must be a positive whole number (got ${JSON.stringify(steps)}).`)];
  }
  return [];
}

function _checkRubricThresholds(model) {
  if (model.mode !== "rubric") return [];
  const high = Number(model.thresholdHigh);
  const medium = Number(model.thresholdMedium);
  if (!(high > medium)) {
    return [
      _diag(
        "error",
        "thresholdHigh",
        `High threshold (${model.thresholdHigh}) must be greater than medium threshold (${model.thresholdMedium}).`
      ),
    ];
  }
  return [];
}

function _checkDrafts(model) {
  const out = [];
  for (const r of model.rules || []) {
    for (const p of r.predicates || []) {
      if (p.draft) {
        out.push(
          _diag("error", "rules", `A condition has an unsaved edit${p.draft.error ? `: ${p.draft.error}` : ""}.`)
        );
      }
    }
  }
  return out;
}

// _serializeRubric() only honors outcomes literally named light_repair/deep_repair;
// any other authored outcome is silently dropped at emission (BUG-3486 decision).
function _checkRubricUnknownOutcomes(model) {
  if (model.mode !== "rubric") return [];
  const out = [];
  for (const o of model.outcomes || []) {
    if (o.name !== "light_repair" && o.name !== "deep_repair") {
      out.push(
        _diag("warning", "outcomes", `Outcome "${o.name}" is not "light_repair" or "deep_repair"; rubric mode ignores it.`)
      );
    }
  }
  return out;
}

function _checkShadows(model) {
  return detectShadows(model.rules || []).map((s) =>
    _diag("warning", "rules", `Rule ${s.ruleNumber} (→ ${s.target}) never fires — an earlier rule already covers it.`)
  );
}

/**
 * Validate a builder `model`, returning every diagnostic found (BUG-3486).
 * Pure, non-throwing — the primary surface for reserved-name/duplicate/
 * missing-reference/incomplete-action/step-budget/threshold/draft/rubric
 * diagnostics; absorbs `detectShadows` as warnings. `severity: "error"`
 * diagnostics must block export (Copy/Download); `"warning"` diagnostics
 * are informational only. `_assertNoReservedTokens()` inside the
 * serializers stays as a throwing defense-in-depth check — this function
 * is what lets the UI show the same problem *before* the user tries to
 * export.
 * @param {Object} model  a builder model (see file-header model-shape contract)
 * @returns {Array<{severity: "error"|"warning", field: string, message: string}>}
 */
export function validateBuilderModel(model) {
  const mode = model.mode || "decision_table";
  return [
    ..._checkReservedTokens(mode, model),
    ..._checkReservedDimensions(model),
    ..._checkDuplicateOutcomes(model),
    ..._checkMissingReferences(model),
    ..._checkModeTypeCombinations(model),
    ..._checkIncompleteActions(model),
    ..._checkStepBudget(model),
    ..._checkRubricThresholds(model),
    ..._checkDrafts(model),
    ..._checkRubricUnknownOutcomes(model),
    ..._checkShadows(model),
    ..._checkLifecycleOnlyTransitions(model),
    ..._checkActionlessNewTransitionKinds(model),
    ..._checkDimensionMetadata(model),
  ];
}

/**
 * Move a rule one position up or down in precedence order. Pure: returns a
 * new object (shallow-copied `rules` array); never mutates `model.rules` or
 * the rule objects it contains. A no-op (returns an equivalent copy) at
 * either boundary — moving the first rule up, or the last rule down.
 *
 * FEAT-2301: this is the reorder half of the "ordered, numbered rule list"
 * UX model. The template calls it from ↑/↓ buttons and re-derives the
 * flattened rule order from the returned `.rules` for `buildModel()`,
 * `evaluateRules()`, and `detectShadows()` — reordering therefore changes
 * both precedence and the live "Try it" winner.
 *
 * @param {{rules: Array}} model  any object carrying a `.rules` array (the
 *   full builder model, or a minimal `{rules}` shape — only `.rules` is read)
 * @param {number} index  0-based index of the rule to move
 * @param {number|'up'|'down'} direction  -1/'up' moves the rule earlier
 *   (higher precedence); 1/'down' moves it later
 * @returns {{rules: Array}} a new object with the same own keys as `model`,
 *   plus a new `rules` array reflecting the move (or the original order,
 *   copied, if the move would go out of bounds)
 */
export function moveRule(model, index, direction) {
  const rules = (model && model.rules ? model.rules : []).slice();
  const delta = direction === "up" || direction === -1 ? -1 : 1;
  const target = index + delta;
  if (index < 0 || index >= rules.length || target < 0 || target >= rules.length) {
    return { ...model, rules };
  }
  const tmp = rules[index];
  rules[index] = rules[target];
  rules[target] = tmp;
  return { ...model, rules };
}

// ===========================================================================
// Draft / project persistence (ENH-3487)
// ===========================================================================
//
// BuilderProject {schemaVersion, generatorVersion, projectId, activeMode, drafts}
// Draft {model: Model} — a wrapper (not the bare model) so a later issue
// (FEAT-3488) can add sibling keys such as `scenarios` without changing the
// object validateBuilderModel checks or forcing a schemaVersion bump.
// DraftHistory {past, present, future} — whole-project scope: `present` is a
// ProjectSnapshot {activeMode, drafts}, not a single draft, because a mode
// switch is itself a history entry — undo across it restores both the
// previous activeMode and that mode's draft. Project/draft ID generation
// happens at the UI boundary (the template), never here, so this module
// stays pure and deterministic.

export const BUILDER_PROJECT_SCHEMA_VERSION = 1;
const _HISTORY_LIMIT = 100;
const _SUPPORTED_MODES = ["decision_table", "rubric", "issue_lifecycle"];

function _deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

// FEAT-3488: structural (not semantic) shape check for one stored scenario.
// Mirrors validateProjectStructure's own storage-vs-execution split: a
// missing input member, out-of-range score, unsupported frontmatter text, or
// stale index is editable JSON data that must survive Save/Open/reload
// unchanged — Run (runScenarioSuite/evaluateScenario) is what diagnoses those
// semantic defects, never this function.
function _validateScenarioShape(scenario, mode, idx) {
  const prefix = `drafts[${mode}].scenarios[${idx}]`;
  if (!scenario || typeof scenario !== "object" || Array.isArray(scenario)) {
    return [`${prefix} must be a JSON object`];
  }
  const errors = [];
  if (typeof scenario.id !== "string" || !scenario.id) {
    errors.push(`${prefix}.id must be a non-empty string`);
  }
  if (scenario.name !== undefined && typeof scenario.name !== "string") {
    errors.push(`${prefix}.name must be a string`);
  }
  if (!scenario.input || typeof scenario.input !== "object" || Array.isArray(scenario.input)) {
    errors.push(`${prefix}.input must be a JSON object`);
  }
  if (
    scenario.expectedTarget !== undefined &&
    scenario.expectedTarget !== null &&
    typeof scenario.expectedTarget !== "string"
  ) {
    errors.push(`${prefix}.expectedTarget must be a string or null`);
  }
  if (
    scenario.expectedRuleIndex !== undefined &&
    scenario.expectedRuleIndex !== null &&
    typeof scenario.expectedRuleIndex !== "number"
  ) {
    errors.push(`${prefix}.expectedRuleIndex must be a number or null`);
  }
  if (scenario.expectedFallback !== undefined && typeof scenario.expectedFallback !== "boolean") {
    errors.push(`${prefix}.expectedFallback must be a boolean`);
  }
  if (
    scenario.expectedRulesFingerprint !== undefined &&
    scenario.expectedRulesFingerprint !== null &&
    typeof scenario.expectedRulesFingerprint !== "string"
  ) {
    errors.push(`${prefix}.expectedRulesFingerprint must be a string or null`);
  }
  return errors;
}

/**
 * Structural (not semantic) validation of a BuilderProject-shaped object:
 * envelope fields, draft shapes, and draft-key/model.mode agreement. Never
 * judges export-readiness (that stays validateBuilderModel's job) — a draft
 * with an unfinished predicate, empty action body, missing reference, or
 * invalid step budget is structurally valid and passes here. Unknown
 * JSON-compatible fields on `project` or a draft are left untouched (not an
 * error), so later scenario metadata round-trips without being stripped.
 * @param {*} project
 * @returns {string[]} diagnostics; empty when structurally valid
 */
export function validateProjectStructure(project) {
  if (!project || typeof project !== "object" || Array.isArray(project)) {
    return ["project must be a JSON object"];
  }
  const errors = [];
  if (typeof project.projectId !== "string" || !project.projectId) {
    errors.push("projectId must be a non-empty string");
  }
  if (!_SUPPORTED_MODES.includes(project.activeMode)) {
    errors.push(
      `activeMode must be one of ${_SUPPORTED_MODES.join(", ")}, got ${JSON.stringify(project.activeMode)}`
    );
  }
  if (!project.drafts || typeof project.drafts !== "object" || Array.isArray(project.drafts)) {
    errors.push("drafts must be a JSON object");
    return errors;
  }
  for (const [mode, draft] of Object.entries(project.drafts)) {
    if (!_SUPPORTED_MODES.includes(mode)) {
      errors.push(`unknown draft mode ${JSON.stringify(mode)}`);
      continue;
    }
    if (!draft || typeof draft !== "object" || Array.isArray(draft)) {
      errors.push(`drafts[${mode}] must be a JSON object`);
      continue;
    }
    const model = draft.model;
    if (!model || typeof model !== "object" || Array.isArray(model)) {
      errors.push(`drafts[${mode}].model must be a JSON object`);
      continue;
    }
    if (model.mode !== mode) {
      errors.push(
        `drafts[${mode}].model.mode (${JSON.stringify(model.mode)}) does not match its draft key`
      );
    }
    if (!Array.isArray(model.dimensions) || !Array.isArray(model.rules) || !Array.isArray(model.outcomes)) {
      errors.push(`drafts[${mode}].model.dimensions/rules/outcomes must be arrays`);
    }
    // FEAT-3488: `scenarios` is an optional additive sibling of `model` on the
    // draft wrapper. Structural shape only (id/name/input/expectation field
    // types) — never export-readiness or execution validity, and absence is
    // not an error (older projects predate the field).
    if (draft.scenarios !== undefined) {
      if (!Array.isArray(draft.scenarios)) {
        errors.push(`drafts[${mode}].scenarios must be an array`);
      } else {
        draft.scenarios.forEach((s, idx) => {
          errors.push(..._validateScenarioShape(s, mode, idx));
        });
      }
    }
  }
  if (!errors.length && !project.drafts[project.activeMode]) {
    errors.push(`no draft exists for activeMode ${JSON.stringify(project.activeMode)}`);
  }
  return errors;
}

/**
 * Serialize a BuilderProject to indented, deterministic JSON text (Save
 * project / localStorage). Pure — no ID generation or clock reads; touches no
 * ambient globals (DI factories receive them injected).
 * @param {Object} project
 * @returns {string}
 */
export function serializeBuilderProject(project) {
  return JSON.stringify(project, null, 2);
}

/**
 * Parse and structurally validate project JSON text (Open project /
 * localStorage restore). Throws a matchable `Error` — never returns a
 * partial result — on malformed JSON or an invalid envelope/draft shape;
 * semantic export-readiness diagnostics (see validateBuilderModel) are never
 * checked here and never block a parse. A `schemaVersion` newer than
 * BUILDER_PROJECT_SCHEMA_VERSION is rejected without touching the caller's
 * current draft (the caller must catch and no-op on throw). No migrations
 * exist yet at v1 — this is the hook where a future older-schemaVersion
 * migration would run, ahead of structural validation.
 * @param {string} text
 * @returns {Object} a structurally valid BuilderProject
 */
export function parseBuilderProject(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    throw new Error(`Can't parse project: ${err.message}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Can't read project: expected a JSON object");
  }
  if (typeof parsed.schemaVersion !== "number") {
    throw new Error("Can't read project: missing schemaVersion");
  }
  if (parsed.schemaVersion > BUILDER_PROJECT_SCHEMA_VERSION) {
    throw new Error(
      `Can't read project: schemaVersion ${parsed.schemaVersion} is newer than supported (${BUILDER_PROJECT_SCHEMA_VERSION})`
    );
  }
  const errors = validateProjectStructure(parsed);
  if (errors.length) {
    throw new Error(`Can't read project: ${errors.join("; ")}`);
  }
  return parsed;
}

/**
 * Default every draft's `scenarios` to `[]` where absent (FEAT-3488: old
 * projects predate the field). A separate, explicit post-parse step — never
 * inside `parseBuilderProject` itself, which stays a faithful structural
 * parse (its golden-fixture round-trip must reproduce the source bytes
 * exactly). Pure: returns a new project object; a draft that already carries
 * `scenarios` (including hand-authored forward-compatible shapes structural
 * validation already accepted) is returned unchanged.
 * @param {Object} project  a structurally valid BuilderProject (e.g. from parseBuilderProject)
 * @returns {Object}
 */
export function withScenariosDefaulted(project) {
  const drafts = {};
  for (const [mode, draft] of Object.entries(project.drafts)) {
    drafts[mode] = draft.scenarios === undefined ? { ...draft, scenarios: [] } : draft;
  }
  return { ...project, drafts };
}

/**
 * Apply one edit to a whole-project DraftHistory. Pure: every stored
 * snapshot is a deep copy, so later mutation of the caller's live state can
 * never retroactively change a history entry.
 *
 * `edit` shapes:
 *   {type: "commit", activeMode, drafts} — any committed field/rule/outcome
 *     change, mode switch, "Start blank", or preset apply (ENH-3491); pushes
 *     the current `present` onto `past` (capped at 100 — oldest dropped
 *     first) and clears `future`
 *   {type: "undo"} / {type: "redo"} — no-op at either end of the stack
 *
 * @param {{past: Object[], present: Object|null, future: Object[]}} history
 * @param {{type: string, activeMode?: string, drafts?: Object}} edit
 * @returns {{past: Object[], present: Object, future: Object[]}}
 */
export function applyDraftEdit(history, edit) {
  const past = (history && history.past) || [];
  const present = (history && history.present) || null;
  const future = (history && history.future) || [];

  if (edit && edit.type === "undo") {
    if (!past.length) return { past, present, future };
    const restored = past[past.length - 1];
    const newPast = past.slice(0, -1);
    const newFuture = present ? [_deepClone(present), ...future] : future;
    return { past: newPast, present: restored, future: newFuture };
  }
  if (edit && edit.type === "redo") {
    if (!future.length) return { past, present, future };
    const [restored, ...rest] = future;
    const newPast = present ? [...past, _deepClone(present)] : past;
    return { past: newPast, present: restored, future: rest };
  }

  const snapshot = { activeMode: edit.activeMode, drafts: edit.drafts };
  const newPast = present ? [...past, _deepClone(present)].slice(-_HISTORY_LIMIT) : past;
  return { past: newPast, present: _deepClone(snapshot), future: [] };
}

// ===========================================================================
// Offline scenario suites (FEAT-3488)
// ===========================================================================
//
// Scenario {id, name, input, expectedTarget, expectedRuleIndex?, expectedFallback?,
//   expectedRulesFingerprint?} — a named, independently authored test case
// attached to one mode's draft (drafts[mode].scenarios). `input` is mode-
// specific (see normalizeScenarioInput). `expectedTarget: null` is
// unasserted; nothing manufactures its own oracle from the observed winner.
//
// ScenarioResult {scenarioId, actualTarget, ruleIndex?, rubricBranch?, trace,
//   verdict, diagnostics, input, needsReview} — verdict is one of
//   pass/fail/unasserted/error (see evaluateScenario's precedence).
//
// This module stays pure and DOM-free (DI factories such as
// createBuilderStorage receive ambient globals injected): no ID generation, no clock reads, no
// execution of scenario actions — the template owns ID assignment
// (crypto.randomUUID(), mirroring _newProjectId) and Run-all UI wiring.

/**
 * Canonical JSON fingerprint of a model's *authored* rules only — ordered
 * predicates `{dim, op, value}` plus `target`, in authored order. Never the
 * derived fallback (`_serializeRulesText` only appends it when no authored
 * catch-all exists), so changing solely the fallback target leaves every
 * index expectation's fingerprint current. Cryptographic hashing is
 * unnecessary offline; plain JSON text is the fingerprint.
 * @param {{rules: Array}} model
 * @returns {string}
 */
export function rulesFingerprint(model) {
  const canon = (model.rules || []).map((r) => ({
    predicates: (r.predicates || []).map((p) => ({ dim: p.dim, op: p.op, value: p.value })),
    target: r.target,
  }));
  return JSON.stringify(canon);
}

function _normalizeDecisionTableInput(model, input) {
  const diagnostics = [];
  const scores = {};
  const provenance = {};
  const dims = model.dimensions || [];
  const dimByNorm = new Map(dims.map((d) => [normalizeDimName(d.name), d]));
  const values = input && typeof input === "object" ? input.values : undefined;
  if (!values || typeof values !== "object" || Array.isArray(values)) {
    diagnostics.push(_diag("error", "input", "Decision-table scenario input must be {values: {...}}."));
    return { scores, provenance, diagnostics };
  }
  for (const [key, dim] of dimByNorm) {
    const has = Object.prototype.hasOwnProperty.call(values, key);
    const raw = has ? values[key] : undefined;
    provenance[key] = {
      sourceKey: key,
      rawPresent: has,
      rawValue: raw,
      encodedPresent: false,
      encodedValue: undefined,
    };
    if (!has) continue;
    if (raw === null) {
      diagnostics.push(_diag("error", "input", `Field "${key}" is null; omit the key to mean missing.`));
      continue;
    }
    if (dim.type === "boolean") {
      if (typeof raw !== "boolean") {
        diagnostics.push(_diag("error", "input", `Field "${key}" must be a boolean.`));
        continue;
      }
      const encoded = raw ? 100 : 0;
      scores[key] = encoded;
      provenance[key].encodedPresent = true;
      provenance[key].encodedValue = encoded;
    } else {
      if (typeof raw !== "number" || !Number.isFinite(raw) || raw < 0 || raw > 100) {
        diagnostics.push(_diag("error", "input", `Field "${key}" must be a finite number in [0,100].`));
        continue;
      }
      scores[key] = raw;
      provenance[key].encodedPresent = true;
      provenance[key].encodedValue = raw;
    }
  }
  for (const key of Object.keys(values)) {
    if (!dimByNorm.has(key)) {
      diagnostics.push(_diag("error", "input", `Field "${key}" is not a declared dimension.`));
    }
  }
  return { scores, provenance, diagnostics };
}

function _normalizeLifecycleInput(model, input) {
  const diagnostics = [];
  const provenance = {};
  const text = input && typeof input === "object" ? input.frontmatterText : undefined;
  if (typeof text !== "string") {
    diagnostics.push(_diag("error", "input", "Lifecycle scenario input must be {frontmatterText: string}."));
    return { scores: {}, provenance, diagnostics };
  }
  let fm;
  try {
    fm = parseFrontmatterBlock(text);
  } catch (err) {
    diagnostics.push(_diag("error", "input", err.message));
    return { scores: {}, provenance, diagnostics };
  }
  const scores = encodeFrontmatterScores(fm, model.dimensions || []);
  for (const d of model.dimensions || []) {
    const normName = normalizeDimName(d.name);
    // Derived dimension: retain the actual frontmatter source key ("priority"
    // for "priority_rank"), matching encodeFrontmatterScores' own lookup.
    const sourceKey = d.name === "priority_rank" ? "priority" : d.name;
    const rawPresent = fm != null && Object.prototype.hasOwnProperty.call(fm, sourceKey);
    const rawValue = rawPresent ? fm[sourceKey] : undefined;
    const encodedPresent = Object.prototype.hasOwnProperty.call(scores, normName);
    provenance[normName] = {
      sourceKey,
      rawPresent,
      rawValue,
      encodedPresent,
      encodedValue: encodedPresent ? scores[normName] : undefined,
    };
  }
  return { scores, provenance, diagnostics };
}

function _normalizeRubricInput(input) {
  const diagnostics = [];
  const raw = input && typeof input === "object" ? input.aggregate : undefined;
  if (typeof raw !== "number" || !Number.isFinite(raw) || !Number.isInteger(raw) || raw < 0 || raw > 100) {
    diagnostics.push(
      _diag("error", "input", "Rubric scenario input must be {aggregate: integer in [0,100]}.")
    );
    return { scores: {}, provenance: {}, diagnostics };
  }
  return { scores: {}, provenance: {}, aggregate: raw, diagnostics };
}

/**
 * Normalize one scenario's mode-specific `input` into the encoded `scores`
 * object `evalPredicate`/`evaluateModel` consume, plus raw/encoded
 * provenance for trace explanations. Pure; never throws — unsupported or
 * malformed input is reported via `diagnostics`, never guessed at.
 * @param {Object} model  a builder model
 * @param {Object} input  mode-specific scenario input (see file-header contract)
 * @returns {{scores: Object, provenance: Object, aggregate?: number, diagnostics: Array}}
 */
export function normalizeScenarioInput(model, input) {
  const mode = model.mode || "decision_table";
  if (mode === "rubric") return _normalizeRubricInput(input);
  if (mode === "issue_lifecycle") return _normalizeLifecycleInput(model, input);
  return _normalizeDecisionTableInput(model, input);
}

// The routing-relevant "invalid model" definition (see the issue's Proposed
// Solution): a model whose only validateBuilderModel errors are export-
// readiness ones (empty action bodies, missing outcome references, step
// budget, dimension anchors) still routes every scenario normally. Only
// these three reasons turn every scenario in the suite into `error`.
function _modelRoutingDiagnostics(model) {
  const mode = model.mode || "decision_table";
  const diagnostics = [];
  let compiled = null;
  try {
    compiled = parseRuleTable(_serializeRulesText(model));
  } catch (err) {
    diagnostics.push(_diag("error", "rules", `Rule table does not compile: ${err.message}`));
  }
  const dims = model.dimensions || [];
  const normCounts = new Map();
  for (const d of dims) {
    const n = normalizeDimName(d.name);
    normCounts.set(n, (normCounts.get(n) || 0) + 1);
  }
  const dupNames = [...normCounts.entries()].filter(([, c]) => c > 1).map(([n]) => n);
  if (dupNames.length) {
    diagnostics.push(
      _diag("error", "dimensions", `Duplicate normalized dimension name(s): ${dupNames.join(", ")}.`)
    );
  }
  if (compiled) {
    const known = new Set(dims.map((d) => normalizeDimName(d.name)));
    const unknown = new Set();
    for (const rule of compiled) {
      for (const p of rule.predicates || []) {
        if (!known.has(p.dim)) unknown.add(p.dim);
      }
    }
    if (unknown.size) {
      diagnostics.push(
        _diag("error", "rules", `Predicate references unknown dimension(s): ${[...unknown].join(", ")}.`)
      );
    }
  }
  if (mode === "rubric") {
    const high = Number(model.thresholdHigh);
    const medium = Number(model.thresholdMedium);
    if (!Number.isFinite(high) || !Number.isFinite(medium) || !(high > medium)) {
      diagnostics.push(
        _diag("error", "thresholdHigh", "Rubric thresholds are non-finite or not high > medium.")
      );
    }
  }
  return { diagnostics, compiled };
}

function _rubricBranch(model, aggregate) {
  const high = Number(model.thresholdHigh);
  const medium = Number(model.thresholdMedium);
  if (aggregate >= high) return "high";
  if (aggregate >= medium) return "medium";
  return "low";
}

const _RUBRIC_TARGETS = new Set(["done", "light_repair", "deep_repair"]);

// The valid assertion-target token set for the current policy (BUG-3486-
// adjacent to _checkMissingReferences' `names` set, reused here so
// "Expected target absent from the current policy" agrees with the
// reference-validity the rest of the builder already enforces).
function _validTargetTokens(model) {
  if (model.mode === "rubric") return _RUBRIC_TARGETS;
  const tokens = new Set();
  for (const r of model.rules || []) if (r.target) tokens.add(r.target);
  if (model.fallback) tokens.add(model.fallback);
  for (const o of model.outcomes || []) if (o.name) tokens.add(o.name);
  if (model.mode === "issue_lifecycle") {
    for (const d of LIFECYCLE_DESTINATIONS) tokens.add(d.name);
  }
  return tokens;
}

function _expectationDiagnostics(model, scenario) {
  const out = [];
  const mode = model.mode || "decision_table";
  const hasIndex = scenario.expectedRuleIndex != null;
  const hasFallback = scenario.expectedFallback === true;
  if (mode === "rubric") {
    if (hasIndex) out.push(_diag("error", "expectedRuleIndex", "Rubric scenarios reject expectedRuleIndex."));
    if (hasFallback) out.push(_diag("error", "expectedFallback", "Rubric scenarios reject expectedFallback."));
  }
  if (hasIndex && hasFallback) {
    out.push(_diag("error", "expectedFallback", "expectedFallback is mutually exclusive with expectedRuleIndex."));
  }
  if (hasFallback && scenario.expectedTarget == null) {
    out.push(_diag("error", "expectedFallback", "expectedFallback requires a non-null expectedTarget."));
  }
  if (scenario.expectedTarget == null && hasIndex) {
    out.push(_diag("error", "expectedRuleIndex", "A null expectedTarget with expectedRuleIndex is invalid."));
  }
  if (scenario.expectedTarget != null && !_validTargetTokens(model).has(scenario.expectedTarget)) {
    out.push(
      _diag(
        "error",
        "expectedTarget",
        `Expected target "${scenario.expectedTarget}" is not a defined destination in the current policy.`
      )
    );
  }
  return out;
}

// "current" (fingerprint matches rulesFingerprint(model)), "stale" (mismatch),
// or "needs_review" (missing fingerprint) — only meaningful when the
// scenario carries an expectedRuleIndex.
function _indexExpectationStatus(model, scenario) {
  if (!scenario.expectedRulesFingerprint) return "needs_review";
  return scenario.expectedRulesFingerprint === rulesFingerprint(model) ? "current" : "stale";
}

/**
 * Trace a scenario `input` against `model`: normalizes input, walks the
 * shared compiled-rule path (`_traceCompiledRules`) retaining full raw/
 * encoded provenance, and reports the routing-relevant invalid-model
 * diagnostics (nothing from export-readiness checks). Shares lower-level
 * compilation/predicate evaluation with `evaluateModel`; never duplicates
 * its semantics.
 * @param {Object} model  a builder model
 * @param {Object} input  mode-specific scenario input
 * @returns {{match: {ruleIndex: number, target: string|null, isFallback: boolean}|null, rules: Array, rubricBranch?: string|null, diagnostics: Array}}
 */
export function traceModel(model, input) {
  const { diagnostics, compiled } = _modelRoutingDiagnostics(model);
  if (diagnostics.length || !compiled) {
    return { match: null, rules: [], diagnostics };
  }
  if (model.mode === "rubric") {
    const { aggregate } = normalizeScenarioInput(model, input);
    const rubricBranch = aggregate == null ? null : _rubricBranch(model, aggregate);
    return { match: null, rules: [], rubricBranch, diagnostics };
  }
  const { scores, provenance } = normalizeScenarioInput(model, input);
  const authoredCount = (model.rules || []).length;
  const { rules, winner } = _traceCompiledRules(compiled, scores, authoredCount, provenance);
  const match = winner
    ? { ruleIndex: winner.ruleIndex, target: winner.target, isFallback: winner.isFallback }
    : { ruleIndex: -1, target: null, isFallback: false };
  return { match, rules, diagnostics };
}

/**
 * Evaluate one scenario against `model`, applying the explicit verdict
 * precedence: invalid model/input/expectation structure (or an expected
 * target absent from the current policy, or an out-of-range index claiming a
 * current fingerprint) → error; a stale/missing-fingerprint index expectation
 * → unasserted+needsReview; a null expectedTarget → unasserted; otherwise
 * compare target (and index/fallback identity when supplied) → pass/fail.
 * @param {Object} model  a builder model
 * @param {{id: string, name?: string, input: Object, expectedTarget: string|null, expectedRuleIndex?: number, expectedFallback?: boolean, expectedRulesFingerprint?: string}} scenario
 * @returns {{scenarioId: string, actualTarget: string|null, ruleIndex?: number, rubricBranch?: string, trace: Object, verdict: "pass"|"fail"|"unasserted"|"error", diagnostics: Array, input: Object, needsReview: boolean}}
 */
export function evaluateScenario(model, scenario) {
  const inputResult = normalizeScenarioInput(model, scenario.input);
  const trace = traceModel(model, scenario.input);
  const expectationDiags = _expectationDiagnostics(model, scenario);
  const diagnostics = [...trace.diagnostics, ...inputResult.diagnostics, ...expectationDiags];

  const hasIndex = scenario.expectedRuleIndex != null;
  const hasFallback = scenario.expectedFallback === true;

  let outOfRangeError = false;
  if (
    diagnostics.length === 0 &&
    hasIndex &&
    model.mode !== "rubric" &&
    _indexExpectationStatus(model, scenario) === "current"
  ) {
    const idx = scenario.expectedRuleIndex;
    if (!(Number.isInteger(idx) && idx >= 0 && idx < (model.rules || []).length)) {
      outOfRangeError = true;
    }
  }

  const base = { scenarioId: scenario.id, input: scenario.input, trace, diagnostics };

  if (diagnostics.length > 0 || outOfRangeError) {
    return { ...base, actualTarget: null, verdict: "error", needsReview: false };
  }

  let actualTarget = null;
  let ruleIndex;
  let rubricBranch;
  if (model.mode === "rubric") {
    rubricBranch = trace.rubricBranch;
    actualTarget = rubricBranch === "high" ? "done" : rubricBranch === "medium" ? "light_repair" : rubricBranch === "low" ? "deep_repair" : null;
  } else if (trace.match) {
    actualTarget = trace.match.target;
    ruleIndex = trace.match.ruleIndex;
  }

  if (hasIndex && _indexExpectationStatus(model, scenario) !== "current") {
    return { ...base, actualTarget, ruleIndex, rubricBranch, verdict: "unasserted", needsReview: true };
  }

  if (scenario.expectedTarget == null) {
    return { ...base, actualTarget, ruleIndex, rubricBranch, verdict: "unasserted", needsReview: false };
  }

  let pass = actualTarget === scenario.expectedTarget;
  if (pass && hasIndex) pass = ruleIndex === scenario.expectedRuleIndex;
  if (pass && hasFallback) pass = ruleIndex === -1;

  return { ...base, actualTarget, ruleIndex, rubricBranch, verdict: pass ? "pass" : "fail", needsReview: false };
}

// Does the model actually emit a derived fallback (a catch-all
// `_serializeRulesText` appends because no authored rule already supplies
// one)? Mirrors that function's own condition directly rather than
// re-parsing — fallback applicability is about what would be *emitted*, not
// about any one scenario's routing outcome.
function _hasDerivedFallback(model) {
  const hasAuthoredCatchall = (model.rules || []).some((r) => isCatchall(r));
  return !hasAuthoredCatchall && !!model.fallback;
}

/**
 * Run every scenario in `scenarios` against `model` and summarize totals and
 * routing coverage. Non-applicable mode collections are empty (rubric
 * branches for decision_table/issue_lifecycle; rule coverage for rubric).
 * Coverage counts only scenarios that routed successfully (verdict !==
 * "error") — invalid model/input cases (including duplicate scenario IDs)
 * contribute none.
 * @param {Object} model  a builder model
 * @param {Array} scenarios
 * @returns {{results: Array, summary: {passed: number, failed: number, unasserted: number, errors: number}, coverage: {winningRuleIndexes: number[], evaluatedRuleIndexes: number[], uncoveredRuleIndexes: number[], fallback: {applicable: boolean, covered: boolean}, winningRubricBranches: string[], uncoveredRubricBranches: string[]}}}
 */
export function runScenarioSuite(model, scenarios) {
  const results = [];
  const summary = { passed: 0, failed: 0, unasserted: 0, errors: 0 };
  const winningRuleIndexes = new Set();
  const evaluatedRuleIndexes = new Set();
  const winningRubricBranches = new Set();
  let fallbackCovered = false;

  const idCounts = new Map();
  for (const s of scenarios || []) {
    if (s && s.id) idCounts.set(s.id, (idCounts.get(s.id) || 0) + 1);
  }

  (scenarios || []).forEach((scenario, position) => {
    let result;
    if (scenario && scenario.id && idCounts.get(scenario.id) > 1) {
      result = {
        scenarioId: scenario.id,
        position,
        input: scenario.input,
        trace: null,
        actualTarget: null,
        verdict: "error",
        needsReview: false,
        diagnostics: [_diag("error", "id", `Duplicate scenario id "${scenario.id}".`)],
      };
    } else {
      result = { ...evaluateScenario(model, scenario), position };
    }
    results.push(result);
    const bucket =
      result.verdict === "pass"
        ? "passed"
        : result.verdict === "fail"
        ? "failed"
        : result.verdict === "unasserted"
        ? "unasserted"
        : "errors";
    summary[bucket]++;

    if (result.verdict === "error") return;
    if (model.mode === "rubric") {
      if (result.rubricBranch) winningRubricBranches.add(result.rubricBranch);
      return;
    }
    if (result.trace && result.trace.rules) {
      for (const r of result.trace.rules) {
        if ((r.status === "matched" || r.status === "failed") && r.ruleIndex >= 0) {
          evaluatedRuleIndexes.add(r.ruleIndex);
        }
      }
    }
    if (result.ruleIndex != null && result.ruleIndex >= 0) {
      winningRuleIndexes.add(result.ruleIndex);
    } else if (result.ruleIndex === -1) {
      fallbackCovered = true;
    }
  });

  const totalRules = (model.rules || []).length;
  const uncoveredRuleIndexes = [];
  for (let i = 0; i < totalRules; i++) {
    if (!winningRuleIndexes.has(i)) uncoveredRuleIndexes.push(i);
  }
  const allBranches = ["high", "medium", "low"];
  const uncoveredRubricBranches =
    model.mode === "rubric" ? allBranches.filter((b) => !winningRubricBranches.has(b)) : [];

  return {
    results,
    summary,
    coverage: {
      winningRuleIndexes: [...winningRuleIndexes].sort((a, b) => a - b),
      evaluatedRuleIndexes: [...evaluatedRuleIndexes].sort((a, b) => a - b),
      uncoveredRuleIndexes,
      fallback: { applicable: model.mode !== "rubric" && _hasDerivedFallback(model), covered: fallbackCovered },
      winningRubricBranches: model.mode === "rubric" ? [...winningRubricBranches] : [],
      uncoveredRubricBranches,
    },
  };
}

// Deep-copy helpers so seeded/blank models never share array/object
// references with the exported constants (mutating a builder session must
// never mutate BUILTIN_FRONTMATTER_DIMENSIONS / LIFECYCLE_VERBS).
function _cloneDims(dims) {
  return dims.map((d) => ({ ...d }));
}
function _cloneOutcomes(outcomes) {
  return outcomes.map((o) => ({ ...o, transition: { ...o.transition } }));
}

/**
 * A small, runnable issue_lifecycle example model — the seeded Use Case rules
 * (FEAT-3474): route on `status`/`severity`/`review_status`/`confidence_score`
 * through the five lifecycle verbs, falling back to `gate`.
 * @returns {Object} a builder model (see file-header model-shape contract)
 */
function _seedIssueLifecycle() {
  return {
    mode: "issue_lifecycle",
    name: "my-issue-lifecycle-loop",
    description: "",
    subject: "",
    maxSteps: 20,
    thresholdHigh: 85,
    thresholdMedium: 65,
    dimensions: [
      ..._cloneDims(BUILTIN_FRONTMATTER_DIMENSIONS),
      { name: "severity", type: "string" },
      { name: "review_status", type: "string" },
    ],
    rules: [
      {
        predicates: [{ dim: "status", op: "==", value: "done" }],
        target: "verify",
        isCatchall: false,
      },
      {
        predicates: [
          { dim: "severity", op: "==", value: "critical" },
          { dim: "review_status", op: "==", value: "approved" },
        ],
        target: "implement",
        isCatchall: false,
      },
      {
        predicates: [{ dim: "confidence_score", op: ">=", value: "85" }],
        target: "implement",
        isCatchall: false,
      },
      {
        predicates: [{ dim: "confidence_score", op: "<", value: "85" }],
        target: "refine",
        isCatchall: false,
      },
    ],
    fallback: "gate",
    outcomes: _cloneOutcomes(LIFECYCLE_VERBS),
  };
}

/**
 * An empty issue_lifecycle model — the built-in dimensions and the five
 * verbs are always present (they are structural to the mode), but no rules
 * are authored. Fallback defaults to "gate" (a verb), never the
 * decision-table default "done" (`fallbackState`, ~line 544) — "done" is the
 * bare terminal in this mode, not a routable verb.
 * @returns {Object} a builder model (see file-header model-shape contract)
 */
function _blankIssueLifecycle() {
  return {
    mode: "issue_lifecycle",
    name: "my-issue-lifecycle-loop",
    description: "",
    subject: "",
    maxSteps: 20,
    thresholdHigh: 85,
    thresholdMedium: 65,
    dimensions: _cloneDims(BUILTIN_FRONTMATTER_DIMENSIONS),
    rules: [],
    fallback: "gate",
    outcomes: _cloneOutcomes(LIFECYCLE_VERBS),
  };
}

/**
 * A small, runnable Decision Table example model — the "never a blank form"
 * seed (UX model §6). Non-empty: two dimensions, two ordered rules
 * demonstrating precedence, three outcomes, and a fallback.
 * @param {"decision_table"|"rubric"|"issue_lifecycle"} [mode="decision_table"]
 * @returns {Object} a builder model (see file-header model-shape contract)
 */
export function seedExample(mode = "decision_table") {
  if (mode === "issue_lifecycle") return _seedIssueLifecycle();
  if (mode === "rubric") {
    return {
      mode: "rubric",
      name: "my-rubric-loop",
      description: "",
      subject: "artifact.md",
      maxSteps: 10,
      thresholdHigh: 85,
      thresholdMedium: 65,
      dimensions: [
        { name: "clarity", type: "numeric" },
        { name: "has-examples", type: "boolean" },
      ],
      rules: [],
      fallback: "",
      outcomes: [],
    };
  }
  return {
    mode: "decision_table",
    name: "my-policy-loop",
    description: "",
    subject: "artifact.md",
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
      {
        predicates: [{ dim: "quality", op: ">=", value: "80" }],
        target: "light-repair",
        isCatchall: false,
      },
    ],
    fallback: "deep-repair",
    outcomes: [
      { name: "done", actionType: "none", body: "", transition: { kind: "finish" } },
      {
        name: "light-repair",
        actionType: "prompt",
        body: "Re-prompt for the lowest-scoring dimension, then re-score.",
        transition: { kind: "rescore" },
      },
      {
        name: "deep-repair",
        actionType: "prompt",
        body: "Apply comprehensive repairs across every dimension, then re-score.",
        transition: { kind: "rescore" },
      },
    ],
  };
}

/**
 * An empty builder model — the target of the "Start blank" control (UX
 * model §6). Every collection is empty; `serializeLoopYaml` can still accept
 * it (it degrades to a single catch-all/fallback), but it authors nothing.
 * `issue_lifecycle` is the exception: its built-in dimensions and five verbs
 * are structural to the mode and are never blank (see `_blankIssueLifecycle`).
 * @param {"decision_table"|"rubric"|"issue_lifecycle"} [mode="decision_table"]
 * @returns {Object} a builder model (see file-header model-shape contract)
 */
export function blankModel(mode = "decision_table") {
  if (mode === "issue_lifecycle") return _blankIssueLifecycle();
  if (mode === "rubric") {
    return {
      mode: "rubric",
      name: "my-rubric-loop",
      description: "",
      subject: "",
      maxSteps: 10,
      thresholdHigh: 85,
      thresholdMedium: 65,
      dimensions: [],
      rules: [],
      fallback: "",
      outcomes: [],
    };
  }
  return {
    mode: "decision_table",
    name: "my-policy-loop",
    description: "",
    subject: "",
    maxSteps: 20,
    thresholdHigh: 85,
    thresholdMedium: 65,
    dimensions: [],
    rules: [],
    fallback: "",
    outcomes: [],
  };
}

// ===========================================================================
// Task presets (ENH-3491)
// ===========================================================================
//
// TaskPreset {id, label, description, mode, build: () -> Model}. `mode` is
// authoritative for the mode switch the template performs on apply (see the
// Preset ↔ mode contract). Every `build()` returns a model shaped like
// `seedExample`/`blankModel` output — never a shared reference to any module
// constant (those already deep-clone dimensions/outcomes internally).
function _presetLifecycleBase(name) {
  const model = blankModel("issue_lifecycle");
  model.name = name;
  model.rules = [{ predicates: [], target: "prepare", isCatchall: true }];
  model.fallback = "prepare";
  return model;
}

function _outcomeByName(model, name) {
  return model.outcomes.find((o) => o.name === name);
}

const _TASK_PRESETS = [
  {
    id: "document-improvement",
    label: "Document improvement",
    description: "Score a document against quality dimensions and repair the lowest scorers.",
    mode: "rubric",
    build: () => seedExample("rubric"),
  },
  {
    id: "condition-based-routing",
    label: "Condition-based routing",
    description: "Route to named outcomes based on a table of conditions, in precedence order.",
    mode: "decision_table",
    build: () => seedExample("decision_table"),
  },
  {
    id: "preparation",
    label: "Preparation",
    description: "Format and refine an issue up to a confidence gate; stops before implementation.",
    mode: "issue_lifecycle",
    build: () => {
      const model = _presetLifecycleBase("prepare-issue-loop");
      _outcomeByName(model, "prepare").transition = { kind: "goto", target: "refine" };
      _outcomeByName(model, "refine").transition = { kind: "goto", target: "gate" };
      _outcomeByName(model, "gate").transition = { kind: "finish" };
      return model;
    },
  },
  {
    id: "implementation",
    label: "Implementation",
    description: "Prepare, then implement — no acceptance verification.",
    mode: "issue_lifecycle",
    build: () => {
      const model = _presetLifecycleBase("implement-issue-loop");
      _outcomeByName(model, "prepare").transition = { kind: "goto", target: "refine" };
      _outcomeByName(model, "refine").transition = { kind: "goto", target: "gate" };
      _outcomeByName(model, "gate").transition = { kind: "goto", target: "implement" };
      _outcomeByName(model, "implement").transition = { kind: "finish" };
      return model;
    },
  },
  {
    id: "implementation-with-verification",
    label: "Implementation with verification",
    description:
      "Prepare, implement, then run a configurable acceptance-check command before finishing. " +
      "Requires a command to be configured before it will export.",
    mode: "issue_lifecycle",
    build: () => {
      const model = _presetLifecycleBase("implement-verify-issue-loop");
      _outcomeByName(model, "prepare").transition = { kind: "goto", target: "refine" };
      _outcomeByName(model, "refine").transition = { kind: "goto", target: "gate" };
      _outcomeByName(model, "gate").transition = { kind: "goto", target: "implement" };
      _outcomeByName(model, "implement").transition = { kind: "goto", target: "verify" };
      const verify = _outcomeByName(model, "verify");
      verify.actionType = "shell";
      verify.body = "";
      verify.args = "";
      verify.transition = { kind: "finish" };
      verify.verificationContract = "acceptance_exit_code";
      return model;
    },
  },
];

/**
 * The available task presets (ENH-3491). Returns fresh shallow copies of the
 * preset descriptors (never the shared module array) — `build()` itself
 * already returns a fresh model on every call.
 * @returns {Array<{id: string, label: string, description: string, mode: string, build: () => Object}>}
 */
export function taskPresets() {
  return _TASK_PRESETS.map((p) => ({ ...p }));
}

/**
 * Summarize an issue_lifecycle model's reachable transitions, verification
 * status, and step budget in plain language (ENH-3491). Pure — derived from
 * `_emittedVerbs()`/outcome data, the same inputs `serializeLoopYaml`
 * consumes, never from template `state` directly, so an outcome whose
 * `actionType` changed away from `shell` is never reported as carrying an
 * acceptance contract. A state merely *named* "verify" that isn't reachable
 * (no rule/fallback/goto-chain reaches it) is not evidence of verification —
 * `verification` stays "none" in that case.
 * @param {Object} model  a builder model (see file-header model-shape contract)
 * @returns {{steps: string[], stopsAfterImplement: boolean, stopDestination: string|null, verification: "acceptance"|"issue_validation"|"unconfigured"|"custom"|"none", stepsPerAttempt: number, attempts: number, maxStepsNote: string}}
 */
export function summarizeTransitions(model) {
  const outcomeMap = new Map();
  for (const o of model.outcomes || []) outcomeMap.set(o.name, o);
  const verbs = _emittedVerbs(model);

  const implementOutcome = verbs.includes("implement") ? outcomeMap.get("implement") : null;
  const implementTransition = implementOutcome && implementOutcome.transition;
  // ENH-3492: stop/skip/attention on `implement` also stop the run — not
  // just `finish`. `stopDestination` names which terminal is actually
  // reached, so a caller can distinguish a successful stop/skip from the
  // needs_attention failure terminal.
  const implementKind = implementTransition ? implementTransition.kind : "finish";
  const stopsAfterImplement =
    !!implementOutcome &&
    (!implementTransition || implementKind === "finish" || !!_KIND_TO_DESTINATION[implementKind]);
  const stopDestination = stopsAfterImplement
    ? _KIND_TO_DESTINATION[implementKind] || "done"
    : null;

  let verification = "none";
  if (verbs.includes("verify")) {
    const v = outcomeMap.get("verify");
    const at = v ? v.actionType || "none" : "none";
    if (at === "shell") {
      const hasBody = v.body && String(v.body).trim();
      verification = hasBody && v.verificationContract === "acceptance_exit_code" ? "acceptance" : "unconfigured";
    } else if (at === "slash_command" && v.body === "/ll:verify-issues") {
      verification = "issue_validation";
    } else {
      verification = "custom";
    }
  }

  // stepsPerAttempt = score + policy_dispatch (2 fixed states) + the longest
  // reachable verb chain from any dispatch target — a `goto` continues the
  // chain, anything else (`rescore`/`finish`) ends it. FEAT-3501: chain
  // length is now derived from `analyzeTransitions`'s shared `goto` edges
  // (exactly the old per-outcome goto guard's targets) so the summary and
  // the graph can never disagree about reachable chains. A cycle guard
  // prevents an infinite loop on an authored goto cycle (summary purposes
  // only).
  const analysis = analyzeTransitions(model);
  const gotoNext = new Map();
  for (const e of analysis.edges) if (e.kind === "goto") gotoNext.set(e.source, e.target);
  const chainLenFrom = (name, seen) => {
    if (seen.has(name)) return 0;
    seen.add(name);
    if (gotoNext.has(name)) return 1 + chainLenFrom(gotoNext.get(name), seen);
    return 1;
  };
  const dispatchTargets = new Set();
  for (const e of analysis.edges) {
    if (e.source === "policy_dispatch" && e.kind === "dispatch" && outcomeMap.has(e.target)) {
      dispatchTargets.add(e.target);
    }
  }
  let chainLength = 0;
  for (const target of dispatchTargets) {
    chainLength = Math.max(chainLength, chainLenFrom(target, new Set()));
  }
  const stepsPerAttempt = 2 + chainLength;
  const maxSteps = Number.isInteger(model.maxSteps) && model.maxSteps >= 1 ? model.maxSteps : 20;
  const attempts = Math.floor(maxSteps / stepsPerAttempt);
  // ENH-3492: the budget route is now the explicit needs_attention failure
  // terminal, not a bare "failed" — no summary may classify it as success.
  const maxStepsNote =
    `max steps ${maxSteps} ≈ ${attempts} attempt${attempts === 1 ? "" : "s"} of ` +
    `${stepsPerAttempt} state${stepsPerAttempt === 1 ? "" : "s"} each; exceeding the budget ` +
    `lands on needs_attention (failure)`;

  return {
    steps: verbs,
    stopsAfterImplement,
    stopDestination,
    verification,
    stepsPerAttempt,
    attempts,
    maxStepsNote,
  };
}

/**
 * Parse one predicate string into {dim, op, value}. Mirrors _parse_predicate.
 * @param {string} text
 * @param {RegExp} re
 * @returns {{dim: string, op: string, value: string}}
 */
function parsePredicate(text, re) {
  const m = re.exec(text.trim());
  if (!m || !m.groups) {
    throw new Error(`Invalid predicate ${JSON.stringify(text)}`);
  }
  const dim = m.groups.dim.trim();
  const op = m.groups.op;
  const value = m.groups.value.trim();
  // Parity with Python's _parse_predicate (policy_rules.py:87-94): an
  // ordered operator requires a numeric value at parse time.
  if (ORDERED_OPS.includes(op) && Number.isNaN(Number(value))) {
    throw new Error(
      `Ordered operator ${JSON.stringify(op)} requires a numeric value; ` +
        `got ${JSON.stringify(value)} in predicate ${JSON.stringify(text)}`
    );
  }
  return { dim, op, value };
}

/**
 * Parse a newline-separated rule table into a rules array. Mirrors parse_rules.
 * Skips blank/`#` lines; `*` LHS = catch-all; `&`-splits predicates.
 * @param {string} text
 * @param {Object} [grammar]  grammar_spec()-shaped object (optional)
 * @returns {Array<{predicates: Array, target: string, isCatchall: boolean}>}
 */
export function parseRuleTable(text, grammar) {
  const re = _predRegex(grammar);
  const rules = [];
  const lines = String(text).split("\n");
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const arrow = line.indexOf("->");
    if (arrow === -1) {
      throw new Error(`Rule is missing '->': ${JSON.stringify(line)}`);
    }
    const lhs = line.slice(0, arrow).trim();
    const target = line.slice(arrow + 2).trim();
    if (!target) {
      throw new Error(`Empty target state in: ${JSON.stringify(line)}`);
    }
    // Parity with Python's _TARGET_PATTERN check (policy_rules.py:140-144).
    if (!_TARGET_RE.test(target)) {
      throw new Error(
        `Line has invalid target state name ${JSON.stringify(target)} ` +
          `(only word chars and hyphens allowed)`
      );
    }
    if (lhs === "*") {
      rules.push({ predicates: [], target, isCatchall: true });
    } else {
      const parts = lhs
        .split("&")
        .map((p) => p.trim())
        .filter((p) => p.length > 0);
      if (parts.length === 0) {
        throw new Error(`Empty LHS in: ${JSON.stringify(line)}`);
      }
      const preds = parts.map((p) => parsePredicate(p, re));
      rules.push({ predicates: preds, target, isCatchall: false });
    }
  }
  return rules;
}

// ===========================================================================
// YAML serialization
// ===========================================================================

function _yamlBlockScalar(value, indent) {
  // Emit a `|` block scalar. `indent` is the spaces preceding child lines.
  const pad = " ".repeat(indent);
  const lines = String(value).replace(/\s+$/, "").split("\n");
  return lines.map((l) => (l.length ? pad + l : "")).join("\n");
}

function _dq(value) {
  // Double-quote a scalar, escaping backslashes and quotes. Deterministic.
  return `"${String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

// Build the canonical rule-table text for context.policy_rules. Numeric dims
// pass through; boolean predicates are compiled to numeric (>=50 / <50).
// Exported (in addition to internal use by both serializers) so the
// template's Try-it panel and node:test can evaluate the same *compiled*
// text the emitted YAML carries — see `evalPredicate`'s note on why raw
// `model.rules` (`==true`/`==false` tokens) must never be fed to
// `evaluateRules` directly.
export function _serializeRulesText(model) {
  const boolDims = new Set(
    (model.dimensions || [])
      .filter((d) => d.type === "boolean")
      .map((d) => normalizeDimName(d.name))
  );
  const lines = [];
  let hasCatchall = false;
  for (const rule of model.rules || []) {
    if (rule.isCatchall || !rule.predicates || rule.predicates.length === 0) {
      hasCatchall = true;
      lines.push(`* -> ${rule.target}`);
      continue;
    }
    const predStrs = rule.predicates.map((p) => {
      const dim = normalizeDimName(p.dim);
      let op = p.op;
      let value = p.value;
      if (boolDims.has(dim) && (op === "==" || op === "==true" || op === "==false")) {
        const truth =
          op === "==true" ||
          (op === "==" && String(value).trim().toLowerCase() === "true");
        const compiled = compileBooleanPredicate(truth ? "==true" : "==false");
        op = compiled.op;
        value = compiled.value;
      }
      return `${dim}:${op}${value}`;
    });
    lines.push(`${predStrs.join(" & ")} -> ${rule.target}`);
  }
  // Append the fallback catch-all last if the table didn't supply one.
  if (!hasCatchall && model.fallback) {
    lines.push(`* -> ${model.fallback}`);
  }
  return lines.join("\n");
}

// Pipe-joined, normalized dimension names for context.rubric_dimensions.
function _serializeDimensions(model) {
  return (model.dimensions || []).map((d) => normalizeDimName(d.name)).join("|");
}

// Does any dimension require the 100/0 boolean scoring instruction?
function _hasBoolean(model) {
  return (model.dimensions || []).some((d) => d.type === "boolean");
}

// ENH-3492: `instructions`/anchor `meaning` text is opaque literal text
// passed through to the LLM grading prompt — never an FSM interpolation
// template. A YAML block scalar (`_yamlBlockScalar`) protects YAML structure
// but not the FSM's own `${...}` interpolation once the emitted prompt
// reaches FSMExecutor, so any literal `${` must be escaped to `$${` (the
// FSM's existing escape convention, `fsm/interpolation.py` ESCAPED_PATTERN)
// before emission. Doubling composes: authored `$${x}` already contains one
// `${` occurrence and is escaped to `$$${x}`, which unescapes back to the
// authored `$${x}` at runtime — a single, uniform rule.
function _escapeInterpolation(text) {
  return String(text).replace(/\$\{/g, (m) => "$" + m);
}

function _scoreActionBody(model) {
  const dims = _serializeDimensions(model);
  let body =
    `Evaluate ${"${context.subject}"} on these dimensions: ${"${context.rubric_dimensions}"}.\n` +
    `For each dimension output: DIMENSION: <name>: <score 0-100> — <one-sentence rationale>\n`;
  if (_hasBoolean(model)) {
    const boolNames = (model.dimensions || [])
      .filter((d) => d.type === "boolean")
      .map((d) => normalizeDimName(d.name))
      .join(", ");
    body +=
      `For boolean dimensions (${boolNames}): score 100 if the condition holds, ` +
      `0 if it does not.\n`;
  }
  // ENH-3492: optional per-dimension scoring instructions/anchors. Absent on
  // every dimension, this loop appends nothing — existing prompts stay
  // byte-for-byte unchanged.
  for (const d of model.dimensions || []) {
    if (d.instructions && String(d.instructions).trim()) {
      body += `For ${normalizeDimName(d.name)}: ${_escapeInterpolation(
        String(d.instructions).trim()
      )}\n`;
    }
    if (Array.isArray(d.anchors) && d.anchors.length) {
      const parts = d.anchors
        .slice()
        .sort((a, b) => Number(a.score) - Number(b.score))
        .map((a) => `${a.score}=${_escapeInterpolation(String(a.meaning || ""))}`);
      body += `Score anchors for ${normalizeDimName(d.name)}: ${parts.join(", ")}\n`;
    }
  }
  body += `Final line: AGGREGATE: <int 0-100>`;
  return body;
}

// Render a per-outcome state body action. Returns lines for the state.
//
// BUG-2813 fix (shared by both modes): the executor never runs a terminal
// state's action (it returns the instant a `terminal: true` state is
// entered, executor.py:816), so a `finish` transition on an outcome that
// *has* an action must not be emitted as `action: ... / terminal: true` in
// the same state — that action is dead code. Instead it is emitted as a
// non-terminal state with `next: <doneState>`, and the caller is
// responsible for emitting the bare `<doneState>: {terminal: true}` state
// once. An outcome with `actionType: "none"` and `finish` still emits a bare
// `terminal: true` on itself (nothing would ever run there either way).
//
// `issueArg` (FEAT-3474): when set, appends the issue-id reference and then
// ` <outcome.args>` (if non-empty) to slash_command/shell bodies — the
// issue_lifecycle mode's per-verb argument-bearing emit shape. Also adds
// support for `actionType: "shell"` (single-line `action:`, no leading
// skill-select semantics), used by the `implement` verb's shell default.
// `shell` bodies use the shlex-quoting `${context.issue_id:shell}` form (MR-11:
// a bare `${context.issue_id}` in an `action_type: shell` body is user-controlled
// interpolation in a raw bash-token position and trips the unsafe-interpolation
// WARNING); `slash_command` bodies are not bash-executed, so they keep the bare
// `${context.issue_id}` form the AC pins.
function _outcomeStateLines(outcome, { doneState = "done", issueArg = false, mode } = {}) {
  const lines = [];
  lines.push(`  ${outcome.name}:`);
  const at = outcome.actionType || "none";
  const hasAction = at === "prompt" || at === "slash_command" || at === "shell";
  if (hasAction) {
    lines.push(`    action_type: ${at}`);
    if (at === "prompt") {
      lines.push(`    action: |`);
      lines.push(_yamlBlockScalar(outcome.body || "", 6));
    } else {
      let body = (outcome.body || "").trim();
      if (issueArg) {
        body += at === "shell" ? " ${context.issue_id:shell}" : " ${context.issue_id}";
        if (outcome.args && String(outcome.args).trim()) {
          body += ` ${String(outcome.args).trim()}`;
        }
      }
      lines.push(`    action: ${body}`);
    }
  }
  // Axis B transition.
  const t = outcome.transition || { kind: "finish" };
  // ENH-3492: stop/skip/attention route straight to a LIFECYCLE_DESTINATIONS
  // terminal — lifecycle mode only (rubric/decision_table never reach this
  // branch; validation/the serializer's throwing guard reject the kind
  // before emission). Emitted even when the outcome has no action: a
  // destination reference always replaces the verb's `next` target, never
  // its (possibly absent) action.
  const destination = mode === "issue_lifecycle" ? _KIND_TO_DESTINATION[t.kind] : undefined;
  if (t.kind === "rescore") {
    lines.push(`    next: score`);
  } else if (t.kind === "goto") {
    lines.push(`    next: ${t.target}`);
  } else if (destination) {
    lines.push(`    next: ${destination}`);
  } else if (hasAction) {
    lines.push(`    next: ${doneState}`);
  } else {
    lines.push(`    terminal: true`);
  }
  return lines;
}

/**
 * The state name to use for the shared "finish with an action" done target
 * (BUG-2813 fix). Returns "done" unless an outcome, rule target, or the
 * fallback already uses that name (decision-table outcomes may legitimately
 * be named anything, including "done" — `fallbackState` itself defaults to
 * "done"), in which case "finished" is used instead so no self-loop or
 * duplicate `done:` key is ever emitted. issue_lifecycle's fixed verb set
 * (prepare/refine/gate/implement/verify) can never collide.
 * @param {{rules: Array, outcomes: Array, fallback: string}} model
 * @returns {string}
 */
export function _doneStateName(model) {
  const used = new Set();
  for (const r of model.rules || []) if (r.target) used.add(r.target);
  for (const o of model.outcomes || []) if (o.name) used.add(o.name);
  if (model.fallback) used.add(model.fallback);
  return used.has("done") ? "finished" : "done";
}

function _serializeDecisionTable(model) {
  _assertNoReservedTokens("decision_table", model);
  _assertLifecycleOnlyTransitionsAllowed("decision_table", model);
  const out = [];
  const name = model.name || "policy-builder";
  out.push(`name: ${name}`);
  if (model.description) {
    out.push(`description: |`);
    out.push(_yamlBlockScalar(model.description, 2));
  }
  out.push(`max_steps: ${model.maxSteps != null ? model.maxSteps : 20}`);
  out.push("");
  // ENH-3492: a step-budget exhaustion is now the explicit needs_attention
  // failure terminal, not the generic `failed` terminal — `needs_attention`
  // is reserved for decision_table (RESERVED_STATE_NAMES) so it is only ever
  // reachable via this automatic route, never an authored rule/outcome.
  out.push("on_max_steps: needs_attention");
  out.push("");
  out.push("import:");
  out.push("  - lib/rubric-router.yaml");
  out.push("  - lib/policy-router.yaml");
  out.push("");
  out.push("context:");
  out.push(`  subject: ${_dq(model.subject || "")}`);
  out.push(`  rubric_dimensions: ${_dq(_serializeDimensions(model))}`);
  out.push(`  threshold_high: ${_dq(String(model.thresholdHigh != null ? model.thresholdHigh : 85))}`);
  out.push(
    `  threshold_medium: ${_dq(String(model.thresholdMedium != null ? model.thresholdMedium : 65))}`
  );
  out.push(`  policy_rules: |`);
  out.push(_yamlBlockScalar(_serializeRulesText(model), 4));
  out.push("");
  out.push("initial: score");
  out.push("");
  out.push("states:");
  // score
  out.push("  score:");
  out.push("    fragment: rubric_score");
  out.push("    action: |");
  out.push(_yamlBlockScalar(_scoreActionBody(model), 6));
  out.push("    capture: scores");
  out.push("    next: parse_scores");
  out.push("    on_error: failed");
  out.push("");
  // parse_scores
  out.push("  parse_scores:");
  out.push("    fragment: policy_parse_scores");
  out.push("    next: policy_dispatch");
  out.push("    on_error: failed");
  out.push("");
  // policy_dispatch with route map covering every outcome + _/_error
  out.push("  policy_dispatch:");
  out.push("    fragment: policy_table_dispatch");
  out.push("    on_error: failed");
  out.push("    route:");
  // Collect every outcome token from rules + outcomes + fallback (dedup, ordered).
  const tokens = [];
  const seen = new Set();
  const addToken = (tok) => {
    if (tok && !seen.has(tok)) {
      seen.add(tok);
      tokens.push(tok);
    }
  };
  for (const r of model.rules || []) addToken(r.target);
  for (const o of model.outcomes || []) addToken(o.name);
  if (model.fallback) addToken(model.fallback);
  for (const tok of tokens) {
    out.push(`      ${tok}: ${tok}`);
  }
  // Sentinels: default -> fallback (or first outcome); error (BUG-3489) ->
  // the dedicated `failed` terminal, never a user outcome — `_error` now
  // resolves ahead of `_` in `FSMExecutor._route()`, so it must not reuse
  // the first rule's target the way `_` does.
  const fallbackState = model.fallback || tokens[0] || "done";
  out.push(`      _: ${fallbackState}`);
  out.push(`      _error: failed`);
  out.push("");
  // One state per outcome. Build outcome map for authoring; tokens not listed
  // in `outcomes` get a default terminal state so the route never dead-ends.
  const outcomeMap = new Map();
  for (const o of model.outcomes || []) outcomeMap.set(o.name, o);
  const doneState = _doneStateName(model);
  let usedDoneState = false;
  for (const tok of tokens) {
    const outcome =
      outcomeMap.get(tok) || { name: tok, actionType: "none", transition: { kind: "finish" } };
    const at = outcome.actionType || "none";
    const isFinish = !outcome.transition || outcome.transition.kind === "finish";
    if (isFinish && at !== "none") usedDoneState = true;
    for (const line of _outcomeStateLines(outcome, { doneState })) out.push(line);
    out.push("");
  }
  // BUG-2813 fix: only the outcomes above ever reference `doneState` (via
  // `next: <doneState>`), so it is only emitted when at least one finish
  // outcome actually has an action — never a dangling/unreachable extra
  // terminal on a table where every finish outcome is `actionType: none`
  // (those already emit their own bare `terminal: true`).
  if (usedDoneState) {
    out.push(`  ${doneState}:`);
    out.push(`    terminal: true`);
    out.push("");
  }
  out.push(`  failed:`);
  out.push(`    terminal: true`);
  out.push(`    failure: true`);
  out.push("");
  // ENH-3492: unconditional — needs_attention is reserved for decision_table,
  // so it is only ever reached via the on_max_steps route above, never an
  // authored reference.
  out.push(`  needs_attention:`);
  out.push(`    terminal: true`);
  out.push(`    failure: true`);
  out.push("");
  return out.join("\n").replace(/\n+$/, "\n");
}

function _serializeRubric(model) {
  _assertNoReservedTokens("rubric", model);
  _assertLifecycleOnlyTransitionsAllowed("rubric", model);
  const out = [];
  const name = model.name || "rubric-builder";
  out.push(`name: ${name}`);
  if (model.description) {
    out.push(`description: |`);
    out.push(_yamlBlockScalar(model.description, 2));
  }
  out.push(`category: quality`);
  out.push(`input_key: subject`);
  out.push(`required_inputs: ["subject"]`);
  out.push(`initial: score`);
  out.push(`max_steps: ${model.maxSteps != null ? model.maxSteps : 10}`);
  out.push("");
  // ENH-3492: rubric previously emitted no on_max_steps line at all; this is
  // an added line, not a changed one. needs_attention is reserved for
  // rubric, so — same as decision_table — only ever reached via this route.
  out.push("on_max_steps: needs_attention");
  out.push("");
  out.push("import:");
  out.push("  - lib/rubric-router.yaml");
  out.push("");
  out.push("context:");
  out.push(`  subject: ${_dq(model.subject || "")}`);
  out.push(`  rubric_dimensions: ${_dq(_serializeDimensions(model))}`);
  out.push(`  threshold_high: ${_dq(String(model.thresholdHigh != null ? model.thresholdHigh : 85))}`);
  out.push(
    `  threshold_medium: ${_dq(String(model.thresholdMedium != null ? model.thresholdMedium : 65))}`
  );
  out.push("");
  out.push("states:");
  // score
  out.push("  score:");
  out.push("    fragment: rubric_score");
  out.push("    action: |");
  out.push(_yamlBlockScalar(_scoreActionBody(model), 6));
  out.push("    capture: scores");
  out.push("    next: parse_scores");
  out.push("");
  // parse_scores
  out.push("  parse_scores:");
  out.push("    fragment: rubric_parse_scores");
  out.push("    next: route_high");
  out.push("");
  // route_high
  out.push("  route_high:");
  out.push("    fragment: rubric_route_high");
  out.push("    on_yes: done");
  out.push("    on_no: route_medium");
  out.push("");
  // route_medium
  out.push("  route_medium:");
  out.push("    fragment: rubric_route_medium");
  out.push("    on_yes: light_repair");
  out.push("    on_no: deep_repair");
  out.push("");
  // Repair states: prefer authored outcomes for light_repair/deep_repair if present.
  const outcomeMap = new Map();
  for (const o of model.outcomes || []) outcomeMap.set(o.name, o);
  for (const tok of ["light_repair", "deep_repair"]) {
    const authored = outcomeMap.get(tok);
    if (authored) {
      for (const line of _outcomeStateLines(authored)) out.push(line);
    } else {
      out.push(`  ${tok}:`);
      out.push(`    action_type: prompt`);
      out.push(`    action: |`);
      const body =
        tok === "light_repair"
          ? `Apply light refinements to ${"${context.subject}"}.\n` +
            `Focus on the lowest-scoring dimensions to push the aggregate above ${"${context.threshold_high}"}.`
          : `Apply comprehensive repairs to ${"${context.subject}"}.\n` +
            `The aggregate is below ${"${context.threshold_medium}"}; rewrite the weakest sections.`;
      out.push(_yamlBlockScalar(body, 6));
      out.push(`    next: score`);
    }
    out.push("");
  }
  out.push("  done:");
  out.push("    terminal: true");
  out.push("");
  // ENH-3492: unconditional, same reasoning as decision_table's — reserved,
  // only reached via on_max_steps.
  out.push("  needs_attention:");
  out.push("    terminal: true");
  out.push("    failure: true");
  return out.join("\n").replace(/\n+$/, "\n");
}

// ===========================================================================
// issue_lifecycle serialization (FEAT-3474)
// ===========================================================================

/**
 * `name:type|name:type` text (raw, non-normalized key names) for
 * `context.frontmatter_dimensions` — the pipe-separated dimension
 * declaration the `frontmatter_scores` fragment parses at run time. Unlike
 * `_serializeDimensions` (which normalizes names for `context.rubric_dimensions`),
 * this preserves the raw frontmatter key so the fragment can look it up
 * case-sensitively in the parsed frontmatter dict.
 * @param {{dimensions: Array<{name: string, type: string}>}} model
 * @returns {string}
 */
export function serializeFrontmatterDimensions(model) {
  return (model.dimensions || []).map((d) => `${d.name}:${d.type}`).join("|");
}

/**
 * The transitive closure of emitted verb states: verbs targeted by a rule,
 * `model.fallback`, and the `goto` target of any verb already in the set
 * (recursively — a goto chain through several verbs is fully included).
 * Only verbs in this closure get a state in the emitted YAML; the rest are
 * left out entirely (fixed verb set, but not every verb is necessarily
 * reachable in a given rule table). Returned in Verb Table / `model.outcomes`
 * order for deterministic emission.
 * @param {{rules: Array, outcomes: Array, fallback: string}} model
 * @returns {string[]}
 */
export function _emittedVerbs(model) {
  const outcomeMap = new Map();
  for (const o of model.outcomes || []) outcomeMap.set(o.name, o);

  const emitted = new Set();
  for (const r of model.rules || []) {
    if (r.target && outcomeMap.has(r.target)) emitted.add(r.target);
  }
  if (model.fallback && outcomeMap.has(model.fallback)) emitted.add(model.fallback);

  let changed = true;
  while (changed) {
    changed = false;
    for (const name of Array.from(emitted)) {
      const oc = outcomeMap.get(name);
      const target = oc && oc.transition && oc.transition.kind === "goto" && oc.transition.target;
      if (target && outcomeMap.has(target) && !emitted.has(target)) {
        emitted.add(target);
        changed = true;
      }
    }
  }

  return (model.outcomes || []).map((o) => o.name).filter((n) => emitted.has(n));
}

/**
 * The LIFECYCLE_DESTINATIONS names an author has actually selected — as a
 * rule target, the fallback, or a verb's `transition.kind` — as opposed to
 * `needs_attention`'s automatic `on_max_steps` route, which references a
 * destination without any dispatch mechanism reaching it (ENH-3492). Drives
 * which `policy_dispatch.route` entries `_serializeIssueLifecycle` emits
 * beyond the verb entries, and (via `computeSummary`) which destinations a
 * transition summary reports alongside verbs. Returned in
 * `LIFECYCLE_DESTINATIONS` order for deterministic emission.
 * @param {{rules: Array, outcomes: Array, fallback: string}} model
 * @returns {string[]}
 */
export function _dispatchedDestinations(model) {
  const destNames = new Set(LIFECYCLE_DESTINATIONS.map((d) => d.name));
  const found = new Set();
  for (const r of model.rules || []) {
    if (r.target && destNames.has(r.target)) found.add(r.target);
  }
  if (model.fallback && destNames.has(model.fallback)) found.add(model.fallback);
  for (const o of model.outcomes || []) {
    const dest = o.transition && _KIND_TO_DESTINATION[o.transition.kind];
    if (dest) found.add(dest);
  }
  return LIFECYCLE_DESTINATIONS.map((d) => d.name).filter((n) => found.has(n));
}

/**
 * The LIFECYCLE_DESTINATIONS names that need a terminal YAML block emitted:
 * `_dispatchedDestinations(model)` plus `needs_attention` unconditionally
 * (the automatic `on_max_steps` route always targets it, in every model,
 * whether or not anything else references it) — so the terminal exists for
 * the executor to land on even when nothing dispatches to it (ENH-3492).
 * Strictly a superset of `_dispatchedDestinations`; the two sets differ
 * exactly when `on_max_steps` is the only reference to `needs_attention`.
 * @param {{rules: Array, outcomes: Array, fallback: string}} model
 * @returns {string[]}
 */
export function _requiredTerminalBlocks(model) {
  const required = new Set(_dispatchedDestinations(model));
  required.add("needs_attention");
  return LIFECYCLE_DESTINATIONS.map((d) => d.name).filter((n) => required.has(n));
}

/**
 * Structural transition analysis for an issue_lifecycle model (FEAT-3501):
 * one shared `{nodes, edges, reachableNodeIds, cycles}` contract that both
 * `summarizeTransitions` and the builder's graph panel consume, so the prose
 * summary and the graph can never disagree. Pure — derived from
 * `model.rules`/`model.outcomes`/`model.fallback` only, the same emitted-
 * outcome/destination semantics `_emittedVerbs`/`_dispatchedDestinations`/
 * `_requiredTerminalBlocks`/`_outcomeStateLines` use for YAML generation.
 * Edges cover *authored* transitions only — the implicit `on_max_steps` ->
 * needs_attention route and every state's `on_error: failed` route are never
 * represented, so a structural warning never claims an action outcome or
 * guarantees nontermination. Non-lifecycle models (`rubric`/`decision_table`)
 * return the empty analysis; the graph panel itself is lifecycle-only.
 * @param {Object} model  a builder model (see file-header model-shape contract)
 * @returns {{nodes: Array<{id: string, kind: "scoring"|"dispatch"|"outcome"|"terminal"}>, edges: Array<{source: string, target: string, kind: "dispatch"|"goto"|"rescore"|"terminal"}>, reachableNodeIds: string[], cycles: Array<{nodeIds: string[], kind: "goto"|"rescore_feedback"}>}}
 */
export function analyzeTransitions(model) {
  if (!model || model.mode !== "issue_lifecycle") {
    return { nodes: [], edges: [], reachableNodeIds: [], cycles: [] };
  }

  const outcomes = model.outcomes || [];
  const outcomeMap = new Map();
  for (const o of outcomes) outcomeMap.set(o.name, o);

  const nodes = [
    { id: "score", kind: "scoring" },
    { id: "policy_dispatch", kind: "dispatch" },
    ...outcomes.map((o) => ({ id: o.name, kind: "outcome" })),
    { id: "done", kind: "terminal" },
    ...LIFECYCLE_DESTINATIONS.map((d) => ({ id: d.name, kind: "terminal" })),
  ];

  const edges = [{ source: "score", target: "policy_dispatch", kind: "dispatch" }];

  // policy_dispatch -> every distinct rule target / the fallback, in
  // authoring order; a target may be a verb or a destination.
  const dispatchTargets = [];
  const seenDispatchTargets = new Set();
  for (const r of model.rules || []) {
    if (r.target && !seenDispatchTargets.has(r.target)) {
      seenDispatchTargets.add(r.target);
      dispatchTargets.push(r.target);
    }
  }
  if (model.fallback && !seenDispatchTargets.has(model.fallback)) {
    seenDispatchTargets.add(model.fallback);
    dispatchTargets.push(model.fallback);
  }
  for (const target of dispatchTargets) {
    edges.push({ source: "policy_dispatch", target, kind: "dispatch" });
  }

  // Per-outcome edges, mirroring `_outcomeStateLines`'s transition branch
  // exactly (policy_builder_core.mjs's YAML `next:`/`terminal:` emission).
  for (const o of outcomes) {
    const t = o.transition || { kind: "finish" };
    if (t.kind === "goto") {
      if (t.target && outcomeMap.has(t.target)) {
        edges.push({ source: o.name, target: t.target, kind: "goto" });
      }
    } else if (t.kind === "rescore") {
      edges.push({ source: o.name, target: "score", kind: "rescore" });
    } else if (_KIND_TO_DESTINATION[t.kind]) {
      edges.push({ source: o.name, target: _KIND_TO_DESTINATION[t.kind], kind: "terminal" });
    } else {
      // `finish` (or no transition): an action yields an edge to `done`; no
      // action makes the outcome itself a sink (`terminal: true` in the
      // emitted YAML) — no edge.
      const at = o.actionType || "none";
      const hasAction = at === "prompt" || at === "slash_command" || at === "shell";
      if (hasAction) edges.push({ source: o.name, target: "done", kind: "terminal" });
    }
  }

  const adjacency = new Map();
  for (const e of edges) {
    if (!adjacency.has(e.source)) adjacency.set(e.source, []);
    adjacency.get(e.source).push(e.target);
  }
  const reached = new Set();
  const toVisit = ["score"];
  while (toVisit.length) {
    const cur = toVisit.pop();
    if (reached.has(cur)) continue;
    reached.add(cur);
    for (const next of adjacency.get(cur) || []) {
      if (!reached.has(next)) toVisit.push(next);
    }
  }
  const reachableNodeIds = nodes.map((n) => n.id).filter((id) => reached.has(id));
  const reachedOutcomeIds = new Set(outcomes.map((o) => o.name).filter((n) => reached.has(n)));

  // Goto cycles: each outcome has at most one outgoing `goto` edge, so the
  // `goto` subgraph has out-degree <= 1 per node — a simple chain-walk with
  // a per-start visited set finds every simple cycle (self-loops included)
  // without needing full Tarjan SCC. `cycleNodeIds` dedupes cycles reached
  // by more than one tail so each cycle is recorded exactly once.
  const gotoNext = new Map();
  for (const e of edges) if (e.kind === "goto") gotoNext.set(e.source, e.target);

  const cycles = [];
  const cycleNodeIds = new Set();
  for (const o of outcomes) {
    const start = o.name;
    if (!reachedOutcomeIds.has(start) || cycleNodeIds.has(start)) continue;
    const path = [];
    const indexInPath = new Map();
    let cur = start;
    while (!indexInPath.has(cur) && !cycleNodeIds.has(cur) && gotoNext.has(cur)) {
      indexInPath.set(cur, path.length);
      path.push(cur);
      cur = gotoNext.get(cur);
    }
    if (indexInPath.has(cur)) {
      const members = new Set(path.slice(indexInPath.get(cur)));
      const nodeIds = outcomes.map((oc) => oc.name).filter((n) => members.has(n));
      cycles.push({ nodeIds, kind: "goto" });
      for (const n of members) cycleNodeIds.add(n);
    }
  }

  // Rescore feedback: informational, one record per reachable outcome whose
  // transition is `rescore` — every preset and the seed use `rescore`, so
  // this is the normal shape of a lifecycle policy, not a warning.
  for (const o of outcomes) {
    if (reachedOutcomeIds.has(o.name) && o.transition && o.transition.kind === "rescore") {
      cycles.push({ nodeIds: ["score", "policy_dispatch", o.name], kind: "rescore_feedback" });
    }
  }

  return { nodes, edges, reachableNodeIds, cycles };
}

// Emits the issue_lifecycle-mode loop YAML (Proposed Solution §2): a thin
// standalone loop that imports lib/policy-router.yaml, self-declares
// `parameters: { issue_id: {...} }` (not `with:` — that key is caller-side
// only, fsm/schema.py:684), and replaces the LLM rubric_score/policy_parse_scores
// pair with the deterministic `frontmatter_scores` fragment. Every verb state
// carries `on_error: failed`; `scope`/`pruning_profile_ok`/`on_max_steps`/
// `timeout` are all required for the zero-warnings AC (see the issue's
// 4th/5th-pass findings).
function _serializeIssueLifecycle(model) {
  _assertNoReservedTokens("issue_lifecycle", model);
  const out = [];
  const name = model.name || "issue-lifecycle-loop";
  out.push(`name: ${name}`);
  if (model.description) {
    out.push(`description: |`);
    out.push(_yamlBlockScalar(model.description, 2));
  }
  // FEAT-3504: declares the policy mode via the loop's existing `category`
  // field so `validate_policy_revision` (policy_revision.py) can accept
  // builder-emitted issue_lifecycle YAML — see `_SUPPORTED_MODES` there.
  out.push(`category: issue_lifecycle`);
  out.push(`max_steps: ${model.maxSteps != null ? model.maxSteps : 20}`);
  out.push("");
  out.push("import:");
  out.push("  - lib/policy-router.yaml");
  out.push("");
  out.push("context:");
  out.push(`  frontmatter_dimensions: ${_dq(serializeFrontmatterDimensions(model))}`);
  out.push(`  policy_rules: |`);
  out.push(_yamlBlockScalar(_serializeRulesText(model), 4));
  out.push("");
  out.push("parameters:");
  out.push("  issue_id:");
  out.push("    type: string");
  out.push("    required: true");
  out.push("");
  out.push(`scope: ["."]`);
  out.push("");
  out.push("# every verb is a /ll: skill; MR-12 would otherwise warn per verb state");
  out.push("pruning_profile_ok: true");
  out.push("");
  // ENH-3492: budget exhaustion now lands on the explicit needs_attention
  // failure terminal instead of the generic `failed` terminal.
  out.push("on_max_steps: needs_attention");
  out.push("");
  out.push("timeout: 14400");
  out.push("");
  out.push("initial: score");
  out.push("");
  out.push("states:");
  out.push("  score:");
  out.push("    fragment: frontmatter_scores");
  out.push("    next: policy_dispatch");
  out.push("    on_error: failed");
  out.push("");
  out.push("  policy_dispatch:");
  out.push("    fragment: policy_table_dispatch");
  out.push("    on_error: failed");
  out.push("    route:");
  const verbs = _emittedVerbs(model);
  for (const v of verbs) {
    out.push(`      ${v}: ${v}`);
  }
  // ENH-3492: dispatch route entries for author-selected destination
  // references only (rule target, fallback, or a verb's transition.kind) —
  // never solely because on_max_steps targets needs_attention.
  const dispatchedDestinations = _dispatchedDestinations(model);
  for (const d of dispatchedDestinations) {
    out.push(`      ${d}: ${d}`);
  }
  out.push(`      _: ${model.fallback || verbs[0] || "gate"}`);
  out.push(`      _error: failed`);
  out.push("");
  const outcomeMap = new Map();
  for (const o of model.outcomes || []) outcomeMap.set(o.name, o);
  for (const v of verbs) {
    const outcome = outcomeMap.get(v);
    for (const line of _outcomeStateLines(outcome, {
      doneState: "done",
      issueArg: true,
      mode: "issue_lifecycle",
    })) {
      out.push(line);
    }
    out.push(`    on_error: failed`);
    out.push("");
  }
  out.push("  done:");
  out.push("    terminal: true");
  out.push("");
  // ENH-3492: terminal blocks for dispatched destinations plus (always)
  // needs_attention — see _requiredTerminalBlocks's doc comment.
  const destMeta = new Map(LIFECYCLE_DESTINATIONS.map((d) => [d.name, d]));
  for (const name of _requiredTerminalBlocks(model)) {
    out.push(`  ${name}:`);
    out.push(`    terminal: true`);
    if (destMeta.get(name).failure) out.push(`    failure: true`);
    out.push("");
  }
  out.push("  failed:");
  out.push("    terminal: true");
  out.push("    failure: true");
  out.push("");
  return out.join("\n").replace(/\n+$/, "\n");
}

/**
 * Serialize a builder model to loop YAML text (deterministic). See the
 * model-shape contract in the file header.
 * @param {Object} model
 * @returns {string}
 */
export function serializeLoopYaml(model) {
  if (model && model.mode === "issue_lifecycle") {
    return _serializeIssueLifecycle(model);
  }
  if (model && model.mode === "rubric") {
    return _serializeRubric(model);
  }
  return _serializeDecisionTable(model);
}

// ===========================================================================
// Frontmatter Try-it mini-parser + encoder (FEAT-3474)
// ===========================================================================

// FEAT-3488: true when `value` is wrapped in one matching pair of quotes —
// gates the unsupported-subset rejects below so quoted literal text (e.g.
// `x: "{a: b}"`) stays ordinary string content, never a rejected construct.
function _isQuotedScalar(value) {
  if (value.length < 2) return false;
  const first = value[0];
  const last = value[value.length - 1];
  return (first === "'" && last === "'") || (first === '"' && last === '"');
}

function _stripMatchingQuotes(value) {
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === "'" && last === "'") || (first === '"' && last === '"')) {
      return value.slice(1, -1);
    }
  }
  return value;
}

// Strip a `#` comment from a raw (untrimmed) line — only when the `#` sits at
// line start or is preceded by whitespace, and only outside single/double
// quotes (BUG-3486 defect e). A quoted `#` is literal and left alone.
function _stripComment(raw) {
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
    } else if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
    } else if (ch === "#" && !inSingle && !inDouble && (i === 0 || /\s/.test(raw[i - 1]))) {
      return raw.slice(0, i);
    }
  }
  return raw;
}

// Split a flow-list's inner text on commas that are outside single/double
// quotes, then unquote each element (BUG-3486 defect e: a quoted comma like
// `[a, "b, c"]` must stay inside its element, not split it).
function _parseFlowList(inner) {
  if (inner.trim() === "") return [];
  const items = [];
  let cur = "";
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i];
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      cur += ch;
    } else if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      cur += ch;
    } else if (ch === "," && !inSingle && !inDouble) {
      items.push(_stripMatchingQuotes(cur.trim()));
      cur = "";
    } else {
      cur += ch;
    }
  }
  items.push(_stripMatchingQuotes(cur.trim()));
  return items;
}

/**
 * A minimal, pure YAML-frontmatter-subset reader for the Try-it panel.
 * Mirrors `parse_frontmatter`'s (BaseLoader) contract closely enough that
 * the emitted loop and Try-it never disagree on the seed rules: scalars stay
 * strings (never JS booleans/numbers — the boolean encoding rule is
 * string-truthiness, not a parser concern), one pair of matching quotes is
 * stripped, splitting is on the *first* `:` only (so `title: 'a: b'` and ISO
 * timestamps with `:` inside a quoted value work), `""`/`null`/`~` normalize
 * to `null` (absent), `status` synonyms are canonicalized exactly like
 * `STATUS_SYNONYMS`, and `---` fence lines are tolerated/ignored. Supports
 * `#` end-of-line comments (stripped when at line-start or preceded by
 * whitespace, outside quotes) and flow lists (`[a, "b, c"]`, quoted commas
 * kept literal) and dash lists (`- a` / `- b`).
 *
 * Anything the mini-parser cannot represent — a nested mapping, a
 * multi-line block scalar (`|`/`>`) continuation, or a YAML anchor/alias
 * (`&name` / `*name`) — raises rather than guessing (BUG-3486 defect e:
 * "reject rather than guess" for the unsupported subset). Non-goal: the
 * runtime scorer uses the full `parse_frontmatter`, not this mini-parser.
 *
 * Throws `Error("Can't read line N: <text>")` on the first unparseable or
 * unsupported line, matching the UI-Notes error format the hint text
 * surfaces verbatim.
 * @param {string} text
 * @returns {Record<string, string|string[]|null>}
 */
export function parseFrontmatterBlock(text) {
  const result = {};
  let currentListKey = null;
  let currentList = null;
  const lines = String(text).split("\n");
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = _stripComment(raw).trim();
    if (line === "") continue;
    if (/^-{3,}\s*$/.test(line)) continue; // --- fence, tolerated/ignored
    const isDashItem = line === "-" || line.startsWith("- ");
    if (isDashItem && currentListKey !== null) {
      const item = line === "-" ? "" : _stripMatchingQuotes(line.slice(2).trim());
      currentList.push(item);
      result[currentListKey] = currentList;
      continue;
    }
    const indent = raw.length - raw.replace(/^[ \t]+/, "").length;
    if (indent > 0) {
      // An indented line that isn't a recognized dash-list continuation:
      // a nested mapping, a block-scalar continuation, or similar — not a
      // representable construct.
      throw new Error(`Can't read line ${i + 1}: ${raw}`);
    }
    if (isDashItem) {
      // Orphan dash item — no preceding `key:` opened a list.
      throw new Error(`Can't read line ${i + 1}: ${raw}`);
    }
    const idx = line.indexOf(":");
    if (idx === -1) {
      throw new Error(`Can't read line ${i + 1}: ${raw}`);
    }
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    currentListKey = null;
    currentList = null;
    if (value === "") {
      // Might be the head of a dash-list on following lines; stays absent
      // (null) if no dash items follow before the next key.
      currentListKey = key;
      currentList = [];
      result[key] = null;
      continue;
    }
    if (value === "~" || /^null$/i.test(value)) {
      result[key] = null;
      continue;
    }
    if (value[0] === "&" || value[0] === "*") {
      // YAML anchor/alias — not representable by this mini-parser.
      throw new Error(`Can't read line ${i + 1}: ${raw}`);
    }
    // FEAT-3488: close the remaining unsupported-subset gaps — a nested flow
    // mapping (`{...}`), an explicit YAML tag (`!`/`!!str`), a bare block-
    // scalar indicator (`|`/`>`, with or without a chomping/indent suffix),
    // or a flow list missing its closing `]`. Only when unquoted — a quoted
    // literal containing these characters is ordinary text and stays valid.
    if (!_isQuotedScalar(value)) {
      if (value[0] === "{" || value[0] === "!") {
        throw new Error(`Can't read line ${i + 1}: ${raw}`);
      }
      if (/^[|>][+-]?\d*\s*$/.test(value)) {
        throw new Error(`Can't read line ${i + 1}: ${raw}`);
      }
      if (value[0] === "[" && !value.endsWith("]")) {
        throw new Error(`Can't read line ${i + 1}: ${raw}`);
      }
    }
    if (value.startsWith("[") && value.endsWith("]")) {
      result[key] = _parseFlowList(value.slice(1, -1));
      continue;
    }
    // A quoted empty scalar (`key: ""` / `key: ''`) normalizes to null too —
    // mirrors `_normalize_loaded_mapping`'s `value.lower() in ("null", "~", "")`
    // check, which runs *after* YAML has already resolved the quotes.
    const scalar = _stripMatchingQuotes(value);
    result[key] = scalar === "" ? null : scalar;
  }
  if (typeof result.status === "string") {
    result.status = STATUS_SYNONYMS_JS[result.status] ?? result.status;
  }
  return result;
}

/**
 * JS mirror of the Python `frontmatter_scores` fragment's
 * `encode_frontmatter_scores` — same Encoding Rules, same cases, keyed by
 * normalized dimension name (matching the `rubric-dim-<normalized-name>.txt`
 * filenames `policy_table_dispatch` reads). Values are always returned as
 * strings (the on-disk file contents are text; `policy_table_dispatch` does
 * its own float coercion) so Try-it's evaluator sees exactly what the
 * emitted loop's dispatch fragment would see.
 * @param {Record<string, unknown>} fm  parsed frontmatter (string/list/null values)
 * @param {Array<{name: string, type: string}>} dims
 * @returns {Record<string, string>}
 */
export function encodeFrontmatterScores(fm, dims) {
  const scores = {};
  const isTruthy = (raw) => {
    const norm = (raw == null ? "" : String(raw)).trim().toLowerCase();
    return norm === "true" || norm === "yes" || norm === "on" || norm === "1";
  };
  const listCount = (raw) => {
    if (raw == null) return 0;
    if (Array.isArray(raw)) return raw.length;
    return String(raw).trim() === "" ? 0 : 1;
  };
  for (const d of dims || []) {
    const rawKey = d.name;
    const normName = normalizeDimName(rawKey);
    // Derived dimension (BUG-3486: parity with Python's encode_frontmatter_scores,
    // frontmatter_scores.py:106-115) — triggered by raw_key === "priority_rank",
    // not by a dimension literally named "priority". Always reads the literal
    // "priority" frontmatter key, independent of whether a "priority" dimension
    // is also declared. Skips the generic type-switch below entirely.
    if (rawKey === "priority_rank") {
      const hasPriority = fm != null && Object.prototype.hasOwnProperty.call(fm, "priority");
      const rawPriority = hasPriority ? fm["priority"] : undefined;
      if (rawPriority !== undefined && rawPriority !== null) {
        const m = /^P(\d)$/.exec(String(rawPriority).trim());
        if (m) scores[normName] = m[1];
      }
      continue;
    }
    const has = fm != null && Object.prototype.hasOwnProperty.call(fm, rawKey);
    const raw = has ? fm[rawKey] : undefined;
    if (d.type === "boolean") {
      scores[normName] = isTruthy(raw) ? "100" : "0";
    } else if (d.type === "list") {
      scores[normName] = String(listCount(raw));
    } else if (d.type === "numeric") {
      if (raw === undefined || raw === null) continue;
      if (Array.isArray(raw)) {
        scores[normName] = String(raw.length);
        continue;
      }
      const s = String(raw).trim();
      if (s === "") continue;
      scores[normName] = s;
    } else if (d.type === "string") {
      if (raw === undefined || raw === null) continue;
      const s = String(raw).trim();
      if (s === "") continue;
      scores[normName] = s;
    }
  }
  return scores;
}

// ===========================================================================
// FEAT-3503: boundary suggestions and local issue-file import
// ===========================================================================

function _canonicalJson(value) {
  if (Array.isArray(value)) return "[" + value.map(_canonicalJson).join(",") + "]";
  if (value && typeof value === "object") {
    return (
      "{" +
      Object.keys(value)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + _canonicalJson(value[k]))
        .join(",") +
      "}"
    );
  }
  return JSON.stringify(value);
}

/**
 * Semantic identity of a scenario input: canonical (key-sorted) JSON of
 * `{mode, scores}` (rubric: `{mode, aggregate}`) taken from
 * `normalizeScenarioInput`. Raw key presence and text formatting are not part
 * of it — routing sees only the encoded scores — but numeric spelling is
 * (`"85"`, `"85.0"`, `"8.5e1"` stay distinct). Returns `null` when the input
 * does not normalize cleanly (invalid cases never participate in dedup).
 * @param {Object} model
 * @param {Object} input
 * @returns {string|null}
 */
export function scenarioSemanticKey(model, input) {
  const mode = model.mode || "decision_table";
  const n = normalizeScenarioInput(model, input);
  if (n.diagnostics.length) return null;
  if (mode === "rubric") return _canonicalJson({ mode, aggregate: n.aggregate });
  return _canonicalJson({ mode, scores: n.scores });
}

// Adjacent IEEE-754 doubles. May return +/-Infinity at the finite extrema;
// callers discard nonfinite results.
function _nextUp(x) {
  if (Number.isNaN(x) || x === Infinity) return x;
  if (x === 0) return Number.MIN_VALUE;
  const dv = new DataView(new ArrayBuffer(8));
  dv.setFloat64(0, x);
  dv.setBigInt64(0, dv.getBigInt64(0) + (x > 0 ? 1n : -1n));
  return dv.getFloat64(0);
}
function _nextDown(x) {
  return -_nextUp(-x);
}
export { _nextUp, _nextDown };

const _SUGGEST_LIST_CAP = 1000;
const _SKIP_DT_STRING = "unsupported-decision-table-string-dimension";
const _SKIP_NONFINITE = "nonfinite-literal";
const _SKIP_NO_WITNESS = "no-satisfying-witness";
const _SKIP_ROUNDTRIP = "serialization-round-trip-failed";

function _lifecycleSourceKey(dim) {
  return dim.name === "priority_rank" ? "priority" : dim.name;
}

/**
 * The frontmatter source keys the lifecycle model's dimensions read
 * (`priority_rank` reads `priority`).
 * @param {Object} model
 * @returns {string[]}
 */
export function lifecycleDimensionSourceKeys(model) {
  const keys = [];
  for (const d of model.dimensions || []) {
    const k = _lifecycleSourceKey(d);
    if (!keys.includes(k)) keys.push(k);
  }
  return keys;
}

// Quote a string scalar when the frontmatter mini-parser would otherwise
// mangle it (comments, splitting, null markers, unsupported leading chars).
function _fmScalar(value) {
  const s = String(value);
  if (/[\n\r]/.test(s)) throw new Error("multi-line scalar");
  const needsQuote =
    /[#:,"']/.test(s) ||
    /^[\[\-\s{!&*|>]/.test(s) ||
    /\s$/.test(s) ||
    s === "" ||
    /^(null|~)$/i.test(s);
  return needsQuote ? `"${s}"` : s;
}

function _serializeLifecycleFrontmatter(fields, order) {
  const lines = [];
  for (const key of order) {
    if (!Object.prototype.hasOwnProperty.call(fields, key)) continue;
    const v = fields[key];
    let text;
    if (Array.isArray(v)) text = "[" + v.map(_fmScalar).join(", ") + "]";
    else if (typeof v === "boolean") text = v ? "true" : "false";
    else if (typeof v === "number") text = String(v);
    else text = _fmScalar(v);
    lines.push(`${key}: ${text}`);
  }
  return lines.join("\n");
}
export { _serializeLifecycleFrontmatter };

function _suggestCore(model) {
  const mode = model.mode || "decision_table";
  const skips = [];
  const out = [];
  const { diagnostics, compiled } = _modelRoutingDiagnostics(model);
  if (diagnostics.length || !compiled) return { suggestions: [], skips };

  if (mode === "rubric") {
    const seen = new Set();
    const push = (aggregate, label) => {
      if (aggregate < 0 || aggregate > 100 || !Number.isInteger(aggregate)) return;
      const input = { aggregate };
      const key = scenarioSemanticKey(model, input);
      if (key == null || seen.has(key)) return;
      seen.add(key);
      const branch = traceModel(model, input).rubricBranch;
      out.push({
        key,
        name: `Rubric: aggregate ${aggregate}`,
        input,
        expectedTarget: null,
        reason: `${label}: aggregate ${aggregate} → ${branch} branch`,
      });
    };
    for (const [field, t] of [
      ["thresholdHigh", Number(model.thresholdHigh)],
      ["thresholdMedium", Number(model.thresholdMedium)],
    ]) {
      push(Math.ceil(t) - 1, `${field} ${t} just below`);
      if (Number.isInteger(t)) push(t, `${field} ${t} at`);
      push(Math.floor(t) + 1, `${field} ${t} just above`);
    }
    return { suggestions: out, skips };
  }

  const isLifecycle = mode === "issue_lifecycle";
  const dims = model.dimensions || [];
  const dimByNorm = new Map(dims.map((d) => [normalizeDimName(d.name), d]));
  const sourceKeyOf = (d) => (isLifecycle ? _lifecycleSourceKey(d) : normalizeDimName(d.name));
  const order = [];
  for (const d of dims) {
    const k = sourceKeyOf(d);
    if (!order.includes(k)) order.push(k);
  }
  const buildInput = (fields) => {
    if (!isLifecycle) return { values: { ...fields } };
    return { frontmatterText: _serializeLifecycleFrontmatter(fields, order) };
  };
  const scoresOf = (fields) => {
    let input;
    try {
      input = buildInput(fields);
    } catch (err) {
      return null;
    }
    const n = normalizeScenarioInput(model, input);
    return n.diagnostics.length ? null : n.scores;
  };
  const satisfies = (fields, preds) => {
    const scores = scoresOf(fields);
    return scores != null && preds.every((p) => evalPredicate(p, scores));
  };
  const domainOf = (groupDims) => {
    if (isLifecycle && groupDims.some((d) => d.name === "priority_rank")) return "priority";
    return groupDims[0].type;
  };
  const discrete = (domain) => domain === "priority" || domain === "list";

  const seen = new Set();
  const authoredCount = (model.rules || []).length;
  const ruleName = (i) => `Rule ${i + 1}`;
  const candidates = []; // {input, key, name, label, ruleIndex}
  const addCandidate = (fields, name, label, ruleIndex) => {
    let input;
    try {
      input = buildInput(fields);
    } catch (err) {
      return;
    }
    const key = scenarioSemanticKey(model, input);
    if (key == null || seen.has(key)) return;
    seen.add(key);
    candidates.push({ input, key, name, label, ruleIndex });
  };

  for (let ri = 0; ri < authoredCount; ri++) {
    const rule = compiled[ri];
    if (!rule || isCatchall(rule)) continue;
    const skip = (reason) => skips.push({ ruleIndex: ri, reason });
    // Group predicates by source field.
    const groups = new Map();
    for (const p of rule.predicates) {
      const d = dimByNorm.get(p.dim);
      const key = sourceKeyOf(d);
      if (!groups.has(key)) groups.set(key, { key, dims: [], preds: [] });
      const g = groups.get(key);
      if (!g.dims.includes(d)) g.dims.push(d);
      g.preds.push(p);
    }
    const fields = {};
    let skipReason = null;
    for (const g of groups.values()) {
      const domain = domainOf(g.dims);
      if (!isLifecycle && domain === "string") {
        skipReason = _SKIP_DT_STRING;
        break;
      }
      const numericLike = domain === "numeric" || domain === "list" || domain === "priority";
      const numericPreds = domain === "priority" ? g.preds.filter((p) => p.dim === "priority_rank") : g.preds;
      if (numericLike && numericPreds.some((p) => !Number.isFinite(Number(p.value)))) {
        skipReason = _SKIP_NONFINITE;
        break;
      }
      let cands = [];
      const lits = g.preds.map((p) => p.value);
      const finiteLits = numericLike ? numericPreds.map((p) => Number(p.value)) : [];
      if (domain === "boolean") {
        cands = [false, true];
      } else if (domain === "numeric") {
        const set = new Set([0]);
        if (!isLifecycle) {
          set.add(0);
          set.add(100);
        }
        for (const t of finiteLits) {
          set.add(t);
          for (const n of [_nextUp(t), _nextDown(t)]) if (Number.isFinite(n)) set.add(n);
        }
        cands = [...set]
          .filter((v) => isLifecycle || (v >= 0 && v <= 100))
          .sort((a, b) => Math.abs(a) - Math.abs(b) || a - b);
      } else if (domain === "list") {
        const set = new Set([0]);
        for (const t of finiteLits) {
          for (const n of [Math.floor(t), Math.ceil(t)]) {
            set.add(n - 1);
            set.add(n);
            set.add(n + 1);
          }
        }
        cands = [...set]
          .filter((n) => Number.isSafeInteger(n) && n >= 0 && n <= _SUGGEST_LIST_CAP)
          .sort((a, b) => a - b)
          .map((n) => Array.from({ length: n }, (_, i) => `item-${i + 1}`));
      } else if (domain === "priority") {
        cands = Array.from({ length: 10 }, (_, i) => `P${i}`);
      } else {
        const eq = g.preds.filter((p) => p.op === "==").map((p) => p.value);
        const excluded = new Set(lits);
        const notted = lits.map((l) => {
          let c = `not-${l}`;
          while (excluded.has(c)) c = `not-${c}`;
          return c;
        });
        cands = [...new Set([...eq, ...notted])];
      }
      const hit = cands.find((c) => satisfies({ [g.key]: c }, g.preds));
      if (hit === undefined) {
        skipReason = _SKIP_NO_WITNESS;
        break;
      }
      fields[g.key] = hit;
    }
    if (skipReason == null && !satisfies(fields, rule.predicates)) skipReason = _SKIP_ROUNDTRIP;
    if (skipReason != null) {
      skip(skipReason);
      continue;
    }
    addCandidate(fields, `${ruleName(ri)}: satisfying case`, `satisfies rule ${ri + 1}`, ri);

    // Boundary variants: one-unit probes of the witness per numeric predicate.
    for (const p of rule.predicates) {
      const d = dimByNorm.get(p.dim);
      const g = groups.get(sourceKeyOf(d));
      const domain = domainOf(g.dims);
      const isRankPred = domain === "priority" ? d.name === "priority_rank" : true;
      if (!(domain === "numeric" || domain === "list" || (domain === "priority" && isRankPred))) {
        continue;
      }
      const t = Number(p.value);
      const vals = discrete(domain)
        ? [Math.ceil(t) - 1, Number.isInteger(t) ? t : null, Math.floor(t) + 1]
        : [t - 1, t, t + 1];
      const words = ["just below", "at", "just above"];
      vals.forEach((v, vi) => {
        if (v == null || !Number.isFinite(v)) return;
        let raw;
        if (domain === "priority") {
          if (v < 0 || v > 9) return;
          raw = `P${v}`;
        } else if (domain === "list") {
          if (v < 0 || v > _SUGGEST_LIST_CAP) return;
          raw = Array.from({ length: v }, (_, i) => `item-${i + 1}`);
        } else {
          if (!isLifecycle && (v < 0 || v > 100)) return;
          raw = v;
        }
        addCandidate(
          { ...fields, [g.key]: raw },
          `${ruleName(ri)}: ${d.name} ${v}`,
          `rule ${ri + 1} boundary: ${d.name} ${words[vi]} ${t}`,
          ri
        );
      });
    }

    // Missing-field variants: omit the source key (never for lifecycle
    // boolean/list — the encoder always emits a score for those).
    const omitted = new Set();
    for (const p of rule.predicates) {
      if (p.op === "!=") continue;
      const d = dimByNorm.get(p.dim);
      if (isLifecycle && (d.type === "boolean" || d.type === "list")) continue;
      const key = sourceKeyOf(d);
      if (omitted.has(key)) continue;
      omitted.add(key);
      const rest = { ...fields };
      delete rest[key];
      addCandidate(rest, `${ruleName(ri)}: ${d.name} absent`, `rule ${ri + 1}: ${d.name} absent`, ri);
    }
  }

  // Trace-driven fallback: only when no candidate already reaches the derived
  // fallback, and only if the all-omitted input itself does.
  const isDerived = (input) => {
    const m = traceModel(model, input).match;
    return !!m && m.isFallback && m.ruleIndex === -1;
  };
  if (_hasDerivedFallback(model) && !candidates.some((c) => isDerived(c.input))) {
    const input = buildInput({});
    const key = scenarioSemanticKey(model, input);
    if (key != null && !seen.has(key) && isDerived(input)) {
      seen.add(key);
      candidates.push({
        input,
        key,
        name: "Fallback: all fields absent",
        label: "all fields absent (fallback)",
        ruleIndex: -1,
      });
    }
  }

  for (const c of candidates) {
    const m = traceModel(model, c.input).match;
    let reason;
    if (!m || m.target == null) {
      reason = `${c.label} → no match`;
    } else {
      reason = `${c.label} → ${m.target}`;
      if (c.ruleIndex >= 0 && m.ruleIndex !== c.ruleIndex) {
        reason += m.ruleIndex === -1 ? " (won by fallback)" : ` (won by rule ${m.ruleIndex + 1})`;
      }
    }
    out.push({ key: c.key, name: c.name, input: c.input, expectedTarget: null, reason });
  }
  return { suggestions: out, skips };
}

/**
 * Deterministic, deduplicated, unasserted boundary-case suggestions for the
 * model's authored rules (per rule: a satisfying witness, one-unit boundary
 * probes per numeric predicate, and missing-field variants) plus a
 * trace-driven fallback case; rubric mode yields integer neighbours of both
 * thresholds. Every suggestion normalizes cleanly and carries
 * `expectedTarget: null`. Empty for a routing-invalid model.
 * @param {Object} model
 * @returns {Array<{key: string, name: string, input: Object, expectedTarget: null, reason: string}>}
 */
export function suggestScenarios(model) {
  return _suggestCore(model).suggestions;
}

/**
 * Rules `suggestScenarios` skipped, each with a named reason
 * (`unsupported-decision-table-string-dimension`, `nonfinite-literal`,
 * `no-satisfying-witness`, `serialization-round-trip-failed`).
 * @param {Object} model
 * @returns {Array<{ruleIndex: number, reason: string}>}
 */
export function _suggestionSkips(model) {
  return _suggestCore(model).skips;
}

/**
 * Return the contents of the leading `---`-delimited frontmatter block of a
 * full issue Markdown file (BOM and CRLF tolerated); the body is never
 * inspected. Throws a diagnostic naming the defect otherwise.
 * @param {string} text
 * @returns {string}
 */
export function extractIssueFrontmatter(text) {
  let s = String(text);
  if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
  const lines = s.replace(/\r\n?/g, "\n").split("\n");
  if (!/^---\s*$/.test(lines[0])) {
    throw new Error("Missing opening frontmatter fence: the file must start with a `---` line.");
  }
  for (let i = 1; i < lines.length; i++) {
    if (/^---\s*$/.test(lines[i])) return lines.slice(1, i).join("\n");
  }
  throw new Error("Unclosed frontmatter fence: no closing `---` line found.");
}

const _TOP_KEY_RE = /^[^\s#\-][^:]*:/;

/**
 * Drop multi-line continuation lines (indented lines and block-scalar bodies)
 * under top-level keys that are NOT routing-dimension source keys, so
 * `parseFrontmatterBlock` never sees them. A bare `|`/`>` indicator on such a
 * key is dropped too (the key normalizes to null). Lines under dimension keys
 * pass through untouched. Pure; never throws.
 * @param {string} text
 * @param {Iterable<string>} dimensionSourceKeys
 * @returns {string}
 */
export function dropNonDimensionContinuations(text, dimensionSourceKeys) {
  const keys = new Set(dimensionSourceKeys);
  const out = [];
  let dropping = false;
  for (const line of String(text).split("\n")) {
    if (_TOP_KEY_RE.test(line)) {
      const idx = line.indexOf(":");
      const key = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim();
      dropping = !keys.has(key);
      if (dropping && /^[|>][+-]?\d*$/.test(value)) {
        out.push(`${line.slice(0, idx)}:`);
      } else {
        out.push(line);
      }
      continue;
    }
    if (dropping && /^\s+\S/.test(line)) continue;
    out.push(line);
  }
  return out.join("\n");
}

/**
 * Turn a full local issue file into an unasserted lifecycle scenario:
 * `extractIssueFrontmatter` → `dropNonDimensionContinuations` →
 * `parseFrontmatterBlock` → `normalizeScenarioInput`. Throws an Error whose
 * message contains `frontmatter`/`fence`; nothing is mutated.
 * @param {Object} model  the lifecycle model
 * @param {string} fileText
 * @param {string} fileName
 * @returns {{name: string, input: {frontmatterText: string}}}
 */
export function buildImportedScenario(model, fileText, fileName) {
  const block = extractIssueFrontmatter(fileText);
  const frontmatterText = dropNonDimensionContinuations(block, lifecycleDimensionSourceKeys(model));
  let fm;
  try {
    fm = parseFrontmatterBlock(frontmatterText);
  } catch (err) {
    const m = /^Can't read line (\d+):/.exec(err.message);
    if (m) {
      const lines = frontmatterText.split("\n");
      for (let i = Number(m[1]) - 1; i >= 0; i--) {
        if (_TOP_KEY_RE.test(lines[i])) {
          const key = lines[i].slice(0, lines[i].indexOf(":")).trim();
          throw new Error(
            `Frontmatter: multi-line value under routing field \`${key}\` is not supported — ${err.message}`
          );
        }
      }
    }
    throw new Error(`Frontmatter: ${err.message}`);
  }
  const input = { frontmatterText };
  const n = normalizeScenarioInput(model, input);
  if (n.diagnostics.length) {
    throw new Error(`Frontmatter: ${n.diagnostics.map((d) => d.message).join(" ")}`);
  }
  const id = typeof fm.id === "string" && fm.id.trim() ? fm.id.trim() : null;
  return { name: id || fileName, input };
}

/**
 * ENH-3507: draft/meta/issue-selection storage with injected dependencies.
 * Offline (`connectedContext == null`) keys are `ll-policy-builder-draft-<mode>`
 * and `ll-policy-builder-meta`; connected keys are namespaced by
 * `connectedContext.workspaceId`. Unscoped data is never migrated. Every storage
 * call is guarded: only a `persistDraft` failure calls `warn` (once per
 * instance); everything else fails silently. `storage == null` (blocked) reads
 * as empty and fails writes.
 * @param {{storage: ?Object, connectedContext: ?{workspaceId: string}, warn: function(): void}} deps
 * @returns {Object}
 */
export function createBuilderStorage(deps) {
  const { storage, connectedContext, warn } = deps || {};
  const wsId = connectedContext && connectedContext.workspaceId ? connectedContext.workspaceId : null;
  const draftKey = (mode) =>
    wsId ? `ll-policy-builder-draft-${wsId}-${mode}` : `ll-policy-builder-draft-${mode}`;
  const metaKey = wsId ? `ll-policy-builder-meta-${wsId}` : "ll-policy-builder-meta";
  const issueKey = wsId ? `ll-policy-builder-issue-${wsId}` : null;
  let warned = false;

  function readJson(key) {
    try {
      const raw = storage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function persistDraft(mode, model, scenarios) {
    try {
      storage.setItem(draftKey(mode), JSON.stringify({ model, scenarios: scenarios || [] }));
    } catch (e) {
      if (!warned) {
        warned = true;
        try {
          if (typeof warn === "function") warn();
        } catch (e2) { /* ignore */ }
      }
    }
  }

  return {
    persistDraft,
    persistAllDrafts(drafts) {
      Object.keys(drafts).forEach((mode) =>
        persistDraft(mode, drafts[mode].model, drafts[mode].scenarios || [])
      );
    },
    clearDraftsExcept(keepModes, allModes) {
      for (const mode of allModes) {
        if (!keepModes.has(mode)) {
          try {
            storage.removeItem(draftKey(mode));
          } catch (e) { /* ignore */ }
        }
      }
    },
    persistMeta(meta) {
      try {
        storage.setItem(metaKey, JSON.stringify(meta));
        return true;
      } catch (e) {
        return false;
      }
    },
    readDraft(mode) {
      return readJson(draftKey(mode));
    },
    readMeta() {
      return readJson(metaKey);
    },
    readIssueSelection() {
      return issueKey ? readJson(issueKey) : null;
    },
    writeIssueSelection(issueId) {
      if (!issueKey) return;
      try {
        if (issueId == null) storage.removeItem(issueKey);
        else storage.setItem(issueKey, JSON.stringify({ issueId }));
      } catch (e) { /* ignore */ }
    },
  };
}

// ---------------------------------------------------------------------------
// FEAT-3505: submission controller (hash helper, storage-backed request records,
// delivery states, polling). Every environment dependency is injected; the
// template only binds DOM events/rendering to it.
// ---------------------------------------------------------------------------

/** Queue status → display label (all seven `QUEUE_STATUSES`). */
export const QUEUE_STATUS_LABELS = {
  awaiting_approval: "Awaiting approval",
  pending: "Approved — waiting to run",
  running: "Running",
  done: "Done",
  failed: "Failed",
  dead_letter: "Failed — moved to dead letter",
  cancelled: "Rejected / cancelled by host",
};
/** Mirrors `little_loops.queue_store.QUEUE_TERMINAL_STATUSES`. */
export const QUEUE_TERMINAL_STATUSES = ["done", "failed", "dead_letter", "cancelled"];
const _RUN_REQUEST_MAX_BYTES = 1048576;
const _PROJECT_ID_MAX_CODE_POINTS = 128;
const _PLACEHOLDER_REQUEST_ID = "00000000-0000-4000-8000-000000000000";
const _REJECTION_CODES = new Set([
  "bad_request", "body_too_large", "revision_mismatch", "wrong_workspace",
  "request_conflict", "issue_not_found", "validation_failed",
]);
const _RESOLVED_HISTORY_LIMIT = 5;
const _INACTIVE_PROJECT_LIMIT = 3;

/** Human label for a queue status; an unrecognized status is shown verbatim. */
export function queueStatusLabel(status) {
  return Object.prototype.hasOwnProperty.call(QUEUE_STATUS_LABELS, status)
    ? QUEUE_STATUS_LABELS[status]
    : String(status);
}

/**
 * Lowercase-hex SHA-256 of the UTF-8 encoding of `text` (matches Python
 * `hashlib.sha256(text.encode("utf-8"))`).
 * @param {string} text
 * @param {?{digest: function}} subtle Injected; defaults to `globalThis.crypto.subtle`.
 * @returns {Promise<string>}
 */
export async function sha256Hex(text, subtle) {
  const s = subtle || (globalThis.crypto && globalThis.crypto.subtle);
  if (!s) throw new Error("crypto.subtle is unavailable");
  const digest = await s.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Number of Unicode code points (Python `len`), not UTF-16 code units. */
export function codePointLength(text) {
  return [...text].length;
}

/**
 * True when `text` is well-formed UTF-16. `useNative` selects
 * `String.prototype.isWellFormed` when available; otherwise (or when false) a
 * code-unit scan runs — never a silent bypass.
 */
export function isWellFormedUtf16(text, useNative = true) {
  if (useNative && typeof text.isWellFormed === "function") return text.isWellFormed();
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const n = text.charCodeAt(i + 1);
      if (!(n >= 0xdc00 && n <= 0xdfff)) return false;
      i++;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function _utf8Length(text) {
  return new TextEncoder().encode(text).length;
}

/**
 * Submission state machine for the connected policy builder.
 * @param {Object} deps {fetch, storage, subtle, setTimeout, clearTimeout, randomUUID,
 *   makeAbortController, connectedContext, ensureDocumentIdentity, requestTimeoutMs,
 *   submissionBudgetBytes, now}
 * @returns {Object}
 */
export function createSubmissionController(deps) {
  const d = deps || {};
  const ws = d.connectedContext && d.connectedContext.workspaceId ? d.connectedContext.workspaceId : null;
  const storage = d.storage || null;
  const setT = d.setTimeout || ((fn, ms) => globalThis.setTimeout(fn, ms));
  const clearT = d.clearTimeout || ((h) => globalThis.clearTimeout(h));
  const timeoutMs = d.requestTimeoutMs == null ? 30000 : d.requestTimeoutMs;
  const budgetBytes = d.submissionBudgetBytes == null ? 3 * 1024 * 1024 : d.submissionBudgetBytes;
  const now = d.now || (() => new Date().toISOString());
  const recPrefix = `ll-policy-builder-submission-${ws}-`;
  const idxPrefix = `ll-policy-builder-submissions-${ws}-`;
  const recKey = (projectId, requestId) => `${recPrefix}${projectId}-${requestId}`;
  const idxKey = (projectId) => `${idxPrefix}${projectId}`;

  let ctx = { projectId: null, issueId: null, mode: null };
  let reviewGen = 0;
  let docGen = 0;
  let opSeq = 0;
  let review = { status: "none" };
  let draftEdited = false;
  let issues = { status: "idle", list: [], error: null };
  let sub = null; // {record, queueStatus, readback, notFound, missing, conflict, poll, pollNote}
  let history = [];
  let notices = [];
  let submitting = false;
  let pollTimer = null;
  let readHandle = null;
  let issuesHandle = null;
  let postHandle = null;
  let disposed = false;
  const listeners = new Set();

  // ---- state exposure -----------------------------------------------------
  function availability() {
    if (!ws) {
      return { ok: false, reason: "Connected submission is available only on the page served by ll-artifact serve --policy-builder." };
    }
    if (!storage || typeof storage.getItem !== "function") {
      return { ok: false, reason: "Browser storage is unavailable, so a request cannot be saved before it is sent." };
    }
    if (!d.subtle || typeof d.fetch !== "function" || typeof d.randomUUID !== "function") {
      return { ok: false, reason: "This page lacks the secure-context features needed to submit (open it from the served URL)." };
    }
    if (ctx.mode !== "issue_lifecycle") {
      return { ok: false, reason: "Switch to the issue lifecycle mode to submit a policy." };
    }
    return { ok: true, reason: null };
  }

  function identityOf(record) {
    return record.kind === "full"
      ? {
          requestId: record.envelope.requestId, projectId: record.envelope.projectId,
          workspaceId: record.envelope.workspaceId, issueId: record.envelope.issueId,
          revisionId: record.envelope.revisionId, yamlByteLength: record.yamlByteLength,
        }
      : record.identity;
  }

  function viewOf(s) {
    if (!s) return null;
    const id = identityOf(s.record);
    const st = s.queueStatus;
    const runCurrent = st === "running" || QUEUE_TERMINAL_STATUSES.includes(st);
    const rb = s.readback || {};
    const result = rb.result === undefined ? null : rb.result;
    const prevResult = result && typeof result === "object" && Object.prototype.hasOwnProperty.call(result, "previous");
    return {
      requestId: id.requestId, projectId: id.projectId, issueId: id.issueId, revisionId: id.revisionId,
      revisionShort: id.revisionId.slice(0, 12), yamlByteLength: id.yamlByteLength,
      delivery: s.record.delivery,
      warnings: s.record.delivery.warnings === undefined ? null : s.record.delivery.warnings,
      warningsUnavailable: s.record.delivery.state === "accepted" && s.record.delivery.warnings === undefined,
      queueId: s.record.delivery.queueId || null,
      queueStatus: st || null,
      statusLabel: st ? queueStatusLabel(st) : null,
      terminal: QUEUE_TERMINAL_STATUSES.includes(st),
      bindings: rb.bindings || null,
      loopInstanceId: rb.loopInstanceId || null,
      runDir: rb.runDir || null,
      runIsCurrent: runCurrent,
      result: prevResult ? null : result,
      previousResult: prevResult ? result.previous : null,
      notFound: !!s.notFound, missing: !!s.missing, conflict: s.conflict || null,
      poll: s.poll, pollNote: s.pollNote || null,
      canRetry: s.record.delivery.state === "outcome_unknown" && !!s.notFound && s.record.kind === "full",
    };
  }

  function getState() {
    const snap = review.snapshot || null;
    return {
      availability: availability(),
      context: { ...ctx },
      issues: { ...issues, list: issues.list.slice() },
      review: {
        status: review.status, reason: review.reason || null,
        snapshot: snap, revisionShort: snap && snap.revisionId ? snap.revisionId.slice(0, 12) : null,
      },
      draftEdited,
      submission: viewOf(sub),
      history: history.slice(),
      notices: notices.slice(),
      busy: submitting || review.status === "hashing",
      submitting,
    };
  }

  function emit() {
    if (disposed) return;
    for (const cb of Array.from(listeners)) {
      try { cb(getState()); } catch (e) { /* listener errors never break the controller */ }
    }
  }

  function notify(text) {
    if (!notices.includes(text)) notices.push(text);
  }

  // ---- storage ------------------------------------------------------------
  function encode(value) {
    return JSON.stringify(value);
  }

  function writeRecord(record) {
    const id = identityOf(record);
    try {
      storage.setItem(recKey(id.projectId, id.requestId), encode(record));
      return true;
    } catch (e) {
      return false;
    }
  }

  function removeKey(key) {
    try {
      storage.removeItem(key);
      return true;
    } catch (e) {
      return false;
    }
  }

  function writeIndex(idx) {
    try {
      storage.setItem(idxKey(idx.projectId), encode(idx));
      return true;
    } catch (e) {
      return false;
    }
  }

  function readIndex(projectId) {
    try {
      const raw = storage.getItem(idxKey(projectId));
      if (raw == null) return { ok: true, idx: null };
      const idx = JSON.parse(raw);
      return _validIndex(idx, ws, projectId) ? { ok: true, idx } : { ok: false };
    } catch (e) {
      return { ok: false };
    }
  }

  function _validIdentityFields(id) {
    return id && typeof id === "object" &&
      ["requestId", "projectId", "workspaceId", "issueId", "revisionId"].every((k) => typeof id[k] === "string" && id[k]);
  }

  function _validRecord(rec) {
    if (!rec || rec.v !== 1 || !rec.delivery || typeof rec.delivery.state !== "string") return null;
    if (rec.kind === "full") {
      if (!["prepared", "outcome_unknown"].includes(rec.delivery.state)) return null;
      if (!_validIdentityFields(rec.envelope) || typeof rec.envelope.yaml !== "string") return null;
      if (rec.envelope.workspaceId !== ws) return null;
      return identityOf(rec);
    }
    if (rec.kind === "compact") {
      if (!["accepted", "rejected"].includes(rec.delivery.state)) return null;
      if (!_validIdentityFields(rec.identity) || rec.identity.workspaceId !== ws) return null;
      return rec.identity;
    }
    return null;
  }

  function _validIndex(idx, wsId, projectId) {
    return !!idx && typeof idx === "object" && idx.workspaceId === wsId &&
      typeof idx.projectId === "string" && idx.projectId && (projectId == null || idx.projectId === projectId) &&
      (idx.activeRequestId === null || typeof idx.activeRequestId === "string") &&
      Array.isArray(idx.recent) && idx.recent.every((r) => typeof r === "string");
  }

  /** Snapshot this workspace's submission keys; any malformed/unreadable entry fails the scan. */
  function enumerate() {
    const records = [];
    const indexes = [];
    let total = 0;
    try {
      const keys = [];
      const n = storage.length;
      for (let i = 0; i < n; i++) {
        const k = storage.key(i);
        if (typeof k === "string" && (k.startsWith(recPrefix) || k.startsWith(idxPrefix))) keys.push(k);
      }
      for (const key of keys) {
        const raw = storage.getItem(key);
        if (raw == null) continue;
        let val;
        try { val = JSON.parse(raw); } catch (e) { return { ok: false, error: `Submission storage entry ${key} is malformed.` }; }
        const size = 2 * (key.length + raw.length);
        if (key.startsWith(recPrefix)) {
          const id = _validRecord(val);
          if (!id || recKey(id.projectId, id.requestId) !== key) {
            return { ok: false, error: `Submission storage entry ${key} does not match its contents.` };
          }
          records.push({ key, rec: val, id, size });
        } else {
          if (!_validIndex(val, ws, null) || idxKey(val.projectId) !== key) {
            return { ok: false, error: `Submission index ${key} does not match its contents.` };
          }
          indexes.push({ key, idx: val, size });
        }
        total += size;
      }
    } catch (e) {
      return { ok: false, error: `Submission storage could not be read: ${e && e.message ? e.message : e}` };
    }
    return { ok: true, records, indexes, total };
  }

  const _isResolved = (rec) => rec.kind === "compact";

  /** Remove a never-attempted `prepared` record: index references first, then the record. */
  function discardPrepared(projectId, requestId) {
    const r = readIndex(projectId);
    if (!r.ok) {
      notify("Submission storage index could not be read; cleanup stopped.");
      return false;
    }
    if (r.idx) {
      const idx = { ...r.idx, recent: r.idx.recent.filter((x) => x !== requestId) };
      let changed = idx.recent.length !== r.idx.recent.length;
      if (idx.activeRequestId === requestId) {
        idx.activeRequestId = idx.recent.length ? idx.recent.shift() : null;
        changed = true;
      }
      if (changed) {
        idx.updatedAt = now();
        if (!writeIndex(idx)) {
          notify("Submission storage index could not be updated; cleanup stopped.");
          return false;
        }
      }
    }
    if (!removeKey(recKey(projectId, requestId))) {
      notify("A discarded request could not be removed from browser storage; it will be retried.");
      return false;
    }
    return true;
  }

  /** Boot/Open cleanup: discard prepared, adopt orphans, drop dangling refs. */
  function recoverStorage() {
    const en = enumerate();
    if (!en.ok) {
      notify(en.error);
      return false;
    }
    const projects = new Set([...en.records.map((r) => r.id.projectId), ...en.indexes.map((i) => i.idx.projectId)]);
    for (const pid of projects) {
      const recs = en.records.filter((r) => r.id.projectId === pid);
      const existing = en.indexes.find((i) => i.idx.projectId === pid);
      const idx = existing ? { ...existing.idx, recent: existing.idx.recent.slice() } : null;
      const byId = new Map(recs.map((r) => [r.id.requestId, r]));
      const prepared = recs.filter((r) => r.rec.delivery.state === "prepared");
      for (const p of prepared) {
        if (!discardPrepared(pid, p.id.requestId)) return false;
        byId.delete(p.id.requestId);
        notify("A request that was prepared but never sent was discarded — review the policy again before submitting.");
      }
      const fresh = readIndex(pid);
      if (!fresh.ok) {
        notify("Submission storage index could not be read; cleanup stopped.");
        return false;
      }
      let cur = fresh.idx ? { ...fresh.idx, recent: fresh.idx.recent.slice() } : null;
      let changed = false;
      if (cur) {
        const before = [cur.activeRequestId, ...cur.recent].filter(Boolean).length;
        cur.recent = cur.recent.filter((x) => byId.has(x));
        if (cur.activeRequestId && !byId.has(cur.activeRequestId)) {
          cur.activeRequestId = cur.recent.length ? cur.recent.shift() : null;
        }
        if ([cur.activeRequestId, ...cur.recent].filter(Boolean).length !== before) changed = true;
      }
      const referenced = new Set(cur ? [cur.activeRequestId, ...cur.recent].filter(Boolean) : []);
      for (const [rid] of byId) {
        if (referenced.has(rid)) continue;
        if (!cur) cur = { workspaceId: ws, projectId: pid, activeRequestId: null, recent: [], updatedAt: now() };
        if (cur.activeRequestId == null) cur.activeRequestId = rid;
        else cur.recent.push(rid);
        referenced.add(rid);
        changed = true;
        notify("Recovered a saved request whose index entry was missing; its status will be checked.");
      }
      if (cur && changed) {
        cur.updatedAt = now();
        if (!writeIndex(cur)) {
          notify("Submission storage index could not be updated; cleanup stopped.");
          return false;
        }
      }
      if (cur && cur.activeRequestId == null && !cur.recent.length && !byId.size) removeKey(idxKey(pid));
    }
    return pruneResolved();
  }

  /** Prune resolved history only (never the active or an unresolved record). */
  function pruneResolved() {
    const en = enumerate();
    if (!en.ok) {
      notify(en.error);
      return false;
    }
    const recById = (pid) => new Map(en.records.filter((r) => r.id.projectId === pid).map((r) => [r.id.requestId, r]));
    const inactive = [];
    for (const { idx } of en.indexes) {
      const recs = recById(idx.projectId);
      const resolvedRecent = idx.recent.filter((rid) => recs.get(rid) && _isResolved(recs.get(rid).rec));
      if (resolvedRecent.length > _RESOLVED_HISTORY_LIMIT) {
        const drop = new Set(resolvedRecent.slice(_RESOLVED_HISTORY_LIMIT));
        const next = { ...idx, recent: idx.recent.filter((x) => !drop.has(x)), updatedAt: idx.updatedAt };
        if (!writeIndex(next)) {
          notify("Submission storage index could not be updated; cleanup stopped.");
          return false;
        }
        for (const rid of drop) removeKey(recKey(idx.projectId, rid));
      }
      if (idx.projectId !== ctx.projectId) {
        const all = [idx.activeRequestId, ...idx.recent].filter(Boolean);
        if (all.length && all.every((rid) => recs.get(rid) && _isResolved(recs.get(rid).rec))) inactive.push(idx);
      }
    }
    inactive.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : 0));
    for (const idx of inactive.slice(_INACTIVE_PROJECT_LIMIT)) {
      const all = [idx.activeRequestId, ...idx.recent].filter(Boolean);
      if (!removeKey(idxKey(idx.projectId))) {
        notify("Submission storage index could not be updated; cleanup stopped.");
        return false;
      }
      for (const rid of all) removeKey(recKey(idx.projectId, rid));
    }
    return true;
  }

  // ---- network ------------------------------------------------------------
  /** One deadline-bound request; settles even if fetch/body ignore abort. */
  function request(url, init) {
    let settle = () => {};
    let ac = null;
    const abort = () => {
      try { if (ac) ac.abort(); } catch (e) { /* best effort */ }
    };
    const promise = new Promise((resolve) => {
      let done = false;
      let timer = null;
      settle = (v) => {
        if (done) return;
        done = true;
        if (timer != null) clearT(timer);
        resolve(v);
      };
      try { ac = d.makeAbortController ? d.makeAbortController() : null; } catch (e) { ac = null; }
      timer = setT(() => { settle({ kind: "timeout" }); abort(); }, timeoutMs);
      (async () => {
        try {
          const resp = await d.fetch(url, { ...init, signal: ac ? ac.signal : undefined });
          const ct = (resp.headers && typeof resp.headers.get === "function" && resp.headers.get("content-type")) || "";
          const text = await resp.text();
          if (!/json/i.test(ct)) return settle({ kind: "transport", status: resp.status, error: "The server returned a non-JSON response." });
          let body;
          try { body = JSON.parse(text); } catch (e) { return settle({ kind: "transport", status: resp.status, error: "The response could not be decoded." }); }
          settle({ kind: "json", status: resp.status, body });
        } catch (e) {
          settle({ kind: "transport", error: e && e.message ? e.message : String(e) });
        }
      })();
    });
    return { promise, cancel() { settle({ kind: "aborted" }); abort(); } };
  }

  // ---- issues -------------------------------------------------------------
  async function loadIssues() {
    if (disposed) return;
    if (issuesHandle) issuesHandle.cancel();
    const h = request("./issues", { method: "GET", cache: "no-store" });
    issuesHandle = h;
    issues = { ...issues, status: "loading", error: null };
    emit();
    const res = await h.promise;
    if (issuesHandle !== h || disposed) return;
    issuesHandle = null;
    if (res.kind === "json" && res.status === 200 && res.body && Array.isArray(res.body.issues)) {
      issues = {
        status: "ready", error: null,
        list: res.body.issues.map((i) => ({ id: i.id, title: i.title, priority: i.priority, status: i.status })),
      };
    } else {
      const msg = res.kind === "timeout"
        ? "Loading issues timed out."
        : res.kind === "json" && res.body && res.body.error ? res.body.error.message : "Could not reach the server to load issues.";
      issues = { ...issues, status: "error", error: msg };
    }
    emit();
  }

  // ---- delivery transitions -------------------------------------------------
  function compact(record, delivery) {
    return { v: 1, kind: "compact", identity: identityOf(record), delivery };
  }

  /** Apply a delivery transition; compaction failure keeps the prior full record in storage. */
  function applyDelivery(record, delivery) {
    const next = record.kind === "full" && ["accepted", "rejected"].includes(delivery.state)
      ? compact(record, delivery)
      : { ...record, delivery };
    const persisted = writeRecord(next);
    if (!persisted) notify("The response could not be saved; it will be re-checked after reload.");
    if (sub && identityOf(sub.record).requestId === identityOf(record).requestId) {
      sub.record = next;
    }
    return next;
  }

  function classifyPost(res, record) {
    if (res.kind === "json") {
      const b = res.body || {};
      if (res.status >= 200 && res.status < 300 && typeof b.queueId === "string") {
        const delivery = { state: "accepted", queueId: b.queueId };
        if (b.created !== false && Array.isArray(b.warnings)) delivery.warnings = b.warnings;
        else if (b.created !== false) delivery.warnings = [];
        return applyDelivery(record, delivery);
      }
      if (res.status >= 400 && res.status < 500 && b.error && _REJECTION_CODES.has(b.error.code)) {
        const e = b.error;
        const error = { code: e.code, message: e.message || "" };
        if (e.errors) error.errors = e.errors;
        if (e.warnings) error.warnings = e.warnings;
        return applyDelivery(record, { state: "rejected", error });
      }
    }
    return record; // network loss / non-JSON / 5xx / timeout: outcome stays unknown
  }

  async function sendPost(record) {
    const env = record.envelope;
    const gen = docGen;
    const h = request("./run-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({
        requestId: env.requestId, projectId: env.projectId, workspaceId: env.workspaceId,
        revisionId: env.revisionId, yaml: env.yaml, issueId: env.issueId,
      }),
    });
    postHandle = h;
    submitting = true;
    emit();
    const res = await h.promise;
    if (postHandle === h) postHandle = null;
    submitting = false;
    if (disposed) return;
    const next = classifyPost(res, record);
    if (res.kind === "timeout") notify("The request timed out; check its status before sending again.");
    else if (res.kind === "transport") notify("Could not confirm the request was received; check its status before sending again.");
    if (sub && identityOf(sub.record).requestId === env.requestId) {
      if (next.delivery.state === "accepted" && gen === docGen) {
        sub.poll = "active";
        schedulePoll(2000);
      } else if (next.delivery.state === "outcome_unknown") {
        sub.poll = "stopped";
      }
    }
    emit();
  }

  // ---- readback / polling -----------------------------------------------------
  function clearPoll() {
    if (pollTimer != null) { clearT(pollTimer); pollTimer = null; }
  }

  function schedulePoll(ms) {
    clearPoll();
    if (disposed || !sub) return;
    const gen = docGen;
    const s = sub;
    pollTimer = setT(() => {
      pollTimer = null;
      if (gen !== docGen || sub !== s) return;
      readback(s, false);
    }, ms);
  }

  async function readback(s, manual) {
    if (disposed || !s || readHandle) return;
    const id = identityOf(s.record);
    if (s.record.delivery.state === "rejected") return;
    const gen = docGen;
    const h = request(`./run-request/${encodeURIComponent(id.requestId)}?workspaceId=${encodeURIComponent(ws)}`, {
      method: "GET", cache: "no-store",
    });
    readHandle = h;
    if (manual) { s.poll = "active"; s.pollNote = null; emit(); }
    const res = await h.promise;
    if (readHandle === h) readHandle = null;
    if (gen !== docGen || sub !== s || disposed) return;
    applyReadback(s, res);
    emit();
  }

  function applyReadback(s, res) {
    const id = identityOf(s.record);
    if (res.kind === "json" && res.status === 200 && res.body && res.body.bindings) {
      const b = res.body;
      if (b.bindings.issueId !== id.issueId || b.bindings.revisionId !== id.revisionId) {
        s.conflict = "The host has a request with this ID bound to a different issue or revision.";
        if (s.record.delivery.state === "outcome_unknown") {
          applyDelivery(s.record, { state: "rejected", error: { code: "request_conflict", message: s.conflict } });
        }
        s.poll = "stopped";
        return;
      }
      s.conflict = null;
      s.notFound = false;
      s.missing = false;
      if (s.record.delivery.state === "outcome_unknown") {
        applyDelivery(s.record, { state: "accepted", queueId: b.queueId });
      }
      s.queueStatus = b.status;
      s.readback = { bindings: b.bindings, loopInstanceId: b.loopInstanceId, runDir: b.runDir, result: b.result };
      s.pollNote = null;
      if (QUEUE_TERMINAL_STATUSES.includes(b.status)) {
        s.poll = "stopped";
        clearPoll();
      } else {
        s.poll = "active";
        schedulePoll(b.status === "awaiting_approval" ? 10000 : 2000);
      }
      return;
    }
    if (res.kind === "json" && res.status === 404 && res.body && res.body.error && res.body.error.code === "request_not_found") {
      if (s.record.delivery.state === "accepted") s.missing = true;
      else s.notFound = true;
      s.poll = "stopped";
      clearPoll();
      return;
    }
    s.poll = "paused";
    s.pollNote = res.kind === "timeout"
      ? "Status check timed out."
      : res.kind === "json" ? "The server could not report status." : "Could not reach the server.";
  }

  // ---- session (boot / Open) -----------------------------------------------
  function stopActivity() {
    clearPoll();
    if (readHandle) { readHandle.cancel(); readHandle = null; }
  }

  function loadSession() {
    sub = null;
    history = [];
    if (!ws || !storage || !ctx.projectId) return;
    if (!recoverStorage()) { emit(); return; }
    const r = readIndex(ctx.projectId);
    if (!r.ok) { notify("Submission storage index could not be read."); return; }
    if (!r.idx) return;
    const en = enumerate();
    if (!en.ok) { notify(en.error); return; }
    const byId = new Map(en.records.filter((x) => x.id.projectId === ctx.projectId).map((x) => [x.id.requestId, x.rec]));
    const active = r.idx.activeRequestId ? byId.get(r.idx.activeRequestId) : null;
    if (active) {
      sub = { record: active, queueStatus: null, readback: null, notFound: false, missing: false, conflict: null, poll: "stopped", pollNote: null };
    }
    history = r.idx.recent.map((rid) => byId.get(rid)).filter(Boolean).map((rec) => ({
      requestId: identityOf(rec).requestId, issueId: identityOf(rec).issueId,
      revisionShort: identityOf(rec).revisionId.slice(0, 12), state: rec.delivery.state,
    }));
    const gen = docGen;
    const s = sub;
    (async () => {
      if (s && s.record.delivery.state !== "rejected") await readback(s, false);
      if (gen !== docGen || disposed) return;
      for (const rid of r.idx.recent) {
        const rec = byId.get(rid);
        if (!rec || rec.kind !== "full" || rec.delivery.state !== "outcome_unknown") continue;
        const tmp = { record: rec, queueStatus: null, readback: null, notFound: false, missing: false, conflict: null, poll: "stopped" };
        const h = request(`./run-request/${encodeURIComponent(rid)}?workspaceId=${encodeURIComponent(ws)}`, { method: "GET", cache: "no-store" });
        const res = await h.promise;
        if (gen !== docGen || disposed) return;
        if (res.kind === "json" && res.status === 200 && res.body && res.body.bindings &&
            res.body.bindings.issueId === identityOf(rec).issueId && res.body.bindings.revisionId === identityOf(rec).revisionId) {
          applyDelivery(tmp.record, { state: "accepted", queueId: res.body.queueId });
          history = history.map((x) => (x.requestId === rid ? { ...x, state: "accepted" } : x));
          emit();
        }
      }
    })();
  }

  // ---- public API -------------------------------------------------------------
  function documentOpened(next) {
    if (disposed) return;
    docGen += 1;
    reviewGen += 1;
    stopActivity();
    ctx = { projectId: next.projectId || null, issueId: next.issueId || null, mode: next.mode || null };
    review = { status: "none" };
    draftEdited = false;
    notices = [];
    loadSession();
    emit();
  }

  function contextChanged(next) {
    if (disposed) return;
    const n = { projectId: next.projectId || null, issueId: next.issueId || null, mode: next.mode || null };
    const changed = n.projectId !== ctx.projectId || n.issueId !== ctx.issueId || n.mode !== ctx.mode;
    ctx = n;
    if (changed) {
      reviewGen += 1;
      if (review.status !== "none") review = { status: "none" };
    }
    emit();
  }

  function draftChanged() {
    if (disposed) return;
    draftEdited = true;
    emit();
  }

  function refuse(reason) {
    review = { status: "refused", reason };
    emit();
  }

  function startReview(input) {
    if (disposed || review.status === "hashing") return;
    const av = availability();
    if (!av.ok) return refuse(av.reason);
    const yaml = input ? input.yaml : null;
    if (input && input.blockedReason) return refuse(input.blockedReason);
    const { projectId, issueId } = ctx;
    if (!projectId) return refuse("This document has no project ID yet.");
    if (codePointLength(projectId) > _PROJECT_ID_MAX_CODE_POINTS) {
      return refuse(`The project ID is longer than ${_PROJECT_ID_MAX_CODE_POINTS} characters.`);
    }
    if (!issueId) return refuse("Select an issue before reviewing.");
    if (codePointLength(issueId) > _PROJECT_ID_MAX_CODE_POINTS) return refuse("The issue ID is too long.");
    if (typeof yaml !== "string" || !yaml) return refuse("There is no generated policy file to review.");
    if (!isWellFormedUtf16(yaml)) return refuse("The policy contains text that cannot be encoded as UTF-8 (an unpaired surrogate).");
    const probe = JSON.stringify({
      requestId: _PLACEHOLDER_REQUEST_ID, projectId, workspaceId: ws, revisionId: "0".repeat(64), yaml, issueId,
    });
    const bytes = _utf8Length(probe);
    if (bytes > _RUN_REQUEST_MAX_BYTES) {
      return refuse(`The request would be ${bytes} bytes, over the ${_RUN_REQUEST_MAX_BYTES}-byte limit.`);
    }
    const gen = reviewGen;
    const op = ++opSeq;
    const snapshot = Object.freeze({ projectId, workspaceId: ws, issueId, yaml });
    review = { status: "hashing", snapshot, op };
    draftEdited = false;
    emit();
    sha256Hex(yaml, d.subtle).then(
      (hex) => {
        if (disposed || gen !== reviewGen || review.op !== op) return;
        review = { status: "ready", snapshot: Object.freeze({ ...snapshot, revisionId: hex }), op };
        emit();
      },
      () => {
        if (disposed || gen !== reviewGen || review.op !== op) return;
        refuse("The policy could not be hashed.");
      }
    );
  }

  function submit(opts) {
    if (disposed || submitting) return false;
    const newRun = !!(opts && opts.newRun);
    if (review.status !== "ready") { notify("Review the policy before submitting."); emit(); return false; }
    if (!availability().ok) { notify(availability().reason); emit(); return false; }
    if (sub && sub.record.delivery.state === "outcome_unknown" && !newRun) {
      notify("An earlier request may still exist on the host. Check its status, or choose Run again to send a new one.");
      emit();
      return false;
    }
    const snap = review.snapshot;
    const gen = reviewGen;
    const requestId = d.randomUUID();
    const envelope = Object.freeze({
      requestId, projectId: snap.projectId, workspaceId: snap.workspaceId,
      revisionId: snap.revisionId, yaml: snap.yaml, issueId: snap.issueId,
    });
    const yamlByteLength = _utf8Length(envelope.yaml);
    const fail = (msg) => { notify(msg); emit(); return false; };

    // -- synchronous persist-before-POST sequence: no await below this line --
    if (!pruneResolved()) return fail("Cleaning up saved requests failed; nothing was sent.");
    let identityOk = false;
    try { identityOk = !!d.ensureDocumentIdentity(envelope.projectId); } catch (e) { identityOk = false; }
    if (!identityOk) return fail("This document's identity could not be saved to browser storage; nothing was sent.");
    const prepared = { v: 1, kind: "full", envelope, yamlByteLength, delivery: { state: "prepared" } };
    const unknown = { ...prepared, delivery: { state: "outcome_unknown" } };
    const cur = readIndex(envelope.projectId);
    if (!cur.ok) return fail("Saved request index could not be read; nothing was sent.");
    const prevIdx = cur.idx;
    const recent = prevIdx
      ? [prevIdx.activeRequestId, ...prevIdx.recent].filter((x) => x && x !== requestId)
      : [];
    const nextIdx = { workspaceId: ws, projectId: envelope.projectId, activeRequestId: requestId, recent, updatedAt: now() };
    const en = enumerate();
    if (!en.ok) return fail(`${en.error} Nothing was sent.`);
    const kRec = recKey(envelope.projectId, requestId);
    const recSize = 2 * (kRec.length + Math.max(encode(prepared).length, encode(unknown).length));
    const oldIdx = en.indexes.find((i) => i.idx.projectId === envelope.projectId);
    const idxSize = 2 * (idxKey(envelope.projectId).length + encode(nextIdx).length);
    const peak = en.total + recSize + Math.max(0, idxSize - (oldIdx ? oldIdx.size : 0));
    if (peak > budgetBytes) {
      return fail("There is not enough room in browser storage to save this request; nothing was sent. Existing requests were kept.");
    }
    if (!writeRecord(prepared)) {
      removeKey(kRec);
      return fail("The request could not be saved to browser storage; nothing was sent.");
    }
    if (!writeIndex(nextIdx)) {
      if (!removeKey(kRec)) notify("A partly saved request could not be removed; it will be cleaned up on reload.");
      return fail("The request index could not be saved; nothing was sent.");
    }
    if (!writeRecord(unknown)) {
      discardPrepared(envelope.projectId, requestId);
      review = { status: "none" };
      return fail("The request could not be marked as sent; nothing was sent. Review the policy again.");
    }
    if (gen !== reviewGen) return fail("The document changed before sending; review it again.");
    // -- POST barrier passed --
    stopActivity();
    sub = { record: unknown, queueStatus: null, readback: null, notFound: false, missing: false, conflict: null, poll: "stopped", pollNote: null };
    notices = [];
    review = { status: "none" };
    sendPost(unknown);
    return true;
  }

  function retry() {
    if (disposed || submitting || !sub || !sub.notFound || sub.record.kind !== "full" ||
        sub.record.delivery.state !== "outcome_unknown") return false;
    sub.notFound = false;
    notices = [];
    sendPost(sub.record);
    return true;
  }

  function refreshStatus() {
    if (disposed || !sub) return;
    readback(sub, true);
  }

  function dispose() {
    disposed = true;
    docGen += 1;
    reviewGen += 1;
    stopActivity();
    if (issuesHandle) issuesHandle.cancel();
    if (postHandle) postHandle.cancel();
    listeners.clear();
  }

  return {
    getState,
    onChange(cb) { listeners.add(cb); return () => listeners.delete(cb); },
    documentOpened, contextChanged, draftChanged,
    loadIssues, review: startReview, submit, retry, refreshStatus, dispose,
  };
}

// Browser-only global so the inlined copy can expose the API without breaking
// node import.
if (typeof window !== "undefined") {
  window.PolicyBuilderCore = {
    evaluateRules,
    detectShadows,
    isCatchall,
    parseRuleTable,
    compileBooleanPredicate,
    normalizeDimName,
    serializeLoopYaml,
    moveRule,
    seedExample,
    blankModel,
    // FEAT-3474 (issue_lifecycle mode)
    BUILTIN_FRONTMATTER_DIMENSIONS,
    LIFECYCLE_VERBS,
    _serializeIssueLifecycle,
    _emittedVerbs,
    _doneStateName,
    // ENH-3492 (terminal destinations, dispatch/terminal-block split)
    LIFECYCLE_DESTINATIONS,
    _dispatchedDestinations,
    _requiredTerminalBlocks,
    serializeFrontmatterDimensions,
    parseFrontmatterBlock,
    encodeFrontmatterScores,
    // BUG-3489 (reserved-name guard)
    RESERVED_STATE_NAMES,
    isReservedOutcomeToken,
    // BUG-3486 (model validation, compiled Try-it evaluation, editing reconciliation)
    validateBuilderModel,
    evaluateModel,
    reconcilePredicateForDim,
    opsForType,
    // ENH-3507 (injected-storage factory)
    createBuilderStorage,
    // FEAT-3505 (submission controller)
    sha256Hex,
    createSubmissionController,
    queueStatusLabel,
    QUEUE_TERMINAL_STATUSES,
    // ENH-3487 (draft/project persistence, undo/redo)
    BUILDER_PROJECT_SCHEMA_VERSION,
    validateProjectStructure,
    serializeBuilderProject,
    parseBuilderProject,
    applyDraftEdit,
    // ENH-3491 (task presets, transition summary)
    taskPresets,
    summarizeTransitions,
    // FEAT-3488 (offline scenario suites)
    rulesFingerprint,
    normalizeScenarioInput,
    traceModel,
    evaluateScenario,
    runScenarioSuite,
    withScenariosDefaulted,
    // FEAT-3501 (shared structural transition analysis)
    analyzeTransitions,
    // FEAT-3503 (boundary suggestions, local issue-file import)
    suggestScenarios,
    scenarioSemanticKey,
    extractIssueFrontmatter,
    dropNonDimensionContinuations,
    lifecycleDimensionSourceKeys,
    buildImportedScenario,
  };
}
