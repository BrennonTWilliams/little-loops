# ENH-182: Add State Persistence to ll-sprint - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-182-add-state-persistence-to-ll-sprint.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `ll-sprint` command executes sprints in dependency-aware waves but lacks any state persistence. When a sprint is interrupted (Ctrl+C, crash, timeout), all progress is lost.

### Key Discoveries
- `_cmd_sprint_run()` in `cli.py:1619-1741` tracks progress only in local variables (`completed`, `failed_waves`)
- `StateManager` class in `state.py:76-203` provides the canonical pattern for state persistence
- `ProcessingState` dataclass in `state.py:17-73` shows the serialization pattern with `to_dict()`/`from_dict()`
- ll-auto uses `.auto-manage-state.json`, ll-parallel uses `.parallel-manage-state.json`
- Sprint runs process waves sequentially, with single-issue waves using `process_issue_inplace()` and multi-issue waves using `ParallelOrchestrator`

## Desired End State

- Sprint execution state persists to `.sprint-state.json`
- `--resume/-r` flag allows continuing interrupted sprints
- Completed waves/issues are tracked and skipped on resume
- State file is cleaned up on successful completion (no failures)

### How to Verify
- Run a sprint, interrupt mid-execution, resume and verify it continues from the correct wave
- Run a sprint to completion and verify the state file is removed
- Run tests for the new `SprintState` dataclass and integration

## What We're NOT Doing

- Not adding state persistence to individual `process_issue_inplace()` calls (that's handled by ll-auto's StateManager)
- Not persisting state for `ParallelOrchestrator` waves (it has its own state management)
- Not adding a separate `SprintStateManager` class - will use inline methods in `_cmd_sprint_run()` following the `ParallelOrchestrator` pattern
- Not modifying the `Sprint` or `SprintManager` classes - state is runtime execution state, not sprint definition

## Problem Analysis

The sprint run function needs to:
1. Track which waves have been completed
2. Save state after each wave completes
3. Load state on startup when `--resume` flag is present
4. Skip already-completed waves when resuming
5. Clean up state file on successful completion

## Solution Approach

Follow the `ParallelOrchestrator` pattern (inline `_load_state`, `_save_state`, `_cleanup_state` methods) rather than creating a separate manager class. The `SprintState` dataclass will be added to `sprint.py` alongside `Sprint` and `SprintOptions`.

## Implementation Phases

### Phase 1: Add SprintState Dataclass

#### Overview
Add the `SprintState` dataclass to `sprint.py` following the `ProcessingState` pattern.

#### Changes Required

**File**: `scripts/little_loops/sprint.py`
**Changes**: Add `SprintState` dataclass after `SprintOptions` (around line 54)

```python
@dataclass
class SprintState:
    """Persistent state for sprint execution.

    Enables resume capability after interruption by tracking:
    - Sprint name being executed
    - Current wave number
    - Completed issues
    - Failed issues with reasons
    - Timing information

    Attributes:
        sprint_name: Name of the sprint being executed
        current_wave: Wave number currently being processed (1-indexed)
        completed_issues: List of completed issue IDs
        failed_issues: Mapping of issue ID to failure reason
        timing: Per-issue timing breakdown
        started_at: ISO 8601 timestamp when sprint started
        last_checkpoint: ISO 8601 timestamp of last state save
    """

    sprint_name: str = ""
    current_wave: int = 0
    completed_issues: list[str] = field(default_factory=list)
    failed_issues: dict[str, str] = field(default_factory=dict)
    timing: dict[str, dict[str, float]] = field(default_factory=dict)
    started_at: str = ""
    last_checkpoint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return {
            "sprint_name": self.sprint_name,
            "current_wave": self.current_wave,
            "completed_issues": self.completed_issues,
            "failed_issues": self.failed_issues,
            "timing": self.timing,
            "started_at": self.started_at,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SprintState":
        """Create state from dictionary (JSON deserialization)."""
        return cls(
            sprint_name=data.get("sprint_name", ""),
            current_wave=data.get("current_wave", 0),
            completed_issues=data.get("completed_issues", []),
            failed_issues=data.get("failed_issues", {}),
            timing=data.get("timing", {}),
            started_at=data.get("started_at", ""),
            last_checkpoint=data.get("last_checkpoint", ""),
        )
```

