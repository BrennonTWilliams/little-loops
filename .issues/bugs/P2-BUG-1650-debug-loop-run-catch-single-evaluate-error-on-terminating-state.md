---
id: BUG-1650
type: enhancement
priority: P2
status: done
captured_at: '2026-05-23T23:20:27Z'
completed_at: '2026-05-24T13:43:15Z'
discovered_date: '2026-05-23'
discovered_by: capture-issue
component: skills/debug-loop-run
labels:
- debug-loop-run
- signal-rules
- fsm
- evaluate
relates_to:
- ENH-1655
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1650: debug-loop-run misses single evaluate-error that terminates the loop

## Summary

`/ll:debug-loop-run` does not classify an `evaluate` event with `verdict == "error"` as a fault signal when it occurs on a state whose error path terminates the loop (or when its propagation causes the run to end). The existing rules either require multiple occurrences or only key off the terminal `loop_complete` payload, leaving the actual cause un-cited in the synthesized report.

## Current Behavior

A single `evaluate.verdict == "error"` event that terminates the loop falls through every existing signal rule in `skills/debug-loop-run/SKILL.md`:

- **Evaluate failure** keys on `verdict == "fail"` AND requires ≥3 occurrences on the same state.
- **FATAL_ERROR termination** fires on `loop_complete.terminated_by == "error"` but cites only the final state — it does not surface the evaluator or its `reason`.
- **Action failure** keys off `action_complete.exit_code`, not evaluator verdicts.

Result: the synthesized BUG reports `"<loop> terminated with error in <final_state>"` and an investigator must re-read the raw JSONL to discover that an evaluate-error was the proximate cause.

## Expected Behavior

When a single `evaluate.verdict == "error"` event is followed by `loop_complete`, `/ll:debug-loop-run` emits a P2 fault signal that:

- Names the failing state and includes the evaluator's `reason` field.
- Fires on the first occurrence (no occurrence threshold).
- Supersedes the generic FATAL_ERROR signal for the same `loop_complete` (de-duplicated — the new signal is strictly more informative).
- Leaves FATAL_ERROR coverage unchanged for non-evaluator termination paths.

## Motivation

The verdict enum documented at `skills/debug-loop-run/SKILL.md:145` is `pass | fail | continue | retry | error`. Today:

- **BUG — Evaluate failure** (`skills/debug-loop-run/SKILL.md:286-291`) only triggers on `verdict == "fail"` AND requires **3 or more occurrences** on the same state.
- **BUG — FATAL_ERROR termination** (`skills/debug-loop-run/SKILL.md:181-184`) triggers on `loop_complete.terminated_by == "error"` but says nothing about which state's evaluator produced the error.
- **BUG — Action failure** keys off `action_complete.exit_code`, not evaluator verdicts.

The `evaluate` → `verdict == "error"` case (typically an evaluator raising, an LLM judge returning unparseable output, or a `script` evaluator crashing) falls through all three rules when it happens just once. The run terminates, FATAL_ERROR fires, and the synthesized BUG cites only "<loop> terminated with error in <final_state>" — investigators must then re-read the JSONL to discover the evaluate-error was the trigger.

**Why:** signal rules exist precisely so a human or downstream automation does not need to re-read raw event logs to identify the proximate cause. A single terminating evaluate-error is high-signal (terminations are rare) and should never be suppressed by an occurrence threshold tuned for noisy failure modes.

## Proposed Solution

Add a new signal rule (preferred — keeps FATAL_ERROR as the loop-level catch-all and gives evaluate-error its own pinpointed signal), or expand the FATAL_ERROR rule to enrich it with the evaluator context. Recommend **new rule** so the report can cite both: the loop terminated AND the specific evaluate-error that caused it.

### New rule sketch

#### BUG — Evaluate error terminated the loop
- **Class**: Fault signal (terminal-event handler).
- **Trigger**: any `evaluate` event with `verdict == "error"` that is followed by `loop_complete` (with or without intervening events) AND has no `retry`/recovery path that visits a non-error state in between — **emit on the first occurrence** (no occurrence threshold).
  - Practically: scan the event list; if the last `evaluate` before `loop_complete` has `verdict == "error"`, fire. Optionally also fire when `terminated_by` is `"error"` AND any `evaluate.verdict == "error"` exists in the run, attributing the termination to that evaluator.
