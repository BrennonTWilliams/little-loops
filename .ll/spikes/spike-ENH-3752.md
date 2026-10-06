# Spike Plan: ENH-3752 — guarded raw_events redaction persistence core

## Context

ENH-3752 has no `### Outcome Risk Factors` section; its `## Implementation Steps` M0
and `## Confidence Check Notes` name the unproven mechanism (`spike=absent`,
`spike_needed: true`, `unproven_mechanism: true`):

> "run `/ll:spike ENH-3752` through the public backend and Hrana stub. Prove typed
> BLOB/context guards, mixed TEXT/BLOB and type-only differences, NULL/COALESCE
> retention/NOT NULL prerequisites, capped projections, nullable/nonpositive
> keysets, short counts and bounded retry/reconciliation, committed-but-lost
> acknowledgement, wire upper bounds for both write shapes, and interruption after
> local commit but before accounting."

Both canonical drivers apply: **(a)** no code anywhere issues a typed-guarded,
`COALESCE`-partial `UPDATE` through `LibsqlConnection.executemany` and reconciles a
short/ambiguous summed count; **(b)** no test exercises a committed-but-unacknowledged
remote write, a capped BLOB projection, or a nullable/nonpositive keyset over
`raw_events`.

Scope per risk: SQL guard semantics (typed BLOB `IS ?`, context type guards,
`COALESCE` retention, NOT NULL), capped projections, keyset, count/reconciliation
state machine, lost acknowledgement, wire-byte estimator, local commit/accounting
interruption. Hosted-provider parity is an explicit assumption, not tested.
Excluded: PII sanitizer logic (already proven by ENH-3750/3751), CLI routing, docs.

## Approach

A standalone `redaction_core.py` library that speaks only the cursor/`execute`/
`executemany` surface shared by `sqlite3.Connection` and the public
`LibsqlConnection`, so each AC runs against **real SQLite** (local) and the real
`HranaClient`→`HranaStub` (remote, stub backed by real SQLite). The "sanitizer" is a
fake: tests hand in desired replacement bytes. Faked: provider (stub, not Turso/sqld)
and the sanitizer. Real: SQL guards, SQLite typing, Hrana encoding, atomic
`execute_many`, stub post-execution stalls (commit-then-lost-ack), `sqlite_file_uri(
mode="rw"/"ro")`.

## Critical files

Contracts honored (not modified): `session_store/libsql.py`
(`LibsqlConnection.executemany` summed count), `session_store/hrana.py`
(`encode_value`, `execute_many`, `_post` body), `session_store/schema.py` (`raw_events`
DDL), `sqlite_uri.py`, `scripts/tests/hrana_stub.py`.

New spike paths: `scripts/tests/spike/enh3752_raw_redaction/`.

## Implementation

```
scripts/tests/spike/enh3752_raw_redaction/
├── __init__.py
├── conftest.py              # ll-spike-verdict hook (scaffolding, not promoted)
├── redaction_core.py        # SQL, projections, keyset, apply/reconcile, estimator
└── test_redaction_core.py   # AC + guard tests
```

```python
UPDATE_SQL: str                          # typed-guard COALESCE UPDATE (issue §Guarded persistence)
def projection_sql(cap: int) -> str      # typeof/length/capped-BLOB for both columns + context
def snapshot_max_id(conn) -> int | None
def fetch_page(conn, *, snapshot, last_id, limit, cap) -> list[Row]
def update_params(row, new_raw, new_parsed) -> tuple    # NULL = retain sibling
def apply_unit(conn, rows, *, local: bool) -> UnitResult # ack count / unconfirmed
def reconcile(conn, row, desired, *, retry_ok) -> Outcome # reconciled|retried|conflict|vanished|unconfirmed
def estimate_request_bytes(sql, params) -> int           # conservative wire upper bound
class Accounting                                          # commit-issued marker + atomic counters
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_type_only_difference_misses_guard` (local+remote) | typed BLOB guard: TEXT vs BLOB with equal bytes | behavior |
| `test_blob_context_misses_text_context_guard` | context `typeof` guard | behavior |
| `test_null_param_retains_sibling_bytes_and_type` (local+remote) | COALESCE retention, mixed TEXT/BLOB | behavior |
| `test_not_null_prerequisite_rejects_null_write` | NOT NULL column prerequisite | behavior |
| `test_capped_projection_bounds_value_and_reports_length` | capped projection; oversize→NULL w/ length; invalid-UTF-8 TEXT fetched as bytes | behavior |
| `test_keyset_nullable_nonpositive_and_holes` | empty `MAX(id)=None`; 0/negative/min-int IDs; deleted holes; explicit insert beyond max excluded | behavior |
| `test_full_ack_unit_counts_all_candidates` | summed count over `executemany` | behavior |
| `test_short_ack_is_committed_unit_with_misses` | short count ≠ rollback; others applied | behavior |
| `test_reconcile_classifies_desired_original_changed_missing` | reconciliation table | behavior |
| `test_retry_once_then_second_zero_is_conflict_no_loop` | bounded retry, ABA | behavior |
| `test_aba_counts_inequalities` | `updates_applied`/`unattributed`/`reconciled` ABA example | behavior |
| `test_committed_but_lost_ack_is_found_desired` | stub post-commit stall → `HranaUnavailable`; re-read sees desired (no `no_parallel` marker: it would skip under xdist and read as inconclusive) | behavior |
| `test_estimator_bounds_captured_executemany_and_execute_bodies` | wire upper bound, both write shapes | behavior |
| `test_two_1mib_text_replacements_fit_8mib_request` | single-row worst case fits cap | behavior |
| `test_captured_page_response_under_32mib` | read-response envelope derivation | behavior |
| `test_mode_rw_open_never_creates_and_ro_preview_leaves_bytes` | non-creating writable open; live-WAL preview byte equality | behavior |
| `test_interrupt_after_commit_before_accounting_is_unconfirmed` | commit-issued marker; rollback-acked = zero | behavior |
| `test_guard_spike_does_not_import_production_raw_redaction` | isolation guard (AST) | regression |
| `test_guard_no_private_client_calls` | no `conn.client.batch`/`_post` in spike library | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/enh3752_raw_redaction/ -v          # role: spike
python -m pytest scripts/tests/test_libsql_backend.py -v                # role: regression
python -m pytest scripts/tests/test_sqlite_uri.py -v                    # role: regression
python -m pytest scripts/tests/test_hrana_client.py -v                  # role: regression
```

## Out of Scope

Production `raw_redaction.py`, sanitizer/policy/context-registry query, bounded zlib
decoder, CLI/telemetry routing, docs, hosted-provider validation, RSS bounds. The
real `no_parallel` serial gate for lost-ack stalls runs at implementation time.

## Promotion

On acceptance, fold the proven SQL/projection/reconciliation/estimator code from
`scripts/tests/spike/enh3752_raw_redaction/redaction_core.py` into
`scripts/little_loops/session_store/raw_redaction.py` and the AC tests into
`scripts/tests/test_raw_redaction.py`, in a separate PR. `conftest.py` is scaffolding
and is not promoted.
