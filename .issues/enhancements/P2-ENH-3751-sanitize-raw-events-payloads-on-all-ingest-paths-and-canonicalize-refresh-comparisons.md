---
id: ENH-3751
title: Sanitize raw_events payloads on all ingest paths and canonicalize refresh comparisons
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
parent: ENH-3743
blocked_by: []
labels:
- security
- privacy
- history
decision_needed: false
size: Large
confidence_score: 95
verify_verdict: CLAIMS_OUTDATED
verify_evidence: 'Integration Map (wiring pass): ''docs/reference/CLI.md ll-session
  refresh flags and safety (:4635-4650)'' -> section now starts at line 4666 and spans
  to about 4695; Integration Map (wiring pass): ''recompress flags (:4693-4698), idempotent
  and byte-lossless'' -> section now starts at line 4717 with the byte-lossless sentence
  at line 4729; Integration Map (wiring pass): ''ll-session example block (~:4735-4754)''
  -> refresh/recompress examples now at lines 4769-4786; Documentation (Codebase Research
  Findings): ''CLI.md:4635-4659 documents ll-session refresh skip reporting'' -> refresh
  section now at lines 4666-4695'
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
risk_factors:
- id: broad-dependent-surface
  domain: outcome
  criterion: change_surface
  description: _backfill_raw_events has four callers plus the Claude insert, cli/session.py,
    cli/backfill_worker.py and two spawning hooks (6-10 dependents).
- id: codex-split-contract-churn
  domain: outcome
  criterion: ambiguity
  description: Contract has churned across critique rounds; the Codex first-cursor
    literal-vs-canonical split and rollback-scope rules are the likeliest places for
    iteration.
- id: cross-module-rollback-depth
  domain: outcome
  criterion: complexity
  description: Rollback/watermark boundaries, both-column preservation, per-line metadata
    refusal and NULL-to-marker qualification are shared-state logic across lifecycle.py
    and usage_refresh.py.
- id: ordered-refusal-sequence
  domain: outcome
  criterion: ambiguity
  description: Ordered refusals (holds, attribution, per-line metadata, qualification,
    decode, preservation) must be one explicit sequence; reordering changes the reported
    reason.
- id: rebuild-fingerprint-seam
  domain: outcome
  criterion: complexity
  description: Rebuild-fingerprint gate constrains where sanitization may be inserted;
    a misplaced seam forces a REBUILD_DERIVE_VERSION bump.
- id: stale-doc-line-refs
  domain: readiness
  criterion: issue_well_specified
  description: Integration Map cites CLI.md refresh/recompress/example line ranges
    that have drifted (verify_verdict CLAIMS_OUTDATED).
---

# ENH-3751: Sanitize raw_events payloads on all ingest paths and canonicalize refresh comparisons

## Summary

Wire the ENH-3750 policy into all three raw-event SQL insert sites before serialization, compression, or remote queuing. Use the same canonical policy for source certification and conservative refresh, preserving nonsecret fields, replay attribution, and physical source proofs.

## Current Behavior

Verified on branch `main` on 2026-10-05:

- `lifecycle._backfill_raw_events` serializes `event.payload` once and supplies the same packed bytes to local `execute` or remote `_REMOTE_RAW_INSERT`/`executemany`; neither redacts. Remote chunks are 200 events and may commit independently.
- Claude `refresh_usage_source` has a separate insert from the original decoded record. Codex delegates inserts to `_backfill_raw_events`, but first-cursor certification compares unpacked stored `raw_line` directly to the parser payload.
- `usage_refresh._event_signature` and `_stored_signatures` compare original payloads, with stored signatures reading only `raw_line`. `_preserves_fields` rejects field/value loss. The unchanged short-circuit compares the two unpacked column strings; a final signature check verifies inserts.
- Per-line metadata differences currently fall through to source replacement rather than refusal. Explicit source refresh also promotes a NULL `usage_contract` from the original file, including when the payload itself is unchanged; the existing stripped-usage recovery test relies on this qualification transition.
- Refresh operations are SQLite-only today. Their source replacement/usage cursor operations use local transactions; the remote-capable insert path is `backfill_raw_events`/`backfill_incremental`. Remote `commit`/`rollback` cannot undo previously committed batches.
- Direct derived-table writers can read original files; sanitizing these raw columns does not sanitize every history table or original transcript.

## Expected Behavior

- New payload inserts are sanitized by default, once per event, before JSON serialization, packing, or adding bytes to an outbound remote batch. Both new columns get identical sanitized bytes. Pass the source's verified `host` and `event.type` to the sanitizer; Claude's separate path uses `host='claude-code'` and the original record's type.
- Build relational metadata and producer qualification from the original verified event, retaining the exact session/source/line/ordinal/type/timestamp/usage-contract behavior. The policy must preserve required payload fields so replay from sanitized rows gives the same identities, counters, and qualification.
- Certification and refresh compare canonical sanitized payloads with the same context on both sides. Keep structural attribution checks and `_preserves_fields` active. Before canonicalizing payloads, match each existing line's timestamp/session/host/basis/ordinal/event type, rather than just checking session-ID sets. Treat usage qualification separately under the transition rule below. Include both stored columns in preservation/parity decisions; never overwrite a nonsecret field unique to `parsed_json` merely because `raw_line` matches the source.
- A source with matching relational metadata and qualification is a no-op after canonicalization, including legacy plaintext vs redacted rows and historical differences caused solely by supported secret spans. This certifies semantic compatibility, not storage compliance. Existing plaintext rows are upgraded explicitly by ENH-3752's maintenance command; canonical equality alone must not claim they were scrubbed.
- Explicit source refresh may promote a NULL usage contract to the marker justified by the original verified source, including recovery of stripped usage or a qualification-only upgrade. It must use full transactional replacement and report `refreshed`/`needs_rebuild`; it cannot take the unchanged branch or update the marker in place. A non-NULL marker cannot be removed or changed. Rebuild/replay still copies persisted qualification and never promotes it by re-evaluation.
- If a legitimate parser upgrade adds fields while retaining every canonical field in either stored column, refresh may replace both with the sanitized source payload. Divergence that would lose nonsecret data refuses replacement. Nonsecret value changes, missing keys, or changed list positions/lengths remain refusal conditions. New lines must retain the existing source session-ID set; this issue does not expand source attribution.
- Policy extensions work when source/stored representations reach the same current fixed point and historical placeholders remain recognized. An incompatible policy change refuses safely rather than disabling field checks. Use the existing historical header-only PEM behavior as the concrete compatibility fixture described below; no policy version or runtime policy toggle is needed.
- Comparison is type-sensitive recursively: booleans, integers and floats are distinct, including `true` vs `1`, `false` vs `0`, and `1` vs `1.0`. Key order and serialization whitespace are immaterial; list positions/lengths and scalar types/values are preserved. Apply this rule to preservation, canonical equality, Codex certification and decoded post-insert checks.
- Stored-column decoding at these comparison seams is also fail-safe: malformed zlib/UTF-8/JSON, unsupported storage values, duplicate JSON object keys and non-object roots refuse with `invalid_payload`; decoding recursion overflow refuses with `resource_limit`. Never surface original decoder exceptions or silently discard duplicate members. Use both-column decoding for old canonical comparisons and new literal checks without changing replay codecs. This adds no maintenance-style allocation bounds.
- On sanitizer failure, reject the affected source/ingest transaction; do not persist originals, placeholder substitute payloads, silently skip the event, advance its cursor, or publish a success watermark. Local operations roll back; committed remote chunks may remain and must contain only sanitized rows. A retry uses existing dedup and the unchanged success boundary. `refresh_raw_events` reports an explicit per-source refusal and continues other sources; bulk backfill and usage-source refresh still raise the safe exception.

