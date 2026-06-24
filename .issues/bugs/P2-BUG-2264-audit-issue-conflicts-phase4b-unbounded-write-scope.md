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

## Motivation

`/ll:audit-issue-conflicts` is trusted to produce clean, targeted edits during conflict resolution. When Phase 4b silently writes to `done`/`cancelled`/`deferred` issues it corrupts the historical record — closed work gains spurious `blocked_by` entries that never belonged there. This degrades triage clarity and undermines user confidence in the skill's output. The exposure grows: once FEAT-1389 makes epics a first-class loaded type, the detection agent will surface more child-issue IDs, widening the unguarded write surface. The fix is low-effort and is a prerequisite to safely landing FEAT-1389.

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

In Phase 4b, gate every file-modifying action behind a pre-check following the same **prose instruction** pattern as the existing idempotency guards (lines 327, 340, 390). Since the skill is LLM-executed with no persistent shell session between phases, the guard must be written as prose that the agent evaluates, not a bash function:

> Before editing `[TARGET]`, verify two conditions using the ISSUE_FILES list from Phase 1 context:
> (1) **Membership**: the target's file path appears in ISSUE_FILES. If not, skip this action and log `[skipped: TARGET not in active set (not loaded in Phase 1)]`.
> (2) **TOCTOU re-check**: run `awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' TARGET` and confirm the result is `open`, `in_progress`, or `blocked`. If terminal, skip and log `[skipped: TARGET status is CURRENT_STATUS — not active]`.
> Increment `SKIPPED_INACTIVE_COUNT` for each skip; report in Phase 6.

The `is_active_target()` bash helper below captures the full two-check logic for reference; adapt it to prose in `SKILL.md` following the pattern at lines 327, 340, 390:

```bash
# Reference logic (not a bash function in SKILL.md — express as prose):
#  (1) membership: must be in Phase-1 ISSUE_FILES list
#  (2) status: must still be active (TOCTOU re-check)
printf '%s\n' "${ISSUE_FILES[@]}" | grep -qxF "$target" || skip "not in active set"
st=$(awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' "$target")
case "${st:-open}" in
    open|in_progress|blocked) : ;;  # proceed
    *) skip "status is $st" ;;
esac
```

Apply in each Phase 4b branch (`merge/deprecate`, `add_dependency`, `split/update_scope`) before the first Edit/append. Track skips with a `SKIPPED_INACTIVE_COUNT` counter (mirroring `TERMINAL_COUNT` from Phase 1); include in Phase 6 SUMMARY.

## Implementation Steps

1. Add the membership + status pre-check to Phase 4b in `skills/audit-issue-conflicts/SKILL.md` (before the `merge/deprecate`, `add_dependency`, and `split/update_scope` action blocks).
2. Add a "Skipped (target not active)" tally and a Phase 6 report line.
3. Add a regression test in `scripts/tests/test_audit_issue_conflicts_skill.py` in class `TestAuditIssueConflictsSkillExists`, following `test_phase4b_idempotency_guard_present` (line 84):
   ```python
   def test_phase4b_write_side_guard_present(self) -> None:
       """Phase 4b must guard writes to non-active targets (BUG-2264)."""
       content = SKILL_FILE.read_text()
       phase4b_start = content.index("## Phase 4b")
       phase5_start = content.index("## Phase 5")
       phase4b_text = content[phase4b_start:phase5_start]
       assert "ISSUE_FILES" in phase4b_text, "Phase 4b must reference ISSUE_FILES membership"
       assert "open|in_progress|blocked" in phase4b_text, "Phase 4b must re-check status"
       assert "not in active set" in phase4b_text, "Phase 4b must log skip reason"
   ```
