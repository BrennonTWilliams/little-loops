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
| `--type` | | Comma-separated issue types: `BUG`, `FEAT`, `ENH`, `EPIC` | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--config` | | Path to project root (default: current directory) | `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-sync` |
| `--timeout` | `-t` | Timeout in seconds per issue | `ll-parallel`, `ll-sprint run` |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100, default: from config) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--context-limit` | | Override context window token estimate (default: from config or model-detected) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--format` | `-f` | Output format: `text`, `json`, `markdown` | `ll-history`, `ll-deps`, `ll-verify-docs`, `ll-check-links` |

---

## Skill Invocation

### ll-action

Thin CLI wrapper for invoking ll skills as one-shot commands with JSON-structured output. Useful for dashboard integrations, shell scripts, and cron jobs that need a single skill result without running a full FSM loop.

**Subcommands:**

#### `invoke`

Invokes a skill and streams output as newline-delimited JSON (NDJSON) events by default.

| Flag | Description |
|------|-------------|
| `skill` | Skill name (e.g. `refine-issue`, `confidence-check`) |
| `--args ARG [ARG ...]` | Arguments to pass to the skill |
| `--timeout SECONDS` | Timeout in seconds (default: 300) |
| `--output FORMAT` | `stream-json` (default) or `json` |

**stream-json event shapes:**
```json
{"event":"action_start","ts":"...","skill":"refine-issue","args":["ENH-353"]}
{"event":"action_output","ts":"...","line":"Analyzing ENH-353..."}
{"event":"action_complete","ts":"...","exit_code":0,"duration_ms":45230}
```

**json output shape (`--output json`):**
```json
{"exit_code":0,"duration_ms":45230,"output":"...","error":null}
```

#### `capabilities`

Returns the full `CapabilityReport` for the configured host. Does not invoke Claude.

```json
{
  "host": "claude-code",
  "binary": "claude",
  "version": "1.0.3",
  "capabilities": [
    {"name": "streaming", "status": "full", "note": ""},
    {"name": "permission_skip", "status": "full", "note": ""},
    {"name": "agent_select", "status": "full", "note": ""},
    {"name": "tool_allowlist", "status": "full", "note": ""},
    {"name": "json_schema", "status": "unsupported", "note": "..."}
  ],
  "hooks": [
    {"name": "session_start", "status": "installed", "note": ""}
  ]
}
```

#### `list`

Returns all skills with names and descriptions from the plugin manifest. Does not invoke Claude.

```json
[{"name":"refine-issue","description":"..."},...]
```

**Exit codes:** `0` = success, `1` = error, `124` = timeout

**Examples:**
```bash
ll-action invoke refine-issue --args P2-ENH-1229
ll-action invoke confidence-check --args FEAT-042 --timeout 120
ll-action invoke refine-issue --args P2-ENH-1229 --output json
ll-action capabilities
ll-action list
```

---

## Diagnostics

### ll-doctor

Probes the active host CLI and reports which little-loops features are supported. Produces a `CapabilityReport` with one `CapabilityEntry` per capability (streaming, permission skip, agent selection, tool allowlist) and one `HookEntry` per registered hook event.

**Flags:**
- `-j`, `--json` — emit the `CapabilityReport` as JSON instead of the human-readable table.

**Exit codes:** `0` = all capabilities supported, `1` = one or more capabilities unsupported.

**Example output:**
```
Host:    claude  (1.2.3)
Binary:  /usr/local/bin/claude

Capabilities:
  streaming          full
  permission_skip    full
  agent_select       full
  tool_allowlist     partial  (flag accepted but not validated)

Hooks:
  pre_tool_use       installed
  post_tool_use      registered
