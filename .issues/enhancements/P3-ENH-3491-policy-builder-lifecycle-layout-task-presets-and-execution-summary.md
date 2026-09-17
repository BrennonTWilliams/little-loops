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
- ENH-3487
relates_to:
- ENH-3492
- FEAT-3474
blocks:
- ENH-3492
- FEAT-3488
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

- Reorder fieldsets in the template and wrap action editors and budget inputs in a `<details>` advanced section; retain the existing `renderLifecycleOutcomes()` loop and `renderRules()` structure; extend the action editor only for the acceptance-verification contract below.

- Add task presets as pure, unit-tested constructors. The implementation-with-verification preset routes `implement` to `verify`, but replaces the default `/ll:verify-issues` action: that skill validates issue files, not implemented acceptance criteria. The preset uses a user-supplied shell acceptance-check command (a project wrapper/executable accepting the issue ID as its first appended argument, followed by configured args). Exit 0 means acceptance checks passed; nonzero/error routes to `failed` with `failure: true`; success finishes at `done`. Do not treat command dispatch alone as a pass.

- Initially leave that command empty and clearly label the preset as requiring configuration. **Extend the empty-body diagnostic to `shell`** (`policy_builder_core.mjs:555-563` currently covers only `prompt`/`slash_command`) so an unconfigured shell outcome is an `error` that blocks YAML Copy/Download like the other incomplete actions; add a `node:test` case for it. Save/Open of this unfinished preset must work via ENH-3487. Store authoring metadata `verificationContract: "acceptance_exit_code"` on the configured shell outcome; clear it when action type/body/args change unless the user explicitly reaffirms the contract. **Carry it through `buildModel()`**: add `verificationContract` to the outcome projection at tmpl `:259-265` (it is otherwise dropped, see Current Behavior), and have `summarizeTransitions` classify from the built model, never from `state` directly. `serializeLoopYaml` ignores the key, so emitted YAML for existing models is unchanged. It is not a claim that arbitrary shell code has been inspected for correctness.

- Hide `#f-subject` in lifecycle mode via `applyModeVisibility`.

- Render a transition summary from reachable emitted transitions, not outcome names or list order. Distinguish issue-file validation, configured acceptance checks, unconfigured checks, and custom/unknown actions; a state named `verify` is insufficient evidence of acceptance verification. Cover branches, cycles, unreachable verify states, and changed action bindings. ENH-3492 extends this summary with its terminal destinations.

- Add `@media (max-width: 600px)` collapsing the grid to one column.

- Show `catalog` skill descriptions and argument hints in the action editor. **Argument hints are not in the stamped catalog today** (review 2026-09-17): `_load_skill_catalog` (`scripts/little_loops/cli/artifact/policy_builder.py:21-58`) projects only `{name, description}` out of the `HelpEntry` rows it already gets from `cli/help.py::collect_entries` — and `HelpEntry` already carries `argument_hint: str | None` (`cli/help.py:124`), parsed from `args`/`argument-hint` frontmatter. So no new parser is needed: carry `entry.argument_hint` through as a nullable `args_hint` key on each stamped row. This is the one `policy_builder.py` change in this issue; `test_policy_builder_emit.py` asserts every stamped row has the `args_hint` key and that a skill with a known hint stamps it verbatim. (`little_loops.tool_catalog` parses the same field independently for the MCP tool list; do not add a second catalog source.)

- Preset buttons go through ENH-3487's committed-edit path (push a history entry, persist the draft), exactly like "Start blank" — never a bare `applyStateToForm` that bypasses undo/persistence. Preset/start-blank replacement clears scenarios only in the replaced draft (if present); the UI states that effect and one undo restores the prior model and scenarios together. Other drafts and project identity are preserved. No scenario UI is added here; FEAT-3488 wires its controls to this contract.

## Integration Map

