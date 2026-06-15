---
id: EPIC-2167
title: Decision-router as the core routing pattern for automated loops
type: epic
status: open
priority: P2
discovered_date: 2026-06-15
discovered_by: manual
labels: [epic, loops, fsm, routing, decision-table, evaluators, dx]
relates_to: [ENH-2165, ENH-2164, ENH-2166, ENH-2154]
---

# EPIC-2167: Decision-router as the core routing pattern for automated loops

## Summary

Umbrella tracking issue for establishing the **policy-based router + decision
table** as a fundamental, reusable routing primitive across the little-loops
automated-development loops. The goal is that converge / refine / score-and-route
loops — issue refinement, eval harnesses, artifact-generation refinement, plan
optimization, and the recursive orchestrators — express their routing as a
**declarative, priority-ordered decision table** evaluated by a shared engine,
rather than as bespoke shell `if/elif` blocks fanned out into hand-rolled
`output_contains` routing cascades.

The pattern has three structural pieces:
1. **A scorer** (LLM or deterministic) that writes per-dimension scores.
2. **A decision-table engine** that maps `(dimensions) → action-state` via an
   ordered, first-match-wins rule table supporting conjunctive predicates.
3. **A single-state router** that dispatches the engine's emitted token to the
   target state via a `classify` evaluator + a `route:` table.

`rn-remediate`'s `diagnose` / `check_convergence` states are the existing,
shipping, hand-rolled instance of exactly this pattern — they motivate the
abstraction and serve as its first migration target and stress test.

## Children (Foundation phase)

- **ENH-2165** — `classify` evaluator: stdout-token-as-verdict for single-state
  multi-way `route:` dispatch (the L0 executor primitive; unblocks the rest).
- **ENH-2164** — `lib/policy-router.yaml`: the general decision-table engine
  (conjunctive rules, score-source-agnostic input, `classify`-based handoff).
  Grown into the engine role per the 2-layer decision below; `lib/rubric-router`
  (ENH-2154, done) remains the thin single-aggregate preset.
- **ENH-2166** — Migrate `rn-remediate`'s `route_d_*` / `route_conv_*` cascades onto
  `classify` + the engine. The real-world adopter that validates the stack.

## Future Adopters (candidate children — filed in the Adoption phase, not yet)

Deliberately **not** spec'd as issues yet (see "Prove before mandate" below). Each
becomes a concrete child issue only after the pattern is validated by ENH-2166:

- Issue-refinement convergence routing (`/ll:refine-issue` driving loops)
- Eval-harness verdict routing (`ll-harness` / `create-eval-from-issues` outputs)
- Artifact-generation refinement loops (score → tier → repair → re-score)
- `loop-router.yaml` — confidence→loop-selection dispatch (a 1-dimension instance)
- `rn-plan-apo.yaml` — `route_convergence` score→route→repair loop
- `rn-implement.yaml` — parent-side `route_rem_*` / `route_dec_*` token cascades

## Design Decisions (locked)

1. **2-layer stack, not 3.** No separate `lib/decision-router` fragment is created.
   `lib/policy-router.yaml` (ENH-2164) absorbs the general engine role directly
   (conjunctive rules + score-source-agnosticism); `lib/rubric-router` (ENH-2154)
   stays the degenerate single-aggregate preset. Rationale: only one strong
   concrete driver (`rn-remediate`) plus the engine itself need the general grammar
   today — extracting a third fragment would be speculative (YAGNI).
2. **Routing handoff is `classify` + `route:`.** Not the verbose
   `policy_route_<name>` exit-code cascade, and not a new `dynamic_next` executor
   convention. The dispatch fragment emits the winning action-state token; the
   `classify` evaluator (ENH-2165) lifts it to the verdict; the existing `_route()`
   table dispatches. This reuses machinery that already exists.
