# API Reference

This document provides the public API for the little-loops Python package.

> **Related Documentation:**
> - [Architecture Overview](ARCHITECTURE.md) - System design and diagrams
> - [Troubleshooting](TROUBLESHOOTING.md) - Common issues and diagnostic commands
> - [README](../README.md) - Installation and quick start

## Installation

```bash
pip install -e "/path/to/little-loops/scripts[dev]"
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
| `little_loops.dependency_mapper` | Cross-issue dependency discovery and mapping |
| `little_loops.work_verification` | Verification helpers |
| `little_loops.subprocess_utils` | Subprocess handling |
| `little_loops.state` | State persistence |
| `little_loops.logger` | Logging utilities |
| `little_loops.logo` | CLI logo display |
| `little_loops.frontmatter` | YAML frontmatter parsing |
| `little_loops.doc_counts` | Documentation count verification |
| `little_loops.link_checker` | Link validation for markdown docs |
| `little_loops.user_messages` | User message extraction from Claude logs |
| `little_loops.workflow_sequence_analyzer` | Workflow sequence analysis for multi-step patterns |
| `little_loops.goals_parser` | Product goals file parsing |
| `little_loops.sync` | GitHub Issues bidirectional sync |
| `little_loops.session_log` | Session log linking for issue files |
| `little_loops.cli` | CLI entry points (package) |
| `little_loops.parallel` | Parallel processing subpackage |
| `little_loops.fsm` | FSM loop system subpackage |
| `little_loops.sprint` | Sprint planning and execution |

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
- Loads `.claude/ll-config.json` if present
- Merges with sensible defaults
- Creates typed config objects

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `project` | `ProjectConfig` | Project-level settings |
| `issues` | `IssuesConfig` | Issue management settings |
| `automation` | `AutomationConfig` | Sequential automation settings |
| `parallel` | `ParallelAutomationConfig` | Parallel automation settings |
| `commands` | `CommandsConfig` | Command customization (includes `confidence_gate: ConfidenceGateConfig`) |
| `scan` | `ScanConfig` | Codebase scanning settings |
| `issue_categories` | `list[str]` | List of category names |
| `issue_priorities` | `list[str]` | List of priority prefixes |

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

**Returns:** `Path` to completed directory

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
    stream_output: bool | None = None,
    show_model: bool | None = None,
) -> ParallelConfig
```

Create a `ParallelConfig` from BRConfig settings with optional overrides.

**Parameters:**
- `max_workers` - Override max workers (default: from config)
- `priority_filter` - Override priority filter
- `max_issues` - Maximum issues to process (0 = unlimited)
- `dry_run` - Preview mode without processing
- `timeout_seconds` - Per-issue timeout in seconds
- `stream_output` - Stream Claude output
- `show_model` - Display model info on setup

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
```

**Fields:**
- `worktree_copy_files` - Files copied from main repo to each worktree
- `require_code_changes` - Fail issues that don't produce code changes

**Note:** Shared fields from `AutomationConfig` are accessed via `base.*`:
- `base.max_workers` - Maximum parallel workers (default: 2)
- `base.worktree_base` - Base directory for worktrees (default: ".worktrees")
- `base.state_file` - State file path (default: ".parallel-manage-state.json")
- `base.timeout_seconds` - Per-issue timeout in seconds (default: 3600)
- `base.stream_output` - Stream subprocess output (default: False for parallel)

---

## little_loops.issue_parser

Issue file parsing utilities.

### IssueInfo

Parsed information from an issue file.

```python
@dataclass
class IssueInfo:
    path: Path           # Path to the issue file
    issue_type: str      # e.g., "bugs"
    priority: str        # e.g., "P1"
    issue_id: str        # e.g., "BUG-123"
    title: str           # Issue title
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

#### find_issues

```python
def find_issues(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
) -> list[IssueInfo]
```

Find all issues matching criteria, sorted by priority.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter (e.g., `"bugs"`)
- `skip_ids` - Issue IDs to skip

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
) -> IssueInfo | None
```

Find the highest priority issue.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter
- `skip_ids` - Issue IDs to skip

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
) -> DependencyGraph
```

Build graph from list of issues.

**Parameters:**
- `issues` - List of `IssueInfo` objects with `blocked_by` fields
- `completed_ids` - Set of completed issue IDs (treated as resolved)

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

---

## little_loops.dependency_mapper

Cross-issue dependency discovery and mapping. Analyzes active issues to discover potential dependencies based on file overlap and validates existing dependency references for integrity.

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

Product goals configuration for issue prioritization.

### ProductGoals

