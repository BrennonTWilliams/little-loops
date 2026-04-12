---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 71
---

# FEAT-1048: ll-create-extension Core CLI Implementation

## Summary

Create the `ll-create-extension <name>` CLI command: the entry point module, scaffolding templates, pyproject.toml entry point registration, and tests.

## Parent Issue

Decomposed from FEAT-1044: ll-create-extension CLI and Scaffolding Templates

## Context

Without scaffolding, extension authors must manually configure `pyproject.toml` entry points and implement the Protocol from scratch by reading docs. A scaffolding command eliminates boilerplate and provides a working starting point.

## Motivation

This feature would:
- Eliminate boilerplate: extension authors currently must manually configure `pyproject.toml` entry points and implement the Protocol from scratch by reading docs
- Lower barrier to entry: a single command provides a working starting point instead of copy-pasting from examples
- Ensure correctness: generated `pyproject.toml` uses the correct `[project.entry-points."little_loops.extensions"]` format, reducing configuration errors

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

## Use Case

**Who**: Extension developer (plugin author) building a new little-loops extension

**Context**: Starting a new extension project and needing a scaffold with proper `pyproject.toml` entry points, a compliant `on_event` handler skeleton, and an example `LLTestBus`-based test

**Goal**: Run `ll-create-extension my-dashboard-ext` and immediately have a working, installable extension project to develop from

**Outcome**: A scaffolded directory with `pyproject.toml` (entry point registered), `my_dashboard_ext/extension.py` (skeleton handler with doc link), and `tests/test_extension.py` (LLTestBus example) — ready for `pip install -e .` and test runs

## Proposed Solution

1. Create `scripts/little_loops/cli/create_extension.py` with `main_create_extension()`
2. Build `templates/extension/` scaffolding using `parts: list[str]` + `"\n".join()` pattern with string `.replace()` for `{{name}}` substitution
3. Register in `scripts/pyproject.toml` and re-export from `cli/__init__.py`
4. Write tests in `scripts/tests/test_create_extension.py`

## Integration Map

### Files to Create / Modify

- `scripts/little_loops/cli/create_extension.py` — new file, `main_create_extension()`
- `templates/extension/` — new directory with:
  - `pyproject.toml.tmpl` — with `[project.entry-points."little_loops.extensions"]` registration
  - `extension.py.tmpl` — skeleton `on_event` handler; must include comment: `# See docs/reference/EVENT-SCHEMA.md for all available event types and payload fields`
  - `test_extension.py.tmpl` — example test using `LLTestBus`
- `scripts/little_loops/cli/__init__.py` — three changes: (1) add `from little_loops.cli.create_extension import main_create_extension` after line 20 (between `auto` at line 20 and `deps` at line 21); (2) add `"main_create_extension"` to `__all__` after `"main_check_links"` at line 40; (3) add `- ll-create-extension: ...` to module docstring near line 17
- `scripts/pyproject.toml` — add `ll-create-extension = "little_loops.cli:main_create_extension"` after `ll-check-links` (line 58, before `ll-issues` at line 59)
- `scripts/tests/test_create_extension.py` — new test file

### Key References

- `scripts/little_loops/cli/auto.py:21-103` — `main_auto()` as closest model (simple argparse, `BRConfig(project_root)` + `configure_output(config.cli)`)
- `scripts/little_loops/issue_template.py:40-114` — `parts: list[str]` + `"\n".join()` scaffolding pattern; **no Jinja2 anywhere in codebase**
- `scripts/little_loops/parallel/types.py:357-385` — string `.replace()` for `{{name}}` substitution
- `scripts/little_loops/cli_args.py` — use only `add_dry_run_arg` (NOT `add_config_arg`, NOT `add_common_auto_args`)
- `scripts/little_loops/extension.py:101-116` — `NoopLoggerExtension` as skeleton template model

### Critical Implementation Notes

