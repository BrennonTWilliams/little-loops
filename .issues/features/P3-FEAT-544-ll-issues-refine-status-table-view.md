---
discovered_date: 2026-03-03T00:00:00Z
discovered_by: capture-issue
---

# FEAT-544: `ll-issues` Refinement Status Table View

## Summary

Add a new `ll-issues refine-status` subcommand (or `ll-issues list --refinement`) that renders all open/active issues in a table where each column represents a refinement command or skill found in the `## Session Log` section. Issues are sorted by refinement depth — the more commands have touched an issue, the higher it appears.

## Current Behavior

`ll-issues` has no `refine-status` subcommand. The only way to assess an issue's refinement state is to open each file individually and read its `## Session Log`. With a growing backlog there is no at-a-glance view showing which issues have been through `/ll:refine-issue`, `/ll:ready-issue`, `/ll:confidence-check`, or other commands.

## Expected Behavior

`ll-issues refine-status` renders a table of all active issues. Each column maps to a distinct `/ll:<name>` command found across Session Log entries (derived dynamically — no hardcoded list). A `Total` column sorts issues descending by refinement depth; `Ready` and `OutConf` columns surface the numeric `confidence_score` and `outcome_confidence` values from frontmatter.

## Motivation

As the issue backlog grows, it becomes hard to see which issues are "implementation-ready" vs. just created. The Session Log already records every command that has touched an issue (`/ll:scan-codebase`, `/ll:refine-issue`, `/ll:tradeoff-review-issues`, `/ll:ready-issue`, `/ll:confidence-check`, etc.), but there is no way to see this at a glance across all issues. A refinement table makes sprint planning and backlog triage instant.

## Use Case

**Who**: Developer or tech lead managing a growing issue backlog.

**Context**: About to start a sprint planning session with 20+ active issues; unsure which have been through the full refinement pipeline.

**Goal**: Identify at a glance which issues are implementation-ready and which still need `/ll:refine-issue`, `/ll:ready-issue`, or `/ll:confidence-check` passes.

**Outcome**: A ranked table sorted by refinement depth makes the decision instant:

```
ID       Pri  Title                          scan  refine  tradeoff  ready  confidence  Ready  OutConf  Total
BUG-525  P2   TOCTOU race condition           ✓     ✓        ✓        ✓        ✓          92     78       5
ENH-534  P2   Fatal error loop stop signals   ✓     ✓        ✓        —        —           —      —       3
FEAT-543 P4   ll-loop history filtering       ✓     —        —        —        —           —      —       1
FEAT-544 P3   ll-issues refine-status table   —     —        —        —        —           —      —       0
```

`Ready` and `OutConf` show the numeric `confidence_score` and `outcome_confidence` values written to frontmatter by `/ll:confidence-check` (0–100).

## Acceptance Criteria

- `ll-issues refine-status` prints a table of all active issues (excludes completed/deferred)
- Columns are dynamically derived from the distinct `/ll:<name>` entries found across all Session Log sections — no hardcoded list
- Each column shows `✓` if that command appears in the issue's Session Log, `—` if not
- Two fixed numeric columns — `Ready` (`confidence_score`) and `OutConf` (`outcome_confidence`) — show the values written to YAML frontmatter by `/ll:confidence-check`; display `—` if absent
- A `Total` column shows the count of distinct commands that have touched the issue
- Issues are sorted descending by `Total`, then by priority as a tiebreaker
- `--type BUG|FEAT|ENH` filter is supported (consistent with `ll-issues list`)
- `--format json` outputs the same data as newline-delimited JSON for scripting
- Table respects terminal width — truncates long titles with `…` rather than wrapping

## API/Interface

```bash
ll-issues refine-status                   # All active issues, sorted by refinement depth
ll-issues refine-status --type BUG        # Only bugs
ll-issues refine-status --format json     # JSON output
```

Example JSON record:
```json
{"id": "BUG-525", "priority": "P2", "title": "TOCTOU race condition", "commands": ["scan-codebase", "refine-issue", "tradeoff-review-issues", "ready-issue", "confidence-check"], "confidence_score": 92, "outcome_confidence": 78, "total": 5}
```

## Implementation Steps

1. Extend `issue_parser.py` with `parse_session_log(path) -> list[str]` and frontmatter score extraction (`confidence_score`, `outcome_confidence`)
2. Implement `scripts/little_loops/cli/issues/refine_status.py` — aggregate data, derive dynamic column set, sort, and render table with terminal-width truncation
3. Register `refine-status` subparser in `__init__.py` with `--type` and `--format` flags (following `list_cmd.py` pattern)
4. Add `--format json` path to emit newline-delimited JSON records
5. Write tests in `scripts/tests/test_refine_status.py` and verify against real issue files

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `refine-status` subparser
- `scripts/little_loops/issue_parser.py` — add `parse_session_log()` and frontmatter score extraction

### Files to Create
- `scripts/little_loops/cli/issues/refine_status.py` — new subcommand module

### Dependent Files (Callers/Importers)
- N/A — new additive subcommand; no existing callers

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` as reference for issue iteration and filtering
- `scripts/little_loops/cli/issues/impact_effort_cmd.py` — table rendering pattern (if present)

### Tests
- `scripts/tests/test_refine_status.py` — new test file covering Session Log parsing, dynamic column derivation, sort order, and JSON output

### Documentation
- CLI help text auto-generated via argparse `description`
- `docs/reference/API.md` — update `ll-issues` subcommand list if documented

### Configuration
- N/A

## Impact

- **Priority**: P3 — Valuable for sprint planning and backlog triage but not blocking any workflow
- **Effort**: Large — Non-trivial: dynamic column derivation, terminal-width-aware rendering, Session Log parsing, dual output formats (table + JSON)
- **Risk**: Medium — Session Log format variations across issues could produce unexpected column names; frontmatter parsing must handle missing fields gracefully
- **Breaking Change**: No — fully additive new subcommand

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/issues/list_cmd.py` | Pattern to follow for issue listing |
| `scripts/little_loops/cli/issues/__init__.py` | Where to register new subparser |
| `scripts/little_loops/issue_parser.py` | Issue parsing utilities to extend |

## Session Log

- `/ll:capture-issue` — 2026-03-03T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ace9385-297c-4f88-9e68-d349c8dea381.jsonl`
- `/ll:format-issue` — 2026-03-03T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26ee613e-e461-449f-abe5-936627dc59aa.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P3
`feat`, `ll-issues`, `refinement`, `table-view`, `capture-issue`
