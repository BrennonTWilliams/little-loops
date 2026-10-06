---
id: ENH-3743
title: Redact history raw payloads before persistence and provide a resumable scrub
type: ENH
priority: P2
status: done
discovered_date: '2026-10-05'
labels:
- security
- privacy
- history
learning_tests_required:
- hypothesis
decision_needed: false
verify_verdict: VALID
confidence_score: 80
outcome_confidence: 55
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
size: Very Large
---

## Summary

The three SQL insert sites for `raw_events` persist transcript-derived payloads without redaction. Both `raw_line` and `parsed_json` contain the payload, usually as zlib-compressed BLOBs. Credential or PII matches in message text, reasoning blocks, tool inputs, or tool outputs therefore survive compression and can reach a configured shared remote store.

Add default-on, deterministic redaction before serialization/compression, preserve the event structure needed for replay and usage attribution, and provide an explicit, rerunnable maintenance command for existing local and remote raw rows. The guarantee is removal of the supported rule matches from these two logical payload columns; it is not universal secret detection or a declaration that the whole database has been sanitized.

## Current Behavior

Verified on `main` in the little-loops repository on 2026-10-05:

- `scripts/little_loops/session_store/lifecycle.py` → `_backfill_raw_events()` parses all supported hosts through `iter_events(handle)`, serializes `event.payload`, compresses it with `_pack_payload()`, and supplies the same bytes to **both** payload columns. Its local `execute()` and remote `_REMOTE_RAW_INSERT`/`executemany()` branches share the serialization step. These are normalized, reserialized events, not necessarily verbatim physical transcript lines.
- `lifecycle.py` → `refresh_usage_source()` has a separate Claude insert using `json.dumps(record)` and `_pack_payload()`. Its Codex branch, `_refresh_codex_usage_source()`, delegates insertion to `_backfill_raw_events()` but compares previously stored JSON against the original parser payload during first cursor certification.
- `scripts/little_loops/session_store/usage_refresh.py` → `refresh_raw_events()` also reinserts through `_backfill_raw_events()`. `_event_signature()`, `_stored_signatures()`, and `_preserves_fields()` currently compare original and stored payloads. Redacting inserts without adapting these comparisons would reject unchanged originals or roll back refresh.
- `scripts/little_loops/pii.py` → `redact_pii()` replaces email, phone, SSN, and fixed credential shapes with existing uppercase placeholders such as `[EMAIL]` and `[GITHUB_TOKEN]`. Its `apply_pii_action()` is the SFT consumer. The logs command imports the redactor; the loop evidence command imports the separate credential scanner. None of the raw insert sites uses either API.
- The existing `private_key_pem` credential pattern matches only a BEGIN header, leaving the body and END marker. Regex replacement on serialized JSON also misses decoded secrets represented with Unicode escapes. Both behaviors were reproduced with synthetic inputs during review.
- Local dedup uses `(source_path, line_no)`; remote insertion additionally deduplicates `(session_id, line_no)`. Source cursor `tail_sha256` hashes original file bytes, not stored JSON. Usage qualification depends on host/basis, producer version, session/message/request/turn identities, and numeric counters.
- `recompress_raw_events()` is an existing bounded-batch TEXT/BLOB maintenance pattern, but explicitly refuses remote stores. `LibsqlConnection.commit()`/`rollback()` are no-ops; remote `executemany()` uses an atomic Hrana batch.
- Updating raw rows alone leaves previously materialized message/tool/search/summary copies untouched. Some direct writers also consume original files. Raw retention can make destructive replay incomplete, so a blanket rebuild is not a safe cleanup strategy.

## Motivation

The capture report observed non-empty plaintext Claude `thinking` blocks in stored rows. Those blocks, like visible conversation and tool data, can contain credentials. Preventing new supported secret matches from entering raw storage reduces persistence and remote propagation without disabling history replay. Existing installations also need a bounded cleanup operation that accurately states what it cleaned.

## Expected Behavior

- Redaction is enabled for new raw payload writes without configuration, before either payload column is compressed or queued for remote transmission.
- A JSON-aware traversal processes decoded string content recursively, including nested reasoning/tool data, and returns a fresh payload without mutating parser-owned objects. Ordinary protocol keys, structure, numeric values, booleans, and nulls remain usable.
- Pure text redaction remains deterministic and idempotent. Preserve the established `[TYPE]` placeholder style; add typed names for new families rather than changing the public `redact_pii()` output contract.
- Supported families include existing PII/fixed credential rules, complete or truncated PEM private-key material, case-insensitive bearer credentials, URI userinfo credentials, and explicit credential context. Do not claim arbitrary high-entropy text is necessarily a secret.
- Replay identities, usage totals/qualification, physical source boundaries, and existing dedup keys remain correct. Source proofs continue to use original file bytes.
- Existing rows can be scrubbed explicitly with dry-run and machine-readable reports. Unreadable rows, concurrent conflicts, or interrupted work must not be reported as complete.

## Proposed Solution

### 1. Add a history payload policy without changing unrelated scanner contracts

Add pure helpers in `pii.py` that reuse `PII_PATTERNS` and the fixed credential rule definitions but apply a history-specific policy:

- Decode JSON before traversing string leaves; never regex-replace serialized JSON as the ingest implementation. Decoded Unicode escapes and multiline PEM content must receive the same treatment as ordinary text.
- Replace a whole PEM block, including its body and END marker. For a BEGIN marker without an END marker, redact through the end of that string. Handle real newlines and literal escaped newline separators inside decoded text. Recognize the legacy header-only `[PRIVATE_KEY_PEM]` form when it is followed by recognizable key material/END context, so remaining key bodies can still be scrubbed; a standalone full-redaction placeholder stays unchanged. Apply broad enclosing matches (PEM, bearer, URI credentials, explicit credential fields) before narrower PII/token matches so partial replacement cannot expose a remainder or break subsequent matching.
- Redact the entire bearer credential and URI userinfo, including percent-encoded username/password material, while retaining noncredential URI structure. Define match boundaries with adversarial multiline/quoted fixtures.
- Explicitly enumerate credential field names, such as `api_key`, `access_token`, `authorization`, `password`, `private_key`, and `client_secret`, with documented case/separator normalization. Redact their string values regardless of entropy. Support corresponding clearly delimited assignments/header text in free-form messages; avoid bare `key`/`id` heuristics.
- **Replace the original unconditional high-entropy requirement with context-bound detection.** UUIDs, commit SHAs, content hashes, base64 data, native IDs, and ordinary long strings must not be removed merely for having high entropy. A hex/hash-shaped value in an explicit credential field still gets redacted; do not globally exempt hex secrets.
- Protect only verified protocol identity paths needed by host replay, not every field called `id` inside arbitrary tool data. If a supported secret match would change a required structural identity, fail the affected ingest instead of persisting an original secret or silently corrupting identity. Scan secret-bearing arbitrary mapping keys too; handle replacement collisions by failing safely rather than dropping a member.
- Preserve explicitly typed opaque protocol values such as thinking signatures, `redacted_thinking` data, and image/base64 blocks; do not treat every base64-looking message/tool string as exempt. Document that encrypted/encoded opaque data is outside plaintext detector coverage. Default PII remains part of the requested policy, but phone/SSN-shaped free-form numeric text can be intentionally lossy; protect actual numeric counters/identities and cover representative tool-output near misses.
- Keep the existing `redact_pii()`, `detect_pii()`, `scan_text()`, `CredentialFinding`, and scanner-version contracts intact unless deliberately changing their shared scan semantics. If shared rule semantics change, update `CREDENTIAL_SCANNER_VERSION` and its tests; a separate history policy version does not imply the evidence scanner changed.
- Report rule names and counts only. No matched text, decoded key material, or per-secret fingerprint is needed for maintenance.
- Bound detector work on large tool outputs: avoid nested/backtracking-heavy regexes, cap any credential-context lookaround, and include adversarial multi-MB inputs and a scaling check. Pure text redaction must handle arbitrary strings without throwing; structural/key conflicts can raise a safe sanitizer error.