- Interface: one positional `name` arg plus `--dry-run` only — drop `--config` (command operates on `cwd`, has no project root concept) — NOT `add_common_auto_args`
- Each CLI command has its own file under `scripts/little_loops/cli/` — do NOT add to `auto.py`
- `cli/__init__.py` `__all__` is alphabetically sorted — insert `"main_create_extension"` after `"main_check_links"` at line 40
- Do NOT add Jinja2; use string `.replace()` for template substitution
- `ll-create-extension` entry goes after `ll-check-links` at line 58 in `pyproject.toml` (before `ll-issues` at line 59, within `[project.scripts]` block)
- `configure_output` is for color config; a pure file-scaffolding command does not need it — omit unless adding colored output
- Generated test file: import `LLTestBus` as `from little_loops import LLTestBus` (public re-export at `scripts/little_loops/__init__.py:31`)
- Generated `extension.py`: import `LLEvent` as `from little_loops import LLEvent` (same public re-export pattern)
- **Class name derivation**: kebab-case → PascalCase, no `Extension` suffix appended (e.g., `my-dashboard-ext` → `MyDashboardExt`). Authors may rename.
- **`event_filter`**: omit from skeleton — the Protocol field defaults to `None` (receive all events), which is the right starting point
- **Existing directory**: if `<name>/` already exists in `cwd`, abort with `exit 1` and print: `Error: directory '<name>' already exists. Remove it or choose a different name.`
- **`pyproject.toml.tmpl` structure**: use `hatchling` build backend; `requires-python = ">=3.11"`; `dependencies = ["little-loops"]` unpinned (author tightens); entry point uses `{{pkg_name}}.extension:{{class_name}}`

### Ordering Constraint

`create_extension.py` and the `cli/__init__.py` import addition **must land in the same atomic commit**. Adding the import to `__init__.py` before `create_extension.py` exists causes `ImportError` at pytest collection for:

- `scripts/tests/test_ll_loop_state.py`
- `scripts/tests/test_ll_loop_commands.py`
- `scripts/tests/test_issues_cli.py`
- `scripts/tests/test_cli_e2e.py`

_Wiring pass added by `/ll:wire-issue`:_

The following additional test files also import from `little_loops.cli` and will fail at collection if the ordering constraint is violated — no content changes needed, but verify they all pass after the atomic commit:

- `scripts/tests/test_cli.py`
- `scripts/tests/test_issue_history_cli.py`
- `scripts/tests/test_next_issues.py`
- `scripts/tests/test_create_loop.py`
- `scripts/tests/test_ll_loop_integration.py`

### Tests

- `scripts/tests/test_create_extension.py` — new test file; import from `little_loops.cli.create_extension` directly (NOT `little_loops.cli`) to avoid triggering the full `__init__.py` import chain
- Follow pattern from `scripts/tests/test_gitignore_cmd.py`: one class per mode (`TestMainCreateExtensionDryRun`, `TestMainCreateExtensionApply`); patch `sys.argv` and collaborators at `"little_loops.cli.create_extension.<fn>"`; assert integer return codes
- No existing tests need updating

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

Documentation wiring for `ll-create-extension` is split across two sibling issues — this issue does not need to implement these:

- **FEAT-1049** (`ll-create-extension` documentation wiring) covers:
  - `commands/help.md` — add `ll-create-extension` to the `CLI TOOLS` block (after `ll-gitignore` at line 230)
  - `skills/init/SKILL.md` — add `"Bash(ll-create-extension:*)"` to permissions block (line 442), and add `ll-create-extension` bullet to both CLAUDE.md boilerplate blocks (lines 523 and 547)
  - `skills/configure/areas.md` — increment tool count (`13` → `14`) and append `ll-create-extension` to the list (line 793)

