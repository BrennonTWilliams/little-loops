---
id: ENH-2198
type: ENH
priority: P3
status: open
captured_at: 2026-06-16T18:21:36Z
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels: [hermes, cli, loop, discovery]
---

# Add `ll-loop list --visibility` inheritance-aware filter

## Summary

Add a `--visibility public|internal|example` filter to `ll-loop list` so callers
can restrict the catalog to routable (`public`) loops. Today `ll-loop list`
exposes `--json`, `--label`, and `--builtin` but has no visibility filter, so the
Hermes loop-router cannot select only dispatchable loops. The filter must be
inheritance-aware: resolve `from:` chains via `is_runnable_loop()` so non-runnable
stubs are excluded from `public`. Source: `PRD-Hermes-Integration-v4.md` (EG-2).

## Acceptance Criteria

- `ll-loop list --json --visibility public` returns only runnable, `public`-tier loops.
- `--visibility internal` and `--visibility example` filter to their respective tiers.
- `--visibility all` (or omitting the flag, per chosen default) reveals `from:` stubs.
- `from:` inheritance chains are resolved before the routability decision
  (`is_runnable_loop()`), so a stub that resolves to a runnable public loop is
  classified correctly.
- `--visibility` composes with `--label` and `--json`.

## Notes

- Wiring point: `scripts/little_loops/cli/loop/__init__.py` (`list` subparser ~line 157)
  and the list handler in `scripts/little_loops/cli/loop/`.
- Confirm the visibility tier source of truth (loop YAML field) and default
  behavior when a loop omits a visibility declaration.
