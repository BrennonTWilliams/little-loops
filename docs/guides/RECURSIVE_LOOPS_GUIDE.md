# Recursive Loops Guide (the `rn-*` Family)

> **When to use this**: You want to understand the `rn-*` ("recursive-N") loops —
> how `rn-plan`, `rn-refine`, `rn-implement`, `rn-remediate`, and `rn-decompose`
> each work and, more importantly, how they hand off to each other to turn a goal
> into refined plans and implemented issues. This guide is the conceptual map; for
> per-loop context variables and full FSM state tables, see the
> [Built-in Loops Reference](LOOPS_REFERENCE.md). For FSM fundamentals (states,
> evaluators, routing), see the [Loops Guide](LOOPS_GUIDE.md).

## Contents

- [What the `rn-*` Family Is](#what-the-rn--family-is)
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
| `rn-plan` | Planning | Entry point | A task description (string) | `plan.md` + `plan-rubric.md` + `research.md` |
| `rn-refine` | Planning | Entry point / orchestrator | Path to an existing `plan.md` | Recursively refined `plan.md` (in place) |
| `rn-implement` | Implementation | Entry point / orchestrator | Issue ID(s) | Implemented issues + `summary.json` |
| `rn-remediate` | Implementation | Sub-loop (per issue) | One issue ID | Outcome token |
| `rn-decompose` | Implementation | Sub-loop (per issue) | One issue ID | Outcome token + enqueued children |
| `oracles/plan-node-refine` | Planning | Sub-loop (per node) | One plan-tree node | Outcome token + enqueued child sub-plans |

> **Note**: The sub-loops (`rn-remediate`, `rn-decompose`) are normally driven by
> `rn-implement`, but each is independently runnable with `ll-loop run` if you
> want to operate on a single issue.

## The Big Picture

`rn-build` is a separate capstone orchestrator (spec → tech research → design →
EPIC → issue refinement → eval harness → clustered implementation → eval gate)
that shares the "recurse until converged" idea but does **not** delegate to
`rn-plan`, `rn-refine`, or `rn-implement` directly — it has its own
research/design/scoping states, uses the `recursive-refine` loop to seed-refine
newly scoped issues, and dispatches execution through `goal-cluster`, which in
turn batches work out to `rn-implement`. See
[Built-in Loops Reference § rn-build](LOOPS_REFERENCE.md#rn-build--spec-to-project-capstone-orchestrator)
for its full state chain. The two families below (`rn-plan`/`rn-refine` and
`rn-implement`/`rn-remediate`/`rn-decompose`) are each independently runnable
and don't call each other directly at runtime. The call graph for the two
families:

```
Planning ─────────────────────────────────────────────
  rn-plan   (task → plan.md)
      └── oracles/plan-research-iteration
            classify → research (files|web) → synthesize
  rn-refine (existing plan.md → recursively refined plan.md)
      │  dequeue node → refine → decide leaf|decompose
      └── oracles/plan-node-refine  (per node)
            refine to convergence (reuses plan-research-iteration)
            then LEAF, or DECOMPOSE → enqueue child sub-plans
                                      (depth-first recursion)

Implementation ───────────────────────────────────────
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

Both families share the same recursion shape: a depth-bounded queue where a
node, when it is too large/coarse, is split into children that are *prepended*
back onto the queue and processed depth-first. In implementation that feedback
arrow is `rn-decompose` prepending child issues onto `rn-implement`'s queue; in
planning it is `oracles/plan-node-refine` prepending child sub-plans onto
`rn-refine`'s node queue. That prepend-and-re-enter step is what makes each
tree *recursive*.

## Planning Loops: `rn-plan` & `rn-refine`

Both produce a structured `plan.md` and a `plan-rubric.md` of dimension scores in
a per-run artifact directory (`.loops/runs/<loop>-<timestamp>/`). Each iteration
delegates to the shared `oracles/plan-research-iteration` oracle, which decides
whether the next gap needs **file** research or **web** research, gathers it, and
synthesizes the findings back into the plan. The loop keeps iterating until every
rubric dimension reaches `VERY-HIGH` or `max_steps` is hit.

**`rn-plan` — plan from scratch.** Give it a natural-language task. It generates
an outline plus a nine-dimension rubric (breadth, depth, complexity, clarity,
consistency, logic_strategy, feasibility, testability, risk_mitigation), starting
*all* dimensions at `LOW`, then researches and refines upward.

```bash
ll-loop run rn-plan "build a rate-limiting middleware for the API"
```

**`rn-refine` — recursively deepen an existing plan.** Give it a path to a draft
`.md` plan (from `rn-plan`, `/ll:iterate-plan`, or written by hand). Unlike a flat
whole-document pass, `rn-refine` treats the plan as the **root of a decomposition
tree** and refines it recursively to adaptive depth: it refines each node, then
decides whether the node is atomic (a leaf) or bundles independent sub-goals worth
splitting into their own focused sub-plans (ADaPT-style — depth grows only where
complexity warrants, bounded by `max_depth`/`max_nodes`). Children are refined
depth-first, then rolled **bottom-up** into a reassembled plan — the integration
phase runs **in parallel**: `synth_dispatch` background-spawns up to `synth_workers`
(default 4) `oracles/integrate-node` workers that pop from a shared queue under a
readiness gate (a node integrates only once all its children have, so same-depth
nodes fold up concurrently). Per-node work is delegated to the
`oracles/plan-node-refine` sub-loop, which itself reuses the same research/synthesize
chain as `rn-plan`. Before writing, a `preflight_check` state verifies invariants
(ENH-2418) and can abort rather than risk a destructive write; once it passes,
`finalize` first writes a timestamped backup (`${run_dir}/source-backup-<ISO>.md`)
and then **overwrites the original file in place** — no manual copy out of
`.loops/` needed, and the backup means the pre-refine version isn't lost.

```bash
ll-loop run rn-refine ".loops/runs/rn-plan-20260526T143022/plan.md"
```

If a long run is interrupted, resume it with the same flags regardless of which
phase was in flight — re-pass the same plan and run dir:

```bash
ll-loop run rn-refine "path/to/plan.md" --context resume=1 --context run_dir=<prior-run-dir>
```

`check_resume` reconciles against on-disk state to pick the right re-entry point
(BUG-2610): if the tree was fully refined (every visited node has a completion
marker and the queue is empty), resume rebuilds the integration queue from which
nodes still lack a `final.md`, so already-refined and already-integrated work is
reused (ENH-2565). If the interruption instead landed **mid-walk** — refinement
itself was killed, e.g. via `ll-loop stop` — resume re-queues the in-flight node
(and any other visited-but-incomplete node) and continues the walk from durable
on-disk state before ever reaching synthesis, rather than treating the tree as
though it were done. Omitting `--context resume=1` against a `run_dir` that
already has a `nodes/` tree is refused (exit 1 with a hint) instead of
re-seeding and destroying the prior work.

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
  → is it blocked_by an unfinished dep?           → defer
  → does it have unproven learning_tests_required? → defer (prove with /ll:explore-api)
  → is it deeper than max_depth (3)?               → cap
  → is it already done/cancelled?                  → skip
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
                          Note: the refine action uses two states —
                          refine_first (REFINE-diagnosis path, uses --full-rewrite)
                          and refine_followup (all other refine callers, no --full-rewrite)
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
| `IMPLEMENTED` | Issue implemented. FEAT-2552: `rn-remediate`'s inner code-run-gate oracle passed (build / test / typecheck / lint / health all green), or all commands were null/empty (`GATE_SKIP` from the oracle, which `rn-remediate`'s own gate-child routing treats identically to `GATE_PASS` before ever writing the parent-visible sidecar) — so `GATE_SKIP` never appears as a distinct token in this table; it's folded into `IMPLEMENTED` upstream. | `route_rem_implemented` → `re_enqueue_unblocked`, continue |
| `GATE_FAILED` | FEAT-2552: code-run-gate oracle reported a non-skip failure (build / test / typecheck / lint / health). Written by `rn-remediate.record_gate_failure`. Increments the same `remediation_count_<ID>.txt` counter that `check_remediation_budget` enforces, so a gate failure consumes a budget slot. Tagged `GATE_FAILED_CODE_QUALITY` in `failures.txt` for the report's per-tag tally. | `route_rem_gate_failed` → `record_failure`, dequeue next |
| `GATE_FAILED_INFRA` | FEAT-2552 / ENH-2005 mirror: code-run-gate child crashed / timed out / context-resolution-failed before writing its token. Written by `rn-remediate.record_gate_error`. Distinct from `GATE_FAILED` so a gate infrastructure failure isn't confused with a code-quality failure, but it is **not** a separate terminal — the `GATE_FAILED` substring match in `route_rem_gate_failed` also catches it, so it routes the same way. | `route_rem_gate_failed` → `record_failure` (tagged `GATE_FAILED_INFRA` in `failures.txt`), dequeue next |
| `NEEDS_DECOMPOSE` | Issue too large | Delegate to `rn-decompose` |
| `STALLED_NEEDS_DECOMPOSE` | Remediation exhausted its budget | Try `rn-decompose`; if no children, defer |
| `MANUAL_REVIEW_NEEDED` | Needs a human decision | Mark blocked |
| `MANUAL_REVIEW_RECOMMENDED` | `decision_needed: true` but `/ll:decide-issue` found zero enumerable options even after one `/ll:refine-issue --auto` deposit-options retry, and Phase 3b's inline provisional-language scan also found no clear winner (ENH-2443, BUG-2606) — distinct from a genuine human-required decision | Mark blocked (same counter, distinct diagnostic pointing at `/ll:refine-issue`) |
| `RATE_LIMITED` | Host rate limit hit | Record rate-limit diagnostic, continue |
| `IMPLEMENT_FAILED` | Implementation failure | Record failure, continue |
| `SCORES_MISSING` | Diagnostic/tooling failure (confidence or outcome frontmatter unreadable after implementation) | Record diagnostic failure separately, continue |
| `SIZE_REVIEW_FAILED` | `/ll:issue-size-review` errored or was inconclusive during decompose | Record diagnostic failure separately, continue |
| `ENV_NOT_READY` | Host auth not configured (HTTP 401/403 during `ll-auto`) | Abort the queue (ENH-2353) |
| `LEARNING_GATE_BLOCKED` | Learning gate (ENH-2319) blocked the issue on unproven external-API deps | Record diagnostic separately (remedy: `/ll:explore-api`), continue |

The learning-gate routing is **consistent across all three loops that call
`ll-auto --only` directly**: `rn-remediate` (the sub-loop `rn-implement`
delegates to per issue — `rn-implement` itself makes no LLM/`ll-auto` calls of
its own, see [`rn-implement` — the orchestrator you run](#rn-implement--the-orchestrator-you-run)),
`autodev`, and (via `auto-refine-and-implement` →
`autodev`) `sprint-refine-and-implement` all implement through the same
`ll-auto --only` choke point, which runs the ENH-2319 gate inside
`process_issue_inplace`. On a block, `ll-auto` prints the `LEARNING_GATE_BLOCKED`
marker; each loop screens the captured output (`ll_auto_learning_gate_check`
fragment) *before* the auth/failure checks so a gate block is reported distinctly
rather than laundered into a generic implementation failure. A uniform
`skip_learning_gate` context knob (parity with `ll-auto --skip-learning-gate`)
threads from each loop down to the inner `ll-auto --only` call.

`LEARNING_GATE_BLOCKED` is no longer exclusively a post-implement, `rn-remediate`-
originated token. ENH-2406 added a pre-dequeue gate (`check_learning_ready` /
`route_learning_ready` / `mark_learning_blocked`) directly in `rn-implement`'s
router, ahead of `run_remediation` — a learning-blocked issue can never be fixed
by remediation, so catching it before the issue is even dequeued into a
remediation pass is strictly cheaper. This pre-dequeue catch is tagged with a
distinct `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` token (tallied separately in
`summary.json` as `learning_gate_blocked_pre_dequeue`) so operators can tell free
pre-dequeue catches apart from remediation-spent safety-net catches. The
post-implement `check_learning_gate` classifier in `rn-remediate` remains in
place as defense-in-depth — it still fires for callers that bypass
`rn-implement` entirely, or when a target becomes unproven/stale between the
pre-dequeue check and the inner `ll-auto --only` call.

ENH-2431 gave the pre-dequeue gate a way to resolve the block itself instead of
always dead-ending: `check_learning_ready` attempts `ll-learning-tests prove
<target>` for each unproven target before routing to `mark_learning_blocked` — if
proving succeeds, the issue proceeds to `check_depth` in the same run. A target
that still fails proving falls through to `mark_learning_blocked` as before, which
tags the failure `LEARNING_GATE_BLOCKED_PRE_DEQUEUE_ATTEMPTED` (an additive-suffix
superset of `LEARNING_GATE_BLOCKED_PRE_DEQUEUE`) when a prove attempt was actually
made, so `failures.txt` distinguishes "tried and still stuck" from "never
attempted" without changing `report`'s existing tally arithmetic.

**Auto-prove is config-gated (ENH-2487).** Whether the prove attempt fires is
resolved in three tiers: an explicit per-run `auto_prove_learning_gate` context
flag wins (any non-empty value except an off token — `0`/`false`/`no`/`off`); with
no flag it is config-driven — on when `learning_tests.enabled &&
learning_tests.auto_prove` (`auto_prove` defaults `true`), so a project with the
Learning Test feature enabled gets self-healing auto-prove by default and can opt
out per-project with `learning_tests.auto_prove: false`; otherwise off. ENH-2487
also added the **remediation-path** prove step `prove_rem_learning_gate`: when
`rn-remediate`'s inner `ll-auto --only` emits `LEARNING_GATE_BLOCKED` (the ENH-2319
JIT gate) on a target that only surfaced after remediation, that deeper gate makes
the same config-gated one-attempt prove before `record_learning_gate_blocked`,
rather than dead-ending. Both gate sites share the identical three-tier resolution
and `timeout=1800` prove budget, so decomposed children re-entering the pipeline
get the same behavior at every recursion depth.

**Diagnostic stderr tokens from `check_blocked_by` (ENH-2534).** `rn-implement`'s
`check_blocked_by` state emits three diagnostic tokens to **stderr** immediately
before each silent fail-open exit so `audit-loop-run` and the
`fsm/executor.py:stderr_preview` surface (ENH-2469) can distinguish a real
"READY — proceed" from a degraded empty-parse:

| Token | Meaning |
|-------|---------|
| `UNRESOLVED` | `blocked_by` file exists but no blocker IDs could be resolved (parse failure) |
| `PARSE_ERROR` | The bash wrapper's `$UNMET` capture itself broke (jq / regex failure) |
| `DONE_SET_ERROR` | Issue is already `done` in `.issues/completed/` but also appears in the queue (drift) |

The tokens are emitted **before** the existing silent `sys.exit(0)` fail-open
exits — the fail-open semantics are unchanged (the wrapper stdout still sees
empty `$UNMET`, so `route_blocked_by` still routes `READY → check_depth`), but
the stderr marker is now observable. The legitimate no-deps / READY exit
emits no token.

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

The `summary.json` carries additive structured fields beyond the original 14
scalar counters (ENH-2533): `per_issue` is an array of one record per
`subloop_outcome_<ID>.txt` sidecar (`{id, outcome, reason?}` with optional
`pre_scores` / `post_scores` / `convergence` embeddings) and `learning_followups`
is an array of one record per `learning_unproven_<ID>.txt` sidecar
(`{id, targets, remedy}` where `remedy` is `/ll:explore-api <targets>`).
These make per-issue outcomes and learning-gate followups discoverable
without grepping the sidecars directly; downstream tooling (audit-loop-run's
Step 6b verdict, follow-up runs) reads them via the archived copy under
`.loops/.history/<run_id>-rn-implement/summary.json`. Malformed per-issue
sidecars are surfaced in `summary_warnings.txt` rather than aborting the
report.

> **Tip**: For the full end-to-end pipeline (spec → design → EPIC → eval harness
> → batched implementation → eval gate), use `rn-build` — see its section in the
> [Built-in Loops Reference](LOOPS_REFERENCE.md#rn-build--spec-to-project-capstone-orchestrator).

## See Also

- [Loops Guide](LOOPS_GUIDE.md) — FSM fundamentals: states, evaluators, routing,
  authoring
- [Built-in Loops Reference](LOOPS_REFERENCE.md) — full per-loop catalog: context
  variables, complete FSM flows, and every invocation flag for the `rn-*` loops
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — meta-loop design
  rules and the optimizer error taxonomy
- `ll-loop --help` — full CLI reference for all loop subcommands
