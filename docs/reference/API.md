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
| `little_loops.subprocess_utils` | Subprocess handling |
| `little_loops.host_runner` | Host-agnostic CLI invocation layer (`HostRunner` Protocol + `ClaudeCodeRunner` + `CodexRunner` + `OpenCodeRunner` + `PiRunner`) |
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
| `little_loops.history_reader` | Typed read-only query module for `.ll/history.db`. Exports: `UserCorrection`, `FileEvent`, `SearchResult`, `IssueEvent`, `SessionRef` (ENH-1711) dataclasses; `find_user_corrections()`, `recent_file_events()`, `search()`, `related_issue_events()`, `sessions_for_issue(issue_id, *, limit, db)` (ENH-1711), `issue_effort(issue_id, *, db)`, `recent_issue_velocity(limit, *, db)` (ENH-1905), `lookup_session_metadata(session_id, *, db)` (ENH-1943), `conversation_turns(db_path, *, since, context_window)` (ENH-1942) query functions. All functions return empty lists or `None` on missing/corrupt DB. |
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
| `active_theme` | `str` | `"light"` | Name of the active theme; must match a file in `themes_dir`. |

#### DecisionsConfig

Controls the decisions and rules log. See [CONFIGURATION.md → `decisions`](CONFIGURATION.md#decisions) for setup guidance.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `False` | Enable the decisions log feature. When `False`, all integrations gracefully skip. |
| `log_path` | `str` | `".ll/decisions.yaml"` | Path to the decisions log file, relative to the project root. |
| `auto_generate` | `list[str]` | `[]` | Sources to auto-generate decision entries from (e.g., `["completed"]`). |

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

##### get_completed_dir

```python
def get_completed_dir(self) -> Path
```

> **Deprecated:** Use `IssueInfo.status` instead. This method emits `DeprecationWarning` and will be removed in a future release.

Get the path to the completed issues directory.

##### get_deferred_dir

```python
def get_deferred_dir(self) -> Path
```

> **Deprecated:** Use `IssueInfo.status` instead. This method emits `DeprecationWarning` and will be removed in a future release.

Get the path to the deferred issues directory.

**Returns:** `Path` to the deferred issues directory

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
    merge_pending: bool = False,
    clean_start: bool = False,
    ignore_pending: bool = False,
    overlap_detection: bool = False,
    serialize_overlapping: bool = True,
    base_branch: str = "main",
) -> ParallelConfig
```

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
- `merge_pending` - Attempt to merge pending worktrees from previous runs
- `clean_start` - Remove all worktrees without checking for pending work
- `ignore_pending` - Report pending work but continue without merging
- `overlap_detection` - Enable pre-flight overlap detection
- `serialize_overlapping` - If True, defer overlapping issues; if False, just warn
- `base_branch` - Base branch for rebase/merge operations

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
    worktree_copy_files: list[str] = field(default_factory=lambda: [".claude/settings.local.json", ".env"])
    require_code_changes: bool = True
    use_feature_branches: bool = False
    remote_name: str = "origin"
```

**Fields:**
- `worktree_copy_files` - Files copied from main repo to each worktree
- `require_code_changes` - Fail issues that don't produce code changes
- `use_feature_branches` - Create `feature/<id>-<slug>` branches instead of auto-merged worktree branches; skips auto-merge, leaving branches as PR-ready
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
    sprints_dir: str = ".sprints"        # Directory for sprint YAML files
    default_timeout: int = 3600          # Default per-issue timeout in seconds
    default_max_workers: int = 2         # Default worker count for wave execution
```

### LoopsConfig

FSM loop configuration.

```python
@dataclass
class LoopsConfig:
    loops_dir: str = ".loops"    # Directory for loop YAML definitions
```

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
    depends_on: list[str] = []            # Soft ordering prerequisites (preferred ordering, not wave-gated)
    relates_to: list[str] = []            # Thematically related issue IDs (no ordering constraint)
    duplicate_of: str | None = None        # Issue ID this duplicates; set when closing a duplicate
    discovered_by: str | None = None       # Source command/workflow that created this issue
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
    learning_tests_required: list[str] | None = None  # Declared assumptions about external systems; /ll:ready-issue checks each via ll-learning-tests check
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
2. All required sections for its type template are present as `##` headings.

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `templates_dir` - Optional override for the templates directory

**Returns:** `True` if the issue passes either criterion; `False` for files whose type cannot be determined or whose template cannot be loaded

