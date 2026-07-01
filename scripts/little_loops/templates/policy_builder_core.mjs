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
function _serializeRulesText(model) {
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
function _outcomeStateLines(outcome) {
  const lines = [];
  lines.push(`  ${outcome.name}:`);
  const at = outcome.actionType || "none";
  if (at === "prompt" || at === "slash_command") {
    lines.push(`    action_type: ${at}`);
    const body = at === "slash_command" ? (outcome.body || "").trim() : outcome.body || "";
    if (at === "slash_command") {
      lines.push(`    action: ${body}`);
    } else {
      lines.push(`    action: |`);
      lines.push(_yamlBlockScalar(body, 6));
    }
  }
  // Axis B transition.
  const t = outcome.transition || { kind: "finish" };
  if (t.kind === "rescore") {
    lines.push(`    next: score`);
  } else if (t.kind === "goto") {
    lines.push(`    next: ${t.target}`);
  } else {
    lines.push(`    terminal: true`);
  }
  return lines;
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
  for (const tok of tokens) {
    const outcome =
      outcomeMap.get(tok) || { name: tok, actionType: "none", transition: { kind: "finish" } };
    for (const line of _outcomeStateLines(outcome)) out.push(line);
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

/**
 * Serialize a builder model to loop YAML text (deterministic). See the
 * model-shape contract in the file header.
 * @param {Object} model
 * @returns {string}
 */
export function serializeLoopYaml(model) {
  if (model && model.mode === "rubric") {
    return _serializeRubric(model);
  }
  return _serializeDecisionTable(model);
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
  };
}
