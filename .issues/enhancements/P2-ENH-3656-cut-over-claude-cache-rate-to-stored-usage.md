---
id: ENH-3656
type: ENH
title: Cut over Claude cache rate to stored usage
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:07:13Z'
parent: EPIC-3562
epic: EPIC-3562
labels:
- observability
- multi-host
blocked_by:
- ENH-3651
relates_to:
- ENH-3543
- ENH-3546
- ENH-3549
- ENH-3649
blocks:
- ENH-3549
---

# ENH-3656: Cut over Claude cache rate to stored usage

## Summary

Cut over the Claude Code ll-ctx-stats cache-rate path to stored normalized usage after ENH-3651 provides current-session ingest and derivation. Establish numeric parity or document a fixture-backed correction before replacing the direct reader. Add the paired verified-host/session selector filter, diagnostics, as-of/staleness qualification, and an end-to-end current-session test. Keep the existing Codex direct rollout path until ENH-3549 completes its separately gated cutover.


## Current Behavior

`ll-ctx-stats` computes the Claude cache rate by opening the selected transcript and summing `message.usage` in `_compute_cache_rate_from_jsonl`. Its local `seen_uuids` set skips a repeated assistant UUID, whereas `_backfill_usage_events` currently writes every qualifying raw line. The direct reader accepts a usage block when any cache-rate component is present; backfill skips a block when both input and output are absent. These paths can disagree even with a fresh store. `select_usage_observations` has no paired host/session filter. Stored transcript usage is stale until `rebuild()`; ENH-3651 supplies incremental ingest and derive before this cutover.

## Expected Behavior

For the latest eligible Claude Code `SessionHandle`, read only persisted normalized observations via `select_usage_observations(host=handle.host, session_id=handle.session_id)`. Preserve workspace/host selection and agent exclusion. Require the verified host/session pair; same-ID rows from another host or unverified attribution never enter the result. Reads do not parse transcripts or mutate ingestion state.

### Numeric parity gate

Before retiring the direct reader, compare its numeric cache components, eligible/missing counts and hit rate with a stored read on the same versioned Claude fixtures. Include repeated assistant UUIDs, repeated `message.id` with distinct UUIDs, changed usage on a repeated ID, partial/cache-only usage, missing identity, explicit zero and a second completed turn. ENH-3546 supplies producer-grain evidence; ENH-3651 owns the shared full/incremental derive and observation key. The chosen rule may correct an existing direct-reader overcount, but any changed figure must be explained as an intentional, fixture-backed correction with a regression test and user-facing documentation. Do not declare position-key deduplication equivalent to producer observation deduplication. If the producer contract remains unknown, keep the direct path until the discrepancy is resolved rather than silently changing the reported number.

The result carries stored provenance and coverage qualification. Distinguish no store, unreadable store, selected session not yet ingested, and ingested-without-usage in stderr while keeping JSON stdout parseable. A stored value is not automatically current: expose its committed as-of boundary and report stale or unavailable when the selected source has advanced beyond derived progress. A read may inspect source metadata to determine lag, but does not parse usage or start ingestion. Unknown lag is explicit. ENH-3651 owns the write-side cursor/checkpoint needed to support this proof.

## Scope Boundaries

- **In scope**: Claude Code stored-usage reader, numeric-parity/correction gate, paired verified-host/session filter if ENH-3543 has not already added it, four stored-usage diagnostics, as-of/staleness qualification, and Claude current-session cutover tests.
- **Out of scope**: Codex cutover and removal of `_codex_cache_usage` (ENH-3549), live/rollout reconciliation (ENH-3543), producer qualification (ENH-3546), other-host producer/trigger implementation (ENH-3534).
- Preserve existing Codex and other-host direct-reader behavior until their separate cutovers; do not make a Claude-only trigger appear to provide all-host freshness.
- ENH-3649 independently owns the no-sessions discovery warning. Coordinate stderr wording and `--json` tests with its four stored-usage diagnostics; neither issue needs to block the other.

## Program Design

### Types

