---
discovered_date: "2026-04-21"
discovered_by: planning-discussion
confidence_score: 85
size: Small
depends_on: FEAT-1232, FEAT-1233
status: deferred
deferred_date: "2026-04-21"
deferred_reason: low-value
---

# FEAT-1234: Tests for `ll-loop parallel`

## Summary

Add unit and integration tests for the `ll-loop parallel` command covering: pre-flight scope conflict detection, subprocess lifecycle management, signal propagation, exit code aggregation, and status display polling.

## Deferral Notes

Deferred alongside FEAT-1232 and FEAT-1233. Tests have no standalone value without the feature being implemented.

## Acceptance Criteria

### Unit tests (`scripts/tests/test_ll_loop_parallel.py`)

**TestScopeConflictDetection**
- [ ] `test_no_conflict_non_overlapping_scopes` — loops with `scope: ["src/"]` and `scope: ["tests/"]` pass pre-flight
- [ ] `test_conflict_detected_overlapping_scopes` — loops both using `scope: ["."]` trigger conflict error before any subprocess starts
- [ ] `test_conflict_detected_partial_overlap` — `scope: ["src/", "docs/"]` vs `scope: ["docs/"]` is flagged

**TestParallelLauncher** (mocked subprocesses)
- [ ] `test_all_succeed_exit_zero` — two mocked loops both exit 0; launcher exits 0
- [ ] `test_one_fails_exit_one` — one loop exits 0, one exits 1; launcher exits 1
- [ ] `test_loop_not_found_exits_before_start` — referencing a nonexistent loop name exits 1 without starting others
- [ ] `test_pid_file_poll_detects_completion` — completion detected when PID file is removed

**TestSignalPropagation** (mocked)
- [ ] `test_sigint_sends_sigterm_to_children` — SIGINT to launcher sends SIGTERM to all child PIDs
- [ ] `test_second_sigint_sends_sigkill` — second SIGINT escalates to SIGKILL

**TestStatusDisplay** (unit)
- [ ] `test_display_reads_state_files` — given mock state files, display table reflects current_state and iteration
- [ ] `test_display_handles_missing_state_file` — missing state file for a loop shows "starting..." without crashing
- [ ] `test_display_non_tty_no_escape_codes` — non-TTY output contains no ANSI cursor movement sequences

### Integration test (`@pytest.mark.integration`)
- [ ] `test_two_loops_run_concurrently` — start two loops using `--no-llm` toy fixtures with non-overlapping scopes, assert both PID files exist simultaneously (process overlap), both complete, launcher exits 0

## Implementation Notes

- Fixture loops for integration test: use existing `scripts/tests/fixtures/fsm/` YAML fixtures with `--no-llm`; pick two with distinct `scope:` fields or add a `scope:` field to existing fixtures
- Mock subprocess spawning with `unittest.mock.patch("subprocess.Popen")`
- PID file simulation: write temp PID files with a known PID, then remove them to simulate loop completion
- Signal tests: use `unittest.mock.patch("os.kill")` to capture calls without sending real signals
