---
id: BUG-1731
type: BUG
priority: P3
status: done
captured_at: '2026-05-26T23:19:12Z'
completed_at: '2026-05-27T01:53:21Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
relates_to:
- ENH-1669
- ENH-1399
- ENH-1614
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1731: `ll-loop list --running` shows stale state without triggering ENH-1669 reconciliation

## Summary

`ll-loop list --running` reads `.loops/.running/*.state.json` directly and prints whatever `status` is on disk, without applying the dead-PID reconciliation that ENH-1669 wired into `ll-loop status`. Users see inflated "running" counts (e.g., 12 of 20 autodev instances reported as running) that are immediately corrected the moment they run `ll-loop status <loop>`. The two commands disagree about the same files because the read-path writer is installed in only one of them.

## Motivation

`ll-loop list --running` is the primary command users reach for when asking "how many loops are currently running?" When it returns inflated counts (10 of 20 entries stale in the observed case), users waste time diagnosing phantom instances — the issue itself prompted a multi-step investigation session before the discrepancy was traced to the missing reconciliation call. Because ENH-1669 already contains the fix logic, the cost to close this trust gap is minimal: a wiring change and one new test path.

## Root Cause

**File**: `scripts/little_loops/cli/loop/info.py`
**Function**: `cmd_list()` (lines 54-258)

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

Option (a) is selected: moving the helpers to `persistence.py` makes every future read site self-correcting without additional wiring at each new call site.

## API/Interface

No public CLI changes. Internal: `_reconcile_stale_running()` either moves to `fsm/persistence.py` or gets re-exported. `list_running_loops()` becomes a read-path writer (matches the pattern ENH-1669 established for `cmd_status`).

## Implementation Steps

1. Move `_reconcile_stale_running()` and `_resolve_live_pid()` to `fsm/persistence.py` (option a — selected: every future read site self-corrects without additional wiring).
2. If (a): move the two helpers, update the `lifecycle.py` import to re-export or re-import. Verify no circular imports.
3. Invoke `_reconcile_stale_running()` inside `list_running_loops()` (`persistence.py:796`) for each instance before appending to the result list.
4. Add a test in `scripts/tests/test_fsm_persistence.py`: write a state file with `status="running"`, dead `state.pid`, no `.pid`/`.lock`; call `list_running_loops()`; assert the returned `LoopState` has `status="interrupted"` and the on-disk file has been rewritten.
5. Add an integration test that `cmd_list(--running)` and `cmd_status(<loop>)` produce identical status counts when run back-to-back against the same fixture.
6. Update `docs/reference/CLI.md` (and `docs/guides/LOOPS_GUIDE.md` if it describes `list` as a read-only command) to note that `--running` now reconciles stale entries in-place, mirroring `status`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Before moving helpers to `persistence.py`: audit all 6 methods in `TestReconcileStaleRunning` (`test_cli_loop_lifecycle.py:2028`) and update every `patch("little_loops.cli.loop.lifecycle._process_alive", ...)` call to `patch("little_loops.fsm.persistence._process_alive", ...)` — required because the patched name must match the module where it is looked up at call time.
8. Extend `scripts/tests/test_ll_loop_integration.py:test_list_running_shows_status_info` (L303) with a dead-PID scenario: write a state file with `status="running"` and a non-existent `state.pid`; call `main_loop(["list", "--running"])`; assert the on-disk file flips to `interrupted` and the output no longer shows `[running]` for that entry.
9. Update `docs/reference/API.md` — `list_running_loops()` utility function entry (L4728-4730): add write-side-effect notice.
10. Update `skills/debug-loop-run/SKILL.md` — Step 1 framing (L53-64): note that `ll-loop list --running` now reconciles stale entries in-place, same as `ll-loop status`.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/persistence.py` — host the reconciliation helpers; call inside `list_running_loops()`.
- `scripts/little_loops/cli/loop/lifecycle.py` — adjust import if helpers move.
- `scripts/little_loops/cli/loop/info.py` — no logic change required if reconciliation is inside `list_running_loops()`.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/transport.py` — second call site of `list_running_loops` (inside `_make_seed_callback()._seed()` callback at L583); if reconciliation moves into `list_running_loops()` (option a), transport.py gains the fix for free with no code change; under option (b) it remains stale and would need a separate wiring call.
- `scripts/little_loops/fsm/__init__.py` — re-exports `list_running_loops`; no logic change required.
- `scripts/little_loops/cli/loop/__init__.py` — exposes `cmd_list` as the CLI dispatch entry point; no change required.

### Tests

