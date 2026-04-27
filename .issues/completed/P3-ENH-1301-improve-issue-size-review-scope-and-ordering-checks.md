---
id: ENH-1301
type: ENH
priority: P3
status: completed
discovered_date: 2026-04-27
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
size: Small
---

# ENH-1301: Improve `issue-size-review` with scope completeness and ordering checks

## Summary

`/ll:issue-size-review` produced a flawed decomposition of ENH-1298: it silently
dropped a full implementation step (the ready-issue lint check), proposed strictly
sequential children that offer no parallelism benefit, and left the parent issue
in an open/modified state without resolving it. Three targeted improvements to
`skills/issue-size-review/SKILL.md` prevent these failure modes.

## Problem

Reviewing the decomposition of ENH-1298 into ENH-1299 and ENH-1300 exposed
three structural gaps in the skill:

**1. Dropped scope.** ENH-1298's step 3 — extending `ready-issue` with an
anchor lint check — was not assigned to either child issue. The skill had no
mechanism to verify that proposed children collectively covered 100% of the
parent's scope, so an entire deliverable silently vanished.

**2. Ordering constraints ignored.** ENH-1299 must complete before ENH-1300 can
run (sweeper must follow source-file fixes or re-contamination occurs). The two
children also share the anchor resolver infrastructure. With strict sequential
ordering and shared scope, the decomposition adds tracking overhead with no
parallelism benefit — the original monolith would have been preferable. The
skill offered no analysis of this.

**3. Parent left in limbo.** ENH-1298 remained open and modified (MM in git
status) after the children were created. The skill's Phase 6 specifies moving
the parent to `completed/`, but this did not happen, producing an inconsistent
state where both parent and children were simultaneously active.

## Solution

Three additions to `skills/issue-size-review/SKILL.md`:

**Phase 4, step 3 — Scope completeness check**: Before drafting child content,
the skill now enumerates every numbered step and `###` subsection in the parent's
Proposed Solution / Implementation Steps and maps each to exactly one proposed
child. Any unmapped step surfaces as a `⚠ SCOPE GAP`. Execution is blocked until
every gap is either assigned to a child or explicitly marked as intentionally
deferred with a stated reason.

**Phase 4, step 4 — Ordering dependency analysis**: The skill now classifies the
execution pattern of proposed children as Parallel, Partially ordered, or
Strictly sequential, by detecting ordering language in the parent ("run after
step N", "must complete before", numbered steps that build on each other, shared
infrastructure one child creates and another consumes). If strictly sequential
AND children share infrastructure, the skill surfaces a recommendation to keep
the issue together rather than decompose.

**Phase 5 — Scope gap guard**: Added an explicit guard that blocks decomposition
execution (in both auto and interactive modes) when unresolved scope gaps exist.
In auto mode this emits `[ID] blocked: decomposition would lose scope — steps
not covered: [list]. Review manually.`

**Output format**: The PROPOSALS section now shows `Execution pattern` and
`Scope coverage` per proposal, and each child listing includes a `Covers:` line
naming which parent steps it accounts for, making coverage auditable at a glance.

**Best Practices**: Added two entries to the "Avoid" list: losing scope when
decomposing, and decomposing strictly sequential children with shared
infrastructure.

## Files Changed

- `skills/issue-size-review/SKILL.md` — Phase 4 (two new steps), Phase 5 (scope
  gap guard), output format template (Execution pattern, Scope coverage, Covers
  fields), Best Practices "Avoid" section (two new entries)

## Session Log

- manual review session - 2026-04-27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6004b6bd-98cd-4890-a69a-b3c5136d203f.jsonl`
