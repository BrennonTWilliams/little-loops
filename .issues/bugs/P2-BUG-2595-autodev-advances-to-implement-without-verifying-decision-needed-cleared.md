---
id: BUG-2595
title: autodev advances to implement_current after run_decide without verifying decision_needed
  cleared
type: BUG
priority: P2
status: done
captured_at: '2026-07-10T00:00:00Z'
completed_at: '2026-07-11T02:41:02Z'
discovered_date: '2026-07-10'
discovered_by: audit-loop-run
source_loop: autodev
source_state: recheck_after_decide
relates_to:
- BUG-2594
- BUG-1378
- BUG-2513
- BUG-1256
- BUG-1416
labels:
- loops
- fsm
- autodev
- decide-issue
- decision-gate
confidence_score: 98
outcome_confidence: 77
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 17
score_change_surface: 18
---

# BUG-2595: autodev advances to `implement_current` after `run_decide` without verifying `decision_needed` was cleared

## Summary

After `run_decide` runs `/ll:decide-issue --auto`, `autodev` verifies only that
readiness/outcome **scores** pass (`recheck_after_decide`) before routing to
`implement_current`. It never re-checks that `decision_needed` was actually
cleared. When `/ll:decide-issue --auto` silently no-ops — leaving
`decision_needed: true` and writing nothing to `.ll/decisions.yaml` — but the
scores already pass, the loop marches into `implement_current`, where `ll-auto
--only` correctly refuses to implement a gated issue and exits 1. That failure
is then routed to `check_learning_gate`, which misclassifies a **decision-gate**
block as a non-learning-gate outcome and drains the issue as a generic failure.
The issue is never implemented and no distinct "decision unresolved" outcome is
recorded.

## Current Behavior

Observed in run `2026-07-11T011831-autodev` (issue BUG-2588):

1. `check_decision_at_dequeue` saw `decision_needed: true` → routed to
   `run_decide`.
2. `run_decide` ran `/ll:decide-issue BUG-2588 --auto` (`next: mark_decide_ran`,
   `on_error: recheck_after_decide`). It exited 0 but **cleared nothing**:
   BUG-2588 still has `decision_needed: true` and there is **no BUG-2588 entry
   in `.ll/decisions.yaml`**.
3. `mark_decide_ran` → `rerun_confidence_after_decide` → `recheck_after_decide`.
4. `recheck_after_decide` ran `ll-issues check-readiness BUG-2588 --readiness 85
   --outcome ...`. BUG-2588's scores (`confidence_score: 97`,
   `outcome_confidence: 86`) pass → exit 0 → `on_yes: implement_current`.
5. `implement_current` ran `ll-auto --only BUG-2588` → manage-issue halted at
   **Phase 2.3 Decision Gate** (`decision_needed` still armed), emitted a plan
   for manual approval, exited 1 (the BUG-1256 fix working correctly).
6. `implement_current.on_no` routed to `check_learning_gate` — but a
   decision-gate block is not a learning-gate block, so (had it not crashed on
   BUG-2594) it would emit `OK` and fall through `check_impl_auth` →
   `dequeue_next`, dropping BUG-2588 as a generic failure with no
   decision-specific outcome.

Verbatim `ll-auto` output (captured `ll_auto_output`):
```
Phase 2.3: Decision Gate — HALTED ← you are here
### To clear the gate
Run one of these:
  /ll:decide-issue BUG-2588
  /ll:manage-issue bug fix BUG-2588 --force-implement
```
Verbatim `ll-auto` stderr:
```
Warning: BUG-2588 status=open (expected done/cancelled)
No meaningful changes detected - only excluded files modified: ['.issues/bugs/P3-BUG-2588-...']
```

This is distinct from prior decision-gate bugs:
- **BUG-1378** (done): `recheck_after_decide` read *stale/too-low* scores. Here
  scores are fresh and *passing* — the inverse failure.
- **BUG-2513** (done): bypass on `refine_current` *non-success* exits. Here
  `refine_current` was never entered (decision detected at dequeue).
- **BUG-1256** (done): `ll-auto` exited 0 on a gate block. That fix works — it
  exits 1 here. The remaining gap is that autodev advances into a guaranteed
  failure and then misclassifies it.

## Expected Behavior

After `run_decide`, `autodev` must confirm the decision gate is actually cleared
before advancing to `implement_current`. If `decision_needed` is still armed:

