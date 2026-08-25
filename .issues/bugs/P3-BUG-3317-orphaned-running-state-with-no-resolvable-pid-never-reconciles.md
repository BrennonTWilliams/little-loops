---
id: BUG-3317
type: BUG
title: 'Orphaned ''running'' state with no resolvable PID never reconciles — dead runs
  show as live indefinitely in ll-loop list --running and dashboards'
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
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` (via `list_running_loops`),
  `cmd_status`; no code change expected, behavior change only
- `scripts/little_loops/fsm/executor.py` — startup sweep call site for
  `_reconcile_stale_runs`
- `scripts/little_loops/mcp_server/tasks.py` — reads `accumulated_ms`/status from
  disk status; benefits from correct statuses
- `scripts/little_loops/transport.py` — dashboard-seed callback consumes the
  unfiltered run list

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

### Documentation
- `docs/reference/CLI.md` — `ll-loop list --running` reconciliation note, if it
  documents the current PID-only rule

### Configuration
- N/A (threshold is a module constant; promote to `.ll/ll-config.json` only if a real
  need appears)

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
- `/ll:refine-issue` - 2026-08-25T00:27:16 - `b31fdb34-d45a-44b4-81b6-d5f34a9cf389.jsonl`
