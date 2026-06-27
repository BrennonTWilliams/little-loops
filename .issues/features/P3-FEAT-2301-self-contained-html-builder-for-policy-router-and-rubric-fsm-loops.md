---
id: FEAT-2301
title: Self-contained HTML builder for policy-router and rubric FSM loops
type: FEAT
priority: P3
status: open
discovered_date: 2026-06-26
discovered_by: capture-issue
captured_at: '2026-06-26T00:35:41Z'
relates_to:
- ENH-2299
- FEAT-1023
- ENH-2309
- ENH-2334
confidence_score: 98
outcome_confidence: 68
score_complexity: 13
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
---

# FEAT-2301: Self-contained HTML builder for policy-router and rubric FSM loops

## Summary

Generate a single, self-contained `.html` artifact that lets a user visually
configure a Policy Router + Decision Table FSM loop (`lib/policy-router.yaml`)
or a Rubric 3-tier loop (`lib/rubric-router.yaml`) and export valid loop YAML.
The page is a one-page minimalist form built around action-grouped rule cards
(rules grouped under the action they trigger, with a plain "Everything else →"
fallback), with live plain-language validation, a light/dark theme toggle,
an optional design-token profile picker, and a downloadable YAML output. It is
the *visual, greenfield* sibling of ENH-2299 (the conversational `/ll:create-loop`
wizard branch) and `ll-loop edit-routes` (the round-trip table editor for
*existing* loops).

## Motivation

The policy-router decision table is the one little-loops authoring artifact that
fights both of its current surfaces:

- The `/ll:create-loop` wizard (ENH-2299) is linear `AskUserQuestion` prose — bad
  at a grid where row *order* encodes precedence and columns appear/disappear as
  the dimension set changes.
- `ll-loop edit-routes` renders the compound table as markdown and round-trips it
  to YAML, but only for a loop that *already exists*, with no live validation.

A real HTML grid fits the table's shape natively and can make the error classes
the guide and ENH-2299 call out — missing catch-all, unmatched `route:` keys,
MR-4 dead-ends, numeric-coercion parse errors — **structurally unrepresentable**
rather than merely validated after the fact. It also matches the project's
"portable, self-contained artifact" philosophy (cf. FEAT-1023's
`html-website-generator`, which already emits self-contained HTML with an
embedded light/dark toggle).

## Use Case

A little-loops author wants to design a new `policy-router` loop from scratch. They open
`policy-router-builder.html` in their browser (no install, no server), fill in the loop name
and dimensions (e.g. `overall_quality` numeric, `has_citations` boolean), reorder the rules
by precedence, verify the "Everything else →" fallback fires last, then download `refine-quality.yaml`.
They run `ll-loop validate refine-quality.yaml` and it passes with no MR-4 dead-ends and no
unmatched route keys — without hand-writing the `import:` block, `route:` map, or catch-all
arms.

## Current Behavior

To author a policy-router loop today a user must hand-write the FSM YAML: the
`import:` block, `context.policy_rules` decision table, the `score → parse_scores
→ policy_dispatch` pipeline, the `route:` map (with `_:` / `_error:` catch-alls),
and a terminal/`next:` arm for every action state. The guide
(`docs/guides/POLICY_ROUTER_GUIDE.md`) documents the pattern and `ll-loop
edit-routes` can edit an existing table, but there is no visual, greenfield
composer and no live validation while authoring.

## Expected Behavior

A generated, self-contained `.html` file (no external dependencies; works over
`file://`) presents a one-page form:

1. **Mode switch** at the top: **Rubric** (one aggregate score, 3 tiers) vs
   **Decision Table** (per-dimension conjunctive rules). Names map 1:1 to the two
   lib fragments and the guide's vocabulary — *not* "Lite/Full", which implies one
   is a diminished version of the other.
2. **Identity / scaffolding**: loop `name`, `subject`, `max_steps`, scoring source
   (LLM rubric via `lib/rubric-router.yaml`, or custom shell scorer that writes
   `rubric-dim-<name>.txt`).
3. **Dimensions as chips** that reactively define the decision-table columns; each
   dimension typed numeric vs boolean so the operator dropdown only offers
   valid ops (ordered ops `>= <= < >` for numeric; `==true/==false` for boolean) —
   preventing the parse-time numeric-coercion error class. The reserved
   `aggregate` pseudo-dimension is always available. **Boolean dimensions are a UI
   affordance over a numeric encoding** (see "Boolean dimension encoding" below): the
   chip reads `==true/==false`, but the generated YAML emits the dimension into
   `rubric_dimensions` with a 0/100 scoring instruction and compiles the predicate to
   a numeric form (`==true` → `>=50`, `==false` → `<50`). This keeps boolean
   predicates live at runtime with **no change to the score/parse fragments**.