### 2. Use the same sanitized representation for inserts and comparisons

Sanitize once in `_backfill_raw_events()` before `json.dumps()`/`_pack_payload()`, covering both local and remote branches, and use the same helper in the Claude `refresh_usage_source()` branch. Build relational metadata and producer qualification from the original verified event; sanitization must preserve the payload fields those consumers require. Both new payload columns receive the same sanitized representation.

Canonicalize both stored and parser payloads with the same policy in Codex first-use certification and source refresh signatures/field-preservation checks. Continue to check nonsecret field parity, structural identities, file changes, and field loss; do not bypass `_preserves_fields()` just because redaction occurred. Test mixed legacy/redacted rows and a later policy extension. Tail digests, offsets, inode/device checks, line numbers, and ingest watermarks retain their existing meaning.

ENH-3751 specifies per-line relational identity refusal and a separate usage-qualification rule: explicit source refresh may promote NULL from verified original evidence through replacement/rebuild, but must not remove/change a persisted marker. Replay never promotes qualification. Codex first-use certification compares pre-existing rows canonically and newly inserted rows literally to the sanitized source, so a missed insertion seam cannot be hidden by sanitizing the stored side during verification.

If sanitization fails, never fall back to original content, advance a cursor past the failed record, or publish a success watermark. Roll back the local affected operation; already committed remote chunks may remain, but are sanitized and safe to deduplicate on retry. Diagnostics must not echo input or exception text containing it.

### 3. Provide explicit logical raw-row maintenance

Add `ll-session redact [--dry-run] [--batch N] [--json]`, using the existing global `--db`/configured history target resolution. Positive batch sizes are required. This is explicit maintenance, not an unbounded migrate-on-open or SessionStart pass.

- Resolve the target once through the history backend. Support SQLite and the configured libSQL project store. A remote run covers that store's rows from all ingesting machines; it must not silently operate on a local fallback or treat this machine's watermark as a scope filter.
- Capture `MAX(id)` at run start, then page by `id` in bounded batches through that snapshot. Read **both** columns independently using `_unpack_payload()`: legacy TEXT and compressed BLOB values coexist, and historical columns may differ. Preserve those differences rather than copying one column over the other. Parse/redact/reserialize only as appropriate; unchanged columns need not be recompressed or rewritten.
- Update only payload columns in place. Preserve IDs, source/session attribution, host/basis, timestamps, positions, ordinal, usage contract, compaction/summary links, usage source cursors, and ingest/derive watermarks. Do not delete/reinsert rows, re-ingest original files, or automatically rebuild derived tables.
- Use short SQLite transactions; use bounded atomic `executemany()` batches for libSQL rather than assuming its `commit()`/`rollback()` implement interactive transactions. Guard updates against concurrent payload changes using the values read. Re-read guard conflicts; do not overwrite a source refresh or call unresolved conflicts clean. An ambiguous remote commit is safe to retry because transformation and guarded updates are idempotent.
- Dry-run reads without changing payloads or progress markers. Report policy version, nonsecret target identity, snapshot boundary, scanned/changed/would-change rows, rule counts per payload column, and failures/conflicts. Count changes only after confirmed persistence; duplicate spans in the two columns are intentionally separate counts.
- Corrupt BLOBs, undecodable data, invalid legacy JSON, key collisions, or unsafe identity changes remain unchanged, receive safe row-ID/reason diagnostics, and make the result incomplete with a nonzero exit. Do not mark such rows sanitized. A restarted run may rescan prior rows safely; no schema migration or permanent one-time skip marker is required.
- Every invocation may rescan with the current policy. A success covers only the reported snapshot and supported matches in the raw columns. Concurrent inserts by older writers require another pass after those writers are upgraded. Default-on new writers prevent reintroduction through supported paths.
- Print/document that existing derived/search/summary/live rows, original transcripts, backups, SQLite free pages/WAL, and remote provider history are outside this operation's cleanup guarantee. Do not run `VACUUM` remotely or imply an UPDATE securely erases historical physical copies.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Open decision — guarded remote UPDATE shape.** `HranaClient.execute_many()` returns only a summed `affected_row_count` over its data steps (`session_store/hrana.py:488`), and `LibsqlConnection.executemany()` forwards that sum as `rowcount` (`session_store/libsql.py:228-230`). Per-step results are available only via `HranaClient.batch()` → `BatchResult.step_results[i].affected_row_count` / `step_errors[i]` (`hrana.py:150-158`, `:454-468`). Two shapes satisfy "guarded, atomic, conflict-detecting":

**Option A**: Guarded `executemany` with summed-count check. Issue `UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = ? AND raw_line IS ? AND parsed_json IS ?` through `conn.executemany()` in bounded chunks. If the summed `rowcount` equals the chunk size, every row landed. If it is lower, the chunk is atomic and committed, so re-read the chunk's rows, classify each as already-sanitized or conflicted, and report the conflicted ones without overwriting.

> **Selected:** Option A — reuses the `LibsqlConnection.executemany` rowcount path and backend-neutral connection surface; per-row attribution is deferred to a re-read only on a short count.

**Option B**: Guarded `HranaClient.batch` with per-step results. Build explicit `BatchStep` lists (`begin`, one guarded UPDATE per row, `commit`, conditional `rollback`, following the step-condition helpers `cond_ok`/`cond_not` in `hrana.py:161-166`), call `conn.client.batch(steps)`, and read `step_results[i].affected_row_count` to attribute a guard miss to a specific row id with no re-read. Per-step SQL errors surface in `step_errors[i]` instead of raising.

