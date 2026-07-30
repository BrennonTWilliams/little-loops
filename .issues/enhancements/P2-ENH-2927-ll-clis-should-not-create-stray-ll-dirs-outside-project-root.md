---
id: ENH-2927
title: ll-* CLIs should not implicitly create .ll/ directories outside a resolved project root
type: ENH
status: open
priority: P2
discovered_date: 2026-07-30
discovered_by: review
labels:
- robustness
- cli
- hygiene
relates_to:
- ENH-2924
- ENH-2870
blocked_by:
- ENH-2924
---

# ENH-2927: ll-* CLIs should not implicitly create `.ll/` directories outside a resolved project root

## Summary

Running any `ll-*` command from a subdirectory implicitly creates a `.ll/` directory
at the current working directory. These stray dirs regenerate faster than manual
cleanup (four new strays — `scripts/.ll`, `scripts/little_loops/.ll`, `skills/.ll`,
`hooks/adapters/opencode/.ll` — appeared within two days of a 50-dir cleanup on
2026-07-27) and are the generation-side root cause behind ENH-2924's resolution fix.
ENH-2924 makes `find_project_root()` skip strays; this issue stops producing them, so
every *other* nearest-`.ll` walker (config discovery, history DB resolution, decisions
store) stops tripping on them too.

## Current Behavior

Various code paths (config write-through, history DB default path `.ll/history.db`,
decisions store `.ll/decisions.d/`, queue DB `.ll/queue.db`, run/state scratch) create
their parent `.ll/` with `mkdir(parents=True, exist_ok=True)`-style calls anchored at
a root derived from cwd. When invoked from a subdirectory with no upward resolution
(or before resolution runs), the `.ll/` lands at cwd. The dirs are gitignored-by-
default side effects, so pollution accumulates silently.

## Expected Behavior

`.ll/` is only ever created at a *resolved* project root:

- If an ancestor of cwd already contains `.ll/` (per ENH-2924's `.git`-aware
  resolution), all writes anchor there — never at cwd.
- If no project root resolves at all, commands that need `.ll/` state either fail
  with a clear "not inside a little-loops project; run ll-init" error, or (for
  `ll-init` itself) create it deliberately at the chosen root.
- No `ll-*` command creates `.ll/` as an incidental side effect of a read-only
  operation (list, show, validate, stats).

## Proposed Solution

1. Inventory every `mkdir` / open-for-write site whose path contains `.ll`
   (`grep -rn "\.ll" scripts/little_loops --include='*.py' | grep -i "mkdir\|parents=True"`)
   and classify each as read-path (must never create), write-path (must anchor at
   resolved root), or init-path (`ll-init`, allowed to create).
2. Introduce/centralize a single `resolve_ll_dir(create: bool = False)` helper that
   performs upward resolution (sharing ENH-2924's `.git`-aware rule) and is the only
   place allowed to `mkdir` `.ll/`.
3. Route the inventoried sites through it; read-paths get `create=False` and a clear
   error or graceful empty result when no root exists.
4. Regression test: invoking a representative read command (e.g. `ll-issues list`)
   from a `tmp_path` repo subdirectory leaves no `.ll/` behind at that subdirectory.

## Program Design

### Signatures

- `resolve_ll_dir(start: Path | None = None, create: bool = False) -> Path | None`

  New; likely home alongside `find_project_root` in `scripts/little_loops/issues/program_design.py` or a new `paths` module (final placement decided at inventory time). Sole authority for locating and (when `create=True`) creating `.ll/`; delegates upward resolution to ENH-2924's `.git`-aware `find_project_root` rule.

### Call Path

Each inventoried creation site — e.g. the session-store default DB resolution in `scripts/little_loops/session_store/db.py` (`resolve_history_db`), the decisions store under `scripts/little_loops/issues/`, the queue DB `.ll/queue.db` — currently computes `<root>/.ll` locally and creates it with a parents-and-exist-ok mkdir; each is rerouted through the new `resolve_ll_dir` helper, which itself calls the existing `find_project_root`. Read-paths pass `create=False` and return empty or error when resolution fails; `ll-init` (`main_init`) remains the only caller allowed to create `.ll/` at a root that has none.

## Scope Boundaries

**In scope:** creation-site inventory and rerouting through a shared resolver;
regression coverage that subdirectory invocations create no stray `.ll/`.

**Out of scope:** ENH-2924's `find_project_root()` selection rule (lands first and
this builds on it); deleting existing strays (one-time manual cleanup); changing
what lives inside `.ll/`.

## Impact

- **Priority**: P2 — same live failure class as ENH-2924; resolution-side fix alone
  leaves other `.ll` walkers exposed and keeps polluting consuming repos.
- **Effort**: Medium — the change is mechanical but the creation-site inventory
  spans several modules.
- **Risk**: Low-Medium — a missed write-path anchored at cwd today would start
  erroring instead of silently writing to the wrong place; that surfacing is the
  point.
- **Breaking Change**: Only for workflows that (accidentally) depended on cwd-local
  `.ll/` creation.

## Status

**Open** | Created: 2026-07-30 | Priority: P2
