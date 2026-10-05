---
id: ENH-3743
title: Redact history raw payloads before persistence and provide a resumable scrub
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
labels: [security, privacy, history]
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

### Dependent Files and Similar Patterns

- `session_store/writers.py` → `_pack_payload()`, `_unpack_payload()`, `_iter_events_with_host()` and replay/usage consumers; preserve their contracts.
- `session_store/claude_usage.py` → `claude_transcript_contract()`; preserve producer qualification.
- `session_store/libsql.py` → `LibsqlConnection.executemany()` and `session_store/hrana.py` → `HranaClient.execute_many()` provide bounded atomic remote batches; no new backend required.
- `lifecycle.py` → `recompress_raw_events()` provides local maintenance structure, not a remote implementation to copy verbatim.
- `cli/logs.py`, `cli/loop/evidence.py`, SFT filtering, and package exports depend on existing PII/scanner behavior.

### Tests

- `scripts/tests/test_pii.py` — policy fixtures, existing API parity, and Hypothesis properties (already a dev dependency).
- `scripts/tests/test_session_store_lifecycle.py` — local ingest, TEXT/BLOB cleanup, replay, dedup, and failure recovery.
- `scripts/tests/test_remote_ingestion_telemetry.py` / `test_libsql_backend.py` — Hrana stub storage, outbound compressed insert payloads, cleanup, guards, and ambiguous commits.
- `scripts/tests/test_session_store_incremental_usage.py` / `test_enh3549_codex_usage_refresh.py` — Claude/Codex cursor certification, source proofs, producer qualification, and usage parity.
- `scripts/tests/test_session_store_usage_refresh.py` / `test_ll_session_refresh.py` — sanitized field preservation and repeat refresh.
- `scripts/tests/test_ll_session.py` — `redact` CLI, dry-run, reports, target routing, and nonzero incomplete results.

### Documentation and Configuration

- `docs/reference/CLI.md` — command usage and scope/physical-erasure limits.
- `docs/reference/API.md` — new helpers/maintenance report and changed raw payload semantics.
- `docs/reference/CONFIGURATION.md` — default-on capture policy and remote maintenance scope.
- Configuration/schema: no opt-out, new dependency, or schema migration required for the proposed design.

## Implementation Steps

1. Add pure history-specific text/JSON sanitizers, explicit rule precedence, credential contexts, and safe structural/key handling with fixtures and property tests.
2. Wire shared sanitization before both insert branches and the Claude refresh insert; adapt Codex/source refresh comparisons without weakening nonsecret parity checks.
3. Implement bounded local/libSQL raw scrubbing and safe reports, including dry-run, guarded updates, incomplete-row handling, and rerun semantics.
4. Add CLI/export wiring and focused ingest/refresh/replay/maintenance regression tests.
5. Document policy coverage, legacy cleanup steps, and excluded stores/copies; run the authoritative local test suite.

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

## Session Log
- `/ll:ready-issue` - 2026-10-05T20:38:27 - `5e941467-cbb1-4a41-8ad7-cda0d6a9d0e0.jsonl`

---

## Status

**Open** | Created: 2026-10-05 | Priority: P2
