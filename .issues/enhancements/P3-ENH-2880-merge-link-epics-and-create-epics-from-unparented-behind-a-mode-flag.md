---
id: ENH-2880
title: Merge link-epics and create-epics-from-unparented behind a mode flag
type: ENH
priority: P3
status: open
captured_at: "2026-07-28T02:07:33Z"
discovered_date: 2026-07-28
labels:
- skills
relates_to: [ENH-2877]
---

# ENH-2880: Merge link-epics and create-epics-from-unparented behind a mode flag

Follow-up from the ENH-2877 skill-merge audit — Tier 1 candidate C1.

## Summary

`skills/link-epics/` and `skills/create-epics-from-unparented/` are self-declared
inverse operations over an identical input population, using identical scoring
machinery, duplicated as prose across two files. Merge them into one skill with a
`mode` argument (`assign` | `synthesize`).

## Current Behavior

Two skills, both of which:

- start from the same population — open BUG/FEAT/ENH issues with no `parent:`
  frontmatter field;
- score with **Jaccard similarity on title + summary text**;
- accept `--auto` and `--min-score`;
- write `parent: EPIC-NNN` into the child and update the EPIC's `## Children`
  section.

`create-epics-from-unparented`'s own description states it is "*the inverse of
`/ll:link-epics`*". The difference is solely the target: assign orphans to
**existing** EPICs, versus synthesize **new** EPICs from the orphan pool.

**The duplication has already produced drift.** `--min-score` defaults diverge:
`link-epics` uses 0.7 with `--auto` and 0.0 without; `create-epics-from-unparented`
uses a flat 0.3. Nothing forces those to be reconciled or even compared, because
they live in separate prose bodies.

## Expected Behavior

One skill covering both directions, with the orphan-discovery query, the Jaccard
scoring description, and the write-back procedure stated **once**.

## Motivation

This is a maintenance-cost argument, and deliberately not a menu-footprint one.

The ENH-2877 audit established that `ll-verify-skill-budget` is at **516 / 2000
tokens — 74% headroom**, so there is no live token pressure motivating any
consolidation. ENH-2877's own guidance is that a candidate whose only argument is
"fewer entries in the menu" should be recommended *against*. This candidate does
not rely on that argument: the shared logic is duplicated prose that has
**already** drifted on a user-visible default, which is a realized defect rather
than a hypothetical one.

## Proposed Solution

One skill (retaining the name `link-epics`) with a `mode` argument:

- `mode: assign` — score orphans against existing EPICs and link accepted
  proposals. Current `link-epics` behavior.
- `mode: synthesize` — cluster orphans and propose new EPIC files. Current
  `create-epics-from-unparented` behavior.

Shared: orphan discovery, Jaccard scoring, `--auto`, `--min-score`, write-back.
Mode-specific: `--min-cluster` (synthesize only), and mode-conditional
`--min-score` defaults preserving today's tuned values rather than picking one.

**Precedent for the shape**: `skills/manage-issue/SKILL.md` dispatches on an
`action` argument across five behaviors; `skills/configure/SKILL.md` dispatches
internally on an `area` argument across ~20 areas. Both are the model here.

### What would be lost

Two clean single-purpose files become one file carrying a mode conditional.
Mode-conditional defaults are a genuine readability cost — the reason the two
defaults drifted is that they were never side by side, but putting them side by
side means a reader must now track which mode they are in.

## Scope Boundaries

**In scope**

- Merging `link-epics` and `create-epics-from-unparented` into one skill under
  the retained name `link-epics`, with a `mode` argument.
- Reconciling the `--min-score` default drift between the two, per mode.
- Updating the skill catalog in `.claude/CLAUDE.md`, `commands/help.md`, and docs.

**Out of scope**

- **Any other merge candidate.** ENH-2877's Tier 2 and Tier 3 findings
  (`debug-loop-run`/`audit-loop-run`, `confidence-check`/`go-no-go`,
  `product-analyzer`/`scan-product`, `review-loop`/`simplify-loop`, the
  workflow-analysis pipeline, and the `refine-issue`/`wire-issue`/`reconcile-issue`
  cluster) were each examined and **recommended against**. Do not opportunistically
  fold any of them in.
- **Any router or change to name-based dispatch.** ENH-2877 explicitly rejects
  that shape; individually addressable skills are load-bearing for FSM states,
  MR-12 validation, and `ll-action`/`ll-queue`.
- Changing the Jaccard scoring algorithm itself, or the EPIC file format.
- A deprecation shim for `/ll:create-epics-from-unparented` — the name is
  removed outright (0 automation references).

**Backwards compatibility**: `/ll:create-epics-from-unparented` stops resolving.
No FSM loop, `_VERIFIER_SKILLS`/`_REVIEWER_SKILLS` entry, or `ll-*` bridge
references it, so the break is confined to direct user invocation and must be
noted in the changelog.

## Integration Map

### Dispatch-site check (ENH-2877 AC #2)

**Clean — no name-based dispatch site is affected.**

| Site | `link-epics` | `create-epics-from-unparented` |
|------|--------------|-------------------------------|
| Loop corpus `/ll:<name>` refs (`scripts/little_loops/loops/`) | 0 | 0 |
| `_VERIFIER_SKILLS` (`cli/action.py:30`) | no | no |
| `_REVIEWER_SKILLS` (`cli/action.py:49`) | no | no |
| `ll-*` thin bridge in `skills/` | none | none |
| `skills/configure/areas.md` allowlist | n/a — that preset covers `ll-` CLI entry points, not skill names | n/a |

Remaining references are docs and tests only. Retaining the name `link-epics`
keeps even those stable for one of the two.

### Files

- `skills/link-epics/SKILL.md` (259 lines) — merge target.
- `skills/create-epics-from-unparented/SKILL.md` (341 lines) — removed.
- `scripts/little_loops/text_utils.py` — `extract_words()` (131),
  `calculate_word_overlap()` (148); the Jaccard primitive both describe.
- Docs listing the command catalog: `.claude/CLAUDE.md` § Commands & Skills,
  `commands/help.md`, `docs/` references to either name.
- `scripts/tests/` — any test asserting the skill inventory or either name.

## Implementation Steps

1. Diff the two `SKILL.md` bodies to isolate genuinely shared prose from
   mode-specific prose.
2. Reconcile the `--min-score` default drift explicitly — decide per mode and
   document why, rather than collapsing to a single value.
3. Write the merged `skills/link-epics/SKILL.md` with `mode` dispatch.
4. **Check the 500-line cap**: 259 + 341 = 600 lines concatenated. The merged
   file must come in under 500 (`ll-verify-skills`), or extract to a companion
   file per the ENH-494 pattern. Do not assume the merge fits.
5. Delete `skills/create-epics-from-unparented/`.
6. Update the catalog in `.claude/CLAUDE.md`, `commands/help.md`, and docs.
7. Run `python -m pytest scripts/tests/`, `ll-verify-skills`,
   `ll-verify-skill-budget`.

## Impact

- **Users**: `/ll:create-epics-from-unparented` stops resolving. This is a
  breaking change to a user-facing name with no deprecation shim proposed —
  acceptable given 0 automation references, but it should be called out in the
  changelog.
- **Maintenance**: one orphan-discovery + scoring description instead of two.
- **Risk**: Low. No automation path touches either name.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Commands & Skills catalog listing both names; the "Prefer Skills over Agents" and skill-authoring conventions |
| `docs/ARCHITECTURE.md` | Skill/command surface and the FEAT-1896 bridge pattern that scopes what counts as a real skill |

## Session Log
- `/ll:capture-issue` - 2026-07-28T02:07:33Z - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`

## Status

open
