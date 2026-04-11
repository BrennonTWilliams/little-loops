---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
---

# FEAT-916: Extension SDK with Scaffolding Command and Test Harness

## Summary

Provide developer experience tooling for extension authors: an `ll-create-extension` command that scaffolds a new extension repo with correct `pyproject.toml` entry points, a skeleton `on_event` handler, and a test harness (`LLTestBus`) that replays recorded `.events.jsonl` files through extensions for offline testing. The skeleton references `docs/reference/EVENT-SCHEMA.md` for event type documentation. JSON Schema generation is tracked separately in FEAT-919.

## Context

Identified from conversation reviewing FEAT-911's "unconstrained vision." Without scaffolding and test tooling, every extension author must reverse-engineer the setup from docs alone. A proper SDK lowers the barrier to building extensions.

## Current Behavior

No extension system exists yet (FEAT-911 pending). Once FEAT-911 ships, extension authors would need to manually configure `pyproject.toml` entry points, implement the Protocol from scratch, and run real loops to test their extensions.

## Expected Behavior

- `ll-create-extension <name>` scaffolds a new directory/repo with:
  - `pyproject.toml` with correct `[project.entry-points."little_loops.extensions"]`
  - Skeleton `on_event` handler implementing `LLExtension` Protocol; comment links to `docs/reference/EVENT-SCHEMA.md` for event type reference
  - Example test using `LLTestBus`
- `LLTestBus` class loads a recorded `.events.jsonl`, replays events through an extension, and exposes `delivered_events` for assertions — no real loop execution needed

## Motivation

Extension ecosystems live or die on developer experience. Scaffolding eliminates boilerplate; the test harness eliminates the need to run full loops during development; published schemas let non-Python tools validate events.

## Proposed Solution

1. Create `ll-create-extension` CLI command (new entry point in `scripts/pyproject.toml`)
2. Add scaffolding templates under `templates/extension/` with string substitution; skeleton `extension.py` includes a comment linking to `docs/reference/EVENT-SCHEMA.md` for event type reference
3. Implement `LLTestBus` in `scripts/little_loops/testing.py` — reads JSONL, replays through extension's `on_event`, collects results
4. Export `LLTestBus` from `scripts/little_loops/__init__.py`

## Integration Map

### Files to Modify
- `scripts/pyproject.toml` — add `ll create-extension` entry point and `little-loops[dev]` optional dependency group
- `scripts/little_loops/testing.py` — create `LLTestBus` class (new file)
- `templates/extension/` — new directory with scaffolding templates (pyproject.toml, skeleton extension.py, example test)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/extension.py` (FEAT-911 completed) — `LLExtension` Protocol (`extension.py:28-49`), `ExtensionLoader` (`extension.py:70-136`), `wire_extensions()` (`extension.py:139-168`)
- `scripts/little_loops/cli/loop/run.py:156-159` — `wire_extensions(executor.event_bus, config.extensions)` call; live integration point where extensions receive events (ll-loop only; ll-auto does not wire extensions)
- `scripts/little_loops/cli/__init__.py` — re-exports all `main_*` functions; new `main_create_extension` must be added here and registered in `pyproject.toml`
- `scripts/little_loops/events.py:67-150` — `EventBus` class; `EventBus.read_events(path)` at `events.py:132-150` already reads JSONL into `list[LLEvent]` — `LLTestBus` can reuse this directly

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_extensions(event_bus, config.extensions)`; informational, no changes needed for FEAT-916 [Agent 1]
- `scripts/little_loops/cli/parallel.py` — calls `wire_extensions(event_bus, config.extensions)`; informational, no changes needed for FEAT-916 [Agent 1]
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`; informational — note: the issue text stated only `run.py` wires extensions, but `lifecycle.py` does too [Agent 1]

### Similar Patterns
- `scripts/little_loops/cli/auto.py:21-103` — `main_auto()` single-command entry point pattern; closest model for `main_create_extension` (simple argparse, no subcommands, `BRConfig(project_root)` + `configure_output(config.cli)`)
- `scripts/little_loops/cli_args.py` — shared argparse helpers (`add_dry_run_arg`, `add_config_arg`, etc.); compose from these rather than inline `add_argument` calls
- `scripts/little_loops/issue_template.py:40-114` — `parts: list[str]` + `"\n".join()` scaffolding pattern; **no Jinja2 used anywhere in codebase** — use this approach for extension templates
- `scripts/tests/test_extension.py:114-131` — `patch("little_loops.extension.entry_points")` pattern for extension-related tests
- `scripts/tests/conftest.py` — fixture conventions: `tmp_path`, `temp_project_dir`, one-line docstring on every test method

### Tests
- `scripts/tests/test_testing.py` — new test file for `LLTestBus`
- `scripts/tests/test_create_extension.py` — new test file for scaffolding command

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_extension.py:465-537` — `TestNewProtocols` class has smoke import tests for each public symbol exported from `little_loops`; add `test_smoke_import_ll_test_bus` following the existing pattern (`from little_loops import LLTestBus; assert LLTestBus is not None`) [Agent 3 — new test to write]

