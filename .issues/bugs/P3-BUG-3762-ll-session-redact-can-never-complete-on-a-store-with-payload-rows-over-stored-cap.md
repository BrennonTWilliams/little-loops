---
id: BUG-3762
title: ll-session redact can never complete on a store with payload rows over STORED_CAP
type: BUG
priority: P3
status: open
discovered_date: '2026-10-06'
labels: []
decision_needed: false
unproven_mechanism: true
verify_verdict: VALID
spike_needed: true
spike_attempted: true
spike_completed: true
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
risk_factors:
- id: decoded-allocation-8mib
  domain: outcome
  criterion: ambiguity
  description: Spike measured 387.8 MiB peak for structurally dense 8 MiB-decoded
    JSON; Step 3 must decide accept vs bound structural size
- id: multi-site-shared-state-change
  domain: outcome
  criterion: complexity
  description: About 8 sites with moderate shared plan/reconcile/write state across
    _handle, _plan_row and _write_unit
- id: report-contract-fanout
  domain: outcome
  criterion: change_surface
  description: Additive report/problem fields reach CLI printer, exports, JSON contract,
    tests and three docs
- id: stale-step1-proof-text
  domain: readiness
  criterion: issue_well_specified
  description: Implementation Step 1 and Status still describe the proof as pending
    although Spike Results records it passing
---

## Summary

`ll-session redact` refuses a `raw_events` payload column above `STORED_CAP` (1 MiB) before inspecting its contents. The run reports failure and tells the operator to rerun, but the same row is refused on every run. Clean legacy rows therefore prevent completion permanently.

Keep the existing page budgets and the remote request budget. Add a separate bounded, coherent single-row read for larger payloads, with fixed internal limits, and report remaining size refusals honestly. Clean rows within those limits must reach completion; dirty rows must either be scrubbed with the existing full-value guards or remain entirely unchanged and explicitly incomplete.

## Steps to Reproduce

1. Insert a valid, supported-context JSON payload whose compressed BLOB exceeds 1 MiB into both payload columns of an existing current-schema store.
2. Confirm the history sanitizer finds zero matches.
3. Run `ll-session redact --dry-run --json` twice.
4. Both runs return `complete: false`, `failed: 1`, and two column-level `resource_limit` problems. Text mode advises a rerun although it cannot change the result.

Observed under v1.167.0 on six clean user rows with 1.1–3.3 MB stored and 1.5–4.7 MB decoded per payload. Independently reproduced during this review on 2026-10-06 using synthetic data and a temporary SQLite store: seeded random hex text in a supported assistant payload, **2,278,273 stored bytes and 4,000,077 decoded bytes per column**, zero sanitizer matches, identical refusals on both dry runs. No private payload is needed for regression tests.

## Current Behavior

- In `scripts/little_loops/session_store/raw_redaction.py`, `_projection()` returns SQL type and byte length but no payload value above 1 MiB. Both `_fetch_page()` and `_fetch_one()` share this cap.
- `_plan_column()` maps the missing oversized value to `resource_limit`; the same code also covers decoded-byte exhaustion, JSON recursion, sanitizer structural limits, oversized replacements and request estimates. Those causes require different remedies.
- `decode_payload()` caps decoded output at 4 MiB, so increasing only the stored read limit would still refuse the largest reported row. A highly compressed row can exceed the decoded limit while remaining below the stored limit.
- `_plan_row()` discards both replacements if either column fails. Preserve this row atomicity.
- `_plan_row()` also refuses a dirty row whose estimated write request exceeds `REQUEST_BYTES_CAP`, on every target. That cap is a remote (Hrana) wire limit; local writes run `BEGIN IMMEDIATE … COMMIT` with no request-size limit, so locally the refusal is self-inflicted. No existing test pins a local request refusal (`test_raw_redaction.py` request-estimate tests use the remote stub).
- `_Run.report()` counts distinct failed rows; `problems` counts per-column diagnostics and retains at most 100 entries. A size refusal can be omitted entirely after earlier failures.
- In `scripts/little_loops/cli/session.py`, `_print_redact_report()` prints only aggregate failures and the generic rerun advice. `_main_redact()` returns 1 for an incomplete run and writes no telemetry.

## Root Cause

**File:** `scripts/little_loops/session_store/raw_redaction.py`

**Anchor:** `_projection()`, `_plan_column()`, `_Run._handle()`.

The capped page projection is also the only single-row projection. A length-only observation cannot be decoded or certified clean, and no alternate bounded read exists. The report loses the specific byte budget that prevented processing, then presents a deterministic refusal as something a rerun can resolve.

## Expected Behavior

Rows within the expanded single-row limits are actually validated under the current policy. Unchanged columns retain exact bytes and storage class. Rows that cannot be validated or safely written remain unchanged, keep the run incomplete, and carry a specific, content-free explanation. Completion retains the existing logical scan guarantee; it does not become a global database snapshot or cover physical erasure.

## Acceptance Criteria

