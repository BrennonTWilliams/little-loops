---
id: BUG-1385
type: BUG
priority: P1
status: active
title: "--resume fails in print mode during Option E context-handoff continuation"
---

# BUG-1385: `--resume` fails in print mode during Option E context-handoff continuation

## Summary

`run_with_continuation` uses `--resume` to send an explicit handoff instruction to an
existing Claude session (Option E path), but the Claude CLI requires a session ID when
`--resume` is combined with `--print` (`-p`). The correct flag for "continue the most
recent session without specifying an ID" in print mode is `--continue`.

Confirmed independently in blender-agents (BUG-9180) and in this repo (BUG-1383).

## Error

```
Error: --resume requires a valid session ID or session title when used with --print.
Usage: claude -p --resume <session-id|title>
```

## Root Cause

`subprocess_utils.py:267-268` adds `--resume` as a bare flag (no session ID):

```python
if resume_session:
    cmd_args.append("--resume")   # ← wrong flag for -p mode
cmd_args += ["-p", command]
```

The Claude CLI distinguishes two flags:
- `--resume [SESSION_ID]` — resume by ID; **requires** an ID when used with `-p`
- `--continue` — continue the most recent conversation; works without an ID in `-p` mode

The Option E path intends "continue the existing session to send it the handoff instruction".
That semantic maps to `--continue`, not `--resume` without an ID.

The same `resume_session=True` call pattern exists in `worker_pool.py` and propagates
through the same underlying `subprocess_utils.run_claude_command`.

## Files

- `scripts/little_loops/subprocess_utils.py:267-268` — the actual flag
- `scripts/little_loops/issue_manager.py:119-120,131,186,324` — wrapper + call site + comment
- `scripts/little_loops/parallel/worker_pool.py:658,833` — parallel worker same path
- `scripts/tests/test_subprocess_utils.py` — test asserts `--resume` in args (must update)

## Fix

Replace `--resume` with `--continue` in `subprocess_utils.run_claude_command`:

```python
# subprocess_utils.py:267-268
if resume_session:
    cmd_args.append("--continue")   # --continue works in -p mode without a session ID
cmd_args += ["-p", command]
```

Update the cosmetic log line in `issue_manager.run_claude_command` (line 131):
```python
resume_flag = " --continue" if resume_session else ""
```

Update the test in `test_subprocess_utils.py` (`TestRunClaudeCommandResumeSession`) to
assert `--continue` instead of `--resume`.

No API or interface changes — `resume_session: bool` parameter name and semantics are
unchanged; only the generated CLI flag changes.

## Steps to Reproduce

1. Run any `ll-auto` / `ll-sprint` / `ll-parallel` job that triggers the Option E sentinel path
2. The sentinel is detected → `run_with_continuation` calls `run_claude_command(resume_session=True)`
3. Claude CLI subprocess exits immediately with the `--resume requires a valid session ID` error

## Impact

- **Severity**: High — Option E context-handoff path is completely broken; any session that
  ends with high context usage and no explicit handoff signal will fail on retry
- **Effort**: Trivial — one-line change + test update
- **Risk**: Low — `--continue` is the documented flag for this exact use case
- **Breaking Change**: No

## Labels

`bug`, `high-priority`, `context-handoff`, `option-e`

---

## Status

**Open** | Created: 2026-05-09T17:46:30.689731+00:00 | Updated: 2026-05-09 | Priority: P1

## Related Issues

- BUG-1383 — original issue whose implementation triggered this failure
- BUG-9180 (blender-agents) — same failure observed in downstream project; independently confirmed root cause