### Documentation
- `docs/reference/API.md` — add `LLTestBus` API docs and extension SDK section
- `CONTRIBUTING.md` — add extension development workflow

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — "CLI Tools" list (lines 104-116) does not include `ll-create-extension`; add entry [Agent 2]
- `README.md` — "13 CLI tools" count at line 90 becomes 14; add `### ll-create-extension` section to `## CLI Tools` [Agent 2]
- `docs/reference/CLI.md` — canonical CLI reference has no `### ll-create-extension` section; add before `### mcp-call` at line 1003 [Agent 2]
- `docs/ARCHITECTURE.md` — missing `create_extension.py` in `scripts/little_loops/cli/` tree (lines 177-213); missing `testing.py` in module list; missing `templates/extension/` in templates tree (lines 160-173) [Agent 2]
- `docs/reference/CONFIGURATION.md` — "Authoring an extension" block (lines 631-659) has no reference to `ll-create-extension` or `LLTestBus`; add cross-reference [Agent 2]

### Design Constraint: Event Schema Alignment with FEAT-918

`LLTestBus` records and replays events via `.events.jsonl` and must define schemas for
all 19 event types. FEAT-918 (cross-process event streaming) independently defines the
production event format for Unix sockets, HTTP webhooks, and OpenTelemetry.

**Risk**: If FEAT-916 finalizes its recorded event format before FEAT-918 is implemented,
the schemas may diverge — making `LLTestBus` replay events in a shape that differs from
what production extensions receive, rendering the test harness misleading.

**Mitigation**:
- If FEAT-918 has already landed: import its event schema definitions instead of
  defining independently. The recorded `.events.jsonl` format must be a serialization
  of the same event types used in production streaming.
- If FEAT-918 has not landed: mark the event schema in `LLTestBus` as provisional and
  add a TODO referencing FEAT-918 for reconciliation. Avoid publishing the schema as
  stable until FEAT-918 finalizes the production format.

