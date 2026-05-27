"""Tests for the rn-refine loop init state shell logic and routing structure.

Validates file-not-found error handling, the cp-based content preservation that
distinguishes rn-refine from rn-plan's blank init, and the routing fix that
ensures the report state fires before done.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from little_loops.fsm.validation import load_and_validate


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


# Shell body of the rn-refine init state, parametrized by plan_file and run_dir.
def _init_script(plan_file: str, run_dir: str) -> str:
    return f"""
    if [ ! -f "{plan_file}" ]; then
      echo "ERROR: Plan file not found: {plan_file}"
      exit 1
    fi
    DIR="{run_dir}"
    mkdir -p "$DIR"
    cp "{plan_file}" "$DIR/plan.md"
    realpath "{plan_file}" > "$DIR/.source-path"
    : > "$DIR/plan-rubric.md"
    : > "$DIR/research.md"
    echo "$(pwd)/$DIR"
    """


class TestInitFileNotFound:
    """init exits non-zero with an error message when plan_file does not exist."""

    def test_missing_file_exits_nonzero(self, tmp_path: Path) -> None:
        """Non-existent plan_file path causes exit code 1."""
        run_dir = str(tmp_path / ".loops" / "runs" / "rn-refine-20260526T120000")
        result = _bash(_init_script("nonexistent/plan.md", run_dir), tmp_path)

        assert result.returncode != 0

    def test_missing_file_error_message_on_stdout(self, tmp_path: Path) -> None:
        """Error message is emitted to stdout when plan_file is missing."""
        run_dir = str(tmp_path / ".loops" / "runs" / "rn-refine-20260526T120000")
        result = _bash(_init_script("nonexistent/plan.md", run_dir), tmp_path)

        assert "ERROR" in result.stdout or "ERROR" in result.stderr

    def test_no_run_dir_created_when_file_missing(self, tmp_path: Path) -> None:
        """No run directory is created when plan_file does not exist."""
        run_dir = tmp_path / ".loops" / "runs" / "rn-refine-20260526T120000"
        _bash(_init_script("nonexistent/plan.md", str(run_dir)), tmp_path)

        assert not run_dir.exists()


class TestInitFileCopy:
    """init copies source plan content into the run directory rather than blank-initializing."""

    def _run_dir(self, tmp_path: Path) -> Path:
        return tmp_path / ".loops" / "runs" / "rn-refine-20260526T120000"

    def test_source_content_preserved_in_run_dir(self, tmp_path: Path) -> None:
        """Content of the source plan file is copied verbatim to $DIR/plan.md."""
        content = "# Existing Plan\n\nThis is my plan content.\n"
        plan = tmp_path / "existing-plan.md"
        plan.write_text(content)
        run_dir = self._run_dir(tmp_path)

        result = _bash(_init_script(str(plan), str(run_dir)), tmp_path)

        assert result.returncode == 0
        copied = (run_dir / "plan.md").read_text()
        assert copied == content

    def test_plan_rubric_initialized_empty(self, tmp_path: Path) -> None:
        """plan-rubric.md is created as an empty file in the run directory."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")
        run_dir = self._run_dir(tmp_path)

        result = _bash(_init_script(str(plan), str(run_dir)), tmp_path)

        assert result.returncode == 0
        assert (run_dir / "plan-rubric.md").exists()
        assert (run_dir / "plan-rubric.md").read_text() == ""

    def test_research_md_initialized_empty(self, tmp_path: Path) -> None:
        """research.md is created as an empty file in the run directory."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")
        run_dir = self._run_dir(tmp_path)

        result = _bash(_init_script(str(plan), str(run_dir)), tmp_path)

        assert result.returncode == 0
        assert (run_dir / "research.md").exists()
        assert (run_dir / "research.md").read_text() == ""

    def test_run_dir_path_printed_to_stdout(self, tmp_path: Path) -> None:
        """init prints the absolute run directory path to stdout for capture."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")
        run_dir = self._run_dir(tmp_path)
        # The runner injects run_dir as a relative path; mirror that here so
        # echo "$(pwd)/$DIR" produces the correct absolute path.
        rel_run_dir = run_dir.relative_to(tmp_path)

        result = _bash(_init_script(str(plan), str(rel_run_dir)), tmp_path)

        assert result.returncode == 0
        output = Path(result.stdout.strip())
        assert output.is_absolute()
        assert output.exists()

    def test_multiline_content_preserved(self, tmp_path: Path) -> None:
        """Multi-section plan content with code blocks is preserved exactly."""
        content = (
            "# Implementation Plan\n\n"
            "## Phase 1\n\n"
            "- Step A\n"
            "- Step B\n\n"
            "```python\nprint('hello')\n```\n"
        )
        plan = tmp_path / "impl-plan.md"
        plan.write_text(content)
        run_dir = self._run_dir(tmp_path)

        result = _bash(_init_script(str(plan), str(run_dir)), tmp_path)

        assert result.returncode == 0
        assert (run_dir / "plan.md").read_text() == content


