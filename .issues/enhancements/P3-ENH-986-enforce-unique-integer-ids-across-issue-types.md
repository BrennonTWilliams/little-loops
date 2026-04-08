---
discovered_date: 2026-04-07
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-986: Enforce Unique Integer IDs Across Issue Types

## Summary

The integer portion of an issue ID must be globally unique across all issue types. Currently nothing prevents `ENH-016` and `FEAT-016` from coexisting, which constitutes an ID collision and can cause ambiguity when referencing issues by number alone.

## Current Behavior

`/ll:normalize-issues` and `ll-issues` (including `next-id`) operate per-type or do not validate cross-type uniqueness. Two issues can share the same integer ID as long as they have different type prefixes (e.g., `ENH-016` and `FEAT-016`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**What is already implemented (no changes needed):**
- `get_next_issue_number()` at `scripts/little_loops/issue_parser.py:113` already scans all dirs (bugs, features, enhancements, completed, deferred) using a union prefix regex (`(?:BUG|FEAT|ENH)-(\d+)`) and returns `max_integer + 1` globally across all types.
- `normalize-issues` Step 1b at `commands/normalize-issues.md:156-177` already builds an `integer→file` map across the entire `.issues/` tree and uses `uniq -d` to flag duplicate integers across types.
- Collision resolution (renumber to next available ID via `ll-issues next-id`) already exists in `normalize-issues`.
- `test_global_uniqueness_across_types` at `scripts/tests/test_issue_parser.py:753` and `test_global_uniqueness_with_higher_in_completed` at `test_issue_parser.py:781` already verify cross-type uniqueness of `get_next_issue_number`.
- `capture-issue` skill at `skills/capture-issue/SKILL.md:198-204` already calls `ll-issues next-id` (globally-scoped) for every new issue.

**Actual remaining gap:**
The `PreToolUse` hook at `hooks/scripts/check-duplicate-issue-id.sh:64,107` extracts and checks the full typed ID string (e.g., `BUG-007`) — not the bare integer. A new file `P2-FEAT-007-foo.md` would search for `FEAT-007` in existing basenames; an existing `P2-BUG-007-bar.md` would not match, so the write proceeds. Cross-type integer collisions are therefore **not caught at write time** by the hook.

## Expected Behavior

- The integer portion of every issue ID is unique across all types (bugs, features, enhancements, deferred, completed).
- `ll-issues next-id` returns the next integer not used by **any** issue regardless of type.
- `/ll:normalize-issues` detects and reports integer ID collisions as an error condition.
- Collision resolution offers renumbering one of the conflicting issues to the next available ID.

## Motivation

Issue IDs are frequently referenced in commit messages, PR descriptions, dependency chains (`depends_on`, `blocks`), and conversation. If two issues share the same integer, references like "see #016" or `--id 016` are ambiguous. The type prefix being part of the name does not protect against this in practice — the number is the meaningful identifier and must be treated as globally unique.

## Proposed Solution

Update `hooks/scripts/check-duplicate-issue-id.sh` to extract the bare integer from the new filename and search for any existing `.issues/**/*.md` file containing that integer (regardless of type prefix), not just the same typed ID string.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The hook at `hooks/scripts/check-duplicate-issue-id.sh:62-68` currently does:
```bash
ISSUE_ID=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | head -1)
# ...
if echo "$BASENAME" | grep -qE "(^|[-_])${ISSUE_ID}([-_.]|$)"; then
```

Fix: after extracting `ISSUE_ID` (e.g. `FEAT-007`), also extract the bare integer (`007`) and scan all `.issues/**/*.md` basenames for any file containing that integer with any type prefix:
```bash
ISSUE_NUM=$(echo "$ISSUE_ID" | grep -oE '[0-9]{3,}')
# Check cross-type: any file with same integer but different type prefix
if find "$ISSUES_BASE_DIR" -name "*.md" | xargs -I{} basename {} | \
   grep -qE "(BUG|FEAT|ENH)-0*${ISSUE_NUM}([-_.]|$)"; then
    # deny: cross-type collision
fi
```

The hook already uses an advisory lock at `.issues/.issue-id.lock` (line ~90) to narrow the race window — this should be preserved. Follow the existing allow/deny JSON output format used throughout the hook.

## Scope Boundaries

- **In scope**: Updating `ll-issues next-id` to scan all issue directories globally, adding cross-type collision detection to `/ll:normalize-issues`, updating `capture-issue` to use globally-scoped ID assignment
- **Out of scope**: Changing the type prefix scheme or ID format, bulk renaming non-colliding existing issues, enforcing ID uniqueness in external references (commit messages, PR descriptions)

## Integration Map

### Files to Modify
- `hooks/scripts/check-duplicate-issue-id.sh:62-107` — update to extract bare integer and check cross-type (the actual gap; all other components already enforce global uniqueness)

### Files Verified As Already Correct (No Changes Needed)
- `scripts/little_loops/issue_parser.py:113-153` — `get_next_issue_number()` already scans all dirs cross-type via union prefix regex
- `scripts/little_loops/cli/issues/next_id.py:11-24` — `cmd_next_id` thin wrapper, calls `get_next_issue_number`; prints as `{next_num:03d}`
- `commands/normalize-issues.md:156-177` — Step 1b already builds cross-type integer→file map; detects and reports duplicates
- `skills/capture-issue/SKILL.md:198-204` — already calls `ll-issues next-id` (globally scoped) for ID assignment

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_lifecycle.py:463` — imports and calls `get_next_issue_number` during ID assignment
- `scripts/little_loops/sync.py:20` — imports `get_next_issue_number` for GitHub sync
- `commands/normalize-issues.md:241` — references `ll-issues next-id` for ID assignment during normalization
- `hooks/hooks.json:29-40` — wires `check-duplicate-issue-id.sh` as `PreToolUse` hook on `Write|Edit`

### Similar Patterns
- `scripts/tests/test_hooks_integration.py:999-1090` — `TestDuplicateIssueId` class: pattern to follow for new cross-type collision tests (uses `subprocess.run` with JSON piped to stdin, `ThreadPoolExecutor` for concurrency tests)
- `commands/normalize-issues.md:156-177` — bash pattern for cross-type integer extraction (`grep -oE '[0-9]{3,}'`) to reference in hook update

### Tests
- `scripts/tests/test_issue_parser.py:753` — `test_global_uniqueness_across_types` (already exists, passes — no change needed)
- `scripts/tests/test_issue_parser.py:781` — `test_global_uniqueness_with_higher_in_completed` (already exists, passes)
- `scripts/tests/test_hooks_integration.py:999` — add new test to `TestDuplicateIssueId` class: assert that writing `P2-FEAT-007-foo.md` is denied when `P2-BUG-007-bar.md` already exists
- `scripts/tests/test_issues_cli.py:17-38` — existing `TestIssuesCLINextId` tests (already pass)

### Documentation
- `docs/reference/CLI.md:382` — documents `ll-issues next-id` as "globally unique across all types" (already accurate; no update needed)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md:819-835` — "Duplicate issue ID not detected" section currently describes only same-type collision detection (manual test example uses `P2-BUG-001-test.md` against existing `BUG-001`); update to describe cross-type integer scope after ENH-986
- `docs/guides/GETTING_STARTED.md:172` — states `"IDs are globally unique across all types — you won't have both BUG-007 and FEAT-007"` but currently overstates hook enforcement (the hook does NOT enforce this yet); after ENH-986 the claim becomes accurate — no text change required but verify the statement holds post-implementation

### Configuration
- N/A

## API/Interface

```python
# next-id should scan all active + completed + deferred directories
# normalize-issues should report cross-type collisions
```

## Implementation Steps

_Updated by `/ll:refine-issue` with concrete file references. Steps 1–4 are already implemented; only Step 5 represents real work._

1. ~~Audit `ll-issues next-id`~~ — Already global: `issue_parser.py:113-153` scans all 5 dirs with union prefix regex.
2. ~~Add collision detection to `normalize-issues`~~ — Already exists: `commands/normalize-issues.md:156-177` (Step 1b) builds integer→file map and flags cross-type duplicates; collision resolution (renumber via `ll-issues next-id`) is at `normalize-issues.md:257-259`.
3. ~~Add collision resolution flow~~ — Already implemented in `normalize-issues`.
4. ~~Update `capture-issue`~~ — Already calls `ll-issues next-id` (globally scoped) at `skills/capture-issue/SKILL.md:198-204`.
5. **Update `hooks/scripts/check-duplicate-issue-id.sh:62-107`** — extract bare integer after line 64 (`ISSUE_NUM=$(echo "$ISSUE_ID" | grep -oE '[0-9]{3,}')`); add a cross-type scan using `find "$ISSUES_BASE_DIR" -name "*.md"` checking for any `(BUG|FEAT|ENH)-0*${ISSUE_NUM}` match; output deny JSON following the existing format in the hook. Preserve advisory lock at `.issues/.issue-id.lock`.
6. **Add cross-type hook test** — add a test to `TestDuplicateIssueId` at `scripts/tests/test_hooks_integration.py:999` asserting that a new file `P2-FEAT-007-foo.md` is denied when `P2-BUG-007-bar.md` already exists (follow the `subprocess.run` + JSON stdin pattern established in the class).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/development/TROUBLESHOOTING.md:819-835` — revise "Duplicate issue ID not detected" section and its manual test example to reflect cross-type integer collision scope (not just same-type)

## Impact

- **Priority**: P3 - Prevents silent ID collisions that corrupt dependency graphs and references
- **Effort**: Small - Mostly a scan-scope change in `next-id` and an additional validation pass in normalize
- **Risk**: Low - Read-only validation addition; renumbering is opt-in
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `issue-management`, `normalize-issues`, `ll-issues`, `captured`

---

## Status

**Open** | Created: 2026-04-07 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e44fb90d-b4e4-4ad9-9419-1afaa1fdfa63.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` - 2026-04-08T01:51:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35ae828f-0aec-4a66-9fb1-4a01389cf7d4.jsonl`
- `/ll:format-issue` - 2026-04-08T01:46:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/465921c9-f0f4-460c-8b95-af465f70d003.jsonl`
- `/ll:capture-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbefe1f9-2164-43d3-b547-be6f8fadffe4.jsonl`
