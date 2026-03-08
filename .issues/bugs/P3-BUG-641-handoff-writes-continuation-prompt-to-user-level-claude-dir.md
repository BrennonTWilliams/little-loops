---
id: BUG-641
priority: P3
status: active
type: bug
discovered_date: 2026-03-08
discovered_by: capture-issue
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
- `commands/handoff.md` (line 122) — fix write instruction to use absolute path
- `commands/resume.md` — add guard to check both locations

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "ll-continue-prompt" commands/`

### Similar Patterns
- TBD — check if other commands write to `.claude/` paths that may have the same ambiguity

### Tests
- Manual integration test in a non-little-loops project

### Documentation
- `docs/TROUBLESHOOTING.md` — update if it covers handoff/resume behavior

### Configuration
- N/A

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:09:24Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d52cd1ce-a033-4728-b390-ae54f1cabf90.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
