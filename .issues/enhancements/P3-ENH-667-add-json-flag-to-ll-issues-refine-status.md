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

1. In `scripts/little_loops/cli/issues/__init__.py`, add `--json` boolean argument to the `refine-status` subparser (alongside existing `--format`).
2. In `cmd_refine_status` (`refine_status.py`), check `getattr(args, "json", False)` and treat it as equivalent to `fmt == "json"`.
3. Output shape: JSON array (not NDJSON) when `--json` is used. `--format json` keeps NDJSON for backwards compatibility.
4. Update help text and epilog example in `__init__.py`.
5. Add/update tests in `scripts/tests/` for `--json` flag on `refine-status`.

## Related Files

- `scripts/little_loops/cli/issues/__init__.py` — argument registration (lines 91-110)
- `scripts/little_loops/cli/issues/refine_status.py` — `cmd_refine_status` (lines 155-355)
- `scripts/little_loops/cli/issues/list_cmd.py` — reference implementation for `--json` flag

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

## Status

**Active** | P3 | ENH

## Session Log
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/534f29dc-9078-4565-b6a5-14cb33271b6f.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
