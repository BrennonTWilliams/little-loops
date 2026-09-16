---
id: ENH-3487
type: ENH
title: Policy builder persistence and clearer interaction
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T20:54:20Z'
labels:
- policy-builder
- captured
depends_on:
- BUG-3486
relates_to:
- FEAT-3474
---

# ENH-3487: Policy builder persistence and clearer interaction

## Summary

Improve policy-builder persistence and interaction so users can safely maintain a policy over multiple sessions and understand what their loop will do. Preserve the self-contained offline HTML experience while adding versioned saved projects, per-mode drafts, undo/redo, and a task-oriented authoring flow.

Captured from the 2026-09-16 review following FEAT-3474, as the second of three requested workstreams.

## Current Behavior

The page holds authoring state only in memory; localStorage stores the theme. Mode changes replace all work with a seed, and refresh loses edits. Only YAML is exported, with no builder-project reopening. The lifecycle page presents nine built-in fields and five verbose action editors before its rules, retains an irrelevant grading-subject input, and describes available verbs like a pipeline even though implementation stops by default. Max steps counts FSM state executions, not whole attempts. The two-column CSS lacks responsive breakpoints; Copy has no success/failure feedback.

Rubric dimensions have no score definitions, skill descriptions are collected but not displayed, and lifecycle defaults hardcode a confidence threshold rather than exposing the project's implementation gate. The verify verb checks issue-file accuracy via verify-issues; it is not inherently an acceptance-test runner.

## Expected Behavior

Edits survive reload and mode exploration. Users can save/reopen a portable versioned project, undo changes, choose a task preset, edit fields/rules before advanced action settings, and inspect an accurate execution summary. Offline authoring remains usable without a server or browser storage permission.

## Motivation

Prevent accidental loss of authoring work and make the builder useful for ongoing policy maintenance. Users should understand stopping, repetition, verification, and export without learning internal state names or inspecting generated YAML.

## Proposed Solution

- Persist independent per-mode drafts with versioned project export/import and undo/redo. Validate imports before replacing a draft; report storage failures and keep explicit file saving available.
- Reorganize lifecycle authoring as Fields, Rules, Try it, and Export; collapse action bindings and budgets under advanced settings. Present task presets for document improvement, condition-based routing, preparation, implementation, and implementation with verification.
- Use friendly type labels and field explanations while retaining exact frontmatter keys. Hide mode-irrelevant inputs and show an accurate graph/summary of the current transitions.
- Add explicit stop-success, skip, and needs-attention destinations for lifecycle policies. Preserve existing five-verb projects when reopening; new presets must distinguish issue validation from acceptance verification and declare the latter's configured command/result contract.
- Show skill descriptions/argument hints, add optional dimension scoring instructions and score anchors, and expose the stamped project confidence gate alongside rule thresholds. Explain state-step budgets and default transitions.
- Provide responsive layout, associated labels, keyboard-operable controls, live feedback, copy success/failure feedback, and exact save/validate/run instructions with required parameters.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py.
- Dependent files: scripts/little_loops/artifact_template_kit.py for shared shell conventions; scripts/tests/fixtures/policy_builder/ for generated fixtures.
- Similar patterns: existing theme storage fallback, flat JSON-friendly builder model, project-derived stamping.
- Tests: scripts/tests/js/policy_validator.test.mjs, scripts/tests/test_policy_builder_emit.py, scripts/tests/test_policy_builder_node_gate.py; browser workflows for reload, switching, import, undo, responsive layout, and keyboard interaction.
- Configuration: read existing confidence-gate settings; do not add a server requirement.

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| policy-router-builder.html.tmpl | Offline use, three modes, theme toggle, YAML export | Persistent drafts, guided layout, explicit execution semantics | Destructive implicit reseeding on mode change |
| policy_builder_core.mjs | Valid rule semantics and YAML generation | Versioned project serialization, terminal destinations, optional scoring instructions | None |

## Program Design

### Types

Proposed BuilderProject carries schemaVersion, generatorVersion, activeMode, and drafts. DraftHistory carries past, present, and future snapshots.

### Signatures

Proposed new pure JS contracts:
- `serializeBuilderProject(project) -> string`
- `parseBuilderProject(text) -> BuilderProject`
- `applyDraftEdit(history, edit) -> DraftHistory`

### Call Path

`applyStateToForm` -> `applyModeVisibility` -> `updatePreview` -> `serializeLoopYaml`.

`cmd_policy_builder` stamps project metadata and configured confidence-gate settings alongside existing grammar/catalog data. The template restores the active draft before rendering the form.

## Implementation Steps

1. Define and test the versioned project model, import validation, per-mode draft storage, and undo/redo.
2. Reorganize the form with task presets, advanced action settings, and an accurate transition summary.
3. Implement explicit destinations, grading instructions, action metadata, and project gate explanations.
4. Add export/run guidance, accessible feedback, and responsive styling.
5. Exercise offline persistence, round trips, and browser workflows; update fixtures and reference material.

## Impact

- Priority: P3 — improves repeat use and prevents loss of unsaved authoring work.
- Effort: Large — persistence, interaction design, and backwards-compatible model evolution.
- Risk: Medium — migrations and reset behavior must preserve user work.
- Breaking change: No intended incompatibility for existing valid generated loops.

## API/Interface

Add Save project / Open project with a versioned JSON envelope; YAML remains the execution export. Reject unsupported project versions without overwriting current work. Add optional dimension instructions and explicit terminal destination metadata with backward-compatible defaults for existing models. Arbitrary hand-edited YAML import is not included.

## Acceptance Criteria

- [ ] Edits survive reload and round-trip mode switching; undo/redo restores rules, fields, actions, and transitions in automated interaction tests.
- [ ] Save/Open project round-trips all authoring settings and generates equivalent YAML; corrupt/unsupported imports preserve the existing draft and show an error.
- [ ] Disabled/unavailable browser storage leaves authoring and explicit project-file saving functional, with visible save-state feedback.
- [ ] Lifecycle hides grading-only inputs; rules precede advanced action editors; 375px and desktop viewport tests show no page-level horizontal overflow and keyboard-accessible controls.
- [ ] Summaries reflect actual transitions, distinguish state steps from attempts, and clearly indicate whether implementation is followed by verification.
- [ ] Stop-success, skip, and needs-attention destinations emit valid loops; reopening existing five-verb models preserves their behavior.
- [ ] Project gate thresholds and skill descriptions/argument hints are displayed; optional scoring instructions appear in emitted prompts and persist through project round trips.
- [ ] Copy success/failure is visible, and export guidance includes a concrete destination, validation command, and run command with required issue input.

## Success Metrics

Automated round trips lose zero authored fields. Reload and mode changes preserve every tested draft. Every supported mode has tested save/open and keyboard-driven export paths.

## Scope Boundaries

Includes persistent authoring, terminology/layout, action and scoring explanations, lifecycle presets/destinations, and offline export guidance. Excludes arbitrary YAML round-trip editing, named scenario suites, real issue loading through a server, and run submission. Correctness fixes and consumer discovery are a separate workstream; coordinate shared model changes rather than duplicating those fixes.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Architecture | docs/ARCHITECTURE.md | Project context stamping and artifact conventions |
| Reference | docs/reference/CLI.md | Saved artifact generation and usage |
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Authoring flow and lifecycle semantics |

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-16T20:55:13 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
