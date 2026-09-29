---
id: ENH-3549
title: Consume stored usage for ll-ctx-stats cache rate
type: ENH
priority: P2
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
discovered_by: ll-issues-create
labels:
- observability
- multi-host
blocked_by:
- ENH-3532
- ENH-3651
relates_to:
- ENH-3543
- ENH-3546
- ENH-3534
- ENH-3649
---

# ENH-3549: Consume stored usage for ll-ctx-stats cache rate

## Summary

Replace `ll-ctx-stats`'s transcript-parsing cache-rate helper with a read-only consumer of stored normalized `usage_events` observations through `select_usage_observations`, preserving the existing latest-session/workspace/host selection and propagating stored provenance and coverage qualification.

**Split 2026-09-28:** the reader-isolation gate, `ll-ctx-stats` empty-discovery diagnostics, spike promotion and read-side fake-host coverage moved to ENH-3649 (unblocked), together with the spike results and isolation research. The dependency on ENH-3534 was dropped: Claude transcript rows are already backfilled today, Codex rows arrive with ENH-3532, and ENH-3534 only widens host coverage. The old confidence scores covered the pre-split scope and were removed; re-score after the freshness gate below is decided.

## Current Behavior

- `ctx_stats._compute_cache_rate_from_jsonl(cwd, host)` takes the latest discovered handle; for Codex it calls `_codex_cache_usage` (reads the live rollout via `iter_events`), for every other host it opens `handle.path` directly and sums assistant `message.usage` with a local `seen_uuids` dedup. Non-Codex figures are labelled `provenance: "unknown"`.
- `select_usage_observations` (`history_reader/usage.py`) streams every `usage_events` row; its only filters are `since` and `require_run_id`. There is no session filter.
- `usage_events` transcript rows are derived only by `rebuild()` (`_backfill_usage_events`, called from `session_store/lifecycle.py` in that one place). The SessionStart hook spawns a detached `backfill_worker` (not a daemon thread) that runs `backfill_incremental`, which is ingest-only (`raw_events`); it passes `--rebuild` only when `SCHEMA_VERSION` has advanced past `last_rebuild_version`. Stored transcript usage is therefore stale until a schema bump or a manual rebuild, and the current session is never present (correction 2026-09-29; ENH-3651 owns the fix).

## Expected Behavior

Cache-rate accounting reads persisted observations for the selected session through `select_usage_observations(..., host=handle.host, session_id=handle.session_id)`, preserving the latest eligible session, host/workspace scope and agent exclusion. It never widens to all-session totals, infers zeros, parses transcripts, or backfills during a read. Stored provenance (ENH-3546 for Claude, ENH-3532 for Codex) and coverage qualification (ENH-3543, or the unreconciled-sum contract before it) pass through unchanged. Unverified/NULL host identity is not attributed to the selected host merely because its session ID matches.

For a discovered session without stored eligible usage, the result is unavailable with a stderr diagnostic that distinguishes: no store, unreadable store, selected session not yet ingested, and session ingested but without usage. Missing fields are unknown; nothing is labelled estimated without an estimator.

### Freshness decision and cutover gate

ENH-3651 owns hook-driven ingest, initial catch-up of already-ingested raw rows and incremental derivation. This issue adds no `--ingest` flag: ordinary reads remain pure, and an unavailable result gives the existing manual backfill guidance. A raw-transcript fallback would reintroduce the second token parser this issue removes.

Before the Claude or Codex direct reader is retired, an end-to-end fixture must prove that host's selected current session is ingested, derived and readable with the required freshness. ENH-3651 initially targets a Claude Code hook; the remaining hosts without a proven stored producer/trigger are explicitly unavailable, with a diagnostic, until their producer path is wired under ENH-3534 or a linked host-specific issue. That limitation is part of this staged cutover and is not counted as completed eight-host coverage. The Codex path additionally requires ENH-3532's rollout normalizer and ENH-3651's rollout derive; a full-rebuild-only test does not satisfy its cutover gate.