Main configuration class for product goals.

```python
@dataclass
class ProductGoals:
    """Product goals for issue prioritization."""
    personas: dict[str, PersonaGoals] | None = None
    priorities: dict[str, PriorityGoals] | None = None
```

### PersonaGoals

Configuration for persona-based goal prioritization.

```python
@dataclass
class PersonaGoals:
    """Goals for a specific persona."""
    persona: str
    description: str
    priorities: list[str]
```

### PriorityGoals

Configuration for priority-based goal categorization.

```python
@dataclass
class PriorityGoals:
    """Goals for a specific priority level."""
    priority: str  # P0-P5
    description: str
    categories: list[str]  # Issue types to prioritize
```

### validate_goals

```python
def validate_goals(goals: ProductGoals) -> list[str]
```

Validate product goals configuration.

**Parameters:**
- `goals` - ProductGoals instance to validate

**Returns:** List of validation error messages (empty if valid)

**Example:**
```python
from little_loops.goals_parser import ProductGoals, validate_goals

goals = ProductGoals(
    personas={
        "end-user": PersonaGoals(
            persona="end-user",
            description="End user of the product",
            priorities=["usability", "performance", "reliability"]
        )
    }
)

errors = validate_goals(goals)
if errors:
    for error in errors:
        print(f"Validation error: {error}")
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

### Public Functions (11)

| Function | Purpose |
|----------|---------|
| `load_completed_issues()` | Load all completed issues from disk |
| `compute_history_summary()` | Generate summary statistics |
| `analyze_hotspots()` | Find files/components with most issues |
| `analyze_coupling()` | Find issue correlation patterns |
| `compute_velocity()` | Calculate issues per time period |
| `analyze_type_distribution()` | Breakdown by issue type |
| `analyze_priority_distribution()` | Breakdown by priority |
| `cluster_regressions()` | Group related regressions |
| `get_trend_data()` | Time series data for trends |
| `generate_velocity_report()` | Human-readable velocity report |
| `compute_failure_classification()` | Categorize failure types |

### Data Classes (19)

#### CompletedIssue

Parsed completed issue.

```python
@dataclass
class CompletedIssue:
    """A parsed completed issue."""
    issue_id: str
    issue_type: str  # bug, feature, enhancement
    priority: str  # P0-P5
    title: str
    completed_at: str  # ISO timestamp
    file_path: Path
    blockers: list[str]
    blocks: list[str]
    tags: list[str]
```

#### HistorySummary

Overall statistics.

```python
@dataclass
class HistorySummary:
    """Summary of completed issues."""
    total_count: int
    date_range: tuple[str, str]
    velocity: float  # issues per day
    type_distribution: dict[str, int]
    priority_distribution: dict[str, int]
```

#### Hotspot

Files with frequent issues.

```python
@dataclass
class Hotspot:
    """A file or component with frequent issues."""
    file_path: str
    issue_count: int
    issue_types: dict[str, int]
    last_issue_date: str
```

#### CouplingPair

Correlated issues.

```python
@dataclass
class CouplingPair:
    """Two issues that are frequently blocked/blocking together."""
    issue_a: str
    issue_b: str
    correlation_score: float
    shared_files: list[str]
```

#### VelocityMetrics

Throughput measurements.

```python
@dataclass
class VelocityMetrics:
    """Velocity metrics over time."""
    overall_velocity: float  # issues/day
    weekly_velocity: float
    monthly_velocity: float
    trend: Literal["improving", "stable", "declining"]
```

#### TrendDataPoint

Time series data.

```python
@dataclass
class TrendDataPoint:
    """A single data point in a trend series."""
    date: str
    count: int
    cumulative: int
```

### Example

```python
from little_loops.issue_history import (
    load_completed_issues,
    compute_history_summary,
    analyze_hotspots,
    generate_velocity_report,
)
from pathlib import Path

# Load and analyze
completed_dir = Path(".issues/completed")
issues = load_completed_issues(completed_dir)
summary = compute_history_summary(issues)

print(f"Completed: {summary.total_count}")
print(f"Velocity: {summary.velocity:.2f} issues/day")

# Find problematic files
hotspots = analyze_hotspots(issues, min_issues=3)
for hotspot in hotspots[:5]:
    print(f"{hotspot.file_path}: {hotspot.issue_count} issues")

