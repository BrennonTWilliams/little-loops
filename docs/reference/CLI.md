# CLI Tools Reference

Complete reference for all `ll-` command-line tools. Install from PyPI:

```bash
pip install little-loops
```

See [COMMANDS.md](COMMANDS.md) for `/ll:` slash commands and [README](../../README.md) for overview.

## Common Flags

These flags appear across multiple tools:

| Flag | Short | Behavior | Used by |
|------|-------|----------|---------|
| `--dry-run` | `-n` | Show what would happen without making changes | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-deps fix`, `ll-sync` |
| `--resume` | `-r` | Resume from previous checkpoint | `ll-auto`, `ll-parallel`, `ll-sprint run` |
| `--max-issues` | `-m` | Limit number of issues to process (0 = unlimited) | `ll-auto`, `ll-parallel` |
| `--quiet` | `-q` | Suppress non-essential output | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-sync` |
| `--only` | | Comma-separated issue IDs to process exclusively | `ll-auto`, `ll-parallel` |
| `--skip` | | Comma-separated issue IDs to exclude | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--type` | | Comma-separated issue types: `BUG`, `FEAT`, `ENH` | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--config` | | Path to project root (default: current directory) | `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-sync` |
| `--timeout` | `-t` | Timeout in seconds per issue | `ll-parallel`, `ll-sprint run` |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100, default: from config) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--context-limit` | | Override context window token estimate (default: from config or model-detected) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--format` | `-f` | Output format: `text`, `json`, `markdown` | `ll-history`, `ll-deps`, `ll-sprint analyze`, `ll-verify-docs`, `ll-check-links` |

---

## Issue Processing

### ll-auto

Process all backlog issues sequentially in priority order.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--resume` | `-r` | Resume from previous checkpoint |
| `--dry-run` | `-n` | Show what would be processed without running |
| `--max-issues` | `-m` | Limit number of issues (0 = unlimited) |
| `--quiet` | `-q` | Suppress non-essential output |
| `--only` | | Process only these issue IDs (comma-separated) |
| `--skip` | | Skip these issue IDs (comma-separated) |
| `--type` | | Process only these types: `BUG`, `FEAT`, `ENH` |
| `--config` | | Path to project root |
| `--category` | `-c` | Filter to category: `bugs`, `features`, `enhancements` |
| `--priority` | `-p` | Comma-separated priority levels to process (e.g., `P1,P2`) |
| `--idle-timeout` | | Kill worker if no output for N seconds (0 to disable) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

**Examples:**
```bash
ll-auto                          # Process all issues in priority order
ll-auto --max-issues 5           # Process at most 5 issues
ll-auto --resume                 # Resume from previous state
ll-auto --dry-run                # Preview what would be processed
ll-auto --category bugs          # Only process bugs
ll-auto --only BUG-001,BUG-002   # Process only specific issues
ll-auto --skip BUG-003           # Skip a specific issue
ll-auto --type BUG               # Process only bugs
ll-auto --type BUG,ENH           # Process bugs and enhancements
ll-auto --priority P1,P2         # Only process P1 and P2 issues
ll-auto --handoff-threshold 90   # Trigger handoff at 90% context usage
```

---

### ll-parallel

Process issues concurrently using isolated git worktrees.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--workers` | `-w` | Number of parallel workers (default: from config or 2) |
| `--priority` | `-p` | Comma-separated priorities to process (e.g., `P1,P2`) |
| `--worktree-base` | | Base directory for git worktrees |
| `--cleanup` | `-c` | Clean up all worktrees and exit |
| `--merge-pending` | | Attempt to merge pending work from interrupted runs |
| `--clean-start` | | Remove all worktrees and start fresh |
| `--ignore-pending` | | Report pending work but continue without merging |
| `--stream-output` | | Stream Claude CLI subprocess output to console |
| `--show-model` | | Verify and display model on worktree setup |
| `--overlap-detection` | | Enable pre-flight overlap detection to reduce merge conflicts |
| `--warn-only` | | With `--overlap-detection`, warn instead of serializing |
| `--dry-run` | `-n` | Show what would be processed |
| `--resume` | `-r` | Resume from previous checkpoint |
| `--timeout` | `-t` | Timeout in seconds per issue |
| `--quiet` | `-q` | Suppress non-essential output |
| `--only` | | Process only these issue IDs |
| `--skip` | | Skip these issue IDs |
| `--type` | | Process only these types: `BUG`, `FEAT`, `ENH` |
| `--max-issues` | `-m` | Limit total issues processed |
| `--config` | | Path to project root |
| `--idle-timeout` | | Kill worker if no output for N seconds (0 to disable) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

