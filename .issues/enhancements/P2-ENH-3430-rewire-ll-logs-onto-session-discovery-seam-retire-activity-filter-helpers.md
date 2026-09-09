---
id: ENH-3430
type: ENH
title: Rewire ll-logs onto the session-discovery seam; retire _has_ll_activity/_extract_cwd_from_project
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-09-09'
captured_at: '2026-09-09T21:54:30Z'
labels:
- multi-host
- observability
parent: ENH-3419
blocked_by:
- ENH-3427
blocks: []
relates_to:
- ENH-3420
- FEAT-3417
- ENH-3428
- ENH-3429
- ENH-3422
---

# ENH-3430: Rewire ll-logs onto the session-discovery seam; retire _has_ll_activity/_extract_cwd_from_project

## Summary

Decomposed from ENH-3419 (score 8/11, Very Large). This is the widest child: 11
`get_project_folder` call sites across 6 functions in `cli/logs.py`, plus the `--all` enumeration
in `discover_all_projects`. Depends on ENH-3427 for `_resolve_host`, `REGISTERED_HOSTS`, and the
`--host` flag already registered on `ll-logs`'s 9 session-touching subcommands.

**Coordination note**: this issue owns the handles-based `_extract_ll_event_streams` signature;
ENH-3422 (the backfill/HostLayout shrink) retargets only `_backfill_raw_events`
(`session_store/lifecycle.py`), the layout-descriptor shrink in `session_store/writers.py`, and the
`cli/session.py`/`cli/backfill_worker.py` callers. `_has_ll_activity` and `_extract_cwd_from_project`
(both defined in `cli/logs.py`, lines 97 and 134) are deleted by this issue, not ENH-3422 — drop
them from ENH-3422's scope.

## Parent Issue

Decomposed from ENH-3419: Adopt the session-discovery seam in ll-logs, ll-messages, and
ll-ctx-stats (Codex observability).

## Current Behavior

11 un-hosted `get_project_folder(...)` calls across 6 functions: `_collect_sequences` (653, 658,
667), `_cmd_sequences` (693), `_cmd_extract` (774, 783), `_collect_failure_clusters` (1353, 1358,
1367; second caller `_cmd_fleet_review` at ~2843), `_cmd_scan_failures` (1554), `_cmd_eval_export`
(2040). Every one globs `*.jsonl` excluding `agent-*` (797, 1375, 2050 — **not** 725, which is
`generate_index` globbing the local extracted `logs/` output dir and must not be rewired). Plus
`--all` enumeration in `discover_all_projects` (166-215), which walks
`host_layout_for(host).projects_root.iterdir()` (`None` for Codex), filters to workspaces with ll
activity (`_has_ll_activity`, 213), and has seven consumers: `_collect_sequences` (664),
`_cmd_extract` (780), `_cmd_dead_skills` (1075), `_collect_failure_clusters` (1364), `_cmd_stats`
(1639), `_cmd_loop_fleet` (2335), `_cmd_fleet_review` (2782), plus the `discover` subcommand
(3235). `_extract_ll_event_streams` (261-290, `cli/logs.py`) still takes a `project_folder` and globs
`effective.session_glob` (the resolved `HostLayout`, defaulting to Claude Code). `_collect_sequences`
also resolves a `HostLayout` from `LL_HOOK_HOST` directly (649).

## Expected Behavior

- All 11 `get_project_folder` call sites and the `--all` enumeration path route through
  `detect_sessions`/`list_workspaces` instead of `get_project_folder`/`get_sessions_folder`.
- With no `--host` flag and no `LL_HOOK_HOST`, `ll-logs sequences`/`extract`/`scan-failures`/
  `eval-export`/`discover` show sessions from every host that recorded activity for the target
  workspace (e.g. both a Claude Code and a Codex session in the same cwd); `--host <name>` narrows
  to one.
- `--all` enumeration unions workspaces across hosts (deduped on resolved cwd), still applying the
  existing ll-activity filter so output does not widen to include non-ll workspaces.
- `_has_ll_activity` and `_extract_cwd_from_project` no longer exist; `_extract_ll_event_streams`
  takes `SessionHandle` objects instead of a bare `project_folder`.
- Existing Claude Code and qwen behavior (session content, `agent-*` exclusion, exit codes, stdout
  contracts) is unchanged.

## Scope Boundaries