# Generate human-readable report
report = generate_velocity_report(issues)
print(report)
```

---

## little_loops.git_operations

Git utility functions for status checking, work verification, and .gitignore management.

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

### verify_work_was_done

```python
def verify_work_was_done(
    logger: Logger,
    changed_files: list[str] | None = None,
) -> bool
```

Verify that actual work was done (not just issue file moves).

Prevents marking issues as "completed" when no actual fix was implemented by checking if changes were made to files outside of excluded directories (`.issues/`, `thoughts/`, etc.).

**Parameters:**
- `logger` - Logger for output
- `changed_files` - Optional list of changed files. If not provided, detects via git diff

**Returns:** `True` if meaningful file changes were detected

### filter_excluded_files

```python
def filter_excluded_files(files: list[str]) -> list[str]
```

Filter out files in excluded directories.

**Parameters:**
- `files` - List of file paths to filter

**Returns:** List of files not in excluded directories

---

## little_loops.issue_manager

Sequential automated issue management.

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
)
```

**Parameters:**
- `config` - Project configuration
- `dry_run` - Preview mode (no actual changes)
- `max_issues` - Maximum issues to process (0 = unlimited)
- `resume` - Resume from previous state
- `category` - Filter to specific category

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
) -> subprocess.CompletedProcess[str]
```

Invoke Claude CLI command with output streaming.

**Parameters:**
- `command` - Command to pass to Claude CLI
- `logger` - Logger for output
- `timeout` - Timeout in seconds
- `stream_output` - Whether to stream output to console

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
) -> bool
```

Close an issue by moving to completed with closure status.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration
- `logger` - Logger for output
- `close_reason` - Reason code (e.g., `"already_fixed"`)
- `close_status` - Status text (e.g., `"Closed - Already Fixed"`)

**Returns:** `True` if successful

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
Logger(verbose: bool = True, use_color: bool = True)
```

**Parameters:**
- `verbose` - Whether to output messages (False silences all output)
- `use_color` - Whether to use ANSI color codes

#### Methods

| Method | Color | Description |
|--------|-------|-------------|
| `info(msg)` | Cyan | General information |
| `debug(msg)` | Gray | Debug messages |
| `success(msg)` | Green | Success messages |
| `warning(msg)` | Yellow | Warnings |
| `error(msg)` | Red | Errors (to stderr) |
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
- `output_path` - Output file path. If None, uses `.claude/user-messages-{timestamp}.jsonl`

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

Utilities for parsing Claude's output from `/ll:ready-issue` commands. Located at `little_loops.parallel.output_parsing`.

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
from little_loops.parallel.output_parsing import parse_ready_issue_output

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

**See [MERGE-COORDINATOR.md](MERGE-COORDINATOR.md) for comprehensive documentation.**

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
    timeout_per_issue: int = 7200
    orchestrator_timeout: int = 0
    stream_subprocess_output: bool = False
    show_model: bool = False
    command_prefix: str = "/ll:"
    ready_command: str = "ready-issue {{issue_id}}"
    manage_command: str = "manage-issue {{issue_type}} {{action}} {{issue_id}}"
    only_ids: set[str] | None = None
    skip_ids: set[str] | None = None
    require_code_changes: bool = True
    worktree_copy_files: list[str]
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
    should_close: bool = False
    close_reason: str | None = None
    close_status: str | None = None
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
| `p0_count() -> int` | Count of P0 issues in queue |
| `parallel_count() -> int` | Count of P1-P5 issues in queue |

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
    started_at: str
    last_checkpoint: str
```

---

## little_loops.cli

CLI entry points for the package.

### main_auto

```python
def main_auto() -> int
```

Entry point for `ll-auto` command. Sequential automated issue management.

**Returns:** Exit code

### main_loop

```python
def main_loop() -> int
```

Entry point for `ll-loop` command. FSM-based automation loop execution.

**Returns:** Exit code

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

---

## little_loops.workflow_sequence_analyzer

Step 2 of a 3-step workflow analysis pipeline. Analyzes user message patterns to identify multi-step workflows, link related sessions, and detect workflow boundaries.

### Quick Example

