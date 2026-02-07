# ENH-267: CLI Link Checker for Documentation - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-267-cli-link-checker-for-documentation.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The project currently has **no automated link checking** for documentation. Quality checks are performed manually through:

1. **CLI-based documentation verification**: `ll-verify-docs` (scripts/little_loops/doc_counts.py:110-157) - verifies numerical counts only, NOT links
2. **Manual documentation audit**: `/ll:audit_docs` command (commands/audit_docs.md) - mentions link checking but performs it manually
3. **No GitHub Actions workflows**: The `.github/workflows/` directory does not exist
4. **No pre-commit hooks**: `.pre-commit-config.yaml` does not exist

### Key Discoveries
- **scripts/little_loops/doc_counts.py** - Pattern for CLI verification tools with argparse, multiple output formats, exit codes
- **scripts/little_loops/cli.py:2250-2337** - CLI entry point pattern (`main_verify_docs()`)
- **scripts/pyproject.toml:47-56** - CLI tool registration via `[project.scripts]`
- **scripts/little_loops/parallel/file_hints.py:15-18** - File path regex pattern that filters URLs
- **scripts/little_loops/logger.py** - Logger class for consistent colored output
- **scripts/tests/test_doc_counts.py** - Test patterns using pytest with tmp_path fixtures

### Current Documentation Files
- README.md, CONTRIBUTING.md (root level)
- docs/ARCHITECTURE.md, docs/API.md, docs/COMMANDS.md, docs/TESTING.md, docs/TROUBLESHOOTING.md, docs/INDEX.md, docs/E2E_TESTING.md, docs/CLI-TOOLS-AUDIT.md, docs/SESSION_HANDOFF.md, docs/demo-repo-rubric.md, docs/generalized-fsm-loop.md, docs/claude-cli-integration-mechanics.md

### Patterns to Follow
- **CLI Structure**: argparse with `--format`, `--json`, `--directory` options, return exit codes 0/1/2
- **File Processing**: Use `Path.rglob()` for recursive markdown scanning
- **Output Formatting**: Three-format pattern (text, JSON, markdown) with separate formatter functions
- **Result Tracking**: Use dataclasses with `@dataclass` for results
- **Testing**: pytest with tmp_path fixtures, separate test classes for unit/integration tests

## Desired End State

1. **CLI command `ll-check-links`** that scans markdown files for broken links
2. **GitHub Actions workflow** `.github/workflows/docs-link-check.yml` for automated checking
3. **Configuration file** `.mlc.config.json` for link checker settings

### How to Verify
- Run `ll-check-links` and see broken links reported
- Run `ll-check-links --json` for machine-readable output
- Run tests via `pytest scripts/tests/test_link_checker.py`
- GitHub Actions workflow runs on PR/push to markdown files

## What We're NOT Doing

- Not adding pre-commit hooks - the issue mentions this but the project doesn't use git pre-commit hooks (uses Claude Code plugin hooks instead)
- Not using external link checker libraries - implementing pure Python solution for consistency with existing tools
- Not creating `.github/` directory structure beyond the single workflow file needed
- Not adding link checking to `/ll:audit_docs` command - that's a separate enhancement

## Problem Analysis

ENH-267 was created by `/ll:audit_docs` which manually checked links and found:
- No automated detection of broken links
- No pre-commit hook for link validation
- No CI job to catch broken links in PRs

The issue proposes GitHub Actions with `gaurav-nelson/github-action-markdown-check@v1`, but research shows:
1. The project has no existing CI/CD infrastructure
2. All quality checks are local CLI commands
3. A native Python CLI tool following existing patterns would be more consistent

## Solution Approach

**Primary**: Create a native Python CLI tool `ll-check-links` following the established patterns from `ll-verify-docs`

**Secondary**: Add GitHub Actions workflow that can be used when CI/CD is adopted

### Design Decisions

1. **Pure Python implementation** - Uses existing patterns and utilities, no external dependencies
2. **Multiple output formats** - text (default), JSON for automation, markdown for reports
3. **Configurable ignore patterns** - `.mlc.config.json` as proposed in the issue
4. **Exit codes** - 0 (all links valid), 1 (broken links found), 2 (error occurred)

