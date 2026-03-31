---
id: ENH-900
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-31
completed_date: 2026-03-31
discovered_by: manual-audit
depends_on: [ENH-896]
confidence_score: 100
---

# ENH-900: Migrate workflow-analysis and user-messages paths from `.claude/` to `.ll/`

## Summary

Follow-up to ENH-896. The original `.claude/` to `.ll/` migration missed two categories of little-loops artifacts:

1. **`.claude/workflow-analysis/`** — output directory for the 3-step workflow analysis pipeline (step1-patterns, step2-workflows, step3-proposals, summaries)
2. **`.claude/user-messages-{timestamp}.jsonl`** — default output from `ll-messages` CLI
3. **`.claude/backup-continue-prompt.md`** — example path in resume command

Additionally, `skills/init/SKILL.md` Step 8 still had `mkdir -p .claude` for creating the config directory, which should be `mkdir -p .ll`.

## Changes Made

### Python source (functional)

- `scripts/little_loops/workflow_sequence/__init__.py` — changed `_DEFAULT_INPUT_PATH` and all default output paths from `.claude/workflow-analysis/` to `.ll/workflow-analysis/`; updated help text and examples
- `scripts/little_loops/user_messages.py` — changed default output directory from `.claude` to `.ll`
- `scripts/little_loops/cli/messages.py` — updated help text and pipeline examples

### Tests

- `scripts/tests/test_workflow_sequence_analyzer.py` — updated assertion string for default input path

### Commands

- `commands/analyze-workflows.md` — ~25 path references migrated
- `commands/resume.md` — example path updated

### Skills

- `skills/workflow-automation-proposer/SKILL.md` — input/output directory references
- `skills/init/SKILL.md` — Step 8 `mkdir -p .claude` changed to `mkdir -p .ll`

### Agents

- `agents/workflow-pattern-analyzer.md` — example and output path references

### Documentation

- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — all workflow-analysis and user-messages path references
- `docs/reference/CLI.md` — CLI documentation path references
- `docs/reference/API.md` — API documentation path references and code examples
- `EXAMPLE-WORKFLOW-ANALYSIS-README.md` — example file path references

### Config

- `.gitignore` — added `.ll/workflow-analysis/` and `.ll/user-messages-*.jsonl`

## Not changed (correct as-is)

- `.claude/settings.json`, `.claude/settings.local.json` — Claude Code native settings
- `.claude/CLAUDE.md`, `.claude/rules/` — Claude Code project instructions
- `~/.claude/projects/` — Claude Code session JSONL logs
- `.claude/` directory copying for worktrees — Claude Code infrastructure
- `.issues/completed/` — historical issue records
- `thoughts/shared/plans/` — historical plans
- `site/` — generated HTML (regenerated on build)

## Verification

- All 128 tests pass (`python -m pytest scripts/tests/test_workflow_sequence_analyzer.py`)
- Lint clean (`ruff check`)
- Zero remaining `.claude/workflow-analysis` or `.claude/user-messages` references in source files

## Files Modified

```
scripts/little_loops/workflow_sequence/__init__.py
scripts/little_loops/user_messages.py
scripts/little_loops/cli/messages.py
scripts/tests/test_workflow_sequence_analyzer.py
commands/analyze-workflows.md
commands/resume.md
skills/workflow-automation-proposer/SKILL.md
skills/init/SKILL.md
agents/workflow-pattern-analyzer.md
docs/guides/WORKFLOW_ANALYSIS_GUIDE.md
docs/reference/CLI.md
docs/reference/API.md
EXAMPLE-WORKFLOW-ANALYSIS-README.md
.gitignore
```

---

## Status

**COMPLETED** — 2026-03-31
