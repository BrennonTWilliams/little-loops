---
id: 2877
title: Audit which ll skills are close enough in scope to merge into fewer skills
type: ENH
priority: P3
status: open
discovered_date: 2026-07-27
labels:
- skills
---

# ENH-2877: Audit which ll skills are close enough in scope to merge into fewer skills

Origin: ll-product #ENH-061

No parent EPIC — deliberately standalone. See the rejection note below for why this is not part of a larger consolidation effort.

## Summary

A deliberately scoped-down survivor of a **rejected** proposal. Read the rejection first — it is the more important half of this issue.

## What was rejected, and why

The rejected shape: consolidate the entire command surface into **one** user-invocable skill with sub-commands behind a router table, keeping maintenance tooling out of the `/` menu entirely. The motivation is real — `/` menu pollution gets worse as users install more plugins.

**That shape does not transfer to little-loops, and must not be adopted.** Individually addressable skills are load-bearing here:

- FSM states invoke `/ll:<name>` directly. A router would break slash-command resolution for every loop state that calls a skill by name.
- The MR-12 validation rule, pruning profiles, and `ll-action` / `ll-queue` dispatch all resolve skills by name.
- The menu's token footprint is already governed by an **enforced** mechanism (`ll-verify-skill-budget`), so the cost the source is solving for is already bounded by different means.
- The lazy-loading benefit does not apply either: each `SKILL.md` already loads only on invocation, so little-loops already gets what the source's per-command reference files buy.

This rejection is recorded here so the same proposal is not re-derived from the same source later.

## What survives

A much smaller question with **no architectural change**: some existing skills may be close enough in scope that one skill with a mode flag would serve both. That is worth knowing independently of any router.

## Proposed work

A **read-only audit**, producing a list of merge candidates with the argument for each:

1. Survey existing skills for pairs or clusters with substantially overlapping scope, inputs, or output shape.
2. For each candidate cluster, state what a merged skill would look like, what the mode flag would be, and what would be lost.
3. Explicitly flag any candidate whose merge would change a name that an FSM state, pruning profile, or `ll-action` / `ll-queue` dispatch path currently resolves — those are disqualified or require a migration plan, not a rename.
4. Recommend, do not execute. Merges are separate follow-up issues.

## Acceptance criteria

- Output is a written list of merge candidates, each with a stated argument and a stated cost.
- Every candidate is checked against name-based dispatch sites, and any that would break one is marked as such.
- No skill is merged, renamed, or removed as part of this issue.
- No router, no change to name-based dispatch.
