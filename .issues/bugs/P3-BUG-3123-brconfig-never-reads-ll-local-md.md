---
id: BUG-3123
title: BRConfig never reads .ll/ll.local.md overrides
type: BUG
priority: P3
status: open
captured_at: '2026-08-08T21:48:47Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- config
relates_to: [ENH-3113]
---

# BUG-3123: BRConfig never reads `.ll/ll.local.md` overrides

## Summary

`.ll/ll.local.md` overrides (e.g. `project.test_cmd`, `scan.focus_dirs`) are
only ever merged inside the SessionStart hook process. `BRConfig`, which every
`ll-*` CLI command constructs directly, never reads the file — so an override
declared in `ll.local.md` silently does not apply to actual command execution,
in the main tree as well as in a worktree.

## Current Behavior

`SessionStart` (`scripts/little_loops/hooks/session_start.py:136-147`) is the
only code that parses `.ll/ll.local.md`'s YAML frontmatter and merges it via
`deep_merge()` (`config/core.py:57-84`) on top of the base config. That merged
result (`merged_config`) is used only for two things inside that single hook
invocation: the hook's own internal `HistoryConfig`/feature-validation logic,
and the JSON printed to session-start stdout for host-CLI context display
(`session_start.py:239-246`). It is never written back to disk and never read
by anything else.

`BRConfig._load_config()` (`scripts/little_loops/config/core.py:229-240`)
loads only `resolve_config_path()`'s result (`.ll/ll-config.json` or a
root-level `ll-config.json`) — it has no knowledge of `.ll/ll.local.md` at
all. Every `ll-*` CLI entry point that constructs a `BRConfig` therefore reads
the un-overridden base config, regardless of what `ll.local.md` declares.

## Expected Behavior

An override declared in `.ll/ll.local.md` (e.g. `project.test_cmd`) is
honored by any code path that resolves config through `BRConfig`, not just by
the SessionStart hook's own internal logic and printed context.

## Motivation

`.ll/ll.local.md` exists specifically to hold per-machine settings that
shouldn't be committed (see `.claude/CLAUDE.md` § Local Settings Override,
which documents overriding `project.test_cmd` as the canonical example). If
`BRConfig` never actually applies that override, the documented feature is
silently a no-op for anything except the SessionStart hook's own narrow
internal use — a project can set `test_cmd` in `ll.local.md` and have every
`ll-*` command keep using the base value with no error or warning.

Discovered while running `/ll:confidence-check` on ENH-3113 (worktree
`ll.local.md` copy mechanics), which deliberately scopes this out —
EPIC-3111's stated scope is worktree copy semantics only, not `BRConfig`'s
override-resolution mechanism, so this is filed separately rather than folded
into that issue.

## Root Cause

`BRConfig._load_config()` (`scripts/little_loops/config/core.py:229-240`) was
never extended to read `.ll/ll.local.md`; only `hooks/session_start.py` was
given that logic, and its merge result is process-local (printed/consumed
in-hook, never persisted).

## Proposed Solution

Give `BRConfig._load_config()` a read path for `.ll/ll.local.md`, reusing the
existing `_parse_frontmatter()` (`session_start.py`) and `deep_merge()`
(`config/core.py:57-84`) helpers rather than duplicating the parsing logic.
Candidate approaches to weigh during implementation:

1. Extract `_parse_frontmatter()` out of `hooks/session_start.py` into
   `config/core.py` (or a shared module both import), then have
   `BRConfig._load_config()` apply the same `deep_merge()` step the hook
   already performs.
2. Have `BRConfig` call into a shared `resolve_effective_config()` helper that
   both the hook and `BRConfig` use, so the two consumers can't drift again.

Either approach should decide: is `ll.local.md` read once at `BRConfig`
construction time, or does staleness matter (e.g. `ll-issues decisions sync`
rewriting `## Active Rules` mid-run)? Given `BRConfig` instances are typically
short-lived (one per CLI invocation), read-once-at-construction is likely
sufficient.

## Implementation Steps

1. Decide where the shared parse/merge logic lives (extract from
   `session_start.py` vs. new shared helper) so the hook and `BRConfig` share
   one implementation instead of drifting.
2. Wire `BRConfig._load_config()` to apply the override after loading the
   base config.
3. Confirm the SessionStart hook keeps working unchanged (it should now be
   able to delegate to the shared helper instead of its own inline parse).
4. Test: with a `.ll/ll.local.md` overriding `project.test_cmd`, assert a
   freshly constructed `BRConfig` returns the overridden value.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py` — `BRConfig._load_config()`
- `scripts/little_loops/hooks/session_start.py` — reuse point for the shared
  parse/merge logic

### Similar Patterns
- `hooks/session_start.py:136-147` — the existing (process-local) parse +
  `deep_merge()` logic to reuse/extract

### Tests
- `scripts/tests/test_config.py` — new coverage for `BRConfig` + local
  override
- `scripts/tests/test_hook_session_start.py::TestSessionStartLocalOverrides`
  — existing coverage for the hook's own merge path, must keep passing

## Impact

- **Priority**: P3 — real but narrow; most projects don't heavily override
  config, and the failure mode (falls back to base config) is silent rather
  than destructive
- **Effort**: Medium — touches the shared config-loading core used by every
  `ll-*` invocation, not a single call site
- **Risk**: Low-Medium — behavior change is additive (previously-ignored
  overrides now apply), but `BRConfig._load_config()` is on the hot path for
  every CLI command
- **Breaking Change**: No — but any project whose `ll.local.md` currently sets
  an override that was silently ignored will see a behavior change once this
  ships

## Session Log
- `/ll:capture-issue` - 2026-08-08T21:49:28 - `d7b6c474-eeb6-4901-9ffd-be8f7cc9a06c.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P3
