// ENH-3560 node:test — the builder's client JS must never route model-derived
// strings (outcome/dimension names, dimension types) through innerHTML.
//
// Two layers: (1) a static scan of the template that fails closed on any
// innerHTML / outerHTML / insertAdjacentHTML write whose value is not a
// single constant string literal, and (2) a hostile-project render test that
// runs the real render functions in a stub-DOM node:vm sandbox (no jsdom —
// the suite stays zero-dependency).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

import { parseBuilderProject, normalizeDimName } from "../../little_loops/templates/policy_builder_core.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_PATH = join(__dirname, "..", "..", "little_loops", "templates", "policy-router-builder.html.tmpl");
const templateSrc = readFileSync(TEMPLATE_PATH, "utf8");

const PAYLOAD = "<img src=x onerror=alert(1)>";

// ---------------------------------------------------------------------------
// Static check
// ---------------------------------------------------------------------------

/** Return the offending sites (with line numbers) in `src`; empty when clean. */
export function findNonConstantHtmlSinks(src) {
  const violations = [];
  const lineOf = (idx) => src.slice(0, idx).split("\n").length;
  const CONST_LITERAL = /^(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\$]|\\.|\$(?!\{))*`)$/;

  // `.innerHTML = X;`, `.innerHTML += X;`, `.outerHTML = X;` — X runs to the
  // first `;` outside string/template literals.
  const assign = /\.(?:innerHTML|outerHTML)\s*(\+?=)(?!=)/g;
  let m;
  while ((m = assign.exec(src))) {
    const rhs = _readExpression(src, assign.lastIndex, [";"]);
    if (rhs === null || !CONST_LITERAL.test(rhs.trim())) {
      violations.push(`line ${lineOf(m.index)}: ${(rhs ?? "<unparseable>").trim().slice(0, 80)}`);
    }
  }

  // `.insertAdjacentHTML(pos, X)` — X is the second argument.
  const adjacent = /\.insertAdjacentHTML\s*\(/g;
  while ((m = adjacent.exec(src))) {
    const args = _readExpression(src, adjacent.lastIndex, [")"]);
    const second = args === null ? null : _splitTopLevel(args)[1];
    if (second === undefined || second === null || !CONST_LITERAL.test(second.trim())) {
      violations.push(`line ${lineOf(m.index)}: insertAdjacentHTML(${(args ?? "<unparseable>").trim().slice(0, 80)})`);
    }
  }
  return violations;
}

// Scan from `start` to the first `terminators` char at bracket depth 0 and
// outside string/template literals. Returns null (fail closed) on EOF.
function _readExpression(src, start, terminators) {
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    const c = src[i];
    if (c === '"' || c === "'" || c === "`") {
      i = _skipLiteral(src, i);
      if (i === -1) return null;
      continue;
    }
    if (c === "(" || c === "[" || c === "{") depth++;
    else if (c === ")" || c === "]" || c === "}") {
      if (depth === 0 && terminators.includes(c)) return src.slice(start, i);
      depth--;
    } else if (depth === 0 && terminators.includes(c)) return src.slice(start, i);
  }
  return null;
}

function _skipLiteral(src, i) {
  const quote = src[i];
  for (let j = i + 1; j < src.length; j++) {
    if (src[j] === "\\") j++;
    else if (src[j] === quote) return j;
    else if (quote === "`" && src[j] === "$" && src[j + 1] === "{") {
      // Interpolation: skip the balanced expression (may contain nested literals).
      const end = _readExpression(src, j + 2, ["}"]);
      if (end === null) return -1;
      j += 2 + end.length;
    }
  }
  return -1;
}

function _splitTopLevel(args) {
  const parts = [];
  let depth = 0;
  let last = 0;
  for (let i = 0; i < args.length; i++) {
    const c = args[i];
    if (c === '"' || c === "'" || c === "`") {
      i = _skipLiteral(args, i);
      if (i === -1) return parts;
    } else if ("([{".includes(c)) depth++;
    else if (")]}".includes(c)) depth--;
    else if (c === "," && depth === 0) {
      parts.push(args.slice(last, i));
      last = i + 1;
    }
  }
  parts.push(args.slice(last));
  return parts;
}

test("ENH-3560: static check flags variable, concatenated, and interpolated sinks", () => {
  assert.equal(findNonConstantHtmlSinks(`el.innerHTML = "";`).length, 0);
  assert.equal(findNonConstantHtmlSinks("el.innerHTML = `<label>Do:</label>`;").length, 0);
  assert.equal(findNonConstantHtmlSinks(`el.insertAdjacentHTML("beforeend", "<b>x</b>");`).length, 0);
  assert.equal(findNonConstantHtmlSinks(`el.innerHTML = html;`).length, 1, "bare variable");
  assert.equal(findNonConstantHtmlSinks("el.innerHTML = `<b>${x}</b>`;").length, 1, "interpolated template");
  assert.equal(findNonConstantHtmlSinks(`el.innerHTML = "<b>" + x;`).length, 1, "concatenation");
  assert.equal(findNonConstantHtmlSinks(`el.innerHTML += f();`).length, 1, "call, +=");
  assert.equal(findNonConstantHtmlSinks(`el.outerHTML = x;`).length, 1, "outerHTML");
  assert.equal(findNonConstantHtmlSinks("el.insertAdjacentHTML(pos, `<b>${x}</b>`);").length, 1, "adjacent");
  assert.equal(findNonConstantHtmlSinks(`el.innerHTML = "unterminated`).length, 1, "fails closed");
});