3. **Deterministic routing on LLM-or-shell scores.** The *scorer* may be an LLM
   (e.g. `confidence-check`, `rubric_score`); the *router* is always deterministic
   shell/Python over the written score files. This keeps the routing layer on the
   right side of the SHOR self-evaluation-bias concern (cf. EPIC-1663 / MR-1).
4. **Prove before mandate.** The pattern is NOT standardized across the fleet until
   ENH-2166 validates it on a real loop. Premature standardization on an unproven
   abstraction is the failure mode this epic explicitly avoids.

## Phased Plan

```
Phase 1 — Prove      ENH-2165 → ENH-2164 → ENH-2166
                     (classify → engine → rn-remediate migration as stress test)
   ↓ extract from the shipped implementation
Phase 2 — Document   Pattern guide in docs/guides/ + LOOPS_GUIDE "Decision-Router"
                     section, written from real code (not hypothetical examples)
   ↓ graduate the provisional decision
Phase 3 — Codify     create-loop "decision-router" template branch + a soft
                     (WARNING) ll-loop validate advisory nudging new converge
                     loops toward the pattern  (the EPIC-1663 playbook)
   ↓ pattern is proven + nudged-by-default
Phase 4 — Adopt      File the Future-Adopter candidates as concrete child issues,
                     one per loop, sequenced by value
```

Phase 1 is the only "now" work; Phases 2–4 are gated on it. A provisional decision
(`.ll/decisions.yaml`, `type: decision`, scope: project) records the intent and is
promotable to an `advisory` rule in Phase 3 via `ll-issues decisions promote`.

## Motivation

- The decision-list routing pattern is currently reimplemented ad-hoc in every
  loop that needs it (`rn-remediate`, `loop-router`, `rn-plan-apo`), each wiring its
  own parse + tier-route + re-entry from scratch — the same boilerplate ENH-2154
  began removing for the single-aggregate case.
- Hand-rolled `output_contains` cascades are verbose (one state per branch),
  order-fragile (substring collisions like `STALLED_NEEDS_DECOMPOSE` vs
  `NEEDS_DECOMPOSE`), and untestable as a unit.
- A shared engine makes routing rules **declarative, diffable, and unit-testable**,
  and makes routing-layer health checks (`diagnose-evaluators`-style) possible.
- This is the direct successor to EPIC-1663's playbook: prove a pattern, document
  it, then codify it as a `create-loop` default + `ll-loop validate` nudge so it
  propagates to new loops by construction.

## Out of Scope

- Mandating the pattern across existing loops before ENH-2166 proves it (Phase 4,
  gated).
- Changes to the FSM executor core beyond the `classify` evaluator (ENH-2165).
- Nested/parenthesized boolean rule grammars, `|`-disjunction within a single rule,
  or probabilistic/weighted rules (v1 uses ordered rows + `&` conjunction).
- Migrating `rn-decompose` (its single branch is not a routing cascade).

## Related Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/rn-remediate.yaml` | Shipping hand-rolled instance; `diagnose` / `check_convergence` cascades; first migration target |
| `scripts/little_loops/loops/lib/rubric-router.yaml` | ENH-2154 — the single-aggregate preset; degenerate case of the engine |
| `scripts/little_loops/fsm/executor.py` (`_route`) | The `route:` table dispatch the pattern builds on |
| `scripts/little_loops/fsm/evaluators.py` | Home of the `classify` evaluator (ENH-2165) |
| `.issues/epics/P2-EPIC-1663-codify-meta-loop-harness-design-rules.md` | Precedent playbook: prove → document → codify as validate rule + wizard branch |
| `docs/guides/LOOPS_GUIDE.md` | Target for the Phase-2 "Decision-Router" pattern section |

## Labels

- epic
- loops
- fsm
- routing
- decision-table
- evaluators
- dx

## Status

**Open** | Created: 2026-06-15 | Priority: P2

## Session Log
- `manual` - 2026-06-15T06:05:00Z - epic scaffolded
