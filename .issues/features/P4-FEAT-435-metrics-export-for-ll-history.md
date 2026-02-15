---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# FEAT-435: Metrics export for ll-history

## Summary

The `ll-history` command outputs formatted reports (text, JSON, YAML, markdown) but doesn't provide a dedicated export for raw metrics data. The underlying analysis modules calculate rich metrics (period trends, technical debt, agent effectiveness, hotspots, coupling) that could be exported for external analytics tools.

## Current Behavior

`ll-history analyze` and `ll-history summary` render human-readable reports. JSON output includes the full structure but isn't optimized for metrics consumption or dashboard integration.

## Expected Behavior

`ll-history export --format csv` or `ll-history export --metrics-only` outputs structured metrics in machine-readable formats (CSV, flat JSON) suitable for import into spreadsheets, dashboards, or analytics tools.

## Motivation

Development teams want to track productivity and quality metrics over time. Currently the data exists but is locked in markdown reports. CSV/flat-JSON export enables integration with tools like Google Sheets, Grafana, or custom dashboards without writing parsers.

## Use Case

A team lead runs `ll-history export --format csv --period monthly` to generate a CSV of monthly metrics (issues completed, avg resolution time, bug rate). They import this into a Google Sheet that auto-updates their team dashboard.

## Acceptance Criteria

- `ll-history export` subcommand exists
- Supports `--format csv` and `--format json-flat` output
- `--metrics-only` flag outputs only numeric metrics (no descriptions)
- `--period weekly|monthly|quarterly` controls time grouping
- CSV output has headers and is valid for spreadsheet import

## Proposed Solution

Add `export` subcommand to `ll-history`:

```python
def cmd_export(args: Namespace) -> int:
    analysis = run_analysis(args.period)
    if args.format == "csv":
        write_csv(analysis.metrics, sys.stdout)
    elif args.format == "json-flat":
        write_flat_json(analysis.metrics, sys.stdout)
    return 0
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — add `export` subcommand

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/analysis.py` — reuse existing analysis

### Similar Patterns
- Existing `--format` flag on `analyze` subcommand

### Tests
- Add test for CSV and flat-JSON output formats

### Documentation
- Update CLI help text

### Configuration
- N/A

## Implementation Steps

1. Add `export` subparser to history CLI
2. Implement CSV writer for metrics
3. Implement flat-JSON writer
4. Add `--metrics-only` filter
5. Add tests

## Impact

- **Priority**: P4 - Nice-to-have for analytics integration
- **Effort**: Small - Data already computed, just needs formatting
- **Risk**: Low - New subcommand, no existing behavior changed
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `history`, `cli`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4
