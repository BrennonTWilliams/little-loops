---
id: BUG-1767
title: StallDetector progress_paths fingerprint is defeated by loops that mutate their
  own progress-path files
type: BUG
priority: P3
captured_at: '2026-05-28T17:31:20Z'
completed_at: '2026-06-01T17:28:27Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
status: done
labels:
- bug
- captured
- fsm
- stall-detector
- loops
relates_to:
- BUG-1674
- BUG-1766
parent: EPIC-1773
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1767: StallDetector `progress_paths` fingerprint is defeated by loops that mutate their own progress-path files

## Summary

`BUG-1674` (done) made `StallDetector` progress-aware by fingerprinting a configured set
of `progress_paths` and resetting the stall deque whenever those files change between
records. But when a loop's `progress_paths` point at files the loop **mutates every
iteration as part of its own bookkeeping**, the fingerprint always changes, the deque
always resets, and the detector **never fires** — even during a genuine no-real-progress
spin.

`general-task.yaml` is the live example: its `progress_paths` are the plan/DoD tracking
files (`general-task-plan.md`, `general-task-dod.md`, lines 18–20), and its `continue_work`
state appends to `plan.md` on every cycle. In audit run `2026-05-28T145405`, the loop spun
for ~40 iterations re-executing finished work (see [[BUG-1766]]) and the audit recorded
**"no fault signals"** — because each `continue_work` append registered as "progress" and
reset the stall window. The detector is counting "the loop wrote to its own scratchpad" as
real progress.

## Motivation

- **Safety gap**: The BUG-1674 stall guard — designed to prevent infinite spins — is silently disabled for any loop whose `progress_paths` overlap its own write targets, negating an explicit reliability investment.
- **Observed impact**: In audit run `2026-05-28T145405`, `general-task` spun ~40 iterations re-executing finished work with **no fault signals** emitted (see [[BUG-1766]]), because scratchpad writes were counted as progress.
- **Scope**: Affects all loops that set `circuit.repeated_failure.progress_paths` to files they also write — any such loop silently loses stall protection, bounded only by `max_iterations`.

## Current Behavior

- `StallDetector` records `(state, exit_code, verdict)` and, per BUG-1674, a fingerprint
  of `progress_paths` (mtime/size or content hash).
- On each record, if the fingerprint differs from the prior record for that state, the
  deque resets.
- In `general-task`, `continue_work` appends a remediation step to `plan.md` every cycle,
  so the fingerprint of `plan.md` changes every cycle → deque resets every cycle → the
  stall signal can never accumulate to its `window`.
- Net effect: the BUG-1674 hardening is **disabled in practice** for any loop whose
  `progress_paths` overlap its own write targets.

## Expected Behavior

The detector should distinguish **real working-state progress** from **the loop touching
its own bookkeeping files**. Options to evaluate during refinement:

- **Separate the signals**: a loop should be able to declare progress paths that are
  *distinct* from its internal tracking artifacts (the work surface vs. the scratchpad),
  so appending to its own plan/DoD does not count as progress.
- **Content-semantic fingerprint**: instead of mtime/size, hash only the *meaningful*
  content (e.g. count of checked criteria) so that appending a duplicate/no-op step does
  not reset the deque.
- **Per-loop guidance/lint**: at minimum, warn (via `ll-loop validate`) when a loop's
  `progress_paths` intersect files written by its own prompt/shell actions, since that
  configuration silently neuters the stall guard.

The detector must still fire promptly for genuine no-progress loops.

## Steps to Reproduce

