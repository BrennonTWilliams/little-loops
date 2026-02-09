---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# BUG-302: ll-sprint subprocess hangs if Claude calls AskUserQuestion in -p mode

## Summary

When `ll-sprint run` invokes Claude Code subprocesses with `-p` (prompt mode), stdin is not connected to a terminal. If Claude decides to call `AskUserQuestion` (e.g., during mismatch handling in `manage_issue`), the subprocess hangs indefinitely until the timeout kills it (default 3600s). There is no mechanism to detect that the process is waiting for input.

## Context

Identified from conversation analyzing how `ll-sprint run` handles commands that may wait for user approval. The `manage_issue.md` prompt instructions still mention `AskUserQuestion` for plan divergence (line 450) and design decisions (line 182), even when `--gates` is not passed. While the default no-gates instructions say to auto-adapt, these are prompt instructions — not enforced code — so Claude may still call `AskUserQuestion`.

## Current Behavior

1. `ll-sprint run` invokes `claude --dangerously-skip-permissions -p <command>`
2. stdin is inherited from the parent (no terminal attached; not explicitly redirected)
3. If Claude calls `AskUserQuestion`, the subprocess blocks waiting for input that will never arrive
4. The only safeguard is the timeout (default 3600s), after which the process is killed
5. No heartbeat, idle detection, or output-activity monitoring exists

## Expected Behavior

The subprocess should either:
- Never encounter `AskUserQuestion` in automation mode (prevented at the prompt level), OR
- Be detected as idle/stuck and terminated early rather than waiting the full timeout

## Steps to Reproduce

1. Create a sprint with an issue that has a complex implementation likely to trigger plan divergence
2. Run `ll-sprint run <sprint-name>`
3. If Claude encounters a mismatch and calls `AskUserQuestion`, the subprocess hangs
4. Wait up to 3600s for the timeout to kill it

## Actual Behavior

Subprocess hangs silently for up to 1 hour with no indication that it's waiting for input.

## Proposed Solution

Multi-pronged approach:
1. Update `manage_issue.md` to explicitly forbid `AskUserQuestion` when `--gates` is not passed (Issue ENH-304)
2. Add idle output detection to `subprocess_utils.py` (Issue ENH-303)
3. Consider passing an environment variable (e.g., `CLAUDE_AUTOMATION_MODE=1`) so skills/commands can detect non-interactive execution

## Impact

- **Priority**: P2
- **Effort**: Medium
- **Risk**: Low — changes are additive safeguards

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents subprocess_utils, ll-sprint flow, and manage_issue lifecycle |
| architecture | docs/API.md | Documents subprocess_utils module and manage_issue command templates |

## Labels

`bug`, `captured`, `automation`, `subprocess`

---

## Status

**Completed** | Created: 2026-02-09 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-09
- **Status**: Completed

### Changes Made
- `commands/manage_issue.md`: Restructured mismatch handling to explicitly forbid AskUserQuestion without --gates flag; scoped design decisions interactive prompts to --gates mode; added automation guard to Default Behavior section
- `scripts/little_loops/subprocess_utils.py`: Added `idle_timeout` parameter to `run_claude_command()` with output inactivity detection — kills process and raises `TimeoutExpired` with `output="idle_timeout"` when no output for configurable period
- `scripts/little_loops/config.py`: Added `idle_timeout_seconds` (default 600) to `AutomationConfig`
- `scripts/little_loops/parallel/types.py`: Added `idle_timeout_per_issue` (default 600) to `ParallelConfig` with serialization support
- `scripts/little_loops/issue_manager.py`: Threaded `idle_timeout` through `run_claude_command()` and `run_with_continuation()` wrappers
- `scripts/little_loops/parallel/worker_pool.py`: Passed `idle_timeout` from `ParallelConfig` to `_run_claude_base()`
- `scripts/tests/test_subprocess_utils.py`: Added 5 tests for idle timeout (trigger, disabled, reset on output, output field, cleanup callback)
- `scripts/tests/test_worker_pool.py`: Updated mock to accept `idle_timeout` kwarg

### Verification Results
- Tests: PASS (2660 passed)
- Lint: PASS
- Types: PASS
