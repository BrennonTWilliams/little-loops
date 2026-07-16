# Configuration Reference

little-loops uses `.ll/ll-config.json` for project-specific settings. All settings have sensible defaults. Run `ll-init` to auto-detect your project type and generate a config file.

For interactive editing, use `/ll:configure`.

## Full Configuration Example

```json
{
  "$schema": "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/scripts/little_loops/config-schema.json",

  "project": {
    "name": "my-project",
    "src_dir": "src/",
    "test_dir": "tests",
    "test_cmd": "pytest tests/",
    "lint_cmd": "ruff check src/",
    "type_cmd": "mypy src/",
    "format_cmd": "ruff format src/"
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
    "next_issue": { "strategy": "confidence_first" },
    "auto_commit": false,
    "auto_commit_prefix": "chore(issues)"
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
    "decide_command": "decide-issue {{issue_id}}",
    "worktree_copy_files": [".claude/settings.local.json", ".env"],
    "require_code_changes": true,
    "use_feature_branches": false,
    "epic_branches": { "enabled": false },
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
    "recursive_refine": {
      "max_depth": 3
    },
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
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true,
    "max_continuations": 3,
    "prompt_expiry_hours": 24
  },

  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80,
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
        "ENH": "enhancement",
        "EPIC": "epic"
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

  "design_tokens": {
    "enabled": true,
    "path": ".ll/design-tokens",
    "primitives_file": "primitives.json",
    "semantic_file": "semantic.json",
    "themes_dir": "themes",
    "active_theme": "dark"
  },

  "artifacts": {
    "default_output_dir": "."
  },

  "loops": {
    "loops_dir": ".loops"
  },

  "scratch_pad": {
    "enabled": false,
    "threshold_lines": 200,
    "automation_contexts_only": true,
    "tail_lines": 20,
    "command_allowlist": ["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"],
    "file_extension_filters": [".log", ".txt", ".json", ".md", ".py", ".ts", ".tsx", ".js"]
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

  "code_query": {
    "provider": "auto",
    "codegraph": {
      "db_path": ".codegraph/codegraph.db"
    },
    "staleness": "warn"
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
        "ENH": "34",
        "EPIC": "35"
      },
      "fsm_active_state": "32",
      "fsm_edge_labels": {}
    }
  },

  "decisions": {
    "enabled": false,
    "log_path": ".ll/decisions.yaml",
    "auto_generate": []
  },

  "extensions": [
    "my_package.ext:MyExtension"
  ]
}
```

## Top-Level Fields

### `install_source`

A string recorded by `ll-init` that identifies how little-loops was installed. This field is written automatically and is not intended to be edited by hand.

| Value | Meaning |
|-------|---------|
| `"local-editable"` | Installed via `pip install -e` (development / editable install) |
| `"pypi"` | Installed from PyPI via `pip install little-loops` |
| `"global-claude-code"` | Installed as a global Claude Code plugin |
| `"project-claude-code"` | Installed as a project-level Claude Code plugin |
| `"global-codex"` | Installed as a global Codex plugin |
| `"global-pi"` | Installed as a global Pi plugin |
| `null` | Source could not be determined |

`ll-init` re-writes this field on every run. If you change your install method (e.g., switch from a local editable install to a PyPI release), run `ll-init` again to refresh it.

---

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
| `health_url` | `null` | Optional service health probe URL (FEAT-2551, used by `oracles/code-run-gate` `service_health` state) |

### `issues`

Issue management settings:

