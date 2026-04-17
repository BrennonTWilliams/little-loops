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
| `--only` | | Comma-separated issue IDs to process exclusively | `ll-auto`, `ll-parallel`, `ll-sprint run` |
| `--skip` | | Comma-separated issue IDs to exclude | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--type` | | Comma-separated issue types: `BUG`, `FEAT`, `ENH` | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--config` | | Path to project root (default: current directory) | `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-sync` |
| `--timeout` | `-t` | Timeout in seconds per issue | `ll-parallel`, `ll-sprint run` |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100, default: from config) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--context-limit` | | Override context window token estimate (default: from config or model-detected) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--format` | `-f` | Output format: `text`, `json`, `markdown` | `ll-history`, `ll-deps`, `ll-verify-docs`, `ll-check-links` |

---

## Issue Processing

### ll-auto

Process all backlog issues sequentially in priority order. On startup, `ll-auto` prints a header showing the active LLM model name (detected from the Claude CLI `stream-json` init event).

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
| `--verbose` | `-v` | Show full prompt text; default shows abbreviated 5-line preview |
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

> **Config tip:** Branch naming and merge behavior are controlled by `parallel.use_feature_branches` in `ll-config.json`. When `true`, branches are named `feature/<id>-<slug>` and auto-merge is skipped, leaving PR-ready branches for review. See [Configuration reference](CONFIGURATION.md#parallel).

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
| `--only` | | Issue IDs to process exclusively during execution |
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
| `--json` | `-j` | Output as JSON array |

#### `ll-sprint show <sprint>` / `ll-sprint s <sprint>`

Show sprint details, dependency graph, and health summary.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `sprint` | | Sprint name |
| `--json` | `-j` | Output as JSON (includes all fields) |
| `--config` | | Path to project root |
| `--skip-analysis` | | Skip dependency analysis |

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
| `input` | | (Optional positional) If valid JSON object with keys matching defined context variables, unpacks into those keys; otherwise stored as a string in `context[input_key]` |
| `--max-iterations` | `-n` | Override iteration limit |
| `--delay` | | Sleep N seconds between iterations (useful for recording) |
| `--no-llm` | | Disable LLM evaluation |
| `--llm-model` | | Override LLM model |
| `--dry-run` | | Show execution plan without running |
| `--background` | `-b` | Run as background daemon |
| `--quiet` | `-q` | Suppress progress output |
| `--verbose` | `-v` | Stream all action output live; default shows a short response head preview |
| `--queue` | | Wait for conflicting loops to finish |
| `--show-diagrams` | | Display FSM box diagram with active state highlighted after each step; the top-level loop is preceded by `== loop: <name> ====...` and, when sub-loops are active, each nesting level is rendered below its parent separated by `── sub-loop: <name> ──` (supports arbitrary depth) |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty) |
| `--builtin` | | Load loop from built-ins directory (bypasses project `.loops/` lookup) |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--worktree` | | Run loop in an isolated git worktree on a new branch named `TIMESTAMP-LOOP-NAME`; worktree and branch are removed on exit |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

> **Note:** `agent:` and `tools:` are per-state YAML fields, not CLI flags. See [Subprocess Agent and Tool Scoping](../guides/LOOPS_GUIDE.md#subprocess-agent-and-tool-scoping) in the Loops Guide for per-state agent and tool scoping options.

#### `ll-loop validate <loop>` / `ll-loop val <loop>`

Validate a loop definition file.

#### `ll-loop list` / `ll-loop l`

List available loops. Output is grouped by `category` when categories are set. Loops without a category appear under `uncategorized`.

| Flag | Short | Description |
|------|-------|-------------|
| `--running` | | Only show currently running loops |
| `--builtin` | | Only show built-in loops (exclude project `.loops/`) |
| `--category <cat>` | `-c` | Filter to loops with the given category (e.g. `apo`, `issue-management`, `code-quality`) |
| `--label <tag>` | `-l` | Filter to loops that carry the given label tag; repeat for multiple tags (OR match) |
| `--json` / `-j` | | Output as JSON array; each entry includes `name`, `path`, `category`, `labels`, and `built_in` (when applicable) |

#### `ll-loop status <loop>` / `ll-loop st <loop>`

Show current status of a loop.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output loop state as JSON |

#### `ll-loop stop <loop>`

Stop a running loop.

#### `ll-loop resume <loop>` / `ll-loop res <loop>`

Resume an interrupted loop.

| Flag | Short | Description |
|------|-------|-------------|
| `--background` | `-b` | Resume as a detached background process |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--show-diagrams` | | Display FSM box diagram with active state highlighted after each step; the top-level loop is preceded by `== loop: <name> ====...` and, when sub-loops are active, each nesting level is rendered below its parent separated by `── sub-loop: <name> ──` (supports arbitrary depth) |
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
| `--event` | `-e` | Filter by event type (e.g. `evaluate`, `route`, `state_enter`) |
| `--state` | `-s` | Filter by state name (matches `state`, `from`, or `to` fields) |
| `--since` | | Filter to events within a time window (e.g. `1h`, `30m`, `2d`) |
| `--verbose` | `-v` | Show action output preview and LLM call details (model, latency, prompt, response) |
| `--full` | | Show untruncated prompts and output (implies `--verbose`) |
| `--json` | `-j` | Output events as JSON array |

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