class TestSynthesizeState:
    """synthesize state updates plan-rubric.md task: field after rewriting plan.md."""

    @staticmethod
    def _load_yaml() -> dict:
        import yaml

        loop_path = Path(__file__).parent.parent / "little_loops" / "loops" / "rn-refine.yaml"
        return yaml.safe_load(loop_path.read_text())

    def test_synthesize_action_references_plan_rubric(self) -> None:
        """synthesize action must reference plan-rubric.md for the task: field update."""
        data = self._load_yaml()
        action = data["states"]["synthesize"]["action"]
        assert "plan-rubric.md" in action

    def test_synthesize_action_references_task_field(self) -> None:
        """synthesize action must instruct updating the task: field."""
        data = self._load_yaml()
        action = data["states"]["synthesize"]["action"]
        assert "task:" in action

    def test_synthesize_action_preserves_dimensions(self) -> None:
        """synthesize action must explicitly preserve ## Dimensions scores."""
        data = self._load_yaml()
        action = data["states"]["synthesize"]["action"]
        assert "## Dimensions" in action or "Dimensions" in action

    def test_synthesize_action_preserves_aggregate(self) -> None:
        """synthesize action must explicitly preserve the ## Aggregate section."""
        data = self._load_yaml()
        action = data["states"]["synthesize"]["action"]
        assert "## Aggregate" in action or "Aggregate" in action


class TestRoutingStructure:
    """Routing fix: report state fires before done so terminal action is not skipped."""

    @staticmethod
    def _load_rn_refine():
        loop_path = Path(__file__).parent.parent / "little_loops" / "loops" / "rn-refine.yaml"
        fsm, _ = load_and_validate(loop_path)
        return fsm

    def test_score_routes_to_verify_score_on_yes(self) -> None:
        """score.on_yes routes to verify_score for file-content confirmation before report."""
        fsm = self._load_rn_refine()
        assert fsm.states["score"].on_yes == "verify_score"

    def test_verify_score_routes_to_report_on_yes(self) -> None:
        """verify_score.on_yes must point to report after rubric file confirms ALL_VERY_HIGH."""
        fsm = self._load_rn_refine()
        assert fsm.states["verify_score"].on_yes == "report"

    def test_verify_score_routes_to_classify_research_on_no(self) -> None:
        """verify_score.on_no returns to classify_research when rubric file has ITERATE."""
        fsm = self._load_rn_refine()
        assert fsm.states["verify_score"].on_no == "classify_research"

    def test_report_state_exists(self) -> None:
        """report state must be present in the loop."""
        fsm = self._load_rn_refine()
        assert "report" in fsm.states

    def test_report_action_type_is_prompt(self) -> None:
        """report.action_type must be prompt so the runner executes it."""
        fsm = self._load_rn_refine()
        assert fsm.states["report"].action_type == "prompt"

    def test_report_routes_to_done(self) -> None:
        """report.next must point to done."""
        fsm = self._load_rn_refine()
        assert fsm.states["report"].next == "done"

    def test_done_has_no_action(self) -> None:
        """done must be a bare terminal with no action so it is a clean exit anchor."""
        fsm = self._load_rn_refine()
        assert getattr(fsm.states["done"], "action", None) is None

    def test_done_is_terminal(self) -> None:
        """done.terminal must be True."""
        fsm = self._load_rn_refine()
        assert fsm.states["done"].terminal is True


class TestDiagnoseRouting:
    """Diagnose state exists and all on_error transitions route to it instead of failed."""

    @staticmethod
    def _load_rn_refine():
        loop_path = Path(__file__).parent.parent / "little_loops" / "loops" / "rn-refine.yaml"
        fsm, _ = load_and_validate(loop_path)
        return fsm

    def test_init_on_error_routes_to_diagnose(self) -> None:
        fsm = self._load_rn_refine()
        assert fsm.states["init"].on_error == "diagnose"

    def test_score_on_error_routes_to_diagnose(self) -> None:
        fsm = self._load_rn_refine()
        assert fsm.states["score"].on_error == "diagnose"

    def test_verify_score_on_error_routes_to_diagnose(self) -> None:
        fsm = self._load_rn_refine()
        assert fsm.states["verify_score"].on_error == "diagnose"

    def test_diagnose_state_exists(self) -> None:
        fsm = self._load_rn_refine()
        assert "diagnose" in fsm.states

    def test_diagnose_action_type_is_prompt(self) -> None:
        fsm = self._load_rn_refine()
        assert fsm.states["diagnose"].action_type == "prompt"

    def test_diagnose_routes_to_failed(self) -> None:
        fsm = self._load_rn_refine()
        assert fsm.states["diagnose"].next == "failed"
