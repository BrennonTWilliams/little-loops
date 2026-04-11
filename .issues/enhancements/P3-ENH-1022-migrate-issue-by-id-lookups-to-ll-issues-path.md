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
- `skills/create-eval-from-issues/SKILL.md` — already uses `ll-issues path`; reference implementation

### Tests
- N/A — shell script changes in markdown skill files; no unit tests to update

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update 5 skill files: replace `for dir` + `find | grep` blocks with `FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)`
2. Update `wire-issue` skill (same pattern, 2 sites)
3. Update 2 command files: `refine-issue.md` and `ready-issue.md`
4. Verify: `grep -r "find.*maxdepth.*grep.*-E" skills/ commands/` returns zero matches

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
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a587f97e-afd1-46fe-a9ac-dfcf57d1753f.jsonl`

---

## Status

**Open** | Created: 2026-04-10 | Priority: P3
