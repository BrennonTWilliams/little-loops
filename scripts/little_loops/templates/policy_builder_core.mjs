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
  return {
    dim: m.groups.dim.trim(),
    op: m.groups.op,
    value: m.groups.value.trim(),
  };
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
function _outcomeStateLines(outcome, { doneState = "done", issueArg = false } = {}) {
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
  if (t.kind === "rescore") {
    lines.push(`    next: score`);
  } else if (t.kind === "goto") {
    lines.push(`    next: ${t.target}`);
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
  const out = [];
  const name = model.name || "policy-builder";
  out.push(`name: ${name}`);
  if (model.description) {
    out.push(`description: |`);
    out.push(_yamlBlockScalar(model.description, 2));
  }
  out.push(`max_steps: ${model.maxSteps != null ? model.maxSteps : 20}`);
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
  out.push("");
  // parse_scores
  out.push("  parse_scores:");
  out.push("    fragment: policy_parse_scores");
  out.push("    next: policy_dispatch");
  out.push("");
  // policy_dispatch with route map covering every outcome + _/_error
  out.push("  policy_dispatch:");
  out.push("    fragment: policy_table_dispatch");
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
  // Sentinels: default -> fallback (or first outcome), error -> first outcome.
  const fallbackState = model.fallback || tokens[0] || "done";
  const errorState = tokens[0] || fallbackState;
  out.push(`      _: ${fallbackState}`);
  out.push(`      _error: ${errorState}`);
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
  return out.join("\n").replace(/\n+$/, "\n");
}

function _serializeRubric(model) {
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

// Emits the issue_lifecycle-mode loop YAML (Proposed Solution §2): a thin
// standalone loop that imports lib/policy-router.yaml, self-declares
// `parameters: { issue_id: {...} }` (not `with:` — that key is caller-side
// only, fsm/schema.py:684), and replaces the LLM rubric_score/policy_parse_scores
// pair with the deterministic `frontmatter_scores` fragment. Every verb state
// carries `on_error: failed`; `scope`/`pruning_profile_ok`/`on_max_steps`/
// `timeout` are all required for the zero-warnings AC (see the issue's
// 4th/5th-pass findings).
function _serializeIssueLifecycle(model) {
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
  out.push("on_max_steps: failed");
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
  out.push("    route:");
  const verbs = _emittedVerbs(model);
  for (const v of verbs) {
    out.push(`      ${v}: ${v}`);
  }
  out.push(`      _: ${model.fallback || verbs[0] || "gate"}`);
  out.push(`      _error: failed`);
  out.push("");
  const outcomeMap = new Map();
  for (const o of model.outcomes || []) outcomeMap.set(o.name, o);
  for (const v of verbs) {
    const outcome = outcomeMap.get(v);
    for (const line of _outcomeStateLines(outcome, { doneState: "done", issueArg: true })) {
      out.push(line);
    }
    out.push(`    on_error: failed`);
    out.push("");
  }
  out.push("  done:");
  out.push("    terminal: true");
  out.push("");
  out.push("  failed:");
  out.push("    terminal: true");
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
 * flow lists (`[a, b]`) and dash lists (`- a` / `- b`) — no nested maps
 * (Non-goals: the runtime scorer uses the full `parse_frontmatter`, not this
 * mini-parser).
 *
 * Throws `Error("Can't read line N: <text>")` on the first unparseable line
 * (no `:` and not a recognized list-continuation), matching the UI-Notes
 * error format the hint text surfaces verbatim.
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
    const line = raw.trim();
    if (line === "") continue;
    if (/^-{3,}\s*$/.test(line)) continue; // --- fence, tolerated/ignored
    if (line === "-" || line.startsWith("- ")) {
      if (currentListKey === null) {
        throw new Error(`Can't read line ${i + 1}: ${raw}`);
      }
      const item = line === "-" ? "" : _stripMatchingQuotes(line.slice(2).trim());
      currentList.push(item);
      result[currentListKey] = currentList;
      continue;
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
    if (value.startsWith("[") && value.endsWith("]")) {
      const inner = value.slice(1, -1).trim();
      result[key] = inner ? inner.split(",").map((s) => _stripMatchingQuotes(s.trim())) : [];
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
  // Derived priority_rank: only when `priority` is a declared dimension and
  // its value matches ^P(\d)$ after strip. Independent of whether
  // `priority_rank` itself is also declared (it always is, as a built-in).
  const priorityDim = (dims || []).find((d) => normalizeDimName(d.name) === "priority");
  if (priorityDim) {
    const has = fm != null && Object.prototype.hasOwnProperty.call(fm, priorityDim.name);
    const rawPriority = has ? fm[priorityDim.name] : undefined;
    if (rawPriority !== undefined && rawPriority !== null) {
      const m = /^P(\d)$/.exec(String(rawPriority).trim());
      if (m) scores["priority_rank"] = m[1];
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
    serializeFrontmatterDimensions,
    parseFrontmatterBlock,
    encodeFrontmatterScores,
  };
}