## Implementation Phases

### Phase 1: Create Link Checker Module

#### Overview
Create the core link checking module with URL extraction and validation logic.

#### Changes Required

**File**: `scripts/little_loops/link_checker.py` (NEW)
**Changes**: Create new module with:
- `LinkResult` dataclass for individual link results
- `LinkCheckResult` dataclass for overall results
- `extract_links_from_markdown()` function
- `check_url()` function with timeout and retry
- `check_markdown_links()` main function
- Formatter functions (text, JSON, markdown)
- Ignore pattern loading from config

```python
# Key patterns to follow from doc_counts.py
@dataclass
class LinkResult:
    """Result of checking a single link."""
    url: str
    file: str
    line: int
    status: str  # "valid", "broken", "timeout", "ignored"
    error: str | None = None

@dataclass
class LinkCheckResult:
    """Overall results from link checking."""
    total_links: int = 0
    valid_links: int = 0
    broken_links: int = 0
    ignored_links: int = 0
    results: list[LinkResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return self.broken_links > 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_link_checker.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/link_checker.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/link_checker.py`

---

### Phase 2: Add CLI Entry Point

#### Overview
Add CLI command entry point following the pattern from `main_verify_docs()`.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add `main_check_links()` function at end of file (around line 2337+)

```python
def main_check_links() -> int:
    """Entry point for ll-check-links command.

    Check markdown documentation for broken links.

    Returns:
        Exit code (0 = all links valid, 1 = broken links found, 2 = error)
    """
    from little_loops.link_checker import (
        check_markdown_links,
        format_result_json,
        format_result_markdown,
        format_result_text,
        load_ignore_patterns,
    )

    parser = argparse.ArgumentParser(
        prog="ll-check-links",
        description="Check markdown documentation for broken links",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check all markdown files
  %(prog)s --json             # Output as JSON
  %(prog)s --format markdown  # Markdown report
  %(prog)s docs/              # Check specific directory
  %(prog)s --ignore 'http://localhost.*'  # Ignore pattern

Exit codes:
  0 - All links valid
  1 - Broken links found
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
        "-C",
        "--directory",
        type=Path,
        default=None,
        help="Base directory (default: current directory)",
    )

    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Ignore URL patterns (can be used multiple times)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)",
    )

    args = parser.parse_args()

    # Determine base directory
    base_dir = args.directory or Path.cwd()

    # Load ignore patterns from config + CLI args
    ignore_patterns = load_ignore_patterns(base_dir)
    ignore_patterns.extend(args.ignore)

    # Run link check
    result = check_markdown_links(base_dir, ignore_patterns, args.timeout)

    # Format output
    if args.json or args.format == "json":
        output = format_result_json(result)
    elif args.format == "markdown":
        output = format_result_markdown(result)
    else:
        output = format_result_text(result)

    print(output)

    # Return exit code based on results
    if result.has_errors:
        return 1
    return 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v -k "cli or link" --tb=short`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] CLI command works: `ll-check-links --help`

**Manual Verification**:
- [ ] Run `ll-check-links` and see output format
- [ ] Run `ll-check-links --json` and verify JSON output
- [ ] Run `ll-check-links docs/` and verify directory filtering

---

### Phase 3: Register CLI Command

#### Overview
Register the new CLI command in pyproject.toml.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Changes**: Add entry point to `[project.scripts]` section (around line 56)

```toml
[project.scripts]
# ... existing entries ...
ll-verify-docs = "little_loops.cli:main_verify_docs"
ll-check-links = "little_loops.cli:main_check_links"
```

#### Success Criteria

**Automated Verification**:
- [ ] Command is available: `ll-check-links --help`
- [ ] No errors running: `ll-check-links docs/`

---

### Phase 4: Create GitHub Actions Workflow

#### Overview
Create GitHub Actions workflow for automated link checking (optional but recommended).

#### Changes Required