**Conventions and ground truth for this decision** (evidence, not templates):
- No existing UPDATE compares a data column against a previously read value; every guard in the codebase is a status or null-state predicate (`queue_store.py:570-695`, `session_store/writers.py:1493-1500`). No existing code compares a rowcount to an expected batch size — all uses are `> 0`, `== 0`, `== 1`, truthiness or accumulation.
- Only one remote write path consumes `rowcount` from `executemany` (`lifecycle.py:842`, the `_REMOTE_RAW_INSERT` insert), and remote writes are chunked at `_REMOTE_INSERT_CHUNK = 200` (`lifecycle.py:778`). No chunked remote read or UPDATE exists yet.
- `BatchStep`/`client.batch` is already used for multi-step atomic remote work with per-step error inspection in `session_store/remote_schema.py:100-149` (guard step plus detection through `step_errors`/`step_results`), so Option B has an in-repo usage shape; `execute_many` is the only caller that reads `affected_row_count` from step results, and it sums.
- Ambiguous-commit handling has exactly one in-repo handler: `remote_schema.py:_apply_one` catches `HranaUnavailable` and re-reads an idempotent marker. A redaction pass has no marker row, but the issue's own idempotent-transform and guarded-update properties make a plain re-run the equivalent safe recovery.
- `HranaStub` (`scripts/tests/hrana_stub.py`) can model both shapes: `_batch` runs steps with conditions and records per-step errors, and `delay`/`stall_body` execute the batch server-side while the client times out (a committed-but-unacknowledged write). It has no hook to force a specific per-step `affected_row_count` or inject a per-step SQL error; a conflict test must seed a changed row through `stub.db` between read and update. No test currently asserts on a write that landed behind an `HranaUnavailable`.
- Local SQLite maintenance in this module commits per batch and pages by self-clearing predicate (`lifecycle.py:965-990`); `id > ?` paging exists only in `_derive_usage_incremental_conn`. Neither convention covers the issue's `MAX(id)` snapshot plus keyset design, which is a deliberate departure already noted above.
- CLI convention for maintenance subcommands: `prune`/`recompress` return 0 unconditionally and do not catch `HistoryError`; `refresh` catches `HistoryError`, prints a reason-coded skip to stderr, and exits 1 on any skip (`cli/session.py:746-843`); `migrate` resolves via `resolve_history_target`, branches on `isinstance(target, RemoteTarget)`, and returns 1 on `HistoryError` (`cli/session.py:478-522`). The `redact` incomplete-run exit contract aligns with `refresh`/`migrate`, not `recompress`.
- `main_session()` wraps every command except `migrate` in `cli_event_context` (`writers.py:601`), so `redact` would write a `cli_events` row remotely unless it runs outside that wrapper as `migrate` does; the issue currently says to disclose it.

### Decision Rationale

**Selected:** Option A — guarded `executemany` with a summed-count check and a re-read on mismatch.

**Reasoning:** Option A stays on the backend-neutral `conn.executemany()` surface, the only remote write path that already consumes `rowcount` (`lifecycle.py:842`), so it keeps `_guard` (read-only, schema access, deadline) and `_run` telemetry in force and mirrors the existing chunked-remote shape (`_REMOTE_INSERT_CHUNK`). Option B calls `conn.client.batch()` directly, bypassing `LibsqlConnection._guard`/`_run`, hand-builds begin/commit/rollback steps, and duplicates the local-vs-remote split. Its one advantage, per-row conflict attribution without a re-read, costs little here: a short count is the rare path, and a re-read is already required by the issue's "re-read guard conflicts" rule.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — `executemany` + summed count | 2 | 2 | 2 | 2 | 8/12 |
| B — `batch` + per-step results | 2 | 1 | 2 | 1 | 6/12 |

**Key evidence:** `libsql.py:228-230` (`executemany` → summed `rowcount`); `lifecycle.py:778,842` (chunked remote write consuming `rowcount`); `libsql.py:183-206` (`_guard`/`_run` bypassed by `client.batch`); `remote_schema.py:100-149` (only existing `batch` use, for schema migration under its own client handle); `hrana_stub.py` supports a conflict test by seeding a changed row via `stub.db` between read and update.

## Program Design

New identifiers below are proposed; existing call sites are named explicitly.

### Types

- `HistoryRedactionResult`: dataclass with `payload: dict[str, Any]` and `counts: dict[str, int]`.
- `RawRedactionReport`: dataclass with `policy_version: int`, `snapshot_max_id: int`, `scanned: int`, `changed: int`, `would_change: int`, `counts_by_column: dict[str, dict[str, int]]`, `failed: int`, `conflicts: int`, and `complete: bool`.
- `HISTORY_REDACTION_VERSION: int`: version of the history policy, independent of evidence-scanner versioning.

### Signatures

```python
def redact_history_text(text: str) -> str: ...
def sanitize_history_payload(payload: dict[str, Any]) -> HistoryRedactionResult: ...
def redact_raw_events(
    db: Path | str | HistoryTarget = DEFAULT_DB_PATH,
    *,
    batch_size: int = 2000,
    dry_run: bool = False,
) -> RawRedactionReport: ...
```

### Call Path

`backfill_raw_events()` / `refresh_raw_events()` / `_refresh_codex_usage_source()` → `_backfill_raw_events()` → `sanitize_history_payload()` → `json.dumps()` → `_pack_payload()` → local `execute()` or remote `executemany()`.

`refresh_usage_source()` (Claude) → `sanitize_history_payload()` → serialize/pack → insert.

`main_session()` (`redact`) → `redact_raw_events()` → resolved history backend → keyset read → unpack/parse/sanitize each column → guarded batch update → safe report.

## Integration Map

### Files to Modify