| Key | Default | Description |
|-----|---------|-------------|
| `base_dir` | `.issues` | Base directory for issues |
| `categories` | See above | Issue category definitions |
| `completed_dir` | `completed` | **Deprecated** — use `IssueInfo.status` instead; kept for backward compatibility |
| `deferred_dir` | `deferred` | **Deprecated** — use `IssueInfo.status` instead; kept for backward compatibility |
| `priorities` | `[P0-P5]` | Valid priority prefixes |
| `templates_dir` | `null` | Directory for issue templates |
| `deploy_templates` | `false` | When `true`, `ll-init` copies the bundled per-type section templates into `<project_root>/.ll/templates/` so projects can customise them. Deployed copies take precedence over the bundled wheel templates via `resolve_templates_dir()`. |
| `capture_template` | `"full"` | Default template style for captured issues (`"full"`, `"minimal"`, or `"legacy"`) |
| `duplicate_detection.exact_threshold` | `0.8` | Jaccard similarity threshold for exact duplicates (0.0-1.0) |
| `duplicate_detection.similar_threshold` | `0.5` | Jaccard similarity threshold for similar issues (0.0-1.0) |
| `next_issue.strategy` | `"confidence_first"` | Selection order for `ll-issues next-issue` / `next-issues`. Named preset: `confidence_first` or `priority_first`. See [`issues.next_issue`](#issuesnext_issue). |
| `next_issue.sort_keys` | `null` | Optional list of `{key, direction}` entries that overrides `strategy` with a custom sort order. |
| `auto_commit` | `false` | When `true`, the `issue-auto-commit.sh` PostToolUse hook automatically commits issue file changes (Write/Edit) with no other staged files present. |
| `auto_commit_prefix` | `"chore(issues)"` | Commit message prefix used by the auto-commit hook. Final message format is `<prefix>: <verb> <ISSUE_ID> <slug>` where `verb` is `capture` (Write) or `update` (Edit/Update) and `<ISSUE_ID>` + `<slug>` are parsed from the issue filename (`P[0-5]-TYPE-NNN-slug.md`). |

**Custom Categories**: The four core categories (bugs, features, enhancements, epics) are always included automatically. You can add custom categories and they will be merged with the required ones:

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
| `idle_timeout_seconds` | `0` | Seconds of idle inactivity before automation considers the session idle (0 to disable) |
| `state_file` | `.auto-manage-state.json` | State persistence |
| `worktree_base` | `.worktrees` | Git worktree directory |
| `max_workers` | `2` | Parallel workers |
| `stream_output` | `true` | Stream subprocess output |
| `max_continuations` | `3` | Maximum continuation prompts before automation stops (minimum 1) |

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
| `decide_command` | `decide-issue {{issue_id}}` | Command template for the decide-issue step when `decision_needed: true`. `{{issue_id}}` is substituted at runtime. |
| `worktree_copy_files` | `[".claude/settings.local.json", ".env"]` | Files to copy to worktrees |
| `require_code_changes` | `true` | Require worktree to produce code changes before merging. Skips no-op runs. |
| `use_feature_branches` | `false` | Create a `feature/<id>-<slug>` branch per issue instead of `parallel/<id>-<timestamp>`. When `true`, auto-merge is skipped and branches survive as PR-ready. Use for PR-based CI/CD workflows. |
| `push_feature_branches` | `false` | Push the feature branch to `remote_name` after worker success using `git push --force-with-lease`. Requires `use_feature_branches: true`. |
| `open_pr_for_feature_branches` | `false` | Open a draft PR via `gh pr create` after push and record `pr_url:` on the issue. Requires `push_feature_branches: true` and `gh auth status`. |
| `base_branch` | auto-detected | Base branch targeted by PR creation when `open_pr_for_feature_branches` is `true`. Also used as the rebase target for worktree updates. When unset, auto-detected at startup (`origin/HEAD` → current branch → `main`); an explicit value overrides auto-detection. An individual EPIC may override this for its own integration branch via a per-EPIC `base_branch:` (alias `target_branch:`) frontmatter field (FEAT-2652); `ll-sprint` dispatch hard-stops if a declared per-EPIC base does not exist (local or remote). |
| `remote_name` | `"origin"` | Git remote name for fetch/pull operations. Set if your remote is not named `origin` (e.g., `"upstream"`). |
| `epic_branches.enabled` | `false` | **FEAT-2447, child 1/4 of FEAT-2339.** When `true`, all children of a single EPIC share one integration branch (`epic/<EPIC-ID>-<slug>`) for both fork point AND merge target (per Decision ARCHITECTURE-096). Standalone (parentless) issues keep today's per-worker behavior unchanged. Worker-pool wiring landed in FEAT-2448; the `_maybe_complete_epic` / `_inspect_worktree` orchestrator paths landed in FEAT-2449 / FEAT-2562. Remaining CLI/TUI/docs polish is tracked in FEAT-2450. See `.ll/decisions.yaml#ARCHITECTURE-096`. |
| `epic_branches.prefix` | `"epic/"` | Prefix for the per-EPIC integration branch name; the branch composes as `f"{prefix}{epic_id.lower()}-{slug}"` (e.g. `epic/epic-2339-foo`). `{slug}` is the kebab-cased EPIC title. |
| `epic_branches.merge_to_base_on_complete` | `true` | When `true`, the EPIC integration branch is itself merged back to `base_branch` after the EPIC's last child completes. Set `false` to leave the integration branch un-merged (e.g. for manual PR review). |
| `epic_branches.open_pr` | `false` | When `true`, open a PR for the EPIC integration branch via the `gh` CLI on completion. Requires `gh` installed and authenticated. |
| `epic_branches.verify_before_merge` | `false` | When `true`, before merging an EPIC integration branch to `base_branch` (or opening its PR), check it out in a scratch worktree and run `test_cmd`/`lint_cmd` against it. On failure the merge/PR-open is blocked, the branch is left as-is (retried on the next completion event), and the failure is surfaced in the run summary rather than silently logged (ENH-2603). On the `auto-refine-and-implement` FSM loop path this check is skipped as redundant when the loop's `verify` state already produced a `passed` verdict for the current epic tip — the `merge_epic_branch` state reuses that verdict instead of re-running the suite (ENH-2630). |

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

`product.enabled` defaults to `false`; opt in with `ll-init --yes --enable product` (or set `product.enabled: true` in `.ll/ll-config.json` for an existing project). When enabled, `ll-init` deploys `.ll/ll-goals.md` automatically. `ll-goals.md` is optional — if absent, goals are auto-discovered from existing project documentation (README, CHANGELOG, architecture docs). Create a hand-authored goals file only when you want precise control over product vision, personas, and strategic priorities.

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
| `max_refine_count` | `5` | Maximum lifetime `/ll:refine-issue` full-rewrite calls per issue (1–20). Gap-analysis runs (`--gap-analysis`) are exempt. Enforced by `refine-to-ready-issue` and directly by `check_attempt_budget` in `recursive-refine` before each sub-loop entry |
| `recursive_refine.max_depth` | `3` | Maximum decomposition depth per subtree for the `recursive-refine` loop (1–∞, integer); issues at or beyond this depth are skipped with reason `depth-cap` and recorded in `.loops/tmp/recursive-refine-skipped-depth.txt` instead of being passed to size-review |
| `rate_limits.max_wait_seconds` | `21600` | Total wall-clock budget (seconds) spent retrying 429s before routing to `on_rate_limit_exhausted` (default 6h) |
| `rate_limits.long_wait_ladder` | `[300, 900, 1800, 3600]` | Long-wait tier backoff ladder (seconds): 5 min → 15 min → 30 min → 1 h. Each 429 after the short-burst tier advances the index, capped at the last entry |
| `rate_limits.circuit_breaker_enabled` | `true` | Enable cross-worktree circuit breaker: prompt-mode actions pre-sleep until `estimated_recovery_at` when a peer worker has observed a 429 |
| `rate_limits.circuit_breaker_path` | `".loops/tmp/rate-limit-circuit.json"` | Path to the shared circuit-breaker sidecar file read/written by all `ll-parallel` workers |

#### `commands.review_epic`

Configuration for the `/ll:review-epic` skill:

| Key | Default | Description |
|-----|---------|-------------|
| `review_epic.stale_days` | `14` | Days without activity before a child issue is considered stalled. |
| `review_epic.enable_scope_drift_check` | `true` | Enable LLM-based scope-drift and missing-coverage passes. |

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
| `context_limit_estimate` | `0` (auto) | Override for the context window token limit. Omit or set to `0` for auto-detection (`[1m]`-suffixed model ids resolve to 1M by identifier; known claude-*-4* base models → 200000; transcript baseline exceeding the resolved limit auto-upgrades to 1000000 as a fallback). Set to an explicit non-zero value to override, e.g. `1000000` for 1M-context models. Also overridable via `LL_CONTEXT_LIMIT` env var. |
| `use_transcript_baseline` | `true` | Use JSONL transcript token counts as an API-exact baseline (one-turn lag). Part of the three-tier token priority system: `result_token_count > 0` (zero-lag authoritative, written by the `on_usage` callback from stream-json `result` events) → transcript baseline (one-turn lag, ±5–15%) → pure heuristics (±30–50%). This setting enables the second tier; the first tier (`result_token_count`) is always active when available. |

### `session_capture`

Continuous session event capture (FEAT-1262). When enabled, `session-capture.sh`
appends one structured event record per tool invocation to `.ll/ll-session-events.jsonl`,
providing the data source for FEAT-1264's PreCompact handoff snapshot builder.
Default is off; opt in alongside FEAT-1264.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable per-tool event capture to `.ll/ll-session-events.jsonl`. |

### `analytics`

Context-window analytics settings (FEAT-1160 family). When enabled, the
`post_tool_use` hook (FEAT-1623) persists per-tool byte metrics
(`bytes_in` / `bytes_out` / `cache_hit`) into `.ll/history.db` for
consumption by `/ll:ctx-stats` (FEAT-1624). Default is off; opt in once
the ctx-stats CLI ships.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable per-tool byte tracking and file-event recording in the `post_tool_use` hook. When false, the handler is a no-op and writes nothing to SQLite (`tool_events` or `file_events`). |

#### `analytics.capture`

Per-category gating for analytics writes (ENH-1840). All categories default to enabled; set individual fields to restrict which data is collected. `ll-doctor` reports the current state of these settings.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `analytics.capture.skills` | `list[str]` | `["*"]` | Skill names whose invocations are recorded. `["*"]` captures all; use an explicit list to restrict (e.g. `["refine-issue", "scan-codebase"]`). |
| `analytics.capture.cli_commands` | `list[str]` | `["*"]` | CLI command names whose invocations are recorded. `["*"]` captures all. |
| `analytics.capture.corrections` | `bool` | `true` | Record user correction events into `user_corrections`. |
| `analytics.capture.file_events` | `bool` | `true` | Record file-read/write events into `file_events`. When `false`, `ll-ctx-stats` will not have per-file byte data. |
| `analytics.capture.usage_events` | `bool` | `true` | Capture real LLM token-usage events (input/output/cache tokens + derived cost) into `usage_events` (ENH-2461). Forward-compat gate: `usage_events` is currently derived by the `raw_events` rebuild parser (`_backfill_usage_events`), not a live per-event writer, so this flag is reserved for a future live writer. |
| `analytics.capture.correction_patterns` | `list[str]` | `[]` | Additional regex patterns appended to the built-in correction detector. Built-ins always remain active; absent config leaves behavior unchanged. Patterns are raw regex strings. |

**Example** — disable file-event recording:
```json
{
  "analytics": {
    "enabled": true,
    "capture": {
      "file_events": false
    }
  }
}
```

#### `analytics.retention`

Retention policy for `history.db` raw event tables (ENH-1906). Pruning is **dual-gated**: both `min_project_age_days` and `min_db_size_mb` must be exceeded before any rows are deleted. This protects fresh or small projects from accidental data loss. High-value tables (`issue_events`, `user_corrections`) are never pruned regardless of settings.

Run `ll-session prune --dry-run` to preview what would be deleted before committing.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `analytics.retention.min_project_age_days` | `integer` | `365` | Minimum project age in days (MIN(started_at) from sessions table) before pruning is allowed. Both gates must be exceeded. |
| `analytics.retention.min_db_size_mb` | `integer` | `800` | Minimum `.ll/history.db` file size in MB before pruning is allowed. Both gates must be exceeded. |
| `analytics.retention.raw_event_max_age_days` | `integer\|null` | `90` | Delete rows older than N days from `tool_events`, `cli_events`, `file_events`, and `message_events`. `null` disables per-table pruning. |

**Example** — reduce raw-event retention to 30 days once the DB reaches 200 MB:
```json
{
  "analytics": {
    "retention": {
      "min_project_age_days": 180,
      "min_db_size_mb": 200,
      "raw_event_max_age_days": 30
    }
  }
}
```

### `history`

History.db read/consume configuration (ENH-1913). Single namespace owner for all `.ll/history.db`
consumer tunables. The producer side (hooks, `SQLiteTransport`) is always active when analytics is
enabled; these keys control how skills and CLI tools *read* that data.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `history.velocity_window` | `integer` | `10` | Number of recent issues to use when computing velocity (ENH-1905). |
| `history.effort_fields` | `list[str]` | `["session_count", "cycle_time_days"]` | Fields extracted from history.db for effort reporting (ENH-1905). |
| `history.max_age_days` | `integer\|null` | `null` | Maximum age in days for history entries; `null` = no limit (ENH-1905). |
| `history.planning_skills` | `list[str]` | `["create-sprint", "scope-epic", "manage-issue", "review-epic"]` | Skill names whose sessions are included in planning context queries (ENH-1909). |

#### `history.session_digest`

Opt-in project-context snapshot injected at session start (ENH-1907). Queries `history.db` and
prepends a `<project_context>` block to session context so every new session gets a "what's been
happening lately" summary. Default: enabled (opt-out via `history.session_digest.enabled: false`). Run `ll-history-context --project` to preview.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `history.session_digest.enabled` | `boolean` | `true` | Gate flag — set `false` to disable injection. |
| `history.session_digest.days` | `integer` | `7` | Freshness window in days; rows older than this are excluded. |
| `history.session_digest.char_cap` | `integer` | `1200` | Hard character ceiling on the injected block. Truncates with `+N more`. |
| `history.session_digest.sections` | `list[str]` | `[]` | Ordered list of section keys to render. Empty = all providers. Supported: `"touched_files"`, `"completed_issues"`, `"recurring_corrections"`. |

#### `history.evolution`

Feedback evolution configuration (ENH-1911). Controls which correction patterns surface in
evolution analysis.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `history.evolution.feedback_min_recurrence` | `integer` | `2` | Minimum recurrence count for a correction to surface in evolution analysis. |
| `history.evolution.bypass_min_count` | `integer` | `2` | Minimum bypass count threshold for evolution signal suppression. |

#### `history.go_no_go`

Go/no-go decision scoring configuration (ENH-1914).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `history.go_no_go.correction_penalty` | `number` | `-0.2` | Score penalty applied per correction event in go/no-go scoring. |

#### `history.capture_issue`

Capture-issue deduplication configuration (ENH-1914).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `history.capture_issue.dup_overlap_threshold` | `number` | `0.7` | Overlap ratio threshold above which a new issue is considered a duplicate. |

**Example** — enable session digest and tighten velocity window:
```json
{
  "history": {
    "velocity_window": 5,
    "max_age_days": 90,
    "session_digest": {
      "enabled": true,
      "days": 7,
      "char_cap": 1200
    }
  }
}
```

### `sprints`

Sprint management settings (ll-sprint, `/ll:create-sprint`):

| Key | Default | Description |
|-----|---------|-------------|
| `sprints_dir` | `.sprints` | Directory for sprint definitions |
| `default_timeout` | `3600` | Default timeout per issue in seconds |
| `default_max_workers` | `2` | Worker count for parallel execution within waves (1-8) |
| `max_issue_wall_clock_time` | `2700` | Hard per-issue wall-clock timeout in seconds. If an issue (including continuations) exceeds this limit, the orchestrator kills it and proceeds to the next issue. |

### `sync`

GitHub Issues synchronization for `/ll:sync-issues`:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable GitHub Issues sync feature |
| `provider` | `"github"` | Issue tracking provider (currently only GitHub) |
| `github.repo` | `null` | GitHub repository in owner/repo format (auto-detected if null) |
| `github.label_mapping` | `{"BUG": "bug", ..., "EPIC": "epic"}` | Map issue types (BUG/FEAT/ENH/EPIC) to GitHub labels |
| `github.priority_labels` | `true` | Add priority as GitHub label (e.g., "P1") |
| `github.sync_completed` | `false` | Also sync completed issues (close on GitHub) |
| `github.state_file` | `.ll/ll-sync-state.json` | File to track sync state |
| `github.pull_template` | `"minimal"` | Creation variant for issues pulled from GitHub (`"full"`, `"minimal"`, or `"legacy"`). Determines section structure of the generated issue file. |
| `github.pull_limit` | `integer` | `500` | Max number of issues to pull from GitHub in a single sync run. |

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
        "files": ["docs/ARCHITECTURE.md", "docs/reference/API.md"]
      }
    }
  }
}
```

Each category requires a `files` array of relative paths. The optional `description` field documents what the category covers.

### `design_tokens`

Design system token settings for artifact-generating loops. When enabled, `ll-loop run` and `ll-loop resume` pre-inject the resolved token set into the FSM initial context before the first state is entered.

#### Multi-Profile System (ENH-1768)

Design tokens are organized into **profiles** under `path/profiles/`. Each profile is a self-contained directory with its own `primitives.json`, `semantic.json`, `spacing.json`, `typography.json`, and `themes/` subdirectory.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `active` | `str` | `"default"` | Name of the active profile; must match a subdirectory in `path/profiles/`. |
| `profiles_dir` | `str\|null` | `null` | Subdirectory under `path` containing profile directories. Defaults to `"profiles"` at runtime when `null`. |

Built-in profiles:
- `default` — WCAG AA accessible palette
- `editorial-mono` — monochrome editorial theme
- `warm-paper` — warm paper-like palette

**Profile directory layout:**
```
.ll/design-tokens/profiles/
├── default/
│   ├── primitives.json
│   ├── semantic.json
│   ├── spacing.json
│   ├── typography.json
│   └── themes/
│       ├── light.json
│       └── dark.json
├── editorial-mono/
│   └── ...
└── warm-paper/
    └── ...
