---
id: BUG-876
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 61
---

# BUG-876: Display Timing Bug When Running in External Project

## Summary

A display timing bug occurs when little-loops is run in a project other than its own repository on this machine. The exact manifestation is unknown pending investigation, but the bug was observed during real-world use of little-loops as a plugin in another project.

## Current Behavior

Display output exhibits incorrect timing behavior when little-loops CLI tools or commands are executed from a different project's working directory on this machine.

## Expected Behavior

little-loops should display output with correct timing regardless of which project it is invoked from.

## Motivation

little-loops is designed to be used across projects. If display timing is broken in external-project contexts, it degrades the experience for all users who are not developing little-loops itself — the primary intended use case.

## Steps to Reproduce

1. Install little-loops in a separate project (not the little-loops repo itself)
2. Run one of the little-loops CLI tools (e.g., `ll-auto`, `ll-parallel`, `ll-sprint`) from that project
3. Observe: display output has incorrect timing (e.g., progress updates, spinners, or output appears too early/late or in wrong sequence)

## Root Cause

- **File**: `scripts/little_loops/logger.py`
- **Anchor**: All output methods — `info()`, `success()`, `warning()`, `error()`, `timing()`, `debug()` (lines ~65–126)
- **Cause**: Every `Logger` output method calls `print()` without `flush=True`. When stdout is not a TTY (the common case in external projects where output may be piped, redirected, or monitored), Python defaults to block buffering. Output is held in the buffer and only flushed when the buffer fills or the process exits — causing output to appear delayed, batched, or completely absent during execution.
- **Secondary**: `orchestrator.py:670` has a direct `print()` call without `flush=True` in the status reporting path, also affected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `Logger` class does **not** call `sys.stdout.isatty()` at all — defaults `use_color=True` unless `NO_COLOR` is set (`logger.py:53–55`)
- The `ll-loop` display path (`cli/loop/_helpers.py:334,357,362,369,374,387,392,395,399,406...`) correctly uses `flush=True` on every `print()` — which is why it doesn't exhibit this bug
- `orchestrator.py:703–736` poll loop: `time.sleep(0.1)` between iterations; status print throttled to once per 5 seconds (`orchestrator.py:613`) — this is intentional, not a bug

## Proposed Solution

Add `flush=True` to all `print()` calls in `Logger` output methods, and to the direct `print()` in `orchestrator.py:670`. This matches the already-correct pattern used in `cli/loop/_helpers.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The correct pattern is already established in `cli/loop/_helpers.py` — every `print()` in that file's display path uses `flush=True`. The fix is to apply the same convention to `logger.py` and `orchestrator.py:670`.

## Integration Map

### Files to Modify

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/logger.py` — add `flush=True` to all `print()` calls in `info()`, `success()`, `warning()`, `error()`, `timing()`, `debug()` methods (~lines 65–126)
- `scripts/little_loops/parallel/orchestrator.py:670` — add `flush=True` to the direct `print()` in `_maybe_report_status()`

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/auto.py` — instantiates `Logger`, calls `configure_output(config.cli)` at line 63
- `scripts/little_loops/cli/parallel.py` — instantiates `Logger` at line 147, calls `configure_output` at line 145
- `scripts/little_loops/cli/sprint/__init__.py` — uses `Logger` (no `configure_output` call in sprint's `run.py`)
- `scripts/little_loops/cli/loop/__init__.py:33` — calls `configure_output(config.cli)`

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/_helpers.py:334,357,362,369,374,387,392,395,399,406,426,435,462,466,470,475` — every `print()` in the loop display path uses `flush=True`; this is the pattern to follow
- `scripts/little_loops/fsm/executor.py:312–314` — uses `sys.stdout.write()` + explicit `sys.stdout.flush()` for interactive prompts

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_logger.py` — existing `Logger` output tests; no non-TTY flush behavior coverage
- `scripts/tests/test_cli_output.py` — `configure_output()` and `_USE_COLOR` tests; use `patch("sys.stdout")` as mock
- `scripts/tests/test_ll_loop_display.py:1689–1722` — `isatty` gate tests for `_helpers.py` (correct reference for the pattern)
- New test needed: verify `Logger` methods flush immediately in non-TTY context (e.g., capture output with `StringIO` and verify it appears before process exit)

### Documentation

- N/A — internal behavior change, no user-facing docs affected

### Configuration

- N/A

## Implementation Steps

_Updated by `/ll:refine-issue` — based on codebase analysis:_

1. Add `flush=True` to all six `print()` calls in `scripts/little_loops/logger.py` output methods (`info`, `success`, `warning`, `error`, `timing`, `debug`, ~lines 65–126)
2. Add `flush=True` to the direct `print()` at `scripts/little_loops/parallel/orchestrator.py:670` in `_maybe_report_status()`
3. Add a regression test in `scripts/tests/test_logger.py` that captures `Logger` output via `StringIO` and asserts it flushes before EOF
4. Run existing tests: `python -m pytest scripts/tests/test_logger.py scripts/tests/test_cli_output.py -v`
5. Verify manually in an external project: run `ll-auto` or `ll-parallel` and confirm output appears in real time

## Impact

- **Priority**: P3 - Affects real-world external-project use; not blocking but degrades core UX
- **Effort**: Small/Medium - Scope unknown until reproduced; likely isolated to display layer
- **Risk**: Low - Display code is unlikely to have broad side effects
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `display`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53ba0be0-d3da-480a-afee-b057175a21d5.jsonl`
- `/ll:refine-issue` - 2026-03-24T21:16:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62b2e8f8-ccf9-4ace-b015-4f31884ff3af.jsonl`

- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7b65b55-cf2f-4329-bd1e-bb86516edd27.jsonl`

---

**Open** | Created: 2026-03-24 | Priority: P3
