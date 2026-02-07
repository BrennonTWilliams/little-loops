# ENH-265: Automated Documentation Count Verification - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-265-automated-documentation-count-verification.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The project has recurring documentation count drift issues. Hard-coded counts for commands (34), agents (8), and skills (6) appear across multiple documentation files with different formatting styles. Over 7 completed issues (BUG-014, BUG-083, BUG-098, BUG-148, BUG-153, BUG-155, BUG-161, BUG-162) relate to count discrepancies, indicating this is a systemic problem.

### Key Discoveries
- **README.md:25-27, 593**: Contains command count in overview and directory structure
- **ARCHITECTURE.md:24, 64**: Mermaid diagram and directory structure with command count
- **CONTRIBUTING.md:113, 123**: Directory structure with agent and skill counts
- **No CI/CD exists**: No `.github/workflows/` directory for automated verification
- **Pattern found**: CLI tools use `argparse` with entry points in `pyproject.toml` (scripts/little_loops/cli.py:1969-2100)
- **Pattern found**: File counting uses `Path.glob()` pattern matching (scripts/little_loops/issue_history.py:981-1003)

### Current Count Formats
Three different inline formats across documentation:
1. README style: `# 34 commands)` - count in parentheses
2. ARCHITECTURE style: `34 slash command templates` - count before category
3. CONTRIBUTING style: `8 agent definitions (*.md)` - count before category with extension

## Desired End State

A CLI tool `ll-verify-docs` that:
1. Counts actual files in `commands/`, `agents/`, `skills/`
2. Validates counts against documentation files
3. Reports mismatches with file:line references
4. Provides `--fix` flag to auto-update counts
5. Returns exit code 1 if mismatches found (for CI use)
6. Outputs structured results (text, JSON, or Markdown)

### How to Verify
- Run `ll-verify-docs` - should verify current counts are accurate
- Add a command: `ll-verify-docs --check` - returns exit code for CI
- Manually add a command file and run `ll-verify-docs` - should detect mismatch
- Run `ll-verify-docs --fix` - should update counts in all documentation files

## What We're NOT Doing

