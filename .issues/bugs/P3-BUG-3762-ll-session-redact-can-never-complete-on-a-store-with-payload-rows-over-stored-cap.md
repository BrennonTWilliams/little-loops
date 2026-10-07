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
---

## Summary

`ll-session redact` (ENH-3752) refuses any `raw_events` payload column whose stored size exceeds `STORED_CAP` (1 MiB). It never inspects that row. Afterwards it prints `Failed: N row(s) left as found` and `Incomplete: rerun after resolving the above.` — but the operator has nothing to resolve. Rerunning refuses the same rows, so a store with even one large transcript row can **never** reach a complete redaction. The command can't tell "this row is unsafe" apart from "this row is too big to look at".

The 1 MiB / 4 MiB bounds are deliberate ENH-3752 design limits (page-size and wire-size safety). This issue does not ask to remove them. It asks for a path to completion and an honest, actionable report.

## Steps to Reproduce

1. Use a store with at least one `raw_events` row whose `raw_line` or `parsed_json` is over 1 MiB stored (zlib-compressed). A user turn carrying a large pasted or attached payload can reach this size.
2. Run `ll-session redact --dry-run -j`.
3. Observe `problems` entries `{"row_id": N, "column": "raw_line"|"parsed_json", "reason": "resource_limit"}`, `complete: false`, and the text-mode "Incomplete: rerun…" line. Rerun: the result is identical.

Observed on a consumer project's store under v1.167.0. Six rows (1.1–3.3 MB stored, 1.5–4.7 MB decoded, all `type: user`) were refused on every run. Decoded by hand and passed through `pii.redact_history_text`, all six contained **zero** matches. They were clean, yet the run can never report complete.

## Current Behavior

- `STORED_CAP = 1 << 20` (`scripts/little_loops/session_store/raw_redaction.py:93`). The page SELECT projects a column's value only when it is at most the cap (`:266`), and the plan step refuses larger values with `resource_limit` (`:391`).
- `cli/session.py:573` prints "Incomplete: rerun after resolving the above." with no indication that a `resource_limit` row cannot be resolved by rerunning, and no remedy.
- `DECODED_CAP = 4 << 20` (`raw_redaction.py:94`) would itself reject the largest observed row (4.7 MB decoded). The fix must also account for rows above the decoded bound.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- `resource_limit` is one code for six distinct causes today: stored column over `STORED_CAP`, text over `DECODED_CAP` (unreachable on scanned rows), zlib output over `DECODED_CAP`, `RecursionError`, a replacement over `STORED_CAP` (`_plan_column`), and a request estimate over `REQUEST_BYTES_CAP` (`_plan_row`, keyed `(None, "resource_limit")`). Reports cannot distinguish them.
- `_plan_row` discards a row's whole plan when either column is refused, so an in-bounds dirty sibling of an oversized column is also left unredacted (pinned by `test_failed_sibling_discards_planned_replacement`).
- A both-columns-oversize row yields two `RawRedactionProblem` entries but counts once in `failed` (`failed_ids` is a frozenset of row ids).
- Text mode prints no row ids, columns, sizes or reason codes; only `--json` `problems` (capped at `PROBLEM_CAP = 100`, rest counted in `omitted_problems`) carries them. The text line is `"{label}: N row(s) left as found (see --json for codes)."`, then `Incomplete: rerun after resolving the above.` (`cli/session.py:573`).
- Exit code is 1 whenever `complete` is false (`_main_redact`), so an automation wrapping `ll-session redact` fails permanently on an affected store.
- Ingest (ENH-3751) applies **no** byte cap: `_backfill_raw_events` (`lifecycle.py:854`) and `refresh_usage_source` (`lifecycle.py:1630`) run `sanitize_history_payload(...)` then `_pack_payload(json.dumps(...))` fully in memory. An over-cap incoming payload is therefore stored *sanitized*, not unsanitized and not refused. The "also check" gap is thus not a redaction hole for new data; it is the source of new oversize rows that redact will later refuse. The only ingest-side limits are the sanitizer's `_MAX_PASSES=8`, `_MAX_DEPTH=200`, `_MAX_NODES=10_000_000` (`pii.py`), none of which is a byte bound. `pii.redact_history_text` itself has no length bound.

## Root Cause

