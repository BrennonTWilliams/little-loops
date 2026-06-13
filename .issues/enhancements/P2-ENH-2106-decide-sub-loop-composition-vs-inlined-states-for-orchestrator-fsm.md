---
id: ENH-2106
title: "Decide: reusable sub-loop composition vs inlined per-issue states for orchestrator FSM Layers 1+2"
type: ENH
priority: P2
status: open
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1867
relates_to: [FEAT-2000, FEAT-1899]
blocks: [FEAT-2000, FEAT-1899]
decision_needed: false
labels:
  - fsm
  - orchestration
  - decision
  - spike
---

# ENH-2106: Decide: reusable sub-loop composition vs inlined per-issue states for orchestrator FSM Layers 1+2

## Summary

Resolve Open Question 1 of the orchestrator decomposition plan
(`docs/research/ll-orchestrator-decomposition-plan-v0.2.md`): should the
per-issue processing states (claim → implement → verify → complete/fail) be
extracted into a reusable sub-loop that both Layer 1 (`loops/ll-auto.yaml`,
FEAT-2000) and Layer 2 (the ll-sprint FSM, FEAT-1899) compose, or should each
layer inline its own copy of those states?

## Motivation

This design decision directly shapes how FEAT-2000 and FEAT-1899 are
authored. If it is unresolved when authoring begins, FEAT-1899 will likely
duplicate FEAT-2000's states, and converging later means rewriting one or
both loops. Deciding first is a small spike; deciding later is a refactor.

## Acceptance Criteria

- [ ] Evidence gathered: current sub-loop/fragment composition support in the
  FSM runner (`loops/lib/` fragments, any `sub_loop`/include mechanism) and
  its limitations
- [ ] Decision recorded in `.ll/decisions.yaml` via `ll-issues decisions add`
  (type=decision, category=architecture, issue=EPIC-1867) with rationale and
  rejected alternative
- [ ] FEAT-2000 and FEAT-1899 issue bodies annotated with the decision so
  authoring follows it
- [ ] If composition is chosen: the shared state fragment's home
  (`loops/lib/...`) is named in the decision

## Proposed Solution

Two options to evaluate:

### Option A: Reusable sub-loop composition (`loop:` field)

> **Selected:** Option A — single-definition sub-loop composition; 46 call sites in the codebase confirm this is the established pattern, and `rn-implement.yaml` provides the exact sidecar-token template.

Extract the per-issue processing states into a standalone loop file (e.g.,
`scripts/little_loops/loops/per-issue-processor.yaml`) with a `parameters:`
block declaring `issue_id` as required. Both `ll-auto.yaml` and `ll-sprint.yaml`
invoke it via:

```yaml
run_per_issue:
  loop: per-issue-processor
  with:
    issue_id: "${captured.current.output}"
    baseline_sha: "${captured.baseline.output}"
  on_yes: pick_next     # child terminal: done
  on_no: pick_next      # child terminal: failed / error
```

Outcomes signal back through sidecar token files
(`${context.run_dir}/subloop_outcome_${issue_id}.txt`) following the pattern
established in `rn-implement.yaml` and the `subloop_rate_limit_diagnostic`
fragment in `lib/common.yaml`.

- **Pros**: single definition for the 6–8 per-issue states; fix once, both
  orchestrators benefit; consistent behavior across `ll-auto` and `ll-sprint`;
  matches the codebase's established `rn-implement` → `rn-remediate` pattern.
- **Cons**: sub-loop nesting adds one context-propagation layer; outcomes require
  sidecar token files rather than direct capture; child timeout is clamped to
  parent's remaining wall-clock budget; slightly harder to debug nested runs.

### Option B: Inline per-issue states in each orchestrator

Each loop (`ll-auto.yaml`, `ll-sprint.yaml`) embeds its own copy of the
per-issue states directly in its `states:` map. Fragment library snippets from
`lib/common.yaml` (`shell_exit`, `queue_pop`, etc.) reduce per-state boilerplate,
but the full sequence is duplicated.

- **Pros**: simpler to author and read; each loop can evolve independently; no
  sub-loop nesting; straightforward `captured.<state>.output` access.
- **Cons**: ~6–8 states duplicated across two files; consistency drift risk;
  changes must be applied twice; divergence is silent unless lint catches it.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-13.

**Selected**: Option A: Reusable sub-loop composition (`loop:` field)

**Reasoning**: The `loop:` + `with:` pattern has 46 call sites across 20+ loop files — it is the codebase's established orchestration primitive, not an experimental pattern. The size contrast between `sprint-refine-and-implement.yaml` (74 lines, 5 states via delegation) and `autodev.yaml` (593 lines, 30+ inlined states) makes Option B's maintainability cost concrete. Option B's silent drift risk — 12–16 identical state blocks split across two files with no lint guard — is the key disqualifier.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: sub-loop composition | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Option B: inline states | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- **Option A**: 46 `loop:` call sites across 20+ files; `rn-implement.yaml` provides the exact sidecar-token + `with:` template; `sprint-refine-and-implement.yaml` (74 lines, 5 states) shows how delegation keeps orchestrators lean; `_execute_sub_loop()` at `executor.py:517` is fully implemented with timeout clamping, context binding, and capture merge
- **Option B**: `autodev.yaml` grew to 593 lines with 30+ inlined states; no lint rule in `fsm/validation.py` catches silent divergence between duplicated state blocks; each bug fix must be applied twice

## Integration Map

