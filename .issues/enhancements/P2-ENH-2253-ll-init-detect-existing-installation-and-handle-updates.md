---
id: ENH-2253
title: ll-init should detect existing plugin installation and handle version updates
type: enhancement
status: open
priority: P2
discovered_date: 2026-06-20
captured_at: '2026-06-21T02:09:57Z'
discovered_by: capture-issue
labels:
- init
- cli
- dx
- installation
decision_needed: false
confidence_score: 97
outcome_confidence: 75
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 19
score_change_surface: 21
---

# ENH-2253: ll-init should detect existing plugin installation and handle version updates

## Summary

`ll-init` currently assumes the `ll@little-loops` Claude Code plugin is already installed globally. Instead, the init wizard and automated setup process should: (1) detect existing local and global plugin installations, (2) check version currency and offer to update if out of date, and (3) include installation and setup as an integrated first step rather than a prerequisite.

## Motivation

New users running `ll-init` on a fresh machine (or in CI) hit a silent assumption: the plugin must already be installed. This breaks the "one-command setup" promise. Similarly, teams using little-loops across versions have no automated path to detect drift between the installed plugin and the current package. Baking install detection into the wizard closes the gap and makes `ll-init` genuinely self-contained.

## Scope Boundaries

- **In scope**: Detecting local dev installs (editable `pip install -e` in active venv), detecting global plugin registrations via `resolve_host()` CLI queries, comparing installed vs. current version, dispatching the correct install command per host CLI (claude-code, opencode, codex), recording install outcome in generated `ll-config.json`.
- **Out of scope**: Managing multiple Python versions or virtual environments, configuring the plugin after install (handled by existing wizard rounds), automatically upgrading in interactive mode without user confirmation, PyPI-based installs (local dev and host CLI registration only for now).

## Current Behavior

`ll-init` skips any check for whether `ll@little-loops` (or a local `./scripts/` dev install) is present. If the plugin is missing, subsequent skill invocations silently fail or produce confusing errors. There is no version-check step; version drift is discovered only when a feature is missing.

## Expected Behavior

1. **Detect installation** — On startup, `ll-init` checks for:
   - A local dev install (editable `pip install -e ./scripts[dev]` present in the active venv or `site-packages`).
   - A global plugin install registered with the host CLI (`claude mcp list` or equivalent `resolve_host()` invocation).
   - Both absent → proceed to install step.
   - One found → record source, proceed to version check.

2. **Version check and update** — If an installation is found:
   - Compare installed version against `scripts/little_loops/__version__.py` (or PyPI if applicable).
   - If out of date: prompt user (interactive mode) or auto-update (headless `--yes` mode).
   - If current: skip silently.

3. **Install as wizard step** — If no installation is detected:
   - In interactive mode: present an install prompt as Round 0 of the wizard (before project-detection rounds).
   - In headless `--yes` mode: run the appropriate install command automatically (e.g., `pip install -e ./scripts[dev]` for local dev; `claude mcp add ll@little-loops` for global).
   - Record outcome in the generated `ll-config.json`.

## Implementation Steps

1. **Create `scripts/little_loops/init/install_check.py`** — define `InstallStatus` enum (`UpToDate | OutOfDate | NotInstalled | Unknown`) and two public functions:
   - `detect_installation(project_root: Path) -> tuple[str | None, str | None]` — returns `(install_source, installed_version)`. For local detection: call `importlib.metadata.version("little-loops")` and catch `PackageNotFoundError` (reuse logic from `_check_little_loops_version()` in `validate.py`). For global: `subprocess.run(["claude", "plugin", "list"], ...)` guarded by `shutil.which("claude")`.
   - `check_version(installed: str, current: str) -> InstallStatus` — compares version strings, returns `UpToDate` / `OutOfDate`.
