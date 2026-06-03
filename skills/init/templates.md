# init — Reference Templates

Reference tables, verbatim output templates, and example invocations extracted
from [SKILL.md](SKILL.md) to keep the main skill body focused. Each section is
referenced from the corresponding step in SKILL.md.

## Valid Flag Combinations

| Combination | Behavior |
|-------------|----------|
| `--interactive` | Full guided wizard |
| `--yes` | Accept all defaults, no confirmation |
| `--force` | Overwrite existing config |
| `--dry-run` | Preview config without writing files |
| `--interactive --force` | Full wizard, allow overwriting existing config |
| `--yes --force` | Accept defaults, overwrite existing config |
| `--dry-run --force` | Preview what overwrite would produce |
| `--codex` | Install the Codex CLI hook adapter (in addition to the default Claude Code wiring) |
| `--codex --dry-run` | Preview the Codex hook adapter that would be written, without touching `.codex/` |
| `--interactive --yes` | **Error** — mutually exclusive |

## Project-Type Template Files (Step 3)

9 project-type templates live under `templates/` (relative to the little-loops
plugin directory):

| Template File | Detect Files | Notes |
|---------------|-------------|-------|
| `python-generic.json` | `pyproject.toml`, `setup.py`, `requirements.txt` | |
| `typescript.json` | `tsconfig.json` | |
| `javascript.json` | `package.json` | exclude: `tsconfig.json` |
| `go.json` | `go.mod` | |
| `rust.json` | `Cargo.toml` | |
| `java-maven.json` | `pom.xml` | |
| `java-gradle.json` | `build.gradle`, `build.gradle.kts` | |
| `dotnet.json` | `*.csproj`, `*.sln`, `*.fsproj` | |
| `generic.json` | _(none — fallback)_ | `priority: -1` |

## Configuration Summary Template (Step 6)

```
================================================================================
LITTLE-LOOPS INITIALIZATION
================================================================================

Detected project type: [TYPE]

Configuration Summary:

  [PROJECT]
  project.name:       [name]
  project.src_dir:    [src_dir]
  project.test_dir:   [test_dir]                # Only show if configured
  project.test_cmd:   [test_cmd]
  project.lint_cmd:   [lint_cmd]
  project.type_cmd:   [type_cmd]
  project.format_cmd: [format_cmd]
  project.build_cmd:  [build_cmd]               # Only show if configured
  project.run_cmd:    [run_cmd]                  # Only show if configured

  [ISSUES]
  issues.base_dir:    [base_dir]

  [SCAN]
  scan.focus_dirs:    [focus_dirs]
  scan.exclude_patterns: [exclude_patterns]

  [PARALLEL]                              # Only show if configured
  parallel.max_workers: [workers]          # Only show if non-default (not 2)
  parallel.timeout_per_issue: [seconds]    # Only show if non-default (not 3600)
  parallel.worktree_copy_files: [files]

  [CONTEXT MONITOR]                       # Only show if enabled
  context_monitor.enabled: true
  context_monitor.auto_handoff_threshold: [threshold]  # Only if non-default

  [SYNC]                                  # Only show if enabled
  sync.enabled: true
  sync.github.priority_labels: [true/false]    # Only if non-default
  sync.github.sync_completed: [true/false]     # Only if non-default

  [COMMANDS]                              # Only show if pre/post implement configured in Round 8
  commands.pre_implement: [command]        # Only show if configured
  commands.post_implement: [command]       # Only show if configured

  [SPRINTS]                               # Only show if "Sprint management" selected in Round 3b
  sprints.default_max_workers: [workers]  # Only if non-default (not 2)

  [LOOPS]                                 # Only show if "FSM loops" selected in Round 3b
  loops.loops_dir: .loops                 # Always .loops (default)

  [AUTOMATION]                            # Only show if "Sequential automation" selected in Round 3b
  automation.timeout_seconds: [seconds]   # Only if non-default (not 3600)

  [PRODUCT]                               # Only show if enabled
  product.enabled: true
  product.goals_file: .ll/ll-goals.md

  [DOCUMENTS]                             # Only show if enabled
  documents.enabled: true
  documents.categories: [architecture, product]  # List category names

  [LEARNING TESTS]                        # Only show if enabled
  learning_tests.enabled: true
  learning_tests.stale_after_days: [days]

  [ANALYTICS]                             # Only show if enabled
  analytics.enabled: true

  [CONTINUATION]                          # Only show if configured (non-defaults)
  continuation.prompt_expiry_hours: [hours]

  [PROMPT OPTIMIZATION]                   # Only show if configured (non-defaults)
  prompt_optimization.enabled: [true/false]
  prompt_optimization.mode: [quick/thorough]
  prompt_optimization.confirm: [true/false]

================================================================================
```

