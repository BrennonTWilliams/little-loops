---
captured_at: '2026-05-04T20:29:17Z'
completed_at: '2026-05-04T21:54:39Z'
discovered_date: '2026-05-04'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1363: Add --issues filter argument to tradeoff-review-issues

## Summary

Add an optional `--issues` argument to `/ll:tradeoff-review-issues` that accepts a comma-separated list of issue IDs (e.g., `BUG-123,FEAT-456`), allowing users to scope the review to a specific subset of active issues instead of always scanning the entire backlog.

## Current Behavior

`/ll:tradeoff-review-issues` always scans all active issues across all category directories. There is no way to target a specific issue or subset of issues — users must run the full backlog review and act selectively during the per-issue approval prompts.

## Expected Behavior

Users can invoke `/ll:tradeoff-review-issues BUG-123` or `/ll:tradeoff-review-issues BUG-123,FEAT-456,ENH-789` to review only the specified issues, skipping Phase 1's full scan and evaluating only the requested IDs.

## Motivation

When a user already knows which issues they want to evaluate (e.g., after asking "is this worth implementing?"), running the full backlog review is noisy and slow. A targeted filter lets users spot-check one or two issues without wading through approval prompts for unrelated items. This is especially useful before deciding whether to implement a specific issue.

## Proposed Solution

Add argument parsing at the start of the command workflow:

```
IF args contain comma-separated issue IDs:
  Resolve each ID to its file path using `ll-issues path <ID>`
  Skip Phase 1 full scan; use resolved paths as the issue set
ELSE:
  Phase 1 proceeds as normal (scan all active issues)
```

The `ll-issues path` subcommand already resolves IDs to file paths, so no new CLI work is needed. The command just needs to short-circuit Phase 1 when IDs are provided.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Frontmatter change** (follow `commands/create-sprint.md:12–16`):
```yaml
argument-hint: "[issue-ids]"
arguments:
  - name: issues
    description: Comma-separated issue IDs to filter (e.g., "BUG-123,FEAT-456"). If omitted, scans all active issues.
    required: false
```

**ID resolution loop** (follow `skills/issue-size-review/SKILL.md:93–97`):
```bash
ISSUES_ARG="${issues:-}"
declare -a ISSUE_FILES

if [ -n "$ISSUES_ARG" ]; then
    IFS=',' read -ra IDS <<< "$ISSUES_ARG"
    for id in "${IDS[@]}"; do
        id="${id// /}"  # strip accidental spaces
        FILE=$(ll-issues path "${id}" 2>/dev/null)
        if [ -n "$FILE" ]; then
            ISSUE_FILES+=("$FILE")
        else
            echo "Warning: Issue $id not found (skipping)"
        fi
    done
    if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
        echo "Error: None of the specified issue IDs resolved to active issues"
        exit 1
    fi
    # Build issue records from resolved paths (same structure as Phase 1 Glob output)
else
    # Phase 1 Glob scan proceeds unchanged
fi
```

## Integration Map

### Files to Modify
- `commands/tradeoff-review-issues.md` - Add argument parsing and conditional Phase 1 skip; also add `Bash(ll-issues:*)` to `allowed-tools` frontmatter (currently absent — required for the new `ll-issues path` calls in the conditional branch) [Agent wiring finding]

### Dependent Files (Callers/Importers)
- N/A (command file, not a Python module)

### Similar Patterns
- `commands/manage-issue.md` - accepts issue ID as argument; check how it resolves IDs
- `commands/ready-issue.md` - accepts issue ID argument for reference

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1363_doc_wiring.py` — new test file needed; follow the pattern in `scripts/tests/test_refine_issue_command.py` (`TestOptionCountDetectionInCommand`) and `scripts/tests/test_enh1299_doc_wiring.py`; assert: `argument-hint` present in frontmatter, `arguments:` block present, `issues` argument named with comma-separated description, `Bash(ll-issues:*)` in `allowed-tools`, conditional Phase 1 branch text present, filtered example in `## Examples` section [Agent 3 finding]
- `scripts/tests/test_refine_status.py` — uses `/ll:tradeoff-review-issues` as a session-log fixture string (lines 752–754, 833, 1638); NOT broken by this change (command name is unchanged) [Agent 3 finding — no update needed]

