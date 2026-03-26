---
type: ENH
id: ENH-894
title: Ask to add ll- CLI commands to target project CLAUDE.md during init --interactive
priority: P3
status: open
created: 2026-03-26
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# ENH-894: Ask to add ll- CLI commands to target project CLAUDE.md during init --interactive

## Summary

When `/ll:init --interactive` asks whether to register ll- CLI commands in `.claude/settings.json` or `.claude/settings.local.json`, it should also ask if those commands should be documented in the target project's `CLAUDE.md` file (creating the file if none exists).

## Current Behavior

The init wizard asks whether to add ll- CLI commands to `.claude/settings.json` or `.claude/settings.local.json` (the permissions/allowed-tools configuration). It does not ask about updating or creating the target project's `CLAUDE.md` to document the available ll- CLI commands.

## Expected Behavior

After asking about settings file registration, the init wizard includes an additional prompt:

> "Would you also like to add ll- CLI command documentation to your project's `CLAUDE.md`? (Creates the file if it doesn't exist)"

If the user answers yes:
1. Check if `.claude/CLAUDE.md` (or `CLAUDE.md`) exists in the target project
2. If it exists, append an `## little-loops` section with the CLI commands list
3. If it does not exist, create it with a minimal structure including the CLI commands section

## Motivation

Developers who install little-loops via init and configure the settings permissions still need to discover the available `ll-` CLI commands. Adding this to `CLAUDE.md` gives all contributors (and future Claude Code sessions in that project) immediate visibility into the available commands, without requiring them to remember to run `/ll:help` or read the README.

## Success Metrics

- Users completing `/ll:init --interactive` are prompted about CLAUDE.md documentation
- When user answers yes: `.claude/CLAUDE.md` (or `CLAUDE.md`) in the target project contains a `## little-loops Commands` section after wizard completion
- When user answers no: no CLAUDE.md files are created or modified

## Scope Boundaries

- **In scope**: New optional wizard step in `skills/init/SKILL.md` for `--interactive` mode; detecting, appending to, or creating `.claude/CLAUDE.md` in the target project
- **Out of scope**: Non-interactive init mode (`--auto`); auto-detecting which commands are relevant per project; updating an already-present `## little-loops Commands` section if content drifts; providing a configurable template for the commands section

## Proposed Solution

In `skills/init/SKILL.md`, add a new step after the current settings.json/settings.local.json question:

1. Display the question about adding ll- commands to `CLAUDE.md`
2. If yes, detect whether `.claude/CLAUDE.md` exists in the target project
3. If it exists, append a `## little-loops Commands` (or similar heading) section with the standard ll- CLI commands list
4. If it does not exist, create `.claude/CLAUDE.md` with a header block and the commands section

The section to append/create should include the core CLI commands (ll-auto, ll-parallel, ll-sprint, ll-loop, ll-issues, etc.) with brief one-line descriptions, mirroring what's in the little-loops README or CLAUDE.md.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Add Step 11.5 (new CLAUDE.md action step after Step 10, ~line 440); update dry-run preview block (~line 268) and completion message (~line 444)
- `skills/init/interactive.md` — Add Round 12 wizard question after Round 11 (~line 669); update STEP/TOTAL counter (~line 9) and round summary table (~line 673)

### Similar Patterns
- `skills/init/SKILL.md:307-328` — Step 9 gitignore: check existence → create or append with duplicate guard; exact "conditionally write to a file" pattern to follow for CLAUDE.md handling
- `skills/init/SKILL.md:393-440` — Step 10 settings merge: reads wizard answer, detects files with `[ -f path ] && VAR=true`, performs conditional write; action step pattern for the new Step 11.5
- `skills/init/interactive.md:621-635` — Round 11 Allowed Tools question: exact `AskUserQuestion` YAML format (header/question/options/multiSelect) and "Skip" option convention; the predecessor round
- `skills/init/SKILL.md:444-471` — Step 11 completion message: conditional `Created:` / `Updated:` line pattern to follow for reporting the CLAUDE.md outcome

### Tests
- Manual: run `/ll:init --interactive` in a temp project directory with and without an existing `CLAUDE.md`; verify the appended/created section is correct

### Documentation
- No additional docs needed — this step is self-documenting through the wizard

