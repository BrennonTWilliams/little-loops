# FEAT-228: Add /ll:open-pr Slash Command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-228-add-open-pr-slash-command.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `/ll:describe-pr` exists as a **command** at `commands/describe_pr.md` — it gathers branch info, analyzes commits, generates PR descriptions, and optionally creates the PR via `gh pr create`
- The project uses two mechanisms: **commands** (`commands/*.md` with YAML frontmatter) for procedural instructions, and **skills** (`skills/*/SKILL.md`) as trigger/routing metadata that invoke commands
- Skills auto-discover via the `"skills": ["./skills"]` entry in `plugin.json` — no individual registration needed
- `describe_pr` already has the full PR creation flow (gather info → analyze → generate body → offer to create PR), but it's focused on description generation, not streamlined PR opening
- The `commit.md` command shows the pattern for `allowed-tools: Bash(git:*)`
- Issue ID regex pattern `(BUG|FEAT|ENH)-(\d+)` is well-established in the codebase (see `scripts/little_loops/sync.py:347-360`)

### Patterns to Follow
- Command frontmatter: `description`, `arguments`, `allowed-tools`
- Skill frontmatter: `description` with trigger keywords
- Skill body: "When to Activate", "How to Use", "Integration" sections
- Git info gathering from `describe_pr.md:17-34`

## Desired End State

A new `/ll:open-pr` command and corresponding skill that:
1. Gathers branch/commit information
2. Auto-generates a PR title and body
3. Detects issue references from branch names and commits
4. Supports `--draft` flag and `target_branch` argument
5. Creates the PR via `gh pr create` after user confirmation
6. Reports the resulting PR URL

### How to Verify
- `/ll:open-pr` appears in help and can be invoked
- PR is created on GitHub with correct title, body, and linked issues
- `--draft` flag creates a draft PR
- Custom target branch works
- Issue auto-linking works when branch name contains issue ID

## What We're NOT Doing

- Not modifying `/ll:describe-pr` — we'll incorporate similar logic directly in the new command
- Not adding Python backing code — this is a pure procedural command like `describe_pr`
- Not adding reviewer assignment or label mapping (can be a future enhancement)
- Not adding PR template detection (already handled by describe_pr; users can use describe_pr for template-based workflows)

## Solution Approach

Create two files:
1. **Command**: `commands/open_pr.md` — procedural instructions for Claude to open a PR
2. **Skill**: `skills/open-pr/SKILL.md` — trigger metadata to route users to the command

Then update documentation: `commands/help.md`, `docs/COMMANDS.md`.

## Implementation Phases

### Phase 1: Create the Command

#### Overview
Create `commands/open_pr.md` with the full PR creation workflow.

#### Changes Required

**File**: `commands/open_pr.md` (NEW)
**Changes**: Create command with YAML frontmatter and procedural instructions

The command will:
1. Check prerequisites (`gh auth status`)
2. Gather branch info (current branch, base branch, commits, diff stats)
3. Auto-generate PR title from commits (use first commit subject or conventional commit summary)
4. Auto-generate PR body using describe_pr-style template
5. Detect issue IDs from branch name using regex `(BUG|FEAT|ENH)-(\d+)`
6. Add `Closes #NNN` if GitHub issue number is found in the local issue's frontmatter
7. Present title + body + settings to user for confirmation via `AskUserQuestion`
8. Execute `gh pr create` with appropriate flags (`--draft` if requested)
9. Output PR URL and summary

Key design decisions:
- Arguments: `target_branch` (optional, auto-detect), `flags` (`--draft`)
- `allowed-tools`: `Bash(gh:*, git:*)`
- Issue linking: Parse branch name for issue IDs, then check if the local `.issues/` file has a `github_issue` frontmatter field for the GitHub issue number

#### Success Criteria

**Automated Verification**:
- [ ] File `commands/open_pr.md` exists and has valid YAML frontmatter
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Invoke `/ll:open-pr` in Claude Code — it should gather info and present a PR preview
- [ ] Invoke `/ll:open-pr --draft` — should include `--draft` flag in gh command

---

### Phase 2: Create the Skill

#### Overview
Create `skills/open-pr/SKILL.md` with trigger keywords and routing metadata.

#### Changes Required

**File**: `skills/open-pr/SKILL.md` (NEW)
**Changes**: Create skill definition following the sync-issues/capture-issue pattern

Structure:
- YAML frontmatter with description and trigger keywords ("open pr", "create pull request", "submit pr", "create pr", "open pull request")
- "When to Activate" section
- "How to Use" section mapping user intents to `/ll:open-pr` invocations
- "Integration" section linking to `/ll:commit`, `/ll:check-code`, `/ll:describe-pr`

#### Success Criteria

**Automated Verification**:
- [ ] File `skills/open-pr/SKILL.md` exists and has valid YAML frontmatter
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Saying "open a PR" in Claude Code triggers the skill

---

### Phase 3: Update Documentation

#### Overview
Add `/ll:open-pr` to help command and COMMANDS.md reference.

#### Changes Required

**File**: `commands/help.md`
**Changes**: Add `/ll:open-pr` entry in the "GIT & WORKFLOW" section (after `/ll:describe-pr`) and in the quick reference table

**File**: `docs/COMMANDS.md`
**Changes**: Add `/ll:open-pr` entry in the "Git & Workflow" section and quick reference table

**File**: `commands/commit.md`
**Changes**: Add `/ll:open-pr` to integration section

**File**: `commands/describe_pr.md`
**Changes**: Add `/ll:open-pr` to integration section

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "open_pr" commands/help.md` returns at least 2
- [ ] `grep -c "open_pr" docs/COMMANDS.md` returns at least 2
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] `/ll:help` shows the new `open_pr` command

---

## Testing Strategy

### Manual Tests
- Create a feature branch with commits, run `/ll:open-pr` to verify the full flow
- Test `--draft` flag produces a draft PR
- Test with a branch named like `feat/FEAT-228-description` to verify issue auto-linking
- Test target branch override

### Integration
- Verify `/ll:open-pr` works after `/ll:commit`
- Verify skill triggers on natural language like "open a PR for this"

## References

- Issue: `.issues/features/P3-FEAT-228-add-open-pr-slash-command.md`
- describe_pr pattern: `commands/describe_pr.md`
- Skill pattern: `skills/sync-issues/SKILL.md`
- Command pattern: `commands/commit.md`
- Issue ID regex: `scripts/little_loops/sync.py:347-360`