- **In scope**: the 11 `get_project_folder` call sites and `discover_all_projects` in
  `cli/logs.py`; deleting `_has_ll_activity`/`_extract_cwd_from_project`; threading `--host` through
  all 8 `discover_all_projects` callers; the handles-based `_extract_ll_event_streams` signature.
- **Out of scope**: `ll-messages` (ENH-3428) and `ll-ctx-stats` (ENH-3429) — disjoint files, separate
  issues. The `_backfill_raw_events`/`HostLayout` shrink and the `cli/session.py`/
  `cli/backfill_worker.py` callers — owned by ENH-3422. Fixing `list_workspaces("omp")`'s lossy
  session-dir encoding — documented gap, not fixed here. Restoring `discover_all_projects`'s
  lossy-decode `cwd` fallback for synthetic fixtures lacking a `cwd` record — intentionally dropped,
  not preserved.

## Program Design

### Types

- `SessionHandle` (existing, `session_store/sessions.py`): `host: str`, `session_id: str`,
  `path: Path`, `cwd: Path`, `updated_at: float`, `is_agent: bool`.

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` (existing, `session_store/sessions.py`)
- `list_workspaces(host: str, *, existing_only: bool = True, home: Path | None = None) -> list[Path]` (existing, `session_store/sessions.py`)
- `_extract_ll_event_streams(handles: list[SessionHandle], *, cutoff: datetime | None = None, until: datetime | None = None) -> dict[str, list[InvocationEvent]]` (rewritten signature, `cli/logs.py`)

### Call Path

`_cmd_sequences` -> `_collect_sequences` -> `detect_sessions` -> `iter_events` ->
`_extract_ll_event_streams`

`discover_all_projects` -> `list_workspaces` (per host) -> `iter_events` (via `_is_ll_relevant`
filter) -> dedupe on `cwd`

## Proposed Solution

1. **Route the 11 call sites** through `detect_sessions(..., include_agents=False)`.
2. **`--all` enumeration** through `list_workspaces(host, existing_only=...)`. Iterate **per host,
   not per workspace with `host=None`**: `for h in hosts: for ws in list_workspaces(h, ...):
   detect_sessions(ws, h, include_agents=False)` — calling `detect_sessions(ws, None)` per
   workspace probes all 8 hosts for every workspace. Dedupe after the per-host loop, on resolved
   cwd. The ll-activity filter **stays**: re-apply `_is_ll_relevant` per workspace via an
   early-exit walk over `iter_events(h)`, so `discover`/`extract --all`/`scan-failures --all`
   output does not widen. Known gap to document, not fix: `list_workspaces("omp")` always returns
   `[]` (lossy session-dir encoding), so `--all` never enumerates omp workspaces under the union
   default.
3. **All 8 `discover_all_projects` callers** (`_collect_sequences` 664, `_cmd_extract` 780,
   `_cmd_dead_skills` 1075, `_collect_failure_clusters` 1364, `_cmd_stats` 1639, `_cmd_loop_fleet`
   2335, `_cmd_fleet_review` 2782, `discover` 3235) must thread
   `host=_resolve_host(getattr(args, "host", None))` — use `getattr` because
   `test_ll_logs.py:6051,6093` call `_collect_failure_clusters`/`_collect_sequences` directly with
   hand-built `argparse.Namespace` objects lacking a `host` attribute.
4. **`_extract_ll_event_streams`**: give it a handles-based entry point —
   `_extract_ll_event_streams(handles: list[SessionHandle], *, cutoff, until)` iterating
   `iter_events(h)` and applying `_extract_tool_name(e.payload)` — and delete the `layout=`
   pass-through in `_collect_sequences` together with `host_layout_for(LL_HOOK_HOST)` at 649.
   Bucket on `e.payload.get("sessionId") or h.session_id` (Codex payloads carry no `sessionId`).
5. **Delete `_has_ll_activity` (97) and `_extract_cwd_from_project` (134)**: their only production
   callers are inside `discover_all_projects`, which step 2 rewrites. Delete them together with
   their two direct unit tests. `discover_all_projects`'s lossy-decode fallback
   (`project_dir.name.replace("-", "/")` when no record carries `cwd`) is **not preserved** —
   `list_workspaces` has no such fallback; documented as a behavior change (real Claude Code
   records always carry `cwd`, so only synthetic fixtures are affected).
6. **`list_workspaces → detect_sessions(ws)` round-trip**: must tolerate an unresolved recorded
   `cwd` on macOS (`/var/...` → `/private/var/...`) — this depends on ENH-3427's both-spellings
   probe having landed in `session_store/sessions.py`.
7. **No-sessions stderr**: `_cmd_scan_failures`/`sequences`/`extract`/`eval-export` change the
   wording to `"No sessions found for: <cwd>"`; exit code stays **1** (two existing tests lock
   `rc=1`: `test_sequences_project_not_found_returns_1` 1224, `test_extract_project_not_found_
   returns_1` 1822). Reorder `.loops/ll-logs-telemetry-digest.yaml:63-66` so the grep for the new
   string precedes the `[ "$RC" -ne 0 ]` check, so a missing-sessions `rc=1` reports
   `FAILURES_NO_DATA` and any other `rc≠0` still reports `FAILURES_ERROR`.
8. **`ll-logs fleet-review` stdout contract** (last line = report path) stays unchanged —
   `fleet-loop-improve.yaml:78,80` pipes it through `tail -n 1`; AC-locked.

## Files to Modify

- `scripts/little_loops/cli/logs.py` (module docstring line 1; `discover_all_projects` 166-215;
  the 6 functions/11 call sites above; 649; `_cmd_fleet_review` ~2843; delete 97, 134)
- `.loops/ll-logs-telemetry-digest.yaml:63-67`
- `scripts/little_loops/cli/__init__.py` module docstring line 16
- `docs/reference/CLI.md` — `### ll-logs` section
- `docs/guides/*` — remaining `ll-logs` Claude-Code-only framing not already covered by ENH-3428

