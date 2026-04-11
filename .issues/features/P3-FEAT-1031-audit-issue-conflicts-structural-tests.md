---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 85
outcome_confidence: 80
parent_issue: FEAT-1029
blocked_by: FEAT-1028
---

# FEAT-1031: audit-issue-conflicts — Structural Tests

## Summary

Write the structural test file for `audit-issue-conflicts` that verifies the skill file's contract. Depends on FEAT-1028 (skill file must exist first).

## Motivation

After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, no tests verify the skill file's contract. Structural tests catch regressions if the skill file is removed or malformed.

## Use Case

**Who**: A little-loops developer or plugin maintainer

**Context**: FEAT-1028 creates the skill file; no test coverage exists yet.

**Goal**: Create a 7-assertion test file that verifies the skill file's presence and key content contracts.

**Outcome**: `python -m pytest scripts/tests/test_audit_issue_conflicts_skill.py` passes with 7 assertions green.

## Parent Issue

Decomposed from FEAT-1029: audit-issue-conflicts — Wiring, Docs, and Tests

## Acceptance Criteria

- [ ] `scripts/tests/test_audit_issue_conflicts_skill.py` exists and asserts:
  1. `skills/audit-issue-conflicts/SKILL.md` exists
  2. `--dry-run` token present
  3. `--auto` token present
  4. severity labels (`high`, `medium`, `low`) present
  5. conflict type tokens (`requirement`, `objective`, `architecture`, `scope`) present
  6. `"No conflicts found"` path documented
  7. `{{config.issues.base_dir}}` glob pattern referenced
- [ ] All 7 assertions pass after FEAT-1028 is complete

## Proposed Solution

Follow exact pattern from `scripts/tests/test_improve_claude_md_skill.py`. Use `Path(__file__).parent.parent.parent` to anchor to the project root — not a relative `Path("skills/...")` — or tests break when pytest runs from a different working directory.

```python
# scripts/tests/test_audit_issue_conflicts_skill.py

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = ROOT / "skills/audit-issue-conflicts/SKILL.md"

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

### New Files to Create

- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural test file (7 assertions)

### Similar Patterns

- `scripts/tests/test_improve_claude_md_skill.py` — structural test pattern to follow exactly

## Implementation Steps

1. **Verify FEAT-1028 is complete** — confirm `skills/audit-issue-conflicts/SKILL.md` exists; tests will fail without it
2. **Create `scripts/tests/test_audit_issue_conflicts_skill.py`** — 7 assertions using ROOT-anchored path
3. **Run `python -m pytest scripts/tests/test_audit_issue_conflicts_skill.py`** — confirm all 7 assertions pass

## Impact

- **Priority**: P3 - Medium value
- **Effort**: Trivial - Single test file creation following established pattern
- **Risk**: Very Low - New test file only
- **Breaking Change**: No

## Labels

`feature`, `issue-management`, `audit`, `tests`

## Status

**Open** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
