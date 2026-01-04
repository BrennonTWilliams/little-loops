"""Tests for little_loops.parallel.output_parsing module."""

from __future__ import annotations

import pytest

from little_loops.parallel.output_parsing import (
    parse_manage_issue_output,
    parse_ready_issue_output,
    parse_sections,
    parse_status_lines,
    parse_validation_table,
)


class TestParseSections:
    """Tests for parse_sections function."""

    def test_single_section(self) -> None:
        """Test parsing output with a single section."""
        output = """## RESULT
This is the result content.
"""
        sections = parse_sections(output)

        assert "RESULT" in sections
        assert sections["RESULT"] == "This is the result content."

    def test_multiple_sections(self) -> None:
        """Test parsing output with multiple sections."""
        output = """## METADATA
Issue: BUG-001
Priority: P0

## PLAN
1. Fix the bug
2. Add tests

## RESULT
Status: COMPLETED
"""
        sections = parse_sections(output)

        assert "METADATA" in sections
        assert "PLAN" in sections
        assert "RESULT" in sections
        assert "Issue: BUG-001" in sections["METADATA"]
        assert "1. Fix the bug" in sections["PLAN"]
        assert "COMPLETED" in sections["RESULT"]

    def test_preamble_content(self) -> None:
        """Test content before first section goes to PREAMBLE."""
        output = """Some intro text here.

## FIRST
First section content.
"""
        sections = parse_sections(output)

        assert "PREAMBLE" in sections
        assert "Some intro text here." in sections["PREAMBLE"]
        assert "FIRST" in sections

    def test_empty_output(self) -> None:
        """Test parsing empty output."""
        sections = parse_sections("")

        assert "PREAMBLE" in sections
        assert sections["PREAMBLE"] == ""

    def test_no_sections(self) -> None:
        """Test output with no section headers."""
        output = "Just some plain text\nwithout any sections."
        sections = parse_sections(output)

        assert "PREAMBLE" in sections
        assert "Just some plain text" in sections["PREAMBLE"]


class TestParseValidationTable:
    """Tests for parse_validation_table function."""

    def test_parse_table(self) -> None:
        """Test parsing a validation table."""
        content = """
| Check | Status | Details |
|-------|--------|---------|
| Format | PASS | All files formatted correctly |
| Tests | FAIL | 2 tests failing |
| Lint | WARN | 3 warnings found |
"""
        result = parse_validation_table(content)

        assert "Format" in result
        assert result["Format"]["status"] == "PASS"
        assert "formatted correctly" in result["Format"]["details"]

        assert "Tests" in result
        assert result["Tests"]["status"] == "FAIL"

        assert "Lint" in result
        assert result["Lint"]["status"] == "WARN"

    def test_skip_header_row(self) -> None:
        """Test that header row is skipped."""
        content = """
| Check | Status | Details |
|-------|--------|---------|
| Test | PASS | OK |
"""
        result = parse_validation_table(content)

        # Should not include 'Check' from header
        assert "Check" not in result
        assert "Test" in result

    def test_empty_table(self) -> None:
        """Test parsing empty content."""
        result = parse_validation_table("")
        assert result == {}

    def test_no_table(self) -> None:
        """Test content without table format."""
        content = "Some text without any table."
        result = parse_validation_table(content)
        assert result == {}


class TestParseStatusLines:
    """Tests for parse_status_lines function."""

    def test_parse_status_lines(self) -> None:
        """Test parsing status lines."""
        content = """
- tests: PASS
- lint: PASS
- types: FAIL
- format: WARN
"""
        result = parse_status_lines(content)

        assert result["tests"] == "PASS"
        assert result["lint"] == "PASS"
        assert result["types"] == "FAIL"
        assert result["format"] == "WARN"

    def test_uppercase_conversion(self) -> None:
        """Test that status values are uppercased."""
        content = "- item: pass"
        result = parse_status_lines(content)

        assert result["item"] == "PASS"

    def test_empty_content(self) -> None:
        """Test parsing empty content."""
        result = parse_status_lines("")
        assert result == {}


