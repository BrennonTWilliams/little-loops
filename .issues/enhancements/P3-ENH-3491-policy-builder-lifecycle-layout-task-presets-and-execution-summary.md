---
id: ENH-3491
parent: EPIC-3493
epic: EPIC-3493
type: ENH
title: Policy builder lifecycle layout, task presets, and execution summary
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:49:50Z'
completed_at: '2026-09-17T18:20:27Z'
labels:
- policy-builder
decision_needed: false
depends_on:
- BUG-3486
- ENH-3487
relates_to:
- ENH-3492
- FEAT-3474
blocks:
- ENH-3492
- FEAT-3488
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
verify_verdict: VALID
---

# ENH-3491: Policy builder lifecycle layout, task presets, and execution summary

## Summary

Reorganize the policy builder's lifecycle authoring flow so users edit fields and rules before advanced action settings, pick a task preset, and see an accurate execution summary. Split out of ENH-3487 (workstream b: layout and interaction); no change to emitted YAML.

## Current Behavior

The lifecycle page presents nine built-in fields (`BUILTIN_FRONTMATTER_DIMENSIONS`, `scripts/little_loops/templates/policy_builder_core.mjs:89`) and five action editors (one generic `renderLifecycleOutcomes()` loop over `LIFECYCLE_VERBS`, `scripts/little_loops/templates/policy-router-builder.html.tmpl:453`) before its rules. The grading-subject input (`#f-subject`, tmpl `:144`) is shown in lifecycle mode but never read by `_serializeIssueLifecycle()`. The verb list is described like a pipeline even though implementation stops by default. Max steps counts FSM state executions, not whole attempts, and nothing explains that. The two-column CSS grid (tmpl `:32`) has no `@media` breakpoint; no authored template in `scripts/little_loops/templates/` has one. Skill descriptions are collected but not displayed. The only collapsible precedent is the `<details>` around raw YAML (tmpl `:222`); fieldsets are toggled only per mode via `applyModeVisibility` (`:885-901`). (Anchors re-verified 2026-09-17 post-`8faffee5a`; see Program Design.)

Two facts the preset design depends on (verified 2026-09-17): the empty-body diagnostic in `validateBuilderModel` (`policy_builder_core.mjs:555-563`) fires only for `prompt` and `slash_command` action types — an empty `shell` body is not flagged and would export `action:  ${context.issue_id:shell}`. And `buildModel()` (tmpl `:248-268`) rebuilds each outcome from a fixed field list (`name, actionType, body, args, transition`), so any extra key stored on a `state.outcomes[i]` entry is dropped before `validateBuilderModel`/`serializeLoopYaml`/any summary function sees it.

## Expected Behavior

Lifecycle authoring is organized as Fields, Rules, Try it, Export. Action bindings and budgets sit under an advanced-settings `<details>`. Task presets (document improvement, condition-based routing, preparation, implementation, implementation with verification) seed the form. Mode-irrelevant inputs are hidden. A summary shows the actual transitions of the current model, distinguishes state steps from attempts, and says whether implementation is followed by verification. Skill descriptions and argument hints are shown. The layout has no page-level horizontal overflow at 375px and desktop widths; all controls are keyboard-operable with associated labels.

## Proposed Solution

- Reorder fieldsets in the template and wrap action editors and budget inputs in a `<details id="advanced-details">` advanced section (collapsed by default); retain the existing `renderLifecycleOutcomes()` loop and `renderRules()` structure; extend the action editor only for the acceptance-verification contract below. Because a collapsed `<details>` hides the field a diagnostic points at, `updatePreview` must set `advanced-details.open = true` whenever `validateBuilderModel` returns an `error` diagnostic with `field === "outcomes"` or `"maxSteps"` (never auto-close it).

- Add task presets as pure, unit-tested constructors. The implementation-with-verification preset routes `implement` to `verify`, but replaces the default `/ll:verify-issues` action: that skill validates issue files, not implemented acceptance criteria. The preset uses a user-supplied shell acceptance-check command (a project wrapper/executable accepting the issue ID as its first appended argument, followed by configured args). Exit 0 means acceptance checks passed; nonzero/error routes to `failed` with `failure: true`; success finishes at `done`. Do not treat command dispatch alone as a pass.

  **Mechanism (review 2026-09-17, no serializer change needed):** the issue-ID-first argument shape is already produced by `_outcomeStateLines` (`policy_builder_core.mjs:1250-1255`), which appends ` ${context.issue_id:shell}` and then `args` to every lifecycle shell body. The exit-code routing works only because `_serializeIssueLifecycle` (`:1597`) emits `on_error: failed` on every verb state and `FSMExecutor` routes a nonzero exit to `on_error` when one is declared (`scripts/little_loops/fsm/executor.py:2161-2166`). The same mechanism makes an `implement` nonzero exit route to `failed` before `verify` ever runs. Add a `node:test` assertion that the preset's emitted `verify` state carries `on_error: failed` so a future serializer change cannot silently break the contract.