#### find_issues

```python
def find_issues(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: list[str] | set[str] | None = None,
    type_prefixes: set[str] | None = None,
    status_filter: set[str] | None = None,
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

**Returns:** List of `IssueInfo` sorted by priority

**Example:**
```python
from little_loops.issue_parser import find_issues

issues = find_issues(config, category="bugs")
for issue in issues:
    print(f"{issue.priority} {issue.issue_id}: {issue.title}")
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
def get_next_issue_number(config: BRConfig, category: str) -> int
```

Determine the next issue number for a category.

**Parameters:**
- `config` - Project configuration
- `category` - Category key

**Returns:** Next available issue number

#### slugify

```python
def slugify(text: str) -> str
```

Convert text to slug format for filenames.

**Parameters:**
- `text` - Text to convert

**Returns:** Lowercase slug with hyphens

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

### Public Functions (25)

#### Parsing & Scanning

| Function | Purpose |
|----------|---------|
| `parse_completed_issue(file_path, *, batch_dates=None)` | Parse a single completed issue file |
| `scan_completed_issues(completed_dir)` | Scan completed directory for all issues |
| `scan_active_issues(base_dir, categories)` | Scan active issue directories |

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
| `TestGap` | A source file with bugs but missing/weak test coverage |
| `TestGapAnalysis` | Container for test gap analysis results |
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
completed_dir = Path(".issues/completed")
issues = scan_completed_issues(completed_dir)
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
    verbose: bool = True,
    label_filter: set[str] | None = None,
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
- `verbose` - Whether to output progress messages
- `label_filter` - If provided, only process issues carrying one of these labels
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
    on_usage: UsageCallback | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
) -> subprocess.CompletedProcess[str]
```

Host-agnostic CLI command invocation with output streaming (delegates to `host_runner.resolve_host().build_streaming()`; retained as a public alias for the pre-`host_runner` call surface).

**Parameters:**
- `command` - Command to pass to Claude CLI
- `logger` - Logger for output
- `timeout` - Timeout in seconds
- `stream_output` - Whether to stream output to console
- `idle_timeout` - Kill process if no output for this many seconds (0 to disable)
- `on_model_detected` - Optional callback invoked with the model name from the stream-json system/init event
- `on_usage` - Optional callback invoked with `(input_tokens, output_tokens)` from the stream-json result event. `input_tokens` includes `cache_read_input_tokens`.
- `agent` - Claude agent model override; appended as `--agent <value>` to CLI invocation
- `tools` - Restrict available tools; appended as `--tools <value>` to CLI invocation

**Returns:** `CompletedProcess` with stdout/stderr captured. When a `result` event with `is_error=True` is present in the stream-json output, `CompletedProcess.stderr` will include a `[result] <error>` line containing the error text from the result event's `error` field (falling back to the `result` field).

#### verify_issue_completed

```python
def verify_issue_completed(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger
) -> bool
```

Verify that an issue was moved to completed directory.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration
- `logger` - Logger for output

**Returns:** `True` if issue is in completed directory

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

Move an issue from its active category directory to `deferred/`.

Appends a `## Deferred` section to the issue file with the reason and date, then commits the move.

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
- `deferred_issue_path` - Path to the issue file in `deferred/`
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
new_path = undefer_issue(config, Path(".issues/deferred/P3-FEAT-042-example.md"), logger)
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
StateManager(state_file: Path, logger: Logger)
```

**Parameters:**
- `state_file` - Path to the state file
- `logger` - Logger instance for output

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
| `update_current(path, phase)` | Update current issue and phase |
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
    content: str           # The text content of the message
    timestamp: datetime    # When the message was sent
    session_id: str        # Claude Code session identifier
    uuid: str              # Unique message identifier
    cwd: str | None        # Working directory when sent
    git_branch: str | None # Git branch active when sent
    is_sidechain: bool     # Whether this was a sidechain message
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
from JSONL records first, then falling back to string-replacing ``-`` with ``/``.
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
)
```

