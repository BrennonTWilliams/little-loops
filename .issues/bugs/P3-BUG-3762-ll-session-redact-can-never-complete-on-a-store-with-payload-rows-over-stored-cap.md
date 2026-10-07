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
---

## Summary

`ll-session redact` refuses a `raw_events` payload column above `STORED_CAP` (1 MiB) before inspecting its contents. The run reports failure and tells the operator to rerun, but the same row is refused on every run. Clean legacy rows therefore prevent completion permanently.

Keep the existing page and write budgets. Add a separate bounded, coherent single-row read for larger payloads, with fixed internal limits, and report remaining size refusals honestly. Clean rows within those limits must reach completion; dirty rows must either be scrubbed with the existing full-value guards or remain entirely unchanged and explicitly incomplete.

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
- [ ] A dirty expanded row whose replacements and full guarded request fit the budgets is scrubbed atomically. If any input/output/request budget fails, both original payloads and their SQL types remain unchanged, `complete` is false, and exit status is 1. Never count a refused or known-dirty row as clean.
- [ ] Promotion covers stored-input overflow, decoded-input byte overflow even for highly compressed small BLOBs, and replacement stored/decoded overflow. JSON recursion and sanitizer structural limits do not trigger larger byte budgets.
- [ ] A fallback read observes both payload columns and host/event-type context in one statement. Concurrent changes, vanished rows, short/lost acknowledgements and bounded reconciliation never overwrite another version or equate unfetched values with original/desired bytes.
- [ ] Existing `TestWireBounds` remains green. Actual local/remote singleton reads respect their caps; captured remote page and singleton responses remain below 32 MiB, every serialized write request remains at most 8 MiB, and retained replacements remain at most 8 MiB.
- [ ] Malformed oversized values within the read budget retain specific validation reasons; in particular an oversized zero BLOB is invalid compression, rather than automatically a size refusal. Over-budget inputs are never fetched/decompressed without a hard bound.
- [ ] Text and JSON distinguish size-budget failures from other failures, identify the budget and available stored size, and explain why an unchanged rerun cannot resolve them. Distinct size-refused rows remain visible in aggregate after diagnostic truncation; two refused columns count as one failed row.
- [ ] Dry-run performs the same expanded validation and planning while writing no payload, schema, progress or telemetry. Mixed ordinary/expanded pages continue scanning once per row through the original keyset snapshot.
- [ ] Synthetic over-cap ingest regressions cover both backfill and usage-source insertion: both compressed columns actually exceed 1 MiB, decoded sensitive markers are replaced, and benign large content remains intact. Ingest continues to sanitize before storage.
- [ ] CLI/API/history-guide documentation states the fixed limits, new diagnostics, completion scope and manual remedy; no new public flag or config setting is introduced.

## Proposed Solution

### Selected approach

**Option A:** A separate bounded single-row path with the `unverifiable_oversize` reporting floor included in this selected design. Use one coherent SELECT rather than separate chunk requests. Keep `_fetch_page()` on its original projection; larger limits belong exclusively to the singleton path. Clean rows need no write. Dirty rows retain both full-value/type/context guards, and are refused when their request cannot fit.

> **Selected:** Option A — fixed bounded singleton reads, existing guarded writes, and explicit size-refusal reporting.

**Option B (rejected):** Raise the shared page projection through a user-selected size budget. This grows ordinary page responses and adds a public setting without helping an oversized guarded write fit its request limit.

**Option C (rejected as the sole fix):** Reporting-only changes. These explain failures but cannot provide a completion path for the observed clean rows. The selected approach incorporates this reporting protection for rows outside its safe budgets.

### Decision Rationale

The decision recorded on 2026-10-06 selected separate single-row processing and a reporting floor. This review makes that direction concrete and removes the stale flag-dependent instructions from the directive sections.

Clarification recorded as issue-scoped decision `66592853-37b3-4605-abc8-637fdbff52aa`, extending the original selection without changing its page/write safety requirements.

