---
id: BUG-2822
type: BUG
priority: P2
status: open
captured_at: '2026-07-26T01:54:53Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels: [fsm, loops, max-steps, flux, generator-evaluator]
relates_to: [BUG-2815, FEAT-2817, ENH-2814]
---

# BUG-2822: `generator-evaluator-flux` starves at 2.5 cycles and discards a generated image on budget exhaustion

## Summary

`oracles/generator-evaluator-flux.yaml` inherits `max_steps: 20` from
`generator-evaluator` but adds a `synthesize` state, making its cycle **8 states
long** — 20 ÷ 8 = 2.5 cycles. The oracle is architecturally incapable of
completing a third *scored* iteration regardless of image quality. It also has no
`on_max_steps` handler, so an exhausted child is indistinguishable from a crash:
the parent's `run_gen_eval` routes `on_no → diagnose → failed` and throws away a
completed, on-disk FLUX image.

Evidence: `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md`
(`/ll:audit-loop-run` on run `2026-07-26T011622`, verdict `partial`).

Same defect class as [[BUG-2815]] (`evaluation-quality`), different loop. The
family-wide version of the budget half is tracked separately in BUG-2824.

## Current Behavior

Verified by loading the resolved FSMs (`ll-loop` loader, `from:` inheritance
expanded):

```
oracles/generator-evaluator-flux   max_steps=20  on_max_steps=None  nstates=10
oracles/generator-evaluator        max_steps=20  on_max_steps=None  nstates=9
flux-image-generator               max_steps=20  on_max_steps=None  nstates=8
```

The child's cycle:

```
generate → synthesize → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
```

Observed run trace (from the audited `events.jsonl`, 181 lines):

```
cycle 1: generate → synthesize → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
cycle 2: generate → synthesize → evaluate → snapshot → score → record_score → check_stall → check_diff_stall
cycle 3: generate → synthesize → evaluate → snapshot   ← BUDGET EXHAUSTED at step 20
```

```json
{"event":"loop_complete","final_state":"score","iterations":20,"terminated_by":"max_steps","depth":1}
{"event":"loop_complete","final_state":"failed","iterations":5,"terminated_by":"terminal"}
```

Consequences observed on disk in the run dir:

- `image-iter-3.png` (607,499 bytes, `seed=1023760`) was generated but **never
  scored** — no `critique.md` entry, no `.score_history` line.
- `.score_history` holds only `5.8` and `5.4` against `pass_threshold: 6`.
- `grep -c max_steps_summary events.jsonl` → `0`.
- `vision_gate` — the only external, non-self-certifying evaluator — **never
  ran**, despite `VISION_*` being configured. `.vision_rounds` does not exist.
- Parent utilization was 5/20 (0.25); the child's was 20/20 (1.00). Every one of
  the 24 `action_complete` events carried `exit_code: 0` — nothing actually
  failed.

**Critical detail for whoever fixes this**: the audit document's own diff targets
`flux-image-generator.yaml`'s `max_steps`. That is the **wrong file**. Each loop
resolves its own `max_steps`; a sub-loop does not inherit the parent's. Raising
the parent's budget alone would not have changed this run at all.

## Steps to Reproduce

Structural (no FLUX endpoint required):

```bash
python3 -c "
import logging, pathlib, little_loops.loops as L
from little_loops.cli.loop._helpers import load_loop
d = pathlib.Path(L.__file__).parent
f = load_loop('oracles/generator-evaluator-flux', d, logging.getLogger('x'))
print('max_steps=', f.max_steps, 'on_max_steps=', f.on_max_steps)
"
# → max_steps= 20 on_max_steps= None
```

The cycle is 8 states (`generate → synthesize → evaluate → snapshot → score →
record_score → check_stall → check_diff_stall`), so 20 ÷ 8 = 2.5 cycles. No run
is needed to observe the ceiling.

Behavioural (requires `IMAGE_BASE_URL`): run
`ll-loop run flux-image-generator` on any brief that will not pass the rubric in
two rounds, then inspect the run dir — `.gen_counter` will exceed the line count
of `.score_history`, and `grep -c max_steps_summary events.jsonl` returns `0`.

## Expected Behavior

1. The child oracle's budget accommodates its intended iteration count — at 8
   states per cycle, `max_steps: 60` buys ~7 full scored cycles, which is the
   headroom `check_stall` (`score_stall`, `max_stall: 2`) and `check_diff_stall`
   (`max_stall: 3`) were calibrated to consume.
2. Budget exhaustion is a distinct, reported outcome, not a silent crash. An
   exhausted child writes a best-so-far verdict via an `on_max_steps` summary
   state so the parent can report partial success and surface the images that
   were produced.
3. A generated-but-unscored image is never orphaned by a budget cut.
4. `synthesize` fails loudly when `image-prompt.txt` is **stale** (unchanged
   since the previous iteration), not just when it is missing or empty.

## Motivation

Every wasted cycle here is real GPU spend on a self-hosted diffusion endpoint,
plus an LLM rubric call. This run burned three FLUX generations and delivered a
`failed` verdict while holding a usable image on disk. The loop shipped in
FEAT-2817 (commit `c52d0988`) can, as configured, never converge on any image
requiring more than two refinement rounds — which is most non-trivial briefs.