```python
from pathlib import Path
from little_loops.workflow_sequence_analyzer import analyze_workflows

# Analyze messages from Step 1 output
result = analyze_workflows(
    messages_file=Path(".claude/user-messages.jsonl"),
    patterns_file=Path(".claude/workflow-analysis/step1-patterns.yaml"),
    output_file=Path(".claude/workflow-analysis/step2-workflows.yaml"),
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
from little_loops.workflow_sequence_analyzer import analyze_workflows

result = analyze_workflows(
    messages_file=Path(".claude/user-messages.jsonl"),
    patterns_file=Path(".claude/workflow-analysis/step1-patterns.yaml"),
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
from little_loops.workflow_sequence_analyzer import extract_entities

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
    verify_work_was_done,
)
from little_loops.state import StateManager, ProcessingState
from little_loops.logger import Logger, format_duration
from little_loops.user_messages import (
    UserMessage,
    get_project_folder,
    extract_user_messages,
    save_messages,
)

# Workflow analysis
from little_loops.workflow_sequence_analyzer import (
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
from little_loops.parallel.output_parsing import parse_ready_issue_output
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
| `little_loops.fsm.compilers` | Compile paradigms (goal, convergence, etc.) to FSM |
| `little_loops.fsm.evaluators` | Verdict evaluators (exit_code, llm_structured, etc.) |
| `little_loops.fsm.executor` | FSM execution engine |
| `little_loops.fsm.interpolation` | Variable substitution (`${context.*}`, etc.) |
| `little_loops.fsm.validation` | Schema validation utilities |
| `little_loops.fsm.persistence` | Loop state persistence |

### Quick Import

```python
from little_loops.fsm import (
    # Schema
    FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig,
    # Validation
    ValidationError, validate_fsm, load_and_validate,
    # Compilation
    compile_paradigm,
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
    paradigm: str | None = None        # Source paradigm (goal, convergence, etc.)
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
            on_success="done",
            on_failure="fix",
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

#### StateConfig

Configuration for a single FSM state.

```python
@dataclass
class StateConfig:
    action: str | None = None          # Command to execute
    evaluate: EvaluateConfig | None    # Evaluator configuration
    route: RouteConfig | None          # Full routing table
    on_success: str | None = None      # Shorthand routing
    on_failure: str | None = None      # Shorthand routing
    on_error: str | None = None        # Shorthand routing
    next: str | None = None            # Unconditional transition
    terminal: bool = False             # End state marker
    capture: str | None = None         # Variable name to store output
    timeout: int | None = None         # Action timeout in seconds
    on_maintain: str | None = None     # State for maintain mode restart
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
        routes={"success": "proceed", "failure": "wait"},
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

### little_loops.fsm.compilers

Paradigm compilers for FSM loop generation. Each paradigm compiles to the universal FSM schema.

#### compile_paradigm

```python
def compile_paradigm(spec: dict[str, Any]) -> FSMLoop
```

Route to appropriate compiler based on paradigm field.

**Parameters:**
- `spec` - Paradigm specification dictionary with `paradigm` field

**Returns:** Compiled `FSMLoop` instance

**Raises:** `ValueError` if paradigm is unknown

**Supported paradigms:** `goal`, `convergence`, `invariants`, `imperative`, `fsm`

**Example:**
```python
from little_loops.fsm import compile_paradigm

# Goal paradigm
spec = {
    "paradigm": "goal",
    "goal": "No type errors in src/",
    "tools": ["/ll:check-code types", "/ll:manage-issue bug fix"],
    "max_iterations": 20,
}
fsm = compile_paradigm(spec)
print(fsm.initial)  # "evaluate"
```

#### Paradigm-Specific Compilers

```python
def compile_goal(spec: dict) -> FSMLoop
```
Goal paradigm: evaluate → (success → done, failure → fix), fix → evaluate

```python
def compile_convergence(spec: dict) -> FSMLoop
```
Convergence paradigm: measure → (target → done, progress → apply, stall → done)

```python
def compile_invariants(spec: dict) -> FSMLoop
```
Invariants paradigm: chain multiple check/fix constraints

```python
def compile_imperative(spec: dict) -> FSMLoop
```
Imperative paradigm: step sequence with exit condition

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
print(result.verdict)  # "success"

# Pattern matching
result = evaluate_output_contains("All tests passed", "passed")
print(result.verdict)  # "success"

result = evaluate_output_contains("Error occurred", "Error", negate=True)
print(result.verdict)  # "failure"
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
        "check": StateConfig(action="pytest", on_success="done", on_failure="check"),
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
    ) -> ActionResult: ...
```

Implement this protocol to customize action execution (useful for testing).

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
        "start": StateConfig(action="echo", on_success="done", on_failure="done"),
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
        "check": StateConfig(action="pytest", on_success="done", on_failure="check"),
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
List all loops with saved state.

```python
def get_loop_history(loop_name: str, loops_dir: Path | None = None) -> list[dict]
```
Get event history for a loop.

---

## little_loops.sprint

Sprint planning and execution for batch issue processing.

### SprintOptions

```python
@dataclass
class SprintOptions:
    max_iterations: int = 100   # Max Claude iterations per issue
    timeout: int = 3600         # Per-issue timeout in seconds
    max_workers: int = 4        # Worker count for parallel execution within waves
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
