---
discovered_commit: 45e5fdedd4e2a77e858c47840c98ded017b79b47
discovered_branch: main
discovered_date: 2026-04-12T19:32:44Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# ENH-1064: Wire Logger and configure_output to non-compliant CLI commands

## Summary

7 of 15 `ll-` CLI commands emit all output via raw `print()`, bypassing the project's two-part output styling system (`Logger` + `cli/output.py`). These tools do not respect `NO_COLOR`, do not produce colored/prefixed status output, and are inconsistent with the 8 compliant tools.

## Motivation

The project has a well-established output contract:
- `configure_output()` — wires color config and respects `NO_COLOR`
- `Logger` — colored, timestamped `.info()` / `.success()` / `.warning()` / `.error()` / `.timing()` / `.header()` methods

8 tools already follow this contract. The 7 non-compliant tools produce plain uncolored output, making the CLI experience inconsistent and breaking `NO_COLOR` support for those commands.

## Non-Compliant Tools (7)

| Tool | File | `print()` calls |
|------|------|-----------------|
| `ll-deps` | `scripts/little_loops/cli/deps.py` | ~47 |
| `ll-workflows` | `scripts/little_loops/workflow_sequence/__init__.py` | ~14 |
| `ll-create-extension` | `scripts/little_loops/cli/create_extension.py` | ~9 |
| `ll-history` | `scripts/little_loops/cli/history.py` | ~8 |
| `ll-verify-docs` | `scripts/little_loops/cli/docs.py` | ~3 |
| `ll-check-links` | `scripts/little_loops/cli/docs.py` | ~3 |
| `ll-generate-schemas` | `scripts/little_loops/cli/schemas.py` | ~2 |

## Implementation Steps

### Standard pattern (tools without BRConfig)

```python
from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger

# In main_*():
configure_output()  # None arg = auto-detect, respects NO_COLOR
logger = Logger(use_color=use_color_enabled())
```

### Standard pattern (tools with BRConfig — `ll-history`)

```python
configure_output(config.cli)
logger = Logger(use_color=use_color_enabled())
```

### Two categories of `print()` calls

**Replace with Logger** (status, errors, progress):
- `print(f"Error: ...")` → `logger.error(...)`
- `print("No issues found.")` → `logger.info(...)` or `logger.warning(...)`
- `print(f"Created: {name}/")` → `logger.success(...)`
- `print(f"Generated N schemas in ...")` → `logger.success(...)`
- Verbose/progress lines → `logger.info(...)`

**Keep as `print()`** (raw data — must be pipeable/clean):
- JSON dumps: `print(json.dumps(...))`
- Pre-formatted report text (markdown/YAML/text): `print(format_report(...))`
- Tabular/graph output: `print(format_text_graph(...))`

### Per-file changes

**`cli/schemas.py`** — 3 changes in `main_generate_schemas()` (line 9): add `configure_output()` + `Logger`; line 49 `"Generated N schema(s)"` → `logger.success`; line 52 `"Error: {exc}"` → `logger.error` (currently goes to stdout, not stderr — Logger.error writes to stderr correctly)

**`cli/create_extension.py`** — ~9 changes: add `configure_output()` + `Logger`; error prints → `logger.error`; dry-run/file-list → `logger.info`; `Created:` → `logger.success`; next-steps → `logger.info`

**`cli/docs.py`** — ~3 targeted changes: add `configure_output()` + `Logger` in both `main_verify_docs()` (line 9) and `main_check_links()` (line 101); line 94 `"Fixed N count(s)"` → `logger.success`; keep primary data output (lines 88, 211 — formatted text/json/markdown)

**`workflow_sequence/__init__.py`** — ~7 targeted changes in `main()` at line 60: 5 stderr error prints (155–178, 216) → `logger.error`; verbose progress block (191–210) → `logger.info` gated by `logger.verbose`; line 211 `"Output written to:"` → `logger.success`; keep raw data output. Note: `analysis.py:661-679` has 8 stderr prints inside library function `analyze_workflows()` — those are already gated by a `verbose` flag, leave unchanged

**`cli/history.py`** — ~2 targeted changes: `BRConfig` already instantiated at line 193 — insert `configure_output(config.cli)` after it; line 271 `"Documentation written to"` → `logger.success`; keep all formatted data output (`print(doc)`, JSON/YAML/markdown reports at lines 203, 205, 235–241, 273)

**`cli/deps.py`** — ~12-15 changes from ~47 total: add `configure_output()` + `Logger` at `main_deps()` line 54; error lines (stderr at 213, 233, 242, 395, 405–408, 421–424) → `logger.error`; "No issues found"/sprint-empty/no-validation lines (247, 236, 316) → `logger.info`/`logger.warning`; keep all report/graph/JSON output (lines 301–308, 354, 361–382, 427–483). Note: `BRConfig` is lazy-loaded deep inside helpers — must construct `config = BRConfig(Path.cwd())` at top of `main_deps()` or use `configure_output()` with no args

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Test isolation** — `configure_output()` mutates module-level `_USE_COLOR` in `cli/output.py`. Tests that run in the same process after a newly-wired entry point may see altered state. Confirm `test_cli_output.py:164-182` `setup_method` resets cover this; if ordering issues appear, add a `setup_method` reset in affected test classes.
- **Docs update (optional)** — `docs/reference/OUTPUT_STYLING.md` — note that all ll-* commands are now fully compliant after this change.

