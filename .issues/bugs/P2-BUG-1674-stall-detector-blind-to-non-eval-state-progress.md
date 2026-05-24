---
id: BUG-1674
type: BUG
priority: P2
status: done
discovered_date: 2026-05-24
completed_at: 2026-05-24T09:29:26Z
discovered_by: downstream-report
relates_to:
- FEAT-1637
confidence_score: 100
outcome_confidence: 89
decision_needed: false
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1674: StallDetector is blind to progress made by states with unconditional `next:` transitions

## Summary

`StallDetector` only records `(state, exit_code, verdict)` triples for states whose `_execute_state` reaches line 815 of `scripts/little_loops/fsm/executor.py`. States with an unconditional `next:` and no `evaluate:` take the early return at `executor.py:777` and never call `_stall_detector.record(...)`. Consequence: the detector cannot distinguish a *real* stall (same eval verdict, no work between cycles) from *slow but real* progress (same eval verdict, but an intermediate non-eval state made file-level changes between cycles). With `window: 3`, three visits to any eval-bearing state with identical verdict will fire the stall — even if the loop is iterating productively.

## Steps to Reproduce

Downstream report: `ll-marketing/.issues/bugs/P2-BUG-004-general-task-stalled-on-check-done.md`.

1. Use an FSM loop with a `check↔work` ping-pong where the work state uses `next:` (no `evaluate:`) — e.g. `general-task.yaml`'s `continue_work` state.
2. Run the loop against a task with many DoD criteria (~15+ unchecked).
3. Observe eval-bearing state (`check_done`) visited at iterations 4, 6, 8 — each returning `(check_done, 0, "no")` because the DoD still has ~16 unchecked criteria.
4. Between those visits, `continue_work` (iterations 5, 7) completes plan steps and flips DoD criteria from `[ ]` to `[x]` — real, file-level progress.
5. Observe: stall detector fires on the third identical `check_done` verdict and routes to `diagnose → failed`, killing the loop despite incremental progress.

## Root Cause

`scripts/little_loops/fsm/executor.py:751-777` — the `if state.next:` early-return path executes the action and routes via `state.next` without ever reaching the stall-detector record block at `executor.py:815-817`. So in any loop with a check↔work ping-pong where the work state uses `next:` (no `evaluate:`), the detector's deque fills with consecutive identical triples from the eval-bearing state regardless of intermediate productive work.

`general-task.yaml`'s `continue_work` matches this exactly: `action_type: prompt`, `next: check_done`, no `evaluate:`.

The detector is doing what it's documented to do (`stall_detector.py:1-11`), but the documented contract — "the same state produces the same exit code and verdict across consecutive iterations" — is itself the bug. "Consecutive in eval-bearing terms" is not the same as "consecutive without productive intermediate work," and the detector treats them identically.

## Current Behavior

`StallDetector` records `(state, exit_code, verdict)` triples only for states that reach `_stall_detector.record()` in `_execute_state`. States with an unconditional `next:` transition take the early-return path at `executor.py:777` and never call `record()`. With `window: 3`, three consecutive visits to any eval-bearing state with identical verdicts triggers the stall signal — even when intermediate non-eval states have made real file-level changes between cycles. The detector treats "same eval verdict" as equivalent to "no progress."

## Expected Behavior

The stall detector should not fire when intermediate state activity has measurably advanced the loop's working state since the previous record. Concretely: if observable artifacts the loop writes to (e.g. files under the loop's tmp dir, or a configured fingerprint set) changed between two `record()` calls for the same eval-bearing state, the deque should be reset.

The detector should still fire promptly for genuine no-progress loops: same verdict, zero file changes between cycles.

## Proposed Solution

Make the detector progress-aware. Two implementation sketches:

**Option A — Fingerprint-based reset, opt-in per loop:**
> **Selected:** Option A — Fingerprint-based reset — explicit, opt-in, reuses all existing patterns in the FSM module with no behavior change for existing loops
- Extend `RepeatedFailureConfig` (`fsm/schema.py:774-806`) with an optional `progress_paths: list[str]` (or `progress_glob`) field. When set, the executor hashes those paths' (mtime, size) — or a content hash for small files — before calling `record(...)` and passes the fingerprint in. `StallDetector.record(state, exit_code, verdict, fingerprint)` resets the deque if the fingerprint differs from the previous record for that state.
- Default behavior (no `progress_paths`) preserves current semantics — no regression for existing loops that rely on the detector.