### Configuration
- `scripts/pyproject.toml` — `[dev]` optional dependency group including test harness

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`LLEvent` is a flat dataclass** (`events.py:28-64`), NOT a typed subclass hierarchy. `type: str` carries the event name; `payload: dict[str, Any]` carries all event-specific fields untyped. Schema generation cannot introspect typed subclasses — it must enumerate known event types from `docs/reference/EVENT-SCHEMA.md` (11 event types: `loop_start`, `state_enter`, `route`, `action_start`, `action_output`, `action_complete`, `evaluate`, `retry_exhausted`, `loop_complete`, `handoff_detected`, `handoff_spawned`).
- **`EventBus.read_events(path)`** (`events.py:132-150`) already reads a JSONL file and returns `list[LLEvent]`, silently skipping malformed lines. `LLTestBus.replay()` can call this directly instead of reimplementing JSONL parsing.
- **Event wire format** (from `LLEvent.to_dict()`): `{"event": type, "ts": timestamp, ...payload}`. Real `.events.jsonl` files exist at `.loops/.running/*.events.jsonl` for manual testing.
- **`wire_extensions()` closure pattern** (`extension.py:159-163`): uses `_make_callback(e: LLExtension)` factory (inner function returning `_cb`) to avoid late-binding bug in loops — the outer loop variable is `ext`, the closure parameter is `e`. Follow this pattern in `LLTestBus.replay()` when dispatching to multiple extensions.
- **`NoopLoggerExtension`** (`extension.py:52-67`): reference extension implementation; skeleton template should follow its structure.
- **Extensions discover callers via two paths**: `ExtensionLoader.from_config()` (`extension.py:73-95`, dotted `"module:Class"` strings) and `ExtensionLoader.from_entry_points()` (`extension.py:97-118`, `importlib.metadata.entry_points(group="little_loops.extensions")`). The scaffolded extension must register in the latter group.
- **Live `.events.jsonl` files** at `.loops/.running/general-task.events.jsonl` and similar paths — usable as real fixture data for `LLTestBus` integration tests.
- **`docs/reference/EVENT-SCHEMA.md` has 19 total event types** across 5 subsystems (not 11 — that count covers only the FSM executor): 11 FSM Executor (`loop_start`, `state_enter`, `route`, `action_start`, `action_output`, `action_complete`, `evaluate`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `loop_complete`), 1 FSM Persistence (`loop_resume`), 2 StateManager (`state.issue_completed`, `state.issue_failed`), 4 Issue Lifecycle (`issue.failure_captured`, `issue.closed`, `issue.completed`, `issue.deferred`), 1 Parallel Orchestrator (`parallel.worker_completed`). Schema generation should enumerate all 19.
- **`[project.entry-points."little_loops.extensions"]` already exists** in `scripts/pyproject.toml:64` with a comment showing the registration format (`my_ext = "my_package:MyExtension"`). No new section needed — just add the `ll-create-extension` script entry to `[project.scripts]` (lines 48-62).
- **`scripts/little_loops/cli/loop/testing.py`** is NOT related to `LLTestBus` — it implements the `ll-loop test` and `ll-loop simulate` subcommands. `LLTestBus` does not exist anywhere in the codebase and must be created at `scripts/little_loops/testing.py`.
- **`cli/__init__.py` exact pattern**: import block is at lines 19-34; `__all__` list is at lines 36-53. New `main_create_extension` requires: (1) new file `scripts/little_loops/cli/create_extension.py`, (2) `from little_loops.cli.create_extension import main_create_extension` added to lines 19-34 block, (3) `"main_create_extension"` added to `__all__`.
- **`LLTestBus` interface design**: The proposed API `bus.register(MyExtension())` is NOT compatible with `EventBus.register()` — `EventBus` takes `EventCallback = Callable[[dict[str, Any]], None]`, not `LLExtension` instances. `LLTestBus` must be a **standalone class** (not an `EventBus` subclass) with its own `register(ext: LLExtension)` that stores extensions directly. `replay()` then calls `ext.on_event(event)` directly for each `LLEvent` from `EventBus.read_events()` — **the `_make_callback` closure pattern from `wire_extensions()` is NOT needed** since `LLTestBus` already works with `LLEvent` objects, not raw `dict[str, Any]`.
- **`event_filter` support in `LLTestBus.replay()`**: `wire_extensions()` passes `filter=getattr(ext, "event_filter", None)` to `EventBus.register()` (`extension.py:165`). `LLTestBus.replay()` must replicate this filtering: check `getattr(ext, "event_filter", None)` and use `fnmatch.fnmatch(event.type, pattern)` (matching `EventBus.emit()` at `events.py:113-118`) to skip events that don't match the extension's filter.
- **`[dev]` optional-dependencies correction**: Implementation Step 5 is WRONG — adding `LLTestBus` to the `[dev]` optional group is a category error. The `[dev]` group (`pyproject.toml:68-76`) holds external development tools (pytest, mypy, ruff), NOT internal modules. `LLTestBus` is part of `little_loops` itself and requires no optional install. Correct action: export `LLTestBus` from `scripts/little_loops/__init__.py` following the existing pattern (import at lines 9-13, export in `__all__` at lines 34-43).
- **`from_raw_event` vs `from_dict`**: `LLEvent.from_raw_event(raw)` (`events.py:62-64`) just copies the dict and calls `from_dict()` — it exists to avoid mutating EventBus's in-flight dict. For `LLTestBus`, `EventBus.read_events()` already returns `list[LLEvent]`, so neither method is needed in `replay()` — events are already typed.

