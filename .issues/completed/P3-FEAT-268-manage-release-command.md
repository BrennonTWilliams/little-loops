---
discovered_date: 2026-02-06
discovered_by: capture_issue
github_issue: null
github_url: null
last_synced: null
---

# FEAT-268: Add /ll:manage_release Command for Release Management

## Summary

Add a new slash command `/ll:manage_release` to the little-loops Claude Code plugin for release management functionality, including creating git tags, generating changelogs, and managing GitHub releases. Integrates with the plugin's Issue Management system to include completed issues in release notes, supports an interactive no-argument mode via `AskUserQuestion`, and uses a parallel agent wave pattern for efficient data gathering.

## Context

**Direct mode**: User description: "New Slash Command in our `ll@little-loops` (`ll`) claude code plugin, `/ll:manage_release`, for release management functionality (creating git tags, generating changelogs, managing releases). This command should match the same patterns as other similar commands in our `ll` plugin."

The user identified that the plugin lacks release management capabilities despite having commands for:
- `/ll:commit` - Creating commits
- `/ll:open_pr` - Opening pull requests
- `/ll:sync_issues` - Syncing issues with GitHub

## Current Behavior

No slash command or Skill exists for:
- Creating git tags (annotated or lightweight)
- Generating changelogs from commit history
- Creating GitHub releases
- Managing release notes
- Version bumping

## User Story

As a solo developer, I want to automate my release process so I can ship faster with less manual effort.

## Acceptance Criteria

- [ ] `tag` action creates annotated git tags following semver (vX.Y.Z)
- [ ] `changelog` action generates a categorized changelog from commits and completed issues since last tag
- [ ] `release` action creates a GitHub release via `gh` CLI with generated notes
- [ ] `bump` action updates version strings in project files (pyproject.toml, .claude-plugin/plugin.json)
- [ ] `full` action runs tag + changelog + release + bump in sequence
- [ ] Interactive mode (no arguments) prompts user via `AskUserQuestion` for actions and version, then executes without further stops
- [ ] Completed issues since last tag appear in changelogs/release notes, categorized by type (BUG, FEAT, ENH)
- [ ] Issues with `github_issue` frontmatter include linked GitHub issue numbers in notes
- [ ] Wave 1 spawns 3 parallel agents (git history, completed issues, version references) in a single message
- [ ] Wave 2 merges agent results before executing selected actions
- [ ] `--dry-run` flag previews actions without executing them
- [ ] Command file placed in `commands/` directory (auto-discovered by plugin via `.claude-plugin/plugin.json`)

## Expected Behavior

A new `/ll:manage_release` command should provide:

1. **Git tag creation**: Create version tags following semantic versioning (vX.Y.Z)
2. **Changelog generation**: Generate changelogs from commits since last tag
3. **GitHub release creation**: Create GitHub releases with auto-generated notes
4. **Version management**: Update version numbers in project files
5. **Issue integration**: Changelog and release notes include completed Issues since last tag, categorized by type (BUG, FEAT, ENH)
6. **Interactive mode**: When run without arguments, use `AskUserQuestion` to gather release preferences, then execute all selected actions without further stops
7. **Parallel data gathering**: Use agent wave pattern to gather git history, completed issues, and version references concurrently

## Proposed Solution

Create a new command file `commands/manage_release.md` following the pattern of existing commands like `open_pr.md` and `sync_issues.md`:

### Command Structure

```yaml
---
description: |
  Manage releases - create git tags, generate changelogs, and manage GitHub releases.
  Integrates with Issue Management to include completed issues in release notes.

  Trigger keywords: "manage release", "create release", "new release", "tag release", "publish release", "make release"
allowed-tools:
  - Bash(git:*)
  - Bash(gh:*)
  - AskUserQuestion
  - Task
arguments:
  - name: action
    description: "Action to perform (tag|changelog|release|bump|full). Omit for interactive mode."
    required: false
  - name: version
    description: "Version string (e.g., v1.2.3 or 1.2.3)"
    required: false
  - name: flags
    description: "Optional flags: --dry-run, --annotate, --push, --draft"
    required: false
---
```

### Interactive No-Argument Mode

When `/ll:manage_release` is invoked without arguments, use `AskUserQuestion` to gather user preferences before executing. Pattern reference: `commands/create_sprint.md` (extensive `AskUserQuestion` usage).

**Step 1**: Ask the user what release actions to perform and which version to target:

