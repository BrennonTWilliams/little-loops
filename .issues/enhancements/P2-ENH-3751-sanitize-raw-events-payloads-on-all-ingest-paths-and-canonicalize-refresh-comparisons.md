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

Wire the ENH-3750 sanitizer into every `raw_events` insert path so both `raw_line` and `parsed_json` are redacted before serialization/compression/remote transmission, and adapt the Codex certification and source-refresh comparisons so sanitized rows still verify against parser output.

## Parent Issue

Decomposed from ENH-3743: Redact history raw payloads before persistence and provide a resumable scrub. Covers parent **Proposed Solution §2** ("Use the same sanitized representation for inserts and comparisons") and Implementation Steps 2. Depends on ENH-3750 (`sanitize_history_payload`). Under `tdd_mode`, the integration wiring stays in this child with its tests.

## Scope

Follow ENH-3743 Proposed Solution §2 and the Wiring Phase items for ingest/refresh:

- Sanitize once in `_backfill_raw_events()` before `json.dumps()`/`_pack_payload()`, covering local `execute()` and remote `_REMOTE_RAW_INSERT`/`executemany()` branches; apply the same helper in the Claude `refresh_usage_source()` insert. Build relational metadata and producer qualification from the original verified event; both columns get the same sanitized representation.
- Canonicalize stored and parser payloads with the same policy in: `lifecycle._refresh_codex_usage_source()` first-cursor certification (~1467); `usage_refresh._event_signature()/_stored_signatures()/_preserves_fields()`; the column-parity "unchanged" short-circuit (~203) and post-insert signature check (~246) in `refresh_raw_events()`. Keep `_preserves_fields()` active (real field loss still refuses refresh). Test mixed legacy/redacted rows and a later policy extension.
- Tail digests, offsets, inode/device, line numbers, and watermarks keep their meaning.
- Sanitizer failure: never fall back to original content, advance a cursor, or publish a success watermark; roll back the local operation; no input/exception text in diagnostics (`cli/backfill_worker.py` prints `{exc}`).
- Keep `lifecycle._backfill_raw_events` a module attribute with its positional call shape. Keep sanitizer calls out of `rebuild`-reachable functions (`writers._unpack_payload`, `_iter_events*`, `_backfill_*`) or bump `REBUILD_DERIVE_VERSION` and regenerate `rebuild_fingerprint.json`.
- Update stale "verbatim"/"JSON-equal" comments (text only): `lifecycle.py` `_backfill_raw_events` docstring, `usage_refresh.py` module docstring, `session_store/qwen.py`, `writers.py` payload-compression comment, `schema.py` DDL comment. Run `test_enh3678_rebuild_derive_gate.py` after the `writers.py` edit.

## Files

- `scripts/little_loops/session_store/lifecycle.py`, `usage_refresh.py` (+ comment-only edits in `qwen.py`, `writers.py`, `schema.py`)

## Tests

- `test_session_store_lifecycle.py` (local ingest, TEXT/BLOB, replay, dedup, failure recovery; model on `test_backfill_stores_compressed_blobs`)
- `test_remote_ingestion_telemetry.py` (outbound compressed insert payloads via `backfill_raw_events`; keep `test_inserts_are_batched_not_one_round_trip_per_event` under 20 requests)
- `test_session_store_incremental_usage.py`, `test_enh3549_codex_usage_refresh.py`, `test_session_store_usage_refresh.py`, `test_ll_session_refresh.py`
- Existing tests that may break: `test_enh_omp_normalizer.py` (both columns equal), `test_enh3532_codex_rollout_usage.py`, Codex fixture `rollout-interactive.jsonl` (email → `[EMAIL]`), `test_failed_reingestion_rolls_back_existing_rows`, `test_refresh_refuses_parser_output_that_drops_existing_fields`
- Regression-run: `test_enh3731_usage_qualification.py`, `test_enh3656_stored_cache_rate.py`, `test_enh3549_codex_stored_ctx_stats.py`, `test_bug3736_usage_replay_holds.py`
- New: ingest → rebuild → usage totals/identity parity with vs. without redaction

## Docs

- `docs/reference/API.md` (`raw_events / rebuild / compact` section: "JSON-equal" no longer true for matched spans), `docs/ARCHITECTURE.md` (Ingest bullet), `docs/guides/HISTORY_SESSION_GUIDE.md` (`raw_events` row redaction note; "Retention & Pruning" verbatim wording; end-user wording only), `docs/reference/CLI.md` (`refresh` row: re-ingestion re-applies redaction), `docs/reference/CONFIGURATION.md` (Ingestion bullet: default-on payload redaction)

## Acceptance Criteria

- [ ] Each of the three SQL insert sites is exercised with every supported rule family; after decompression neither payload column contains the planted secret; remote tests inspect outbound payloads; nested reasoning/tool data/arrays/escapes covered.
- [ ] Replay yields unchanged usage totals, qualification, and identity; dedup stable.
- [ ] Codex first-cursor certification and `ll-session refresh` work with sanitized/mixed legacy rows and a policy extension; unchanged refresh is a no-op; real nonsecret field loss still refuses; tail/inode/offset proofs still detect truncation/overwrite.
- [ ] Sanitization failures never persist originals or advance success boundaries.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Blocked By

- ENH-3750


## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
