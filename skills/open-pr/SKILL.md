---
description: |
  Open a pull request for the current branch. Gathers branch info, generates title and body, auto-links issues, and creates the PR via `gh pr create`.

  Trigger keywords: "open pr", "create pull request", "submit pr", "create pr", "open pull request", "submit for review", "make a pr"
---

# Open PR Skill

This skill detects when users want to open a pull request and invokes the `/ll:open_pr` command.

## When to Activate

Proactively offer or invoke this skill when the user:
- Wants to open or create a pull request
- Says things like "let's submit this for review" or "open a PR"
- Has finished implementing and committing changes and wants to share their work
- Asks to push their branch and create a PR

## How to Use

When this skill activates, invoke the command:

```
/ll:open_pr [target_branch] [--draft]
```

### Examples

| User Says | Action |
|-----------|--------|
| "Open a PR" | `/ll:open_pr` |
| "Create a draft PR" | `/ll:open_pr --draft` |
| "Submit this for review against develop" | `/ll:open_pr develop` |
| "Let's open a draft PR to main" | `/ll:open_pr main --draft` |
| "Create a pull request" | `/ll:open_pr` |

## Prerequisites

**GitHub CLI** (`gh`) must be installed and authenticated:
```bash
gh auth status
```

## Integration

Works well with:
- `/ll:commit` - Commit changes before opening a PR
- `/ll:check_code` - Ensure code quality before opening a PR
- `/ll:run_tests` - Verify tests pass before opening a PR
- `/ll:describe_pr` - For more detailed PR description with template support