### Refinement Pass 2 — Corrections and New Findings

_Added by `/ll:refine-issue` — verified against current codebase state:_

- **`scripts/little_loops/__init__.py` line number correction**: Import block ends at line **14** (not 13) — the extension import block is `from little_loops.extension import (` at line 9 with closing `)` at line 14. `__all__` extends to line **66** (not 43). Best insertion point for `LLTestBus`: add `from little_loops.testing import LLTestBus` after line 14; add `"LLTestBus"` to `__all__` after line 42 (within the existing `# extensions` comment block at lines 39-43).

### Refinement Pass 3 — Line Number Corrections

_Added by `/ll:refine-issue` — verified against current codebase state:_

- **`scripts/little_loops/__init__.py` import insertion point corrected**: The correct insertion point for `from little_loops.testing import LLTestBus` is **after line 31** (the closing `)` of the `work_verification` block), NOT "after line 14" from Refinement Pass 2. New imports were added since that pass (lines 15-31 now contain `git_operations`, `issue_lifecycle`, `issue_manager`, `output_parsing`, `sync`, and `work_verification`); inserting after line 14 would place `LLTestBus` mid-block between extensions and git_operations. Correct insertion: after the `)` at line 31, before the blank line at 32.
- **`__all__` insertion point corrected**: Add `"LLTestBus"` after line 43 (`"wire_extensions",`), NOT "after line 42" from Refinement Pass 2 (which would split `"NoopLoggerExtension"` from `"wire_extensions"`). The `# extensions` comment block is at lines 39-43; `LLTestBus` groups cleanly after `wire_extensions`.
- **`scripts/little_loops/cli/__init__.py` line numbers CONFIRMED accurate**: Import block at lines 19-34 (ends with `from little_loops.cli.sync import main_sync` at line 34); `__all__` at lines 36-53 (last named entry `"main_verify_docs"` at line 48, then three re-exported internal helpers). Add `from little_loops.cli.create_extension import main_create_extension` after line 34; add `"main_create_extension"` after `"main_verify_docs"` at line 48.
- **`main_create_extension` argparse scope**: Use only `add_config_arg` + `add_dry_run_arg` from `cli_args.py` — NOT `add_common_auto_args` (which bundles automation orchestration flags like `--max-issues`, `--skip`, `--only`, `--priority`, `--idle-timeout` that are irrelevant for a scaffolding command). Interface: one positional `name` arg plus `--config` and `--dry-run`.
- **`LLExtension` Protocol line correction**: `extension.py:29-49` (not 28-49 as previously stated — confirmed against current file).
- **ENH-922 is completed**: `pyproject.toml:48-62` — the `[project.scripts]` section now ends at line 62 with `mcp-call = "little_loops.mcp_call:main"` (added by recent commit). `ll-create-extension` entry goes after line 62.
- **Extension API section already exists in `docs/reference/API.md`**: ENH-922 is in `completed/` — the full extension section is at `API.md:5037-5209`, covering `LLExtension` protocol, `NoopLoggerExtension`, `ExtensionLoader`, `wire_extensions`, config key, and a "Creating a Custom Extension" example. Implementation Step 6 should extend this existing section with `LLTestBus` API docs, not create a new one. There is a `<!-- TODO: update-docs stub — FEAT-927 -->` marker at lines 5142-5144 (for error-handling and `event_filter` details in `wire_extensions` docs — adjacent to what FEAT-916 needs, but separate scope).
- **`conftest.py` `events_file` fixture** (line 285): Creates a `.events.jsonl` file with sample events for history tests. Reuse this fixture in `test_testing.py` for `LLTestBus` tests — avoids duplicating JSONL fixture setup. `many_events_file` fixture at line 297 provides 10 events for boundary testing.
- **Implementation Step 1 ambiguity resolved**: Use a **new file** `scripts/little_loops/cli/create_extension.py` (not `auto.py`) — `auto.py` is for the `ll-auto` command; mixing CLI commands in one file is not the codebase convention. Each CLI command has its own file under `scripts/little_loops/cli/`.

