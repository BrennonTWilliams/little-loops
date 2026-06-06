---
id: FEAT-1980
title: ll-init interactive terminal TUI
type: feature
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1978
relates_to: [EPIC-1978, FEAT-1979]
labels: [init, cli, tui, dx]
---

# FEAT-1980: ll-init interactive terminal TUI

## Summary

Build the interactive terminal frontend for `ll-init` over the headless core
(FEAT-1979). Replaces the LLM-interpreted 12-round wizard
(`skills/init/interactive.md`) with a fast native TUI — multi-select for
feature toggles, single-select where appropriate, a confirmation summary, and a
completion message. This is the "quick and easy" first-run surface EPIC-1978
targets.

## Motivation

The 12-round prose wizard is the specific thing first-time users find
off-putting: each round is an LLM round-trip interpreting English instructions.
A `questionary`/`rich` TUI collapses the same choices into a couple of fast,
keyboard-driven screens with no token cost and no dropped steps.

## What to Build

- Depends on FEAT-1979 (calls `build_config` / writers; does not duplicate
  logic).
- TUI library: `questionary` (multi-select, confirm) + `rich` (summary panel /
  progress). Add to `scripts/pyproject.toml` deps.
- Collapse the wizard rounds into grouped screens:
  - **Project basics** — name, source dir, test/lint/type/format commands
    (pre-filled from detected template; user edits inline).
  - **Features** — single multi-select checklist replacing Rounds 3a/4/6/7/8/9
    (parallel processing, product analysis, document tracking, design tokens,
    learning tests, analytics). Conditional follow-ups (e.g. worktree count
    when parallel is checked) shown only when relevant.
  - **Settings target** — settings.local.json vs settings.json; CLAUDE.md
    opt-in.
- Render the bordered configuration summary (port `templates.md`), confirm,
  then call the FEAT-1979 writers.
- Host selection is **not** built here — it is FEAT-1981 (this issue assumes a
  resolved host list and renders feature choices for it).
- Graceful non-TTY fallback: if stdin is not a TTY, error with a hint to use
  `ll-init --yes` (no half-interactive hangs).

## Acceptance Criteria

- `ll-init` with no flags launches the TUI and writes a config matching what
  the equivalent answers would produce via `--yes`/`--plan`.
- All feature toggles from the existing wizard are reachable; nothing the
  prose wizard collected is lost (parity checklist).
- Conditional questions (parallel workers, etc.) appear only when their gate is
  selected.
- Non-TTY invocation exits cleanly with the `--yes` hint.
- Summary + completion output match the skill's templates.

## Integration Map

### Files to Create
- `scripts/little_loops/init/tui.py`.
- `scripts/tests/test_init_tui.py` (drive via questionary's test/prompt
  injection or a thin input-abstraction seam).

### Files to Modify
- `scripts/pyproject.toml` — add `questionary`, `rich` deps; wire TUI as the
  default `ll-init` (no-flag) path.

### Dependent Files
- `scripts/little_loops/init/core.py` (FEAT-1979) — consumed, not modified.

## Impact

- **Priority**: P2 — this is the user-visible DX win of the epic.
- **Effort**: Medium.
- **Risk**: Low-Medium — TUI testing needs an input seam; mitigated by the
  headless core doing all real work.
- **Breaking Change**: No.

## Labels

`init`, `cli`, `tui`, `dx`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
