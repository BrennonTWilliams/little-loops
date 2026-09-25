---
id: FEAT-3586
type: FEAT
title: Brainstorm optional pre-mortem finisher
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3586: Brainstorm optional pre-mortem finisher

## Summary

Add an optional `premortem` finisher (approach D from EPIC-3581): the portfolio
winner (and optionally the runner-up) is attacked by a critic, a defender revises,
and the final report ships each idea with its known risks and kill criteria.

## Current Behavior

Brainstorm ships the tournament winner as-is: no step challenges it, and the report carries no known risks or kill criteria.

## Expected Behavior

- Enabled per profile (`functional`, `business` default on) or via `premortem=true`.
- Critic produces the top failure modes ("it's 12 months later and this failed
  because…"); defender revises the idea or concedes; a bounded number of rounds.
- Report gains a `Risks & Kill Criteria` section per finalist; an idea the defender
  concedes is demoted and the next finalist promoted.

## Use Case

**Who**: A little-loops user brainstorming a functional design or business opportunity whose winner they may act on.

**Context**: The tournament winner has never been attacked; its weaknesses surface only after work starts.

**Goal**: Have the top idea critiqued and defended before it ships in the report.

**Outcome**: Each finalist appears with a `Risks & Kill Criteria` section; a conceded idea is demoted and the next finalist promoted.

## Motivation

EPIC-3581 approach D adds an adversarial pre-mortem to reduce false confidence in the winner. Shipping risks and kill criteria alongside each idea makes the report actionable, and demoting conceded ideas keeps weak winners from surfacing.

## Proposed Solution

Add an optional `premortem` finisher to `scripts/little_loops/loops/brainstorm.yaml`, after `tournament`/`portfolio` selection:

- Enabled by profile (`functional`, `business` default on) or `premortem=true`.
- A critic states the top failure modes ("it's 12 months later and this failed because…"); a defender revises or concedes.
- Rounds are bounded by a context value and enforced by the FSM with a per-run counter kept under `${captured.run_dir.output}` (not the shared-scratch `retry_counter` fragment).
- The report gains a `Risks & Kill Criteria` section per finalist; a conceded idea is demoted, the next finalist promoted, and the change recorded in `ideas.jsonl`.

## Program Design

### Types

- `Risk`: `{failure_mode: str, kill_criterion: str}`
- `PremortemVerdict`: `{idea_id: str, conceded: bool, risks: [Risk]}`

### Signatures

- `critique(idea: IdeaRecord) -> list[Risk]` — critic LLM state
- `defend(idea: IdeaRecord, risks: list[Risk]) -> PremortemVerdict` — defender revises or concedes
- `apply_verdicts(winners: list[str], verdicts: list[PremortemVerdict]) -> list[str]` — script demotes conceded ideas and promotes the next finalist

### Call Path

`tournament` -> `premortem_critic` -> `premortem_defender` -> `premortem_round_gate` -> `portfolio` -> `verify_artifacts`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Verified anchors: `converge` (state), `route_sink` (state, `classify` evaluator routing `none|file|issue|decision`), `verify_artifacts` (asserts non-empty `brainstorm.md`), `retry_counter` (`lib/common.yaml` fragment). `tournament` and `portfolio` do not yet exist in `brainstorm.yaml` — FEAT-3582 dependency.
- Decision Rules: skip route — `premortem` false (resolved from profile or explicit `premortem=true`) must route straight past the finisher with `brainstorm.md`/`winners.md` byte-identical to the no-finisher output. Round bound: the counter must increment per round and route out at `premortem_rounds`; a still-unconceded idea at the bound ships with its risks (not demoted). Concede = defender verdict `conceded: true`; the next finalist is promoted only if one remains, otherwise the demoted idea ships flagged.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `premortem_critic`, `premortem_defender`, and demote/promote script; extend report rendering

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` `retry_counter` / `convergence_gate` — bounded-round counters

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: round bound enforced by the FSM, demotion/promotion recorded in `ideas.jsonl`, clean skip when disabled

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context keys: `premortem` (bool, resolved from profile) and `premortem_rounds`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Loop shape today**: `scripts/little_loops/loops/brainstorm.yaml` has no `tournament`/`portfolio`/`premortem` states yet (states: `init … rank → converge → route_sink → verify_artifacts → finalize_done`). The Call Path in `## Program Design` names states that only exist once FEAT-3582 lands (already in `blocked_by`); the finisher's insertion point is between `converge` and `route_sink`, since `converge` writes `brainstorm.md` and `winners.md` and `route_sink` fans out to the sinks.
- **Winners live in `winners.md`, not `ideas.jsonl`**: `converge` writes `${captured.run_dir.output}/winners.md` (JSON lines, same schema as `ideas.jsonl`); sinks consume it. "Reflected in `winners`" therefore means rewriting `winners.md` (and any `winners` structure FEAT-3582 introduces); the `ideas.jsonl` record of demotion/promotion is an additional append-only trail, not a replacement.
- **`retry_counter` scope constraint**: `lib/common.yaml` `retry_counter` writes its counter to `.loops/tmp/${param.counter_key}` — shared scratch outside the run's isolation boundary, and it persists across runs (a stale file from a prior run would pre-exhaust the bound). `mechanize-skills.yaml` `diagnosis_retry` documents this (MR-3) and hand-rolls a counter under `${captured.run_dir.output}` with `evaluate: output_numeric / lt`. The Proposed Solution's "use the `retry_counter` fragment" is unsafe as written; the bound must be per-run.
- **Existing test pins**: `scripts/tests/test_brainstorm.py::TestBrainstormYaml::test_max_steps_is_60` pins `max_steps == 60`; adding critic/defender/verdict states with bounded rounds must fit the budget or change the pin deliberately. `test_required_states_exist` and `test_context_has_required_knobs`/`test_context_defaults` enumerate states and context keys, so new `premortem`/`premortem_rounds` keys and states extend those contracts.

### Wiring Additions

_Wiring pass added by `/ll:wire-issue`:_

**Files to Modify**
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entries for `premortem_critic`/`premortem_defender` (interpolate `${context.brief}`) [Agent 3]
- `scripts/tests/data/loop_interpolation_baseline.json` — new counter/apply_verdicts shell sites [Agent 2]

**Tests**
- No existing test executes the hand-rolled counter in `mechanize-skills.yaml` `diagnosis_retry` (only structural tests in `test_builtin_loops.py`, ~lines 13991/14023); write a Pattern-A `_bash` test for the round bound, modeled on `test_brainstorm.py` `test_saturation_counter_increments_on_zero_novel` [Agent 3]
- `scripts/tests/test_builtin_loops.py` — `MR11_MARKER_ALLOWLIST` (exact set; the `# ll-lint: mr11-ok` marker on a counter under `${captured.run_dir.output}` changes it) and `TestValidatorWarningBudget` [Agent 3]

**Configuration**
- Validator: `_validate_zero_retry_counter` flags a counter + `output_numeric lt` with target ≤ 1, so `premortem_rounds` must default to ≥ 2 or the gate be shaped differently [Agent 2]
- Adds ~3 steps per premortem round to the `max_steps: 60` budget tracked in FEAT-3582; `test_max_steps_is_60` pin [Agent 2]

## Implementation Steps

1. Add `premortem_critic` and `premortem_defender` states, gated on the resolved profile (FEAT-3583) or `premortem=true`.
2. Bound rounds with a per-run counter under `${captured.run_dir.output}` (`evaluate: output_numeric / lt`, as `mechanize-skills.yaml` `diagnosis_retry` does) and a `premortem_rounds` context value; do not use the `retry_counter` fragment, whose `.loops/tmp/` counter persists across runs.
3. Implement `apply_verdicts` to demote/promote and record changes in `ideas.jsonl` and `winners`.
4. Render `Risks & Kill Criteria` per finalist in `brainstorm.md`; leave output shape unchanged when disabled.
5. Add tests for bounded rounds, demotion/promotion, and the disabled path; run `ll-loop validate brainstorm`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add critic/defender states to `fence.py` `FENCE_ROLES`
- Set `premortem_rounds` default ≥ 2 to satisfy `_validate_zero_retry_counter`
- Write an executable round-bound test (none exists for `diagnosis_retry`); update `MR11_MARKER_ALLOWLIST` and `loop_interpolation_baseline.json`
- Budget premortem rounds against `max_steps` (see FEAT-3582)

## Impact

- **Priority**: P4 - optional finisher that refines output but is not needed for a working engine
- **Effort**: Small - two LLM states, one per-run bounded counter, and one small script
- **Risk**: Low - off by default for `artifact`/`visual` profiles and skipped cleanly when disabled
- **Breaking Change**: No

## Acceptance Criteria

- Round count is bounded by context and enforced by the FSM (no unbounded debate).
- Demotion/promotion is recorded in `ideas.jsonl` and reflected in `winners`.
- Skipped cleanly when disabled; no change to output shape otherwise.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-09-25T02:07:46 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:43 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:52 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