1. Configure a loop with `circuit.repeated_failure.progress_paths` pointing at a file the
   loop appends to every iteration (e.g. `general-task`'s `plan.md`).
2. Drive it into a state cycle that makes no real progress but keeps appending to that file
   (e.g. the BUG-1766 `continue_work → select_step → … → count_done → continue_work` spin).
3. Observe: the stall detector never fires despite many no-progress cycles; the loop runs
   to convergence or `max_iterations` with no fault signal emitted.

## Root Cause

- **File**: `scripts/little_loops/fsm/stall_detector.py` — fingerprint-reset logic added by
  BUG-1674; resets the deque on any `progress_paths` change.
- **File**: `scripts/little_loops/fsm/executor.py` — computes the fingerprint passed into
  `record(...)`.
- **Config surface**: `scripts/little_loops/loops/general-task.yaml` lines 18–20 —
  `progress_paths` set to files the loop itself mutates.
- **Cause**: the fingerprint treats *any* change to a progress path as evidence of forward
  progress. It cannot tell a real artifact change from the loop's own bookkeeping append,
  so a self-appending loop can never trip the stall window.

## Proposed Solution

Refine the BUG-1674 mechanism so self-mutated bookkeeping files don't mask stalls. Likely
the cleanest: distinguish "progress paths" (external work surface) from the loop's internal
tracking files, and/or fingerprint semantic content rather than mtime/size. Add an
`ll-loop validate` warning when `progress_paths` overlap the loop's own write targets.
Decide the concrete approach during `/ll:refine-issue` — both the detector semantics and
the general-task config need to land together.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Three concrete options surfaced. Select one via `/ll:decide-issue BUG-1767`.

### Option A — Add `exclude_paths` field to `RepeatedFailureConfig`

> **Selected:** Option A (add `exclude_paths` to `RepeatedFailureConfig`) — separates external progress signals from internal bookkeeping in the data model, actually closing the safety gap rather than only warning about it

Add `exclude_paths: list[str] = field(default_factory=list)` to `RepeatedFailureConfig` (`schema.py:800`), alongside `progress_paths`. In `_compute_progress_fingerprint()` (`executor.py:685`), filter out any resolved path that matches an `exclude_paths` entry before building the fingerprint tuple. Fix `general-task.yaml` lines 18–20 by moving `plan.md` / `dod.md` to `exclude_paths` (or removing `progress_paths` entirely). Update `fsm-loop-schema.json`. Add `_validate_progress_paths_isolation()` warning in `validation.py`.

- **Pro**: backward-compatible; no existing `progress_paths` configs break; minimal change to detector logic.
- **Con**: requires the loop author to correctly separate paths; another author can make the same mistake again without the lint catching it.

### Option B — Replace mtime/size fingerprint with content hash

Change `_compute_progress_fingerprint()` (`executor.py:685`) to hash file content via `hashlib.md5(p.read_bytes()).hexdigest()` instead of `(st.st_mtime, st.st_size)`. A no-op `continue_work` append (same text repeated) would no longer reset the deque; only genuinely new content resets it. Model after `evaluate_action_stall()` (`evaluators.py:510`) which uses `hashlib.md5` on tracked context values. Pair with `_validate_progress_paths_isolation()` lint warning.

- **Pro**: self-healing — idempotent / duplicate appends no longer defeat detection; no schema change needed.
- **Con**: content hash still changes on *any* new unique append, even a low-signal remediation step; does not fully decouple bookkeeping writes from progress detection; large files add minor hashing overhead.

### Option C — `ll-loop validate` WARNING only (no detector change)

Add `_validate_progress_paths_isolation(fsm)` to `validation.py`, modeled on `_validate_artifact_isolation()` (line 1136) + `_find_shared_tmp_writes()` (line 1120). Scan each state's `action` string for writes to files listed in `circuit.repeated_failure.progress_paths`; emit `ValidationSeverity.WARNING` per match. Wire into `validate_fsm()` (line 760) via `errors.extend(...)`. Fix `general-task.yaml` by removing `progress_paths` or pointing it at a file the loop never writes.

- **Pro**: smallest change; zero risk of regressing BUG-1674 real-progress detection; immediately adds the lint gate described in the issue.
- **Con**: does not fix the underlying detector semantics; a future loop with a write pattern the regex misses can still silently neuter stall detection.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: Option A — Add `exclude_paths` field to `RepeatedFailureConfig`

**Reasoning**: Option A and Option C both score 10/12, but Option A is selected because it closes the root cause — it adds a dedicated `exclude_paths: list[str]` field that separates "external work-surface progress signals" from "internal bookkeeping files", so the stall detector can actually fire during a genuine no-progress spin. Option C only adds a lint warning without fixing the detector semantics; the safety gap would remain open for any loop whose write pattern the regex misses. Option B scores 6/12 because content-hash fingerprinting is a partial fix: `continue_work` appends unique-numbered steps (`- [ ] Step N: …`) so hash still changes during the BUG-1766 stuck-loop scenario.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (exclude_paths) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B (content hash) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option C (lint only) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `progress_paths` field in `schema.py:817` is the exact structural template; `exclude_common_files` in `automation.py:242` is a living naming-convention precedent; `_validate_artifact_isolation()` in `validation.py:1136` provides the validator scaffold; `additionalProperties: false` on `repeated_failure` in `fsm-loop-schema.json:231` requires the schema update (mandatory but mechanical)
- Option B: `hashlib.md5` precedent in `evaluators.py:566` is strong, but `continue_work` appends unique step numbers each cycle — content hash still changes during the BUG-1766 stuck-loop scenario, leaving the bug unfixed for its primary observed case
- Option C: `TestArtifactIsolation` at `test_fsm_validation.py:988` provides all 6 test patterns as direct clones, but removing `progress_paths` from `general-task.yaml` disables the false-positive protection for bounce cycles; underlying safety gap remains open

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/stall_detector.py` — fingerprint/reset semantics.
- `scripts/little_loops/fsm/executor.py` — fingerprint computation passed to `record(...)`.
- `scripts/little_loops/loops/general-task.yaml` — `progress_paths` config (and any other
  loop with the same overlap).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/schema.py` — `RepeatedFailureConfig.progress_paths` (validation
  / possible new field for semantic vs. mtime fingerprinting).
- `scripts/little_loops/fsm/validation.py` — `_validate_circuit()` (line 1209) and `validate_fsm()` (line 760): new `_validate_progress_paths_isolation()` rule wires in here via `errors.extend(...)`.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for loop YAMLs; must be updated if a new field (`exclude_paths` or `semantic_paths`) is added to `circuit.repeated_failure`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `RepeatedFailureConfig`; transparently picks up new `exclude_paths` field; no code change required
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` in `cmd_validate()` surfaces new `_validate_progress_paths_isolation()` warnings via existing `for w in warnings` loop; no code change required

### Tests
- `scripts/tests/` FSM/stall-detector tests — add a regression that a loop appending to a
  `progress_paths` file every cycle still trips the stall window when no semantic progress
  occurs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_stall_detector.py:TestStallDetector` (line 12) — unit tests for fingerprint reset; BUG-1674 regression tests at lines 96–155 (`test_fingerprint_change_resets_window`, `test_fingerprint_unchanged_allows_stall_to_fire`); add BUG-1767 regression: self-appending loop still fires stall
- `scripts/tests/test_fsm_executor.py:TestStallDetector.test_progress_paths_prevent_false_positive_stall` (line 6691) — integration test using `ProgressRunner` fixture that writes new content each cycle; invert the scenario for a BUG-1767 regression (self-writes should not suppress stall)
- `scripts/tests/test_fsm_validation.py:TestCircuitValidation` (line 661) and `TestArtifactIsolation` (line 988) — validation warning test templates for new `_validate_progress_paths_isolation()` rule; import list at line 23 must be extended
- `scripts/tests/test_fsm_schema.py:test_repeated_failure_progress_paths_round_trip` (line 2922) — schema round-trip test pattern; update if a new `exclude_paths` field is added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py:TestGeneralTaskLoopFile.test_validates_as_fsm` (line 43) — will break if `general-task.yaml` is updated to use `exclude_paths` before `fsm-loop-schema.json` is updated; JSON schema and YAML must change in the same commit
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` (line 37) — runs `load_and_validate` over all builtin loops; same breakage risk as above; no change needed if schema and YAML land together

### Similar Patterns
- Audit other loops with `circuit.repeated_failure.progress_paths` for the same overlap
  between progress paths and self-write targets.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Scope confirmed**: `general-task.yaml` is the **only** builtin loop in `scripts/little_loops/loops/` with `progress_paths` configured — no sweep of other loops is needed beyond verifying `general-task.yaml` itself.
- **Direct structural template for validation rule**: `validation.py:_validate_artifact_isolation()` (line 1136) + `_find_shared_tmp_writes()` (line 1120) — scans state action strings for path overlap using a module-level regex; returns one `ValidationError(severity=WARNING)` per match; suppressed via a `shared_state_ok: true` flag. New `_validate_progress_paths_isolation()` should follow this exact pattern.
- **Content-hash templates** (for Option B): `evaluators.py:evaluate_diff_stall()` (line 415) and `evaluate_action_stall()` (line 510) both use `hashlib.md5` on content rather than mtime/size to distinguish real from fake progress — directly applicable to `_compute_progress_fingerprint()` in `executor.py:685`.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` / stall-detector reference — document that `progress_paths`
  must point at the external work surface, not the loop's own tracking files.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — inline `RepeatedFailureConfig` dataclass listing under "Nested config dataclasses (FEAT-1637)" needs `exclude_paths: list[str]` field added alongside the existing `progress_paths` entry

### Configuration
- Possible new schema field to opt into semantic-content fingerprinting.

## Implementation Steps

1. Decide detector approach (separate progress paths from tracking files vs. semantic
   fingerprint) during refinement.
2. Implement the chosen detector change in `stall_detector.py` / `executor.py`.
3. Fix `general-task.yaml` `progress_paths` to match the new contract.
4. Add an `ll-loop validate` warning for `progress_paths` ∩ self-write targets.
5. Add regression tests; sweep other loops for the same misconfiguration.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line references (apply after `/ll:decide-issue` selects option):_

**Option A (`exclude_paths` field):**
1. `schema.py:800` `RepeatedFailureConfig` — add `exclude_paths: list[str] = field(default_factory=list)`; update `from_dict()` (line 831) and `to_dict()` (line 819)
2. `executor.py:685` `_compute_progress_fingerprint()` — resolve `exclude_paths` entries via `interpolate()`; skip any path that matches an entry before appending to the fingerprint tuple
3. `scripts/little_loops/fsm/fsm-loop-schema.json` — add `exclude_paths` array property under `circuit.repeated_failure`
4. `validation.py` — add `_validate_progress_paths_isolation(fsm) -> list[ValidationError]` after `_validate_circuit()` (line 1209); model on `_validate_artifact_isolation()` (line 1136) and `_find_shared_tmp_writes()` (line 1120); wire into `validate_fsm()` (line 760) via `errors.extend(_validate_progress_paths_isolation(fsm))`
5. `general-task.yaml` lines 18–20 — move `general-task-plan.md` / `general-task-dod.md` to `exclude_paths` (or remove `progress_paths` block)
6. `test_stall_detector.py:TestStallDetector` (line 12) — add regression: self-appending loop with only `exclude_paths` changed still fires stall
7. `test_fsm_executor.py:TestStallDetector` (line 6522) — integration regression using inverted `ProgressRunner` scenario
8. `test_fsm_validation.py:TestCircuitValidation` (line 661) — add WARNING rule test; extend import list (line 23)
9. `test_fsm_schema.py:test_repeated_failure_progress_paths_round_trip` (line 2922) — add `exclude_paths` round-trip case

**Option B (content-hash fingerprint):**
1. `executor.py:685` `_compute_progress_fingerprint()` — replace `(st.st_mtime, st.st_size)` with `hashlib.md5(p.read_bytes()).hexdigest()`; add `import hashlib` at top of file
2. `validation.py` — same as Option A step 4
3. `general-task.yaml` lines 18–20 — fix `progress_paths` config (point at files the loop writes only on genuine transitions)
4. `test_stall_detector.py:TestStallDetector` (line 12) — add regression with content-hash semantics (idempotent append does not reset deque)

**Option C (lint warning only):**
1. `validation.py` — add `_validate_progress_paths_isolation(fsm)` after `_validate_circuit()` (line 1209); model on `_validate_artifact_isolation()` (line 1136) + `_find_shared_tmp_writes()` (line 1120); wire into `validate_fsm()` (line 760)
2. `general-task.yaml` lines 18–20 — remove `progress_paths` or point it at a file the loop never writes
3. `test_fsm_validation.py:TestCircuitValidation` (line 661) — add WARNING rule test
4. Run: `python -m pytest scripts/tests/test_fsm_validation.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/reference/API.md` — add `exclude_paths: list[str]` to the `RepeatedFailureConfig` inline dataclass listing under "Nested config dataclasses (FEAT-1637)"
11. Commit `fsm-loop-schema.json` and `general-task.yaml` together — `test_general_task_loop.py:test_validates_as_fsm` (line 43) and `test_builtin_loops.py:test_all_validate_as_valid_fsm` (line 37) both fail if `exclude_paths` appears in the YAML before the JSON schema is updated

## Impact

- **Priority**: P3 — Reliability gap in a safety mechanism, not an outage. It silently
  disables the BUG-1674 stall guard for self-appending loops, allowing wasted iterations
  (see BUG-1766) to go undetected. Bounded by `max_iterations`.
- **Effort**: Medium — touches detector semantics plus config and validation; needs a
  decision on approach.
- **Risk**: Medium — changing stall semantics affects every loop using `progress_paths`;
  must avoid regressing real-progress detection (the original BUG-1674 goal).
- **Breaking Change**: Possibly — if a new `progress_paths` contract requires existing
  loops to reconfigure.

## Related Key Documentation

- [[BUG-1674]] — introduced the `progress_paths` fingerprint reset this issue refines.
- [[BUG-1766]] — the general-task spin that this detector gap failed to catch.

## Labels

`bug`, `captured`, `fsm`, `stall-detector`, `loops`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-30_

**Verdict: VALID** — All claims confirmed:
- Referenced files exist: `stall_detector.py`, `executor.py`, `general-task.yaml` ✓
- `progress_paths` fingerprint reset logic correctly described ✓
- Self-mutating loop defeating stall detection is a real design concern ✓
- Related issues BUG-1674 (done) and BUG-1766 correctly linked ✓

## Resolution

**Fixed** via Option A (`exclude_paths` field). Added `exclude_paths: list[str]` to `RepeatedFailureConfig` (`schema.py`). The executor (`executor.py:_compute_progress_fingerprint()`) now resolves and filters out `exclude_paths` entries before building the fingerprint tuple. `general-task.yaml` moves its bookkeeping files from `progress_paths` to `exclude_paths`. `validation.py` gains `_validate_progress_paths_isolation()` warning when state actions reference an unexcluded `progress_paths` file. `fsm-loop-schema.json` updated. Tests added for all layers.

## Session Log
- `/ll:ready-issue` - 2026-06-01T17:20:23 - `2127b7f3-9b8d-4674-be8d-f44f8353a20c.jsonl`
- `/ll:confidence-check` - 2026-06-01T18:00:00 - `0f4fdf57-3369-4a0a-a654-a539b5b275a9.jsonl`
- `/ll:wire-issue` - 2026-06-01T17:12:49 - `1781e718-7f06-4b5d-95f3-141040199f61.jsonl`
- `/ll:decide-issue` - 2026-06-01T16:43:52 - `997f450b-5b8a-445c-92b5-d4f26bfcec0b.jsonl`
- `/ll:refine-issue` - 2026-06-01T16:37:41 - `d0453b81-1553-443e-b691-17734560a9e0.jsonl`
- `/ll:format-issue` - 2026-06-01T16:29:31 - `92bcd8b4-38a6-46b1-9488-9de681167c3e.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:03 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-28T23:48:16 - `0efd786b-4b4c-43ee-9e8e-268bad2cc8a5.jsonl`
- `/ll:capture-issue` - 2026-05-28T17:31:20Z - `d72d4842-d084-41b6-af0f-1adf964926ab.jsonl`

---

**Open** | Created: 2026-05-28 | Priority: P3