1. Do not route to `implement_current` (implementation is guaranteed to halt).
2. Route to a distinct "decision unresolved" outcome that is recorded in the run
   summary (so the operator sees "decide-issue produced no actionable decision"
   rather than a generic implementation failure), mirroring how learning-gate
   blocks are recorded distinctly.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: states `run_decide` (`next: mark_decide_ran` — success unverified)
  and `recheck_after_decide` (`ll-issues check-readiness ...` — validates scores
  only)
- **Cause**: `run_decide`'s success path never verifies the flag was cleared,
  and the only gate between decide and implement (`recheck_after_decide`) checks
  readiness/outcome scores, not `decision_needed`. When scores already pass, a
  no-op decide leaks a still-armed issue into `implement_current`. The downstream
  `check_learning_gate` then treats the resulting decision-gate block as a
  non-learning-gate outcome (misclassification).

Note: the very issue under test (BUG-2588 — "save_decisions() silently drops
entry keys not declared on the dataclass") may explain *why* decide recorded
nothing, but the autodev routing gap is independent of that: any silent no-op
from `/ll:decide-issue --auto` (see BUG-1416) reproduces it.

## Steps to Reproduce

1. Pick an issue with `decision_needed: true` whose readiness/outcome scores
   already exceed the thresholds.
2. Ensure `/ll:decide-issue --auto` no-ops for it (no enumerable options / see
   BUG-1416), leaving `decision_needed: true`.
3. Run `ll-loop run autodev "<ID>"`.
4. Observe `recheck_after_decide` passes on scores → `implement_current` →
   `ll-auto --only` halts at the decision gate and exits 1.
5. Observe the failure routes to `check_learning_gate` and is not recorded as a
   decision-gate outcome; the issue is not implemented.

## Proposed Solution

Insert a decision-gate re-check between decide and implement, and give
`run_decide` a verified post-condition:

```yaml
  recheck_after_decide:
    action: |
      ll-issues check-readiness ${captured.input.output} \
        --readiness ${context.readiness_threshold} \
        --outcome ${context.outcome_threshold} \
        && echo "${captured.input.output}" >> ${context.run_dir}/autodev-passed.txt
    fragment: shell_exit
+   on_yes: assert_decision_cleared   # was: implement_current
    on_no: snap_and_size_review
    on_error: snap_and_size_review

+ assert_decision_cleared:
+   # Guard: after decide, the flag must be cleared before implementing.
+   # ll-auto would otherwise halt at manage-issue's decision gate.
+   action: ll-issues check-flag ${captured.input.output} decision_needed
+   evaluate: { type: exit_code }
+   on_yes: record_decision_unresolved   # flag still present → distinct outcome
+   on_no: implement_current             # flag cleared → safe to implement
+   on_error: implement_current
```

`record_decision_unresolved` writes the issue to a distinct outcome file (e.g.
`autodev-decision-unresolved.txt`) surfaced in the run summary, then advances the
queue — parallel to `mark_gate_blocked` for learning-gate blocks. (Confirm the
exact `check-flag` exit-code semantics for "flag present/true".)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`ll-issues check-flag` already exists — no new CLI work needed.** Implemented
  at `scripts/little_loops/cli/issues/check_flag.py:13` (`cmd_check_flag`):
  `fm.get(args.field)`; returns `0` if the string value is `"true"`
  (case-insensitive), `1` otherwise (false/unset/any other value). Registered in
  `scripts/little_loops/cli/issues/__init__.py:626-634` (`check-flag`, alias
  `cf`, positional args `issue_id field`) and dispatched at lines 847-848. This
  **confirms** the proposed solution's exit-code semantics: exit 0 =
  `decision_needed == "true"` (flag still armed) → `on_yes`; exit 1 = cleared →
  `on_no`. The comments in the proposed YAML diff (`on_yes: ... # flag still
  present`, `on_no: ... # flag cleared`) are correct as written.
- **Directly reusable precedent already in this same file.** Four existing
  states in `autodev.yaml` use the identical
  `ll-issues check-flag ${captured.input.output} decision_needed` /
  `fragment: shell_exit` / `on_yes: run_decide` shape:
  `check_decision_at_dequeue` (lines 106-118), `check_decision_after_refine`
  (169-177), `check_decision_before_size_review` (610-622), and
  `check_missing_artifacts` (640-648, field `missing_artifacts`). All of these
  gate *entry* into `run_decide`; none re-verify the flag *after* `run_decide`
  runs — `assert_decision_cleared` would be the first post-decide instance of
  this pattern.
- **Confirmed misclassification path.** `check_learning_gate` (lines 446-458)
  uses `fragment: ll_auto_learning_gate_check`, which greps
  `ll_auto_last.txt` for the `LEARNING_GATE_BLOCKED` marker
  (`scripts/little_loops/loops/lib/common.yaml:327-351`,
  `evaluate: { type: output_contains, pattern: "GATE_BLOCKED" }`). A Phase 2.3
  Decision Gate halt does not print that marker, so it falls through
  `on_no: check_impl_auth` (line 457) rather than `mark_gate_blocked` — verifying
  the issue's claim that decision-gate blocks are misclassified as generic
  failures through this route.
- **Additional aggregation site not yet in the Integration Map.** When autodev
  runs as a sub-loop of `auto-refine-and-implement` (the sprint/backlog
  wrapper), that parent loop's summary state independently reads
  `autodev-gate-blocked.txt` and feeds it into `summary.json`'s `gate_blocked`
  key and the `parked_rate` denominator — see
  `scripts/little_loops/loops/auto-refine-and-implement.yaml:232` (count),
  `:263` (parked-rate calc), `:284-285` (JSON payload). A new
  `autodev-decision-unresolved.txt` ledger would need equivalent read/aggregate
  logic added at this site too, not just in `autodev.yaml`'s own `done` state,
  to avoid the ENH-2404 failure mode ("a blocked issue vanished from
  summary.json with no trace") recurring for decision-unresolved outcomes.
- **`done` state aggregation pattern to mirror** (`autodev.yaml:741-776`):
  reads `autodev-gate-blocked.txt` into `GATE_BLOCKED_IDS`/`_COUNT`/`_LIST`
  (lines 752, 757, 761) and conditionally prints a summary line (lines
  768-770). `init` (line 53) resets `autodev-gate-blocked.txt` to empty at run
  start — a new `autodev-decision-unresolved.txt` needs the same reset.
- **Test precedent for the new distinct-outcome state.**
  `test_mark_gate_blocked_advances_queue_without_failing`
  (`scripts/tests/test_builtin_loops.py:2697-2708`) asserts the action string
  contains the target ledger filename, an operator-facing remedy string, and
  `next == "dequeue_next"` — the template to copy for a
  `test_record_decision_unresolved_advances_queue_without_failing` test.
  `test_recheck_after_decide_on_no_routes_to_snap_and_size_review` (around line
  3315) only asserts `on_no`/`on_error`, so it is unaffected by retargeting
  `on_yes` to `assert_decision_cleared`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `recheck_after_decide.on_yes`
  retarget (line 341: `implement_current` → `assert_decision_cleared`); new
  `assert_decision_cleared` + `record_decision_unresolved` states; reset
  `autodev-decision-unresolved.txt` in `init` (mirror line 53); read/aggregate
  it in `done` (mirror lines 752-761, 768-770).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the parent
  sprint/backlog wrapper loop independently aggregates
  `autodev-gate-blocked.txt` into `summary.json`'s `gate_blocked` key and the
  `parked_rate` denominator (lines 232, 263, 284-285); needs equivalent
  `autodev-decision-unresolved.txt` handling or the new outcome disappears from
  `summary.json` the same way ENH-2404 fixed for gate-blocked issues.

### Dependent Files (Callers/Importers)
- Summary/reporting for autodev — `autodev.yaml`'s own `done` state
  (lines 741-776, mirrors the `autodev-gate-blocked.txt` handling at lines
  752-761/768-770) AND `auto-refine-and-implement.yaml`'s summary state (see
  above) both need the new decision-unresolved bucket wired in.

### Similar Patterns
- `mark_gate_blocked` (distinct learning-gate outcome) — mirror its shape for
  the decision-unresolved outcome.
- `rn-remediate` decide path — check for the same missing post-decide flag
  verification.

### Tests
- `scripts/tests/test_builtin_loops.py` — case where decide no-ops but scores
  pass; assert the loop records a decision-unresolved outcome and does not enter
  `implement_current`.
- `scripts/tests/test_autodev_decision_gate.py` — dedicated decision-gate test
  module (holds `TestCheckDecisionAtDequeueStructural`/`Routing`,
  `TestCheckDecisionBeforeSizeReviewStructural`/`Routing` for the BUG-2513 /
  BUG-2519 fixes); the natural home for a new
  `TestAssertDecisionClearedStructural`/`Routing` class rather than adding to
  `test_builtin_loops.py`.
- `.issues/enhancements/P3-ENH-2404-autodev-skip-and-gate-blocked-summary-visibility.md`
  — prior art for exactly the "new ledger file needs summary-visibility wiring"
  problem this fix creates for `autodev-decision-unresolved.txt`; review its
  Integration Map for the full set of aggregation sites it touched (mirrors the
  `auto-refine-and-implement.yaml` gap noted above).

_Wiring pass added by `/ll:wire-issue` — confirmed no existing test currently
pins the assertions this change touches, so nothing needs updating, only new
coverage:_
- No existing test asserts `recheck_after_decide.on_yes == "implement_current"`
  by name (`test_recheck_after_decide_on_no_routes_to_snap_and_size_review`,
  `test_builtin_loops.py:3315`, only checks `on_no`/`on_error`) — the retarget
  to `assert_decision_cleared` is safe; add
  `test_recheck_after_decide_on_yes_routes_to_assert_decision_cleared`.
- `test_mark_gate_blocked_advances_queue_without_failing`
  (`test_builtin_loops.py:2697-2708`) is the exact template for a new
  `test_record_decision_unresolved_advances_queue_without_failing` (assert the
  action writes to `autodev-decision-unresolved.txt`, points the operator at
  `/ll:decide-issue`, and `next == "dequeue_next"`).
- `TestCheckDecisionAtDequeueStructural`/`Routing`
  (`test_autodev_decision_gate.py:97-260`, using the module's
  `_load_autodev_yaml()`/`_StubRunner`/`_state`/`_loop` helpers) is the direct
  template for new `TestAssertDecisionClearedStructural`/`Routing` classes.
- The `_run_finalize` fixture (`test_builtin_loops.py:2024-2087`) and its
  `gate_blocked` kwarg/quartet (`test_finalize_summary_has_enh_2404_keys`,
  `test_finalize_sources_gate_blocked_ledger`,
  `test_finalize_gate_blocked_count_surfaces`,
  `test_finalize_gate_blocked_zero_when_no_ledger_entries`, lines 2254-2287)
  is the direct template for a `decision_unresolved` kwarg + matching
  four-test quartet against `auto-refine-and-implement.yaml`'s `finalize`
  state.
- Gap confirmed in *existing* coverage, not just new: no test shell-executes
  `autodev.yaml`'s `done` state to assert on its `GATE_BLOCKED_IDS`/`_COUNT`/
  `_LIST` aggregation or summary printf text (grepped, zero matches) — so
  there's no direct template for asserting the mirrored
  `autodev-decision-unresolved.txt` aggregation in `done`; a new test would
  need to be written from scratch (shell-execute `done`'s action, assert on
  printed text) rather than copied.
- If the ll-parallel-path gap noted under "Similar Patterns" below is also
  fixed, `TestDecideIssueGate` (`test_worker_pool.py:2905-2961`) is the class
  to extend with a "still `decision_needed: true` after decide" regression
  case.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` / autodev docs — note the
  post-decide flag verification.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `### autodev` FSM-flow ASCII diagram
  repeats the edge `recheck_after_decide → [thresholds met?] → implement_current`
  **eight times** across lines 936, 937, 939, 949, 950, 952, 957, 958 (once per
  decide-entry branch). Each needs the new `assert_decision_cleared` hop
  inserted. The "Outcome failure triage" prose immediately below (line 966)
  also states "On gate pass, the loop proceeds to `implement_current` without
  decomposition" — goes stale and needs the new state name.
- `skills/audit-loop-run/SKILL.md` (line ~290, `## Step 6:` ENH-2404 key
  enumeration) — if the new `autodev-decision-unresolved.txt` bucket is
  surfaced in `summary.json` for visibility parity with `gate_blocked` (per
  the ENH-2404 precedent this issue already cites), Step 6 should mention the
  new key alongside `skipped_breakdown`/`gate_blocked`/`parked_rate`, mirroring
  the "additive"/"legacy" back-compat language already there. Advisory —
  confirm whether visibility parity is in scope before touching this file.

### Similar Patterns (confirmed instances of the same gap)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml:626-633` (`decide` state) —
  **confirmed same gap**: `on_yes: re_assess` trusts `/ll:decide-issue --auto`'s
  own reported outcome and never re-verifies `decision_needed` was actually
  cleared via `ll-issues check-flag`, unlike the pre-decide gate
  `check_decision_needed_post` (line 725-735) which does use `check-flag`. If
  `assert_decision_cleared` becomes the established post-decide-verification
  pattern, this is the direct sibling to retrofit.
- `scripts/little_loops/parallel/worker_pool.py:518-528` (`_process_issue`,
  ll-parallel path) — **confirmed same gap, more permissive**: on
  `decision_needed is True`, runs `decide-issue`; even when
  `decide_result.returncode != 0` it only logs a warning
  ("continuing to implementation anyway...") and proceeds unconditionally —
  never checks whether `decision_needed` was cleared, on success or failure.
  Existing test coverage: `scripts/tests/test_worker_pool.py:2905-2961`
  (`TestDecideIssueGate` — class covering conditional decide-issue invocation)
  is the place a `decision_needed still true after decide` regression test
  would go if this path is also fixed.

### Configuration
- N/A

## Motivation

Without a post-decide flag check, autodev wastes a full `ll-auto` implementation
attempt (270s+ here) on an issue that cannot possibly implement, then buries the
result as a generic failure — so operators cannot tell "decide produced no
decision" from "implementation failed." Recording the outcome distinctly makes
the failure actionable (remedy: run `/ll:decide-issue` manually or
`--force-implement`) and avoids the guaranteed-halt round trip.

## Impact

- **Priority**: P2 — leaks a still-gated issue into implementation, wasting a
  long `ll-auto` run and misclassifying the outcome; not data-corrupting, and
  manage-issue correctly refuses to implement, so no wrong code is written.
- **Effort**: Small — one guard state plus a distinct-outcome state mirroring
  `mark_gate_blocked`.
- **Risk**: Low — adds a gate on the path to implementation; the happy path
  (flag actually cleared) is unchanged.
- **Breaking Change**: No

## Resolution

Inserted `assert_decision_cleared` between `recheck_after_decide` and
`implement_current` in `scripts/little_loops/loops/autodev.yaml`. It re-checks
`decision_needed` via `ll-issues check-flag` (exit 0 = still armed) after
`run_decide` runs, so a silent `/ll:decide-issue --auto` no-op with
already-passing scores can no longer leak into `implement_current`'s
guaranteed halt. A still-armed flag routes to a new `record_decision_unresolved`
state (mirrors `mark_gate_blocked`), which writes the issue to
`autodev-decision-unresolved.txt` and returns to `dequeue_next` — the issue is
left in place, not dropped as a generic failure. `init` resets the new ledger;
`done` surfaces a distinct `Decision-unresolved (N): ...` summary line, mirroring
the `Gate-blocked` line. `auto-refine-and-implement.yaml`'s `finalize` state
(the sprint/backlog wrapper) reads the same ledger into a new
`decision_unresolved` `summary.json` key and folds it into `parked_rate`,
mirroring the ENH-2404 `gate_blocked` precedent so the outcome doesn't vanish
from the parent loop's summary.

Added `TestAssertDecisionClearedStructural`/`Routing` to
`test_autodev_decision_gate.py` and a `decision_unresolved` kwarg + test quartet
to `test_builtin_loops.py`'s `_run_finalize` fixture. Both loop YAMLs pass
`ll-loop validate`.

## Status

**Done** | Created: 2026-07-10 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-07-11T02:40:17 - `55ad7083-fb33-43be-bbc0-c9787228c8de.jsonl`
- `/ll:ready-issue` - 2026-07-11T02:33:40 - `8a3f6a0f-3e0b-4abe-8ebc-428ab149cd61.jsonl`
- `/ll:confidence-check` - 2026-07-10T00:00:00Z - `1994db89-6c40-419c-af1c-18ff766e3a2a.jsonl`
- `/ll:wire-issue` - 2026-07-11T02:30:16 - `1135792b-b9c8-4aab-a829-c8745b00ef5f.jsonl`
- `/ll:refine-issue` - 2026-07-11T02:23:41 - `6857fc5c-2daf-4ac8-adc2-3cb272810226.jsonl`
