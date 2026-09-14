---
id: ENH-3473
title: 'Write a best_effort-tagged checkpoint when a loop ends with no acceptance, so no outer iteration produces zero artifacts'
type: ENH
priority: P2
status: open
discovered_date: '2026-09-13'
labels: []
parent: ENH-3468
depends_on: [ENH-3471]
---

## Summary

When a loop's budget ends with no acceptance (a qualifying no-acceptance `terminated_by`), nothing is written beyond the cap-hit itself — the attempt that came closest to the objective is discarded even though it was already paid for. This issue adds a `best_effort`-tagged checkpoint on that path, so every outer iteration produces exactly one artifact whether or not the run succeeded, matching the pattern already used ad hoc by `canvas-sketch-generator.yaml`'s `finalize` state.

**Depends on ENH-3471**: "which `terminated_by` values qualify as no-acceptance" is only answerable once ENH-3471's named attempt-batch/decision-step vocabulary exists — implement this child after that one lands.

## Current Behavior

When a loop's budget ends with no acceptance (a qualifying no-acceptance `terminated_by`), nothing is written beyond the cap-hit itself — the attempt that came closest to the objective is discarded even though it was already paid for. `PersistentExecutor._save_state()` (`fsm/persistence.py:1129-1159`) only overwrites a single fixed per-instance state file on each `state_enter`/`loop_complete`/`baseline_complete` event; there is no per-iteration accumulation anywhere in `StatePersistence`, and no type representing a `best_effort`-tagged checkpoint artifact exists anywhere in the codebase.

## Expected Behavior

On a qualifying no-acceptance termination (per the `terminated_by` vocabulary ENH-3471 introduces), the executor writes exactly one `best_effort`-tagged checkpoint artifact (e.g. `iter_<N>_best_effort.json` with `metadata.best_effort=True`) holding the closest-to-objective attempt — so every outer iteration produces exactly one artifact whether or not the run succeeded, mirroring `canvas-sketch-generator.yaml`'s `finalize` pattern. Context-compaction failure (`hooks/pre_compact.py`, `session_store/lifecycle.py::compact_session()`) must stay hard-terminal and must NOT produce a best-effort checkpoint.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 3** and its directly-dependent wiring (checkpoint-artifact consumers — the attempt-batch/decision-step vocabulary wiring belongs to ENH-3471).

## Design

Pattern taken from a production search-loop framework over an expensive stochastic subject, whose failure-handling discipline is: *every failure mode has a designated resting place, and none of them is an exception escaping the loop.* On the no-acceptance path it writes an `iter_<N>_best_effort.json` checkpoint with `metadata.best_effort=True` — "every outer iter produces a checkpoint, never zero."

Closest existing analog: `scripts/little_loops/loops/canvas-sketch-generator.yaml:34,293,344` — `on_max_steps: finalize` plus `snapshot`/`finalize` states, where `finalize` always publishes the highest-scored iteration (`scores.tsv`, `sort -k2,2n -k1,1n | tail -1`) as `best.html`, reached on both a passing gate and step-cap exhaustion — but this is bespoke shell logic local to one loop, not a shared executor primitive. `general-task.yaml`'s `on_max_steps: summarize_partial` / `partial` terminal (ENH-2575, `:1219,1244,1303`) is precedent for "a run that hits its cap must still emit a graded artifact and land on its own terminal," not for the checkpoint-per-iteration mechanism itself.

**No shared "closest attempt to objective" scoring utility exists anywhere in the codebase** (confirmed by repo-wide search) — every existing per-loop instance reimplements the comparison independently in a different shape (deterministic shell sort, LLM-narrated score-history read, model self-report). This issue must pick or build one rather than assuming a reusable utility exists.

