---
id: ENH-3366
type: ENH
priority: P3
status: open
captured_at: '2026-08-30T23:30:00Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- ENH-1679
- ENH-2005
decision_needed: true
---

# ENH-3366: `delegate`(autodev) verdict is laundered through `recheck_set`

## Summary

In `scripts/little_loops/loops/auto-refine-and-implement.yaml`, the
`delegate` state that invokes the `autodev` sub-loop (line 299) routes both
outcomes to the same next state:

```
on_success: recheck_set   # line 320
on_failure: recheck_set   # line 321
```

`recheck_set` (line 324) only re-resolves the sprint/EPIC's current issue
list to look for newly-added descendants to re-dispatch — it never reads any
`subloop_outcome_autodev`-style sidecar, so it cannot tell whether `autodev`
actually reached a successful terminal or crashed/failed. This is the same
verdict-laundering shape [[ENH-1679]] fixed for `refine_current`'s sub-loop,
but on this different state, and it does not qualify for the ENH-2005 sidecar
exemption `/ll:audit-loop-run` checks for (the shared next state's action
does not contain `subloop_outcome_`).

## Current Behavior

`delegate`'s `on_success` and `on_failure` both route to `recheck_set` (lines
320-321). `recheck_set` only re-resolves the sprint/EPIC's descendant set to
find newly-added children; it never reads any `autodev` outcome sidecar, so
whether `autodev` reached a clean terminal or crashed/failed is indistinguishable
by the time execution reaches `recheck_set` — both paths look identical.

## Expected Behavior

`autodev`'s real terminal verdict should be recoverable downstream — either
by giving `on_success`/`on_failure` distinct next states, or by having
`autodev`'s own finalize write a `subloop_outcome_autodev.txt` sidecar that
`recheck_set` (or a new intermediate state) reads before deciding whether to
re-dispatch, following the same artifact-channel pattern already used for
`auto-refine-and-implement`'s own outcome (`subloop_outcome_auto-refine-and-implement.txt`,
read by `sprint-refine-and-implement.yaml`'s `read_outcome` state).

## Proposed Solution

Two viable resolutions surfaced by research into how this codebase already
fixes this exact defect shape:

**Option A**: Differentiate `delegate`'s `on_success`/`on_failure` into
distinct target states, mirroring ENH-1679's actual fix for `autodev.yaml`'s
own `refine_current` state (lines 470-539) — no new artifact, no change to
`autodev.yaml`. Each target state would decide, using only the executor's
existing `terminated_by`/`failure_terminal` classification already available
via `${captured.delegate.*}` (`executor.py:1147-1196`), whether to proceed
into `recheck_set` (success) or route to a failure-handling state (failure)
before ever reaching `recheck_set`.

**Option B**: Have `autodev.yaml`'s `finalize_done` state write a new
`subloop_outcome_autodev.txt` sidecar (a one-line `printf '%s\n' "$VERDICT"`
addition, since `$VERDICT` is already computed there), and have
`recheck_set` (or a new intermediate state) read it before deciding whether
to re-dispatch — matching the existing `auto-refine-and-implement` →
`sprint-refine-and-implement` sidecar convention (ENH-2005).

**Recommended**: Option A — it is the only precedent in this codebase for
this *exact* defect shape (a sub-loop join needing to distinguish
success/failure at the routing level itself), it lives in the same
subsystem (`autodev.yaml`) already, requires no new artifact or change to
`autodev.yaml`, and has an established 5-test regression model to follow
(`test_refine_current_has_success_and_failure_routes` and its four siblings
in `scripts/tests/test_builtin_loops.py`). Option B is the better fit when a
state genuinely needs the child's *full* verdict detail preserved for a
later read by another state (as `sprint-refine-and-implement`'s
`read_outcome` does) — that need has not been demonstrated for
`recheck_set`, which only needs a success/crash distinction to decide
whether to re-dispatch.

## Scope Boundaries

- Does not change `recheck_set`'s re-dispatch semantics for EPIC descendant
  resolution (ENH-2615) — only how it (or an intermediate state) learns
  `autodev`'s prior verdict before deciding to re-dispatch.
- Does not add a new terminal-verdict enum value beyond what's needed to
  distinguish an `autodev` crash from a clean pass at this join point; it
  reuses the existing sidecar-file pattern rather than inventing new
  `summary.json` fields.
- Does not touch `refine_current`'s sub-loop join, which [[ENH-1679]]
  already fixed.

## Program Design

### Signatures

- `subloop_outcome_autodev.txt: str` — new sidecar artifact `autodev`'s own `finalize` state writes under `${context.run_dir}`, mirroring the existing `subloop_outcome_auto-refine-and-implement.txt` convention `sprint-refine-and-implement.yaml`'s `read_outcome` state already reads.
- `recheck_set(RUN_DIR)` (`auto-refine-and-implement.yaml:324`) — extend to read `subloop_outcome_autodev.txt` before deciding on re-dispatch, or route through a new intermediate state that does so first.

