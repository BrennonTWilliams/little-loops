---
discovered_date: 2026-03-12
discovered_by: capture-issue
---

# ENH-677: Add count sub-command to ll-issues CLI

## Summary

Add `ll-issues count` (alias `c`) sub-command that outputs active issue counts by type and priority, with `--json` flag for machine-readable output. Designed for consumption by FSM loop evaluators to track issue volume changes between iterations.

## Current Behavior

`ll-issues list` computes and displays issue counts, but they're embedded in formatted table output. There's no way to get a clean, parseable count without parsing the list output. FSM loops that need to check "how many new issues since last iteration" have no simple primitive.

## Expected Behavior

```bash
# Simple total count
ll-issues count                    # → 12

# JSON output for FSM loops
ll-issues count --json
# → {"total": 12, "by_type": {"BUG": 3, "FEAT": 7, "ENH": 2}, "by_priority": {"P0": 1, "P1": 2, "P2": 3, "P3": 4, "P4": 2, "P5": 0}}

# Filtered counts
ll-issues count --type BUG         # → 3
ll-issues count --priority P0,P1   # → 3
```

## Motivation

FSM loops need lightweight, machine-readable issue counts to make state transition decisions (e.g., "if new bugs > 0, transition to triage"). Currently, loops would need to parse `ll-issues list` output or call `find_issues()` directly from Python. A dedicated `count` sub-command provides a clean CLI primitive that keeps loop evaluators simple.

## Proposed Solution

Add `cli/issues/count.py` following the same pattern as `list_cmd.py`:

1. Call `find_issues(config, type_prefixes=...)` with optional `--type` filter
2. Apply `--priority` filter in-memory
3. Output modes:
   - Default: print total count as integer (single line)
   - `--json`: print JSON object with `total`, `by_type`, and `by_priority` breakdowns
4. Register sub-command in `cli/issues/__init__.py` with alias `c`

Key functions to reference:
- `find_issues()` in `issue_parser.py` — reuse existing issue loading
- `print_json()` utility — reuse for JSON output
- `cmd_list()` in `list_cmd.py` — pattern to follow for argparser setup

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `count` sub-command and alias `c`

### New Files
- `scripts/little_loops/cli/issues/count.py` — `cmd_count(config, args)` implementation

### Dependent Files (Callers/Importers)
- N/A — new sub-command, no existing callers

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py` — follows same structure (argparser, find_issues, filter, output)

### Tests
- `scripts/tests/` — add test for count sub-command output (plain and JSON modes)

### Documentation
- `CLAUDE.md` — update CLI tools description for ll-issues
- `docs/reference/API.md` — add count sub-command reference

### Configuration
- N/A

## Implementation Steps

1. Create `count.py` with `register_parser()` and `cmd_count()` following `list_cmd.py` pattern
2. Register sub-command in `__init__.py` dispatcher
3. Add `--json`, `--type`, `--priority` arguments
4. Add tests for plain output, JSON output, and filtered counts
5. Update CLI documentation

## API/Interface

```python
# cli/issues/count.py
def register_parser(subparsers) -> None:
    """Register 'count' sub-command with alias 'c'."""

def cmd_count(config: BRConfig, args: argparse.Namespace) -> int:
    """Print active issue counts. Returns exit code."""
```

```bash
# CLI interface
ll-issues count [--type BUG|FEAT|ENH] [--priority P0,P1,...] [--json] [--config PATH]
```

## Scope Boundaries

- Read-only — no issue modification
- Active issues only (not completed/deferred) — consistent with `list`
- No historical tracking (delta from last run) — that's the loop's responsibility
- No completed/deferred counts — could be added later if needed

## Impact

- **Priority**: P3 - Quality of life improvement, enables cleaner FSM loop evaluators
- **Effort**: Small - ~50 lines of new code, follows existing patterns exactly
- **Risk**: Low - Additive change, no existing behavior modified
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17cce4eb-7ba6-4d65-a800-c3c0f2ad0a91.jsonl`

---

**Open** | Created: 2026-03-12 | Priority: P3