**Parameters:**
- `parallel_config` - Parallel processing configuration
- `br_config` - Project configuration
- `repo_path` - Path to the git repository (default: current directory)
- `verbose` - Whether to output progress messages

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
| `submit(issue_info, callback) -> Future` | Submit issue for processing |
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
    worktree_base: Path
    state_file: Path
    max_merge_retries: int = 2
    priority_filter: list[str]
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
    only_ids: set[str] | None = None
    skip_ids: set[str] | None = None
    type_prefixes: set[str] | None = None
    require_code_changes: bool = True
    worktree_copy_files: list[str]
    merge_pending: bool = False
    clean_start: bool = False
    ignore_pending: bool = False
    overlap_detection: bool = False
    serialize_overlapping: bool = True
    base_branch: str = "main"
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
    branch_name: str                # Git branch (parallel/<issue-id>-<timestamp>)
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

**Returns:** Exit code

### main_loop

```python
def main_loop() -> int
```

Entry point for `ll-loop` command. FSM-based automation loop execution.

**Returns:** Exit code

### main_issues

```python
def main_issues() -> int
```

Entry point for `ll-issues` command. Issue management and visualization utilities.

**Returns:** Exit code

**Sub-commands:**

| Sub-command | Description |
|-------------|-------------|
| `next-id` | Print next globally unique issue number |
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
| `check-readiness` | Exit 0 if `confidence_score` and `outcome_confidence` meet thresholds; reads from `ll-config.json` or `--readiness`/`--outcome` flags |

#### next-issue

```
ll-issues next-issue [--json] [--path] [--skip ISSUE_IDS]
ll-issues nx [--json] [--path] [--skip ISSUE_IDS]
```

Print the single highest-confidence active issue ID. Uses the same sort key as `next-issues`.

**Output flags:**
- `--json` - Output as a JSON object with fields: `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`
- `--path` - Output only the file path instead of the issue ID

**Filter flags:**
- `--skip ISSUE_IDS` - Comma-separated list of issue IDs to exclude (e.g., `BUG-003,FEAT-004`). Useful in FSM loops to skip issues already attempted in the current session.

**Exit codes:** 0 when an issue is found; 1 when no active issues exist (after filtering).

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
ll-issues next-issue                      # print top issue ID
ll-issues nx --json                       # top issue as JSON object
ll-issues nx --path                       # top issue file path
ll-issues nx --skip BUG-003,FEAT-004      # skip specific issues
```

**FSM loop use**: Use `--skip` to avoid re-selecting issues already processed in the current loop run. Pair with `next-issues` when you need the full ranked list.

#### next-issues

```
ll-issues next-issues [COUNT] [--json] [--path]
ll-issues nxs [COUNT] [--json] [--path]
```

Print all active issues sorted by outcome confidence, readiness score, and priority. Returns one issue ID per line by default.

**Arguments:**
- `COUNT` - Optional integer; limit output to top N issues

**Output flags:**
- `--json` - Output as a JSON array with fields: `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`
- `--path` - Output one file path per line instead of IDs

**Exit codes:** 0 when at least one issue found; 1 when no active issues exist.

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
ll-issues next-issues           # all active issues ranked
ll-issues next-issues 5         # top 5 only
ll-issues nxs --json            # ranked list as JSON array
ll-issues nxs --path            # ranked list as file paths
```

**FSM loop use**: Pair with `ll-issues next-issue` (singular) when you need only the top item; use `next-issues` when you want to seed a loop queue or inspect the full ranked backlog.

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

**`--json` output fields**: `issue_id`, `title`, `priority`, `status`, `effort`, `confidence`, `outcome`, `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`, `summary`, `integration_files`, `risk`, `labels`, `history`, `path`, `source`, `norm`, `fmt`

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
- `--max-workers` - Number of parallel workers
- `--timeout` - Per-issue timeout in seconds
- `--issues` - Specific issue IDs to process

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

**Sub-commands:** `analyze`, `validate`, `fix`, `apply`, `tree`

### main_verify_docs

```python
def main_verify_docs() -> int
```