**Examples:**
```bash
ll-parallel                         # Process with default workers
ll-parallel --workers 3             # Use 3 parallel workers
ll-parallel --dry-run               # Preview what would be processed
ll-parallel --priority P1,P2        # Only process P1 and P2 issues
ll-parallel --cleanup               # Clean up worktrees and exit
ll-parallel --stream-output         # Stream Claude output in real-time
ll-parallel --only BUG-001,BUG-002  # Process only specific issues
ll-parallel --type BUG,ENH          # Process bugs and enhancements
ll-parallel --overlap-detection     # Reduce merge conflicts
ll-parallel --handoff-threshold 85  # Override handoff threshold for this run
```

---

### ll-sprint

Define and execute curated issue sets with dependency-aware ordering.

**Subcommands:**

#### `ll-sprint create <name>`

Create a new sprint.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `name` | | Sprint name (used as filename) |
| `--issues` | | **Required.** Comma-separated issue IDs |
| `--description` | `-d` | Sprint description |
| `--max-workers` | `-w` | Max parallel workers (default: 2) |
| `--timeout` | `-t` | Timeout per issue in seconds (default: 3600) |
| `--skip` | | Issue IDs to exclude |
| `--type` | | Filter by type: `BUG`, `FEAT`, `ENH` |

#### `ll-sprint run <sprint>` / `ll-sprint r <sprint>`

Execute a sprint.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `sprint` | | Sprint name to execute |
| `--dry-run` | `-n` | Show plan without running |
| `--max-workers` | `-w` | Max parallel workers |
| `--timeout` | `-t` | Timeout per issue in seconds |
| `--config` | | Path to project root |
| `--resume` | `-r` | Resume interrupted sprint |
| `--quiet` | `-q` | Suppress non-essential output |
| `--skip` | | Issue IDs to skip during execution |
| `--skip-analysis` | | Skip dependency analysis |
| `--type` | | Filter by type |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

#### `ll-sprint list` / `ll-sprint l`

List all sprints.

| Flag | Short | Description |
|------|-------|-------------|
| `--verbose` | `-v` | Show detailed information |
| `--json` | | Output as JSON array |

#### `ll-sprint show <sprint>` / `ll-sprint s <sprint>`

Show sprint details, dependency graph, and health summary.

| Argument/Flag | Description |
|---------------|-------------|
| `sprint` | Sprint name |
| `--config` | Path to project root |
| `--skip-analysis` | Skip dependency analysis |

#### `ll-sprint edit <sprint>` / `ll-sprint e <sprint>`

Edit a sprint's issue list.

| Argument/Flag | Description |
|---------------|-------------|
| `sprint` | Sprint name |
| `--add` | Comma-separated issue IDs to add |
| `--remove` | Comma-separated issue IDs to remove |
| `--prune` | Remove invalid/completed issue references |
| `--revalidate` | Re-run dependency analysis after edits |
| `--config` | Path to project root |

#### `ll-sprint delete <sprint>` / `ll-sprint del <sprint>`

Delete a sprint definition.

#### `ll-sprint analyze <sprint>` / `ll-sprint a <sprint>`

Analyze sprint for file conflicts between issues.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `sprint` | | Sprint name |
| `--format` | `-f` | Output format: `text` (default), `json` |
| `--config` | | Path to project root |