- **Priority**: P2 (matches FATAL_ERROR severity — a terminating evaluator error is at least as serious as an action exit code anomaly).
- **Title**: `"<state> evaluator returned error and terminated <loop_name> loop (verdict=error)"`
- **Include**: state name, `reason` field from the failing `evaluate` payload, `final_state`, `iterations`, last 5 events before `loop_complete`.
- **Rationale**: an evaluator raising on its first attempt should never be silenced by an occurrence threshold — it represents either a bug in the evaluator (script crash, schema mismatch) or a malformed action output that the evaluator cannot parse. Both warrant immediate investigation; both are obscured today.

### De-duplication

If both this new rule AND the existing FATAL_ERROR rule fire on the same `loop_complete`, emit only the new rule (it is strictly more informative — it cites the specific evaluator). Mirror the existing "Multiple signals on same state" precedence note at `skills/debug-loop-run/SKILL.md:299-301`.

## Implementation Steps

1. In `skills/debug-loop-run/SKILL.md`, add the new signal rule under "### Signal Rules" near the existing FATAL_ERROR / Evaluate failure rules.
2. Update the "Multiple signals on same state" subsection (`skills/debug-loop-run/SKILL.md:299-301`) to add the FATAL_ERROR ↔ Evaluate-error precedence.
3. Update the Fault Signals bucket description (`skills/debug-loop-run/SKILL.md:423`) and the classification table (`skills/debug-loop-run/SKILL.md:483`) to include "evaluate error termination".
4. Update the `signal_type` enum line (`skills/debug-loop-run/SKILL.md:514`) to add `eval_error_termination` (or similar) alongside `fatal_error`, `eval_failure`.
5. Add or extend a synthesis test under `scripts/tests/test_debug_loop_run_synthesis.py` with a fixture JSONL containing a single terminating `evaluate.verdict=="error"` and assert that the new signal is emitted with the expected fields.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/COMMANDS.md` — add `evaluate.verdict == "error"` → BUG P2 to the `_Fault Signals (BUG-class):_` bullet list in the `### /ll:debug-loop-run` section
7. Update `skills/audit-loop-run/SKILL.md` — add `eval_error_termination` (single-occurrence terminating evaluate-error) to the `## Step 5: Phase 1 — Fault Signals` enumerated bullet list; distinguish from existing "Evaluate failures" which covers `verdict == "fail"` 3+ times
8. Update `scripts/tests/test_debug_loop_run_synthesis.py:TestAnalyzeLoopSynthesis.test_step5_fault_effectiveness_grouping_assigns_signal3_to_effectiveness` — add `"eval_error_termination"` to the `fault_signals` set (~line 560)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`reason` vs `error` field in evaluate events** (`executor.py:1112–1119`, `evaluators.py`):
The SKILL.md event table (line 145) lists `reason` as the optional field, but real `verdict == "error"` events emit an `error` field instead — e.g. `{"verdict": "error", "error": "Failed to parse LLM response: ..."}`. The `reason` field is only present on `llm_structured` evaluators returning `yes/no/blocked/partial` verdicts. The "Include" line in the rule sketch and the signal shape in `## API/Interface` should capture `error` if present, falling back to `reason`:
```yaml
reason: <evaluate.error or evaluate.reason from failing event>
```

**`terminated_by` independence** (confirmed from `.loops/.history/general-task/2026-03-17T213110/events.jsonl`):
A real run shows `evaluate.verdict == "error"` → routing to a `failed` terminal state → `loop_complete.terminated_by == "terminal"`. The new signal must fire regardless of `terminated_by` value. De-duplication against FATAL_ERROR only applies when both `terminated_by == "error"` AND `evaluate.verdict == "error"` hold simultaneously — when `terminated_by == "terminal"`, FATAL_ERROR never fires and no de-duplication is needed.

**Line number corrections** (verified against `skills/debug-loop-run/SKILL.md`):
- FATAL_ERROR rule: lines **181–185** (Implementation Step 3 cites 181–184)
- Evaluate failure rule: lines **287–291** (Implementation Step 1 cites 286–291)
- "Multiple signals on same state": lines **300–301** (accurate)
- Fault Signals bucket description: **line 424** (cited as ~423)
- Classification table: **lines 482–486** (accurate)
- `signal_type` enum: **line 515** inside the fenced code block (cited as 514)

**Test approach** (`scripts/tests/test_debug_loop_run_synthesis.py`):
The test file validates FSM YAML **structural preconditions** using YAML spec fixtures — it does not parse JSONL event streams. There is no Python signal-detection code to unit-test (debug-loop-run is SKILL.md only). Appropriate additions are **inline discriminator tests** (Pattern C from the file — e.g. `test_3b5_inline_dominant_share_meets_threshold`):

