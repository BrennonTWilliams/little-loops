---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 71
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

## Motivation

Without scaffolding, extension authors must manually configure `pyproject.toml` entry points and implement the `LLExtension` Protocol from scratch by reading docs. This creates friction for contributors and risks incorrect setup.

- **Developer experience**: A single command eliminates boilerplate and provides a working starting point
- **Adoption**: Lowers barrier to entry for the extension ecosystem
- **Correctness**: Generated templates ensure proper entry point registration and Protocol implementation out of the box

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
- `scripts/little_loops/cli/__init__.py` — three changes: (1) add `from little_loops.cli.create_extension import main_create_extension` after line 20 (between `auto` at line 20 and `deps` at line 21); (2) add `"main_create_extension"` to `__all__` after `"main_check_links"` at line 40 (line 41 is `"main_deps"` — insert between them); (3) add `- ll-create-extension: ...` to module docstring near line 17
- `scripts/pyproject.toml` — add `ll-create-extension = "little_loops.cli:main_create_extension"` after `ll-check-links` (line 58, before `ll-issues` at line 59); `mcp-call` at line 63 is NOT part of `[project.scripts]` — inserting after it places the entry outside the block
- `scripts/tests/test_create_extension.py` — new test file

### Key References
- `scripts/little_loops/cli/auto.py:21-103` — `main_auto()` as closest model (simple argparse, `BRConfig(project_root)` + `configure_output(config.cli)`)
- `scripts/little_loops/issue_template.py:40-114` — `parts: list[str]` + `"\n".join()` scaffolding pattern; **no Jinja2 anywhere in codebase**
- `scripts/little_loops/parallel/types.py:357-385` — string `.replace()` for `{{name}}` substitution
- `scripts/little_loops/cli_args.py` — use only `add_config_arg` + `add_dry_run_arg` (NOT `add_common_auto_args`)
- `scripts/little_loops/extension.py:101-116` — `NoopLoggerExtension` as skeleton template model (lines 52-67 are `LLExtension.on_event` docstring and `InterceptorExtension`, not the concrete class)
- `scripts/pyproject.toml:64` — `[project.entry-points."little_loops.extensions"]` format comment already present

### Critical Implementation Notes
- Interface: one positional `name` arg plus `--config` and `--dry-run` only — NOT `add_common_auto_args`
- Each CLI command has its own file under `scripts/little_loops/cli/` — do NOT add to `auto.py`
- `cli/__init__.py` `__all__` is alphabetically sorted — insert `"main_create_extension"` after `"main_check_links"` at line 40
- Do NOT add Jinja2; use string `.replace()` for template substitution
- `ll-create-extension` entry goes after `ll-check-links` at line 58 in `pyproject.toml` (before `ll-issues` at line 59, within `[project.scripts]` block)
- `configure_output` is for color config; a pure file-scaffolding command does not need it — omit unless adding colored output
- Generated test file: import `LLTestBus` as `from little_loops import LLTestBus` (public re-export at `scripts/little_loops/__init__.py:31`)

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md:216-230` — CLI TOOLS block lists all `ll-*` tools; add `ll-create-extension` entry after `ll-gitignore` (line 230); **not covered by FEAT-1045**
- `skills/init/SKILL.md:430-443` — Bash permissions block that `/ll:init` writes into `.claude/settings.local.json`; add `"Bash(ll-create-extension:*)"` entry; **not covered by FEAT-1045**
- `skills/init/SKILL.md:511-523` — "file exists" CLAUDE.md append boilerplate; add `ll-create-extension` bullet; **not covered by FEAT-1045**
- `skills/init/SKILL.md:535-547` — "create new" CLAUDE.md write boilerplate; add `ll-create-extension` bullet; **not covered by FEAT-1045**
- `skills/configure/areas.md:793` — "Authorize all N ll- CLI tools" description; increment count `13` → `14` and append `ll-create-extension` to enumerated list; **not covered by FEAT-1045**

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

**Ordering constraint** — these test files import from `little_loops.cli` (the `__init__.py` being modified); if the import line is added to `__init__.py` before `create_extension.py` exists, all of them will fail at pytest collection with `ImportError`:
- `scripts/tests/test_ll_loop_state.py` — `from little_loops.cli import main_loop`
- `scripts/tests/test_ll_loop_commands.py` — `from little_loops.cli import main_loop`
- `scripts/tests/test_issues_cli.py` — `from little_loops.cli import main_issues`
- `scripts/tests/test_cli_e2e.py` — `from little_loops.cli import main_auto, main_parallel, main_loop`

`create_extension.py` and the `cli/__init__.py` import addition **must land in the same atomic commit**.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension.py` — new test file; import from `little_loops.cli.create_extension` directly (NOT `little_loops.cli`) to avoid triggering the full `__init__.py` import chain
- Follow pattern from `scripts/tests/test_gitignore_cmd.py`: one class per mode (`TestMainCreateExtensionDryRun`, `TestMainCreateExtensionApply`); patch `sys.argv` and collaborators at `"little_loops.cli.create_extension.<fn>"`; assert integer return codes
- No existing tests need updating — no test asserts the contents or length of `cli/__init__.py`'s `__all__`

## Implementation Steps

1. Create `scripts/little_loops/cli/create_extension.py`:
   - `main_create_extension()` entry point
   - Argparse: positional `name`, `add_config_arg`, `add_dry_run_arg`
   - Calls template rendering functions; creates output directory

