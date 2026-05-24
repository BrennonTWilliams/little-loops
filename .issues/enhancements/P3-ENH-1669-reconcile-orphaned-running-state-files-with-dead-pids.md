---
captured_at: '2026-05-24T04:52:29Z'
discovered_date: '2026-05-24'
discovered_by: capture-issue
status: open
depends_on:
- BUG-1668
relates_to:
- ENH-1670
- ENH-1399
decision_needed: false
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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

A `reconciled_at: <iso8601>` field will be written to record when the auto-flip happened, for forensic clarity.

## Proposed Solution

Add a `_reconcile_stale_running(state, running_dir, stem) -> LoopState` helper used by both `_status_single()` and `cmd_status()` multi-instance branch in `lifecycle.py`. The helper:

1. Checks `state.status == "running"`.
2. Resolves the canonical PID using the same logic BUG-1352 added (`.pid` file → `.lock` file → state-embedded PID).
3. Tests liveness with `kill -0` (or equivalent) on the resolved PID.
4. If dead/absent, persists `status: interrupted` and `reconciled_at: <iso8601>` via `StatePersistence.save_state()`.
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

No config knob — auto-reconciliation is unconditional (decided: knob is YAGNI, nobody has requested strict read-only `status` semantics).

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/lifecycle.py` — add helper; call from `_status_single()` and `cmd_status()` multi-instance branch.
- Possibly `scripts/little_loops/cli/loop/_helpers.py` — if `_find_instances` needs to filter or annotate reconciled instances.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — if `reconciled_at` is used: add `reconciled_at: datetime | None = None` to `LoopState`; update `to_dict()` (omit when None) and `from_dict()` (`data.get("reconciled_at")`) following the `active_sub_loop` field pattern [Agent 2 finding]
- `config-schema.json` — add `"reconcile_stale_running"` boolean property to `"loops"` object (`"additionalProperties": false` requires it) if optional config knob is implemented [Agent 2 finding]
- `scripts/little_loops/config/features.py` — add `reconcile_stale_running: bool = True` to `LoopsConfig` dataclass and `from_dict()` if config knob is implemented [Agent 2 finding]
- `scripts/little_loops/config/core.py` — include `reconcile_stale_running` in `BRConfig.to_dict()` `"loops"` block if config knob is implemented [Agent 2 finding]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/__init__.py` — dispatches `cmd_status`, `cmd_stop`, `cmd_resume`.
- `skills/cleanup-loops/SKILL.md` — currently the manual escape hatch; should be cross-referenced and possibly simplified once auto-reconciliation lands.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — calls `_reconcile_stale_runs()` at startup (line 208); provides the glob/load/check/persist pattern precedent but requires no changes from ENH-1669 [Agent 1 finding]
- `scripts/little_loops/transport.py` — `_seed()` at line ~555 calls `state.to_dict()` on all running instances to build `state_change` socket events; after ENH-1669, reconciled instances will include `reconciled_at` in these events. No code change required (the key is additive and consumers use `data.get()`) but confirms the field must be omitted from `to_dict()` when `None` [Second wiring pass finding]

### Similar Patterns

- BUG-1352 (done) — `.lock` fallback for PID resolution; the new helper should reuse the same `(.pid, .lock, state)` resolution chain.
- ENH-899 (done) — `_format_relative_time` helper alongside which the new reconciliation helper would live.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction — `_find_instances()` location**: The issue references `_helpers.py` for `_find_instances`, but the function is defined in `scripts/little_loops/fsm/persistence.py` (`_find_instances(loop_name, running_dir) -> list[tuple[str | None, LoopState]]`). `_helpers.py` does not need modification for the core reconciliation.

**Correction — method name**: `StatePersistence` exposes `save_state(state: LoopState) -> None` (not `save()`). Mutate `state.status = "interrupted"` then call `persistence.save_state(state)`. The method atomically writes via `os.replace`.

**`StatePersistence` constructor**: `StatePersistence(loop_name, loops_dir, instance_id=instance_id)` — where `instance_id` is the per-run stem (e.g. `"autodev-20260523T145013"`) returned by `_find_instances`.

**`_process_alive()` import**: Already imported in `lifecycle.py` as `from little_loops.fsm.concurrency import _process_alive`. Handles `EPERM` correctly (returns `True` — process exists, no kill permission) vs `ESRCH` (returns `False` — no such process).