- Reuse `SessionHandle`, stored usage rows and existing provenance/coverage fields. Add reader-visible as-of/stale qualification only where ENH-3651's committed progress can support it.

### Signatures

- `_compute_cache_rate_from_usage(cwd: Path, host: str | None, *, db: Path | str | None = None) -> dict | None` — stored-observation consumer for the Claude path; ENH-3549 extends it to Codex and remaining hosts.
- `select_usage_observations(conn, *, since=None, require_run_id=False, host=None, session_id=None)` — additive paired filter. `session_id` without `host` is an error; verified candidate selection occurs before report-window filtering. Coordinate with ENH-3543 so only one shared filter is added.
- Freshness may use a global derive checkpoint plus source-specific cursors if they prove the selected session's committed tail. Otherwise ENH-3651 records a per-session completion boundary. Observation time alone is not a derive-completion marker.

### Call Path

- `main_ctx_stats` → `detect_sessions` → latest eligible Claude `SessionHandle` → read-only history connection → `select_usage_observations(host=handle.host, session_id=handle.session_id)` → cache components plus provenance/coverage/as-of qualification → text/JSON output and stderr diagnostic.

## Integration Map

- `scripts/little_loops/cli/ctx_stats.py` — route Claude cache-rate reporting through the stored consumer and emit diagnostics outside the numeric helper.
- `scripts/little_loops/history_reader/usage.py`, `token_provenance.py` — paired filter and shared qualification.
- `scripts/tests/test_cli_ctx_stats.py`, `test_history_reader_usage.py`, `test_enh3528_token_provenance.py` — direct-vs-stored numeric parity/correction, producer identity cases, store-backed selection, same-ID cross-host isolation, current-session freshness and stale-worker cases.
- `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md` — stored selection, as-of/stale wording and manual backfill guidance.

## Implementation Steps

1. Capture the needed versioned producer fixtures or reuse ENH-3546's if they have landed, then apply ENH-3651's observation-identity rule and compare direct and stored numeric results. Record parity or each deliberate correction before switching readers; ENH-3546's full provenance-promotion work is not a hard dependency.
2. After ENH-3651, prove Claude hook → ingest → incremental derive → read for the selected current session, including a successful second turn.
3. Add or reuse the paired host/session filter and route only Claude cache-rate reporting to the stored reader. Preserve the other hosts' existing paths.
4. Test all four stored-usage absence diagnostics, an appended source after a successful derive followed by worker failure, unknown lag, same-ID rows from another host, and JSON output. Coordinate the separate ENH-3649 empty-discovery warning and update docs.

## Impact

- **Priority**: P2 — enables a safe early stored-reader cutover without waiting for Codex rollout ingestion.
- **Effort**: Small to medium — reader and qualification work after ENH-3651.
- **Risk**: Medium — stale existing values, session-selection regressions and changed duplicate/partial-record semantics can mislead silently.
- **Breaking Change**: No CLI option change.

## Acceptance Criteria

- [ ] A Claude current-session hook → ingest → derive → read fixture passes before its direct transcript reader is retired; no read-time parsing or backfill remains on the Claude path.
- [ ] Direct and stored cache components, eligible/missing counts and hit rate match on versioned repeated-ID, partial/cache-only, missing-ID, zero and multi-turn fixtures, or each difference is a documented, producer-backed correction with a regression test. A source path/line key alone does not satisfy this criterion.
- [ ] Latest-session/workspace/host and agent selection and stored provenance/coverage are preserved. A session ID alone never joins another host's rows.
- [ ] No store, unreadable store, not-yet-ingested and ingested-without-usage have distinct stderr diagnostics; JSON stdout stays parseable.
- [ ] After an earlier successful derive, a newly appended source plus a failed/skipped worker cannot be reported as a fresh figure. Output includes a committed as-of boundary and explicit stale/unknown-lag qualification; reads do not mutate the store.
- [ ] The Codex and other-host paths keep their existing behavior until ENH-3549 or a host-specific cutover is implemented.

## Status

**Open** | Created: 2026-09-29 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-29T05:14:29 - `a56f3607-c825-4a5b-a7c5-f263b20ddf6d.jsonl`
