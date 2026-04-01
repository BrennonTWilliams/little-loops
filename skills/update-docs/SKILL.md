---
description: |
  Use when the user asks to update docs, find stale documentation, check doc coverage after a sprint, or asks "what docs need updating?"

  Trigger keywords: "update docs", "stale docs", "missing docs", "docs since sprint", "doc coverage", "what docs need updating", "documentation gaps", "docs after sprint", "catch up docs"
argument-hint: "[--since <date|git-ref>] [--fix]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Edit
  - Bash(git:*, ll-history:*, ll-issues:*)
arguments:
  - name: since
    description: Change window start — date (YYYY-MM-DD) or git ref (default: last commit touching a doc file)
    required: false
  - name: fix
    description: Draft stub documentation sections inline rather than just reporting gaps
    required: false
---

# Update Docs

You are tasked with identifying documentation that needs to be written or updated by analyzing recent git commits and completed issues since a given date. This skill detects *missing/new* coverage, not incorrect existing content (that's `/ll:audit-docs`).

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Issues base**: `{{config.issues.base_dir}}`

## Process

### 1. Resolve Since Reference

Determine the change window start:

```bash
# Parse --since argument
SINCE_ARG="${since}"

if [ -z "$SINCE_ARG" ]; then
    # Default: last commit touching a doc file
    SINCE_REF=$(git log --oneline -- docs/ README.md CONTRIBUTING.md CHANGELOG.md | head -1 | awk '{print $1}')
    if [ -z "$SINCE_REF" ]; then
        echo "No documentation commits found — using all history"
        SINCE_REF=""
    else
        echo "Using last doc commit: $SINCE_REF"
    fi
else
    SINCE_REF="$SINCE_ARG"
    echo "Using provided ref: $SINCE_REF"
fi
```

Output the resolved since-ref so the user knows the change window being analyzed.

### 2. Collect Changed Source Files

Identify which source files changed since the reference:

```bash
# Get changed files since the ref
if [ -n "$SINCE_REF" ]; then
    # If SINCE_REF looks like a date (YYYY-MM-DD), use --since flag
    if echo "$SINCE_REF" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
        git log --since="$SINCE_REF" --name-only --pretty="" -- {{config.project.src_dir}} | sort -u | grep -v '^$'
    else
        # Treat as git commit hash or ref
        git log "${SINCE_REF}..HEAD" --name-only --pretty="" -- {{config.project.src_dir}} | sort -u | grep -v '^$'
    fi
else
    git log --name-only --pretty="" -- {{config.project.src_dir}} | sort -u | grep -v '^$'
fi
```

Group changed files by module/component (e.g., `scripts/little_loops/cli/`, `scripts/little_loops/issue_history/`).

### 3. Collect Completed Issues

Scan `.issues/completed/` for issues completed after the since-ref:

```bash
# Get completion date of the since-ref (if it's a git hash)
if echo "$SINCE_REF" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    SINCE_DATE="$SINCE_REF"
else
    # Get the commit date for the git ref
    SINCE_DATE=$(git log -1 --format="%cs" "$SINCE_REF" 2>/dev/null || echo "")
fi

# List completed issues modified after since-date
python3 -c "
from little_loops.issue_history.parsing import scan_completed_issues
from pathlib import Path
import sys

issues = scan_completed_issues(Path('.issues/completed'))
since = sys.argv[1] if sys.argv[1:] else ''
for i in sorted(issues, key=lambda x: str(x.completed_date or ''), reverse=True):
    if not since or (i.completed_date and str(i.completed_date) >= since):
        print(f'{i.completed_date or \"unknown\"}\t{i.path.name}\t{i.title or \"\"}')
" "$SINCE_DATE" 2>/dev/null || \
find .issues/completed -name "*.md" -newer ".git/refs/heads/$(git branch --show-current)" | sort
```

### 4. Build Change Inventory

For each changed source file and completed issue, extract what changed and what documentation it would affect:

**For source file changes:**
- Identify the module/CLI tool (e.g., `ll-loop`, `ll-issues`, `issue_history`)
- Check git log for commit messages describing changes:
  ```bash
  git log "${SINCE_REF}..HEAD" --pretty="%s" -- <changed_file>
  ```
- Note what new flags, functions, or behaviors were added

**For completed issues:**
- Read the issue title and summary
- Identify the component/feature area
- Note what user-visible behavior was added or changed

### 5. Cross-Reference Existing Docs

For each change in the inventory, search documentation files for coverage:

```bash
# Find all documentation files
find . -name "*.md" \
    -not -path "./.git/*" \
    -not -path "./.issues/*" \
    -not -path "./node_modules/*" \
    -not -path "./.venv/*" \
    | sort
```

For each changed module/feature:
1. Search doc files for the module name, CLI command, or feature keyword
2. Check if existing coverage mentions the new behavior/flag/feature
3. Flag as a gap if no coverage found, or if coverage predates the change

```bash
# Example: check if '--elide' flag is documented
grep -r "elide\|--elide" docs/ README.md CONTRIBUTING.md 2>/dev/null
```

### 6. Report Gaps

Produce a prioritized gap report using the format defined in [templates.md](templates.md) (see "Gap Report Format" section).

**Prioritization rules:**
- **High**: Completed feature/enhancement with no doc coverage (user-visible behavior undocumented)
- **Medium**: Changed CLI tool or public API with no updated docs
- **Low**: Internal module changes that may affect API docs or troubleshooting guides

Group gaps by source:
1. **From completed issues** — shipped features with no doc coverage
2. **From git changes** — source files changed but no doc update found

### 7. Offer Action

For each gap, offer one of the following actions using the format in [templates.md](templates.md) (see "Action Prompt Format" section):

**If `--fix` flag is set**: Skip prompts. For each gap, draft a stub documentation section inline using the stub template from [templates.md](templates.md) and insert it into the most appropriate doc file.

**Otherwise**: Present the full gap report and ask for each gap:

Use the AskUserQuestion tool with single-select:
- Question: "Documentation gap: [description]"
- Header: "[component/feature]"
- Options:
  - label: "Draft stub"
    description: "Insert a stub section into [target doc file]"
  - label: "Create issue"
    description: "Create a documentation issue to track this gap"
  - label: "Skip"
    description: "Ignore this gap"

#### Draft Stub

For "Draft stub" selections, insert a stub section using the template in [templates.md](templates.md) (see "Stub Section Template" section) into the most appropriate documentation file.

After drafting stubs:
```bash
git add [modified doc files]
```

Output:
```
Stub drafted: [feature/component] in [doc-file:section]
```

#### Create Issue

For "Create issue" selections, create a documentation issue using the template in [templates.md](templates.md) (see "Doc Issue Template" section).

### 8. Watermark (Optional)

After a successful run, optionally record the current HEAD commit as a watermark:

```bash
# Store current HEAD as watermark for next run
CURRENT_HEAD=$(git rev-parse HEAD)
echo "$CURRENT_HEAD" > .ll/ll-update-docs.watermark
echo "Watermark updated: $CURRENT_HEAD"
```

If `.ll/ll-update-docs.watermark` exists and no `--since` was provided, use the watermark as the since-ref instead of the last doc commit.

### 9. Summary Output

```
Update Docs complete:
- Change window: [since-ref] → HEAD
- Source changes analyzed: N files across M modules
- Completed issues analyzed: N issues
- Gaps found: N (H high, M medium, L low)
  - Stub drafted: X
  - Issues created: Y
  - Skipped: Z

Run `/ll:commit` to commit drafted stubs and issue files.
```

---

## Arguments

$ARGUMENTS

- **--since** (optional): Change window start
  - Date: `YYYY-MM-DD` (e.g., `--since=2026-03-01`)
  - Git ref: commit hash or branch name (e.g., `--since=main`, `--since=abc1234`)
  - Default: last commit touching a doc file (or watermark if `.ll/ll-update-docs.watermark` exists)

- **--fix** (optional, flag): Draft stub documentation sections inline rather than prompting per gap. Non-draftable gaps still flow to issue creation.

---

## Examples

```bash
# Find docs gaps since last doc commit (default)
/ll:update-docs

# Find gaps since a specific date
/ll:update-docs --since=2026-03-01

# Find gaps since a sprint branch point
/ll:update-docs --since=sprint-start

# Find gaps and auto-draft stubs for all gaps
/ll:update-docs --fix

# Catch up docs after a sprint
/ll:update-docs --since=2026-02-15 --fix
```

---

## Integration

After running:
1. Review the gap report to understand what's undocumented
2. **Draft stubs** for gaps where you know what to write
3. **Create issues** for gaps that need research or design
4. Use `/ll:commit` to save all changes (drafted stubs + issue files)

Works well with:
- `/ll:audit-docs` — validates accuracy of *existing* content (complementary, not overlapping)
- `/ll:manage-issue` — implement doc issues created by this skill
- `/ll:commit` — commit drafted stubs and issue files
