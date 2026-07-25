---
id: FEAT-2794
type: feature
priority: P3
status: open
parent: FEAT-2763
blocked_by: FEAT-2793
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

## Acceptance Criteria

- [ ] `ll-doctor` verifies every `[project.scripts]` entry point resolves to
      an importable callable and reports any that do not.
- [ ] Reports discoverability counts and load failures for skills
      (`skills/*/SKILL.md`) and commands (`commands/*.md`) via
      `assemble_tool_catalog()`.
- [ ] Reports presence/health of `.ll/decisions.yaml` and/or
      `.ll/decisions.d/`, accepting either.
- [ ] Reports `.ll/history.db` presence and readability; absent is
      informational, not a failure.
- [ ] Reports FSM loop validity (aggregating `load_and_validate()`) without
      running any loop.
- [ ] All five checks are read-only and never mutate project state.
- [ ] Absent optional subsystems (fresh install) produce an informational
      status, not a failure.
- [ ] `--json` includes every new section.
- [ ] New tests: `scripts/tests/test_cli_doctor_install_checks.py` covering
      each check's pure helper directly; `test_tool_catalog.py`'s coverage is
      not re-derived — patch `assemble_tool_catalog()` at the `cli.doctor`
      import site instead. Same for `load_and_validate()` against
      `test_fsm_validation.py`'s coverage.
- [ ] `test_cli_doctor.py::TestMainDoctor.test_exit_zero_on_real_claude_code_report`
      still passes: since these checks run unconditionally (not gated behind
      `--full`), ensure they don't break real-filesystem CWD assumptions in
      that test — mock the new checks' filesystem probes in that test if
      needed.

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
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
