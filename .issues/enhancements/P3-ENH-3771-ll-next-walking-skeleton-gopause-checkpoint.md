---
id: ENH-3771
type: ENH
title: ll-next walking-skeleton go/pause checkpoint
priority: P3
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T20:23:28Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
blocks:
- FEAT-3769
- FEAT-3711
- FEAT-3713
- FEAT-3721
deferred_by: human
deferred_date: '2026-10-07T20:24:42Z'
---

# ENH-3771: ll-next walking-skeleton go/pause checkpoint

## Summary

Maintainer-run go/pause checkpoint for EPIC-3710, split out of FEAT-3561's Implementation Step 5 (2026-10-07 convergence review). FEAT-3561 ends at working code, docs and structural checks; this issue records whether the `implement-issue` + `refine-issue` + `--explain` walking skeleton is useful enough to justify FEAT-3769, FEAT-3721, FEAT-3711 and FEAT-3713. It is `deferred` on purpose and must be run by a human, never by `ll-auto`/`ll-parallel`/`ll-sprint`/`manage-issue`.

## Current Behavior

FEAT-3561 carried the checkpoint as its own Implementation Step 5 and the four follow-ons were `blocked_by: FEAT-3561`. "FEAT-3561 done" therefore meant "follow-ons unblocked" whether or not a maintainer had recorded a GO. Automation marks an issue done when its code is complete (an automated-fallback Resolution has previously marked an issue `done` although the feature was not implemented), so nothing machine-enforced that the human judgment happened before the follow-ons started.

## Expected Behavior

FEAT-3769, FEAT-3721, FEAT-3711 and FEAT-3713 are `blocked_by: ENH-3771`; this issue is `blocked_by: FEAT-3561`. Only a maintainer setting this issue to `done` unblocks them.

Why `deferred` (human): `find_issues` skips `done`/`cancelled`/`deferred` by default, so `next-issue`, `ll-auto`, `ll-parallel` and `ll-sprint` never select it; `deferred` is non-terminal for dependency edges (only `done`/`cancelled` resolve `blocked_by`), so the follow-ons stay blocked. **Never record a PAUSE by cancelling this issue:** `cancelled` resolves the edges and would unblock all four follow-ons.

## Procedure

Run by hand once FEAT-3561 is done, on one recorded backlog snapshot/config/`as_of`.

1. **Record populations before comparing rankings.** Report per-bucket eligible, gate-failed and gate-missing counts and how many issues pass the readiness/outcome gate. As of 2026-10-07 this repo had 45 active non-EPIC issues, only 4 with both scores and 3 passing 85/65, so `--type implement-issue --top 3` against `ll-issues next-issues 3` would compare about three issues. If fewer than 10 issues pass the gate, run `/ll:confidence-check` over a sample of active issues first, chosen by a recorded seed or deterministic rule (e.g. every k-th active non-EPIC issue by sorted ID), never by `next-issues` order, so the comparison is not circular. A recorded fixture backlog of realistic size may supply the mechanics comparisons in steps 2-3 but **not** the usefulness judgment in step 5 criterion 3, which is made on the real backlog (seeded with the sample scores). Say which was used. Never present agreement on a population that small as evidence.
2. **Implement comparison.** Compare `ll-next --type implement-issue --top 3` with `ll-issues next-issues 3`: report eligibility/population differences separately and also compare both ranking rules on the core's common eligible population, so stricter gates are not mistaken for better ranking.
3. **Refine comparison, on the common population** (leaf, `open`/`blocked`, non-ambiguous). `ll-issues next-action` also surfaces EPICs (on 2026-10-07 it printed `NEEDS_VERIFY EPIC-3556`), which `refine-issue` excludes by design, so its raw pick is not directly comparable. (a) **Per-issue step parity**: for every common-population issue, compare the refine adapter's step with what `next-action`'s ordered checks give for that issue; the only expected differences are the documented outcome-waiver policy and captured-policy snapshotting, and each other difference is explained with `--explain`. (b) Report the baseline's raw single pick separately, noting whether it is in the common population.
4. **Inspect mixed output.** Review default `ll-next` output, `--top 10`, and fixed scenarios with ready, unready, blocked and cold-start targets for usable complete actions, per-verb counts, availability and explanations.
5. **Record and decide.** Write the comparisons, populations and snapshot/config/`as_of` in Resolution notes, then a maintainer **GO** or **PAUSE** using this rubric. GO requires: (1) every selected recommendation carries a complete copyable action; (2) `--explain` lets the maintainer reproduce the rank of three sampled targets by hand; (3) the maintainer judges the mixed output (real backlog) more useful than running `next-issues` and `next-action` separately. "More useful after change X" is **not** a GO: file X as an issue under EPIC-3710, make this issue `blocked_by` it, and repeat steps 4-5 after it lands. Record any recommendation judged clearly wrong with its cause.
   - **GO:** `ll-issues set-status ENH-3771 done`. This is the only action that unblocks the follow-ons.
   - **PAUSE:** record what would have to change, leave this issue `deferred`, and re-scope EPIC-3710 before starting any follow-on.

Agreement within the implementation bucket alone is not evidence the cross-verb arena lacks value, and `next-issue` has no refinement ranking. The cancelled FEAT-3712 requires no implementation or checkpoint.

This checkpoint supplies usefulness evidence for [EPIC-3710's adoption and migration policy](../epics/P3-EPIC-3710-ll-next-next-action-arena.md#adoption-and-migration). After a recorded GO, use the observed output and eligibility differences to inform the separate migration assessment. A GO does not establish that `ll-next` replaces existing selector contracts or authorize their deprecation; migration work does not expand this checkpoint's rubric.

## Impact

- **Priority**: P3 - gates four follow-on slices.
- **Effort**: Small - maintainer time plus optional sample scoring.
- **Risk**: Low - read-only comparison; the risk it removes is building loop, history and event machinery on an unproven arena.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] FEAT-3561 is done and `ll-next` runs on the real backlog (default output, `--top 10`, `--type`, `--explain`).
- [ ] Resolution records per-bucket populations; the gate-passing implement population with the sample-scoring rule/seed (or fixture) used; the implement-only top-3 comparison against `ll-issues next-issues 3` (population differences separate, common-population ranking comparison); refine per-issue step parity on the common population plus the raw baseline pick; mixed output and scenario evidence; snapshot/config/`as_of`.
- [ ] A maintainer GO or PAUSE is recorded using the rubric. GO sets `status: done`; PAUSE leaves the issue `deferred` and re-scopes EPIC-3710 before any follow-on starts.
- [ ] No follow-on (FEAT-3769, FEAT-3721, FEAT-3711, FEAT-3713) starts before a recorded GO.

## Related

- EPIC-3710 (parent). FEAT-3561 (blocker; implementation and `--explain`). FEAT-3769, FEAT-3721, FEAT-3711, FEAT-3713 (blocked by this checkpoint).

## Status

**Deferred** (human; awaiting FEAT-3561) | Created: 2026-10-07 | Priority: P3