2. **Extend `scripts/little_loops/init/cli.py:_run_yes()`** — after the `existing_config` load block and before `project_type, template = detect_project_type(project_root)`, call `detect_installation()`. In headless `--yes` mode with an out-of-date install, auto-run the appropriate install command (e.g., `pip install -e ./scripts[dev]` for local dev) and record `install_source` into the config dict before `build_config()`.
3. **Extend `scripts/little_loops/init/tui.py:run_tui()`** — after the `existing_config` load block and before `console.rule("[bold]1 / 6  Project Basics[/bold]")`, insert a "Plugin Install" check step. If out of date or not installed, present a `questionary.confirm()` prompt. Update all `N / 6` labels to `N / 7` throughout `run_tui()`.
4. **Add per-host install dispatch** in `install_check.py` (or `cli.py`) — `claude mcp add ll@little-loops` for claude-code, host-specific equivalents via the `_dispatch_host_adapters()` pattern in `init/cli.py:_dispatch_host_adapters()`. Do not add new methods to `host_runner.py`; `build_version_check()` already exists there.
5. **Add `install_source` to `config-schema.json`** — add an optional string field at the root config level (alongside `project`, `issues`, etc.).
6. **Write `scripts/tests/test_init_install.py`** — test `detect_installation()` and `check_version()` following `TestValidateDeps` in `test_init_core.py`. Mock `importlib.metadata.version` and `subprocess.run`. Scenarios: no installation, local-only, global-only, both present, version match, version drift.
7. **Run** `python -m pytest scripts/tests/ -k "init and install"` to verify.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Inject `install_source` post-`build_config()`** in `_run_yes()` (`init/cli.py`) — after `config = build_config(template, choices)`, add `if install_source: config["install_source"] = install_source`; `build_config()` in `init/core.py` does not accept `install_source` and must not be changed; apply the same injection pattern in `run_tui()`'s `_apply_config()` helper in `init/tui.py`
9. **Update `scripts/tests/test_init_tui.py`** — add `install_confirmed: bool = True` parameter to `_wire_q()` helper (prepend it to `confirm_returns`); update `TestDesignTokenProfilePicker.test_profile_warm_paper_written_to_config`, `TestCtrlC.test_ctrl_c_on_confirm_returns_130`, `TestCtrlC.test_user_declines_confirm_returns_1_no_config`, and `TestHostSelection.test_ctrl_c_on_hosts_returns_130` to account for the new first `confirm()` call
10. **Add `test_install_source_in_schema`** to `scripts/tests/test_config_schema.py:TestConfigSchema` — verifies `install_source` is declared in `config-schema.json` properties before any code writes it to `.ll/ll-config.json`
11. **Mock `detect_installation()`** in all `TestMainInit` tests in `scripts/tests/test_init_core.py` that call `main_init(["--yes", ...])` — add `@patch("little_loops.init.cli.detect_installation", return_value=(None, None))` to the patch stack
12. **Export from `scripts/little_loops/init/__init__.py`** — if `detect_installation`, `check_version`, or `InstallStatus` are used outside the `init` package, add them to the module's `__all__` list
13. **Update `.claude/CLAUDE.md`** — `ll-init` one-liner in CLI Tools list; append `detects existing install and version drift` to the parenthetical description

## Acceptance Criteria