A singleton with **two 8 MiB stored payloads** returns the same maximum 16 MiB of payload bytes as an ordinary page of eight rows with two 1 MiB columns. Derive the singleton stored limit from `PAGE_ROWS_MAX * STORED_CAP` and test that invariant. BLOB projection makes remote payload encoding base64, approximately 21.34 MiB plus bounded context/envelope overhead, below the existing 32 MiB captured-response ceiling. Capture the real response in tests rather than relying only on arithmetic. A fixed **8 MiB decoded limit per column** covers the reported 4.7 MB decoded row while limiting allocation growth to twice the ordinary decoded budget.

Separate chunk requests would need a new snapshot/identity protocol: `scripts/little_loops/session_store/libsql.py` executes independently, and `scripts/little_loops/session_store/hrana.py` sends stateless requests. Matching lengths, types or context cannot detect same-size changes or ABA. One SELECT avoids constructing a payload from different versions and needs no remote adapter extension.

Retain the existing exact write guard. A large read does not imply a safe large write: the request includes both original payloads and all replacements, with base64/string encoding overhead. Rows that fail the estimate remain unchanged. Do not add hash-only guards, chunked writes, automatic deletion or a provider-specific extension.

The estimator leaves less space for dirty rows than for clean reads. With a small sibling and a replacement approximately the original size, two BLOB parameters cost about `8/3 * n` bytes, leaving less than 3 MiB for that dirty column; the conservative TEXT replacement estimate plus BLOB original guard costs about `10/3 * n`, leaving less than 2.4 MiB before overhead. A large sibling lowers those ceilings further. These are illustrative estimates, not a universal writable-size threshold: the full request estimate decides. Known-dirty rows above the safe write budget remain unredacted and must be reported as such. A larger write budget would require separate provider evidence and is outside this issue.

### Review evidence

Reviewed on 2026-10-06 against current production code. The focused baseline suite passed **527 tests** across `test_raw_redaction.py`, `test_ll_session.py`, `test_enh3751_sanitize_raw_events.py`, `test_remote_operation_matrix.py` and `test_wiring_reference_docs.py`. These establish existing contracts; they do not prove the proposed expanded path. Keep `unproven_mechanism` and `spike_needed` until an isolated local/remote proof establishes the bounds and reconciliation behavior.

`/ll:advise --signal user_requested --host claude-code --model opus` recommended the coherent singleton approach with **0.80 confidence**. Its main risks were decoded JSON allocation, dirty rows exceeding the guarded request budget, replacement expansion, reconciliation through the ordinary capped read, and truncated reporting. Adopted its lower decoded-limit alternative (8 MiB); deferred its dissent favoring larger write requests because this fix must preserve the existing write bound. Refetch only withheld payloads, reuse already coherent full observations for decode/output promotion, and report known-dirty unwritten rows explicitly. The decision remains provisional on the mechanism proof, not on further option selection.

## Integration Map

### Files to Modify

| File | Required integration |
|------|----------------------|
| `scripts/little_loops/session_store/raw_redaction.py` | Parameterized bounded projection/decoder; expanded row planning and singleton processing; full guarded writes and expanded reconciliation; precise size refusals and independent aggregate accounting; safety docstrings |
| `scripts/little_loops/cli/session.py` | `_print_redact_report()` size detail and actionable incomplete guidance; existing dispatch/parser/public flags remain compatible |
| `scripts/tests/test_raw_redaction.py` | Synthetic expanded-input/output fixtures, caps, validation, concurrency/reconciliation, dry-run/accounting and captured wire bounds |
| `scripts/tests/test_ll_session.py` | Additive report serialization, text guidance, truncated problems, CLI exit/no-telemetry behavior |
| `scripts/tests/test_enh3751_sanitize_raw_events.py` | Parameterized over-cap regressions for backfill and usage-source insertion |
| `docs/reference/CLI.md` | Report fields, limits, completion and size-refusal guidance |
| `docs/reference/API.md` | Additive dataclass fields, bounded singleton behavior; public function signature stays unchanged |
| `docs/guides/HISTORY_SESSION_GUIDE.md` | Document the completion path and replace blanket rerun advice |

### Dependent Files

