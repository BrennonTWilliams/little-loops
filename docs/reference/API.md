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
| `little_loops.state` | State persistence |
| `little_loops.events` | Structured events and EventBus dispatcher |
| `little_loops.extension` | Extension protocol, loader, and reference implementation |
| `little_loops.testing` | Offline test harness (LLTestBus) for extension development |
| `little_loops.logger` | Logging utilities |
| `little_loops.logo` | CLI logo display |
| `little_loops.frontmatter` | YAML frontmatter parsing |
| `little_loops.doc_counts` | Documentation count verification |
| `little_loops.link_checker` | Link validation for markdown docs |
| `little_loops.user_messages` | User message extraction from Claude logs |
| `little_loops.workflow_sequence` | Workflow sequence analysis for multi-step patterns |
| `little_loops.goals_parser` | Product goals file parsing |
| `little_loops.sync` | GitHub Issues bidirectional sync |
| `little_loops.session_log` | Session log linking for issue files |
| `little_loops.text_utils` | Text extraction utilities for issue content |
| `little_loops.cli` | CLI entry points (package) |
| `little_loops.parallel` | Parallel processing subpackage |
| `little_loops.fsm` | FSM loop system subpackage |
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
| `commands` | `CommandsConfig` | Command customization (includes `confidence_gate: ConfidenceGateConfig`, `tdd_mode: bool`) |
| `scan` | `ScanConfig` | Codebase scanning settings |
| `sprints` | `SprintsConfig` | Sprint management settings |
| `loops` | `LoopsConfig` | FSM loop settings |
| `sync` | `SyncConfig` | GitHub Issues sync settings |
| `dependency_mapping` | `DependencyMappingConfig` | Overlap detection thresholds |
| `refine_status` | `RefineStatusConfig` | refine-status display settings |
| `cli` | `CliConfig` | CLI output settings (color toggle and color overrides) |
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
        "ENH": "34"
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
| `cli.colors.type.*` | `str` | see above | Raw ANSI SGR codes for issue type labels BUG, FEAT, ENH. |

**Notes:**
- Setting `NO_COLOR=1` in the environment disables color regardless of `cli.color`.
- Unspecified `cli.colors` sub-keys retain their defaults.
- Color values are raw SGR parameter strings (e.g. `"32"`, `"38;5;208"`, `"1;34"`).

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

Get the path to the completed issues directory.

##### get_deferred_dir

```python
def get_deferred_dir(self) -> Path
```

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
    completed_dir: str = "completed"
    deferred_dir: str = "deferred"
    priorities: list[str]  # ["P0", "P1", ...]
    templates_dir: str | None = None
    capture_template: str = "full"
    duplicate_detection: DuplicateDetectionConfig  # thresholds for skip/update/create
```

### DuplicateDetectionConfig

Thresholds controlling duplicate issue detection behavior.

```python
@dataclass
class DuplicateDetectionConfig:
    exact_threshold: float = 0.8   # score >= this → skip (duplicate)
    similar_threshold: float = 0.5  # score >= this → update existing issue
```

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
    blocked_by: list[str] = []             # Issue IDs that block this issue
    blocks: list[str] = []                 # Issue IDs that this issue blocks
    discovered_by: str | None = None       # Source command/workflow that created this issue
    product_impact: ProductImpact | None = None  # Product impact assessment
    effort: int | None = None              # Effort estimate (1=low, 2=medium, 3=high)
    impact: int | None = None              # Impact estimate (1=low, 2=medium, 3=high)
    confidence_score: int | None = None    # Readiness score (0-100) from /ll:confidence-check
    outcome_confidence: int | None = None  # Outcome confidence (0-100) from /ll:confidence-check
    score_complexity: int | None = None    # Outcome criterion A – Complexity (0-25) from /ll:confidence-check
    score_test_coverage: int | None = None # Outcome criterion B – Test Coverage (0-25) from /ll:confidence-check
    score_ambiguity: int | None = None     # Outcome criterion C – Ambiguity (0-25) from /ll:confidence-check
    score_change_surface: int | None = None # Outcome criterion D – Change Surface (0-25) from /ll:confidence-check
    size: str | None = None               # Issue size from /ll:issue-size-review (Small, Medium, Large, Very Large)
    testable: bool | None = None           # False = skip TDD phase; None = treat as testable
    session_commands: list[str] = []       # Distinct /ll:* commands in ## Session Log
    session_command_counts: dict[str, int] = {}  # Per-command occurrence counts
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

**Returns:** `True` if filename matches `^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$`

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
    only_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
) -> list[IssueInfo]
```