**Escape hatch — must NOT apply this pattern to context-compaction failure**: `scripts/little_loops/hooks/pre_compact.py`, `session_store/lifecycle.py::compact_session()` (called from `cli/compact_session.py::main_compact_session()`, no surrounding try/except) must stay hard-terminal. Compaction's own internal LCM escalation already guarantees a leaf node is produced, so a `best_effort`-tagged partial result there would misrepresent a failure as salvaged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Confirmed via repo-wide search: no shared "best of N" / "closest attempt to objective" scoring utility exists in `fsm/`, `cli/`, or any shared module. Every hit for candidate names (`best_of_n`, `select_best`, `BestAttempt`, `rank`, `top_n`, `highest_scor*`) belongs to an unrelated domain (host-model tiers in `advisor.py:83`, issue-priority ranking in `queue_store.py:300`, skill-keyword matching in `cli/verify_triggers.py:225`, epic-title picking in `cli/issues/link_epics.py:231`) or is a bespoke loop-YAML state name (`select_best` in `interactive-component-generator.yaml:363`, `apo-beam.yaml:39`) with no backing Python utility.
- Two disagreeing precedent conventions exist for "which iteration is closest to the objective," and this issue must pick one knowingly rather than assume either is canonical: (a) deterministic shell-side numeric comparison against a machine-written score file — `canvas-sketch-generator.yaml`'s `finalize` state (`sort -k2,2n -k1,1n scores.tsv | tail -1`, :344-363) and `vega-viz.yaml`'s incremental `record` state, which overwrites `best.html`/`best_score.txt` in place whenever a new score beats the stored best (:485-538, "the best result survives even if the loop ends by hitting max_iterations mid-cycle"); (b) LLM-narrated selection with no programmatic verification — `generator-evaluator.yaml`/`generator-evaluator-flux.yaml`'s `max_steps_summary` state, which hands the model a plain-text `.score_history` file and has it narrate the best iteration (:210-236, :335-359).
- The codebase's established per-iteration artifact convention is a directory per iteration (`iter-N/`, tracked via an `.iter_counter`/`.iter` sentinel file — `canvas-sketch-generator.yaml:293-320`, `vega-viz.yaml:500-509`, documented generically in `loops/lib/common.yaml:243`) or a flat `*-iter-N.*` filename (`docs/guides/LOOPS_REFERENCE.md:1899`) — not a single `iter_<N>_*.json` file. No file anywhere in the repo follows the `iter_<N>_*.json` shape this issue's Signatures section proposes, and no `metadata.best_effort=True`-style tag exists on any written artifact today (confirmed by repo-wide search — the only `best_effort` hits are unrelated test names about best-effort DB writes).
- Confirmed: no existing test covers "context-compaction failure stays hard-terminal" — `test_session_store_lifecycle.py::TestCompactSession`, `test_compaction.py`, `test_pre_compact.py` were searched directly with no match on this boundary. `session_store/lifecycle.py::compact_session()` (:679-710) wraps its call to `_compact_session_conn()` in a bare `try/finally` (only closing the connection) with no `except` clause, and `cli/compact_session.py::main_compact_session()` (:55-96) calls `compact_session(...)` with no surrounding try/except either — confirming the issue's claim that a compaction failure propagates as a raised exception rather than being converted into any kind of partial artifact.

## Program Design

### Types
- No existing type represents a `best_effort`-tagged checkpoint artifact anywhere in this codebase (confirmed by repo-wide search) — this is new surface area, not a rename of an existing mechanism. No `metadata.best_effort=True`-style tag, `iter_<N>_*.json` filename convention, `abort_reason`/`AbortReason` symbol, or literal `attempt_batch`/`decision_step` identifier exists today.

### Existing per-iteration persistence (do not reuse for this)
- `PersistentExecutor._save_state()` (`fsm/persistence.py:1129-1159`) is an existing per-iteration checkpoint mechanism, but it overwrites a single fixed file (`StatePersistence.save_state()`, `:502-523`, atomic `os.replace` over `<running_dir>/<instance_id>.state.json`) on every `state_enter`/`loop_complete`/`baseline_complete` event — there is no existing per-iteration accumulation anywhere in `StatePersistence`. A checkpoint that must survive past the next iteration needs a **new** write path, not a modification of this one. `usage.jsonl`/`messages.jsonl` (also written from `_handle_event()`, `:1020-1049`/`:1051-1062`) are the actual append-only per-event logs that already accumulate the "already-paid traces" this issue is salvaging.

### Decision Rules (must be resolved before/during implementation)
- **Which `terminated_by` values qualify for a "no acceptance" checkpoint** — not every value is a failure needing salvage (e.g. `handoff`/`user_stopped` are deliberate stops). Per the `general-task.yaml` `partial`-terminal precedent, whichever values qualify must route to a terminal distinct from both `done` and `failed`, since sub-loop routing treats `done` as `on_yes`. Depends on ENH-3471's new vocabulary being available.
- **"Closest to the objective" selection metric** — no established comparison rule to reuse generically (see Design above); pick one and document it.

