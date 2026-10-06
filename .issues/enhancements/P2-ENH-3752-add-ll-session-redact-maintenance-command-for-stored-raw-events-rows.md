---
id: ENH-3752
title: Add ll-session redact maintenance command for stored raw_events rows
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
parent: ENH-3743
blocked_by:
- ENH-3750
- ENH-3751
labels:
- security
- privacy
- history
decision_needed: false
---

# ENH-3752: Add ll-session redact maintenance command for stored raw_events rows

## Summary

Add `ll-session [--db TARGET] redact [--dry-run] [--batch N] [--json]`: an explicit, bounded, rerunnable scrub of both stored raw payload columns on SQLite and the configured libSQL project store. Report the scanned snapshot, confirmed changes, reconciliation uncertainty, and safe row failures without changing derived data or source boundaries.

## Current Behavior

Verified on branch `main` on 2026-10-05:

- `recompress_raw_events` demonstrates local TEXT/BLOB maintenance but refuses remote, rewrites both columns for compression, and is not a redaction operation.
- `resolve_history_target` supports local and remote targets. `resolve_history_db` requires a filesystem path and cannot be used to pre-resolve a configured libSQL store.
- `LibsqlConnection.executemany` preserves backend access/deadline guards and forwards a summed `rowcount` from atomic `HranaClient.execute_many`. Remote `commit`/`rollback` are no-ops; there is no interactive transaction around arbitrary statements.
- A summed count cannot identify which rows matched guards in a partial batch. Re-reading desired payloads later proves observed state, not which writer produced it. Hrana can commit a batch before a timeout hides its acknowledgement.
- `main_session` wraps commands other than `migrate` in `cli_event_context` before argparse, writing CLI telemetry even for a nominal dry-run and potentially to the default target instead of an explicit `--db` target.
- Before ENH-3751, Codex first-cursor certification compares plaintext source with stored payloads directly. Scrubbing rows before that compatibility wiring can break certification/refresh. This command must ship after ENH-3751, not independently.

## Expected Behavior

- Resolve the requested/configured target once and honor it throughout. Support the remote project's rows from all machines without local fallback or machine-watermark scope filters. Never print endpoint credentials/auth tokens.
- Capture `MAX(id)` once and keyset-scan `id > last_scanned_id AND id <= snapshot_max_id ORDER BY id` with a row limit. Process both columns independently, using the row's host/event type for the ENH-3750 context. Handle legacy TEXT, compressed BLOB, missing original files, compacted rows, and differing payload columns.
- If neither decoded column changes, preserve both original values byte-for-byte; do not normalize JSON whitespace/order, recompress, or merge columns opportunistically. Preserve each column's TEXT/BLOB storage type when changing it. If either column is corrupt/undecodable/invalid/unsafe, leave the whole row unchanged, record a fixed reason, and continue the bounded scan with `complete=false`.
- Update payload columns in place only. IDs, source/session attribution, host/basis, type/timestamp/positions, ordinal, usage contract, compaction/summary links, source cursors, and ingest/derive watermarks remain unchanged. No delete/reinsert, original-file ingestion, automatic rebuild, pruning or VACUUM.
- Dry-run performs zero database/telemetry/progress/schema writes. It uses strict read-only target access and refuses missing/stale stores with migration guidance. `changed=0`; `would_change` and rule counts describe candidates that passed validation. Apply must also avoid silently creating a wrong target; migration is an explicit separate operation.
- Interrupted/backend-failed/conflicted runs remain incomplete with nonzero exit; previously committed batches remain safe. Every new invocation rescans with the current policy, so restarting needs no durable checkpoint/one-time sanitized marker.

## Motivation

New default-on writes do not remove existing plaintext. A logical scrub needs truthful counts and bounded conflict-safe writes across both supported backends; compression or a blanket rebuild would not provide this contract.

## Proposed Solution

### Bounded scan and guarded persistence

Put the maintenance core in a new sibling module rather than growing `lifecycle.py` or editing replay helpers. Preflight the exact resolved target/schema, capture its snapshot, then decode/sanitize rows outside long-held write locks. Enforce both row-count and byte/decompressed-payload/depth bounds; oversized or invalid rows get a safe `resource_limit`/decode reason, not truncated content or an unbounded allocation.

Use short SQLite transactions and the backend-neutral `conn.executemany` remote surface (selected Option A). Remote write subchunks are at most `min(batch_size, 200)` rows and have an explicit serialized-request byte budget including old guard values, new BLOB encodings and protocol overhead. A single row exceeding the supported budget is a reported failure; do not bypass the bound. Local read/work batches also have a byte bound, not only a row limit. No change to the shared decompression/rebuild functions is required: enforce checked decompression in the maintenance path and retain existing codec semantics.