- `scripts/tests/test_fsm_persistence.py` — new test class or test in `TestListRunningLoops` (if exists) covering the reconciliation side effect.
- `scripts/tests/test_cli_loop_lifecycle.py` — extend `TestReconcileStaleRunning` parity tests to cover the `list` call site.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdList.test_running_shows_status_and_elapsed` (L230) and `TestCmdListRunningJson` (L1542) mock `list_running_loops` at `little_loops.fsm.persistence.list_running_loops`; safe under option (a) since the mock replaces the whole function, bypassing any internal reconciliation. No update required under recommended option (a). Would break under option (b) if `cmd_list()` calls reconciliation after `list_running_loops` returns.
- `scripts/tests/test_ll_loop_integration.py` — `test_list_running_shows_status_info` (L303) exercises the real disk path via `main_loop()`; currently has no dead-PID fixture. Extend with a dead-PID scenario to provide end-to-end coverage of the reconciliation path without mocking.
- `scripts/tests/test_transport.py` — 3 socket transport tests (L309, L325, L340) mock `list_running_loops`; isolation tests for `wire_transports()`, not behavior tests — no update needed.
- **Patch-target risk**: `TestReconcileStaleRunning` in `test_cli_loop_lifecycle.py` patches `little_loops.cli.loop.lifecycle._process_alive` in all 6 methods. If `_reconcile_stale_running()` and `_resolve_live_pid()` move to `persistence.py` under option (a), these patch targets must change to `little_loops.fsm.persistence._process_alive` — audit all 6 before moving the helpers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `TestListRunningLoops` does **not** exist. Add new persistence tests to `TestUtilityFunctions` (line 1124) or `TestAcceptanceCriteria` (line 1324) in `test_fsm_persistence.py`.
- `TestReconcileStaleRunning` at `test_cli_loop_lifecycle.py:2028` exists with 6 methods (`test_reconciles_dead_state_pid_no_pid_file`, `test_reconciles_dead_pid_file`, `test_no_reconcile_live_lock_pid`, etc.). Extend it with a `test_cmd_list_reconciles_same_as_cmd_status` method.
- Dead PID mock pattern (use in step 4): `pytest.MonkeyPatch.context()` with `mp.setattr("little_loops.fsm.persistence._process_alive", lambda pid: False)` — see `test_fsm_persistence.py:1219`.
- On-disk assertion pattern: `written = json.loads(state_file.read_text()); assert written["status"] == "interrupted"; assert "reconciled_at" in written` — see `test_cli_loop_lifecycle.py:2070`.
- Existing `cmd_list --running` tests in `TestCmdListRunningJson` (line 1542) and `TestLoopListRunning` (line 230) in `test_ll_loop_commands.py` mock `list_running_loops` — the new integration test (step 5) must exercise the real disk path without mocking to validate end-to-end agreement.
- If option (a): mock path is `little_loops.fsm.persistence._process_alive`; if option (b): mock path is `little_loops.cli.loop.lifecycle._process_alive`.

### Documentation

- `docs/reference/CLI.md` — `ll-loop list --running` is now a read-path writer.
- `docs/guides/LOOPS_GUIDE.md` — update any "read-only listing" framing.
- `skills/cleanup-loops/SKILL.md` — Step 1 uses `ll-loop list --running --json`; the note about ENH-1669 reconciliation should be moved up so it applies to `list` output too.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `list_running_loops()` entry in the "Utility Functions" section (L4728-4730) describes the function as a pure read. Add a write-side-effect notice matching the note added for `cmd_status` under ENH-1669.
- `skills/debug-loop-run/SKILL.md` — Step 1 (L53-64) uses `ll-loop list --running --json` and frames `list` as a passive listing operation. Update to note that `list --running` now reconciles stale entries in-place (same behavior as `ll-loop status`).

### Configuration

N/A — no configuration files affected.

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

## Resolution

Moved `_read_pid_file`, `_resolve_live_pid`, and `_reconcile_stale_running` from `cli/loop/lifecycle.py` to `fsm/persistence.py`. Called `_reconcile_stale_running` inside `list_running_loops()` for each state-file entry before appending to results. Updated `lifecycle.py` to import the three helpers from `persistence.py`. Updated 5 patch targets in `TestReconcileStaleRunning` to `little_loops.fsm.persistence._process_alive`. Added 3 unit tests to `test_fsm_persistence.py` and 1 integration test to `test_ll_loop_integration.py`.

## Session Log
- `/ll:ready-issue` - 2026-05-27T01:43:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92894725-51ac-4831-9def-bb3295f53006.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/85649679-ddd9-482b-b438-56be54938df4.jsonl`
- `/ll:decide-issue` - 2026-05-27T01:38:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c18a0f69-7238-487d-83bd-d0561eb8cae9.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/496d28d9-55c3-4fec-931f-280dc36878b7.jsonl`
- `/ll:wire-issue` - 2026-05-27T01:35:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ea42eaac-b11c-47e0-92a5-d02d529e4203.jsonl`
- `/ll:refine-issue` - 2026-05-27T01:28:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6605a432-a7c9-4279-a4b1-8298b0f3f87a.jsonl`
- `/ll:format-issue` - 2026-05-26T23:52:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8061561c-1f12-4e02-b1e7-6a9314f79f64.jsonl`

- `/ll:capture-issue` - 2026-05-26T23:19:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0010b6d0-c5ea-42f5-b7da-dacb34c4bb15.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
