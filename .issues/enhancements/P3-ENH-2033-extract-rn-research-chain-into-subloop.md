---
id: ENH-2033
title: Extract the rn-plan/rn-refine research chain into a flow-authored sub-loop
type: ENH
priority: P3
parent: ENH-1777
relates_to:
  - ENH-2032
  - ENH-1775
  - ENH-1776
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: loop-audit
decision_needed: false
status: open
---

# ENH-2033: Extract the rn-plan/rn-refine research chain into a flow-authored sub-loop

## Summary

`rn-plan.yaml` and `rn-refine.yaml` share a six-state research-and-synthesize
chain that is copied almost verbatim between the two loops. Extract it into a
single reusable child loop authored with `flow:` (linear-with-ternary
shorthand), parameterized so `rn-refine`'s in-place source-file overwrite is
guarded behind a flag. This is the "sequential chain" finding from the loop
audit and the companion to the single-state extractions in [[ENH-2032]].

## Motivation

This enhancement would:
- **Eliminate duplication**: The six-state research chain is copied verbatim between `rn-plan.yaml` and `rn-refine.yaml`, creating a maintenance liability where bug fixes or prompt changes must be applied twice.
- **Enable reuse via `flow:`**: The chain's linear-with-ternary shape is a natural fit for the existing `flow:` shorthand — extraction requires no new FSM machinery.
- **Complete Wave 4 refactor**: Companion to the single-state extractions in [[ENH-2032]]; together they consolidate all rn-* research logic into composable, independently-validatable units.

## Parent Issue

Continues ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows.

## Current Behavior

The two loops duplicate this chain:

`classify_research → route_files → route_web → research_files → research_web → synthesize`

Verbatim-identical states (byte-for-byte):

| State | rn-plan | rn-refine |
|---|---|---|
| `classify_research` | `rn-plan.yaml:97` | `rn-refine.yaml:108` |
| `route_files` | `rn-plan.yaml:121` | `rn-refine.yaml:132` |
| `route_web` | `rn-plan.yaml:131` | `rn-refine.yaml:142` |
| `research_files` | `rn-plan.yaml:142` | `rn-refine.yaml:153` |

`classify_research` emits `NEEDS_FILES`/`NEEDS_WEB`; `route_files`/`route_web` are
`output_contains` routers dispatching to `research_files`/`research_web`, both
falling back to `synthesize` on error.

`research_web` (`rn-plan.yaml:172` / `rn-refine.yaml:183`) and `synthesize`
(`rn-plan.yaml:202` / `rn-refine.yaml:213`) are ~90% identical — **rn-refine adds
Step 7/8**: read `${run_dir}/.source-path`, overwrite the user's original file
in-place, then update the `task:` field in `plan-rubric.md`, and routes to
`snapshot` instead of `score`. rn-plan has no source file and routes straight to
`score`.