Entry point for `ll-verify-docs` command. Verify that documented counts match actual file counts in the project.

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
- `sequences` — Extract tool-chain n-grams of ll invocations from JSONL logs; requires `--project DIR` or `--all`; options: `--min-len N` (default 2), `--min-count M` (default 1), `--top N`, `--window-days D`, `--json`; JSON schema: `[{chain: [str], count: int, edges: [{from, to, freq}]}]`
- `stats` — Aggregate per-skill invocation frequency and correction rate from `skill_events` in `.ll/history.db`; requires `--project DIR` or `--all`; options: `--window-days D`, `--sort {freq,corrections}` (default freq), `--json`; JSON schema: `[{skill: str, invocations: int, corrections: int, correction_rate: float, errors: null, error_rate: null}]`
- `dead-skills` — Cross-reference skill catalog against log corpus to flag never/rarely-invoked skills; requires `--project DIR` or `--all`; options: `--window-days D`, `--threshold N` (default 3), `--json`; JSON schema: `[{skill: str, invocations: int, tier: "never"|"rarely"}]`; excludes bridge skills and `disable-model-invocation: true` entries
- `scan-failures` — Mine failed `ll-*` Bash calls from interactive session JSONL logs; requires `--project DIR` or `--all`; options: `--window-days D`, `--json`, `--capture`; clusters failures by `(tool, normalized-error-signature)`, suppresses transient errors and `ll-verify-*` expected-nonzero gates; JSON schema: `[{tool: str, count: int, normalized_sig: str, sample_error: str, session_ids: [str]}]`; `--capture` creates a BUG issue file per cluster via `create_issue_from_failure()`
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
- `tail` — Stream live events from an active loop session; requires `--loop NAME`

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
- `search` — FTS5 full-text query with BM25-ranked results; requires `--fts QUERY`, optional `--limit N` (default 20)
- `recent` — Most recent rows for an event kind; requires `--kind {tool,file,issue,loop,correction,message,skill,cli}`, optional `--limit N` (default 20)
- `backfill` — Seed the database from existing on-disk sources; `--since DATE` (ISO 8601 or YYYY-MM-DD) uses incremental JSONL-only mode via `backfill_incremental()` (ENH-1830); output includes `corrections=N` count of user-correction rows mined from `message_events` (ENH-1904). `--host {claude-code,codex,opencode,pi}` selects the host for session log discovery (default: auto-detect from ``LL_HOOK_HOST`` env var); full backfill (no ``--since``) also uses ``--host`` for JSONL file discovery (ENH-1945)
- `related` — Issue events for a given issue ID; requires `ISSUE_ID` positional arg, optional `--limit N` and `--json`
- `path` — Resolve and print the JSONL file path for a session ID; exits non-zero if unknown

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

Entry point for `ll-ctx-stats` command. Show context-window analytics for the current project (FEAT-1160). Reads per-tool byte metrics that the `post_tool_use` hook persists into `.ll/history.db` (FEAT-1623) and renders a compact summary of how much data was processed by tools vs. how much actually entered the conversation context. Falls back to `.ll/ll-context-state.json` (token estimates) when the SQLite store is absent.

**Returns:** 0 when a report was rendered (data present or fallback used), 1 when no data found in either the SQLite store or the fallback file.

**Flags:**
- `--db PATH` — Use a non-default session database (default `.ll/history.db`)
- `--json` — Emit the report as JSON instead of the human-readable summary

