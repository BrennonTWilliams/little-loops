# FEAT-046: State Persistence and Events

## Summary

Implement state persistence for resumable loops and structured event streaming for observability and debugging.

## Priority

P2 - Required for background execution and debugging

## Dependencies

- FEAT-045: FSM Executor Core

## Blocked By

- FEAT-045

## Description

Loops should be resumable after interruption and provide detailed execution logs:

1. **State Persistence** - Save execution state to `.loops/.running/<name>.state.json`
2. **Event Streaming** - Append events to `.loops/.running/<name>.events.jsonl`
3. **Resume Capability** - Continue from saved state after restart

### File Structure

```
.loops/
├── fix-types.yaml          # Loop definition
├── lint-cycle.yaml         # Loop definition
└── .running/               # Runtime state (auto-managed)
    ├── fix-types.state.json
    ├── fix-types.events.jsonl
    ├── lint-cycle.state.json
    └── lint-cycle.events.jsonl
```

## Technical Details

### State File Format

```json
{
  "loop_name": "fix-types",
  "current_state": "fix",
  "iteration": 3,
  "captured": {
    "errors": {
      "output": "4",
      "stderr": "",
      "exit_code": 0,
      "duration_ms": 234
    }
  },
  "prev_result": {
    "output": "...",
    "exit_code": 1,
    "state": "check"
  },
  "last_result": {
    "verdict": "failure",
    "details": {
      "confidence": 0.65,
      "reason": "Still seeing type errors"
    }
  },
  "started_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:32:45Z",
  "status": "running"
}
```

### Event Stream Format

Events are appended to JSONL file, one event per line:

```jsonl
{"event": "loop_start", "loop": "fix-types", "ts": "2024-01-15T10:30:00Z"}
{"event": "state_enter", "state": "check", "iteration": 1, "ts": "2024-01-15T10:30:00Z"}
{"event": "action_start", "action": "mypy src/", "ts": "2024-01-15T10:30:01Z"}
{"event": "action_complete", "exit_code": 1, "duration_ms": 2340, "ts": "2024-01-15T10:30:03Z"}
{"event": "evaluate", "type": "exit_code", "verdict": "failure", "ts": "2024-01-15T10:30:03Z"}
{"event": "route", "from": "check", "to": "fix", "verdict": "failure", "ts": "2024-01-15T10:30:03Z"}
{"event": "state_enter", "state": "fix", "iteration": 1, "ts": "2024-01-15T10:30:03Z"}
{"event": "action_start", "action": "/ll:manage-issue bug fix", "ts": "2024-01-15T10:30:04Z"}
{"event": "action_complete", "duration_ms": 45000, "ts": "2024-01-15T10:31:49Z"}
{"event": "evaluate", "type": "llm_structured", "verdict": "success", "confidence": 0.92, "ts": "2024-01-15T10:31:50Z"}
{"event": "route", "from": "fix", "to": "verify", "verdict": "success", "ts": "2024-01-15T10:31:50Z"}
{"event": "loop_complete", "final_state": "done", "iterations": 3, "terminated_by": "terminal", "ts": "2024-01-15T10:35:00Z"}
```

### Implementation

