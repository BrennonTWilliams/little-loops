# rn-refine-timeout-finalize-2026-07-09

**Date**: 2026-07-09
**Loop**: `rn-refine`
**Run folder**: `.loops/runs/rn-refine-20260709T134820/`
**Run start**: 2026-07-09T18:48:20+00:00
**Run end**: 2026-07-09T22:54:37+00:00 (wall-clock: 4h 6m 17s)
**Source plan**: `/Users/brennon/AIProjects/MC-vault/dashboard-redesign-and-implement.md`
**Investigator**: `/ll:debug-loop-run rn-refine`

---

## TL;DR

The 2026-07-09T18:48 rn-refine run hit the loop's 14400s (4h) timeout during the
final root-integration step. All 23 non-root nodes produced a `final.md`, but
`nodes/n0/final.md` was never written, the run-dir `plan.md` was never
re-assembled, and the source file was never updated in place. The work itself
is intact and reusable — it just needs the missing n0 integration plus the
`assemble` → `finalize` sequence to land.

---

## What happened

### Refinement phase (success)

- 24 nodes created across 3 depth levels (n0 = root, n1/n2/n3 = depth 1
  branches, n4–n23 = depth 2 leaves; see `depth_map.txt`).
- 18 nodes reached `REFINED_LEAF`; 5 internal nodes (n1, n2, n3, n10, n12)
  triggered `DECOMPOSE`; 0 capped or failed nodes (`capped.txt` empty,
  `failed_nodes.txt` empty).
- 23 of 24 nodes have a non-empty `final.md` (9,896 lines, ~880 KB combined).
- n2 is in the leaves list but its `final.md` exists at 18,382 bytes — minor
  bookkeeping quirk, no functional impact.

### Integration phase (interrupted)

`synth_pop` ran the integration queue deepest-first. The successful
integrations, in event order:

| iter | node | duration |
|---|---|---|
| ~163 | n10 | 136.8 s |
| ~165 | n12 | 155.9 s |
| ~167 | n1 | 192.3 s |
| ~169 | n3 | **736.6 s** (12.3 min) |
| 170 | n0 | — *interrupted* |

Iteration 170's `synth_pop` popped `n0` from the queue (action output: `n0`,
evaluate `output_contains("SYNTH_DONE")` → `no`, route to `integrate_node`),
then the very next event was `loop_complete` with `terminated_by: "timeout"`
and `final_state: "synth_pop"`. The intervening `state_enter: integrate_node`
for n0 never fired. `state.json` for the final `synth_pop` entry carries
`"flushed": true`, indicating the harness terminated between the route and
the next state entry.

### Net effect

- `nodes/n0/final.md` — **does not exist**
- `nodes/n0/plan.md` — exists, 8,239 bytes (root plan at last refinement)
- `.loops/runs/rn-refine-20260709T134820/plan.md` — still 174 bytes (the
  original task title from `init`); never reassembled
- Source file `/Users/brennon/AIProjects/MC-vault/dashboard-redesign-and-implement.md`
  — **unchanged** (no `source-backup-*.md` written under the run dir, which is
  the only side-effect of `finalize`)

### What the timeout left behind that is still useful

All 23 child final.md files. The n0 integration could be performed by hand
using exactly the same prompt the loop's `integrate_node` state uses:

```
Read edges.tsv rows where the first column == "n0" → those are n0's children.
Read nodes/n0/plan.md (root overview) and each child's final.md.
Write nodes/n0/final.md as a single integrated section per the integrate_node
prompt body (verbatim from rn-refine.yaml).
```

After that, `cp nodes/n0/final.md plan.md`, then `final_score` →
`preflight_check` → `finalize` can run. The full pipeline is not lost — just
suspended on the root integration.

---

## Root cause

The loop's `timeout: 14400` (4h) was insufficient for a 24-node tree with
`max_depth: 3` and `max_node_iters: 2`. The integration step is the dominant
late-stage cost:

- Internal-node integration requires reading 1 parent's `plan.md` plus every
  child's `final.md`, and emitting a coherent rewrite. Each internal node's
  children summed to ~50–150 KB of input by the bottom of the tree.
- n3 was the integration worst case (5 children at depth 2 with full
  refinements): 736.6 s, producing 130 KB of integrated content.
