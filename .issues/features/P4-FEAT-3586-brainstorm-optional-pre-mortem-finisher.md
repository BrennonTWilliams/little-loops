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
- FEAT-3583
reconcile_attempted: true
confidence_score: 80
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3586: Brainstorm optional pre-mortem finisher

## Summary

Add an optional `premortem` finisher (approach D from EPIC-3581): the portfolio
**winner and runner-up** (not the wildcard) are attacked by a critic, a defender responds
with mitigations or concedes, and the final report ships each idea with its known
risks and kill criteria. The idea body itself is never rewritten.

## Current Behavior

Brainstorm ships the tournament winner as-is: no step challenges it, and the report carries no known risks or kill criteria.

## Expected Behavior

- Enabled per profile (`functional`, `business` default on) or via `premortem=true`.
- Critic produces the top failure modes ("it's 12 months later and this failed
  because…"), each tagged `severity: fatal | major | minor`; defender adds a
  mitigation per risk (annotation only — the idea's `title`/`body` are immutable,
  so the shipped idea is the one that was grounded, rendered, and ranked) or
  leaves it `null`; a bounded number of rounds.
- **Concession is script-determined, not the defender's call**: an idea is
  `conceded` when any `fatal` risk still has `mitigation: null` after the defender
  responds. This avoids a same-model defender conceding too rarely or too eagerly.
- Report gains a `Risks & Kill Criteria` section per critiqued finalist; a conceded
  idea is demoted and the next finalist promoted. `apply_verdicts` recomputes the
  runner-up (different cell from the winner) and wildcard per the FEAT-3582 slot
  rules and records `conceded` ids in `portfolio.json`.
- A promoted finalist receives its own critique round, counted against the same
  `premortem_rounds` bound; if the bound is exhausted it ships flagged
  `not_premortemed`.
- Conceded ideas are excluded from `winners.md` and never reach a sink. If every
  finalist concedes, `portfolio.json` has `winner: null` (the only case FEAT-3582
  permits), the report states so, `winners.md` is empty, sinks are skipped, and
  the run still ends `done` (the engine worked; the answer is "none
  of these survive").

## Use Case

**Who**: A little-loops user brainstorming a functional design or business opportunity whose winner they may act on.

**Context**: The tournament winner has never been attacked; its weaknesses surface only after work starts.

**Goal**: Have the top idea critiqued and defended before it ships in the report.

**Outcome**: Each finalist appears with a `Risks & Kill Criteria` section; a conceded idea is demoted and the next finalist promoted.

## Motivation

EPIC-3581 approach D adds an adversarial pre-mortem to reduce false confidence in the winner. Shipping risks and kill criteria alongside each idea makes the report actionable, and demoting conceded ideas keeps weak winners from surfacing.

## Proposed Solution

Add an optional `premortem` finisher to `scripts/little_loops/loops/brainstorm.yaml`, after `portfolio` and before the core's `validate_portfolio` gate:

- Enabled by the resolved profile (`functional`, `business` default on) or an explicit `premortem=true` override.
- A critic states the top failure modes ("it's 12 months later and this failed because…"); a defender attaches a mitigation per risk or concedes. Mitigations are annotations; the idea body is not revised, so no grounding/rendering/ranking needs to be repeated.
- Rounds are bounded by a context value and enforced by the FSM with a per-run counter kept under `${captured.run_dir.output}` (not the shared-scratch `retry_counter` fragment). Promoted finalists consume rounds from the same bound.
- `apply_verdicts` rewrites `portfolio.json` and `winners.md`: conceded ideas are removed from `winners.md` and flagged `conceded` in `portfolio.json`; the next finalist is promoted; changes are appended to `ideas.jsonl`.
- All finalists conceded → empty `winners.md`, sinks skipped, report says so, run ends `done`. `validate_portfolio` treats "all conceded" as a valid outcome, not a floor violation.
- The report gains a `Risks & Kill Criteria` section per finalist.

## Program Design

### Types

- `Risk`: `{failure_mode: str, severity: "fatal" | "major" | "minor", kill_criterion: str, mitigation: str | null}`
- `PremortemVerdict`: `{idea_id: str, conceded: bool, risks: [Risk]}` — `conceded` is computed by `apply_verdicts` (any fatal risk with `mitigation: null`), never accepted from LLM output; no field may carry a revised idea body

### Signatures

- `critique(idea: IdeaRecord) -> list[Risk]` — critic LLM state
- `defend(idea: IdeaRecord, risks: list[Risk]) -> list[Risk]` — defender fills mitigations; returns risks only
- `apply_verdicts(portfolio: dict, verdicts: list[PremortemVerdict], ranking: list[str]) -> dict` — script demotes conceded ideas, promotes the next finalist, flags `not_premortemed` when the bound is exhausted

### Call Path

`portfolio` -> `premortem_critic` -> `premortem_defender` -> `premortem_round_gate` -> `apply_verdicts` -> `validate_portfolio` -> `route_sink`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Verified anchors: `converge` (state), `route_sink` (state, `classify` evaluator routing `none|file|issue|decision`), `verify_artifacts` (asserts non-empty `brainstorm.md`), `retry_counter` (`lib/common.yaml` fragment). `tournament` and `portfolio` do not yet exist in `brainstorm.yaml` — FEAT-3582 dependency.
- Decision Rules: skip route — `premortem` false (resolved from profile or explicit `premortem=true`) must route straight past the finisher with `brainstorm.md`/`winners.md` byte-identical to the no-finisher output. Round bound: the counter must increment per round and route out at `premortem_rounds`; a still-unconceded idea at the bound ships with its risks (not demoted). Concede = defender verdict `conceded: true`; the next finalist is promoted only if one remains. _Superseded 2026-09-25 (Astra review): a conceded idea never ships as a winner — if none remain, `winners.md` is empty and sinks are skipped (see § Expected Behavior)._

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `premortem_critic`, `premortem_defender`, round-gate, and `apply_verdicts` demote/promote script between `portfolio` and `validate_portfolio`; extend report rendering and `validate_portfolio` (all-conceded valid)

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)

### Similar Patterns
- `scripts/little_loops/loops/mechanize-skills.yaml` `diagnosis_retry` — hand-rolled per-run bounded-round counter under `${captured.run_dir.output}` (`output_numeric / lt`); `lib/common.yaml` `retry_counter` is NOT reusable here (shared `.loops/tmp/` counter persists across runs)

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: round bound enforced by the FSM, demotion/promotion recorded in `ideas.jsonl`, clean skip when disabled, promoted finalist critiqued within the bound, all-conceded → empty `winners.md` + no sink, defender output containing a revised body rejected

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context keys: `premortem` (bool, resolved from profile) and `premortem_rounds`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Loop shape today**: `scripts/little_loops/loops/brainstorm.yaml` has no `tournament`/`portfolio`/`premortem` states yet (states: `init … rank → converge → route_sink → verify_artifacts → finalize_done`). The Call Path in `## Program Design` names states that only exist once FEAT-3582 lands (already in `blocked_by`); in the pre-3582 file the insertion point would be between `converge` and `route_sink`; after FEAT-3582 it is between `portfolio` and `validate_portfolio` (see Call Path), so no sink sees a conceded winner.
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

1. Add `premortem_critic` and `premortem_defender` states between `portfolio` and `validate_portfolio` (Blocked by FEAT-3582; the states do not exist until it lands), gated on the resolved profile (FEAT-3583) or `premortem=true`; a false gate routes straight past the finisher. The defender output must be schema-checked to reject any revised idea body.
2. Bound rounds with a per-run counter under `${captured.run_dir.output}` (`evaluate: output_numeric / lt`, as `mechanize-skills.yaml` `diagnosis_retry` does) and a `premortem_rounds` context value; do not use the `retry_counter` fragment, whose `.loops/tmp/` counter persists across runs.
3. Implement `apply_verdicts` to demote conceded ideas (flag `conceded` in `portfolio.json`, remove from `winners.md`), promote the next finalist (critiqued within the same `premortem_rounds` bound, else flagged `not_premortemed`), and append changes to `ideas.jsonl`. If all finalists concede, write an empty `winners.md`, skip sinks, and end `done`; make `validate_portfolio` accept "all conceded".
4. Render `Risks & Kill Criteria` per finalist in `brainstorm.md`; leave output shape unchanged when disabled.
5. Add tests for bounded rounds, demotion/promotion (incl. promoted finalist critiqued within the bound), all-conceded (empty `winners.md`, no sink), rejected revised-body defender output, and the disabled path; run `ll-loop validate brainstorm`.

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

- Round count is bounded by context and enforced by the FSM (no unbounded debate);
  promoted finalists count against the same bound.
- The shipped idea's `title`/`body` are byte-identical to the ranked idea; the
  defender contributes mitigations only.
- Demotion/promotion is recorded in `ideas.jsonl` and reflected in `portfolio.json`
  and `winners.md`.
- A conceded idea never reaches a sink; all-conceded runs end `done` with empty
  `winners.md` and no sink executed.
- Skipped cleanly when disabled; no change to output shape otherwise.

## Review Decisions

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

- Pinned critiqued set: winner + runner-up (wildcard is not critiqued); promoted finalists still consume the shared `premortem_rounds` bound.
- Concession moved from the defender's discretion to a script rule over critic-assigned severity.
- All-conceded is the sole permitted `winner: null` case; `apply_verdicts` recomputes runner-up/wildcard (FEAT-3582 § Data Contract).
- Priority stays P4, but FEAT-3596 no longer hard-blocks on this issue (see FEAT-3596).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 64/100 → MODERATE

### Gaps to Address
- Unresolved dependencies (hard override): `blocked_by` FEAT-3582 and FEAT-3583 are both `Open`. The `portfolio`/`validate_portfolio` states and resolved `premortem` profile value this issue extends do not exist yet.

### Concerns
- "Winner (and optionally the runner-up)" leaves the critiqued-finalist count open; pin it.

### Outcome Risk Factors
- Moderate per-site complexity: `apply_verdicts` demotes/promotes across `portfolio.json`, `winners.md`, and `ideas.jsonl`, and `validate_portfolio` must be extended for all-conceded.
- No executable test exists for the hand-rolled round counter pattern (`diagnosis_retry`), so the bound test must be written from scratch; also constrained by `max_steps` and `_validate_zero_retry_counter`.


## Session Log
- `/ll:confidence-check` - 2026-09-25T17:21:40 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:35 - `fa11583b-aa00-4da8-b0f0-fc89c6cf8f64.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:46 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:43 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:52 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