- [ ] Clean BLOB and TEXT rows above the ordinary stored or decoded limit, but within the fixed single-row limits below, reach `complete: true` without changing either payload; repeated runs still complete.
- [ ] A dirty expanded row whose replacements fit the output budgets — and, on remote targets only, whose full guarded request fits — is scrubbed atomically; local targets apply no request-size limit. If any input/output budget (or the remote request budget) fails, both original payloads and their SQL types remain unchanged, `complete` is false, and exit status is 1. Never count a refused or known-dirty row as clean.
- [ ] Promotion covers stored-input overflow, decoded-input byte overflow even for highly compressed small BLOBs, and replacement stored/decoded overflow. JSON recursion and sanitizer structural limits do not trigger larger byte budgets.
- [ ] A fallback read observes both payload columns and host/event-type context in one statement. Concurrent changes, vanished rows, short/lost acknowledgements and bounded reconciliation never overwrite another version or equate unfetched values with original/desired bytes.
- [ ] Existing `TestWireBounds` remains green. Actual local/remote singleton reads respect their caps; captured remote page and singleton responses remain below 32 MiB, every serialized remote write request remains at most 8 MiB, and retained replacements remain within their bound (the 8 MiB remote request estimate; at most 8 MiB per column locally).
- [ ] Malformed oversized values keep the validation order `decode_payload` has today, bounded by the effective stored and decoded budgets: decoded-byte exhaustion takes precedence over EOF/checksum/trailing defects that cannot yet be established within that bound, and an oversized zero BLOB remains invalid compression. Over-budget inputs are never fetched/decompressed without a hard bound.
- [ ] Text and JSON distinguish size-budget failures from other failures, identify the budget and available stored size, and explain why an unchanged rerun cannot resolve them. On remote targets, incremental request estimation prevents retaining an oversized dirty plan; no separate total-replacement diagnostic is needed. Distinct size-refused rows remain visible in aggregate after diagnostic truncation; two refused columns count as one failed row. Guidance states that the entire refused row remains unchanged and may retain unredacted matches, including in a successfully validated sibling; discarded matches never enter successful-row counters.
- [ ] Dry-run performs the same expanded validation and planning while writing no payload, schema, progress or telemetry. Mixed ordinary/expanded pages continue scanning once per row through the original keyset snapshot.
- [ ] CLI/API/history-guide documentation states the fixed limits, new diagnostics, completion scope and manual remedy, and that the request-size limit applies to remote targets only; no new public flag or config setting is introduced.

## Proposed Solution

### Selected approach

**Option A:** A separate bounded single-row path with the `unverifiable_oversize` reporting floor included in this selected design. Use one coherent SELECT rather than separate chunk requests. Keep `_fetch_page()` on its original projection; larger limits belong exclusively to the singleton path. Clean rows need no write. Dirty rows retain both full-value/type/context guards on every target; on remote targets they are refused when their request cannot fit, while local targets have no request limit.

> **Selected:** Option A — fixed bounded singleton reads, existing guarded writes, and explicit size-refusal reporting.

**Option B (rejected):** Raise the shared page projection through a user-selected size budget. This grows ordinary page responses and adds a public setting without helping an oversized guarded write fit its request limit.

**Option C (rejected as the sole fix):** Reporting-only changes. These explain failures but cannot provide a completion path for the observed clean rows. The selected approach incorporates this reporting protection for rows outside its safe budgets.

### Decision Rationale

The decision recorded on 2026-10-06 selected separate single-row processing and a reporting floor. This review makes that direction concrete and removes the stale flag-dependent instructions from the directive sections.

Clarification recorded as issue-scoped decision `66592853-37b3-4605-abc8-637fdbff52aa`, extending the original selection without changing its page/write safety requirements.

A singleton with **two 8 MiB stored payloads** returns the same maximum 16 MiB of payload bytes as an ordinary page of eight rows with two 1 MiB columns. Derive the singleton stored limit from `PAGE_ROWS_MAX * STORED_CAP` and test that invariant. BLOB projection makes remote payload encoding base64, approximately 21.34 MiB plus bounded context/envelope overhead, below the existing 32 MiB captured-response ceiling. Capture the real response in tests rather than relying only on arithmetic. A fixed **8 MiB decoded limit per column** covers the reported 4.7 MB decoded row while limiting allocation growth to twice the ordinary decoded budget. In practice the decoded limit, not the stored limit, is the binding one — compressible JSON reaches 8 MiB decoded far below 8 MiB stored — and the documentation must say so.

Wire limits are not a heap bound. The current scan retains its ordinary page while handling a row, so up to 16 MiB of page payloads can coexist conservatively with a 16 MiB expanded observation, plus encoded replacements, parsed/sanitized objects and a reconciliation observation. The proof records an absolute peak for these overlapping lifetimes (mixed-page promotion, a local dirty write, lost-ack reconciliation) rather than gating on a relative ratio. Release obsolete partial plans and expanded observations promptly; process columns sequentially and do not retain expanded observations across rows. The conservative 32 MiB page-plus-singleton payload envelope is accepted provisionally, subject to the proof; it is not a 32 MiB total-memory guarantee.

