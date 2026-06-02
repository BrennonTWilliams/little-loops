---
id: ENH-1699
type: ENH
status: done
priority: P4
parent: ENH-1667
completed_at: 2026-05-25T22:10:39Z
depends_on:
- ENH-1665
labels:
- telemetry
- loops
- meta-loop
- harness
- observability
decision_needed: false
confidence_score: 98
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1699: Meta-eval telemetry write and archive

## Summary

Instrument `PersistentExecutor._handle_event()` to write one JSONL entry to
`meta-eval.jsonl` per iteration when a meta-loop (as detected by
`_is_meta_loop()`) transitions out of an `llm_structured` evaluate state.
Archive the file alongside `events.jsonl` and `state.json` at run end.

## Current Behavior

Meta-loop runs produce no per-iteration telemetry pairing LLM self-grade
verdicts with external evaluator results. There is no way to measure
self-evaluation accuracy (i.e., how often the LLM's "yes/no" matches the
external gate outcome) without manually correlating `events.jsonl` entries
post-hoc. The divergence documented in ENH-1667 (SHOR Table 1: Sonnet 4.6
agrees with external evaluators ~33% of the time) is not observable at
run time.

## Expected Behavior

When a meta-loop transitions through an `llm_structured` evaluate state,
`PersistentExecutor._handle_event()` appends one JSONL entry to
`{run_dir}/meta-eval.jsonl` containing: `iteration`, `ts`, `loop`, `state`,
`llm_verdict`, `llm_rationale` (truncated), `external_verdict`,
`external_state`, `external_evaluator`, `external_value`, `external_target`,
`diff_stats`, and `agreed` (boolean). `StatePersistence.archive_run()`
conditionally copies the file to the history archive alongside `events.jsonl`
and `state.json`. Non-meta-loop runs are unaffected (no file produced).

## Impact

- **Priority**: P4 — Low; observability gap does not block functionality but
  enables future analysis of LLM self-evaluation drift
- **Effort**: Small — two targeted changes in `persistence.py`, one new
  property on `StatePersistence`, plus doc and test additions
- **Risk**: Low — conditional logic guarded by `_is_meta_loop()`; non-meta
  runs unchanged; archive copy is existence-guarded
- **Breaking Change**: No

## Scope Boundaries

- Does **not** change LLM judge prompts, evaluation logic, or routing
- Does **not** add analysis tooling or dashboards for the telemetry
- Does **not** backfill historical runs; new file appears in future runs only
- `meta_self_eval_ok: true` loops still produce telemetry (that flag suppresses
  the validator warning, not observability)
- Diff stats capture reuses `diff_stall` cached output when available;
  a fresh `git diff --stat HEAD` call is the fallback — no new subprocess
  infrastructure

## Parent Issue

Decomposed from ENH-1667: Meta-loop runtime divergence telemetry (follow-up)

## Implementation Steps

**Step 1 — Write site in `PersistentExecutor._handle_event()` (`persistence.py:501`)**

In `_handle_event()`, track the last non-LLM `evaluate` event on the instance
(similar to the existing `_last_result` tracking). When an `llm_structured`
`evaluate` event arrives and `_is_meta_loop(self.fsm)` is true, emit a
combined JSONL entry to `{run_dir}/meta-eval.jsonl`:

```json
{
  "iteration": 7,
  "ts": "2026-05-24T03:14:15Z",
  "loop": "harness-optimize",
  "state": "check_semantic",
  "llm_verdict": "yes",
  "llm_rationale": "<truncated to 200 chars>",
  "external_verdict": "no",
  "external_state": "gate",
  "external_evaluator": "convergence",
  "external_value": "0.82",
  "external_target": "0.85",
  "diff_stats": {
    "files_changed": 1,
    "insertions": 4,
    "deletions": 2
  },
  "agreed": false
}
```

Import `_is_meta_loop` as `from little_loops.fsm.validation import _is_meta_loop`.
`run_dir` = `self.persistence.events_file.parent`. Use append mode with
`json.dumps(entry) + "\n"` per the `StatePersistence.append_event()` pattern
at `persistence.py:277`.

**State name (`"state"` field)**: The `evaluate` event dict does **not** carry the
current state name (confirmed by reading `FSMExecutor._emit()` at `executor.py:1339`).
Read `self._executor.current_state` at the moment `_handle_event()` fires to populate
the `"state"` field. `self._executor` is the inner `FSMExecutor` instance stored at
construction time (line 466 of `persistence.py`).