Guard each update against the exact fetched payload values AND the context used to sanitize them; bind original TEXT/BLOB types without reserialization:

```sql
UPDATE raw_events SET raw_line = ?, parsed_json = ?
WHERE id = ? AND raw_line IS ? AND parsed_json IS ?
  AND host IS ? AND event_type IS ?
```

Each primary-key statement can affect at most one row; candidates contain unique IDs. `rowcount == candidate_count` proves the whole batch applied. Reject impossible counts (negative/greater than candidates) as a backend invariant failure. A short count is a known committed batch with guard misses, not a rollback; a transport failure may have an unknown commit outcome. Do not call `conn.client.batch` directly or assume `commit`/`rollback` undoes remote chunks.

On a short acknowledgement or ambiguous remote outcome, re-read every candidate (including context) and classify:

| Current state | Action |
|---|---|
| Exact desired payload and unchanged context | `reconciled`; no own-write/per-rule attribution inferred |
| Exact original payload and context | One bounded guarded per-row retry via `execute`; acknowledgement of 1 has exact attribution; another miss is re-read once |
| Different payload/context | Conflict; leave it untouched and report incomplete |
| Missing row | Vanished/conflict; do not claim it was sanitized |
| Read/retry outcome unavailable | Unconfirmed; stop safely with incomplete report |

Never retry against newly observed arbitrary payloads or overwrite a source refresh. Do not retry forever. Under SQLite apply the same guard discipline; update and acknowledgement counts become durable only after local commit, and a rolled-back batch contributes zero committed changes.

### Report and count semantics

Retain the parent's core report fields and add explicit uncertainty/progress fields. A successful acknowledged batch contributes its summed affected rows to `changed`. When every candidate is acknowledged, its per-column/rule counts are attributable and included. For an acknowledged short batch, add its affected sum to `changed` and `unattributed_changed`, but do not infer the rule breakdown from a later read. Per-row retry acknowledgements add exact rule counts. A committed-but-unacknowledged desired row is `reconciled`, not an invented `changed` write.

`changed` and apply `counts_by_column` are confirmed lower bounds when `counts_complete=false`; the latter excludes unattributable batch writes and reconciled rows. `counts_complete=false` whenever a short batch with positive affected count or an ambiguous commit prevents exact attribution. Empty/no-op columns and already-redacted placeholders contribute zero. Duplicate spans across columns are intentionally counted separately. Dry-run counts are planned removals in valid candidate rows; it makes no confirmed-persistence claim and retains `changed=0`.

`complete` describes scan coverage/current-policy results as observed row by row: reached the reported snapshot with no failed, conflicted/vanished, or unconfirmed rows. It may be true after successful reconciliation even when exact write/rule attribution is unavailable; `counts_complete` keeps those claims separate. `MAX(id)` bounds concurrent inserts, not updates or an isolated whole-table snapshot. A writer can change a previously observed row; do not claim simultaneous database-wide cleanliness. Upgrade writers first and rerun after relevant concurrent activity.

Keep `last_scanned_id`, snapshot boundary and bounded reason-only row problems in reports. A per-row validation failure must not stall keyset progress or be hidden by an end-of-scan success. Bound the retained diagnostic list with an omitted-problem count so corrupt large stores do not defeat bounded memory.

### CLI, context, and rollout

Run the redact dispatch outside `cli_event_context` for both apply and dry-run, using parsed command selection so global `--db` before `redact` works. Do not refactor other command telemetry in this issue. Use strict read-only opens for preview; apply requires the existing/current schema and a writable backend connection to that same resolved target. Keep `redact` out of `_REMOTE_REFUSALS` and do not use `resolve_history_db` or `refuse_on_remote` on this path. Positive `--batch` is validated in the CLI and public API (reject bool/zero/negative values).

Pass known stored host/event type even when `host_basis` is null; do not promote attribution. For missing/unknown host context that cannot support replay-safe policy application, leave the row unchanged with `unsupported_context`. Never guess the ambient host or silently apply generic mode and claim replay safety.

JSON mode emits exactly one report/error object on stdout, including incomplete runs; human guidance belongs on stderr. Failures expose row ID, payload-column name and finite reason codes only, not source/session IDs, arbitrary keys, raw backend exceptions or content-bearing tracebacks. Return 1 for incomplete/backend failures; interruption must not emit a successful complete report. Reports identify local path or remote provider/project without auth material.