- **Preset ↔ mode contract.** Presets are cross-mode: document improvement → `rubric`, condition-based routing → `decision_table`, preparation / implementation / implementation-with-verification → `issue_lifecycle`. `TaskPreset.mode` is authoritative. Applying a preset whose mode differs from `state.mode` must, in one handler: save the outgoing draft into `drafts` (as the `mode-switch` handler at tmpl `:1106-1116` does), set `$("mode-switch").value` to `preset.mode`, replace **only** `drafts[preset.mode]` with `{model: preset.build()}`, then `applyStateToForm(); applyModeVisibility(); renderAll(); commit();` — exactly one history entry, so one undo restores both the previous `activeMode` and that mode's prior draft (ENH-3487 snapshots are whole-project, so this needs no core change). Same-mode presets take the same path minus the select update. Preset buttons render in every mode (they are not lifecycle-only), grouped with "Start blank".

- Initially leave that command empty and clearly label the preset as requiring configuration. **Extend the empty-body diagnostic to `shell`** (`policy_builder_core.mjs:555-563` currently covers only `prompt`/`slash_command`) so an unconfigured shell outcome is an `error` that blocks YAML Copy/Download like the other incomplete actions; add a `node:test` case for it. Save/Open of this unfinished preset must work via ENH-3487. Store authoring metadata `verificationContract: "acceptance_exit_code"` on the `verify` outcome. **Invalidation rule (corrected in review 2026-09-17):** the contract is cleared only when the outcome's `actionType` changes away from `shell`; editing `body` or `args` never clears it, because filling in the required command is itself a body edit and the preset flow must reach `"acceptance"` after configuration. The user sets/unsets it through a checkbox rendered in the action editor for `shell` outcomes only ("Exit code 0 means acceptance checks passed"; `id="oc-contract-<i>"`, label-associated, goes through the delegated `change` commit path). The preset renders it pre-checked; switching `actionType` off `shell` unchecks and hides it. **Carry it through `buildModel()`**: add `verificationContract` to the outcome projection at tmpl `:417-423` (it is otherwise dropped, see Current Behavior), and have `summarizeTransitions` classify from the built model, never from `state` directly. `serializeLoopYaml` ignores the key, so emitted YAML for existing models is unchanged. It is not a claim that arbitrary shell code has been inspected for correctness.

- Hide `#f-subject` in lifecycle mode via `applyModeVisibility`.

- Render a transition summary from reachable emitted transitions, not outcome names or list order. Distinguish issue-file validation, configured acceptance checks, unconfigured checks, and custom/unknown actions; a state named `verify` is insufficient evidence of acceptance verification. Cover branches, cycles, unreachable verify states, and changed action bindings. ENH-3492 extends this summary with its terminal destinations.

  `maxStepsNote` is computed, not canned: in lifecycle mode one attempt costs `score` + `policy_dispatch` + the longest reachable verb chain from a dispatch target (e.g. `implement → verify` = 2), so `stepsPerAttempt = 2 + chainLength` and `attempts = floor(maxSteps / stepsPerAttempt)`. Only `rescore` transitions start a new attempt; `goto` continues the current one; `finish` ends the run. The note states both numbers ("max steps 20 ≈ 5 attempts of 4 states each").

- Add `@media (max-width: 600px)` collapsing the grid to one column.

- Show `catalog` skill descriptions and argument hints in the action editor. **Argument hints are not in the stamped catalog today** (review 2026-09-17): `_load_skill_catalog` (`scripts/little_loops/cli/artifact/policy_builder.py:21-58`) projects only `{name, description}` out of the `HelpEntry` rows it already gets from `cli/help.py::collect_entries` — and `HelpEntry` already carries `argument_hint: str | None` (`cli/help.py:124`), parsed from `args`/`argument-hint` frontmatter. So no new parser is needed: carry `entry.argument_hint` through as a nullable `args_hint` key on each stamped row. This is the one `policy_builder.py` change in this issue; `test_policy_builder_emit.py` asserts every stamped row has the `args_hint` key and that a skill with a known hint stamps it verbatim. (`little_loops.tool_catalog` parses the same field independently for the MCP tool list; do not add a second catalog source.)

- Preset buttons go through ENH-3487's committed-edit path (push a history entry, persist the draft), exactly like "Start blank" — never a bare `applyStateToForm` that bypasses undo/persistence. **Draft-replacement rule:** preset and start-blank replace the entire draft wrapper object (`drafts[mode] = {model}`), never assign into `drafts[mode].model`. Start-blank already does this (tmpl `:1279`); keep it that way. Any sibling keys a later issue adds to the wrapper (FEAT-3488's `scenarios`) are therefore dropped atomically with the model and restored by the same single undo, with no scenario-aware code in this issue. No scenario UI or scenario-facing text is added here; FEAT-3488 owns that messaging. Other drafts and project identity are preserved.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md:5081-5096` (`#### ll-artifact policy-builder`) — reflect task presets, the collapsed advanced-action `<details>`, and skill argument-hint display alongside the existing `docs/guides/POLICY_ROUTER_GUIDE.md` update.
- Add `taskPresets`/`summarizeTransitions` to the named-export import list in `scripts/tests/js/policy_validator.test.mjs:9-39`.
- Add a `test_persistence_and_history_affordances_present` regression check to the fieldset-reorder test pass, or confirm it still passes unmodified.
- The `args_hint`/`__SKILL_CATALOG_JSON__` extraction test must regex `window\.__SKILL_CATALOG__\s*=\s*(\[.*?\]);` out of the rendered HTML (an array), not the source-only `/*__SKILL_CATALOG_JSON__*/` placeholder token (`policy_builder.py:99`, replaced away at generation time) or `_extract_grammar`'s object-shaped `\{.*?\}` pattern — see Acceptance Criteria correction below.

