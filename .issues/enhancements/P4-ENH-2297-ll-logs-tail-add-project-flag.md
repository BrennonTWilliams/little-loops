---
id: ENH-2297
title: "Add --project DIR flag to ll-logs tail for cross-project consistency"
type: ENH
priority: P4
status: open
captured_at: "2026-06-25T18:52:54Z"
discovered_date: "2026-06-25"
discovered_by: capture-issue
---

# ENH-2297: Add --project DIR flag to ll-logs tail for cross-project consistency

## Summary

`ll-logs extract` accepts `--project DIR` to operate on an arbitrary project without changing directory, but `ll-logs tail` is CWD-locked — it calls `BRConfig(Path.cwd())` to resolve the loops dir and offers no way to override it. The two subcommands should be consistent: `tail` should accept the same `--project DIR` flag so a loop running in another project (e.g. `loop-sandbox`) can be tailed from any working directory.

## Current Behavior

`ll-logs tail --loop <name>` always resolves the loops directory from the current working directory via `BRConfig(Path.cwd())` (`cli/logs.py`, `_cmd_tail` / `main` at the `tail` dispatch block). There is no `--project` flag; the only workaround is `cd /path/to/other-project && ll-logs tail --loop <name>`.

## Expected Behavior

`ll-logs tail --loop <name> --project /path/to/other-project` resolves the loops directory from the given project root instead of CWD, consistent with `ll-logs extract --project DIR`.

## Motivation

When working in one project (e.g. `little-loops`) and running a loop in another (e.g. `loop-sandbox`), there is no way to tail the remote loop without leaving the current shell context. The inconsistency is confusing: `extract` supports cross-project use but `tail` does not, with no documented reason for the difference. This appears to be an oversight rather than a deliberate design choice.

## Proposed Solution

1. Add an optional `--project DIR` argument to the `tail` subparser in `_build_parser` (alongside the existing `--loop` argument).
2. In the `tail` dispatch block in `main`, pass `args.project` (defaulting to `Path.cwd()`) to `BRConfig` instead of hardcoding `Path.cwd()`:

```python
# Before (logs.py, tail dispatch):
config = BRConfig(Path.cwd())
loops_dir = Path(config.loops.loops_dir)
return _cmd_tail(args, loops_dir)

# After:
project_root = Path(args.project) if getattr(args, "project", None) else Path.cwd()
config = BRConfig(project_root)
loops_dir = Path(config.loops.loops_dir)
return _cmd_tail(args, loops_dir)
```

3. The `--project` flag should be optional; omitting it preserves current CWD behaviour.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_build_parser` (tail subparser), `main` (tail dispatch block ~line 1935–1938)

### Dependent Files (Callers/Importers)
- N/A — `_cmd_tail` already receives `loops_dir` as a parameter; no signature change needed

### Similar Patterns
- `ll-logs extract` (`_cmd_extract`) already accepts and uses `args.project` — follow the same pattern

### Tests
- `scripts/tests/test_builtin_loops.py` or logs test file — add a test that passes `--project` to `tail` and verifies `loops_dir` resolves from the given root, not CWD

### Documentation
- `docs/reference/CLI.md` — update `ll-logs tail` usage line to show `--project` flag

### Configuration
- N/A

## Implementation Steps

1. Add `tail_parser.add_argument("--project", metavar="DIR", help="Project root to tail loops from (default: CWD)")` in `_build_parser`.
2. Update the `tail` dispatch block in `main` to use `args.project` when set.
3. Add or extend a test asserting cross-project resolution.
4. Update CLI reference docs.

## Impact

- **Priority**: P4 — Workaround exists (`cd /path && ll-logs tail`); affects users running loops in a project other than their current shell CWD
- **Effort**: Small — Two-line patch to `_build_parser` and the `tail` dispatch in `main`; mirrors the existing `extract --project` pattern exactly
- **Risk**: Low — Optional flag with CWD fallback preserves all existing behaviour; no breaking change
- **Breaking Change**: No

## Labels

`cli`, `ll-logs`, `consistency`

## Status

**Open** | Created: 2026-06-25 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-06-25T18:56:06 - `4bf59de2-23a4-414b-a149-93b27c0b197d.jsonl`
- `/ll:capture-issue` - 2026-06-25T18:52:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0eaae7ef-edbe-497f-bc91-15b8fc518594.jsonl`