## Proposed Solution

### 1. Raise the child oracle's budget (`oracles/generator-evaluator-flux.yaml`)

Add a top-level override — the file currently inherits 20 silently via `from:`:

```yaml
 name: generator-evaluator-flux
 from: generator-evaluator
 visibility: internal
+# 8-state cycle (the base 7 + synthesize); 60 ≈ 7 full scored iterations.
+# Overrides the inherited max_steps: 20, which capped this oracle at 2.5 cycles.
+max_steps: 60
```

Also raise `flux-image-generator.yaml`'s own `max_steps: 20`. Its
`vision_gate → run_gen_eval` back-edge costs 2 states per vision round against a
`ROUND_CAP` of 3, and the linear prefix is 4 — the parent cannot currently
complete the vision rounds its own code budgets for.

### 2. Add an `on_max_steps` summary state

Give the flux oracle a summary state that reads `.score_history`, `seeds.txt` and
`.gen_counter`, names the best-scoring iteration, and emits a verdict token the
parent's `run_gen_eval` evaluator can consume as partial success. Per BUG-158
semantics (`executor.py:590-601`), a terminal doubling as the `on_max_steps`
handler *does* execute its action — one of only two live terminal actions in the
corpus — so this is the sanctioned shape and does not fall foul of [[BUG-2813]].

The parent then needs a route that distinguishes "child exhausted with usable
output" from "child errored", instead of collapsing both into
`on_no → diagnose → failed`. Note this interacts with ENH-2814: today a `failed`
terminal exits 0 anyway, so the distinction is currently unobservable downstream.

### 3. Detect a stale prompt file in `synthesize`

`synthesize` already hard-fails on a missing/empty prompt
(`[ ! -s "$PROMPT_FILE" ]`), but not on an unchanged one. Iteration 3's evaluator
returned `partial` with this verdict, verbatim:

> "the file-writing action itself is only supported by a self-report (\"The
> image-prompt.txt has been written (118 words)\") rather than a visible Write
> tool result... the actual file creation cannot be verified from the output
> alone."

Hash `image-prompt.txt` into `.prompt_hash` alongside the existing `.gen_counter`
idiom and emit `IMAGE_FAIL` when the hash is unchanged on iteration ≥ 2 — a
regenerate on an unrewritten prompt burns a full FLUX generation to re-render a
near-identical latent.

**Explicitly rejected** (the audit's recommendation #4): splitting `generate`'s
`on_yes`/`on_no`/`on_partial: synthesize` collapse. That collapse is a
deliberate, documented decision (ENH-1907, commented in both
`generator-evaluator.yaml` and `generator-evaluator-flux.yaml`): routing on the
default judge's read of the agent's *narration* dead-ends the sub-loop
nondeterministically, because a pass that describes its fixes rather than
asserting them earns `partial`. The hash check above is the correct, deterministic
answer to the same concern.

### 4. Score before snapshot (deferred)

The audit also recommends reordering the cycle so `score`/`record_score` follow
`evaluate` directly, so a budget cut can never orphan a generated image. That
ordering lives in the **base** `generator-evaluator`, shared by 6+ wrappers —
it belongs to BUG-2824, not here.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` | `max_steps: 60` override; `on_max_steps` summary state; stale-prompt hash gate in `synthesize` |
| `scripts/little_loops/loops/flux-image-generator.yaml` | raise `max_steps`; route exhausted-with-output distinctly from `run_gen_eval` |
| `scripts/tests/test_flux_image_generator.py` | assert resolved `max_steps` ≥ 8 × intended cycles and `on_max_steps` is set; behavioural test for the stale-prompt failure mode against the existing stub FLUX server |

## Implementation Steps

1. Add the `max_steps` override and `on_max_steps` summary state to the flux
   oracle; confirm with the resolved-FSM load that both take effect through
   `from:` inheritance.
2. Add the stale-prompt hash gate to `synthesize`, reusing the `.gen_counter`
   file-counter idiom already in that Python heredoc.
3. Raise the parent's `max_steps` and add the partial-success route.
4. Extend `test_flux_image_generator.py` with the structural assertions and a
   stale-prompt behavioural case (the stub server harness already exists).
5. Run `ll-loop validate flux-image-generator` and
   `ll-loop validate oracles/generator-evaluator-flux`.

## Impact

- **Severity**: P2. The loop produces output but cannot converge; the failure is
  silent and costs real GPU spend per wasted cycle.
- **Blast radius**: contained to the two flux YAMLs and their test file. The base
  oracle is untouched, so no sibling wrapper regresses.
- **Risk**: low. Budget increases cannot break a passing run; the `on_max_steps`
  state is additive; the hash gate is a new failure mode on a path that currently
  silently wastes a generation.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md` | Source audit; verbatim run evidence |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 / MR-5 rules and validator gates |
| `docs/guides/LOOPS_REFERENCE.md` | Loop catalog entry for `flux-image-generator` |

## Session Log
- `/ll:capture-issue` - 2026-07-26T01:54:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bbb9637-e022-4716-b2c1-d8b3f35b1152.jsonl`

---

## Status

- [ ] Open