### Refinement Pass 4 — Corrections to Pass 3

_Added by `/ll:refine-issue` — verified against current codebase state:_

- **CLI naming correction (5 occurrences fixed)**: Issue previously used `ll create-extension` (space) in Summary, Expected Behavior, Proposed Solution, API section, and Use Case. Correct invocation is `ll-create-extension` (hyphen), consistent with all other entry points (`ll-auto`, `ll-parallel`, `ll-loop`, etc.). The Integration Map and Implementation Steps already used the correct hyphenated form.
- **`events_file` fixture in `conftest.py:284` is NOT reusable for `LLTestBus` tests**: Refinement Pass 3 recommended reusing this fixture, but it produces history/state-machine format `{"timestamp": ..., "state": ..., "action": ...}` — NOT the `LLEvent` wire format `{"event": type, "ts": ..., ...payload}`. While `EventBus.read_events()` will parse it (falling back to `type="unknown"`), the resulting events are meaningless for extension tests. `test_testing.py` needs its own fixture creating properly formatted JSONL: e.g., `{"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop_name": "test-loop"}`.
- **`event_filter` normalization (Implementation Step 3 updated)**: `LLExtension.event_filter` is typed `str | list[str] | None` (`extension.py:41`). `LLTestBus.replay()` must normalize it exactly as `EventBus.register()` does at `events.py:90-93`: wrap a bare string in a list, pass lists through as-is, `None` means no filter. Step 3 now includes the exact normalization code.
- **`EventBus.read_events()` requires `Path`, not `str`** (`events.py:132`): `LLTestBus.from_jsonl(path: str | Path)` must call `Path(path)` before passing to `read_events()`.

### Refinement Pass 6 — Post-ll-gitignore Alphabetical Ordering Correction (2026-04-04)

_Added by `/ll:refine-issue` — verified against current codebase state:_

- **`cli/__init__.py` alphabetical ordering correction (Implementation Step 1 affected)**: The `__all__` list is alphabetically sorted — confirmed by `main_gitignore` being inserted at line 40 between `main_deps` and `main_history`. Previous passes instructed inserting `"main_create_extension"` after `"main_verify_docs"` at line 48, which breaks alphabetical order. Correct `__all__` insertion: **after `"main_check_links"` at line 38** (between `main_check_links` and `main_deps`). Similarly, the import `from little_loops.cli.create_extension import main_create_extension` should be inserted **after `from little_loops.cli.auto import main_auto` at line 19** (between `auto` and `deps`), not "after line 34."
- **`pyproject.toml` `mcp-call` line re-confirmed at 62**: `ll-gitignore` was added at line 61 since Pass 5, but `mcp-call` remains at line 62. `ll-create-extension` goes after line 62 — all existing references accurate.
- **`scripts/little_loops/__init__.py` line numbers re-confirmed**: Insert `LLTestBus` import after line 31; add `"LLTestBus"` to `__all__` after `"wire_extensions"` at line 43 — both still accurate (no new imports added since Pass 5).

### Refinement Pass 5 — Inline Corrections and Verification

_Added by `/ll:refine-issue` — verified current codebase state (2026-04-03):_

