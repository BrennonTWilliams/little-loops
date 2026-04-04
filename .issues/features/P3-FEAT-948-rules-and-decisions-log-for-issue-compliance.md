---
discovered_date: 2026-04-04
discovered_by: capture-issue
---

# FEAT-948: Rules and Decisions Log for Issue Compliance

## Summary

Add a tracked and maintained rules and decisions log to ensure issues are compliant with project standards. Each entry records a timestamp, associated issue file, category, and labels. The log can be populated manually, auto-generated from completed or active issues, and used during automated validation, review, or refactoring passes.

## Current Behavior

There is no centralized log of project rules and decisions. Standards are encoded in templates and CLAUDE.md but are not tracked as individual, timestamped entries associated with specific issues. Compliance is verified informally during review commands.

## Expected Behavior

A dedicated rules and decisions log exists with structured entries. Each entry includes:
- Timestamp of when the rule/decision was established
- Associated issue file (if applicable)
- Category (e.g., naming, template structure, workflow, tooling)
- Labels for filtering and querying

The log can be created/updated through four paths:
1. Manually by the user
2. Auto-generated from completed issues (post-implementation learnings)
3. Auto-generated from open/active issues before implementation (pre-implementation decisions)
4. Auto-generated as part of automated validation, review, or refactoring workflows

## Motivation

As the issue count grows and workflows become more automated (ll-auto, ll-parallel, ll-sprint), there is increasing risk that newly captured or generated issues drift from established standards. A decisions log creates a machine-readable source of truth that automated commands can query during validation, making compliance enforceable rather than advisory.

## Proposed Solution

TBD - requires investigation

Key design decisions to resolve:
- Storage format: YAML/JSON sidecar file vs. markdown log vs. dedicated `.ll/decisions.yaml`
- Integration points: `capture-issue`, `ready-issue`, `verify-issues`, `format-issue` commands should be able to read and write entries
- CLI surface: a `ll-decisions` subcommand or subcommand of `ll-issues` for CRUD
- Auto-generation triggers: post-`manage-issue` completion hook and pre-implementation confidence check

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — may need to log decisions at capture time
- `skills/ready-issue/` — validation step could check against log
- `skills/verify-issues/` — can surface rule violations
- `scripts/little_loops/` — CLI entry point(s) for the new log

### Similar Patterns
- `.ll/ll-config.json` — structured config as a model for the log format
- `scripts/little_loops/issues.py` — existing issue management CLI patterns

### Tests
- TBD — unit tests for log CRUD; integration tests for auto-generation from completed issues

### Documentation
- `docs/ARCHITECTURE.md` — document new log as a persistence layer
- `.claude/CLAUDE.md` — update Key Directories and CLI Tools sections

### Configuration
- `.ll/ll-config.json` — may need a `decisions` config block (enabled, log path, auto-generate triggers)

## Implementation Steps

1. Design log schema (entry format, storage file location, indexing strategy)
2. Implement core CRUD for the log (Python module in `scripts/little_loops/`)
3. Add CLI surface (`ll-issues decisions` subcommand or dedicated `ll-decisions`)
4. Integrate manual entry creation into `capture-issue` workflow
5. Add auto-generation from completed issues (post-`manage-issue` hook or `ll-history` integration)
6. Add auto-generation from active issues (pre-implementation step in `confidence-check` or `ready-issue`)
7. Add validation/query support to `verify-issues` and `ready-issue`
8. Update docs and CLAUDE.md

## Use Case

A user runs `/ll:ready-issue 948`. The command checks the rules and decisions log and finds an existing decision: "Issue filenames must use the `P[0-5]-[TYPE]-[NNN]-slug.md` format (decided 2025-11-01, FEAT-200)." It surfaces this as a compliance check result, confirming the issue under review is compliant — without the user needing to manually cross-reference templates.

## Acceptance Criteria

- [ ] A structured log file exists (e.g., `.ll/decisions.yaml`) with schema-validated entries
- [ ] Each entry has: `timestamp`, `issue` (optional), `category`, `labels[]`, `rule` (text)
- [ ] Manual entry creation is supported via CLI or capture-issue flow
- [ ] Auto-generation from completed issues is triggered post-implementation
- [ ] Auto-generation from active issues is available as a pre-implementation step
- [ ] `verify-issues` and/or `ready-issue` can query the log and surface violations
- [ ] Automated validation, review, and refactoring passes can read the log
- [ ] Tests cover CRUD and auto-generation paths

## API/Interface

```python
# Example entry schema (decisions.yaml)
# - timestamp: "2026-04-04T00:00:00Z"
#   issue: "P3-FEAT-948-rules-and-decisions-log-for-issue-compliance.md"  # optional
#   category: "workflow"
#   labels: ["issue-compliance", "automation"]
#   rule: "All issue files must pass ready-issue validation before sprint inclusion."

# Example CLI
# ll-issues decisions list [--category=workflow] [--label=automation]
# ll-issues decisions add --category=naming --rule="..." [--issue=FEAT-948]
# ll-issues decisions generate --from=completed  # auto-generate from completed issues
```

## Impact

- **Priority**: P3 - Governance improvement; important for scaling automation but not blocking current workflows
- **Effort**: Large - New persistence layer, CLI, schema design, and multi-command integration
- **Risk**: Low - Additive feature; no changes to existing issue files or commands required for MVP
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design context for new persistence layer |
| `.claude/CLAUDE.md` | Key Directories and CLI Tools need updates |
| `CONTRIBUTING.md` | Development guidelines for new module |

## Labels

`feature`, `issue-management`, `automation`, `compliance`, `captured`

---

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d50b6641-c597-41dc-894f-47b323d241b9.jsonl`
