---
discovered_date: 2026-03-10
discovered_by: capture-issue
---

# ENH-667: Add `--json` flag to `ll-issues refine-status`

## Current Behavior

`ll-issues refine-status` supports machine-readable output via `--format json`, which outputs one JSON record per line (NDJSON). However, `ll-issues list` uses `--json` (a boolean flag) for its JSON mode. The inconsistency means scripts and FSM loops must use different flag styles depending on which subcommand they call.

## Expected Behavior

`ll-issues refine-status` accepts a `--json` boolean flag as a shorthand alias for `--format json`, matching the interface of `ll-issues list`. Both flags can coexist: `--json` sets format to JSON, `--format json` continues to work as before.

`--json` outputs a JSON array (matching `list --json`), not NDJSON. `--format json` continues to output NDJSON for backwards compatibility. The two flags intentionally produce different shapes — this is documented in help text.

## Summary

Add `--json` flag to `ll-issues refine-status` for interface consistency with `ll-issues list`.

## Motivation

FSM loops and automation scripts that use `ll-issues list --json` expect a consistent `--json` flag pattern across all `ll-issues` subcommands. Requiring `--format json` for `refine-status` is a papercut that breaks muscle memory and makes shell pipelines inconsistent.

## Implementation Steps

1. **`__init__.py:110`** — Add `--json` boolean arg after the existing `--no-key` argument in the `refine-status` subparser:
   ```python
   refine_s.add_argument(
       "--json",
       action="store_true",
       default=False,
       help="Output as JSON array. Matches ll-issues list --json interface. (--format json outputs NDJSON instead)",
   )
   ```
2. **`__init__.py:47`** — Add epilog example: `%(prog)s refine-status --json`
3. **`refine_status.py:9`** — Add `print_json` to the output import line:
   ```python
   from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json, terminal_width
   ```
4. **`refine_status.py:203`** — Insert `--json` check **before** the existing `fmt` check; use `print_json()` for JSON array output:
   ```python
   fmt = getattr(args, "format", "table")
   use_json_array = getattr(args, "json", False)

   if use_json_array:
       print_json([
           {
               "id": issue.issue_id,
               "priority": issue.priority,
               "title": issue.title,
               "source": issue.discovered_by,
               "commands": issue.session_commands,
               "confidence_score": issue.confidence_score,
               "outcome_confidence": issue.outcome_confidence,
               "total": len(issue.session_commands),
               "normalized": is_normalized(issue.path.name),
               "formatted": is_formatted(issue.path),
               "refine_count": issue.session_command_counts.get("/ll:refine-issue", 0),
           }
           for issue in sorted_issues
       ])
       return 0

   if fmt == "json":  # existing NDJSON path — unchanged
       ...
   ```
5. **`scripts/tests/test_refine_status.py`** — Add `TestRefineStatusJsonFlag` class after the existing `TestRefineStatusJson` class (line 683+). Follow the pattern from `test_issues_cli.py:256-325` (`patch.object(sys, "argv", [...])`, `capsys.readouterr()`, `json.loads(out)` asserts list). Key test cases:
   - `test_json_flag_outputs_array` — verify output parses as a JSON list `[...]`
   - `test_json_flag_fields` — verify each record has the same fields as `--format json`
   - `test_json_flag_no_color_codes` — verify no ANSI escape sequences in output
   - `test_json_flag_and_format_json_coexist` — verify `--json --format json` doesn't error (last wins or `--json` takes precedence)

## Related Files

- `scripts/little_loops/cli/issues/__init__.py` — argument registration (lines 91-110)
- `scripts/little_loops/cli/issues/refine_status.py` — `cmd_refine_status` (lines 155-355)
- `scripts/little_loops/cli/issues/list_cmd.py` — reference implementation for `--json` flag

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py:91-110` — add `--json` boolean arg to `refine-status` subparser; update epilog at line 47
- `scripts/little_loops/cli/issues/refine_status.py:9` — add `print_json` to the `cli.output` import; add `--json` check at line 203 (before `fmt = getattr(args, "format", "table")`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:135-136` — dispatches to `cmd_refine_status(config, args)`

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:36-49` — `getattr(args, "json", False)` + `print_json([...])` — exact pattern to follow
- `scripts/little_loops/cli/output.py:97-99` — `print_json(data)` utility: `print(json.dumps(data, indent=2))`

### Tests
- `scripts/tests/test_refine_status.py:683` — existing `TestRefineStatusJson` class (covers `--format json` NDJSON); add new `TestRefineStatusJsonFlag` class after it
- `scripts/tests/test_issues_cli.py:256-325` — `--json` test patterns for `list` subcommand (reference for new tests)

### Documentation
- `scripts/little_loops/cli/issues/__init__.py:30-48` — epilog; add `%(prog)s refine-status --json` example

## API/Interface

New flag added to `refine-status` subparser:

```python
# In __init__.py refine-status subparser
parser_refine_status.add_argument(
    "--json",
    action="store_true",
    default=False,
    help="Output as JSON array (equivalent to --format json). Matches ll-issues list --json interface.",
)
```

Output shape: JSON array (matching `ll-issues list --json`) — not NDJSON. When `--json` is set, output is a `[...]` array of objects rather than one object per line.

## Scope Boundaries

- **In scope**: Add `--json` flag to `refine-status` only; standardize its output to JSON array
- **Out of scope**: Adding `--json` to other `ll-issues` subcommands (separate issues if needed)
- **Out of scope**: Deprecating or removing `--format json`; the flag remains and continues to work
- **Out of scope**: Refactoring the underlying format/output engine beyond wiring the alias
- **Breaking change**: `--format json` currently outputs NDJSON; `--json` will output JSON array. The `--format json` behavior is preserved as-is (NDJSON) to avoid breaking existing scripts — only `--json` uses array format.

## Impact

- **Priority**: P3 — Convenience/consistency fix; unblocks clean FSM loop scripting but not critical path
- **Effort**: Small — One argument registration, one conditional in `cmd_refine_status`, output shape selection, tests
- **Risk**: Medium — Introducing `--json` as JSON array while `--format json` stays NDJSON creates a subtle inconsistency; scripts must know which flag gives which shape. Document clearly.
- **Breaking Change**: No — additive only; existing `--format json` behavior unchanged

## Labels

`enhancement`, `cli`, `dx`, `captured`

---

## Resolution

**Status**: Completed
**Date**: 2026-03-10

### Changes Made
- `scripts/little_loops/cli/issues/__init__.py`: Added `--json` boolean arg to `refine-status` subparser; added `%(prog)s refine-status --json` example to epilog
- `scripts/little_loops/cli/issues/refine_status.py`: Added `print_json` to `cli.output` import; added `--json` check before `fmt` check — outputs JSON array via `print_json()`
- `scripts/tests/test_refine_status.py`: Added `TestRefineStatusJsonFlag` class with 4 tests covering array output, field verification, no color codes, and coexistence with `--format json`

### Verification
- All 4 new tests pass
- All existing `TestRefineStatusJson` tests (NDJSON path) continue to pass

## Status

**Completed** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2d9af7e-2193-4292-8ae7-dc0e052f33b8.jsonl`
- `/ll:ready-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/85130897-5362-4131-a548-590ccb343ee9.jsonl`
- `/ll:manage-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c8f8071-e5fb-4ae8-bb16-8e133482ff0f.jsonl`

## Blocks
- FEAT-543
- ENH-507
- ENH-470
