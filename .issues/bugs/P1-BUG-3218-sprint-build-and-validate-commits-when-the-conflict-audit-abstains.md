---
id: BUG-3218
type: BUG
title: sprint-build-and-validate commits when the conflict audit abstains
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:27:23Z'
parent: EPIC-3217
---

# BUG-3218: sprint-build-and-validate commits when the conflict audit abstains

## Summary

`sprint-build-and-validate.yaml`'s `audit_conflicts` gate is an `llm_structured` judge with `on_error: commit`. Since ENH-3185, a judge that cannot evaluate the conflict audit from the evidence available returns `cannot_judge`; with no `on_cannot_judge` declared, `FSMExecutor` holds the state twice and then escalates to the `on_error` fallback — which is `commit`. An audit that could not be performed therefore produces a commit, exactly as if it had returned `yes`.

This is the fabricated-pass failure mode ENH-3185 was written to remove, relocated from the judge's verdict into the loop's route table.

## Current Behavior

`scripts/little_loops/loops/sprint-build-and-validate.yaml`, state `audit_conflicts`:

- `on_yes: commit`
- `on_no: audit_conflicts_retry`
- `on_partial: audit_conflicts_retry`
- `on_error: commit`

An abstention takes the `on_error` branch (`executor.py:2669` `_abstention_fallback`) after `_ABSTENTION_HOLD_CAP = 2` holds, landing on `commit`. Note the two holds re-enter the state and re-run its action, so the audit is attempted three times before the loop gives up and commits anyway.

## Expected Behavior

An abstained conflict audit must not reach `commit`. Abstention here means "the audit could not be performed", which is a reason to retry with better evidence or to stop — never a reason to proceed as though no conflicts exist.

The `on_error: commit` route should also be re-examined on its own merits: it was presumably written to keep an infrastructure failure from stalling a sprint, but it has the same fail-open shape for genuine errors.

## Motivation

This gate guards a commit. A silent fail-open on an unobservable audit is the highest-severity instance of the abstention gap found in the built-in loops, and it is the only one where the wrong route writes to the repository.

## Root Cause

- **File**: `scripts/little_loops/loops/sprint-build-and-validate.yaml`
- **Anchor**: state `audit_conflicts` (lines 97-118)
- **Cause**: The state's `on_error: commit` (line 118) is a shorthand route for genuine evaluator/infrastructure errors, not for abstention. Since ENH-3185, an undeclared `cannot_judge`/`cannot_judge_uncertain` verdict is *not* treated as `on_error` on the first occurrence — `FSMExecutor`'s dispatch branch (`scripts/little_loops/fsm/executor.py:2075-2085`) routes it through `_route_abstention_hold()` (`:2683-2697`) instead, which holds (re-enters `audit_conflicts`, re-running its prompt/evaluate cycle) up to `_ABSTENTION_HOLD_CAP = 2` (`:2654`) times before calling `_abstention_fallback()` (`:2669-2681`). Because `audit_conflicts.route is None`, `_abstention_fallback` falls through to `if state.on_error:` and resolves `"commit"` — the same destination a genuine `on_yes` verdict reaches. Three consecutive `cannot_judge` verdicts (2 holds + 1 escalation) therefore drive the FSM into `commit`, indistinguishable from a passed audit.

## Proposed Solution

Declare `on_cannot_judge: audit_conflicts_retry` so an abstention routes immediately (a declared route fires with no hold, per the ENH-3185 precedence) into the existing retry path, which already exists for `no`/`partial`.

If the retry path can itself abstain indefinitely, pair it with the state's `max_retries` / `on_retry_exhausted` machinery so exhaustion terminates in a failure-shaped state rather than in `commit`.

