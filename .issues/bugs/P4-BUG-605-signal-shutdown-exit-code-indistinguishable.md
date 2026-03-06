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
- **Line(s)**: 350 (at scan commit: c010880)
- **Anchor**: `in function run_foreground()`, final return
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/_helpers.py#L350)
- **Code**:
```python
return 0 if result.terminated_by == "terminal" else 1
```

Same pattern at `lifecycle.py:188` in `cmd_resume`.

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
- `scripts/little_loops/cli/loop/_helpers.py` — replace binary exit code at line 350 with `EXIT_CODES` mapping
- `scripts/little_loops/cli/loop/lifecycle.py` — replace binary exit code at line 188 in `cmd_resume` with same mapping

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
3. Apply the same mapping at `lifecycle.py:188` in `cmd_resume`
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
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — Readiness: 96/100 PROCEED; Outcome: 87/100 HIGH CONFIDENCE

---

## Status

**Open** | Created: 2026-03-06 | Priority: P4