### Staging: Claude first

The `blocked_by: ENH-3532` edge is needed only for Codex (it retires `_codex_cache_usage`, which reads live rollouts). The Claude path (stored consumer, paired host/session filter, diagnostics) can ship first after ENH-3651 makes stored transcript usage current. Codex switches over only after ENH-3532 and ENH-3651 pass the combined ingest → incremental derive → read fixture; landing ENH-3532 alone is insufficient.

### Which session id

`select_usage_observations(host=..., session_id=...)` must receive the handle's verified host and the same ID the stored rows carry. For Codex, that is the **thread** ID (`payload.id`), which is what `SessionHandle` and `raw_events.session_id` use; a subagent then reads its own rows, not its parent's. Do not hand the filter a root/`payload.session_id` value. A same-ID row from another host must not enter the selected session's totals.

## Scope Boundaries

- **In scope**: the stored-usage cache-rate consumer; the paired host/session selector filter (shared with ENH-3543 — whichever lands first adds it); missing/unreadable/not-ingested diagnostics; per-host cutover tests.
- **Out of scope**: reader isolation gate, empty-discovery diagnostics and fake-host coverage (ENH-3649); producer eligibility (ENH-3532/3534/3546); live/rollout reconciliation (ENH-3543); token normalization.

## Program Design

### Types

- Reuse the stored observation/provenance contract and `SessionHandle`; no new token-accounting type.

### Signatures

- `_compute_cache_rate_from_usage(cwd: Path, host: str | None, *, db: Path | str | None = None) -> dict | None` — stored-observation consumer. Preserve existing numeric keys and add qualification from stored observations. Retire `_compute_cache_rate_from_jsonl` and `_codex_cache_usage` and update their callers/tests; any temporary compatibility wrapper delegates to the stored consumer and never parses transcripts.
- `select_usage_observations(conn, *, since=None, require_run_id=False, host=None, session_id=None)` — additive paired filter; a `session_id` requires `host`, and candidate coverage is reconciled before report filtering (ENH-3543 § Session filter).

### Call Path

- `main_ctx_stats` → `detect_sessions` → latest `SessionHandle` → read-only history connection → `select_usage_observations(host=handle.host, session_id=handle.session_id)` → cache components + provenance.
- Missing/unreadable/not-ingested usage → distinct stderr diagnostic → unavailable cache result.

### Decision Rules

Preserve latest eligible session and host/workspace scope, and exclude agent records as before. Usage deduplication belongs to persisted identity/coverage policy, not a reader-local UUID filter: drop `seen_uuids`.

## Integration Map

- `scripts/little_loops/cli/ctx_stats.py` — replace the transcript helper; emit diagnostics outside the numeric helper.
- `scripts/little_loops/history_reader/usage.py` — `session_id` filter on `select_usage_observations`.
- `scripts/little_loops/token_provenance.py` — reuse `counted_entry`, `json_pointer`, `format_figure`, `footnotes`.
- Freshness implementation lives in ENH-3651 (`hooks/hooks.json`, a lifecycle handler and the session-store derive entry point); this issue tests the reader-side cutover.
- Tests: `test_cli_ctx_stats.py`, `test_enh3528_token_provenance.py` (seed normalized usage via the store; do not weaken Qwen/Gemini expectations just because older parsers stripped usage), `test_history_reader_usage.py`, `test_usage_selection_chokepoint_gate.py`.
- Docs: `docs/reference/CLI.md` (stored-usage selection, not-yet-ingested case, backfill guidance, stderr diagnostics), `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md` (do not claim non-Codex hosts stay unknown after their producer contracts land).

## Implementation Steps

