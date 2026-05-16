---
id: BUG-1385
type: BUG
priority: P1
status: done
title: --resume fails in print mode during Option E context-handoff continuation
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-09T19:01:12Z
---

# BUG-1385: `--resume` fails in print mode during Option E context-handoff continuation

## Summary

`run_with_continuation` uses `--resume` to send an explicit handoff instruction to an
existing Claude session (Option E path), but the Claude CLI requires a session ID when
`--resume` is combined with `--print` (`-p`). The correct flag for "continue the most
recent session without specifying an ID" in print mode is `--continue`.

Confirmed independently in blender-agents (BUG-9180) and in this repo (BUG-1383).

## Current Behavior

When `run_with_continuation` detects the Option E sentinel and calls `run_claude_command` with `resume_session=True`, the CLI command includes `--resume` (without a session ID). In print mode (`-p`), this causes an immediate subprocess failure:

```
Error: --resume requires a valid session ID or session title when used with --print.
Usage: claude -p --resume <session-id|title>
```

The Option E context-handoff path never completes; the handoff instruction is never delivered.

## Expected Behavior

The `--continue` flag (not `--resume`) should be used when continuing the most recent session in print mode without a session ID. With `--continue`, the CLI successfully delivers the handoff instruction as a new user turn in the existing session context.

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

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py:268` — `cmd_args.append("--resume")` → `cmd_args.append("--continue")` (**the one real code change**)
- `scripts/little_loops/subprocess_utils.py:250` — docstring mentions `--resume`; update to `--continue`
- `scripts/little_loops/issue_manager.py:131` — log string interpolates `" --resume"`; update to `" --continue"`
- `scripts/little_loops/issue_manager.py:119-120` — docstring says `--resume`; update
- `scripts/little_loops/issue_manager.py:186` — `run_with_continuation()` docstring Option E description says `--resume CLI flag`; update
- `scripts/little_loops/issue_manager.py:324` — inline comment says `--resume CLI flag`; update
- `scripts/little_loops/issue_manager.py:308-310` — runtime `logger.info` string "sending explicit handoff instruction via --resume"; update to `--continue` _(wiring pass: `/ll:wire-issue`)_
- `scripts/little_loops/parallel/worker_pool.py:658` — `_run_claude_command()` docstring; update
- `scripts/little_loops/parallel/worker_pool.py:833` — `resume_session=True` call site (no string change needed; just the downstream subprocess_utils fix)

### Test Files to Update
- `scripts/tests/test_subprocess_utils.py:1748` — `assert "--resume" in args` → `assert "--continue" in args`
- `scripts/tests/test_subprocess_utils.py:1751` — ordering assertion uses `args.index("--resume")` → `args.index("--continue")`
- `scripts/tests/test_subprocess_utils.py:1769` — `assert "--resume" not in captured_args[0]` → `assert "--continue" not in captured_args[0]`
- `scripts/tests/test_issue_manager.py:1172` — `TestRunWithContinuation.test_sentinel_triggers_explicit_handoff_instruction` checks `resume_session_flags` via kwargs (no string assertions); **no string change needed**
- `scripts/tests/test_worker_pool.py:2291` — same pattern; **no string change needed**

### Do NOT Change (Different Mechanism)
The following `--resume` strings are appended to the **skill command text** (the `-p` argument to Claude), not to `cmd_args`. They tell the skill to resume and are separate from the CLI flag bug:
- `issue_manager.py:266` — `current_command = f"{_base} --resume"`
- `worker_pool.py:771` — `current_command = f"{command} --resume"`
- `worker_pool.py:848` — `current_command = f"{command} --resume"`

### Dependent Files (Callers With `resume_session=True`)
- `scripts/little_loops/issue_manager.py:333` — `run_claude_command(..., resume_session=True)` — Option E call site
- `scripts/little_loops/parallel/worker_pool.py:833` — `self._run_claude_command(..., resume_session=True)` — parallel Option E call site

No other callers pass `resume_session=True`.

## Implementation Steps

1. **Fix the flag** — In `subprocess_utils.py:run_claude_command()` at line 268, change `cmd_args.append("--resume")` to `cmd_args.append("--continue")`
2. **Update docstrings, comments, and log strings** — Update `--resume` → `--continue` in:
   - `subprocess_utils.py:250` (docstring)
   - `issue_manager.py:119-120, 131, 186, 308-310, 324` (docstring, log string, docstring, runtime logger, comment) _(308-310 added by `/ll:wire-issue`: runtime `logger.info` displaying the flag name)_
   - `worker_pool.py:658` (docstring)
3. **Update test assertions** — In `test_subprocess_utils.py:TestRunClaudeCommandResumeSession` (line 1720): change the three `"--resume"` string literals at lines 1748, 1751, 1769 to `"--continue"`
4. **Verify** — Run `python -m pytest scripts/tests/test_subprocess_utils.py -k TestRunClaudeCommandResumeSession -v`; also run full suite: `python -m pytest scripts/tests/ -v --tb=short`

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

## Resolution

Changed `--resume` to `--continue` in `subprocess_utils.run_claude_command()`. The `--continue` flag correctly continues the most recent session in print mode without requiring a session ID, while `--resume` requires an explicit ID when used with `-p`. Updated all related docstrings, log strings, comments, and test assertions accordingly.

**Files changed**: `subprocess_utils.py`, `issue_manager.py`, `parallel/worker_pool.py`, `tests/test_subprocess_utils.py`

## Session Log
- `/ll:ready-issue` - 2026-05-09T18:51:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/317120a0-9102-442b-8320-06956d7930ca.jsonl`
- `/ll:wire-issue` - 2026-05-09T18:45:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfcc9fa3-c4a8-4876-ba04-ec1062fd5a98.jsonl`
- `/ll:refine-issue` - 2026-05-09T18:41:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5e8908f-e25e-4e7b-b3aa-483b256549a6.jsonl`
- `/ll:confidence-check` - 2026-05-09T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:manage-issue` - 2026-05-09T19:01:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Status

**Completed** | Created: 2026-05-09T17:46:30.689731+00:00 | Updated: 2026-05-09 | Priority: P1

## Related Issues

- BUG-1383 — original issue whose implementation triggered this failure
- BUG-9180 (blender-agents) — same failure observed in downstream project; independently confirmed root cause
