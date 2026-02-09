# BUG-302: ll-sprint subprocess hangs on AskUserQuestion - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-302-ll-sprint-subprocess-hangs-on-askuserquestion.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

When `ll-sprint run` invokes Claude Code subprocesses with `-p` (prompt mode), if Claude calls `AskUserQuestion`, the subprocess hangs indefinitely because stdin isn't connected to a terminal. The only safeguard is the wall-clock timeout (default 3600s).

### Key Discoveries
- `subprocess_utils.py:89-97` — `Popen` does not pipe stdin; child inherits parent's (no terminal in automation)
- `subprocess_utils.py:112-119` — Only wall-clock timeout exists; no idle output tracking
- `manage_issue.md:450-456` — `AskUserQuestion` referenced in mismatch handling without `--gates` scoping
- `manage_issue.md:178-182` — Design decisions section says "Present options to user" with no automation guard
- Neither `issue_manager.py:473` nor `worker_pool.py:360` ever append `--gates` to the command

## Desired End State

1. `manage_issue.md` explicitly forbids `AskUserQuestion` when `--gates` is not passed
2. `subprocess_utils.py` supports an `idle_timeout` parameter that kills stuck processes based on output inactivity
3. Callers (`issue_manager.py`, `worker_pool.py`) pass a sensible `idle_timeout` default
4. Tests cover idle timeout behavior

### How to Verify
- `manage_issue.md` contains explicit prohibition of `AskUserQuestion` in no-gates mode
- `python -m pytest scripts/tests/test_subprocess_utils.py -v` — idle timeout tests pass
- `ruff check scripts/` — no lint issues
- `python -m mypy scripts/little_loops/` — type checks pass

## What We're NOT Doing

- Not adding `CLAUDE_AUTOMATION_MODE` env var — deferred; prompt-level fix + idle detection is sufficient
- Not changing other command templates — only `manage_issue.md` is in scope
- Not adding automatic retry after idle timeout — leave to callers
- Not changing the `--gates` flag parsing logic — it's prompt-level, which is fine

## Problem Analysis

Two root causes:
1. **Prompt gap**: `manage_issue.md` mentions `AskUserQuestion` in mismatch handling (line 450) without scoping it to `--gates` mode. The no-gates fallback (line 457) reads as step 3 in a sequential list, not as a replacement for step 2.
2. **No idle detection**: `run_claude_command()` only checks wall-clock timeout. A process that hangs (producing no output) wastes up to 1 hour before being killed.

## Solution Approach

1. Fix the prompt (prevent the hang) — restructure `manage_issue.md` mismatch handling to explicitly forbid `AskUserQuestion` when `--gates` is not passed
2. Add defense in depth (detect the hang) — add `idle_timeout` parameter to `run_claude_command()` that kills processes with no output activity
3. Wire up callers — pass `idle_timeout` from `issue_manager.py` and `worker_pool.py`

## Code Reuse & Integration

- **Reusable existing code**: `subprocess_utils.py:106-148` selector loop — extend with `last_output_time` tracking
- **Patterns to follow**: Existing timeout check at `subprocess_utils.py:116-119` — idle timeout mirrors this exactly
- **Test patterns**: `test_subprocess_utils.py:558-625` — reuse mocked time approach for idle timeout tests
- **New code justification**: `idle_timeout` parameter and `last_output_time` tracking is genuinely new; no existing idle detection exists anywhere

## Implementation Phases

### Phase 1: Update manage_issue.md prompt instructions

#### Overview
Restructure the mismatch handling section to make `AskUserQuestion` explicitly `--gates`-only, and add a clear automation guard to the "No Open Questions" section.

#### Changes Required

**File**: `commands/manage_issue.md`

1. Add automation guard to the "Default Behavior" section (after line 429):
   - Add: `- Do NOT use AskUserQuestion or any interactive tools — all decisions must be made autonomously`

2. Restructure mismatch handling (lines 440-465) to use conditional branching:
   - Change step 2 to be explicitly scoped to `--gates` mode: "**With --gates flag**: Use the AskUserQuestion tool..."
   - Change step 3 to: "**Without --gates flag (default)**: ..."
   - This makes the two paths clearly mutually exclusive

3. Update "No Open Questions Rule" (line 182):
   - Change "Present options to user, get explicit approval" to scope it: "Present options to user, get explicit approval **(only with --gates flag; otherwise make the best autonomous decision and document the rationale)**"

