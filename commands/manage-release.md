---
description: |
  Manage releases - create git tags, generate changelogs, and manage GitHub releases.
  Integrates with Issue Management to include completed issues in release notes.

  Trigger keywords: "manage release", "create release", "new release", "tag release", "publish release", "make release", "bump version"
argument-hint: "[action] [version]"
arguments:
  - name: action
    description: "Action to perform (tag|changelog|release|bump|full). Omit for interactive mode."
    required: false
  - name: version
    description: "Version string (e.g., v1.2.3 or 1.2.3) or bump level (patch|minor|major)"
    required: false
  - name: flags
    description: "Optional flags: --dry-run, --push, --draft"
    required: false
allowed-tools:
  - Bash(gh:*, git:*)
  - AskUserQuestion
  - Task
  - Read
  - Glob
  - Grep
---

# Manage Release

You are tasked with managing releases for this project. This includes creating git tags, generating changelogs from commits and completed issues, creating GitHub releases, and bumping version numbers.

## Configuration

Read settings from `.claude/ll-config.json`:

- **Issues base**: `{{config.issues.base_dir}}` (default: `.issues`)
- **Completed dir**: `{{config.issues.completed_dir}}` (default: `completed`)

Version is tracked in these files:
- `{{config.project.src_dir}}pyproject.toml` — `version = "X.Y.Z"`
- `.claude-plugin/plugin.json` — `"version": "X.Y.Z"`
- `{{config.project.src_dir}}little_loops/__init__.py` — `__version__ = "X.Y.Z"`