**Option B — Generic intermediate-state-activity tracker:**
- Executor tracks a monotonic "productive activity counter" that increments whenever any non-eval-bearing state's action exits 0 (or writes a tracked artifact). The detector resets if the counter advanced between two records of the same triple.
- Less configuration, but harder to define "productive" generically — risks false negatives (a tracked state that does nothing useful still counts).

Recommend **Option A**: explicit, easy to reason about, no behavior change for loops that don't opt in. `general-task.yaml` would declare:
```yaml
circuit:
  repeated_failure:
    window: 3
    on_repeated_failure: diagnose
    progress_paths:
      - "${env.PWD}/.loops/tmp/general-task-plan.md"
      - "${env.PWD}/.loops/tmp/general-task-dod.md"
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-24.

**Selected**: Option A — Fingerprint-based reset, opt-in per loop

**Reasoning**: Every building block Option A requires is already present in the codebase — `evaluate_diff_stall()` in `evaluators.py:378-470` is a direct analogue computing mtime/size snapshots, `EvaluateConfig.scope` establishes the exact `list[str]` schema field pattern, and `interpolate()` is already in scope at the single `_stall_detector.record()` call site (`executor.py:817`). Option B is disqualified because `action_type: prompt` states — the dominant class of `next:`-bearing work states, including `continue_work` — always return exit code 0 regardless of productive output, making "exits 0" semantically meaningless as a discriminator without an artifact-tracking layer that has no existing infrastructure.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- Option A: `evaluate_diff_stall()` (`evaluators.py:378-470`) is a direct analogue; single call site at `executor.py:817`; `EvaluateConfig.scope` establishes exact schema pattern; `StallDetector.reset()` already exists; opt-in design means zero regression risk for existing loops
- Option B: `action_type: prompt` (used by `continue_work`, `define_done`, `plan`, `execute`) always exits 0 — breaks the "exits 0 = productive" heuristic; artifact tracking has no codebase infrastructure; broad impact on 215 `next:` traversals across 53 files for a feature used by one loop today

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/stall_detector.py` — extend `record()` to accept optional fingerprint; reset deque on fingerprint change
- `scripts/little_loops/fsm/executor.py` — compute path fingerprint before calling `record()` in `_execute_state`
- `scripts/little_loops/fsm/schema.py` — extend `RepeatedFailureConfig` with optional `progress_paths: list[str]`; update `from_dict()`/`to_dict()` (follow `EvaluateConfig.scope` pattern at `schema.py:80`)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `progress_paths` to the `repeated_failure` properties block (line 213); currently has `"additionalProperties": false` (line 226) which will reject the new field without a schema update

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/general-task.yaml` — add `progress_paths` under `circuit.repeated_failure`
- Any loop YAML using `circuit.repeated_failure` with `next:`-only work states (search: `repeated_failure` in `loops/`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py` — `_validate_circuit()` (lines 830–864) reads `RepeatedFailureConfig`; `progress_paths` is intentionally not validated here (interpolation strings like `${env.PWD}` cannot be validated at load time); no code change required, but confirm `from_dict()` call path passes cleanly on the new field [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — exports `StallDetector`, `Stall`, `RepeatedFailureConfig` in `__all__`; the `record()` signature change (`fingerprint=None` default) is backward-compatible; no change required, but verify export list after any class-level additions [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py:evaluate_diff_stall()` (lines 378–470) — closest existing analogue: computes a snapshot, reads a previous snapshot from a tmp file, resets a stall counter when the snapshot changes. Uses `hashlib.md5` for cache-key derivation and `Path.cwd() / ".loops" / "tmp"` for scratch storage. (Note: no `circuit_breaker.py` exists; the rate-limit circuit is `rate_limit_circuit.py` and has no fingerprint mechanism.)
- Other loop YAMLs with `check↔work` patterns: audit after fix

### Tests
- `scripts/tests/test_stall_detector.py` — unit tests for `StallDetector`; add fingerprint-reset tests; follow existing class `TestStallDetector` pattern (direct instantiation, `d.record(...)` then `d.check()`)
- `scripts/tests/test_fsm_executor.py` — integration-level stall tests in `TestStallDetector` class (lines 6252–6419); use `_make_fsm()` factory and `MockActionRunner` with `use_indexed_order=True` for controlled action sequences; filter events by `e.get("event") == "stall_detected"`
- `scripts/tests/test_fsm_schema.py` — `TestCircuitConfig` class with round-trip serialization tests (lines 2724–2760); add `test_repeated_failure_progress_paths_round_trip()` following existing round-trip pattern
- `scripts/tests/test_general_task_loop.py` — integration test for acceptance criterion: ~15 DoD criteria, ≥10 `check_done` cycles without stalling when `continue_work` writes to plan/DoD files

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py` — `TestCircuitValidation` class (lines 588–677); add `test_progress_paths_with_circuit_recognized_no_warning`: write a YAML with `progress_paths` under `repeated_failure`, call `load_and_validate()`, assert no unknown-key errors; follow `_write_yaml()` pattern at line 603 [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — document new `progress_paths` field on `RepeatedFailureConfig` (see existing entry at line 3937)
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide (confirmed at line 82 with `circuit.repeated_failure` reference table); add `progress_paths` to the stall-detector section

_Wiring pass added by `/ll:wire-issue`:_
- `skills/debug-loop-run/SKILL.md` — `#### BUG — Stall detector aborted the run` diagnostic note currently says to investigate the evaluator/action; after this fix the note will mislead — should also advise adding `progress_paths` to `circuit.repeated_failure` when the loop has productive `next:`-only work states between eval cycles [Agent 2 finding]

### Configuration
- `scripts/little_loops/loops/general-task.yaml` — add `progress_paths` entries for plan and DoD files

## Implementation Steps

1. Extend `RepeatedFailureConfig` in `fsm/schema.py` with `progress_paths: list[str] = field(default_factory=list)`; update `to_dict()` with `if self.progress_paths: result["progress_paths"] = self.progress_paths` and `from_dict()` with `progress_paths=data.get("progress_paths", [])` — follow `EvaluateConfig.scope` pattern (`schema.py:80,114,139`)
2. Update `scripts/little_loops/fsm/fsm-loop-schema.json`: add `"progress_paths": {"type": "array", "items": {"type": "string"}, "description": "..."}` inside `repeated_failure.properties` (after line 224); remove `"additionalProperties": false` guard would break other checks so add the property instead (line 226 already allows no extras — add the new property before it)
3. In `_execute_state` (`fsm/executor.py`, stall block at lines 815–817): interpolate each path in `repeated_failure.progress_paths` using `interpolate(p, ctx)` (supports `${env.PWD}` etc.), then compute `fingerprint = tuple((Path(p).stat().st_mtime, Path(p).stat().st_size) for p in resolved_paths if Path(p).exists())`; pass to `_stall_detector.record()`
4. Update `StallDetector.record()` (`stall_detector.py:41`) to accept `fingerprint: tuple | None = None`; store last fingerprint per state; if fingerprint differs from previous record for same state, call `self.reset()` before appending the new triple
5. Update `general-task.yaml` to declare `progress_paths` under `circuit.repeated_failure` pointing to `${env.PWD}/.loops/tmp/general-task-plan.md` and `${env.PWD}/.loops/tmp/general-task-dod.md` (interpolation already supported — `${env.PWD}` is used elsewhere in the same file); also revert `window: 7` back to `window: 3` since `progress_paths` removes the need for the workaround headroom
6. Add tests in `test_stall_detector.py` (unit: fingerprint-changes → deque reset; same fingerprint → fires; no `progress_paths` → current semantics), `test_fsm_executor.py` `TestStallDetector` (integration: mock file writes between records, follow `_make_fsm()` + `MockActionRunner` pattern), `test_fsm_schema.py` `TestCircuitConfig` (round-trip with `progress_paths`)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Confirm `scripts/little_loops/fsm/validation.py` `_validate_circuit()` requires no changes — `from_dict()` already uses `data.get("progress_paths", [])` default, so the load-time path does not fail on missing keys; `progress_paths` is intentionally excluded from validation (interpolation strings cannot be resolved at load time)
8. Add test in `scripts/tests/test_fsm_validation.py` `TestCircuitValidation`: `test_progress_paths_with_circuit_recognized_no_warning` — write YAML with `progress_paths` under `repeated_failure`, call `load_and_validate()`, assert no unknown-key errors (uses `_write_yaml()` helper at line 603)
9. Update `skills/debug-loop-run/SKILL.md` `#### BUG — Stall detector aborted the run` — append note that loops with productive `next:`-only work states between eval cycles should add `progress_paths` under `circuit.repeated_failure` to prevent false-positive stall fires

## Workaround (already applied)

`scripts/little_loops/loops/general-task.yaml` `circuit.repeated_failure.window` widened from 3 to 7 (this commit). Buys runway for slow-progress cycles but doesn't fix the underlying class of bug — any loop with a long check↔work tail that uses `next:` for the work state is still vulnerable, and the threshold is necessarily a guess.

## Acceptance Criteria

- [ ] Stall detector does not fire when a state with unconditional `next:` made observable file-level changes between two consecutive identical verdicts of an eval-bearing state.
- [ ] A `general-task` run with ~15 unchecked DoD criteria iterates at least 10 `check_done` cycles without stalling, provided `continue_work` writes to the plan or DoD file each cycle.
- [ ] Stall detector still fires within `window` cycles for a genuine no-progress loop (same verdict, zero file changes between cycles).
- [ ] Existing loops that don't opt into progress tracking retain current detector semantics (no regression in `scripts/tests/test_stall_detector.py`).

## Impact

- **Priority**: P2 — False-positive stall fires kill productive loops prematurely; directly observed in `general-task`; affects any loop with `next:`-only work states
- **Effort**: Medium — Well-defined Option A; touches 3 files (schema, executor, stall_detector) plus loop YAML and tests; no novel patterns required
- **Risk**: Medium — Changes FSM executor and stall detector core; Option A is opt-in so existing loops without `progress_paths` are unaffected; regression risk bounded to `test_stall_detector.py`
- **Breaking Change**: No (opt-in `progress_paths` field; default behavior preserved)

## Labels

`stall-detector`, `fsm`, `executor`, `false-positive`

## Notes

- Related: BUG-1657 (general-task evaluate prompt simplification) — different bug, same loop.
- Related: FEAT-1637 (original stall detector).
- The downstream issue's "raise stall threshold" proposal is the workaround, not the fix. The "task should be scoped narrowly enough that DoD gap closes within ~3 cycles" proposal is unworkable for general-purpose loops that take arbitrary task input.

---

**Done** | Created: 2026-05-24 | Priority: P2

## Resolution

Implemented Option A (fingerprint-based reset). Added `progress_paths: list[str]` to `RepeatedFailureConfig`; the executor computes `(mtime, size)` fingerprints for those paths before each `record()` call and resets the window when any path changed since the previous record for that state. Reverted `general-task.yaml` `window` from 7 back to 3 and added `progress_paths` for the plan/DoD files. Existing loops without `progress_paths` are unaffected.


## Session Log
- `/ll:ready-issue` - 2026-05-24T09:19:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2166d25c-ed32-456a-bb5f-11bf12e192e7.jsonl`
- `/ll:confidence-check` - 2026-05-24T08:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05261683-829a-4403-986e-27389bc47dbe.jsonl`
- `/ll:wire-issue` - 2026-05-24T07:44:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c3f102e7-8b1c-40a0-92c7-9fea7bc9a310.jsonl`
- `/ll:decide-issue` - 2026-05-24T07:35:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81b5e62d-c94a-4872-b49f-a5ea9e87a99a.jsonl`
- `/ll:refine-issue` - 2026-05-24T07:31:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2aaa4e23-87ed-4641-85ed-a9de682a4d82.jsonl`
- `/ll:refine-issue` - 2026-05-24T07:30:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0975e21a-7b1b-4a84-82ba-aee75195eb72.jsonl`
- `/ll:format-issue` - 2026-05-24T07:24:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4bd7f585-d3e7-44e3-81e4-3bd5de0cef5d.jsonl`