#### Success Criteria
- [x] `manage_issue.md` contains explicit `AskUserQuestion` prohibition in no-gates mode
- [x] Mismatch handling uses clear conditional branching (with/without `--gates`)
- [x] No Open Questions section scopes interactive prompts

### Phase 2: Add idle_timeout to subprocess_utils.py

#### Overview
Add `idle_timeout` parameter to `run_claude_command()` that tracks when the last output line was received and kills the process if it goes silent for too long.

#### Changes Required

**File**: `scripts/little_loops/subprocess_utils.py`

1. Add `idle_timeout` parameter to `run_claude_command()` signature (default: 0 = disabled)
2. Initialize `last_output_time = time.time()` alongside `start_time`
3. Update `last_output_time` whenever a line is successfully read (inside the `for key, _ in ready:` loop)
4. Add idle timeout check alongside the existing timeout check:
   ```python
   if idle_timeout and (time.time() - last_output_time) > idle_timeout:
       process.kill()
       process.wait()
       raise subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")
   ```
   Note: We reuse `TimeoutExpired` with the `output` field set to `"idle_timeout"` to distinguish it from a regular timeout, avoiding a new exception class.

#### Success Criteria
- [ ] `idle_timeout` parameter added with default 0 (disabled)
- [ ] `last_output_time` tracked and updated on each line read
- [ ] Idle timeout kills process and raises `TimeoutExpired`
- [ ] Existing timeout behavior unaffected
- [ ] Tests pass: `python -m pytest scripts/tests/test_subprocess_utils.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

### Phase 3: Wire up callers with idle_timeout

#### Overview
Pass `idle_timeout` from the two calling sites (`issue_manager.py` and `worker_pool.py`) to `run_claude_command()`.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`
- `run_claude_command()` wrapper (line 91): Add `idle_timeout` parameter, pass through to `_run_claude_base()`

**File**: `scripts/little_loops/parallel/worker_pool.py`
- `_run_claude_command()` (line 642): Pass `idle_timeout` to `_run_claude_base()`
- Use `self.parallel_config.timeout_per_issue // 6` as the idle timeout (e.g., 600s for 3600s timeout) or a sensible default like 600

**File**: `scripts/little_loops/parallel/types.py`
- Add `idle_timeout_per_issue: int = 600` to `ParallelConfig`

#### Success Criteria
- [ ] `issue_manager.py` passes `idle_timeout` through
- [ ] `worker_pool.py` passes `idle_timeout` from config
- [ ] `ParallelConfig` has `idle_timeout_per_issue` field
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`

### Phase 4: Add tests for idle timeout

#### Overview
Add test cases for the idle timeout feature, following existing timeout test patterns.

#### Changes Required

**File**: `scripts/tests/test_subprocess_utils.py`

Add new test class `TestRunClaudeCommandIdleTimeout`:
1. `test_raises_timeout_on_idle` — Process produces output then goes silent; idle timeout triggers
2. `test_idle_timeout_zero_means_disabled` — `idle_timeout=0` never triggers idle timeout
3. `test_idle_timeout_resets_on_output` — Output activity resets the idle timer
4. `test_idle_timeout_output_field_set` — The `TimeoutExpired` exception has `output="idle_timeout"`
5. `test_on_process_end_called_on_idle_timeout` — Lifecycle callback fires

#### Success Criteria
- [ ] All idle timeout tests pass
- [ ] Tests cover: trigger, disabled, reset, distinction from regular timeout, cleanup
- [ ] `python -m pytest scripts/tests/test_subprocess_utils.py -v`

## Testing Strategy

### Unit Tests
- Idle timeout triggers after configurable silence period
- Idle timeout resets when output is received
- Idle timeout disabled when set to 0
- Regular timeout still works alongside idle timeout
- Process cleanup (kill + wait) on idle timeout
- Lifecycle callbacks fire on idle timeout

### Integration Tests
- Callers pass idle_timeout correctly (covered by existing caller tests if we verify parameters)

## References

- Original issue: `.issues/bugs/P2-BUG-302-ll-sprint-subprocess-hangs-on-askuserquestion.md`
- Related: `.issues/enhancements/P3-ENH-303-add-idle-detection-for-ll-sprint-subprocesses.md`
- Related: `.issues/enhancements/P3-ENH-304-clarify-manage-issue-automation-mode-no-askuserquestion.md`
- Selector loop pattern: `subprocess_utils.py:106-148`
- Timeout test pattern: `test_subprocess_utils.py:558-625`