### Files to Read
- `docs/research/ll-orchestrator-decomposition-plan-v0.2.md:278` — Open Question 1
  verbatim; Layer-1 reference FSM YAML (lines 119–200)
- `scripts/little_loops/fsm/executor.py:517` — `_execute_sub_loop()`: full
  sub-loop runtime mechanics (context binding, timeout clamping, capture merge,
  routing logic)
- `scripts/little_loops/fsm/schema.py` — `StateConfig` fields: `loop`, `with_`,
  `context_passthrough`, `fragment_parameters` (sub-loop vs fragment contract)
- `scripts/little_loops/fsm/validation.py` — `_validate_with_bindings()`:
  static cross-validation of `with:` keys against child `parameters:`; also
  `_validate_state_action()` for `loop:` ↔ `action:` mutual-exclusion rules
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()`: parse-time
  fragment expansion (note: fragments expand into a state; they do NOT invoke
  a child FSM at runtime — distinct from `loop:`)
- `scripts/little_loops/loops/lib/common.yaml` — `subloop_rate_limit_diagnostic`
  fragment (sidecar token pattern for sub-loop failure signaling); also
  `queue_pop`, `shell_exit`, `queue_track` fragments reusable in either option
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_loop_run` fragment (shell
  subprocess alternative to `loop:` keyword — exit-code only, no capture
  propagation)

### Existing Sub-loop Examples to Study
- `scripts/little_loops/loops/rn-implement.yaml` — canonical `loop:` + `with:` +
  sidecar token pattern: `run_remediation` state calls `rn-remediate` with
  `{issue_id, readiness_threshold, outcome_threshold, max_remediation_passes,
  run_dir}`; outcome read from `subloop_outcome_<ID>.txt`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:51` —
  `refine_issue` state uses `loop: recursive-refine` + `context_passthrough:
  true`; `implement_chain` uses `loop: oracles/implement-issue-chain` + `with:`
- `scripts/little_loops/loops/scan-and-implement.yaml` — mixes bare `loop:`
  (no bindings) with `loop:` + `with:` in the same orchestrator
- `scripts/little_loops/loops/autodev.yaml` — queue-orchestration template that
  FEAT-2000 models `ll-auto.yaml` after; inlines per-issue work inline (Option B
  reference)

### Files to Modify
- `.ll/decisions.yaml` (via `ll-issues decisions add`)
- `.issues/features/P2-FEAT-2000-author-loops-ll-auto-yaml-fsm-definition.md` —
  decision annotation: if Option A, name the shared loop file; if Option B,
  confirm inline states
- `.issues/features/P3-FEAT-1899-ll-sprint-fsm-wave-driver-and-shim.md` —
  decision annotation: update `run_sequential` state design to match decision

### If Option A is chosen: candidate shared loop home
- `scripts/little_loops/loops/per-issue-processor.yaml` — new file; NOT under
  `loops/lib/` (lib/ contains fragment libraries only — not runnable loops;
  `is_runnable_loop()` returns `False` for files without `initial:` + `states:`)

## Implementation Steps

1. Read `docs/research/ll-orchestrator-decomposition-plan-v0.2.md:278` (Open
   Question 1) and the reference `loops/ll-auto.yaml` YAML (lines 119–200) to
   confirm what the 6–8 per-issue states are.
2. Examine `scripts/little_loops/fsm/executor.py:517` (`_execute_sub_loop()`) and
   `scripts/little_loops/fsm/validation.py:_validate_with_bindings()` to confirm
   sub-loop composition support and `with:` parameter-contract validation.
3. Study `scripts/little_loops/loops/rn-implement.yaml` (`run_remediation` state)
   as the canonical `loop:` + `with:` + sidecar-token pattern for per-item
   orchestration.
4. Study `scripts/little_loops/loops/autodev.yaml` as the inline-state reference
   for Option B (queue-orchestration with per-issue states inlined).
5. Evaluate trade-offs using the criteria in `## Proposed Solution` above.
6. Record decision via:
   ```bash
   ll-issues decisions add \
     --type decision \
     --category architecture \
     --issue EPIC-1867 \
     --title "Per-issue states: sub-loop vs inline" \
     --verdict "Option A|Option B" \
     --rationale "..." \
     --rejected-alt "..."
   ```
7. If Option A: name the shared loop file (`loops/per-issue-processor.yaml`) in
   the decision record.
8. Annotate `FEAT-2000` (`P2-FEAT-2000-author-loops-ll-auto-yaml-fsm-definition.md`):
   add a note under Implementation Steps step 2 specifying whether `ll-auto.yaml`
   inlines per-issue states or delegates via `loop: per-issue-processor`.
9. Annotate `FEAT-1899` (`P3-FEAT-1899-ll-sprint-fsm-wave-driver-and-shim.md`):
   update the `run_sequential` state design in Proposed Solution to match the
   decision (either `loop: per-issue-processor` with `with:` bindings, or inlined
   states mirroring `ll-auto.yaml`'s copy).

## Impact

- **Priority**: P2 — gates authoring of FEAT-2000 and FEAT-1899
- **Effort**: Small — research + decision record, no implementation
- **Risk**: Low — decision-only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P2


## Session Log
- `/ll:decide-issue` - 2026-06-13T14:10:31 - `9aaae9fc-d0da-4b2b-80af-8f24ea621c5f.jsonl`
- `/ll:refine-issue` - 2026-06-13T14:05:31 - `0df548d1-097e-4c28-ab0b-0c0e9ac98101.jsonl`
