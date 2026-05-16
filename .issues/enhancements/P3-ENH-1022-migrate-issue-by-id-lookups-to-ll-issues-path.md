---
id: ENH-1022
type: ENH
priority: P3
status: open
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 70
---

# ENH-1022: Migrate Issue-by-ID Lookups to `ll-issues path`

## Summary

8 skills and commands use an ad-hoc `find -maxdepth 1 | grep -E` loop to locate issue files by ID. Replace all instances with the canonical `ll-issues path <ID>` CLI command, which searches all directories (including `completed/` and `deferred/`) and is the single source of truth.

## Current Behavior

The following files each duplicate this pattern:

```bash
FILE=""
for dir in .issues/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
        if [ -n "$FILE" ]; then break; fi
    fi
done
```

Affected files:
- `skills/manage-issue/SKILL.md` (line 78)
- `skills/format-issue/SKILL.md` (line 111)
- `skills/go-no-go/SKILL.md` (line 83)
- `skills/confidence-check/SKILL.md` (lines 100, 157)
- `skills/issue-size-review/SKILL.md` (line 96)
- `skills/wire-issue/SKILL.md` (lines 89–90)
- `commands/refine-issue.md` (line 87)
- `commands/ready-issue.md` (line 88)

This pattern only searches active category dirs (`bugs/`, `features/`, `enhancements/`) and silently fails when an issue lives in `completed/` or `deferred/`.

## Expected Behavior

All ID→path lookups use the canonical CLI:

```bash
FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)
```

`ll-issues path` accepts bare numeric (`1009`), type+ID (`ENH-1022`), or full (`P3-ENH-1022`) formats, searches all categories including `completed/` and `deferred/`, and exits 1 if not found.

## Motivation

The canonical `ll-issues path` CLI was built specifically for ID→path resolution but only one file (`skills/create-eval-from-issues/SKILL.md`) uses it. The 8 ad-hoc duplicates silently miss issues in `completed/` and `deferred/`, causing confusing "issue not found" failures for closed or deferred work. Consolidating to the CLI eliminates ~8 copies of fragile shell logic and ensures consistent behavior across all skills and commands.

## Proposed Solution

Replace every ad-hoc `for dir` + `find | grep` block with:

```bash
FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)
if [ -z "$FILE" ]; then
    echo "Error: Issue ${ISSUE_ID} not found"
    exit 1
fi
```

The outer dir loop and `$SEARCH_DIR` variable can be removed entirely — `ll-issues path` handles all directory searching internally.

For `confidence-check` line 157 (sprint mode), use the loop variable: `FILE=$(ll-issues path "${id}" 2>/dev/null)`.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — line 78
- `skills/format-issue/SKILL.md` — line 111 (single-ID mode only; batch `ALL_MODE` stays)
- `skills/go-no-go/SKILL.md` — line 83
- `skills/confidence-check/SKILL.md` — lines 100, 157
- `skills/issue-size-review/SKILL.md` — line 96
- `skills/wire-issue/SKILL.md` — lines 89–90
- `commands/refine-issue.md` — line 87
- `commands/ready-issue.md` — line 88

### Dependent Files (Callers/Importers)
- N/A — these are skill/command files invoked by users, not imported

### Similar Patterns
- `skills/create-eval-from-issues/SKILL.md` — uses `ll-issues show "$ID" --json` and extracts the `path` field from JSON output; the underlying resolution (`_resolve_issue_id`) is the same function `ll-issues path` calls, so behavior is equivalent

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`ll-issues path` confirmed behavior** (`scripts/little_loops/cli/issues/path_cmd.py:14-42`):
- Returns exit code `0` + prints **relative** path to stdout on success (relative to project root); absolute-path fallback only if path is outside project root
- Returns exit code `1` + prints `Error: Issue '<id>' not found.` to stderr on miss
- Searches `.issues/bugs/`, `.issues/features/`, `.issues/enhancements/`, `.issues/completed/`, `.issues/deferred/` (in that order) via `_resolve_issue_id` (`show.py:17-83`)
- Accepts all three formats: `1022`, `ENH-1022`, `P3-ENH-1022` (case-insensitive)
- Covered by `scripts/tests/test_issues_path.py` (304 lines, 5 test classes including `TestPathSearchesAllDirs`)

**manage-issue requires partial replacement only** (`skills/manage-issue/SKILL.md:62-87`):
- The `$SEARCH_DIR` case statement (lines 68-72) and the `else` branch (highest-priority-in-dir, lines 80-86) must be **preserved** — they serve the no-`ISSUE_ID` default mode
- **Only** the `if [ -n "$ISSUE_ID" ]; then` branch (line 78) is in scope
- The variable is `ISSUE_FILE` (not `FILE`) — must be preserved for downstream references

**go-no-go uses `$ID` not `$ISSUE_ID`** (`skills/go-no-go/SKILL.md:82-85`):
- The replacement variable is `$ID`: `FILE=$(ll-issues path "${ID}" 2>/dev/null)`
- Remove the full `for dir in .issues/{bugs,features,enhancements}/; do ... done` block (lines 82-85)