Also add `Any` to the typing imports and `json` to imports.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/sprint.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/sprint.py`

---

### Phase 2: Add --resume Flag to CLI

#### Overview
Add the `--resume/-r` argument to the sprint run subparser.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add argument to run subparser at line 1320

```python
run_parser.add_argument(
    "--resume",
    "-r",
    action="store_true",
    help="Resume from previous checkpoint",
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Help output shows --resume flag: `ll-sprint run --help`

---

### Phase 3: Integrate State into Sprint Run

#### Overview
Add state persistence logic to `_cmd_sprint_run()` function.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Modify `_cmd_sprint_run()` at lines 1619-1741

1. Add imports at top of file (around line 30):
```python
import json
```

2. Add helper functions before `_cmd_sprint_run()` (around line 1617):
```python
def _get_sprint_state_file() -> Path:
    """Get path to sprint state file."""
    return Path.cwd() / ".sprint-state.json"


def _load_sprint_state(logger: Logger) -> SprintState | None:
    """Load sprint state from file."""
    state_file = _get_sprint_state_file()
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
        state = SprintState.from_dict(data)
        logger.info(f"State loaded from {state_file}")
        return state
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to load state: {e}")
        return None


def _save_sprint_state(state: SprintState, logger: Logger) -> None:
    """Save sprint state to file."""
    state.last_checkpoint = datetime.now().isoformat()
    state_file = _get_sprint_state_file()
    state_file.write_text(json.dumps(state.to_dict(), indent=2))
    logger.info(f"State saved to {state_file}")


def _cleanup_sprint_state(logger: Logger) -> None:
    """Remove sprint state file."""
    state_file = _get_sprint_state_file()
    if state_file.exists():
        state_file.unlink()
        logger.info("Sprint state file cleaned up")
```

3. Modify `_cmd_sprint_run()` to use state persistence:

After sprint/dependency validation (around line 1662), add state initialization:
```python
    # Initialize or load state
    state: SprintState
    start_wave = 1

    if args.resume:
        loaded_state = _load_sprint_state(logger)
        if loaded_state and loaded_state.sprint_name == args.sprint:
            state = loaded_state
            # Find first incomplete wave by checking completed issues
            completed_set = set(state.completed_issues)
            for i, wave in enumerate(waves, 1):
                wave_ids = {issue.issue_id for issue in wave}
                if not wave_ids.issubset(completed_set):
                    start_wave = i
                    break
            else:
                # All waves completed
                logger.info("Sprint already completed - nothing to resume")
                _cleanup_sprint_state(logger)
                return 0
            logger.info(f"Resuming from wave {start_wave}/{len(waves)}")
            logger.info(f"  Previously completed: {len(state.completed_issues)} issues")
        else:
            logger.warning("No valid state found - starting fresh")
            state = SprintState(
                sprint_name=args.sprint,
                started_at=datetime.now().isoformat(),
            )
    else:
        # Fresh start - delete any old state
        _cleanup_sprint_state(logger)
        state = SprintState(
            sprint_name=args.sprint,
            started_at=datetime.now().isoformat(),
        )
```

4. Modify wave loop to use start_wave and save state:
```python
    for wave_num, wave in enumerate(waves, 1):
        # Skip already-completed waves when resuming
        if wave_num < start_wave:
            continue

        wave_ids = [issue.issue_id for issue in wave]
        state.current_wave = wave_num
        ...
```

5. After each wave completion, update state:
```python
        # After successful wave processing:
        state.completed_issues.extend(wave_ids)
        state.timing.update({...})  # if timing available
        _save_sprint_state(state, logger)
```

6. For failed waves, track failures:
```python
        # On wave failure:
        for issue_id in wave_ids:
            if issue_id not in state.completed_issues:
                state.failed_issues[issue_id] = "Wave execution failed"
        _save_sprint_state(state, logger)
```

7. At end of function, clean up on success:
```python
    # Before return 0:
    if failed_waves == 0:
        _cleanup_sprint_state(logger)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] Run `ll-sprint run test-sprint`, interrupt with Ctrl+C, verify `.sprint-state.json` exists
- [ ] Run `ll-sprint run test-sprint --resume`, verify it continues from correct wave
- [ ] Run sprint to completion, verify `.sprint-state.json` is removed

---

### Phase 4: Add Tests

#### Overview
Add tests for `SprintState` dataclass and integration tests for resume functionality.

#### Changes Required

**File**: `scripts/tests/test_sprint.py`
**Changes**: Add tests for `SprintState`

```python
class TestSprintState:
    """Tests for SprintState dataclass."""

    def test_default_values(self) -> None:
        """SprintState has correct default values."""
        state = SprintState()

        assert state.sprint_name == ""
        assert state.current_wave == 0
        assert state.completed_issues == []
        assert state.failed_issues == {}
        assert state.timing == {}
        assert state.started_at == ""
        assert state.last_checkpoint == ""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        state = SprintState(
            sprint_name="test-sprint",
            current_wave=2,
            completed_issues=["BUG-001", "FEAT-002"],
            failed_issues={"BUG-003": "Timeout"},
            timing={"BUG-001": {"total": 120.5}},
            started_at="2026-01-29T10:00:00",
            last_checkpoint="2026-01-29T10:30:00",
        )

        result = state.to_dict()

        assert result["sprint_name"] == "test-sprint"
        assert result["current_wave"] == 2
        assert result["completed_issues"] == ["BUG-001", "FEAT-002"]
        assert result["failed_issues"] == {"BUG-003": "Timeout"}
        assert result["timing"] == {"BUG-001": {"total": 120.5}}
        assert result["started_at"] == "2026-01-29T10:00:00"
        assert result["last_checkpoint"] == "2026-01-29T10:30:00"

    def test_to_dict_json_serializable(self) -> None:
        """Test that to_dict output is JSON serializable."""
        state = SprintState(
            sprint_name="test",
            current_wave=1,
            completed_issues=["A"],
        )

        result = state.to_dict()
        # Should not raise
        json.dumps(result)

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "sprint_name": "my-sprint",
            "current_wave": 3,
            "completed_issues": ["FEAT-001"],
            "failed_issues": {"FEAT-002": "Error"},
            "timing": {"FEAT-001": {"ready": 10.0}},
            "started_at": "2026-01-29T09:00:00",
            "last_checkpoint": "2026-01-29T09:45:00",
        }

        state = SprintState.from_dict(data)

        assert state.sprint_name == "my-sprint"
        assert state.current_wave == 3
        assert state.completed_issues == ["FEAT-001"]
        assert state.failed_issues == {"FEAT-002": "Error"}

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict with missing keys uses defaults."""
        data = {"sprint_name": "partial"}

        state = SprintState.from_dict(data)

        assert state.sprint_name == "partial"
        assert state.current_wave == 0
        assert state.completed_issues == []
        assert state.failed_issues == {}

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip through to_dict and from_dict."""
        original = SprintState(
            sprint_name="roundtrip-test",
            current_wave=2,
            completed_issues=["A", "B"],
            failed_issues={"C": "error"},
            timing={"A": {"total": 50.0}},
            started_at="2026-01-29T08:00:00",
            last_checkpoint="2026-01-29T08:30:00",
        )

        restored = SprintState.from_dict(original.to_dict())

        assert restored.sprint_name == original.sprint_name
        assert restored.current_wave == original.current_wave
        assert restored.completed_issues == original.completed_issues
        assert restored.failed_issues == original.failed_issues
        assert restored.timing == original.timing
        assert restored.started_at == original.started_at
        assert restored.last_checkpoint == original.last_checkpoint
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_sprint.py::TestSprintState -v`
- [ ] All sprint tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_sprint.py`

---

## Testing Strategy

### Unit Tests
- `SprintState` dataclass serialization/deserialization
- Default values and missing field handling
- JSON roundtrip serialization

### Integration Tests
- Resume from partial completion
- Clean start when no state exists
- State cleanup on successful completion

## References

- Original issue: `.issues/enhancements/P2-ENH-182-add-state-persistence-to-ll-sprint.md`
- StateManager pattern: `scripts/little_loops/state.py:76-203`
- ProcessingState pattern: `scripts/little_loops/state.py:17-73`
- OrchestratorState pattern: `scripts/little_loops/parallel/types.py:175-226`
- Sprint run function: `scripts/little_loops/cli.py:1619-1741`