### Signatures
- `write_best_effort_checkpoint(run_dir: Path, iteration: int, result: ExecutionResult) -> Path` (new, `scripts/little_loops/fsm/persistence.py`) — writes `iter_<iteration>_best_effort.json` with `metadata.best_effort=True`; called only when `terminated_by` is in the no-acceptance set ENH-3471 defines.
- `PersistentExecutor.run(self, clear_previous: bool = True) -> ExecutionResult` (existing, `scripts/little_loops/fsm/persistence.py:1212`) — gains a branch invoking `write_best_effort_checkpoint()` on a qualifying no-acceptance termination.
- `map_final_status(...)` (existing, `scripts/little_loops/fsm/persistence.py:132-168`) — decide whether the new outcome needs its own bucket in the closed 5-value return contract, per Wiring below.

### Call Path
`PersistentExecutor.run()` (`fsm/persistence.py:1212`) → `write_best_effort_checkpoint()` (new) → `StatePersistence` write helper (existing, `fsm/persistence.py:502-523`) → `map_final_status()` (`fsm/persistence.py:132-168`) → `_derive_loop_outcome()` (`cli/logs.py:2037-2062`).

## Wiring

- `scripts/little_loops/fsm/persistence.py::map_final_status()` (:132-168) — decide whether the no-acceptance/`best_effort` outcome needs its own bucket in the closed 5-value return contract (`completed`/`failed`/`interrupted`/`timed_out`/`awaiting_continuation`), or is acceptable in the existing `"failed"` catch-all; update the docstring's enumerated return values either way. Also called from `transport.py:1750` (OTel span attribute) and `session_store/writers.py:2891` (`loop_events.state`, BUG-3066).
- `scripts/little_loops/history_reader/usage.py::_WASTED_RUN_PREDICATE` (:310-316) — decide whether a `best_effort`-tagged salvaged run should count as "wasted" at all (arguably not, since a usable artifact was produced), and add the value if so.
- `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` (:2037-2062) — a closed `if/elif` chain checking `"error" in event` before `terminated_by`. A no-acceptance/`best_effort` terminal that does not set `error` (the entire point of the checkpoint being "no exception, just no acceptance") falls through every branch to the `final_state` keyword heuristic (:2060-2062) and, since a best-effort terminal name is unlikely to contain "fail"/"error"/"abort", silently returns `"converged"` — misclassifying a salvaged failure as success in fleet-review output. Needs an explicit new branch.
- `scripts/little_loops/cli/loop/runner.py` — `EXIT_CODES: dict[str, int]` (:39-55), looked up via `EXIT_CODES.get(result.terminated_by, 1)` (:585): decide the exit code for the new outcome rather than relying on the default-1 fallback. `_is_success = result.terminated_by in ("terminal", "interrupted", "handoff") and not result.failure_terminal` (:511-513): relevant only if the new outcome arrives as `terminated_by="terminal"` with `failure_terminal=True` (the `general-task.yaml` precedent) rather than a new string — needs correct `failure_terminal` to avoid being miscolored green as success.
- `skills/audit-loop-run/SKILL.md` (~line 293) — Step 6b verdict table's `partial` row is keyed on `terminated_by == "max_steps"` AND a `max_steps_summary` event (ENH-2575 precedent this issue's checkpoint models itself on). Add an analogous new row for the `best_effort` outcome, or it gets no verdict classification.
- `scripts/little_loops/generate_schemas.py` (:615-634) and `docs/reference/EVENT-SCHEMA.md` / `docs/guides/LOOPS_GUIDE.md` `### terminated_by exit reasons` table — add the new value's row once ENH-3471 lands the enumeration-update mechanics; this child only needs to add its own row/value to what ENH-3471 leaves in place.

### Wiring Pass Additions (`/ll:wire-issue`)

_The new checkpoint file lands in the gitignored, ephemeral `run_dir`; every durable-artifact consumer below works off a closed, hand-maintained filename/glob list that does not yet know about `iter_<N>_best_effort.json`. Without these additions the checkpoint is written but never durably archived, never credential-scanned, never hashed into the evidence bundle, and gets miscounted as an unexplained mutation:_

