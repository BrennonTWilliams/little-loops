---
id: ENH-1996
title: Option J continuation should use /ll:resume instead of injecting summary blob
type: ENH
status: done
priority: P3
confidence: 90
captured_at: '2026-06-07T01:40:43Z'
completed_at: '2026-06-07T02:16:28Z'
discovered_date: '2026-06-06'
discovered_by: capture-issue
decision_needed: false
confidence_score: 91
outcome_confidence: 80
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 19
score_change_surface: 20
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

### Codebase Research Findings

_Added by `/ll:refine-issue`:_

**Option A — Extend `commands/resume.md` to handle directory arguments**: detect when the argument is a directory and resolve a fixed continuation file within it (e.g., look for `continue-prompt.md` or fall back to `ll-session` query). Keeps the interface clean (`/ll:resume <run_dir>`) but requires modifying the resume command, which the issue currently scopes as out-of-bounds.

**Option B — Write a continuation file into the run dir**: before spawning the fresh session in Option J, write a `guillotine-prompt.md` into `<run_dir>/` containing `/ll:resume` context instructions, then invoke `/ll:resume <run_dir>/guillotine-prompt.md`. The resume command already handles file paths; no change to `commands/resume.md` needed. Adds a write step in the Option J block.

> **Selected:** Option B — Write a continuation file into the run dir — reuses the established `Path(run_dir).write_text()` pattern (matching `ab_writer.py`, `write_sentinel`); no changes to `commands/resume.md` needed.

**Step 5 call-chain gap**: The loop runner (`cli/loop/run.py`) injects `run_dir` into `fsm.context["run_dir"]` (line 162) but the FSM executor calls `DefaultActionRunner.run()` → `run_claude_command()` directly — NOT `run_with_continuation`. There is no existing call path from the loop runner to `run_with_continuation`. For Option J to fire in loop contexts via `run_with_continuation`, either (a) `DefaultActionRunner.run()` must be extended to use `run_with_continuation` (scope expansion), or (b) this fix is scoped to `ll-auto`/`ll-parallel` only (no change to the FSM path).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-06.

**Selected**: Option B — Write a continuation file into the run dir

