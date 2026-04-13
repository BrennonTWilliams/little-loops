---
id: ENH-1090
type: ENH
priority: P3
discovered_date: 2026-04-12
discovered_by: issue-size-review
parent_issue: ENH-1089
confidence_score: 100
outcome_confidence: 71
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

## Motivation

Size assessments from `/ll:issue-size-review` are ephemeral — they vanish at session end. Persisting the `size` label in frontmatter lets downstream tools (refine-status, ll-auto priority ordering, sprint planning) consume it without re-running the skill. It also creates a permanent audit trail of when size was determined, enabling trend analysis and workload forecasting.

## Proposed Solution

**Step 1 — Add `Edit` to `allowed-tools`:**

`skills/issue-size-review/SKILL.md:6-9` currently lists `Read`, `Glob`, `Bash(ll-issues:*, git:*)`. Add `Edit` to the list so the skill can write back to issue files.

**Step 2 — Insert Phase 3 write-back after size determination:**

After Phase 2 size assessment (ends at line 124), insert a new phase **before** the current Phase 3 (Decomposition Proposal, line 126). The current Phase 3, 4, 5 shift to Phase 4, 5, 6 respectively, and line 76 ("5-phase workflow") becomes "6-phase workflow".

```
### Phase 3: Frontmatter Write-back

Skip this phase when `CHECK_MODE=true`.

For each assessed issue, use the Edit tool to add or update `size: <label>` in
the YAML frontmatter block. Follow the exact pattern from
`skills/confidence-check/SKILL.md:398-432`:
- Parse the existing `---` block
- Add/replace the `size` line, preserving all other fields
- Derive the label from the score using the Size Thresholds table (SKILL.md:325-333):
  0-2 → Small, 3-4 → Medium, 5-7 → Large, 8+ → Very Large
- Write-back applies to ALL assessed issues, not just decomposition candidates (score ≥5)
- Perform the write-back per-issue inside the assessment loop (not as a batch step)

After writing, stage the file:
  git add <issue-path>
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Phase numbering**: Current Phase 4 (User Approval, `SKILL.md:155`) and Phase 5 (Execution, `SKILL.md:183`) must be renumbered to Phase 5 and Phase 6. The new write-back phase is Phase 3 (not Phase 4 as originally drafted).
- **Workflow count header**: `SKILL.md:76` reads `"The skill follows a 5-phase workflow:"` — must be updated to `"6-phase workflow"` after the insertion.
- **Size thresholds table**: The score-to-label mapping is defined at `SKILL.md:325-333` (`## Size Thresholds`), separate from Phase 2. Phase 3 must apply these thresholds to compute the label from the score.
- **Write-back scope**: Write-back applies to every assessed issue (all sizes), not only candidates. The expected behavior says "after assessing an issue" — this means Small and Medium issues also get `size:` written.
- **Multi-issue loop placement**: When reviewing multiple issues, the write-back happens per-issue immediately after each score is computed, inside the existing assessment loop.

## Integration Map

### Files to Modify

- `skills/issue-size-review/SKILL.md:7-10` — add `Edit` to `allowed-tools` (currently lists `Read`, `Glob`, `Bash(ll-issues:*, git:*)`)
- `skills/issue-size-review/SKILL.md:76` — update "5-phase workflow" to "6-phase workflow"
- `skills/issue-size-review/SKILL.md:155,183` — renumber Phase 4 → Phase 5 (User Approval) and Phase 5 → Phase 6 (Execution) after inserting new Phase 3
- `skills/issue-size-review/SKILL.md:126` — insert new Phase 3: Frontmatter Write-back between Phase 2 (ends line 124) and current Phase 3 (starts line 126)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml` — `run_size_review` state dispatches `/ll:issue-size-review ${captured.input.output} --auto`; will additionally write `size:` frontmatter after ENH-1090 (additive, no YAML change needed)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — `size_review` state dispatches `/ll:issue-size-review --auto`; same
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `breakdown_issue` state dispatches `/ll:issue-size-review ${captured.issue_id.output} --auto`; same
- `scripts/little_loops/loops/issue-size-split.yaml` — `size_review` state dispatches the skill via prompt text; same
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml` — references skill by name in prompt text; same

### Similar Patterns

- `skills/confidence-check/SKILL.md` (`append_frontmatter_field` phase) — exact Phase 4 pattern to mirror: use Edit tool to add/update field in frontmatter block, preserve all existing fields; follow with `git add <issue-path>`

### Tests