- [ ] `ll-init` on a machine with no plugin installed proceeds through install before wizard rounds.
- [ ] `ll-init` on a machine with an out-of-date install offers upgrade before wizard rounds.
- [ ] `ll-init --yes` (headless) installs or upgrades without prompts.
- [ ] `ll-init` on a machine with a current install skips the install step silently.
- [ ] All host CLIs supported by `resolve_host()` have appropriate install dispatch.
- [ ] Tests pass: `python -m pytest scripts/tests/ -k "init and install"`.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/install_check.py` (new) — `detect_installation()` and `check_version()`; reuse logic from `_check_little_loops_version()` in `validate.py`
- `scripts/little_loops/init/cli.py` — extend `_run_yes()` and (via `tui.py`) the TUI path to call `detect_installation()` before first wizard round
- `scripts/little_loops/init/validate.py` — consider extracting `_check_little_loops_version()` into `install_check.py` to avoid duplication (or call it from there)
- `config-schema.json` — add optional `install_source` string field to root config definition

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/core.py` — `build_config()` returns a plain dict with no `install_source` key; inject `config["install_source"] = install_source_value` into the dict returned by `build_config()` **before** calling `write_config()` in both `_run_yes()` and the TUI path's `_apply_config()`; do not pass `install_source` into `build_config()` itself
- `scripts/little_loops/init/__init__.py` — if `detect_installation`, `check_version`, or `InstallStatus` are part of the public init API, add them to the exports here (follow existing export pattern)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py` — `_run_yes()` and `_run_apply()` are primary consumers; `main_init()` is the registered entry point (`ll-init = "little_loops.cli:main_init"` → re-exported from `little_loops.init.cli`)
- `scripts/little_loops/init/tui.py` — `run_tui()` needs the pre-round-1 install check
- Any automation that calls `ll-init --yes` (CI scripts, headless flows)

### Similar Patterns
- `scripts/little_loops/init/validate.py:_check_little_loops_version()` — existing version detection via `importlib.metadata.version("little-loops")`; catch `PackageNotFoundError` for not-installed case; follow this exact pattern
- `scripts/little_loops/cli/action.py:cmd_capabilities()` — canonical pattern for executing `build_version_check()` via `subprocess.run`; includes `timeout=10` and `(subprocess.TimeoutExpired, FileNotFoundError, OSError)` error handling
- `scripts/little_loops/init/cli.py:_detect_hosts()` — `shutil.which()` binary probe pattern used by `_dispatch_host_adapters()`
- `scripts/little_loops/host_runner.py` — `resolve_host()` and `build_version_check()` already exist on all runners; **no new methods needed** in this file

### Tests
- `scripts/tests/test_init_install.py` (new) — covering: no installation, local-only, global-only, both present, version match, version drift
- Model after `scripts/tests/test_init_core.py:TestValidateDeps` — uses `patch("little_loops.init.validate.importlib.metadata.version", side_effect=PackageNotFoundError(...))` and `return_value="1.0.0"` for version mismatch

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py` — **will break** when Round 0 is added: `_wire_q()` builds `confirm_returns` as a positionally ordered list; new install `questionary.confirm()` prepends a call before `add_excludes`, shifting all positions by +1. Must add `install_confirmed: bool = True` to `_wire_q()` and update manual `mock_q.confirm.side_effect` lists in: `TestDesignTokenProfilePicker.test_profile_warm_paper_written_to_config` (5 entries → 6), `TestCtrlC.test_ctrl_c_on_confirm_returns_130`, `TestCtrlC.test_user_declines_confirm_returns_1_no_config`, `TestHostSelection.test_ctrl_c_on_hosts_returns_130` (4 entries → 5)
- `scripts/tests/test_config_schema.py` — add `test_install_source_in_schema` to `TestConfigSchema`; root schema has `"additionalProperties": false` so `install_source` written to config before being declared in the schema will fail validation; pattern: `assert "install_source" in json.loads(CONFIG_SCHEMA.read_text())["properties"]`
- `scripts/tests/test_init_core.py` (`TestMainInit`) — all `main_init(["--yes", ...])` tests will fail once `detect_installation()` is called inside `_run_yes()`; add `patch("little_loops.init.cli.detect_installation", return_value=(None, None))` to the `@patch` stacks; mock path strings: `"little_loops.init.install_check.importlib.metadata.version"`, `"little_loops.init.install_check.shutil.which"`, `"little_loops.init.install_check.subprocess.run"`

### Documentation
- `docs/reference/CLI.md` — `ll-init` section should document `--yes` install behavior and `install_source` config field
- `docs/reference/HOST_COMPATIBILITY.md` — add per-host plugin install commands to capability matrix

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — update `ll-init` one-liner in CLI Tools list to include install detection behavior (currently reads: "headless core; `--yes`, `--dry-run`, `--plan`/`apply`, `--hosts` multi-select; always writes `loops.run_defaults` into generated config")