**Examples:**
```bash
ll-sprint create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
ll-sprint run sprint-1
ll-sprint run sprint-1 --dry-run
ll-sprint list
ll-sprint list --json                         # JSON array of all sprints
ll-sprint show sprint-1
ll-sprint edit sprint-1 --add BUG-045,ENH-050
ll-sprint edit sprint-1 --remove BUG-001
ll-sprint edit sprint-1 --prune
ll-sprint delete sprint-1
ll-sprint analyze sprint-1 --format json
```

---

## Loop Automation

### ll-loop

Execute FSM-based automation loops. If the first argument is a loop name (not a subcommand), `run` is inferred automatically.

**Subcommands:**

#### `ll-loop run <loop>` / `ll-loop r <loop>`

Run a loop.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `loop` | | Loop name or path |
| `input` | | (Optional positional) Input string injected as `context['input']` (or the key declared in `input_key`) |
| `--max-iterations` | `-n` | Override iteration limit |
| `--delay` | | Sleep N seconds between iterations (useful for recording) |
| `--no-llm` | | Disable LLM evaluation |
| `--llm-model` | | Override LLM model |
| `--dry-run` | | Show execution plan without running |
| `--background` | `-b` | Run as background daemon |
| `--quiet` | `-q` | Suppress progress output |
| `--verbose` | `-v` | Show full prompt text and more output lines |
| `--queue` | | Wait for conflicting loops to finish |
| `--show-diagrams` | | Display FSM box diagram with active state highlighted after each step |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty) |
| `--builtin` | | Load loop from built-ins directory (bypasses project `.loops/` lookup) |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

#### `ll-loop validate <loop>` / `ll-loop val <loop>`

Validate a loop definition file.

#### `ll-loop list` / `ll-loop l`

List available loops.

| Flag | Description |
|------|-------------|
| `--running` | Only show currently running loops |
| `--json` | Output as JSON array |

#### `ll-loop status <loop>` / `ll-loop st <loop>`

Show current status of a loop.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output loop state as JSON |

#### `ll-loop stop <loop>`

Stop a running loop.

#### `ll-loop resume <loop>` / `ll-loop res <loop>`

Resume an interrupted loop.

| Flag | Short | Description |
|------|-------|-------------|
| `--background` | `-b` | Resume as a detached background process |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--show-diagrams` | | Display FSM box diagram with active state highlighted after each step |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty) |
| `--delay` | | Sleep N seconds between iterations (useful for recording) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

#### `ll-loop history <loop>` / `ll-loop h <loop>`

Show execution history for a loop.

| Flag | Short | Description |
|------|-------|-------------|
| `run_id` | | (Optional positional) Archived run ID to inspect; omit to list all archived runs |
| `--tail` | `-n` | Last N events to show (default: 50) |
| `--verbose` | `-v` | Show action output preview and LLM call details (model, latency, prompt, response) |
| `--full` | | Show untruncated prompts and output (implies `--verbose`) |
| `--json` | | Output events as JSON array |

#### `ll-loop test <loop>` / `ll-loop t <loop>`

Run a single test iteration to verify loop configuration.

#### `ll-loop simulate <loop>` / `ll-loop sim <loop>`

Trace loop execution interactively without running commands.

| Flag | Short | Description |
|------|-------|-------------|
| `--scenario` | | Auto-select results: `all-pass`, `all-fail`, `first-fail`, `alternating` |
| `--max-iterations` | `-n` | Override max iterations (default: min of loop config or 20) |

#### `ll-loop install <loop>`

Copy a built-in loop to `.loops/` for customization.

#### `ll-loop show <loop>` / `ll-loop s <loop>`

Show loop details and FSM structure.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output FSM config as JSON |

**Examples:**
```bash
ll-loop fix-types                     # Run loop (shorthand for run)
ll-loop run fix-types --dry-run       # Show execution plan
ll-loop validate fix-types            # Validate loop definition
ll-loop test fix-types                # Run single test iteration
ll-loop simulate fix-types            # Interactive simulation
ll-loop simulate fix-types --scenario all-pass
ll-loop list                          # List available loops
ll-loop list --running                # List running loops
ll-loop list --json                   # JSON array of available loops
ll-loop status fix-types              # Show loop status
ll-loop status fix-types --json       # Loop state as JSON
ll-loop stop fix-types                # Stop a running loop
ll-loop resume fix-types              # Resume interrupted loop
ll-loop history fix-types             # Show execution history
ll-loop history fix-types --tail 20   # Last 20 events
ll-loop history fix-types --verbose   # Include LLM call details
ll-loop history fix-types --full      # Untruncated output
ll-loop history fix-types --json      # JSON output
ll-loop history fix-types <run_id>    # Inspect a specific archived run
ll-loop install fix-types             # Install built-in loop
ll-loop show fix-types                # Show loop details
ll-loop show fix-types --json         # FSM config as JSON
```

See [LOOPS_GUIDE](../guides/LOOPS_GUIDE.md) for loop configuration details.

---

## Issue Management

### ll-issues

Issue management and visualization utilities.

**Subcommands:**

#### `ll-issues next-id` / `ll-issues ni`

Print the next globally unique issue number across all types.

#### `ll-issues list` / `ll-issues l`

List active issues with optional filters.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` |
| `--priority` | Filter by priority: `P0`–`P5` |
| `--status` | Filter by status: `active` (default), `completed`, `deferred`, `all` |
| `--include-completed` | Include completed issues (alias for `--status all`) |
| `--flat` | Output flat list for scripting |
| `--json` | Output as JSON array |
| `--limit` / `-n` | Cap output at N issues (must be ≥ 1) |
| `--config` | Path to project root |