class TestParseReadyIssueOutput:
    """Tests for parse_ready_issue_output function."""

    def test_ready_verdict_new_format(self) -> None:
        """Test parsing READY verdict in new format."""
        output = """
## VALIDATION
| Check | Status | Details |
|-------|--------|---------|
| Format | PASS | OK |

## VERDICT
READY

The issue is ready for implementation.

## CONCERNS
- None
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True
        assert result["was_corrected"] is False
        assert result["should_close"] is False

    def test_not_ready_verdict_with_concerns(self) -> None:
        """Test parsing NOT_READY verdict with concerns."""
        output = """
## VALIDATION
| Check | Status | Details |
|-------|--------|---------|
| Files | FAIL | Missing file |

## VERDICT
NOT_READY

## CONCERNS
- Referenced file src/missing.py does not exist
- Code snippet outdated
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False
        assert len(result["concerns"]) == 2
        assert "src/missing.py" in result["concerns"][0]

    def test_corrected_verdict(self) -> None:
        """Test parsing CORRECTED verdict."""
        output = """
## VERDICT
CORRECTED

## CORRECTIONS_MADE
- Updated file path from old.py to new.py
- Fixed code snippet to match current implementation
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CORRECTED"
        assert result["is_ready"] is True
        assert result["was_corrected"] is True
        assert len(result["corrections"]) == 2

    def test_close_verdict(self) -> None:
        """Test parsing CLOSE verdict."""
        output = """
## VERDICT
CLOSE

## CLOSE_REASON
- Reason: already_fixed

## CLOSE_STATUS
Closed - Already Fixed
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CLOSE"
        assert result["should_close"] is True
        assert result["close_reason"] == "already_fixed"
        assert result["close_status"] == "Closed - Already Fixed"

    def test_close_verdict_with_bold_markers(self) -> None:
        """Test parsing CLOSE verdict when Claude adds bold markers."""
        output = """
## VERDICT
CLOSE

## CLOSE_REASON
- **Reason**: **already_fixed**

## CLOSE_STATUS
**Closed - Already Fixed**
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CLOSE"
        assert result["should_close"] is True
        assert result["close_reason"] == "already_fixed"

    def test_close_verdict_with_backticks(self) -> None:
        """Test parsing CLOSE verdict when Claude wraps value in backticks."""
        output = """
## VERDICT
CLOSE

## CLOSE_REASON
- Reason: `invalid_ref`

## CLOSE_STATUS
Closed - Invalid Reference
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CLOSE"
        assert result["should_close"] is True
        assert result["close_reason"] == "invalid_ref"

    def test_close_verdict_with_bold_and_backticks(self) -> None:
        """Test parsing CLOSE verdict with both bold markers and backticks."""
        output = """
## VERDICT
CLOSE

## CLOSE_REASON
- **Reason**: `already_fixed`

## CLOSE_STATUS
Closed - Already Fixed
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CLOSE"
        assert result["should_close"] is True
        assert result["close_reason"] == "already_fixed"

    def test_old_format_verdict(self) -> None:
        """Test parsing old format VERDICT: READY."""
        output = """
VERDICT: READY

The issue is ready.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_old_format_not_ready(self) -> None:
        """Test parsing old format NOT READY."""
        output = "VERDICT: NOT_READY"
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

    def test_unknown_verdict(self) -> None:
        """Test parsing output with no recognizable verdict."""
        output = "Some random output without a verdict."
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "UNKNOWN"
        assert result["is_ready"] is False

    def test_bold_verdict_stripped(self) -> None:
        """Test that markdown bold is stripped from verdict."""
        output = """
## VERDICT
**READY**
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_bracketed_verdict_stripped(self) -> None:
        """Test that brackets are stripped from verdict."""
        output = """
## VERDICT
[READY]
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"

    def test_old_format_concerns_fallback(self) -> None:
        """Test fallback concern detection in old format."""
        output = """
VERDICT: NOT_READY

WARNING: Missing dependency
Concern: Outdated code snippet
Issue: File not found
"""
        result = parse_ready_issue_output(output)

        assert len(result["concerns"]) >= 3
        assert any("WARNING" in c for c in result["concerns"])
        assert any("Concern" in c for c in result["concerns"])

    def test_verdict_in_code_block(self) -> None:
        """Test parsing verdict wrapped in code block."""
        output = """
## VERDICT
```
READY
```
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_verdict_in_code_block_with_language(self) -> None:
        """Test parsing verdict in code block with language specifier."""
        output = """
