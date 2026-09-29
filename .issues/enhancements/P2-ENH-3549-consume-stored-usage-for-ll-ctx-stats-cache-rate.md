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
- ENH-3656
relates_to:
- ENH-3543
- ENH-3546
- ENH-3534
- ENH-3649
- ENH-3656
---

# ENH-3549: Consume stored usage for ll-ctx-stats cache rate

## Summary

Finish `ll-ctx-stats`'s move to a read-only consumer of stored normalized `usage_events` observations through `select_usage_observations`. ENH-3656 ships the Claude Code path and shared paired host/session filter first. This issue cuts over Codex only after its producer and current-session trigger are proven, then retires the remaining direct transcript accounting paths with explicit unavailable results where stored producers are absent.

**Splits:** the reader-isolation gate, empty-discovery diagnostics and read-side fake-host coverage moved to ENH-3649 on 2026-09-28. The Claude stored-reader stage moved to ENH-3656 on 2026-09-29 so its work is not hard-blocked by Codex ingestion. ENH-3534 only widens host coverage and is not a blocker for this issue; unsupported current-session hosts remain explicitly unavailable. The old confidence scores covered the pre-split scope and were removed; re-score after the Codex freshness gate below is decided.

## Current Behavior

- `ctx_stats._compute_cache_rate_from_jsonl(cwd, host)` takes the latest discovered handle; for Codex it calls `_codex_cache_usage` (reads the live rollout via `iter_events`), for every other host it opens `handle.path` directly and sums assistant `message.usage` with a local `seen_uuids` dedup. Non-Codex figures are labelled `provenance: "unknown"`.
- `select_usage_observations` (`history_reader/usage.py`) streams every `usage_events` row; its only filters are `since` and `require_run_id`. There is no session filter.
- `usage_events` transcript rows are derived only by `rebuild()` (`_backfill_usage_events`, called from `session_store/lifecycle.py` in that one place). The SessionStart hook spawns a detached `backfill_worker` (not a daemon thread) that runs `backfill_incremental`, which is ingest-only (`raw_events`); it passes `--rebuild` only when `SCHEMA_VERSION` has advanced past `last_rebuild_version`. Stored transcript usage is therefore stale until a schema bump or a manual rebuild, and the current session is never present (correction 2026-09-29; ENH-3651 owns the fix).

## Expected Behavior

After ENH-3656 establishes the Claude stored reader, extend cache-rate accounting to Codex through `select_usage_observations(..., host=handle.host, session_id=handle.session_id)`, preserving latest eligible session, workspace/host scope and agent exclusion. Finish removing other direct transcript token accounting. The read never widens to all-session totals, infers zeros, parses transcripts, or backfills. Stored provenance (ENH-3546 for Claude, ENH-3532 for Codex), coverage qualification (ENH-3543, or the unreconciled-sum contract before it), and ENH-3656's as-of/staleness qualification pass through unchanged. Unverified/NULL host identity is not attributed to the selected host merely because its session ID matches.

Reuse ENH-3656's distinct stderr diagnostics for no store, unreadable store, selected session not yet ingested, and session ingested but without usage. A previously stored value with unproven current-session freshness is stale or has explicit unknown lag, never silently current. Missing fields are unknown; nothing is labelled estimated without an estimator.

### Freshness decision and cutover gate

ENH-3651 owns hook-driven ingest, initial catch-up of already-ingested raw rows and incremental derivation. ENH-3656 owns the shared read-side as-of/staleness contract. This issue adds no `--ingest` flag: reads remain pure, and an unavailable result gives manual backfill guidance. A raw-transcript fallback would reintroduce the second token parser this issue removes.

Before retiring `_codex_cache_usage`, this issue wires a real Codex lifecycle trigger to ENH-3651's shared worker and brings the selected current session through ingest → incremental derive → stored read with the required as-of qualification. Name the trigger, verify its event timing and transcript/rollout path, and test the actual adapter-to-worker path; a manually invoked worker or full-rebuild-only fixture is insufficient. ENH-3532's rollout normalizer and ENH-3651's rollout derive are both required. If Codex has no proven trigger, retain its direct reader and leave this issue open; do not declare a Codex stored-reader cutover complete. Other hosts without a proven stored producer/trigger are explicitly unavailable only when their direct reader is retired under this issue or a linked host-specific issue; that limitation is not completed eight-host coverage.

### Staging and issue ownership

ENH-3656 owns the Claude path, paired host/session filter and diagnostics after ENH-3651 makes stored transcript usage current. This issue's `blocked_by` edges now describe only the final Codex/remaining-host cutover: ENH-3532 (rollout producer), ENH-3651 (shared incremental derive and Claude trigger), and ENH-3656 (shared stored reader). This issue owns the Codex trigger. ENH-3543 may land before either reader stage; whichever of ENH-3543/ENH-3656 lands first adds the shared filter, and this issue reuses it.

### Which session id

`select_usage_observations(host=..., session_id=...)` must receive the handle's verified host and the same ID the stored rows carry. For Codex, that is the **thread** ID (`payload.id`), which is what `SessionHandle` and `raw_events.session_id` use; a subagent then reads its own rows, not its parent's. Do not hand the filter a root/`payload.session_id` value. A same-ID row from another host must not enter the selected session's totals.

