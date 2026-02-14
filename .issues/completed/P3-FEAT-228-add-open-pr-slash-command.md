---
discovered_date: 2026-02-05
discovered_by: capture_issue
---

# FEAT-228: Add /ll:open-pr slash command

## Summary

Add a new Slash Command `/ll:open-pr` to open a new Pull Request for the current work in the current branch.

## Context

User description: "Add a new Slash Command `/ll:open-pr` to open a new Pull Request for the current work in the current branch"

## Current Behavior

There is no built-in command for opening pull requests. Users must manually construct `gh pr create` commands or use `/ll:describe-pr` to generate a description and then create the PR separately.

## User Story

As a developer using little-loops, I want to open a PR from my current branch so that I can submit my work for review without leaving Claude Code.

## Expected Behavior

A `/ll:open-pr` command that automates opening a pull request for the current branch, including generating an appropriate title, description, and handling the `gh pr create` workflow.

## Acceptance Criteria

- [x] Auto-generate PR title from branch name and/or commit history
- [x] Auto-generate PR body using `/ll:describe-pr` style logic
- [x] Allow specifying target branch (default to main/master)
- [x] Support creating PR as draft via option/flag
- [x] Auto-link PR to related issue if detected from branch name or commit messages
- [x] Use `gh pr create` under the hood and require `gh` CLI to be installed

## Proposed Solution

Create a Skill that wraps `gh pr create`, leveraging the existing `/ll:describe-pr` logic for generating the PR body and commit analysis for the title. This aligns with the project preference for Skills over Agents (per CLAUDE.md).

Key implementation details:
- Reuse `/ll:describe-pr` command logic for body generation
- Analyze commits on current branch vs target branch for title generation
- Pass `--draft` flag to `gh pr create` when draft mode is requested
- Detect issue references from branch naming conventions (e.g., `FEAT-228-description`) and include `Closes #NNN` in the body
- Accept optional arguments for target branch override and draft mode

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

`feature`, `refined`

---

## Status

**Completed** | Created: 2026-02-05 | Completed: 2026-02-05 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-05
- **Status**: Completed

### Changes Made
- `commands/open_pr.md`: New command with full PR creation workflow (prereq checks, branch info gathering, title/body generation, issue auto-linking, user confirmation, gh pr create execution)
- `skills/open-pr/SKILL.md`: New skill with trigger keywords for natural language activation
- `commands/help.md`: Added /ll:open-pr to help output and quick reference table
- `docs/COMMANDS.md`: Added /ll:open-pr to command reference and quick reference table
- `commands/commit.md`: Added /ll:open-pr to integration section
- `commands/describe_pr.md`: Added /ll:open-pr to integration section

### Verification Results
- Tests: PASS (2455 passed)
- Lint: PASS
- Types: PASS
