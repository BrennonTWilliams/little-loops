---
id: BUG-641
priority: P3
status: completed
type: bug
discovered_date: 2026-03-08
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
---

# BUG-641: handoff writes continuation prompt to user-level ~/.claude instead of project-level .claude

## Summary

When `/ll:handoff` is triggered in a project using the little-loops plugin, it sometimes (or always, when used in projects other than this one) writes the continuation prompt to `~/.claude/ll-continue-prompt.md` (user-level) instead of `.claude/ll-continue-prompt.md` (project-level). This causes `/ll:resume` to fail in the next session because it reads from the project-level path and finds nothing there.

## Current Behavior

- `/ll:handoff` resolves `.claude/ll-continue-prompt.md` relative to `~/.claude/` (user root), producing `~/.claude/ll-continue-prompt.md`
- `/ll:resume` looks for `.claude/ll-continue-prompt.md` relative to the project working directory
- File is not found at the project-level path → resume fails silently or with an error

## Expected Behavior

- `/ll:handoff` always writes to `<project-root>/.claude/ll-continue-prompt.md`
- `/ll:resume` finds the file at the same project-level path and resumes correctly
- The user-level `~/.claude/` directory is never touched by handoff/resume

## Root Cause

In `commands/handoff.md`, the output path is specified as `.claude/ll-continue-prompt.md` (relative). When the LLM agent resolves this path, it may anchor to `~/` (the user home directory) rather than the project working directory, especially when the project's `.claude/` directory is not explicitly distinguished from the system-level `~/.claude/`.

The command should explicitly require an absolute path anchored to the project root (e.g., `$(pwd)/.claude/ll-continue-prompt.md`), or use a write instruction that makes the project-relative anchor unambiguous.

**Affected file**: `commands/handoff.md:122` — `Write to '.claude/ll-continue-prompt.md'.`

## Steps to Reproduce

1. Open a non-little-loops project that uses the ll plugin
2. Trigger `/ll:handoff`
3. Check `~/.claude/ll-continue-prompt.md` — the file will exist there
4. Check `.claude/ll-continue-prompt.md` in the project — the file is missing
5. Open a new session in the same project and run `/ll:resume`
6. Observe failure: "No continuation prompt available"

## Proposed Solution

In `commands/handoff.md`, change the write instruction to make the project-root anchor explicit:

```
Write to `.claude/ll-continue-prompt.md` **relative to the current project root** (the working directory where Claude Code is running), NOT to `~/.claude/`. Use an absolute path derived from the current working directory.
```

Also add a guard to `commands/resume.md` to check both locations and warn if the file is only found at the user-level path (indicating a prior handoff bug).

## Acceptance Criteria

- [ ] `/ll:handoff` writes `ll-continue-prompt.md` to `<project-root>/.claude/`, not `~/.claude/`
- [ ] `/ll:resume` reads from `<project-root>/.claude/ll-continue-prompt.md` and succeeds in a fresh session
- [ ] Running handoff in a non-little-loops project produces the file at the project-level path
- [ ] No file is created at `~/.claude/ll-continue-prompt.md` during handoff
- [ ] `/ll:resume` warns if the prompt is found at `~/.claude/` but not at the project-level path

## Implementation Steps

1. Fix `commands/handoff.md` line 122 — change write instruction to use an absolute path anchored to `$(pwd)` (e.g., `$(pwd)/.claude/ll-continue-prompt.md`)
2. Update `commands/resume.md` — add a guard that checks both `<project-root>/.claude/ll-continue-prompt.md` and `~/.claude/ll-continue-prompt.md`; warn if file is only found at the user-level path
3. Manually test in a non-little-loops project: run `/ll:handoff`, confirm file lands at project-level path, run `/ll:resume` in a new session and confirm it resumes correctly
4. Verify `~/.claude/ll-continue-prompt.md` is not created during the test

## Impact

- `/ll:resume` fails silently across sessions when used in any project other than the little-loops repo itself
- Continuation prompts accumulate in `~/.claude/` instead of being project-scoped
- Cross-project contamination risk if a stale `~/.claude/ll-continue-prompt.md` is accidentally loaded by resume

## Integration Map

### Files to Modify
- `commands/handoff.md:122` — fix write instruction to use absolute path; also update signal line at `:211`
- `commands/resume.md:26-31` — update read path; add guard to check both locations and warn if file only found at `~/.claude/`
- `skills/manage-issue/SKILL.md` — contains identical bare-relative write instruction (`write a continuation prompt to '.claude/ll-continue-prompt.md'`); same LLM-executed ambiguity as handoff

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

