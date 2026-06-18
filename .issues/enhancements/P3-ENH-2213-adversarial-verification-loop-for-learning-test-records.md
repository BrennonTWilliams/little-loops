---
id: ENH-2213
title: Adversarial verification loop for learning test records
type: enhancement
priority: P3
status: cancelled
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2213: Adversarial verification loop for learning test records

## Summary

Learning test records are written once and trusted indefinitely (until stale by age). A flawed proof script can produce a `proven` record with incorrect assertions. Add a `verify-learning-test` FSM loop that independently attempts to refute each `pass` assertion in a record by writing a second proof script from scratch and comparing results — following the adversarial verification pattern from CLAUDE.md.

## Current Behavior

Learning test records are written once and trusted indefinitely (until stale by age). A flawed proof script can produce a `proven` record with incorrect assertions, and there is no mechanism to independently verify these assertions remain valid between captures.

## Expected Behavior

A `verify-learning-test` FSM loop should independently attempt to refute each `pass` assertion in a learning test record by spawning a separate agent to write a proof script from scratch and comparing results. A claim that survives two independent scripts is more trustworthy than one proven once. The loop should output `verified` for surviving assertions and downgrade refuted claims to `fail`, calling `ll-learning-tests mark-stale` to update the record accordingly.

## Motivation

The same SHOR-derived concern that applies to meta-loops (self-evaluation bias) applies here: the original proof script and the original assertion were written by the same agent in the same session. An independent refuter with no access to the original script surfaces disagreements. A claim that survives two independent scripts is more trustworthy than one proven once.

## Proposed Solution

Create `loops/verify-learning-test.yaml` following the adversarial verification pattern from CLAUDE.md. The loop loads a learning test record, filters for `pass` assertions, spawns independent LLM agents to write refutation proof scripts, tallies verdicts, and updates the record.

Key components:
1. **FSM loop** at `loops/verify-learning-test.yaml` with states: `load_record`, `filter_pass`, `refute`, `tally`, `update_record`, `report`
2. **Schema update** — add `verified` as an optional `result` value in `Assertion` (alongside `pass`/`fail`/`untested`) to distinguish original-proof from adversarially-verified
3. **CLI wrapper** — `ll-learning-tests verify "<target>"` as a convenience wrapper around `ll-loop run verify-learning-test`

## Implementation Steps

1. Create `loops/verify-learning-test.yaml` with states:
   - `load_record`: shell — run `ll-learning-tests check "$TARGET"`, parse JSON assertions
   - `filter_pass`: shell — extract only `result: pass` assertions into a list
   - `refute`: for each assertion, spawn an LLM agent prompted to "Write a minimal proof script that would DISPROVE this claim about <TARGET>. Run it and report whether the claim held or was refuted."
   - `tally`: aggregate verdicts — if ≥2 of 3 refuters find the claim holds, mark `verified`; if ≥2 refute, downgrade to `fail` and update the record
   - `update_record`: shell — call `ll-learning-tests mark-stale` if any claim was downgraded; write updated assertion results to the record file
   - `report`: emit a summary
2. Wire `verified` as a new optional `result` value in `Assertion` (alongside `pass`/`fail`/`untested`) to distinguish original-proof from adversarially-verified.
3. Add `ll-learning-tests verify "<target>"` as a convenience wrapper around `ll-loop run verify-learning-test`.

## Integration Map

### Files to Modify
- `loops/verify-learning-test.yaml` — New FSM loop definition
- `scripts/little_loops/cli/learning_tests.py` — Add `verify` subcommand to `ll-learning-tests`
- `scripts/little_loops/learning_tests/` — Update assertion schema with `verified` result value

### Dependent Files (Callers/Importers)
- TBD — use grep to find references to `ll-learning-tests` or assertion result schema

### Similar Patterns
- Existing loop YAMLs under `loops/` follow the same state-machine pattern
- `ll-loop run` used by other learning-test loops

### Tests
- TBD — add tests for `verify-learning-test` loop
- TBD — update assertion schema tests with `verified` value

### Documentation
- `docs/reference/API.md` — add `ll-learning-tests verify` to CLI reference

### Configuration
- N/A

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2211 (debt marker) and ENH-2212 (install hook). Key lifecycle separation:

- ENH-2211 writes to issue frontmatter `learning_tests_required` only — it does NOT create `LearningTestRecord` objects. The verification loop here operates on registry records only, not on frontmatter fields.
- The `verified` result value added by this issue must be recognized by ENH-2212's registry query so adversarially-verified records are treated as proven (suppressing install nudges). See [[ENH-2211]] and [[ENH-2212]] for the hook-layer integration.

## Acceptance Signals

- Running the loop on a record with a correct `pass` assertion produces `verified` result
- Running it on a deliberately wrong proof produces a `fail` downgrade and `mark-stale` call
- The loop validates cleanly with `ll-loop validate`
- MR-1: paired non-LLM evaluator (exit_code from the refuter scripts) alongside the LLM judge

## Success Metrics

- Correct `pass` assertions survive adversarial verification → `verified` result
- Deliberately wrong proofs get downgraded → `fail` result + `mark-stale` call
- Loop validates cleanly with `ll-loop validate`

## Scope Boundaries

- **In scope**: Creating the `verify-learning-test` FSM loop, adding `verified` result value to `Assertion` schema, adding `ll-learning-tests verify` convenience wrapper
- **Out of scope**: Bulk re-verification of all existing learning test records, changes to the capture workflow, changes to how learning tests are discovered or created

## API/Interface

- New result value `verified` added to `Assertion` schema (alongside `pass`, `fail`, `untested`)
- New CLI command: `ll-learning-tests verify "<target>"` wraps `ll-loop run verify-learning-test`

## Impact

- **Priority**: P3 — Important for trust in learning test records but not blocking current development
- **Effort**: Medium — New FSM loop YAML, schema update, and CLI wrapper
- **Risk**: Low — Fully additive; no changes to existing records or capture workflows
- **Breaking Change**: No — Existing `pass`/`fail`/`untested` results remain valid; `verified` is optional

## Labels

`enhancement`, `captured`, `adversarial-verification`, `learning-tests`

**Open** | Created: 2026-06-18 | Priority: P3

## Cancellation Note

Cancelled per EPIC-2207 scoping review. Learning tests are validated by real code execution, not LLM judgment — the proof script runs and produces observable results. A flawed proof script is caught by re-execution (which stale detection already covers). Spawning 3 LLM refuters per assertion has the same failure mode as the original proof script (SHOR applies to refuters too). The `verified` result value would add schema complexity for marginal trust gain. See EPIC-2207 for rationale.

## Session Log
- `/ll:format-issue` - 2026-06-18T19:32:30 - `5a588f07-44ea-456b-a878-a98a2d1afc07.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
