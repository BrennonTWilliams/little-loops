# Spike Plan: BUG-3762 — bounded single-row read/plan/reconcile for oversized `raw_events` payloads

## Context

BUG-3762's `### Outcome Risk Factors` (outcome confidence 64, hard-capped by
`unproven_mechanism`):

> - Unproven mechanism: the cap holds outcome at 64 until Step 1 (singleton wire capture,
>   cap/cap+1 bounds, expanded lost-ack reconciliation) is recorded and the flags cleared via
>   a proven spike.
> - The 8 MiB decoded budget doubles allocation growth, and structurally dense valid JSON is
>   unmeasured.
> - Dirty expanded rows on remote targets may not fit the guarded 8 MiB request estimate and
>   stay unredacted. … local targets have no request limit.
> - Deep per-site complexity … shared plan/reconcile/write state across `_handle`,
>   `_plan_row` and `_write_unit`.

Both canonical drivers apply: **(a)** no code reads one row with 8 MiB-per-column stored
caps in a single coherent SELECT, decodes under a parameterized 8 MiB cap, or reconciles a
lost acknowledgement through a read wider than the ordinary page cap; **(b)** no test
exercises any of that — `TestWireBounds` only covers the 1 MiB page.

Per risk, the spike must rule out:

| Risk | Failure to rule out |
|------|---------------------|
| singleton wire | one 2×8 MiB SELECT exceeds the 32 MiB captured-response ceiling or the full-page maximum; singleton cap/cap+1 not honored locally/remotely |
| decoded budget | parameterized decoder is unbounded, mis-orders refusals (decoded-byte exhaustion vs EOF/checksum/trailing; zero BLOB), or a structurally dense 8 MiB JSON blows memory unacceptably |
| request fit | request estimate applied to local targets, not incremental, or not an exact boundary; a remote dirty plan retained past the 8 MiB request budget |
| lost-ack | reconciliation through the ordinary 1 MiB read gives a false conflict (unchanged oversized sibling, or replacement grown past 1 MiB) or equates an unfetched value with original/desired |
| shared state | atomic row planning (failed sibling discards other plan) and guarded write/reconcile composed on the expanded path |

Excluded: the sanitizer (faked), CLI/report/docs fan-out (`report-contract-fanout`; plain
additive fields, not a mechanism risk), ingest paths.

## Approach

A standalone `singleton_core.py` that speaks only the `execute`/`executemany` surface
shared by `sqlite3.Connection` and the public `LibsqlConnection`, built on the already-proven
ENH-3752 spike core (typed guards, `apply_unit`, estimator). It adds only the new
mechanism: a parameterized bounded `decode_payload`, the singleton read, `plan_column`/
`plan_row` with stage-tagged byte refusals and the remote-only incremental request estimate,
and `reconcile_expanded` with a caller-chosen read cap. Real: SQLite, `LibsqlConnection` →
`HranaClient` → `HranaStub` (wire capture, commit-then-lost-ack stall), zlib, `tracemalloc`.
Faked: the sanitizer (marker replacement) and the provider (stub). Fixtures are seeded
incompressible hex text plus a controlled marker.

## Critical files

Contracts honored (not modified): `scripts/little_loops/session_store/raw_redaction.py`
(`decode_payload`, `_plan_column`, `_plan_row`, `_fetch_one`, `_Run._reconcile_one`,
`UPDATE_SQL`, caps), `session_store/libsql.py`, `session_store/hrana.py`,
`scripts/tests/hrana_stub.py`, ENH-3752 spike core
(`scripts/tests/spike/enh3752_raw_redaction/redaction_core.py`).

New spike paths: `scripts/tests/spike/bug3762_singleton_redaction/`.

## Implementation

```
scripts/tests/spike/bug3762_singleton_redaction/
├── __init__.py
├── conftest.py              # ll-spike-verdict hook (scaffolding, not promoted)
├── singleton_core.py        # decode, singleton read, plan_row, reconcile_expanded
├── driver.py                # fixtures + absolute tracemalloc peak scenarios
└── test_singleton_core.py   # AC + guard tests
```