### Configuration
- `config-schema.json` — add optional `install_source` field (suggested values: `"local-editable"`, `"global-claude-code"`, `"global-codex"`, `"global-pi"`, `null`)
- Generated `.ll/ll-config.json` — written by `write_config()` in `init/writers.py` via `atomic_write_json()`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Existing code that overlaps with the proposed implementation:**

- `scripts/little_loops/init/validate.py:_check_little_loops_version()` — already does `importlib.metadata.version("little-loops")`, catches `PackageNotFoundError`, and compares versions. The new `detect_installation()` + `check_version()` pair should call or refactor this function rather than re-implement the same logic.

**Corrected entry point path:**

- The issue originally referenced `scripts/little_loops/cli/init.py` — the actual file is `scripts/little_loops/init/cli.py`. The `ll-init = "little_loops.cli:main_init"` entry point in `pyproject.toml` re-exports `main_init` from `little_loops.init.cli` via `scripts/little_loops/cli/__init__.py`.

**`build_version_check()` already exists:**

- All concrete `HostRunner` implementations in `host_runner.py` already have `build_version_check()` returning `HostInvocation(binary="<host>", args=["--version"], ...)`. No changes needed to `host_runner.py` for version-checking; the new code only needs to call it.
- Note: `OpenCodeRunner` and `PiRunner` raise `HostNotConfigured` from `build_version_check()` — handle this in `detect_installation()`.

**Exact insert points:**

- **Headless path** (`_run_yes()` in `init/cli.py`): insert `detect_installation()` call after the `existing_config` load block (`if _existing_path is not None: ...`) and before `project_type, template = detect_project_type(project_root)`.
- **TUI path** (`run_tui()` in `init/tui.py`): insert after the `existing_config` load block and before `console.rule("[bold]1 / 6  Project Basics[/bold]")`. A new "0 / 6 Plugin Install" screen would shift all existing round numbers to "N+1 / 7".

**Plugin list command for global registration detection:**

- Use `claude plugin list` (not `claude mcp list`) — this is the command used in `skills/update/SKILL.md` Step 2 to detect `ll@little-loops`. No Python wrapper exists; implement as a `subprocess.run(["claude", "plugin", "list"], ...)` call guarded by `shutil.which("claude")` check, modeled after the `cmd_capabilities()` pattern in `cli/action.py`.

**TUI screen expansion:**

- Adding a "Round 0" shifts existing 1/6–6/6 labels to 2/7–7/7. Each screen uses `console.rule("[bold]N / 6  Label[/bold]")` and `if result is None: return 130` (Ctrl-C guard). Follow this pattern exactly.

## Impact

- **Priority**: P2 — Medium. Breaks the "one-command setup" promise for new users and CI environments; not blocking existing installs but materially degrades first-run DX.
- **Effort**: Medium — New detection utilities (~2 functions), one wizard extension, per-host install dispatch, and a dedicated test file.
- **Risk**: Low — New code path executed before the existing wizard rounds; no changes to current wizard logic or config format.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | Host CLI abstraction and resolve_host() patterns |
| `docs/reference/HOST_COMPATIBILITY.md` | Per-host capability matrix and install commands |

## Status

open

---

## Session Log
- `/ll:confidence-check` - 2026-06-20T00:00:00Z - `141f626f-5cf5-41a6-a306-b7cee561efb4.jsonl`
- `/ll:wire-issue` - 2026-06-21T02:42:48 - `81a3e5b3-1459-4b5f-b2ac-84e042c77111.jsonl`
- `/ll:refine-issue` - 2026-06-21T02:20:06 - `7821b45a-10dc-484b-b3b3-374cbf9fb76a.jsonl`
- `/ll:format-issue` - 2026-06-21T02:13:56 - `bd1e198e-bec0-4314-99a3-895c2055f1b5.jsonl`
- `/ll:capture-issue` - 2026-06-21T02:09:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6dcac093-dc3f-4cd9-afae-3043aafa86f4.jsonl`