**Reasoning**: Option B reuses the ubiquitous `Path(run_dir).mkdir() + .write_text()` idiom established across `ab_writer.py`, `write_sentinel`, and the loop test suite. The `/ll:resume <file>` protocol already exists and is documented with examples — no changes to `commands/resume.md` are required. Option A requires writing novel directory-resolution logic into `commands/resume.md` with no precedent in any command `.md` file and no existing utility for finding a continuation file within a run directory.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Extend resume.md | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |
| Option B — Write continuation file | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- Option A: No directory-resolution logic in any `commands/*.md` file; no existing utility to resolve a continuation file within a run dir; issue itself scoped resume command modification as out-of-bounds.
- Option B: `ab_writer.py:write_ab_json()` provides exact `Path(run_dir).write_text()` idiom; `/ll:resume <file>` already documented; `write_sentinel` in `subprocess_utils.py:118` uses same write-file-for-next-session pattern.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worker_pool.py` — new test needed: `_run_with_continuation` with `run_dir` set asserts `commands_received[1].startswith("/ll:resume")` and `"CONTEXT LIMIT REACHED" not in commands_received[1]`; follow `test_guillotine_path_on_overflow` pattern at line 2355 using `patch.object(worker_pool, "_run_claude_command", ...)` [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — update `run_with_continuation` signature entry
- `hooks/prompts/` — no changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `commands/resume.md` — invoked at runtime by the new Option J path as `/ll:resume <run_dir>/guillotine-prompt.md`; accepts file paths (not directories); no changes needed under Option B, but must be verified against the written file path [Agent 2 finding]
- `CHANGELOG.md` — new entry needed under the next release section for ENH-1996 [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified line numbers** (all confirmed correct):
- `run_with_continuation` at `issue_manager.py:194` ✓
- `resume_command` parameter at `issue_manager.py:202` ✓
- Option J block: `issue_manager.py:322-347` (issue says 320-342; actual span is 322–347)
- `assemble_guillotine_prompt` at `subprocess_utils.py:152` ✓
- `worker_pool.py:833` Option J call site ✓
- Option E path at `issue_manager.py:395-400` ✓

**Additional files requiring modification (not listed above):**
- `commands/resume.md` — **CRITICAL**: accepts a `prompt_file` positional argument (a FILE path). It does NOT resolve directory paths. Passing `/ll:resume <run_dir>` will fail silently or resolve incorrectly unless this command is extended. The issue marks this as "Out of scope" but it is NOT a pre-existing capability.

**Call chain clarification — FSM/loop runner:**
- `scripts/little_loops/fsm/runners.py:DefaultActionRunner.run()` (lines 71–147) — FSM dispatches slash-command states here, calling `run_claude_command()` directly, NOT `run_with_continuation()`. The Option J guillotine block does not exist in this path.
- `scripts/little_loops/cli/loop/run.py:162` — `run_dir` is injected into `fsm.context["run_dir"]` here (value: `.loops/runs/<loop>-<ts>/`). This is accessible to `PersistentExecutor` for writing artifacts but is NOT passed to `run_with_continuation` at any call site.
- **Consequence for scope**: Proposed Solution Step 5 ("Wire `run_dir` into the ll-loop runner's call to `run_with_continuation`") assumes a connection that does not exist. For `ll-loop` contexts, Option J does not fire through `run_with_continuation`. This step requires redesign — see Proposed Solution research findings below.

## Implementation Steps

1. Add `run_dir: str | None = None` to `run_with_continuation` signature
2. In the Option J block, branch: if `run_dir` is set, set `guillotine_cmd = f"/ll:resume {run_dir}"`; else call `assemble_guillotine_prompt` as today
3. ~~Wire `run_dir` from the ll-loop runner into the `run_with_continuation` call~~ — **DROPPED**: the ll-loop FSM path calls `DefaultActionRunner.run()` → `run_claude_command()` directly, never `run_with_continuation`. No bridge exists. Wiring this would require extending `DefaultActionRunner.run()`, which is out of scope. This issue is scoped to ll-auto/ll-parallel paths only.
4. Apply same change in `parallel/worker_pool.py`
5. Add unit tests for both branches
6. Verify end-to-end: trigger a guillotine mid-run and confirm the continuation session starts with `/ll:resume`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Revise Step 2 to reflect Option B** — The decision selected "Option B — Write a continuation file into the run dir." Step 2 above is incomplete: before setting `guillotine_cmd`, write a `guillotine-prompt.md` into `<run_dir>/` with resume context, then set `guillotine_cmd = f"/ll:resume {run_dir}/guillotine-prompt.md"`. The `/ll:resume` command accepts a file path, not a directory — the raw `run_dir` path will fail silently without the file-write step.

8. **Add test in `test_worker_pool.py`** — `_run_with_continuation` needs a parallel test for the `run_dir` branch, following `test_guillotine_path_on_overflow` (line 2355) using `patch.object(worker_pool, "_run_claude_command", ...)`. Assert `commands_received[1].startswith("/ll:resume")` and `"CONTEXT LIMIT REACHED" not in commands_received[1]`.

9. **Add `CHANGELOG.md` entry** — New entry needed under the next release section for ENH-1996.

### Codebase Research Findings

_Added by `/ll:refine-issue`:_

- **Step 3 (Revised)**: The ll-loop FSM runner does NOT call `run_with_continuation` — it calls `DefaultActionRunner.run()` → `run_claude_command()` directly (`fsm/runners.py:71-147`). `run_dir` lives in `fsm.context` (set at `cli/loop/run.py:162`) but has no bridge to `run_with_continuation`. Two paths: (a) accept that this enhancement only applies to `ll-auto`/`ll-parallel` paths and drop Step 3, or (b) extend `DefaultActionRunner.run()` to use `run_with_continuation` (significantly larger scope). See Proposed Solution options.
- **Test template**: `test_issue_manager.py:TestRunWithContinuation` (class at line 1131) has `test_guillotine_path_on_context_overflow` (line 1347) and `test_guillotine_path_on_prompt_too_long` (line 1397) as exact templates for the new Option J tests. Follow the `mock_run` callable + `patch("little_loops.issue_manager.run_claude_command")` pattern used there.
- **`worker_pool._run_with_continuation` method signature** (`worker_pool.py:729`): currently `(self, command, working_dir, issue_id, max_continuations, context_limit, sentinel_threshold, guillotine_threshold)` — `run_dir` not present; call site at `worker_pool.py:396` passes no `run_dir`.

## Success Metrics

- When `run_dir` is provided to `run_with_continuation`, the continuation prompt is exactly `/ll:resume <run_dir>` with no injected summary blob content
- When `run_dir` is `None`, `assemble_guillotine_prompt` is still called (fallback preserved, no regression)
- Unit tests for both branches pass
- End-to-end: manually triggered guillotine mid-run produces a continuation session that starts with `/ll:resume` and correctly picks up where the previous session left off

## Scope Boundaries

- **In scope**: Option J (guillotine) path only — `issue_manager.py:320-342` and `worker_pool.py:833`; scoped to ll-auto/ll-parallel paths
- **Out of scope**: Option E (normal handoff) path — it uses `read_continuation_prompt` and already has `resume_command` wiring
- **Out of scope**: Modifying `/ll:resume` itself — Option B (write a file into the run dir and pass a file path) resolves this without touching `commands/resume.md`
- **Out of scope**: ll-loop FSM path — `DefaultActionRunner.run()` calls `run_claude_command()` directly, never `run_with_continuation`; bridging these would require extending `DefaultActionRunner.run()` and is a separate effort
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
- `/ll:ready-issue` - 2026-06-07T02:12:00 - `3384dda5-ded8-4449-b909-8788dde5fe51.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `4618c901-07ca-4729-b2a0-eb75257e69a0.jsonl`
- `/ll:wire-issue` - 2026-06-07T02:03:30 - `e5ce0b01-1132-43aa-ac74-dc946a564b11.jsonl`
- `/ll:decide-issue` - 2026-06-07T01:57:15 - `0b2efaaf-5e08-4e86-a9ab-8d50d7d57abb.jsonl`
- `/ll:refine-issue` - 2026-06-07T01:51:16 - `b2347ef5-49cd-4508-a9a7-c9b321c4425a.jsonl`
- `/ll:format-issue` - 2026-06-07T01:44:06 - `93c9ad96-c067-4060-9d3d-b03baf3f7888.jsonl`
- `/ll:capture-issue` - 2026-06-07T01:40:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/207c23c3-64d9-4b1e-9717-2d8dd4b3640c.jsonl`

---

## Status

**Open** | Created: 2026-06-06 | Priority: P3
