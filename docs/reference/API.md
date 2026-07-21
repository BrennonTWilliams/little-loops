# API Reference

This document provides the public API for the little-loops Python package.

> **Related Documentation:**
> - [Architecture Overview](../ARCHITECTURE.md) - System design and diagrams
> - [Troubleshooting](../development/TROUBLESHOOTING.md) - Common issues and diagnostic commands
> - [README](../../README.md) - Installation and quick start

## Installation

```bash
# End users
pip install little-loops

# Contributors (editable install with test dependencies)
pip install -e "./scripts[dev]"
```

## Module Overview

| Module | Purpose |
|--------|---------|
| `little_loops.config` | Configuration management |
| `little_loops.issue_parser` | Issue file parsing |
| `little_loops.issue_discovery` | Issue discovery and deduplication |
| `little_loops.issue_manager` | Sequential automation |
| `little_loops.issue_lifecycle` | Issue lifecycle operations |
| `little_loops.issue_history` | Issue history and statistics |
| `little_loops.git_operations` | Git utilities |
| `little_loops.dependency_graph` | Dependency graph construction |
| `little_loops.dependency_mapper` | Cross-issue dependency discovery and mapping (sub-package: `models`, `analysis`, `formatting`, `operations`) |
| `little_loops.work_verification` | Verification helpers |
| `little_loops.context_window` | Model→context-window size mapping (`context_window_for()`) |
| `little_loops.subprocess_utils` | Subprocess handling |
| `little_loops.host_runner` | Host-agnostic CLI invocation layer (`HostRunner` Protocol + `ClaudeCodeRunner` + `CodexRunner` + `GeminiRunner` + `OmpRunner` + `OpenCodeRunner` + `PiRunner`) |
| `little_loops.adapters` | Host-parameterised emitter layer (`HostEmitter` Protocol + `resolve_emitter` registry factory) — `CodexEmitter` and `GeminiEmitter` fully implemented (FEAT-2391/2392) |
| `little_loops.state` | State persistence |
| `little_loops.events` | Structured events and EventBus dispatcher |
| `little_loops.hooks` | Host-agnostic hook intent dispatcher and built-in handlers |
| `little_loops.extension` | Extension protocol, loader, and reference implementation |
| `little_loops.testing` | Offline test harness (LLTestBus) for extension development |
| `little_loops.logger` | Logging utilities |
| `little_loops.logo` | CLI logo display |
| `little_loops.frontmatter` | YAML frontmatter read/write utilities |
| `little_loops.decisions` | Decisions and rules log data layer (FEAT-1891) |
| `little_loops.decisions_sync` | Sync active required rules to `.ll/ll.local.md` |
| `little_loops.learning_tests` | Learning test registry — CRUD for `.ll/learning-tests/` records |
| `little_loops.doc_counts` | Documentation count verification |
| `little_loops.link_checker` | Link validation for markdown docs |
| `little_loops.user_messages` | User message extraction from Claude logs |
| `little_loops.workflow_sequence` | Workflow sequence analysis for multi-step patterns |
| `little_loops.goals_parser` | Product goals file parsing |
| `little_loops.history_reader` | Typed read-only query module for `.ll/history.db`. Exports event dataclasses including `UserCorrection`, `FileEvent`, `SearchResult`, `IssueEvent`, `SessionRef` (ENH-1711), `OrchestrationRun` (ENH-2492), `LoopRun` (ENH-2463), `LearningTestEvent` (ENH-2466), and `LifecycleEvent` (ENH-2495); query functions include `find_user_corrections()`, `recent_file_events()`, `search()`, `related_issue_events()`, `sessions_for_issue()`, effort/velocity/session metadata helpers, conversation and compaction readers, skill/commit/test/usage readers, plus `recent_orchestration_runs()` / `aggregate_orchestration_runs()` (ENH-2492), `recent_loop_runs()` / `find_loop_run()` / `aggregate_loop_runs()` (ENH-2463), `recent_learning_tests()` / `find_learning_test()` (ENH-2466), and `recent_lifecycle_events()` / `handoff_frequency()` (ENH-2495). All functions return empty lists or `None` on missing/corrupt DB. |
| `little_loops.sync` | GitHub Issues bidirectional sync |
| `little_loops.session_log` | Session log linking for issue files |
| `little_loops.file_utils` | Shared file I/O utilities (atomic writes) |
| `little_loops.text_utils` | Text extraction utilities for issue content |
| `little_loops.pii` | PII detection and redaction utilities (`detect_pii`, `redact_pii`, `apply_pii_action`) |
| `little_loops.cli` | CLI entry points (package) |
| `little_loops.parallel` | Parallel processing subpackage |
| `little_loops.fsm` | FSM loop system subpackage |
| `little_loops.loops` | Loop YAML utilities subpackage (`yaml_state_editor`: round-trip `extract_action`/`replace_action`) |
| `little_loops.cli_args` | CLI argument parsing utilities |
| `little_loops.sprint` | Sprint planning and execution |
| `little_loops.issue_template` | Issue template assembly for sync pull (v2.0-compliant markdown from per-type section files) |
| `little_loops.output_parsing` | Claude CLI output parsing utilities used by `issue_manager` and `parallel` |
| `little_loops.output.parse` | Stop-sequence / prefill JSON output helpers (`extract_between_tags`, `parse_prefilled_json`) that bound LLM output-token cost |
| `little_loops.output_cleaner` | Anti-event + duplicate-window pre-filter (`filter_output`) that trims tool/log noise before it enters context |
| `little_loops.ab_writer` | A/B baseline results aggregation and `ab.json` writer (FEAT-1790). Provides `ABResults` dataclass + summary calculation + JSON schema generation. |
| `little_loops.cache_marking_oracle` | Cache-marking cost oracle (FEAT-2673, EPIC-2456 F1) — decides whether a stable prompt block is safe to mark `cache_control: ephemeral` via a per-model token-floor gate plus a `FragmentStore` reuse-repeat gate. |
| `little_loops.analytics` | Analytics subpackage — association-rule mining (lift/PMI) and per-evaluator Bernoulli variance for loop diagnostics. |
| `little_loops.design_tokens` | Multi-layer token loader (primitives → semantic → typography → spacing → theme) with profile-aware resolution (ENH-1768). Renders `{token.reference}` aliases for prompts and CSS. |
| `little_loops.extensions` | Reference extension implementations — `ReferenceInterceptorExtension` copy-paste starting point for custom interceptors / event handlers. |
| `little_loops.issue_progress` | EPIC progress aggregation: child-issue status rollup (`IssueProgress`), oldest-open detection, and `epic-progress` CLI support. |
| `little_loops.issues` | Issue utility subpackage — anchor generation and sweep utilities used by `ll-issues anchor-sweep`. |
| `little_loops.observability` | DES variant registry and audit-tree walker for cross-checking every emit site against registered event shapes (ENH-2475, F5 adoption gate). |
| `little_loops.output` | Output-parsing subpackage — stop-sequence / prefill JSON helpers (`extract_between_tags`, `parse_prefilled_json`) for bounding LLM output-token cost (FEAT-2470). |
| `little_loops.pricing` | Model pricing constants (USD per million tokens) for token cost estimation across the model registry. |
| `little_loops.pytest_history_plugin` | Pytest plugin (registered under `pytest11` entry point) that records test-run pass/fail counts, duration, and failing node IDs into `.ll/history.db` (ENH-2459). |
| `little_loops.queue_store` | Persisted `ll-queue` entry store (`.ll/queue.db`; FEAT-2682) — schema `{id, action, enqueuedAt, priority, status, result}` with tiered `(priority, enqueuedAt)` ordering. |
| `little_loops.recursive_finalize` | Decomposed-parent lifecycle and EPIC re-linking. Powers `ll-issues finalize-decomposition` (ENH-1977 Fix 4), invoked from `rn-decompose` and `autodev`'s decomposition states (ENH-2615). |
| `little_loops.session_store` | Unified per-project SQLite + FTS5 history store (`.ll/history.db`; FEAT-1112) — single source of truth for tool events, file modifications, issue transitions, loop runs, and user corrections. |
| `little_loops.sft_formatter` | SFT (supervised fine-tuning) data format converters — ChatML and siblings — used by `ll-messages --sft-format`. |
| `little_loops.skill_expander` | Pre-expand skill/command Markdown content for subprocess prompts (replaces ToolSearch → Skill deferred-tool dependency in `ll-auto`). |
| `little_loops.stats` | Statistical utilities — Wilson 95% binomial confidence intervals for honest uncertainty reporting at small sample sizes. |
| `little_loops.transport` | EventBus transport abstraction (`Transport` Protocol + `send`/`close`) with built-in `JsonlTransport`, `UnixSocketTransport`, and `OTelTransport` sinks. |
| `little_loops.worktree_utils` | Shared worktree setup/cleanup utilities used by `ll-parallel`, `ll-sprint`, and `ll-loop`. |
| `little_loops.mcp_call` | Thin CLI wrapper for direct MCP tool invocation via JSON-RPC |

---

## little_loops.config

Configuration management for little-loops projects.

### BRConfig

Main configuration class that loads and provides access to project settings.

```python
from pathlib import Path
from little_loops.config import BRConfig

config = BRConfig(Path.cwd())
print(config.project.src_dir)  # "src/"
print(config.issues.base_dir)  # ".issues"
```

#### Constructor

```python
BRConfig(project_root: Path)
```

**Parameters:**
- `project_root` - Path to the project root directory

**Behavior:**
- Loads `.ll/ll-config.json` if present
- Merges with sensible defaults
- Creates typed config objects

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `project` | `ProjectConfig` | Project-level settings |
| `issues` | `IssuesConfig` | Issue management settings |
| `automation` | `AutomationConfig` | Sequential automation settings |
| `parallel` | `ParallelAutomationConfig` | Parallel automation settings |
| `commands` | `CommandsConfig` | Command customization (includes `confidence_gate: ConfidenceGateConfig`, `tdd_mode: bool`, `rate_limits: RateLimitsConfig`) |
| `scan` | `ScanConfig` | Codebase scanning settings |
| `sprints` | `SprintsConfig` | Sprint management settings |
| `loops` | `LoopsConfig` | FSM loop settings |
| `sync` | `SyncConfig` | GitHub Issues sync settings |
| `dependency_mapping` | `DependencyMappingConfig` | Overlap detection thresholds |
| `code_query` | `CodeQueryConfig` | Code-query provider selection, codegraph db path, and staleness policy (inert until a provider consumes it, see [CONFIGURATION.md#code_query](CONFIGURATION.md#code_query)) |
| `refine_status` | `RefineStatusConfig` | refine-status display settings |
| `cli` | `CliConfig` | CLI output settings (color toggle and color overrides) |
| `design_tokens` | `DesignTokensConfig` | Design system token settings |
| `orchestration` | `OrchestrationConfig` | Orchestration settings (host CLI selection, composer config, cluster config) |
| `events` | `EventsConfig` | Event transport/emission settings |
| `decisions` | `DecisionsConfig` | Decisions and rules log configuration |
| `learning_tests` | `LearningTestsConfig` | Learning test registry settings |
| `analytics_capture` | `AnalyticsCaptureConfig` | Analytics capture sub-settings (see [CONFIGURATION.md#analytics](CONFIGURATION.md#analytics)) |
| `history` | `HistoryConfig` | History.db consumer tuning (see [CONFIGURATION.md#history](CONFIGURATION.md#history)) |
| `extensions` | `list[str]` | Extension module paths to load |
| `repo_path` | `Path` | Resolved repository root path |
| `issue_categories` | `list[str]` | List of category names |
| `issue_priorities` | `list[str]` | List of priority prefixes |

#### CliConfig

Controls ANSI color output across all `ll-*` CLI tools.

```json
{
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
      }
    }
  }
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `cli.color` | `bool` | `true` | Enable ANSI color output. Set to `false` for CI or plain-text terminals. |
| `cli.colors.logger.*` | `str` | see above | Raw ANSI SGR codes for each log level (e.g. `"38;5;208"` for orange). |
| `cli.colors.priority.*` | `str` | see above | Raw ANSI SGR codes for priority labels P0–P5. |
| `cli.colors.type.*` | `str` | see above | Raw ANSI SGR codes for issue type labels BUG, FEAT, ENH, EPIC. |

**Notes:**
- Setting `NO_COLOR=1` in the environment disables color regardless of `cli.color`.
- Unspecified `cli.colors` sub-keys retain their defaults.
- Color values are raw SGR parameter strings (e.g. `"32"`, `"38;5;208"`, `"1;34"`).

#### DesignTokensConfig

Controls design system token injection into FSM loops. See [CONFIGURATION.md → `design_tokens`](CONFIGURATION.md#design_tokens) for setup guidance.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable design-token context injection into FSM loops. |
| `path` | `str` | `".ll/design-tokens"` | Directory containing token definition files. |
| `primitives_file` | `str` | `"primitives.json"` | Filename for primitive (raw) token values within `path`. |
| `semantic_file` | `str` | `"semantic.json"` | Filename for semantic (aliased) token values within `path`. |
| `themes_dir` | `str` | `"themes"` | Subdirectory of `path` containing per-theme override files. |
| `active_theme` | `str` | `"dark"` | Name of the active theme; must match a file in `themes_dir`. |
| `active` | `str` | `"default"` | Active design token profile name; selects a bundled profile under `<path>/<profiles_dir>/<active>/`. |
| `profiles_dir` | `str \| None` | `None` | Subdirectory of `path` containing per-profile layouts (ENH-1768). `None` falls back to the legacy flat layout (`<path>/primitives.json`, etc.). |

#### DecisionsConfig

Controls the decisions and rules log. See [CONFIGURATION.md → `decisions`](CONFIGURATION.md#decisions) for setup guidance.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `False` | Enable the decisions log feature. When `False`, all integrations gracefully skip. |
| `log_path` | `str` | `".ll/decisions.yaml"` | Path to the legacy flat decisions file, relative to the project root. The append-only fragment directory is derived as its `.d`-suffixed sibling (`.ll/decisions.d/`); reads union both tiers. |
| `auto_generate` | `list[str]` | `[]` | Issue type prefixes to include during `ll-issues decisions generate` (e.g., `["FEAT", "ENH"]`). Empty list (default) generates entries for all completed issue types. |

#### Methods

##### get_issue_dir

```python
def get_issue_dir(self, category: str) -> Path
```

Get the directory path for an issue category.

**Parameters:**
- `category` - Category key (e.g., `"bugs"`, `"features"`)

**Returns:** `Path` to the issue category directory

**Example:**
```python
bugs_dir = config.get_issue_dir("bugs")
# Returns: Path(".issues/bugs")
```

##### get_issue_prefix

```python
def get_issue_prefix(self, category: str) -> str
```

Get the issue ID prefix for a category.

**Parameters:**
- `category` - Category key

**Returns:** Issue prefix (e.g., `"BUG"`, `"FEAT"`)

##### get_category_action

```python
def get_category_action(self, category: str) -> str
```

Get the default action for a category.

**Parameters:**
- `category` - Category key

**Returns:** Action verb (e.g., `"fix"`, `"implement"`)

##### create_parallel_config

```python
def create_parallel_config(
    self,
    *,
    max_workers: int | None = None,
    priority_filter: list[str] | None = None,
    max_issues: int = 0,
    dry_run: bool = False,
    timeout_seconds: int | None = None,
    idle_timeout_per_issue: int | None = None,
    stream_output: bool | None = None,
    show_model: bool | None = None,
    only_ids: set[str] | None = None,
    skip_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
    label_filter: set[str] | None = None,
    merge_pending: bool = False,
    clean_start: bool = False,
    ignore_pending: bool = False,
    overlap_detection: bool = False,
    serialize_overlapping: bool = True,
    base_branch: str | None = None,
    remote_name: str | None = None,
    use_feature_branches: bool | None = None,
    skip_learning_gate: bool = False,
    epic_branches: EpicBranchesConfig | None = None,
) -> ParallelConfig
```

`epic_branches` accepts an `EpicBranchesConfig` override (from
`little_loops.config.automation`); when `None` the value falls back to
`parallel.epic_branches` in config. CLI callers build the override with
`dataclasses.replace(config.parallel.epic_branches, enabled=<flag>)` so the
`--epic-branches` / `--no-epic-branches` flag toggles only `enabled` while
preserving the configured `prefix` / `merge_to_base_on_complete` / `open_pr`.

Create a `ParallelConfig` from BRConfig settings with optional overrides.

**Parameters:**
- `max_workers` - Override max workers (default: from config)
- `priority_filter` - Override priority filter
- `max_issues` - Maximum issues to process (0 = unlimited)
- `dry_run` - Preview mode without processing
- `timeout_seconds` - Per-issue timeout in seconds
- `idle_timeout_per_issue` - Kill worker if no output for N seconds (0 to disable)
- `stream_output` - Stream Claude output
- `show_model` - Display model info on setup
- `only_ids` - If provided, only process these issue IDs
- `skip_ids` - Issue IDs to skip (in addition to completed/failed)
- `type_prefixes` - If provided, only process issues with these type prefixes
- `label_filter` - If provided, only process issues with one of these labels
- `merge_pending` - Attempt to merge pending worktrees from previous runs
- `clean_start` - Remove all worktrees without checking for pending work
- `ignore_pending` - Report pending work but continue without merging
- `overlap_detection` - Enable pre-flight overlap detection
- `serialize_overlapping` - If True, defer overlapping issues; if False, just warn
- `base_branch` - Base branch for rebase/merge operations (default: from `parallel.base_branch` config)
- `remote_name` - Git remote name (default: from `parallel.remote_name` config)
- `use_feature_branches` - Override `parallel.use_feature_branches` config
- `skip_learning_gate` - Bypass per-worktree proof-first-task gate

**Returns:** Configured `ParallelConfig`

**Example:**
```python
parallel_config = config.create_parallel_config(
    max_workers=4,
    max_issues=10,
    dry_run=True
)
```

##### to_dict

```python
def to_dict(self) -> dict[str, Any]
```

Convert configuration to dictionary for variable substitution.

**Returns:** Dictionary representation of all config values

##### resolve_variable

```python
def resolve_variable(self, var_path: str) -> str | None
```

Resolve a variable path like `project.src_dir` to its value.

**Parameters:**
- `var_path` - Dot-separated path to configuration value

**Returns:** The resolved value as a string, or `None` if not found

---

### ProjectConfig

Project-level configuration dataclass.

```python
@dataclass
class ProjectConfig:
    name: str = ""
    src_dir: str = "src/"
    test_dir: str = "tests"
    test_cmd: str = "pytest"
    lint_cmd: str = "ruff check ."
    type_cmd: str | None = "mypy"
    format_cmd: str | None = "ruff format ."
    build_cmd: str | None = None
    run_cmd: str | None = None
    health_url: str | None = None
```

### IssuesConfig

Issue management configuration dataclass.

```python
@dataclass
class IssuesConfig:
    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig]
    completed_dir: str = "completed"  # DEPRECATED: use IssueInfo.status instead
    deferred_dir: str = "deferred"  # DEPRECATED: use IssueInfo.status instead
    priorities: list[str]  # ["P0", "P1", ...]
    templates_dir: str | None = None
    capture_template: str = "full"
    duplicate_detection: DuplicateDetectionConfig  # thresholds for skip/update/create
    next_issue: NextIssueConfig  # selection strategy for ll-issues next-issue / next-issues
    auto_commit: bool = False
    auto_commit_prefix: str = "chore(issues)"
```

### DuplicateDetectionConfig

Thresholds controlling duplicate issue detection behavior.

```python
@dataclass
class DuplicateDetectionConfig:
    exact_threshold: float = 0.8   # score >= this → skip (duplicate)
    similar_threshold: float = 0.5  # score >= this → update existing issue
```

### NextIssueConfig

Selection behavior for `ll-issues next-issue` / `next-issues` commands. Named strategies map to preset sort orderings; an explicit `sort_keys` list overrides the preset.

```python
@dataclass
class NextIssueConfig:
    strategy: str = "confidence_first"   # "confidence_first" | "priority_first"
    sort_keys: list[NextIssueSortKey] | None = None  # custom sort, overrides strategy

@dataclass
class NextIssueSortKey:
    key: str         # "priority" | "outcome_confidence" | "confidence_score" |
                     # "effort" | "impact" | "score_complexity" |
                     # "score_test_coverage" | "score_ambiguity" | "score_change_surface"
    direction: str = "asc"  # "asc" | "desc"
```

Strategy presets:
- `confidence_first` (default): `(-outcome_confidence, -confidence_score, priority_int)` — byte-identical to the legacy hardcoded ordering.
- `priority_first`: `(priority_int, -outcome_confidence, -confidence_score)`.

None-handling (per-field sentinel): `direction="desc"` → component is `-value` when set, `1` when `None` (sorts after negatives); `direction="asc"` → component is `value` when set, `9999` when `None` (sorts last).

`NextIssueConfig.from_dict` validates `strategy` and each `sort_keys[*].key` against the allowed enum, raising `ValueError` on unknown values.

### CategoryConfig

Configuration for an issue category.

```python
@dataclass
class CategoryConfig:
    prefix: str      # e.g., "BUG"
    dir: str         # e.g., "bugs"
    action: str      # e.g., "fix"
```

### AutomationConfig

Sequential automation configuration.

```python
@dataclass
class AutomationConfig:
    timeout_seconds: int = 3600
    idle_timeout_seconds: int = 0  # Kill if no output for N seconds (0 to disable)
    post_stream_close_grace_seconds: int = 300  # Grace before force-kill after streams close
    state_file: str = ".auto-manage-state.json"
    worktree_base: str = ".worktrees"
    max_workers: int = 2
    stream_output: bool = True
    max_continuations: int = 3  # Max session restarts on context handoff
```

### ParallelAutomationConfig

Parallel automation configuration stored in BRConfig using composition.

Uses `AutomationConfig` for shared settings (max_workers, worktree_base, state_file, timeout_seconds, stream_output) plus parallel-specific fields.

```python
@dataclass
class ParallelAutomationConfig:
    base: AutomationConfig  # Shared automation settings
    p0_sequential: bool = True
    max_merge_retries: int = 2
    command_prefix: str = "/ll:"
    ready_command: str = "ready-issue {{issue_id}}"
    manage_command: str = "manage-issue {{issue_type}} {{action}} {{issue_id}}"
    decide_command: str = "decide-issue {{issue_id}}"
    worktree_copy_files: list[str] = field(default_factory=lambda: [".claude/settings.local.json", ".env"])
    require_code_changes: bool = True
    use_feature_branches: bool = False
    push_feature_branches: bool = False
    open_pr_for_feature_branches: bool = False
    base_branch: str = "main"
    remote_name: str = "origin"
```

**Fields:**
- `decide_command` - Command template for automated decision resolution
- `worktree_copy_files` - Files copied from main repo to each worktree
- `require_code_changes` - Fail issues that don't produce code changes
- `use_feature_branches` - Create `feature/<id>-<slug>` branches instead of auto-merged worktree branches; skips auto-merge, leaving branches as PR-ready
- `push_feature_branches` - Push feature branches to remote after creation
- `open_pr_for_feature_branches` - Open a PR automatically for each feature branch
- `base_branch` - Base branch for rebase/merge operations (default: `None` — auto-detected at runtime as `origin/HEAD` → current branch → `main`)
- `remote_name` - Git remote name for fetch/pull operations (default: `"origin"`)

**Note:** Shared fields from `AutomationConfig` are accessed via `base.*`:
- `base.max_workers` - Maximum parallel workers (default: 2)
- `base.worktree_base` - Base directory for worktrees (default: ".worktrees")
- `base.state_file` - State file path (default: ".parallel-manage-state.json")
- `base.timeout_seconds` - Per-issue timeout in seconds (default: 3600)
- `base.stream_output` - Stream subprocess output (default: False for parallel)

### SprintsConfig

Sprint management configuration.

```python
@dataclass
class SprintsConfig:
    sprints_dir: str = ".sprints"                 # Directory for sprint YAML files
    default_timeout: int = 3600                   # Default per-issue timeout in seconds
    default_max_workers: int = 2                  # Default worker count for wave execution
    max_issue_wall_clock_time: int = 2700         # Max wall-clock seconds per issue before forced handoff
```

### LoopsConfig

FSM loop configuration.

```python
@dataclass
class LoopsConfig:
    loops_dir: str = ".loops"                    # Directory for loop YAML definitions
    queue_wait_timeout_seconds: int = 86400      # Max seconds to wait for a queue item
    glyphs: LoopsGlyphsConfig                    # Unicode badge overrides for FSM box diagrams
    run_defaults: LoopRunDefaults                # Persistent CLI defaults for ll-loop run
```

### LoopRunDefaults

Persistent CLI defaults for `ll-loop run`. Values are backfilled when the corresponding flag is absent; explicit CLI flags always take precedence.

```python
@dataclass
class LoopRunDefaults:
    clear: bool = False           # If True, inject --clear into every ll-loop run invocation
    show_diagrams: str | None = None  # Inject --show-diagrams <value>; 'default' = bare flag; None = disabled
    mode: str | None = None       # Reserved for a future --mode flag
    include: str = ""             # Default loop allowlist injected into fsm.context; empty = all loops visible
    delay: float | None = None    # Inject --delay <seconds> inter-iteration pause; None = disabled
```

`include` accepts comma-separated selectors: `loop-name`, `builtin:*`, `project:*`, `category:<label>`. Set in `ll-config.json` as `loops.run_defaults.include`; override per-invocation with `--context include=VALUE`.

`delay` injects `--delay <seconds>` (a non-negative inter-iteration pause) when `--delay` is absent on the CLI; an explicit `--delay` always wins, and `null` disables injection.

### GitHubSyncConfig

GitHub-specific sync configuration.

```python
@dataclass
class GitHubSyncConfig:
    repo: str | None = None                    # GitHub repo slug (owner/repo); auto-detected if None
    label_mapping: dict[str, str] = {          # Issue type → GitHub label
        "BUG": "bug",
        "FEAT": "enhancement",
        "ENH": "enhancement",
        "EPIC": "epic",
    }
    priority_labels: bool = True               # Sync priority as GitHub labels
    sync_completed: bool = False               # Include completed issues in sync
    state_file: str = ".ll/ll-sync-state.json"  # Sync state file path
    pull_template: str = "minimal"             # Template for pulled issues ("minimal" | "full")
    pull_limit: int = 500                      # Max issues to fetch from GitHub per pull (ENH-825)
```

> **Note**: When `pull_issues()` returns exactly `pull_limit` results, a warning is logged indicating the results may be truncated. Increase `sync.github.pull_limit` in `ll-config.json` if you have more issues than the default limit.

### SyncConfig

Issue sync configuration.

```python
@dataclass
class SyncConfig:
    enabled: bool = False
    provider: str = "github"
    github: GitHubSyncConfig = GitHubSyncConfig()
```

### ScoringWeightsConfig

Scoring weights for semantic conflict analysis. Used by `DependencyMappingConfig`.

```python
@dataclass
class ScoringWeightsConfig:
    semantic: float = 0.5    # Weight for semantic target overlap (component/function names)
    section: float = 0.3     # Weight for section mention overlap (UI regions)
    type: float = 0.2        # Weight for modification type match
```

Weights should sum to 1.0 for normalized scoring.

### DependencyMappingConfig

Dependency mapping threshold configuration. Controls overlap detection sensitivity and conflict scoring.

```python
@dataclass
class DependencyMappingConfig:
    overlap_min_files: int = 2                 # Minimum overlapping files to trigger overlap
    overlap_min_ratio: float = 0.25            # Minimum ratio of overlapping to smaller file set
    min_directory_depth: int = 2               # Minimum path segments for directory overlap
    conflict_threshold: float = 0.4            # Below = parallel-safe, above = dependency proposed
    high_conflict_threshold: float = 0.7       # Above = HIGH conflict label
    confidence_modifier: float = 0.5           # Applied when dependency direction is ambiguous
    scoring_weights: ScoringWeightsConfig      # Weights for semantic/section/type signals
    exclude_common_files: list[str]            # Infrastructure files excluded from overlap detection
```

**Overlap detection AND semantics**: An issue pair is considered overlapping only when **both** `overlap_min_files` and `overlap_min_ratio` thresholds are met simultaneously. This prevents false serialization for pairs that share many small files (high file count, low ratio) or few files from a large set (low file count, high ratio). Lower either threshold to serialize more aggressively; raise both to parallelize more.

### RefineStatusConfig

Configuration for the `ll-issues refine-status` display.

```python
@dataclass
class RefineStatusConfig:
    columns: list[str] = []       # Column names to include (empty = all default columns)
    elide_order: list[str] = []   # Column drop sequence for narrow terminals (empty = default order)
```

---

## little_loops.issue_parser

Issue file parsing utilities.

### IssueInfo

Parsed information from an issue file.

```python
@dataclass
class IssueInfo:
    path: Path                              # Path to the issue file
    issue_type: str                         # e.g., "bugs"
    priority: str                           # e.g., "P1"
    issue_id: str                           # e.g., "BUG-123"
    title: str                              # Issue title
    blocked_by: list[str] = []             # Issue IDs that block this issue (hard dependency — wave-gated)
    blocks: list[str] = []                 # Issue IDs that this issue blocks (computed inverse of blocked_by)
    parent: str | None = None              # Parent issue ID this was decomposed from (e.g., "ENH-179")
    depends_on: list[str] = []            # Soft ordering prerequisites (wave-gated: scheduled after; non-fatal if absent)
    relates_to: list[str] = []            # Thematically related issue IDs (no ordering constraint)
    duplicate_of: str | None = None        # Issue ID this duplicates; set when closing a duplicate
    discovered_by: str | None = None       # Source command/workflow that created this issue
    epic: str | None = None                # Epic issue ID this child belongs to (e.g., "EPIC-001")
    base_branch: str | None = None         # For EPIC issues, the fork base for the integration branch; from frontmatter `base_branch:` or alias `target_branch:`; None means fall back to `parallel.base_branch` (FEAT-2652)
    product_impact: ProductImpact | None = None  # Product impact assessment
    effort: int | None = None              # Effort estimate (1=low, 2=medium, 3=high)
    impact: int | None = None              # Impact estimate (1=low, 2=medium, 3=high)
    confidence_score: int | None = None    # Readiness score (0-100) from /ll:confidence-check
    outcome_confidence: int | None = None  # Outcome confidence (0-100) from /ll:confidence-check
    score_complexity: int | None = None    # Outcome criterion A – Complexity (0-25; Breadth 0-12 + Depth 0-13) from /ll:confidence-check
    score_test_coverage: int | None = None # Outcome criterion B – Test Coverage (0-25) from /ll:confidence-check
    score_ambiguity: int | None = None     # Outcome criterion C – Ambiguity (0-25) from /ll:confidence-check
    score_change_surface: int | None = None # Outcome criterion D – Change Surface / Fanout Verifiability (0-25; Pattern A blast-radius or Pattern B enumerated mechanical fanout) from /ll:confidence-check
    size: str | None = None               # Issue size from /ll:issue-size-review (Small, Medium, Large, Very Large)
    testable: bool | None = None           # False = skip TDD phase; None = treat as testable
    decision_needed: bool | None = None    # Set to true by /ll:refine-issue (2+ options) or /ll:confidence-check (unresolved decision); cleared by /ll:decide-issue
    missing_artifacts: bool | None = None  # Set to true by /ll:confidence-check (Phase 4.7) when absent pre-condition files detected; suppressed for co-deliverable files in Files to Create
    implementation_order_risk: bool | None = None  # Set to true by /ll:confidence-check (Phase 4.9) when ordering advice detected (e.g., "implement tests first"); not a wiring gap
    learning_tests_required: list[str] | None = None  # Declared assumptions about external systems; /ll:ready-issue and /ll:confidence-check (Phase 1.5) each check via ll-learning-tests check
    session_commands: list[str] = []       # Distinct /ll:* commands in ## Session Log
    session_command_counts: dict[str, int] = {}  # Per-command occurrence counts
    labels: list[str] = []                 # Labels from `labels:` frontmatter field
    milestone: str | None = None           # Sprint or milestone name; None if unassigned
    status: str = "open"                   # Lifecycle status from frontmatter: open | in_progress | blocked | deferred | done | cancelled
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `priority_int` | `int` | Priority as integer (0=P0, 1=P1, etc.) |

#### Methods

```python
def to_dict(self) -> dict[str, Any]
```
Convert to dictionary for JSON serialization.

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> IssueInfo
```
Create from dictionary.

#### Confidence-Check Score Rubrics (Outcome Criteria A & D)

The `score_complexity` and `score_change_surface` fields are composite scores produced by `/ll:confidence-check`. They were refactored in ENH-1413 and ENH-1412 respectively into sub-axis structures:

**Criterion A — Complexity (0–25 = Breadth 0–12 + Depth 0–13)** _(ENH-1413)_

- **Breadth** scores how many files/components the change touches (detected by enumeration in the issue's integration map).
- **Depth** scores how complex the change is per-site (detected from change-description language: "rewrite", "refactor", "new abstraction" → high; "rename", "add flag", "extend table" → low).
- Risk factors phrase concerns by the dominant axis ("wide-shallow" vs "narrow-deep").

**Criterion D — Change Surface / Fanout Verifiability (0–25)** _(ENH-1412)_

Dual-pattern rubric — the issue is scored under whichever pattern fits:

- **Pattern A — Code blast radius** (count-based): Score by how many files/symbols the change ripples to. Used for novel changes whose effects cannot be enumerated up-front.
- **Pattern B — Enumerated mechanical fanout** (verifiability-based): Score by completeness of the verification chain (issue enumerates all sites + greppable invariant + automated test that asserts coverage). A complete chain earns a full score even with a large file count, because the change is mechanically verifiable.
- Phase 4.8 suppresses large-file-surface risk phrases when Pattern B's verification chain is complete.

See `skills/confidence-check/rubric.md` for the full rubric tables and output templates, and `skills/confidence-check/SKILL.md` for the phase definitions and flow.

### ProductImpact

Product impact assessment dataclass, stored as `IssueInfo.product_impact`.

```python
@dataclass
class ProductImpact:
    goal_alignment: str | None = None    # Strategic priority ID this supports
    persona_impact: str | None = None    # ID of affected persona
    business_value: str | None = None    # "high" | "medium" | "low"
    user_benefit: str | None = None      # Description of user benefit
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert to dictionary for JSON serialization |
| `from_dict(data)` | `ProductImpact \| None` | Create from dictionary; returns `None` if data is `None`/empty |

### IssueParser

Parses issue files based on project configuration.

```python
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
parser = IssueParser(config)
info = parser.parse_file(Path(".issues/bugs/P1-BUG-001-example.md"))

print(info.issue_id)  # "BUG-001"
print(info.priority)  # "P1"
print(info.title)     # "Example bug title"
```

#### Constructor

```python
IssueParser(config: BRConfig)
```

**Parameters:**
- `config` - Project configuration

#### Methods

##### parse_file

```python
def parse_file(self, issue_path: Path) -> IssueInfo
```

Parse an issue file to extract metadata.

**Parameters:**
- `issue_path` - Path to the issue markdown file

**Returns:** Parsed `IssueInfo`

### Helper Functions

#### is_normalized

```python
def is_normalized(filename: str) -> bool
```

Check whether an issue filename conforms to naming conventions.

**Parameters:**
- `filename` - The basename of the issue file (e.g. `"P2-BUG-010-my-issue.md"`)

**Returns:** `True` if filename matches `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$`

#### is_formatted

```python
def is_formatted(issue_path: Path, templates_dir: Path | None = None) -> bool
```

Check whether an issue file has been formatted to the template structure.

An issue is considered formatted if either:
1. Its `## Session Log` section contains a `/ll:format-issue` entry, **or**
2. All required sections for its type template are present as `##` headings. `Labels` is no longer a required body heading post-ENH-1392 (it moved to `labels:` frontmatter); `is_formatted()` derives this from the template, so no `## Labels` body section is needed.

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `templates_dir` - Optional override for the templates directory

**Returns:** `True` if the issue passes either criterion; `False` for files whose type cannot be determined or whose template cannot be loaded

#### check_format_gaps

```python
def check_format_gaps(issue_path: Path, templates_dir: Path | None = None) -> FormatGaps
```

Grade an issue's structural format gaps against its type template (ENH-2426). Deterministic (no LLM) — backs the `ll-issues format-check` subcommand and the `ensure_formatted` gate in `rn-remediate.yaml`. Unlike `is_formatted()`, this always runs the structural analysis; it does not honor the `/ll:format-issue` session-log shortcut, since every issue reaching the gate has already run that command.

Reports four gap classes on the returned `FormatGaps` dataclass (`missing`, `renamed`, `empty`, `boilerplate` — each a `list[str]`, plus a derived `has_gaps` property and a `to_dict()` for JSON output):
- **missing** — a required section header is absent from the body.
- **renamed** — a present section header is `deprecated: true` in the template with an extractable canonical replacement in its `deprecation_reason` (e.g. `"Proposed Fix" -> "Proposed Solution"`).
- **empty** — a required section header is present but its body is whitespace-only.
- **boilerplate** — a required section's body still equals its `creation_template` (whole-body match only, to avoid false positives on partially-filled sections).

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `templates_dir` - Optional override for the templates directory

**Returns:** A `FormatGaps` instance. Fails open (no gaps reported) when the file is unreadable, its type cannot be determined, or its template cannot be loaded — mirroring `is_formatted()`'s fail-open behavior.

#### count_enumerable_options

```python
def count_enumerable_options(content: str) -> int
```

Deterministic (no LLM) re-implementation of `skills/decide-issue/SKILL.md` Phase 3's
option-extraction patterns (ENH-2443). Backs the `ll-issues check-decidable` subcommand —
the FSM-facing companion to `/ll:decide-issue --validate-only`, mirroring how
`check_format_gaps` backs `ll-issues format-check`. Counts matches for the first pattern
tier (in precedence order: `### Option X` headers, `**Option X**` bold labels, numbered
`N. **Option`/`...approach` items, `- (x)`/`- Option X` bullets) that has any; widens to
`## Codebase Research Findings` / `## Implementation Status` when `## Proposed Solution`
yields 0, mirroring Phase 3's own widening.

**Parameters:**
- `content` - Full issue file text

**Returns:** Count of enumerable options found (0 when there is nothing to decide).

#### count_unresolved_options

```python
def count_unresolved_options(content: str) -> int
```

Coverage-aware sibling of `count_enumerable_options` (ENH-2446). Counts only the
`### Option X` / `**Option X: ...**` blocks in `## Proposed Solution` (with the same
fallback widening to `## Codebase Research Findings` / `## Implementation Status`) that
LACK a resolution marker — i.e. neither `> **Selected:**` callout nor `### Decision Rationale`
subsection within the block's boundary. An issue with resolved options PLUS unresolved
free-form questions is the coverage gap this probe catches (the count-based
`count_enumerable_options` returns 2 in that case; this returns 0). Backs the
`ll-issues check-open-questions` subcommand alongside `count_open_questions_in_sections`.

**Parameters:**
- `content` - Full issue file text

**Returns:** Count of unresolved (unmarked) option blocks. 0 means every enumerable
option in the issue has a `> **Selected:**` or `### Decision Rationale` marker.

#### count_open_questions_in_sections

```python
def count_open_questions_in_sections(content: str) -> int
```

Counts unresolved open questions in `## Edge Cases`, `## Confidence Check Notes`, and
`## Open Questions` sections (ENH-2446). An item is an "open question" if it is a
bullet or numbered list line carrying an open-question signal (`Q:` prefix, ends with
`?`, or contains `open question`, `needs decision`, `decision needed`, `open decision`,
`unresolved decision`, or `decision point`) AND lacks a resolved-question marker
(`✅ RESOLVED`, `✔ RESOLVED`, `**RESOLVED**`, or `> **RESOLVED**`). Mirrors the resolved-
question vocabulary already defined in `skills/decide-issue/SKILL.md:197` so both the
deterministic probe and the LLM skill read the same markers.

**Parameters:**
- `content` - Full issue file text

**Returns:** Count of unresolved open questions across the three target sections. 0 means
every bullet/numbered item is either resolved or not an open question.

#### QuestionGaps

```python
@dataclass
class QuestionGaps:
    unresolved_options: list[str]
    open_questions: list[str]
```

Typed return-value mirroring the `FormatGaps` shape (ENH-2446). Each list carries the
respective markers/headings; `has_gaps` is derived; `to_dict()` serializes for
`--format json`. Companion to `FormatGaps` for the coverage-aware decidability probe.

#### find_issues

```python
def find_issues(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: list[str] | set[str] | None = None,
    type_prefixes: set[str] | None = None,
    status_filter: set[str] | None = None,
    *,
    skip_blocked: bool = False,
) -> list[IssueInfo]
```

Find all issues matching criteria, sorted by priority.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter (e.g., `"bugs"`)
- `skip_ids` - Issue IDs to skip
- `only_ids` - If provided, only include these issue IDs. When a list, results are returned in list order; when a set, results are sorted by priority.
- `type_prefixes` - If provided, only include issues whose ID starts with one of these prefixes (e.g., `{"BUG", "ENH"}`)
- `status_filter` - If provided, only include issues whose status is in this set. When `None` (default), skips `done`/`cancelled`/`deferred` issues, preserving all existing caller behaviour.
- `skip_blocked` - Keyword-only. When `True` (ENH-2436), exclude issues whose `Blocked By` references a non-terminal (`done`/`cancelled`) issue. Default `False` is byte-identical to prior behaviour — no existing caller is affected.

**Returns:** List of `IssueInfo` sorted by priority

**Example:**
```python
from little_loops.issue_parser import find_issues

issues = find_issues(config, category="bugs")
for issue in issues:
    print(f"{issue.priority} {issue.issue_id}: {issue.title}")

# Skip blocked issues (ENH-2436)
ready = find_issues(config, skip_blocked=True)
```

#### find_highest_priority_issue

```python
def find_highest_priority_issue(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
) -> IssueInfo | None
```

Find the highest priority issue.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter
- `skip_ids` - Issue IDs to skip
- `only_ids` - If provided, only include these issue IDs
- `type_prefixes` - If provided, only include issues with these type prefixes

**Returns:** Highest priority `IssueInfo` or `None` if no issues found

#### get_next_issue_number

```python
def get_next_issue_number(config: BRConfig, category: str | None = None) -> int
```

Determine the next globally unique issue number across all issue types.

Scans ALL issue directories (active and any legacy completed/deferred) to find the highest existing number across ALL issue types (BUG, FEAT, ENH, EPIC). Issue numbers are globally unique regardless of type.

**Parameters:**
- `config` - Project configuration
- `category` - Unused; kept for backwards compatibility

**Returns:** Next available issue number (globally unique across all types)

#### slugify

```python
def slugify(text: str) -> str
```

Convert text to slug format for filenames.

**Parameters:**
- `text` - Text to convert

**Returns:** Lowercase slug with hyphens

---

## little_loops.issue_template

Issue template assembly using per-type section definition files.

### resolve_templates_dir

Return the templates directory using 4-tier precedence lookup.

```python
def resolve_templates_dir(config: BRConfig) -> Path
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `BRConfig` | Project configuration |

**Returns:** `Path` — resolved templates directory

**Precedence (highest to lowest):**

1. `config.issues.templates_dir` — explicit config override
2. `<project_root>/.ll/templates/` — project-deployed copy (written by `ll-init --deploy-templates`)
3. Bundled in-package `templates/` (always available)

Skills and commands that need template JSON should invoke `ll-issues sections <type>` (which calls this internally) rather than reading the template path directly. This ensures project-local overrides propagate correctly.

**Example:**

```python
from little_loops.issue_template import resolve_templates_dir
from little_loops.config import load_config

config = load_config()
templates_dir = resolve_templates_dir(config)
# Returns .ll/templates/ if deployed, otherwise bundled templates/
```

### load_issue_sections

Load per-type sections JSON from the resolved templates directory.

```python
def load_issue_sections(issue_type: str, templates_dir: Path | None = None) -> dict[str, Any]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue_type` | `str` | Issue type prefix (`BUG`, `FEAT`, `ENH`, `EPIC`) |
| `templates_dir` | `Path \| None` | Optional override path; defaults to bundled `templates/` |

**Returns:** `dict[str, Any]` — parsed JSON template data

**Raises:** `FileNotFoundError` if the per-type sections file does not exist.

---

## little_loops.dependency_graph

Dependency graph construction for issue scheduling based on `Blocked By` relationships.

### DependencyGraph

Represents a directed acyclic graph (DAG) of issue dependencies.

```python
from little_loops.dependency_graph import DependencyGraph
from little_loops.issue_parser import find_issues
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
issues = find_issues(config)
graph = DependencyGraph.from_issues(issues)

# Get issues ready to process (no active blockers)
ready = graph.get_ready_issues()

# Get execution waves for parallel processing
waves = graph.get_execution_waves()
for i, wave in enumerate(waves, 1):
    print(f"Wave {i}: {[issue.issue_id for issue in wave]}")
```

#### Construction

```python
@classmethod
def from_issues(
    cls,
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
) -> DependencyGraph
```

Build graph from list of issues.

**Parameters:**
- `issues` - List of `IssueInfo` objects; both `blocked_by` and `blocks` fields are consumed to build edges
- `completed_ids` - Set of completed issue IDs (treated as resolved)
- `all_known_ids` - Set of all issue IDs that exist on disk; references to these are silently skipped (not warned) even if not in the graph

**Returns:** Constructed `DependencyGraph`

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `issues` | `dict[str, IssueInfo]` | Mapping of issue ID to `IssueInfo` |
| `blocked_by` | `dict[str, set[str]]` | Mapping of issue ID to blocker IDs |
| `blocks` | `dict[str, set[str]]` | Reverse mapping (what each issue blocks) |
| `depends_on_edges` | `dict[str, set[str]]` | Mapping of issue ID to soft-prerequisite issue IDs |

#### Methods

##### get_ready_issues

```python
def get_ready_issues(self, completed: set[str] | None = None) -> list[IssueInfo]
```

Return issues whose blockers are all completed.

**Parameters:**
- `completed` - Set of completed issue IDs

**Returns:** List of `IssueInfo` for ready issues, sorted by priority

##### get_execution_waves

```python
def get_execution_waves(self, completed: set[str] | None = None) -> list[list[IssueInfo]]
```

Return issues grouped into parallel execution waves.

Wave 1: All issues with no blockers (or blockers already completed)
Wave 2: Issues whose blockers are all in wave 1
Wave N: Issues whose blockers are all in waves 1..N-1

**Parameters:**
- `completed` - Set of already-completed issue IDs

**Returns:** List of waves, each wave is a list of issues that can run in parallel

**Raises:** `ValueError` if graph contains cycles

**Example:**
```python
graph = DependencyGraph.from_issues(issues)
waves = graph.get_execution_waves()

# Wave 1: [FEAT-001, BUG-001]  - no blockers
# Wave 2: [FEAT-002, FEAT-003] - blocked by FEAT-001
# Wave 3: [FEAT-004]           - blocked by FEAT-002, FEAT-003
```

##### topological_sort

```python
def topological_sort(self) -> list[IssueInfo]
```

Return issues in dependency order (Kahn's algorithm).

**Returns:** List of `IssueInfo` in topological order

**Raises:** `ValueError` if graph contains cycles

##### has_cycles

```python
def has_cycles(self) -> bool
```

Check if the graph contains cycles.

**Returns:** `True` if cycles exist

##### detect_cycles

```python
def detect_cycles(self) -> list[list[str]]
```

Find all cycles in the graph using DFS.

**Returns:** List of cycles, each cycle is a list of issue IDs

### WaveContentionNote

Annotation returned when `refine_waves_for_contention()` splits a wave due to file overlap between issues.

```python
@dataclass
class WaveContentionNote:
    contended_paths: list[str]   # Files that caused the split
    sub_wave_index: int          # 0-based index of this sub-wave within the parent wave
    total_sub_waves: int         # Total sub-waves the parent wave was split into
    parent_wave_index: int = 0   # 0-based index of the original unsplit wave
```

### refine_waves_for_contention

```python
def refine_waves_for_contention(
    waves: list[list[IssueInfo]],
    *,
    config: DependencyMappingConfig | None = None,
) -> tuple[list[list[IssueInfo]], list[WaveContentionNote | None]]
```

Refine execution waves by splitting issues that would edit the same files. Uses greedy graph coloring so no two issues in the same sub-wave modify the same files. Called automatically by `ll-sprint` before each wave is dispatched to parallel workers.

**Parameters:**
- `waves` — Execution waves from `DependencyGraph.get_execution_waves()`
- `config` — Optional `DependencyMappingConfig` for file-hint extraction tuning

**Returns:** `(refined_waves, contention_notes)` — parallel lists of equal length. `contention_notes[i]` is `None` for waves that were not split, and a `WaveContentionNote` for sub-waves that were.

**Example:**
```python
from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention

graph = DependencyGraph.from_issues(issues)
waves = graph.get_execution_waves()
refined, notes = refine_waves_for_contention(waves)

for i, (wave, note) in enumerate(zip(refined, notes)):
    if note:
        print(f"Wave {i}: sub-wave {note.sub_wave_index+1}/{note.total_sub_waves} "
              f"(split on: {note.contended_paths})")
```

---

## little_loops.dependency_mapper

Cross-issue dependency discovery and mapping. Analyzes active issues to discover potential dependencies based on file overlap and validates existing dependency references for integrity.

This is a sub-package split into focused modules:
- `dependency_mapper.models` — data models (`DependencyProposal`, `ParallelSafePair`, `ValidationResult`, `DependencyReport`, `FixResult`)
- `dependency_mapper.analysis` — conflict scoring and dependency analysis
- `dependency_mapper.formatting` — report and graph formatting
- `dependency_mapper.operations` — file mutation operations (apply/fix)

All names are re-exported from `little_loops.dependency_mapper` for backwards compatibility.

Complements `dependency_graph`:
- `dependency_graph` = execution ordering from existing `Blocked By` data
- `dependency_mapper` = discovery and proposal of new relationships

### DependencyProposal

A proposed dependency relationship between two issues.

```python
@dataclass
class DependencyProposal:
    """A proposed dependency relationship between two issues."""
    source_id: str              # Issue that would be blocked
    target_id: str              # Issue that would block (the blocker)
    reason: str                 # Category of discovery method
    confidence: float           # Score from 0.0 to 1.0
    rationale: str              # Human-readable explanation
    overlapping_files: list[str]  # Files referenced by both issues
    conflict_score: float       # Semantic conflict score from 0.0 to 1.0
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_id` | `str` | Issue that would be blocked |
| `target_id` | `str` | Issue that would block (the blocker) |
| `reason` | `str` | Category of discovery method (e.g., "file_overlap") |
| `confidence` | `float` | Score from 0.0 to 1.0 |
| `rationale` | `str` | Human-readable explanation |
| `overlapping_files` | `list[str]` | Files referenced by both issues |
| `conflict_score` | `float` | Semantic conflict score (0.0 = parallel-safe, 1.0 = definite conflict). Default: 0.5 |

### ParallelSafePair

A pair of issues that share files but can safely run in parallel (conflict score below threshold).

```python
@dataclass
class ParallelSafePair:
    """A pair of issues that share files but can safely run in parallel."""
    issue_a: str                # First issue ID
    issue_b: str                # Second issue ID
    shared_files: list[str]     # Files referenced by both issues
    conflict_score: float       # Semantic conflict score (< 0.4)
    reason: str                 # Why these are parallel-safe
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `issue_a` | `str` | First issue ID |
| `issue_b` | `str` | Second issue ID |
| `shared_files` | `list[str]` | Files referenced by both issues |
| `conflict_score` | `float` | Semantic conflict score (always < 0.4) |
| `reason` | `str` | Explanation of why the pair is parallel-safe (e.g., "Different sections (body vs header)") |

### ValidationResult

Result of validating existing dependency references.

```python
@dataclass
class ValidationResult:
    """Result of validating existing dependency references."""
    broken_refs: list[tuple[str, str]]             # (issue_id, missing_ref_id) for blocked_by refs
    missing_backlinks: list[tuple[str, str]]       # (issue_id, should_have_backlink_from)
    cycles: list[list[str]]                        # Cycle paths
    stale_completed_refs: list[tuple[str, str]]    # (issue_id, completed_ref_id)
    broken_depends_on_refs: list[tuple[str, str]]  # (issue_id, missing_ref_id) for depends_on refs
    broken_relates_to_refs: list[tuple[str, str]]  # (issue_id, missing_ref_id) for relates_to refs

    @property
    def has_issues(self) -> bool
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `broken_refs` | `list[tuple[str, str]]` | References to nonexistent issues in `blocked_by` or `duplicate_of` |
| `missing_backlinks` | `list[tuple[str, str]]` | Asymmetric `Blocked By`/`Blocks` pairs |
| `cycles` | `list[list[str]]` | Circular dependency chains |
| `stale_completed_refs` | `list[tuple[str, str]]` | References to completed issues |
| `broken_depends_on_refs` | `list[tuple[str, str]]` | References to nonexistent issues in `depends_on` |
| `broken_relates_to_refs` | `list[tuple[str, str]]` | References to nonexistent issues in `relates_to` |

**Properties:**
- `has_issues` - Returns `True` if any validation problems were found

### DependencyReport

Complete dependency analysis report combining proposals, parallel-safe pairs, and validation.

```python
@dataclass
class DependencyReport:
    """Complete dependency analysis report."""
    proposals: list[DependencyProposal]
    parallel_safe: list[ParallelSafePair]
    validation: ValidationResult
    issue_count: int
    existing_dep_count: int
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `proposals` | `list[DependencyProposal]` | Proposed new dependency relationships (conflict score >= 0.4) |
| `parallel_safe` | `list[ParallelSafePair]` | File-overlapping pairs safe to run in parallel (conflict score < 0.4) |
| `validation` | `ValidationResult` | Validation results for existing dependencies |
| `issue_count` | `int` | Total issues analyzed |
| `existing_dep_count` | `int` | Number of existing dependency edges |

### Functions

#### extract_file_paths

```python
def extract_file_paths(content: str) -> set[str]
```

Extract file paths from issue content.

Searches for file paths in backtick-quoted paths, location section bold paths, and standalone paths with recognized extensions. Code fence blocks are stripped before extraction.

**Parameters:**
- `content` - Issue file content

**Returns:** Set of file paths found in the content

#### compute_conflict_score

```python
def compute_conflict_score(
    content_a: str,
    content_b: str,
) -> float
```

Compute semantic conflict score between two issues.

Combines three weighted signals to determine how likely two file-overlapping issues are to conflict:

| Signal | Weight | Description |
|--------|--------|-------------|
| Semantic target overlap | 0.5 | Jaccard similarity of component/function names (PascalCase, function refs, explicit scopes) |
| Section mention overlap | 0.3 | Whether issues reference the same UI regions (header, body, sidebar, etc.) |
| Modification type match | 0.2 | Whether both issues have the same modification type (structural, infrastructure, enhancement) |

When a signal cannot be determined (e.g., no component names found), it defaults to 0.5 (moderate).

**Parameters:**
- `content_a` - First issue's file content
- `content_b` - Second issue's file content

**Returns:** Conflict score from 0.0 (parallel-safe) to 1.0 (definite conflict)

**Score interpretation:**

| Score | Level | Meaning |
|-------|-------|---------|
| >= 0.7 | HIGH | Same component, same section, same type — definite conflict |
| 0.4–0.7 | MEDIUM | Possible conflict, unclear if same section |
| < 0.4 | LOW | Different sections/components — likely safe to parallelize |

#### find_file_overlaps

```python
def find_file_overlaps(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
) -> tuple[list[DependencyProposal], list[ParallelSafePair]]
```

Find issues that reference overlapping files and propose dependencies.

For each pair of issues where both reference the same file(s), computes a semantic conflict score. High-conflict pairs (score >= 0.4) get dependency proposals; low-conflict pairs (score < 0.4) are reported as parallel-safe.

**Dependency direction logic:**
1. **Different priorities**: Higher priority (lower P-number) blocks lower priority
2. **Same priority, different modification types**: Structural blocks infrastructure blocks enhancement
3. **Same priority, same type**: Falls back to ID ordering with reduced confidence (0.5x multiplier)

Pairs that already have a dependency relationship are skipped.

**Parameters:**
- `issues` - List of parsed issue objects
- `issue_contents` - Mapping from issue_id to file content

**Returns:** Tuple of (proposed dependencies, parallel-safe pairs)

#### validate_dependencies

```python
def validate_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
) -> ValidationResult
```

Validate existing dependency references for integrity.

Checks for broken references to nonexistent issues, missing backlinks where A blocks B but B doesn't list A in `blocked_by`, circular dependency chains, and stale references to completed issues.

**Parameters:**
- `issues` - List of parsed issue objects
- `completed_ids` - Set of completed issue IDs

**Returns:** `ValidationResult` with all detected problems

Also checks broken refs in `depends_on`, `relates_to`, and `duplicate_of` fields.

#### validate_frontmatter_fields

```python
def validate_frontmatter_fields(issues: list[IssueInfo]) -> None
```

Warn about deprecated relationship frontmatter keys found in issue files on disk.

Reads the raw file content for each issue and emits a `logger.warning()` for any deprecated key (e.g., `parent_issue:`, `related:`) left over from pre-ENH-1434 migration.

**Parameters:**
- `issues` - List of parsed issue objects (must have a valid `.path` attribute)

#### analyze_dependencies

```python
def analyze_dependencies(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
    completed_ids: set[str] | None = None,
) -> DependencyReport
```

Run full dependency analysis: discovery and validation.

Combines file overlap discovery with dependency validation to produce a comprehensive report.

**Parameters:**
- `issues` - List of parsed issue objects
- `issue_contents` - Mapping from issue_id to file content
- `completed_ids` - Set of completed issue IDs

**Returns:** Comprehensive `DependencyReport`

#### format_report

```python
def format_report(report: DependencyReport) -> str
```

Format a dependency report as human-readable markdown.

Output includes:
- Summary statistics (issues analyzed, existing deps, proposed deps, parallel-safe pairs, validation issues)
- **Proposed Dependencies** table with Conflict level column (HIGH/MEDIUM/LOW)
- **Parallel Execution Safe** table listing file-overlapping pairs that can run concurrently
- **Validation Issues** sections (broken refs, missing backlinks, cycles, stale refs)

**Parameters:**
- `report` - The analysis report to format

**Returns:** Markdown-formatted report string

#### format_text_graph

```python
def format_text_graph(
    issues: list[IssueInfo],
    proposals: list[DependencyProposal] | None = None,
) -> str
```

Generate an ASCII dependency graph diagram.

Shows existing dependencies as solid arrows (`──→`) and proposed dependencies as dashed arrows (`-.→`).

**Parameters:**
- `issues` - List of parsed issue objects
- `proposals` - Optional proposed dependencies to include

**Returns:** Text graph string readable in the terminal

#### format_epic_tree

```python
def format_epic_tree(
    root_id: str,
    root_info: IssueInfo,
    child_map: dict[str, IssueInfo],
    graph: DependencyGraph,
    use_color: bool = True,
) -> str
```

Render an EPIC's child hierarchy as a Unicode box-drawing tree string.

Children are ordered via topological sort. Status badges (`[done]`, `[blocked]`) appear inline; `[open]` is suppressed. Blocking edges are annotated as `⮡ blocks ISSUE-NNN` under the blocker's tree line.

**Parameters:**
- `root_id` - The EPIC issue ID (e.g. `"EPIC-001"`)
- `root_info` - IssueInfo for the root EPIC
- `child_map` - Mapping from child issue ID to IssueInfo
- `graph` - DependencyGraph scoped to the EPIC's children
- `use_color` - Whether to emit ANSI color codes (default `True`)

**Returns:** Unicode box-drawing tree string, or `"EPIC-001: (no children)"` when `child_map` is empty

#### apply_proposals

```python
def apply_proposals(
    proposals: list[DependencyProposal],
    issue_files: dict[str, Path],
) -> list[str]
```

Write approved dependency proposals to issue files.

For each proposal, adds the target to the source's `## Blocked By` section and the source to the target's `## Blocks` section.

**Parameters:**
- `proposals` - Approved proposals to apply
- `issue_files` - Mapping from issue_id to file path

**Returns:** List of modified file paths

**Usage Example:**
```python
from little_loops.dependency_mapper import analyze_dependencies, apply_proposals
from little_loops.issue_parser import find_issues
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
issues = find_issues(config)

# Load issue contents
contents = {issue.issue_id: issue.path.read_text() for issue in issues}

# Run analysis
report = analyze_dependencies(issues, contents)

# Review proposals (conflict score >= 0.4)
for proposal in report.proposals:
    print(f"{proposal.source_id} -> {proposal.target_id} "
          f"(conflict: {proposal.conflict_score:.0%}): {proposal.rationale}")

# Review parallel-safe pairs (conflict score < 0.4)
for pair in report.parallel_safe:
    print(f"{pair.issue_a} || {pair.issue_b}: {pair.reason}")

# Apply approved proposals
if report.proposals:
    issue_files = {issue.issue_id: issue.path for issue in issues}
    modified = apply_proposals(report.proposals, issue_files)
    print(f"Modified: {modified}")
```

---

## little_loops.goals_parser

Parser for `ll-goals.md` product goals document. Provides structured access to product goals including persona and priorities.

### Persona

Primary user persona.

```python
@dataclass
class Persona:
    """Primary user persona."""
    id: str
    name: str
    role: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Persona: ...
```

### Priority

Strategic priority.

```python
@dataclass
class Priority:
    """Strategic priority."""
    id: str
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> Priority: ...
```

### ProductGoals

Parsed product goals from `ll-goals.md`.

```python
@dataclass
class ProductGoals:
    """Parsed product goals from ll-goals.md."""
    version: str
    persona: Persona | None
    priorities: list[Priority] = field(default_factory=list)
    raw_content: str = ""

    @classmethod
    def from_file(cls, path: Path) -> ProductGoals | None: ...

    @classmethod
    def from_content(cls, content: str) -> ProductGoals | None: ...

    def is_valid(self) -> bool: ...
```

**`from_file(path)`** — Parse goals from an `ll-goals.md` file. Returns `None` if the file doesn't exist or is invalid.

**`from_content(content)`** — Parse goals from raw string content. Returns `None` if the content is invalid or missing a YAML frontmatter block.

**`is_valid()`** — Returns `True` if both `persona` and at least one `priority` are defined.

### validate_goals

```python
def validate_goals(goals: ProductGoals) -> list[str]
```

Validate product goals and return warnings.

**Parameters:**
- `goals` - ProductGoals instance to validate

**Returns:** List of validation warning messages (empty if valid)

**Example:**
```python
from pathlib import Path
from little_loops.goals_parser import ProductGoals, validate_goals

goals = ProductGoals.from_file(Path(".ll/ll-goals.md"))
if goals is None:
    print("Goals file not found or invalid")
else:
    warnings = validate_goals(goals)
    for warning in warnings:
        print(f"Warning: {warning}")

    if goals.persona:
        print(f"Persona: {goals.persona.name} ({goals.persona.role})")

    for priority in goals.priorities:
        print(f"Priority: {priority.id} - {priority.name}")
```

---

## little_loops.issue_discovery

Issue discovery, duplicate detection, and regression analysis. Implemented as a
package (`issue_discovery/`) with three sub-modules: `matching`, `extraction`,
and `search`.

### Public Functions (6)

| Function | Purpose |
|----------|---------|
| `search_issues_by_content()` | Search issues by content with relevance scoring |
| `search_issues_by_file_path()` | Search for issues mentioning a specific file path |
| `detect_regression_or_duplicate()` | Classify a completed issue match |
| `find_existing_issue()` | Multi-pass search for an existing issue matching a finding |
| `reopen_issue()` | Move a completed issue back to active with Reopened section |
| `update_existing_issue()` | Add new findings to an existing active issue |

### Classes

#### MatchClassification

Enum classifying how a finding relates to an existing issue.

```python
class MatchClassification(Enum):
    NEW_ISSUE = "new_issue"    # No existing issue matches
    DUPLICATE = "duplicate"    # Active issue exists
    REGRESSION = "regression"  # Completed, fix broken by later changes
    INVALID_FIX = "invalid_fix"  # Completed, fix never worked
    UNVERIFIED = "unverified"  # Completed, no fix commit tracked
```

#### RegressionEvidence

Evidence gathered when classifying a completed-issue match.

```python
@dataclass
class RegressionEvidence:
    fix_commit_sha: str | None = None
    fix_commit_exists: bool = True
    files_modified_since_fix: list[str] = field(default_factory=list)
    days_since_fix: int = 0
    related_commits: list[str] = field(default_factory=list)
```

#### FindingMatch

Result of matching a finding to an existing issue.

```python
@dataclass
class FindingMatch:
    issue_path: Path | None
    match_type: str  # "exact", "similar", "content", "none"
    match_score: float  # 0.0–1.0
    is_completed: bool = False
    matched_terms: list[str] = field(default_factory=list)
    classification: MatchClassification = MatchClassification.NEW_ISSUE
    regression_evidence: RegressionEvidence | None = None
```

Key properties: `should_skip` (score ≥ 0.8), `should_update` (0.5–0.8),
`should_create` (< 0.5), `should_reopen`, `should_reopen_as_regression`,
`should_reopen_as_invalid_fix`, `is_unverified`.

### Example

```python
from little_loops.issue_discovery import (
    find_existing_issue,
    reopen_issue,
    MatchClassification,
)
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())

# Search for an existing issue matching a new finding
match = find_existing_issue(
    config,
    finding_type="BUG",
    file_path="scripts/little_loops/config.py",
    finding_title="Config fails to load on missing key",
    finding_content="KeyError raised when optional key absent",
)

if match.should_skip:
    print(f"Duplicate of {match.issue_path}")
elif match.should_reopen_as_regression:
    print(f"Regression: {match.issue_path} — {match.regression_evidence}")
elif match.should_create:
    print("New issue — no match found")
```

---

## little_loops.issue_history

Analysis of completed issues for project health insights.

### Public Functions (28)

#### Parsing & Scanning

| Function | Purpose |
|----------|---------|
| `parse_completed_issue(file_path, *, batch_dates=None)` | Parse a single completed issue file |
| `scan_completed_issues(issues_dir, category_dirs=None)` | Scan `.issues/` for completed issues (takes the parent `.issues/` directory, not the completed subdir) |
| `scan_active_issues(base_dir, categories)` | Scan active issue directories |
| `detect_recurring_feedback(corrections)` | Detect recurring correction patterns |
| `detect_skill_bypass(history)` | Detect skill bypass events |
| `scan_completed_issues_from_db(db_path)` | Scan completed issues from history.db |

#### parse_completed_issue

```python
def parse_completed_issue(
    file_path: Path,
    *,
    batch_dates: dict[str, date] | None = None,
) -> CompletedIssue | None
```

Parse a single completed issue file.

**Parameters:**
- `file_path` — Path to the completed issue `.md` file
- `batch_dates` — Optional pre-fetched filename→date mapping from `_batch_completion_dates()`. When provided, the completion date is resolved via an O(1) dict lookup instead of a per-file `git log` subprocess call. Pass this when calling from inside a loop over many issue files.

**Returns:** `CompletedIssue` dataclass, or `None` if the file cannot be parsed.

**Performance note**: Without `batch_dates`, each call runs one `git log` subprocess to determine when the file was added to the repo. For scanning an entire directory, prefer `scan_completed_issues()` — it pre-fetches all completion dates in a single `git log` call and passes the resulting map to each `parse_completed_issue()` call automatically (ENH-970).

#### Analysis

| Function | Purpose |
|----------|---------|
| `calculate_summary(issues)` | Calculate summary statistics |
| `calculate_analysis(completed_dir, ...)` | Calculate full history analysis |
| `analyze_hotspots(issues, ...)` | Detect file/directory hotspots |
| `analyze_coupling(issues, ...)` | Analyze file coupling patterns |
| `analyze_regression_clustering(issues)` | Cluster regression bug chains |
| `analyze_test_gaps(issues, ...)` | Detect test coverage gaps |
| `analyze_rejection_rates(issues)` | Analyze rejection and closure patterns |
| `detect_manual_patterns(issues)` | Detect recurring manual activities |
| `detect_config_gaps(manual_analysis, ...)` | Detect configuration automation gaps |
| `analyze_agent_effectiveness(issues)` | Analyze agent effectiveness by type |
| `analyze_complexity_proxy(issues)` | Analyze complexity via issue duration |
| `detect_cross_cutting_smells(issues)` | Detect cross-cutting concern patterns |

#### Formatting

| Function | Purpose |
|----------|---------|
| `format_summary_text(summary)` | Format summary as plain text |
| `format_summary_json(summary)` | Format summary as JSON |
| `format_analysis_text(analysis)` | Format full analysis as plain text |
| `format_analysis_json(analysis)` | Format full analysis as JSON |
| `format_analysis_markdown(analysis)` | Format full analysis as Markdown |
| `format_analysis_yaml(analysis)` | Format full analysis as YAML |

#### Documentation Synthesis

| Function | Purpose |
|----------|---------|
| `synthesize_docs(issues, topic, ...)` | Synthesize documentation from issue history |
| `score_relevance(issue, topic)` | Score issue relevance to a topic |
| `build_narrative_doc(issues, topic)` | Build narrative-style documentation |
| `build_structured_doc(issues, topic)` | Build structured documentation |

### Data Classes (26)

#### CompletedIssue

Parsed information from a completed issue file.

```python
@dataclass
class CompletedIssue:
    """Parsed information from a completed issue file."""
    path: Path
    issue_type: str          # BUG, ENH, FEAT, EPIC
    priority: str            # P0-P5
    issue_id: str            # e.g., BUG-001
    discovered_by: str | None = None
    discovered_date: date | None = None
    completed_date: date | None = None
    captured_at: datetime | None = None   # sub-day precision from `captured_at` frontmatter
    completed_at: datetime | None = None  # sub-day precision from `completed_at` frontmatter
```

#### HistorySummary

Summary statistics for completed issues.

```python
@dataclass
class HistorySummary:
    """Summary statistics for completed issues."""
    total_count: int
    type_counts: dict[str, int] = field(default_factory=dict)
    priority_counts: dict[str, int] = field(default_factory=dict)
    discovery_counts: dict[str, int] = field(default_factory=dict)
    earliest_date: date | None = None
    latest_date: date | None = None
    # Properties: date_range_days, velocity
```

#### Hotspot

A file or directory that appears in multiple issues.

```python
@dataclass
class Hotspot:
    """A file or directory that appears in multiple issues."""
    path: str
    issue_count: int = 0
    issue_ids: list[str] = field(default_factory=list)
    issue_types: dict[str, int] = field(default_factory=dict)  # {"BUG": 5, "ENH": 3, "EPIC": 2}
    bug_ratio: float = 0.0
    churn_indicator: str = "low"  # "high", "medium", "low"
```

#### CouplingPair

A pair of files that frequently appear together in issues.

```python
@dataclass
class CouplingPair:
    """A pair of files that frequently appear together in issues."""
    file_a: str
    file_b: str
    co_occurrence_count: int = 0
    coupling_strength: float = 0.0  # 0-1, Jaccard similarity
    issue_ids: list[str] = field(default_factory=list)
```

#### Other Data Classes

| Class | Purpose |
|-------|---------|
| `PeriodMetrics` | Metrics for a specific time period (quarter, month, week) |
| `SubsystemHealth` | Health metrics for a subsystem directory |
| `HotspotAnalysis` | Container for file/directory hotspot analysis results |
| `CouplingAnalysis` | Container for file coupling analysis results |
| `RegressionCluster` | A cluster of bugs where fixes caused new bugs |
| `RegressionAnalysis` | Container for regression clustering results |
| `Gap` | A source file with bugs but missing/weak test coverage |
| `GapAnalysis` | Container for test gap analysis results |
| `RejectionMetrics` | Metrics for rejection and invalid closure tracking |
| `RejectionAnalysis` | Container for rejection pattern analysis |
| `ManualPattern` | A recurring manual activity detected across issues |
| `ManualPatternAnalysis` | Container for manual pattern analysis results |
| `ConfigGap` | A configuration gap that could automate manual work |
| `ConfigGapsAnalysis` | Container for configuration gap analysis |
| `AgentOutcome` | Metrics for a single agent processing a specific issue type |
| `AgentEffectivenessAnalysis` | Container for agent effectiveness analysis |
| `TechnicalDebtMetrics` | Technical debt health indicators |
| `ComplexityProxy` | Duration-based complexity proxy for a file/directory |
| `ComplexityProxyAnalysis` | Container for complexity proxy analysis |
| `CrossCuttingSmell` | A detected cross-cutting concern scattered across the codebase |
| `CrossCuttingAnalysis` | Container for cross-cutting concern analysis |
| `HistoryAnalysis` | Complete history analysis report (all analysis results) |

### Example

```python
from little_loops.issue_history import (
    scan_completed_issues,
    calculate_summary,
    analyze_hotspots,
    format_summary_text,
)
from pathlib import Path

# Load and analyze
issues_dir = Path(".issues")
issues = scan_completed_issues(issues_dir)
summary = calculate_summary(issues)

print(f"Completed: {summary.total_count}")
print(f"Velocity: {summary.velocity:.2f} issues/day")

# Find problematic files
hotspot_analysis = analyze_hotspots(issues)
for hotspot in hotspot_analysis.file_hotspots[:5]:
    print(f"{hotspot.path}: {hotspot.issue_count} issues")

# Generate text report
report = format_summary_text(summary)
print(report)
```

---

## little_loops.git_operations

Git utility functions for status checking and .gitignore management.

### GitignorePattern

Represents a suggested .gitignore pattern with metadata.

```python
@dataclass
class GitignorePattern:
    pattern: str           # The .gitignore pattern (e.g., "*.log", ".env")
    category: str          # Category of file (e.g., "coverage", "environment")
    description: str       # Human-readable description
    files_matched: list[str]  # Untracked files matching this pattern
    priority: int          # Suggestion priority (1=highest, 5=lowest)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_wildcard` | `bool` | True if pattern contains wildcards (`*`, `?`) |
| `is_directory` | `bool` | True if pattern targets a directory (ends with `/`) |

### GitignoreSuggestion

Container for gitignore suggestions with user interaction helpers.

```python
@dataclass
class GitignoreSuggestion:
    patterns: list[GitignorePattern]  # Suggested patterns
    existing_gitignore: Path | None   # Path to .gitignore file
    already_ignored: list[str]        # Files already covered by .gitignore
    total_files: int                  # Total untracked files examined
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_suggestions` | `bool` | True if there are patterns to suggest |
| `files_to_ignore` | `list[str]` | All files that would be ignored by suggested patterns |
| `summary` | `str` | Human-readable summary of suggestions |

### suggest_gitignore_patterns

```python
def suggest_gitignore_patterns(
    untracked_files: list[str] | None = None,
    repo_root: Path | str = ".",
    logger: Logger | None = None,
) -> GitignoreSuggestion
```

Analyze untracked files and suggest .gitignore patterns.

Examines untracked files against a curated list of common patterns (coverage reports, environment files, logs, Python/Node.js artifacts, etc.). Respects existing .gitignore patterns and won't suggest patterns for already-ignored files.

**Parameters:**
- `untracked_files` - Optional list of untracked files. If None, detects via git status
- `repo_root` - Path to repository root (default: current directory)
- `logger` - Optional logger for debug output

**Returns:** `GitignoreSuggestion` with suggested patterns and metadata

**Example:**
```python
from little_loops.git_operations import suggest_gitignore_patterns
from little_loops.logger import Logger

logger = Logger()
result = suggest_gitignore_patterns(logger=logger)

if result.has_suggestions:
    for pattern in result.patterns:
        print(f"{pattern.pattern}: {pattern.description}")
        print(f"  Matches: {', '.join(pattern.files_matched)}")
```

### add_patterns_to_gitignore

```python
def add_patterns_to_gitignore(
    patterns: list[str],
    repo_root: Path | str = ".",
    logger: Logger | None = None,
    backup: bool = True,
) -> bool
```

Add patterns to .gitignore file.

Skips duplicate patterns and optionally creates a backup before modifying.

**Parameters:**
- `patterns` - List of patterns to add
- `repo_root` - Path to repository root
- `logger` - Optional logger for output
- `backup` - If True, creates `.gitignore.backup` before modifying

**Returns:** `True` if patterns were added successfully

**Example:**
```python
from little_loops.git_operations import add_patterns_to_gitignore
from little_loops.logger import Logger

logger = Logger()
success = add_patterns_to_gitignore(
    patterns=["*.log", ".env", "coverage.json"],
    logger=logger
)
```

### get_untracked_files

```python
def get_untracked_files(repo_root: Path | str = ".") -> list[str]
```

Get list of untracked files from git status.

Uses `git status --porcelain` to detect untracked files.

**Parameters:**
- `repo_root` - Path to repository root (default: current directory)

**Returns:** List of untracked file paths (relative to repo root)

### check_git_status

```python
def check_git_status(logger: Logger) -> bool
```

Check for uncommitted changes.

**Parameters:**
- `logger` - Logger for output

**Returns:** `True` if there are uncommitted changes

---

## little_loops.work_verification

Shared work verification utilities used by `issue_manager` (ll-auto) and `worker_pool` (ll-parallel).

```python
from little_loops.work_verification import verify_work_was_done, filter_excluded_files
```

### Constants

```python
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)
```

Directories excluded from work verification. Changes to files in these directories do not count as meaningful implementation work.

### filter_excluded_files

```python
def filter_excluded_files(files: list[str]) -> list[str]
```

Filter out files in excluded directories.

**Parameters:**
- `files` - List of file paths to filter

**Returns:** List of files not in `EXCLUDED_DIRECTORIES`

### verify_work_was_done

```python
def verify_work_was_done(
    logger: Logger,
    changed_files: list[str] | None = None,
    baseline_sha: str | None = None,
) -> bool
```

Verify that actual work was done (not just issue file moves).

Prevents marking issues as "completed" when no actual fix was implemented. Returns `True` if there are file changes outside of excluded directories.

Detection runs in three modes (first match wins):
1. **Pre-computed list** (`changed_files` provided) — used by `ll-parallel` via `worker_pool.py`
2. **Uncommitted/staged** — `git diff --name-only` + `git diff --cached --name-only`
3. **Commit-range** (`baseline_sha` provided and HEAD has moved) — `git diff --name-only <baseline_sha>..HEAD` — covers the common case where the agent commits mid-phase and exits with a clean working tree

**Parameters:**
- `logger` - Logger for output
- `changed_files` - Optional pre-computed file list. If `None`, detects via `git diff` and `git diff --cached`
- `baseline_sha` - Optional git SHA captured before Phase 2 began. When provided and HEAD has advanced beyond this SHA, checks for non-excluded files committed in the range; enables detection of mid-phase commits in `ll-auto`

**Returns:** `True` if meaningful file changes were detected

**Example:**

```python
from little_loops.work_verification import verify_work_was_done
from little_loops.logger import Logger

logger = Logger()
if not verify_work_was_done(logger):
    logger.warning("No implementation changes detected")
```

---

## little_loops.context_window

Single source of truth for model → context-window size mapping. Used by `issue_manager`, `subprocess_utils`, and `worker_pool` to resolve the correct token denominator for handoff/guillotine decisions.

### context_window_for

```python
def context_window_for(model: str | None, override: int | None = None) -> int:
    """Resolve context-window size for a model id.

    Precedence (highest to lowest):
    1. Explicit ``override`` argument (non-zero)
    2. ``LL_CONTEXT_LIMIT`` environment variable (non-zero integer)
    3. ``[1m]`` suffix on model id → 1_000_000
    4. Exact model-id lookup in MODEL_CONTEXT_WINDOW
    5. 200_000 conservative floor
    """
```

**Parameters**:
- `model` — Model identifier string (e.g. `"claude-opus-4-8[1m]"`), or `None` to use env-var / floor.
- `override` — Explicit token count; takes top precedence when non-zero.

**Returns**: Context window size in tokens (always a positive `int`).

**Examples**:
```python
from little_loops.context_window import context_window_for

context_window_for("claude-opus-4-8[1m]")          # → 1_000_000
context_window_for("claude-opus-4-8")               # → 200_000
context_window_for(None)                             # → 200_000 (conservative floor)
context_window_for("claude-opus-4-8", override=500_000)  # → 500_000
```

**Note**: The bash layer (`hooks/scripts/context-monitor.sh:get_context_limit()`) implements the same logic; both are kept in sync via a `# keep in sync with` comment. The env-var precedence means that `LL_CONTEXT_LIMIT` set by any CLI (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`) flows through `context_window_for()` into every Python continuation path.

---

## little_loops.issue_manager

Process all backlog issues sequentially in priority order.

### AutoManager

Automated issue manager for sequential processing.

```python
from little_loops.issue_manager import AutoManager
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
manager = AutoManager(
    config=config,
    dry_run=False,
    max_issues=5,
    resume=False,
    category="bugs"
)
exit_code = manager.run()
```

#### Constructor

```python
AutoManager(
    config: BRConfig,
    dry_run: bool = False,
    max_issues: int = 0,
    resume: bool = False,
    category: str | None = None,
    only_ids: list[str] | set[str] | None = None,
    skip_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
    priority_filter: set[str] | None = None,
    label_filter: set[str] | None = None,
    verbose: bool = True,
    preview_full: bool = False,
    db_path: Path | None = None,
)
```

**Parameters:**
- `config` - Project configuration
- `dry_run` - Preview mode (no actual changes)
- `max_issues` - Maximum issues to process (0 = unlimited)
- `resume` - Resume from previous state
- `category` - Filter to specific category
- `only_ids` - If provided, only process these issue IDs
- `skip_ids` - Issue IDs to skip (in addition to attempted issues)
- `type_prefixes` - If provided, only process issues with these type prefixes
- `priority_filter` - If provided, only process issues with these priority levels (e.g., `{"P0", "P1"}`)
- `label_filter` - If provided, only process issues carrying one of these labels
- `verbose` - Whether to output progress messages
- `preview_full` - Show full issue body in dry-run preview (default: summary only)
- `db_path` - Override path for the SQLite session store (default: `.ll/history.db`)

**Behavior:** On construction, `AutoManager` creates an internal `EventBus` and wires a `SQLiteTransport(db_path or DEFAULT_DB_PATH)` to it automatically. Issue lifecycle events (`issue.completed`, `issue.deferred`, `issue.skipped`, `issue.started`, etc.) are recorded live during `run()` without any additional configuration.

#### Methods

##### run

```python
def run(self) -> int
```

Run the automation loop.

**Returns:** Exit code (0 = success)

### Helper Functions

#### run_claude_command

```python
def run_claude_command(
    command: str,
    logger: Logger,
    timeout: int = 3600,
    stream_output: bool = True,
    idle_timeout: int = 0,
    on_model_detected: Callable[[str], None] | None = None,
    on_usage: Callable[[int, int], None] | None = None,
    preview_full: bool = False,
    resume_session: bool = False,
) -> subprocess.CompletedProcess[str]
```

Preview and invoke a Claude CLI command with output streaming. This is the `issue_manager`-local wrapper that logs and truncates the command before delegating to `subprocess_utils.run_claude_command`.

**Parameters:**
- `command` - Command to pass to Claude CLI
- `logger` - Logger for output
- `timeout` - Timeout in seconds
- `stream_output` - Whether to stream output to console
- `idle_timeout` - Kill process if no output for this many seconds (0 to disable)
- `on_model_detected` - Optional callback invoked with the model name from the stream-json system/init event
- `on_usage` - Optional callback invoked with `(input_tokens, output_tokens)` from the stream-json result event
- `preview_full` - If `True`, display the full command without truncation (for `--verbose`)
- `resume_session` - If `True`, passes `--continue` to the Claude CLI to continue the most recent conversation

**Returns:** `CompletedProcess` with stdout/stderr captured. When a `result` event with `is_error=True` is present in the stream-json output, `CompletedProcess.stderr` will include a `[result] <error>` line containing the error text from the result event's `error` field (falling back to the `result` field).

**Turn-end detection**: The reader breaks on the stream-json `result` event rather than waiting for pipe EOF. This is necessary because background `Workflow`/`Task` child processes spawned by the headless `claude -p` session inherit the stdout/stderr write-ends; a pipe only reports EOF when the *last* writer closes it, so EOF may never arrive even after the turn completes, causing the reader to hang until the wall-clock timeout fires. Stopping on `result` bounds read latency to the actual turn duration regardless of whether background children are still running.

**Process-group cleanup**: On timeout or idle-timeout, cleanup sends `SIGKILL` to the entire process group via `os.killpg(os.getpgid(pid), SIGKILL)` rather than just the direct child PID. The subprocess is started with `start_new_session=True` so it leads its own isolated process group. This ensures background `Workflow`/`Task` children spawned during the session are reaped together with the main process; otherwise they would linger as orphans holding pipe write-ends open. Falls back to `process.kill()` on platforms where `os.killpg` is absent (Windows). (ENH-1999)

#### verify_issue_completed

```python
def verify_issue_completed(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger
) -> bool
```

Verify that an issue was marked as completed via frontmatter status check.

Reads the issue file's `status:` frontmatter field; `done` or `cancelled` means the close lifecycle ran successfully. Issues are updated in-place rather than moved, so this is a pure frontmatter check.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration (unused; kept for signature stability)
- `logger` - Logger for output

**Returns:** `True` if issue's frontmatter `status` is `done` or `cancelled`

#### close_issue

```python
def close_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    close_reason: str | None,
    close_status: str | None,
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
    event_bus: EventBus | None = None,
    interceptors: list[Any] | None = None,
) -> bool
```

Close an issue by moving to completed with closure status.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration
- `logger` - Logger for output
- `close_reason` - Reason code (e.g., `"already_fixed"`)
- `close_status` - Status text (e.g., `"Closed - Already Fixed"`)
- `fix_commit` - SHA of the commit that fixed the issue (for regression tracking)
- `files_changed` - List of files modified by the fix (for regression tracking)
- `event_bus` - Optional `EventBus` for emitting lifecycle events during closure
- `interceptors` - Optional list of interceptor objects; each may implement `before_issue_close(info) -> bool | None`. Returning `False` vetoes the close and causes this function to return `False` immediately without moving the issue file.

**Returns:** `True` if successful, `False` if vetoed by an interceptor or if an error occurs

#### complete_issue_lifecycle

```python
def complete_issue_lifecycle(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    event_bus: EventBus | None = None,
) -> bool
```

Fallback: Complete issue lifecycle when command exited early.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration
- `logger` - Logger for output
- `event_bus` - Optional `EventBus` for emitting lifecycle events on completion

**Returns:** `True` if successful

---

## little_loops.issue_lifecycle

Issue lifecycle operations: completing, closing, deferring, and undeferring issues.

```python
from little_loops.issue_lifecycle import defer_issue, undefer_issue
```

### defer_issue

```python
def defer_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> bool
```

Defer an issue by writing `status: deferred` to its frontmatter.

The file remains in its type directory; only the `status:` field changes. Appends a `## Deferred` section with the reason and date, then commits the update.

**Parameters:**
- `info` - Parsed issue info
- `config` - Project configuration
- `logger` - Logger for output
- `reason` - Reason for deferring (default: `"Intentionally set aside for later consideration"`)
- `event_bus` - Optional `EventBus` for emitting `issue.deferred` lifecycle event

**Returns:** `True` if successful, `False` otherwise

### undefer_issue

```python
def undefer_issue(
    config: BRConfig,
    deferred_issue_path: Path,
    logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> Path | None
```

Update a deferred issue in-place: sets status to `open` and emits `issue.started`.

**Parameters:**
- `config` - Project configuration
- `deferred_issue_path` - Path to the issue file (in its type directory, e.g. `.issues/features/`)
- `logger` - Logger for output
- `reason` - Reason for undeferring (optional)
- `event_bus` - Optional `EventBus` for emitting `issue.started` lifecycle event

**Returns:** Same path as `deferred_issue_path` — the issue is updated in-place (status set to `open`), no file is moved; returns `None` if failed

**Example:**

```python
from little_loops.issue_lifecycle import defer_issue, undefer_issue
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
from little_loops.logger import Logger
from pathlib import Path

config = BRConfig(Path.cwd())
logger = Logger()
parser = IssueParser(config)
info = parser.parse_file(Path(".issues/features/P3-FEAT-042-example.md"))

# Defer
defer_issue(info, config, logger, reason="Blocked pending design review")

# Undefer later
new_path = undefer_issue(config, Path(".issues/features/P3-FEAT-042-example.md"), logger)
```

---

## little_loops.state

State persistence for automation resume capability.

### ProcessingState

Persistent state for automated issue processing.

```python
@dataclass
class ProcessingState:
    current_issue: str = ""
    phase: str = "idle"
    timestamp: str = ""
    completed_issues: list[str] = field(default_factory=list)
    failed_issues: dict[str, str] = field(default_factory=dict)
    attempted_issues: set[str] = field(default_factory=set)
    timing: dict[str, dict[str, float]] = field(default_factory=dict)
    corrections: dict[str, list[str]] = field(default_factory=dict)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_issue` | `str` | Path to currently processing issue file |
| `phase` | `str` | Current processing phase |
| `timestamp` | `str` | Last update timestamp |
| `completed_issues` | `list[str]` | List of completed issue IDs |
| `failed_issues` | `dict[str, str]` | Mapping of issue ID to failure reason |
| `attempted_issues` | `set[str]` | Set of issues already attempted |
| `timing` | `dict` | Per-issue timing breakdown |
| `corrections` | `dict[str, list[str]]` | Mapping of issue ID to list of auto-corrections made |

#### Methods

```python
def to_dict(self) -> dict[str, Any]
@classmethod
def from_dict(cls, data: dict[str, Any]) -> ProcessingState
```

### StateManager

Manages persistence of processing state.

```python
from little_loops.state import StateManager
from little_loops.logger import Logger
from pathlib import Path

manager = StateManager(Path(".auto-manage-state.json"), Logger())
state = manager.load()
manager.mark_completed("BUG-001", {"total": 120.5})
manager.save()
```

#### Constructor

```python
StateManager(state_file: Path, logger: Logger, event_bus: EventBus | None = None)
```

**Parameters:**
- `state_file` - Path to the state file
- `logger` - Logger instance for output
- `event_bus` - Optional `EventBus` for emitting state transition events

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `state` | `ProcessingState` | Get current state, creating new if needed |

#### Methods

| Method | Description |
|--------|-------------|
| `load() -> ProcessingState \| None` | Load state from file |
| `save()` | Save current state to file |
| `cleanup()` | Remove state file |
| `update_current(issue_path: str, phase: str)` | Update current issue and phase |
| `mark_attempted(issue_id, *, save=True)` | Mark issue as attempted |
| `mark_completed(issue_id, timing=None)` | Mark issue as completed |
| `mark_failed(issue_id, reason)` | Mark issue as failed |
| `is_attempted(issue_id) -> bool` | Check if issue was attempted |
| `record_corrections(issue_id, corrections)` | Record auto-corrections made to an issue |

---

## little_loops.logger

Logging utilities with colorized output.

### Logger

Simple logger with timestamps and colors.

```python
from little_loops.logger import Logger

logger = Logger(verbose=True, use_color=True)
logger.info("Processing...")
logger.success("Done!")
logger.warning("Check this")
logger.error("Failed!")
logger.timing("Took 5.2 seconds")
logger.header("SUMMARY")
```

#### Constructor

```python
Logger(verbose: bool = True, use_color: bool | None = None, colors: CliColorsConfig | None = None)
```

**Parameters:**
- `verbose` - Whether to output messages (False silences all output)
- `use_color` - Whether to use ANSI color codes. Defaults to `True` unless the `NO_COLOR` environment variable is set or stdout is not a TTY.
- `colors` - Optional `CliColorsConfig` to override default ANSI color codes per log level.

#### Methods

| Method | Color | Description |
|--------|-------|-------------|
| `info(msg)` | Cyan | General information |
| `debug(msg)` | Gray | Debug messages |
| `success(msg)` | Green | Success messages |
| `warning(msg)` | Yellow | Warnings |
| `error(msg)` | Orange | Errors (to stderr) |
| `timing(msg)` | Magenta | Timing information |
| `header(msg, char="=", width=60)` | - | Header with separators |

### format_duration

```python
def format_duration(seconds: float) -> str
```

Format duration in human-readable form.

**Parameters:**
- `seconds` - Duration in seconds

**Returns:** Human-readable string

**Example:**
```python
from little_loops.logger import format_duration

format_duration(65.5)  # "1.1 minutes"
format_duration(45.2)  # "45.2 seconds"
```

---

## little_loops.user_messages

Extract and analyze user messages from Claude Code session logs.

### UserMessage

Extracted user message with metadata.

```python
@dataclass
class UserMessage:
    content: str                                       # The text content of the message
    timestamp: datetime                                # When the message was sent
    session_id: str                                    # Claude Code session identifier
    uuid: str                                          # Unique message identifier
    cwd: str | None = None                             # Working directory when sent
    git_branch: str | None = None                      # Git branch active when sent
    is_sidechain: bool = False                         # Whether this was a sidechain message
    response_metadata: ResponseMetadata | None = None  # Metadata extracted from the assistant response
```

#### Methods

```python
def to_dict(self) -> dict
```
Convert to dictionary for JSON serialization.

### ExampleRecord

Training example pair extracted from a skill invocation session, suitable for APO/prompt-optimization pipelines.

```python
@dataclass
class ExampleRecord:
    skill: str         # Skill name (e.g., "capture-issue")
    input: str         # Concatenated preceding user messages as context
    output: str        # JSON-serialized ResponseMetadata (tools_used, files_modified, completion_status)
    session_id: str    # Claude Code session identifier
    timestamp: datetime
    context_window: int  # Number of preceding messages used
```

#### Methods

```python
def to_dict(self) -> dict
```
Convert to dictionary for JSON serialization. Output includes `type: "example"`.

### build_examples

```python
def build_examples(
    messages: list[UserMessage],
    skill: str,
    context_window: int = 3,
) -> list[ExampleRecord]
```

Build training example pairs from skill invocation sessions.

Groups messages by session, identifies skill trigger records (user-side records containing
`<command-name>/ll:SKILL_NAME</command-name>`), and pairs each with the N preceding messages
as input context.

**Parameters:**
- `messages` - UserMessage list (typically pre-filtered to skill-matching sessions)
- `skill` - Skill name to build examples for (e.g. `"capture-issue"`)
- `context_window` - Number of preceding messages to include as input context (default: 3)

**Returns:** List of `ExampleRecord` objects, one per skill trigger found.

**Example:**
```python
from little_loops.user_messages import extract_user_messages, build_examples, get_project_folder

project_folder = get_project_folder()
messages = extract_user_messages(project_folder, include_response_context=True)
examples = build_examples(messages, "capture-issue", context_window=3)
for ex in examples:
    print(ex.to_dict())
```

### get_project_folder

```python
def get_project_folder(
    cwd: Path | None = None, *, host: str | None = None
) -> Path | None
```

Map a directory to the host's session-log project folder. Dispatches to host-specific
helpers for Claude Code, Codex, OpenCode, and Pi.

**Parameters:**
- `cwd` - Working directory to map (default: current directory)
- `host` - Host identifier: ``"claude-code"``, ``"codex"``, ``"opencode"``, or ``"pi"``.
  If ``None``, auto-detects from the ``LL_HOOK_HOST`` env var (default ``"claude-code"``).

**Returns:** Path to the host's project session folder, or ``None`` if it doesn't exist.

**Example:**
```python
from little_loops.user_messages import get_project_folder
from pathlib import Path

# Map current directory (auto-detect host from LL_HOOK_HOST)
project_folder = get_project_folder()

# Map specific directory for Claude Code
project_folder = get_project_folder(Path("/Users/me/my-project"), host="claude-code")
# Returns: ~/.claude/projects/-Users-me-my-project

# Map for Codex
project_folder = get_project_folder(host="codex")
# Returns: ~/.codex/projects/-Users-me-my-project
```

**Internal helpers:**

- ``_get_claude_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.claude/projects/<encoded_path>``
- ``_get_codex_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.codex/projects/<encoded_path>``
- ``_get_opencode_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.opencode/projects/<encoded_path>``
- ``_get_pi_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.pi/projects/<encoded_path>`` (stub; Pi adapter deferred per FEAT-992)

Each helper returns the ``Path`` if the directory exists, or ``None`` otherwise.

**Encoding rule:** ``encode_project_path(path_str: str) -> str`` (also exported from
``little_loops.user_messages``) maps every non-alphanumeric character — slashes, dots,
underscores, hyphens — 1:1 to a single ``-``. Consecutive special characters are **not**
collapsed: a cwd segment like ``/.worktrees/`` (slash followed by dot) encodes to
``--worktrees`` (two dashes), matching Claude Code's on-disk project-folder naming. This
matters for git worktree checkouts (``ll-parallel`` / ``ll-sprint`` / subloop epics),
whose paths always contain a dotted ``.worktrees/`` segment.

### discover_all_projects

```python
def discover_all_projects(
    logger: Logger, *, host: str | None = None
) -> list[Path]
```

Discover all projects with ll activity for the given host. Iterates the host's session
directory (e.g. ``~/.claude/projects/`` for Claude Code, ``~/.codex/projects/`` for
Codex), resolves each directory name back to an absolute path, checks for ll-relevant
JSONL records, and returns a sorted list of paths that exist on disk.

**Parameters:**
- ``logger`` - Logger instance for warnings.
- ``host`` - Host identifier: ``"claude-code"``, ``"codex"``, ``"opencode"``, or ``"pi"``.
  If ``None``, auto-detects from the ``LL_HOOK_HOST`` env var (default ``"claude-code"``).

**Returns:** Sorted list of decoded absolute paths for projects with ll activity.

**Example:**
```python
from little_loops.cli.logs import discover_all_projects
from little_loops.logger import Logger

logger = Logger.get()
projects = discover_all_projects(logger)
# ['/Users/me/my-project', '/Users/me/other-project']

# Discover Codex projects
projects = discover_all_projects(logger, host="codex")
```

**Implementation:** Uses the same four-way host dispatch as ``get_project_folder()``.
Decodes project directory names back to absolute paths by preferring the ``cwd`` field
from JSONL records first, then falling back to string-replacing ``-`` with ``/``. The
fallback decode is inherently lossy — the encode side (``encode_project_path()``) maps
dots, underscores, and hyphens all onto the same ``-``, so a bare reverse-replace can't
reconstruct the original path exactly. This is why the ``cwd``-from-JSONL preference
exists: it is the only exact source of the original path, and the round trip only holds
because that field is checked first.
Filters to directories that contain ll-relevant JSONL records via ``_has_ll_activity()``.
Returns an empty list for unknown host identifiers.

### extract_user_messages

```python
def extract_user_messages(
    project_folder: Path,
    limit: int | None = None,
    since: datetime | None = None,
    include_agent_sessions: bool = True,
    include_response_context: bool = False,
) -> list[UserMessage]
```

Extract user messages from all JSONL session files in a project folder.

**Parameters:**
- `project_folder` - Path to Claude project folder
- `limit` - Maximum number of messages to return
- `since` - Only include messages after this datetime
- `include_agent_sessions` - Whether to include agent-*.jsonl files
- `include_response_context` - Whether to include the assistant response immediately following each user message

**Returns:** Messages sorted by timestamp, most recent first.

**Filters:**
- Only messages with `type == "user"`
- Excludes tool results (array content with `tool_result` type)

**Example:**
```python
from datetime import datetime
from little_loops.user_messages import extract_user_messages, get_project_folder

project_folder = get_project_folder()
if project_folder:
    # Get last 50 messages
    messages = extract_user_messages(project_folder, limit=50)

    # Get messages since a date
    since = datetime(2026, 1, 1)
    recent = extract_user_messages(project_folder, since=since)

    for msg in messages:
        print(f"[{msg.timestamp}] {msg.content[:50]}...")
```

### save_messages

```python
def save_messages(
    messages: list[UserMessage],
    output_path: Path | None = None,
) -> Path
```

Save messages to a JSONL file.

**Parameters:**
- `messages` - List of UserMessage objects to save
- `output_path` - Output file path. If None, uses `.ll/user-messages-{timestamp}.jsonl`

**Returns:** Path to the saved file.

### print_messages_to_stdout

```python
def print_messages_to_stdout(messages: list[UserMessage]) -> None
```

Print messages to stdout in JSONL format.

**Parameters:**
- `messages` - List of UserMessage objects to print

---

## little_loops.parallel

Parallel processing subpackage with git worktree isolation.

### ParallelOrchestrator

Main controller for parallel issue processing.

```python
from little_loops.config import BRConfig
from little_loops.parallel import ParallelOrchestrator
from pathlib import Path

br_config = BRConfig(Path.cwd())
parallel_config = br_config.create_parallel_config(max_workers=3)

orchestrator = ParallelOrchestrator(
    parallel_config=parallel_config,
    br_config=br_config,
    repo_path=Path.cwd(),
    verbose=True
)
exit_code = orchestrator.run()
```

#### Constructor

```python
ParallelOrchestrator(
    parallel_config: ParallelConfig,
    br_config: BRConfig,
    repo_path: Path | None = None,
    verbose: bool = True,
    wave_label: str | None = None,
    event_bus: EventBus | None = None,
)
```

**Parameters:**
- `parallel_config` - Parallel processing configuration
- `br_config` - Project configuration
- `repo_path` - Path to the git repository (default: current directory)
- `verbose` - Whether to output progress messages
- `wave_label` - Optional label for wave-based execution (e.g., `"Wave 1"`)
- `event_bus` - Optional `EventBus` for emitting worker completion events

#### Methods

| Method | Description |
|--------|-------------|
| `run() -> int` | Run parallel issue processor, returns exit code |

### WorkerPool

Thread pool for processing issues in isolated git worktrees.

```python
from little_loops.parallel import WorkerPool

pool = WorkerPool(parallel_config, br_config, logger, repo_path)
pool.start()
future = pool.submit(issue_info, on_complete_callback)
result = future.result()  # WorkerResult
pool.shutdown()
pool.cleanup_all_worktrees()
```

#### Constructor

```python
WorkerPool(
    parallel_config: ParallelConfig,
    br_config: BRConfig,
    logger: Logger,
    repo_path: Path | None = None,
)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `active_count` | `int` | Number of active workers |

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start the worker pool |
| `submit(issue: IssueInfo, on_complete: Callable[[WorkerResult], None] \| None = None) -> Future` | Submit issue for processing |
| `shutdown(wait=True)` | Shutdown the worker pool |
| `cleanup_all_worktrees()` | Remove all worktree directories |

### Output Parsing

Utilities for parsing Claude's output from `/ll:ready-issue` commands. Located at `little_loops.output_parsing`.

#### parse_ready_issue_output

```python
def parse_ready_issue_output(output: str) -> dict[str, Any]
```

Parse the output from a `/ll:ready-issue` command to extract verdict and metadata.

**Parameters:**
- `output` - Raw stdout from Claude CLI

**Returns:** Dictionary with parsed results:

```python
{
    "verdict": str,              # READY, CORRECTED, NOT_READY, NEEDS_REVIEW, CLOSE, or UNKNOWN
    "concerns": list[str],       # List of concerns from ## CONCERNS section
    "is_ready": bool,            # True if verdict is READY or CORRECTED
    "was_corrected": bool,       # True if verdict is CORRECTED
    "should_close": bool,        # True if verdict is CLOSE
    "close_reason": str | None,  # Reason code (e.g., "already_fixed", "invalid_ref")
    "close_status": str | None,  # Status text (e.g., "Closed - Already Fixed")
    "corrections": list[str],    # List of corrections made
    "validated_file_path": str | None,  # File path from validation
    "sections": dict,            # Raw parsed sections
    "validation": dict           # Validation details
}
```

**Example:**
```python
from little_loops.output_parsing import parse_ready_issue_output

result = subprocess.run(["claude", "-p", "/ll:ready-issue BUG-001"], capture_output=True, text=True)
parsed = parse_ready_issue_output(result.stdout)

if parsed["is_ready"]:
    print(f"Issue ready! Was corrected: {parsed['was_corrected']}")
elif parsed["should_close"]:
    print(f"Issue should be closed: {parsed['close_reason']}")
else:
    print(f"Not ready: {len(parsed['concerns'])} concern(s)")
```

#### Valid Verdicts

| Verdict | Description | `is_ready` | `should_close` |
|---------|-------------|------------|----------------|
| `READY` | Issue is prepared for implementation | `True` | `False` |
| `CORRECTED` | Issue had problems that were auto-fixed | `True` | `False` |
| `NOT_READY` | Issue has concerns preventing implementation | `False` | `False` |
| `NEEDS_REVIEW` | Requires manual review | `False` | `False` |
| `CLOSE` | Issue should be closed (already fixed, invalid, etc.) | `False` | `True` |
| `UNKNOWN` | Verdict could not be parsed (error state) | `False` | `False` |

#### Parsing Strategy

The parser uses a 6-step fallback strategy to extract verdicts:

1. **New format**: Look for `## VERDICT` section header
2. **Old format**: Match `VERDICT: <keyword>` pattern via regex
3. **Keyword scan**: Search lines containing "verdict" for keywords
4. **Full scan**: Search entire output for verdict keywords
5. **Clean retry**: Remove markdown formatting and retry extraction
6. **Infer from READY_FOR**: If still unknown, check `## READY_FOR` section for "Implementation: Yes"

This multi-step approach handles variations in Claude's output formatting (bold, backticks, headers) and different response styles.

#### Tool-Specific Verdict Handling

Both `ll-auto` and `ll-parallel` use `parse_ready_issue_output()` but handle results differently:

| Aspect | ll-auto | ll-parallel |
|--------|---------|-------------|
| **UNKNOWN verdict** | Logs and proceeds | Returns error with output snippet for debugging |
| **CLOSE handling** | Validates "invalid_ref" reason, checks file path | Generic handling via WorkerResult flags |
| **File validation** | Validates path with fallback retry | None (relies on worktree isolation) |

### JSON Output Helpers

Stop-sequence / prefill recipes for bounding the *output* tokens an LLM spends
emitting structured data (FEAT-2470, EPIC-2456 Tier 0). Located at
`little_loops.output.parse`. Both return a `(value, error)` tuple — the same
convention as `output_parsing.extract_tagged_json` (BUG-2383); neither swallows,
so callers must surface `error` when `value is None`.

#### extract_between_tags

```python
def extract_between_tags(start_tag: str, end_tag: str, raw: str) -> tuple[str | None, str | None]
```

Extract the text between `start_tag` and `end_tag`. Pairs with the **stop-sequence**
recipe: set `end_tag` as the model's stop sequence so generation halts the instant
the payload is complete. Tolerates a missing `end_tag` (returns the remainder after
`start_tag`). Returns `(None, error)` only when `start_tag` is absent.

#### parse_prefilled_json

```python
def parse_prefilled_json(raw: str) -> tuple[Any | None, str | None]
```

Parse a JSON object from prefilled output. Pairs with the **prefill** recipe
(seed the assistant turn with `{`). Tries a verbatim parse first, then falls back
to the `rfind('{')` recipe — scanning from the last `{` to its matching `}` via a
string-aware bracket-depth walk — so leading fragments or trailing prose don't
break it.

```python
from little_loops.output.parse import extract_between_tags, parse_prefilled_json

payload, err = extract_between_tags("<json>", "</json>", raw_output)
verdict, err = parse_prefilled_json(raw_output)  # raw begins with "{"
```

### Output Cleaner

Anti-event + duplicate-window pre-filter (FEAT-2470, EPIC-2456 technique [25])
that trims avoidable token cost from tool/log output before it enters the model's
context. Located at `little_loops.output_cleaner`.

#### filter_output

```python
def filter_output(raw: str, *, dup_threshold: int = 1) -> str
```

Strips ANSI, drops **anti-event** lines (tqdm/ascii progress bars, spinner frames,
pytest-xdist worker chatter), and collapses **duplicate windows** — runs of
consecutive identical lines become a single line plus a `… (repeated N×)` marker
once the run exceeds `dup_threshold`. Consecutive blank lines collapse to one.
Trailing-newline presence is preserved.

```python
from little_loops.output_cleaner import filter_output

trimmed = filter_output(noisy_pytest_stdout)
```

### MergeCoordinator

Sequential merge queue with sophisticated conflict handling, error recovery, and adaptive strategies.

**See [MERGE-COORDINATOR.md](../development/MERGE-COORDINATOR.md) for comprehensive documentation.**

```python
from little_loops.parallel import MergeCoordinator

coordinator = MergeCoordinator(config, logger, repo_path)
coordinator.start()
coordinator.queue_merge(worker_result)
coordinator.wait_for_completion(timeout=120)
coordinator.shutdown()
```

#### Constructor

```python
MergeCoordinator(
    config: ParallelConfig,
    logger: Logger,
    repo_path: Path | None = None,
)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `merged_ids` | `list[str]` | Successfully merged issue IDs |
| `failed_merges` | `dict[str, str]` | Failed merges with errors |
| `stash_pop_failures` | `dict[str, str]` | Issues where merge succeeded but stash restore failed |
| `pending_count` | `int` | Pending merge requests |

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start the merge coordinator background thread |
| `queue_merge(result)` | Queue a worker result for merging |
| `wait_for_completion(timeout)` | Wait for all pending merges |
| `shutdown(wait=True, timeout=30.0)` | Shutdown the coordinator |

### ParallelConfig

Configuration dataclass for parallel processing.

```python
@dataclass
class ParallelConfig:
    max_workers: int = 2
    p0_sequential: bool = True
    merge_interval: float = 30.0
    worktree_base: Path = field(default_factory=lambda: Path(".worktrees"))
    state_file: Path = field(default_factory=lambda: Path(".parallel-manage-state.json"))
    max_merge_retries: int = 2
    priority_filter: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    max_issues: int = 0
    dry_run: bool = False
    timeout_per_issue: int = 3600
    idle_timeout_per_issue: int = 0
    orchestrator_timeout: int = 0
    stream_subprocess_output: bool = False
    show_model: bool = False
    command_prefix: str = "/ll:"
    ready_command: str = "ready-issue {{issue_id}}"
    manage_command: str = "manage-issue {{issue_type}} {{action}} {{issue_id}}"
    decide_command: str = "decide-issue {{issue_id}}"
    only_ids: set[str] | None = None
    skip_ids: set[str] | None = None
    type_prefixes: set[str] | None = None
    label_filter: set[str] | None = None
    require_code_changes: bool = True
    use_feature_branches: bool = False
    push_feature_branches: bool = False
    open_pr_for_feature_branches: bool = False
    worktree_copy_files: list[str] = field(default_factory=lambda: [".claude/settings.local.json", ".env"])
    merge_pending: bool = False
    clean_start: bool = False
    ignore_pending: bool = False
    overlap_detection: bool = False
    serialize_overlapping: bool = True
    skip_learning_gate: bool = False
    base_branch: str | None = None
    remote_name: str = "origin"
    epic_branches: EpicBranchesConfig = field(default_factory=EpicBranchesConfig)
```

#### Methods

##### get_ready_command

```python
def get_ready_command(self, issue_id: str) -> str
```

Build the ready-issue command string.

**Parameters:**
- `issue_id` - Issue identifier

**Returns:** Complete command string (e.g., `"/ll:ready-issue BUG-001"`)

##### get_manage_command

```python
def get_manage_command(self, issue_type: str, action: str, issue_id: str) -> str
```

Build the manage-issue command string.

**Parameters:**
- `issue_type` - Type of issue (bug, feature, enhancement)
- `action` - Action to perform (fix, implement, improve)
- `issue_id` - Issue identifier

**Returns:** Complete command string

### EpicBranchesConfig

Per-EPIC integration branch configuration (FEAT-2339). Declared twice with
identical fields — a runtime dataclass at `little_loops.parallel.types` (held by
`ParallelConfig.epic_branches`) and an automation-side dataclass at
`little_loops.config.automation` (held by `parallel.epic_branches` in config).
`BRConfig.create_parallel_config` converts the automation form to the runtime
form via `_build_parallel_epic_branches`.

```python
@dataclass
class EpicBranchesConfig:
    enabled: bool = False              # master switch; False preserves per-worker behavior
    prefix: str = "epic/"              # branch = f"{prefix}{epic_id.lower()}-{slug}"
    merge_to_base_on_complete: bool = True  # merge EPIC branch to base after last child
    open_pr: bool = False              # open a PR for the EPIC branch via gh on completion
    verify_before_merge: bool = False  # run test_cmd/lint_cmd against the branch tip before merge/PR-open (ENH-2603)
```

When `enabled`, `WorkerPool` routes every child of a shared `parent:` EPIC onto
one `epic/<EPIC-ID>-<slug>` branch (fork point and merge target), recorded on
`WorkerResult.epic_branch`. See [Configuration reference](CONFIGURATION.md#parallel).

BUG-2614: the merge/verify/PR logic is implemented as three stateless free functions
in `little_loops.worktree_utils` — `verify_epic_branch_before_merge`,
`merge_epic_branch_to_base`, `open_pr_for_epic_branch` — extracted from what were
previously `ParallelOrchestrator` instance methods, so both `ll-parallel`'s
`WorkerPool` completion path and the `auto-refine-and-implement` FSM loop's
`merge_epic_branch` state can share one implementation instead of the FSM loop
reimplementing it inline. `ParallelOrchestrator._verify_epic_branch_before_merge`/
`_merge_epic_branch_to_base`/`_open_pr_for_epic_branch` remain as thin wrappers that
adapt the free functions to this instance's config/state (`self._git_lock`,
`self.repo_path`, `self._merged_epic_branches` idempotency set,
`self._epic_branch_verify_failures` reporting dict — none of which the free functions
take directly, since they're specific to `WorkerPool`'s concurrency model).

When `verify_before_merge` is `True`, `verify_epic_branch_before_merge` checks out the
EPIC branch tip in a scratch worktree (via `worktree_utils.setup_worktree(...,
checkout_existing=True)`), runs `test_cmd`/`lint_cmd` against it, and always tears the
worktree down, returning `(ok, message, returncode)` (ENH-2631: `returncode` is the
failing process exit code — `None` on success or a worktree-setup failure — so callers
can tell a pytest collection/usage error, exit 2, from a real test failure, exit 1,
without re-running the suite). When the optional `src_dir` kwarg is truthy
(callers forward `project.src_dir`, e.g. `"scripts"`), the verify subprocess prepends
the worktree's `<worktree>/<src_dir>` onto `PYTHONPATH` so branch-only modules resolve
to the worktree — defeating editable-install `.pth` shadowing that would otherwise
resolve `import little_loops.<new_module>` to the main checkout and false-fail
collection (BUG-2629). When `src_dir` is falsy (default `None`), no injection occurs,
preserving prior behavior for non-editable / non-Python setups. Independent of
`src_dir`, the verify subprocess always carries `LL_VERIFY_GATE="1"` in its
environment (BUG-2649, mirroring the `LL_NON_INTERACTIVE` marker idiom): tests
that are non-deterministic under the gate's non-standard invocation (injected
`PYTHONPATH` + parallel-xdist worktree) detect it via
`os.environ.get("LL_VERIFY_GATE") == "1"` and quarantine themselves
(`pytest.mark.skipif`) rather than false-negative a genuinely mergeable branch —
the assertions still run under the standard `python -m pytest scripts/tests/`
invocation off the gate. On the `ll-parallel` path, a failure blocks
the merge/PR-open (the branch is NOT added to `_merged_epic_branches`, so it is retried
on the next completion event), and the message is recorded in
`ParallelOrchestrator.epic_branch_verify_failures` (EPIC ID → message), which
`_report_results()` surfaces in the run summary (ENH-2603). On the FSM loop path, the
`merge_epic_branch` state writes the outcome to a `$RUN_DIR/epic-merge-verdict.txt`
artifact instead — the loop runs `merge_epic_branch` exactly once per execution, so no
idempotency set or failure dict is needed; a branch that no longer exists (already
merged) is the sole idempotency signal. ENH-2630: on the FSM loop path the
`verify` state runs `verify_epic_branch_before_merge` first (unconditionally) and
records both its verdict (`$RUN_DIR/verify-verdict.txt`) and the epic tip SHA
(`$RUN_DIR/verify-sha.txt`). `merge_epic_branch` then **reuses** that verdict —
skipping its own `verify_epic_branch_before_merge` call — when the verdict is
`passed` and the recorded SHA still matches the current epic tip (the two states
run back-to-back, so it normally does), avoiding a redundant second full-suite
run. It falls back to invoking the gate only when the verdict is missing,
non-`passed`, or the SHA is stale, so the binding gate still cannot merge a
failing tip.

ENH-2643: `merge_epic_branch_to_base` accepts an optional keyword-only
`run_dir: Path | None = None`. On the FSM loop path the `merge_epic_branch` state
threads `run_dir=$RUN_DIR` through, so a merge *failure* — before `git merge
--abort` discards the conflict state — persists three flat-text diagnostic
artifacts under the run dir, mirroring the verify gate's `verify-detail.txt`
pair: `merge-returncode.txt` (the failing `git merge` exit code),
`merge-detail.txt` (the bounded `stderr + stdout` tail via `format_verify_detail`),
and `merge-conflicts.txt` (the conflicted-path list from `git diff --name-only
--diff-filter=U`). A clean merge writes none of them. The `ll-parallel`
orchestrator wrapper has no per-run `run_dir` and omits the kwarg (defaults to
`None` → nothing persisted), so its behavior is unchanged.

### WorkerResult

Result from a worker processing an issue.

```python
@dataclass
class WorkerResult:
    issue_id: str
    success: bool
    branch_name: str
    worktree_path: Path
    changed_files: list[str] = field(default_factory=list)
    leaked_files: list[str] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    was_corrected: bool = False
    corrections: list[str] = field(default_factory=list)
    should_close: bool = False
    close_reason: str | None = None
    close_status: str | None = None
    was_blocked: bool = False
    interrupted: bool = False
    epic_branch: str | None = None  # EPIC integration branch this worker forked
                                    # from / merges into (FEAT-2452); None for
                                    # standalone issues or when epic_branches is
                                    # disabled
```

### IssuePriorityQueue

Priority queue for issue processing. Located at `little_loops.parallel.priority_queue`.

```python
from little_loops.parallel.priority_queue import IssuePriorityQueue

queue = IssuePriorityQueue()
added = queue.add_many(issues)
queued_issue = queue.get(block=False)
queue.mark_completed(issue_id)
queue.mark_failed(issue_id)
```

#### Methods

| Method | Description |
|--------|-------------|
| `add(issue_info) -> bool` | Add a single issue |
| `add_many(issues) -> int` | Add multiple issues, return count added |
| `get(block=True, timeout=None)` | Get next issue from queue |
| `mark_completed(issue_id)` | Mark issue as completed |
| `mark_failed(issue_id)` | Mark issue as failed |
| `qsize() -> int` | Count of issues currently in queue |
| `in_progress_count() -> int` | Count of issues currently being processed |
| `completed_count() -> int` | Count of completed issues |
| `failed_count() -> int` | Count of failed issues |

### Additional Types

Located at `little_loops.parallel.types`:

#### SprintWorkerContext

Sprint worker identity injected into guillotine continuation prompts (BUG-2141).
Tells a fresh Option J session which single issue it must complete and that it
must exit immediately after — preventing deadlock where a fresh session processes
multiple visible issues and blocks on "What next?".

```python
@dataclass
class SprintWorkerContext:
    issue_id: str   # e.g. "FEAT-025"
    branch: str     # Git branch for this worker (main or worktree branch)

    def to_dict(self) -> dict[str, Any]: ...
```

#### QueuedIssue

```python
@dataclass
class QueuedIssue:
    priority: int
    issue_info: IssueInfo
    timestamp: float
```

#### MergeStatus

```python
class MergeStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    CONFLICT = "conflict"
    FAILED = "failed"
    RETRYING = "retrying"
```

#### MergeRequest

```python
@dataclass
class MergeRequest:
    worker_result: WorkerResult
    status: MergeStatus = MergeStatus.PENDING
    retry_count: int = 0
    error: str | None = None
    queued_at: float
```

#### OrchestratorState

```python
@dataclass
class OrchestratorState:
    in_progress_issues: list[str]
    completed_issues: list[str]
    failed_issues: dict[str, str]
    pending_merges: list[str]
    timing: dict[str, dict[str, float]]
    corrections: dict[str, list[str]]   # Issue ID → corrections made (for pattern analysis)
    started_at: str
    last_checkpoint: str
```

#### WorkerStage

```python
class WorkerStage(Enum):
    SETUP = "setup"                # Creating git worktree and copying .claude/
    VALIDATING = "validating"      # Running ready-issue command
    PROVING = "proving"            # Running proof-first-task assumption-firewall gate
    IMPLEMENTING = "implementing"  # Running manage-issue command
    VERIFYING = "verifying"        # Checking work was done and updating branch base
    MERGING = "merging"            # Awaiting merge coordination
    COMPLETED = "completed"        # Successfully finished
    FAILED = "failed"              # Failed at some stage
    INTERRUPTED = "interrupted"    # Interrupted during shutdown
```

Located at `little_loops.parallel.types`.

#### PendingWorktreeInfo

```python
@dataclass
class PendingWorktreeInfo:
    worktree_path: Path             # Path to the worktree directory
    branch_name: str | None         # Git branch from rev-parse, or None if unavailable
    issue_id: str                   # Extracted issue ID (e.g., "BUG-045")
    commits_ahead: int              # Commits ahead of main
    has_uncommitted_changes: bool   # Whether there are uncommitted changes
    changed_files: list[str]        # Files with uncommitted changes
```

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `has_pending_work` | `bool` | `True` if `commits_ahead > 0` or `has_uncommitted_changes` |

Located at `little_loops.parallel.types`.

#### OverlapResult

```python
@dataclass
class OverlapResult:
    has_overlap: bool = False
    overlapping_issues: list[str] = []    # Issue IDs that overlap
    overlapping_files: set[str] = set()   # Specific files/paths that overlap
```

`bool(result)` returns `result.has_overlap`. Located at `little_loops.parallel.overlap_detector`.

#### OverlapDetector

Thread-safe tracker for detecting file modification conflicts between parallel issues. Located at `little_loops.parallel.overlap_detector`.

```python
class OverlapDetector:
    def __init__(self, config: DependencyMappingConfig | None = None) -> None
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `register_issue(issue)` | `FileHints` | Register an issue as actively being processed |
| `unregister_issue(issue_id)` | `None` | Unregister a completed issue |
| `check_overlap(issue)` | `OverlapResult` | Check for conflicts without registering |
| `get_active_issues()` | `list[str]` | List currently active issue IDs |
| `get_hints(issue_id)` | `FileHints \| None` | Get hints for a registered issue |
| `clear()` | `None` | Clear all tracked issues |

**Usage pattern:**
```python
from little_loops.parallel.overlap_detector import OverlapDetector

detector = OverlapDetector()
result = detector.check_overlap(new_issue)
if not result:
    detector.register_issue(new_issue)
    # ... process issue ...
    detector.unregister_issue(new_issue.issue_id)
```

---

## little_loops.cli

CLI entry points for the package.

### main_action

```python
def main_action() -> int
```

Entry point for `ll-action` command. Thin CLI wrapper for invoking ll skills as one-shot commands with JSON-structured output.

**Returns:** Exit code

**Subcommands:**
- `invoke <skill> [--args ARG ...] [--timeout SECONDS] [--output stream-json|json]` — invoke a skill and stream NDJSON events or collect JSON
- `capabilities` — emit `CapabilityReport` as JSON
- `list` — list all skills with names, descriptions, and argument hints

**`list` output shape:**

```json
[
  {"name": "refine-issue", "description": "...", "args": "ISSUE_ID [--auto] [--dry-run]"},
  {"name": "old-skill", "description": "...", "args": null}
]
```

The `args` field is sourced from the `args:` frontmatter field in `skills/<name>/SKILL.md`. If `args:` is absent but `argument-hint:` is present, `argument-hint:` is used as a fallback. The field is `null` when neither is set.

---

### main_auto

```python
def main_auto() -> int
```

Entry point for `ll-auto` command. Process all backlog issues sequentially in priority order.

Supports `--skip-learning-gate` to bypass the per-issue learning-test gate (equivalent to `ll-sprint`'s `--skip-learning-gate` flag). The gate runs `proof-first-task` between the ready and implement phases for each issue whose resolved targets are non-empty.

**Returns:** Exit code

### main_loop

```python
def main_loop() -> int
```

Entry point for `ll-loop` command. FSM-based automation loop execution.

**Returns:** Exit code

**Signal handling (`ll-loop run`):**

When `ll-loop run` is executing a loop in the foreground, the process
registers POSIX signal handlers for `SIGINT` (Ctrl-C) and `SIGTERM`
(`scripts/little_loops/cli/loop/_helpers.py:157-173`). The contract is:

| Signal | Behavior |
|--------|----------|
| `SIGINT` (1st) / `SIGTERM` | Graceful shutdown: the executor completes its current state, then `PersistentExecutor.run` calls `archive_run()`. The audit trail (`events.jsonl`, `state.json`, `.history/<run_id>-<loop_name>/` archive) is complete. Exit code: `0`. |
| `SIGINT` (2nd) | Force-exit: the signal handler calls `archive_run_only(terminated_by="interrupted_force")` *before* `sys.exit(1)` (ENH-2516, `scripts/little_loops/cli/loop/_helpers.py:103-107`). The `.history/<run_id>-<loop_name>/` archive still lands. Exit code: `1`. |
| `SIGKILL` (`kill -9`) | **Cannot be trapped.** Data already written via `_append_jsonl` (ENH-2515, `scripts/little_loops/fsm/persistence.py:129-145`) is durable, but the `.history/<run_id>-<loop_name>/` archive and the final `state.json` snapshot may not land. To prevent silent data loss, run `ll-loop run` under a supervisor (`systemd`, `supervisord`), a terminal multiplexer (`tmux`, `screen`), or `nohup` so the loop receives `SIGTERM` (which is trap-able) on shutdown rather than `SIGKILL`. |

The end-to-end SIGINT contract is locked by
`scripts/tests/test_fsm_signal_integration.py`.

### main_issues

```python
def main_issues() -> int
```

Entry point for `ll-issues` command. Issue management and visualization utilities.

**Returns:** Exit code

**Sub-commands:**

| Sub-command | Description |
|-------------|-------------|
| `next-id` | Print next globally unique issue number; `--count N` / `-n N` emits N consecutive IDs from a single scan |
| `list` | List active issues with optional type/priority filters |
| `search` | Search issues with text query, filters, sorting, and multiple output formats |
| `count` | Count active issues with optional filters (`--type`, `--priority`, `--json`) |
| `show` | Show summary card for a single issue |
| `sequence` | Suggest dependency-ordered implementation sequence |
| `impact-effort` | Display impact vs effort matrix for active issues |
| `refine-status` | Refinement depth table sorted by commands touched (`--type`, `--format json`) |
| `next-action` | Next refinement action needed across all active issues (for FSM loop use) |
| `next-issue` | Single highest-confidence issue ID (alias: `nx`) |
| `next-issues` | All active issues in ranked order (alias: `nxs`); optional count argument |
| `append-log` | Append a session log entry to an issue file |
| `clusters` | Visualize issue dependency clusters as box diagrams (`--include-orphans`, `--min-connections N`, `--json`, `--edges SET`, `--status SET`) |
| `anchor-sweep` | Rewrite bare `file:line` references in active issue files to enclosing anchor form (`--dry-run`, `--issues-dir DIR`) |
| `fingerprint` | Extract structured fingerprint (id, files_to_modify, key_terms) from an issue file as JSON; used by `audit-issue-conflicts` Phase 2b (`--cross-theme`) |
| `check-flag` | Exit 0 if a named boolean frontmatter field equals `true`; takes `issue_id` and `field` positional args |
| `check-decidable` | Exit 0 if an issue has >=1 enumerable option to decide between (deterministic companion to `/ll:decide-issue --validate-only`, ENH-2443) |
| `check-readiness` | Exit 0 if `confidence_score` and `outcome_confidence` meet thresholds; reads from `ll-config.json` or `--readiness`/`--outcome` flags |
| `epic-consistency` | Detect and reconcile EPIC body/parent drift (`--all`, `--fix`, `--format text\|json`); exits non-zero when drift found in report-only mode |
| `deferred-triage` | List `deferred_by: automation` issues awaiting human triage, with reason + age (alias: `dt`) |

#### deferred-triage

```
ll-issues deferred-triage [--format text|json|markdown]
ll-issues dt [--format text|json|markdown]
```

Lists `status: deferred` issues with `deferred_by: automation` — the discriminator stamped by
`ll-issues set-status <ID> deferred --by automation --reason <code>` (see `mark_deferred` in
`loops/rn-implement.yaml`, and the equivalent not-ready exits in `loops/autodev.yaml` —
`mark_gate_blocked`, `record_decision_unresolved`, `recheck_after_size_review` — added by
ENH-2666 to align autodev's not-ready handling to the same model) — showing `deferred_reason`
and age-since-`deferred_date`. `deferred_by: human` (or absent) issues are excluded.
`remediation_stalled` entries rank above `blocked_by_unmet`, above `gate_blocked`, above
`decision_unresolved`, above `low_readiness`; ties break oldest-first. This closes the cross-run
resurfacing gap FEAT-2665 targets: `re_enqueue_unblocked` only re-surfaces within a single run.

#### next-issue

```
ll-issues next-issue [--json] [--path] [--skip ISSUE_IDS] [--include-blocked]
ll-issues nx [--json] [--path] [--skip ISSUE_IDS] [--include-blocked]
```

Print the single highest-confidence active issue ID. Uses the same sort key as `next-issues`.

By default (ENH-2436), issues whose `Blocked By` references a non-terminal
(`done`/`cancelled`) issue are filtered out of the candidate set, so the
returned ID is always actionable. Pass `--include-blocked` to revert to the
legacy behavior (return any active issue, blocked or not).

EPIC-type ids are never returned (BUG-2638), in any output mode — EPICs are
umbrella containers meant to be decomposed via scope resolution, not implemented
as leaves.

**Output flags:**
- `--json` - Output as a JSON object with fields: `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`. When `--include-blocked` is also set, the row additionally carries `blocked` (bool), `blocked_by` (sorted list of issue IDs), and `pending_prerequisites` (sorted list of still-open soft `depends_on` targets, ENH-2635). `blocked` reflects hard `blocked_by` edges only; combined with `pending_prerequisites` this distinguishes three states — **hard-blocked** (`blocked: true`), **soft-deferred** (`blocked: false` with a non-empty `pending_prerequisites`), and **ready** (`blocked: false`, `pending_prerequisites: []`). The default (no-flag) path already filters both hard and soft edges via `get_ready_issues()`, so it never returns a soft-deferred pick; this field only matters in the `--include-blocked` reporting mode.
- `--path` - Output only the file path instead of the issue ID

**Filter flags:**
- `--skip ISSUE_IDS` - Comma-separated list of issue IDs to exclude (e.g., `BUG-003,FEAT-004`). Useful in FSM loops to skip issues already attempted in the current session.
- `--include-blocked` (ENH-2436) - Re-include issues with unresolved blockers in the ranked output. Each JSON row carries `blocked` (bool), `blocked_by` (sorted list), and `pending_prerequisites` (sorted list of open soft `depends_on` targets, ENH-2635) fields when this flag is set.

**Exit codes:** 0 when an issue is found; 1 when no active issues exist or when every active issue is currently blocked (the latter surfaces `Error: No ready issues (N blocked, 0 ready)` on stderr).

**Strategy**: Config-driven via `issues.next_issue.strategy` (default `confidence_first`). See [`NextIssueConfig`](#nextissueconfig) for available presets and custom sort keys.

**Sort key (default, `confidence_first`)**: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int` — byte-identical to the legacy hardcoded tuple.

**Configuration**: Switch strategies via `.ll/ll-config.json`:
```json
{
  "issues": {
    "next_issue": { "strategy": "priority_first" }
  }
}
```

**Examples:**
```bash
ll-issues next-issue                            # print top unblocked issue ID
ll-issues nx --json                             # top unblocked issue as JSON object
ll-issues nx --path                             # top unblocked issue file path
ll-issues nx --skip BUG-003,FEAT-004            # skip specific issues
ll-issues nx --include-blocked                  # include blocked issues (legacy behavior)
ll-issues nx --include-blocked --json           # JSON with blocked / blocked_by / pending_prerequisites
```

**FSM loop use**: Use `--skip` to avoid re-selecting issues already processed in the current loop run. Pair with `next-issues` when you need the full ranked list. Loops that need the legacy behavior (i.e. pick any active issue even if blocked) should pass `--include-blocked` to opt back in.

#### next-issues

```
ll-issues next-issues [COUNT] [--json] [--path] [--include-blocked]
ll-issues nxs [COUNT] [--json] [--path] [--include-blocked]
```

Print all active issues sorted by outcome confidence, readiness score, and priority. Returns one issue ID per line by default.

By default (ENH-2436), issues whose `Blocked By` references a non-terminal
(`done`/`cancelled`) issue are filtered out of the ranked list. Pass
`--include-blocked` to revert to the legacy behavior (return every active
issue, blocked or not).

EPIC-type ids are never included in the ranked list (BUG-2638), in any output
mode — EPICs are decomposed via scope resolution, not ranked as implementable
leaves. This also prevents an EPIC and its own children from being
double-dispatched into the same backlog wave.

**Arguments:**
- `COUNT` - Optional integer; limit output to top N issues

**Output flags:**
- `--json` - Output as a JSON array with fields: `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`. When `--include-blocked` is also set, each row additionally carries `blocked` (bool), `blocked_by` (sorted list), and `pending_prerequisites` (sorted list of still-open soft `depends_on` targets, ENH-2635). As with `next-issue`, `blocked` reflects hard `blocked_by` edges only, so a row's state is **hard-blocked**, **soft-deferred** (non-empty `pending_prerequisites`), or **ready** (both empty).
- `--path` - Output one file path per line instead of IDs

**Filter flags:**
- `--include-blocked` (ENH-2436) - Re-include issues with unresolved blockers in the ranked list. Each JSON row carries `blocked`, `blocked_by`, and `pending_prerequisites` (open soft `depends_on` targets, ENH-2635) fields when set.

**Exit codes:** 0 when at least one unblocked issue is found; 1 when no active issues exist or when every active issue is currently blocked (the latter surfaces `Error: No ready issues (N blocked, 0 ready)` on stderr).

**Strategy**: Config-driven via `issues.next_issue.strategy` (default `confidence_first`). See [`NextIssueConfig`](#nextissueconfig) for available presets and custom sort keys.

**Sort key (default, `confidence_first`)**: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int` — byte-identical to the legacy hardcoded tuple.

**Configuration**: Switch strategies via `.ll/ll-config.json`:
```json
{
  "issues": {
    "next_issue": { "strategy": "priority_first" }
  }
}
```

**Examples:**
```bash
ll-issues next-issues                       # all unblocked issues ranked
ll-issues next-issues 5                     # top 5 unblocked
ll-issues nxs --json                        # unblocked list as JSON array
ll-issues nxs --path                        # unblocked list as file paths
ll-issues nxs --include-blocked --json      # JSON with blocked / blocked_by / pending_prerequisites
```

**FSM loop use**: Pair with `ll-issues next-issue` (singular) when you need only the top item; use `next-issues` when you want to seed a loop queue or inspect the full ranked backlog. Loops that need the legacy behavior (i.e. include blocked issues in the queue) should pass `--include-blocked`.

#### search

```
ll-issues search [QUERY] [OPTIONS]
```

Search across issues with rich filtering, sorting, and output options.

**Arguments:**
- `QUERY` - Optional text to match against title and body (case-insensitive substring)

**Filters:**
- `--type {BUG,FEAT,ENH,EPIC}` - Filter by issue type (repeatable)
- `--priority P` - Filter by priority P0–P5 or range e.g. `P0-P2` (repeatable)
- `--status {open,in_progress,blocked,deferred,done,cancelled,all}` - Filter by status (default: `open`)
- `--include-completed` - Include issues of all statuses (alias for `--status all`)
- `--label LABEL` - Filter by label tag in the `## Labels` section (repeatable)
- `--since DATE` - Only issues discovered on or after DATE (`YYYY-MM-DD`)
- `--until DATE` - Only issues discovered on or before DATE (`YYYY-MM-DD`)
- `--date-field {discovered,updated}` - Date field to filter on (default: `discovered`)

**Sorting:**
- `--sort {priority,id,date,type,title}` - Sort field (default: `priority`)
- `--asc` / `--desc` - Sort direction (default: asc except date which defaults to desc)

**Output:**
- `--json` - Output as JSON array with fields: `id`, `priority`, `type`, `title`, `path`, `status`, `discovered_date`
- `--format {table,list,ids}` - Output format (default: `table`)
- `--limit N` - Cap results at N

**Examples:**
```bash
ll-issues search                           # list all open issues
ll-issues search "caching" --status all
ll-issues search --type BUG --priority P0-P2
ll-issues search --since 2026-01-01 --sort date
ll-issues search --label api --json
ll-issues search --type BUG --format ids
```

#### show

```
ll-issues show <issue_id>
```

Display a formatted summary card for a single issue. Accepts three input formats:
- Numeric ID: `ll-issues show 518`
- Type + ID: `ll-issues show FEAT-518`
- Priority + Type + ID: `ll-issues show P3-FEAT-518`

Searches all type directories regardless of status. Displays a box-drawing character card with:
- **Metadata**: priority, status, effort, risk level
- **Scores**: confidence score, outcome confidence (when present in frontmatter)
- **Details**: summary text (word-wrapped to fit card width), source (`discovered_by` alias), norm (✓/✗ filename convention check), fmt (✓/✗ required sections check), integration file count, labels, session log history with command counts
- **Path**: relative path from project root

**`--json` output fields**: `issue_id`, `title`, `priority`, `status`, `effort`, `confidence`, `outcome`, `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`, `summary`, `integration_files`, `risk`, `labels`, `history`, `path`, `source`, `norm`, `fmt`. ENH-2535 added the following additive keys (all `str | None`; absent when the source issue lacks the field): `raw_status`, `decision_ref`, `closing_note`, `closed_reason`, `cancelled_reason`, `deferred_reason`, `closed_by`, `closed_at`, `deferred_date`, `closure_text`, `discovered_date`, `discovered_commit`, `discovered_branch`, `discovered_source`, `discovered_external_repo`, `parent`, `parent_display`, `relates_to`, `depends_on`, `blocked_by`, `blocks`, `supersedes`, `decomposed_into`, `affects`, `focus_area`, `testable`.

### main_history

```python
def main_history() -> int
```

Entry point for `ll-history` command. Display summary statistics, analysis, and synthesized documentation for completed issues.

**Returns:** Exit code

**Sub-commands:**

| Sub-command | Description |
|-------------|-------------|
| `summary` | Show issue statistics (count, velocity, type/priority breakdown) |
| `analyze` | Full analysis with trends, subsystems, and debt metrics |
| `export` | Export topic-filtered excerpts from completed issue history |

**Global options (all sub-commands):**
- `--intent QUERY` - Intent query for output filtering (no-op until FTS5 ranking lands; ENH-1114)
- `--intent-limit N` - Max lines for intent-filtered output (default: `50`)

#### export

```
ll-history export <topic> [options]
```

Exports a markdown document from completed issues matching a topic.

**Arguments:**
- `topic` - Topic, area, or system to generate documentation for

**Options:**
- `--output PATH` - Write output to file instead of stdout
- `-f, --format {narrative,structured}` - Output format (default: `narrative`)
- `-d, --directory PATH` - Path to issues directory (default: `.issues`)
- `--since DATE` - Only include issues completed after DATE (YYYY-MM-DD)
- `--min-relevance FLOAT` - Minimum relevance score threshold (default: `0.5`)
- `--type {BUG,FEAT,ENH,EPIC}` - Filter by issue type
- `--scoring {intersection,bm25,hybrid}` - Relevance scoring method (default: `intersection`)

**Scoring modes:**
- `intersection` (default): fraction of topic words appearing in the issue — best recall, no corpus needed
- `hybrid`: `intersection * 0.5 + normalized_bm25 * 0.5` — blends recall and ranking precision
- `bm25`: normalized BM25 score only — ranks by term frequency and IDF weighting

**Example:**
```bash
# Default intersection scoring
ll-history export "session logging" --output docs/arch/session.md

# Hybrid scoring for better ranking among many results
ll-history export "sprint CLI" --scoring hybrid --min-relevance 0.3

# BM25-only for precision-focused ranking
ll-history export "dependency resolution" --scoring bm25 --format structured
```

### main_messages

```python
def main_messages() -> int
```

Entry point for `ll-messages` command. Extract user messages from Claude Code logs.

**Returns:** Exit code

**CLI Arguments:**
- `-n, --limit` - Maximum messages to extract (default: 100)
- `--since` - Only messages after date (YYYY-MM-DD or ISO format)
- `-o, --output` - Output file path
- `--cwd` - Working directory to use
- `--exclude-agents` - Exclude agent session files
- `--stdout` - Print to stdout instead of file
- `-v, --verbose` - Verbose progress output
- `--skill` - Filter to sessions where this skill was invoked
- `--examples-format` - Output (input, output) training pairs (requires `--skill`); mutually exclusive with `--sft-format`
- `--sft-format` - Output conversation turns in SFT training format (`chatml`/`alpaca`/`sharegpt`); mutually exclusive with `--examples-format`
- `--context-window` - Number of context turn-pairs per window in `--examples-format` or `--sft-format` (default: 3)

### main_sprint

```python
def main_sprint() -> int
```

Entry point for `ll-sprint` command. Define and execute curated issue sets with dependency-aware wave ordering.

**Returns:** Exit code

**Sub-commands:** `create`, `edit`, `list`, `show`, `delete`, `run`, `resume`, `status`

### main_parallel

```python
def main_parallel() -> int
```

Entry point for `ll-parallel` command. Process issues concurrently using isolated git worktrees.

**Returns:** Exit code

**CLI Arguments:**
- `--workers` - Number of parallel workers (short: `-w`)
- `--timeout` - Per-issue timeout in seconds
- `--only` - Comma-separated issue IDs to process exclusively

### main_sync

```python
def main_sync() -> int
```

Entry point for `ll-sync` command. Sync local issues with GitHub Issues (bidirectional push/pull).

**Returns:** Exit code

**Sub-commands:** `push`, `pull`, `status`, `reset`

### main_deps

```python
def main_deps() -> int
```

Entry point for `ll-deps` command. Cross-issue dependency analysis and validation.

**Returns:** Exit code

**Global options:**
- `--intent QUERY` - Intent query for output filtering (no-op until FTS5 ranking lands; ENH-1114)
- `--intent-limit N` - Max lines for intent-filtered output (default: `50`)

**Sub-commands:** `analyze`, `validate`, `fix`, `apply`, `tree`

### main_verify_docs

```python
def main_verify_docs() -> int
```

Entry point for `ll-verify-docs` command. Verify that documented counts match actual file counts in the project.

### main_verify_des_audit

```python
def main_verify_des_audit() -> int
```

Entry point for `ll-verify-des-audit` command (ENH-2475). Walk the source tree, classify every event-emit site against the canonical `DES_VARIANTS` registry, and exit 0 iff every currently-emitted event has a registered variant — the F5 adoption gate (EPIC-2456 § Tier 1).

**Returns:** Exit code

### main_check_links

```python
def main_check_links() -> int
```

Entry point for `ll-check-links` command. Check markdown documentation for broken links.

**Returns:** Exit code

---

### main_logs

```python
def main_logs() -> int
```

Entry point for `ll-logs` command. Discover, extract, sequence, and tail Claude Code session logs for ll-loop and ll-commands.

**Returns:** 0 on success, 1 when no subcommand given or on error

**Subcommands:**
- `discover` — List all Claude projects with ll activity (no flags)
- `extract` — Extract ll-relevant JSONL records to `logs/<slug>/<session-id>.jsonl`; requires `--project DIR` or `--all`; optional `--cmd TOOL` to filter by CLI tool
- `sequences` — Extract tool-chain n-grams of ll invocations from JSONL logs; requires `--project DIR` or `--all`; options: `--min-len N` (default 2), `--min-count M` (default 1), `--top N`, `--window-days D`, `--json`; JSON schema: `[{chain: [str], count: int, edges: [{from, to, freq, pmi?, lift?}], pmi?: float, lift?: float}]`; `pmi` and `lift` are additive optional fields (present when the corpus has sufficient unigram data); `lift < 1.0` means the pair co-occurs at or below the frequency-prior baseline (frequency-prior-equivalent)
- `stats` — Aggregate per-skill invocation frequency and correction rate from `skill_events` in `.ll/history.db`; requires `--project DIR` or `--all`; options: `--window-days D`, `--sort {freq,corrections}` (default freq), `--json`; JSON schema: `[{skill: str, invocations: int, corrections: int, correction_rate: float}]`
- `dead-skills` — Cross-reference skill catalog against log corpus to flag never/rarely-invoked skills; requires `--project DIR` or `--all`; options: `--window-days D`, `--threshold N` (default 3), `--json`; JSON schema: `[{skill: str, invocations: int, tier: "never"|"rarely"}]`; excludes bridge skills and `disable-model-invocation: true` entries
- `scan-failures` — Mine failed `ll-*` Bash calls from interactive session JSONL logs; requires `--project DIR` or `--all`; options: `--window-days D`, `--json`, `--capture`; clusters failures by `(tool, normalized-error-signature)`, suppresses transient errors and `ll-verify-*` expected-nonzero gates; JSON schema: `[{tool: str, count: int, normalized_sig: str, sample_error: str, session_ids: [str]}]`; `--capture` creates a BUG issue file per cluster via `create_issue_from_failure()`
- `loop-fleet` — Aggregate cross-project loop-run outcomes from `.loops/.history/*/events.jsonl` for built-in loop improvement; requires `--project DIR` or `--all`; options: `--loop NAME` (filter to one loop), `--window-days D`, `--existing-only` (skip dead worktrees; meaningful with `--all`), `--json`; reads the `loop_complete` terminal event from each archived run dir, derives outcome (`converged`/`failed`/`max-steps`/`stalled`/`interrupted`/`error`), and attributes each loop as `builtin` (name matches a shipped `little_loops/loops/**/*.yaml`) or `custom`; default output: per-loop table (Loop, Type, Runs, Success%, Med-Iter, Top Outcome, Projects); JSON schema (one record per run, sorted newest-first): `[{loop_name: str, project: str, run_folder: str, final_state: str, iterations: int, outcome: str, ts: str, attribution: "builtin"|"custom"}]`; complements `scan-failures` (session-layer) with FSM-run-layer diagnostics; use `-j` output as input to `ll-loop validate`/`diagnose-evaluators`/`loop-specialist`
- `diff` — Compare two sessions' ll-invocation behavior; positional args: `SESSION_A SESSION_B` (session ID or JSONL path); option: `--json`; reports added/removed skills, invocation count deltas, and unified sequence diff; JSON schema: `{session_a: str, session_b: str, skills_added: [str], skills_removed: [str], count_deltas: {skill: {a: int, b: int, delta: int}}, sequence_diff: [str]}`; resolves session IDs via `sessions` table in `.ll/history.db`
- `eval-export` — Reconstruct `ll-harness` eval fixtures (EvalFixture v1) from session logs; optional `--project DIR` (default: cwd), `--skill NAME`, `--issue ID`, `--limit N` (0 = unlimited), `--out PATH` (default: stdout), `--json` (default: YAML). Walks the project's JSONL via the ENH-1919 invocation extractor, sources an **execution** outcome (`accepted`/`corrected`/`failed`; `unknown` records are skipped with a logged count) from `history_reader.lookup_session_metadata()`, and best-effort-redacts `input_context` (PII + absolute paths, flagged by `pii_detected`). ll-harness has **no fixture loader** — a fixture replays by serializing its fields into `ll-harness <runner> <target> [runner_args...] [--exit-code N] [--semantic TEXT] [--timeout S]`. Fixture fields: `runner` (skill|cmd), `target`, `session_id`, `timestamp`, `outcome`, `runner_args`, `exit_code`, `semantic`, `timeout`, `input_context`, `issue_id`, `skill_name`, `pii_detected`. Schema + outcome taxonomy fixed by decision ARCHITECTURE-017 in `.ll/decisions.yaml` (FEAT-1968). Example record:
  ```yaml
  - runner: skill
    target: refine-issue
    session_id: 9c1f-...
    timestamp: '2026-06-06T00:00:00Z'
    outcome: accepted
    runner_args: []
    exit_code: null
    semantic: null
    timeout: 120
    input_context: refine FEAT-1971 in the backlog
    issue_id: FEAT-1971
    skill_name: refine-issue
    pii_detected: false
  ```
- `tail` — Stream live events from an active loop session; requires `--loop NAME`; optional `--project DIR`

---

### main_session

```python
def main_session() -> int
```

Entry point for `ll-session` command. Query the unified session store (SQLite + FTS5) — the per-project `.ll/history.db`.

**Returns:** 0 on success, 1 when no subcommand given or on error

**Global flags:**
- `--db PATH` — Path to the session database (default: `.ll/history.db`)

**Subcommands:**
- `search` — FTS5 full-text query with BM25-ranked results; requires `--fts QUERY`, optional `--kind` (choices come from `VALID_KINDS`: `tool,file,issue,loop,correction,message,skill,cli,snapshot,commit,test_run,usage,orchestration_run,loop_run,learning_test,session_lifecycle`), `--limit N` (default 20), `--json`
- `recent` — Most recent rows for an event kind; requires `--kind` (same `VALID_KINDS` choices as `search`, or `--issue ID` to list sessions for an issue); optional `--limit N` (default 20), `--json`
- `backfill` — Ingest on-disk sources; issue/loop-state/commit data is written directly, session JSONL lines go into `raw_events` only (ENH-2581). `--rebuild` also materializes the JSONL-derived cache tables in the same call (equivalent to a following `rebuild`). `--since DATE` (ISO 8601 or YYYY-MM-DD) uses incremental JSONL-only mode via `backfill_incremental()` (ENH-1830). `--host {claude-code,codex,opencode,pi}` selects the host for session log discovery (default: auto-detect from ``LL_HOOK_HOST`` env var); full backfill (no ``--since``) also uses ``--host`` for JSONL file discovery (ENH-1945). `--extract-decisions` runs decision mining after backfill (ENH-2152). `--snapshots` hydrates the `issue_snapshots` table from existing `.issues/` files (ENH-2151)
- `rebuild` — Wipe+re-derive the JSONL-derived cache tables (and their `search_index` rows) from `raw_events`; optional `--config PATH`, `--json` (ENH-2581)
- `compact` — Sweep `raw_events` rows past the retention cutoff into per-session `kind='retention'` summary nodes, marking them `compacted=1`; optional `--and-prune` (also runs `prune` afterward), `--config PATH`, `--json` (ENH-2581)
- `related` — Issue events for a given issue ID; requires `ISSUE_ID` positional arg, optional `--limit N` and `--json`
- `path` — Resolve and print the JSONL file path for a session ID; exits non-zero if unknown
- `grep` — Regex search over `message_events` with optional summary-node context; requires `PATTERN`, optional `--summary-id ID`, `--limit N` (default 50), `--json`
- `expand` — Return `message_events` covered by a summary node; requires `SUMMARY_ID`, optional `--json`
- `describe` — Show metadata for a summary node; requires `NODE_ID`, optional `--json`
- `prune` — Delete `raw_events` rows already marked `compacted=1` past the configured max-age, then VACUUM the database; optional `--dry-run`, `--json` (ENH-2581 — previously deleted directly from `tool_events`/`cli_events`/`file_events`/`message_events`)

---

### main_queue

```python
def main_queue() -> int
```

Entry point for `ll-queue` command (FEAT-2682). Persisted work-item queue backed by `.ll/queue.db` (`little_loops.queue_store`) — distinct from `ll-loop queue`'s PID-liveness marker mechanism.

**Returns:** 0 on success, 1 on not-found/ambiguous id, 2 on a malformed `--arg`

**Subcommands:**
- `add TARGET` — Classify and persist a new entry. Without `--runner`, `TARGET` is classified in order: an FSM loop name (resolves via `resolve_loop_path`), a skill/command name (resolves via `skills/<name>/SKILL.md` / `commands/<name>.md`), else a raw CLI invocation. Optional `--priority {P0..P5}` (default `P3`), `--runner {skill,cmd,mcp,prompt,loop}` (skip classification), `--arg KEY=VALUE` (repeatable), `--timeout N` (default 120), `--json`
- `list` — List all entries ordered by priority tier then FIFO within tier; optional `--json`
- `status ID` — Show one entry by full id or 8+-char prefix; optional `--json`
- `remove ID` — Delete a `pending` entry by full id or 8+-char prefix; `--force` removes a non-pending entry too; optional `--json`

---

### main_history_context

```python
def main_history_context() -> int
```

Entry point for `ll-history-context` command. Query `.ll/history.db` for user corrections and FTS5 matches related to an issue ID and render a `## Historical Context` markdown block.

**Returns:** 0 on success (including empty output when no matches or DB absent), 1 on argument error

**Flags:**
- `ISSUE_ID` — Issue ID to query (required positional argument)
- `--file PATH` — Also include recent file events for this path (optional)
- `--db PATH` — Path to the session database (default: `.ll/history.db`)
- `--effort` — Output a `## Effort Context` block with per-issue session count and cycle time (ENH-1905)
- `--for-skill NAME` — Exit 0 with no output if NAME is not in `history.planning_skills` (ENH-1909)

**Behavior:**
- Calls `find_user_corrections(topic=issue_id)` and `search(query=issue_id, kind="correction")` with deduplication
- Post-filters `search()` results by staleness (no built-in stale filter in `search()`)
- Optionally calls `recent_file_events(path=file)` when `--file` is given
- Caps output at 5 rows
- Returns empty output when DB is missing, no matches, or all rows stale

---

### main_learning_tests

```python
def main_learning_tests() -> int
```

Entry point for `ll-learning-tests` command. Query and manage the learning test registry.

**Returns:** 0 on success, 1 when target not found

**Subcommands:**
- `check <target>` — Print record JSON to stdout; exit 1 if not found
- `list` — Print all records as a JSON array
- `mark-stale <target>` — Set status=stale on a record; exit 1 if not found

---

### main_ctx_stats

```python
def main_ctx_stats() -> int
```

Entry point for `ll-ctx-stats` command. Show context-window analytics for the current project (FEAT-1160). Reads per-tool byte metrics that the `post_tool_use` hook persists into `.ll/history.db` (FEAT-1623) and renders a compact summary of how much data was processed by tools vs. how much actually entered the conversation context. Also aggregates skill-health signals (per-skill invocation frequency and correction rate) via `_aggregate_skill_stats()` from the same `.ll/history.db` (ENH-1921); when skill events are present a "Skill health" section is appended to the human-readable report and a `skill_health` array is included in `--json` output. Falls back to `.ll/ll-context-state.json` (token estimates) when the SQLite store is absent.

**Returns:** 0 when a report was rendered (data present or fallback used), 1 when no data found in either the SQLite store or the fallback file.

**Flags:**
- `--db PATH` — Use a non-default session database (default `.ll/history.db`)
- `--json` — Emit the report as JSON instead of the human-readable summary; includes `skill_health: [{skill, invocations, corrections, correction_rate}]` or `null`

Enable per-tool byte tracking by setting `"analytics": {"enabled": true}` in `.ll/ll-config.json`. The `post_tool_use` hook reads this gate and no-ops when disabled or absent. Use `analytics.capture` for per-category control (e.g. `analytics.capture.file_events: false` disables file-event recording while keeping tool-event metrics active). See [CONFIGURATION.md § analytics.capture](CONFIGURATION.md#analyticscapture) for the full key reference.

---

### main_config

```python
def main_config() -> int
```

Entry point for `ll-config` command. Resolve and print a single dot-path configuration value via `BRConfig.resolve_variable()`. This is the CLI a markdown skill shells out to when it needs a resolved config value at runtime — the `{{config.path.to.value}}` template token syntax only expands under `ll-auto`'s `skill_expander.py` pre-expansion pass, so interactive/slash-command skill runs never see it substituted (ENH-2678).

**Returns:** 0 always — mirrors `resolve_variable()`'s never-raise, config-or-default contract.

**Subcommands:**
- `get <key>` — Print the resolved value for a dot-separated config path (e.g. `history.go_no_go.correction_penalty`); prints nothing for unknown keys.

---

## little_loops.workflow_sequence

Step 2 of a 3-step workflow analysis pipeline. Analyzes user message patterns to identify multi-step workflows, link related sessions, and detect workflow boundaries.

> **Note**: Previously exposed as `little_loops.workflow_sequence_analyzer` (monolithic module). Refactored in ENH-840 into a sub-package at `little_loops/workflow_sequence/`. The public API is unchanged — import from `little_loops.workflow_sequence`.

### Quick Example

```python
from pathlib import Path
from little_loops.workflow_sequence import analyze_workflows

# Analyze messages from Step 1 output
result = analyze_workflows(
    messages_file=Path(".ll/user-messages.jsonl"),
    patterns_file=Path(".ll/workflow-analysis/step1-patterns.yaml"),
    output_file=Path(".ll/workflow-analysis/step2-workflows.yaml"),
)

print(f"Found {len(result.workflows)} workflows")
print(f"Linked {len(result.session_links)} sessions")
```

### SessionLink

Represents a link between related sessions.

```python
@dataclass
class SessionLink:
    link_id: str                    # Unique identifier for the link
    sessions: list[dict[str, Any]]  # Session data with positions
    unified_workflow: dict[str, Any]  # Combined workflow metadata
    confidence: float               # Link confidence score (0.0-1.0)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### EntityCluster

Represents a group of messages sharing common entities.

```python
@dataclass
class EntityCluster:
    cluster_id: str                 # Unique identifier for the cluster
    primary_entities: list[str]     # Top 3 most common entities
    all_entities: set[str]          # All entities in the cluster
    messages: list[str]             # Message UUIDs in this cluster
    span: dict[str, str]            # Time span (first, last timestamps)
    inferred_workflow: str          # Inferred workflow type
    cohesion_score: float           # Cluster cohesion (0.0-1.0)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### WorkflowBoundary

Represents a potential boundary between workflows.

```python
@dataclass
class WorkflowBoundary:
    msg_a: str                      # UUID of first message
    msg_b: str                      # UUID of second message
    time_gap_seconds: float         # Time between messages
    time_gap_weight: float          # Boundary weight from time gap (0.0-1.0)
    entity_overlap: float           # Jaccard similarity of entities (0.0-1.0)
    final_boundary_score: float     # Combined boundary score
    is_boundary: bool               # True if score >= threshold
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### Workflow

Represents a detected multi-step workflow.

```python
@dataclass
class Workflow:
    workflow_id: str                # Unique identifier
    name: str                       # Human-readable name
    pattern: str                    # Template pattern matched
    pattern_confidence: float       # Match confidence (0.0-1.0)
    messages: list[str]             # Message UUIDs in workflow
    session_span: dict[str, str]    # Time span (first, last)
    entity_cluster: str | None      # Related entity cluster ID
    semantic_cluster: str | None    # Related semantic cluster ID
    duration_minutes: float         # Workflow duration
    handoff_points: list[str]       # Detected handoff message UUIDs
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### WorkflowAnalysis

Complete output container for all analysis results.

```python
@dataclass
class WorkflowAnalysis:
    metadata: dict[str, Any]                # Analysis metadata
    session_links: list[SessionLink]        # Linked sessions
    entity_clusters: list[EntityCluster]    # Entity-based clusters
    workflow_boundaries: list[WorkflowBoundary]  # Detected boundaries
    workflows: list[Workflow]               # Detected workflows
    handoff_analysis: dict[str, Any]        # Handoff statistics
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### analyze_workflows

```python
def analyze_workflows(
    messages_file: Path,
    patterns_file: Path,
    output_file: Path | None = None,
) -> WorkflowAnalysis
```

Main entry point for workflow sequence analysis (Step 2 of pipeline).

**Parameters:**
- `messages_file` - Path to JSONL file with user messages
- `patterns_file` - Path to YAML file from Step 1 (pattern analysis)
- `output_file` - Optional output path for YAML results

**Returns:** `WorkflowAnalysis` with all analysis results

**Example:**
```python
from pathlib import Path
from little_loops.workflow_sequence import analyze_workflows

result = analyze_workflows(
    messages_file=Path(".ll/user-messages.jsonl"),
    patterns_file=Path(".ll/workflow-analysis/step1-patterns.yaml"),
)

for workflow in result.workflows:
    print(f"{workflow.name}: {len(workflow.messages)} messages")
    print(f"  Pattern: {workflow.pattern}")
    print(f"  Duration: {workflow.duration_minutes:.1f} min")
```

### Helper Functions

#### extract_entities

```python
def extract_entities(content: str) -> set[str]
```

Extract entities from message content using regex patterns.

**Parameters:**
- `content` - Message text to analyze

**Returns:** Set of extracted entities (file paths, issue IDs, commands, etc.)

**Example:**
```python
from little_loops.workflow_sequence import extract_entities

entities = extract_entities("Fix BUG-123 in src/utils.py using /ll:manage-issue")
# Returns: {"BUG-123", "src/utils.py", "/ll:manage-issue"}
```

#### calculate_boundary_weight

```python
def calculate_boundary_weight(gap_seconds: int) -> float
```

Map time gaps to boundary weights using tiered thresholds.

**Parameters:**
- `time_gap_seconds` - Time gap between messages in seconds

**Returns:** Weight from 0.0 (same task) to 0.95 (likely different workflow)

**Thresholds:**
- < 30s → 0.0 (same task)
- 30s-2min → 0.1
- 2-5min → 0.3
- 5-15min → 0.5
- 15-30min → 0.7
- 30min-2h → 0.85
- > 2h → 0.95 (likely different workflow)

#### entity_overlap

```python
def entity_overlap(entities_a: set[str], entities_b: set[str]) -> float
```

Calculate Jaccard similarity between two entity sets.

**Parameters:**
- `entities_a` - First entity set
- `entities_b` - Second entity set

**Returns:** Jaccard coefficient (0.0-1.0), or 0.0 if either set is empty

#### get_verb_class

```python
def get_verb_class(content: str) -> str | None
```

Extract verb class from message content.

**Parameters:**
- `content` - Message text to analyze

**Returns:** Verb class name or `None` if no match

**Classes:** `deletion`, `modification`, `creation`, `search`, `verification`, `execution`

#### semantic_similarity

```python
def semantic_similarity(
    msg_a: dict[str, Any],
    msg_b: dict[str, Any],
    patterns: dict[str, Any],
) -> float
```

Calculate weighted similarity between two messages.

**Parameters:**
- `msg_a` - First message dict
- `msg_b` - Second message dict
- `patterns` - Step 1 patterns data for category lookup

**Returns:** Similarity score (0.0-1.0)

**Weights:**
- Keyword overlap: 0.3
- Verb class match: 0.3
- Entity overlap: 0.3
- Category match: 0.1

### Constants

#### VERB_CLASSES

```python
VERB_CLASSES: dict[str, set[str]]
```

Mapping of verb class names to sets of related verbs:
- `deletion` - delete, remove, drop, etc.
- `modification` - update, modify, change, etc.
- `creation` - create, add, new, etc.
- `search` - find, search, look, etc.
- `verification` - test, verify, check, etc.
- `execution` - run, execute, build, etc.

#### WORKFLOW_TEMPLATES

```python
WORKFLOW_TEMPLATES: dict[str, list[str]]
```

Mapping of workflow pattern names to category sequences:
- `explore -> modify -> verify`
- `create -> refine -> finalize`
- `search -> analyze -> implement`

---

## Import Shortcuts

```python
# Main package imports
from little_loops.config import BRConfig
from little_loops.issue_parser import IssueParser, IssueInfo, find_issues
from little_loops.issue_manager import AutoManager
from little_loops.git_operations import (
    GitignorePattern,
    GitignoreSuggestion,
    suggest_gitignore_patterns,
    add_patterns_to_gitignore,
    get_untracked_files,
    check_git_status,
)
from little_loops.work_verification import verify_work_was_done, filter_excluded_files
from little_loops.state import StateManager, ProcessingState
from little_loops.logger import Logger, format_duration
from little_loops.user_messages import (
    UserMessage,
    get_project_folder,
    extract_user_messages,
    save_messages,
)

# Workflow analysis
from little_loops.workflow_sequence import (
    analyze_workflows,
    SessionLink,
    EntityCluster,
    WorkflowBoundary,
    Workflow,
    WorkflowAnalysis,
    extract_entities,
    calculate_boundary_weight,
    entity_overlap,
    get_verb_class,
    semantic_similarity,
)

# Parallel subpackage
from little_loops.parallel import (
    ParallelOrchestrator,
    WorkerPool,
    MergeCoordinator,
    ParallelConfig,
    WorkerResult,
)
from little_loops.parallel.priority_queue import IssuePriorityQueue
from little_loops.parallel.types import QueuedIssue, MergeRequest, MergeStatus
from little_loops.output_parsing import parse_ready_issue_output
```

---

## Usage Examples

### Basic Configuration Loading

```python
from pathlib import Path
from little_loops.config import BRConfig

# Load config from current directory
config = BRConfig(Path.cwd())

# Access settings
print(f"Project: {config.project.name}")
print(f"Source dir: {config.project.src_dir}")
print(f"Test command: {config.project.test_cmd}")

# Get issue directories
bugs_dir = config.get_issue_dir("bugs")
```

### Finding and Parsing Issues

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.issue_parser import find_issues, find_highest_priority_issue

config = BRConfig(Path.cwd())

# Find all issues
all_issues = find_issues(config)
print(f"Found {len(all_issues)} issues")

# Find only bugs
bugs = find_issues(config, category="bugs")

# Find highest priority issue
next_issue = find_highest_priority_issue(config)
if next_issue:
    print(f"Next: {next_issue.issue_id} ({next_issue.priority})")
```

### Running Sequential Automation

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager

config = BRConfig(Path.cwd())
manager = AutoManager(
    config=config,
    max_issues=3,
    dry_run=True,  # Preview only
)
exit_code = manager.run()
```

### Running Parallel Automation

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.parallel import ParallelOrchestrator

br_config = BRConfig(Path.cwd())
parallel_config = br_config.create_parallel_config(
    max_workers=2,
    max_issues=5,
)

orchestrator = ParallelOrchestrator(
    parallel_config=parallel_config,
    br_config=br_config,
)
exit_code = orchestrator.run()
```

---

## little_loops.observability

DES (discriminated-union) variant registry for every event shape currently emitted to `.ll/history.db` (ENH-2475). The registry enumerates the full event surface so F5 (`observability/tracing.py`, EPIC-2456 § Tier 1) can adopt a canonical emit schema without runtime shape-coercion.

### little_loops.observability.schema

```python
from little_loops.observability.schema import DESVariant, DES_VARIANTS, DES_VARIANT_TYPES
```

Frozen dataclasses (per `little_loops.host_runner` value-object convention) keyed by a `type: Literal[...]` discriminator. Every variant matches a wire-format event type currently emitted from `scripts/little_loops/`:

| Export | Description |
|--------|-------------|
| `DESVariant` | Base frozen dataclass for every registered variant |
| `DES_VARIANTS` | `Final[Tuple[Type[DESVariant], ...]]` — every registered variant class |
| `DES_VARIANT_TYPES` | `Final[frozenset[str]]` — every discriminator string (the audit walker's allow-list) |

Each concrete variant subclasses `DESVariant` and declares its discriminator via `type: Literal["exact_string"] = "exact_string"`. Example:

```python
@dataclass(frozen=True)
class LoopStartVariant(DESVariant):
    """FSMExecutor._emit('loop_start') — FSM loop begins execution."""
    type: Literal["loop_start"] = "loop_start"
    loop: str = ""
```

### little_loops.observability.audit

```python
from little_loops.observability.audit import audit_tree, AuditResult
```

Static walker that classifies every emit site in a source tree against `DES_VARIANT_TYPES`. Two-phase detection (regex for positional string literals, AST for `event=...` keyword args) covers both `_emit("type", {...})` and `event_bus.emit({..., "event": "type", ...})` patterns.

```python
result = audit_tree(Path("scripts/little_loops"))
if not result.passed:
    for etype in result.uncovered_event_types:
        print(f"Uncovered event type: {etype}")
```

### little_loops.observability.tracing

```python
from little_loops.observability import (
    OTelAttributes, StampUsageEvent, StreamingParityChecker, vendor_for_runner,
)
```

OTel `gen_ai.*` attribute shaping + streaming-parity primitives (FEAT-2478). Emits
OpenTelemetry-semantic-convention-shaped attributes from internal token-usage rows
**without** an OTel SDK in-process. See
[docs/observability/otel-mapping.md](../observability/otel-mapping.md) for the full
internal-name ↔ OTel-canonical map.

- `OTelAttributes.from_usage(usage, vendor=None, invocation_id=None) -> dict` —
  shape a `TokenUsage` (or flat dict) into the canonical **dotted** `gen_ai.usage.*`
  attribute dict (`gen_ai.usage.cache_read.input_tokens`, not the underscore form).
- `StampUsageEvent.usage_event(row, vendor=None, invocation_id=None) -> dict` —
  non-destructively augment a flat usage row with `gen_ai.*` keys.
- `StreamingParityChecker(threshold=0.001).diff(blocking, streaming)` /
  `.within_threshold(...)` — gate the ENH-2479 0.1% cache-token parity threshold
  across all four token fields.
- `vendor_for_runner(name) -> str` — map a `HostRunner.name` to the
  `gen_ai.provider.vendor` addendum (`anthropic` / `openai` / `google` / `other`).

```python
attrs = OTelAttributes.from_usage(usage, vendor="anthropic", invocation_id=str(uuid4()))
# {"gen_ai.usage.input_tokens": ..., "gen_ai.usage.cache_read.input_tokens": ..., ...}
```

---

## little_loops.fsm

FSM (Finite State Machine) loop system for automation workflows. This subpackage provides the schema, compilation, evaluation, and execution engine for declarative automation loops.

### Submodule Overview

| Module | Purpose |
|--------|---------|
| `little_loops.fsm.schema` | FSM state machine schema definitions |
| `little_loops.fsm.evaluators` | Verdict evaluators (exit_code, llm_structured, etc.) |
| `little_loops.fsm.executor` | FSM execution engine |
| `little_loops.fsm.runners` | Action runner protocol and default/simulation implementations |
| `little_loops.fsm.types` | Core result types (`ExecutionResult`, `ActionResult`) |
| `little_loops.fsm.interpolation` | Variable substitution (`${context.*}`, etc.) |
| `little_loops.fsm.validation` | Schema validation utilities |
| `little_loops.fsm.persistence` | Loop state persistence |
| `little_loops.fsm.handoff_handler` | Context handoff signal handling |
| `little_loops.fsm.concurrency` | Scope-based lock management for concurrent loops |
| `little_loops.fsm.rate_limit_circuit` | Shared circuit-breaker state file for cross-worktree 429 coordination |
| `little_loops.fsm.signal_detector` | Pattern-based signal detection in action output |
| `little_loops.fsm.host_guard` | Adaptive host memory-pressure guard: `HostGuardConfig`, `HostGuard`, `RssSampler`, memory probes (ENH-2452/ENH-2453) |
| `little_loops.fsm.stall_detector` | `StallDetector` and `Stall` dataclass for circuit-breaker stall detection |
| `little_loops.fsm.fragments` | Fragment composition: `resolve_fragments()`, `resolve_inheritance()`, `resolve_flow()` |
| `little_loops.fsm.policy_rules` | Shared policy-rule grammar for decision-table routing: `parse_rules()`, `serialize_rules()`, `evaluate_rules()`, `Rule`, `Predicate` dataclasses. Single source of truth used by both `lib/policy-router.yaml` and `edit-routes` compound mode (ENH-2164) |
| `little_loops.fsm.route_table` | Route-table extraction, rendering, parsing, and application for `ll-loop edit-routes`. Includes standard matrix classes (`RouteTableExtractor`, `RouteTableRenderer`, `RouteTableParser`, `RouteTableApplier`) and compound decision-table classes added in ENH-2233 (`PolicyRuleExtractor`, `CompoundGridRenderer`, `CompoundGridParser`, `PolicyRuleApplier`) |

### Quick Import

```python
from little_loops.fsm import (
    # Schema
    FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig,
    TargetFileSpec, TargetStateSpec,
    # Validation
    ValidationError, validate_fsm, load_and_validate,
    # Interpolation
    InterpolationContext, InterpolationError, interpolate, interpolate_dict,
    # Evaluation
    EvaluationResult, evaluate, evaluate_exit_code, evaluate_output_numeric,
    evaluate_output_json, evaluate_output_contains, evaluate_convergence,
    evaluate_llm_structured,
    # Execution
    FSMExecutor, ExecutionResult, ActionResult, ActionRunner,
    # Persistence
    LoopState, StatePersistence, PersistentExecutor,
    list_running_loops, get_loop_history,
    # Rate Limiting
    RateLimitCircuit,
)
```

---

### little_loops.fsm.schema

Schema dataclasses for FSM loop definitions.

#### FSMLoop

Complete FSM loop definition.

```python
@dataclass
class FSMLoop:
    name: str                          # Unique loop identifier
    initial: str                       # Starting state name
    states: dict[str, StateConfig]     # State configurations
    description: str | None = None     # Free-text summary surfaced by `ll-loop list` and `--explain`
    context: dict[str, Any] = {}       # User-defined shared variables
    parameters: dict[str, ParameterSpec] = {}  # Declared loop inputs (validated at --from-yaml / --input)
    scope: list[str] = []              # Paths for concurrency control
    max_steps: int = 50                # Step cap (individual state executions)
    on_max_steps: str | None = None    # State to run once when step cap fires (ENH-1631)
    max_iterations: int | None = None  # Full-pass cap (maintain-mode restarts); None = no cap
    on_max_iterations: str | None = None  # State to run once when full-pass cap fires
    max_edge_revisits: int = 100       # Per-edge cycle detection limit (see below)
    backoff: float | None = None       # Seconds between iterations
    timeout: int | None = None         # Max runtime in seconds
    default_timeout: int | None = None # Per-action default when state.timeout is unset
    maintain: bool = False             # If True, restart after completion
    singleton: bool = False            # BUG-2526: serialize loop-name conflicts regardless of scope
    llm: LLMConfig = LLMConfig()       # LLM evaluation settings
    on_handoff: Literal["pause", "spawn", "terminate"] = "pause"  # ContextLimitHandoff handler
    input_key: str = "input"           # Context var that contains the initial input
    config: LoopConfigOverrides | None = None  # Per-loop ll-config.json overrides
    category: str = ""                 # Topical grouping for `ll-loop list` filtering (orthogonal to visibility)
    labels: list[str] = []             # Free-form tags surfaced by `ll-loop list --labels k=v`
    visibility: str = "public"         # Audience tier: "public" (user-facing), "internal" (sub-loop only), or "example" (template)
    required_inputs: list[str] = []    # Names of context vars that must be populated before invocation
    commands: list[CommandEntry] = []  # Optional Commands section override for ll-loop show
    targets: list[TargetFileSpec] = []  # Per-FSM-state targeting spec for harness-optimize APO (ENH-1552)
    circuit: CircuitConfig | None = None  # Top-level safety knobs; currently the stall detector (FEAT-1637)
    host_guard: HostGuardConfig = HostGuardConfig()  # ENH-2452 (memory pressure) + ENH-2453 (subprocess RSS budget)
    prompt_size_guard: PromptSizeGuardConfig = PromptSizeGuardConfig()  # ENH-2486 interpolated-prompt size guard (WARN-only)
    meta_self_eval_ok: bool = False       # Suppress MR-1/MR-2 meta-loop lint rules (ENH-1665)
    shared_state_ok: bool = False         # Suppress MR-3 artifact-isolation lint rule
    partial_route_ok: bool = False        # Suppress MR-4 partial-route dead-end lint rule (ENH-1917)
    artifact_versioning: bool = False     # Declare that this loop versions artifacts per-iteration (satisfies MR-5)
    artifact_versioning_ok: bool = False  # Suppress MR-5 artifact-versioning lint rule (ENH-1957)
    generator_fix_ok: bool = False        # Suppress MR-6 generator-fix discipline lint rule (ENH-2079)
    bash_default_ok: bool = False         # Suppress MR-7 bash-default interpolation lint rule (ENH-2348)
    evidence_contract_ok: bool = False    # Suppress MR-8 evidence-contract lint rule (ENH-2342)
    shell_pid_ok: bool = False            # Suppress MR-9 over-escaped shell $$ PID-corruption lint rule (BUG-2368)
    parse_swallow_ok: bool = False        # Suppress MR-10 inline-Python parse-swallow lint rule
    unsafe_context_interpolation_ok: bool = False  # Suppress MR-11 unsafe raw context interpolation lint rule (BUG-2622)
    policy_dims_scored_ok: bool = False   # Suppress policy-table inactive-rubric-dim lint rule
    imports: list[str] = []               # Raw `import:` list from YAML (fragment metadata, not serialized by to_dict)
```

**Nested config dataclasses (FEAT-1637):**

```python
@dataclass
class RepeatedFailureConfig:
    window: int = 3                        # Consecutive identical triples required to fire
    on_repeated_failure: str = "abort"     # "abort" or name of a declared recovery state
    progress_paths: list[str] = field(default_factory=list)  # BUG-1674: opt-in fingerprint paths
    exclude_paths: list[str] = field(default_factory=list)   # BUG-1767: paths to exclude from fingerprint
    recurrent_window: int | None = None    # ENH-2245: total occurrences threshold (non-consecutive); None = disabled

@dataclass
class CircuitConfig:
    repeated_failure: RepeatedFailureConfig | None = None
```

The stall detector records `(state_name, exit_code, eval_verdict)` after every transition and fires when the last `window` triples are identical. When `on_repeated_failure == "abort"` the run terminates with `terminated_by="stall_detected"` (exit code 1); otherwise the executor routes to the named state. Each firing also emits a `stall_detected` event with `state`, `exit_code`, `verdict`, `consecutive`, and `action` fields.

**`progress_paths` — fingerprint-based reset (BUG-1674):** Loops with a check↔work ping-pong where the work state uses `next:` (no `evaluate:`) are invisible to the detector — only the eval-bearing state records triples, so three identical `check` verdicts fire the stall even when `work` made real file-level progress. Set `progress_paths` to a list of paths (supports `${env.PWD}` interpolation) to watch: if any path's `(mtime, size)` changes between two consecutive records for the same eval-bearing state, the rolling window resets. Empty by default — existing loops without this field retain current semantics.

**`exclude_paths` — bookkeeping file exclusion (BUG-1767):** When a loop's own internal tracking files (plan, DoD, scratchpad) are listed in `progress_paths`, every append to those files resets the stall window, silently disabling stall detection. Add such files to `exclude_paths` so the executor filters them out before computing the fingerprint. Paths support `${env.PWD}` interpolation. `ll-loop validate` emits a WARNING when a state action references a `progress_paths` file that is not also in `exclude_paths`.

**`recurrent_window` — non-consecutive stall detection (ENH-2245):** The consecutive detector only fires when the same triple appears N times *in a row*. Loops that cycle through intermediate states between each failure (e.g., `run_final_tests → continue_work → select_step → run_final_tests → ...`) never produce consecutive triples, so the consecutive guard never fires regardless of how many times the failure occurs. Set `recurrent_window: N` to also fire the circuit breaker when the same `(state, exit_code, verdict)` triple has been seen N times *total* across the run (non-consecutive). The same `on_repeated_failure` target and `stall_detected` event are reused; the event payload uses `recurrent` (total count) instead of `consecutive`. `null` (default) disables this check — existing loops are unaffected. Minimum value: 2.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert to dictionary for serialization |
| `from_dict(data)` | `FSMLoop` | Create from dictionary |
| `get_all_state_names()` | `set[str]` | All defined state names |
| `get_terminal_states()` | `set[str]` | States with `terminal=True` |
| `get_all_referenced_states()` | `set[str]` | All states referenced by transitions |

When any single state→state edge (e.g., `evaluate → fix`) is traversed more than `max_edge_revisits` times, the loop terminates immediately with `terminated_by="cycle_detected"` (exit code 1) rather than continuing until `max_steps` is reached. This prevents tight infinite loops where two states bounce between each other indefinitely without making progress. Edge counts are persisted in `LoopState` so they survive a `--resume`. The default value of `100` covers all practical loops; lower it on short single-purpose loops to catch regressions faster.

```yaml
# Example: tighten cycle guard on a short loop
name: quick-check
max_steps: 10
max_edge_revisits: 5   # terminate if any edge fires more than 5 times
```

**Example:**
```python
from little_loops.fsm import FSMLoop, StateConfig

fsm = FSMLoop(
    name="check-fix-loop",
    initial="check",
    states={
        "check": StateConfig(
            action="pytest",
            on_yes="done",
            on_no="fix",
        ),
        "fix": StateConfig(
            action="/ll:manage-issue bug fix",
            next="check",
        ),
        "done": StateConfig(terminal=True),
    },
    max_steps=20,
)
```

**Sub-loop composition example** — a parent loop that sequences two child loops:
```python
from little_loops.fsm import FSMLoop, StateConfig

# Parent loop: run quality gate, then commit changes
fsm = FSMLoop(
    name="quality-then-commit",
    initial="run_quality",
    states={
        "run_quality": StateConfig(
            loop="fix-quality-and-tests",   # Invokes .loops/fix-quality-and-tests.yaml
            context_passthrough=True,       # Share parent context; merge child captures back
            on_success="run_git",           # Alias for on_yes
            on_failure="done",              # Alias for on_no
        ),
        "run_git": StateConfig(
            loop="issue-refinement-git",
            on_success="done",
            on_failure="done",
        ),
        "done": StateConfig(terminal=True),
    },
    max_steps=5,
)
```

#### StateConfig

Configuration for a single FSM state.

```python
@dataclass
class StateConfig:
    action: str | None = None          # Command to execute
    action_type: str | None = None     # How to run action: "prompt", "slash_command", "shell", "mcp_tool"
    params: dict[str, Any] = field(default_factory=dict)  # MCP tool arguments (mcp_tool only)
    evaluate: EvaluateConfig | None = None  # Evaluator configuration
    route: RouteConfig | None = None   # Full routing table
    on_yes: str | None = None          # Shorthand routing
    on_no: str | None = None           # Shorthand routing
    on_error: str | None = None        # Shorthand routing
    on_partial: str | None = None      # Shorthand routing for partial verdict
    on_blocked: str | None = None      # Shorthand routing for blocked verdict
    next: str | None = None            # Unconditional transition
    terminal: bool = False             # End state marker
    capture: str | None = None         # Variable name to store output
    append_to_messages: str | None = None  # Append captured value to message history
    timeout: int | None = None         # Action timeout in seconds
    on_maintain: str | None = None     # State for maintain mode restart
    max_retries: int | None = None     # Max consecutive re-entries before on_retry_exhausted
    on_retry_exhausted: str | None = None  # State when max_retries exceeded
    retryable_exit_codes: list[int] | None = None  # Exit codes that trigger retry (for shell states)
    loop: str | None = None            # Sub-loop to invoke (name from .loops/<name>.yaml)
    context_passthrough: bool = False  # Pass parent context vars to child; merge child captures back
    with_: dict[str, Any] = field(default_factory=dict)  # Explicit parameter bindings for sub-loop calls
    worktree: str | None = None        # Branch-name template; child runs in a scratch worktree on that branch (sub-loop states only, ENH-2609)
    fragment_name: str | None = None   # Original fragment name (populated by resolve_fragments)
    fragment_bindings: dict[str, Any] = field(default_factory=dict)  # Parameter bindings for fragment references
    fragment_parameters: dict[str, Any] = field(default_factory=dict)  # Parsed ParameterSpec declarations
    agent: str | None = None           # Subprocess agent name; passes --agent <name> to Claude CLI (prompt states only)
    tools: list[str] | None = None     # Subprocess tool scope; passes --tools <csv> to Claude CLI (prompt states only)
    model: str | None = None           # Model override for this state's LLM action
    extra_routes: dict[str, str] = field(default_factory=dict)  # Additional on_<verdict> → state mappings
    type: str | None = None            # State type marker (e.g., "learning")
    max_rate_limit_retries: int | None = None        # Short-burst tier budget; requires on_rate_limit_exhausted
    on_rate_limit_exhausted: str | None = None       # Target state when total wall-clock budget spent
    rate_limit_backoff_base_seconds: int | None = None  # Short-tier backoff base (default 30); delay = base * 2^n + jitter
    rate_limit_max_wait_seconds: int | None = None   # Total wall-clock budget across both tiers (default 21600 / 6h)
    rate_limit_long_wait_ladder: list[int] | None = None  # Long-wait ladder (default [300, 900, 1800, 3600]); index caps at last entry
    throttle: ThrottleConfig | None = None           # Per-state progressive tool-call throttling
    on_throttle_hard: str | None = None              # Target state when hard_max is reached (or hard-stop if unset)
    learning: LearningConfig | None = None           # FEAT-1283: type=learning state targets + retry budget
    cost_ceiling: CostCeilingConfig | None = None    # Per-state USD limit for LLM actions; routes on cost ceiling trip
```

#### ThrottleConfig

`from little_loops.fsm.schema import ThrottleConfig`

Per-state progressive throttling configuration. Counts tool calls within a single state visit and escalates restrictions before provider limits are hit.

```python
@dataclass
class ThrottleConfig:
    normal_max: int | None = None   # Calls 1..normal_max pass through (default 3)
    warn_max: int | None = None     # At warn_max, emits throttle_warn event (default 8)
    hard_max: int | None = None     # At hard_max, routes to on_throttle_hard (default 12)
```

**Throttle event constants** (emitted to the EventBus):

| Constant | Value | Description |
|----------|-------|-------------|
| `THROTTLE_WARN_EVENT` | `"throttle_warn"` | Emitted when tool-call count reaches `warn_max` |
| `THROTTLE_HARD_EVENT` | `"throttle_hard"` | Emitted when tool-call count reaches `hard_max` |
| `THROTTLE_STOP_EVENT` | `"throttle_stop"` | Emitted when count exceeds `hard_max` with no `on_throttle_hard` (hard stop) |

#### PromptSizeGuardConfig

`from little_loops.fsm.schema import PromptSizeGuardConfig`

ENH-2486: per-loop guard that WARNs when a fully-interpolated action grows large. The executor measures `len(action)` (chars) at the single interpolation choke point in `FSMExecutor._run_action` and emits `prompt_size_warn` when it reaches `warn_chars`. WARN-only (it does not route) — it turns a silently ballooning prompt (e.g. a state that re-embeds a monotonically growing captured output each iteration) into an observable signal in `<run>.events.jsonl`. Disable per-run with `--no-prompt-size-guard`; the size unit is chars because the codebase has no tokenizer (the event also reports `est_tokens = size // 4`).

```python
@dataclass
class PromptSizeGuardConfig:
    enabled: bool = True       # Master switch (disable with --no-prompt-size-guard)
    warn_chars: int = 50_000   # Chars at/above which prompt_size_warn fires; 0 disables
```

**Prompt-size event constant** (emitted to the EventBus):

| Constant | Value | Description |
|----------|-------|-------------|
| `PROMPT_SIZE_WARN_EVENT` | `"prompt_size_warn"` | Emitted when an interpolated action's size reaches `warn_chars` |

#### LearningConfig

`from little_loops.fsm.schema import LearningConfig`

FEAT-1283: per-state configuration for `type: learning` dispatch. The handler resolves the target list at runtime — if `targets_csv` is set it is interpolated and CSV-split; otherwise `targets` is used directly. The retry limit is resolved similarly: `max_retries_expr` (if set) is interpolated and `int()`-cast; otherwise `max_retries` (default 2) is used. Each target is then consulted in the learning-tests registry (ENH-1282); the state invokes `/ll:explore-api <target>` on a missing or stale record and advances via `on_yes` only after every target reaches status `proven`; refuted records and exhausted retries route to `on_blocked` (preferred) or `on_no`.

```python
@dataclass
class LearningConfig:
    targets: list[str] = field(default_factory=list)  # Ordered targets (slugified internally for registry lookups)
    targets_csv: str | None = None      # Runtime-interpolated CSV alternative to targets (ENH-1741)
    max_retries: int = 2                # Max /ll:explore-api invocations per target before routing to on_blocked
    max_retries_expr: str | None = None # Runtime-interpolated retry limit; takes precedence over max_retries (ENH-1741)
```

**Learning event types** (see `docs/reference/EVENT-SCHEMA.md` for full payloads):

| Event | Description |
|-------|-------------|
| `learning_target_proven` | A target's registry record is current with status=`proven` |
| `learning_target_stale` | A target's record is missing or stale; explore-api is about to fire |
| `learning_explore_invoked` | The state is calling `/ll:explore-api <target>` (paired with `action_start`) |
| `learning_target_refuted` | A target's record has status=`refuted`; state routes to blocked |
| `learning_complete` | Every target proven; state advances via `on_yes` |
| `learning_blocked` | State cannot advance (reason: `refuted` or `retries_exhausted`) |

> **Rate-limit handling (two-tier):** When a state's action returns an HTTP 429, the executor runs a two-tier retry ladder. **Short-burst tier** (up to `max_rate_limit_retries` attempts) uses `rate_limit_backoff_base_seconds * 2^n` + jitter. Once the short tier is spent, the executor enters the **long-wait tier** and walks `rate_limit_long_wait_ladder` (advancing index on each 429, capped at the last entry). The FSM routes to `on_rate_limit_exhausted` only once `total_wait_seconds >= rate_limit_max_wait_seconds`. The jitter is important under `ll-parallel` to avoid thundering-herd re-requests after a shared 429.

> **Alias note:** `on_success` and `on_failure` are accepted as aliases for `on_yes` and `on_no` in all states (including sub-loop states).

#### TargetStateSpec

`from little_loops.fsm import TargetStateSpec`

ENH-1552: per-state optimization spec for `harness-optimize` APO. Names a single FSM state within a target loop file and associates it with the examples file and eval fragment used during that state's optimization pass.

```python
@dataclass
class TargetStateSpec:
    name: str             # State name within the target loop
    examples_file: str    # Path to the examples YAML file for this state
    eval_fragment: str    # Eval fragment identifier (serialized as "eval:" in YAML)
```

#### TargetFileSpec

`from little_loops.fsm import TargetFileSpec`

ENH-1552: per-file targeting spec for `harness-optimize` APO. Associates a loop YAML file (or glob pattern) with the list of states to optimize.

```python
@dataclass
class TargetFileSpec:
    file: str | None = None            # Explicit path to a loop YAML file
    glob: str | None = None            # Glob pattern matching loop YAML files
    states: list[TargetStateSpec] = [] # States within the matched file(s) to optimize
```

#### EvaluateConfig

Evaluator configuration for action result interpretation.

```python
@dataclass
class EvaluateConfig:
    type: Literal[
        "exit_code",        # Map exit codes to verdicts
        "output_numeric",   # Compare numeric output
        "output_json",      # Extract and compare JSON path
        "output_contains",  # Pattern matching
        "convergence",      # Progress toward target
        "diff_stall",       # Detect stalled iterations via git diff
        "score_stall",      # Detect scored-output plateau via per-round score history
        "action_stall",     # Detect repeated action/output for N consecutive iterations
        "llm_structured",   # LLM with structured output
        "mcp_result",       # Parse MCP tool call response envelope
        "harbor_scorer",    # Harbor-format benchmark scorer (exit code + float stdout)
        "comparator",       # Blind A/B comparison against stored baseline via LLM judge
        "contract",         # Validate producer/consumer pairs
        "classify",         # Classify a single line of output
    ]
    operator: str | None = None        # Comparison: eq, ne, lt, le, gt, ge
    target: int | float | str | None = None  # Target value
    tolerance: float | str | None = None     # For convergence
    pattern: str | None = None         # For output_contains
    negate: bool = False               # Invert match result
    path: str | None = None            # JSON path for output_json
    prompt: str | None = None          # For llm_structured
    schema: dict | None = None         # For llm_structured
    min_confidence: float = 0.5        # For llm_structured
    uncertain_suffix: bool = False     # Append _uncertain to low-confidence
    source: str | None = None          # Override default source
    previous: str | None = None        # Previous value reference
    direction: Literal["minimize", "maximize"] = "minimize"
    scope: list[str] | None = None     # For diff_stall: limit git diff to these paths
    max_stall: int = 1                 # For diff_stall/score_stall: consecutive no-progress rounds before failure
    history_file: str | None = None    # For score_stall: per-round score-history file (default: ${context.run_dir}/.score_history)
    epsilon: float = 0.5               # For score_stall: minimum score improvement counted as progress
    track: list[str] | None = None    # For action_stall: context keys to track (default: ["action"])
    max_repeat: int = 2               # For action_stall: consecutive identical iterations before failure
    baseline_path: str | None = None   # For comparator: path to .loops/baselines/<loop>/ dir
    auto_promote: bool = False         # For comparator: write output to baseline on yes verdict
    min_pairs: int = 1                 # For comparator: number of blind A/B comparison pairs
    pairs: list[dict] | None = None    # For contract: list of producer/consumer pair dicts
    line: str | int | None = None      # For classify: which line to read (last/first/<int index>)
    error_patterns: list[str] | None = None  # For output_contains: patterns that yield verdict="error"
```

#### RouteConfig

Routing table configuration for verdict-to-state mapping.

```python
@dataclass
class RouteConfig:
    routes: dict[str, str] = {}  # Verdict -> next state
    default: str | None = None   # Default for unmatched verdicts ("_")
    error: str | None = None     # State for errors ("_error")
```

**Example:**
```python
from little_loops.fsm import StateConfig, EvaluateConfig, RouteConfig

state = StateConfig(
    action="check_status",
    evaluate=EvaluateConfig(
        type="output_json",
        path=".status",
        operator="eq",
        target="ready",
    ),
    route=RouteConfig(
        routes={"yes": "proceed", "no": "wait"},
        default="error_state",
    ),
)
```

#### LLMConfig

LLM evaluation configuration.

```python
@dataclass
class LLMConfig:
    enabled: bool = True
    model: str = DEFAULT_LLM_MODEL  # Default from schema.py
    max_tokens: int = 256
    timeout: int = 30
```

---

### little_loops.fsm.evaluators

Evaluators interpret action output and produce verdicts for state transitions.

#### EvaluationResult

```python
@dataclass
class EvaluationResult:
    verdict: str                  # Routing key for transitions
    details: dict[str, Any]       # Evaluator-specific metadata
```

For `llm_structured` evaluations (ENH-2342), `details` always includes:
- `evidence: str` — verbatim quote from action output supporting the verdict; empty string means no evidence was found
- `evidence_coerced: bool` — `True` when evidence was absent and the verdict was downgraded to `"no"` (only fires for default schema; custom schemas bypass coercion)

#### Tier 1 Evaluators (Deterministic)

```python
def evaluate_exit_code(exit_code: int) -> EvaluationResult
```
Map Unix exit code to verdict: 0→success, 1→failure, 2+→error

```python
def evaluate_output_numeric(
    output: str,
    operator: str,
    target: float,
) -> EvaluationResult
```
Parse stdout as number and compare to target.

```python
def evaluate_output_json(
    output: str,
    path: str,
    operator: str,
    target: Any,
) -> EvaluationResult
```
Parse JSON and extract value at jq-style path, then compare.

```python
def evaluate_output_contains(
    output: str,
    pattern: str,
    negate: bool = False,
    error_patterns: list[str] | None = None,
) -> EvaluationResult
```
Check if pattern (regex or substring) exists in output. When `error_patterns` is set and the
main pattern is not found, any matching error_pattern yields `verdict="error"` instead of `"no"`,
enabling `on_error` routing for auth/error output even when the action exits with code 0.

```python
def evaluate_convergence(
    current: float,
    previous: float | None,
    target: float,
    tolerance: float = 0,
    direction: str = "minimize",
) -> EvaluationResult
```
Compare current value to target and previous. Returns: target, progress, or stall.

#### Tier 2 Evaluators (LLM-based)

```python
def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = DEFAULT_LLM_MODEL,  # Default from schema.py
    max_tokens: int = 256,
    timeout: int = 30,
) -> EvaluationResult
```
Evaluate action output using an LLM with structured output. Dispatches through `host_runner.resolve_host().build_blocking_json()` and calls the resolved CLI as a subprocess (no Anthropic Python SDK dependency); requires a supported host CLI on PATH (e.g. `claude`).

#### Dispatcher

```python
def evaluate(
    config: EvaluateConfig,
    output: str,
    exit_code: int,
    context: InterpolationContext,
) -> EvaluationResult
```
Dispatch to appropriate evaluator based on config type.

**Action-level timeouts**: When `exit_code == 124` (action killed at its `timeout:`), the dispatcher short-circuits to `EvaluationResult(verdict="error", details={"exit_code": 124, "error": "action timed out"})` for all types except `mcp_result` (which has its own `timeout` verdict). This ensures `on_error:` is the canonical branch for action timeouts regardless of evaluator type.

**Example:**
```python
from little_loops.fsm import evaluate_exit_code, evaluate_output_contains

# Exit code evaluation
result = evaluate_exit_code(0)
print(result.verdict)  # "yes"

# Pattern matching
result = evaluate_output_contains("All tests passed", "passed")
print(result.verdict)  # "yes"

result = evaluate_output_contains("Error occurred", "Error", negate=True)
print(result.verdict)  # "no"
```

---

### little_loops.fsm.executor

Runtime engine for FSM loop execution.

#### FSMExecutor

```python
class FSMExecutor:
    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: ActionRunner | None = None,
        signal_detector: SignalDetector | None = None,
        handoff_handler: HandoffHandler | None = None,
        loops_dir: Path | None = None,
        circuit: RateLimitCircuit | None = None,
    )
```

Execute an FSM loop until terminal state, max iterations, timeout, or signal.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `ExecutionResult` | Execute FSM to completion |
| `request_shutdown()` | `None` | Request graceful shutdown |

**Example:**
```python
from little_loops.fsm import FSMLoop, StateConfig, FSMExecutor

fsm = FSMLoop(
    name="test",
    initial="check",
    states={
        "check": StateConfig(action="pytest", on_yes="done", on_no="check"),
        "done": StateConfig(terminal=True),
    },
)

events = []
executor = FSMExecutor(fsm, event_callback=events.append)
result = executor.run()

print(result.final_state)     # "done"
print(result.iterations)      # Number of iterations
print(result.terminated_by)   # "terminal", "max_steps", "max_iterations_reached", "timeout", "interrupted", "cycle_detected", "stall_detected", or "error"
```

#### ExecutionResult

```python
@dataclass
class ExecutionResult:
    final_state: str                      # State when execution stopped
    iterations: int                       # Total iterations
    terminated_by: str                    # "terminal" | "max_steps" | "max_iterations_reached" | "timeout" | "interrupted" | "cycle_detected" | "stall_detected" | "error"
    duration_ms: int                      # Total execution time
    captured: dict[str, dict[str, Any]]   # Captured variable values
    error: str | None = None              # Error message if failed
```

#### ActionResult

```python
@dataclass
class ActionResult:
    output: str       # stdout
    stderr: str       # stderr
    exit_code: int    # Exit code
    duration_ms: int  # Execution time
```

#### ActionRunner Protocol

```python
class ActionRunner(Protocol):
    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Callable[[str], None] | None = None,
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: UsageCallback | None = None,
        on_usage_detailed: DetailedUsageCallback | None = None,
        model: str | None = None,
    ) -> ActionResult: ...
```

Implement this protocol to customize action execution (useful for testing). In the extension system, `ActionRunner` is also the contributed-actions runtime dispatch interface — extension plugins register runners against custom `action_type` strings via `ActionProviderExtension.provided_actions()`, and `FSMExecutor` dispatches to them through the `_contributed_actions` registry at runtime.

---

### little_loops.fsm.interpolation

Variable interpolation using `${namespace.path}` syntax.

#### InterpolationContext

```python
@dataclass
class InterpolationContext:
    context: dict[str, Any] = {}           # User-defined variables
    captured: dict[str, dict] = {}         # Stored action results
    prev: dict[str, Any] | None = None     # Previous state result
    result: dict[str, Any] | None = None   # Current evaluation result
    state_name: str = ""                   # Current state
    iteration: int = 1                     # Current iteration
    loop_name: str = ""                    # FSM loop name
    started_at: str = ""                   # ISO timestamp
    elapsed_ms: int = 0                    # Milliseconds since start
```

**Supported namespaces:**
- `context` - User-defined variables from FSM context block
- `captured` - Values stored via `capture:` in states
- `prev` - Previous state's result (output, exit_code, state)
- `result` - Current evaluation result (verdict, details)
- `state` - Current state metadata (name, iteration)
- `loop` - Loop metadata (name, started_at, elapsed_ms, elapsed)
- `env` - Environment variables

**Methods:**

```python
def resolve(self, namespace: str, path: str) -> Any
```
Resolve a namespace.path reference to its value.

#### interpolate

```python
def interpolate(template: str, ctx: InterpolationContext) -> str
```

Replace `${namespace.path}` variables in template string.

**Example:**
```python
from little_loops.fsm import InterpolationContext, interpolate

ctx = InterpolationContext(
    context={"target_dir": "src/", "threshold": 10},
    captured={"check": {"output": "5", "exit_code": 0}},
)

result = interpolate("mypy ${context.target_dir}", ctx)
# Returns: "mypy src/"

result = interpolate("Errors: ${captured.check.output}", ctx)
# Returns: "Errors: 5"

# Escape with $$ — passes through as literal ${...}
result = interpolate("Use $${context.var} syntax", ctx)
# Returns: "Use ${context.var} syntax"

# Bash parameter expansion operators inside $${ } pass through unchanged
result = interpolate("printf '$${DEPTH:-0}'", ctx)
# Returns: "printf '${DEPTH:-0}'"  (bash evaluates ${DEPTH:-0} at runtime)

# Safe interpolation — :default= returns fallback on missing path
result = interpolate("${captured.missing:default=fallback}", ctx)
# Returns: "fallback"

# Safe interpolation — ? returns empty string on missing path
result = interpolate("${captured.missing?}", ctx)
# Returns: ""

# :shell suffix — shlex.quote()s the value for safe use in a bash token
# position (BUG-2622); used WITHOUT surrounding quotes
result = interpolate('VAL=${context.target_dir:shell}', ctx)
# Returns: "VAL=src/"

# Unsuffixed references still raise InterpolationError on missing paths
# interpolate("${captured.missing}", ctx)  → InterpolationError
```

#### interpolate_dict

```python
def interpolate_dict(obj: dict[str, Any], ctx: InterpolationContext) -> dict[str, Any]
```

Recursively interpolate all string values in a dict.

---

### little_loops.fsm.validation

FSM validation and loading utilities.

#### ValidationError

```python
@dataclass
class ValidationError:
    message: str                           # Human-readable description
    path: str | None = None                # Path to problematic element
    severity: ValidationSeverity = ERROR   # ERROR or WARNING
```

#### validate_fsm

```python
def validate_fsm(fsm: FSMLoop) -> list[ValidationError]
```

Validate FSM structure and return list of errors.

**Checks performed:**
- Initial state exists in states dict
- All referenced states exist
- At least one terminal state defined
- Evaluator configs have required fields
- No conflicting routing definitions
- Warns about unreachable states
- Warns when no top-level `description:` field is set
- Warns (WARNING) when a failure-named terminal state (e.g. `failed`, `error`, `aborted`) has no predecessor state with a diagnostic action
- **MR-1 (ERROR)**: meta-loop (writes harness artifacts or imports `lib/benchmark.yaml`) must have at least one non-LLM evaluator; suppress with `meta_self_eval_ok: true` (ENH-1665)
- **MR-2 (WARNING)**: meta-loop should reference a captured baseline value in a later evaluator (measure→propose→apply→re-measure spine); suppress with `meta_self_eval_ok: true` (ENH-1665)
- **MR-3 (WARNING)**: loop writes intermediate artifacts to shared `.loops/tmp/` instead of `${context.run_dir}/`; suppress with `shared_state_ok: true`
- **MR-4 (WARNING)**: LLM-judged state maps `on_yes` but has no route for `no`/`partial` verdicts with no `next:` or `route:` table — dead-ends the loop; suppress with `partial_route_ok: true` (ENH-1917)
- **MR-5 (WARNING)**: harness-category loop writes artifact files to a flat path in an iterative generate→evaluate→generate cycle — only the final iteration's output survives; add per-iteration snapshots and declare `artifact_versioning: true`, or set `artifact_versioning_ok: true` to suppress when intentional overwrite is desired (ENH-1957)
- **MR-6 (WARNING)**: meta-loop has a `shell`-type state that writes to the same file path as an LLM-generator state — hand-patching creates fragile output that diverges from the generator on the next run; fix the generator action so every run produces correct output automatically, or set `generator_fix_ok: true` for intentional post-processing (ENH-2079)
- **MR-7 (ERROR)**: any FSM action string contains an unescaped `${namespace.path:-default}` (bash `:-` default syntax) — the interpolation engine crashes at runtime; use `${ns.path:default=value}` (engine-native) or `$${VAR:-value}` (shell-escaped), or set `bash_default_ok: true` to suppress (ENH-2348)
- **MR-8 (WARNING)**: a `check_semantic`/`llm_structured` state's `evaluate.prompt` omits evidence-contract keywords (`verbatim`, `quote`, `evidence`) — verdicts without verbatim citation requirements default to optimism (SHOR Table 1: 33–55% accuracy); states with `evaluate.prompt: null` inherit `DEFAULT_LLM_PROMPT` which includes the contract automatically; set `evidence_contract_ok: true` to suppress (ENH-2342)
- **MR-9 (ERROR)**: a shell action string contains `$$(` or `$$VAR` — over-escaped bash; the FSM interpolator only rewrites the brace form `$${...}` → `${...}`, so bare `$(...)` / `$VAR` doubled with `$$` expand to the runner's PID at runtime, silently corrupting every downstream `${captured.*}` reference; use single `$` for command substitution and variables, reserve `$$` exclusively for the `$${VAR}` brace escape that collides with `${ns.path}` interpolation; set `shell_pid_ok: true` to suppress (BUG-2368)
- **MR-10 (WARNING)**: a `shell`-type state's inline Python calls `json.loads`/`json.load`, catches `JSONDecodeError`/`ValueError`/bare `Exception`, and explicitly exits 0 — without an `on_error:` route — silently discarding parse failures as an empty success; add `on_error:` to route parse failures explicitly, or set `parse_swallow_ok: true` to suppress when an empty result is intentional (BUG-2383)
- **MR-11 (WARNING)**: a `shell`-type state pastes a user-controlled `${context.input|goal|description|task|prompt|query|topic}` value raw into the action body outside a safe position (single-quoted string, quoted heredoc `<<'EOF'`, or the `:shell` suffix) — `interpolate()` substitutes with a bare `str(value)` and no shell escaping, so a value containing `"`, `$`, `` ` ``, `\`, or `!` breaks bash tokenizing or injects commands; wrap the placeholder in single quotes, write it through a quoted heredoc, or use `${context.input:shell}` to shlex-quote it, or set `unsafe_context_interpolation_ok: true` to suppress (BUG-2622)

**Example:**
```python
from little_loops.fsm import FSMLoop, StateConfig, validate_fsm, ValidationSeverity

fsm = FSMLoop(
    name="test",
    initial="start",
    states={
        "start": StateConfig(action="echo", on_yes="done", on_no="done"),
        "done": StateConfig(terminal=True),
    },
)

errors = validate_fsm(fsm)
error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
print(f"Found {len(error_list)} errors")
```

#### load_and_validate

```python
def load_and_validate(path: Path) -> FSMLoop
```

Load YAML file and validate FSM structure.

**Parameters:**
- `path` - Path to YAML file

**Returns:** Validated `FSMLoop` instance

**Raises:**
- `FileNotFoundError` - If file doesn't exist
- `yaml.YAMLError` - If invalid YAML
- `ValueError` - If validation fails

**Example:**
```python
from pathlib import Path
from little_loops.fsm import load_and_validate

try:
    fsm = load_and_validate(Path(".loops/my-loop.yaml"))
    print(f"Loaded loop: {fsm.name}")
except ValueError as e:
    print(f"Validation error: {e}")
```

---

### little_loops.fsm.persistence

State persistence and event streaming for FSM loops.

#### LoopState

```python
@dataclass
class LoopState:
    loop_name: str                        # Name of the loop
    current_state: str                    # Current FSM state
    iteration: int                        # Current iteration
    captured: dict[str, dict[str, Any]]   # Captured outputs
    prev_result: dict[str, Any] | None    # Previous state result
    last_result: dict[str, Any] | None    # Last evaluation result
    started_at: str                       # ISO timestamp
    updated_at: str                       # Last update timestamp
    status: str                           # running, completed, failed, interrupted
    continuation_prompt: str | None       # Handoff context (awaiting_continuation)
    accumulated_ms: int                   # Total elapsed ms across segments (resume offset)
    retry_counts: dict[str, int]          # Per-state retry tracking
    messages: list[str]                   # Emitted loop messages
    context: dict[str, Any]               # Full FSM context (input, program.md, --context);
                                          # persisted for resume (BUG-2485). Kept out of the
                                          # CLI status/list --json contract: to_dict() emits it
                                          # only when include_context=True (the on-disk path).
```

#### StatePersistence

```python
class StatePersistence:
    def __init__(self, loop_name: str, loops_dir: Path | None = None, instance_id: str | None = None)
```

Manage loop state persistence and event streaming.

**Methods:**

| Method | Description |
|--------|-------------|
| `initialize()` | Create running directory |
| `save_state(state)` | Save state to JSON file |
| `load_state()` | Load state, or None if not exists |
| `clear_state()` | Remove state file |
| `append_event(event)` | Append event to JSONL file |
| `read_events()` | Read all events from file |
| `clear_events()` | Remove events file |
| `clear_all()` | Archive current run to history, then clear state, events, and meta-eval |
| `archive_run(run_dir=None)` | Copy state, events, meta-eval (meta-loops), and summary.json (when present in `run_dir`) to `.loops/.history/<run_id>-<name>/` |

**File structure:**
```
.loops/
├── my-loop.yaml           # Loop definition
└── .running/              # Runtime state
    ├── my-loop-20260503T122306.state.json
    ├── my-loop-20260503T122306.events.jsonl
    └── my-loop-20260503T122306.meta-eval.jsonl  # meta-loops only
```

#### PersistentExecutor

```python
class PersistentExecutor:
    def __init__(
        self,
        fsm: FSMLoop,
        persistence: StatePersistence | None = None,
        loops_dir: Path | None = None,
        **executor_kwargs,
    )
```

FSM Executor with state persistence and event streaming.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `run(clear_previous=True)` | `ExecutionResult` | Run with persistence |
| `resume()` | `ExecutionResult \| None` | Resume from saved state |
| `request_shutdown()` | `None` | Request graceful shutdown |

**Example:**
```python
from pathlib import Path
from little_loops.fsm import FSMLoop, StateConfig, PersistentExecutor

fsm = FSMLoop(
    name="my-loop",
    initial="check",
    states={
        "check": StateConfig(action="pytest", on_yes="done", on_no="check"),
        "done": StateConfig(terminal=True),
    },
)

executor = PersistentExecutor(fsm, loops_dir=Path(".loops"))
result = executor.run()

# Later, check saved state
state = executor.persistence.load_state()
print(f"Status: {state.status}")
```

#### Utility Functions

```python
def list_running_loops(loops_dir: Path | None = None) -> list[LoopState]
```
List all loops with saved state, including loops in the `starting` status (not yet executing their first state).

```python
def get_loop_history(loop_name: str, loops_dir: Path | None = None) -> list[dict]
```
Get event history for a loop.

---

### little_loops.fsm.handoff_handler

Handles context handoff signals during FSM loop execution, with configurable behavior (pause, spawn, or terminate).

#### HandoffBehavior

```python
class HandoffBehavior(Enum):
    TERMINATE = "terminate"   # Stop loop execution immediately, no state preservation
    PAUSE = "pause"           # Save state with continuation prompt and exit (default)
    SPAWN = "spawn"           # Save state and spawn a new Claude session to continue
```

#### HandoffResult

```python
@dataclass
class HandoffResult:
    behavior: HandoffBehavior               # The behavior that was applied
    continuation_prompt: str | None         # Continuation prompt from the signal
    spawned_process: subprocess.Popen | None = None  # Set if SPAWN behavior used
```

#### HandoffHandler

```python
class HandoffHandler:
    def __init__(self, behavior: HandoffBehavior = HandoffBehavior.PAUSE) -> None
```

Handle context handoff signals with configurable behavior.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `handle(loop_name, continuation)` | `HandoffResult` | Handle a detected handoff signal; save state responsibility falls on the caller |

**Example:**

```python
from little_loops.fsm.handoff_handler import HandoffHandler, HandoffBehavior

handler = HandoffHandler(HandoffBehavior.PAUSE)
result = handler.handle("fix-types", "Continue from iteration 5")
# result.behavior == HandoffBehavior.PAUSE
```

---

### little_loops.fsm.concurrency

Scope-based concurrency control for FSM loops. Prevents concurrent loops from conflicting on the same files via file-based locking under `.loops/.running/`.

#### ScopeLock

```python
@dataclass
class ScopeLock:
    loop_name: str      # Name of the loop holding the lock
    scope: list[str]    # List of paths this loop operates on
    pid: int            # Process ID of the lock holder
    started_at: str     # ISO timestamp when lock was acquired
    singleton: bool = False  # BUG-2526: True = block other instances with same loop_name
                             # regardless of scope overlap. False (default) preserves
                             # ENH-1354 / FEAT-1789 disjoint-scope concurrency.
```

**Methods:** `to_dict()`, `from_dict(data)`

`ScopeLock.from_dict()` reads the `singleton` key with a default of `False` so legacy lock files written before BUG-2526 (no `singleton` key) parse cleanly. New writers emit `singleton: true` only when the field is set.

#### LockManager

```python
class LockManager:
    def __init__(self, loops_dir: Path | None = None) -> None
```

Manage scope-based locks for concurrent loop execution. Lock files are stored in `.loops/.running/<instance_id>.lock`.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `acquire(loop_name, scope, instance_id=None, *, singleton=False)` | `bool` | Acquire lock; returns `False` if conflict exists. When `singleton=True`, any other instance with the same `loop_name` is a conflict regardless of scope overlap (BUG-2526). |
| `release(loop_name, instance_id=None)` | `None` | Release lock for a loop instance |
| `find_conflict(scope, *, caller_loop_name=None, caller_singleton=False)` | `ScopeLock \| None` | Find conflicting running loop; cleans stale locks. Returns `None` if the only conflict is an ancestor process of the caller (prevents self-blocking when a parent loop spawns a child that shares the same scope). When `caller_singleton=True` and `caller_loop_name` matches a candidate with `singleton=True`, also returns that candidate as a singleton conflict. |
| `list_locks()` | `list[ScopeLock]` | List all active locks; cleans stale locks |
| `wait_for_scope(scope, timeout=300, *, loop_name=None, singleton=False)` | `bool` | Wait until scope is available; `False` on timeout. Pass `loop_name` + `singleton=True` so the singleton predicate fires inside the polling loop. |

#### resolve_scope

```python
def resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]
```

Resolve `${context.<var>}` template expressions in scope paths. Each template referencing a context variable is replaced with the variable's value. Unresolved templates are preserved as literal strings. Static paths (no templates) pass through unchanged.

---

### little_loops.fsm.rate_limit_circuit

Shared circuit-breaker state file for cross-worktree 429 coordination.

#### RateLimitCircuit

```python
class RateLimitCircuit:
    def __init__(self, path: Path) -> None
```

File-backed circuit-breaker for shared 429 backoff coordination. The `path` argument is the absolute path to the shared JSON state file (internally coerced via `Path(path)`); a sidecar `.lock` file is derived from it for `fcntl.flock`-guarded writes.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `record_rate_limit(backoff_seconds)` | `None` | Record a 429 event; increments `attempts` and advances `estimated_recovery_at` monotonically so concurrent observers cannot shrink an in-flight backoff window |
| `get_estimated_recovery()` | `float \| None` | Epoch-seconds timestamp of estimated recovery, or `None` if the entry is stale or the file is absent |
| `is_stale()` | `bool` | `True` when `last_seen` is older than `STALE_THRESHOLD_SECONDS` (3600s); `False` if the file is absent |
| `clear()` | `None` | Remove the state file; no-op if already absent |

---

### little_loops.fsm.host_guard

Adaptive host memory-pressure guard (ENH-2452) and cumulative subprocess RSS budget (ENH-2453) for the FSM executor. Probes use `vm_stat` (macOS) and `/proc/meminfo` (Linux) — no psutil dependency.

#### HostGuardConfig

```python
@dataclass
class HostGuardConfig:
    enabled: bool = True                  # master switch (--no-host-guard overrides)
    cooldown_ms: int = 500                # extra sleep at warn_pct (added to --delay floor)
    warn_pct: float = 75.0                # used-memory % for extra cooldown
    critical_pct: float = 85.0            # used-memory % for on_pressure
    on_pressure: str = "cool_down"        # cool_down | route | abort
    pressure_state: str | None = None     # required when on_pressure="route"
    on_abort_route: str | None = None     # optional final state on abort
    max_cumulative_subproc_mb: int = 0    # RSS budget in MB; 0 = disabled
    on_budget_exceeded: str = "route"     # route | abort
    budget_state: str | None = None       # required when routing with an enabled budget
```

Mirrors the loop YAML `host_guard:` block; exposed as `FSMLoop.host_guard` (always present, default-enabled). Supports `to_dict()` / `from_dict()` with skip-if-default serialization.

#### HostGuard

```python
class HostGuard:
    def __init__(self, config: HostGuardConfig,
                 probe: Callable[[], float | None] = read_memory_pressure) -> None
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `pre_state()` | `GuardDecision` | Sample host memory and decide: `ok`, `cooldown`, `route`, or `abort`. Probe failures yield `ok` with `used_pct=None` |
| `record_subproc_rss(label, peak_rss_mb)` | `bool` | Accumulate one subprocess's peak RSS; returns `True` exactly once when the sum first crosses `max_cumulative_subproc_mb` |
| `budget_enabled` (property) | `bool` | `True` when `max_cumulative_subproc_mb > 0` |

#### Probes and sampling

| Function/Class | Description |
|----------------|-------------|
| `read_memory_pressure()` | Host used-memory percentage via `vm_stat` (macOS) or `/proc/meminfo` (Linux); `None` on failure |
| `parse_vm_stat(output)` / `parse_meminfo(text)` | Pure parsers for the probe outputs |
| `sample_rss_mb(pid)` | Live process RSS in MB (`VmHWM` peak on Linux, `ps -o rss=` elsewhere) |
| `RssSampler(pid, interval=1.0)` | Background thread tracking a subprocess's peak RSS (`start()` / `stop() -> float \| None`) |

#### Events

Emitted through the executor's event stream:

| Event | When |
|-------|------|
| `host_cooldown` | Used memory >= `warn_pct`; payload includes `used_pct`, `cooldown_seconds` |
| `host_pressure` | Used memory >= `critical_pct`; payload `action` is `route:<state>` or `abort` |
| `host_pressure_relieved` | Pressure dropped back below `warn_pct` after a critical crossing |
| `host_pressure_abort` | `on_pressure="abort"` fired; run finishes with `terminated_by="host_pressure_abort"` |
| `host_subproc_rss` | Per sampled subprocess; payload includes `peak_rss_mb`, `cumulative_mb`, `budget_mb` |
| `host_budget_exceeded` | Cumulative RSS sum first crossed the budget; run routes to `budget_state` or finishes with `terminated_by="host_budget_exceeded"` |

---

### little_loops.fsm.signal_detector

Pattern-based signal detection for interpreting special markers in action output (e.g. `CONTEXT_HANDOFF:`, `FATAL_ERROR:`, `LOOP_STOP:`).

#### DetectedSignal

```python
@dataclass
class DetectedSignal:
    signal_type: str        # Type of signal (e.g., "handoff", "error", "stop")
    payload: str | None     # Captured content after the signal marker
    raw_match: str          # The full matched string
```

#### SignalPattern

```python
class SignalPattern:
    def __init__(self, name: str, pattern: str) -> None
```

Configurable signal pattern using regex. A capture group extracts the payload.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `search(output)` | `DetectedSignal \| None` | Search for pattern in output |

**Built-in patterns:**

| Name | Marker | Signal type |
|------|--------|-------------|
| `HANDOFF_SIGNAL` | `CONTEXT_HANDOFF: <payload>` | `"handoff"` |
| `ERROR_SIGNAL` | `FATAL_ERROR: <payload>` | `"error"` |
| `STOP_SIGNAL` | `LOOP_STOP: <payload>` | `"stop"` |

#### SignalDetector

```python
class SignalDetector:
    def __init__(self, patterns: list[SignalPattern] | None = None) -> None
```

Detect signals in command output. Defaults to the three built-in patterns.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `detect(output)` | `list[DetectedSignal]` | Detect all signals in output |
| `detect_first(output)` | `DetectedSignal \| None` | Detect first matching signal (highest priority wins) |

**Example:**

```python
from little_loops.fsm.signal_detector import SignalDetector

detector = SignalDetector()
signal = detector.detect_first("Some output\nCONTEXT_HANDOFF: Ready for fresh session")
if signal and signal.signal_type == "handoff":
    print(signal.payload)  # "Ready for fresh session"
```

---

## little_loops.sprint

Sprint planning and execution for batch issue processing.

### SprintOptions

```python
@dataclass
class SprintOptions:
    max_iterations: int = 100   # Max Claude iterations per issue
    timeout: int = 3600         # Per-issue timeout in seconds
    max_workers: int = 2        # Worker count for parallel execution within waves
```

Sprint execution uses dependency-aware wave-based scheduling. Issues are grouped into waves where each wave contains issues whose blockers have all completed, and each wave is executed in parallel.

### Sprint

```python
@dataclass
class Sprint:
    name: str                           # Sprint identifier
    description: str                    # Human-readable purpose
    issues: list[str]                   # Issue IDs (e.g., BUG-001, FEAT-010)
    created: str                        # ISO 8601 timestamp
    options: SprintOptions | None       # Execution options
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |
| `from_dict(data)` | `Sprint` | Create from dictionary |
| `save(sprints_dir)` | `Path` | Save to YAML file |
| `load(sprints_dir, name)` | `Sprint \| None` | Load from file |

### SprintState

Persistent state for sprint execution. Enables resume capability after interruption.

```python
@dataclass
class SprintState:
    sprint_name: str = ""                           # Name of the sprint being executed
    current_wave: int = 0                           # Wave number currently being processed (1-indexed)
    completed_issues: list[str] = []                # Completed issue IDs
    failed_issues: dict[str, str] = {}              # Issue ID → failure reason
    skipped_blocked_issues: dict[str, str] = {}     # Issue ID → block reason
    timing: dict[str, dict[str, float]] = {}        # Per-issue timing breakdown
    started_at: str = ""                            # ISO 8601 start timestamp
    last_checkpoint: str = ""                       # ISO 8601 last save timestamp
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for JSON serialization |
| `from_dict(data)` | `SprintState` | Create from dictionary |

### SprintManager

```python
class SprintManager:
    def __init__(
        self,
        sprints_dir: Path | None = None,
        config: BRConfig | None = None,
    )
```

Manager for sprint CRUD operations.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `create(name, issues, description, options)` | `Sprint` | Create new sprint |
| `load(name)` | `Sprint \| None` | Load sprint by name |
| `load_or_resolve(arg)` | `Sprint \| None` | Load sprint by name **or** resolve an EPIC ID (`EPIC-NNN`) to an ephemeral Sprint via forward (`relates_to:`) + backward **transitive** (`parent:`-chain walk, cycle-guarded — grandchildren under sub-EPICs/intermediates included, ENH-2615) lookup, filtered to active statuses |
| `list_all()` | `list[Sprint]` | List all sprints |
| `delete(name)` | `bool` | Delete sprint |
| `validate_issues(issues)` | `dict[str, Path]` | Validate issue IDs exist |
| `load_issue_infos(issues)` | `list[IssueInfo]` | Load full IssueInfo objects for dependency analysis |

**Example:**
```python
from pathlib import Path
from little_loops.sprint import SprintManager, SprintOptions
from little_loops.config import BRConfig

config = BRConfig(Path.cwd())
manager = SprintManager(config=config)

# Create a sprint
sprint = manager.create(
    name="week-1",
    issues=["BUG-001", "BUG-002", "FEAT-010"],
    description="First week bug fixes and feature",
    options=SprintOptions(max_workers=2),
)

# Validate issues exist
valid = manager.validate_issues(sprint.issues)
print(f"Found {len(valid)} valid issues")

# List all sprints
for s in manager.list_all():
    print(f"{s.name}: {len(s.issues)} issues")
```

---

## little_loops.frontmatter

Shared YAML-subset frontmatter read/write utilities used by issue_parser, sync, and issue_history modules.

### Public Functions

| Function | Purpose |
|----------|---------|
| `parse_frontmatter` | Extract YAML frontmatter from file content |
| `parse_skill_frontmatter` | Extract flat key/value pairs from SKILL.md frontmatter, resolving block scalars |
| `strip_frontmatter` | Remove YAML frontmatter block, returning the body |
| `update_frontmatter` | Merge updates into (or create) the YAML frontmatter block |

### parse_frontmatter

```python
def parse_frontmatter(
    content: str, *, coerce_types: bool = False
) -> dict[str, Any]
```

Extract YAML frontmatter from content between opening and closing `---` markers. Parses it with `yaml.load` (`BaseLoader`), so any valid YAML is supported — including PyYAML's own serialized output (block sequences whose long items wrap across physical lines, block scalars, flow lists, and `\uXXXX` escapes). `BaseLoader` resolves every scalar to a string, preserving the `coerce_types=False` contract (values stay strings rather than being coerced to int/bool/datetime). Empty values (`key:`, `null`, `~`) normalize to `None`; `status` synonyms are canonicalized. Malformed YAML falls back to a permissive line-based scan that warns on orphaned `- item` lines.

**Parameters:**
- `content` - File content to parse
- `coerce_types` - If `True`, coerce digit strings to `int`

**Returns:** Dictionary of frontmatter fields, or empty dict if no frontmatter found.

**Example:**
```python
from little_loops.frontmatter import parse_frontmatter

content = "---\npriority: P1\ngithub_issue: 42\n---\n# Title"
meta = parse_frontmatter(content, coerce_types=True)
print(meta)  # {"priority": "P1", "github_issue": 42}
```

### parse_skill_frontmatter

```python
def parse_skill_frontmatter(text: str) -> dict[str, str]
```

Extract flat `key: value` pairs from SKILL.md frontmatter. Uses `yaml.safe_load` so YAML block scalars (e.g. `description: |`) are resolved to their string content instead of the indicator literal `"|"`. Non-string scalar values are stringified; nested structures are dropped. Falls back to a permissive line-based scan if the frontmatter is not valid YAML (e.g. unquoted colons in values).

Prefer this over `parse_frontmatter` for SKILL.md files: it stringifies scalar values (bools/ints) and returns a flat `dict[str, str]`, the shape SKILL.md consumers expect. (`parse_frontmatter` now resolves block scalars natively via YAML, but returns a richer `dict[str, Any]`.)

**Parameters:**
- `text` - Full SKILL.md file content (including the `---` delimited frontmatter block).

**Returns:** Dictionary mapping frontmatter keys to stringified values, or empty dict if no frontmatter found.

**Example:**
```python
from little_loops.frontmatter import parse_skill_frontmatter

content = "---\ndescription: |\n  Use when user does X.\n  Trigger keywords: foo\n---\n# Body"
fm = parse_skill_frontmatter(content)
print(fm["description"])  # "Use when user does X.\nTrigger keywords: foo\n"
```

### update_frontmatter

```python
def update_frontmatter(
    content: str, updates: dict[str, str | int]
) -> str
```

Merge `updates` into an existing `---` delimited YAML frontmatter block, preserving other fields and their order. If no frontmatter block exists, a new one is prepended. Existing keys are overwritten with the new values. Uses `yaml.dump` with `default_flow_style=False, sort_keys=False` so URLs and other colon-containing values round-trip correctly.

**Parameters:**
- `content` - Full file content, possibly with existing frontmatter
- `updates` - Fields to add or overwrite in frontmatter

**Returns:** Content with the updated frontmatter block.

**Example:**
```python
from little_loops.frontmatter import update_frontmatter

content = "---\npriority: P1\n---\n\n# Title\n"
result = update_frontmatter(content, {"completed_at": "2026-04-18T12:00:00Z"})
```

---

## little_loops.learning_tests

Registry for learning test records — structured knowledge about external APIs and libraries, persisted as YAML-frontmatter Markdown files under `.ll/learning-tests/<slug>.md`.

### Data Classes

#### Assertion

```python
@dataclass
class Assertion:
    claim: str
    result: Literal["pass", "fail", "untested"]
```

A single tested claim about an API or library behavior.

#### LearnTestRecord

```python
@dataclass
class LearnTestRecord:
    target: str                    # API or library name (e.g., "Anthropic SDK streaming")
    date: str                      # ISO date string (e.g., "2026-04-25")
    status: Literal["proven", "refuted", "stale"]
    assertions: list[Assertion]
    raw_output_path: str | None    # Path to raw test output, if captured
```

A record capturing what is known about a target API or library. Records are stored at `.ll/learning-tests/<slugified-target>.md`.

**File format** (`.ll/learning-tests/<slug>.md`):

```yaml
---
target: "Anthropic SDK streaming"
date: "2026-04-25"
status: proven
assertions:
  - claim: "streaming events are dicts with a `type` key"
    result: pass
raw_output_path: ".ll/learning-tests/raw/anthropic-sdk-streaming.txt"
---
```

### Public Functions

| Function | Purpose |
|----------|---------|
| `write_record` | Write a `LearnTestRecord` to `.ll/learning-tests/<slug>.md` |
| `read_record` | Read a record by slug; returns `None` if not found |
| `list_records` | Return all records in the registry directory |
| `mark_stale` | Set `status: stale` on an existing record, preserving other fields |
| `check_learning_test` | Look up a record by target name (slugified); returns `None` if not found |
| `resolve_learning_targets` | Return targets for an issue (field-first, JIT extraction fallback) — ENH-2319 |
| `run_learning_gate_for_issue` | Invoke `proof-first-task` loop and return `"passed"`, `"blocked"`, or `"skipped"` — ENH-2319 |

### write_record

```python
def write_record(
    record: LearnTestRecord, *, base_dir: Path | None = None
) -> Path
```

Write `record` to `.ll/learning-tests/<slug>.md`, overwriting any existing file for the same target slug. Returns the path of the written file.

**Example:**
```python
from little_loops.learning_tests import Assertion, LearnTestRecord, write_record

record = LearnTestRecord(
    target="Anthropic SDK streaming",
    date="2026-04-25",
    status="proven",
    assertions=[Assertion(claim="events have a 'type' key", result="pass")],
    raw_output_path=None,
)
path = write_record(record)
```

### read_record

```python
def read_record(
    target_slug: str, *, base_dir: Path | None = None
) -> LearnTestRecord | None
```

Read a record by its slug (the slugified form of `target`). Returns `None` if the file does not exist or has no parseable frontmatter.

### list_records

```python
def list_records(*, base_dir: Path | None = None) -> list[LearnTestRecord]
```

Return all `LearnTestRecord` objects in the registry directory, sorted by filename. Returns an empty list if the directory does not exist.

### mark_stale

```python
def mark_stale(target_slug: str, *, base_dir: Path | None = None) -> None
```

Set `status: stale` on the record identified by `target_slug`, preserving all other frontmatter fields. No-op if the record does not exist.

### check_learning_test

```python
def check_learning_test(
    target: str, *, base_dir: Path | None = None
) -> LearnTestRecord | None
```

Convenience wrapper: slugifies `target` and calls `read_record`. Returns `None` if not found.

**Example:**
```python
from little_loops.learning_tests import check_learning_test

rec = check_learning_test("Anthropic SDK streaming")
if rec and rec.status == "proven":
    # assertions are trusted
    pass
```

### resolve_learning_targets

```python
def resolve_learning_targets(
    issue: IssueInfo,
    *,
    llm_call: Callable[[str], str] | None = None,
) -> list[str]
```

Return learning-test targets for an issue (ENH-2319). Returns `issue.learning_tests_required` when the field is non-`None` (field-first, no LLM call). Falls back to JIT extraction via `extract_learning_targets` when the field is `None`. Returns `[]` on `OSError`.

The `is not None` sentinel is intentional: `[]` means "proven empty — no external deps" and must NOT trigger JIT extraction; `None` means "field not yet populated" and triggers it.

### run_learning_gate_for_issue

```python
def run_learning_gate_for_issue(
    issue_path: Path,
    *,
    skip: bool = False,
    cwd: Path | None = None,
    targets: list[str] | None = None,
) -> Literal["passed", "blocked", "skipped"]
```

Invoke the `proof-first-task` loop for an issue and return the gate verdict (ENH-2319). All terminal states exit 0; `"blocked"` is distinguished from `"passed"` by reading the loop state file at `<cwd>/.loops/.running/proof-first-task.state.json`. `skip=True` short-circuits to `"skipped"` without running the loop (honours `--skip-learning-gate`). `targets`, when non-empty, is forwarded as a `targets_csv` context input so `proof-first-task` proves exactly the registered `learning_tests_required` list instead of re-extracting one via `assumption-firewall`; `None`/empty preserves the JIT extraction fallback (ENH-2405).

---

## little_loops.doc_counts

Automated verification that documented counts (commands, agents, skills, loops) match actual file counts in the codebase.

### Data Classes

#### CountResult

```python
@dataclass
class CountResult:
    category: str              # e.g., "commands", "agents", "skills", "loops"
    actual: int                # Actual file count
    documented: int | None     # Documented count (if found)
    file: str | None           # Documentation file path
    line: int | None           # Line number in doc file
    matches: bool              # Whether counts match
```

#### VerificationResult

```python
@dataclass
class VerificationResult:
    total_checked: int                   # Number of counts checked
    mismatches: list[CountResult]        # List of mismatches
    all_match: bool                      # True if all counts match
```

##### Methods

| Method | Description |
|--------|-------------|
| `add_result(result)` | Add a `CountResult` and track mismatches |

#### FixResult

```python
@dataclass
class FixResult:
    fixed_count: int              # Number of counts fixed
    files_modified: list[str]     # Files that were modified
```

### Public Functions

| Function | Purpose |
|----------|---------|
| `count_files` | Count files matching a glob pattern in a directory |
| `extract_count_from_line` | Extract a count number from a documentation line |
| `verify_documentation` | Verify all documented counts against actual file counts |
| `fix_counts` | Auto-fix count mismatches in documentation files |
| `format_result_text` | Format verification result as plain text |
| `format_result_json` | Format verification result as JSON |
| `format_result_markdown` | Format verification result as Markdown |

### verify_documentation

```python
def verify_documentation(
    base_dir: Path | None = None,
) -> VerificationResult
```

Verify all documented counts against actual file counts.

**Parameters:**
- `base_dir` - Base directory path (defaults to current working directory)

**Returns:** `VerificationResult` with all results.

**Example:**
```python
from pathlib import Path
from little_loops.doc_counts import verify_documentation

result = verify_documentation(Path.cwd())
if result.all_match:
    print("All counts match!")
else:
    for m in result.mismatches:
        print(f"{m.category}: documented={m.documented}, actual={m.actual}")
```

---

## little_loops.link_checker

Automated verification that links in markdown files are valid. Supports HTTP/HTTPS URL checking and internal file reference validation.

### Data Classes

#### LinkResult

```python
@dataclass
class LinkResult:
    url: str                    # The URL that was checked
    file: str                   # File containing the link
    line: int                   # Line number where link appears
    status: str                 # "valid", "broken", "timeout", "ignored", "internal"
    error: str | None           # Error message if broken
    link_text: str | None       # The link text from markdown [text](url)
```

#### LinkCheckResult

```python
@dataclass
class LinkCheckResult:
    total_links: int            # Total number of links found
    valid_links: int            # Number of valid links
    broken_links: int           # Number of broken links
    ignored_links: int          # Number of ignored links
    internal_links: int         # Number of internal file references
    results: list[LinkResult]   # Individual link results
```

##### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_errors` | `bool` | `True` if any broken links were found |

### Public Functions

| Function | Purpose |
|----------|---------|
| `extract_links_from_markdown` | Extract all links from markdown content |
| `is_internal_reference` | Check if a URL is an internal file reference |
| `should_ignore_url` | Check if a URL matches ignore patterns |
| `check_url` | Check if a single URL is reachable |
| `check_markdown_links` | Check all markdown files for broken links |
| `load_ignore_patterns` | Load ignore patterns from `.mlc.config.json` |
| `format_result_text` | Format link check result as plain text |
| `format_result_json` | Format link check result as JSON |
| `format_result_markdown` | Format link check result as Markdown |

### check_markdown_links

```python
def check_markdown_links(
    base_dir: Path,
    ignore_patterns: list[str] | None = None,
    timeout: int = 10,
    verbose: bool = False,
) -> LinkCheckResult
```

Check all markdown files for broken links.

**Parameters:**
- `base_dir` - Base directory to search
- `ignore_patterns` - List of regex patterns to ignore (defaults to localhost patterns)
- `timeout` - Request timeout in seconds
- `verbose` - Whether to show progress

**Returns:** `LinkCheckResult` with all findings.

**Example:**
```python
from pathlib import Path
from little_loops.link_checker import check_markdown_links

result = check_markdown_links(Path.cwd())
if result.has_errors:
    for r in result.results:
        if r.status == "broken":
            print(f"Broken: {r.url} at {r.file}:{r.line}")
else:
    print(f"All {result.total_links} links valid!")
```

---

## little_loops.session_log

Session log linking for issue files. Links Claude Code JSONL session files to issue files by appending timestamped log entries.

```python
from little_loops.session_log import (
    parse_session_log,
    count_session_commands,
    get_current_session_jsonl,
    append_session_log_entry,
)
```

### parse_session_log

```python
def parse_session_log(content: str) -> list[str]
```

Extract distinct `/ll:*` command names from the `## Session Log` section, in first-seen order (deduplicated).

**Parameters:**
- `content` - Full text of an issue markdown file

**Returns:** List of distinct command names (e.g. `["/ll:refine-issue", "/ll:ready-issue"]`)

### count_session_commands

```python
def count_session_commands(content: str) -> dict[str, int]
```

Count occurrences of each `/ll:*` command in the `## Session Log` section. Unlike `parse_session_log()`, this does NOT deduplicate — each entry is counted.

**Parameters:**
- `content` - Full text of an issue markdown file

**Returns:** Mapping of command name to occurrence count (e.g. `{"/ll:refine-issue": 3}`)

### get_current_session_jsonl

```python
def get_current_session_jsonl(cwd: Path | None = None) -> Path | None
```

Resolve the active Claude Code session's JSONL file path. Finds the most recently modified `.jsonl` file in the project's Claude Code session directory, excluding agent session files.

**Parameters:**
- `cwd` - Working directory to map. If `None`, uses current directory

**Returns:** `Path` to the most recent JSONL file, or `None` if not found

### append_session_log_entry

```python
def append_session_log_entry(
    issue_path: Path,
    command: str,
    session_jsonl: Path | None = None,
) -> bool
```

Append a session log entry to an issue file. Creates or appends to the `## Session Log` section with command name, ISO timestamp, and session JSONL path.

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `command` - Command name (e.g. `"/ll:manage-issue"`)
- `session_jsonl` - Path to session JSONL file. If `None`, auto-detected via `get_current_session_jsonl()`

**Returns:** `True` if entry was appended, `False` if session could not be resolved

**Example:**

```python
from pathlib import Path
from little_loops.session_log import append_session_log_entry

success = append_session_log_entry(
    Path(".issues/bugs/P1-BUG-001-example.md"),
    "/ll:manage-issue",
)
```

---

## little_loops.text_utils

Text extraction utilities for issue content. Provides shared functions for extracting file paths from markdown issue text, used by `dependency_mapper`, `issue_history`, and other modules that need to identify file references.

### Public Constants

| Constant | Type | Description |
|----------|------|-------------|
| `SOURCE_EXTENSIONS` | `frozenset[str]` | Recognized source file extensions for path filtering |

### Public Functions

| Function | Purpose |
|----------|---------|
| `extract_file_paths` | Extract file paths from issue content |
| `extract_words` | Tokenize text into a set of significant words (3+ chars, stop words removed) |
| `calculate_word_overlap` | Jaccard similarity between two word sets |
| `score_bm25` | BM25 relevance score for a document against a query |

### SOURCE_EXTENSIONS

```python
SOURCE_EXTENSIONS: frozenset[str]
```

A `frozenset` of 24 file extension strings (each with leading dot) considered real source file paths. Used to filter false-positive path matches during extraction.

Includes: `.py`, `.ts`, `.js`, `.tsx`, `.jsx`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini`, `.html`, `.css`, `.scss`, `.sh`, `.bash`, `.sql`, `.go`, `.rs`, `.java`, `.kt`, `.rb`, `.php`

### extract_file_paths

```python
def extract_file_paths(content: str) -> set[str]
```

Extract file paths from issue content. Searches for paths in backtick-quoted references, bold `**File**:` labels, and standalone paths with recognized extensions. Code fence blocks are stripped before extraction to avoid matching example code.

**Parameters:**
- `content` - Issue file content (markdown text)

**Returns:** `set[str]` of file paths found in the content.

**Example:**
```python
from little_loops.text_utils import extract_file_paths

content = """
## Location

**File**: `scripts/little_loops/config.py`

See also `docs/reference/API.md` and scripts/little_loops/state.py:42.
"""

paths = extract_file_paths(content)
print(paths)
# {'scripts/little_loops/config.py', 'docs/reference/API.md', 'scripts/little_loops/state.py'}
```

### extract_words

```python
def extract_words(text: str) -> set[str]
```

Extract significant words from text. Returns lowercase alphabetic words of 3+ characters, excluding common stop words (`the`, `and`, `file`, `code`, `issue`, etc.).

**Parameters:**
- `text` - Input text

**Returns:** `set[str]` of significant words.

### calculate_word_overlap

```python
def calculate_word_overlap(words1: set[str], words2: set[str]) -> float
```

Calculate Jaccard similarity between two word sets: `|intersection| / |union|`.

**Returns:** Float in `[0.0, 1.0]`.

### score_bm25

```python
def score_bm25(
    query_words: set[str],
    doc_words: set[str],
    doc_freq: dict[str, int],
    avg_doc_len: float,
    total_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float
```

BM25 relevance score for a document against a query. Uses Robertson BM25 with IDF smoothing. Since `doc_words` comes from `extract_words()` (a set), term frequency within the document is always 1 for matching terms.

**Parameters:**
- `query_words` - Set of query terms
- `doc_words` - Set of document terms (unique words, from `extract_words`)
- `doc_freq` - Document frequency per term (number of docs containing each term)
- `avg_doc_len` - Average document length in unique words across corpus
- `total_docs` - Total number of documents in corpus
- `k1` - Term frequency saturation parameter (default: `1.5`)
- `b` - Length normalization parameter (default: `0.75`)

**Returns:** Non-negative float. Normalize to `[0, 1)` via `score / (score + 1)` before combining with intersection scores.

**Example:**
```python
from little_loops.text_utils import extract_words, score_bm25

docs = ["session logging added to history CLI", "sprint dependency ordering fixed"]
doc_words_list = [extract_words(d) for d in docs]

# Build corpus stats
doc_freq: dict[str, int] = {}
for words in doc_words_list:
    for word in words:
        doc_freq[word] = doc_freq.get(word, 0) + 1
avg_doc_len = sum(len(w) for w in doc_words_list) / len(doc_words_list)

query = extract_words("session logging")
raw = score_bm25(query, doc_words_list[0], doc_freq=doc_freq, avg_doc_len=avg_doc_len, total_docs=2)
normalized = raw / (raw + 1)  # map to [0, 1)
print(f"BM25 normalized: {normalized:.3f}")
```

---

## little_loops.pii

Regex-based PII detection and redaction utilities for SFT corpus filtering.

```python
from little_loops.pii import detect_pii, redact_pii, apply_pii_action
```

### PII_PATTERNS

```python
PII_PATTERNS: dict[str, re.Pattern[str]]
```

Module-level dict mapping PII type names to their compiled regex patterns.

| Key | Pattern covers |
|-----|---------------|
| `"email"` | Standard email addresses |
| `"phone"` | US phone numbers (with/without country code, parens, dashes, dots) |
| `"ssn"` | Social Security Numbers (``NNN-NN-NNNN`` format) |

### detect_pii

```python
def detect_pii(text: str) -> list[str]
```

Return list of PII type names found in *text*.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Input text to scan |

**Returns**: List of PII type name strings (e.g. `["email", "phone"]`); empty list if none found.

### redact_pii

```python
def redact_pii(text: str) -> str
```

Replace all PII spans in *text* with ``[TYPE]`` placeholders.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Input text to redact |

**Returns**: Text with PII replaced by ``[EMAIL]``, ``[PHONE]``, or ``[SSN]`` placeholders.

### apply_pii_action

```python
def apply_pii_action(example: dict, action: str) -> dict | None
```

Apply ``flag``/``redact``/``discard`` to a formatted SFT example dict.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `example` | `dict` | SFT example dict (Alpaca, ShareGPT, etc.) |
| `action` | `str` | One of ``"flag"``, ``"redact"``, ``"discard"`` |

**Returns**: Modified example dict, or ``None`` for ``"discard"`` when PII is detected.

**Raises**: `ValueError` if *action* is not one of the three supported values.

**Example**

```python
from little_loops.pii import detect_pii, redact_pii, apply_pii_action

text = "Contact john@example.com or call 555-867-5309"
detect_pii(text)    # -> ["email", "phone"]
redact_pii(text)    # -> "Contact [EMAIL] or call [PHONE]"

example = {"instruction": "Email john@example.com", "output": "OK"}
apply_pii_action(example, "flag")     # -> {... "pii_detected": True}
apply_pii_action(example, "redact")   # -> {"instruction": "Email [EMAIL]", ...}
apply_pii_action(example, "discard")  # -> None
```

---

## little_loops.events

Structured event system and EventBus dispatcher for the extension architecture.

> **Event catalog:** For a complete reference of all event types, payload fields, and subsystem namespaces, see [EVENT-SCHEMA.md](EVENT-SCHEMA.md).

```python
from pathlib import Path

from little_loops.events import EventBus, LLEvent
from little_loops.transport import JsonlTransport

bus = EventBus()
bus.register(lambda evt: print(f"Event: {evt['event']}"))
bus.add_transport(JsonlTransport(Path(".ll/events.jsonl")))
bus.emit(LLEvent(type="issue.completed", timestamp="2026-04-02T12:00:00Z", payload={"id": "BUG-001"}).to_dict())
```

### EventCallback

Type alias for event observer callables.

```python
EventCallback = Callable[[dict[str, Any]], None]
```

A callable that accepts a single `dict[str, Any]` argument (the serialized event) and returns `None`. Used as the type for observers registered with `EventBus.register()`.

### LLEvent

Structured event dataclass for the extension system.

```python
@dataclass
class LLEvent:
    type: str                              # Event type identifier (e.g., "issue.completed")
    timestamp: str                         # ISO 8601 timestamp string
    payload: dict[str, Any] = field(default_factory=dict)  # Additional event data
```

#### Methods

```python
def to_dict(self) -> dict[str, Any]
```
Serialize to a flat dictionary. Field names are remapped: `type` becomes `"event"`, `timestamp` becomes `"ts"`, and `payload` keys are spread into the root.

**Returns:** `{"event": self.type, "ts": self.timestamp, **self.payload}`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> LLEvent
```
Deserialize from a flat dictionary. Pops `"event"` (fallback: `"type"`, `"unknown"`) for the type field and `"ts"` (fallback: `"timestamp"`, `""`) for timestamp. Remaining keys become the payload. Operates on a copy of `data`.

```python
@classmethod
def from_raw_event(cls, raw: dict[str, Any]) -> LLEvent
```
Convenience wrapper over `from_dict`. Copies the input dict before parsing so the original is not mutated.

### EventBus

Central dispatcher that fans out events to registered observers and transports.

```python
from little_loops.events import EventBus, LLEvent
from little_loops.transport import JsonlTransport
from pathlib import Path

bus = EventBus()
bus.register(lambda evt: print(evt))
bus.add_transport(JsonlTransport(Path(".ll/events.jsonl")))
bus.emit({"event": "test", "ts": "2026-04-02T00:00:00Z"})
```

#### Constructor

```python
EventBus()
```

Initializes empty observer and transport lists. No parameters.

#### Methods

| Method | Description |
|--------|-------------|
| `register(callback: EventCallback, filter: str \| list[str] \| None = None) -> None` | Append an observer callback with an optional glob filter. `None` (default) receives all events. |
| `unregister(callback: EventCallback) -> None` | Remove an observer by identity. Silently ignores if not found. |
| `add_transport(transport: Transport) -> None` | Register a `Transport` to receive every emitted event. |
| `close_transports() -> None` | Call `close()` on every registered transport, isolating exceptions. |
| `emit(event: dict[str, Any]) -> None` | Fan out event to matching observers, then deliver to every transport via `send()`. Per-observer and per-transport exceptions are caught and logged. |
| `read_events(path: Path) -> list[LLEvent]` | *(static)* Read a JSONL event log file. Returns `[]` if file does not exist. Skips invalid JSON lines. |

#### Filter parameter

The `filter` argument to `register()` accepts a glob pattern string or list of patterns matched against the event's `"event"` key using `fnmatch`:

```python
# Subscribe to issue namespace only
bus.register(my_callback, filter="issue.*")

# Subscribe to multiple namespaces
bus.register(my_callback, filter=["issue.*", "parallel.*"])

# Subscribe to bare FSM event names
bus.register(my_callback, filter=["state_enter", "loop_*"])

# Subscribe to everything (default)
bus.register(my_callback)
```

**Event namespace conventions:**
- `issue.*` — issue lifecycle events (`issue.closed`, `issue.completed`, etc.)
- `state.*` — state manager events (`state.issue_completed`, `state.issue_failed`)
- `parallel.*` — parallel orchestrator events (`parallel.worker_completed`)
- Bare names — FSM executor events (`state_enter`, `loop_start`, `action_start`, etc.)

---

## little_loops.history_reader

Typed read-only query module for `.ll/history.db` (ENH-1752). Provides the common queries that ll skills and agents need to consume the session database without importing ad-hoc SQL into every caller. All functions degrade gracefully: missing/empty/corrupt databases return empty lists, never raise.

> **Session store:** For the write-side schema, `SQLiteTransport`, and backfill functions, see [`little_loops.session_store`](#little_loopssession_store).

```python
from little_loops.history_reader import (
    find_user_corrections,
    recent_file_events,
    search,
    related_issue_events,
    sessions_for_issue,
    lookup_session_metadata,
    conversation_turns,
    recent_skill_events,     # ENH-2460
    summarize_skills,        # ENH-2460
    recent_commit_events,    # ENH-2458
    recent_test_runs,        # ENH-2459
    OrchestrationRun,        # ENH-2492
    recent_orchestration_runs,    # ENH-2492
    aggregate_orchestration_runs, # ENH-2492
    find_session_for_issue_transition,  # ENH-2462
    agent_usage,             # ENH-2497
    recent_tool_events,      # ENH-2497
    LearningTestEvent,       # ENH-2466
    recent_learning_tests,   # ENH-2466
    find_learning_test,      # ENH-2466
    LifecycleEvent,          # ENH-2495
    recent_lifecycle_events, # ENH-2495
    handoff_frequency,       # ENH-2495
    SubagentRun,             # ENH-2505
    subagent_tree,           # ENH-2505
    subagent_retries,        # ENH-2505
    subagent_budget,         # ENH-2505
)
```

### SubagentRun

Dataclass for `subagent_runs` rows — one Task/Agent spawn (ENH-2505). `agent_id` is spawn-local (scoped to `parent_session_id`, not a `sessions.session_id`); a subagent's transcript is a nested file, not a joinable top-level session row.

```python
@dataclass
class SubagentRun:
    ts: str
    parent_session_id: str | None
    agent_id: str | None
    agent_type: str | None
    agent_transcript_path: str | None
    started_at: str | None
    ended_at: str | None
    status: str | None
```

```python
def subagent_tree(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> list[SubagentRun]
def subagent_retries(agent_type: str, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict]
def subagent_budget(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> dict | None
```

`subagent_tree()` returns the direct `agent_id` spawns for a parent session (no grandchild recursion — that requires re-parsing each `agent_transcript_path`, not a SQL join). `subagent_retries()` returns per-parent re-spawn counts for a given `agent_type`, restricted to parents that spawned it more than once (the "oscillation" signal). `subagent_budget()` returns `{"spawn_count", "total_duration_s"}` for a parent session (the "burn budget" signal), or `None` when no rows exist.

### UserCorrection

Dataclass for user correction rows from the `user_corrections` table.

```python
@dataclass
class UserCorrection:
    ts: str
    session_id: str | None
    content: str
    source: str | None
```

### FileEvent

Dataclass for file event rows from the `file_events` table.

```python
@dataclass
class FileEvent:
    ts: str
    session_id: str | None
    path: str | None
    op: str | None
    issue_id: str | None
    git_sha: str | None
```

### SearchResult

Dataclass for FTS5 search results from the `search_index` virtual table.

```python
@dataclass
class SearchResult:
    content: str
    kind: str
    ref: str
    anchor: str
    ts: str
    score: float
```

### IssueEvent

Dataclass for issue event rows from the `issue_events` table.

```python
@dataclass
class IssueEvent:
    ts: str
    issue_id: str | None
    transition: str | None
    discovered_by: str | None
    issue_type: str | None
    priority: str | None
```

### SessionRef

Dataclass for `issue_sessions` view rows (ENH-1711). A session that co-occurred with an issue's active period.

```python
@dataclass
class SessionRef:
    issue_id: str | None
    session_id: str | None
    jsonl_path: str | None
    first_message_ts: str | None
    last_message_ts: str | None
```

### find_user_corrections

```python
def find_user_corrections(
    topic: str,
    *,
    limit: int = 10,
    include_stale: bool = False,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[UserCorrection]
```

Return user corrections whose content matches *topic* (LIKE search).

**Parameters:**
- `topic` — substring to match against the `content` column (LIKE `%topic%`)
- `limit` — maximum number of rows to return (default: 10)
- `include_stale` — if `False` (default), excludes rows older than 30 days
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `UserCorrection` instances ordered by `ts DESC`. Returns `[]` if the database is unavailable.

### recent_file_events

```python
def recent_file_events(
    path: str,
    *,
    limit: int = 10,
    include_stale: bool = False,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[FileEvent]
```

Return recent file events for *path* (LIKE pattern match).

**Parameters:**
- `path` — substring to match against the `path` column (LIKE `%path%`)
- `limit` — maximum number of rows to return (default: 10)
- `include_stale` — if `False` (default), excludes rows older than 30 days
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `FileEvent` instances ordered by `ts DESC`. Returns `[]` if the database is unavailable.

### search

```python
def search(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 10,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SearchResult]
```

FTS5 full-text search with optional *kind* filter.

**Parameters:**
- `query` — search string, matched as a literal FTS5 phrase (BM25-ranked results). The query is quoted via `fts_phrase()`, so hyphenated issue IDs (e.g. `BUG-490`) and other FTS5 operator characters match literally instead of being parsed as expressions (BUG-2651).
- `kind` — optional filter: `tool`, `file`, `issue`, `loop`, `correction`, `message`
- `limit` — maximum number of rows to return (default: 10)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SearchResult` instances ordered by BM25 score. Returns `[]` if the database is unavailable or the FTS5 query syntax is invalid.

### related_issue_events

```python
def related_issue_events(
    issue_id: str,
    *,
    session_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[IssueEvent]
```

Return issue events for *issue_id*, ordered by most recent first. When `session_id` is given, only events recorded with that exact authoritative session ID are returned (ENH-2462).

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1752"`)
- `session_id` — optional exact `issue_events.session_id` filter (ENH-2462)
- `limit` — maximum number of rows to return (default: 20)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `IssueEvent` instances ordered by `ts DESC` (each carries `session_id`, `None` for legacy rows). Returns `[]` if the database is unavailable.

### find_session_for_issue_transition

```python
def find_session_for_issue_transition(
    issue_id: str,
    transition: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None
```

Return the authoritative `session_id` recorded for an exact issue transition (ENH-2462), or `None` for legacy pre-v16 rows, transitions emitted outside a session-known context, or unknown transitions.

### recent_skill_events

```python
def recent_skill_events(
    skill_name: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SkillEvent]
```

Return recent `skill_events` rows, newest first, including the v15 completion columns (`exit_code`, `success`, `duration_ms` — `None` for dispatch-only rows) (ENH-2460).

### summarize_skills

```python
def summarize_skills(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-skill rollup powering `ll-session skill-stats` (ENH-2460): returns dicts with `skill_name`, `invocations`, `completions`, `successes`, `success_rate` (over completion-carrying rows only; `None` when no completions), and `avg_duration_ms`, sorted by invocation count descending.

### agent_usage

```python
def agent_usage(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-agent rollup of `Task`-tool subagent spawn counts (ENH-2497): returns dicts with `agent_type` and `invocations`, filtered to `tool_name='Task'` rows with a non-NULL `agent_type` (the v24 `tool_events` column), sorted by invocation count descending. Returns `[]` on a missing/unreadable DB.

### recent_tool_events

```python
def recent_tool_events(
    agent_type: str | None = None,
    mcp_server: str | None = None,
    mcp_tool: str | None = None,
    mcp_outcome: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Return recent `tool_events` rows, newest first, optionally filtered to a single `agent_type` (ENH-2497) and/or `mcp_server`/`mcp_tool`/`mcp_outcome` (ENH-2511, the v25 `tool_events` columns). Returns `[]` on a missing/unreadable DB.

### mcp_server_usage

```python
def mcp_server_usage(
    server: str | None = None,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-MCP-server rollup of invocations/completions/success rate/average latency (ENH-2511), sourced from `tool_events.mcp_server`/`mcp_outcome`/`latency_ms`. Returns `[]` on a missing/unreadable DB.

### mcp_failure_rate

```python
def mcp_failure_rate(
    server: str | None = None,
    tool: str | None = None,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-server/tool MCP failure-rate rollup (ENH-2511): counts of invocations and `mcp_outcome='error'` rows, grouped by `(mcp_server, mcp_tool)`. Returns `[]` on a missing/unreadable DB.

### cost_attribution

```python
def cost_attribution(
    group_by: str = "gen_ai.invocation.id",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-`group_by` token/cost rollup over `usage_events` (FEAT-2478). `group_by` is an
OTel attribute name (`gen_ai.invocation.id` / `gen_ai.provider.vendor`) or a raw
column (`session_id` / `model` / `state` / `invocation_id` / `provider_vendor`); any
other value raises `ValueError` (the `GROUP BY` clause is whitelisted). Each returned
dict carries the group key plus the summed token counts under the canonical dotted
OTel names (`gen_ai.usage.input_tokens`, `gen_ai.usage.cache_read.input_tokens`, …),
`cost_usd`, and `invocations`, so a `GROUP BY gen_ai.invocation.id` rollup matches raw
`result`-event `usage` totals row-for-row.

### recent_commit_events

```python
def recent_commit_events(
    *,
    branch: str | None = None,
    issue_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[CommitEvent]
```

Return recent `commit_events` rows, newest first, optionally filtered by exact `branch` and/or `issue_id` (ENH-2458). `CommitEvent` carries `ts`, `commit_sha`, `parent_sha`, `message`, `author`, `branch`, `issue_id`, and `files_json` (JSON array of touched paths).

### recent_test_runs

```python
def recent_test_runs(
    *,
    branch: str | None = None,
    head_sha: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[RunEvent]
```

Return recent `test_run_events` rows, newest first, optionally filtered (ENH-2459). `RunEvent` exposes a derived `pass_rate` property (`passed / total`, `None` when `total` is 0/unknown).

### OrchestrationRun / recent_orchestration_runs / aggregate_orchestration_runs

```python
@dataclass
class OrchestrationRun:
    run_id: str
    driver: str
    issue_id: str
    status: str
    failure_reason: str | None
    duration_s: float | None
    wave: str | None
    pr_url: str | None
    started_at: str | None
    ended_at: str | None
    head_sha: str | None
    branch: str | None


def recent_orchestration_runs(
    driver: str | None = None,
    issue_id: str | None = None,
    *,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[OrchestrationRun]


def aggregate_orchestration_runs(
    group_by: Literal["driver", "issue_id", "status"] = "driver",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Read per-issue outcomes written by `ll-auto`, `ll-parallel`, and `ll-sprint` (ENH-2492). The recent reader filters by exact driver/issue and optional completion-time lower bound. The aggregate reader returns run count, completed count, success rate, and average duration for a fixed, SQL-safe grouping dimension. Both return `[]` on unavailable or pre-v22 databases.

### LoopRun / recent_loop_runs / find_loop_run / aggregate_loop_runs

```python
@dataclass
class LoopRun:
    run_id: str
    loop_name: str
    started_at: str | None
    ended_at: str | None
    final_state: str | None
    iterations: int | None
    terminated_by: str | None
    error: str | None
    evaluator_score: float | None
    diagnostics_path: str | None
    head_sha: str | None
    branch: str | None


def recent_loop_runs(
    *,
    loop_name: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LoopRun]


def find_loop_run(run_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> LoopRun | None


def aggregate_loop_runs(
    group_by: Literal["loop_name", "terminated_by"] = "loop_name",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Read per-run summaries written by `FSMExecutor._finish()` (ENH-2463). `recent_loop_runs()` filters by exact `loop_name` and optional completion-time lower bound; `find_loop_run()` looks up a single row by its archive-time `run_id`; `aggregate_loop_runs()` returns run count and mean iteration count for a fixed grouping dimension. All three return `[]`/`None` on unavailable or pre-v23 databases. Known v1 coverage gap: runs that exit via handoff or forced archive (never reaching `_finish()`) have no row.

### LearningTestEvent / recent_learning_tests / find_learning_test

```python
@dataclass
class LearningTestEvent:
    ts: str
    record_id: str
    target: str | None
    status: str | None
    assertions_json: str | None
    date: str | None
    raw_output_path: str | None


def recent_learning_tests(
    *,
    status: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LearningTestEvent]


def find_learning_test(target: str, *, db: Path | str = DEFAULT_DB_PATH) -> LearningTestEvent | None
```

Read the `learning_test_events` mirror of the Learning Test Registry (`.ll/learning-tests/*.md`, ENH-2466). `LearningTestEvent` is the DB-side mirror row — not to be confused with `little_loops.learning_tests.LearnTestRecord`, the registry-file dataclass it mirrors. `recent_learning_tests()` filters by exact `status`; `find_learning_test()` looks up a single row by `target` (slugified to `record_id` internally). Both return `[]`/`None` on unavailable or pre-v26 databases.

### LifecycleEvent / recent_lifecycle_events / handoff_frequency

```python
@dataclass
class LifecycleEvent:
    id: int
    ts: str
    session_id: str | None
    event: str
    detail: dict | None
    head_sha: str | None
    branch: str | None


def recent_lifecycle_events(
    *,
    event: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LifecycleEvent]


def handoff_frequency(*, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> int
```

Read the `session_lifecycle_events` table — session-lifecycle/handoff transitions written by `record_session_lifecycle_event()` (ENH-2495). `LifecycleEvent.detail` is parsed from the stored JSON `TEXT` column into a `dict` (unlike `CommitEvent.files_json`/`LearningTestEvent.assertions_json`, which stay raw strings). `recent_lifecycle_events()` filters by exact `event` discriminator and/or `ts >= since`. `handoff_frequency()` counts `handoff_needed` rows, optionally since a timestamp — the metric for "how often does this project hit the context-handoff threshold?". Both return `[]`/`0` on unavailable databases.

### sessions_for_issue

```python
def sessions_for_issue(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SessionRef]
```

Return sessions that co-occurred with *issue_id*'s active period.

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1752"`)
- `limit` — maximum number of rows to return (default: 20)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SessionRef` instances ordered by `first_message_ts DESC`. Queries the `issue_sessions` VIEW (v5 schema migration, ENH-1711). Returns `[]` when the view is absent (pre-v5 schema), the issue has no recorded sessions, or the database is unavailable.

### lookup_session_metadata

```python
def lookup_session_metadata(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict
```

Return session-quality metadata for a session ID (ENH-1943).

**Parameters:**
- `session_id` — the session UUID to query
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** `dict` with keys `has_corrections` (bool), `issue_outcome` (str|None), `tool_count` (int), `files_modified` (int), and `loop_outcome` (None). `issue_outcome` is the transition value when an issue was closed in this session; `None` if no issue was closed. `loop_outcome` is always `None` — `loop_events` has no `session_id` column, so loop outcomes cannot be joined to sessions without a schema change. Returns empty `{}` when the DB is missing, empty, lacks relevant tables, or any query raises a SQL error. All computed fields default to their zero values when the session ID has no matching rows.

**Used by:** `sft-corpus` loop (enrich state) to batch-join session-quality signals for SFT corpus filtering.

### conversation_turns

```python
def conversation_turns(
    db_path: Path | str,
    since: datetime | None = None,
    context_window: int = 3,
) -> list[list[tuple[str, str]]]
```

Return conversation turn-pair windows from `history.db` (ENH-1942).

Queries `message_events` and `assistant_messages` (requires schema ≥ v11), pairs user messages with their assistant responses via temporal adjacency, and groups them into sliding windows of `context_window` turn-pairs each.

**Parameters:**
- `db_path` — path to `history.db`
- `since` — only include turns where the user message timestamp is >= this value (optional)
- `context_window` — number of (user, assistant) turn-pairs per output window (default: 3)

**Returns:** List of conversation windows; each window is a `list[tuple[str, str]]` alternating between `("user", text)` and `("assistant", text)`. Returns `[]` when the database is missing, empty, predates schema v11 (no `assistant_messages` table), no turn-pairs match the `since` filter, or any query raises a SQL error.

**Temporal adjacency pairing:** Each assistant message (from `assistant_messages`) is paired with the immediately preceding user message in the same session. Assistant messages that fall between user message A and user message B are assigned to user message A. Multiple assistant messages following a single user message are joined with `"\n\n"`.

**Sliding windows:** N turn-pairs produce `max(1, N - context_window + 1)` output windows. A single turn-pair session still produces 1 window (of 1 pair). Windows are emitted in chronological order, each covering `context_window` consecutive turn-pairs; adjacent windows overlap by `context_window - 1` pairs.

**Relationship to `extract_conversation_turns()`:** This function is the DB query path; `extract_conversation_turns()` in `user_messages.py` calls this function first (DB-first, `reader="auto"` mode) and falls back to `_extract_turn_pairs()` (JSONL parsing) when the DB is unavailable or returns no results. The temporal adjacency algorithm is identical in both paths; only the data source differs (SQLite vs. JSONL log files).

**Used by:** `extract_conversation_turns()` in `user_messages.py`, which is called by `ll-messages --sft-format` to extract training examples from either the session DB or raw JSONL logs.

### condensed_nodes_for_issue

```python
def condensed_nodes_for_issue(
    issue_id: str,
    *,
    limit: int = 3,
    node_char_cap: int = 500,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SummaryNode]
```

Return level-0 condensed `summary_nodes` for an issue's sessions (ENH-2231).

Joins the `issue_sessions` VIEW to `summary_nodes` filtering for `kind='condensed'` and `level=0` (per-session condensed nodes, one per session). Returns nodes newest-first, limited to `limit`. Each node's `content` is truncated to `node_char_cap` characters before returning.

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-2231"`)
- `limit` — maximum number of condensed nodes to return (default: 3)
- `node_char_cap` — maximum characters per node's `content` field (default: 500)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SummaryNode` objects (newest first). Returns `[]` when the DB is absent, the issue has no recorded sessions, no condensed nodes have been generated (requires `history.compaction.enabled: true`), or any query raises a SQL error.

**Integration:** Called by `ll-history-context <issue_id>` when `history.compaction.enabled` is `true` to inject a `## Prior Work (condensed)` section. Output is byte-identical when compaction is disabled or no level-0 nodes exist for the issue's sessions. See ENH-2231 and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` for the DAG architecture.

**FEAT-2598 note:** for sessions that cross the 7,500-token soft threshold, `session_store._maybe_soft_threshold_summary()` may rewrite this same row's `content` into the 6-section cookbook schema (User Intent / Completed Work / Errors & Corrections / Active Work / Pending Tasks / Key References) — the row's `kind`/`level`/identity are unchanged, so this function's query and truncation behavior are unaffected.

## little_loops.compaction

Session-memory compaction: StreamingLLM eviction + 6-section schema (FEAT-2598). Extends the LCM compaction surface in `session_store` with two complementary passes: instant structural eviction (no LLM cost, always-on) and 6-section semantic summarization (gated on `history.compaction.enabled`, fires in a background thread at the soft token threshold).

### evict_sink_and_window

```python
def evict_sink_and_window(
    messages: list[dict],
    sink_n: int = 4,
    window_n: int = 20,
) -> list[dict]
```

StreamingLLM-style eviction: keeps the first `sink_n` + last `window_n` messages, dropping the middle. Operates at message granularity (not token/KV-cache granularity). `system`-role messages (system prompt / CLAUDE.md blocks) are preserved unconditionally and excluded from the sink/window accounting. Returns the original list unchanged when there is nothing to prune.

### is_valid_cutoff / compute_goal_tokens / select_sliding_window

```python
def is_valid_cutoff(messages: list[dict], index: int) -> bool
def compute_goal_tokens(model: str | None = None, sliding_window_percentage: float = 0.3, override: int | None = None) -> int
def select_sliding_window(messages: list[dict], model: str | None = None, sliding_window_percentage: float = 0.3, override: int | None = None) -> list[dict]
```

Letta-style sliding-window selection. `compute_goal_tokens` implements `goal_tokens = (1 - sliding_window_percentage) * context_window` using `context_window.context_window_for()`. `select_sliding_window` selects the most recent messages fitting within that budget (inflated by `APPROX_TOKEN_SAFETY_MARGIN = 1.3`, the project's byte/4 token-estimate heuristic), snapped to a valid cutoff via `is_valid_cutoff` (a user-turn boundary, avoiding a split mid assistant/tool-call sequence).

### summarize_6_section

```python
def summarize_6_section(
    messages: list[str] | list[dict],
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str
```

Produces a 6-section cookbook-style summary (User Intent / Completed Work / Errors & Corrections / Active Work / Pending Tasks / Key References) via `session_store._call_llm_for_summary` (same sanctioned host-CLI abstraction `_summarize_block` uses). Falls back to a deterministic empty-section skeleton if the LLM call fails, so a well-shaped summary is always produced.

### CompactResult / compact_result_for_session

```python
@dataclass
class CompactResult:
    summary_message: str | None
    compacted_messages: list[int] = field(default_factory=list)
    summary_text: str | None = None
    context_token_estimate: int = 0

def compact_result_for_session(session_id: str, db: Path | str) -> CompactResult | None
```

`CompactResult` is a thin dataclass wrapper over existing `summary_nodes`/`summary_spans` rows — no schema change. `compact_result_for_session` returns `None` when the session has no per-session condensed node (`kind='condensed'`, `level=0`) yet.

**CLI:** `ll-compact-session SESSION_ID [--db PATH] [--json]` manually triggers `session_store.compact_session()` for one session and prints the resulting `CompactResult`. Distinct from `ll-session compact`, which sweeps the separate *retention* axis (`kind='retention'` `raw_events` summarization, ENH-1906/ENH-2581).

### issue_effort

```python
def issue_effort(
    issue_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None
```

Return per-issue effort: session count and cycle time (ENH-1905).

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1905"`)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** `{"session_count": int, "cycle_time_days": float | None}` or `None` when the DB is absent or the issue has no recorded sessions. Uses a direct aggregate query over `issue_sessions` (no LIMIT cap) for accurate `cycle_time_days` across many sessions.

### recent_issue_velocity

```python
def recent_issue_velocity(
    limit: int = 10,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Return effort data for recently completed issues (ENH-1905).

**Parameters:**
- `limit` — maximum number of recently completed issues to include (default: 10, configurable via `history.velocity_window`)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `{"issue_id": str, "session_count": int, "cycle_time_days": float | None}` dicts ordered by `completed_at DESC`. Returns `[]` when the DB is absent or no completed issues exist.

### SectionProvider

Config-addressable digest section with query and render logic (ENH-1907). The three v1 providers (`touched_files`, `completed_issues`, `recurring_corrections`) are registered in `SECTION_PROVIDERS`.

```python
@dataclass(frozen=True)
class SectionProvider:
    name: str           # config-addressable key (e.g. "touched_files")
    query: Callable     # (conn, *, cutoff: str, cap: int) -> list
    default_cap: int    # max rows returned by this provider
    render: Callable    # (rows: list) -> list[str]  markdown lines
```

### ProjectDigest

Aggregated project-context snapshot from `history.db` (ENH-1907).

```python
@dataclass
class ProjectDigest:
    sections: list[tuple[str, list[str]]]  # [(name, markdown_lines), ...]
    days: int = 7

    @property
    def empty(self) -> bool: ...
```

### SECTION_PROVIDERS

Registry of v1 section providers. Keys: `"touched_files"`, `"completed_issues"`, `"recurring_corrections"`. Future providers (effort/velocity, evolution triggers) register here without requiring a formatter rewrite.

```python
SECTION_PROVIDERS: dict[str, SectionProvider]
```

### project_digest

```python
def project_digest(
    db_path: Path,
    *,
    days: int = 7,
    sections: list[str] | None = None,
) -> ProjectDigest
```

Aggregate a project-wide context snapshot from `history.db`. Returns a `ProjectDigest` with `.empty == True` on missing/empty/stale DB. `sections=None` or `sections=[]` renders all registered providers in registry order; a non-empty list restricts and orders the output. Degrades gracefully — never raises.

### render_project_context

```python
def render_project_context(
    digest: ProjectDigest,
    *,
    char_cap: int = 1200,
    days: int | None = None,
) -> str
```

Render a `<project_context>` block from *digest*, capped at *char_cap* chars. Returns `""` when the digest is empty. Truncates with a `+N more` tail when content would exceed *char_cap*.

---

## little_loops.compression

In-house, zero-dependency heuristic prompt compressor (FEAT-2675, EPIC-2456 Tier 3). Three extractive passes over a `list[dict]` (`role`/`content`) message list plus a `compress()` entry point gated on a window-relative trigger, and a `compress_action_text()` string adapter used by `FSMExecutor._run_action()`. Token estimates use the project's `len(text) // 4` convention (no BPE tokenizer). The LLMLingua-gated benchmark comparator is FEAT-2676.

### drop_stale_tool_results / dedupe_stable_system_blocks / tail_truncate_assistant_turns

```python
def drop_stale_tool_results(messages: list[dict], max_age_turns: int = 5) -> list[dict]
def dedupe_stable_system_blocks(messages: list[dict]) -> tuple[list[dict], list[int]]
def tail_truncate_assistant_turns(messages: list[dict], max_n: int = 8) -> list[dict]
```

The three passes. `drop_stale_tool_results` drops `role=="tool"` messages older than `max_age_turns` user turns (measured from the last user turn), preserving `system` rows unconditionally. `dedupe_stable_system_blocks` keeps the first occurrence of each unique `system` block and returns `(deduped, cache_control_candidates)` where the second element lists output-list indices of surviving repeated blocks — flagged for the future F1 `cache_control` child; no marking happens here. `tail_truncate_assistant_turns` keeps only the most recent `max_n` `assistant` messages, leaving other roles untouched.

### compress / CompressedResult

```python
@dataclass
class CompressedResult:
    messages: list[dict]
    original_tokens: int
    compressed_tokens: int
    cache_control_candidates: list[int] = field(default_factory=list)
    triggered: bool = False
    @property
    def reduction_ratio(self) -> float: ...

def compress(
    messages: list[dict],
    context_window: int | None = None,
    trigger_pct: float = 0.4,
    trigger_tokens: int | None = None,
    max_tool_result_age_turns: int = 5,
    max_assistant_tail_turns: int = 8,
) -> CompressedResult
```

Runs the three passes in order behind an effective trigger: the lower of `trigger_pct * context_window` (when the window is known) and `trigger_tokens` (when set). Below the trigger, returns the messages unchanged with `triggered=False`. When neither trigger applies (both `None`), the passes always run — the mode the locked-trace reduction measurement relies on.

### compress_action_text

```python
def compress_action_text(text: str, *, model: str | None = None, context_window: int | None = None,
                         trigger_pct: float = 0.4, trigger_tokens: int | None = None,
                         max_tool_result_age_turns: int = 5, max_assistant_tail_turns: int = 8) -> str
```

Executor string adapter. Resolves the context window from `model` via `context_window.context_window_for()` when not given. Below the trigger, or when `text` is not a JSON message list, returns `text` **byte-identical**; above the trigger it compresses the parsed message list and re-serializes. This keeps arbitrary prose prompts unmodified while compressing the motivating case — loops re-embedding captured message-list JSON.

---

## little_loops.cache_marking_oracle

Cache-marking cost oracle (FEAT-2673, EPIC-2456 F1 — Goal #3). Decides which stable prompt blocks (system / tool / stable-skill) are safe to mark with `cache_control: {"type": "ephemeral", ...}` without risking the unamortized 1.25x write premium (Anthropic prompt caching: writes cost 1.25x, reads cost 0.1x — marking a block that's never reused is a pure 1.25x loss). Two independent gates must both pass: (1) a per-model **cacheable-prefix minimum** (1024 tokens for Sonnet, 4096 for Opus; unknown models fall back to the conservative Opus floor), and (2) a **reuse-stability signal** from `little_loops.prompts.fragment_store.FragmentStore` (FEAT-2671) — a block is only marked once its content-hash key has already been observed at least once, so the oracle never pays the write premium on a fragment that's never reused. `require_repeat=False` disables gate 2 for callers with a stronger external stability signal.

```python
from little_loops.cache_marking_oracle import (
    CacheMarkingDecision,       # frozen dataclass: should_mark: bool, reason: str
    CACHEABLE_PREFIX_MINIMUMS,  # {"sonnet": 1024, "opus": 4096}
    decide_cache_marking,
)

def decide_cache_marking(
    *,
    block_text: str,
    fragment_key: str,
    fragment_store: FragmentStore,
    model: str = "sonnet",
    require_repeat: bool = True,
) -> CacheMarkingDecision: ...
```

`fragment_store` is consulted read-only via `.get()` — it does not record an observation; callers own the `put()` lifecycle. Token estimation uses the project-wide `len(text) // 4` convention (no BPE tokenizer in the codebase). Never raises.

---

## little_loops.prompts

Content-hash fragment store (FEAT-2671, EPIC-2456 F1-prereq a). Computes a stable SHA-256 key over the three stable prompt fragments — skill body, system prompt, and tool definitions — and tracks whether each observed key repeats a prior invocation. Wired read-only into `FSMExecutor._run_action()` (prompt-mode actions only, measured on the pre-interpolation `action_template` plus `state.agent`/`state.tools`), so it never changes the emitted action. Gives the F1 cache-marking oracle (FEAT-2673) a cheap, deterministic stability signal: a hit means the fragment triple was byte-identical to an earlier call, so marking it `cache_control: ephemeral` would amortize real reads instead of paying an unamortized 1.25x write premium.

```python
from little_loops.prompts import FragmentStore, fragment_key

def fragment_key(skill_body: str, system_prompt: str | None, tool_definitions: list[str] | None) -> str

class FragmentStore:
    hits: int
    misses: int
    def get(self, key: str) -> bool: ...     # True if key was observed before
    def put(self, key: str) -> bool: ...     # records the observation; returns True on a repeat (hit)
    @property
    def hit_rate_pct(self) -> float: ...
```

`fragment_key()` hashes `json.dumps({"skill_body": ..., "system_prompt": ..., "tool_definitions": ...}, sort_keys=True, default=str)` via SHA-256, returning the full 64-char hex digest (unlike `session_store._hash_args()`'s `[:16]` truncation — this is a stability/equality signal, not a storage key needing brevity). `FragmentStore` is a small in-memory `get`/`put` store with a hit counter; `put()` is a miss the first time a key is seen and a hit on every repeat.

---

## little_loops.session_store

Unified SQLite session store for `.ll/history.db`. Current schema version: **28**. All write-side helpers degrade gracefully and are safe to call on every session start via `ensure_db()`. The DB path resolves through a single precedence chain (ENH-2623): the `LL_HISTORY_DB` env var, then the `history.db_path` config key, then the default `.ll/history.db` — applied to default-shaped paths only; a deliberate explicit path is honored verbatim.

```python
from little_loops.session_store import (
    SCHEMA_VERSION,        # 28
    VALID_KINDS,           # tuple of valid recent()/search --kind values — single source (ENH-2581)
    ensure_db,             # create/migrate the DB
    connect,               # open a write-capable connection
    record_correction,     # write a user_corrections row
    record_skill_event,    # write a skill_events row (dispatch-time; completion columns NULL)
    skill_event_context,   # ctx manager: INSERT on enter, UPDATE exit_code/success/duration_ms on exit (ENH-2460)
    record_commit_event,   # write a commit_events row; issue_id inferred from message/branch (ENH-2458)
    record_test_run_event, # write a test_run_events row (ENH-2459)
    record_orchestration_run, # UPSERT one per-issue batch outcome (ENH-2492)
    record_loop_run_summary, # write a loop_runs row (ENH-2463)
    update_loop_run_diagnostics, # link a diagnostics artifact to its loop_runs row (ENH-2463)
    record_learning_test_event, # UPSERT one learning_test_events row (ENH-2466)
    record_session_lifecycle_event, # write a session_lifecycle_events row (ENH-2495)
    record_subagent_run_start, # write a running subagent_runs row from SubagentStart (ENH-2505)
    record_subagent_run_stop, # UPDATE ended_at/status/agent_transcript_path from SubagentStop (ENH-2505)
    record_retirement,     # mark a correction cluster as addressed (ENH-2046)
    list_retirements,      # return all correction_retirements rows (ENH-2046)
    backfill_raw_events,   # ingest JSONL lines into raw_events only (ENH-2581)
    rebuild,               # wipe+re-derive the JSONL-derived cache tables from raw_events (ENH-2581)
    compact,               # sweep old raw_events into retention summary_nodes (ENH-2581)
    prune,                 # delete compacted raw_events rows and VACUUM (ENH-2581)
)
```

### raw_events / rebuild / compact (ENH-2581)

`raw_events` is the source of truth for the JSONL-derived cache tables (`tool_events`, `message_events`, `assistant_messages`, `skill_events`, `sessions`): one row per JSONL line, storing both the verbatim `raw_line` and its parsed fields (`ts`, `session_id`, `host`, `source_path`, `line_no`, `event_type`). `backfill()`/`backfill_incremental()` now ingest into `raw_events` only — pass `also_rebuild=True` to also materialize the cache tables in the same call.

```python
def _iter_events(source: list[Path] | sqlite3.Cursor) -> Generator[tuple[str, str], None, None]
```

Dispatch helper letting the JSONL-derived `_backfill_*` functions (`_backfill_sessions`, `_backfill_tool_events`, `_backfill_usage_events`, `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_skill_events`) accept either a legacy `list[Path]` (re-reads files line-by-line) or a `raw_events` cursor selecting `(raw_line, source_path)` — the mechanism `rebuild()` uses to replay previously-ingested lines without touching the filesystem.

```python
def rebuild(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    max_sessions: int | None = None,
) -> dict[str, int]
```

Wipes `tool_events`, `message_events`, `assistant_messages`, `skill_events`, `sessions`, `user_corrections`, `summary_nodes`, `summary_spans`, and the `search_index` rows for `kind in ('tool', 'message', 'skill', 'correction')`, then re-derives them by replaying every `raw_events` row through `_iter_events()`. Idempotent. Updates the `last_rebuild_version` meta key to `SCHEMA_VERSION`. Issue/loop/commit/cli/file/test_run/orchestration tables are outside `raw_events`'s scope and are left untouched — no re-derivation path exists for them.

```python
def compact(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    and_prune: bool = False,
) -> dict[str, int]
```

Sweeps `raw_events` rows older than `analytics.retention.raw_event_max_age_days` (default 90) that aren't yet `compacted`, groups them by `session_id`, and inserts one `kind='retention'` `summary_nodes` row per session — a deterministic one-liner (no host-CLI call), distinct from the LLM-backed `history.compaction` feature's `kind='condensed'` nodes so the two features' dedup indexes never collide. Marks the swept rows `compacted=1` with `summary_node_id` set. `and_prune=True` also calls `prune()` afterward.

`prune()` now deletes only `raw_events` rows already marked `compacted=1` past the cutoff (previously it deleted directly from `tool_events`/`cli_events`/`file_events`/`message_events` and never touched `search_index`, leaving stale FTS rows behind a since-deleted event — the "FTS5 leak"). Because `rebuild()` always wipes+re-populates `search_index` from current cache-table state, running `rebuild()` after a `prune()` brings FTS row counts back in sync.

### skill_event_context

```python
@contextmanager
def skill_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    skill_name: str = "",
    args: str = "",
    config: dict | None = None,
) -> Generator[SkillEventCompletion, None, None]
```

Skill-host analogue of `cli_event_context()` (ENH-2460): inserts a `skill_events` row on enter and updates `exit_code`, `success`, and `duration_ms` on exit. Yields a mutable `SkillEventCompletion` handle — hosts that observe a concrete process exit code (e.g. `ll-action invoke`) set `completion.exit_code` before the block exits; otherwise a clean exit records `exit_code=0, success=1` and a raise records `exit_code=1, success=0`. Best-effort per the EPIC-1707 contract: a missing/locked database never blocks the wrapped skill body.

### record_commit_event

```python
def record_commit_event(
    db_path: Path | str,
    commit_sha: str,
    message: str,
    *,
    author: str | None = None,
    branch: str | None = None,
    issue_id: str | None = None,
    files: Sequence[str] | None = None,
    parent_sha: str | None = None,
    ts: str | None = None,
    config: dict | None = None,
) -> bool
```

Write one `commit_events` row and index it in `search_index` with `kind="commit"` (ENH-2458). `issue_id` is inferred from the message (`Closes/Fixes/Resolves/Issue:` references, bare `TYPE-NNN` tokens) and branch naming (`feat/ENH-2458-*`) when not given. Idempotent via `INSERT OR IGNORE` on the `commit_sha` UNIQUE constraint; returns `True` when a new row was inserted. Producers: the `hooks/scripts/record-commit-post-commit` git hook (via `little_loops.hooks.post_commit.record_head_commit()`) and `ll-session backfill`, which walks `git log --all`.

### record_test_run_event

```python
def record_test_run_event(
    db_path: Path | str,
    *,
    ts: str,
    ended_at: str | None = None,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    errored: int = 0,
    skipped: int = 0,
    duration_s: float | None = None,
    failing_names: Sequence[str] | None = None,
    env_label: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    command: str | None = None,
    config: dict | None = None,
) -> None
```

Write one `test_run_events` row and index it in `search_index` with `kind="test_run"` (ENH-2459). `failing_names` (pytest node IDs) are stored as a JSON array and fed into FTS so failing-test fragments are searchable. The primary producer is the `little_loops.pytest_history_plugin` pytest11 plugin (auto-registered via entry point; opt out with `PYTEST_DISABLE_PLUGIN_LL_HISTORY=1`); it only activates when the invocation directory contains `.ll/` or `LL_HISTORY_DB` is set, records from the xdist controller only, and swallows all write errors.

### record_orchestration_run

```python
def record_orchestration_run(
    db_path: Path | str,
    *,
    run_id: str,
    driver: str,
    issue_id: str,
    status: str,
    failure_reason: str | None = None,
    duration_s: float | None = None,
    wave: str | None = None,
    pr_url: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    config: dict | None = None,
) -> bool
```

UPSERT one `orchestration_runs` row per `(run_id, issue_id)` and replace its matching FTS row (ENH-2492). A top-level `ll-auto`, `ll-parallel`, or `ll-sprint` invocation reuses one opaque UUID for all of its issues and retries; the final retry therefore replaces the initial failure rather than adding a duplicate. Producers guard calls with `contextlib.suppress(Exception)` so history failures never alter orchestration behavior.

### record_loop_run_summary / update_loop_run_diagnostics

```python
def record_loop_run_summary(
    db_path: Path | str,
    *,
    run_id: str,
    loop_name: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    final_state: str | None = None,
    iterations: int | None = None,
    terminated_by: str | None = None,
    error: str | None = None,
    evaluator_score: float | None = None,
    diagnostics_path: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    config: dict | None = None,
) -> bool


def update_loop_run_diagnostics(db_path: Path | str, run_id: str, diagnostics_path: str) -> bool
```

Write one `loop_runs` row and index it in `search_index` with `kind="loop_run"` (ENH-2463). `run_id` is the archive-time identifier (`started_at` mangled the same way as `fsm/persistence.py::archive_run`, joined with `-<loop_name>`) so the row JOINs to the on-disk `.loops/.history/` archive. Idempotent via `INSERT OR IGNORE` on the `run_id` UNIQUE constraint — a resumed-then-completed run contributes exactly one row. The sole v1 producer is `FSMExecutor._finish()`, called best-effort (wrapped in `try/except`) immediately after it emits `loop_complete`. `update_loop_run_diagnostics()` is a single `UPDATE ... WHERE run_id = ?` linking a `loop-specialist`-written diagnostics artifact back to its row; exposed as a public API but not yet wired into any caller (the artifact filename does not encode the archive `run_id`, so an upstream caller must supply it — a known v1 gap).

### record_learning_test_event / _backfill_learning_test_events

```python
def record_learning_test_event(
    db_path: Path | str,
    target: str,
    file_path: str,
    config: dict | None = None,
) -> bool


def _backfill_learning_test_events(conn: sqlite3.Connection, registry_dir: Path) -> int
```

UPSERT one `learning_test_events` row mirroring a Learning Test Registry record and refresh its FTS row (ENH-2466). `record_learning_test_event()` reads the `.md` file at `file_path`, keys the row on `record_id` (the slugified `target`), and is called best-effort from `ll-learning-tests prove`/`mark-stale`/`orphans --mark-stale` — a re-prove overwrites `status`/`assertions_json`/`date` rather than inserting a duplicate. `_backfill_learning_test_events()` is the reconcile companion: it walks `registry_dir` (`.ll/learning-tests/*.md`) with `INSERT OR IGNORE` on `record_id` so out-of-band file edits still land, without overwriting a live-written row's newer status. Wired into `backfill(db, ..., registry_dir=...)`, defaulting to `.ll/learning-tests` when not given.

### record_session_lifecycle_event

```python
def record_session_lifecycle_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    event: str,
    detail: dict | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool
```

Write one `session_lifecycle_events` row and index it in `search_index` with `kind="session_lifecycle"` (ENH-2495). `event` is an open TEXT discriminator (no CHECK constraint) — `handoff_needed`, `compaction`, `stale_ref_sweep` are the v1 producers; ENH-2509 shares the table with `worktree_*` values. Best-effort: catches `sqlite3.Error` internally and returns `False` (never raises), so a hook's primary job is never blocked by a missing/locked database. One authoritative producer per discriminator — `context-monitor.sh`'s first 80%-threshold crossing per pressure episode (`handoff_needed`), `pre_compact.handle()` after state persistence (`compaction`), `sweep_stale_refs.handle()` once per invocation including zero findings (`stale_ref_sweep`).

### record_retirement

```python
def record_retirement(
    db: Path | str = DEFAULT_DB_PATH,
    topic_fingerprint: str = "",
    rule_id: str = "",
    session_id: str = "",
) -> None
```

Mark a recurring-correction cluster as addressed. Uses `INSERT OR REPLACE` so calling it a second time for the same fingerprint updates the record. `rule_id` should be the `decisions.yaml` entry ID (e.g. `BEHAVIOR-001`) or `"claude-md"` when the rule was written directly into CLAUDE.md.

**Parameters:**
- `db` — path to the SQLite database (default: `.ll/history.db`)
- `topic_fingerprint` — 16-char hex fingerprint from `_fingerprint(content)` in `evolution.py`
- `rule_id` — the persisted rule ID (for audit trail); optional
- `session_id` — the session that accepted the rule; optional

### list_retirements

```python
def list_retirements(
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Return all `correction_retirements` rows as `dict` objects, ordered by `addressed_at DESC`. Returns `[]` when the DB does not exist.

**Dict keys:** `topic_fingerprint`, `rule_id`, `addressed_at`, `session_id`.

### correction_retirements table (v13, ENH-2046)

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | |
| `topic_fingerprint` | `TEXT NOT NULL` | `sha256(content[:512])[:16]`; unique index |
| `rule_id` | `TEXT` | `decisions.yaml` entry ID or `"claude-md"` |
| `addressed_at` | `TEXT NOT NULL` | UTC ISO 8601 timestamp |
| `session_id` | `TEXT` | session that accepted the rule |

`detect_recurring_feedback()` in `evolution.py` queries this table read-only via the existing `_open_db()` path; clusters whose fingerprint appears here are excluded from `RecurringFeedbackAnalysis.feedbacks` and counted in `retired_count`.

---

## little_loops.hooks

Host-agnostic hook intent dispatcher. Adapters under `hooks/adapters/<host>/` translate each host's native hook payload into an `LLHookEvent`, pipe it to `python -m little_loops.hooks <intent>`, and translate the returned `LLHookResult` back to the host's response contract.

```python
from little_loops.hooks import LLHookEvent, LLHookResult, main_hooks
```

Public surface — `__all__ = ["LLHookEvent", "LLHookResult", "main_hooks"]`.

### LLHookEvent

The host-agnostic request payload delivered to a hook intent handler. Defined in `scripts/little_loops/hooks/types.py`.

```python
@dataclass
class LLHookEvent:
    host: str
    intent: str = ""
    timestamp: str = ""        # wire key: "ts"
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    cwd: str | None = None
```

**Fields:**

| Field | Type | Default | Wire key | Description |
|---|---|---|---|---|
| `host` | `str` | *(required)* | `host` | Host agent identifier (`"claude-code"`, `"opencode"`, `"codex"`, …). Adapters set this; the CLI reads `LL_HOOK_HOST` (default `"claude-code"`). |
| `intent` | `str` | `""` | `intent` | Hook intent name matching the handler module (`pre_compact`, `session_start`, …). |
| `timestamp` | `str` | `""` | `ts` | ISO 8601 UTC. **Field name and wire key differ** — stored as `timestamp`, serialized as `ts`. |
| `payload` | `dict[str, Any]` | `{}` | `payload` | Host-supplied event data. Schema is intent-specific. |
| `session_id` | `str \| None` | `None` | `session_id` | Host session identifier. Omitted from the wire dict when `None`. |
| `cwd` | `str \| None` | `None` | `cwd` | Working directory the host was operating in. Omitted from the wire dict when `None`. |

**Behavior:**
- `to_dict()` emits the timestamp under the key `ts`; `from_dict()` accepts either `ts` or `timestamp` via `data.get("ts", data.get("timestamp", ""))`. A dict from `to_dict()` round-trips cleanly through `from_dict()`.
- `session_id` and `cwd` are omitted from the wire dict when `None`, so a `from_dict(to_dict(e)) == e` round-trip preserves the `None` sentinel.

```python
from little_loops.hooks import LLHookEvent

event = LLHookEvent(
    host="claude-code",
    intent="pre_compact",
    payload={"transcript_path": "/tmp/session.jsonl"},
    cwd="/Users/me/project",
)
event.to_dict()
# {"host": "claude-code", "intent": "pre_compact", "ts": "", "payload": {...}, "cwd": "..."}
```

### LLHookResult

The host-agnostic response returned by a hook intent handler. Defined in `scripts/little_loops/hooks/types.py`.

```python
@dataclass
class LLHookResult:
    exit_code: int = 0
    feedback: str | None = None
    decision: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    stdout: str | None = None
```

**Fields:**

| Field | Type | Default | Wire key | Description |
|---|---|---|---|---|
| `exit_code` | `int` | `0` | `exit_code` | Always emitted. `0` = pass; `2` = block and surface `feedback` to the model. Non-Claude hosts map this to their own permit/deny semantics. |
| `feedback` | `str \| None` | `None` | `feedback` | Human-readable message. Claude Code writes this to stderr when `exit_code == 2`. Omitted from the wire dict when `None`. |
| `decision` | `str \| None` | `None` | `decision` | Permission decision for permission-checking intents (`allow` / `deny` / `ask`). Omitted from the wire dict when `None`. |
| `data` | `dict[str, Any]` | `{}` | `data` | Additional structured data returned to the host. Omitted from the wire dict when empty. |
| `stdout` | `str \| None` | `None` | `stdout` | Raw payload written to the host's stdout (e.g. `session_start`'s merged config JSON). Omitted from the wire dict when `None`. |

**Behavior:**
- `main_hooks` writes `result.stdout` to stdout verbatim if non-`None`, prints `result.feedback` to stderr if truthy, and raises `SystemExit(result.exit_code)`.
- Handlers should **not** `print()` directly — return bytes on `LLHookResult.stdout` instead so adapters can route them to the host's stdout contract.

```python
from little_loops.hooks import LLHookResult

LLHookResult(exit_code=2, feedback="context budget exceeded; consider /compact")
```

### main_hooks

CLI entry point. Invoked as `python -m little_loops.hooks <intent>`.

```python
def main_hooks(argv: list[str]) -> int: ...
```

**Behavior:**
1. Reads stdin as JSON (skips when stdin is a TTY).
2. Builds `LLHookEvent(host=os.environ.get("LL_HOOK_HOST", "claude-code"), intent=argv[1], payload=<parsed>, cwd=os.getcwd())`. Note: `timestamp` and `session_id` stay at dataclass defaults — the CLI does not populate them.
3. Looks up the handler via `_dispatch_table()` — extension-contributed intents merged with built-ins, with built-ins shadowing extensions on collision.
4. Calls the handler; writes `result.stdout` to stdout if non-`None`, prints `result.feedback` to stderr if truthy, and returns `result.exit_code` (the `__main__` shim raises `SystemExit(...)`).

**Adapter integration:**
- Claude Code adapters (`hooks/adapters/claude-code/precompact.sh`, `precompact-handoff.sh`, `post-tool-use.sh`, `session-start.sh`, `session-end.sh`) invoke `python -m little_loops.hooks <intent>` directly — `LL_HOOK_HOST` defaults to `"claude-code"`.
- The OpenCode adapter (`hooks/adapters/opencode/index.ts`) sets `LL_HOOK_HOST=opencode` before invoking the same CLI.
- The Codex CLI adapter (`scripts/little_loops/hooks/adapters/codex/session-start.sh`, `pre-compact.sh`) sets `LL_HOOK_HOST=codex` before invoking the same CLI. The `hooks.json` template restricts `SessionStart` to `"matcher": "startup"` per FEAT-957's policy (avoids re-emitting identifiers on `resume`/`clear` and minimizes trust-hash churn).

---

## little_loops.host_runner

Host-agnostic CLI invocation layer. Every shell-out to a host CLI (`claude`, `codex`, `opencode`, `pi`, `gemini`, `omp`) is built through a `HostRunner` implementation, so the orchestration layer (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff) never hard-codes host-specific argv.

```python
from little_loops.host_runner import (
    CapabilityEntry,
    CapabilityNotSupported,
    CapabilityReport,
    HostCapabilities,
    HostInvocation,
    HostNotConfigured,
    HostRunner,
    HookEntry,
    apply_host_cli_from_config,
    resolve_host,
)
```

Public surface — `__all__ = ["CapabilityEntry", "CapabilityNotSupported", "CapabilityReport", "ClaudeCodeRunner", "CodexRunner", "GeminiRunner", "HostCapabilities", "HostInvocation", "HostNotConfigured", "HostRunner", "HookEntry", "OmpRunner", "OpenCodeRunner", "PiRunner", "apply_host_cli_from_config", "resolve_host"]`.

### HostInvocation

Immutable value object describing how to invoke a host CLI. Returned by every `build_*` factory on `HostRunner`. Call sites pass `binary` + `args` to `subprocess.Popen`/`run` and merge `env` into the child process environment.

```python
@dataclass(frozen=True)
class HostInvocation:
    binary: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    capabilities: HostCapabilities = field(default_factory=HostCapabilities)
    cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `binary` | `str` | *(required)* | Name of the host binary (e.g., `"claude"`, `"codex"`, `"opencode"`, `"pi"`). |
| `args` | `list[str]` | *(required)* | Positional + flag arguments to append after `binary`. Host-specific argv shape lives here. |
| `env` | `dict[str, str]` | `{}` | Environment variables to merge into the child process. Notably includes `GIT_DIR` / `GIT_WORK_TREE` when working inside a worktree, and host-specific knobs like `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`. |
| `capabilities` | `HostCapabilities` | `HostCapabilities()` | Snapshot of the runner's capability flags, so callers can branch on what was actually wired without re-querying the runner. |
| `cleanup_paths` | `tuple[Path, ...]` | `()` | Temp files created during invocation building that the caller must unlink after the subprocess completes. Currently populated by `CodexRunner.build_blocking_json` when `json_schema` is supplied — the schema dict is written to a temp file and `--output-schema <path>` is appended to `args`. Call `p.unlink(missing_ok=True)` for each path in this tuple after `subprocess.run`. |

**Behavior:**
- `frozen=True` — mutating an invocation in flight would silently corrupt argv across the runner/caller boundary. This establishes the `frozen=True` convention for new value objects in `scripts/little_loops/`.

### HostCapabilities

Capability flags describing what a host runner supports. Each flag corresponds to a feature that may or may not be available on a given host; call sites that require a capability should check the relevant flag and either fall back gracefully or emit `CapabilityNotSupported`.

```python
@dataclass(frozen=True)
class HostCapabilities:
    streaming: bool = False
    permission_skip: bool = False
    agent_select: bool = False
    tool_allowlist: bool = False
    structured_output: bool = False
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `streaming` | `bool` | `False` | Host can produce turn-by-turn structured (JSON / NDJSON) events for long-running orchestration paths. |
| `permission_skip` | `bool` | `False` | Host supports skipping interactive permission prompts (Claude `--dangerously-skip-permissions`, Codex `--dangerously-bypass-approvals-and-sandbox`). Required for headless automation. |
| `agent_select` | `bool` | `False` | Host accepts a per-invocation agent / persona selector. |
| `tool_allowlist` | `bool` | `False` | Host accepts an explicit tool allowlist on invocation. |
| `structured_output` | `bool` | `False` | Host's CLI honors the inline `--json-schema` flag the FSM evaluators append (Anthropic `claude` CLI). When `False`, evaluators skip the flag and rely on prompt-and-parse (BUG-2626 tag fallback). Gated at the evaluator call sites (ENH-2627). |

### HostRunner

Protocol every host runner satisfies. `@runtime_checkable`, so `isinstance(obj, HostRunner)` works for registry validation. Protocols are matched structurally — any class with the methods below satisfies `HostRunner` whether or not it subclasses the Protocol explicitly.

```python
@runtime_checkable
class HostRunner(Protocol):
    name: str

    def detect(self) -> bool: ...
    def build_streaming(self, *, prompt: str, working_dir: Path | None = None,
                        resume: bool = False, agent: str | None = None,
                        tools: list[str] | None = None,
                        sandbox_mode: str | None = None) -> HostInvocation: ...
    def build_blocking_json(self, *, prompt: str, model: str | None = None,
                            json_schema: dict | None = None,
                            sandbox_mode: str | None = None) -> HostInvocation: ...
    def build_version_check(self) -> HostInvocation: ...
    def build_detached(self, *, prompt: str,
                       sandbox_mode: str | None = None) -> HostInvocation: ...
    def describe_capabilities(self) -> CapabilityReport: ...
```

**Methods:**
- `detect()` — return `True` if this host is available in the current environment (typically `shutil.which("<binary>") is not None`).
- `build_streaming()` — argv that streams structured turn-by-turn events. Used by the long-running orchestration paths (`ll-auto`, `ll-parallel`, FSM runners).
- `build_blocking_json()` — argv for a one-shot invocation returning a single JSON blob. Used by FSM structured evaluators.
- `build_version_check()` — argv that prints the host's version and exits. Used by capability probes.
- `build_detached()` — argv for fire-and-forget detached execution. Used by FSM handoff.
- `describe_capabilities()` — probe the host and return a `CapabilityReport` describing which features are supported. Used by `ll-doctor` and `ll-action`.

**Concrete runners:**

| Runner | Host | Status | Notes |
|---|---|---|---|
| `ClaudeCodeRunner` | `claude` CLI | ✓ production | Argv mirrors `subprocess_utils.run_claude_command`; snapshot test in `tests/test_host_runner.py::test_claude_runner_matches_legacy_args`. |
| `CodexRunner` | `codex` CLI | ✓ production | Translates the Claude-shaped Protocol surface to Codex `exec` headless mode. Auto-detected when `codex` is on PATH (probe order: `claude → codex → pi → gemini → omp`). For `agent`, `build_streaming` reads `.codex/agents/<name>.toml` and prepends `developer_instructions` as a `[Persona: <name>]` block (ENH-1533); when the TOML is absent, falls back to emitting `CapabilityNotSupported` plus a stderr notice. `tools` always emits `CapabilityNotSupported` and is dropped; use `sandbox_mode=` (ENH-1529) for constrained execution. `describe_capabilities()` reports `agent_select.status == "partial"` and `tool_allowlist.status == "partial"` (via sandbox_mode). |
| `GeminiRunner` | `gemini` CLI | ✓ production | Gemini CLI (npm `@google/gemini-cli`). Flags are near-identical to Claude Code: `-p <prompt>`, `--output-format stream-json` / `json`, `--approval-mode yolo` for permission skip, `--resume latest` for resume, `--model <id>`. `agent` and `tools` parameters emit `CapabilityNotSupported` and are dropped (no `--agent` flag — skills activate implicitly; tool policy is a TOML-file Policy Engine, not a flag). `json_schema` is silently dropped like `ClaudeCodeRunner`. See `thoughts/research/gemini-cli-surface.md` (ENH-2184/ENH-2185). |
| `OmpRunner` | `omp` CLI | ✓ production | oh-my-pi (Bun `@oh-my-pi/pi-coding-agent`). `-p <prompt>` print mode; `--mode json` emits a JSONL event stream (no single-blob mode — `build_blocking_json` uses `--mode json --no-session` and callers consume the final event, same contract as Codex). `--continue` for resume, `--model <pattern>`, native `--tools <comma-list>` allowlist. `agent` emits `CapabilityNotSupported` (subagents spawn in-session). Permission skip is implicit — print mode never prompts. See `thoughts/research/omp-headless-flags.md` (FEAT-1850). |
| `OpenCodeRunner` | `opencode` CLI | stub | Registered so `LL_HOST_CLI=opencode` resolves to a useful error rather than the generic "unknown host". All `build_*` methods raise `HostNotConfigured`. See FEAT-1472. |
| `PiRunner` | `pi` CLI | frozen stub | Present in `_PROBE_ORDER`, so hosts with `pi` on PATH resolve to this stub. All `build_*` methods raise `HostNotConfigured`. Vanilla Pi support is cancelled (ARCHITECTURE-050); superseded by `OmpRunner` (EPIC-2258). |

### CapabilityEntry

Immutable value object describing the support status of a single host capability.

```python
@dataclass(frozen=True)
class CapabilityEntry:
    name: str
    status: Literal["full", "partial", "unsupported"]
    note: str = ""
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *(required)* | Capability identifier (e.g., `"streaming"`, `"permission_skip"`). |
| `status` | `Literal["full", "partial", "unsupported"]` | *(required)* | Support level on the active host. |
| `note` | `str` | `""` | Optional human-readable clarification (e.g., `"flag accepted but not validated"`). |

### HookEntry

Immutable value object describing the installation status of a single hook event.

```python
@dataclass(frozen=True)
class HookEntry:
    name: str
    status: Literal["installed", "registered", "deferred", "absent"]
    note: str = ""
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *(required)* | Hook event name (e.g., `"pre_tool_use"`, `"post_tool_use"`). |
| `status` | `Literal["installed", "registered", "deferred", "absent"]` | *(required)* | Whether the hook is active on this host. |
| `note` | `str` | `""` | Optional clarification. |

### CapabilityReport

Aggregated result of `describe_capabilities()`. Produced by every `HostRunner` implementation and consumed by `ll-doctor` and `ll-action capabilities`.

```python
@dataclass(frozen=True)
class CapabilityReport:
    host: str
    binary: str
    version: str
    capabilities: list[CapabilityEntry]
    hooks: list[HookEntry]
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `host` | `str` | Runner name (e.g., `"claude"`, `"codex"`). |
| `binary` | `str` | Resolved binary path (e.g., `"/usr/local/bin/claude"`). |
| `version` | `str` | Version string reported by the host, or `"unknown"` if detection fails. |
| `capabilities` | `list[CapabilityEntry]` | One entry per capability probe. |
| `hooks` | `list[HookEntry]` | One entry per registered hook event. |

### describe_capabilities

Protocol method implemented by every `HostRunner`. Returns a `CapabilityReport` without invoking the host for a real task — capability probes are fast, read-only checks.

```python
def describe_capabilities(self) -> CapabilityReport: ...
```

Used by `ll-doctor` (and `ll-doctor --json`) to generate human-readable and JSON diagnostic output. Each runner reports only the capabilities it can probe; stubs (`OpenCodeRunner`, `PiRunner`) return `"unsupported"` for all entries.

### apply_host_cli_from_config

Apply the `orchestration.host_cli` config key (or `LL_HOST_CLI` env var) to the runner selection before the binary probe runs. Typically called once at startup by orchestration entry points.

```python
def apply_host_cli_from_config(config: dict) -> None: ...
```

### resolve_host

Discovery entry point. Returns a `HostRunner` instance ready to build invocations.

```python
def resolve_host(env: dict[str, str] | None = None) -> HostRunner: ...
```

**Behavior:**

Detection order (first match wins):
1. `LL_HOST_CLI` environment variable — explicit override.
2. `LL_HOOK_HOST` environment variable — falls back to the hooks-layer host identifier so users with an existing hook config don't need a second knob.
3. Binary probe: `claude` → `codex` → `pi` → `gemini` → `omp` (see `_PROBE_ORDER`).
4. Raise `HostNotConfigured` with a remediation hint.

```python
from little_loops.host_runner import resolve_host

runner = resolve_host()
invocation = runner.build_streaming(prompt="Hello, world")
# subprocess.run([invocation.binary, *invocation.args], env={**os.environ, **invocation.env})
```

### build_anthropic_request / build_batch_request / dispatch_anthropic_request / dispatch_batch_request / poll_batch_result

`orchestration.request_path` opt-in dispatch (FEAT-2673, FEAT-2710, FEAT-2716,
EPIC-2456 F1) — a request path structurally distinct from the `HostRunner`
Protocol above: it calls the `anthropic` SDK's `messages.create()` /
`messages.batches.*` directly rather than shelling out to a host CLI
subprocess.

```python
def build_anthropic_request(*, skill_body, system_prompt, tools, messages, model,
                             fragment_store, require_repeat=True,
                             defer_loading_threshold=None,
                             search_tool_variant="bm25") -> dict[str, Any]: ...

def build_batch_request(*, custom_id, skill_body, system_prompt, tools, messages,
                         model, fragment_store, require_repeat=True,
                         defer_loading_threshold=None,
                         search_tool_variant="bm25") -> dict[str, Any]: ...

def dispatch_anthropic_request(*, action, system_prompt=None, tools=None, model,
                                fragment_store, require_repeat=True,
                                defer_loading_threshold=None,
                                search_tool_variant="bm25") -> ActionResult: ...

def dispatch_batch_request(*, custom_id, action, system_prompt=None, tools=None,
                            model, fragment_store, require_repeat=True,
                            defer_loading_threshold=None,
                            search_tool_variant="bm25") -> str: ...

def poll_batch_result(*, batch_id, custom_id, poll_interval_seconds=5.0,
                       max_wait_seconds=3600.0, backoff_factor=1.5,
                       max_poll_interval_seconds=60.0) -> ActionResult: ...
```

**Behavior:**
- `build_anthropic_request()` / `build_batch_request()` only assemble request
  kwargs (system/tools/messages, plus F1 cache-marking `cache_control` blocks
  and F1 deferred-tool-loading search-tool injection) — no network call. This
  keeps the `anthropic` package import lazy for callers that stay on the
  default `"cli"` path.
- `dispatch_anthropic_request()` builds via `build_anthropic_request()`, then
  calls `anthropic.Anthropic().messages.create(**request)` and normalizes the
  response into an `ActionResult` (same contract `action_runner.run()`
  returns for the CLI subprocess path). `anthropic.APIError` is caught and
  returned as a nonzero-exit-code result rather than raised.
- `dispatch_batch_request()` builds via `build_batch_request()`, submits via
  `anthropic.Anthropic().messages.batches.create(**kwargs)`, and returns the
  new batch's id. Persisting that id so a resumed run doesn't double-submit
  is the caller's responsibility — see `fsm/batch_tracker.py`'s
  `BatchTracker`.
- `poll_batch_result()` polls `messages.batches.retrieve()` with exponential
  backoff (capped at `max_poll_interval_seconds`) until
  `processing_status == "ended"` or `max_wait_seconds` elapses, then fetches
  `messages.batches.results()` and returns the entry matching `custom_id` as
  an `ActionResult`. Raises `BatchPollTimeout` on deadline — callers should
  leave the batch tracker file in place on that error so a resumed run
  retries against the same `batch_id`.
- `FSMExecutor._resolve_request_path()` / `_dispatch_live()`
  (`fsm/executor.py`) are the sole production call sites, gated on
  `state.request_path or orchestration_config.request_path` resolving to
  `"sdk"`/`"batch"` for `action_mode == "prompt"` states. Default (`"cli"`)
  behavior is unaffected.

### HostNotConfigured

Raised when no host runner can be resolved from env or binary probe. The error message includes a remediation hint pointing at the `LL_HOST_CLI` and `LL_HOOK_HOST` env vars and the `orchestration.host_cli` config key so users have a clear path to fix the failure.

```python
class HostNotConfigured(RuntimeError): ...
```

Also raised by stub runners (`OpenCodeRunner`, `PiRunner`) on any `build_*` call, so callers that explicitly select a non-wired host get a useful error rather than malformed argv.

### CapabilityNotSupported

Warning emitted when a caller requests a capability the active host lacks (e.g., requesting `tools=` against `CodexRunner`; or requesting `agent=` against `CodexRunner` when `.codex/agents/<name>.toml` is absent — ENH-1533 prompt injection succeeds silently when the TOML exists).

```python
class CapabilityNotSupported(UserWarning): ...
```

Subclasses `UserWarning` (not `Warning`) so test code can capture it via `pytest.warns` and production code can route it through `warnings.simplefilter("error", CapabilityNotSupported)` for strict contexts. Mirrors the precedent set by `config.core` which emits `DeprecationWarning` via `warnings.warn(..., stacklevel=2)`.

---

## little_loops.runner_spec

Shared runner abstraction extracted from `ll-harness`/`ll-action`'s previously duplicated dispatch if/elifs (ENH-2668). `ll-harness` and `ll-action` build an `ActionSpec` and call `run_action()` instead of each owning its own runner-kind dispatch.

```python
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action
```

### RunnerType

`Enum` covering the runner kinds `ll-harness` exposes (`SKILL`, `CMD`, `MCP`, `PROMPT`, `DSL`) plus `LOOP` for FSM loop execution.

### ActionSpec

```python
@dataclass(frozen=True)
class ActionSpec:
    name: str
    runner: RunnerType
    target: str
    args: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120
```

Frozen, following the same crosses-the-runner/caller-boundary convention as `host_runner.HostInvocation`.

### RunnerResult

Unchanged in shape from its pre-extraction definition in `cli/harness.py`; that module re-exports it (`from little_loops.cli.harness import RunnerResult` still resolves) so existing importers are unaffected.

### run_action

`run_action(spec: ActionSpec) -> RunnerResult` dispatches to the runner named by `spec.runner`. Covers `SKILL`/`CMD`/`MCP`/`PROMPT`. `RunnerType.DSL` is a batch driver over `PROMPT` (callers loop and call `run_action` once per task, as `ll-harness`'s `cmd_dsl` does via `cmd_prompt`) rather than an independent execution path. `RunnerType.LOOP` is **not** dispatched by `run_action` — raises `ValueError` if attempted — because FSM loop execution (`PersistentExecutor`/`run_foreground()`) is a stateful, resumable, multi-state engine with per-state persistence, an event bus, and scope locking spanning the entire run, not a single blocking call. `cli/loop/run.py`'s `cmd_run()` builds a `RunnerType.LOOP` `ActionSpec` for structural/observability parity only and continues to call `PersistentExecutor` directly for execution.

---

## little_loops.queue_store

Persisted queue-entry store for `ll-queue` (FEAT-2682), backing a dedicated `.ll/queue.db` — distinct from `ll-loop queue`'s PID-liveness marker mechanism (`cli/loop/queue.py`), which FEAT-2684 preserves unchanged as a compat shim rather than migrating. Modeled directly on `session_store`'s migration/`connect`/`ensure_db` shape (own `_MIGRATIONS`/`SCHEMA_VERSION`, copied rather than shared).

```python
from little_loops.queue_store import (
    DEFAULT_DB_PATH,     # Path(".ll/queue.db")
    PRIORITY_TIERS,      # ("P0", "P1", "P2", "P3", "P4", "P5")
    QueueEntry,           # id, action: ActionSpec, enqueued_at, priority, status, result
    AmbiguousEntryIdError,
    ensure_db,
    connect,
    add_entry,            # (action: ActionSpec, priority: str = "P3", *, db_path=...) -> QueueEntry
    list_entries,          # ordered by priority tier, then FIFO within tier
    get_entry,              # exact id lookup
    resolve_entry,          # exact id or 8+-char prefix; raises AmbiguousEntryIdError on a multi-match prefix
    remove_entry,
    update_entry_result,   # for the FEAT-2683 worker loop to record status/result
)
```

Schema: `queue_entries(id, action, enqueued_at, priority, status, result)`. `action` is a JSON-serialized `ActionSpec` (`little_loops.runner_spec`); `priority` is stored as the 0(P0)-5(P5) numeric rank so `ORDER BY priority ASC, enqueued_at ASC` reproduces `QueuedIssue.__lt__`'s tiered-then-FIFO ordering without importing that class (it's typed concretely against `IssueInfo`). `result` is `NULL` until a worker calls `update_entry_result()`.

---

## little_loops.tool_catalog

Catalog-assembly for little-loops' own Anthropic Messages API tool set (FEAT-2680). Walks `skills/*/SKILL.md`, `commands/*.md`, and `agents/*.md` frontmatter and produces a full `tools` array — the single, stable data source FEAT-2672 (deferred tool loading) and FEAT-2673 (`build_anthropic_request()`) consume instead of each reimplementing frontmatter enumeration.

```python
from little_loops.tool_catalog import ToolDefinition, assemble_tool_catalog, to_anthropic_tools
```

### ToolDefinition

```python
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    cache_control: dict[str, str] | None = None
```

Frozen, following the same crosses-a-boundary convention as `host_runner.CapabilityEntry`. `cache_control` is always `None` coming out of `assemble_tool_catalog` — no code today populates it (see FEAT-2681); callers may set it before serializing.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *(required)* | Skill directory name / command file stem / agent file stem. |
| `description` | `str` | *(required)* | Frontmatter `description`, quote-stripped. |
| `input_schema` | `dict[str, Any]` | *(required)* | Envelope-free Anthropic `input_schema` body — see below. |
| `cache_control` | `dict[str, str] \| None` | `None` | Unset by `assemble_tool_catalog`; present in serialized output only when set. |

### assemble_tool_catalog

```python
def assemble_tool_catalog(project_root: Path) -> list[ToolDefinition]: ...
```

Walks `project_root / "skills"` (`*/SKILL.md`), `project_root / "commands"` (`*.md`), and `project_root / "agents"` (`*.md`), each via `sorted(glob(...))` for deterministic order. Missing directories contribute no entries and never raise, matching the `cli/action.py:_load_skills()` / `cli/artifact.py:_load_skill_catalog()` precedent. All three walks parse frontmatter with the same `frontmatter.parse_skill_frontmatter()` — standardized on the flat parser rather than `adapters/core.py:_read_frontmatter()`'s nested-preserving variant, since `input_schema` bodies are hand-authored per entry *kind*, not derived from an agent's `tools:`/`model:` structure.

`input_schema` generation has no mechanical derivation path (skills/commands' `args`/`argument-hint` frontmatter is free-text display hints with no type information; agents carry no args-equivalent field at all):
- Skill/command **with** an `args`/`argument-hint` hint: `{"type": "object", "properties": {"args": {"type": "string", "description": <hint>}}, "required": []}`.
- Skill/command **without** a hint: `{"type": "object", "properties": {}, "required": []}`.
- Agent (always): fixed `{"type": "object", "properties": {"description": {...}, "prompt": {...}}, "required": ["description", "prompt"]}`, mirroring the real Agent-tool invocation contract.

### to_anthropic_tools

```python
def to_anthropic_tools(
    entries: list[ToolDefinition], *, defer_loading_threshold: int | None = None
) -> list[dict[str, Any]]: ...
```

Serializes catalog entries into the literal Anthropic Messages API `tools` array shape. `cache_control` is omitted from the dict entirely when `None` — the Anthropic API rejects a literal `null` cache_control value, so `None` must never become a JSON key.

`defer_loading_threshold` (FEAT-2672, EPIC-2456 F1): when set, entries at or past this catalog index get `defer_loading: True`, withholding their full definition from the assembled system prompt unless the model searches for them via a server-side search tool. `None` (default) leaves every entry unflagged — unchanged behavior. Setting `defer_loading: True` has no effect unless the request's `tools` array also carries a `tool_search_tool_bm25_20251119` / `tool_search_tool_regex_20251119` entry — see `host_runner.build_anthropic_request()`, which injects that entry automatically.

---

## little_loops.adapters

> `CodexEmitter` and `GeminiEmitter` are fully implemented (FEAT-2391/2392). Use `ll-adapt --host codex --apply` or `ll-adapt --host gemini --apply` to emit artifacts for a given host.

Host-parameterised adapter layer that converts ll skill/command/agent metadata into each target host's discovery format. Parallel to `little_loops.host_runner` (which handles *invoking* the host CLI); this module handles *emitting* ll artifacts *to* a host.

```python
from little_loops.adapters import HostEmitter, resolve_emitter, AdapterError
```

### HostEmitter

`@runtime_checkable` structural Protocol. Any class exposing `name: str` and the three `emit_*` methods satisfies it without explicit subclassing; `isinstance(obj, HostEmitter)` works at runtime.

```python
class HostEmitter(Protocol):
    name: str
    def emit_skill(self, skill_meta: dict) -> str: ...
    def emit_command(self, cmd_meta: dict) -> str: ...
    def emit_agent(self, agent_meta: dict) -> str: ...
```

### resolve_emitter

Registry-backed factory. Returns a `HostEmitter` instance for the given host name.

```python
emitter = resolve_emitter("codex")
output = emitter.emit_skill({"name": "my-skill", ...})
```

**Args:** `host` — one of `"codex"`, `"gemini"`, `"omp"`.  
**Raises:** `AdapterError` if the host is not registered.

### AdapterError

Raised when a host emitter cannot fulfil the request (unknown host, or stub emitter called before implementation is wired up).

```python
class AdapterError(Exception): ...
```

### Built-in emitters

| Class | Host key | Status |
|-------|----------|--------|
| `CodexEmitter` | `"codex"` | Implemented (FEAT-2391) — emits `.codex/` skill/command/agent files |
| `GeminiEmitter` | `"gemini"` | Implemented (FEAT-2392) — emits `.gemini/` skill/command/agent files |
| `OmpEmitter` | `"omp"` | Raises `AdapterError` (not `NotImplementedError`) with a PR pointer; absent from auto-detection |

To add a host: create `scripts/little_loops/adapters/<host>.py` implementing `HostEmitter`, then register the class in `_EMITTER_REGISTRY` in `core.py`.

---

## little_loops.codequery

Structural code-query provider protocol and registry (FEAT-2576). Mirrors the `adapters/`
shape above: a `@runtime_checkable` Protocol, a lazy-import registry, and a `resolve_*`
factory. Answers "who calls/imports/defines/references X" and "what is impacted if these
files change" without requiring any index to be built.

```python
from little_loops.codequery import CodeQueryProvider, CodeRef, ProviderStatus, resolve_provider
```

### CodeQueryProvider

```python
class CodeQueryProvider(Protocol):
    name: str
    def capabilities(self) -> set[str]: ...
    def status(self) -> ProviderStatus: ...
    def callers_of(self, symbol: str) -> list[CodeRef]: ...
    def callees_of(self, symbol: str) -> list[CodeRef]: ...
    def importers_of(self, module: str) -> list[CodeRef]: ...
    def defines(self, path: str) -> list[CodeRef]: ...
    def references(self, symbol: str) -> list[CodeRef]: ...
    def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]: ...
```

### resolve_provider

```python
provider = resolve_provider("auto")  # or "fallback"
refs = provider.callers_of("little_loops.issue_manager.IssueManager.load")
```

**Args:** `name` — a registered provider name, or `"auto"` (default) to pick the first
registered provider (registration order) whose `status()` reports `available`.
**Raises:** `CodeQueryError` if `name` is not registered, or `"auto"` finds none available.

### Built-in providers

| Class | Provider key | Status |
|-------|--------------|--------|
| `CodegraphProvider` | `"codegraph"` | Implemented (ENH-2613) — read-only reader over a `.codegraph/codegraph.db` SQLite index; `exact` confidence, staleness-checked against `git HEAD` and the working tree per `code_query.staleness` |
| `FallbackProvider` | `"fallback"` | Implemented (FEAT-2576) — grep/AST over the working tree; always available, always `freshness: fresh` |

To add a provider: create `codequery/<provider>.py` implementing `CodeQueryProvider`, then
register in `_PROVIDER_MAP` in `core.py`.

---

## little_loops.transport

Transport abstraction for the EventBus. A `Transport` is an additive sink that receives every event emitted on the bus. The Protocol is intentionally minimal — `send(event)` for delivery and `close()` for cleanup — so new sinks can be added without modifying `EventBus` itself.

```python
from pathlib import Path

from little_loops.events import EventBus
from little_loops.transport import JsonlTransport, Transport

bus = EventBus()
bus.add_transport(JsonlTransport(Path(".ll/events.jsonl")))
bus.emit({"event": "demo", "ts": "2026-05-02T00:00:00Z"})
bus.close_transports()
```

### Transport Protocol

```python
@runtime_checkable
class Transport(Protocol):
    def send(self, event: dict[str, Any]) -> None: ...
    def close(self) -> None: ...
```

Implement this protocol to register a custom event sink. The `@runtime_checkable` decorator enables `isinstance(obj, Transport)` checks at runtime. Transports do not filter events — every event emitted on the bus is delivered to every registered transport. Implementations must tolerate arbitrary `dict[str, Any]` shapes (the bus does not validate event contents). Per-transport `send()` and `close()` exceptions are caught and logged by `EventBus`, so a faulty transport never blocks delivery to other observers or transports.

### JsonlTransport

Reference implementation that appends each event as a single JSON line to a file. Replaces the previous `EventBus._file_sinks` mechanism.

```python
from little_loops.transport import JsonlTransport
from pathlib import Path

transport = JsonlTransport(Path(".ll/events.jsonl"))
transport.send({"event": "demo", "ts": "2026-05-02T00:00:00Z"})
```

#### Constructor

```python
JsonlTransport(path: Path)
```

**Parameters:**
- `path` - Path to the JSONL log file. The parent directory is created at construction time so per-event writes do not have to check it.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Append `json.dumps(event)` as a line to the configured path. Each call opens and closes the file. |
| `close() -> None` | No-op. Each `send()` already closes its file handle. |

### UnixSocketTransport

Streams newline-delimited JSON events over an `AF_UNIX` socket so local consumers (TUIs, log tailers, dev dashboards) get sub-second latency without polling. Stdlib-only (no external dependencies).

```python
from little_loops.transport import UnixSocketTransport
from pathlib import Path

transport = UnixSocketTransport(Path(".ll/events.sock"), max_clients=8)
transport.send({"event": "demo", "ts": "2026-05-02T00:00:00Z"})
transport.close()
```

#### Constructor

```python
UnixSocketTransport(path: Path, max_clients: int = 8, on_connect: Callable[[_SocketClient], None] | None = None)
```

**Parameters:**
- `path` - Path to the AF_UNIX socket. Any stale file at this path is unlinked before bind. The file is `chmod 0600` immediately after `bind()`.
- `max_clients` - Maximum simultaneous client connections. Used as both the `listen()` backlog and the live-clients cap; further connections are accepted-and-closed.
- `on_connect` - Optional callback invoked by `_accept_loop` immediately after a new client is registered. Receives the new `_SocketClient`; used internally by `wire_transports` to seed current loop state. Defaults to `None` (no-op).

**Wire format:** Each `send(event)` serializes the event with `json.dumps(event)` and appends a `\n`, so consumers can parse one line at a time:

```bash
nc -U .ll/events.sock | jq
```

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Enqueue the serialized event into every connected client's outbound queue. Non-blocking — if a client's queue is full, the newest event is dropped (preserving causal order) and a rate-limited warning is logged. |
| `close() -> None` | Set the shutdown event, join the accept thread (≤2s) and each client thread (≤1s, 10s ceiling overall), close the server socket, and unlink the socket file. |

**Platform support:** Requires `AF_UNIX` (POSIX). On Windows, [`wire_transports`](#wire_transports) raises `RuntimeError` rather than registering the transport.

### OTelTransport

Maps ll loop executions to OpenTelemetry traces and spans, exporting via OTLP to any OTel-compatible backend (Grafana, Jaeger, Datadog, etc.). Requires `pip install 'little-loops[otel]'`.

**Span hierarchy:** loop run = trace root (`loop_start`/`loop_complete`), state = child span (`state_enter`), action = grandchild span (`action_start`/`action_complete`). Span events are emitted for `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, and `action_output`.

```python
from little_loops.transport import OTelTransport

transport = OTelTransport(
    endpoint="http://localhost:4317",
    service_name="little-loops",
)
transport.send({"event": "loop_start", "loop_name": "my-loop"})
transport.send({"event": "loop_complete", "outcome": "success"})
transport.close()
```

#### Constructor

```python
OTelTransport(
    endpoint: str = "http://localhost:4317",
    service_name: str = "little-loops",
)
```

**Parameters:**
- `endpoint` - OTLP gRPC endpoint for the collector. Passed directly to `OTLPSpanExporter`.
- `service_name` - Value for the `service.name` OTel resource attribute applied to all spans.

**Raises `RuntimeError`** at construction time if `opentelemetry-sdk` or `opentelemetry-exporter-otlp-grpc` are not installed.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Route the event through the span state machine. Sub-loop events (`depth > 0`) are no-ops with a single warning per session. |
| `close() -> None` | Call `force_flush()` then `shutdown()` on the tracer provider, flushing all buffered spans before exit. |

#### Event → span mapping

| Event | Span action |
|-------|-------------|
| `loop_start` | Open root span (new trace). Name = `event["loop_name"]`. |
| `loop_resume` | Close all open spans; open a new root span (new trace). |
| `state_enter` | Close prior state span + action span; open child of loop span. Name = `event["state"]`. |
| `action_start` | Open grandchild of state span. Name = `event["action"]`. |
| `action_complete` | Close action span. |
| `loop_complete` | Close state + action spans; set loop span status (OK or ERROR); close loop span. |
| `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `action_output` | Add span event on innermost open span. |

### WebhookTransport

POSTs batched FSM events to an HTTP endpoint for remote dashboards, Slack bots, and CI systems. Requires `pip install 'little-loops[webhooks]'`.

**Batching:** `send()` enqueues events non-blocking; a daemon thread flushes the queue every `batch_ms` milliseconds. All accumulated events are POSTed as a single JSON array.

**Retry:** Failed POSTs (5xx or connection error) are retried up to `max_retries` times with exponential backoff (0.5s → … → 8s). After exhaustion the batch is dropped with a `WARNING` — exceptions never propagate to the caller.

```python
from little_loops.transport import WebhookTransport

transport = WebhookTransport(
    url="https://hooks.example.com/ll-events",
    batch_ms=1000,
    headers={"Authorization": "Bearer token"},
    max_retries=3,
)
transport.send({"event": "loop_start", "loop_name": "my-loop"})
transport.close()
```

#### Constructor

```python
WebhookTransport(
    url: str,
    batch_ms: int = 1000,
    headers: dict[str, str] | None = None,
    max_retries: int = 3,
)
```

**Parameters:**
- `url` - HTTP endpoint to POST batched events to.
- `batch_ms` - Flush interval in milliseconds (default: 1000).
- `headers` - Optional dict of extra HTTP headers (e.g. `{"Authorization": "Bearer tok"}`).
- `max_retries` - Number of retries on 5xx/connection error before giving up (default: 3).

**Raises `RuntimeError`** at construction time if `httpx` is not installed.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Enqueue the event for the next batch flush. Non-blocking. No-op after `close()` is called. |
| `close() -> None` | Signal shutdown, drain the queue with one final flush, and join the daemon thread (10s timeout). |

### wire_transports

Register the transports listed in an `EventsConfig` on an `EventBus`. Called by CLI entry points (ll-loop, ll-parallel, ll-sprint) at startup.

```python
from little_loops.events import EventBus
from little_loops.transport import wire_transports
from pathlib import Path

bus = EventBus()
wire_transports(bus, config.events, log_dir=Path(".ll"))
```

**Signature:**
```python
def wire_transports(
    bus: EventBus,
    config: EventsConfig,
    log_dir: Path | None = None,
) -> None
```

**Parameters:**
- `bus` - The `EventBus` instance to register transports on.
- `config` - `EventsConfig` whose `transports` field lists the transport names to wire up.
- `log_dir` - Directory under which built-in transports place their log files. Defaults to `Path(".ll")` under the current working directory.

**Behavior:**
- Each name in `config.transports` is resolved against an internal registry of built-in transport names. Five transports are currently shipped: `"jsonl"` (registers a `JsonlTransport` writing to `<log_dir>/events.jsonl`), `"socket"` (registers a [`UnixSocketTransport`](#unixsockettransport) bound at `config.socket.path` with `config.socket.max_clients`), `"otel"` (registers an [`OTelTransport`](#oteltransport) using `config.otel.endpoint` and `config.otel.service_name`), `"webhook"` (registers a [`WebhookTransport`](#webhooktransport) using `config.webhook.url`, `batch_ms`, and `headers`; skipped with a warning if `url` is `None`), and `"sqlite"` (registers a `SQLiteTransport` — defined in `little_loops.session_store`, not `transport.py` — writing events into the per-project `.ll/history.db` unified session store).
- Unknown names log a `WARNING` and are skipped — a typo in user config never prevents the loop from starting.
- The `"socket"` transport raises `RuntimeError` on platforms without `AF_UNIX` (e.g. Windows). This is the deliberate exception to the warn-and-skip rule: silently dropping `"socket"` on Windows would be a more confusing failure mode.

---

## little_loops.extension

Extension protocol, loader, and reference implementation for the plugin extension system.

```python
from little_loops.extension import ExtensionLoader, LLExtension

extensions = ExtensionLoader.load_all(config_paths=["my_package:MyExtension"])
for ext in extensions:
    ext.on_event(LLEvent(type="issue.completed", timestamp="2026-04-02T12:00:00Z"))
```

### ENTRY_POINT_GROUP

```python
ENTRY_POINT_GROUP = "little_loops.extensions"
```

Module-level constant defining the Python entry point group name used by `ExtensionLoader.from_entry_points()` and by external packages registering extensions in `pyproject.toml`.

### LLExtension Protocol

```python
@runtime_checkable
class LLExtension(Protocol):
    event_filter: str | list[str] | None  # optional; defaults to None
    def on_event(self, event: LLEvent) -> None: ...
```

Implement this protocol to create an extension that receives structured events from the EventBus. The `@runtime_checkable` decorator enables `isinstance(obj, LLExtension)` checks at runtime.

Optionally declare `event_filter` as a class attribute to subscribe only to specific event namespaces. `wire_extensions()` reads this attribute and passes it to `bus.register()`. If the attribute is absent, the extension receives all events:

```python
class MyFSMExtension:
    event_filter = ["state_enter", "loop_*"]  # bare FSM event names

    def on_event(self, event: LLEvent) -> None:
        print(f"FSM event: {event.type}")

class MyIssueExtension:
    event_filter = "issue.*"  # dotted namespace

    def on_event(self, event: LLEvent) -> None:
        print(f"Issue event: {event.type}")
```

### NoopLoggerExtension

Reference implementation of `LLExtension` that appends events to a JSONL log file.

```python
from little_loops.extension import NoopLoggerExtension
from pathlib import Path

ext = NoopLoggerExtension(log_path=Path(".ll/my-events.jsonl"))
ext.on_event(event)  # appends event.to_dict() as JSON line
```

#### Constructor

```python
NoopLoggerExtension(log_path: Path | None = None)
```

**Parameters:**
- `log_path` - Path to the JSONL log file. Defaults to `Path(".ll/extension-events.jsonl")`. Parent directories are created on construction.

#### Methods

| Method | Description |
|--------|-------------|
| `on_event(event: LLEvent) -> None` | Append `json.dumps(event.to_dict())` as a line to the log file. |

### ExtensionLoader

Discovers and instantiates extensions from config paths and Python entry points. All methods are static.

#### Methods

```python
@staticmethod
def from_config(extension_paths: list[str]) -> list[LLExtension]
```
Load extensions from `"module.path:ClassName"` strings. Each string is split on the last `":"`, the module is imported, and the class is instantiated with no arguments. Failures are caught and logged individually.

```python
@staticmethod
def from_entry_points() -> list[LLExtension]
```
Discover extensions registered under the `"little_loops.extensions"` entry point group via `importlib.metadata.entry_points()`. Each discovered class is instantiated with no arguments. Includes Python 3.11 compatibility fallback.

```python
@staticmethod
def load_all(config_paths: list[str] | None = None) -> list[LLExtension]
```
Combined loader. When `config_paths` is provided, loads from config first, then always loads from entry points. Returns the merged list.

**Parameters:**
- `config_paths` - Optional list of `"module:Class"` strings from the `extensions` config key. Defaults to `None`.

**Returns:** List of instantiated extensions from both sources.

### wire_extensions

Convenience helper that loads all extensions from config and registers them on an `EventBus`. This is the function called by CLI entry points (ll-loop, ll-parallel, ll-sprint) to activate extension callbacks at run time.

```python
from little_loops.extension import wire_extensions
from little_loops.events import EventBus

bus = EventBus()
extensions = wire_extensions(bus, config.extensions)
```

**Signature:**
```python
def wire_extensions(
    bus: EventBus,
    config_paths: list[str] | None = None,
    executor: FSMExecutor | None = None,
) -> list[LLExtension]
```

**Parameters:**
- `bus` - The `EventBus` instance to register extensions on.
- `config_paths` - Optional list of `"module.path:ClassName"` strings (from `BRConfig.extensions`). Pass `None` or omit to skip config-path loading (entry-point discovery still runs).
- `executor` - Optional `FSMExecutor` to populate with contributed actions, evaluators, and interceptors from loaded extensions.

**Returns:** List of all successfully loaded extension instances (from both config paths and entry points).

**Behavior:**
- Calls `ExtensionLoader.load_all(config_paths)` to discover extensions from both config paths and Python entry points.
- For each loaded extension, wraps `ext.on_event` to convert the raw event dict into an `LLEvent` (using `LLEvent.from_raw_event()`, which copies the dict to prevent mutation), then calls `bus.register(callback, filter=getattr(ext, "event_filter", None))` — forwarding any `event_filter` declared on the extension class.
- The forwarded `event_filter` is matched against the event's `type` field using `fnmatch` glob patterns. `None` (the default) means the extension receives every event.
- When `executor` is provided, a second pass populates `executor._contributed_actions`, `executor._contributed_evaluators`, and `executor._interceptors` from each extension that implements the corresponding protocols (`ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension`).
- The same second pass also merges any `LLHookIntentExtension.provided_hook_intents()` mappings into the module-level `_HOOK_INTENT_REGISTRY` in `little_loops.hooks` (detected via `hasattr()`), making the contributed `name → Callable[[LLHookEvent], LLHookResult]` handlers available to `little_loops.hooks.main_hooks()` for dispatch by the host adapters under `hooks/adapters/<host>/`.

**Error handling:**
- **Load failures** — both `ExtensionLoader.from_config()` and `from_entry_points()` catch all exceptions per extension, log a `WARNING` with the full traceback, and continue. A single bad extension never prevents others from loading; `wire_extensions` returns a partial list of the extensions that did succeed.
- **Runtime failures** — if an extension's `on_event` raises during `EventBus.emit()`, the exception is caught and logged at `WARNING` level. Other registered observers still receive the event.
- **Duplicate key conflicts** — if two extensions provide the same action or evaluator key, `wire_extensions` raises `ValueError: "Extension conflict: action/evaluator '<key>' already registered by another extension"`.

### LLHookIntentExtension

Optional mixin Protocol that extensions implement to contribute hook intent handlers. Detected by `wire_extensions()` via `hasattr(ext, "provided_hook_intents")` (same duck-typing pattern as `ActionProviderExtension`, `EvaluatorProviderExtension`, and `InterceptorExtension`).

```python
@runtime_checkable
class LLHookIntentExtension(Protocol):
    def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `provided_hook_intents() -> dict[str, Callable[[LLHookEvent], LLHookResult]]` | Return a mapping of intent name → handler. Handler signature must match `(LLHookEvent) -> LLHookResult`. Called once at wire time. |

**Behavior:**
- `wire_extensions()` calls `_register_hook_intents(ext.provided_hook_intents())` for each extension that implements the Protocol, merging the result into the module-level `_HOOK_INTENT_REGISTRY` in `little_loops.hooks`.
- Duplicate intent names **across extensions** raise `ValueError` at wire time — first-loaded wins is not the policy; collisions are an error.
- Built-in intents (`pre_compact`, `pre_compact_handoff`, `session_start`, `session_end`, `user_prompt_submit`, `post_tool_use`, `pre_tool_use`) shadow extension-registered intents on collision: `_dispatch_table()` returns `{**_HOOK_INTENT_REGISTRY, **built_ins}`, so a built-in always wins.
- The same `little_loops.extensions` entry-point group used for `LLExtension` also discovers `LLHookIntentExtension` providers (per FEAT-1116 Decision 2 — single shared group; FEAT-1117 group-split is deferred). See [Configuration → `extensions`](CONFIGURATION.md#extensions).

**Usage:**

```python
from little_loops.hooks import LLHookEvent, LLHookResult

class MyHookIntents:
    """Extension contributing a custom 'license_check' hook intent."""

    def provided_hook_intents(self):
        return {"license_check": self._license_check}

    def _license_check(self, event: LLHookEvent) -> LLHookResult:
        if event.payload.get("license") == "GPL":
            return LLHookResult(exit_code=2, feedback="GPL files not allowed.")
        return LLHookResult(exit_code=0)
```

Register via the same `extensions` config key or entry-point group as any other `LLExtension`:

```toml
[project.entry-points."little_loops.extensions"]
my_hook_intents = "my_package:MyHookIntents"
```

After installation, `python -m little_loops.hooks license_check` dispatches to `MyHookIntents._license_check`.

### Configuration

Extensions are configured in `.ll/ll-config.json` via the `extensions` key:

```json
{
  "extensions": [
    "my_package.ext:MyExtension",
    "another_package:AnotherExtension"
  ]
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `extensions` | `array` of `string` | `[]` | Extension module paths to load. Format: `"module.path:ClassName"`. Extensions receive structured events from the EventBus. |

External packages can also register extensions for automatic discovery via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."little_loops.extensions"]
my_ext = "my_package:MyExtension"
```

### Creating a Custom Extension

```python
from little_loops.events import LLEvent

class MyExtension:
    """Custom extension that handles issue completion events."""

    def on_event(self, event: LLEvent) -> None:
        if event.type == "issue.completed":
            print(f"Issue completed: {event.payload.get('id', 'unknown')}")
```

Register via config (`"my_package:MyExtension"`) or entry point. The class must implement `on_event(self, event: LLEvent) -> None` to satisfy the `LLExtension` protocol.

### LLTestBus

```python
from little_loops.testing import LLTestBus
```

Offline replay engine for testing `LLExtension` implementations without a running `ll-loop` or live `EventBus`. Load a JSONL events file recorded during a real run, register your extension, and call `replay()` to drive `on_event` with the recorded events. Unlike the live `EventBus`, exceptions from extensions propagate immediately so tests see raw failures.

```python
bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
ext = MyExtension()
bus.register(ext)
bus.replay()
assert len(bus.delivered_events) == 15
```

**Constructor:**

```python
LLTestBus(events: list[LLEvent])
```

Create from a pre-parsed list of `LLEvent` objects. Initializes `delivered_events` to an empty list.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `delivered_events` | `list[LLEvent]` | Events delivered to at least one registered extension during the last `replay()` call. Reset at the start of each `replay()` — not accumulated across calls. |

**Class methods:**

```python
@classmethod
def from_jsonl(cls, path: str | Path) -> LLTestBus
```

Load events from a JSONL file (one JSON object per line). Returns an empty `LLTestBus` if the file does not exist. Malformed lines are silently skipped.

Each line must be a JSON object with at minimum an `"event"` key (the event type string) and a `"ts"` key (ISO 8601 timestamp). All other keys become payload attributes:

```json
{"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop": "test-loop"}
{"event": "issue.closed", "ts": "2025-01-01T00:00:01", "issue": "BUG-001"}
```

**Methods:**

```python
def register(self, ext: LLExtension) -> None
```

Register an extension to receive events during `replay()`. Accepts any object implementing the `LLExtension` protocol. May be called multiple times to register multiple extensions. Extensions can optionally declare an `event_filter` class attribute (see below).

```python
def replay(self) -> None
```

Reset `delivered_events` to `[]`, then deliver all loaded events to every registered extension in order. For each event, each extension's `event_filter` attribute is checked (via `fnmatch` glob matching against the event type). If the filter matches — or if the extension has no filter — `on_event(event)` is called. An event is added to `delivered_events` if at least one extension received it. Exceptions from extensions are **not** caught and propagate immediately.

**Event filtering:**

Extensions can opt in to a subset of events by declaring `event_filter` as a class attribute:

```python
class MyExtension:
    event_filter = "issue.*"          # single glob pattern
    # event_filter = ["loop_*", "issue.*"]  # or a list of patterns
    # event_filter = None             # or absent — receives all events

    def on_event(self, event: LLEvent) -> None: ...
```

Patterns use `fnmatch` glob syntax matched against `event.type`. `None` or a missing attribute means the extension receives every event.

**Example:**

```python
from pathlib import Path
from little_loops.testing import LLTestBus

class CountingExtension:
    event_filter = "issue.*"  # only issue.* events

    def __init__(self):
        self.count = 0

    def on_event(self, event):
        self.count += 1

ext = CountingExtension()
bus = LLTestBus.from_jsonl(Path("tests/fixtures/recorded.jsonl"))
bus.register(ext)
bus.replay()
assert ext.count == 3
assert len(bus.delivered_events) == 3  # only issue.* events delivered
```

> **Tip:** The scaffold generated by `ll-create-extension` includes a starter test using `LLTestBus` in `tests/test_extension.py`.

---

## little_loops.skill_expander

Pre-expands skill and command Markdown files into self-contained prompt strings for subprocess invocation. Used by `ll-auto` to eliminate the `ToolSearch → Skill` deferred-tool round-trip when spawning Claude subprocesses.

### expand_skill

```python
def expand_skill(name: str, args: list[str], config: BRConfig) -> str | None
```

Reads the Markdown source for *name*, strips frontmatter, substitutes `{{config.xxx}}` placeholders, converts relative `(file.md)` link targets to absolute paths, and replaces the `$ARGUMENTS` token with the joined *args*.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Skill or command name (e.g. `"manage-issue"`, `"ready-issue"`) |
| `args` | `list[str]` | Arguments that would normally follow the slash command |
| `config` | `BRConfig` | Project configuration used for `{{config.xxx}}` placeholder substitution |

**Returns**: Fully-expanded prompt string, or `None` on any failure (file not found, substitution error, etc.). Callers should fall back to the original slash command when `None` is returned.

**Resolution order**: `skills/{name}/SKILL.md` → `commands/{name}.md`

**Plugin root**: Reads `CLAUDE_PLUGIN_ROOT` env var first; falls back to the directory three levels above `skill_expander.py`.

**Example**

```python
from little_loops.config import BRConfig
from little_loops.skill_expander import expand_skill

config = BRConfig(Path.cwd())
prompt = expand_skill("ready-issue", ["FEAT-123"], config)
if prompt is None:
    prompt = "/ll:ready-issue FEAT-123"  # fallback
```

## little_loops.init.install_check

Installation detection and version-comparison helpers used by `ll-init` to detect package drift and auto-upgrade. All network calls are offline-safe: every function returns `None` on timeout, missing binary, or parse failure.

### InstallStatus

```python
class InstallStatus(Enum):
    UpToDate     = "up_to_date"
    OutOfDate    = "out_of_date"
    NotInstalled = "not_installed"
    Unknown      = "unknown"
```

### detect_installation

```python
def detect_installation(project_root: Path) -> tuple[str | None, str | None, str | None]
```

Detects the active little-loops installation. Checks pip metadata first; falls back to `<host> plugin list --json` for global/project plugin installs. The plugin-check binary is resolved via `resolve_host()` rather than a hardcoded `claude` literal (CLAUDE.md host-abstraction rule), so the check is skipped cleanly when no host CLI is configured.

**Returns**: `(install_source, installed_version, install_path)` where `install_source` is one of `"local-editable"`, `"pypi"`, `"global-claude-code"`, `"project-claude-code"`, or `None` (not found). `installed_version` is the version string for pip-based and claude-code plugin installs (populated via `--json` flag; `None` if the CLI is too old to support it). `install_path` is the `installPath` from the plugin JSON for claude-code plugin installs; `None` otherwise.

| `install_source` value | Meaning |
|------------------------|---------|
| `"local-editable"` | Installed via `pip install -e` (dev / contributor path) |
| `"pypi"` | Installed via `pip install little-loops` (end-user path) |
| `"global-claude-code"` | Installed as a user-scoped Claude Code plugin (`scope: "user"`) |
| `"project-claude-code"` | Installed as a project-scoped Claude Code plugin (`scope: "project"`) |
| `None` | Not found |

### installed_package_version

```python
def installed_package_version() -> str | None
```

Returns the installed `little-loops` package version via `importlib.metadata.version`, or `None` when the package is not installed. Single source of truth for the codex adapter gen-version stamp (written by `install_codex_adapter`) and the warn-only staleness comparison in `ll-init`.

### fetch_latest_pypi

```python
def fetch_latest_pypi(timeout: float = 10.0) -> str | None
```

Fetches the latest little-loops release version from PyPI using `pip index versions`. Parses the `LATEST:` line. Returns `None` on any failure (offline, timeout, pip not available).

### fetch_latest_plugin

```python
def fetch_latest_plugin(timeout: float = 10.0) -> str | None
```

Fetches the latest `ll@little-loops` plugin version from the Claude Code marketplace. Uses `resolve_host()` — never hardcodes the `claude` binary. Returns `None` when the host CLI is not configured or the call fails. Only meaningful when the `claude-code` host is active.

### check_version

```python
def check_version(installed: str, latest: str) -> InstallStatus
```

Compares an installed version string against the latest available version using semver-aware tuple comparison. Returns `InstallStatus.UpToDate` when `installed >= latest` (including when the local build is newer than PyPI), `InstallStatus.OutOfDate` when `installed < latest`. Does not perform network I/O; call `fetch_latest_pypi` / `fetch_latest_plugin` first.

---

## Agents

Specialized sub-agents live in `agents/*.md` and are registered in `.claude-plugin/plugin.json`. Each agent is spawned via the `Task` / `Agent` tool with `subagent_type` set to the agent name. Codex-CLI mirrors are generated into `.codex/agents/*.toml` by `ll-adapt --host codex --apply`.

| Agent | Model | Tools | Purpose |
|-------|-------|-------|---------|
| [`codebase-analyzer`](../../agents/codebase-analyzer.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Trace HOW code works — implementation details, data flows, integration points, anchor-based references. |
| [`codebase-locator`](../../agents/codebase-locator.md) | haiku | Read, Glob, Grep, WebFetch, WebSearch | Find WHERE code lives — file paths grouped by purpose without reading contents. |
| [`codebase-pattern-finder`](../../agents/codebase-pattern-finder.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Extract concrete code examples of patterns and conventions to model new work after. |
| [`consistency-checker`](../../agents/consistency-checker.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Validate cross-component references between CLAUDE.md, agents, skills, commands, hooks, and MCP config. |
| [`loop-specialist`](../../agents/loop-specialist.md) | sonnet | Bash, Read, Edit, Write | Monitor, diagnose, refine, and verify FSM loops; classifies failures against the seven-mode taxonomy (including `evaluator-trivial`) and writes diagnosis artifacts to `.loops/diagnostics/`. |
| [`plugin-config-auditor`](../../agents/plugin-config-auditor.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Audit individual agent/skill/command/hook definitions for quality, completeness, and best practices. |
| [`prompt-optimizer`](../../agents/prompt-optimizer.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch, Write | Gather codebase context so vague user prompts can be rewritten with specific references and conventions. |
| [`web-search-researcher`](../../agents/web-search-researcher.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch, Bash | Fetch current external documentation, release notes, and best-practice references beyond the training cutoff. |
| [`workflow-pattern-analyzer`](../../agents/workflow-pattern-analyzer.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch, Write | Categorize extracted user messages and emit `step1-patterns.yaml` for the three-step workflow-analysis pipeline. |

## Loops

Built-in loops live in `scripts/little_loops/loops/`. Full documentation and a decision guide are in [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md).

### `rn-build` — Spec-to-Project Capstone Orchestrator

**Category**: orchestration  
**File**: `scripts/little_loops/loops/rn-build.yaml`  
**Required input**: `spec` (path to spec Markdown file)

End-to-end spec-to-project pipeline. Accepts a spec Markdown file and drives: spec validation → tech research → design artifacts → commit → scope EPIC + feature stubs → issue refinement → eval harness → `goal-cluster` (batched `rn-implement`, `value_ranked` scheduling) → eval gate with bounded re-entry → structured JSON result.

Uses value-ranked scheduling via `rn-implement` + `goal-cluster` rather than an `eval-driven-development` sub-loop.

**CLI invocation:**

```bash
ll-loop run rn-build --context spec=specs/sample.md

# Multiple spec files (comma-separated)
ll-loop run rn-build --context spec=specs/backend.md,specs/frontend.md
```

**Key phases:**

| Phase | States | Description |
|-------|--------|-------------|
| 0 — Resume (optional) | `resume`, `resume_read_harness` | Skip front half; re-enter `cluster_execute` for an already-scoped EPIC. Entered when `resume_epic` is set |
| 1 — Spec validation | `init` | Reads and validates the spec file(s); halts with clear error if required sections are missing |
| 2 — Research & design | `tech_research`, `design_artifacts`, `commit_design` | LLM tech research → generates architecture and design artifacts → commits them to the working tree |
| 3 — Scope | `scope_project`, `write_epic_id`, `enumerate_epic_children`, `refine_seed` | Runs `/ll:scope-epic` to create EPIC + feature stubs, captures EPIC ID, enumerates child issues, refines them via `recursive-refine` (depth-first, handles size-review decomposition) |
| 4 — Eval harness | `eval_harness`, `read_harness_name` | Installs an eval harness loop keyed to the spec's acceptance criteria |
| 5 — Execution | `cluster_execute` | Delegates to `goal-cluster` which batches issues and dispatches each batch to `rn-implement` with `schedule_mode=value_ranked` |
| 6 — Eval gate | `check_harness_name`, `eval_gate`, `check_eval_retry_budget`, `capture_eval_failures` | Runs eval harness; on failure, captures failing scenarios as new issues and re-enters `cluster_execute` (bounded by `max_eval_retries`) |
| 7 — Result | `synthesize_result`, `done` | Emits a structured JSON summary of the build outcome; includes `resume_command` when `eval_passed: false` |

**Context knobs:**

| Variable | Default | Description |
|----------|---------|-------------|
| `spec` | `""` | **Required.** Path(s) to spec Markdown file(s), comma-separated. |
| `max_eval_retries` | `"2"` | Maximum `eval_gate` retry cycles before accepting a partial result. |
| `harness_name` | `""` | Auto-populated: name of the installed eval harness loop. Do not set manually. |
| `epic_id` | `""` | Auto-populated: EPIC ID from `scope_project`. Do not set manually. |
| `resume_epic` | `""` | **Resume only.** EPIC ID from a prior run. When set, `init` skips spec validation and routes to `resume`, which re-enters `cluster_execute`. |
| `resume_harness` | `""` | **Resume only.** Harness loop name from a prior run. Passed to `eval_gate` via `resume_read_harness`. |

**Internal dispatch flags** (fixed; set automatically, not user-facing):

| Flag | Value | Effect |
|------|-------|--------|
| `schedule_mode` | `value_ranked` | Passed to each `rn-implement` batch via `goal-cluster`; issues are implemented in value-ranked order |
| `propagate_context` | `true` | Cluster propagates context across batches so later batches can incorporate earlier-batch results |

**Loop settings**: `max_steps: 30`, `timeout: 86400s` (24h), `on_handoff: spawn` (auto-resumes across session boundaries).