- `scripts/little_loops/session_store/usage_refresh.py` has its own stored-payload decoder. Leave that read policy unchanged. Retain the ordinary default of the maintenance decoder for its existing direct callers and tests.
- `scripts/little_loops/session_store/lifecycle.py` sanitizes both ingest paths before serialization. Add coverage at the existing seams, rather than extending this maintenance bug into an ingest redesign.
- `scripts/little_loops/session_store/__init__.py` already exports the public report/problem types and entry point; no export change is needed.
- `scripts/tests/test_remote_operation_matrix.py` and `scripts/tests/test_wiring_reference_docs.py` must remain green. Preserve the documentation anchors for the redact flags, API entry point and stored-payload guide.
- `docs/reference/CONFIGURATION.md` only describes remote support, not these limits. No configuration or mandatory edit is required unless the final wording becomes inaccurate.
- The earlier ENH-3752 spike is independent of production code; do not mirror production changes into it. Defer changelog edits to release preparation.

### Behavior Parity

Preserve ordinary page limits, strict decode/context validation, original payload bytes/storage class for unchanged columns, full guards for both columns, row atomicity, snapshot/keyset accounting, bounded diagnostics, schema/target selection, and dry-run/no-telemetry behavior. Preserve the history guide's logical-cleanup scope and concurrency caveats while replacing its blanket rerun advice. Expanded processing changes only the bounded completion path and additive diagnostics.

### Similar Patterns and Tests

Use `TestLocalScrub`, `TestBoundedDecode`, `TestWireBounds` and remote `HranaStub` helpers in `scripts/tests/test_raw_redaction.py`. Preserve the ordinary `_fetch_one(conn, row_id)` call shape used by existing monkeypatches. The exact CLI dispatch kwargs test remains applicable because no argument is added. `RawRedactionProblem` additions need defaults to preserve existing three-argument construction/equality.

In `scripts/tests/test_ll_session.py`, update `_redact_report()` to supply the new aggregate in its base dictionary and use its existing override pattern for report assertions.

## Program Design

### Types

Preserve `STORED_CAP=1 MiB`, `DECODED_CAP=4 MiB`, `PAGE_ROWS_MAX=8`, `REQUEST_BYTES_CAP=8 MiB`, `REPLACEMENT_BYTES_CAP=8 MiB`, context bounds and `PROBLEM_CAP=100`. Add internal `SINGLE_ROW_STORED_CAP = PAGE_ROWS_MAX * STORED_CAP` (8 MiB) and `SINGLE_ROW_DECODED_CAP = 2 * DECODED_CAP` (8 MiB) per payload column. They are finite maintenance limits, not total Python heap guarantees; JSON parsing and sanitization still allocate structural objects and retain their depth/node limits. Decode/sanitize columns sequentially and release each source before processing the next.

Extend internal byte-limit refusals with a stage/effective bound so promotion does not depend on the overloaded `resource_limit` string. After the one allowed promotion, exhausted byte budgets become `unverifiable_oversize`; other validation failures keep their existing vocabulary. This is a per-row failure, not a new stop reason, and belongs only to the extra maintenance vocabulary, outside `pii.HISTORY_ERROR_REASONS`.

Add optional defaulted fields to `RawRedactionProblem`:

- `stored_bytes: int | None = None`: exact original stored column length, when column-specific; no decoded payload or source path.
- `decoded_bytes: int | None = None`: exact decoded input size only when available; null when bounded decode exhausted its cap.
- `limit_kind: str | None = None`: fixed vocabulary `stored`, `decoded`, `replacement_stored`, `replacement_decoded`, `request`.
- `limit_bytes: int | None = None`: the effective exhausted budget. Request problems use `column=None`; unavailable column sizes remain null.

Do not invent an exact decoded size after cap exhaustion. The diagnostic names the decoded budget that was exceeded; a bounded decoder knows only that output is larger than that limit.

Append defaulted `oversize_refused: int = 0` to `RawRedactionReport`, counting **distinct rows** refused by size budgets, a subset of `failed`. Maintain the corresponding row-id set independently of retained `problems`, so truncation cannot suppress guidance. Keep existing row/application/count semantics and the completion expression. JSON always includes the new fields: null metadata for non-size problems and zero aggregate when no row is size-refused.

Carry an internal expanded-plan marker/effective bounds for reconciliation; both original and desired values may exceed the ordinary projection. Plans used for writing must contain both complete original payload observations and validated context; never bind missing over-cap values as NULL guards.

### Signatures