Separately, evaluate whether `on_error: commit` should become a failure-shaped terminal.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — `audit_conflicts` state (lines 97-118) declares `on_yes`/`on_no`/`on_partial`/`on_error` but no `on_cannot_judge`; an undeclared `cannot_judge`/`cannot_judge_uncertain` verdict here holds twice (re-running the audit action each time) then escalates via `_abstention_fallback` to `on_error: commit` (line 118).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_abstention_declared` (2656-2667), `_route_abstention_hold`/`_ABSTENTION_HOLD_CAP=2` (2652-2697), `_abstention_fallback` (2669-2681, resolves `state.on_error` when `state.route is None`), and the dispatch branch selecting hold-vs-`_route()` (2075-2085). None of these need to change for this fix — they already implement the ENH-3185 precedence (a *declared* `on_cannot_judge` routes immediately, no hold).
- `scripts/little_loops/fsm/schema.py` — `StateConfig.from_dict()` (`_known_on_keys` set 853-865, `extra_routes` comprehension 866-870) is what a new `on_cannot_judge: audit_conflicts_retry` line would parse through; no code change needed here either.
- `audit_conflicts_retry` (same file, lines 120-129) is the existing retry state today reached only via `on_no`/`on_partial`; it has an unconditional `next: commit` with no `max_retries`/`on_retry_exhausted` of its own, and re-running the audit twice via the hold mechanism does not touch it (the hold re-enters `audit_conflicts`, not `audit_conflicts_retry`).

### Conventions in Force
- Every judged gate that has multiple `on_*` shorthand routes in this codebase orders them `on_yes`, `on_no`, `on_partial`, `on_error` last (evidence: `sprint-build-and-validate.yaml:115-118` itself, and `harness-single-shot.yaml:152-154`) — a new `on_cannot_judge` line would conventionally sit alongside `on_partial`, before `on_error`.
- Retry states pairing `max_retries` with `on_retry_exhausted` sit on the *producing* action state one step upstream of the judge, not on the judge's own `evaluate` state (evidence: `harness-single-shot.yaml:32-42` `execute` state's `max_retries: 3` / `on_retry_exhausted: failed`; `general-task.yaml:309-329` `do_work`'s `max_retries: 2` / `on_retry_exhausted: capture_work_exit`). `on_retry_exhausted` targets are not a single canonical name across loops — each loop picks its own failure-shaped destination.
- Failure-shaped terminals in this file already exist as siblings to reuse or model a new one after: `refine_failed`, `sprint_failed`, `refine_unresolved_failed` (`sprint-build-and-validate.yaml:171-181`), each `terminal: true` / `failure: true`.
- No loop YAML in the repo currently declares `on_cannot_judge` (confirmed via grep across `scripts/little_loops/loops/**`) — this is the first retrofit instance under EPIC-3217, so there is no in-repo precedent for its exact phrasing beyond the `docs/generalized-fsm-loop.md:547` prose description ("Declare `on_cannot_judge: <target>` ... same as `on_blocked`").

### Tests
- `scripts/tests/test_fsm_executor.py` — `TestAbstentionRouting` (from line 1882) exercises the generic hold/escalate/immediate-route mechanism (`test_declared_on_cannot_judge_routes_immediately_no_hold`, `test_undeclared_cannot_judge_shorthand_holds_then_falls_to_on_error`, etc.) but never against `sprint-build-and-validate.yaml` itself.
- `scripts/tests/test_builtin_loops.py` — structural tests for this loop (class scoped at `LOOP_FILE` line 7943) assert `audit_conflicts`'s `on_yes`/`on_no`/`on_partial` routes (`test_audit_conflicts_uses_llm_structured_evaluator` 8176, `test_audit_conflicts_on_yes_routes_to_commit` 8187, `test_audit_conflicts_on_no_routes_to_retry` 8194, `test_audit_conflicts_on_partial_routes_to_retry` 8201, `test_audit_conflicts_retry_state_exists` 8208, `test_max_steps_accommodates_retry_cycle` 8216) but assert nothing about `on_error` or an `on_cannot_judge` route — none of these would catch this bug or need to change unless a new assertion is added.

### Documentation
- `docs/generalized-fsm-loop.md:547` already documents the `on_cannot_judge` shorthand and the hold-then-`on_error` fallback in prose; no update needed unless this fix changes the general mechanism (it does not — only the loop YAML changes).

### Configuration
N/A

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Decision Rules
- New routing decision this fix introduces: `audit_conflicts`'s `evaluate.type: llm_structured` block (`sprint-build-and-validate.yaml:104-113`, `min_confidence: 0.7`) may itself downgrade a low-confidence YES/NO/PARTIAL to `cannot_judge` — the exact inputs are the verdict enum `{yes, no, partial, cannot_judge, cannot_judge_uncertain}` and the `min_confidence` threshold already declared. This issue's fix is to declare `on_cannot_judge: audit_conflicts_retry` so that verdict routes immediately (no hold), matching the existing `on_no`/`on_partial` destination. Escape hatch: if `audit_conflicts_retry`'s own re-run also abstains, it currently has an unconditional `next: commit` (line 129) regardless of verdict — the Expected Behavior section's request to "evaluate whether `on_error: commit` should become a failure-shaped terminal" and to pair the retry with `max_retries`/`on_retry_exhausted` (per the `harness-single-shot.yaml:32-42` / `general-task.yaml:309-329` convention found above) is the open decision the implementer must resolve; this issue does not mandate a specific target name.

### Types
N/A — no data shape introduced or modified.

### Signatures
- `FSMExecutor._abstention_fallback(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — unaffected; the fix is declarative (a YAML routing key), not a code change to this function.

### Call Path
`audit_conflicts` (llm_structured evaluate) -> `FSMExecutor` abstention dispatch -> `on_error: commit` is the current abstention path this issue closes by adding a declared `on_cannot_judge` route, which instead resolves via `FSMExecutor` `_route` directly with no hold. `FSMExecutor` (`scripts/little_loops/fsm/executor.py`) owns both the hold-and-escalate path and the immediate-route path this fix switches between.

## Implementation Steps

1. `audit_conflicts` in `scripts/little_loops/loops/sprint-build-and-validate.yaml:97-118` declares `on_cannot_judge: audit_conflicts_retry`, so an abstained audit routes on the first occurrence, with no hold, into the same retry path `on_no`/`on_partial` already use.
2. The retry path's exhaustion behavior is decided and stated explicitly: either `audit_conflicts_retry` (lines 120-129) gains `max_retries`/`on_retry_exhausted` pointed at a failure-shaped terminal (following the `harness-single-shot.yaml:32-42` / `general-task.yaml:309-329` convention), or the existing unconditional `next: commit` is left as a deliberate choice — whichever is chosen, the issue's Expected Behavior constraint holds: an audit that never resolves must not reach `commit` silently.
3. `on_error: commit` (line 118) is re-examined on its own merits per the issue's Expected Behavior — a genuine infrastructure error reaching `commit` has the same fail-open shape being fixed for abstention; the resolution (leave as-is with rationale, or route to a failure terminal) is recorded either in this issue or a follow-up.
4. `scripts/tests/test_builtin_loops.py`'s existing `audit_conflicts` assertions (8176-8216) continue passing, and a new assertion covers the added `on_cannot_judge` route the same way `test_audit_conflicts_on_no_routes_to_retry` (8194) covers `on_no`.
5. `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py -v` passes.

## Impact

Removes a fail-open path to `commit` on an unobservable conflict audit.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — abstention-fallback routing and MR-4's `on_yes`-without-route rule
- `docs/ARCHITECTURE.md` `## Extension Architecture & Event Flow` — FSM executor
  role and event emission for state transitions

## Status

**Open** | Created: 2026-08-16 | Priority: P1


## Session Log
- `/ll:refine-issue` - 2026-08-16T23:54:28 - `40668286-18e1-4fb3-b8c2-566405cf8bec.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
