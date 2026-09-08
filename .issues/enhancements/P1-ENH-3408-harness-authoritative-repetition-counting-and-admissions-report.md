---
id: ENH-3408
title: Count authoritative repetitions in harness pass-rate reporting + admissions
  tabulation
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
verify_verdict: VALID
parent: ENH-3397
labels:
- harness
- evaluation
- statistics
size: Large
confidence_score: 80
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
---

# ENH-3408: Count authoritative repetitions in harness pass-rate reporting + admissions tabulation

## Summary

Make ll-harness's pass-rate/abstention-rate reporting count authoritative repetitions
instead of raw attempt rows, and surface admission interventions in the run report. Third
of three issues decomposed from ENH-3397 — consumes the schema from ENH-3406 (landed
`b55eb2872`) and the writers/gate from ENH-3407 (landed `28e64617d`, a `b55eb2872`
descendant). This is the issue that
actually changes what `n` means in reported numbers — the anti-p-hacking guarantee
ENH-3397 exists to deliver doesn't hold until this issue lands, even though
ENH-3406/ENH-3407 build its plumbing.

## Parent Issue

Decomposed from ENH-3397.

## Design Decisions

### D1. "Authoritative" is exactly `superseded_by IS NULL` — no per-cell fan-out needed

An earlier `/ll:verify-issues` pass flagged a PROPOSAL_UNSOUND gap: `authoritative_attempt(db,
cell_key, repetition)` / `authoritative_attempts(db, cell_key)` are keyed by `cell_key`
(`json.dumps([runner, target, head_sha])`, `cli/harness.py::_cell_key`), while all three
counting sites aggregate by `target` across many `cell_key`s, and no target→cell_keys
enumeration helper exists. **Resolved: the fan-out is unnecessary.** The write path makes
the authoritative set equal to the single SQL predicate `superseded_by IS NULL`:

- `session_store/writers.py::_admit_retry` updates `superseded_by` only `WHERE superseded_by
  IS NULL` and raises on `rowcount == 0`, and `cli/harness.py::_retry_refusal` refuses
  `--retry-of` against an already-superseded row. Retry chains are therefore linear and
  exactly one non-superseded row survives per `(cell_key, repetition)`.
- `attempt_kind='repetition'` rows are unique per `(cell_key, repetition)` by
  `idx_harness_cell_repetition` (partial unique index, `schema.py:1377`), so two valid
  repetitions never share an index.
- Legacy pre-v49 rows (`cell_key`/`repetition`/`superseded_by` all NULL) satisfy the
  predicate and stay counted, which is correct — they were never superseded.

Consequently the per-repetition Python dedup inside `authoritative_attempts()` is a
defensive tie-break that never fires on data the current writers produce. This issue
consumes ENH-3407's **selection rule**, not necessarily its function: define one
module-level SQL fragment in `history_reader/harness.py` (e.g.
`_AUTHORITATIVE_PREDICATE = "superseded_by IS NULL"`), interpolate it into
`harness_eval_pass_rate()`'s and `harness_eval_abstention_rate()`'s `WHERE` clauses, reuse
it in `authoritative_attempt()`/`authoritative_attempts()`, and filter
`e.superseded_by is None` in `_read_target_history()`'s Python loop. This is the
`history_reader/usage.py::_WASTED_RUN_PREDICATE` single-source-of-truth pattern
(interpolated at lines 341/345 of `waste_attribution()`).

### D2. Superseded rows leave every denominator; the surviving attempt's verdict is reported

A row is either authoritative or superseded, never both. Superseded rows are always
timeouts (`_retry_refusal` admits a retry only when `prior.timed_out`), stored with
`semantic_passed = 0` and `semantic_verdict = NULL`. Today that means they inflate the
pass-rate denominator as failures while already being excluded from the abstention-rate
denominator (the asymmetry documented under Program Design → Call Path). After this
change they are excluded from both, so the two denominators converge on the same
population; their stored `semantic_passed = 0` is simply never read for rate purposes.