- `redact_raw_events(db=DEFAULT_DB_PATH, *, batch_size=2000, dry_run=False) -> RawRedactionReport` — public signature remains unchanged.
- `decode_payload(sql_type: str, data: bytes, *, decoded_cap: int = DECODED_CAP) -> dict[str, Any]` — existing strict default; explicit larger limits only on the expanded path.
- `_projection_sql(*, stored_cap: int = STORED_CAP) -> str` — ordinary projection shape by default.
- `_fetch_oversize_one(conn: Any, row_id: int) -> _Observed | None` — planned internal helper, larger bounded projection for **both payloads plus both context columns in one SELECT**. Keep `_fetch_one()` unchanged for ordinary reconciliation.
- Thread effective stored/decoded limits through `_plan_column()` and `_plan_row()` for originals and replacements, rather than using the permissive unpack helper.

### Call Path

`_main_redact -> redact_raw_events -> _Run.scan -> _Run._handle -> _plan_row -> _plan_column -> decode_payload`

Expanded observations use the planned singleton helper; expanded writes reuse `_write_unit()` and `_Run._reconcile_one()` with the plan's effective read bounds.

### Decision Rules

1. `_Run._handle()` plans the ordinary observation. Promote the whole row once on stored-input overflow, actual decoded-input byte overflow, or stored/decoded replacement overflow. A request overflow is already a write refusal; larger read limits cannot make it fit. Structural resource failures never promote.
2. Before expanded processing, flush pending ordinary plans and respect any stop (dry-run has no pending writes). Refetch only when a payload value was withheld by the stored cap; replace the entire row observation and discard the earlier page's sibling/context and partial plans. For decoded/output overflow with both original values already present, reuse that coherent observation and replan under singleton limits without another read. A vanished refetch is an existing conflict outcome, counted scanned once. A shrunk row is replanned at singleton limits; changed context is validated afresh; a row now beyond the singleton stored cap is refused with its current size. Validate both columns anew.
3. Count the row once after final planning; promotion does not duplicate `scanned`, `would_change`, attributed counts or failure ids. Keep keyset advancement/snapshot semantics. No generic retry loop for repeated promotion or changes.
4. Clean rows produce no UPDATE. Dirty rows produce one atomic singleton unit only if all replacement limits, aggregate retained-replacement budget and the full request estimate fit. Check the remaining aggregate budget before retaining each column replacement in the plan; release an over-budget candidate immediately instead of accumulating two 8 MiB replacements. The 8 MiB retention bound covers planned/queued encoded replacements, not temporary serializer/compressor allocations or total heap. Include both original guards and every replacement in the estimate. Flush/release this unit before processing the next expanded row.
5. On lost/short acknowledgement, use the expanded bounded read for expanded plans, including when only a replacement grew beyond the ordinary cap. Retain full-byte desired/original comparisons and at most one guarded retry. An unfetched oversized value is never proof of convergence; vanished/changed/unconfirmed outcomes retain existing accounting.
6. A size refusal leaves the entire row intact, adds `unverifiable_oversize` with stage/limit metadata, and increments the distinct size-refused aggregate. A malformed value fetched within budget instead retains its validation code.
7. Text mode renders retained row/column/size/budget detail and explicitly states how many details were omitted. Stored/decoded input failures mean content could not be fully validated. Replacement/request failures mean supported redactable content was found but **not written**; report this explicitly, not just as "could not verify." For size-refused rows, explain that rerunning unchanged cannot help: review the reported row ids and reduce or remove the affected payloads through backend administration before rerunning. Manual modification/deletion is an explicit operator choice with replay/data-loss consequences; this command never performs it. No promise that prune/compact or a nonexistent flag solves the problem, since prune/compact are refused remotely and are not targeted by row size. When all size details are omitted, still print the aggregate and honest fixed-limit guidance; state that omitted rows may include known-dirty payloads left unredacted, and do not claim JSON contains omitted ids.

## Implementation Steps