- **File**: `scripts/little_loops/session_store/raw_redaction.py`
- **Anchor**: `in function _plan_column()` (refusal at the `col.value is None` check), fed by `_projection()` / `_projection_sql()`
- **Cause**: `_projection(name: str, cap: int)` projects `typeof`, the blob length, and the value only inside a `CASE WHEN length(CAST({name} AS BLOB)) <= {int(cap)} THEN CAST({name} AS BLOB) END` with no `ELSE` branch, so a stored-oversize column arrives as `_Col.value is None` with only `_Col.length` populated. `_plan_column` cannot tell that from "unreadable" and calls `_refuse("resource_limit")` before `decode_payload()` or `sanitize_history_payload()` ever run. `_Run._handle` then adds the row id to `failed_ids`, and `_Run.report()` computes `complete` as false whenever `failed_ids` is non-empty. No code path removes an id from `failed_ids`, and the refusal depends only on stored size, so every rerun repeats it. `_Col.length` is populated but read by nothing in `raw_redaction.py`.

## Expected Behavior

Either every row is actually scanned, or the report clearly separates rows that were verified clean or redacted from rows that cannot be verified, names the reason, and tells the operator exactly what to do about each one.

## Proposed Direction (options, not prescriptive)

1. **Process oversized rows separately, one at a time**, outside the 8-row page. Fetch each one with `substr()`/blob chunks under its own byte budget, decode and scan it, and write it back in a single-row request. That keeps the page and wire bounds intact.
2. **Treat a refused row as verified when it can be decoded within an explicit, larger opt-in bound** (e.g. `--max-row-bytes`) and scans clean, so the run reaches `complete: true`.
3. **At minimum**, report `resource_limit` rows as a distinct `unverifiable_oversize` outcome with row ids and sizes and a concrete remedy (e.g. the opt-in flag, or `ll-session prune`/`compact` for the affected sessions), rather than "rerun".

**Also check:** does ingest-time sanitization (ENH-3751) apply the same size bound? If an incoming row over the cap is stored unsanitized rather than refused or sanitized in chunks, write-time redaction has the same gap for new data, and this issue's fix should cover both paths.

## Acceptance Criteria

- [ ] A store whose only refusals are oversized-but-clean rows can reach `complete: true` through a documented path (default or opt-in).
- [ ] An oversized row that does contain a match is redacted (or left as found and clearly reported as unverified), never silently counted as clean.
- [ ] The text and JSON reports tell an unresolvable size refusal apart from other failures, and give an actionable remedy instead of "rerun after resolving the above."
- [ ] Page and request byte bounds stay enforced (existing `TestWireBounds` still passes).
- [ ] Ingest-time behavior for payloads over the cap is confirmed and covered by a test; if it stores unsanitized data, that path is fixed too.
- [ ] Tests use a synthetic over-cap row (clean and dirty variants) and fail on the current code.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

**Option A**: Process oversized rows separately, one at a time, outside the 8-row page — fetch each under its own byte budget, decode and scan it, and write back through a single-row request (issue "Proposed Direction" item 1). Keeps page and wire bounds intact; needs a bounded fetch for a column the capped `_projection` returns as `NULL`, and a write guard that fits `REQUEST_BYTES_CAP`.
> **Selected:** Option A — keeps page/wire bounds untouched and reaches `complete: true` for clean oversize rows (no write needed); Option C's distinct outcome is the floor for rows beyond the per-row bound or dirty rows whose write guard cannot fit.
⚠ Unproven mechanism — no existing site reads blob chunks or decodes above DECODED_CAP

**Option B**: Decode refused rows within an explicit larger opt-in bound (e.g. `--max-row-bytes`) and report `complete: true` when they scan clean (item 2). Smaller change, but `_fetch_one` and `_fetch_page` share the capped projection, so the bound must reach `_projection` and the 8-row page worst case (8 × 2 × `STORED_CAP` = 16 MiB, pinned by `test_captured_page_response_under_32mib`) grows with it.

**Option C**: Report-only — emit a distinct `unverifiable_oversize`-style outcome with row ids and stored sizes and a remedy that holds on local and remote targets (item 3). Does not reach `complete: true`, so on its own it fails the first Acceptance Criterion; viable only as the report-side floor for rows still beyond any opt-in bound.

**Recommended**: Option A — with Option C's distinct outcome retained for rows that exceed the per-row bound, so a refusal is never silent and never reads as "rerun". Option B's flag can supply the per-row budget for A.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-10-06.

