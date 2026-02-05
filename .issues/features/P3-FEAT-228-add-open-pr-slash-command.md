---
discovered_date: 2026-02-05
discovered_by: capture_issue
---

# FEAT-228: Add /ll:open_pr slash command

## Summary

Add a new Slash Command `/ll:open_pr` to open a new Pull Request for the current work in the current branch.

## Context

User description: "Add a new Slash Command `/ll:open_pr` to open a new Pull Request for the current work in the current branch"

## Current Behavior

There is no built-in command for opening pull requests. Users must manually construct `gh pr create` commands or use `/ll:describe_pr` to generate a description and then create the PR separately.

## Expected Behavior

A `/ll:open_pr` command that automates opening a pull request for the current branch, including generating an appropriate title, description, and handling the `gh pr create` workflow.

## Proposed Solution

TBD - requires investigation

## Impact

- **Priority**: P3
- **Effort**: TBD
- **Risk**: TBD

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Slash command and skill registration |
| guidelines | CONTRIBUTING.md | Development conventions for new commands |

## Labels

`feature`, `captured`

---

## Status

**Open** | Created: 2026-02-05 | Priority: P3
