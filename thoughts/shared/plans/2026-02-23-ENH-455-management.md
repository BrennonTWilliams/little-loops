# ENH-455: Expand parallel, commands, and issues coverage in init wizard

**Date**: 2026-02-23
**Issue**: P3-ENH-455
**Action**: implement
**Status**: IN_PROGRESS

## Research Summary

### Current State
- `interactive.md` has 7 mandatory rounds + up to 5 conditional rounds (10 max)
- Round 2 is at the 4-question limit (Format Cmd, Issues, Scan Dirs, Excludes)
- Round 5 has 8 conditional questions with overflow handling (5a: first 4, 5b: remaining)
- Round 8 has 3 questions (Test Dir, Build Cmd, Run Cmd) - room for 1 more
- Schema defaults: `parallel.max_workers=2`, `parallel.timeout_per_issue=3600`, `issues.completed_dir="completed"`, `commands.pre_implement=null`, `commands.post_implement=null`

### Design Decision: completed_dir placement
Issue proposes Round 2, but Round 2 is at the 4-question limit. Adding `completed_dir` to Round 5 as a conditional question (when issues enabled) follows the existing pattern and avoids removing an existing Round 2 question. This is the same pattern used for `issues_path`.

## Implementation Plan

### Phase A: Update Round 5 conditions (interactive.md)

**1. Add 3 new conditions to the ordered list (lines 360-369)**

New ordered list of 11 conditions:
1. issues_path (Round 2 → "Yes, custom directory")
2. **completed_dir** (Round 2 → issues enabled, not "Disable") ← NEW
3. worktree_files (Round 3a → Parallel processing)
4. **parallel_workers** (Round 3a → Parallel processing) ← NEW
5. **parallel_timeout** (Round 3a → Parallel processing) ← NEW
6. threshold (Round 3a → Context monitoring)
7. priority_labels (Round 3a → GitHub sync)
8. sync_completed (Round 3a → GitHub sync)
9. gate_threshold (Round 3a → Confidence gate)
10. sprints_workers (Round 3b → Sprint management)
11. auto_timeout (Round 3b → Sequential automation)

**2. Update ACTIVE counting (lines 197-211)**

- Add: `if Round 2 → issues enabled (not "Disable"): ACTIVE += 1`
- Change: `if Round 3a → "Parallel processing": ACTIVE += 3` (was 1)

**3. Extend overflow handling for >8 conditions**

- 5a: first 4 active
- 5b: positions 5-8 active
- 5c: positions 9-11 active (new)
- Update TOTAL calculation: `if ACTIVE > 8: TOTAL += 1`

### Phase B: Add new questions to Round 5

**4. Add completed_dir question (Round 5a, position 2)**

```yaml
- header: "Completed Dir"
  question: "What directory name should completed issues be moved to?"
  options:
    - label: "completed (Recommended)"
      description: "Standard directory inside issues base dir"
    - label: "done"
      description: "Alternative naming"
    - label: "archive"
      description: "Alternative naming"
  multiSelect: false
```

**5. Add parallel_workers question (Round 5a, position 4)**

```yaml
- header: "Workers"
  question: "How many parallel workers should ll-parallel use?"
  options:
    - label: "2 (Recommended)"
      description: "Conservative — safe default for most systems"
    - label: "3"
      description: "Moderate parallelism"
    - label: "4"
      description: "Higher parallelism — needs more CPU/memory"
  multiSelect: false
```

**6. Add parallel_timeout question (Round 5a/5b, position 5)**

```yaml
- header: "Issue Timeout"
  question: "What timeout should ll-parallel use per issue?"
  options:
    - label: "3600 (Recommended)"
      description: "1 hour per issue — default"
    - label: "7200"
      description: "2 hours — complex issues"
    - label: "14400"
      description: "4 hours — very complex issues"
  multiSelect: false
```

### Phase C: Add config output for new questions (interactive.md)

**7. Add config mapping for new questions**

- completed_dir → `{ "issues": { "completed_dir": "done" } }` (only if non-default, not "completed")
- parallel_workers → `{ "parallel": { "max_workers": 3 } }` (only if non-default, not 2)
- parallel_timeout → `{ "parallel": { "timeout_per_issue": 7200 } }` (only if non-default, not 3600)

### Phase D: Add pre/post implement to Round 8 (interactive.md)

**8. Add impl hooks question as 4th question in Round 8**

```yaml
- header: "Impl Hooks"
  question: "Run commands before or after issue implementation? (manage-issue hooks)"
  options:
    - label: "Skip (Recommended)"
      description: "No hooks — standard implementation flow"
    - label: "Post: run tests"
      description: "Run test suite after each implementation"
    - label: "Pre: lint, Post: tests"
      description: "Lint before starting, run tests after"
  multiSelect: false
```

Config mapping uses test_cmd/lint_cmd from Round 1.

### Phase E: Update SKILL.md config summary

**9. Add new fields to summary display**

- Under `[ISSUES]`: add `issues.completed_dir` (only if non-default)
- Under `[PARALLEL]`: add `parallel.max_workers` and `parallel.timeout_per_issue` (only if non-default)
- Add `[COMMANDS]` section: show `commands.pre_implement` and `commands.post_implement` (only if configured)

### Phase F: Update summary table (interactive.md)

**10. Update the Interactive Mode Summary table at the bottom**

## Success Criteria

- [ ] Round 5 condition list updated to 11 entries
- [ ] ACTIVE counting updated for new conditions
- [ ] Overflow handling extended for >8 active conditions (5c)
- [ ] completed_dir question added to Round 5
- [ ] parallel_workers and parallel_timeout questions added to Round 5
- [ ] Config output section updated for all 3 new Round 5 questions
- [ ] pre_implement/post_implement question added to Round 8
- [ ] Config output for Round 8 hooks question added
- [ ] SKILL.md summary display updated with new fields
- [ ] Summary table at bottom of interactive.md updated
