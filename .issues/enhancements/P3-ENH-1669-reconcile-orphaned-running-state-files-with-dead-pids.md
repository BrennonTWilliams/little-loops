---
captured_at: '2026-05-24T04:52:29Z'
discovered_date: '2026-05-24'
discovered_by: capture-issue
status: open
depends_on: [BUG-1668]
relates_to: [ENH-1670]
---

# ENH-1669: Auto-reconcile orphaned `status: running` state files when the PID is dead

## Summary

Foreground loop runs that exit ungracefully (terminal closed, Ctrl-C without graceful shutdown, parent process killed) leave behind `state.json` files claiming `status: running` even though the process is long dead. These orphans persist indefinitely, inflate `ll-loop status <name>` output (e.g. 8 stale `autodev` entries observed), and require manual `cleanup-loops` intervention. The system should auto-flip these to `interrupted` when status detects "pid is dead/absent and persisted status is running".

## Motivation

Today, `ll-loop status autodev` showed 8 instances all reporting `status: running` — every one of them had a dead or absent PID, with no `.pid` file (foreground runs) and a `state.json` whose embedded PID failed `kill -0`. The operator must run `cleanup-loops` or manually edit state files to recover an honest picture. Auto-reconciliation on read closes the loop without requiring a separate maintenance step.

This is the natural follow-on to BUG-1352 (which made `pid` non-null for foreground runs via `.lock` fallback) and BUG-1668 (which makes the `Log:` line honest about run mode). Together they would give a fully accurate status snapshot — but only if the persisted `status` field is also reconciled.

## Current Behavior

- `ll-loop status autodev` lists 8 entries with `status: running` and dead PIDs.
- The PID embedded in `autodev-20260523T145013.state.json` (40692) fails `ps -p 40692`.
- No `.pid` file (foreground), no `.lock` file (released or never written), but `state.json` still claims running.
- The orphan persists until `cleanup-loops` is run, or the user manually rewrites the file.

## Expected Behavior

When status code detects `persisted_status == "running"` AND the process is provably not alive (no `.pid` file → PID-from-state is dead OR `.pid` file exists but its PID is dead AND no `.lock` file holds a live PID), the state should be transparently rewritten to `interrupted` and rendered as such.

Optionally, a `reconciled_at: <iso8601>` field could be added to record when the auto-flip happened, for forensic clarity.

## Proposed Solution

Add a `_reconcile_stale_running(state, running_dir, stem) -> LoopState` helper used by both `_status_single()` and `cmd_status()` multi-instance branch in `lifecycle.py`. The helper:

1. Checks `state.status == "running"`.
2. Resolves the canonical PID using the same logic BUG-1352 added (`.pid` file → `.lock` file → state-embedded PID).
3. Tests liveness with `kill -0` (or equivalent) on the resolved PID.
4. If dead/absent, persists `status: interrupted` (and optionally a `reconciled_at` field) via `StatePersistence.save()`.
5. Returns the (possibly mutated) state to the caller for rendering.

`cmd_stop`, `cmd_resume`, and `_find_instances` should be reviewed to ensure they treat `interrupted` consistently after reconciliation.

## API/Interface

No public CLI interface changes. Two private helpers added to `lifecycle.py`:

```python
def _resolve_live_pid(
    running_dir: Path,
    stem: str,
    state: LoopState,
) -> int | None:
    """Resolve canonical PID via .pid → .lock → state-embedded chain (reuses BUG-1352 logic)."""

def _reconcile_stale_running(
    state: LoopState,
    persistence: StatePersistence,
    running_dir: Path,
    stem: str,
) -> LoopState:
    """Return state with status='interrupted' (+ reconciled_at) when running state has dead PID."""
```

