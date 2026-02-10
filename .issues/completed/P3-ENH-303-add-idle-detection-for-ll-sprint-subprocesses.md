---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-303: Add idle detection for ll-sprint subprocesses

## Summary

Add output-activity monitoring to `subprocess_utils.py` so that stuck subprocesses (e.g., waiting for `AskUserQuestion` input that will never arrive) are detected and terminated early rather than waiting the full timeout (default 3600s).

## Context

Identified from conversation analyzing `ll-sprint run` approval handling. Currently the only protection against a hanging subprocess is the configurable timeout. If a subprocess produces no output for an extended period, it's likely stuck, but there's no detection for this.

## Current Behavior

`run_claude_command()` in `subprocess_utils.py:55-149` monitors the subprocess with a simple timeout loop (body starts at line 82, monitoring loop at lines 115-137). It reads stdout/stderr but does not track when the last output was produced. A stuck process runs for the entire timeout duration.

## Expected Behavior

If a subprocess produces no stdout/stderr output for a configurable idle period (e.g., 5-10 minutes), it should be flagged as potentially stuck and terminated with an appropriate error message distinguishing it from a normal timeout.

## Current Pain Point

A single stuck subprocess in `ll-sprint` wastes up to 1 hour of wall-clock time before being killed, blocking downstream waves that depend on it. This significantly slows sprint execution when issues trigger unexpected interactive prompts.

## Proposed Solution

1. Track `last_output_time` in `run_claude_command()` alongside the existing timeout check
2. Add a configurable `idle_timeout` parameter (default: 300-600 seconds)
3. When idle timeout is exceeded, kill the process and raise a distinct `IdleTimeoutError` (or similar)
4. Log a clear message indicating the process was killed due to inactivity vs. total timeout

## Scope Boundaries

- Out of scope: Detecting *what* the subprocess is waiting for (just detect lack of output)
- Out of scope: Automatic retry after idle timeout (leave that to the caller)
- Out of scope: Changes to the Claude Code runtime itself

## Impact

- **Priority**: P3
- **Effort**: Small-Medium
- **Risk**: Low — additive change to existing timeout logic

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents subprocess_utils and ll-sprint execution flow |
| architecture | docs/API.md | Documents subprocess_utils module API |

## Labels

`enhancement`, `captured`, `automation`, `subprocess`

---

## Status

**Resolved** | Created: 2026-02-09 | Resolved: 2026-02-10 | Priority: P3

## Resolution

Already implemented. `run_claude_command()` at `subprocess_utils.py:55` has full idle detection:
- `idle_timeout` parameter (line 62, default 0 = disabled)
- `last_output_time` tracking (line 116, updated at line 140)
- Idle timeout check kills process and raises `TimeoutExpired(output="idle_timeout")` (lines 126-131)

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: RESOLVED
- Idle detection was implemented since the previous verification on 2026-02-09
- All proposed features (last_output_time, configurable idle_timeout, distinct error) are present