Enable per-tool byte tracking by setting `"analytics": {"enabled": true}` in `.ll/ll-config.json`. The `post_tool_use` hook reads this gate and no-ops when disabled or absent. Use `analytics.capture` for per-category control (e.g. `analytics.capture.file_events: false` disables file-event recording while keeping tool-event metrics active). See [CONFIGURATION.md § analytics.capture](CONFIGURATION.md#analyticscapture) for the full key reference.

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
def calculate_boundary_weight(time_gap_seconds: float) -> float
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
completed_dir = config.get_completed_dir()
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
| `little_loops.fsm.stall_detector` | `StallDetector` and `Stall` dataclass for circuit-breaker stall detection |
| `little_loops.fsm.fragments` | Fragment composition: `resolve_fragments()`, `resolve_inheritance()`, `resolve_flow()` |

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
    context: dict[str, Any] = {}       # User-defined shared variables
    scope: list[str] = []              # Paths for concurrency control
    max_iterations: int = 50           # Safety limit
    on_max_iterations: str | None = None  # State to run once when cap fires (ENH-1631)
    max_edge_revisits: int = 100       # Per-edge cycle detection limit (see below)
    backoff: float | None = None       # Seconds between iterations
    timeout: int | None = None         # Max runtime in seconds
    maintain: bool = False             # If True, restart after completion
    llm: LLMConfig = LLMConfig()       # LLM evaluation settings
    commands: list[CommandEntry] = []  # Optional Commands section override for ll-loop show
    targets: list[TargetFileSpec] = []  # Per-FSM-state targeting spec for harness-optimize APO (ENH-1552)
    circuit: CircuitConfig | None = None  # Top-level safety knobs; currently the stall detector (FEAT-1637)
    meta_self_eval_ok: bool = False       # Suppress MR-1/MR-2 meta-loop lint rules (ENH-1665)
    shared_state_ok: bool = False         # Suppress MR-3 artifact-isolation lint rule
    partial_route_ok: bool = False        # Suppress MR-4 partial-route dead-end lint rule (ENH-1917)
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

@dataclass
class CircuitConfig:
    repeated_failure: RepeatedFailureConfig | None = None
```

The stall detector records `(state_name, exit_code, eval_verdict)` after every transition and fires when the last `window` triples are identical. When `on_repeated_failure == "abort"` the run terminates with `terminated_by="stall_detected"` (exit code 1); otherwise the executor routes to the named state. Each firing also emits a `stall_detected` event with `state`, `exit_code`, `verdict`, `consecutive`, and `action` fields.

**`progress_paths` — fingerprint-based reset (BUG-1674):** Loops with a check↔work ping-pong where the work state uses `next:` (no `evaluate:`) are invisible to the detector — only the eval-bearing state records triples, so three identical `check` verdicts fire the stall even when `work` made real file-level progress. Set `progress_paths` to a list of paths (supports `${env.PWD}` interpolation) to watch: if any path's `(mtime, size)` changes between two consecutive records for the same eval-bearing state, the rolling window resets. Empty by default — existing loops without this field retain current semantics.

**`exclude_paths` — bookkeeping file exclusion (BUG-1767):** When a loop's own internal tracking files (plan, DoD, scratchpad) are listed in `progress_paths`, every append to those files resets the stall window, silently disabling stall detection. Add such files to `exclude_paths` so the executor filters them out before computing the fingerprint. Paths support `${env.PWD}` interpolation. `ll-loop validate` emits a WARNING when a state action references a `progress_paths` file that is not also in `exclude_paths`.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert to dictionary for serialization |
| `from_dict(data)` | `FSMLoop` | Create from dictionary |
| `get_all_state_names()` | `set[str]` | All defined state names |
| `get_terminal_states()` | `set[str]` | States with `terminal=True` |
| `get_all_referenced_states()` | `set[str]` | All states referenced by transitions |

When any single state→state edge (e.g., `evaluate → fix`) is traversed more than `max_edge_revisits` times, the loop terminates immediately with `terminated_by="cycle_detected"` (exit code 1) rather than continuing until `max_iterations` is reached. This prevents tight infinite loops where two states bounce between each other indefinitely without making progress. Edge counts are persisted in `LoopState` so they survive a `--resume`. The default value of `100` covers all practical loops; lower it on short single-purpose loops to catch regressions faster.

```yaml
# Example: tighten cycle guard on a short loop
name: quick-check
max_iterations: 10
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
    max_iterations=20,
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
    max_iterations=5,
)
```

#### StateConfig

Configuration for a single FSM state.

```python
@dataclass
class StateConfig:
    action: str | None = None          # Command to execute
    evaluate: EvaluateConfig | None    # Evaluator configuration
    route: RouteConfig | None          # Full routing table
    on_yes: str | None = None      # Shorthand routing
    on_no: str | None = None      # Shorthand routing
    on_error: str | None = None        # Shorthand routing
    next: str | None = None            # Unconditional transition
    terminal: bool = False             # End state marker
    capture: str | None = None         # Variable name to store output
    timeout: int | None = None         # Action timeout in seconds
    on_maintain: str | None = None     # State for maintain mode restart
    loop: str | None = None            # Sub-loop to invoke (name from .loops/<name>.yaml)
    context_passthrough: bool = False  # Pass parent context vars to child; merge child captures back
    agent: str | None = None           # Subprocess agent name; passes --agent <name> to Claude CLI (prompt states only)
    tools: list[str] | None = None     # Subprocess tool scope; passes --tools <csv> to Claude CLI (prompt states only)
    max_rate_limit_retries: int | None = None        # Short-burst tier budget; requires on_rate_limit_exhausted
    on_rate_limit_exhausted: str | None = None       # Target state when total wall-clock budget spent
    rate_limit_backoff_base_seconds: int | None = None  # Short-tier backoff base (default 30); delay = base * 2^n + jitter
    rate_limit_max_wait_seconds: int | None = None   # Total wall-clock budget across both tiers (default 21600 / 6h)
    rate_limit_long_wait_ladder: list[int] | None = None  # Long-wait ladder (default [300, 900, 1800, 3600]); index caps at last entry
    throttle: ThrottleConfig | None = None           # Per-state progressive tool-call throttling
    on_throttle_hard: str | None = None              # Target state when hard_max is reached (or hard-stop if unset)
    learning: LearningConfig | None = None           # FEAT-1283: type=learning state targets + retry budget
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
        "action_stall",     # Detect repeated action/output for N consecutive iterations
        "llm_structured",   # LLM with structured output
        "mcp_result",       # Parse MCP tool call response envelope
        "harbor_scorer",    # Harbor-format benchmark scorer (exit code + float stdout)
        "comparator",       # Blind A/B comparison against stored baseline via LLM judge
    ]
    operator: str | None = None        # Comparison: eq, ne, lt, le, gt, ge
    target: int | float | str | None   # Target value
    tolerance: float | str | None      # For convergence
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
    baseline_path: str | None = None   # For comparator: path to .loops/baselines/<loop>/ dir
    auto_promote: bool = False          # For comparator: write output to baseline on yes verdict
    min_pairs: int = 1                  # For comparator: number of blind A/B comparison pairs
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
) -> EvaluationResult
```
Check if pattern (regex or substring) exists in output.

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
print(result.terminated_by)   # "terminal", "max_iterations", "timeout", "signal", "cycle_detected", "stall_detected", or "error"
```