```

Run `/ll:configure design-tokens` to interactively set up profiles and select the active one.

#### Auto-scaffolding built-in profiles

When you run `/ll:configure` and select or enable a built-in design token profile, the skill detects whether the profile directory is missing from disk and offers to materialize it automatically via `shutil.copytree`:

- **Case A — switching active profile to an unmaterialized built-in**: If `active` is changed to `default`, `editorial-mono`, or `warm-paper` but that profile subdirectory does not yet exist under `path/profiles/`, `/ll:configure` prompts you to scaffold it. Accept to copy the built-in bundle from the ll package into your project's profile directory.

- **Case B — enabling design tokens for the first time with no profiles directory**: If `enabled` is flipped from `false` to `true` (or was absent) and no `profiles/` directory exists at all, all three built-in profiles are copied in one operation without prompting.

Both cases accept automatically when `DANGEROUSLY_SKIP_PERMISSIONS` is set or when `/ll:configure` is invoked with `--auto`.

Custom or unknown profile names (anything not in the built-in list) are unaffected — a warning is emitted if the directory is missing, but no scaffold is offered.

**Legacy flat structure (pre-ENH-1768):**

When no `profiles/` directory is present, the resolver falls back to the flat layout:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `primitives_file` | `str` | `"primitives.json"` | Filename for primitive (raw) token values within `path`. |
| `semantic_file` | `str` | `"semantic.json"` | Filename for semantic (aliased) token values within `path`. |
| `themes_dir` | `str` | `"themes"` | Subdirectory of `path` containing per-theme override files. |
| `active_theme` | `str` | `"dark"` | Name of the active theme; must match a file in `themes_dir`. |

```json
{
  "design_tokens": {
    "enabled": true,
    "path": ".ll/design-tokens",
    "active": "default"
  }
}
```

#### W3C DTCG `$value` Format (ENH-1769)

The design token loader supports the [W3C Design Tokens Community Group](https://tr.designtokens.org/) `$value` format in addition to the legacy flat key-value layout. When a token file contains `$value` keys (e.g., `{"color-primary": {"$value": "#A3B59A"}}`), the loader normalizes them to the internal representation automatically.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `dtcg_mode` | `str` | `"auto"` | Format detection mode: `"auto"` (detect from file content), `"dtcg"` (force DTCG `$value` parsing), or `"flat"` (legacy key-value only). |

**Example DTCG token file:**
```json
{
  "color-primary": { "$value": "#A3B59A" },
  "spacing-md": { "$value": "16px" }
}
```

**See also**: [Design Tokens Community Group specification](https://tr.designtokens.org/)

### `artifacts`

Output settings for `ll-artifact`, the generator of self-contained human-facing HTML artifacts (FEAT-2390). Currently backs the `policy-builder` subcommand, which stamps design-token CSS vars, the canonical predicate grammar, and the skill/command catalog into a `file://`-safe policy-router / rubric loop builder page.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_output_dir` | `str` | `"."` | Directory where `ll-artifact` writes generated artifacts when no `--output`/`-o` override is given. Relative paths resolve against the project root. |

