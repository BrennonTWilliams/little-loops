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
is a **third grammar/mode** alongside FEAT-2301's existing `policy-router` and
`rubric` modes on the same self-contained-HTML builder shell (EPIC-3299), not a
generator for `scripts/little_loops/loops/autodev.yaml` itself.

## Current Behavior

No GUI exists for authoring an issue-lifecycle-shaped loop. Today a user who wants
an autodev-like loop for their own issue conventions must either hand-write FSM
YAML from scratch, or copy and heavily edit `autodev.yaml` (a large, tightly
coupled file with little-loops-specific assumptions throughout).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The self-contained builder shell this issue extends already dispatches on `model.mode` via string-literal comparison, not a registry: `serializeLoopYaml()` (`scripts/little_loops/templates/policy_builder_core.mjs:645`) returns `_serializeRubric(model)` only when `model.mode === "rubric"`; every other value falls through to `_serializeDecisionTable(model)` with no error path. `blankModel()` (`:300`) and `seedExample()` (`:247`) in the same file take no `mode` argument and always hardcode `mode: "decision_table"` — there is no existing per-mode branch in either function to extend by example.
- Roughly ten additional `model.mode`/`state.mode` comparisons live in `scripts/little_loops/templates/policy-router-builder.html.tmpl`'s inline script (`computeSummary`, `renderTryIt`, `updateTryIt`, `renderMessages`, `renderAll`, `applyModeVisibility`, the `#mode-switch` change handler, `#start-blank-btn`'s click handler) — a third mode's UI wiring touches this file, not only `policy_builder_core.mjs`.

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- `cmd_policy_builder()` in `scripts/little_loops/cli/artifact/policy_builder.py` assembles the emitted artifact by loading `grammar_spec()` and `_load_skill_catalog()`, then stamping four literal placeholders into the read `.tmpl`/`.mjs` text (theme CSS vars, grammar-spec JSON, skill-catalog JSON, the core JS itself) via sequential `str.replace()` calls — there is no general templating engine and no `--mode` CLI flag; mode is a pure runtime/browser concept never inspected server-side. `_load_skill_catalog()` returns a flat `list[dict]` of `{"name": str, "description": str}` with no verb/category field to filter by lifecycle stage.

## Expected Behavior

A `policy-router-builder.html.tmpl`-style page (or a new mode on it) where:

- **Subject** is an Issue file's YAML frontmatter (as in `.issues/*.md`), not an
  arbitrary artifact.
- **Dimensions** in the rule builder are frontmatter fields:
  - little-loops' own built-in fields (`status`, `priority`, `blocked_by`,
    `decision_needed`, `confidence_score`, `outcome_confidence`,
    `deferred_reason`, etc.) as first-class known dimensions with typed operators,
    mirroring FEAT-2301's numeric/boolean dimension-type restriction (`opsForType`).
  - PLUS arbitrary user-declared **generic** frontmatter fields — a consuming
    project with its own custom frontmatter schema should be able to add a field
    name and use it as a rule dimension without little-loops needing to know about
    it in advance. This is the key differentiator from a little-loops-only tool.
- **Actions** per rule/outcome map onto the issue-lifecycle verbs: prepare,
  refine, gate, implement, verify — presumably backed by existing skills/commands
  (`/ll:refine-issue`, `/ll:wire-issue`, `/ll:confidence-check`,
  `/ll:manage-issue`, `/ll:verify-issues`, `ll-issues check-readiness`, `ll-auto
  --only`), the same way FEAT-2301's action authoring already offers "run a
  skill" from an emit-time skill catalog dropdown.
- Reuses FEAT-2301/FEAT-2390's shipped patterns where they fit (self-contained
  `file://` HTML, ordered reorderable rule list, pinned "Otherwise" footer,
  demoted YAML, seeded example, theme handling, pure-function `.mjs` core +
  `node --test` gate, jargon-denylist for on-screen labels) rather than
  reinventing the shell.

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

FEAT-2301/FEAT-2390 already proved the shell: ordered/reorderable first-match rule
list read as plain sentences, pinned non-input catch-all, demoted-YAML view,
seeded example, jargon-denylist, pure-function core + `node --test` conformance
gate. This issue asks: what's the smallest issue-lifecycle-specific grammar that
reuses that shell and engine, without trying to clone autodev's full complexity?

