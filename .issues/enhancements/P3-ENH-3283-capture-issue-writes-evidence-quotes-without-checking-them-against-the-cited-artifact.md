---
id: ENH-3283
type: ENH
title: capture-issue writes evidence quotes without checking them against the cited
  artifact
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:30:17Z'
labels:
- capture-issue
- skills
- evidence
- hallucination
relates_to:
- BUG-3282
- BUG-3278
---

# ENH-3283: capture-issue writes evidence quotes without checking them against the cited artifact

## Summary

`/ll:capture-issue` writes `## Current Behavior` and `## Steps to Reproduce` containing quoted
lines attributed to specific files, with no step that confirms those lines exist there. It is the
write-time half of the gap BUG-3282 closes at verify time.

## Current Behavior

The skill's Phase 1 extracts a title, type, priority, and description; Phase 2 checks for
duplicates; Phase 4 writes the file via `ll-issues create`. No phase validates the *content* of
the body it writes. When capture reconstructs evidence from conversation context rather than from
a file read, a plausible-but-nonexistent quote is written verbatim into the issue and inherits the
authority of the surrounding accurate citations.

Observed on BUG-3278: `git show baa553d9` (2026-08-21 10:56) is the capture output. Its
`## Current Behavior` attributes to ENH-3277 a `- **(a) Make the documented override real.**`
bullet and a `**DECISION — pick one before step 4 touches this file:**` directive. Neither exists
in any committed revision of ENH-3277 — its second decision point is prose. The capture also
derived a `bullet`-tier attribution, a span-exclusion fix proposal, and an `--all-tiers` CLI
alternative from that invented shape. All of it was present 31 minutes before the
`refine-to-ready-issue` loop started; no loop pass introduced it, and none removed it.

## Expected Behavior

[What should happen instead]

## Motivation

Capture is where an issue's evidence enters the pipeline, and it is the cheapest place to check
it — one `grep -F` per quote against a file that is usually already open. Everything downstream
compounds instead of correcting: on BUG-3278, `refine_issue` and `wire_issue` built ~150 lines of
Integration Map, docs inventory, and test wiring on the fabricated mechanism, and two
`verify_issue` passes certified it `VALID` at confidence 98.

BUG-3282 adds the verify-time gate, which is the backstop. This issue adds the write-time gate,
which is the one that prevents the wasted downstream work rather than detecting it afterward.

## Proposed Solution

Add a self-check before the Phase 4 `ll-issues create` write:

1. Identify quoted spans in the drafted body that are attributed to a named file or issue ID.
2. For each, read or `grep -F` the cited artifact and confirm the span appears in it.
3. On a miss, either drop the quote and describe the evidence in prose, or read the artifact and
   quote it correctly — never write the unverified span.
4. When the evidence genuinely came from an uncommitted or transient state (a working-tree edit, a
   loop run directory), say so explicitly in the issue rather than attributing it to the file.

If BUG-3282 lands the deterministic checker as a CLI, this phase should call it rather than
reimplementing span extraction in skill prose.

## Integration Map

### Files to Modify

- `skills/capture-issue/SKILL.md` — new pre-write validation step in Phase 4
- The evidence checker from BUG-3282, if it ships as a CLI — call site, no new logic

### Tests

- `scripts/tests/` skill-prose assertions following the existing structural-test convention for
  LLM-executed skills (see `test_decide_issue_skill.py`): assert the pre-write check phrase and
  its "drop or correct, never write unverified" instruction are present

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 — BUG-3282 catches the same class at verify time; this one saves the wasted
  refine/wire work in between
- **Effort**: Small if BUG-3282's checker exists; Small-Medium standalone
- **Risk**: Low — the check can only suppress or correct a quote
- **Breaking Change**: No

## Related Key Documentation

- BUG-3282 — verify-time enforcement of the same invariant; shares the checker
- BUG-3278 — the capture whose fabricated evidence propagated through a full refine loop
- `skills/capture-issue/SKILL.md` Phase 4 — where the check lands

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
