---
id: FEAT-3474
type: FEAT
title: Web GUI for issue-lifecycle FSM loops driven by frontmatter rules
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T17:11:03Z'
parent: EPIC-3299
---

# FEAT-3474: Web GUI for issue-lifecycle FSM loops driven by frontmatter rules

## Summary

A self-contained `.html` GUI (`file://`, no install) that lets a user author their
own simplified issue-lifecycle FSM loop — prepare, refine, gate, implement, verify
— driven by an Issue file's YAML frontmatter, without hand-writing FSM YAML. This
is a **third grammar/mode** (`issue_lifecycle`) alongside FEAT-2301's existing
`decision_table` and `rubric` modes on the same self-contained-HTML builder shell
(EPIC-3299), not a generator for `scripts/little_loops/loops/autodev.yaml` itself.

The emitted artifact is a **thin standalone loop YAML with the same shape
`decision_table` mode already emits** (imports `lib/policy-router.yaml`, carries
the rule table in `context.policy_rules`, dispatches via `policy_table_dispatch`),
with one substitution: the LLM `rubric_score` + `policy_parse_scores` states are
replaced by a single **deterministic frontmatter scorer** state that reads the
issue file and writes the per-dimension score files the dispatch fragment
already consumes. One issue per run; no queue/retry/rate-limit machinery.

## Current Behavior

No GUI exists for authoring an issue-lifecycle-shaped loop. Today a user who wants
an autodev-like loop for their own issue conventions must either hand-write FSM
YAML from scratch, or copy and heavily edit `autodev.yaml` (a large, tightly
coupled file with little-loops-specific assumptions throughout).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The self-contained builder shell this issue extends already dispatches on `model.mode` via string-literal comparison, not a registry: `serializeLoopYaml()` (`scripts/little_loops/templates/policy_builder_core.mjs:645`) returns `_serializeRubric(model)` only when `model.mode === "rubric"`; every other value falls through to `_serializeDecisionTable(model)` with no error path. `blankModel()` (`:300`) and `seedExample()` (`:247`) in the same file take no `mode` argument and always hardcode `mode: "decision_table"` — there is no existing per-mode branch in either function to extend by example.
- Roughly ten additional `model.mode`/`state.mode` comparisons live in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline script (`computeSummary`, `renderTryIt`, `updateTryIt`, `renderMessages`, `renderAll`, `applyModeVisibility`, the `#mode-switch` change handler, `#start-blank-btn`'s click handler) — a third mode's UI wiring touches this file, not only `policy_builder_core.mjs`.
- `cmd_policy_builder()` in `scripts/little_loops/cli/artifact/policy_builder.py` assembles the emitted artifact by loading `grammar_spec()` and `_load_skill_catalog()`, then stamping four literal placeholders into the read `.tmpl`/`.mjs` text (theme CSS vars, grammar-spec JSON, skill-catalog JSON, the core JS itself) via sequential `str.replace()` calls — there is no general templating engine and no `--mode` CLI flag; mode is a pure runtime/browser concept never inspected server-side. `_load_skill_catalog()` returns a flat `list[dict]` of `{"name": str, "description": str}` with no verb/category field to filter by lifecycle stage.

_Added by review — 2026-09-16 — based on codebase analysis:_

- `ll-issues show --json` (the deterministic scorer precedent used by `loops/rn-remediate.yaml:351-368`) returns a **fixed, curated key set** and **renames** fields: frontmatter `confidence_score` → JSON `confidence`, `outcome_confidence` → `outcome`. Arbitrary custom frontmatter keys (e.g. `severity`, `review_status`) are **not** passed through. It therefore cannot back the custom-field acceptance criterion; the scorer must read raw frontmatter via `little_loops.frontmatter.parse_frontmatter(content, coerce_types=True)` (`scripts/little_loops/frontmatter.py:255`).
- The builder's dimension types are exactly `numeric` and `boolean` (`.tmpl:163-166`); there is no `string` type. `_serializeRulesText()` (`policy_builder_core.mjs:392`) compiles boolean predicates to numeric `>=50`/`<50` because the LLM rubric encodes booleans as 100/0 (`.tmpl:169` help text). The engine itself already supports string `==`/`!=` with numeric-first coercion (`fsm/policy_rules.py:188-225`), and ordered ops require numeric values at parse time.
- `policy_table_dispatch` (`lib/policy-router.yaml:140-184`) is scorer-agnostic: it reads every `rubric-dim-<name>.txt` in `${context.run_dir}/` plus optional `rubric-aggregate.txt`, coercing each to float when possible and leaving it a string otherwise. Dimension file names are lowercased with spaces→hyphens (`normalizeDimName()`, `policy_builder_core.mjs:90`); underscores pass through unchanged, so `confidence_score` → `rubric-dim-confidence_score.txt`.
- Emitted outcome states are produced by `_outcomeStateLines()` (`policy_builder_core.mjs:458-482`): `actionType` is one of `none | prompt | slash_command`, and `slash_command` bodies are emitted verbatim as `action: <body>`. The lifecycle verbs therefore map cleanly onto `slash_command` outcomes whose body embeds an issue-identity context variable.
- `loops/rn-remediate.yaml:11-36` is the precedent for a per-issue loop: `issue_id` is a `with:` parameter and the loop is run as `ll-loop run rn-remediate --context issue_id=<ID>`.

## Expected Behavior

A new `issue_lifecycle` mode on `policy-router-builder.html.tmpl` where:

- **Subject** is a single Issue file's YAML frontmatter (as in `.issues/*.md`),
  identified at run time by `--context issue_id=<ID>`.
- **Dimensions** in the rule builder are frontmatter fields:
  - little-loops' own built-in fields as pre-typed, pre-populated dimensions
    (see the Built-in Dimension Table below).
  - PLUS arbitrary user-declared **custom** frontmatter fields — the user names
    the key and picks a type (`numeric`, `boolean`, `string`); little-loops
    needs no prior knowledge of the field. This is the key differentiator from
    a little-loops-only tool.
  - Operators offered per type: `numeric` → all six; `boolean` → `==true` /
    `==false`; `string` → `==` / `!=` only. (`string` is a **new** builder type;
    the existing `opsForType()` only special-cases `boolean`.)
- **Actions** per rule/outcome are the five lifecycle verbs — prepare, refine,
  gate, implement, verify — each pre-bound to a default `/ll:*` slash command
  (see Verb Table) and overridable from the same emit-time skill catalog
  FEAT-2301's "run a skill" dropdown already surfaces.
- **Try it** panel accepts a pasted frontmatter block and shows which rule
  fires, using the same evaluator the emitted loop uses.
- Reuses FEAT-2301/FEAT-2390's shipped patterns (self-contained `file://`
  HTML, ordered reorderable rule list, pinned "Otherwise" footer, demoted YAML,
  seeded example, theme handling, pure-function `.mjs` core + `node --test`
  gate, jargon-denylist for on-screen labels).

