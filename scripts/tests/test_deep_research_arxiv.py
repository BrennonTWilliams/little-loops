"""Tests for the deep-research-arxiv built-in FSM loop (FEAT-1673).

After ENH-2161, deep-research-arxiv.yaml became a from: deep-research stub that
overrides context.source_filter and context.academic_mode.  Tests use two fixtures:
  data         — raw YAML (stub-level: name, from, visibility, context overrides)
  resolved_data — inheritance-resolved YAML (inherited states, scalars, and context)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.fragments import resolve_fragments, resolve_inheritance
from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "deep-research-arxiv.yaml"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


class TestDeepResearchArxivYaml:
    """Validate the deep-research-arxiv YAML parses and passes FSM validation."""

    @pytest.fixture
    def data(self) -> dict:
        """Raw stub YAML — tests stub-specific fields (from, visibility, context overrides)."""
        assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"
        return yaml.safe_load(LOOP_FILE.read_text())

    @pytest.fixture
    def resolved_data(self) -> dict:
        """Inheritance-resolved YAML — tests fields inherited from deep-research."""
        raw = yaml.safe_load(LOOP_FILE.read_text())
        raw = resolve_inheritance(raw, BUILTIN_LOOPS_DIR)
        raw = resolve_fragments(raw, BUILTIN_LOOPS_DIR)
        return raw

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
        assert data.get("description"), "deep-research-arxiv must have a non-empty description"

    def test_stub_inherits_from_deep_research(self, data: dict) -> None:
        """After ENH-2161, arxiv stub must declare from: deep-research."""
        assert data.get("from") == "deep-research", (
            f"deep-research-arxiv must inherit from 'deep-research', got {data.get('from')!r}"
        )

    def test_stub_is_internal_visibility(self, data: dict) -> None:
        """Stub must be hidden from ll-loop list; canonical entry is deep-research."""
        assert data.get("visibility") == "internal", (
            f"deep-research-arxiv must have visibility: internal, got {data.get('visibility')!r}"
        )

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "deep-research-arxiv"
        assert data.get("input_key") == "topic"

    def test_required_states_exist(self, resolved_data: dict) -> None:
        required = {"init", "run_research", "done", "failed"}
        actual = set(resolved_data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing required states: {missing}"

    def test_init_state_is_shell_with_capture(self, resolved_data: dict) -> None:
        state = resolved_data["states"]["init"]
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "run_research"

    def test_init_action_uses_absolute_path(self, resolved_data: dict) -> None:
        action = resolved_data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, "init.action must use $(pwd) for an absolute path"

    def test_init_touches_all_artifact_files(self, resolved_data: dict) -> None:
        action = resolved_data["states"]["init"].get("action", "")
        for artifact in ("report.md", "knowledge-base.md", "coverage.md", "query-log.md"):
            assert artifact in action, f"init.action must touch {artifact}"

    def test_terminal_done_state(self, resolved_data: dict) -> None:
        assert resolved_data["states"]["done"].get("terminal") is True

    def test_context_has_topic(self, resolved_data: dict) -> None:
        ctx = resolved_data.get("context", {})
        assert "topic" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_depth_and_coverage_threshold(self, resolved_data: dict) -> None:
        ctx = resolved_data.get("context", {})
        assert "depth" in ctx
        assert "coverage_threshold_pct" in ctx

    def test_max_iterations_is_30(self, resolved_data: dict) -> None:
        assert resolved_data.get("max_iterations") == 30

    def test_timeout_is_3600(self, resolved_data: dict) -> None:
        assert resolved_data.get("timeout") == 3600

    def test_category_is_research(self, resolved_data: dict) -> None:
        assert resolved_data.get("category") == "research"

    def test_run_research_source_filter_is_arxiv(self, data: dict) -> None:
        """Stub must override context.source_filter to constrain queries to arxiv."""
        ctx = data.get("context", {})
        assert ctx.get("source_filter") == "site:arxiv.org", (
            f"context.source_filter must be 'site:arxiv.org', got {ctx.get('source_filter')!r}"
        )

    def test_run_research_academic_mode_is_true(self, data: dict) -> None:
        """Stub must override context.academic_mode to enable recency scoring and BibTeX."""
        ctx = data.get("context", {})
        assert ctx.get("academic_mode") is True, (
            f"context.academic_mode must be True, got {ctx.get('academic_mode')!r}"
        )

    def test_run_research_delegates_to_oracle(self, resolved_data: dict) -> None:
        state = resolved_data["states"].get("run_research", {})
        assert state.get("loop") == "oracles/research-coverage", (
            f"run_research.loop should be 'oracles/research-coverage', got {state.get('loop')!r}"
        )

    def test_run_research_with_bindings_present(self, resolved_data: dict) -> None:
        state = resolved_data["states"].get("run_research", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_
        assert "topic" in with_
        assert "source_filter" in with_
        assert "academic_mode" in with_

    def test_run_research_routes_to_done_on_success(self, resolved_data: dict) -> None:
        state = resolved_data["states"].get("run_research", {})
        assert state.get("on_success") == "done"
        assert state.get("on_failure") == "failed"
        assert state.get("on_error") == "failed"


class TestDeepResearchArxivShellStates:
    """Exercise the init shell action directly to verify directory and artifact creation."""

    def test_init_creates_run_directory(self, tmp_path: Path) -> None:
        """init action creates the run_dir and all four artifact files."""
        run_dir = tmp_path / ".loops" / "runs" / "deep-research-arxiv-20260526T120000"
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
        run_dir = tmp_path / ".loops" / "runs" / "deep-research-arxiv-20260526T120000"
        script = f"""
DIR="{run_dir}"
mkdir -p "$DIR"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        path = result.stdout.strip()
        assert path.startswith("/"), f"init must output absolute path, got: {path!r}"


class TestDeepResearchArxivResolution:
    """Verify the loop is discoverable via the built-in loop resolver."""

    def test_loop_resolves_as_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_loop_path finds deep-research-arxiv as a built-in loop."""
        from little_loops.cli.loop._helpers import get_builtin_loops_dir, resolve_loop_path

        monkeypatch.chdir(tmp_path)
        result = resolve_loop_path("deep-research-arxiv", get_builtin_loops_dir())
        assert result is not None, "deep-research-arxiv should resolve as a built-in loop"
        assert result.name == "deep-research-arxiv.yaml"
        assert result.exists()

    def test_loop_loads_with_topic_input(self) -> None:
        """FSMLoop loads from deep-research-arxiv.yaml with input_key == topic."""
        fsm, _ = load_and_validate(LOOP_FILE)
        assert fsm.input_key == "topic"
        assert "topic" in fsm.context
        assert fsm.initial == "init"

    def test_resolved_context_has_arxiv_overrides(self) -> None:
        """After inheritance resolution, context must contain arxiv-specific values."""
        fsm, _ = load_and_validate(LOOP_FILE)
        assert fsm.context.get("source_filter") == "site:arxiv.org"
        assert fsm.context.get("academic_mode") is True


class TestDeepResearchArxivDryRun:
    """CLI smoke test via main_loop with --dry-run."""

    def test_loop_dry_run_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-loop run --dry-run for deep-research-arxiv outputs the loop name and exits 0."""
        import sys
        from unittest.mock import patch

        from little_loops.cli import main_loop

        monkeypatch.chdir(tmp_path)

        with patch.object(
            sys,
            "argv",
            ["ll-loop", "run", "deep-research-arxiv", "test research topic", "--dry-run"],
        ):
            result = main_loop()

        captured = capsys.readouterr()
        assert "deep-research-arxiv" in captured.out
        assert result == 0