```python
# persistence.py
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

RUNNING_DIR = ".loops/.running"


@dataclass
class LoopState:
    loop_name: str
    current_state: str
    iteration: int
    captured: dict[str, dict]
    prev_result: dict | None
    last_result: dict | None
    started_at: str
    updated_at: str
    status: str  # "running", "completed", "failed", "interrupted"


class StatePersistence:
    """Manage loop state persistence."""

    def __init__(self, loop_name: str, loops_dir: Path = Path(".loops")):
        self.loop_name = loop_name
        self.running_dir = loops_dir / ".running"
        self.state_file = self.running_dir / f"{loop_name}.state.json"
        self.events_file = self.running_dir / f"{loop_name}.events.jsonl"

    def initialize(self):
        """Create running directory if needed."""
        self.running_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: LoopState):
        """Save current state to file."""
        state.updated_at = _iso_now()
        with open(self.state_file, "w") as f:
            json.dump(asdict(state), f, indent=2)

    def load_state(self) -> LoopState | None:
        """Load state from file, or None if not exists."""
        if not self.state_file.exists():
            return None
        with open(self.state_file) as f:
            data = json.load(f)
        return LoopState(**data)

    def clear_state(self):
        """Remove state file after completion."""
        if self.state_file.exists():
            self.state_file.unlink()

    def append_event(self, event: dict):
        """Append event to JSONL file."""
        with open(self.events_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def read_events(self) -> list[dict]:
        """Read all events from file."""
        if not self.events_file.exists():
            return []
        events = []
        with open(self.events_file) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def clear_events(self):
        """Remove events file."""
        if self.events_file.exists():
            self.events_file.unlink()


class PersistentExecutor:
    """FSM Executor with state persistence."""

    def __init__(
        self,
        fsm: FSMLoop,
        persistence: StatePersistence | None = None,
        **kwargs
    ):
        self.fsm = fsm
        self.persistence = persistence or StatePersistence(fsm.name)
        self.persistence.initialize()

        # Create base executor with event callback that persists
        self.executor = FSMExecutor(
            fsm,
            event_callback=self._handle_event,
            **kwargs
        )

    def _handle_event(self, event: dict):
        """Handle event: persist and optionally forward."""
        self.persistence.append_event(event)
        self._save_state()

    def _save_state(self):
        """Save current executor state."""
        state = LoopState(
            loop_name=self.fsm.name,
            current_state=self.executor.current_state,
            iteration=self.executor.iteration,
            captured=self.executor.captured,
            prev_result=self.executor.prev_result,
            last_result=None,  # Updated after evaluation
            started_at=self.executor.started_at,
            updated_at=_iso_now(),
            status="running",
        )
        self.persistence.save_state(state)

    def run(self) -> ExecutionResult:
        """Run with persistence."""
        result = self.executor.run()

        # Update final state
        final_state = LoopState(
            loop_name=self.fsm.name,
            current_state=result.final_state,
            iteration=result.iterations,
            captured=result.captured,
            prev_result=self.executor.prev_result,
            last_result=None,
            started_at=self.executor.started_at,
            updated_at=_iso_now(),
            status="completed" if result.terminated_by == "terminal" else "failed",
        )
        self.persistence.save_state(final_state)

        return result

    def resume(self) -> ExecutionResult | None:
        """Resume from saved state, or None if no state."""
        state = self.persistence.load_state()
        if state is None:
            return None

        if state.status != "running":
            return None  # Already completed

        # Restore executor state
        self.executor.current_state = state.current_state
        self.executor.iteration = state.iteration
        self.executor.captured = state.captured
        self.executor.prev_result = state.prev_result
        self.executor.started_at = state.started_at

        # Continue execution
        return self.run()


def list_running_loops(loops_dir: Path = Path(".loops")) -> list[LoopState]:
    """List all loops with running state."""
    running_dir = loops_dir / ".running"
    if not running_dir.exists():
        return []

    states = []
    for state_file in running_dir.glob("*.state.json"):
        with open(state_file) as f:
            data = json.load(f)
        states.append(LoopState(**data))
    return states


def get_loop_history(loop_name: str, loops_dir: Path = Path(".loops")) -> list[dict]:
    """Get event history for a loop."""
    persistence = StatePersistence(loop_name, loops_dir)
    return persistence.read_events()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

## Acceptance Criteria

- [ ] `.loops/.running/` directory created automatically
- [ ] State saved to `<name>.state.json` after each state transition
- [ ] Events appended to `<name>.events.jsonl` as they occur
- [ ] `load_state()` returns `None` if no state file exists
- [ ] `resume()` continues from saved state maintaining iteration count
- [ ] `resume()` returns `None` for completed/failed loops
- [ ] `list_running_loops()` returns all loops with "running" status
- [ ] `get_loop_history()` returns all events for a loop
- [ ] State file includes: loop_name, current_state, iteration, captured, started_at, status
- [ ] Event file is append-only JSONL format
- [ ] Cleanup: state file remains after completion (for history), cleared on new run

## Testing Requirements

```python
# tests/integration/test_persistence.py
class TestStatePersistence:
    def test_save_and_load_state(self, tmp_path):
        """State round-trips through save/load."""
        persistence = StatePersistence("test-loop", tmp_path)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="fix",
            iteration=3,
            captured={"errors": {"output": "4"}},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)

        loaded = persistence.load_state()
        assert loaded.current_state == "fix"
        assert loaded.iteration == 3
        assert loaded.captured["errors"]["output"] == "4"

    def test_append_events(self, tmp_path):
        """Events append to JSONL file."""
        persistence = StatePersistence("test-loop", tmp_path)
        persistence.initialize()

        persistence.append_event({"event": "loop_start", "ts": "..."})
        persistence.append_event({"event": "state_enter", "state": "check", "ts": "..."})

        events = persistence.read_events()
        assert len(events) == 2
        assert events[0]["event"] == "loop_start"

    def test_resume_continues_execution(self, tmp_path, mock_action_runner):
        """Resume picks up from saved state."""
        # First run: interrupt mid-execution
        # ...

        # Second run: resume
        executor = PersistentExecutor(fsm, persistence)
        result = executor.resume()

        assert result is not None
        assert result.iterations > saved_iteration

    def test_resume_returns_none_for_completed(self, tmp_path):
        """Resume returns None if loop already completed."""
        # Save completed state
        state = LoopState(..., status="completed")
        persistence.save_state(state)

        result = PersistentExecutor(fsm, persistence).resume()
        assert result is None
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` sections "State Persistence" and "Structured Events"

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made

- `scripts/little_loops/fsm/persistence.py`: New module implementing:
  - `LoopState` dataclass for persistent state
  - `StatePersistence` class for file I/O (state.json and events.jsonl)
  - `PersistentExecutor` wrapper for FSMExecutor with persistence
  - `list_running_loops()` utility function
  - `get_loop_history()` utility function
- `scripts/little_loops/fsm/__init__.py`: Added exports for new persistence module
- `scripts/tests/test_fsm_persistence.py`: Comprehensive test suite (41 tests) covering all acceptance criteria

### Verification Results

- Tests: PASS (41 new tests, 1043 total)
- Lint: PASS
- Types: PASS