- **`recorded_events` → `delivered_events` (Summary)**: Summary previously said `recorded_events`; corrected to `delivered_events` for consistency with API/Interface section and Implementation Steps. `delivered_events` is the correct attribute name since it reflects events actually delivered through the extension's `event_filter`.
- **Acceptance Criteria AC1 fixed**: `ll create-extension <name>` → `ll-create-extension <name>`. Pass 4 fixed 5 occurrences (Summary, Expected Behavior, Proposed Solution, API section, Use Case) but missed Acceptance Criteria.
- **All key line numbers re-confirmed against current file state** (no new imports added since Pass 3/4):
  - `scripts/little_loops/__init__.py`: insert `LLTestBus` import after line 31; insert `"LLTestBus"` in `__all__` after line 43 — **ACCURATE**
  - `scripts/little_loops/cli/__init__.py`: insert import after line 34; insert `"main_create_extension"` after line 48 — **ACCURATE**
  - `scripts/pyproject.toml`: `mcp-call` is still the last entry at line 62 — **ACCURATE**
  - `extension.py:29-49` (LLExtension Protocol), `events.py:90-93` (filter normalization), `events.py:132` (read_events signature `Path`) — **ACCURATE**
- **No JSON Schema tooling exists in codebase**: `jsonschema` only appears in `fsm/evaluators.py` as Claude CLI's `--json-schema` flag (structured output), not schema generation. Schema generation in Step 4 must be written from scratch using `json.dumps()` of hand-constructed dicts — one per event type, keyed off the 19 types from `docs/reference/EVENT-SCHEMA.md`.
- **`conftest.py:284` `events_file` fixture format re-confirmed**: Uses `{"timestamp": ..., "state": ..., "action": ...}` — incompatible with `LLEvent` wire format. `test_testing.py` must define its own fixture: `{"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop_name": "test-loop"}` etc.

### Refinement Pass 7 — Line Number Corrections After ll-generate-schemas (2026-04-11)

_Added by `/ll:refine-issue` — verified against current codebase state:_

- **`scripts/little_loops/cli/__init__.py` line numbers updated**: `main_auto` import is at line 20; `main_deps` import is at line 21 — insert `from little_loops.cli.create_extension import main_create_extension` **after line 20** (between `auto` and `deps`). In `__all__`, `"main_check_links"` is at line 40 and `"main_deps"` is at line 41 — insert `"main_create_extension"` **after line 40** (alphabetical: `check_links` < `create_extension` < `deps`). Previous passes (Pass 3/5) stated "after line 34" / "after line 48" which are no longer accurate after `main_generate_schemas` was added.
- **`scripts/pyproject.toml` updated**: `mcp-call` is at line **63** (not 62 as in Pass 6) — `ll-generate-schemas` was added at line 62, pushing `mcp-call` to line 63. Insert `ll-create-extension = "little_loops.cli:main_create_extension"` after line 63.
- **`scripts/little_loops/__init__.py` insertion point updated**: The `work_verification` closing `)` is now at line **35** (not 31 from Pass 3/6) — new imports (`ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension` in the extension block; `RouteContext`, `RouteDecision` from `fsm`; `parse_manage_issue_output`/`parse_ready_issue_output` from `output_parsing`) have shifted lines. Insert `from little_loops.testing import LLTestBus` **after line 35**. `"wire_extensions"` in `__all__` is now at line **50** (not 43 from Pass 3/6); add `"LLTestBus"` after line 50.

## Implementation Steps