```

**Examples:**
```bash
ll-doctor
ll-doctor --json
```

---

### ll-ctx-stats

Show context-window analytics for the current project (FEAT-1160). Reads per-tool byte metrics that the `post_tool_use` hook persists into `.ll/history.db` (FEAT-1623) and renders a compact summary of how much data was processed by tools vs. how much actually entered the conversation context. Falls back to `.ll/ll-context-state.json` (token estimates) when the SQLite store is absent so first-time users still get useful output.

**Flags:**
- `--db PATH` — Use a non-default session database (default `.ll/history.db`).
- `--json` — Emit the report as JSON instead of the human-readable summary.

**Exit codes:** `0` = report rendered (data present or fallback used), `1` = no data found in either the SQLite store or the fallback file.

**Examples:**
```bash
ll-ctx-stats
ll-ctx-stats --db custom/history.db
ll-ctx-stats --json
```

To enable per-tool byte tracking, set `"analytics": {"enabled": true}` in `.ll/ll-config.json`.

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
| `--type` | | Process only these types: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--config` | | Path to project root |
| `--category` | `-c` | Filter to category: `bugs`, `features`, `enhancements`, `epics` |
| `--priority` | `-p` | Comma-separated priority levels to process (e.g., `P1,P2`) |
| `--label` | | Comma-separated labels to process (e.g., `fsm,cli,quick-win`); matches issues with `labels:` frontmatter containing any of the specified values |
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
ll-auto --label quick-win        # Only process issues tagged quick-win
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
| `--type` | | Process only these types: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--label` | | Comma-separated labels to process (e.g., `fsm,quick-win`) |
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
| `--type` | | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |

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

> **Milestone write-back**: When `ll-sprint run` starts, it writes `milestone: <sprint-name>` to the frontmatter of every issue in the sprint. This makes the sprint assignment visible on each issue file and enables `ll-issues list --milestone` filtering and `ll-sync` milestone assignment.

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
| `--queue` | | Wait for conflicting loops to finish; writes a queue entry to `<loops_dir>/.queue/<uuid>.json` while waiting (see [Queue entries](#queue-entries-loopsqueue)) |
| `--show-diagrams[=main\|full\|mini]` | | Display FSM box diagram with active state highlighted after each step. Optional mode: `main` (default for bare flag) hides off-happy-path edges (`error`, `partial`, `blocked`, `retry_exhausted`, `rate_limit_exhausted`, `throttle_hard`) and the states only reachable through them; `full` shows every edge and reachable state (legacy behavior); `mini` is a skeleton view — each state box shows only its title (no body lines) and edges render without labels, inheriting `main`'s happy-path edge filter. If the active state is hidden in `main`/`mini`, the renderer falls back to `full` for that iteration with a one-line note. The top-level loop is preceded by `== loop: <name> ====...` and, when sub-loops are active, each nesting level is rendered below its parent separated by `── sub-loop: <name> ──` (supports arbitrary depth) |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty). When combined with `--show-diagrams` on a tty, the screen splits into a pinned FSM diagram on top and a scrolling action-output region below; on terminals too short for the full diagram the pinned pane falls back to a 1-hop neighborhood view (predecessors → [active] → successors), then to a single-line `fsm: ... → [...] → ...` status. The pane redraws on SIGWINCH (terminal resize) |
| `--builtin` | | Load loop from built-ins directory (bypasses project `.loops/` lookup) |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--program-md PATH` | | Load steering directive from a Markdown file (default: `.ll/program.md` when present); parsed fields injected into context before `--context` overrides. See [program-md reference](program-md.md). |
| `--worktree` | | Run loop in an isolated git worktree on a new branch named `TIMESTAMP-LOOP-NAME`; worktree and branch are removed on exit. **Cannot be combined with `--background`** — passing both exits with an error. |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