Show loop details and FSM structure. The header line displays active [per-loop config overrides](../guides/LOOPS_GUIDE.md#per-loop-config-overrides) (e.g., `config: handoff_threshold=60`) when a `config:` block is present in the loop YAML.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output FSM config as JSON |

#### `ll-loop fragments <lib>`

List fragments defined in a library file, showing each fragment's name and description. Resolves the library path relative to `.loops/`, then falls back to the built-in library directory.

```bash
ll-loop fragments lib/common.yaml   # list built-in common fragments
ll-loop fragments lib/cli.yaml      # list built-in CLI tool fragments
ll-loop fragments .loops/my-lib.yaml  # list project-local fragment library
```

**Examples:**
```bash
ll-loop fix-types                     # Run loop (shorthand for run)
ll-loop run fix-types --worktree      # Run in isolated git worktree
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
ll-loop fragments lib/common.yaml     # List built-in common fragments with descriptions
ll-loop fragments lib/cli.yaml        # List built-in CLI tool fragments with descriptions
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
| `--priority` | Filter by priority: `P0`–`P5`, or comma-separated e.g. `P1,P2` |
| `--status` | Filter by status: `active` (default), `completed`, `deferred`, `all` |
| `--flat` | Output flat list for scripting |
| `--json` / `-j` | Output as JSON array |
| `--limit` / `-n` | Cap output at N issues (must be ≥ 1) |
| `--config` | Path to project root |

#### `ll-issues count` / `ll-issues c`

Count active issues. Outputs a single integer by default, or a JSON object with breakdowns.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` |
| `--priority` | Filter by priority: `P0`–`P5`, or comma-separated e.g. `P1,P2` |
| `--status` | Filter by status: `active` (default), `completed`, `deferred`, `all` |
| `--json` / `-j` | Output JSON with `total`, `status`, `by_type`, and `by_priority` breakdowns |
| `--config` | Path to project root |

#### `ll-issues show <issue_id>` / `ll-issues s <issue_id>`

Show summary card for a single issue. Accepts short form (`518`), type-prefixed (`FEAT-518`), or full (`P3-FEAT-518`). Searches all active category directories, the completed directory, and the deferred directory.

The card includes: ID, title, priority, status, effort, risk, confidence scores, dimension scores (Cmplx, Tcov, Ambig, Chsrf — when present), source (discovered_by), norm (normalized filename check), fmt (formatted/required sections check), integration file count, labels, session history, and path.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output issue fields as JSON (includes `source`, `norm`, `fmt` keys) |

#### `ll-issues path <issue_id>` / `ll-issues p <issue_id>`

Print the relative file path for an issue ID. Accepts short form (`1009`), type-prefixed (`FEAT-1009`), or full (`P3-FEAT-1009`). Searches all active category directories, the completed directory, and the deferred directory. Exits 0 on match, 1 if not found.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output as JSON object `{"path": "..."}` |

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
| `--json` / `-j` | Output as JSON array |

#### `ll-issues sequence` / `ll-issues seq`

Suggest a dependency-ordered implementation sequence.

| Flag | Description |
|------|-------------|
| `--type` | Filter by issue type: `BUG`, `FEAT`, `ENH` |
| `--limit` | Maximum issues to show (default: 10) |
| `--json` / `-j` | Output sequence as JSON array |
| `--config` | Path to project root |

#### `ll-issues impact-effort` / `ll-issues ie`

Display an impact vs. effort matrix for active issues.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` |
| `--json` / `-j` | Output as JSON object with quadrant keys |

#### `ll-issues refine-status` / `ll-issues rs`

Show refinement depth table sorted by commands touched. Columns: ID, Pri, size, Title, source, norm, fmt, per-command session indicators (✓/—), Ready (confidence score), conf (outcome confidence), cmplx (complexity score 0–25), tcov (test coverage score 0–25), ambig (ambiguity score 0–25), chsrf (change surface score 0–25), total.

| Argument/Flag | Description |
|---------------|-------------|
| `ISSUE-ID` | (Optional) Filter to a single issue by ID (e.g. `FEAT-873`, `BUG-525`). Ignores `--type` when set. Exits 1 if the issue is not found. |
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH` (ignored when `ISSUE-ID` is provided) |
| `--format` | Output format: `table` (default), `json` (NDJSON) |
| `--json` / `-j` | Output as JSON array; with `ISSUE-ID` outputs a single JSON object instead |
| `--no-key` | Suppress the key/legend section at the bottom of output |
| `--config` | Path to project root |

The `Norm` column checks filenames against `^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$`. JSON output includes a `"normalized": true/false` boolean field per record.

**Narrow terminal support**: When the table exceeds the available terminal width, columns are automatically elided in priority order. The default drop sequence is `source` → `norm` → `fmt` → `size` → `chsrf` → `ambig` → `tcov` → `cmplx` → `confidence` → `ready` → `total`; any remaining command columns are then dropped rightmost-first. `id`, `priority`, and `title` are always pinned. The `title` column maintains a minimum width of 20 characters. The drop order is configurable via `refine_status.elide_order` in `ll-config.json` — see [CONFIGURATION.md](CONFIGURATION.md#refine_status).

#### `ll-issues next-action` / `ll-issues na`

Print the next refinement action needed across all active issues. Designed for FSM loop integration — exits 1 when work remains, exits 0 when all issues are ready.

Output format: `<ACTION> <issue-id>` (one line), or `ALL_DONE`.

| Action token | Meaning |
|--------------|---------|
| `NEEDS_FORMAT` | Issue file does not match template v2.0 structure |
| `NEEDS_VERIFY` | `/ll:verify-issues` has not been run on this issue |
| `NEEDS_SCORE` | Confidence/outcome score is missing |
| `NEEDS_REFINE` | Score is below threshold and refine-cap not reached |

| Flag | Default | Description |
|------|---------|-------------|
| `--refine-cap N` | `5` | Max `/ll:refine-issue` runs before moving on |
| `--ready-threshold N` | `85` | Minimum readiness score to consider issue ready |
| `--outcome-threshold N` | `70` | Minimum outcome confidence score to consider issue ready |
| `--skip ISSUE_ID[,...]` | — | Comma-separated issue IDs to exclude (e.g. `ENH-929,BUG-001`); absent `--skip` preserves existing behavior |

#### `ll-issues next-issue` / `ll-issues nx`

Print the issue ranked highest by outcome confidence and readiness score. Designed for FSM loop integration — use this to pick the best issue to work on next based on implementation readiness rather than raw priority.

**Sort order:** Config-driven via `issues.next_issue.strategy` (default: `confidence_first` — `outcome_confidence` desc, `confidence_score` desc, `priority` asc). Issues without scores are ranked below all scored issues.

**Exit codes:** 0 = issue found, 1 = no active issues.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output a JSON object: `{id, path, outcome_confidence, confidence_score, priority}` |
| `--path` | Output only the file path (useful for shell scripting: `$(ll-issues next-issue --path)`) |
| `--skip / -s ISSUE_ID[,...]` | Comma-separated issue IDs to exclude (e.g. `FEAT-007,BUG-001`); absent `--skip` preserves existing behavior |
| `--config` | Path to project root |

#### `ll-issues next-issues [N]` / `ll-issues nxs [N]`

Print all active issues in ranked order by outcome confidence and readiness score. Designed for FSM loop integration — use this to get a ranked list of all issues, not just the top one.

**Sort order:** Config-driven via `issues.next_issue.strategy` (default: `confidence_first` — `outcome_confidence` desc, `confidence_score` desc, `priority` asc). Issues without scores are ranked below all scored issues.

**Exit codes:** 0 = at least one issue found, 1 = no active issues.

| Flag/Arg | Description |
|----------|-------------|
| `N` | Optional count — limit output to top N issues |
| `--json` / `-j` | Output a JSON array of objects: `{id, path, outcome_confidence, confidence_score, priority}` |
| `--path` | Output file paths instead of issue IDs |
| `--config` | Path to project root |

#### `ll-issues skip <issue_id>` / `ll-issues sk`

Deprioritize an active issue by bumping its priority prefix and appending a `## Skip Log` entry. Use this to move refinement failures or blocked issues out of the active queue without completing or deleting them.

| Argument / Flag | Short | Description |
|-----------------|-------|-------------|
| `<issue_id>` | | Issue to deprioritize. Accepts numeric ID (`955`), type+ID (`FEAT-955`), or full prefix (`P3-FEAT-955`) |
| `--priority` | `-p` | Target priority P0–P5 (default: `P5`) |
| `--reason TEXT` | | Reason text appended to the `## Skip Log` entry in the issue file |

**Behavior:**
- Renames the issue file with the new priority prefix (e.g., `P3-FEAT-955` → `P5-FEAT-955`) using `git mv` for tracked files to preserve history, falling back to an atomic rename for untracked files
- Appends a `## Skip Log` section with ISO timestamp and the provided reason (or `"No reason provided"` if omitted)
- If the issue is already at the target priority, the file is not renamed but the Skip Log entry is still appended
- Only works on issues in active directories (`bugs/`, `features/`, `enhancements/`); exits with error for `completed/` or `deferred/`
- Prints the new file path to stdout on success

**Examples:**
```bash
ll-issues skip FEAT-955                                          # Deprioritize to P5 (default)
ll-issues skip 955 --priority P4                                 # Deprioritize to P4
ll-issues skip BUG-042 --reason "retry after CI fix"             # With reason
ll-issues sk ENH-123 -p P3 --reason "blocked on upstream change"
```

---

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
ll-issues list --priority P1,P2              # Filter by multiple priorities
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
ll-issues path 1009                   # Resolve numeric ID to file path
ll-issues path FEAT-1009              # Resolve TYPE-NNN to file path
ll-issues path P3-FEAT-1009           # Resolve full ID to file path
ll-issues path FEAT-1009 --json       # Output as {"path": "..."}
ll-issues search "caching"                   # Search by keyword
ll-issues search --type BUG --priority P0-P2  # Filter bugs by priority range
ll-issues search --since 2026-01-01 --json   # Issues since date as JSON
ll-issues sequence --limit 10
ll-issues sequence --json             # Ordered sequence as JSON
ll-issues impact-effort
ll-issues impact-effort --type BUG    # Only bugs
ll-issues impact-effort --json        # JSON object with quadrant arrays
ll-issues impact-effort --json --type BUG  # Filtered JSON output
ll-issues refine-status
ll-issues refine-status FEAT-873              # Single-issue view
ll-issues refine-status FEAT-873 --json       # Single issue as JSON object
ll-issues refine-status --type BUG --format json
ll-issues next-action                            # Next refinement action needed (exits 1 if work remains)
ll-issues next-action --refine-cap 3             # Lower the refine-cap
ll-issues next-action --ready-threshold 90       # Stricter readiness threshold
ll-issues next-action --skip ENH-929,BUG-001     # Exclude specific issues from consideration
ll-issues next-issue                             # Highest-confidence issue ID
ll-issues next-issue --json                      # As JSON: {id, path, outcome_confidence, confidence_score, priority}
ll-issues next-issue --path                      # File path only (for shell scripting)
ll-issues next-issue --skip FEAT-007,BUG-001     # Exclude specific issues from consideration
ll-issues next-issues                            # All active issues in ranked order
ll-issues next-issues 5                          # Top 5 ranked issues
ll-issues nxs --json                             # Ranked list as JSON array
ll-issues nxs --path                             # Ranked list as file paths
ll-issues skip FEAT-955                          # Deprioritize to P5
ll-issues skip BUG-042 --priority P4 --reason "retry after CI fix"
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

#### `ll-deps apply`

Write proposed dependency relationships to issue files. Re-runs analysis internally and writes accepted proposals (above a confidence threshold) to `## Blocked By` sections. Backlinks are intentionally not written — run `ll-deps fix` afterward to add missing `## Blocks` entries.

| Flag | Short | Description |
|------|-------|-------------|
| `--min-confidence` | | Minimum confidence to apply (default: `0.7`) |
| `--dry-run` | `-n` | Preview without writing |
| `--sprint` | | Restrict to issues in named sprint |
| `<source> <relation> <target>` | | Explicit pair: `FEAT-001 blocks FEAT-002` or `FEAT-001 blocked-by FEAT-002` |

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
ll-deps apply                         # Apply proposals >= 0.7 confidence
ll-deps apply --min-confidence 0.5    # Lower threshold
ll-deps apply --dry-run               # Preview only (no writes)
ll-deps apply --sprint my-sprint      # Sprint-scoped apply
ll-deps apply FEAT-001 blocks FEAT-002       # Manual explicit pair
ll-deps apply FEAT-001 blocked-by FEAT-002   # Manual explicit pair (inverse)
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
| `--json` | `-j` | Output as JSON |
| `--directory` | `-d` | Path to issues directory (default: `.issues`) |

#### `ll-history analyze`

Full analysis with trends, subsystems, and debt metrics.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown`, `yaml` |
| `--directory` | `-d` | Path to issues directory |
| `--period` | `-p` | Trend grouping: `weekly`, `monthly` (default), `quarterly` |
| `--compare` | `-c` | Compare last N days to previous N days |
| `--since` | | Only analyze issues completed on or after DATE (YYYY-MM-DD) |
| `--until` | | Only analyze issues completed on or before DATE (YYYY-MM-DD) |

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
| `--input` | `-i` | Input JSONL file with user messages (default: `.ll/workflow-analysis/step1-patterns.jsonl`) |
| `--patterns` | `-p` | **Required.** Input YAML from Step 1 (workflow-pattern-analyzer) |
| `--output` | `-o` | Output YAML file (default: `.ll/workflow-analysis/step2-workflows.yaml`) |
| `--verbose` | `-v` | Show verbose analysis output |

**Examples:**
```bash
# Use conventional path (no --input needed if ll-messages wrote to the default location)
ll-messages --output .ll/workflow-analysis/step1-patterns.jsonl
ll-workflows analyze --patterns .ll/workflow-analysis/step1-patterns.yaml

# Explicit input
ll-workflows analyze -i messages.jsonl -p patterns.yaml -o output.yaml
ll-workflows analyze --input .ll/user-messages.jsonl \
                     --patterns .ll/workflow-analysis/step1-patterns.yaml
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

Requires `"sync": { "enabled": true }` in `.ll/ll-config.json`.

---

## Utilities

### ll-messages

Extract user messages from Claude Code session logs.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--limit` | `-n` | Maximum messages to extract (default: 100) |
| `--since` | | Include only messages after this date (YYYY-MM-DD or ISO) |
| `--output` | `-o` | Output file path (default: `.ll/user-messages-{timestamp}.jsonl`) |
| `--cwd` | | Working directory to use (default: current directory) |
| `--exclude-agents` | | Exclude agent session files (`agent-*.jsonl`) |
| `--stdout` | | Print to stdout instead of writing to file |
| `--verbose` | `-v` | Print verbose progress information |
| `--include-response-context` | | Include metadata from assistant responses |
| `--skip-cli` | | Exclude CLI commands from output |
| `--commands-only` | | Extract only CLI commands, no user messages |
| `--tools` | | Comma-separated tools to extract commands from (default: `Bash`) |
| `--skill` | | Filter to sessions where this skill was invoked (e.g. `capture-issue`) |
| `--examples-format` | | Output `(input, output)` training pairs instead of raw messages (requires `--skill`) |
| `--context-window` | | Number of preceding messages to include as context in `--examples-format` (default: 3) |

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
ll-messages --skill capture-issue         # Filter to sessions where /ll:capture-issue was invoked
ll-messages --skill capture-issue --examples-format --since 2026-01-01 -o examples.jsonl
ll-messages --skill refine-issue --examples-format --context-window 5 --stdout
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

### ll-create-extension

Scaffold a new little-loops extension project directory. Generates a ready-to-install Python package with an `LLExtension` implementation, a `pyproject.toml` registered under the `little_loops.extensions` entry point, and a starter test using `LLTestBus`.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Extension name in kebab-case (e.g. `my-dashboard-ext`) |

The name is automatically converted: hyphens become underscores for the package directory (`my_dashboard_ext`) and each word is capitalized for the class name (`MyDashboardExt`).

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview files that would be created without writing them |

**Generated layout:**
```
<name>/
├── pyproject.toml          # Package metadata + little_loops.extensions entry point
├── <pkg_name>/
│   ├── __init__.py
│   └── extension.py        # LLExtension implementation stub
└── tests/
    └── test_extension.py   # Starter test using LLTestBus
```

**Generated file contents:**

`pyproject.toml` — wires automatic extension discovery via the `little_loops.extensions` entry point group:
```toml
[project.entry-points."little_loops.extensions"]
my-dashboard-ext = "my_dashboard_ext.extension:MyDashboardExt"
```

`<pkg_name>/extension.py` — skeleton implementing the `LLExtension` protocol:
```python
class MyDashboardExt:
    """MyDashboardExt extension.

    Implement on_event to handle little-loops lifecycle events.
    Optional mixin Protocols (InterceptorExtension, ActionProviderExtension,
    EvaluatorProviderExtension) are opt-in — implement their methods to activate.
    """

    def on_event(self, event: LLEvent) -> None:
        """Handle an incoming event."""
        # See docs/reference/EVENT-SCHEMA.md for all available event types and payload fields
        pass
```

`tests/test_extension.py` — starter test using `LLTestBus`:
```python
class TestMyDashboardExt:
    def test_receives_events(self) -> None:
        """Extension receives events via LLTestBus replay."""
        bus = LLTestBus([])
        ext = MyDashboardExt()
        bus.register(ext)
        bus.replay()
        assert bus.delivered_events == []
```

**Dry-run output:**
```
[DRY RUN] Would create: my-dashboard-ext/
  pyproject.toml
  my_dashboard_ext/__init__.py
  my_dashboard_ext/extension.py
  tests/test_extension.py
```

**Exit codes:** `0` = scaffold created successfully, `1` = directory already exists or error

**Examples:**
```bash
ll-create-extension my-dashboard-ext              # Scaffold extension
ll-create-extension my-dashboard-ext --dry-run    # Preview without writing files
```

After scaffolding:
```bash
cd my-dashboard-ext
pip install -e .          # Install with entry point registration
python -m pytest tests/   # Run starter tests
```

---

### ll-generate-schemas

> **Internal:** Maintainer/developer tool. End users do not need to run this directly.

Generate JSON Schema (draft-07) files for all 22 `LLEvent` types and write them to `docs/reference/schemas/`.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--output` | `-o` | Output directory (default: `docs/reference/schemas/` relative to cwd) |

**Exit codes:** `0` = schemas generated successfully, `1` = error

**Examples:**
```bash
ll-generate-schemas                          # Write to docs/reference/schemas/
ll-generate-schemas -o path/to/schemas/      # Custom output directory
```

> **Note:** Run this after modifying `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py` or adding a new `LLEvent` type. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the full schema maintenance workflow.

---

### mcp-call

Thin CLI wrapper for direct MCP tool invocation via JSON-RPC. Reads `.mcp.json` from the current directory, spawns the MCP server subprocess, performs the JSON-RPC initialize handshake, calls `tools/call`, and writes the MCP response envelope to stdout.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `server/tool-name` | MCP server name and tool name joined by `/` (e.g., `pencil/batch_get`) |
| `params_json` | Tool parameters as a JSON object string |

**Exit codes:** `0` = success, `1` = tool error, `2` = usage/config error, `124` = timeout, `127` = server or tool not found in `.mcp.json`

**Examples:**
```bash
mcp-call pencil/batch_get '{"patterns": ["**/*.pen"]}'
mcp-call my-server/my-tool '{"key": "value"}'
```

---

## See Also

- [COMMANDS.md](COMMANDS.md) — `/ll:` slash commands reference
- [ARCHITECTURE.md](../ARCHITECTURE.md) — System design
- [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md) — FSM loop configuration guide
- [API.md](API.md) — Python module API reference
