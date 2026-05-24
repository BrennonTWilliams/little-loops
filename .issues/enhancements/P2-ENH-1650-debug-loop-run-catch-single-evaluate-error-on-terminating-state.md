---
id: ENH-1650
type: enhancement
priority: P2
status: open
captured_at: "2026-05-23T23:20:27Z"
discovered_date: "2026-05-23"
discovered_by: capture-issue
component: skills/debug-loop-run
labels: [debug-loop-run, signal-rules, fsm, evaluate]
relates_to: [ENH-1655]
---

# ENH-1650: debug-loop-run misses single evaluate-error that terminates the loop

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

### Dependent Files (Callers/Importers)
- N/A — SKILL.md is invoked by Claude Code via `/ll:debug-loop-run`; not imported by Python modules.

### Similar Patterns
- Existing signal rules in `skills/debug-loop-run/SKILL.md` (FATAL_ERROR at lines 181-184, Evaluate failure at lines 286-291, Action failure) — keep formatting and field ordering consistent.
- "Multiple signals on same state" precedence note (`skills/debug-loop-run/SKILL.md:299-301`) — extend with new rule's precedence over FATAL_ERROR.

### Tests
- `scripts/tests/test_debug_loop_run_synthesis.py` — add fixtures for: (a) single terminating evaluate-error, (b) terminated_by=error with no evaluate-error present. Assert new signal emitted in case (a) and FATAL_ERROR remains in case (b).

### Documentation
- `docs/ARCHITECTURE.md` — cross-check verdict enum reference (`pass | fail | continue | retry | error`) stays accurate; no expected change.

### Configuration
- N/A.

## Related Key Documentation

| Path | Why |
|------|-----|
| `skills/debug-loop-run/SKILL.md` | Skill being modified; rules added under "### Signal Rules". |
| `scripts/tests/test_debug_loop_run_synthesis.py` | Where fixture-based signal tests live (referenced at `skills/debug-loop-run/SKILL.md:174`). |
| `docs/ARCHITECTURE.md` | FSM evaluator verdict semantics (cross-check the `pass/fail/continue/retry/error` enum stays accurate). |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:format-issue` - 2026-05-23T23:24:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fb32199-4c7e-45f4-9a40-75be401d19e7.jsonl`
- `/ll:capture-issue` - 2026-05-23T23:20:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d302e094-e886-4f1c-9e6a-9cb4dda50f7a.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1655 (evaluate retry before termination) reduces the frequency of the event this issue detects. ENH-1650 remains valid even after ENH-1655 ships — the single evaluate-error termination can still occur for exhausted retries and non-retryable error paths. Sequence ENH-1655 before or alongside ENH-1650.