Find all issues matching criteria, sorted by priority.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter (e.g., `"bugs"`)
- `skip_ids` - Issue IDs to skip
- `only_ids` - If provided, only include these issue IDs
- `type_prefixes` - If provided, only include issues whose ID starts with one of these prefixes (e.g., `{"BUG", "ENH"}`)

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
- `issues` - List of `IssueInfo` objects with `blocked_by` fields
- `completed_ids` - Set of completed issue IDs (treated as resolved)
- `all_known_ids` - Set of all issue IDs that exist on disk; references to these are silently skipped (not warned) even if not in the graph

**Returns:** Constructed `DependencyGraph`

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `issues` | `dict[str, IssueInfo]` | Mapping of issue ID to `IssueInfo` |
| `blocked_by` | `dict[str, set[str]]` | Mapping of issue ID to blocker IDs |
| `blocks` | `dict[str, set[str]]` | Reverse mapping (what each issue blocks) |

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
    broken_refs: list[tuple[str, str]]         # (issue_id, missing_ref_id)
    missing_backlinks: list[tuple[str, str]]   # (issue_id, should_have_backlink_from)
    cycles: list[list[str]]                    # Cycle paths
    stale_completed_refs: list[tuple[str, str]]  # (issue_id, completed_ref_id)

    @property
    def has_issues(self) -> bool
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `broken_refs` | `list[tuple[str, str]]` | References to nonexistent issues |
| `missing_backlinks` | `list[tuple[str, str]]` | Asymmetric `Blocked By`/`Blocks` pairs |
| `cycles` | `list[list[str]]` | Circular dependency chains |
| `stale_completed_refs` | `list[tuple[str, str]]` | References to completed issues |

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
    issue_type: str          # BUG, ENH, FEAT
    priority: str            # P0-P5
    issue_id: str            # e.g., BUG-001
    discovered_by: str | None = None
    discovered_date: date | None = None
    completed_date: date | None = None
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
    issue_types: dict[str, int] = field(default_factory=dict)  # {"BUG": 5, "ENH": 3}
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
) -> bool
```

Verify that actual work was done (not just issue file moves).

Prevents marking issues as "completed" when no actual fix was implemented. Returns `True` if there are file changes outside of excluded directories.

**Parameters:**
- `logger` - Logger for output
- `changed_files` - Optional pre-computed file list. If `None`, detects via `git diff` and `git diff --cached`

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
    only_ids: set[str] | None = None,
    skip_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
    priority_filter: set[str] | None = None,
    verbose: bool = True,
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
    agent: str | None = None,
    tools: list[str] | None = None,
) -> subprocess.CompletedProcess[str]
```

Invoke Claude CLI command with output streaming.

**Parameters:**
- `command` - Command to pass to Claude CLI
- `logger` - Logger for output
- `timeout` - Timeout in seconds
- `stream_output` - Whether to stream output to console
- `agent` - Claude agent model override; appended as `--agent <value>` to CLI invocation
- `tools` - Restrict available tools; appended as `--tools <value>` to CLI invocation

**Returns:** `CompletedProcess` with stdout/stderr captured

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
) -> bool
```

Fallback: Complete issue lifecycle when command exited early.

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
) -> bool
```

Move an issue from its active category directory to `deferred/`.

Appends a `## Deferred` section to the issue file with the reason and date, then commits the move.

**Parameters:**
- `info` - Parsed issue info
- `config` - Project configuration
- `logger` - Logger for output
- `reason` - Reason for deferring (default: `"Intentionally set aside for later consideration"`)

**Returns:** `True` if successful, `False` otherwise

### undefer_issue

```python
def undefer_issue(
    config: BRConfig,
    deferred_issue_path: Path,
    logger: Logger,
    reason: str | None = None,
) -> Path | None
```

