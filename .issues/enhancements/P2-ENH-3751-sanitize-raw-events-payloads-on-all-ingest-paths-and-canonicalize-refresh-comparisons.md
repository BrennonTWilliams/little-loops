---
id: ENH-3751
title: Sanitize raw_events payloads on all ingest paths and canonicalize refresh comparisons
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
parent: ENH-3743
blocked_by:
- ENH-3750
labels:
- security
- privacy
- history
decision_needed: false
---

# ENH-3751: Sanitize raw_events payloads on all ingest paths and canonicalize refresh comparisons

## Summary

Wire the ENH-3750 policy into all three raw-event SQL insert sites before serialization, compression, or remote queuing. Use the same canonical policy for source certification and conservative refresh, preserving nonsecret fields, replay attribution, and physical source proofs.

## Current Behavior

Verified on branch `main` on 2026-10-05:

- `lifecycle._backfill_raw_events` serializes `event.payload` once and supplies the same packed bytes to local `execute` or remote `_REMOTE_RAW_INSERT`/`executemany`; neither redacts. Remote chunks are 200 events and may commit independently.
- Claude `refresh_usage_source` has a separate insert from the original decoded record. Codex delegates inserts to `_backfill_raw_events`, but first-cursor certification compares unpacked stored `raw_line` directly to the parser payload.
- `usage_refresh._event_signature` and `_stored_signatures` compare original payloads, with stored signatures reading only `raw_line`. `_preserves_fields` rejects field/value loss. The unchanged short-circuit compares the two unpacked column strings; a final signature check verifies inserts.
- Refresh operations are SQLite-only today. Their source replacement/usage cursor operations use local transactions; the remote-capable insert path is `backfill_raw_events`/`backfill_incremental`. Remote `commit`/`rollback` cannot undo previously committed batches.
- Direct derived-table writers can read original files; sanitizing these raw columns does not sanitize every history table or original transcript.

## Expected Behavior

- New payload inserts are sanitized by default, once per event, before JSON serialization, packing, or adding bytes to an outbound remote batch. Both new columns get identical sanitized bytes. Pass the source's verified `host` and `event.type` to the sanitizer; Claude's separate path uses `host='claude-code'` and the original record's type.
- Build relational metadata and producer qualification from the original verified event, retaining the exact session/source/line/ordinal/type/timestamp/usage-contract behavior. The policy must preserve required payload fields so replay from sanitized rows gives the same identities, counters, and qualification.
- Certification and refresh compare canonical sanitized payloads with the same context on both sides. Keep structural attribution checks and `_preserves_fields` active. Include both stored columns in preservation/parity decisions; never overwrite a nonsecret field unique to `parsed_json` merely because `raw_line` matches the source.
- An unchanged source is a no-op after canonicalization, including legacy plaintext vs redacted rows and historical differences caused solely by supported secret spans. This certifies semantic compatibility, not storage compliance. Existing plaintext rows are upgraded explicitly by ENH-3752's maintenance command; canonical equality alone must not claim they were scrubbed.
- If a legitimate parser upgrade adds fields while retaining every canonical field in either stored column, refresh may replace both with the sanitized source payload. Divergence that would lose nonsecret data refuses replacement. Nonsecret value changes, missing keys, or changed list positions/lengths remain refusal conditions.
- Policy extensions work when source/stored representations reach the same current fixed point and historical placeholders remain recognized. An incompatible policy change refuses safely rather than disabling field checks.
- On sanitizer failure, reject the affected operation; do not persist originals, placeholder substitute payloads, silently skip the event, advance its cursor, or publish a success watermark. Local operations roll back; committed remote chunks may remain and must contain only sanitized rows. A retry uses existing dedup and the unchanged success boundary.

## Motivation

Persisting redacted rows without changing equality checks would break Codex first-use certification and source refresh. Making those checks canonical preserves replay while giving the explicit cleanup command a compatible storage baseline.

## Proposed Solution

Use the ENH-3750 result payload at the shared serialization site in `_backfill_raw_events` and at Claude's separate insert. Keep original event objects for metadata/qualification and source-byte proofs. Counts are not persisted as new metadata in this issue.

Add a small internal canonicalization helper in `usage_refresh` taking decoded payload plus `host`/`event_type`; both source and stored signatures use it. For rows, context comes from relational host/event type, not ambient configuration or a user-controlled nested discriminator. Canonicalize both payload columns independently and apply `_preserves_fields` to each before any source delete. The unchanged test compares decoded canonical objects, not compressed bytes or incidental JSON whitespace/order. The post-insert check must still prove the new rows and both columns match the expected sanitized source representation.