> **Note:** `agent:` and `tools:` are per-state YAML fields, not CLI flags. See [Subprocess Agent and Tool Scoping](../guides/LOOPS_GUIDE.md#subprocess-agent-and-tool-scoping) in the Loops Guide for per-state agent and tool scoping options.

##### Queue entries (`.loops/.queue/`)

When `ll-loop run --queue` encounters a scope conflict with a running loop, it creates `<loops_dir>/.queue/<uuid>.json` before entering the wait and removes it on lock acquisition, timeout, error, or process exit (via `atexit`). The file lets external observers (e.g. a dashboard) enumerate loops that are waiting on a scope lock without scanning process state.

**Ordering:** When multiple loops are waiting on the same lock, they acquire it in FIFO (arrival) order — the first loop to enqueue is the first to run after the current holder exits.

**Entry schema:**

```json
{
  "id": "<uuid>",
  "loopName": "<loop name>",
  "enqueuedAt": "<ISO 8601 UTC timestamp>",
  "context": {
    "waitingFor": "<name of conflicting running loop>",
    "scope": ["<scope path>", ...],
    "pid": <integer PID of the waiting process>
  }
}
```

Entries are short-lived and ephemeral — treat the directory as a live view, not a history log. Stale entries are possible if a process exits abnormally without running `atexit` handlers; cleanup tooling may want to prune entries whose `pid` is no longer alive.

#### `ll-loop validate <loop>` / `ll-loop val <loop>`

Validate a loop definition file.

#### `ll-loop list` / `ll-loop l`

List available loops. Discovery is recursive: runnable loops nested under subdirectories of `loops/` (e.g. `oracles/oracle-capture-issue`) are included, while library fragments under `loops/lib/` are filtered out via `is_runnable_loop()`. Output is grouped by `category` with blank-line separators between groups. Loop names are column-aligned for scanability. Descriptions are truncated with `…` at terminal width. Labels appear as `[label]` badges between the description and `[built-in]` tag. Project loops use bold cyan names while built-in loops use dimmer (non-bold) cyan. The `[built-in]` tag is always positioned on the same line as the name.

For nested loops, the displayed identifier is the **relative path** without the `.yaml` suffix (e.g. `oracles/oracle-capture-issue`) — the same string `ll-loop run` and `ll-loop validate` accept. Top-level loops continue to display as their bare stem. Override suppression (a project loop hiding a built-in of the same name) keys on the full relative path, not the bare stem — so a project `oracles/foo.yaml` does **not** suppress a built-in top-level `foo.yaml`.

| Flag | Short | Description |
|------|-------|-------------|
| `--running` | | Only show currently running loops |
| `--builtin` | | Only show built-in loops (exclude project `.loops/`) |
| `--category <cat>` | `-c` | Filter to loops with the given category (e.g. `apo`, `issue-management`, `code-quality`) |
| `--label <tag>` | `-l` | Filter to loops that carry the given label tag; repeat for multiple tags (OR match) |
| `--json` / `-j` | | Output as JSON array. Without `--running`: each entry includes `name` (relative-path identifier — e.g. `oracles/oracle-capture-issue` for nested loops, `fix-quality-and-tests` for top-level), `path`, `category`, `labels`, and `built_in`. With `--running`: each entry is a `LoopState` object (`loop_name`, `status`, `current_state`, `iteration`, `updated_at`, etc.); `instance_id` is **absent** from this output — use `ll-loop status <loop> --json` to resolve per-instance details |

#### `ll-loop status <loop>` / `ll-loop st <loop>`

Show current status of a loop. Aggregates across all running instances of `<loop>`.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output loop state as JSON. Returns a single object when one instance is running; returns a JSON array of objects (each including `instance_id`, `pid`, `pid_source`, `log_file`) when two or more instances are running. The `pid` field is populated from the `.pid` file if present, otherwise falls back to the `.lock` file. The `pid_source` field is `"pid_file"`, `"lock_file"`, or `null` |

#### `ll-loop stop <loop>`

Stop a running loop. Terminates **all running instances** of the named loop (no `--instance-id` selector).

Also handles loops in `interrupted` state that hold an orphaned lock-file PID: if `.loops/.running/<loop>.lock` exists and its PID is alive, `ll-loop stop` sends SIGTERM (with SIGKILL fallback after 10 s) and removes the lock file. This resolves scope conflicts that block subsequent `ll-loop run` invocations without requiring manual `kill` + `rm`. If the lock-file PID is already dead, the stale lock is cleaned up and reported.

#### `ll-loop resume <loop>` / `ll-loop res <loop>`

Resume a loop. Resumable statuses are `"running"`, `"awaiting_continuation"`, and `"interrupted"` — loops stopped via `ll-loop stop` or Ctrl-C are fully resumable. Exits with an error listing instance IDs when two or more resumable instances exist — use `--instance-id` to select one.

| Flag | Short | Description |
|------|-------|-------------|
| `--instance-id <id>` | | Select a specific instance to resume (required when 2+ resumable instances match) |
| `--background` | `-b` | Resume as a detached background process |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--show-diagrams[=main\|full\|mini]` | | Display FSM box diagram with active state highlighted after each step. Optional mode: `main` (default for bare flag) hides off-happy-path edges (`error`, `partial`, `blocked`, `retry_exhausted`, `rate_limit_exhausted`, `throttle_hard`) and the states only reachable through them; `full` shows every edge and reachable state (legacy behavior); `mini` is a skeleton view — each state box shows only its title (no body lines) and edges render without labels, inheriting `main`'s happy-path edge filter. If the active state is hidden in `main`/`mini`, the renderer falls back to `full` for that iteration with a one-line note. The top-level loop is preceded by `== loop: <name> ====...` and, when sub-loops are active, each nesting level is rendered below its parent separated by `── sub-loop: <name> ──` (supports arbitrary depth) |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty). When combined with `--show-diagrams` on a tty, the screen splits into a pinned FSM diagram on top and a scrolling action-output region below; on terminals too short for the full diagram the pinned pane falls back to a 1-hop neighborhood view (predecessors → [active] → successors), then to a single-line `fsm: ... → [...] → ...` status. The pane redraws on SIGWINCH (terminal resize) |
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

The **Commands** section at the bottom of the output can be overridden by adding a top-level `commands:` list to the loop YAML. Each entry is a `{cmd, comment}` pair; when present, this list replaces the five generic default commands so that loops requiring `--param` or `--context` flags can surface copy-paste-ready examples. See `docs/generalized-fsm-loop.md` for the full `commands:` schema.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output FSM config as JSON |
| `--resolved` | | Expand sub-loop states inline under `_subloop` key (requires `--json`) |

#### `ll-loop fragments <lib>`

List fragments defined in a library file, showing each fragment's name and description. Resolves the library path relative to `.loops/`, then falls back to the built-in library directory.

```bash
ll-loop fragments lib/common.yaml     # list built-in common fragments
ll-loop fragments lib/cli.yaml        # list built-in CLI tool fragments
ll-loop fragments lib/benchmark.yaml  # list built-in benchmark runner fragment
ll-loop fragments .loops/my-lib.yaml  # list project-local fragment library
```

#### `ll-loop next-loop`

Inspect `.loops/.history/` and suggest the next loop(s) to run, with resolved input parameters where available. Useful for unattended chaining or scheduled follow-up work.

| Flag | Short | Description |
|------|-------|-------------|
| `--count N` | `-n` | Return top N suggestions instead of just one (default: 1) |
| `--json` | `-j` | Output suggestions as a JSON array |
| `--execute` | | Run the top suggestion immediately via the same code path as `ll-loop run` |
| `--exclude NAME` | | Skip the named loop from suggestions (repeatable; useful from on-completion hooks to avoid trivial self-loops) |

Each suggestion includes a scored `rationale` (run frequency, recency, success rate) and a ready-to-paste shell command. For `autodev`, the suggested input is automatically resolved to the current set of `status: open` issue IDs.

**JSON output keys:** `loop`, `input`, `context`, `score`, `rationale`, `command`

**Examples:**
```bash
ll-loop next-loop                          # Top suggestion with human-readable output
ll-loop next-loop --count 3                # Top 3 ranked candidates
ll-loop next-loop --json                   # Machine-readable suggestion
ll-loop next-loop --execute                # Run the top suggestion immediately
ll-loop next-loop --exclude autodev        # Skip autodev (e.g. from its own on-completion hook)
ll-loop next-loop --count 3 --json        # Top 3 as JSON for downstream tooling
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
ll-loop show fix-types --json --resolved  # FSM config with sub-loop states expanded
ll-loop fragments lib/common.yaml     # List built-in common fragments with descriptions
ll-loop fragments lib/cli.yaml        # List built-in CLI tool fragments with descriptions
ll-loop fragments lib/benchmark.yaml  # List built-in benchmark runner fragment
ll-loop next-loop                     # Suggest next loop from history
ll-loop next-loop --count 3 --json    # Top 3 suggestions as JSON
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

List issues with optional filters.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--priority` | Filter by priority: `P0`–`P5`, or comma-separated e.g. `P1,P2` |
| `--label` | Filter by label from `labels:` frontmatter; repeatable for OR match |
| `--milestone` | Filter by milestone name from `milestone:` frontmatter (exact match) |
| `--status` | Filter by status: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`, `all`. Note: synonyms in on-disk frontmatter are normalized on read, but `--status` arguments must use canonical values (argparse validates choices before normalization runs). |
| `--flat` | Output flat list for scripting |
| `--json` / `-j` | Output as JSON array; each entry includes `id`, `title`, `priority`, `type`, `status`, `path`, `labels`, and `milestone` |
| `--limit` / `-n` | Cap output at N issues (must be ≥ 1) |
| `--config` | Path to project root |

#### `ll-issues count` / `ll-issues c`

Count issues. Outputs a single integer by default, or a JSON object with breakdowns.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--priority` | Filter by priority: `P0`–`P5`, or comma-separated e.g. `P1,P2` |
| `--status` | Filter by status: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`, `all`. Note: synonyms in on-disk frontmatter are normalized on read, but `--status` arguments must use canonical values (argparse validates choices before normalization runs). |
| `--json` / `-j` | Output JSON with `total`, `status`, `by_type`, and `by_priority` breakdowns |
| `--config` | Path to project root |

#### `ll-issues show <issue_id>` / `ll-issues s <issue_id>`

Show summary card for a single issue. Accepts short form (`518`), type-prefixed (`FEAT-518`), or full (`P3-FEAT-518`). Searches all type directories regardless of status.

The card includes: ID, title, priority, status, effort, risk, confidence scores, dimension scores (Cmplx, Tcov, Ambig, Chsrf — when present), source (discovered_by), norm (normalized filename check), fmt (formatted/required sections check), integration file count, labels, `captured_at` / `completed_at` timestamps (when present), session history, and path.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output issue fields as JSON (includes `source`, `norm`, `fmt` keys) |

#### `ll-issues path <issue_id>` / `ll-issues p <issue_id>`

Print the relative file path for an issue ID. Accepts short form (`1009`), type-prefixed (`FEAT-1009`), or full (`P3-FEAT-1009`). Searches all type directories regardless of status. Exits 0 on match, 1 if not found.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output as JSON object `{"path": "..."}` |

#### `ll-issues search [query]` / `ll-issues sr [query]`

Search issues with filters and sorting.

| Argument/Flag | Description |
|---------------|-------------|
| `query` | (Optional) Text to match against title and body (case-insensitive) |
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` (repeatable) |
| `--priority` | Filter by priority: `P0`–`P5` or range e.g. `P0-P2` (repeatable) |
| `--status` | Filter by status: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`, `all` |
| `--include-completed` | Include issues of all statuses (alias for `--status all`) |
| `--label` | Filter by label tag (repeatable) |
| `--since` | Only issues on or after DATE (YYYY-MM-DD) |
| `--until` | Only issues on or before DATE (YYYY-MM-DD) |
| `--date-field` | Date field to filter on: `discovered` (default) prefers `captured_at` frontmatter (sub-day resolution) and falls back to `discovered_date`; `updated` uses the last `## Session Log` entry timestamp, falling back to file mtime |
| `--sort` | Sort field: `priority` (default), `id`, `date`, `type`, `title`, `created`, `completed`, `confidence`, `outcome`, `refinement` |
| `--asc` / `--desc` | Sort direction |
| `--format` | Output format: `table` (default), `list`, `ids` |
| `--limit` | Cap results at N |
| `--json` / `-j` | Output as JSON array |

#### `ll-issues sequence` / `ll-issues seq`

Suggest a dependency-ordered implementation sequence.

| Flag | Description |
|------|-------------|
| `--type` | Filter by issue type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--limit` | Maximum issues to show (default: 10) |
| `--json` / `-j` | Output sequence as JSON array |
| `--config` | Path to project root |

#### `ll-issues impact-effort` / `ll-issues ie`

Display an impact vs. effort matrix for active issues.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--json` / `-j` | Output as JSON object with quadrant keys |

#### `ll-issues refine-status` / `ll-issues rs`

Show refinement depth table sorted by commands touched. Columns: ID, Pri, size, Title, source, norm, fmt, per-command session indicators (✓/—), Ready (confidence score), conf (outcome confidence), cmplx (complexity score 0–25), tcov (test coverage score 0–25), ambig (ambiguity score 0–25), chsrf (change surface score 0–25), total.

| Argument/Flag | Description |
|---------------|-------------|
| `ISSUE-ID` | (Optional) Filter to a single issue by ID (e.g. `FEAT-873`, `BUG-525`). Ignores `--type` when set. Exits 1 if the issue is not found. |
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` (ignored when `ISSUE-ID` is provided) |
| `--format` | Output format: `table` (default), `json` (NDJSON) |
| `--json` / `-j` | Output as JSON array; with `ISSUE-ID` outputs a single JSON object instead |
| `--no-key` | Suppress the key/legend section at the bottom of output |
| `--config` | Path to project root |

The `Norm` column checks filenames against `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$`. JSON output includes a `"normalized": true/false` boolean field per record.

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
- Works on issues in any type directory (`bugs/`, `features/`, `enhancements/`, `epics/`)
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
ll-issues count --status done                # Count done issues
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
ll-issues anchor-sweep --dry-run                 # Preview file:line rewrites
ll-issues anchor-sweep                           # Rewrite file:line refs in active issues
ll-issues asw --dry-run                          # Alias: asw
```

---

#### `ll-issues clusters` / `ll-issues cl`

Visualize issue dependency clusters as box diagrams. Walks all relationship types across active issues by default and renders each connected component as a vertically stacked box diagram with arrows.

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--edges SET` | `all` | Relationship types to follow. Aliases: `all` (all types), `blocking` (`blocked_by`+`blocks` only — legacy behaviour), `hard` (`blocked_by`+`blocks`+`depends_on`). Or a comma-separated list of: `blocked_by,blocks,depends_on,relates_to,parent`. |
| `--status SET` | `active` | Issue statuses to include. Aliases: `active` (`open`/`in_progress`/`blocked`), `+deferred` (active + deferred), `all` (everything except cancelled). Or a comma-separated list of canonical status values. |
| `--include-orphans` | off | Include 1-issue clusters (isolated issues with no relationships). |
| `--min-connections N` | 0 | Only show clusters where at least one issue has N or more connections. |
| `--json` / `-j` | off | Output as JSON array. Each element has `cluster_index`, `issue_count`, `issues`, and `edges` (with `relationship` values: `blocked_by`, `blocks`, `depends_on`, `relates_to`, `parent`). |

**Examples:**

```bash
ll-issues clusters                          # All relationship types, active issues
ll-issues clusters --edges=blocking         # Legacy view: blocked_by/blocks only
ll-issues clusters --status=+deferred       # Include deferred issues
ll-issues clusters --status=all             # All statuses except cancelled
ll-issues clusters --json | jq '[.[] | {n: .issue_count, types: [.edges[].relationship] | unique}]'
ll-issues cl --include-orphans              # Show isolated issues too
```

---

#### `ll-issues anchor-sweep` / `ll-issues asw`

Scan all active issue files (`bugs/`, `features/`, `enhancements/`, `epics/`) for bare `file:line` references outside code fences and rewrite them to enclosing function/class/section anchors. Uses a language-agnostic regex backwards-scan (no AST) covering Python, TypeScript, JavaScript, Go, Rust, Ruby, Java, C#, and Markdown.

| Flag | Description |
|------|-------------|
| `--dry-run` | Print what would change without modifying files |
| `--issues-dir DIR` | Issues base directory (default: `.issues`) |

**Behavior:**
- Scans backwards from the cited line number to find the nearest enclosing `def`/`func`/`fn`/`function`/`class`/`struct`/`#` heading.
- Replaces `file.py:42` with `` `file.py` (near function `foo`) ``.
- References inside code fences are skipped.
- References with no resolvable anchor are left unchanged with a warning.
- Always run `--dry-run` before the first production sweep.

**Examples:**
```bash
ll-issues anchor-sweep --dry-run
ll-issues anchor-sweep
ll-issues anchor-sweep --issues-dir custom/issues
ll-issues asw --dry-run
```

---

#### `ll-issues check-flag` / `ll-issues cf`

Exit 0 if a named boolean frontmatter field in the issue equals `true`. Designed for use as a shell gate in FSM loop states.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `field` | Frontmatter field name (e.g., `decision_needed`) |

**Examples:**
```bash
ll-issues check-flag 518 decision_needed   # Exit 0 if decision_needed: true
ll-issues cf FEAT-518 implementation_ready # Exit 0 if implementation_ready: true
```

**FSM loop use**: Use as a shell action with `evaluate: {type: exit_code}` to branch on a single frontmatter boolean without an LLM call.

---

#### `ll-issues check-readiness` / `ll-issues cr`

Exit 0 if an issue's `confidence_score` and `outcome_confidence` frontmatter fields both meet the configured thresholds. Reads thresholds from `commands.confidence_gate` in `ll-config.json`, falling back to `--readiness` / `--outcome` CLI args.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `issue_id` | _(required)_ | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `--readiness N` | `90` | Fallback readiness threshold when not set in `ll-config.json` |
| `--outcome N` | `75` | Fallback outcome confidence threshold when not set in `ll-config.json` |

**Examples:**
```bash
ll-issues check-readiness 518             # Use thresholds from ll-config.json
ll-issues cr FEAT-518 --readiness 85      # Override readiness threshold
ll-issues check-readiness 518 --readiness 80 --outcome 70
```

**FSM loop use**: Use as a shell gate in `refine-to-ready-issue`-style loops to branch without an LLM call. Pair with `ll-issues show --json` when you need the raw scores.

#### `ll-issues set-scores` / `ll-issues ss`

Write `confidence_score`, `outcome_confidence`, and the four per-dimension scores into an issue's YAML frontmatter. Writes idempotently: existing fields are overwritten, unrelated keys are preserved, and missing frontmatter is created from scratch. If no score flags are provided, returns 0 with a warning and writes nothing.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `issue_id` | _(required)_ | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `--confidence N` | `None` | Overall readiness score (0–100) |
| `--outcome N` | `None` | Outcome confidence score (0–100) |
| `--score-complexity N` | `None` | Complexity dimension score (0–25) |
| `--score-test-coverage N` | `None` | Test-coverage dimension score (0–25) |
| `--score-ambiguity N` | `None` | Ambiguity dimension score (0–25) |
| `--score-change-surface N` | `None` | Change-surface dimension score (0–25) |

**Examples:**
```bash
ll-issues set-scores BUG-1307 --confidence 95 --outcome 80
ll-issues ss FEAT-518 --confidence 88 --outcome 72 --score-complexity 22 --score-test-coverage 20 --score-ambiguity 25 --score-change-surface 15
```

**Used by**: `/ll:confidence-check` Phase 4 to persist scores deterministically instead of a free-form `Edit` call.

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

When present in issue frontmatter, `captured_at` and `completed_at` are preferred over the legacy `discovered_date` field and Resolution body regex / git-log fallbacks; the JSON serialization of `CompletedIssue` includes both fields at sub-day ISO 8601 resolution.

**Subcommands:**

#### `ll-history summary`

Show issue statistics for completed issues.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON |
| `--directory` | `-d` | Path to issues directory (default: `.issues`) |

When the unified session DB (`.ll/history.db`, FEAT-1112) contains backfilled `issue_events` rows (run `ll-session backfill`), `summary` reads from the DB instead of re-parsing every completed-issue file. An empty/absent DB falls back to file parsing — no behavior change for un-backfilled projects (ENH-1621). Only the `summary` subcommand is DB-backed; `analyze` and `export` still scan the files because they need bodies and git history.

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
| `--type` | | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
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

The Python API (`analyze_workflows()`) accepts an optional `db_path` argument that prefers the unified session store's `message_events` table over the JSONL input when populated (ENH-1621); an empty/missing DB transparently falls back to the JSONL file. The `--patterns` YAML is a generated analysis artifact and stays a file input.

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

Push local issues to GitHub. If no IDs given, pushes all. When an issue has a `milestone:` frontmatter field, `ll-sync push` passes it to `gh issue create/edit --milestone <name>` to assign the issue to the matching GitHub milestone (by title).

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
| `--all-completed` | Close all GitHub issues whose local counterparts have `status: done` or `status: cancelled` |

#### `ll-sync reopen [issue_ids...]`

Reopen GitHub issues for locally-active issues. After a successful reopen, the issue's `status` frontmatter is updated to `open`; the file stays in its type directory (`bugs/`, `features/`, etc.).

| Flag | Description |
|------|-------------|
| `--all-reopened` | Reopen all GitHub issues whose local counterparts are not closed on GitHub |

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

### ll-logs

Discover and extract ll-relevant JSONL entries from Claude Code session logs. Also generates `logs/index.md` after extraction.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `discover` | List all Claude projects with ll activity (one path per line, sorted) |
| `tail` | Stream live events from an active loop session |
| `extract` | Extract ll-relevant JSONL records to `logs/<slug>/<session-id>.jsonl` |

**`tail` flags:**

| Flag | Description |
|------|-------------|
| `--loop NAME` | Loop name to tail (required) |

**`extract` flags:**

| Flag | Description |
|------|-------------|
| `--all` | Extract all projects with ll activity |
| `--project DIR` | Working directory of the target project |
| `--cmd TOOL` | Filter to records containing this ll- tool name (e.g. `ll-history`) |

`--all` and `--project` are mutually exclusive.

**Examples:**
```bash
ll-logs discover                          # List all projects with ll activity
ll-logs tail --loop my-loop              # Stream live events from an active loop session
ll-logs extract --all                    # Extract all projects to logs/
ll-logs extract --project /path/to/proj  # Extract one project to logs/<slug>/
ll-logs extract --all --cmd ll-history   # Filter to ll-history invocations
```

---

### ll-session

Query the unified session store (SQLite + FTS5) — the per-project `.ll/history.db` populated by `SQLiteTransport` and `ll-session backfill`. Lets operators search and inspect session activity without re-parsing the scattered JSON/markdown sources the analyze-* skills read.

**Global flags:**

| Flag | Description |
|------|-------------|
| `--db PATH` | Path to the session database (default: `.ll/history.db`) |

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `search` | FTS5 full-text query with BM25-ranked results |
| `recent` | Most recent rows for an event kind |
| `backfill` | Seed the database from existing on-disk sources |

**`search` flags:**

| Flag | Description |
|------|-------------|
| `--fts QUERY` | FTS5 match query (required) |
| `--limit N` | Maximum results (default: 20) |

**`recent` flags:**

| Flag | Description |
|------|-------------|
| `--kind {tool,file,issue,loop,correction}` | Event kind to list (required) |
| `--limit N` | Maximum rows (default: 20) |

**Examples:**
```bash
ll-session search --fts "rate limit"   # Full-text search, BM25-ranked
ll-session recent --kind loop          # Recent loop events
ll-session backfill                    # Seed the database from on-disk sources
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

### ll-migrate

One-time migration script that moves all issues from `completed/` and `deferred/` directories into their type-based directories, backfills `completed_at:` for older completed files, and sets correct `status:` frontmatter. Part of the ENH-1390 status-decoupling migration.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned moves without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate --dry-run   # Preview all planned moves (strongly advised before running)
ll-migrate             # Execute migration
ll-migrate --config /path/to/project  # Run for a specific project
```

---

### ll-migrate-relationships

One-time migration script that renames deprecated relationship frontmatter keys in all `.md` files under `.issues/`: `parent_issue:` → `parent:` and `related:` → `relates_to:`. Part of the ENH-1434 relationship field standardization.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned renames without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-relationships --dry-run   # Preview all planned renames
ll-migrate-relationships             # Execute migration
ll-migrate-relationships --config /path/to/project  # Run for a specific project
```

---

### ll-migrate-labels

One-time migration script that reads the freeform `## Labels` body section from all `.md` files under `.issues/` and writes the labels as a `labels:` YAML list in frontmatter. Part of the ENH-1392 labels field addition.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned migrations without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-labels --dry-run   # Preview all planned migrations
ll-migrate-labels             # Execute migration
ll-migrate-labels --config /path/to/project  # Run for a specific project
```

---

### ll-migrate-status

One-time migration script that reads the `status:` frontmatter field from all `.md` files under `.issues/` and rewrites any non-canonical synonyms (e.g. `completed`, `wip`) to their canonical equivalents. Uses the authoritative `STATUS_SYNONYMS` map from `frontmatter.py`. Part of the ENH-1551 cleanup pass.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned normalizations without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-status --dry-run   # Preview all planned normalizations
ll-migrate-status             # Execute migration
ll-migrate-status --config /path/to/project  # Run for a specific project
```

---

### ll-verify-docs

Verify that documented counts (commands, agents, skills, loops) match actual file counts.

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

### ll-verify-skill-budget

Check that the total skill description token footprint stays within the Claude Code listing budget.

Scans all `skills/*/SKILL.md` frontmatter `description` fields. Skips skills with `disable-model-invocation: true`. Token estimate: `len(description) // 4`. Exits 1 if total exceeds the threshold.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--threshold` | | Token budget threshold (default: 2000; overrides ll-config.json) |
| `--directory` | `-C` | Base directory (default: current directory) |

**Exit codes:** `0` = under budget, `1` = over budget

**Examples:**
```bash
ll-verify-skill-budget                # Check against default 2000-token budget
ll-verify-skill-budget --threshold 1500  # Custom threshold
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
    EvaluatorProviderExtension, LLHookIntentExtension) are opt-in — implement
    their methods to activate.
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

