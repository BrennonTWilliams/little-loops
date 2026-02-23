---
type: ENH
id: ENH-456
title: Add intro context and improve feature descriptions in init wizard
priority: P3
status: open
created: 2026-02-22
---

# Add intro context and improve feature descriptions in init wizard

## Summary

Two clarity issues in the interactive wizard:

### 1. No opening context
The wizard jumps straight into project name detection. A brief intro would orient new users:
> "This wizard will create `.claude/ll-config.json` — the configuration file that controls how little-loops manages your project's issues, code quality checks, and automation tools."

### 2. Feature descriptions assume prior knowledge
Round 3 feature descriptions reference internal tools without explanation:

- **Current**: "Configure ll-parallel for concurrent issue processing with git worktrees"
- **Better**: "Process multiple issues in parallel using isolated git worktrees (requires ll-parallel CLI)"

- **Current**: "Block manage-issue implementation when confidence score is below threshold"
- **Better**: "Require a minimum readiness score before automated implementation proceeds"

## Current Behavior

The wizard jumps directly into project name detection with no opening context. Round 3 feature descriptions use internal tool names without explanation:
- "Configure ll-parallel for concurrent issue processing with git worktrees"
- "Block manage-issue implementation when confidence score is below threshold"

New users unfamiliar with little-loops cannot evaluate these options from the descriptions alone.

## Expected Behavior

A 1-2 sentence intro is displayed before Round 1 explaining what the wizard creates. Round 3 feature descriptions are self-explanatory: they explain what each feature does and what it requires, without assuming prior knowledge of CLI tool names.

## Motivation

The init wizard is the first interaction new users have with little-loops. Poor feature descriptions cause users to skip useful features (or blindly enable ones they don't need). A brief intro reduces the "what is this?" confusion that new users experience.

## Proposed Solution

1. Add a 1-2 sentence intro text output before Round 1
2. Rewrite Round 3 feature descriptions to be self-explanatory without prior tool knowledge
3. Consider adding a brief "What is this?" note for less obvious features like confidence gate

## Scope Boundaries

- **In scope**: Adding intro text before Round 1; rewriting Round 3 feature option descriptions
- **Out of scope**: Changes to wizard logic, question structure, or which features are offered; adding help links; modifying other rounds

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Add intro text output before Step 5 / Round 1
- `skills/init/interactive.md` — Round 3 feature option descriptions (lines ~128-148)

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add a text output block before Round 1 in `SKILL.md`: "This wizard creates `.claude/ll-config.json` — the configuration file for little-loops' issue management, automation, and code quality tools."
2. Rewrite each Round 3 feature description in `interactive.md` to be self-explanatory (e.g., "Process multiple issues in parallel using isolated git worktrees (requires ll-parallel CLI)")
3. Add brief "What is this?" context for less obvious features (confidence gate)
4. Review all rewritten descriptions for clarity with a "new user" perspective

## Impact

- **Priority**: P3 — Improves first-run experience; reduces feature selection errors during onboarding
- **Effort**: Small — Text-only changes to two files
- **Risk**: Low — Cosmetic change; no behavioral impact
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `interactive-wizard`, `ux`, `onboarding`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- BUG-449
- ENH-451
- ENH-452
- ENH-454

## Blocks

- ENH-453
- ENH-458
- ENH-460

---

## Resolution

**Resolved**: 2026-02-23
**Action**: implement

### Changes Made
- Added wizard intro text ("Welcome to little-loops setup!") before Round 1 in `skills/init/interactive.md`
- Rewrote all 4 Round 3a (Core Features) descriptions to be self-explanatory without prior tool knowledge
- Rewrote all 3 Round 3b (Automation Features) descriptions to be self-explanatory without prior tool knowledge

### Files Modified
- `skills/init/interactive.md` — Added intro section, rewrote 7 feature descriptions

## Status

**Completed** | Created: 2026-02-22 | Resolved: 2026-02-23 | Priority: P3
