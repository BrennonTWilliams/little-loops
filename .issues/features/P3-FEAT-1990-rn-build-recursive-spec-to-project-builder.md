---
id: FEAT-1990
title: "rn-build — Recursive Spec-to-Project Builder (greenfield-builder successor)"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: Very Large
relates_to:
- FEAT-1988
- FEAT-1808
- FEAT-1809
labels:
- loops
- orchestration
- built-in
- greenfield
---

# FEAT-1990: `rn-build` — Recursive Spec-to-Project Builder

## Summary

Ship a new built-in FSM loop, `rn-build`, that takes a single high-level project
spec Markdown file and autonomously drives the project from zero to a working,
evaluated implementation by composing the EPIC-1811 orchestration stack —
`scope-epic` (spec → EPIC), `goal-cluster` (dedup + cross-feature context
propagation), and `rn-implement` (recursive decompose + implement) — rather than
the older linear `eval-driven-development` delegation used by `greenfield-builder`.

This is the **integration capstone** of EPIC-1811: the other children are
orchestration primitives; `rn-build` is the agent that uses them to demonstrate
the EPIC's thesis — empowering an agent to decompose a goal, decide what to work
on next, and adapt as it goes.

## Motivation

`greenfield-builder` predates the `rn-*` recursive family. It does a valuable
front half (tech research → design artifacts → eval harness → spec decomposition →
refinement) but then hands the implement→eval→fix cycle to `eval-driven-development`
and decomposes the spec in a single non-recursive pass (`max_issues: 30`). It never
exercises the recursive `rn-implement` queue, the `goal-cluster` context
propagation, or any intelligent "what to work on next" scheduling.

The EPIC-1811 stack now has every primitive needed to do this properly. `rn-build`
ties them together and replaces `greenfield-builder`.

**Why:** A spec-to-project builder is the clearest demonstration of agent-driven
decision-making — it must decompose, sequence, implement recursively, and adapt
on failure. **How to apply:** compose landed loops; the only genuinely new
capability is value-ranked scheduling (FEAT-1991).

## Design (locked)

### Layering — `goal-cluster → rn-implement`

The division of labor is by granularity, so the queue is never fragmented:

- **`goal-cluster`** owns the *inter-batch* layer: dedup overlapping features,
  batch them, and propagate cross-feature context (data-model decisions, auth
  approach, naming conventions) into downstream batch `hints`. This is the
  load-bearing reason a fresh project benefits — features share decisions.
- **`rn-implement` (value-ranked)** owns the *intra-batch* layer: it receives a
  batch's issue IDs and its new `select_next` scheduler (FEAT-1991) picks the
  highest-value *ready* issue each tick, recursing via `rn-decompose` when an
  issue is too large. The whole batch tree stays visible to one scheduler.

Two granularities of "decide what to work on next": `goal-cluster` decides batch
order and carries context forward; `rn-implement` decides issue order within a
batch by value + dependency-readiness.

### State graph

```
init             validate + read spec.md (reuse greenfield init)
  → tech_research        prompt → docs/research.md            ┐ reused
  → design_artifacts     prompt → docs/data-model, contracts  │ from
  → commit_design        /ll:commit                           ┘ greenfield-builder
  → scope_project        scope-epic: spec+design → EPIC + epic/feature stubs
  → refine_seed          loop: issue-refinement (seed issues → ready)
  → eval_harness         install + customize as-a-user harness; capture harness_name
  → cluster_execute      loop: goal-cluster (input=EPIC-ID, propagate_context=true)
                           └─ per batch → loop: rn-implement (schedule_mode=value_ranked)
  → eval_gate            run harness loop; failures → capture-issue → re-enter cluster_execute
  → synthesize_result    cluster-wide summary + recommended next batch
  → done
```

`eval-driven-development` drops out entirely: `rn-remediate`'s converge handles
implement→fix, and the project-level `eval_gate` replaces the old delegation.

## Decomposition

This capstone is implemented by four children:

- **FEAT-1991** — `rn-implement` value-ranked dequeue (`select_next`). Independent;
  unblocked; benefits all `rn-implement` callers.
- **FEAT-1992** — `rn-build` loop YAML + loaders + integration. Blocked by
  FEAT-1988 (goal-cluster core) and FEAT-1991.
- **FEAT-1993** — deprecate `greenfield-builder`. Blocked by FEAT-1992.
- **FEAT-1994** — `rn-build` create-loop wizard + docs + tests. Blocked by FEAT-1992.

## Acceptance Criteria

- `ll-loop run rn-build path/to/spec.md` drives a spec to an implemented,
  harness-evaluated project end-to-end.
- The loop composes `scope-epic` → `goal-cluster` → `rn-implement` (not
  `eval-driven-development`).
- `rn-implement` runs in `value_ranked` schedule mode under `rn-build`.
- `greenfield-builder` is deprecated (still present for one release for A/B).
- All four children (FEAT-1991/1992/1993/1994) are done.

## Open Questions

1. **Harness category.** `rn-build` creates an eval harness loop (a harness
   artifact) but its primary operation is implementing project code. Keep
   `category: orchestration`/`planning` (not `harness`) and delegate
   harness creation to `ll-loop install harness-*` as `greenfield-builder` does.
   Confirm MR-1/MR-5 do not apply since `eval_gate` uses a concrete harness run
   (exit_code), not an LLM self-grade.
2. **Batch sizing for greenfield.** Should `cluster_execute` set
   `orchestration.cluster.max_batch_size` higher for greenfield (whole-project
   visibility) or keep the default 5 and rely on context propagation across
   batches?

## Relationship to Sibling Issues

- **FEAT-1988 (goal-cluster core)** — `rn-build` consumes goal-cluster as its
  inter-batch engine; gates FEAT-1992.
- **FEAT-1808/1809 (loop-composer / adaptive)** — `rn-build` MAY dispatch
  `loop-composer` for any single feature too large for one loop (via the
  goal-cluster → loop-composer allowlist already encoded in FEAT-1810).
- **greenfield-builder** — superseded by `rn-build`; deprecated via FEAT-1993.

## Status

- **State**: open
- **Created**: 2026-06-06
