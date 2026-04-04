---
discovered_date: 2026-04-04
discovered_by: capture-issue
---

# FEAT-949: Add `improve-claude-md` skill using `<important if>` block restructuring

## Summary

Add a new `ll:improve-claude-md` skill that rewrites a project's `CLAUDE.md` file using `<important if="condition">` XML blocks, improving LLM instruction adherence by scoping each section to the tasks where it's actually relevant.

## Context

Identified from conversation comparing humanlayer/skills `improve-claude-md` to ll's `audit-claude-config`. The comparison revealed that ll has no equivalent capability: `audit-claude-config` audits CLAUDE.md quality but does not rewrite the file. The core mechanism — `<important if>` XML blocks — exploits the same XML pattern used by Claude Code's own system prompt, cutting through the "may or may not be relevant" system reminder to give Claude precise, conditional instruction attention.

## Motivation

Claude Code injects a system reminder that CLAUDE.md content "may or may not be relevant to your tasks," causing Claude to selectively ignore sections. Wrapping instructions in `<important if="condition">` blocks signals relevance explicitly. Without this skill, users must manually restructure their CLAUDE.md, and ll's audit step has no automated rewrite path.

## Proposed Solution

Create a `skills/improve-claude-md/SKILL.md` that implements the humanlayer 9-step rewrite algorithm:

1. Extract project identity — leave bare (always relevant)
2. Extract directory map — leave bare
3. Extract tech stack — leave bare, condensed
4. Extract commands — wrap together in one `<important if="you need to run commands...">` block; never drop any command
5. Break apart rules — each rule gets its own narrow-condition `<important if>` block
6. Wrap domain sections — testing patterns, API conventions, etc. each get their own block
7. Delete linter-territory — strip style rules already enforced by linter/formatter
8. Delete code snippets — replace with file path references
9. Delete vague instructions — remove non-actionable guidance

**Key design constraints (from humanlayer reference impl)**:
- Foundational context (identity, project map, tech stack) stays bare — relevant to 90%+ of tasks
- Conditions must be narrow and specific (not "you are writing code" but "you are adding imports")
- No file sharding — everything inline, LLM attends by condition match
- Never drop commands — commands table is a hard constraint

**Scope options** (to decide during refinement):
- Option A: Standalone `ll:improve-claude-md` skill (mirrors humanlayer structure)
- Option B: Add `--rewrite` flag to `ll:audit-claude-config` (integrated into existing audit flow)

Option A is preferred for composability and discoverability.

## Implementation Steps

1. Create `skills/improve-claude-md/SKILL.md` with the 9-step rewrite algorithm
2. Add trigger keywords: "improve claude md", "rewrite claude md", "`<important if>`", "instruction adherence"
3. The skill should: read current CLAUDE.md, apply the 9 steps sequentially, write the rewritten file, show a diff summary
4. Add a `--dry-run` flag to preview without writing
5. Add to `commands/*.md` listing and `CLAUDE.md` skill index

## Use Case

A developer has a large flat CLAUDE.md with many sections. They run `/ll:improve-claude-md` and the skill rewrites it so that, for example:
- Scratch-pad automation instructions only activate during `ll-auto`/`ll-parallel` runs
- Git/commit guidelines only activate during commit/PR operations
- Code style rules that the linter already enforces are removed

## API/Interface

```bash
# Rewrite CLAUDE.md in place
/ll:improve-claude-md

# Preview changes without writing
/ll:improve-claude-md --dry-run

# Target a specific file (default: .claude/CLAUDE.md or ./CLAUDE.md)
/ll:improve-claude-md --file path/to/CLAUDE.md
```

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | The primary target file this skill rewrites |
| architecture | docs/ARCHITECTURE.md | Skill system design and plugin structure |

## Labels

`feature`, `captured`, `claude-config`, `skill`

---

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5baed11d-a52e-4c14-99da-b2c843eb04ba.jsonl`
