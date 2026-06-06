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

## Motivation

The skill is a deterministic procedure hosted in an LLM interpreter (see
EPIC-1978). Porting it to Python makes it fast, cheap, unit-testable, and
free of the step-dropping failure class. Everything else in the epic depends
on this core existing.

## What to Build

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

### Dependent Files
- `templates/*.json` — now read by Python instead of prose (no content change).
- `scripts/little_loops/host_runner.py` — reuse `resolve_host()` for defaults.

## Impact

- **Priority**: P2 — blocks every other child of EPIC-1978.
- **Effort**: Medium-Large.
- **Risk**: Medium — parity must be exact; covered by byte-equivalence test.
- **Breaking Change**: No (new tool; skill untouched until ENH-1982).

## Labels

`init`, `cli`, `refactor`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