4. **Action-grouped rule cards** (Decision Table mode): instead of a wide, sparse
   2-D grid, rules are grouped under the action-state they trigger. Each action is
   a card ("`light_repair` happens when…") listing its rules as readable condition
   rows (per-dimension op+value controls; an empty rule is unconstrained); multiple
   rules targeting the same action stack as alternative situations within that
   card. **Global precedence is preserved and visible**: every rule shows a sequence
   badge (#1, #2, …) reflecting the single top-to-bottom "first match wins" order
   *across all cards*, and precedence is reorderable (drag or ↑/↓). A rule's action
   is reassigned via a **dropdown** on the rule — *not* card-drag (decided
   2026-06-26; see "UI presentation" below). The catch-all renders as a visually
   distinct, non-deletable **"Everything else → `<action>`" fallback footer**
   (dashed/muted card) that always occupies the last position in the output YAML —
   it reads as a sentence, not a `*` row that scans as missing data. Each action
   card also surfaces its `terminal`-vs-`next:` choice as a human-worded toggle
   ("re-scores, then loops" vs "finishes the loop"). Rubric mode replaces the cards
   with two threshold sliders (`threshold_high`, `threshold_medium`) feeding a
   fixed 3-row high/medium/low table.
5. **Derived action states**: the set of `→ action` targets is auto-listed; each
   gets a forced `terminal` vs `next:` choice (+ optional prompt body). This is
   what makes MR-4 dead-ends unrepresentable. The `route:` map and `_:` / `_error:`
   arms are *generated*, never hand-typed (no unmatched keys).
6. **Live, friendly validation** colored from the active design-token semantics,
   with plain-language inline messages rather than color alone: a shadowed rule is
   flagged in-place — "can never fire — rule #N above already matches everything
   this would" (referencing the shadowing rule's sequence number); a rule with no
   conditions is flagged as matching everything and starving the rules below it;
   unknown action → danger; a clean, fully-reachable table whose fallback covers
   the remainder → success. A summary banner counts unreachable rules. Severities:
   shadowed / zero-condition → warning, unknown action → danger, clean → success.
7. **Theming**: stamped from the active design-token profile in
   `.ll/ll-config.json` (e.g. `warm-paper`), with **both** light and dark CSS
   variable blocks inlined and an embedded sun/moon toggle. Theme precedence:
   `prefers-color-scheme` (fallback) → config `active_theme` (default) →
   `localStorage` (user override, wins). Optionally inline all 3 profiles × 2
   themes to make the **profile** switchable in-page too.
8. **Output**: live YAML preview + Copy + Download `<name>.yaml`, with a printed
   `ll-loop validate <name>` line underneath so the Python gate stays authoritative.

## Acceptance Criteria

- [ ] The generated `.html` file loads without errors over `file://` with no external
  dependencies (no CDN, no fetch at runtime)
- [ ] Mode switch between **Rubric** and **Decision Table** renders without a page reload
- [ ] Decision Table mode: dimension chip type (numeric vs boolean) restricts operator
  dropdown to valid ops only (`>= <= < >` for numeric; `==true/==false` for boolean),
  preventing the numeric-coercion parse-error class
- [ ] The in-browser validator's operator sets and predicate regex are **stamped at emit
  time** from a new public `fsm/policy_rules.grammar_spec()` accessor (exposing `_ORDERED_OPS`,
  `_ALL_OPS`, and `_PRED_PATTERN.pattern`) — never hand-written as JS literals in the template.
  The emit path injects them as a JSON `<script>` block; the operator dropdown and the
  numeric-coercion branch are built from that data. Python named groups `(?P<name>…)` are
  converted to JS `(?<name>…)` by a single deterministic `_py_pattern_to_js` helper. This removes
  the *data* half of the grammar-drift surface entirely: a new operator added to `policy_rules.py`
  flows into builder output on the next emit with no template edit
- [ ] A grammar drift-guard test asserts (a) the operator sets embedded in generated HTML exactly
  equal `sorted(_ALL_OPS)` / `sorted(_ORDERED_OPS)`, and (b) the emitted + translated regex
  accepts/rejects a shared predicate corpus identically to Python's `_PRED_PATTERN` (re-compiled in
  the test). CI fails if the canonical grammar changes shape and builder output is not regenerated
- [ ] The rule *logic* the validator cannot stamp (shadow detection, catch-all detection, predicate
  evaluation) is pinned by a checked-in conformance corpus of `(rule_table, scores) →
  expected_target` and `(rule_table) → expected_shadow_warnings` cases, consumed by the Python tests
  against `evaluate_rules` / `_detect_shadows`; the same fixture is the contract a JS validator test
  consumes if a node test runner is added. This bounds the logic half that genuinely must be
  re-expressed in JS
- [ ] Decision Table mode: a boolean dimension is **emitted into `rubric_dimensions`** in
  the generated YAML (so the score prompt actually rates it) and its scoring instruction
  asks for `100`/`0`; a `==true` predicate compiles to `>=50` and `==false` to `<50` in
  the output `policy_rules` table — so a builder-generated boolean predicate is live at
  runtime (matches a scored dimension), never a silent-inert `==true` against an unscored
  dimension. No change to `lib/rubric-router.yaml` / `lib/policy-router.yaml` is required.
- [ ] Decision Table mode: dimension names are normalized identically (lowercase,
  whitespace → hyphens) across the column header, the injected LLM scoring instruction,
  AND the emitted `policy_rules` predicates — OR dimension input is restricted to
  `[a-z0-9-]`. Without this, a header like `Has Citations` yields a score file keyed
  `has-citations` (`policy_parse_scores` lowercases + spaces→hyphens) while the emitted
  predicate stays `Has Citations:…`, so `evaluate_rules`'s exact-string `scores.get(pred.dim)`
  misses, the predicate is silently inert, and routing falls through to the catch-all — the
  same dead-predicate class the boolean encoding prevents, generalized to any mixed-case or
  spaced dimension name. Base `ll-loop validate` does NOT catch this (no semantic liveness
  check); ENH-2309 *can* catch it at the gate **iff** it compares the raw predicate dim
  against the normalized scored-dimension set (its current step-1-raw / step-2-normalized
  asymmetry — see ENH-2309 cross-ref), but the builder is the only place to guarantee
  builder output is never inert
