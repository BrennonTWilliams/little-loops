---
discovered_date: 2026-01-23
discovered_by: manual
---

# FEAT-111: Issue History Summary Command

## Summary

Add a minimal `ll-history` CLI command that provides a quick summary of completed issues using reliably available metadata: type counts, priority distribution, completion timeline, and discovery sources.

## Context

With 116+ completed issues, basic historical analysis would be valuable. This is the minimal first step before building more advanced analysis (see FEAT-110).

## Proposed Solution

### Components to Create

1. **Python Module**: `scripts/little_loops/issue_history.py`
   - Parse completed issues from `.issues/completed/`
   - Extract metadata: type, priority, completion date, discovery source
   - Calculate summary statistics
   - Output as formatted text or JSON

2. **CLI Entry Point**: `ll-history` command
   - `ll-history summary` - Show summary statistics
   - `ll-history summary --json` - JSON output for scripting

3. **Tests**: `scripts/tests/test_issue_history.py`

### Summary Output

```
Issue History Summary
=====================
Total Completed: 116
Date Range: 2026-01-06 to 2026-01-22 (16 days)
Velocity: 7.3 issues/day

By Type:
  BUG:  42 (36%)
  ENH:  51 (44%)
  FEAT: 23 (20%)

By Priority:
  P0:  2 ( 2%)
  P1:  8 ( 7%)
  P2: 28 (24%)
  P3: 56 (48%)
  P4: 18 (16%)
  P5:  4 ( 3%)

By Discovery Source:
  scan_codebase:  45 (39%)
  manual:         38 (33%)
  capture_issue:  33 (28%)
```

### Scope Boundaries

**In scope:**
- Type counts (BUG/ENH/FEAT) from filename
- Priority distribution (P0-P5) from filename
- Completion dates from git history or file mtime
- Discovery source from frontmatter `discovered_by`
- Basic velocity calculation

**Out of scope (see FEAT-110):**
- File hotspot detection
- Quality metrics (test/lint pass rates)
- AI-generated insights and recommendations
- Slash command and skill integration
- Multiple output formats (markdown, YAML)

## Impact

- **Priority**: P3 - Useful for understanding project health
- **Effort**: Small - ~200 lines, single module + CLI
- **Risk**: Low - Additive, read-only analysis

## Acceptance Criteria

- [x] `ll-history summary` shows type/priority/source breakdown
- [x] `ll-history summary --json` outputs machine-readable JSON
- [x] Handles empty `.issues/completed/` gracefully
- [x] Tests cover parsing and statistics calculation

## Related

- **Follow-up**: FEAT-110 (advanced analysis with hotspots, insights, slash command)

## Labels

`feature`, `analysis`, `cli`

---

**Priority**: P3 | **Created**: 2026-01-23

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_history.py`: New module with CompletedIssue and HistorySummary dataclasses, parsing functions, and summary formatters
- `scripts/little_loops/cli.py`: Added main_history() entry point function
- `scripts/pyproject.toml`: Registered ll-history CLI entry point
- `scripts/tests/test_issue_history.py`: 32 comprehensive tests for all functionality

### Verification Results
- Tests: PASS (32/32 new tests, 1507 total)
- Lint: PASS
- Types: PASS
- End-to-end: Verified against real .issues/completed/ with 116 issues