## Motivation

Persisting redacted rows without changing equality checks would break Codex first-use certification and source refresh. Making those checks canonical preserves replay while giving the explicit cleanup command a compatible storage baseline.

## Proposed Solution

Use the ENH-3750 result payload at the shared serialization site in `_backfill_raw_events` and at Claude's separate insert. Keep original event objects for metadata/qualification and source-byte proofs. Counts are not persisted as new metadata in this issue.

Add a private `_decode_stored_payload` helper beside the comparison helpers in `usage_refresh`, reused by Codex certification. At all stored comparison SELECTs, fetch both payload columns as `CAST(column AS BLOB)` alongside `typeof(column)`, retaining the relational/compaction slots. Invalid UTF-8 in a legacy SQLite TEXT value otherwise raises an input-bearing `sqlite3.OperationalError` during fetch, before the helper can suppress it. The helper accepts those byte values plus the original SQL type: decode TEXT as strict UTF-8 without decompression; unpack compressed BLOB using the existing codec. Reject unsupported SQL types, duplicate JSON object keys and non-object roots. Convert only expected decoding failures (`zlib.error`, `UnicodeDecodeError`, `json.JSONDecodeError`) to `HistorySanitizationError('invalid_payload') from None`; a decoding `RecursionError` becomes `HistorySanitizationError('resource_limit') from None`. Explicit validation refusals use the same reason-only construction. Source/stored canonicalization still rejects non-finite numbers through the existing sanitizer. Literal checks decode/validate without sanitizing newly inserted values. Do not catch arbitrary `Exception` as a decode refusal, import private `pii._fail`, extend the closed sanitizer reason vocabulary, or modify `_unpack_payload`/parser/replay behavior. Unexpected parser/backend failures retain their current propagation behavior; the reason-only guarantee applies to these defined policy/decode failures. These byte projections provide no stored/decompressed allocation cap; ENH-3752 owns bounded maintenance.

Add a small internal canonicalization helper in `usage_refresh` taking decoded payload plus `host`/`event_type`; both source and stored signatures use it. For rows, context comes from relational host/event type, not ambient configuration or a user-controlled nested discriminator. Canonicalize both payload columns independently and apply `_preserves_fields` to each before any source delete. The unchanged test compares decoded canonical objects, not compressed bytes or incidental JSON whitespace/order. The post-insert check must prove that both decoded columns equal the expected sanitized source object **before applying another sanitization pass to the inserted columns**. A canonical-only post-check could hide a missed insertion seam by turning newly inserted plaintext into the expected object in memory. Test both the semantic legacy pre-check and literal sanitized post-insert representation; only supported matched spans may differ from the original.

For source replacement in `refresh_raw_events`, build an original-source metadata map keyed by line number before canonicalizing payloads. Every existing line must remain present with matching timestamp, session ID, host, host basis, ordinal and event type; retain existing attribution/position refusals and use `source_metadata_changed` for other per-line mismatches. A missing existing line retains `existing_payload_not_preserved`. Refuse before deletion or payload canonicalization. This intentionally rejects metadata repair, including `unknown` -> a concrete event type or reassignment among sessions even when the overall session-ID set is unchanged. Retain the existing whole-source session-ID-set guard and its `session_attribution_changed` reason; new lines within that set and new fields remain allowed when existing lines pass preservation. Adding a previously unseen session ID remains a refusal even when old lines are intact.

Compute expected `usage_contract` from the original verified source, independently of that identity comparison. Equal contracts are compatible. NULL -> a non-NULL expected contract is compatible only through full source replacement after both-column preservation passes; this retains existing explicit refresh behavior. Any non-NULL -> NULL/different transition refuses with `usage_contract_changed`. Qualification-only promotion also invalidates cursors/non-live usage and derive checkpoints, requires rebuild, and creates newly sanitized rows. Payload canonical equality alone does not bypass this transition or make it unchanged. Codex's expected Claude contract is NULL; an unexpected persisted marker must not be certified. The two new refusal codes are decided contracts, not implementation options. Retain existing early-guard precedence (including holds, attribution, compaction, coverage, session-ID sets and file witnesses); then check existing-line presence/metadata, forbidden qualification transitions, stored decoding/canonicalization, and finally field preservation. This prevents a corrupt payload from overriding an earlier structural refusal.

Use the same policy/context in `_refresh_codex_usage_source` first-cursor certification; include both payload columns and `usage_contract`. Within its existing local `BEGIN IMMEDIATE` transaction, capture the source's existing line-number set **before** calling `_backfill_raw_events`. Existing lines use canonical comparison for legacy compatibility. Newly inserted lines must compare both decoded columns literally with the expected sanitized source, without sanitizing the stored side again; otherwise first-cursor certification could conceal the same missed insert seam as source refresh. Keep `INSERT OR IGNORE` and the helper's positional call shape: this classification relies on never rewriting existing lines. A mismatch uses the existing certification refusal and rolls back without publishing a cursor. Add one indexed source-line read only for first certification; later appends retain their current insert-only behavior and rely on insert-path tests. Leave line coverage, attribution, inode/device, offsets, raw-byte tail digests, and final file-change witnesses intact. Neither canonicalization nor maintenance changes what those witnesses prove.

Keep `_preserves_fields` as the conservative dict-subset/list-position checker, but require identical scalar types before equality. Add a private recursive equality helper for exact canonical/post-insert comparisons; ordinary Python dict/list equality conflates booleans, integers and floats. Compare relational signature segments separately and route each payload slot through this helper; whole-signature tuple/list equality would still hide nested coercions. Use that helper at every payload equality seam, including Codex certification; do not change replay consumer bodies.

Handle `HistorySanitizationError`, including comparison decode refusals, with content-free reason diagnostics. Local `backfill_raw_events`, both usage-refresh branches, and source refresh must release connections and roll back on failure; test failure after at least one candidate insert and after source replacement starts. In `refresh_raw_events`, catch this specific exception within the per-source boundary, roll back, append `SourceRefresh(path, 'skipped', exc.reason, rows=0)`, and continue. Reuse the finite sanitizer reasons verbatim and keep the usage-replay-hold refusal ahead of canonicalization/replacement. Preserve previously committed outcomes and `needs_rebuild`; let unexpected parser/backend exceptions propagate through the existing rollback path. The CLI consumes the ordinary result and emits its existing single JSON report plus reason-only skip diagnostics and exit 1. Catching only around the whole call would hide earlier successful commits. Bulk backfill and usage-source APIs still raise; their CLI/worker boundaries handle the safe reason.