4. Coordinate ordering with FEAT-1389 — if epics become first-class loaded, this guard is a prerequisite, not a follow-up.
5. Add a Phase 6 structural test in the same class following `test_phase1_filters_by_status` as the pattern (BUG-2264 Phase 6 side):
   ```python
   def test_phase6_skipped_inactive_count_reported(self) -> None:
       """Phase 6 must report SKIPPED_INACTIVE_COUNT for write-side guard skips (BUG-2264)."""
       content = SKILL_FILE.read_text()
       phase6_start = content.index("## Phase 6")
       phase6_text = content[phase6_start:]
       assert "SKIPPED_INACTIVE_COUNT" in phase6_text, "Phase 6 must tally skipped inactive writes"
       assert "Skipped (target not active)" in phase6_text, "Phase 6 must label the skip category"
   ```

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
- `skills/audit-issue-conflicts/SKILL.md:62-83` — Phase 1 read-side status filter (the symmetric read guard this issue mirrors on the write side); line 62 is the actual start (`declare -a ISSUE_FILES`)
- `skills/capture-issue/SKILL.md:174` — awk status-extraction one-liner reused here
- `skills/audit-issue-conflicts/SKILL.md:327` — existing prose idempotency pre-check in add_dependency branch ("before appending, read the kept issue file and check whether `## Scope Addition` already contains..."); the write-side guard should follow the same **prose** pattern
- `skills/audit-issue-conflicts/SKILL.md:340` — existing prose guard for `## Resolution` (merge/deprecate branch)
- `skills/audit-issue-conflicts/SKILL.md:390` — existing prose guard for `## Scope Boundary` (split/update_scope branch)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Phase 4b is LLM-executed prose, not a persistent bash script.** Each phase runs in separate tool invocations with no shared shell session. `ISSUE_FILES` from Phase 1 is available in the LLM's context but not in a live bash environment when Phase 4b runs. The `is_active_target()` bash function in the Proposed Solution illustrates the logic correctly, but the actual implementation in `SKILL.md` must follow the existing idempotency pre-check pattern (prose instructions, not a bash function definition).
- Phase 4b `add_dependency` branch (lines 374–386) has no idempotency guard at all (unlike merge/deprecate and split/update_scope). The write-side guard also fills this gap.
- Phase 6 SUMMARY tally (lines 422–455) has slots for: Issues scanned, Conflicts found, Recommendations applied, Skipped (idempotent), Skipped (user declined), Could not evaluate — but no "Skipped (target not active)" slot. A `SKIPPED_INACTIVE_COUNT` counter (analogous to `TERMINAL_COUNT` from Phase 1) is needed.
- `cards-project-audit-issue-conflicts-investigation-2026-06-24.md` — actual observed incident: 4 of 5 recommendations applied cleanly; only Conflict #1 (EPIC-324 vs. EPIC-328 → child FEAT-329, status `done`) triggered the spurious write.

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural tests for skill phases/flags; add a write-guard assertion

### Related Bugs (Same Defect Class)
- `.issues/bugs/P2-BUG-1799-audit-issue-conflicts-scans-terminal-issues.md` — read-side status filter (done); this is the write-side sibling
- `.issues/bugs/P2-BUG-1800-audit-issue-conflicts-git-add-sweeps-untracked.md` — Phase 5 staging scope (done); same "bound the write surface" theme

### Related Features
- `.issues/features/P2-FEAT-1389-add-epic-as-first-class-issue-type.md` — first-classing epics widens this exposure; guard should land first

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — invokes `/ll:audit-issue-conflicts --auto` in the `audit_conflicts` FSM state (line 95); transparent consumer, no code change required — the write-side guard is additive and does not alter observable output when no inactive targets are involved [Agent 1 finding]

### Documentation
- N/A — internal skill logic change; no user-facing docs require updates

### Configuration
- N/A

## Impact

- **Priority**: P2 — silently mutates terminal issues; corrupts the historical record and can introduce spurious `blocked_by` on closed work. No functional harm to running code, but incorrect process and confusing for users.
- **Effort**: Small — one shared guard helper + report line + structural test.
- **Risk**: Low — strictly narrows what Phase 4b may write; no change to detection semantics.
- **Breaking Change**: No.

## Session Log
- `/ll:wire-issue` - 2026-06-24T20:41:38 - `cab00745-6580-45c4-87b5-4d107e68bd28.jsonl`
- `/ll:refine-issue` - 2026-06-24T20:25:26 - `3eaafc1f-779c-4470-b381-fdd0d770bfa4.jsonl`
- `/ll:format-issue` - 2026-06-24T18:01:24 - `583a1678-ddec-4a1a-9641-b1b934fb8a25.jsonl`
- `/ll:capture-issue` - 2026-06-24T17:55:55Z - `583a1678-ddec-4a1a-9641-b1b934fb8a25.jsonl`

## Status

**Open** | Created: 2026-06-24 | Priority: P2
