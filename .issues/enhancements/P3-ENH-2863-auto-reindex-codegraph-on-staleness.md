---
id: ENH-2863
title: auto-sync codegraph index on staleness via codegraph CLI sync
type: ENH
priority: P3
status: open
labels:
- code-intelligence
- codegraph
- captured
captured_at: '2026-07-27T16:53:49Z'
discovered_date: '2026-07-27'
discovered_by: capture-issue
parent: EPIC-2575
relates_to:
- ENH-2577
- ENH-2578
---

# ENH-2863: auto-sync codegraph index on staleness via codegraph CLI sync

## Summary

`CodegraphProvider` (`scripts/little_loops/codequery/codegraph.py`) reads
`.codegraph/codegraph.db` strictly read-only and already detects staleness
(`status()`, lines 156-237: `head_moved` git-log-since count + scoped
`dirty_files` count, gated by `config.staleness` policy `strict|warn|off`,
default `warn`). The index itself is built and refreshed by an **external**
tool, `@colbymchenry/codegraph` (npm, installed globally — confirmed present
on this machine at `~/.npm-global/bin/codegraph`), not by anything in this
repo. That CLI already ships the exact incremental primitive needed:
`codegraph sync [path]` diffs the working tree against the last index and
updates only changed files — confirmed cheap in practice (0.18s on a
906-file / 28.5k-node / 65k-edge project with no pending changes; a few
seconds when there are real changes to parse). Nothing in little-loops calls
`sync` automatically, so `.codegraph.db` only advances when a human happens
to run it by hand.

## Current Behavior

Under the default `warn` policy, a stale index still reports
`available: true`, so `/ll:wire-issue` Phase 3.6 (per
`skills/wire-issue/graph-discovery-layer.md`) keeps using it — treating
results as unconfirmed leads and widening confirmation, per the "never trust
negatives" rule. This is graceful degradation, not a failure, but graph
answers quietly get less useful the longer a project goes without a manual
sync. Observed in the wild: `/ll:wire-issue ENH-2852 --auto` ran against an
index 193 commits stale (`indexed_at: 2026-07-22`); running
`codegraph sync --quiet` closed the gap in well under a second and flipped
`ll-code status` back to `freshness: fresh` immediately.

ENH-2577 (which built `CodegraphProvider` + staleness detection) explicitly
scoped "auto-reindex hooks" **out** as a future follow-up once ENH-2578
landed; no issue tracked that follow-up until now.

## Expected Behavior

Wire an auto-trigger that runs `codegraph sync --quiet [path]` whenever the
index is stale, instead of leaving it to accumulate indefinitely:

- **Where to trigger from** — candidates, not mutually exclusive:
  - A `SessionStart` hook (mirrors `session-end.sh`'s existing
    staleness-triggered sweep pattern from FEAT-1680).
  - Inline in `CodegraphProvider`/`ll-code` itself: on a `stale` status read,
    shell out to `codegraph sync --quiet` before answering the query (sync
    cost is low enough — sub-second when clean — that this can likely run
    synchronously rather than needing a background job).
  - A check folded into `ll-doctor --full`.
- **Detect the CLI is absent gracefully.** `codegraph` is an external,
  separately-installed dependency (not vendored, not a `pyproject.toml`
  entry) — if the binary isn't on `PATH`, skip the sync attempt silently and
  fall through to today's `stale`-but-`available` behavior. Do not hard-fail
  a calling skill because the optional sync couldn't run.
- **No configurable threshold needed.** Given sync cost is negligible when
  the tree is clean (confirmed: 0.18s no-op) and proportional to actual
  changed-file count otherwise, simplest correct behavior is "sync whenever
  status reports non-fresh," not a commit-count threshold requiring tuning.

## Motivation

Every project running little-loops with the codegraph provider enabled hits
this same silent decay — the index drifts further from HEAD with every
commit, with no signal beyond a `stale` field buried in `ll-code status`
output, even though closing that gap costs almost nothing. Graph-accelerated
discovery (ENH-2578) was built on the assumption that a usably-fresh index
exists; an auto-sync trigger is a small, cheap wire-up that keeps that
assumption true for the life of a project instead of degrading over time.

## Proposed Solution

Add a `_sync_if_stale()` (or similarly named) helper near
`CodegraphProvider.status()` that, when `is_fresh` is `False`:
1. Locates the `codegraph` binary (e.g. `shutil.which("codegraph")`); no-op
   if absent.
2. Runs `codegraph sync --quiet <repo_root>` with a short timeout.
3. On success, staleness naturally clears on the next `status()` call (no
   need to hand-patch `indexed_at` — re-derive from the tool's own output).
4. On failure/timeout, log at debug level and fall through to existing
   `stale`-but-`available` behavior — never raise.

Call this helper from wherever `status()` first observes `stale` under the
default policy (or gate behind a new `config.codegraph.auto_sync: bool`,
default `true`, if a kill switch is wanted for environments that manage
`codegraph sync` via their own external cron/git-hook).

## Implementation Steps

1. Add the `sync`-shelling helper to `CodegraphProvider` (or a thin wrapper
   module), gated on binary presence via `shutil.which`.
2. Trigger it from `status()` (or from `ll-code` CLI dispatch, whichever
   keeps query paths simplest) when staleness is detected, before returning
   the freshness verdict.
3. Add a `config.codegraph.auto_sync` toggle (default `true`) for opt-out.
4. Tests: binary-absent no-op path, sync-success path (freshness flips to
   `fresh` on next status call), sync-failure/timeout path (falls through
   without raising).
5. Update `docs/reference/API.md` codegraph section and
   `skills/wire-issue/graph-discovery-layer.md` if auto-sync changes how
   often "stale" is realistically encountered in practice.

## Impact

- **Priority**: P3 — graceful degradation already exists (`warn` policy),
  so this is an effectiveness improvement, not a broken-state fix.
- **Effort**: Small — the expensive unknown (would we need to write our own
  indexer?) is resolved: the incremental sync primitive already exists
  externally. This is a shell-out wire-up plus a graceful-absence guard.
- **Risk**: Low — sync is confirmed cheap and non-destructive (updates the
  same db in place); the binary-absent and sync-failure paths must both be
  strictly non-blocking so this never turns an optional acceleration into a
  new failure mode for skills that call `ll-code`.

## Session Log
- `/ll:capture-issue` - 2026-07-27T16:53:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92005058-34f6-4492-9015-3c5341fed493.jsonl`

---
## Status
- [ ] Not Started
