---
id: ENH-3491
parent: EPIC-3493
epic: EPIC-3493
type: ENH
title: Policy builder lifecycle layout, task presets, and execution summary
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
relates_to:
- ENH-3487
- ENH-3492
- FEAT-3474
---

# ENH-3491: Policy builder lifecycle layout, task presets, and execution summary

## Summary

Reorganize the policy builder's lifecycle authoring flow so users edit fields and rules before advanced action settings, pick a task preset, and see an accurate execution summary. Split out of ENH-3487 (workstream b: layout and interaction); no change to emitted YAML.

## Current Behavior

The lifecycle page presents nine built-in fields (`BUILTIN_FRONTMATTER_DIMENSIONS`, `scripts/little_loops/templates/policy_builder_core.mjs:85-95`) and five action editors (one generic `renderLifecycleOutcomes()` loop over `LIFECYCLE_VERBS`, `scripts/little_loops/templates/policy-router-builder.html.tmpl:456-552`) before its rules. The grading-subject input (`#f-subject`, tmpl `:143-144`) is shown in lifecycle mode but never read by `_serializeIssueLifecycle()`. The verb list is described like a pipeline even though implementation stops by default. Max steps counts FSM state executions, not whole attempts, and nothing explains that. The two-column CSS grid (tmpl `:32`) has no `@media` breakpoint; no authored template in `scripts/little_loops/templates/` has one. Skill descriptions are collected but not displayed. The only collapsible precedent is the `<details>` around raw YAML (tmpl `:222-225`); fieldsets are toggled only per mode via `applyModeVisibility` (`:837-853`).

## Expected Behavior

Lifecycle authoring is organized as Fields, Rules, Try it, Export. Action bindings and budgets sit under an advanced-settings `<details>`. Task presets (document improvement, condition-based routing, preparation, implementation, implementation with verification) seed the form. Mode-irrelevant inputs are hidden. A summary shows the actual transitions of the current model, distinguishes state steps from attempts, and says whether implementation is followed by verification. Skill descriptions and argument hints are shown. The layout has no page-level horizontal overflow at 375px and desktop widths; all controls are keyboard-operable with associated labels.

## Proposed Solution

- Reorder fieldsets in the template and wrap action editors and budget inputs in a `<details>` advanced section; keep the existing `renderLifecycleOutcomes()` loop and `renderRules()` unchanged.
- Add task presets as new `seedExample`-style constructors in `policy_builder_core.mjs` (pure, unit-tested with `node:test`); presets must distinguish issue validation (verify-issues) from acceptance verification and declare the latter's command/result contract.
- Hide `#f-subject` in lifecycle mode via `applyModeVisibility`.
- Render a transition summary from the model (pure function in core.mjs, unit-tested) next to the YAML preview.
- Add `@media (max-width: 600px)` collapsing the grid to one column.
- Show `catalog` skill descriptions/argument hints in the action editor.

## Integration Map

- Files to modify: `scripts/little_loops/templates/policy-router-builder.html.tmpl`; `scripts/little_loops/templates/policy_builder_core.mjs`.
- Tests at risk: `scripts/tests/test_policy_builder_emit.py::TestFeat2301UsabilityStructural` (`test_seed_and_blank_wiring_present`, `test_rubric_mode_has_no_dt_only_affordances`, `test_yaml_is_collapsed_behind_details`) depend on the `start-blank-btn`, `rules-fieldset`/`outcomes-fieldset`/`tryit-fieldset`, `yaml-details`/`yaml-preview`/`yaml-summary` ids; keep the ids or update the tests. `test_theme_resolution_order_is_stored_stamped_os_light` must keep passing.
- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` (byte-identical golden test in `test_enh3035_artifact_template_kit.py`).
- Docs: `docs/guides/POLICY_ROUTER_GUIDE.md:198-242` ("Visual Builder") `:232-234` YAML-behind-details framing goes stale with a dedicated Export section.

## Impact

- **Priority**: P3 - usability of repeat authoring; no correctness impact
- **Effort**: Medium - template reorder, presets, summary function, CSS
- **Risk**: Low - no emitted-YAML change; structural tests pin element ids
- **Breaking Change**: No

## Program Design

### Types

`TaskPreset {id, label, description, mode, build: () -> Model}` in `policy_builder_core.mjs`. `TransitionSummary {steps: string[], stopsAfterImplement: boolean, verifiesAfterImplement: boolean, maxStepsNote: string}`.

### Signatures

- `taskPresets() -> TaskPreset[]` — pure; each `build()` returns a model shaped like `seedExample(mode)` output.
- `summarizeTransitions(model) -> TransitionSummary` — pure; derived from the same outcome/transition data `serializeLoopYaml` consumes.

### Call Path

`applyStateToForm` -> `applyModeVisibility` -> `updatePreview` -> `serializeLoopYaml`, with `summarizeTransitions` called from `updatePreview` and rendered next to the YAML preview. Preset buttons call `applyStateToForm(preset.build())`. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:56-107`) still emits the page unchanged; it only needs the golden fixture regenerated.

Anchors: `applyStateToForm` (`scripts/little_loops/templates/policy-router-builder.html.tmpl:858-864`), `applyModeVisibility` (`:837-853`), `updatePreview` (`:809-816`) live in the template's inline module script; `serializeLoopYaml` (`scripts/little_loops/templates/policy_builder_core.mjs:1049`) is in the pure-JS core; `summarizeTransitions` and `taskPresets` are new exports added to core.mjs next to `seedExample` (`:412`).

## Acceptance Criteria

- [ ] Lifecycle hides grading-only inputs; rules precede advanced action editors, which are collapsed by default.
- [ ] Each task preset seeds a model whose `serializeLoopYaml` output validates via `ll-loop validate` (fixture pair + parametrize entry in `test_policy_builder_node_gate.py`).
- [ ] Summary reflects actual transitions of the current model, distinguishes state steps from attempts, and states whether verification follows implementation; summary function is unit-tested in `scripts/tests/js/`.
- [ ] Skill descriptions and argument hints are displayed.
- [ ] No page-level horizontal overflow at 375px and desktop widths; controls are keyboard-operable with associated labels. Verified by documented manual browser testing (no DOM test harness in this repo; see ENH-3487 decision).
- [ ] Golden fixture regenerated; existing structural tests pass or are updated with the id renames noted.

## Scope Boundaries

Includes layout, presets, summary, responsive CSS, skill metadata display. Excludes persistence/undo/save-open (ENH-3487), new terminal destinations and scoring instructions (ENH-3492), and any change to emitted YAML for existing models. Coordinate with BUG-3486, which touches the same editing-state code.

## Status

**Open** | Created: 2026-09-16 | Priority: P3
