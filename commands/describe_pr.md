---
description: Generate comprehensive PR descriptions following repository templates
argument-hint: "[base-branch]"
allowed-tools:
  - Read
  - Bash(git:*, gh:*)
arguments:
  - name: base_branch
    description: "Base branch for comparison (default: auto-detect from origin/HEAD)"
    required: false
---

# Describe PR

You are tasked with generating a comprehensive pull request description for the current branch.

## Process

### 1. Gather Information

```bash
# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

# Get base branch (usually main or master)
BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
echo "Base branch: $BASE_BRANCH"

# Get commits on this branch
git log --oneline $BASE_BRANCH..HEAD

# Get changed files
git diff --stat $BASE_BRANCH...HEAD

# Get full diff for context
git diff $BASE_BRANCH...HEAD
```

### 2. Analyze Changes

Review all commits and changes to understand:
- **What** was changed (features, fixes, refactors)
- **Why** the changes were made (motivation, problem solved)
- **How** it was implemented (approach, trade-offs)

### 3. Check for PR Template

```bash
# Look for PR template
if [ -f .github/PULL_REQUEST_TEMPLATE.md ]; then
    cat .github/PULL_REQUEST_TEMPLATE.md
elif [ -f .github/pull_request_template.md ]; then
    cat .github/pull_request_template.md
elif [ -f docs/PULL_REQUEST_TEMPLATE.md ]; then
    cat docs/PULL_REQUEST_TEMPLATE.md
fi
```

### 4. Generate Description

If a template exists, fill it out. Otherwise, use this format:

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
- [Describe any new tests added]

## Screenshots (if applicable)

[Add screenshots for UI changes]

## Related Issues

- Fixes #[issue number]
- Related to #[issue number]

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated (if needed)
- [ ] No new warnings introduced
```

### 5. Output

Present the generated description and ask:
- "Would you like me to create the PR with this description?"
- "Should I modify anything before creating the PR?"

If approved, use:
```bash
gh pr create --title "[PR Title]" --body "$(cat <<'EOF'
[Generated description]
EOF
)"
```

---

## Arguments

$ARGUMENTS

- **base_branch** (optional, default: auto-detect): Base branch for PR comparison
  - If provided, uses specified branch as comparison target
  - If omitted, auto-detects from `refs/remotes/origin/HEAD` (usually `main` or `master`)

---

## Examples

```bash
# Generate PR description for current branch
/ll:describe_pr

# Review the generated description
# Modify if needed
# Create PR when satisfied
```

---

## Integration

This command works well with:
- `/ll:commit` - Commit changes first
- `/ll:open_pr` - Open the PR after generating a description
- `/ll:check_code` - Ensure code quality before PR
- `/ll:run_tests` - Verify tests pass
