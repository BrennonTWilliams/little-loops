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

Cache-rate accounting reads persisted observations for the selected session through `select_usage_observations(..., session_id=...)`, preserving the latest eligible session, host/workspace scope and agent exclusion. It never widens to all-session totals, infers zeros, parses transcripts, or backfills during a read. Stored provenance (ENH-3546 for Claude, ENH-3532 for Codex) and coverage qualification (ENH-3543, or the unreconciled-sum contract before it) pass through unchanged.

For a discovered session without stored eligible usage, the result is unavailable with a stderr diagnostic that distinguishes: no store, unreadable store, selected session not yet ingested, and session ingested but without usage. Missing fields are unknown; nothing is labelled estimated without an estimator.

### Readiness gate: freshness of the current session

`ll-ctx-stats` usually reports on the latest session, which is usually the one still running and not yet ingested. A pure stored-usage consumer turns today's working figure into "unavailable" for the whole of the current session. Decide before implementation:

- **A. Hook-driven incremental ingest (recommended).** Add a Stop/PreCompact (or throttled PostToolUse) incremental backfill of the current transcript, reusing the SessionStart backfill path and its `(source_path, line_no)` idempotency. Reads stay pure and every stored-usage reader benefits. Cost: hook latency; must be non-blocking like the SessionStart daemon thread.
- **B. Explicit opt-in ingest flag.** `ll-ctx-stats --ingest` backfills the selected session before reading. Reads stay pure by default; the diagnostic tells the user to pass it.
- **C. Accept and document.** The current session is unavailable until the next SessionStart; the diagnostic names the cause and the backfill command.

A raw-transcript fallback for the un-ingested session is excluded: it reintroduces the second token parser this issue removes.

**Revised 2026-09-29 (supersedes the earlier "C now, B if cheap" recommendation).** Code review showed stored transcript usage is derived only by a full `rebuild()` (see Current Behavior), so options B and C are not viable on their own: C would turn today's working figure into "unavailable" for every session since the last rebuild, and B's `--ingest` flag would need an incremental derive, not just raw ingest. The incremental ingest+derive is therefore split into **ENH-3651** and this issue is `blocked_by` it; the choice here reduces to how the hook is triggered (owned by ENH-3651) and whether `ll-ctx-stats --ingest` is also offered as a manual escape hatch. Record the final choice here before implementation.

### Staging: Claude first

The `blocked_by: ENH-3532` edge is needed only for Codex (it retires `_codex_cache_usage`, which reads live rollouts). The Claude path (stored consumer, `session_id` filter, diagnostics) can ship first, after ENH-3651 makes stored transcript usage current and the session-id meaning is fixed below. Codex switches over when ENH-3532 lands.

### Which session id

`select_usage_observations(session_id=...)` must be called with the same id the stored rows carry. ENH-3532 gate 1 rule c recommends the **thread** id (`payload.id`), which is what `SessionHandle` and `raw_events.session_id` use, so the handle lookup and the filter agree; a subagent then reads its own rows, not its parent's. Do not hand the filter a root/`payload.session_id` value.

## Scope Boundaries

- **In scope**: the stored-usage cache-rate consumer; the `session_id` selector filter (shared with ENH-3543 — whichever lands first adds it); missing/unreadable/not-ingested diagnostics; the freshness decision and, for option A or B, its implementation.
- **Out of scope**: reader isolation gate, empty-discovery diagnostics and fake-host coverage (ENH-3649); producer eligibility (ENH-3532/3534/3546); live/rollout reconciliation (ENH-3543); token normalization.

## Program Design

### Types

- Reuse the stored observation/provenance contract and `SessionHandle`; no new token-accounting type.

### Signatures

- `_compute_cache_rate_from_usage(cwd: Path, host: str | None, *, db: Path | str | None = None) -> dict | None` — stored-observation consumer. Preserve existing numeric keys and add qualification from stored observations. Retire `_compute_cache_rate_from_jsonl` and `_codex_cache_usage` and update their callers/tests; any temporary compatibility wrapper delegates to the stored consumer and never parses transcripts.
- `select_usage_observations(conn, *, since=None, require_run_id=False, session_id=None)` — additive filter; reconciles before filtering (ENH-3543 § Session filter).

### Call Path

- `main_ctx_stats` → `detect_sessions` → latest `SessionHandle` → read-only history connection → `select_usage_observations(session_id=handle.session_id)` → cache components + provenance.
- Missing/unreadable/not-ingested usage → distinct stderr diagnostic → unavailable cache result.

### Decision Rules

Preserve latest eligible session and host/workspace scope, and exclude agent records as before. Usage deduplication belongs to persisted identity/coverage policy, not a reader-local UUID filter: drop `seen_uuids`.

## Integration Map

- `scripts/little_loops/cli/ctx_stats.py` — replace the transcript helper; emit diagnostics outside the numeric helper.
- `scripts/little_loops/history_reader/usage.py` — `session_id` filter on `select_usage_observations`.
- `scripts/little_loops/token_provenance.py` — reuse `counted_entry`, `json_pointer`, `format_figure`, `footnotes`.
- For freshness option A: `hooks/hooks.json`, a Stop/PreCompact handler under `scripts/little_loops/hooks/`, `session_store/lifecycle.py` backfill entry point.
- Tests: `test_cli_ctx_stats.py`, `test_enh3528_token_provenance.py` (seed normalized usage via the store; do not weaken Qwen/Gemini expectations just because older parsers stripped usage), `test_history_reader_usage.py`, `test_usage_selection_chokepoint_gate.py`.
- Docs: `docs/reference/CLI.md` (stored-usage selection, not-yet-ingested case, backfill guidance, stderr diagnostics), `docs/reference/API.md`, `docs/reference/HOST_COMPATIBILITY.md` (do not claim non-Codex hosts stay unknown after their producer contracts land).

## Implementation Steps

1. Decide the freshness gate and record it here.
2. Pin existing latest-session/host/agent selection and cache result semantics in store-backed tests.
3. Add the `session_id` filter (if ENH-3543 has not) and the stored-observation consumer; retire the transcript helpers.
4. Add the four distinguishable diagnostics; implement the chosen freshness option; update docs; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 — closes the last raw token-accounting bypass.
- **Effort**: Small to medium (medium with freshness option A).
- **Risk**: Medium — latest-session selection, freshness and missing-store behavior must stay consistent.
- **Breaking Change**: No CLI change; un-ingested usage becomes explicitly unavailable (or ingested, per the freshness decision) instead of silently parsed from disk.

## Acceptance Criteria

- [ ] Cache-rate reporting uses stored normalized observations via `select_usage_observations(session_id=...)`, preserving producer provenance and coverage qualification; no host-wide unknown override or direct transcript accounting remains.
- [ ] Existing Codex/Claude latest-session, workspace and agent selection stays equivalent (store-backed tests).
- [ ] No store, unreadable store, selected session not ingested, and ingested-without-usage produce distinct stderr diagnostics; `--json` stdout stays parseable; report reads do not mutate ingestion state (unless option B's explicit flag is passed).
- [ ] The freshness decision is recorded and tested: the current, still-running session behaves as decided.
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
