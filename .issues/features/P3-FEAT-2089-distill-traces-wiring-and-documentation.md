---
id: FEAT-2089
title: "distill-traces: wiring and documentation updates"
type: FEAT
priority: P3
status: open
parent: FEAT-2078
captured_at: '2026-06-10T00:00:00Z'
discovered_date: '2026-06-10'
discovered_by: issue-size-review
size: Small
---

# FEAT-2089: distill-traces: wiring and documentation updates

## Summary

Wire the `distill-traces` skill into the harness registration points and update all documentation to reflect the new skill. Depends on FEAT-2088 being merged (needed for `ll-verify-docs` count verification).

## Parent Issue

Decomposed from FEAT-2078: Add distill-traces skill to extract reusable loop fragments from history

## Proposed Solution

### Step 8 — Update `.claude/CLAUDE.md`

Add `distill-traces`^ to the **Automation & Loops** bullet in `## Commands & Skills`.

### Step 9 — Update `docs/reference/COMMANDS.md`

Add `### /ll:distill-traces` subsection in `## Automation Loops` and a row in the `## Quick Reference` table.

### Step 10 — Update skill count in docs

Update the skill count annotation 64 → 65 in:
- `docs/ARCHITECTURE.md` — add `distill-traces/` to skills directory tree; update count annotation
- `CONTRIBUTING.md` — update `# 64 skill definitions` count annotation
- `README.md` — update `**64 skills**` to `**65 skills**`

After editing, run `ll-verify-docs` to verify all counts match:
```bash
python -m ll_verify_docs 2>/dev/null || ll-verify-docs
```

### Step 11 — Update `commands/loop-suggester.md`

Add `distill` to keyword signals in the `Step FC-2: Group by Workflow Theme` table's `loops-automation` row.

### Step 12 — Update `docs/guides/LOOPS_GUIDE.md`

At `## Reusable State Fragments` — mention `distill-traces` as the extraction tool alongside manual fragment authoring. Add `ll-loop fragments lib/<loop-name>/state-templates.yaml` as an example invocation documenting the new subdirectory path convention.

## Files to Modify

- `.claude/CLAUDE.md` — add `distill-traces`^ to Automation & Loops bullet
- `docs/reference/COMMANDS.md` — add subsection and quick-reference row
- `docs/ARCHITECTURE.md` — add skill to tree; count 64 → 65
- `CONTRIBUTING.md` — count annotation 64 → 65
- `README.md` — `**64 skills**` → `**65 skills**`
- `commands/loop-suggester.md` — add `distill` keyword
- `docs/guides/LOOPS_GUIDE.md` — mention distill-traces at `## Reusable State Fragments`

## Acceptance Criteria

- [ ] `.claude/CLAUDE.md` lists `distill-traces`^ in Automation & Loops
- [ ] `docs/reference/COMMANDS.md` has `/ll:distill-traces` subsection
- [ ] Skill count updated to 65 in ARCHITECTURE.md, CONTRIBUTING.md, README.md
- [ ] `ll-verify-docs` exits 0
- [ ] `commands/loop-suggester.md` includes `distill` in `loops-automation` keyword table
- [ ] `docs/guides/LOOPS_GUIDE.md` references distill-traces at `## Reusable State Fragments`

## Notes

- Run `ll-verify-docs` after all count edits to confirm correctness
- Soft dependency: FEAT-2088 must merge first so the skill file exists for `ll-verify-docs` to count

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low — documentation-only changes
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-10 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-06-10T00:00:00Z - `05bf4f79-aed4-42a8-af0b-8633b9f97798.jsonl`