Add explicit rollback-before-close to local `backfill_raw_events` and full `backfill` on failure. Full backfill rolls back all uncommitted writes on that connection, including earlier issue/snapshot/loop/git/search writes; helpers must not commit them first. Bulk raw ingest similarly rolls back all handles in that call. The watermark belongs to the final success transaction, and `also_rebuild` runs only after a successful ingest commit. Schema setup or independent telemetry already committed on other connections is outside this rollback scope.

Remote failure after a committed chunk stops before the watermark write, discards unflushed candidates, and is recoverable through ordinary retry/dedup. Do not promise rollback across remote chunks. The rejected source may remain blocked until its unsafe content/structure is resolved; that is intentional, not a reason to fabricate a replay record.

Deterministic failures remain failures on subsequent calls: for example, Python's JSON decoder accepts `NaN`/`Infinity` but the sanitizer rejects them with `invalid_payload`. This also aborts all uncommitted full-backfill writes; later appended valid events do not authorize skipping the rejected event. The detached usage worker exits on the first failed refresh without executing its scheduled second pass or writing success retry state. Do not add self-rescheduling, per-line quarantine, or automatic repair in this issue.

## Program Design

### Signatures

Consume the new policy API supplied by ENH-3750:

```python
sanitize_history_payload(payload, *, host=None, event_type=None) -> HistoryRedactionResult
```

Proposed internal helper:

```python
def _decode_stored_payload(value: bytes, *, storage_type: str) -> dict[str, Any]:
    """Decode comparison input, converting expected failures to safe policy reasons."""
    ...

def _canonical_payload(
    payload: dict[str, Any], *, host: str | None, event_type: str | None
) -> dict[str, Any]: ...

def _payload_equal(left: object, right: object) -> bool:
    """Exact recursive JSON equality with identical scalar types."""
    ...
```

Existing `_event_signature(event, handle)`, `_stored_signatures(rows)`, `_preserves_fields(stored, parsed)`, `SourceRefresh`, and `RefreshResult` remain private/current compatibility surfaces. Add context handling without changing public refresh/backfill signatures. Keep `lifecycle._backfill_raw_events` a module attribute with its existing positional call shape for callers/tests.

### Call Path

`backfill_raw_events` / `backfill_incremental` / `refresh_raw_events` / `_refresh_codex_usage_source` -> `_backfill_raw_events` -> sanitizer with verified event context -> serialize -> pack -> local insert or bounded remote insert batch.

Claude `refresh_usage_source` -> decode original record -> qualification/metadata plus sanitizer -> serialize/pack -> insert -> derive -> success boundary.