#### `ll-issues count` / `ll-issues c`

Count active issues. Outputs a single integer by default, or a JSON object with breakdowns.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` |
| `--priority` | Filter by priority: `P0`–`P5` |
| `--status` | Filter by status: `active` (default), `completed`, `deferred`, `all` |
| `--json` | Output JSON with `total`, `status`, `by_type`, and `by_priority` breakdowns |
| `--config` | Path to project root |

#### `ll-issues show <issue_id>` / `ll-issues s <issue_id>`

Show summary card for a single issue. Accepts short form (`518`), type-prefixed (`FEAT-518`), or full (`P3-FEAT-518`). Searches all active category directories, the completed directory, and the deferred directory.

| Flag | Description |
|------|-------------|
| `--json` | Output issue fields as JSON |

#### `ll-issues search [query]` / `ll-issues sr [query]`

Search issues with filters and sorting.

| Argument/Flag | Description |
|---------------|-------------|
| `query` | (Optional) Text to match against title and body (case-insensitive) |
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` (repeatable) |
| `--priority` | Filter by priority: `P0`–`P5` or range e.g. `P0-P2` (repeatable) |
| `--status` | Filter by status: `active` (default), `completed`, `deferred`, `all` |
| `--include-completed` | Include completed issues (alias for `--status all`) |
| `--label` | Filter by label tag (repeatable) |
| `--since` | Only issues on or after DATE (YYYY-MM-DD) |
| `--until` | Only issues on or before DATE (YYYY-MM-DD) |
| `--date-field` | Date field to filter on: `discovered` (default) uses `discovered_date` frontmatter; `updated` uses the last `## Session Log` entry timestamp, falling back to file mtime |
| `--sort` | Sort field: `priority` (default), `id`, `date`, `type`, `title`, `created`, `completed`, `confidence`, `outcome`, `refinement` |
| `--asc` / `--desc` | Sort direction |
| `--format` | Output format: `table` (default), `list`, `ids` |
| `--limit` | Cap results at N |
| `--json` | Output as JSON array |

#### `ll-issues sequence` / `ll-issues seq`

Suggest a dependency-ordered implementation sequence.

| Flag | Description |
|------|-------------|
| `--limit` | Maximum issues to show (default: 10) |
| `--json` | Output sequence as JSON array |
| `--config` | Path to project root |

#### `ll-issues impact-effort` / `ll-issues ie`