- `scripts/little_loops/fsm/persistence.py::StatePersistence.archive_run()` (:585-644) — add an `iter_*_best_effort.json`-shaped glob to the existing `("probe-*.json", "prepatch_evidence_*.json")` copy-list, or the checkpoint is never copied out of `run_dir` into `.loops/.history/` and is lost when `run_dir` is discarded [Agent 2 finding]
- `scripts/little_loops/cli/loop/evidence.py::_scan_for_credentials()` (~198-249) — add the new file to the fixed `("state.json", "events.jsonl", "summary.json")` tuple / `probe-*.json` glob so it gets credential-scanned like other checkpoint artifacts (ENH-3470) [Agent 2 finding]
- `scripts/little_loops/cli/loop/evidence.py` sha256 hashing tuple (~312-318, a second, independently-maintained copy of the same `("state.json", "events.jsonl", "summary.json")` tuple) — add the new file so it's included in the deterministic verification-evidence bundle (FEAT-3182) [Agent 2 finding]
- `scripts/little_loops/cli/loop/audit.py::_AUX_EXCLUDED_NAMES` / `_scan_aux_mutations()` (~23-30, ~144-174) — needs a **prefix/pattern check** (`name.startswith("iter_") and name.endswith("_best_effort.json")`), not a membership addition, since the filename is parameterized by iteration number; otherwise every best-effort checkpoint inflates `aux_mutation_count` [Agent 2 finding]
- `scripts/little_loops/cli/logs.py` — `_FLAG_OUTCOMES` (~line 1184), `is_flagged()` (~1187-1206), `_LoopFleetAggregate`/`_aggregate_fleet_runs()` (~1122-1160), and the fleet-review "Delta vs baseline" table (~2564-2566) all consume `_derive_loop_outcome()`'s bucket vocabulary; once that function gains its new branch (already in this issue's Wiring list above), decide whether the new bucket joins `_FLAG_OUTCOMES` [Agent 1 finding]
- `scripts/little_loops/fleet_improve.py` (imports `is_flagged` at :42; consumes `top_outcome`/`outcomes` at :243, :332-333, :344, :443-444, :552) — sidecar consumer applying the identical flagging rule; verify against once the outcome vocabulary changes [Agent 1 finding]
- `docs/runbooks/FLEET_LOOP_REVIEW.md` (~90-97) — outcome vocabulary prose (`converged | failed | error | max-steps | stalled | interrupted | signal`) needs the new bucket documented [Agent 1 finding]
- `docs/guides/LOOPS_GUIDE.md` `### Safety Limits` table (~line 127, `on_max_steps` row: "unset | Silent budget exhaustion...") — becomes stale once the executor writes a best-effort checkpoint on a qualifying no-acceptance termination even when `on_max_steps` is unset; this is a different section of the same file than the `terminated_by` table already listed above [Agent 2 finding]

### Tests (added by `/ll:wire-issue`)

