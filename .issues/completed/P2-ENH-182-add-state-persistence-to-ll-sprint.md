---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-182: Add state persistence to ll-sprint

## Summary

ll-sprint lacks state persistence, making it impossible to resume interrupted sprints. This is a significant gap compared to ll-auto and ll-parallel which both have robust state management.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Consistency Matrix shows ll-sprint has "❌ None" for State Management (40% score)
- Listed as "High Priority" standardization opportunity
- ll-auto uses `StateManager` with `.auto-manage-state.json`
- ll-parallel uses `OrchestratorState` with `.parallel-manage-state.json`

## Current Behavior

When ll-sprint is interrupted (Ctrl+C, system crash, timeout), all progress is lost. The next run starts from scratch with no knowledge of which issues in which waves were already completed.

## Expected Behavior

- Sprint execution state persists to `.sprint-state.json` or similar
- `--resume` flag allows continuing interrupted sprints
- Completed waves/issues are tracked and skipped on resume
- State file cleaned up on successful completion

## Proposed Solution

1. Create `SprintState` dataclass following the `ProcessingState` pattern from ll-auto:

```python
@dataclass
class SprintState:
    sprint_name: str
    current_wave: int
    completed_waves: list[int]
    completed_issues: list[str]
    failed_issues: list[str]
    started_at: str
    last_updated: str
```

2. Add state persistence methods to `sprint.py`:
   - `save_state()` - Write state after each issue/wave completion
   - `load_state()` - Read state on startup with `--resume`
   - `clear_state()` - Remove state file on successful completion

3. Update CLI to add `--resume/-r` flag in `cli.py:1284-1336`

4. Modify `_cmd_sprint_run()` to check state and skip completed work

## Files to Modify

- `scripts/little_loops/sprint.py` - Add SprintState dataclass and persistence
- `scripts/little_loops/cli.py:1308-1320` - Add --resume argument to run subparser
- `scripts/little_loops/cli.py:1619-1741` - Integrate state into `_cmd_sprint_run()` logic

## Impact

- **Priority**: P2 (High - core functionality gap)
- **Effort**: Medium (follow existing patterns)
- **Risk**: Low (well-established patterns to follow)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| reference | scripts/little_loops/state.py:76 | StateManager pattern to follow |
| reference | scripts/little_loops/parallel/types.py:176 | OrchestratorState pattern |
| audit | docs/CLI-TOOLS-AUDIT.md | Source of this issue |

## Labels

`enhancement`, `ll-sprint`, `consistency`, `captured`

---

## Verification Notes

**Verified: 2026-01-29** (updated by ready_issue)

- Confirmed: No `SprintState` or state persistence exists in sprint code
- ll-auto uses `StateManager` at `state.py:76` (not issue_manager.py)
- ll-parallel uses `OrchestratorState` in `parallel/types.py:176`
- Sprint run function is at `cli.py:1619-1741`
- Run subparser definition is at `cli.py:1308-1320`
- Issue description remains accurate

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sprint.py`: Added `SprintState` dataclass with `to_dict()` and `from_dict()` methods for JSON serialization
- `scripts/little_loops/cli.py`: Added `--resume/-r` flag to sprint run subparser
- `scripts/little_loops/cli.py`: Added helper functions `_get_sprint_state_file()`, `_load_sprint_state()`, `_save_sprint_state()`, `_cleanup_sprint_state()`
- `scripts/little_loops/cli.py`: Updated `_cmd_sprint_run()` to track state, skip completed waves on resume, and clean up on success
- `scripts/tests/test_sprint.py`: Added `TestSprintState` test class with 7 tests

### Verification Results
- Tests: PASS (1879 passed, 1 pre-existing unrelated failure)
- Lint: PASS
- Types: PASS

### Features Implemented
- State persists to `.sprint-state.json` after each wave completion
- `--resume/-r` flag loads existing state and continues from the first incomplete wave
- State file is cleaned up on successful completion (no failures)
- Mismatch detection when resuming with a different sprint name

---

## Status

**Completed** | Created: 2026-01-29 | Verified: 2026-01-29 | Completed: 2026-01-29 | Priority: P2
