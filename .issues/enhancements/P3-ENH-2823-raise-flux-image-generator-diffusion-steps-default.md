---
id: ENH-2823
type: ENH
priority: P3
status: open
captured_at: '2026-07-26T01:54:53Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels: [loops, flux, defaults]
relates_to: [BUG-2822, FEAT-2817]
---

# ENH-2823: Raise `flux-image-generator`'s `steps` default from 4 to ~20

## Summary

`flux-image-generator.yaml` defaults `steps: 4` (diffusion steps per generation).
Four steps is a fast-preview setting. The audited run's rubric failures were
uniformly *sampler-quality* complaints, not prompt-semantics complaints — a class
of defect that prompt refinement cannot fix at any iteration count, so the loop
spends its whole budget rewording a prompt against a ceiling set by the step
count.

Evidence: `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md`.

## Current Behavior

```yaml
context:
  pass_threshold: 6
  steps: 4                    # diffusion steps per generation
  base_seed: 1
```

`steps` is interpolated into the child oracle as `FLUX_STEPS` and reaches the
endpoint in the `synthesize` POST body. Both scored iterations of the audited run
landed below the `pass_threshold: 6` bar (means `5.8` then `5.4`), and both
critiques attributed the gap to render quality. From `critique.md`, verbatim:

> "artifact_freedom: 5/10 — Several visible problems: (1) state nodes have soft
> shadows that read as 3D pucks rather than flat badges, violating the \"no 3D
> puck nodes\" rule; ... (4) the plates themselves carry subtle edge
> gradients/bevels rather than reading as truly flat."

> "style_adherence: 4/10 — ... The render instead shows clear soft drop shadows
> under nodes, gradient-like depth on plate edges, and a slight glossy highlight
> on the teal orchestrator plate. It looks more like a polished UI /
> skeuomorphic illustration than the engineering flat-vector infographic
> requested."

Soft shadows, edge gradients, and gloss on a brief that asked for flat vector are
under-denoising signatures. The prompt-refinement loop cannot reach them: the
`generate` state can only change wording, and the wording was already correct.

## Expected Behavior

The shipped default produces images the rubric can plausibly pass on a
flat-vector or technical-diagram brief — the loop's stated primary use case. A
caller who wants fast previews can still set `steps` down via `context`, which is
the direction that should require an explicit opt-in.

## Motivation

The `steps` default silently sets the ceiling on every score the loop can
achieve. Left at 4, the harness can burn its entire (already tight — see
[[BUG-2822]]) budget on iterations that were never going to converge, and the
resulting `partial`/`failed` verdict misattributes a sampler-budget problem to
prompt quality. This is a one-line change with a large effect on whether the loop
is useful out of the box.

## Proposed Solution

```yaml
 context:
   description: ""
   pass_threshold: 6
-  steps: 4                    # diffusion steps per generation
+  steps: 20                   # diffusion steps per generation; 4 is a
+                              # fast-preview setting that cannot reach the
+                              # flat-vector crispness most briefs ask for
   base_seed: 1
```

Worth validating empirically before committing to the number: run the same brief
at `steps: 4`, `12`, and `20` against the same `base_seed` and compare the rubric
means. If the gain flattens before 20, take the knee. The generation-time cost
scales roughly linearly with steps, so this trades wall-clock per iteration
against iterations needed — the audited run suggests that trade is currently
badly mispriced.

The `synthesize` heredoc already coerces `FLUX_STEPS` safely
(`int(os.environ.get("FLUX_STEPS") or 4)`), so no code change is needed — but
note that fallback literal `4` should move in step with the context default to
avoid the two disagreeing.

## Scope Boundaries

**In scope**: the `steps` default in `flux-image-generator.yaml` and the matching
`context.steps` / `int(... or 4)` fallback in `oracles/generator-evaluator-flux.yaml`,
plus the empirical comparison that picks the number, plus any doc that states the
default.

**Out of scope**:
- `base_seed` and `pass_threshold` — untouched.
- The budget starvation that made the audited run terminate early: [[BUG-2822]].
- Any change to the rubric, the prompt-authoring instructions, or the
  `vision_gate` critic. This issue asserts the *sampler* was the constraint; it
  does not re-tune the evaluators.
- Other visual harnesses (`svg-image-generator` etc.) — they do not use `steps`.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/flux-image-generator.yaml` | `context.steps` default |
| `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` | `context.steps` default + the `int(... or 4)` fallback in `synthesize` |
| `docs/guides/LOOPS_REFERENCE.md` | update the documented default if it is stated there |

## Implementation Steps

1. Run the 4 / 12 / 20 comparison at a fixed `base_seed` on a representative
   flat-vector brief; record the rubric means.
2. Set the default to the knee of that curve.
3. Align the `synthesize` fallback literal with the new default.
4. Update the loop docs.

## Impact

- **Severity**: P3. Quality-of-default, not correctness.
- **Blast radius**: `flux-image-generator` and its oracle only. No other loop
  reads `steps`.
- **Risk**: low. Slower per generation; no behavioural or structural change.
- **Dependency**: best measured *after* [[BUG-2822]] raises the budget, since the
  comparison run needs enough headroom to complete scored iterations.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/audit-loop-run-flux-image-generator-2026-07-26T011622.md` | Source audit; verbatim critique quotes |
| `docs/guides/LOOPS_REFERENCE.md` | Loop catalog entry |

## Session Log
- `/ll:capture-issue` - 2026-07-26T01:54:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bbb9637-e022-4716-b2c1-d8b3f35b1152.jsonl`

---

## Status

- [ ] Open