**File**: `.github/workflows/docs-link-check.yml` (NEW)
**Changes**: Create new workflow file

```yaml
name: Documentation Link Check

on:
  pull_request:
    paths:
      - '**.md'
  push:
    paths:
      - '**.md'
  workflow_dispatch:

jobs:
  link-check:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install little-loops
        run: pip install -e "./scripts[dev]"

      - name: Check documentation links
        run: ll-check-links --format markdown
```

#### Success Criteria

**Manual Verification**:
- [ ] File exists at `.github/workflows/docs-link-check.yml`
- [ ] YAML is valid (can be parsed)
- [ ] Workflow runs correctly in GitHub Actions (when PR is created)

---

### Phase 5: Create Link Checker Configuration

#### Overview
Create configuration file for ignore patterns.

#### Changes Required

**File**: `.mlc.config.json` (NEW at root)
**Changes**: Create configuration file

```json
{
  "ignorePatterns": [
    {"pattern": "^http://localhost"},
    {"pattern": "^https://github.com/BrennonTWilliams/little-loops/.*$"}
  ],
  "timeout": "10s",
  "retryOn429": true,
  "retryCount": 3,
  "fallbackRetryDelay": "5s"
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Configuration file is valid JSON
- [ ] Ignore patterns are loaded correctly by link_checker.py

---

### Phase 6: Create Tests

#### Overview
Create comprehensive tests for the link checker module.

#### Changes Required

**File**: `scripts/tests/test_link_checker.py` (NEW)
**Changes**: Create test file following patterns from test_doc_counts.py

```python
"""Tests for link_checker module."""

import pytest
from pathlib import Path
from little_loops.link_checker import (
    LinkResult,
    LinkCheckResult,
    extract_links_from_markdown,
    check_markdown_links,
    format_result_text,
    format_result_json,
    format_result_markdown,
    load_ignore_patterns,
)

class TestExtractLinks:
    """Tests for extract_links_from_markdown function."""

    def test_extract_markdown_links(self, tmp_path: Path) -> None:
        """Extract standard markdown links [text](url)."""
        # Implementation...

    def test_extract_bare_urls(self, tmp_path: Path) -> None:
        """Extract bare URLs in text."""

    def test_ignore_localhost(self, tmp_path: Path) -> None:
        """Ignore localhost URLs."""

class TestCheckMarkdownLinks:
    """Integration tests for check_markdown_links function."""

    def test_all_links_valid(self, tmp_path: Path) -> None:
        """All links are valid."""

    def test_broken_link_detected(self, tmp_path: Path) -> None:
        """Broken links are detected."""

    def test_ignore_patterns_work(self, tmp_path: Path) -> None:
        """Ignore patterns filter correctly."""

class TestFormatters:
    """Tests for output formatters."""

    def test_format_result_text(self) -> None:
        """Text format output."""

    def test_format_result_json(self) -> None:
        """JSON format output."""

    def test_format_result_markdown(self) -> None:
        """Markdown format output."""
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_link_checker.py -v`
- [ ] Coverage check: `python -m pytest scripts/tests/test_link_checker.py --cov=little_loops.link_checker --cov-report=term-missing`

---

## Testing Strategy

### Unit Tests
- URL extraction from markdown content
- Link validation with mock HTTP responses
- Ignore pattern matching
- Output formatting

### Integration Tests
- Full directory scanning
- Multiple file types
- Mixed valid/broken links
- Configuration file loading

### Edge Cases
- Empty markdown files
- Files with no links
- Network timeout handling
- Invalid URL formats

## References

- Original issue: `.issues/enhancements/P4-ENH-267-cli-link-checker-for-documentation.md`
- CLI pattern: `scripts/little_loops/cli.py:2250-2337` (main_verify_docs)
- Doc counts module: `scripts/little_loops/doc_counts.py:1-306`
- Test patterns: `scripts/tests/test_doc_counts.py:1-463`
- Logger utility: `scripts/little_loops/logger.py:1-104`
- Entry point registration: `scripts/pyproject.toml:47-56`