## Reference Implementations

- `scripts/little_loops/cli/sync.py` — Logger throughout
- `scripts/little_loops/cli/gitignore.py` — Logger throughout
- `scripts/little_loops/cli/parallel.py` — `configure_output()` + `Logger(use_color=use_color_enabled())`

## Integration Map

### Files to Modify

| File | Entry Point | Line | BRConfig Available |
|------|-------------|------|--------------------|
| `scripts/little_loops/cli/schemas.py` | `main_generate_schemas()` | 9 | No — must construct |
| `scripts/little_loops/cli/create_extension.py` | `main_create_extension()` | 116 | No — must construct |
| `scripts/little_loops/cli/docs.py` | `main_verify_docs()` / `main_check_links()` | 9 / 101 | No — must construct |
| `scripts/little_loops/workflow_sequence/__init__.py` | `main()` | 60 | No — must construct |
| `scripts/little_loops/cli/history.py` | `main_history()` | 12 | **Yes — line 193 already** |
| `scripts/little_loops/cli/deps.py` | `main_deps()` | 54 | Lazy-loaded inside helpers only |

### Callers / Re-exports

- `scripts/little_loops/cli/__init__.py:22-31` — re-exports all `main_*` entry points; imports all non-compliant modules

### CLI Entry Points (`scripts/pyproject.toml:55-63`)

- `ll-workflows` → `little_loops.workflow_sequence:main`
- `ll-history` → `little_loops.cli:main_history`
- `ll-verify-docs` → `little_loops.cli:main_verify_docs`
- `ll-check-links` → `little_loops.cli:main_check_links`
- `ll-create-extension` → `little_loops.cli:main_create_extension`
- `ll-deps` → `little_loops.cli:main_deps`
- `ll-generate-schemas` → `little_loops.cli:main_generate_schemas`

### Reference Pattern — Exact Lines

**Full BRConfig pattern** (`parallel.py:151-155`):
```python
config = BRConfig(project_root)
configure_output(config.cli)
logger = Logger(verbose=args.verbose or not args.quiet, use_color=use_color_enabled())
```
Imports: `parallel.py:10` — `from little_loops.cli.output import configure_output, use_color_enabled` / `parallel.py:28` — `from little_loops.logger import Logger`

**Logger-only pattern** (no configure_output — used by `sync.py:115-116`, `gitignore.py:43-44`):
```python
logger = Logger(verbose=not args.quiet)
```
Note: `Logger(use_color=None)` independently auto-detects `NO_COLOR` + TTY at instantiation time, so this already respects `NO_COLOR` without `configure_output`.

**`history.py` special case** — `BRConfig` already at line 193, just insert `configure_output(config.cli)` after it:
```python
config = BRConfig(project_root)
configure_output(config.cli)  # ADD THIS LINE
```

### Tests

- `scripts/tests/test_cli_docs.py` — covers `main_check_links`, `main_verify_docs`
- `scripts/tests/test_create_extension.py` / `test_create_extension_wiring.py` — covers `create_extension.py`
- `scripts/tests/test_generate_schemas.py` — covers `schemas.py`
- `scripts/tests/test_dependency_mapper.py` — covers `deps.py`
- `scripts/tests/test_workflow_sequence_analyzer.py` — covers `workflow_sequence/__init__.py`
- `scripts/tests/test_issue_history_cli.py` — covers `history.py`
- `scripts/tests/test_logger.py` / `test_cli_output.py` — Logger + configure_output unit tests

**Testing patterns for Logger output** (`test_cli_sync.py:222-258`):
- Pass `MagicMock()` as logger; assert on `logger.info.call_args_list` / `logger.error.call_args_list`
- Or use `pytest` `capsys` fixture to capture stdout and assert on plain text

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_synthesis.py:388-482` — also calls `main_history`; lines 393-394, 456-457 assert on data-output `print()` lines kept as-is — survives the migration
- `scripts/tests/test_cli.py:2685-2837` (`TestHistoryCLI`) — calls `main_history` extensively; return-code assertions only — safe

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — does not currently enumerate which tools are compliant; after this change all 7 non-compliant tools become compliant; consider adding a note or table confirming full compliance across all ll-* commands

### `workflow_sequence/analysis.py` Note

`analysis.py:661-679` contains 8 `print(..., file=sys.stderr)` calls gated by `if verbose:`. These are in library code (`analyze_workflows()`), not the CLI entry point — treat separately or leave unchanged (the verbose flag already provides control).

## Impact

- **Severity**: Low (cosmetic inconsistency; no functional breakage)
- **Effort**: Medium (7 files, ~40-50 targeted line changes)
- **Risk**: Low (additive wiring; raw data output unchanged)

## Labels

`enhancement`, `cli`, `logger`, `output-styling`, `no-color`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60aa1d19-112b-4250-a43b-a5986852e393.jsonl`
- `/ll:wire-issue` - 2026-04-13T01:29:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1b3029d-1f24-48d8-a235-4f55d666b8c3.jsonl`
- `/ll:refine-issue` - 2026-04-13T01:17:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b19e73-9a31-4405-88d4-1165503fb996.jsonl`
- `/ll:capture-issue` - 2026-04-12T19:32:44Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da757c9-7ce6-4e48-97f4-06e4c7a2b36b.jsonl`