## Scope Boundaries

- **In scope**: Codex stored-reader cutover, final retirement of remaining direct transcript token accounting, reuse of the paired host/session filter and diagnostics, and per-host cutover tests.
- **Out of scope**: Claude reader/filter/diagnostic implementation (ENH-3656), reader isolation and empty-discovery diagnostics (ENH-3649), producer eligibility (ENH-3532/3534/3546), live/rollout reconciliation (ENH-3543), token normalization.

## Program Design

### Types

- Reuse the stored observation/provenance contract and `SessionHandle`; no new token-accounting type.

### Signatures

- `_compute_cache_rate_from_usage(cwd: Path, host: str | None, *, db: Path | str | None = None) -> dict | None` — supplied for Claude by ENH-3656 and extended to Codex here. Preserve numeric keys and qualification. Retire `_codex_cache_usage` only after its runtime cutover test; retire the remaining direct transcript helper when no supported host still needs it.
- `select_usage_observations(conn, *, since=None, require_run_id=False, host=None, session_id=None)` — paired filter supplied by ENH-3656 or ENH-3543 and reused here; a `session_id` requires `host`, and candidate coverage is reconciled before report filtering (ENH-3543 § Session filter).

### Call Path

- `main_ctx_stats` → `detect_sessions` → latest `SessionHandle` → read-only history connection → `select_usage_observations(host=handle.host, session_id=handle.session_id)` → cache components + provenance.
- Missing/unreadable/not-ingested or stale usage → ENH-3656's diagnostic/qualification contract → unavailable or explicitly stale cache result.

### Decision Rules

Preserve latest eligible session and host/workspace scope, and exclude agent records as before. Usage deduplication belongs to persisted identity/coverage policy, not a reader-local UUID filter: drop `seen_uuids`.

## Integration Map

- `scripts/little_loops/cli/ctx_stats.py` — replace the transcript helper; emit diagnostics outside the numeric helper.
- `scripts/little_loops/history_reader/usage.py` — reuse ENH-3656/ENH-3543's `session_id` filter; extend only if Codex coverage selection requires it.
- `scripts/little_loops/token_provenance.py` — reuse `counted_entry`, `json_pointer`, `format_figure`, `footnotes`.
- `scripts/little_loops/hooks/adapters/codex/hooks.json` and its handler — choose a lifecycle event that fires after the usage is available, passes the verified current rollout path, and starts ENH-3651's detached worker without turn latency. A pre-turn-only event cannot certify the just-completed turn.
- Freshness writing lives in ENH-3651; shared reader qualification lives in ENH-3656. This issue tests Codex's real trigger and reader-side cutover.
- Tests: `test_cli_ctx_stats.py`, `test_enh3528_token_provenance.py` (seed normalized usage via the store; do not weaken Qwen/Gemini expectations just because older parsers stripped usage), `test_history_reader_usage.py`, `test_usage_selection_chokepoint_gate.py`.
- Docs: `docs/reference/CLI.md` (stored-usage selection, not-yet-ingested case, backfill guidance, stderr diagnostics), `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md` (do not claim non-Codex hosts stay unknown after their producer contracts land).

## Implementation Steps

1. Reuse ENH-3656's store-backed selection and diagnostics; pin the existing Codex latest-session/host/agent and same-ID cross-host behavior.
2. Verify a real Codex lifecycle trigger and transcript/rollout path through ENH-3651's worker, ENH-3532's normalizer, incremental derive and selected read. Retire `_codex_cache_usage` only after this passes.
3. Remove other direct transcript token accounting only with explicit per-host stored availability/unavailability behavior; update docs and run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 — closes the last raw token-accounting bypass.
- **Effort**: Small to medium for the final reader cutover; ENH-3651 and ENH-3656 own the derive and Claude foundation.
- **Risk**: Medium — latest-session selection, freshness and missing-store behavior must stay consistent.
- **Breaking Change**: No CLI option change; after a host's direct parser is retired, un-ingested usage becomes explicitly unavailable instead of silently parsed from disk. Codex requires a proven runtime stored replacement; other hosts await ENH-3534 or a linked issue.

## Acceptance Criteria

- [ ] Codex cache-rate reporting uses stored normalized observations via `select_usage_observations(host=..., session_id=...)`, preserving producer provenance, coverage and as-of qualification; same-ID rows from another host are excluded.
- [ ] Existing Codex latest-session, workspace and agent selection stays equivalent (store-backed tests); ENH-3656's Claude path remains unchanged.
- [ ] Reuse ENH-3656's four distinct diagnostics and stale/unknown-lag behavior; `--json` stdout stays parseable and reads do not mutate ingestion state. No `--ingest` flag exists.
- [ ] A real Codex hook → ingest → incremental derive → read fixture passes before `_codex_cache_usage` is retired, including current-session freshness after a completed turn. A manual worker/full-rebuild-only test does not satisfy this criterion; a missing trigger leaves the direct Codex reader in place and this issue open.
- [ ] Other hosts lacking a proven stored producer/trigger are explicitly unavailable only when their direct parser is retired, documented as such, and linked to ENH-3534 or a host-specific follow-up. No host-wide unknown override or direct transcript token accounting remains when this issue is done.
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