Move an issue from `deferred/` back to its original category directory.

Removes the `## Deferred` section from the issue file and commits the move.

**Parameters:**
- `config` - Project configuration
- `deferred_issue_path` - Path to the issue file in `deferred/`
- `logger` - Logger for output
- `reason` - Reason for undeferring (optional)

**Returns:** New `Path` of the issue in its active category directory, or `None` if failed

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
def get_project_folder(cwd: Path | None = None) -> Path | None
```

Map a directory to its Claude Code project folder.

**Parameters:**
- `cwd` - Working directory to map (default: current directory)

**Returns:** Path to Claude project folder (`~/.claude/projects/-path-to-dir`), or `None` if it doesn't exist.

**Example:**
```python
from little_loops.user_messages import get_project_folder
from pathlib import Path

# Map current directory
project_folder = get_project_folder()

# Map specific directory
project_folder = get_project_folder(Path("/Users/me/my-project"))
# Returns: ~/.claude/projects/-Users-me-my-project
```

### extract_user_messages

```python
def extract_user_messages(
    project_folder: Path,
    limit: int | None = None,
    since: datetime | None = None,
    include_agent_sessions: bool = True,
) -> list[UserMessage]
```

Extract user messages from all JSONL session files in a project folder.

**Parameters:**
- `project_folder` - Path to Claude project folder
- `limit` - Maximum number of messages to return
- `since` - Only include messages after this datetime
- `include_agent_sessions` - Whether to include agent-*.jsonl files

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

**Sort key**: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int`

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

