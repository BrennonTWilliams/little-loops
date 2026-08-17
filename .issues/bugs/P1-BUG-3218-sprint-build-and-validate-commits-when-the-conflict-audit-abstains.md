---
id: BUG-3218
type: BUG
title: sprint-build-and-validate commits when the conflict audit abstains
priority: P1
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:27:23Z'
completed_at: '2026-08-17T02:18:45Z'
parent: EPIC-3217
confidence_score: 98
outcome_confidence: 85
score_complexity: 21
score_test_coverage: 21
score_ambiguity: 21
score_change_surface: 22
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

**The retry path is itself fail-open.** `audit_conflicts_retry` (lines 120-129) has **no `evaluate:` block at all** and an unconditional `next: commit`. So the `on_no`/`on_partial` branches already reach `commit` after exactly one more audit attempt, with the second attempt's result never inspected. This is a pre-existing fail-open wider than the abstention case: a conflict audit that reports unaddressed conflicts twice still commits. Any fix that only redirects abstention *into* this retry path inherits the same fail-open.

**Verdict-string scope.** `_abstention_declared` (`executor.py:2655-2664`) matches the *literal* verdict string, and `_route` resolves only `extra_routes[verdict]`. A declared `on_cannot_judge` therefore does **not** claim `cannot_judge_uncertain`; that verdict still holds twice and escalates to `on_error`. It cannot occur here today (`uncertain_suffix` defaults to `false` and no built-in loop sets it — `fsm/schema.py:103`, `evaluators.py:1295-1296`), but it re-opens this exact fail-open the moment anyone sets `uncertain_suffix: true` on this gate while `on_error` still resolves to `commit`. **Resolved at EPIC-3217 (decision (a), 2026-08-16): BUG-3228** adds a general `_uncertain` suffix fallback to `_route`, so `cannot_judge_uncertain` will resolve through this issue's `on_cannot_judge` route once it lands. This issue declares `on_cannot_judge` only, needs no second key, and is safe before or after BUG-3228 because it removes `commit` from the error route regardless.

## Expected Behavior

An abstained conflict audit must not reach `commit`. Abstention here means "the audit could not be performed", which is a reason to retry with better evidence or to stop — never a reason to proceed as though no conflicts exist.

The same must hold for the retry attempt: no path through `audit_conflicts` / `audit_conflicts_retry` may reach `commit` without a `yes` verdict from an audit that actually ran.

The `on_error: commit` route is re-examined on its own merits as part of this fix: it was presumably written to keep an infrastructure failure from stalling a sprint, but it has the same fail-open shape for genuine errors, and leaving it pointed at `commit` leaves a second unguarded door into the same defect.

## Steps to Reproduce

This is a routing defect reached through the FSM, not a manually-driven UI
repro. To trigger it end to end:

1. Run the `sprint-build-and-validate` loop (`scripts/little_loops/loops/sprint-build-and-validate.yaml`)
   on a sprint whose `audit_conflicts` state's judged evaluation returns
   `cannot_judge` (e.g. `/ll:audit-issue-conflicts --auto` produces output the
   judge cannot ground a YES/NO/PARTIAL verdict in, per the
   `CHECK_SEMANTIC_EVIDENCE_CONTRACT`) on three consecutive attempts (the
   initial run plus the two `_ABSTENTION_HOLD_CAP` holds).
2. Observe that `FSMExecutor._route_abstention_hold` exhausts its holds and
   calls `_abstention_fallback`, which — because `audit_conflicts` declares no
   `on_cannot_judge` — falls through to `state.on_error`, resolving to
   `commit` (`sprint-build-and-validate.yaml:118`).
3. The loop proceeds to `commit` exactly as if the audit had returned `yes`,
   even though the conflict audit never actually produced a usable verdict.

Equivalently, at the unit level: `scripts/tests/test_fsm_executor.py`'s
`TestAbstentionRouting` (from line 1882) already exercises the generic
hold/escalate mechanism this bug relies on
(`test_undeclared_cannot_judge_shorthand_holds_then_falls_to_on_error`); this
issue is that mechanism reached through `sprint-build-and-validate.yaml`'s
specific `on_error: commit` route, which no test in
`test_builtin_loops.py` currently asserts against (see Tests below).

