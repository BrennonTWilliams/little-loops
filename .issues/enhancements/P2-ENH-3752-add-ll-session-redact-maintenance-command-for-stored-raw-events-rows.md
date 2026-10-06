---
id: ENH-3752
title: Add ll-session redact maintenance command for stored raw_events rows
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
unproven_mechanism: true
spike_needed: true
spike_attempted: true
spike_completed: true
size: Very Large
confidence_score: 85
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
risk_factors:
- id: cli-parse-before-telemetry
  domain: readiness
  criterion: architecture
  description: Parse-once-before-cli_event_context reroutes _main_session and drops
    help/usage-error telemetry for every ll-session command
- id: deep-concurrency-accounting
  domain: outcome
  criterion: complexity
  description: Guarded writes, ambiguous-commit reconciliation, ABA accounting and
    interruption transitions share state across local/remote paths
- id: estimator-contract-stale-vs-spike
  domain: readiness
  criterion: well_specified
  description: Contract keeps a flat sixfold context-TEXT bound; spike proved it undercounts
    non-ASCII (needs 2x/6x/12x tiers)
- id: m3-split-undecided
  domain: outcome
  criterion: ambiguity
  description: Remote milestone M3 split is left conditional with no recorded decision
    after M0 completed
- id: main-session-routing-blast-radius
  domain: outcome
  criterion: change_surface
  description: Changing _main_session parse ordering touches the dispatch path of
    every ll-session subcommand and its telemetry tests
- id: related-maintenance-helpers
  domain: readiness
  criterion: no_duplicates
  description: recompress_raw_events and ENH-3751 decode/compare helpers overlap in
    purpose but cannot be reused (unbounded decode, local-only)
- id: stale-spike-status-text
  domain: readiness
  criterion: well_specified
  description: Status footer, Confidence Check Notes and Review Notes still describe
    M0 spike as absent/outstanding after it was PROVEN
- id: wide-site-count
  domain: outcome
  criterion: complexity
  description: Five production files plus four doc files and many test files across
    two backends and the CLI
---

# ENH-3752: Add ll-session redact maintenance command for stored raw_events rows

## Summary

Add `ll-session [--db TARGET] redact [--dry-run] [--batch N] [--json]`: an explicit, bounded, rerunnable scrub of both stored raw payload columns on SQLite and the configured libSQL project store. Preserve unchanged bytes, SQL types and all metadata; report confirmed update applications, reconciliation uncertainty and safe failures. Implement through the proof/core/local/remote/CLI milestones below.

## Current Behavior

Verified on `main` on 2026-10-06, after commit `28612c337`:

- ENH-3750 and ENH-3751 are done. `lifecycle._backfill_raw_events` and Claude's separate `refresh_usage_source` insert sanitize before serialization/compression/remote queuing. New inserts supply identical sanitized values to both columns; legacy plaintext remains until explicitly scrubbed.
- ENH-3751's Codex first-cursor certification and `usage_refresh.refresh_raw_events` compare **both** stored columns with the same canonical policy/context, retaining type-sensitive equality, field-preservation and qualification checks. Existing-line canonical equality certifies compatibility without removing stored secrets. The former `_stored_signatures` helper no longer exists; the current seams are `_stored_payloads`, `_canonical_payload`, `_payload_equal` and `_decode_stored_payload`.
- `recompress_raw_events` rewrites compression locally, refuses remote and is not redaction. `_unpack_payload` uses unchecked `zlib.decompress`; ENH-3751's comparison decoder rejects malformed content but does not bound allocation or reject trailing zlib streams. Maintenance needs its own bounded decoder without changing replay codecs.
- `resolve_history_target` supports local/remote targets; `resolve_history_db` requires a filesystem path. Normal writable local opens create/migrate; `connect_readonly` does neither but tolerates old schema versions. Remote read-only access likewise tolerates behind/ahead/unstamped stores; maintenance must preflight explicitly.
- `LibsqlConnection.executemany` preserves access/deadline guards and forwards the summed count from one atomic `HranaClient.execute_many` batch. Remote `commit`/`rollback` are no-ops. A short count cannot identify changed IDs; a lost acknowledgement can hide a committed write.
- `main_session` now catches `HistorySanitizationError` around `_main_session`. `_main_session` retains the raw-argv migrate fast path, then enters `cli_event_context(DEFAULT_DB_PATH, ...)` before argparse; nominal previews would write telemetry and explicit `--db` need not select that telemetry target.
- `raw_events.id` is an AUTOINCREMENT primary key without `CHECK(id > 0)`: explicit zero/negative IDs are legal. Payload/context columns are declared `TEXT NOT NULL`, but SQLite dynamic typing permits BLOBs. Starting a scan at zero or decoding context without its SQL type would make false completeness/safety claims.

## Expected Behavior

- Resolve the requested/configured target once; honor existing precedence without local fallback. An explicit non-default path is local; an explicit default-shaped `.ll/history.db` still follows configured/env selection. Remote scans include all project machines, without ingestion-watermark filters. Report only local path or remote provider/project, never endpoint/auth material.
- Scan every eligible ID through a captured `MAX(id)`, including zero/negative IDs, compacted rows, missing-original-file rows and independently differing columns. No source-file ingestion is needed.
- Process both columns independently with stored host/event-type context. Preserve each unchanged column byte-for-byte and with its original SQL type even when its sibling changes; never normalize, recompress or merge no-op columns. If either column/context is invalid, unsafe, unsupported or over a bound, leave the whole row unchanged, advance scan progress and report incomplete.
- Update payload columns in place only. Preserve IDs, attribution, host/basis, type/timestamp/positions, ordinal, usage contract, compaction/summary links, source cursors and ingest/derive watermarks. No delete/reinsert, schema/progress marker, rebuild, pruning or VACUUM.
- Preview performs the same validation as apply but zero logical payload/schema/progress/telemetry writes or target creation. In controlled tests the main DB/WAL bytes stay unchanged; live-WAL lock/shared-memory bookkeeping is allowed. Both modes require an existing current-schema target. Migration is a separate explicit operation.
- Conflicts, failed/unconfirmed rows, backend failures and interruption yield an incomplete nonzero result while preserving confirmed prior work. Every invocation rescans under the current policy; no durable checkpoint or one-time sanitized marker is needed.