**Third PID fallback (`state.pid`)**: `LoopState` carries a `pid: int | None` field written by `PersistentExecutor` via `pid=os.getpid()` in `cmd_run`. For foreground runs that crash, `atexit` removes `.pid` and `LockManager.release()` removes `.lock`, leaving `state.pid` as the only surviving PID. The existing BUG-1352 chain (`.pid` → `.lock`) never falls back to `state.pid` — this is the critical third link that ENH-1669 must add.

**Direct precedent — `_reconcile_stale_runs()`**: `scripts/little_loops/fsm/persistence.py` already contains `_reconcile_stale_runs(loops_dir)` (called at startup from `run.py`). It archives dead-PID entries on the `.pid` file only. ENH-1669's helper is the read-path complement: same liveness test, different outcome (write `interrupted` in-place instead of archive). Study this function for the glob/load/check/persist pattern.

**`cmd_resume()` — no changes needed**: `RESUMABLE_STATUSES = frozenset({"running", "awaiting_continuation", "interrupted"})`. After reconciliation flips `running` → `interrupted`, `cmd_resume` already accepts the entry. No filtering changes required.

**`cmd_stop()` — review scope is narrow**: `cmd_stop` filters `running_instances = [(iid, s) for iid, s in instances if s.status == "running"]`. Entries reconciled by a prior `status` call will already be `interrupted` and thus excluded from this filter — correct behavior. The review called for in step 5 can be scoped to verifying this assumption holds.

**Read-path writer precedent**: `_is_earliest_waiter()` in `scripts/little_loops/cli/loop/_helpers.py` already removes dead-PID queue entries as a side-effect of being called (read-path writer). `LockManager.find_conflict()` in `scripts/little_loops/fsm/concurrency.py` does the same for lock files. ENH-1669 follows the same established pattern.

### Tests

- `scripts/tests/test_cli_loop_lifecycle.py` — add scenarios: dead PID from state with no `.pid`/`.lock`; dead `.pid` with no `.lock`; live `.lock` (must NOT reconcile); cleanly interrupted (no change).
- `scripts/tests/test_cli_loop_background.py` — ensure background-run live PIDs are never wrongly reconciled.

_Wiring pass added by `/ll:wire-issue`:_

**Tests pre-fixed (2026-05-24) — applied before implementation begins:**
- ~~`TestCmdStatus.test_status_prints_state` in `test_cli_loop_lifecycle.py`~~ — **DONE**: added `mock_state.pid = None` inline; no PID file → reconciliation skips.
- ~~`TestCmdStatusLogFile._make_state` in `test_cli_loop_lifecycle.py`~~ — **DONE**: added `mock_state.pid = None` to helper; 7 tests now safe.
- ~~`TestCmdStatusMultiInstance` in `test_cli_loop_lifecycle.py`~~ — **DONE**: added `state1.pid = None` / `state2.pid = None` to both test bodies.
- ~~`TestCmdStatusWithPid.test_status_shows_stale_pid` in `test_cli_loop_background.py`~~ — **DONE**: patched `StatePersistence.save_state` (decided over `to_dict.return_value` — test is about display behavior, not persistence; "stale" assertion still holds post-reconciliation since `_status_single` checks `.pid` file again for display).
- ~~`TestCmdStatusWithPid.test_status_without_pid_file` in `test_cli_loop_background.py`~~ — **DONE**: added `mock_state.pid = None`; no PID anywhere → reconciliation skips entirely.

**New tests to write:**
- `scripts/tests/test_fsm_persistence.py` — add `test_reconciled_at_field_roundtrip`, `test_reconciled_at_defaults_to_none`, `test_reconciled_at_omitted_when_none` (follow `test_active_sub_loop_field_roundtrip` pattern at line 89) [Agent 3 finding]

