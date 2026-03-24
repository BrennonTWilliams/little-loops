---
id: ENH-875
type: ENH
priority: P3
status: open
discovered_date: 2026-03-24
discovered_by: capture-issue
---

# ENH-875: Add --auto flag to commit skill

## Summary

The `/ll:commit` skill should accept an `--auto` flag that suppresses all user interactivity and makes the best decision it can autonomously — staging files, writing commit messages, and executing without prompting.

## Current Behavior

`/ll:commit` always pauses to present its plan to the user and ask for gitignore approval before executing any git operations. There is no way to run it non-interactively.

## Expected Behavior

When invoked with `--auto`, the skill skips all `AskUserQuestion` prompts and proceeds with the best available decision:
- Skips the gitignore suggestions step (or silently applies obvious patterns)
- Stages and commits without presenting a plan for approval
- Outputs a summary of what it did after the fact

## Motivation

Automation contexts (`ll-auto`, `ll-parallel`, `ll-sprint`, FSM loops) need to commit changes without human approval gates. Today these pipelines cannot use `/ll:commit` at all — they either call raw `git` commands or skip committing entirely. An `--auto` flag would make the skill usable as a building block in fully automated workflows.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- `commands/commit.md` — add `--auto` flag parsing and conditional branching around `AskUserQuestion` calls

### Dependent Files (Callers/Importers)
- Any skill or loop state that invokes `/ll:commit` could pass `--auto`
- TBD - grep for `ll:commit` references in skills/loops

### Similar Patterns
- `--auto` flag already used in `/ll:confidence-check` and `/ll:format-issue`; follow the same parsing convention

### Tests
- TBD - identify test files to update

### Documentation
- TBD - update `commands/commit.md` Examples section to show `--auto` usage

### Configuration
- N/A

## Implementation Steps

1. Add `--auto` flag parsing at the top of `commands/commit.md` (follow `--quick` pattern already present)
2. Wrap the gitignore `AskUserQuestion` block in a `if not AUTO_MODE` guard; in auto mode silently skip or apply all patterns
3. Wrap the plan-presentation / approval step in a `if not AUTO_MODE` guard; in auto mode log the plan and proceed
4. Verify output still clearly reports what commits were created

## API/Interface

```bash
# Non-interactive commit from automation context
/ll:commit --auto
```

## Impact

- **Priority**: P3 - Useful for automation but no existing workflows are broken without it
- **Effort**: Small - One command file, pattern already established by other `--auto` flags
- **Risk**: Low - Auto mode is opt-in; existing interactive behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `commit-skill`, `automation`, `captured`

## Status

**Open** | Created: 2026-03-24 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c23589c-5619-4975-90e9-77c587e90773.jsonl`