Separate chunk requests would need a new snapshot/identity protocol: `scripts/little_loops/session_store/libsql.py` executes independently, and `scripts/little_loops/session_store/hrana.py` sends stateless requests. Matching lengths, types or context cannot detect same-size changes or ABA. One SELECT avoids constructing a payload from different versions and needs no remote adapter extension.

Retain the existing exact write guard on every target. On remote targets a large read does not imply a safe large write: the request includes both original payloads and all replacements, with base64/string encoding overhead, and rows that fail the estimate remain unchanged. Local targets (`BEGIN IMMEDIATE … COMMIT`) have no request-size limit, so planning skips the request estimate there; their retained replacements are bounded by the per-column 8 MiB output limit (at most 16 MiB retained), and the write binds up to ~32 MiB of parameters (both originals plus both replacements), including a transient SQLite copy that the recorded peak must include. Do not add hash-only guards, chunked writes, automatic deletion or a provider-specific extension.

On remote targets the estimator leaves less space for dirty rows than for clean reads. With a small sibling and a replacement approximately the original size, two BLOB parameters cost about `8/3 * n` bytes, leaving less than 3 MiB for that dirty column; the conservative TEXT replacement estimate plus BLOB original guard costs about `10/3 * n`, leaving less than 2.4 MiB before overhead. A large sibling lowers those ceilings further. These are illustrative estimates, not a universal writable-size threshold: the full request estimate decides. Known-dirty remote rows above the safe write budget remain unredacted and must be reported as such. A larger remote write budget would require separate provider evidence and is outside this issue.

### Review evidence

Reviewed on 2026-10-06 against current production code. The focused baseline suite passed **527 tests** across `test_raw_redaction.py`, `test_ll_session.py`, `test_enh3751_sanitize_raw_events.py`, `test_remote_operation_matrix.py` and `test_wiring_reference_docs.py`. These establish existing contracts; they do not prove the proposed expanded path. Keep `unproven_mechanism` and `spike_needed` until an isolated local/remote proof establishes the bounds and reconciliation behavior.

The additional review on 2026-10-06 passed **674 baseline tests**, including verifier/repair/probe/selector coverage alongside those redaction suites. Direct code review and `/ll:advise` with Opus (0.80 confidence) found no hidden singleton correctness flaw and recommended a conditional go for the proof only. Adopted incremental request estimation instead of a redundant aggregate-refusal label, explicit reconciliation-time conflict classification, counted-once replacement accounting, and measurable allocation/runtime proof gates. Its dissent considered an extra retention label and cautioned that a relative allocation gate assumes the ordinary baseline is acceptable; retain the existing request diagnostic and record absolute peaks alongside the relative measurements.

`/ll:advise --signal user_requested --host claude-code --model opus` recommended the coherent singleton approach with **0.80 confidence**. Its main risks were decoded JSON allocation, dirty rows exceeding the guarded request budget, replacement expansion, reconciliation through the ordinary capped read, and truncated reporting. Adopted its lower decoded-limit alternative (8 MiB); deferred its dissent favoring larger write requests because this fix must preserve the existing write bound. Refetch only withheld payloads, reuse already coherent full observations for decode/output promotion, and report known-dirty unwritten rows explicitly. The decision remains provisional on the mechanism proof, not on further option selection.

A further pre-implementation review on 2026-10-07 (direct code read plus `/ll:advise --signal user_requested --host claude-code --model fable`, 0.82 confidence) found that `_plan_row()` applies the remote-only request estimate to local targets, which made the "dirty rows above ~3 MiB stay unredacted" residual self-inflicted for the default target. Adopted: the request estimate is remote-only and local retained replacements are bounded by the per-column output limit; the Step 1 proof is reduced to one wire capture, cap/cap+1 tests, a lost-ack demonstration and recorded absolute peaks (relative ratio/runtime gates and the multi-sample protocol dropped); `decoded_bytes` is dropped from the problem fields; over-cap ingest regressions are split to a follow-up; three ordering contracts were pinned in the Decision Rules. Dissent retained: the local bypass could be argued scope creep for a P3, kept in because it is a few lines and no test pins a local request refusal.

## Integration Map

### Files to Modify

| File | Required integration |
|------|----------------------|
| `scripts/little_loops/session_store/raw_redaction.py` | Parameterized bounded projection/decoder; expanded row planning and singleton processing; full guarded writes (request estimate applied to remote targets only) and expanded reconciliation; precise size refusals and independent aggregate accounting; safety docstrings |
| `scripts/little_loops/cli/session.py` | `_print_redact_report()` size detail and actionable incomplete guidance; existing dispatch/parser/public flags remain compatible |
| `scripts/tests/test_raw_redaction.py` | Synthetic expanded-input/output fixtures, caps, validation, concurrency/reconciliation, dry-run/accounting and captured wire bounds |
| `scripts/tests/test_ll_session.py` | Additive report serialization, text guidance, truncated problems, CLI exit/no-telemetry behavior |
| `docs/reference/CLI.md` | Report fields, limits, completion and size-refusal guidance |
| `docs/reference/API.md` | Additive dataclass fields, bounded singleton behavior; public function signature stays unchanged |
| `docs/guides/HISTORY_SESSION_GUIDE.md` | Document the completion path and replace blanket rerun advice |

