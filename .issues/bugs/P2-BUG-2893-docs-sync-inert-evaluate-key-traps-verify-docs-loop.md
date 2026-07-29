---
id: BUG-2893
type: BUG
priority: P2
status: done
captured_at: '2026-07-28T22:13:33Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2894
- ENH-2895
- ENH-2896
depends_on:
- ENH-2895
completed_at: '2026-07-28T23:20:22Z'
---

# BUG-2893: docs-sync inert `evaluate.key` traps the loop in a verify_docs retry cycle

## Summary

`docs-sync.yaml`'s `check_findings` state declares `evaluate.key: remaining_findings`
on an `output_numeric` evaluator. `EvaluateConfig` has no `key` field, so the value is
silently discarded at load time and `evaluate_output_numeric` runs
`float(output.strip())` against the entire stdout line — which is `remaining_findings=0`,
not `0`. The parse fails, the evaluator returns `verdict="error"`, and the state's
`on_error: verify_docs` routes execution back into the verify state.

Unlike the sibling occurrence in `oracles/code-run-gate.yaml` (BUG-2894), this one is
**not benign**: `on_yes`, `on_no`, and `on_error` all have different targets, so the
permanent `error` verdict means the `yes`/`no` branches are unreachable.

## Current Behavior

`scripts/little_loops/loops/docs-sync.yaml` — `check_findings` state:

```yaml
      echo "remaining_findings=$((NON_AUTO + LINK_EXIT))"
    capture: remaining_findings
    evaluate:
      type: output_numeric
      key: remaining_findings      # <-- silently dropped by EvaluateConfig.from_dict
      operator: "eq"
      target: 0
    on_yes: commit
    on_no: report_findings
    on_error: verify_docs
```

Every invocation:

1. stdout is `remaining_findings=0` (or `remaining_findings=3`, etc.)
2. `evaluate_output_numeric` (`scripts/little_loops/fsm/evaluators.py`, `float(output.strip())`)
   raises `ValueError` → `EvaluationResult(verdict="error")`
3. routing takes `on_error: verify_docs`
4. `verify_docs` runs again, reaches `check_findings` again, fails identically

The loop cycles between `verify_docs` and `check_findings` until `max_steps` is
exhausted. `commit` is never reached on a clean run, and `report_findings` is never
reached on a dirty one — so the loop neither commits clean docs nor reports drift.

Additionally, `capture: remaining_findings` captures the whole `key=value` blob rather
than the numeric field, so any downstream `${captured.remaining_findings.output}`
reference is also the raw string.

## Expected Behavior

`check_findings` extracts the numeric value `0` from the output, compares it to
`target: 0` with `operator: eq`, and routes to `commit` on a clean verify or
`report_findings` when drift remains. `on_error` is reserved for genuine evaluation
failures, not the normal path.

## Motivation

`docs-sync` is a built-in loop shipped to every consuming project. In its current state
it burns its full `max_steps` budget re-running `ll-verify-docs` and `ll-check-links`
on every run and then terminates without performing either of its two terminal actions.
Users see a loop that "runs" and produces no commit and no findings report — a silent
failure that looks like "no drift found."

Because little-loops is installed `local-editable` across every project on this machine,
the broken loop is live everywhere, not just here.

## Root Cause

`EvaluateConfig.from_dict` (`scripts/little_loops/fsm/schema.py`) constructs the
dataclass by enumerating known fields with `data.get(...)`. Keys not in that enumeration
are discarded with no error, no warning, and no `ll-loop validate` diagnostic. `key` is
one such key. See ENH-2896 for the systemic fix and ENH-2895 for implementing `key`
itself.

## Proposed Solution

Contingent on ENH-2895 (implement `evaluate.key` on `output_numeric`):

- **If ENH-2895 lands**: no change needed to `docs-sync.yaml` — the existing YAML
  becomes correct as written.
- **If ENH-2895 is declined**: change the shell to emit a bare number and drop `key:`:

  ```yaml
        echo "$((NON_AUTO + LINK_EXIT))"
      evaluate:
        type: output_numeric
        operator: "eq"
        target: 0
  ```

  Note this loses the self-describing output in the run log; consider writing the
  labelled form to a `${context.run_dir}/` artifact and echoing only the number.

Either way, add a regression test asserting `check_findings` yields `yes` on a clean
verify rather than `error`.

## Integration Map

- `scripts/little_loops/loops/docs-sync.yaml` — `check_findings` state
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_numeric`
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig`
- `scripts/tests/test_builtin_loops.py` — regression coverage

## Implementation Steps

1. Reproduce: run the `check_findings` evaluator against literal stdout
   `remaining_findings=0` and assert the current verdict is `error`.
2. Resolve the dependency on ENH-2895 (implement `key`) vs. the bare-number fallback.
3. Apply the chosen fix to `docs-sync.yaml`.
4. Fix `capture:` so downstream references get the numeric value, not the blob.
5. Add a test asserting clean-verify → `yes` → `commit` and dirty-verify → `no` →
   `report_findings`.
6. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: High for the loop's users — `docs-sync` silently performs neither of its
  terminal actions.
- **Blast radius**: One built-in loop, live in every `local-editable` consuming project.
- **Risk of fix**: Low; the change is confined to one state's evaluator wiring.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM evaluator dispatch and routing semantics |
| `docs/reference/API.md` | `little_loops.fsm.evaluators` reference |
| `.claude/CLAUDE.md` | Loop Authoring rules; `ll-loop validate` gate table |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-28T23:20:23 - `c53b272d-061d-4930-bc4e-fede59dd7ae2.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T22:30:33 - `0c009821-2287-4712-ab12-876baba4cf48.jsonl`
- `/ll:verify-issues` - 2026-07-28T22:25:20 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Status

open

---

## Resolution

- **Completed**: 2026-07-28
- **Reason**: Fixed by commit `e2ea3c56` (ENH-2895), confirmed by
  `/ll:audit-issue-conflicts`
- **Proposed change**: This issue's own stated branch was taken verbatim — *"If
  ENH-2895 lands: no change needed to `docs-sync.yaml` — the existing YAML
  becomes correct as written."* `EvaluateConfig.key` now exists
  (`fsm/schema.py`), is wired through `from_dict`, and `evaluate_output_numeric`
  extracts it by regex. Verified live against this loop's exact stdout:
  `evaluate_output_numeric('remaining_findings=0', 'eq', 0, key='remaining_findings')`
  returns `verdict='yes'` — the reported failure no longer reproduces.

  The regression test this issue asked for is **already present**:
  `scripts/tests/test_builtin_loops.py::test_route_results_key_dispatches_correctly`
  asserts `config.key == "remaining_findings"`, `yes` on `remaining_findings=0`,
  and `no` on `remaining_findings=2`.

  Note for the record: this issue named the state `check_findings`; the actual
  state at `scripts/little_loops/loops/docs-sync.yaml:45` is `route_results`.
  The quoted `evaluate:` block was otherwise verbatim.