- Not creating GitHub Actions CI/CD pipeline (no `.github/workflows/` exists, would be separate issue)
- Not changing the documentation count formats to be consistent (that's a separate documentation cleanup issue)
- Not adding counts to other documentation files outside scope
- Not creating automated hooks (would be separate enhancement)

## Problem Analysis

Root causes:
1. **Manual updates**: Counts are hard-coded integers that developers must remember to update
2. **Multiple locations**: Same counts appear in 3 files with 3 different formats
3. **No verification**: No automated check prevents drift before commit
4. **Recurring issues**: Historical pattern of 7+ count drift bugs indicates systemic problem

The solution should provide:
- Easy verification command developers can run
- Automated detection of mismatches
- Optional auto-fix to reduce manual work
- Exit code for potential future CI integration

## Solution Approach

Create a Python CLI tool `ll-verify-docs` that follows the established pattern of other `ll-*` tools:

1. **Count discovery**: Use `Path.glob()` to count files in each directory
2. **Regex extraction**: Extract existing counts from documentation files using multiple patterns
3. **Validation**: Compare actual vs documented counts
4. **Reporting**: Output results in multiple formats (text/JSON/Markdown)
5. **Auto-fix**: Use regex substitution to update counts when `--fix` flag provided

The tool will be added to the existing Python package structure with:
- Main module: `scripts/little_loops/doc_counts.py`
- CLI entry point: `scripts/little_loops/cli.py` function `main_verify_docs()`
- Tests: `scripts/tests/test_doc_counts.py`

## Implementation Phases

### Phase 1: Create Core Count Verification Module

#### Overview
Create the core module that counts files and validates against documentation.

#### Changes Required

**File**: `scripts/little_loops/doc_counts.py` [CREATED]
**Changes**: New module with count verification logic

```python
"""Documentation count verification utilities.

Provides automated verification that documented counts (commands, agents, skills)
match actual file counts in the codebase.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# Documentation files to check
DOC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/ARCHITECTURE.md",
]

# Directories to count
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "SKILL.md"),
}


@dataclass
class CountResult:
    """Result of counting files in a directory."""

    category: str
    actual: int
    documented: int | None = None
    file: str | None = None
    line: int | None = None
    matches: bool = True


@dataclass
class VerificationResult:
    """Overall verification result."""

    total_checked: int
    mismatches: list[CountResult] = field(default_factory=list)
    all_match: bool = True

    def add_result(self, result: CountResult) -> None:
        """Add a result and track mismatches."""
        if not result.matches:
            self.mismatches.append(result)
            self.all_match = False


def count_files(directory: str, pattern: str, base_dir: Path = Path.cwd()) -> int:
    """Count files matching pattern in directory.

    Args:
        directory: Directory name relative to base_dir
        pattern: Glob pattern (e.g., "*.md" or "SKILL.md")
        base_dir: Base directory path

    Returns:
        Number of matching files
    """
    dir_path = base_dir / directory
    if not dir_path.exists():
        return 0

    return len(list(dir_path.glob(pattern)))


def extract_count_from_line(line: str, category: str) -> int | None:
    """Extract count from a documentation line.

    Handles multiple formats:
    - "34 commands" or "34 slash commands"
    - "8 agents" or "8 specialized agents"
    - "6 skills" or "6 skill definitions"

    Args:
        line: Line text to search
        category: Category name (commands, agents, skills)

    Returns:
        Extracted count or None if not found
    """
    # Pattern matches: number followed by category name (with optional words)
    # Examples: "34 commands", "8 specialized agents", "6 skill definitions"
    pattern = rf"(\d+)\s+\w*\s*{category}"
    match = re.search(pattern, line, re.IGNORECASE)
    return int(match.group(1)) if match else None


def verify_documentation(
    base_dir: Path = Path.cwd(),
) -> VerificationResult:
    """Verify all documented counts against actual file counts.

    Args:
        base_dir: Base directory path

    Returns:
        VerificationResult with all results
    """
    result = VerificationResult(total_checked=0)

    # Get actual counts
    actual_counts: dict[str, int] = {}
    for category, (directory, pattern) in COUNT_TARGETS.items():
        actual_counts[category] = count_files(directory, pattern, base_dir)

    # Check each documentation file
    for doc_file in DOC_FILES:
        doc_path = base_dir / doc_file
        if not doc_path.exists():
            continue

        content = doc_path.read_text()
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            for category in COUNT_TARGETS:
                documented = extract_count_from_line(line, category)
                if documented is not None:
                    actual = actual_counts[category]
                    matches = documented == actual

                    count_result = CountResult(
                        category=category,
                        actual=actual,
                        documented=documented,
                        file=str(doc_file),
                        line=line_num,
                        matches=matches,
                    )
                    result.add_result(count_result)
                    result.total_checked += 1

    return result
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_doc_counts.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/doc_counts.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/doc_counts.py`

**Manual Verification**:
- [ ] Run `python -c "from little_loops.doc_counts import verify_documentation; print(verify_documentation())"` and verify it returns expected results
- [ ] Add a temporary file to `commands/` and verify it detects mismatch

---

### Phase 2: Create CLI Entry Point

#### Overview
Add the CLI command interface following established patterns.

#### Changes Required

**File**: `scripts/little_loops/cli.py` [MODIFIED]
**Changes**: Add `main_verify_docs()` function

```python
def main_verify_docs() -> int:
    """Entry point for ll-verify-docs command.

    Verify that documented counts (commands, agents, skills) match actual file counts.

    Returns:
        Exit code (0 = all match, 1 = mismatches found)
    """
    import argparse

    from little_loops.doc_counts import (
        format_result_json,
        format_result_markdown,
        format_result_text,
        verify_documentation,
    )

    parser = argparse.ArgumentParser(
        prog="ll-verify-docs",
        description="Verify documented counts match actual file counts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check and show results
  %(prog)s --json             # Output as JSON
  %(prog)s --format markdown  # Markdown report
  %(prog)s --fix              # Auto-fix mismatches

Exit codes:
  0 - All counts match
  1 - Mismatches found
  2 - Error occurred
""",
    )

    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix count mismatches in documentation files",
    )

    parser.add_argument(
        "-C",
        --directory",
        type=Path,
        default=None,
        help="Base directory (default: current directory)",
    )

    args = parser.parse_args()

    # Determine base directory
    base_dir = args.directory or Path.cwd()

    # Run verification
    result = verify_documentation(base_dir)

    # Format output
    if args.json or args.format == "json":
        output = format_result_json(result)
    elif args.format == "markdown":
        output = format_result_markdown(result)
    else:
        output = format_result_text(result)

    print(output)

    # Auto-fix if requested
    if args.fix and not result.all_match:
        from little_loops.doc_counts import fix_counts

        fix_result = fix_counts(base_dir, result)
        print(f"\nFixed {fix_result.fixed_count} count(s) in {fix_result.files_modified} file(s)")

    # Return exit code based on results
    return 0 if result.all_match else 1
```

**File**: `scripts/pyproject.toml` [MODIFIED]
**Changes**: Add CLI entry point

```toml
[project.scripts]
# ... existing entries ...
ll-verify-docs = "little_loops.cli:main_verify_docs"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -k verify_docs -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] Command exists: `ll-verify-docs --help` shows help text

**Manual Verification**:
- [ ] Run `ll-verify-docs` and verify text output format is readable
- [ ] Run `ll-verify-docs --json` and verify JSON is valid
- [ ] Run `ll-verify-docs --format markdown` and verify markdown formatting

---

### Phase 3: Add Output Formatting Functions

#### Overview
Add formatting functions for different output types.

#### Changes Required

**File**: `scripts/little_loops/doc_counts.py` [MODIFIED]
**Changes**: Add formatting functions

```python
@dataclass
class FixResult:
    """Result of fixing counts."""

    fixed_count: int
    files_modified: list[str]


def format_result_text(result: VerificationResult) -> str:
    """Format verification result as text.

    Args:
        result: Verification result

    Returns:
        Formatted text output
    """
    lines = ["Documentation Count Verification", "=" * 40]

    if result.all_match:
        lines.append(f"✓ All {result.total_checked} count(s) match!")
    else:
        lines.append(f"✗ Found {len(result.mismatches)} mismatch(es):")
        lines.append("")

        for mismatch in result.mismatches:
            lines.append(
                f"  {mismatch.category}: "
                f"documented={mismatch.documented}, "
                f"actual={mismatch.actual}"
            )
            lines.append(f"    at {mismatch.file}:{mismatch.line}")

    return "\n".join(lines)


def format_result_json(result: VerificationResult) -> str:
    """Format verification result as JSON.

    Args:
        result: Verification result

    Returns:
        JSON string
    """
    import json

    data = {
        "all_match": result.all_match,
        "total_checked": result.total_checked,
        "mismatches": [
            {
                "category": m.category,
                "documented": m.documented,
                "actual": m.actual,
                "file": m.file,
                "line": m.line,
            }
            for m in result.mismatches
        ],
    }

    return json.dumps(data, indent=2)


def format_result_markdown(result: VerificationResult) -> str:
    """Format verification result as Markdown.

    Args:
        result: Verification result

    Returns:
        Markdown formatted string
    """
    lines = ["# Documentation Count Verification", ""]

    if result.all_match:
        lines.append("## ✅ All Counts Match")
        lines.append(f"\nAll {result.total_checked} documented count(s) are accurate.")
    else:
        lines.append("## ❌ Mismatches Found")
        lines.append("")
        lines.append("| Category | Documented | Actual | Location |")
        lines.append("|----------|-----------|--------|----------|")

        for mismatch in result.mismatches:
            lines.append(
                f"| {mismatch.category} | {mismatch.documented} | "
                f"{mismatch.actual} | `{mismatch.file}:{mismatch.line}` |"
            )

    return "\n".join(lines)


def fix_counts(
    base_dir: Path, result: VerificationResult
) -> FixResult:
    """Fix count mismatches in documentation files.

    Args:
        base_dir: Base directory path
        result: Verification result with mismatches

    Returns:
        FixResult with counts of fixes made
    """
    files_modified: set[str] = set()
    fixed_count = 0

    # Group mismatches by file
    mismatches_by_file: dict[str, list[CountResult]] = {}
    for mismatch in result.mismatches:
        if mismatch.file:
            mismatches_by_file.setdefault(mismatch.file, []).append(mismatch)

    # Fix each file
    for file_path, mismatches in mismatches_by_file.items():
        doc_path = base_dir / file_path
        content = doc_path.read_text()
        lines = content.splitlines()

        for mismatch in mismatches:
            if mismatch.line is not None and 1 <= mismatch.line <= len(lines):
                line = lines[mismatch.line - 1]

                # Replace the count while preserving the rest of the line
                # Pattern: find the number and replace with actual count
                new_line = re.sub(
                    rf"(\d+)(\s+\w*\s*{mismatch.category})",
                    f"{mismatch.actual}\\2",
                    line,
                    count=1,  # Only replace first occurrence
                    flags=re.IGNORECASE,
                )

                if new_line != line:
                    lines[mismatch.line - 1] = new_line
                    fixed_count += 1
                    files_modified.add(file_path)

        # Write back if changes were made
        if file_path in files_modified:
            doc_path.write_text("\n".join(lines))

    return FixResult(
        fixed_count=fixed_count,
        files_modified=list(files_modified),
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_doc_counts.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/doc_counts.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/doc_counts.py`

**Manual Verification**:
- [ ] Run `ll-verify-docs --json` and pipe to `jq .` to verify valid JSON
- [ ] Run `ll-verify-docs --format markdown` and verify markdown table format

---

### Phase 4: Add Tests

#### Overview
Create comprehensive tests for the verification module.

#### Changes Required

**File**: `scripts/tests/test_doc_counts.py` [CREATED]
**Changes**: New test file

```python
"""Tests for documentation count verification."""

from pathlib import Path

import pytest

from little_loops.doc_counts import (
    CountResult,
    VerificationResult,
    count_files,
    extract_count_from_line,
    fix_counts,
    format_result_json,
    format_result_markdown,
    format_result_text,
    verify_documentation,
)


class TestCountFiles:
    """Tests for count_files function."""

    def test_count_commands(self, tmp_path: Path) -> None:
        """Count command markdown files."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("# Command 1")
        (commands_dir / "cmd2.md").write_text("# Command 2")

        count = count_files("commands", "*.md", tmp_path)
        assert count == 2

    def test_count_skills_with_subdirs(self, tmp_path: Path) -> None:
        """Count skill files in subdirectories."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "skill1" / "SKILL.md").parent.mkdir(parents=True)
        (skills_dir / "skill1" / "SKILL.md").write_text("# Skill 1")

        count = count_files("skills", "SKILL.md", tmp_path)
        assert count == 1

    def test_count_nonexistent_directory(self, tmp_path: Path) -> None:
        """Return 0 for nonexistent directory."""
        count = count_files("nonexistent", "*.md", tmp_path)
        assert count == 0


class TestExtractCountFromLine:
    """Tests for extract_count_from_line function."""

    def test_extract_simple_count(self) -> None:
        """Extract simple '34 commands' pattern."""
        count = extract_count_from_line("34 commands", "commands")
        assert count == 34

    def test_extract_with_adjective(self) -> None:
        """Extract '34 slash commands' pattern."""
        count = extract_count_from_line("34 slash commands", "commands")
        assert count == 34

    def test_extract_agents(self) -> None:
        """Extract '8 specialized agents' pattern."""
        count = extract_count_from_line("8 specialized agents", "agents")
        assert count == 8

    def test_extract_skills(self) -> None:
        """Extract '6 skill definitions' pattern."""
        count = extract_count_from_line("6 skill definitions", "skills")
        assert count == 6

    def test_no_match_returns_none(self) -> None:
        """Return None when pattern doesn't match."""
        count = extract_count_from_line("no numbers here", "commands")
        assert count is None

    def test_case_insensitive(self) -> None:
        """Match regardless of case."""
        count = extract_count_from_line("34 Commands", "commands")
        assert count == 34


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_add_result_tracks_mismatches(self) -> None:
        """Adding mismatched result updates state."""
        result = VerificationResult(total_checked=0)
        mismatch = CountResult(
            category="commands",
            actual=35,
            documented=34,
            file="README.md",
            line=10,
            matches=False,
        )

        result.add_result(mismatch)

        assert not result.all_match
        assert len(result.mismatches) == 1
        assert result.mismatches[0].category == "commands"

    def test_add_result_matching(self) -> None:
        """Adding matched result doesn't change all_match."""
        result = VerificationResult(total_checked=0)
        match = CountResult(
            category="commands",
            actual=34,
            documented=34,
            file="README.md",
            line=10,
            matches=True,
        )

        result.add_result(match)

        assert result.all_match
        assert len(result.mismatches) == 0


class TestFormatResultText:
    """Tests for format_result_text function."""

    def test_format_all_match(self) -> None:
        """Format when all counts match."""
        result = VerificationResult(total_checked=3, all_match=True)

        output = format_result_text(result)

        assert "All 3 count(s) match" in output
        assert "✓" in output

    def test_format_with_mismatches(self) -> None:
        """Format with mismatched counts."""
        result = VerificationResult(total_checked=3, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_text(result)

        assert "1 mismatch" in output
        assert "commands:" in output
        assert "documented=34, actual=35" in output
        assert "README.md:10" in output


class TestFormatResultJson:
    """Tests for format_result_json function."""

    def test_format_valid_json(self) -> None:
        """Output is valid JSON."""
        import json

        result = VerificationResult(total_checked=2, all_match=True)

        output = format_result_json(result)

        data = json.loads(output)
        assert data["all_match"] is True
        assert data["total_checked"] == 2

    def test_format_includes_mismatches(self) -> None:
        """JSON includes mismatch details."""
        import json

        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_json(result)
        data = json.loads(output)

        assert len(data["mismatches"]) == 1
        assert data["mismatches"][0]["category"] == "commands"
        assert data["mismatches"][0]["actual"] == 35


class TestFormatResultMarkdown:
    """Tests for format_result_markdown function."""

    def test_format_all_match_markdown(self) -> None:
        """Format markdown when all counts match."""
        result = VerificationResult(total_checked=3, all_match=True)

        output = format_result_markdown(result)

        assert "# Documentation Count Verification" in output
        assert "All Counts Match" in output
        assert "✅" in output

    def test_format_with_mismatches_table(self) -> None:
        """Format markdown with mismatches table."""
        result = VerificationResult(total_checked=3, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_markdown(result)

        assert "| Category | Documented | Actual |" in output
        assert "| commands | 34 | 35 |" in output
        assert "`README.md:10`" in output


class TestFixCounts:
    """Tests for fix_counts function."""

    def test_fix_replaces_count(self, tmp_path: Path) -> None:
        """Fix replaces incorrect count with actual."""
        # Create test file with wrong count
        test_file = tmp_path / "README.md"
        test_file.write_text("## 34 commands\n")

        # Create result with mismatch
        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,  # Actual count
                documented=34,  # Documented (wrong)
                file="README.md",
                line=1,
                matches=False,
            )
        )

        # Fix
        fix_result = fix_counts(tmp_path, result)

        # Verify
        assert fix_result.fixed_count == 1
        assert len(fix_result.files_modified) == 1

        updated = test_file.read_text()
        assert "35 commands" in updated
        assert "34 commands" not in updated

    def test_fix_preserves_line_format(self, tmp_path: Path) -> None:
        """Fix preserves surrounding text and format."""
        test_file = tmp_path / "README.md"
        test_file.write_text("- **34 slash commands** for workflows\n")

        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )

        fix_counts(tmp_path, result)

        updated = test_file.read_text()
        assert "- **35 slash commands** for workflows" in updated
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_doc_counts.py -v`
- [ ] Coverage check: `python -m pytest scripts/tests/test_doc_counts.py --cov=little_loops.doc_counts --cov-report=term-missing`

**Manual Verification**:
- [ ] Review test coverage report - aim for >80% coverage
- [ ] Run specific failing test to verify error messages are helpful

---

### Phase 5: Update Documentation

#### Overview
Document the new command in relevant docs.

#### Changes Required

**File**: `docs/API.md` [MODIFIED]
**Changes**: Add doc_counts module reference

```markdown
### doc_counts

Documentation count verification utilities.

::: little_loops.doc_counts
```

**File**: `README.md` [MODIFIED - if appropriate]
**Changes**: May add mention of verification command in Quick Start

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check docs/API.md`
- [ ] Command documented: `ll-verify-docs --help` works

**Manual Verification**:
- [ ] Docs mention the new verification command
- [ ] Run `ll-verify-docs` after docs update to verify no mismatches introduced

---

## Testing Strategy

### Unit Tests
- Test count_files with various directory structures
- Test extract_count_from_line with different line formats
- Test formatting functions for all output types
- Test fix_counts with temporary files

### Integration Tests
- Run `ll-verify-docs` on actual codebase
- Test `--fix` flag creates backup or shows what would change
- Verify exit codes (0 for match, 1 for mismatch)

### Manual Testing
- Add temporary command file, verify detection
- Run `--fix` and verify counts are updated correctly
- Test JSON output parsing

## References

- Original issue: `.issues/enhancements/P4-ENH-265-automated-documentation-count-verification.md`
- CLI pattern: `scripts/little_loops/cli.py:1969-2100`
- Counting pattern: `scripts/little_loops/issue_history.py:981-1003`
- Entry point pattern: `scripts/pyproject.toml:47-55`
- Test patterns: `scripts/tests/test_cli.py`