### Built-in Dimension Table

| Frontmatter key | Type | Scorer encoding |
|---|---|---|
| `status` | string | verbatim |
| `priority` | string | verbatim (`P0`..`P5`) |
| `confidence_score` | numeric | verbatim |
| `outcome_confidence` | numeric | verbatim |
| `decision_needed` | boolean | `100` / `0` |
| `spike_needed` | boolean | `100` / `0` |
| `blocked_by` | numeric | list length (0 when absent/empty) |
| `deferred_reason` | string | verbatim, empty string when absent |

### Verb Table

| Verb | Default slash command (body) |
|---|---|
| prepare | `/ll:format-issue ${context.issue_id}` |
| refine | `/ll:refine-issue ${context.issue_id}` |
| gate | `/ll:confidence-check ${context.issue_id}` |
| implement | `/ll:manage-issue ${context.issue_id}` |
| verify | `/ll:verify-issues ${context.issue_id}` |

## Motivation

`autodev.yaml` (2652 lines) is little-loops' own hand-tuned production loop for
driving issues through prepare → refine → gate → implement → verify. It is not a
realistic target for a rules-GUI to reproduce faithfully — it has bespoke queue
management, decision/blocker/gate pre-flight checks, repair cycles, rate-limit
handling, and infra-vs-quality failure classification built up over dozens of
issues. But its *shape* — route an issue through lifecycle stages based on
frontmatter conditions — is a pattern other users (and other little-loops
consumers with their own issue conventions) plausibly want a smaller, self-service
version of, the same way FEAT-2301 gave non-experts a GUI for the `policy-router`
grammar instead of hand-written `route:` maps.

