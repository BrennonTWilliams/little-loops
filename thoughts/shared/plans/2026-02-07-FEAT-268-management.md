# FEAT-268: Add /ll:manage-release Command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-268-manage-release-command.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- Commands auto-discovered via `.claude-plugin/plugin.json:19` → `"commands": ["./commands"]`
- Version tracked in 3 files: `scripts/pyproject.toml:7`, `.claude-plugin/plugin.json:3`, `scripts/little_loops/__init__.py:25` — all currently `1.3.0`
- Existing tags: `v1.0.0`, `v1.1.0` (no v1.2.0 or v1.3.0 tags)
- `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/) format
- `scan_completed_issues()` at `issue_history.py:981` returns `list[CompletedIssue]` from `.issues/completed/`
- `CompletedIssue` dataclass (`issue_history.py:78-100`) has `completed_date` but NOT `github_issue` — need separate frontmatter parse for GitHub linking
- `parse_frontmatter()` at `frontmatter.py:13` is a flat key-value parser that can extract `github_issue`

### Patterns to Follow
- Command frontmatter: `description`, `arguments`, `allowed-tools` (pattern: `open_pr.md:1-15`)
- Wave pattern: spawn agents in SINGLE message (pattern: `audit_claude_config.md:82-84`)
- Interactive mode: `AskUserQuestion` with `multiSelect` (pattern: `create_sprint.md:99-230`)
- Git/GitHub CLI: `Bash(gh:*, git:*)` tool allowlist (pattern: `open_pr.md:14`)
- `$ARGUMENTS` placeholder for argument docs (pattern: `open_pr.md:172`)
- `gh auth status` prerequisite check (pattern: `open_pr.md:26-27`)
- `github_issue` frontmatter lookup for linking (pattern: `open_pr.md:108-111`)

## Desired End State

A new `/ll:manage-release` command file at `commands/manage_release.md` that:
1. Creates annotated git tags following semver
2. Generates categorized changelogs from commits + completed issues since last tag
3. Creates GitHub releases via `gh` CLI
4. Bumps version strings in `pyproject.toml`, `plugin.json`, `__init__.py`
5. Supports interactive mode (no args) and direct mode (with args)
6. Uses parallel agent wave pattern for data gathering
7. Includes `--dry-run` flag

### How to Verify
- Command file exists at `commands/manage_release.md` with valid frontmatter
- Running `/ll:manage-release` triggers interactive mode
- Running `/ll:manage-release tag v1.4.0 --dry-run` shows tag preview
- Wave pattern spawns 3 agents in a single message
- Completed issues appear categorized in changelog output

## What We're NOT Doing

- Not creating Python module code — this is a command-only feature (all logic is in the command markdown, executed by Claude)
- Not modifying `issue_history.py` — we'll use existing `scan_completed_issues()` and do separate frontmatter parse for `github_issue`
- Not adding unit tests — command files are markdown instructions, not testable code
- Not updating `plugin.json` — commands are auto-discovered
- Not creating a skill — this is a user-invoked command with arguments, matching the command pattern

## Solution Approach

Create a single command file `commands/manage_release.md` following the established patterns. The command will:
1. Check prerequisites (gh auth, git repo)
2. In interactive mode, use AskUserQuestion for action + version selection
3. Spawn 3 parallel agents (Wave 1) for git history, completed issues, and version references
4. Merge results (Wave 2) and execute selected actions sequentially
5. Support `--dry-run` to preview without executing

## Implementation Phases

### Phase 1: Create Command File

#### Overview
Create `commands/manage_release.md` with complete frontmatter, process flow, interactive mode, wave pattern, and all actions.

#### Changes Required

**File**: `commands/manage_release.md` [CREATE]
**Changes**: New command file with:

1. **Frontmatter** — description with trigger keywords, 3 optional arguments (action, version, flags), allowed-tools including `Bash(gh:*, git:*)`, `AskUserQuestion`, `Task`, `Read`, `Glob`, `Grep`

2. **Prerequisites section** — `gh auth status`, verify git repo, check for uncommitted changes

3. **Interactive mode** — When no arguments: AskUserQuestion with 2 questions:
   - Q1: Which release actions? (multiSelect: true) — Full release, Tag only, Changelog only, GitHub release only, Bump only
   - Q2: Version bump level? (multiSelect: false) — Auto-detect, Patch, Minor, Major, Specific version

4. **Wave 1: Parallel data gathering** — 3 Task agents:
   - Agent 1 (Explore): Git history analysis — tags, commits since last tag, conventional commit breakdown, suggested next version
   - Agent 2 (Explore): Completed issues — scan `.issues/completed/`, filter by date, categorize, extract `github_issue` frontmatter
   - Agent 3 (Explore): Version references — find version strings in `pyproject.toml`, `plugin.json`, `__init__.py`

5. **Wave 2: Synthesis + Execution** — Merge results, then execute actions:
   - `tag` — `git tag -a vX.Y.Z -m "Release vX.Y.Z"` + optional `git push origin vX.Y.Z`
   - `changelog` — Generate Keep a Changelog formatted entry, prepend to `CHANGELOG.md`
   - `release` — `gh release create vX.Y.Z --title "vX.Y.Z" --notes-file /tmp/release-notes.md`
   - `bump` — Update version in `pyproject.toml`, `plugin.json`, `__init__.py`
   - `full` — tag → changelog → release → bump (sequential)

6. **Dry-run support** — `--dry-run` shows preview of all actions without executing

7. **Arguments section** — `$ARGUMENTS` + detailed docs
8. **Examples section** — Usage examples
9. **Error Handling section** — Failure modes
10. **Integration section** — Related commands

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/manage_release.md`
- [ ] Frontmatter has valid YAML (`description`, `arguments`, `allowed-tools`)
- [ ] All argument names match spec: `action`, `version`, `flags`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Command appears in `/ll:help` listing
- [ ] Interactive mode prompts correctly
- [ ] Wave pattern spawns agents in single message

---

### Phase 2: Update CHANGELOG.md

#### Overview
Add entry for the new command in the `[Unreleased]` section.

#### Changes Required

**File**: `CHANGELOG.md` [MODIFIED]
**Changes**: Add `manage_release` command to `[Unreleased]` → `### Added` section

#### Success Criteria

**Automated Verification**:
- [ ] CHANGELOG.md has entry mentioning `manage_release`

## Testing Strategy

### Manual Testing
- Run `/ll:manage-release` without args to verify interactive mode
- Run `/ll:manage-release tag v1.4.0 --dry-run` to verify dry-run
- Verify wave pattern spawns 3 agents concurrently

## References

- Original issue: `.issues/features/P3-FEAT-268-manage-release-command.md`
- Command pattern: `commands/open_pr.md:1-15`
- Wave pattern: `commands/audit_claude_config.md:82-209`
- Interactive pattern: `commands/create_sprint.md:99-230`
- Issue history: `scripts/little_loops/issue_history.py:981-1002`
- Version files: `scripts/pyproject.toml:7`, `.claude-plugin/plugin.json:3`, `scripts/little_loops/__init__.py:25`
