---
id: ENH-2236
type: ENH
status: open
priority: P3
discovered_date: 2026-06-19
discovered_by: audit-docs
testable: false
labels:
- docs
- loops
- meta-loop
- harness
- validation
relates_to:
- ENH-1665
---

# ENH-2236: Add missing MR-2 row to HARNESS_OPTIMIZATION_GUIDE design rules table

## Summary

Add MR-2 to the design rules table in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` and add a corresponding enforcement paragraph to `.claude/CLAUDE.md` § Loop Authoring, so developers who encounter MR-2 warnings from `ll-loop validate` have documentation explaining the rule and suppression flag.

## Current Behavior

`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` lists design rules MR-1, MR-3, MR-4, MR-5, MR-6 in its table (line 93) but silently omits MR-2. MR-2 is a real, enforced WARNING emitted by `ll-loop validate`:

```
# scripts/little_loops/fsm/validation.py:1100
MR-2 (WARNING): meta-loop should reference a captured baseline in an evaluator.
```

It checks that the loop has a measure→propose→apply→re-measure spine: at least one captured value from a baseline state must be referenced by a later evaluator. Without the table row, a developer hitting an MR-2 warning from `ll-loop validate` has no guide text to explain what the rule requires or how to suppress it.

MR-2 is also absent from the normative source (`.claude/CLAUDE.md` § Loop Authoring). The guide is the only place the full rule table lives.

## Expected Behavior

The table in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` includes a row for MR-2:

| Rule | What it requires | Why | Severity | Suppress with |
|------|------------------|-----|----------|---------------|
| **MR-2** | A meta-loop's captured baseline value must be referenced by a later evaluator (measure→propose→apply→re-measure spine) | Without a baseline comparison, the gate cannot tell whether an edit helped or hurt | WARNING | `meta_self_eval_ok: true` |

The CLAUDE.md § Loop Authoring section should also gain a corresponding `ll-loop validate enforces rule MR-2 as WARNING severity` paragraph, consistent with the MR-3 through MR-6 paragraphs already present.

## Implementation Steps

1. Confirm MR-2 is enforced in `fsm/validation.py` and determine its exact location (git blame for ENH-1665 context)
2. Insert MR-2 row between MR-1 and MR-3 in the HARNESS_OPTIMIZATION_GUIDE design rules table
3. Add `ll-loop validate enforces rule MR-2 as WARNING severity` paragraph to `.claude/CLAUDE.md` § Loop Authoring, after the MR-1 paragraph
4. Verify no other doc references to the rule table need updating

## Scope Boundaries

- Out of scope: Modifying the MR-2 validation logic in `fsm/validation.py`
- Out of scope: Adding MR-2 enforcement examples to existing loops (`harness-optimize.yaml` already serves as the reference implementation)
- Out of scope: Changing the behavior of the suppression flag (`meta_self_eval_ok: true`)

## Impact

- **Priority**: P3 — Low-priority documentation gap; no user-facing behavior changes, but causes developer confusion when MR-2 warnings appear without guide explanation
- **Effort**: Small — Two targeted file edits: one table row insertion and one paragraph addition
- **Risk**: Low — Documentation-only change; no code modified
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-19 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-20T03:50:37 - `0f099cd8-b3d8-4868-a874-14d98dd66159.jsonl`