_Second refinement pass — `/ll:refine-issue`:_
- ~~**`TestCmdStatusWithPid.test_status_shows_stale_pid` fix decision**: Chose option (b) — patch `StatePersistence.save_state`. Reasoning: test is about display behavior; `"stale"` assertion holds because `_status_single` re-checks the `.pid` file for display independently of reconciliation; patching `save_state` keeps test intent clear without adding serialization boilerplate. **Resolved 2026-05-24.**~~
- `TestReconcileStaleRuns.test_missing_pid_file_running_left_alone` in `test_fsm_persistence.py` (confirmed) — when `state.pid` is `None` and no `.pid` file exists, startup sweep leaves the orphan alone; this is exactly the case ENH-1669 must catch on the read path via the `state.pid` fallback.
- `save_state()` in `persistence.py` mutates `state.updated_at` to `_iso_now()` before writing — reconciled state files will have a fresh `updated_at` timestamp; account for this in any test assertions that verify state content post-reconciliation.
- `TestFindInstances._write_state()` at line 1658 in `test_cli_loop_lifecycle.py` — a second real-`LoopState` writer helper in that file; model new reconcile tests after `TestCmdStatusLockFilePid` pattern (patch `_find_instances`, write real files) rather than this helper.

### Documentation

- `docs/reference/CLI.md` — note that `ll-loop status` may transparently update state files when a running entry is detected as dead.
- `skills/cleanup-loops/SKILL.md` — update to reflect that status now does first-pass reconciliation.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `LoopState` field list needs `reconciled_at` if field is added (existing stub already omits several fields) [Agent 2 finding]
- ~~`docs/reference/CONFIGURATION.md`~~ — config knob not implemented; no docs update needed.
- `skills/debug-loop-run/SKILL.md` — Step 2 calls `ll-loop status` which becomes a writer; soft coupling — behaviorally compatible (already accepts `interrupted`), but description implies status is read-only [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md` — same soft coupling as `debug-loop-run/SKILL.md` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — multiple sections present `ll-loop status` as a passive read command (Monitor section, Background loop management at lines 1706–1712, quick-reference table at line 2511, troubleshooting table at line 3137); add one-line note that `ll-loop status` may transparently rewrite orphaned `running` state files [Second wiring pass finding]

### Configuration

- No config knob. Auto-reconciliation is unconditional. (Decided 2026-05-24: knob is YAGNI — `status` as a read-path writer is established pattern in this codebase.)

## Implementation Steps

1. Add `_resolve_live_pid(running_dir, stem, state) -> int | None` to `scripts/little_loops/cli/loop/lifecycle.py` — chain: `_read_pid_file(running_dir / f"{stem}.pid")` → parse `running_dir / f"{stem}.lock"` → `state.pid`. Return first non-None PID. Consolidates the three inline duplications of BUG-1352 logic in `_status_single()` and `cmd_status()`.
2. Add `_reconcile_stale_running(state, persistence, running_dir, stem) -> LoopState` to `lifecycle.py` — check `state.status == "running"`, call `_resolve_live_pid()`, call `_process_alive(pid)` (already imported from `little_loops.fsm.concurrency`). If dead/absent: `state.status = "interrupted"` and `state.reconciled_at = datetime.now(UTC).isoformat()`, then `persistence.save_state(state)`. Return `state`. Model on `cmd_stop`'s "mutate + save_state" idiom (lines ~344–355 of `lifecycle.py`).
3. Call `_reconcile_stale_running()` at the top of `_status_single()` (before any print) and in the multi-instance loop of `cmd_status()` (before both JSON and human-readable branches). Construct `persistence = StatePersistence(state.loop_name, loops_dir, instance_id=instance_id)` for each call.
4. Add tests to `scripts/tests/test_cli_loop_lifecycle.py` modeled on `TestCmdStatusLockFilePid` class — mock `_find_instances`, write real `state.json` with embedded PID, patch `_process_alive`. Cover: (a) dead `state.pid`, no `.pid`/`.lock` → flips to `interrupted`; (b) dead `.pid` file, no `.lock` → flips; (c) live `.lock` PID → must NOT reconcile; (d) cleanly `interrupted` status → no change. Add to `scripts/tests/test_cli_loop_background.py`: live background PID → no reconciliation.
5. Review `cmd_stop`: its primary filter already uses `s.status == "running"`, so reconciled entries become `interrupted` and are excluded — no code change needed. Verify the secondary `.lock`-holder path is unaffected.
6. `cmd_resume` needs no changes — `interrupted` is already in `RESUMABLE_STATUSES`.
7. Update `docs/reference/CLI.md` to note `ll-loop status` may transparently update state files. Update `skills/cleanup-loops/SKILL.md` to reflect first-pass reconciliation now happens on `status`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/fsm/persistence.py` — add `reconciled_at: datetime | None = None` to `LoopState`, guard `to_dict()` with `if self.reconciled_at is not None`, add `data.get("reconciled_at")` to `from_dict()` (follow `active_sub_loop` pattern)
9. ~~Fix at-risk tests: add `mock_state.pid = None` to `_make_state()` helpers in `TestCmdStatus`, `TestCmdStatusLogFile`, and `TestCmdStatusMultiInstance` in `test_cli_loop_lifecycle.py`~~ — **DONE 2026-05-24**
10. ~~`TestCmdStatusWithPid.test_status_shows_stale_pid` in `test_cli_loop_background.py` — patch `StatePersistence.save_state`~~ — **DONE 2026-05-24**
11. ~~`TestCmdStatusWithPid.test_status_without_pid_file` in `test_cli_loop_background.py` — add `mock_state.pid = None`~~ — **DONE 2026-05-24**
12. Update `docs/guides/LOOPS_GUIDE.md` — add a one-line note in the Monitor section and Background loop management section that `ll-loop status` may transparently rewrite orphaned `running` state files [Second wiring pass finding]
~~13. Config knob — not implemented.~~ (Decided 2026-05-24: YAGNI.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_read_pid_file(pid_file: Path) -> int | None` already exists in `lifecycle.py` — reuse it in `_resolve_live_pid`.
- `_process_alive` import already present in `lifecycle.py`: `from little_loops.fsm.concurrency import _process_alive`.
- `StatePersistence` constructor: `StatePersistence(loop_name, loops_dir, instance_id=instance_id)` — `instance_id` is the `str | None` from `_find_instances()` return value (in `persistence.py`).
- `save_state` atomically writes via `os.replace`; safe to call mid-`status` command.
- `save_state()` also mutates `state.updated_at` to `_iso_now()` before serializing — reconciled entries will have a fresh timestamp in the written file.
- Test helper to model: `TestReconcileStaleRuns._write_state()` in `test_fsm_persistence.py` for minimal `LoopState` construction with `state.pid` set.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-24_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **4 pre-identified test breakages** — `TestCmdStatus`, `TestCmdStatusLogFile`, `TestCmdStatusMultiInstance`, and `TestCmdStatusWithPid` all have MagicMock states with uncontrolled `.pid` attributes; reconciliation chain reaches `state.pid` and raises `TypeError`. Fix `_make_state()` helpers before or alongside the core implementation.
- **Optional scope decisions add files** — if `reconciled_at` field is included, `persistence.py` + API docs expand the surface; if config knob is included, 3 more files (config-schema, features.py, core.py). Decide at implementation start to avoid mid-task scope creep.
- **Status becomes a writer** — introduces a narrow race window where a just-spawned process with no `.pid` yet could be wrongly reconciled. Add a "just-started, no .pid yet" regression test modeled on `TestCmdStatusLockFilePid`.

## Session Log
- `pre-impl test fixes + save_state decision` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b86d74a1-029b-46f2-a7b9-03e998a02e0f.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b86d74a1-029b-46f2-a7b9-03e998a02e0f.jsonl`
- `/ll:wire-issue` - 2026-05-24T13:40:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3464582d-1db1-46a9-b80a-7ca32c3d5cd4.jsonl`
- `/ll:refine-issue` - 2026-05-24T13:31:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73097563-3366-47c7-ad17-c2ae7263a6e6.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/765fa3c6-1a05-4cb7-8170-c01366684b4e.jsonl`
- `/ll:wire-issue` - 2026-05-24T13:18:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/765fa3c6-1a05-4cb7-8170-c01366684b4e.jsonl`
- `/ll:refine-issue` - 2026-05-24T13:12:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5e8e93a-1535-42f0-83c5-a8a802d567b9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:format-issue` - 2026-05-24T05:08:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6eeae06-e4aa-4cf4-b5de-f799be9249c8.jsonl`
- `/ll:capture-issue` - 2026-05-24T04:52:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f605fdcc-8000-4585-8dc4-835fc0020291.jsonl`

---

## Status

**Open** | Created: 2026-05-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1670 (optional log capture for foreground runs) addresses the same foreground-run observability gap from a complementary angle — state accuracy (this issue) vs. log artifact (ENH-1670). Both depend on BUG-1668 and form a coherent foreground-run improvement cluster; consider implementing all three in the same sprint.