Use the same policy/context in `_refresh_codex_usage_source` first-cursor certification; include stored column parity rather than certifying only `raw_line`. Leave line coverage, attribution, inode/device, offsets, raw-byte tail digests, and final file-change witnesses intact. Neither canonicalization nor maintenance changes what those witnesses prove.

Handle `HistorySanitizationError` with content-free reason diagnostics. Local `backfill_raw_events`, both usage-refresh branches, and source refresh must release connections and roll back on failure; test failure after at least one candidate insert and after source replacement starts. Remote failure after a committed chunk stops before the watermark write, discards unflushed candidates, and is recoverable through ordinary retry/dedup. Do not promise rollback across remote chunks. The rejected source may remain blocked until its unsafe content/structure is resolved; that is intentional, not a reason to fabricate a replay record.

## Program Design

### Signatures

Consume the new policy API supplied by ENH-3750:

```python
sanitize_history_payload(payload, *, host=None, event_type=None) -> HistoryRedactionResult
```

Proposed internal helper:

```python
def _canonical_payload(
    payload: dict[str, Any], *, host: str | None, event_type: str | None
) -> dict[str, Any]: ...
```

Existing `_event_signature(event, handle)`, `_stored_signatures(rows)`, `_preserves_fields(stored, parsed)`, `SourceRefresh`, and `RefreshResult` remain private/current compatibility surfaces. Add context handling without changing public refresh/backfill signatures. Keep `lifecycle._backfill_raw_events` a module attribute with its existing positional call shape for callers/tests.

### Call Path

`backfill_raw_events` / `backfill_incremental` / `refresh_raw_events` / `_refresh_codex_usage_source` -> `_backfill_raw_events` -> sanitizer with verified event context -> serialize -> pack -> local insert or bounded remote insert batch.

Claude `refresh_usage_source` -> decode original record -> qualification/metadata plus sanitizer -> serialize/pack -> insert -> derive -> success boundary.

`refresh_raw_events` -> canonical source plus both stored columns -> structural/preservation checks -> unchanged OR transactional sanitized replacement -> post-insert parity. Codex first-cursor certification uses the same policy before publishing a cursor.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — shared/local/remote serialization, Claude insert, Codex certification, failure cleanup.
- `scripts/little_loops/session_store/usage_refresh.py` — context-aware signatures, both-column preservation, canonical no-op and post-insert verification.
- Comment-only updates: `scripts/little_loops/session_store/qwen.py`, `writers.py`, and `schema.py` where wording claims verbatim/JSON-equal raw payloads. DDL is unchanged.

### Dependent Files and Similar Patterns

- `scripts/little_loops/session_store/sessions.py`, `claude_usage.py`, and replay consumers in `writers.py` define payload shapes and attribution; preserve their function behavior.
- `scripts/little_loops/cli/backfill_worker.py` inherits policy via backfill/usage refresh; it prints exception text, so verify safe reason-only errors at this boundary too.
- `scripts/little_loops/session_store/libsql.py` / `hrana.py` provide atomic per-chunk remote insertion; do not broaden remote refresh support.
- Rebuild fingerprints cover reachable replay functions. Add sanitization only at ingestion/comparison seams, not in `_unpack_payload`, `_iter_events*`, or rebuild-reachable `_backfill_*` consumers. `_backfill_raw_events` is the required insert seam, not a blanket prohibition on all `_backfill_*` names. If replay function bodies must change, bump `REBUILD_DERIVE_VERSION` and regenerate the existing fingerprint deliberately.

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| `lifecycle.py` | Dedup/positions/metadata, byte proofs, qualification, chunking, cursor boundaries | Sanitize all insert payloads; canonicalize Codex certification; explicit safe rollback | Original matched spans in newly inserted raw payloads |
| `usage_refresh.py` | Conservative source/field loss checks, per-source transaction, unchanged no-op | Compare canonical objects/context and preserve both stored columns | Reliance on original secret bytes for equality |
| Replay/compression/schema modules | Replay logic, compression codec, DDL and derive fingerprint | Comments describe redacted normalized payloads | None |

### Tests

