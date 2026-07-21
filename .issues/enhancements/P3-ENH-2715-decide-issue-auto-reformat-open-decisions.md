---
id: ENH-2715
title: decide-issue --auto should reformat found-but-unstructured open decisions
status: open
captured_at: "2026-07-21T03:08:03Z"
discovered_date: 2026-07-21
discovered_by: capture-issue
---

# ENH-2715: decide-issue --auto should reformat found-but-unstructured open decisions

## Summary

When `/ll:decide-issue ISSUE_ID --auto` cannot find a properly formatted
decision (no `### Option A/B` blocks, no bold `**Option X**` labels, no
scoreable structure) it currently only reacts by invoking
`/ll:refine-issue ${ISSUE_ID} --auto` once (Phase 2.5, ENH-2443) to have
refine-issue *research and deposit new* options, then re-scans. If the issue
already contains open decisions expressed in unstructured prose — e.g. an
`## Open Questions` section with unresolved items, or ad-hoc "we could do X
or Y" language in the body — that content is only picked up by Phase 3b's
inline provisional-language scan for *locking in* a clear winner (Pattern
D). There is no path where decide-issue rewrites an existing informal
decision into the canonical `### Option A` / `### Option B` structure so it
can go through normal Phase 4–7 scoring.

## Current Behavior

`skills/decide-issue/SKILL.md` Phase 2.5 / Phase 3 / Phase 3b:
- `OPTIONS == 0` + `AUTO_MODE` → calls `/ll:refine-issue --auto` once to
  deposit new options via codebase research, then re-scans.
- If the re-scan still finds 0 structured options, falls through to Phase 3b,
  which only scans for a declarative recommendation marker to lock in a
  single winner (or leaves `decision_needed: true` for human review if no
  marker exists).
- Neither path reformats an existing informal decision (e.g. bullet points
  under `## Open Questions`, or inline "Option A vs Option B" prose that
  doesn't match Patterns 1–4) into the structured template so it can be
  scored normally.

## Expected Behavior

After the existing `refine-issue --auto` deposit attempt is exhausted
(`DEPOSIT_ATTEMPTED = true`) and a re-scan still yields `OPTIONS == 0`,
decide-issue should check the issue body for open decisions expressed in
unstructured form (unresolved `## Open Questions` items, informal
alternative-listing prose elsewhere in the body) and, if found, rewrite them
in-place into the canonical `### Option A` / `### Option B` structure under
`## Proposed Solution` before falling through to Phase 3b. This lets a
decision that already exists in the issue — just not in scoreable form — get
picked up by normal Phase 4–7 scoring instead of dead-ending at
`NO_ACTIONABLE_DECISIONS` or staying stuck on `decision_needed: true`.

## Motivation

Today, an issue author who jots down alternatives informally (a quick "could
do X or Y" note, or an `## Open Questions` list without the lettered-option
structure) gets no benefit from `--auto` decision-making even though the
substance of a decision is already written down — automation only helps if
the prose happens to match Patterns 1–4 or contains an explicit
recommendation marker. Reformatting existing content is lower-risk than
depositing brand-new options (no new research/investigation needed) and
should be tried before conceding to `NO_ACTIONABLE_DECISIONS` or leaving
`decision_needed: true` on issues that could be resolved with the
information already present.

## Proposed Solution

TBD - requires investigation into where to insert this step relative to
Phase 3b, and how to distinguish "informal but real alternatives worth
reformatting" from prose that merely mentions options in passing (to avoid
false positives worse than the existing Pattern 4 bullet-list handling
guard, which explicitly avoids over-eager auto-scoring of author-authored
lists).

## Impact

- **Priority**: P3 — quality-of-life improvement to an existing auto-mode
  gap; not blocking, no data loss or regression risk.
- **Effort**: Medium — touches `skills/decide-issue/SKILL.md` Phase 2.5/3b
  logic and likely needs new test coverage in the decide-issue test suite.
- **Risk**: Low-medium — must not over-trigger and rewrite issue prose that
  wasn't actually meant as a decision list (same class of risk the Phase 3
  "Auto-mode bullet-list handling" guard was added to avoid).

## Session Log
- `/ll:capture-issue` - 2026-07-21T03:08:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/58687b43-4209-4796-b24a-1505ad6b098f.jsonl`

---

## Status

- [ ] Not started
