---
discovered_commit: c5005eb
discovered_branch: main
discovered_date: 2026-02-06T22:30:00Z
discovered_by: audit_docs
doc_file: docs/
---

# ENH-267: CLI Link Checker for Documentation

## Summary

Documentation issue found by `/ll:audit_docs`. No automated link checking exists to catch broken documentation links before they reach users.

## Location

- **Missing**: CI link checking job
- **Tools**: Could use `markdown-link-check`, `lychee`, or similar

## Current Content

Documentation links are checked manually during audit, but:
- No automated detection of broken links
- No pre-commit hook for link validation
- No CI job to catch broken links in PRs

## Problem

- Broken links can slip through to published documentation
- External links may rot over time
- Manual auditing is time-consuming
- Cross-file references may break during refactoring

## Expected Content

Add link checker to workflow:

```yaml
# .github/workflows/docs-link-check.yml
name: Documentation Link Check

on:
  pull_request:
    paths:
      - '**.md'
  push:
    paths:
      - '**.md'

jobs:
  link-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: gaurav-nelson/github-action-markdown-link-check@v1
        with:
          config-file: '.mlc.config.json'
```

Configuration:
```json
{
  "ignorePatterns": [
    {"pattern": "^http://localhost"},
    {"pattern": "^https://github.com/BrennonTWilliams/little-loops/.*$"}
  ],
  "timeout": "20s",
  "retryOn429": true,
  "retryCount": 5,
  "fallbackRetryDelay": "30s"
}
```

Also add pre-commit hook:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/tdsmith/linkchecker
    rev: 0.1.0
    hooks:
      - id: markdown-link-check
```

## Impact

- **Severity**: Low (documentation quality)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `ci-cd`

---

## Status

**Open** | Created: 2026-02-06 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- **scripts/little_loops/link_checker.py** (NEW): Link checker module with URL extraction, validation, and multiple output formats
- **scripts/little_loops/cli.py**: Added `main_check_links()` CLI entry point function
- **scripts/pyproject.toml**: Registered `ll-check-links` CLI command
- **scripts/tests/test_link_checker.py** (NEW): Comprehensive test coverage (35 tests, all passing)
- **.github/workflows/docs-link-check.yml** (NEW): GitHub Actions workflow for automated link checking
- **.mlc.config.json** (NEW): Link checker configuration with ignore patterns

### CLI Usage
```bash
# Check all markdown files
ll-check-links

# Output as JSON
ll-check-links --json

# Markdown report
ll-check-links --format markdown

# Check specific directory
ll-check-links --directory docs/

# Ignore patterns
ll-check-links --ignore 'http://localhost.*'
```

### Features Implemented
- Native Python implementation (no external dependencies)
- Markdown link extraction `[text](url)` and bare URLs
- HTTP/HTTPS URL validation with configurable timeout
- Internal reference detection (anchors, relative paths)
- Configurable ignore patterns via `.mlc.config.json`
- Multiple output formats: text (default), JSON, markdown
- Proper exit codes: 0 (valid), 1 (broken links), 2 (error)

### Verification Results
- Tests: PASS (35/35)
- Lint: PASS (ruff)
- Types: PASS (mypy)
- CLI: Functional (tested with `ll-check-links --help`)

### Notes
- Pre-commit hook was NOT implemented (project uses Claude Code plugin hooks instead)
- Used native Python implementation following existing patterns from `ll-verify-docs`
- GitHub Actions workflow uses the CLI command instead of external actions
