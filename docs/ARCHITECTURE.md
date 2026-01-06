# Architecture Overview

little-loops is a Claude Code plugin providing development workflow automation with issue management, code quality commands, and parallel processing capabilities.

> **Related Documentation:**
> - [API Reference](API.md) - Detailed class and method documentation
> - [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
> - [README](../README.md) - Installation and quick start

## System Components

The system consists of three main layers:

1. **Command Layer** - Slash commands and agents for Claude Code
2. **Automation Layer** - Python CLI tools for batch processing
3. **Configuration Layer** - JSON-based project configuration

## High-Level Architecture

```mermaid
flowchart TB
    subgraph "Claude Code Plugin"
        CMD[Commands<br/>18 slash commands]
        AGT[Agents<br/>7 specialized agents]
    end

    subgraph "Configuration"
        CFG[ll-config.json]
        SCHEMA[config-schema.json]
        TPL[templates/*.json]
    end

    subgraph "Python Automation"
        CLI[cli.py<br/>Entry points]
        AUTO[issue_manager.py<br/>Sequential processing]
        PARALLEL[parallel/<br/>Parallel processing]
    end

    subgraph "Issue Storage"
        ISSUES[.issues/<br/>bugs, features, enhancements]
        COMPLETED[.issues/completed/]
    end

    CFG --> CMD
    TPL --> CFG
    SCHEMA -.->|validates| CFG
    CFG --> CLI
    CMD --> AGT
    CLI --> AUTO
    CLI --> PARALLEL
    AUTO --> ISSUES
    PARALLEL --> ISSUES
    AUTO --> COMPLETED
    PARALLEL --> COMPLETED
```

## Directory Structure

```
little-loops/
├── plugin.json              # Plugin manifest
├── config-schema.json       # JSON Schema for validation
├── commands/                # 18 slash command templates
│   ├── init.md
│   ├── help.md
│   ├── check_code.md
│   ├── run_tests.md
│   ├── manage_issue.md
│   ├── normalize_issues.md
│   └── ...
├── agents/                  # 7 specialized agents
│   ├── codebase-analyzer.md
│   ├── codebase-locator.md
│   ├── codebase-pattern-finder.md
│   ├── consistency-checker.md
│   ├── plugin-config-auditor.md
│   ├── prompt-optimizer.md
│   └── web-search-researcher.md
├── hooks/                   # Lifecycle hooks and validation scripts
│   ├── hooks.json           # Hook configuration
│   ├── check-duplicate-issue-id.sh  # Validation script
│   └── prompts/
│       ├── post-tool-state-tracking.md
│       ├── pre-compact-state.md
│       └── continuation-prompt-template.md
├── templates/               # Project type configs
│   ├── python-generic.json
│   ├── javascript.json
│   ├── typescript.json
│   ├── go.json
│   ├── rust.json
│   ├── java-maven.json
│   ├── java-gradle.json
│   ├── dotnet.json
│   └── generic.json
└── scripts/                 # Python package
    └── little_loops/
        ├── __init__.py
        ├── cli.py               # CLI entrypoints
        ├── config.py            # Configuration loading
        ├── state.py             # State persistence
        ├── logger.py            # Logging utilities
        ├── issue_manager.py     # Sequential automation
        ├── issue_parser.py      # Issue file parsing
        ├── issue_discovery.py   # Issue discovery and deduplication
        ├── issue_lifecycle.py   # Issue lifecycle operations
        ├── git_operations.py    # Git utilities
        ├── work_verification.py # Verification helpers
        ├── subprocess_utils.py  # Subprocess handling
        └── parallel/
            ├── __init__.py
            ├── orchestrator.py
            ├── worker_pool.py
            ├── merge_coordinator.py
            ├── priority_queue.py
            ├── output_parsing.py
            ├── git_lock.py
            ├── types.py
            └── tasks/
                ├── README.md
                ├── lint-all.yaml
                ├── test-suite.yaml
                ├── build-assets.yaml
                └── health-check.yaml
```

---

## Sequential Mode (ll-auto)

The sequential mode processes issues one at a time in priority order.

```mermaid
sequenceDiagram
    participant User
    participant CLI as ll-auto
    participant Manager as AutoManager
    participant Claude as Claude CLI
    participant Git

    User->>CLI: ll-auto --max-issues 5
    CLI->>Manager: Initialize with config

    loop For each issue (priority order)
        Manager->>Manager: Find highest priority issue

        Note over Manager,Claude: Phase 1: Validation
        Manager->>Claude: /ll:ready_issue ISSUE-ID
        Claude-->>Manager: READY / NOT_READY / CLOSE

        alt READY
            Note over Manager,Claude: Phase 2: Implementation
            Manager->>Claude: /ll:manage_issue type action id
            Claude->>Git: Make changes
            Claude->>Git: Create commit
            Claude-->>Manager: Success

            Note over Manager,Git: Phase 3: Verification
            Manager->>Git: Move issue to completed/
            Manager->>Manager: Verify completion
        else NOT_READY
            Manager->>Manager: Mark failed, skip
        else CLOSE
            Manager->>Git: Move to completed/ (closed)
        end

        Manager->>Manager: Save state
    end

    Manager-->>User: Summary report
```

### Sequential Mode Components

| Component | File | Purpose |
|-----------|------|---------|
| `AutoManager` | `issue_manager.py` | Main orchestration loop |
| `IssueParser` | `issue_parser.py` | Parse issue files |
| `StateManager` | `state.py` | Persist state for resume |
| `Logger` | `logger.py` | Colorized console output |

---

## Parallel Mode (ll-parallel)

The parallel mode uses git worktrees to process multiple issues concurrently.

```mermaid
flowchart TB
    subgraph Orchestrator["ParallelOrchestrator"]
        ORCH[Main Controller]
        QUEUE[IssuePriorityQueue]
        STATE[OrchestratorState]
    end

    subgraph Workers["Worker Pool"]
        POOL[WorkerPool]
        W1[Worker 1]
        W2[Worker 2]
        WN[Worker N]
    end

    subgraph Merge["Merge Coordinator"]
        MCOORD[MergeCoordinator]
        MQUEUE[Merge Queue]
    end

    subgraph Worktrees["Git Worktrees"]
        WT1[".worktrees/worker-1/"]
        WT2[".worktrees/worker-2/"]
        WTN[".worktrees/worker-N/"]
    end

    ORCH --> QUEUE
    ORCH --> STATE
    ORCH --> POOL

    POOL --> W1
    POOL --> W2
    POOL --> WN

    W1 --> WT1
    W2 --> WT2
    WN --> WTN

    W1 --> MCOORD
    W2 --> MCOORD
    WN --> MCOORD

    MCOORD --> MQUEUE
```

### Parallel Processing Flow

```mermaid
sequenceDiagram
    participant Orch as Orchestrator
    participant Queue as PriorityQueue
    participant Pool as WorkerPool
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant Merge as MergeCoordinator
    participant Git

    Note over Orch,Queue: Setup Phase
    Orch->>Queue: Scan and queue issues

    Note over Orch,Pool: Processing Phase
    Orch->>Pool: Start workers

    par Worker 1
        Pool->>W1: Process BUG-001
        W1->>Git: Create worktree + branch
        W1->>W1: Run ready_issue
        W1->>W1: Run manage_issue
        W1->>Git: Commit in worktree
        W1-->>Pool: WorkerResult
    and Worker 2
        Pool->>W2: Process BUG-002
        W2->>Git: Create worktree + branch
        W2->>W2: Run ready_issue
        W2->>W2: Run manage_issue
        W2->>Git: Commit in worktree
        W2-->>Pool: WorkerResult
    end

    Note over Pool,Merge: Merge Phase (Sequential)
    Pool->>Merge: Queue BUG-001 result
    Merge->>Git: Merge branch to main
    Merge-->>Orch: Merge complete

    Pool->>Merge: Queue BUG-002 result
    Merge->>Git: Merge branch to main
    Merge-->>Orch: Merge complete

    Note over Orch,Git: Cleanup Phase
    Orch->>Git: Remove worktrees
    Orch->>Git: Delete branches
```

### Parallel Mode Components

| Component | File | Purpose |
|-----------|------|---------|
| `ParallelOrchestrator` | `orchestrator.py` | Coordinate all components |
| `IssuePriorityQueue` | `priority_queue.py` | Priority-based issue ordering |
| `WorkerPool` | `worker_pool.py` | Thread pool with worktrees |
| `MergeCoordinator` | `merge_coordinator.py` | Sequential merge queue |

---

## Class Relationships

```mermaid
classDiagram
    class BRConfig {
        +project: ProjectConfig
        +issues: IssuesConfig
        +automation: AutomationConfig
        +parallel: ParallelAutomationConfig
        +get_issue_dir(category) Path
        +get_completed_dir() Path
        +create_parallel_config() ParallelConfig
        +to_dict() dict
    }

    class IssueParser {
        +config: BRConfig
        +parse_file(path) IssueInfo
    }

    class IssueInfo {
        +path: Path
        +issue_type: str
        +priority: str
        +issue_id: str
        +title: str
        +priority_int: int
    }

    class AutoManager {
        +config: BRConfig
        +state_manager: StateManager
        +run() int
    }

    class StateManager {
        +state_file: Path
        +load() ProcessingState
        +save()
        +mark_completed(issue_id)
        +mark_failed(issue_id, reason)
    }

    class ParallelOrchestrator {
        +parallel_config: ParallelConfig
        +br_config: BRConfig
        +queue: IssuePriorityQueue
        +worker_pool: WorkerPool
        +merge_coordinator: MergeCoordinator
        +run() int
    }

    class WorkerPool {
        +parallel_config: ParallelConfig
        +start()
        +submit(issue) Future
        +shutdown()
        +cleanup_all_worktrees()
    }

    class MergeCoordinator {
        +config: ParallelConfig
        +start()
        +queue_merge(result)
        +shutdown()
    }

    BRConfig --> IssueParser
    IssueParser --> IssueInfo
    BRConfig --> AutoManager
    AutoManager --> StateManager
    BRConfig --> ParallelOrchestrator
    ParallelOrchestrator --> WorkerPool
    ParallelOrchestrator --> MergeCoordinator
    ParallelOrchestrator --> IssuePriorityQueue
```

---

## Configuration Flow

```mermaid
flowchart LR
    subgraph Load["Load Phase"]
        JSON[".claude/ll-config.json"]
        INIT["BRConfig.__init__()"]
        PARSE["_parse_config()"]
    end

    subgraph Objects["Config Objects"]
        PC[ProjectConfig]
        IC[IssuesConfig]
        AC[AutomationConfig]
        PAC[ParallelAutomationConfig]
    end

    subgraph Usage["Usage"]
        CMD["Command Templates<br/>{{config.project.*}}"]
        AUTO_CLI["ll-auto"]
        PAR_CLI["ll-parallel"]
    end

    JSON --> INIT
    INIT --> PARSE
    PARSE --> PC
    PARSE --> IC
    PARSE --> AC
    PARSE --> PAC
    PC --> CMD
    IC --> CMD
    AC --> AUTO_CLI
    PAC --> PAR_CLI
```

---

## Issue Processing Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Discovered: /ll:scan_codebase

    Discovered --> Prioritized: /ll:prioritize_issues
    Prioritized --> Validating: /ll:ready_issue

    Validating --> Ready: READY verdict
    Validating --> NotReady: NOT_READY verdict
    Validating --> ShouldClose: CLOSE verdict

    Ready --> InProgress: /ll:manage_issue
    InProgress --> Verifying: Implementation done
    Verifying --> Completed: Tests pass
    Verifying --> Failed: Tests fail

    NotReady --> Discovered: Fix issue file
    ShouldClose --> Completed: Move to completed/
    Failed --> Discovered: Create follow-up issue

    Completed --> [*]: Move to .issues/completed/
```

---

## Priority Queue Design

The priority queue separates P0 (critical) issues for sequential processing while allowing P1-P5 to be processed in parallel.

```mermaid
flowchart TB
    subgraph Input["Issue Scanning"]
        SCAN[Scan .issues/ directories]
    end

    subgraph Queue["IssuePriorityQueue"]
        P0Q[P0 Queue<br/>Sequential]
        PARQ[P1-P5 Queue<br/>Parallel]
    end

    subgraph Processing["Processing"]
        SEQ[Sequential<br/>One at a time]
        PAR[Parallel<br/>Up to max_workers]
    end

    SCAN --> P0Q
    SCAN --> PARQ

    P0Q --> SEQ
    PARQ --> PAR

    SEQ --> |Complete before| PAR
```

**Rationale**: P0 issues are critical and may have dependencies. Processing them sequentially ensures stability before parallel work begins.

---

## Key Design Decisions

### Git Worktree Isolation

Each parallel worker operates in a separate git worktree:

```
.worktrees/
├── worker-1/           # Full repo copy
│   ├── src/
│   ├── tests/
│   └── .claude/
├── worker-2/
└── worker-N/
```

**Benefits**:
- No file conflicts between workers
- Each worker has isolated branch
- Clean rollback on failure

**Trade-offs**:
- Disk space usage (full copy per worker)
- Initial setup time for worktrees

### Sequential Merging

Despite parallel issue processing, merges happen one at a time:

```mermaid
flowchart LR
    W1[Worker 1<br/>Complete] --> MQ[Merge Queue]
    W2[Worker 2<br/>Complete] --> MQ
    W3[Worker 3<br/>Complete] --> MQ

    MQ --> M1[Merge 1]
    M1 --> M2[Merge 2]
    M2 --> M3[Merge 3]
```

**Rationale**: Parallel merges would cause conflicts. Sequential merging with rebase-on-conflict ensures clean integration.

### State Persistence

Both modes save state for resume capability:

| Mode | State File | Contents |
|------|------------|----------|
| Sequential | `.auto-manage-state.json` | Current issue, completed list, failed list, timing |
| Parallel | `.parallel-manage-state.json` | In-progress, completed, failed, pending merges |

**Format**:
```json
{
  "completed_issues": ["BUG-001", "BUG-002"],
  "failed_issues": {"BUG-003": "Test failure"},
  "attempted_issues": ["BUG-001", "BUG-002", "BUG-003"],
  "timing": {
    "BUG-001": {"ready": 30.5, "implement": 120.2, "verify": 5.1}
  }
}
```

### Merge Strategy

The merge coordinator uses:
1. Fast-forward merge when possible
2. Rebase worker branch on conflict
3. Retry up to `max_merge_retries` times
4. Auto-stash local changes before merge

---

## Data Flow Summary

```mermaid
flowchart TB
    subgraph User["User Input"]
        CMD_INPUT["ll-auto / ll-parallel"]
        FLAGS["--max-issues, --workers, etc."]
    end

    subgraph Config["Configuration"]
        LOAD["Load .claude/ll-config.json"]
        MERGE_CFG["Merge with defaults"]
    end

    subgraph Discovery["Issue Discovery"]
        SCAN["Scan .issues/*/"]
        PARSE["Parse markdown files"]
        SORT["Sort by priority"]
    end

    subgraph Processing["Processing"]
        VALIDATE["Validate (ready_issue)"]
        IMPLEMENT["Implement (manage_issue)"]
        VERIFY["Verify (tests pass)"]
    end

    subgraph Completion["Completion"]
        MOVE["Move to completed/"]
        COMMIT["Git commit"]
        REPORT["Summary report"]
    end

    CMD_INPUT --> LOAD
    FLAGS --> LOAD
    LOAD --> MERGE_CFG
    MERGE_CFG --> SCAN
    SCAN --> PARSE
    PARSE --> SORT
    SORT --> VALIDATE
    VALIDATE --> IMPLEMENT
    IMPLEMENT --> VERIFY
    VERIFY --> MOVE
    MOVE --> COMMIT
    COMMIT --> REPORT
```
