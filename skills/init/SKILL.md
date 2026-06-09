---
name: init
description: Use when asked to initialize little-loops, set up ll for a project, or bootstrap config.
argument-hint: "[flags]"
allowed-tools:
  - Read
  - Glob
  - Write
  - Edit
  - AskUserQuestion
  - Bash(mkdir:*)
  - Bash(which:*)
  - Bash(python3:*)
  - Bash(pip:*)
arguments:
  - name: flags
    description: Optional flags (--interactive, --yes, --force, --dry-run, --codex)
    required: false
metadata:
  short-description: Use when asked to initialize little-loops, set up ll for a project, or bootstrap
---

# Initialize Configuration

<!-- PLUGIN_VERSION: 1.106.0 -->

You are tasked with initializing little-loops configuration for a project by creating `.ll/ll-config.json`.

## Arguments

$ARGUMENTS

- **flags** (optional): Command flags
  - `--interactive` - Full guided wizard mode with prompts for each option
  - `--yes` - Accept all defaults without confirmation
  - `--force` - Overwrite existing configuration file
  - `--dry-run` - Preview generated configuration without writing files
  - `--codex` - Also install the OpenAI Codex CLI hook adapter (writes `.codex/hooks.json` from the codex adapter template). Auto-enabled when `codex` is on PATH **or** a `.codex/` directory already exists in the project root. See Step 8.5.

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
INTERACTIVE=false
YES=false
FORCE=false
DRY_RUN=false
CODEX=false

if [[ "$FLAGS" == *"--interactive"* ]]; then INTERACTIVE=true; fi
if [[ "$FLAGS" == *"--yes"* ]]; then YES=true; fi
if [[ "$FLAGS" == *"--force"* ]]; then FORCE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--codex"* ]]; then CODEX=true; fi

_ACTIVE_HOST="${LL_HOST_CLI:-${LL_HOOK_HOST:-}}"
if [[ "$CODEX" == false ]] && [[ "$_ACTIVE_HOST" != "claude-code" ]]; then
    if command -v codex >/dev/null 2>&1 || [ -d ".codex" ]; then CODEX=true; fi
fi

# Validate: --interactive and --yes are mutually exclusive
if [[ "$INTERACTIVE" == true ]] && [[ "$YES" == true ]]; then
    echo "Error: Cannot combine --interactive and --yes"; exit 1
