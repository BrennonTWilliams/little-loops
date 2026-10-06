---
id: ENH-3752
title: Add ll-session redact maintenance command for stored raw_events rows
type: ENH
priority: P2
status: open
discovered_date: '2026-10-05'
parent: ENH-3743
blocked_by:
- ENH-3751
labels:
- security
- privacy
- history
decision_needed: false
unproven_mechanism: true
spike_needed: true
size: Very Large
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
- Preserve each unchanged column byte-for-byte and with its original SQL type, even when its sibling changes; do not normalize JSON whitespace/order, recompress, or merge columns opportunistically. If neither column changes, issue no UPDATE. Preserve each column's TEXT/BLOB storage type when changing it. If either column is corrupt/undecodable/invalid/unsafe, leave the whole row unchanged, record a fixed reason, and continue the bounded scan with `complete=false`.
- Update payload columns in place only. IDs, source/session attribution, host/basis, type/timestamp/positions, ordinal, usage contract, compaction/summary links, source cursors, and ingest/derive watermarks remain unchanged. No delete/reinsert, original-file ingestion, automatic rebuild, pruning or VACUUM.
- Dry-run performs zero logical database/telemetry/progress/schema writes; main DB and WAL bytes remain unchanged. SQLite lock/shared-memory (`-shm`) bookkeeping needed to read a live WAL is allowed and is not counted as a logical write. It uses strict read-only target access and refuses missing/stale stores with migration guidance. `updates_applied=0`; `would_change` and rule counts describe candidates that passed validation. Apply must also avoid silently creating a wrong target; migration is an explicit separate operation.
- Interrupted/backend-failed/conflicted runs remain incomplete with nonzero exit; previously committed batches remain safe. Every new invocation rescans with the current policy, so restarting needs no durable checkpoint/one-time sanitized marker.

## Motivation

New default-on writes do not remove existing plaintext. A logical scrub needs truthful counts and bounded conflict-safe writes across both supported backends; compression or a blanket rebuild would not provide this contract.

## Proposed Solution

### Bounded scan and guarded persistence

Put the maintenance core in a new sibling module rather than growing `lifecycle.py` or editing replay helpers. Preflight the exact resolved target/schema, capture its snapshot, then decode/sanitize rows outside long-held write locks. Enforce row-count/stored-byte bounds in SQL before fetching values and decompressed-byte bounds before JSON decoding. Depth/node limits apply after JSON decoding; do not claim pre-decoding structural bounds. A row-count LIMIT alone is insufficient: Hrana reads the full response and SQLite can fail while decoding malformed TEXT before a per-row handler runs.

Decided client bounds (named constants with rationale comments, not new user settings): stored payload cap 1 MiB per column; decoded payload cap 4 MiB per column; at most 8 rows in a value-returning page, additionally limited by positive `batch_size`; at most 16 MiB of fetched original payload bytes per page; at most 8 MiB of retained encoded replacement values; at most 8 MiB per serialized outbound write request, including protocol/SQL overhead. Candidate guards reference the original page values without copying them; flush/reconcile the page's candidates before fetching the next page. Original-page and replacement budgets are separate and may coexist. Process columns sequentially within one row and release decoded source/sanitized objects before decoding the next column; retain only encoded replacements and rule counts for pending writes.

For a conforming successful response, the capped BLOB projections give a 32 MiB read-response envelope bound: 8 × 2 × 1 MiB × base64 expansion plus bounded metadata/envelope headroom. Pin that bound against captured stub responses. Hrana has no response-size limiter: this is a bound derived from selected values, not a transport guarantee against malformed/unexpected server responses. Python JSON objects, UTF-8 strings and protocol/serialization buffers can exceed their input byte sizes. The named input/page/candidate/request caps do not promise a total-process RSS ceiling or an engine-memory ceiling.

Validate actual outbound JSON wire bytes before scheduling/sending writes; UTF-8 stored size is not wire size. Hrana's default `ensure_ascii=True` expands BLOB values by base64 and TEXT by JSON escaping, conservatively up to six ASCII bytes per input UTF-8 byte plus quotes/envelope overhead. A within-cap row may still exceed the request budget and must fail with `resource_limit`; no oversized request is sent. Pin non-ASCII, DEL/control-escape, quote/backslash and base64 cases against captured requests. `--batch` is a row ceiling, not permission to bypass internal byte/page bounds. Validate prospective rewritten bytes against the same stored/decoded caps before scheduling a write, so successful output remains maintainable on a later run; output growth past a cap is a row `resource_limit` failure. Oversized rows are failures, never silently truncated.

Preview performs the same context/decode/sanitize/output-size/single-row request-budget validation as apply, without sending writes. A row that cannot fit even one supported write request is a failure in both modes, not a successful dry-run candidate.

Use one keyset SELECT per value page with `typeof(column)`, `length(CAST(column AS BLOB))`, and a guarded value projection: `CASE WHEN length(CAST(column AS BLOB)) <= CAP THEN CAST(column AS BLOB) END`. Do this for both payload columns in the same statement; the value and length check share its snapshot. Return TEXT as BLOB bytes too, preserving the original SQL type tag for later writes. This avoids UTF-8 decode failure in SQLite's page fetch and bounds Hrana TEXT escaping by using base64 BLOB values. Bound host/event-type projections to 256 bytes each and validate/decode them without exposing arbitrary context text. A NULL value due to an over-cap column is `resource_limit`, not JSON null. Reject unsupported SQL storage classes as row problems. Advance keyset progress for rejected rows. These bounds cover client/wire allocations, not the DB engine's transient page/row reads; no engine-memory guarantee is made.

For compressed BLOBs, use checked `decompressobj` output bounded to decoded-cap + 1 (the extra byte detects overflow). Require EOF and no unconsumed/unused data; truncated, trailing-garbage or concatenated streams refuse rather than silently normalize. TEXT and decompressed bytes require strict UTF-8, JSON object roots, unique object keys and finite JSON numbers. Catch decode/JSON/recursion errors with finite content-free reasons. The existing sanitizer depth/node limits remain active; do not claim they bound allocations before JSON decoding. No separate nesting scanner or shared codec rewrite is needed.

Use short SQLite transactions and the backend-neutral `conn.executemany` remote surface (selected Option A). Remote write subchunks are at most `min(batch_size, 200)` rows and have an explicit serialized-request byte budget including old guard values, new TEXT/BLOB encodings, escaping/base64 expansion and protocol overhead; use a conservative measured upper bound and pin it against captured wire requests. A single row exceeding the supported budget is a reported failure; do not bypass the bound. Local read/work batches also have a byte bound, not only a row limit. No change to the shared decompression/rebuild functions is required: enforce checked decompression in the maintenance path and retain existing codec semantics.

Guard each update against the fetched byte representation, original SQL storage type AND the context used to sanitize it. Bind guard payloads as BLOB bytes; bind changed replacement values as the original TEXT/BLOB type. Bind SQL NULL for an unchanged column and let `COALESCE` retain its existing server value exactly, avoiding a redundant payload transmission/re-encoding. Both columns are `NOT NULL`; pin that schema prerequisite in the proof/tests. NULL is an instruction to retain, never a replacement payload:

```sql
UPDATE raw_events
SET raw_line = COALESCE(?, raw_line), parsed_json = COALESCE(?, parsed_json)
WHERE id = ? AND typeof(raw_line) = ? AND CAST(raw_line AS BLOB) IS ?
  AND typeof(parsed_json) = ? AND CAST(parsed_json AS BLOB) IS ?
  AND host IS ? AND event_type IS ?
```

Each primary-key statement can affect at most one row; candidates contain unique IDs. `rowcount == candidate_count` proves the whole batch applied, and fully acknowledged batches are never retried. Reject impossible counts (negative/greater than candidates) as a backend invariant failure. A short count is a known committed batch with guard misses, not a rollback; a transport failure may have an unknown commit outcome. Do not call `conn.client.batch` directly or assume `commit`/`rollback` undoes remote chunks.