Optional: `reconcile_stale_running: bool` config knob (default `true`) — see §Configuration in Integration Map.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/lifecycle.py` — add helper; call from `_status_single()` and `cmd_status()` multi-instance branch.
- Possibly `scripts/little_loops/cli/loop/_helpers.py` — if `_find_instances` needs to filter or annotate reconciled instances.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/__init__.py` — dispatches `cmd_status`, `cmd_stop`, `cmd_resume`.
- `skills/cleanup-loops/SKILL.md` — currently the manual escape hatch; should be cross-referenced and possibly simplified once auto-reconciliation lands.

### Similar Patterns

- BUG-1352 (done) — `.lock` fallback for PID resolution; the new helper should reuse the same `(.pid, .lock, state)` resolution chain.
- ENH-899 (done) — `_format_relative_time` helper alongside which the new reconciliation helper would live.

### Tests

- `scripts/tests/test_cli_loop_lifecycle.py` — add scenarios: dead PID from state with no `.pid`/`.lock`; dead `.pid` with no `.lock`; live `.lock` (must NOT reconcile); cleanly interrupted (no change).
- `scripts/tests/test_cli_loop_background.py` — ensure background-run live PIDs are never wrongly reconciled.

### Documentation

- `docs/reference/CLI.md` — note that `ll-loop status` may transparently update state files when a running entry is detected as dead.
- `skills/cleanup-loops/SKILL.md` — update to reflect that status now does first-pass reconciliation.

### Configuration

- Optional: a config knob to disable auto-reconciliation for users who want strict read-only semantics from `status`.

## Implementation Steps

1. Add `_resolve_live_pid(running_dir, stem, state) -> int | None` (reusing BUG-1352's chain).
2. Add `_reconcile_stale_running(state, persistence, running_dir, stem) -> LoopState` that writes `status: interrupted` (and `reconciled_at`) when no live PID is found.
3. Call the reconciliation helper at the top of both `_status_single()` and the multi-instance loop in `cmd_status()`.
4. Add tests per the Integration Map.
5. Review `cmd_stop` and `cmd_resume` for assumptions that `status: running` always means a live process; tighten if needed.
6. Update docs and `cleanup-loops` skill.

## Impact

- **Priority**: P3 — quality-of-life and accuracy improvement; not blocking work but compounds across every foreground run.
- **Effort**: Small-to-medium — the resolution chain already exists post-BUG-1352; the new piece is a write on the read path plus careful test coverage to avoid false reconciliations.
- **Risk**: Medium — `status` becomes a writer instead of a pure reader. Must guarantee no false-positive reconciliations of live runs (especially around the race where a process has just spawned but hasn't yet written its `.pid`).
- **Breaking Change**: No (state transition that was previously expected to happen manually now happens automatically).

## Scope Boundaries

- Reconciliation triggers from `ll-loop status` only. Other read-only commands (`ll-loop list`, `ll-loop show`) are out of scope for this issue.
- Background-mode runs with a live `.pid` or `.lock` are never reconciled.

## Success Metrics

- **Orphan clearance**: `ll-loop status autodev` shows 0 entries with `status: running` and dead PIDs after auto-reconciliation (baseline: 8 stale entries observed).
- **No false positives**: Zero live-process runs wrongly flipped to `interrupted` across foreground and background run scenarios in the test suite.
- **Idempotency**: Two consecutive `ll-loop status` calls on the same instance set produce identical output.
- **`cleanup-loops` redundancy reduction**: Orphan handling in `cleanup-loops` can be simplified or removed after this lands.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `cli`, `state-reconciliation`, `captured`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:format-issue` - 2026-05-24T05:08:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6eeae06-e4aa-4cf4-b5de-f799be9249c8.jsonl`
- `/ll:capture-issue` - 2026-05-24T04:52:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f605fdcc-8000-4585-8dc4-835fc0020291.jsonl`

---

## Status

**Open** | Created: 2026-05-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1670 (optional log capture for foreground runs) addresses the same foreground-run observability gap from a complementary angle — state accuracy (this issue) vs. log artifact (ENH-1670). Both depend on BUG-1668 and form a coherent foreground-run improvement cluster; consider implementing all three in the same sprint.