```python
# Scenario (a): last evaluate before loop_complete has verdict=="error" → new signal fires
def test_eval_error_termination_inline_fires_on_last_eval_error(self) -> None:
    events = [
        {"event": "evaluate", "state": "check", "verdict": "error", "error": "parse failed"},
        {"event": "loop_complete", "terminated_by": "terminal"},
    ]
    last_eval = next((e for e in reversed(events) if e.get("event") == "evaluate"), None)
    assert last_eval is not None and last_eval.get("verdict") == "error"

# Scenario (b): terminated_by="error" with no evaluate event → FATAL_ERROR fires, new signal absent
def test_eval_error_termination_inline_no_eval_no_new_signal(self) -> None:
    events = [{"event": "loop_complete", "terminated_by": "error"}]
    last_eval = next((e for e in reversed(events) if e.get("event") == "evaluate"), None)
    assert last_eval is None  # FATAL_ERROR path — no evaluate event present
```

An optional FSM YAML fixture (`analysis-eval-error-terminates.yaml`) with `on_error: failed` routing to a terminal state can document the structural pattern that produces this runtime event, but the inline discriminator tests above are the primary test coverage.

## Acceptance Criteria

- [ ] A run whose only fault is a single `evaluate.verdict == "error"` event immediately followed by `loop_complete` produces a P2 BUG signal that names the failing state and includes the `reason` field.
- [ ] The new rule fires on a single occurrence (no 3-occurrence threshold).
- [ ] When the new rule fires, the report does not also emit a duplicate FATAL_ERROR-only entry for the same `loop_complete`.
- [ ] Existing FATAL_ERROR coverage for non-evaluator termination paths (e.g. action raising → terminated_by=error with no evaluate.verdict=="error") is unchanged.
- [ ] Test fixture exercises both: (a) single terminating evaluate-error, (b) terminated_by=error with no evaluate-error present.

## Scope Boundaries

- **Out of scope**: changing the evaluator verdict enum (`pass | fail | continue | retry | error`) or how evaluators emit verdicts.
- **Out of scope**: non-terminating evaluate-errors — only the *terminating* evaluate-error case is covered here. Repeated non-terminating errors remain in the noise floor.
- **Out of scope**: action-exit-code-based terminations (already covered by the existing Action failure rule).
- **Out of scope**: retroactive re-analysis of historical JSONLs; rule applies to runs analyzed after the change lands.

## API/Interface

Extends the `signal_type` enum surfaced in `/ll:debug-loop-run` reports (declared at `skills/debug-loop-run/SKILL.md:514`):

```
signal_type ∈ {fatal_error, eval_failure, ..., eval_error_termination}
```

New signal shape (informal):

```yaml
signal_type: eval_error_termination
priority: P2
state: <failing_state_name>
reason: <evaluate.reason from failing event>
final_state: <loop_complete.final_state>
iterations: <loop_complete.iterations>
recent_events: <last 5 events before loop_complete>
```

No CLI argument or Python function signature changes — this is a report payload extension only.

## Impact

- **Priority**: P2 — Improves report accuracy for a rare but high-signal failure mode (terminating evaluator error). Not blocking, high-value when it triggers.
- **Effort**: Small — Single signal rule added to one SKILL.md file plus one synthesis test fixture; no runtime/code changes outside tests.
- **Risk**: Low — Additive rule with explicit de-duplication against FATAL_ERROR; existing rule behavior preserved for non-evaluator terminations.
- **Breaking Change**: No — new enum value is additive; downstream consumers reading `signal_type` should already tolerate unknown values.

## Integration Map

### Files to Modify
- `skills/debug-loop-run/SKILL.md` — new signal rule + de-duplication note + enum line + classification table update.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:debug-loop-run` Fault Signals bullet list; add the new signal rule (`evaluate.verdict == "error"` → terminating → BUG P2) [Agent 2 finding]
- `skills/audit-loop-run/SKILL.md` — `## Step 5: Phase 1 — Fault Signals` enumerated fault subset bullet list; add `eval_error_termination` alongside "Evaluate failures" (different semantics: single-occurrence terminating, not 3+ occurrences of `verdict == "fail"`) [Agent 2 finding]

### Dependent Files (Callers/Importers)
- N/A — SKILL.md is invoked by Claude Code via `/ll:debug-loop-run`; not imported by Python modules.

