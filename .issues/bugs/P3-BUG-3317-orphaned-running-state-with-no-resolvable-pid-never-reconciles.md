---
id: BUG-3317
type: BUG
title: "Orphaned 'running' state with no resolvable PID never reconciles \u2014 dead\
  \ runs show as live indefinitely in ll-loop list --running and dashboards"
priority: P3
status: open
discovered_by: ci-agent-report
discovered_date: '2026-08-24'
captured_at: '2026-08-24T00:00:00Z'
labels:
- fsm
- persistence
- observability
testable: true
confidence_score: 100
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3317: Orphaned 'running' state with no resolvable PID never reconciles

## Summary

A `.loops/.running/*.state.json` entry with `status: "running"` whose PID cannot be
resolved from any source (`.pid` file gone, `.lock` file gone, `state.pid` null) is
left as `running` forever. Both reconciliation paths —
`_reconcile_stale_running()` (`scripts/little_loops/fsm/persistence.py`, read path,
called from `list_running_loops` and the `ll-loop status` command path) and
`_reconcile_stale_runs()`
(startup path) — deliberately bail when liveness cannot be proven, so the entry
never self-heals. The run then appears as an active loop in `ll-loop list --running`
and in every consumer that seeds off that list, indefinitely.

Observed live in a downstream consuming project: an
`.loops/.running/<loop>.state.json` has been `status: "running"` since **2026-04-26**
(last `updated_at` 44m52s after its `started_at`, `pid: null`, `reconciled_at: null`)
— four months of a dead process reported as running.

## Context