The reported verdict for a repetition is the **last link of its retry chain** — the only
row with `superseded_by IS NULL`. "Earliest non-superseded" in ENH-3397's wording
collapses to "the non-superseded row" under the current gate, because a graded attempt can
never be retried and therefore never superseded.

### D3. `cmd_dsl`'s in-memory `graded_total`/`graded_pass` are NOT converted

`/ll:verify-issues` was right: those counters are scoped to one CLI invocation's per-task
loop (`cli/harness.py:1198-1311`), one row per task file. A `--retry-of` chain is always
a separate invocation (and restricted to a single task file, line 1156), so there is no
cross-invocation duplication to dedup. Leave them alone; only the three DB-aggregate sites
change.

### D4. Admissions tabulation scope: the same population the pass rate counts

Constraints found in the current code:

- `cli/harness.py::_record_harness_event` returns `None`, so `cmd_dsl` never learns the
  attempt ids it wrote. `session_store/writers.py::record_attempt` already returns the new
  id — propagate it (`-> int | None`).
- For `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`, `_evaluate_and_report()` prints the
  report *before* `_record_harness_event()` writes the attempt and its admission, so "the
  run's own admission" cannot appear in that report without reordering.
- `session_store/queries.py::recent(db, kind="harness_admission")` is `SELECT * ... ORDER BY
  id DESC LIMIT ?` with no filter, so it cannot scope admissions to a run or target.
- Under today's CLI every admission has `reason='timeout'` (`_record_harness_event`
  hardcodes it) and a DSL invocation admits at most one attempt, so a per-invocation
  "count by reason" would only ever print `timeout×1`.

**Decision**: tabulate admissions over the population the pass rate counts.

- **Single-target commands**: `_read_target_history()` additionally counts
  `harness_admissions` rows whose `attempt_id` is among the target's rows in the
  `_HISTORY_WINDOW_DAYS` window, exposed as `history_admissions: {reason: count}` (omitted
  when empty). `_format_target_history_line()` renders it, e.g.
  `pass 80% (5 runs, 2 infra retries admitted: timeout×2)`; the dict already flows into
  `--output json` via `payload.update(target_history)` (line 868), so the JSON payload
  gains `history_admissions` for free.
- **`cmd_dsl`**: after the per-task loop, query admissions whose `attempt_id` is in the
  set of ids this invocation wrote, and append one non-empty-gated line onto the existing
  `lines` list (after the `if failures:` append, line 1352), e.g.
  `  admissions: 1 (timeout×1)`.
- **Data access**: one small reader in `history_reader/harness.py`, e.g.
  `admissions_by_reason(db, attempt_ids: Iterable[int]) -> dict[str, int]` (raw SQL with an
  `IN (...)` placeholder list; the `reason` column is CHECK-constrained to
  `timeout|host_crash|harness_error|network`, so the category set is closed). Re-export via
  `history_reader/__init__.py`. Nothing existing covers this shape.
- **Rendering**: no shared "render breakdown" helper exists (five bespoke call sites:
  `ctx_stats.py` `crossings`, `sprint/show.py::_print_composition`, `logs.py`
  `outcome_counts`, `issue_manager.py:2106-2118` "Most common corrections:",
  `cli/issues/clusters.py:134-135` `_cluster_header`). Use `key×count`, comma-joined,
  count-descending — the `crossings` shape — and don't add a shared helper.

### D5. No new minimum n

The existing `_HISTORY_MIN_SCORED = 3` display-suppression gate (`cli/harness.py:693`) is
unchanged and now applies to the authoritative count. Nothing else introduces a default or
minimum n (deferred to the n-run-redundancy follow-on).

## Files to Modify