#### ExecutionResult

```python
@dataclass
class ExecutionResult:
    final_state: str                      # State when execution stopped
    iterations: int                       # Total iterations
    terminated_by: str                    # "terminal" | "max_iterations" | "timeout" | "signal" | "cycle_detected" | "stall_detected" | "error"
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
| `archive_run()` | Copy state, events, and (for meta-loops) meta-eval to `.loops/.history/<run_id>-<name>/` |

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
```

**Methods:** `to_dict()`, `from_dict(data)`

#### LockManager

```python
class LockManager:
    def __init__(self, loops_dir: Path | None = None) -> None
```

Manage scope-based locks for concurrent loop execution. Lock files are stored in `.loops/.running/<instance_id>.lock`.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `acquire(loop_name, scope, instance_id=None)` | `bool` | Acquire lock; returns `False` if conflict exists |
| `release(loop_name, instance_id=None)` | `None` | Release lock for a loop instance |
| `find_conflict(scope)` | `ScopeLock \| None` | Find conflicting running loop; cleans stale locks |
| `list_locks()` | `list[ScopeLock]` | List all active locks; cleans stale locks |
| `wait_for_scope(scope, timeout=300)` | `bool` | Wait until scope is available; `False` on timeout |

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
| `load_or_resolve(arg)` | `Sprint \| None` | Load sprint by name **or** resolve an EPIC ID (`EPIC-NNN`) to an ephemeral Sprint via forward (`relates_to:`) + backward (`parent:`) lookup, filtered to active statuses |
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

Extract YAML frontmatter from content between opening and closing `---` markers. Parses simple `key: value` pairs.

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

Prefer this over `parse_frontmatter` for SKILL.md files: `parse_frontmatter` deliberately drops block scalars (logs a warning and sets the value to `None`), which loses the description body for skills that use `description: |`.

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
)
```

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
- `query` — FTS5 query string (BM25-ranked results)
- `kind` — optional filter: `tool`, `file`, `issue`, `loop`, `correction`, `message`
- `limit` — maximum number of rows to return (default: 10)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SearchResult` instances ordered by BM25 score. Returns `[]` if the database is unavailable or the FTS5 query syntax is invalid.

### related_issue_events

```python
def related_issue_events(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[IssueEvent]
```

Return issue events for *issue_id*, ordered by most recent first.

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1752"`)
- `limit` — maximum number of rows to return (default: 20)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `IssueEvent` instances ordered by `ts DESC`. Returns `[]` if the database is unavailable.

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
- Claude Code adapters (`hooks/adapters/claude-code/precompact.sh`, `post-tool-use.sh`, `session-start.sh`, `session-end.sh`) invoke `python -m little_loops.hooks <intent>` directly — `LL_HOOK_HOST` defaults to `"claude-code"`.
- The OpenCode adapter (`hooks/adapters/opencode/index.ts`) sets `LL_HOOK_HOST=opencode` before invoking the same CLI.
- The Codex CLI adapter (`hooks/adapters/codex/session-start.sh`, `pre-compact.sh`) sets `LL_HOOK_HOST=codex` before invoking the same CLI. The `hooks.json` template restricts `SessionStart` to `"matcher": "startup"` per FEAT-957's policy (avoids re-emitting identifiers on `resume`/`clear` and minimizes trust-hash churn).

