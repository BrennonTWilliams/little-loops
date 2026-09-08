---
id: ENH-3407
title: record_attempt/admit_retry/authoritative_attempt writers + --retry-of CLI gate
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
verify_verdict: NON_VALID
reconcile_attempted: true
decision_needed: false
parent: ENH-3397
blocked_by:
- ENH-3406
labels:
- harness
- evaluation
- statistics
size: Large
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3407: record_attempt/admit_retry/authoritative_attempt writers + --retry-of CLI gate

## Summary

Implement the write path for ll-harness's run model: `record_attempt()`/
`admit_retry()`/`authoritative_attempt()`, and thread a new `--retry-of` CLI flag through
ll-harness's evaluators (`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/`cmd_dsl`) with the
admissibility gate and refusal behavior. Second of three issues decomposed from ENH-3397 —
depends on the schema/table from ENH-3406 (landed). This issue's `--retry-of` flag is fully
functional and records correct data, but existing pass-rate calculations do not yet reflect
it (that's ENH-3408).

## Parent Issue

Decomposed from ENH-3397.

## Design Decisions

### Cell identity (`cell_key` canonical encoding — owned by this issue per ENH-3406)

- `cell_key` is a JSON array string, `json.dumps([runner, target, head_sha],
  separators=(",", ":"))`, where:
  - `runner` is the value written to `harness_events.runner` (`"skill"`, `"cmd"`, `"mcp"`,
    `"prompt"`, `"dsl-task"`);
  - `target` is the value written to `harness_events.target` — `args.target` for the four
    single-runner commands, `task_file.name` for `dsl-task` rows (`cli/harness.py:1029,1100`).
    The parent's `task` component is folded into `target`: for DSL it *is* the task file name,
    for single runners there is no separate task;
  - `head_sha` is `_git_output("rev-parse", "HEAD")`, JSON `null` when git is unavailable.
    **Read it once, before `run_action()`, and pass the same value to both `_cell_key()`
    and the row's `head_sha` column.** Today every handler reads `head_sha` post-run inside
    `_record_harness_event()` (`cli/harness.py:154`); skill runs such as `commit` or
    `manage-issue` move HEAD, so a post-run read would disagree with the pre-run key. The
    pre-run sha is the subject under test.
  - `subject = runner + head_sha` per the parent. `dirty` is **not** part of the key (parent
    decision: subject is runner label + head sha); a dirty-tree sample shares its cell with a
    clean sample at the same sha. Readers can still filter on the existing `dirty` column, and
    `target_content_hash` pins the target file. Document this limitation in the docstring.
  - **DSL cell collision (document, do not fix):** `dsl-task` rows use `task_file.name`, so
    two directories holding a same-named task file share one cell. This matches how
    `_read_target_history()` already keys target history; note it in `_cell_key()`'s
    docstring next to the `dirty` limitation.
- JSON-array encoding is chosen over a delimiter because `cmd` targets are arbitrary shell
  strings (spaces, `|`, `:`, quotes) — no single delimiter is safe. It is deterministic,
  stdlib-only, and greppable in sqlite.
- The DSL aggregate/parent row (`cli/harness.py:1003`, `runner="dsl"`) gets `cell_key = NULL`
  and no `attempt_kind`; it is never a cell. Malformed-task rows (`:1028`, `exit_code=1`,
  `timed_out=False`) are ordinary graded `repetition` rows.
- Document the full encoding in `record_attempt()`'s docstring (ENH-3406 follow-up).

### Writer shape

- **Extend `record_harness_event()` rather than adding a parallel INSERT.** Today every
  evaluator writes exactly one `harness_events` row via `_record_harness_event()`
  (`cli/harness.py:124`), and `record_harness_event()` (`writers.py:1024`) has no
  `cell_key`/`repetition`/`attempt_kind`/`continuations`/`superseded_by` kwargs. A separate
  `record_attempt` INSERT would produce two rows per run. So:
  - `record_harness_event()` gains the five nullable kwargs (all default `None`, existing
    callers unchanged) and **returns `cursor.lastrowid` (`int`)** instead of `None`. No
    existing caller reads the return value, so this is backward compatible. This also removes
    `cmd_dsl`'s racy aggregate-id recovery (`SELECT id FROM harness_events ORDER BY id DESC
    LIMIT 1`, `cli/harness.py:1016`) — replace it with the returned id.
  - `record_attempt(db_path, *, cell_key, attempt_kind, retry_of=None, reason=None,
    continuations=None, **event_fields) -> int` allocates the repetition index and performs
    the INSERT. For `attempt_kind="repetition"`: `repetition = COALESCE(MAX(repetition), -1)
    + 1 WHERE cell_key = ?` (0-based). For `attempt_kind="infra_retry"`: `retry_of` and
    `reason` are required and `repetition` is copied from that row.
  - **Allocation runs under `BEGIN IMMEDIATE`, not a retry loop.** Python's legacy
    transaction mode opens no transaction for the `MAX` SELECT, so a read-then-INSERT race
    between two processes is real. `BEGIN IMMEDIATE` takes the write lock before the read;
    a competing allocator blocks on the existing `busy_timeout`
    (`schema.py::_configure_connection`) and then sees the committed row. This removes the
    `idx_harness_cell_repetition` collision entirely — no bounded-retry loop, no monkeypatch
    test. Precedent: `schema.py:1444,1491` (manual `BEGIN IMMEDIATE` control). A residual
    `IntegrityError` is therefore a genuine bug and should propagate.
  - Because the INSERT must sit inside that transaction, `record_attempt` cannot delegate
    to `record_harness_event()`'s own connect/commit. Factor the INSERT + `_index()` body
    into a private `_insert_harness_event(conn, ...) -> int` that both public writers call;
    `record_harness_event()` keeps its public shape and gains the `int` return.
  - **The retry write is one transaction.** When `retry_of` is set, `record_attempt`
    performs, on the same connection, after the INSERT: `UPDATE harness_events SET
    superseded_by = ? WHERE id = ? AND superseded_by IS NULL` (raise if 0 rows affected — a
    concurrent admission won) then `INSERT INTO harness_admissions(ts, attempt_id,
    superseded_id, reason)`, and commits once. A failure at any step rolls back the new row,
    the supersede, and the admission together — no orphan `infra_retry` row with
    `superseded_by IS NULL` can be left behind for ENH-3408 to reason about. The CLI makes
    **one** writer call on the retry path.
  - `continuations` is accepted as a kwarg and written through but never populated by any
    caller in this issue (ENH-3406 follow-up: column is reserved).
- `admit_retry(db_path, *, attempt_id, superseded_id, reason) -> None` is the public
  standalone form of that supersede + admission step, for callers that already hold a
  recorded attempt id. It shares a private `_admit_retry(conn, ...)` helper with
  `record_attempt` and commits in one transaction. An UPDATE on `harness_events` is
  permitted; only `harness_admissions` is append-only.
- **`authoritative_attempt` lives on the read side, not in `writers.py`.** No `writers.py`
  function returns a dataclass today; the row-dataclass convention (`HarnessEvent`,
  `history_reader/harness.py:36-63`, via `_row_to_dataclass`) is entirely in
  `history_reader/`. Add to `history_reader/harness.py`:
  - `harness_event_by_id(db_path, attempt_id) -> HarnessEvent | None` — used by the
    `--retry-of` gate;
  - `authoritative_attempt(db_path, cell_key, repetition) -> HarnessEvent | None` — the
    earliest row (`ORDER BY id`) for that `(cell_key, repetition)` with `superseded_by IS
    NULL`;
  - `authoritative_attempts(db_path, cell_key) -> list[HarnessEvent]` — one per repetition
    index, the set ENH-3408 counts as n.
  - **Clarification of the parent's rule.** "The earliest attempt where `superseded_by IS
    NULL` is authoritative" is per *repetition*, not per cell: a cell with three clean
    repetitions has three authoritative rows. A single-row `authoritative_attempt(cell_key)`
    as the parent sketched cannot feed ENH-3408's counting.
  - This pulls the "add `cell_key`/`repetition`/`attempt_kind`/`continuations`/`superseded_by`
    to `HarnessEvent` and `_HARNESS_EVENT_COLUMNS`" step into this issue (ENH-3408 currently
    lists it as its own "hard blocker, do first"; update ENH-3408 to consume it instead).
  - **`HarnessEvent` also needs `id`.** The dataclass has no `id` field and
    `_HARNESS_EVENT_COLUMNS` (`history_reader/harness.py:66-71`) does not select it, yet
    the gate needs `prior.id` for `retry_of`, `superseded_id`, and every refusal message.
    Add `id: int | None = None` as a **trailing default field** (existing positional
    construction in tests keeps working) and prepend `id` to `_HARNESS_EVENT_COLUMNS`. Six
    new fields total, not five.
- No Python-side enum validation on `attempt_kind`/`reason`; the CHECK constraints landed by
  ENH-3406 (`schema.py:1372-1373,1384`) enforce the closed sets. Both CHECK and no-CHECK
  enum columns are live precedent in `schema.py`; the new columns already have CHECKs.

### `--retry-of` admissibility gate and refusal

- Flag: `--retry-of ID` (`dest="retry_of"`, `type=int`, default `None`), declared once in
  `_add_evaluator_flags()` (`cli/harness.py:384`), so it lands on all five subparsers.
- **The gate runs before `run_action()`**, not at the `_evaluate_and_report()` call site —
  a refused retry must not spend a run. Sequence per `cmd_*`:
  1. Read `head_sha = _git_output("rev-parse", "HEAD")` once; compute this invocation's
     `cell_key` from it. Both are reused by the record step.
  2. If `retry_of` is set: `prior = harness_event_by_id(DEFAULT_DB_PATH, retry_of)`; apply
     the refusal rules below; on refusal print the message **to stderr** (so `--output json`
     consumers never receive a bare text line on stdout) and `return 1` without running.
     In `cmd_mcp` the gate sits **after** the existing `server:tool` and `--args` JSON
     validation, so a malformed invocation still exits 2 as today.
  3. Run the action and evaluate as today.
  4. Record, passing the pre-run `head_sha`: with `retry_of`, one call —
     `record_attempt(..., attempt_kind="infra_retry", retry_of=prior.id, reason="timeout",
     head_sha=head_sha, ...)` — which inserts, supersedes, and admits in one transaction.
     Without `retry_of`: `record_attempt(..., attempt_kind="repetition", head_sha=head_sha,
     ...)`, still wrapped in the best-effort `contextlib.suppress(Exception)` as today.
- **Refusal rules** (exit 1, message names the attempt id and the rule). Shape follows
  `cli/queue.py::cmd_requeue`/`cmd_remove` (`queue.py:686,321`, shared
  `_not_found_or_ambiguous()` at `:259`) — id lookup → persisted-state check → loud refusal —
  **without** their `--force` escape hatch (parent decision: no override).
  - `prior is None` — no such attempt.
  - `prior.cell_key is None` — pre-migration row or DSL aggregate row; not a cell.
  - `prior.superseded_by is not None` — already superseded by attempt N.
  - `prior.cell_key != current cell_key` — different runner, target, or head sha; the
    repetition index cannot be reused across cells. (Retrying after a commit is a new cell.)
  - `not prior.timed_out` — the prior attempt reached grading, or hit a runner error with no
    persisted signal (see Scope Boundaries, Option A). This is the "graded FAIL is rejected"
    case.
- **Reason is always `"timeout"` in this issue.** Under Option A the only admissible signal is
  the persisted `timed_out` column, so `host_crash`/`harness_error`/`network` are unreachable
  until a persisted error signal exists. Do not add a `--reason` flag.
- **Write failures on the retry path are not suppressed.** `_record_harness_event()` wraps
  the ordinary write in `contextlib.suppress(Exception)`; an admitted retry whose
  `harness_admissions` row silently failed to land defeats the audit purpose. When
  `retry_of` is set, let the `record_attempt` exception surface: print
  `error: retry of attempt N was not recorded: <exc>` to stderr and exit 1. Because the
  retry write is one transaction, a failure leaves the prior row un-superseded, no
  admission row, and no new `infra_retry` row.
- **`cmd_dsl`:** a DSL run writes one aggregate row plus N task rows, and `--retry-of` names
  one row. `--retry-of` on `dsl` is admissible only when `path` is a single task file and
  `prior.runner == "dsl-task"` with matching `cell_key` (which implies the same
  `task_file.name`); a directory `path` with `--retry-of` is refused with a message saying
  so. The retry's task row is recorded via `record_attempt` under a fresh aggregate row as
  usual. Note `cmd_dsl`'s PROMPT-kind tasks go through `_run_prompt_action()`
  (`cli/harness.py:927`, returns `tuple[RunnerResult, int]`) — an extra hop the other four
  handlers don't have; the gate is applied before that call.

### Signal-gap background (from parent + codebase research)

- `exit_code == 2` does not identify the error branch: `_run_skill` trace/stream sub-paths
  store `exit_code=124` on timeout (`runner_spec.py:194-201,218-219`); `_run_skill`
  default, `_run_cmd`, and `_run_prompt` store `2` for both timeout and runner error
  (`:234-237,341-346,261-263,287-290,390,392`); `_run_mcp` passes through `call_mcp_tool`'s
  codes (`mcp_call.py:155-161`) with neither `timed_out` nor `error` set; `run_action()`'s
  `scope_runner_error()` path (`runner_spec.py:402-417,420-441`, ENH-3403) returns
  `exit_code=2, error=...` before any runner. An ordinary graded `--exit-code 2` mismatch
  also stores `2`.
- Only `timed_out` is persisted (`schema.py:725`); `RunnerResult.error` (`runner_spec.py:78`)
  has no column. `_evaluate_and_report()` (`cli/harness.py:659`) reads both only for its
  early `return 2` and drops them from `HarnessEvalOutcome`.
- `cli/queue.py::_drain_once()` (`queue.py:483,492-496`) is a working precedent for reading
  `timed_out`/`error`/`exit_code` off a fresh `RunnerResult` — reference only.
- **Naming collision, not a coupling**: `superseded_by` also exists as an issue-frontmatter
  field (ENH-2829, `docs/reference/CLI.md:1475`). Different table, different domain; do not
  conflate when grepping.

## Files to Modify

- `scripts/little_loops/session_store/writers.py` — extend `record_harness_event()`
  (`:1024`) with `cell_key`/`repetition`/`attempt_kind`/`continuations`/`superseded_by`
  kwargs and an `int` return; factor its INSERT + `_index()` body into a private
  `_insert_harness_event(conn, ...)`; add `record_attempt()` (`BEGIN IMMEDIATE`
  allocation, single-transaction retry path) and `admit_retry()` sharing a private
  `_admit_retry(conn, ...)`.
- `scripts/little_loops/history_reader/harness.py` — add `id` (trailing default) plus the
  five v49 columns to `HarnessEvent` and `_HARNESS_EVENT_COLUMNS` (`_row_to_dataclass()`
  in `history_reader/_base.py:87-91` silently drops unmapped columns, so this is required,
  not optional); add `harness_event_by_id()`, `authoritative_attempt()`,
  `authoritative_attempts()`.
- `scripts/little_loops/session_store/__init__.py` — export `record_attempt`/`admit_retry`
  mirroring `record_harness_event` (docstring line 54, import block line 147, `__all__` line
  234). The import block is alphabetical; `__all__` and the docstring's Public API list are
  in feature-landing order — append there, do not alphabetize.
- `scripts/little_loops/history_reader/__init__.py` — export the three new readers, following
  however `recent_harness_events` is exported.
- `scripts/little_loops/cli/harness.py` — `--retry-of` in `_add_evaluator_flags()` (`:384`);
  pre-run `head_sha` read + gate + `record_attempt` in `cmd_skill` (~835), `cmd_cmd`
  (~868), `cmd_mcp` (~911), `cmd_prompt` (~952), `cmd_dsl` (~1072); replace the
  aggregate-id `SELECT ... ORDER BY id DESC` (`:1016`) with `record_harness_event()`'s
  return value; a small `_cell_key(runner, target, head_sha)` helper next to
  `_record_harness_event()`, which itself gains a `head_sha` kwarg so the post-run
  `_git_output("rev-parse", "HEAD")` at `:154` is dropped in favour of the pre-run value.
  Read `getattr(args, "retry_of", None)` at the gate (the `--issue-id` precedent, `:720`),
  so `_make_namespace()`-built tests keep working.
- `docs/reference/CLI.md:212-313` — add `--retry-of` to the shared-evaluator-flags table
  (226-234); document the refusal rules and exit code.
- `docs/reference/API.md` — `### record_attempt` / `### admit_retry` after
  `### record_harness_event` (`API.md:9544-9569`); note the `int` return; add the three
  `history_reader.harness` readers to that module's section.
- `docs/guides/EVALUATION_GUIDE.md:73-75,116-119` — add `--retry-of` to the shared flags
  list; reconcile the exit-code table's "`2` ... per-task infra error" prose with the
  timeout-only admissibility.
- `docs/reference/EVENT-SCHEMA.md:1795` — same reconciliation for the `RunnerResult.exit_code`
  sentence.

### Dependent Files (awareness only, no change)

- `scripts/little_loops/history_reader/harness.py::recent_harness_events()`/
  `harness_eval_pass_rate()`/`harness_eval_abstention_rate()` — still unfiltered on
  `attempt_kind`/`superseded_by`; counting fix is ENH-3408.
- `scripts/little_loops/session_store/queries.py:104` — `_EXPORT_TABLE_MAP["harness_event"]`
  echoes raw rows into `ll-history export`; new columns appear unfiltered.
- `scripts/little_loops/observability/schema.py:730-735` (`HarnessEventVariant`) — DES
  variant registry. The audit walker only detects `emit(...)` call sites, so plain SQL
  writers won't trip it; adding sibling variants is optional.

## Tests

- `scripts/tests/test_session_store_writers.py`:
  - `record_harness_event()` returns the inserted id; existing callers passing no new kwargs
    produce the old row shape (new columns NULL).
  - `record_attempt()` allocates 0, 1, 2 for three fresh repetitions of one cell; a second
    cell starts at 0; `infra_retry` with `retry_of` copies the prior's repetition.
  - `record_attempt()` serialises allocation: two `record_attempt` calls for one cell from
    two threads on separate connections get indices 0 and 1 with no `IntegrityError`
    (the second blocks on the write lock, then reads the committed `MAX`).
  - `record_attempt(attempt_kind="infra_retry", retry_of=N, reason="timeout")` inserts the
    new row, sets `superseded_by` on N, and appends one `harness_admissions` row, all
    committed together; when the admission INSERT fails (e.g. invalid `reason`, CHECK), the
    new row is **not** present and N is still un-superseded (rollback).
  - `admit_retry()` sets `superseded_by` and appends one `harness_admissions` row in one
    transaction; a second `admit_retry` against an already-superseded id raises and writes
    no admission row; an invalid `reason` raises `IntegrityError` (CHECK).
  - **No UPDATE/DELETE against `harness_admissions`**: parse `writers.py` with `ast`, walk
    `ast.Call` nodes, collect string-constant arguments containing `harness_admissions`, and
    assert none starts with `UPDATE`/`DELETE`. Scoped to that table on purpose:
    `record_orchestration_run` (`writers.py:1365`) and `record_learning_test_event`
    (`:1658,1665`) legitimately UPDATE/DELETE other tables, so a blanket substring check
    fails. This combines `test_sprint.py:3158-3182`'s `ast.walk()` call filtering with
    `test_git_operations.py:306-320`'s source-inspection intent (`TestSnapshotAndPreserve::
    test_no_code_path_invokes_git_stash`, itself a plain substring check); it is a direct copy
    of neither.
- `scripts/tests/test_history_reader_harness.py` — `harness_event_by_id`; `authoritative_
  attempt(cell, rep)` returns the non-superseded row of a timeout→retry chain;
  `authoritative_attempts(cell)` returns one row per repetition and excludes superseded rows;
  `HarnessEvent` carries `id` and the five new fields.
- `scripts/tests/test_cli_harness.py`:
  - refusal, each with `result == 1`, no `run_action` call (mock asserts not called), and a
    message naming the attempt id **on stderr** (stdout empty, so `--output json` stays
    parseable): unknown id; `cell_key IS NULL` row; already-superseded row; cell-key
    mismatch (different `head_sha`); graded FAIL (`timed_out=0`).
  - accepted: prior `timed_out=1` → new row `attempt_kind='infra_retry'`, same `repetition`,
    prior's `superseded_by == new id`, one `harness_admissions` row with `reason='timeout'`.
  - `record_attempt` failure on the retry path exits 1 with the "was not recorded" message
    (not suppressed) and leaves no new row.
  - `head_sha` consistency: patch `subprocess.run` so `git rev-parse HEAD` returns sha A
    before the run and sha B after; the recorded row's `head_sha` is A and equals the sha
    inside its `cell_key`.
  - `cmd_mcp` with `--retry-of` and a malformed `--args` still exits 2 (validation precedes
    the gate).
  - `cmd_dsl`: `--retry-of` with a directory `path` is refused; with a single task file and a
    matching `dsl-task` prior it is accepted.
  - `_make_namespace()` (`test_cli_harness.py:48-61`) has no `retry_of` key; the gate reads
    `getattr(args, "retry_of", None)`, so no default needs adding (matches `--issue-id`).
- `scripts/tests/test_cli_e2e.py::TestLlHarnessE2E` (`:472-489`) — one `--retry-of` e2e case
  next to `test_cmd_echo_hello_passes`.
- Verify unmodified: `scripts/tests/test_ll_session.py:1345-1362`,
  `scripts/tests/test_ll_logs.py:4677-4771`, `scripts/tests/test_create_eval_from_issues.py`
  (`TestFixtureToHarnessArgv`/`TestExportThenReplay`) — `_parse_harness_args` round-trips;
  `scripts/tests/test_runner_spec.py:94-152,240` — `RunnerResult` shape unchanged;
  `scripts/tests/test_session_store_schema.py:3061` (`TestPackageReexportSurface`) — fails
  loudly if a new `__all__` name lacks its import.

## Implementation Steps

1. `history_reader/harness.py`: add `id` (trailing default) and the five fields to
   `HarnessEvent` + `_HARNESS_EVENT_COLUMNS`; add `harness_event_by_id`,
   `authoritative_attempt`, `authoritative_attempts`; tests.
2. `writers.py`: factor `_insert_harness_event(conn, ...)` out of `record_harness_event`
   (kwargs + `int` return); add `record_attempt` (`BEGIN IMMEDIATE` allocation,
   single-transaction retry path via `_admit_retry(conn, ...)`, docstring with the
   `cell_key` encoding) and `admit_retry`; exports; tests including the
   `harness_admissions` AST check.
3. `cli/harness.py`: `_cell_key()` helper; every `cmd_*` reads `head_sha` once pre-run,
   computes `cell_key`, and writes via `record_attempt(attempt_kind="repetition",
   head_sha=...)`; `cmd_dsl` uses the returned aggregate id.
4. `cli/harness.py`: `--retry-of` flag; pre-run gate with the refusal rules; retry write path
   with unsuppressed failures; DSL single-file constraint; tests + e2e.
5. Docs: `CLI.md`, `API.md`, `EVALUATION_GUIDE.md`, `EVENT-SCHEMA.md`.
6. Update ENH-3408's "hard blocker, do first" (`HarnessEvent` columns) to "provided by
   ENH-3407", and its consumer references to `authoritative_attempts(cell_key)` /
   `authoritative_attempt(cell_key, repetition)`.

## Acceptance Criteria

- A fresh invocation records `attempt_kind = repetition` with the next free 0-based
  repetition index for its cell; concurrent allocators are serialised under
  `BEGIN IMMEDIATE`, so no `IntegrityError` surfaces and no index is skipped. `cell_key`
  follows the documented JSON-array encoding.
- The row's `head_sha` column equals the sha embedded in its `cell_key`; both come from a
  single pre-run `git rev-parse HEAD`.
- `--retry-of <id>` records `infra_retry`, reuses the prior's repetition index, sets
  `superseded_by` on the prior row, and appends exactly one `harness_admissions` row with
  `reason = 'timeout'` — all in one transaction.
- `--retry-of` is refused with exit 1 and a stderr message naming the attempt — before any
  action runs — when the prior attempt: does not exist; has no `cell_key`; is already
  superseded; belongs to a different cell; or did not time out (reached grading or runner
  error). Test: a retry of a graded FAIL is rejected; a retry of a timeout is accepted.
- A retry whose `record_attempt` write fails exits non-zero with an error naming the
  attempt and leaves no new row, the prior row un-superseded, and no admission row
  (transactional).
- `harness_admissions` rows are never updated or deleted; a test asserts no UPDATE/DELETE
  SQL statement in `writers.py` targets `harness_admissions` (scoped to that table).
- `authoritative_attempt(cell_key, repetition)` returns the earliest non-superseded row for
  that repetition; `authoritative_attempts(cell_key)` returns one per repetition. No CLI
  flag overrides selection. Losing attempts remain in `harness_events`.
- `record_harness_event()` returns the inserted id; existing callers are unaffected.
- `HarnessEvent` exposes `id` and the five new columns.
- `--retry-of` on `dsl` is accepted only for a single task-file `path` with a matching
  `dsl-task` prior.

## Scope Boundaries

- **In scope**: writer/reader functions above, `record_harness_event` extension, `HarnessEvent`
  column addition (moved here from ENH-3408), `--retry-of` flag + gate + refusal,
  `harness_admissions` writes, `cell_key` encoding, docs, resolving the **timeout** half of
  the exit-signal ambiguity via the persisted `timed_out` column. The **runner-error** half
  (`FileNotFoundError`, scope-resolution failures, MCP config/usage errors,
  `scope_runner_error()`'s dispatcher-level `exit_code=2`) has no persisted signal:

  **Option A**: Fail closed — refuse `--retry-of` whenever the prior's `timed_out` is falsy,
  accepting that legitimate runner-error retries stay inadmissible until a future issue adds
  a persisted error signal.

  > **Selected:** Option A — no new schema DDL, and the timeout half is already resolvable
  > via the existing `timed_out` column.

  **Option B**: Add a persisted error signal to `harness_events` (schema DDL) so runner-error
  retries can be admitted too.

### Decision Rationale

**Selected: Option A — fail closed on the runner-error signal gap.**

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — Fail closed | 3 | 3 | 3 | 3 | 12/12 |
| B — Widen scope (schema DDL) | 0 | 0 | 1 | 0 | 1/12 |

The original rationale also cited ENH-3406 being still open; ENH-3406 is now `done` and its
schema has landed, so that concern is moot. Option A stands on its own: no DDL, and it is
directly implementable today. A follow-up issue for the persisted error signal (which would
unlock `harness_error`/`host_crash`/`network` reasons) is the natural next step.

- **Out of scope**: `harness_events`/`harness_admissions` schema DDL (ENH-3406, landed);
  `history_pass_rate_runs` / DSL `graded_total` / `harness_eval_pass_rate` /
  `harness_eval_abstention_rate` counting logic and the run-report admissions tabulation
  (ENH-3408); populating `continuations`; a persisted runner-error signal; any `--force`
  escape hatch.

## Program Design

### Types
- `RunnerResult.timed_out: bool`, `RunnerResult.error: str | None` (`runner_spec.py:71-84`);
  only `timed_out` is persisted.
- `HarnessEvalOutcome` (`cli/harness.py:557-564`) carries neither; the gate reads the prior's
  persisted `timed_out`, and the recording path reads the fresh `RunnerResult`.
- `harness_events` (`schema.py:715-733` + v49 `:1370-1378`): `cell_key TEXT`, `repetition
  INTEGER`, `attempt_kind TEXT CHECK IN ('repetition','infra_retry')`, `continuations
  INTEGER`, `superseded_by INTEGER`; partial UNIQUE `idx_harness_cell_repetition` on
  `(cell_key, repetition) WHERE attempt_kind = 'repetition'`.
- `harness_admissions` (`schema.py:1379-1385`): `id`, `ts`, `attempt_id`, `superseded_id`,
  `reason TEXT CHECK IN ('timeout','host_crash','harness_error','network')`.
- `HarnessEvent` (`history_reader/harness.py:36-63`) + `id` + five new fields.

### Signatures
- `record_harness_event(db_path, *, ts, ..., cell_key=None, repetition=None,
  attempt_kind=None, continuations=None, superseded_by=None) -> int`
- `_insert_harness_event(conn, *, ts, ..., superseded_by=None) -> int` (private; INSERT +
  `_index()` on a caller-owned connection, no commit)
- `record_attempt(db_path, *, cell_key, attempt_kind, retry_of=None, reason=None,
  continuations=None, **event_fields) -> int` (`BEGIN IMMEDIATE`; with `retry_of`, also
  supersedes + admits before the single commit)
- `admit_retry(db_path, *, attempt_id, superseded_id, reason) -> None`
- `_admit_retry(conn, *, attempt_id, superseded_id, reason) -> None` (private; shared
  UPDATE + admission INSERT, no commit)
- `harness_event_by_id(db_path, attempt_id) -> HarnessEvent | None`
- `authoritative_attempt(db_path, cell_key, repetition) -> HarnessEvent | None`
- `authoritative_attempts(db_path, cell_key) -> list[HarnessEvent]`
- `_cell_key(runner: str, target: str, head_sha: str | None) -> str` (`cli/harness.py`)

Precedent notes: no `writers.py` function returns an inserted id today (`cli_event_context`/
`skill_event_context`, `:483,578`, keep `lastrowid` internal); the two return conventions are
raise-on-failure/`None` (`record_harness_event` and siblings) and guard-clause/`bool`
(`record_orchestration_run` `:1287`, `record_learning_test_event` `:1604`). The `int`
return is new but additive. No "next free N in a group" SQL allocator exists anywhere in
`session_store/` (the only counter precedent is `issue_parser.py:3220-3247`'s file-backed
issue-id highwater) — `record_attempt`'s allocation is new query logic, backed by
`idx_harness_cell_key` (ENH-3406).

### Call Path
`cmd_*` → pre-run `head_sha` + `_cell_key()` → gate (`harness_event_by_id`, refusal rules)
→ `run_action()` (`runner_spec.py:420`) → `_evaluate_and_report()` (`cli/harness.py:659`)
→ `record_attempt()` → `_insert_harness_event()` → (`retry_of` only) `_admit_retry()` → commit.

## Current Behavior

No `session_store` writer records an attempt against a `cell_key`/`repetition`, admits a
retry, or resolves which attempt for a cell is authoritative. `ll-harness`'s evaluators
have no `--retry-of` flag, so there is no way to mark an infra retry as distinct from a
fresh repetition, and no admission event is ever recorded — a retry of a timed-out attempt
and a retry of a graded failure are indistinguishable in `harness_events` today. The v49
columns exist but are written by nothing.

## Expected Behavior

Every evaluator invocation writes a `harness_events` row with `cell_key`, `repetition`, and
`attempt_kind`. `--retry-of <id>` is gated before the run by the refusal rules, and when
admitted records `infra_retry` with `superseded_by` set on the prior and an append-only
`harness_admissions` row. Readers can resolve the authoritative attempt per repetition.
Pass-rate calculations still count raw rows until ENH-3408.

## Impact

- **Priority**: P1.
- **Effort**: Large — writer extension + two new writers, three new readers, `HarnessEvent`
  columns, a pre-run gate threaded through 5 handlers with DSL special-casing, and docs.
- **Risk**: Medium — the gate is fail-closed on a single persisted signal; the main risk is
  the DSL retry semantics and the unsuppressed write path changing exit behavior only when
  `--retry-of` is present.
- **Breaking Change**: No.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-08:_

- ENH-3406 is `status: done`; its schema is confirmed landed in `schema.py`. This issue is
  ready to implement.
- Five line-citation drifts corrected in that pass; all other citations confirmed.
- Decisions log: no active required rules. Evidence-quote check clean.

_Review pass — 2026-09-08 (manual):_ added the `cell_key` encoding, the
`record_harness_event` extension, the pre-run gate ordering, the extra refusal rules, DSL
semantics, the per-repetition authoritative rule, the read-side placement of
`authoritative_attempt`, ENH-3406's three follow-ups, and unsuppressed retry-path writes.
Re-run `/ll:verify-issues` before `/ll:manage-issue` to refresh `verify_verdict`.

_Pre-implementation review — 2026-09-08 (manual):_ added `id` to `HarnessEvent` (gate
needs `prior.id`; the dataclass had none); pre-run single `head_sha` read shared by
`cell_key` and the row (post-run read at `cli/harness.py:154` drifts when a skill run
commits); `BEGIN IMMEDIATE` allocation replacing the `IntegrityError` retry loop;
single-transaction retry write (no orphan `infra_retry` row); refusal messages to stderr;
`cmd_mcp` gate after arg validation; DSL same-name cell collision documented.

## Status

**Open** | Created: 2026-09-08 | Priority: P1 | Blocked by: ENH-3406 (done)


## Session Log
- `/ll:confidence-check` - 2026-09-08T20:44:42 - `6f51642f-2e27-4a91-aa1c-d82fabf2a587.jsonl`
- `/ll:verify-issues` - 2026-09-08T20:23:07 - `177666e2-e3a8-45e9-869d-82933b239524.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:57:50 - `b6b6e9ca-1e9e-4589-b966-7e973d10f797.jsonl`
- `/ll:wire-issue` - 2026-09-08T19:18:57 - `8253aa54-816e-4b30-a515-5729bc18e0a3.jsonl`
- `/ll:decide-issue` - 2026-09-08T19:08:06 - `204483fb-0035-4a22-9571-7e0656ebef10.jsonl`
- `/ll:reconcile-issue` - 2026-09-08T18:52:23 - `454b24f9-6fdd-4c61-af5d-a12445ba857c.jsonl`
- `/ll:refine-issue` - 2026-09-08T18:44:58 - `204483fb-0035-4a22-9571-7e0656ebef10.jsonl`
- `/ll:format-issue` - 2026-09-08T18:36:35 - `204483fb-0035-4a22-9571-7e0656ebef10.jsonl`
- `/ll:verify-issues` - 2026-09-08T16:33:42 - `c583b7d9-3c7b-4be3-a8d8-28020e64ec08.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T16:28:15 - `f0d9ed08-0cba-4bb7-8f0a-69ea09901e1b.jsonl`
- `/ll:verify-issues` - 2026-09-08T16:20:32 - `2dadb131-5e4a-4c09-9d19-56a9dade3f05.jsonl`
- `/ll:wire-issue` - 2026-09-08T16:12:48 - `b577621d-b663-413a-acf5-9443c97719cf.jsonl`
- `/ll:refine-issue` - 2026-09-08T15:57:12 - `762622bd-d347-40b3-98c7-f5255d78a179.jsonl`
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`
