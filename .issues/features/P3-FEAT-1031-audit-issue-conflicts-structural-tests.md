---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 100
parent_issue: FEAT-1029
blocked_by: FEAT-1028
---

# FEAT-1031: audit-issue-conflicts — Structural Tests

## Summary

Write the structural test file for `audit-issue-conflicts` that verifies the skill file's contract. Depends on FEAT-1028 (skill file must exist first).

## Current Behavior

No structural test file exists for `audit-issue-conflicts`. After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, there is no automated verification that the skill file is present, well-formed, or contains the expected content tokens.

## Expected Behavior

`scripts/tests/test_audit_issue_conflicts_skill.py` exists and all 7 assertions pass: skill file presence, `--dry-run`, `--auto`, severity labels (`high`, `medium`, `low`), conflict type tokens (`requirement`, `objective`, `architecture`, `scope`), `"No conflicts found"` path, and `{{config.issues.base_dir}}` glob pattern.

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

## API/Interface

N/A - No public API changes (new test file only)

## Proposed Solution

Follow exact pattern from `scripts/tests/test_improve_claude_md_skill.py`. Use `Path(__file__).parent.parent.parent` to anchor to the project root — not a relative `Path("skills/...")` — or tests break when pytest runs from a different working directory.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Canonical pattern corrections** (from `test_improve_claude_md_skill.py:11-16`):
- Use `PROJECT_ROOT` (not `ROOT`) — the existing skill test files use this name
- Add `from __future__ import annotations` as the first import
- Wrap tests in a class `TestAuditIssueConflictsSkillExists` with docstrings on every method and `-> None` return types
- Use guard pattern in each test: `assert SKILL_FILE.exists(), "Skill file not found"` before any `read_text()` call (not just in `test_skill_file_exists`)

**Critical fix — acceptance criterion #6**: The SKILL.md uses `"No conflicts detected"` (not `"No conflicts found"`). Asserting the latter will fail. Verified at `skills/audit-issue-conflicts/SKILL.md` (grep confirms no match for `"No conflicts found"`).

**All other tokens confirmed present** in `skills/audit-issue-conflicts/SKILL.md`:
- `"--dry-run"` — present
- `"--auto"` — present
- `"high"`, `"medium"`, `"low"` — severity labels present
- `"requirement"`, `"objective"`, `"architecture"`, `"scope"` — conflict type tokens present
- `"{{config.issues.base_dir}}"` — glob pattern present (multiple occurrences)

```python
# scripts/tests/test_audit_issue_conflicts_skill.py
"""Structural tests for the audit-issue-conflicts skill (FEAT-1031)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "audit-issue-conflicts" / "SKILL.md"


class TestAuditIssueConflictsSkillExists:
    """Verify the audit-issue-conflicts skill file is present and well-formed."""

    def test_skill_file_exists(self) -> None:
        """Skill file must be present."""
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_dry_run_flag(self) -> None:
        """Skill must document --dry-run flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--dry-run" in SKILL_FILE.read_text()

    def test_auto_flag(self) -> None:
        """Skill must document --auto flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--auto" in SKILL_FILE.read_text()

    def test_severity_labels(self) -> None:
        """Skill must reference high, medium, and low severity labels."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for label in ("high", "medium", "low"):
            assert label in content

    def test_conflict_types(self) -> None:
        """Skill must reference all four conflict type tokens."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for ctype in ("requirement", "objective", "architecture", "scope"):
            assert ctype in content

    def test_no_conflicts_path(self) -> None:
        """Skill must document the no-conflicts output path."""
        assert SKILL_FILE.exists(), "Skill file not found"
        # NOTE: SKILL.md uses "No conflicts detected" (not "No conflicts found")
        assert "No conflicts detected" in SKILL_FILE.read_text()

    def test_config_issues_base_dir_glob(self) -> None:
        """Skill must reference the config.issues.base_dir glob pattern."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "{{config.issues.base_dir}}" in SKILL_FILE.read_text()
```

## Integration Map

### New Files to Create

- `scripts/tests/test_audit_issue_conflicts_skill.py` — structural test file (7 assertions)

### Similar Patterns

- `scripts/tests/test_improve_claude_md_skill.py` — structural test pattern to follow exactly

## Implementation Steps

1. **FEAT-1028 is already complete** — `skills/audit-issue-conflicts/SKILL.md` exists; blocker is resolved
2. **Create `scripts/tests/test_audit_issue_conflicts_skill.py`** — use the corrected code from Proposed Solution (class-based, `PROJECT_ROOT` anchor, guard pattern in each method, `"No conflicts detected"` not `"No conflicts found"`)
3. **Run `python -m pytest scripts/tests/test_audit_issue_conflicts_skill.py -v`** — confirm all 7 assertions pass

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
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a87c1420-a83d-43ba-b59a-1acbfc8d4f78.jsonl`
- `/ll:wire-issue` - 2026-04-11T17:46:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f7e2183-b845-49f7-9c98-af22e8f0d287.jsonl`
- `/ll:refine-issue` - 2026-04-11T17:37:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36b4e078-b3a3-4a8e-ba65-369011fd2841.jsonl`
- `/ll:format-issue` - 2026-04-11T05:35:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09f5ad48-02b2-4a2b-98cf-6d1da7ce2e95.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
