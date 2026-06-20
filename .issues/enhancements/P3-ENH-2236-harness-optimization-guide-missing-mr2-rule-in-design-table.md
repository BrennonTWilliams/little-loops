---
id: ENH-2236
type: ENH
status: open
priority: P3
discovered_date: 2026-06-19
discovered_by: audit-docs
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

## Problem

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

## Implementation Notes

- Suppress flag: `meta_self_eval_ok: true` (same as MR-1; both are suppressed together in `fsm/validation.py:1102`)
- Reference implementation: `scripts/little_loops/loops/harness-optimize.yaml` captures the baseline score and the gate compares post-edit score to it
- The table row should slot between MR-1 and MR-3 (the guide intentionally uses non-sequential numbering only if MR-2 was intentionally omitted — confirm with git blame on ENH-1665)
- Also add the rule to CLAUDE.md immediately after the existing MR-1 paragraph at line 123