- Integration runs serially in `synth_pop`. n10→n12→n1→n3 took ~1,222 s
  cumulative; n0 (root, 4 direct children: n1, n2, n3, and an implicit
  re-roll of children-of-n2) would have been at least as expensive as n3.

---

## Why didn't the loop create a final plan file

1. `integrate_node` for `n0` was never executed (timeout between route and
   state_enter).
2. Without `nodes/n0/final.md`, `assemble`'s preferred branch (`cp
   nodes/n0/final.md plan.md`) would have failed; the elif branch (`cp
   nodes/n0/plan.md plan.md`) would have copied an un-integrated root.
3. `final_score` → `preflight_check` → `finalize` → `report` never ran because
   the loop died in `synth_pop`.
4. `finalize` is the only state that writes back to the source file, so the
   source stayed untouched.

---

## Recommendations (in priority order)

### R1. Raise the loop timeout (or make it configurable per-run)

`timeout: 14400` in `rn-refine.yaml` is too tight for a 24-node, 3-deep tree
with full bottom-up integration. Either:

- **R1a**: bump the default to `21600` (6h), OR
- **R1b**: make it a context parameter like `max_depth` / `max_nodes` so
  per-run overrides are possible without editing the loop YAML.

R1a is the lower-friction fix; R1b is the right long-term shape but requires
parameter wiring.

### R2. Parallelize internal-node integration

`synth_pop` currently dequeues one node at a time and runs `integrate_node`
serially. Internal nodes at the same depth are independent (their children
are disjoint by construction), so they can be integrated concurrently — at
minimum, fan out across the 4 internal nodes at depth 1 (n1, n2, n3, n10,
n12). Concretely: instead of one `synth_pop → integrate_node` flow, use a
loop with multiple worker sub-loops, or split `synth_queue.txt` into a
worker-pool dispatch.

A 4× parallelism on integration would have shaved ~1,000 s off this run,
turning the 4h6m wall-clock into ~3h25m — comfortably under the 4h cap.

### R3. Add a best-effort fallback in `synth_pop` / `assemble`

When the run is approaching the global timeout (or already in a tail-end
state), fall back to a degraded assembly:

- If `nodes/n0/final.md` is missing but `nodes/n0/plan.md` exists, copy
  `plan.md` to `plan.md` (the existing elif branch) — and write a clear
  `RECOVERY_NEEDED` marker into `plan-rubric.md` so the operator knows the
  plan is the *refined* version, not the *integrated* version.
- Optionally, in `finalize`, gate source-write behind a stricter preflight
  that warns the operator the integration is incomplete.

This guarantees the user gets *something* written back to the source instead
of a silent timeout.

### R4. Persist `final.md` snapshots to `.loops/diagnostics/`

Currently, on timeout, the entire run is archived to `.loops/.history/` only
on graceful exit (per the observation in `autodev-bug2501-kill-analysis.md`).
In this case the history folder *does* exist because the run hit a graceful
timeout (not SIGKILL), so we got lucky. To make this robust:

- After every successful `integrate_node`, copy `nodes/<id>/final.md` to
  `.loops/diagnostics/<run-id>-<node-id>.md`.
- On resume (R5 below), these snapshots are the inputs the integration step
  can re-use without redoing the whole refinement tree.

### R5. Support resume from "integration interrupted" state

Add a `--resume` (or auto-detect) mode that:

- Reads the run dir's existing `nodes/<id>/final.md` files
- Re-builds `synth_queue.txt` for any internal node whose `final.md` is
  missing
- Skips refinement entirely and goes straight to `synth_pop` → `integrate_node`
  → `assemble` → `finalize`

Combined with R4, this means a timeout never wastes the work — the operator
re-runs once and gets the integration completed.

---

## Suggested follow-up

Create a BUG issue in the MC-vault `.issues/bugs/` for the timeout, then
either:

- **Quick path**: re-run `ll-loop run rn-refine <source-plan>` with R1a in
  place (~10 min fix in `rn-refine.yaml`).
- **Operator path**: hand-execute the n0 integration using the existing 23
  child `final.md` files, run `cp nodes/n0/final.md plan.md`, then run the
  remaining `assemble → finalize` sequence manually — but the loop does not
  currently expose individual states, so this requires ad-hoc Python or a
  feature for "resume from state".

For now, the simplest fix is R1a + R3: bump the timeout and add a degraded
fallback so future runs of this scale either complete or produce a partial
result the operator can recover from.