Changelog: `CHANGELOG.md` (follows [Keep a Changelog](https://keepachangelog.com/) format)

---

## Process

### 1. Check Prerequisites

```bash
# Verify gh CLI is authenticated
gh auth status

# Verify we're in a git repo
git rev-parse --git-dir

# Check for uncommitted changes
git status --porcelain
```

If `gh` is not authenticated, instruct the user to run `gh auth login` and stop.

If there are uncommitted changes, warn the user and ask whether to proceed or stop:

```yaml
questions:
  - question: "There are uncommitted changes in the working tree. Proceed with release anyway?"
    header: "Uncommitted"
    multiSelect: false
    options:
      - label: "Proceed anyway"
        description: "Continue with release despite uncommitted changes"
      - label: "Stop"
        description: "Abort release to commit or stash changes first"
```

### 2. Parse Arguments

```
ACTION="${action}"        # tag|changelog|release|bump|full (optional)
VERSION="${version}"      # vX.Y.Z, X.Y.Z, patch, minor, major (optional)
DRY_RUN=false            # set true if flags contains "--dry-run"
PUSH=false               # set true if flags contains "--push"
DRAFT=false              # set true if flags contains "--draft"
```

### 3. Interactive Mode (No Arguments)

If `ACTION` is empty, use `AskUserQuestion` to gather preferences:

```yaml
questions:
  - question: "Which release actions should be performed?"
    header: "Actions"
    multiSelect: true
    options:
      - label: "Full release (Recommended)"
        description: "Run bump + tag + changelog + release in sequence"
      - label: "Tag only"
        description: "Create a git tag for the release version"
      - label: "Changelog only"
        description: "Generate changelog from commits and completed issues since last tag"
      - label: "GitHub release only"
        description: "Create a GitHub release with generated notes"
  - question: "Which version bump level should be used?"
    header: "Version"
    multiSelect: false
    options:
      - label: "Auto-detect (Recommended)"
        description: "Infer from conventional commits (feat→minor, fix→patch, BREAKING→major)"
      - label: "Patch"
        description: "Bug fixes and minor changes (x.y.Z)"
      - label: "Minor"
        description: "New features, backwards compatible (x.Y.0)"
      - label: "Major"
        description: "Breaking changes (X.0.0)"
```

Map user responses to action and version variables:
- "Full release" → `ACTION=full`
- "Tag only" → `ACTION=tag`
- "Changelog only" → `ACTION=changelog`
- "GitHub release only" → `ACTION=release`
- If multiple selected, execute each in order: bump → tag → changelog → release
- "Auto-detect" → `VERSION=auto`
- "Patch" / "Minor" / "Major" → `VERSION=patch|minor|major`

**After initial prompt**: Execute ALL selected actions without stopping for further confirmation.

---

### 4. Wave 1: Parallel Information Gathering

**IMPORTANT**: Spawn all 3 agents in a SINGLE message with multiple Task tool calls.

#### Agent 1: Git History Analysis

```
Use Task tool with subagent_type="Explore"

Prompt:
Analyze git history for release preparation.

1. List all existing tags:
   git tag --list --sort=-version:refname

2. Identify the most recent tag:
   git describe --tags --abbrev=0

3. Get commits since last tag (or all commits if no tags):
   git log <last_tag>..HEAD --pretty=format:"%H|%s|%an|%ad" --date=short

4. Parse conventional commits and categorize:
   - feat: → Features (minor bump)
   - fix: → Bug Fixes (patch bump)
   - refactor:/perf: → Improvements
   - docs: → Documentation
   - chore:/ci:/build: → Maintenance
   - BREAKING CHANGE or !: → Breaking Changes (major bump)

5. Suggest next version based on commit types:
   - If any BREAKING CHANGE → major
   - If any feat: → minor
   - Otherwise → patch

Return: last tag, commit breakdown by type, suggested next version, full commit list.
```

#### Agent 2: Completed Issues Since Last Tag

```
Use Task tool with subagent_type="Explore"

Prompt:
Scan completed issues for release notes.

1. First, determine the date of the last git tag:
   git log --format=%ai $(git describe --tags --abbrev=0) -1

2. Scan .issues/completed/ for all .md files

3. For each completed issue file:
   - Parse the filename for priority, type (BUG/FEAT/ENH), and issue ID
   - Read the file and extract:
     - Title from the H1 heading
     - completed_date from the Resolution section
     - github_issue from frontmatter (if present)
   - Include the issue if completed_date >= last_tag_date

4. Categorize issues:
   - Features: FEAT-* issues
   - Bug Fixes: BUG-* issues
   - Enhancements: ENH-* issues

5. Format each entry as:
   - With github_issue: "ISSUE-ID: Title (#github_number)"
   - Without github_issue: "ISSUE-ID: Title"

Return: categorized list of issues, count per category, date range.
```

#### Agent 3: Version References

```
Use Task tool with subagent_type="Explore"

Prompt:
Find all version references in the project.

Search for version strings in these files:
1. {{config.project.src_dir}}pyproject.toml — look for: version = "X.Y.Z"
2. .claude-plugin/plugin.json — look for: "version": "X.Y.Z"
3. {{config.project.src_dir}}little_loops/__init__.py — look for: __version__ = "X.Y.Z"
4. Any other files containing the current version string

For each file found, report:
- File path and line number
- Current version value
- The exact line content (for precise editing)

Return: list of version locations with current values.
```

### 5. Wave 2: Synthesis and Execution

After all Wave 1 agents complete:

#### 5a. Merge Results

1. **Determine target version**:
   - If `VERSION=auto`: use Wave 1 Agent 1's suggestion based on conventional commits
   - If `VERSION=patch|minor|major`: calculate from current version (Wave 1 Agent 3)
   - If `VERSION=vX.Y.Z` or `X.Y.Z`: use as-is (normalize to `vX.Y.Z` for tags, `X.Y.Z` for files)

2. **Build release notes** by merging:
   - Completed issues (Agent 2) grouped by type
   - Commits without associated issues (Agent 1) grouped by conventional commit type

#### 5b. Execute Actions

If `DRY_RUN` is true, show preview of each action instead of executing.

Execute actions in order: **bump → tag → changelog → release**

##### Action: `bump`

Update version in all files found by Agent 3:

```bash
# For each version file, use Edit tool to update version string
# {{config.project.src_dir}}pyproject.toml: version = "X.Y.Z" → version = "NEW_VERSION"
# .claude-plugin/plugin.json: "version": "X.Y.Z" → "version": "NEW_VERSION"
# {{config.project.src_dir}}little_loops/__init__.py: __version__ = "X.Y.Z" → __version__ = "NEW_VERSION"
```

After bumping, commit the version change:

```bash
git add {{config.project.src_dir}}pyproject.toml .claude-plugin/plugin.json {{config.project.src_dir}}little_loops/__init__.py
git commit -m "chore(release): bump version to NEW_VERSION"
```

##### Action: `tag`

Create an annotated git tag:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

If `--push` flag is set:

```bash
git push origin vX.Y.Z
```

##### Action: `changelog`

Generate a changelog entry following the [Keep a Changelog](https://keepachangelog.com/) format.

Build the entry:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added

- **Feature name** - Description (FEAT-NNN)
- feat: commit message (abc1234)

### Fixed

- **Bug fix name** - Description (BUG-NNN)
- fix: commit message (abc1234)

### Changed

- **Enhancement name** - Description (ENH-NNN)
- refactor: commit message (abc1234)

### Other

- docs: commit message (abc1234)
- chore: commit message (abc1234)
```

Rules:
- Completed issues take priority over commits — if a commit is associated with an issue, only list the issue
- Include GitHub issue links where `github_issue` exists: `(FEAT-NNN, #42)`
- Omit empty sections (e.g., if no "Fixed" entries, don't include the heading)
- Add comparison link at bottom: `[X.Y.Z]: https://github.com/OWNER/REPO/compare/PREV_TAG...vX.Y.Z`

Insert the entry into `CHANGELOG.md`:
1. Read current `CHANGELOG.md`
2. Replace `## [Unreleased]` section content with the `### Planned` items (keep section header)
3. Insert new version section between `## [Unreleased]` and the previous version section
4. Add comparison link

Commit the changelog:

```bash
git add CHANGELOG.md
git commit -m "docs(release): add changelog for vX.Y.Z"
```

##### Action: `release`

Create a GitHub release:

```bash
# Write release notes to temp file
# (Same content as changelog entry, formatted for GitHub)

gh release create vX.Y.Z \
  --title "vX.Y.Z" \
  --notes-file /tmp/ll-release-notes.md
```

If `--draft` flag is set, add `--draft` to the command.

If the tag hasn't been pushed yet:

```bash
git push origin vX.Y.Z
```

##### Action: `full`

Execute all actions in sequence: bump → tag → changelog → release

---

### 6. Dry-Run Output

When `--dry-run` is active, output:

```
=== DRY RUN: Release vX.Y.Z ===

Current version: A.B.C
Target version:  X.Y.Z
Last tag:        vA.B.C

Actions to perform:
  [bump]      Update version in 3 files
  [tag]       Create annotated tag vX.Y.Z
  [changelog] Add changelog entry with N issues and M commits
  [release]   Create GitHub release vX.Y.Z

--- Changelog Preview ---

## [X.Y.Z] - YYYY-MM-DD

### Added
- ...

### Fixed
- ...

--- Version Files ---
  {{config.project.src_dir}}pyproject.toml:7 → version = "X.Y.Z"
  .claude-plugin/plugin.json:3 → "version": "X.Y.Z"
  {{config.project.src_dir}}little_loops/__init__.py:25 → __version__ = "X.Y.Z"

=== END DRY RUN (no changes made) ===
```

### 7. Report Result

After successful execution, output:

```
Release vX.Y.Z completed successfully!

  Tag:       vX.Y.Z (annotated)
  Changelog: CHANGELOG.md updated
  Release:   https://github.com/OWNER/REPO/releases/tag/vX.Y.Z
  Version:   X.Y.Z (updated in 3 files)

  Issues included: N (F features, B bug fixes, E enhancements)
  Commits included: M
```

---

## Arguments

$ARGUMENTS

- **action** (optional): Action to perform
  - `tag` — Create an annotated git tag
  - `changelog` — Generate changelog from commits and completed issues since last tag
  - `release` — Create a GitHub release with generated notes
  - `bump` — Update version strings in project files
  - `full` — Run bump + tag + changelog + release in sequence
  - If omitted, enters interactive mode

- **version** (optional): Version target
  - `vX.Y.Z` or `X.Y.Z` — Use specific version
  - `patch` — Bump patch version (x.y.Z)
  - `minor` — Bump minor version (x.Y.0)
  - `major` — Bump major version (X.0.0)
  - If omitted, auto-detects from conventional commits

- **flags** (optional):
  - `--dry-run` — Preview actions without executing
  - `--push` — Push tag to remote after creation
  - `--draft` — Create GitHub release as draft

---

## Examples

```bash
# Interactive mode — prompts for actions and version
/ll:manage-release

# Create a specific version tag
/ll:manage-release tag v1.5.0

# Generate changelog (auto-detect version from commits)
/ll:manage-release changelog

# Full release pipeline with specific version
/ll:manage-release full v1.5.0

# Full release with auto-detected version
/ll:manage-release full

# Bump version only
/ll:manage-release bump minor

# Preview what a release would do
/ll:manage-release full v1.5.0 --dry-run

# Create a draft GitHub release
/ll:manage-release release v1.5.0 --draft

# Tag and push to remote
/ll:manage-release tag v1.5.0 --push
```

---

## Error Handling

- **gh not installed**: Suggest installation via `brew install gh` (macOS) or platform docs
- **gh not authenticated**: Suggest `gh auth login`
- **Not a git repo**: Inform user and stop
- **Uncommitted changes**: Warn and ask to proceed or stop
- **Tag already exists**: Inform user, offer to use `--force` or choose different version
- **No commits since last tag**: Inform user there are no changes to release
- **Version parse failure**: Show current version and ask user to provide explicit version
- **GitHub release creation fails**: Show error, suggest checking `gh auth status` and repository permissions

---

## Integration

This command works well with:
- `/ll:commit` — Commit changes before releasing
- `/ll:check-code` — Ensure code quality before releasing
- `/ll:run-tests` — Verify tests pass before releasing
- `/ll:manage-issue` — Complete issues that should be in the release
- `/ll:sync-issues` — Sync issues with GitHub before including in release notes
- `/ll:open-pr` — Open PR for release branch if using release branches
