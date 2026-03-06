---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 96
outcome_confidence: 87
---

# BUG-605: Signal-shutdown exit code `1` indistinguishable from genuine failure

## Summary

`run_foreground` and `cmd_resume` return exit code `0` only for `terminated_by == "terminal"` and `1` for everything else — including `"signal"` (graceful user-initiated Ctrl-C). Scripts and CI pipelines cannot distinguish between a user-interrupted loop and a genuine failure.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 403 (updated from 350 at scan commit: c010880)
- **Anchor**: `in function run_foreground()`, final return
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/_helpers.py#L350)
- **Code**:
```python
return 0 if result.terminated_by == "terminal" else 1
```

Same pattern at `lifecycle.py:193` in `cmd_resume`.

## Current Behavior

Graceful signal shutdown returns exit code `1`, same as timeout or max_iterations exceeded.

## Expected Behavior

Different termination reasons should map to distinct exit codes (e.g., `0` for terminal, `0` for signal, `1` for max_iterations/timeout, `2` for error).

## Steps to Reproduce

1. Run a loop: `ll-loop run <loop>`
2. Press Ctrl-C to trigger a graceful signal shutdown
3. Check exit code: `echo $?` — returns `1`
4. Compare with a loop that exceeds `max_iterations` — also returns `1`
5. CI pipeline cannot distinguish user interruption from genuine failure

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in function run_foreground()`, final return
- **Cause**: The binary `0 if result.terminated_by == "terminal" else 1` mapping was written when only two termination cases were expected. As `terminated_by` values expanded (`"signal"`, `"max_iterations"`, `"timeout"`, `"handoff"`), no corresponding exit code differentiation was added.

## Motivation

CI pipelines and wrapper scripts that call `ll-loop run` or `ll-loop resume` cannot distinguish a deliberate Ctrl-C from an error condition:

- **CI false failures**: A user pressing Ctrl-C to stop a manual run marks the pipeline step as failed
- **Script ambiguity**: Wrapper scripts that check `if [ $? -ne 0 ]` treat signal-interrupted loops as errors, triggering unintended error-handling paths
- **Two affected sites**: Both `run_foreground` (`_helpers.py:350`) and `cmd_resume` (`lifecycle.py:188`) share this binary mapping, so neither foreground nor resumed loops can be correctly classified

## Proposed Solution

Map `terminated_by` values to meaningful exit codes:
```python
EXIT_CODES = {"terminal": 0, "signal": 0, "max_iterations": 1, "timeout": 1, "handoff": 0}
return EXIT_CODES.get(result.terminated_by, 1)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — replace binary exit code at line 403 with `EXIT_CODES` mapping
- `scripts/little_loops/cli/loop/lifecycle.py` — replace binary exit code at line 193 in `cmd_resume` with same mapping

### Dependent Files (Callers/Importers)
- Any shell scripts or CI configs calling `ll-loop run` or `ll-loop resume` — will observe changed exit code for `"signal"` termination (0 instead of 1)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — add tests asserting exit code for each `terminated_by` value

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Define `EXIT_CODES` dict in `_helpers.py` near `run_foreground`
2. Replace `return 0 if result.terminated_by == "terminal" else 1` at line 350 with `return EXIT_CODES.get(result.terminated_by, 1)`
3. Apply the same mapping at `lifecycle.py:193` in `cmd_resume`
4. Add tests for each `terminated_by` value

## Impact

- **Priority**: P4 - Affects CI/scripting use cases, not interactive users
- **Effort**: Small - Mapping change in 2 locations
- **Risk**: Low - Only changes exit codes for non-terminal cases
- **Breaking Change**: No (scripts depending on exit code `1` for signal would see `0`)

## Labels

`bug`, `ll-loop`, `cli`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `return 0 if result.terminated_by == "terminal" else 1` confirmed at `_helpers.py:350` and `lifecycle.py:188`
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — v2.0 format: added Steps to Reproduce, Root Cause, Motivation, Integration Map, Implementation Steps; added confidence_score and outcome_confidence to frontmatter; added Status footer
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb28e4a35.jsonl` — Readiness: 96/100 PROCEED; Outcome: 87/100 HIGH CONFIDENCE
- `/ll:ready-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c43e18f-ee84-4109-9f86-77e479f07065.jsonl` — CORRECTED: line drift updated (_helpers.py:350→403, lifecycle.py:188→193)

- `/ll:manage-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/` — FIXED: Defined EXIT_CODES dict in _helpers.py; updated run_foreground and cmd_resume to use EXIT_CODES.get(result.terminated_by, 1); added 13 tests covering all terminated_by values for both functions

---

## Resolution

**Fixed** in commit pending.

- Defined `EXIT_CODES = {"terminal": 0, "signal": 0, "handoff": 0, "max_iterations": 1, "timeout": 1}` in `_helpers.py`
- Replaced binary `return 0 if result.terminated_by == "terminal" else 1` with `return EXIT_CODES.get(result.terminated_by, 1)` in both `run_foreground` (_helpers.py:403) and `cmd_resume` (lifecycle.py:193)
- Added `TestRunForegroundExitCodes` (8 tests) in `test_ll_loop_display.py`
- Added `TestCmdResumeExitCodes` (5 tests) in `test_cli_loop_lifecycle.py`

## Status

**Completed** | Created: 2026-03-06 | Resolved: 2026-03-06 | Priority: P4