**Sort key**: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int`

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

Search across active, completed, and/or deferred issues with rich filtering, sorting, and output options.

**Arguments:**
- `QUERY` - Optional text to match against title and body (case-insensitive substring)

**Filters:**
- `--type {BUG,FEAT,ENH}` - Filter by issue type (repeatable)
- `--priority P` - Filter by priority P0–P5 or range e.g. `P0-P2` (repeatable)
- `--status {active,completed,deferred,all}` - Filter by status (default: `active`)
- `--include-completed` - Include completed issues (alias for `--status all`)
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
ll-issues search                           # list all active issues
ll-issues search "caching" --include-completed
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

Searches all active category directories and the completed directory. Displays a box-drawing character card with:
- **Metadata**: priority, status, effort, risk level
- **Scores**: confidence score, outcome confidence (when present in frontmatter)
- **Details**: summary text (word-wrapped to fit card width), source (`discovered_by` alias), norm (✓/✗ filename convention check), fmt (✓/✗ required sections check), integration file count, labels, session log history with command counts
- **Path**: relative path from project root

**`--json` output fields**: `issue_id`, `title`, `priority`, `status`, `effort`, `confidence`, `outcome`, `summary`, `integration_files`, `risk`, `labels`, `history`, `path`, `source`, `norm`, `fmt`

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
- `--type {BUG,FEAT,ENH}` - Filter by issue type
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

**Sub-commands:** `validate`, `suggest`, `report`

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
| `little_loops.fsm.signal_detector` | Pattern-based signal detection in action output |

### Quick Import

```python
from little_loops.fsm import (
    # Schema
    FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig,
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
    backoff: float | None = None       # Seconds between iterations
    timeout: int | None = None         # Max runtime in seconds
    maintain: bool = False             # If True, restart after completion
    llm: LLMConfig = LLMConfig()       # LLM evaluation settings
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert to dictionary for serialization |
| `from_dict(data)` | `FSMLoop` | Create from dictionary |
| `get_all_state_names()` | `set[str]` | All defined state names |
| `get_terminal_states()` | `set[str]` | States with `terminal=True` |
| `get_all_referenced_states()` | `set[str]` | All states referenced by transitions |

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
```

> **Alias note:** `on_success` and `on_failure` are accepted as aliases for `on_yes` and `on_no` in all states (including sub-loop states).

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
        "llm_structured",   # LLM with structured output
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
Evaluate action output using LLM with structured output.

**Note:** Requires `pip install little-loops[llm]` for anthropic package.

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
        event_callback: Callable[[dict], None] | None = None,
        action_runner: ActionRunner | None = None,
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
print(result.terminated_by)   # "terminal", "max_iterations", "timeout", "signal", or "error"
```

#### ExecutionResult

```python
@dataclass
class ExecutionResult:
    final_state: str                      # State when execution stopped
    iterations: int                       # Total iterations
    terminated_by: str                    # Reason for termination
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

# Escape with $$
result = interpolate("Use $${context.var} syntax", ctx)
# Returns: "Use ${context.var} syntax"
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
    def __init__(self, loop_name: str, loops_dir: Path | None = None)
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
| `clear_all()` | Clear state and events |

**File structure:**
```
.loops/
├── my-loop.yaml           # Loop definition
└── .running/              # Runtime state
    ├── my-loop.state.json
    └── my-loop.events.jsonl
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

Manage scope-based locks for concurrent loop execution. Lock files are stored in `.loops/.running/<name>.lock`.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `acquire(loop_name, scope)` | `bool` | Acquire lock; returns `False` if conflict exists |
| `release(loop_name)` | `None` | Release lock for a loop |
| `find_conflict(scope)` | `ScopeLock \| None` | Find conflicting running loop; cleans stale locks |
| `list_locks()` | `list[ScopeLock]` | List all active locks; cleans stale locks |
| `wait_for_scope(scope, timeout=300)` | `bool` | Wait until scope is available; `False` on timeout |

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

Shared YAML-subset frontmatter parsing used by issue_parser, sync, and issue_history modules.

### Public Functions

| Function | Purpose |
|----------|---------|
| `parse_frontmatter` | Extract YAML frontmatter from file content |

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

---

## little_loops.doc_counts

Automated verification that documented counts (commands, agents, skills) match actual file counts in the codebase.

### Data Classes

#### CountResult

```python
@dataclass
class CountResult:
    category: str              # e.g., "commands", "agents", "skills"
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

## little_loops.events

Structured event system and EventBus dispatcher for the extension architecture.

> **Event catalog:** For a complete reference of all event types, payload fields, and subsystem namespaces, see [EVENT-SCHEMA.md](EVENT-SCHEMA.md).

```python
from little_loops.events import EventBus, LLEvent

bus = EventBus()
bus.register(lambda evt: print(f"Event: {evt['event']}"))
bus.add_file_sink(Path(".ll/events.jsonl"))
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

Central dispatcher that fans out events to registered observers and file sinks.

```python
from little_loops.events import EventBus, LLEvent
from pathlib import Path

bus = EventBus()
bus.register(lambda evt: print(evt))
bus.add_file_sink(Path(".ll/events.jsonl"))
bus.emit({"event": "test", "ts": "2026-04-02T00:00:00Z"})
```

#### Constructor

```python
EventBus()
```

Initializes empty observer and file sink lists. No parameters.

#### Methods

| Method | Description |
|--------|-------------|
| `register(callback: EventCallback, filter: str \| list[str] \| None = None) -> None` | Append an observer callback with an optional glob filter. `None` (default) receives all events. |
| `unregister(callback: EventCallback) -> None` | Remove an observer by identity. Silently ignores if not found. |
| `add_file_sink(path: Path) -> None` | Add a JSONL file sink. Creates parent directories if needed. |
| `emit(event: dict[str, Any]) -> None` | Fan out event to matching observers, then append JSON line to all file sinks. Per-observer exceptions are caught and logged. |
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

**Error handling:**
- **Load failures** — both `ExtensionLoader.from_config()` and `from_entry_points()` catch all exceptions per extension, log a `WARNING` with the full traceback, and continue. A single bad extension never prevents others from loading; `wire_extensions` returns a partial list of the extensions that did succeed.
- **Runtime failures** — if an extension's `on_event` raises during `EventBus.emit()`, the exception is caught and logged at `WARNING` level. Other registered observers still receive the event.
- **Duplicate key conflicts** — if two extensions provide the same action or evaluator key, `wire_extensions` raises `ValueError: "Extension conflict: action/evaluator '<key>' already registered by another extension"`.

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

config = BRConfig.load()
prompt = expand_skill("ready-issue", ["FEAT-123"], config)
if prompt is None:
    prompt = "/ll:ready-issue FEAT-123"  # fallback
```
