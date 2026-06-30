---
id: ENH-2405
title: Learning gate re-extracts targets instead of proving the registered `learning_tests_required`
type: ENH
priority: P3
status: open
relates_to:
- EPIC-2207
- ENH-2209
- ENH-2319
- FEAT-1696
- FEAT-1738
captured_at: '2026-06-30T21:17:26Z'
discovered_date: '2026-06-30'
discovered_by: capture-issue
labels:
- learning-tests
- rn-remediate
- consistency
- efficiency
---

# ENH-2405: Learning gate re-extracts targets instead of proving the registered `learning_tests_required`

## Summary

ENH-2209 made `/ll:refine-issue` and `/ll:wire-issue` auto-populate the issue's
`learning_tests_required` frontmatter — the canonical list of external-API hypotheses to
prove before implementation. But the implement-time learning gate does **not** prove that
list. It uses `learning_tests_required` only as a boolean trigger guard and then
**re-extracts** an independent target list via the `assumption-firewall` LLM step. The
result is a redundant LLM extraction on every gated issue and a silent divergence risk: the
hypotheses an author/refinement registered are not necessarily the ones the gate proves.

## Current Behavior

In `process_issue_inplace` (`scripts/little_loops/issue_manager.py:854-869`):

```python
if config.learning_tests.enabled is True and not dry_run:
    targets = resolve_learning_targets(info)          # reads learning_tests_required frontmatter
    if targets:                                       # ← used only as a trigger guard
        verdict = run_learning_gate_for_issue(info.path, skip=skip_learning_gate, cwd=gate_cwd)
        ...
```

`targets` (the registered list from ENH-2209) gates **whether** the check runs, but is then
discarded — `run_learning_gate_for_issue` (`scripts/little_loops/learning_tests/gate.py:76-114`)
is passed `info.path`, not `targets`. It shells to `ll-loop run proof-first-task`, whose
`gate` state delegates to `assumption-firewall`, which **re-extracts** the external-API
assumption list from the raw issue text via its own `extract_assumptions` LLM step
(max 7) before delegating testable claims to `ready-to-implement-gate` (the `type: learning`
state that actually runs `/ll:explore-api`).

So the proof set is re-derived by a second, independent LLM call rather than read from the
frontmatter that refinement already wrote.

## Expected Behavior

When `learning_tests_required` is populated, the gate proves **exactly that list** and skips
the redundant `assumption-firewall` extraction. The registered hypotheses and the proven
hypotheses are guaranteed identical. LLM extraction at gate time runs only as a fallback when
the frontmatter field is absent (preserving the JIT path for un-refined issues, e.g.
BUG-2320 / ll-parallel).

Concretely: an issue with `learning_tests_required: ["stripe"]` whose body also happens to
mention `requests` in passing must have the gate prove **`stripe`** (the registered target),
not a freshly-extracted `["stripe", "requests"]`.

## Motivation

1. **Single source of truth.** ENH-2209 established `learning_tests_required` as the
   registry of an issue's hypotheses. A gate that re-derives its own list defeats that — the
   field becomes advisory rather than authoritative.
2. **Divergence risk.** Two independent LLM extractions over evolving issue text can disagree
   (different model, different prompt, the 7-target cap, body edited since refine). The gate
   can then prove a different set than what was registered/reviewed.
3. **Redundant cost.** Every gated issue pays for a second assumption-extraction LLM call
   whose answer the system already computed and persisted during refinement.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py` — add optional `targets: list[str] | None` to `run_learning_gate_for_issue`; forward as a `targets_csv` context input into the `proof-first-task` run.
- `scripts/little_loops/issue_manager.py` — in `process_issue_inplace`, pass the already-resolved `targets` (from `resolve_learning_targets`) into `run_learning_gate_for_issue` instead of discarding it after the trigger guard.
- `scripts/little_loops/loops/proof-first-task.yaml` — accept a `targets_csv` context input; when present, route directly to `ready-to-implement-gate` and skip the `assumption-firewall` delegation.
- `scripts/little_loops/loops/assumption-firewall.yaml` — `extract_assumptions` becomes the fallback-only path (runs only when no registered targets are supplied).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` (`process_issue_inplace`) — sole production caller of `run_learning_gate_for_issue`; the behavior change originates here.
- `resolve_learning_targets` (`scripts/little_loops/learning_tests/gate.py`) — already produces the `targets` list now consumed as the proof set rather than a boolean guard.