```json
"artifacts": {
  "default_output_dir": "."
}
```

Per-project config only needs an `artifacts` block to override the default output directory; the dataclass default suffices otherwise.

### `decisions`

Decisions and rules log configuration (FEAT-1891). When enabled, architectural decisions and project rules are persisted to a log for traceability. Storage is **hybrid**: new entries are append-only per-entry fragments under `.ll/decisions.d/*.json`, folded into the legacy `.ll/decisions.yaml` flat file on compaction (BUG-2642). Reads union both tiers; a fresh install has only the fragment directory. The fragment directory is **derived** from `log_path` (its `.d`-suffixed sibling) and is not independently configurable (BUG-2647).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `false` | Enable the decisions log feature. |
| `log_path` | `str` | `".ll/decisions.yaml"` | Path to the legacy flat file; the derived fragment directory is its `.d`-suffixed sibling (`.ll/decisions.d/`). |
| `auto_generate` | `list[str]` | `[]` | Issue type prefixes that filter which issue types are processed when running `ll-issues decisions generate`. Empty list processes all types. Example: `["FEAT", "ENH"]` skips BUG entries. |

**Integrity gate (ENH-2591).** The local test suite
(`python -m pytest scripts/tests/`) is this project's CI per `.claude/CLAUDE.md`.
A pytest belt at [`scripts/tests/test_decisions_yaml_gate.py`](../../scripts/tests/test_decisions_yaml_gate.py)
shells out to `ll-verify-decisions` against the live decisions log — both the
flat `.ll/decisions.yaml` and the `.ll/decisions.d/*.json` fragments, which the
validator re-globs in a strict second pass (positive case) and an OTHE-203 corrupted `tmp_path` fixture (negative
case), so any YAML parse error, missing required field, or unknown
entry-type discriminator fails the local suite — closing the
`git commit --no-verify` and non-hook edit paths that the pre-commit
hook (ENH-2590) alone cannot cover. The gate skips gracefully when
`ll-verify-decisions` is absent from `PATH`.