> **See also:** [Write a little-loops hook](../claude-code/write-a-hook.md) — full authoring walkthrough for the `LLHookIntentExtension` Protocol, including the adapter flow and pure-function + subprocess testing patterns.

---

### ll-generate-schemas

> **Internal:** Maintainer/developer tool. End users do not need to run this directly.

Generate JSON Schema (draft-07) files for all 25 `LLEvent` types and write them to `docs/reference/schemas/`.

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

### ll-generate-skill-descriptions

> **Release utility:** Run before tagging a release to batch-refresh skill descriptions.

Auto-generate concise (≤100 character) descriptions for LLM-discoverable skills using the Claude CLI. For each `skills/*/SKILL.md` that does **not** have `disable-model-invocation: true`, it extracts trigger keywords and a body excerpt, prompts Claude to produce a single-line description, and optionally writes it back to the frontmatter.

Dry-run by default (previews proposed descriptions without modifying files).

**Flags:**

| Flag | Description |
|------|-------------|
| `--apply` | Write generated descriptions back to `SKILL.md` frontmatter |
| `--quiet` | Suppress per-skill output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = one or more skills failed or skills directory not found

**Examples:**
```bash
ll-generate-skill-descriptions               # Dry-run: preview proposed descriptions
ll-generate-skill-descriptions --apply       # Write descriptions back to SKILL.md files
ll-generate-skill-descriptions --quiet       # Suppress per-skill output
```

