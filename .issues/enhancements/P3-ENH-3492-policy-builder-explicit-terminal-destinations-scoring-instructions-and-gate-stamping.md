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
decision_needed: true
depends_on:
- BUG-3486
relates_to:
- ENH-3487
- ENH-3491
- BUG-3489
- FEAT-3474
blocked_by:
- ENH-3491
---

# ENH-3492: Policy builder explicit terminal destinations, scoring instructions, and gate stamping

## Summary

Add explicit stop-success, skip, and needs-attention terminal destinations to lifecycle policies, optional per-dimension scoring instructions and score anchors, and stamp the project's confidence-gate thresholds into the builder. Split out of ENH-3487 (workstream c: emitted-YAML semantics). Needs a design decision before implementation.

## Current Behavior

The builder emits a binary terminal model, differing by mode:
- `issue_lifecycle` (`_serializeIssueLifecycle`, `scripts/little_loops/templates/policy_builder_core.mjs:974-1041`) hardcodes `on_max_steps: failed` (`:1002`), every verb state carries `on_error: failed` (`:1031`), and only `done`/`failed` terminals are emitted (`:1034-1039`).
- `decision_table` (`_serializeDecisionTable`, `:741-833`) emits no `on_max_steps`.
- `rubric` (`_serializeRubric`, `:834-909`) has a single `done` terminal and no `on_max_steps`.
No `stop-success`, `skip`, or `needs-attention` concept exists anywhere in the builder. Rubric dimensions have no score definitions. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:56-107`) stamps only theme, CSS vars, grammar spec, and catalog; lifecycle defaults hardcode a confidence threshold. `ConfidenceGateConfig` (`scripts/little_loops/config/automation.py:155-170`) is unread by this command.

## Expected Behavior

Lifecycle rules can route to stop-success, skip, and needs-attention destinations, each emitting a valid loop. Reopening existing five-verb models preserves their behavior byte-for-byte. Dimensions accept optional scoring instructions and score anchors that appear in emitted prompts. The builder displays the project's configured readiness/outcome thresholds alongside rule thresholds.

## Proposed Solution

Decision required first (`decision_needed: true`; run `/ll:decide-issue ENH-3492`):
1. Is `stop-success` an alias for the existing `done` terminal, or a distinct terminal state with its own name? Recommendation: distinct terminal `stopped` with `terminal: true`, so postmortems can tell "finished the pipeline" from "rule said stop here".
2. Which routes to `skip` vs `needs-attention` vs `failed`: recommendation — `skip` and `needs-attention` are rule-selectable destinations only (never automatic); `on_error` stays `failed`; `on_max_steps` becomes `needs-attention` for lifecycle.
3. Should `decision_table` and `rubric` gain `on_max_steps`/`on_error`? Recommendation: yes for `on_max_steps` → `needs-attention`, unchanged otherwise; existing golden fixtures must stay byte-equal, so this needs a model flag defaulting off for pre-existing models.

Then:
- Extend `LIFECYCLE_VERBS`/outcome transition kinds in core.mjs with the new destinations; `_outcomeStateLines`/`_doneStateName` (`:687-739`) route to them. Backward-compatible defaults for models lacking the new fields.
- Add optional `instructions`/`anchors` to dimension entries; `serializeFrontmatterDimensions` (`:925`) emits them into prompts. Touch `scripts/little_loops/fsm/frontmatter_scores.py` (`encode_frontmatter_scores` mirrors `normalizeDimName` rules) only if `BUILTIN_FRONTMATTER_DIMENSIONS` shape changes, and extend `conformance_corpus.json` accordingly.
- In `cmd_policy_builder` read `config.commands.confidence_gate` off the already-built `BRConfig` (mirror `scripts/little_loops/fsm/context_seed.py:68`; do not copy `cli/issues/check_readiness.py:78-115`'s raw-JSON bypass) and stamp `readiness_threshold`/`outcome_threshold`. No `config-schema.json` change needed (`confidence_gate` defined at `:509`).

## Integration Map

- Files: `policy_builder_core.mjs`, `policy-router-builder.html.tmpl`, `cli/artifact/policy_builder.py`, possibly `fsm/frontmatter_scores.py`.
- Tests: new `.model.json`/`.yaml` fixture pairs under `scripts/tests/fixtures/policy_builder/` for each new destination plus parametrize entries in `test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode` (arbitrary terminal names are schema-legal per `fsm/validation/structural_rules.py:26-35`); `scripts/tests/js/policy_validator.test.mjs`; `test_policy_builder_corpus.py`; regenerate the golden HTML fixture.
- Docs: `docs/reference/CLI.md:5079-5095` prose at `:5081` (five fixed verbs); `docs/guides/POLICY_ROUTER_GUIDE.md:227-229,290-291` ("can't be deleted and no new outcome can be added") and `:295-301` (Verb Table needs a destination column).

## Impact

- **Priority**: P3 - richer lifecycle semantics; blocked on a design decision
- **Effort**: Medium - new transition kinds, dimension metadata, config stamping
- **Risk**: Medium - changes emitted YAML; existing fixtures must stay byte-identical
- **Breaking Change**: No

## Program Design

### Types

Outcome `transition.kind` gains `"stop" | "skip" | "attention"` alongside existing `"finish"`/verb targets. Dimension entries gain optional `instructions: string` and `anchors: {score: number, meaning: string}[]`. Stamped `__CONFIDENCE_GATE__ {readiness_threshold, outcome_threshold}` in the template.

### Signatures

- `_outcomeStateLines(model) -> string[]` — extended to emit `stopped`, `skipped`, `needs_attention` terminals (exact names per the decision above)
- `_doneStateName(model) -> string` — unchanged for `finish`; returns the new terminal for `stop`
- `serializeFrontmatterDimensions(model) -> string` — emits `instructions`/`anchors` into the grading prompt when present
- `cmd_policy_builder(args, logger) -> int` — reads `config.commands.confidence_gate` and stamps it

### Call Path

`serializeLoopYaml` -> `_serializeIssueLifecycle` -> `_outcomeStateLines` -> terminal-state emission. `cmd_policy_builder` -> `BRConfig` -> template stamping; the builder displays thresholds beside rule thresholds.

## Acceptance Criteria

- [ ] Decision questions 1-3 resolved and recorded in this issue before implementation.
- [ ] Stop-success, skip, and needs-attention destinations each emit YAML that passes `ll-loop validate`, covered by fixture pairs in the Node gate.
- [ ] Existing `.model.json` fixtures serialize byte-identically (no behavior change for five-verb models).
- [ ] Optional scoring instructions and anchors appear in emitted prompts and survive `serializeLoopYaml` round trips; unit-tested in `node:test`.
- [ ] Builder displays stamped readiness/outcome thresholds; `test_policy_builder_emit.py` asserts they are read from `BRConfig`.
- [ ] CLI.md and POLICY_ROUTER_GUIDE.md passages listed above are updated.

## Scope Boundaries

Includes destination semantics, scoring metadata, gate stamping, and their docs. Excludes persistence (ENH-3487), layout/presets (ENH-3491), runtime policy-router fixes (see the related runtime issue in frontmatter). If the chosen semantics change how the runtime treats terminal outcomes, promote that related issue to `depends_on`.

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-16T23:13:05 - `e4d4d311-3a45-427a-958f-7960765e8da2.jsonl`