On a short acknowledgement or ambiguous remote outcome, re-read every candidate with the same bounded projections (including SQL storage types and context) and classify:

| Current state | Action |
|---|---|
| Exact desired bytes, desired SQL types and unchanged context | `reconciled`; no own-write/per-rule attribution inferred |
| Exact original bytes, SQL types and context | One bounded guarded per-row retry via `execute`; acknowledgement of 1 has exact attribution; another miss is re-read once |
| Different bytes/type/context | Conflict; leave it untouched and report incomplete |
| Missing row | Vanished/conflict; do not claim it was sanitized |
| Read/retry outcome unavailable | Unconfirmed; stop safely with incomplete report |

Never retry against newly observed arbitrary payloads or overwrite a source refresh. Do not retry forever. A second zero acknowledgement is incomplete even if a later read again shows the original: record a conflict and stop retrying that row. Concurrent ABA changes can explain this, so a later read is not proof that the guard implementation is broken. Impossible acknowledgement counts stop the run as backend invariant failures. Under SQLite apply the same guard discipline; update and acknowledgement counts become durable only after local commit, and a rolled-back batch contributes zero committed changes.

### Report and count semantics

Refine the parent's proposed changed-row counter into explicit operation units before this new API ships: `updates_applied` counts acknowledged committed UPDATE applications, and `unattributed_updates_applied` counts the anonymous applications acknowledged by short batches. A successful acknowledged batch adds its summed affected count. When every candidate is acknowledged, its per-column/rule counts are attributable and included. For an acknowledged short batch, add its affected sum to both operation counters, but do not infer the rule breakdown from a later read. Per-row retry acknowledgements add one application plus exact rule counts. A committed-but-unacknowledged desired row is `reconciled`, not an invented acknowledged write.

`updates_applied` and apply `counts_by_column` are confirmed lower bounds on update/removal applications when `counts_complete=false`; the latter excludes unattributable batch writes and reconciled observations. `counts_complete=false` whenever a short batch with positive affected count or an ambiguous commit prevents exact attribution. Empty/no-op columns and already-redacted placeholders contribute zero. Duplicate spans across columns are intentionally counted separately. Dry-run counts are planned removals in valid candidate rows; it makes no confirmed-persistence claim and retains `updates_applied=0`.

Do not describe applications as distinct rows changed. Under concurrent ABA restores, the same ID may be updated in the short batch and again by its one retry, so `updates_applied` can exceed `would_change`. `reconciled` counts candidate IDs observed in the exact desired state during reconciliation; it may overlap acknowledged writes and is not an additive partition. Full-acknowledgement batches are never retried, each candidate ID is scanned once, and each ID has at most one retry. Consequently `updates_applied - unattributed_updates_applied` is a conservative lower bound on distinct IDs with attributed successful redactions. Per-rule counts describe those attributed applications; they do not identify unique original secrets or account for anonymous work. Pin these units and invariants in tests/help/docs rather than claiming `updates_applied + reconciled == would_change`.

Required ABA example: A/B candidates, short acknowledgement 1 updated A, another writer restores A and changes B to desired, retry A acknowledges 1. Report `updates_applied=2`, `unattributed_updates_applied=1`, `reconciled=1`, with exact rule counts from A's retry only; only one distinct ID was changed by this invocation. Also cover the normal overlapping case where A remains desired and B's retry succeeds. Assert `0 <= unattributed_updates_applied <= updates_applied`, the attributed difference and `reconciled` are each at most `would_change`, and applications are at most candidates plus attempted retries.

`complete` describes scan coverage/current-policy results as observed row by row: reached the reported snapshot with no failed, conflicted/vanished, or unconfirmed rows. It may be true after successful reconciliation even when exact write/rule attribution is unavailable; `counts_complete` keeps those claims separate. `MAX(id)` bounds concurrent inserts, not updates or an isolated whole-table snapshot. A writer can change a previously observed row; do not claim simultaneous database-wide cleanliness. Upgrade writers first and rerun after relevant concurrent activity.

Keep `last_scanned_id`, snapshot boundary and bounded reason-only row problems in reports. A per-row validation failure must not stall keyset progress or be hidden by an end-of-scan success. Bound the retained diagnostic list with an omitted-problem count so corrupt large stores do not defeat bounded memory.

### CLI, context, and rollout

Run the redact dispatch outside `cli_event_context` for both apply and dry-run, using parsed command selection so global `--db` before `redact` works. Do not refactor other command telemetry in this issue. Use strict read-only opens for preview; never use `immutable=1` to bypass WAL visibility or sidecar bookkeeping; apply requires the existing/current schema and a writable backend connection to that same resolved target. Keep `redact` out of `_REMOTE_REFUSALS` and do not use `resolve_history_db` or `refuse_on_remote` on this path. Positive `--batch` is validated in the CLI and public API (reject bool/zero/negative values).

Pass known stored host/event type even when `host_basis` is null; do not promote attribution. Use a new public boolean context-support query in `little_loops.pii`, derived directly from the existing protocol-rule registry. Proposed API: `is_replay_safe_history_context(*, host: str | None, event_type: str | None) -> bool`. It returns true exactly when the registry supplies replay-protecting rules: string context for Claude-shaped/Kimi hosts, and registered native/normalized Codex types. Unknown Codex types, missing/non-string context and unregistered hosts are false, even if the host alone is registered. This issue owns the additive query; it changes neither sanitizer generic behavior, policy semantics/version nor the closed sanitizer-error vocabulary. Do not duplicate a Codex type list or call private registry functions from maintenance.

Unsupported context leaves the whole row unchanged with `unsupported_context`, advances `scanned`, increments `failed`, and makes `complete=false`. Never guess the ambient host or apply generic mode while claiming replay safety. Known stored context is required even for an otherwise no-op row: an unsupported row is not certified scrubbed. Report this refusal visibly without echoing the unknown values.

JSON mode emits exactly one report/error object on stdout after successful argument parsing, including incomplete runs; human guidance belongs on stderr. Fatal pre-snapshot failures emit `{"complete": false, "error": "<reason>"}` rather than inventing snapshot/counter values. Argparse usage errors retain exit 2 and stderr usage with no stdout report. Failures expose row ID, payload-column name and finite reason codes only, not source/session IDs, arbitrary keys, raw backend exceptions or content-bearing tracebacks. Return 1 for incomplete/backend failures and 130 for interruption; interruption must not emit a successful complete report. Reports identify local path or remote provider/project without auth material.

On `KeyboardInterrupt`, roll back an open local transaction before reporting; its batch adds zero confirmed changes. An in-flight remote write with no acknowledgement is unconfirmed, never presumed rolled back or counted in `updates_applied`, and sets `counts_complete=false`. After the snapshot exists, return accrued confirmed counts in one `complete=false` report with `interrupted`; before the snapshot, emit the safe error object. Do not attempt network reconciliation after the user interrupts. Cleanup must cover `BaseException` without swallowing unrelated exceptions or printing their content.

Define and pin one closed `RAW_REDACTION_REASONS` vocabulary: existing `HISTORY_ERROR_REASONS` plus `unsupported_context`, `unsupported_storage`, `invalid_encoding`, `invalid_compression`, `invalid_json`, `conflict`, `vanished`, `unconfirmed`, `backend_failure`, `backend_invariant`, `schema_mismatch`, `target_unavailable`, and `interrupted`. Map decoder/backend/open/version failures to these fixed codes with suppressed exception chains; never print arbitrary `HistoryError` messages. Batch argument errors are `ValueError` in the public API and argparse usage errors in the CLI. A bounded diagnostic list and omitted count retain no arbitrary content.

