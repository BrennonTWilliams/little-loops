# Configuration Reference

little-loops uses `.ll/ll-config.json` for project-specific settings. All settings have sensible defaults. Run `/ll:init` to auto-detect your project type and generate a config file.

For interactive editing, use `/ll:configure`.

## Full Configuration Example

```json
{
  "$schema": "../config-schema.json",

  "project": {
    "name": "my-project",
    "src_dir": "src/",
    "test_dir": "tests",
    "test_cmd": "pytest tests/",
    "lint_cmd": "ruff check src/",
    "type_cmd": "mypy src/",
    "format_cmd": "ruff format src/",
    "build_cmd": null,
    "run_cmd": null
  },

  "issues": {
    "base_dir": ".issues",
    "categories": {
      "bugs": { "prefix": "BUG", "dir": "bugs", "action": "fix" },
      "features": { "prefix": "FEAT", "dir": "features", "action": "implement" },
      "enhancements": { "prefix": "ENH", "dir": "enhancements", "action": "improve" }
    },
    "completed_dir": "completed",
    "deferred_dir": "deferred",
    "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
    "templates_dir": null,
    "capture_template": "full",
    "duplicate_detection": {
      "exact_threshold": 0.8,
      "similar_threshold": 0.5
    },
    "next_issue": { "strategy": "confidence_first" }
  },

  "automation": {
    "timeout_seconds": 3600,
    "idle_timeout_seconds": 0,
    "state_file": ".auto-manage-state.json",
    "worktree_base": ".worktrees",
    "max_workers": 2,
    "stream_output": true
  },

  "parallel": {
    "max_workers": 2,
    "p0_sequential": true,
    "worktree_base": ".worktrees",
    "state_file": ".parallel-manage-state.json",
    "timeout_per_issue": 3600,
    "max_merge_retries": 2,
    "stream_subprocess_output": false,
    "command_prefix": "/ll:",
    "ready_command": "ready-issue {{issue_id}}",
    "manage_command": "manage-issue {{issue_type}} {{action}} {{issue_id}}",
    "worktree_copy_files": [".claude/settings.local.json", ".env"],
    "require_code_changes": true,
    "use_feature_branches": false,
    "remote_name": "origin"
  },

  "commands": {
    "pre_implement": null,
    "post_implement": null,
    "custom_verification": [],
    "confidence_gate": {
      "enabled": false,
      "readiness_threshold": 85,
      "outcome_threshold": 70
    },
    "tdd_mode": false,
    "max_refine_count": 5,
    "rate_limits": {
      "max_wait_seconds": 21600,
      "long_wait_ladder": [300, 900, 1800, 3600],
      "circuit_breaker_enabled": true,
      "circuit_breaker_path": ".loops/tmp/rate-limit-circuit.json"
    }
  },

  "scan": {
    "focus_dirs": ["src/", "tests/"],
    "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"],
    "custom_agents": []
  },

  "product": {
    "enabled": false,
    "goals_file": ".ll/ll-goals.md",
    "analyze_user_impact": true,
    "analyze_business_value": true,
    "goals_discovery": {
      "max_files": 5,
      "required_files": ["README.md"]
    }
  },

  "prompt_optimization": {
    "enabled": true,
    "mode": "quick",
    "confirm": true,
    "bypass_prefix": "*",
    "clarity_threshold": 6
  },

  "continuation": {
    "enabled": true,
    "auto_detect_on_session_start": true,
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true,
    "max_continuations": 3,
    "prompt_expiry_hours": 24
  },

  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80,
    "context_limit_estimate": 1000000,
    "use_transcript_baseline": true
  },

  "sprints": {
    "sprints_dir": ".sprints",
    "default_timeout": 3600,
    "default_max_workers": 2
  },

  "sync": {
    "enabled": false,
    "provider": "github",
    "github": {
      "repo": null,
      "label_mapping": {
        "BUG": "bug",
        "FEAT": "enhancement",
        "ENH": "enhancement"
      },
      "priority_labels": true,
      "sync_completed": false,
      "state_file": ".ll/ll-sync-state.json"
    }
  },

  "documents": {
    "enabled": false,
    "categories": {}
  },

  "loops": {
    "loops_dir": ".loops"
  },

  "scratch_pad": {
    "enabled": false,
    "threshold_lines": 200
  },

  "dependency_mapping": {
    "overlap_min_files": 2,
    "overlap_min_ratio": 0.25,
    "min_directory_depth": 2,
    "conflict_threshold": 0.4,
    "high_conflict_threshold": 0.7,
    "confidence_modifier": 0.5,
    "scoring_weights": {
      "semantic": 0.5,
      "section": 0.3,
      "type": 0.2
    },
    "exclude_common_files": [
      "__init__.py", "pyproject.toml", "setup.py",
      "setup.cfg", "CHANGELOG.md", "README.md", "conftest.py"
    ]
  },

  "refine_status": {
    "columns": [],
    "elide_order": []
  },

  "cli": {
    "color": true,
    "colors": {
      "logger": {
        "info": "36",
        "success": "32",
        "warning": "33",
        "error": "38;5;208"
      },
      "priority": {
        "P0": "38;5;208;1",
        "P1": "38;5;208",
        "P2": "33",
        "P3": "0",
        "P4": "2",
        "P5": "2"
      },
      "type": {
        "BUG": "38;5;208",
        "FEAT": "32",
        "ENH": "34"
      },
      "fsm_active_state": "32",
      "fsm_edge_labels": {}
    }
  },

  "extensions": [
    "my_package.ext:MyExtension"
  ]
}
```

