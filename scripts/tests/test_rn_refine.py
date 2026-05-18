"""Tests for the rn-refine loop init state shell logic and routing structure.

Validates slug derivation, file-not-found error handling, the cp-based
content preservation that distinguishes rn-refine from rn-plan's blank init,
and the routing fix that ensures the report state fires before done.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from little_loops.fsm.validation import load_and_validate


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


# Shell body of the rn-refine init state, parametrized by plan_file and output_dir.
def _init_script(plan_file: str, output_dir: str = ".loops/plans") -> str:
    return f"""
    if [ ! -f "{plan_file}" ]; then
      echo "ERROR: Plan file not found: {plan_file}"
      exit 1
    fi
    SLUG=$(basename "{plan_file}" .md | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
    SLUG="${{SLUG:-rn-refine-run}}"
    DIR="{output_dir}/$SLUG"
    mkdir -p "$DIR"
    cp "{plan_file}" "$DIR/plan.md"
    : > "$DIR/plan-rubric.md"
    : > "$DIR/research.md"
    echo "$(pwd)/$DIR"
    """


class TestInitSlugDerivation:
    """init derives a lowercase hyphenated slug from the plan filename stem."""

    def test_simple_lowercase_filename(self, tmp_path: Path) -> None:
        """Simple lowercase filename produces expected slug."""
        plan = tmp_path / "my-feature-plan.md"
        plan.write_text("# My Feature Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert run_dir.name == "my-feature-plan"

    def test_uppercase_stem_lowercased(self, tmp_path: Path) -> None:
        """Uppercase characters in the filename stem are lowercased in the slug."""
        plan = tmp_path / "MyPlan.md"
        plan.write_text("# My Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert run_dir.name == "myplan"

    def test_spaces_become_hyphens(self, tmp_path: Path) -> None:
        """Non-alphanumeric chars (spaces, underscores) are replaced with hyphens."""
        plan = tmp_path / "my_feature_plan.md"
        plan.write_text("# Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert run_dir.name == "my-feature-plan"

    def test_consecutive_hyphens_collapsed(self, tmp_path: Path) -> None:
        """Multiple consecutive non-alphanumeric chars collapse to a single hyphen."""
        plan = tmp_path / "my--plan.md"
        plan.write_text("# Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert run_dir.name == "my-plan"

    def test_leading_trailing_hyphens_stripped(self, tmp_path: Path) -> None:
        """Leading and trailing hyphens in the slug are stripped."""
        plan = tmp_path / "-plan-.md"
        plan.write_text("# Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert not run_dir.name.startswith("-")
        assert not run_dir.name.endswith("-")


class TestInitFileNotFound:
    """init exits non-zero with an error message when plan_file does not exist."""

    def test_missing_file_exits_nonzero(self, tmp_path: Path) -> None:
        """Non-existent plan_file path causes exit code 1."""
        result = _bash(_init_script("nonexistent/plan.md"), tmp_path)

        assert result.returncode != 0

    def test_missing_file_error_message_on_stdout(self, tmp_path: Path) -> None:
        """Error message is emitted to stdout when plan_file is missing."""
        result = _bash(_init_script("nonexistent/plan.md"), tmp_path)

        assert "ERROR" in result.stdout or "ERROR" in result.stderr

    def test_no_run_dir_created_when_file_missing(self, tmp_path: Path) -> None:
        """No .loops/plans directory is created when plan_file does not exist."""
        _bash(_init_script("nonexistent/plan.md"), tmp_path)

        assert not (tmp_path / ".loops" / "plans").exists()


class TestInitFileCopy:
    """init copies source plan content into the run directory rather than blank-initializing."""

    def test_source_content_preserved_in_run_dir(self, tmp_path: Path) -> None:
        """Content of the source plan file is copied verbatim to $DIR/plan.md."""
        content = "# Existing Plan\n\nThis is my plan content.\n"
        plan = tmp_path / "existing-plan.md"
        plan.write_text(content)

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        copied = (run_dir / "plan.md").read_text()
        assert copied == content

    def test_plan_rubric_initialized_empty(self, tmp_path: Path) -> None:
        """plan-rubric.md is created as an empty file in the run directory."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert (run_dir / "plan-rubric.md").exists()
        assert (run_dir / "plan-rubric.md").read_text() == ""

    def test_research_md_initialized_empty(self, tmp_path: Path) -> None:
        """research.md is created as an empty file in the run directory."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert (run_dir / "research.md").exists()
        assert (run_dir / "research.md").read_text() == ""

    def test_run_dir_path_printed_to_stdout(self, tmp_path: Path) -> None:
        """init prints the absolute run directory path to stdout for capture."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert run_dir.is_absolute()
        assert run_dir.exists()

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

        result = _bash(_init_script(str(plan)), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert (run_dir / "plan.md").read_text() == content


class TestRoutingStructure:
    """Routing fix: report state fires before done so terminal action is not skipped."""

    @staticmethod
    def _load_rn_refine():
        loop_path = Path(__file__).parent.parent / "little_loops" / "loops" / "rn-refine.yaml"
        fsm, _ = load_and_validate(loop_path)
        return fsm

    def test_score_routes_to_report_on_yes(self) -> None:
        """score.on_yes must point to report, not done."""
        fsm = self._load_rn_refine()
        assert fsm.states["score"].on_yes == "report"

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


class TestInitOutputDir:
    """init respects a custom output_dir context variable."""

    def test_custom_output_dir_used(self, tmp_path: Path) -> None:
        """Run directory is created under the custom output_dir."""
        plan = tmp_path / "my-plan.md"
        plan.write_text("# Plan\n")
        custom_dir = ".custom/output"

        result = _bash(_init_script(str(plan), output_dir=custom_dir), tmp_path)

        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        assert f"/{custom_dir}/" in str(run_dir)
