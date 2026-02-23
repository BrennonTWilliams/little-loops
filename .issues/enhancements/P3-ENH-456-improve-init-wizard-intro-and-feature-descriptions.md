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

## Proposed Change

1. Add a 1-2 sentence intro text output before Round 1
2. Rewrite Round 3 feature descriptions to be self-explanatory without prior tool knowledge
3. Consider adding a brief "What is this?" note for less obvious features like confidence gate

## Files

- `skills/init/SKILL.md` (before Step 5 / Round 1)
- `skills/init/interactive.md` (Round 3, lines ~128-148)