**`meta_eval_file` path**: Add a `meta_eval_file` property to `StatePersistence`
(analogous to the existing `state_file`/`events_file` properties) returning
`self._running_dir / "meta-eval.jsonl"` (or equivalent path convention). Then
reference `self.persistence.meta_eval_file` at the write site and in `archive_run()`.
This avoids repeating path construction logic and keeps the pattern consistent.

For `diff_stats`: reuse `diff_stall` event details when available (the
`diff_stall` evaluator at `evaluators.py:378` already runs `git diff --stat`).
**Caution**: the `diff_stall` event's `details` dict contains `stall_count`,
`max_stall`, and `diff_changed` — it does NOT contain `files_changed`/`insertions`/
`deletions`. When the last non-LLM result is from `diff_stall`, parse its stored diff
text from `.loops/tmp/ll-diff-stall-<cache_key>.txt` or fall back to a fresh
`subprocess.run(["git", "diff", "--stat", "HEAD"])` call and parse the summary line.
`agreed` = LLM verdict and external verdict both map to the same boolean outcome.

**Step 5 — Update `StatePersistence.archive_run()` (`persistence.py:310`)**

After the two existing `shutil.copy2` calls (`state.json`, `events.jsonl`),
add a conditional third:

```python
if (running_dir / "meta-eval.jsonl").exists():
    shutil.copy2(running_dir / "meta-eval.jsonl", archive_dir / "meta-eval.jsonl")
```

This keeps non-meta-loop runs unaffected. `_reconcile_stale_runs()` at
line 356 calls `archive_run()` indirectly — the same fix covers that path.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/generalized-fsm-loop.md` — add `<stem>.meta-eval.jsonl` to the
   directory tree under `### Canonical Location` (~line 1438) as a meta-loop-only
   artifact; add a brief note in `## Structured Events` (~line 1543) that meta-loops
   write a sibling `meta-eval.jsonl` during `llm_structured` evaluate transitions