### Dependent Files

- `scripts/little_loops/session_store/usage_refresh.py` has its own stored-payload decoder. Leave that read policy unchanged. Retain the ordinary default of the maintenance decoder for its existing direct callers and tests.
- `scripts/little_loops/session_store/lifecycle.py` sanitizes both ingest paths before serialization. No ingest change or ingest regression coverage belongs in this maintenance bug; over-cap ingest regression coverage at the backfill and usage-source seams is split to a follow-up (not yet captured).
- `scripts/little_loops/session_store/__init__.py` already exports the public report/problem types and entry point; no export change is needed.
- `scripts/tests/test_remote_operation_matrix.py` and `scripts/tests/test_wiring_reference_docs.py` must remain green. Preserve the documentation anchors for the redact flags, API entry point and stored-payload guide.
- `docs/reference/CONFIGURATION.md` only describes remote support, not these limits. No configuration or mandatory edit is required unless the final wording becomes inaccurate.
- The earlier ENH-3752 spike is independent of production code; do not mirror production changes into it. Defer changelog edits to release preparation.

### Behavior Parity

Preserve ordinary page limits, strict decode/context validation, original payload bytes/storage class for unchanged columns, full guards for both columns, row atomicity, snapshot/keyset accounting, bounded diagnostics, schema/target selection, and dry-run/no-telemetry behavior. Preserve the history guide's logical-cleanup scope and concurrency caveats while replacing its blanket rerun advice. Expanded processing changes only the bounded completion path and additive diagnostics, plus skipping the remote-only request estimate on local targets.

### Similar Patterns and Tests

Use `TestLocalScrub`, `TestBoundedDecode`, `TestWireBounds` and remote `HranaStub` helpers in `scripts/tests/test_raw_redaction.py`. Preserve the ordinary `_fetch_one(conn, row_id)` call shape used by existing monkeypatches. The exact CLI dispatch kwargs test remains applicable because no argument is added. `RawRedactionProblem` additions need defaults to preserve existing three-argument construction/equality.

In `scripts/tests/test_ll_session.py`, update `_redact_report()` to supply the new aggregate in its base dictionary and use its existing override pattern for report assertions.

## Program Design

### Types

Preserve `STORED_CAP=1 MiB`, `DECODED_CAP=4 MiB`, `PAGE_ROWS_MAX=8`, `REQUEST_BYTES_CAP=8 MiB` (remote targets only), `REPLACEMENT_BYTES_CAP=8 MiB`, context bounds and `PROBLEM_CAP=100`. Add internal `SINGLE_ROW_STORED_CAP = PAGE_ROWS_MAX * STORED_CAP` (8 MiB) and `SINGLE_ROW_DECODED_CAP = 2 * DECODED_CAP` (8 MiB) per payload column. They are finite maintenance limits, not total Python heap guarantees; JSON parsing and sanitization still allocate structural objects and retain their depth/node limits. Decode/sanitize columns sequentially and release each source before processing the next.

Extend internal byte-limit refusals with a stage/effective bound so promotion does not depend on the overloaded `resource_limit` string. After the one allowed promotion, exhausted byte budgets become `unverifiable_oversize`; other validation failures keep their existing vocabulary. This is a per-row failure, not a new stop reason, and belongs only to the extra maintenance vocabulary, outside `pii.HISTORY_ERROR_REASONS`.

Add optional defaulted fields to `RawRedactionProblem`:

- `stored_bytes: int | None = None`: exact original stored column length, when column-specific; no decoded payload or source path.
- `limit_kind: str | None = None`: fixed vocabulary `stored`, `decoded`, `replacement_stored`, `replacement_decoded`, `request` (`request` arises on remote targets only).
- `limit_bytes: int | None = None`: the effective exhausted budget. Request problems use `column=None`; unavailable column sizes remain null.

On remote targets, for a dirty plan, the request estimate includes both complete original guards/context, retained replacements and the current candidate, with only future replacements represented as `None`; never estimate an unfetched original as a NULL guard. It dominates counted encoded replacement bytes: BLOB parameters cost at least 4/3 of their byte length, and ASCII TEXT replacements cost at least twice their encoded length. Check the partial request estimate before retaining a candidate or planning another column; an over-budget candidate is released and refused as `request`, with no second promotion. This bounds retained replacement bytes without a sixth diagnostic kind. `REPLACEMENT_BYTES_CAP` remains the ordinary queue budget; its accounting counts each encoded replacement once, not heap copies. TEXT `params` may retain a separate string copy, which belongs in the memory proof. Local targets skip the request estimate entirely; their retained replacements are bounded by the per-column output limit.

No decoded size is recorded. The diagnostic names the decoded budget that was exceeded; a bounded decoder knows only that output is larger than that limit.