## Motivation

This gate guards a commit. A silent fail-open on an unobservable audit is the highest-severity instance of the abstention gap found in the built-in loops, and it is the only one where the wrong route writes to the repository.

## Root Cause

- **File**: `scripts/little_loops/loops/sprint-build-and-validate.yaml`
- **Anchor**: state `audit_conflicts` (lines 97-118)
- **Cause**: The state's `on_error: commit` (line 118) is a shorthand route for genuine evaluator/infrastructure errors, not for abstention. Since ENH-3185, an undeclared `cannot_judge`/`cannot_judge_uncertain` verdict is *not* treated as `on_error` on the first occurrence — `FSMExecutor`'s dispatch branch (`scripts/little_loops/fsm/executor.py:2075-2085`) routes it through `_route_abstention_hold()` (`:2683-2697`) instead, which holds (re-enters `audit_conflicts`, re-running its prompt/evaluate cycle) up to `_ABSTENTION_HOLD_CAP = 2` (`:2654`) times before calling `_abstention_fallback()` (`:2669-2681`). Because `audit_conflicts.route is None`, `_abstention_fallback` falls through to `if state.on_error:` and resolves `"commit"` — the same destination a genuine `on_yes` verdict reaches. Three consecutive `cannot_judge` verdicts (2 holds + 1 escalation) therefore drive the FSM into `commit`, indistinguishable from a passed audit.

## Proposed Solution

Three changes, all required — the first alone does not satisfy Expected Behavior, because it routes abstention into a retry path that unconditionally commits.

1. `audit_conflicts` declares `on_cannot_judge: audit_conflicts_retry`, so an abstention routes immediately (a declared route fires with no hold, per the ENH-3185 precedence) into the same retry path `no`/`partial` already use.
2. `audit_conflicts_retry` gains its own `evaluate:` block — the same `llm_structured` judge and prompt as `audit_conflicts` over the re-captured `conflict_result` — replacing the unconditional `next: commit`. Only `on_yes` reaches `commit`; `on_no`, `on_partial`, `on_cannot_judge`, and `on_error` all reach a failure-shaped terminal.
3. `audit_conflicts`'s `on_error` is repointed off `commit` to that same failure-shaped terminal.

This makes the gate fail-closed on every path: a sprint whose conflict audit cannot be resolved (or cannot be performed, or errors) reports failure instead of committing and running. That is a deliberate behavior change beyond the abstention case — it also closes the pre-existing `no`/`partial` fail-open documented in Current Behavior.