7. Update `docs/guides/LOOPS_GUIDE.md` — revise the archive description at ~line
   2654 to include `meta-eval.jsonl` for meta-loops ("state, event logs, and
   meta-eval telemetry")
8. Update `docs/reference/API.md` — update the `.running/` file structure example
   in the `#### StatePersistence` section (lines 4625–4632) to include
   `<stem>.meta-eval.jsonl` (in addition to the `archive_run()` method table row
   update already planned in Step 5)
9. Add `test_archive_run_copies_meta_eval_when_exists` in
   `scripts/tests/test_fsm_persistence.py::TestArchiveRun` — isolates the
   conditional copy logic directly without requiring a full `PersistentExecutor.run()`
   fixture (see Tests section above)

### Open Questions (from parent)

- Should `meta_self_eval_ok: true` loops still produce telemetry? **Yes** —
  the flag suppresses the validator, not observability. `self.fsm.meta_self_eval_ok`
  is available at the write site; do not gate on it.
- Diff capture cost: reuse `diff_stall` event details when available to
  avoid an extra `git diff --stat` call per iteration.

## Tests

- **`scripts/tests/test_fsm_persistence.py`** (primary): Add a new test in
  `TestPersistentExecutor` following the pattern of
  `test_run_archives_to_history_on_completion` at line 966 — run a meta-loop
  fixture through `PersistentExecutor.run()` and assert `meta-eval.jsonl` is
  produced in the history archive with the expected fields (`iteration`, `loop`,
  `state`, `llm_verdict`, `external_verdict`, `agreed`). Read the JSONL,
  `json.loads()` each line, assert on field presence and `agreed` bool.
- **`scripts/tests/test_fsm_persistence.py::TestArchiveRun`** (new, direct unit
  test): Add `test_archive_run_copies_meta_eval_when_exists` — construct a
  `StatePersistence` directly, write a `meta-eval.jsonl` file to the running dir,
  call `archive_run()`, and assert it is copied to the history archive. This
  complements the full `PersistentExecutor.run()` integration test above and
  isolates the conditional copy logic in `archive_run()` itself. Follow the same
  file-existence guard pattern as `test_archive_run_copies_state_and_events` (line
  395) and `test_archive_run_only_state_no_events` (line 444).
- **`scripts/tests/test_harness_optimize.py`**: Note — this file does NOT run
  `PersistentExecutor.run()`; it tests YAML structure and Bash snippet fragments
  via `subprocess.run()`. An end-to-end archive assertion belongs in
  `test_fsm_persistence.py` (above), not here. No change required to this file
  unless validating the YAML declares the meta-loop correctly for `_is_meta_loop()`.
- **`scripts/tests/test_fsm_persistence.py`**: Watch —
  `TestArchiveRun.test_archive_run_only_state_no_events` at line 444 asserts
  `events.jsonl` is absent for non-event runs. The `meta-eval.jsonl` write is
  gated on `_is_meta_loop()`, so this non-meta-loop fixture is safe; verify the
  fixture loop is not inadvertently classified as a meta-loop before signing off.
  Also watch `test_clear_all_archives_before_clearing` (line 480) — same safe
  assumption; confirm fixture before sign-off.
- **`scripts/tests/test_ll_loop_execution.py`**: Exercises `PersistentExecutor.run()`
  end-to-end via `main_loop()` (with subprocess mocked). `TestEndToEndExecution`
  globs for `*.events.jsonl` and `*.state.json` only; `meta-eval.jsonl` is not
  inspected. No changes needed since all fixtures are non-meta-loops, but this
  file is a consumer of the full run lifecycle — confirm no fixture accidentally
  becomes meta-loop-classified after the change. [Agent 1 finding]
- **`scripts/tests/test_cli_loop_lifecycle.py`**: All tests patch `StatePersistence`
  with plain `MagicMock` — the new `meta_eval_file` property auto-creates as a
  `MagicMock` attribute, so no breakage. Watch out if any test is later switched
  to `create_autospec(StatePersistence)` — the property must exist at spec time.
  No changes needed now. [Agent 3 finding]
- **`scripts/tests/test_fsm_validation.py`**: Tests `_is_meta_loop()` and
  `_validate_meta_loop_evaluation()` — the gate condition used at the write site.
  No changes needed, but review these tests to understand what FSM fixture shapes
  trigger meta-loop classification before writing the new `TestPersistentExecutor`
  meta-loop fixture. [Agent 1 finding]

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/persistence.py` — add `meta_eval_file` property
  to `StatePersistence`; add `_last_non_llm_result` tracking in `_handle_event()`
  (line 501); write `meta-eval.jsonl` on `llm_structured` evaluate events in
  meta-loops (state name via `self._executor.current_state`); update `archive_run()`
  at line 310 to copy `meta-eval.jsonl` conditionally
- `scripts/little_loops/fsm/validation.py` — import `_is_meta_loop` from
  here (line 858); no changes needed to this file

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — imports `PersistentExecutor`,
  `_reconcile_stale_runs`; constructs `PersistentExecutor(...)` at line 344
  and invokes `executor.run()` — the primary execution entry point that triggers
  `_handle_event()` and `archive_run()`; no code changes needed, but the full
  run lifecycle (including `meta-eval.jsonl` write and archive) flows through here
- `scripts/little_loops/cli/loop/lifecycle.py` — imports `StatePersistence`;
  `cmd_resume()` constructs `PersistentExecutor` and calls `executor.resume()`,
  meaning **resume runs of meta-loops will also write and archive `meta-eval.jsonl`**;
  `_status_single()`, `cmd_stop()` also construct `StatePersistence` directly
  (for state reading, not write/archive — no impact)
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` (line 640)
  calls `executor.run()` and `executor.resume()`; transitive consumer of the new
  behavior; no code changes needed
- `scripts/little_loops/fsm/__init__.py` — re-exports `PersistentExecutor` and
  `StatePersistence` in `__all__`; no changes needed (new `meta_eval_file` property
  is on `StatePersistence` and is automatically part of the public interface)

### Documentation Updates

- `docs/reference/loops.md` — add `meta-eval.jsonl` to the `harness-optimize`
  output artifacts section (note: no `### Output Artifacts` subsection exists today
  for `harness-optimize`; create it under the `## harness-optimize` section)
- `docs/reference/API.md` — update `StatePersistence.archive_run()` method
  table row to reflect three files being copied (currently says two); also update
  the `.running/` file structure example (lines 4625–4632 in the `#### StatePersistence`
  section) to include `<stem>.meta-eval.jsonl` alongside `.state.json` / `.events.jsonl`
- `docs/generalized-fsm-loop.md` — add `<stem>.meta-eval.jsonl` to the directory
  tree in `### Canonical Location` (~line 1438) as a meta-loop-only artifact;
  add a brief note in `## Structured Events` (~line 1543) that meta-loops also
  produce a sibling `meta-eval.jsonl` file written during `llm_structured` evaluate
  transitions [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — update the archive description sentence at
  ~line 2654 ("Loop run state and event logs are automatically archived…") to
  mention `meta-eval.jsonl` for meta-loops [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`evaluate` event structure** (`executor.py:1339`): `FSMExecutor._emit()` produces
  `{"event": "evaluate", "ts": ..., "type": <evaluator_type>, "verdict": ..., **result.details}`.
  For `llm_structured`, `event["type"] == "llm_structured"`. State name is NOT in the
  event — must be read from `self._executor.current_state` at handler call time.
- **`_last_result` pattern** (`persistence.py:472`, `501`): Already tracks every
  evaluate event as `{"verdict": ..., "details": {...}}`. The new `_last_non_llm_result`
  should be set inside the same branch when `event.get("type") != "llm_structured"`,
  giving the prior non-LLM evaluator result to pair with the LLM verdict.
- **`diff_stall` event details** (`evaluators.py:378`): Fields in `result.details` are
  `stall_count`, `max_stall`, `diff_changed` — NOT `files_changed`/`insertions`/`deletions`.
  The diff text is persisted to `.loops/tmp/ll-diff-stall-<cache_key>.txt`; parse that
  or run a fresh `git diff --stat HEAD` to produce the structured `diff_stats`.
- **`StatePersistence.events_file`** (`persistence.py:227`): Path is
  `.loops/.running/<stem>.events.jsonl`. Add `meta_eval_file` as
  `.loops/.running/<stem>.meta-eval.jsonl` following the same convention.
- **JSONL append convention**: `open(path, "a") + json.dumps(entry) + "\n"` — consistent
  across `StatePersistence.append_event()` (L277), `JsonlTransport.send()` (transport.py:93),
  and `JsonlFileTransport.on_event()` (extension.py:126).
- **`archive_run()` existing copy calls** (`persistence.py:310`): Uses `shutil.copy2`
  (not `shutil.copy`) with per-file existence guards. Third copy should follow same pattern:
  `if (meta_eval_file).exists(): shutil.copy2(meta_eval_file, archive_dir / "meta-eval.jsonl")`.
- **`_is_meta_loop()` availability** (`validation.py:858`): Takes `FSMLoop`; `self.fsm` in
  `PersistentExecutor` is the `FSMLoop` instance (line 451). `self.fsm.meta_self_eval_ok`
  is available but must NOT gate the write (per the resolved open question).
- **Test reference**: `TestPersistentExecutor.test_run_archives_to_history_on_completion`
  at `test_fsm_persistence.py:966` is the exact pattern to follow for asserting archive
  contents after a full `PersistentExecutor.run()` call.
- **`_reconcile_stale_runs()` path** (`persistence.py:356`): Reaches `archive_run()` via
  `clear_all()` → `archive_run()`. New `meta_eval_file` property ensures the stale-run
  path picks it up automatically without changes to `_reconcile_stale_runs()`.
- **Related files** (no changes needed): `scripts/little_loops/fsm/schema.py` (FSMLoop
  at line 891), `scripts/little_loops/fsm/executor.py` (`_emit()` at line 1339)

## Verification

- Running any meta-loop produces `.loops/.history/<run_id>-<name>/meta-eval.jsonl`
  with one entry per iteration that hits an `llm_structured` state.
- Non-meta loops do NOT produce the file.
- `archive_run()` copies `meta-eval.jsonl` alongside `events.jsonl` and `state.json`.

## Session Log
- `/ll:ready-issue` - 2026-05-25T22:02:03 - `f360a7f8-c817-4ae2-95db-0b84dfdf3ee6.jsonl`
- `/ll:wire-issue` - 2026-05-25T21:57:45 - `26cf1dbf-472d-4db3-8f33-aac18fae86eb.jsonl`
- `/ll:refine-issue` - 2026-05-25T21:50:03 - `7033f867-b050-4b60-8afb-7642aa185381.jsonl`
- `/ll:issue-size-review` - 2026-05-25T22:45:00Z - `1164a851-abd3-4d31-9115-03f9bcd570f7.jsonl`
- `/ll:confidence-check` - 2026-05-25T23:30:00Z - `c6a3c6a3-666b-4b59-8bfb-287c7f66148b.jsonl`