> **See also:** [CONTRIBUTING.md New Skill Checklist](../../CONTRIBUTING.md) for the classification policy and when to run this tool.

---

### ll-adapt-skills-for-codex

Adapt ll's `skills/*/SKILL.md` files for the Codex Skills API **and** bridge every `commands/*.md` slash command into a Codex-discoverable `skills/ll-<name>/` entry.

**Skills adaptation (in-place).** For each `skills/<name>/SKILL.md`, inserts `name:` (the directory slug) and `metadata.short-description:` (first line of the existing `description:` field, ≤80 chars) into the SKILL.md frontmatter, and creates `agents/openai.yaml` with `display_name` and `short_description` under an `interface:` block. Uses targeted string manipulation — no YAML roundtrip — to preserve existing frontmatter formatting.

**Commands bridge (synthesized).** For each `commands/<name>.md`, synthesizes a wrapper `skills/ll-<name>/SKILL.md` (with `name: ll-<name>`, the source command's `description:` copied verbatim, and a derived `metadata.short-description:`) plus a matching `agents/openai.yaml`. The `ll-` namespace prefix prevents collisions with skills sharing a base name (e.g. `commit`). Commands whose frontmatter declares `disable-model-invocation: true` are skipped, mirroring the skills-adapter contract. Multi-line descriptions are emitted as YAML block scalars so the synthesized frontmatter parses cleanly. Bridged `ll-<name>/` entries are committed in-repo and discovered by Codex via the same Skills API path as adapted real skills.

Dry-run by default (previews proposed changes without modifying files).

**Flags:**

| Flag | Description |
|------|-------------|
| `--apply` | Write skill frontmatter updates and create bridged `skills/ll-<name>/` directories on disk |
| `--quiet` | Suppress per-entry output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = one or more entries failed or `skills/` directory not found

**Examples:**
```bash
ll-adapt-skills-for-codex            # Dry-run: preview proposed skill + command changes
ll-adapt-skills-for-codex --apply    # Write frontmatter, bridge commands → skills/ll-<name>/
ll-adapt-skills-for-codex --quiet    # Suppress per-entry output
```

---

### ll-adapt-agents-for-codex

Generate `.codex/agents/*.toml` files from `agents/*.md` so Codex CLI can select ll subagents via `--agent <name>`.

For each `agents/<name>.md`, reads the agent's name and description from its frontmatter (falling back to the H1 heading), then writes a TOML file to `.codex/agents/<name>.toml` with `name`, `description`, `model`, and `developer_instructions` fields. Uses an idempotent marker comment (`# generated by ll-adapt-agents-for-codex`) to detect and skip previously generated files unless `--force` is passed. User-edited TOML files (files lacking the marker) are never overwritten.

Dry-run by default (previews proposed changes without writing files).

**Flags:**

| Flag | Description |
|------|-------------|
| `--apply` | Write `.codex/agents/*.toml` files to disk |
| `--force` | Overwrite previously generated files even if already up-to-date |
| `--quiet` | Suppress per-entry output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = one or more entries failed or `agents/` directory not found

**Examples:**
```bash
ll-adapt-agents-for-codex            # Dry-run: preview proposed agent TOML changes
ll-adapt-agents-for-codex --apply    # Write .codex/agents/*.toml files
ll-adapt-agents-for-codex --force --apply  # Regenerate all files (including up-to-date)
```

---

### mcp-call

Thin CLI wrapper for direct MCP tool invocation via JSON-RPC. Reads `.mcp.json` from the current directory, spawns the MCP server subprocess, performs the JSON-RPC initialize handshake, calls `tools/call`, and writes the MCP response envelope to stdout.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `server/tool-name` | MCP server name and tool name joined by `/` (e.g., `pencil/batch_get`) |
| `params_json` | Tool parameters as a JSON object string |
| `--timeout SECONDS` | Request timeout in seconds (default: 30). Exit code `124` on timeout. |

**Exit codes:** `0` = success, `1` = tool error, `2` = usage/config error, `124` = timeout, `127` = server or tool not found in `.mcp.json`

**Examples:**
```bash
mcp-call pencil/batch_get '{"patterns": ["**/*.pen"]}'
mcp-call my-server/my-tool '{"key": "value"}'
mcp-call pencil/batch_design '{"nodes": [...]}' --timeout 120
```

---

### ll-learning-tests

Query and manage the learning test registry. Skills and loops call this via `Bash` to check coverage before proceeding.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `check <target>` | Print record JSON; exit 1 if not found |
| `list` | Print all records as a JSON array |
| `mark-stale <target>` | Set status=stale; exit 1 if not found |

**Examples:**
```bash
ll-learning-tests check "Anthropic SDK streaming"
ll-learning-tests list
ll-learning-tests mark-stale "Anthropic SDK streaming"
ll-learning-tests --help
```

**Exit codes:** `0` = success, `1` = target not found

---

## See Also

- [COMMANDS.md](COMMANDS.md) — `/ll:` slash commands reference
- [ARCHITECTURE.md](../ARCHITECTURE.md) — System design
- [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md) — FSM loop configuration guide
- [API.md](API.md) — Python module API reference
- [write-a-hook.md](../claude-code/write-a-hook.md) — hook authoring guide for `LLHookIntentExtension`
