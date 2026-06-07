---
id: ENH-1996
title: "Option J continuation should use /ll:resume instead of injecting summary blob"
type: ENH
status: open
priority: P3
confidence: 90
captured_at: "2026-06-07T01:40:43Z"
discovered_date: "2026-06-06"
discovered_by: capture-issue
---

# ENH-1996: Option J continuation should use /ll:resume instead of injecting summary blob

## Summary

When ll-auto (or ll-parallel) triggers an Option J guillotine — context window at ≥90% or "Prompt is too long" — it currently spawns a fresh `claude -p` session whose prompt is a reconstructed summary blob built by `assemble_guillotine_prompt`: original task excerpt + captured stdout tail + token stats. This is a lossy re-serialization of state that already exists authoritatively in the loop run directory, history DB, and git log. The fix: spawn with only `/ll:resume <run_dir>` as the `-p` argument — no injected message history, no summary blob.

## Current Behavior

`issue_manager.py:assemble_guillotine_prompt` assembles a multi-section prompt string:
```
⚠ CONTEXT LIMIT REACHED — FRESH SESSION CONTINUATION
## Original Task
<truncated initial_command>
## Session Progress at Interruption
- Approximate tokens used: N / 200,000
- Trigger reason: usage 90%
## Last Session Output (what was happening at interruption)
<last ~N chars of captured stdout>
## Scratch Pad Files Available
<scratch listing>
## Instructions for This Session
1. Do NOT restart from scratch...
```

This blob is then passed as the entire `-p` argument for the fresh session.

## Expected Behavior

The fresh session starts with only:
```
/ll:resume <run_dir>
```

where `run_dir` is the loop's `.loops/runs/<loop>-<timestamp>/` directory. `/ll:resume` reads the run dir state, history DB (`ll-session`), and `git log` directly — giving a more accurate picture than whatever the interrupted session managed to summarize before hitting the limit.

## Motivation

- The current summary blob is inherently truncated (stdout tail only, task excerpt limited to N lines) and can mislead the continuation session about what was accomplished.
- `/ll:resume` was designed for exactly this handoff — it reads authoritative state, not a summarized copy.
- Eliminates the risk of the continuation session re-doing completed work because the stdout tail was cut off mid-sentence.
- Removes a large class of "continuation session ignored that X was already done" bugs.

## Proposed Solution

1. Add a `run_dir: str | None = None` parameter to `run_with_continuation` (or thread it through the Option J block via a callable/context object).
2. In the Option J handler (`issue_manager.py:320-342`), when `run_dir` is provided, replace the `assemble_guillotine_prompt` call with:
   ```python
   guillotine_cmd = f"/ll:resume {run_dir}"
   ```
3. When `run_dir` is `None` (non-loop contexts where no run dir exists), fall back to the existing `assemble_guillotine_prompt` behavior — no regression for bare `ll-auto` runs.
4. Apply the same change to `parallel/worker_pool.py:assemble_guillotine_prompt` call site (line 833).
5. Wire `run_dir` into the ll-loop runner's call to `run_with_continuation` — the runner already knows the run dir path.

`assemble_guillotine_prompt` in `subprocess_utils.py:152` can be kept (non-loop fallback) or deprecated later.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — Option J block (lines 320–342), `run_with_continuation` signature (line 194)
- `scripts/little_loops/parallel/worker_pool.py` — Option J call site (line 833)
- `scripts/little_loops/loop_runner.py` (or equivalent) — wire `run_dir` into `run_with_continuation` call

### Dependent Files (Callers/Importers)
- `scripts/little_loops/subprocess_utils.py:152` — `assemble_guillotine_prompt` (retained for fallback; no change needed immediately)
- Any other callers of `run_with_continuation` — new param is `None`-defaulted so no API break

### Similar Patterns
- Option E path (`issue_manager.py:395-399`) already uses `resume_command` parameter — same pattern, different trigger
- `resume_command` parameter at `run_with_continuation:202` already supports slash-command continuation for Option E

### Tests
- `scripts/tests/test_issue_manager.py` — add test: Option J with `run_dir` set uses `/ll:resume` instead of summary blob
- `scripts/tests/test_issue_manager.py` — verify Option J with `run_dir=None` still calls `assemble_guillotine_prompt` (fallback)
- `scripts/tests/test_subprocess_utils.py` — `assemble_guillotine_prompt` unchanged; existing tests still pass

### Documentation
- `docs/reference/API.md` — update `run_with_continuation` signature entry
- `hooks/prompts/` — no changes needed

### Configuration
- N/A

## Implementation Steps

1. Add `run_dir: str | None = None` to `run_with_continuation` signature
2. In the Option J block, branch: if `run_dir` is set, set `guillotine_cmd = f"/ll:resume {run_dir}"`; else call `assemble_guillotine_prompt` as today
3. Wire `run_dir` from the ll-loop runner into the `run_with_continuation` call
4. Apply same change in `parallel/worker_pool.py`
5. Add unit tests for both branches
6. Verify end-to-end: trigger a guillotine mid-run and confirm the continuation session starts with `/ll:resume`

## Scope Boundaries

- **In scope**: Option J (guillotine) path only — `issue_manager.py:320-342` and `worker_pool.py:833`
- **Out of scope**: Option E (normal handoff) path — it uses `read_continuation_prompt` and already has `resume_command` wiring
- **Out of scope**: Modifying `/ll:resume` itself — it should already handle a `run_dir` argument
- **Out of scope**: Non-loop contexts (bare `ll-auto` without a loop run dir) — keep `assemble_guillotine_prompt` fallback

## API/Interface

```python
# Before
def run_with_continuation(
    initial_command: str,
    ...,
    resume_command: str | None = None,
    ...
) -> ...: ...

# After — new optional param, no breaking change
def run_with_continuation(
    initial_command: str,
    ...,
    resume_command: str | None = None,
    run_dir: str | None = None,   # <-- new
    ...
) -> ...: ...
```

## Impact

- **Priority**: P3 — correctness improvement; current behavior works but is fragile
- **Effort**: Small — two call sites, one new parameter, two test cases
- **Risk**: Low — `None`-defaulted new param, existing behavior preserved as fallback
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`automation`, `continuation`, `ll-auto`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-06-07T01:40:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/207c23c3-64d9-4b1e-9717-2d8dd4b3640c.jsonl`

---

## Status

**Open** | Created: 2026-06-06 | Priority: P3