## Integration Map

- Files to modify: `scripts/little_loops/templates/policy-router-builder.html.tmpl`; `scripts/little_loops/templates/policy_builder_core.mjs`; `scripts/little_loops/cli/artifact/policy_builder.py` (`_load_skill_catalog` gains `args_hint` only).

- Tests at risk: `scripts/tests/test_policy_builder_emit.py::TestFeat2301UsabilityStructural` (`test_seed_and_blank_wiring_present`, `test_rubric_mode_has_no_dt_only_affordances`, `test_yaml_is_collapsed_behind_details`) depend on the `start-blank-btn`, `rules-fieldset`/`outcomes-fieldset`/`tryit-fieldset`, `yaml-details`/`yaml-preview`/`yaml-summary` ids; keep the ids or update the tests. `test_theme_resolution_order_is_stored_stamped_os_light` must keep passing.

- Add configured verification fixtures to `test_policy_builder_node_gate.py` and stub-command execution cases to `test_fsm_executor.py` (existing precedent: `TestGeneratedPolicyRouterFailureRouting`, `scripts/tests/test_fsm_executor.py:2810-2917` — loads a real generated fixture via `resolve_fragments`, runs `FSMExecutor`, stubs commands with `MockActionRunner.set_result(pattern, exit_code=...)`); preserve all existing-model YAML goldens. Two stub pitfalls: `set_result` matches by substring, so the fixture's verify command must not be a substring of the `implement` command (`ll-auto --only`) or of any fragment action; and the failing-verify stub's `stderr` must be plain text — infra-looking stderr (rate-limit / timeout phrasing) is classified `INFRA_RETRY` by the executor (`executor.py:2343-2380`) and retries instead of routing to `on_error`.

### Tests (additional intra-file sites)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_validator.test.mjs:9-39` — the exhaustive named-export import list from `policy_builder_core.mjs`; add `taskPresets` and `summarizeTransitions` here once exported, alongside `seedExample`/`blankModel`/`validateBuilderModel`/`applyDraftEdit`.
- `scripts/tests/js/policy_validator.test.mjs:779-864` (ENH-3487 section) — pattern to follow for "preset applies through the committed-edit path, one undo restores prior state": build `history` via sequential `applyDraftEdit(history, {type: "commit", activeMode, drafts})` calls, assert `history.past.length` increments by one per commit, then `applyDraftEdit(history, {type: "undo"})` and assert the restored draft matches the pre-commit snapshot.
- `scripts/tests/test_policy_builder_emit.py::TestFeat2301UsabilityStructural::test_persistence_and_history_affordances_present` (`:233-242`) — asserts `undo-btn`, `redo-btn`, `save-project-btn`, `open-project-btn`, `open-project-input`, `live-status`/`aria-live="polite"` are present; at risk if the fieldset reorder relocates or removes any of these controls (not previously cited alongside the other three `TestFeat2301UsabilityStructural` tests already named above).
- FYI: `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees specifically so `test_policy_builder_renders_byte_identically_to_golden_fixture` doesn't false-fail on degraded design tokens — since this issue forces a golden-fixture regeneration, any epic-branch verify run for this work depends on that stopgap remaining intact. No file change required here.

- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` (byte-identical golden test in `test_enh3035_artifact_template_kit.py`).