**Claude-side host belt (ENH-2592).** A sibling belt at
[`hooks/scripts/check-decisions-yaml.sh`](../../hooks/scripts/check-decisions-yaml.sh)
runs as a Claude Code `PreToolUse` hook on every `Write`/`Edit` of
`.ll/decisions.yaml` or a `.ll/decisions.d/*.json` fragment, blocking
(host-level exit 2) corruption before the file is even written. It validates the *candidate* content
(`tool_input.content` for Write, `old_string → new_string` reconstruction
for Edit), staged in a temp config root, against the same `ll-verify-decisions`
binary. Only this host-layer belt fires for Claude-driven writes inside the
session — direct editor edits bypass it; the pre-commit hook + pytest gate
remain the authoritative backstops. The hook skips gracefully when
`ll-verify-decisions` or `python3` is missing.

### `learning_tests`

Master switch for the learning test registry feature. When enabled, skills and loops can query `.ll/learning-tests/` via `ll-learning-tests` to check whether a target API or pattern is already proven before re-doing the work. Records are stored as YAML-frontmatter markdown files under `.ll/learning-tests/<slug>.md`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `false` | Enable the learning test registry and `ll-learning-tests` CLI. When disabled, `ll-learning-tests` exits with a message and skills skip proof checks. |
| `auto_prove` | `bool` | `true` | When `enabled`, `rn-implement`'s learning gates (pre-dequeue `check_learning_ready` **and** the remediation-path `prove_rem_learning_gate`) make one `ll-learning-tests prove <target>` attempt before parking an issue on an unproven external-API target. Set `false` to keep the gates check-only for budget-conscious runs. Overridable per-run via the `auto_prove_learning_gate` context flag (ENH-2487). |
| `stale_after_days` | `int` | `30` | Days after which a record is considered stale and should be re-validated. |
| `discoverability.mode` | `str` | `"warn"` | How learning-test gaps are surfaced: `"off"` — silent; `"warn"` — emits a one-line hint and allows the tool call; `"block"` — injects feedback into model context and blocks the `Write`/`Edit`. **Hook behavior**: the `PreToolUse` gate (active for Claude Code; opt-in for Codex/OpenCode) fires on every `Write` or `Edit` call, detects unknown external imports, and consults the registry. |
| `discoverability.skip_packages` | `list[str]` | `["std", "typing", "os", "sys"]` | Packages whose imports are never flagged by the `PreToolUse` gate. Add internal packages or well-known stdlib re-exports here to suppress false positives. |
| `release_gate` | `str` | `"warn"` | Pre-release audit behavior when stale/refuted records are found for imported packages: `"block"` aborts with exit 1; `"warn"` (default) continues with a visible warning. |
| `scan_dirs` | `list[str]` | `["scripts/"]` | Source directories to scan for Python imports during the pre-release audit and orphaned record detection. |

```json
{
  "learning_tests": {
    "enabled": false,
    "auto_prove": true,
    "stale_after_days": 30,
    "discoverability": {
      "mode": "warn",
      "skip_packages": ["std", "typing", "os", "sys"]
    }
  }
}
```

Run `/ll:configure learning-tests` to enable and set up the registry directory.

See [LEARNING_TESTS_GUIDE.md](../guides/LEARNING_TESTS_GUIDE.md) for the full workflow.

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
| `glyphs.parallel` | `∥` | Badge glyph for `parallel` action states |
| `queue_wait_timeout_seconds` | `86400` | Seconds to wait for a conflicting scope lock to release when `--queue` is used |

#### `throttle` (per-state progressive throttling)

Controls the `ThrottleConfig` applied to a state to prevent runaway tool-call loops. Defined inline under a state in loop YAML.

| Field | Default | Description |
|-------|---------|-------------|
| `normal_max` | `3` | Tool calls 1..`normal_max` pass through unrestricted |
| `warn_max` | `8` | At `warn_max` calls, a `throttle_warn` event is emitted |
| `hard_max` | `12` | At `hard_max` calls, routes to `on_throttle_hard` (or hard stop if unset) |

Use `on_throttle_hard: <state>` on the same state to route gracefully instead of stopping. See [EVENT-SCHEMA.md](EVENT-SCHEMA.md) for the `throttle_warn`, `throttle_hard`, and `throttle_stop` events.

#### `prompt_size_guard` (per-loop interpolated-prompt size guard)

ENH-2486: a top-level loop block that WARNs (does not route) when a fully-interpolated action reaches `warn_chars` characters. It surfaces loops that silently re-embed monotonically growing captured outputs/artifacts so the ballooning is observable in `<run>.events.jsonl` rather than only showing up as recurring cost or an OOM. Default-enabled; disable per-run with `--no-prompt-size-guard` or override the threshold with `--prompt-size-warn-chars N`.

| Field | Default | Description |
|-------|---------|-------------|
| `enabled` | `true` | Master switch for the guard. |
| `warn_chars` | `50000` | Interpolated-action char size at/above which a `prompt_size_warn` event is emitted. `0` disables the guard even when `enabled` is `true`. ~12.5K tokens at the 4-chars/token convention. |

The size is measured in characters because the codebase has no tokenizer; the emitted event also reports `est_tokens = size // 4`. See [EVENT-SCHEMA.md](EVENT-SCHEMA.md) for the `prompt_size_warn` event.

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