Print/document the supported-match, raw-column-only logical guarantee and exclusions: derived/FTS/summary/live rows, original transcripts, backups, WAL/free pages, and provider history. No automatic `rebuild`: retention/replay holds can make it destructive, and it does not clean every excluded copy. A deliberate later rebuild derives only the tables it covers from available redacted rows. Shipping order is ENH-3750 -> ENH-3751 -> ENH-3752; the core can be developed separately, but the CLI is not safe to roll out before the compatibility wiring.

## Program Design

### Signatures

Proposed new dataclasses/API:

- `redact_raw_events(db: Path | str | HistoryTarget = DEFAULT_DB_PATH, *, batch_size: int = 2000, dry_run: bool = False) -> RawRedactionReport`

```python
@dataclass(frozen=True)
class RawRedactionProblem:
    row_id: int | None
    column: str | None
    reason: str  # finite content-free reason code

@dataclass(frozen=True)
class RawRedactionReport:
    policy_version: int
    target: dict[str, str]
    dry_run: bool
    snapshot_max_id: int
    last_scanned_id: int
    scanned: int
    changed: int
    would_change: int
    counts_by_column: dict[str, dict[str, int]]
    counts_complete: bool
    unattributed_changed: int
    reconciled: int
    failed: int
    conflicts: int  # includes vanished candidates
    unconfirmed: int
    problems: tuple[RawRedactionProblem, ...]
    omitted_problems: int
    complete: bool

def redact_raw_events(
    db: Path | str | HistoryTarget = DEFAULT_DB_PATH,
    *,
    batch_size: int = 2000,
    dry_run: bool = False,
) -> RawRedactionReport: ...
```

`scanned` counts each fetched row once; `would_change` counts valid candidate rows rather than columns, in both modes; confirmed counters advance after commit/acknowledgement. Failure before a snapshot is obtained raises a safe `HistoryError` for the CLI's single structured error object. Expected per-row failures return the incomplete report, not a traceback.

### Call Path

`main_session` -> parsed redact dispatch outside telemetry -> `redact_raw_events` -> one resolved target -> strict preflight/read or writable connection -> snapshot/keyset read -> independently unpack/decode/sanitize both columns with row context -> guarded bounded writes/reconciliation -> report. Export the public function/report types through `session_store/__init__.py`.

## Integration Map

### Files to Add/Modify

- `scripts/little_loops/session_store/raw_redaction.py` (new file) — maintenance/report core; avoids sharing `lifecycle.py` edits with ENH-3751.
- `scripts/little_loops/session_store/__init__.py` — imports and `__all__` exports.
- `scripts/little_loops/cli/session.py` — parser, dispatch before telemetry, imports, module subcommand list/epilog, safe single-document reporting.

### Dependent Files and Similar Patterns

`session_store/backend.py` / `db.py` / `targets.py` supply target/connection/error seams; `libsql.py` / `hrana.py` supply guarded atomic batches. Use their existing APIs, not a new backend/per-step wrapper. `lifecycle.recompress_raw_events` is a local codec-maintenance example only; `writers._pack_payload` / `_unpack_payload` define codec semantics but must not gain new replay-time policy. `_positive_int` in `cli/history.py` is an argparse validation model.

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| `cli/session.py` | Existing subcommands' target/telemetry behavior | Add redact with explicit no-telemetry dispatch and strict preview | None |
| Stored rows/backend | Metadata, raw IDs, cursors/watermarks, local/remote guard semantics | In-place supported raw-string removal only | Matched spans in successfully updated columns |
| `session_store/__init__.py` | Existing package reexports | Add maintenance API/report types | None |

### Tests