- Docs: `docs/guides/POLICY_ROUTER_GUIDE.md:258-303` ("Visual Builder") `:292-294` YAML-behind-details framing goes stale with a dedicated Export section. (Re-verified `/ll:verify-issues` 2026-09-16: a new "Failure Routing and Clean-Slate Scoring" subsection inserted earlier in the doc shifted this section by +60 lines from its originally-cited location.)

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wheel_smoke.py:241,253` — imports `_load_skill_catalog` directly against an installed wheel and asserts `"check-code" in {row["name"] for row in catalog}` by `name` only; the only call site of the function's return shape outside `cmd_policy_builder`. Safe against the new `args_hint` key (name-only assertion), no change required, but flag as existing coverage.

### Documentation (additional)
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5081-5096` (`#### ll-artifact policy-builder`) — narrates the current UI in enough detail (fieldset order, skill-catalog dropdown, collapsed YAML `<details>`) to go stale once task presets, the collapsed advanced-action `<details>`, and skill argument-hint display land; none of these are mentioned today.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- `scripts/tests/js/policy_validator.test.mjs` is the existing `node:test` suite for `validateBuilderModel`'s checkers, including the current `prompt`/`slash_command` case of `_checkIncompleteActions` (test at line 626). Every test in this file follows the same shape: build a model via `seedExample(mode)`, mutate the one field the check targets, run `validateBuilderModel(model)`, filter to `severity === "error"`, and regex-assert on `.message`. The private `_check*` functions are never imported directly — only `validateBuilderModel` is exported and exercised. The new `shell`-body test case belongs in this file, following that same convention.
- No existing test in `scripts/tests/test_policy_builder_emit.py` extracts or asserts on `__SKILL_CATALOG_JSON__` content — `_load_skill_catalog` has no direct unit test anywhere in `scripts/tests/` today (only referenced via the golden-fixture byte-comparison and a wheel-smoke-test string mention). The file's established convention for asserting on a different stamped JSON global (`__GRAMMAR_SPEC__`) is `_extract_grammar()` (line 78): regex out the `window.__X__ = (...);` assignment with `re.DOTALL`, `json.loads` the captured group, then assert on individual keys. The new `args_hint` assertion this issue's Acceptance Criteria requires will be a new test, not a modification of an existing one.

## Impact

- **Priority**: P3 - usability of repeat authoring; no correctness impact

- **Effort**: Medium - template reorder, presets, summary function, CSS

- **Risk**: Low - no emitted-YAML change; structural tests pin element ids

- **Breaking Change**: No

## Program Design

### Types

`TaskPreset {id, label, description, mode, build: () -> Model}` in `policy_builder_core.mjs`; `mode` is authoritative for the mode switch on apply. `TransitionSummary {steps: string[], stopsAfterImplement: boolean, verification: "acceptance" | "issue_validation" | "unconfigured" | "custom" | "none", stepsPerAttempt: number, attempts: number, maxStepsNote: string}`. Outcome entries gain an optional `verificationContract?: "acceptance_exit_code"` key, which `buildModel()` must project (tmpl `:417-423`) and `serializeLoopYaml` ignores; it is cleared only on `actionType` change away from `shell`. Summaries classify the current reachable action and contract, not merely its name.

### Signatures

- `taskPresets() -> TaskPreset[]` — pure; each `build()` returns a model shaped like `seedExample(mode)` output.

- `summarizeTransitions(model) -> TransitionSummary` — pure; derived from the same outcome/transition data `serializeLoopYaml` consumes.

### Call Path

`applyStateToForm` -> `applyModeVisibility` -> `updatePreview` -> `serializeLoopYaml`, with `summarizeTransitions` called from `updatePreview` and rendered next to the YAML preview. Preset buttons apply `preset.build()` through ENH-3487's committed-edit path (`applyDraftEdit` + persist), then `applyStateToForm`. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:61-112`) changes only in `_load_skill_catalog` (`args_hint`); the golden fixture is regenerated.

Anchors (re-verified in review 2026-09-17 after commit `8faffee5a`, which shifted every core.mjs/template anchor): `applyStateToForm` (`scripts/little_loops/templates/policy-router-builder.html.tmpl:906-912`), `applyModeVisibility` (`:885-901`), `updatePreview` (`:840-864`), `renderAll` (`:866-883`), `renderLifecycleOutcomes()` (`:453`), `renderRules()` (`:556`), `#f-subject` (`:144`), YAML `<details>` (`:222`), grid (`:32`) live in the template; `serializeLoopYaml` (`scripts/little_loops/templates/policy_builder_core.mjs:1448`), `seedExample` (`:782`), `blankModel` (`:857`), `LIFECYCLE_VERBS` (`:108-144`), `BUILTIN_FRONTMATTER_DIMENSIONS` (`:89`), `_emittedVerbs` (`:1336`) are in the pure-JS core; `summarizeTransitions` and `taskPresets` are new exports added next to `seedExample`. The transition is expressible with `implement.transition = {kind: "goto", target: "verify"}` (`_emittedVerbs` follows goto chains), but the default verify action must be replaced with the explicit acceptance-check contract above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Anchors re-verified 2026-09-17 (post-commit `50b3d37a5`, "add draft persistence, undo/redo, and saved projects" — this is ENH-3487, which has now landed on `main`; see Scope Boundaries finding below). Every function anchor in this section's own "Anchors" paragraph and "Call Path" above predates that commit and has shifted again:
  - `buildModel()` — `policy-router-builder.html.tmpl:405-425` (was `:248-268`)
  - `updatePreview()` — `:1020-1044` (was `:840-864`)
  - `renderAll()` — `:1046-1063` (was `:866-883`)
  - `applyModeVisibility()` — `:1065-1081` (was `:885-901`)
  - `applyStateToForm()` — `:1086-1092` (was `:906-912`)
  - `validateBuilderModel()` — `policy_builder_core.mjs:640-655`
  - `_checkIncompleteActions()` — `:551-566`; its only caller is `validateBuilderModel` (`:648`), its only callee is `_diag()` (`:447-449`, `_diag(severity, field, message)` — a plain `{severity, field, message}` object literal)