Append defaulted `oversize_refused: int = 0` to `RawRedactionReport`, counting **distinct rows** refused by size budgets during initial planning, a subset of `failed`. Maintain the corresponding row-id set independently of retained `problems`, so truncation cannot suppress guidance. Put it in the immutable `_Tally` and update it together with failed ids/diagnostics in one transition; interruption must not produce `oversize_refused > failed` or partial promotion accounting. A later reconciliation observation beyond the singleton read cap is a changed/conflicting version, not a new planning refusal or size-refused id. Keep existing row/application/count semantics and the completion expression. JSON always includes the new fields: null metadata for non-size problems and zero aggregate when no row is size-refused.

Carry an internal expanded-plan marker/effective bounds for reconciliation; both original and desired values may exceed the ordinary projection. Plans used for writing must contain both complete original payload observations and validated context; never bind missing over-cap values as NULL guards.

### Signatures

- `redact_raw_events(db=DEFAULT_DB_PATH, *, batch_size=2000, dry_run=False) -> RawRedactionReport` — public signature remains unchanged.
- `decode_payload(sql_type: str, data: bytes, *, decoded_cap: int = DECODED_CAP) -> dict[str, Any]` — existing strict default; explicit larger limits only on the expanded path.
- `_projection_sql(*, stored_cap: int = STORED_CAP) -> str` — ordinary projection shape by default.
- `_fetch_oversize_one(conn: Any, row_id: int) -> _Observed | None` — planned internal helper, larger bounded projection for **both payloads plus both context columns in one SELECT**. Keep `_fetch_one()` unchanged for ordinary reconciliation.
- Thread effective stored/decoded limits through `_plan_column()` and `_plan_row()` for originals and replacements, rather than using the permissive unpack helper. `_plan_row()` also takes `request_cap: int | None = REQUEST_BYTES_CAP` (so existing direct callers keep today's behavior); the run passes `REQUEST_BYTES_CAP` for remote targets and `None` for local ones, derived from `_Run.remote`.

### Call Path

`_main_redact -> redact_raw_events -> _Run.scan -> _Run._handle -> _plan_row -> _plan_column -> decode_payload`

Expanded observations use the planned singleton helper; expanded writes reuse `_write_unit()` and `_Run._reconcile_one()` with the plan's effective read bounds.

### Decision Rules

1. `_Run._handle()` plans the ordinary observation. Promote the whole row once on stored-input overflow, actual decoded-input byte overflow, or stored/decoded replacement overflow. Detect a withheld oversized payload before decoding/sanitizing its in-bounds sibling so that obsolete work is not performed and discarded. A request overflow is already a write refusal; larger read limits cannot make it fit. Structural resource failures never promote. Run the context and column storage-class checks (`_context`, `unsupported_storage`) before deciding to promote, so a row that is refused regardless is never refetched.
2. Before expanded processing, flush pending ordinary plans and respect any stop (dry-run has no pending writes). If that flush sets a stop, the expanded row is left unplanned and unrefetched, and `last_scanned_id` does not advance past it. Refetch only when a payload value was withheld by the stored cap; replace the entire row observation and discard the earlier page's sibling/context and partial plans. For decoded/output overflow with both original values already present, reuse that coherent observation and replan under singleton limits without another read. A vanished refetch is an existing conflict outcome, counted scanned once. A shrunk row is replanned at singleton limits; changed context is validated afresh; a row now beyond the singleton stored cap is refused with its current size. Revalidate both columns before declaring clean or writing; a decisive bounded refusal may stop further planning while leaving the whole row unchanged.
3. Count the row once after final planning; promotion does not duplicate `scanned`, `would_change`, attributed counts or failure ids. Keep keyset advancement/snapshot semantics. No generic retry loop for repeated promotion or changes.
4. Clean rows produce no UPDATE. On remote targets, once a dirty replacement is found, estimate the request with both original guards and the replacements so far before retaining that candidate or planning the next column. If it cannot fit, release it and refuse as `request`; larger read limits cannot help. Local targets skip this estimate and rely on the per-column output limits. A final dirty plan must satisfy both effective output limits and, on remote targets, the full request estimate. Apply it immediately through `_apply([plan])`, without joining the ordinary queue, and release it before the next row. The 8 MiB replacement budget counts encoded replacement bytes once; it excludes temporary serializer/compressor allocations, TEXT parameter copies and total heap. Preserve the ordinary queue's existing budget. Copy the needed rule counts, then release the sanitizer result and serialized text before output re-decode so avoidable object trees do not overlap.
5. On lost/short acknowledgement, use the expanded bounded read for expanded plans, including when only a replacement grew beyond the ordinary cap. Retain full-byte desired/original comparisons and at most one guarded retry. An unfetched oversized value is never proof of convergence; a now-over-cap reconciliation version is classified changed/conflict, without incrementing failed/size-refused planning ids. Vanished/changed/unconfirmed outcomes retain existing accounting. The plan's expanded-read marker selects the bounded read for both `_classify` lookups in `_reconcile_one` (the initial one and the recheck after a zero acknowledgement).
6. A size refusal leaves the entire row intact, adds `unverifiable_oversize` with stage/limit metadata, and increments the distinct size-refused aggregate. Preserve a specific validation code when that defect is detectable within both effective input bounds. When bounded decode exhausts its cap before it can establish EOF/checksum/trailing validity, report the decoded-byte refusal; never exceed the cap to find a more specific defect.
7. Text mode renders retained row/column/size/budget detail and explicitly states how many details were omitted. Stored/decoded input failures mean content could not be fully validated. Replacement/request failures mean supported redactable content was found but **not written**; report this explicitly, not just as "could not verify." Every size-refusal message states that the whole row remains unchanged and may retain unredacted matches, including in a validated sibling discarded for row atomicity. For size-refused rows, explain that rerunning unchanged cannot help: review the reported row ids and reduce or remove the affected payloads through backend administration before rerunning. Manual modification/deletion is an explicit operator choice with replay/data-loss consequences; this command never performs it. No promise that prune/compact or a nonexistent flag solves the problem, since prune/compact are refused remotely and are not targeted by row size. When all size details are omitted, still print the aggregate and honest fixed-limit guidance; state that omitted rows may include known-dirty payloads left unredacted, and do not claim JSON contains omitted ids.

## Implementation Steps

1. **Prove the bounded mechanism first (reduced gate).** Using synthetic local SQLite and the existing libSQL/Hrana stub: (a) one captured wire test of a singleton with two maximum-sized columns, asserting the raw response stays below the 32 MiB captured-response ceiling and never exceeds the full-page maximum; (b) strict cap/cap+1 unit tests for both read tiers, the per-column output budgets and the remote request estimate; (c) one expanded lost-ack reconciliation demonstration; (d) one recorded absolute `tracemalloc` peak each for ordinary-page co-retention plus singleton processing, a local dirty write binding both originals and both replacements (~32 MiB of parameters, including the transient SQLite copy), and expanded reconciliation, with fixture hashes and Python version. There are no relative ratio/runtime gates and no multi-sample protocol: the 8 MiB limits are fixed constants and the peaks are recorded, not gated, unless one is surprising. If bounds or reconciliation fail, or a peak is unacceptable, revise this design and retain the flags rather than weakening guards. Record the results here before clearing `unproven_mechanism`/`spike_needed`.
2. Add failing regressions for the reproduced clean row, decoded-only overflow and dirty expanded fit/refusal. Fixtures use seeded incompressible benign content plus a separately controlled sensitive marker; assert stored/decoded premises and sanitizer counts. Repeated-character padding alone does not exercise the stored limit.
3. Implement byte-limit stage metadata, internal bounds, coherent singleton refetch and one-time promotion. Cover replacement growth, unsupported context/storage, malformed compression/encoding/JSON, and preserved row atomicity. Include a trailing/corrupt compressed stream whose stored input fits but whose decoded output exceeds the effective cap: it must stop boundedly with a size refusal, while an oversized zero BLOB remains invalid compression. Keep ordinary callers on their existing defaults.
4. Integrate singleton guarded writes, bounded replacement lifetime and expanded reconciliation. Exercise dirty normal siblings, both-large columns, mutation between page/fallback and between plan/write, disappearance, short/lost acknowledgement, one guarded retry and a refetch now above the expanded cap. Assert no false success, no false conflict from an unchanged oversized sibling, and exact untouched siblings/types. Rerun a successfully scrubbed expanded row and require zero changes/failures. Pin captured remote request estimates against oversized BLOB and escaped/non-ASCII TEXT values, and assert a local dirty expanded row whose originals plus replacements exceed the remote request estimate is scrubbed.
5. Add report fields and CLI guidance. Test two refused columns as one failed/size-refused row; set `PROBLEM_CAP=1` with a non-size failure before a size failure and confirm the independent aggregate/guidance. Test a dirty validated sibling with an input-refused sibling: both remain exact, discarded matches do not enter successful-row counters, and guidance warns of an unchanged atomic row with possible unredacted matches. Inject an interruption at the refusal-accounting boundary and require the aggregate to remain a subset of failed rows. Test JSON as one content-free object, complete/incomplete/interrupted exit codes, dry-run and zero telemetry.
6. Update the three affected docs and run the focused suite, then the authoritative `python -m pytest scripts/tests/` gate for implementation. Preserve existing wire/vocabulary/default-caller/remote-operation contracts. Run relevant lint/types only when production code changes.

## Impact

- **Priority:** P3 — affects completion on stores with large legacy payloads; existing refusals leave data unchanged.
- **Effort:** Medium — bounded refetch and decoder plumbing, singleton accounting/reconciliation, additive diagnostics and focused coverage.
- **Risk:** Medium — correctness of completion and memory/wire bounds; expanded reads must be proved before implementation is treated as ready.
- **Compatibility:** No new public command flag, function kwarg, schema, config setting or remote dependency. JSON gains optional problem metadata and one defaulted aggregate; document the additive contract.

## Status

**Open** | Created: 2026-10-06 | Priority: P3. The defect is reproduced. The design is reconciled and was trimmed on 2026-10-07 (remote-only request limit, reduced Step 1 proof gate, ingest regressions split to a follow-up); the reduced Step 1 proof is still required before production implementation.

## Confidence Check Notes

### Historical assessment

The earlier 85/100 readiness and 63/100 outcome assessment preceded this review and is historical, not a score for the revised design. Its unresolved flag/replacement decisions and rejected-option directive drift have been removed. Do not carry those scores forward without a new assessment.

Remaining risks are the increased decoded allocation and observation co-retention, exact guarded-request fit, and expanded reconciliation. `unproven_mechanism: true` and `spike_needed: true` remain honest until the proof in Implementation Step 1 passes. No broader ingestion redesign or remote snapshot/chunk protocol is required by the selected design.

### Latest recorded assessment

_Re-assessed by `/ll:confidence-check` on 2026-10-07 against the revised contract (remote-only request limit, reduced proof gate, three pinned ordering contracts); scores are current._

**Readiness Score**: 95/100 → PROCEED (isolated Step 1 proof first; production implementation remains conditional on its result)
**Outcome Confidence**: 64/100 → MODERATE (hard-capped from a raw 71 by `unproven_mechanism`)

The recorded outcome is below this project's configured 65-point gate. Code references re-verified against `raw_redaction.py` (`_plan_row` still applies the request estimate on every target at line 445, `_projection_sql()` takes no `stored_cap` yet); the Program Design, dependency, claim, parity and decision gates are all clean. Passing the Step 1 proof and clearing `unproven_mechanism` is what lifts the cap.

### Concerns
- Issue well-specified (15/20): the 8 MiB stored/decoded singleton limits are provisional until the Implementation Step 1 proof passes; the issue itself says to revise the design if they cannot be proved.

### Outcome Risk Factors
- Unproven mechanism: the cap holds outcome at 64 until Step 1 (singleton wire capture, cap/cap+1 bounds, expanded lost-ack reconciliation) is recorded and the flags cleared via a proven spike.
- Deep per-site complexity (10/25): about 8 sites with moderate shared plan/reconcile/write state across `_handle`, `_plan_row` and `_write_unit`.
- The 8 MiB decoded budget doubles allocation growth, and structurally dense valid JSON is unmeasured.
- Dirty expanded rows on remote targets may not fit the guarded 8 MiB request estimate and stay unredacted. This is by design but must be reported accurately; local targets have no request limit.
- Additive report/problem fields fan out to the CLI printer, exports, JSON contract, tests and three docs (change surface 18/25).

### Risk Factor Delta
- Added: none
- No longer reported: none
- Retained: `decoded-allocation-8mib`, `dirty-row-request-fit`, `expanded-reconciliation-lost-ack`, `multi-site-shared-state-change`, `report-contract-fanout`, `unproven-bounded-singleton-mechanism`
- Changed fields: none

## Spike Results

_Added by `/ll:spike` on 2026-10-07_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| Singleton wire: one 2×8 MiB SELECT stays under the 32 MiB response ceiling and the full-page maximum; cap/cap+1 honored locally and remotely | `TestSingletonRead::test_cap_boundary_local_and_remote`, `::test_one_statement_coherent_read`, `::test_remote_wire_response_under_32mib_and_not_above_page`, `::test_over_cap_values_are_not_shipped` | ✓ pass |
| Decoded budget: parameterized 8 MiB decoder is hard-bounded, ordered like today's `decode_payload`, structural limits never promote | `TestBoundedDecode::test_decoded_cap_boundary_8mib`, `::test_highly_compressed_small_blob_needs_promotion`, `::test_bomb_decode_is_hard_bounded`, `::test_decoded_exhaustion_precedes_unestablishable_defects`, `::test_oversized_zero_blob_is_invalid_compression`, `::test_recursion_has_no_byte_budget` | ✓ pass |
| Request fit: estimate is remote-only, incremental, exact at cap/cap+1, and bounds the captured wire body; local dirty rows beyond it are scrubbed | `TestPlanBounds::test_local_dirty_expanded_scrubbed_beyond_request_estimate`, `::test_remote_dirty_over_request_refused_unchanged`, `::test_request_estimate_exact_boundary`, `::test_incremental_estimate_skips_later_column`, `::test_replacement_output_budgets` | ✓ pass |
| Expanded lost-ack reconciliation: no false conflict from an oversized sibling or replacement-only growth; an over-cap version is a conflict, never convergence | `TestExpandedReconciliation::test_lost_ack_found_desired_with_expanded_read`, `::test_ordinary_read_misclassifies_oversized_sibling`, `::test_replacement_grown_past_ordinary_cap`, `::test_over_cap_version_is_conflict_not_convergence`, `::test_concurrent_change_and_vanish_never_overwrite` | ✓ pass |
| Shared plan/write state: row atomicity composed with guarded write/reconcile on the expanded path | `TestPlanBounds::test_failed_sibling_discards_other_plan`, `TestPlanBounds::test_clean_expanded_row_needs_no_write` | ✓ pass |

**Recorded absolute `tracemalloc` peaks** (Python 3.12.10, seeded fixtures; recorded, not gated — only a 1 GiB sanity ceiling applies):

| Scenario | Peak | Fixture |
|----------|------|---------|
| Ordinary page (8×2×1 MiB) co-retained + singleton plan, BLOB/BLOB ~8 MiB decoded | 55.3 MiB | `aa24d789f292` |
| Local dirty write, TEXT/TEXT ~8 MiB (≈31.7 MiB of bound parameters: both originals + both replacements) | 63.3 MiB | `aa24d789f292` |
| Remote lost-ack reconcile with plan retained (includes the in-process stub's allocations) | 39.7 MiB | `3716d74f6a4d` |
| Decoder refusing a 48 MiB zlib bomb at the 8 MiB cap | 16.1 MiB (~2× cap, transient) | n/a |
| **Structurally dense JSON** (`[{},{},…]`, 8 MiB decoded, 8 KB stored) decode + sanitizer-style walk | **387.8 MiB** (~46× the decoded size) | `27247012fe6a` |

**Findings to carry into implementation**

- The decoder's transient peak is ~2× its decoded cap, so the 8 MiB limit costs ~16 MiB transient per column, sequentially.
- The dense-JSON peak is the one surprising number. The fake sanitizer rebuilds the whole structure (as the real one does), so it covers parse plus a full copy. A stored size of 8 KB reaches it, so the 8 MiB decoded limit, not the stored limit, is the binding resource. Decide in Step 3 whether to accept it or bound structural size separately; the spike does not gate it.
- Remote request fit, as measured: a dirty ~1.6 MiB-stored column with a ~1.6 MiB-stored clean sibling fits the estimate and writes (captured body ≤ estimate ≤ 8 MiB); a row with two dirty ~3.6 MiB-stored columns is refused as `request` on remote and scrubbed locally (~31.7 MiB of bound parameters).

**Spike location**: `scripts/tests/spike/bug3762_singleton_redaction/` (plan: `.ll/spikes/spike-BUG-3762.md`)
**Verification**: 32 spike tests (29 AC + 3 guard) pass, plus regressions `test_raw_redaction.py` (61) and the ENH-3752 spike (37): 130 tests across 3 commands.
**Promotion**: fold into its production module under `project.src_dir` and its test under `project.test_dir`, in a separate PR.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-07 (post-spike re-score)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE (no cap: `spike_completed` suppresses the `unproven_mechanism` cap; raw sum 71 clears the 65 gate)

### Risk Factor Delta
- Added: `stale-step1-proof-text`
- No longer reported: `dirty-row-request-fit`, `expanded-reconciliation-lost-ack`, `unproven-bounded-singleton-mechanism`
- Retained: `decoded-allocation-8mib`, `multi-site-shared-state-change`, `report-contract-fanout`
- Changed fields: `decoded-allocation-8mib` — description

## Session Log
- `/ll:confidence-check` - 2026-10-07T06:18:12 - `a272514e-787d-48a7-ac65-893a82e6e4bf.jsonl`
- `/ll:spike` - 2026-10-07T06:03:01 - `8c655ae6-6aea-48c9-b19a-e5c5f9c860df.jsonl`
- `/ll:confidence-check` - 2026-10-07T05:51:23 - `8f69bdcc-23e5-40e5-af3a-a2f0f3e89cbf.jsonl`
- `/ll:ready-issue` - 2026-10-07T03:56:46 - `3c6d0c53-4b3d-4add-9a0f-232a9cd13bc0.jsonl`
- `/ll:confidence-check` - 2026-10-07T03:20:38 - `aecfbd08-532c-4197-ae58-4ddcb5df7be5.jsonl`
- `/ll:verify-issues` - 2026-10-07T03:14:57 - `d0c6965a-f073-4230-9107-254c09a30024.jsonl`
- `/ll:confidence-check` - 2026-10-07T03:03:27 - `23c0001a-6fdc-4e90-a957-6cc6382e6a26.jsonl`
- `/ll:confidence-check` - 2026-10-07T02:01:21 - `f53e748b-82f7-41b3-bce8-59be22735cbb.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:06:04 - `51f4678d-2b6a-45cf-bb75-d154b3120223.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-07T01:04:15 - `c24bb708-1ad0-4da8-9d25-50c9d7db6349.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:01:29 - `fec5599b-fa5e-41b8-98dd-172ad808fa28.jsonl`
- `/ll:wire-issue` - 2026-10-07T00:59:39 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
- `/ll:decide-issue` - 2026-10-07T00:51:15 - `6b41f46f-0778-4eee-bd27-b06a454db20a.jsonl`
- `/ll:refine-issue` - 2026-10-07T00:47:16 - `707e2f6d-f91c-469f-87fe-53582d107779.jsonl`
- `/ll:format-issue` - 2026-10-06T23:51:15 - `a0ac9893-a394-4fc1-a6b5-800ff281d815.jsonl`
