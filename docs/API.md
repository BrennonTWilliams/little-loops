# API Reference

This document provides the public API for the little-loops Python package.

## Installation

```bash
pip install /path/to/little-loops/scripts
```

## Module Overview

| Module | Purpose |
|--------|---------|
| `little_loops.config` | Configuration management |
| `little_loops.issue_parser` | Issue file parsing |
| `little_loops.issue_manager` | Sequential automation |
| `little_loops.issue_lifecycle` | Issue lifecycle operations |
| `little_loops.git_operations` | Git utilities |
| `little_loops.work_verification` | Verification helpers |
| `little_loops.subprocess_utils` | Subprocess handling |
| `little_loops.state` | State persistence |
| `little_loops.logger` | Logging utilities |
| `little_loops.cli` | CLI entry points |
| `little_loops.parallel` | Parallel processing subpackage |

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
| `commands` | `CommandsConfig` | Command customization |
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
    include_p0: bool | None = None,
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
- `include_p0` - Include P0 in parallel queue
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
```

### IssuesConfig

Issue management configuration dataclass.

```python
@dataclass
class IssuesConfig:
    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig]
    completed_dir: str = "completed"
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
    include_p0: bool = False
    command_prefix: str = "/ll:"
    ready_command: str = "ready_issue {{issue_id}}"
    manage_command: str = "manage_issue {{issue_type}} {{action}} {{issue_id}}"
    worktree_copy_files: list[str] = [".claude/settings.local.json", ".env"]
    require_code_changes: bool = True
```

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

### MergeCoordinator

Sequential merge queue with conflict handling.

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
    include_p0: bool = False
    stream_subprocess_output: bool = False
    show_model: bool = False
    command_prefix: str = "/ll:"
    ready_command: str = "ready_issue {{issue_id}}"
    manage_command: str = "manage_issue {{issue_type}} {{action}} {{issue_id}}"
```

#### Methods

##### get_ready_command

```python
def get_ready_command(self, issue_id: str) -> str
```

Build the ready_issue command string.

**Parameters:**
- `issue_id` - Issue identifier

**Returns:** Complete command string (e.g., `"/ll:ready_issue BUG-001"`)

##### get_manage_command

```python
def get_manage_command(self, issue_type: str, action: str, issue_id: str) -> str
```

Build the manage_issue command string.

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

### main_parallel

```python
def main_parallel() -> int
```

Entry point for `ll-parallel` command. Parallel issue management with git worktrees.

**Returns:** Exit code

---

## Import Shortcuts

```python
# Main package imports
from little_loops.config import BRConfig
from little_loops.issue_parser import IssueParser, IssueInfo, find_issues
from little_loops.issue_manager import AutoManager
from little_loops.state import StateManager, ProcessingState
from little_loops.logger import Logger, format_duration

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
