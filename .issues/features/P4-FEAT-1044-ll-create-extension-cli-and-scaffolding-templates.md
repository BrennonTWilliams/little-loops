---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 85
---

# FEAT-1044: ll-create-extension CLI and Scaffolding Templates

## Summary

Create the `ll-create-extension <name>` CLI command that scaffolds a new extension repo with the correct `pyproject.toml` entry points, a skeleton `on_event` handler implementing `LLExtension`, and an example test using `LLTestBus`. Register it as a script entry point in `scripts/pyproject.toml`.

## Parent Issue

Decomposed from FEAT-916: Extension SDK with Scaffolding Command and Test Harness

## Context

Without scaffolding, extension authors must manually configure `pyproject.toml` entry points and implement the Protocol from scratch by reading docs. A scaffolding command eliminates boilerplate and provides a working starting point.

## Current Behavior

No `ll-create-extension` command or `templates/extension/` directory exists. No `main_create_extension` in `scripts/little_loops/cli/__init__.py`.

## Expected Behavior

```bash
ll-create-extension my-dashboard-ext
# Creates: my-dashboard-ext/
#   pyproject.toml (with entry point)
#   my_dashboard_ext/__init__.py
#   my_dashboard_ext/extension.py (skeleton)
#   tests/test_extension.py (with LLTestBus example)
```

## Proposed Solution

1. Create `scripts/little_loops/cli/create_extension.py` with `main_create_extension()`
2. Build `templates/extension/` scaffolding using `parts: list[str]` + `"\n".join()` pattern with string `.replace()` for `{{name}}` substitution
3. Register in `scripts/pyproject.toml` and re-export from `cli/__init__.py`

## Integration Map

### Files to Create / Modify
- `scripts/little_loops/cli/create_extension.py` — new file, `main_create_extension()`
- `templates/extension/` — new directory with:
  - `pyproject.toml.tmpl` — with `[project.entry-points."little_loops.extensions"]` registration
  - `extension.py.tmpl` — skeleton `on_event` handler; must include comment: `# See docs/reference/EVENT-SCHEMA.md for all available event types and payload fields`
  - `test_extension.py.tmpl` — example test using `LLTestBus`
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.create_extension import main_create_extension` **after line 20** (between `auto` and `deps`); add `"main_create_extension"` to `__all__` **after `"main_check_links"` at line 40** (alphabetical: `check_links` < `create_extension` < `deps`)
- `scripts/pyproject.toml` — add `ll-create-extension = "little_loops.cli:main_create_extension"` after line 63 (after `mcp-call`)
- `scripts/tests/test_create_extension.py` — new test file

### Key References
- `scripts/little_loops/cli/auto.py:21-103` — `main_auto()` as closest model (simple argparse, `BRConfig(project_root)` + `configure_output(config.cli)`)
- `scripts/little_loops/issue_template.py:40-114` — `parts: list[str]` + `"\n".join()` scaffolding pattern; **no Jinja2 anywhere in codebase**
- `scripts/little_loops/parallel/types.py:357-385` — string `.replace()` for `{{name}}` substitution
- `scripts/little_loops/cli_args.py` — use only `add_config_arg` + `add_dry_run_arg` (NOT `add_common_auto_args`)
- `scripts/little_loops/extension.py:52-67` — `NoopLoggerExtension` as skeleton template model
- `scripts/pyproject.toml:64` — `[project.entry-points."little_loops.extensions"]` format comment already present

### Critical Implementation Notes
- Interface: one positional `name` arg plus `--config` and `--dry-run` only — NOT `add_common_auto_args`
- Each CLI command has its own file under `scripts/little_loops/cli/` — do NOT add to `auto.py`
- `cli/__init__.py` `__all__` is alphabetically sorted — insert `"main_create_extension"` after `"main_check_links"` at line 40
- Do NOT add Jinja2; use string `.replace()` for template substitution
- `ll-create-extension` entry goes after `mcp-call` at line 63 in `pyproject.toml`

## Implementation Steps

1. Create `scripts/little_loops/cli/create_extension.py`:
   - `main_create_extension()` entry point
   - Argparse: positional `name`, `add_config_arg`, `add_dry_run_arg`
   - Calls template rendering functions; creates output directory

2. Create `templates/extension/` scaffolding files:
   - Use `parts: list[str]` + `"\n".join()` pattern
   - String `.replace("{{name}}", name)` for substitution
   - Skeleton `extension.py` includes comment linking to `docs/reference/EVENT-SCHEMA.md`

3. Update `scripts/little_loops/cli/__init__.py`:
   - Add import after line 20 (between `auto` and `deps`)
   - Add to `__all__` after line 40 (alphabetical)

4. Register in `scripts/pyproject.toml` after line 63

5. Create `scripts/tests/test_create_extension.py`

## Acceptance Criteria

- [ ] `ll-create-extension <name>` creates a working directory scaffold
- [ ] Generated `pyproject.toml` has correct `[project.entry-points."little_loops.extensions"]`
- [ ] Skeleton `extension.py` includes comment linking to `docs/reference/EVENT-SCHEMA.md`
- [ ] Generated test file uses `LLTestBus` example
- [ ] `--dry-run` flag shows what would be created without writing files

## Impact

- **Priority**: P4 - Developer experience; valuable once extension ecosystem has traction
- **Effort**: Small-Medium - Scaffolding is straightforward
- **Risk**: Low - Purely additive new tooling; no changes to existing code paths
- **Breaking Change**: No
- **Depends On**: FEAT-911 (completed), FEAT-1043 (LLTestBus, for generated test template)

## Labels

`feat`, `extension-api`, `developer-experience`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
