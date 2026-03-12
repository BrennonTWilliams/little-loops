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
ll-issues count --priority P0      # → 1
```

## Motivation

FSM loops need lightweight, machine-readable issue counts to make state transition decisions (e.g., "if new bugs > 0, transition to triage"). Currently, loops would need to parse `ll-issues list` output or call `find_issues()` directly from Python. A dedicated `count` sub-command provides a clean CLI primitive that keeps loop evaluators simple.

## Proposed Solution

Add `cli/issues/count_cmd.py` following the same pattern as `list_cmd.py`:

1. Call `find_issues(config, type_prefixes=...)` with optional `--type` filter
2. Apply `--priority` filter in-memory (single choice, matching `list` interface)
3. Output modes:
   - Default: print total count as integer (single line)
   - `--json`: print JSON object with `total`, `by_type`, and `by_priority` breakdowns
4. Register sub-command inline in `cli/issues/__init__.py` with alias `c`

Key functions to reference:
- `find_issues()` at `issue_parser.py:597` — reuse existing issue loading (returns `list[IssueInfo]` sorted by priority)
- `print_json()` at `cli/output.py:97` — reuse for JSON output (`json.dumps(data, indent=2)`)
- `cmd_list()` at `list_cmd.py:14` — pattern to follow for `--type`/`--priority`/`--json` handling

**Note**: There is no `register_parser()` function pattern in this codebase. All sub-command registration is done inline in `main_issues()` at `__init__.py:52-117`. The `cmd_*` functions only take `(config, args)` and return `int`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `count` sub-command and alias `c`
  - Add lazy import at lines 17–22 block: `from .count_cmd import cmd_count`
  - Add parser registration after line 90 (after `impact-effort` block): `subs.add_parser("count", aliases=["c"], ...)`
  - Add dispatch branch at lines 132–143 block: `if args.command == "count": return cmd_count(config, args)`
  - Update epilog string at lines 31–48 to include `count` sub-command

### New Files
- `scripts/little_loops/cli/issues/count_cmd.py` — `cmd_count(config: BRConfig, args: argparse.Namespace) -> int`

### Dependent Files (Callers/Importers)
- N/A — new sub-command, no existing callers

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:14-77` — closest pattern: `--type`/`--priority`/`--json` flags with `find_issues()` + post-filter
- `scripts/little_loops/cli/issues/refine_status.py:171-172` — second `--type` + `--json` example
- `scripts/little_loops/cli/issues/next_id.py:11-24` — minimal `cmd_*` pattern (no args needed beyond config)

### Tests
- `scripts/tests/test_issues_cli.py` — add `TestIssuesCLICount` class following existing class-per-subcommand pattern
  - Uses `sys.argv` patching: `patch.object(sys, "argv", ["ll-issues", "count", "--config", str(temp_project_dir)])`
  - Shared fixtures from `conftest.py`: `temp_project_dir` (line 56), `sample_config` (line 66), `issues_dir` (line 124)
  - JSON assertions: `json.loads(captured.out)` then validate structure

### Documentation
- `docs/reference/CLI.md` — add count sub-command reference
- `docs/reference/API.md` — add count sub-command reference

### Configuration
- N/A

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/count_cmd.py` with `cmd_count(config, args)` following `list_cmd.py:14-77` pattern
   - Defer `find_issues` import inside function body (matches convention at `list_cmd.py:15`)
   - Use `getattr(args, "type", None)` guard pattern (matches `list_cmd.py:26`)
   - Default output: `print(len(issues))` — single integer line
   - `--json` output via `print_json({"total": N, "by_type": {...}, "by_priority": {...}})`
2. Register sub-command inline in `__init__.py:52-117` block:
   - Add `from .count_cmd import cmd_count` to lazy imports at lines 17–22
   - Add `subs.add_parser("count", aliases=["c"], help="Count active issues")` with `--type`, `--priority`, `--json` args
   - Add `if args.command == "count": return cmd_count(config, args)` to dispatch at lines 132–143
3. Add `TestIssuesCLICount` class to `scripts/tests/test_issues_cli.py`:
   - Test plain output (assert `captured.out.strip()` is a number)
   - Test `--json` output (parse JSON, validate `total`/`by_type`/`by_priority` keys)
   - Test `--type BUG` filter (count matches filtered total)
   - Test `--priority P1` filter
   - Use existing `issues_dir` fixture from `conftest.py:124` (provides 3 BUGs + 2 FEATs)
4. Update `docs/reference/CLI.md` with count sub-command usage

## API/Interface

```python
# cli/issues/count_cmd.py
def cmd_count(config: BRConfig, args: argparse.Namespace) -> int:
    """Print active issue counts. Returns exit code 0."""
```

Note: No `register_parser()` — registration is inline in `__init__.py` (codebase convention).

```bash
# CLI interface
ll-issues count [--type BUG|FEAT|ENH] [--priority P0|P1|P2|P3|P4|P5] [--json] [--config PATH]
```

Note: `--priority` accepts a single value (matching `list` sub-command convention), not comma-separated.

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
- `/ll:refine-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/654f36d5-1586-4900-9e28-5609b1f156c7.jsonl`
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53470d3c-3588-4319-9e16-707a874f8979.jsonl`

---

## Resolution

- Created `scripts/little_loops/cli/issues/count_cmd.py` with `cmd_count()` following `list_cmd.py` pattern
- Registered `count` sub-command (alias `c`) in `__init__.py` with `--type`, `--priority`, `--json` flags
- Added 7 tests in `TestIssuesCLICount` class covering plain output, filters, JSON, empty project, and alias
- Updated `docs/reference/CLI.md` and `docs/reference/API.md`

**Completed** | Created: 2026-03-12 | Resolved: 2026-03-12 | Priority: P3