```yaml
questions:
  - question: "Which release actions should be performed?"
    header: "Actions"
    multiSelect: true
    options:
      - label: "Full release (Recommended)"
        description: "Run tag + changelog + release + bump in sequence"
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

**After initial approval**: Execute ALL selected actions without stopping for further confirmation. The interactive prompt is the single point of user input.

### Wave 1: Parallel Information Gathering

Spawn 3 agents in a SINGLE message using the Task tool (pattern reference: `commands/audit_claude_config.md` wave pattern):

**Agent 1** — Git History Analysis (`subagent_type="codebase-analyzer"`):
- List all tags, identify the most recent tag
- Gather commits since last tag with conventional commit parsing
- Break down commits by type (feat, fix, refactor, docs, chore, etc.)
- Suggest next version based on conventional commit types

**Agent 2** — Completed Issues (`subagent_type="codebase-analyzer"`):
- Scan `.issues/completed/` directory
- Filter issues where `completed_date >= last_tag_date`
- Categorize by type: BUG, FEAT, ENH
- Reference `scan_completed_issues()` from `scripts/little_loops/issue_history.py`
- Extract `github_issue` frontmatter for linking

**Agent 3** — Version References (`subagent_type="codebase-locator"`):
- Find version fields in `pyproject.toml`, `plugin.json`, and any other project files
- Report current version values and file locations for bump operations

### Wave 2: Synthesis and Execution

After Wave 1 agents complete:

1. **Merge results**: Combine git commit analysis with completed issue data
2. **Generate categorized changelog**:
   - **Features** — FEAT issues + `feat:` commits
   - **Bug Fixes** — BUG issues + `fix:` commits
   - **Enhancements** — ENH issues + `refactor:`/`perf:` commits
   - **Other Changes** — Commits without associated issues (docs, chore, ci, etc.)
3. **Execute selected actions** sequentially without further user prompts
4. **Use `run_in_background`** for `git push` and `gh release create` operations where appropriate

### Issue Integration Details

- Use `issue_history.py` → `scan_completed_issues()` to get all completed issues
- Filter by `completed_date >= last_tag_date` to scope to the current release
- Complement with git commit analysis for changes that don't have associated issues
- Include GitHub issue links where `github_issue` frontmatter field exists
- Changelog entry format: `- ISSUE-ID: Title (#github_number)` (e.g., `- BUG-245: Fix config loader crash (#42)`)
- For commits without issues: `- type: commit message (sha_short)`

### Implementation Plan

1. **Create command file**: `commands/manage_release.md`
   - Follow the same frontmatter pattern as `open_pr.md` and `sync_issues.md`
   - Include trigger keywords for discoverability
   - Allow `gh` CLI tools for GitHub integration
   - Include `AskUserQuestion` and `Task` in allowed-tools

2. **Implement actions**:
   - `tag` - Create git tag (annotated by default)
   - `changelog` - Generate changelog from commits and completed issues since last tag
   - `release` - Create GitHub release with notes
   - `bump` - Update version in project files (pyproject.toml, plugin.json, etc.)
   - `full` - Run tag + changelog + release + bump in sequence

3. **Add to plugin manifest**: Update `.claude-plugin/plugin.json` if needed (note: commands in `commands/` are auto-discovered via the `"commands": ["./commands"]` directive)

4. **Add tests**: Create tests in `scripts/tests/` following existing patterns

### Example Usage

```bash
# Interactive mode — prompts for actions and version
/ll:manage_release

# Create a new release tag
/ll:manage_release tag v1.5.0

# Generate changelog for upcoming release
/ll:manage_release changelog

# Create full GitHub release
/ll:manage_release release v1.5.0

# Bump version and tag
/ll:manage_release bump patch

# Full release pipeline (tag + changelog + release + bump)
/ll:manage_release full v1.5.0

# Create a draft GitHub release
/ll:manage_release release v1.5.0 --draft
```

## Impact

- **Priority**: P3
- **Effort**: Medium-High (expanded scope with issue integration, interactive mode, and parallel agent waves)
- **Risk**: Low (new command, doesn't modify existing functionality)
- **Dependencies**: `scripts/little_loops/issue_history.py` (`CompletedIssue` dataclass, `scan_completed_issues()` function), wave pattern from `commands/audit_claude_config.md`, interactive pattern from `commands/create_sprint.md`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | commands/open_pr.md | Similar command structure pattern |
| guidelines | commands/sync_issues.md | Similar GitHub CLI integration pattern |
| guidelines | commands/commit.md | Git operations pattern |
| guidelines | commands/audit_claude_config.md | Wave pattern for parallel agent spawning |
| guidelines | commands/create_sprint.md | AskUserQuestion interactive mode pattern |
| architecture | docs/ARCHITECTURE.md | Command registration and plugin structure |
| implementation | scripts/little_loops/issue_history.py | CompletedIssue dataclass, scan_completed_issues() function |

## Labels

`feature`, `command`, `release-management`, `github-integration`, `issue-integration`, `interactive`

---

## Status

**Completed** | Created: 2026-02-06 | Completed: 2026-02-07 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-07
- **Status**: Completed

### Changes Made
- `commands/manage_release.md`: New command file with full release management workflow — git tags, changelog generation, GitHub releases, version bumping, interactive mode via AskUserQuestion, and parallel agent wave pattern for data gathering
- `CHANGELOG.md`: Added `manage_release` command entry to `[Unreleased]` section

### Verification Results
- Tests: PASS (2607 passed)
- Lint: PASS (pre-existing issues only)
- Types: PASS (no issues in 46 source files)