1. **Prove the bounded mechanism first.** Use synthetic local SQLite and the existing libSQL/Hrana stub to capture a singleton with two maximum-sized columns, prove its raw response never exceeds the full-page maximum, prove strict cap/cap+1 limits for both read tiers and output/request budgets, and demonstrate expanded lost-ack reconciliation. Exercise realistic and structurally dense valid-object decoded fixtures; record allocation/runtime observations for the 8 MiB decoded budget and sequential source lifetime. Record results before clearing the mechanism/spike flags. If the fixed budgets cannot be proved, revise this design rather than weakening guards.
2. Add failing regressions for the reproduced clean row, decoded-only overflow and dirty expanded fit/refusal. Fixtures use seeded incompressible benign content plus a separately controlled sensitive marker; assert stored/decoded premises and sanitizer counts. Repeated-character padding alone does not exercise the stored limit.
3. Implement byte-limit stage metadata, internal bounds, coherent singleton refetch and one-time promotion. Cover replacement growth, unsupported context/storage, malformed compression/encoding/JSON, and preserved row atomicity. Keep ordinary callers on their existing defaults.
4. Integrate singleton guarded writes, bounded replacement lifetime and expanded reconciliation. Exercise dirty normal siblings, both-large columns, mutation between page/fallback and between plan/write, disappearance, short/lost acknowledgement, one guarded retry and a refetch now above the expanded cap. Assert no false success, no false conflict from an unchanged oversized sibling, and exact untouched siblings/types. Rerun a successfully scrubbed expanded row and require zero changes/failures. Pin captured request estimates against oversized BLOB and escaped/non-ASCII TEXT values.
5. Add report fields and CLI guidance. Test two refused columns as one failed/size-refused row; set `PROBLEM_CAP=1` with a non-size failure before a size failure and confirm the independent aggregate/guidance. Test JSON as one content-free object, complete/incomplete/interrupted exit codes, dry-run and zero telemetry.
6. Add over-cap ingestion coverage at both independent write seams, asserting both compressed column sizes, sensitive-marker removal and benign-content preservation. No ingest behavior change is currently justified.
7. Update the three affected docs and run the focused suite, then the authoritative `python -m pytest scripts/tests/` gate for implementation. Preserve existing wire/vocabulary/default-caller/remote-operation contracts. Run relevant lint/types only when production code changes.

## Impact

- **Priority:** P3 — affects completion on stores with large legacy payloads; existing refusals leave data unchanged.
- **Effort:** Medium — bounded refetch and decoder plumbing, singleton accounting/reconciliation, additive diagnostics and focused coverage.
- **Risk:** Medium — correctness of completion and memory/wire bounds; expanded reads must be proved before implementation is treated as ready.
- **Compatibility:** No new public command flag, function kwarg, schema, config setting or remote dependency. JSON gains optional problem metadata and one defaulted aggregate; document the additive contract.

## Status

**Open** | Created: 2026-10-06 | Priority: P3. The defect is reproduced. The design is reconciled; its local/remote mechanism proof is still required before production implementation.

## Confidence Check Notes

The earlier 85/100 readiness and 63/100 outcome assessment preceded this review and is historical, not a score for the revised design. Its unresolved flag/replacement decisions and rejected-option directive drift have been removed. Do not carry those scores forward without a new assessment.

Remaining risks are the increased decoded allocation, exact guarded-request fit, and expanded reconciliation. `unproven_mechanism: true` and `spike_needed: true` remain honest until the proof in Implementation Step 1 passes. No broader ingestion redesign or remote snapshot/chunk protocol is required by the selected design.

## Session Log
- `/ll:confidence-check` - 2026-10-07T02:01:21 - `f53e748b-82f7-41b3-bce8-59be22735cbb.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:06:04 - `51f4678d-2b6a-45cf-bb75-d154b3120223.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-07T01:04:15 - `c24bb708-1ad0-4da8-9d25-50c9d7db6349.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:01:29 - `fec5599b-fa5e-41b8-98dd-172ad808fa28.jsonl`
- `/ll:wire-issue` - 2026-10-07T00:59:39 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
- `/ll:decide-issue` - 2026-10-07T00:51:15 - `6b41f46f-0778-4eee-bd27-b06a454db20a.jsonl`
- `/ll:refine-issue` - 2026-10-07T00:47:16 - `707e2f6d-f91c-469f-87fe-53582d107779.jsonl`
- `/ll:format-issue` - 2026-10-06T23:51:15 - `a0ac9893-a394-4fc1-a6b5-800ff281d815.jsonl`
