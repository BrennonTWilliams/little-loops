---
discovered_date: 2026-04-10
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 85
parent_issue: FEAT-1027
blocked_by: FEAT-1028
---

# FEAT-1029: audit-issue-conflicts — Wiring, Docs, and Tests

## Summary

Wire the new `audit-issue-conflicts` skill into all registry files and documentation, and write the structural test file. Depends on FEAT-1028 (skill file must exist first).

## Motivation

This feature ensures:
- **Discoverability**: The new `audit-issue-conflicts` skill appears in help, README, and all documentation surfaces so users can find and use it
- **Registry consistency**: Skill count discrepancies across docs are corrected, preventing confusion about the number of available skills
- **Test coverage**: Structural tests verify the skill file's contract, catching regressions if the skill file is removed or malformed

## Use Case

**Who**: A little-loops developer or plugin maintainer

**Context**: After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill exists but is invisible — absent from help listings, README tables, all doc references, and uncovered by tests

**Goal**: Wire the new skill into every discovery surface and add structural tests that verify the skill file's contract

**Outcome**: `audit-issue-conflicts` appears in all expected places; `ll-verify-docs` passes; the 7-assertion test suite confirms the skill file is present and well-formed

## Parent Issue

Decomposed from FEAT-1027: Issue Conflict Audit Skill with Auto-Apply

## Current Behavior

After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill works but is absent from:
- `commands/help.md` (hardcoded skill listing)
- `README.md` (skill count + command table)
- `CONTRIBUTING.md` (skill count + directory tree)
- `docs/ARCHITECTURE.md` (skill count + directory listing)
- `docs/reference/COMMANDS.md` (`--auto`/`--dry-run` consumer lists + subsection)
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` ("Plan a Feature Sprint" recipe)
- `.claude/CLAUDE.md` (command list)
- No structural tests exist

## Expected Behavior

All registry files and documentation reflect the new skill. Structural tests verify the skill file's contract.

## Acceptance Criteria

- [ ] `commands/help.md` — `/ll:audit-issue-conflicts` added to ISSUE REFINEMENT block (lines 44–81) and Quick Reference Table (`Issue Refinement` entry, ~line 254)
- [ ] `README.md` — skill count bumped `25 → 26` (line 89); `/ll:audit-issue-conflicts` row added to Issue Refinement table (lines 108–123)
- [ ] `CONTRIBUTING.md` — skill count bumped `25 → 26` (line 125); `audit-issue-conflicts/` added to skill directory tree after `audit-docs/`
- [ ] `docs/ARCHITECTURE.md` — skill count bumped `25 → 26` at lines 26 and 99; `├── audit-issue-conflicts/` added between `audit-claude-config/` and `audit-docs/` (lines 104–107)
- [ ] `docs/reference/COMMANDS.md` — `audit-issue-conflicts` in `--auto` consumer list (line 14) and `--dry-run` consumer list (line 15); `### /ll:audit-issue-conflicts` subsection added after `/ll:tradeoff-review-issues` (~line 204)
- [ ] `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `audit-issue-conflicts` added to "Plan a Feature Sprint" recipe (~line 484) as step 3.5 before `tradeoff-review-issues`
- [ ] `.claude/CLAUDE.md` — `audit-issue-conflicts`^ added to Issue Refinement or Meta-Analysis section
- [ ] `scripts/tests/test_audit_issue_conflicts_skill.py` exists and asserts: (1) `skills/audit-issue-conflicts/SKILL.md` exists, (2) `--dry-run` token present, (3) `--auto` token present, (4) severity labels (`high`, `medium`, `low`) present, (5) conflict type tokens (`requirement`, `objective`, `architecture`, `scope`) present, (6) `"No conflicts found"` path documented, (7) `{{config.issues.base_dir}}` glob pattern referenced
- [ ] `ll-verify-docs` passes after all changes

## API/Interface

N/A - No public API changes. This issue is purely documentation wiring and structural test creation.

## Proposed Solution

### Wiring Steps

Work through each file in order. All changes are mechanical and well-specified:

**`commands/help.md`**
- Add `/ll:audit-issue-conflicts` entry to ISSUE REFINEMENT block (lines 44–81)
- Add entry to Quick Reference Table (`Issue Refinement:` entry, ~line 254)

**`README.md`**
- Bump skill count `25 → 26` at line 89
- Add `/ll:audit-issue-conflicts` row to Issue Refinement command table (lines 108–123)

**`CONTRIBUTING.md`**
- Bump skill count `25 → 26` at line 125
- Add `audit-issue-conflicts/` to skill directory tree after `audit-docs/` (lines 125–148)

**`docs/ARCHITECTURE.md`**
- Bump skill count `25 → 26` at lines 26 and 99
- Add `├── audit-issue-conflicts/` between `audit-claude-config/` and `audit-docs/` (lines 104–107)

**`docs/reference/COMMANDS.md`**
- Append `audit-issue-conflicts` to `--auto` consumer list (line 14)
- Append `audit-issue-conflicts` to `--dry-run` consumer list (line 15)
- Add `### /ll:audit-issue-conflicts` subsection after `/ll:tradeoff-review-issues` (~line 204)

