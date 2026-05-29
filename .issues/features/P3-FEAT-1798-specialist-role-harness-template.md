---
id: FEAT-1798
type: FEAT
title: Specialist-role harness template (Plan → Research → Implement → Report)
priority: P3
status: open
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - captured
  - fsm
  - harness
  - loops
  - templates
  - create-loop
relates_to: [ENH-1796]
---

# FEAT-1798: Specialist-role harness template (Plan → Research → Implement → Report)

## Summary

Add a third harness variant to the `/ll:create-loop` wizard — **Variant
C: specialist-role pipeline** — that mirrors DeerFlow v1's
coordinator/planner/researcher/coder/reporter topology as a fixed FSM
template. Today the wizard offers only Variant A (single-shot) and
Variant B (multi-item), both of which collapse all "work" into one
`execute` step. Many real tasks (deep refactors, multi-file features,
cross-cutting refactors) benefit from explicit Plan → Research →
Implement → Report decomposition with HITL gates between stages.

## Current Behavior

- Wizard branches on H1 (target skill) and H2 (work-item mode) into
  Variants A and B.
- Both variants have a single `execute` state followed by evaluation
  gates.
- A user who wants a planning step today has to either:
  - Hand-author the FSM (30–60 min) per the loops reference, or
  - Chain `/ll:iterate-plan` and `/ll:manage-issue` outside any loop.
- No pre-built pattern reflects the multi-role architecture that has
  become a de-facto standard (DeerFlow, GPT-Researcher,
  langgraph-supervisor, etc.).

## Expected Behavior

A new wizard branch generating an FSM like:

```yaml
name: "harness-plan-research-implement-report"
initial: plan
max_iterations: 50
states:
  plan:
    action: /ll:iterate-plan ${args.task}
    action_type: slash_command
    capture: plan
    next: review_plan       # HITL gate (FEAT-1794 dependency)
  review_plan:
    action_type: human_approval   # depends on FEAT-1794
    prompt: "Review the plan: ${captured.plan.output}"
    on_yes: research
    on_no: plan
  research:
    action: "<background investigation skill>"
    action_type: prompt
    capture: research
    next: implement
  implement:
    action: /ll:manage-issue ${captured.plan.output}
    action_type: slash_command
    next: check_concrete
  check_concrete: { ... }          # existing phase chain
  check_semantic: { ... }
  check_invariants: { ... }
  report:
    action: /ll:describe-pr
    action_type: slash_command
    next: done
  done: { terminal: true }
```

Wizard additions:
- New H1 / H2 option set, or a new top-level "Workflow type" question.
- Sensible defaults for each role (configurable per-skill).
- Generated YAML lives under `scripts/little_loops/loops/` as a runnable
  annotated example, matching the `harness-single-shot.yaml` /
  `harness-multi-item.yaml` pattern.
- Documentation entry in `AUTOMATIC_HARNESSING_GUIDE.md` § Generated
  FSM Structure as "Variant C".

## Impact

- **Priority**: P3 — Net-new template; existing variants still cover
  the common case. Highest value once FEAT-1794 (HITL) lands, since
  the role boundaries are where human gates belong.
- **Effort**: Medium — wizard logic, generated YAML, annotated example,
  docs. Dependencies on FEAT-1794 and (nice-to-have) ENH-1796 for
  cross-role context sharing.
- **Risk**: Low — opt-in third variant; doesn't affect A or B.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Generated FSM Structure | Variants A/B documented here; this adds C |
| `skills/create-loop/loop-types.md` | Wizard implementation (lines 548–914 for Harness Questions) |
| `FEAT-1794` | HITL state type — preferred (not strictly required) for inter-role gates |
| `ENH-1796` | Shared message log — improves prompt quality across the role chain |

## Labels

`captured`, `create-loop`, `fsm`, `harness`, `loops`, `templates`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
