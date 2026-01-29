# ENH-169: Add property-based tests for parsers using Hypothesis - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-169-property-based-tests-for-parsers.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### Key Discoveries
- No existing Hypothesis usage in the codebase (confirmed via grep)
- Dev dependencies in `scripts/pyproject.toml:56-62` include pytest, pytest-cov, ruff, mypy
- Existing test patterns use class-based organization with pytest fixtures
- All tests have type hints and docstrings

### Parser Files to Test
1. **issue_parser.py** (508 lines):
   - `IssueInfo` dataclass with `to_dict()`/`from_dict()` at lines 109-134
   - `IssueParser.parse_file()` entry point at line 158
   - `_parse_priority()` at line 198 - extracts priority from filename
   - `_parse_type_and_id()` at line 224 - extracts type and ID from filename
   - `_parse_frontmatter()` at line 287 - parses YAML frontmatter
   - `_parse_section_items()` at line 349 - extracts issue IDs from sections
   - `_strip_code_fences()` at line 387 - removes code fence content
   - `slugify()` at line 23 - text to slug conversion

2. **fsm/compilers.py** (469 lines):
   - `compile_paradigm()` dispatcher at line 81
   - `compile_goal()` at line 134 - produces 3 states (evaluate, fix, done)
   - `compile_convergence()` at line 205 - produces 3 states (measure, apply, done)
   - `compile_invariants()` at line 288 - produces 2*N+1 states
   - `compile_imperative()` at line 387 - produces N+2 states

3. **fsm/schema.py** - Key dataclasses:
   - `EvaluateConfig.to_dict()`/`from_dict()` at lines 73-125
   - `RouteConfig.to_dict()`/`from_dict()` at lines 144-161
   - `StateConfig.to_dict()`/`from_dict()` at lines 200-255
   - `FSMLoop.to_dict()`/`from_dict()` at lines 364-420
   - `FSMLoop.get_all_state_names()`, `get_terminal_states()`, `get_all_referenced_states()`

### Patterns to Follow
- Test classes use `Test<ClassName>` naming convention
- Methods use `test_<behavior>` naming
- Fixtures defined via `@pytest.fixture` decorators
- All tests have `-> None` return type annotations
- Docstrings describe what's being tested

## Desired End State

Property-based tests that verify parser invariants hold across thousands of randomly generated inputs, catching edge cases that example-based tests miss.

### How to Verify
- All tests pass: `python -m pytest scripts/tests/ -v`
- Type checking passes: `python -m mypy scripts/little_loops/`
- Lint passes: `ruff check scripts/`
- Coverage maintained at ≥80%

## What We're NOT Doing

- Not changing existing parser implementations
- Not adding property tests for `workflow_sequence_analyzer.py` (optional future enhancement)
- Not modifying existing example-based tests
- Not adding Hypothesis to runtime dependencies (dev only)

## Solution Approach

1. Add `hypothesis>=6.0` to dev dependencies
2. Create property test files following existing test patterns
3. Build custom Hypothesis strategies for generating valid test data
4. Test key invariants: roundtrip serialization, bounds, determinism

## Implementation Phases

### Phase 1: Add Hypothesis Dependency

#### Overview
Add Hypothesis to the project's dev dependencies.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Changes**: Add hypothesis to dev dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",  # Add this line
    "ruff>=0.1.0",
    "mypy>=1.0",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] `pip install -e "./scripts[dev]"` succeeds
- [ ] `python -c "import hypothesis"` succeeds

---

### Phase 2: Create Issue Parser Property Tests

#### Overview
Create property tests for `issue_parser.py` testing key invariants.

#### Changes Required

**File**: `scripts/tests/test_issue_parser_properties.py` (new file)
**Changes**: Create property tests with custom strategies

Key properties to test:

1. **IssueInfo roundtrip serialization**: `from_dict(info.to_dict()) == info`
2. **slugify idempotence**: `slugify(slugify(x)) == slugify(x)`
3. **slugify bounds**: Output only contains `[a-z0-9-]`
4. **priority_int consistency**: Valid priorities map to 0-5, invalid to 99
5. **Code fence stripping**: No ```` ``` ```` markers in output

```python
"""Property-based tests for issue_parser module using Hypothesis."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from little_loops.issue_parser import IssueInfo, slugify


class TestSlugifyProperties:
    """Property tests for slugify function."""

    @given(st.text(max_size=200))
    def test_slugify_idempotent(self, text: str) -> None:
        """Applying slugify twice produces same result as once."""
        assert slugify(slugify(text)) == slugify(text)

    @given(st.text(max_size=200))
    def test_slugify_only_valid_chars(self, text: str) -> None:
        """Output contains only lowercase letters, digits, and hyphens."""
        result = slugify(text)
        assert all(c.islower() or c.isdigit() or c == "-" for c in result)

    @given(st.text(max_size=200))
    def test_slugify_no_leading_trailing_hyphens(self, text: str) -> None:
        """Output has no leading or trailing hyphens."""
        result = slugify(text)
        if result:
            assert not result.startswith("-")
            assert not result.endswith("-")

    @given(st.text(max_size=200))
    def test_slugify_no_consecutive_hyphens(self, text: str) -> None:
        """Output has no consecutive hyphens."""
        result = slugify(text)
        assert "--" not in result


class TestIssueInfoProperties:
    """Property tests for IssueInfo dataclass."""

    @given(
        path=st.text(min_size=1, max_size=100).map(Path),
        issue_type=st.sampled_from(["bugs", "features", "enhancements"]),
        priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]),
        issue_id=st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True),
        title=st.text(min_size=1, max_size=200),
        blocked_by=st.lists(st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5),
        blocks=st.lists(st.from_regex(r"[A-Z]{2,4}-\d{1,4}", fullmatch=True), max_size=5),
        discovered_by=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
    )
    @settings(max_examples=200)
    def test_roundtrip_serialization(
        self,
        path: Path,
        issue_type: str,
        priority: str,
        issue_id: str,
        title: str,
        blocked_by: list[str],
        blocks: list[str],
        discovered_by: str | None,
    ) -> None:
        """IssueInfo survives roundtrip through to_dict/from_dict."""
        original = IssueInfo(
            path=path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
            discovered_by=discovered_by,
        )
        restored = IssueInfo.from_dict(original.to_dict())

        assert restored.path == original.path
        assert restored.issue_type == original.issue_type
        assert restored.priority == original.priority
        assert restored.issue_id == original.issue_id
        assert restored.title == original.title
        assert restored.blocked_by == original.blocked_by
        assert restored.blocks == original.blocks
        assert restored.discovered_by == original.discovered_by

    @given(priority=st.sampled_from(["P0", "P1", "P2", "P3", "P4", "P5"]))
    def test_priority_int_valid_priorities(self, priority: str) -> None:
        """Valid priorities map to expected integers."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority=priority,
            issue_id="BUG-001",
            title="Test",
        )
        expected = int(priority[1])
        assert info.priority_int == expected

    @given(priority=st.text(max_size=10).filter(lambda x: not x.startswith("P") or not x[1:].isdigit()))
    def test_priority_int_invalid_priorities(self, priority: str) -> None:
        """Invalid priorities map to 99."""
        info = IssueInfo(
            path=Path("test.md"),
            issue_type="bugs",
            priority=priority,
            issue_id="BUG-001",
            title="Test",
        )
        assert info.priority_int == 99
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser_properties.py -v`
- [ ] Types pass: `python -m mypy scripts/tests/test_issue_parser_properties.py`
- [ ] Lint passes: `ruff check scripts/tests/test_issue_parser_properties.py`

---

### Phase 3: Create FSM Compiler Property Tests

#### Overview
Create property tests for `fsm/compilers.py` testing structural invariants.

#### Changes Required

**File**: `scripts/tests/test_fsm_compiler_properties.py` (new file)
**Changes**: Create property tests for FSM compilers

Key properties to test:

1. **All transitions target defined states**: Referenced states exist in `states` dict
2. **Initial state exists**: `fsm.initial` is a key in `fsm.states`
3. **At least one terminal state**: Every FSM has ≥1 terminal state
4. **State count bounds**: Goal=3, Convergence=3, Invariants=2N+1, Imperative=N+2
5. **Roundtrip FSMLoop serialization**: `from_dict(loop.to_dict())` equivalent
6. **Paradigm preserved**: Output `fsm.paradigm` matches input

```python
"""Property-based tests for FSM compilers using Hypothesis."""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from little_loops.fsm.compilers import (
    compile_goal,
    compile_convergence,
    compile_invariants,
    compile_imperative,
    compile_paradigm,
)
from little_loops.fsm.schema import FSMLoop, StateConfig, EvaluateConfig


