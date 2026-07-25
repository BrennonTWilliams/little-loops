---
id: FEAT-2794
type: feature
priority: P3
status: done
completed_at: '2026-07-25T14:38:19Z'
parent: EPIC-2765
blocked_by: FEAT-2793
relates_to:
- FEAT-2763
confidence_score: 100
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
---

# FEAT-2794: Add ll-doctor fast default install-surface checks

## Summary

Implement the sub-second, default-run install-surface checks: entry-point
resolution, skill/command discoverability, decisions-store health, history DB
readability, and FSM loop validity. Register each against the check-registry
protocol introduced in FEAT-2793.

## Parent Issue

Decomposed from FEAT-2763: Expand ll-doctor to validate little-loops' own
install surface. This child covers Implementation Step 3 and the relevant
slice of `--json` wiring (Acceptance Criteria for entry points, skills/
commands, decisions, history DB, and loop validity).

## Proposed Solution

Add one `_<name>_section_data()`/`_print_<name>_section()` pair per check,
following `doctor.py`'s existing pattern, each registered against the
FEAT-2793 registry:

- **Entry points**: parse `[project.scripts]` from `scripts/pyproject.toml`
  with `tomllib`, `importlib.import_module()` + `getattr()` per pair,
  distinguishing "module not found" from "function renamed/removed" (mirrors
  `extension.py`'s `from_config()` try/except-per-item shape).
- **Skills/commands**: reuse `assemble_tool_catalog()`
  (`scripts/little_loops/tool_catalog.py`) rather than a fresh glob.
- **Decisions store**: reuse `verify_decisions.py:_run()`'s two-pass idiom
  (`load_decisions()` for the flat file, then a direct re-glob of
  `.ll/decisions.d/*.json` via `_entry_from_dict()`) to surface fragment
  corruption `load_decisions()` alone would swallow (BUG-2644).
- **History DB**: probe `session_store.py`'s `DEFAULT_DB_PATH` / `connect()` /
  `ensure_db()`; absence is informational, not a failure.
- **Loop validity**: call `load_and_validate(path, raise_on_error=False)`
  (`fsm/validation.py:3022-3047`) per loop, checking for
  `ValidationSeverity.ERROR`, per `cli/loop/config_cmds.py:12-69`'s idiom —
  aggregate results, never execute a loop.

All checks are read-only, degrade gracefully when their subject is absent, and
each new section appears in both text and `--json` output.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Check-registry protocol (FEAT-2793, already merged)** — `doctor.py:28`
  `CheckResult` (frozen dataclass: `name`, `status: Literal["full","partial",
  "unsupported"]`, `note`, `severity: Literal["error","informational"] =
  "error"`); `doctor.py:50` `_CHECKS: list[Callable[[], list[CheckResult]]]`;
  `doctor.py:53` `register_check(fn)` decorator appends to `_CHECKS` and
  returns `fn` unchanged (so it's also directly callable in tests);
  `doctor.py:67` `_run_registered_checks()` flattens all registered checks'
  results; `doctor.py:75` `_exit_code_for(results)` returns `1` iff any
  result has `severity == "error"` and `status == "unsupported"` — this is
  exactly the mechanism the "absent optional subsystem → informational, not
  failure" AC needs (set `severity="informational"` on that `CheckResult`).
  `doctor.py:48-49` has a comment explicitly earmarking `_CHECKS` as where
  "New install-surface checks (FEAT-2794, FEAT-2795) register." **Gap**:
  `_run_registered_checks()`'s results currently only feed the exit code —
  there is no existing print/JSON hook wired for registered checks (unlike
  the hand-written `capture`/`issues` sections below), so each new check
  needs its own `_print_<name>_section()` call site added in `main_doctor()`
  and its `_data()` dict added to `_print_report()`'s JSON payload.
- **`_<name>_section_data()`/`_print_<name>_section()` template** —
  `doctor.py:81` `_capture_section_data()` / `doctor.py:100`
  `_print_capture_section()`, and `doctor.py:92` `_issues_section_data()` /
  `doctor.py:123` `_print_issues_section()`. Each `_data()` fn returns a
  plain dict via `getattr(cfg, field, default)` (tolerates a missing/partial
  config object) and is the single source of truth reused by both the JSON
  branch (`_print_report()`, embeds e.g. `"issues"` key) and the text
  printer, which formats with `_STATUS_SYMBOLS` glyphs (✓/○/✗). Both are
  wired in `main_doctor()`, text-print calls gated on `not args.json`.
- **Entry points**: `scripts/pyproject.toml:77` defines
  `ll-doctor = "little_loops.cli:main_doctor"` as one `[project.scripts]`
  row. Existing `tomllib` prior art:
  `scripts/little_loops/cli/verify_cli_allowlist.py:39`
  `_all_ll_entry_points()` opens the file in `"rb"` mode and reads
  `data["project"]["scripts"]` — but it only returns entry-point *names*
  (`.keys()`-derived), not the `module:function` target strings. FEAT-2794's
  check needs the full dict (`name -> "module.path:func"`) to actually
  import each target, so this function isn't directly reusable as-is (need
  the dict form, not the name-only set).
  For distinguishing "module not found" vs "function renamed/removed":
  `scripts/little_loops/extension.py:136` `ExtensionLoader.from_config()` is
  the only existing `importlib.import_module()` + `getattr()` call site, but
  it uses a single broad `except Exception` (logs and skips) — it does
  **not** separately branch on `ModuleNotFoundError` vs `AttributeError`.
  The new check is the first to need that split (two `except` clauses, one
  per failure mode, each producing a distinct `CheckResult.note`).
- **Skills/commands**: `scripts/little_loops/tool_catalog.py:145`
  `assemble_tool_catalog(project_root: Path) -> list[ToolDefinition]` walks
  `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md` via internal
  `_skill_entries()`/`_command_entries()`/`_agent_entries()` helpers.
  Missing directories yield no entries and never raise (`Path.glob()` on a
  nonexistent dir is empty, and `_read_text_or_empty()` swallows `OSError`)
  — matches the "degrade gracefully" requirement with no extra handling
  needed. `ToolDefinition` fields: `name`, `description`, `input_schema`,
  `cache_control`.
- **Decisions store**: `scripts/little_loops/cli/verify_decisions.py:50`
  `_run(log_path)` is the two-pass idiom to mirror: pass 1 calls
  `load_decisions(log_path)` (from `little_loops.decisions`) inside
  `try/except (yaml.YAMLError, KeyError, ValueError)`; pass 2 re-globs
  `.ll/decisions.d/*.json` directly (bypassing `load_decisions()`'s own
  silent-skip fragment loader) and for each fragment calls
  `json.loads(...)` then `_entry_from_dict(data)` (also from
  `little_loops.decisions`) inside a broader
  `except (json.JSONDecodeError, KeyError, ValueError, TypeError,
  AttributeError)`. `_run()` returns `(exit_code, message)`; the new
  doctor check needs the same two-pass logic but returning `CheckResult`
  objects instead.
- **History DB**: `scripts/little_loops/session_store.py:121`
  `DEFAULT_DB_PATH = Path(".ll/history.db")`; `:1323` `ensure_db(path)` and
  `:1364` `connect(path)`. **Important gap**: neither function is read-only
  w.r.t. absence — `ensure_db()` creates the parent dir and a fresh DB file
  if none exists (idempotent by design, not an error path), and `connect()`
  calls `ensure_db()` first. So calling either against a genuinely absent
  `.ll/history.db` will silently *create* one rather than reporting
  "absent." The check must test `path.exists()` **before** calling
  `connect()`/`ensure_db()` to distinguish "absent" (informational) from
  "present but unreadable" (error) — do not call `connect()`/`ensure_db()`
  as the sole probe, or the check will violate the "read-only, never
  mutate project state" AC.
- **Loop validity**: `scripts/little_loops/fsm/validation.py:3022`
  `load_and_validate(path, raise_on_error=False)` — with
  `raise_on_error=False` it never raises on validation content, returning
  `(FSMLoop, all_violations_sorted_errors_first)`; still raises
  `FileNotFoundError`/`ValueError` for a missing file or non-mapping YAML.
  `ValidationSeverity` enum (`:40`): `ERROR`, `WARNING`. Reference idiom:
  `scripts/little_loops/cli/loop/config_cmds.py:12-69` `cmd_validate()`, but
  note it validates a **single** loop file per call (`resolve_loop_path()` →
  one path) — there is no existing multi-file aggregator anywhere in the
  codebase. The new check must introduce its own glob over loop YAML files
  and call `load_and_validate(path, raise_on_error=False)` per file,
  aggregating `any(v.severity == ValidationSeverity.ERROR for v in
  violations)` per loop into the overall `CheckResult`.
- **Test precedent**: `scripts/tests/test_cli_doctor.py`'s
  `TestCheckRegistry` class has
  `test_register_check_appends_and_runs()` (save/restore `_CHECKS` in
  `try/finally`) and
  `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor()`
  (registers both an `"informational"` and an `"error"` unsupported check,
  patches `resolve_host`/`BRConfig`/`print`, asserts exit code reflects only
  the error-severity one) — this is the template to copy per new check. No
  filesystem-mocking precedent exists yet in this file (all current checks
  are host-capability/config-object based); use `tmp_path`/`monkeypatch`
  fixtures for the filesystem-touching checks (history DB, decisions store,
  loop glob) instead.

## Acceptance Criteria

- [x] `ll-doctor` verifies every `[project.scripts]` entry point resolves to
      an importable callable and reports any that do not.
- [x] Reports discoverability counts and load failures for skills
      (`skills/*/SKILL.md`) and commands (`commands/*.md`) via
      `assemble_tool_catalog()`.
- [x] Reports presence/health of `.ll/decisions.yaml` and/or
      `.ll/decisions.d/`, accepting either.
- [x] Reports `.ll/history.db` presence and readability; absent is
      informational, not a failure.
- [x] Reports FSM loop validity (aggregating `load_and_validate()`) without
      running any loop.
- [x] All five checks are read-only and never mutate project state.
- [x] Absent optional subsystems (fresh install) produce an informational
      status, not a failure.
- [x] `--json` includes every new section.
- [x] New tests: `scripts/tests/test_cli_doctor_install_checks.py` covering
      each check's pure helper directly; `test_tool_catalog.py`'s coverage is
      not re-derived — patch `assemble_tool_catalog()` at the `cli.doctor`
      import site instead. Same for `load_and_validate()` against
      `test_fsm_validation.py`'s coverage.
- [x] `test_cli_doctor.py::TestMainDoctor.test_exit_zero_on_real_claude_code_report`
      still passes: since these checks run unconditionally (not gated behind
      `--full`), ensure they don't break real-filesystem CWD assumptions in
      that test — mock the new checks' filesystem probes in that test if
      needed.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — add 5 `@register_check`-decorated
  functions plus their `_<name>_section_data()`/`_print_<name>_section()`
  pairs, following `_capture_section_data()`/`_print_capture_section()`
  (line 81/100) and `_issues_section_data()`/`_print_issues_section()`
  (line 92/123); wire each new print call into `main_doctor()` and each new
  `_data()` dict into `_print_report()`'s JSON payload

### Dependent Files (reused, not modified)
- `scripts/little_loops/tool_catalog.py:145` — `assemble_tool_catalog()`,
  called (not modified) by the skills/commands check
- `scripts/little_loops/decisions.py:346,354` — `_entry_from_dict()`,
  `load_decisions()`, called by the decisions-store check
- `scripts/little_loops/session_store.py:121,1323,1364` —
  `DEFAULT_DB_PATH`, `ensure_db()`, `connect()`; the check must guard with
  `path.exists()` before calling either (see Codebase Research Findings —
  both functions create-on-demand, not read-only)
- `scripts/little_loops/fsm/validation.py:3022` — `load_and_validate()`,
  called per loop file with `raise_on_error=False`
- `scripts/pyproject.toml:77` — read for `[project.scripts]` entries

### Similar Patterns
- `scripts/little_loops/cli/verify_cli_allowlist.py:39`
  `_all_ll_entry_points()` — tomllib parse precedent (names-only; entry
  check needs the full `name -> target` dict)
- `scripts/little_loops/cli/verify_decisions.py:50` `_run()` — two-pass
  decisions validation idiom to mirror
- `scripts/little_loops/cli/loop/config_cmds.py:12-69` `cmd_validate()` —
  single-file `load_and_validate()` call pattern (no existing multi-file
  aggregator to reuse verbatim)
- `scripts/little_loops/extension.py:136` `ExtensionLoader.from_config()` —
  closest import+getattr precedent, but needs splitting into
  `ModuleNotFoundError`/`AttributeError` branches for this check

### Tests
- `scripts/tests/test_cli_doctor.py`'s `TestCheckRegistry` —
  `test_register_check_appends_and_runs()` and
  `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor()`
  are the templates to copy per new check
- `scripts/tests/test_tool_catalog.py`, `test_fsm_validation.py` — do not
  re-derive; patch `assemble_tool_catalog()`/`load_and_validate()` at the
  `cli.doctor` import site instead (per AC)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor.py` — beyond the AC-named
  `test_exit_zero_on_real_claude_code_report`, every other `TestMainDoctor`
  test that patches `little_loops.config.BRConfig` as a bare `MagicMock()`
  with no `_CHECKS` stubbing (`test_exit_zero_when_all_capabilities_supported`,
  `test_exit_one_when_critical_capability_missing`,
  `test_partial_capability_does_not_trigger_exit_one`,
  `test_empty_capabilities_returns_zero`, `test_text_output_shows_host_info`,
  `test_status_symbols_in_text_output`) calls `main_doctor()` without clearing
  `_CHECKS`, so the 5 new unconditional checks run for real against pytest's
  cwd in each of them too — not just the one test the issue's AC #9 already
  names. Each must either get the new checks' filesystem probes mocked, or
  follow `TestCheckRegistry`'s `doctor._CHECKS.clear()` / `.extend(original)`
  try/finally idiom to isolate them from the new registered checks. [Agent 1
  + Agent 3 finding]
- `scripts/tests/test_verify_decisions.py` — `_make_project()`/`_write_yaml()`
  tmp_path fixture helpers and its three-tier corruption test shape
  (yaml-error / key-error / value-error, each mirrored by a CLI exit-code
  assertion) are the direct precedent to reuse for the decisions-store
  check's tests, closer than the generic `TestCheckRegistry` template. [Agent
  3 finding]
- `scripts/tests/test_session_store.py` — `test_graceful_when_store_unwritable`
  (locked/corrupt DB via `monkeypatch.setattr(session_store, "connect", boom)`)
  and `test_missing_meta_table_still_reads_as_version_zero` (real empty
  sqlite file in `tmp_path`) are the direct precedent for the history-DB
  check's "present but unreadable" vs "present but empty" test cases. [Agent
  3 finding]
- `scripts/little_loops/init/install_check.py` — `detect_installation()` /
  `_is_editable_install()` is the closest existing entry-point/install
  resolution logic (uses `importlib.metadata.version()` /
  `PackageNotFoundError` in narrow except clauses), though no dedicated test
  file exists for it yet — not directly reusable but informs the
  ModuleNotFoundError/AttributeError split style. [Agent 3 finding]

Confirmed out of scope for this issue (do not touch — owned by FEAT-2796 per
its own Execution Pattern, which runs strictly after FEAT-2794 and FEAT-2795):
`docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md`,
`commands/help.md`, `.claude/CLAUDE.md`, `docs/reference/API.md`,
`docs/ARCHITECTURE.md`, `docs/codex/usage.md`, `docs/codex/README.md`,
`CONTRIBUTING.md`. The doc-wiring guard tests (`test_wiring_guides_and_meta.py`,
`test_wiring_init_and_configure.py`, `test_wiring_cli_registry.py`) only assert
the literal substring `"ll-doctor"` is present in those files and are
unaffected by this issue's changes. [Agent 1 + Agent 2 finding]

## Files

- `scripts/little_loops/cli/doctor.py` — new sections, registered against the
  FEAT-2793 registry
- `scripts/pyproject.toml` — source of truth for entry points to verify
  (read-only)
- `scripts/tests/test_cli_doctor_install_checks.py` (new)
- `scripts/tests/test_cli_doctor.py` — cwd-independence guard for the
  real-report test

## Execution Pattern

Depends on FEAT-2793 (registry must exist first). Can run in parallel with
FEAT-2795 (`--full` aggregation) — different checks, same file, low conflict
risk since each adds an independent section.

## Session Log
- `/ll:manage-issue` (implement) - 2026-07-25T14:37:37Z - `5f3b4d7a-9285-4bf6-b6dc-09a0b8e2cad2.jsonl`
- `/ll:ready-issue` - 2026-07-25T14:25:27 - `748cc41e-f049-4964-81ac-a182565d38b1.jsonl`
- `/ll:wire-issue` - 2026-07-25T14:22:59 - `7a0c481b-d997-4797-9579-71f13cabca1c.jsonl`
- `/ll:refine-issue` - 2026-07-25T14:15:24 - `3de55810-4f7b-4f6f-a67b-e7b2a7bfa386.jsonl`
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
