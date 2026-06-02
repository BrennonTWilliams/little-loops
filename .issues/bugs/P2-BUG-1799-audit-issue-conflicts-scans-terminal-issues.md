---
id: BUG-1799
type: BUG
priority: P2
status: done
captured_at: '2026-05-29T20:55:00Z'
completed_at: '2026-05-30T04:18:53Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
labels:
- bug
- skills
- audit-issue-conflicts
parent: EPIC-1745
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1799: audit-issue-conflicts scans terminal (done/deferred) issues alongside active ones

## Summary

`skills/audit-issue-conflicts/SKILL.md` Phase 1 collects every `.md` file under `.issues/{bugs,features,enhancements}/` and treats them all as active. In practice, type directories now contain both active and terminal issues distinguished by `status:` frontmatter, so the audit wastes work on already-closed issues and can spawn hundreds of unnecessary parallel agents on large backlogs.

## Current Behavior

Phase 1 uses a plain `find` glob over type directories (`bugs/`, `features/`, `enhancements/`) that collects every `.md` file regardless of `status:` frontmatter. Terminal issues (`status: done`, `status: deferred`, `status: cancelled`) are included in the active set and passed through to conflict-detection stages, wasting work on already-closed issues.

## Steps to Reproduce

1. Have ≥100 issues in `.issues/{bugs,features,enhancements}/` where most are `status: done` (typical post-`ll-migrate` state)
2. Run `/ll:audit-issue-conflicts`
3. Phase 1 reports "Found N active issues" where N includes all done/deferred/cancelled files

Observed in this repo on 2026-05-29: 1,692 files in type dirs, only 54 with `status: open|in_progress|blocked`. The skill would have batched all 1,692 into ~340 parallel agents instead of ~11.

## Expected Behavior

Phase 1 should filter to issues whose frontmatter `status:` is one of `open`, `in_progress`, `blocked` (or absent — default open). Terminal statuses (`done`, `deferred`, `cancelled`) should be excluded.

## Root Cause

`skills/audit-issue-conflicts/SKILL.md` lines 59–74 (Phase 1 bash block) globs `find "$dir" -maxdepth 1 -name "*.md"` without inspecting frontmatter. The skill predates the ENH-1390/ENH-1551 model where completed issues live alongside active ones in the same type directory rather than under a `completed/` subdir.

## Proposed Solution

Replace the Phase 1 collection block with a status-aware filter:

> **Selected:** Bash awk filter (matching `capture-issue/SKILL.md:167-178` pattern) — `ll-issues list --status` only accepts a single value, so the awk approach is the only viable option for collecting `open+in_progress+blocked` in one pass.

```bash
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    [ -d "$dir" ] || continue
    for f in "$dir"*.md; do
        [ -f "$f" ] || continue
        status=$(awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' "$f")
        case "${status:-open}" in
            open|in_progress|blocked) ISSUE_FILES+=("$f") ;;
        esac
    done
done
```

> **Rejected alternative:** `ll-issues list --status open,in_progress,blocked --format path` — the `--status` flag accepts only a single value (confirmed by codebase research), making it unsuitable for collecting multiple active statuses in one pass.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-29.

**Selected**: Bash awk filter (matching `capture-issue/SKILL.md:167-178` pattern)

**Reasoning**: The CLI alternative was ruled out by codebase research — `ll-issues list --status` accepts only a single value, so it cannot express `open,in_progress,blocked` in one invocation. The awk-based filter is already proven in `capture-issue/SKILL.md:167-178` and is a drop-in pattern copy. No new infrastructure needed.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Bash awk filter | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| `ll-issues list` CLI | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **Bash awk filter**: Already implemented in `skills/capture-issue/SKILL.md:167-178` — same pattern, zero new abstractions. Test pattern exists at `test_issue_parser.py:1056`. Matches how `find_issues()` in `issue_parser.py:877` already filters by status.
- **`ll-issues list` CLI**: Single-value `--status` limitation confirmed at `scripts/little_loops/cli/issues/list_cmd.py:33` — would require multiple invocations or a CLI change, adding complexity without benefit over the one-liner awk approach.

## Implementation Steps

1. Update Phase 1 collection block in `skills/audit-issue-conflicts/SKILL.md:59-75` — replace the bare `find` loop with the awk-based status filter from `skills/capture-issue/SKILL.md:167-178` (shown in Proposed Solution)
2. Update the count message to clarify: "Found N active issues (excluded M terminal issues)"
3. Add a regression test in `scripts/tests/test_audit_issue_conflicts_skill.py` — create fixture issues with mixed statuses, assert only active ones reach Phase 2. Model after `test_find_issues_skips_status_done` at `scripts/tests/test_issue_parser.py:1056`
4. Fix the same defect in `commands/tradeoff-review-issues.md:57-71` — Phase 1 Glob should include status-filter instructions (separate commit or follow-up issue)
5. `skills/format-issue/SKILL.md:122` and `skills/confidence-check/SKILL.md:118` also use bare `find` — assess whether those skills intentionally operate on all files before fixing

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Root cause confirmed**: `skills/audit-issue-conflicts/SKILL.md:59-75` uses `find "$dir" -maxdepth 1 -name "*.md"` with zero frontmatter inspection. The `capture-issue` skill at `skills/capture-issue/SKILL.md:167-178` already solved this with an awk one-liner — the fix is a drop-in pattern copy.
- **Cross-check results**: `commands/tradeoff-review-issues.md` has the same defect (bare Glob, no status filter). `commands/align-issues.md` and `commands/verify-issues.md` are already correct (use `ll-issues list` which defaults to `--status open`). `skills/format-issue/SKILL.md:122` and `skills/confidence-check/SKILL.md:118` also use bare `find` — needs assessment.
- **CLI limitation**: `ll-issues list --status` accepts only a single value (not comma-separated), so the bash awk approach is preferred over CLI invocation for collecting `open+in_progress+blocked` in one pass.
- **Python-side is correct**: `find_issues()` at `scripts/little_loops/issue_parser.py:877` and `_load_issues_with_status()` at `scripts/little_loops/cli/issues/search.py:113` both filter by status — the defect is isolated to shell/Glob-based collection in skill markdown files.