## Command Availability Check (Step 7.5)

**Skip this step if** `--yes` or `--dry-run` is set.

After the user confirms, check whether the configured tool commands are available in PATH. This is a **non-blocking** check — display warnings but always proceed to Step 8.

1. Collect configured command values: `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`
2. For each non-null command, extract the **base command** (first word). For example:
   - `ruff check .` → `ruff`
   - `python -m pytest` → `python`
   - `go test ./...` → `go`
3. **Deduplicate** base commands (e.g., if `ruff` is used for both lint and format, check it only once)
4. For each unique base command, run via Bash:
   ```bash
   which <base_command> 2>/dev/null
   ```
5. For any command **not found**, display a warning:
   ```
   Warning: '<base_command>' not found in PATH — install it before running /ll:check-code
   ```

   Use this mapping for the warning message:
   | Source field | Suggested skill |
   |-------------|----------------|
   | `test_cmd` | `/ll:run-tests` |
   | `lint_cmd` | `/ll:check-code` |
   | `type_cmd` | `/ll:check-code` |
   | `format_cmd` | `/ll:check-code` |

   If a base command is shared across multiple fields, mention the first matching skill only.

6. **Always proceed** to Step 8 regardless of results.

## Codex CLI Hook Adapter Install (Step 8.5)

**Skip this step if** `$CODEX` is false.

If `--codex` was passed (or auto-detected via `which codex` / `.codex/`
directory), install the Codex CLI hook adapter:

1. **Locate the adapter template**: read
   `hooks/adapters/codex/hooks.json` from the little-loops plugin directory
   (relative to `${CLAUDE_PLUGIN_ROOT}` if set, otherwise the plugin install
   path resolved by the Read tool).

2. **Substitute the plugin root**: replace the literal placeholder
   `{{LL_PLUGIN_ROOT}}` in the template with the **absolute** path of the
   installed little-loops plugin (the directory containing
   `hooks/adapters/codex/`). Use an absolute path so that hooks fire
   correctly regardless of the user's working directory at session start
   and so that the Codex trust-hash for the command string remains stable
   across invocations.

3. **Write `.codex/hooks.json`**:
   - **If `--dry-run` is set**: include the rendered JSON in the dry-run
     preview block under a `--- Codex Adapter Preview (.codex/hooks.json) ---`
     header and list `[write] .codex/hooks.json` in the actions block. Do
     not create the directory or write the file.
   - **Otherwise**:
     - `mkdir -p .codex`
     - If `.codex/hooks.json` already exists and `--force` was NOT passed:
       skip with a warning: `Skipped: .codex/hooks.json already exists — use --force to overwrite`
     - Otherwise: write the rendered JSON to `.codex/hooks.json`
     - Track outcome: `CODEX_HOOKS_INSTALLED=true`

4. **Print the trust-dialog warning** as the **last** line of the init
   flow (after the completion summary in Step 12, but as a distinct
   `[Codex]` line so it is not missed):

   ```
   [Codex] .codex/hooks.json written. Codex will show a hook-trust dialog
   on next session start — choose "Trust All" (or "Review Hooks"). Until
   you do, little-loops hooks will not fire (Codex silently skips
   untrusted hooks).
   ```

   This warning is **required** by FEAT-957's trust-model UX policy:
   untrusted hooks are silently skipped (`HookRunStatus::Untrusted`) with
   no error and no stderr, which is the worst failure mode. The one-line
   warning at install time prevents the support load.

**Always proceed to Step 9 regardless of results.**

## Settings File Detection & Target Selection (Step 10)

1. Check which settings files exist:

   ```bash
   SETTINGS_JSON_EXISTS=false
   SETTINGS_LOCAL_EXISTS=false
   [ -f ".claude/settings.json" ] && SETTINGS_JSON_EXISTS=true
   [ -f ".claude/settings.local.json" ] && SETTINGS_LOCAL_EXISTS=true
   ```