## Motivation

Default-on ingest sanitization does not remove older plaintext. Compression and rebuilding cannot provide a bounded, conflict-safe raw-column scrub with truthful local/remote accounting. ENH-3751 now supplies the compatibility prerequisite; proof of the new persistence mechanism remains outstanding.

## Proposed Solution

### Target, preflight and CLI routing

Put the core in new `session_store/raw_redaction.py`, separate from lifecycle/replay helpers. Pass an already resolved `LocalTarget`/`RemoteTarget` through every subsequent open/read/write. Preview uses strict read-only connections, never `immutable=1` or an ensuring/migrating open. Add a narrowly scoped non-creating writable local opener in `session_store/backend.py`, using `sqlite_file_uri(path, mode="rw")`; no raw `sqlite3.connect` in the new maintenance module. Apply uses explicit short transactions locally and the guarded writable backend remotely.

Preflight the **same** target without mutations: local `_current_version`, remote fresh `remote_schema.read_state` plus matching nonempty project stamp, expected raw columns/NOT NULL prerequisites and exact installed schema version. Do not rely on the remote process verification cache or the permissive read-only access policy to certify a current store. Missing/unreachable targets get `target_unavailable`; schema/version/project mismatches get `schema_mismatch`. Give fixed migrate guidance for behind/unstamped stores and upgrade guidance for ahead stores on stderr, without forwarding backend messages. Neither mode creates or migrates a target.

Retain the existing migrate fast path. Parse each remaining invocation **once** before `cli_event_context`; route parsed `redact` to a dedicated handler outside telemetry, then wrap valid other subcommands as before. Accept/document the narrow consequence that help and argparse usage errors no longer emit telemetry. Keep other commands' target/capture behavior. Keep the refresh `resolve_history_db` call in `_main_session`, matching the current caller allowlist; add no resolver call or allowlist exemption for redact. The existing outer `main_session` sanitizer handler must never consume a maintenance row refusal and defeat its JSON report.

Validate positive `--batch` in argparse and the public API (reject bool/non-int/zero/negative values). Preserve default `batch_size=2000`; it is a row ceiling and cannot override the smaller internal bounds. Keep `redact` out of `_REMOTE_REFUSALS`.

### Snapshot, projections and context

Capture `MAX(id)` once, without `COALESCE`: `None` means an empty table. Start with `last_scanned_id=None`. The first keyset page uses `id <= snapshot_max_id ORDER BY id LIMIT n`; subsequent pages additionally require `id > last_scanned_id`. Never subtract one from `MIN(id)` or assume positive IDs. Advance `scanned`/`last_scanned_id` when a row is processed or rejected, not across still-unprocessed prefetched rows. Deletions can leave holes or a final observed ID below the maximum; completion is exhaustion through the bound.

One SELECT returns each page's SQL type, stored byte length and bounded value for both columns: `typeof(column)`, `length(CAST(column AS BLOB))`, and `CASE WHEN length(CAST(column AS BLOB)) <= CAP THEN CAST(column AS BLOB) END`. Fetch TEXT as BLOB bytes too; keep its original type for decoding/writing. Value and length check share one statement snapshot. A projected NULL from overflow is a `resource_limit` failure, never JSON null; reject other SQL storage classes as `unsupported_storage`. This bounds fetched values and avoids SQLite decoding malformed TEXT before a row handler runs.

Also project `typeof(host)`/`typeof(event_type)` and bounded BLOB values/lengths (256 bytes per field). Require both original SQL types to be `text`, within cap and strict UTF-8; otherwise the entire row gets `unsupported_context` before any sanitizer call. Do not turn a BLOB context into a registered string. Pass valid stored context even when `host_basis` is NULL, without promoting attribution.

Add a public `pii.is_replay_safe_history_context(*, host: str | None, event_type: str | None) -> bool`, derived directly from the existing protocol-rule registry. True means the registry supplies replay-protecting rules: string context for Claude-shaped/Kimi hosts and registered native/normalized Codex types. Missing/non-string context, unknown Codex types and unregistered hosts are false. No maintenance-local type list or private-registry calls; no sanitizer policy/version/error-vocabulary change. Unsupported context refuses even an otherwise no-op row, advances progress, increments `failed` and exposes no arbitrary context values.

### Bounded decode, sanitize and encode

Process columns sequentially; release decoded source/sanitized objects before decoding the sibling. Compressed BLOBs use checked `decompressobj`, bounded to decoded-cap + 1 to detect overflow. Require EOF and no unconsumed/unused bytes; truncated/trailing/concatenated streams refuse. TEXT and decompressed bytes use strict UTF-8, JSON object roots, unique object keys and finite numbers. Keep existing sanitizer depth/node limits; these act **after** JSON decoding and do not bound prior structural allocations. No new nesting scanner or shared replay-codec rewrite.