# Custom strategies for generating valid specs

@st.composite
def goal_spec(draw: st.DrawFn) -> dict:
    """Generate valid goal paradigm specs."""
    goal = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"))))
    num_tools = draw(st.integers(min_value=1, max_value=3))
    tools = [draw(st.text(min_size=1, max_size=50)) for _ in range(num_tools)]
    max_iter = draw(st.integers(min_value=1, max_value=100))

    spec = {
        "paradigm": "goal",
        "goal": goal,
        "tools": tools,
        "max_iterations": max_iter,
    }

    # Optionally add name
    if draw(st.booleans()):
        spec["name"] = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))))

    return spec


@st.composite
def convergence_spec(draw: st.DrawFn) -> dict:
    """Generate valid convergence paradigm specs."""
    name = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))))
    check = draw(st.text(min_size=1, max_size=100))
    toward = draw(st.integers(min_value=0, max_value=1000))
    using = draw(st.text(min_size=1, max_size=50))

    return {
        "paradigm": "convergence",
        "name": name,
        "check": check,
        "toward": toward,
        "using": using,
        "tolerance": draw(st.integers(min_value=0, max_value=10)),
    }


@st.composite
def constraint(draw: st.DrawFn) -> dict:
    """Generate a valid constraint for invariants paradigm."""
    name = draw(st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True))
    return {
        "name": name,
        "check": draw(st.text(min_size=1, max_size=50)),
        "fix": draw(st.text(min_size=1, max_size=50)),
    }


@st.composite
def invariants_spec(draw: st.DrawFn) -> dict:
    """Generate valid invariants paradigm specs."""
    name = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))))
    num_constraints = draw(st.integers(min_value=1, max_value=5))

    # Generate unique constraint names
    constraints = []
    used_names = set()
    for _ in range(num_constraints):
        c = draw(constraint())
        # Ensure unique names
        while c["name"] in used_names:
            c = draw(constraint())
        used_names.add(c["name"])
        constraints.append(c)

    return {
        "paradigm": "invariants",
        "name": name,
        "constraints": constraints,
        "maintain": draw(st.booleans()),
    }


@st.composite
def imperative_spec(draw: st.DrawFn) -> dict:
    """Generate valid imperative paradigm specs."""
    name = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))))
    num_steps = draw(st.integers(min_value=1, max_value=5))
    steps = [draw(st.text(min_size=1, max_size=50)) for _ in range(num_steps)]

    return {
        "paradigm": "imperative",
        "name": name,
        "steps": steps,
        "until": {
            "check": draw(st.text(min_size=1, max_size=50)),
        },
    }