- Call-chain correction: `applyStateToForm`, `applyModeVisibility`, and `renderAll` do not call each other by name — every call site (bootstrap, mode-switch handler, file-open handler, `#start-blank-btn` handler, `restoreFromSnapshot`) invokes them as separate sequential statements. `renderAll()` calls the mode-specific sub-renderers and, as its last statement, calls `updatePreview()`, which then calls `buildModel()` → `serializeLoopYaml(model)` and `validateBuilderModel(model)`. So the effective order is `applyStateToForm(); applyModeVisibility(); renderAll() → […] → updatePreview() → serializeLoopYaml()/validateBuilderModel()` — a sequence of sibling calls at each call site, not a function-invokes-function chain.
- Confirms the "emitted YAML unchanged" claim doubly: `buildModel()`'s outcome projection is a fixed 5-key literal (`name, actionType, body, args, transition`, tmpl `:417-423`) that already drops any other key — a `verificationContract` key would never reach `model.outcomes[i]`. And even if it did, `_serializeIssueLifecycle` (`policy_builder_core.mjs:1538-1608`) and `_outcomeStateLines` (`:1239-1272`) read only those same five keys — never `verificationContract`.
- `LIFECYCLE_VERBS` (`policy_builder_core.mjs:108-144`): the `implement` verb is `{name: "implement", actionType: "shell", ...}`; the file's own comment at `:105-107` calls it out as "the one `shell` verb" — direct textual confirmation that `_checkIncompleteActions` not covering `at === "shell"` leaves exactly this verb's empty-body case unchecked today.
- Precedent for "field present on the model, excluded from serialization" (supports the `verificationContract` design): `FSMConfig.imports` (`scripts/little_loops/fsm/schema.py`) is populated by `from_dict()` but simply never referenced by `to_dict()`'s hand-built result dict — no explicit strip step, just omission. `policy_builder_core.mjs`'s serializers (`_serializeIssueLifecycle`/`_serializeDecisionTable`/etc.) are built the same way, as an ordered list of `out.push(...)` lines reading specific fields — a field no `out.push` line reads is already the established shape for "authoring-only metadata."
- The `TaskPreset {id, label, description, mode, build}` shape this section proposes does not match either existing "preset" convention in the codebase: `seedExample()`/`blankModel()` (`policy_builder_core.mjs`) are bare constructor functions with no wrapping metadata, and `PRESET_EXPANSIONS` (`scripts/little_loops/cli/loop/diagram_modes.py:58`) is a static `dict[name] -> pre-built object`, not a function. Neither is a precedent conflict to resolve — noting it so the implementer knows `TaskPreset` is establishing a new shape, not following one.

## Acceptance Criteria

- [ ] Lifecycle hides grading-only inputs; rules precede advanced action editors, which are collapsed by default.

- [ ] Each configured task preset emits YAML passing `ll-loop validate` (fixture pairs and Node gate). Implementation-with-verification initially requires its command; that unfinished draft saves/opens correctly and blocks YAML export because an empty `shell` body is now an `error` diagnostic (node:test covers the new `shell` case alongside the existing `prompt`/`slash_command` ones). A configured fixture uses a harmless test command accepting an issue ID.

- [ ] `verificationContract` survives `buildModel()` and Save/Open; `summarizeTransitions(buildModel())` reports `"acceptance"` only when the reachable verify outcome is a non-empty `shell` action carrying the contract, and `"unconfigured"` when the body is empty. Editing `body`/`args` preserves the contract (node:test: preset → set body → summary is `"acceptance"`); changing `actionType` off `shell` clears it (summary becomes `"issue_validation"`/`"custom"` per the new action). Emitted YAML is byte-identical with or without the key, and the preset's emitted `verify` state carries `on_error: failed`.

- [ ] Applying a preset whose mode differs from the active mode switches mode, replaces only that mode's draft, and pushes exactly one history entry; one undo restores the previous `activeMode` and that mode's prior draft (node:test via `applyDraftEdit` snapshots, following `policy_validator.test.mjs:779-864`).

- [ ] The advanced `<details>` opens automatically when an `outcomes`/`maxSteps` error diagnostic is present, and is never auto-closed.

- [ ] Summary reflects reachable transitions and the current verification contract, distinguishes state steps from attempts, and never labels `/ll:verify-issues` or an arbitrary state named `verify` as acceptance verification. Tests cover custom bindings, unreachable checks, branching/cycles, and invalidated contract metadata.

- [ ] Generated implementation-with-verification loops run through the real executor with harmless stub commands: verify exit 0 reaches `done`; nonzero reaches `failed` with `failure_terminal == true`; implementation failure never runs verification. No real implementation or LLM runs occur.