#### `loops.run_defaults`

Persistent CLI defaults for `ll-loop run`. Values are backfilled when the corresponding flag is absent; explicit CLI flags always take precedence. Set once in `ll-init` via `loops.run_defaults` in the generated config.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `run_defaults.clear` | `boolean` | `true` | If `true`, inject `--clear` into every `ll-loop run` invocation. |
| `run_defaults.show_diagrams` | `string\|null` | `"clean"` | Inject `--show-diagrams <value>` into every invocation. Valid values: `layered`, `neighborhood`, `inline`, `detailed`, `summary`, `clean`, `local`, `slim`, `oneline`, `default`. `null` disables. |
| `run_defaults.mode` | `string\|null` | `null` | Reserved for a future `--mode` flag on `ll-loop run`. No effect until that flag is added. |
| `run_defaults.include` | `string` | `""` | Default loop allowlist injected into `fsm.context["include"]`; empty string = all loops visible. Accepts comma-separated selectors: `loop-name`, `builtin:*`, `project:*`, `category:<label>`. Override per-invocation with `--context include=VALUE`. |
| `run_defaults.delay` | `number\|null` | `null` | Inject `--delay <seconds>` into every `ll-loop run` invocation (inter-iteration pause). Must be a non-negative number. Explicit `--delay` overrides. `null` disables (no pause injected). |

### `scratch_pad`

Observation masking via scratch pad files to reduce context bloat in automation sessions. When `enabled: true`, the `scratch-pad-redirect` PreToolUse hook (`hooks/scripts/scratch-pad-redirect.sh`) rewrites large `Bash` outputs to a scratch file + `tail`, keeping the transcript small. `Read` is **not** intercepted — denying a `Read` edit-locks the file for the session (BUG-2357), and `Read` is already self-capping via `offset`/`limit`.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Enable scratch pad instructions for automation sessions |
| `automation_contexts_only` | `true` | Only enforce redirection in automation sessions (`ll-auto`, `ll-parallel`, `ll-sprint`); skip in interactive sessions |
| `tail_lines` | `20` | Number of lines to surface via `tail` when redirecting large outputs to a scratch file (5-200) |
| `command_allowlist` | `["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"]` | Shell commands eligible for `Bash` redirection by the PreToolUse hook |
| `threshold_lines` | `200` | Retained for config compatibility; no longer affects behavior (previously gated the removed `Read` interception) |
| `file_extension_filters` | `[".log", ".txt", ".json", ".md", ".py", ".ts", ".tsx", ".js"]` | Retained for config compatibility; no longer affects behavior (previously gated the removed `Read` interception) |

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

### `code_query`

Code-query provider selection, codegraph db path, and staleness policy, consumed by the
`codegraph` `CodeQueryProvider` (ENH-2613, `ll-code`). This block is opt-in: with no
`.codegraph/` index present, `ll-code`'s `auto` resolution falls through to the always-available
`fallback` provider unchanged.

| Key | Default | Description |
|-----|---------|-------------|
| `provider` | `"auto"` | Code-query provider to use for structural code lookups. One of `auto`, `codegraph`, `fallback`. |
| `codegraph.db_path` | `".codegraph/codegraph.db"` | Path to the codegraph SQLite database. |
| `staleness` | `"warn"` | How to treat a stale codegraph database relative to source changes. One of `strict`, `warn`, `off`. |

### `issues.next_issue`