## VERDICT
```markdown
CORRECTED
```
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CORRECTED"
        assert result["is_ready"] is True

    def test_verdict_with_inline_backticks(self) -> None:
        """Test parsing verdict with inline code backticks."""
        output = """
## VERDICT
`NOT_READY`
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

    def test_single_hash_header(self) -> None:
        """Test parsing with single # header instead of ##."""
        output = """
# VERDICT
READY
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_verdict_with_explanation(self) -> None:
        """Test verdict with inline explanation text."""
        output = """
## VERDICT
READY - The issue is complete and ready for implementation
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"

    def test_verdict_space_variant(self) -> None:
        """Test verdict with space instead of underscore."""
        output = """
## VERDICT
NOT READY
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

    def test_verdict_hyphen_variant(self) -> None:
        """Test verdict with hyphen instead of underscore."""
        output = """
## VERDICT
NEEDS-REVIEW
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NEEDS_REVIEW"
        assert result["is_ready"] is False

    def test_verdict_near_keyword(self) -> None:
        """Test finding verdict near 'verdict' keyword without section."""
        output = """
After analysis, the verdict is READY for implementation.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_verdict_lowercase(self) -> None:
        """Test parsing lowercase verdict."""
        output = """
## VERDICT
ready
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_verdict_fallback_scan(self) -> None:
        """Test fallback to scanning entire output for verdict."""
        output = """
Some preamble text here.

After reviewing the issue, it is CORRECTED and ready to proceed.

More text follows.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CORRECTED"
        assert result["is_ready"] is True

    def test_validation_section_parsing(self) -> None:
        """Test that validation section is parsed."""
        output = """
## VALIDATION
| Check | Status | Details |
|-------|--------|---------|
| Format | PASS | OK |
| Tests | PASS | All pass |

## VERDICT
READY
"""
        result = parse_ready_issue_output(output)

        assert "validation" in result
        assert "Format" in result["validation"]
        assert result["validation"]["Format"]["status"] == "PASS"

    def test_sections_included_in_result(self) -> None:
        """Test that all sections are included in result."""
        output = """
## METADATA
Issue: BUG-001

## VERDICT
READY
"""
        result = parse_ready_issue_output(output)

        assert "sections" in result
        assert "METADATA" in result["sections"]
        assert "VERDICT" in result["sections"]

    def test_triple_hash_header(self) -> None:
        """Test parsing with ### header (3 hashes)."""
        output = """
### VERDICT
READY
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_no_space_after_hashes(self) -> None:
        """Test parsing when there's no space after hashes."""
        output = """
##VERDICT
READY
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_bold_in_header(self) -> None:
        """Test parsing when header name has bold markers."""
        output = """
## **VERDICT**
READY
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_phrasing_ready_for_implementation(self) -> None:
        """Test extracting verdict from 'ready for implementation' phrasing."""
        output = """
After reviewing the issue, it is ready for implementation.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

    def test_phrasing_should_be_closed(self) -> None:
        """Test extracting verdict from 'should be closed' phrasing."""
        output = """
This issue should be closed as the feature already exists.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CLOSE"
        assert result["should_close"] is True

    def test_phrasing_needs_more_work(self) -> None:
        """Test extracting verdict from 'needs more work' phrasing."""
        output = """
This issue needs more work before implementation can proceed.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

    def test_phrasing_not_ready(self) -> None:
        """Test extracting verdict from 'not ready' phrasing without 'for'."""
        output = """
The issue is not ready for various reasons.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

    def test_phrasing_issue_not_ready(self) -> None:
        """Test extracting verdict from 'issue not ready' phrasing."""
        output = """
After review, this issue not ready due to missing details.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

    def test_phrasing_corrections_made(self) -> None:
        """Test extracting verdict from 'corrections made' phrasing."""
        output = """
Corrections made to the issue file. Line numbers updated.
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "CORRECTED"
        assert result["is_ready"] is True

    def test_double_space_after_hashes(self) -> None:
        """Test parsing when there are multiple spaces after hashes."""
        output = """
##  VERDICT
READY
"""
        result = parse_ready_issue_output(output)

        assert result["verdict"] == "READY"
        assert result["is_ready"] is True


