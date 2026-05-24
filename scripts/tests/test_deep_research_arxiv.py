"""Tests for the deep-research-arxiv built-in FSM loop (FEAT-1673)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.evaluators import evaluate_output_contains
from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "deep-research-arxiv.yaml"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


class TestDeepResearchArxivYaml:
    """Validate the deep-research-arxiv YAML parses and passes FSM validation."""

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
        assert data.get("description"), "deep-research-arxiv must have a non-empty description"

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "deep-research-arxiv"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "topic"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {
            "init",
            "generate_queries",
            "search_web",
            "evaluate_sources",
            "score_coverage",
            "plan_next",
            "synthesize",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing required states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        state = data["states"]["init"]
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "generate_queries"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, "init.action must use $(pwd) for an absolute path"

    def test_init_touches_all_artifact_files(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        for artifact in ("report.md", "knowledge-base.md", "coverage.md", "query-log.md"):
            assert artifact in action, f"init.action must touch {artifact}"

    def test_coverage_state_uses_sentinel(self, data: dict) -> None:
        state = data["states"]["score_coverage"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "COVERAGE_SUFFICIENT"
        assert state.get("on_yes") == "synthesize"
        assert state.get("on_no") == "plan_next"
        assert state.get("on_error") == "synthesize"

    def test_plan_next_loops_back_to_search_web(self, data: dict) -> None:
        state = data["states"]["plan_next"]
        assert state.get("next") == "search_web"

    def test_terminal_done_state(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True

    def test_context_has_topic_and_output_dir(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert "topic" in ctx
        assert "output_dir" in ctx
        assert ctx["output_dir"] == ".loops/research"

    def test_context_has_depth_and_coverage_threshold(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert "depth" in ctx
        assert "coverage_threshold_pct" in ctx

    def test_max_iterations_is_30(self, data: dict) -> None:
        assert data.get("max_iterations") == 30

    def test_timeout_is_3600(self, data: dict) -> None:
        assert data.get("timeout") == 3600

    def test_category_is_research(self, data: dict) -> None:
        assert data.get("category") == "research"

    def test_score_coverage_has_on_error(self, data: dict) -> None:
        state = data["states"]["score_coverage"]
        assert "on_error" in state, "score_coverage must have on_error for graceful degradation"

    def test_search_web_constrains_to_arxiv(self, data: dict) -> None:
        """search_web prompt must instruct the LLM to constrain queries with site:arxiv.org."""
        action = data["states"]["search_web"].get("action", "")
        assert "site:arxiv.org" in action, (
            "search_web must constrain queries to site:arxiv.org for arxiv-only research"
        )

    def test_evaluate_sources_uses_recency_not_credibility(self, data: dict) -> None:
        """evaluate_sources must score on recency (not credibility) per FEAT-1673."""
        action = data["states"]["evaluate_sources"].get("action", "")
        assert "recency" in action.lower(), (
            "evaluate_sources must score sources on recency for arxiv preprints"
        )
        # Credibility flattens on arxiv (everything is academic) — it must be dropped.
        # Use a word-boundary-style check to avoid false positives if "credibility"
        # appears as part of a different phrase. The original parent loop uses the
        # exact tokens 'credibility (1–5)' and 'credibility: N/5'.
        assert "credibility:" not in action.lower(), (
            "evaluate_sources must not annotate with credibility: — use recency: instead"
        )
        assert "credibility (1" not in action.lower(), (
            "evaluate_sources must not score credibility (1-5) — use recency (1-5) instead"
        )

    def test_evaluate_sources_emits_arxiv_id_annotation(self, data: dict) -> None:
        """evaluate_sources annotation format must include arxiv-id for dedup."""
        action = data["states"]["evaluate_sources"].get("action", "")
        assert "arxiv-id" in action.lower(), (
            "evaluate_sources annotation must include arxiv-id field"
        )

    def test_synthesize_sources_table_has_arxiv_columns(self, data: dict) -> None:
        """synthesize sources table must use arXiv ID columns, not the generic URL table."""
        action = data["states"]["synthesize"].get("action", "")
        for column in ("arXiv ID", "Title", "Authors", "Year", "Relevance", "Recency", "Facet"):
            assert column in action, f"synthesize sources table missing column: {column}"

    def test_synthesize_emits_bibtex_section(self, data: dict) -> None:
        """synthesize must instruct the LLM to emit a ## BibTeX section with @misc{...} entries."""
        action = data["states"]["synthesize"].get("action", "")
        assert "## BibTeX" in action, "synthesize must emit a ## BibTeX section"
        assert "@misc" in action, "synthesize BibTeX section must use @misc{...} entries"