Selection behavior for `ll-issues next-issue` / `next-issues`. Picks which issue (or ranked list) the commands return. The default `confidence_first` preset is byte-identical to the legacy hardcoded ordering; the default *dependency filter* (ENH-2436) now skips issues with unresolved blockers unless `--include-blocked` is passed. See the [CLI reference](./API.md#next-issue) for the flag.

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
| `EPIC` | `35` | Purple-magenta |

### `cli.colors.fsm_active_state`

ANSI foreground color code for the currently active state box in FSM diagrams (shown with `--show-diagrams`). This value controls both the **border color** and the **interior background fill**: the fg code is automatically converted to its bg equivalent (e.g. `"32"` → `"42"`) so all interior cells are filled with the highlight color. The state name renders with a contrasting dark foreground (`30`) over the filled background.

Compound ANSI codes (e.g. `"38;5;208"`) cannot be auto-converted to a bg code and fall back to border-only coloring with no interior fill.

| Key | Default ANSI | Appearance |
|-----|-------------|------------|
| `fsm_active_state` | `32` | Green border + green background fill |

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
| `default` | `2` | Dim | Unlabeled / catch-all transitions (`_`) |

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

### `orchestration`

Settings for the host CLI used by orchestration scripts (`ll-auto`, `ll-parallel`, `ll-sprint`).

| Key | Default | Description |
|-----|---------|-------------|
| `host_cli` | (auto-detected) | Override the host CLI: `"claude-code"`, `"codex"`, `"opencode"`, or `"pi"`. Mirrors the `LL_HOST_CLI` environment variable; env var takes precedence if both are set. |

#### `orchestration.composer`

Settings for the `loop-composer` built-in orchestration loop.

| Key | Default | Description |
|-----|---------|-------------|
| `max_plan_nodes` | `8` | Maximum number of steps allowed in a single loop-composer plan. |
| `auto` | `false` | When true, skip the HITL plan-approval gate and execute the plan immediately. |

#### `orchestration.composer.adaptive`

Tuning knobs for the `loop-composer-adaptive` built-in loop (fault-tolerant re-plan-on-failure).

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | When true, prefer the adaptive composer variant. |
| `max_replans` | `2` | Maximum re-plan attempts before aborting. |
| `reassess_min_confidence` | `0.6` | Confidence threshold below which the reassess gate triggers a re-plan. |

#### `orchestration.cluster`

Settings for the `goal-cluster` multi-goal orchestration loop.

| Key | Default | Description |
|-----|---------|-------------|
| `max_batch_size` | `5` | Maximum number of issues to process in a single cluster batch. |
| `enable_dedup` | `true` | When true, deduplicate issues with overlapping goals before batching. |
| `propagate_context` | `true` | When true, pass accumulated context from completed issues to subsequent batches. |

### `hooks`

Settings for hook adapter selection.

| Key | Default | Description |
|-----|---------|-------------|
| `host` | (auto-detected) | Host agent identifier for hook adapters: `"claude-code"`, `"opencode"`, or `"codex"`. Adapters translate between the host's native hook protocol and `LLHookEvent`/`LLHookResult`. |
| `stale_ref_fix` | `"report"` | Session-end stale-ref sweep mode: `"report"` prints findings to stderr; `"auto"` also rewrites them in-place. |

#### `hooks.pre_compact.rubric`

Rubric-gated compaction timing (ENH-2341). When enabled, the `precompact.sh` hook evaluates four structural conditions over the recent transcript before writing state. All conditions must pass; any failure causes the hook to return exit 0 without writing state (compaction still fires but without a continuation snapshot). Disabled by default.

| Key | Default | Description |
|-----|---------|-------------|
| `hooks.pre_compact.rubric.enabled` | `false` | Enable rubric-gated compaction timing. When `false`, falls back to original threshold-only behaviour. |
| `hooks.pre_compact.rubric.hard_ceiling_pct` | `0.95` | Reserved: context fill fraction above which state is always written. Not yet enforced (token count not exposed in PreCompact payload). |
| `hooks.pre_compact.rubric.signals.closed_unit_signals` | `["\bdone\b", "\bcompleted\b", "\bfixed\b", "\bresolved\b"]` | Patterns indicating a reasoning unit is closed. |
| `hooks.pre_compact.rubric.signals.reducible_signals` | `["\bin summary\b", "\bto summarize\b", "\boverall\b"]` | Patterns indicating content is summarisable. |
| `hooks.pre_compact.rubric.signals.progress_signals` | `["\bchanged\b", "\bupdated\b", "\bmodified\b", "\bimplemented\b"]` | Patterns indicating progress since last compaction. |
| `hooks.pre_compact.rubric.signals.stuck_signals` | `["\bsame error\b", "\bstill failing\b", "\brepeat\b"]` | Patterns indicating a stuck loop. Any match causes rubric to fail. |

```json
{
  "hooks": {
    "pre_compact": {
      "rubric": {
        "enabled": true,
        "hard_ceiling_pct": 0.95,
        "signals": {
          "closed_unit_signals": ["\\bdone\\b", "\\bcompleted\\b"],
          "reducible_signals": ["\\bin summary\\b"],
          "progress_signals": ["\\bchanged\\b", "\\bupdated\\b"],
          "stuck_signals": ["\\bsame error\\b", "\\bstill failing\\b"]
        }
      }
    }
  }
}
```

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

The same `little_loops.extensions` entry-point group also dispatches `LLHookIntentExtension` providers — extensions that contribute hook intent handlers via `provided_hook_intents()`. A single package can implement both `LLExtension` (event observers) and `LLHookIntentExtension` (request/response hook handlers); `wire_extensions()` duck-types each interface independently. This single shared group is the resolved design from FEAT-1116 Decision 2 (FEAT-1117 group-split is deferred). See [API Reference → `LLHookIntentExtension`](API.md#llhookintentextension) for the Protocol shape.

Extensions can also be auto-discovered via Python entry points — see [API Reference → Extension API](API.md#extension-api).

> **Tip**: Use [`ll-create-extension`](CLI.md#ll-create-extension) to scaffold a new extension repo with a ready-to-run entry point, skeleton handler, and example test. Use [`LLTestBus`](API.md#lltestbus) to replay recorded events against your extension offline without starting a live loop.

---

### `events.transports`

List of transports to wire onto the EventBus at runtime. Transports are additive sinks that receive every event emitted on the bus (no filtering at the transport layer). Names are resolved against the registry in `little_loops.transport.wire_transports`; unknown names log a warning and are skipped so a typo never prevents the loop from starting.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `events.transports` | `array` of `string` | `[]` | Transport names to register on the EventBus. |

**Currently shipped transports:**

| Name | Effect |
|------|--------|
| `"jsonl"` | Registers a `JsonlTransport` writing to `<log_dir>/events.jsonl` (defaults to `.ll/events.jsonl`). |
| `"socket"` | Registers a `UnixSocketTransport` streaming newline-delimited JSON events over an `AF_UNIX` socket. Configured under `events.socket` (see below). Not available on Windows — `wire_transports` raises `RuntimeError`. |
| `"otel"` | Registers an `OTelTransport` that maps loop executions to OpenTelemetry traces/spans and exports via OTLP. Configured under `events.otel` (see below). Requires `pip install 'little-loops[otel]'`. |
| `"webhook"` | Registers a `WebhookTransport` that batches events and POSTs them as JSON arrays to an HTTP endpoint. Configured under `events.webhook` (see below). Requires `pip install 'little-loops[webhooks]'`. |
| `"sqlite"` | Registers a `SQLiteTransport` that records events into the per-project `.ll/history.db` unified session store. Configured under `events.sqlite` (see below). Queryable via the `ll-session` CLI. |

```json
{
  "events": {
    "transports": ["jsonl", "socket"],
    "socket": {
      "path": ".ll/events.sock",
      "max_clients": 32
    }
  }
}
```

### `events.socket`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `events.socket.path` | `string` | `".ll/events.sock"` | Filesystem path for the AF_UNIX socket. The transport unlinks any stale file before binding and removes the file on `close()`. |
| `events.socket.max_clients` | `integer` | `32` | Maximum simultaneous clients. Connections beyond the cap are accepted-and-closed. |

The socket file is `chmod 0600` immediately after `bind()` — owner-only, since the events stream may include issue titles, file paths, and branch names. Operators wanting wider access must relax permissions out-of-band.

**Per-client buffering and slow-consumer behaviour:** Each client gets a bounded outbound queue (1024 events). When a client cannot keep up, the newest event is dropped (preserving causal order) and a rate-limited warning is logged — `send()` never blocks the FSM thread.

**`ll-auto` exclusion:** `cli/auto.py` does not construct an `EventBus`, so listing `"socket"` (or any transport) under `events.transports` has no effect under `ll-auto`. The socket transport is available under `ll-loop run`/`resume`, `ll-parallel`, and `ll-sprint` parallel-wave runs.

**Subscribing locally:** Any AF_UNIX-aware tool can subscribe — for ad-hoc inspection, pipe `nc -U .ll/events.sock | jq`.

### `events.otel`

Requires: `pip install 'little-loops[otel]'` (installs `opentelemetry-sdk` and `opentelemetry-exporter-otlp-grpc`).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `events.otel.endpoint` | `string` | `"http://localhost:4317"` | OTLP gRPC endpoint for the collector (Grafana Agent, Jaeger, Datadog, etc.). |
| `events.otel.service_name` | `string` | `"little-loops"` | OpenTelemetry `service.name` resource attribute applied to all emitted spans. |

**Span hierarchy:** Each loop run becomes an OTel trace. Loop = root span, state = child span, action = grandchild span. Events such as `evaluate`, `route`, `retry_exhausted`, `cycle_detected`, `stall_detected`, `handoff_detected`, `handoff_spawned`, and `action_output` are recorded as span events on the innermost open span.

**Sub-loop behaviour:** Sub-loop events (`depth > 0`) are no-ops with a single warning per session. Full nested-trace support is deferred.

```json
{
  "events": {
    "transports": ["otel"],
    "otel": {
      "endpoint": "http://localhost:4317",
      "service_name": "little-loops"
    }
  }
}
```

### `events.webhook`

Requires: `pip install 'little-loops[webhooks]'` (installs `httpx`).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `events.webhook.url` | `string \| null` | `null` | HTTP endpoint to POST batched events to. When `null`, the transport is skipped even if `"webhook"` is listed in `transports`. |
| `events.webhook.batch_ms` | `integer` | `1000` | Flush interval in milliseconds. Events accumulate and are POSTed as a JSON array on each tick. |
| `events.webhook.headers` | `object` | `{}` | Additional HTTP headers sent with every POST (e.g. `{"Authorization": "Bearer token"}`). User-supplied keys override defaults; `Content-Type` defaults to `application/json` and can be overridden. |

**Batching:** Events are enqueued non-blocking in `send()` and flushed by a daemon thread. All events queued during a `batch_ms` window are included in one POST body as a JSON array.

**Retry behaviour:** Failed POSTs (5xx responses or connection errors) are retried up to 3 times with exponential backoff (0.5s → 1s → 2s, capped at 8s; 4 total attempts). After retries are exhausted the batch is dropped with a warning — exceptions never propagate to the caller.

**Shutdown:** `close()` signals the daemon thread to stop, performs one final flush of any queued events, then joins the thread with a 10s timeout.

```json
{
  "events": {
    "transports": ["jsonl", "webhook"],
    "webhook": {
      "url": "https://hooks.example.com/ll-events",
      "batch_ms": 1000,
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

### `events.sqlite`

Records FSM loop events into the per-project session store (`.ll/history.db`) for indexed cross-cutting queries via the `ll-session` CLI.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `events.sqlite.path` | `string` | `".ll/history.db"` | Filesystem path for the SQLite session database. |

**Env-var override**: `LL_HISTORY_DB` takes precedence if set (e.g. for test isolation).

The session store is a SQLite database with an FTS5 full-text index. `SQLiteTransport` writes events as they are emitted; `ll-session search`/`recent`/`backfill` query and seed it. As of ENH-1691, `ll-auto` writes issue lifecycle events live via `AutoManager`'s internal transport — no additional config is required. Use `ll-session backfill` to import historical data captured before ENH-1691. As of ENH-1830, `session_start` automatically triggers an incremental backfill in a background thread for each interactive session, so new data is indexed without manual intervention.

```json
{
  "events": {
    "transports": ["jsonl", "sqlite"],
    "sqlite": {
      "path": ".ll/history.db"
    }
  }
}
```

See [API Reference → little_loops.transport](API.md#little_loopstransport) for the `Transport` Protocol and how to author custom transports.

#### `history.compaction`

LCM-style three-level compaction for `summary_nodes` (FEAT-1712). Controls whether `ll-session backfill` generates LLM summaries over `message_events` blocks and stores them as a summary DAG. **Disabled by default** to avoid background LLM calls without user opt-in.

**Three-level LCM Algorithm 3 escalation:** When enabled, each block of message events is summarized progressively:

1. **Level 1 — Normal LLM summary** (default, up to `budget_tokens`): A standard LLM call generates a concise summary of the message block. If the summary is within budget and converged, it stops here.
2. **Level 2 — Aggressive bullet-point LLM**: If Level 1 produces more than one summary paragraph (or exceeds half the budget), a second LLM call condenses the output into tight bullet points.
3. **Level 3 — Deterministic truncation**: If Level 2 still produces >1 paragraph (or the LLM is unavailable), the summarizer falls back to a deterministic character-based truncation — no LLM call. This guarantees termination without runaway costs.

Each summary is stored as a node in `summary_nodes`. Condensed nodes receive `parent_id` linkage back to their source leaves, forming an N-level DAG traversal path. `ll-session grep` and `ll-session expand` use a recursive CTE to drill from any condensed node (at any depth) through descendant leaves back to source messages.

**Cross-session recursive condensation (ENH-1954):** When `cross_session_enabled` is `true` (default), the compaction pass recurses over existing condensed nodes level by level after per-session compaction finishes. At each level, condensed nodes are grouped by token budget (same greedy algorithm as per-session block accumulation), summarised, and inserted as higher-order condensed nodes (`session_id=NULL`, `level=1+`). Recursion continues until exactly one project-root summary node remains — providing a single, top-level summary of the entire project's session history. Set `max_level` to cap the recursion depth.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `history.compaction.enabled` | `boolean` | `false` | Gate flag — set `true` to enable LLM summarization during backfill. |
| `history.compaction.budget_tokens` | `integer` | `4096` | Token budget per summary node. |
| `history.compaction.model` | `string\|null` | `null` | Model override for summary generation; `null` uses the session default. |
| `history.compaction.timeout` | `integer` | `60` | Timeout in seconds for each LLM summarization call. |
| `history.compaction.cross_session_enabled` | `boolean` | `true` | Enable recursive cross-session condensation (ENH-1954). Set `false` to preserve pre-ENH-1954 per-session-only behavior. |
| `history.compaction.max_level` | `integer\|null` | `null` | Maximum condensation depth. `null` means no limit — recurses until one root remains. |

```json
{
  "history": {
    "compaction": {
      "enabled": true,
      "budget_tokens": 4096,
      "model": null,
      "timeout": 60,
      "cross_session_enabled": true,
      "max_level": null
    }
  }
}
```

---

## Manual Configuration

The following fields are defined in `config-schema.json` but are not exposed through `ll-init` or `/ll:configure`. To set them, edit `.ll/ll-config.json` directly. All have sensible defaults and rarely need changing.

> **Re-init preserves these.** Re-running `ll-init` (without `--force`) deep-merges the regenerated config over your existing one, so any manually-set values here — and any other keys `ll-init` does not model — survive. Pass `--force` to reset to template defaults and drop them.

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

> **Behavioral note:** These settings are active when `ll-goals.md` is absent — `max_files` limits how many files are read during discovery; `required_files` entries trigger a warning if missing but never block analysis.

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
