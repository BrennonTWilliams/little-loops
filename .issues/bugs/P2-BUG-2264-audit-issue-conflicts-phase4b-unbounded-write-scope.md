---
id: BUG-2264
type: BUG
priority: P2
status: open
captured_at: '2026-06-24T17:55:55Z'
discovered_date: '2026-06-24'
discovered_by: capture-issue
labels:
- bug
- skills
- audit-issue-conflicts
relates_to: [BUG-1799, FEAT-1389]
---

# BUG-2264: audit-issue-conflicts Phase 4b applies edits with unbounded write scope (modifies done issues)

## Summary

`skills/audit-issue-conflicts/SKILL.md` enforces the active-status invariant only on the **read** side (Phase 1 load), not the **write** side (Phase 4b apply). Phase 4b resolves recommendations by issue **ID** and edits whatever file that ID maps to, with no check that the target was in the Phase-1 `ISSUE_FILES` set and no re-check of the target's `status:`. As a result, a recommendation can modify a `done`/`cancelled`/`deferred` issue. Observed in a downstream project: an `add_dependency` recommendation between two open epics appended `blocked_by: FEAT-326` to a child issue (FEAT-329) whose `status:` was already `done`.

## Current Behavior

- Phase 1 (`SKILL.md:65-83`) correctly filters loaded issues to `open|in_progress|blocked` (the fix from BUG-1799 holds — done issues never enter conflict *detection*).
- Phase 4b (`SKILL.md:314-406`) applies the agent's recommendations by ID. The `add_dependency` branch (`SKILL.md:374-386`) appends `blocked_by:`/`depends_on:` to "the dependent issue file" — whatever ID the detection agent emitted — with no guard. The `merge/deprecate` and `split/update_scope` branches similarly edit files named in `proposed_change` without bounding them to the active set.
- The conflict-detection agent (Phase 2) legitimately reads issue **bodies**, including epic child-issue dependency tables, and is free to emit any issue ID in its `issues` / `proposed_change` output — including IDs of issues that were never loaded in Phase 1 because they are terminal.

## Steps to Reproduce

1. Have an open epic whose body lists child issues in a dependency table, where one or more children are `status: done` (e.g., EPIC-A child FEAT-X depends on EPIC-B child FEAT-Y, both children done).
2. Run `/ll:audit-issue-conflicts` (interactive or `--auto`).
3. Detection surfaces the epic-vs-epic architectural dependency and emits an `add_dependency` recommendation naming the done child.
4. Phase 4b appends `blocked_by: FEAT-Y` to the done child's frontmatter — a terminal issue is silently mutated.

## Expected Behavior

Phase 4b must not modify any issue file outside the Phase-1 active set. Concretely:
1. **Write-side membership guard (primary):** before any edit, verify the target issue path is in `ISSUE_FILES` (the set loaded and filtered in Phase 1). Skip and log otherwise.
2. **Write-time status re-check (TOCTOU guard):** re-read the target's `status:` immediately before editing; skip if not `open|in_progress|blocked` (covers issues completed mid-run).
3. Skipped writes are reported in Phase 6 under a new "Skipped (target not active)" line.

## Root Cause

The active-status invariant is enforced only at load time. There is no corresponding constraint at apply time. BUG-1799 added the Phase 1 read filter but did not add a symmetric write filter, so the conflict-detection agent's ability to name *any* ID (notably IDs harvested from epic child-tables) becomes an unbounded write surface. This is a sibling defect to BUG-1799 in the same root class: status enforced on reads but not writes.

### Epic conduit (why done IDs reach Phase 4b)

Epic bodies carry child-issue dependency tables. The detection agent reads those tables (correct behavior for conflict detection — epic structure matters) and surfaces child-level dependencies, naming child IDs that may be `done`. Note: the current skill Phase 1 globs only `{bugs,features,enhancements}` and does **not** load `epics/` (epics-as-first-class is tracked by FEAT-1389). For an epic to be in scope today, the downstream project must store its `EPIC-*.md` files inside a scanned type dir. **Once FEAT-1389 makes epics a first-class loaded type, this exposure widens** — the write-side guard should land before/with that change.

## Proposed Solution

In Phase 4b, gate every file-modifying action behind a shared pre-check helper:

```bash
# Before modifying any target issue file in Phase 4b:
#  (1) membership: must be in the Phase-1 active set
#  (2) status: must still be active (TOCTOU re-check)
is_active_target() {
    local target="$1"
    # membership check against ISSUE_FILES collected in Phase 1
    printf '%s\n' "${ISSUE_FILES[@]}" | grep -qxF "$target" || return 1
    local st
    st=$(awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' "$target")
    case "${st:-open}" in
        open|in_progress|blocked) return 0 ;;
        *) return 1 ;;
    esac
}
```

Apply it in each Phase 4b branch (`merge/deprecate`, `add_dependency`, `split/update_scope`) before the first `Edit`/append. On failure, log `[skipped: TARGET not in active set]` and continue; tally these for Phase 6.

## Implementation Steps

1. Add the membership + status pre-check to Phase 4b in `skills/audit-issue-conflicts/SKILL.md` (before the `merge/deprecate`, `add_dependency`, and `split/update_scope` action blocks).
2. Add a "Skipped (target not active)" tally and a Phase 6 report line.
3. Add a regression test in `scripts/tests/test_audit_issue_conflicts_skill.py`: assert the skill text contains a Phase-4b write-side guard referencing `ISSUE_FILES`/status (model after the BUG-1799 structural test added there).
4. Coordinate ordering with FEAT-1389 — if epics become first-class loaded, this guard is a prerequisite, not a follow-up.

## Acceptance Criteria

- A recommendation naming a `done`/`cancelled`/`deferred` issue does not modify that issue; the skip is reported.
- A recommendation naming an ID not present in the Phase-1 active set is skipped and reported.
- An issue that was active at Phase 1 but completed before Phase 4b runs is skipped (TOCTOU re-check).
- Phase 6 final report includes a "Skipped (target not active)" count.

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md:314-406` — Phase 4b action blocks need a write-side membership + status guard
- `skills/audit-issue-conflicts/SKILL.md:422-455` — Phase 6 report needs a "Skipped (target not active)" line

### Similar Patterns
- `skills/audit-issue-conflicts/SKILL.md:65-83` — Phase 1 read-side status filter (the symmetric read guard this issue mirrors on the write side)
- `skills/capture-issue/SKILL.md` — awk status-extraction one-liner reused here

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural tests for skill phases/flags; add a write-guard assertion

### Related Bugs (Same Defect Class)
- `.issues/bugs/P2-BUG-1799-audit-issue-conflicts-scans-terminal-issues.md` — read-side status filter (done); this is the write-side sibling
- `.issues/bugs/P2-BUG-1800-audit-issue-conflicts-git-add-sweeps-untracked.md` — Phase 5 staging scope (done); same "bound the write surface" theme

### Related Features
- `.issues/features/P2-FEAT-1389-add-epic-as-first-class-issue-type.md` — first-classing epics widens this exposure; guard should land first

## Impact

- **Priority**: P2 — silently mutates terminal issues; corrupts the historical record and can introduce spurious `blocked_by` on closed work. No functional harm to running code, but incorrect process and confusing for users.
- **Effort**: Small — one shared guard helper + report line + structural test.
- **Risk**: Low — strictly narrows what Phase 4b may write; no change to detection semantics.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-06-24T17:55:55Z - `583a1678-ddec-4a1a-9641-b1b934fb8a25.jsonl`

## Status

**Open** | Created: 2026-06-24 | Priority: P2