### Similar Patterns
- Existing signal rules in `skills/debug-loop-run/SKILL.md` (FATAL_ERROR at lines 181-184, Evaluate failure at lines 286-291, Action failure) — keep formatting and field ordering consistent.
- "Multiple signals on same state" precedence note (`skills/debug-loop-run/SKILL.md:299-301`) — extend with new rule's precedence over FATAL_ERROR.

### Tests
- `scripts/tests/test_debug_loop_run_synthesis.py` — add fixtures for: (a) single terminating evaluate-error, (b) terminated_by=error with no evaluate-error present. Assert new signal emitted in case (a) and FATAL_ERROR remains in case (b).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_debug_loop_run_synthesis.py:TestAnalyzeLoopSynthesis.test_step5_fault_effectiveness_grouping_assigns_signal3_to_effectiveness` — update existing test: the `fault_signals` set on ~line 560 must include `"eval_error_termination"` alongside `"fatal_error"`, `"evaluate_failure"`, etc. Test will not break without it, but the set is the canonical in-test enumeration of fault-class signal types [Agent 2 + 3 finding]
- New test method: `test_eval_error_termination_inline_fires_on_last_eval_error` in `TestAnalyzeLoopSynthesis` — Pattern B inline discriminator; event list with `evaluate.verdict=="error"` followed by `loop_complete`; asserts last evaluate before `loop_complete` has `verdict == "error"` [Agent 3 finding]
- New test method: `test_eval_error_termination_inline_no_eval_no_new_signal` in `TestAnalyzeLoopSynthesis` — Pattern B inline discriminator; event list with only `loop_complete(terminated_by="error")` and no evaluate event; asserts `last_eval is None` (FATAL_ERROR path, no new signal) [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — cross-check verdict enum reference (`pass | fail | continue | retry | error`) stays accurate; no expected change.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:debug-loop-run` section; `_Fault Signals (BUG-class — broke the run):_` bullet list must be updated to show the new signal (moved to "Files to Modify" since it requires an edit) [Agent 1 + 2 finding]

### Configuration
- N/A.

## Related Key Documentation

| Path | Why |
|------|-----|
| `skills/debug-loop-run/SKILL.md` | Skill being modified; rules added under "### Signal Rules". |
| `scripts/tests/test_debug_loop_run_synthesis.py` | Where fixture-based signal tests live (referenced at `skills/debug-loop-run/SKILL.md:174`). |
| `docs/ARCHITECTURE.md` | FSM evaluator verdict semantics (cross-check the `pass/fail/continue/retry/error` enum stays accurate). |

## Resolution

Added `BUG — Evaluate error terminated the loop` signal rule to `skills/debug-loop-run/SKILL.md`. The new rule fires on the first occurrence when the last `evaluate` before `loop_complete` has `verdict == "error"`, uses the `error` field (falling back to `reason`), and de-duplicates against FATAL_ERROR when both would fire. Updated FATAL_ERROR rule to clarify it is the non-evaluator catch-all. Extended "Multiple signals on same state" with the FATAL_ERROR/eval_error_termination precedence. Updated `signal_type` enum, Step 5 Fault Signals bucket description, and Step 6b classification table. Propagated `eval_error_termination` to `docs/reference/COMMANDS.md` and `skills/audit-loop-run/SKILL.md`. Added two inline discriminator tests and `eval_error_termination` to the `fault_signals` enumeration in `test_debug_loop_run_synthesis.py`.

## Session Log
- `/ll:ready-issue` - 2026-05-24T13:41:02 - `17fc3a37-e9af-4753-a16b-8ad8164f5f05.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `b77b78b1-4efc-4fe8-86cb-a9d75fd27e45.jsonl`
- `/ll:wire-issue` - 2026-05-24T13:36:00 - `73097563-3366-47c7-ad17-c2ae7263a6e6.jsonl`
- `/ll:refine-issue` - 2026-05-24T13:31:18 - `0a6cb46e-058a-4445-a65f-2a50af9c1288.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:format-issue` - 2026-05-23T23:24:02 - `4fb32199-4c7e-45f4-9a40-75be401d19e7.jsonl`
- `/ll:capture-issue` - 2026-05-23T23:20:27Z - `d302e094-e886-4f1c-9e6a-9cb4dda50f7a.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1655 (evaluate retry before termination) reduces the frequency of the event this issue detects. ENH-1650 remains valid even after ENH-1655 ships — the single evaluate-error termination can still occur for exhausted retries and non-retryable error paths. Sequence ENH-1655 before or alongside ENH-1650.