- Files to modify: `scripts/little_loops/templates/policy-router-builder.html.tmpl`; `scripts/little_loops/templates/policy_builder_core.mjs`; `scripts/little_loops/cli/artifact/policy_builder.py` (`_load_skill_catalog` gains `args_hint` only).

- Tests at risk: `scripts/tests/test_policy_builder_emit.py::TestFeat2301UsabilityStructural` (`test_seed_and_blank_wiring_present`, `test_rubric_mode_has_no_dt_only_affordances`, `test_yaml_is_collapsed_behind_details`) depend on the `start-blank-btn`, `rules-fieldset`/`outcomes-fieldset`/`tryit-fieldset`, `yaml-details`/`yaml-preview`/`yaml-summary` ids; keep the ids or update the tests. `test_theme_resolution_order_is_stored_stamped_os_light` must keep passing.

- Add configured verification fixtures to `test_policy_builder_node_gate.py` and stub-command execution cases to `test_fsm_executor.py`; preserve all existing-model YAML goldens.

- Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` (byte-identical golden test in `test_enh3035_artifact_template_kit.py`).

- Docs: `docs/guides/POLICY_ROUTER_GUIDE.md:258-303` ("Visual Builder") `:292-294` YAML-behind-details framing goes stale with a dedicated Export section. (Re-verified `/ll:verify-issues` 2026-09-16: a new "Failure Routing and Clean-Slate Scoring" subsection inserted earlier in the doc shifted this section by +60 lines from its originally-cited location.)

## Impact

- **Priority**: P3 - usability of repeat authoring; no correctness impact

- **Effort**: Medium - template reorder, presets, summary function, CSS

- **Risk**: Low - no emitted-YAML change; structural tests pin element ids

- **Breaking Change**: No

## Program Design

### Types

`TaskPreset {id, label, description, mode, build: () -> Model}` in `policy_builder_core.mjs`. `TransitionSummary {steps: string[], stopsAfterImplement: boolean, verification: "acceptance" | "issue_validation" | "unconfigured" | "custom" | "none", maxStepsNote: string}`. Outcome entries gain an optional `verificationContract?: "acceptance_exit_code"` key, which `buildModel()` must project (tmpl `:259-265`) and `serializeLoopYaml` ignores; summaries classify the current reachable action and contract, not merely its name.

### Signatures

- `taskPresets() -> TaskPreset[]` — pure; each `build()` returns a model shaped like `seedExample(mode)` output.

- `summarizeTransitions(model) -> TransitionSummary` — pure; derived from the same outcome/transition data `serializeLoopYaml` consumes.

### Call Path

`applyStateToForm` -> `applyModeVisibility` -> `updatePreview` -> `serializeLoopYaml`, with `summarizeTransitions` called from `updatePreview` and rendered next to the YAML preview. Preset buttons apply `preset.build()` through ENH-3487's committed-edit path (`applyDraftEdit` + persist), then `applyStateToForm`. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:61-112`) changes only in `_load_skill_catalog` (`args_hint`); the golden fixture is regenerated.

Anchors (re-verified in review 2026-09-17 after commit `8faffee5a`, which shifted every core.mjs/template anchor): `applyStateToForm` (`scripts/little_loops/templates/policy-router-builder.html.tmpl:906-912`), `applyModeVisibility` (`:885-901`), `updatePreview` (`:840-864`), `renderAll` (`:866-883`), `renderLifecycleOutcomes()` (`:453`), `renderRules()` (`:556`), `#f-subject` (`:144`), YAML `<details>` (`:222`), grid (`:32`) live in the template; `serializeLoopYaml` (`scripts/little_loops/templates/policy_builder_core.mjs:1448`), `seedExample` (`:782`), `blankModel` (`:857`), `LIFECYCLE_VERBS` (`:108-144`), `BUILTIN_FRONTMATTER_DIMENSIONS` (`:89`), `_emittedVerbs` (`:1336`) are in the pure-JS core; `summarizeTransitions` and `taskPresets` are new exports added next to `seedExample`. The transition is expressible with `implement.transition = {kind: "goto", target: "verify"}` (`_emittedVerbs` follows goto chains), but the default verify action must be replaced with the explicit acceptance-check contract above.

