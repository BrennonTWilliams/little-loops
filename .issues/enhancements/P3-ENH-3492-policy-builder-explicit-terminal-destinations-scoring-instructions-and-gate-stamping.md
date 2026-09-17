---
id: ENH-3492
parent: EPIC-3493
epic: EPIC-3493
type: ENH
title: Policy builder explicit terminal destinations, scoring instructions, and gate
  stamping
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:49:50Z'
labels:
- policy-builder
decision_needed: false
depends_on:
- BUG-3486
- BUG-3499
relates_to:
- ENH-3487
- ENH-3491
- BUG-3489
- FEAT-3474
blocks:
- FEAT-3488
blocked_by: []
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
verify_verdict: VALID
---

# ENH-3492: Policy builder explicit terminal destinations, scoring instructions, and gate stamping

## Summary

Add explicit stop-success, skip, and needs-attention terminal destinations to lifecycle policies, optional per-dimension scoring instructions and score anchors, and stamp the project's confidence-gate thresholds into the builder. Split out of ENH-3487 (workstream c: emitted-YAML semantics). Design decisions are resolved below, including the 2026-09-17 review corrections.

## Current Behavior

The builder emits a binary terminal model, differing by mode:

- `issue_lifecycle` (`_serializeIssueLifecycle`, `scripts/little_loops/templates/policy_builder_core.mjs:1698-1768`) hardcodes `on_max_steps: failed` (`:1727`), every verb state carries `on_error: failed` (`:1757`), and only `done`/`failed` terminals are emitted (`:1760-1766`).

- `decision_table` (`_serializeDecisionTable`, `:1453-1555`) now unconditionally emits `on_max_steps: failed` (added by the BUG-3489 fix, committed `22f4ff6ed`; see `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7`) — no model flag, and existing golden fixtures were regenerated (not kept byte-equal) as part of that change.

