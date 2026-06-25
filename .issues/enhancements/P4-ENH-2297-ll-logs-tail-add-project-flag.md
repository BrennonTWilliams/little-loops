---
id: ENH-2297
title: Add --project DIR flag to ll-logs tail for cross-project consistency
type: ENH
priority: P4
status: open
captured_at: '2026-06-25T18:52:54Z'
discovered_date: '2026-06-25'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 91
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 25
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

> _Codebase research note_: Declare `type=Path` on the argument (as `eval-export` does at `logs.py:1871`) so `args.project` is already a `Path | None` — the `Path(args.project)` wrapper in the dispatch snippet above becomes unnecessary and `getattr` is not needed since argparse always sets the attribute when `add_argument` is called.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_build_parser` (tail subparser), `main` (tail dispatch block ~line 1935–1938)

### Dependent Files (Callers/Importers)
- N/A — `_cmd_tail` already receives `loops_dir` as a parameter; no signature change needed

### Similar Patterns
- `ll-logs extract` (`_cmd_extract`) already accepts and uses `args.project` — follow the same pattern

### Tests
- `scripts/tests/test_ll_logs.py` — `TestTail` class (lines 483–557); add tests following the patterns in Codebase Research Findings below

_Wiring pass added by `/ll:wire-issue`:_
- `TestArgumentParsing.test_tail_project_flag` — argparse-only; add to `TestArgumentParsing`, not `TestTail`; follows `TestScanFailures.test_scan_failures_project_flag` shape (line 2086) [Agent 3 finding]
- `TestTail.test_tail_project_not_found_returns_1` — integration error-path via `main_logs()`; follows `TestExtract.test_extract_project_not_found_returns_1` shape (line 1353) [Agent 3 finding]
- `TestTail.test_tail_uses_project_loops_dir` — direct `_cmd_tail` with `argparse.Namespace(loop="myloop", project=Path("/alt"))` to verify cross-project loops dir resolution [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — update `ll-logs tail` usage line to show `--project` flag (subcommand coverage at lines 1993–2078)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `main_logs` subcommands list, `tail` bullet (~line 3732): append `; optional --project DIR` [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Tail dispatch block**: `logs.py:1935–1938` — `BRConfig(Path.cwd())` is the exact call to parameterize
- **Tail subparser**: `logs.py:1683–1688` — only `--loop` is currently registered; `--project` goes here
- **`_cmd_tail` signature**: `logs.py:663` — `def _cmd_tail(args: argparse.Namespace, loops_dir: Path) -> int`; already parameterized on `loops_dir`, no signature change needed
- **Preferred `--project` pattern for `tail`**: Use the optional standalone form (like `eval-export` at `logs.py:1871–1876`), **not** the `required=True` mutually-exclusive group used by `extract` — `tail` requires `--loop`, has no `--all` counterpart:
  ```python
  tail_parser.add_argument("--project", type=Path, metavar="DIR", help="Project root to tail loops from (default: CWD)")
  ```
  With `type=Path`, `args.project` is already a `Path` or `None`, so the dispatch simplifies to:
  ```python
  project_root = args.project if args.project else Path.cwd()
  config = BRConfig(project_root)
  loops_dir = Path(config.loops.loops_dir)
  return _cmd_tail(args, loops_dir)
  ```
- **Test patterns** (`TestTail` at `test_ll_logs.py:483–557`):
  - Argparse-only: `patch("sys.argv", ["ll-logs", "tail", "--loop", "name", "--project", "/tmp"])` → `args = _parse_args()` → `assert args.project == Path("/tmp")`
  - Integration via `main_logs()`: patch `sys.argv`, `pathlib.Path.home`, and `little_loops.cli.logs.Path.cwd`; follow `TestExtract.test_extract_project_not_found_returns_1` (line 1353) for error-path coverage
  - Direct `_cmd_tail` tests use `argparse.Namespace(loop="name")` — extend with `project=None` for existing path, `project=Path("/alt")` for cross-project path

## Implementation Steps

1. Add `tail_parser.add_argument("--project", metavar="DIR", help="Project root to tail loops from (default: CWD)")` in `_build_parser`.
2. Update the `tail` dispatch block in `main` to use `args.project` when set.
3. Add or extend a test asserting cross-project resolution.
4. Update CLI reference docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/API.md` — `main_logs` subcommands list, `tail` bullet (~line 3732): append `; optional --project DIR`

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
- `/ll:confidence-check` - 2026-06-25T20:00:00Z - `c21ec4d9-b5a5-41b5-8ddb-c973d34b23b3.jsonl`
- `/ll:wire-issue` - 2026-06-25T19:09:16 - `16886653-9d7a-446b-b2a5-0cf6603480f4.jsonl`
- `/ll:refine-issue` - 2026-06-25T19:02:30 - `853a5f56-2b9f-4b28-ab01-3785b3961b4d.jsonl`
- `/ll:format-issue` - 2026-06-25T18:56:06 - `4bf59de2-23a4-414b-a149-93b27c0b197d.jsonl`
- `/ll:capture-issue` - 2026-06-25T18:52:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0eaae7ef-edbe-497f-bc91-15b8fc518594.jsonl`
