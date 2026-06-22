---
id: ENH-2254
title: Remove or deprecate-annotate --codex flag from /ll:init docs in COMMANDS.md
type: ENH
priority: P5
status: done
completed_at: 2026-06-22 16:45:22+00:00
testable: false
confidence_score: 90
outcome_confidence: 78
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
---

## Summary

`docs/reference/COMMANDS.md` lists `--codex` in the `/ll:init` flags section alongside `--yes`, `--force`, `--dry-run`, `--hosts`. In the actual implementation (`main_init` in `scripts/little_loops/init/cli.py`), this flag is registered with `argparse.SUPPRESS` and the comment "deprecated alias for --hosts codex". `docs/reference/CLI.md` correctly omits it.

## Current Behavior

`docs/reference/COMMANDS.md` line 32 reads:

```
**Flags:** `--yes` (accepts all defaults), `--force`, `--dry-run`, `--hosts`, `--codex`
```

`--codex` appears as a first-class, undifferentiated flag with no deprecation indication.

## Expected Behavior

`--codex` is either removed from the flags list (matching `docs/reference/CLI.md`) or annotated as `--codex` *(deprecated alias for `--hosts codex`)* to set user expectations.

## Impact

Minor documentation inconsistency. Users who see `--codex` in COMMANDS.md may use it thinking it is current, when they should prefer `--hosts codex`.

## Proposed Fix

In `docs/reference/COMMANDS.md`, under `/ll:init` flags, either:
- Remove `--codex` entirely (matching CLI.md), or
- Change it to `--codex` *(deprecated alias for `--hosts codex`)* to set expectations

## Files

- `docs/reference/COMMANDS.md` — `/ll:init` flags line listing `--codex`
- `scripts/little_loops/init/cli.py` (`main_init`) — suppressed arg definition (source of truth)

## Scope Boundaries

- Only `docs/reference/COMMANDS.md` needs updating; `docs/reference/CLI.md` already omits the flag
- No changes to `scripts/little_loops/init/cli.py` — the suppressed arg is correct as-is
- No changes to the CLI behavior itself; this is documentation only

## Labels

`documentation`, `dx`

## Acceptance Criteria

- [ ] `docs/reference/COMMANDS.md` `/ll:init` flags section no longer promotes `--codex` as a first-class flag
- [ ] Consistent with `docs/reference/CLI.md` treatment

## Status

**Open** | Created: 2026-06-22 | Priority: P5

## Session Log
- `/ll:ready-issue` - 2026-06-22T16:43:59 - `c2ef19d7-8f33-4655-a7c0-c78ab6d95bf4.jsonl`
- `/ll:confidence-check` - 2026-06-22T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b08ebf-7080-42be-8691-5b5866f474c0.jsonl`
