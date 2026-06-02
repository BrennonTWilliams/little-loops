---
id: ENH-1781
title: Create shared output formatting utility for ll-* CLIs
type: enh
status: done
priority: P3
decision_needed: false
captured_at: '2026-05-29T02:23:45Z'
completed_at: '2026-05-29T04:45:35Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- cli
- ux
- captured
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1781: Create shared output formatting utility for ll-* CLIs

## Summary

Create a shared `ll_output` module providing consistent colored messages, tables, progress bars, and status blocks across all `ll-*` CLIs. Modeled after CLI-Anything's `repl_skin.py` which gives 42+ generated CLIs a unified look and feel.

## Current Behavior

Each `ll-*` CLI implements its own output formatting — colors, table rendering, status messages, progress indicators — leading to:
- Inconsistent UX across tools
- Duplicated formatting code
- Varying quality of terminal output

## Expected Behavior

All `ll-*` CLIs use a shared `scripts/little_loops/output.py` module providing:
- **Colored messages**: `success()`, `error()`, `warning()`, `info()`, `hint()` — each with consistent icons, colors, and stream routing (stdout vs stderr)
- **Table rendering**: auto-width columns, box-drawing separators, optional JSON mode
- **Progress bars**: 20-char bar with configurable width
- **Status blocks**: key-value pairs with aligned labels
- **Environment awareness**: respects `NO_COLOR`, `FORCE_COLOR`, terminal detection

## Motivation