## Configuration Sections

### `project`

Project-level settings for commands:

| Key | Default | Description |
|-----|---------|-------------|
| `name` | Directory name | Project name |
| `src_dir` | `src/` | Source code directory |
| `test_dir` | `tests` | Test directory path |
| `test_cmd` | `pytest` | Command to run tests |
| `lint_cmd` | `ruff check .` | Command to run linter |
| `type_cmd` | `mypy` | Command for type checking |
| `format_cmd` | `ruff format .` | Command to format code |
| `build_cmd` | `null` | Optional build command |
| `run_cmd` | `null` | Optional run/start command (smoke test) |

### `issues`

Issue management settings:

| Key | Default | Description |
|-----|---------|-------------|
| `base_dir` | `.issues` | Base directory for issues |
| `categories` | See above | Issue category definitions |
| `completed_dir` | `completed` | Where completed issues go |
| `deferred_dir` | `deferred` | Where deferred/parked issues go |
| `priorities` | `[P0-P5]` | Valid priority prefixes |
| `templates_dir` | `null` | Directory for issue templates |
| `capture_template` | `"full"` | Default template style for captured issues (`"full"` or `"minimal"`) |
| `duplicate_detection.exact_threshold` | `0.8` | Jaccard similarity threshold for exact duplicates (0.5-1.0) |
| `duplicate_detection.similar_threshold` | `0.5` | Jaccard similarity threshold for similar issues (0.1-0.9) |
| `next_issue.strategy` | `"confidence_first"` | Selection order for `ll-issues next-issue` / `next-issues`. Named preset: `confidence_first` or `priority_first`. See [`issues.next_issue`](#issuesnext_issue). |
| `next_issue.sort_keys` | `null` | Optional list of `{key, direction}` entries that overrides `strategy` with a custom sort order. |

**Custom Categories**: The three core categories (bugs, features, enhancements) are always included automatically. You can add custom categories and they will be merged with the required ones:

```json
{
  "issues": {
    "categories": {
      "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"},
      "tech-debt": {"prefix": "TECH-DEBT", "dir": "tech-debt", "action": "address"}
    }
  }
}
```

Each category requires a `prefix` (issue ID prefix), and optionally `dir` (subdirectory name, defaults to category key) and `action` (verb for commit messages, defaults to "address").

### `automation`

Sequential automation settings (ll-auto):

| Key | Default | Description |
|-----|---------|-------------|
| `timeout_seconds` | `3600` | Per-issue timeout |
| `idle_timeout_seconds` | `0` | Kill worker if no output for N seconds (0 to disable) |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |

### `parallel`

Parallel automation settings with git worktree isolation (ll-parallel):

| Key | Default | Description |
|-----|---------|-------------|
| `max_workers` | `2` | Number of parallel workers |
| `p0_sequential` | `true` | Process P0 issues sequentially |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `state_file` | `.parallel-manage-state.json` | State persistence |
| `timeout_per_issue` | `3600` | Per-issue timeout in seconds |
| `max_merge_retries` | `2` | Rebase attempts before failing |
| `stream_subprocess_output` | `false` | Stream Claude CLI output |
| `command_prefix` | `/ll:` | Prefix for slash commands |
| `ready_command` | `ready-issue {{issue_id}}` | Ready command template |
| `manage_command` | `manage-issue {{issue_type}} {{action}} {{issue_id}}` | Manage command template |
| `worktree_copy_files` | `[".claude/settings.local.json", ".env"]` | Files to copy to worktrees |
| `require_code_changes` | `true` | Require worktree to produce code changes before merging. Skips no-op runs. |
| `use_feature_branches` | `false` | Create a `feature/<id>-<slug>` branch per issue instead of `parallel/<id>-<timestamp>`. When `true`, auto-merge is skipped and branches survive as PR-ready. Use for PR-based CI/CD workflows. |
| `remote_name` | `"origin"` | Git remote name for fetch/pull operations. Set if your remote is not named `origin` (e.g., `"upstream"`). |

### `product`

Product analysis configuration for `/ll:scan-product`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable product-focused issue analysis |
| `goals_file` | `.ll/ll-goals.md` | Path to product goals/vision document |
| `analyze_user_impact` | `true` | Include user impact assessment in issues |
| `analyze_business_value` | `true` | Include business value scoring in issues |
| `goals_discovery.max_files` | `5` | Maximum markdown files to analyze for goal discovery (1-20) |
| `goals_discovery.required_files` | `["README.md"]` | Files that must exist for discovery (warning if missing) |

To enable product scanning, set `product.enabled: true` and create a goals file with your product vision, personas, and strategic priorities.

### `commands`

Command customization for `/ll:manage-issue`:

| Key | Default | Description |
|-----|---------|-------------|
| `pre_implement` | `null` | Command to run before implementation |
| `post_implement` | `null` | Command to run after implementation |
| `custom_verification` | `[]` | Additional verification commands |
| `confidence_gate.enabled` | `false` | Enable confidence score gate before implementation |
| `confidence_gate.readiness_threshold` | `85` | Minimum readiness score (1-100) required to proceed |
| `confidence_gate.outcome_threshold` | `70` | Minimum outcome confidence score (1-100) required to proceed |
| `tdd_mode` | `false` | Enable TDD mode: write failing tests before implementation |
| `max_refine_count` | `5` | Maximum lifetime `/ll:refine-issue` calls per issue (1–20); enforced by the `refine-to-ready-issue` loop and by `recursive-refine` via sub-loop delegation |
| `rate_limits.max_wait_seconds` | `21600` | Total wall-clock budget (seconds) spent retrying 429s before routing to `on_rate_limit_exhausted` (default 6h) |
| `rate_limits.long_wait_ladder` | `[300, 900, 1800, 3600]` | Long-wait tier backoff ladder (seconds): 5 min → 15 min → 30 min → 1 h. Each 429 after the short-burst tier advances the index, capped at the last entry |
| `rate_limits.circuit_breaker_enabled` | `true` | Enable cross-worktree circuit breaker: prompt-mode actions pre-sleep until `estimated_recovery_at` when a peer worker has observed a 429 |
| `rate_limits.circuit_breaker_path` | `".loops/tmp/rate-limit-circuit.json"` | Path to the shared circuit-breaker sidecar file read/written by all `ll-parallel` workers |

When `confidence_gate.enabled` is `true`, `manage-issue` checks the issue's `confidence_score` frontmatter before Phase 3 (Implementation). If the score is below `readiness_threshold`, implementation halts. Use `--force-implement` to bypass.

The `refine-to-ready-issue` built-in loop also reads `readiness_threshold` and `outcome_threshold` from its `context:` block (defaults: 90/75). Override per-run with `--context readiness_threshold=95` or set project-wide in `ll-config.json` and install the loop locally (`ll-loop install refine-to-ready-issue`) to apply your config defaults.

When `tdd_mode` is `true`, `manage-issue` splits Phase 3 into Phase 3a (Write Tests — Red) and Phase 3b (Implement — Green). In Phase 3a, tests are written based on the plan's acceptance criteria and must fail against the current codebase. In Phase 3b, implementation code is written to make those tests pass.

**Per-issue override**: Set `testable: false` in an issue's YAML frontmatter to skip Phase 3a for that issue even when `tdd_mode` is `true`. Use this for documentation-only changes, prompt-file edits, or any issue where automated testing is not applicable. See [ISSUE_TEMPLATE.md](./ISSUE_TEMPLATE.md#frontmatter-fields) for details.

### `scan`

Codebase scanning configuration:

| Key | Default | Description |
|-----|---------|-------------|
| `focus_dirs` | `["src/", "tests/"]` | Directories to scan |
| `exclude_patterns` | Standard patterns | Paths to exclude from scanning |
| `custom_agents` | `[]` | Custom scanning agents to include |

### `prompt_optimization`

Automatic prompt optimization settings (`/ll:toggle-autoprompt`). When enabled, each user message is evaluated for clarity before being sent to Claude — ambiguous or under-specified prompts are rewritten to be more actionable.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable automatic prompt optimization |
| `mode` | `"quick"` | Optimization mode (`"quick"` or `"thorough"`) |
| `confirm` | `true` | Show diff and ask for confirmation before applying |
| `bypass_prefix` | `*` | Prefix character to skip optimization for that message |
| `clarity_threshold` | `6` | Minimum clarity score (1–10) to pass through unchanged |

**Mode differences**:
- `quick` — Checks wording clarity and specificity only. Fast (< 1 s). Catches vague requests like "fix the bug" but won't add codebase-specific context.
- `thorough` — Also searches the codebase for relevant files, patterns, and conventions to enrich the prompt with concrete references. Slower (5–15 s depending on project size) but produces significantly more precise prompts.

**`clarity_threshold`**: Prompts that score at or above this value (1–10) are passed through unchanged. Score 1–5 = vague/generic; 6 = adequately specific; 7–10 = precise with concrete references. Lower the threshold to optimize more aggressively; raise it to reduce interruptions on already-clear prompts.

**`bypass_prefix`**: Prepend this character to any message to skip optimization entirely for that message. Default `*`, so `*just do it` skips optimization. Useful for one-off commands, raw prompts, or when the optimization would lose intentional ambiguity.

**When to disable**: Turn off (`enabled: false`) for codebases with domain-specific shorthand where optimization rewrites valid terminology, or when running in fully automated pipelines where prompts are pre-authored.

### `continuation`

Session continuation and handoff settings (`/ll:handoff`, `/ll:resume`):

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable continuation prompt features |
| `auto_detect_on_session_start` | `true` | Check for continuation prompt when session starts |
| `include_todos` | `true` | Include todo list state in continuation prompt |
| `include_git_status` | `true` | Include git status in continuation prompt |
| `include_recent_files` | `true` | Include recently modified files in continuation prompt |
| `max_continuations` | `3` | Max automatic session continuations for CLI tools |
| `prompt_expiry_hours` | `24` | Hours before continuation prompt is considered stale |

### `context_monitor`

Context window monitoring for automatic session handoff. See [Session Handoff Guide](../guides/SESSION_HANDOFF.md) for full details.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable context window monitoring (enabled by default; all project templates include this setting) |
| `auto_handoff_threshold` | `80` | Context usage percentage to trigger handoff warning |
| `context_limit_estimate` | `1000000` | Fallback/override for the context window token limit. Auto-detection reads the model from the JSONL transcript and selects the correct limit for known models (claude-*-4* → 200 000). Set this only to override auto-detection or when using an unknown/custom model. Also overridable via `LL_CONTEXT_LIMIT` env var. |
| `use_transcript_baseline` | `true` | Use JSONL transcript token counts as an API-exact baseline (one-turn lag). Improves accuracy from ±30–50% to ±5–15%. Falls back to pure heuristics when unavailable. |

### `sprints`

Sprint management settings (ll-sprint, `/ll:create-sprint`):

| Key | Default | Description |
|-----|---------|-------------|
| `sprints_dir` | `.sprints` | Directory for sprint definitions |
| `default_timeout` | `3600` | Default timeout per issue in seconds |
| `default_max_workers` | `2` | Worker count for parallel execution within waves (1-8) |

### `sync`

GitHub Issues synchronization for `/ll:sync-issues`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable GitHub Issues sync feature |
| `provider` | `"github"` | Issue tracking provider (currently only GitHub) |
| `github.repo` | `null` | GitHub repository in owner/repo format (auto-detected if null) |
| `github.label_mapping` | `{"BUG": "bug", ...}` | Map issue types to GitHub labels |
| `github.priority_labels` | `true` | Add priority as GitHub label (e.g., "P1") |
| `github.sync_completed` | `false` | Also sync completed issues (close on GitHub) |
| `github.state_file` | `.ll/ll-sync-state.json` | File to track sync state |

To enable sync, set `sync.enabled: true`. The repository is auto-detected from your git remote; set `sync.github.repo` to override.

### `documents`

Document category tracking for `/ll:align-issues`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable document category tracking |
| `categories` | `{}` | Document categories with file lists |

To enable document tracking, set `documents.enabled: true` and define categories:

```json
{
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": ["docs/ARCHITECTURE.md", "docs/API.md"]
      }
    }
  }
}
```

Each category requires a `files` array of relative paths. The optional `description` field documents what the category covers.

### `loops`

FSM loop settings:

| Key | Default | Description |
|-----|---------|-------------|
| `loops_dir` | `.loops` | Directory for loop definitions and runtime state |
| `glyphs.prompt` | `✦` | Badge glyph for `prompt` action states in FSM box diagrams |
| `glyphs.slash_command` | `/━►` | Badge glyph for `slash_command` action states |
| `glyphs.shell` | `❯_` | Badge glyph for `shell` action states |
| `glyphs.mcp_tool` | `⚡` | Badge glyph for `mcp_tool` action states |
| `glyphs.sub_loop` | `↳⟳` | Badge glyph for `sub_loop` action states |
| `glyphs.route` | `⑃` | Badge glyph for `route` action states |

Override individual glyphs to customize how FSM box diagrams render state type badges:

```json
{
  "loops": {
    "glyphs": {
      "prompt": "?",
      "shell": "$"
    }
  }
}
```

### `scratch_pad`

Observation masking via scratch pad files to reduce context bloat in automation sessions:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable scratch pad instructions for automation sessions |
| `threshold_lines` | `200` | Line count threshold above which tool outputs are redirected to scratch files (50-1000) |

### `refine_status`

Display settings for `ll-issues refine-status` / `ll-issues rs`:

| Key | Default | Description |
|-----|---------|-------------|
| `columns` | `[]` (all defaults) | Ordered list of columns to display. Valid names: `id`, `priority`, `size`, `title`, `source`, `norm`, `fmt`, `ready`, `confidence`, `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`, `total`. Empty list uses the default set. |
| `elide_order` | `["source", "norm", "fmt", "size", "score_change_surface", "score_ambiguity", "score_test_coverage", "score_complexity", "confidence", "ready", "total"]` | Ordered list of columns to drop (first to last) when the table exceeds terminal width. `id`, `priority`, and `title` are always pinned and cannot be elided. Any column omitted from this list (other than pinned columns) is dropped rightmost-first after the explicit list is exhausted. Empty list (`[]`) restores the default drop sequence. |

**Example** — drop `source` and `fmt` before other columns on narrow terminals:

```json
{
  "refine_status": {
    "elide_order": ["source", "fmt", "confidence"]
  }
}
```

### `dependency_mapping`

Dependency mapping threshold configuration for overlap detection and conflict scoring:

| Key | Default | Description |
|-----|---------|-------------|
| `overlap_min_files` | `2` | Minimum overlapping files to trigger overlap detection |
| `overlap_min_ratio` | `0.25` | Minimum ratio of overlapping files to smaller set (0.0-1.0) |
| `min_directory_depth` | `2` | Minimum path segments for directory overlap (e.g., `src/components/` = 2) |
| `conflict_threshold` | `0.4` | Conflict score cutoff: below = parallel-safe, above = dependency proposed (0.0-1.0) |
| `high_conflict_threshold` | `0.7` | Conflict score above which issues are labeled HIGH conflict (0.0-1.0) |
| `confidence_modifier` | `0.5` | Confidence reduction applied when dependency direction is ambiguous (0.0-1.0) |
| `scoring_weights.semantic` | `0.5` | Weight for semantic target overlap (component/function names) |
| `scoring_weights.section` | `0.3` | Weight for section mention overlap (UI regions) |
| `scoring_weights.type` | `0.2` | Weight for modification type match |
| `exclude_common_files` | See below | Infrastructure files excluded from overlap detection |

Default `exclude_common_files`: `["__init__.py", "pyproject.toml", "setup.py", "setup.cfg", "CHANGELOG.md", "README.md", "conftest.py"]`

### `issues.next_issue`

Selection behavior for `ll-issues next-issue` / `next-issues`. Picks which issue (or ranked list) the commands return. The default `confidence_first` preset is byte-identical to the legacy hardcoded ordering, so existing projects see no change until they opt in.

| Key | Default | Description |
|-----|---------|-------------|
| `strategy` | `"confidence_first"` | Named preset. `confidence_first`: sort by `(-outcome_confidence, -confidence_score, priority_int)`. `priority_first`: sort by `(priority_int, -outcome_confidence, -confidence_score)`. |
| `sort_keys` | `null` | Optional custom sort. A list of `{key, direction}` entries that overrides `strategy`. Valid keys: `priority`, `outcome_confidence`, `confidence_score`, `effort`, `impact`, `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`. Valid directions: `asc`, `desc`. |

None-handling: missing values use a per-field sentinel — `direction: "desc"` puts `None` after all scored issues; `direction: "asc"` puts `None` last.

Unknown `strategy` or `sort_keys[*].key` values raise `ValueError` at config load time rather than falling back to defaults.

**Example** (prefer raw priority order for a deadline-driven sprint):

```json
{
  "issues": {
    "next_issue": { "strategy": "priority_first" }
  }
}
```

**Example** (custom ordering — complexity first, then priority):

```json
{
  "issues": {
    "next_issue": {
      "sort_keys": [
        { "key": "score_complexity", "direction": "asc" },
        { "key": "priority", "direction": "asc" }
      ]
    }
  }
}
```

### `cli`

CLI output settings.

| Key | Default | Description |
|-----|---------|-------------|
| `color` | `true` | Enable ANSI color output. Set to `false` for CI or plain-text terminals. Also suppressed by the `NO_COLOR` environment variable. Logger instances also respect this setting via `use_color_enabled()` after `configure_output()` is called. |

### `cli.colors.logger`

Override ANSI color codes for log-level output from all `ll-*` tools.

| Key | Default ANSI | Appearance |
|-----|-------------|------------|
| `info` | `36` | Cyan |
| `success` | `32` | Green |
| `warning` | `33` | Yellow |
| `error` | `38;5;208` | Orange |

### `cli.colors.priority`

Override ANSI color codes for issue priority labels in list and card output.

| Key | Default ANSI | Appearance |
|-----|-------------|------------|
| `P0` | `38;5;208;1` | Bold orange |
| `P1` | `38;5;208` | Orange |
| `P2` | `33` | Yellow |
| `P3` | `0` | Default |
| `P4` | `2` | Dim |
| `P5` | `2` | Dim |

### `cli.colors.type`

Override ANSI color codes for issue type labels in list and card output.

| Key | Default ANSI | Appearance |
|-----|-------------|------------|
| `BUG` | `38;5;208` | Orange |
| `FEAT` | `32` | Green |
| `ENH` | `34` | Blue |

### `cli.colors.fsm_active_state`

ANSI color code for the currently active state box highlight in FSM diagrams (shown with `--show-diagrams`).

| Key | Default ANSI | Appearance |
|-----|-------------|------------|
| `fsm_active_state` | `32` | Green |

**Example** — use blue for the active state:

```json
{
  "cli": {
    "colors": {
      "fsm_active_state": "34"
    }
  }
}
```

### `cli.colors.fsm_edge_labels`

Override the default ANSI color codes used for FSM diagram edge labels and connector line characters. Colors are applied to both the text label and the `│`, `─`, `▼`, `▶`, and corner characters that form each edge.

| Key | Default ANSI | Appearance | When applied |
|-----|-------------|------------|--------------|
| `yes` | `32` | Green | Success / affirmative transitions |
| `no` | `38;5;208` | Orange | Failure / negative transitions |
| `error` | `31` | Red | Error transitions |
| `blocked` | `31` | Red | `on_blocked` routing |
| `partial` | `33` | Yellow | Partial-success transitions |
| `retry_exhausted` | `38;5;208` | Orange | `on_retry_exhausted` transitions |
| `rate_limit_exhausted` | `38;5;214` | Amber | `on_rate_limit_exhausted` transitions |
| `next` | `2` | Dim | Default/unconditional transitions |

**Example** — use cyan for success edges and magenta for error edges:

```json
{
  "cli": {
    "colors": {
      "fsm_edge_labels": {
        "yes": "36",
        "error": "35"
      }
    }
  }
}
```

Set `NO_COLOR=1` to disable all colorization regardless of config.

### `extensions`

List of extension module paths to load at startup. Each entry is a `"module.path:ClassName"` string. Extensions implement the `LLExtension` protocol and receive structured `LLEvent` notifications from the EventBus during ll-loop, ll-parallel, and ll-sprint runs.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `extensions` | `array` of `string` | `[]` | Extension module paths. Format: `"module.path:ClassName"`. |

```json
{
  "extensions": [
    "my_package.ext:MyExtension",
    "another_pkg:AnotherExtension"
  ]
}
```

**Authoring an extension:**

```python
# my_package/ext.py
from little_loops.events import LLEvent

class MyExtension:
    # Optional: subscribe only to matching event types (fnmatch glob).
    # Omit or set to None to receive all events.
    event_filter = "issue.*"

    def on_event(self, event: LLEvent) -> None:
        print(f"{event.type} — {event.payload}")
```

`event_filter` accepts a single glob string (e.g. `"issue.*"`) or a list of globs (e.g. `["issue.*", "parallel.*"]`). The filter is matched against the event's `type` field using Python's `fnmatch`. Omit `event_filter` or set it to `None` to receive every event.

**Auto-discovery via entry points:**

To have your extension loaded automatically without listing it in `ll-config.json`, register it under the `little_loops.extensions` entry-point group in your package's `pyproject.toml`:

```toml
[project.entry-points."little_loops.extensions"]
my_ext = "my_package.ext:MyExtension"
```

After installing the package, `ll` will discover and load it on every run alongside any config-listed extensions.

Extensions can also be auto-discovered via Python entry points — see [API Reference → Extension API](API.md#extension-api).

> **Tip**: Use [`ll-create-extension`](CLI.md#ll-create-extension) to scaffold a new extension repo with a ready-to-run entry point, skeleton handler, and example test. Use [`LLTestBus`](API.md#lltestbus) to replay recorded events against your extension offline without starting a live loop.

---

## Manual Configuration

The following fields are defined in `config-schema.json` but are not exposed through `/ll:init` or `/ll:configure`. To set them, edit `.ll/ll-config.json` directly. All have sensible defaults and rarely need changing.

### `scan.custom_agents`

Custom scanning agent names to include during `/ll:scan-codebase`:

```json
{ "scan": { "custom_agents": ["my-security-scanner"] } }
```

Default: `[]` (empty — only built-in agents run).

### `context_monitor.estimate_weights`

Weight factors for the context monitoring token estimation heuristic. Adjust if the context monitor's estimates are consistently too high or too low:

```json
{
  "context_monitor": {
    "estimate_weights": {
      "read_per_line": 10,
      "tool_call_base": 100,
      "bash_output_per_char": 0.3,
      "per_turn_overhead": 800,
      "system_prompt_baseline": 10000
    }
  }
}
```

| Sub-field | Default | Description |
|-----------|---------|-------------|
| `read_per_line` | `10` | Estimated tokens per line read |
| `tool_call_base` | `100` | Base tokens per tool call overhead |
| `bash_output_per_char` | `0.3` | Estimated tokens per character of bash output |
| `per_turn_overhead` | `800` | Tokens per turn for Claude output and user message |
| `system_prompt_baseline` | `10000` | One-time token estimate for system prompt |

### `context_monitor.post_compaction_percent`

After context compaction, reset the token estimate to this percentage of `context_limit_estimate` as a safety margin:

```json
{ "context_monitor": { "post_compaction_percent": 30 } }
```

Default: `30` (range: 10-60).

### `product.analyze_user_impact` / `product.analyze_business_value`

Toggle sub-features of product analysis. Both default to `true` when `product.enabled` is `true`:

```json
{
  "product": {
    "analyze_user_impact": false,
    "analyze_business_value": false
  }
}
```

### `product.goals_discovery`

Fine-tune how product goal auto-discovery scans documentation:

```json
{
  "product": {
    "goals_discovery": {
      "max_files": 10,
      "required_files": ["README.md", "docs/VISION.md"]
    }
  }
}
```

| Sub-field | Default | Description |
|-----------|---------|-------------|
| `max_files` | `5` | Maximum markdown files to analyze (1-20) |
| `required_files` | `["README.md"]` | Files that must exist (warning if missing) |

### `prompt_optimization.bypass_prefix`

Character prefix that bypasses prompt optimization. Messages starting with this prefix are sent as-is:

```json
{ "prompt_optimization": { "bypass_prefix": "!" } }
```

Default: `*`.

## Variable Substitution

Commands use `{{config.*}}` for configuration values:

```markdown
# In command templates
{{config.project.src_dir}}     # -> "src/"
{{config.project.test_cmd}}    # -> "pytest"
{{config.issues.base_dir}}     # -> ".issues"
```

## Command Override

Projects can override plugin commands by placing files in `.claude/commands/ll/`.

Override priority:
1. Project `.claude/commands/ll/*.md` (highest)
2. Plugin `commands/*.md`
3. Default behavior

### Example Override

To add project-specific verification to `manage-issue`:

```bash
# .claude/commands/ll/manage-issue.md
# Copy from plugin and modify as needed
```