- `rubric` (`_serializeRubric`, `:1558-1633`) has a single `done` terminal and no `on_max_steps`.
No `stop-success`, `skip`, or `needs-attention` concept exists anywhere in the builder. Rubric dimensions have no score definitions. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:62-114`) stamps only theme, CSS vars, grammar spec, and catalog; lifecycle defaults hardcode a confidence threshold. `ConfidenceGateConfig` (`scripts/little_loops/config/automation.py:155-170`) is unread by this command.

## Expected Behavior

Lifecycle rules can route to `stopped`, `skipped`, and `needs_attention` destinations, each emitting a valid loop. Reopening existing five-verb models emits YAML that differs from today's only by the `on_max_steps` line and the new terminal blocks (no verb, route, or action changes). Dimensions accept optional scoring instructions and score anchors that appear in emitted prompts. The builder displays the project's configured readiness/outcome thresholds alongside rule thresholds.

## Proposed Solution

1. Add lifecycle-only built-in destinations `stopped`, `skipped`, and `needs_attention` in `LIFECYCLE_DESTINATIONS`, separate from the five `LIFECYCLE_VERBS`. Rules and fallback may reference these terminals directly in `issue_lifecycle` mode only; verb transitions gain `stop`, `skip`, and `attention` **restricted to `issue_lifecycle` mode**. `_outcomeStateLines` is shared across all three modes, so the new `transition.kind` values must be gated inside it (or by its caller) on `model.mode === "issue_lifecycle"`; `rubric` and `decision_table` reject an outcome whose `transition.kind` is `stop`/`skip`/`attention` at validation time (`_checkReservedTokens`/model-load), and the `policy-router-builder.html.tmpl` transition-kind `<select>` only offers the three new options when the builder is in lifecycle mode — they must not appear, or be importable, in rubric/decision-table models. Keep `_emittedVerbs` restricted to verb states; terminal references are computed by two **new** helpers, `_dispatchedDestinations` and `_requiredTerminalBlocks` (no `_emittedDestinations` helper exists today — nothing is being replaced). **Dispatch destinations and emitted terminal blocks are two separate sets, computed separately**: dispatch routes are emitted only for destinations actually referenced by a rule target, fallback, or verb `transition.kind` (i.e. author-selected references) — the automatic `on_max_steps → needs_attention` budget route does **not** by itself add a `needs_attention` dispatch route, since no dispatch mechanism reaches it. The set of required terminal *blocks* is broader: it includes every dispatch-referenced destination plus `needs_attention` whenever `on_max_steps` targets it, so the terminal exists for the executor to land on even when nothing dispatches to it. Concretely: an existing five-verb model with no authored reference to `needs_attention` gains the `needs_attention` terminal block and the changed `on_max_steps` line, but gains **no** new dispatch route — satisfying the Expected Behavior/AC constraint that reopening such a model changes only the budget line and terminal blocks, not routing.

2. `stopped` and `skipped` are successful terminals (no `failure` key). `needs_attention` and existing `failed` emit `failure: true`. `on_error` stays `failed`; `on_max_steps` becomes `needs_attention` in all three modes (rubric emits no `on_max_steps` today, so there it is an added line rather than a changed one). This budget route is the explicit automatic exception; stop/skip remain author-selected. Preserve existing model fixtures; regenerate their YAML with changes limited to the budget route and added terminal blocks. No preservation flag is introduced.

   **Action-before-terminal**: a verb whose `transition.kind` is `attention` (or `stop`/`skip`) still runs that verb's own action exactly once before the transition takes effect — the destination replaces only the verb's `next` target, not its action. If the action itself errors, `on_error: failed` still applies and the run lands on `failed`, not on the verb's declared destination; the destination is reached only on the verb's normal (non-erroring) completion.

   **Action-less outcomes with the new kinds (2026-09-17 review)**: `_outcomeStateLines` emits a bare `terminal: true` whenever the outcome has no action (`hasAction` false), regardless of `transition.kind`. Left as-is, a `stop`/`skip`/`attention` outcome with `actionType: none` would silently become a success terminal named after the verb. Rule: `_outcomeStateLines` emits `next: <destination>` for the three new kinds even when there is no action, and `validateBuilderModel` additionally rejects (error diagnostic) a lifecycle outcome that combines `actionType: none` with `stop`/`skip`/`attention`, since a verb that does nothing and then routes to a terminal is never what an author means. Test both the serializer branch and the diagnostic.

   **Consumers distinguish the terminals by `final_state` only**: nothing else at runtime separates `stopped`/`skipped` from `done` — all three are non-failure terminals with no `failure` key, and `FSMExecutor` exposes only `final_state`, `terminated_by`, and `failure_terminal`. The distinction is informational to any caller (ll-auto, FEAT-3488's router execution, a parent loop) that reads `final_state`; this issue does not add any runtime behavior keyed on the names. FEAT-3488 does not currently reference the new names — if it is meant to act on them, it must say so in its own spec.

   **Runtime prerequisite — resolved**: `FSMExecutor._finish` (`scripts/little_loops/fsm/executor.py:4333-4345`) previously set `failure_terminal` only when `terminated_by == "terminal"`, so a cap-routed handler finishing with `terminated_by == "max_steps"` reported `failure_terminal == False` even with `failure: true` (probe confirmed: `final_state needs_attention / terminated_by max_steps / failure_terminal False`). BUG-3499 (`depends_on`) is now `status: done`, fixed by commit `9e3454cc5`: the guard widened to `terminated_by in ("terminal", "max_steps", "max_iterations_reached")`. The prerequisite has landed, so the max-steps executor test below can assert `failure_terminal is True` directly, with no deferred second assertion.

3. Register generated names in the shared per-mode reserved-name map: all three in lifecycle, `needs_attention` in rubric/decision-table. Reservation forbids an authored outcome from shadowing a generated state; it does **not** forbid an allowed lifecycle reference to that built-in destination. Update `_checkReservedTokens`, `_checkMissingReferences`, and the serializer's `_assertNoReservedTokens` defense together. Lifecycle target/fallback selectors offer verbs plus destinations; other modes keep their existing target rules and collision guards. Unknown names remain errors.

   **Rubric gains the serializer guard (2026-09-17 review)**: `_serializeRubric` (`policy_builder_core.mjs:1558`) does not call `_assertNoReservedTokens` today, unlike the other two serializers. Add `_assertNoReservedTokens("rubric", model)` at its top so the "fails serializer guards in every mode" acceptance criterion is actually true for rubric. Note the behavior change this introduces: rubric emission only honors outcomes literally named `light_repair`/`deep_repair`, so a rubric outcome named `needs_attention` (or `score`, `done`, …) is silently ignored today; after this change it is a hard error at emission, matching the non-throwing UI diagnostic. That is intended — a silently dropped outcome is the same bug class BUG-3489 fixed.

4. Optional dimension `instructions` and `anchors` affect LLM grading in rubric/decision-table modes via `_scoreActionBody`. Keep `_serializeDimensions` and `serializeFrontmatterDimensions` wire formats unchanged: the latter is `name:type|...` for deterministic frontmatter extraction, not a prompt. Lifecycle hides these editing controls and does not use their contents at runtime; imported metadata is retained on Save/Open. Validate anchors as unique finite numeric scores in [0,100] with nonempty meanings; boolean dimensions accept only 0/100 anchors. Emit multiline instructions safely through the existing YAML block-scalar helper and test delimiters/quotes/newlines. Absent metadata preserves existing prompts byte-for-byte.

   **Runtime escaping — literal text, not runtime-interpolated**: `instructions` text and anchor `meaning` strings are opaque literal text passed through to the LLM grading prompt; they are never treated as FSM interpolation templates. A YAML block scalar protects YAML structure but does not stop the FSM's own `${...}` interpolation once the emitted prompt reaches `FSMExecutor` — confirmed by probe: an instruction containing `${customer.name}` raises `InterpolationError` at execution time rather than being emitted verbatim. The serializer must therefore escape any literal `${` sequence in `instructions`/anchor `meaning` text (e.g. doubling to `$${` per the FSM's existing escape convention, or an equivalent that survives round-trip) before emission, so authored text containing `${...}` is never misread as a variable reference. Add a runtime regression test that builds a model with `${...}` in an instruction, serializes it, and runs the resulting fragment through `FSMExecutor` (or the same probe technique used to confirm the failure) asserting no `InterpolationError` and that the literal text reaches the grading prompt unchanged. The escape is `ESCAPED_PATTERN = re.compile(r"\$\$\{")` (`fsm/interpolation.py:30`, applied in `interpolate()` `:348`): each `$${` becomes a literal `${`. Doubling composes correctly for text that already contains the escape — authored `$${x}` is emitted as `$$${x}` and unescapes back to `$${x}` — so the regression test must also cover an authored `$${...}` instruction and assert it reaches the prompt as `$${...}`.

5. Read `config.commands.confidence_gate` from the existing `BRConfig`; stamp enabled/readiness/outcome values and display them as project configuration alongside authored rule thresholds. Display disabled gates explicitly. Stamping is informational: never silently rewrite saved rule predicates or treat it as runtime enforcement. No config-schema change is required.

   **Seeded models keep their hardcoded thresholds (2026-09-17 review)**: `seedExample("issue_lifecycle")` and `_blankIssueLifecycle` (`policy_builder_core.mjs` ~`:895-940`) hardcode `85` in the seeded `confidence_score` rules and `thresholdHigh: 85`/`thresholdMedium: 65`. Seeding fresh models from the stamped `readiness_threshold` is **out of scope** here: `seedExample` is a pure core.mjs function exercised directly by the Node golden fixtures, and coupling it to a `window.__CONFIDENCE_GATE__` global would destabilize those fixtures. The stamped values are displayed next to the authored thresholds only. If seed-from-config is wanted, capture it as a follow-up.

6. Extend ENH-3491's transition summary for the destinations (including unresolved budget exhaustion); no summary may classify `needs_attention` as a successful finish. Concretely (2026-09-17 review): in `summarizeTransitions` (`policy_builder_core.mjs:1161`), `stopsAfterImplement` currently recognizes only `finish` (`:1168`) — `stop`/`skip`/`attention` on `implement` must also count as stopping after implement, with the summary naming which terminal (`stopped`/`skipped` as success, `needs_attention` as failure); `maxStepsNote` must say the budget lands on `needs_attention` (failure). In the template's `computeSummary` (`policy-router-builder.html.tmpl:445-461`), the lifecycle branch lists only `_emittedVerbs`, so a rule routing straight to `skipped` renders "reaches: nothing yet" — include `_dispatchedDestinations` in the "reaches:" list.

### Decision Rationale

The prior terminal decision is retained with explicit reference-vs-definition validation. Separate destinations prevent action editors from acquiring fake verbs. A failed budget terminal prevents unresolved loops reporting success. Scoring descriptions belong in LLM prompts, while lifecycle scoring remains deterministic frontmatter extraction. Saved-project round trips, not nonexistent YAML import, preserve the authoring metadata.

## Integration Map

- Files: `policy_builder_core.mjs`, `policy-router-builder.html.tmpl`, `cli/artifact/policy_builder.py`, `fsm/frontmatter_scores.py` is a compatibility surface only and remains unchanged.

- Tests: new `.model.json`/`.yaml` fixture pairs under `scripts/tests/fixtures/policy_builder/` for each new destination plus parametrize entries in `test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode` (arbitrary terminal names are schema-legal per `fsm/validation/structural_rules.py:1160-1168`); `scripts/tests/js/policy_validator.test.mjs`; `test_policy_builder_corpus.py`; regenerate the golden HTML fixture.

- Docs: `docs/reference/CLI.md:5083` prose (five fixed verbs); `docs/guides/POLICY_ROUTER_GUIDE.md:378-379` ("can't be deleted and no new outcome can be added") and `:383-389` (Verb Table needs a destination column). (Line numbers re-verified `/ll:verify-issues` 2026-09-17: commit `f0fa5c404` inserted a new task-presets paragraph and Verb/Dimension tables earlier in the "Issue Lifecycle Mode" section, shifting this passage by roughly +25 lines from its previously-cited location; CLI.md's builder paragraph is one un-wrapped line, so a single line number now suffices.)

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/lib/policy-router.yaml:154` — the `frontmatter_scores` fragment's action body invokes `from little_loops.fsm.frontmatter_scores import main`; a live runtime caller (via a heredoc-invoked subprocess at loop execution time), distinct from `test_frontmatter_scores.py`'s unit-test import. Assert its `context.frontmatter_dimensions` env-passing contract stays unchanged when metadata is present.

### Tests
_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_fsm_executor.py::TestGeneratedPolicyRouterFailureRouting` (~2810-2917) — loads the real `sample-decision-table.yaml`/`sample-issue-lifecycle.yaml` golden fixtures via `resolve_fragments` and runs them through a live `FSMExecutor`, asserting hardcoded terminal literals (`final_state == "failed"`/`"done"`, `failure_terminal`); must be updated in lockstep with any change to `on_max_steps` routing or terminal names.

- `scripts/tests/test_fsm_fragments.py` (~2408-2454) — pins the `frontmatter_scores` fragment's shell-env contract (`context.frontmatter_dimensions`) in `loops/lib/policy-router.yaml`; assert metadata does not alter the emitted dimension string format.

- `scripts/tests/js/policy_validator.test.mjs:227-236` — `RESERVED_STATE_NAMES` exact sorted-array `deepEqual` assertions will fail as soon as `stopped`/`skipped`/`needs_attention` are added to either mode's set; update the literal arrays.

- `scripts/tests/js/policy_validator.test.mjs:274` — literal `assert.match(yaml, /on_max_steps: failed/)`; update if `on_max_steps` routes to `needs_attention` instead.

- `scripts/tests/js/policy_validator.test.mjs:375-378` — exact-string assertion on `serializeFrontmatterDimensions` output (`"Review Status:string|confidence_score:numeric"`); add a companion case asserting metadata leaves that string unchanged; separately assert generated grading prompts contain the metadata.

- `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7` and `sample-issue-lifecycle.yaml:29` — literal `on_max_steps: failed` lines; update alongside the routing change and regenerate.

- No existing test covers the transition-kind `<select>` options list in `policy-router-builder.html.tmpl:604,747` (the two `[["rescore", "Score again"], ["goto", "Go to…"], ["finish", "Stop here"]]` literals; earlier citations of `:420,524` were wrong — those lines are the end of draft restore and the inside of `renderFallback()`); add coverage in `test_policy_builder_emit.py` for the new destination entries.

- No existing test covers confidence-gate stamping in `cmd_policy_builder`; add `test_emitted_confidence_gate_matches_config` to `test_policy_builder_emit.py` following the `test_emitted_grammar_matches_canonical` regex-extract-and-compare pattern (`test_policy_builder_emit.py:68-71`), asserting against `BRConfig(Path.cwd()).commands.confidence_gate`.

- `scripts/tests/test_policy_builder_emit.py:65` (`test_emit_writes_html`) — pre-existing generic leftover-placeholder gate, `assert "/*__" not in html`; any new `/*__CONFIDENCE_GATE_JSON__*/`-style template token must be fully substituted by `cmd_policy_builder` or this test fails independently of the new `test_emitted_confidence_gate_matches_config` [wiring pass finding].

### Documentation
_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/POLICY_ROUTER_GUIDE.md:249-256` ("Reserved names" section) — literally enumerates the current `RESERVED_STATE_NAMES` token sets per mode (e.g. "the generated decision-table pipeline uses `score`, `parse_scores`, `policy_dispatch`, and `failed`..."); must be updated alongside the already-listed `:378-379`/`:383-389` passages.

- `docs/guides/POLICY_ROUTER_GUIDE.md:412` (Issue Lifecycle "Seeded example" prose) — states the literal value this issue replaces: "once the score clears 85, bounded by `on_max_steps: failed` if the refine/gate cycle never converges"; update to `needs_attention` [wiring pass finding].

- `docs/generalized-fsm-loop.md:1779` — the BUG-2813 rule that a terminal doubling as the loop's `on_max_steps` handler is exempt from the non-terminal-`action` warning; governs whether a builder-emitted `needs_attention` terminal complies with `ll-loop validate`, directly bearing on Acceptance Criterion 2 [wiring pass finding — reference only, verify compliance rather than edit unless the rule's wording needs updating for the new terminal name].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Golden fixture pairs under `scripts/tests/fixtures/policy_builder/` are wired independently into three gates (`policy_validator.test.mjs` byte-equality tests, `test_policy_builder_node_gate.py`'s round-trip-validates parametrize list, and `policy_validator.test.mjs`'s `validateBuilderModel` zero-error-diagnostics list) — a new fixture pair need not appear in all three. Precedent: `sample-issue-lifecycle-verification.model.json/.yaml` is wired into the round-trip gate only.
- `cmd_policy_builder`'s config-to-template stamping uses two coexisting granularities: shared cross-template values go through `artifact_template_kit.py`'s `stamp_page_shell()` (theme/CSS vars); artifact-local values (grammar spec, skill catalog, generator version, inlined core JS) are stamped via direct `str.replace("/*__X_JSON__*/", ...)` calls inside `cmd_policy_builder` itself (`policy_builder.py:99-102`). No existing rule settles which granularity a new `__CONFIDENCE_GATE__` stamp belongs to.
- The cited test pattern `test_emitted_grammar_matches_canonical` (`test_policy_builder_emit.py:78-116`) extracts the stamped `window.__GRAMMAR_SPEC__` value from rendered HTML via a `window\.__X__\s*=\s*(...)` regex, then asserts field-by-field equality against the canonical Python value computed by the same source function the CLI calls — not byte-equality on the whole placeholder. `test_emitted_confidence_gate_matches_config` should follow the same extract-and-compare shape for a `window.__CONFIDENCE_GATE__` assignment.
- `RESERVED_STATE_NAMES`'s doc comment (`policy_builder_core.mjs:146-156`) is maintained as a running changelog narrating which serializer emits each added name; prior additions (BUG-3489/BUG-3486) updated it in place rather than replacing it — the new terminal names should extend it the same way.

## Impact

- **Priority**: P3 - richer lifecycle semantics; design decisions resolved 2026-09-16/17

- **Effort**: Medium - new transition kinds, rule-target destinations, dimension metadata, config stamping

- **Risk**: Medium - changes emitted YAML for every mode (`on_max_steps`); all golden `.yaml` fixtures regenerate

- **Breaking Change**: No

## Program Design

### Types

Outcome `transition.kind` gains `"stop" | "skip" | "attention"` alongside existing `"finish"`/`"rescore"`/`"goto"`. Lifecycle rule `target` and `fallback` additionally accept the built-in destination names `stopped` | `skipped` | `needs_attention` (a `LIFECYCLE_DESTINATIONS` constant in core.mjs, distinct from `LIFECYCLE_VERBS`; each is `{name, failure: boolean}`). Dimension entries gain optional `instructions: string` and `anchors: {score: number, meaning: string}[]`. Stamped `__CONFIDENCE_GATE__ {enabled, readiness_threshold, outcome_threshold}` in the template.

### Signatures

- `_outcomeStateLines(outcome, {doneState, issueArg, mode}) -> string[]` (`policy_builder_core.mjs:1399`) — gains a `mode` option (the function has no mode awareness today) so `transition.kind` `stop`/`skip`/`attention` emit `next: stopped`/`next: skipped`/`next: needs_attention` **only when `mode === "issue_lifecycle"`** (this function is shared by all three modes), and emit that `next:` line even when the outcome has no action (see §2 "Action-less outcomes"); the terminal blocks themselves are emitted by `_serializeIssueLifecycle` (`:1698`), not here. Model load/validation rejects a `stop`/`skip`/`attention` `transition.kind` on a `rubric`/`decision_table` outcome (including an imported one) before it reaches this function.

- `_emittedVerbs(model) -> string[]` (`:1664`) — unchanged; two **new** companions are added (no destination helper exists today): `_dispatchedDestinations(model)` returns which built-in destinations have an author-selected reference (rule target, fallback, or verb `transition.kind` — **excluding** the automatic `on_max_steps` route) and drives which dispatch route entries `_serializeIssueLifecycle` emits; `_requiredTerminalBlocks(model)` returns `_dispatchedDestinations(model)` plus `needs_attention` whenever `on_max_steps` targets it, and drives which terminal blocks are emitted. The two sets differ exactly when `on_max_steps` is the only reference to a destination.

- `_doneStateName(model) -> string` (`:1445`) — unchanged

- `_scoreActionBody(model) -> string` — emits optional instructions/anchors in rubric and decision-table grading prompts

- `serializeFrontmatterDimensions(model) -> string` and `_serializeDimensions(model) -> string` — unchanged wire formats

- `_checkReservedTokens` / `_checkMissingReferences` / `_assertNoReservedTokens` — accept built-in lifecycle references but reject definitions that shadow generated states; `_serializeRubric` (`:1558`) gains its own `_assertNoReservedTokens("rubric", model)` call (§3)

- `summarizeTransitions(model)` (`:1161`) and the template's `computeSummary(model)` (`policy-router-builder.html.tmpl:445`) — extended per §6 to report destinations

- `cmd_policy_builder(args, logger) -> int` — reads `config.commands.confidence_gate` and stamps it

### Call Path

`serializeLoopYaml` (`policy_builder_core.mjs:1776`) -> `_serializeIssueLifecycle` (`:1698`) -> `_emittedVerbs`/`_emittedDestinations` -> `_outcomeStateLines` (`:1399`) -> terminal-state emission (currently the fixed `done`/`failed` blocks at `:1760-1766`; `on_max_steps: failed` literal at `:1727`). `cmd_policy_builder` -> `BRConfig` -> template stamping; the builder displays thresholds beside rule thresholds.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `policy-router-builder.html.tmpl:604,747` — add entries for the new terminal destinations to the transition-kind `<select>` options list (currently only `rescore`/`goto`/`finish`), offered only when `state.mode === "issue_lifecycle"`

- Update `scripts/tests/js/policy_validator.test.mjs:227-236` — extend the `RESERVED_STATE_NAMES` sorted-array assertions with `stopped`/`skipped`/`needs_attention`, per mode

- Update `scripts/tests/js/policy_validator.test.mjs:274` — adjust the `on_max_steps: failed` literal match if routing changes to `needs_attention`

- Update `scripts/tests/js/policy_validator.test.mjs:375-378` — assert metadata leaves the joined string unchanged and appears only in grading prompts

- Update `scripts/tests/test_fsm_executor.py::TestGeneratedPolicyRouterFailureRouting` — adjust hardcoded terminal-literal assertions (`final_state`, `failure_terminal`) to match the new fixture shape

- Update `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` and `sample-issue-lifecycle.yaml` — update the `on_max_steps` line and regenerate

- Add `test_emitted_confidence_gate_matches_config` to `scripts/tests/test_policy_builder_emit.py` — verify the stamped `confidence_gate` JSON matches `BRConfig(Path.cwd()).commands.confidence_gate`

- Add coverage for the new transition-kind destinations in `scripts/tests/test_policy_builder_emit.py` (no existing test asserts on the `rescore`/`goto`/`finish` `<select>` list)

- Update `docs/guides/POLICY_ROUTER_GUIDE.md:249-256` ("Reserved names" section) — reflect the three new reserved tokens

- Verify `scripts/tests/test_fsm_fragments.py`'s `frontmatter_scores` fragment env-contract assertions to prove `instructions`/`anchors` leave the emitted dimension string format unchanged

- Update `docs/guides/POLICY_ROUTER_GUIDE.md:412` — the Seeded example's `on_max_steps: failed` prose to `needs_attention`

- Verify the new stamped `/*__CONFIDENCE_GATE_JSON__*/`-style placeholder is fully substituted, so `test_policy_builder_emit.py::test_emit_writes_html`'s `assert "/*__" not in html` keeps passing

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- `summarizeTransitions` (`policy_builder_core.mjs:1161-1215`) is a caller of `_emittedVerbs` not previously named in this issue's Call Path; it derives `implementOutcome`, a `verification` classification, and `stepsPerAttempt`/`maxStepsNote` consumed only by the UI's `#transition-summary` display (`policy-router-builder.html.tmpl:1120-1135`, `issue_lifecycle` mode only). Proposed Solution §6 ("Extend ENH-3491's transition summary for the destinations") targets this function; it sits outside `serializeLoopYaml`'s emission path.
- `_serializeRubric` (`policy_builder_core.mjs:1558-1633`) does not call `_assertNoReservedTokens` today, unlike `_serializeDecisionTable`/`_serializeIssueLifecycle`. Adding `needs_attention` to `RESERVED_STATE_NAMES.rubric` registers it for the non-throwing `_checkReservedTokens`/`validateBuilderModel` UI path only; the throwing defense-in-depth check will not fire for rubric unless `_serializeRubric` also gains its own `_assertNoReservedTokens("rubric", model)` call.
- `_checkMissingReferences` (`policy_builder_core.mjs:507`) currently requires every rule target/fallback/`goto` target to resolve to a defined `model.outcomes` entry — it has no existing concept of a reference that is legal without being a definition. Proposed Solution §3's reference-vs-definition distinction for the new built-in destinations is new logic for this function, not an extension of an existing branch.
- The existing convention for a multiline field that may be absent (`_yamlBlockScalar`, `policy_builder_core.mjs:1293-1298`, used at the `model.description` call site) guards emission with `if (model.<field>) { push "<key>: |"; push _yamlBlockScalar(value, indent) }`, omitting the key/body pair entirely when the field is unset rather than emitting an empty block scalar. Proposed Solution §4's `instructions` field should match this shape.

## Acceptance Criteria

- [x] Decision questions 1-3 resolved and recorded in this issue before implementation (`/ll:decide-issue` 2026-09-16; questions 4-5 added and resolved in review 2026-09-17).

- [ ] `stopped`, `skipped`, and `needs_attention` each emit YAML that passes `ll-loop validate`, reachable both as a rule target/fallback and as a verb `transition.kind`, covered by fixture pairs in the Node gate — **lifecycle mode only**. `rubric` and `decision_table` models reject a `stop`/`skip`/`attention` `transition.kind` (both freshly authored and imported), and their transition-kind `<select>` never offers these options. Tests cover rejection in both non-lifecycle modes.

- [ ] For an existing five-verb model with no author-selected reference to `needs_attention`, the regenerated YAML gains the `needs_attention` terminal block and the changed `on_max_steps` line but **no** new dispatch route — dispatch routes are emitted only for rule/fallback/verb-transition references, never solely because of `on_max_steps`. Tested by asserting on the emitted route list, not just diff shape.

- [ ] `needs_attention` emits `failure: true`; `stopped`/`skipped` do not. `TestGeneratedPolicyRouterFailureRouting` gains a max-steps case asserting `final_state == "needs_attention"`, `terminated_by == "max_steps"`, and `failure_terminal is True` (BUG-3499, `depends_on`, is done — see Proposed Solution §2).

- [ ] For every existing `.model.json` fixture, the regenerated `.yaml` differs from the pre-change golden only by the added or changed `on_max_steps` line and the added terminal blocks (asserted by a diff-shape test, not byte equality).

- [ ] Generated names are reserved per mode. Authored outcomes shadowing them fail both UI validation and serializer guards (including `_serializeRubric`, which gains the `_assertNoReservedTokens` call); valid lifecycle rule/fallback references succeed, unknown references fail, and each referenced terminal is emitted once. Tests cover all three reference mechanisms and every mode.

- [ ] A lifecycle outcome combining `actionType: none` with `stop`/`skip`/`attention` is rejected by `validateBuilderModel`; the serializer still emits `next: <destination>` (never a bare `terminal: true`) for those kinds when no action is present. Both branches are tested.

- [ ] Optional scoring instructions/anchors survive project Save/Open and appear in rubric/decision-table grading prompts. Tests cover invalid/duplicate/out-of-range anchors, boolean anchors, multiline escaping, and absent-metadata prompt compatibility. Lifecycle hides these controls and preserves imported metadata without changing frontmatter extraction or its wire format. Instructions and anchor meanings are literal text, never runtime-interpolated: a regression test asserts that an instruction containing `${...}` neither raises `InterpolationError` nor is substituted at execution time, and that the literal text reaches the grading prompt unchanged; the same test covers an authored `$${...}` instruction reaching the prompt as `$${...}`.

- [ ] Adding the new destination options to the transition-kind UI does not regress `renderFallback()`: with coverage that actually exercises selecting a `skipped` (or `stopped`/`needs_attention`) fallback, rerendering the form, and reopening the saved project — not just asserting the option labels are present — confirming a saved fallback absent from `state.outcomes` is never silently replaced by the first outcome.

- [ ] Builder displays stamped enabled/readiness/outcome values from `BRConfig`; tests cover disabled gates and confirm saved predicates are not overwritten by stamped thresholds.

- [ ] Transition summaries distinguish successful stop/skip from failed `needs_attention`, including the automatic max-steps route: `summarizeTransitions` treats `stop`/`skip`/`attention` on `implement` as stopping after implement, and the template's `computeSummary` lists dispatched destinations alongside verbs.

- [ ] CLI.md and POLICY_ROUTER_GUIDE.md passages listed above are updated.

## Scope Boundaries

Includes destination semantics, scoring metadata, gate stamping, and their docs. Excludes persistence (ENH-3487), layout/presets (ENH-3491), and runtime policy-router fixes. The one runtime change the chosen semantics require — `failure_terminal` honoring the `failure:` flag for cap-routed finishes — is BUG-3499, now in `depends_on`; this issue does not modify `fsm/executor.py`. Also excluded: seeding fresh models' thresholds from the stamped confidence gate (Proposed Solution §5), and any runtime behavior keyed on the `stopped`/`skipped` names beyond `final_state` (§2).

## Verification Notes

Historical observations below describe earlier drafts; the current Proposed Solution and Acceptance Criteria supersede their open-question and preservation-flag language.

_Added by `/ll:verify-issues` — 2026-09-16 (batch run with ENH-3487/ENH-3491):_

Verdict at time of check: **PROPOSAL_UNSOUND** (the citation and Current-Behavior corrections
below were applied in the same pass; the RESERVED_STATE_NAMES gap was not — it needs an
author/implementer decision alongside the three already-open decision questions, not a
mechanical fix, so it remains an outstanding action item).

- **PROPOSAL_UNSOUND finding (check B6)**: BUG-3489 (committed `22f4ff6ed`, landed after this
  issue was captured) added `RESERVED_STATE_NAMES`/`isReservedOutcomeToken`
  (`policy_builder_core.mjs:152-172`) specifically so an authored outcome name, rule target,
  or fallback can never silently collide with a generated state key — its own issue text says
  BUG-3486 must extend this shared map for new generated names rather than define a parallel
  list. This issue's Proposed Solution adds three new generated terminal names
  (`stopped`/`skipped`/`needs_attention`) but never mentions `RESERVED_STATE_NAMES` or the
  guard; implemented as written, an author could name an outcome or rule target
  `needs_attention` (or `stopped`/`skipped`) and it would collide with the generated terminal
  at emission — the exact bug class BUG-3489 just fixed for `done`/`failed`/`error`. Added an
  explicit "also add each new terminal to `RESERVED_STATE_NAMES`" line to the Proposed
  Solution and a matching Acceptance Criterion; the decision questions and implementation
  still need to account for it once `/ll:decide-issue ENH-3492` resolves the exact terminal
  names (the reserved-name entries depend on those exact names).
- **Current Behavior correction**: this issue's claim "`decision_table` ... emits no
  `on_max_steps`" is now false — the same BUG-3489 commit unconditionally added
  `on_max_steps: failed` to `_serializeDecisionTable` (confirmed in
  `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7`), with no model flag,
  and the golden fixtures were already regenerated (not kept byte-equal). Corrected in place,
  and Decision Question 3's premise ("existing golden fixtures must stay byte-equal") no
  longer applies to `decision_table` — only to `rubric`, which still emits no `on_max_steps`.
  The remaining open question for `decision_table` narrows to whether its existing `failed`
  terminal should become `needs-attention` instead.
- **Anchor drift (fixed in this pass)**: BUG-3489/BUG-3486 work inserted ~66-70 new lines into
  `policy_builder_core.mjs` ahead of every function this issue cites. Corrected:
  `_serializeIssueLifecycle` (`974-1041`→`1052-1122`), its `on_max_steps: failed`
  (`1002`→`1081`), per-verb `on_error: failed` (`1031`→`1111`), `done`/`failed` terminals
  (`1034-1039`→`1114-1120`); `_serializeDecisionTable` (`741-833`→`807-910`); `_serializeRubric`
  (`834-909`→`912-987`); `_outcomeStateLines`/`_doneStateName` (`687-739`→`753-805`);
  `serializeFrontmatterDimensions` (`925`→`1003`). `context_seed.py:68`,
  `check_readiness.py:78-115`, `cli/artifact/policy_builder.py:56-107`, and
  `config/automation.py:155-170` (all unmodified files) were re-verified and remain accurate.
- **Citation error (unrelated to the drift above, fixed in this pass)**:
  `fsm/validation/structural_rules.py:26-35` (cited for "arbitrary terminal names are
  schema-legal") is an import block, not a terminal-name check, in both the working tree and
  HEAD before BUG-3489 — the citation was simply wrong. The actual check is
  `validate_fsm`'s "at least one terminal state" logic (no name constraint) at
  `structural_rules.py:1160-1168`; corrected in place.
- `docs/guides/POLICY_ROUTER_GUIDE.md` also shifted +60 lines (new "Failure Routing and
  Clean-Slate Scoring" subsection inserted ahead of "Visual Builder"): `227-229,290-291`→
  `287-289,350-351`, `295-301`→`355-361`; corrected in place. `docs/reference/CLI.md:5079-5095`
  (unmodified) re-verified accurate.
- Dependency backlink (fixed in this pass): this issue's `depends_on: BUG-3486` had no
  matching entry in `BUG-3486`'s `blocks:` list. Added `ENH-3491`/`ENH-3492` to `BUG-3486`'s
  `blocks:`. This issue's own `blocked_by: [ENH-3491]` already has a correct backlink now that
  `ENH-3491` declares `blocks: [ENH-3492]`.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query (`ll-issues decisions list --type rule --enforcement required
  --active-only`) returned no entries.
- `decision_needed: true` remains correct — Acceptance Criterion 1 explicitly requires the
  three decision questions resolved before implementation; that gate is unaffected by the
  findings above (it gains a fourth de-facto sub-question: reserved-name registration for
  whatever terminal names the decision settles on).

_Manual review — 2026-09-17:_

- `depends_on: BUG-3486` is satisfied (status `done`); BUG-3489 is also `done`.
- Anchor drift from commit `8faffee5a` (post-dates the last verify pass) corrected in place: `_serializeIssueLifecycle` `1052-1122`→`1370-1440`, its `on_max_steps` literal `1081`→`1399`, `done`/`failed` terminals `1114-1120`→`1432-1437`, `_outcomeStateLines`/`_doneStateName` `753-805`→`1071-1123`, `serializeFrontmatterDimensions` `1003`→`1321`, `RESERVED_STATE_NAMES`/`isReservedOutcomeToken` `152-172`→`157-186`, `serializeLoopYaml`→`1448`. `_serializeDecisionTable` is now `1125` and `_serializeRubric` `1230`. `policy_validator.test.mjs` anchors: `RESERVED_STATE_NAMES` assertions `231-243`, `on_max_steps: failed` match `282`.
- Resolved three gaps: (1) Expected Behavior/AC contradicted decisions 2-3 on byte-identical fixtures; (2) the failure flag on new terminals was undefined; (3) "rule routes to destination" vs "`transition.kind`" were two different mechanisms — both are now in scope with one shared terminal set.
- `_outcomeStateLines` signature corrected (takes an outcome, not the model).

_Third `/ll:verify-issues` pass — 2026-09-17 (batch run with ENH-3487/ENH-3491/FEAT-3488):_

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so
the issue as it now reads is up to date — this section is a record of what was wrong and
fixed, not an outstanding action item).

- Commit `25e39fb1d` (BUG-3490, "resolve installed plugin content root for skill/command
  discovery", 2026-09-17T00:12:13) rewrote `policy_builder.py` between the prior verify
  pass and this one, shifting the `cmd_policy_builder` citation in Current Behavior
  (`56-107`→`61-112`). No substance change: it still stamps only theme/CSS/grammar/catalog,
  still doesn't read `config.commands.confidence_gate` — the proposed gate-stamping addition
  is unaffected.
- `FSMExecutor._finish` line `4337` (the `failure_terminal` gate this issue's §2 runtime
  prerequisite depends on) re-confirmed by direct read — `terminated_by == "terminal"`
  precondition is exactly as cited; BUG-3499 remains open (untracked, not yet committed),
  so `depends_on: BUG-3499` is still accurate and unresolved.
- Doc citation correction (unrelated to the `25e39fb1d` commit, which touched
  `docs/reference/CLI.md:3757`/`docs/reference/API.md:11912` only — both above this issue's
  cited ranges with no net line-count change before line 5079): the Integration Map's second
  citation for "can't be deleted and no new outcome can be added" (`350-351`) pointed at
  unrelated custom-field-type prose; the phrase is actually at `docs/guides/
  POLICY_ROUTER_GUIDE.md:355-356`. Corrected in place; the companion `:355-361` citation
  (Verb Table) was already accurate.
- `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` anchors (all cited in Program
  Design) unaffected by `25e39fb1d`; re-confirmed unchanged since the prior pass's
  post-`8faffee5a` correction.
- Dependency backlinks checked directly: `blocked_by: [ENH-3491]` / `ENH-3491.blocks:
  [ENH-3492]` match; `depends_on: [BUG-3486, BUG-3499]` — BUG-3486 done with a matching
  `blocks:` backlink, BUG-3499 open (no backlink needed pending completion); `blocks:
  [FEAT-3488]` / `FEAT-3488.blocked_by` includes `ENH-3492` — consistent. No DEP_ISSUES
  findings.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query returned no entries.
- Proposal-vs-code consequence check (B6): no new issue found.

_Fourth `/ll:verify-issues` pass — 2026-09-17:_

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so
the issue as it now reads is up to date — this section is a record of what was wrong and
fixed, not an outstanding action item).

- **BUG-3499 has landed** (commit `9e3454cc5`, "honor failure terminals reached via
  step/iteration caps") between the prior pass and this one — `depends_on: BUG-3499` is
  now satisfied. `FSMExecutor._finish`'s guard (`executor.py:4333-4345`, the `4337`
  citation shifted slightly within the same comment block) now reads `terminated_by in
  ("terminal", "max_steps", "max_iterations_reached")`, confirmed by direct read. Proposed
  Solution §2's "Runtime prerequisite" paragraph and the matching Acceptance Criterion
  described this as a still-open contingency ("until it lands" / "once ... has landed");
  corrected in place to state it as resolved, and the deferred second assertion on
  `failure_terminal is True` is now a direct one.
- **Anchor drift from commit `f0fa5c404`** ("add task presets, verification contract, and
  execution summary", landed after the prior pass, before the wire-issue pass at
  `2888d3052`): shifted every `policy_builder_core.mjs` function this issue's Current
  Behavior and Program Design sections cite by +646 lines. The wire-issue pass's own new
  citations (Codebase Research Findings' `_serializeRubric:1558-1633`,
  `summarizeTransitions:1161-1215`, `_checkMissingReferences:507`,
  `_yamlBlockScalar:1293-1298`) were already written against the post-shift file and are
  unaffected — only the older Current Behavior / Program Design Signatures / Call Path
  citations (last corrected in the manual review predating `f0fa5c404`) had drifted.
  Corrected in place: `_serializeIssueLifecycle` `1052-1122`→`1698-1768` (on_max_steps
  `1081`→`1727`, per-verb `on_error` `1111`→`1757`, `done`/`failed` terminals
  `1114-1120`→`1760-1766`); `_serializeDecisionTable` `807-910`→`1453-1555`;
  `_serializeRubric` `912-987`→`1558-1633`; `_outcomeStateLines` `1071`→`1399`;
  `_emittedVerbs` `1336`→`1664`; `_doneStateName` `1117`→`1445`; `serializeLoopYaml`
  `1448`→`1776`. `cmd_policy_builder` shifted by 1-2 lines (`61-112`→`62-114`) from an
  earlier, unrelated commit; no substance change — still stamps only theme/CSS/grammar/
  catalog, still doesn't read `config.commands.confidence_gate`.
- **Doc citation drift**, same `f0fa5c404` commit (it also inserted a task-presets
  paragraph plus new Dimension/Verb tables into `POLICY_ROUTER_GUIDE.md`'s "Issue
  Lifecycle Mode" section): the "can't be deleted and no new outcome can be added" phrase
  moved `355-356`→`378-379`; the Verb Table moved `355-361`→`383-389`. The Wiring Phase
  Documentation bullet's back-reference to these citations (`:287-289`/`:350-351`/
  `:355-361`) was already stale before this pass — corrected to the new locations.
  `docs/reference/CLI.md`'s "five fixed lifecycle verbs" sentence is a single un-wrapped
  paragraph line that moved `5081`→`5083`; the range citation collapsed to the one line.
  `POLICY_ROUTER_GUIDE.md:249-256` (Reserved names) and `:412` (Seeded example) are
  unaffected — re-confirmed unchanged.
- Confidence Check Notes' sole gap (`blocked_by: ENH-3491` unresolved) is now stale:
  ENH-3491 is `status: done`, and this issue's own `blocked_by` frontmatter is already
  empty (cleared in an earlier pass) — the dependency the gap named is satisfied. Left the
  Confidence Check Notes section itself untouched (owned by `/ll:confidence-check`); a
  re-run would likely clear the STOP verdict.
- Dependency backlinks re-checked: `depends_on: [BUG-3486, BUG-3499]` both `done`, both
  satisfied (informational); `blocked_by: []`; `blocks: [FEAT-3488]` / `FEAT-3488.blocked_by`
  includes `ENH-3492` — consistent. No DEP_ISSUES findings.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query returned no entries.
- Proposal-vs-code consequence check (B6): no new issue found — the mechanism the
  Proposed Solution describes is unaffected by the anchor drift or BUG-3499 landing.

_Fifth review pass (manual, review feedback) — 2026-09-17:_

Verdict: close, with four gaps resolved in this pass (no files changed, evidence check
passed, decisions query returned no active required rules):

1. Lifecycle-only transition kinds were implied but not enforced end-to-end: `_outcomeStateLines`
   is shared by all three modes, and the wiring instructions updated both transition selectors
   without restricting the new options to lifecycle. Corrected Proposed Solution §1, the
   `_outcomeStateLines` signature, and Acceptance Criteria to require the new `transition.kind`
   values and their `<select>` options be lifecycle-only, and to require `rubric`/`decision_table`
   to reject them (including on import).
2. Dispatch destinations and emitted terminal blocks were conflated: `_emittedDestinations`
   would have included `needs_attention` solely because of `on_max_steps`, adding a dispatch
   route to every existing lifecycle fixture and contradicting the "budget-line and terminal-block
   changes only" acceptance criterion. Split into `_dispatchedDestinations` (author-selected
   references only) and `_requiredTerminalBlocks` (dispatched destinations plus `on_max_steps`'s
   target); added an Acceptance Criterion asserting no new dispatch route appears when only
   `on_max_steps` references a destination.
3. Runtime escaping for scoring text was unspecified: a YAML block scalar protects YAML
   structure but not FSM interpolation — an instruction containing `${customer.name}` was
   confirmed (probe) to raise `InterpolationError` at execution time. Specified instructions/anchor
   meanings as literal, non-interpolated text requiring `${` escaping at emission, with a runtime
   regression test.
4. `renderFallback()` silently replaces a fallback absent from `state.outcomes` with the first
   outcome; adding destination options without covering this would risk silently replacing a
   saved `skipped` fallback. Added an Acceptance Criterion requiring coverage through an actual
   select/rerender/reopen cycle, not just option-label presence.

Also pinned action-before-terminal behavior (a verb with `attention` runs its action once, then
reaches the failure terminal; action errors still route to `failed`) in Proposed Solution §2, and
retired the stale STOP confidence-check verdict below — both dependencies it named (ENH-3491,
BUG-3499) are now `done`.

_Seventh `/ll:verify-issues` pass — 2026-09-17:_

Verdict: **VALID**. No commits touched any cited file (`policy_builder_core.mjs`,
`policy-router-builder.html.tmpl`, `cli/artifact/policy_builder.py`, `fsm/executor.py`,
`docs/reference/CLI.md`, `docs/guides/POLICY_ROUTER_GUIDE.md`) between the prior pass
(`aa2ef1015`/`ee8978dc2`) and this one. Re-confirmed by direct read, all citations exact:
`_serializeIssueLifecycle` (`:1698`), `on_max_steps: failed` (`:1727`), `done`/`failed`
terminals (`:1760-1766`), `_outcomeStateLines` (`:1399`), `_doneStateName` (`:1445`),
`_serializeDecisionTable` (`:1453`), `_serializeRubric` (`:1558`, still lacking
`_assertNoReservedTokens` per §3's proposed change), `_emittedVerbs` (`:1664`),
transition-kind `<select>` literals (`:604,747`), `FSMExecutor._finish`'s widened
`terminated_by in ("terminal", "max_steps", "max_iterations_reached")` guard, CLI.md:5083,
POLICY_ROUTER_GUIDE.md:378-379/383-389/412. Dependency backlinks consistent:
`depends_on: [BUG-3486, BUG-3499]` both done with matching `blocks:` entries;
`blocked_by: []`; `blocks: [FEAT-3488]`/`FEAT-3488.blocked_by` includes `ENH-3492`. No
DEP_ISSUES. `ll-verify-evidence --json`: `ok: true`, 0 findings. Decisions log: no active
required rules. Proposal-vs-code consequence check (B6): no new issue.

_Sixth review pass (manual, pre-implementation) — 2026-09-17:_

Verdict: ready after the corrections applied in this pass. Verified against the working tree:
`$${` escaping (`fsm/interpolation.py:30,348`), `_TARGET_PATTERN` accepting
`needs_attention` (`fsm/policy_rules.py:37`), `on_max_steps` targets counted as reachable
(`fsm/validation/_base.py:234`), and the on_max_steps terminal exemption
(`fsm/validation/evaluator_rules.py:42-52`) — so a `needs_attention` block referenced only by
the budget line trips neither an unreachable-state nor a terminal-action warning.

- `_emittedDestinations` was cited as an existing helper to keep/replace; it does not exist.
  Reworded §1 and the Program Design signature: both destination helpers are new.
- Transition-kind `<select>` citation `policy-router-builder.html.tmpl:420,524` was wrong
  (`:420` is the end of draft restore, `:524` is inside `renderFallback()`); the option-list
  literals are at `:604,747`. Corrected in three places.
- Specified action-less outcomes with the new kinds (`_outcomeStateLines` emits `terminal: true`
  when `hasAction` is false): emit `next: <dest>` and reject the combination in
  `validateBuilderModel`; new AC.
- Promoted the rubric `_assertNoReservedTokens` gap from research notes to a required §3 change,
  noting the silently-ignored → hard-error behavior change.
- Made §6 concrete: `summarizeTransitions.stopsAfterImplement` (`:1168`, finish-only today) and
  the template's `computeSummary` lifecycle branch (verbs only).
- Escaping test must also cover authored `$${...}` (doubling composes: `$$${` → `$${`).
- Stated that `stopped`/`skipped` are distinguishable from `done` only via `final_state`; FEAT-3488
  does not reference the names.
- Seed-from-stamp for fresh models excluded explicitly (Scope Boundaries) to keep `seedExample`
  pure and the Node golden fixtures stable.
- Confidence Check Notes below still carry the stale STOP; re-run `/ll:confidence-check` before
  `/ll:manage-issue`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-17; STOP verdict below is stale as of the 2026-09-17 review — both dependencies it named are now satisfied (ENH-3491 `status: done`; BUG-3499 `status: done`, `depends_on` frontmatter already reflects this) and `blocked_by` is empty. A re-run of `/ll:confidence-check` would be expected to clear the STOP verdict; this section is left as a historical record pending that re-run._

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (dependencies hard override; superseded, see note above)
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address (resolved)
- ~~`blocked_by: ENH-3491` is unresolved (status `Open`, not `done`/`cancelled`) — the BUG-3051 Dependencies Hard Override forces this verdict regardless of the otherwise-80/100 aggregate. Wait for ENH-3491 to land, or drop it from `blocked_by` if the layout/preset work it depends on is no longer a prerequisite.~~ Resolved: ENH-3491 is `status: done` and BUG-3499 is `status: done`.

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-09-17T19:29:37 - `067aee00-97de-4da1-af70-f2f7a36f18d0.jsonl`
- `/ll:verify-issues` - 2026-09-17T19:20:20 - `db7e2ee5-b919-46a0-b998-938b24125dfa.jsonl`
- manual review - 2026-09-17 - pre-implementation pass: fixed `_emittedDestinations` (nonexistent) and template `<select>` (`:604,747`) citations; specified action-less outcomes with new kinds; required rubric `_assertNoReservedTokens`; made §6 summary changes concrete; `$${` round-trip test; `final_state`-only distinction; excluded seed-from-stamp.
- manual review - 2026-09-17 - resolved four review gaps: restricted new transition kinds/destinations to lifecycle mode (reject in rubric/decision_table); split dispatch-destination emission from required-terminal-block emission so `on_max_steps` alone adds no dispatch route; specified literal-text runtime escaping for scoring instructions/anchors with an `InterpolationError` regression test; added `renderFallback()` select/rerender/reopen coverage. Pinned action-before-terminal behavior; retired stale STOP confidence verdict (ENH-3491/BUG-3499 both done).
- `/ll:verify-issues` - 2026-09-17T18:57:38 - `64b082f5-b4f8-409b-a5d1-79e44b8a0152.jsonl`
- `/ll:wire-issue` - 2026-09-17T18:46:50 - `291797e2-08f6-425b-9547-d7555f015908.jsonl`
- `/ll:refine-issue` - 2026-09-17T18:30:29 - `46c00341-49d5-41d7-9341-4caa93d77adc.jsonl`
- `/ll:confidence-check` - 2026-09-17T06:34:34 - `848ad701-11e3-43ba-8e5b-b86aa9978421.jsonl`
- `/ll:verify-issues` - 2026-09-17T06:28:31 - `9b9f3eca-ed5d-4fd7-a99d-217cb278def3.jsonl`
- manual review - 2026-09-17 - executor probe showed cap-routed `failure_terminal` is False; filed BUG-3499 and added to `depends_on`; max-steps AC asserts `terminated_by` now, `failure_terminal` after BUG-3499; rubric `on_max_steps` is an added line in the diff-shape AC
- manual review - 2026-09-17 - resolved terminal-reference reservation contradiction; moved scoring metadata to grading prompts; fixed project-round-trip criteria; preserved wire protocols; clarified gate display and terminal summaries
- manual review - 2026-09-17 - resolved byte-identical contradiction, defined failure flags and rule-target vs transition mechanisms, corrected anchors post-8faffee5a
- `/ll:verify-issues` - 2026-09-17T02:36:59 - `ed6d999b-26a2-4d77-bbbf-604f7482188a.jsonl`
- `/ll:wire-issue` - 2026-09-17T02:03:58 - `5caaeb95-8e3b-4dc5-9258-679a7e06d4cd.jsonl`
- `/ll:decide-issue` - 2026-09-17T01:33:55 - `be9c9d04-b7b3-40fa-a6b2-8aa383887a4c.jsonl`
- `/ll:verify-issues` - 2026-09-17T01:18:51 - `716b78b0-d53f-401a-997f-791cc3ac58be.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-16T23:13:05 - `e4d4d311-3a45-427a-958f-7960765e8da2.jsonl`