Filed from a CI-agent bug report that misdiagnosed the symptom as "`started_at` is
stale after resume." That diagnosis was **wrong** and its proposed fix is rejected —
see [Rejected Diagnosis](#rejected-diagnosis-do-not-implement) below. The real
defect is the liveness gap described here.

## Current Behavior

`_reconcile_stale_running()` flips `running` → `interrupted` only when
`_resolve_live_pid()` returns a PID **and** `_process_alive()` says it is dead:

```python
pid = _resolve_live_pid(running_dir, stem, state)
if pid is None:
    return state  # no PID resolvable — cannot determine liveness, leave alone
if _process_alive(pid):
    return state
```

`_reconcile_stale_runs()` has the mirrored guard on the startup path: "No `.pid`
file → leave alone (can't confirm)."

PID resolution fails permanently for any state written before PID tracking existed,
and for any run whose `.pid`/`.lock` files were cleaned up (or removed by
`ll-loop stop`) while the state file kept `status: "running"`. Once in that
condition the entry is unreachable by both reconcilers and only manual deletion or
`/ll:cleanup-loops` clears it.

Because `ACTIVE_RUN_STATUSES = {"running", "starting"}`, `cmd_list` in
`scripts/little_loops/cli/loop/info.py` keeps rendering these entries under
`--running`, with a duration derived from the state's accumulated-elapsed field
(correct for the run, but presented as if the run were live).

## Expected Behavior

When no PID is resolvable, reconciliation falls back to an `updated_at` staleness
check: a `running` state whose last write is older than a threshold (default 6h) is
provably not a live loop — a live FSM writes state on every transition — and is
flipped to `interrupted` with `reconciled_at` stamped, exactly as the dead-PID path
does today. Genuinely long-running-but-quiet loops are protected by the threshold
being far above any single action's runtime.

## Steps to Reproduce

1. Start any loop so `.loops/.running/<loop>.state.json` is written with
   `status: "running"`.
2. Kill the process without a clean shutdown, then delete the sibling `.pid` and
   `.lock` files (any state file predating PID tracking has `pid: null` and
   reproduces this directly).
3. Wait any amount of time — days or months.
4. Run `ll-loop list --running`.
5. Observe: the dead run is still listed as `[running]`, and re-reading its state
   file shows `status: "running"`, `reconciled_at: null`. It never reconciles.

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `in function _reconcile_stale_running()` (read path) and
  `in function _reconcile_stale_runs()` (startup path)
- **Cause**: Both treat "PID unresolvable" as "liveness unknown → leave alone."
  `_resolve_live_pid()` returns `None` whenever `.pid`, `.lock`, and `state.pid` are
  all absent, which is a permanent condition for legacy and cleaned-up entries. With
  no secondary liveness signal, the `running` status is a terminal trap.

## Proposed Solution

Add an `updated_at`-age fallback used only when `_resolve_live_pid()` returns `None`.
Keep the existing PID logic first — a resolvable, alive PID must still win regardless
of `updated_at` age.

```python
STALE_RUNNING_THRESHOLD_S: int = 6 * 3600  # no state write in 6h ⇒ not a live loop

def _running_state_is_stale(state: LoopState, threshold_s: int = STALE_RUNNING_THRESHOLD_S) -> bool:
    """True when a running state's last write is older than threshold_s."""
    if not state.updated_at:
        return False  # never saved — cannot judge; leave alone
    try:
        ts = datetime.fromisoformat(state.updated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:            # tolerate legacy naive timestamps
        ts = ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds() > threshold_s
```

In `_reconcile_stale_running()`, replace the bare `if pid is None: return state`
with: if `pid is None` and `_running_state_is_stale(state)` → flip to `interrupted`,
stamp `reconciled_at`, `persistence.save_state(state)`; otherwise return unchanged.
Apply the mirrored change to `_reconcile_stale_runs()`'s `status == "running"` branch
so the startup sweep archives the same entries.

Alternative considered and rejected: deleting/archiving unresolvable entries outright
— `interrupted` is the correct terminal here because it stays resumable, matching how
the dead-PID path already behaves.

### Not in scope: `accumulated_ms` vs `started_at`

The reporting consumer (`ll-console`) computes elapsed as `now − started_at`. That is
its own bug and its own repo — `ll-console` has no source in this codebase (no
`ll-console` entry point in `scripts/pyproject.toml`, no `/api/projects` handler).
The authoritative duration is `LoopState.accumulated_ms`, already emitted by
`LoopState.to_dict()` and already what `cmd_list` reads. No change needed here;
notify that consumer separately.

### Rejected diagnosis (do not implement)

The originating report proposed "reset `started_at` on resume so it stays
authoritative." This must **not** be done:

- `started_at` is intentionally the first-ever start; `PersistentFSM.resume()`
  restores it verbatim and carries prior elapsed forward via
  `self._executor.elapsed_offset_ms = state.accumulated_ms`.
- It is load-bearing identity: the archive `run_id` is derived from it
  (`StatePersistence.archive_run()`), and `list_run_history()` sorts on it.
  Rewriting it mid-run would rename archive directories and break run identity.
- The two-field split is already correct and consistent: `started_at` = when the run
  began; `accumulated_ms` = active elapsed across all segments, excluding paused gaps.

The report's headline evidence ("resumed ~45 min ago, shown as 4 months") does not
hold: the observed state file was never resumed. It ran once for 44m52s
(`accumulated_ms: 2692855`, matching `updated_at − started_at`) and the process died.
Both numbers were correct; only the *liveness* claim was false.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `_reconcile_stale_running()`,
  `_reconcile_stale_runs()`, new `_running_state_is_stale()` +
  `STALE_RUNNING_THRESHOLD_S`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` (via `list_running_loops`);
  no code change expected, behavior change only
  > ⚠ Superseded — `cmd_status` lives in `lifecycle.py`, not here
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status` (calls
  `_reconcile_stale_running` at lines ~161, ~223, ~312, ~348 via
  `_build_status_dict`/`_status_single`); no code change expected, behavior change
  only [Agent 1 finding, graph-confirmed]
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` (line ~347, function-local
  import) calls `_reconcile_stale_runs` — this is the actual startup sweep call
  site [Agent 1 finding, graph-confirmed]
  > ⚠ Superseded — was misattributed to `fsm/executor.py`, which has zero
  > references to any reconciliation symbol (confirmed by grep)
- `scripts/little_loops/fsm/__init__.py` — re-exports `list_running_loops` in
  `__all__` (line ~247) [Agent 1 finding]
- `scripts/little_loops/mcp_server/tasks.py` — `handle_tasks_get()` reads
  `accumulated_ms`/status via `read_run_status()` (`lifecycle.py`), which calls
  `_build_status_dict()` → `_reconcile_stale_running()` — a documented transitive
  dependency (`lifecycle.py`'s `read_run_status` docstring cites Decision 1:
  PID-liveness reconciliation); benefits from correct statuses [Agent 1/2 finding]
- `scripts/little_loops/transport.py` — `_make_seed_callback()` (line ~591) calls
  `list_running_loops()` directly to seed dashboard clients on connect; genuine
  direct dependency, no code change expected [Agent 1 finding, graph-confirmed]

### Similar Patterns
- `LockManager.find_conflict()` stale-lock cleanup in
  `scripts/little_loops/fsm/concurrency.py` — same "prove it's dead" shape; consider
  whether it needs the same age fallback (out of scope unless it shares the trap)

### Tests
- `scripts/tests/` FSM persistence tests — add cases: (a) unresolvable PID + fresh
  `updated_at` → left `running`; (b) unresolvable PID + `updated_at` older than
  threshold → flipped to `interrupted` with `reconciled_at` set; (c) resolvable live
  PID + old `updated_at` → left `running`; (d) empty/malformed `updated_at` → left
  alone

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` `TestReconcileStaleRuns` (startup path,
  lines ~3009-3121) — extend `_write_state()` (line ~3012) with an `updated_at`
  param (currently hardcoded to `""`) and add cases (a)-(d) above. This class has
  no direct unit test for `_reconcile_stale_running()` (the read path) at all
  [Agent 3 finding — confirmed gap].
- `scripts/tests/test_cli_loop_lifecycle.py` `TestReconcileStaleRunning` (line
  ~2734) — an existing class already exercising `_reconcile_stale_running()`
  indirectly via `cmd_status`, not previously listed in this issue. Extend its
  `_make_state()` helper (line ~2737) with an `updated_at` param the same way.
  [Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning::test_no_reconcile_no_pid_anywhere`
  (line ~2852) — **will break** under this fix: its fixture hardcodes
  `updated_at="2026-05-24T10:05:00Z"`, which is now >6h stale, so the state will
  flip to `interrupted` and its `assert state.status == "running"` /
  `assert state.reconciled_at is None` assertions will fail. Must be updated to
  either use a fresh relative timestamp or split into an explicit stale-case
  variant. [Agent 3 finding — confirmed breaking test]
- No `freezegun`/`freeze_time` dependency exists in this repo. Follow the
  relative-timestamp pattern from `scripts/tests/test_cli_loop_next.py` (lines
  ~127-178): `(datetime.now(UTC) - timedelta(hours=7)).isoformat()` for stale,
  `timedelta(minutes=5)` for fresh — no `datetime` monkeypatching needed for
  ordinary threshold cases. [Agent 3 finding]
- `scripts/tests/test_transport.py`, `test_json_output_contracts.py`,
  `test_ll_loop_commands.py` all mock `list_running_loops` directly and bypass
  `_reconcile_stale_running()`'s internal logic entirely — unaffected by this
  change, no update needed. [Agent 1/3 finding, informational]

### Documentation
- `docs/reference/CLI.md` — `ll-loop list --running` reconciliation note, if it
  documents the current PID-only rule

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:924` — confirmed: the `ll-loop status` note describes only
  the PID-dead rewrite ("If a state file claims `status: running` but its PID … is
  provably dead …"); needs an additive sentence for the new `updated_at`-age
  fallback. [Agent 2 finding]
- `docs/reference/CLI.md:4812-4816` — the `tasks/get` MCP doc's "reconciles PID
  liveness before ever reporting `working`" line is accurate but incomplete after
  this fix (reconciliation now also covers no-PID/stale-`updated_at`). [Agent 2
  finding]
- `docs/guides/MCP_SERVER_GUIDE.md:550` — same wording duplicated from CLI.md's MCP
  section; same additive update needed. [Agent 2 finding]
- `skills/cleanup-loops/SKILL.md:69` — Note documents only the PID-dead rewrite,
  same incompleteness. Also worth flagging to skill authors: the skill implements
  its own independent 15-minute `updated_at` staleness check (lines ~91-114) for
  no-PID `running` loops, which now partially overlaps with the new 6h fallback for
  loops stuck 15min-6h without a resolvable PID (the skill's tighter threshold
  still does non-redundant work outside that window, so no behavior change is
  required — informational only). [Agent 2 finding]

### Configuration
- N/A (threshold is a module constant; promote to `.ll/ll-config.json` only if a real
  need appears)

_Wiring pass added by `/ll:wire-issue`:_
- Precedent confirmed for the "module constant, not config" choice:
  `scripts/little_loops/session_store/writers.py:2000` —
  `STALE_SUBAGENT_MIN_AGE_SECONDS = 6 * 3600`, the *same* 6-hour value, used as the
  identical age-fallback threshold shape for `reconcile_stale_subagent_runs()` in a
  sibling subsystem, also kept as a bare constant rather than config-schema-exposed.
  [Agent 2 finding — supports the existing N/A decision, no action needed]

## Program Design

### Types

- `STALE_RUNNING_THRESHOLD_S: int`

### Signatures

- `_running_state_is_stale(state: LoopState, threshold_s: int = STALE_RUNNING_THRESHOLD_S) -> bool`
- `_reconcile_stale_running(state: LoopState, persistence: StatePersistence, running_dir: Path, stem: str) -> LoopState` — unchanged signature, new fallback branch
- `_reconcile_stale_runs(loops_dir: Path) -> int` — unchanged signature, new fallback branch

### Call Path

`list_running_loops` -> `_reconcile_stale_running` -> `_running_state_is_stale` -> `StatePersistence.save_state`

## Implementation Steps

1. Add `STALE_RUNNING_THRESHOLD_S` and `_running_state_is_stale()` to
   `fsm/persistence.py`.
2. Wire the fallback into `_reconcile_stale_running()`'s `pid is None` branch.
3. Mirror it in `_reconcile_stale_runs()`'s `status == "running"` branch.
4. Add the four regression tests above.
5. Verify against a real orphaned artifact: a months-old `pid: null` running entry
   read via `ll-loop list --running` now flips to `interrupted` and drops off the
   running list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning::test_no_reconcile_no_pid_anywhere` — its fixture's hardcoded `updated_at` is now stale under the new threshold and the test will fail without a fix
- Extend `scripts/tests/test_fsm_persistence.py::TestReconcileStaleRuns._write_state()` with an `updated_at` parameter to support the new fresh/stale/malformed test cases
- Extend `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning._make_state()` with an `updated_at` parameter for the same reason
- Add a direct unit test for `_reconcile_stale_running()` (read path) — no such test exists today; coverage is only indirect via `cmd_status`
- Update `docs/reference/CLI.md` (both the `ll-loop status` note at ~line 924 and the `tasks/get` MCP section at ~lines 4812-4816) and `docs/guides/MCP_SERVER_GUIDE.md:550` to describe the new age-fallback path, not just the PID-dead rewrite
- Update `skills/cleanup-loops/SKILL.md:69`'s reconciliation Note for the same reason

## Impact

- **Priority**: P3 — Misleading observability only. No data loss, no execution
  impact; the state file stays resumable either way. Visible because dead runs
  pollute `--running` and every dashboard seeded from it, and the entries accumulate
  permanently.
- **Effort**: Small — one helper plus two call-site branches, all inside a single
  module; reuses the existing flip-and-save path.
- **Risk**: Low — the change only widens reconciliation for entries that today are
  provably unreachable. Threshold is far above any real action runtime, and a
  resolvable live PID still short-circuits. Worst case is an early flip to
  `interrupted`, which is resumable.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A `running` state with no resolvable PID and `updated_at` older than the
      threshold is flipped to `interrupted` with `reconciled_at` set, on both the
      read path and the startup sweep.
- [ ] A `running` state with no resolvable PID but a recent `updated_at` is left
      untouched.
- [ ] A `running` state with a resolvable, live PID is left untouched regardless of
      `updated_at` age.
- [ ] Regression tests covering all three cases plus the empty/malformed
      `updated_at` guard pass under `python -m pytest scripts/tests/`.
- [ ] `started_at` semantics are unchanged; no test asserts it advances on resume.

## Status

**Open** | Created: 2026-08-24 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-25T01:07:07 - `c0b9fe69-0e8b-4aa4-850b-b9fc74a99fe4.jsonl`
- `/ll:wire-issue` - 2026-08-25T00:59:30 - `35df48ee-1624-44f3-9b90-d443ec0fa011.jsonl`
- `/ll:refine-issue` - 2026-08-25T00:27:16 - `b31fdb34-d45a-44b4-81b6-d5f34a9cf389.jsonl`