fi
```

See [templates.md](templates.md) for the valid flag combinations table.

### 2. Check Existing Configuration

Before proceeding, check if `.ll/ll-config.json` already exists:

- If it exists and `--force` was NOT provided:
  - Display warning: "Configuration already exists at .ll/ll-config.json"
  - Suggest: "Use --force to overwrite, or edit the existing file directly"
  - **Stop here** - do not proceed

- If it exists and `--force` WAS provided:
  - Display notice: "Overwriting existing configuration"
  - Continue with initialization

### 3. Detect Project Type

Read all project-type template JSON files from `templates/` (relative to the little-loops plugin directory), excluding `bug-sections.json`, `feat-sections.json`, `enh-sections.json`, and `ll-goals-template.md`. For each template, check `_meta.detect` patterns against files in the project root:

1. For each template file, read its `_meta.detect` array
2. Check if ANY listed indicator file exists in the project root
3. If `_meta.detect_exclude` is present, skip this template if any excluded file also exists
4. If `_meta.detect` is empty (e.g., `generic.json`), this is the fallback template
5. If multiple templates match, prefer the one without `priority: -1`

See [templates.md](templates.md) for the project-type template file table (9 templates and their detect-file indicators).

Also detect:
- **Project name**: Use the directory name
- **Source directory**: Look for `src/`, `lib/`, or `app/` directories

### 4. Generate Configuration

Read the matched template JSON file from Step 3. Extract the `project` and `scan` sections as the initial configuration presets. Also apply the `issues` section as the default issue tracking configuration.

Strip the `_meta` and `$schema` sections. Do NOT strip `product` — in `--yes` mode include `product.enabled: true`; in `--interactive` mode apply the Round 4 selection (include if opted in, omit if skipped).

### 5. Interactive Mode (if --interactive)

If `--interactive` flag is set, follow the interactive wizard flow in [interactive.md](interactive.md) which guides the user through 10–11 rounds of configuration questions, with a progress indicator shown at each step.

### 6. Display Summary

Render the bordered configuration summary, showing each configured section
and omitting sections per the conditional rules. See [templates.md](templates.md)
for the full configuration summary template (section layout and per-section
show/omit conditions).

### 7. Confirm and Create

If `--dry-run` flag IS set:
- Skip confirmation (no files will be written)

If `--interactive` flag IS set:
- Skip confirmation and proceed immediately (user has already approved settings through the interactive workflow)

If `--yes` flag IS set:
- Skip confirmation and proceed

Otherwise (neither `--interactive`, `--yes`, nor `--dry-run`):
- Ask: "Create .ll/ll-config.json with these settings? (y/n)"
- Wait for confirmation
- If user declines, abort without changes

### 7.5. Command Availability Check

**Skip this step if** `--yes` or `--dry-run` is set.

After the user confirms, run a **non-blocking** PATH check on the configured
tool commands (`test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`): extract and
dedupe each base command, `which` it, and warn for any not found. Always
proceed to Step 8 regardless of results. See [templates.md](templates.md) for
the full procedure and the source-field → suggested-skill warning mapping.

### 8. Write Configuration

**If `--dry-run` is set**, output a preview instead of writing files:

```
=== DRY RUN: /ll:init ===

--- Configuration Preview (.ll/ll-config.json) ---
{
  "$schema": "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/config-schema.json",
  "project": { ... },
  "issues": { ... },
  "scan": { ... }
}

--- Actions that would be taken ---
  [write]  .ll/ll-config.json
  [write]  .ll/ll-goals.md (from templates/ll-goals-template.md)  # Only if product enabled
  [write]  .ll/design-tokens/profiles/ (3 starter profiles)      # Only if design tokens enabled
  [mkdir]  {{config.issues.base_dir}}/{bugs,features,enhancements,completed,deferred}
  [update] .gitignore (add state file exclusions)
  [update] .claude/settings.local.json (add ll- CLI tool permissions)  # Only if opted in
  [write/update] .claude/CLAUDE.md (ll- CLI command documentation)      # Only if opted in
  [write]  .codex/hooks.json (Codex CLI hook adapter)            # Only if --codex enabled