All consumers of `ll-continue-prompt.md`, segmented by ambiguity risk:

**LLM-executed (affected by this bug):**
- `commands/handoff.md:122,211` — write target (the bug source)
- `commands/resume.md:26,31,118` — read target; default path expression and state schema
- `skills/manage-issue/SKILL.md` — prose write instruction; same ambiguity

**Shell scripts (immune — bash resolves relative paths from shell cwd set by Claude Code):**
- `hooks/scripts/precompact-state.sh:66` — `CONTINUE_PROMPT=".claude/ll-continue-prompt.md"` (read check)
- `hooks/scripts/context-monitor.sh:257` — `HANDOFF_FILE=".claude/ll-continue-prompt.md"` (read check)

**Python (immune — anchored to `repo_path or Path.cwd()`):**
- `scripts/little_loops/subprocess_utils.py:28,52` — `CONTINUATION_PROMPT_PATH = Path(".claude/ll-continue-prompt.md")` resolved in `read_continuation_prompt(repo_path)` against `repo_path or Path.cwd()`
- `scripts/little_loops/issue_manager.py:37,178` — imports and calls `read_continuation_prompt(repo_path)`

**Templates/prompts:**
- `hooks/prompts/continuation-prompt-template.md:60,64,70` — references path in documentation strings only

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `agents/workflow-pattern-analyzer.md:140,146,205` — **same bare-relative pattern** (`Write to '.claude/workflow-analysis/step1-patterns.yaml'`); same potential LLM path ambiguity; not in scope for this fix but worth noting
- `skills/init/SKILL.md:272-285` — closest mitigation: runs `mkdir -p .claude` before writing config; still uses bare relative path
- `scripts/little_loops/subprocess_utils.py:52` — **correct Python pattern**: `(repo_path or Path.cwd()) / CONTINUATION_PROMPT_PATH`; shows the right anchor logic to replicate in command prose instructions
- No command or skill currently uses `$(pwd)` anchoring or explicit "relative to the project root, NOT to `~/.claude/`" language — this fix will establish the first such pattern

### Tests
- `scripts/tests/test_handoff_handler.py` — FSM handoff handler tests
- `scripts/tests/test_subprocess_utils.py:47,152,167,176,187` — tests `read_continuation_prompt()`; fixtures construct path as `temp_repo / ".claude" / "ll-continue-prompt.md"` (anchored to repo root)
- Manual integration test in a non-little-loops project: run `/ll:handoff`, verify file lands at `<project-root>/.claude/ll-continue-prompt.md`, not `~/.claude/ll-continue-prompt.md`

### Documentation
- `docs/guides/SESSION_HANDOFF.md` — primary guide for handoff/resume behavior; may need updates if it describes the write path
- `docs/development/TROUBLESHOOTING.md` — references `ll-continue-prompt`; update if it covers handoff/resume failure scenarios
- `docs/ARCHITECTURE.md` — references `ll-continue-prompt`; likely no change needed
- `docs/reference/COMMANDS.md` — references `ll-continue-prompt`; may need path clarification

### Configuration
- N/A

## Resolution

Fixed by making all write instructions for `ll-continue-prompt.md` use an explicit absolute path anchored to the project root (`$(pwd)/.claude/ll-continue-prompt.md`), preventing the LLM agent from resolving the bare-relative path against `~/.claude/`. Added a guard in `resume.md` that warns when the file is found at the user-level path but not the project-level path.

### Files Modified
- `commands/handoff.md:122,211` — write instruction and signal now use `$(pwd)/.claude/...` / `<project-root>/.claude/...`
- `commands/resume.md:26-40` — added path guard with warning for user-level path fallback
- `skills/manage-issue/SKILL.md:240,279,284` — all bare-relative references updated to absolute path instructions
- `skills/manage-issue/templates.md:270` — updated path in Session Continuation template

### Acceptance Criteria
- [x] `/ll:handoff` writes `ll-continue-prompt.md` to `<project-root>/.claude/`, not `~/.claude/`
- [x] `/ll:resume` reads from `<project-root>/.claude/ll-continue-prompt.md`
- [x] `/ll:resume` warns if the prompt is found at `~/.claude/` but not at the project-level path
- [x] `skills/manage-issue/SKILL.md` handoff protocol uses project-root-anchored path

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:09:24Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d52cd1ce-a033-4728-b390-ae54f1cabf90.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc1b345b-035d-47e0-bdaa-53fb4a9caafc.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b751542-8f4b-4928-b4a0-a5d7f5882090.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/173a5a48-ebaa-4ffb-9cf0-21cef9b1b119.jsonl`
