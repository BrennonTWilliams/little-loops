---
id: BUG-2812
type: BUG
priority: P1
status: open
captured_at: '2026-07-25T22:08:07Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [fsm, loops, validator, interpolation]
---

# BUG-2812: Three built-in loops crash on the sub-loop capture namespace (`captured.<var>` vs `captured.<state>.<var>`)

## Summary

Three built-in FSM loops — `integrate-sdk`, `adopt-third-party-api`, and
`proof-first-task` — reference sub-loop captures at the wrong namespace path and
abort the entire run with `InterpolationError`. Two of the three suppressed the
validator rule that would have caught it via `capture_reachability_ok: true`.
Empirically reproduced against the installed `little_loops.fsm.interpolation`
module (audit §1.6, `thoughts/builtin-loops-audit-2026-07-24.md`).

## Current Behavior

Executor facts (verified at source):

- A child loop's captures merge into the parent **under the parent state's
  name**: `self.captured[self.current_state] = child_executor.captured`
  (`fsm/executor.py:1008-1010`) — and only when the state sets
  `context_passthrough` / `with:`. They are **never flattened**.
- A sub-loop state's own `capture:` key stores the child's **event stream** as
  `{"output": <jsonl>, "exit_code": None}` (`fsm/executor.py:1000-1006`) — not
  the child's captures.
- A missing `${captured.*}` path with no `:default=` raises `InterpolationError`,
  which aborts the run as `terminated_by="error"` (`fsm/executor.py:788-795`).

Three loops get this wrong (all reproduced with `RAISES: Path ... not found in captured`):

| Loop | Site | Bug |
|---|---|---|
| `integrate-sdk` | `:145` — `PROVEN SURFACES: ${captured.targets.output}` | Real path is `captured.prove.targets.output`. Crashes the **success path of every run**, right after the oracle succeeds. The header comment (`:14-17`, attributed to ENH-2748) claims the sub-loop "injects" a flat `targets` capture — factually wrong per `executor.py:1008-1010` — and `capture_reachability_ok: true` (`:17`) silences the rule. (`:202-203` survive only because they carry `:default=not-reached`.) |
| `adopt-third-party-api` | `:81` and `:110` — `${captured.enumeration.output}` | Same defect on **both** post-oracle branches (success and partial); real path is `captured.prove.enumeration.output`. Suppressed by `capture_reachability_ok: true` at `:11`. Loop is unusable beyond enumeration. |
| `proof-first-task` | `:54` — `${captured.gate_result.extracted.output}` | `gate_result` is the `gate` state's own `capture:` — the event-stream dict with only `output`/`exit_code` keys — while assumption-firewall's `extracted` capture lands at `captured.gate.extracted`. Crashes the **`on_failure` branch the state exists to discriminate**; whenever the firewall reports failure the loop aborts `error`. Distinct from the known empty-task/`input_hash` bug. |

**Validator gap**: the capture-reachability rule checks only the *top-level*
captured variable name. `proof-first-task` passes it honestly (top-level
`gate_result` **is** captured); the other two suppressed it. Nested-path
correctness is checked nowhere.

## Expected Behavior

- All three loops resolve their sub-loop captures at the correct nested path and
  complete their success/failure branches without `InterpolationError`.
- The capture-reachability validator rule is nested-path-aware: it knows a
  sub-loop `capture:` value exposes only `output`/`exit_code`, and that merged
  child captures live under the parent **state name**.
- Every `capture_reachability_ok: true` suppression in the corpus carries a
  factually-true justifying comment.

## Root Cause

Author mental model treats sub-loop captures as flattened into the parent
namespace. The executor namespaces them under the invoking state's name
(`executor.py:1008-1010`), and the state's own `capture:` holds the child's
event stream rather than its captures (`:1000-1006`). The validator's
reachability rule only checks the top-level segment, so the nested-path error is
invisible — and where it would have fired, `capture_reachability_ok: true` was
set with an incorrect rationale.

The correct idiom already exists in-tree: `examples-miner.yaml:152` —
`${captured.run_optimizer.gradient.output}`.

## Proposed Solution

1. Correct the three references:
   - `integrate-sdk.yaml:145` → `${captured.prove.targets.output}`
   - `adopt-third-party-api.yaml:81,:110` → `${captured.prove.enumeration.output}`
   - `proof-first-task.yaml:54` → `${captured.gate.extracted.output}`
2. Remove/correct the false header comment at `integrate-sdk.yaml:14-17` and drop
   the now-unneeded `capture_reachability_ok: true` at `:17` and
   `adopt-third-party-api.yaml:11`.
3. Make the capture-reachability rule in `fsm/validation.py` nested-path-aware.
4. Audit all five loops carrying `capture_reachability_ok: true`
   (`adopt-third-party-api`, `autodev`, `examples-miner`, `goal-cluster`,
   `integrate-sdk`) — two of five were hiding real crashes.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/integrate-sdk.yaml`
- `scripts/little_loops/loops/adopt-third-party-api.yaml`
- `scripts/little_loops/loops/proof-first-task.yaml`
- `scripts/little_loops/fsm/validation.py` (capture-reachability rule)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:998-1010` (capture merge semantics — read-only reference)
- `scripts/little_loops/fsm/interpolation.py` (raise path)

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml:152` — correct idiom, use as the positive test fixture

### Tests
- `scripts/tests/test_builtin_loops.py` — add a nested-capture-path structural check
- New validator unit test: nested path against a sub-loop `capture:` (only `output`/`exit_code` valid)

### Documentation
- `docs/generalized-fsm-loop.md` — document the sub-loop capture namespace explicitly

### Configuration
- N/A

## Implementation Steps

1. Reproduce all three crashes (interpolation module, direct).
2. Fix the three YAML references; delete the two suppression flags.
3. Extend the capture-reachability rule to validate nested segments.
4. Re-run `ll-loop validate` across the corpus; confirm no new errors and that
   the previously-suppressed loops now pass honestly.
5. Add regression tests.

## Impact

- **Severity**: High — `integrate-sdk` and `adopt-third-party-api` crash on
  *every* successful run; `proof-first-task` (79 recorded runs) crashes on the
  discriminating failure branch.
- Two loops are effectively non-functional as shipped.
- The validator gap means the class can recur silently.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.6, §3.2, rec #1 | Source finding, reproduction trail |
| `docs/generalized-fsm-loop.md` | Authoring conventions to update |

## Steps to Reproduce

1. `ll-loop run integrate-sdk "<some sdk>"` — the run aborts
   `terminated_by="error"` immediately after the `prove` oracle succeeds.
2. Or reproduce directly against the interpolation module: build a `captured`
   dict shaped like the executor's post-sub-loop merge
   (`{"prove": {"targets": {...}}}`) and interpolate
   `${captured.targets.output}` → `InterpolationError: Path ... not found in
   captured`.
3. `adopt-third-party-api`: same, on both post-oracle branches (`:81`, `:110`).
4. `proof-first-task`: drive the `gate` state to an assumption-firewall
   *failure* so the `on_failure` branch at `:54` is taken → abort instead of the
   intended blocked/run_impl discrimination.

## Session Log
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