2. Create `templates/extension/` scaffolding files:
   - Use `parts: list[str]` + `"\n".join()` pattern
   - String `.replace("{{name}}", name)` for substitution
   - Skeleton `extension.py` includes comment linking to `docs/reference/EVENT-SCHEMA.md`

3. Update `scripts/little_loops/cli/__init__.py` **in the same commit as step 1** (ordering constraint — see Dependent Files above):
   - Add import after line 20 (between `auto` and `deps`)
   - Add to `__all__` after line 40 (alphabetical)

4. Register in `scripts/pyproject.toml` after `ll-check-links` (line 58, before `ll-issues`)

5. Create `scripts/tests/test_create_extension.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `commands/help.md:230` — add `ll-create-extension` bullet to CLI TOOLS block after `ll-gitignore`
7. Update `skills/init/SKILL.md:442` — add `"Bash(ll-create-extension:*)"` to permissions block
8. Update `skills/init/SKILL.md:523,547` — add `ll-create-extension` bullet to both CLAUDE.md boilerplate blocks ("file exists" and "create new")
9. Update `skills/configure/areas.md:793` — increment count `13` → `14`; append `ll-create-extension` to enumerated list

## Use Case

**Who**: Extension developer creating their first little-loops extension

**Context**: When starting a new extension project and wanting a working starting point without manually reading docs to understand the required `pyproject.toml` entry points and Protocol implementation

**Goal**: Scaffold a complete, working extension skeleton with a single CLI command

**Outcome**: A runnable extension directory (e.g. `my-dashboard-ext/`) with correct `pyproject.toml`, skeleton `extension.py`, and an example test using `LLTestBus`, ready to customize and install

## Acceptance Criteria

- [ ] `ll-create-extension <name>` creates a working directory scaffold
- [ ] Generated `pyproject.toml` has correct `[project.entry-points."little_loops.extensions"]`
- [ ] Skeleton `extension.py` includes comment linking to `docs/reference/EVENT-SCHEMA.md`
- [ ] Generated test file uses `LLTestBus` example
- [ ] `--dry-run` flag shows what would be created without writing files

## API/Interface

```bash
ll-create-extension <name> [--config CONFIG] [--dry-run]
```

- `name` (positional): Extension name in kebab-case (e.g., `my-dashboard-ext`); used to derive package name (`my_dashboard_ext`)
- `--config CONFIG`: Path to `ll-config.json` (optional, uses project default)
- `--dry-run`: Show what would be created without writing any files

Entry point registered in `scripts/pyproject.toml`:
```toml
ll-create-extension = "little_loops.cli:main_create_extension"
```

## Impact

- **Priority**: P4 - Developer experience; valuable once extension ecosystem has traction
- **Effort**: Small-Medium - Scaffolding is straightforward
- **Risk**: Low - Purely additive new tooling; no changes to existing code paths
- **Breaking Change**: No
- **Depends On**: FEAT-911 (completed), FEAT-1043 (LLTestBus, for generated test template)

## Labels

`feat`, `extension-api`, `developer-experience`

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Test file patterns to model after:**
- `scripts/tests/test_gitignore_cmd.py` — dry-run mode + `main_*` direct call + `patch("sys.argv", [...])` pattern; classes organized by subcommand/mode; asserts integer return code
- `scripts/tests/test_cli_sync.py` — BRConfig patching pattern: `patch("little_loops.cli.sync.BRConfig", return_value=mock_config)`; patch at import site, not source

**`LLTestBus` public API for the generated test template:**
- Import: `from little_loops import LLTestBus` (`scripts/little_loops/__init__.py:31`)
- Usage: `bus = LLTestBus(events)` or `LLTestBus.from_jsonl(path)` → `bus.register(ext)` → `bus.replay()` → assert on `bus.delivered_events` or `ext.received`
- See full API in `scripts/little_loops/testing.py:30-103` and test examples in `scripts/tests/test_testing.py`

**`NoopLoggerExtension` confirmed at `scripts/little_loops/extension.py:101-116`** (not 52-67):
- Lines 52-67 are `LLExtension.on_event()` docstring and start of `InterceptorExtension` Protocol
- The concrete skeleton class (`__init__` + `on_event`) is at lines 101-116

**`pyproject.toml` `[project.scripts]` block confirmed at lines 48-63:**
- Current alphabetical neighbors: `ll-check-links` (line 58) → `ll-issues` (line 59)
- `ll-create-extension` inserts between them (lines shift down by 1)

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- `scripts/little_loops/cli/create_extension.py` does not exist ✓
- `templates/extension/` directory does not exist ✓
- No `ll-create-extension` entry point in `scripts/pyproject.toml` ✓
- Feature not yet implemented

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-11
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into

- FEAT-1048: ll-create-extension Core CLI Implementation
- FEAT-1049: ll-create-extension Documentation Wiring

## Status

**Decomposed** | Created: 2026-04-11 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91ac1f52-5b78-4d84-b76b-59e0062299af.jsonl`
- `/ll:wire-issue` - 2026-04-12T02:56:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/592210f4-d925-4e60-8249-8d65a18f81d3.jsonl`
- `/ll:refine-issue` - 2026-04-12T02:52:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07ed7e02-9480-4491-8f6b-3057438b46f3.jsonl`
- `/ll:format-issue` - 2026-04-12T02:48:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/849523b4-4401-4dce-b25b-30233e8c0205.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/641c5bf7-b7c1-42cd-b701-507df2a51df9.jsonl`