- `scripts/little_loops/pii.py` — pure history policy and JSON traversal; reuse existing detection definitions and placeholders.
- `scripts/little_loops/session_store/lifecycle.py` — both ingest helpers, Codex certification, and raw maintenance.
- `scripts/little_loops/session_store/usage_refresh.py` — canonicalized signatures and preservation checks.
- `scripts/little_loops/session_store/__init__.py` — export the new maintenance API consistently with `recompress_raw_events()`.
- `scripts/little_loops/cli/session.py` — parser, dispatch, reports, and help.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/lifecycle.py:1467` — `json.loads(_unpack_payload(row[6])) != event.payload` followed by `RuntimeError("Codex stored source differs from current rollout")`, in `_refresh_codex_usage_source()`; canonicalize both sides here (the first-cursor certification site) [Agent 1 finding]
- `scripts/little_loops/session_store/usage_refresh.py:203` — `stored == expected and all(_unpack_payload(row[8]) == _unpack_payload(row[7]) ...)` "unchanged" short-circuit compares the two payload columns to each other, in `refresh_raw_events()`; both columns must carry the same sanitized representation or legacy rows with divergent columns never reach `unchanged` [Agent 1 finding]
- `scripts/little_loops/session_store/usage_refresh.py:246` — post-insert `_stored_signatures(replaced) != expected` check in `refresh_raw_events()`; without canonicalized signatures every redacted row reports `parser_changed_during_refresh` and rolls back [Agent 2 finding]
- `scripts/little_loops/session_store/lifecycle.py:960` — `refuse_on_remote(db, "recompress")`, `SELECT id, raw_line, parsed_json` (~968) and `UPDATE raw_events SET raw_line = ?, parsed_json = ?` (~984) in `recompress_raw_events()`; local-maintenance template only (it must keep refusing remote; `redact_raw_events` must not call `refuse_on_remote`) [Agent 1 finding]
- `scripts/little_loops/cli/session.py:754` — `refuse_on_remote(args.db, "refresh_raw_events")` + `resolve_history_db(args.db)` (~755) in `main_session()` `refresh` branch; the new `redact` branch must resolve through `resolve_history_target` (not `resolve_history_db`, which raises `HistoryBackendNotLocal` on a remote target) and wrap the call in `try/except HistoryError` as `refresh` does [Agent 2 finding]
- `scripts/little_loops/cli/session.py` — `main_session()` wraps every command in `cli_event_context(...)`, so each `redact` run (remote included) writes a `cli_events` row outside the raw-only guarantee; disclose in the command output/docs [Agent 2 finding]
- `scripts/little_loops/cli/session.py` — new `redact` touches the same four places as `recompress` in `_build_parser()`: module docstring "Subcommands:" list, epilog `Examples:` block, subparser registration block, and the `main_session()` dispatch branch; add `redact_raw_events` to the `from little_loops.session_store import (...)` block (tests patch `little_loops.cli.session.redact_raw_events`). For the "positive batch sizes" requirement reuse `_positive_int` in `cli/history.py` / `positive_int` in `cli/issues/next_id.py` as the argparse `type=` rather than the plain `type=int` `recompress` uses [Agent 2 finding]
- `scripts/little_loops/pii.py` — module docstring ("for SFT corpus filtering") goes stale once the history policy lives here; keep the new history rule table separate from `CREDENTIAL_RULES` (adding bearer/URI/credential-field families to `CREDENTIAL_RULES` breaks `test_has_one_rule_per_expected_name`, changes `credential_rules_sha()`, and flows into SFT and the evidence bundle) [Agent 2 finding]
- `scripts/little_loops/__init__.py` — `from little_loops.pii import (...)` block (line 64) and `__all__` `# pii` group; decide explicitly whether `redact_history_text`/`sanitize_history_payload` join the package surface (`detect_pii`/`redact_pii`/`apply_pii_action` must stay exported — pinned by `test_extension.py`) [Agent 1 finding]
- Stale comments/docstrings that contradict "payloads are sanitized" — update text only, no function-body edits: `lifecycle.py` `_backfill_raw_events()` docstring ("JSON-equal to the parser's own output", ~828), `usage_refresh.py` module docstring ("``raw_events`` stores normalized payloads"), `session_store/qwen.py` module docstring ("``raw_events`` keeps the verbatim source line", ~28), the `# raw_events payload compression` comment block above `_pack_payload()` in `session_store/writers.py` (~154), and the `raw_line`/`parsed_json` DDL comment in `session_store/schema.py` (comment-only; `_schema_manifest` is PRAGMA-derived) [Agent 2 finding]

### Dependent Files and Similar Patterns

