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

## Proposed Fix

In `commands/handoff.md`, change the write instruction to make the project-root anchor explicit:

```
Write to `.claude/ll-continue-prompt.md` **relative to the current project root** (the working directory where Claude Code is running), NOT to `~/.claude/`. Use an absolute path derived from the current working directory.
```

Also add a guard to `commands/resume.md` to check both locations and warn if the file is only found at the user-level path (indicating a prior handoff bug).

## Impact

- `/ll:resume` fails silently across sessions when used in any project other than the little-loops repo itself
- Continuation prompts accumulate in `~/.claude/` instead of being project-scoped
- Cross-project contamination risk if a stale `~/.claude/ll-continue-prompt.md` is accidentally loaded by resume

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:09:24Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d52cd1ce-a033-4728-b390-ae54f1cabf90.jsonl`