`max_retries` / `on_retry_exhausted` are *not* used here: the loop already bounds the audit at two attempts by construction (`audit_conflicts` → `audit_conflicts_retry`), and the ENH-3185 hold mechanism supplies bounded retry for the abstention case on its own.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `sprint-build-and-validate` section's ASCII FSM flow diagram (~lines 862-869) shows only `YES/error → commit` and `NO/PARTIAL → audit_conflicts_retry`, with no abstention branch; the per-state table row for `audit_conflicts` (line 890) spells out `on_yes`/`on_no`/`on_partial`/`on_error` explicitly and needs a new clause for `on_cannot_judge`. The `audit_conflicts_retry` row (line 891, "unconditionally routes to `commit`") also needs updating if Implementation Step 2 adds `max_retries`/`on_retry_exhausted`. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` `TestSprintBuildAndValidateLoop` — add `test_audit_conflicts_on_cannot_judge_routes_to_retry`, modeled on the existing `test_audit_conflicts_on_no_routes_to_retry` (line 8194), asserting `data["states"]["audit_conflicts"].get("on_cannot_judge") == "audit_conflicts_retry"` (this test class reads the raw parsed YAML dict directly, not `StateConfig.extra_routes`) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` `test_audit_conflicts_retry_state_exists` (line 8208) currently asserts `audit_conflicts_retry.next == "commit"` unconditionally — **will break** if Implementation Step 2 converts the state to `max_retries`/`on_retry_exhausted` instead of a bare `next: commit`; update alongside that choice [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` `test_max_steps_accommodates_retry_cycle` (line 8216) and the repo-wide failure-terminal walker (`test_no_failure_edge_routes_to_a_success_terminal`-style check at lines 64-87, asserting every `on_error`/`on_failure`/`on_retry_exhausted` target has `failure: true`) — re-verify against whichever exhaustion design Implementation Step 2 picks; if a new failure-shaped terminal is introduced, it must set `failure: true` (matching the `refine_failed`/`sprint_failed` sibling pattern) or the walker fails [Agent 2 finding]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Decision Rules
- New routing decision this fix introduces: `audit_conflicts`'s `evaluate.type: llm_structured` block (`sprint-build-and-validate.yaml:104-113`) uses the default schema, so its verdict grammar is `DEFAULT_VERDICT_ENUM` = `{yes, no, blocked, partial, cannot_judge}` (`fsm/verdicts.py:15`), and the universally-injected `CHECK_SEMANTIC_EVIDENCE_CONTRACT` (`evaluators.py:66-74`) instructs the judge to answer Cannot Judge when it cannot quote supporting text. That is the input to the new route.
- **Correction to an earlier reading of this state**: the declared `min_confidence: 0.7` does **not** downgrade a low-confidence verdict to `cannot_judge`, and in fact has no routing effect at all here. `evaluators.py:1263` computes `confident = confidence >= min_confidence`, but the only consumer is `evaluators.py:1295-1296`, which appends an `_uncertain` suffix *and only when `uncertain_suffix: true`* (`fsm/schema.py:103`, default `false`; this state does not set it). Otherwise `confident` lands in `details` and is never routed on. Do not implement against a low-confidence→`cannot_judge` path; it does not exist.
- Verdict-string scope: `on_cannot_judge` claims the literal `cannot_judge` only, not `cannot_judge_uncertain` (see Current Behavior). Unreachable at this gate today; the fix's removal of `commit` from the error route is what keeps it safe if that changes. The general resolution is EPIC-3217's call, not this issue's.
- The failure-shaped terminal this fix routes to follows the sibling pattern already in this file (`refine_failed`, `sprint_failed`, `refine_unresolved_failed`, lines 171-181): `terminal: true` **and** `failure: true` must both be set explicitly, or `test_builtin_loops.py`'s failure-terminal walker (lines 64-87) fails. Name is the implementer's call; `audit_failed` matches the file's `<phase>_failed` convention.

### Types
N/A — no data shape introduced or modified.

### Signatures
- `FSMExecutor._abstention_fallback(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — unaffected; the fix is declarative (a YAML routing key), not a code change to this function.

### Call Path
`audit_conflicts` (llm_structured evaluate) -> `FSMExecutor` abstention dispatch -> `on_error: commit` is the current abstention path this issue closes by adding a declared `on_cannot_judge` route, which instead resolves via `FSMExecutor` `_route` directly with no hold. `FSMExecutor` (`scripts/little_loops/fsm/executor.py`) owns both the hold-and-escalate path and the immediate-route path this fix switches between.

## Implementation Steps

1. A failure-shaped terminal (e.g. `audit_failed`) is added to `scripts/little_loops/loops/sprint-build-and-validate.yaml` with both `terminal: true` and `failure: true`, matching the `refine_failed`/`sprint_failed` siblings (lines 171-181).
2. `audit_conflicts` (lines 97-118) declares `on_cannot_judge: audit_conflicts_retry`, so an abstained audit routes on the first occurrence with no hold, into the same retry path `on_no`/`on_partial` already use.
3. `audit_conflicts`'s `on_error` (line 118) is repointed from `commit` to the failure terminal — a genuine infrastructure error reaching `commit` is the same fail-open shape being fixed for abstention, and leaving it in place keeps a second unguarded door to `commit`.
4. `audit_conflicts_retry` (lines 120-129) gains an `evaluate:` block (the same `llm_structured` judge and prompt as `audit_conflicts`, over the re-captured `conflict_result`) replacing its unconditional `next: commit`. Routes: `on_yes: commit`; `on_no`, `on_partial`, `on_cannot_judge`, `on_error` all to the failure terminal. This closes the pre-existing `no`/`partial` fail-open as well as the abstention one.
5. `max_steps` (currently 18) is re-checked against the longest path now that the retry state evaluates rather than falling straight through, and `test_max_steps_accommodates_retry_cycle` (`test_builtin_loops.py:8216`) is updated if the bound moved.
6. `scripts/tests/test_builtin_loops.py`: a new assertion covers the added `on_cannot_judge` route the same way `test_audit_conflicts_on_no_routes_to_retry` (8194) covers `on_no`; `test_audit_conflicts_retry_state_exists` (8208) is updated, since its `audit_conflicts_retry.next == "commit"` assertion **will break** by design under Step 4; and an assertion pins `audit_conflicts.on_error` to the failure terminal so Step 3 cannot silently regress.
7. The failure-terminal walker (`test_builtin_loops.py:64-87`, asserting every `on_error`/`on_failure`/`on_retry_exhausted` target sets `failure: true`) passes against the new terminal, and `TestValidatorWarningBudget`'s corpus-wide lint ratchet stays clean (this loop already emits a pre-existing MR-8 evidence-contract warning on `audit_conflicts`; do not add a new warning class).
8. `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py -v` passes and `ll-loop validate scripts/little_loops/loops/sprint-build-and-validate.yaml` exits 0.

## Impact

Removes every fail-open path to `commit` in this gate: the unobservable audit (abstention), the errored audit, and the pre-existing unchecked-retry path that commits on a second `no`/`partial`. Behavior change: a sprint whose conflict audit cannot be resolved now terminates as failed instead of committing and running.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — abstention-fallback routing and MR-4's `on_yes`-without-route rule
- `docs/ARCHITECTURE.md` `## Extension Architecture & Event Flow` — FSM executor
  role and event emission for state transitions

