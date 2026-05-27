---
id: BUG-1731
type: BUG
priority: P3
status: open
captured_at: '2026-05-26T23:19:12Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
relates_to:
  - ENH-1669
  - ENH-1399
  - ENH-1614
---

# BUG-1731: `ll-loop list --running` shows stale state without triggering ENH-1669 reconciliation

## Summary

`ll-loop list --running` reads `.loops/.running/*.state.json` directly and prints whatever `status` is on disk, without applying the dead-PID reconciliation that ENH-1669 wired into `ll-loop status`. Users see inflated "running" counts (e.g., 12 of 20 autodev instances reported as running) that are immediately corrected the moment they run `ll-loop status <loop>`. The two commands disagree about the same files because the read-path writer is installed in only one of them.

## Root Cause

**File**: `scripts/little_loops/cli/loop/info.py`
**Function**: `cmd_list()` (lines 54-114)

`cmd_list()` calls `list_running_loops(loops_dir)` from `fsm/persistence.py:796-847`, which globs `.state.json` files and returns their on-disk `LoopState` snapshots verbatim. The reconciliation helpers `_resolve_live_pid()` and `_reconcile_stale_running()` added by ENH-1669 live in `cli/loop/lifecycle.py` and are wired only into `_status_single()` and `cmd_status()`. `cmd_list()` never invokes them.

## Steps to Reproduce

1. Have ≥1 abandoned foreground autodev run (`status: running` on disk, PID dead).
2. `ll-loop list --running` — see inflated `[running]` count.
3. `ll-loop status autodev` — entries auto-flip to `interrupted`.
4. `ll-loop list --running` again — count is now accurate.

Observed today: `list --running` reported `12 running, 7 paused, 1 completed`. After one `ll-loop status` call: `1 running, 18 interrupted (paused), 1 completed`. Same 20 files; 10 were silently misreported by `list`.

## Expected Behavior

`ll-loop list --running` and `ll-loop status <loop>` should agree on the status of every instance in `.loops/.running/`. The reconciliation that ENH-1669 made automatic on `status` should fire on `list` too — same PID-resolution chain, same `state.status = "interrupted"` write, same `reconciled_at` timestamp.

## Current Behavior

`list_running_loops()` returns raw on-disk `LoopState` objects. `cmd_list()` renders the `status` field directly (mapping `interrupted` → `paused` for display). No PID-liveness check, no save-back.

## Proposed Solution

Lift `_reconcile_stale_running()` from `cli/loop/lifecycle.py` into `fsm/persistence.py` (or a shared `_helpers` module) so it can be called from both call sites without circular import. Then call it inside `list_running_loops()` (`persistence.py:796-847`) before returning — same construction pattern ENH-1669 uses in `_status_single()`:

```python
persistence = StatePersistence(state.loop_name, loops_dir, instance_id=instance_id)
state = _reconcile_stale_running(state, persistence, running_dir, stem)
```

Alternatively, leave the reconciliation in `lifecycle.py` and have `cmd_list()` invoke it on each returned instance before display. The first option is preferred because it makes any future read site self-correcting.

## API/Interface

No public CLI changes. Internal: `_reconcile_stale_running()` either moves to `fsm/persistence.py` or gets re-exported. `list_running_loops()` becomes a read-path writer (matches the pattern ENH-1669 established for `cmd_status`).

## Implementation Steps

1. Decide between (a) move `_reconcile_stale_running()` + `_resolve_live_pid()` to `fsm/persistence.py`, or (b) call them from `cmd_list()` in `info.py` post-list. Option (a) is more durable.
2. If (a): move the two helpers, update the `lifecycle.py` import to re-export or re-import. Verify no circular imports.
3. Invoke `_reconcile_stale_running()` inside `list_running_loops()` (`persistence.py:796`) for each instance before appending to the result list.
4. Add a test in `scripts/tests/test_fsm_persistence.py`: write a state file with `status="running"`, dead `state.pid`, no `.pid`/`.lock`; call `list_running_loops()`; assert the returned `LoopState` has `status="interrupted"` and the on-disk file has been rewritten.
5. Add an integration test that `cmd_list(--running)` and `cmd_status(<loop>)` produce identical status counts when run back-to-back against the same fixture.
6. Update `docs/reference/CLI.md` (and `docs/guides/LOOPS_GUIDE.md` if it describes `list` as a read-only command) to note that `--running` now reconciles stale entries in-place, mirroring `status`.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/persistence.py` — host the reconciliation helpers; call inside `list_running_loops()`.
- `scripts/little_loops/cli/loop/lifecycle.py` — adjust import if helpers move.
- `scripts/little_loops/cli/loop/info.py` — no logic change required if reconciliation is inside `list_running_loops()`.

### Tests

- `scripts/tests/test_fsm_persistence.py` — new test class or test in `TestListRunningLoops` (if exists) covering the reconciliation side effect.
- `scripts/tests/test_cli_loop_lifecycle.py` — extend `TestReconcileStaleRunning` parity tests to cover the `list` call site.

### Documentation

- `docs/reference/CLI.md` — `ll-loop list --running` is now a read-path writer.
- `docs/guides/LOOPS_GUIDE.md` — update any "read-only listing" framing.
- `skills/cleanup-loops/SKILL.md` — Step 1 uses `ll-loop list --running --json`; the note about ENH-1669 reconciliation should be moved up so it applies to `list` output too.

### Similar Patterns

- ENH-1669 (done) — installed the same reconciliation on `status`; this issue is the symmetric application to `list`.
- ENH-1399 (done) — startup sweep that does a stricter cleanup at `cmd_run()` time. The `list`-time reconciliation is the read-path complement, not a replacement.

## Impact

- **Priority**: P3 — correctness/UX issue, not blocking. Users get misleading state until they hit `status`, which causes wasted investigation (this exact issue prompted a multi-step diagnosis session).
- **Effort**: Small — the reconciliation logic already exists; this is a wiring/dedup change with one new test path.
- **Risk**: Low — same write behavior as ENH-1669, applied to a new read site. Background runs with live PIDs are still protected by the existing PID-liveness check.
- **Breaking Change**: No (state transition that was previously deferred to `status` now also fires on `list`).

## Success Metrics

- `ll-loop list --running` and `ll-loop status <loop>` report identical status counts back-to-back for any loop with stale entries.
- No regression in background-run handling (live PIDs never wrongly reconciled).
- The investigation that motivated this issue (misleading "12 running" from `list --running`) does not recur.

## Scope Boundaries

- Out of scope: bulk cleanup of `interrupted` state files (separate concern; cleanup-loops skill / potential `--prune-interrupted` flag).
- Out of scope: handling pre-ENH-1669 state files with no `state.pid` (edge case for one historical file; would need a TTL fallback).
- Out of scope: changing the display label from `paused` to `interrupted` in `cmd_list()` output (ENH-1614 territory).

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM loop persistence layer |
| [docs/reference/API.md](../../docs/reference/API.md) | `little_loops.fsm.persistence` reference |
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md) | Loop authoring conventions |

## Labels

`bug`, `ll-loop`, `cli`, `state-reconciliation`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-05-26T23:19:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0010b6d0-c5ea-42f5-b7da-dacb34c4bb15.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