### Tests

- `scripts/tests/test_ll_logs.py` — `TestSequences`/`TestArgumentParsingSequences` (797-1339),
  `TestExtract` (1547-2127), `TestScanFailures` (2924-4155), `TestEvalExport*` (4437-4841); add
  `--host codex` variants using the committed fixtures under `scripts/tests/fixtures/codex/`. Add a
  union-dedupe case: same cwd recorded under two hosts appears once.
  `TestDiscover::test_discover_skips_non_ll_project` (204) and its positive siblings
  (`test_discover_finds_project_via_queue_operation` 138, `..._dotted_worktree_subpath` 171) must
  pass unmodified. Re-patch `little_loops.cli.logs.get_project_folder` sites (e.g. ~2083 in
  `TestExtract`) to `detect_sessions`. `test_sequences_project_not_found_returns_1` (1224) and
  `test_extract_project_not_found_returns_1` (1822) pass unmodified. Direct-call tests at 6051,
  6093 pass unmodified (read `getattr(args, "host", None)`).
- `scripts/tests/test_enh_3166_qwen_normalizer.py` — delete `test_has_ll_activity_detects_
  normalized_run_shell_command` (288) and `test_extract_cwd_honors_chats_glob` (298);
  `test_discover_all_projects_finds_qwen_project` (277) stays and must pass through the new path.
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py` — re-run after adding `--host`;
  add the `FAILURES_NO_DATA` reachability test.
- Add a `fleet-review` last-stdout-line-is-path test.

### Behavior Parity

`scripts/tests/test_enh_3166_qwen_normalizer.py`:

| Behavior | Status |
|---|---|
| `test_discover_all_projects_finds_qwen_project` — qwen project discoverable via `discover_all_projects` | Preserved (routes through `list_workspaces`/`detect_sessions` instead) |
| `test_has_ll_activity_detects_normalized_run_shell_command` — direct `_has_ll_activity` unit coverage | Dropped (function deleted; the ll-activity filter it tested is re-applied inside `discover_all_projects`'s per-workspace walk and still exercised via the discover test above) |
| `test_extract_cwd_honors_chats_glob` — direct `_extract_cwd_from_project` unit coverage | Dropped (function deleted; cwd extraction now lives in `session_store.sessions._first_record_cwd`, already covered by that module's own tests) |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- `scripts/little_loops/session_store/__init__.py` — public re-exports of the seam this issue rewires onto: `SessionHandle` (132/272), `detect_sessions` (133/275) — confirms these are stable public entry points, not internals.
- `scripts/little_loops/session_store/sessions.py:466,474` — inline comments there reference `_extract_cwd_from_project` and `discover_all_projects`'s silent-`[]` precedent, corroborating this issue's own note that the lossy-decode `cwd` fallback has no `list_workspaces` equivalent.
- `docs/reference/API.md:3539-3587` — existing `discover_all_projects` docstring/signature; `:9497-9567` documents the `SessionHandle`/`detect_sessions`/`list_workspaces` seam already, so the doc update in scope is narrower than a fresh write.
- `scripts/tests/test_fleet_improve.py`, `scripts/tests/test_builtin_loops.py` — additional existing coverage touching `ll-logs fleet-review`/`fleet-loop-improve.yaml`, not previously listed; worth a pass-unmodified check alongside the named test files.
- Confirmed via repo-wide grep: `_resolve_host`, `REGISTERED_HOSTS`, and a registered `--host` flag do not yet exist anywhere in `scripts/little_loops/` (0 production hits) — ENH-3427's host-resolution seam this issue is `blocked_by` has genuinely not landed yet, not just undocumented.

## Acceptance Criteria

- `ll-logs` obtains sessions via `detect_sessions`/`iter_events` and never calls
  `get_project_folder`/`get_sessions_folder` for session enumeration; `--all` enumerates via
  `list_workspaces`, unions hosts when none is resolved (deduped on cwd; omp workspaces documented
  as a gap), and still applies the ll-activity filter (all four `TestDiscover` tests pass
  unmodified on macOS and Linux).
- `_extract_ll_event_streams` takes handles, buckets on `payload.get("sessionId") or
  handle.session_id`, and `cli/logs.py` no longer calls `host_layout_for(LL_HOOK_HOST)` (line 649
  removed); `_has_ll_activity` and `_extract_cwd_from_project` no longer exist; `ll-logs sequences`
  output for existing Claude Code and qwen tests is unchanged.
- Every one of the 8 `discover_all_projects` call sites passes the resolved host through, asserted
  by a test that `LL_HOOK_HOST=qwen ll-logs discover` lists only qwen workspaces.
- `ll-logs scan-failures`/`sequences`/`extract`/`eval-export` with no sessions for the target still
  exit 1, now with `"No sessions found for: <cwd>"` on stderr
  (`test_ll_logs.py:1224,1822` unmodified); `.loops/ll-logs-telemetry-digest.yaml`'s
  `scan_failures` state actually reaches `FAILURES_NO_DATA` on an empty home (test-asserted).
- `ll-logs fleet-review --all` still prints the report path as its last stdout line.
- With no flag and no `LL_HOOK_HOST`, a workspace containing both a Claude Code and a Codex session
  shows both in `ll-logs sequences`; `--host codex`/`--host claude-code` narrows to one.
- Claude Code output for every existing test in `test_ll_logs.py` is unchanged; every `cli/logs.py`
  path still excludes `agent-*` sessions.
- `docs/reference/CLI.md` and remaining guides no longer frame `ll-logs` as Claude-Code-only.

## Impact

- **Priority**: P2 - widest and highest-risk child of ENH-3419's decomposition (11 call sites, 6
  functions, 8 `discover_all_projects` callers); blocks full multi-host parity for `ll-logs`.
- **Effort**: Large - touches 6 functions across `cli/logs.py`, threads `--host` through 8 callers,
  rewrites `_extract_ll_event_streams`'s signature, deletes 2 functions plus their direct unit
  tests, and requires `--host codex` test variants across 4 test classes.
- **Risk**: Medium - behavior changes are scoped and documented (omp gap, dropped lossy-`cwd`
  fallback for synthetic fixtures), and existing Claude Code/qwen test suites must pass unmodified
  per the Acceptance Criteria; the main risk is the per-host iteration requirement in `--all`
  enumeration (calling `detect_sessions(ws, None)` per workspace instead of iterating per host would
  silently multiply the host-probe cost and break the union-dedupe contract).
- **Breaking Change**: No for real usage (Claude Code/qwen output unchanged); Yes for synthetic test
  fixtures relying on the lossy-decode `cwd` fallback, which is intentionally dropped.

## Dependencies

Blocked by ENH-3427 (host-resolution seam, including the both-spellings probe this issue's
`TestDiscover` tests need). Independent of ENH-3428/ENH-3429 (disjoint files — touches
`cli/logs.py` only). Coordinates with ENH-3422: this issue deletes `_has_ll_activity`/
`_extract_cwd_from_project`, so ENH-3422 must not retarget them.

## Status

**Open** | Created: 2026-09-09 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-09T22:41:03 - `9fe38579-0a99-4bad-b518-b7f5e109e55f.jsonl`
- `/ll:format-issue` - 2026-09-09T22:05:30 - `af86aaee-e2d3-4675-b045-b23f45bd4759.jsonl`
- `/ll:issue-size-review` - 2026-09-09T21:57:08 - `0ecdfd2a-1186-4e76-ae8e-586f75aad086.jsonl`