- [ ] Skill descriptions and argument hints are displayed; `_load_skill_catalog` stamps `args_hint` from `HelpEntry.argument_hint`, and `test_policy_builder_emit.py` regexes `window\.__SKILL_CATALOG__\s*=\s*(\[.*?\]);` out of the rendered HTML (the `/*__SKILL_CATALOG_JSON__*/` token at `policy_builder.py:99` is replaced away at generation time) and asserts every row has the `args_hint` key and a known-hint skill stamps it verbatim.

- [ ] Applying a preset creates one undo entry and persists the draft (ENH-3487 path); it replaces the whole draft wrapper object, so undo after a preset restores the prior wrapper intact (including any sibling keys a later issue adds); other drafts and project identity are unchanged.

- [ ] No page-level horizontal overflow at 375px and desktop widths; controls are keyboard-operable with associated labels. Verified by documented manual browser testing (no DOM test harness in this repo; see ENH-3487 decision).

- [ ] Golden fixture regenerated; existing structural tests pass or are updated with the id renames noted.

## Scope Boundaries

Includes layout, presets, summary, responsive CSS, skill metadata display. Excludes persistence/undo/save-open (ENH-3487, which must land first so presets can use its committed-edit path), new terminal destinations and scoring instructions (ENH-3492), and any change to emitted YAML for existing models. BUG-3486 (`depends_on`) is done.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- ENH-3487 (`depends_on`) has landed: commit `50b3d37a5` ("feat(policy-builder): add draft persistence, undo/redo, and saved projects", 2026-09-17) is on `main`, and `ll-issues show ENH-3487` reports status `Completed` (= `done`). This resolves the unresolved-prerequisite concern recorded in this issue's Confidence Check Notes (Criterion 5 scored 0/20 because `depends_on: [ENH-3487]` was still `open` at that check) — the committed-edit path this issue's presets and undo/persistence integration depend on now exists on `main`.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-16 (batch run with ENH-3487/ENH-3492):_

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so the
issue as it now reads is up to date — this section is a record of what was wrong and fixed,
not an outstanding action item).

- BUG-3486 (this issue's `depends_on`) landed real commits since this issue was captured
  (`22f4ff6ed`, `9f71f86f6` — BUG-3489, a coordinated same-code-area dependency), inserting
  ~66-70 new lines into `policy_builder_core.mjs` and ~15 into
  `policy-router-builder.html.tmpl` ahead of every anchor this issue's Program Design cites.
  Corrected in place: `applyStateToForm` (`858-864`→`868-875`), `applyModeVisibility`
  (`837-853`→`847-862`), `updatePreview` (`809-816`→`808-824`), `serializeLoopYaml`
  (`1049`→`1130`), `seedExample` (`412`→`478`). No claim's *substance* changed — only line
  numbers. `BUILTIN_FRONTMATTER_DIMENSIONS` (`85-95`), `LIFECYCLE_VERBS` (`104-140`),
  `renderLifecycleOutcomes()` (`456-552`), `renderRules()` (`559-675`), `#f-subject`
  (`143-144`), and the `<details>` YAML precedent (`222-225`) all sit before the insertion
  point and remain accurate unchanged.
- `docs/guides/POLICY_ROUTER_GUIDE.md` also shifted: a new "Failure Routing and Clean-Slate
  Scoring" subsection was inserted ahead of "Visual Builder (greenfield)", pushing every
  cited passage down by +60 lines (`198-242`→`258-303`, `232-234`→`292-294`); corrected in
  place.
- Dependency backlink (fixed in this pass): this issue's `depends_on: BUG-3486` had no
  matching entry in `BUG-3486`'s `blocks:` list (the convention used elsewhere in
  `.issues/`). Added `ENH-3491`/`ENH-3492` to `BUG-3486`'s `blocks:`. Separately, `ENH-3492`
  declares `blocked_by: [ENH-3491]` but this issue had no `blocks:` field at all — added
  `blocks: [ENH-3492]`.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query (`ll-issues decisions list --type rule --enforcement required
  --active-only`) returned no entries.
- Proposal-vs-code consequence check (B6): no issue found — the layout/preset/summary work
  reorders existing rendering and adds pure functions; it does not touch the BUG-3489
  reserved-token guard or any other changed code path.

_Third `/ll:verify-issues` pass — 2026-09-17 (batch run with ENH-3487/ENH-3492/FEAT-3488):_

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so
the issue as it now reads is up to date — this section is a record of what was wrong and
fixed, not an outstanding action item).