- `scripts/tests/test_raw_redaction.py` (new file) — local TEXT/BLOB, independent divergent columns, byte/type-preserving no-op, compacted/missing-original rows, zero second-pass writes, strict read-only dry-run (no file creation/schema/telemetry), batch/API validation, corrupt/invalid/non-object JSON, unsafe key/identity, unknown-context and resource errors. Snapshot/keyset holes, inserts beyond snapshot, per-row failures with continued progress, rollback/interruption and metadata equality.
- `scripts/tests/test_libsql_backend.py` / `test_remote_ingestion_telemetry.py` — exact fetched guard types/context; full and short counts with mixed rule families, concurrent redactor/source refresh/deletion, bounded per-row retry, impossible rowcount, desired-state reconciliation, and committed-but-unacknowledged timeout. Assert lower-bound/attribution counters and completeness independently; cap rows, request bytes and diagnostic memory.
- `scripts/tests/hrana_stub.py` supplies a post-execution response-body stall for committed-but-unacknowledged timeouts and an underlying SQLite connection for interleaving guard misses. Its pre-execution delay alone is not proof of a committed write; use fault timing deterministically.
- `test_ll_session.py` (`TestRecompressSubcommand` model) / `test_remote_schema.py` — CLI with configured remote, explicit `--db`, malformed batches, JSON incomplete/fatal reports, reason-only diagnostics, no telemetry in either mode.
- `test_remote_operation_matrix.py` — supported remote operation; never add redact to its rejection table. `test_remote_callers_bug3652.py` — preserve target-aware caller gate. `test_session_store_schema.py::TestPackageReexportSurface` / `test_wiring_reference_docs.py` — public exports/help/docs.
- Rollout regression: ingest with ENH-3751 -> redact -> unchanged source refresh/Codex first-cursor certification -> replay/usage parity. Include legacy-null host basis, canonical secret-only differences, and incompatible policy/field loss refusal.

### Documentation

`docs/reference/CLI.md` (subcommand/flag table, examples, counters, exit contract and remote support), `docs/reference/CONFIGURATION.md` (supported remote maintenance), `docs/guides/HISTORY_SESSION_GUIDE.md` (section/ToC, preview/apply, exclusions and writer-upgrade order), and `docs/reference/API.md` (API/report and lower-bound semantics). No private source paths/secret fixtures in end-user docs.

### Configuration

Use existing target configuration. No schema migration, durable progress marker, new dependency, automatic maintenance hook or user-configurable policy bypass.

## Implementation Steps

1. Add local/remote report/guard/count tests, including strict preview and concurrency/timeout attribution cases.
2. Implement bounded independent column decoding and keyset scanning with safe per-row problems.
3. Implement short local transactions and Option A remote batches with exact-value/context guards, bounded reconciliation/retry and truthful counters.
4. Add package exports and no-telemetry CLI dispatch with safe JSON/error/exit behavior.
5. Document the logical guarantee, counts/uncertainty and rollout order; run focused backend/CLI/parity gates and `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] Both TEXT/BLOB columns are scrubbed independently with original types/unchanged bytes preserved; rerun makes zero writes; metadata/links/cursors/watermarks are identical and no original files are required.
- [ ] Preview performs no payload/schema/progress/telemetry writes or target creation, resolves the actual requested/configured store, and rejects invalid batch sizes safely.
- [ ] Guards bind exact original values/types and context; concurrent changes/deletions, short counts, impossible counts, ambiguous commits and bounded retries never overwrite another writer or fabricate per-rule attribution.
- [ ] Reports separate confirmed/lower-bound writes, unattributed changes, reconciled state and exact count availability; row failures/unconfirmed work make the scan incomplete/nonzero with content-free diagnostics and bounded memory/work/requests.
- [ ] Snapshot/keyset/interruption behavior is rerunnable and truthfully bounded; help/docs/JSON state the observation boundary, raw-only exclusions and ENH-3751-before-maintenance rollout.
- [ ] Post-scrub refresh/certification/replay remains compatible; package/doc/remote operation gates and `python -m pytest scripts/tests/` pass.

## Scope Boundaries

Logical raw-column cleanup only. No physical secure erase, derived/FTS/live cleanup, source rewrite/re-ingestion, automatic rebuild/VACUUM, whole-table snapshot isolation, durable resume token, schema migration, backend wrapper redesign, exact per-rule attribution from summed partial counts, or guarantee covering later concurrent writes.

## Impact

- **Priority**: P2 — removes supported legacy raw matches, including shared remote rows.
- **Effort**: Medium/Large — backend-neutral maintenance with bounded remote reconciliation and precise reporting.
- **Risk**: Medium — concurrent writes and ambiguous acknowledgements need explicit semantics; fail-safe guards avoid destructive source/metadata changes.
- **Breaking Change**: No API removal; the new command changes only explicitly requested raw payloads.

## Review Notes

Reviewed on `main`, 2026-10-05, with `/ll:advise` using `claude-opus-5-5`. Added the ENH-3751 blocker, strict no-write preview, typed/context guards, explicit bounded reconciliation, and truthful lower-bound counters. Retained Option A on the guarded backend surface rather than expanding Hrana wrappers or attributing writes from later observations. No automated derived cleanup is implied.

## Blocked By

- ENH-3750
- ENH-3751

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