2. Determine target file:
   - **`--yes` mode**: use `.claude/settings.local.json` (create if absent) without prompting
   - **`--interactive` mode**: use the choice recorded in Round 11 of the wizard
   - **Otherwise**, use `AskUserQuestion` inline:
     - If *neither* exists → ask: "Create `.claude/settings.local.json` (Recommended), `.claude/settings.json`, or Skip?"
     - If only `settings.local.json` exists → ask: "Update `.claude/settings.local.json` with ll- entries? (y/Skip)"
     - If only `settings.json` exists → ask: "Update `.claude/settings.json` with ll- entries, create `settings.local.json`, or Skip?"
     - If *both* exist → ask: "Update `settings.local.json` (Recommended), `settings.json`, or Skip?"

3. If user chose "Skip", proceed to Step 11 without changes.

## Per-Section Omit Rules (Step 8, sub-step 3)

Only include sections with non-default values to keep the config file minimal:

- Omit `parallel` section entirely if not configured in interactive mode
- Omit `context_monitor` section if user selected "No" (disabled is the default)
- Omit `sync` section entirely if user did not select "GitHub sync" (disabled is the default)
- Omit `product` section if user selected "No, skip" (disabled is the default)
- Omit `documents` section if user selected "Skip" (disabled is the default)
- Include `learning_tests` section with `enabled: true` or `enabled: false` based on Round 8 selection (always write this section to record the explicit choice)
- Include `analytics` section with `enabled: true` and full `capture` sub-object, or `enabled: false`, based on Round 9 selection (always write this section to record the explicit choice)
- Omit `continuation` section if all values match schema defaults
- Omit `prompt_optimization` section if all values match schema defaults

## Deploy Design Token Profiles (Step 8, sub-step 6 — ENH-1768)

If `design_tokens.enabled: true` in the config AND `.ll/design-tokens/profiles/`
does not already exist:

- Mirror the full `templates/design-tokens/profiles/` tree into
  `.ll/design-tokens/profiles/`. Three starter profiles ship: `default`,
  `editorial-mono`, `warm-paper`. Each profile directory contains six files:
  `primitives.json`, `semantic.json`, `typography.json`, `spacing.json`,
  `themes/light.json`, `themes/dark.json`.
- Write `design_tokens.active: <chosen-profile-name>` into the config (default
  is `"default"`; in `--interactive` mode the Round 7 profile picker selects the
  value).

Skip silently if `.ll/design-tokens/profiles/` already exists (never overwrite).
Track outcome: `DESIGN_TOKENS_CREATED=true`

## Create Learning-Tests Directory (Step 8, sub-step 7 — FEAT-1743)

If `LEARNING_TESTS_ENABLED=true` AND `.ll/learning-tests/` does not already
exist:

- Create `.ll/learning-tests/` directory:
  ```bash
  mkdir -p .ll/learning-tests
  ```
- Create `.ll/learning-tests/.gitkeep`: write an empty file to
  `.ll/learning-tests/.gitkeep`
- Print next steps hint: *"Run `/ll:explore-api <api-name>` to record your first
  proof, or run `proof-first-task` instead of `general-task` for any issue that
  touches a third-party API."*

Skip silently if `.ll/learning-tests/` already exists (never overwrite).
Track outcome: `LEARNING_TESTS_DIR_CREATED=true`

## .gitignore State Entries (Step 9)

Add little-loops state files to `.gitignore` to prevent committing runtime state:

1. Check if `.gitignore` exists at project root
2. If it doesn't exist, create it with the entries below
3. If it exists, check if entries are already present (to avoid duplicates)
4. Append the following if not already present:

```
# little-loops state files
.auto-manage-state.json
.parallel-manage-state.json
.ll/ll-context-state.json
.ll/ll-sync-state.json
```

**Logic:**
- Read existing `.gitignore` content (if file exists)
- Only add entries that aren't already present (exact line match)
- Add a blank line before the comment header if appending to existing content
- Track whether the file was created or updated for the completion message

## Examples

```bash
# Initialize with smart defaults (detect project type, confirm)
/ll:init

# Initialize with full interactive wizard
/ll:init --interactive

# Initialize accepting all defaults without confirmation
/ll:init --yes

# Overwrite existing configuration
/ll:init --force

# Preview what init would generate without writing files
/ll:init --dry-run

# Combine flags
/ll:init --yes --force
/ll:init --interactive --force
/ll:init --dry-run --force

# Install Codex CLI hook adapter alongside default config
/ll:init --codex
/ll:init --yes --codex
/ll:init --codex --dry-run

# Invalid: --interactive and --yes are mutually exclusive
# /ll:init --interactive --yes  → Error
```
