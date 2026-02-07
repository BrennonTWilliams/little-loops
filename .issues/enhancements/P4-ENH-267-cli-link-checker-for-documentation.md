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