Print/document the supported-match, raw-column-only logical guarantee and exclusions: derived/FTS/summary/live rows, original transcripts, backups, WAL/free pages, and provider history. No automatic `rebuild`: retention/replay holds can make it destructive, and it does not clean every excluded copy. A deliberate later rebuild derives only the tables it covers from available redacted rows. Shipping order is ENH-3750 -> ENH-3751 -> ENH-3752; the core can be developed separately, but the CLI is not safe to roll out before the compatibility wiring.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Bounds convention in force**: existing limits are module-level constants with a rationale comment, each bounding one dimension (rows, bytes, depth, nodes, passes), and exceeding one is a refusal/failure — not truncation (`pii.py` `_MAX_*`; `lifecycle._REMOTE_INSERT_CHUNK = 200`; `verify_evidence._BLOB_MEMO_MAX_BYTES`, which counts retained bytes rather than entries; `policy_builder_routes._MAX_RUN_REQUEST_BYTES`, checked before the body is read). The one truncating site is `hooks/pre_done.py` diff capture and is the contrary case. No byte cap exists anywhere on session_store read or write paths, and no Hrana request-size cap exists, so the byte budgets this issue requires are net-new constants.
- **Guarded-UPDATE precedents are state-guards, not payload-guards**: the existing compare-and-set writes compare a status or NULL marker and decide on `cursor.rowcount` (`queue_store.py` guarded status updates return a bool; `writers._admit_retry` raises on a lost race; the `prompt_opt_events` write acts on `if cursor.rowcount:`). None compares a payload column, binds a BLOB, or goes through remote `executemany`. The only remote summed-`rowcount` consumer is `lifecycle._flush` over `_REMOTE_RAW_INSERT`, an `INSERT OR IGNORE … WHERE NOT EXISTS` batch, so the exact-value `IS ?` guard over typed BLOBs remains unproven.
- **Reporting conventions (disagreements flagged)**:
  - JSON output: `cli/output.py:print_json` is the single stdout writer (`json.dumps(indent=2)`, no `allow_nan=False`); human diagnostics go to stderr. `refresh` (`cli/session.py`) is the model for stderr-notes-plus-one-JSON-object.
  - Incomplete exit code is contested: `refresh` returns 1 on partial failure; `ll-verify-evidence` `_incomplete` returns 2 and prints `status: incomplete` in-band. This issue's contract (exit 1) follows `refresh`, the only `ll-session` precedent.
  - Report-to-JSON conversion is contested: `cli/session.py` uses `dataclasses.asdict` for search/events/recent/grep/describe results but hand-builds the dict for `refresh`; `session_store/` report dataclasses define no `to_dict`. `asdict` handles nested dataclasses and tuples, which `problems: tuple[RawRedactionProblem, ...]` needs.
  - Reason vocabularies are validated three different ways (membership assertion on an observed value — `test_pii.py::TestHistoryErrorSafety`; closed-set test — `test_enh3731_usage_qualification.py::test_reason_vocabulary_is_closed`; equality with a source enum — `test_issue_lifecycle.py`), while `RebuildState`/`SourceRefresh` leave reasons unvalidated. The issue's finite-code requirement is only enforceable if a test pins the set.
  - Content-free errors: the rule is a fixed code plus a suppressed cause at the raise site, with a test asserting a canary is absent from traceback, `str`, `repr` and `args` (`test_pii.py::_assert_clean`). Backend errors are not content-free — `HranaClient._post` embeds the exception type name and scrubbed server text, and `execute_many` classifies server messages without scrubbing — so row problems must not forward backend exception text.
  - Interruption: there is no `KeyboardInterrupt` handling in `cli/session.py` or `session_store/`; rollback idiom elsewhere is `except BaseException: rollback; raise` (`lifecycle.py` prune, `schema.py` migrations). `sprint/run.py` returns 130 for interrupt; that is the nearest CLI precedent for a non-success interrupt exit.
- **Zero-write assertion conventions**: local tests compare db-file bytes/sha256 or a directory tree before and after (`test_session_store_backend.py::TestConnectReadonlyStrict`; `test_sqlite_uri.py::_tree`, which ignores `-wal`/`-shm` as a documented exception); remote tests compare `len(stub.requests)` or row counts in `stub.db`. Nothing uses SQLite `total_changes`.
- **`no_parallel` convention**: applied by decorator at class or test scope; `conftest.py` skips marked tests on xdist workers and `test_no_parallel_serial_gate.py` runs them serially by marker expression, with no hand-maintained list. Real-I/O timing cases assert against a named tolerance smaller than the tested budget, and exact budget accounting uses a `FakeClock` patched into `deadline_mod.now` (both in `test_enh3720_session_store_deadline.py`). `test_worktree_utils.py` notes the opposite choice (nested `pytest -n 0` subprocess) because a marked test goes dormant under `-n logical`.

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
    updates_applied: int
    would_change: int
    counts_by_column: dict[str, dict[str, int]]
    counts_complete: bool
    unattributed_updates_applied: int
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

`scanned` counts each projected keyset row once, including over-cap/unsupported rows; `would_change` counts valid candidate rows rather than columns, in both modes; confirmed counters advance after commit/acknowledgement. Failure before a snapshot is obtained raises a safe `HistoryError` for the CLI's single structured error object. Expected per-row failures return the incomplete report, not a traceback. A backend failure after scanning begins returns the accrued incomplete report with a fixed reason; it must not discard confirmed prior-batch counts. `last_scanned_id` is the last actually observed row ID, not necessarily the snapshot maximum when concurrent deletions leave gaps. Completion means no eligible rows remain through the snapshot bound, with no recorded failures/conflicts/unconfirmed work.

### Call Path