=== END DRY RUN (no changes made) ===
```

Skip all Write, Edit, and Bash(mkdir) tool calls. Skip Steps 9, 10, 11, and 12 — the dry-run output above replaces them.

**Otherwise**, proceed with normal file writes:

1. Create `.ll/` directory if it doesn't exist:
   ```bash
   mkdir -p .ll
   ```

2. Write the configuration file with the `$schema` reference (same JSON shape
   shown in the dry-run preview above: `$schema`, `project`, `issues`, `scan`).

3. Only include sections with non-default values to keep the file minimal.
   Always write the `learning_tests`, `analytics`, and `history` (session_digest)
   sections to record the explicit Round 8 / Round 9 / Round 9.5 choices
   (`enabled: true`/`false`; analytics includes its full `capture` sub-object
   when enabled; history includes `session_digest` with `enabled`, `days`, and
   `char_cap` when enabled). Omit `parallel`, `context_monitor`, `sync`,
   `product`, `documents`, `continuation`, and `prompt_optimization` when
   unconfigured or default. See [templates.md](templates.md) for the full
   per-section omit rules.

4. Create issue tracking directories:
   ```bash
   mkdir -p {{config.issues.base_dir}}/{bugs,features,enhancements,completed,deferred}
   ```

5. Deploy goals template if product is enabled:
   If `product.enabled: true` AND `.ll/ll-goals.md` does not already exist, read
   `templates/ll-goals-template.md` (plugin-relative) and write it to
   `.ll/ll-goals.md`. Skip silently if it already exists (never overwrite).
   Track outcome: `GOALS_FILE_CREATED=true`

6. Deploy design token profiles if design tokens are enabled (ENH-1768):
   If `design_tokens.enabled: true`, mirror `templates/design-tokens/profiles/`
   into `.ll/design-tokens/profiles/` and write `design_tokens.active` into the
   config. See [templates.md](templates.md) for the full procedure (starter
   profiles, per-profile files, skip/track rules).

7. Create learning-tests directory if learning tests are enabled (FEAT-1743):
   If `LEARNING_TESTS_ENABLED=true`, create `.ll/learning-tests/` (with a
   `.gitkeep`) and print the `learning_tests` next-steps hint. See
   [templates.md](templates.md) for the full procedure (mkdir, hint text,
   skip/track rules).

### 8.5. Install Codex CLI Hook Adapter (Conditional)

**Skip this step if** `$CODEX` is false.

If `--codex` was passed (or auto-detected via `which codex` / `.codex/`
directory), install the Codex CLI hook adapter from
`hooks/adapters/codex/hooks.json`, substituting the absolute plugin root for
`{{LL_PLUGIN_ROOT}}`, writing `.codex/hooks.json` (honoring `--dry-run` /
`--force` / existing-file skip), and printing the FEAT-957 trust-dialog
warning as the last line of the flow. Always proceed to Step 9. See
[templates.md](templates.md) for the full step-by-step procedure and the exact
trust-dialog warning text.

### 9. Update .gitignore

Add little-loops runtime state files to `.gitignore` (idempotently, only
appending entries not already present), creating the file if absent and
tracking whether it was created or updated for the completion message. See
[templates.md](templates.md) for the exact state-file entries and the
append/dedupe logic.

### 9.5. Hook Dependency Validation

**Skip this step if** `--dry-run` is set.

After config is written, validate that hook script runtime dependencies are available and the pip package is version-aligned with the plugin. This is a **non-blocking** check — display warnings but always proceed to Step 10.

Run the following checks via Bash:

1. **jq available** (required by all hook scripts):
   ```bash
   which jq 2>/dev/null
   ```
   If not found:
   ```
   Warning: 'jq' not found in PATH — Claude Code hook adapters (hooks/adapters/claude-code/*.sh, including session-start.sh and precompact.sh) will fail silently. Adapters parse the host JSON envelope with jq before invoking the Python handlers in little_loops.hooks; the LLHookIntentExtension dispatch path requires jq on the adapter side even though the handlers themselves are Python.
   Install: https://stedolan.github.io/jq/download/
   ```

2. **python3 available** (required by the SessionStart adapter and the `little_loops.hooks` Python handlers):
   ```bash
   which python3 2>/dev/null
   ```
   If not found:
   ```
   Warning: 'python3' not found in PATH — SessionStart adapter will fail silently
   ```

3. **pyyaml installed** (required by `little_loops.hooks.session_start` for `.ll/ll.local.md` frontmatter parsing):
   ```bash
   python3 -c "import yaml" 2>/dev/null
   ```
   If import fails:
   ```
   Warning: 'pyyaml' not installed — SessionStart config merge will fail silently
   Install: pip install pyyaml
   ```

4. **little_loops pip package installed and version-aligned**:
   ```bash
   python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null
   ```
   - If the command fails → warn: `'little-loops' pip package not installed — ll-* CLI tools unavailable. Install: pip install -e "./scripts"`
   - If installed → compare returned version against the `PLUGIN_VERSION` embedded in this skill (the `<!-- PLUGIN_VERSION: X.Y.Z -->` comment near the top, updated at each release alongside plugin.json, pyproject.toml, `__init__.py`, and CHANGELOG.md)
   - If versions differ:
     - Determine install command:
       ```bash
       [ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
       ```
     - If `$YES == true` (auto mode): run `$INSTALL_CMD` via Bash
       - On success: `✓ little-loops updated to A.B.C`
       - On failure: `Warning: pip package update failed — run manually: $INSTALL_CMD`
     - Otherwise (interactive mode): use `AskUserQuestion`:
       ```
       The installed little-loops package (X.Y.Z) is out of date (plugin: A.B.C).
       Update now?
       Options: Yes / No
       ```
       - If user confirms: run `$INSTALL_CMD`; report success/failure as above
       - If user declines: `Warning: pip package version mismatch — run: $INSTALL_CMD`
   - If versions match → no output (silent success)

**Always proceed to Step 10 regardless of results.**

### 10. Update Allowed Tools

Add ll- CLI command allow entries to Claude Code's settings file to pre-authorize them for agent use.

**If `--dry-run` is set, skip this step** (already shown in dry-run preview).

1. Detect which `.claude/settings.json` / `.claude/settings.local.json` files
   exist and choose the target file (`--yes` → `settings.local.json`;
   `--interactive` → Round 11 choice; otherwise `AskUserQuestion` per the
   exist/skip branches). If the user chose "Skip", proceed to Step 11 without
   changes. See [templates.md](templates.md) for the detection snippet and the
   full AskUserQuestion branch wording.

2. Perform merge into the chosen target file:
   - Read target file, or start with `{"permissions": {"allow": [], "deny": []}}` if absent
   - Remove all existing entries starting with `Bash(ll-` from `permissions.allow` (idempotency)
   - Remove any existing `Write(.ll/ll-continue-prompt.md)` entry from `permissions.allow` (idempotency)
   - Append the canonical allow entries:
     ```json
     "Bash(ll-action:*)",
     "Bash(ll-issues:*)",
     "Bash(ll-auto:*)",
     "Bash(ll-parallel:*)",
     "Bash(ll-sprint:*)",
     "Bash(ll-loop:*)",
     "Bash(ll-workflows:*)",
     "Bash(ll-messages:*)",
     "Bash(ll-history:*)",
     "Bash(ll-history-context:*)",
     "Bash(ll-deps:*)",
     "Bash(ll-sync:*)",
     "Bash(ll-verify-docs:*)",
     "Bash(ll-verify-skills:*)",
     "Bash(ll-check-links:*)",
     "Bash(ll-gitignore:*)",
     "Bash(ll-create-extension:*)",
     "Bash(ll-learning-tests:*)",
     "Bash(ll-logs:*)",
     "Bash(ll-session:*)",
     "Bash(ll-doctor:*)",
     "Bash(ll-ctx-stats:*)",
     "Bash(ll-adapt-skills-for-codex:*)",
     "Bash(ll-adapt-agents-for-codex:*)",
     "Bash(ll-harness:*)",
     "Write(.ll/ll-continue-prompt.md)"
     ```
   - **If `LEARNING_TESTS_ENABLED=true`**, also append `"Skill(ll:explore-api)"` to the allow list after the canonical entries, before `"Write(.ll/ll-continue-prompt.md)"`:
     ```json
     "Skill(ll:explore-api)"
     ```
   - Create `.claude/` directory first if needed
   - Write result back with 2-space indent, preserving all top-level keys (`$schema`, `env`, etc.)

**Always proceed to Step 10.5 regardless of results.**

### 10.5. Hooks Note

ll plugin hooks fire automatically when `ll@little-loops` is globally enabled in `~/.claude/settings.json`. The plugin's own `hooks/hooks.json` handles all hook events with correct `${CLAUDE_PLUGIN_ROOT}` resolution — no manual installation into project settings files is needed or correct.

To verify hooks are active after init: `/ll:configure hooks show`

**Always proceed to Step 11.**

### 11. Update CLAUDE.md

Add ll- CLI command documentation to the target project's `CLAUDE.md`.

**If `--dry-run` is set, skip this step** (already shown in dry-run preview).

**If `--interactive` mode**: use the answer recorded in Round 12 (`CLAUDE_MD_ANSWER`). If the user chose "Skip", proceed to Step 12 without changes.

**Otherwise**: skip this step (Step 11 only runs in interactive mode).

If user opted in:

1. Detect existing file (reuse detection from Round 12, or re-detect):
   ```bash
   CLAUDE_MD_EXISTS=false
   CLAUDE_MD_PATH=""
   [ -f ".claude/CLAUDE.md" ] && CLAUDE_MD_EXISTS=true && CLAUDE_MD_PATH=".claude/CLAUDE.md"
   [ "$CLAUDE_MD_EXISTS" = false ] && [ -f "CLAUDE.md" ] && CLAUDE_MD_EXISTS=true && CLAUDE_MD_PATH="CLAUDE.md"
   ```

2. **Duplicate guard** (if file exists): check whether a `## little-loops` section is already present:
   - Read existing file content
   - If the string `## little-loops` is found anywhere in the file, skip writing (already documented) and log: `Skipped: CLAUDE.md already contains a ## little-loops section`
   - Otherwise, proceed to append

3. **If file exists and no duplicate**: append the commands section:
   ```markdown

   ## little-loops CLI Commands

   - `ll-action` - Invoke ll skills as one-shot commands with JSON-structured output
   - `ll-harness` - One-shot runner evaluation (skill, cmd, mcp, prompt) with exit-code and semantic criteria
   - `ll-auto` - Process all backlog issues sequentially in priority order
   - `ll-parallel` - Process issues concurrently using isolated git worktrees
   - `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
   - `ll-loop` - Execute FSM-based automation loops
   - `ll-workflows` - Identify multi-step workflow patterns from user message history
   - `ll-messages` - Extract user messages from Claude Code logs
   - `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
   - `ll-history-context` - Render a `## Historical Context` block for an issue from `.ll/history.db`
   - `ll-deps` - Cross-issue dependency analysis and validation
   - `ll-sync` - Sync local issues with GitHub Issues
   - `ll-verify-docs` - Verify documented counts match actual file counts
   - `ll-verify-skills` - Check that no SKILL.md exceeds 500 lines
   - `ll-check-links` - Check markdown documentation for broken links
   - `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, set-status, anchor-sweep, fingerprint, epic-progress, decisions)
   - `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files
   - `ll-create-extension` - Scaffold a new little-loops extension project
   - `ll-generate-schemas` - Regenerate JSON Schema files for all LLEvent types (maintainer tool)
   - `ll-learning-tests` - Query and manage the learning test registry (check/list/mark-stale)
   - `ll-logs` - Discover, extract, and analyze (sequences, scan-failures) ll-relevant log entries from Claude project logs
   - `ll-doctor` - Check host CLI capability support for little-loops features
   - `ll-ctx-stats` - Show context-window analytics for the current project (per-tool byte vs. context savings)
   - `ll-adapt-skills-for-codex` - Add Codex Skills API frontmatter to skills and bridge commands for Codex discovery
   - `ll-adapt-agents-for-codex` - Generate `.codex/agents/*.toml` from `agents/*.md` for Codex agent-select support

   Install: `pip install -e "./scripts[dev]"`
   ```
   Track outcome: `CLAUDE_MD_UPDATED=true`

4. **If no file exists**: create `.claude/` directory if needed, then write `.claude/CLAUDE.md`:
   ```markdown
   # Project Configuration

   ## little-loops CLI Commands

   - `ll-action` - Invoke ll skills as one-shot commands with JSON-structured output
   - `ll-harness` - One-shot runner evaluation (skill, cmd, mcp, prompt) with exit-code and semantic criteria
   - `ll-auto` - Process all backlog issues sequentially in priority order
   - `ll-parallel` - Process issues concurrently using isolated git worktrees
   - `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
   - `ll-loop` - Execute FSM-based automation loops
   - `ll-workflows` - Identify multi-step workflow patterns from user message history
   - `ll-messages` - Extract user messages from Claude Code logs
   - `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
   - `ll-history-context` - Render a `## Historical Context` block for an issue from `.ll/history.db`
   - `ll-deps` - Cross-issue dependency analysis and validation
   - `ll-sync` - Sync local issues with GitHub Issues
   - `ll-verify-docs` - Verify documented counts match actual file counts
   - `ll-verify-skills` - Check that no SKILL.md exceeds 500 lines
   - `ll-check-links` - Check markdown documentation for broken links
   - `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, set-status, anchor-sweep, fingerprint, epic-progress, decisions)
   - `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files
   - `ll-create-extension` - Scaffold a new little-loops extension project
   - `ll-generate-schemas` - Regenerate JSON Schema files for all LLEvent types (maintainer tool)
   - `ll-learning-tests` - Query and manage the learning test registry (check/list/mark-stale)
   - `ll-logs` - Discover, extract, and analyze (sequences, scan-failures) ll-relevant log entries from Claude project logs
   - `ll-doctor` - Check host CLI capability support for little-loops features
   - `ll-ctx-stats` - Show context-window analytics for the current project (per-tool byte vs. context savings)
   - `ll-adapt-skills-for-codex` - Add Codex Skills API frontmatter to skills and bridge commands for Codex discovery
   - `ll-adapt-agents-for-codex` - Generate `.codex/agents/*.toml` from `agents/*.md` for Codex agent-select support

   Install: `pip install -e "./scripts[dev]"`
   ```
   Track outcome: `CLAUDE_MD_CREATED=true`

### 12. Display Completion Message

```
================================================================================
INITIALIZATION COMPLETE
================================================================================

Created: .ll/ll-config.json
Created: .ll/ll-goals.md (product goals template)  # Only show if product enabled
Created: .ll/design-tokens/profiles/{default,editorial-mono,warm-paper}/ (3 starter profiles)  # Only show if DESIGN_TOKENS_CREATED=true
Created: .ll/learning-tests/.gitkeep (learning test registry)  # Only show if LEARNING_TESTS_DIR_CREATED=true
Created: {{config.issues.base_dir}}/{bugs,features,enhancements,completed,deferred}
Updated: .gitignore (added state file exclusions)
Updated: .claude/settings.local.json (added ll- CLI tool permissions)  # Only show if user opted in
Created: .claude/CLAUDE.md (ll- CLI command documentation)             # Only show if CLAUDE_MD_CREATED=true
Updated: .claude/CLAUDE.md (appended ## little-loops CLI Commands)     # Only show if CLAUDE_MD_UPDATED=true
Created: .codex/hooks.json (Codex CLI hook adapter)                    # Only show if CODEX_HOOKS_INSTALLED=true

Next steps:
  1. Review and customize: .ll/ll-config.json
  2. Try a command: /ll:check-code
  3. Configure product goals: .ll/ll-goals.md      # Only show if product enabled
  4. Run parallel processing: ll-parallel      # Only show if parallel configured
  5. Record your first learning test: /ll:explore-api <api-name>  # Only show if LEARNING_TESTS_DIR_CREATED=true
  6. Sync with GitHub: /ll:sync-issues push   # Only show if sync enabled
  7. Run sprint processing: ll-sprint run [sprint-file]   # Only show if sprint management selected
  8. Run FSM loop: ll-loop run [loop-file]               # Only show if FSM loops selected
  9. Run sequential automation: ll-auto                  # Only show if sequential automation selected

Additional settings for sprints, loops, and automation can be customized via:
  /ll:configure                                          # Only show if any automation feature selected

Documentation: https://github.com/BrennonTWilliams/little-loops

================================================================================
```

## Additional Resources

- For reference tables, output templates, and example `/ll:init` invocations covering all flag combinations, see [templates.md](templates.md)
- For interactive wizard question flows, see [interactive.md](interactive.md)
- For project type configuration presets, see `templates/*.json` (relative to the little-loops plugin directory)