test("ENH-3560: policy-router-builder.html.tmpl assigns only constant string literals to HTML sinks", () => {
  const violations = findNonConstantHtmlSinks(templateSrc);
  assert.deepEqual(violations, [], `non-constant HTML sinks:\n${violations.join("\n")}`);
});

// ---------------------------------------------------------------------------
// Hostile-project render test
// ---------------------------------------------------------------------------

function extractFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `could not locate function ${name} — template moved`);
  let i = src.indexOf("{", start);
  let depth = 0;
  for (; i < src.length; i++) {
    // Plain brace counting: comments hold apostrophes, so literal-skipping
    // would desync; braces inside these functions' strings are balanced.
    const c = src[i];
    if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return src.slice(start, i + 1);
  }
  throw new Error(`unbalanced braces extracting ${name}`);
}

function makeElement(log, tag = "div") {
  const el = {
    tagName: tag.toUpperCase(),
    children: [],
    style: {},
    dataset: {},
    attributes: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    _text: "",
    appendChild(c) { this.children.push(c); return c; },
    append(...cs) { this.children.push(...cs); },
    setAttribute(k, v) { this.attributes[k] = v; },
    addEventListener() {},
    insertAdjacentHTML(_pos, html) { log.html.push(html); },
    querySelector: () => null,
    querySelectorAll: () => [],
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); },
    get innerHTML() { return this._html ?? ""; },
    set innerHTML(v) { this._html = v; log.html.push(v); },
  };
  log.elements.push(el);
  return el;
}

function renderHostile(mode) {
  const dimName = PAYLOAD;
  const project = parseBuilderProject(
    JSON.stringify({
      schemaVersion: 1,
      projectId: "hostile",
      activeMode: mode,
      drafts: {
        [mode]: {
          model: {
            mode,
            dimensions: [{ name: dimName, type: PAYLOAD }],
            rules: [],
            outcomes: [{ name: PAYLOAD, actionType: "slash_command", action: "", skill: "" }],
            fallback: PAYLOAD,
          },
        },
      },
    })
  );
  const model = project.drafts[mode].model;
  const log = { html: [], elements: [] };
  const byId = new Map();
  const $ = (id) => {
    if (!byId.has(id)) byId.set(id, makeElement(log));
    return byId.get(id);
  };
  const context = vm.createContext({
    state: { ...model, mode },
    $,
    document: { createElement: (tag) => makeElement(log, tag), querySelectorAll: () => [] },
    normalizeDimName,
    BUILTIN_DIM_NAMES: new Set(),
    LIFECYCLE_DESTINATIONS: [],
    renderAll() {},
    commit() {},
    updatePreview() {},
    _liveOperation: (fn) => fn(),
    CATALOG: [],
    _skillHintFor: () => "",
    _anchorsToText: () => "",
    _anchorsFromText: () => [],
    Set,
  });
  const fns = ["renderDimensions", "renderOutcomes", "renderLifecycleOutcomes"];
  vm.runInContext(fns.map((n) => extractFunction(templateSrc, n)).join("\n"), context);
  return { context, log };
}

function textContents(log) {
  const out = [];
  const walk = (el) => {
    if (typeof el === "string") return out.push(el);
    if (el._text) out.push(el._text);
    el.children.forEach(walk);
  };
  log.elements.forEach(walk);
  return out;
}

test("ENH-3560: hostile outcome/dimension names render as inert text, never via innerHTML", () => {
  const { context, log } = renderHostile("decision_table");
  vm.runInContext("renderDimensions(); renderOutcomes();", context);
  const lifecycle = renderHostile("issue_lifecycle");
  vm.runInContext("renderLifecycleOutcomes();", lifecycle.context);

  for (const l of [log, lifecycle.log]) {
    for (const html of l.html) {
      assert.ok(!html.includes("<img"), `innerHTML received hostile markup: ${html}`);
    }
  }
  const texts = [...textContents(log), ...textContents(lifecycle.log)];
  assert.ok(texts.includes(PAYLOAD), "outcome name appears verbatim in textContent");
  assert.ok(texts.includes(`(${PAYLOAD})`), "dimension type appears verbatim in textContent");
  assert.ok(texts.includes(normalizeDimName(PAYLOAD)), "normalized dimension name appears in textContent");
});