- [ ] Decision Table mode: rules are grouped into per-action cards ("`<action>` happens
  when…"); multiple rules for the same action stack as alternative situations within the
  card; each rule's action is reassignable via a dropdown (no card-drag)
- [ ] Decision Table mode: every rule shows a global sequence badge (#1, #2, …) reflecting
  the single top-to-bottom first-match-wins order across all cards; precedence is reorderable
  (drag or ↑/↓) and the order is reflected in the output YAML's rule precedence
- [ ] Decision Table mode: the catch-all renders as a non-deletable "Everything else →
  `<action>`" fallback footer (visually distinct) and is always last in the output YAML's
  rule list
- [ ] Rubric mode: two threshold sliders produce a fixed high/medium/low 3-row table in YAML
- [ ] Action-state list auto-populates from rule action targets; each requires an explicit
  `terminal` or `next:` choice (MR-4 dead-ends are structurally unrepresentable), surfaced
  per action card as a human-worded toggle ("re-scores, then loops" vs "finishes the loop")
- [ ] Live validation surfaces plain-language inline messages (not color alone): a shadowed
  rule reads "can never fire — rule #N above already matches everything this would"; a
  zero-condition rule is flagged as matching everything; unknown action → danger; a clean
  reachable table → success; a summary banner counts unreachable rules
- [ ] Theme toggle follows correct precedence: `prefers-color-scheme` → config `active_theme`
  → `localStorage` user override
- [ ] Generated `.html` stamps the active profile's resolved token values inline at generation
  time; no runtime token fetch is required
- [ ] A builder-generated YAML passes `ll-loop validate` with no errors (catch-alls present,
  route map complete, no MR-4 dead-ends)
- [ ] `render_as_css_vars_themed(light, dark)` emits two scoped CSS blocks — `:root { … }`
  for light and `[data-theme=dark] { … }` for dark — with all alias chains resolved to
  concrete hex values

## Scope Boundaries

- **In scope**: the generated single-file HTML builder (Rubric + Decision Table
  modes); a small `render_as_css_vars_themed(light, dark)` helper in
  `design_tokens.py` that emits scoped `:root` + `[data-theme=dark]` blocks; an
  emit path that stamps the active profile into the file.
- **Out of scope**: changes to `lib/policy-router.yaml` / `lib/rubric-router.yaml`
  runtime logic (no fragment changes).
- **Out of scope**: round-trip *editing of existing* loop YAML in the browser —
  `ll-loop edit-routes` owns that; this builder is greenfield-only.
- **Out of scope**: nested/chained policy tables; the builder produces one flat
  `context.policy_rules` table.
- **Out of scope**: re-implementing the canonical rule grammar / MR validation in
  a way that can drift from `fsm/policy_rules.py` / `fsm/route_table.py`. The grammar
  *data* (operator sets + predicate regex) is stamped from `policy_rules.grammar_spec()`
  rather than hand-copied (see "Grammar as single source"); the validator's *logic* is
  pinned by a shared conformance corpus. `ll-loop validate` remains the authoritative gate.

## Proposed Solution

### Theming: reuse existing token machinery

`design_tokens.py` already does the hard part:

- `load_design_tokens(base_path, theme=...)` reads the active profile from
  `.ll/ll-config.json`, layers `semantic → typography → spacing → theme`, and
  resolves `{color.paper.900}` alias chains to concrete hex.
- `render_as_css_vars(tokens)` emits a single `:root { --color-...: #...; }` block.

The only gap: `render_as_css_vars` emits **one** theme. A live in-browser toggle
needs both inlined and scoped:

```css
:root             { --color-surface-primary: #fdfbf6; /* light */ }
[data-theme=dark] { --color-surface-primary: #0d0b08; /* dark  */ }
```

Add `render_as_css_vars_themed(light_tokens, dark_tokens)` (~15 lines) that calls
`load_design_tokens(theme="light")` and `load_design_tokens(theme="dark")` and
emits the two scoped blocks. Typography tokens ride along, so the builder's font
system follows the profile for free (warm-paper handcrafted vs editorial-mono
mono). For an in-page profile picker, emit `:root[data-profile=…][data-theme=…]`
blocks for all 3 profiles × 2 themes.

### Self-containment

All CSS (resolved token vars for the stamped profile(s)), the validation JS, and
the YAML serializer are inlined — no fetch, works over `file://`, mirroring
FEAT-1023's `html-website-generator` self-contained output. The light/dark toggle
(and optional profile picker) are fully client-side; nothing requires
regeneration. Only *which profile palette(s)* are inlined is decided at stamp time.

### Boolean dimension encoding (Option B — decided 2026-06-26)

A boolean dimension (`has_citations` with `==true/==false`) cannot be expressed
naively, because the score → parse → dispatch pipeline is numeric-only end to end:

- `lib/rubric-router.yaml` `rubric_score` asks the LLM for `<score 0-100>` per
  dimension — never `true`/`false`.
- `lib/policy-router.yaml` `policy_parse_scores` extracts per-dimension values with
  `re.finditer(r'DIMENSION:\s*…:\s*(\d+)')` — the `(\d+)` group **drops any
  non-digit value**, so no `rubric-dim-<name>.txt` is ever written for a boolean.
- `fsm/policy_rules.py:_eval_predicate` treats a missing dimension as matching only
  `!=` — so a `has_citations:==true` predicate against an unscored dimension is
  **permanently inert**, and routing silently falls through to the catch-all.

`ll-loop validate` does **not** catch this: `==` accepts any value (`_ALL_OPS`) and
the route map is complete, so the gate greenlights a semantically dead table. (See
ENH-2309, which adds the gate that does catch it.)

**Decision: compile booleans to a numeric 0/100 encoding** rather than introduce
first-class boolean scoring (which would require changing the shared fragments —
out of scope per "Scope Boundaries"). The builder:

1. Emits every boolean dimension into `context.rubric_dimensions` (so the LLM scores
   it like any other dimension).
2. Generates a scoring instruction for it of the form *"score `has_citations` as
   `100` if the artifact has citations, else `0`"* — a digit value the existing
   `(\d+)` parser captures into `rubric-dim-has-citations.txt`.
3. Compiles the grid predicate: `==true` → `>=50`, `==false` → `<50`. (`>=50` is a
   robust threshold for a 0/100 signal; it tolerates a stray `100`-vs-`0` LLM
   wobble better than `==100`.)

The chip stays a friendly boolean affordance in the UI; the output YAML is honest
numeric that runs correctly with **zero fragment-runtime changes**. The literal
`==true` never appears in generated output, so the dead-predicate class is
structurally impossible for builder output. First-class `==true` literals (if ever
wanted) are deferred to a separate fragment-scoped change.

### Dimension-name normalization (generalizes the boolean fix)

The boolean encoding closes one instance of a broader dead-predicate class. The
general root cause: `policy_parse_scores` writes per-dimension score files under a
**normalized** key — `dim_name = re.sub(r'\s+', '-', m.group(1).strip().lower())`
(lowercase, whitespace → hyphens) — while `evaluate_rules` does an **exact-string**
`scores.get(pred.dim)` against the *un-normalized* predicate dim parsed from the rule
table (`policy_rules.py:_parse_predicate` only `.strip()`s `dim`, never lowercases).
So any dimension with uppercase letters or spaces (e.g. a `Has Citations` column) is
written as `rubric-dim-has-citations.txt` (key `has-citations`) but referenced as
`Has Citations` in the predicate → `scores.get()` returns `None` → `_eval_predicate`
matches only `!=` → silent fall-through to the catch-all.

**Builder requirement:** normalize every dimension name with the *same*
lowercase + whitespace→hyphens transform when emitting (a) the column header's
canonical name, (b) the injected LLM scoring instruction's `DIMENSION: <name>` token,
and (c) the `policy_rules` predicate dim — OR constrain the dimension-name input field
to `[a-z0-9-]` so no normalization divergence is possible. This must hold for *all*
dimensions, numeric and boolean alike; the boolean 0/100 path already happens to emit
a normalized name, but numeric dimensions share the same hazard.

**Gate coverage note:** base `ll-loop validate` has no semantic-liveness check, so it
does not catch this. ENH-2309 *can* — its spec collects referenced predicate dims raw
(step 1) but normalizes the scored-dimension set (step 2), so a raw `Has Citations`
predicate is correctly flagged as never-scored against the `has-citations` score key.
This only holds while ENH-2309 keeps that asymmetry; if an implementer "fairly"
normalizes both sides, the warning disappears while the runtime bug remains (see the
ENH-2309 cross-ref note added for this). Either way the builder is the only place to
*prevent* the mismatch in builder output, which is why this is an acceptance criterion,
not deferred to the gate.

### Grammar as single source: stamp, don't hand-write (decided 2026-06-26)

The in-browser validator must mirror the canonical predicate grammar
(`fsm/policy_rules.py:27–34`: `_ORDERED_OPS`, `_ALL_OPS`, `_PRED_PATTERN`). The naive
approach — hand-copying those constants into the template's JS — creates a silent
drift surface: a future operator or regex change in `policy_rules.py` would not
propagate, and base `ll-loop validate` has no way to flag builder JS that lags the
Python grammar. That drift surface **already exists in-tree**: `route_table.py`
re-lists the operators by hand (`route_table.py:455`, "expected operator prefix
(>=, <=, ==, !=, <, >)") and maintains its own `_COND_PATTERN`, independent of
`policy_rules.py`'s set — nothing imports the canonical constants because they are
private. So this is worth fixing structurally, not waving off.

**Decision: split the mirror into a *data* half (stamp it) and a *logic* half (pin it
with a shared corpus).**

- **Data — operator sets + predicate regex — are generated, not written.** Add a public
  `grammar_spec()` accessor to `policy_rules.py`:
  ```python
  def grammar_spec() -> dict[str, object]:
      """Public, serializable view of the canonical predicate grammar.

      Single source for any consumer that must mirror the grammar out-of-process
      (the FEAT-2301 HTML builder's JS, route_table's operator list, …).
      """
      return {
          "ordered_ops": sorted(_ORDERED_OPS),
          "all_ops": sorted(_ALL_OPS),
          "pred_pattern": _PRED_PATTERN.pattern,
      }
  ```
  The emit path (`policy_builder.py`) injects `grammar_spec()` into the HTML as a JSON
  `<script>` block — the same "Python is source of truth, emit a derived artifact"
  pattern the issue already follows for `cli/schemas.py` → JSON Schema, and the same
  emit-time stamping already used for the design-token CSS vars. The JS builds its
  operator dropdown from `all_ops`, selects the numeric-coercion branch from
  `ordered_ops`, and constructs its validator via `new RegExp(...)` from `pred_pattern`.
  No operator literal or regex source is hand-typed in the template.

  The regex is portable with **one deterministic transform**: Python named groups
  `(?P<dim>…)` → JS `(?<dim>…)`. Everything else in `_PRED_PATTERN` (`\w \s \S \-`, the
  `>=|<=|==|!=|<|>` alternation, lazy `*?`, `^…$` anchors) is byte-identical in the JS
  engine. The one semantic gap — Python `\w` is Unicode, JS `\w` is ASCII — is moot here
  because the dimension-name normalization AC restricts names to `[a-z0-9-]`. A ~3-line
  `_py_pattern_to_js(pattern)` helper performs the named-group rewrite and is unit-tested
  directly.

- **Logic — shadow / catch-all / eval — is pinned by a conformance corpus.** The
  validator's behavioral logic (`_detect_shadows`, catch-all detection, `_eval_predicate`
  numeric coercion) is algorithm, not data, so it cannot be stamped; it must be
  re-expressed in JS. To stop *that* half from drifting, add a checked-in fixture of
  `(rule_table, scores) → expected_target` and `(rule_table) → expected_shadow_warnings`
  cases. The Python tests assert it against `evaluate_rules` / `_detect_shadows`; the same
  file is the contract a node JS test consumes (the standard shared-conformance-corpus
  approach for unavoidable cross-language logic).

- **Drift guard.** A test asserts the HTML-embedded `all_ops` / `ordered_ops` equal the
  Python sets and that the translated regex matches the predicate corpus identically to
  `_PRED_PATTERN`, so a grammar change that isn't propagated fails CI.

**Bonus consolidation (tracked as ENH-2334):** once `grammar_spec()` is public,
repoint `route_table.py`'s hand-listed operator string and `_COND_PATTERN` derivation
at it, closing the pre-existing Python↔Python drift. Split out as **ENH-2334** so it
isn't lost if FEAT-2301 ships without the optional repoint.

### UI presentation: action-grouped cards (decided 2026-06-26)

Early sketches used a literal 2-D grid (rows = rules, columns = dimensions + a
final `→ Action` column). An interactive mockup review replaced that with an
**action-grouped card layout**, which read clearer for non-FSM-expert authors:

- **Rules grouped by outcome.** Each action-state is a card ("`light_repair`
  happens when…"); rules targeting it stack as alternative situations. The outcome
  reads first and the wide grid of empty `—` cells is gone.
- **"Everything else →" fallback.** The catch-all is a visually distinct,
  non-deletable footer card phrased as a sentence — not a pinned `*` row that scans
  as missing data. Still emitted last in the YAML rule list.
- **Global precedence stays visible.** Every rule carries a sequence badge
  (#1, #2, …) for the single top-to-bottom first-match-wins order across all cards;
  reorder via drag or ↑/↓. This stops action-grouping from hiding precedence.
- **Friendly inline validation.** Plain-language messages, not color alone — a
  shadowed rule reads "can never fire — rule #N above already matches everything
  this would"; a zero-condition rule is flagged as matching everything.
- **Action reassignment via dropdown, not card-drag.** Card-drag was considered
  and rejected: the discoverability / touch / a11y cost outweighs the benefit when
  an accessible menu is needed as a fallback regardless.

The error-class-unrepresentability argument in Motivation is unchanged — cards
enforce the same invariants (typed operators, forced `terminal`/`next:`, generated
`route:` + catch-all) the grid would have. A reference interactive mockup of this
layout (action cards + fallback footer + live shadow validation) was built during
the 2026-06-26 review.

### Generated YAML shape (Decision Table mode)

Matches `policy-refine.yaml`: `import:` (`lib/policy-router.yaml` + optionally
`lib/rubric-router.yaml`), `context` (`subject`, `rubric_dimensions`,
`policy_rules`), `initial: score`, and the `score → parse_scores → policy_dispatch`
pipeline with a `route:` map covering every action token plus `_:` and `_error:`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**API correction — `load_design_tokens` actual signature** (`design_tokens.py:160`):
```python
def load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None:
```
`base_path` is not a parameter — it is derived internally as `config.project_root / config.design_tokens.path`. The emit path must pass a `BRConfig` instance (from `little_loops.config.core`), not a raw path. Returns `None` when tokens are disabled or the profile directory is missing.

**`_`-prefix filter required in `render_as_css_vars_themed`**: `render_as_css_vars` (line 320) does NOT filter `_wcag_spot_check.*` and `_note` metadata keys — they land in the `:root` block as `--_wcag_spot_check-...` properties. The themed variant must skip keys where `name.startswith("_")`.

**Implementation sketch for `render_as_css_vars_themed`** (extending `render_as_css_vars` at `design_tokens.py:320`):
```python
def render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str:
    def _block(scope: str, tokens: DesignTokens) -> str:
        lines = [f"{scope} {{"]
        for name, value in sorted(tokens.resolved.items()):
            if name.startswith("_"):
                continue
            lines.append(f"  --{name.replace('.', '-')}: {value};")
        lines.append("}")
        return "\n".join(lines)
    return _block(":root", light) + "\n" + _block("[data-theme=dark]", dark)
```

**Rubric mode required form fields** (from `lib/rubric-router.yaml` public interface):
- `context.subject` — what is being evaluated
- `context.rubric_dimensions` — pipe-separated names (e.g. `"clarity|completeness|feasibility"`)
- `context.threshold_high` — integer string (default `"85"`)
- `context.threshold_medium` — integer string (default `"65"`)

**Import order for generated YAML**: `lib/rubric-router.yaml` MUST appear before `lib/policy-router.yaml` in the `import:` block (verified from `policy-refine.yaml`).

**`RouteConfig` serialization** (`fsm/schema.py`, `RouteConfig.to_dict()`): writes `default → "_"` and `error → "_error"`. The YAML serializer must follow this convention — these sentinel keys are not arbitrary strings.

**JS validation grammar** — stamped at emit time from `fsm/policy_rules.grammar_spec()`
(see "Grammar as single source" in Proposed Solution), **not** hand-re-implemented. For
reference, the underlying constants in `fsm/policy_rules.py:27–34`:
- Ordered ops (require `float(value)` parse, raise on non-numeric): `>=, <=, <, >`
- String-value ops (accept any string): `==, !=`
- Predicate regex: `/^([\w][\w\s\-]*?)\s*:\s*(>=|<=|==|!=|<|>)\s*(\S.*?)$/`
- Grid cell format (compound grid, `route_table.py`): `<op><value>` with no dim or colon — the column header supplies the dim
- Catch-all row (grid): ALL dim cells ∈ `{"*", "", "—", "-"}` AND at least one equals `"*"`
- Shadow rule detection: rule `i` is shadowed when earlier rule `j` has predicate-set ⊆ rule `i`'s predicate-set (and `j`'s set is non-empty); OR when `j` is a catch-all
- Do NOT confuse with evaluator operators (`eq/ne/lt/le/gt/ge` word-form in `fsm/evaluators.py`) — entirely separate namespace

**MR-4 dead-end detection** (`fsm/validation.py`, `_validate_partial_route_dead_end()`): flagged when `action_type` is `"prompt"` or `"slash_command"`, AND `next == null`, AND `route == null`, AND `on_yes != null`, AND (`on_no == null` OR `on_partial == null`). The builder makes this unrepresentable by requiring each action state to declare either `terminal: true` or a `next:` target — so builder output should never trigger this warning.

**Exact Python constant names** (`fsm/policy_rules.py:27–28`):
```python
_ORDERED_OPS: frozenset[str] = frozenset({">=", "<=", "<", ">"})
_ALL_OPS: frozenset[str] = frozenset({">=", "<=", "==", "!=", "<", ">"})
```
The JS validation grammar should mirror these exact sets. `_ORDERED_OPS` → require `parseFloat(value)` (numeric coercion error class); `_ALL_OPS \ _ORDERED_OPS` → accept any string value.

**`_PRED_PATTERN` named capture groups** (`fsm/policy_rules.py:32`): the regex uses named groups `(?P<dim>...)`, `(?P<op>...)`, `(?P<value>...)`. The JS equivalent should replicate these same three groups (dim, op, value) so grid-cell format `<op><value>` (column-header supplies the dim) is parsed correctly.

**`DesignTokens.resolved` type confirmed** (`design_tokens.py:33`): declared as `dict[str, str]` — all values are string-coerced via `str()` in `_resolve_value`. The `render_as_css_vars_themed` implementation sketch using `{value}` directly (no conversion) is correct.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — add `render_as_css_vars_themed(light, dark)` (scoped two-theme emit; optional multi-profile variant)
- `scripts/little_loops/fsm/policy_rules.py` — add a public `grammar_spec()` accessor over `_ORDERED_OPS` / `_ALL_OPS` / `_PRED_PATTERN.pattern` so the builder's JS grammar is stamped from a single source (not hand-copied). Optionally repoint `fsm/route_table.py`'s hand-listed operator string (`route_table.py:455`) + `_COND_PATTERN` at it to close the pre-existing in-tree duplication (tracked separately as **ENH-2334**).

### New Files
- `scripts/little_loops/cli/artifact.py` (or `cli/artifact/__init__.py`) — top-level `main_artifact` dispatcher with argparse subparsers; routes `policy-builder` to `artifact/policy_builder.py`
- `scripts/little_loops/cli/artifact/policy_builder.py` — core emit logic for the policy-builder subcommand; stamps the active design-token profile into the generated file. Modeled on `cli/schemas.py` `main_generate_schemas` (63 lines).
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — source template stamped with resolved token CSS vars at generation time; checked in as package data, not as a pre-built output artifact
- Output: `<artifacts.default_output_dir>/policy-router-builder.html` (default: CWD); `--output <path>` overrides. No checked-in output artifact. Filename `policy-router-builder.html` is fixed for v1; future builder subcommands use their own names.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/policy-router.yaml` — consumed by generated loops (no change)
- `scripts/little_loops/loops/lib/rubric-router.yaml` — consumed in Rubric mode (no change)
- `scripts/little_loops/loops/policy-refine.yaml` — canonical reference for the generated YAML shape (Decision Table mode)
- `scripts/little_loops/loops/rubric-refine.yaml` — reference implementation for Rubric mode output shape (parallel to `policy-refine.yaml`; use as the pattern for Rubric mode YAML generation)
- `scripts/little_loops/fsm/policy_rules.py`, `scripts/little_loops/fsm/route_table.py` — canonical grammar/validation the builder's JS must mirror (and defer to via `ll-loop validate`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — second existing caller of `load_design_tokens` + `render_as_prompt_context` (~line 523/531), alongside `run.py`; both follow the `BRConfig`-based load convention the emit path must reuse [Agent 1/2]
- `scripts/little_loops/config/features.py` — `DesignTokensConfig` dataclass defines the `active` / `active_theme` keys the loader resolves; the emit path reads the profile through this [Agent 1]
- `scripts/little_loops/config/core.py` — `BRConfig` aggregator loads `design_tokens` from `.ll/ll-config.json`; `load_design_tokens(config)` requires a `BRConfig` instance, not a raw path [Agent 1]
- NOTE (negative finding): the runner callers (`run.py`, `lifecycle.py`) only call `render_as_prompt_context`, never `render_as_css_vars`. The FEAT-2301 emit path is the **first executed caller of the CSS-var render path** — there is no precedent caller for `render_as_css_vars` / `render_as_css_vars_themed` to copy. [Agent 2]

### Registration / Manifest

> **Selected:** `ll-artifact policy-builder` — first subcommand of a new `ll-artifact` top-level CLI. `ll-artifact` becomes the durable namespace for all little-loops artifact generation (HTML builders, diagrams, exporters, etc.). Supersedes the earlier `ll-emit-builder` standalone decision (2026-06-25); updated 2026-06-25.

**Registration touchpoints for `ll-artifact`:**
- `scripts/pyproject.toml` — `ll-artifact = "little_loops.cli:main_artifact"` in `[project.scripts]` [Agent 2]
- `scripts/little_loops/cli/artifact.py` (or `cli/artifact/__init__.py`) — top-level argparse dispatcher with `subparsers`; delegates `policy-builder` to `artifact/policy_builder.py` [Agent 2]
- `scripts/little_loops/cli/__init__.py` — new import + `__all__` entry for `main_artifact` [Agent 2]
- `docs/reference/CLI.md` — new `### ll-artifact` section with `#### ll-artifact policy-builder` subsection [Agent 2]
- `.claude/CLAUDE.md` — new "CLI Tools" bullet for `ll-artifact` [Agent 2]

_Future subcommands (e.g. `ll-artifact loop-diagram`, `ll-artifact decision-table`) add only a new `artifact/` module + a dispatch arm — no new pyproject entries or `__all__` exports needed._

_Note: `ll-generate-schemas` / `ll-generate-skill-descriptions` remain as-is (release/maintainer utilities); `ll-artifact` owns interactive/visual artifact generation. The distinction: `ll-generate-*` produces machine-consumed artifacts (JSON schemas, description strings); `ll-artifact *` produces human-facing artifacts (HTML builders, diagrams)._

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` (FEAT-1023) — precedent for self-contained inline-CSS/JS HTML with an embedded light/dark toggle and design-token injection
- `render_as_css_vars` / `render_as_prompt_context` in `design_tokens.py` — existing render helpers to follow

### Tests
- `scripts/tests/` — unit test for `render_as_css_vars_themed` (both scoped blocks present, references resolved to hex)
- `scripts/tests/` — unit test for `grammar_spec()` (returns `sorted(_ALL_OPS)` / `sorted(_ORDERED_OPS)` and `_PRED_PATTERN.pattern`) and for `_py_pattern_to_js` (named-group rewrite; the translated regex round-trips a predicate corpus identically to `_PRED_PATTERN`)
- `scripts/tests/` — grammar drift-guard: assert the operator sets embedded in generated HTML equal `sorted(_ALL_OPS)` / `sorted(_ORDERED_OPS)`, and the emitted regex matches the predicate corpus identically to `_PRED_PATTERN`
- `scripts/tests/fixtures/` — checked-in policy-rule conformance corpus (`(rule_table, scores) → expected_target`, `(rule_table) → expected_shadow_warnings`) consumed by the Python tests against `evaluate_rules` / `_detect_shadows`; same file is the contract for a future JS validator test
- Smoke test that a builder-generated YAML passes `ll-loop validate` (catch-alls present, route map complete, no MR-4 dead-ends)

_Wiring pass added by `/ll:wire-issue` — concrete files + patterns to follow:_
- `scripts/tests/test_design_tokens.py` — UPDATE: add `render_as_css_vars_themed` to the named import block (~line 10), add a `TestRenderAsCssVarsThemed` class modeled on the existing `TestRenderAsCssVars` (reuse its `_write_tokens` / `_make_config` helpers; assert `:root {` AND `[data-theme=dark] {` blocks, hex-resolved values, distinct light vs dark values). No `__all__` / snapshot exists, so the new export breaks nothing. [Agent 3]
- For an integration-level themed test against a real bundled profile, follow `test_enh1768_profile_system.py`'s `_copy_templates()` pattern (`shutil.copytree(TEMPLATES_DIR, …)` then `load_design_tokens(config, theme="light"|"dark")`). [Agent 3]
- Smoke test pattern for builder YAML → `ll-loop validate`: lowest-level is `test_fsm_fragments.py` (`load_and_validate` + filter `ValidationSeverity.ERROR`, cf. `test_policy_refine_loop_validates`); mid-level is `test_ll_loop_commands.py`'s `cmd_validate(...)` returning `0`. [Agent 3]
- If an emit subcommand is added, test it via the `cmd_<name>(loop, argparse.Namespace(), loops_dir, Logger(use_color=False))` + `capsys` pattern in `test_ll_loop_commands.py`. [Agent 3]
- Tests that patch `little_loops.design_tokens.load_design_tokens` by module path (`test_ll_loop_program_md.py:323`, `test_cli_loop_lifecycle.py:832`) are UNAFFECTED by the new function — no update needed. [Agent 2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`TestRenderAsCssVarsThemed` — two-theme file setup**: `_write_tokens` writes only one theme file (`themes/<theme_name>.json`) and returns the `token_dir` path. The test must write the second theme file manually before loading:
  ```python
  token_dir = _write_tokens(tmp_path, primitives={"color": {"bg": {"light": "#FFF"}}}, theme_name="light", theme={"color": {"bg": "#FFF"}})
  (token_dir / "themes" / "dark.json").write_text(json.dumps({"color": {"bg": "#000"}}))
  config = _make_config(tmp_path)
  light = load_design_tokens(config, theme="light")
  dark = load_design_tokens(config, theme="dark")
  assert light is not None and dark is not None
  output = render_as_css_vars_themed(light, dark)
  assert ":root {" in output
  assert "[data-theme=dark] {" in output
  ```
- **Smoke test — `validate_fsm` is a required second step**: Step 12's wiring note says "`load_and_validate` + filter `ValidationSeverity.ERROR`" but `load_and_validate` returns `(fsm, fragment_warnings)`; the rule-checking violations come from a **separate** `validate_fsm(fsm)` call. All three imports are needed (exact pattern from `test_fsm_fragments.py:2397` `test_policy_refine_loop_validates` and `:2277` `test_rubric_refine_loop_validates`):
  ```python
  from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

  fsm, _ = load_and_validate(builder_yaml_path)
  errors = validate_fsm(fsm)
  error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
  assert not error_list, f"builder YAML validation errors: {[str(e) for e in error_list]}"
  ```

- **Inline import pattern for `validate_fsm`**: `load_and_validate` and `validate_fsm` are imported **inside** each test method in `test_fsm_fragments.py`, not at the file's top-level import block. The file's top-level imports only cover `_deep_merge` and `resolve_fragments`. Replicate this inline pattern in the smoke test:
  ```python
  def test_builder_yaml_validates(tmp_path):
      from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm
      # ... generate builder YAML into tmp_path ...
      fsm, _ = load_and_validate(builder_yaml_path)
      errors = validate_fsm(fsm)
      error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
      assert not error_list, f"builder YAML validation errors: {[str(e) for e in error_list]}"
  ```

- **`rubric-refine.yaml` structural differences vs `policy-refine.yaml`** (critical for Rubric mode YAML generation):
  - Extra top-level keys in `rubric-refine.yaml`: `category: quality`, `input_key: subject`, `required_inputs: ["subject"]` — these are absent from `policy-refine.yaml`
  - `import:` block: only `lib/rubric-router.yaml` (no `lib/policy-router.yaml`)
  - No `policy_rules` key in `context`; no `route:` map anywhere in the file
  - Route states use `on_yes`/`on_no` binary routing; `policy-refine.yaml` uses a `route:` map with `_:` / `_error:` keys
  - Repair states reference `${captured.scores.output}` to inline rubric scores in the repair action prompt
  - Builder Rubric mode output should include `category`/`input_key`/`required_inputs` if the generated YAML is intended to be directly runnable by `ll-loop run`

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add a "Visual builder" section cross-linking the artifact and contrasting it with `ll-loop edit-routes` (greenfield vs round-trip)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` (~line 846, the `DesignTokensConfig` "cross-cutting input to artifact-generating loops" paragraph) — add a note about the CSS-var themed render path / HTML builder artifact, if the builder is described architecturally [Agent 2]
- `docs/reference/API.md` (`DesignTokensConfig` section, ~lines 176–189) — NEGATIVE finding: documents config keys only, no function-level entries for `design_tokens` render helpers; under the existing pattern no update is required for `render_as_css_vars_themed` [Agent 2]
- (Emit-path docs — `CLI.md`, `LOOPS_GUIDE.md`, `LOOPS_REFERENCE.md`, `.claude/CLAUDE.md` — are listed under "Registration / Manifest" above, gated on the emit-path choice.)

### Configuration
- Reads `design_tokens.active` / `design_tokens.active_theme` from `.ll/ll-config.json` (existing keys; no change)
- **New config key**: `artifacts.default_output_dir` (string, default `"."`) — default output directory for `ll-artifact` subcommands; `--output` flag takes precedence at runtime. Future subcommands share this namespace. _(2026-06-25 lockdown decision)_

_Wiring pass added by `/ll:wire-issue` — updated 2026-06-25:_
- `config-schema.json` (`"design_tokens"` block, ~lines 1440–1486) — both `active` (default `"default"`) and `active_theme` (default `"dark"`) are already defined; no change needed for design-token keys. [Agent 1/2]
- `config-schema.json` — **ADD** a new top-level `"artifacts"` block: `{ "type": "object", "properties": { "default_output_dir": { "type": "string", "default": "." } }, "additionalProperties": false }`. This is the only schema change required. _(2026-06-25 lockdown decision)_

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional files to reference**:
- `scripts/little_loops/cli/loop/run.py` (~line 195) — canonical token-injection pattern: `load_design_tokens(_config)` → `render_as_prompt_context` stamped into `context["design_tokens_context"]`. The emit path for the HTML builder should follow the same `BRConfig`-based loading pattern but call `render_as_css_vars_themed` instead.
- `scripts/little_loops/cli/loop/edit_routes.py` — `cmd_edit_routes()`, `CompoundGridRenderer`, `PolicyRuleExtractor`, `PolicyRuleApplier` — the existing round-trip text editor; the greenfield builder must not overlap with it.
- `scripts/little_loops/fsm/validation.py` — `_validate_partial_route_dead_end()` + `_is_llm_judged()` — MR-4 logic the builder makes structurally unrepresentable.
- `scripts/little_loops/fsm/schema.py` — `RouteConfig` dataclass with `routes`, `default`, `error` fields and `from_dict()` / `to_dict()` — canonical `route:` map serialization.

**Test files to pattern after for `render_as_css_vars_themed`**:
- `scripts/tests/test_design_tokens.py` — existing unit tests for `render_as_css_vars`, `render_as_prompt_context`, `load_design_tokens`
- `scripts/tests/test_enh1768_profile_system.py` — multi-profile loading tests (`warm-paper`, `editorial-mono`)

**FEAT-1023 precedent clarification**: `html-website-generator.yaml` generates HTML via LLM prompt states (the LLM writes `index.html`). `design_tokens_context` injection at `run.py:195` feeds the LLM semantic names. FEAT-2301's builder is a **Python-generated** static artifact — a different architectural pattern; no LLM state writes the HTML.

### Decision Rationale

Initial decision by `/ll:decide-issue` on 2026-06-25: **standalone CLI `ll-emit-builder`**.

**Superseded 2026-06-25**: Renamed to `ll-artifact policy-builder` — first subcommand of a new `ll-artifact` top-level CLI.

**Revised Reasoning**: Artifact generation is a broad, recurring concern in little-loops (HTML builders, diagrams, exporters, etc.). Rather than proliferating `ll-generate-*` / `ll-emit-*` / `ll-build-*` standalone commands, `ll-artifact` establishes a durable namespace where all human-facing artifact generators live as subcommands. The registration cost is one more level of argparse dispatch compared to a standalone tool, but future artifact generators (`ll-artifact loop-diagram`, etc.) cost only a new module + dispatch arm — no additional `pyproject.toml` entries. The distinction from existing `ll-generate-*` tools: those produce machine-consumed artifacts (JSON schemas, description strings); `ll-artifact *` produces human-facing, interactive artifacts (HTML builders, visual tools).

The original scoring across `ll-loop` subcommand / standalone / built-in-loop-YAML still holds — the `ll-artifact` shape is the standalone option with a thin dispatcher layered on top. `cli/schemas.py` `main_generate_schemas` (63 lines) remains the template for the `policy_builder.py` core module; only the top-level entry point changes from `main_emit_builder` to `main_artifact`.

**Decision impact on the rest of the issue**: Implementation Steps 9–10 resolve to the **`ll-artifact` subcommand** registration arm. See Registration / Manifest section above for the full touchpoint list.

## Implementation Steps

1. Add `render_as_css_vars_themed(light, dark)` to `design_tokens.py` (+ optional multi-profile variant); unit-test resolution and scoping.
2. Build the one-page HTML: mode switch (Rubric / Decision Table), identity fields, dimension chips (typed), reactive decision grid with pinned catch-all + drag-reorder, derived action-state list with forced terminal/next.
3. Add a public `grammar_spec()` to `fsm/policy_rules.py` and a `_py_pattern_to_js` named-group transform; stamp the operator sets + predicate regex into the HTML as a JSON `<script>` block. Implement client-side validation that builds its operator dropdown / numeric-coercion branch from the stamped data and re-expresses the *logic* (shadow, gap, missing catch-all, unknown action), colored from token semantics. Add the conformance corpus + grammar drift-guard test.
4. Implement the YAML serializer + live preview + Copy/Download + printed `ll-loop validate <name>` hint.
5. Wire the embedded theme toggle (precedence: prefers-color-scheme → config active_theme → localStorage) and optional profile picker.
6. Add the emit/stamp path: read `artifacts.default_output_dir` from `BRConfig` (or `--output` override), write `<dir>/policy-router-builder.html` with the active profile's resolved token CSS vars inlined via `render_as_css_vars_themed`.
7. Smoke-test a generated YAML through `ll-loop validate`.
8. Document in `POLICY_ROUTER_GUIDE.md`; cross-link from ENH-2299's wizard completion message as an alternative table-authoring surface.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Emit-path shape: DECIDED — `ll-artifact policy-builder`** (supersedes `ll-emit-builder` standalone decision; 2026-06-25). Implement `scripts/little_loops/cli/artifact/policy_builder.py` (core emit logic) + `scripts/little_loops/cli/artifact.py` (top-level `main_artifact` dispatcher with argparse subparsers). Core module modeled on `cli/schemas.py` `main_generate_schemas` (63 lines).
10. **Register `ll-artifact`**: add `ll-artifact = "little_loops.cli:main_artifact"` to `scripts/pyproject.toml` `[project.scripts]` + `from little_loops.cli.artifact import main_artifact` import and `"main_artifact"` entry in `scripts/little_loops/cli/__init__.py` `__all__` + a `### ll-artifact` section (with `#### ll-artifact policy-builder` subsection) in `docs/reference/CLI.md` + a "CLI Tools" bullet in `.claude/CLAUDE.md` + add the top-level `"artifacts"` block to `config-schema.json` with `"default_output_dir"` (string, default `"."`, `additionalProperties: false`).
11. **Update `scripts/tests/test_design_tokens.py`** — add `render_as_css_vars_themed` to the import block and a `TestRenderAsCssVarsThemed` class (model on `TestRenderAsCssVars`, reuse `_write_tokens`/`_make_config`).
12. **Add the `ll-loop validate` smoke test** following `test_fsm_fragments.py` (`load_and_validate` + ERROR-severity filter) or `test_ll_loop_commands.py` (`cmd_validate(...) == 0`).
13. Add a `cmd_policy_builder` test in `test_ll_loop_commands.py` using the `argparse.Namespace()` + `Logger(use_color=False)` + `capsys` pattern; assert the output file is written to the expected path.
14. **Update `docs/ARCHITECTURE.md`** (~line 846) if the builder is described as an architectural artifact.

## Impact

- **Priority**: P3 — discoverability/authoring quality-of-life; the pattern already works via hand-authoring and `edit-routes`. No urgent unblock.
- **Effort**: Medium — one self-contained HTML artifact + a ~15-line token helper + an emit path + tests/docs. No FSM runtime changes.
- **Risk**: Low — purely additive; runtime, fragments, and existing wizard/edit-routes paths are untouched. The JS-drift risk is now structurally reduced, not just deferred: the grammar *data* (operator sets + regex) is stamped from `policy_rules.grammar_spec()` so it cannot drift, the *logic* half is pinned by a shared conformance corpus, and `ll-loop validate` remains the authoritative gate as a backstop.
- **Breaking Change**: No

## Labels

`feature`, `loops`, `policy-router`, `design-tokens`, `html`, `tooling`

## Status

**Open** | Created: 2026-06-26 | Priority: P3

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-26 (re-run; scores stable)_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 68/100 → below threshold

### Outcome Risk Factors
- **JS grammar drift** (mitigated): the grammar *data* (operator sets + predicate regex) is no longer hand-copied — it is stamped from a new public `policy_rules.grammar_spec()` at emit time and guarded by a test asserting the HTML-embedded ops equal the Python sets, so the data half cannot silently drift. The *logic* half (shadow detection, catch-all, numeric-coercion eval) must still be re-expressed in JS but is pinned by a shared conformance corpus; `ll-loop validate` remains the authoritative backstop. Residual surface is the JS logic re-expression, bounded by the corpus.
- **No automated JS test coverage**: Interactive browser behavior (drag-reorder, reactive decision grid, YAML serializer, theme toggle) requires manual verification. The JS layer is the dominant complexity locus and sits outside pytest's reach.
- **Dimension-name normalization divergence**: `policy_parse_scores` keys score files by a lowercase + whitespace→hyphens normalized name, but `evaluate_rules` matches predicate dims by exact string. A mixed-case/spaced dimension yields a silently-inert predicate that passes base `ll-loop validate` (no liveness check). ENH-2309 catches it at the gate only while its referenced-raw / scored-normalized asymmetry holds. Mitigated by the new normalization acceptance criterion (builder normalizes header/scoring-instruction/predicate identically, or restricts input to `[a-z0-9-]`); functional correctness of generated YAML depends on it.
- ~~**Output artifact path not finalized**~~ — _resolved 2026-06-25_: generated on-demand at `<artifacts.default_output_dir>/policy-router-builder.html` (default CWD); `--output` override; no checked-in artifact. `config-schema.json` gets a new `"artifacts"` block.

## Session Log
- `grammar single-source decision` - 2026-06-26 - Replaced hand-re-implementation of the JS predicate grammar with emit-time stamping from a new public `policy_rules.grammar_spec()` (operator sets + regex), a `_py_pattern_to_js` named-group transform, a drift-guard test, and a shared shadow/eval conformance corpus; flagged the pre-existing `route_table.py:455` operator duplication for consolidation. Downgraded the "JS grammar drift" outcome risk from open maintenance surface to "data half eliminated, logic half bounded".
- `UI design decision` - 2026-06-26 - Adopted action-grouped rule cards + "Everything else →" fallback footer + friendly inline validation (plain-language shadow/zero-condition messages); rejected card-drag for action reassignment (dropdown instead). From a Cowork interactive-mockup review.
- `boolean-dim decision` - 2026-06-26 - Closed the dead boolean/string-dimension hole: boolean chips compile to a numeric 0/100 encoding (`==true`→`>=50`, dim emitted into `rubric_dimensions`), keeping the feature live with no fragment-runtime change. Spun off ENH-2309 (validator rule flagging unscored policy dimensions).
- `/ll:confidence-check` - 2026-06-26 - `d8445ed0-55b6-4efb-8cb4-0c6d5010e8b9.jsonl`
- `/ll:refine-issue` - 2026-06-26T19:31:35 - `bd56b623-ba39-47c4-bd64-a420b910b8ec.jsonl`
- `/ll:confidence-check` - 2026-06-26 - `6ab2d0ba-0319-4ff2-829a-5b6224e5e954.jsonl`
- `/ll:confidence-check` - 2026-06-25 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:refine-issue` - 2026-06-26T01:31:25 - `af981b92-c03e-478c-b61b-511a0b83ff43.jsonl`
- `naming decision` - 2026-06-25 - Renamed emit path from `ll-emit-builder` (standalone) to `ll-artifact policy-builder` (subcommand of new `ll-artifact` CLI); `ll-artifact` established as the durable namespace for all human-facing artifact generation
- `/ll:decide-issue` - 2026-06-26T01:11:10 - `81cb10d8-c7ce-4642-bb0e-3ecbdb6e258a.jsonl`
- `/ll:wire-issue` - 2026-06-26T01:01:02 - `f9198542-abe8-4adb-a324-052b78ba3060.jsonl`
- `/ll:refine-issue` - 2026-06-26T00:51:56 - `d6038229-795a-45ee-8ef3-49cfaf152cac.jsonl`
- `/ll:format-issue` - 2026-06-26T00:42:29 - `dace4845-a459-498c-a40e-691d358094f6.jsonl`
- `/ll:capture-issue` - 2026-06-26T00:35:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ac50ab5-0773-4ba5-b0ed-58ad5b368658.jsonl`
