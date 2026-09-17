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
  for (let i = 0; i < compiled.length; i++) {
    const rule = compiled[i];
    const ruleIndex = i < authoredCount ? i : -1;
    if (isCatchall(rule)) {
      return { ruleIndex, target: rule.target, isFallback: true, conditionResults: [] };
    }
    const conditionResults = rule.predicates.map((p) => evalPredicate(p, scores));
    if (conditionResults.every(Boolean)) {
      return { ruleIndex, target: rule.target, isFallback: false, conditionResults };
    }
  }
  return noMatch;
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
  }
  if (!errors.length && !project.drafts[project.activeMode]) {
    errors.push(`no draft exists for activeMode ${JSON.stringify(project.activeMode)}`);
  }
  return errors;
}

/**
 * Serialize a BuilderProject to indented, deterministic JSON text (Save
 * project / localStorage). Pure — no ID generation or clock reads.
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
 * @returns {{steps: string[], stopsAfterImplement: boolean, verification: "acceptance"|"issue_validation"|"unconfigured"|"custom"|"none", stepsPerAttempt: number, attempts: number, maxStepsNote: string}}
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
  // chain, anything else (`rescore`/`finish`) ends it. A cycle guard prevents
  // an infinite loop on an authored goto cycle (summary purposes only).
  const chainLenFrom = (name, seen) => {
    if (seen.has(name)) return 0;
    seen.add(name);
    const oc = outcomeMap.get(name);
    const t = oc && oc.transition;
    if (t && t.kind === "goto" && t.target && outcomeMap.has(t.target)) {
      return 1 + chainLenFrom(t.target, seen);
    }
    return 1;
  };
  const dispatchTargets = new Set();
  for (const r of model.rules || []) {
    if (r.target && outcomeMap.has(r.target)) dispatchTargets.add(r.target);
  }
  if (model.fallback && outcomeMap.has(model.fallback)) dispatchTargets.add(model.fallback);
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
    // ENH-3487 (draft/project persistence, undo/redo)
    BUILDER_PROJECT_SCHEMA_VERSION,
    validateProjectStructure,
    serializeBuilderProject,
    parseBuilderProject,
    applyDraftEdit,
    // ENH-3491 (task presets, transition summary)
    taskPresets,
    summarizeTransitions,
  };
}
