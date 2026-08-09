---
id: BUG-3131
status: done
priority: P2
captured_at: "2026-08-09T06:01:47Z"
completed_at: "2026-08-09T06:01:47Z"
discovered_date: 2026-08-09
discovered_by: capture-issue
relates_to: [ENH-3129, ENH-3130]
---

# BUG-3131: ll-auto timeout handler reports already-completed work as failed

## Summary

`AutoManager._process_issue`'s `except subprocess.TimeoutExpired` handler
fabricated a failure result without consulting the issue file. Because the
wall-clock kill is a `SIGKILL` delivered at an arbitrary instant, it can land
*after* the agent finalized the lifecycle and committed — producing a run
summary that reports `Issues processed: 0 / Failed issues: 1` for work that is
already `done` on the branch, and a `--resume` run that reprocesses it.

## Current Behavior

Observed on the `ll-auto --only FEAT-3078` run of 2026-08-08:

```
7733d9a5 2026-08-09 00:35:36 -0500 feat(host-runner): thread disable_background_tasks...
[00:35:51] FEAT-3078: timeout after 3600s
[00:35:51] Issues processed: 0
[00:35:51] Failed issues: 1
```

The commit landed 15 seconds before the kill. FEAT-3078 was `status: done`,
committed, with a passing suite — and was still recorded as a failure.

## Root Cause

`scripts/little_loops/issue_manager.py`, `AutoManager._process_issue`, the
`except subprocess.TimeoutExpired` branch (BUG-2976 added this handler so a
per-issue timeout would not abort the whole backlog):

```python
except subprocess.TimeoutExpired as exc:
    kind = "idle timeout" if exc.output == "idle_timeout" else "timeout"
    reason = f"{kind} after {exc.timeout:.0f}s"
    self.logger.error(f"{info.issue_id}: {reason}")
    result = IssueProcessingResult(success=False, ...)
```

`success=False` is unconditional. The handler never calls
`verify_issue_completed`, so the timeout path bypasses every recovery
mechanism the normal returncode path has:

- the BUG-2409 uncommitted-changes / plan-awaiting-approval discrimination
- the BUG-3058 finalize-retry re-drive
- the `result.returncode == 0` content-marker and evidence fallbacks

This is the same family as the recurring *"previous session implemented X but
ended its turn without finalizing"* corrections in the session digest.

## Expected Behavior

On timeout, consult the authoritative frontmatter before recording a verdict:

- issue already `done`/`cancelled` → record **success** despite the timeout
- otherwise → record the failure exactly as before, with the same
  `timeout after Ns` reason

## Proposed Fix

Implemented. `verify_issue_completed(info, self.config, self.logger)` now runs
inside the handler and gates the result.

Deliberately narrow: the evidence fallback (`complete_issue_lifecycle` on a
dirty working tree) is **not** invoked from the timeout path. The returncode-0
path can trust a clean turn-end as corroboration that the work is finished; a
`SIGKILL` has no such signal, and a killed agent's half-written implementation
is indistinguishable from a finished one. Auto-completing there would trade a
false negative for a false positive, which is worse. Uncommitted work is
instead *reported* — "review the working tree before re-running" — and never
auto-completed.

## Integration Map

### Files Modified
- `scripts/little_loops/issue_manager.py` — `AutoManager._process_issue`
  timeout handler
- `scripts/tests/test_issue_manager.py` — two new regression tests

### Dependent Files (Callers/Importers)
- `little_loops.issue_lifecycle.verify_issue_completed` and
  `little_loops.work_verification.verify_work_was_done` — both already
  imported in `issue_manager.py`; no new imports required

### Tests
- `test_timeout_after_finalization_records_success` — agent finalizes, then
  the kill fires (the FEAT-3078 sequence); asserts success + not in
  `failed_issues`
- `test_timeout_without_finalization_still_fails` — patches
  `verify_work_was_done` to True to pin that a dirty tree does **not** trigger
  auto-completion
- Both BUG-2976 regression guards still pass unchanged

### Documentation
- N/A — internal handler behavior, no user-facing surface change

### Configuration
- N/A

## Impact

- **Risk**: Low. The change only *adds* a success path that requires
  authoritative `done`/`cancelled` frontmatter; the failure path is byte-for-byte
  the same reason string.
- **Benefit**: `--resume` no longer reprocesses completed issues, and run
  summaries stop under-reporting throughput.

## Verification

- `python -m pytest scripts/tests/` → **18712 passed**, 43 skipped, 1 failed
- The single failure is `test_prose_dep_sweep_gate::test_no_prose_dependency_drift_in_repo`,
  pre-existing and unrelated: stale prose in `ENH-3095`/`FEAT-3122` citing
  `FEAT-3078`/`FEAT-3108`, which became `done`. Markdown content in `.issues/`,
  not code — untouched by this change.
- `ruff check`, `ruff format --check`, `python -m mypy` all clean on the
  changed files.

## Follow-ups

Two related items captured separately rather than folded in here:

- **ENH-3129** — `automation.timeout_seconds` is a per-invocation budget with
  no per-issue ceiling; raise the default and add
  `automation.max_issue_wall_clock_time`
- **ENH-3130** — SIGTERM finalize grace before SIGKILL, so the lifecycle this
  fix detects is more likely to have completed in the first place

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Automation driver and issue lifecycle design |
| `docs/reference/API.md` | `little_loops.issue_manager` module reference |
| `docs/development/TROUBLESHOOTING.md` | Timeout behavior in automation runs |

## Status

- **Current**: done
- **Completed**: 2026-08-09
- **Blockers**: None

## Session Log
- `/ll:capture-issue` - 2026-08-09T06:02:42 - `ce451e9a-4952-45a2-828c-106f17467622.jsonl`
- `hook:posttooluse-status-done` - 2026-08-09T06:02:23 - `ce451e9a-4952-45a2-828c-106f17467622.jsonl`
