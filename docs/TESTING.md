# Testing Guide

This guide covers all testing patterns, conventions, and examples for contributors to the little-loops project.

> **Related Documentation:**
> - [End-to-End Testing](E2E_TESTING.md) - E2E CLI workflow testing
> - [Contributing Guide](../CONTRIBUTING.md) - Development setup and guidelines
> - [Architecture](ARCHITECTURE.md) - System design and component relationships

## Table of Contents

- [Overview](#overview)
- [Running Tests](#running-tests)
- [Test Suite Organization](#test-suite-organization)
- [Writing Tests](#writing-tests)
- [Advanced Testing](#advanced-testing)
- [Test Patterns by Module](#test-patterns-by-module)
- [CI/CD and Coverage](#ci-cd-and-coverage)

---

## Overview

The little-loops project uses **pytest** as its test framework with comprehensive test coverage across:

- **Unit Tests** - Individual component testing (~50 test modules)
- **Integration Tests** - Component interaction testing (marked with `@pytest.mark.integration`)
- **E2E Tests** - Complete CLI workflow testing (see [E2E_TESTING.md](E2E_TESTING.md))
- **Property-Based Tests** - Hypothesis tests for invariants

### Coverage Requirements

- **Minimum Coverage**: 80% (enforced via `pyproject.toml`)
- **Coverage Report**: Run with `--cov=little_loops --cov-report=html`
- **Exclusions**: Test files and `__init__.py` files

---

## Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest scripts/tests/

# Run only unit tests (fast, excludes integration tests)
pytest -m "not integration" scripts/tests/

# Run only integration tests
pytest -m integration scripts/tests/

# Run with verbose output
pytest scripts/tests/ -v

# Run specific test file
pytest scripts/tests/test_config.py

# Run specific test class
pytest scripts/tests/test_config.py::TestCategoryConfig

# Run specific test method
pytest scripts/tests/test_config.py::TestCategoryConfig::test_from_dict_with_all_fields
```

### Running with Coverage

```bash
# Run with coverage report (terminal + HTML)
pytest scripts/tests/ --cov=little_loops --cov-report=term-missing:skip-covered --cov-report=html

# View HTML coverage report
open scripts/htmlcov/index.html

# Run coverage for specific module
pytest scripts/tests/test_config.py --cov=little_loops.config
```

### Running Marked Tests

```bash
# Run only integration tests
pytest -m integration scripts/tests/

# Exclude integration tests (faster feedback)
pytest -m "not integration" scripts/tests/

# Exclude slow tests
pytest -m "not slow" scripts/tests/

# Run only slow tests
pytest -m slow scripts/tests/
```

### Running Property-Based Tests

```bash
# Run all property-based tests
pytest scripts/tests/test_*_properties.py -v

# Run specific property test file
pytest scripts/tests/test_issue_parser_properties.py -v
```

---

## Test Suite Organization

### Directory Structure

```
scripts/tests/
├── conftest.py                 # Shared pytest fixtures
├── fixtures/                   # Test fixture data
│   ├── fsm/                   # FSM YAML fixtures (8 files)
│   └── issues/                # Issue markdown fixtures (18 files)
├── test_*.py                   # Unit tests (50+ modules)
├── test_*_integration.py       # Integration tests
├── test_*_properties.py        # Property-based tests (Hypothesis)
└── test_cli_e2e.py            # E2E CLI tests
```

### Test File Naming Conventions

| Pattern | Purpose | Example |
|---------|---------|---------|
| `test_<module>.py` | Unit tests for a module | `test_config.py`, `test_issue_parser.py` |
| `test_<feature>_integration.py` | Integration tests | `test_workflow_integration.py` |
| `test_cli_e2e.py` | E2E CLI tests | `test_cli_e2e.py` |
| `test_<module>_properties.py` | Property-based tests | `test_issue_parser_properties.py` |

### Test Class and Method Naming

```python
class TestModuleName:  # Test class: Test + module name
    """Tests for ModuleName component."""

    def test_specific_behavior(self) -> None:  # Test method: test_ + description
        """Test that specific behavior works correctly."""
        pass
```

---

## Writing Tests

### Basic Unit Test Structure

```python
"""Tests for little_loops.config module."""

from pathlib import Path
import pytest


class TestCategoryConfig:
    """Tests for CategoryConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating CategoryConfig with all fields specified."""
        data = {"prefix": "TST", "dir": "test-issues", "action": "verify"}
        config = CategoryConfig.from_dict("tests", data)

        assert config.prefix == "TST"
        assert config.dir == "test-issues"
        assert config.action == "verify"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating CategoryConfig with default values."""
        config = CategoryConfig.from_dict("mytype", {})

        assert config.prefix == "MYT"  # First 3 chars of key uppercased
        assert config.dir == "mytype"
        assert config.action == "fix"
```

### Using Fixtures

#### Built-in Fixtures (from `conftest.py`)

```python
def test_with_temp_project(temp_project_dir: Path) -> None:
    """Test using temporary project directory fixture."""
    # temp_project_dir is auto-created and cleaned up
    config_file = temp_project_dir / ".claude" / "ll-config.json"
    assert temp_project_dir.exists()

def test_with_sample_config(sample_config: dict[str, Any]) -> None:
    """Test using sample configuration fixture."""
    assert "project" in sample_config
    assert sample_config["project"]["name"] == "test-project"

def test_with_issue_fixtures(issue_fixtures: Path) -> None:
    """Test using issue fixtures directory."""
    bug_file = issue_fixtures / "bug-with-frontmatter.md"
    assert bug_file.exists()
```

#### Creating Custom Fixtures

```python
@pytest.fixture
def custom_issue() -> IssueInfo:
    """Create a custom IssueInfo for testing."""
    return IssueInfo(
        path=Path(".issues/bugs/P1-BUG-999-test.md"),
        issue_type="bugs",
        priority="P1",
        issue_id="BUG-999",
        title="Test Bug",
    )

@pytest.fixture
def temp_repo_with_config() -> Generator[Path, None, None]:
    """Create a temporary directory with config (auto-cleanup)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        claude_dir = repo_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "ll-config.json").write_text("{}")
        yield repo_path
        # Cleanup happens automatically via TemporaryDirectory context
```

#### Loading Fixture Files

```python
from tests.conftest import load_fixture

def test_parse_issue(fixtures_dir: Path) -> None:
    """Test parsing issue from fixture file."""
    content = load_fixture(fixtures_dir, "issues", "bug-with-frontmatter.md")
    parser = IssueParser()
    issue = parser.parse(content, Path("test.md"))
    assert issue.issue_id == "BUG-001"
```

### Parametrized Tests

Test multiple scenarios with a single test function:

```python
@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("", []),
        ("?? single.txt\n", ["single.txt"]),
        ("?? a.txt\n?? b.txt\n", ["a.txt", "b.txt"]),
        ('?? "has spaces.txt"\n', ["has spaces.txt"]),
        (" M modified.txt\n", []),
    ],
    ids=["empty", "single", "multiple", "quoted", "modified_only"],
)
def test_various_outputs(self, tmp_path: Path, stdout: str, expected: list[str]) -> None:
    """Parametrized test for various git output scenarios."""
    with patch("little_loops.git_operations.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        )
        result = get_untracked_files(tmp_path)
    assert result == expected
```

### Testing Exceptions

```python
def test_empty_pattern_raises(self) -> None:
    """Test that empty pattern raises ValueError."""
    with pytest.raises(ValueError, match="Pattern cannot be empty"):
        GitignorePattern(pattern="", category="test", description="test")

def test_error_when_no_previous_state(self) -> None:
    """Error when no previous state result exists."""
    fsm = FSMLoop(name="test", initial="a", states={"a": StateConfig(action="echo")})
    executor = FSMExecutor(fsm)
    template = Template("{{state.result.output}}")

    with pytest.raises(InterpolationError, match="No previous state result"):
        template.render(executor)
```

### Testing Output with `capsys`

```python
def test_info_prints_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
    """Message appears in output."""
    logger.info("info message")
    captured = capsys.readouterr()
    assert "info message" in captured.out

def test_format_includes_timestamp(
    self, logger: Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    """Output contains [HH:MM:SS] timestamp."""
    logger.info("test message")
    captured = capsys.readouterr()
    # Match timestamp pattern like [14:32:55]
    assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", captured.out) is not None
```

### Using `tmp_path` for Temporary Files

```python
def test_read_existing_gitignore(self, tmp_path: Path) -> None:
    """Test .gitignore with patterns."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.log\nnode_modules/\n.env\n")
    patterns = _read_existing_gitignore(tmp_path)
    assert patterns == ["*.log", "node_modules/", ".env"]
```

### Using `monkeypatch` for Environment Changes

```python
def test_load_finds_loop_files(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load finds all loop YAML files in .loops directory."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "loop1.yaml").write_text("name: loop1\ninitial: start\nstates:\n  start:\n    terminal: true")

    monkeypatch.chdir(tmp_path)

    manager = LoopStateManager()
    loops = manager.load()

    assert len(loops) == 1
    assert "loop1" in loops
```

---

## Advanced Testing

### Property-Based Testing with Hypothesis

Property-based tests verify invariants hold across thousands of randomly generated inputs.

```python
"""Property-based tests for issue_parser module using Hypothesis."""

from hypothesis import given, settings
from hypothesis import strategies as st

class TestSlugifyProperties:
    """Property tests for slugify function."""

    @given(st.text(max_size=200))
    def test_slugify_idempotent(self, text: str) -> None:
        """Applying slugify twice produces same result as once."""
        assert slugify(slugify(text)) == slugify(text)

    @given(st.text(max_size=200))
    def test_slugify_only_word_chars_and_hyphens(self, text: str) -> None:
        """Output contains only Unicode word characters (\w) and hyphens."""
        import re
        result = slugify(text)
        for c in result:
            assert re.match(r"[\w-]", c, re.UNICODE), f"Unexpected char: {repr(c)}"

    @given(st.text(max_size=200))
    def test_slugify_no_consecutive_hyphens(self, text: str) -> None:
        """Output has no consecutive hyphens."""
        result = slugify(text)
        assert "--" not in result
```

#### Custom Hypothesis Strategies

For complex data structures, create custom strategies:

```python
@st.composite
def goal_spec(draw: st.DrawFn) -> dict:
    """Generate valid goal paradigm specs."""
    goal = draw(
        st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        )
    )
    num_tools = draw(st.integers(min_value=1, max_value=3))
    tools = [draw(st.text(min_size=1, max_size=50)) for _ in range(num_tools)]
    max_iter = draw(st.integers(min_value=1, max_value=100))

    spec: dict = {
        "paradigm": "goal",
        "goal": goal,
        "tools": tools,
        "max_iterations": max_iter,
    }
    return spec

class TestGoalCompilerProperties:
    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_always_three_states(self, spec: dict) -> None:
        """Goal paradigm always produces exactly 3 states."""
        fsm = compile_goal(spec)
        assert len(fsm.states) == 3
        assert set(fsm.states.keys()) == {"evaluate", "fix", "done"}
```

### Mutation Testing with mutmut

Mutation testing verifies test assertion quality by introducing artificial bugs.

```bash
# Run mutation testing (slow - can take hours)
cd scripts
mutmut run

# View results summary
mutmut results

# Show specific surviving mutant details
mutmut show 42

# Apply a mutation to see what it looks like
mutmut apply 42
```

**Configuration** (`scripts/pyproject.toml:122-126`):
```toml
[tool.mutmut]
paths_to_mutate = ["little_loops/"]
pytest_add_cli_args_test_selection = ["tests/"]
pytest_add_cli_args = ["-x", "-q"]
```

### Integration Tests

Mark tests with `@pytest.mark.integration` for component-level testing:

```python
"""Integration tests for the full issue processing workflow."""

import pytest

pytestmark = pytest.mark.integration


class TestSequentialWorkflowIntegration:
    """Integration tests for sequential issue processing (AutoManager)."""

    @pytest.fixture
    def project_setup(self) -> Generator[tuple[Path, dict[str, Any]], None, None]:
        """Create a complete project setup with config and issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # ... setup code
            yield project_root, config
```

### Mock Usage Patterns

#### Mocking Subprocess Calls

```python
from unittest.mock import patch

def test_returns_empty_list_when_no_untracked_files(self, tmp_path: Path) -> None:
    """Returns empty list when git status shows no untracked files."""
    with patch("little_loops.git_operations.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        result = get_untracked_files(tmp_path)
    assert result == []
```

#### Custom Mock Classes

```python
@dataclass
class MockActionRunner:
    """Mock action runner for testing."""
    results: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def run(self, action: str, timeout: int, is_slash_command: bool) -> ActionResult:
        """Return configured result for action."""
        self.calls.append(action)
        for pattern, result_data in self.results:
            if pattern in action:
                return ActionResult(
                    output=result_data.get("output", ""),
                    stderr=result_data.get("stderr", ""),
                    exit_code=result_data.get("exit_code", 0),
                )
        return ActionResult(output="", stderr="", exit_code=0)

# Usage
def test_simple_success_path(self) -> None:
    """check -> done on first success."""
    fsm = FSMLoop(...)
    mock_runner = MockActionRunner()
    mock_runner.set_result("pytest", exit_code=0)

    executor = FSMExecutor(fsm, action_runner=mock_runner)
    result = executor.run()

    assert result.final_state == "done"
```

#### Generator-Based Mock Fixtures

```python
@pytest.fixture
def mock_popen() -> Generator[MagicMock, None, None]:
    """Mock subprocess.Popen that completes immediately."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.stdout = io.StringIO("")
    mock_process.stderr = io.StringIO("")
    mock_process.returncode = 0

    with patch("subprocess.Popen", return_value=mock_process) as mock:
        yield mock
```

---

## Test Patterns by Module

### Testing CLI Commands

#### Argument Parsing Tests

```python
class TestAutoArgumentParsing:
    """Tests for ll-auto (main_auto) argument parsing."""

    def _parse_auto_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_auto."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--resume", "-r", action="store_true")
        parser.add_argument("--dry-run", "-n", action="store_true")
        return parser.parse_args(args)

    def test_default_args(self) -> None:
        """Default values when no arguments provided."""
        args = self._parse_auto_args([])
        assert args.resume is False
        assert args.dry_run is False
```

#### CLI Invocation Tests

```python
def test_ll_auto_dry_run(self, e2e_project_dir: Path) -> None:
    """ll-auto --dry-run should list issues without processing."""
    from unittest.mock import patch
    from little_loops.cli import main_auto

    original_cwd = Path.cwd()
    original_argv = sys.argv.copy()

    try:
        os.chdir(e2e_project_dir)
        sys.argv = ["ll-auto", "--dry-run", "--max-issues", "1"]

        with patch("subprocess.Popen") as mock_popen:
            with patch("subprocess.run"):
                exit_code = main_auto()

        assert exit_code == 0
    finally:
        os.chdir(original_cwd)
        sys.argv = original_argv
```

### Testing Git Operations

```python
class TestGetUntrackedFiles:
    """Tests for get_untracked_files function."""

    def test_returns_untracked_files(self, tmp_path: Path) -> None:
        """Returns list of untracked files from git status."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? file1.txt\n?? file2.py\n?? dir/file3.md\n",
                stderr="",
            )
            result = get_untracked_files(tmp_path)
        assert result == ["dir/file3.md", "file1.txt", "file2.py"]

    def test_ignores_non_untracked_status(self, tmp_path: Path) -> None:
        """Only extracts files with ?? status (untracked), ignores others."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=" M modified.txt\nA  staged.txt\n D deleted.txt\n?? untracked.txt\n",
                stderr="",
            )
            result = get_untracked_files(tmp_path)
        assert result == ["untracked.txt"]
```

### Testing FSM Execution

#### State Transition Testing

```python
def test_simple_success_path(self) -> None:
    """check -> done on first success."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="pytest",
                on_success="done",
                on_failure="fix",
            ),
            "done": StateConfig(terminal=True),
            "fix": StateConfig(action="fix.sh", next="check"),
        },
    )
    mock_runner = MockActionRunner()
    mock_runner.set_result("pytest", exit_code=0)

    executor = FSMExecutor(fsm, action_runner=mock_runner)
    result = executor.run()

    assert result.final_state == "done"
    assert result.iterations == 1
```

#### Variable Interpolation Testing

```python
def test_context_interpolation(self) -> None:
    """${context.*} resolves in action."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        context={"target_dir": "src/"},
        states={
            "check": StateConfig(
                action="mypy ${context.target_dir}",
                on_success="done",
            ),
            "done": StateConfig(terminal=True),
        },
    )
    mock_runner = MockActionRunner()
    mock_runner.always_return(exit_code=0)

    executor = FSMExecutor(fsm, action_runner=mock_runner)
    executor.run()

    assert "mypy src/" in mock_runner.calls
```

### Testing Dataclass Serialization

```python
def test_roundtrip_serialization(self) -> None:
    """Test roundtrip through to_dict and from_dict."""
    original = IssueInfo(
        path=Path("/test/path.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-999",
        title="Critical Bug",
    )
    restored = IssueInfo.from_dict(original.to_dict())

    assert restored.path == original.path
    assert restored.issue_type == original.issue_type
    assert restored.priority == original.priority
    assert restored.issue_id == original.issue_id
    assert restored.title == original.title
```

### Testing Edge Cases

```python
class TestLoggerEdgeCases:
    """Edge case tests for Logger."""

    def test_empty_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty string message still outputs timestamp."""
        logger.info("")
        captured = capsys.readouterr()
        assert re.search(r"\[\d{2}:\d{2}:\d{2}\]", captured.out) is not None

    def test_long_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Long messages are not truncated."""
        long_msg = "x" * 1000
        logger.info(long_msg)
        captured = capsys.readouterr()
        assert long_msg in captured.out

    def test_unicode_message(self, logger: Logger, capsys: pytest.CaptureFixture[str]) -> None:
        """Unicode characters handled correctly."""
        logger.info("Unicode: \u2714 \u2717 \U0001f600")
        captured = capsys.readouterr()
        assert "\u2714" in captured.out
```

### Testing Concurrent/Thread-Safety

```python
def test_concurrent_updates(self, hook_script: Path, tmp_path: Path) -> None:
    """Simulate concurrent hooks updating state file."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def run_hook(tool_name: str) -> subprocess.CompletedProcess:
        """Run hook with tool information."""
        input_data = {"tool_name": tool_name}
        return subprocess.run([str(hook_script)], input=json.dumps(input_data))

    # Run 10 hooks concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(run_hook, "Read") for _ in range(10)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 10
```

---

## CI/CD and Coverage

### Coverage Configuration

**Configuration** (`scripts/pyproject.toml:104-120`):

```toml
[tool.coverage.run]
source = ["little_loops"]
omit = [
    "*/tests/*",
    "*/__init__.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
fail_under = 80
```

### Generating Coverage Reports

```bash
# Generate terminal + HTML coverage report
pytest scripts/tests/ --cov=little_loops --cov-report=term-missing:skip-covered --cov-report=html

# View HTML report (opens in browser)
open scripts/htmlcov/index.html

# Generate XML report for CI tools
pytest scripts/tests/ --cov=little_loops --cov-report=xml
```

### Troubleshooting Coverage Issues

**Missing Coverage for Imported Code**

If a module is imported but not showing in coverage:

1. Verify the module path is in `source = ["little_loops"]`
2. Check that the file isn't in `omit` patterns
3. Ensure tests actually import and execute the code

**Excluded Lines Not Working**

If `pragma: no cover` isn't being respected:

```python
# This should be excluded
if True:  # pragma: no cover
    pass
```

Verify the line is exactly in `exclude_lines` configuration.

### CI/CD Status

> **Note**: CI/CD is not currently configured (no `.github/workflows/`). All testing is run locally via:
> - `pytest scripts/tests/` - Full test suite
> - `ruff check scripts/little_loops/` - Linting
> - `mypy scripts/little_loops/` - Type checking

---

## Quick Reference

### Common pytest Commands

| Command | Purpose |
|---------|---------|
| `pytest scripts/tests/` | Run all tests |
| `pytest -m "not integration"` | Run only unit tests |
| `pytest -m integration` | Run only integration tests |
| `pytest --cov=little_loops` | Run with coverage |
| `pytest -v` | Verbose output |
| `pytest -x` | Stop on first failure |
| `pytest -k "test_name"` | Run tests matching pattern |

### Test Markers

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.integration` | Integration test |
| `@pytest.mark.slow` | Slow-running test |

### Key Fixtures

| Fixture | Purpose |
|---------|---------|
| `temp_project_dir` | Temporary project directory |
| `sample_config` | Sample configuration dict |
| `fixtures_dir` | Path to fixtures |
| `issue_fixtures` | Path to issue fixtures |
| `fsm_fixtures` | Path to FSM fixtures |
| `tmp_path` | Built-in pytest tmp fixture |
| `capsys` | Capture stdout/stderr |
| `monkeypatch` | Modify environment/paths |

### Testing Best Practices

1. **Use descriptive test names** - `test_returns_empty_list_when_no_files` not `test_1`
2. **One assertion per test** - Split complex tests into multiple focused tests
3. **Follow AAA pattern** - Arrange, Act, Assert
4. **Mock external dependencies** - subprocess, file I/O, network calls
5. **Test both success and error paths** - Ensure error handling works
6. **Use fixtures for common setup** - Avoid duplication via `conftest.py`
7. **Parametrize similar tests** - Reduce code duplication
8. **Add docstrings to tests** - Explain what is being tested

---

## Additional Resources

- **E2E Testing**: See [E2E_TESTING.md](E2E_TESTING.md) for CLI workflow testing
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- **Contributing**: See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup
- **API Reference**: See [API.md](API.md) for Python module documentation