`main_session` -> parsed redact dispatch outside telemetry -> `redact_raw_events` -> one resolved target -> strict preflight/read or writable connection -> snapshot/keyset read -> independently unpack/decode/sanitize both columns with row context -> guarded bounded writes/reconciliation -> report. Export the public function/report types through `session_store/__init__.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Sanitizer result carries no `changed` signal**: `HistoryRedactionResult` (`pii.py`) has only `payload` and `counts`. Every call returns a freshly built, equal-but-not-identical payload (pinned by `test_pii.py::test_returns_fresh_payload_without_mutating_or_aliasing_input`), so `counts == {}` is the only valid "unchanged" test. Comparing `json.dumps(result.payload)` to stored text is invalid — stored TEXT may differ in whitespace/key order, which would break the byte-for-byte no-op rule.
- **Context-support rule inputs (for `unsupported_context`)**: `pii._protocol_rules` does not read `HISTORY_REGISTERED_HOSTS` (its only consumer is a `test_pii.py` parity assertion against `_PARSERS`); it switches on `HISTORY_CLAUDE_SHAPED_HOSTS` and the literals `"kimi-code"` / `"codex"`, and returns no exemptions when `host` or `event_type` is not a `str`. Claude-shaped hosts and `kimi-code` ignore `event_type`; only `codex` dispatches on it, and an unknown codex `event_type` gets no exemptions despite a registered host. A host-membership check alone therefore does not cover that case — the decided context-support query rejects unknown Codex types; no maintenance-local type list is introduced.
- **Sanitizer limits and failure surface**: `_MAX_DEPTH=200`, `_MAX_NODES=10_000_000`, `_MAX_PASSES=8`; failures are exactly the four `HISTORY_ERROR_REASONS` (`invalid_payload`, `key_collision`, `unsafe_identity`, `resource_limit`), raised with a suppressed cause so the exception carries only the code. Only `type(payload) is dict` is accepted as a root (`int`, `dict` subclasses → `invalid_payload`). `RecursionError` maps to `resource_limit`. These codes are already a content-free vocabulary the row-problem `reason` field can reuse for sanitizer-originated failures.
- **Decompression is unchecked everywhere**: `writers._unpack_payload` holds the only `zlib.decompress` call under `scripts/`; a repo-wide search finds no `decompressobj`/`max_length` precedent. A byte-bounded decompression path is net-new, and `zlib.error` / `UnicodeDecodeError` from the existing codec are unwrapped, so any new reason code for them is the maintenance path's own vocabulary.

## Integration Map

### Files to Add/Modify

- `scripts/little_loops/pii.py` — additive registry-derived context-support query, no sanitizer semantics/version change.
- `scripts/tests/test_pii.py` — registered/unknown pair query contract, including unknown Codex types.
- `scripts/little_loops/session_store/raw_redaction.py` (new file) — maintenance/report core; avoids sharing `lifecycle.py` edits with ENH-3751.
- `scripts/little_loops/session_store/__init__.py` — imports and `__all__` exports.
- `scripts/little_loops/cli/session.py` — parser, dispatch before telemetry, imports, module subcommand list/epilog, safe single-document reporting.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/backend.py` — host the non-creating writable local open (`sqlite_file_uri(path, mode="rw")`, `little_loops/sqlite_uri.py`) as a backend-chokepoint helper next to `connect_readonly`; `raw_redaction.py` cannot call `sqlite3.connect(` itself because `test_history_store_chokepoint_gate.py::test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist` AST-scans `little_loops/` and only allowlists `session_store/backend.py`, `schema.py`, `queries.py`, `sessions.py` and a few others. Do **not** add a `redact` key to `_REMOTE_REFUSALS` in the same file. [Agent 2 finding]
- `scripts/little_loops/cli/session.py` — import `redact_raw_events` at module level (not lazily in the dispatch branch) so `patch("little_loops.cli.session.redact_raw_events")` works in dispatch-layer tests, as `recompress_raw_events` does; the redact branch must live inside `main_session` or a helper that never calls `resolve_history_db` (see `_CALLER_ALLOWLIST` in `test_remote_callers_bug3652.py`). [Agent 2/3 finding]
- `scripts/little_loops/session_store/__init__.py` — add a `from little_loops.session_store.raw_redaction import (...)` block modeled on the `lifecycle` import block, and add each name to `__all__`; optionally list `raw_redaction.py` in the module docstring "Package layout" block (already incomplete, not required). [Agent 2 finding]

### Dependent Files and Similar Patterns