1. Create `scripts/little_loops/cli/create_extension.py` with `main_create_extension()` (each CLI command has its own file — do not add to `auto.py`); re-export from `scripts/little_loops/cli/__init__.py` (add `from little_loops.cli.create_extension import main_create_extension` **after line 20** (`main_auto`), before line 21 (`main_deps`); add `"main_create_extension"` to `__all__` **after `"main_check_links"` at line 40**, before `"main_deps"` at line 41); register `ll-create-extension = "little_loops.cli:main_create_extension"` in `scripts/pyproject.toml` after the existing last entry `mcp-call` at line 63; use **only** `add_config_arg` + `add_dry_run_arg` from `scripts/little_loops/cli_args.py` (NOT `add_common_auto_args` — interface is: one positional `name` arg plus `--config` and `--dry-run`)
2. Create `templates/extension/` scaffolding using `parts: list[str]` + `"\n".join()` pattern (see `scripts/little_loops/issue_template.py:40-114`); **do not add Jinja2** — use string `.replace()` for `{{name}}` substitution (see `scripts/little_loops/parallel/types.py:357-385`); skeleton `extension.py` must include a comment: `# See docs/reference/EVENT-SCHEMA.md for all available event types and payload fields`
3. Implement `LLTestBus` in `scripts/little_loops/testing.py` as a standalone class (not an `EventBus` subclass): `from_jsonl(path: str | Path)` classmethod calls `Path(path)` then `EventBus.read_events(path)` (`events.py:132-150`, requires `Path` not str); store extensions in `_extensions: list[LLExtension]` via `register(ext: LLExtension)`; `replay()` filters events using `event_filter` normalization **matching `EventBus.register()` at `events.py:90-93`**: `ef = getattr(ext, "event_filter", None); patterns = ([ef] if isinstance(ef, str) else list(ef)) if ef is not None else None` — then skip event if `patterns is not None and not any(fnmatch.fnmatch(event.type, p) for p in patterns)`; call `ext.on_event(event)` directly for each passing `LLEvent`; expose `delivered_events: list[LLEvent]`. **Do NOT use the `_make_callback` closure pattern** — that is only needed when wrapping for `EventBus.register()` (raw dict layer); `LLTestBus` already has typed `LLEvent` objects
4. Export `LLTestBus` from `scripts/little_loops/__init__.py`: add `from little_loops.testing import LLTestBus` **after line 35** (end of import block, after the `work_verification` closing `)`); add `"LLTestBus"` to `__all__` **after line 50** (`"wire_extensions",`, within the `# extensions` comment block at lines 43-50). **Do NOT add to `[dev]` optional-dependencies** — `LLTestBus` is a regular module, not an external tool; the `[dev]` group (`pyproject.toml:68-76`) is for external dev tools only
5. Add `LLTestBus` API docs to the **existing** extension section in `docs/reference/API.md` at lines 5037-5209 (added by ENH-922, now completed); also document the create → develop → test → publish workflow; update `CONTRIBUTING.md` with extension development workflow

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/cli/__init__.py` module docstring (lines 3-18) — add `- ll-create-extension: Scaffold a new extension repo with entry-point, skeleton handler, and LLTestBus example` to the prose CLI tool list [Agent 2]
7. Update `.claude/CLAUDE.md` CLI Tools list (lines 104-116) — add `- \`ll-create-extension\`` entry (alphabetical order after `ll-check-links`) [Agent 2]
8. Update `README.md` — increment "13 CLI tools" to "14 CLI tools" at line 90; add `### ll-create-extension` section to the `## CLI Tools` section [Agent 2]
9. Update `docs/reference/CLI.md` — add `### ll-create-extension` section with usage/flags (`<name>`, `--dry-run`, `--config`) before `### mcp-call` at line 1003 [Agent 2]
10. Update `docs/ARCHITECTURE.md` — add `create_extension.py` to `scripts/little_loops/cli/` tree (lines 177-213); add `testing.py` to module list; add `templates/extension/` to templates tree (lines 160-173) [Agent 2]
11. Update `docs/reference/CONFIGURATION.md` — add cross-reference in "Authoring an extension" block (lines 631-659) pointing to `ll-create-extension` for scaffolding and `LLTestBus` for offline testing [Agent 2]
12. Add `test_smoke_import_ll_test_bus` to `scripts/tests/test_extension.py` `TestNewProtocols` class (lines 465-537) — `from little_loops import LLTestBus; assert LLTestBus is not None` — follows existing pattern [Agent 3]