At the `json.loads` boundary only, use maintenance-owned duplicate-key/non-finite-constant hooks; map decoding `ValueError` (including `JSONDecodeError` and Python's long-integer conversion limit) to `invalid_json`, and `RecursionError` to `resource_limit`. Do not broaden this catch around the sanitizer/program/backend or swallow `MemoryError`. Map policy failures separately from `HistorySanitizationError.reason` and codec/UTF-8 failures to fixed codes, suppressing content-bearing exception chains.

`HistoryRedactionResult` has `payload` and `counts`, no changed flag; it returns a fresh equal object for no-op input. Use empty `counts` as the no-change signal. Comparing reserialized JSON with stored bytes would incorrectly normalize whitespace/order. Discard both columns' planned counts/replacements if either fails validation. If neither changes, issue no UPDATE.

For changed columns serialize with `json.dumps(payload, ensure_ascii=True, allow_nan=False)` (no indent), yielding ASCII JSON. Preserve original storage class: TEXT stays text; BLOB stays zlib-compressed bytes. Revalidate each replacement with the bounded strict decoder and the same stored/decoded caps before scheduling it, so successful output remains maintainable on a rerun. No truncation or opportunistic sibling reencoding. Preview validates output and single-row write-request fit just as apply does.

### Resource bounds and request packing

Use named constants with rationale comments, no user settings:

| Dimension | Bound |
|---|---|
| Stored payload / decoded payload | 1 MiB / 4 MiB per column |
| Host / event type | 256 stored bytes each |
| Value-returning page | At most `min(batch_size, 8)` rows |
| Fetched original payload bytes | At most 16 MiB per page |
| Retained encoded replacements | At most 8 MiB |
| Serialized outbound write request | At most 8 MiB, including SQL/protocol overhead |
| Retained problems | 100 entries, plus uncapped omitted count |

Original page and replacement budgets may coexist; guards reference original page bytes without copying. Flush pending candidates before exceeding replacement/request bounds, and finish a page's writes/reconciliation before fetching the next scan page. Greedily split a page into one or more fitting requests; each request is its own atomic acknowledgement/reconciliation unit. There is no separate 200-row write subchunk: the page already caps rows at eight. Reconciliation reads one candidate at a time with the same capped projections and releases each observation before the next.

Use a **conservative wire-byte upper bound**, not a claim to serialize/validate the exact final outbound body in maintenance. Size encoded parameter components (the public Hrana `encode_value` helper is available), encoded SQL, and fixed per-step/envelope overhead covering begin/commit/rollback, conditions, close and pipeline wrapping. Pin the estimator against captured real `_post` bodies for both `executemany` and single-row retry `execute`: estimate >= actual body bytes <= request cap. Do not duplicate transaction builders, add a serializer API or call private client methods.

BLOB data expands by `4 * ceil(n / 3)` plus wrappers. Changed TEXT JSON is ASCII: its outer JSON escaping costs at most twice its byte length plus wrappers. Arbitrary context TEXT retains a general sixfold bound or its measured encoded component size. Old payload guards are always BLOB/base64. With these choices, even two 1 MiB TEXT replacements plus two 1 MiB original guards fit alone under 8 MiB with bounded overhead (~6.7 MiB); avoid a blanket sixfold replacement estimate that needlessly refuses conforming rows. A truly over-budget single row is `resource_limit` in both modes, and no oversized request is sent. Pin non-ASCII source/context, DEL/control escapes, quotes/backslashes, base64 and cap boundaries.

Capped BLOB projections derive a <=32 MiB conforming read-response envelope for eight two-column rows plus bounded metadata/headroom; pin captured stub responses. Hrana reads whole response bodies and has no response-size limiter, so this is not a malformed/unexpected-server transport guarantee. These input/page/replacement/request bounds do not promise total Python RSS or database-engine memory bounds; JSON objects and serialization buffers can exceed input sizes.

### Guarded persistence and reconciliation

Use short explicit local transactions and remote `conn.executemany` (selected Option A), never `conn.client.batch` or remote interactive transaction assumptions. Payload columns are NOT NULL; a bound SQL NULL means retain the unchanged sibling without retransmission/reencoding:

```sql
UPDATE raw_events
SET raw_line = COALESCE(?, raw_line), parsed_json = COALESCE(?, parsed_json)
WHERE id = ? AND typeof(raw_line) = ? AND CAST(raw_line AS BLOB) IS ?
  AND typeof(parsed_json) = ? AND CAST(parsed_json AS BLOB) IS ?
  AND typeof(host) = 'text' AND host IS ?
  AND typeof(event_type) = 'text' AND event_type IS ?
```

Bind guard payloads as original BLOB bytes, replacement values in original TEXT/BLOB types, and validated context as strings. Candidate IDs are unique; each primary-key statement affects at most one row. A full summed count proves every guard matched; fully acknowledged committed units are never retried. Negative/greater-than-candidate counts are `backend_invariant` and stop the run. Locally acknowledge counts only after commit; an acknowledged rollback contributes zero. A short count is a committed unit with misses, not a rollback. Remote transport/response failure can have unknown commit outcome; no-op `rollback` does not resolve it.

For a short acknowledgement or ambiguous remote outcome, re-read every candidate with bounded bytes/types/context and classify:

| Observed state | Action |
|---|---|
| Exact desired bytes/types and unchanged context | `reconciled`; infer no own-write/rule attribution |
| Exact original bytes/types/context | At most one guarded per-row `execute` retry; ack 1 attributes a write; ack 0 gets one final bounded re-read |
| Different bytes/type/context | Conflict; do not overwrite |
| Missing row | Vanished/conflict; do not claim sanitized |
| Read/retry outcome unavailable | Unconfirmed; stop incomplete |

Never retry against newly observed arbitrary values. A second zero acknowledgement is a conflict even if the final read is again original; ABA can explain it, so this is not proof of a broken backend guard. A final desired observation can reconcile it. Impossible acknowledgements stop as invariants. Respect request bounds on retries too. Apply the same typed/context guards locally; known committed guard misses use the same bounded classification.

### Reporting and counter units

`scanned` counts each processed keyset row once, including rejects. `would_change` counts valid candidate **rows**, not columns, in both modes. `failed`, `conflicts` (including vanished), and `unconfirmed` count affected candidate/validation IDs once each in their category, never operation-level errors; diagnostics may have multiple column entries per row. A failed sibling contributes no candidate/removal counts.

`updates_applied` counts acknowledged **committed UPDATE applications**, not distinct rows. A full acknowledgement contributes the whole unit and exact per-column/rule counts. A short acknowledgement contributes its affected sum to both `updates_applied` and `unattributed_updates_applied`, without a guessed rule breakdown. A per-row retry ack 1 contributes one attributed application and exact counts. Committed-but-unacknowledged desired observations are `reconciled`, not invented acknowledged writes.

`counts_complete=false` whenever a short positive count or ambiguous commit prevents exact write/rule attribution. Confirmed counters are lower bounds then; `counts_by_column` excludes anonymous applications and reconciled observations. A scan/read/validation failure alone does not create write-attribution uncertainty; `complete` separately captures coverage/failures. Preview reports planned removals in valid candidates, `updates_applied=unattributed_updates_applied=reconciled=0`, without a persistence claim. Empty/no-op columns and existing placeholders count zero; duplicate spans across columns count separately.

`reconciled` counts candidate IDs observed exactly desired during reconciliation and may overlap acknowledged work. ABA example: A/B candidates, short ack 1 updated A; another writer restores A and makes B desired; retry A acknowledges 1. Report `updates_applied=2`, `unattributed_updates_applied=1`, `reconciled=1`, and rule counts from A's retry only; only one distinct ID was changed by this invocation. Also cover A remaining desired while B's retry succeeds. Do not claim an additive partition or `updates_applied + reconciled == would_change`.

Pin `0 <= unattributed_updates_applied <= updates_applied`; the attributed difference and `reconciled` are each <= `would_change`; applications <= candidates plus attempted retries. Because full-ack units never retry and each ID has at most one retry, `updates_applied - unattributed_updates_applied` is a conservative lower bound on distinct IDs with attributed successful redactions. Per-rule counts describe attributed applications, not unique original secrets.

`complete` means scan exhaustion through the snapshot bound with no failed/conflicted/vanished/unconfirmed work or stop reason. `MAX(id)` defines an ID boundary: later autoallocated IDs are excluded, while explicit inserts at/below that boundary may be observed if their position has not passed. It does not isolate concurrent updates or the whole table; a later writer can change an observed row. Never claim simultaneous database-wide cleanliness. Upgrade writers first and rerun after relevant activity. `last_scanned_id` is the last processed/rejected ID, which can be below the maximum after deletions. Empty snapshots have both cursor fields `None` and `scanned=0`.

Keep at most 100 problems in encounter order; increment `omitted_problems` for every additional diagnostic. Operation-level problems use `row_id=None`. **`stop_reason` is independent of this cap**: `None` (scan exhausted), `interrupted`, `target_unavailable`, `schema_mismatch`, `backend_failure`, `backend_invariant`, or `unconfirmed`. A row failure can leave `stop_reason=None` but `complete=false`; a stopped run cannot be complete. Never derive exit status from a retained diagnostic or hide a fatal stop when the list is full.

### Interruption, errors and cleanup

Track pending acknowledgement/accounting state through the commit and counter transition. Local writes use explicit BEGIN; before issuing commit retain pending candidates and a commit-issued marker. On interruption, a pending batch with an active transaction contributes zero **only after rollback is acknowledged**. If commit was issued and the transaction is already closed before accounting completes, or rollback fails/is interrupted, its outcome is unconfirmed: no invented application/rule count, `counts_complete=false`, and affected candidates counted unconfirmed. The same applies to an unacknowledged remote in-flight write. Drop the blanket claim that every interrupted local batch can be rolled back. Counter/accounting transitions must not leave half-applied report invariants if SIGINT arrives between Python bytecodes.

Handle `KeyboardInterrupt` before the general `BaseException` cleanup/re-raise path. After snapshot capture, return accrued confirmed counts with `complete=false` and `stop_reason='interrupted'`; before capture, raise a content-free `HistoryError('interrupted') from None` for the CLI's safe error object. Do not reconcile over the network after interruption. Other unexpected `BaseException`s clean up and propagate without a fabricated success. A backend failure after snapshot likewise returns accrued incomplete counters and an independent stop reason; pre-snapshot failure raises a safe fixed-code `HistoryError` without invented snapshot/counter fields.

Pin closed `RAW_REDACTION_REASONS`: existing `HISTORY_ERROR_REASONS` plus `unsupported_context`, `unsupported_storage`, `invalid_encoding`, `invalid_compression`, `invalid_json`, `conflict`, `vanished`, `unconfirmed`, `backend_failure`, `backend_invariant`, `schema_mismatch`, `target_unavailable`, `interrupted`. Pin the smaller stop vocabulary above separately. Only row ID, payload-column name (or None) and code appear in failures; no source/session IDs, arbitrary keys/context, backend exceptions or content-bearing tracebacks. Redact-only error mapping suppresses exception chains and never prints arbitrary `HistoryError` messages. Public batch errors are `ValueError`; CLI errors are argparse usage errors.

After successful argument parsing, JSON mode emits exactly one report/error object on stdout, including incomplete runs. Fatal pre-snapshot errors are `{"complete": false, "error": "<stop reason>"}`. Human guidance goes to stderr. Exit 0 for complete, 130 for `interrupted`, otherwise 1; pre-snapshot errors use the same rule. Argparse usage errors remain exit 2 with stderr usage and no stdout report. Library callers receive the same explicit interrupted report after snapshot, rather than losing it in a raised KeyboardInterrupt.

Print/document the supported-match, raw-column-only logical guarantee and exclusions: derived/FTS/summary/live rows, original transcripts, backups, WAL/free pages and provider history. No automatic rebuild: retention/replay holds can make it destructive and it does not clean every excluded copy. A deliberate later rebuild derives only its covered tables from available redacted rows. ENH-3750 -> ENH-3751 -> ENH-3752 remains the deployment order across installed writers; the first two are now implemented here.

## Program Design

### Signatures

Proposed new public API/report types (not existing symbols):

```python
@dataclass(frozen=True)
class RawRedactionProblem:
    row_id: int | None
    column: str | None
    reason: str

@dataclass(frozen=True)
class RawRedactionReport:
    policy_version: int
    target: dict[str, str]
    dry_run: bool
    snapshot_max_id: int | None
    last_scanned_id: int | None
    scanned: int
    updates_applied: int
    would_change: int
    counts_by_column: dict[str, dict[str, int]]
    counts_complete: bool
    unattributed_updates_applied: int
    reconciled: int
    failed: int
    conflicts: int
    unconfirmed: int
    problems: tuple[RawRedactionProblem, ...]
    omitted_problems: int
    stop_reason: str | None
    complete: bool

def redact_raw_events(
    db: Path | str | HistoryTarget = DEFAULT_DB_PATH,
    *, batch_size: int = 2000, dry_run: bool = False,
) -> RawRedactionReport: ...
```

`HistoryTarget` is imported from `session_store.targets`/`backend`, not currently re-exported by `session_store`. `policy_version` is `HISTORY_REDACTION_VERSION`. Validate row/stop codes and count invariants in tests. The public function raises fixed-code `HistoryError` only before a snapshot exists for expected maintenance failures; thereafter it returns an incomplete report with accrued counts. Batch argument validation remains `ValueError`.

### Call Path

`main_session` -> `_main_session` parse once -> redact-only handler outside telemetry -> `redact_raw_events` -> one resolved target -> strict preflight/open -> nullable snapshot/keyset -> bounded context/decode/sanitize/encode -> per-request guarded writes/reconciliation -> safe report. Export the function and both report types through `session_store/__init__.py`.

## Integration Map

### Files to Add/Modify

| File | Responsibility |
|---|---|
| `scripts/little_loops/session_store/raw_redaction.py` (new) | Core, bounds, wire estimator, guarded persistence/reconciliation, reports/reasons |
| `scripts/little_loops/session_store/backend.py` | Non-creating writable local open at the existing connection chokepoint; no new refusal |
| `scripts/little_loops/pii.py` | Add the public registry-derived context-support query only |
| `scripts/little_loops/session_store/__init__.py` | Explicit import block and `__all__` for the new public API/types |
| `scripts/little_loops/cli/session.py` | Module-level maintenance import for dispatch mocks; parser, one parse before telemetry, safe handler, help/subcommand list/epilog |

### Dependent Files and Similar Patterns

- `session_store/db.py`/`targets.py`/`backend.py` own target/error seams; `libsql.py`/`hrana.py` own backend guards and atomic batches. Use their existing surfaces, without new per-step results or backend wrappers.
- `lifecycle.recompress_raw_events` models local codec maintenance only; do not copy its remote refusal/unconditional ID update. `writers._pack_payload`/`_unpack_payload` define storage semantics, not bounded maintenance decoding.
- `usage_refresh`'s current `_decode_stored_payload`, `_stored_payloads`, `_canonical_payload`, `_payload_equal` and `_preserves_fields`, plus lifecycle Codex first-cursor certification, own landed ENH-3751 compatibility. Their semantics/tests are regression models; their unchecked decompression cannot satisfy the maintenance bounds, so do not reuse that decoder directly or edit replay helpers here.
- `_positive_int` in `cli/history.py` models argparse validation; newer frozen reports and `dataclasses.asdict` model JSON conversion. Existing migrate bypass models telemetry placement only, not target selection (`_main_migrate` ignores `args.db`).
- `hooks/scripts/record-hook-event.sh` and `init/writers.py` permissions already cover every subcommand through the `ll-session` prefix; no hook/plugin/entry-point or command edit. Use existing target configuration, including literal URL or URL/token env-variable names and project ID; no new config keys/dependency.

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| CLI | Valid existing commands' target/capture behavior and migrate fast path | Add no-telemetry redact; parse before capture | Help/usage-error telemetry |
| Raw rows/backend | Metadata, IDs, cursors/watermarks, typed guards | Explicit in-place supported raw-string removals | Matched spans in successfully changed columns |
| Package | Existing exports/replay codecs | Add maintenance API/report types and context query | None |

### Tests and Gates

- `scripts/tests/test_raw_redaction.py` (new): independent TEXT/BLOB and divergent columns, no-op byte/type stability, sibling NULL retention, no source files, compacted rows, second-pass zero writes, byte/context/decompression/JSON bounds, keyset zero/negative/min-int IDs and empty/deleted snapshots, inserts beyond maximum, row failure progress, metadata equality and capped diagnostics/stop causes.
- `scripts/tests/test_pii.py`: proposed context query registry parity, missing/non-string/unregistered hosts, unknown Codex types, native/normalized types, Claude/Kimi string context; unchanged sanitizer/version/vocabulary.
- `scripts/tests/test_session_store_backend.py` and `scripts/tests/test_sqlite_uri.py`: mode-rw open never creates/migrates; strict current-schema preview/apply and target precedence; read-only writes refused; live WAL visible with main/WAL byte equality in controlled tests. Pin current/behind/ahead/missing stores.
- `scripts/tests/test_libsql_backend.py`/`test_remote_schema.py`/`test_remote_ingestion_telemetry.py`: typed/context guards, BLOB `IS ?`, full/short/impossible counts, bounded retries, desired/missing/changed reconciliation, anonymous/ABA count invariants, per-request packing, captured wire/read ceilings and credential canaries. Remote preview necessarily sends reads: assert absence of mutating statements/logical changes, **not unchanged request count**. Cover wrong/missing project stamp and fresh schema checks despite a populated verification cache.
- `scripts/tests/hrana_stub.py`: interleave through its underlying SQLite connection; its post-execution response-body stall commits before stalling the reply. A pre-execution delay is not proof of lost acknowledgement after commit. Real-I/O stall/signal tests use `@pytest.mark.no_parallel` and the serial gate; deterministic failure tests inject at the relevant commit/accounting boundary.
- `scripts/tests/test_ll_session.py`/`test_ll_session_refresh.py`: proposed redact parser/dispatch tests modeled on `TestRecompressSubcommand`, module-level mocks, global `--db` before command, invalid batches, one JSON on row/fatal/interrupt results, safe stderr, no redact telemetry, valid other-command telemetry and help/usage-error routing. Preserve the ENH-3751 outer sanitizer handler contract.
- `scripts/tests/test_enh3751_sanitize_raw_events.py` is the **existing** rollout baseline, including redacted/legacy canonical no-ops and both-column nonsecret preservation. Extend it or new maintenance tests with legacy -> redact -> unchanged refresh/Codex first-cursor certification -> replay/usage parity; include NULL host basis, existing usage qualification, secret-only historical differences and incompatible policy/field-loss refusal. Also use `test_enh3549_codex_usage_refresh.py` fixtures as appropriate.
- `scripts/tests/test_remote_operation_matrix.py`: positive supported-operation test; never add redact to `_REJECTED`. `test_remote_callers_bug3652.py` currently allowlists `('cli/session.py', '_main_session')` for local-only refresh; preserve it without a new redact exemption. `test_history_store_chokepoint_gate.py` forbids raw opens in the new module; do not expand its allowlist.
- `scripts/tests/test_usage_selection_chokepoint_gate.py`/`test_session_reader_no_host_roots_gate.py`: the new module enters their scans; avoid usage SQL and literal transcript roots. `test_session_store_schema.py::TestPackageReexportSurface` checks exports; `test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` pins new CLI/API docs. Fixtures use `LL_HISTORY_DB`/`tmp_path`/explicit non-default targets to protect real history.

### Documentation

Update `docs/reference/CLI.md` (subcommand/flags/examples/counters/exits/remote support), `docs/reference/CONFIGURATION.md` (supported remote logical maintenance), `docs/guides/HISTORY_SESSION_GUIDE.md` (preview/apply, exclusions, writer upgrades and ToC), and `docs/reference/API.md` (public API/reports/context query, nullable cursors and uncertainty). Keep remote retention refusals accurate and no private fixtures/paths or contributor instructions in end-user docs. Add new CLI/API rows to `DOC_STRINGS_PRESENT`; changelog promotion follows release convention, not a new `[Unreleased]` section.

## Implementation Steps

1. **M0 — internal proof before production:** run `/ll:spike ENH-3752` through the public backend and Hrana stub. Prove typed BLOB/context guards, mixed TEXT/BLOB and type-only differences, NULL/COALESCE retention/NOT NULL prerequisites, capped projections, nullable/nonpositive keysets, short counts and bounded retry/reconciliation, committed-but-lost acknowledgement, wire upper bounds for both write shapes, and interruption after local commit but before accounting. Record proof through the spike workflow; retain unproven flags until it succeeds. Stub proof establishes client/SQLite/protocol behavior; hosted-provider parity remains an explicit deployment assumption, not a provider-validation claim.
2. **M1 — pure core:** context-support query, bounded strict decode, sanitize/no-op detection, ASCII serialization/output validation, safe codes and resource estimator. Gate with pure boundary/PII tests.
3. **M2 — local maintenance:** non-creating open/preflight, nullable keyset, short explicit transactions, guards, reconciliation, safe interruption and atomic accounting transitions. Gate with local/URI/metadata/preview tests.
4. **M3 — remote maintenance:** per-request byte packing, public executemany/execute writes, short/ambiguous outcomes, attribution and reconciliation. Gate with deterministic interleavings/captured requests and serial lost-ack tests. Split this milestone only if M0 proves it needs separate scope/review.
5. **M4 — CLI and exports:** one parse before telemetry, report/error/exit routing, package exports and supported remote operation. Gate with CLI/telemetry/export/chokepoint tests.
6. **M5 — rollout and docs:** landed ENH-3751 parity regressions, help/docs/counter/exclusion contracts, focused gates and `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] Both columns scrub independently with original types/unchanged bytes and siblings preserved; second pass writes zero; metadata/links/cursors/watermarks identical; no original files required.
- [ ] Preview/apply honor the resolved target, require current schema/project stamp, never create/migrate, and preview writes neither database data nor telemetry. Help/usage errors also avoid capture; valid existing commands still capture as before.
- [ ] Nullable snapshot/keyset handles empty, zero/negative/min-int IDs and holes without false success or skipped rows. Per-row failures progress; later autoallocated IDs stay outside the captured maximum, without claiming time-based snapshot isolation for explicit-ID inserts.
- [ ] Context SQL type/UTF-8/size and registry support are validated before sanitization, including no-op rows. Policy semantics/version remain unchanged.
- [ ] Guarded per-request units, short/impossible/ambiguous counts, concurrent changes/deletions and one retry never overwrite a refresh or fabricate rule attribution. Captured bytes fit the proven request/read bounds; large `--batch` bypasses none.
- [ ] Reports pin application units, anonymous counts, overlapping observations, ABA inequalities, planned preview counts and independent completeness/stop reason. A full diagnostic buffer cannot hide interruption/fatal state.
- [ ] Interruptions before/after snapshot and during write/commit/accounting return safe one-object output and exit 130. Proven rollback counts zero; closed/failed-rollback local outcomes and remote unknown writes remain unconfirmed, without network reconciliation after interruption.
- [ ] Required internal proof is recorded before production implementation; hosted-provider parity is not inferred from a stub. Post-scrub refresh/certification/replay/usage preserves ENH-3751 behavior.
- [ ] Package/doc/remote/chokepoint gates and the authoritative local suite `python -m pytest scripts/tests/` pass.

### Required Boundary Cases

- Stored/decoded/context values exactly at cap and cap+1; replacement growth beyond caps; bounded zlib bomb/truncated/trailing/concatenated streams; invalid UTF-8 as TEXT/BLOB; SQL NULL/unsupported storage; duplicate keys, non-object/non-finite JSON, long-integer decoder ValueError and excessive nesting. Failed whole rows preserve both independent bytes/types/counts and progress advances.
- Changed SQL type with equal byte representation misses guards; BLOB/non-string/over-cap/invalid-UTF-8 context refuses before policy, as do unknown native Codex types/unregistered hosts. Supported Claude/Kimi and native/normalized Codex pairs work with NULL host basis.
- Single-statement growth cannot bypass projection limits; pending replacements flush rather than overflowing; each split request is accounted/reconciled independently. Capture ASCII output, non-ASCII source/context, DEL/control, quote/backslash and base64 worst cases against real wire bodies.
- Controlled live-WAL preview preserves main/WAL bytes and sees WAL rows; only lock/SHM bookkeeping allowed. Remote preview makes read requests but no writes, cache-file/telemetry/progress changes or migration. Explicit local target under remote config and env/default-shaped precedence resolve consistently.
- Retained diagnostic cap already reached before backend stop/interrupt; empty interrupted snapshot; successful local commit followed by injected KeyboardInterrupt before counters; rollback failure; earlier confirmed batches plus a later unknown unit. Row-level counts stay uncapped and stop_reason drives exit independently of problems.
- ABA and normal short-batch examples distinguish acknowledged applications/anonymous work/observed desired IDs. A second miss never loops; updates plus reconciled can exceed candidate rows without claiming a distinct-row partition.

## Scope Boundaries

Logical raw-column cleanup only. No physical secure erase, engine/RSS bound, malformed-server response guarantee, derived/FTS/live cleanup, source rewrite/re-ingestion, automatic rebuild/VACUUM, whole-table snapshot isolation, durable resume token, schema migration, backend/serializer wrapper redesign, exact rule attribution from summed partial counts, or guarantee covering later writers. Existing valid commands' telemetry behavior is preserved; moving argparse ahead of capture intentionally drops help/usage-error telemetry.

## Impact

- **Priority**: P2 — removes supported legacy raw matches, including shared remote rows.
- **Effort**: Very Large — bounded maintenance/concurrency/reporting across two backends; one public contract with independently gated milestones.
- **Risk**: Medium — ambiguous commits and accounting need proof; guards/refusals preserve source/metadata while logical cleanup remains explicit.
- **Breaking Change**: No API removal; new nullable/report fields belong to an unshipped API. Existing CLI help/usage errors cease telemetry writes.

## Review Notes

Prior reviews on 2026-10-05/06 with `/ll:advise` and `claude-opus-5-5` settled bounded typed/context guards, independent-column retention, Option A on the existing summed-count backend API, unknown-context refusal, logical-only scope and ABA application accounting. This revision retains those decisions while consolidating duplicated research/wiring notes into the current contract and integration map.

Reviewed again on `main`, 2026-10-06, after ENH-3751 landed (`28612c337`), with `/ll:advise --signal user_requested --host claude-code --model claude-opus-5-5` (confidence 0.78). Removed the completed dependency and obsolete integration claims. Added nullable keysets, context SQL-type validation, uncapped stop_reason, conservative local commit/rollback uncertainty, strict decoder ValueError handling and a fixed diagnostic cap. Resolved contradictory exact-wire/upper-bound wording; ASCII replacements keep conforming single-row requests within the cap, while captured full bodies prove the estimator. Accepted parse-before-capture consequences; rejected the advisor's suggested new redact resolver exemption because redact must not call resolve_history_db at all.

Advisor dissent offered an interrupted-report exception as an alternative to a field; the explicit stop_reason keeps library/JSON callers on one report contract. A hosted-provider validation claim and immediate splitting of remote work were not adopted: M0 remains required and provider parity remains an assumption. The local reproductions confirmed nonpositive IDs/BLOB context are legal and a within-cap long integer raises ValueError. Existing policy/ingest regression verification: `python -m pytest scripts/tests/test_enh3751_sanitize_raw_events.py scripts/tests/test_pii.py -q` — **220 passed**. This review adds no production implementation or proof record.

## Confidence Check Notes

Earlier scores/verdicts described pre-ENH-3751 plans and are superseded by this contract; do not reuse them as implementation approval. No unresolved issue dependency remains. `ll-learning-tests assess --issue ENH-3752 --json` reports **absent** (`spike=absent`); `spike_needed: true` and `unproven_mechanism: true` remain. Run M0 and reassess confidence before production implementation.

## Status

**Open** | Created: 2026-10-05 | Priority: P2 | Next prerequisite: M0 spike proof

## Spike Results

_Added by `/ll:spike` on 2026-10-06_

**Retired risks** (M0 proof, run against real SQLite and the public `LibsqlConnection` → `HranaClient` → `HranaStub`)

| Risk (from M0 / Confidence Check Notes) | Proven by | Result |
|------------------------------------------|-----------|--------|
| Typed BLOB guard; type-only difference misses | `TestTypedGuards::test_type_only_difference_misses_guard` | ✓ pass |
| Context `typeof` guard (BLOB host/event_type) | `test_blob_context_misses_text_context_guard` | ✓ pass |
| Mixed TEXT/BLOB, NULL/COALESCE sibling retention | `test_null_param_retains_sibling_bytes_and_type` | ✓ pass |
| NOT NULL prerequisite | `test_not_null_prerequisite_rejects_null_write` | ✓ pass |
| Capped projections (cap / cap+1, invalid-UTF-8 TEXT as bytes) | `TestProjectionAndKeyset::test_capped_projection_bounds_value_and_reports_length` | ✓ pass |
| Nullable / nonpositive / min-int keyset, holes, beyond-max inserts | `test_keyset_nullable_nonpositive_and_holes` | ✓ pass |
| Full / short counts, bounded retry, reconciliation, ABA accounting | `TestAckAndReconcile::*` | ✓ pass |
| Committed-but-lost acknowledgement | `test_committed_but_lost_ack_is_found_desired` | ✓ pass |
| Wire upper bounds (`executemany` + `execute`), 2×1 MiB TEXT fits 8 MiB, 8-row page < 32 MiB | `TestWireBounds::*` | ✓ pass |
| `mode=rw` never creates; ro preview leaves live-WAL main/WAL bytes unchanged | `test_mode_rw_open_never_creates_and_ro_preview_leaves_bytes` | ✓ pass |
| Interruption after commit / before commit / failed rollback | `TestLocalOpenAndInterrupt::*` | ✓ pass |

**Findings to carry into M1–M3**

- A flat sixfold escaping bound **undercounts non-ASCII context**: astral code points JSON-escape to a 12-byte surrogate pair. The estimator uses 2× (printable ASCII), 6× (ASCII with control chars) and 12× (non-ASCII) per character; use measured `encode_value` size or this tiered bound, not a blanket 6×.
- A direct `SELECT raw_line` on invalid-UTF-8 TEXT raises on both backends; only the `CAST(... AS BLOB)` projection reads it, confirming the bytes-first projection is required.
- An acknowledged local ROLLBACK counts zero; commit-then-interrupt and failed-rollback outcomes are unconfirmed even though the data did commit.
- Accounting transitions as one frozen-state swap keep the counters from being half-applied.

**Spike location**: `scripts/tests/spike/enh3752_raw_redaction/` (plan: `.ll/spikes/spike-ENH-3752.md`)
**Verification**: 37 tests pass (35 AC + 2 guard) plus `test_libsql_backend.py`, `test_sqlite_uri.py` and `test_hrana_client.py` across 4 commands; verdict PROVEN.
**Assumptions not proven**: hosted-provider (Turso/sqld) parity; the stub is SQLite-backed. The lost-acknowledgement test runs without `no_parallel` (0.4 s timeout against a 1.5 s post-commit stall); the serial real-I/O gate remains an implementation-time task.
**Promotion**: fold into its production module under `project.src_dir` and its test under `project.test_dir`, in a separate PR.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

Supersedes the earlier Confidence Check Notes above: M0 is now PROVEN (`ll-learning-tests assess` → proven; `spike_completed`), so the unproven-mechanism cap is suppressed.

### Concerns
- Contract text still specifies a flat sixfold bound for arbitrary context TEXT; the spike proved this undercounts non-ASCII — fold the tiered 2×/6×/12× (or measured `encode_value`) bound into "Resource bounds and request packing".
- Status footer, Review Notes and the older Confidence Check Notes still describe M0 as outstanding; refresh them so the issue does not contradict its own Spike Results.
- Parse-once-before-telemetry changes `_main_session` dispatch for every `ll-session` subcommand; keep the existing telemetry/remote-caller gates green.
- Remote milestone M3 split is left conditional ("only if M0 proves it needs") with no recorded decision now that M0 passed.

### Risk Factor Delta
- Baseline: none recorded

## Session Log
- `/ll:confidence-check` - 2026-10-06T21:10:02 - `4fc0d666-699d-4898-92bb-0f49567df55d.jsonl`
- `/ll:spike` - 2026-10-06T21:03:01 - `abc671b1-1433-4acc-b1c8-d9248434e4e4.jsonl`
- `/ll:confidence-check` - 2026-10-06T09:57:04 - `6e20ecba-9b39-4fa5-a2d1-2716b647e53a.jsonl`
- `/ll:verify-issues` - 2026-10-06T09:55:28 - `5670a7ad-a6f3-4ca8-8442-6031f1500522.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T09:53:43 - `61d58fe9-ad6e-4e80-ba4c-3aba78f84c55.jsonl`
- `/ll:confidence-check` - 2026-10-06T09:45:03 - `516d313f-0876-453e-a4bd-d939284c79cd.jsonl`
- `/ll:verify-issues` - 2026-10-06T09:42:19 - `4eeb9aca-1309-400c-ae28-1d7a375687ea.jsonl`
- `/ll:wire-issue` - 2026-10-06T09:39:00 - `811edce9-fc13-4f33-9a06-63ced28c5602.jsonl`
- `/ll:refine-issue` - 2026-10-06T09:31:38 - `072141b9-68bd-494d-8ef6-a4eb91ff0db1.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:46:34 - `2fc077e6-f247-45dc-97b8-6729a8243496.jsonl`
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