---

## little_loops.host_runner

Host-agnostic CLI invocation layer. Every shell-out to a host CLI (`claude`, `codex`, `opencode`, `pi`) is built through a `HostRunner` implementation, so the orchestration layer (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff) never hard-codes host-specific argv.

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

Public surface — `__all__ = ["CapabilityEntry", "CapabilityNotSupported", "CapabilityReport", "ClaudeCodeRunner", "CodexRunner", "HostCapabilities", "HostInvocation", "HostNotConfigured", "HostRunner", "HookEntry", "OpenCodeRunner", "PiRunner", "apply_host_cli_from_config", "resolve_host"]`.

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
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `streaming` | `bool` | `False` | Host can produce turn-by-turn structured (JSON / NDJSON) events for long-running orchestration paths. |
| `permission_skip` | `bool` | `False` | Host supports skipping interactive permission prompts (Claude `--dangerously-skip-permissions`, Codex `--dangerously-bypass-approvals-and-sandbox`). Required for headless automation. |
| `agent_select` | `bool` | `False` | Host accepts a per-invocation agent / persona selector. |
| `tool_allowlist` | `bool` | `False` | Host accepts an explicit tool allowlist on invocation. |

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
| `CodexRunner` | `codex` CLI | ✓ production | Translates the Claude-shaped Protocol surface to Codex `exec` headless mode. Auto-detected when `codex` is on PATH (probe order: `claude → codex → pi`). For `agent`, `build_streaming` reads `.codex/agents/<name>.toml` and prepends `developer_instructions` as a `[Persona: <name>]` block (ENH-1533); when the TOML is absent, falls back to emitting `CapabilityNotSupported` plus a stderr notice. `tools` always emits `CapabilityNotSupported` and is dropped; use `sandbox_mode=` (ENH-1529) for constrained execution. `describe_capabilities()` reports `agent_select.status == "partial"` and `tool_allowlist.status == "partial"` (via sandbox_mode). |
| `OpenCodeRunner` | `opencode` CLI | stub | Registered so `LL_HOST_CLI=opencode` resolves to a useful error rather than the generic "unknown host". All `build_*` methods raise `HostNotConfigured`. See FEAT-1472. |
| `PiRunner` | `pi` CLI | stub | Present in `_PROBE_ORDER`, so hosts with `pi` on PATH resolve to this stub. All `build_*` methods raise `HostNotConfigured`. Pi orchestration is tracked under FEAT-992. |

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
3. Binary probe: `claude` → `codex` → `pi` (see `_PROBE_ORDER`).
4. Raise `HostNotConfigured` with a remediation hint.

```python
from little_loops.host_runner import resolve_host

runner = resolve_host()
invocation = runner.build_streaming(prompt="Hello, world")
# subprocess.run([invocation.binary, *invocation.args], env={**os.environ, **invocation.env})
```

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
- Each name in `config.transports` is resolved against an internal registry of built-in transport names. Currently shipped: `"jsonl"` (registers a `JsonlTransport` writing to `<log_dir>/events.jsonl`), `"socket"` (registers a [`UnixSocketTransport`](#unixsockettransport) bound at `config.socket.path` with `config.socket.max_clients`), `"otel"` (registers an [`OTelTransport`](#oteltransport) using `config.otel.endpoint` and `config.otel.service_name`), and `"webhook"` (registers a [`WebhookTransport`](#webhooktransport) using `config.webhook.url`, `batch_ms`, and `headers`; skipped with a warning if `url` is `None`).
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
- Built-in intents (`pre_compact`, `session_start`, `session_end`, `user_prompt_submit`, `post_tool_use`, `pre_tool_use`) shadow extension-registered intents on collision: `_dispatch_table()` returns `{**_HOOK_INTENT_REGISTRY, **built_ins}`, so a built-in always wins.
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

## Agents

Specialized sub-agents live in `agents/*.md` and are registered in `.claude-plugin/plugin.json`. Each agent is spawned via the `Task` / `Agent` tool with `subagent_type` set to the agent name. Codex-CLI mirrors are generated into `.codex/agents/*.toml` by `ll-adapt-agents-for-codex`.

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