### Configuration
- Could optionally be controlled by a config flag (e.g., `init.add_claude_md_commands: true`) but not required for initial implementation

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Canonical section content**: `.claude/CLAUDE.md:101-118` — the `## CLI Tools` section with 13 ll- command bullets is the exact format to replicate; use heading `## little-loops CLI Commands` (more descriptive when embedded in another project's CLAUDE.md)
- **TOTAL counter**: `skills/init/interactive.md:9-27` defines `TOTAL = 5`; Round 12 is conditional, so increment TOTAL when the user opts in (following the Round 5a pattern at `interactive.md:219-229`)
- **Dry-run preview block**: `skills/init/SKILL.md:268-274` must include `[write] .claude/CLAUDE.md` or `[update] .claude/CLAUDE.md` conditional line
- **Round summary table**: `skills/init/interactive.md:673-690` — add Row 12 with condition "If user opts in to CLAUDE.md documentation"
- **File existence check**: use `[ -f ".claude/CLAUDE.md" ] || [ -f "CLAUDE.md" ]` — same `[ -f path ] && VAR=true` idiom as `skills/init/SKILL.md:401-406`
- **Duplicate guard**: check for `## little-loops` presence in existing CLAUDE.md (section-level match, not line-level) before appending to avoid re-running

_Updated by `/ll:refine-issue` — second pass with deeper verification:_

- **TOTAL counter clarification** (`interactive.md:13`): Round 12 is always presented in `--interactive` mode (user can only "skip" it, the wizard doesn't skip it) — treat it like Round 11 (mandatory), not like Round 5a (conditional). Increment `TOTAL = 5` → `TOTAL = 6` unconditionally. Round 5a then adds 1 more if parallel selected, giving a range of 6–7. Update the summary comment on `interactive.md:13` from `# Working total (mandatory rounds: 1, 2, 3a, 6, 11)` to `# Working total (mandatory rounds: 1, 2, 3a, 6, 11, 12)`. Update the summary comment on `interactive.md:675` from `Total interaction rounds: 5–6 (6 only if parallel processing selected)` to `Total interaction rounds: 6–7 (7 only if parallel processing selected)`.

- **Round summary table row** (`interactive.md:689`): Add after Round 11 row:
  ```
  | **12** | **CLAUDE.md Docs** | **add ll- CLI commands to CLAUDE.md (yes/skip)** | **Always in --interactive** |
  ```

- **Round 12 AskUserQuestion YAML** — two variants based on `CLAUDE_MD_EXISTS` detection. If **`.claude/CLAUDE.md` or `CLAUDE.md` exists**:
  ```yaml
  questions:
    - header: "CLAUDE.md Documentation"
      question: "Add ll- CLI command documentation to your project's CLAUDE.md?"
      options:
        - label: "Yes, append to existing CLAUDE.md (Recommended)"
          description: "Append a ## little-loops CLI Commands section to the existing file"
        - label: "Skip"
          description: "Don't modify CLAUDE.md"
      multiSelect: false
  ```
  If **neither exists**:
  ```yaml
  questions:
    - header: "CLAUDE.md Documentation"
      question: "Add ll- CLI command documentation to your project's CLAUDE.md? (Improves discoverability)"
      options:
        - label: "Yes, create .claude/CLAUDE.md (Recommended)"
          description: "Create .claude/CLAUDE.md with a minimal header and ## little-loops CLI Commands section"
        - label: "Skip"
          description: "Don't create a CLAUDE.md file"
      multiSelect: false
  ```

- **Dry-run preview lines** — append after `SKILL.md:269` (the `[update] .claude/settings.local.json` line):
  ```
    [write]  .claude/CLAUDE.md (ll- CLI command documentation)        # Only if opted in + no existing file
    [update] .claude/CLAUDE.md (append ## little-loops CLI Commands)  # Only if opted in + existing file
  ```

- **Completion message lines** — append after `SKILL.md:453` (the `Updated: .claude/settings.local.json` line):
  ```
  Created: .claude/CLAUDE.md (ll- CLI command documentation)         # Only if opted in + new file
  Updated: .claude/CLAUDE.md (appended ## little-loops CLI Commands)  # Only if opted in + existing
  ```

- **Exact section content to write/append** (source: `.claude/CLAUDE.md:101-118`, heading renamed):
  ```markdown
  ## little-loops CLI Commands

  - `ll-auto` - Process all backlog issues sequentially in priority order
  - `ll-parallel` - Process issues concurrently using isolated git worktrees
  - `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
  - `ll-loop` - Execute FSM-based automation loops
  - `ll-workflows` - Identify multi-step workflow patterns from user message history
  - `ll-messages` - Extract user messages from Claude Code logs
  - `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
  - `ll-deps` - Cross-issue dependency analysis and validation
  - `ll-sync` - Sync local issues with GitHub Issues
  - `ll-verify-docs` - Verify documented counts match actual file counts
  - `ll-check-links` - Check markdown documentation for broken links
  - `ll-issues` - Issue management and visualization (next-id, list, show, sequence, impact-effort, refine-status)
  - `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files

  Install: `pip install -e "./scripts[dev]"`
  ```
  When creating `.claude/CLAUDE.md` from scratch, wrap in a minimal header: `# Project Configuration\n\n` before the section. Note: `ll-gitignore` is the 13th CLI tool but is intentionally absent from the settings allow-list (which has 12 `Bash(ll-*)` entries + `Write(.claude/ll-continue-prompt.md)`).

## API/Interface

N/A - No public API changes (wizard flow modification in `skills/init/SKILL.md` only)

## Implementation Steps

1. **`skills/init/interactive.md`** (~line 9): increment `TOTAL = 5` to `TOTAL = 6` to account for the new conditional Round 12; update round summary table at ~line 673 with Round 12 row (condition: "If user opts in to CLAUDE.md documentation")
2. **`skills/init/interactive.md`** (after Round 11, ~line 669): add Round 12 — run `[ -f ".claude/CLAUDE.md" ] || [ -f "CLAUDE.md" ]` Bash check first, then call `AskUserQuestion` using the same YAML format as `interactive.md:621-635`; offer three options: "Append to existing CLAUDE.md", "Create .claude/CLAUDE.md", "Skip"; record result for Step 11.5
3. **`skills/init/SKILL.md`** (after Step 10, ~line 440): add Step 11.5 — read the Round 12 answer; if "Skip", proceed to Step 11 unchanged; otherwise follow the Step 9 gitignore pattern (`SKILL.md:307-328`): read existing CLAUDE.md (if present), check for an existing `## little-loops` heading (duplicate guard), append `## little-loops CLI Commands` section with the 13-command bullet list from `.claude/CLAUDE.md:104-116`; or create `.claude/CLAUDE.md` with a minimal header + commands section if no CLAUDE.md exists; track "Created" vs. "Updated" for reporting
4. **`skills/init/SKILL.md:268-274`** (dry-run preview block): add conditional line `[write] .claude/CLAUDE.md (ll- CLI command documentation)` or `[update] .claude/CLAUDE.md (append ## little-loops CLI Commands section)`
5. **`skills/init/SKILL.md:444-471`** (completion message): add conditional line following the `Updated: .claude/settings.local.json` pattern — `Created: .claude/CLAUDE.md` or `Updated: CLAUDE.md (appended ## little-loops CLI Commands section)` depending on which path was taken
6. Verify: run `/ll:init --interactive` in a temp directory (a) without any CLAUDE.md, (b) with an existing `.claude/CLAUDE.md`, (c) choosing "Skip"; confirm correct file creation, append, and no-op respectively

## Impact

- **Priority**: P3 — Improves discoverability for new project adopters
- **Effort**: Small-Medium — One new wizard step + file create/append logic
- **Risk**: Low — Additive only; no existing behavior changed
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/init/SKILL.md` | Target file for the new init wizard step |
| `.claude/CLAUDE.md` | Example of the ll- commands documentation format to replicate |
| `README.md` | Documents the ll- CLI commands; source for section content |

## Labels

`enhancement`, `init`, `onboarding`, `claude-md`, `discoverability`

## Session Log
- `/ll:refine-issue` - 2026-03-26T19:57:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a6984070-445a-4d12-84a8-cff27f584410.jsonl`
- `/ll:confidence-check` - 2026-03-26T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d74fd998-5ed3-431a-9af6-24ec2e79ab03.jsonl`
- `/ll:refine-issue` - 2026-03-26T19:47:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c471ee77-14f8-4630-9bf8-5cb13df084f7.jsonl`
- `/ll:format-issue` - 2026-03-26T19:42:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b405b1fd-34e7-4ad1-b03e-220b227f80c2.jsonl`
- `/ll:capture-issue` - 2026-03-26T19:38:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Open** | Created: 2026-03-26 | Priority: P3