- Commit `25e39fb1d` (BUG-3490, "resolve installed plugin content root for skill/command
  discovery", 2026-09-17T00:12:13) rewrote `_load_skill_catalog` and shifted
  `cmd_policy_builder` in `policy_builder.py` between the prior verify pass and this one.
  Corrected: `_load_skill_catalog` (`22-56`→`21-58`), `cmd_policy_builder` in the Call Path
  (`61-107`→`61-112`). `HelpEntry.argument_hint` (`cli/help.py:124`) still exists and the
  function still returns only `{name, description}` from the stamped rows — the `args_hint`
  addition plan is unaffected in substance. (BUG-3490 also added a skill-preferred dedup
  step inside `_load_skill_catalog`, keyed on `entry.name`; this issue's plan reads
  `entry.argument_hint` off the same already-deduped `entry` the loop iterates, so the
  dedup change requires no adjustment to the proposal.)
- `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` anchors unaffected — `25e39fb1d`
  did not touch either file; `_checkIncompleteActions` (the empty-body diagnostic this issue
  extends to `shell`) confirmed at `policy_builder_core.mjs:550-564`, condition on `at ===
  "prompt" || at === "slash_command"` only, matching the cited `555-563` range.
- `docs/guides/POLICY_ROUTER_GUIDE.md` "Visual Builder" passage citations (`:305` greenfield
  framing) re-confirmed exact; unaffected by the `25e39fb1d` doc edits (which only touched
  `docs/reference/CLI.md:3757` and `docs/reference/API.md:11912`, both well before this
  issue's cited ranges, with no net line-count change to CLI.md before line 5079).
- Dependency backlinks checked directly: consistent in both directions across
  ENH-3487→ENH-3491→ENH-3492→FEAT-3488; no DEP_ISSUES findings.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query returned no entries.
- Proposal-vs-code consequence check (B6): no new issue found.

## Resolution

Implemented per the Proposed Solution and Program Design (no deviations):

- **core.mjs (`policy_builder_core.mjs`)**: extended `_checkIncompleteActions` to flag
  an empty `shell` body as an error (alongside the existing `prompt`/`slash_command`
  cases). Added `taskPresets()` (the five documented presets, each `build()` returning
  a fresh model — three lifecycle presets share a `_presetLifecycleBase()` helper) and
  `summarizeTransitions(model)` (reachable-verb `steps`, `stopsAfterImplement`,
  `verification` classification, `stepsPerAttempt`/`attempts` from the longest
  reachable goto chain off any dispatch target, `maxStepsNote`). Both exported as
  named exports and via `window.PolicyBuilderCore`.
- **Template**: reordered lifecycle fieldsets to Fields → Rules → Try it → Export,
  moving `#outcomes-fieldset` and the max-steps input into a new collapsed
  `<details id="advanced-details">` that `updatePreview()` force-opens (never
  auto-closes) whenever an `outcomes`/`maxSteps` error diagnostic exists. Wrapped
  `#f-subject` in `#subject-row`, hidden in lifecycle mode via `applyModeVisibility`.
  Added a `#preset-row` ("Start from:" + the five preset buttons + "Start blank")
  and `applyPreset()`, which saves the outgoing draft, switches `#mode-switch` when
  the preset's mode differs, replaces only the target mode's draft wrapper, and
  calls `commit()` once (one history entry either way, per the Preset ↔ mode
  contract). `buildModel()` now projects an outcome's `verificationContract` when
  present. `renderLifecycleOutcomes()` gained: an editable command `<input>` for
  non-`implement` `shell` outcomes, a `verificationContract` checkbox
  (`id="oc-contract-<i>"`) shown only while `actionType === "shell"` and cleared
  whenever the skill `<select>` picks a slash-command skill, and a skill
  description/argument-hint `<small>` (also added to `renderOutcomes()`'s
  slash_command branch and both `<option title>` attributes) via a shared
  `_skillHintFor(body)` helper. Added `@media (max-width: 600px)` collapsing the
  two-column grid to one column. `updatePreview()` renders a
  `#transition-summary` line in lifecycle mode from `summarizeTransitions()`.
- **`policy_builder.py`**: `_load_skill_catalog` now stamps `args_hint` from
  `HelpEntry.argument_hint` on every catalog row (nullable).
- **Fixtures/tests**: 12 new `node:test` cases in `policy_validator.test.mjs`
  covering the shell empty-body diagnostic, preset shape/freshness/validation,
  the unconfigured→configured verification-contract transition, the emitted
  `verify` state's `on_error: failed`, contract clearing on `actionType` change,
  unreachable-verify non-classification, chain-length arithmetic, a goto-cycle
  guard, and branch-reachability. Added `test_skill_catalog_stamps_args_hint`,
  `test_advanced_action_details_collapsed_by_default`, and
  `test_task_preset_buttons_present_grouped_with_start_blank` to
  `test_policy_builder_emit.py`. Added a new configured fixture pair
  (`sample-issue-lifecycle-verification.{model.json,yaml}`, validating cleanly
  with zero `validate_fsm` findings) wired into
  `test_policy_builder_node_gate.py`'s `ll-loop validate` parametrize list, plus
  three `FSMExecutor` end-to-end tests in `TestGeneratedPolicyRouterFailureRouting`
  (acceptance-check success reaches `done`, nonzero exit reaches `failed` via
  `on_error` without misclassifying as `INFRA_RETRY`, and an `implement` failure
  never runs `verify`). Regenerated `golden_policy_router_builder.html`. Updated
  `docs/reference/CLI.md` and `docs/guides/POLICY_ROUTER_GUIDE.md`.

**Manual browser verification (AC "no page-level horizontal overflow... keyboard-operable"):**
this session ran headlessly with no interactive browser available. The concrete,
verifiable proxy landed instead: the `@media (max-width: 600px)` single-column
rule, no new fixed-pixel widths introduced, and every new/changed control
(command input, checkbox, preset buttons) uses the same labeled-input patterns
already covered by `test_persistence_and_history_affordances_present`-style
structural checks. **This is not a substitute for an actual 375px-viewport
manual check** — that still needs a human with a browser before this AC is
considered fully verified; flagging explicitly rather than claiming it was done.

**Pre-existing, unrelated test failures observed in the full suite** (present
before this session's changes; not touched by this issue):
`test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (flags
a span in `P2-BUG-3484-sse-bridge-two-producers-test-crashes-xdist-worker-under-full-suite-cpu-contention.md`,
untouched by this session) and a `pytest-xdist` worker crash on
`test_feat3323_sse_bridge.py::TestSseBridgeFanIn::test_two_producers_reach_one_client_with_distinct_producer_pid`
(passes in isolation with `-n0`; matches that same BUG-3484's documented
worker-crash-under-contention class).

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-17_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- ~~`depends_on: [ENH-3487]` is still `status: open`; Criterion 5 (Dependencies Satisfied) scored 0/20.~~ **Resolved 2026-09-17 (manual review):** ENH-3487 landed as `50b3d37a5` and `ll-issues show` reports both `depends_on` entries (BUG-3486, ENH-3487) as done. The 0/20 dependency score is stale; the aggregate is not re-scored here — rerun `/ll:confidence-check` if a fresh number is wanted.

## Verification (Recheck)

_Added by `/ll:verify-issues` — 2026-09-17 (second pass)_

Verdict: **VALID** (recheck confirms previous corrections remain current; no new changes).

All Program Design anchors verified accurate (buildModel line 405, updatePreview 1020, renderAll 1046, applyModeVisibility 1065, applyStateToForm 1086, validateBuilderModel 640, _checkIncompleteActions 551). Dependencies satisfied: BUG-3486 done with correct blocks entry, ENH-3487 done, ENH-3492 has correct blocked_by entry. No code changes to policy-builder files since last verify pass (2026-09-17T14:52:55). Evidence verification clean (0 findings). Decision rules query returned no conflicts. Proposal soundness check passed.

## Session Log
- `/ll:manage-issue` - 2026-09-17T18:19:39 - `ee3ca2cb-58cc-40fc-839a-9295dd1b7ed5.jsonl`
- `/ll:ready-issue` - 2026-09-17T17:49:55 - `61a65e26-3231-44fc-82ed-feccd03666e2.jsonl`
- `/ll:confidence-check` - 2026-09-17T15:23:30 - `edd8d3ee-219a-4f19-b572-8600a38aa1cc.jsonl`
- `/ll:verify-issues` - 2026-09-17T15:08:39 - `defa41b0-42f9-4a0d-aaa2-260632de068b.jsonl`
- manual review - 2026-09-17 - fixed contract-invalidation rule (body edits no longer clear `verificationContract`; checkbox UI defined); added cross-mode preset contract; replaced scenario-clearing clause with the draft-wrapper replacement rule; documented the `on_error: failed` + executor nonzero-exit mechanism and stub pitfalls; specified `maxStepsNote` arithmetic and advanced-`<details>` auto-open; rewrote superseded AC; marked confidence-check dependency concern resolved
- `/ll:wire-issue` - 2026-09-17T14:52:55 - `d32b8878-c913-4d69-aa9c-3c71bc1fa530.jsonl`
- `/ll:refine-issue` - 2026-09-17T14:34:09 - `9d2644bd-122c-4727-b4a0-65456e38a722.jsonl`
- `/ll:confidence-check` - 2026-09-17T06:35:15 - `27f66a27-b6ed-470d-a90f-1d2b427f8b5c.jsonl`
- `/ll:verify-issues` - 2026-09-17T06:27:55 - `9b9f3eca-ed5d-4fd7-a99d-217cb278def3.jsonl`
- manual review - 2026-09-17 - empty-body diagnostic must be extended to `shell` (was assumed to exist); `verificationContract` must be projected by `buildModel()`; `args_hint` comes from `HelpEntry.argument_hint`, not `tool_catalog`; Current Behavior anchors corrected
- manual review - 2026-09-17 - defined acceptance-check command/input/exit-code contract, unfinished-preset behavior, action-aware summaries, and atomic model/scenario replacement undo
- manual review - 2026-09-17 - `args_hint` missing from stamped catalog (policy_builder.py now touched); presets route through ENH-3487's edit path (ENH-3487 promoted to depends_on); anchors corrected post-8faffee5a
- `/ll:verify-issues` - 2026-09-17T02:36:59 - `ed6d999b-26a2-4d77-bbbf-604f7482188a.jsonl`
- `/ll:verify-issues` - 2026-09-17T01:18:50 - `716b78b0-d53f-401a-997f-791cc3ac58be.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-16T23:13:05 - `e4d4d311-3a45-427a-958f-7960765e8da2.jsonl`
