"""Tests for the deep-research built-in FSM loop (FEAT-1540)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "deep-research.yaml"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


class TestDeepResearchYaml:
    """Validate the deep-research YAML parses and passes FSM validation."""

    @pytest.fixture
    def data(self) -> dict:
        assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"
        return yaml.safe_load(LOOP_FILE.read_text())

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists()

    def test_yaml_parses(self, data: dict) -> None:
        assert isinstance(data, dict)

    def test_fsm_validates_without_errors(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_msgs = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert not error_msgs, f"FSM validation errors: {error_msgs}"

    def test_description_is_present(self, data: dict) -> None:
        assert data.get("description"), "deep-research must have a non-empty description"

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "deep-research"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "topic"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {"init", "run_research", "done", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing required states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        state = data["states"]["init"]
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "run_research"

    def test_run_research_delegates_to_oracle(self, data: dict) -> None:
        state = data["states"].get("run_research", {})
        assert state.get("loop") == "oracles/research-coverage", (
            f"run_research.loop should be 'oracles/research-coverage', got {state.get('loop')!r}"
        )

    def test_run_research_with_bindings_present(self, data: dict) -> None:
        state = data["states"].get("run_research", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_, "run_research.with must contain 'run_dir'"
        assert "topic" in with_, "run_research.with must contain 'topic'"
        assert "source_filter" in with_, "run_research.with must contain 'source_filter'"
        assert "academic_mode" in with_, "run_research.with must contain 'academic_mode'"

    def test_run_research_routes_to_done_on_success(self, data: dict) -> None:
        state = data["states"].get("run_research", {})
        assert state.get("on_success") == "done"
        assert state.get("on_failure") == "failed"
        assert state.get("on_error") == "failed"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, "init.action must use $(pwd) for an absolute path"

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        action = data["states"]["init"].get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

    def test_init_touches_all_artifact_files(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        for artifact in ("report.md", "knowledge-base.md", "coverage.md", "query-log.md"):
            assert artifact in action, f"init.action must touch {artifact}"

    def test_terminal_done_state(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True

    def test_context_has_topic(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert "topic" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_depth_and_coverage_threshold(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert "depth" in ctx
        assert "coverage_threshold_pct" in ctx

    def test_context_has_source_filter_and_academic_mode(self, data: dict) -> None:
        """ENH-2161: context must expose source_filter and academic_mode so arxiv stub can override."""
        ctx = data.get("context", {})
        assert "source_filter" in ctx, "context must have source_filter key"
        assert "academic_mode" in ctx, "context must have academic_mode key"
        assert ctx["source_filter"] == "", "default source_filter must be empty string (web-wide)"
        assert ctx["academic_mode"] is False, "default academic_mode must be False"

    def test_run_research_with_uses_context_interpolation(self, data: dict) -> None:
        """ENH-2161: run_research.with must use ${context.*} tokens so stubs can vary the params."""
        state = data["states"].get("run_research", {})
        with_ = state.get("with", {})
        assert with_.get("source_filter") == "${context.source_filter}", (
            f"run_research.with.source_filter must be '${{context.source_filter}}', got {with_.get('source_filter')!r}"
        )
        assert with_.get("academic_mode") == "${context.academic_mode}", (
            f"run_research.with.academic_mode must be '${{context.academic_mode}}', got {with_.get('academic_mode')!r}"
        )

    def test_max_steps_is_30(self, data: dict) -> None:
        assert data.get("max_steps") == 30


class TestDeepResearchShellStates:
    """Exercise the init shell action directly to verify directory and artifact creation."""

    def test_init_creates_run_directory(self, tmp_path: Path) -> None:
        """init action creates the run_dir and all four artifact files."""
        run_dir = tmp_path / ".loops" / "runs" / "deep-research-20260526T120000"
        script = f"""
DIR="{run_dir}"
mkdir -p "$DIR"
: > "$DIR/report.md"
: > "$DIR/knowledge-base.md"
: > "$DIR/coverage.md"
: > "$DIR/query-log.md"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0, f"init shell failed: {result.stderr}"
        assert run_dir.is_dir(), f"Run directory not created: {run_dir}"
        assert (run_dir / "report.md").exists(), "report.md not created"
        assert (run_dir / "knowledge-base.md").exists(), "knowledge-base.md not created"
        assert (run_dir / "coverage.md").exists(), "coverage.md not created"
        assert (run_dir / "query-log.md").exists(), "query-log.md not created"

    def test_init_outputs_absolute_path(self, tmp_path: Path) -> None:
        """init action echoes an absolute path (starts with /)."""
        run_dir = tmp_path / ".loops" / "runs" / "deep-research-20260526T120000"
        script = f"""
DIR="{run_dir}"
mkdir -p "$DIR"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        path = result.stdout.strip()
        assert path.startswith("/"), f"init must output absolute path, got: {path!r}"

    def test_init_handles_absolute_context_run_dir(self, tmp_path: Path) -> None:
        """When ${context.run_dir} is already absolute, init must not double it (BUG-2435)."""
        abs_dir = tmp_path / ".loops" / "runs" / "deep-research-20260526T120000"
        script = f"""
DIR="{abs_dir}"
mkdir -p "$DIR"
case "$DIR" in
  /*) echo "$DIR" ;;
  *) echo "$(pwd)/$DIR" ;;
esac
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert Path(result.stdout.strip()) == abs_dir


class TestDeepResearchResolution:
    """Verify the loop is discoverable via the built-in loop resolver."""

    def test_loop_resolves_as_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_loop_path finds deep-research as a built-in loop."""
        from little_loops.cli.loop._helpers import get_builtin_loops_dir, resolve_loop_path

        monkeypatch.chdir(tmp_path)
        result = resolve_loop_path("deep-research", get_builtin_loops_dir())
        assert result is not None, "deep-research should resolve as a built-in loop"
        assert result.name == "deep-research.yaml"
        assert result.exists()

    def test_loop_loads_with_topic_input(self) -> None:
        """FSMLoop loads from deep-research.yaml with input_key == topic."""
        fsm, _ = load_and_validate(LOOP_FILE)
        assert fsm.input_key == "topic"
        assert "topic" in fsm.context
        assert fsm.initial == "init"


class TestDeepResearchDryRun:
    """CLI smoke test via main_loop with --dry-run."""

    def test_loop_dry_run_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-loop run --dry-run for deep-research outputs the loop name and exits 0."""
        import sys
        from unittest.mock import patch

        from little_loops.cli import main_loop

        monkeypatch.chdir(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-loop", "run", "deep-research", "test research topic", "--dry-run"],
        ):
            result = main_loop()

        captured = capsys.readouterr()
        assert "deep-research" in captured.out
        assert result == 0