- `scripts/tests/test_session_store_lifecycle.py` — local insert/replay/dedup, TEXT/BLOB mixed rows, context forwarding, original object immutability, failure after a preceding insert with no watermark advancement.
- `scripts/tests/test_remote_ingestion_telemetry.py` — inspect outbound/decompressed params from the public raw-ingest API; every supported rule family, failure after a committed 200-row chunk, retry with unchanged watermark and stable dedup. Keep `test_inserts_are_batched_not_one_round_trip_per_event` under 20 requests.
- `test_session_store_incremental_usage.py`, `test_enh3549_codex_usage_refresh.py`, `test_session_store_usage_refresh.py`, `test_ll_session_refresh.py` — all three insert sites; first-cursor and later append; unchanged sanitized/mixed legacy no-op; policy-extension fixed point; both-column secret-only divergence vs real field/value loss; failure rollback and source overwrite/truncation proofs.
- Update assertions in `test_enh_omp_normalizer.py` / `test_enh3532_codex_rollout_usage.py` only for supported redacted spans; do not weaken whole-payload equality to key-presence checks. The existing Codex interactive fixture email should become `[EMAIL]` in storage.
- Regression: `test_enh3731_usage_qualification.py`, `test_enh3656_stored_cache_rate.py`, `test_enh3549_codex_stored_ctx_stats.py`, `test_bug3736_usage_replay_holds.py`, and `test_enh3678_rebuild_derive_gate.py`.
- Cross-host ingest -> rebuild parity checks compare identities, tool linkage and usage totals/qualification with the original payload's expected values; nested reasoning/tool strings, arrays and Unicode escapes receive leak checks. Capture CLI/worker stderr and formatted tracebacks with a secret canary.

### Documentation

`docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/CLI.md`, and `docs/reference/CONFIGURATION.md`: default-on raw-column coverage, semantic refresh no-op vs explicit legacy cleanup, fail-safe rejected sources, remote chunk boundary, and preserved replay/source proofs. Mention that direct derived writers and originals are outside this guarantee. Use end-user wording in guides/reference docs.

### Configuration

No opt-out, policy-version column, schema migration, or new dependency. Existing history target configuration/dedup stays unchanged.

## Implementation Steps

1. Add insert/context/failure tests for the shared local/remote path and separate Claude insert.
2. Wire sanitization before serialization/packing and ensure rollback/watermark boundaries remain safe.
3. Add canonical source/stored comparisons, both-column preservation, and Codex certification tests, including legacy no-op and extension behavior.
4. Verify replay/usage/tool-linkage parity, update contradictory comments/docs, run focused regressions and the full local suite.

## Acceptance Criteria

- [ ] Each of the three SQL sites uses the same context-aware policy; decompressed stored/outbound columns contain no planted supported match and new columns have identical bytes, with nested/array/escaped fixtures.
- [ ] Replay identities, usage totals/qualification, tool linkage and dedup are stable; source byte digests/offset/inode/line/watermark contracts remain intact.
- [ ] Canonical Codex certification and refresh accept sanitized/mixed legacy rows and compatible policy extensions; unchanged is no-write and explicitly does not scrub legacy plaintext.
- [ ] Both stored columns participate in field preservation; true nonsecret field/value/list loss still refuses before writes; successful replacement/post-check uses the sanitized source in both columns.
- [ ] Local failures roll back and remote failures publish no success boundary; prior committed remote chunks are sanitized and retry deduplicates safely; errors/tracebacks contain no canary secret.
- [ ] Relevant docs, focused regressions, rebuild-fingerprint gate, and `python -m pytest scripts/tests/` pass.

## Scope Boundaries

Raw payload inserts and certification/refresh comparisons only. No historical cleanup here, blanket derived/FTS redaction, opaque decoding, schema migration, remote source replacement, automatic skip/placeholder substitution on sanitizer failure, or redefinition of physical source proofs. ENH-3752 supplies explicit stored-row maintenance after this issue lands.

## Impact

- **Priority**: P2 — prevents new supported secret persistence and is required before stored-row cleanup can safely ship.
- **Effort**: Medium — three insert sites plus several conservative comparison/failure paths and replay tests.
- **Risk**: Medium — equality/cursor mistakes could block ingestion or weaken refresh checks; context/parity and rollback tests cover these boundaries.
- **Breaking Change**: Matched raw payload strings become placeholders; public APIs and usage semantics remain compatible.

## Review Notes

Reviewed on `main`, 2026-10-05, with `/ll:advise` using `claude-opus-5-5`. Distinguished semantic certification from storage compliance, required preservation of both columns, and made local rollback/remote partial-commit behavior explicit. Fail-safe source rejection is retained deliberately; a placeholder payload would not preserve replay. ENH-3752 now waits for this compatibility wiring.

## Blocked By

- ENH-3750

## Blocks

- ENH-3752

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
