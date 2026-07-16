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
decision_needed: true
decision_context: "Subprocess argv shape — see Proposed Solution Codebase Research Findings. Option A: stage merged JSONL list into a temp dir (zero worker signature change). Option B: extend worker signature to accept multiple --jsonl=path pairs (cleaner argv, more code change). Recommended: Option A for v1."
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
- `scripts/little_loops/cli/logs.py:137-199` defines
  `discover_all_projects()`, which iterates
  `~/.claude/projects/` (or the per-host equivalent) and is
  the model for user-root discovery. **Note**: the file reads
  `LL_HOOK_HOST` directly via `os.environ.get("LL_HOOK_HOST",
  "claude-code")` (`cli/logs.py:161`) and does **not** call
  `host_runner.resolve_host()`; the new helper should use
  `resolve_host().name` to align with all other call sites
  (`session_store.py:2689`, `cli/loop/_helpers.py:2016`,
  `subprocess_utils.py:328`, `cli/action.py:155`,
  `cli/doctor.py:141`).
- The hardcoded `claude-code` host in the `recent --kind` and
  `search --kind` argparse lists is unrelated; the host
  resolution is via `LL_HOOK_HOST` env var and
  `host_runner.resolve_host()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`cli/logs.py:142` reference is off by ~5 lines** — the
  relevant function is `discover_all_projects()` at
  `scripts/little_loops/cli/logs.py:137-199`. The
  `_extract_cwd_from_project()` helper at `cli/logs.py:110-134`
  already provides the JSONL-based `cwd` extraction the new
  helper needs (it returns `Path(cwd)` from the first record
  with a non-empty `cwd` string and skips `agent-*.jsonl`).
- **`_iter_projects` does not exist** in the codebase. The
  proposed solution refers to it, but the only iteration helper
  in `cli/logs.py` is `discover_all_projects()` itself. The new
  helper should be modeled on it (host-root dispatch +
  per-directory JSONL inspection) rather than introducing a
  parallel `_iter_projects` symbol.
- **`cwd_to_user_dir` does not exist** as a generic reverse
  mapping. `encode_project_path()` at `user_messages.py:358-366`
  performs a *forward* mapping (`/foo/bar` → `-foo-bar`), but it
  is **lossy for paths containing hyphens** (the
  `discover_all_projects()` docstring calls this out: a path
  like `/Users/foo/little-loops` cannot be unambiguously
  recovered from `-Users-foo-little-loops`). The new helper
  must iterate `~/.claude/projects/<host>/*/` and filter by
  reading `cwd` from JSONL — not by encoding the current `cwd`
  and probing a single directory. This is exactly what
  `_extract_cwd_from_project()` was built for.
- **Subprocess argv shape is a real decision point.** The
  current `backfill_worker.py:36-38` accepts a single
  `<db_path> <jsonl_or_dir>` positional pair, then either
  globs a directory or uses a single file. The new helper
  returns `list[Path]` (potentially many JSONL files from
  multiple user-root directories merged with the project-root
  fallback). Two viable resolutions:

  **Option A**: Stage discovered files into a temp directory
  (symlinks or hardlinks into the user's session dirs) and
  pass that single dir to the existing worker. **Zero worker
  signature change**; uses the worker's existing
  `path_arg.is_dir()` glob path.

  **Option B**: Extend the worker to accept multiple
  positional `--jsonl=path` arguments (or `nargs="*"` after
  the db path), updating both `main()` and the
  `session_start.py` argv construction at lines 153-159.
  Cleaner argv; requires touching the worker.

  **Recommended**: Option A for v1 — keeps the worker
  contract stable (the `--rebuild` ad-hoc-flag precedent at
  `backfill_worker.py:24` argues against extending argv
  shape), and the temp-dir staging can be reused by any
  future caller that needs multi-file discovery.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (new helper)**: Place the helper alongside
  `discover_all_projects()` at `cli/logs.py:137-199`. It should
  use `resolve_host().name` (not `os.environ.get` directly) and
  delegate cwd extraction to the existing
  `_extract_cwd_from_project()` at `cli/logs.py:110-134` (skip
  `agent-*.jsonl`, return on first valid `cwd` record, fail
  silently on `OSError`/`JSONDecodeError`). Filter by
  `cwd == cwd.resolve()` (or `cwd.is_relative_to(target)` for
  descendant match — per the issue's `--strict-cwd` opt-out).
- **Step 2 (worker)**: `backfill_worker.py:22` (`main()`) needs
  to accept a `--project-only` flag with the same ad-hoc
  detection pattern as `--rebuild` (`"--project-only" in args`,
  line 24). When set, skip the new helper. When unset, call the
  helper first, then fall back to the existing
  `path_arg.is_dir()` glob. Per Option A above, stage the
  merged list into a temp dir under `tempfile.TemporaryDirectory`
  before passing to `backfill_incremental()`.
- **Step 3 (argparse)**: `cli/session.py:139-183` is the actual
  `backfill` subparser (the issue's `session.py:150` reference
  is inside `--extract-decisions`). Add the flag at line 167
  (after `--snapshots`) with `action="store_true",
  default=False, dest="project_only"`, and consume it in the
  dispatch block at `session.py:470-562`. The naming aligns
  with the `--existing-only` pattern at `cli/logs.py:1980-1984`.
- **Step 4 (SessionStart)**: The current subprocess argv is at
  `session_start.py:153-159`. The new three-step discovery
  produces either a single file (transcript_path) or a temp
  dir (Option A staging). Update the `_backfill_path` logic at
  `session_start.py:141-147` accordingly. The `--rebuild` flag
  construction at `session_start.py:160-172` is orthogonal and
  stays.
- **Steps 6-7 (tests)**: Mirror `TestBackfillSnapshotsFlag` at
  `test_ll_session.py:897-929` (newer model) rather than
  `TestBackfillSinceFlag` at `test_ll_session.py:513-570`. Both
  patterns are valid but `TestBackfillSnapshotsFlag` uses
  cleaner mock boundaries (patches `backfill_snapshots`
  directly). The test file is
  `scripts/tests/test_ll_session.py` (not split — there is no
  `test_cli_logs.py`; the `cli/logs.py` tests live in
  `scripts/tests/test_ll_logs.py`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add
  `resolve_user_root_sessions(host, cwd)` alongside
  `discover_all_projects()` at line 137; reuse
  `_extract_cwd_from_project()` at line 110.
- `scripts/little_loops/cli/backfill_worker.py` — extend
  `main()` at line 22 with `--project-only` ad-hoc flag
  detection (mirrors `--rebuild` at line 24); add Option A
  temp-dir staging when helper is called.
- `scripts/little_loops/cli/session.py` — add `--project-only`
  to `backfill_parser` at line 167 (between `--snapshots` and
  `--max-sessions`); consume in dispatch block at
  `cli/session.py:470-562`.
- `scripts/little_loops/hooks/session_start.py` — replace the
  single-path logic at `session_start.py:141-147` with
  three-step discovery; update argv construction at
  `session_start.py:153-159`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/messages.py` — uses
  `get_project_folder` (same forward map; no change needed).
- `scripts/little_loops/cli/loop/_helpers.py:2016` — uses
  `resolve_host().name` (same pattern the new helper should
  follow).
- `scripts/little_loops/session_store.py:2689` — uses
  `resolve_host().name` for event-kind dispatch.

### Similar Patterns
- `scripts/little_loops/cli/logs.py:137-199` —
  `discover_all_projects()` is the canonical user-root
  discovery pattern (host dispatch + JSONL cwd extraction).
- `scripts/little_loops/cli/logs.py:110-134` —
  `_extract_cwd_from_project()` is the canonical
  embedded-cwd extractor.
- `scripts/little_loops/cli/logs.py:1980` — `--existing-only`
  flag pattern (positive-scope opt-out naming; same shape as
  the new `--project-only`).

### Tests
- `scripts/tests/test_ll_session.py` — existing
  `TestBackfillSinceFlag` (line 513) and
  `TestBackfillSnapshotsFlag` (line 897); add
  `TestBackfillProjectOnly` mirroring the snapshots pattern.
- `scripts/tests/test_ll_logs.py` — add
  `TestResolveUserRootSessions` for the new helper.
- `scripts/tests/test_hook_session_start.py` — add
  three-step discovery coverage for the SessionStart subprocess.

### Documentation
- `docs/reference/API.md#little_loopscli_logs` — document
  `resolve_user_root_sessions()`.
- `docs/reference/CLI.md#ll-session-backfill` — document
  `--project-only`.
- `docs/ARCHITECTURE.md` — update the session-start flow
  diagram to show the three-step discovery.

### Configuration
- No new config keys required. `analytics.auto_collect.enabled`
  remains orthogonal (per AC).

_Added by `/ll:refine-issue` — Integration Map section
populated from codebase research; the original issue had no
Integration Map._

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
- `/ll:refine-issue` - 2026-07-16T17:31:04 - `8fa2ea39-9ae6-4c89-90c1-a8a949c1dbde.jsonl`
- `/ll:capture-issue` - 2026-07-08T00:00:00Z - fourth-pass expansion of EPIC-2457
