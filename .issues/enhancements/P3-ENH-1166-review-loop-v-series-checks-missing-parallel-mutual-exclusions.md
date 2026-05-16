---
discovered_date: "2026-04-18"
discovered_by: capture-issue
depends_on: [FEAT-1074]
status: deferred
---

# ENH-1166: `review-loop` V-Series Check Table Missing Parallel Mutual-Exclusion Entries

> **FOLDED into FEAT-1074 — not a separate work item.** 2026-04-20: the V-series table update is an acceptance criterion of FEAT-1074 (see FEAT-1074 "Blockers & Folded Criteria"). **Action on ship**: when FEAT-1074 merges, move this file to `.issues/completed/` and add a Session Log entry pointing at the FEAT-1074 PR. Do NOT re-open, do NOT re-implement.
>
> **Release blocker for parallel v1** (flagged 2026-04-20): without the V-series check-table entries, `/ll:review-loop` silently passes loops that violate the `parallel:` mutual-exclusion rules (parallel+action, parallel+loop, parallel+next). Authoring-time guidance must land together with runtime validation (FEAT-1074). This issue remains P3 (it's a docs/table update, not a feature) and stays in `deferred/` (work happens inside FEAT-1074) — but it MUST NOT fall off the release checklist when FEAT-1074 ships.

## Summary

`skills/review-loop/reference.md:21-38` V-series check table has no entries for the three `parallel:` mutual-exclusion validation rules added by FEAT-1074. This update was explicitly deferred to "FEAT-1078 scope" in FEAT-1074, but FEAT-1078 was completed by decomposition without capturing this work in any of its child issues (FEAT-1080, FEAT-1081, FEAT-1083, FEAT-1086).

## Current Behavior

The V-series check table in `skills/review-loop/reference.md` documents validation rules that `/ll:review-loop` enforces. FEAT-1074 adds three new mutual-exclusion validation errors:
- `parallel` + `action` → ERROR
- `parallel` + `loop` → ERROR
- `parallel` + `next` → ERROR

None of these appear in the V-series table. The `/ll:review-loop` skill references this table to guide its validation checks — missing entries mean parallel loops with malformed state configurations are not flagged by the skill.

## Expected Behavior

The V-series check table includes three new rows for the parallel mutual-exclusion rules, following the existing format for `loop`/`action` mutual exclusion entries. Each row includes:
- V-series ID (next available after existing entries)
- Rule description
- Error severity (ERROR)
- Example of invalid YAML

## Motivation

`/ll:review-loop` is the primary human-readable validation tool for loop authors. Without V-series entries, a loop author who accidentally writes `parallel:` alongside `action:` or `next:` will not be flagged by the review skill — even though the FSM engine will reject the loop at runtime. Adding these entries closes the gap between runtime validation (FEAT-1074) and authoring-time guidance.

## Proposed Solution

Read `skills/review-loop/reference.md` to find:
1. The current last V-series ID (e.g., V-12)
2. The table format (columns, example style)

Then add three rows after the last existing V-series entry:

```markdown
| V-N   | Mutual exclusion: `parallel` + `action`  | A state may not have both `parallel:` and `action:` | ERROR |
| V-N+1 | Mutual exclusion: `parallel` + `loop`    | A state may not have both `parallel:` and `loop:`   | ERROR |
| V-N+2 | Mutual exclusion: `parallel` + `next`    | A state may not have both `parallel:` and `next:`   | ERROR |
```

Also add `parallel:` to the "State type quick reference" table if one exists, alongside `action:`, `loop:`, and `shell:` entries.

## Implementation Steps

1. Read `skills/review-loop/reference.md` to find the last V-series ID and table format
2. Add 3 new V-series rows for the parallel mutual-exclusion rules (next available IDs)
3. If a "State type quick reference" or similar table exists, add `parallel:` row
4. Verify `/ll:review-loop` skill prompt references the V-series table correctly (no skill prompt changes needed if it reads from the reference doc)

## Integration Map

### Files to Modify
- `skills/review-loop/reference.md` — add V-series rows at the current table tail

### Context
- FEAT-1074 (`validation.py`) implements the runtime rules; this issue makes the skill aware of them
- FEAT-1074 wiring notes: "V-series IDs not yet listed — address in FEAT-1078 scope"
- FEAT-1078 is now completed by decomposition; none of its child issues (1080, 1081, 1083, 1086) cover this file

## Acceptance Criteria

- `skills/review-loop/reference.md` V-series table includes entries for all three parallel mutual-exclusion rules
- V-series IDs are sequential with no gaps
- Running `/ll:review-loop` on a loop with `parallel:` + `action:` in the same state flags the violation

## Impact

- **Priority**: P3 — Low urgency; only affects `/ll:review-loop` skill guidance, not runtime enforcement
- **Effort**: Very Small — 3 table rows in one file; exact format from existing entries
- **Risk**: Very Low — documentation/skill-guidance only; no code changes
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `review-loop`, `skills`, `docs`

---

## Session Log
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ff9cd96-1544-4ffa-b28c-15aab5e9f3e8.jsonl`

---

**Open** | Created: 2026-04-18 | Priority: P3
