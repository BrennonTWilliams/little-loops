---
id: ENH-2254
title: Remove or deprecate-annotate --codex flag from /ll:init docs in COMMANDS.md
type: ENH
priority: P5
status: open
---

## Summary

`docs/reference/COMMANDS.md` lists `--codex` in the `/ll:init` flags section alongside `--yes`, `--force`, `--dry-run`, `--hosts`. In the actual implementation (`scripts/little_loops/init/cli.py:477`), this flag is registered with `argparse.SUPPRESS` and the comment "deprecated alias for --hosts codex". `docs/reference/CLI.md` correctly omits it.

## Impact

Minor documentation inconsistency. Users who see `--codex` in COMMANDS.md may use it thinking it is current, when they should prefer `--hosts codex`.

## Proposed Fix

In `docs/reference/COMMANDS.md`, under `/ll:init` flags, either:
- Remove `--codex` entirely (matching CLI.md), or
- Change it to `--codex` *(deprecated alias for `--hosts codex`)* to set expectations

## Files

- `docs/reference/COMMANDS.md` — `/ll:init` flags line listing `--codex`
- `scripts/little_loops/init/cli.py:477` — suppressed arg definition (source of truth)

## Acceptance Criteria

- [ ] `docs/reference/COMMANDS.md` `/ll:init` flags section no longer promotes `--codex` as a first-class flag
- [ ] Consistent with `docs/reference/CLI.md` treatment