`flow:` already exists for exactly this shape (LOOPS_GUIDE.md §"Linear Flow
Shorthand", lines 4207–4277): a linear chain with ternary branches and
`state_defs:` bodies that can themselves pull `fragment:`. The chain is therefore
a natural `flow:`-authored sub-loop.

## Expected Behavior

- A single child loop owns the research chain. Both `rn-plan` and `rn-refine`
  delegate to it rather than carrying their own copies.
- The rn-refine-only in-place-overwrite tail (Step 7/8) is behind a parameter so
  rn-plan skips it.
- `ll-loop validate` passes for the new child and both parents; a smoke run
  produces artifacts equivalent to the pre-extraction loops.

## Success Metrics

- Duplication eliminated: 0 verbatim-shared research states between `rn-plan.yaml` and `rn-refine.yaml` (currently: 4 states byte-for-byte identical, 2 states ~90% identical).
- `ll-loop validate` exit code: 0 for `rn-plan`, `rn-refine`, and the new child loop.
- Behavior parity: smoke runs of both parents reach `score`/`snapshot` with artifacts equivalent to pre-extraction.

## Scope Boundaries

- **In scope**: Extracting the six-state research chain (`classify_research` → `synthesize`) into a `flow:`-authored child loop; updating both parents to delegate to it; gating rn-refine's Step 7/8 in-place overwrite behind `overwrite_source`.
- **Out of scope**: Changing prompt content of any research state; modifying `score`, `snapshot`, or `diagnose` states in either parent; fragment extractions already covered by [[ENH-2032]].

## Proposed Solution

Author the child as `oracles/plan-research-iteration.yaml` using `flow:`:

```yaml
name: plan-research-iteration
parameters:
  run_dir: { type: path, required: true }
  overwrite_source: { type: boolean, required: false }  # rn-refine tail (F2)
initial: classify_research
flow:
  - classify_research
  - "route_files?research_files:route_web"
  - "route_web?research_web:research_files"
  - research_files
  - research_web
  - synthesize
state_defs:
  # verbatim prompt bodies lifted from rn-plan; research_web/synthesize gate
  # the Step 7/8 overwrite on ${overwrite_source}
```

Parents invoke it via the chosen reuse vehicle (see Decision), passing
`run_dir` and (for rn-refine) `overwrite_source: true`. The parent's own
`score`/`snapshot`/`diagnose` states stay in place — only the research chain
moves.

## Decision

**`decision_needed: true`** — reuse vehicle (resolve at refinement). Both options
use existing abstractions; neither is net-new machinery.

- **Option A — sub-loop (`loop:`)**: each parent calls the child via `loop:` +
  `with:`. Cleanest isolation, mature path; child runs as one atomic state and
  merges captures back. Slight child-FSM runtime overhead.

> **Selected:** Option A — sub-loop (`loop:`) — dominant invocation pattern (20+ call sites), mature `_execute_sub_loop()` runtime, cleanest isolation for independent validation

- **Option B — shared base (`from:`)**: a `lib/`-level base loop holds the
  research states; `rn-plan`/`rn-refine` inherit via `from:` and override their
  non-shared parts. No child-FSM overhead, but tighter coupling and the parents
  remain single `states:` graphs (so the shared states live in the base, not a
  callable unit).

Recommendation leans **Option A** (matches how other oracles like
`oracles/enumerate-and-prove` are consumed), but confirm during refinement.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-08.

**Selected**: Option A — sub-loop (`loop:`)

**Reasoning**: The `loop:` + `with:` invocation model is the dominant pattern with 20+ call sites, a mature `_execute_sub_loop()` runtime in `executor.py:506`, and 5 existing oracles confirming the design. Both options are fully implemented — `from:` resolution is parse-time with zero runtime overhead and `fragments.py:159` handles per-child state overrides via `_deep_merge`. The decisive differentiator is **testability**: the sub-loop child is an independently runnable/validatable unit (`ll-loop run oracles/plan-research-iteration`), while `from:` embeds the shared states into each parent graph with no way to validate the research chain in isolation.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — sub-loop (`loop:`) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B — shared base (`from:`) | 2/3 | 2/3 | 1/3 | 2/3 | 7/12 |

**Key evidence**:
- Option A: 20+ `loop:` call sites; `executor.py:506` `_execute_sub_loop()` battle-tested; 5 oracles in `loops/oracles/`; `integrate-sdk.yaml:120-123` and `adopt-third-party-api.yaml:61` show parameterized `with:` invocation; child is independently runnable
- Option B: `from:` is fully implemented (`fragments.py:159`) with 3 APO users; `loops/lib/` designated home; parse-time only (no runtime overhead); LOOPS_GUIDE.md §4095–4203 has decision table; but shared states embedded in parent graphs — no independent oracle to validate the research chain in isolation

## Implementation Steps

1. Resolve the Decision (Option A sub-loop vs Option B shared base) and record the outcome in the issue.
2. Author `oracles/plan-research-iteration.yaml` using `flow:` with the six shared research states and the `overwrite_source` parameter gate for rn-refine's Step 7/8.
3. Update `rn-plan.yaml` to delegate the research chain to the child via the chosen vehicle, removing the inline state copies.
4. Update `rn-refine.yaml` to delegate with `overwrite_source: true`, removing its inline copies.
5. Run `ll-loop validate` on the child and both parents; fix any validation failures.
6. Smoke-run `rn-plan` and `rn-refine`; verify artifacts match pre-extraction behavior.
7. Add parity/validation tests in `scripts/tests/`; update `docs/guides/LOOPS_GUIDE.md` if the guide enumerates oracles.

## Integration Map

### Files to Modify / Create
- `scripts/little_loops/loops/oracles/plan-research-iteration.yaml` — **new** child.
- `scripts/little_loops/loops/rn-plan.yaml` — replace the six research states with
  a delegation to the child (vehicle per Decision).
- `scripts/little_loops/loops/rn-refine.yaml` — same, passing `overwrite_source: true`.

### Reference Patterns
- `oracles/enumerate-and-prove.yaml` + its caller `adopt-third-party-api.yaml`
  (`loop:` + `with:` invocation model).
- LOOPS_GUIDE.md §"Linear Flow Shorthand via `flow:`" (lines 4207–4277) and
  §"Composable Sub-Loops" (lines 3703–3800).
- `scripts/little_loops/fsm/executor.py:_execute_sub_loop()` (sub-loop semantics);
  `fsm/fragments.py:resolve_flow()` (flow expansion).

### Tests & Docs
- `scripts/tests/` — add a parity/validation test for the new child and assert
  both parents still validate and reach `score`/`snapshot`.
- `docs/guides/LOOPS_GUIDE.md` — note the shared research oracle if the guide
  enumerates oracles.

## Acceptance Criteria

- [ ] `oracles/plan-research-iteration.yaml` exists, authored with `flow:`, and
      passes `ll-loop validate`.
- [ ] `rn-plan` and `rn-refine` delegate the research chain to it; the inline
      copies are removed.
- [ ] `overwrite_source` correctly gates rn-refine's Step 7/8; rn-plan skips it.
- [ ] `ll-loop validate` passes for `rn-plan`, `rn-refine`, and the new child.
- [ ] Behavior parity: smoke runs of `rn-plan` and `rn-refine` reach `score`
      with artifacts equivalent to pre-extraction.
- [ ] Reuse vehicle (Option A vs B) decided and recorded before implementation.


## Session Log
- `/ll:decide-issue` - 2026-06-09T01:37:41 - `5822886d-9616-489f-b479-e23fbca1e095.jsonl`
- `/ll:format-issue` - 2026-06-09T01:28:10 - `b8cd5b00-183b-4a0c-a5fc-6f9113d43c0a.jsonl`