class TestParseManageIssueOutput:
    """Tests for parse_manage_issue_output function."""

    def test_completed_status(self) -> None:
        """Test parsing COMPLETED status."""
        output = """
## RESULT
Status: COMPLETED

Implementation successful.
"""
        result = parse_manage_issue_output(output)

        assert result["status"] == "COMPLETED"

    def test_failed_status(self) -> None:
        """Test parsing FAILED status."""
        output = """
## RESULT
Status: FAILED

Tests are failing.
"""
        result = parse_manage_issue_output(output)

        assert result["status"] == "FAILED"

    def test_files_changed(self) -> None:
        """Test parsing FILES_CHANGED section."""
        output = """
## FILES_CHANGED
- src/main.py
- src/utils.py
- tests/test_main.py

## RESULT
Status: COMPLETED
"""
        result = parse_manage_issue_output(output)

        assert len(result["files_changed"]) == 3
        assert "src/main.py" in result["files_changed"]
        assert "tests/test_main.py" in result["files_changed"]

    def test_files_created(self) -> None:
        """Test parsing FILES_CREATED section."""
        output = """
## FILES_CREATED
- src/new_module.py
- tests/test_new_module.py

## RESULT
Status: COMPLETED
"""
        result = parse_manage_issue_output(output)

        assert len(result["files_created"]) == 2
        assert "src/new_module.py" in result["files_created"]

    def test_commits(self) -> None:
        """Test parsing COMMITS section."""
        output = """
## COMMITS
- abc1234: fix: resolve crash on startup
- def5678: test: add unit tests

## RESULT
Status: COMPLETED
"""
        result = parse_manage_issue_output(output)

        assert len(result["commits"]) == 2
        assert "abc1234" in result["commits"][0]

    def test_verification(self) -> None:
        """Test parsing VERIFICATION section."""
        output = """
## VERIFICATION
- tests: PASS
- lint: PASS
- types: FAIL

## RESULT
Status: BLOCKED
"""
        result = parse_manage_issue_output(output)

        assert result["verification"]["tests"] == "PASS"
        assert result["verification"]["lint"] == "PASS"
        assert result["verification"]["types"] == "FAIL"

    def test_ooda_impact(self) -> None:
        """Test parsing OODA_IMPACT section."""
        output = """
## OODA_IMPACT
- observe: HIGH
- orient: MEDIUM
- decide: LOW
- act: HIGH

## RESULT
Status: COMPLETED
"""
        result = parse_manage_issue_output(output)

        assert result["ooda_impact"]["observe"] == "HIGH"
        assert result["ooda_impact"]["orient"] == "MEDIUM"
        assert result["ooda_impact"]["decide"] == "LOW"
        assert result["ooda_impact"]["act"] == "HIGH"

    def test_none_values_filtered(self) -> None:
        """Test that '- None' entries are filtered out."""
        output = """
## FILES_CHANGED
- None

## FILES_CREATED
- None

## RESULT
Status: COMPLETED
"""
        result = parse_manage_issue_output(output)

        assert result["files_changed"] == []
        assert result["files_created"] == []

    def test_unknown_status(self) -> None:
        """Test output without recognizable status."""
        output = "Some output without a RESULT section."
        result = parse_manage_issue_output(output)

        assert result["status"] == "UNKNOWN"

    def test_full_output(self) -> None:
        """Test parsing complete manage_issue output."""
        output = """
## METADATA
Issue: BUG-001
Type: bug
Action: fix

## PLAN
1. Identify root cause
2. Implement fix
3. Add tests

## FILES_CHANGED
- src/database.py
- src/models.py

## FILES_CREATED
- tests/test_database.py

## COMMITS
- abc1234: fix(db): resolve connection leak

## VERIFICATION
- tests: PASS
- lint: PASS
- types: PASS

## OODA_IMPACT
- observe: HIGH
- act: HIGH

## RESULT
Status: COMPLETED

Issue resolved successfully.
"""
        result = parse_manage_issue_output(output)

        assert result["status"] == "COMPLETED"
        assert len(result["files_changed"]) == 2
        assert len(result["files_created"]) == 1
        assert len(result["commits"]) == 1
        assert result["verification"]["tests"] == "PASS"
        assert "sections" in result
        assert "METADATA" in result["sections"]
        assert "PLAN" in result["sections"]