## API/Interface

```python
# Test harness
from little_loops.testing import LLTestBus

bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
bus.register(MyExtension())
bus.replay()
assert len(bus.delivered_events) == 15
assert bus.delivered_events[0].type == "loop_start"
```

```bash
# Scaffolding
ll-create-extension my-dashboard-ext
# Creates: my-dashboard-ext/
#   pyproject.toml (with entry point)
#   my_dashboard_ext/__init__.py
#   my_dashboard_ext/extension.py (skeleton)
#   tests/test_extension.py (with LLTestBus example)
```

## Use Case

A developer wants to build a Grafana dashboard extension. They run `ll-create-extension grafana-dashboard`, get a working skeleton, write their event handler, test it against recorded events from a real loop run, and publish to PyPI.

## Acceptance Criteria

- [ ] `ll-create-extension <name>` produces a working, installable extension skeleton
- [ ] Skeleton extension passes its own generated test suite out of the box
- [ ] Skeleton `extension.py` includes a comment linking to `docs/reference/EVENT-SCHEMA.md`
- [ ] `LLTestBus` can replay `.events.jsonl` files and expose delivered events for assertions
- [ ] Documentation covers the full create → develop → test → publish workflow

## Impact

- **Priority**: P4 - Developer experience; valuable once extension ecosystem has traction
- **Effort**: Medium - Scaffolding is straightforward; test harness needs careful API design
- **Risk**: Low - Purely additive new tooling; no changes to existing code paths
- **Breaking Change**: No (new tooling only)
- **Depends On**: FEAT-911

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Extension Protocol and event type definitions |
| guidelines | CONTRIBUTING.md | Development setup patterns to model scaffolding after |

## Labels

`feat`, `extension-api`, `developer-experience`, `captured`

## Verification Notes

**Verdict**: VERIFIED — Core claims confirmed valid; stale line numbers corrected in Refinement Pass 7 (2026-04-11):

- FEAT-911 is COMPLETED — extension Protocol exists; no scaffolding tooling exists yet ✓
- No `ll-create-extension` entry point in `scripts/pyproject.toml` ✓
- No `templates/extension/` directory ✓
- No `LLTestBus` in `scripts/little_loops/testing.py` (or anywhere in `scripts/`) ✓
- All Implementation Step line numbers corrected to reflect current codebase state (see Refinement Pass 7)

— Verified 2026-04-11 | Updated 2026-04-11

---

## Blocks

- FEAT-918

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-11
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-1043: LLTestBus Test Harness
- FEAT-1044: ll-create-extension CLI and Scaffolding Templates
- FEAT-1045: Extension SDK Documentation Updates

## Status

**Decomposed** | Created: 2026-04-02 | Priority: P4

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-11T22:14:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
- `/ll:confidence-check` - 2026-04-11T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/699d3376-760c-4896-9e5a-043be16c3126.jsonl`
- `/ll:wire-issue` - 2026-04-11T21:31:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0800be1c-f6b4-497c-b5ac-2b3352749526.jsonl`
- `/ll:refine-issue` - 2026-04-11T21:21:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d9d3c2d4-5cf6-495c-8cd4-7181ace6fb24.jsonl`
- `/ll:confidence-check` - 2026-04-04T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be4f3256-56a9-4589-bcf6-68479ffab453.jsonl`
- `/ll:refine-issue` - 2026-04-04T20:51:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1a6b5c3-1492-44f3-bd9c-617b8c558a7d.jsonl`
- `/ll:verify-issues` - 2026-04-03T07:40:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T14:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:37:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T12:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:31:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T09:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:25:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:19:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T08:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c25f637-5481-4d98-bba6-846f5500e0e9.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T08:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:07:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T07:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:01:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T06:55:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T06:50:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:refine-issue` - 2026-04-03T09:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c25f637-5481-4d98-bba6-846f5500e0e9.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`
