---
id: ENH-3771
type: ENH
title: ll-next walking-skeleton go/pause checkpoint
priority: P3
status: cancelled
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T20:23:28Z'
parent: EPIC-3710
blocked_by: []
blocks: []
deferred_by: human
deferred_date: '2026-10-07T20:24:42Z'
---

# ENH-3771: ll-next walking-skeleton go/pause checkpoint

> **Cancelled as a gate (2026-10-07).** The maintainer decided to assume GO, so nothing waits on this issue; FEAT-3769, FEAT-3721, FEAT-3711 and FEAT-3713 are `blocked_by` FEAT-3561 again. The procedure below is kept as an optional, non-gating usefulness review to run once `ll-next` works. It was cancelled, not completed, so it carries no GO evidence.

## Summary

Optional maintainer-run usefulness review for EPIC-3710, retained after the go/pause gate was cancelled. Compare the `implement-issue` + `refine-issue` + `--explain` walking skeleton with existing selectors once FEAT-3561 works. This issue stays `cancelled`; its procedure supplies possible tuning evidence, not a dependency, closure requirement or recorded GO.

## Current Behavior

The convergence review briefly made this a human-deferred dependency gate. The maintainer subsequently chose to assume GO and cancelled it. Current frontmatter has no dependency edges; FEAT-3769 and FEAT-3721 depend on core completion, and FEAT-3711/FEAT-3713 also depend on both of those slices.

## Expected Behavior

Implementation follows EPIC-3710's current dependency order without waiting for this review. If the maintainer chooses to run it, record observations and file actionable improvements. Do not change this issue's status, reintroduce its dependency edges or treat a missing comparison as a reason to block implementation.

## Procedure

Optionally run by hand once FEAT-3561 is done, on one recorded backlog snapshot/config/`as_of`.

1. **Record populations before comparing rankings.** Report per-bucket eligible, gate-failed and gate-missing counts and how many issues pass the readiness/outcome gate. As of 2026-10-07 this repo had 45 active non-EPIC issues, only 4 with both scores and 3 passing 85/65, so `--type implement-issue --top 3` against `ll-issues next-issues 3` would compare about three issues. If fewer than 10 issues pass the gate, run `/ll:confidence-check` over a sample of active issues first, chosen by a recorded seed or deterministic rule (e.g. every k-th active non-EPIC issue by sorted ID), never by `next-issues` order, so the comparison is not circular. A recorded fixture backlog of realistic size may supply the mechanics comparisons in steps 2-3 but **not** the usefulness judgment in step 5 criterion 3, which is made on the real backlog (seeded with the sample scores). Say which was used. Never present agreement on a population that small as evidence.
2. **Implement comparison.** Compare `ll-next --type implement-issue --top 3` with `ll-issues next-issues 3`: report eligibility/population differences separately and also compare both ranking rules on the core's common eligible population, so stricter gates are not mistaken for better ranking.
3. **Refine comparison, on the common population** (leaf, `open`/`blocked`, non-ambiguous). `ll-issues next-action` also surfaces EPICs (on 2026-10-07 it printed `NEEDS_VERIFY EPIC-3556`), which `refine-issue` excludes by design, so its raw pick is not directly comparable. (a) **Per-issue step parity**: compare the refine adapter's step with what `next-action`'s ordered checks give for that issue. Equality applies when both raw scores are valid in the arena domain, with the documented outcome-waiver and captured-policy exceptions; strict score-domain validation is another intentional difference (e.g. legacy `101/65` can report `ALL_DONE`, while the arena requests `confidence-check`). Explain each other difference with `--explain`. (b) Report the baseline's raw single pick separately, noting whether it is in the common population.
4. **Inspect mixed output.** Review default `ll-next` output, `--top 10`, and fixed scenarios with ready, unready, blocked and cold-start targets for usable complete actions, per-verb counts, availability and explanations.
5. **Record findings.** Write the comparisons, populations and snapshot/config/`as_of` in review notes. Assess whether: (1) every selected recommendation carries a complete copyable action; (2) `--explain` lets the maintainer reproduce the rank of three sampled targets by hand; (3) mixed output on the real backlog is more useful than running `next-issues` and `next-action` separately. Record clearly wrong recommendations with their causes and file improvements. These observations do not change this issue's cancelled status or the follow-ons' dependencies.

Agreement within the implementation bucket alone is not evidence the cross-verb arena lacks value, and `next-issue` has no refinement ranking. The cancelled FEAT-3712 requires no implementation or checkpoint.

If performed, this review supplies usefulness evidence for [EPIC-3710's adoption and migration policy](../epics/P3-EPIC-3710-ll-next-next-action-arena.md#adoption-and-migration). Observed output and eligibility differences can inform the separate migration assessment; they do not establish that `ll-next` replaces existing selector contracts or authorize their deprecation.

## Impact

- **Priority**: P3 - optional evidence for tuning and later migration assessment.
- **Effort**: Small - maintainer time plus optional sample scoring.
- **Risk**: Low - comparisons are read-only; optional sample scoring updates the selected issues through the existing command.
- **Breaking Change**: No

## Acceptance Criteria

These are an optional review checklist retained for reference, not conditions for changing this cancelled issue's status or unblocking implementation.

- [ ] FEAT-3561 is done and `ll-next` runs on the real backlog (default output, `--top 10`, `--type`, `--explain`).
- [ ] Review notes record per-bucket populations; the gate-passing implement population with the sample-scoring rule/seed (or fixture) used; the implement-only top-3 comparison against `ll-issues next-issues 3` (population differences separate, common-population ranking comparison); refine per-issue step parity and intentional policy differences plus the raw baseline pick; mixed output and scenario evidence; snapshot/config/`as_of`.
- [ ] Useful observations and any clearly wrong recommendations are recorded, with actionable improvements filed separately.

## Related

- EPIC-3710 (parent). FEAT-3561 (supplies implementation and `--explain`). FEAT-3769, FEAT-3721, FEAT-3711 and FEAT-3713 (independent of this optional review).

## Status

**Cancelled** (gate dropped by maintainer decision) | Created: 2026-10-07 | Priority: P3
