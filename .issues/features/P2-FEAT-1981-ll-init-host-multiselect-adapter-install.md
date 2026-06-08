---
id: FEAT-1981
title: ll-init host multi-select and adapter install dispatch
type: feature
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1978
relates_to:
- EPIC-1978
- EPIC-1463
- EPIC-1622
- FEAT-1475
labels:
- init
- cli
- host-compat
confidence_score: 86
outcome_confidence: 78
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 22
---

# FEAT-1981: ll-init host multi-select and adapter install dispatch

## Summary

Add host-harness selection (Claude Code / Codex / Pi) to `ll-init` as a
first-class multi-select step, and dispatch each selected host to its adapter
install. This is the shared seam EPIC-1978 identified between the Codex
(EPIC-1463) and Pi (EPIC-1622) tracks — host choice has install-time
consequences (which adapter files to write), so it belongs in one place.

## Current Behavior

`ll-init` (via `cli.py`) auto-detects Codex via `which codex` / `.codex/` and
installs the Codex adapter silently. There is no Pi adapter path and no explicit
user-facing host selection — host wiring is opaque and not overridable.

## Expected Behavior

`ll-init` presents a host multi-select (TUI) or accepts `--hosts
claude-code,codex,pi` (headless). Detection-seeded defaults are shown but
overridable. Each selected host's adapter is installed; Pi surfaces a graceful
"not yet available" message until its adapter lands.

## Use Case

A developer sets up little-loops on a machine that runs both Claude Code and
Codex. They run `ll-init` and see a multi-select pre-checked with both detected
hosts. They confirm, and `ll-init` installs both adapters in one pass with
per-host post-install notes. On a CI machine with `--yes`, they pass `--hosts
codex` and get a deterministic headless install.

## Motivation

Today `/ll:init` only conditionally installs the Codex adapter (Step 8.5),
auto-detected via `which codex` / `.codex/`. There is no Pi path and no
explicit user-facing host choice. As Codex and Pi adapters mature, the user
should pick which harness(es) to wire in one multi-select, and `ll-init` should
install exactly those adapters.

## What to Build

- Host multi-select in the TUI (FEAT-1980) and a `--hosts claude-code,codex,pi`
  flag for `ll-init --yes`.
- Default selection seeded from detection: `resolve_host()` /
  `which codex` / `which pi` / existing `.codex`/`.pi` dirs (preserve current
  auto-detect behavior as the default, now overridable).
- Dispatch table in the FEAT-1979 core: each selected host → its adapter
  installer:
  - **claude-code** — no adapter file needed (plugin hooks fire when globally
    enabled); just the standard config.
  - **codex** — `install_codex_adapter()` (port of Step 8.5; the EPIC-1463
    install path).
  - **pi** — install the Pi adapter once it exists (FEAT-1475 / EPIC-1622);
    until then, surface a clear "Pi adapter not yet available" message rather
    than failing.
- Honor `--dry-run` / `--force` / existing-file skip per host.
- Print each host's post-install note (e.g. the FEAT-957 Codex trust-dialog
  warning).

## Acceptance Criteria

- `ll-init --hosts codex` installs `.codex/hooks.json` identically to today's
  `/ll:init --codex`.
- `ll-init` (TUI) shows a host multi-select with detection-seeded defaults.
- Selecting Pi before its adapter exists yields a graceful "not yet available"
  message, not a traceback.
- Host selection composes with `--dry-run` (preview lists per-host actions)
  and `--force`.
- Unit tests cover the dispatch table per host and the detection-default
  seeding.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — replace `--codex` bool flag with `--hosts` list arg; replace `if codex: install_codex_adapter()` dispatch block with per-host dispatch table; update `_print_dry_run` and `_build_init_info` host detection logic.
- `scripts/little_loops/init/core.py` (FEAT-1979) — host dispatch table.
- `scripts/little_loops/init/tui.py` (FEAT-1980) — host multi-select screen.
- `scripts/little_loops/host_runner.py` — reuse `resolve_host()` for defaults.

### Dependent Files
- `hooks/adapters/codex/hooks.json` — install source (Codex).
- `hooks/adapters/pi/` — install source once FEAT-1475/EPIC-1622 lands.
- `docs/reference/HOST_COMPATIBILITY.md` — note `ll-init --hosts` as the
  install path; flips Codex/Pi init cells.

## Impact

- **Priority**: P2 — unblocks clean Codex/Pi install UX; the shared seam for
  EPIC-1463 / EPIC-1622.
- **Effort**: Small-Medium (Codex path is a port; Pi path is a stub until its
  adapter exists).
- **Risk**: Low — additive; default behavior matches today's auto-detect.
- **Breaking Change**: No.

## Dependencies

- Codex install: ready (port of existing Step 8.5).
- Pi install: gated on FEAT-1475 / EPIC-1622 (Pi adapter must exist). Ship the
  dispatch + graceful-unavailable message now; wire the real Pi install when
  the adapter lands.

## Labels

`init`, `cli`, `host-compat`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-08_

**Readiness Score**: 86/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- `cli.py` is missing from "Files to Modify" but is the primary implementation site: it holds the `--hosts` argparse flag, the existing `codex: bool` parameter to replace/alias, and the `if codex: install_codex_adapter()` dispatch block (lines 86–93) that this feature generalizes into a host dispatch table.

## Session Log
- `/ll:ready-issue` - 2026-06-08T16:11:45 - `708619f8-a0aa-4b4a-aeb3-262397c809bd.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df2f8f5e-bc85-4400-9a3a-fc89cc3407c8.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