## Acceptance Criteria

- Running `/ll:audit-issue-conflicts` on a backlog with mixed statuses processes only active issues
- Phase 1 logs both the active count and the excluded terminal count
- Pytest fixture covers the status-filter path

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md:59-75` — Phase 1 `find` loop needs status-aware filtering

### Dependent Files (Callers/Importers)
- None — this is a skill file invoked by the agent directly; no Python callers

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/sprint-build-and-validate.yaml:98` — invokes `/ll:audit-issue-conflicts --auto` in the `audit_conflicts` FSM state. Consumer only; automatically benefits from the fix, no changes needed.

### Similar Patterns
- `skills/capture-issue/SKILL.md:167-178` — canonical awk-based status filter (Phase 2 "Search Active Issues"); same bash-level collection loop with `case "${status:-open}" in open|in_progress|blocked)` filter
- `scripts/little_loops/issue_parser.py:877` — `find_issues()` defaults to skipping `done|cancelled|deferred` when `status_filter is None`
- `scripts/little_loops/cli/issues/search.py:113` — `_load_issues_with_status()` uses `IssueParser.parse_file()` for per-file status reading
- `scripts/little_loops/cli/issues/list_cmd.py:33` — `cmd_list()` translates `--status` flag into `include_open`/`include_done`/`include_deferred` booleans

### Sibling Skills with Same Defect

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `commands/tradeoff-review-issues.md:57-71` — Phase 1 uses Glob `*.md` without status filtering; comment "no completed/deferred dirs to exclude" predates ENH-1390 frontmatter-based terminal status
- `skills/format-issue/SKILL.md:122` — same bare `find *.md` glob (may not need fix if format-issue intentionally operates on all files)
- `skills/confidence-check/SKILL.md:118` — same bare `find *.md` glob (may not need fix if confidence-check intentionally operates on all files)

### Sibling Skills Already Correct
- `commands/align-issues.md:183` — uses `ll-issues list` (default `--status open`); status-filtered by CLI
- `commands/verify-issues.md:51` — uses `ll-issues list` (default `--status open`); status-filtered by CLI

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural tests for skill existence/flags; add a mixed-status fixture case
- `scripts/tests/test_issue_parser.py:1056` — `test_find_issues_skips_status_done` — model for status-filter assertions
- `scripts/tests/test_issue_parser.py:1106` — `test_find_issues_skips_status_deferred` — model for status-filter assertions
- `scripts/tests/test_issue_parser.py:1131` — `test_find_issues_status_filter_includes_deferred` — model for explicit inclusion
- `scripts/tests/test_issues_cli.py:3109` — `test_list_status_short` — CLI-level status filter test pattern

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_enh1363_doc_wiring.py` — structural tests for `commands/tradeoff-review-issues.md` (class `TestTradeoffReviewConditionalPhase1`). If the same-defect fix from Implementation Step 4 is applied to that command, add a status-filter structural assertion here.

### Related Bugs (Same Defect Class)
- `.issues/bugs/P2-BUG-1649-create-sprint-counts-done-cancelled-issues-as-active.md` — `create-sprint` counting terminal issues as active; same root cause (pre-ENH-1390 directory model)

## Impact

- **Priority**: P2 — degrades skill utility on any real backlog; pure-design bug
- **Effort**: Small — single-block rewrite + test
- **Risk**: Low — narrows scope, doesn't change conflict-detection semantics
- **Breaking Change**: No — strictly fewer files audited

## Session Log
- `/ll:ready-issue` - 2026-05-30T04:17:23 - `7949c439-c2bc-449a-800f-259e92e11e55.jsonl`
- `/ll:decide-issue` - 2026-05-30T04:13:27 - `20913251-e684-466b-a3be-c8bc94f7c706.jsonl`
- `/ll:confidence-check` - 2026-05-30T04:15:00 - `5e2daf50-26d6-4657-859b-a4e70fd08209.jsonl`
- `/ll:refine-issue` - 2026-05-30T04:04:26 - `6224dad8-97d7-4fe1-b6d9-3e126ce2aa37.jsonl`
- `/ll:format-issue` - 2026-05-29T21:11:18 - `d42814df-045f-41ae-b065-5f4d670ef04d.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:confidence-check` - 2026-05-30T04:22:00 - `75253662-ac29-4581-81b8-599f2ab844d4.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P2