**confidence-check has two lookups** (`skills/confidence-check/SKILL.md`):
- Single-issue mode (lines 98-103): `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)` — remove surrounding `for dir` loop
- Sprint mode (lines 153-166): `FILE=$(ll-issues path "${id}" 2>/dev/null)` (lowercase `$id`) — preserve the surrounding `for id` outer loop and the warning-on-miss behavior (`echo "Warning: Sprint issue $id not found (skipping)"`)

**issue-size-review has sprint mode ONLY** (`skills/issue-size-review/SKILL.md:92-102`):
- No single-issue `find | grep` pattern exists — only the sprint-mode block (lines 92-102)
- Line 96 replacement: `FILE=$(ll-issues path "${id}" 2>/dev/null)` (lowercase `$id`)
- Remove the `for dir` inner loop (lines 94-99), preserve outer `for id` loop and warning-on-miss behavior

**wire-issue full block** (`skills/wire-issue/SKILL.md:82-92`):
- Full block to replace is lines 82-92 (includes `for dir` opener, completed/deferred skip, `if -d`, and the 2-line `find \` + `| grep` pipeline at lines 88-90)
- Replace entire block with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`

**ready-issue.md skips only `completed/`, not `deferred/`** (`commands/ready-issue.md:82-94`):
- Currently skips `completed_dir` at line 84 but has no `deferred_dir` skip — unlike `refine-issue.md` which skips both
- The `ll-issues path` migration implicitly fixes this inconsistency: all dirs searched uniformly

### Tests
- N/A — shell script changes in markdown skill files; no unit tests to update

_Wiring pass added by `/ll:wire-issue`:_
- No existing tests will break — the target files are markdown, not Python
- `scripts/tests/test_issues_path.py` — already covers `ll-issues path` exit codes (0/1), relative-path output, and `completed/`+`deferred/` directory search; no updates needed
- `scripts/tests/test_update_skill.py:122-129` — established codebase pattern for content-asserting tests on SKILL.md files (asserts a deprecated shell pattern was removed); a new `scripts/tests/test_enh_1022_migration.py` following this pattern could assert `find.*maxdepth.*grep.*-E` is absent from all 8 target files and `ll-issues path` is present — automates the manual `grep` verification in Step 7 (optional but recommended)

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:115` — **pre-existing gap (from FEAT-1009, out of scope)**: `ll-issues` sub-command list reads `(next-id, list, show, sequence, impact-effort, refine-status)` and omits `path`; `skills/init/SKILL.md:521,545` (the init template) already includes `path` — recommend a separate fix independent of this migration

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/reference/API.md:2940` — `main_issues` sub-command table lists `show`, `sequence`, etc. but omits `path` and `skip`; pre-existing gap from FEAT-1009 (same root cause as `.claude/CLAUDE.md:115` — recommend fixing both in one pass, separate from this migration)

### Configuration
- N/A

## Implementation Steps

1. **`skills/manage-issue/SKILL.md` line 78** — partial replacement only:
   - Replace the inner find line: `ISSUE_FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
   - **Preserve** the `$SEARCH_DIR` case statement (lines 68-72) and `else` branch (lines 80-86)
   - Variable name stays `ISSUE_FILE` (not `FILE`)

2. **`skills/format-issue/SKILL.md` lines 106-117** — full loop replacement:
   - Remove the `FILE=""` + `for dir` loop + inner find block
   - Replace with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`

3. **`skills/go-no-go/SKILL.md` lines 82-85** — uses `$ID` (not `$ISSUE_ID`):
   - Remove `for dir in .issues/{bugs,features,enhancements}/; do ... done` block
   - Replace with `FILE=$(ll-issues path "${ID}" 2>/dev/null)`

4. **`skills/confidence-check/SKILL.md` lines 98-103** (single-issue mode) and **lines 153-166** (sprint mode):
   - Single-issue: remove `for dir` loop + find; replace with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
   - Sprint mode: remove inner `for dir` loop (lines 155-160); replace with `FILE=$(ll-issues path "${id}" 2>/dev/null)` (lowercase `$id`); **preserve** outer `for id` loop and warning-on-miss (`echo "Warning: Sprint issue $id not found (skipping)"`)

5. **`skills/issue-size-review/SKILL.md` lines 92-102** — sprint loop only, uses `$id` (lowercase):
   - Remove inner `for dir` loop (lines 94-99)
   - Replace with `FILE=$(ll-issues path "${id}" 2>/dev/null)`
   - **Preserve** outer `for id` loop and warning-on-miss

6. **`skills/wire-issue/SKILL.md` lines 82-92** — full block including 2-line `find \` + `| grep` pipeline:
   - Remove entire `for dir in {{config.issues.base_dir}}/*/; do ... done` block (lines 82-92)
   - Replace with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`

7. **`commands/refine-issue.md` lines 82-93**, **`commands/ready-issue.md` lines 82-94** — full loop replacement:
   - Remove `for dir` loop + skip guards + inner find block
   - Replace with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
   - `ready-issue.md` fix also implicitly adds `deferred/` searching (currently absent)

7. Verify: `grep -r "find.*maxdepth.*grep.*-E" skills/ commands/` returns zero matches

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **`skills/confidence-check/SKILL.md:94`** — update prose header "locate the issue file across active categories" to drop the "active categories" qualifier (since `ll-issues path` also searches `completed/` and `deferred/`); e.g., change to "Locate the issue file by ID:"
9. (Optional) Create `scripts/tests/test_enh_1022_migration.py` — follow pattern from `scripts/tests/test_update_skill.py:122-129`; assert the old `find.*maxdepth.*grep.*-E` pattern is absent from all 8 target files and `ll-issues path` is present in each; this automates the manual verification in Step 7
10. **`skills/go-no-go/SKILL.md:105`** — update the comment `# Resolve each ID to a file path using the same find pattern as Case 1` (in Case 2's for-loop body); after Case 1's find block is replaced with `ll-issues path`, this comment is stale — change to e.g. `# Resolve each ID to its file path`
11. **Sprint-mode warning text** — `skills/issue-size-review/SKILL.md:101` and `skills/confidence-check/SKILL.md:164` currently emit `"Warning: Sprint issue $id not found in active issues (skipping)"`. After migration, `ll-issues path`'s own stderr is silenced via `2>/dev/null`, so the warning must be emitted explicitly by the shell block. Replace wording with `echo "Warning: Sprint issue $id not found (skipping)"` — drop "in active issues" since `ll-issues path` searches all dirs, making the qualifier inaccurate
12. (Optional test scope) — In `scripts/tests/test_enh_1022_migration.py`, the `manage-issue` negative assertion must NOT broadly check `find` + `maxdepth` — the `else` branch retains a `find -maxdepth 1` for highest-priority-in-dir mode. Instead, assert absence of `grep -E "[-_]${ISSUE_ID}[-_.]"` specifically (the unique fingerprint of the ID-lookup pattern)

## Impact

- **Priority**: P3 — Correctness improvement (missed lookups in completed/deferred) + reduces duplication across 8 files
- **Effort**: Small — Mechanical search-and-replace in 8 markdown files
- **Risk**: Low — `ll-issues path` is already tested; canonical CLI is the reference implementation in `create-eval-from-issues`
- **Breaking Change**: No

## Success Metrics

- `grep -r "find.*maxdepth.*grep.*-E" skills/ commands/` returns 0 matches
- All 8 files use `ll-issues path` for ID→path resolution

## Scope Boundaries

Files that use `find` to **enumerate all active issues** (not ID→path lookup) are explicitly out of scope:
- `commands/verify-issues.md`, `commands/align-issues.md`, `commands/normalize-issues.md`, `commands/sync-issues.md`
- `skills/format-issue/SKILL.md` batch mode (`ALL_MODE`)
- `skills/confidence-check/SKILL.md` batch mode

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `refactor`, `captured`

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-11T03:51:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fb7eb6f-8deb-41e5-aa4d-459ae4b5765d.jsonl`
- `/ll:manage-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-04-11T03:46:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44510ef5-4a64-4ede-8e78-109d9ab3a513.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a6ba73a0-551f-4a18-80df-e5f87aefff1e.jsonl`
- `/ll:wire-issue` - 2026-04-11T03:38:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe9849b2-c9ca-4d60-92fc-cfd769be2923.jsonl`
- `/ll:wire-issue` - 2026-04-11T03:30:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/659ec7d9-c3a6-420e-8d7b-69bffa5211e3.jsonl`
- `/ll:refine-issue` - 2026-04-11T03:25:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c12c3590-c6bf-477d-a7d4-efac11be037c.jsonl`
- `/ll:format-issue` - 2026-04-11T03:22:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/118942ee-b3c8-4f1a-91e4-c62e1a5da527.jsonl`
- `/ll:refine-issue` - 2026-04-11T03:19:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b0e24d9-9939-46ca-8a19-b2fd49f87d61.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a587f97e-afd1-46fe-a9ac-dfcf57d1753f.jsonl`

---

## Resolution

**Resolved** | 2026-04-11

All 8 ad-hoc `find | grep -E` ID-lookup blocks replaced with `ll-issues path "${ISSUE_ID}" 2>/dev/null` across:
- `skills/manage-issue/SKILL.md` — partial (if-branch only, `$SEARCH_DIR`/else preserved)
- `skills/format-issue/SKILL.md` — full loop
- `skills/go-no-go/SKILL.md` — full loop; stale comment updated
- `skills/confidence-check/SKILL.md` — single-issue mode + sprint mode; prose header updated
- `skills/issue-size-review/SKILL.md` — sprint mode inner loop
- `skills/wire-issue/SKILL.md` — full block
- `commands/refine-issue.md` — loop inside path-detection guard
- `commands/ready-issue.md` — loop inside path-detection guard; implicit `deferred/` gap fixed

`grep -r "find.*maxdepth.*grep.*-E" skills/ commands/` returns 0 matches.

## Status

**Completed** | Created: 2026-04-10 | Priority: P3
