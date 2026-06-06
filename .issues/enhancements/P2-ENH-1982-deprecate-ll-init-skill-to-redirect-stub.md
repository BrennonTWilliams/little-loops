---
id: ENH-1982
title: Deprecate /ll:init skill to a redirect stub
type: enhancement
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1978
relates_to: [EPIC-1978, FEAT-1979, FEAT-1980, FEAT-1981]
labels: [init, cleanup, skill]
---

# ENH-1982: Deprecate /ll:init skill to a redirect stub

## Summary

Once `ll-init` (FEAT-1979/1980/1981) reaches parity, collapse the ~1,250-line
`/ll:init` skill into a thin redirect stub and delete the prose wizard. This
removes the parallel implementation so there is one source of truth for init.

## Motivation

EPIC-1978's whole point is that init logic should live once, in Python.
Leaving the prose skill in place would guarantee drift between it and
`ll-init`. The user's decision (2026-06-05) is to **deprecate the skill
entirely** rather than convert it to a `--plan`/`apply` wrapper — the
in-session interactive path needs a real PTY the host `!`-prefix can't reliably
provide, and first-run almost always happens in a terminal where `ll-init` runs
natively.

## What to Build

Replace `skills/init/SKILL.md` body with a short stub that, when invoked
in-session as `/ll:init`:

1. Detects whether stdin is interactive. It generally is not (the skill runs
   inside the host), so:
2. Either runs `ll-init --yes` non-interactively (sensible defaults from
   detection) **or** prints: "Guided setup moved to the `ll-init` CLI — run
   `ll-init` in your terminal for the interactive wizard, or re-run `/ll:init`
   to accept detected defaults." Decide between auto-run-`--yes` vs.
   print-and-stop during implementation; auto-run is friendlier if the produced
   config is safe to write unprompted.
3. Passes through recognized flags (`--force`, `--dry-run`, `--codex`/`--hosts`)
   to `ll-init` so existing muscle-memory invocations keep working.

Cleanup:
- Delete `skills/init/interactive.md` (925 lines).
- Reduce `skills/init/templates.md` to only what the stub still needs (or
  remove if fully owned by the Python core).
- Update the skill description/frontmatter to reflect the redirect role.

## Acceptance Criteria

- `skills/init/SKILL.md` is a short stub (target < 60 lines) with no
  duplicated procedure.
- `interactive.md` removed; `ll-verify-skills` (≤ 500 lines) trivially passes.
- `/ll:init` in-session still does something correct and non-confusing
  (either writes a default config or cleanly redirects).
- Recognized flags pass through to `ll-init`.
- README / `.claude/CLAUDE.md` / HOST_COMPATIBILITY reflect `ll-init` as the
  canonical init path.
- No remaining doc points users at the old multi-round wizard.

## Dependencies

- **Blocked by** FEAT-1979 (core) and FEAT-1980 (TUI) reaching parity — do not
  delete the prose flow until `ll-init` covers every choice it collected.
- FEAT-1981 should land first if the stub passes through `--hosts`.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — collapse to stub.
- `.claude/CLAUDE.md`, `README.md`, `docs/reference/HOST_COMPATIBILITY.md` —
  point at `ll-init`.

### Files to Delete
- `skills/init/interactive.md`.
- `skills/init/templates.md` (if fully absorbed by the Python core).

## Impact

- **Priority**: P2 — completes the epic; without it the drift risk remains.
- **Effort**: Small.
- **Risk**: Low — gated behind parity; pure deletion + redirect.
- **Breaking Change**: Soft — `/ll:init` no longer runs the in-session wizard;
  produced config is unchanged.

## Labels

`init`, `cleanup`, `skill`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