### Similar Patterns
- `proof-first-task.yaml` already forwards per-target context to the `ready-to-implement-gate` learning state; extend that same mechanism with `targets_csv` rather than introducing a new passing convention.

### Tests
- `scripts/tests/test_issue_manager.py` — covers `process_issue_inplace` gate invocation; add the divergence test (frontmatter `["stripe"]` vs body mentioning `requests`) asserting the gate proves `stripe` only.
- `scripts/tests/test_learning_tests.py`, `scripts/tests/test_learning_state.py` — assert zero `extract_assumptions` calls when registered targets are supplied; retain extraction-path coverage for the absent-field fallback.
- `scripts/tests/test_install_learning_gate.py` — guards the `LEARNING_GATE_BLOCKED` / exit-code contract (Acceptance Criterion 4); confirm byte-for-byte unchanged.

### Documentation
- `docs/guides/LEARNING_TESTS_GUIDE.md` — describes the gate and `learning_tests_required`; update to state the gate proves the registered list and only extracts as a fallback.

### Configuration
- N/A — no new config; the gate continues to trigger on `learning_tests.enabled`.

## Implementation Steps

1. **Thread the registered targets into the gate.** Pass the resolved `targets` from
   `issue_manager.py:855` into `run_learning_gate_for_issue` (new optional `targets:
   list[str] | None` parameter on `gate.py:76`).
2. **Prefer registered targets in the gate chain.** When targets are supplied, route them to
   `ready-to-implement-gate` directly (the `type: learning` prover) — bypassing
   `assumption-firewall`'s `extract_assumptions` step. `proof-first-task` already accepts
   per-target context; add a `targets_csv` context input it forwards to the learning gate.
3. **Keep extraction as fallback.** When `targets` is `None`/absent (un-refined issue),
   retain today's `assumption-firewall` re-extraction so the JIT path (ENH-2319) is
   unchanged.
4. **Unit test divergence.** Add a test where frontmatter and body disagree, asserting the
   gate proves the frontmatter list and makes zero `extract_assumptions` calls.

## Scope Boundaries

- **In scope**: making the implement-time gate consume `learning_tests_required` as its proof
  set; suppressing the redundant extraction when the field is populated.
- **Out of scope**: changing how refinement populates the field (ENH-2209); changing
  `/ll:explore-api` record creation; removing the gate from the `ll-auto` choke point
  (ENH-2319 — the gate stays there, it just sources targets differently); the
  post-implement `check_learning_gate` marker classifier in rn-remediate/autodev (reporting
  shim, unaffected).

## Acceptance Criteria

1. An issue with `learning_tests_required: ["stripe"]` and a body mentioning `requests` is
   gated on `stripe` only; `requests` is not proven.
2. With the field populated, no `assumption-firewall` `extract_assumptions` LLM call is made
   (verified via mock/log).
3. An issue with no `learning_tests_required` field still runs the existing extraction-based
   gate (JIT path unchanged).
4. `ll-auto --only` exit-code / `LEARNING_GATE_BLOCKED` contract is byte-for-byte unchanged.

## Impact

- **Priority**: P3 — correctness/consistency seam in a working feature; not blocking.
- **Effort**: Small–Medium — one new parameter threaded through `gate.py` + `proof-first-task`
  context; reuses the existing `ready-to-implement-gate` prover.
- **Risk**: Low — additive; fallback preserves current behavior for un-refined issues.
- **Breaking Change**: No.

## Related Key Documentation

- [LEARNING_TESTS_GUIDE.md](../../docs/guides/LEARNING_TESTS_GUIDE.md) — learning test registry, the implement-time gate, and `learning_tests_required` semantics.

## Labels

`enhancement`, `learning-tests`, `consistency`, `efficiency`

## Session Log
- `/ll:format-issue` - 2026-06-30T21:23:15 - `8bc99825-3dc5-4925-a87b-bed78c17905a.jsonl`
- `/ll:capture-issue` - 2026-06-30T21:17:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/517f4fde-43d5-44f7-afc7-41dd7c15be45.jsonl`

## Status

**Open** | Created: 2026-06-30 | Priority: P3