class TestDeepResearchArxivShellStates:
    """Exercise the init shell action directly to verify slug and directory creation."""

    def test_init_creates_run_directory(self, tmp_path: Path) -> None:
        """init action creates the output directory and all four artifact files."""
        topic = "speculative decoding for LLM inference"
        script = f"""
SLUG=$(echo "{topic}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
SLUG="${{SLUG:-deep-research-arxiv-run}}"
DIR=".loops/research/$SLUG"
mkdir -p "$DIR"
: > "$DIR/report.md"
: > "$DIR/knowledge-base.md"
: > "$DIR/coverage.md"
: > "$DIR/query-log.md"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0, f"init shell failed: {result.stderr}"
        run_dir = result.stdout.strip()
        assert run_dir, "init must output the run directory path"

        run_path = Path(run_dir)
        assert run_path.is_dir(), f"Run directory not created: {run_path}"
        assert (run_path / "report.md").exists(), "report.md not created"
        assert (run_path / "knowledge-base.md").exists(), "knowledge-base.md not created"
        assert (run_path / "coverage.md").exists(), "coverage.md not created"
        assert (run_path / "query-log.md").exists(), "query-log.md not created"

    def test_init_slug_is_lowercase_hyphenated(self, tmp_path: Path) -> None:
        """init action produces a lowercase, hyphenated slug from the topic."""
        topic = "Speculative Decoding for LLM Inference"
        script = f"""
SLUG=$(echo "{topic}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
echo "$SLUG"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        slug = result.stdout.strip()
        assert slug == "speculative-decoding-for-llm-inference"

    def test_init_outputs_absolute_path(self, tmp_path: Path) -> None:
        """init action echoes an absolute path (starts with /)."""
        topic = "deep research arxiv test topic"
        script = f"""
SLUG=$(echo "{topic}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
DIR=".loops/research/$SLUG"
mkdir -p "$DIR"
echo "$(pwd)/$DIR"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        path = result.stdout.strip()
        assert path.startswith("/"), f"init must output absolute path, got: {path!r}"

    def test_init_empty_topic_uses_fallback_slug(self, tmp_path: Path) -> None:
        """init action falls back to 'deep-research-arxiv-run' when topic produces empty slug."""
        script = """
SLUG=$(echo "" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-\\+/-/g; s/^-//; s/-$//')
SLUG="${SLUG:-deep-research-arxiv-run}"
echo "$SLUG"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        slug = result.stdout.strip()
        assert slug == "deep-research-arxiv-run"


class TestDeepResearchArxivEvaluators:
    """Unit-test the convergence evaluator without subprocess."""

    def test_coverage_sentinel_matches(self) -> None:
        """COVERAGE_SUFFICIENT → yes; NEED_MORE → no."""
        data = yaml.safe_load(LOOP_FILE.read_text())
        pattern = data["states"]["score_coverage"]["evaluate"]["pattern"]

        assert evaluate_output_contains("COVERAGE_SUFFICIENT\n", pattern).verdict == "yes"
        assert evaluate_output_contains("NEED_MORE\n", pattern).verdict == "no"
        assert (
            evaluate_output_contains(
                "Average coverage: 4.2/5\nCOVERAGE_SUFFICIENT", pattern
            ).verdict
            == "yes"
        )
        assert evaluate_output_contains("", pattern).verdict == "no"


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
