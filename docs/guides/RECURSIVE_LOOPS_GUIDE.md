# Recursive Loops Guide (the `rn-*` Family)

> **When to use this**: You want to understand the `rn-*` ("recursive-N") loops —
> how `rn-plan`, `rn-refine`, `rn-implement`, `rn-remediate`, and `rn-decompose`
> each work and, more importantly, how they hand off to each other to turn a goal
> into refined plans and implemented issues. This guide is the conceptual map; for
> per-loop context variables and full FSM state tables, see the
> [Built-in Loops Reference](LOOPS_REFERENCE.md). For FSM fundamentals (states,
> evaluators, routing), see the [Loops Guide](LOOPS_GUIDE.md).

## Contents

- [What the `rn-*` Family Is](#what-the-rn-family-is)
- [The Big Picture](#the-big-picture)
- [Planning Loops: `rn-plan` & `rn-refine`](#planning-loops-rn-plan--rn-refine)
- [Implementation Loops: `rn-implement`, `rn-remediate`, `rn-decompose`](#implementation-loops-rn-implement-rn-remediate-rn-decompose)
- [How They Connect](#how-they-connect)
- [Running Them](#running-them)
- [See Also](#see-also)

---

## What the `rn-*` Family Is

The `rn-*` loops share one idea: **score, research, refine, repeat — until a
measurable condition holds.** "Recursive-N" means they keep deepening their own
output (a plan, or an issue tree) across bounded iterations rather than running a
single fixed pass.

There are two sub-families, joined by that shared idea:

- **Planning loops** operate on a plan `.md` document. They score it against a
  rubric and iterate until every dimension reaches `VERY-HIGH`.
- **Implementation loops** operate on `.issues/` files. They walk a depth-bounded
  issue queue, remediating each issue until it's ready to implement, and
  decomposing issues that are too large into children that re-enter the queue.

| Loop | Family | Role | Input | Output |
|------|--------|------|-------|--------|
| `rn-plan` | Planning | Entry point | A task description (string) | `plan.md` + rubric |
| `rn-refine` | Planning | Entry point | Path to an existing `plan.md` | Refined `plan.md` (in place) |
| `rn-implement` | Implementation | Entry point / orchestrator | Issue ID(s) | Implemented issues + `summary.json` |
| `rn-remediate` | Implementation | Sub-loop (per issue) | One issue ID | Outcome token |
| `rn-decompose` | Implementation | Sub-loop (per issue) | One issue ID | Outcome token + enqueued children |

> **Note**: The sub-loops (`rn-remediate`, `rn-decompose`) are normally driven by
> `rn-implement`, but each is independently runnable with `ll-loop run` if you
> want to operate on a single issue.

## The Big Picture

The capstone `rn-build` loop ties both families together — it plans, scopes an
EPIC, then implements — but you can run either family on its own. The call graph:

```
rn-build  (capstone: spec → plans → EPIC → implement)
  │
  ├── Planning ─────────────────────────────────────────────
  │     rn-plan   (task → plan.md)
  │     rn-refine (existing plan.md → better plan.md)
  │         └── oracles/plan-research-iteration
  │               classify → research (files|web) → synthesize
  │
  └── Implementation ───────────────────────────────────────
        rn-implement  (queue orchestrator)
          │  dequeue issue → gates (blocked / depth / status)
          │
          ├── rn-remediate  (per issue: diagnose → remediate → converge)
          │       emits outcome token ──► parent routes
          │
          └── rn-decompose  (split issue into children)
                  enqueues children ──► back into rn-implement's queue
                                        (depth-first recursion)
```

The two families don't call each other directly at runtime — `rn-build` is the
glue that runs planning first and implementation second. Within the
implementation family, the feedback arrow that matters is `rn-decompose`
prepending children back onto `rn-implement`'s queue: that is what makes the
issue tree *recursive*.

## Planning Loops: `rn-plan` & `rn-refine`

Both produce a structured `plan.md` and a `plan-rubric.md` of dimension scores in
a per-run artifact directory (`.loops/runs/<loop>-<timestamp>/`). Each iteration
delegates to the shared `oracles/plan-research-iteration` oracle, which decides
whether the next gap needs **file** research or **web** research, gathers it, and
synthesizes the findings back into the plan. The loop keeps iterating until every
rubric dimension reaches `VERY-HIGH` or `max_steps` is hit.

**`rn-plan` — plan from scratch.** Give it a natural-language task. It generates
an outline plus an 8-dimension rubric (breadth, depth, complexity, clarity,
consistency, logic_strategy, feasibility, testability, risk_mitigation), starting
*all* dimensions at `LOW`, then researches and refines upward.

```bash
ll-loop run rn-plan "build a rate-limiting middleware for the API"
```

**`rn-refine` — improve an existing plan.** Give it a path to a draft `.md` plan
(from `rn-plan`, `/ll:iterate-plan`, or written by hand). Its key difference is
`assess_existing`: it calibrates a 9-dimension rubric to the plan's *current*
state rather than assuming everything is `LOW`, so it doesn't waste iterations
re-refining what's already strong. On completion it **overwrites the original
file in place** — no manual copy out of `.loops/` needed.

```bash
ll-loop run rn-refine ".loops/runs/rn-plan-20260526T143022/plan.md"
```

> **Tip**: Pick `rn-plan` when you're starting cold; pick `rn-refine` when you
> already have a draft and want it deepened without losing existing structure.

## Implementation Loops: `rn-implement`, `rn-remediate`, `rn-decompose`

This family turns a backlog of issues into implemented work, recursively
splitting anything too large to implement directly.

### `rn-implement` — the orchestrator you run

`rn-implement` is a **pure queue orchestrator** — it makes no LLM calls of its
own. Given an issue ID (or comma-separated list), it seeds a queue and loops:

```
dequeue next issue
  → is it blocked_by an unfinished dep?   → defer
  → is it deeper than max_depth (3)?      → cap
  → is it already done/cancelled?         → skip
  → otherwise → delegate to rn-remediate
        ↳ if remediation says "decompose" → delegate to rn-decompose
repeat until the queue is empty or max_steps (500) is hit
```

All domain reasoning lives in the delegated sub-loops; `rn-implement` only
schedules and routes. It supports FIFO (default) or value-ranked scheduling, and
re-enqueues deferred issues once their `blocked_by` dependencies complete.

```bash
ll-loop run rn-implement "FEAT-1808,ENH-1842"
```

### `rn-remediate` — make one issue ready, then implement it

For each dequeued issue, `rn-remediate` runs an iterative deepening cycle in four
phases:

```
1. Assessment Bridge   /ll:confidence-check → readiness gate
                       (already ready? short-circuit straight to implement)
2. Dimensional Diagnosis  analyze 5 dimensions → route to one action:
                          IMPLEMENT · DECIDE · WIRE · REFINE · DECOMPOSE
3. Remediation Actions    run the chosen action (decide / wire / refine /
                          implement) with refine+wire marker gating
4. Re-Assessment & Convergence  re-score → compute deltas → converged?
                          improved? stalled? (bounded by max_remediation_passes: 3)
```

It never returns a bare "pass" — instead it writes an **outcome token** the
parent reads (see [How They Connect](#how-they-connect)). The cycle is bounded by
`max_remediation_passes` (default 3) and `max_steps` (100).

### `rn-decompose` — split an issue, feed children back to the queue

When remediation decides an issue is too large (or stalls), `rn-implement`
delegates to `rn-decompose`:

```
size review (/ll:issue-size-review) → detect new child issues →
enqueue children (cycle detection, depth = parent_depth + 1) →
close & link parent to its EPIC
```

The children are **prepended depth-first** onto `rn-implement`'s queue, so they
get processed before the parent's siblings. This is the recursion: a child can
itself be remediated, and decomposed again, up to `max_depth`.

## How They Connect

Three mechanisms join the implementation loops into one recursive system.

**1. Outcome-token handoff.** Sub-loops don't rely on an ambiguous
done/failed verdict. Each writes a deterministic token to
`${run_dir}/subloop_outcome_<ID>.txt`, and the parent's `classify_*` states read
it and route. For `rn-remediate`:

| Outcome token | Meaning | `rn-implement` routes to |
|---------------|---------|--------------------------|
| `IMPLEMENTED` | Issue implemented | Re-enqueue newly-unblocked issues, continue |
| `NEEDS_DECOMPOSE` | Issue too large | Delegate to `rn-decompose` |
| `STALLED_NEEDS_DECOMPOSE` | Remediation exhausted its budget | Try `rn-decompose`; if no children, defer |
| `MANUAL_REVIEW_NEEDED` | Needs a human decision | Mark blocked |
| `RATE_LIMITED` | Host rate limit hit | Record rate-limit diagnostic, continue |
| `IMPLEMENT_FAILED` / `SCORES_MISSING` | Failure | Record failure, continue |

`rn-decompose` emits `DECOMPOSED` (children enqueued) or `NO_CHILDREN` (atomic);
the parent uses the stall-vs-atomic distinction above to decide between deferring
and skipping.

**2. Shared run directory.** All three implementation loops read and write the
same `${run_dir}`: `queue.txt`, `visited.txt`, `depth_map.txt`, per-issue score
snapshots, and counters. The queue and visited set are how a child enqueued by
`rn-decompose` becomes visible to the next `rn-implement` dequeue, and how cycle
detection avoids reprocessing an issue.

**3. Recursion bounds.** Three circuit breakers keep the recursion finite:

| Bound | Loop | Default | Stops |
|-------|------|---------|-------|
| `max_depth` | `rn-implement` | 3 | Decomposition recursing too deep |
| `max_steps` | `rn-implement` | 500 | Runaway orchestration across all issues |
| `max_remediation_passes` | `rn-remediate` | 3 | An issue churning without converging |

## Running Them

Each loop is individually runnable. Artifacts always land under
`.loops/runs/<loop>-<timestamp>/`.

```bash
# Planning
ll-loop run rn-plan "design an offline-first sync layer"
ll-loop run rn-refine "thoughts/sync-layer-plan.md"

# Implementation (the entry point — drives the sub-loops for you)
ll-loop run rn-implement "FEAT-1808"
ll-loop run rn-implement "FEAT-1808,ENH-1842,BUG-1001"

# Sub-loops standalone, against a single issue
ll-loop run rn-remediate "ENH-1842"
ll-loop run rn-decompose "FEAT-1808"
```

When `rn-implement` finishes it writes a `summary.json` and a human-readable
completion message; check `failures.txt`, `deferred.txt`, and `blocked.txt` in
the run directory for issues that need attention.

> **Tip**: For the full end-to-end pipeline (spec → design → EPIC → batched
> implementation), use `rn-build` — see its section in the
> [Built-in Loops Reference](LOOPS_REFERENCE.md#rn-build--spec-to-project-capstone-orchestrator).

## See Also

- [Loops Guide](LOOPS_GUIDE.md) — FSM fundamentals: states, evaluators, routing,
  authoring
- [Built-in Loops Reference](LOOPS_REFERENCE.md) — full per-loop catalog: context
  variables, complete FSM flows, and every invocation flag for the `rn-*` loops
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — meta-loop design
  rules and the optimizer error taxonomy
- `ll-loop --help` — full CLI reference for all loop subcommands