- `session_store/writers.py` → `_pack_payload()`, `_unpack_payload()`, `_iter_events_with_host()` and replay/usage consumers; preserve their contracts.
- `session_store/claude_usage.py` → `claude_transcript_contract()`; preserve producer qualification.
- `session_store/libsql.py` → `LibsqlConnection.executemany()` and `session_store/hrana.py` → `HranaClient.execute_many()` provide bounded atomic remote batches; no new backend required.
- `lifecycle.py` → `recompress_raw_events()` provides local maintenance structure, not a remote implementation to copy verbatim.
- `cli/logs.py`, `cli/loop/evidence.py`, SFT filtering, and package exports depend on existing PII/scanner behavior.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/backfill_worker.py` — `_refresh_usage_source()` calls `refresh_usage_source`, and `main()` calls `backfill_incremental`; the hook-spawned worker is a live ingest path that inherits sanitization with no edit. Both `_run_usage_trigger()` (`print(f"backfill_worker: usage refresh failed: {exc}", ...)`, line 120) and `main()` (`print(f"backfill_worker: {exc}", ...)`, line 231) echo exception text to stderr, so the sanitizer's error type must carry a content-free message [Agent 1 + 2 finding]
- `scripts/little_loops/loops/sft-corpus.yaml` — shell action imports `apply_pii_action` (line 331); consumes the shared `CREDENTIAL_RULES`, so it is affected only if shared scan semantics change (hence the separate history rule table). No edit needed [Agent 1 finding]
- `scripts/little_loops/session_store/backend.py` — `_REMOTE_REFUSALS` / `refuse_on_remote()`; `redact` must stay out of this table (supported remotely by decision). Note `refresh_usage_source`, `refresh_raw_events`, and `backfill_usage_incremental` all call `refuse_on_remote`, so the Claude refresh insert, `refresh_raw_events`, and Codex certification are **SQLite-only today**: the remote-capable ingest path is `backfill_raw_events` / `backfill_incremental` (SessionStart worker, `backfill --since`) [Agent 2 finding]
- `scripts/little_loops/session_store/libsql.py` / `hrana.py` — `HranaClient.execute_many()` runs one SQL with many parameter sets and returns only the **summed** `affected_row_count`; `LibsqlConnection.executemany()` forwards that sum as `rowcount`. A guarded remote `UPDATE ... WHERE id=? AND raw_line=? AND parsed_json=?` batch therefore cannot attribute conflicts per row: either compare the summed count to the batch size and re-read the batch on mismatch, or use `HranaClient.batch` with explicit `BatchStep`s (per-step results) [Agent 2 finding]
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — hashes every function reachable from `lifecycle.rebuild`, including `writers._unpack_payload`, `_iter_events`, `_iter_events_with_host`, and the `writers._backfill_*` writers. Placing the sanitizer in or calling it from those functions requires a `REBUILD_DERIVE_VERSION` bump + fingerprint regeneration; `_backfill_raw_events`, `refresh_*`, and `recompress_raw_events` are outside the closure [Agent 2 + 3 finding]
- Derived-table consequence to disclose: `rebuild` after `redact` re-derives `tool_events` (args hash via `writers._hash_args`), `message_events`, FTS, and summaries from placeholders, so hashes recomputed from placeholder text differ from earlier ones [Agent 2 finding]

### Tests

- `scripts/tests/test_pii.py` — policy fixtures, existing API parity, and Hypothesis properties (already a dev dependency).
- `scripts/tests/test_session_store_lifecycle.py` — local ingest, TEXT/BLOB cleanup, replay, dedup, and failure recovery.
- `scripts/tests/test_remote_ingestion_telemetry.py` / `test_libsql_backend.py` — Hrana stub storage, outbound compressed insert payloads, cleanup, guards, and ambiguous commits.
- `scripts/tests/test_session_store_incremental_usage.py` / `test_enh3549_codex_usage_refresh.py` — Claude/Codex cursor certification, source proofs, producer qualification, and usage parity.
- `scripts/tests/test_session_store_usage_refresh.py` / `test_ll_session_refresh.py` — sanitized field preservation and repeat refresh.
- `scripts/tests/test_ll_session.py` — `redact` CLI, dry-run, reports, target routing, and nonzero incomplete results.

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests that may break**
- `scripts/tests/test_pii.py` — `TestCredentialRules::test_has_one_rule_per_expected_name` asserts `{r.name for r in CREDENTIAL_RULES} == set(_RULE_FIXTURES)`; breaks if new families go into `CREDENTIAL_RULES`. Also `TestCredentialRulesSha` and `TestScanText::test_rejects_near_miss_fixture` (pinned to the header-only `private_key_pem`) break if the shared pattern is widened [Agent 3 finding]
- `scripts/tests/test_feat3182_evidence_bundle.py` — `TestCredentialScan` asserts `credential_scan.version/rules_sha/hit_count/hits`; breaks if `CREDENTIAL_RULES` or `CREDENTIAL_SCANNER_VERSION` change without matching updates [Agent 3 finding]
- `scripts/tests/test_remote_operation_matrix.py` — `_REJECTED` / `TestRejectedOperations` (`("recompress", ...)`): `redact` must stay absent; add a positive remote case in `TestSupportedOperations` [Agent 2 + 3 finding]
- `scripts/tests/test_remote_callers_bug3652.py` — `TestResolveHistoryDbCallerGate::test_allowlist_has_no_stale_entries` requires `main_session` to still call `resolve_history_db` (satisfied by the `refresh` branch); `_CALLER_ALLOWLIST` reason string for `("cli/session.py", "main_session")` says it "already refuses via refuse_on_remote" — reword if the `redact` branch changes the justification [Agent 2 + 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — `TestDeriveFingerprint::test_digest_matches_snapshot` and `test_resolved_function_set_matches_snapshot` trip if any `rebuild`-reachable function (e.g. `writers._unpack_payload`) is edited, including by the comment/docstring updates in Files to Modify; run it after those edits [Agent 2 + 3 finding]
- `scripts/tests/test_session_store_schema.py` — `TestPackageReexportSurface::test_all_and_required_private_names_resolve` fails if `redact_raw_events` is in `__all__` but not imported in `session_store/__init__.py` [Agent 2 + 3 finding]
- `scripts/tests/test_session_store_usage_refresh.py` — `test_failed_reingestion_rolls_back_existing_rows` monkeypatches `lifecycle._backfill_raw_events` with a `*_args` function (keep the module attribute name and positional call shape); `test_refresh_refuses_parser_output_that_drops_existing_fields` (`existing_payload_not_preserved`) must keep refusing real field loss [Agent 3 finding]
- `scripts/tests/test_enh_omp_normalizer.py` — `test_raw_line_and_parsed_json_are_normalized_form` asserts `parsed == raw` after unpacking both columns; holds only if both columns get the same sanitized payload [Agent 3 finding]
- `scripts/tests/test_enh3532_codex_rollout_usage.py` — `test_direct_and_stored_replay_agree_and_copy_is_idempotent` compares stored replay payloads to the file's; green only while the fixture has no redactable text [Agent 3 finding]
- `scripts/tests/fixtures/codex/rollout-interactive.jsonl` — two lines carry an email address that becomes `[EMAIL]` in stored rows; read by `test_session_store_lifecycle.py::TestBackfillCodexHandlesD4`, `test_session_discovery.py::TestBackfillRawEventsCodexHandleD3`, and parser-only `test_enh_3433_codex_normalizer.py`. None asserts the email text today [Agent 2 + 3 finding]
- `scripts/tests/test_extension.py` — smoke imports of `detect_pii`, `redact_pii`, `apply_pii_action`, `CREDENTIAL_RULES` from `little_loops`; keep them exported [Agent 1 + 3 finding]
- `scripts/tests/test_remote_ingestion_telemetry.py` — `TestRemoteIngestion::test_inserts_are_batched_not_one_round_trip_per_event` asserts `len(remote.requests) - before < 20` for 450 events; sanitization must stay in-process (no per-event round trip) [Agent 3 finding]

**New tests to write (with closest template)**
- `scripts/tests/test_pii.py` — history-policy fixture table parallel to `_RULE_FIXTURES` (positive + near-miss per family) and a `TestNoLeak`-style check; first Hypothesis tests in this file (shape: `test_config_properties.py::TestBRConfigProperties::test_to_dict_idempotent`, `@st.composite` in `test_issue_parser_fuzz.py`; use `fuzz_max_examples` from `tests/helpers.py`). Multi-MB/scaling tests must stay well under the suite's 120s thread timeout (or carry `@pytest.mark.timeout(N)`/`slow`); no tree-wide wall-clock scaling helper exists [Agent 3 finding]
- `scripts/tests/test_session_store_lifecycle.py` — `redact_raw_events` local cases modeled on `TestRawEventsPayloadCompression::test_recompress_converts_legacy_rows_and_preserves_rebuild` / `test_recompress_is_idempotent`; ingest sanitization modeled on `test_backfill_stores_compressed_blobs` [Agent 3 finding]
- `scripts/tests/test_remote_ingestion_telemetry.py` — outbound compressed payload inspection via `TestRemoteIngestion` + `_transcript(...)`; `HranaStub` stores raw request bodies as text, so decode JSON → base64 blob → `_unpack_payload`. Remote refresh/certification cannot be tested remotely (they `refuse_on_remote`); remote outbound coverage goes through `backfill_raw_events` only [Agent 2 + 3 finding]
- `scripts/tests/test_libsql_backend.py` — guarded-update batch atomicity (template: `TestConnection::test_executemany_is_atomic`); ambiguous commit via `HranaStub` fault hooks (`fail_next`, `delays`, `stall_body`) [Agent 3 finding]
- `scripts/tests/test_remote_schema.py` (~lines 244-269) — template for a remote `ll-session redact` CLI test (`monkeypatch.setattr(sys, "argv", [...])` then `main_session()` against the stub) [Agent 3 finding]
- `scripts/tests/test_ll_session.py` — `TestRecompressSubcommand` is the template (parse test, defaults, `patch("little_loops.cli.session.<name>")` invoke test); add a `--batch 0` rejection test (no existing equivalent) [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py` — add a `DOC_STRINGS_PRESENT` row for `ll-session redact` in `docs/reference/CLI.md` alongside `("docs/reference/CLI.md", "ll-session migrate", "FEAT-3535")` [Agent 3 finding]
- Ingest → rebuild → usage totals/identity parity with vs. without redaction (no existing test; closest `test_enh3532_codex_rollout_usage.py::test_direct_and_stored_replay_agree_and_copy_is_idempotent`) [Agent 3 finding]
- Other Claude/Codex refresh callers to regression-run: `test_enh3731_usage_qualification.py`, `test_enh3656_stored_cache_rate.py`, `test_enh3549_codex_stored_ctx_stats.py`, `test_bug3736_usage_replay_holds.py` (hand-seeded legacy rows — realistic scrub inputs) [Agent 3 finding]
- Secret fixtures are assembled from fragments (gitleaks pre-commit); use `/nonexistent/...` rather than `/home/<user>/` paths (private-refs hook) [Agent 2 + 3 finding]