- `scripts/little_loops/history_reader/harness.py` — add the shared authoritative
  predicate (D1); apply it in `harness_eval_pass_rate()` (line 210) and
  `harness_eval_abstention_rate()` (line 249); reuse it in `authoritative_attempt()`
  (148) / `authoritative_attempts()` (176); add `admissions_by_reason()` (D4). The
  `HarnessEvent` dataclass and `_HARNESS_EVENT_COLUMNS` already carry `id` plus the five
  v49 fields (lines 39-86, ENH-3407) — no change needed there.
- `scripts/little_loops/history_reader/__init__.py` — import, docstring, and `__all__`
  entries for the new reader (existing block: `harness_eval_abstention_rate`,
  `harness_eval_pass_rate`, `recent_harness_events` at lines 184-186; `__all__` 308-309,
  329).
- `scripts/little_loops/cli/harness.py`:
  - `_record_harness_event()` (196) returns the attempt id from `record_attempt()`.
  - `_read_target_history()` (696) filters `superseded_by is None` before computing
    `pass_scored`/`judged_scored`, and adds `history_admissions` (D4).
  - `_format_target_history_line()` (751) renders the admissions suffix.
  - `cmd_dsl()` (1134): collect ids from the two `_record_harness_event()` calls
    (1209, 1290); append the admissions line onto `lines` (1346-1353). `graded_total`/
    `graded_pass` untouched (D3).
- `docs/reference/CLI.md` (212-313) — `--output json` payload table: reword
  `history_pass_rate`/`history_pass_rate_runs` and `history_abstention_rate`/
  `history_judged_runs` (currently "...≥3 non-abstained prior runs...") to say
  authoritative attempts; add a `history_admissions` row; mention the DSL admissions line
  in the "Retrying a run (`--retry-of ID`, ENH-3407)" section just past line 313.