### Documentation
- `commands/tradeoff-review-issues.md` examples section - add example with IDs
- `commands/help.md` — lines 73-75, the detail block for `/ll:tradeoff-review-issues`; should show `[issue-ids]` argument syntax [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `### /ll:tradeoff-review-issues` section (around line 219) lacks `**Arguments:**` subsection; add one for the new `issues` argument [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `commands/create-sprint.md:12–16` — closest existing pattern: comma-separated `issues` named argument in frontmatter `arguments:` block; use this as the direct template (not manage-issue, which handles only a single ID)
- `skills/issue-size-review/SKILL.md:93–97` and `skills/confidence-check/SKILL.md:147–153` — canonical ID-resolution loop: `for id in "${IDS[@]}"; do FILE=$(ll-issues path "${id}" 2>/dev/null); ...done` — both use this pattern for converting a list of IDs to file paths with skip-on-miss behavior
- `commands/tradeoff-review-issues.md` currently has **no `arguments:` frontmatter block** — one must be added alongside `argument-hint` (the file only declares `description` and `allowed-tools`)
- Phase 1 uses **Glob tool calls** (not `find` or `ll-issues list`) against three subdirectories (`bugs/`, `features/`, `enhancements/`) — the conditional branch replaces these Glob calls when IDs are provided
- Phase 1 output is an in-memory list of records with fields `file`, `issue_id`, `type`, `priority`, `title`, `summary` — the filter path must build records in this same structure after resolving paths via `ll-issues path`

### Codebase Research Findings (Pass 2)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact frontmatter insertion point**: `commands/tradeoff-review-issues.md` line 12 (closing `---`) — insert `argument-hint: "[issue-ids]"` before line 12; insert `arguments:` block after the existing `allowed-tools:` list (follow `commands/create-sprint.md:7–17` for ordering: `argument-hint` before `allowed-tools`, `arguments:` after)
- **Exact Phase 1 Glob calls**: lines 27–30 in `commands/tradeoff-review-issues.md` — three consecutive Glob calls for `bugs/`, `features/`, `enhancements/`; the conditional branch wraps or replaces these when `${issues:-}` is non-empty
- **Phase 1 / Phase 2 boundary**: Phase 1 ends at lines 40–43 (empty-backlog guard); Phase 2 (`### Phase 2: Wave-Based Evaluation`) begins at line 44
- **Examples section insertion**: lines 357–363 in `commands/tradeoff-review-issues.md` — single bare invocation example; add filtered examples after the existing block
- **`ll-issues path` accepts all three ID formats**: bare numeric (`1363`), `TYPE-NNN` (`ENH-1363`), or `P-TYPE-NNN` (`P4-ENH-1363`); the `2>/dev/null` suppression is universal across all call sites
- **Sister issue ENH-1362** (`commands/align-issues.md`) implements the same filter pattern — consider reading its implementation first if it lands before this one

## Implementation Steps

1. Add argument parsing logic at the top of the workflow (parse comma-separated IDs from args)
2. Add conditional Phase 1: if IDs provided, resolve each to a file path via `ll-issues path`; otherwise scan all active directories
3. Update the examples section in the command file with ID-filter usage
4. Add error handling: warn and skip any IDs that don't resolve to an active issue file

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add `arguments:` block to `commands/tradeoff-review-issues.md` frontmatter** — currently absent; follow `commands/create-sprint.md:12–16` for the named `issues` argument declaration
2. **Add conditional branch before Phase 1 Glob calls** in `commands/tradeoff-review-issues.md` — when `${issues:-}` is non-empty, resolve IDs using the loop from `skills/issue-size-review/SKILL.md:93–97` instead of running Glob; produce the same record structure (`file`, `issue_id`, `type`, `priority`, `title`, `summary`) that Phase 2 expects
3. **Update examples section** of `commands/tradeoff-review-issues.md` — add single-ID and comma-separated usage examples (see API/Interface above)
4. **Skip-on-miss behavior** — unresolvable IDs print `Warning: Issue <ID> not found (skipping)` and are skipped; abort if zero IDs resolve (see `skills/confidence-check/SKILL.md:147–153` for this exact pattern)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add `Bash(ll-issues:*)` to `allowed-tools` in `commands/tradeoff-review-issues.md` frontmatter — currently absent; the `ll-issues path` call in the new conditional branch requires this permission
6. Update `commands/help.md` — add `[issue-ids]` to the argument description in the detail block for `/ll:tradeoff-review-issues` (lines 73-75)
7. Add `**Arguments:**` subsection to `docs/reference/COMMANDS.md` under `### /ll:tradeoff-review-issues` (around line 219) documenting the new `issues` argument
8. Write `scripts/tests/test_enh1363_doc_wiring.py` — doc-wiring test asserting frontmatter completeness and conditional Phase 1 presence; follow `test_refine_issue_command.py` class structure

## Scope Boundaries

- Only active issues are filterable — completed/deferred issues are not valid targets (they are excluded from tradeoff review)
- Does not support glob or prefix patterns (e.g., `FEAT-*`) — only explicit comma-separated IDs
- Does not change the evaluation logic, scoring, or approval flow

## Success Metrics

- Users can invoke `/ll:tradeoff-review-issues BUG-123` and receive tradeoff analysis for only that issue
- Users can pass comma-separated IDs (e.g., `BUG-123,FEAT-456`) and receive analysis for only those issues
- Unresolvable IDs produce a warning and are skipped; valid IDs in the same invocation still evaluate normally
- No-arg invocation behavior is unchanged — full backlog scan proceeds as before

## API/Interface

```bash
# Single issue
/ll:tradeoff-review-issues BUG-123

# Multiple issues (comma-separated, no spaces)
/ll:tradeoff-review-issues BUG-123,FEAT-456,ENH-789
```

## Impact

- **Priority**: P4 - Quality-of-life improvement; the full scan is always an option
- **Effort**: Small - argument parsing + conditional branch in Phase 1; `ll-issues path` already exists
- **Risk**: Low - additive change; existing no-arg behavior is unchanged
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/CLI.md` — documents `ll-issues path` subcommand (including `--json` flag) at line 527; confirm exact invocation syntax before implementation
- `docs/reference/COMMANDS.md` — command reference; update with the new `[issue-ids]` argument when the change lands

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-05-04T21:54:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/788e9e94-b8a6-4865-af7c-4f5eba1ae671.jsonl`
- `/ll:ready-issue` - 2026-05-04T21:50:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2eb2f30a-fec4-4f7c-8ad6-cdf3a44a50a6.jsonl`
- `/ll:confidence-check` - 2026-05-04T21:47:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e517095-5e16-4a2f-9ba9-022896042d88.jsonl`
- `/ll:wire-issue` - 2026-05-04T21:45:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fcbd1f9-eaf5-479a-96d9-cb2fa0858814.jsonl`
- `/ll:refine-issue` - 2026-05-04T21:40:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b533065f-bb41-4ee0-88bd-bf4355d9be26.jsonl`
- `/ll:refine-issue` - 2026-05-04T21:11:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2cacbb2-3baa-47a6-8310-3720c7e6ca3e.jsonl`
- `/ll:format-issue` - 2026-05-04T21:08:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2cacbb2-3baa-47a6-8310-3720c7e6ca3e.jsonl`
- `/ll:format-issue` - 2026-05-04T21:07:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a99b592-a169-47b6-94ae-74c34304e026.jsonl`

- `/ll:capture-issue` - 2026-05-04T20:29:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db5648f7-6175-41b6-9af0-89d734f66fea.jsonl`

---

---

## Resolution

- **Status**: Completed
- **Completed**: 2026-05-04
- **Approach**: Added `argument-hint`, `arguments:` block, and `Bash(ll-issues:*)` to frontmatter; inserted conditional Phase 1 branch resolving comma-separated IDs via `ll-issues path`; updated help.md, COMMANDS.md, and examples; added 15-test doc-wiring suite.

**Closed** | Created: 2026-05-04 | Completed: 2026-05-04 | Priority: P4