## Proposed Solution

Extend the existing self-contained HTML builder shell rather than building a new
one. Add a third mode literal `"issue_lifecycle"` to `policy_builder_core.mjs`
and the template's inline script. Three pieces of work:

### 1. Scorer fragment (new, in `lib/policy-router.yaml`)

Add a `frontmatter_scores` fragment alongside `policy_parse_scores`. It is a
shell state that:

- resolves `${context.issue_id}` to a path via `ll-issues path <ID>`;
- parses the file with `parse_frontmatter(content, coerce_types=True)`;
- for each `name:type` pair in `${context.frontmatter_dimensions}`
  (pipe-separated, e.g. `status:string|confidence_score:numeric|decision_needed:boolean|severity:string`)
  writes `${context.run_dir}/rubric-dim-<normalized-name>.txt` using the
  encoding rules: numeric → value as-is (missing → file not written, so the
  engine's missing-dimension semantics apply); boolean → `100`/`0` (missing →
  `0`); string → `str(value)` (missing → empty string); list-valued key with
  numeric type → `len(list)`.
- exits non-zero when the issue ID does not resolve (mirrors rn-remediate's
  BUG-2003 AC5 contract).

Booleans are encoded 100/0 so the existing `compileBooleanPredicate` path in
`_serializeRulesText()` is reused unchanged; no engine changes are needed.

### 2. Core (`policy_builder_core.mjs`)