- `docs/guides/EVALUATION_GUIDE.md` — line 458 ("nothing reads `harness_events`
  from the CLI for pass-rate purposes"); the "Across runs" paragraph starting
  "`harness_eval_pass_rate` counts every row with a non-NULL `semantic_passed`"; the
  "Reading the Signal" → "A single run" prose describing `_HISTORY_MIN_SCORED` as "3 prior
  runs". The `DSL pass-rate: 12/14 ...` fenced example stays valid; optionally add the
  admissions line beneath it.
- `docs/reference/API.md` — in the "HarnessEvent / recent_harness_events /
  harness_eval_pass_rate" section: update the "Read-side API for `harness_events` rows..."
  paragraph and the `_HISTORY_MIN_SCORED` paragraph for the redefinition; document
  `admissions_by_reason()`; and backfill the `HarnessEvent` code block (~lines 8918-8936),
  which is already missing `target_content_hash`/`target_path`/`dirty` (ENH-141) as well
  as `id` and the five v49 fields — write the full current field list, don't append.

## Tests

Fixture convention in both target files: rows are built by direct calls to the real
writers, no mocks. `test_history_reader_harness.py::TestAuthoritativeAttempts` (line 173)
builds a retry chain with `record_attempt(db, cell_key=CELL, attempt_kind="repetition",
timed_out=True, ...)` then `record_attempt(..., attempt_kind="infra_retry",
retry_of=original_id, reason="timeout", ...)` — reuse that construction.
`test_cli_harness.py::TestReadTargetHistory` wraps `record_harness_event` in a class-local
`_seed(self, target, rows: list[dict])` helper; extend it (or add a sibling that calls
`record_attempt`) rather than inventing a new fixture shape. Line numbers below drift;
re-locate by test name.

- `scripts/tests/test_history_reader_harness.py::TestHarnessEventReaders` — add
  superseded-row cases to `test_harness_eval_pass_rate` (~56),
  `test_harness_eval_pass_rate_excludes_abstained_rows` (~79),
  `test_harness_eval_abstention_rate` (~102),
  `test_harness_eval_abstention_rate_does_not_match_unrelated_verdict` (~126). Confirm
  `test_harness_eval_pass_rate_none_when_all_unscored`, `..._none_when_no_rows`, and
  `test_harness_eval_abstention_rate_none_when_no_rows` still return `None` (they should,
  unchanged).
- `scripts/tests/test_cli_harness.py::TestReadTargetHistory` (~1977) —
  `test_at_threshold_renders`, `test_distinct_denominators_for_pass_and_abstention`
  (hand-count comment `# 3 non-abstained judged + 3 exit-only` and
  `history_pass_rate_runs == 6`), `test_window_excludes_old_rows`;
  `TestTargetHistoryRegression::test_current_run_excluded_from_reported_rate`
  (`history_judged_runs == 3`). These seed distinct single-attempt rows, so their numbers
  should not change — update only if the assertion shape changes.
- **New — retry-chain n-collapse** (AC #1/#2): seed one cell as timeout → infra retry
  that times out → infra retry that grades `semantic_passed=True`. Before this change the
  fixture yields n=3 with one pass; after, n=1 with the surviving attempt's pass.
  Separately, two clean repetitions of one cell yield n=2. Assert at the
  `harness_eval_pass_rate()` layer and through `_read_target_history()` (which also needs
  the `_HISTORY_MIN_SCORED` gate to see the collapsed count: three chains of one graded
  survivor each clear it; one chain of three rows does not).
- **New — admissions tabulation** (AC #3): `_read_target_history()` returns
  `history_admissions == {"timeout": 1}` for the chain fixture and omits the key with no
  admissions; `_format_target_history_line()` output contains `timeout×1`; `cmd_dsl` with
  `--retry-of` prints a line containing `admissions:` and omits it otherwise. Use substring
  assertions, matching `TestCmdDsl`'s style (`assert "pass-rate" in out`,
  `test_cli_harness.py:1115-1116`) and `test_sprint.py::test_show_composition_line`.
- **New — `admissions_by_reason()`** unit test: empty id list → `{}`; ids spanning two
  reasons (seed via `admit_retry()` directly, since the CLI path only ever writes
  `timeout`) → counts by reason.
- Unaffected (confirmed by `/ll:wire-issue`): every `TestCmdDsl` fixture (1070-1605) and
  `TestHarnessEventPersistence::test_dsl_batch_writes_aggregate_and_per_task_rows` use one
  attempt per task file; `test_below_threshold_returns_none` and `test_none_when_db_empty`
  seed only distinct single-attempt rows.

## Acceptance Criteria

1. `history_pass_rate_runs`, `history_judged_runs`, and the rates behind them count only
   rows with `superseded_by IS NULL`. Test: the retry-chain fixture yields a lower n after
   this change than before.
2. The reported verdict for a repetition is that of its surviving (non-superseded)
   attempt — the last link of the retry chain. Test: two clean repetitions of one cell
   contribute n=2; one timed-out attempt plus two infra retries (the last graded)
   contribute n=1 with the last retry's verdict.
3. The run report tabulates admissions (count, by reason) next to the pass rate whenever
   any admission belongs to the counted population: `history_admissions` in
   `_read_target_history()`'s dict, the `--output json` payload, and the target-history
   line; an `admissions:` line in `cmd_dsl`'s report. Omitted entirely when empty.
4. `cmd_dsl`'s `graded_total`/`graded_pass` are unchanged (D3).
5. No new default n or minimum n; `_HISTORY_MIN_SCORED` is unchanged and applies to the
   authoritative count.

## Scope Boundaries

- **In scope**: the shared authoritative predicate and its use in
  `harness_eval_pass_rate`/`harness_eval_abstention_rate`/`authoritative_attempt(s)`/
  `_read_target_history`; `admissions_by_reason()` reader; admissions rendering in the
  target-history line, JSON payload, and `cmd_dsl` report; `_record_harness_event()`
  returning the attempt id; test and doc updates listed above.
- **Out of scope**: `harness_events`/`harness_admissions` schema DDL (ENH-3406);
  `record_attempt`/`admit_retry`/`authoritative_attempt`/`--retry-of` semantics
  (ENH-3407) — this issue reuses their selection rule, it does not redefine it. Any
  default or minimum n. Non-`timeout` admission reasons from the CLI (the enum exists in
  the schema; only `timeout` is written today). The `ll-artifact dashboard` raw-row export
  (`session_store/queries.py::_EXPORT_TABLE_MAP["harness_event"]`) echoes rows, not
  rates, and needs no change.

## Program Design

### Types

No new dataclass. `HarnessEvent` (`history_reader/harness.py:39-77`) already carries
`id`, `cell_key`, `repetition`, `attempt_kind`, `continuations`, `superseded_by` (ENH-3407).
`admissions_by_reason()` returns a plain `dict[str, int]`; `history_admissions` is the same
dict inside `_read_target_history()`'s return value.

### Signatures

- `harness_eval_pass_rate(target, *, since=None, db=DEFAULT_DB_PATH) -> float | None`
  (`history_reader/harness.py:210`) — unchanged signature; `WHERE target = ? AND
  <predicate>`.
- `harness_eval_abstention_rate(target, *, since=None, db=DEFAULT_DB_PATH) -> dict | None`
  (249) — same.
- `admissions_by_reason(db: Path | str, attempt_ids: Iterable[int]) -> dict[str, int]` —
  new.
- `_record_harness_event(...) -> int | None` (`cli/harness.py:196`) — was `-> None`;
  returns `record_attempt()`'s id, or `None` when the suppressed best-effort write fails.
- `_read_target_history(target: str) -> dict | None` (696) — unchanged signature; dict may
  gain `history_admissions`.

### Call Path

`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` → `_evaluate_and_report()` (line 834 reads
history *before* the current run's write, so history excludes the current run) →
`_read_target_history()` → `recent_harness_events(target, since, limit=1000)` → filter
`superseded_by is None` → `pass_scored`/`judged_scored` → if ≥ `_HISTORY_MIN_SCORED`:
`harness_eval_pass_rate()` / `harness_eval_abstention_rate()` (each its own SQL aggregate,
now with the predicate) → `admissions_by_reason(db, [e.id for e in events])` →
`_format_target_history_line()` and `payload.update(target_history)` (868).

`cmd_dsl()` → per-task `_record_harness_event()` (1209/1290) returning ids → after the
loop, `admissions_by_reason(db, ids)` → conditional append onto `lines` (1346-1353) →
`print("\n".join(lines))`. `_update_aggregate()` and the `print()` stay after the
insertion point.

`_read_target_history()`'s `limit=1000` means it can under-count relative to the SQL
`COUNT()` for a target with more than 1000 events in the window — a pre-existing
divergence, unchanged here.

### Decision Rules

The only rule is D1's predicate. No new gate, threshold, or keyword list.

## Current Behavior

`harness_eval_pass_rate()`, `harness_eval_abstention_rate()`, and `_read_target_history()`
count raw `harness_events` rows. A cell retried after an infra timeout contributes one row
per attempt to the reported `n`, so an infra retry inflates the sample size instead of
replacing the attempt it superseded — and each superseded timeout row counts as a
*failure* in the pass rate. The run report has no visibility into admission
interventions. `authoritative_attempt`/`authoritative_attempts` have zero production
callers; no reader for `harness_admissions` exists.

## Expected Behavior

The three counting sites count only non-superseded rows: a cell with a timed-out attempt
plus two infra retries contributes `n=1`, using the surviving attempt's verdict. The
target-history line, JSON payload, and DSL report tabulate admissions (count, by reason)
whenever any exist for the counted population. This is the issue that makes ENH-3397's
anti-p-hacking guarantee actually hold in reported numbers.

## Impact

- **Priority**: P1 — this is what makes reported n sound; without it ENH-3406/ENH-3407
  have no observable effect on reported numbers.
- **Effort**: Medium — one predicate applied at three sites, one small reader, one
  returned id, two report renderers, tests and docs.
- **Risk**: Low-Medium — `history_pass_rate_runs` changes what it counts, which can shift
  previously reported n for targets with retry history. A superseded timeout row also
  stops counting as a failure, so historical pass rates for such targets go *up*.
- **Breaking Change**: No — read-side only; no rows are rewritten.

## Status

**Open** | Created: 2026-09-08 | Priority: P1 | Blockers: none (ENH-3406, ENH-3407 done)

## Verification Notes

_`/ll:verify-issues` — 2026-09-08:_ flagged (a) the target→cell_keys fan-out gap and
(b) the `cmd_dsl` counter claim. Both resolved by design review on 2026-09-08: (a) is a
non-problem, see D1; (b) accepted, see D3.

_Design review — 2026-09-08:_ additionally found that AC #2's original fixture ("one
graded attempt plus two infra retries ... earliest graded attempt's verdict") cannot occur
under `_retry_refusal`'s timeout-only gate, and that the admissions tabulation had no
defined scope and no way to obtain attempt ids. Rewritten as D2 and D4.

_`/ll:verify-issues` — 2026-09-08:_ re-checked every file/line/quote citation against
HEAD: all code-level citations (dataclass fields, function signatures,
`writers.py::_admit_retry`, `schema.py:1377`, `queries.py::recent`, the D2 timeout-only
retry gate) matched exactly; `ll-verify-evidence` found no fabricated quotes; no active
required decision rules. Found and corrected two stale citations in this pass: (1) the
Summary's commit attribution collapsed ENH-3406 and ENH-3407 onto one commit — split into
their actual commits (`b55eb2872` schema, `28e64617d` writers/gate); (2) the
`docs/guides/EVALUATION_GUIDE.md` "nothing reads `harness_events`..." quote was cited at
lines 308/446 but now lives at line 458 — corrected in Files to Modify. Both fixed in
place; verdict **VALID** with corrections applied.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 63/100 → MODERATE

Both concerns raised (fan-out gap; `cmd_dsl` scope) are now resolved in Design Decisions
D1 and D3. Scores not yet re-run.

## Session Log
- `/ll:verify-issues` - 2026-09-08T23:13:18 - `6838caf5-f9a1-4968-903c-7ebff6345cb2.jsonl`
- `/ll:confidence-check` - 2026-09-08T22:55:59 - `b8f1a5da-c225-4249-91e2-295287d87d5e.jsonl`
- `/ll:verify-issues` - 2026-09-08T22:43:56 - `de8d5d84-5a41-428b-835e-669b7afc984e.jsonl`
- `/ll:wire-issue` - 2026-09-08T22:19:01 - `d465057a-e29b-4c19-8620-0af7f2ad1788.jsonl`
- `/ll:refine-issue` - 2026-09-08T22:04:46 - `35eb0ad3-e497-496d-b193-1dad8fa5f0e6.jsonl`
- `/ll:confidence-check` - 2026-09-08T19:15:36 - `3dfd0114-2334-4e08-9e14-e44fec8303b9.jsonl`
- `/ll:format-issue` - 2026-09-08T18:36:35 - `204483fb-0035-4a22-9571-7e0656ebef10.jsonl`
- `/ll:verify-issues` - 2026-09-08T17:09:42 - `3b8d2d10-26d6-4407-8c50-28fe3b34bf14.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T17:05:29 - `bd30e086-08dc-4823-aa37-f5118816aece.jsonl`
- `/ll:verify-issues` - 2026-09-08T16:57:01 - `ca004fd7-16f8-4917-8714-ea9456f5383b.jsonl`
- `/ll:wire-issue` - 2026-09-08T16:52:50 - `840e5cd3-969c-4a9b-8f06-5c2b03b57a03.jsonl`
- `/ll:refine-issue` - 2026-09-08T16:41:46 - `32a13f82-52a5-4a4d-99b8-67b2074972cb.jsonl`
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`