**Selected**: Option A (with Option C's `unverifiable_oversize` outcome as the report-side floor)

**Reasoning**: A clean oversize row needs only fetch, decode and scan — `_plan_column` already returns `(None, {})` for a clean column — so A reaches `complete: true` for the reported case (six clean rows) while leaving `PAGE_ROWS_MAX`, the 16 MiB page worst case and `TestWireBounds` untouched. B routes a larger bound through the `_projection_sql()` shared by `_fetch_page` and `_fetch_one`, growing the page worst case and the response bound pinned at 32 MiB. C scores highest on raw simplicity/risk but cannot satisfy the first Acceptance Criterion alone, so it is selected only as the floor for rows A cannot verify (beyond the per-row bound, or dirty rows whose full-bytes write guard exceeds `REQUEST_BYTES_CAP`).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option B | 2/3 | 1/3 | 1/3 | 1/3 | 5/12 |
| Option C | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 (fails AC1 standalone — not eligible as sole fix) |

**Key evidence**:
- Evidence on A — reuses `_fetch_one` (`raw_redaction.py:293`), single-statement `execute` and `_reconcile_one`'s single-row `UPDATE_SQL` path; `_Col.length` already detects and sizes oversize columns. Against: no `substr`/blob-chunk read or cap-parameterized `decode_payload` exists anywhere (`DECODED_CAP` at `:210-219`), remote reads materialize the whole base64 result (`libsql.py:124`), and `UPDATE_SQL`'s full-bytes guard costs ~4.4 MB on a 3.3 MB row. The unproven fetch/decode mechanism remains (`unproven_mechanism: true`); the dirty-row write-back is the real unknown.
- Evidence on B — `--batch`/`batch_size` is a clean flag-plumbing template (`cli/session.py:417`, `:586`), but the bound must reach `_projection_sql`, `decode_payload`, the `STORED_CAP` replacement check (`:391`) and `REQUEST_BYTES_CAP` (`:445`, `:725`), and `test_captured_page_response_under_32mib` has no dependency on the flag.
- Evidence on C — new reason code is a one-line vocabulary addition plus `TestVocabulary` edit; sizes need a field on frozen `RawRedactionProblem` (update `_redact_report` helper). No remote-valid remedy command exists — `prune`/`compact` are remote-refused and keyed on source path/age (`backend.py:97-104`).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Files to modify**: `scripts/little_loops/session_store/raw_redaction.py` (`_projection`, `_fetch_one`, `_plan_column`, `_plan_row`, `_Run._handle`, `_Run.report`, `RawRedactionProblem`, `RawRedactionReport`, `RAW_REDACTION_REASONS`, `redact_raw_events`); `scripts/little_loops/cli/session.py` (`_build_parser()` `redact_parser`, `_main_redact`, `_print_redact_report` at `:544`, `_REDACT_GUIDANCE`).
- **Importers of `raw_redaction`** (graph-confirmed): `session_store/__init__.py:141` (re-export, `__all__` at ~`:270`), `cli/session.py:81`, `scripts/tests/test_raw_redaction.py:30`. Other test consumers: `test_ll_session.py`, `test_remote_operation_matrix.py`, `test_wiring_reference_docs.py`.
- **Ingest sites (read-only check, currently no size bound)**: `session_store/lifecycle.py:854` (`_backfill_raw_events`) and `:1630` (`refresh_usage_source`); `session_store/usage_refresh.py:115` sanitizes on the refresh-compare path.
- **Remote write path**: `libsql.py` `LibsqlConnection.executemany` → `hrana.py` `HranaClient.execute_many` / `_post`; `_post` does `json.dumps({"baton": None, "requests": ...})` with no client-side size check. Reads materialize the whole result (`LibsqlCursor`), no streaming.
- **Docs that name redact flags/outputs**: `docs/reference/CLI.md` (examples block ~`:4799`, `**`redact` flags**` table ~`:4814`, `**Report fields**` ~`:4828`, exit codes ~`:4830`); `docs/reference/API.md` (`### Raw payload redaction: redact_raw_events (ENH-3752)`, ~`:10463-10518`, states the 1 MiB / 4 MiB bounds); `docs/guides/HISTORY_SESSION_GUIDE.md` (`## Scrubbing Stored Payloads`, ~`:703-719`, carries the user-facing "Rerun after resolving them" sentence). `test_wiring_reference_docs.py` `DOC_STRINGS_PRESENT` pins `"ll-session redact"`, `` "**`redact` flags**" ``, `"redact_raw_events"`, `"## Scrubbing Stored Payloads"` — keep those strings.
- **Mirror/spike copies**: `scripts/tests/spike/enh3752_raw_redaction/redaction_core.py` and its `TestWireBounds` duplicate (`PAYLOAD_CAP = 1 << 20`) are an earlier spike, not the shipped module.

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Remedy-wording constraints**: `ll-session prune` and `ll-session compact` (`lifecycle.py` `prune()` / `compact()`) are keyed on source path and age (`raw_event_max_age_days`, `min_project_age_days`, `min_db_size_mb` gates), never on payload size or row id, and both are in `backend.py` `_REMOTE_REFUSALS` so they fail on a remote store while `redact` supports one. `compact` never reads the payload column. A remedy naming them is therefore neither targeted nor universally available; any remedy text must hold on both local and remote targets.

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Tests**: `scripts/tests/test_raw_redaction.py` — `TestWireBounds` (`:197`; must keep passing), `TestVocabulary` (`:104`, pins the reason set), `TestRowFailures.test_unsupported_storage_and_resource_limit` (`:449`, builds its over-cap row with `zeroblob(STORED_CAP + 1)` — all zeros, not valid zlib/JSON, and asserts `resource_limit` for `(1, "parsed_json")` and `report.failed == 2`; this existing contract changes or is narrowed by the fix), `TestBoundedDecode.test_decoded_cap_boundary`. `scripts/tests/test_ll_session.py::TestRedactSubcommand` pins the `redact_raw_events` call kwargs exactly (`{"batch_size": 7, "dry_run": True}`), so a new keyword threaded from the CLI must update those assertions. No test asserts on `Incomplete:` / `Failed:` text, and none builds a valid over-cap payload (clean or dirty) — the synthetic rows the acceptance criteria call for do not exist yet. `scripts/tests/test_enh3751_sanitize_raw_events.py` has no over-cap ingest case.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/session.py` — calls `redact_raw_events(args.db, batch_size=args.batch, dry_run=args.dry_run)` and formats the report, in `_main_redact()`; sole runtime consumer of `RawRedactionReport` (`print_json(asdict(report))`, so any new report/problem field appears in `--json` automatically) [Agent 1, 2 finding]
- `scripts/little_loops/session_store/raw_redaction.py` — `_Run._reconcile_one()` is the only caller of `_fetch_one()` and `_plan_row()` is the only caller of `_plan_column()`/`_update_params()`; `decode_payload()` is called only from `_plan_column()` (two sites), so parameterizing its cap touches no other module [Agent 1 finding; graph-confirmed]
- `scripts/little_loops/session_store/raw_redaction.py` — `_state()`/`_desired_state()`/`_classify()` compare `_Col.value`; two over-cap columns both carry `value is None`, so they compare equal. Any oversize path that leaves `value` as `None` must not let reconcile read an unchanged oversize column as "converged" [Agent 2 finding, in `_classify()`]
- `scripts/little_loops/session_store/raw_redaction.py` — `_update_params()` binds `obs.raw.value`/`obs.parsed.value` as the full-bytes guard and asserts `obs.host.value is not None`; a column with `value is None` (over cap) has no bytes to bind, so the dirty-oversize write guard cannot reuse it unchanged [Agent 2 finding, in `_update_params()`]
- `scripts/little_loops/session_store/writers.py` — `_unpack_payload()` does an unbounded `zlib.decompress`; the only other `decompressobj` user is `decode_payload()`. The new bounded oversize decode must not route through `_unpack_payload` (would bypass the zlib-bomb bound) [Agent 1 finding, in `_unpack_payload()`]
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events()` and `refresh_usage_source()` apply no byte cap (sanitize then `_pack_payload`); these are the source of new oversize rows. Read-only for this issue, relevant only to the ingest-pinning test [Agent 1, 3 finding]
- `scripts/little_loops/session_store/__init__.py` — re-exports only `redact_raw_events`, `RawRedactionProblem`, `RawRedactionReport`; a new reason code or size field needs **no** edit here (`RAW_REDACTION_REASONS`, caps and `decode_payload` are not re-exported) [Agent 2 finding]
- No loop YAML, hook, skill, command or plugin manifest runs `ll-session redact` or parses its `complete`/`problems`/`failed` fields or exit code (`.loops/.history/` hits are run logs, not gates); `init/writers.py` allowlists `Bash(ll-session:*)`, so a new flag needs no permission change [Agent 1, 2 finding]

### Files to Modify (additional sites)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/session_store/raw_redaction.py` — `_Run._handle()` and `_Run._enqueue()` both compare `_estimate_request_bytes(...)` to `REQUEST_BYTES_CAP`; `_plan_row()` returns `None` keyed `(None, "resource_limit")` on the same overflow. These are the dirty-oversize write-guard touchpoints for the Option C floor [Agent 1, 2 finding]
- `scripts/little_loops/session_store/raw_redaction.py` — `_Run._record()` enforces `PROBLEM_CAP`/`omitted_problems`; new size fields on `RawRedactionProblem` must carry integers only (`test_no_content_in_problems` and the `asdict(report)` token-leak assertions forbid content) and need **default values** so the 3-arg `RawRedactionProblem(1, "raw_line", "invalid_json")` equality in `test_failures_advance_progress_and_leave_rows_unchanged` keeps holding [Agent 2, 3 finding]
- `scripts/little_loops/session_store/raw_redaction.py` — module docstring "Safety model" bullets (lines 13-14: "bounded-BLOB so no oversized … value is ever decoded", "hard byte/decompression caps"), the `DECODED_CAP` comment ("zlib-bomb ceiling") and the `PAGE_ROWS_MAX` comment ("8 rows x 2 columns x STORED_CAP = 16 MiB") encode the current invariant and must be restated for the oversize path [Agent 2 finding, in the module docstring]
- `unverifiable_oversize` must live **outside** `pii.HISTORY_ERROR_REASONS` (pinned as an exact tuple in `scripts/tests/test_pii.py`); add it only to the `extra` part of `RAW_REDACTION_REASONS` [Agent 2 finding]
- `scripts/little_loops/cli/session.py` — `_build_parser()` epilog "Examples" block and the module docstring command list name `redact` and need updating if a flag is added; the `--batch` help text ("internal byte bounds still apply") is the template for any new flag, and `_positive_int` is the existing validator for a `>= 1` integer flag [Agent 1, 2 finding]
- `scripts/little_loops/cli/session.py` — per-row reasons such as `resource_limit` never pass through `_REDACT_GUIDANCE` (it is keyed only on pre-snapshot `RawRedactionError` reasons: `target_unavailable`, `schema_mismatch`, `backend_failure`, `interrupted`); the oversize remedy text belongs in `_print_redact_report()`, not `_REDACT_GUIDANCE` [Agent 2 finding]
- Conditional (Option C floor, rows beyond the per-row bound / dirty rows whose guard cannot fit): the `unverifiable_oversize` path adds a new `RawRedactionProblem` outcome that must feed `failed_ids` (or change the `complete` expression in `_Run.report()`) to keep the exit code at 1; if it is also made a stop reason, `RAW_REDACTION_STOP_REASONS` and its pinned 6-name set in `TestVocabulary` change too [Agent 1, 2 finding]
- Open question carried from decision `60424792-…json`: it records `--max-row-bytes` (Option B) as **rejected**, while this issue's Recommended line and Program Design still allow it as A's per-row budget. The `max_row_bytes` kwarg/CLI/test/doc touchpoints below apply only if the flag is kept [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md` — **`redact` flags** table (~`:4814`), **Report fields** paragraph (~`:4828`, states "`problems` (at most 100 entries of `row_id`, `column`, `reason`)") and the unfiltered-`complete` definition; update for any new problem field, the oversize outcome, and `--max-row-bytes` if kept. Keep the `test_wiring_reference_docs.py` needles (`ll-session redact`, `` **`redact` flags** ``) [Agent 2 finding, in `Report fields`]
- `docs/reference/API.md` — `### Raw payload redaction: redact_raw_events (ENH-3752)`: the signature block, the `RawRedactionProblem` field block (lists only `row_id`, `column`, `reason`), the `RawRedactionReport` field list (must mirror the dataclass) and the "Behavior" paragraph ("1 MiB stored and 4 MiB decoded per column, 8 MiB per remote write request") [Agent 2 finding, in `Behavior`]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — `## Scrubbing Stored Payloads`: the bullet "Conflicts are reported, not overwritten" ends "Rerun after resolving them." and says unvalidated rows are "counted under `failed`"; that wording is wrong for an oversize refusal. Keep the heading needle [Agent 2 finding, in `Scrubbing Stored Payloads`]
- `docs/reference/CONFIGURATION.md` — `history.backend` remote bullet list: "**Supported remotely.**" (pinned needle ``` `ll-session redact` scrubs stored raw payload ```) and the adjacent "**Not supported remotely.**" bullet (`prune`, `compact`, `recompress` refused) — the latter is why the oversize remedy text cannot name `prune`/`compact` [Agent 2 finding, in the `history.backend` bullet list]
- `CHANGELOG.md` — do not add under `[Unreleased]` (project rule); the `## [1.167.0] - 2026-10-06` section is already dated, so a BUG-3762 entry belongs in a new versioned section at release prep [Agent 2 finding]
- No hits in `README.md`, `scripts/README.md`, `CONTRIBUTING.md`, `.claude/CLAUDE.md`, `docs/ARCHITECTURE.md`, `commands/`, `skills/`, `hooks/` or host-adapter mirrors, so `ll-adapt` / README mirror gates do not apply [Agent 1, 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_raw_redaction.py` — `TestVocabulary.test_reasons_extend_sanitizer_codes_and_are_closed` (`:105`) hard-codes the 13-name `extra` set and the 6-name `RAW_REDACTION_STOP_REASONS`; add `unverifiable_oversize` to the right set [Agent 3 finding]
- `scripts/tests/test_raw_redaction.py` — `TestRowFailures.test_unsupported_storage_and_resource_limit` (`:449`) will break: `zeroblob(STORED_CAP + 1)` is not a zlib stream, so a bounded fetch likely yields `invalid_compression` or the new outcome, and `report.failed == 2` may change. Narrow or rewrite it [Agent 2, 3 finding]
- `scripts/tests/test_raw_redaction.py` — `TestRowFailures.test_failures_advance_progress_and_leave_rows_unchanged` (`:420`) pins `RawRedactionProblem(1, "raw_line", "invalid_json")` equality and `report.failed == 5`; breaks if a new size field has no default [Agent 2, 3 finding]
- `scripts/tests/test_raw_redaction.py` — `TestRemote.test_unknown_outcome_and_unreadable_reconcile_is_unconfirmed` (`:918`) monkeypatches `rr._fetch_one` with `lambda conn, row_id: ...`; breaks if `_fetch_one`'s signature or call shape changes. The `_fetch_page` monkeypatches (`fetch(conn, **kw)`, `spy(conn, **kw)`; kwargs `snapshot`, `last_id`, `limit`) tolerate added kwargs but not renames [Agent 2, 3 finding]
- `scripts/tests/test_raw_redaction.py` — `TestWireBounds.test_captured_page_response_under_32mib` (`:265`) reads `rows[0].raw.value`, uses `_fetch_page(conn, snapshot=8, last_id=None, limit=8)` and a `_Handler._reply` size spy; breaks if `_Col.value` is renamed or `_projection` changes shape. Reuse its spy to prove each single-row oversize fetch response stays bounded [Agent 3 finding]
- `scripts/tests/test_raw_redaction.py` — `TestBoundedDecode.test_decoded_cap_boundary` and its `_refusal(sql_type, data)` helper are the template for a cap-parameterized `decode_payload` test (cap+1 bomb under a larger cap) [Agent 3 finding]
- `scripts/tests/test_raw_redaction.py` — **new tests**, following `TestLocalScrub` with the `blob()` / `payload()` / `Db.insert()` helpers (no valid over-cap row exists today; build one from incompressible base64 noise and assert the premise `STORED_CAP < len(stored)` and `len(text) <= DECODED_CAP`): clean oversize blob row → `complete`; dirty oversize blob and TEXT row; dirty row whose replacement exceeds `STORED_CAP` (`_plan_column` `:391`, untested today); mixed page of normal + oversize rows with `batch_size=2` (`test_zero_negative_ids_and_holes` pattern); dry-run leaves bytes unchanged (`test_dry_run_changes_nothing_and_reports_plan` pattern); remote clean/dirty oversize via the `remote` fixture (`HranaStub`, `_rinsert`, `_rcell`, `stub.requests` body assertions as in `test_preview_sends_reads_only`) [Agent 3 finding]
- `scripts/tests/test_ll_session.py` — `TestRedactSubcommand.test_dispatch_passes_target_batch_and_dry_run` (`:1381`) pins `mock.call_args.kwargs == {"batch_size": 7, "dry_run": True}` exactly; pass `max_row_bytes` only when the flag is set, or update the assertion [Agent 2, 3 finding]
- `scripts/tests/test_ll_session.py` — `_redact_report()` (`:1312`) builds `RawRedactionReport(**base)` with all 19 fields and the dataclass is frozen with no defaults; add any new report field to `base`. `test_json_is_exactly_one_object` (`:1396`) reads `failed`/`complete`/`problems`; extend for new keys. `test_parsed_defaults_and_flags` and `test_invalid_batch_is_usage_error_exit_2` (parametrized `0, -1, x, 1.5`) are the templates for a new flag's parse/default/invalid-value tests [Agent 2, 3 finding]
- `scripts/tests/test_ll_session.py` — **new text-mode test** for the oversize outcome using the `capsys` + `_redact_report(...)` override pattern; no test asserts on `Incomplete:`, `left as found`, `see --json for codes` or `Failed:` today, so nothing breaks but nothing guards the new wording either. `test_end_to_end_preview_then_apply_without_telemetry` is the real-SQLite template for an end-to-end oversize case (also asserts `_cli_event_count() == 0`) [Agent 3 finding]
- `scripts/tests/test_enh3751_sanitize_raw_events.py` — **new ingest test** modelled on `test_local_ingest_sanitizes_both_columns_identically` (`ensure_db` + `backfill_raw_events` + `_columns(db)`) with a large incompressible record, asserting `len(raw) > STORED_CAP` and that both columns are sanitized and stored (pins "sanitized, not refused"); no over-cap ingest case exists [Agent 3 finding]
- `scripts/tests/test_remote_operation_matrix.py` — `TestRedactIsASupportedRemoteOperation` calls `redact_raw_events(dry_run=True)` / `redact_raw_events()` with no size kwargs; stays green unless the call signature changes [Agent 2, 3 finding]
- `scripts/tests/test_pii.py` — pins `HISTORY_ERROR_REASONS` as an exact tuple (~`:1064`); unaffected provided the new code stays out of it [Agent 2 finding]
- `scripts/tests/spike/enh3752_raw_redaction/` is independent (`test_guard_spike_does_not_import_production_raw_redaction`); not affected [Agent 3 finding]

## Program Design

### Types

- `RawRedactionProblem.reason: str` — gains an `unverifiable_oversize` outcome (distinct from `resource_limit`) carrying row id and stored/decoded sizes
- `max_row_bytes: int | None` — opt-in per-row decoded bound for oversized rows; `None` keeps the current `STORED_CAP`/`DECODED_CAP` behavior

### Signatures

- `redact_raw_events(db: Path | str | HistoryTarget = DEFAULT_DB_PATH, *, batch_size: int = 2000, dry_run: bool = False, max_row_bytes: int | None = None) -> RawRedactionReport`
- `_plan_column(col: _Col, host: str, event_type: str) -> tuple[bytes | None, dict[str, int]]` — oversized branch routes to the single-row path instead of refusing
- `_print_redact_report(report: RawRedactionReport) -> None` — names oversize rows and the remedy instead of "rerun"

### Call Path

`_main_redact` -> `redact_raw_events` -> `_plan_row` -> `_plan_column` -> `decode_payload`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Existing shapes to extend, not replace**: `_Col` already carries `sql_type`, `length` (true stored size) and `value` (`None` when over cap) — an over-cap column needs no new projection to be *detected* and sized. `RawRedactionProblem` is `@dataclass(frozen=True)` with `(row_id, column, reason)` and no size field; `RawRedactionReport` is frozen and `test_ll_session.py::_redact_report` constructs it with **every** field, so any added field must be added to that helper's base dict.
- **Reason vocabulary is a closed, test-pinned set**: `RAW_REDACTION_REASONS` is `(*HISTORY_ERROR_REASONS, ...extra)` and `TestVocabulary.test_reasons_extend_sanitizer_codes_and_are_closed` hard-codes the exact `extra` set. A new outcome code must be added to both; `_Tally.problem` does not enforce membership at runtime.
- **Guarded-write invariant**: `UPDATE_SQL` re-states `typeof` and `CAST(col AS BLOB) IS ?` for both payload columns, and `_update_params` binds the *full original bytes* of each. `_estimate_request_bytes` costs a blob at `4*ceil(n/3)+_ARG`, so a 3.3 MB stored column costs ~4.4 MB of guard alone before the replacement, against `REQUEST_BYTES_CAP = 8 << 20`. Any write-back of a dirty oversize row must keep an optimistic-concurrency guard that fits the request bound; the existing full-value guard does not scale to these rows. A **clean** oversize row needs no write at all (`_plan_column` returns `(None, {})`).
- **Replacement bound**: `_plan_column` refuses a redacted output over `STORED_CAP` (`resource_limit`), so a dirty oversize row's replacement is itself currently unwritable. Whether the bound for replacements moves with the opt-in is a decision the fix must make explicitly.
- **Decode bound**: `decode_payload` caps zlib output at `DECODED_CAP` via `decompressobj.decompress(data, DECODED_CAP + 1)`; the largest observed row (4.7 MB decoded) exceeds it, so scanning it needs a bound parameterized through `decode_payload` (currently a module constant).
- **Decision Rules**: N/A — no new decision logic beyond the size-bound comparison above; the literal values (`STORED_CAP=1<<20`, `DECODED_CAP=4<<20`, `REQUEST_BYTES_CAP=8<<20`, `PAGE_ROWS_MAX=8`, `PROBLEM_CAP=100`) are unchanged by this issue unless an opt-in bound is chosen.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

1. A refused oversize column is detected from `_Col.length` and is no longer reported as an undifferentiated `resource_limit`; the report separates oversize-unverified rows from rows that failed for other reasons — verified by a vocabulary/report test alongside `TestVocabulary`.
2. A synthetic over-cap row that decodes to valid JSON (clean variant, and a dirty variant containing `SECRET`) reaches the intended outcome: clean → `complete: true`; dirty → redacted, or left as found and reported as unverified, never counted clean — both tests fail on current `main`.
3. Page (`PAGE_ROWS_MAX`), response (32 MiB) and request (`REQUEST_BYTES_CAP`) bounds still hold with an oversize row present — `TestWireBounds` passes unchanged, plus a bound check for the oversize path.
4. Text mode names the oversize row ids/sizes and a remedy valid on local and remote targets, and the JSON `problems`/report fields carry the same distinction (`_redact_report` helper updated for any new field).
5. Ingest behavior over the cap is pinned by a test in `test_enh3751_sanitize_raw_events.py` (current behavior: sanitized and stored, not refused) and the CLI/API/guide docs state the bounds and the new path without breaking the `test_wiring_reference_docs.py` needles.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/session_store/raw_redaction.py` — give new `RawRedactionProblem` size fields default values and integer-only content; add `unverifiable_oversize` to the `extra` part of `RAW_REDACTION_REASONS` (never to `pii.HISTORY_ERROR_REASONS`); make the new outcome feed `failed_ids` so exit code and `complete` stay correct
- Update `scripts/little_loops/session_store/raw_redaction.py` — in `_classify()`/`_state()`/`_desired_state()`/`_update_params()`, handle `_Col.value is None` for oversize columns explicitly (no `None == None` convergence, no full-bytes guard bind from a value that was never fetched); keep the guard within `REQUEST_BYTES_CAP` or fall to the `unverifiable_oversize` floor
- Update `scripts/little_loops/session_store/raw_redaction.py` — restate the module docstring "Safety model", `DECODED_CAP` and `PAGE_ROWS_MAX` comments for the oversize path; do not route the bounded decode through `writers._unpack_payload` (unbounded)
- Update `scripts/little_loops/cli/session.py` — put the oversize remedy text in `_print_redact_report()` (not `_REDACT_GUIDANCE`), valid on local and remote targets; thread `max_row_bytes` from `redact_parser` through `_main_redact()` only when set (if the flag is kept — decision `60424792-…` rejected Option B); update the epilog "Examples" and module docstring
- Inject at `scripts/little_loops/cli/session.py:_main_redact()` — `redact_raw_events(args.db, batch_size=..., dry_run=...)`: pass `max_row_bytes` conditionally so `test_dispatch_passes_target_batch_and_dry_run` keeps its exact-kwargs contract
- Update `scripts/tests/test_raw_redaction.py` — `TestVocabulary` (`extra` + stop-reason sets), `test_unsupported_storage_and_resource_limit` (zero-blob row no longer a pure `resource_limit`), keep `_fetch_one` call shape compatible with the `lambda conn, row_id:` monkeypatch; add the new clean/dirty/TEXT/replacement-overflow/mixed-page/dry-run/remote oversize tests
- Update `scripts/tests/test_ll_session.py` — add new fields to `_redact_report()` `base`; extend `test_json_is_exactly_one_object`; add flag parse/default/invalid, text-mode and end-to-end oversize tests
- Update `scripts/tests/test_enh3751_sanitize_raw_events.py` — add the over-cap ingest test pinning "sanitized and stored, not refused"
- Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/CONFIGURATION.md` — report fields, flag table, bounds text, and replace the "Rerun after resolving them." wording; preserve the `test_wiring_reference_docs.py` needles
- Defer `CHANGELOG.md` to release prep (no `[Unreleased]` entry)

## Impact

- **Priority**: P3 - `ll-session redact` cannot report `complete: true` on affected stores, but only for stores with over-cap payload rows and no data is lost or leaked by the refusal
- **Effort**: Medium - reuses `_fetch_one` and the single-row write path; new work is bounded chunked fetch plus report changes and an ingest-time (ENH-3751) check
- **Risk**: Medium - touches redaction completeness; must keep `TestWireBounds` page/request bounds intact
- **Breaking Change**: No

## Status

**Open** | Created: 2026-10-06 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-10-07T00:59:39 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
- `/ll:decide-issue` - 2026-10-07T00:51:15 - `6b41f46f-0778-4eee-bd27-b06a454db20a.jsonl`
- `/ll:refine-issue` - 2026-10-07T00:47:16 - `707e2f6d-f91c-469f-87fe-53582d107779.jsonl`
- `/ll:format-issue` - 2026-10-06T23:51:15 - `a0ac9893-a394-4fc1-a6b5-800ff281d815.jsonl`