## Resolution

Implemented per Implementation Steps 1-8:

1. Added `audit_failed` terminal state (`terminal: true`, `failure: true`) to
   `sprint-build-and-validate.yaml`.
2. `audit_conflicts` now declares `on_cannot_judge: audit_conflicts_retry` so
   an abstention routes on the first occurrence, no hold.
3. `audit_conflicts.on_error` repointed from `commit` to `audit_failed`.
4. `audit_conflicts_retry` gained its own `evaluate:` block (same
   `llm_structured` judge/prompt) replacing the unconditional `next: commit`;
   only `on_yes` reaches `commit` — `on_no`/`on_partial`/`on_cannot_judge`/
   `on_error` all route to `audit_failed`.
5. `max_steps` (18) re-checked — unchanged; the retry state already counted
   as one step whether or not it evaluates.
6. `test_builtin_loops.py::TestSprintBuildAndValidateLoop` updated: existing
   `test_audit_conflicts_retry_state_exists` now asserts the evaluate block
   instead of the removed `next: commit`; new tests cover
   `on_cannot_judge`, `audit_conflicts.on_error`, all four
   `audit_conflicts_retry` failure edges, and `audit_failed`'s
   terminal/failure flags; `audit_failed` added to
   `test_required_states_exist`.
7. Failure-terminal walker (`test_no_failure_edge_routes_to_a_success_terminal`)
   and `TestValidatorWarningBudget` both pass unchanged — no new warning
   class introduced (the pre-existing MR-8 evidence-contract warning now
   also fires on `audit_conflicts_retry`, same category, not new).
8. `python -m pytest scripts/tests/` — 19595 passed, 46 skipped.
   `ll-loop validate scripts/little_loops/loops/sprint-build-and-validate.yaml`
   exits 0.

No `## Program Design` deviations — implementation matched the documented
Decision Rules, Signatures, and Call Path exactly.

## Status

**Open** | Created: 2026-08-16 | Priority: P1


## Session Log
- `/ll:manage-issue` - 2026-08-17T02:18:15 - `36f8e2e2-aff6-4bce-a03c-7b4dc7185314.jsonl`
- `/ll:ready-issue` - 2026-08-17T02:09:27 - `7484266f-2a08-44d2-9f57-f74069bbea9e.jsonl`
- `/ll:confidence-check` - 2026-08-17T01:07:43 - `5a985576-1a12-4019-84a2-4fcf31653b26.jsonl`
- `/ll:wire-issue` - 2026-08-17T00:15:05 - `364ce564-b8a8-42f8-9c6e-ae082c11cf3e.jsonl`
- `/ll:refine-issue` - 2026-08-16T23:54:28 - `40668286-18e1-4fb3-b8c2-566405cf8bec.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
