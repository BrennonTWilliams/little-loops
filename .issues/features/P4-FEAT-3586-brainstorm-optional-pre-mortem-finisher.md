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
- Rounds are bounded by a context value and enforced by the FSM using the `retry_counter` fragment from `lib/common.yaml`.
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

`tournament` -> `premortem_critic` -> `premortem_defender` -> `retry_counter` -> `portfolio` -> `verify_artifacts`

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

## Implementation Steps

1. Add `premortem_critic` and `premortem_defender` states, gated on the resolved profile (FEAT-3583) or `premortem=true`.
2. Bound rounds with the `retry_counter` fragment and a `premortem_rounds` context value.
3. Implement `apply_verdicts` to demote/promote and record changes in `ideas.jsonl` and `winners`.
4. Render `Risks & Kill Criteria` per finalist in `brainstorm.md`; leave output shape unchanged when disabled.
5. Add tests for bounded rounds, demotion/promotion, and the disabled path; run `ll-loop validate brainstorm`.

## Impact

- **Priority**: P4 - optional finisher that refines output but is not needed for a working engine
- **Effort**: Small - two LLM states, one bounded counter, and one small script; reuses `retry_counter`
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
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:52 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
