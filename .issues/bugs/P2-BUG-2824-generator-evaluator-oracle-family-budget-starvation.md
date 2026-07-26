---
id: BUG-2824
type: BUG
priority: P2
status: open
captured_at: '2026-07-26T01:54:53Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels: [fsm, loops, max-steps, generator-evaluator]
relates_to: [BUG-2822, BUG-2815, ENH-2814]
---

# BUG-2824: `generator-evaluator` oracle gives every wrapper ~2.8 scored cycles and no `on_max_steps`

## Summary

`oracles/generator-evaluator.yaml` sets `max_steps: 20` against a **7-state
cycle**, yielding ~2.8 scored iterations before the step cap — and defines no
`on_max_steps` handler, so exhaustion is indistinguishable from a crash. Every
wrapper built on this oracle inherits both defects.

This is the family-wide generalization of [[BUG-2822]] (which covers the flux
variant's 8-state cycle in isolation). It also **extends audit §2.1** in
`thoughts/builtin-loops-audit-2026-07-24.md`: that document's "too tight"
`max_steps` table lists `adversarial-redesign`, `cua-agent-desktop`,
`refine-to-ready-issue`, `rn-build`, `sprint-build-and-validate` and
`workflow-generator` — the generator-evaluator family is **not** in it, because
the audit compared budget against *state count* rather than against *cycle cost ×
intended iterations*. For a deliberately cyclic oracle, state count is the wrong
denominator.

## Current Behavior

Resolved-FSM load (`from:` inheritance expanded):

```
oracles/generator-evaluator        max_steps=20  on_max_steps=None  nstates=9
oracles/generator-evaluator-flux   max_steps=20  on_max_steps=None  nstates=10
```

The base cycle costs 7 states:

```
generate → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
```

20 ÷ 7 ≈ 2.8 cycles. The oracle's own stall guards are calibrated for more than
that: `check_stall` uses `score_stall` with `max_stall: 2` and `check_diff_stall`
uses `diff_stall` with `max_stall: 3`. A `diff_stall` of 3 **cannot fire before
the step cap does** — the plateau detector is structurally unreachable, so the
loop cannot distinguish "converged" from "ran out of budget."

Direct wrappers of the base oracle and their own top-level budgets:

| Wrapper | own `max_steps` |
|---|---|
| `svg-image-generator` | 20 |
| `html-website-generator` | 12 |
| `openscad-model-generator` | 20 |
| `canvas-sketch-generator` | 40 |
| `interactive-component-generator` | 120 |
| `hitl-md`, `hitl-compare`, `html-anything` | (via oracle) |
| `oracles/generator-evaluator-cli`, `oracles/generator-evaluator-flux` | `from:` inheritors |

Note the parent budgets are largely irrelevant to the symptom: **a sub-loop
resolves its own `max_steps`; it does not inherit the caller's.** The 20 in the
oracle is what binds, whatever the wrapper declares. This was the single most
misleading thing about the flux audit, which proposed patching the wrapper.

Interacts with an already-recorded finding — audit §3.5:
`oracles/generator-evaluator::record_score` is a `next:`-only shell state with no
`on_error`, so any failure silently skips the `.score_history` append,
`check_stall` sees a short history, and the plateau detector never fires. Budget
starvation and the disarmed stall gate compound: the loop cannot converge early
*and* cannot survive to its cap productively.

## Steps to Reproduce

Structural, no run required:

```bash
python3 -c "
import logging, pathlib, little_loops.loops as L
from little_loops.cli.loop._helpers import load_loop
d = pathlib.Path(L.__file__).parent
for n in ['oracles/generator-evaluator', 'oracles/generator-evaluator-flux']:
    f = load_loop(n, d, logging.getLogger('x'))
    print(n, 'max_steps=', f.max_steps, 'on_max_steps=', f.on_max_steps)
"
# → oracles/generator-evaluator       max_steps= 20 on_max_steps= None
# → oracles/generator-evaluator-flux  max_steps= 20 on_max_steps= None
```

Then compare against the declared cycle: 7 states in the base oracle, and
`check_diff_stall`'s `max_stall: 3` — 3 stall rounds × 7 states = 21 > 20, so the
plateau detector cannot fire before the cap. The arithmetic is the reproduction.

## Expected Behavior

1. The oracle's budget is expressed against its cycle cost and intended iteration
   count, not copied. At 7 states, a 5-iteration intent is ~35–40 steps.
2. `check_diff_stall`'s `max_stall: 3` is reachable — the plateau detector, which
   is the oracle's designed early-exit, actually gets a chance to fire.
3. An exhausted oracle writes a best-so-far verdict via `on_max_steps` rather
   than dead-ending, so callers can distinguish exhaustion from error and salvage
   the artifacts produced.
4. Whatever calibration is chosen is *verified*, not asserted — the repo already
   ships `ll-loop calibrate-budget` and `ll-loop diagnose-evaluators` for exactly
   this, and audit §2.1 notes they are unused.

## Motivation

This oracle is the shared substrate for the entire visual-generation harness
family. A miscalibration here silently caps the quality ceiling of 8+ built-in
loops at once, and does so invisibly: the loops produce output, so nothing looks
broken. The flux run that surfaced this reported `failed` while holding a
perfectly good generated image on disk, having burned three rounds of GPU spend.

Fixing it in the base oracle fixes every wrapper at once. Fixing it per-wrapper
(as the flux audit proposed) fixes none of them, because the wrapper's budget is
not what binds.

## Proposed Solution

Scope this as a calibration pass over the family rather than a single edit:

1. **Measure before choosing numbers.** Run `ll-loop calibrate-budget` on the
   oracle and its heaviest wrappers, and `ll-loop diagnose-evaluators` to confirm
   `score_stall`/`diff_stall` verdicts actually vary (Bernoulli variance
   `p*(1-p)` ≥ 0.05 across ≥10 runs). Per `.claude/CLAUDE.md`, raising budget
   against a toothless evaluator earns nothing — and §3.5 gives concrete reason to
   suspect this evaluator *is* currently toothless.
2. **Set the oracle's budget from cycle cost × intended iterations**, and record
   the arithmetic in a comment so the next copy-paste inherits the reasoning
   rather than the number.
3. **Add an `on_max_steps` summary state** to the base oracle. Per BUG-158
   semantics (`executor.py:590-601`) a terminal doubling as the `on_max_steps`
   handler *does* execute its action — this is the sanctioned live-terminal shape
   and is exempt from [[BUG-2813]]. Wrappers inherit it for free.
4. **Fix §3.5's missing `on_error` on `record_score`** in the same arc — the
   stall gate must be armed before extra budget is worth anything.
5. **Evaluate the score-before-snapshot reorder** deferred from [[BUG-2822]]:
   moving `score`/`record_score` to directly follow `evaluate` means a budget cut
   can never orphan a generated-but-unscored artifact. This is a cycle-order
   change in shared code — validate against every wrapper before adopting.
6. **Audit the wrapper budgets** for the same copy-paste smell now that the
   binding constraint is understood — `html-website-generator`'s 12 and
   `interactive-component-generator`'s 120 are unlikely to both be calibrated.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/oracles/generator-evaluator.yaml` | `max_steps` recalibration; `on_max_steps` summary state; `on_error` on `record_score`; possible cycle reorder |
| `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml`, `generator-evaluator-cli.yaml` | verify `from:` inheritors pick up the changes; keep flux's own override consistent with [[BUG-2822]] |
| `svg-image-generator`, `html-website-generator`, `openscad-model-generator`, `canvas-sketch-generator`, `interactive-component-generator`, `hitl-md`, `hitl-compare`, `html-anything` | wrapper budget audit |
| `scripts/tests/test_builtin_loops.py` | assert resolved oracle budget covers ≥ N cycles and `on_max_steps` is set, so the regression cannot recur silently |

## Implementation Steps

1. Run `ll-loop diagnose-evaluators oracles/generator-evaluator` — establish
   whether the stall evaluators discriminate at all before spending budget.
2. Fix `record_score`'s missing `on_error` (§3.5); re-run the diagnosis.
3. Run `ll-loop calibrate-budget` on the oracle; set `max_steps` from the result.
4. Add the `on_max_steps` summary state; verify inheritance reaches both `from:`
   children.
5. Sweep wrapper budgets against the now-known cycle cost.
6. Add the structural regression test to `test_builtin_loops.py`.
7. `ll-loop validate` across the whole family.

## Impact

- **Severity**: P2. Silent quality ceiling across 8+ built-in loops; each affected
  run wastes real generation spend.
- **Blast radius**: wide — this is shared oracle code. Every change needs
  validation against all wrappers, which is why the calibration and the cycle
  reorder are staged separately here.
- **Risk**: budget increases and an additive `on_max_steps` state are low risk.
  The cycle reorder (step 5) is the one genuinely risky change and can be dropped
  without losing the rest.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` | §2.1 `max_steps` miscalibration (this issue extends its table); §3.5 `record_score` missing `on_error` |
| `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md` | Run evidence that surfaced the family-wide pattern |
| `.claude/CLAUDE.md` § Loop Authoring | `calibrate-budget` / `diagnose-evaluators` guidance before raising `max_steps` |

## Session Log
- `/ll:capture-issue` - 2026-07-26T01:54:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bbb9637-e022-4716-b2c1-d8b3f35b1152.jsonl`

---

## Status

- [ ] Open
