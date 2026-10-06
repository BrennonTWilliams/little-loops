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
labels:
- security
- privacy
- history
decision_needed: false
---

# ENH-3752: Add ll-session redact maintenance command for stored raw_events rows

## Summary

Add `ll-session redact [--dry-run] [--batch N] [--json]` and `redact_raw_events()`: an explicit, bounded, rerunnable pass that scrubs existing `raw_events` payload columns on SQLite and the configured libSQL project store using the ENH-3750 sanitizer.

## Parent Issue

Decomposed from ENH-3743: Redact history raw payloads before persistence and provide a resumable scrub. Covers parent **Proposed Solution §3** ("Provide explicit logical raw-row maintenance"), the Decision Rationale (Option A) and Implementation Steps 3–5 for the CLI. Depends on ENH-3750; independent of ENH-3751 (can run in parallel).

## Scope

Follow ENH-3743 Proposed Solution §3, Decision Rationale, and Wiring Phase CLI items:

- `RawRedactionReport` dataclass (`policy_version, snapshot_max_id, scanned, changed, would_change, counts_by_column, failed, conflicts, complete`) and `redact_raw_events(db, *, batch_size=2000, dry_run=False)`.
- Resolve the target once (`resolve_history_target`, branch on `RemoteTarget`; not `resolve_history_db`); support SQLite and libSQL; do not call `refuse_on_remote`; keep `redact` out of `_REMOTE_REFUSALS` / `test_remote_operation_matrix.py::_REJECTED`.
- Capture `MAX(id)` at start; keyset-page by `id` through that snapshot; read both columns independently via `_unpack_payload()` (TEXT + BLOB, divergent columns preserved); update payload columns only (no delete/reinsert, re-ingest, rebuild, or metadata/watermark changes).
- Short SQLite transactions; remote guarded `UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = ? AND raw_line IS ? AND parsed_json IS ?` via `conn.executemany()` in bounded chunks, compare summed `rowcount` to chunk size, re-read on a short count and classify conflicted vs already-sanitized (**Option A — `HranaClient.batch` is rejected**). Ambiguous remote commit is retried safely.
- Dry-run writes nothing; counts reflect confirmed persistence only; per-rule/per-column counts; corrupt/undecodable/collision/unsafe-identity rows remain unchanged, report row-ID + reason, make the run incomplete with nonzero exit.
- CLI in `cli/session.py`: parser, dispatch (`try/except HistoryError`, exit 1 on incomplete like `refresh`/`migrate`), module docstring list, epilog examples, import block; positive-int `--batch` type (`_positive_int` in `cli/history.py`); disclose that `cli_events` is still written (or run outside `cli_event_context` as `migrate` does). Print/document the raw-only logical guarantee and exclusions (derived/FTS/summary rows, transcripts, backups, WAL/free pages, remote provider history; `rebuild` after `redact` re-derives from placeholders).
- Export `redact_raw_events` in `session_store/__init__.py` import block and `__all__`.

## Files

- `scripts/little_loops/session_store/lifecycle.py` (or a sibling module), `session_store/__init__.py`, `scripts/little_loops/cli/session.py`

## Tests

- `test_session_store_lifecycle.py` (local cleanup; model on `test_recompress_converts_legacy_rows_and_preserves_rebuild` / `test_recompress_is_idempotent`)
- `test_libsql_backend.py` (guarded-update atomicity; ambiguous commit via `HranaStub` fault hooks; conflict by seeding a changed row through `stub.db`), `test_remote_ingestion_telemetry.py`
- `test_ll_session.py` (`TestRecompressSubcommand` template; `--batch 0` rejection), `test_remote_schema.py` (~244–269) template for a remote CLI test
- `test_remote_operation_matrix.py` (positive remote case in `TestSupportedOperations`), `test_remote_callers_bug3652.py` (reword `_CALLER_ALLOWLIST` reason if justification changes), `test_session_store_schema.py::TestPackageReexportSurface`, `test_wiring_reference_docs.py` (`DOC_STRINGS_PRESENT` row for `ll-session redact`)

## Docs

- `docs/reference/CLI.md` (row, `**\`redact\` flags:**` table + prose, examples, remote-refusal exception), `docs/reference/CONFIGURATION.md` (`redact` as supported remote maintenance), `docs/guides/HISTORY_SESSION_GUIDE.md` ("Redacting stored payloads" section + ToC; end-user wording)

## Acceptance Criteria

- [ ] Handles legacy TEXT and compressed BLOBs, divergent columns, missing source files, compacted rows without changing metadata, links, cursors, or watermarks; a second pass makes zero changes; dry-run makes no writes; counts are per rule/column.
- [ ] Local/remote batch interruption, corrupt payloads, concurrent guarded-update conflicts, and ambiguous remote commits are tested; rerun completes; incomplete runs exit nonzero with no plaintext diagnostics.
- [ ] Resolves requested/configured target, reports its snapshot, makes no SQLite-only maintenance call remotely; help/docs/output state the raw-only guarantee and exclusions.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Blocked By

- ENH-3750


## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