CLI-Anything's `repl_skin.py` demonstrates that a single shared output module eliminates inconsistency across a family of related CLIs. Little-loops has ~20 CLIs with varying output quality. A shared utility:
- Makes all tools feel like one product
- Eliminates duplication (each CLI shouldn't reinvent table rendering)
- Makes it trivial to add `--json` / `--plain` mode switching globally

## Success Metrics

- All new CLI output uses the shared utility (0 ad-hoc formatting in new or refactored code)
- At least 3 core CLIs migrated (`ll-issues`, `ll-loop`, `ll-sprint`)
- Consistent icon and color scheme across all migrated tools (visual audit passes)

## Scope Boundaries

- **In scope**: Creating `scripts/little_loops/output.py` with message, table, progress, and status helpers; incremental CLI migration starting with highest-use CLIs; respecting `NO_COLOR`/`FORCE_COLOR`; tests for each formatter
- **Out of scope**: Rewriting all ~20 CLIs at once; changing any CLI's behavior or output structure (only the formatting implementation); adding new output features beyond the five helpers defined in Proposed Solution; JSON output mode (covered by ENH-1780)

## Proposed Solution

Create `scripts/little_loops/output.py` with:

```python
# Core message helpers
def success(msg: str) -> None: ...
def error(msg: str) -> None: ...
def warning(msg: str) -> None: ...
def info(msg: str) -> None: ...
def hint(msg: str) -> None: ...

# Structured output
def table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str: ...
def status_block(items: dict[str, str]) -> str: ...
def progress(current: int, total: int, width: int = 20) -> str: ...

# Mode toggling
def set_output_mode(mode: "human" | "json" | "plain") -> None: ...
```

Refactor existing CLIs to use it incrementally, starting with the most frequently used: `ll-issues`, `ll-loop`, `ll-sprint`.

## API/Interface

```python
# Core message helpers
def success(msg: str) -> None: ...
def error(msg: str) -> None: ...
def warning(msg: str) -> None: ...
def info(msg: str) -> None: ...
def hint(msg: str) -> None: ...

# Structured output
def table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str: ...
def status_block(items: dict[str, str]) -> str: ...
def progress(current: int, total: int, width: int = 20) -> str: ...

# Mode toggling
def set_output_mode(mode: Literal["human", "json", "plain"]) -> None: ...
```

## Integration Map

### Files to Modify
- **Existing shared output module**: `scripts/little_loops/cli/output.py:1` — provides `colorize()`, `configure_output()`, `print_json()`, `terminal_width()`, `wrap_text()`, `format_relative_time()`, `use_color_enabled()`, and module-level `PRIORITY_COLOR`/`TYPE_COLOR` dicts. The proposed `success()`/`error()`/`warning()`/`info()`/`hint()` message helpers and `table()`/`status_block()`/`progress()` structured formatters should be added either here or in a new `scripts/little_loops/output.py`.
- **Logger with similar-named methods**: `scripts/little_loops/logger.py:17` — `Logger` class provides timestamped `success()`, `error()`, `warning()`, `info()` methods designed for automation-tool logging. The proposed message helpers are distinct: simple, untimestamped, user-facing CLI messages (analogous to `click.secho`).
- **Shared arg helpers**: `scripts/little_loops/cli_args.py:197` — `add_json_arg()` is the pattern for shared CLI arg helpers; a similar `add_plain_arg()` or output-mode flag helper may be warranted.
- **Config dataclasses**: `scripts/little_loops/config/cli.py:125` — `CliColorsConfig`, `CliColorsLoggerConfig`, `CliColorsPriorityConfig`, `CliColorsTypeConfig` control ANSI color overrides. Any new colorized output should integrate with this config schema.
- **CLI entry points to migrate** (30+ files import from `cli.output`):
  - `scripts/little_loops/cli/issues/` — list_cmd, show, search, clusters, impact_effort, refine_status (heaviest ad-hoc table/box rendering)
  - `scripts/little_loops/cli/loop/` — info, layout (FSM diagram rendering), lifecycle, run, next_loop
  - `scripts/little_loops/cli/sprint/` — show, _helpers (execution plan display with box-drawing)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The issue states "30+ files import from cli.output" but only names ~7. These are the remaining 14 non-migration CLI files that directly depend on `cli/output.py` and would be affected by signature changes:

- `scripts/little_loops/cli/session.py` — imports `configure_output, print_json, use_color_enabled`
- `scripts/little_loops/cli/history.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/auto.py` — imports `configure_output`
- `scripts/little_loops/cli/parallel.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/action.py` — lazy imports `print_json`
- `scripts/little_loops/cli/doctor.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/ctx_stats.py` — imports `configure_output, print_json, use_color_enabled`
- `scripts/little_loops/cli/docs.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/deps.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/logs.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/schemas.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/create_extension.py` — imports `configure_output, use_color_enabled`
- `scripts/little_loops/cli/learning_tests.py` — lazy imports `print_json`
- `scripts/little_loops/workflow_sequence/__init__.py` — imports `configure_output, use_color_enabled`

Deep/internal consumers (non-CLI entry points that import from `cli/output.py`):

- `scripts/little_loops/issue_manager.py:126` — lazy imports `terminal_width` for display computation; line 998 lazy imports `use_color_enabled` for Logger wiring
- `scripts/little_loops/parallel/orchestrator.py:85` — lazy imports `use_color_enabled` for Logger wiring

Subpackage dispatchers (each calls `configure_output()` and routes to subcommands):

- `scripts/little_loops/cli/issues/__init__.py:634` — `configure_output(config.cli)`
- `scripts/little_loops/cli/loop/__init__.py:39` — `configure_output(config.cli)`
- `scripts/little_loops/cli/sprint/__init__.py:223` — `configure_output(config.cli)`

### Similar Patterns
- CLI-Anything `repl_skin.py` — the reference implementation for unified CLI output
- `format_result_*()` convention in `scripts/little_loops/link_checker.py:362`, `scripts/little_loops/doc_counts.py:185`, `scripts/little_loops/issue_history/formatting.py:18` — one-function-per-output-format pattern (`_text()`, `_json()`, `_markdown()`)
- `scripts/little_loops/design_tokens.py` — `render_as_prompt_context()` and `render_as_css_vars()` pattern for format-switchable output

### Tests

**New tests to write** (unit tests for the planned helpers):
- `scripts/tests/test_output.py` (or extend `test_cli_output.py`) — unit tests for message helpers, table, status_block, progress
- `test_add_plain_arg()` in `test_cli_args.py` — follow `TestAddJsonArg` pattern at lines 482-518

**Existing untested functions** in `cli/output.py` that should get coverage (independent of ENH-1781):
- `format_relative_time()` at `cli/output.py:119` — zero tests
- `wrap_text()` at `cli/output.py:31` — zero tests
- `print_json()` at `cli/output.py:114` — zero tests

**Existing test files that will need updates** (these mock `_USE_COLOR` or `terminal_width` directly — if the module location changes, all mock paths break):

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_cli_output.py` — 337 lines; dedicated tests for `colorize()`, `configure_output()`, `terminal_width()`, `_USE_COLOR`
- `scripts/tests/test_logger.py` — 768 lines; `Logger` class tests for same-named `success()`/`error()`/`warning()`/`info()` methods. `Logger.__init__` color-detection must stay in sync with any `FORCE_COLOR` addition to `configure_output()`
- `scripts/tests/test_config.py` — lines 1796-1896; `TestCliColorsLoggerConfig`, `TestCliColorsPriorityConfig`, `TestCliColorsTypeConfig`, `TestCliColorsConfig`. Extend for any new color dataclass fields added
- `scripts/tests/test_cli_args.py` — lines 482-518; `TestAddJsonArg` is the model for `add_plain_arg()` tests
- `scripts/tests/test_issues_cli.py` — ~26 tests that reference `output_mod._USE_COLOR` or assert on color/ANSI output
- `scripts/tests/test_ll_loop_display.py` — ~15 tests patching `output_mod._USE_COLOR`
- `scripts/tests/test_sprint.py` — ~12 tests patching `output_mod._USE_COLOR`
- `scripts/tests/test_cli.py` — lines 1421, 1440; 2 locations accessing `output_mod._USE_COLOR`
- `scripts/tests/test_ll_loop_commands.py` — lines 828, 925; patches `little_loops.cli.output._USE_COLOR`
- `scripts/tests/test_subprocess_mocks.py` — lines 307, 346; patches `little_loops.cli.output.terminal_width`
- `scripts/tests/test_cli_ctx_stats.py` — lines 70-86; `TestProgressBar` is the existing progress bar test pattern to model new `progress()` tests after

**Total: ~55 test locations across 11 test files** that interact with `_USE_COLOR`, `colorize()`, `configure_output()`, or `terminal_width()`.

### Documentation
- `docs/reference/API.md` lines 111-161 — already documents `cli.output` functions and color config schema; extend for new helpers
- `docs/reference/OUTPUT_STYLING.md` (319 lines) — **Primary reference** for `cli/output.py` API. Documents `colorize()`, `terminal_width()`, `PRIORITY_COLOR`, `TYPE_COLOR`, `configure_output()`, and has an "Adding New Styled Output" section (line 309) prescribing `from little_loops.cli.output import colorize, terminal_width, wrap_text`. Must be extended with new helper signatures, usage examples, and mode toggling docs. _Wiring pass added by `/ll:wire-issue`._
- `docs/reference/CONFIGURATION.md` (lines 663-758) — Documents `cli.color`, `cli.colors.logger.*`, `cli.colors.priority.*`, `cli.colors.type.*`, `cli.colors.fsm_*`. Must be extended if new config keys are added for message helper colors or output mode. _Wiring pass added by `/ll:wire-issue`._
- `CONTRIBUTING.md:202` — Directory tree listing references `output.py` as "Shared CLI output utilities (colors, terminal width)". Must be updated if a new module file is created (Options B or C). _Wiring pass added by `/ll:wire-issue`._
- `docs/ARCHITECTURE.md` — directory tree at line 211 lists `output.py` under `cli/`; line 241 lists `cli_args.py`. Must be updated if module location changes (Options B/C). _Wiring pass added by `/ll:wire-issue`._

### Configuration
- `scripts/little_loops/config/cli.py:163` — `CliConfig.color: bool` already controls color enable/disable via `configure_output()`. New output helpers should respect the same `_USE_COLOR` flag.
- `config-schema.json` (lines 1016-1090) — JSON Schema for `cli.color`, `cli.colors.logger.*`, `cli.colors.priority.*`, `cli.colors.type.*`, `cli.colors.fsm_*`. Must be updated if new config keys are added (e.g., output mode, message helper colors, FORCE_COLOR toggle). _Wiring pass added by `/ll:wire-issue`._
- `scripts/little_loops/config/__init__.py` — Re-exports all `Cli*` config types. Must be updated if new dataclasses are added (e.g., `CliOutputConfig` for message helper settings). _Wiring pass added by `/ll:wire-issue`._
- `.claude-plugin/plugin.json` — Plugin manifest. If a new module is created at package root (Option B), it must be registered here. _Wiring pass added by `/ll:wire-issue`._

### Dependencies
- `scripts/pyproject.toml` — `wcwidth` is already a dependency for terminal width calculation. No external libraries (`rich`, `colorama`, `termcolor`) are used; all formatting is raw ANSI via `colorize()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing shared output module already exists**: `scripts/little_loops/cli/output.py` is the de-facto shared output utility imported by 30+ files. The issue's proposed filename `scripts/little_loops/output.py` (package root, not under `cli/`) would be a NEW module adjacent to the existing one — raising a location decision: extend `cli/output.py` vs. create a separate `output.py` at package root.
- **`Logger` class vs. proposed message helpers**: `scripts/little_loops/logger.py`'s `Logger` class already has timestamped `success()`, `error()`, `warning()`, `info()` methods. The proposed `success()`/`error()`/`warning()`/`info()`/`hint()` functions are conceptually distinct (simple, untimestamped, user-facing messages vs. automation-tool logging), but the naming overlap warrants explicit differentiation in the API design.
- **No shared `--plain` mode flag**: `add_json_arg()` in `cli_args.py:197` is the only shared mode-toggle arg helper. There is no shared `--plain` or `--no-color` CLI flag; a few CLIs define `--format` with `choices=["table", "json"]` inline. The proposed `set_output_mode()` would need a corresponding CLI arg helper.
- **Ad-hoc table rendering is widespread**: `cli/issues/refine_status.py`, `cli/issues/impact_effort.py` (2x2 ASCII grid), `cli/issues/clusters.py` (box diagrams), `cli/issues/show.py` (box-drawing cards), `cli/loop/layout.py` (FSM diagrams), and `cli/sprint/_helpers.py` (execution plan display) each build their own column-width arithmetic and box-drawing logic. A shared `table()` helper would eliminate significant duplication.
- **`FORCE_COLOR` is NOT currently checked**: Only `NO_COLOR` and `isatty()` control `_USE_COLOR`. The issue's Expected Behavior mentions `FORCE_COLOR` support, which would be additive to the existing logic in `configure_output()` (`cli/output.py:59`) and `Logger.__init__()` (`logger.py:53`).
- **Specific duplication to consolidate**: `_strip_ansi()` / `_ANSI_RE` is copy-pasted in 4 files (`cli/issues/show.py:278`, `cli/loop/info.py:257`, `cli/loop/layout.py:21`, `cli/loop/_helpers.py:58`); box-drawing characters (`─`, `│`, `┌`, etc.) are defined locally in 5+ renderers (`cli/issues/show.py`, `cli/issues/impact_effort.py`, `cli/issues/clusters.py`, `cli/sprint/_helpers.py`, `cli/loop/layout.py`). The new module should provide a single `strip_ansi()` and shared box-drawing constants.
- **Existing progress bar to model**: `scripts/little_loops/cli/ctx_stats.py:_progress_bar()` at line 92 implements a simple `|#### |` string — the only progress bar in the codebase. The proposed `progress()` function could generalize this pattern.
- **Existing symbol registry**: `scripts/little_loops/cli/doctor.py:_STATUS_SYMBOLS` at line 12 maps statuses to `✓`/`○`/`✗` — a partial precedent for the issue's proposed icon consistency. The new module should provide a canonical symbol/icon set.

## Implementation Steps

### Phase 1: Decide module location (resolve `decision_needed`)
- **Option A**: Extend existing `scripts/little_loops/cli/output.py` — single shared module, no new file, all output utilities co-located. Import stays `from little_loops.cli.output import ...`.
  > **Selected:** Option A — single shared module, no new file, all output utilities co-located; highest reuse score (3/3) with zero import path changes.
- **Option B**: Create new `scripts/little_loops/output.py` at package root — separates "pure formatting" (messages, tables, progress) from "CLI display plumbing" (colorize, configure_output, terminal_width). Requires new import path `from little_loops.output import ...`.
- **Option C**: Create `scripts/little_loops/cli/output/` subpackage — split into `formatting.py` (message/table/status/progress helpers) and keep `output.py` for terminal plumbing (colorize, configure_output, etc.).

### Phase 2: Implement shared helpers
1. Add `success()`/`error()`/`warning()`/`info()`/`hint()` message helpers to the chosen module location — simple functions that print to stdout (or stderr for error) with consistent icons and colors, respecting `_USE_COLOR` from `cli/output.py:41`. Differentiate from `Logger` (`logger.py:17`) by omitting timestamps and using `sys.stdout` (not `Logger`'s `_format` wrapper).
2. Add `table(headers, rows, max_col_width)` — auto-width columns using `terminal_width()` from `cli/output.py:26` and `wcwidth` (already in `pyproject.toml`); model after column arithmetic in `cli/issues/refine_status.py` and box-drawing in `cli/issues/show.py`.
3. Add `status_block(items: dict[str, str])` — aligned key-value pairs, model after `CliColorsConfig` dataclass structure in `config/cli.py:125`.
4. Add `progress(current, total, width)` — follow existing `format_duration()` pattern in `logger.py:115` for pure-function return-a-string design.
5. Add `set_output_mode(mode: Literal["human", "json", "plain"])` — integrate with `configure_output()` (`cli/output.py:59`) and `add_json_arg()` (`cli_args.py:197`); add `FORCE_COLOR` support to `configure_output()`'s existing `NO_COLOR` + `isatty()` check.
6. Optionally add `add_plain_arg()` helper to `cli_args.py:197` alongside `add_json_arg()`.

### Phase 3: Test
1. Create `scripts/tests/test_output.py` (or extend `scripts/tests/test_cli_output.py`) following existing patterns: `capsys` fixture for stdout/stderr capture, `patch.object` for `_USE_COLOR` mocking, `patch.dict("os.environ", {"NO_COLOR": "1"})` for env-var tests, and `FlushTracker` pattern from `test_logger.py:572` for verifying flush behavior.

### Phase 4: Migrate CLIs incrementally
1. Migrate `ll-issues list` (`cli/issues/list_cmd.py`) as proof-of-concept — replace direct `colorize()` calls with message helpers where appropriate.
2. Migrate `ll-loop info` (`cli/loop/info.py`) and `ll-sprint show` (`cli/sprint/show.py`).
3. Incrementally migrate remaining CLIs.

### Phase 5: Documentation
1. Extend `docs/reference/API.md` section on `cli.output` (lines 111-161) with new function signatures and usage examples.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/reference/OUTPUT_STYLING.md` — the primary reference document (319 lines); add new helper signatures, usage examples, mode toggling docs, and update the "Adding New Styled Output" section
2. Update `docs/reference/CONFIGURATION.md` (lines 663-758) — extend cli config section if new config keys are added
3. Update `config-schema.json` (lines 1016-1090) — add JSON Schema entries for any new config keys (output mode, message helper colors, FORCE_COLOR toggle)
4. Update `scripts/little_loops/config/__init__.py` — re-export any new dataclasses
5. Update `CONTRIBUTING.md:202` — directory tree listing if a new module file is created (Options B/C)
6. Update `.claude-plugin/plugin.json` — register new module if created at package root (Option B)
7. Extend `scripts/tests/test_config.py` (lines 1796-1896) — add test cases for new color dataclass fields
8. Extend `scripts/tests/test_cli_args.py` (lines 482-518) — add `TestAddPlainArg` following `TestAddJsonArg` pattern
9. Add tests for 3 currently-untested functions in `cli/output.py`: `format_relative_time()`, `wrap_text()`, `print_json()`
10. If `_USE_COLOR` is refactored or moved, update ~55 mock paths across 11 test files (`test_issues_cli.py`, `test_ll_loop_display.py`, `test_sprint.py`, `test_cli.py`, `test_ll_loop_commands.py`, `test_subprocess_mocks.py`)
11. Ensure `Logger.__init__` color-detection (`logger.py:53`) stays in sync with any `FORCE_COLOR` addition to `configure_output()` — both currently use the same `isatty() and not NO_COLOR` logic
12. Provide shared `strip_ansi()` and box-drawing constants in the new module, then migrate the 3 copy-pasted `_strip_ansi()` definitions and 5+ local box-drawing character sets to use the shared versions
13. Add `add_plain_arg` to `__all__` list in `cli_args.py` (lines 436-462) alongside existing entries like `add_json_arg`
14. Wire any new top-level `cli` config keys through `CliConfig.from_dict()` in `config/core.py:209` — `self._cli = CliConfig.from_dict(self._raw_config.get("cli", {}))`

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-28.

**Selected**: Option A — Extend existing `scripts/little_loops/cli/output.py`

**Reasoning**: Option A wins decisively (12/12) because it requires zero new files, zero import path changes, and directly reuses 10 existing utilities (`_USE_COLOR`, `colorize()`, `configure_output()`, `terminal_width()`, `print_json()`, `PRIORITY_COLOR`, `TYPE_COLOR`, `wcwidth`, `test_cli_output.py` fixtures, `add_json_arg()` pattern). The 31 source files already importing from `cli.output` need no import changes, and 55 test mock-patch locations remain valid without updates. `docs/reference/OUTPUT_STYLING.md:311` already prescribes `from little_loops.cli.output import ...` as the documented import path for new styled output. Options B and C both introduce friction (dual import paths, re-export infrastructure, conceptual boundary decisions) without offsetting benefit.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (extend cli/output.py) | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| Option B (new root output.py) | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| Option C (cli/output/ subpackage) | 1/3 | 0/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- **Option A**: 31 source files import from `cli.output`; `configure_output()` central dispatch called by 6 CLI subpackage init points; existing `test_cli_output.py` (337 lines) provides established test patterns; `OUTPUT_STYLING.md` documents `cli.output` as the canonical import path. No external libraries (`rich`, `colorama`, `termcolor`) — all formatting is raw ANSI via `colorize()`, which this option extends directly.
- **Option B**: Package-root placement has precedent (34 modules at root vs 24 under `cli/`), but `output_parsing.py` (root) handles *parsing* not *rendering*; `cli_args.py` (root) provides *argparse helpers* not *output formatting*. No package-root module has a module-level dependency on `cli/` (only lazy imports exist). Dual imports per file add friction.
- **Option C**: Subpackage pattern exists for dispatch domains (`issues/`, `sprint/`, `loop/`) but not for splitting a single utility into orthogonal layers. `_helpers.py` files serve command modules, not other utility modules. Highest complexity with re-export infrastructure and conceptual boundary decisions.

## Impact

- **Priority**: P3 — Not blocking, quality-of-life improvement across all CLIs
- **Effort**: Medium — New module is small; refactoring ~20 CLIs is the bulk
- **Risk**: Low — Additive; existing output unchanged until each CLI is explicitly migrated
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-29_

**Readiness Score**: 86/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- ~~**Unresolved module location decision**~~ **Resolved**: Option A (extend `cli/output.py`) was selected by `/ll:decide-issue` on 2026-05-28. See Decision Rationale section for scoring.
- **Logger naming overlap**: `Logger.success()`/`error()`/`warning()`/`info()` exist in `logger.py` — the new helpers must be clearly differentiated in naming and documentation to avoid confusion.

## Session Log
- `/ll:ready-issue` - 2026-05-29T04:34:16 - `7bd0959b-eb56-4c78-8696-f768fa1526d0.jsonl`
- `/ll:ready-issue` - 2026-05-29T04:31:17 - `b559abf7-354c-489b-8008-e056852380f3.jsonl`
- `/ll:decide-issue` - 2026-05-29T04:26:44 - `de671d7a-96d8-4b3e-86d0-8534a69f8651.jsonl`
- `/ll:wire-issue` - 2026-05-29T04:18:35 - `99c7c1db-35d5-4a7c-b7dc-b29122ffe376.jsonl`
- `/ll:refine-issue` - 2026-05-29T04:12:49 - `e3c725de-2d7b-44bf-b709-fdf814aae9f0.jsonl`
- `/ll:refine-issue` - 2026-05-29T04:10:39 - `1fcbddfc-b25b-47de-86e4-c658d5238d68.jsonl`
- `/ll:format-issue` - 2026-05-29T02:28:33 - `9e23d1bf-3385-43d7-80c9-602fafbaf867.jsonl`
- `/ll:capture-issue` - 2026-05-29T02:23:45Z - `8b24cba6-684e-4420-9519-de98c8b4822b.jsonl`
- `/ll:confidence-check` - 2026-05-29T06:00:00 - `34f618d5-57ea-4064-abe4-6f6f199791bc.jsonl`
- `/ll:confidence-check` - 2026-05-29T06:00:00 - `5947ea14-7070-4b6b-8b99-f8662c07901a.jsonl`
- `/ll:confidence-check` - 2026-05-29T07:00:00 - `ac839f3f-026b-4b53-bdc8-45cc3941db7e.jsonl`
- `/ll:confidence-check` - 2026-05-29T07:45:00 - `c4eda6ba-f152-4a9f-af9d-8dad1d8ad478.jsonl`
- `/ll:ready-issue` - 2026-05-28T00:00:00 - `current-session.jsonl`
- `/ll:manage-issue` - 2026-05-29T04:45:35Z - `32ec6455-fe59-410e-b50d-9f823d1eb658.jsonl`

## Resolution

Implemented by extending `scripts/little_loops/cli/output.py` with new helpers:

- **ANSI stripping**: `strip_ansi()` and shared `_ANSI_RE` regex
- **Box-drawing constants**: `BOX_H`, `BOX_V`, `BOX_TL`, `BOX_TR`, `BOX_BL`, `BOX_BR`, `BOX_ML`, `BOX_MR`
- **Message helpers**: `success()`, `error()`, `warning()`, `info()`, `hint()` — icon-prefixed, icon-only-when-color, `error()` to stderr, all with flush
- **Structured formatters**: `table()` (box-drawn, auto-width, truncation), `status_block()` (aligned key-value pairs), `progress()` (|####  | bar)
- **FORCE_COLOR support**: `FORCE_COLOR=1` enables color without TTY; `NO_COLOR` takes precedence
- **Output mode toggling**: `set_output_mode()` / `get_output_mode()` with `human`/`json`/`plain` modes

Migration of duplicated patterns:
- `cli/loop/_helpers.py`: replaced `_ANSI_RE` with `strip_ansi`
- `cli/loop/info.py`: replaced `_ANSI_RE` + `_strip_ansi()` with `strip_ansi`
- `cli/issues/show.py`: replaced `_ANSI_RE` + `_strip_ansi()` with `strip_ansi`
- `cli/loop/layout.py`: replaced `_ANSI_ESCAPE_RE` with `strip_ansi`

Tests: 36 new tests in `test_cli_output.py` (62 total, all passing). Lint and type checks pass.

---

**Done** | Completed: 2026-05-29T04:45:35Z | Priority: P3