`refresh_raw_events` -> canonical source plus both stored columns -> structural/preservation checks -> unchanged OR transactional sanitized replacement -> post-insert parity. Codex first-cursor certification uses the same policy before publishing a cursor.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — shared/local/remote serialization, Claude insert, first-cursor existing/new line classification and both-column certification, explicit raw/full-backfill failure cleanup.
- `scripts/little_loops/session_store/usage_refresh.py` — byte-safe comparison reads/decoder, context-aware signatures, both-column preservation, canonical no-op and post-insert verification. Codex certification reuses its decoder for both existing and new rows.
- Comment-only updates: `scripts/little_loops/session_store/qwen.py`, `writers.py`, and `schema.py` where wording claims verbatim/JSON-equal raw payloads. DDL is unchanged.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py`, `main_session` refresh branch — retain its per-source skip reporting and single JSON result. Sanitizer failures become `SourceRefresh` refusals inside `refresh_raw_events`, rather than an outer catch that loses previously committed outcomes. Backfill retains explicit safe exception handling at the CLI boundary.
- `scripts/little_loops/cli/session.py:894,915,951,974` — `backfill_incremental(...)` / `backfill(...)` calls in `main_session()` (`backfill` branch) have no handler for `HistorySanitizationError` either; same fix [Agent 1 + 2 findings]
- `scripts/little_loops/cli/backfill_worker.py:230` — `except HistoryUnsupported` in `main()` is the only handler around `backfill_incremental` (`:221`); add `HistorySanitizationError` so the ingest branch prints a reason-only line and returns 1 instead of propagating a traceback. `_run_usage_trigger` (`:120`, `{exc}` print) is already safe once `exc` is the reason-only error [Agent 1 + 2 findings; confirmed by reading `:217-233`]
- `scripts/little_loops/session_store/lifecycle.py:1968` — `backfill_incremental()` docstring says "Errors are not suppressed — the caller (session hook) catches them and logs a warning"; the worker does not catch `HistorySanitizationError` today, so update the wording alongside the handler above [Agent 2 finding]
- `scripts/little_loops/session_store/usage_refresh.py:3` — module docstring ("`raw_events` stores normalized payloads…") belongs to the comment-only wording sweep in a file already being modified [Agent 2 finding]
- `scripts/little_loops/session_store/writers.py:154-160` — the "source-of-truth table" compression comment above `_PAYLOAD_ZLIB_LEVEL` and the `_iter_events_with_host` docstring ("replaying previously-ingested lines") are in the same comment-only sweep; edit comments/docstrings only (they are stripped before the rebuild-fingerprint hash, but `_unpack_payload`/`_iter_events*` bodies must not change) [Agent 2 finding]

### Dependent Files and Similar Patterns

- `scripts/little_loops/session_store/sessions.py`, `claude_usage.py`, and replay consumers in `writers.py` define payload shapes and attribution; preserve their function behavior.
- `scripts/little_loops/cli/backfill_worker.py` inherits policy via backfill/usage refresh; it prints exception text, so verify safe reason-only errors at this boundary too.
- `scripts/little_loops/session_store/libsql.py` / `hrana.py` provide atomic per-chunk remote insertion; do not broaden remote refresh support.
- Rebuild fingerprints cover reachable replay functions. Add sanitization only at ingestion/comparison seams, not in `_unpack_payload`, `_iter_events*`, or rebuild-reachable `_backfill_*` consumers. `_backfill_raw_events` is the required insert seam, not a blanket prohibition on all `_backfill_*` names. If replay function bodies must change, bump `REBUILD_DERIVE_VERSION` and regenerate the existing fingerprint deliberately.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/lifecycle.py:968-984` — payload-blind readers/writers of both columns in `recompress_raw_events()` (`SELECT id, raw_line, parsed_json … typeof(...)='text'` then `UPDATE`, packing legacy TEXT via `_pack_payload`); must stay byte-lossless — it is not a sanitize seam and must not sanitize, or "unchanged is no-write / legacy plaintext is not scrubbed" is violated [Agent 1 + 2 findings]
- `scripts/little_loops/session_store/lifecycle.py:1447` — `SELECT … ordinal, raw_line FROM raw_events WHERE source_path = ?` in `_refresh_codex_usage_source()` is the only stored-column read used by certification; add `parsed_json` and `usage_contract`, plus a pre-insert line-number query in the first-cursor branch. `_stored_signatures` in `usage_refresh.py` already receives both columns but currently decodes only `raw_line`. [Updated by review; Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py:1589-1594` — the Claude insert is `_pack_payload(json.dumps(record))` + `INSERT OR IGNORE INTO raw_events` inside `refresh_usage_source()`, distinct from the shared `_backfill_raw_events` seam at `:854`/`:876` (`_REMOTE_RAW_INSERT` at `:779`, `executemany` at `:842`) [Agent 1 finding; confirmed by grep]
- `scripts/little_loops/session_store/writers.py:3912` and `_iter_events_with_host` `qwen` branch — read `raw_line`/`parsed_json` via `_unpack_payload`/`json.loads` and re-normalize with `is_raw_qwen_record`/`normalize_qwen_record`; sanitization must preserve the shape those predicates key on. All eight ingest hosts are registered with the ENH-3750 sanitizer (`test_pii.py::test_registered_hosts_match_session_parsers`), so none falls into "unknown context" [Agent 2 finding]
- `scripts/little_loops/session_store/__init__.py:97` — re-exports `backfill_raw_events`, `backfill_incremental`, `refresh_usage_source`, `_pack_payload`, `_unpack_payload` (not `refresh_raw_events`); no change needed, but keeps the public/positional shapes pinned [Agent 1 finding]
- `scripts/little_loops/hooks/session_start.py:150-231` and `scripts/little_loops/hooks/usage_stop.py:40` — spawn `little_loops.cli.backfill_worker` with stderr/stdout `DEVNULL`; no loop/skill/command consumes `ll-session refresh`/`backfill` output or exit codes (searched `loops/`, `hooks/`, `skills/`, `commands/`, `docs/`), so the new exit-1 reason lines have no gate consumers [Agent 1 + 2 findings]
- Full `backfill()` in `scripts/little_loops/session_store/lifecycle.py` commits once at the end on one connection spanning issues, loops, raw events and learning tests. A sanitizer failure rolls back that whole uncommitted batch; bulk `backfill_raw_events` likewise aborts all handles in the call and leaves the watermark unchanged. The earlier issue/snapshot/loop/git helpers and `_index` do not commit this connection; retain that property and test the earlier writes as part of rollback. [Updated by review; Agent 2 finding]

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
- Comparison tests seed `true`/`1`, `false`/`0`, and integer/float substitutions in either stored column, including nested lists; preservation/certification refuse and inserted-row verification detects them. Key-order/whitespace-only differences remain compatible.
- Per-line metadata tests change timestamp, ordinal, event type, and session attribution while leaving canonical payloads intact; include session reassignment with an unchanged overall session-ID set. Assert refusal and no row/cursor/checkpoint writes before canonicalization, including `unknown` -> concrete type.
- Attribution tests accept an appended line with an existing session ID and refuse an appended previously unseen session ID with `session_attribution_changed`. Keep every old line unchanged in both fixtures, so the whole-source guard is tested separately from per-line metadata preservation.
- Concrete policy-compatibility fixture: keep metadata/qualification identical and use a free-text payload leaf containing a full synthetic PEM block in the source, a historical `[PRIVATE_KEY_PEM]` header plus recognizable body/END in one stored column, and the final `[PRIVATE_KEY_PEM]` in the other (mix TEXT/BLOB storage). All three must reach the same current fixed point, certify/no-op without writes, and remain idempotent. Then add a nonsecret suffix only to a stored column; refresh must refuse `existing_payload_not_preserved`, and Codex first-cursor certification must refuse without publishing a cursor. Exercise the same compatibility fixture through replacement by adding an ordinary source field, and assert literal sanitized post-insert parity. This covers the existing policy's historical-output extension without inventing or mocking a new detector.
- Qualification tests retain `test_refresh_recovers_stripped_usage_and_rebuild_is_stable`, cover qualification-only NULL -> marker replacement and later unchanged refresh, and refuse marker removal/replacement. Rebuild a fully qualifying payload with a persisted NULL marker and prove it stays unqualified. For every qualified ingest fixture, assert that the original and sanitized payload yield the same producer contract and usage components.
- Codex first-cursor fault tests bypass sanitization when inserting a new line, separately in `raw_line` and `parsed_json`. Certification must refuse and roll back the new row and cursor; otherwise canonicalizing the stored side masks the leak. Pre-existing secret-only legacy differences still certify without payload writes. Do not introduce append-time re-certification.
- Full-backfill failure tests seed earlier issue/snapshot/loop/git/search writes, then fail raw sanitization; prove those uncommitted writes roll back, previous committed rows/watermarks survive, and `also_rebuild` is not invoked. Remote retry tests must resolve the failing input, insert only missing lines, retain the sanitized committed chunk, and publish the watermark only after success.
- Multi-source refresh tests place a sanitizer failure before, between and after valid sources, including a failure after source deletion starts. The failing source is restored exactly; valid source commits/results remain visible; `needs_rebuild` reflects those commits; CLI JSON remains one document and exit is 1.
- Comparison decode tests corrupt each stored column separately (invalid zlib, compressed invalid UTF-8 with a canary, malformed legacy TEXT created with `CAST(? AS TEXT)` over invalid bytes, malformed JSON, duplicate keys, non-object roots, and excessive JSON nesting). Assert the decided safe reason, exact row/cursor/checkpoint retention and prior-source results. Pin TEXT-vs-BLOB decoding using `typeof` so byte projections are never mistaken for compressed data. Codex first-cursor failure rolls back prospective inserts/cursor. Check `str`, `repr`, `args`, formatted tracebacks and CLI/worker stderr; suppressed decoder context must never expose original bytes. Include a hold/metadata mismatch plus corrupt payload to prove earlier refusals run before decoding.
- A source with a valid preceding event and then `NaN`/`Infinity` must abort raw/full backfill and Claude usage-source refresh with `invalid_payload`, retaining committed data and success boundaries. A usage-trigger worker failure must return 1 after one refresh attempt, retaining its prior retry state; no second-pass or self-retry is scheduled.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh_3166_qwen_normalizer.py` — `TestClaudeParity::test_claude_rebuild_counts_and_lines_unchanged` asserts `[line for line, _ in rows] == original_lines` as exact text; breaks if the sanitized payload serializes with different key order/separators than `json.dumps(r)`. Fixture has no secrets, so keep the exact assertion and keep serialization identical; update the comment at `:642` ("verbatim source lines") [Agent 3 finding]
- `scripts/tests/test_enh_3393_gemini_normalizer.py` — `TestGeminiIngest::test_raw_line_and_parsed_json_are_normalized_form` (`~:182`) is a ready both-columns-identical assertion; update the "JSON-equal to the source line" comment at `:235-236` in `TestClaudeParityUnaffectedByNormalizeFile::test_claude_host_still_uses_per_line_path` [Agent 3 finding]
- `scripts/tests/test_session_discovery.py` — `TestBackfillRawEventsCodexHandleD3::test_codex_handle_seeds_session_id_via_fallback` (`:979`) calls `_backfill_raw_events(conn, [handle])` positionally on the email fixture; guards the positional shape and that `session_id` stays derived from the original payload [Agent 1 + 3 findings; confirmed by grep]
- `scripts/tests/test_session_store_lifecycle.py` — `TestBackfillCodexHandlesD4::test_backfill_ingests_codex_fixtures_via_handles` and `::test_rebuild_derives_codex_tool_events` ingest the `[EMAIL]` fixture through `backfill()` and assert counts/tool names (`["Bash","Bash","Bash"]`); they are the ingest→rebuild parity guards, not payload-text assertions [Agent 3 finding]
- `scripts/tests/test_remote_hooks.py` — `TestBackfillWorker::test_ingest_only_is_allowed` (`:317`) is the only worker-level remote ingest test; add the worker-stderr canary/no-`Traceback` check beside `test_a_rebuild_is_refused_with_a_message_and_no_traceback` [Agent 1 + 3 findings]
- `scripts/tests/test_backfill_worker_usage_trigger.py` — `test_failure_keeps_request_retryable` (`:61`) is the closest fail-on-Nth-call idiom (`nonlocal attempts`); extend with a `HistorySanitizationError` raise to assert state-file/watermark untouched [Agent 3 finding]
- `scripts/tests/test_ll_session.py` — patches `little_loops.cli.session.backfill_incremental` (`:713`, `:795`); add the `ll-session refresh`/`backfill` `HistorySanitizationError` reporting tests next to these, plus `test_ll_session_refresh.py` for the `refresh` branch [Agent 1 finding]
- `scripts/tests/test_bug3736_usage_replay_holds.py` — `TestWholeSourceReplayGuard::test_refresh_of_held_source_is_rejected_before_invalidating` (`:242`) seeds `'{}'` TEXT rows and expects `("skipped","usage_replay_held")` with `meta`/cursors unchanged; canonicalization must not run or write before that hold check [Agent 3 finding]
- `scripts/tests/test_session_store_usage_refresh.py::_remove_stored_usage` (`:51`) and `scripts/tests/test_ll_session_refresh.py::_prepared` (`:20`) seed the same `packed` bytes into both columns; both-column divergence tests need a new seeding helper that writes different values to `raw_line` and `parsed_json` [Agent 3 finding]
- `scripts/tests/test_session_store_usage_refresh.py::test_failed_reingestion_rolls_back_existing_rows` monkeypatches `"little_loops.session_store.lifecycle._backfill_raw_events"` with a `*_args` stub and compares `SELECT id, raw_line` before/after; pins that the name stays a call-time module attribute with the positional `(conn, handles)` shape and that rollback is byte-stable [Agent 2 + 3 findings]
- `scripts/tests/test_libsql_backend.py::test_executemany_is_atomic` (`:273`) — only existing chunk-atomicity test; a duplicate-PK row is the one existing way to make a chunk fail, while `HranaStub.fail_next` (`scripts/tests/hrana_stub.py`) is one-shot and cannot target the second 200-row chunk without counting requests — for "failure after a committed chunk" prefer a call-counting stub on the lifecycle sanitizer name over `fail_next` [Agent 3 finding]
- New test gaps (no existing coverage): no ingest→rebuild test carries a supported span inside nested reasoning/tool strings, arrays, or Unicode escapes; no cross-host (claude/codex/omp/pi/qwen/gemini/opencode) test plants a secret and compares post-rebuild usage and tool linkage; no shared helper decodes stored/outbound columns (each test inlines `json.loads(_unpack_payload(...))`; candidates `scripts/tests/helpers.py` or a sibling of `hrana_stub.py`, whose `_decode_value` already base64-decodes blob args) [Agent 3 finding]
- Pre-commit: plant secrets as fragments (`"AKIA" + "I" * 16`, `test_pii.py`) for gitleaks (`.pre-commit-config.yaml`); the `rollout-interactive.jsonl` email (`brennon@brenentech.com`, lines 26-27) is the only real email in fixtures; use `/nonexistent/...`, not `/home/<user>/`, in test paths [Agent 2 finding]

### Documentation

`docs/reference/API.md`, `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/CLI.md`, and `docs/reference/CONFIGURATION.md`: default-on raw-column coverage, semantic refresh no-op vs explicit legacy cleanup, fail-safe rejected sources, remote chunk boundary, and preserved replay/source proofs. Explain the narrower per-line metadata refusal and retained explicit-refresh qualification promotion: promotion requires replacement/rebuild and can change legacy usage qualification; replay alone cannot promote it. Mention full-backfill transaction scope and that direct derived writers and originals are outside this guarantee. Use end-user wording in guides/reference docs.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-session` "`refresh` flags and safety" (`:4635-4650`) promises nonzero exit only for skipped sources; describe sanitizer rejection as a reason-only line. "`recompress` flags" (`:4693-4698`, "idempotent and byte-lossless") must say `recompress` does not scrub legacy plaintext. The `ll-session` example block (`~:4735-4754`) is the place for a `refresh`/`recompress` note [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — `[^qwenwire]` footnote (`:719-737`) describes what reaches `raw_events` and how replay re-normalizes it; check it against sanitized storage. `[^kimiwire]` (`:713`, "yields the raw typed events untouched") is parser-level and likely unchanged [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `### history` / "Remote history backend" **Ingestion** bullet (`:737`) is the natural home for the committed-remote-chunk statement; keep both headings (pinned by `scripts/tests/test_wiring_reference_docs.py`) [Agent 2 finding]
- `docs/ARCHITECTURE.md` — keep the `## History DB: Producer→Consumer Flow` heading when editing raw-event descriptions. The heading is pinned by `scripts/tests/test_wiring_guides_and_meta.py`. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — the "`raw_events` is the source of truth" admonition (`:195-207`) plus `:666`/`:677` ("verbatim source records") [Agent 2 finding]
- `CHANGELOG.md:1919-1921` — historical "`raw_events` is now the source of truth" text; leave as-is. New entry goes in a concrete version section at release prep, never `[Unreleased]` [Agent 2 finding]
- `scripts/little_loops/session_store/claude_usage.py:3-5` — module docstring's "persisted at ingest time; replay must copy" contract is consistent with the plan; no edit [Agent 2 finding]
- `scripts/tests/test_docs_audience_gate.py` applies to `docs/guides`, `docs/reference` and `README.md`: no `scripts/tests/…` paths or "this repo" in those edits [Agent 2 finding]

### Configuration

No opt-out, policy-version column, schema migration, or new dependency. Existing history target configuration/dedup stays unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- ENH-3750 has landed (commit `b953e103c`): `sanitize_history_payload` (`pii.py:679`), `HistoryRedactionResult(payload, counts)` (frozen dataclass; `.payload` is a fresh copy, never aliased to the input) and `HistorySanitizationError` (`pii.py:342`, a `ValueError` subclass whose `str()`/`args` are the reason code only, raised `from None`) all exist. Nothing under `session_store/` or `cli/` imports `little_loops.pii` yet, and `test_pii.py::test_top_level_package_does_not_export_history_api` pins that the history API is importable from `little_loops.pii` only, not the top-level package. The `blocked_by: ENH-3750` edge is therefore stale.
- The sanitizer's registered `(host, event_type)` context protects replay-identity fields and a would-be change to one raises `unsafe_identity`; unknown or missing context gets no exemptions. Context must therefore be the verified handle host (`handle.host` at `lifecycle._backfill_raw_events`; the literal `'claude-code'` at the Claude `refresh_usage_source` insert) and the same `event.type or "unknown"` / `str(record.get("type") or "unknown")` value already written to the `event_type` column.
- There are four callers of `_backfill_raw_events`. In `scripts/little_loops/session_store/lifecycle.py`, they are `backfill_raw_events`, `_refresh_codex_usage_source` and `backfill`. The fourth is `refresh_raw_events` in `scripts/little_loops/session_store/usage_refresh.py`. Full `backfill` also refuses remote stores. Direct helper tests live in `scripts/tests/test_session_store_lifecycle.py`; `backfill_incremental` delegates to `backfill_raw_events`.
- Both payload columns are bound to the *same* `packed` bytes at the local insert, the remote `pending` tuple (12-tuple: 10 column values plus `session_id, line_no` for the `WHERE NOT EXISTS` dedup) and the Claude insert. `session_id` is derived from the original `event.payload.get("sessionId")`, and the Claude insert writes no `ordinal` (column default). `SessionEvent` is a frozen dataclass but `payload` is a mutable dict; `_backfill_raw_events` and `claude_transcript_contract` only read it today, so sanitizing must keep that true.
- Comparison surfaces read different columns: `_stored_signatures` and `_preserves_fields` (`usage_refresh.py`) and the post-insert re-check read `raw_line` only; `parsed_json` appears solely in the unchanged short-circuit as unpacked-string equality; Codex first-cursor certification (`lifecycle.py` `_refresh_codex_usage_source`, `if cursor is None:`) selects `raw_line` only and compares `json.loads(_unpack_payload(row[6])) == event.payload`. A later-append Codex refresh (cursor present) skips certification entirely.
- Failure-handling asymmetry: `backfill_raw_events` and `backfill` have `try/finally: conn.close()` with no `except`/`rollback` (the uncommitted local transaction is discarded and the watermark `INSERT INTO meta` is never reached); `refresh_raw_events`, `refresh_usage_source` and `_refresh_codex_usage_source` have `except Exception: conn.rollback(); raise`. `LibsqlConnection.commit()/rollback()` are no-ops (autocommit); each `executemany` chunk (`_REMOTE_INSERT_CHUNK = 200`) is atomic via Hrana `begin…commit`, earlier chunks stay committed, and rows still in `pending` are dropped when an exception propagates.
- `cli/backfill_worker.py`: `_run_usage_trigger` prints `f"…usage refresh failed: {exc}"` (safe once `exc` is a `HistorySanitizationError`), but `main()` catches only `HistoryUnsupported` around `backfill_incremental`; a `HistorySanitizationError` (`ValueError`) from the ingest branch propagates uncaught out of `main`. `hooks/session_start.py:224-231` spawns the worker with `stderr=DEVNULL`.
- Rebuild-fingerprint gate: `test_enh3678_rebuild_derive_gate.py` hashes a 23-function set resolved from `lifecycle.rebuild` (8 `lifecycle` + 15 `writers` functions, including `writers._unpack_payload`, `_iter_events`, `_iter_events_with_host` and the `writers._backfill_*` derive functions). `lifecycle._backfill_raw_events`, `refresh_usage_source`, `_refresh_codex_usage_source`, everything in `usage_refresh.py`, and `writers._pack_payload` are **outside** the set, so wiring at those seams cannot move the digest. Comments and docstrings are stripped before hashing. `REBUILD_DERIVE_VERSION` is `"enh3678-v1"` (`lifecycle.py` ~line 1064), pinned against `_FROZEN_LEGACY_DERIVE_VERSION`.

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- Convention: ingest/refresh failures propagate as exceptions with fixed literal messages or snake_case reason codes — never payload text (`RuntimeError("Codex stored source differs from current rollout")` at `scripts/little_loops/session_store/lifecycle.py` (`_refresh_codex_usage_source`); refusal codes like `existing_payload_not_preserved`, `parser_changed_during_refresh` at `usage_refresh.py:168-248`; `ll-session refresh` prints only the reason, `cli/session.py:818`). `HistorySanitizationError` already satisfies this.
- Convention: private comparison/packing helpers are underscore-prefixed, take explicit arguments and live beside their callers (`_pack_payload`/`_unpack_payload` at `scripts/little_loops/session_store/writers.py` (`_pack_payload` / `_unpack_payload`); `_event_signature`/`_stored_signatures`/`_preserves_fields` in `usage_refresh.py`). The `session_store` package has no `*canonical*`/`*sanitize*` helper today; elsewhere the repo spells it `canonical_*`/`_canonical_*` (`frontmatter.py:225`, `cli/issues/link.py:298`) and `_normalize_*`.
- Convention: tests monkeypatch the name the code under test resolves at call time (`"little_loops.session_store.lifecycle._backfill_raw_events"` in `test_session_store_usage_refresh.py:194-209`; `patcher.setattr(lifecycle, "_backfill_usage_events", fail_after_one)` in `test_session_store_incremental_usage.py:189-216`). Contested/absent: no existing test injects failure on the Nth insert or after a committed remote chunk (`HranaStub.fail_next` is used only in `test_hrana_client.py`), and refresh/certification are never exercised remotely (`refuse_on_remote`; `test_remote_operation_matrix.py` `_REJECTED`) — only `backfill_raw_events`/`backfill_incremental` reach the remote chunk path.
- Convention: leak checks use a canary rendered through `traceback.format_exception` plus `str`/`repr`/`args` and `__cause__ is None and __suppress_context__ is True` (`test_pii.py:825-848`, `TestHistoryErrorSafety`); stderr/log checks use `assert TOKEN not in out.err` / `caplog` (`test_remote_doctor.py:144-146`, `test_remote_ingestion_telemetry.py:342`). Test secrets are assembled from fragments (`"AKIA" + "I" * 16`, `test_pii.py:37-44`) so the repo's gitleaks hook does not flag them. There is no shared helper for decoding stored/outbound payload columns (each test inlines `json.loads(_unpack_payload(...))`) and no shared `HranaStub` fixture — each of 8 modules defines its own `TOKEN`/`remote`.
- `scripts/tests/fixtures/codex/rollout-interactive.jsonl` lines 26-27 hold the plain email the issue says must become `[EMAIL]` in storage.

## Implementation Steps

1. Add insert/context/failure tests for the shared local/remote path and separate Claude insert.
2. Wire sanitization before serialization/packing and ensure rollback/watermark boundaries remain safe.
3. Add type-sensitive canonical source/stored comparisons, both-column preservation, and Codex certification tests, including legacy no-op and the concrete historical PEM fixture. Match relational identity per existing line before decoding/canonicalization, retain the session-ID-set guard, and apply the separate qualification-transition rule, retaining stripped-usage recovery and explicit-refresh NULL promotion. Source and each stored column use their verified context independently. Decode stored comparisons through the safe helper; keep literal decoded post-insert checks in source refresh and for new Codex first-cursor rows, while pre-existing Codex lines remain canonical. Convert expected policy/decode refusals to per-source outcomes inside `refresh_raw_events` without losing earlier commits.
4. Verify replay/usage/tool-linkage parity, update contradictory comments/docs, run focused regressions and the full local suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/session.py` — handle safe sanitizer exceptions around the `backfill_incremental`/`backfill` calls; refresh uses the per-source refusal results from `refresh_raw_events` and preserves prior commits in its JSON report
- Update `scripts/little_loops/cli/backfill_worker.py` — import the safe sanitizer error from `little_loops.pii` and handle it in the ingest-branch `except` in `main()` (`:230`) with a reason-only stderr line
- Update `scripts/little_loops/session_store/lifecycle.py` — add `parsed_json`/`usage_contract` and byte/type projections to the first-cursor certification SELECT, capture existing lines before insertion, and validate new rows literally; add explicit raw/full-backfill rollback. Leave `recompress_raw_events` byte-lossless; refresh the stale `backfill_incremental` docstring (`:1968`)
- Update `scripts/little_loops/session_store/usage_refresh.py` — safe comparison decoder and byte/type projections on pre/post-replacement SELECTs, plus module docstring wording (`:3`); keep `_backfill_raw_events` imported function-locally and called positionally `(conn, handles)`
- Update comments/docstrings only in `scripts/little_loops/session_store/writers.py` (`:154-160`, `_iter_events_with_host` docstring) — no body changes to rebuild-reachable functions
- Update `scripts/tests/test_enh_3166_qwen_normalizer.py` and `scripts/tests/test_enh_3393_gemini_normalizer.py` — stale "verbatim"/"JSON-equal" comments; keep exact-text and both-column assertions
- Add tests in `scripts/tests/test_remote_hooks.py`, `scripts/tests/test_backfill_worker_usage_trigger.py`, `scripts/tests/test_ll_session.py`, `scripts/tests/test_ll_session_refresh.py` — canary-secret stderr/no-traceback checks for the CLI and worker boundaries
- Add a both-column divergence seeding helper (distinct `raw_line`/`parsed_json`) for refresh/certification tests, and a cross-host ingest→rebuild canary fixture with nested/array/Unicode-escaped spans
- Update `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/CONFIGURATION.md`, `docs/ARCHITECTURE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` — keep pinned headings; end-user wording

## Acceptance Criteria

- [ ] Each of the three SQL sites uses the same context-aware policy; decompressed stored/outbound columns contain no planted supported match and new columns have identical bytes, with nested/array/escaped fixtures.
- [ ] Replay identities, usage totals/qualification, tool linkage and dedup are stable; source byte digests/offset/inode/line/watermark contracts remain intact.
- [ ] Canonical Codex certification and refresh accept sanitized/mixed legacy rows and compatible policy extensions; sanitizer fixed-point/idempotence is covered for source and already-redacted rows. Unchanged is no-write and explicitly does not scrub legacy plaintext.
- [ ] Both stored columns participate in type-sensitive field preservation. Source refresh refuses nonsecret field/value/type/list loss and per-line relational context/identity changes before replacement; Codex certification rolls back prospective inserts on mismatch. Successful source replacement and new Codex first-cursor rows check both decoded columns against the sanitized source without re-sanitizing the inserted value to hide plaintext; existing Codex rows remain canonically compatible.
- [ ] Explicit refresh retains stripped-usage recovery and permits NULL -> original-source qualification only through replacement/rebuild; marker removal/replacement refuses. Qualification equality is required for unchanged. Sanitization preserves producer qualification on new rows, and replay never promotes a persisted NULL marker.
- [ ] Local failures roll back and remote failures publish no success boundary; prior committed remote chunks are sanitized and retry deduplicates safely; errors/tracebacks contain no canary secret. Multi-source refresh returns explicit sanitizer refusals alongside successful source results, with truthful `needs_rebuild` and one CLI JSON document.
- [ ] Expected stored-column decode failures use existing `invalid_payload`/`resource_limit` reasons with suppressed exception context, never discard duplicate JSON members, preserve source data/results transactionally, and occur only after earlier structural/qualification refusals. New session IDs retain `session_attribution_changed`; per-line metadata/qualification mismatches use the decided codes. Deterministic invalid payloads abort ingest without cursor/watermark advancement or worker self-retry.
- [ ] Full local backfill rolls back earlier writes in its transaction on sanitizer failure, publishes no watermark, and does not start `also_rebuild`; existing committed data is preserved.
- [ ] Relevant docs, focused regressions, rebuild-fingerprint gate, and `python -m pytest scripts/tests/` pass.

## Scope Boundaries

Raw payload inserts and certification/refresh comparisons only. No historical cleanup here, blanket derived/FTS redaction, opaque decoding, schema migration, remote source replacement, automatic skip/placeholder substitution on sanitizer failure, or redefinition of physical source proofs. ENH-3752 supplies explicit stored-row maintenance after this issue lands.

## Impact

- **Priority**: P2 — prevents new supported secret persistence and is required before stored-row cleanup can safely ship.
- **Effort**: Large — three insert sites plus several conservative comparison/failure paths and replay tests.
- **Risk**: Medium — equality/cursor mistakes could block ingestion or weaken refresh checks; context/parity and rollback tests cover these boundaries.
- **Breaking Change**: Matched raw payload strings become placeholders; public APIs and usage semantics remain compatible.

## Review Notes

Reviewed on `main`, 2026-10-05, with `/ll:advise` using `claude-opus-5-5`. Distinguished semantic certification from storage compliance, required preservation of both columns, and made local rollback/remote partial-commit behavior explicit. Fail-safe source rejection is retained deliberately; a placeholder payload would not preserve replay. ENH-3752 now waits for this compatibility wiring.

Follow-up review on 2026-10-06 reaffirmed the distinction between semantic legacy compatibility and storage compliance. Added an uncanonicalized decoded post-insert assertion: canonicalizing new rows during verification could mask a missed sanitization seam. Preserve relational context/type/identity checks ahead of payload equivalence. Opus supported both-column canonical legacy comparison and idempotence coverage (consult confidence 0.72). Generic unknown-context sanitizer behavior remains the existing policy, with no claim of registered-protocol protection; ENH-3752 independently refuses unsupported maintenance pairs through its registry query. Cached scores/verdict were cleared for a fresh assessment of the reviewed plan. No implementation edits were made.

Additional review on 2026-10-06 reproduced Python's boolean/numeric equality bypass in `_preserves_fields` and required consistent type-sensitive payload comparisons. Moved expected sanitizer handling into the per-source refresh boundary so a later refusal cannot hide earlier commits or their rebuild requirement. `/ll:advise` using `claude-opus-5-5` supported both refinements (confidence 0.78). Type-sensitive comparisons deliberately refuse legacy scalar coercions that previously passed; document that behavior. These are issue corrections; implementation remains pending.

Pre-implementation review on 2026-10-06 reproduced silent timestamp repair and qualification-only NULL promotion through the public refresh API. `/ll:advise` with Opus (`--model opus`, confidence 0.74) supported per-line identity refusal, a separate monotonic qualification rule, literal verification of new first-cursor Codex rows, and explicit full-backfill rollback scope. Retained existing explicit-refresh NULL promotion, including metadata-only promotion, because the original source supplies the evidence; replay remains unable to promote. Opus's dissent favored insert-path tests as a sufficient alternative to the Codex literal split; chose the split because one indexed read inside the existing transaction closes a concrete masking seam. Added producer-contract parity assertions without an extra runtime qualification pass. The 60 existing source-refresh and rebuild-fingerprint tests passed; the focused source-refresh tests do not rely on metadata repair. Earlier confidence scores remain historical; implementation is pending.

Further review on 2026-10-06 reproduced an input-bearing `UnicodeDecodeError` in stored comparison (`repr`/`args` contain original decompressed bytes), confirmed the existing new-session-ID append refusal, and verified full/historical/final PEM representations converge while a nonsecret suffix remains incompatible. `/ll:advise` with Opus (`--model opus`, confidence 0.76) supported a narrow safe decoder, decided refusal order, the retained session-set guard and concrete compatibility fixtures. Reused the closed `invalid_payload`/`resource_limit` reasons rather than Opus's suggested new decoder code. Added duplicate-key refusal to avoid silent field loss at the comparison seam. A final SQLite probe also reproduced malformed TEXT leaking in the fetch-time exception's `str`; comparison SELECTs therefore fetch payload bytes plus original SQL types before safe decoding. Opus's dissent questioned decode handling as scope expansion; both-column comparison introduces that failure surface, so it belongs here. Retained comment-only updates and separate exact-equality/subset helpers: the fingerprint strips comments/docstrings, and subset preservation must allow added fields. Added explicit non-finite-input/one-attempt worker tests without automatic retry or quarantine. The 254 existing sanitizer, source-refresh, Codex usage-refresh, CLI refresh and rebuild-fingerprint tests passed. No implementation changes were made; cached confidence scores were cleared for the revised contract.

## Blocked By

None. The sanitizer API this issue consumes landed in commit `b953e103c`; the frontmatter edge was removed on 2026-10-06.

## Blocks

- ENH-3752

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

Re-assessed after the latest issue edits. Supersedes the earlier assessment.

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE (below outcome_threshold 65)

### Concerns
- Dependencies clear: ENH-3750 landed (`sanitize_history_payload` at `pii.py:679`, `HistorySanitizationError` at `pii.py:342`), `blocked_by` is empty, and all format-check gates (Program Design, parity, claim, structure, decision) are clean. Anchors verified: `_backfill_raw_events` (`lifecycle.py:804`), `_refresh_codex_usage_source` (`:1369`), `refresh_usage_source` (`:1524`), `_event_signature`/`_stored_signatures`/`_preserves_fields` (`usage_refresh.py:58/74/91`); nothing under `session_store/` or `cli/` imports `little_loops.pii` yet; `backfill_worker.py:230` catches only `HistoryUnsupported`.
- Integration Map doc line ranges for `CLI.md` (refresh flags, recompress flags, example block) have drifted (`verify_verdict: CLAIMS_OUTDATED`); locate by heading, not line number.
- Type-sensitive equality deliberately refuses legacy scalar coercions that previously passed; the docs must say so.
- The contract is dense with ordered refusals (holds → attribution/coverage/session-set → per-line metadata → qualification transition → decode → preservation). Implement the refusal ordering as one explicit sequence and test each adjacent pair.

### Outcome Risk Factors
- Broad dependent surface: `_backfill_raw_events` has four callers plus the Claude insert, `cli/session.py`, `cli/backfill_worker.py`, and two spawning hooks (6–10 dependents).
- Moderate per-site depth: rollback/watermark boundaries across local and remote chunks, both-column preservation, per-line metadata refusal and the NULL→marker qualification transition are cross-module logic with shared state in `lifecycle.py` and `usage_refresh.py`.
- Rebuild-fingerprint gate (`test_enh3678_rebuild_derive_gate.py`) constrains where sanitization may be inserted; a misplaced seam forces a `REBUILD_DERIVE_VERSION` bump.
- Prior critique rounds indicate the contract has churned; treat the Codex first-cursor literal/canonical split and the rollback-scope rules as the likeliest places for iteration.

### Risk Factor Delta
- Baseline: none recorded

## Session Log
- `/ll:confidence-check` - 2026-10-06T20:17:48 - `50d7bb2b-f64d-4142-8ee2-7f463bfad337.jsonl`
- `/ll:verify-issues` - 2026-10-06T20:14:55 - `78d80ae4-e260-4b0c-9bb2-85e65c40ea76.jsonl`
- `/ll:confidence-check` - 2026-10-06T19:45:56 - `466b925c-c989-4144-94bc-ff9597778e0e.jsonl`
- `/ll:confidence-check` - 2026-10-06T19:26:53 - `afda5a75-36fd-4868-b330-ef24a018b110.jsonl`
- `/ll:confidence-check` - 2026-10-06T09:21:57 - `efbe7654-b8cc-4b46-8b6e-54d1216778fc.jsonl`
- `/ll:verify-issues` - 2026-10-06T09:20:37 - `3fd3819a-5352-4bac-bbe1-b8a3f3e515f1.jsonl`
- `/ll:wire-issue` - 2026-10-06T09:18:17 - `69fbb543-02d8-48e4-bbb6-a2a33935a7ec.jsonl`
- `/ll:refine-issue` - 2026-10-06T09:05:52 - `da8cdf64-7ea1-489f-a22f-62d03c35c5b9.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:46:34 - `2fc077e6-f247-45dc-97b8-6729a8243496.jsonl`
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`

## Documentation

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- `docs/reference/API.md:10437-10447` (`### raw_events / rebuild / compact`) still says `raw_line` is "JSON-equal to the parser's own output" and documents `_backfill_raw_events` with a `host` keyword the code does not have (`lifecycle.py:804` is `(conn, handles)`); `API.md:8476-8565` documents the ENH-3750 policy but says nothing about ingest. Comment text claiming verbatim/JSON-equal payloads: `qwen.py:28`, `schema.py:471-473`, `lifecycle.py:826-828`. `HISTORY_SESSION_GUIDE.md:129` calls `raw_events` the "source of truth" and `:666`/`:677` mention "verbatim source records"; `docs/ARCHITECTURE.md` `raw_events` mentions at 695-724, 772, 1588-1594. `CLI.md:4635-4659` documents `ll-session refresh` skip reporting.