- `blankModel()` / `seedExample()` gain a `mode` parameter (default
  `"decision_table"`, preserving today's zero-arg behaviour). The
  `issue_lifecycle` branch pre-populates `dimensions` from the Built-in
  Dimension Table and `outcomes` from the Verb Table.
- `serializeLoopYaml()` gains an explicit `mode === "issue_lifecycle"` branch
  **before** the decision-table fallback, calling `_serializeIssueLifecycle()`,
  which emits:
  - `import: [lib/policy-router.yaml]` (no `rubric-router`);
  - `with: { issue_id: {required: true} }` per the rn-remediate precedent;
  - `context.frontmatter_dimensions` and `context.policy_rules`;
  - `initial: score` → `score: {fragment: frontmatter_scores, next: policy_dispatch}`
    → `policy_dispatch` (identical route-map generation to `_serializeDecisionTable`)
    → one outcome state per verb via the existing `_outcomeStateLines()`.
- `_serializeRulesText()` and a new `opsForType`-equivalent in the core gain
  a `string` type: `==`/`!=` only, value emitted verbatim (no boolean compile).
- Dimension model shape stays `{name, type}`; no `kind` discriminator — the
  model is already open. Built-in vs custom is purely a UI concern (built-ins
  are pre-populated and their type is locked).

### 3. Template (`policy-router-builder.html.tmpl`)

- Third `<option>` on `#mode-switch`; `applyModeVisibility()` shows the
  dimensions/outcomes/rules fieldsets and a new `frontmatter-tryit-fieldset`
  for this mode, hides `threshold-fieldset`.
- `#dim-type` gains a `string` option; `opsForType()` restricts it to `==`/`!=`.
- Outcome fieldset in this mode shows the five verbs with their default
  slash-command bodies pre-filled and the existing skill-catalog dropdown as
  the override.
- Try-it: a `<textarea>` for pasted frontmatter; the page parses it with a
  minimal YAML-frontmatter reader (scalars, booleans, flow/dash lists — no
  nested maps) and runs the existing JS `evaluateRules` mirror over the
  encoded scores. This is the only new JS parser; keep it pure and covered by
  `node --test`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The generic rule-table engine (`fsm/policy_rules.py`'s `parse_rules`/`evaluate_rules`) has exactly two known consumers today: `scripts/little_loops/loops/policy-refine.yaml` (a loop supplying `context.policy_rules` as plain text, routed via the `policy_table_dispatch` fragment from `lib/policy-router.yaml`) and `ll-loop edit-routes` (`cli/loop/edit_routes.py`, a CLI editor over that same `policy_rules` text via `PolicyRuleExtractor`/`CompoundGridRenderer`/`PolicyRuleApplier` in `fsm/route_table.py`). No third consumer exists in the repo.
- Testing convention for the two existing modes: each gets its own dedicated golden model+YAML fixture pair under `scripts/tests/fixtures/policy_builder/` (`sample-decision-table.model.json`/`.yaml`, `sample-rubric.model.json`/`.yaml`). Each mode's "golden YAML validates" test is a separate, non-parametrized function (`test_golden_yaml_validates`, `test_golden_rubric_yaml_validates` in `test_policy_builder_emit.py`), while the node-gate round-trip test (`test_round_trip_yaml_validates_for_each_mode` in `test_policy_builder_node_gate.py`) is parametrized across both mode fixtures in one function.
- Mode-switcher UI convention: a single `<select id="mode-switch">` in the page header (not tabs, `.tmpl:121-124`), with per-mode visibility controlled by direct `.hidden` boolean toggles on four fixed fieldset IDs in `applyModeVisibility()` (`.tmpl:624-628`) — there is no `data-mode` attribute or CSS-scoping convention anywhere in this template.
- Jargon-denylist enforcement is a single hardcoded Python list literal inline in one test function (`test_no_internal_jargon_in_visible_markup`, `test_policy_builder_emit.py:130-135`), checked against the emitted HTML with `<script>`/`<style>`/comment blocks stripped first (`_strip_script_style_comments`, `:22-34`). There is no separate reusable jargon-validator module — a third mode's own jargon terms would need direct additions to that same inline list.
- `serializeLoopYaml()` has no explicit `"decision_table"` branch — any `model.mode` other than the literal `"rubric"` silently falls through to `_serializeDecisionTable(model)` with no error. A third mode's branch must be added explicitly ahead of that fallback.
- Full inventory of `model.mode`/`state.mode` branch sites in the template beyond the three core functions: `computeSummary` (`:265`), `renderTryIt` (`:527`, early-return decision-table-only), `updateTryIt` (`:558`, same guard), `renderMessages` (`:581`, decision-table-only unreachable-outcome check), `renderAll` (`:610`), `applyModeVisibility` (`:624-628`, toggles `.hidden` on `threshold-fieldset`/`outcomes-fieldset`/`rules-fieldset`/`tryit-fieldset`), the `#mode-switch` `onchange` handler (`:632-638`, the only place `state.mode` is reassigned from user input, driven by a two-option `<select>` at `:121-124`), and `#start-blank-btn`'s `onclick` (`:684-693`).
- Because `policy_builder_core.mjs` is stamped verbatim into the emitted HTML, every one of these dispatch sites is also byte-mirrored in `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`.
- `cmd_policy_builder()` (`policy_builder.py:56-107`) has exactly four data-injection points into the template: `/*__THEMED_CSS_VARS__*/`, `/*__GRAMMAR_SPEC_JSON__*/`, `/*__SKILL_CATALOG_JSON__*/`, `/*__BUILDER_CORE_JS__*/` (each a literal `str.replace`). This issue needs no fifth placeholder: the Built-in Dimension Table and Verb Table are constants in the core `.mjs`, not emit-time data.
- The actual `opsForType(type)` at `.tmpl:274-276` is `return type === "boolean" ? ["==true", "==false"] : GRAMMAR.all_ops;` — it special-cases only `"boolean"`; every other type string receives the full unrestricted `GRAMMAR.all_ops` set. Adding `string` requires a second branch there.
- `grammar_spec()`'s `_PRED_PATTERN` (`fsm/policy_rules.py:32-34`) matches any word-ish dimension name, not a closed enum — a GUI author can already add an arbitrary dimension name today with no allowlist check (`.tmpl:646-652`). No engine or grammar change is needed for custom fields.
- `cmd_policy_builder`'s only error handling is a single outer `try/except Exception: logger.error(...); return 1` (`policy_builder.py:65,105-107`); there is no mode-specific validation in the Python CLI layer and no `--mode` flag — mode is purely a runtime/browser `state.mode` concept. This issue keeps it that way.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/policy-router.yaml` — add the
  `frontmatter_scores` fragment (Proposed Solution §1) next to
  `policy_parse_scores`; update the header comment's fragment list and the
  "Score-source agnosticism" note to cite it as the deterministic scorer.
- `scripts/little_loops/templates/policy_builder_core.mjs` — `mode` parameter
  on `blankModel()`/`seedExample()`; `_serializeIssueLifecycle()`; explicit
  `issue_lifecycle` branch in `serializeLoopYaml()`; `string` type in
  `_serializeRulesText()`; Built-in Dimension Table and Verb Table constants;
  pure frontmatter mini-parser + encoder for Try-it.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — third
  mode option, `string` dim type, `opsForType()` branch, verb-outcome UI,
  frontmatter Try-it fieldset, and every `state.mode` dispatch site listed in
  the findings inventory.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` —
  byte-mirrored golden fixture of the full stamped template;
  `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`
  does a hard byte-diff against it, so it MUST be regenerated once the
  template changes.
- `scripts/little_loops/loops/README.md` — update the `lib/policy-router.yaml`
  row (`:217`) to list `frontmatter_scores`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/policy_builder.py` — no code change
  expected (mode is browser-side; no new placeholder). Confirm only.
- `scripts/little_loops/fsm/validation/reachability.py` —
  `_validate_policy_dimensions_scored()` (line 154) calls `parse_rules()`
  (line 184) to lint FSM policy-rule text; the emitted rule text uses the same
  grammar (string `==`/`!=`, numeric ordered ops, compiled booleans) so it
  stays compatible. Verify with `ll-loop validate` on the golden YAML.
- `scripts/little_loops/loops/policy-refine.yaml` — existing consumer of
  `policy_table_dispatch`; unaffected, but re-run its validate as a regression
  check after editing the shared fragment file.
- `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` — both
  document the existing `policy-router`/`rubric` modes and need a third entry.

### Similar Patterns
- `scripts/little_loops/loops/rn-remediate.yaml:351-377` — deterministic
  shell scorer + first-match routing over issue scores; the `frontmatter_scores`
  fragment generalizes this using raw frontmatter instead of `show --json`.
- `scripts/little_loops/loops/rn-remediate.yaml:11-36` — `with: issue_id`
  parameter contract to copy for the emitted loop.
- `scripts/tests/js/policy_validator.test.mjs` — the `node --test`
  conformance pattern the new mode's core functions must follow.

### Tests
- `scripts/tests/test_policy_builder_emit.py` — add
  `test_golden_issue_lifecycle_yaml_validates` (non-parametrized, per
  convention); extend the jargon-denylist list literal if the mode introduces
  on-screen terms.
- `scripts/tests/test_policy_builder_node_gate.py:125` — add
  `"sample-issue-lifecycle.model.json"` to the hardcoded two-entry
  `@pytest.mark.parametrize` list.
- `scripts/tests/js/policy_validator.test.mjs` — add
  `test("serializeLoopYaml matches golden issue-lifecycle fixture", ...)`,
  plus tests for the frontmatter mini-parser/encoder (booleans → 100/0, list
  → length, missing numeric → absent, missing string → empty).
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle.model.json`
  and `.yaml` — new golden fixture pair; the YAML must pass `ll-loop validate`.
- `scripts/tests/test_policy_builder_corpus.py` — add corpus cases for
  string `==`/`!=` predicates against the conformance corpus so the JS mirror
  and `evaluate_rules` agree on string handling.
- New: a pytest for the `frontmatter_scores` fragment that builds a temp
  issue file with built-in, custom, boolean, list, and missing fields, runs
  the fragment's Python body, and asserts the exact `rubric-dim-*.txt` set
  and contents (follow the fragment-testing pattern used for
  `policy_parse_scores` if one exists; otherwise extract the body to
  `little_loops.fsm.frontmatter_scores` and shell into it, matching how
  `policy_table_dispatch` imports `policy_rules`).

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add the `issue_lifecycle` mode with
  the Built-in Dimension Table, Verb Table, and encoding rules.
- `docs/ARCHITECTURE.md` § "Project-enriched artifacts" — cites the catalog
  loader as `cli/action.py:_load_skills()`; the correct symbol is
  `cli/artifact/policy_builder.py:_load_skill_catalog()`. Fix while touching
  this area.

### Configuration
- N/A — no `.ll/ll-config.json` schema changes.

## Implementation Steps

1. Add the `frontmatter_scores` fragment to `lib/policy-router.yaml`
   (extracting its Python body to an importable module if that is how the
   fragment test is written). Unit-test the encoding rules.
2. Add the `issue_lifecycle` mode to `policy_builder_core.mjs`: `mode`
   parameter on `blankModel`/`seedExample`, constants for the two tables,
   `string` type support, `_serializeIssueLifecycle`, explicit dispatch
   branch, frontmatter mini-parser/encoder. Write the golden fixture pair and
   `node --test` cases; confirm the golden YAML passes `ll-loop validate`.
3. Add the mode's UI to `policy-router-builder.html.tmpl` (mode option,
   `string` dim type, `opsForType` branch, verb outcomes with catalog
   override, frontmatter Try-it), touching every `state.mode` site in the
   inventory. Regenerate the golden HTML fixture.
4. Update the parametrize list, corpus, jargon list, loops README row, and
   docs.
5. End-to-end: author the Use Case rules in the GUI, save the YAML into a
   scratch project, run `ll-loop run <name> --context issue_id=<ID>` against
   an issue with a custom `severity` field, and confirm the expected verb
   state fires. Repeat with a missing custom field to confirm the
   "Otherwise" catch-all fires.

### Wiring Phase (added by `/ll:wire-issue`)

- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`
  once template changes land — the byte-diff test will otherwise fail
  unconditionally.
- Add `"sample-issue-lifecycle.model.json"` to the `@pytest.mark.parametrize`
  list in `scripts/tests/test_policy_builder_node_gate.py:125`.
- Add the new mode's golden fixture pair and a matching `test(...)` block in
  `scripts/tests/js/policy_validator.test.mjs`.
- Naming-collision note (no code change, awareness only): the mode literal
  `"issue_lifecycle"` is a plain string match for the pre-existing, unrelated
  production module `scripts/little_loops/issue_lifecycle.py` (issue
  status-transition helpers, imported by `parallel/orchestrator.py` and
  `cli/issues/skip.py`); grep-based searches will hit both — disambiguate in
  commit messages and comments.

## Impact

- **Priority**: P3 - self-service tooling for other little-loops consumers,
  not blocking any in-repo workflow (little-loops itself keeps hand-tuned
  `autodev.yaml`).
- **Effort**: Large - a new grammar/mode on an existing shell, one new
  fragment, a `string` dimension type, a small pure JS frontmatter parser,
  plus new `node --test` and pytest coverage.
- **Risk**: Low - additive third mode alongside `decision_table`/`rubric`;
  the new fragment is additive to `lib/policy-router.yaml`; neither existing
  mode's emitted YAML changes (verified by the existing golden fixtures).
- **Breaking Change**: No

## Design Decision: emitted-artifact shape (resolved)

**Selected:** the emitted artifact is a thin standalone loop YAML of the same
shape `decision_table` mode already emits, with the LLM scorer replaced by a
deterministic `frontmatter_scores` state. It is run per issue with
`ll-loop run <name> --context issue_id=<ID>`.

**Reasoning:** The earlier framing ("Option A: standalone FSM loop that
generates queue/retry/rate-limit states" vs. "Option B: policy config consumed
by a generic sub-loop") was a false dichotomy. `decision_table` mode already
proves the middle path: a standalone loop that is thin *because* the engine
lives in `lib/policy-router.yaml`. Neither a generic queue/retry/rate-limit
sub-loop nor per-artifact code generation of that machinery is needed, and
both are explicitly out of scope (see Non-goals). The only genuinely missing
piece is a deterministic scorer that turns frontmatter into the
`rubric-dim-*.txt` files `policy_table_dispatch` consumes; `ll-issues show
--json` cannot fill that role because it drops custom keys and renames
built-in ones, so the scorer reads raw frontmatter via `parse_frontmatter`.

**Superseded evidence retained for context:** `oracles/resolve-decision.yaml:163-181`
and `autodev.yaml:489-494` document that a `loop:` call state cannot observe a
child's rate-limit-exhaustion terminal. That gap is real but irrelevant here
because the emitted loop makes no sub-loop calls.

## Acceptance Criteria

- [ ] The GUI is a single self-contained `.html` file that opens over `file://`
  with no install step and no network dependency, matching FEAT-2301's shell.
- [ ] In `issue_lifecycle` mode the dimension list is pre-populated with the
  Built-in Dimension Table entries, each with its type locked and operators
  restricted by type (`numeric` all six; `boolean` `==true`/`==false`;
  `string` `==`/`!=`).
- [ ] A user can declare an arbitrary custom frontmatter field name with a
  chosen type (`numeric`, `boolean`, `string`) and use it as a rule dimension,
  and the emitted loop routes on it at run time without any little-loops code
  knowing the field — verified end to end against an issue file carrying a
  custom `severity` key.
- [ ] Each rule's outcome is one of the five lifecycle verbs, pre-bound to the
  Verb Table default and overridable from the emit-time skill catalog; the
  emitted state is a `slash_command` whose body references
  `${context.issue_id}`.
- [ ] Rules are ordered/reorderable and read as a first-match list with a
  pinned non-input "Otherwise" catch-all, per FEAT-2301/FEAT-2390's shipped
  shell conventions.
- [ ] The emitted YAML imports only `lib/policy-router.yaml`, declares
  `with: issue_id`, uses `frontmatter_scores` → `policy_table_dispatch`, and
  passes `ll-loop validate`.
- [ ] `frontmatter_scores` encodes values per the Built-in Dimension Table
  rules (boolean → 100/0, list → length, missing numeric → no file, missing
  string → empty) and exits non-zero on an unresolved issue ID; covered by a
  pytest.
- [ ] The Try-it panel accepts a pasted frontmatter block and reports the
  firing rule, agreeing with `evaluate_rules` on every conformance-corpus case.
- [ ] The new mode's pure-function core logic ships with `node --test`
  conformance coverage, gated into `python -m pytest scripts/tests/` the same
  way `test_policy_builder_node_gate.py` gates the existing modes.
- [ ] Existing `decision_table` and `rubric` golden YAML fixtures are
  byte-unchanged.
- [ ] The GUI does not attempt to reproduce `autodev.yaml`'s queue/retry/rate-
  limit/repair-cycle machinery (see Non-goals).

## Program Design

### Types

- `mode: "issue_lifecycle"` — new literal value for the existing `model.mode`
  field, alongside `"decision_table"` and `"rubric"`.
- `dimension: {name: string, type: "numeric" | "boolean" | "string"}` — the
  existing shape with `"string"` added; no `kind` discriminator.
- `outcome: {name: "prepare" | "refine" | "gate" | "implement" | "verify",
  actionType: "slash_command", body: string, transition: {kind: "finish"}}` —
  existing outcome shape, seeded from the Verb Table.
- `BUILTIN_FRONTMATTER_DIMENSIONS: ReadonlyArray<dimension>` and
  `LIFECYCLE_VERBS: ReadonlyArray<outcome>` — new exported constants in
  `policy_builder_core.mjs`.

### Signatures

- `blankModel(mode = "decision_table") -> Model` — adds an optional parameter
  to the existing zero-arg function (`policy_builder_core.mjs:300`); the
  `issue_lifecycle` branch seeds dimensions and outcomes from the constants.
- `seedExample(mode = "decision_table") -> Model` — same treatment
  (`policy_builder_core.mjs:247`); the example encodes the Use Case rules.
- `serializeLoopYaml(model: Model) -> string` — new explicit
  `mode === "issue_lifecycle"` branch ahead of the decision-table fallback
  (`policy_builder_core.mjs:645`).
- `_serializeIssueLifecycle(model: Model) -> string` — new; emits the shape
  in Proposed Solution §2, reusing `_serializeRulesText`, the route-map
  builder, and `_outcomeStateLines`.
- `serializeFrontmatterDimensions(model: Model) -> string` — new; produces
  the `name:type|name:type` text for `context.frontmatter_dimensions`.
- `parseFrontmatterBlock(text: string) -> Record<string, unknown>` — new pure
  mini-parser for Try-it (scalars, booleans, flow and dash lists).
- `encodeFrontmatterScores(fm: Record<string, unknown>, dims: dimension[]) -> Record<string, number | string>`
  — new pure encoder mirroring the fragment's rules; shared by Try-it.
- `opsForType(type: string) -> string[]` (template, `.tmpl:274`) — add the
  `"string"` branch returning `["==", "!="]`.
- `frontmatter_scores` fragment (YAML, `lib/policy-router.yaml`) — shell
  state reading `${context.issue_id}`, `${context.frontmatter_dimensions}`,
  `${context.run_dir}`; writes `rubric-dim-*.txt`; `next` supplied by caller.

### Call Path

`cmd_policy_builder` -> `_load_skill_catalog` (both
`scripts/little_loops/cli/artifact/policy_builder.py`) -> stamps
`policy_builder_core.mjs` into `policy-router-builder.html.tmpl` -> user
selects `issue_lifecycle`, authors rules -> `serializeLoopYaml` ->
`_serializeIssueLifecycle` -> saved YAML run via `ll-loop run <name>
--context issue_id=<ID>` -> `frontmatter_scores` (fragment) ->
`policy_table_dispatch` (fragment; `parse_rules` / `evaluate_rules` in
`fsm/policy_rules.py`) -> verb outcome state (`slash_command`).

## Use Case

A little-loops consumer has their own issue frontmatter conventions (e.g. a
custom `severity` field, or a `review_status` field that isn't part of
little-loops' schema) and wants a lightweight lifecycle loop — "when severity is
critical and review_status is approved, implement immediately; otherwise gate on
confidence_score >= 70" — without hand-writing FSM YAML or understanding
`autodev.yaml`'s internals. They open the GUI over `file://`, add `severity`
and `review_status` as `string` dimensions, author the two rules plus the
"Otherwise → refine" catch-all, paste an issue's frontmatter into Try-it to
confirm which rule fires, save the YAML, and run it with
`ll-loop run my-lifecycle --context issue_id=BUG-42`.

Seeded example rules (also the `seedExample` content):

```
severity:==critical & review_status:==approved -> implement
confidence_score:>=70 -> gate
* -> refine
```

## Non-goals

- Not a generator for `autodev.yaml` itself, and not a replacement for it in this
  repo.
- No queue management, retries, rate-limit handling, or repair cycles. One
  issue per run; users batch with `ll-auto`, a shell loop, or a wrapping FSM.
- No generic issue-lifecycle sub-loop; the emitted loop is self-contained.
- No round-trip editing of existing loops (consistent with FEAT-2301's scope cut).
- No nested-map frontmatter support in Try-it's mini-parser (scalars, booleans,
  and lists only); the runtime scorer uses the full `parse_frontmatter`.

## Related Key Documentation

- `scripts/little_loops/loops/autodev.yaml` — the production loop whose *shape*
  (not implementation) motivates this issue; explicitly out of scope to clone.
- `.issues/features/P3-FEAT-2301-self-contained-html-builder-for-policy-router-and-rubric-fsm-loops.md`
  — shipped sibling grammar/mode on the same builder shell.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` /
  `policy_builder_core.mjs` — the existing shell + pure-function core this issue
  extends.
- `scripts/little_loops/loops/lib/policy-router.yaml` — the fragment file that
  gains `frontmatter_scores`.
- `scripts/little_loops/loops/rn-remediate.yaml` — precedent for a per-issue
  deterministic scorer loop and the `with: issue_id` contract.

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- review rewrite - 2026-09-16 - resolved emitted-artifact shape, added `frontmatter_scores` scorer, value-encoding rules, `string` type, verb defaults, Try-it; removed refuted directive claims
- `/ll:refine-issue` - 2026-09-16T16:03:25 - `80866648-631d-42a2-9297-c19a0708559a.jsonl`
- `/ll:wire-issue` - 2026-09-16T15:55:33 - `30351525-6d5f-4f17-875c-0966e887e75a.jsonl`
- `/ll:refine-issue` - 2026-09-16T15:42:26 - `5f7a02ee-f693-4547-b06c-90ac4758be6a.jsonl`
- `/ll:refine-issue` - 2026-09-16T15:36:40 - `5f7a02ee-f693-4547-b06c-90ac4758be6a.jsonl`
- `/ll:decide-issue` - 2026-09-16T15:29:10 - `0f1bb5c4-ede6-454e-91d0-c97fb496e2cd.jsonl`
- `/ll:decide-issue` - 2026-09-16T05:02:58 - `8f3ac7b1-a0c3-4119-9504-bcaf52b84b4c.jsonl`
- `/ll:format-issue` - 2026-09-14T17:26:12 - `935702d4-fd79-4fcc-b1ed-24d764f51e14.jsonl`
- `/ll:capture-issue` - 2026-09-14T17:11:14 - `b2c42f0a-8e12-495a-9786-d532e21cd8a7.jsonl`