1. Pin existing latest-session/host/agent selection and cache result semantics in store-backed tests, including same-ID rows from two hosts.
2. Add the paired host/session filter (if ENH-3543 has not) and the stored-observation consumer. Retire the Claude and Codex direct readers after their respective end-to-end current-session cutover tests pass; report other hosts' missing stored observations as unavailable until their producer paths land.
3. Add the four distinguishable diagnostics; verify ENH-3651's freshness and Codex rollout derive path, update docs, and run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 — closes the last raw token-accounting bypass.
- **Effort**: Small to medium for the reader; ENH-3651 owns the larger freshness/derive work.
- **Risk**: Medium — latest-session selection, freshness and missing-store behavior must stay consistent.
- **Breaking Change**: No CLI option change; un-ingested usage becomes explicitly unavailable instead of silently parsed from disk. Claude and Codex current-session paths require a proven stored replacement before cutover; other hosts await ENH-3534 or a linked issue and may temporarily lose a direct-parsed cache figure.

## Acceptance Criteria

- [ ] Cache-rate reporting uses stored normalized observations via `select_usage_observations(host=..., session_id=...)`, preserving producer provenance and coverage qualification; same-ID rows from another host are excluded, and no host-wide unknown override or direct transcript accounting remains.
- [ ] Existing Codex/Claude latest-session, workspace and agent selection stays equivalent (store-backed tests).
- [ ] No store, unreadable store, selected session not ingested, and ingested-without-usage produce distinct stderr diagnostics; `--json` stdout stays parseable; report reads do not mutate ingestion state (unless option B's explicit flag is passed).
- [ ] Current-session ingest → derive → read fixtures pass for Claude and Codex before their direct readers are retired; Codex includes rollout incremental derivation. Other hosts lacking a proven producer/trigger are explicitly unavailable and documented as such, with the ENH-3534 follow-up linked.
- [ ] Missing/partial components stay unknown; nothing is labelled estimated without an estimator.

## Preserved Research Context

_From `/ll:refine-issue` 2026-09-25; isolation-gate and fake-host findings moved to ENH-3649._

- **Payload shape is host-dependent.** `claude-code`, `codex`, `kimi-code` yield host-native records; `qwen`, `gemini`, `omp` yield normalizer output (Claude-shaped, `message.usage` stripped); `opencode`, `pi` share the Claude loop. Codex `payload` is the inner payload of a `response_item`/`event_msg` record. Evidence: `sessions.py` "Payload rule (ENH-3420)", `_PARSERS`.
- **UUID dedup lives only in the `ctx_stats` single-session reader** (`seen_uuids`; `test_deduplicates_by_uuid`). `_codex_cache_usage` does not dedup; `usage_events` backfill dedups via `raw_events` `(source_path, line_no)`. The stored-usage reader delegates identity/coverage to the shared selector.
- **Home isolation for ctx-stats tests**: CLI-level tests patch `Path.home` (`test_cli_ctx_stats.py:test_resolves_qwen_chats_transcript`); unit tests patch the seam call site with a hand-built `SessionHandle` (helper `_handle`). `ctx_stats` imports `detect_sessions` at module level, so the patch target is `little_loops.cli.ctx_stats.detect_sessions`.
- **Reusable helpers:** `token_provenance` (already imported by `ctx_stats`), `ctx_stats._known_int`, `sessions.handles_from_paths`/`session_id_for`.

## Session Log
- `/ll:refine-issue` - 2026-09-25T01:49:59 - `2a69c442-43f4-408a-839a-d32ff801a6aa.jsonl`
- `/ll:decide-issue` - 2026-09-25T01:45:38 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:spike` - 2026-09-25T01:44:07 - `d516d85d-c844-46f9-818c-1329a5ea8e8a.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:41:16 - `e0edff4d-cab8-40c4-ab83-ef8eab746346.jsonl`
- `/ll:wire-issue` - 2026-09-25T01:20:25 - `d7aee0ef-9942-42c4-9fcc-7d8d7c2a43ed.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:12:50 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:format-issue` - 2026-09-25T01:06:51 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:02:51 - `f35cbaf1-740e-46e5-84c9-0ecf04a645f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T23:55:45 - `2bb94109-d967-427c-a647-9b0a7a8e368e.jsonl`

---

## Status

**Open** | Created: 2026-09-24 | Priority: P2