Display an impact vs. effort matrix for active issues.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` |

#### `ll-issues refine-status` / `ll-issues rs`

Show refinement depth table sorted by commands touched. Columns: ID, Pri, Title, per-command session indicators (✓/—), Norm (✓ = filename matches naming convention, ✗ = non-conformant), Ready (confidence score), OutConf (outcome confidence), Total.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` |
| `--format` | Output format: `table` (default), `json` |
| `--no-key` | Suppress the key/legend section at the bottom of output |
| `--config` | Path to project root |

The `Norm` column checks filenames against `^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$`. JSON output includes a `"normalized": true/false` boolean field per record.

**Narrow terminal support**: When the table exceeds the available terminal width, columns are automatically elided in priority order. The default drop sequence is `source` → `norm` → `fmt` → `confidence` → `ready` → `total`; any remaining command columns are then dropped rightmost-first. `id`, `priority`, and `title` are always pinned. The `title` column maintains a minimum width of 20 characters. The drop order is configurable via `refine_status.elide_order` in `ll-config.json` — see [CONFIGURATION.md](CONFIGURATION.md#refine_status).

#### `ll-issues append-log <issue_path> <log_command>` / `ll-issues al`

Append a session log entry to an issue file.

| Argument | Description |
|----------|-------------|
| `issue_path` | Path to the issue markdown file |
| `log_command` | Command name to record (e.g., `/ll:refine-issue`) |

**Examples:**
```bash
ll-issues next-id
ll-issues list --type FEAT --priority P2
ll-issues list --json                         # JSON array of all active issues
ll-issues list --type BUG --json             # JSON filtered by type
ll-issues count                              # Total active issue count
ll-issues count --json                       # JSON with breakdowns
ll-issues count --type BUG                   # Count bugs only
ll-issues count --status completed           # Count completed issues
ll-issues count --status all                 # Total across all statuses
ll-issues show FEAT-518
ll-issues show 518
ll-issues show FEAT-518 --json        # Issue fields as JSON
ll-issues search "caching"                   # Search by keyword
ll-issues search --type BUG --priority P0-P2  # Filter bugs by priority range
ll-issues search --since 2026-01-01 --json   # Issues since date as JSON
ll-issues sequence --limit 10
ll-issues sequence --json             # Ordered sequence as JSON
ll-issues impact-effort
ll-issues impact-effort --type BUG    # Only bugs
ll-issues refine-status
ll-issues refine-status --type BUG --format json
ll-issues append-log .issues/bugs/P2-BUG-123-foo.md /ll:refine-issue
```

---

### ll-deps

Cross-issue dependency discovery and validation.

**Global flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--issues-dir` | `-d` | Path to issues directory (default: `.issues`) |

**Subcommands:**

#### `ll-deps analyze`

Full dependency analysis combining file overlaps and validation.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json` |
| `--graph` | | Include ASCII dependency graph |
| `--sprint` | | Restrict analysis to issues in named sprint |

#### `ll-deps validate`

Validate existing dependency references only (broken refs, cycles).

| Flag | Description |
|------|-------------|
| `--sprint` | Restrict validation to named sprint |

#### `ll-deps fix`

Auto-fix broken refs, stale refs, and missing backlinks.

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview fixes without modifying files |
| `--sprint` | | Restrict fixes to named sprint |

**Examples:**
```bash
ll-deps analyze                       # Full analysis with markdown output
ll-deps analyze --format json         # JSON output
ll-deps analyze --graph               # Include ASCII dependency graph
ll-deps analyze --sprint my-sprint    # Analyze only sprint issues
ll-deps validate                      # Validation only
ll-deps validate --sprint my-sprint   # Validate sprint issue deps
ll-deps fix                           # Auto-fix broken refs and backlinks
ll-deps fix --dry-run                 # Preview fixes
```

---

## History & Analysis

### ll-history

Display summary statistics and analysis for completed issues.

**Subcommands:**

#### `ll-history summary`

Show issue statistics for completed issues.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--directory` | `-d` | Path to issues directory (default: `.issues`) |

#### `ll-history analyze`

Full analysis with trends, subsystems, and debt metrics.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown`, `yaml` |
| `--directory` | `-d` | Path to issues directory |
| `--period` | `-p` | Trend grouping: `weekly`, `monthly` (default), `quarterly` |
| `--compare` | `-c` | Compare last N days to previous N days |

#### `ll-history export <topic>`

Export topic-filtered excerpts from completed issue history.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `topic` | | Topic, area, or system to export |
| `--output` | | Write to file instead of stdout |
| `--format` | `-f` | Format: `narrative` (default), `structured` |
| `--directory` | `-d` | Path to issues directory |
| `--since` | | Only include issues completed after DATE (YYYY-MM-DD) |
| `--min-relevance` | | Minimum relevance score (default: 0.5) |
| `--type` | | Filter by type: `BUG`, `FEAT`, `ENH` |
| `--scoring` | | Relevance method: `intersection` (default), `bm25`, `hybrid` |

**Examples:**
```bash
ll-history summary                         # Summary statistics
ll-history summary --json                  # JSON output
ll-history analyze                         # Full analysis report
ll-history analyze --format markdown       # Markdown report
ll-history analyze --compare 30            # Compare last 30 days to previous
ll-history export "session log"            # Export excerpts for topic
ll-history export "sprint CLI" --output docs/arch/sprint.md
```

---

### ll-workflows

Identify multi-step workflow patterns from user message history. Step 2 of the `/ll:analyze-workflows` pipeline.

**Subcommands:**

#### `ll-workflows analyze`

Analyze workflows from messages and Step 1 patterns.

| Flag | Short | Description |
|------|-------|-------------|
| `--input` | `-i` | **Required.** Input JSONL file with user messages |
| `--patterns` | `-p` | **Required.** Input YAML from Step 1 (workflow-pattern-analyzer) |
| `--output` | `-o` | Output YAML file (default: `.claude/workflow-analysis/step2-workflows.yaml`) |
| `--verbose` | `-v` | Show verbose analysis output |

**Examples:**
```bash
ll-workflows analyze --input messages.jsonl --patterns step1.yaml
ll-workflows analyze -i messages.jsonl -p patterns.yaml -o output.yaml
ll-workflows analyze --input .claude/user-messages.jsonl \
                     --patterns .claude/workflow-analysis/step1-patterns.yaml
```

---

## Synchronization

### ll-sync

Sync local `.issues/` files with GitHub Issues.

**Global flags:**

| Flag | Description |
|------|-------------|
| `--config` | Path to project root |
| `--quiet` | Suppress non-essential output |
| `--dry-run` | Show what would happen without making changes |

**Subcommands:**

#### `ll-sync status`

Show sync status between local issues and GitHub.

#### `ll-sync push [issue_ids...]`

Push local issues to GitHub. If no IDs given, pushes all.

#### `ll-sync pull`

Pull GitHub Issues to local.

| Flag | Short | Description |
|------|-------|-------------|
| `--labels` | `-l` | Filter by labels (comma-separated) |

#### `ll-sync diff [issue_id]`

Show differences between local and GitHub issues. Omit `issue_id` for a summary of all synced issues.

#### `ll-sync close [issue_ids...]`

Close GitHub issues for completed local issues.

| Flag | Description |
|------|-------------|
| `--all-completed` | Close all GitHub issues whose local counterparts are in `completed/` |

#### `ll-sync reopen [issue_ids...]`

Reopen GitHub issues for locally-active issues. If the issue file is in `completed/`, it is moved back to its active category directory (`bugs/`, `features/`, or `enhancements/`).

| Flag | Description |
|------|-------------|
| `--all-reopened` | Reopen all GitHub issues whose local counterparts have moved back to an active directory |

**Examples:**
```bash
ll-sync status                    # Show sync status
ll-sync push                      # Push all local issues to GitHub
ll-sync push BUG-123              # Push specific issue
ll-sync pull                      # Pull GitHub Issues to local
ll-sync diff BUG-123              # Show diff for specific issue
ll-sync diff                      # Diff summary for all synced issues
ll-sync close ENH-123             # Close GitHub issue for ENH-123
ll-sync close --all-completed     # Close all completed issues on GitHub
ll-sync reopen BUG-042            # Reopen GitHub issue for BUG-042
ll-sync reopen --all-reopened     # Reopen all issues moved back to active locally
```

Requires `"sync": { "enabled": true }` in `.claude/ll-config.json`.

---

## Utilities

### ll-messages

Extract user messages from Claude Code session logs.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--limit` | `-n` | Maximum messages to extract (default: 100) |
| `--since` | | Include only messages after this date (YYYY-MM-DD or ISO) |
| `--output` | `-o` | Output file path (default: `.claude/user-messages-{timestamp}.jsonl`) |
| `--cwd` | | Working directory to use (default: current directory) |
| `--exclude-agents` | | Exclude agent session files (`agent-*.jsonl`) |
| `--stdout` | | Print to stdout instead of writing to file |
| `--verbose` | `-v` | Print verbose progress information |
| `--include-response-context` | | Include metadata from assistant responses |
| `--skip-cli` | | Exclude CLI commands from output |
| `--commands-only` | | Extract only CLI commands, no user messages |
| `--tools` | | Comma-separated tools to extract commands from (default: `Bash`) |

**Examples:**
```bash
ll-messages                               # Last 100 messages to file
ll-messages -n 50                         # Last 50 messages
ll-messages --since 2026-01-01            # Messages since date
ll-messages -o output.jsonl               # Custom output path
ll-messages --stdout                      # Print to terminal
ll-messages --include-response-context    # Include response metadata
ll-messages --skip-cli                    # Exclude CLI commands
ll-messages --commands-only               # Extract only CLI commands
```

---

### ll-gitignore

Suggest and apply `.gitignore` patterns based on untracked files.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview suggestions without modifying `.gitignore` |
| `--quiet` | `-q` | Suppress non-essential output |
| `--config` | | Path to project root (default: current directory) |

**Examples:**
```bash
ll-gitignore                  # Show suggestions and apply approved patterns
ll-gitignore --dry-run        # Preview suggestions without modifying .gitignore
ll-gitignore --quiet          # Suppress non-essential output
```

---

### ll-verify-docs

Verify that documented counts (commands, agents, skills) match actual file counts.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON |
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown` |
| `--fix` | | Auto-fix count mismatches in documentation files |
| `--directory` | `-C` | Base directory (default: current directory) |

**Exit codes:** `0` = all counts match, `1` = mismatches found, `2` = error

**Examples:**
```bash
ll-verify-docs                    # Check and show results
ll-verify-docs --json             # Output as JSON
ll-verify-docs --format markdown  # Markdown report
ll-verify-docs --fix              # Auto-fix mismatches
```

---

### ll-check-links

Check markdown documentation for broken links.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON |
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown` |
| `--directory` | `-C` | Base directory (default: current directory) |
| `--ignore` | | Ignore URL patterns — repeatable |
| `--timeout` | | HTTP request timeout in seconds (default: 10) |
| `--workers` | `-w` | Maximum concurrent HTTP requests (default: 10) |
| `--verbose` | `-v` | Show verbose output |

**Exit codes:** `0` = all links valid, `1` = broken links found, `2` = error

**Examples:**
```bash
ll-check-links                            # Check all markdown files
ll-check-links --json                     # Output as JSON
ll-check-links --format markdown          # Markdown report
ll-check-links -C docs/                   # Check specific directory
ll-check-links --ignore 'http://localhost.*'  # Ignore pattern
ll-check-links --timeout 30 --workers 5   # Custom timeout and concurrency
```

---

## See Also

- [COMMANDS.md](COMMANDS.md) — `/ll:` slash commands reference
- [ARCHITECTURE.md](../ARCHITECTURE.md) — System design
- [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md) — FSM loop configuration guide
- [API.md](API.md) — Python module API reference