**`docs/guides/ISSUE_MANAGEMENT_GUIDE.md`**
- Add step 3.5 in "Plan a Feature Sprint" recipe at ~line 484: `/ll:audit-issue-conflicts` with label "← detect conflicting requirements"

**`.claude/CLAUDE.md`**
- Add `audit-issue-conflicts`^ to Issue Refinement section in command list

### Test File

Follow exact pattern from `scripts/tests/test_improve_claude_md_skill.py`. 7 assertions:

```python
# scripts/tests/test_audit_issue_conflicts_skill.py

from pathlib import Path

SKILL_FILE = Path("skills/audit-issue-conflicts/SKILL.md")

def test_skill_file_exists():
    assert SKILL_FILE.exists()

def test_dry_run_flag():
    assert "--dry-run" in SKILL_FILE.read_text()

def test_auto_flag():
    assert "--auto" in SKILL_FILE.read_text()

def test_severity_labels():
    content = SKILL_FILE.read_text()
    for label in ("high", "medium", "low"):
        assert label in content

def test_conflict_types():
    content = SKILL_FILE.read_text()
    for ctype in ("requirement", "objective", "architecture", "scope"):
        assert ctype in content

def test_no_conflicts_path():
    assert "No conflicts found" in SKILL_FILE.read_text()

def test_config_issues_base_dir_glob():
    assert "{{config.issues.base_dir}}" in SKILL_FILE.read_text()
```

## Integration Map

### Files to Modify

- `commands/help.md` — ISSUE REFINEMENT block + Quick Reference Table
- `README.md` — skill count + command table row
- `CONTRIBUTING.md` — skill count + directory tree entry
- `docs/ARCHITECTURE.md` — skill count (×2) + directory listing entry
- `docs/reference/COMMANDS.md` — `--auto`/`--dry-run` lists + new subsection
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "Plan a Feature Sprint" recipe
- `.claude/CLAUDE.md` — command list

### New Files to Create

- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural test file

### Similar Patterns

- `scripts/tests/test_improve_claude_md_skill.py` — structural test pattern to follow exactly

### Dependent Files (Callers/Importers)

- N/A — registry and doc files are terminal; no code imports them

### Tests

- `scripts/tests/test_audit_issue_conflicts_skill.py` — new structural test file (7 assertions)

### Documentation

- `commands/help.md`, `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/reference/COMMANDS.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, `.claude/CLAUDE.md` — all updated as part of this issue

### Configuration

- N/A

## Implementation Steps

1. **Read each wiring file** to confirm current line numbers match issue spec (line numbers may have shifted)
2. **Update `commands/help.md`** — add ISSUE REFINEMENT block entry + Quick Reference Table entry
3. **Update `README.md`** — bump count + add table row
4. **Update `CONTRIBUTING.md`** — bump count + add directory tree entry
5. **Update `docs/ARCHITECTURE.md`** — bump count (×2) + add directory listing entry
6. **Update `docs/reference/COMMANDS.md`** — append to `--auto`/`--dry-run` lists + add subsection
7. **Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** — add step 3.5
8. **Update `.claude/CLAUDE.md`** — add `audit-issue-conflicts`^
9. **Write `scripts/tests/test_audit_issue_conflicts_skill.py`** — 7 assertions
10. **Run `ll-verify-docs`** — confirm passes
11. **Run `python -m pytest scripts/tests/test_audit_issue_conflicts_skill.py`** — confirm all 7 assertions pass

## Impact

- **Priority**: P3 - Medium value
- **Effort**: Small - Mechanical wiring; no logic to implement
- **Risk**: Very Low - Documentation and test changes only
- **Breaking Change**: No

## Labels

`feature`, `issue-management`, `audit`, `wiring`, `docs`, `tests`

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-04-11T05:00:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9aecef0c-ff24-4be0-8fdf-2ff69523276c.jsonl`
- `/ll:issue-size-review` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1583f95-f6e7-426b-b174-369fd745725e.jsonl`
