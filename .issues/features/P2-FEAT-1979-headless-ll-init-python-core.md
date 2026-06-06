---
id: FEAT-1979
title: Headless ll-init Python core
type: feature
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1978
relates_to: [EPIC-1978]
labels: [init, cli, refactor]
---

# FEAT-1979: Headless ll-init Python core

## Summary

Extract every step of the `/ll:init` procedure into a tested, headless Python
module under `scripts/little_loops/init/`. This is the foundation of EPIC-1978:
all init logic lives here once, and both the terminal TUI (FEAT-1980) and any
future skill wrapper consume it. No interactive UI in this issue — pure
functions plus non-interactive CLI entry points.

## Current Behavior

The `/ll:init` procedure runs entirely within a Claude Code skill (LLM-hosted). There is no standalone Python module for init logic, no `ll-init` CLI entry point, and no unit test coverage for the initialization steps. Init logic can only run inside a Claude Code session.

## Expected Behavior

A headless Python module at `scripts/little_loops/init/` implements all init steps as independently testable pure functions. An `ll-init` console script is registered in `pyproject.toml`, providing `--yes` (non-interactive), `--plan` (JSON contract), and `apply` (write from plan) modes. Init logic runs without an LLM and is covered by unit tests in CI.

## Use Case

**Who**: Developer onboarding a new project or configuring CI to run little-loops setup automatically.

**Context**: Project initialization in a headless environment (CI pipeline, scripted setup) where running Claude Code interactively isn't an option.

**Goal**: Run `ll-init --yes` to configure the project non-interactively, or `ll-init --plan` to inspect what would be configured before committing writes.

**Outcome**: A fully configured `.ll/ll-config.json` is produced — byte-equivalent to what `/ll:init --yes` would create — with the init logic unit-tested and verifiable in CI without an LLM.

## Motivation

The skill is a deterministic procedure hosted in an LLM interpreter (see
EPIC-1978). Porting it to Python makes it fast, cheap, unit-testable, and
free of the step-dropping failure class. Everything else in the epic depends
on this core existing.

## Proposed Solution

Functions (mirroring the skill's steps), each independently testable:

- `detect_project_type(root) -> TemplateMatch` — port Step 3: read
  `templates/*.json`, match `_meta.detect` globs against the project root,
  apply `_meta.detect_exclude`, prefer non-`priority: -1` on multi-match,
  fall back to `generic.json`.
- `build_config(template, choices) -> dict` — port Step 4: load template JSON,
  strip `_meta`/`$schema`, apply section presets and per-section omit rules.
- `validate_deps() -> list[Warning]` — port Steps 7.5 + 9.5: `which` on
  configured tool commands, `jq`/`python3`/`pyyaml` presence, and
  `little-loops` pip version vs the plugin version (non-blocking warnings).
- `write_config()`, `update_gitignore()`, `merge_settings()`,
  `update_claude_md()`, `deploy_goals()`, `deploy_design_tokens()`,
  `make_issue_dirs()`, `make_learning_tests_dir()` — port Steps 8–11
  (idempotent file ops).
- `install_codex_adapter()` — port Step 8.5 (template substitution → writes;
  the Codex install path EPIC-1463 cares about). Host dispatch generalized in
  FEAT-1981.

Entry points (non-interactive only here):

- `ll-init --yes [--force] [--dry-run]` — full non-interactive run.
- `ll-init --plan` — emit JSON `{detected, proposed_config, host_options,
  warnings}` (the contract a future skill wrapper could consume).
- `ll-init apply --config <json>` — perform writes from a plan.

## Acceptance Criteria

- New `ll-init` console script registered in `scripts/pyproject.toml`.
- `ll-init --yes` produces a **byte-equivalent** `.ll/ll-config.json` to
  `/ll:init --yes` for all 9 project-type templates (parity test).
- `--dry-run` matches the skill's dry-run preview actions.
- All file mutations are idempotent (re-running changes nothing).
- Unit tests cover detection (per template + multi-match + fallback), config
  generation (omit rules), dependency validation (each warning path), and each
  file writer.
- `python -m mypy scripts/little_loops/init/` and `ruff check` clean.

## Integration Map

### Files to Create
- `scripts/little_loops/init/__init__.py`, `core.py`, `detect.py`,
  `writers.py`, `validate.py`, `cli.py`.
- `scripts/tests/test_init_core.py`.

### Files to Modify
- `scripts/pyproject.toml` — `[project.scripts] ll-init = ...`.

### Dependent Files (Callers/Importers)
- `templates/*.json` — now read by Python instead of prose (no content change).
- `scripts/little_loops/host_runner.py` — reuse `resolve_host()` for defaults.

### Similar Patterns
- `scripts/little_loops/host_runner.py` — `resolve_host()` idiomatic CLI dispatch pattern to follow.
- `scripts/little_loops/session_log.py` — idempotent file-write pattern.

### Tests
- `scripts/tests/test_init_core.py` — new (listed under Files to Create).

### Documentation
- N/A — no existing docs reference `ll-init`.

### Configuration
- `scripts/pyproject.toml` — listed under Files to Modify.

## Implementation Steps

1. Create `scripts/little_loops/init/` package skeleton (`__init__.py`, `detect.py`, `core.py`, `writers.py`, `validate.py`, `cli.py`)
2. Port project-type detection from skill Step 3 into `detect.py` (`detect_project_type`)
3. Port config building and file writers from skill Steps 4 + 8–11 into `core.py` + `writers.py`
4. Port dependency validation from Steps 7.5 + 9.5 into `validate.py`
5. Implement `cli.py` with `ll-init --yes`, `--plan`, and `apply` entry points
6. Write unit tests in `scripts/tests/test_init_core.py` covering detection, config generation, validation, and each writer
7. Add byte-equivalence parity test against `/ll:init --yes` output for all 9 project templates

## Impact

- **Priority**: P2 — blocks every other child of EPIC-1978.
- **Effort**: Medium-Large.
- **Risk**: Medium — parity must be exact; covered by byte-equivalence test.
- **Breaking Change**: No (new tool; skill untouched until ENH-1982).

## Labels

`init`, `cli`, `refactor`

## Status

**Open** | Created: 2026-06-05 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-06-06T20:37:51 - `b4ac5d16-b4a5-41a6-9803-9cd80b05ce08.jsonl`