### Documentation and Configuration

- `docs/reference/CLI.md` — command usage and scope/physical-erasure limits.
- `docs/reference/API.md` — new helpers/maintenance report and changed raw payload semantics.
- `docs/reference/CONFIGURATION.md` — default-on capture policy and remote maintenance scope.
- Configuration/schema: no opt-out, new dependency, or schema migration required for the proposed design.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-session`: add a `redact` subcommand-table row, a `**\`redact\` flags:**` table + prose paragraph (beside `**\`recompress\` flags:**`), and example lines after `ll-session recompress --batch 5000`; the paragraph "**Under a remote history backend** these subcommands are refused…" needs an explicit `redact` exception; the `refresh` row ("Replace verified stored raw rows from available original session files") must say re-ingestion re-applies redaction (not a restore of original text); the `recompress` "byte-lossless" wording sits next to a lossy sibling [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `#### Remote history backend`, in the "Not supported remotely." bullet (`rebuild`, `backfill`, `prune`, `compact`, `recompress`, … "a remote store has no retention path"): add `redact` as an explicitly supported remote maintenance operation; the `Ingestion` bullet is the place for "default-on payload redaction on ingest". Keep the strings pinned by `test_wiring_reference_docs.py` (`Remote history backend`, `history.backend.provider`, `history.backend.project_id`) [Agent 1 + 2 finding]
- `docs/reference/API.md` — `## little_loops.pii` section (intro repeats "for SFT corpus filtering") and its module-table row (lists only `detect_pii, redact_pii, apply_pii_action`); the `### raw_events / rebuild / compact` section sentence "re-serialized `raw_line` (JSON-equal to the parser's own output …)" is no longer true for matched spans; neither `recompress_raw_events` nor `refresh_raw_events` is in the `from little_loops.session_store import (...)` listing, so there is no precedent entry to extend [Agent 1 + 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` (user-facing; `test_docs_audience_gate.py` applies — dotted module names only, no `scripts/…` paths) — the `raw_events` row in "What Gets Recorded" needs a redaction note; the "Getting Started: Backfill" blockquote on `rebuild` should state that `redact` does not scrub derived/FTS/summary rows and `rebuild` re-derives from placeholders; "Retention & Pruning" says pruning "removes the verbatim source records" (conflicts with the new semantics); add a Table of Contents entry if a "Redacting stored payloads" section is added [Agent 2 finding]
- `docs/ARCHITECTURE.md` — the `**Ingest to history.db**` bullet describing `_backfill_raw_events` consuming `iter_events` ("sanitized before serialization") [Agent 1 + 2 finding]
- `docs/reference/loops.md` — documents `pii_action` / `[PRIVATE_KEY_PEM]` via `little_loops.pii.CREDENTIAL_RULES`; edit only if the shared `private_key_pem` pattern semantics change [Agent 2 finding]
- No `README.md`/`scripts/README.md`, `skills/`, `commands/`, `hooks/`, or `loops/` listing of `ll-session` subcommands exists, so the ll-adapt mirror gates and README copy step are not triggered unless those files are touched; `.claude/CLAUDE.md` needs no entry; CHANGELOG is release-prep only [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Conventions in force — maintenance shape**: lifecycle maintenance functions return plain `dict[str, Any]` reports and page by a self-clearing `WHERE`+`LIMIT` predicate with per-batch commit (`lifecycle.py:recompress_raw_events`, `prune`, `compact`); reports built as dataclasses exist only on the refresh path (`usage_refresh.py` `SourceRefresh`/`RefreshResult`, converted to dicts for `--json`). The issue's `RawRedactionReport` dataclass and `MAX(id)` keyset paging are therefore a deliberate departure — `id > ?` paging exists only in the usage-derive checkpoint (`_derive_usage_incremental_conn`).
- **Conventions in force — CLI surface**: `--dry-run` (`store_true`) and `--batch N` (`type=int`, default 2000) appear on separate subcommands (`prune`, `recompress`), each with `add_json_arg`; `_build_parser()` in `cli/session.py` registers subparsers inline (no helper), and a new subcommand touches four places: parser, `main_session` dispatch branch, module docstring list, epilog examples. `--json` branches first via `print_json`; skips are reported as machine-readable `reason` codes plus path only, never content, and exit non-zero (`refresh`).
- **Conventions in force — exports**: maintenance APIs are re-exported in both the import block and `__all__` of `session_store/__init__.py` (`prune`, `compact`, `recompress_raw_events`); `refresh_raw_events` is the exception (imported directly from `usage_refresh`).
- **Contested convention — remote maintenance**: every other maintenance operation calls `refuse_on_remote(db, "<op>")` (`session_store/backend.py:107`, reasons in `_REMOTE_REFUSALS`, `backend.py:97`), is asserted by `test_remote_operation_matrix.py::_REJECTED` (expects `HistoryUnsupported.operation` and zero stub requests), and is listed as refused in `docs/reference/CLI.md` and `docs/reference/CONFIGURATION.md`. This issue's explicit decision to support remote (see Review Notes) breaks that rule: `redact` must stay out of `_REMOTE_REFUSALS`/`_REJECTED`, and the CLI/CONFIGURATION docs' "maintenance is refused remotely" wording needs a stated exception. Local-vs-remote branching inside ingest uses `remote = not hasattr(conn, "create_function")` with `_REMOTE_RAW_INSERT` + `executemany` in `_REMOTE_INSERT_CHUNK = 200` chunks (`lifecycle.py:778`).
- **Conventions in force — pii.py**: patterns are module-level compiled regexes; placeholders derive as `f"[{name.upper()}]"` from `PII_PATTERNS` then `CREDENTIAL_RULES` (frozen `CredentialRule(name, pattern, rationale)`); `credential_rules_sha()` hashes name/pattern/flags; `CREDENTIAL_SCANNER_VERSION` bumps only on scan-semantic change; `CredentialFinding` carries a short fingerprint and no excerpt. No JSON-recursive redactor exists today (`apply_pii_action` handles top-level strings only; other recursive walkers such as `_preserves_fields` are not redaction-specific).
- **Conventions in force — tests**: secret fixtures are assembled from fragments (e.g. `"AKIA" + "I" * 16`) so the gitleaks pre-commit hook does not flag the test file; `test_pii.py` pairs each rule with a positive and a near-miss in `_RULE_FIXTURES` and has a `TestNoLeak` class asserting matched text never appears in finding reprs. Hypothesis is configured (`conftest.py` `ll-dev`/`ll-full` profiles, `LL_FUZZ=full`; `@settings(max_examples=fuzz_max_examples(N), deadline=None)` with `fuzz_max_examples` from `tests/helpers.py:38`) but is not yet used in `test_pii.py`. CLI tests follow `test_ll_session.py::TestRecompressSubcommand` (argv parse, defaults, patched-function `main_session()` call with `json.loads(capsys...)`); remote tests use a per-module `HranaStub` `remote` fixture setting `LL_HISTORY_URL`/`LL_HISTORY_AUTH_TOKEN` and asserting on `stub.db.execute(...)` and `len(stub.requests)`. `HranaClient._scrub` already masks the auth token in remote errors.
- **Docs convention**: a subcommand is documented in `docs/reference/CLI.md` in three places (table row, a `**\`<cmd>\` flags:**` table plus prose paragraph, example lines); `docs/reference/API.md` does not currently list `recompress_raw_events`.

## Implementation Steps

1. Add pure history-specific text/JSON sanitizers, explicit rule precedence, credential contexts, and safe structural/key handling with fixtures and property tests.
2. Wire shared sanitization before both insert branches and the Claude refresh insert; adapt Codex/source refresh comparisons without weakening nonsecret parity checks.
3. Implement bounded local/libSQL raw scrubbing and safe reports, including dry-run, guarded updates, incomplete-row handling, and rerun semantics.
4. Add CLI/export wiring and focused ingest/refresh/replay/maintenance regression tests.
5. Document policy coverage, legacy cleanup steps, and excluded stores/copies; run the authoritative local test suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Keep the history rule table separate from `CREDENTIAL_RULES` in `scripts/little_loops/pii.py`; update the module docstring; leave `credential_rules_sha()` / `CREDENTIAL_SCANNER_VERSION` untouched unless shared semantics deliberately change (then update `test_pii.py::TestCredentialRulesSha` and `test_feat3182_evidence_bundle.py::TestCredentialScan`)
- Update `scripts/little_loops/session_store/lifecycle.py:_refresh_codex_usage_source()` (~1467) and `scripts/little_loops/session_store/usage_refresh.py:refresh_raw_events()` (~203 column-parity short-circuit, ~246 post-insert signature check) to compare canonicalized payloads; keep `_preserves_fields()` active
- Keep `lifecycle._backfill_raw_events` as a module attribute with its positional call shape (monkeypatched by `test_failed_reingestion_rolls_back_existing_rows`)
- Add the `redact` branch in `cli/session.py:main_session()` via `resolve_history_target` + `try/except HistoryError`; touch the module docstring list, epilog examples, subparser block, and import block; use a positive-int `type=` for `--batch`; do not add `redact` to `session_store/backend.py:_REMOTE_REFUSALS` or `test_remote_operation_matrix.py:_REJECTED`
- Export `redact_raw_events` in both the import block and `__all__` of `scripts/little_loops/session_store/__init__.py` (gate: `TestPackageReexportSurface`); decide on `little_loops/__init__.py` pii re-exports
- Guarded remote UPDATE goes through `conn.executemany()` and compares the summed row count to the batch size, re-reading the batch on a short count (Option A, selected under Proposed Solution → Decision Rationale); `HranaClient.batch` per-step results are not used
- Ensure sanitizer exceptions carry content-free messages — `cli/backfill_worker.py` prints `{exc}` to stderr in `_run_usage_trigger()` and `main()`
- Keep sanitizer code out of `rebuild`-reachable functions (`writers._unpack_payload`, `_iter_events*`, `_backfill_*`) or bump `REBUILD_DERIVE_VERSION` and regenerate `rebuild_fingerprint.json`; run `test_enh3678_rebuild_derive_gate.py` after the comment/docstring edits in `writers.py`
- Update stale "verbatim"/"JSON-equal" comments in `lifecycle.py`, `usage_refresh.py`, `qwen.py`, `writers.py`, `schema.py` (text only)
- Update tests: see Tests → "Existing tests that may break" and "New tests to write" above (notably `test_has_one_rule_per_expected_name`, `test_remote_operation_matrix.py`, `test_wiring_reference_docs.py` `DOC_STRINGS_PRESENT`, the Codex fixture email → `[EMAIL]`)
- Update docs: `docs/reference/CLI.md` (row, flags, examples, remote-refusal exception, `refresh` wording), `docs/reference/CONFIGURATION.md` (remote bullet + Ingestion), `docs/reference/API.md` (pii section, raw_events section, module row), `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md`

## Acceptance Criteria

- [ ] Each of the three SQL insert sites is exercised with every supported rule family. After decompression, neither payload column contains the planted synthetic secret. Remote tests also inspect outbound insert payloads, and nested reasoning, tool input/output, arrays, and decoded JSON escapes are covered.
- [ ] PEM bodies and END markers are removed, including incomplete blocks within one string. Bearer, URI userinfo, explicit credential fields/assignments, and existing PII/provider shapes have positive and near-miss fixtures. Existing uppercase placeholder/public scanner contracts remain compatible.
- [ ] Hypothesis tests prove text and JSON traversal determinism/idempotence, valid serialization of generated JSON, no input mutation, safe overlapping matches/key collisions, and preservation of nonsecret structure. Assert original secret fixtures are absent and placeholders do not match any detector; replace the untestable claim that arbitrary output can never resemble any secret. Versioned fixtures include legacy header-only PEM remnants, opaque signed/image fields, representative PII near misses, and adversarial multi-MB text with bounded runtime/scaling.
- [ ] Unlabelled UUIDs, commit/content hashes, base64 data, model/tool names, and native session/message/call/request/turn IDs remain intact; explicitly labelled credentials of the same shapes are redacted. Required structural secret matches fail safely. Replay yields unchanged usage totals, qualification and identity; dedup remains stable.
- [ ] Both Codex first-cursor certification and `ll-session refresh` work with sanitized payloads, mixed legacy rows, and a policy extension. Repeated unchanged refresh is a no-op, actual nonsecret field loss still refuses refresh, and original file tail/inode/offset proofs still detect truncation/overwrite.
- [ ] Scrubbing handles legacy TEXT and compressed BLOBs, divergent columns, missing source files, and compacted rows without changing metadata, links, cursors, or watermarks. A second pass makes zero payload changes. Dry-run makes no writes. Counts are per rule/column and represent confirmed changes or explicitly labelled would-change results.
- [ ] Local/remote batch interruption, corrupt payloads, concurrent guarded-update conflicts, and ambiguous remote commits are tested. Rerun completes safely; incomplete runs exit nonzero and never publish a clean marker or plaintext diagnostic. New ingest sanitization failures never persist originals or advance success boundaries past failures.
- [ ] The command resolves the requested/configured target, handles the shared remote project store, reports its bounded snapshot, and makes no SQLite-only maintenance call remotely. Help/docs/output explicitly state the raw-only logical guarantee and that older writers or other stored copies require separate remediation.
- [ ] `python -m pytest scripts/tests/` exits 0, with targeted regression checks for each modified ingest/refresh/maintenance path.

## Impact

- **Priority: P2** — closes a confirmed missing protection on local and shared raw capture; retain the existing priority while avoiding an unsupported universal-cleanup claim.
- **Effort: Medium** — reuse existing regex, compression, target routing, and batch support; JSON traversal and two refresh comparison contracts require deliberate integration.
- **Risk: Medium** — false positives or changed identities could corrupt replay/usage attribution. Context-bound detection, shared canonicalization, compatibility tests, and bounded maintenance address the main risks.
- **Breaking change: Yes, for raw content consumers** — supported secret/PII text becomes typed placeholders by default. Relational schema, existing PII API placeholders, source identities, and numeric usage semantics remain compatible.

## Scope Boundaries

- Covers both `raw_events` payload columns on all existing insert/reinsert paths and an explicit cleanup pass over their stored logical values.
- Does not sanitize every persistence table or direct/live writer, regenerate old summaries/FTS/message caches, or claim the whole history store is clean. Broader stored-copy remediation requires separate work; do not silently add a destructive rebuild here.
- Does not implement universal entropy-based detection, deobfuscation of arbitrary encodings, or secret reconstruction across separate events/string values. Detection coverage is the enumerated, tested policy.
- Does not alter the choice to retain reasoning blocks, original host transcript files, structural source-path metadata, export-specific policies, backups, SQLite physical remnants/WAL, or provider retention history.

## Review Notes

- 2026-10-05: Corrected verbatim-line claims; confirmed both compressed payload copies, full-PEM and escaped-JSON gaps, source-refresh dependencies, and remote transaction differences. Added concrete design, bounded cleanup/reporting, compatibility coverage, and explicit cleanup limits. Review changes only; implementation remains pending.
- `/ll:advise` with `claude-code` / `opus`, signal `user_requested`: confidence 0.74. Accepted its JSON-aware/canonicalized comparisons, context-bound detection, PEM completeness, compare-and-set maintenance, performance coverage, and no-rebuild remediation advice. It also recommended expanding new-write protection to every live/derived sink and making PII opt-in. Retain the explicitly bounded raw-payload issue and original default PII intent: wider sink/legacy-derived remediation is separate work, and the raw command must disclose that exposure. Do not adopt a remote refusal because the current backend already supports parameterized updates, affected-row counts, and atomic batches. Do not add checkpoint/VACUUM as a claimed secure-erasure guarantee. Its dissent favored remote/export protection over lossy local capture; Impact and Scope Boundaries document that tradeoff.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06 (re-scored 2026-10-05 after `/ll:decide-issue`)_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 55/100 → LOW

### Concerns
- `ll-issues format-check` flags `ll-session redact (no such subcommand)` as `stale_cli_flag`. It is the forward-looking new subcommand, not a stale claim, so it is advisory only, but it caps Criterion 4 at 10.
- Remote `redact` breaks the repo-wide `refuse_on_remote` maintenance convention (Review Notes record this as a deliberate decision). `test_remote_operation_matrix.py`, `docs/reference/CLI.md`, and `docs/reference/CONFIGURATION.md` all need an explicit exception.
- The guarded remote `UPDATE` decision is now recorded (Option A: `executemany` + summed-count check + re-read on short count). The Wiring Phase already reflects it, but `ll-issues format-check` reports `unapplied_decision` (below), so directive sections were not rewritten to match.
- Sanitizer placement matters: any edit to `rebuild`-reachable functions (`writers._unpack_payload`, `_iter_events*`, `_backfill_*`) trips `test_enh3678_rebuild_derive_gate.py` and needs a `REBUILD_DERIVE_VERSION` bump.
- Open judgment calls: whether `redact_history_text`/`sanitize_history_payload` join the `little_loops/__init__.py` exports, and exact bearer/URI-userinfo match boundaries (to be settled by adversarial fixtures).

### Gaps to Address
- `unapplied_decision` (caps Criterion C at 10): the `> **Selected:** Option A` record is present, but the gate still finds rejected-option identifiers unmarked in directive sections (`HranaClient.batch` in Implementation Steps, plus `MAX(id)`, `main_session()`, `redact`, `refresh`, `resolve_history_target`, `recompress`, `cli_events` across Proposed Solution/Program Design/Files to Modify). Most of these are generic identifiers shared with the selected option, so this is largely detector noise; run `/ll:reconcile-issue ENH-3743` to mark Option B's `HranaClient.batch` mentions as rejected and clear the gate.

### Outcome Risk Factors
- Deep per-site complexity: shared canonicalization must stay consistent across the insert branches, Codex certification, and the `refresh_raw_events` signature, field-preservation, and column-parity checks. A mismatch rolls back every refresh.
- Broad blast radius: every raw payload consumer (replay, usage qualification, rebuild, dedup keys) sees changed payload content. A false positive can corrupt identity or usage attribution.
- Broad enumeration across 6-15 change sites (source, tests, five docs files), with 15+ existing tests that may break.

## Session Log
- `/ll:issue-size-review` - 2026-10-06T00:26:53 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
- `/ll:confidence-check` - 2026-10-06T00:25:17 - `8205c006-a395-4b84-bffa-4b266393ef1b.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:24:06 - `48d916c8-bf44-4d12-9c7d-d72a3d5900a9.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T00:22:20 - `a467ce0f-32de-4026-90cb-c574efe1fbc0.jsonl`
- `/ll:confidence-check` - 2026-10-06T00:21:13 - `7f137275-99a6-4d87-8f9e-1ce553a24130.jsonl`
- `/ll:decide-issue` - 2026-10-06T00:19:24 - `cd8feb66-b58f-4e22-afb5-afe735ab0ed8.jsonl`
- `/ll:refine-issue` - 2026-10-06T00:18:19 - `cd8feb66-b58f-4e22-afb5-afe735ab0ed8.jsonl`
- `/ll:confidence-check` - 2026-10-06T00:11:33 - `cba8250f-da78-4dc9-9001-f8bed2e5e7b0.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:09:56 - `23214518-2834-45d1-9a9e-5041b278fc6e.jsonl`
- `/ll:wire-issue` - 2026-10-06T00:08:03 - `b249786e-08d6-4f68-83f0-5c270f528ab9.jsonl`
- `/ll:refine-issue` - 2026-10-05T23:54:08 - `bb41cd42-6536-4a59-9334-2c0ba11bd9e2.jsonl`
- `/ll:ready-issue` - 2026-10-05T20:38:27 - `5e941467-cbb1-4a41-8ad7-cda0d6a9d0e0.jsonl`

---

## Status

**Done** (decomposed; child implementation pending) | Created: 2026-10-05 | Priority: P2

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-10-05
- **Reason**: Issue too large for single session (size score 11/11)

### Decomposed Into
- ENH-3750: Add history payload redaction policy and JSON sanitizer to the pii module (§1; done, policy API landed in `b953e103c`)
- ENH-3751: Sanitize raw_events payloads on all ingest paths and canonicalize refresh comparisons (§2; open and unblocked)
- ENH-3752: Add ll-session redact maintenance command for stored raw_events rows (§3; blocked by ENH-3751)
