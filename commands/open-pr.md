---
description: |
  Open a pull request for the current branch.

  Trigger keywords: "open pr", "create pull request", "submit pr", "create pr", "open pull request", "submit for review", "make a pr"
argument-hint: "[target-branch]"
arguments:
  - name: target_branch
    description: "Target branch for the PR (default: auto-detect from origin/HEAD)"
    required: false
  - name: flags
    description: "Optional flags: --draft (create as draft PR)"
    required: false
allowed-tools:
  - Bash(gh:*, git:*)
---

# Open Pull Request

You are tasked with opening a pull request for the current branch's work.

## Process

### 1. Check Prerequisites

```bash
# Verify gh CLI is authenticated
gh auth status
```

If not authenticated, instruct the user to run `gh auth login` and stop.

```bash
# Verify we're not on the default branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"
```

If the current branch is `main` or `master`, stop and inform the user they need to be on a feature branch.

### 2. Check for Existing PR

```bash
# Check if a PR already exists for this branch
gh pr view --json number,url,state 2>/dev/null
```

If a PR already exists and is open, inform the user and provide the URL. Ask if they want to update it or stop.

### 3. Gather Information

```bash
# Get base branch (auto-detect or use argument)
BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
echo "Base branch: $BASE_BRANCH"

# Get commits on this branch
git log --oneline $BASE_BRANCH..HEAD

# Get changed files summary
git diff --stat $BASE_BRANCH...HEAD
```

If there are no commits ahead of the base branch, stop and inform the user there's nothing to create a PR for.

Use the `target_branch` argument if provided, otherwise use the auto-detected base branch.

### 4. Generate PR Title

Analyze the commits to generate a concise PR title:

- If there's a single commit, use its subject line
- If there are multiple commits, summarize the overall change in one line
- Follow conventional commit style if the repo uses it (check recent merged PRs)
- Keep the title under 70 characters

### 5. Generate PR Body

Review the commits and diff to generate the PR body:

```markdown
## Summary
[1-3 sentences describing what this PR does and why]

## Changes
- [List of specific changes made]
- [Group related changes together]
- [Highlight any breaking changes]

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing performed

## Related Issues
[Auto-detected issue references, if any]
```

### 6. Auto-Link Issues

Check the branch name for issue references:

```bash
# Extract issue ID from branch name (e.g., feat/FEAT-228-description)
echo "$CURRENT_BRANCH" | grep -oE '(BUG|FEAT|ENH)-[0-9]+'
```

If an issue ID is found:
1. Look for the corresponding local issue file in `.issues/`
2. Check if the issue file has a `github_issue` field in its frontmatter
3. If a GitHub issue number exists, add `Closes #NNN` to the PR body
4. If no GitHub issue number, add a reference to the local issue ID in the body

Also scan commit messages for issue references (`#NNN`, `BUG-NNN`, `FEAT-NNN`, `ENH-NNN`).

### 7. Present for Confirmation

Present the PR details to the user using `AskUserQuestion`:

```
PR Preview:
  Title: [generated title]
  Base:  [target branch]
  Head:  [current branch]
  Draft: [yes/no]

Body:
[generated body]
```

Ask the user:
- "Create this PR?" with options:
  - "Yes, create PR" - Proceed with creation
  - "Yes, as draft" - Create as draft PR
  - "Edit first" - Let the user modify title/body before creating

If the user chooses "Edit first", ask what they'd like to change and regenerate.

### 8. Create the PR

```bash
# Ensure branch is pushed to remote
git push -u origin $CURRENT_BRANCH

# Create the PR
gh pr create --title "[PR Title]" --body "$(cat <<'EOF'
[Generated body]
EOF
)" --base $BASE_BRANCH
```

If `--draft` flag was passed or user selected "Yes, as draft", add `--draft` to the command.

### 9. Report Result

After successful creation, output:

```
PR created successfully!

  Number: #[number]
  Title:  [title]
  URL:    [url]
  Status: [Ready for review | Draft]
  Base:   [base branch] <- [current branch]
```

---

## Arguments

$ARGUMENTS

- **target_branch** (optional, default: auto-detect): Target branch for the PR
  - If provided, uses specified branch as the PR base
  - If omitted, auto-detects from `refs/remotes/origin/HEAD` (usually `main` or `master`)

- **flags** (optional):
  - `--draft` - Create the PR as a draft

---

## Examples

```bash
# Open a PR for the current branch
/ll:open-pr

# Open a draft PR
/ll:open-pr --draft

# Open a PR targeting a specific branch
/ll:open-pr develop

# Open a draft PR targeting a specific branch
/ll:open-pr develop --draft
```

---

## Error Handling

- **gh not installed**: Suggest installation via `brew install gh` (macOS) or platform docs
- **gh not authenticated**: Suggest `gh auth login`
- **On default branch**: Inform user to create a feature branch first
- **No commits**: Inform user there are no changes to create a PR for
- **PR already exists**: Show existing PR URL, offer to open in browser
- **Push fails**: Show error and suggest resolving upstream issues

---

## Integration

This command works well with:
- `/ll:commit` - Commit changes before opening a PR
- `/ll:check-code` - Ensure code quality before opening a PR
- `/ll:run-tests` - Verify tests pass before opening a PR
- `/ll:describe-pr` - For more detailed PR description generation with template support
