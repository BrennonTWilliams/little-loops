---
id: ENH-2580
title: ll-session backfill defaults to user-root with project fallback
type: ENH
priority: P3
status: open
discovered_date: 2026-07-08
captured_at: "2026-07-08T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - backfill
  - captured
---

# ENH-2580: ll-session backfill defaults to user-root with project fallback

## Summary

`ll-session backfill` (via the detached subprocess
`scripts/little_loops/cli/backfill_worker.py:36-38`) currently discovers
JSONL files using the project-root path passed to it from
`scripts/little_loops/hooks/session_start.py:141-147`. The user-root
`~/.claude/projects/<host>/` location is only consulted by
`ll-logs` (`scripts/little_loops/cli/logs.py:142`), creating an
asymmetry between the two tools. Flip the default for backfill
discovery to user-root (resolved via the same
`host_runner.resolve_host()` mechanism `ll-logs` uses), with
project-root as a fallback when no user-root match exists for the
current `cwd`. Add `--project-only` to the `backfill` subparser to
opt out.

## Motivation

For users on one project at a time, the user-root
`~/.claude/projects/<host>/<cwd-hash>/<session-id>.jsonl` is the
canonical location of the session transcripts. The project-root
`.claude/projects/.../` location is only meaningful for
shared-checkout workflows (CI, monorepos, ephemeral dev
environments). The current `backfill` path defaults to project-root,
forcing users who want to backfill "all my Claude work for this
project" to first understand the two-location model.

EPIC-2369 (`ll-logs` target project/user mode) is already in flight
with four children (FEAT-2315, FEAT-2316, ENH-2317, ENH-2318) that
establish the user-scoped mode as the default for `ll-logs`. This
child aligns `ll-session backfill` with the same default.

**Concrete win**: the `SessionStart` subprocess at
`session_start.py:150-163` calls
`get_project_folder(cwd)` which only finds project-root JSONL.
Flipping to user-root discovery means the subprocess ingests the
same JSONL files `ll-logs` would show the user, eliminating the
"why is `ll-logs` showing 50 sessions but `ll-session recent` is
empty?" confusion.

## Current Behavior

- `scripts/little_loops/cli/backfill_worker.py:36-38` accepts
  `<db_path> <jsonl_or_dir>` as positional arguments and resolves
  the second arg to a list of `*.jsonl` files via
  `get_project_folder`.
- `scripts/little_loops/hooks/session_start.py:141-147` prefers
  `payload["transcript_path"]` (ENH-1945, the host's per-session
  transcript) over `get_project_folder(cwd)`. There is no concept
  of "user-root discovery" in this code path.
- `scripts/little_loops/cli/logs.py:142` uses
  `resolve_host()` to find `~/.claude/projects/<host>/` and
  iterates the directories inside it. This is the model for
  user-root discovery.
- The hardcoded `claude-code` host in the `recent --kind` and
  `search --kind` argparse lists is unrelated; the host
  resolution is via `LL_HOOK_HOST` env var and
  `host_runner.resolve_host()`.

## Expected Behavior

`ll-session backfill` (and the `SessionStart` subprocess call)
discovers JSONL files in this order:

1. `payload["transcript_path"]` (preserved — the host's
   per-session transcript path, when available).
2. User-root `~/.claude/projects/<host>/*/`, filtered to sessions
   whose first `sessionId` is associated with `cwd` (new — uses
   `host_runner.resolve_host()` to locate the user root and a
   new `cwd_to_user_dir` reverse map to filter).
3. Project-root `<cwd>/.claude/projects/*/` (current default —
   becomes fallback when step 2 yields no files).

The `--project-only` flag skips step 2 entirely. The merged file
list is deduplicated by absolute path.

## Proposed Solution

1. **Add `resolve_user_root_sessions(host, cwd) -> list[Path]`** in
   `scripts/little_loops/cli/logs.py`, alongside the existing
   `_iter_projects()` helper. The function:
   - Resolves the user-root via `resolve_host()` (same path
     `cli/logs.py:142` uses).
   - Iterates `~/.claude/projects/<host>/*/<session_id>.jsonl`.
   - For each JSONL, reads the first line and extracts
     `sessionId` plus the `cwd` the session was started in
     (Claude Code embeds `cwd` in the JSONL header).
   - Returns the subset whose `cwd` matches the current `cwd`
     (or any descendant, with a `--strict-cwd` opt-out).