- **FEAT-1045** (extension SDK documentation updates) covers:
  - `.claude/CLAUDE.md` — add `ll-create-extension` to `## CLI Tools` listing (after `ll-gitignore` at line 116)
  - `README.md` — update `13 CLI tools` count to 14 (line 90); add `### ll-create-extension` section
  - `docs/reference/CLI.md` — add `### ll-create-extension` section (between `### ll-gitignore` and `### ll-generate-schemas`)
  - `docs/reference/API.md` — add `main_create_extension` entry to `## little_loops.cli` section
  - `docs/ARCHITECTURE.md` — add `create_extension.py` to cli/ tree and `templates/extension/` to templates/ tree
  - `docs/reference/CONFIGURATION.md` — add cross-reference to `ll-create-extension` in extension authoring block (lines 631–659)
  - `CONTRIBUTING.md` — add extension development workflow section

This issue only requires updating the `cli/__init__.py` module docstring (step 3, already captured).

### Codebase Research Findings

- `scripts/tests/test_gitignore_cmd.py` — dry-run mode + `main_*` direct call + `patch("sys.argv", [...])` pattern; classes organized by subcommand/mode; asserts integer return code
- `scripts/tests/test_cli_sync.py` — BRConfig patching pattern: `patch("little_loops.cli.sync.BRConfig", return_value=mock_config)`; patch at import site, not source
- `LLTestBus` API: `bus = LLTestBus(events)` or `LLTestBus.from_jsonl(path)` → `bus.register(ext)` → `bus.replay()` → assert on `bus.delivered_events` or `ext.received`
- See full API in `scripts/little_loops/testing.py:30-103` and `scripts/tests/test_testing.py`
- `NoopLoggerExtension` confirmed at `scripts/little_loops/extension.py:101-116`
- `[project.scripts]` block in `pyproject.toml:48-63`; `ll-check-links` (line 58) → `ll-issues` (line 59)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Direct CLI model**: `scripts/little_loops/cli/gitignore.py` is the closest analogue (no BRConfig, no configure_output — a pure file-operation command). The `auto.py` reference in Key References is for orientation only; `gitignore.py` is the file to model `create_extension.py` after. Note: `gitignore.py` uses both `add_config_arg` + `add_dry_run_arg`, but `create_extension.py` should use `add_dry_run_arg` only — the Critical Implementation Notes explicitly drop `--config` because this command operates on `cwd` with no project root concept.
- **`.tmpl` extension is new**: No `.tmpl` files exist anywhere in `templates/` currently (all are `.json` or `.md`). The `templates/extension/` directory and `.tmpl` extension establish a new convention — this is fine, but implementers should know it has no prior art to reference within the project.
- **`ENTRY_POINT_GROUP` constant**: `scripts/little_loops/extension.py:32` defines `ENTRY_POINT_GROUP = "little_loops.extensions"` — the `pyproject.toml.tmpl` must use `[project.entry-points."little_loops.extensions"]` exactly (confirmed to match).
- **`LLExtension` Protocol**: Defined at `scripts/little_loops/extension.py:35-56`. The `on_event(self, event: LLEvent) -> None` method is the only required Protocol method. Three optional mixin Protocols exist (`InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`) detected via `hasattr()` at runtime — mention in the extension.py.tmpl skeleton comment that these are opt-in.
- **`NoopLoggerExtension` signature** (model for skeleton): `__init__(self, log_path: Path | None = None)` + `on_event(self, event: LLEvent) -> None` — keep skeleton simpler (omit `log_path`; just log or no-op in `on_event`).
- **Test multi-patch syntax**: Use Python 3.10+ parenthesized `with (patch(...), patch(...)):` — confirmed in `test_gitignore_cmd.py:44-50`. Patch collaborators at the import site (`"little_loops.cli.create_extension.<fn>"`), not at definition site. No BRConfig patching needed (command doesn't load config).
- **All line-number claims verified accurate** as of 2026-04-11: `auto` at line 20, `deps` at line 21, `"main_check_links"` in `__all__` at line 40, `ll-check-links` at pyproject.toml line 58, `ll-issues` at line 59.

## Implementation Steps

1. Create `scripts/little_loops/cli/create_extension.py`:
   - `main_create_extension()` entry point
   - Argparse: positional `name`, `add_dry_run_arg` only (no `add_config_arg` — command operates on `cwd`, has no project root concept)
   - Calls template rendering functions; creates output directory

2. Create `templates/extension/` scaffolding files:
   - Use `parts: list[str]` + `"\n".join()` pattern
   - String `.replace("{{name}}", name)` for substitution
   - Skeleton `extension.py` includes comment linking to `docs/reference/EVENT-SCHEMA.md`

3. Update `scripts/little_loops/cli/__init__.py` **in the same commit as step 1**:
   - Add import after line 20 (between `auto` and `deps`)
   - Add to `__all__` after line 40 (alphabetical)

4. Register in `scripts/pyproject.toml` after `ll-check-links` (line 58, before `ll-issues`)

5. Create `scripts/tests/test_create_extension.py`

## API/Interface

```bash
ll-create-extension <name> [--dry-run]
```

- `name` (positional): Extension name in kebab-case (e.g., `my-dashboard-ext`); used to derive package name (`my_dashboard_ext`) and class name (`MyDashboardExt`)
- `--dry-run`: Show what would be created without writing any files

Entry point registered in `scripts/pyproject.toml`:
```toml
ll-create-extension = "little_loops.cli:main_create_extension"
```

## Acceptance Criteria

- [x] `ll-create-extension <name>` creates a working directory scaffold
- [x] Generated `pyproject.toml` has correct `[project.entry-points."little_loops.extensions"]`
- [x] Skeleton `extension.py` includes comment linking to `docs/reference/EVENT-SCHEMA.md`
- [x] Generated test file uses `LLTestBus` example
- [x] `--dry-run` flag shows what would be created without writing files
- [x] All new tests pass with `python -m pytest scripts/tests/test_create_extension.py`

## Impact

- **Priority**: P4 - Developer experience; valuable once extension ecosystem has traction
- **Effort**: Small-Medium - Scaffolding is straightforward
- **Risk**: Low - Purely additive new tooling; no changes to existing code paths
- **Breaking Change**: No
- **Depends On**: FEAT-911 (completed), FEAT-1043 (LLTestBus, for generated test template)
- **Sibling**: FEAT-1049 (documentation wiring — can follow this issue)

## Labels

`feat`, `extension-api`, `developer-experience`

---

## Status

**Completed** | Created: 2026-04-11 | Resolved: 2026-04-11 | Priority: P4

## Resolution

Implemented `ll-create-extension <name> [--dry-run]` CLI command:
- `scripts/little_loops/cli/create_extension.py` — new module with `main_create_extension()`, template render functions, and `_write_scaffold()` / `_target_exists()` helpers
- `templates/extension/` — three `.tmpl` reference files (`pyproject.toml.tmpl`, `extension.py.tmpl`, `test_extension.py.tmpl`)
- `scripts/little_loops/cli/__init__.py` — added import, `__all__` entry, and docstring line (atomic with module creation)
- `scripts/pyproject.toml` — registered `ll-create-extension` entry point
- `scripts/tests/test_create_extension.py` — 10 tests, all passing

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-12T04:20:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ed6a07b-21b2-4dd2-b642-a8f8ee28dcfa.jsonl`
- `/ll:ready-issue` - 2026-04-12T04:12:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/944df040-d306-46c9-91a4-e21802bb110a.jsonl`
- `/ll:confidence-check` - 2026-04-11T04:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32c003c1-efad-4d24-b9eb-63cacaec1777.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/552f9ae8-b018-49c2-96eb-16e112223147.jsonl`
- `/ll:confidence-check` - 2026-04-12T04:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/717e28ae-eb80-4486-985b-4a93bb32c71f.jsonl`
- `/ll:wire-issue` - 2026-04-12T03:10:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51a1aad7-49ce-434e-8ce5-a76e8376deb3.jsonl`
- `/ll:refine-issue` - 2026-04-12T03:05:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f875fa22-3b06-4f03-882b-0bca893be6d5.jsonl`
- `/ll:format-issue` - 2026-04-12T03:02:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/136340fb-a87f-495a-a00c-d5c8ef84d1cb.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/641c5bf7-b7c1-42cd-b701-507df2a51df9.jsonl`
