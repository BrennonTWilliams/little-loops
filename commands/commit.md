---
description: Create git commits with user approval and no Claude attribution
allowed-tools:
  - Bash(git:*)
---

# Commit Changes

You are tasked with creating git commits for the changes made during this session.

### 0. Parse Flags

```bash
AUTO_MODE=false

# Auto-enable in automation contexts
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
```

## Process:

1. **Think about what changed:**
   - Review the conversation history and understand what was accomplished
   - Run `git status` to see current changes
   - Run `git diff` to understand the modifications
   - Consider whether changes should be one commit or multiple logical commits

1.5. **Check for files that should be ignored:**
   - After running `git status`, examine the untracked files
   - Import `suggest_gitignore_patterns` and `add_patterns_to_gitignore` from `little_loops.git_operations`
   - Call `suggest_gitignore_patterns()` to analyze untracked files
   - If suggestions are found (`result.has_suggestions` is True):
     a. Present findings grouped by category:
        ```
        Found {N} untracked file(s) that should typically be ignored:

        {Category}:
        - Pattern: {pattern}
        - Files: {comma-separated list of matched files}
        - Description: {description}
        ```
     b. **Auto mode bypass**: If `AUTO_MODE` is true, skip the `AskUserQuestion` prompt and skip gitignore updates entirely. Proceed directly to step 2.
     c. Use `AskUserQuestion` tool to get user approval (interactive mode only):
        ```yaml
        questions:
          - header: "Gitignore Suggestions"
            question: "Found {TOTAL_FILES} untracked file(s) that should typically be ignored. Add these patterns to .gitignore?"
            options:
              - label: "Yes, add all suggested patterns"
                description: "Add {PATTERN_COUNT} pattern(s) to .gitignore: {PATTERNS_LIST}"
              - label: "No, skip gitignore updates"
                description: "Proceed with commit without updating .gitignore"
            multiSelect: false
        ```
     d. Handle user response:
        - **"Yes, add all"**: Extract pattern strings from `result.patterns`, call `add_patterns_to_gitignore()`, show confirmation
        - **"No, skip"**: Continue with commit workflow
     e. If patterns were added, run `git status` again to show updated state

2. **Plan your commit(s):**
   - Identify which files belong together
   - Draft clear, descriptive commit messages
   - Use imperative mood in commit messages
   - Focus on why the changes were made, not just what

3. **Present your plan to the user:**
   - List the files you plan to add for each commit
   - Show the commit message(s) you'll use
   - Inform the user: "Creating [N] commit(s) with these changes..."

4. **Execute:**
   - Use `git add` with specific files (never use `-A` or `.`)
   - Create commits with your planned messages
   - Show the result with `git log --oneline -n [number]`

## Important:
- **NEVER add co-author information or Claude attribution**
- Commits should be authored solely by the user
- Do not include any "Generated with Claude" messages
- Do not add "Co-Authored-By" lines
- Write commit messages as if the user wrote them

## Remember:
- You have the full context of what was done in this session
- Group related changes together
- Keep commits focused and atomic when possible
- The user trusts your judgment - they asked you to commit

---

## Examples

```bash
# Commit changes from current session
/ll:commit

# Non-interactive commit from automation context
/ll:commit --auto
```

---

## Integration

This command creates commits for work done in the current session.

Works well with:
- `/ll:check-code` - Run before committing to ensure code quality
- `/ll:run-tests` - Verify tests pass before committing
- `/ll:open-pr` - After committing, open a pull request
- `/ll:describe-pr` - After committing, generate PR description
