---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-386: Add command cross-reference validation to audit_claude_config

## Summary

Add a cross-reference validation check to `audit_claude_config` that verifies commands listed in skill files match the commands defined in `help.md`. This prevents skill documentation from drifting out of sync when commands are added, renamed, or removed.

## Current Behavior

`audit_claude_config` audits skills for description quality, trigger keywords, and frontmatter completeness, but does not verify that commands referenced within skill content actually exist in the project's command reference (`commands/help.md`).

## Expected Behavior

During skill auditing (Wave 1) or cross-component consistency checks (Wave 2), `audit_claude_config` should extract command references from skill files (e.g., `/ll:scan_codebase`, `/ll:manage_issue`) and verify each one exists in `commands/help.md`. Unrecognized commands should be flagged as warnings.

## Motivation

The `issue-workflow` skill recently drifted significantly out of sync — referencing outdated flags and missing 11+ commands. A cross-reference check would have caught this drift during routine `audit_claude_config` runs. BUG-358 (skill references nonexistent command) is another instance of the same class of problem.

## Proposed Solution

Add a new validation step to the skill auditing phase in `audit_claude_config`:

1. Parse `commands/help.md` to build a set of valid command names
2. For each skill file, extract `/ll:*` references from the content body (below frontmatter)
3. Compare extracted references against the valid command set
4. Report unknown commands as warnings with file path and line number

This fits naturally into the existing Wave 2 consistency checks alongside agent/command cross-references.

## Integration Map

### Files to Modify
- `commands/audit_claude_config.md` — add cross-reference validation step to skill auditing

### Dependent Files (Callers/Importers)
- N/A — this is a command prompt, not code

### Similar Patterns
- Existing Wave 2 cross-checks in `audit_claude_config` (agent tool validation, MCP reference checks)

### Tests
- N/A — command behavior, not Python code

### Documentation
- `commands/help.md` — update `audit_claude_config` description if scope text changes
- `docs/ARCHITECTURE.md` — note new validation in audit pipeline if documented there

### Configuration
- N/A

## Implementation Steps

1. Add command name extraction from `help.md` as a validation data source
2. Add `/ll:*` reference extraction from skill file content
3. Add cross-reference comparison and warning output
4. Integrate into Wave 2 consistency check reporting

## Impact

- **Priority**: P3 - Prevents documentation drift but not blocking
- **Effort**: Small - Pattern already exists in Wave 2 cross-checks
- **Risk**: Low - Additive check, no existing behavior changes
- **Breaking Change**: No

## Scope Boundaries

- Only validates `/ll:*` command references in skill files against `help.md`
- Does NOT validate flag/argument accuracy (e.g., `--deep` existing for a command)
- Does NOT validate command references in agent files (could be a follow-up)

## Success Metrics

- `audit_claude_config` catches stale command references in skills (like the issue-workflow drift)
- Zero false positives on current skill files after the update we just made

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Audit pipeline design |
| guidelines | CONTRIBUTING.md | Command addition workflow |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0d92ce3-b9a6-4888-8b14-5f5d2b2b2715.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