`session_store/backend.py` / `db.py` / `targets.py` supply target/connection/error seams; `libsql.py` / `hrana.py` supply guarded atomic batches. Use their existing APIs, not a new backend/per-step wrapper. `lifecycle.recompress_raw_events` is a local codec-maintenance example only; `writers._pack_payload` / `_unpack_payload` define codec semantics but must not gain new replay-time policy. `_positive_int` in `cli/history.py` is an argparse validation model.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py` — existing `main_session` dispatch (`if args.command == "recompress":` → `recompress_raw_events(args.db, batch_size=args.batch)`) and `_build_parser` `recompress_parser = subparsers.add_parser("recompress"` block are the sibling templates; `_main_migrate` is a telemetry-bypass model only (ignores `args.db`) in `main_session`. [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `recompress_raw_events` (`refuse_on_remote(db, "recompress")` template to deliberately **not** copy) and `_refresh_codex_usage_source` (`if cursor is None:` first-cursor branch compares `json.loads(_unpack_payload(row[6])) != event.payload`) is the certification path a redacted row must not break. [Agent 1/3 finding]
- `scripts/little_loops/session_store/usage_refresh.py` — `refresh_raw_events` unchanged-source check compares `_unpack_payload(row[8]) == _unpack_payload(row[7])` (`parsed_json` vs `raw_line`); redaction that makes the two columns differ flips this status. [Agent 3 finding]
- `scripts/little_loops/cli/doctor.py` and `scripts/little_loops/session_store/remote_schema.py` (`_MIGRATE_HINT`) — existing `ll-session migrate` guidance strings the stale-store refusal can reuse; tests pin the text (`test_remote_doctor.py`, `test_remote_schema.py`). [Agent 2 finding]
- `scripts/little_loops/pii.py` — `sanitize_history_payload`, `HISTORY_REDACTION_VERSION` (feeds `policy_version`), `HISTORY_ERROR_REASONS`, `HISTORY_REGISTERED_HOSTS`; no non-test importer exists yet. [Agent 1 finding]
- `hooks/scripts/record-hook-event.sh` / `scripts/little_loops/init/writers.py` (`Bash(ll-session:*)` permission entry) — prefix-matched, already cover `redact`; no edit needed. [Agent 1/2 finding]

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

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests that may break / gates that scan the new module**
- `scripts/tests/test_history_store_chokepoint_gate.py` — `test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist` fails if `raw_redaction.py` calls `sqlite3.connect(`; `test_allowlist_entries_still_exist_and_still_have_raw_connects` requires any new allowlist entry to hold a live raw connect. Route the writable open through `backend.py` instead. [Agent 2/3 finding]
- `scripts/tests/test_usage_selection_chokepoint_gate.py` (`_violations`) and `scripts/tests/test_session_reader_no_host_roots_gate.py` (`_all_sites`) — `rglob` over `little_loops/`; trip only if `raw_redaction.py` embeds `FROM usage_events` token/cost SQL or literal transcript-root paths (`.claude/projects`). [Agent 2 finding]
- `scripts/tests/test_remote_callers_bug3652.py::TestResolveHistoryDbCallerGate` — `test_no_unlisted_caller_outside_session_store` fails on a new `resolve_history_db` call in any other `cli/session.py` function (e.g. a `_main_redact` helper); `test_allowlist_has_no_stale_entries` stays satisfied only while the `refresh` branch in `main_session` still calls it. [Agent 2/3 finding]
- `scripts/tests/test_session_store_schema.py::TestPackageReexportSurface::test_all_and_required_private_names_resolve` — fails if a new `__all__` name is not importable on the package. [Agent 3 finding]
- `scripts/tests/test_remote_operation_matrix.py::_REJECTED` — pins `("recompress", ...)`; must not gain a `redact` row. [Agent 3 finding]

**New tests, anchored to existing models**
- `scripts/tests/test_ll_session.py` — add `TestRedactSubcommand` modeled on `TestRecompressSubcommand` (`test_recompress_parsed_from_argv`, `test_recompress_default_batch`, `test_recompress_invokes_session_store_recompress`): parse `--dry-run`/`--batch`/`--json`, global `--db` before `redact`, `--batch` 0/negative/non-int rejection, `main_session` calls `redact_raw_events` without entering `cli_event_context`, exit 1 on an incomplete report. [Agent 2/3 finding]
- `scripts/tests/test_remote_schema.py::TestMigrateCommand` — model for a redact no-telemetry test (`test_migrate_does_not_write_telemetry_into_the_store` asserts `select count(*) from cli_events` is 0 on `stub.db`); also assert no `sentinel-token-DO-NOT-LEAK` in stdout/stderr and `HistoryUnsupported` with `ll-session migrate` guidance on a behind store. [Agent 2/3 finding]
- `scripts/tests/test_remote_operation_matrix.py::TestSupportedOperations` — add a positive remote `redact` round-trip case modeled on `test_event_write_round_trips`. [Agent 3 finding]
- `scripts/tests/test_session_store_backend.py::TestConnectReadonlyStrict` (`test_missing_store_raises_history_unavailable`, `test_existing_store_is_byte_identical_before_and_after`, `test_write_attempt_is_rejected`) and `scripts/tests/test_libsql_backend.py::TestReadOnly::test_reads_work_and_writes_are_refused_client_side` — templates for the dry-run zero-write assertions (local sha256 of the db file, remote unchanged `len(stub.requests)`). [Agent 3 finding]
- `scripts/tests/test_sqlite_uri.py::TestHelperContract` (`test_rw_commits_only_to_intended_file`, `test_missing_intended_file_fails_without_creating`) — only existing coverage of the non-creating `mode="rw"` open; extend with the apply-path caller. [Agent 3 finding]
- `scripts/tests/test_libsql_backend.py::test_executemany_is_atomic` — closest `executemany` pattern for guarded-UPDATE short/impossible `rowcount` and BLOB `IS ?` cases (no guarded-UPDATE precedent exists). [Agent 3 finding]
- `scripts/tests/test_enh3720_session_store_deadline.py::test_stalled_body` — only `stall_body` user; a committed-but-unacknowledged redact test must also be `@pytest.mark.no_parallel` (covered by `test_no_parallel_serial_gate.py`). [Agent 3 finding]
- `scripts/tests/test_enh3549_codex_usage_refresh.py` and `scripts/tests/test_ll_session_refresh.py::test_refresh_from_original_and_rebuild_on_request` (helpers `_prepared`, `_run`) — assemble the rollout regression from these; neither currently seeds redacted payloads. [Agent 3 finding]
- `scripts/tests/test_pii.py::TestHistoryProtocolContext` — already proves the unregistered-host no-exemption behavior the `unsupported_context` row relies on. [Agent 3 finding]
- `scripts/tests/conftest.py::_guard_real_history_db` / `_isolate_history_db` — new tests must route through `LL_HISTORY_DB`/`tmp_path` or an explicit non-default-shaped `--db`. [Agent 2/3 finding]
- `scripts/tests/test_wiring_reference_docs.py::DOC_STRINGS_PRESENT` — add rows such as `("docs/reference/CLI.md", "ll-session redact", "ENH-3752")` and an `API.md` `redact_raw_events` row once docs land (additions only; existing rows unaffected). [Agent 2/3 finding]

### Documentation

`docs/reference/CLI.md` (subcommand/flag table, examples, counters, exit contract and remote support), `docs/reference/CONFIGURATION.md` (supported remote maintenance), `docs/guides/HISTORY_SESSION_GUIDE.md` (section/ToC, preview/apply, exclusions and writer-upgrade order), and `docs/reference/API.md` (API/report and lower-bound semantics). No private source paths/secret fixtures in end-user docs.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — in `### ll-session`: add a `redact` row to the Subcommands table, a `**`redact` flags:**` block (`--dry-run`, `--batch`, `--json`; model the exit-1-on-incomplete text on the `refresh` flags-and-safety block), an Examples-block entry, and a sentence in the "**Under a remote history backend** these subcommands are refused…" paragraph stating `redact` is **not** in that list. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — in "#### Remote history backend": the "**Not supported remotely.**" bullet ("With `prune`, `compact` and `recompress` unavailable a remote store has no retention path") must stay accurate; add that `redact` is a supported remote maintenance operation, and note the "**Setup.**" bullet's behind-store "run `ll-session migrate`" refusal applies to redact apply. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — no maintenance/privacy entry in the ToC (lines 7-21); the new section needs a ToC link. Nearest existing section is "## Retention & Pruning"; cross-reference from the `raw_events` table row ("source of truth"). The guide currently mentions neither `recompress` nor `refresh`. [Agent 2 finding]
- `docs/reference/API.md` — in "## little_loops.session_store" (fenced import block is curated, not exhaustive) and its `ll-session` subcommand bullets; cross-link `policy_version` to "### History payload redaction" (`HISTORY_REDACTION_VERSION`). [Agent 2 finding]
- Docs audience gate: `scripts/tests/test_docs_audience_gate.py` bans `scripts/tests`, "this repo", "contributor(s)", `pip install -e`, `pytest scripts`, "your little-loops project" in `docs/guides/`, `docs/reference/`, `README.md`. README.md/scripts/README.md/commands/skills contain no `ll-session` enumeration, so no mirror/`ll-adapt` gate is tripped by docs-only edits. [Agent 2/3 finding]
- `CHANGELOG.md` — `ll-session recompress` / `rebuild` (ENH-2581) are the precedents for the entry; per project convention, promote under a concrete version at release prep, not `[Unreleased]`. [Agent 1 finding]

### Configuration

Use existing target configuration. No schema migration, durable progress marker, new dependency, automatic maintenance hook or user-configurable policy bypass.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` / `.ll/ll-config.json` — no new keys; redact only reads `history.backend.provider`, `history.backend.url_env`, `history.backend.project_id`, `history.db_path` and env `LL_HISTORY_DB` / `LL_HISTORY_URL` / `LL_HISTORY_AUTH_TOKEN`. `analytics.capture.cli_commands` / `analytics.enabled` gate only `cli_event_context`, so they are moot on the unwrapped redact path. [Agent 2 finding]
- `scripts/pyproject.toml` — single `ll-session = "little_loops.cli:main_session"` entry point; a new subcommand adds no entry point or plugin-manifest edit (`hooks/hooks.json`, `.claude-plugin/*`, `commands/`, `agents/` have no `ll-session` subcommand listing). [Agent 1 finding]
- No loop YAML, hook, skill or command invokes `ll-session` maintenance subcommands or consumes their exit codes, so redact's nonzero-on-incomplete exit has no dependent gate. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Dispatch constraint**: `main_session` (`cli/session.py`) only skips telemetry via a raw-argv test (`sys.argv[1:2] == ["migrate"]` → `_main_migrate`), which does not fire for `ll-session --db X redact`. `redact` must therefore be selected from parsed args (`_build_parser().parse_args()`), and any no-telemetry path must read `args.db` — `_main_migrate` ignores `args.db` and resolves `DEFAULT_DB_PATH`, so it is a model for the telemetry bypass only, not for target selection.
- **Telemetry target**: `cli_event_context` (`session_store/writers.py`) is handed `DEFAULT_DB_PATH`, never `args.db`, and opens before argparse runs; this is why an explicit `--db` can have its CLI telemetry land in the default/remote store.
- **Strict preview seams**: `connect_readonly` (`session_store/backend.py`) never creates or migrates, but its local backend does **not** check the schema version (a missing file raises `HistoryUnavailable`; a stale file opens fine). Stale/missing detection must come from `schema._current_version(conn)` (0 when `meta` is absent), as `_main_migrate` and `doctor.py` probe it. Remote read-only (`LibsqlConnection(read_only=True)`) refuses non-read SQL client-side and tolerates behind/ahead stores.
- **Strict apply seams**: local writable access through `schema.connect` / `open_history` ensures and migrates the schema — it would create or upgrade a target, contradicting the "no silently-created wrong target" requirement. `sqlite_file_uri(path, mode="rw")` (non-creating) exists but is currently used only in `test_sqlite_uri.py`. Remote `LibsqlBackend.connect` does not migrate; a write-intent access check raises `HistoryUnsupported(operation="write")` for behind/ahead/unstamped stores, with `ll-session migrate` guidance already in the message.
- **Target typing**: `resolve_history_target` returns `LocalTarget`/`RemoteTarget`; an explicit non-default path is always local, and a default-shaped path with `LL_HISTORY_DB` unset and a backend config returns remote. `_resolve_once` honors an already-absolute `Path` verbatim (BUG-3181). `HistoryTarget` is importable from `session_store/backend.py` / `targets.py` but is **not** re-exported by `session_store/__init__.py`, which matters for the `db: Path | str | HistoryTarget` signature.
- **Sanitizer is present, ingest wiring is not**: ENH-3750's API landed in `little_loops/pii.py` (`sanitize_history_payload(payload: dict, *, host, event_type) -> HistoryRedactionResult`, `HISTORY_REDACTION_VERSION`, `HISTORY_ERROR_REASONS`, `HistorySanitizationError.reason`); a tree-wide search finds no non-test caller, so ENH-3751's ingest wiring is absent. It takes a decoded `dict` (non-dict roots raise `invalid_payload`), its `counts` are per-span keyed by rule ID (not per column), and it does **not** raise on an unregistered host/event type — it silently applies no protocol exemptions. The `unsupported_context` refusal in this issue therefore cannot come from the sanitizer; the caller needs the registry-derived support query specified above; a host-membership check alone is insufficient for Codex.
- **Codec facts**: `writers._pack_payload` is a bare zlib stream (no marker/header); `_unpack_payload(bytes)` is an unchecked `zlib.decompress(...).decode("utf-8")` with no size/depth bound and unwrapped `zlib.error`/`UnicodeDecodeError`. `raw_line`/`parsed_json` are declared `TEXT NOT NULL` but hold TEXT or BLOB by SQLite dynamic typing; for per-line hosts `raw_line` is re-serialized JSON, so both columns must tolerate non-object/non-JSON content as a row problem rather than an exception. `host`, `event_type` are `NOT NULL` in the schema, so the "missing/unknown host" case is an unregistered value, not NULL.
- **Remote batch facts**: `LibsqlConnection.executemany` → `HranaClient.execute_many` runs begin / conditional steps / commit in one request and returns only the summed `affected_row_count` (per-step counts are not exposed); a failing step raises and rolls back the whole batch. `commit`/`rollback` are no-ops. `hrana.py` has no request-size limit or byte budget anywhere (`json.dumps` of the full body; BLOBs base64-encoded; integers as strings); `lifecycle._REMOTE_INSERT_CHUNK = 200` is the only chunk constant. Deadline checks run in `_guard` and `_post`.
- **Test-fixture facts**: `HranaStub.stall_body` sleeps after execution (the write is already committed before the reply), and `stub.db` is directly writable for interleaving; no existing test combines `stall_body` with a guarded UPDATE, and the one stall test is `@pytest.mark.no_parallel`. `test_remote_callers_bug3652.py::TestResolveHistoryDbCallerGate` allowlists `("cli/session.py", "main_session")` on the premise that it refuses via `refuse_on_remote` before resolving — adding a `resolve_history_db` call on the redact path would invalidate that reasoning. `_REMOTE_REFUSALS` lives in `session_store/backend.py` (not `cli/session.py`) and has no `redact` key; `test_remote_operation_matrix.py::_REJECTED` is where `recompress` is pinned as rejected.
- **No precedent for the core mechanism**: no existing guarded `UPDATE raw_events` exists (`recompress_raw_events` updates by `id` alone), and there is no keyset scan over `raw_events` (`lifecycle._derive_usage_incremental_conn` reads `MAX(id)` then `id > checkpoint` with no upper bound or limit, persisting the checkpoint in `meta`). No site binds a BLOB parameter into an `IS ?` guard over the Hrana path; the new guard additionally checks the original SQL type.
  ⚠ Unproven mechanism — typed BLOB `IS ?` guards over Hrana unexercised

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **`raw_events` shape**: 14 columns after all migrations — `id`, `ts`, `session_id` (nullable), `host`, `source_path`, `line_no`, `event_type`, `raw_line`, `parsed_json`, `compacted`, `summary_node_id`, `host_basis`, `ordinal`, `usage_contract` (`schema.py`; current `SCHEMA_VERSION = 60`). Indexes: unique `(source_path, line_no)`, `(session_id, ts)`, `(host, ts)`; no triggers. An `id`-ordered keyset scan rides the rowid primary key, so no secondary index participates.
- **Column-divergence reality**: current writers (`lifecycle._backfill_raw_events`, both local and `_REMOTE_RAW_INSERT`, plus the Claude-live incremental insert) bind the identical packed value to `raw_line` and `parsed_json`, for every host. Columns can differ only in legacy rows (pre-ENH-3422 per-line hosts stored `raw_line` as the verbatim source line) and after `recompress_raw_events`, which packs each column independently — so a row can legitimately hold one TEXT and one BLOB column. Independent per-column handling is a hard requirement, not a theoretical one.
- **Reader asymmetry**: replay and certification read only `raw_line` (`_usage_raw_cursor`, the rebuild raw-events cursor, the Codex first-cursor SELECT, `usage_refresh._stored_signatures`); `parsed_json` is read only by `usage_refresh.refresh_raw_events`' unchanged-source comparison. Redacting `parsed_json` differently from `raw_line` therefore affects refresh status but not replay input.
- **Row deletion/re-keying paths (what "vanished" can mean)**: local `refresh_raw_events` deletes by `source_path` and re-inserts, producing new AUTOINCREMENT ids above any captured snapshot; local `prune` deletes compacted rows. Both are refused on remote (`refuse_on_remote` / `_REMOTE_REFUSALS`), and the only remote `raw_events` writes found are `INSERT OR IGNORE` statements. Consequence: on remote, a guard miss comes from another redactor or an out-of-band writer, never from a refresh delete; locally, vanished candidates are reachable.
- **Writable-open seam**: `SqliteBackend.connect` and `schema.connect` always run `ensure_db` first (creates parent dir/file, applies migrations, sets WAL), so there is no non-creating schema-checked writable open today. `backend.py` already imports `sqlite_file_uri` but every non-test call uses default read-only mode; `mode="rw"` has no non-test caller anywhere under `scripts/little_loops/`. `sqlite_file_uri` accepts only `ro`/`rw` and never stats or creates the file.
- **Remote read/version facts**: `LibsqlConnection.execute` returns `LibsqlRow` objects supporting index, name, `keys()`; BLOB columns come back as `bytes`, TEXT as `str`, integers travel as strings. `HranaStub` mirrors this wire encoding, and `scripts/tests/test_hrana_client.py`, `TestExecute.test_round_trips_every_value_type`, already proves a low-level BLOB round trip. The remaining proof gap is the public backend's typed BLOB `IS ?` guards, unchanged-column retention and summed guarded-batch reconciliation, not basic BLOB transport. A 0-row UPDATE step inside `execute_many` is a successful step (later steps still run), and an empty batch returns 0 without a request. `HranaClient._post` never retries (any `OSError`/`HTTPException` → `HranaUnavailable`, default 10 s timeout) and reads whole response bodies with no row or byte cap, so read-side bounding must be applied by the caller's `LIMIT` and row selection.
- **Schema-version probing differs per backend**: `schema._current_version(conn)` catches only `sqlite3.OperationalError`, so over a remote connection a missing `meta` table surfaces as a `HranaOperationError`, not the "no such table" branch. `cli/doctor.py` (≈ line 780) uses `remote_schema.read_state(client)` for remote and `_current_version` for local; `LibsqlConnection.client` exposes the `HranaClient`. A read-only remote connection enforces only the project check and tolerates behind/ahead stores; `remote_schema.check_access(write=True)` is what refuses behind/ahead/unstamped stores with migration guidance. This refines the earlier "Strict preview seams" finding: the local probe is `_current_version`, the remote probe is `read_state`.
- **`main_session` ordering anchors**: the raw-argv `migrate` check runs first; `cli_event_context(DEFAULT_DB_PATH, ...)` opens before `parse_args()`; `--db` is `type=Path, default=DEFAULT_DB_PATH` on the top-level parser, so an explicit `--db .ll/history.db` is indistinguishable from the default and is treated as default-shaped (remote is chosen when a backend is configured and `LL_HISTORY_DB` is unset). `main_session` has no outer `HistoryError` handler (handling is per branch) and no `KeyboardInterrupt` handling; argparse `SystemExit` (including `--help`/invalid args) currently happens inside the telemetry context for every command except raw-argv `migrate`.
- **Credential-safe target label**: `BackendConfig` holds env-var names, never token values; `RemoteTarget.provider` and `config.project_id` are available; `HranaClient.__repr__`/`__str__` omit the token. No helper renders a provider/project label today (`_main_migrate` prints only the provider), so the report's target label is net-new.

## Implementation Steps

1. Run `/ll:spike ENH-3752` for the internal typed-guard/reconciliation mechanism before production implementation. Through the public backend and `HranaStub`, prove mixed original TEXT/BLOB, equal bytes with different SQL types, exact/missing guards, NULL/COALESCE unchanged-column byte/type retention, NOT NULL schema prerequisites, bounded CAST/length projections, short summed counts, committed-but-lost acknowledgement, and bounded reconciliation. Assert BLOB/base64 guard wire encoding as well as stored outcomes. `spike_needed: true` makes absent proof visible to `ll-learning-tests assess`; leave `unproven_mechanism: true` until the proof is recorded by the spike workflow. A passing stub establishes SQLite/client/protocol behavior; hosted-provider parity remains an explicit deployment assumption, not a claim of provider validation. Then add the report/strict-preview/concurrency tests. ENH-3751 still gates integration/rollout.
2. Implement the single-statement bounded BLOB projections, SQL-type-preserving independent decoding, strict JSON/codec checks and keyset progress with safe per-row problems. Add the registry-derived public context query and its tests in `pii.py`/`test_pii.py`.
3. Implement short local transactions and Option A remote batches with exact-value/context guards, bounded reconciliation/retry and truthful counters.
4. Add package exports and no-telemetry CLI dispatch with safe JSON/error/exit behavior.
5. Document the logical guarantee, counts/uncertainty and rollout order; run focused backend/CLI/parity gates and `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/session_store/backend.py` — add the non-creating writable local open built on `sqlite_file_uri(path, mode="rw")` here, not in `raw_redaction.py` (raw `sqlite3.connect(` outside the chokepoint fails `test_history_store_chokepoint_gate.py`); leave `_REMOTE_REFUSALS` without a `redact` key
- Update `scripts/little_loops/cli/session.py` — module-level `redact_raw_events` import; `redact` branch dispatched from parsed args before `cli_event_context`; add `redact` to the module docstring "Subcommands:" list, the `_build_parser` epilog examples and the `main_session` dispatch chain; no new `resolve_history_db` call
- Update `scripts/little_loops/session_store/__init__.py` — import block from `raw_redaction` plus `__all__` entries (`TestPackageReexportSurface` requires every `__all__` name to resolve)
- Add `TestRedactSubcommand` to `scripts/tests/test_ll_session.py`, a `TestMigrateCommand`-style no-telemetry class to `scripts/tests/test_remote_schema.py`, and a positive `redact` case to `TestSupportedOperations` in `scripts/tests/test_remote_operation_matrix.py`; do not add `redact` to `_REJECTED`
- Add gate-aware checks: confirm `test_history_store_chokepoint_gate.py`, `test_usage_selection_chokepoint_gate.py`, `test_session_reader_no_host_roots_gate.py` and `test_remote_callers_bug3652.py` still pass with the new module in the tree
- Update `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` (with ToC link) and `docs/reference/API.md`; add `DOC_STRINGS_PRESENT` rows in `scripts/tests/test_wiring_reference_docs.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Conventions in force (evidence, not templates)**:
  - Subcommands are declared inline in `_build_parser()` (`cli/session.py`), and a new one appears in three places in that file: the module docstring subcommand list, the parser `epilog` examples, and the `main_session` dispatch chain. Only shared flags use `cli_args` helpers (`add_json_arg`); `--dry-run` is hand-declared per command (`prune`), `--batch` is a plain `type=int` on `recompress`.
  - Positive-int validation: `_positive_int` (`cli/history.py`) is the argparse model and is reused by import (`cli/harness.py`); library-side bool rejection is open-coded per site (`isinstance(x, bool) or not isinstance(x, int)`), with no shared helper — two flavors exist (raise `ValueError`, return `None`).
  - Reports: older maintenance functions return plain dicts; newer ones return frozen dataclasses (`RefreshResult`/`SourceRefresh` in `usage_refresh.py`, `RebuildState`, `MigrationReport`), with reason vocabularies held as module tuples or docstring lists, not `Literal`. Contested: `SourceRefresh.reason` is a free string while `HISTORY_ERROR_REASONS` is a tuple.
  - Partial-failure exit contract: `refresh` is the only `ll-session` maintenance command that exits 1 on partial failure and still prints the full JSON object on stdout; `recompress`/`prune`/`compact` exit 0 unconditionally. `cli/session.py` has no structured JSON error object (the `{"error": msg}` shape exists in `cli/queue.py` and `cli/loop/queue.py`), so single-document error output is a new convention for this file.
  - Dry-run opening is contested: `prune(dry_run=True)` opens writable and rolls back; `rebuild_needed` and the `_main_migrate` probe use `connect_readonly`. The issue's strict-read-only requirement follows the second.
  - Remote handling is contested: `recompress`/`prune`/`refresh` call `refuse_on_remote`; `migrate`, `rebuild_needed`, and `backfill --since` branch on `RemoteTarget`. `redact` belongs to the second group.
  - Exports: `session_store/__init__.py` imports names explicitly and lists them in `__all__` next to related functions; `TestPackageReexportSurface` requires every `__all__` name to resolve as a package attribute. Some CLI-only functions (`refresh_raw_events`, `refuse_on_remote`) are imported directly from their submodule rather than re-exported.
- **Test conventions**: CLI tests have an argparse-only layer (`patch("sys.argv", ...)` + parse) and a dispatch layer (patch `little_loops.cli.session.<fn>`, call `main_session()`); real-store CLI tests use a seeded DB and parse stdout JSON (`test_ll_session_refresh.py`); remote CLI tests write `.ll/ll-config.json` with a libsql provider, point `LL_HISTORY_URL` at `HranaStub`, and inspect `stub.db`; library tests seed `raw_events` with raw `INSERT`s and assert `typeof(raw_line)`/`typeof(parsed_json)` (`TestRawEventsPayloadCompression`). Doc wiring is pinned by `DOC_STRINGS_PRESENT` rows `(doc, needle, issue_id)` in `test_wiring_reference_docs.py`; there are no rows for `recompress`/`refresh`.
- **Doc surface facts**: `docs/reference/CLI.md` `### ll-session` has a subcommand table, per-command flag blocks, an examples block, and a paragraph listing commands refused under a remote backend; `docs/reference/CONFIGURATION.md` carries a "not supported remotely" bullet naming `recompress`; `docs/guides/HISTORY_SESSION_GUIDE.md` does not mention `recompress` or `refresh` (retention content sits under its Retention & Pruning section); `docs/reference/API.md` lists `session_store` imports in a fenced block without `recompress_raw_events`.

## Acceptance Criteria

- [ ] Both TEXT/BLOB columns are scrubbed independently with original types/unchanged bytes preserved, including unchanged siblings retained by NULL/COALESCE; rerun makes zero writes; metadata/links/cursors/watermarks are identical and no original files are required.
- [ ] Preview performs no payload/schema/progress/telemetry writes or target creation, resolves the actual requested/configured store, and rejects invalid batch sizes safely.
- [ ] Guards bind exact original bytes/SQL types and context; concurrent changes/deletions, short counts, impossible counts, ambiguous commits and bounded retries never overwrite another writer or fabricate per-rule attribution.
- [ ] Reports separate confirmed/lower-bound writes, unattributed changes, reconciled state and exact count availability; row failures/unconfirmed work make the scan incomplete/nonzero with closed reason codes and named input/page/candidate/request limits. No total RSS or malformed-server-response guarantee is implied.
- [ ] Required internal proof is recorded before production implementation; tests pin typed BLOB guards, NULL/COALESCE retention and short/ambiguous acknowledgement reconciliation through the public backend.
- [ ] Snapshot/keyset/interruption behavior is rerunnable and truthfully bounded; help/docs/JSON state the observation boundary, raw-only exclusions and ENH-3751-before-maintenance rollout.
- [ ] Post-scrub refresh/certification/replay remains compatible; package/doc/remote operation gates and `python -m pytest scripts/tests/` pass.

### Required Boundary Cases

- Exactly-at-cap and cap+1 stored/decoded values, decompression bombs, truncated/trailing/concatenated streams, invalid UTF-8 stored as TEXT/BLOB, duplicate JSON keys, non-object/non-finite JSON and excessive nesting; rejected whole rows remain byte/type stable and progress advances.
- Captured local/remote queries never return an over-cap payload. Captured read/write requests establish the declared byte ceilings, including new TEXT escaping and guard base64 overhead; a large `--batch` does not bypass them. Concurrent growth between reads cannot bypass the in-statement projection.
- No-op and failed columns preserve independent bytes/types. When only one column changes, SQL NULL retains the sibling's bytes/type without re-binding it. Equal TEXT/BLOB bytes with a changed SQL type fail the guard. Supported Claude/Kimi and known Codex pairs work; unknown Codex/host rows refuse without exposing context.
- Preview preserves main DB/WAL bytes and emits no logical DB, schema, telemetry or progress mutation. Explicitly allow only SQLite shared-memory/lock bookkeeping needed for a consistent live-WAL read; no immutable-WAL shortcut or target creation.
- Failed post-snapshot runs preserve accrued confirmed counts and return one incomplete JSON report; second guard misses never loop. Interrupt before/after a snapshot and during local/remote writes: safe error/report, exit 130, local rollback and no presumed remote commit/rollback. No global cleanliness or exact attribution is inferred from reconciliation.
- Acknowledged short batches with ABA restores and ordinary retries use update-application units; reconciled observations overlap them. Pin the example and inequalities in Report and count semantics, including a case where applications plus reconciled exceeds candidate rows.

## Scope Boundaries

Logical raw-column cleanup only. No physical secure erase, engine-memory bound, derived/FTS/live cleanup, source rewrite/re-ingestion, automatic rebuild/VACUUM, whole-table snapshot isolation, durable resume token, schema migration, backend wrapper redesign, exact per-rule attribution from summed partial counts, or guarantee covering later concurrent writes.

## Impact

- **Priority**: P2 — removes supported legacy raw matches, including shared remote rows.
- **Effort**: Very Large — backend-neutral maintenance with bounded remote reconciliation and precise reporting; implement in the proof/core/backend/CLI milestones above.
- **Risk**: Medium — concurrent writes and ambiguous acknowledgements need explicit semantics; fail-safe guards avoid destructive source/metadata changes.
- **Breaking Change**: No API removal; the new command changes only explicitly requested raw payloads.

## Review Notes

Reviewed on `main`, 2026-10-05, with `/ll:advise` using `claude-opus-5-5`. Added the ENH-3751 blocker, strict no-write preview, typed/context guards, explicit bounded reconciliation, and truthful lower-bound counters. Retained Option A on the guarded backend surface rather than expanding Hrana wrappers or attributing writes from later observations. No automated derived cleanup is implied.

Follow-up review on 2026-10-06 (Opus confidence 0.72) settled registry-derived unknown-context refusal, in-statement BLOB projections, SQL-type guards, fixed byte limits, strict corrupt-row handling, and live-WAL preview bookkeeping. Removed the completed sanitizer dependency; ingest compatibility remains a hard blocker. Retained the existing summed-rowcount backend API and conservative attribution rather than expanding per-statement results. A second miss is a bounded conflict, not proof of a broken guard, because concurrent ABA changes are possible. Cached scores/verdict were cleared; proof and fresh assessment remain implementation prerequisites. No implementation edits were made.

Additional review on 2026-10-06 with `/ll:advise` using `claude-opus-5-5` (confidence 0.78) made the required internal proof machine-visible, selected NULL/COALESCE retention for unchanged siblings without weakening typed/context guards, separated page/replacement/request budgets, and specified closed diagnostics and interruption reporting. The proof gate previously returned `not_required` despite the prose prerequisite. The read-response envelope is derived from capped projections, not enforced by the transport. Hosted-provider parity remains an explicit assumption until exercised there. No production implementation was added.

A focused second Opus consult (confidence 0.85) confirmed that additive short-batch counts plus retries cannot prove distinct changed rows under ABA. Renamed the proposed counters to update-application units, documented overlapping reconciliation and the conservative attributed-row lower bound, and added concrete ABA/report invariants. Retained the summed-rowcount backend API; tighter distinct-row estimation would add bookkeeping without recovering a partition. Also corrected the wire-sizing rationale: the proposed threefold TEXT bound from the first consult is unsafe for valid unescaped DEL; use actual encoding or the conservative sixfold bound plus envelope overhead.

## Blocked By

- ENH-3751

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

Historical assessment of the earlier plan; re-run after the revised contract and required spike proof. ENH-3751 remains open and the spike proof is absent.

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 74/100 → MODERATE (capped from 78 — Unproven Mechanism Cap, ENH-3350)

### Concerns
- Spec is otherwise implementation-ready: cited seams (`recompress_raw_events`, `resolve_history_target`, `connect_readonly`, `sqlite_file_uri(mode="rw")`, `cli_event_context`, `sanitize_history_payload`, `hrana_stub.py`) exist; `raw_redaction.py` and `test_raw_redaction.py` are intentionally new. Program Design gate, parity, claim and structure checks are clean.

- Dependency metadata was corrected during review: only ENH-3751 remains unresolved; ENH-3750 is completed. The prior readiness assessment is historical and needs re-running after this revised plan.

### Gaps to Address
- Unresolved `blocked_by`: ENH-3751 (open); ENH-3750 is done. `sanitize_history_payload` has no non-test caller yet, so ingest wiring is absent. Shipping order is ENH-3750 → ENH-3751 → ENH-3752; the CLI is unsafe to roll out before ENH-3751's compatibility wiring (Codex first-cursor certification compares plaintext source against stored payloads).

### Outcome Risk Factors
- Unproven mechanism: typed BLOB `IS ?` guards over Hrana are unexercised, and no guarded `UPDATE raw_events` or keyset scan precedent exists in the codebase — run `/ll:spike` before implementing.
- Moderate per-site complexity: short-count/ambiguous-commit reconciliation, lower-bound count attribution and byte-budgeted remote chunking share state across one new module and two backends.
- Broad enumeration across ~15 sites (new module, backend helper, CLI, exports, ~8 test files, 4 docs) with several chokepoint gates to keep green.

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Confidence Check Notes listed the sanitizer-API blocker as still open; it is done. Only the ingest-wiring blocker remains open. Corrected in place.

## Session Log
- `/ll:confidence-check` - 2026-10-06T09:57:04 - `6e20ecba-9b39-4fa5-a2d1-2716b647e53a.jsonl`
- `/ll:verify-issues` - 2026-10-06T09:55:28 - `5670a7ad-a6f3-4ca8-8442-6031f1500522.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T09:53:43 - `61d58fe9-ad6e-4e80-ba4c-3aba78f84c55.jsonl`
- `/ll:confidence-check` - 2026-10-06T09:45:03 - `516d313f-0876-453e-a4bd-d939284c79cd.jsonl`
- `/ll:verify-issues` - 2026-10-06T09:42:19 - `4eeb9aca-1309-400c-ae28-1d7a375687ea.jsonl`
- `/ll:wire-issue` - 2026-10-06T09:39:00 - `811edce9-fc13-4f33-9a06-63ced28c5602.jsonl`
- `/ll:refine-issue` - 2026-10-06T09:31:38 - `072141b9-68bd-494d-8ef6-a4eb91ff0db1.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:46:34 - `2fc077e6-f247-45dc-97b8-6729a8243496.jsonl`
- `/ll:issue-size-review` - 2026-10-06T00:26:44 - `09ea1492-1a86-4cce-bf60-5f1435b6dea3.jsonl`