## Acceptance Criteria

- [ ] Lifecycle hides grading-only inputs; rules precede advanced action editors, which are collapsed by default.

- [ ] Each configured task preset emits YAML passing `ll-loop validate` (fixture pairs and Node gate). Implementation-with-verification initially requires its command; that unfinished draft saves/opens correctly and blocks YAML export because an empty `shell` body is now an `error` diagnostic (node:test covers the new `shell` case alongside the existing `prompt`/`slash_command` ones). A configured fixture uses a harmless test command accepting an issue ID.

- [ ] `verificationContract` survives `buildModel()` and Save/Open; `summarizeTransitions(buildModel())` reports `"acceptance"` only when the reachable verify outcome is a non-empty `shell` action carrying the contract, and `"unconfigured"` when the body is empty. Emitted YAML is byte-identical with or without the key.

- [ ] Summary reflects reachable transitions and the current verification contract, distinguishes state steps from attempts, and never labels `/ll:verify-issues` or an arbitrary state named `verify` as acceptance verification. Tests cover custom bindings, unreachable checks, branching/cycles, and invalidated contract metadata.

- [ ] Generated implementation-with-verification loops run through the real executor with harmless stub commands: verify exit 0 reaches `done`; nonzero reaches `failed` with `failure_terminal == true`; implementation failure never runs verification. No real implementation or LLM runs occur.

- [ ] Skill descriptions and argument hints are displayed; `_load_skill_catalog` stamps `args_hint` from `HelpEntry.argument_hint` and `test_policy_builder_emit.py` asserts its presence in `__SKILL_CATALOG_JSON__`.

- [ ] Applying a preset creates one undo entry and persists the draft (ENH-3487 path); undo after a preset restores the prior model and any scenarios; other drafts and project identity are unchanged.

- [ ] No page-level horizontal overflow at 375px and desktop widths; controls are keyboard-operable with associated labels. Verified by documented manual browser testing (no DOM test harness in this repo; see ENH-3487 decision).

- [ ] Golden fixture regenerated; existing structural tests pass or are updated with the id renames noted.

## Scope Boundaries

Includes layout, presets, summary, responsive CSS, skill metadata display. Excludes persistence/undo/save-open (ENH-3487, which must land first so presets can use its committed-edit path), new terminal destinations and scoring instructions (ENH-3492), and any change to emitted YAML for existing models. BUG-3486 (`depends_on`) is done.

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

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-09-17T06:27:55 - `9b9f3eca-ed5d-4fd7-a99d-217cb278def3.jsonl`
- manual review - 2026-09-17 - empty-body diagnostic must be extended to `shell` (was assumed to exist); `verificationContract` must be projected by `buildModel()`; `args_hint` comes from `HelpEntry.argument_hint`, not `tool_catalog`; Current Behavior anchors corrected
- manual review - 2026-09-17 - defined acceptance-check command/input/exit-code contract, unfinished-preset behavior, action-aware summaries, and atomic model/scenario replacement undo
- manual review - 2026-09-17 - `args_hint` missing from stamped catalog (policy_builder.py now touched); presets route through ENH-3487's edit path (ENH-3487 promoted to depends_on); anchors corrected post-8faffee5a
- `/ll:verify-issues` - 2026-09-17T02:36:59 - `ed6d999b-26a2-4d77-bbbf-604f7482188a.jsonl`
- `/ll:verify-issues` - 2026-09-17T01:18:50 - `716b78b0-d53f-401a-997f-791cc3ac58be.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-16T23:13:05 - `e4d4d311-3a45-427a-958f-7960765e8da2.jsonl`
