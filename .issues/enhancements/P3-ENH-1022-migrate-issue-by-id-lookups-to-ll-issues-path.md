---
id: ENH-1022
type: ENH
priority: P3
status: open
discovered_date: 2026-04-10
discovered_by: capture-issue
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
- Returns exit code `0` + prints relative path to stdout on success
- Returns exit code `1` + prints `Error: Issue '<id>' not found.` to stderr on miss
- Searches `.issues/bugs/`, `.issues/features/`, `.issues/enhancements/`, `.issues/completed/`, `.issues/deferred/` (in that order) via `_resolve_issue_id` (`show.py:62-67`)
- Accepts all three formats: `1022`, `ENH-1022`, `P3-ENH-1022` (case-insensitive)

**manage-issue requires partial replacement only** (`skills/manage-issue/SKILL.md:62-87`):
- The `$SEARCH_DIR` case statement (lines 68-72) and the `else` branch (highest-priority-in-dir, lines 80-86) must be **preserved** — they serve the no-`ISSUE_ID` default mode
- **Only** the `if [ -n "$ISSUE_ID" ]; then` branch (line 78) is in scope
- The variable is `ISSUE_FILE` (not `FILE`) — must be preserved for downstream references

**go-no-go uses `$ID` not `$ISSUE_ID`** (`skills/go-no-go/SKILL.md:81-85`):
- The replacement variable is `$ID`: `FILE=$(ll-issues path "${ID}" 2>/dev/null)`
- The outer `for dir` loop at line 82 is removed along with the inner find at line 83

**confidence-check sprint mode uses `$id` (lowercase)** (`skills/confidence-check/SKILL.md:153-165`):
- Line 157 replacement: `FILE=$(ll-issues path "${id}" 2>/dev/null)`
- Remove the surrounding `for dir` loop (lines 155-160)

**issue-size-review sprint mode uses `$id` (lowercase)** (`skills/issue-size-review/SKILL.md:92-103`):
- Line 96 replacement: `FILE=$(ll-issues path "${id}" 2>/dev/null)`
- Remove the surrounding `for dir` loop (lines 94-99)

### Tests
- N/A — shell script changes in markdown skill files; no unit tests to update

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. **`skills/manage-issue/SKILL.md` line 78** — partial replacement only:
   - Replace the inner find line: `ISSUE_FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
   - **Preserve** the `$SEARCH_DIR` case statement (lines 68-72) and `else` branch (lines 80-86)
   - Variable name stays `ISSUE_FILE` (not `FILE`)

2. **`skills/format-issue/SKILL.md` line 111**, **`skills/go-no-go/SKILL.md` lines 82-85**, **`commands/refine-issue.md` lines ~82-90**, **`commands/ready-issue.md` lines ~83-91** — full loop replacement:
   - Remove the `FILE=""` + `for dir` loop + inner find block
   - Replace with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`

3. **`skills/go-no-go/SKILL.md` lines 82-85** — uses `$ID` (not `$ISSUE_ID`):
   - Replace with `FILE=$(ll-issues path "${ID}" 2>/dev/null)`

4. **`skills/confidence-check/SKILL.md` lines 97-108** (single-issue mode) and **lines 153-165** (sprint mode):
   - Single-issue: replace for loop + find with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
   - Sprint mode (line 157): replace with `FILE=$(ll-issues path "${id}" 2>/dev/null)` (lowercase `$id`)

5. **`skills/issue-size-review/SKILL.md` lines 92-103** — sprint loop uses `$id` (lowercase):
   - Replace with `FILE=$(ll-issues path "${id}" 2>/dev/null)`

6. **`skills/wire-issue/SKILL.md` lines 83-97** (2-line find block):
   - Replace `FILE=$(find ... \` + `| grep ...) with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`

7. Verify: `grep -r "find.*maxdepth.*grep.*-E" skills/ commands/` returns zero matches

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
- `/ll:refine-issue` - 2026-04-11T03:19:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b0e24d9-9939-46ca-8a19-b2fd49f87d61.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a587f97e-afd1-46fe-a9ac-dfcf57d1753f.jsonl`

---

## Status

**Open** | Created: 2026-04-10 | Priority: P3