2. **`cli/backfill_worker.py` calls the helper first**, then the
   existing project fallback. Merge by absolute path, preserving
   order (user-root first).

3. **`cli/session.py` `backfill` subparser gains `--project-only`**
   flag. When set, the helper is bypassed.

4. **`hooks/session_start.py:141-147`** switches from
   "prefer transcript_path, fall back to project folder" to the
   same three-step discovery. The `--rebuild` flag (introduced
   by ENH-2581) is orthogonal.

5. **EPIC-2369 alignment**: FEAT-2315/2316 and ENH-2317/2318 share
   `cli/logs.py`, so the new helper is reusable across both epics.
   Document the helper in
   `docs/reference/API.md#little_loopscli_logs`.

## Acceptance Criteria

- `ll-session backfill` (no flags) on a project whose JSONL
  lives only in the user-root discovers and ingests those JSONL.
- `ll-session backfill --project-only` on the same project
  ingests only the project-root JSONL (legacy behavior).
- The merged file list is deduplicated by absolute path (no
  double-ingestion when the same JSONL is in both locations).
- The `SessionStart` subprocess (which calls
  `cli/backfill_worker.py`) uses the same three-step discovery.
- `analytics.auto_collect.enabled` is **not** required to enable
  this change; the user-root discovery is the new default for
  backfill regardless.
- Existing `backfill` tests pass unchanged; new tests cover the
  user-root discovery path and the `--project-only` flag.

## Implementation Steps

1. Add `resolve_user_root_sessions(host, cwd) -> list[Path]` in
   `scripts/little_loops/cli/logs.py`. Mirror the
   `host_runner.resolve_host()` use at
   `cli/logs.py:142`.
2. Extend `cli/backfill_worker.py` to call the helper first,
   then the project fallback, with `--project-only` support.
3. Extend `scripts/little_loops/cli/session.py:150` (`backfill`
   subparser) with `--project-only` argparse flag.
4. Update `scripts/little_loops/hooks/session_start.py:141-147`
   to use the same three-step discovery in the subprocess arg
   list.
5. Document the helper in
   `docs/reference/API.md#little_loopscli_logs` and the new
   flag in `docs/reference/CLI.md#ll-session-backfill`.
6. Tests in
   `scripts/tests/test_ll_session.py` (new
   `TestBackfillProjectOnly` class following
   `TestBackfillSinceFlag` at lines 497-554).
7. Tests in `scripts/tests/test_cli_logs.py` (new
   `TestResolveUserRootSessions`).

## Impact

- **Priority**: P3.
- **Effort**: Small. One new helper, one subprocess arg, one
  CLI flag, two test classes.
- **Risk**: Low. The user-root discovery includes the
  project-root files in the common case (the same JSONL is in
  both locations), so the change is *additive* for users whose
  JSONL happens to live in both. Users whose JSONL lives only
  in the user-root see new behavior; that's the fix.
- **Breaking Change**: No. The `cli_events` table records
  `ll-session backfill` invocations with the same args; no
  schema change.

## Sources

- `thoughts/history-db-raw-events-architecture.md` § "The
  migration story" — the broader architecture this child
  participates in.
- `thoughts/history-db-expand-wiring.md` — the original
  findings report this design extends.
- `scripts/little_loops/cli/logs.py:142` — the
  `resolve_host()` pattern to mirror.
- `scripts/little_loops/hooks/session_start.py:141-163` —
  the current subprocess spawn.
- `scripts/little_loops/cli/backfill_worker.py:36-38` — the
  subprocess body to extend.
- `.issues/epics/P3-EPIC-2369-ll-logs-target-project-user-mode.md`
  — the in-flight epic whose `ll-logs` work this aligns with.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Session start flow; SessionEnd addition (ENH-2582). |
| `docs/reference/API.md` | `host_runner.resolve_host()` reference. |
| `docs/reference/CLI.md` | `ll-session backfill` and the new `--project-only` flag. |
| `thoughts/history-db-raw-events-architecture.md` | The parent design doc. |

## Status

**Open** | Created: 2026-07-08 | Priority: P3

Depends on **ENH-2581** (raw_events source of truth) — the
`raw_events` table is the destination the user-root JSONL files
are ingested into. After ENH-2581 lands, this child is a
~1-day implementation.

## Session Log
- `/ll:capture-issue` - 2026-07-08T00:00:00Z - fourth-pass expansion of EPIC-2457
