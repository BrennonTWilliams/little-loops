---
id: BUG-3051
title: 'confidence-check: no hard override for an unresolved blocked_by dependency'
type: BUG
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: "2026-08-05T02:01:17Z"
relates_to:
- ENH-3047
labels:
- skills
- issues
- gates
decision_needed: false
---

# BUG-3051: confidence-check averages away a hard blocked_by dependency instead of forcing STOP

## Summary

`/ll:confidence-check ENH-3047` returned **75/100 → PROCEED WITH CAUTION** for an issue that
cannot be started at all: it is `blocked_by: [FEAT-3048]`, FEAT-3048 is `status: open`, and
ENH-3047's own body says "without it there is nothing to read." Criterion 5 (Dependencies
Satisfied) correctly scored 0/20, but with no hard override to back it, that 0 was simply
averaged against four near-perfect criteria (20+20+20+15+0=75) into a passing tier.

## Current Behavior

`skills/confidence-check/SKILL.md` Phase 3 ("Score and Recommend") defines exactly two hard
overrides that bypass the normal score-to-tier table and force `STOP — ADDRESS GAPS` regardless
of aggregate score:

- **Learning Test Hard Override** (`SKILL.md:302`) — any `missing`/`refuted` learning-test target
- **Program Design Hard Override** (`SKILL.md:304`) — `PD_FAIL` non-empty

Dependencies Satisfied (Criterion 5, `SKILL.md:220`, `rubric.md:245`) has no equivalent. It is
just one of five 0-20 criteria summed into the readiness total (`rubric.md` Phase 2 table), so a
critical unresolved `blocked_by` — scored 0 per the existing "Critical dependencies unresolved,
cannot proceed" row in that same table — is diluted rather than gating.

## Expected Behavior

An unresolved hard dependency should force `STOP — ADDRESS GAPS` (or `STOP — NOT READY`)
regardless of aggregate score, the same way the Learning Test and Program Design gates already
do — not get averaged into a passing tier that reads as "proceed, just be careful."

## Motivation

This readiness score is not just advisory prose — it is what `/ll:go-no-go`, `ll-auto`, and
sprint selection consume (per ENH-3047's own Motivation section, and per this repo's
`commands.confidence_gate` config gate). A misleadingly high score on a hard-blocked issue risks
that issue being auto-selected or greenlit by automation that trusts the aggregate number over
reading the per-criterion breakdown.

## Proposed Solution

Add a **Dependencies Hard Override** to `SKILL.md` Phase 3, following the exact shape of the two
existing overrides:

- Phase 1 (or a new lightweight Phase 1.x pre-fetch) resolves each ID in the issue's `blocked_by:`
  frontmatter list via `ll-issues show <ID> --json` and checks its `status`.
- If any `blocked_by` entry has a status other than `done`/`cancelled` (see `.claude/CLAUDE.md` §
  Issue File Format — `deferred` is explicitly non-terminal for `blocked_by`/`depends_on` edges),
  set a shell variable (e.g. `DEP_FAIL`) non-empty.
- In Phase 3, if `DEP_FAIL` is non-empty, output `STOP — ADDRESS GAPS` regardless of aggregate
  score, listing the unresolved blocker ID(s) and their status under **Gaps to Address** —
  mirroring the Program Design override's structure (`SKILL.md:304`).

This is additive to the existing Criterion 5 0-20 scoring (which stays as-is for the non-blocking
case — "Minor dependencies unresolved but non-blocking" still just scores 15, not a STOP).

### Files to Modify
- `skills/confidence-check/SKILL.md` — new Dependencies pre-fetch step, Phase 3 hard override
- `skills/confidence-check/rubric.md` — document the override alongside the existing two, if the
  reference table there needs updating

## Program Design

### Types

- `DEP_FAIL: str` — shell variable, empty or non-empty, mirroring `PD_FAIL`'s shape
  (`skills/confidence-check/SKILL.md:132-150`)

### Signatures

- Reuse `ll-issues show <ID> --json` (already used by Phase 1.5's learning-test pre-fetch,
  `rubric.md:113`) to resolve each `blocked_by` ID's `status` field.

### Call Path

`skills/confidence-check/SKILL.md` Phase 1.x pre-fetch -> `ll-issues show <blocked_by ID> --json`
-> status extracted via inline `python -c` -> `DEP_FAIL` shell variable -> `SKILL.md` Phase 3
hard-override paragraph (same slot as `PD_FAIL`, `SKILL.md:304`)

## Impact

- **Priority**: P2 — the score feeds automation (`/ll:go-no-go`, `ll-auto`, sprint selection)
  that trusts the aggregate number
- **Effort**: Low — mirrors an existing, well-established override pattern
- **Risk**: Low — additive gate; does not change scoring for issues without unresolved
  `blocked_by` dependencies

## Related Key Documentation

- `.claude/CLAUDE.md` — Issue File Format, `blocked_by`/`depends_on` deferral discriminator
- `docs/reference/COMMANDS.md` — `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-05 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-05T02:02:02 - `78b80840-5577-4179-95d0-0f368e10d2bb.jsonl`