- Create `scripts/tests/test_issue_size_review_skill.py` — structural SKILL.md text-assertion tests; follow pattern from `scripts/tests/test_confidence_check_skill.py` (`class TestConfidenceCheckSkill`); assert:
  - Write-back phase exists in SKILL.md text
  - Phase does not use `AskUserQuestion`
  - Phase includes a `CHECK_MODE` skip guard
  - Phase writes `size` as the frontmatter key
  - `Edit` appears in the `allowed-tools` section

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:869-895` — frontmatter fields table lists recognized fields (`discovered_date`, `discovered_by`, `confidence_score`, `outcome_confidence`, `testable`) but omits `size`; add `size: Small | Medium | Large | Very Large` row
- `docs/reference/COMMANDS.md:238-251` — `issue-size-review` description section does not mention write-back; add note that normal (non-`--check`) invocations write `size:` to the issue's YAML frontmatter
- `.issues/bugs/P3-BUG-1062-issue-size-review-sprint-does-not-update-sprint-after-decomposition.md:42,45,59,67,73,80` — references "Phase 5: Execution" which becomes "Phase 6: Execution" after phase renumbering; update these references during ENH-1090 implementation

### Configuration

- N/A — no config files affected

## Implementation Steps

1. Read `skills/confidence-check/SKILL.md:398-432` to internalize the frontmatter write-back pattern (replace the full `---` block using Edit tool; `git add` follows at line 471).
2. Edit `skills/issue-size-review/SKILL.md:7-10` — add `Edit` to `allowed-tools`.
3. Edit `skills/issue-size-review/SKILL.md:76` — change "5-phase workflow" to "6-phase workflow".
4. Edit `skills/issue-size-review/SKILL.md:155` — renumber "Phase 4: User Approval" to "Phase 5: User Approval".
5. Edit `skills/issue-size-review/SKILL.md:183` — renumber "Phase 5: Execution" to "Phase 6: Execution".
6. Edit `skills/issue-size-review/SKILL.md:126` — insert new "Phase 3: Frontmatter Write-back" block before current Phase 3 text: per-issue loop writes `size: <label>` using Edit tool, applies `SKILL.md:325-333` thresholds to score, skips when `CHECK_MODE=true`, then `git add <path>`. Applies to all assessed issues.
7. Create `scripts/tests/test_issue_size_review_skill.py` with structural assertions per pattern from `scripts/tests/test_confidence_check_skill.py:11-55`: section-scoped assertions using `content.index("### Phase 3: Frontmatter Write-back")` to bound the section, then assert `"Edit"` in `allowed-tools` text, `"CHECK_MODE"` in phase text, `"size"` in phase text, `"AskUserQuestion"` not in phase text.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/reference/ISSUE_TEMPLATE.md:869-895` — add `size: Small | Medium | Large | Very Large` row to the frontmatter fields table alongside the other recognized frontmatter fields
9. Update `docs/reference/COMMANDS.md:238-251` — add a note to the `issue-size-review` description that normal (non-`--check`) invocations write `size:` to the issue's YAML frontmatter
10. Update `.issues/bugs/P3-BUG-1062-issue-size-review-sprint-does-not-update-sprint-after-decomposition.md` — replace "Phase 5: Execution" with "Phase 6: Execution" at lines 42, 45, 59, 67, 73, and 80 (stale phase reference caused by renumbering)

## Impact

- **Priority**: P3 — Useful persistence feature; not blocking current workflows
- **Effort**: Small — One SKILL.md modified, one new test file; mirrors the existing confidence-check frontmatter write-back pattern exactly
- **Risk**: Very Low — Write-back is additive; no existing behavior changes; CHECK_MODE guard prevents side effects during evaluation
- **Breaking Change**: No

## Scope Boundaries

- Does not change the size assessment algorithm or label vocabulary (`Small`, `Medium`, `Large`, `Very Large`)
- Does not implement CLI display of `size` in `ll-issues show` or `refine-status` — tracked separately in ENH-1091
- Does not retroactively populate `size` on issues assessed before this change
- Does not add size-based filtering or sorting to issue list commands
- Does not affect the `--check` mode evaluation logic (only skips write-back)

## Labels

`enhancement`, `issue-size-review`, `frontmatter`, `skill`

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ecbdeb4-1c63-45f3-9557-6949fade4f15.jsonl`
- `/ll:wire-issue` - 2026-04-13T02:17:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7addff48-eee5-445a-8178-a9b53cef39e6.jsonl`
- `/ll:refine-issue` - 2026-04-13T02:12:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/557fd7f8-4e77-4e6b-b846-071483492cc3.jsonl`
- `/ll:format-issue` - 2026-04-13T02:07:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0bfb43c5-a9c7-48af-be46-8bbb8a4d02b0.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24bfa590-00d2-4387-9ba6-799d36510a45.jsonl`

---

## Status

**State**: active
