---
id: ENH-1090
type: ENH
priority: P3
discovered_date: 2026-04-12
discovered_by: issue-size-review
parent_issue: ENH-1089
---

# ENH-1090: issue-size-review skill writes `size` frontmatter after assessment

## Summary

After `/ll:issue-size-review` computes a size label for an issue, it should persist that result by writing a `size` field to the issue's YAML frontmatter. Currently the assessment is ephemeral — it disappears when the conversation ends.

## Parent Issue

Decomposed from ENH-1089: issue-size-review writes size frontmatter, show in refine-status

## Current Behavior

`/ll:issue-size-review` outputs a size recommendation (`Small`, `Medium`, `Large`, `Very Large`) to the conversation but does not write anything back to the issue file. The result is lost when the session ends.

## Expected Behavior

After assessing an issue, the skill writes `size: <label>` to the issue's YAML frontmatter:

```yaml
size: Medium   # one of: Small, Medium, Large, Very Large
```

The write-back is skipped when `CHECK_MODE=true` (check-only mode).

## Proposed Solution

**Step 1 — Add `Edit` to `allowed-tools`:**

`skills/issue-size-review/SKILL.md:6-9` currently lists `Read`, `Glob`, `Bash(ll-issues:*, git:*)`. Add `Edit` to the list so the skill can write back to issue files.

**Step 2 — Insert Phase 4 write-back after size determination:**

After Phase 2 size assessment (currently lines ~111-126), insert a new phase:

```
### Phase 4: Frontmatter Write-back

Skip this phase when `CHECK_MODE=true`.

For each assessed issue, use the Edit tool to add or update `size: <label>` in
the YAML frontmatter block. Follow the exact pattern from
`skills/confidence-check/SKILL.md:398-428`:
- Parse the existing `---` block
- Add/replace the `size` line, preserving all other fields
- Use actual size labels: Small, Medium, Large, Very Large (not XS/S/M/L/XL codes)

After writing, stage the file:
  git add <issue-path>
```

## Integration Map

### Files to Modify

- `skills/issue-size-review/SKILL.md:6-9` — add `Edit` to `allowed-tools`
- `skills/issue-size-review/SKILL.md` — insert Phase 4 write-back block after Phase 2 size determination

### Similar Patterns

- `skills/confidence-check/SKILL.md:398-428` — exact Phase 4 pattern to mirror: use Edit tool to add/update field in frontmatter block, preserve all existing fields; follow with `git add <issue-path>` (SKILL.md:468)

### Tests

- Create `scripts/tests/test_issue_size_review_skill.py` — structural SKILL.md text-assertion tests; follow pattern from `scripts/tests/test_confidence_check_skill.py:11-55`; assert:
  - Write-back phase exists in SKILL.md text
  - Phase does not use `AskUserQuestion`
  - Phase includes a `CHECK_MODE` skip guard
  - Phase writes `size` as the frontmatter key
  - `Edit` appears in the `allowed-tools` section

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md:398-428` to internalize the frontmatter write-back pattern.
2. Edit `skills/issue-size-review/SKILL.md:6-9` — add `Edit` to `allowed-tools`.
3. Edit `skills/issue-size-review/SKILL.md` — insert Phase 4 write-back block after Phase 2 (around line 126): use Edit tool to add/update `size: <label>` in frontmatter, then `git add <path>`. Skip when `CHECK_MODE=true`. Use labels: `Small`, `Medium`, `Large`, `Very Large`.
4. Create `scripts/tests/test_issue_size_review_skill.py` with structural assertions per pattern above.

## Impact

- **Scope**: Very Small — one SKILL.md modified, one new test file
- **Risk**: Very Low — write-back is additive; no existing behavior changes
- **Users**: Anyone running `/ll:issue-size-review` who wants size data to persist

## Labels

`enhancement`, `issue-size-review`, `frontmatter`, `skill`

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24bfa590-00d2-4387-9ba6-799d36510a45.jsonl`

---

## Status

**State**: active