class TestGoalCompilerProperties:
    """Property tests for compile_goal."""

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_always_three_states(self, spec: dict) -> None:
        """Goal paradigm always produces exactly 3 states."""
        fsm = compile_goal(spec)
        assert len(fsm.states) == 3
        assert set(fsm.states.keys()) == {"evaluate", "fix", "done"}

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_initial_state_exists(self, spec: dict) -> None:
        """Initial state exists in states dict."""
        fsm = compile_goal(spec)
        assert fsm.initial in fsm.states

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_has_terminal_state(self, spec: dict) -> None:
        """Has at least one terminal state."""
        fsm = compile_goal(spec)
        terminal_states = fsm.get_terminal_states()
        assert len(terminal_states) >= 1
        assert "done" in terminal_states

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_goal(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_paradigm_preserved(self, spec: dict) -> None:
        """Output paradigm matches input."""
        fsm = compile_goal(spec)
        assert fsm.paradigm == "goal"


class TestConvergenceCompilerProperties:
    """Property tests for compile_convergence."""

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_always_three_states(self, spec: dict) -> None:
        """Convergence paradigm always produces exactly 3 states."""
        fsm = compile_convergence(spec)
        assert len(fsm.states) == 3
        assert set(fsm.states.keys()) == {"measure", "apply", "done"}

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_convergence(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined


class TestInvariantsCompilerProperties:
    """Property tests for compile_invariants."""

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_state_count_formula(self, spec: dict) -> None:
        """State count is 2*N+1 where N is number of constraints."""
        fsm = compile_invariants(spec)
        n = len(spec["constraints"])
        expected = 2 * n + 1
        assert len(fsm.states) == expected

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_invariants(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_has_all_valid_terminal(self, spec: dict) -> None:
        """Has all_valid terminal state."""
        fsm = compile_invariants(spec)
        assert "all_valid" in fsm.states
        assert fsm.states["all_valid"].terminal is True


class TestImperativeCompilerProperties:
    """Property tests for compile_imperative."""

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_state_count_formula(self, spec: dict) -> None:
        """State count is N+2 where N is number of steps."""
        fsm = compile_imperative(spec)
        n = len(spec["steps"])
        expected = n + 2  # step_0..step_n-1 + check_done + done
        assert len(fsm.states) == expected

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_imperative(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined


class TestFSMLoopProperties:
    """Property tests for FSMLoop serialization."""

    @given(spec=goal_spec())
    @settings(max_examples=50)
    def test_goal_roundtrip(self, spec: dict) -> None:
        """Goal FSM survives roundtrip serialization."""
        original = compile_goal(spec)
        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert restored.paradigm == original.paradigm
        assert set(restored.states.keys()) == set(original.states.keys())

    @given(spec=convergence_spec())
    @settings(max_examples=50)
    def test_convergence_roundtrip(self, spec: dict) -> None:
        """Convergence FSM survives roundtrip serialization."""
        original = compile_convergence(spec)
        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert set(restored.states.keys()) == set(original.states.keys())
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compiler_properties.py -v`
- [ ] Types pass: `python -m mypy scripts/tests/test_fsm_compiler_properties.py`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_compiler_properties.py`

---

### Phase 4: Full Test Suite Verification

#### Overview
Run full test suite to ensure no regressions.

#### Success Criteria

**Automated Verification**:
- [ ] Full test suite passes: `python -m pytest scripts/tests/ -v`
- [ ] Coverage ≥80%: `python -m pytest scripts/tests/ --cov=little_loops --cov-fail-under=80`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

## Testing Strategy

### Unit Tests
- Property tests verify invariants across many random inputs
- Tests use `@settings(max_examples=N)` to control test count

### Edge Cases
- Empty strings for slugify
- Single-character inputs
- Unicode characters
- Boundary values for state counts

## References

- Original issue: `.issues/enhancements/P3-ENH-169-property-based-tests-for-parsers.md`
- Issue parser: `scripts/little_loops/issue_parser.py`
- FSM compilers: `scripts/little_loops/fsm/compilers.py`
- FSM schema: `scripts/little_loops/fsm/schema.py`
- Existing tests: `scripts/tests/test_issue_parser.py`, `scripts/tests/test_fsm_compilers.py`