- Extend `scripts/tests/test_cli_loop_lifecycle.py::TestCmdResumeExitCodes` — model the new outcome's exit-code + persisted-status pair on the `test_workdir_vanished_returns_exit_code_1` (:1466) / `test_workdir_vanished_maps_to_failed_persisted_status` (:1478) two-test shape, the most recent prior addition to both `EXIT_CODES` and `map_final_status`'s fallback [Agent 3 finding]
- Extend `scripts/tests/test_history_reader_usage.py::TestWasteAttribution` with a new dedicated test method (the file's own `_seed_run`-helper-plus-single-assertion-block convention, not `@pytest.mark.parametrize`) — same predicate ENH-3471 also adds a row to; see this issue's own Scope Boundary note above about sequencing against whatever shape ENH-3471 lands [Agent 3 finding]

### Confirmed Not Affected (no action needed)

- `PersistentExecutor.archive_run_only()` (:1161-1210) — its one caller (`cli/loop/signals.py:60`) hardcodes `terminated_by="interrupted_force"` and can never observe a no-acceptance value; it also has no `ExecutionResult` to pass to `write_best_effort_checkpoint()` (it builds `LoopState` directly from live executor fields). Confirmed genuinely out of scope, not merely deferred [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md`'s verdict table has no automated test anywhere (`test_audit_loop_run_skill.py`'s checks are pure string-containment on the prose); adding a `best_effort` row is documentation-only, no test infra to extend [Agent 3 finding]
- `map_final_status()`'s closed 5-value contract has no exhaustiveness/enum-membership assertion anywhere in the suite; adding a 6th bucket won't trip any existing test [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `map_final_status()` has a fourth caller not previously enumerated here: `fsm/persistence.py:1184` inside `archive_run_only()` — the signal-handler-safe force-exit path (invoked from `cli/loop/signals.py`'s `_loop_signal_handler()`). Any new outcome bucket or value this issue adds to `map_final_status()`'s closed contract must also be sane for that path, which runs outside the normal `PersistentExecutor.run()` completion flow.

## Implementation Steps

1. Pick and document a "closest attempt to objective" selection metric (Design → no shared utility exists; do not assume one).
2. Decide and document which `terminated_by` values (built on ENH-3471's new vocabulary) qualify as "no acceptance," per the Decision Rules above.
3. On a qualifying no-acceptance termination, write exactly one checkpoint artifact tagged `best_effort` (e.g. `iter_<N>_best_effort.json` with `metadata.best_effort=True`) — verified by a test asserting the artifact exists after a simulated cap-hit with no acceptance.
4. Add a test asserting NO such artifact is produced for a hard-terminal case this pattern must not cover — specifically context-compaction failure (`hooks/pre_compact.py`, `session_store/lifecycle.py::compact_session()`) staying hard-terminal. No existing test covers this boundary today.
5. Apply the Wiring section's updates (`map_final_status`, `_WASTED_RUN_PREDICATE`, `_derive_loop_outcome`, `EXIT_CODES`/`_is_success`, `audit-loop-run/SKILL.md`, docs/schema rows for this new value).
6. `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_persistence.py scripts/tests/test_builtin_loops.py scripts/tests/test_ll_logs.py -v` passes.

## Tests

- Content-level template for asserting on a checkpoint artifact's actual JSON content (not just YAML routing shape): `test_general_task_loop.py`'s `_load_script`/`_bash` pattern (`_load_script` extracts a state's literal `action:` shell string from the loop YAML, substitutes `${context.*}` placeholders, `_bash` executes it via `subprocess.run(["bash", "-c", ...])` against a real tmp `run_dir`), then `json.loads()`s the written file and asserts on individual keys — e.g. `test_counts_partial_progress_from_dod` (:2317), asserting `data["verdict"] == "partial"`, `data["checked"] == 2`.
- `test_ll_logs.py`'s `test_derive_outcome_workdir_vanished_with_error`/`_without_error` (:5137-5152) — closest structural precedent for "a named cause forced to a hard outcome, immune to other branches," to model the `_derive_loop_outcome` test after.
- Search confirmed no existing test for "context-compaction failure stays hard-terminal" (`test_session_store_lifecycle.py::TestCompactSession`, `test_compaction.py`, `test_pre_compact.py` — none assert this boundary); a new test is needed with no direct existing template.

## Scope Boundaries

- **In scope**: The no-acceptance/`best_effort` checkpoint write path, the "closest attempt to objective" selection metric, and the Wiring section's five downstream updates.
- **Out of scope**: `terminated_by` vocabulary itself (ENH-3471), context-compaction failure handling (must stay hard-terminal per the Design escape hatch), `PersistentExecutor._save_state()`'s existing single-file overwrite mechanism (not reused, not modified).

## Impact

- **Priority**: P2 - Matches frontmatter; blocked on ENH-3471's vocabulary landing first
- **Effort**: Medium - New write path, a selection-metric decision, and five downstream wiring updates (`map_final_status`, `_WASTED_RUN_PREDICATE`, `_derive_loop_outcome`, `EXIT_CODES`/`_is_success`, docs/schema)
- **Risk**: Medium - Touches shared outcome-classification code (`map_final_status`, `_derive_loop_outcome`) that other consumers (OTel spans, `loop_events.state`, fleet-review) already depend on; the Design section's context-compaction escape hatch is the sharpest correctness risk if missed
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-13 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `_WASTED_RUN_PREDICATE` (usage.py:310-316) edit shares the same `IN (...)` membership list as ENH-3471's edit to the same predicate. Already sequenced via `depends_on: [ENH-3471]`, but implement this issue's edit as an additive diff against whatever shape ENH-3471 actually lands (not against the pre-3471 line numbers cited above), since both issues touch the same list.

## Session Log
- `/ll:wire-issue` - 2026-09-14T20:29:41 - `8cf1df9b-8fca-46d9-b751-f28d170c6572.jsonl`
- `/ll:refine-issue` - 2026-09-14T19:32:06 - `93b68600-9c57-4c65-a431-1e887e42f117.jsonl`
- `/ll:format-issue` - 2026-09-14T19:19:10 - `b113a2f7-29c0-4877-96df-0ecdfe92bfb9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:46 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:25 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`