```python
SINGLE_ROW_STORED_CAP = PAGE_ROWS_MAX * STORED_CAP      # 8 MiB
SINGLE_ROW_DECODED_CAP = 2 * DECODED_CAP                # 8 MiB
class Refusal(Exception): reason, limit_kind, limit_bytes, stored_bytes
def decode_payload(sql_type, data, *, decoded_cap=DECODED_CAP, kind="decoded") -> dict
def fetch_singleton(conn, row_id) -> Observed | None    # ONE select, both payloads + context
def plan_column(col, sanitize, *, stored_cap, decoded_cap) -> (bytes|None, int)
def plan_row(obs, sanitize, *, stored_cap, decoded_cap, request_cap) -> (Plan|None, problems)
def reconcile_expanded(conn, orig, want, counters, *, read_cap) -> verdict
def process_expanded(conn, obs, want, acct, counters, *, read_cap, after_apply=None) -> None
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `TestSingletonRead::test_cap_boundary_local_and_remote` | singleton cap/cap+1, both payloads + context, local and remote | behavior |
| `TestSingletonRead::test_one_statement_coherent_read` | one SELECT, no chunk requests | behavior |
| `TestSingletonRead::test_remote_wire_response_under_32mib_and_not_above_page` | singleton wire capture < 32 MiB, ≤ full page | behavior |
| `TestSingletonRead::test_over_cap_values_are_not_shipped` | withheld values stay off the wire | behavior |
| `TestBoundedDecode::test_decoded_cap_boundary_8mib` | decoded cap/cap+1, ordinary default retained | behavior |
| `TestBoundedDecode::test_highly_compressed_small_blob_needs_promotion` | decoded-only overflow of a small BLOB | behavior |
| `TestBoundedDecode::test_bomb_decode_is_hard_bounded` | no unbounded decompress | behavior |
| `TestBoundedDecode::test_decoded_exhaustion_precedes_unestablishable_defects` | validation order | behavior |
| `TestBoundedDecode::test_oversized_zero_blob_is_invalid_compression` | zero BLOB stays invalid | behavior |
| `TestBoundedDecode::test_recursion_has_no_byte_budget` | structural limits never promote | behavior |
| `TestPlanBounds::test_clean_expanded_row_needs_no_write` | clean row completes | behavior |
| `TestPlanBounds::test_local_dirty_expanded_scrubbed_beyond_request_estimate` | request limit remote-only | behavior |
| `TestPlanBounds::test_remote_dirty_over_request_refused_unchanged` | remote refusal, no write | behavior |
| `TestPlanBounds::test_request_estimate_exact_boundary` | cap/cap+1 of the estimate | behavior |
| `TestPlanBounds::test_incremental_estimate_skips_later_column` | no oversized dirty plan retained | behavior |
| `TestPlanBounds::test_replacement_output_budgets` | replacement stored/decoded cap/cap+1 | behavior |
| `TestPlanBounds::test_failed_sibling_discards_other_plan` | row atomicity | behavior |
| `TestExpandedReconciliation::test_lost_ack_found_desired_with_expanded_read` | expanded lost-ack | behavior |
| `TestExpandedReconciliation::test_ordinary_read_misclassifies_oversized_sibling` | why the wide read is needed | behavior |
| `TestExpandedReconciliation::test_replacement_grown_past_ordinary_cap` | replacement-only growth | behavior |
| `TestExpandedReconciliation::test_over_cap_version_is_conflict_not_convergence` | unfetched ≠ desired/original | behavior |
| `TestExpandedReconciliation::test_concurrent_change_and_vanish_never_overwrite` | concurrency | behavior |
| `TestRecordedPeaks::test_*` | absolute `tracemalloc` peaks recorded (sanity ceiling only) | measurement |
| `test_guard_spike_does_not_import_production_raw_redaction` | isolation guard | regression |
| `test_guard_no_private_client_calls` | public-surface guard | regression |
| `test_guard_no_chunked_or_hash_reads` | forbidden mechanism guard | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/bug3762_singleton_redaction/ -v     # role: spike
python -m pytest scripts/tests/test_raw_redaction.py -v                   # role: regression
python -m pytest scripts/tests/spike/enh3752_raw_redaction/ -v            # role: regression
```

## Out of Scope

Production wiring (`_Run._handle` promotion, `_Tally`, report/problem fields, CLI printer,
docs), the real sanitizer, over-cap ingest regressions, hosted-provider (Turso/sqld) parity
for large responses — an explicit assumption, not tested.

## Promotion

On acceptance, fold `decode_payload(decoded_cap=…)`, `fetch_singleton`/`_fetch_oversize_one`,
the stage-tagged refusal, the remote-only incremental request estimate and the
cap-parameterized reconciliation into `scripts/little_loops/session_store/raw_redaction.py`
and their tests into `scripts/tests/test_raw_redaction.py`, in a separate PR. The
`conftest.py` sentinel block is scaffolding and is not promoted.
