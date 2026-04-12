---
discovered_commit: 45e5fdedd4e2a77e858c47840c98ded017b79b47
discovered_branch: main
discovered_date: 2026-04-12T19:32:44Z
discovered_by: capture-issue
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

**`cli/schemas.py`** — 2 changes: add `configure_output()` + `Logger`; replace `print(f"Generated ...")` → `logger.success`; `print(f"Error: {exc}")` → `logger.error`

**`cli/create_extension.py`** — ~9 changes: add `configure_output()` + `Logger`; error prints → `logger.error`; dry-run/file-list → `logger.info`; `Created:` → `logger.success`; next-steps → `logger.info`

**`cli/docs.py`** — ~6 changes across `main_verify_docs()` and `main_check_links()`: add `configure_output()` + `Logger` in each; replace status/result prints

**`workflow_sequence/__init__.py`** — ~14 changes: add `configure_output()` + `Logger`; stderr error prints → `logger.error`; progress lines → `logger.info`; `Output written to:` → `logger.success`; keep raw data output

**`cli/history.py`** — ~8 changes: add near `BRConfig` init; `Documentation written to` → `logger.success`; keep all formatted data output (`print(doc)`, JSON/YAML/markdown reports)

**`cli/deps.py`** — ~12-15 changes from ~47 total: add `configure_output()` + `Logger`; error messages → `logger.error`; "No issues found" variants → `logger.info`/`logger.warning`; "No validation issues found" → `logger.success`; keep all report/graph/JSON output

## Reference Implementations

- `scripts/little_loops/cli/sync.py` — Logger throughout
- `scripts/little_loops/cli/gitignore.py` — Logger throughout
- `scripts/little_loops/cli/parallel.py` — `configure_output()` + `Logger(use_color=use_color_enabled())`

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
- `/ll:capture-issue` - 2026-04-12T19:32:44Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da757c9-7ce6-4e48-97f4-06e4c7a2b36b.jsonl`