## Proposed Solution

Extend the existing self-contained HTML builder shell rather than building a new
one: `policy_builder_core.mjs` already dispatches on a `mode` field
(`decision_table` in `blankModel()` at `policy_builder_core.mjs:300` and
`seedExample()` at `:247`, both consumed by `serializeLoopYaml()` at `:645`,
which also branches on `mode === "rubric"`). This issue adds a third mode
(working name: `issue_lifecycle`) alongside those two:

- Dimension picker offers little-loops' known frontmatter fields (`status`,
  `priority`, `blocked_by`, `decision_needed`, `confidence_score`,
  `outcome_confidence`, `deferred_reason`) as typed dimensions, mirroring
  FEAT-2301's `opsForType` numeric/boolean operator restriction, plus a
  "custom field" affordance letting the user name an arbitrary frontmatter key
  and declare its type.
- Outcome/action picker offers the five lifecycle verbs (prepare, refine,
  gate, implement, verify) as first-class actions, each backed by an existing
  skill/command slug from the same emit-time skill catalog FEAT-2301 already
  surfaces for its "run a skill" action.
- The emitted-artifact shape (standalone FSM loop YAML vs. a policy config
  consumed by a shared sub-loop) is the open question below and is not decided
  by this section — `/ll:refine-issue` should resolve it before implementation
  starts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The generic rule-table engine (`fsm/policy_rules.py`'s `parse_rules`/`evaluate_rules`) has exactly two known consumers today, confirming Option B's precedent: `scripts/little_loops/loops/policy-refine.yaml` (a loop supplying `context.policy_rules` as plain text, routed via the `policy_table_dispatch` fragment from `lib/policy-router.yaml`) and `ll-loop edit-routes` (`cli/loop/edit_routes.py`, a CLI editor over that same `policy_rules` text via `PolicyRuleExtractor`/`CompoundGridRenderer`/`PolicyRuleApplier` in `fsm/route_table.py`). No third consumer exists in the repo.
- Testing convention for the two existing modes: each gets its own dedicated golden model+YAML fixture pair under `scripts/tests/fixtures/policy_builder/` (`sample-decision-table.model.json`/`.yaml`, `sample-rubric.model.json`/`.yaml`). Each mode's "golden YAML validates" test is a separate, non-parametrized function (`test_golden_yaml_validates`, `test_golden_rubric_yaml_validates` in `test_policy_builder_emit.py`), while the node-gate round-trip test (`test_round_trip_yaml_validates_for_each_mode` in `test_policy_builder_node_gate.py`) is parametrized across both mode fixtures in one function.
- Mode-switcher UI convention: a single `<select id="mode-switch">` in the page header (not tabs, `.tmpl:121-124`), with per-mode visibility controlled by direct `.hidden` boolean toggles on four fixed fieldset IDs in `applyModeVisibility()` (`.tmpl:624-628`) — there is no `data-mode` attribute or CSS-scoping convention anywhere in this template; repo-wide search for `data-mode` found no hits in the builder shell.
- Jargon-denylist enforcement is a single hardcoded Python list literal inline in one test function (`test_no_internal_jargon_in_visible_markup`, `test_policy_builder_emit.py:130-135`), checked against the emitted HTML with `<script>`/`<style>`/comment blocks stripped first (`_strip_script_style_comments`, `:22-34`). There is no separate reusable jargon-validator module — a third mode's own jargon terms would need direct additions to that same inline list.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy_builder_core.mjs` — add the
  `issue_lifecycle` mode branch to `blankModel()`, `seedExample()`, and
  `serializeLoopYaml()`
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — add the
  mode's dimension picker and action picker UI
- `scripts/little_loops/cli/artifact/policy_builder.py` — wire the new mode
  into whatever CLI entry point emits/validates the builder artifact

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` —
  byte-mirrored golden fixture of the full stamped template;
  `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`
  does a hard byte-diff against it, so it MUST be regenerated/hand-updated
  once the template changes — not merely "extended with cases" [Agent 3
  finding]
- `scripts/little_loops/loops/README.md` — the loop/fragment registration
  table; needs a new row if Option B's deferred generic sub-loop work adds a
  `lib/*.yaml` fragment (every existing fragment, e.g. `lib/policy-router.yaml`,
  `lib/rubric-router.yaml`, has a row here) [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/__init__.py` — re-exports/registers
  `policy_builder.py`; confirm the new mode doesn't need a separate CLI flag
- `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` — both
  document the existing `policy-router`/`rubric` modes and will need a third
  entry

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/reachability.py` —
  `_validate_policy_dimensions_scored()` (line 154) calls `parse_rules()`
  (line 184) to lint FSM policy-rule text against the same
  `fsm/policy_rules.py` grammar this issue's engine reuse depends on; confirm
  the `issue_lifecycle` mode's emitted rule text stays compatible since this
  validator is a real (non-guarded) production call site [Agent 1 finding]
- `scripts/little_loops/loops/lib/policy-router.yaml` — the actual FSM
  fragment backing `policy-refine.yaml`'s `policy_table_dispatch` state
  (`parse_rules`/`evaluate_rules` calls at lines 168-169); Option B's
  "generic sub-loop" this issue's Decision Rationale defers to follow-on
  refinement is expected to extend or sit alongside this fragment
  [Agent 1 finding]

### Similar Patterns
- `scripts/tests/js/policy_validator.test.mjs` — the `node --test` conformance
  pattern this issue's own "Reuses" list commits to following for the new mode

### Tests
- `scripts/tests/test_policy_builder_emit.py` and
  `scripts/tests/test_enh3035_artifact_template_kit.py` — extend with
  `issue_lifecycle`-mode cases the same way they cover `decision_table`/`rubric`
- `scripts/tests/test_policy_builder_node_gate.py` — the pytest wrapper that
  shells out to `node --test`; already generic across modes, no change
  expected unless new `.mjs` test files are added

  > ⚠ Superseded — `test_round_trip_yaml_validates_for_each_mode`'s
  > `@pytest.mark.parametrize` (line 125) is a hardcoded two-entry list
  > (`sample-decision-table.model.json`, `sample-rubric.model.json`); it DOES
  > need a third `"sample-issue-lifecycle.model.json"` entry — this file is
  > not change-free [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_validator.test.mjs` — not just the pattern to
  follow (as cited under "Similar Patterns" above): this file hardcodes one
  `test(...)` block per mode reading a literal fixture-filename pair, so it
  needs a direct new `test("serializeLoopYaml matches golden issue-lifecycle
  fixture", ...)` block added [Agent 3 finding]
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle.model.json`
  and `.yaml` — new golden fixture pair required by the pattern above; does
  not yet exist [Agent 3 finding]
- `scripts/tests/test_policy_rules.py` — direct unit tests of
  `parse_rules`/`evaluate_rules`/`grammar_spec`/`_PRED_PATTERN`; add coverage
  if the new mode introduces new dimension types or predicate shapes
  [Agent 1 finding]
- `scripts/tests/test_policy_builder_corpus.py` — conformance-corpus tests
  pinning `evaluate_rules`/`_detect_shadows` against
  `fixtures/policy_builder/conformance_corpus.json`; add corpus cases if
  `issue_lifecycle` rules exercise new predicate shapes [Agent 3 finding]

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add the new mode alongside
  `policy-router`/`rubric`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` § "Project-enriched artifacts" — cites
  `ll-artifact policy-builder` as the shipped example of this issue's exact
  extension point, but names the catalog loader as `cli/action.py:_load_skills()`
  — a different, unrelated function from `cli/artifact/policy_builder.py:_load_skill_catalog()`
  this issue actually extends; fix the stale citation while touching this
  area [Agent 2 finding]

### Configuration
- N/A — no `.ll/ll-config.json` schema changes anticipated

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- The two existing modes are asymmetric: only `serializeLoopYaml()` (`policy_builder_core.mjs:645`) reads `model.mode` at runtime — `blankModel()` (`:300`) and `seedExample()` (`:247`) are zero-argument functions that always hardcode `mode: "decision_table"`; neither has an existing per-mode branch to extend by example.
- `serializeLoopYaml()` has no explicit `"decision_table"` branch — any `model.mode` other than the literal `"rubric"` (including a future `"issue_lifecycle"`) silently falls through to `_serializeDecisionTable(model)` with no error. A third mode's branch must be added explicitly ahead of that fallback.
- Full inventory of `model.mode`/`state.mode` branch sites in `scripts/little_loops/templates/policy-router-builder.html.tmpl` beyond the three functions named in Proposed Solution: `computeSummary` (`:265`), `renderTryIt` (`:527`, early-return decision-table-only), `updateTryIt` (`:558`, same guard), `renderMessages` (`:581`, decision-table-only unreachable-outcome check), `renderAll` (`:610`), `applyModeVisibility` (`:624-628`, toggles `.hidden` on `threshold-fieldset`/`outcomes-fieldset`/`rules-fieldset`/`tryit-fieldset`), the `#mode-switch` `onchange` handler (`:632-638`, the only place `state.mode` is reassigned from user input, driven by a two-option `<select>` at `:121-124`), and `#start-blank-btn`'s `onclick` (`:684-693`).
- Because `policy_builder_core.mjs` is stamped verbatim into the emitted HTML, every one of these dispatch sites is also byte-mirrored in `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`.
- `cmd_policy_builder()` (`policy_builder.py:56-107`) has exactly four data-injection points into the template: `/*__THEMED_CSS_VARS__*/`, `/*__GRAMMAR_SPEC_JSON__*/`, `/*__SKILL_CATALOG_JSON__*/`, `/*__BUILDER_CORE_JS__*/` (each a literal `str.replace`). A new mode needing extra emit-time data beyond what these four already carry would need a fifth placeholder plus a matching `.replace()` call — there is no general templating engine here.
- `_load_skill_catalog()` (`policy_builder.py:21-53`) returns a flat, undifferentiated `list[dict]` of `{"name": str, "description": str}` sourced from `skills/*/SKILL.md` and `commands/*.md` frontmatter — there is no `verb`/`category`/`lifecycle_stage` field today that would let a consumer filter the catalog down to just the five lifecycle verbs (prepare/refine/gate/implement/verify) this issue wants; every entry is exposed uniformly as a `/ll:<name>` slash-command string in the existing "Run a skill" dropdown (`renderOutcomes()`, `.tmpl:363-374`).

## Implementation Steps

1. Resolve the Open Design Question (Option A vs. B) via `/ll:refine-issue`
   before scoping further — the emitted-artifact shape determines the rest of
   this list.
2. Add the `issue_lifecycle` mode to `policy_builder_core.mjs` (model shape,
   `seedExample`, `serializeLoopYaml` branch) with `node --test` coverage.
3. Add the mode's UI to `policy-router-builder.html.tmpl` (frontmatter
   dimension picker with built-in + custom fields, lifecycle-verb action
   picker).
4. Wire the mode into `policy_builder.py`/CLI as needed and update
   `POLICY_ROUTER_GUIDE.md`.
5. Verify by authoring the Use Case scenario's example rules in the GUI and
   confirming the emitted artifact runs (or validates, per the chosen
   architecture) end to end.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`
  once template changes land — `test_enh3035_artifact_template_kit.py`'s byte-diff
  test will otherwise fail unconditionally
- Add `"sample-issue-lifecycle.model.json"` to the `@pytest.mark.parametrize`
  list in `scripts/tests/test_policy_builder_node_gate.py:125`
- Add the new mode's golden fixture pair under `scripts/tests/fixtures/policy_builder/`
  and a matching `test(...)` block in `scripts/tests/js/policy_validator.test.mjs`
- Naming-collision note (no code change, awareness only): the proposed mode
  literal `"issue_lifecycle"` is a plain string match for the pre-existing,
  unrelated production module `scripts/little_loops/issue_lifecycle.py`
  (issue status-transition helpers, imported by `parallel/orchestrator.py` and
  `cli/issues/skip.py`); no code collision, but grep-based searches during
  implementation/maintenance will hit both — disambiguate in commit messages
  and comments

## Impact

- **Priority**: P3 - self-service tooling for other little-loops consumers,
  not blocking any in-repo workflow (little-loops itself keeps hand-tuned
  `autodev.yaml`).
- **Effort**: Large - a new grammar/mode on an existing shell, gated on an
  unresolved architecture question (Open Design Question below) plus new
  `node --test` coverage.
- **Risk**: Low - additive third mode alongside `decision_table`/`rubric`;
  does not modify either existing mode's behavior.
- **Breaking Change**: No

## Open Design Question (do not resolve unilaterally — surface for refine-issue / confidence-check)

**What does the GUI actually emit, and how does that map to runnable automation?**

- Option A: a standalone FSM loop YAML (like `policy-router`/`rubric-router` do)
  that the user runs via `ll-loop run <name>`. Given autodev's complexity, safely
  generating a loop that handles queueing, retries, and rate-limits from a flat
  rule table is a much bigger lift than policy-router's flat decision table — this
  may not be achievable at the same "structurally unrepresentable errors" quality
  bar FEAT-2301 held itself to.
- Option B: a smaller, more constrained artifact — e.g. a per-issue-type policy
  config consumed by an existing generic loop (so the GUI authors *policy*, not a
  full bespoke FSM), trading flexibility for safety/correctness.

  > **Selected:** Option B — scores higher on codebase-evidence fit (7/12 vs.
  > 4/12, see Decision Rationale below). The rule-table engine
  > (`lib/policy-router.yaml` + `fsm/policy_rules.py`) is already reusable
  > generic infrastructure the GUI can target directly, whereas Option A's
  > per-generated-artifact queue/retry/rate-limit code generation would inherit
  > a documented, unsolved gap: a `loop:` call state cannot observe a child's
  > rate-limit-exhaustion terminal (`oracles/resolve-decision.yaml:163-181`,
  > `autodev.yaml:489-494`).

Refinement should investigate factoring autodev's queue/retry/rate-limit
machinery into a reusable generic sub-loop that a GUI-authored policy config is
dispatched through — this is the concrete remaining implementation question for
Option B, not an open A-vs-B choice.

### Decision Rationale

**Decision point:** Open Design Question — Option A vs. Option B

**Selected:** Option B — a smaller, constrained policy-config artifact consumed
by an existing/new generic issue-lifecycle loop, rather than a fully
self-contained standalone FSM loop YAML per Option A.

**Reasoning:** Two parallel `ll:codebase-pattern-finder` agents investigated
each option's actual codebase support. Both options score identically on
Consistency (1/3) because neither has a ready-made reusable queue/retry/
rate-limit mechanism to plug into — that machinery exists only hardcoded
inline in `autodev.yaml`, never factored out generically. Where they diverge is
where that unsolved problem lands:

- The standalone-FSM-loop path (A) requires the *generator itself* to
  correctly emit queue/retry/rate-limit states per generated FSM artifact.
  The one existing precedent for sub-loop composition of this kind,
  `oracles/resolve-decision.yaml`, has a documented, currently-unsolved
  architectural gap: a `loop:` call state cannot observe a child sub-loop's
  rate-limit-exhaustion terminal (`_execute_sub_loop` routes only on a
  pass/fail bool, not a terminal name — `resolve-decision.yaml:163-181`,
  `autodev.yaml:489-494`, `:690-711`). That design inherits this gap and must
  additionally code-generate a caller-side sentinel-polling state per call
  site — the opposite of the "structurally unrepresentable errors" bar
  FEAT-2301 set for this shell.
- The policy-config path (B, selected) only requires the GUI to emit
  *declarative rule-table data*. The engine that consumes such data already
  exists and is proven: `lib/policy-router.yaml` + `fsm/policy_rules.py`
  (`parse_rules`/`evaluate_rules`), already reused by `decision_table` mode,
  `ll-loop edit-routes`, and `policy-refine.yaml`. The harder problem — a
  reusable generic queue/retry/rate-limit engine for issue-lifecycle stages —
  still needs to be built, but as a one-time investment separate from the
  GUI's per-artifact code generation, not embedded in it.

### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A: standalone FSM loop YAML | 1 | 1 | 1 | 1 | 4/12 |
| B: policy config + generic loop | 1 | 2 | 2 | 2 | 7/12 |

### Key Evidence

- `policy_builder_core.mjs:645-650` — `serializeLoopYaml` dispatch pattern both
  options could extend for their own artifact shape; not a discriminator.
- `oracles/resolve-decision.yaml:163-181` and `autodev.yaml:489-494`,
  `:690-711` — documented gap: `loop:` call states cannot observe a child's
  rate-limit-exhaustion terminal; Option A inherits this per generated
  artifact.
- `lib/policy-router.yaml:1-184`, `fsm/policy_rules.py` — proven generic
  rule-table engine Option B targets directly; already reused by
  `decision_table` mode and `ll-loop edit-routes`.
- `lib/common.yaml:94-181` (`queue_pop`, `with_rate_limit_handling`) — the
  only existing queue/rate-limit logic in the repo is fragment-level, merged
  into hand-authored caller states, not an invocable generic engine for
  either option to reuse outright.

## Acceptance Criteria

- [ ] The GUI is a single self-contained `.html` file that opens over `file://`
  with no install step and no network dependency, matching FEAT-2301's shell.
- [ ] A user can add a rule dimension for any of little-loops' built-in
  frontmatter fields (`status`, `priority`, `blocked_by`, `decision_needed`,
  `confidence_score`, `outcome_confidence`, `deferred_reason`) with typed
  operators appropriate to that field's type.
- [ ] A user can also declare an arbitrary custom frontmatter field name (not
  in the built-in list) and use it as a rule dimension with a chosen type,
  without little-loops needing prior knowledge of that field.
- [ ] Each rule's outcome maps to one of the five lifecycle actions (prepare,
  refine, gate, implement, verify), selectable from an emit-time skill/command
  catalog the same way FEAT-2301's "run a skill" action works.
- [ ] Rules are ordered/reorderable and read as a first-match list with a
  pinned non-input "Otherwise" catch-all, per FEAT-2301/FEAT-2390's shipped
  shell conventions.
- [ ] The new mode's pure-function core logic ships with `node --test`
  conformance coverage, gated into `python -m pytest scripts/tests/` the same
  way `test_policy_builder_node_gate.py` gates the existing modes.
- [ ] The GUI does not attempt to reproduce `autodev.yaml`'s queue/retry/rate-
  limit/repair-cycle machinery (see Non-goals).

## Program Design

The concrete signatures below depend on which side of the Open Design Question
(Option A vs. B) `/ll:refine-issue` resolves; documented here at the level
resolvable without that decision, anchored to existing identifiers.

### Types

- `mode: "issue_lifecycle"` — new literal value for the existing `model.mode`
  field already handled in `blankModel()` (`policy_builder_core.mjs:300`),
  alongside today's `"decision_table"` and `"rubric"`
- `dimension: {field: string, kind: "builtin" | "custom", type: "string" |
  "number" | "boolean"}` — extends the existing dimension shape with a
  `kind` discriminator so custom (`kind: "custom"`) fields skip the
  built-in-field validation `opsForType` applies to known fields

### Signatures

- `blankModel(mode: "issue_lifecycle") -> Model` — new mode branch in the
  existing function (`policy_builder_core.mjs:300`)
- `seedExample(mode: "issue_lifecycle") -> Model` — new mode branch in the
  existing function (`policy_builder_core.mjs:247`)
- `serializeLoopYaml(model: Model) -> string` — extend the existing
  `mode === "rubric"` branch (`policy_builder_core.mjs:645`) with an
  `issue_lifecycle` branch; exact output shape is the Open Design Question

### Call Path

`cmd_policy_builder` -> `_load_skill_catalog` (both
`scripts/little_loops/cli/artifact/policy_builder.py`) -> renders
`policy-router-builder.html.tmpl` with the `issue_lifecycle` mode's
`blankModel`/`seedExample`/`serializeLoopYaml` branches embedded from
`policy_builder_core.mjs` -> emitted artifact consumed by `ll-loop run`
(Option A) or a shared sub-loop (Option B)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- `blankModel(mode)`/`seedExample(mode)` signatures above describe a mode parameter neither function currently accepts — both are zero-arg and hardcode `mode: "decision_table"` (`policy_builder_core.mjs:300`, `:247`). Implementing a third mode means adding mode-conditional logic to functions that currently have none, not extending an existing per-mode branch.
- The claimed "numeric/boolean dimension-type restriction" (`opsForType`) is not what the current code implements: the actual function is `opsForType(type)` at `scripts/little_loops/templates/policy-router-builder.html.tmpl:274-276` — `return type === "boolean" ? ["==true", "==false"] : GRAMMAR.all_ops;`. It special-cases only `"boolean"`; `"numeric"` (and any other type string) receives the full unrestricted `GRAMMAR.all_ops` set. No numeric-specific operator subset is present anywhere in `opsForType()` or `grammar_spec()` (`scripts/little_loops/fsm/policy_rules.py:262-273`).
- The `dimension: {kind: "builtin" | "custom", ...}` shape proposed above is not present in the current model — a repo-wide search found no `kind`/builtin-vs-custom discriminator anywhere. The underlying model is already open by default: `dimensions` is `{name: string, type: string}` with `name` a free-form string (normalized only by `normalizeDimName()`, `:90`), and `grammar_spec()`'s `_PRED_PATTERN` (`fsm/policy_rules.py:32-34`) matches any word-ish dimension name, not a closed enum — a GUI author can already add an arbitrary dimension name today with no allowlist check (`.tmpl:646-652`). The `kind` discriminator this issue proposes is therefore a UI/validation-layer addition, not something needed to unlock an otherwise-closed model.
- `cmd_policy_builder`'s only error handling is a single outer `try/except Exception: logger.error(...); return 1` (`policy_builder.py:65,105-107`) — there is no mode-specific validation anywhere in the Python CLI layer; mode is never inspected server-side at all (no `--mode` CLI flag exists on the `policy-builder` subcommand), it is purely a runtime/browser `state.mode` concept.

## Use Case

A little-loops consumer has their own issue frontmatter conventions (e.g. a
custom `severity` field, or a `review_status` field that isn't part of
little-loops' schema) and wants a lightweight lifecycle loop — "when severity is
critical and review_status is approved, implement immediately; otherwise gate on
confidence_score >= 70" — without hand-writing FSM YAML or understanding
`autodev.yaml`'s internals. They open the GUI over `file://`, add their custom
frontmatter field as a dimension, author 2-3 rules mapping to prepare/refine/gate/
implement/verify actions, and get something runnable.

## Non-goals (initial scope guess — confirm during refinement)

- Not a generator for `autodev.yaml` itself, and not a replacement for it in this
  repo.
- Not attempting to reproduce autodev's repair-cycle/decision-resolution/
  rate-limit-handling machinery in v1 — see Open Design Question.
- No round-trip editing of existing loops (consistent with FEAT-2301's scope cut).

## Related Key Documentation

- `scripts/little_loops/loops/autodev.yaml` — the production loop whose *shape*
  (not implementation) motivates this issue; explicitly out of scope to clone.
- `.issues/features/P3-FEAT-2301-self-contained-html-builder-for-policy-router-and-rubric-fsm-loops.md`
  — shipped sibling grammar/mode on the same builder shell; this issue's
  "Reuses" list is copied from its shipped ACs.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` /
  `policy_builder_core.mjs` — the existing shell + pure-function core this issue
  should extend or sit alongside.

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-16T16:03:25 - `80866648-631d-42a2-9297-c19a0708559a.jsonl`
- `/ll:wire-issue` - 2026-09-16T15:55:33 - `30351525-6d5f-4f17-875c-0966e887e75a.jsonl`
- `/ll:refine-issue` - 2026-09-16T15:42:26 - `5f7a02ee-f693-4547-b06c-90ac4758be6a.jsonl`
- `/ll:refine-issue` - 2026-09-16T15:36:40 - `5f7a02ee-f693-4547-b06c-90ac4758be6a.jsonl`
- `/ll:decide-issue` - 2026-09-16T15:29:10 - `0f1bb5c4-ede6-454e-91d0-c97fb496e2cd.jsonl`
- `/ll:decide-issue` - 2026-09-16T05:02:58 - `8f3ac7b1-a0c3-4119-9504-bcaf52b84b4c.jsonl`
- `/ll:format-issue` - 2026-09-14T17:26:12 - `935702d4-fd79-4fcc-b1ed-24d764f51e14.jsonl`
- `/ll:capture-issue` - 2026-09-14T17:11:14 - `b2c42f0a-8e12-495a-9786-d532e21cd8a7.jsonl`