### Call Path

`delegate` -> `autodev`'s `finalize` -> `subloop_outcome_autodev.txt` -> `recheck_set` -> distinct downstream routing instead of the current unconditional fan-in from both `on_success` and `on_failure`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- ENH-1679's actual fix (`autodev.yaml`'s `refine_current` state, lines 470-539) is differentiated `on_success`/`on_failure`/`on_error` routing at the join itself — it never introduced or reads a `subloop_outcome_` sidecar. The sidecar convention this section's Signatures/Call Path describe is a *different*, unrelated precedent (ENH-2005, used by `sprint-refine-and-implement.yaml`'s `delegate`/`read_outcome` and `rn-implement.yaml`'s `run_remediation`/`classify_remediation`), not the one the Current Behavior section credits ENH-1679 with.
- See the Proposed Solution section's Option A/Option B framing — this section's existing Signatures/Call Path describe Option B only. Option A would need no new signature or artifact, only differentiated `on_success`/`on_failure` targets consuming the executor's existing `${captured.delegate.*}` classification (`executor.py:1147-1196`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the
  sub-loop-invoking state (lines 299-322) and `recheck_set` state (lines
  324-390) — both options touch these
- Option B only: `scripts/little_loops/loops/autodev.yaml` — `finalize_done`
  state (lines 2320-2496, specifically its `summary.json` write ~lines
  2479-2481)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_sub_loop()`
  (line 914) and its `on_success`/`on_failure`/`on_error` classification
  (lines 1160-1196) is what an Option A fix would read from via
  `${captured.delegate.*}`
- `skills/audit-loop-run/SKILL.md` (Step 8, lines 329-350) — the ENH-2005
  sidecar-exemption check this issue's own text cites; whichever option is
  chosen must satisfy Step 8's laundering check (Option A satisfies it by
  never collapsing `on_success`/`on_failure` in the first place, the same
  way `refine_current` does; Option B satisfies it via the sidecar-read
  condition)

### Conventions in Force
- Two established, working conventions for a sub-loop join needing to
  distinguish real success from failure exist in this codebase today, and
  they are **not** the same convention: (1) differentiated
  `on_success`/`on_failure`/`on_error` routing at the join itself —
  `autodev.yaml`'s `refine_current` (ENH-1679/ENH-2727, both closed); (2) a
  `subloop_outcome_<name>.txt` sidecar the child's own finalize writes,
  read by a shared `on_success`==`on_failure` target while `on_error` stays
  distinct — `sprint-refine-and-implement.yaml`'s `delegate`/`read_outcome`
  and `rn-implement.yaml`'s `run_remediation`/`classify_remediation`
  (ENH-2005, closed).
- `TestSubloopSidecarContract` (`scripts/tests/test_builtin_loops.py:490`)
  already enforces convention (2) mechanically for `rn-remediate`,
  `rn-decompose`, and `oracles/code-run-gate` — its `SUBLOOPS` tuple does
  not include `auto-refine-and-implement`/`autodev`; Option B would be a
  natural (not required) candidate for extending that tuple.
- An existing test, `test_delegate_crash_routes_to_record_error`
  (`test_builtin_loops.py:4300`), currently asserts today's laundered shape
  (`on_success == on_failure == "recheck_set"`) as correct/intentional —
  whichever option is chosen, this test's assertions will need to change.

### Tests
- `test_refine_current_has_success_and_failure_routes`,
  `test_refine_current_failure_routes_to_skip_inflight`,
  `test_refine_current_error_routes_to_skip_inflight_infra`,
  `test_refine_current_has_no_explicit_on_no`,
  `test_refine_current_compiled_on_no_resolves_to_skip_inflight`
  (`test_builtin_loops.py:6103-6163`) — the regression-test model for
  Option A
- `test_delegate_does_not_launder_subloop_verdict`
  (`test_builtin_loops.py:5430`) — the regression-test model for Option B,
  written against `sprint-refine-and-implement.yaml`'s analogous `delegate`
  state
- `test_delegate_crash_routes_to_record_error` (`test_builtin_loops.py:4300`)
  — must be updated regardless of which option is chosen
- `TestSubloopSidecarContract` (`test_builtin_loops.py:490`) — only
  relevant if Option B is chosen and its `SUBLOOPS` coverage is extended

## Impact

- **Priority**: P3 — matches [[ENH-1679]]'s severity class (same defect
  shape, different state); doesn't block the run today since `recheck_set`'s
  own `on_error` already routes to `verify` regardless, but a genuine
  `autodev` crash currently produces no distinguishable signal from a clean
  success at this join point.

## Status

**Open** | Created: 2026-08-30 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-31T02:37:53 - `80c0d0f5-6988-4121-a3c7-d08dabaee7ea.jsonl`
- `/ll:refine-issue` - 2026-08-31T02:36:37 - `b1737911-44d2-40e3-9bd5-5d8a15c8f475.jsonl`
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`
