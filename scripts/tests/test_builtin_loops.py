"""Tests for built-in loops shipped with the plugin."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_generator_fix_discipline,
    _validate_partial_route_dead_end,
    load_and_validate,
    validate_fsm,
)

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


class TestBuiltinLoopFiles:
    """Tests that all built-in loop YAML files are valid."""

    @pytest.fixture
    def builtin_loops(self) -> list[Path]:
        """Get all built-in loop files including oracle sub-loops."""
        assert BUILTIN_LOOPS_DIR.exists(), f"Built-in loops dir not found: {BUILTIN_LOOPS_DIR}"
        files = sorted(p for p in BUILTIN_LOOPS_DIR.rglob("*.yaml") if is_runnable_loop(p))
        assert len(files) > 0, "No built-in loop files found"
        return files

    def test_all_parse_as_yaml(self, builtin_loops: list[Path]) -> None:
        """All built-in loop files parse as valid YAML."""
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), f"{loop_file.name}: root must be a mapping"

    def test_all_validate_as_valid_fsm(self, builtin_loops: list[Path]) -> None:
        """All built-in loops load and validate as FSMs without errors."""
        for loop_file in builtin_loops:
            fsm, _ = load_and_validate(loop_file)
            errors = validate_fsm(fsm)
            error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
            assert not error_list, (
                f"{loop_file.name}: validation errors: {[str(e) for e in error_list]}"
            )

    def test_all_have_description_field(self, builtin_loops: list[Path]) -> None:
        """All built-in loops define a top-level description: field.

        Regression guard for ENH-1331: debug-loop-run and audit-loop-run skills
        require a machine-readable description for goal-alignment assessment.
        """
        for loop_file in builtin_loops:
            fsm, warnings = load_and_validate(loop_file)
            assert fsm.description, f"{loop_file.name}: missing top-level 'description:' field"
            description_warnings = [
                w
                for w in warnings
                if w.severity == ValidationSeverity.WARNING
                and "No 'description' field" in w.message
            ]
            assert not description_warnings, (
                f"{loop_file.name}: produced description warning: "
                f"{[str(w) for w in description_warnings]}"
            )

    def test_expected_loops_exist(self) -> None:
        """The expected set of built-in loops exists."""
        expected = {
            "dead-code-cleanup",
            "docs-sync",
            "evaluation-quality",
            "fix-quality-and-tests",
            "issue-discovery-triage",
            "issue-refinement",
            "issue-staleness-review",
            "learning-tests-audit",
            "backlog-flow-optimizer",
            "sprint-build-and-validate",
            "worktree-health",
            "rl-bandit",
            "rl-rlhf",
            "rl-policy",
            "rl-coding-agent",
            "apo-feedback-refinement",
            "apo-contrastive",
            "apo-opro",
            "apo-beam",
            "apo-textgrad",
            "examples-miner",
            "context-health-monitor",
            "harness-single-shot",
            "harness-multi-item",
            "harness-plan-research-implement-report",
            "harness-optimize",
            "general-task",
            "refine-to-ready-issue",
            "agent-eval-improve",
            "dataset-curation",
            "incremental-refactor",
            "prompt-across-issues",
            "prompt-regression-test",
            "test-coverage-improvement",
            "eval-driven-development",
            "outer-loop-eval",
            "generative-art",
            "p5js-sketch-generator",
            "pixi-data-viz",
            "pixi-generative-art",
            "auto-refine-and-implement",
            "autodev",
            "scan-and-implement",
            "sft-corpus",
            "recursive-refine",
            "html-anything",
            "html-website-generator",
            "sprint-refine-and-implement",
            "svg-image-generator",
            "svg-textgrad",
            "rn-plan",
            "rn-plan-apo",
            "rn-implement",
            "rn-decompose",
            "rn-remediate",
            "rn-refine",
            "loop-specialist-eval",
            "hitl-compare",
            "hitl-md",
            "deep-research",
            "deep-research-arxiv",
            "loop-router",
            "ready-to-implement-gate",
            "assumption-firewall",
            "adopt-third-party-api",
            "integrate-sdk",
            "proof-first-task",
            "cli-anything-bootstrap",
            "adversarial-redesign",
            "migrate-sdk-version",
            "loop-composer",
            "loop-composer-adaptive",
            "goal-cluster",
            "rn-build",
            "vega-viz",
            "canvas-sketch-generator",
            "apply-research",
            "rlhf-animated-svg",
            "rlhf-svg-evaluate",
            "rlhf-svg-refine",
            "rlhf-svg-generate",
            "cua-agent-desktop",
            "rubric-refine",
            "policy-refine",
            "brainstorm",
            "openscad-model-generator",
            "interactive-component-generator",
        }
        actual = {f.stem for f in BUILTIN_LOOPS_DIR.glob("*.yaml")}
        assert expected == actual

    def test_no_bare_pass_token_in_output_contains(self, builtin_loops: list[Path]) -> None:
        """No built-in loop uses bare 'PASS' as an output_contains pattern.

        Bare 'PASS' collides with per-criterion scoring annotations
        (e.g. 'design_quality: 8/10 — PASS') in free-form LLM output.
        Use compound tokens like 'ALL_PASS' or 'CONVERGED' instead.
        """
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                data = yaml.safe_load(f)
            for state_name, state in (data.get("states") or {}).items():
                evaluate = state.get("evaluate") or {}
                if evaluate.get("type") == "output_contains":
                    pattern = evaluate.get("pattern")
                    assert pattern != "PASS", (
                        f"{loop_file.name}/{state_name} uses ambiguous 'PASS' token — "
                        "scoring output annotations will match substring. "
                        "Use a compound token (e.g. 'ALL_PASS')."
                    )

    def test_no_bare_bash_variable_in_shell_actions(self, builtin_loops: list[Path]) -> None:
        """No built-in loop shell action uses unescaped ${...} bash expansions.

        Any unescaped ${...} is intercepted by the FSM template engine and resolved as
        a ${namespace.path} reference before bash ever sees it. Bare ${VAR} (BUG-1675)
        and bash parameter expansions like ${FILE##*.}, ${FILE%.pdf}.md, ${VAR:-default}
        all raise InterpolationError ("Unknown namespace: ...") at runtime. Use $${...}
        to pass the literal through to the shell.

        Regression guard for BUG-1675 and the apply-research ${FILE##*.} failure.
        """
        import re

        # Valid FSM namespaces resolvable by the interpolation engine
        # (interpolation.py:84-110). Anything else inside an unescaped ${...} is a
        # bash construct that must be escaped as $${...}.
        valid_namespaces = {
            "context",
            "captured",
            "prev",
            "result",
            "state",
            "loop",
            "env",
            "messages",
            "param",
        }
        # Match unescaped ${...} (negative lookbehind for the $$ escape prefix).
        var_pattern = re.compile(r"(?<!\$)\$\{([^}]*)\}")
        # Leading identifier inside the braces — the candidate namespace token, i.e.
        # the part before the first separator/operator (. : # % / etc.).
        ns_token_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*")
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                data = yaml.safe_load(f)
            for state_name, state in (data.get("states") or {}).items():
                if state.get("action_type") != "shell":
                    continue
                action = state.get("action", "")
                bad: list[str] = []
                for inner in var_pattern.findall(action):
                    token_match = ns_token_pattern.match(inner)
                    namespace = token_match.group(0) if token_match else ""
                    if namespace not in valid_namespaces:
                        bad.append("${" + inner + "}")
                assert not bad, (
                    f"{loop_file.name}/{state_name} contains unescaped bash expansion(s) "
                    f"{bad} — these collide with the FSM template engine (resolved as "
                    "${namespace.path}). Use $${{...}} to pass them through to the shell "
                    "(BUG-1675)."
                )
                # Secondary pass: catch ${valid_namespace.path:-default} patterns that
                # pass the namespace check above but still cause InterpolationError because
                # the interpolator resolves 'path:-default' as a literal context key.
                # Use ${context.key:default=val} or $${VAR:-default} instead. BUG-2346.
                bash_default_pattern = re.compile(
                    r"(?<!\$)\$\{(?:" + "|".join(sorted(valid_namespaces)) + r")\.[^}]*:-[^}]*\}"
                )
                bad_defaults = bash_default_pattern.findall(action)
                assert not bad_defaults, (
                    f"{loop_file.name}/{state_name} contains bash ':-' default operator(s) "
                    f"{bad_defaults} inside FSM namespace references — raises InterpolationError "
                    "(BUG-2346). Use ${namespace.key:default=val} or $${VAR:-default} instead."
                )

    def test_all_failure_terminals_have_diagnostic_action(self, builtin_loops: list[Path]) -> None:
        """Loops with a diagnose state must have a diagnostic action before failure terminals.

        Regression guard for BUG-1606: all fixed loops must have a pre-terminal diagnose
        state that executes a prompt action before transitioning to a failure terminal.
        Loops without a diagnose state are skipped (not yet updated).
        """
        asserted = 0  # count loops that actually exercise the diagnose assertion
        for loop_file in builtin_loops:
            with open(loop_file) as f:
                data = yaml.safe_load(f)
            states = data.get("states", {})
            failure_terminals = {
                name
                for name, cfg in states.items()
                if cfg.get("terminal") and name in ("failed", "error", "aborted")
            }
            if not failure_terminals:
                continue
            diagnose = states.get("diagnose") or states.get("diagnose_failure")
            if diagnose is None:
                continue  # Loop not yet updated with diagnose state (pending BUG-1606)
            # Accept either an inline action: or a fragment: reference (which carries the action)
            assert diagnose.get("action") or diagnose.get("fragment"), (
                f"{loop_file.name}: 'diagnose' state exists but has no diagnostic action or fragment"
            )
            assert not diagnose.get("terminal", False), (
                f"{loop_file.name}: 'diagnose' state must not be terminal"
            )
            asserted += 1
        # Vacuous-pass guard: if no loop exercises the assertion above, the per-loop
        # `continue` branches would let this regression guard pass having checked nothing.
        # Require at least one updated loop so a refactor that strips every diagnose state
        # fails here instead of silently going green (BUG-1606).
        assert asserted > 0, (
            "No built-in loop exercised the diagnose-before-failure-terminal assertion; "
            "the BUG-1606 regression guard is vacuous (all diagnose states removed?)."
        )


class TestMR6BuiltinFalsePositives:
    """MR-6 (ENH-2079): verify no false positives on known built-in loops."""

    def test_harness_optimize_no_mr6_warnings(self) -> None:
        """harness-optimize.yaml produces no unexpected MR-6 warnings.

        harness-optimize uses both yaml_state_editor (LLM-type) and shell states, but
        they should not write to overlapping file paths. This is a regression guard.
        """
        loop_file = BUILTIN_LOOPS_DIR / "harness-optimize.yaml"
        assert loop_file.exists(), f"harness-optimize.yaml not found at {loop_file}"
        fsm, _ = load_and_validate(loop_file)
        errors = _validate_generator_fix_discipline(fsm)
        assert errors == [], (
            f"harness-optimize.yaml produced unexpected MR-6 warnings: "
            f"{[e.message for e in errors]}"
        )


class TestMR4BuiltinFalsePositives:
    """MR-4 (ENH-1917): verify no false positives on known built-in loops."""

    def test_generator_evaluator_no_mr4_warnings(self) -> None:
        """generator-evaluator oracle has no MR-4 partial-route dead-end warnings.

        The generate state's fix (yes/no/partial → evaluate) must pass clean —
        the loop is the root-cause origin of ENH-1917, so this is a regression guard.
        test_all_validate_as_valid_fsm only checks ERROR severity; this test asserts
        no MR-4 WARNINGs specifically.
        """
        loop_file = BUILTIN_LOOPS_DIR / "oracles" / "generator-evaluator.yaml"
        assert loop_file.exists(), f"generator-evaluator.yaml not found at {loop_file}"
        fsm, _ = load_and_validate(loop_file)
        errors = _validate_partial_route_dead_end(fsm)
        assert errors == [], (
            f"generator-evaluator.yaml produced unexpected MR-4 warnings: "
            f"{[e.message for e in errors]}"
        )


class TestBuiltinLoopResolution:
    """Tests for resolve_loop_path with built-in fallback."""

    def test_builtin_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """resolve_loop_path falls back to built-in loops."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "fix-quality-and-tests"]):
            from little_loops.cli import main_loop

            result = main_loop()
        # Should succeed because fix-quality-and-tests is a built-in
        assert result == 0

    def test_project_overrides_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Project-local loop takes priority over built-in."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Create a project-local loop with the same name but different content
        (loops_dir / "fix-quality-and-tests.yaml").write_text(
            "name: fix-quality-and-tests\ninitial: start\nstates:\n  start:\n    terminal: true\n"
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "fix-quality-and-tests"]):
            from little_loops.cli import main_loop

            result = main_loop()
        # Should use the project-local version (which is a simple terminal FSM)
        assert result == 0


class TestBuiltinLoopList:
    """Tests for ll-loop list with built-in loops."""

    def test_list_shows_builtin_tag(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-loop list shows [built-in] tag for bundled loops."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
        assert "[built-in]" in captured.out
        assert "fix-quality-and-tests" in captured.out

    def test_list_hides_overridden_builtin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Project loop with same name hides built-in from list."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "fix-quality-and-tests.yaml").write_text(
            "name: fix-quality-and-tests\ninitial: start\nstates:\n  start:\n    terminal: true\n"
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        # fix-quality-and-tests should appear without [built-in] tag (project version)
        pr_lines = [line for line in lines if "fix-quality-and-tests" in line]
        assert len(pr_lines) == 1
        assert "[built-in]" not in pr_lines[0]


class TestBuiltinLoopInstall:
    """Tests for ll-loop install subcommand."""

    def test_install_copies_to_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """install copies built-in loop to .loops/."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "fix-quality-and-tests"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        dest = tmp_path / ".loops" / "fix-quality-and-tests.yaml"
        assert dest.exists()
        captured = capsys.readouterr()
        assert "Installed" in captured.out

    def test_install_creates_loops_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install creates .loops/ directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".loops").exists()
        with patch.object(sys, "argv", ["ll-loop", "install", "issue-refinement"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        assert (tmp_path / ".loops" / "issue-refinement.yaml").exists()

    def test_install_rejects_existing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install refuses to overwrite existing project loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "fix-quality-and-tests.yaml").write_text("existing content")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "fix-quality-and-tests"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 1

    def test_install_rejects_unknown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """install rejects unknown loop name."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "install", "nonexistent-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 1


class TestBuiltinLoopScratchIsolation:
    """Tests that built-in loops use project-scoped scratch paths, not global /tmp names."""

    AFFECTED_LOOPS = [
        "issue-refinement",
        "fix-quality-and-tests",
        "dead-code-cleanup",
    ]

    # Bare /tmp paths that must not appear in any action text
    FORBIDDEN_PATTERNS = [
        "/tmp/issue-refinement-commit-count",
        "/tmp/ll-test-results.txt",
        "/tmp/ll-dead-code-report.txt",
        "/tmp/ll-dead-code-excluded.txt",
        "/tmp/ll-dead-code-tests.txt",
        "/tmp/ll-pr-test-results.txt",
    ]

    def _collect_action_text(self, data: dict) -> list[str]:
        """Recursively collect all action strings from an FSM data dict."""
        texts: list[str] = []
        for state_data in data.get("states", {}).values():
            action = state_data.get("action", "")
            if isinstance(action, str):
                texts.append(action)
        return texts

    @pytest.mark.parametrize("loop_name", AFFECTED_LOOPS)
    def test_no_global_tmp_paths(self, loop_name: str) -> None:
        """Action text in affected loops must not reference bare /tmp scratch paths."""
        loop_file = BUILTIN_LOOPS_DIR / f"{loop_name}.yaml"
        assert loop_file.exists(), f"Loop file not found: {loop_file}"
        data = yaml.safe_load(loop_file.read_text())
        action_texts = self._collect_action_text(data)
        combined = "\n".join(action_texts)
        for forbidden in self.FORBIDDEN_PATTERNS:
            # Use negative lookbehind so ".loops/tmp/foo" does not trigger a
            # false positive when checking for the bare "/tmp/foo" pattern.
            bare_pattern = r"(?<!\.loops)" + re.escape(forbidden)
            assert not re.search(bare_pattern, combined), (
                f"{loop_name}.yaml still references global tmp path: {forbidden!r}"
            )


class TestEvaluationQualityLoop:
    """Structural tests for the evaluation-quality FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "evaluation-quality.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "evaluation-quality"
        assert data.get("initial") == "sample"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "sample",
            "evaluate_code",
            "score",
            "route_action",
            "route_issues",
            "route_code",
            "remediate_issues",
            "remediate_code",
            "remediate_backlog",
            "prepare_report",
            "report",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_score_state_has_capture(self, data: dict) -> None:
        """score state must define capture: scores so route states can interpolate it."""
        score_state = data["states"].get("score", {})
        assert score_state.get("capture") == "scores"

    def test_route_states_have_on_error(self, data: dict) -> None:
        """All route/evaluate states must define on_error to prevent hangs."""
        route_states = ["route_action", "route_issues", "route_code"]
        for state_name in route_states:
            state = data["states"].get(state_name, {})
            assert "on_error" in state, f"Route state '{state_name}' missing on_error"

    def test_context_thresholds_defined(self, data: dict) -> None:
        """context block must define the three quality thresholds."""
        ctx = data.get("context", {})
        assert "issue_quality_threshold" in ctx
        assert "code_health_threshold" in ctx
        assert "backlog_health_threshold" in ctx

    def test_evaluate_code_uses_run_dir(self, data: dict) -> None:
        """evaluate_code state must use ${context.run_dir} paths, not bare /tmp/ or .loops/tmp/."""
        action = data["states"].get("evaluate_code", {}).get("action", "")
        assert "${context.run_dir}" in action, (
            "evaluate_code must use ${context.run_dir} for output files"
        )
        # Bare /tmp/... references are forbidden.
        assert not re.search(r"(?<!\.loops)/tmp/eval-", action), (
            "evaluate_code must not use bare /tmp/ paths"
        )
        # .loops/tmp/... references are forbidden after run_dir migration.
        assert ".loops/tmp/" not in action, "evaluate_code must not use shared .loops/tmp/ paths"

    def test_prepare_report_is_shell_state(self, data: dict) -> None:
        """prepare_report must be a shell state (date expansion needs shell context)."""
        state = data["states"].get("prepare_report", {})
        assert state.get("action_type") == "shell"

    def test_report_references_captured_report_path(self, data: dict) -> None:
        """report state must reference ${captured.report_path.output} for dated filename."""
        action = data["states"].get("report", {}).get("action", "")
        assert "${captured.report_path.output}" in action

    def test_score_state_emits_primary_concern(self, data: dict) -> None:
        """score state prompt must instruct output of PRIMARY_CONCERN tag."""
        action = data["states"].get("score", {}).get("action", "")
        assert "PRIMARY_CONCERN" in action

    def test_route_action_routes_on_none(self, data: dict) -> None:
        """route_action must route to prepare_report when PRIMARY_CONCERN: NONE.

        prepare_report is required in all paths (including the healthy/NONE path)
        because $(date +%Y-%m-%d) does not expand in prompt states — a shell state
        must compute the dated report path before the report prompt state runs.
        """
        state = data["states"].get("route_action", {})
        assert state.get("on_yes") == "prepare_report"
        evaluate = state.get("evaluate", {})
        assert "NONE" in evaluate.get("pattern", "")

    def test_max_steps_and_timeout(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0


class TestLearningTestsAuditLoop:
    """Structural tests for the learning-tests-audit FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "learning-tests-audit.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "learning-tests-audit"
        assert data.get("initial") == "list_records"
        assert isinstance(data.get("states"), dict)

    def test_category_is_api_adoption(self, data: dict) -> None:
        """Loop must be in the api-adoption category."""
        assert data.get("category") == "api-adoption"

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "list_records",
            "enumerate_installed",
            "classify_packages",
            "check_versions",
            "mark_stale_candidates",
            "prepare_report_path",
            "build_report",
            "done",
            "done_empty",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_done_empty_state_is_terminal(self, data: dict) -> None:
        """done_empty state must have terminal: true."""
        state = data["states"].get("done_empty", {})
        assert state.get("terminal") is True

    def test_list_records_uses_output_json(self, data: dict) -> None:
        """list_records must use output_json evaluator to gate on record count."""
        state = data["states"].get("list_records", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_json"
        assert evaluate.get("path") == "output_length"
        assert evaluate.get("operator") == "gt"
        assert evaluate.get("target") == 0

    def test_list_records_captures_records(self, data: dict) -> None:
        """list_records must capture: records for downstream states."""
        state = data["states"].get("list_records", {})
        assert state.get("capture") == "records"

    def test_enumerate_installed_uses_shell_exit_fragment(self, data: dict) -> None:
        """enumerate_installed must use shell_exit fragment."""
        state = data["states"].get("enumerate_installed", {})
        assert state.get("fragment") == "shell_exit"

    def test_classify_packages_uses_llm_gate_fragment(self, data: dict) -> None:
        """classify_packages must use llm_gate fragment."""
        state = data["states"].get("classify_packages", {})
        assert state.get("fragment") == "llm_gate"

    def test_classify_packages_has_on_partial_retry(self, data: dict) -> None:
        """classify_packages must retry on partial classification."""
        state = data["states"].get("classify_packages", {})
        assert state.get("on_partial") == "classify_packages"

    def test_check_versions_has_on_error(self, data: dict) -> None:
        """check_versions must define on_error to prevent hangs on registry errors."""
        state = data["states"].get("check_versions", {})
        assert "on_error" in state

    def test_mark_stale_candidates_has_on_error(self, data: dict) -> None:
        """mark_stale_candidates must define on_error for CLI failures."""
        state = data["states"].get("mark_stale_candidates", {})
        assert "on_error" in state

    def test_prepare_report_path_is_shell_state(self, data: dict) -> None:
        """prepare_report_path must be a shell state for date expansion."""
        state = data["states"].get("prepare_report_path", {})
        assert state.get("action_type") == "shell"

    def test_prepare_report_path_captures_report_path(self, data: dict) -> None:
        """prepare_report_path must capture: report_path for build_report."""
        state = data["states"].get("prepare_report_path", {})
        assert state.get("capture") == "report_path"

    def test_prepare_report_path_uses_run_dir(self, data: dict) -> None:
        """prepare_report_path must use ${context.run_dir} for per-run isolation."""
        action = data["states"].get("prepare_report_path", {}).get("action", "")
        assert "${context.run_dir}" in action

    def test_build_report_references_captured_report_path(self, data: dict) -> None:
        """build_report must reference ${captured.report_path.output}."""
        action = data["states"].get("build_report", {}).get("action", "")
        assert "${captured.report_path.output}" in action

    def test_build_report_uses_llm_gate_fragment(self, data: dict) -> None:
        """build_report must use llm_gate fragment."""
        state = data["states"].get("build_report", {})
        assert state.get("fragment") == "llm_gate"

    def test_context_stale_after_days_defined(self, data: dict) -> None:
        """context block must define stale_after_days."""
        ctx = data.get("context", {})
        assert "stale_after_days" in ctx

    def test_max_steps_and_timeout(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0


class TestIssueRefinementSubLoop:
    """Tests that issue-refinement.yaml is an alias for recursive-refine (ENH-2139).

    issue-refinement delegates all logic to recursive-refine with
    order=next-action, commit_every=5, no_recursion=true via a with: binding.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "issue-refinement.yaml"
    REMOVED_INLINE_STATES = [
        "evaluate",
        "parse_id",
        "run_refine_to_ready",
        "check_broke_down",
        "handle_failure",
        "check_commit",
        "commit",
        "route_format",
        "route_verify",
        "route_score",
        "format_issues",
        "score_issues",
        "refine_issues",
        "verify_only",
    ]

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_name_is_issue_refinement(self, data: dict) -> None:
        """Loop name must stay 'issue-refinement' so callers (eval-driven-development) resolve it."""
        assert data.get("name") == "issue-refinement", (
            f"name should be 'issue-refinement', got {data.get('name')!r}"
        )

    def test_run_all_delegates_to_recursive_refine(self, data: dict) -> None:
        """run_all state must call recursive-refine as a sub-loop."""
        state = data["states"].get("run_all", {})
        assert state.get("loop") == "recursive-refine", (
            f"run_all.loop should be 'recursive-refine', got {state.get('loop')!r}"
        )

    def test_with_bindings_set_order_next_action(self, data: dict) -> None:
        """with: must pass order=next-action so recursive-refine uses value-ranked backlog ordering."""
        state = data["states"].get("run_all", {})
        with_ = state.get("with_", {})
        assert with_.get("order") == "next-action", (
            f"run_all.with_.order should be 'next-action', got {with_.get('order')!r}"
        )

    def test_with_bindings_set_commit_every_5(self, data: dict) -> None:
        """with: must pass commit_every=5 to preserve the periodic commit cadence."""
        state = data["states"].get("run_all", {})
        with_ = state.get("with_", {})
        assert with_.get("commit_every") == 5, (
            f"run_all.with_.commit_every should be 5, got {with_.get('commit_every')!r}"
        )

    def test_with_bindings_set_no_recursion_true(self, data: dict) -> None:
        """with: must pass no_recursion=true to keep flat one-pass behavior matching old issue-refinement."""
        state = data["states"].get("run_all", {})
        with_ = state.get("with_", {})
        assert with_.get("no_recursion") is True, (
            f"run_all.with_.no_recursion should be true, got {with_.get('no_recursion')!r}"
        )

    def test_run_all_routes_all_outcomes_to_done(self, data: dict) -> None:
        """run_all must route on_success, on_failure, and on_error to done (alias has no fallback logic)."""
        state = data["states"].get("run_all", {})
        for field in ("on_success", "on_failure", "on_error"):
            assert state.get(field) == "done", (
                f"run_all.{field} should be 'done', got {state.get(field)!r}"
            )

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must be terminal."""
        assert data["states"].get("done", {}).get("terminal") is True, (
            "done state should be terminal: true"
        )

    @pytest.mark.parametrize("state_name", REMOVED_INLINE_STATES)
    def test_inline_refinement_states_absent(self, data: dict, state_name: str) -> None:
        """Inline refinement states must be absent — all logic delegated to recursive-refine."""
        assert state_name not in data["states"], (
            f"State '{state_name}' should be absent; issue-refinement is now an alias for recursive-refine"
        )


class TestRefineToReadyIssueSubLoop:
    """Tests that refine-to-ready-issue.yaml routes correctly through wire, breakdown, and confidence states."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "refine-to-ready-issue.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_confidence_check_delegates_to_verify_confidence_scores_oracle(
        self, data: dict
    ) -> None:
        """confidence_check must delegate score verification to the verify-confidence-scores oracle,
        routing success to check_readiness (extraction of ENH-1033 guard into reusable child loop)."""
        confidence_check = data["states"].get("confidence_check", {})
        assert confidence_check.get("loop") == "verify-confidence-scores", (
            f"confidence_check.loop should be 'verify-confidence-scores', got {confidence_check.get('loop')!r}"
        )
        assert confidence_check.get("on_success") == "check_readiness", (
            f"confidence_check.on_success should be 'check_readiness', got {confidence_check.get('on_success')!r}"
        )

    def test_confidence_check_has_on_error(self, data: dict) -> None:
        """confidence_check must define on_error so a SIGKILL'd subprocess routes to diagnose
        rather than calling request_shutdown() and cascading a full loop termination."""
        confidence_check = data["states"].get("confidence_check", {})
        assert confidence_check.get("on_error") == "diagnose", (
            f"confidence_check.on_error should be 'diagnose', got {confidence_check.get('on_error')!r}"
        )

    def test_verify_scores_persisted_on_yes_routes_to_check_readiness(self) -> None:
        """verify_scores_persisted.on_yes must route to done in the child oracle (maps to
        confidence_check.on_success → check_readiness in the parent)."""
        oracle = yaml.safe_load(
            (BUILTIN_LOOPS_DIR / "oracles" / "verify-confidence-scores.yaml").read_text()
        )
        state = oracle["states"].get("verify_scores_persisted", {})
        assert state.get("on_yes") == "done", (
            f"verify_scores_persisted.on_yes should be 'done' in child oracle, got {state.get('on_yes')!r}"
        )

    def test_verify_scores_persisted_on_no_routes_to_retry_confidence_check(self) -> None:
        """verify_scores_persisted.on_no must route to retry_confidence_check (one re-run before failing)."""
        oracle = yaml.safe_load(
            (BUILTIN_LOOPS_DIR / "oracles" / "verify-confidence-scores.yaml").read_text()
        )
        state = oracle["states"].get("verify_scores_persisted", {})
        assert state.get("on_no") == "retry_confidence_check", (
            f"verify_scores_persisted.on_no should be 'retry_confidence_check', got {state.get('on_no')!r}"
        )

    def test_check_readiness_on_yes_routes_to_check_outcome(self, data: dict) -> None:
        """check_readiness.on_yes must route to check_outcome (readiness passed → check outcome next)."""
        state = data["states"].get("check_readiness", {})
        assert state.get("on_yes") == "check_outcome", (
            f"check_readiness.on_yes should be 'check_outcome', got {state.get('on_yes')!r}"
        )

    def test_check_readiness_on_no_routes_to_check_refine_limit(self, data: dict) -> None:
        """check_readiness.on_no must route to check_refine_limit (technical gap → retry refinement)."""
        state = data["states"].get("check_readiness", {})
        assert state.get("on_no") == "check_refine_limit", (
            f"check_readiness.on_no should be 'check_refine_limit', got {state.get('on_no')!r}"
        )

    def test_check_readiness_on_error_is_check_scores_from_file(self, data: dict) -> None:
        """check_readiness.on_error must route to check_scores_from_file (preserves error fallback)."""
        state = data["states"].get("check_readiness", {})
        assert state.get("on_error") == "check_scores_from_file", (
            f"check_readiness.on_error should be 'check_scores_from_file', got {state.get('on_error')!r}"
        )

    def test_check_outcome_on_yes_routes_to_done(self, data: dict) -> None:
        """check_outcome.on_yes must route directly to done (ENH-2364: restore_best retired, additive refines are non-regressive)."""
        state = data["states"].get("check_outcome", {})
        assert state.get("on_yes") == "done", (
            f"check_outcome.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_outcome_on_no_routes_to_check_decision_needed(self, data: dict) -> None:
        """check_outcome.on_no must route to check_decision_needed (outcome fail → decision check before breakdown)."""
        state = data["states"].get("check_outcome", {})
        assert state.get("on_no") == "check_decision_needed", (
            f"check_outcome.on_no should be 'check_decision_needed', got {state.get('on_no')!r}"
        )

    def test_check_scores_from_file_state_exists(self, data: dict) -> None:
        """check_scores_from_file state must exist as the error recovery path for confidence_check."""
        assert "check_scores_from_file" in data["states"], (
            "State 'check_scores_from_file' not found in refine-to-ready-issue.yaml — "
            "required as fallback when confidence_check LLM evaluation times out"
        )

    def test_check_scores_from_file_routes_to_done(self, data: dict) -> None:
        """check_scores_from_file.on_yes must route to done when scores meet thresholds."""
        state = data["states"].get("check_scores_from_file", {})
        assert state.get("on_yes") == "done", (
            f"check_scores_from_file.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_scores_from_file_routes_to_breakdown_issue_on_no(self, data: dict) -> None:
        """check_scores_from_file.on_no must route to breakdown_issue (ENH-1033: outcome-only fails avoid retry)."""
        state = data["states"].get("check_scores_from_file", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_scores_from_file.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_verify_issue_state_absent(self, data: dict) -> None:
        """verify_issue state must not exist — it was removed in ENH-980."""
        assert "verify_issue" not in data["states"], (
            "State 'verify_issue' should have been removed; confidence_check.on_yes now routes to 'done'"
        )

    def test_check_lifetime_limit_routes_to_breakdown_issue(self, data: dict) -> None:
        """check_lifetime_limit.on_no must route to breakdown_issue (not failed)."""
        state = data["states"].get("check_lifetime_limit", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_lifetime_limit.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_breakdown_issue_state_exists(self, data: dict) -> None:
        """breakdown_issue state must exist to invoke /ll:issue-size-review on cap exhaustion."""
        assert "breakdown_issue" in data["states"], (
            "State 'breakdown_issue' not found in refine-to-ready-issue.yaml"
        )

    def test_breakdown_issue_is_slash_command(self, data: dict) -> None:
        """breakdown_issue must use action_type: slash_command."""
        state = data["states"].get("breakdown_issue", {})
        assert state.get("action_type") == "slash_command", (
            f"breakdown_issue.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )

    def test_breakdown_issue_action_contains_auto(self, data: dict) -> None:
        """breakdown_issue action must include --auto to avoid blocking on interactive input."""
        state = data["states"].get("breakdown_issue", {})
        assert "--auto" in state.get("action", ""), (
            "breakdown_issue action must include '--auto' flag to prevent interactive stalling"
        )

    def test_breakdown_issue_routes_to_write_broke_down(self, data: dict) -> None:
        """breakdown_issue.next must be 'write_broke_down' to set the flag before exiting."""
        state = data["states"].get("breakdown_issue", {})
        assert state.get("next") == "write_broke_down", (
            f"breakdown_issue.next should be 'write_broke_down', got {state.get('next')!r}"
        )

    def test_write_broke_down_state_exists(self, data: dict) -> None:
        """write_broke_down state must exist to signal to recursive-refine that breakdown ran."""
        assert "write_broke_down" in data["states"], (
            "State 'write_broke_down' not found in refine-to-ready-issue.yaml"
        )

    def test_write_broke_down_routes_to_done(self, data: dict) -> None:
        """write_broke_down.next must route to done."""
        state = data["states"].get("write_broke_down", {})
        assert state.get("next") == "done", (
            f"write_broke_down.next should be 'done', got {state.get('next')!r}"
        )

    def test_write_broke_down_action_writes_flag(self, data: dict) -> None:
        """write_broke_down action must write to the refine-broke-down flag file."""
        state = data["states"].get("write_broke_down", {})
        assert "refine-broke-down" in state.get("action", ""), (
            "write_broke_down action must write to '${context.run_dir}/refine-broke-down'"
        )

    def test_broke_down_flag_initialized_in_resolve_issue(self, data: dict) -> None:
        """resolve_issue action must initialize the refine-broke-down flag file."""
        state = data["states"].get("resolve_issue", {})
        assert "refine-broke-down" in state.get("action", ""), (
            "resolve_issue action must initialize '${context.run_dir}/refine-broke-down' flag"
        )

    def test_breakdown_issue_on_error_is_diagnose(self, data: dict) -> None:
        """breakdown_issue.on_error must route to 'diagnose', not 'failed' directly."""
        state = data["states"].get("breakdown_issue", {})
        assert state.get("on_error") == "diagnose", (
            f"breakdown_issue.on_error should be 'diagnose', got {state.get('on_error')!r}"
        )

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose state must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    def test_check_wire_done_state_exists(self, data: dict) -> None:
        """check_wire_done state must exist to gate wire_issue to once per run."""
        assert "check_wire_done" in data["states"], (
            "State 'check_wire_done' not found in refine-to-ready-issue.yaml"
        )

    def test_check_wire_done_evaluate_output_numeric_lt_1(self, data: dict) -> None:
        """check_wire_done must use output_numeric lt 1 to detect whether wire has run."""
        state = data["states"].get("check_wire_done", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_wire_done evaluate.type should be 'output_numeric', got {evaluate.get('type')!r}"
        )
        assert evaluate.get("operator") == "lt", (
            f"check_wire_done evaluate.operator should be 'lt', got {evaluate.get('operator')!r}"
        )
        assert evaluate.get("target") == 1, (
            f"check_wire_done evaluate.target should be 1, got {evaluate.get('target')!r}"
        )

    def test_wire_issue_state_exists(self, data: dict) -> None:
        """wire_issue state must exist to run /ll:wire-issue once per loop run."""
        assert "wire_issue" in data["states"], (
            "State 'wire_issue' not found in refine-to-ready-issue.yaml"
        )

    def test_wire_issue_action_contains_auto(self, data: dict) -> None:
        """wire_issue action must include --auto to avoid blocking on interactive input."""
        state = data["states"].get("wire_issue", {})
        assert "--auto" in state.get("action", ""), (
            "wire_issue action must include '--auto' flag to prevent interactive stalling"
        )

    def test_wire_issue_on_error_is_confidence_check(self, data: dict) -> None:
        """wire_issue.on_error must route to confidence_check (wiring failure is non-fatal)."""
        state = data["states"].get("wire_issue", {})
        assert state.get("on_error") == "confidence_check", (
            f"wire_issue.on_error should be 'confidence_check', got {state.get('on_error')!r}"
        )

    def test_mark_wire_done_state_exists(self, data: dict) -> None:
        """mark_wire_done state must exist to set the wire-done flag after wiring."""
        assert "mark_wire_done" in data["states"], (
            "State 'mark_wire_done' not found in refine-to-ready-issue.yaml"
        )

    def test_mark_wire_done_routes_to_confidence_check(self, data: dict) -> None:
        """mark_wire_done.next must route to confidence_check."""
        state = data["states"].get("mark_wire_done", {})
        assert state.get("next") == "confidence_check", (
            f"mark_wire_done.next should be 'confidence_check', got {state.get('next')!r}"
        )

    def test_wire_done_flag_initialized_in_resolve_issue(self, data: dict) -> None:
        """resolve_issue action must initialize the wire-done flag file."""
        state = data["states"].get("resolve_issue", {})
        assert "refine-to-ready-wire-done" in state.get("action", ""), (
            "resolve_issue action must initialize '.loops/tmp/refine-to-ready-wire-done' flag"
        )

    def test_check_refine_limit_routes_to_refine_followup(self, data: dict) -> None:
        """check_refine_limit.on_yes must route to refine_followup (additive retry, not a fresh refine_issue)."""
        state = data["states"].get("check_refine_limit", {})
        assert state.get("on_yes") == "refine_followup", (
            f"check_refine_limit.on_yes should be 'refine_followup', got {state.get('on_yes')!r}"
        )

    def test_check_refine_limit_on_no_routes_to_breakdown_issue(self, data: dict) -> None:
        """check_refine_limit.on_no must route to breakdown_issue (not failed)."""
        state = data["states"].get("check_refine_limit", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_refine_limit.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_check_missing_artifacts_state_exists(self, data: dict) -> None:
        """check_missing_artifacts state must exist to gate size-review on wiring gaps (BUG-1490)."""
        assert "check_missing_artifacts" in data["states"], (
            "State 'check_missing_artifacts' not found in refine-to-ready-issue.yaml — "
            "required to prevent size-review running on issues with missing_artifacts=true"
        )

    def test_check_missing_artifacts_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_missing_artifacts must use shell_exit fragment to route on exit code."""
        state = data["states"].get("check_missing_artifacts", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_missing_artifacts.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_missing_artifacts_on_yes_routes_to_done(self, data: dict) -> None:
        """check_missing_artifacts.on_yes (missing_artifacts=true) must exit via done so the outer loop owns wire repair."""
        state = data["states"].get("check_missing_artifacts", {})
        assert state.get("on_yes") == "done", (
            f"check_missing_artifacts.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_missing_artifacts_on_no_routes_to_breakdown_issue(self, data: dict) -> None:
        """check_missing_artifacts.on_no must route to breakdown_issue (no artifact gap → scope too large)."""
        state = data["states"].get("check_missing_artifacts", {})
        assert state.get("on_no") == "breakdown_issue", (
            f"check_missing_artifacts.on_no should be 'breakdown_issue', got {state.get('on_no')!r}"
        )

    def test_check_decision_needed_on_no_routes_to_check_missing_artifacts(
        self, data: dict
    ) -> None:
        """check_decision_needed.on_no must route to check_missing_artifacts, not breakdown_issue (BUG-1490)."""
        state = data["states"].get("check_decision_needed", {})
        assert state.get("on_no") == "check_missing_artifacts", (
            f"check_decision_needed.on_no should be 'check_missing_artifacts', got {state.get('on_no')!r}"
        )

    def test_context_fallbacks_match_selector_defaults(self, data: dict) -> None:
        """context.readiness_threshold and outcome_threshold must be 85/70 to match next-action defaults (BUG-2035)."""
        ctx = data.get("context", {})
        assert ctx.get("readiness_threshold") == 85, (
            f"context.readiness_threshold should be 85 (matches next-action fallback), "
            f"got {ctx.get('readiness_threshold')!r}"
        )
        assert ctx.get("outcome_threshold") == 70, (
            f"context.outcome_threshold should be 70 (matches next-action fallback), "
            f"got {ctx.get('outcome_threshold')!r}"
        )

    # ENH-2364: restore_best and snapshot_issue retired (additive refines are non-regressive)

    def test_restore_best_state_absent(self, data: dict) -> None:
        """restore_best state must not exist — retired by ENH-2364 (additive refines are non-regressive)."""
        assert "restore_best" not in data["states"], (
            "State 'restore_best' should have been removed; check_outcome.on_yes now routes to 'done'"
        )

    def test_snapshot_issue_state_absent(self, data: dict) -> None:
        """snapshot_issue state must not exist — retired by ENH-2364 alongside restore_best."""
        assert "snapshot_issue" not in data["states"], (
            "State 'snapshot_issue' should have been removed; iter-N/ snapshotting retired with restore_best"
        )

    def test_refine_issue_next_is_check_wire_done(self, data: dict) -> None:
        """refine_issue.next must route to check_wire_done (snapshot_issue removed by ENH-2364)."""
        state = data["states"].get("refine_issue", {})
        assert state.get("next") == "check_wire_done", (
            f"refine_issue.next should be 'check_wire_done', got {state.get('next')!r}"
        )

    def test_refine_followup_next_is_check_wire_done(self, data: dict) -> None:
        """refine_followup.next must route to check_wire_done (snapshot_issue removed by ENH-2364)."""
        state = data["states"].get("refine_followup", {})
        assert state.get("next") == "check_wire_done", (
            f"refine_followup.next should be 'check_wire_done', got {state.get('next')!r}"
        )


class TestVegaVizScoringGate:
    """Tests the phantom-convergence gate in vega-viz.yaml.

    The LLM `score` judge can self-report VERDICT: ALL_PASS while its own
    "Issues to Address" section lists blocking defects. The deterministic
    `record` state must override a claimed pass back to ITERATE when any
    [BLOCKING] item is present, so a chart the judge itself describes as
    broken cannot terminate the loop. [MINOR] items must not block.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "vega-viz.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    # --- Structural assertions -------------------------------------------

    def test_score_prompt_requires_severity_tags(self, data: dict) -> None:
        """score prompt must instruct the judge to tag issues [BLOCKING]/[MINOR]."""
        action = data["states"]["score"].get("action", "")
        assert "[BLOCKING]" in action and "[MINOR]" in action, (
            "score prompt must require severity tags on Issues to Address items"
        )

    def test_score_prompt_blocks_pass_on_blocking(self, data: dict) -> None:
        """score prompt must state that a [BLOCKING] item forces ITERATE."""
        action = data["states"]["score"].get("action", "")
        assert "zero" in action and "[BLOCKING]" in action, (
            "score prompt must tie ALL_PASS to zero [BLOCKING] items"
        )

    def test_record_action_counts_blocking_items(self, data: dict) -> None:
        """record shell must grep for [BLOCKING] and emit BLOCKING_OVERRIDE."""
        action = data["states"]["record"].get("action", "")
        assert "[BLOCKING]" in action and "BLOCKING_OVERRIDE" in action, (
            "record action must count [BLOCKING] items and override a claimed pass"
        )

    def test_record_on_yes_routes_to_done(self, data: dict) -> None:
        """record.on_yes must still route to done on a genuine EVAL_PASS."""
        assert data["states"]["record"].get("on_yes") == "done"

    def test_record_on_no_routes_to_check_stall(self, data: dict) -> None:
        """record.on_no must route to check_stall (diff-stall guard) before regenerating."""
        assert data["states"]["record"].get("on_no") == "check_stall"

    # --- Shell-execution assertions --------------------------------------

    def _run_record(self, data: dict, run_dir: Path, critique: str) -> subprocess.CompletedProcess:
        (run_dir / "critique.md").write_text(critique)
        action = data["states"]["record"].get("action", "")
        script = action.replace("${captured.run_dir.output}", str(run_dir))
        return subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)

    def test_blocking_item_overrides_claimed_pass(self, data: dict, tmp_path: Path) -> None:
        """ALL_PASS + a [BLOCKING] item → ITERATE (override), never EVAL_PASS."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        critique = (
            "# Evaluation\nfaithfulness: 9/10\nhonesty: 10/10\n"
            "effectiveness: 8/10\ncraft: 7/10\n\n"
            "## Issues to Address\n"
            "- [BLOCKING] Service Tier legend shows empty entry groups\n"
            "- [MINOR] palette could be warmer\n\n"
            "SCORE_TOTAL: 34\nVERDICT: ALL_PASS\n"
        )
        result = self._run_record(data, run_dir, critique)
        assert result.returncode == 0, f"record failed: {result.stderr}"
        assert "BLOCKING_OVERRIDE" in result.stdout, (
            f"Expected blocking override message, got: {result.stdout!r}"
        )
        # The routed token is the LAST line; record must emit ITERATE, not EVAL_PASS.
        tokens = [ln for ln in result.stdout.strip().splitlines() if ln in ("EVAL_PASS", "ITERATE")]
        assert tokens and tokens[-1] == "ITERATE", (
            f"record must route ITERATE when a [BLOCKING] item is present, got: {result.stdout!r}"
        )

    def test_minor_only_pass_terminates(self, data: dict, tmp_path: Path) -> None:
        """ALL_PASS with only [MINOR] items → EVAL_PASS (loop may terminate)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        critique = (
            "# Evaluation\n## Issues to Address\n"
            "- [MINOR] add one more annotation\n\n"
            "SCORE_TOTAL: 36\nVERDICT: ALL_PASS\n"
        )
        result = self._run_record(data, run_dir, critique)
        assert result.returncode == 0, f"record failed: {result.stderr}"
        assert "BLOCKING_OVERRIDE" not in result.stdout
        assert result.stdout.strip().splitlines()[-1] == "EVAL_PASS", (
            f"[MINOR]-only issues must not block a pass, got: {result.stdout!r}"
        )

    def test_clean_pass_terminates(self, data: dict, tmp_path: Path) -> None:
        """ALL_PASS with no issues → EVAL_PASS."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        critique = (
            "# Evaluation\n## Issues to Address\nNo issues — all criteria pass.\n\n"
            "SCORE_TOTAL: 38\nVERDICT: ALL_PASS\n"
        )
        result = self._run_record(data, run_dir, critique)
        assert result.returncode == 0, f"record failed: {result.stderr}"
        assert result.stdout.strip().splitlines()[-1] == "EVAL_PASS"

    def test_iterate_verdict_passes_through(self, data: dict, tmp_path: Path) -> None:
        """A genuine VERDICT: ITERATE must route ITERATE without an override message."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        critique = (
            "# Evaluation\n## Issues to Address\n"
            "- [BLOCKING] craft below threshold\n\n"
            "SCORE_TOTAL: 22\nVERDICT: ITERATE\n"
        )
        result = self._run_record(data, run_dir, critique)
        assert result.returncode == 0, f"record failed: {result.stderr}"
        assert "BLOCKING_OVERRIDE" not in result.stdout, (
            "override message should only fire when the judge claimed ALL_PASS"
        )
        assert result.stdout.strip().splitlines()[-1] == "ITERATE"


class TestGeneratorEvaluatorSubLoop:
    """Regression tests for oracles/generator-evaluator.yaml routing.

    Reproduces the site-generator-20260603T191934 failure: the `generate`
    prompt state previously declared only `on_yes: evaluate` + `on_error:
    failed`. A bare prompt action gets the default LLM judge, which can return
    `partial`/`no` when the agent *narrates* its work instead of asserting it.
    With no on_no/on_partial route, the verdict resolved to None → the sub-loop
    dead-ended → the parent treated it as `failed`, discarding a correct
    artifact. The real quality gate is the downstream evaluate (screenshot) →
    score (rubric) cycle, so generate must hand off to evaluate for every
    non-error verdict.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles" / "generator-evaluator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_generate_on_yes_routes_to_evaluate(self, data: dict) -> None:
        state = data["states"].get("generate", {})
        assert state.get("on_yes") == "evaluate", (
            f"generate.on_yes should be 'evaluate', got {state.get('on_yes')!r}"
        )

    def test_generate_on_no_routes_to_evaluate(self, data: dict) -> None:
        """A `no` verdict from the default judge must NOT dead-end the sub-loop."""
        state = data["states"].get("generate", {})
        assert state.get("on_no") == "evaluate", (
            "generate.on_no must route to 'evaluate' so a non-yes judge verdict "
            f"reaches the screenshot+rubric gate instead of dead-ending; got {state.get('on_no')!r}"
        )

    def test_generate_on_partial_routes_to_evaluate(self, data: dict) -> None:
        """The exact failure: `partial` verdict had no route → sub-loop → failed."""
        state = data["states"].get("generate", {})
        assert state.get("on_partial") == "evaluate", (
            "generate.on_partial must route to 'evaluate' (reproduces "
            "site-generator-20260603T191934 dead-end); got {!r}".format(state.get("on_partial"))
        )

    def test_generate_on_error_still_routes_to_failed(self, data: dict) -> None:
        """Genuine action crashes must still terminate as failed."""
        state = data["states"].get("generate", {})
        assert state.get("on_error") == "failed", (
            f"generate.on_error should remain 'failed', got {state.get('on_error')!r}"
        )


class TestHarnessCapture:
    """Tests that harness YAML files wire execute output to check_semantic via capture/source."""

    HARNESS_FILES = [
        "harness-single-shot.yaml",
        "harness-multi-item.yaml",
    ]

    @pytest.mark.parametrize("loop_name", HARNESS_FILES)
    def test_execute_state_has_capture_execute_result(self, loop_name: str) -> None:
        """execute state must define capture: execute_result so check_semantic can reference it."""
        path = BUILTIN_LOOPS_DIR / loop_name
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        execute_state = data.get("states", {}).get("execute", {})
        assert execute_state.get("capture") == "execute_result", (
            f"{loop_name}: execute state must have 'capture: execute_result' so "
            f"check_semantic can reference the skill output via ${{captured.execute_result.output}}"
        )

    @pytest.mark.parametrize("loop_name", HARNESS_FILES)
    def test_check_semantic_evaluate_has_source(self, loop_name: str) -> None:
        """check_semantic evaluate block must define source pointing to execute's captured output."""
        path = BUILTIN_LOOPS_DIR / loop_name
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        check_semantic = data.get("states", {}).get("check_semantic", {})
        evaluate = check_semantic.get("evaluate", {})
        assert evaluate.get("source") == "${captured.execute_result.output}", (
            f"{loop_name}: check_semantic.evaluate must have "
            f"'source: \"${{captured.execute_result.output}}\"' so the LLM evaluator "
            f"receives actual skill output as evidence, not the echo string"
        )

    @pytest.mark.parametrize("loop_name", HARNESS_FILES)
    def test_check_stall_uses_diff_stall_gate_fragment(self, loop_name: str) -> None:
        """check_stall state must use fragment: diff_stall_gate after ENH-1877 conversion."""
        path = BUILTIN_LOOPS_DIR / loop_name
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        check_stall = data.get("states", {}).get("check_stall", {})
        assert check_stall.get("fragment") == "diff_stall_gate", (
            f"{loop_name}: check_stall.fragment should be 'diff_stall_gate', "
            f"got {check_stall.get('fragment')!r}"
        )


class TestBuiltinLoopOnBlockedCoverage:
    """Tests that llm_structured evaluate states in built-in loops define on_blocked handlers."""

    # Each entry: (loop_file, state_name, expected_on_blocked_value)
    REQUIRED_ON_BLOCKED: list[tuple[str, str, str]] = [
        ("issue-staleness-review.yaml", "triage", "find_stale"),
    ]

    @pytest.mark.parametrize("loop_file,state_name,expected", REQUIRED_ON_BLOCKED)
    def test_llm_structured_state_has_on_blocked(
        self, loop_file: str, state_name: str, expected: str
    ) -> None:
        """Each audited llm_structured evaluate state must define on_blocked."""
        path = BUILTIN_LOOPS_DIR / loop_file
        assert path.exists(), f"Loop file not found: {path}"
        data = yaml.safe_load(path.read_text())
        state_data = data.get("states", {}).get(state_name)
        assert state_data is not None, f"State '{state_name}' not found in {loop_file}"
        assert state_data.get("evaluate", {}).get("type") == "llm_structured", (
            f"State '{state_name}' in {loop_file} is not an llm_structured evaluate state"
        )
        assert "on_blocked" in state_data, (
            f"State '{state_name}' in {loop_file} is missing on_blocked handler"
        )
        assert state_data["on_blocked"] == expected, (
            f"State '{state_name}' in {loop_file}: expected on_blocked={expected!r}, "
            f"got {state_data['on_blocked']!r}"
        )


class TestPromptAcrossIssuesLoop:
    """Structural tests for the prompt-across-issues FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "prompt-across-issues.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "prompt-across-issues"
        assert data.get("initial") == "init"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "init",
            "discover",
            "prepare_prompt",
            "execute",
            "advance",
            "done",
            "diagnose_error",
            "error",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_error_state_is_terminal(self, data: dict) -> None:
        """error state must have terminal: true."""
        error_state = data["states"].get("error", {})
        assert error_state.get("terminal") is True

    def test_discover_captures_current_item(self, data: dict) -> None:
        """discover state must capture as 'current_item'."""
        discover_state = data["states"].get("discover", {})
        assert discover_state.get("capture") == "current_item"

    def test_prepare_prompt_captures_final_prompt(self, data: dict) -> None:
        """prepare_prompt state must capture as 'final_prompt'."""
        prepare_state = data["states"].get("prepare_prompt", {})
        assert prepare_state.get("capture") == "final_prompt"

    def test_execute_uses_final_prompt(self, data: dict) -> None:
        """execute state action must reference ${captured.final_prompt.output}."""
        execute_state = data["states"].get("execute", {})
        action = execute_state.get("action", "")
        assert "${captured.final_prompt.output}" in action

    def test_advance_removes_from_pending_file(self, data: dict) -> None:
        """advance state action must modify the pending.txt file."""
        advance_state = data["states"].get("advance", {})
        action = advance_state.get("action", "")
        assert "pending" in action

    def test_advance_emits_progress_count(self, data: dict) -> None:
        """advance state action must compute REMAINING and echo a progress line."""
        advance_state = data["states"].get("advance", {})
        action = advance_state.get("action", "")
        assert "REMAINING" in action
        assert "remaining" in action

    def test_init_validates_input(self, data: dict) -> None:
        """init state action must check that ${context.input} is non-empty."""
        init_state = data["states"].get("init", {})
        action = init_state.get("action", "")
        assert "${context.input}" in action

    def test_execute_has_max_retries(self, data: dict) -> None:
        """execute state must define max_retries to prevent stuck items."""
        execute_state = data["states"].get("execute", {})
        assert execute_state.get("max_retries", 0) > 0

    def test_diagnose_error_routes_to_error(self, data: dict) -> None:
        state = data["states"].get("diagnose_error", {})
        assert state.get("next") == "error"

    def test_diagnose_error_is_not_terminal(self, data: dict) -> None:
        state = data["states"].get("diagnose_error", {})
        assert not state.get("terminal", False)

    def test_init_on_error_routes_to_diagnose_error(self, data: dict) -> None:
        state = data["states"].get("init", {})
        assert state.get("on_error") == "diagnose_error"

    def test_init_supports_type_filter(self, data: dict) -> None:
        """context.type must default to '' and init action must reference it."""
        assert data.get("context", {}).get("type") == ""
        init_action = data["states"].get("init", {}).get("action", "")
        assert "${context.type}" in init_action or "TYPE_ARG" in init_action

    def test_init_supports_parent_filter(self, data: dict) -> None:
        """context.parent must default to '' and init action must reference it."""
        assert data.get("context", {}).get("parent") == ""
        init_action = data["states"].get("init", {}).get("action", "")
        assert "${context.parent}" in init_action or "context.parent" in init_action


class TestAutoRefineAndImplementLoop:
    """Structural tests for the auto-refine-and-implement FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "auto-refine-and-implement"
        assert data.get("initial") == "init"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "init",
            "get_next_issue",
            "refine_issue",
            "implement_chain",
            "record_implemented",
            "skip_refinement",
            "record_error",
            "finalize",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_state_exists(self, data: dict) -> None:
        """init state must exist to clear temp files on each fresh run."""
        assert "init" in data["states"], "init state missing from auto-refine-and-implement"

    def test_init_state_is_shell_type(self, data: dict) -> None:
        """init state must be a shell action with unconditional next: get_next_issue."""
        init = data["states"].get("init", {})
        assert init.get("action_type") == "shell"
        assert init.get("next") == "get_next_issue"

    def test_init_clears_skip_file(self, data: dict) -> None:
        """init action must clear the skip file so each run starts fresh."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "auto-refine-and-implement-skipped.txt" in action, (
            f"init.action should clear auto-refine-and-implement-skipped.txt, got: {action!r}"
        )

    def test_init_clears_impl_queue_file(self, data: dict) -> None:
        """init action must clear the impl queue so each run starts fresh."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "auto-refine-and-implement-impl-queue.txt" in action, (
            f"init.action should clear auto-refine-and-implement-impl-queue.txt, got: {action!r}"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_get_next_issue_captures_input(self, data: dict) -> None:
        """get_next_issue must capture as 'input' for context_passthrough to work."""
        state = data["states"].get("get_next_issue", {})
        assert state.get("capture") == "input"

    def test_refine_issue_delegates_to_recursive_refine(self, data: dict) -> None:
        """refine_issue must delegate to recursive-refine with explicit input binding."""
        state = data["states"].get("refine_issue", {})
        assert state.get("loop") == "recursive-refine"
        # Migrated from context_passthrough to explicit with: binding (FEAT-1311)
        assert "input" in state.get("with", {}), (
            "refine_issue must bind 'input' via 'with:' to pass the issue ID to recursive-refine"
        )

    def test_refine_issue_has_success_and_failure_routes(self, data: dict) -> None:
        """refine_issue routes success→implement_chain, failure→skip_refinement, and
        crash (on_error)→record_error as a DISTINCT state (audit 2026-06-27): an
        infrastructure crash must not be laundered into the same skip bucket as a
        legitimate confidence-gate miss."""
        state = data["states"].get("refine_issue", {})
        assert state.get("on_success") == "implement_chain"
        assert state.get("on_failure") == "skip_refinement"
        assert state.get("on_error") == "record_error"
        assert state.get("on_failure") != state.get("on_error"), (
            "refine_issue must distinguish refinement failure from sub-loop crash"
        )

    def test_implement_chain_delegates_to_oracle(self, data: dict) -> None:
        """implement_chain must delegate to the implement-issue-chain oracle with caller_prefix."""
        state = data["states"].get("implement_chain", {})
        assert state.get("loop") == "oracles/implement-issue-chain", (
            f"implement_chain.loop should be 'oracles/implement-issue-chain', got {state.get('loop')!r}"
        )
        with_ = state.get("with", {})
        assert with_.get("caller_prefix") == "auto-refine-and-implement", (
            f"implement_chain.with.caller_prefix should be 'auto-refine-and-implement', got {with_.get('caller_prefix')!r}"
        )

    def test_skip_refinement_uses_input_capture(self, data: dict) -> None:
        """skip_refinement must reference captured.input.output (not impl_id)."""
        state = data["states"].get("skip_refinement", {})
        action = state.get("action", "")
        assert "${captured.input.output}" in action

    def test_skip_refinement_routes_to_get_next_issue(self, data: dict) -> None:
        """skip_refinement must route back to get_next_issue."""
        state = data["states"].get("skip_refinement", {})
        assert state.get("next") == "get_next_issue"

    def test_record_error_tracks_crash_separately(self, data: dict) -> None:
        """record_error must write to a distinct errored.txt so a sub-loop crash is
        not indistinguishable from a refinement skip (audit 2026-06-27)."""
        state = data["states"].get("record_error", {})
        action = state.get("action", "")
        assert "auto-refine-and-implement-errored.txt" in action
        assert state.get("next") == "get_next_issue"

    def test_finalize_writes_summary_json(self, data: dict) -> None:
        """finalize must emit a machine-readable summary.json with a verdict so
        callers and audits can distinguish success from a phantom run."""
        state = data["states"].get("finalize", {})
        action = state.get("action", "")
        assert "summary.json" in action
        assert "verdict" in action
        # ENH-2005 artifact-channel sidecar token for the parent to recover.
        assert "subloop_outcome_auto-refine-and-implement" in action

    def test_skipped_file_uses_run_dir(self, data: dict) -> None:
        """Skipped tracking file must use ${context.run_dir} path."""
        states = data.get("states", {})
        skipped_ref = "auto-refine-and-implement-skipped"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if skipped_ref in action:
                found = True
                assert "${context.run_dir}" in action
        assert found, f"No state references {skipped_ref!r}"

    def test_has_optional_scope_parameter(self, data: dict) -> None:
        """scope must be in context with empty default (optional sprint/EPIC scoping)."""
        ctx = data.get("context", {})
        assert "scope" in ctx, "context must have a 'scope' field for sprint/EPIC scoping"
        assert ctx["scope"] == "", (
            "context.scope must default to empty string (backlog poll when unset)"
        )

    def test_get_next_issue_supports_scope_branching(self, data: dict) -> None:
        """get_next_issue must branch on scope: scoped path uses load_or_resolve, backlog path uses ll-issues next-issue."""
        action = data["states"]["get_next_issue"].get("action", "")
        assert "load_or_resolve" in action, (
            "get_next_issue scoped path must use SprintManager.load_or_resolve"
        )
        assert "ll-issues next-issue" in action, (
            "get_next_issue must still use ll-issues next-issue for the default backlog path"
        )
        assert "EPIC" in action, (
            "get_next_issue scoped path must support EPIC IDs (BUG-2136 preservation)"
        )


class TestSprintRefineAndImplementLoop:
    """Structural tests for the sprint-refine-and-implement alias loop (ENH-2138)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "sprint-refine-and-implement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_is_alias_loop(self, data: dict) -> None:
        """sprint-refine-and-implement is a thin alias that delegates to auto-refine-and-implement."""
        delegate = data.get("states", {}).get("delegate", {})
        assert delegate.get("loop") == "auto-refine-and-implement", (
            "delegate state must call auto-refine-and-implement"
        )

    def test_delegate_maps_sprint_name_to_scope(self, data: dict) -> None:
        """delegate state must pass sprint_name as scope to auto-refine-and-implement."""
        delegate = data.get("states", {}).get("delegate", {})
        with_ = delegate.get("with", {})
        assert "scope" in with_, "delegate must pass 'scope' to auto-refine-and-implement"
        assert "sprint_name" in with_["scope"], (
            "delegate.with.scope must reference context.sprint_name"
        )

    def test_sprint_name_is_required_input(self, data: dict) -> None:
        """sprint_name must remain a required input for backward compatibility."""
        assert "sprint_name" in data.get("required_inputs", []), (
            "sprint_name must be in required_inputs for backward compat"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done = data.get("states", {}).get("done", {})
        assert done.get("terminal") is True

    def test_delegate_does_not_launder_subloop_verdict(self, data: dict) -> None:
        """ENH-2005 (audit 2026-06-27): delegate must NOT collapse on_success/on_failure/
        on_error into the same terminal state. on_error routes to a distinct crash state,
        and the success/failure path recovers the child's real verdict from the
        subloop_outcome_ artifact rather than silently reaching done."""
        states = data.get("states", {})
        delegate = states.get("delegate", {})
        assert delegate.get("on_error") not in (
            delegate.get("on_success"),
            delegate.get("on_failure"),
        ), "delegate.on_error must route to a distinct state, not the shared success path"
        outcome_reader = states.get(delegate.get("on_success"), {})
        assert "subloop_outcome_" in outcome_reader.get("action", ""), (
            "the delegate success/failure target must recover the child verdict "
            "from a subloop_outcome_ artifact (ENH-2005 sidecar)"
        )


class TestAutodevLoop:
    """Structural tests for the autodev FSM loop (ENH-1127: interleaved refine+implement)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "autodev.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "autodev"
        assert data.get("initial") == "init"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """Interleaved state machine must have these states; the old refine-all-then-implement-all
        intermediary states (refine_issue, seed_impl_queue, implement_next, implement_issue) must be gone."""
        required = {
            "init",
            "dequeue_next",
            "refine_current",
            "check_decision_after_refine",
            "check_passed",
            "detect_children",
            "enqueue_children",
            "size_review_snap",
            "check_broke_down",
            "recheck_scores",
            "check_decision_before_size_review",
            "triage_outcome_failure",
            "check_missing_artifacts",
            "run_size_review",
            "enqueue_or_skip",
            "recheck_after_size_review",
            "decide_current",
            "run_decide",
            "mark_decide_ran",
            "rerun_confidence_after_decide",
            "snap_and_size_review",
            "run_wire",
            "run_refine",
            "rerun_confidence_after_wire",
            "implement_current",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_old_states_removed(self, data: dict) -> None:
        """Old two-phase states must be removed in favor of the interleaved design."""
        states = set(data["states"].keys())
        forbidden = {"refine_issue", "seed_impl_queue", "implement_next", "implement_issue"}
        present = states & forbidden
        assert not present, f"Deprecated states still present: {present}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_init_references_autodev_queue(self, data: dict) -> None:
        """init must initialize autodev-queue.txt under run_dir as the unified queue."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "autodev-queue.txt" in action
        assert "${context.run_dir}" in action

    def test_init_does_not_reference_impl_queue(self, data: dict) -> None:
        """init must NOT reference the now-removed autodev-impl-queue.txt."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "autodev-impl-queue.txt" not in action, (
            "autodev-impl-queue.txt is removed in the interleaved design"
        )

    def test_no_state_references_impl_queue(self, data: dict) -> None:
        """No state anywhere should reference the deleted autodev-impl-queue.txt."""
        for name, state in data["states"].items():
            action = state.get("action", "")
            assert "autodev-impl-queue.txt" not in action, (
                f"State {name!r} still references deleted autodev-impl-queue.txt"
            )

    def test_no_state_references_recursive_refine_passed(self, data: dict) -> None:
        """autodev must write its own passed file, not read from recursive-refine's."""
        for name, state in data["states"].items():
            action = state.get("action", "")
            assert "recursive-refine-passed.txt" not in action, (
                f"State {name!r} must not read recursive-refine-passed.txt; "
                f"autodev manages its own passed list now"
            )

    def test_dequeue_next_captures_input(self, data: dict) -> None:
        """dequeue_next must capture as 'input' for context_passthrough to the sub-loop."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("capture") == "input"

    def test_dequeue_next_routes_to_refine_current(self, data: dict) -> None:
        """dequeue_next must route to refine_current on success."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("on_yes") == "refine_current"

    def test_refine_current_delegates_to_refine_to_ready_issue(self, data: dict) -> None:
        """refine_current must delegate to refine-to-ready-issue (NOT recursive-refine)."""
        state = data["states"].get("refine_current", {})
        assert state.get("loop") == "refine-to-ready-issue"
        assert state.get("context_passthrough") is True

    def test_refine_current_has_success_and_failure_routes(self, data: dict) -> None:
        """refine_current must define on_success and on_failure routes, and they must differ
        (ENH-1679: failure should not silently reuse the success path)."""
        state = data["states"].get("refine_current", {})
        assert "on_success" in state
        assert "on_failure" in state
        assert state["on_success"] != state["on_failure"], (
            "refine_current.on_success and on_failure must differ — "
            "routing both to the same state launders the sub-loop verdict (ENH-1679)"
        )

    def test_refine_current_failure_routes_to_skip_inflight(self, data: dict) -> None:
        """refine_current.on_failure must route to skip_inflight, not copy_broke_down (ENH-1679).
        A sub-loop that exits via its failed terminal (e.g. diagnose → failed) should skip
        the issue, not proceed to implement_current as if refinement succeeded."""
        state = data["states"].get("refine_current", {})
        assert state.get("on_failure") == "skip_inflight", (
            f"refine_current.on_failure should be 'skip_inflight', got {state.get('on_failure')!r}"
        )

    def test_refine_current_error_routes_to_skip_inflight(self, data: dict) -> None:
        """refine_current.on_error must route to skip_inflight (ENH-1679).
        A signal or executor crash during refinement should skip the issue."""
        state = data["states"].get("refine_current", {})
        assert state.get("on_error") == "skip_inflight", (
            f"refine_current.on_error should be 'skip_inflight', got {state.get('on_error')!r}"
        )

    def test_refine_current_on_no_routes_to_dequeue_next(self, data: dict) -> None:
        """refine_current.on_no (sub-loop queue empty / never started) must route to dequeue_next."""
        state = data["states"].get("refine_current", {})
        assert state.get("on_no") == "dequeue_next", (
            f"refine_current.on_no should be 'dequeue_next', got {state.get('on_no')!r}"
        )

    def test_skip_inflight_state_exists(self, data: dict) -> None:
        """skip_inflight state must be declared in autodev (ENH-1679)."""
        assert "skip_inflight" in data["states"], (
            "skip_inflight state not found — add it as the on_failure/on_error target "
            "for refine_current (ENH-1679)"
        )

    def test_skip_inflight_is_shell_action(self, data: dict) -> None:
        """skip_inflight must use action_type: shell (ENH-1679)."""
        state = data["states"].get("skip_inflight", {})
        assert state.get("action_type") == "shell", (
            f"skip_inflight.action_type should be 'shell', got {state.get('action_type')!r}"
        )

    def test_skip_inflight_writes_skipped_file(self, data: dict) -> None:
        """skip_inflight must append to autodev-skipped.txt (ENH-1679)."""
        state = data["states"].get("skip_inflight", {})
        action = state.get("action", "")
        assert "autodev-skipped.txt" in action, (
            "skip_inflight must record the skipped issue ID in autodev-skipped.txt"
        )

    def test_skip_inflight_clears_autodev_inflight(self, data: dict) -> None:
        """skip_inflight must clear autodev-inflight so done does not surface a stale warning (ENH-1679)."""
        state = data["states"].get("skip_inflight", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "skip_inflight must clear autodev-inflight so BUG-1226 done-state "
            "warning is not triggered for a cleanly-skipped issue"
        )

    def test_skip_inflight_routes_to_dequeue_next(self, data: dict) -> None:
        """skip_inflight must route to dequeue_next on success and on_error (ENH-1679)."""
        state = data["states"].get("skip_inflight", {})
        assert state.get("next") == "dequeue_next", (
            f"skip_inflight.next should be 'dequeue_next', got {state.get('next')!r}"
        )
        assert state.get("on_error") == "dequeue_next", (
            f"skip_inflight.on_error should be 'dequeue_next', got {state.get('on_error')!r}"
        )

    def test_implement_current_uses_shell_exit_fragment(self, data: dict) -> None:
        """implement_current must use shell_exit fragment for exit-code-aware routing."""
        state = data["states"].get("implement_current", {})
        assert state.get("fragment") == "shell_exit"

    def test_implement_current_runs_ll_auto_only(self, data: dict) -> None:
        """implement_current must invoke ll-auto --only against the captured input."""
        state = data["states"].get("implement_current", {})
        action = state.get("action", "")
        assert "ll-auto --only" in action
        assert "${captured.input.output}" in action

    def test_implement_current_routes_back_to_dequeue_next(self, data: dict) -> None:
        """After implementing (exit 0), return to dequeue_next for the next queued issue."""
        state = data["states"].get("implement_current", {})
        assert state.get("on_yes") == "dequeue_next"

    def test_implement_current_on_no_routes_to_dequeue_next(self, data: dict) -> None:
        """On gate-blocked exit (exit 1), still advance to dequeue_next."""
        state = data["states"].get("implement_current", {})
        assert state.get("on_no") == "dequeue_next"

    def test_implement_current_on_error_routes_to_done(self, data: dict) -> None:
        """On fatal error, terminate the loop via done."""
        state = data["states"].get("implement_current", {})
        assert state.get("on_error") == "done"

    def test_copy_broke_down_routes_to_check_decision_after_refine(self, data: dict) -> None:
        """copy_broke_down must route to check_decision_after_refine so decision_needed is
        checked immediately after confidence-check (via sub-loop) completes."""
        state = data["states"].get("copy_broke_down", {})
        assert state.get("next") == "check_decision_after_refine", (
            f"copy_broke_down.next should be 'check_decision_after_refine', got {state.get('next')!r}"
        )

    def test_check_decision_after_refine_routes_correctly(self, data: dict) -> None:
        """check_decision_after_refine must route to run_decide (on_yes) and check_passed (on_no/on_error)."""
        state = data["states"].get("check_decision_after_refine", {})
        assert state.get("on_yes") == "run_decide", (
            f"check_decision_after_refine.on_yes should be 'run_decide', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "check_passed", (
            f"check_decision_after_refine.on_no should be 'check_passed', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "check_passed", (
            f"check_decision_after_refine.on_error should be 'check_passed', got {state.get('on_error')!r}"
        )

    def test_check_passed_on_yes_routes_to_implement_current(self, data: dict) -> None:
        """On threshold pass, proceed directly to implementation (decision_needed already handled
        by check_decision_after_refine before scores are evaluated)."""
        state = data["states"].get("check_passed", {})
        assert state.get("on_yes") == "implement_current"

    def test_check_passed_on_no_routes_to_triage_outcome_failure(self, data: dict) -> None:
        """On threshold fail, triage outcome before routing to size-review or decide."""
        state = data["states"].get("check_passed", {})
        assert state.get("on_no") == "triage_outcome_failure"

    def test_enqueue_children_prepends_to_autodev_queue(self, data: dict) -> None:
        """enqueue_children must rewrite .loops/tmp/autodev-queue.txt, not recursive-refine-queue.txt."""
        state = data["states"].get("enqueue_children", {})
        action = state.get("action", "")
        assert "autodev-queue.txt" in action
        assert "recursive-refine-queue.txt" not in action

    def test_enqueue_children_filters_by_parent_reference(self, data: dict) -> None:
        """enqueue_children must filter candidates by 'Decomposed from' parent reference
        (same discipline as recursive-refine's detect_children/enqueue_children)."""
        # Detect_children does the filter; enqueue_children consumes the filtered file.
        detect_action = data["states"].get("detect_children", {}).get("action", "")
        assert "Decomposed from" in detect_action

    def test_broke_down_flag_copied_to_autodev_namespace(self, data: dict) -> None:
        """autodev must copy refine-broke-down to autodev-broke-down after the sub-loop
        returns, and read the copy for its own routing."""
        # Some state must cp the source file to autodev-broke-down.
        copied = any(
            "autodev-broke-down" in s.get("action", "")
            and "refine-broke-down" in s.get("action", "")
            for s in data["states"].values()
        )
        assert copied, (
            "No state copies refine-broke-down to autodev-broke-down; "
            "cross-loop handshake must be namespaced into autodev-*"
        )

    def test_check_broke_down_reads_autodev_namespaced_flag(self, data: dict) -> None:
        """check_broke_down must read the autodev-namespaced copy, not the source file."""
        state = data["states"].get("check_broke_down", {})
        action = state.get("action", "")
        assert "autodev-broke-down" in action
        # BUG-1183: the shortcut must also depend on a non-empty children file,
        # not the flag alone.
        assert "autodev-new-children.txt" in action

    def test_check_broke_down_evaluate_output_numeric_lt_1(self, data: dict) -> None:
        """check_broke_down must use output_numeric lt 1 to gate the shortcut."""
        state = data["states"].get("check_broke_down", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_broke_down evaluate.type should be 'output_numeric', got {evaluate.get('type')!r}"
        )
        assert evaluate.get("operator") == "lt", (
            f"check_broke_down evaluate.operator should be 'lt', got {evaluate.get('operator')!r}"
        )
        assert evaluate.get("target") == 1, (
            f"check_broke_down evaluate.target should be 1, got {evaluate.get('target')!r}"
        )

    def test_check_broke_down_on_yes_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_yes (flag=0 OR no children) must route to recheck_scores."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_yes") == "recheck_scores", (
            f"check_broke_down.on_yes should be 'recheck_scores', got {state.get('on_yes')!r}"
        )

    def test_check_broke_down_on_no_routes_to_enqueue_or_skip(self, data: dict) -> None:
        """check_broke_down.on_no (flag=1 AND children exist) must route to enqueue_or_skip."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_no") == "enqueue_or_skip", (
            f"check_broke_down.on_no should be 'enqueue_or_skip', got {state.get('on_no')!r}"
        )

    def test_check_broke_down_on_error_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_error must route to recheck_scores (fail-safe)."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_error") == "recheck_scores", (
            f"check_broke_down.on_error should be 'recheck_scores', got {state.get('on_error')!r}"
        )

    def test_tmp_files_use_autodev_namespace(self, data: dict) -> None:
        """All new bookkeeping temp files must use the autodev-* namespace, not recursive-refine-*."""
        for name, state in data["states"].items():
            action = state.get("action", "")
            # These recursive-refine-scoped files must not be read or written from autodev
            # (except recursive-refine-broke-down, which is the shared handshake source — copied to autodev-*).
            assert "recursive-refine-passed.txt" not in action, (
                f"State {name!r} reads recursive-refine-passed.txt"
            )
            assert "recursive-refine-skipped.txt" not in action, (
                f"State {name!r} reads recursive-refine-skipped.txt"
            )
            assert "recursive-refine-queue.txt" not in action, (
                f"State {name!r} rewrites recursive-refine-queue.txt"
            )
            assert "recursive-refine-pre-ids.txt" not in action, (
                f"State {name!r} uses recursive-refine-pre-ids.txt; namespace as autodev-*"
            )
            assert "recursive-refine-post-ids.txt" not in action, (
                f"State {name!r} uses recursive-refine-post-ids.txt; namespace as autodev-*"
            )

    def test_context_passthrough_on_refine_current(self, data: dict) -> None:
        """refine_current must use context_passthrough so the captured input reaches the sub-loop."""
        state = data["states"].get("refine_current", {})
        assert state.get("context_passthrough") is True

    # BUG-1226: autodev-inflight handshake covers timeouts outside the
    # executor flush race window (Part 1). dequeue_next records the in-flight
    # issue ID; enqueue_or_skip and enqueue_children clear it on resolution;
    # init resets it at loop start; done surfaces it when non-empty so the
    # user knows which issue to re-queue.

    def test_init_resets_autodev_inflight(self, data: dict) -> None:
        """init must reset .loops/tmp/autodev-inflight alongside autodev-broke-down."""
        init = data["states"].get("init", {})
        action = init.get("action", "")
        assert "autodev-inflight" in action, (
            "init must reset autodev-inflight to clear stale handshake state "
            "from previous runs (BUG-1226)"
        )

    def test_dequeue_next_writes_autodev_inflight(self, data: dict) -> None:
        """dequeue_next must record the popped issue ID in autodev-inflight."""
        state = data["states"].get("dequeue_next", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "dequeue_next must write the dequeued issue ID to autodev-inflight "
            "so the loop can surface mid-flight issues on timeout (BUG-1226)"
        )

    def test_enqueue_or_skip_uses_shell_exit_fragment(self, data: dict) -> None:
        """enqueue_or_skip must use shell_exit fragment for conditional routing (BUG-1230)."""
        state = data["states"].get("enqueue_or_skip", {})
        assert state.get("fragment") == "shell_exit", (
            f"enqueue_or_skip.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_enqueue_or_skip_on_yes_routes_to_dequeue_next(self, data: dict) -> None:
        """enqueue_or_skip.on_yes (children found) must route to dequeue_next."""
        state = data["states"].get("enqueue_or_skip", {})
        assert state.get("on_yes") == "dequeue_next", (
            f"enqueue_or_skip.on_yes should be 'dequeue_next', got {state.get('on_yes')!r}"
        )

    def test_enqueue_or_skip_on_no_routes_to_recheck_after_size_review(self, data: dict) -> None:
        """enqueue_or_skip.on_no (no children) must route to recheck_after_size_review (BUG-1230)."""
        state = data["states"].get("enqueue_or_skip", {})
        assert state.get("on_no") == "recheck_after_size_review", (
            f"enqueue_or_skip.on_no should be 'recheck_after_size_review', got {state.get('on_no')!r}"
        )

    def test_enqueue_or_skip_clears_autodev_inflight(self, data: dict) -> None:
        """enqueue_or_skip must clear autodev-inflight in the children-found branch (BUG-1226/1230).
        The skip-path inflight clear moved to recheck_after_size_review (BUG-1230)."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "enqueue_or_skip must clear autodev-inflight in the children-found branch (BUG-1226); "
            "the skip-path clear is handled by recheck_after_size_review (BUG-1230)"
        )

    def test_enqueue_children_clears_autodev_inflight(self, data: dict) -> None:
        """enqueue_children must clear autodev-inflight after decomposition."""
        state = data["states"].get("enqueue_children", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "enqueue_children resolves the current issue by decomposition and "
            "must clear autodev-inflight (BUG-1226)"
        )

    def test_done_surfaces_autodev_inflight_warning(self, data: dict) -> None:
        """done must read autodev-inflight and emit a warning when non-empty."""
        state = data["states"].get("done", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "done must read autodev-inflight so the user knows which issue "
            "was in-flight at loop termination (BUG-1226)"
        )

    # BUG-1230: recheck_after_size_review — score check after size-review
    # declines to decompose. Routes to implement_current on pass so leaf-sized
    # ready issues are not silently skipped.

    def test_recheck_after_size_review_uses_shell_exit_fragment(self, data: dict) -> None:
        """recheck_after_size_review must use shell_exit fragment."""
        state = data["states"].get("recheck_after_size_review", {})
        assert state.get("fragment") == "shell_exit", (
            f"recheck_after_size_review.fragment should be 'shell_exit', "
            f"got {state.get('fragment')!r}"
        )

    def test_recheck_after_size_review_on_yes_routes_to_decide_current(self, data: dict) -> None:
        """recheck_after_size_review.on_yes (scores pass) must route to decide_current."""
        state = data["states"].get("recheck_after_size_review", {})
        assert state.get("on_yes") == "decide_current", (
            f"recheck_after_size_review.on_yes should be 'decide_current', "
            f"got {state.get('on_yes')!r}"
        )

    def test_recheck_after_size_review_on_no_routes_to_dequeue_next(self, data: dict) -> None:
        """recheck_after_size_review.on_no (scores fail) must route to dequeue_next."""
        state = data["states"].get("recheck_after_size_review", {})
        assert state.get("on_no") == "dequeue_next", (
            f"recheck_after_size_review.on_no should be 'dequeue_next', got {state.get('on_no')!r}"
        )

    def test_recheck_after_size_review_clears_autodev_inflight(self, data: dict) -> None:
        """recheck_after_size_review must clear autodev-inflight on the skip path."""
        state = data["states"].get("recheck_after_size_review", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "recheck_after_size_review must clear autodev-inflight when scores fail "
            "so done does not warn about a stale in-flight entry (BUG-1230)"
        )

    def test_recheck_scores_on_yes_routes_to_decide_current(self, data: dict) -> None:
        """recheck_scores.on_yes (scores pass) must route to decide_current."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_yes") == "decide_current", (
            f"recheck_scores.on_yes should be 'decide_current', got {state.get('on_yes')!r}"
        )

    def test_recheck_scores_on_no_routes_to_check_decision_before_size_review(
        self, data: dict
    ) -> None:
        """recheck_scores.on_no (scores fail) must route to check_decision_before_size_review."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_no") == "check_decision_before_size_review", (
            f"recheck_scores.on_no should be 'check_decision_before_size_review', got {state.get('on_no')!r}"
        )

    def test_check_decision_before_size_review_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_decision_before_size_review must use shell_exit fragment to route on exit code."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_before_size_review.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_decision_before_size_review_on_yes_routes_to_run_decide(
        self, data: dict
    ) -> None:
        """check_decision_before_size_review.on_yes (decision_needed=true) must route to run_decide."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("on_yes") == "run_decide", (
            f"check_decision_before_size_review.on_yes should be 'run_decide', got {state.get('on_yes')!r}"
        )

    def test_check_decision_before_size_review_on_no_routes_to_run_size_review(
        self, data: dict
    ) -> None:
        """check_decision_before_size_review.on_no (no decision needed) must route to run_size_review."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("on_no") == "run_size_review", (
            f"check_decision_before_size_review.on_no should be 'run_size_review', got {state.get('on_no')!r}"
        )

    def test_triage_outcome_failure_uses_shell_exit_fragment(self, data: dict) -> None:
        """triage_outcome_failure must use shell_exit fragment to route on exit code."""
        state = data["states"].get("triage_outcome_failure", {})
        assert state.get("fragment") == "shell_exit", (
            f"triage_outcome_failure.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_triage_outcome_failure_on_yes_routes_to_run_decide(self, data: dict) -> None:
        """triage_outcome_failure.on_yes (low ambiguity score) must route to run_decide."""
        state = data["states"].get("triage_outcome_failure", {})
        assert state.get("on_yes") == "run_decide", (
            f"triage_outcome_failure.on_yes should be 'run_decide', got {state.get('on_yes')!r}"
        )

    def test_triage_outcome_failure_on_no_routes_to_check_missing_artifacts(
        self, data: dict
    ) -> None:
        """triage_outcome_failure.on_no (not a decision) must route to check_missing_artifacts gate."""
        state = data["states"].get("triage_outcome_failure", {})
        assert state.get("on_no") == "check_missing_artifacts", (
            f"triage_outcome_failure.on_no should be 'check_missing_artifacts', got {state.get('on_no')!r}"
        )

    def test_triage_outcome_failure_on_error_routes_to_detect_children(self, data: dict) -> None:
        """triage_outcome_failure.on_error must fall back safely to detect_children."""
        state = data["states"].get("triage_outcome_failure", {})
        assert state.get("on_error") == "detect_children", (
            f"triage_outcome_failure.on_error should be 'detect_children', got {state.get('on_error')!r}"
        )

    def test_triage_outcome_failure_action_checks_decision_needed(self, data: dict) -> None:
        """triage_outcome_failure action must read decision_needed flag, not only score_ambiguity."""
        state = data["states"].get("triage_outcome_failure", {})
        action = state.get("action", "")
        assert "decision_needed" in action, (
            "triage_outcome_failure action must check 'decision_needed' flag as authoritative routing signal"
        )

    def test_check_missing_artifacts_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_missing_artifacts must use shell_exit fragment to route on exit code."""
        state = data["states"].get("check_missing_artifacts", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_missing_artifacts.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_missing_artifacts_on_yes_routes_to_run_wire(self, data: dict) -> None:
        """check_missing_artifacts.on_yes (missing_artifacts=true) must route to run_wire."""
        state = data["states"].get("check_missing_artifacts", {})
        assert state.get("on_yes") == "run_wire", (
            f"check_missing_artifacts.on_yes should be 'run_wire', got {state.get('on_yes')!r}"
        )

    def test_check_missing_artifacts_on_no_routes_to_detect_children(self, data: dict) -> None:
        """check_missing_artifacts.on_no (no missing artifacts) must route to detect_children."""
        state = data["states"].get("check_missing_artifacts", {})
        assert state.get("on_no") == "detect_children", (
            f"check_missing_artifacts.on_no should be 'detect_children', got {state.get('on_no')!r}"
        )

    def test_run_wire_uses_with_rate_limit_handling_fragment(self, data: dict) -> None:
        """run_wire must use with_rate_limit_handling fragment (mirrors run_decide)."""
        state = data["states"].get("run_wire", {})
        assert state.get("fragment") == "with_rate_limit_handling", (
            f"run_wire.fragment should be 'with_rate_limit_handling', got {state.get('fragment')!r}"
        )

    def test_run_wire_action_type_is_slash_command(self, data: dict) -> None:
        """run_wire must use slash_command action_type."""
        state = data["states"].get("run_wire", {})
        assert state.get("action_type") == "slash_command", (
            f"run_wire.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )

    def test_run_refine_uses_with_rate_limit_handling_fragment(self, data: dict) -> None:
        """run_refine must use with_rate_limit_handling fragment (mirrors run_decide)."""
        state = data["states"].get("run_refine", {})
        assert state.get("fragment") == "with_rate_limit_handling", (
            f"run_refine.fragment should be 'with_rate_limit_handling', got {state.get('fragment')!r}"
        )

    def test_run_refine_action_type_is_slash_command(self, data: dict) -> None:
        """run_refine must use slash_command action_type."""
        state = data["states"].get("run_refine", {})
        assert state.get("action_type") == "slash_command", (
            f"run_refine.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )

    def test_decide_current_uses_shell_exit_fragment(self, data: dict) -> None:
        """decide_current must use shell_exit fragment to route on exit code."""
        state = data["states"].get("decide_current", {})
        assert state.get("fragment") == "shell_exit", (
            f"decide_current.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_decide_current_on_yes_routes_to_run_decide(self, data: dict) -> None:
        """decide_current.on_yes (decision_needed=true) must route to run_decide."""
        state = data["states"].get("decide_current", {})
        assert state.get("on_yes") == "run_decide", (
            f"decide_current.on_yes should be 'run_decide', got {state.get('on_yes')!r}"
        )

    def test_decide_current_on_no_routes_to_implement_current(self, data: dict) -> None:
        """decide_current.on_no (no decision needed) must route to implement_current."""
        state = data["states"].get("decide_current", {})
        assert state.get("on_no") == "implement_current", (
            f"decide_current.on_no should be 'implement_current', got {state.get('on_no')!r}"
        )

    def test_run_decide_uses_with_rate_limit_handling_fragment(self, data: dict) -> None:
        """run_decide must use with_rate_limit_handling fragment."""
        state = data["states"].get("run_decide", {})
        assert state.get("fragment") == "with_rate_limit_handling"

    def test_run_decide_next_routes_to_mark_decide_ran(self, data: dict) -> None:
        """ENH-1415: run_decide.next must route to mark_decide_ran so the decide-ran flag is
        set before the refreshed-score gate; mark_decide_ran in turn routes to
        rerun_confidence_after_decide."""
        state = data["states"].get("run_decide", {})
        assert state.get("next") == "mark_decide_ran"

    def test_run_decide_on_error_routes_to_implement_current(self, data: dict) -> None:
        """run_decide.on_error must fall through to recheck_after_decide (degraded mode)."""
        state = data["states"].get("run_decide", {})
        assert state.get("on_error") == "recheck_after_decide"

    def test_run_decide_on_rate_limit_exhausted_routes_to_done(self, data: dict) -> None:
        """run_decide.on_rate_limit_exhausted must terminate the loop."""
        state = data["states"].get("run_decide", {})
        assert state.get("on_rate_limit_exhausted") == "done"

    def test_rerun_confidence_after_decide_state_exists(self, data: dict) -> None:
        """rerun_confidence_after_decide must be present in the state machine."""
        assert "rerun_confidence_after_decide" in data["states"], (
            "rerun_confidence_after_decide state missing — BUG-1378 fix not applied"
        )

    def test_rerun_confidence_after_decide_uses_with_rate_limit_handling_fragment(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_decide must use with_rate_limit_handling fragment."""
        state = data["states"].get("rerun_confidence_after_decide", {})
        assert state.get("fragment") == "with_rate_limit_handling", (
            f"rerun_confidence_after_decide.fragment should be 'with_rate_limit_handling', got {state.get('fragment')!r}"
        )

    def test_rerun_confidence_after_decide_action_type_is_slash_command(self, data: dict) -> None:
        """rerun_confidence_after_decide must use slash_command action_type."""
        state = data["states"].get("rerun_confidence_after_decide", {})
        assert state.get("action_type") == "slash_command", (
            f"rerun_confidence_after_decide.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )

    def test_rerun_confidence_after_decide_action_contains_confidence_check(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_decide action must invoke /ll:confidence-check."""
        state = data["states"].get("rerun_confidence_after_decide", {})
        action = state.get("action", "")
        assert "/ll:confidence-check" in action, (
            f"rerun_confidence_after_decide.action should contain '/ll:confidence-check', got {action!r}"
        )

    def test_rerun_confidence_after_decide_next_routes_to_recheck_after_decide(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_decide.next must route to recheck_after_decide."""
        state = data["states"].get("rerun_confidence_after_decide", {})
        assert state.get("next") == "recheck_after_decide", (
            f"rerun_confidence_after_decide.next should be 'recheck_after_decide', got {state.get('next')!r}"
        )

    def test_rerun_confidence_after_decide_on_error_routes_to_recheck_after_decide(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_decide.on_error must fall back to recheck_after_decide."""
        state = data["states"].get("rerun_confidence_after_decide", {})
        assert state.get("on_error") == "recheck_after_decide", (
            f"rerun_confidence_after_decide.on_error should be 'recheck_after_decide', got {state.get('on_error')!r}"
        )

    def test_rerun_confidence_after_decide_on_rate_limit_exhausted_routes_to_done(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_decide.on_rate_limit_exhausted must terminate the loop."""
        state = data["states"].get("rerun_confidence_after_decide", {})
        assert state.get("on_rate_limit_exhausted") == "done", (
            f"rerun_confidence_after_decide.on_rate_limit_exhausted should be 'done', got {state.get('on_rate_limit_exhausted')!r}"
        )

    # ENH-1415: route post-decide outcome failures to size-review instead of dropping the issue.

    def test_mark_decide_ran_state_exists(self, data: dict) -> None:
        """ENH-1415: mark_decide_ran must be present so decide_current can short-circuit
        on re-entry from recheck_after_size_review."""
        assert "mark_decide_ran" in data["states"], (
            "mark_decide_ran state missing — ENH-1415 fix not applied"
        )

    def test_mark_decide_ran_next_routes_to_rerun_confidence_after_decide(self, data: dict) -> None:
        """ENH-1415: mark_decide_ran.next must route to rerun_confidence_after_decide so the
        post-decide score refresh still runs."""
        state = data["states"].get("mark_decide_ran", {})
        assert state.get("next") == "rerun_confidence_after_decide"
        assert state.get("on_error") == "rerun_confidence_after_decide"

    def test_mark_decide_ran_writes_decide_ran_flag(self, data: dict) -> None:
        """ENH-1415: mark_decide_ran.action must write the .loops/tmp/autodev-decide-ran flag."""
        state = data["states"].get("mark_decide_ran", {})
        action = state.get("action", "")
        assert "autodev-decide-ran" in action, (
            f"mark_decide_ran.action must write autodev-decide-ran, got {action!r}"
        )

    def test_snap_and_size_review_state_exists(self, data: dict) -> None:
        """ENH-1415: snap_and_size_review must be present so recheck_after_decide can
        route outcome failures to decomposition rather than dropping them."""
        assert "snap_and_size_review" in data["states"], (
            "snap_and_size_review state missing — ENH-1415 fix not applied"
        )

    def test_snap_and_size_review_next_routes_to_run_size_review(self, data: dict) -> None:
        """ENH-1415: snap_and_size_review must hand off to run_size_review."""
        state = data["states"].get("snap_and_size_review", {})
        assert state.get("next") == "run_size_review"
        assert state.get("on_error") == "run_size_review"

    def test_snap_and_size_review_refreshes_pre_ids(self, data: dict) -> None:
        """ENH-1415: snap_and_size_review must snapshot current IDs into autodev-pre-ids.txt
        so enqueue_or_skip's diff captures only this size-review's children."""
        state = data["states"].get("snap_and_size_review", {})
        action = state.get("action", "")
        assert "autodev-pre-ids.txt" in action, (
            f"snap_and_size_review.action must write autodev-pre-ids.txt, got {action!r}"
        )

    def test_recheck_after_decide_on_no_routes_to_snap_and_size_review(self, data: dict) -> None:
        """ENH-1415: when outcome still fails after decide, route to snap_and_size_review so
        the issue gets a decomposition attempt rather than being silently dropped."""
        state = data["states"].get("recheck_after_decide", {})
        assert state.get("on_no") == "snap_and_size_review", (
            f"recheck_after_decide.on_no should be 'snap_and_size_review' "
            f"(was 'dequeue_next' pre-ENH-1415), got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "snap_and_size_review", (
            f"recheck_after_decide.on_error should also fall through to snap_and_size_review, "
            f"got {state.get('on_error')!r}"
        )

    def test_decide_current_checks_decide_ran_flag(self, data: dict) -> None:
        """ENH-1415: decide_current must check the autodev-decide-ran flag so it short-circuits
        to implement_current when re-entered from recheck_after_size_review."""
        state = data["states"].get("decide_current", {})
        action = state.get("action", "")
        assert "autodev-decide-ran" in action, (
            f"decide_current.action must check autodev-decide-ran, got {action!r}"
        )

    def test_dequeue_next_clears_autodev_decide_ran(self, data: dict) -> None:
        """ENH-1415: dequeue_next must clear the per-iteration autodev-decide-ran flag so
        the next issue starts without a stale decide-ran marker."""
        state = data["states"].get("dequeue_next", {})
        action = state.get("action", "")
        assert "autodev-decide-ran" in action, (
            f"dequeue_next.action must clear autodev-decide-ran, got {action!r}"
        )

    # BUG-1491: rerun confidence after wire+refine repair path

    def test_run_refine_next_routes_to_rerun_confidence_after_wire(self, data: dict) -> None:
        """BUG-1491: run_refine.next must route to rerun_confidence_after_wire, not enqueue_or_skip."""
        state = data["states"].get("run_refine", {})
        assert state.get("next") == "rerun_confidence_after_wire", (
            f"run_refine.next should be 'rerun_confidence_after_wire', got {state.get('next')!r}"
        )

    def test_run_refine_on_error_routes_to_rerun_confidence_after_wire(self, data: dict) -> None:
        """BUG-1491: run_refine.on_error must route to rerun_confidence_after_wire."""
        state = data["states"].get("run_refine", {})
        assert state.get("on_error") == "rerun_confidence_after_wire", (
            f"run_refine.on_error should be 'rerun_confidence_after_wire', got {state.get('on_error')!r}"
        )

    def test_rerun_confidence_after_wire_state_exists(self, data: dict) -> None:
        """BUG-1491: rerun_confidence_after_wire must be present in the state machine."""
        assert "rerun_confidence_after_wire" in data["states"], (
            "rerun_confidence_after_wire state missing — BUG-1491 fix not applied"
        )

    def test_rerun_confidence_after_wire_uses_with_rate_limit_handling_fragment(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_wire must use with_rate_limit_handling fragment."""
        state = data["states"].get("rerun_confidence_after_wire", {})
        assert state.get("fragment") == "with_rate_limit_handling", (
            f"rerun_confidence_after_wire.fragment should be 'with_rate_limit_handling', got {state.get('fragment')!r}"
        )

    def test_rerun_confidence_after_wire_action_type_is_slash_command(self, data: dict) -> None:
        """rerun_confidence_after_wire must use slash_command action_type."""
        state = data["states"].get("rerun_confidence_after_wire", {})
        assert state.get("action_type") == "slash_command", (
            f"rerun_confidence_after_wire.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )

    def test_rerun_confidence_after_wire_action_contains_confidence_check(self, data: dict) -> None:
        """rerun_confidence_after_wire action must invoke /ll:confidence-check."""
        state = data["states"].get("rerun_confidence_after_wire", {})
        action = state.get("action", "")
        assert "/ll:confidence-check" in action, (
            f"rerun_confidence_after_wire.action should contain '/ll:confidence-check', got {action!r}"
        )

    def test_rerun_confidence_after_wire_next_routes_to_enqueue_or_skip(self, data: dict) -> None:
        """rerun_confidence_after_wire.next must route to enqueue_or_skip."""
        state = data["states"].get("rerun_confidence_after_wire", {})
        assert state.get("next") == "enqueue_or_skip", (
            f"rerun_confidence_after_wire.next should be 'enqueue_or_skip', got {state.get('next')!r}"
        )

    def test_rerun_confidence_after_wire_on_error_routes_to_enqueue_or_skip(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_wire.on_error must fall back to enqueue_or_skip."""
        state = data["states"].get("rerun_confidence_after_wire", {})
        assert state.get("on_error") == "enqueue_or_skip", (
            f"rerun_confidence_after_wire.on_error should be 'enqueue_or_skip', got {state.get('on_error')!r}"
        )

    def test_rerun_confidence_after_wire_on_rate_limit_exhausted_routes_to_done(
        self, data: dict
    ) -> None:
        """rerun_confidence_after_wire.on_rate_limit_exhausted must terminate the loop."""
        state = data["states"].get("rerun_confidence_after_wire", {})
        assert state.get("on_rate_limit_exhausted") == "done", (
            f"rerun_confidence_after_wire.on_rate_limit_exhausted should be 'done', got {state.get('on_rate_limit_exhausted')!r}"
        )

    def test_skip_inflight_shell_action_writes_skipped_and_clears_inflight(
        self, data: dict, tmp_path: Path
    ) -> None:
        """skip_inflight shell action must append the issue ID to autodev-skipped.txt and
        remove autodev-inflight (ENH-1679).  Modelled on TestAutoRefineAndImplementLoop
        shell-action tests."""
        state = data["states"].get("skip_inflight", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0001")
        (run_dir / "autodev-skipped.txt").write_text("")
        # Substitute template variables with concrete values before running
        script = action.replace("${captured.input.output}", "ENH-0001")
        script = script.replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"skip_inflight action failed: {result.stderr}"
        skipped = (run_dir / "autodev-skipped.txt").read_text()
        assert "ENH-0001" in skipped, "skip_inflight must write the issue ID to autodev-skipped.txt"
        assert not (run_dir / "autodev-inflight").exists(), (
            "skip_inflight must remove autodev-inflight so done does not surface a stale warning"
        )

    def test_implement_current_reconciliation_prepends_stale_inflight(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-1870: on resume, a stale inflight issue (INFLIGHT != CURRENT) whose status
        is not done/cancelled must be prepended to autodev-queue.txt before ll-auto runs."""
        state = data["states"].get("implement_current", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0099")
        (run_dir / "autodev-queue.txt").write_text("ENH-0100\n")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        mock_ll_auto = bin_dir / "ll-auto"
        mock_ll_auto.write_text("#!/bin/bash\nexit 0\n")
        mock_ll_auto.chmod(0o755)
        script = action.replace("${captured.input.output}", "ENH-0042")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = f"export PATH={bin_dir}:$PATH\n" + script
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"implement_current reconciliation failed: {result.stderr}"
        queue = (run_dir / "autodev-queue.txt").read_text()
        assert queue.startswith("ENH-0099"), (
            f"Stale inflight ENH-0099 must be prepended to queue; got: {queue!r}"
        )
        assert "ENH-0100" in queue, "Original queue entry ENH-0100 must be preserved"

    def test_implement_current_reconciliation_noop_when_inflight_equals_current(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-1870: when autodev-inflight equals CURRENT (normal non-resumed run),
        the reconciliation block must not modify autodev-queue.txt."""
        state = data["states"].get("implement_current", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0042")
        (run_dir / "autodev-queue.txt").write_text("ENH-0100\n")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        mock_ll_auto = bin_dir / "ll-auto"
        mock_ll_auto.write_text("#!/bin/bash\nexit 0\n")
        mock_ll_auto.chmod(0o755)
        script = action.replace("${captured.input.output}", "ENH-0042")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = f"export PATH={bin_dir}:$PATH\n" + script
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"implement_current action failed: {result.stderr}"
        queue = (run_dir / "autodev-queue.txt").read_text()
        assert queue.strip() == "ENH-0100", (
            f"Queue must be unchanged when inflight == current; got: {queue!r}"
        )

    def test_implement_current_reconciliation_skips_done_inflight(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-1870: when inflight issue already has status: done, it must not be
        re-queued even if INFLIGHT != CURRENT."""
        state = data["states"].get("implement_current", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0099")
        (run_dir / "autodev-queue.txt").write_text("ENH-0100\n")
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        (issues_dir / "P3-ENH-0099-test-issue.md").write_text(
            "---\nid: ENH-0099\nstatus: done\n---\n"
        )
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        mock_ll_auto = bin_dir / "ll-auto"
        mock_ll_auto.write_text("#!/bin/bash\nexit 0\n")
        mock_ll_auto.chmod(0o755)
        script = action.replace("${captured.input.output}", "ENH-0042")
        script = script.replace("${context.run_dir}", str(run_dir))
        script = f"export PATH={bin_dir}:$PATH\n" + script
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"implement_current action failed: {result.stderr}"
        queue = (run_dir / "autodev-queue.txt").read_text()
        assert "ENH-0099" not in queue, (
            f"Done inflight issue ENH-0099 must not be re-queued; got: {queue!r}"
        )
        assert "ENH-0100" in queue, "Original queue entry ENH-0100 must be preserved"

    def test_scope_field_uses_run_dir_template(self, data: dict) -> None:
        """autodev must declare scope: ["${context.run_dir}"] for per-instance lock isolation
        (FEAT-1789). This enables concurrent autodev instances with different run_dir values."""
        scope = data.get("scope")
        assert scope is not None, (
            "autodev.yaml must declare a 'scope' field for per-instance lock isolation"
        )
        assert isinstance(scope, list), f"scope must be a list, got {type(scope).__name__}"
        assert "${context.run_dir}" in scope, (
            f"scope must contain '${{context.run_dir}}' template, got {scope!r}"
        )


class TestRecursiveRefineLoop:
    """Structural tests for the recursive-refine FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "recursive-refine.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "recursive-refine"
        assert data.get("initial") == "parse_input"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "parse_input",
            "dequeue_next",
            "check_attempt_budget",
            "capture_baseline",
            "run_refine",
            "check_passed",
            "detect_children",
            "enqueue_children",
            "size_review_snap",
            "check_broke_down",
            "recheck_scores",
            "check_depth",
            "run_size_review",
            "enqueue_or_skip",
            "aggregate_decomposition",
            "done",
            "diagnose",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        failed_state = data["states"].get("failed", {})
        assert failed_state.get("terminal") is True

    def test_dequeue_next_captures_input(self, data: dict) -> None:
        """dequeue_next must capture as 'input' for context_passthrough to work."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("capture") == "input"

    def test_dequeue_next_routes_to_check_attempt_budget(self, data: dict) -> None:
        """dequeue_next.on_yes must route to check_attempt_budget (not directly to capture_baseline)."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("on_yes") == "check_attempt_budget"

    def test_dequeue_next_on_no_routes_to_aggregate_decomposition(self, data: dict) -> None:
        """dequeue_next.on_no must route to aggregate_decomposition (not directly to done)."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("on_no") == "aggregate_decomposition"

    def test_aggregate_decomposition_state_exists(self, data: dict) -> None:
        """aggregate_decomposition state must be present in the FSM."""
        assert "aggregate_decomposition" in data["states"]

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    def test_parse_input_on_error_routes_to_diagnose(self, data: dict) -> None:
        state = data["states"].get("parse_input", {})
        assert state.get("on_error") == "diagnose"
        assert state.get("on_no") == "diagnose"

    def test_aggregate_decomposition_routes_to_done(self, data: dict) -> None:
        """aggregate_decomposition.next must route to done."""
        state = data["states"].get("aggregate_decomposition", {})
        assert state.get("next") == "done"

    def test_check_attempt_budget_routes_to_capture_baseline(self, data: dict) -> None:
        """check_attempt_budget.on_yes must route to capture_baseline."""
        state = data["states"].get("check_attempt_budget", {})
        assert state.get("on_yes") == "capture_baseline"

    def test_run_refine_delegates_to_sub_loop(self, data: dict) -> None:
        """run_refine must delegate to refine-to-ready-issue with context_passthrough."""
        state = data["states"].get("run_refine", {})
        assert state.get("loop") == "refine-to-ready-issue"
        assert state.get("context_passthrough") is True

    def test_run_refine_has_success_and_failure_routes(self, data: dict) -> None:
        """run_refine must define on_success and on_failure routes."""
        state = data["states"].get("run_refine", {})
        assert "on_success" in state
        assert "on_failure" in state

    def test_queue_file_uses_run_dir(self, data: dict) -> None:
        """Queue file references must use ${context.run_dir} (not bare .loops/tmp/)."""
        states = data.get("states", {})
        queue_ref = "recursive-refine-queue"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if queue_ref in action:
                found = True
                assert "${context.run_dir}" in action, (
                    f"Queue file reference must use ${{context.run_dir}}, got: {action[:200]}"
                )
        assert found, f"No state references {queue_ref!r}"

    def test_skipped_file_uses_run_dir(self, data: dict) -> None:
        """Skipped tracking file must use ${context.run_dir} path."""
        states = data.get("states", {})
        skipped_ref = "recursive-refine-skipped"
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if skipped_ref in action:
                found = True
                assert "${context.run_dir}" in action
        assert found, f"No state references {skipped_ref!r}"

    def test_parse_input_validates_context_input(self, data: dict) -> None:
        """parse_input must check that ${context.input} is non-empty."""
        state = data["states"].get("parse_input", {})
        action = state.get("action", "")
        assert "${context.input}" in action

    def test_run_size_review_uses_auto_flag(self, data: dict) -> None:
        """run_size_review must invoke issue-size-review with --auto flag."""
        state = data["states"].get("run_size_review", {})
        action = state.get("action", "")
        assert "issue-size-review" in action
        assert "--auto" in action

    def test_context_thresholds_defined(self, data: dict) -> None:
        """context block must define the three threshold/limit variables."""
        ctx = data.get("context", {})
        assert "readiness_threshold" in ctx
        assert "outcome_threshold" in ctx
        assert "max_refine_count" in ctx
        assert "max_depth" in ctx

    def test_size_review_snap_routes_to_check_broke_down(self, data: dict) -> None:
        """size_review_snap.next must route to check_broke_down to guard against duplicate size-review."""
        state = data["states"].get("size_review_snap", {})
        assert state.get("next") == "check_broke_down", (
            f"size_review_snap.next should be 'check_broke_down', got {state.get('next')!r}"
        )

    def test_check_broke_down_state_exists(self, data: dict) -> None:
        """check_broke_down state must exist to skip duplicate size-review after breakdown_issue."""
        assert "check_broke_down" in data["states"], (
            "State 'check_broke_down' not found in recursive-refine.yaml"
        )

    def test_check_broke_down_evaluate_output_numeric_lt_1(self, data: dict) -> None:
        """check_broke_down must use output_numeric lt 1 to detect whether breakdown_issue ran."""
        state = data["states"].get("check_broke_down", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_broke_down evaluate.type should be 'output_numeric', got {evaluate.get('type')!r}"
        )
        assert evaluate.get("operator") == "lt", (
            f"check_broke_down evaluate.operator should be 'lt', got {evaluate.get('operator')!r}"
        )
        assert evaluate.get("target") == 1, (
            f"check_broke_down evaluate.target should be 1, got {evaluate.get('target')!r}"
        )

    def test_check_broke_down_on_yes_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_yes (flag=0, not broken down) must route to recheck_scores."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_yes") == "recheck_scores", (
            f"check_broke_down.on_yes should be 'recheck_scores', got {state.get('on_yes')!r}"
        )

    def test_check_broke_down_on_no_routes_to_enqueue_or_skip(self, data: dict) -> None:
        """check_broke_down.on_no (flag=1, already broken down) must route to enqueue_or_skip."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_no") == "enqueue_or_skip", (
            f"check_broke_down.on_no should be 'enqueue_or_skip', got {state.get('on_no')!r}"
        )

    def test_check_broke_down_on_error_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_error must route to recheck_scores (fail-safe: treat as not broken down)."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_error") == "recheck_scores", (
            f"check_broke_down.on_error should be 'recheck_scores', got {state.get('on_error')!r}"
        )

    def test_check_broke_down_requires_children_file(self, data: dict) -> None:
        """BUG-1183: shortcut must require flag=1 AND non-empty new-children file,
        not the flag alone. Action must reference refine-broke-down and
        recursive-refine-new-children.txt."""
        state = data["states"].get("check_broke_down", {})
        action = state.get("action", "")
        assert "refine-broke-down" in action
        assert "recursive-refine-new-children.txt" in action

    def test_broke_down_flag_cleared_in_capture_baseline(self, data: dict) -> None:
        """capture_baseline must clear refine-broke-down so each issue iteration starts clean."""
        state = data["states"].get("capture_baseline", {})
        assert "refine-broke-down" in state.get("action", ""), (
            "capture_baseline action must clear 'refine-broke-down' flag"
        )

    def test_recheck_scores_routes_to_dequeue_next(self, data: dict) -> None:
        """recheck_scores.on_yes must route to dequeue_next when scores already pass."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_yes") == "dequeue_next", (
            f"recheck_scores.on_yes should be 'dequeue_next', got {state.get('on_yes')!r}"
        )

    def test_recheck_scores_on_no_routes_to_run_size_review(self, data: dict) -> None:
        """recheck_scores.on_no must route to check_depth (which gates into run_size_review)."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_no") == "check_depth", (
            f"recheck_scores.on_no should be 'check_depth', got {state.get('on_no')!r}"
        )

    def test_recheck_scores_on_error_routes_to_run_size_review(self, data: dict) -> None:
        """recheck_scores.on_error must route to check_depth on evaluation error."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_error") == "check_depth", (
            f"recheck_scores.on_error should be 'check_depth', got {state.get('on_error')!r}"
        )

    def test_check_depth_evaluate_output_numeric_lt_1(self, data: dict) -> None:
        """check_depth must use output_numeric lt 1 to detect depth-cap breach."""
        state = data["states"].get("check_depth", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_depth evaluate.type should be 'output_numeric', got {evaluate.get('type')!r}"
        )
        assert evaluate.get("operator") == "lt", (
            f"check_depth evaluate.operator should be 'lt', got {evaluate.get('operator')!r}"
        )
        assert evaluate.get("target") == 1, (
            f"check_depth evaluate.target should be 1, got {evaluate.get('target')!r}"
        )

    def test_check_depth_on_yes_routes_to_check_decision_needed(self, data: dict) -> None:
        """check_depth.on_yes (depth < max_depth) must route to check_decision_needed."""
        state = data["states"].get("check_depth", {})
        assert state.get("on_yes") == "check_decision_needed", (
            f"check_depth.on_yes should be 'check_decision_needed', got {state.get('on_yes')!r}"
        )

    def test_check_depth_on_no_routes_to_dequeue_next(self, data: dict) -> None:
        """check_depth.on_no (depth >= max_depth) must route to dequeue_next, skipping size-review."""
        state = data["states"].get("check_depth", {})
        assert state.get("on_no") == "dequeue_next", (
            f"check_depth.on_no should be 'dequeue_next', got {state.get('on_no')!r}"
        )

    def test_check_depth_on_error_routes_to_check_decision_needed(self, data: dict) -> None:
        """check_depth.on_error must route to check_decision_needed (fail-safe: proceed normally)."""
        state = data["states"].get("check_depth", {})
        assert state.get("on_error") == "check_decision_needed", (
            f"check_depth.on_error should be 'check_decision_needed', got {state.get('on_error')!r}"
        )

    def test_detect_children_filters_by_parent_reference(self, data: dict) -> None:
        """detect_children must use diff-ids.txt intermediate and filter by Decomposed from."""
        state = data["states"].get("detect_children", {})
        action = state.get("action", "")
        assert "recursive-refine-diff-ids.txt" in action, (
            "detect_children must write comm output to diff-ids.txt before filtering"
        )
        assert "Decomposed from" in action, (
            "detect_children must filter candidates by 'Decomposed from' parent reference"
        )

    def test_enqueue_or_skip_filters_by_parent_reference(self, data: dict) -> None:
        """enqueue_or_skip must use diff-ids.txt intermediate and filter by Decomposed from."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        assert "recursive-refine-diff-ids.txt" in action, (
            "enqueue_or_skip must write comm output to diff-ids.txt before filtering"
        )
        assert "Decomposed from" in action, (
            "enqueue_or_skip must filter candidates by 'Decomposed from' parent reference"
        )

    def test_enqueue_children_moves_parent_to_completed(self, data: dict) -> None:
        """enqueue_children must find and move the parent file to .issues/completed/ after decomposition."""
        state = data["states"].get("enqueue_children", {})
        action = state.get("action", "")
        assert "ll-issues path" in action, (
            "enqueue_children must use 'll-issues path' to locate the parent file"
        )
        assert "completed" in action, (
            "enqueue_children must reference 'completed' directory for the move"
        )
        assert "mv" in action, "enqueue_children must contain 'mv' to move the parent file"

    def test_enqueue_or_skip_moves_parent_to_completed_when_children_found(
        self, data: dict
    ) -> None:
        """enqueue_or_skip children-found branch must find and move the parent file to .issues/completed/."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        # The ll-issues path + mv block must appear before the 'else' (no-children branch)
        children_branch = action.split("else")[0] if "else" in action else action
        assert "ll-issues path" in children_branch, (
            "enqueue_or_skip children-found branch must use 'll-issues path' to locate the parent file"
        )
        assert "completed" in children_branch, (
            "enqueue_or_skip children-found branch must reference 'completed' directory"
        )
        assert "mv" in children_branch, (
            "enqueue_or_skip children-found branch must contain 'mv' to move the parent file"
        )

    def test_enqueue_or_skip_else_does_not_move_parent(self, data: dict) -> None:
        """enqueue_or_skip else branch (no children) must NOT move the parent to completed/."""
        state = data["states"].get("enqueue_or_skip", {})
        action = state.get("action", "")
        assert "else" in action, "enqueue_or_skip must have an else branch"
        else_branch = action.split("else", 1)[1]
        assert "completed" not in else_branch, (
            "enqueue_or_skip else branch must NOT move parent to completed/ — "
            "issue remains open for future retry"
        )

    def test_parse_input_initializes_dequeued_count_and_total_enqueued(self, data: dict) -> None:
        """parse_input action must reference both ENH-1348 counter files."""
        action = data["states"].get("parse_input", {}).get("action", "")
        assert "recursive-refine-dequeued-count.txt" in action, (
            "parse_input must initialize recursive-refine-dequeued-count.txt"
        )
        assert "recursive-refine-total-enqueued.txt" in action, (
            "parse_input must initialize recursive-refine-total-enqueued.txt"
        )

    def test_parse_input_initializes_decomposed_and_deadend_tracking_files(
        self, data: dict
    ) -> None:
        """parse_input action must reference both ENH-1350 per-reason tracking files."""
        action = data["states"].get("parse_input", {}).get("action", "")
        assert "recursive-refine-skipped-decomposed.txt" in action, (
            "parse_input must initialize recursive-refine-skipped-decomposed.txt"
        )
        assert "recursive-refine-skipped-deadend.txt" in action, (
            "parse_input must initialize recursive-refine-skipped-deadend.txt"
        )

    def test_dequeue_next_action_references_dequeued_count_file(self, data: dict) -> None:
        """dequeue_next action must read and write recursive-refine-dequeued-count.txt (ENH-1348)."""
        action = data["states"].get("dequeue_next", {}).get("action", "")
        assert "recursive-refine-dequeued-count.txt" in action, (
            "dequeue_next must maintain recursive-refine-dequeued-count.txt for progress line"
        )

    def test_dequeue_next_emits_progress_line_to_stderr(self, data: dict) -> None:
        """dequeue_next action must emit a [N/M] → ID progress line to stderr (ENH-1348)."""
        action = data["states"].get("dequeue_next", {}).get("action", "")
        assert "recursive-refine-total-enqueued.txt" in action, (
            "dequeue_next must read recursive-refine-total-enqueued.txt for the progress line"
        )
        assert ">&2" in action, (
            "dequeue_next must redirect the progress printf to stderr so it does not "
            "interfere with stdout capture"
        )


class TestSprintBuildAndValidateLoop:
    """Structural tests for the sprint-build-and-validate FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "sprint-build-and-validate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "sprint-build-and-validate"
        assert data.get("initial") == "route_input"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "route_input",
            "failed",
            "create_sprint",
            "route_create",
            "extract_sprint_issues",
            "refine_issues",
            "map_dependencies",
            "audit_conflicts",
            "audit_conflicts_retry",
            "commit",
            "run_sprint",
            "extract_unresolved",
            "refine_unresolved",
            "refine_failed",
            "sprint_failed",
            "refine_unresolved_failed",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_route_review_removed(self, data: dict) -> None:
        """route_review state must not exist (replaced by shell_exit routing on run_sprint)."""
        assert "route_review" not in data.get("states", {}), (
            "route_review is a dead state and must be removed"
        )

    def test_route_create_on_yes_targets_extract_sprint_issues(self, data: dict) -> None:
        """route_create.on_yes must target extract_sprint_issues."""
        state = data["states"].get("route_create", {})
        assert state.get("on_yes") == "extract_sprint_issues", (
            f"route_create.on_yes should be 'extract_sprint_issues', got {state.get('on_yes')!r}"
        )

    def test_route_input_routes_to_extract_when_name_provided(self, data: dict) -> None:
        """route_input.on_yes (exit 0, sprint found) must route to extract_sprint_issues."""
        state = data["states"].get("route_input", {})
        assert state.get("on_yes") == "extract_sprint_issues", (
            f"route_input.on_yes should be 'extract_sprint_issues', got {state.get('on_yes')!r}"
        )

    def test_route_input_routes_to_create_when_no_name(self, data: dict) -> None:
        """route_input.on_no (exit 1, no sprint_name) must route to create_sprint."""
        state = data["states"].get("route_input", {})
        assert state.get("on_no") == "create_sprint", (
            f"route_input.on_no should be 'create_sprint', got {state.get('on_no')!r}"
        )

    def test_route_input_routes_to_failed_on_error(self, data: dict) -> None:
        """route_input.on_error (exit 2, sprint file missing) must route to failed terminal state."""
        state = data["states"].get("route_input", {})
        assert state.get("on_error") == "failed", (
            f"route_input.on_error should be 'failed', got {state.get('on_error')!r}"
        )

    def test_failed_is_terminal(self, data: dict) -> None:
        """failed state must be terminal."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True, "failed state must have terminal: true"

    def test_run_sprint_uses_shell_exit_fragment(self, data: dict) -> None:
        """run_sprint must use fragment: shell_exit for exit-code-based routing."""
        state = data["states"].get("run_sprint", {})
        assert state.get("fragment") == "shell_exit", (
            f"run_sprint.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_run_sprint_on_yes_routes_to_done(self, data: dict) -> None:
        """run_sprint.on_yes (exit 0) must route to done."""
        state = data["states"].get("run_sprint", {})
        assert state.get("on_yes") == "done", (
            f"run_sprint.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_run_sprint_on_no_routes_to_extract_unresolved(self, data: dict) -> None:
        """run_sprint.on_no (non-zero exit) must route to extract_unresolved."""
        state = data["states"].get("run_sprint", {})
        assert state.get("on_no") == "extract_unresolved", (
            f"run_sprint.on_no should be 'extract_unresolved', got {state.get('on_no')!r}"
        )

    def test_extract_unresolved_captures_as_input(self, data: dict) -> None:
        """extract_unresolved must capture as 'input' for context_passthrough to work."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("capture") == "input", (
            f"extract_unresolved.capture should be 'input', got {state.get('capture')!r}"
        )

    def test_extract_unresolved_on_yes_routes_to_refine_unresolved(self, data: dict) -> None:
        """extract_unresolved.on_yes must route to refine_unresolved."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("on_yes") == "refine_unresolved", (
            f"extract_unresolved.on_yes should be 'refine_unresolved', got {state.get('on_yes')!r}"
        )

    def test_extract_unresolved_on_no_routes_to_sprint_failed(self, data: dict) -> None:
        """extract_unresolved.on_no (no state file or no failed issues) must route to sprint_failed."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("on_no") == "sprint_failed", (
            f"extract_unresolved.on_no should be 'sprint_failed', got {state.get('on_no')!r}"
        )

    def test_refine_unresolved_delegates_to_recursive_refine(self, data: dict) -> None:
        """refine_unresolved must delegate to recursive-refine sub-loop."""
        state = data["states"].get("refine_unresolved", {})
        assert state.get("loop") == "recursive-refine", (
            f"refine_unresolved.loop should be 'recursive-refine', got {state.get('loop')!r}"
        )

    def test_refine_unresolved_uses_context_passthrough(self, data: dict) -> None:
        """refine_unresolved must use context_passthrough to pass captured.input to child loop."""
        state = data["states"].get("refine_unresolved", {})
        assert state.get("context_passthrough") is True, (
            "refine_unresolved must have context_passthrough: true"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_refine_failed_is_terminal(self, data: dict) -> None:
        """refine_failed must be a terminal state."""
        state = data["states"].get("refine_failed", {})
        assert state.get("terminal") is True, "refine_failed must have terminal: true"

    def test_sprint_failed_is_terminal(self, data: dict) -> None:
        """sprint_failed must be a terminal state."""
        state = data["states"].get("sprint_failed", {})
        assert state.get("terminal") is True, "sprint_failed must have terminal: true"

    def test_refine_unresolved_failed_is_terminal(self, data: dict) -> None:
        """refine_unresolved_failed must be a terminal state."""
        state = data["states"].get("refine_unresolved_failed", {})
        assert state.get("terminal") is True, "refine_unresolved_failed must have terminal: true"

    def test_refine_issues_on_success_routes_to_map_dependencies(self, data: dict) -> None:
        """refine_issues.on_success (child loop done) must still route to map_dependencies."""
        state = data["states"].get("refine_issues", {})
        success = state.get("on_success") or state.get("on_yes")
        assert success == "map_dependencies", (
            f"refine_issues.on_success should be 'map_dependencies', got {success!r}"
        )

    def test_refine_issues_on_failure_routes_to_refine_failed(self, data: dict) -> None:
        """refine_issues.on_failure (child loop failed terminal) must route to refine_failed."""
        state = data["states"].get("refine_issues", {})
        failure = state.get("on_failure") or state.get("on_no")
        assert failure == "refine_failed", (
            f"refine_issues.on_failure should be 'refine_failed', got {failure!r}"
        )

    def test_refine_issues_on_error_routes_to_refine_failed(self, data: dict) -> None:
        """refine_issues.on_error (child loop crash) must route to refine_failed."""
        state = data["states"].get("refine_issues", {})
        assert state.get("on_error") == "refine_failed", (
            f"refine_issues.on_error should be 'refine_failed', got {state.get('on_error')!r}"
        )

    def test_refine_issues_success_and_failure_differ(self, data: dict) -> None:
        """refine_issues success and failure routes must be distinct (anti-laundering guard)."""
        state = data["states"].get("refine_issues", {})
        success = state.get("on_success") or state.get("on_yes")
        failure = state.get("on_failure") or state.get("on_no")
        assert success != failure, (
            f"refine_issues launders verdict: on_success and on_failure both map to {success!r}"
        )

    def test_run_sprint_on_error_routes_to_sprint_failed(self, data: dict) -> None:
        """run_sprint.on_error (crash/killed, no sprint-state.json) must route to sprint_failed."""
        state = data["states"].get("run_sprint", {})
        assert state.get("on_error") == "sprint_failed", (
            f"run_sprint.on_error should be 'sprint_failed', got {state.get('on_error')!r}"
        )

    def test_extract_unresolved_on_error_routes_to_sprint_failed(self, data: dict) -> None:
        """extract_unresolved.on_error must route to sprint_failed."""
        state = data["states"].get("extract_unresolved", {})
        assert state.get("on_error") == "sprint_failed", (
            f"extract_unresolved.on_error should be 'sprint_failed', got {state.get('on_error')!r}"
        )

    def test_refine_unresolved_on_success_routes_to_done(self, data: dict) -> None:
        """refine_unresolved.on_yes (child loop done) must route to done."""
        state = data["states"].get("refine_unresolved", {})
        success = state.get("on_success") or state.get("on_yes")
        assert success == "done", f"refine_unresolved.on_yes should be 'done', got {success!r}"

    def test_refine_unresolved_on_failure_routes_to_refine_unresolved_failed(
        self, data: dict
    ) -> None:
        """refine_unresolved.on_no (child failed terminal) must route to refine_unresolved_failed."""
        state = data["states"].get("refine_unresolved", {})
        failure = state.get("on_failure") or state.get("on_no")
        assert failure == "refine_unresolved_failed", (
            f"refine_unresolved.on_no should be 'refine_unresolved_failed', got {failure!r}"
        )

    def test_refine_unresolved_on_error_routes_to_refine_unresolved_failed(
        self, data: dict
    ) -> None:
        """refine_unresolved.on_error (child crash) must route to refine_unresolved_failed."""
        state = data["states"].get("refine_unresolved", {})
        assert state.get("on_error") == "refine_unresolved_failed", (
            f"refine_unresolved.on_error should be 'refine_unresolved_failed', got {state.get('on_error')!r}"
        )

    def test_refine_unresolved_success_and_failure_differ(self, data: dict) -> None:
        """refine_unresolved success and failure routes must be distinct (anti-laundering guard)."""
        state = data["states"].get("refine_unresolved", {})
        success = state.get("on_success") or state.get("on_yes")
        failure = state.get("on_failure") or state.get("on_no")
        assert success != failure, (
            f"refine_unresolved launders verdict: on_yes and on_no both map to {success!r}"
        )

    def test_audit_conflicts_uses_llm_structured_evaluator(self, data: dict) -> None:
        """audit_conflicts must use an llm_structured evaluator, not bare next:."""
        state = data["states"].get("audit_conflicts", {})
        assert "next" not in state, (
            "audit_conflicts must not use bare next: — it must route via llm_structured evaluate block"
        )
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured", (
            f"audit_conflicts.evaluate.type should be 'llm_structured', got {evaluate.get('type')!r}"
        )

    def test_audit_conflicts_on_yes_routes_to_commit(self, data: dict) -> None:
        """audit_conflicts.on_yes must route to commit."""
        state = data["states"].get("audit_conflicts", {})
        assert state.get("on_yes") == "commit", (
            f"audit_conflicts.on_yes should be 'commit', got {state.get('on_yes')!r}"
        )

    def test_audit_conflicts_on_no_routes_to_retry(self, data: dict) -> None:
        """audit_conflicts.on_no must route to audit_conflicts_retry."""
        state = data["states"].get("audit_conflicts", {})
        assert state.get("on_no") == "audit_conflicts_retry", (
            f"audit_conflicts.on_no should be 'audit_conflicts_retry', got {state.get('on_no')!r}"
        )

    def test_audit_conflicts_on_partial_routes_to_retry(self, data: dict) -> None:
        """audit_conflicts.on_partial must route to audit_conflicts_retry."""
        state = data["states"].get("audit_conflicts", {})
        assert state.get("on_partial") == "audit_conflicts_retry", (
            f"audit_conflicts.on_partial should be 'audit_conflicts_retry', got {state.get('on_partial')!r}"
        )

    def test_audit_conflicts_retry_state_exists(self, data: dict) -> None:
        """audit_conflicts_retry state must exist with next: commit."""
        state = data["states"].get("audit_conflicts_retry", {})
        assert state, "audit_conflicts_retry state must exist"
        assert state.get("next") == "commit", (
            f"audit_conflicts_retry.next should be 'commit', got {state.get('next')!r}"
        )

    def test_max_steps_accommodates_retry_cycle(self, data: dict) -> None:
        """max_steps must be at least 18 to accommodate the audit_conflicts retry path."""
        assert data.get("max_steps", 0) >= 18, (
            f"max_steps should be >= 18 (retry adds up to 2 extra steps), got {data.get('max_steps')}"
        )


class TestHtmlWebsiteGeneratorLoop:
    """Structural tests for the html-website-generator thin-wrapper FSM loop (ENH-1869)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "html-website-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "html-website-generator"
        assert data.get("initial") == "plan"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """Thin wrapper must retain pre-generate states and add run_gen_eval delegation."""
        required = {"plan", "run_gen_eval", "smoke_test", "done", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_inline_generate_evaluate_score_states_removed(self, data: dict) -> None:
        """Inline generate, capture, and score states must be absent in the thin wrapper."""
        states = set(data["states"].keys())
        assert "generate" not in states, "generate state must be removed in thin wrapper"
        assert "capture" not in states, "capture state must be removed in thin wrapper"
        assert "score" not in states, "score state must be removed in thin wrapper"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_run_gen_eval_delegates_to_generator_evaluator(self, data: dict) -> None:
        """run_gen_eval must delegate to oracles/generator-evaluator oracle sub-loop."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("loop") == "oracles/generator-evaluator", (
            f"run_gen_eval.loop should be 'oracles/generator-evaluator', got {state.get('loop')!r}"
        )

    def test_run_gen_eval_with_bindings_present(self, data: dict) -> None:
        """run_gen_eval with: must bind run_dir, generate_prompt, rubric, and pass_threshold."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_, (
            f"run_gen_eval.with must contain 'run_dir', got {list(with_.keys())}"
        )
        assert "generate_prompt" in with_, "run_gen_eval.with must contain 'generate_prompt'"
        assert "rubric" in with_, "run_gen_eval.with must contain 'rubric'"
        assert "pass_threshold" in with_, "run_gen_eval.with must contain 'pass_threshold'"

    def test_run_gen_eval_routes_to_smoke_test_on_yes(self, data: dict) -> None:
        """run_gen_eval must route to smoke_test when sub-loop succeeds (ALL_PASS)."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_yes") == "smoke_test", (
            f"run_gen_eval.on_yes should be 'smoke_test', got {state.get('on_yes')!r}"
        )

    def test_run_gen_eval_routes_to_failed_on_failure(self, data: dict) -> None:
        """run_gen_eval must route to failed when sub-loop fails or exhausts iterations."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_no") == "failed", (
            f"run_gen_eval.on_no should be 'failed', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "failed", (
            f"run_gen_eval.on_error should be 'failed', got {state.get('on_error')!r}"
        )

    def test_plan_routes_to_run_gen_eval(self, data: dict) -> None:
        """plan must route to run_gen_eval (not generate) in the thin wrapper."""
        state = data["states"].get("plan", {})
        assert state.get("next") == "run_gen_eval", (
            f"plan.next should be 'run_gen_eval', got {state.get('next')!r}"
        )

    def test_smoke_test_state_is_shell(self, data: dict) -> None:
        """smoke_test state must use action_type: shell for Playwright functional checks."""
        state = data["states"].get("smoke_test", {})
        assert state.get("action_type") == "shell"

    def test_smoke_test_routes_to_vision_gate_on_pass(self, data: dict) -> None:
        """smoke_test must route to vision_gate (optional aesthetic gate) on pass.

        Functional smoke pass hands off to the vision_gate state, which is a
        no-op passthrough to done unless VISION_* env is configured (the
        vision_gate enhancement); it is no longer a direct edge to done.
        """
        state = data["states"].get("smoke_test", {})
        assert state.get("on_yes") == "vision_gate"

    def test_context_has_description(self, data: dict) -> None:
        """context block must define description variable; output_dir is runner-injected."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_design_tokens_context(self, data: dict) -> None:
        """context block must declare design_tokens_context; runner-injected at loop start."""
        ctx = data.get("context", {})
        assert "design_tokens_context" in ctx

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0


class TestSvgImageGeneratorLoop:
    """Structural tests for the svg-image-generator thin-wrapper FSM loop (ENH-1869)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "svg-image-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "svg-image-generator"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """Thin wrapper must retain pre-generate states and add run_gen_eval delegation."""
        required = {"init", "plan", "run_gen_eval", "done", "diagnose", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_inline_generate_evaluate_score_states_removed(self, data: dict) -> None:
        """Inline generate, evaluate, and score states must be absent in the thin wrapper."""
        states = set(data["states"].keys())
        assert "generate" not in states, "generate state must be removed in thin wrapper"
        assert "evaluate" not in states, "evaluate state must be removed in thin wrapper"
        assert "score" not in states, "score state must be removed in thin wrapper"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "plan"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_run_gen_eval_delegates_to_generator_evaluator(self, data: dict) -> None:
        """run_gen_eval must delegate to oracles/generator-evaluator oracle sub-loop."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("loop") == "oracles/generator-evaluator", (
            f"run_gen_eval.loop should be 'oracles/generator-evaluator', got {state.get('loop')!r}"
        )

    def test_run_gen_eval_with_bindings_present(self, data: dict) -> None:
        """run_gen_eval with: must bind run_dir, generate_prompt, rubric, pass_threshold."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_, (
            f"run_gen_eval.with must contain 'run_dir', got {list(with_.keys())}"
        )
        assert "generate_prompt" in with_, "run_gen_eval.with must contain 'generate_prompt'"
        assert "rubric" in with_, "run_gen_eval.with must contain 'rubric'"
        assert "pass_threshold" in with_, "run_gen_eval.with must contain 'pass_threshold'"

    def test_run_gen_eval_binds_svg_artifact_path(self, data: dict) -> None:
        """run_gen_eval with: must bind artifact_path to 'image.svg' for SVG screenshot."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        assert with_.get("artifact_path") == "image.svg", (
            f"run_gen_eval.with.artifact_path should be 'image.svg', got {with_.get('artifact_path')!r}"
        )

    def test_run_gen_eval_routes_to_done_on_yes(self, data: dict) -> None:
        """run_gen_eval must route to vision_gate when sub-loop succeeds (ALL_PASS)."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_yes") == "vision_gate", (
            f"run_gen_eval.on_yes should be 'vision_gate', got {state.get('on_yes')!r}"
        )

    def test_run_gen_eval_routes_to_diagnose_on_failure(self, data: dict) -> None:
        """run_gen_eval must route to diagnose when sub-loop fails or exhausts iterations."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_no") == "diagnose", (
            f"run_gen_eval.on_no should be 'diagnose', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "diagnose", (
            f"run_gen_eval.on_error should be 'diagnose', got {state.get('on_error')!r}"
        )

    def test_plan_routes_to_run_gen_eval(self, data: dict) -> None:
        """plan must route to run_gen_eval (not generate) in the thin wrapper."""
        state = data["states"].get("plan", {})
        assert state.get("next") == "run_gen_eval", (
            f"plan.next should be 'run_gen_eval', got {state.get('next')!r}"
        )

    def test_context_has_description(self, data: dict) -> None:
        """context block must define description; output_dir is runner-injected run_dir."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_design_tokens_context(self, data: dict) -> None:
        """context block must declare design_tokens_context; runner-injected at loop start."""
        ctx = data.get("context", {})
        assert "design_tokens_context" in ctx

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose state must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)


class TestP5jsSketchGeneratorLoop:
    """Structural tests for the p5js-sketch-generator FSM loop.

    After ENH-2161, p5js-sketch-generator.yaml is a from: generative-art stub.
    State-based tests use resolved_data (inheritance-resolved); stub fields use data.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "p5js-sketch-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        """Raw stub YAML — tests name, from, input_key."""
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.fixture
    def resolved_data(self) -> dict:
        """Inheritance-resolved YAML — tests inherited states and scalars."""
        from little_loops.fsm.fragments import resolve_fragments, resolve_inheritance

        raw = yaml.safe_load(self.LOOP_FILE.read_text())
        raw = resolve_inheritance(raw, BUILTIN_LOOPS_DIR)
        raw = resolve_fragments(raw, BUILTIN_LOOPS_DIR)
        return raw

    def test_required_top_level_fields(self, data: dict, resolved_data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "p5js-sketch-generator"
        assert data.get("input_key") == "description"
        assert resolved_data.get("initial") == "init"
        assert isinstance(resolved_data.get("states"), dict)

    def test_stub_inherits_from_generative_art(self, data: dict) -> None:
        """After ENH-2161, stub must declare from: generative-art."""
        assert data.get("from") == "generative-art"

    def test_required_states_exist(self, resolved_data: dict) -> None:
        """All required states must be present (via inheritance from generative-art)."""
        required = {"init", "plan", "generate", "evaluate", "score", "done", "failed"}
        actual = set(resolved_data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, resolved_data: dict) -> None:
        """done state must have terminal: true."""
        done_state = resolved_data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_evaluate_state_is_shell(self, resolved_data: dict) -> None:
        """evaluate state must use action_type: shell for the Playwright call."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("action_type") == "shell"

    def test_evaluate_state_has_output_contains_evaluator(self, resolved_data: dict) -> None:
        """evaluate state must have an output_contains evaluator with pattern CAPTURED."""
        state = resolved_data["states"].get("evaluate", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_evaluate_routes_to_score_on_yes(self, resolved_data: dict) -> None:
        """evaluate state must route to score when screenshot succeeds."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("on_yes") == "score"

    def test_evaluate_routes_to_generate_on_no(self, resolved_data: dict) -> None:
        """evaluate state must route back to generate when screenshot fails."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("on_no") == "generate"

    def test_evaluate_action_has_noloop_pause(self, resolved_data: dict) -> None:
        """evaluate action must call noLoop() before page.screenshot() for frame-exact capture."""
        state = resolved_data["states"].get("evaluate", {})
        action = state.get("action", "")
        assert "noLoop()" in action, f"evaluate.action must contain noLoop() call, got: {action!r}"

    def test_evaluate_action_has_loop_resume(self, resolved_data: dict) -> None:
        """evaluate action must call loop() after page.screenshot() to resume animation."""
        state = resolved_data["states"].get("evaluate", {})
        action = state.get("action", "")
        assert "loop()" in action, f"evaluate.action must contain loop() call, got: {action!r}"

    def test_evaluate_action_pause_before_screenshot(self, resolved_data: dict) -> None:
        """noLoop() must appear before page.screenshot() in the evaluate action."""
        state = resolved_data["states"].get("evaluate", {})
        action = state.get("action", "")
        noloop_pos = action.find("noLoop()")
        screenshot_pos = action.find("page.screenshot(")
        assert noloop_pos != -1 and screenshot_pos != -1
        assert noloop_pos < screenshot_pos, "noLoop() must come before page.screenshot()"

    def test_score_state_routes_to_done_on_pass(self, resolved_data: dict) -> None:
        """score state must route to done when all criteria pass."""
        state = resolved_data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_context_has_sample_frames(self, resolved_data: dict) -> None:
        """context block must define sample_frames for multi-frame capture."""
        ctx = resolved_data.get("context", {})
        assert "sample_frames" in ctx

    def test_max_steps_and_timeout_defined(self, resolved_data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert resolved_data.get("max_steps", 0) > 0
        assert resolved_data.get("timeout", 0) > 0


class TestPixiGenerativeArtLoop:
    """Structural tests for the pixi-generative-art FSM loop.

    After ENH-2161, pixi-generative-art.yaml is a from: generative-art stub that
    overrides plan/generate/evaluate/score states with PixiJS-specific logic.
    State-based tests use resolved_data; stub-specific tests use data.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "pixi-generative-art.yaml"

    @pytest.fixture
    def data(self) -> dict:
        """Raw stub YAML — tests name, from, pixi-specific state overrides."""
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.fixture
    def resolved_data(self) -> dict:
        """Inheritance-resolved YAML — tests inherited and overridden states."""
        from little_loops.fsm.fragments import resolve_fragments, resolve_inheritance

        raw = yaml.safe_load(self.LOOP_FILE.read_text())
        raw = resolve_inheritance(raw, BUILTIN_LOOPS_DIR)
        raw = resolve_fragments(raw, BUILTIN_LOOPS_DIR)
        return raw

    def test_required_top_level_fields(self, data: dict, resolved_data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "pixi-generative-art"
        assert data.get("input_key") == "description"
        assert resolved_data.get("initial") == "init"
        assert isinstance(resolved_data.get("states"), dict)

    def test_stub_inherits_from_generative_art(self, data: dict) -> None:
        """After ENH-2161, stub must declare from: generative-art."""
        assert data.get("from") == "generative-art"

    def test_required_states_exist(self, resolved_data: dict) -> None:
        """All required states must be present (mix of inherited and overridden)."""
        required = {"init", "plan", "generate", "evaluate", "score", "done", "failed"}
        actual = set(resolved_data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, resolved_data: dict) -> None:
        """done state must have terminal: true."""
        done_state = resolved_data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_evaluate_state_is_shell(self, resolved_data: dict) -> None:
        """evaluate state must use action_type: shell for the Playwright call."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("action_type") == "shell"

    def test_evaluate_state_has_output_contains_evaluator(self, resolved_data: dict) -> None:
        """evaluate state must have an output_contains evaluator with pattern CAPTURED."""
        state = resolved_data["states"].get("evaluate", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_evaluate_routes_to_score_on_yes(self, resolved_data: dict) -> None:
        """evaluate state must route to score when screenshot succeeds."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("on_yes") == "score"

    def test_evaluate_routes_to_generate_on_no(self, resolved_data: dict) -> None:
        """evaluate state must route back to generate when screenshot fails."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("on_no") == "generate"

    def test_evaluate_action_has_ticker_stop(self, data: dict) -> None:
        """evaluate override must call ticker.stop() for frame-exact capture."""
        state = data["states"].get("evaluate", {})
        action = state.get("action", "")
        assert "ticker?.stop()" in action, (
            f"evaluate.action must contain ticker?.stop() call, got: {action!r}"
        )

    def test_evaluate_action_has_ticker_start(self, data: dict) -> None:
        """evaluate override must call ticker.start() to resume animation after screenshot."""
        state = data["states"].get("evaluate", {})
        action = state.get("action", "")
        assert "ticker?.start()" in action, (
            f"evaluate.action must contain ticker?.start() call, got: {action!r}"
        )

    def test_evaluate_action_pause_before_screenshot(self, data: dict) -> None:
        """ticker.stop() must appear before page.screenshot() in the evaluate override."""
        state = data["states"].get("evaluate", {})
        action = state.get("action", "")
        stop_pos = action.find("ticker?.stop()")
        screenshot_pos = action.find("page.screenshot(")
        assert stop_pos != -1 and screenshot_pos != -1
        assert stop_pos < screenshot_pos, "ticker?.stop() must come before page.screenshot()"

    def test_generate_action_requires_pixiapp_exposure(self, data: dict) -> None:
        """generate override must instruct sketch to assign window.__pixiApp = app."""
        state = data["states"].get("generate", {})
        action = state.get("action", "")
        assert "window.__pixiApp = app" in action, (
            f"generate.action must require window.__pixiApp = app assignment, got: {action!r}"
        )

    def test_score_state_routes_to_done_on_pass(self, resolved_data: dict) -> None:
        """score state must route to done when all criteria pass."""
        state = resolved_data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_context_has_sample_frames(self, resolved_data: dict) -> None:
        """context block must define sample_frames for multi-frame capture."""
        ctx = resolved_data.get("context", {})
        assert "sample_frames" in ctx

    def test_max_steps_and_timeout_defined(self, resolved_data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert resolved_data.get("max_steps", 0) > 0
        assert resolved_data.get("timeout", 0) > 0


class TestPixiDataVizLoop:
    """Structural tests for the pixi-data-viz FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "pixi-data-viz.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "pixi-data-viz"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {"init", "plan", "generate", "evaluate", "score", "done", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_evaluate_state_is_shell(self, data: dict) -> None:
        """evaluate state must use action_type: shell for the Playwright call."""
        state = data["states"].get("evaluate", {})
        assert state.get("action_type") == "shell"

    def test_evaluate_state_has_output_contains_evaluator(self, data: dict) -> None:
        """evaluate state must have an output_contains evaluator with pattern CAPTURED."""
        state = data["states"].get("evaluate", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_evaluate_routes_to_score_on_yes(self, data: dict) -> None:
        """evaluate state must route to score when screenshot succeeds."""
        state = data["states"].get("evaluate", {})
        assert state.get("on_yes") == "score"

    def test_evaluate_routes_to_generate_on_no(self, data: dict) -> None:
        """evaluate state must route back to generate when screenshot fails."""
        state = data["states"].get("evaluate", {})
        assert state.get("on_no") == "generate"

    def test_evaluate_action_has_ticker_stop(self, data: dict) -> None:
        """evaluate action must call ticker.stop() before page.screenshot() for frame-exact capture."""
        state = data["states"].get("evaluate", {})
        action = state.get("action", "")
        assert "ticker?.stop()" in action, (
            f"evaluate.action must contain ticker?.stop() call, got: {action!r}"
        )

    def test_evaluate_action_has_ticker_start(self, data: dict) -> None:
        """evaluate action must call ticker.start() after page.screenshot() to resume animation."""
        state = data["states"].get("evaluate", {})
        action = state.get("action", "")
        assert "ticker?.start()" in action, (
            f"evaluate.action must contain ticker?.start() call, got: {action!r}"
        )

    def test_evaluate_action_pause_before_screenshot(self, data: dict) -> None:
        """ticker.stop() must appear before page.screenshot() in the evaluate action."""
        state = data["states"].get("evaluate", {})
        action = state.get("action", "")
        stop_pos = action.find("ticker?.stop()")
        screenshot_pos = action.find("page.screenshot(")
        assert stop_pos != -1 and screenshot_pos != -1
        assert stop_pos < screenshot_pos, "ticker?.stop() must come before page.screenshot()"

    def test_generate_action_requires_pixiapp_exposure(self, data: dict) -> None:
        """generate action must instruct sketch to assign window.__pixiApp = app."""
        state = data["states"].get("generate", {})
        action = state.get("action", "")
        assert "window.__pixiApp = app" in action, (
            f"generate.action must require window.__pixiApp = app assignment, got: {action!r}"
        )

    def test_encoding_clarity_hard_gated(self, data: dict) -> None:
        """score state action must hard-gate encoding_clarity at threshold 7."""
        state = data["states"].get("score", {})
        action = state.get("action", "")
        assert "encoding_clarity" in action and "7" in action, (
            "score.action must reference encoding_clarity hard gate at threshold 7"
        )

    def test_sample_frames_default_is_three_phase(self, data: dict) -> None:
        """sample_frames default must capture initial chrome, mid-transition, and settled state."""
        ctx = data.get("context", {})
        assert ctx.get("sample_frames") == "0,120,240", (
            "pixi-data-viz sample_frames must be '0,120,240' (chrome, mid-transition, settled)"
        )

    def test_score_state_routes_to_done_on_pass(self, data: dict) -> None:
        """score state must route to done when all criteria pass."""
        state = data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0


class TestAdversarialRedesignLoop:
    """Structural tests for the adversarial-redesign FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "adversarial-redesign.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "adversarial-redesign"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "concept"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "init",
            "seed",
            "critic",
            "regen",
            "score_gate",
            "svg_diff",
            "transcript",
            "done",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the run directory path."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "seed"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path using $(pwd)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, f"init.action must contain $(pwd), got: {action!r}"

    def test_seed_state_is_shell_with_output_contains(self, data: dict) -> None:
        """seed state must be a shell action with an output_contains evaluator."""
        state = data["states"].get("seed", {})
        assert state.get("action_type") == "shell"
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "SEEDED"

    def test_seed_calls_autofigure_wrapper(self, data: dict) -> None:
        """seed action must invoke autofigure_wrapper.py."""
        state = data["states"].get("seed", {})
        action = state.get("action", "")
        assert "autofigure_wrapper.py" in action

    def test_critic_state_is_prompt_with_output_contains(self, data: dict) -> None:
        """critic state must be a prompt action with an output_contains evaluator."""
        state = data["states"].get("critic", {})
        assert state.get("action_type") == "prompt"
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "NO_COMPLAINTS"

    def test_critic_routes_to_regen_on_complaints(self, data: dict) -> None:
        """critic state must route to regen when complaints exist."""
        state = data["states"].get("critic", {})
        assert state.get("on_no") == "regen"

    def test_regen_state_is_shell_with_output_contains(self, data: dict) -> None:
        """regen state must be a shell action with an output_contains evaluator."""
        state = data["states"].get("regen", {})
        assert state.get("action_type") == "shell"
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "REGENERATED"

    def test_regen_calls_autofigure_wrapper(self, data: dict) -> None:
        """regen action must invoke autofigure_wrapper.py."""
        state = data["states"].get("regen", {})
        action = state.get("action", "")
        assert "autofigure_wrapper.py" in action

    def test_regen_passes_critique_file(self, data: dict) -> None:
        """regen action must pass --critique-file to the wrapper."""
        state = data["states"].get("regen", {})
        action = state.get("action", "")
        assert "--critique-file" in action

    def test_regen_routes_to_score_gate(self, data: dict) -> None:
        """regen must route to score_gate on success."""
        state = data["states"].get("regen", {})
        assert state.get("on_yes") == "score_gate"

    def test_score_gate_is_shell_with_output_contains(self, data: dict) -> None:
        """score_gate must be a shell action with an output_contains evaluator."""
        state = data["states"].get("score_gate", {})
        assert state.get("action_type") == "shell"
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "IMPROVED"

    def test_score_gate_routes_to_svg_diff_on_improvement(self, data: dict) -> None:
        """score_gate must route to svg_diff when score improves."""
        state = data["states"].get("score_gate", {})
        assert state.get("on_yes") == "svg_diff"

    def test_score_gate_routes_to_transcript_on_stall(self, data: dict) -> None:
        """score_gate must exit to transcript when score stalls."""
        state = data["states"].get("score_gate", {})
        assert state.get("on_no") == "transcript"

    def test_svg_diff_is_shell_with_output_contains(self, data: dict) -> None:
        """svg_diff must be a shell action with an output_contains evaluator."""
        state = data["states"].get("svg_diff", {})
        assert state.get("action_type") == "shell"
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CONVERGED"

    def test_svg_diff_routes_to_critic_on_diverged(self, data: dict) -> None:
        """svg_diff must route back to critic when SVG is still changing."""
        state = data["states"].get("svg_diff", {})
        assert state.get("on_no") == "critic"

    def test_svg_diff_persists_iter_artifacts(self, data: dict) -> None:
        """svg_diff action must copy iter-N.svg and iter-N-critique.json per iteration."""
        state = data["states"].get("svg_diff", {})
        action = state.get("action", "")
        assert "iter-$ITER.svg" in action
        assert "iter-$ITER-critique.json" in action

    def test_shell_states_reference_run_dir(self, data: dict) -> None:
        """Shell states must reference captured.run_dir.output for isolation."""
        for name in ("seed", "regen", "score_gate", "svg_diff"):
            state = data["states"].get(name, {})
            action = state.get("action", "")
            assert "run_dir" in action, f"State '{name}' action must reference run_dir"

    def test_done_and_failed_are_terminal(self, data: dict) -> None:
        """done and failed states must be terminal."""
        assert data["states"].get("done", {}).get("terminal") is True
        assert data["states"].get("failed", {}).get("terminal") is True

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_context_has_concept(self, data: dict) -> None:
        """context block must declare concept; populated from loop_input."""
        ctx = data.get("context", {})
        assert "concept" in ctx


class TestSvgTextgradLoop:
    """Structural tests for the svg-textgrad FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "svg-textgrad.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "svg-textgrad"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "init",
            "plan",
            "generate",
            "screenshot",
            "check_capture_fails",
            "score",
            "verify_score",
            "track_best",
            "compute_gradient",
            "route_convergence",
            "append_gradient",
            "apply_gradient",
            "done",
            "diagnose",
            "failed",
            "seal_artifacts",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "plan"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_generate_does_not_reference_critique(self, data: dict) -> None:
        """generate state must NOT reference critique.md (reads only brief.md)."""
        state = data["states"].get("generate", {})
        action = state.get("action", "")
        assert "critique" not in action, "generate state must not reference critique.md"

    def test_score_routes_to_verify_score(self, data: dict) -> None:
        """score state must route to verify_score (external pass/fail evaluator)."""
        state = data["states"].get("score", {})
        assert state.get("next") == "verify_score"

    def test_compute_gradient_captures_gradient(self, data: dict) -> None:
        """compute_gradient state must capture its output as 'gradient'."""
        state = data["states"].get("compute_gradient", {})
        assert state.get("capture") == "gradient"

    def test_compute_gradient_routes_to_route_convergence(self, data: dict) -> None:
        """compute_gradient state must route to route_convergence (not append_gradient directly)."""
        state = data["states"].get("compute_gradient", {})
        assert state.get("next") == "route_convergence"

    def test_append_gradient_is_shell_routes_to_apply_gradient(self, data: dict) -> None:
        """append_gradient state must be a shell state that routes to apply_gradient."""
        state = data["states"].get("append_gradient", {})
        assert state.get("action_type") == "shell"
        assert state.get("next") == "apply_gradient"

    def test_apply_gradient_routes_to_generate(self, data: dict) -> None:
        """apply_gradient state must route back to generate."""
        state = data["states"].get("apply_gradient", {})
        assert state.get("next") == "generate"

    def test_context_has_description(self, data: dict) -> None:
        """context block must define description; output_dir is runner-injected run_dir."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_design_tokens_context(self, data: dict) -> None:
        """context block must declare design_tokens_context; runner-injected at loop start."""
        ctx = data.get("context", {})
        assert "design_tokens_context" in ctx

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_screenshot_state_is_shell(self, data: dict) -> None:
        """screenshot state must use action_type: shell for the Playwright CLI call."""
        state = data["states"].get("screenshot", {})
        assert state.get("action_type") == "shell"

    def test_screenshot_state_has_output_contains_evaluator(self, data: dict) -> None:
        """screenshot state must have an output_contains evaluator with pattern CAPTURED."""
        state = data["states"].get("screenshot", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_screenshot_routes_to_score_on_yes(self, data: dict) -> None:
        """screenshot state must route to score when screenshot succeeds."""
        state = data["states"].get("screenshot", {})
        assert state.get("on_yes") == "score"

    def test_screenshot_routes_to_check_capture_fails_on_no(self, data: dict) -> None:
        """screenshot state must route to check_capture_fails when Playwright fails to capture."""
        state = data["states"].get("screenshot", {})
        assert state.get("on_no") == "check_capture_fails"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_screenshot_action_has_stderr_redirect(self, data: dict) -> None:
        """screenshot action must redirect stderr to stdout so playwright errors surface."""
        state = data["states"].get("screenshot", {})
        action = state.get("action", "")
        assert "2>&1" in action, f"screenshot.action must contain 2>&1, got: {action!r}"

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose state must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    def test_screenshot_on_error_routes_to_check_capture_fails(self, data: dict) -> None:
        """screenshot state must route to check_capture_fails on error so Playwright failures don't stall."""
        state = data["states"].get("screenshot", {})
        assert state.get("on_error") == "check_capture_fails"

    def test_score_on_error_routes_to_failed(self, data: dict) -> None:
        """score state must route to diagnose on error to surface LLM failures explicitly."""
        state = data["states"].get("score", {})
        assert state.get("on_error") == "diagnose"

    def test_track_best_is_shell(self, data: dict) -> None:
        """track_best state must be a shell action."""
        state = data["states"].get("track_best", {})
        assert state.get("action_type") == "shell"

    def test_track_best_routes_to_compute_gradient(self, data: dict) -> None:
        """track_best state must route to compute_gradient."""
        state = data["states"].get("track_best", {})
        assert state.get("next") == "compute_gradient"

    def test_route_convergence_has_output_contains_evaluator(self, data: dict) -> None:
        """route_convergence must have an output_contains evaluator with pattern CONVERGED."""
        state = data["states"].get("route_convergence", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CONVERGED"

    def test_route_convergence_evaluator_source(self, data: dict) -> None:
        """route_convergence evaluate block must define source pointing to gradient capture."""
        state = data["states"].get("route_convergence", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("source") == "${captured.gradient.output}", (
            "route_convergence.evaluate must have "
            "'source: \"${captured.gradient.output}\"' so the evaluator "
            "reads the prior compute_gradient output, not this state's (empty) output"
        )

    def test_route_convergence_on_yes_routes_to_seal_artifacts(self, data: dict) -> None:
        """route_convergence must route to seal_artifacts when CONVERGED is detected."""
        state = data["states"].get("route_convergence", {})
        assert state.get("on_yes") == "seal_artifacts"

    def test_route_convergence_on_no_routes_to_append_gradient(self, data: dict) -> None:
        """route_convergence must route to append_gradient when not converged."""
        state = data["states"].get("route_convergence", {})
        assert state.get("on_no") == "append_gradient"

    def test_route_convergence_has_on_error(self, data: dict) -> None:
        """route_convergence must define on_error to handle evaluator failures gracefully."""
        state = data["states"].get("route_convergence", {})
        assert "on_error" in state

    def test_done_reports_scores_md_and_best_artifacts(self, data: dict) -> None:
        """done state action must reference scores.md, best.svg, and best-brief.md."""
        state = data["states"].get("done", {})
        action = state.get("action", "")
        assert "scores.md" in action, "done.action must reference scores.md"
        assert "best.svg" in action, "done.action must reference best.svg"
        assert "best-brief.md" in action, "done.action must reference best-brief.md"

    def test_init_touches_scores_md(self, data: dict) -> None:
        """init action must touch scores.md so compute_gradient can read it on iteration 1."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "scores.md" in action, (
            "init.action must touch scores.md to prevent read errors on iteration 1"
        )

    def test_verify_score_is_shell(self, data: dict) -> None:
        """verify_score state must use action_type: shell for external arithmetic."""
        state = data["states"].get("verify_score", {})
        assert state.get("action_type") == "shell"

    def test_verify_score_has_output_contains_evaluator(self, data: dict) -> None:
        """verify_score must have an output_contains evaluator with pattern SHELL_PASS."""
        state = data["states"].get("verify_score", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "SHELL_PASS"

    def test_verify_score_routes_to_seal_artifacts_on_yes(self, data: dict) -> None:
        """verify_score must route to seal_artifacts when weighted average meets pass_threshold."""
        state = data["states"].get("verify_score", {})
        assert state.get("on_yes") == "seal_artifacts"

    def test_verify_score_routes_to_track_best_on_no(self, data: dict) -> None:
        """verify_score must route to track_best on SHELL_ITERATE."""
        state = data["states"].get("verify_score", {})
        assert state.get("on_no") == "track_best"

    def test_verify_score_routes_to_track_best_on_error(self, data: dict) -> None:
        """verify_score must route to track_best on error so failures continue the loop."""
        state = data["states"].get("verify_score", {})
        assert state.get("on_error") == "track_best"

    def test_verify_score_appends_scores_md(self, data: dict) -> None:
        """verify_score action must append to scores.md (track_best no longer appends)."""
        state = data["states"].get("verify_score", {})
        action = state.get("action", "")
        assert "scores.md" in action, "verify_score.action must append to scores.md"

    def test_append_gradient_action_uses_temp_file(self, data: dict) -> None:
        """append_gradient must use temp-file pattern, not inline GRAD= assignment."""
        state = data["states"].get("append_gradient", {})
        action = state.get("action", "")
        assert 'GRAD="${captured.gradient.output}"' not in action, (
            "append_gradient.action must not assign gradient output to GRAD= directly "
            "(bash quoting breaks on backticks/colons in multi-line content)"
        )
        assert ".gradient_tmp.txt" in action, (
            "append_gradient.action must use a temp file to safely handle multi-line gradient output"
        )

    def test_seal_artifacts_state_exists(self, data: dict) -> None:
        """seal_artifacts state must exist in the loop."""
        assert "seal_artifacts" in data["states"]

    def test_seal_artifacts_is_shell(self, data: dict) -> None:
        """seal_artifacts state must use action_type: shell."""
        state = data["states"].get("seal_artifacts", {})
        assert state.get("action_type") == "shell"

    def test_seal_artifacts_routes_to_done(self, data: dict) -> None:
        """seal_artifacts state must route unconditionally to done."""
        state = data["states"].get("seal_artifacts", {})
        assert state.get("next") == "done"

    def test_generate_on_error_routes_to_diagnose(self, data: dict) -> None:
        """generate state must route to diagnose on error."""
        state = data["states"].get("generate", {})
        assert state.get("on_error") == "diagnose"

    def test_context_pass_threshold_is_7(self, data: dict) -> None:
        """context pass_threshold must be 7 (raised from 6 to catch per-criterion regressions)."""
        ctx = data.get("context", {})
        assert ctx.get("pass_threshold") == 7

    def test_context_has_min_per_criterion(self, data: dict) -> None:
        """context must define min_per_criterion for per-criterion floor check."""
        ctx = data.get("context", {})
        assert "min_per_criterion" in ctx

    def test_verify_score_action_uses_min_per_criterion(self, data: dict) -> None:
        """verify_score action must reference min_per_criterion for the per-criterion floor check."""
        state = data["states"].get("verify_score", {})
        action = state.get("action", "")
        assert "min_per_criterion" in action

    def test_seal_artifacts_action_copies_best_svg(self, data: dict) -> None:
        """seal_artifacts action must copy image.svg to best.svg and brief.md to best-brief.md."""
        state = data["states"].get("seal_artifacts", {})
        action = state.get("action", "")
        assert "best.svg" in action
        assert "best-brief.md" in action


class TestWorktreeHealthLoop:
    """Structural tests for the worktree-health FSM loop (ENH-1254)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "worktree-health.yaml"

    def _collect_action_text(self, data: dict) -> list[str]:
        """Recursively collect all action strings from an FSM data dict."""
        texts: list[str] = []
        for state_data in data.get("states", {}).values():
            action = state_data.get("action", "")
            if isinstance(action, str):
                texts.append(action)
        return texts

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_uses_porcelain_worktree_list(self, data: dict) -> None:
        """check_worktrees action must use git worktree list --porcelain."""
        combined = "\n".join(self._collect_action_text(data))
        assert "git worktree list --porcelain" in combined, (
            "worktree-health.yaml must use 'git worktree list --porcelain' to count orphans"
        )

    def test_does_not_grep_for_ll_worktree(self, data: dict) -> None:
        """check_worktrees action must not grep for 'll-worktree' (broken pattern)."""
        combined = "\n".join(self._collect_action_text(data))
        assert "ll-worktree" not in combined, (
            "worktree-health.yaml must not grep for 'll-worktree'; it matches no worktree names"
        )


class TestHtmlAnythingLoop:
    """Structural tests for the html-anything thin-wrapper FSM loop (FEAT-1541, ENH-1869)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "html-anything.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "html-anything"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """Thin wrapper must retain pre-generate states and add run_gen_eval delegation."""
        required = {"init", "plan", "run_gen_eval", "done", "diagnose", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_inline_generate_evaluate_score_states_removed(self, data: dict) -> None:
        """Inline generate, evaluate, and score states must be absent in the thin wrapper."""
        states = set(data["states"].keys())
        assert "generate" not in states, "generate state must be removed in thin wrapper"
        assert "evaluate" not in states, "evaluate state must be removed in thin wrapper"
        assert "score" not in states, "score state must be removed in thin wrapper"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "plan"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose state must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    def test_run_gen_eval_delegates_to_generator_evaluator(self, data: dict) -> None:
        """run_gen_eval must delegate to oracles/generator-evaluator oracle sub-loop."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("loop") == "oracles/generator-evaluator", (
            f"run_gen_eval.loop should be 'oracles/generator-evaluator', got {state.get('loop')!r}"
        )

    def test_run_gen_eval_with_bindings_present(self, data: dict) -> None:
        """run_gen_eval with: must bind run_dir, generate_prompt, rubric, pass_threshold."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_, (
            f"run_gen_eval.with must contain 'run_dir', got {list(with_.keys())}"
        )
        assert "generate_prompt" in with_, "run_gen_eval.with must contain 'generate_prompt'"
        assert "rubric" in with_, "run_gen_eval.with must contain 'rubric'"
        assert "pass_threshold" in with_, "run_gen_eval.with must contain 'pass_threshold'"

    def test_run_gen_eval_routes_to_done_on_yes(self, data: dict) -> None:
        """run_gen_eval must route to done when sub-loop succeeds (ALL_PASS)."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_yes") == "done", (
            f"run_gen_eval.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_run_gen_eval_routes_to_diagnose_on_failure(self, data: dict) -> None:
        """run_gen_eval must route to diagnose when sub-loop fails or exhausts iterations."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_no") == "diagnose", (
            f"run_gen_eval.on_no should be 'diagnose', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "diagnose", (
            f"run_gen_eval.on_error should be 'diagnose', got {state.get('on_error')!r}"
        )

    def test_plan_routes_to_run_gen_eval(self, data: dict) -> None:
        """plan must route to run_gen_eval (not generate) in the thin wrapper."""
        state = data["states"].get("plan", {})
        assert state.get("next") == "run_gen_eval", (
            f"plan.next should be 'run_gen_eval', got {state.get('next')!r}"
        )

    def test_plan_action_references_brief_and_rubric(self, data: dict) -> None:
        """plan state must write both brief.md and rubric.md in a single atomic state."""
        state = data["states"].get("plan", {})
        action = state.get("action", "")
        assert "brief.md" in action, "plan.action must write brief.md"
        assert "rubric.md" in action, "plan.action must write rubric.md"

    def test_rubric_binding_reads_rubric_dynamically(self, data: dict) -> None:
        """run_gen_eval rubric binding must reference rubric.md for per-criterion thresholds."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        rubric = with_.get("rubric", "")
        assert "rubric.md" in rubric, (
            "run_gen_eval.with.rubric must reference rubric.md to load per-criterion thresholds"
        )

    def test_context_pass_threshold_is_7(self, data: dict) -> None:
        """pass_threshold must be 7 — higher than SVG's 6 because platform constraints are binary."""
        ctx = data.get("context", {})
        assert ctx.get("pass_threshold") == 7

    def test_context_has_description(self, data: dict) -> None:
        """context block must define description; output_dir is runner-injected run_dir."""
        ctx = data.get("context", {})
        assert "description" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_design_tokens_context(self, data: dict) -> None:
        """context block must declare design_tokens_context; runner-injected at loop start."""
        ctx = data.get("context", {})
        assert "design_tokens_context" in ctx

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_done_reports_all_five_output_files(self, data: dict) -> None:
        """done state must reference all 5 output files: index.html, brief.md, rubric.md, critique.md, screenshot.png."""
        state = data["states"].get("done", {})
        action = state.get("action", "")
        assert "index.html" in action, "done.action must reference index.html"
        assert "brief.md" in action, "done.action must reference brief.md"
        assert "rubric.md" in action, "done.action must reference rubric.md"
        assert "critique.md" in action, "done.action must reference critique.md"
        assert "screenshot.png" in action, "done.action must reference screenshot.png"


class TestHitlCompareLoop:
    """Structural tests for the hitl-compare thin-wrapper FSM loop (FEAT-1545, ENH-1869)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "hitl-compare.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, and states fields."""
        assert data.get("name") == "hitl-compare"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "inputs"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """Thin wrapper must retain pre-generate states and add run_gen_eval delegation."""
        required = {"init", "identify", "prune", "run_gen_eval", "done", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_inline_generate_evaluate_score_states_removed(self, data: dict) -> None:
        """Inline generate, evaluate, and score states must be absent in the thin wrapper."""
        states = set(data["states"].keys())
        assert "generate" not in states, "generate state must be removed in thin wrapper"
        assert "evaluate" not in states, "evaluate state must be removed in thin wrapper"
        assert "score" not in states, "score state must be removed in thin wrapper"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "identify"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_run_gen_eval_delegates_to_generator_evaluator(self, data: dict) -> None:
        """run_gen_eval must delegate to oracles/generator-evaluator oracle sub-loop."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("loop") == "oracles/generator-evaluator", (
            f"run_gen_eval.loop should be 'oracles/generator-evaluator', got {state.get('loop')!r}"
        )

    def test_run_gen_eval_with_bindings_present(self, data: dict) -> None:
        """run_gen_eval with: must bind run_dir, generate_prompt, rubric, pass_threshold."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_, (
            f"run_gen_eval.with must contain 'run_dir', got {list(with_.keys())}"
        )
        assert "generate_prompt" in with_, "run_gen_eval.with must contain 'generate_prompt'"
        assert "rubric" in with_, "run_gen_eval.with must contain 'rubric'"
        assert "pass_threshold" in with_, "run_gen_eval.with must contain 'pass_threshold'"

    def test_run_gen_eval_routes_to_done_on_yes(self, data: dict) -> None:
        """run_gen_eval must route to done when sub-loop succeeds (ALL_PASS)."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_yes") == "done", (
            f"run_gen_eval.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_run_gen_eval_routes_to_failed_on_failure(self, data: dict) -> None:
        """run_gen_eval must route to failed when sub-loop fails or exhausts iterations."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_no") == "failed", (
            f"run_gen_eval.on_no should be 'failed', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "failed", (
            f"run_gen_eval.on_error should be 'failed', got {state.get('on_error')!r}"
        )

    def test_prune_routes_to_run_gen_eval(self, data: dict) -> None:
        """prune must route to run_gen_eval (not generate) in the thin wrapper."""
        state = data["states"].get("prune", {})
        assert state.get("next") == "run_gen_eval", (
            f"prune.next should be 'run_gen_eval', got {state.get('next')!r}"
        )

    def test_context_has_inputs(self, data: dict) -> None:
        """context block must define inputs; output_dir is runner-injected run_dir."""
        ctx = data.get("context", {})
        assert "inputs" in ctx
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_design_tokens_context(self, data: dict) -> None:
        """context block must declare design_tokens_context; runner-injected at loop start."""
        ctx = data.get("context", {})
        assert "design_tokens_context" in ctx

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_identify_action_writes_items_md(self, data: dict) -> None:
        """identify state action must reference items.md as the output file."""
        state = data["states"].get("identify", {})
        action = state.get("action", "")
        assert "items.md" in action, "identify.action must write items.md"

    def test_prune_action_writes_review_md(self, data: dict) -> None:
        """prune state action must reference review.md as the output file."""
        state = data["states"].get("prune", {})
        action = state.get("action", "")
        assert "review.md" in action, "prune.action must write review.md"

    def test_generate_prompt_binding_writes_index_html(self, data: dict) -> None:
        """run_gen_eval generate_prompt binding must reference index.html as the output file."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        generate_prompt = with_.get("generate_prompt", "")
        assert "index.html" in generate_prompt, "generate_prompt binding must write index.html"

    def test_generate_prompt_binding_has_write_in_affordance(self, data: dict) -> None:
        """generate_prompt binding must include write-in custom option affordance instructions (ENH-1604)."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        generate_prompt = with_.get("generate_prompt", "")
        assert "Write custom option" in generate_prompt, (
            "generate_prompt binding must contain write-in affordance instructions ('Write custom option')"
        )

    def test_rubric_binding_references_write_in(self, data: dict) -> None:
        """rubric binding must reference the write-in affordance (ENH-1604)."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        rubric = with_.get("rubric", "")
        assert "write-in" in rubric, (
            "run_gen_eval.with.rubric comparison_ergonomics must reference the write-in affordance"
        )

    def test_done_reports_all_output_files(self, data: dict) -> None:
        """done state must reference all key output files."""
        state = data["states"].get("done", {})
        action = state.get("action", "")
        assert "index.html" in action, "done.action must reference index.html"
        assert "items.md" in action, "done.action must reference items.md"
        assert "review.md" in action, "done.action must reference review.md"
        assert "critique.md" in action, "done.action must reference critique.md"
        assert "screenshot.png" in action, "done.action must reference screenshot.png"


class TestHitlMdLoop:
    """Structural tests for the hitl-md thin-wrapper FSM loop (FEAT-1613, ENH-1869)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "hitl-md.yaml"
    PROMPT_FILE = Path("prompts/hitl-md-generate.md")

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.fixture
    def generate_spec(self) -> str:
        """Full design specification combining the with: generate_prompt binding and the prompt file."""
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        yaml_data = yaml.safe_load(self.LOOP_FILE.read_text())
        with_ = yaml_data["states"].get("run_gen_eval", {}).get("with", {})
        generate_prompt = with_.get("generate_prompt", "")
        assert self.PROMPT_FILE.exists(), f"Prompt file not found: {self.PROMPT_FILE}"
        prompt_content = self.PROMPT_FILE.read_text()
        return generate_prompt + "\n" + prompt_content

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key (singular), and states fields."""
        assert data.get("name") == "hitl-md"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "input"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """Thin wrapper must retain pre-generate states and add run_gen_eval delegation."""
        required = {"init", "segment", "run_gen_eval", "finalize", "done", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_inline_generate_evaluate_score_states_removed(self, data: dict) -> None:
        """Inline generate, evaluate, and score states must be absent in the thin wrapper."""
        states = set(data["states"].keys())
        assert "generate" not in states, "generate state must be removed in thin wrapper"
        assert "evaluate" not in states, "evaluate state must be removed in thin wrapper"
        assert "score" not in states, "score state must be removed in thin wrapper"

    def test_init_state_is_shell_with_capture(self, data: dict) -> None:
        """init state must be a shell action that captures the timestamped run directory."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "segment"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_run_gen_eval_delegates_to_generator_evaluator(self, data: dict) -> None:
        """run_gen_eval must delegate to oracles/generator-evaluator oracle sub-loop."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("loop") == "oracles/generator-evaluator", (
            f"run_gen_eval.loop should be 'oracles/generator-evaluator', got {state.get('loop')!r}"
        )

    def test_run_gen_eval_with_bindings_present(self, data: dict) -> None:
        """run_gen_eval with: must bind run_dir, generate_prompt, rubric, pass_threshold."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        assert "run_dir" in with_, (
            f"run_gen_eval.with must contain 'run_dir', got {list(with_.keys())}"
        )
        assert "generate_prompt" in with_, "run_gen_eval.with must contain 'generate_prompt'"
        assert "rubric" in with_, "run_gen_eval.with must contain 'rubric'"
        assert "pass_threshold" in with_, "run_gen_eval.with must contain 'pass_threshold'"

    def test_run_gen_eval_routes_to_finalize_on_yes(self, data: dict) -> None:
        """run_gen_eval must route to finalize when sub-loop succeeds (ALL_PASS)."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_yes") == "finalize", (
            f"run_gen_eval.on_yes should be 'finalize', got {state.get('on_yes')!r}"
        )

    def test_run_gen_eval_routes_to_failed_on_failure(self, data: dict) -> None:
        """run_gen_eval must route to failed when sub-loop fails or exhausts iterations."""
        state = data["states"].get("run_gen_eval", {})
        assert state.get("on_no") == "failed", (
            f"run_gen_eval.on_no should be 'failed', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "failed", (
            f"run_gen_eval.on_error should be 'failed', got {state.get('on_error')!r}"
        )

    def test_segment_routes_to_run_gen_eval(self, data: dict) -> None:
        """segment must route to run_gen_eval (not generate) in the thin wrapper."""
        state = data["states"].get("segment", {})
        assert state.get("next") == "run_gen_eval", (
            f"segment.next should be 'run_gen_eval', got {state.get('next')!r}"
        )

    def test_finalize_state_routes_to_done(self, data: dict) -> None:
        """finalize state must route to done after copying the output HTML."""
        state = data["states"].get("finalize", {})
        assert state.get("on_yes") == "done"

    def test_context_has_input(self, data: dict) -> None:
        """context block must define input (singular); output_dir is runner-injected run_dir."""
        ctx = data.get("context", {})
        assert "input" in ctx, "context must have 'input' key (singular, not 'inputs')"
        assert "output_dir" not in ctx  # runner-injected run_dir replaces output_dir

    def test_context_has_design_tokens_context(self, data: dict) -> None:
        """context block must declare design_tokens_context; runner-injected at loop start."""
        ctx = data.get("context", {})
        assert "design_tokens_context" in ctx

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_segment_action_writes_segments_json(self, data: dict) -> None:
        """segment state action must reference segments.json as the output file."""
        state = data["states"].get("segment", {})
        action = state.get("action", "")
        assert "segments.json" in action, "segment.action must write segments.json"

    def test_generate_prompt_binding_writes_index_html(self, data: dict) -> None:
        """run_gen_eval generate_prompt binding must reference index.html as the output file."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        generate_prompt = with_.get("generate_prompt", "")
        assert "index.html" in generate_prompt, "generate_prompt binding must write index.html"

    def test_done_reports_all_output_files(self, data: dict) -> None:
        """done state must reference all key output files."""
        state = data["states"].get("done", {})
        action = state.get("action", "")
        assert "index.html" in action, "done.action must reference index.html"
        assert "segments.json" in action, "done.action must reference segments.json"
        assert "critique.md" in action, "done.action must reference critique.md"
        assert "screenshot.png" in action, "done.action must reference screenshot.png"

    # Simplified 2026-06: the ENH-1770 sensemaking layer (staged highlighting, density
    # slider, multi-channel saliency, schema-switching, minimap, full trust-calibration
    # friction) was removed. Only a lightweight always-on confidence cue is retained.

    def test_segment_action_emits_confidence(self, data: dict) -> None:
        """segment state must instruct the LLM to emit a per-segment confidence score —
        the single trust-calibration signal the renderer surfaces."""
        action = data["states"].get("segment", {}).get("action", "")
        assert "confidence" in action, (
            "segment.action must reference the 'confidence' field for the confidence cue"
        )

    def test_segment_action_drops_sensemaking_channels(self, data: dict) -> None:
        """segment state must NOT instruct the LLM to emit the removed multi-channel
        dimensions (anomaly, claim_type) or the length_normalized flag."""
        action = data["states"].get("segment", {}).get("action", "")
        for removed in ("anomaly", "claim_type", "length_normalized"):
            assert removed not in action, (
                f"segment.action must not reference removed sensemaking field '{removed}'"
            )

    def test_generate_action_has_confidence_cue(self, generate_spec: str) -> None:
        """generate spec must instruct the LLM to render the lightweight confidence cue:
        a dotted underline + a 'low confidence' badge on segments with confidence < 0.5."""
        spec = generate_spec.lower()
        assert "confidence" in spec, "generate spec must describe the confidence cue"
        assert "dotted" in spec, "generate spec must describe the dotted-underline confidence cue"
        assert "low confidence" in spec, "generate spec must describe the 'low confidence' badge"

    def test_generate_action_drops_sensemaking_layer(self, generate_spec: str) -> None:
        """generate spec must NOT instruct the LLM to build the removed ENH-1770 features
        (staged highlighting, density slider, multi-channel, schema-switching, minimap,
        click-to-reveal friction)."""
        spec = generate_spec.lower()
        for removed in (
            "intersectionobserver",
            "density",
            "schema-switch",
            "minimap",
            "localstorage",
            "click-to-reveal",
            "data-channel-anomaly",
        ):
            assert removed not in spec, (
                f"generate spec must not reference removed sensemaking feature '{removed}'"
            )

    def test_rubric_binding_has_confidence_cue_criterion(self, data: dict) -> None:
        """rubric binding must include the confidence_cue criterion."""
        state = data["states"].get("run_gen_eval", {})
        rubric = state.get("with", {}).get("rubric", "")
        assert "confidence_cue" in rubric, (
            "rubric binding must include the 'confidence_cue' criterion"
        )

    def test_rubric_binding_drops_sensemaking_criteria(self, data: dict) -> None:
        """rubric binding must NOT include the removed ENH-1770 criteria."""
        state = data["states"].get("run_gen_eval", {})
        rubric = state.get("with", {}).get("rubric", "")
        for removed in (
            "staged_highlighting",
            "density_control",
            "multi_channel_saliency",
            "schema_switching",
            "minimap_state_rail",
            "design_token_consistency",
        ):
            assert removed not in rubric, (
                f"rubric binding must not include removed criterion '{removed}'"
            )

    def test_rubric_binding_preserves_original_criteria(self, data: dict) -> None:
        """rubric binding must retain all 6 original criteria."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        rubric = with_.get("rubric", "")
        original_criteria = (
            "document_readability",
            "inline_highlighting",
            "affordance_overlay",
            "keyboard_reachability",
            "inline_constraint",
            "markdown_reconstruction",
        )
        for criterion in original_criteria:
            assert criterion in rubric, (
                f"rubric binding must retain the original '{criterion}' criterion"
            )

    def test_rubric_binding_uses_compound_all_pass_token(self, data: dict) -> None:
        """rubric binding must keep ALL_PASS as the compound gate token — per-criterion
        annotations must not collide with a bare 'PASS' token."""
        state = data["states"].get("run_gen_eval", {})
        with_ = state.get("with", {})
        rubric = with_.get("rubric", "")
        assert "ALL_PASS" in rubric, (
            "rubric binding must use the compound ALL_PASS token for gating"
        )


class TestRlCodingAgentLoop:
    """Structural tests for the rl-coding-agent FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rl-coding-agent.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "rl-coding-agent"
        assert data.get("initial") == "act"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "act",
            "refine",
            "observe",
            "score",
            "improve",
            "persist_reward",
            "done",
            "diagnose",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        assert data["states"].get("done", {}).get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        assert data["states"].get("failed", {}).get("terminal") is True

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose state must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    def test_score_error_routes_to_diagnose(self, data: dict) -> None:
        """score state convergence evaluator error route must target diagnose, not failed."""
        state = data["states"].get("score", {})
        route = state.get("route", {})
        assert route.get("error") == "diagnose", (
            f"score.route.error should be 'diagnose', got {route.get('error')!r}"
        )

    def test_act_state_uses_no_bash_default_operator(self, data: dict) -> None:
        """act state action must not contain bash ':-' default operator. BUG-2346.

        rl-coding-agent.yaml line 26 previously used ${context.target_files:-<all changed files>}
        which raises InterpolationError. The correct form is :default=.
        """
        import re

        action = data["states"].get("act", {}).get("action", "")
        bash_default = re.compile(r"(?<!\$)\$\{[^}]*:-[^}]*\}")
        matches = bash_default.findall(action)
        assert not matches, (
            f"rl-coding-agent act state contains bash ':-' default(s) {matches} — "
            "use ${context.key:default=val} instead (BUG-2346)."
        )


class TestAgentEvalImproveLoop:
    """Structural tests for the agent-eval-improve FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "agent-eval-improve.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "agent-eval-improve"
        assert data.get("initial") == "run_eval"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "run_eval",
            "score_results",
            "analyze_failures",
            "route_quality",
            "refine_config",
            "done",
            "diagnose",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        assert data["states"].get("done", {}).get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        assert data["states"].get("failed", {}).get("terminal") is True

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose state must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    def test_run_eval_retry_exhausted_routes_to_diagnose(self, data: dict) -> None:
        """run_eval.on_retry_exhausted must route to diagnose."""
        state = data["states"].get("run_eval", {})
        assert state.get("on_retry_exhausted") == "diagnose", (
            f"run_eval.on_retry_exhausted should be 'diagnose', got {state.get('on_retry_exhausted')!r}"
        )

    def test_score_results_retry_exhausted_routes_to_diagnose(self, data: dict) -> None:
        """score_results.on_retry_exhausted must route to diagnose."""
        state = data["states"].get("score_results", {})
        assert state.get("on_retry_exhausted") == "diagnose", (
            f"score_results.on_retry_exhausted should be 'diagnose', got {state.get('on_retry_exhausted')!r}"
        )

    def test_analyze_failures_retry_exhausted_routes_to_diagnose(self, data: dict) -> None:
        """analyze_failures.on_retry_exhausted must route to diagnose."""
        state = data["states"].get("analyze_failures", {})
        assert state.get("on_retry_exhausted") == "diagnose", (
            f"analyze_failures.on_retry_exhausted should be 'diagnose', got {state.get('on_retry_exhausted')!r}"
        )

    def test_analyze_failures_error_routes_to_diagnose(self, data: dict) -> None:
        """analyze_failures.on_error must route to diagnose."""
        state = data["states"].get("analyze_failures", {})
        assert state.get("on_error") == "diagnose", (
            f"analyze_failures.on_error should be 'diagnose', got {state.get('on_error')!r}"
        )

    def test_route_quality_error_routes_to_diagnose(self, data: dict) -> None:
        """route_quality convergence evaluator error route must target diagnose."""
        state = data["states"].get("route_quality", {})
        route = state.get("route", {})
        assert route.get("error") == "diagnose", (
            f"route_quality.route.error should be 'diagnose', got {route.get('error')!r}"
        )

    def test_refine_config_retry_exhausted_routes_to_diagnose(self, data: dict) -> None:
        """refine_config.on_retry_exhausted must route to diagnose."""
        state = data["states"].get("refine_config", {})
        assert state.get("on_retry_exhausted") == "diagnose", (
            f"refine_config.on_retry_exhausted should be 'diagnose', got {state.get('on_retry_exhausted')!r}"
        )


class TestRlPolicyLoop:
    """Structural tests for the rl-policy FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rl-policy.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "rl-policy"
        assert data.get("initial") == "act"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {"act", "observe", "score", "improve", "done", "diagnose", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_score_uses_convergence_gate_fragment(self, data: dict) -> None:
        """score state must use fragment: convergence_gate after ENH-1871 conversion."""
        state = data["states"].get("score", {})
        assert state.get("fragment") == "convergence_gate", (
            f"score.fragment should be 'convergence_gate', got {state.get('fragment')!r}"
        )

    def test_score_error_routes_to_diagnose(self, data: dict) -> None:
        """score state convergence evaluator error route must target diagnose."""
        state = data["states"].get("score", {})
        route = state.get("route", {})
        assert route.get("error") == "diagnose", (
            f"score.route.error should be 'diagnose', got {route.get('error')!r}"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        assert data["states"].get("done", {}).get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        assert data["states"].get("failed", {}).get("terminal") is True


class TestReadyToImplementGateLoop:
    """Tests that ready-to-implement-gate.yaml has correct structure and routing."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "ready-to-implement-gate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_prove_state_has_type_learning(self, data: dict) -> None:
        """prove state must use type: learning (ENH-1741)."""
        state = data["states"].get("prove", {})
        assert state.get("type") == "learning", (
            f"prove.type should be 'learning', got {state.get('type')!r}"
        )

    def test_prove_state_has_targets_csv_with_context_ref(self, data: dict) -> None:
        """prove state must use targets_csv referencing context.targets (ENH-1741)."""
        state = data["states"].get("prove", {})
        learning = state.get("learning", {})
        targets_csv = learning.get("targets_csv", "")
        assert "${context.targets}" in targets_csv, (
            f"prove.learning.targets_csv must reference '${{context.targets}}', got {targets_csv!r}"
        )
        assert learning.get("max_retries_expr") == "${context.max_retries}", (
            f"prove.learning.max_retries_expr must be '${{context.max_retries}}', "
            f"got {learning.get('max_retries_expr')!r}"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, (
            f"done.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_blocked_is_terminal(self, data: dict) -> None:
        """blocked state must have terminal: true."""
        state = data["states"].get("blocked", {})
        assert state.get("terminal") is True, (
            f"blocked.terminal should be True, got {state.get('terminal')!r}"
        )


class TestAssumptionFirewallLoop:
    """Tests that assumption-firewall.yaml has correct structure and routing."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "assumption-firewall.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_description_is_nonempty(self, data: dict) -> None:
        """Loop must have a non-empty description."""
        assert data.get("description"), "assumption-firewall must have a non-empty description"

    def test_run_gate_delegates_to_ready_to_implement_gate(self, data: dict) -> None:
        """run_gate must delegate to ready-to-implement-gate."""
        state = data["states"].get("run_gate", {})
        assert state.get("loop") == "ready-to-implement-gate", (
            f"run_gate.loop should be 'ready-to-implement-gate', got {state.get('loop')!r}"
        )

    def test_run_gate_with_contains_targets_and_max_retries(self, data: dict) -> None:
        """run_gate with: must bind targets and max_retries."""
        state = data["states"].get("run_gate", {})
        with_ = state.get("with", {})
        assert "targets" in with_, f"run_gate.with must contain 'targets', got {list(with_.keys())}"
        assert "max_retries" in with_, (
            f"run_gate.with must contain 'max_retries', got {list(with_.keys())}"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, (
            f"done.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_blocked_is_terminal(self, data: dict) -> None:
        """blocked state must have terminal: true."""
        state = data["states"].get("blocked", {})
        assert state.get("terminal") is True, (
            f"blocked.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_no_external_deps_is_terminal(self, data: dict) -> None:
        """no_external_deps state must have terminal: true."""
        state = data["states"].get("no_external_deps", {})
        assert state.get("terminal") is True, (
            f"no_external_deps.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_classify_assumptions_exists(self, data: dict) -> None:
        """classify_assumptions state must exist with action_type: prompt."""
        state = data["states"].get("classify_assumptions", {})
        assert state, "classify_assumptions state must exist"
        assert state.get("action_type") == "prompt", (
            f"classify_assumptions.action_type should be 'prompt', got {state.get('action_type')!r}"
        )

    def test_classify_assumptions_has_non_llm_evaluator(self, data: dict) -> None:
        """classify_assumptions must have a non-LLM evaluator (output_contains, satisfying MR-1)."""
        state = data["states"].get("classify_assumptions", {})
        ev = state.get("evaluate", {})
        assert ev.get("type") == "output_contains", (
            f"classify_assumptions.evaluate.type should be 'output_contains', got {ev.get('type')!r}"
        )
        assert "CLASSIFIED_JSON:" in str(ev.get("pattern", "")), (
            f"classify_assumptions evaluate pattern should contain CLASSIFIED_JSON:, got {ev.get('pattern')!r}"
        )

    def test_record_untestable_exists(self, data: dict) -> None:
        """record_untestable state must exist with action_type: shell."""
        state = data["states"].get("record_untestable", {})
        assert state, "record_untestable state must exist"
        assert state.get("action_type") == "shell", (
            f"record_untestable.action_type should be 'shell', got {state.get('action_type')!r}"
        )

    def test_record_untestable_calls_ll_action_explore_api_assume(self, data: dict) -> None:
        """record_untestable action must invoke ll-action explore-api with --assume."""
        state = data["states"].get("record_untestable", {})
        action = state.get("action", "")
        assert "ll-action" in action, (
            f"record_untestable.action should invoke ll-action, got {action!r}"
        )
        assert "explore-api" in action, (
            f"record_untestable.action should invoke explore-api, got {action!r}"
        )
        assert "--assume" in action, (
            f"record_untestable.action should use --assume flag, got {action!r}"
        )

    def test_flatten_testable_exists(self, data: dict) -> None:
        """flatten_testable state must exist (renamed from flatten_targets)."""
        state = data["states"].get("flatten_testable", {})
        assert state, "flatten_testable state must exist"
        assert state.get("action_type") == "shell", (
            f"flatten_testable.action_type should be 'shell', got {state.get('action_type')!r}"
        )

    def test_flatten_targets_removed(self, data: dict) -> None:
        """flatten_targets state must NOT exist (renamed to flatten_testable)."""
        assert "flatten_targets" not in data["states"], (
            "flatten_targets must be renamed to flatten_testable"
        )

    def test_parse_assumptions_routes_to_classify_assumptions(self, data: dict) -> None:
        """parse_assumptions on_yes must route to classify_assumptions."""
        state = data["states"].get("parse_assumptions", {})
        assert state.get("on_yes") == "classify_assumptions", (
            f"parse_assumptions.on_yes should be 'classify_assumptions', got {state.get('on_yes')!r}"
        )

    def test_classify_assumptions_routes_to_record_untestable(self, data: dict) -> None:
        """classify_assumptions on_yes and on_no must both route to record_untestable."""
        state = data["states"].get("classify_assumptions", {})
        assert state.get("on_yes") == "record_untestable", (
            f"classify_assumptions.on_yes should be 'record_untestable', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "record_untestable", (
            f"classify_assumptions.on_no should be 'record_untestable', got {state.get('on_no')!r}"
        )

    def test_record_untestable_routes_to_flatten_testable(self, data: dict) -> None:
        """record_untestable next must route to flatten_testable."""
        state = data["states"].get("record_untestable", {})
        assert state.get("next") == "flatten_testable", (
            f"record_untestable.next should be 'flatten_testable', got {state.get('next')!r}"
        )

    def test_flatten_testable_reads_from_classified(self, data: dict) -> None:
        """flatten_testable must read from captured.raw_classified, not captured.extracted."""
        state = data["states"].get("flatten_testable", {})
        action = state.get("action", "")
        assert "captured.raw_classified" in action, (
            f"flatten_testable.action should reference captured.raw_classified, got {action!r}"
        )
        assert "captured.extracted" not in action, (
            f"flatten_testable.action should NOT reference captured.extracted, got {action!r}"
        )

    def test_flatten_testable_routes_to_no_external_deps_and_run_gate(self, data: dict) -> None:
        """flatten_testable evaluator must route on_yes: no_external_deps, on_no: run_gate."""
        state = data["states"].get("flatten_testable", {})
        assert state.get("on_yes") == "no_external_deps", (
            f"flatten_testable.on_yes should be 'no_external_deps', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "run_gate", (
            f"flatten_testable.on_no should be 'run_gate', got {state.get('on_no')!r}"
        )

    def test_run_gate_targets_refers_to_flatten_testable(self, data: dict) -> None:
        """run_gate.with.targets must interpolate from captured.targets (from flatten_testable)."""
        state = data["states"].get("run_gate", {})
        with_ = state.get("with", {})
        targets_val = with_.get("targets", "")
        assert "${captured.targets.output}" in targets_val, (
            f"run_gate.with.targets should reference ${{captured.targets.output}}, got {targets_val!r}"
        )


class TestProofFirstTaskLoop:
    """Tests that proof-first-task.yaml has correct structure and routing."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "proof-first-task.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_description_is_nonempty(self, data: dict) -> None:
        """Loop must have a non-empty description."""
        assert data.get("description"), "proof-first-task must have a non-empty description"

    def test_check_issue_file_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_issue_file must use the shell_exit fragment."""
        state = data["states"].get("check_issue_file", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_issue_file.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_gate_delegates_to_assumption_firewall(self, data: dict) -> None:
        """gate must delegate to assumption-firewall sub-loop."""
        state = data["states"].get("gate", {})
        assert state.get("loop") == "assumption-firewall", (
            f"gate.loop should be 'assumption-firewall', got {state.get('loop')!r}"
        )

    def test_gate_captures_result(self, data: dict) -> None:
        """gate must capture output for post-gate routing check."""
        state = data["states"].get("gate", {})
        assert state.get("capture") == "gate_result", (
            f"gate.capture should be 'gate_result', got {state.get('capture')!r}"
        )

    def test_gate_with_binds_input(self, data: dict) -> None:
        """gate with: must bind input from context.issue_file."""
        state = data["states"].get("gate", {})
        with_ = state.get("with", {})
        assert "input" in with_, f"gate.with must contain 'input', got {list(with_.keys())}"

    def test_run_impl_uses_dynamic_loop(self, data: dict) -> None:
        """run_impl must use dynamic loop dispatch from context.impl_loop."""
        state = data["states"].get("run_impl", {})
        assert state.get("loop") == "${context.impl_loop}", (
            f"run_impl.loop should be '${{context.impl_loop}}', got {state.get('loop')!r}"
        )

    def test_run_impl_with_binds_input(self, data: dict) -> None:
        """run_impl with: must bind input from context.task."""
        state = data["states"].get("run_impl", {})
        with_ = state.get("with", {})
        assert "input" in with_, f"run_impl.with must contain 'input', got {list(with_.keys())}"

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, (
            f"done.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_blocked_is_terminal(self, data: dict) -> None:
        """blocked state must have terminal: true."""
        state = data["states"].get("blocked", {})
        assert state.get("terminal") is True, (
            f"blocked.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_impl_failed_is_terminal(self, data: dict) -> None:
        """impl_failed state must have terminal: true."""
        state = data["states"].get("impl_failed", {})
        assert state.get("terminal") is True, (
            f"impl_failed.terminal should be True, got {state.get('terminal')!r}"
        )


class TestAdoptThirdPartyApiLoop:
    """Tests that adopt-third-party-api.yaml has correct structure and routing."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "adopt-third-party-api.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_description_is_nonempty(self, data: dict) -> None:
        """Loop must have a non-empty description."""
        assert data.get("description"), "adopt-third-party-api must have a non-empty description"

    def test_prove_delegates_to_enumerate_and_prove_oracle(self, data: dict) -> None:
        """prove must delegate to oracles/enumerate-and-prove."""
        state = data["states"].get("prove", {})
        assert state.get("loop") == "oracles/enumerate-and-prove", (
            f"prove.loop should be 'oracles/enumerate-and-prove', got {state.get('loop')!r}"
        )

    def test_prove_with_contains_raw_enumeration_and_max_retries(self, data: dict) -> None:
        """prove with: must bind raw_enumeration and max_retries for the oracle."""
        state = data["states"].get("prove", {})
        with_ = state.get("with", {})
        assert "raw_enumeration" in with_, (
            f"prove.with must contain 'raw_enumeration', got {list(with_.keys())}"
        )
        assert "max_retries" in with_, (
            f"prove.with must contain 'max_retries', got {list(with_.keys())}"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, (
            f"done.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_failed_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True, (
            f"failed.terminal should be True, got {state.get('terminal')!r}"
        )


class TestIntegrateSdkLoop:
    """Tests that integrate-sdk.yaml has correct structure and routing."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "integrate-sdk.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_description_is_nonempty(self, data: dict) -> None:
        """Loop must have a non-empty description."""
        assert data.get("description"), "integrate-sdk must have a non-empty description"

    def test_prove_delegates_to_enumerate_and_prove_oracle(self, data: dict) -> None:
        """prove state must delegate to oracles/enumerate-and-prove."""
        state = data["states"].get("prove", {})
        assert state.get("loop") == "oracles/enumerate-and-prove", (
            f"prove.loop should be 'oracles/enumerate-and-prove', got {state.get('loop')!r}"
        )

    def test_prove_with_contains_raw_enumeration_and_max_retries(self, data: dict) -> None:
        """prove with: must bind raw_enumeration and max_retries for the oracle."""
        state = data["states"].get("prove", {})
        with_ = state.get("with", {})
        assert "raw_enumeration" in with_, (
            f"prove.with must contain 'raw_enumeration', got {list(with_.keys())}"
        )
        assert "max_retries" in with_, (
            f"prove.with must contain 'max_retries', got {list(with_.keys())}"
        )

    def test_verify_scaffold_uses_exit_code_evaluator(self, data: dict) -> None:
        """verify_scaffold must use exit_code evaluator, not LLM."""
        state = data["states"].get("verify_scaffold", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code", (
            f"verify_scaffold.evaluate.type should be 'exit_code' (non-LLM), "
            f"got {evaluate.get('type')!r}"
        )

    def test_prove_failure_routes_to_non_retry_state(self, data: dict) -> None:
        """prove on_failure must route to diagnose_and_block (not a retry loop)."""
        state = data["states"].get("prove", {})
        on_failure = state.get("on_failure")
        assert on_failure == "diagnose_and_block", (
            f"prove.on_failure should be 'diagnose_and_block', got {on_failure!r}"
        )
        # diagnose_and_block must NOT be terminal (it runs a prompt then routes to blocked)
        diagnose_state = data["states"].get("diagnose_and_block", {})
        assert not diagnose_state.get("terminal"), (
            "diagnose_and_block must not be terminal — it must run the diagnosis prompt "
            "then route to blocked"
        )
        # prove delegates to the oracle, not directly to ready-to-implement-gate
        assert state.get("loop") == "oracles/enumerate-and-prove", (
            f"prove.loop should be 'oracles/enumerate-and-prove', got {state.get('loop')!r}"
        )

    def test_blocked_is_terminal(self, data: dict) -> None:
        """blocked state must have terminal: true."""
        state = data["states"].get("blocked", {})
        assert state.get("terminal") is True, (
            f"blocked.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, (
            f"done.terminal should be True, got {state.get('terminal')!r}"
        )

    def test_scan_branches_to_both_enumerate_states(self, data: dict) -> None:
        """scan_existing_usage must branch to both enumerate_from_code and enumerate_from_docs."""
        state = data["states"].get("scan_existing_usage", {})
        assert state.get("on_yes") == "enumerate_from_code", (
            f"scan_existing_usage.on_yes should be 'enumerate_from_code', "
            f"got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "enumerate_from_docs", (
            f"scan_existing_usage.on_no should be 'enumerate_from_docs', got {state.get('on_no')!r}"
        )


class TestDeadCodeCleanupLoop:
    """Structural tests for the dead-code-cleanup FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "dead-code-cleanup.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "dead-code-cleanup"
        assert data.get("initial") == "scan"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {
            "scan",
            "count_findings",
            "remove_code",
            "verify_tests",
            "revert_and_scan",
            "commit",
            "done",
        }
        assert not required - set(data["states"].keys())

    def test_commit_uses_ll_commit_fragment(self, data: dict) -> None:
        assert data["states"]["commit"].get("fragment") == "ll_commit"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True


class TestTestCoverageImprovementLoop:
    """Structural tests for the test-coverage-improvement FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "test-coverage-improvement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "test-coverage-improvement"
        assert data.get("initial") == "measure"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {"measure", "identify_gaps", "write_tests", "verify_tests", "commit", "done"}
        assert not required - set(data["states"].keys())

    def test_commit_uses_ll_commit_fragment(self, data: dict) -> None:
        assert data["states"]["commit"].get("fragment") == "ll_commit"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True


class TestBacklogFlowOptimizerLoop:
    """Structural tests for the backlog-flow-optimizer FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "backlog-flow-optimizer.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "backlog-flow-optimizer"
        assert data.get("initial") == "measure"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {"measure", "diagnose", "commit", "done"}
        assert not required - set(data["states"].keys())

    def test_commit_uses_ll_commit_fragment(self, data: dict) -> None:
        assert data["states"]["commit"].get("fragment") == "ll_commit"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True


class TestIssueStalenessReviewLoop:
    """Structural tests for the issue-staleness-review FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "issue-staleness-review.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "issue-staleness-review"
        assert data.get("initial") == "find_stale"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {
            "find_stale",
            "review_issue",
            "triage",
            "close_issue",
            "reprioritize",
            "commit",
            "done",
        }
        assert not required - set(data["states"].keys())

    def test_commit_uses_ll_commit_fragment(self, data: dict) -> None:
        assert data["states"]["commit"].get("fragment") == "ll_commit"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True


class TestDocsSyncLoop:
    """Structural tests for the docs-sync FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "docs-sync.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "docs-sync"
        assert data.get("initial") == "verify_docs"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {"verify_docs", "check_links", "route_results", "fix_docs", "commit", "done"}
        assert not required - set(data["states"].keys())

    def test_commit_uses_ll_commit_fragment(self, data: dict) -> None:
        assert data["states"]["commit"].get("fragment") == "ll_commit"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True


class TestIncrementalRefactorLoop:
    """Structural tests for the incremental-refactor FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "incremental-refactor.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "incremental-refactor"
        assert data.get("initial") == "plan_steps"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        required = {
            "plan_steps",
            "execute_step",
            "verify_tests",
            "commit_step",
            "check_complete",
            "revert",
            "replan",
            "done",
        }
        assert not required - set(data["states"].keys())

    def test_commit_step_uses_ll_commit_fragment(self, data: dict) -> None:
        assert data["states"]["commit_step"].get("fragment") == "ll_commit"

    def test_commit_step_keeps_slash_command_action_type(self, data: dict) -> None:
        assert data["states"]["commit_step"].get("action_type") == "slash_command"

    def test_done_state_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True


class TestGeneratorEvaluatorOracle:
    """Structural tests for the generator-evaluator oracle sub-loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/generator-evaluator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "generator-evaluator"
        assert data.get("initial") == "generate"
        assert isinstance(data.get("states"), dict)

    def test_has_parameters_block(self, data: dict) -> None:
        params = data.get("parameters", {})
        assert "run_dir" in params, "parameters block must declare run_dir"
        assert "generate_prompt" in params, "parameters block must declare generate_prompt"
        assert "artifact_path" in params, "parameters block must declare artifact_path"
        assert params["run_dir"].get("required") is True
        assert params["generate_prompt"].get("required") is True
        assert params["artifact_path"].get("required") is not True, "artifact_path must be optional"

    def test_required_states_exist(self, data: dict) -> None:
        states = data.get("states", {})
        for name in ("generate", "evaluate", "snapshot", "score", "done"):
            assert name in states, f"required state '{name}' missing"

    def test_evaluate_uses_playwright_screenshot_fragment(self, data: dict) -> None:
        state = data["states"].get("evaluate", {})
        assert state.get("fragment") == "playwright_screenshot", (
            "evaluate state must use fragment: playwright_screenshot"
        )

    def test_evaluate_routes_to_snapshot_on_all_outcomes(self, data: dict) -> None:
        state = data["states"].get("evaluate", {})
        assert state.get("on_yes") == "snapshot"
        assert state.get("on_no") == "snapshot"
        assert state.get("on_error") == "snapshot"

    def test_score_uses_output_contains_all_pass(self, data: dict) -> None:
        state = data["states"].get("score", {})
        assert state.get("fragment") == "ll_rubric_score"

    def test_score_routes_to_done_on_yes(self, data: dict) -> None:
        state = data["states"].get("score", {})
        assert state.get("on_yes") == "done"

    def test_done_is_terminal(self, data: dict) -> None:
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, "done.terminal should be True"

    def test_imports_harness_yaml(self, data: dict) -> None:
        imports = data.get("import", [])
        assert "lib/harness.yaml" in imports, "must import lib/harness.yaml"


class TestGeneratorEvaluatorCliOracle:
    """Structural tests for the generator-evaluator-cli oracle sub-loop (FEAT-2269).

    generator-evaluator-cli.yaml uses from: generator-evaluator inheritance.
    State-based tests use resolved_data (inheritance + fragment resolved);
    stub-level fields use data.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/generator-evaluator-cli.yaml"

    @pytest.fixture
    def data(self) -> dict:
        """Raw stub YAML — tests name, from, visibility."""
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.fixture
    def resolved_data(self) -> dict:
        """Inheritance + fragment resolved YAML — tests inherited and overridden states."""
        from little_loops.fsm.fragments import resolve_fragments, resolve_inheritance

        raw = yaml.safe_load(self.LOOP_FILE.read_text())
        raw = resolve_inheritance(raw, BUILTIN_LOOPS_DIR / "oracles")
        raw = resolve_fragments(raw, BUILTIN_LOOPS_DIR)
        return raw

    def test_required_top_level_fields(self, data: dict) -> None:
        """Oracle stub must declare name and from: generator-evaluator."""
        assert data.get("name") == "generator-evaluator-cli"
        assert data.get("from") == "generator-evaluator", (
            "generator-evaluator-cli must inherit from generator-evaluator (bare name)"
        )
        assert data.get("visibility") == "internal"

    def test_stub_declares_render_command_parameter(self, data: dict) -> None:
        """Stub must add render_command as a required parameter."""
        params = data.get("parameters", {})
        assert "render_command" in params, "stub must declare render_command parameter"
        assert params["render_command"].get("required") is True

    def test_resolved_has_generator_evaluator_states(self, resolved_data: dict) -> None:
        """After inheritance resolution, all parent states must be present."""
        states = resolved_data.get("states", {})
        for name in ("generate", "evaluate", "snapshot", "score", "done", "failed"):
            assert name in states, f"inherited state '{name}' missing after resolution"

    def test_resolved_has_all_parameters(self, resolved_data: dict) -> None:
        """After inheritance resolution, both parent and child parameters must exist."""
        params = resolved_data.get("parameters", {})
        for name in ("run_dir", "generate_prompt", "artifact_path"):
            assert name in params, f"inherited parameter '{name}' missing"
        assert "render_command" in params, "render_command parameter must survive resolution"
        assert params["run_dir"].get("required") is True
        assert params["generate_prompt"].get("required") is True
        assert params["render_command"].get("required") is True

    def test_resolved_evaluate_is_shell_type(self, resolved_data: dict) -> None:
        """evaluate state override must be a shell action after resolution."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("action_type") == "shell", (
            "evaluate state must be action_type: shell in CLI oracle"
        )

    def test_resolved_evaluate_has_output_contains_captured(self, resolved_data: dict) -> None:
        """evaluate state must have an output_contains evaluator with pattern CAPTURED."""
        state = resolved_data["states"].get("evaluate", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "CAPTURED"

    def test_resolved_evaluate_routes_to_failed_on_no(self, resolved_data: dict) -> None:
        """evaluate.on_no must route to failed (not snapshot) — render failure is terminal."""
        state = resolved_data["states"].get("evaluate", {})
        assert state.get("on_no") == "failed", (
            f"evaluate.on_no should be 'failed', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "failed", (
            f"evaluate.on_error should be 'failed', got {state.get('on_error')!r}"
        )

    def test_resolved_snapshot_copies_views_png(self, resolved_data: dict) -> None:
        """snapshot state action must iterate over views/*.png (multi-view aware)."""
        state = resolved_data["states"].get("snapshot", {})
        action = state.get("action", "")
        assert "views/" in action, "snapshot.action must reference views/ directory"
        assert "*.png" in action, "snapshot.action must glob *.png for multi-view copy"

    def test_resolved_snapshot_routes_to_score(self, resolved_data: dict) -> None:
        """snapshot must still route to score after override."""
        state = resolved_data["states"].get("snapshot", {})
        assert state.get("next") == "score", (
            f"snapshot.next should be 'score', got {state.get('next')!r}"
        )

    def test_done_is_terminal(self, resolved_data: dict) -> None:
        """done.terminal should be True (inherited from parent)."""
        state = resolved_data["states"].get("done", {})
        assert state.get("terminal") is True


class TestEnumerateAndProveOracle:
    """Structural tests for the enumerate-and-prove oracle sub-loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/enumerate-and-prove.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "enumerate-and-prove"
        assert data.get("initial") == "parse_enumeration"
        assert isinstance(data.get("states"), dict)

    def test_has_parameters_block(self, data: dict) -> None:
        params = data.get("parameters", {})
        assert "raw_enumeration" in params, "parameters block must declare raw_enumeration"
        assert params["raw_enumeration"].get("required") is True
        assert "max_retries" in params, "parameters block must declare max_retries"
        assert params["max_retries"].get("required") is not True, "max_retries must be optional"

    def test_required_states_exist(self, data: dict) -> None:
        states = data.get("states", {})
        for name in ("parse_enumeration", "flatten", "prove", "done", "failed"):
            assert name in states, f"required state '{name}' missing"

    def test_parse_enumeration_uses_parse_tagged_json_fragment(self, data: dict) -> None:
        state = data["states"].get("parse_enumeration", {})
        assert state.get("fragment") == "parse_tagged_json", (
            "parse_enumeration state must use fragment: parse_tagged_json"
        )

    def test_prove_delegates_to_ready_to_implement_gate(self, data: dict) -> None:
        """Oracle's prove state delegates to ready-to-implement-gate (not to itself)."""
        state = data["states"].get("prove", {})
        assert state.get("loop") == "ready-to-implement-gate", (
            f"prove.loop should be 'ready-to-implement-gate', got {state.get('loop')!r}"
        )

    def test_prove_with_contains_targets_and_max_retries(self, data: dict) -> None:
        state = data["states"].get("prove", {})
        with_ = state.get("with", {})
        assert "targets" in with_, f"prove.with must contain 'targets', got {list(with_.keys())}"
        assert "max_retries" in with_, (
            f"prove.with must contain 'max_retries', got {list(with_.keys())}"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, "done.terminal should be True"

    def test_failed_is_terminal(self, data: dict) -> None:
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True, "failed.terminal should be True"

    def test_imports_common_yaml(self, data: dict) -> None:
        imports = data.get("import", [])
        assert "lib/common.yaml" in imports, "must import lib/common.yaml"


class TestImplementIssueChainOracle:
    """Structural tests for the implement-issue-chain oracle sub-loop (ENH-1874)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/implement-issue-chain.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "implement-issue-chain"
        assert data.get("initial") == "get_passed_issues"
        assert isinstance(data.get("states"), dict)

    def test_has_parameters_block(self, data: dict) -> None:
        params = data.get("parameters", {})
        assert "caller_prefix" in params, "parameters block must declare caller_prefix"
        assert params["caller_prefix"].get("required") is True

    def test_shared_state_ok_not_set(self, data: dict) -> None:
        assert data.get("shared_state_ok") is not True, (
            "shared_state_ok must not be set after ENH-2097 run_dir migration"
        )

    def test_required_states_exist(self, data: dict) -> None:
        states = data.get("states", {})
        for name in (
            "get_passed_issues",
            "implement_next",
            "go_no_go",
            "implement_issue",
            "done",
        ):
            assert name in states, f"required state '{name}' missing"

    def test_done_is_terminal(self, data: dict) -> None:
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, "done.terminal should be True"

    def test_no_unreachable_failed_state(self, data: dict) -> None:
        """All failure paths drain to done; an unreachable failed terminal was removed."""
        assert "failed" not in data["states"], (
            "implement-issue-chain intentionally has no failed state; all error paths route to done"
        )

    def test_imports_common_yaml(self, data: dict) -> None:
        imports = data.get("import", [])
        assert "lib/common.yaml" in imports, "must import lib/common.yaml"

    def test_get_passed_issues_reads_recursive_refine_outputs(self, data: dict) -> None:
        """get_passed_issues must read both recursive-refine output files."""
        state = data["states"].get("get_passed_issues", {})
        action = state.get("action", "")
        assert "recursive-refine-passed.txt" in action
        assert "recursive-refine-skipped.txt" in action

    def test_get_passed_issues_uses_caller_prefix(self, data: dict) -> None:
        """get_passed_issues must use ${context.caller_prefix} instead of a hardcoded prefix."""
        state = data["states"].get("get_passed_issues", {})
        action = state.get("action", "")
        assert "${context.caller_prefix}" in action

    def test_implement_next_captures_impl_id(self, data: dict) -> None:
        """implement_next must capture as 'impl_id' for implement_issue to reference."""
        state = data["states"].get("implement_next", {})
        assert state.get("capture") == "impl_id"

    def test_implement_next_uses_caller_prefix(self, data: dict) -> None:
        """implement_next must use ${context.caller_prefix} for the impl-queue path."""
        state = data["states"].get("implement_next", {})
        action = state.get("action", "")
        assert "${context.caller_prefix}" in action

    def test_impl_queue_file_uses_run_dir(self, data: dict) -> None:
        """Impl queue file must use ${context.run_dir} with caller_prefix interpolation."""
        states = data.get("states", {})
        found = False
        for state_data in states.values():
            action = state_data.get("action", "")
            if "${context.caller_prefix}-impl-queue" in action:
                found = True
                assert "${context.run_dir}" in action
        assert found, (
            "No state references ${context.caller_prefix}-impl-queue in ${context.run_dir}"
        )

    def test_go_no_go_uses_ll_action_invoke(self, data: dict) -> None:
        """go_no_go must call ll-action via the invoke subcommand."""
        state = data["states"].get("go_no_go", {})
        action = state.get("action", "")
        assert "ll-action invoke" in action, (
            "go_no_go action must use 'll-action invoke', not 'll-action go-no-go'"
        )
        assert "--check" in action, "go_no_go action must pass --check flag"

    def test_implement_issue_uses_impl_id(self, data: dict) -> None:
        """implement_issue action must reference captured.impl_id.output."""
        state = data["states"].get("implement_issue", {})
        action = state.get("action", "")
        assert "${captured.impl_id.output}" in action

    def test_implement_issue_has_completed_guard(self, data: dict) -> None:
        """implement_issue must skip ll-auto when the issue is already in completed/."""
        state = data["states"].get("implement_issue", {})
        action = state.get("action", "")
        assert "completed" in action, "implement_issue action must check .issues/completed/"
        assert "exit 0" in action, (
            "implement_issue action must exit 0 when issue is already completed"
        )

    def test_implement_issue_routes_to_implement_next(self, data: dict) -> None:
        """implement_issue must loop back to implement_next to drain the queue."""
        state = data["states"].get("implement_issue", {})
        assert state.get("next") == "implement_next"


class TestResearchCoverageOracle:
    """Structural tests for the research-coverage oracle sub-loop (ENH-1876)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/research-coverage.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "research-coverage"
        assert data.get("initial") == "generate_queries"
        assert isinstance(data.get("states"), dict)

    def test_has_parameters_block(self, data: dict) -> None:
        params = data.get("parameters", {})
        assert "run_dir" in params, "parameters block must declare run_dir"
        assert params["run_dir"].get("required") is True
        assert "topic" in params, "parameters block must declare topic"
        assert params["topic"].get("required") is True
        assert "source_filter" in params, "parameters block must declare source_filter"
        assert params["source_filter"].get("required") is not True, "source_filter must be optional"
        assert "academic_mode" in params, "parameters block must declare academic_mode"
        assert params["academic_mode"].get("required") is not True, "academic_mode must be optional"

    def test_has_on_handoff_spawn(self, data: dict) -> None:
        assert data.get("on_handoff") == "spawn"

    def test_required_states_exist(self, data: dict) -> None:
        states = data.get("states", {})
        for name in (
            "generate_queries",
            "search_web",
            "evaluate_sources",
            "score_coverage",
            "plan_next",
            "synthesize",
            "done",
        ):
            assert name in states, f"required state '{name}' missing"

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

    def test_score_coverage_has_on_error(self, data: dict) -> None:
        state = data["states"]["score_coverage"]
        assert "on_error" in state, "score_coverage must have on_error for graceful degradation"

    def test_done_is_terminal(self, data: dict) -> None:
        state = data["states"].get("done", {})
        assert state.get("terminal") is True, "done.terminal should be True"

    def test_imports_common_yaml(self, data: dict) -> None:
        imports = data.get("import", [])
        assert "lib/common.yaml" in imports, "must import lib/common.yaml"

    def test_synthesize_supports_bibtex_for_academic_mode(self, data: dict) -> None:
        action = data["states"]["synthesize"].get("action", "")
        assert "## BibTeX" in action, "synthesize must support BibTeX section for academic_mode"
        assert "@misc" in action, "synthesize BibTeX must use @misc{...} entries"

    def test_evaluate_sources_supports_recency_axis(self, data: dict) -> None:
        action = data["states"]["evaluate_sources"].get("action", "")
        assert "recency" in action.lower(), (
            "evaluate_sources must support recency scoring axis for academic_mode"
        )

    def test_search_web_uses_source_filter(self, data: dict) -> None:
        action = data["states"]["search_web"].get("action", "")
        assert "source_filter" in action, (
            "search_web must reference source_filter parameter for site constraint"
        )


class TestMigrateSdkVersionLoop:
    """Structural tests for the migrate-sdk-version FSM loop."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "migrate-sdk-version.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, and states fields."""
        assert data.get("name") == "migrate-sdk-version"
        assert data.get("initial") == "list_stale"
        assert isinstance(data.get("states"), dict)

    def test_category_is_api_adoption(self, data: dict) -> None:
        """Loop must be in the api-adoption category."""
        assert data.get("category") == "api-adoption"

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {
            "list_stale",
            "reprove_next",
            "classify_outcome",
            "apply_update",
            "advance_queue",
            "prepare_report_path",
            "build_report",
            "done",
            "done_empty",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_done_empty_state_is_terminal(self, data: dict) -> None:
        """done_empty state must have terminal: true."""
        state = data["states"].get("done_empty", {})
        assert state.get("terminal") is True

    def test_classify_outcome_uses_output_contains(self, data: dict) -> None:
        """classify_outcome must use output_contains evaluator with CLASSIFY_JSON: pattern."""
        state = data["states"].get("classify_outcome", {})
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_contains"
        assert "CLASSIFY_JSON:" in evaluate.get("pattern", "")

    def test_list_stale_uses_run_dir(self, data: dict) -> None:
        """list_stale action must write queue to ${context.run_dir} for per-run isolation."""
        action = data["states"].get("list_stale", {}).get("action", "")
        assert "${context.run_dir}" in action

    def test_prepare_report_path_uses_run_dir(self, data: dict) -> None:
        """prepare_report_path must use ${context.run_dir} for per-run isolation."""
        action = data["states"].get("prepare_report_path", {}).get("action", "")
        assert "${context.run_dir}" in action

    def test_prepare_report_path_captures_report_path(self, data: dict) -> None:
        """prepare_report_path must capture: report_path for build_report."""
        state = data["states"].get("prepare_report_path", {})
        assert state.get("capture") == "report_path"

    def test_build_report_uses_llm_gate_fragment(self, data: dict) -> None:
        """build_report must use llm_gate fragment."""
        state = data["states"].get("build_report", {})
        assert state.get("fragment") == "llm_gate"

    def test_build_report_references_captured_report_path(self, data: dict) -> None:
        """build_report must reference ${captured.report_path.output}."""
        action = data["states"].get("build_report", {}).get("action", "")
        assert "${captured.report_path.output}" in action

    def test_max_steps_and_timeout(self, data: dict) -> None:
        """Loop must define max_steps and timeout."""
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_reprove_next_captures_reprove(self, data: dict) -> None:
        """reprove_next must capture: reprove so classify_outcome can access old/new records."""
        state = data["states"].get("reprove_next", {})
        assert state.get("capture") == "reprove"


class TestApplyResearchLoop:
    """Structural tests for the apply-research built-in loop (FEAT-2024)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "apply-research.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "apply-research"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "files"
        assert data.get("required_inputs") == ["files"]
        assert isinstance(data.get("states"), dict)

    def test_category_is_research(self, data: dict) -> None:
        assert data.get("category") == "research"

    def test_context_defaults(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert "files" in ctx
        assert "relevance_threshold" in ctx
        assert "max_issues_per_file" in ctx

    def test_required_states_exist(self, data: dict) -> None:
        states = data.get("states", {})
        for name in (
            "init",
            "load_context",
            "read_file",
            "extract_and_score",
            "validate_scores",
            "filter_items",
            "synthesize_recommendations",
            "capture_issues",
            "verify_captures",
            "next_file",
            "report",
            "failed",
        ):
            assert name in states, f"required state '{name}' missing"

    def test_init_uses_exit_code_evaluator(self, data: dict) -> None:
        state = data["states"]["init"]
        assert state.get("evaluate", {}).get("type") == "exit_code"
        assert state.get("on_yes") == "load_context"
        assert state.get("on_no") == "failed"

    def test_validate_scores_is_non_llm_evaluator(self, data: dict) -> None:
        state = data["states"]["validate_scores"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_numeric"
        assert evaluator.get("operator") == "ge"
        assert state.get("action_type") == "shell"

    def test_filter_items_uses_output_numeric(self, data: dict) -> None:
        state = data["states"]["filter_items"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_numeric"
        assert evaluator.get("operator") == "ge"
        assert state.get("action_type") == "shell"

    def test_verify_captures_is_non_llm_evaluator(self, data: dict) -> None:
        state = data["states"]["verify_captures"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_numeric"
        assert evaluator.get("operator") == "ge"
        assert state.get("action_type") == "shell"

    def test_extract_and_score_uses_relevance_sentinel(self, data: dict) -> None:
        state = data["states"]["extract_and_score"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "RELEVANCE_SCORES:"
        assert state.get("action_type") == "prompt"

    def test_synthesize_uses_recommendation_sentinel(self, data: dict) -> None:
        state = data["states"]["synthesize_recommendations"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains"
        assert evaluator.get("pattern") == "RECOMMENDATION:"
        assert state.get("action_type") == "prompt"

    def test_read_file_routes_to_extract_or_report(self, data: dict) -> None:
        state = data["states"]["read_file"]
        assert state.get("on_yes") == "extract_and_score"
        assert state.get("on_no") == "report"
        assert state.get("on_error") == "report"

    def test_next_file_loops_back_to_read_file(self, data: dict) -> None:
        state = data["states"]["next_file"]
        assert state.get("on_yes") == "read_file"
        assert state.get("on_no") == "report"

    def test_capture_issues_uses_prompt_with_next(self, data: dict) -> None:
        state = data["states"]["capture_issues"]
        assert state.get("action_type") == "prompt"
        assert state.get("next") == "verify_captures"
        assert "on_yes" not in state

    def test_report_is_terminal(self, data: dict) -> None:
        assert data["states"].get("report", {}).get("terminal") is True

    def test_failed_is_terminal(self, data: dict) -> None:
        assert data["states"].get("failed", {}).get("terminal") is True

    def test_all_prompt_states_with_on_yes_have_on_no(self, data: dict) -> None:
        """MR-4: prompt states with on_yes must also have on_no."""
        for name, state in data.get("states", {}).items():
            if state.get("action_type") == "prompt" and "on_yes" in state:
                assert "on_no" in state, f"state '{name}' has on_yes but missing on_no (MR-4)"

    def test_no_bare_loops_tmp_writes(self, data: dict) -> None:
        """MR-3: no writes to bare .loops/tmp/."""
        for name, state in data.get("states", {}).items():
            action = state.get("action", "")
            assert ".loops/tmp/" not in action, (
                f"state '{name}' writes to .loops/tmp/ (MR-3 violation)"
            )

    def test_input_key_populates_context_files(self, data: dict) -> None:
        assert data.get("input_key") == "files"
        assert data.get("context", {}).get("files") == ""

    def test_context_files_referenced_in_init(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "${context.files}" in action

    def test_relevance_threshold_used_in_filter_items(self, data: dict) -> None:
        action = data["states"]["filter_items"].get("action", "")
        assert "${context.relevance_threshold}" in action

    def test_max_issues_per_file_used_in_filter_items(self, data: dict) -> None:
        action = data["states"]["filter_items"].get("action", "")
        assert "${context.max_issues_per_file}" in action

    def test_run_dir_used_throughout(self, data: dict) -> None:
        """All shell states reference run_dir for artifact isolation."""
        shell_states = [
            "init",
            "load_context",
            "read_file",
            "validate_scores",
            "filter_items",
            "verify_captures",
            "next_file",
        ]
        for name in shell_states:
            action = data["states"][name].get("action", "")
            assert "${context.run_dir}" in action or "run_dir" in action, (
                f"state '{name}' does not reference run_dir"
            )


class TestPlanResearchIterationOracle:
    """Structural tests for the plan-research-iteration oracle sub-loop (ENH-2033)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/plan-research-iteration.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "plan-research-iteration"
        assert data.get("initial") == "classify_research"

    def test_uses_flow_shorthand(self, data: dict) -> None:
        """Oracle must be authored with flow: shorthand per ENH-2033 acceptance criteria."""
        assert "flow" in data, "plan-research-iteration must use flow: shorthand"

    def test_has_parameters_block(self, data: dict) -> None:
        params = data.get("parameters", {})
        assert "run_dir" in params, "parameters must declare run_dir"
        assert params["run_dir"].get("required") is True, "run_dir must be required"
        assert "overwrite_source" in params, "parameters must declare overwrite_source"
        assert params["overwrite_source"].get("required") is not True, (
            "overwrite_source must be optional"
        )

    def test_flow_contains_all_six_research_states(self, data: dict) -> None:
        flow = data.get("flow", [])
        flow_names = {(e.split("?", 1)[0] if "?" in e else e) for e in flow}
        for expected in (
            "classify_research",
            "route_files",
            "route_web",
            "research_files",
            "research_web",
            "synthesize",
        ):
            assert expected in flow_names, f"flow must include '{expected}'"

    def test_last_flow_entry_is_done(self, data: dict) -> None:
        """Last flow entry must be 'done' so sub-loop routes parent to on_success."""
        flow = data.get("flow", [])
        last = flow[-1] if flow else ""
        state_name = last.split("?", 1)[0] if "?" in last else last
        assert state_name == "done", (
            f"last flow entry must be 'done' for sub-loop success routing, got '{state_name}'"
        )

    def test_route_files_has_needs_files_evaluate(self, data: dict) -> None:
        state_defs = data.get("state_defs", {})
        evaluate = state_defs.get("route_files", {}).get("evaluate", {})
        assert evaluate.get("pattern") == "NEEDS_FILES", (
            "route_files evaluate.pattern must be 'NEEDS_FILES'"
        )

    def test_route_web_has_needs_web_evaluate(self, data: dict) -> None:
        state_defs = data.get("state_defs", {})
        evaluate = state_defs.get("route_web", {}).get("evaluate", {})
        assert evaluate.get("pattern") == "NEEDS_WEB", (
            "route_web evaluate.pattern must be 'NEEDS_WEB'"
        )

    def test_classify_research_captures_classification(self, data: dict) -> None:
        state_defs = data.get("state_defs", {})
        assert state_defs.get("classify_research", {}).get("capture") == "classification", (
            "classify_research must capture as 'classification'"
        )

    def test_synthesize_references_overwrite_source(self, data: dict) -> None:
        state_defs = data.get("state_defs", {})
        action = state_defs.get("synthesize", {}).get("action", "")
        assert "overwrite_source" in action, (
            "synthesize action must reference overwrite_source for rn-refine Step 7/8 gate"
        )

    def test_research_files_overrides_next_to_check_research(self, data: dict) -> None:
        """research_files must override flow-generated next: research_web → check_research."""
        state_defs = data.get("state_defs", {})
        assert state_defs.get("research_files", {}).get("next") == "check_research", (
            "research_files state_defs must set next: check_research to override "
            "flow-generated next: research_web"
        )

    def test_research_states_have_timeout_and_error_route(self, data: dict) -> None:
        """research_web/research_files must bound runtime and degrade through the guard.

        A per-state timeout returns exit 124, which routes via on_error. Both
        research states must route on_error to check_research so a timed-out or
        partial research run is gated rather than fed straight into synthesize.
        See audit rn-refine 2026-06-25.
        """
        state_defs = data.get("state_defs", {})
        for name in ("research_web", "research_files"):
            state = state_defs.get(name, {})
            assert isinstance(state.get("timeout"), int) and state["timeout"] > 0, (
                f"{name} must declare a positive per-state timeout"
            )
            assert state.get("on_error") == "check_research", (
                f"{name} must route on_error to check_research"
            )

    def test_check_research_guards_synthesize(self, data: dict) -> None:
        """check_research must gate synthesize: populated research → synthesize, empty → done.

        synthesize reads research.md unconditionally, so an empty research file
        would produce a phantom no-op rewrite. The guard routes via the
        'check_research?synthesize:done' flow ternary on a `test -s` shell check.
        """
        flow = data.get("flow", [])
        assert "check_research?synthesize:done" in flow, (
            "flow must gate synthesize behind 'check_research?synthesize:done' ternary"
        )
        state = data.get("state_defs", {}).get("check_research", {})
        assert state.get("action_type") == "shell", "check_research must be a shell guard"
        assert "research.md" in state.get("action", ""), (
            "check_research action must test the research.md file"
        )
        assert state.get("evaluate", {}).get("pattern") == "HAS_RESEARCH", (
            "check_research must evaluate on the HAS_RESEARCH token"
        )

    def test_synthesize_only_reachable_via_guard(self, data: dict) -> None:
        """No state may route directly to synthesize except the check_research guard."""
        from little_loops.fsm.fragments import resolve_flow

        expanded = resolve_flow(data)
        offenders = []
        for name, state in expanded["states"].items():
            if name == "check_research":
                continue
            for key in ("next", "on_yes", "on_no", "on_error", "on_partial"):
                if state.get(key) == "synthesize":
                    offenders.append(f"{name}.{key}")
        assert not offenders, f"only check_research may route to synthesize; offenders: {offenders}"

    def test_states_use_context_run_dir(self, data: dict) -> None:
        """All prompt state bodies must reference ${context.run_dir}, not ${captured.*}."""
        state_defs = data.get("state_defs", {})
        for name in ("classify_research", "research_files", "research_web", "synthesize"):
            action = state_defs.get(name, {}).get("action", "")
            assert "${context.run_dir}" in action, (
                f"state_defs.{name}.action must reference ${{context.run_dir}}"
            )


class TestRnPlanDelegatesResearchToOracle:
    """rn-plan must delegate the research chain to plan-research-iteration (ENH-2033)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-plan.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_no_inline_classify_research(self, data: dict) -> None:
        assert "classify_research" not in data.get("states", {}), (
            "rn-plan must not have inline classify_research (extracted to oracle)"
        )

    def test_no_inline_route_files(self, data: dict) -> None:
        assert "route_files" not in data.get("states", {}), (
            "rn-plan must not have inline route_files (extracted to oracle)"
        )

    def test_no_inline_research_files(self, data: dict) -> None:
        assert "research_files" not in data.get("states", {}), (
            "rn-plan must not have inline research_files (extracted to oracle)"
        )

    def test_no_inline_synthesize(self, data: dict) -> None:
        assert "synthesize" not in data.get("states", {}), (
            "rn-plan must not have inline synthesize (extracted to oracle)"
        )

    def test_research_iteration_state_exists(self, data: dict) -> None:
        assert "research_iteration" in data.get("states", {}), (
            "rn-plan must have a research_iteration state"
        )

    def test_research_iteration_delegates_to_oracle(self, data: dict) -> None:
        state = data.get("states", {}).get("research_iteration", {})
        assert state.get("loop") == "oracles/plan-research-iteration", (
            f"research_iteration.loop must be 'oracles/plan-research-iteration', "
            f"got {state.get('loop')!r}"
        )

    def test_research_iteration_passes_run_dir(self, data: dict) -> None:
        with_ = data.get("states", {}).get("research_iteration", {}).get("with", {})
        assert "run_dir" in with_, "research_iteration.with must include run_dir"

    def test_research_iteration_no_overwrite_source_true(self, data: dict) -> None:
        """rn-plan must NOT enable overwrite_source (no in-place file overwrite)."""
        with_ = data.get("states", {}).get("research_iteration", {}).get("with", {})
        assert with_.get("overwrite_source", "false") != "true", (
            "rn-plan research_iteration.with.overwrite_source must not be 'true'"
        )

    def test_score_on_no_is_research_iteration(self, data: dict) -> None:
        score = data.get("states", {}).get("score", {})
        assert score.get("on_no") == "research_iteration", (
            f"score.on_no must be 'research_iteration', got {score.get('on_no')!r}"
        )


class TestRnRefineRecursiveDecomposition:
    """rn-refine is a recursive, adaptive-depth planner: it refines the plan as a
    decomposition tree (per-node refine -> decide leaf/decompose -> enqueue children
    depth-first -> bottom-up synthesis -> reassemble -> overwrite source)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-refine.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_no_inline_classify_research(self, data: dict) -> None:
        """The research/synthesize chain still lives in oracles, never inline."""
        assert "classify_research" not in data.get("states", {})

    def test_no_inline_synthesize(self, data: dict) -> None:
        assert "synthesize" not in data.get("states", {})

    def test_refine_node_delegates_to_node_oracle(self, data: dict) -> None:
        state = data.get("states", {}).get("refine_node", {})
        assert state.get("loop") == "oracles/plan-node-refine", (
            f"refine_node.loop must be 'oracles/plan-node-refine', got {state.get('loop')!r}"
        )

    def test_refine_node_passes_node_id_and_depth_cap(self, data: dict) -> None:
        with_ = data.get("states", {}).get("refine_node", {}).get("with", {})
        for key in ("run_dir", "node_id", "depth", "max_depth"):
            assert key in with_, f"refine_node.with must include {key}"

    def test_decomposed_node_loops_back_to_dequeue(self, data: dict) -> None:
        """A decomposed node's children are enqueued (in the oracle); control returns
        to the queue to process them depth-first."""
        assert data.get("states", {}).get("route_decomposed", {}).get("on_yes") == "dequeue_next"

    def test_empty_queue_routes_to_bottom_up_synthesis(self, data: dict) -> None:
        assert data.get("states", {}).get("dequeue_next", {}).get("on_yes") == "build_synth"

    def test_has_bottom_up_synthesis_chain(self, data: dict) -> None:
        states = data.get("states", {})
        for s in ("build_synth", "synth_pop", "integrate_node", "assemble", "final_score"):
            assert s in states, f"missing synthesis state: {s}"

    def test_finalize_overwrites_source_in_place(self, data: dict) -> None:
        """The reassembled plan is written back over the user's source file."""
        action = data.get("states", {}).get("finalize", {}).get("action", "")
        assert ".source-path" in action and "cp " in action, (
            "finalize must read .source-path and copy the reassembled plan over the source"
        )

    def test_adaptive_depth_cap_is_configurable(self, data: dict) -> None:
        """Adaptive depth is bounded by a configurable max_depth (n = as-needed, capped)."""
        assert "max_depth" in data.get("context", {})


class TestRlhfSvgEvaluateSubLoop:
    """rlhf-svg-evaluate sub-loop structural correctness (ENH-2048)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rlhf-svg-evaluate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_states_present(self, data: dict) -> None:
        states = set(data.get("states", {}).keys())
        for state in ("smoke_test", "score", "track_correlation", "done"):
            assert state in states, f"rlhf-svg-evaluate must have a '{state}' state"

    def test_context_declares_run_dir(self, data: dict) -> None:
        assert "run_dir" in data.get("context", {}), (
            "rlhf-svg-evaluate must declare 'run_dir' in context"
        )

    def test_context_declares_quality_target(self, data: dict) -> None:
        assert "quality_target" in data.get("context", {}), (
            "rlhf-svg-evaluate must declare 'quality_target' in context"
        )

    def test_context_declares_smoke_bypass_threshold(self, data: dict) -> None:
        assert "smoke_bypass_threshold" in data.get("context", {}), (
            "rlhf-svg-evaluate must declare 'smoke_bypass_threshold' in context"
        )

    def test_context_declares_exploit_cutoff(self, data: dict) -> None:
        assert "exploit_cutoff" in data.get("context", {}), (
            "rlhf-svg-evaluate must declare 'exploit_cutoff' in context"
        )

    def test_shell_states_use_context_run_dir_not_captured(self, data: dict) -> None:
        states = data.get("states", {})
        for name, state in states.items():
            action = state.get("action", "") or ""
            if state.get("action_type") == "shell" and action:
                assert "${captured.run_dir.output}" not in action, (
                    f"State '{name}' must use ${{context.run_dir}}, "
                    f"not ${{captured.run_dir.output}}"
                )

    def test_done_is_terminal(self, data: dict) -> None:
        done = data.get("states", {}).get("done", {})
        assert done.get("terminal") is True, "'done' state must be terminal: true"


class TestRlhfSvgRefineSubLoop:
    """rlhf-svg-refine sub-loop structural correctness (ENH-2049)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rlhf-svg-refine.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_states_present(self, data: dict) -> None:
        states = set(data.get("states", {}).keys())
        for state in (
            "rank_components",
            "review_critique",
            "apply_refinements",
            "self_diagnose",
            "write_summary",
            "done",
        ):
            assert state in states, f"rlhf-svg-refine must have a '{state}' state"

    def test_context_declares_run_dir(self, data: dict) -> None:
        assert "run_dir" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'run_dir' in context"
        )

    def test_context_declares_animation_plan(self, data: dict) -> None:
        assert "animation_plan" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'animation_plan' in context"
        )

    def test_context_declares_fix_plan(self, data: dict) -> None:
        assert "fix_plan" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'fix_plan' in context"
        )

    def test_context_declares_component_ranking(self, data: dict) -> None:
        assert "component_ranking" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'component_ranking' in context"
        )

    def test_context_declares_global_iteration(self, data: dict) -> None:
        assert "global_iteration" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'global_iteration' in context"
        )

    def test_context_declares_explore_cutoff(self, data: dict) -> None:
        assert "explore_cutoff" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'explore_cutoff' in context"
        )

    def test_context_declares_exploit_cutoff(self, data: dict) -> None:
        assert "exploit_cutoff" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'exploit_cutoff' in context"
        )

    def test_context_declares_quality_target(self, data: dict) -> None:
        assert "quality_target" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'quality_target' in context"
        )

    def test_context_declares_design_tokens_context(self, data: dict) -> None:
        assert "design_tokens_context" in data.get("context", {}), (
            "rlhf-svg-refine must declare 'design_tokens_context' in context"
        )

    def test_phase_detection_uses_context_global_iteration(self, data: dict) -> None:
        states = data.get("states", {})
        for name in ("review_critique", "apply_refinements"):
            state = states.get(name, {})
            action = state.get("action", "") or ""
            assert "${state.iteration}" not in action, (
                f"State '{name}' must reference ${{context.global_iteration}}, "
                f"not ${{state.iteration}}"
            )
            assert "${context.global_iteration}" in action, (
                f"State '{name}' must reference ${{context.global_iteration}} for phase detection"
            )

    def test_review_critique_captures_fix_plan(self, data: dict) -> None:
        state = data.get("states", {}).get("review_critique", {})
        assert state.get("capture") == "fix_plan", "review_critique must capture 'fix_plan'"

    def test_done_is_terminal(self, data: dict) -> None:
        done = data.get("states", {}).get("done", {})
        assert done.get("terminal") is True, "'done' state must be terminal: true"


class TestRlhfSvgGenerateSubLoop:
    """rlhf-svg-generate sub-loop structural correctness (ENH-2051)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rlhf-svg-generate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_states_present(self, data: dict) -> None:
        states = set(data.get("states", {}).keys())
        for state in ("plan_animation", "render_animation", "verify_render", "done", "plan_failed"):
            assert state in states, f"rlhf-svg-generate must have a '{state}' state"

    def test_context_declares_input(self, data: dict) -> None:
        assert "input" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'input' in context"
        )

    def test_context_declares_run_dir(self, data: dict) -> None:
        assert "run_dir" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'run_dir' in context"
        )

    def test_context_declares_quality_target(self, data: dict) -> None:
        assert "quality_target" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'quality_target' in context"
        )

    def test_context_declares_global_iteration(self, data: dict) -> None:
        assert "global_iteration" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'global_iteration' in context"
        )

    def test_context_declares_design_tokens_context(self, data: dict) -> None:
        assert "design_tokens_context" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'design_tokens_context' in context"
        )

    def test_context_declares_explore_cutoff(self, data: dict) -> None:
        assert "explore_cutoff" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'explore_cutoff' in context"
        )

    def test_context_declares_exploit_cutoff(self, data: dict) -> None:
        assert "exploit_cutoff" in data.get("context", {}), (
            "rlhf-svg-generate must declare 'exploit_cutoff' in context"
        )

    def test_phase_detection_uses_context_global_iteration(self, data: dict) -> None:
        state = data.get("states", {}).get("plan_animation", {})
        action = state.get("action", "") or ""
        assert "${state.iteration}" not in action, (
            "State 'plan_animation' must reference ${context.global_iteration}, "
            "not ${state.iteration}"
        )
        assert "${context.global_iteration}" in action, (
            "State 'plan_animation' must reference ${context.global_iteration} for phase detection"
        )

    def test_done_is_terminal(self, data: dict) -> None:
        done = data.get("states", {}).get("done", {})
        assert done.get("terminal") is True, "'done' state must be terminal: true"

    def test_plan_failed_is_terminal(self, data: dict) -> None:
        plan_failed = data.get("states", {}).get("plan_failed", {})
        assert plan_failed.get("terminal") is True, "'plan_failed' state must be terminal: true"


class TestRlhfAnimatedSvgParentOrchestration:
    """rlhf-animated-svg parent must delegate evaluate/refine to sub-loops (ENH-2056)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rlhf-animated-svg.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    # --- extracted evaluate states absent ---

    def test_no_inline_smoke_test(self, data: dict) -> None:
        assert "smoke_test" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline smoke_test (delegated to rlhf-svg-evaluate)"
        )

    def test_no_inline_score(self, data: dict) -> None:
        assert "score" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline score (delegated to rlhf-svg-evaluate)"
        )

    def test_no_inline_track_correlation(self, data: dict) -> None:
        assert "track_correlation" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline track_correlation (delegated to rlhf-svg-evaluate)"
        )

    # --- extracted refine states absent ---

    def test_no_inline_rank_components(self, data: dict) -> None:
        assert "rank_components" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline rank_components (delegated to rlhf-svg-refine)"
        )

    def test_no_inline_review_critique(self, data: dict) -> None:
        assert "review_critique" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline review_critique (delegated to rlhf-svg-refine)"
        )

    def test_no_inline_apply_refinements(self, data: dict) -> None:
        assert "apply_refinements" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline apply_refinements (delegated to rlhf-svg-refine)"
        )

    def test_no_inline_self_diagnose(self, data: dict) -> None:
        assert "self_diagnose" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline self_diagnose (delegated to rlhf-svg-refine)"
        )

    def test_no_inline_write_summary(self, data: dict) -> None:
        assert "write_summary" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline write_summary (delegated to rlhf-svg-refine)"
        )

    # --- evaluate delegation state ---

    def test_run_evaluate_state_exists(self, data: dict) -> None:
        assert "run_evaluate" in data.get("states", {}), (
            "rlhf-animated-svg must have a run_evaluate delegation state"
        )

    def test_run_evaluate_delegates_to_rlhf_svg_evaluate(self, data: dict) -> None:
        state = data.get("states", {}).get("run_evaluate", {})
        assert state.get("loop") == "rlhf-svg-evaluate", (
            f"run_evaluate.loop must be 'rlhf-svg-evaluate', got {state.get('loop')!r}"
        )

    def test_run_evaluate_with_run_dir(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_evaluate", {}).get("with", {})
        assert "run_dir" in with_, "run_evaluate.with must include run_dir"

    def test_run_evaluate_with_quality_target(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_evaluate", {}).get("with", {})
        assert "quality_target" in with_, "run_evaluate.with must include quality_target"

    def test_run_evaluate_with_smoke_bypass_threshold(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_evaluate", {}).get("with", {})
        assert "smoke_bypass_threshold" in with_, (
            "run_evaluate.with must include smoke_bypass_threshold"
        )

    def test_run_evaluate_with_exploit_cutoff(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_evaluate", {}).get("with", {})
        assert "exploit_cutoff" in with_, "run_evaluate.with must include exploit_cutoff"

    # --- refine delegation state ---

    def test_run_refine_state_exists(self, data: dict) -> None:
        assert "run_refine" in data.get("states", {}), (
            "rlhf-animated-svg must have a run_refine delegation state"
        )

    def test_run_refine_delegates_to_rlhf_svg_refine(self, data: dict) -> None:
        state = data.get("states", {}).get("run_refine", {})
        assert state.get("loop") == "rlhf-svg-refine", (
            f"run_refine.loop must be 'rlhf-svg-refine', got {state.get('loop')!r}"
        )

    def test_run_refine_with_run_dir(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "run_dir" in with_, "run_refine.with must include run_dir"

    def test_run_refine_with_animation_plan(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "animation_plan" in with_, "run_refine.with must include animation_plan"

    def test_run_refine_with_fix_plan(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "fix_plan" in with_, "run_refine.with must include fix_plan"

    def test_run_refine_with_component_ranking(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "component_ranking" in with_, "run_refine.with must include component_ranking"

    def test_run_refine_with_global_iteration(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "global_iteration" in with_, "run_refine.with must include global_iteration"

    def test_run_refine_with_explore_cutoff(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "explore_cutoff" in with_, "run_refine.with must include explore_cutoff"

    def test_run_refine_with_exploit_cutoff(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "exploit_cutoff" in with_, "run_refine.with must include exploit_cutoff"

    def test_run_refine_with_quality_target(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "quality_target" in with_, "run_refine.with must include quality_target"

    def test_run_refine_with_design_tokens_context(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_refine", {}).get("with", {})
        assert "design_tokens_context" in with_, (
            "run_refine.with must include design_tokens_context"
        )

    # --- retained states present ---

    def test_retained_states_present(self, data: dict) -> None:
        states = set(data.get("states", {}).keys())
        for state in (
            "init",
            "validate_input",
            "check_oscillation",
            "check_score_streak",
            "write_final_summary",
            "done",
            "failed",
        ):
            assert state in states, f"rlhf-animated-svg must retain '{state}' state"

    # --- line count ---

    def test_parent_body_within_line_limit(self) -> None:
        # Final target after ENH-2162 extracts generate states to rlhf-svg-generate: ≤450 lines.
        line_count = len(self.LOOP_FILE.read_text().splitlines())
        assert line_count <= 450, (
            f"Parent loop is {line_count} lines (target: ≤450 after generate delegation)"
        )


class TestRlhfAnimatedSvgDelegatesGenerate:
    """rlhf-animated-svg parent must delegate generate phase to rlhf-svg-generate (ENH-2162)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rlhf-animated-svg.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    # --- inline generate states absent ---

    def test_no_inline_plan_animation(self, data: dict) -> None:
        assert "plan_animation" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline plan_animation (delegated to rlhf-svg-generate)"
        )

    def test_no_inline_render_animation(self, data: dict) -> None:
        assert "render_animation" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline render_animation (delegated to rlhf-svg-generate)"
        )

    def test_no_inline_verify_render(self, data: dict) -> None:
        assert "verify_render" not in data.get("states", {}), (
            "rlhf-animated-svg must not have inline verify_render (delegated to rlhf-svg-generate)"
        )

    # --- run_generate delegation state ---

    def test_run_generate_state_exists(self, data: dict) -> None:
        assert "run_generate" in data.get("states", {}), (
            "rlhf-animated-svg must have a run_generate delegation state"
        )

    def test_run_generate_delegates_to_rlhf_svg_generate(self, data: dict) -> None:
        state = data.get("states", {}).get("run_generate", {})
        assert state.get("loop") == "rlhf-svg-generate", (
            f"run_generate.loop must be 'rlhf-svg-generate', got {state.get('loop')!r}"
        )

    def test_run_generate_passes_input(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "input" in with_, "run_generate.with must include input"

    def test_run_generate_passes_run_dir(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "run_dir" in with_, "run_generate.with must include run_dir"

    def test_run_generate_passes_global_iteration(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "global_iteration" in with_, "run_generate.with must include global_iteration"

    def test_run_generate_passes_design_tokens_context(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "design_tokens_context" in with_, (
            "run_generate.with must include design_tokens_context"
        )

    def test_run_generate_passes_quality_target(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "quality_target" in with_, "run_generate.with must include quality_target"

    def test_run_generate_passes_explore_cutoff(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "explore_cutoff" in with_, "run_generate.with must include explore_cutoff"

    def test_run_generate_passes_exploit_cutoff(self, data: dict) -> None:
        with_ = data.get("states", {}).get("run_generate", {}).get("with", {})
        assert "exploit_cutoff" in with_, "run_generate.with must include exploit_cutoff"

    def test_run_generate_on_success_is_run_evaluate(self, data: dict) -> None:
        state = data.get("states", {}).get("run_generate", {})
        assert state.get("on_success") == "run_evaluate", (
            f"run_generate.on_success must be 'run_evaluate', got {state.get('on_success')!r}"
        )

    def test_run_generate_on_failure_is_plan_failed(self, data: dict) -> None:
        state = data.get("states", {}).get("run_generate", {})
        assert state.get("on_failure") == "plan_failed", (
            f"run_generate.on_failure must be 'plan_failed', got {state.get('on_failure')!r}"
        )


class TestRnRemediateAssessRouting:
    """Tests that rn-remediate assess state handles non-yes verdicts without crashing (BUG-2075)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-remediate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_assess_on_partial_routes_to_verify_scores_persisted(self, data: dict) -> None:
        """assess.on_partial must route to verify_scores_persisted (core work done; treat like success)."""
        state = data["states"].get("assess", {})
        assert state.get("on_partial") == "verify_scores_persisted", (
            f"assess.on_partial should be 'verify_scores_persisted', got {state.get('on_partial')!r}"
        )

    def test_assess_on_no_routes_to_refine_first(self, data: dict) -> None:
        """assess.on_no must route to refine_first (ENH-2247: first-pass scoring is not a
        content diagnosis → lighter --auto refine, not the destructive --full-rewrite)."""
        state = data["states"].get("assess", {})
        assert state.get("on_no") == "refine_first", (
            f"assess.on_no should be 'refine_first', got {state.get('on_no')!r}"
        )

    # decide state tests (BUG-2169)

    def test_decide_on_yes_routes_to_re_assess(self, data: dict) -> None:
        """decide.on_yes must route to re_assess (successful decision → re-evaluate scores)."""
        state = data["states"].get("decide", {})
        assert state.get("on_yes") == "re_assess", (
            f"decide.on_yes should be 're_assess', got {state.get('on_yes')!r}"
        )

    def test_decide_on_no_routes_to_emit_implement_failed(self, data: dict) -> None:
        """decide.on_no must route to emit_implement_failed (ENH-2307: surface failure immediately)."""
        state = data["states"].get("decide", {})
        assert state.get("on_no") == "emit_implement_failed", (
            f"decide.on_no should be 'emit_implement_failed', got {state.get('on_no')!r}"
        )

    def test_decide_on_error_routes_to_emit_implement_failed(self, data: dict) -> None:
        """decide.on_error must route to emit_implement_failed (ENH-2307: mirrors assess pattern)."""
        state = data["states"].get("decide", {})
        assert state.get("on_error") == "emit_implement_failed", (
            f"decide.on_error should be 'emit_implement_failed', got {state.get('on_error')!r}"
        )

    def test_decide_on_partial_routes_to_re_assess(self, data: dict) -> None:
        """decide.on_partial must route to re_assess (partial decision → re-evaluate, don't crash)."""
        state = data["states"].get("decide", {})
        assert state.get("on_partial") == "re_assess", (
            f"decide.on_partial should be 're_assess', got {state.get('on_partial')!r}"
        )

    # wire state tests (BUG-2169)

    def test_wire_on_yes_routes_to_mark_wired(self, data: dict) -> None:
        """wire.on_yes must route to mark_wired (successful wire → set marker then re_assess)."""
        state = data["states"].get("wire", {})
        assert state.get("on_yes") == "mark_wired", (
            f"wire.on_yes should be 'mark_wired', got {state.get('on_yes')!r}"
        )

    def test_wire_on_no_routes_to_refine_first(self, data: dict) -> None:
        """wire.on_no must route to refine_first (ENH-2247: a wire failure is an
        integration-map problem, not prose-content → lighter --auto refine)."""
        state = data["states"].get("wire", {})
        assert state.get("on_no") == "refine_first", (
            f"wire.on_no should be 'refine_first', got {state.get('on_no')!r}"
        )

    def test_wire_on_partial_routes_to_mark_wired(self, data: dict) -> None:
        """wire.on_partial must route to mark_wired (partial wire still marks; re_assess evaluates sufficiency)."""
        state = data["states"].get("wire", {})
        assert state.get("on_partial") == "mark_wired", (
            f"wire.on_partial should be 'mark_wired', got {state.get('on_partial')!r}"
        )

    # refine state tests (BUG-2169)

    def test_refine_on_yes_routes_to_mark_refined(self, data: dict) -> None:
        """refine.on_yes must route to mark_refined (successful refine → set marker then re_assess)."""
        state = data["states"].get("refine", {})
        assert state.get("on_yes") == "mark_refined", (
            f"refine.on_yes should be 'mark_refined', got {state.get('on_yes')!r}"
        )

    def test_refine_on_no_routes_to_emit_implement_failed(self, data: dict) -> None:
        """refine.on_no must route to emit_implement_failed (refine failure → terminal escalation)."""
        state = data["states"].get("refine", {})
        assert state.get("on_no") == "emit_implement_failed", (
            f"refine.on_no should be 'emit_implement_failed', got {state.get('on_no')!r}"
        )

    def test_refine_on_partial_routes_to_mark_refined(self, data: dict) -> None:
        """refine.on_partial must route to mark_refined (partial refine still marks; re_assess evaluates sufficiency)."""
        state = data["states"].get("refine", {})
        assert state.get("on_partial") == "mark_refined", (
            f"refine.on_partial should be 'mark_refined', got {state.get('on_partial')!r}"
        )

    def test_partial_route_ok_not_set(self, data: dict) -> None:
        """partial_route_ok must not be set once all MR-4 sibling states are fixed (BUG-2169)."""
        assert not data.get("partial_route_ok"), (
            "partial_route_ok should be absent or false now that decide/wire/refine all "
            "define on_yes/on_no/on_partial; remove it so MR-4 validation catches regressions"
        )


class TestRnImplementDiagnosticOutcomes:
    """rn-implement splits SCORES_MISSING / SIZE_REVIEW_FAILED out of the generic
    record_failure bucket into distinct diagnostic record states for operator triage."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-implement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_rem_rate_limited_on_no_routes_to_scores_missing_router(self, data: dict) -> None:
        """route_rem_rate_limited.on_no must hand off to route_rem_scores_missing
        (instead of collapsing SCORES_MISSING into record_failure)."""
        state = data["states"]["route_rem_rate_limited"]
        assert state["on_no"] == "route_rem_scores_missing"
        assert state["on_error"] == "route_rem_scores_missing"

    def test_route_rem_scores_missing_splits_to_record_state(self, data: dict) -> None:
        """route_rem_scores_missing matches the SCORES_MISSING token and routes it to
        record_scores_missing; everything else falls through to record_failure."""
        state = data["states"]["route_rem_scores_missing"]
        assert state["evaluate"]["type"] == "output_contains"
        assert state["evaluate"]["pattern"] == "SCORES_MISSING"
        assert "${captured.rem_outcome.output}" in state["evaluate"]["source"]
        assert state["on_yes"] == "record_scores_missing"
        assert state["on_no"] == "record_failure"
        assert state["on_error"] == "record_failure"

    def test_dec_rate_limited_on_no_routes_to_size_review_router(self, data: dict) -> None:
        """route_dec_rate_limited.on_no must hand off to route_dec_size_review_failed."""
        state = data["states"]["route_dec_rate_limited"]
        assert state["on_no"] == "route_dec_size_review_failed"
        assert state["on_error"] == "route_dec_size_review_failed"

    def test_route_dec_size_review_failed_splits_to_record_state(self, data: dict) -> None:
        """route_dec_size_review_failed matches SIZE_REVIEW_FAILED and routes it to
        record_size_review_failed; else record_failure."""
        state = data["states"]["route_dec_size_review_failed"]
        assert state["evaluate"]["type"] == "output_contains"
        assert state["evaluate"]["pattern"] == "SIZE_REVIEW_FAILED"
        assert "${captured.dec_outcome.output}" in state["evaluate"]["source"]
        assert state["on_yes"] == "record_size_review_failed"
        assert state["on_no"] == "record_failure"
        assert state["on_error"] == "record_failure"

    @pytest.mark.parametrize(
        "state_name,tag",
        [
            ("record_scores_missing", "SCORES_MISSING"),
            ("record_size_review_failed", "SIZE_REVIEW_FAILED"),
        ],
    )
    def test_diagnostic_record_states_tag_and_continue(
        self, data: dict, state_name: str, tag: str
    ) -> None:
        """Each diagnostic record state writes a tagged line to failures.txt (so report
        can tally it separately) and continues the queue via next: dequeue_next —
        mirroring the record_sub_loop_crash convention."""
        state = data["states"][state_name]
        assert state["action_type"] == "shell"
        assert tag in state["action"]
        assert "failures.txt" in state["action"]
        assert state["next"] == "dequeue_next"

    def test_report_tallies_diagnostics_separately_from_failures(self, data: dict) -> None:
        """report subtracts SCORES_MISSING and SIZE_REVIEW_FAILED from the headline
        failure count and surfaces them as distinct summary.json keys."""
        action = data["states"]["report"]["action"]
        assert 'grep -c "SCORES_MISSING"' in action
        assert 'grep -c "SIZE_REVIEW_FAILED"' in action
        assert "- SCORES_MISSING - SIZE_REVIEW_FAILED" in action
        assert '"scores_missing"' in action
        assert '"size_review_failed"' in action


class TestCheckSubstrateOptionalState:
    """Tests that check_substrate optional state is documented in planning loop templates (ENH-2085)."""

    HARNESS_PLAN_FILE = BUILTIN_LOOPS_DIR / "harness-plan-research-implement-report.yaml"
    LOOP_TYPES_FILE = (
        Path(__file__).parent.parent.parent / "skills" / "create-loop" / "loop-types.md"
    )
    RN_PLAN_FILE = BUILTIN_LOOPS_DIR / "rn-plan.yaml"
    RN_BUILD_FILE = BUILTIN_LOOPS_DIR / "rn-build.yaml"

    def test_harness_plan_file_documents_check_substrate(self) -> None:
        """harness-plan-research-implement-report.yaml must document check_substrate optional state."""
        assert self.HARNESS_PLAN_FILE.exists(), f"Loop file not found: {self.HARNESS_PLAN_FILE}"
        content = self.HARNESS_PLAN_FILE.read_text()
        assert "check_substrate" in content, (
            "harness-plan-research-implement-report.yaml must contain a commented-out "
            "check_substrate optional state block per ENH-2085"
        )

    def test_check_substrate_routes_on_no_to_plan(self) -> None:
        """check_substrate block must route on_no back to plan for infeasible actions."""
        assert self.HARNESS_PLAN_FILE.exists(), f"Loop file not found: {self.HARNESS_PLAN_FILE}"
        content = self.HARNESS_PLAN_FILE.read_text()
        # Find the check_substrate block and verify on_no: plan appears within it
        cs_pos = content.find("check_substrate")
        assert cs_pos != -1, (
            "check_substrate block not found in harness-plan-research-implement-report.yaml"
        )
        # on_no: plan must appear after check_substrate and before research:
        research_pos = content.find("\n  research:", cs_pos)
        block_slice = content[cs_pos:research_pos] if research_pos != -1 else content[cs_pos:]
        assert "on_no: plan" in block_slice, (
            "check_substrate block must contain 'on_no: plan' to route infeasible actions "
            "back to the plan state for revision"
        )

    def test_check_substrate_positioned_between_review_plan_and_research(self) -> None:
        """check_substrate block must appear between review_plan and research in the file."""
        assert self.HARNESS_PLAN_FILE.exists(), f"Loop file not found: {self.HARNESS_PLAN_FILE}"
        content = self.HARNESS_PLAN_FILE.read_text()
        review_plan_pos = content.find("review_plan")
        check_substrate_pos = content.find("check_substrate")
        research_pos = content.find("\n  research:")
        assert review_plan_pos != -1, (
            "review_plan block must be present in harness-plan-research-implement-report.yaml"
        )
        assert check_substrate_pos != -1, (
            "check_substrate block must be present in harness-plan-research-implement-report.yaml"
        )
        assert research_pos != -1, (
            "research state must be present in harness-plan-research-implement-report.yaml"
        )
        assert review_plan_pos < check_substrate_pos < research_pos, (
            "check_substrate must appear after review_plan and before the research state"
        )

    def test_loop_types_documents_check_substrate(self) -> None:
        """loop-types.md specialist pipeline template must document check_substrate optional state."""
        assert self.LOOP_TYPES_FILE.exists(), f"loop-types.md not found: {self.LOOP_TYPES_FILE}"
        content = self.LOOP_TYPES_FILE.read_text()
        assert "check_substrate" in content, (
            "skills/create-loop/loop-types.md specialist pipeline template must include "
            "a check_substrate optional state block per ENH-2085"
        )

    # ── ENH-2098: rn-plan check_substrate gate ─────────────────────────────────

    def test_rn_plan_has_check_substrate(self) -> None:
        """rn-plan.yaml must contain a check_substrate feasibility gate (ENH-2098)."""
        assert self.RN_PLAN_FILE.exists(), f"Loop file not found: {self.RN_PLAN_FILE}"
        content = self.RN_PLAN_FILE.read_text()
        assert "check_substrate" in content, (
            "rn-plan.yaml must contain a check_substrate state per ENH-2098"
        )

    def test_rn_plan_check_substrate_has_full_routing(self) -> None:
        """rn-plan check_substrate must declare on_yes, on_no, and on_partial (MR-4)."""
        assert self.RN_PLAN_FILE.exists(), f"Loop file not found: {self.RN_PLAN_FILE}"
        content = self.RN_PLAN_FILE.read_text()
        cs_pos = content.find("check_substrate:")
        assert cs_pos != -1, "check_substrate state not found in rn-plan.yaml"
        # Slice to the next top-level state (research_iteration)
        next_state_pos = content.find("\n  research_iteration:", cs_pos)
        block = content[cs_pos:next_state_pos] if next_state_pos != -1 else content[cs_pos:]
        assert "on_yes:" in block, "rn-plan check_substrate must have on_yes route (MR-4)"
        assert "on_no:" in block, "rn-plan check_substrate must have on_no route (MR-4)"
        assert "on_partial:" in block, "rn-plan check_substrate must have on_partial route (MR-4)"

    def test_rn_plan_check_substrate_positioned_between_generate_rubric_and_research_iteration(
        self,
    ) -> None:
        """check_substrate in rn-plan must appear after generate_rubric and before research_iteration."""
        assert self.RN_PLAN_FILE.exists(), f"Loop file not found: {self.RN_PLAN_FILE}"
        content = self.RN_PLAN_FILE.read_text()
        generate_rubric_pos = content.find("generate_rubric:")
        check_substrate_pos = content.find("check_substrate:")
        research_iteration_pos = content.find("\n  research_iteration:")
        assert generate_rubric_pos != -1, "generate_rubric state not found in rn-plan.yaml"
        assert check_substrate_pos != -1, "check_substrate state not found in rn-plan.yaml"
        assert research_iteration_pos != -1, "research_iteration state not found in rn-plan.yaml"
        assert generate_rubric_pos < check_substrate_pos < research_iteration_pos, (
            "check_substrate must appear after generate_rubric and before research_iteration in rn-plan.yaml"
        )

    # ── ENH-2098: rn-build check_substrate gate ────────────────────────────────

    def test_rn_build_has_check_substrate(self) -> None:
        """rn-build.yaml must contain a check_substrate feasibility gate (ENH-2098)."""
        assert self.RN_BUILD_FILE.exists(), f"Loop file not found: {self.RN_BUILD_FILE}"
        content = self.RN_BUILD_FILE.read_text()
        assert "check_substrate" in content, (
            "rn-build.yaml must contain a check_substrate state per ENH-2098"
        )

    def test_rn_build_check_substrate_has_full_routing(self) -> None:
        """rn-build check_substrate must declare on_yes, on_no, and on_partial (MR-4)."""
        assert self.RN_BUILD_FILE.exists(), f"Loop file not found: {self.RN_BUILD_FILE}"
        content = self.RN_BUILD_FILE.read_text()
        cs_pos = content.find("check_substrate:")
        assert cs_pos != -1, "check_substrate state not found in rn-build.yaml"
        # Slice to the next top-level state (scope_project)
        next_state_pos = content.find("\n  scope_project:", cs_pos)
        block = content[cs_pos:next_state_pos] if next_state_pos != -1 else content[cs_pos:]
        assert "on_yes:" in block, "rn-build check_substrate must have on_yes route (MR-4)"
        assert "on_no:" in block, "rn-build check_substrate must have on_no route (MR-4)"
        assert "on_partial:" in block, "rn-build check_substrate must have on_partial route (MR-4)"

    def test_rn_build_check_substrate_positioned_between_commit_design_and_scope_project(
        self,
    ) -> None:
        """check_substrate in rn-build must appear after commit_design and before scope_project."""
        assert self.RN_BUILD_FILE.exists(), f"Loop file not found: {self.RN_BUILD_FILE}"
        content = self.RN_BUILD_FILE.read_text()
        commit_design_pos = content.find("commit_design:")
        check_substrate_pos = content.find("check_substrate:")
        scope_project_pos = content.find("\n  scope_project:")
        assert commit_design_pos != -1, "commit_design state not found in rn-build.yaml"
        assert check_substrate_pos != -1, "check_substrate state not found in rn-build.yaml"
        assert scope_project_pos != -1, "scope_project state not found in rn-build.yaml"
        assert commit_design_pos < check_substrate_pos < scope_project_pos, (
            "check_substrate must appear after commit_design and before scope_project in rn-build.yaml"
        )


class TestValidatorWarningBudget:
    """Ratchet on deterministic validator warning categories (FSM loop audit 2026-06-12).

    Every warning in the categories below must be either fixed or explicitly
    allowlisted. Allowlist entries are owned by open issues and must shrink as
    those issues are processed: test_allowlist_entries_are_not_stale fails when
    a fixed warning is still allowlisted, so the ratchet is bidirectional.
    """

    # category -> substring that identifies the warning message
    CATEGORY_PATTERNS: dict[str, str] = {
        "shared-tmp": "writes to shared '.loops/tmp",
        "partial-route": "routes only on_yes",
        "required-inputs": "does not declare required_inputs",
        "unreachable": "not reachable from initial state",
        "failure-terminal": "no predecessor state with a diagnostic action",
        "artifact-versioning": "to a flat path in an iterative cycle",
        "capture-ordering": "References ${captured.",
        "loop-reference": "does not resolve to any file",
    }

    # (loop stem, category) -> allowed warning paths.
    # partial-route: owned by the semantic MR-4 routing issue.
    # capture-ordering: only Bucket A entries remain — sub-loop false positives
    #   where the referenced capture is injected by a child loop's namespace, which
    #   the static validator can't see. Bucket B entries (refs guarded by
    #   `:default=`) were resolved by BUG-2112 Approach B: the validator now parses
    #   the `:default=` suffix (see _unguarded_captured_refs in fsm/validation.py)
    #   and no longer flags guarded references, so those entries were removed.
    ALLOWLIST: dict[tuple[str, str], set[str]] = {
        ("adopt-third-party-api", "capture-ordering"): {
            # Bucket A: enumeration injected by oracles/enumerate-and-prove sub-loop
            "states.build_playbook.action",
            "states.build_playbook_partial.action",
        },
        ("examples-miner", "capture-ordering"): {
            # Bucket A: run_optimizer injected by sub-loop
            "states.synthesize.action",
        },
        ("goal-cluster", "capture-ordering"): {
            # Bucket A: plan_display injected by parent loop via fragment contract
            "states.reassess.action",
        },
        ("integrate-sdk", "capture-ordering"): {
            # Bucket A: targets injected by oracles/enumerate-and-prove sub-loop on success path
            "states.scaffold_integration.action",
        },
        ("refine-to-ready-issue", "loop-reference"): {
            # resolve_loop_path only searches top-level of builtin loops dir; verify-confidence-scores
            # lives in loops/oracles/ and resolves correctly at runtime via the executor's loops_dir.
            "states.confidence_check.loop",
        },
    }

    @pytest.fixture
    def builtin_loops(self) -> list[Path]:
        files = sorted(p for p in BUILTIN_LOOPS_DIR.rglob("*.yaml") if is_runnable_loop(p))
        assert files, "No built-in loop files found"
        return files

    def _classify(self, message: str) -> str | None:
        for category, pattern in self.CATEGORY_PATTERNS.items():
            if pattern in message:
                return category
        return None

    def _collect_findings(self, builtin_loops: list[Path]) -> set[tuple[str, str, str]]:
        """Return (loop stem, category, warning path) for every ratcheted warning."""
        findings: set[tuple[str, str, str]] = set()
        for loop_file in builtin_loops:
            _, warnings = load_and_validate(loop_file)
            for warning in warnings:
                if warning.severity is not ValidationSeverity.WARNING:
                    continue
                category = self._classify(warning.message)
                if category is None:
                    continue
                findings.add((loop_file.stem, category, warning.path or ""))
        return findings

    def test_deterministic_warning_categories_do_not_regrow(
        self, builtin_loops: list[Path]
    ) -> None:
        """No builtin loop may add warnings in ratcheted categories without allowlisting."""
        unexpected = [
            f"{loop} [{category}] {path}"
            for loop, category, path in sorted(self._collect_findings(builtin_loops))
            if path not in self.ALLOWLIST.get((loop, category), set())
        ]
        assert not unexpected, (
            "New validator warnings in ratcheted categories (fix the loop, or add an "
            "ALLOWLIST entry referencing the issue that owns it):\n" + "\n".join(unexpected)
        )

    def test_allowlist_entries_are_not_stale(self, builtin_loops: list[Path]) -> None:
        """Every allowlist entry must still produce its warning; remove entries once fixed."""
        findings = self._collect_findings(builtin_loops)
        stale = [
            f"{loop} [{category}] {path}"
            for (loop, category), paths in sorted(self.ALLOWLIST.items())
            for path in sorted(paths)
            if (loop, category, path) not in findings
        ]
        assert not stale, (
            "Allowlist entries no longer produce warnings - remove them to lock in the fix:\n"
            + "\n".join(stale)
        )


class TestGeneralTaskLoop:
    """Tests for general-task.yaml — pre-flight baseline and routing correctness."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "general-task.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_initial_state_is_check_baseline_tests(self, data: dict) -> None:
        """Loop must start at check_baseline_tests, not define_done (ENH-2244)."""
        assert data.get("initial") == "check_baseline_tests", (
            f"initial should be 'check_baseline_tests', got {data.get('initial')!r}"
        )

    def test_check_baseline_tests_state_exists(self, data: dict) -> None:
        """check_baseline_tests state must be present (ENH-2244)."""
        assert "check_baseline_tests" in data["states"]

    def test_check_baseline_tests_routes_to_define_done(self, data: dict) -> None:
        """check_baseline_tests.next must route to define_done (ENH-2244)."""
        state = data["states"].get("check_baseline_tests", {})
        assert state.get("next") == "define_done", (
            f"check_baseline_tests.next should be 'define_done', got {state.get('next')!r}"
        )

    def test_check_baseline_tests_on_error_routes_to_define_done(self, data: dict) -> None:
        """check_baseline_tests.on_error must route to define_done so errors don't block the loop."""
        state = data["states"].get("check_baseline_tests", {})
        assert state.get("on_error") == "define_done", (
            f"check_baseline_tests.on_error should be 'define_done', got {state.get('on_error')!r}"
        )

    def test_check_baseline_tests_writes_baseline_exit_to_run_dir(self, data: dict) -> None:
        """check_baseline_tests must write baseline-exit.txt under ${context.run_dir} (ENH-2244)."""
        state = data["states"].get("check_baseline_tests", {})
        action = state.get("action", "")
        assert "${context.run_dir}/baseline-exit.txt" in action, (
            "check_baseline_tests action must write to ${context.run_dir}/baseline-exit.txt"
        )

    def test_run_final_tests_reads_baseline_exit(self, data: dict) -> None:
        """run_final_tests must read baseline-exit.txt for regression comparison (ENH-2244)."""
        state = data["states"].get("run_final_tests", {})
        action = state.get("action", "")
        assert "baseline-exit.txt" in action, (
            "run_final_tests action must reference baseline-exit.txt for baseline comparison"
        )

    def test_run_final_tests_compares_final_to_baseline(self, data: dict) -> None:
        """run_final_tests must exit 0 when final exit code matches baseline (ENH-2244)."""
        state = data["states"].get("run_final_tests", {})
        action = state.get("action", "")
        assert "BASELINE_EXIT" in action, (
            "run_final_tests must capture BASELINE_EXIT and compare against final exit code"
        )
        assert "FINAL_EXIT" in action, (
            "run_final_tests must capture FINAL_EXIT from the test command"
        )

    # ENH-2246: timeout-split tests
    def test_do_work_retry_exhausted_routes_to_capture_work_exit(self, data: dict) -> None:
        """do_work.on_retry_exhausted must route to capture_work_exit, not continue_work (ENH-2246)."""
        state = data["states"].get("do_work", {})
        assert state.get("on_retry_exhausted") == "capture_work_exit", (
            f"do_work.on_retry_exhausted should be 'capture_work_exit', got {state.get('on_retry_exhausted')!r}"
        )

    def test_capture_work_exit_state_exists(self, data: dict) -> None:
        """capture_work_exit state must be present (ENH-2246)."""
        assert "capture_work_exit" in data["states"], (
            "capture_work_exit state must exist in general-task.yaml (ENH-2246)"
        )

    def test_capture_work_exit_is_shell_type(self, data: dict) -> None:
        """capture_work_exit must be action_type: shell (ENH-2246)."""
        state = data["states"].get("capture_work_exit", {})
        assert state.get("action_type") == "shell", (
            f"capture_work_exit.action_type should be 'shell', got {state.get('action_type')!r}"
        )

    def test_capture_work_exit_writes_last_exit_code_to_run_dir(self, data: dict) -> None:
        """capture_work_exit must write last-exit-code.txt under ${context.run_dir} (ENH-2246)."""
        state = data["states"].get("capture_work_exit", {})
        action = state.get("action", "")
        assert "${context.run_dir}/last-exit-code.txt" in action, (
            "capture_work_exit action must write to ${context.run_dir}/last-exit-code.txt"
        )

    def test_capture_work_exit_routes_to_continue_work(self, data: dict) -> None:
        """capture_work_exit.next must route to continue_work (ENH-2246)."""
        state = data["states"].get("capture_work_exit", {})
        assert state.get("next") == "continue_work", (
            f"capture_work_exit.next should be 'continue_work', got {state.get('next')!r}"
        )

    def test_capture_work_exit_on_error_routes_to_continue_work(self, data: dict) -> None:
        """capture_work_exit.on_error must route to continue_work so errors don't stall (ENH-2246)."""
        state = data["states"].get("capture_work_exit", {})
        assert state.get("on_error") == "continue_work", (
            f"capture_work_exit.on_error should be 'continue_work', got {state.get('on_error')!r}"
        )

    def test_continue_work_prompt_detects_timeout_exit_code(self, data: dict) -> None:
        """continue_work prompt must reference the do_work exit code for timeout detection (ENH-2246)."""
        state = data["states"].get("continue_work", {})
        action = state.get("action", "")
        assert "work_result.exit_code" in action, (
            "continue_work prompt must reference captured.work_result.exit_code to detect timeout"
        )

    def test_continue_work_prompt_instructs_step_split_on_timeout(self, data: dict) -> None:
        """continue_work prompt must instruct step-splitting when exit code is 124 (ENH-2246)."""
        state = data["states"].get("continue_work", {})
        action = state.get("action", "")
        assert "124" in action, (
            "continue_work prompt must mention exit code 124 for timeout-split branch"
        )
        assert "split" in action.lower(), (
            "continue_work prompt must instruct step-splitting for the timeout case"
        )

    def test_continue_work_prompt_preserves_dod_remediation_for_non_timeout(
        self, data: dict
    ) -> None:
        """continue_work prompt must still instruct DoD remediation for non-timeout failures (ENH-2246)."""
        state = data["states"].get("continue_work", {})
        action = state.get("action", "")
        assert "DoD" in action or "remediation" in action or "unchecked" in action, (
            "continue_work prompt must preserve DoD-criterion remediation logic for non-timeout failures"
        )

    # ENH-2293: OOM resilience tests
    def test_do_work_retryable_exit_codes_is_124_only(self, data: dict) -> None:
        """do_work.retryable_exit_codes must be [124] to limit retry budget to timeout exits (ENH-2293)."""
        state = data["states"].get("do_work", {})
        assert state.get("retryable_exit_codes") == [124], (
            "do_work.retryable_exit_codes should be [124] — prevents non-timeout exits "
            "from consuming the full retry budget (ENH-2293)"
        )

    def test_continue_work_prompt_detects_oom_exit_code(self, data: dict) -> None:
        """continue_work prompt must reference exit -9 / OOM / SIGKILL for OOM detection (ENH-2293)."""
        state = data["states"].get("continue_work", {})
        action = state.get("action", "")
        assert any(marker in action for marker in ("-9", "OOM", "SIGKILL")), (
            "continue_work prompt must reference '-9', 'OOM', or 'SIGKILL' in the OOM branch (ENH-2293)"
        )

    def test_continue_work_prompt_routes_to_diagnose_on_oom(self, data: dict) -> None:
        """continue_work prompt must mention diagnose in the OOM branch (ENH-2293)."""
        state = data["states"].get("continue_work", {})
        action = state.get("action", "")
        assert "diagnose" in action.lower(), (
            "continue_work prompt must mention 'diagnose' in the OOM branch (ENH-2293)"
        )


class TestOpenSCADModelGeneratorLoop:
    """Structural tests for the openscad-model-generator built-in FSM loop (FEAT-2269)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "openscad-model-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must have name, initial, input_key, category, and states fields."""
        assert data.get("name") == "openscad-model-generator"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert data.get("category") == "harness"
        assert isinstance(data.get("states"), dict)

    def test_artifact_versioning_declared(self, data: dict) -> None:
        """artifact_versioning: true must be declared at top level (MR-5 compliance)."""
        assert data.get("artifact_versioning") is True, (
            "artifact_versioning: true is required — MR-5 fires for iterative "
            "generate → render_views cycle that overwrites views/*.png each pass"
        )

    def test_required_states_exist(self, data: dict) -> None:
        """All required FSM states must be present."""
        required = {
            "init",
            "plan",
            "generate",
            "render_views",
            "snapshot",
            "score",
            "check_stall",
            "maybe_stl",
            "vision_gate",
            "done",
            "diagnose",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_captures_run_dir(self, data: dict) -> None:
        """init state must be a shell action that captures run_dir."""
        state = data["states"].get("init", {})
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "plan"

    def test_init_creates_views_directory(self, data: dict) -> None:
        """init action must create a views/ subdirectory for rendered PNGs."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "views" in action, "init.action must create views/ subdirectory"

    def test_generate_routes_unconditionally_to_render_views(self, data: dict) -> None:
        """generate must route all outcomes to render_views (same anti-dead-end pattern as oracle)."""
        state = data["states"].get("generate", {})
        for route in ("on_yes", "on_no", "on_partial"):
            assert state.get(route) == "render_views", (
                f"generate.{route} should be 'render_views', got {state.get(route)!r}"
            )

    def test_render_views_has_output_contains_captured(self, data: dict) -> None:
        """render_views must have an output_contains evaluator with pattern CAPTURED (MR-1)."""
        state = data["states"].get("render_views", {})
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "output_contains", (
            "render_views.evaluate.type must be output_contains (MR-1 non-LLM evaluator)"
        )
        assert evaluator.get("pattern") == "CAPTURED"

    def test_render_views_is_shell_type(self, data: dict) -> None:
        """render_views must be a shell action."""
        state = data["states"].get("render_views", {})
        assert state.get("action_type") == "shell"

    def test_render_views_checks_openscad_on_path(self, data: dict) -> None:
        """render_views action must check for openscad binary before rendering."""
        state = data["states"].get("render_views", {})
        action = state.get("action", "")
        assert "openscad" in action, "render_views.action must reference openscad binary"
        assert "command -v openscad" in action or "which openscad" in action, (
            "render_views.action must check for openscad on PATH before rendering"
        )

    def test_render_views_uses_full_csg_render(self, data: dict) -> None:
        """render_views must use --render (full CSG), never --preview."""
        state = data["states"].get("render_views", {})
        action = state.get("action", "")
        assert "--render" in action, "render_views must use --render for full CSG"
        assert "--preview" not in action, (
            "render_views must NOT use --preview (misses non-manifold geometry)"
        )

    def test_render_views_routes_to_snapshot_on_yes(self, data: dict) -> None:
        """render_views must route to snapshot when renders succeed."""
        state = data["states"].get("render_views", {})
        assert state.get("on_yes") == "snapshot"

    def test_snapshot_routes_to_score(self, data: dict) -> None:
        """snapshot must unconditionally route to score."""
        state = data["states"].get("snapshot", {})
        assert state.get("next") == "score"

    def test_score_uses_ll_rubric_score_fragment(self, data: dict) -> None:
        """score must use the ll_rubric_score fragment."""
        state = data["states"].get("score", {})
        assert state.get("fragment") == "ll_rubric_score"

    def test_score_routes_to_maybe_stl_on_yes(self, data: dict) -> None:
        """score.on_yes must route to maybe_stl (not done) for optional STL export."""
        state = data["states"].get("score", {})
        assert state.get("on_yes") == "maybe_stl", (
            f"score.on_yes should be 'maybe_stl', got {state.get('on_yes')!r}"
        )

    def test_score_routes_to_check_stall_on_no(self, data: dict) -> None:
        """score.on_no must route to check_stall for stall detection."""
        state = data["states"].get("score", {})
        assert state.get("on_no") == "check_stall"

    def test_maybe_stl_routes_to_vision_gate(self, data: dict) -> None:
        """maybe_stl must unconditionally route to vision_gate."""
        state = data["states"].get("maybe_stl", {})
        assert state.get("next") == "vision_gate"

    def test_vision_gate_routes_to_done_on_yes(self, data: dict) -> None:
        """vision_gate must route to done when external vision passes."""
        state = data["states"].get("vision_gate", {})
        assert state.get("on_yes") == "done"

    def test_vision_gate_routes_to_generate_on_no(self, data: dict) -> None:
        """vision_gate must route to generate when external vision fails (vision critique retry)."""
        state = data["states"].get("vision_gate", {})
        assert state.get("on_no") == "generate"

    def test_vision_gate_has_round_cap(self, data: dict) -> None:
        """vision_gate action must contain ROUND_CAP to prevent ping-pong."""
        state = data["states"].get("vision_gate", {})
        action = state.get("action", "")
        assert "ROUND_CAP" in action, "vision_gate.action must have ROUND_CAP anti-ping-pong guard"

    def test_vision_gate_has_graceful_degradation(self, data: dict) -> None:
        """vision_gate must output VISION_PASS when VISION_* env vars are absent."""
        state = data["states"].get("vision_gate", {})
        action = state.get("action", "")
        assert "VISION_PASS" in action, (
            "vision_gate.action must output VISION_PASS for graceful degradation"
        )
        assert "VISION_BASE_URL" in action, "vision_gate.action must check VISION_BASE_URL env var"

    def test_context_has_view_presets_with_default(self, data: dict) -> None:
        """context block must define view_presets with a low default."""
        ctx = data.get("context", {})
        assert "view_presets" in ctx, "context must define view_presets"
        view_presets = ctx.get("view_presets", "")
        presets = [p.strip() for p in str(view_presets).split(",")]
        assert len(presets) >= 2, "view_presets default must include at least 2 camera angles"
        assert len(presets) <= 5, "view_presets default should be low (≤5) for fast demos"

    def test_context_has_export_stl_default_false(self, data: dict) -> None:
        """context block must define export_stl defaulting to false/off."""
        ctx = data.get("context", {})
        assert "export_stl" in ctx, "context must define export_stl"
        assert str(ctx.get("export_stl")).lower() in ("false", "0", "no"), (
            "export_stl must default to false/off"
        )

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        state = data["states"].get("done", {})
        assert state.get("terminal") is True

    def test_failed_state_is_terminal(self, data: dict) -> None:
        """failed state must have terminal: true."""
        state = data["states"].get("failed", {})
        assert state.get("terminal") is True

    def test_diagnose_routes_to_failed(self, data: dict) -> None:
        """diagnose must route to failed."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "failed"

    def test_imports_lib_harness(self, data: dict) -> None:
        """Loop must import lib/harness.yaml for ll_rubric_score fragment."""
        imports = data.get("import", [])
        assert "lib/harness.yaml" in imports, "must import lib/harness.yaml"


class TestInteractiveComponentGeneratorLoop:
    """Structural tests for the interactive-component-generator fan-out FSM loop (FEAT-2343)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "interactive-component-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_required_top_level_fields(self, data: dict) -> None:
        """Loop must declare name, initial, input_key, category, and a states dict."""
        assert data.get("name") == "interactive-component-generator"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "description"
        assert data.get("category") == "harness"
        assert isinstance(data.get("states"), dict)

    def test_max_steps_and_timeout_defined(self, data: dict) -> None:
        assert data.get("max_steps", 0) > 0
        assert data.get("timeout", 0) > 0

    def test_pipeline_states_exist(self, data: dict) -> None:
        """Fan-out pipeline: profile -> ideate -> rank -> worklist build/smoke/record -> select -> compose -> verify."""
        required = {
            "init",
            "profile_input",
            "ideate",
            "rank",
            "pop_next",
            "prep_component",
            "build_component",
            "smoke_component",
            "record",
            "check_any_built",
            "select_best",
            "compose",
            "verify_final",
            "vision_gate",
            "done",
            "diagnose",
            "failed",
        }
        missing = required - set(data["states"].keys())
        assert not missing, f"Missing states: {missing}"

    def test_build_component_delegates_to_oracle(self, data: dict) -> None:
        """Each candidate build reuses the generator-evaluator oracle unchanged."""
        assert data["states"]["build_component"].get("loop") == "oracles/generator-evaluator"

    def test_worklist_pop_routing(self, data: dict) -> None:
        """pop_next routes to a build on item found and to selection wrap-up when the queue is empty."""
        pop = data["states"]["pop_next"]
        assert pop.get("on_yes") == "prep_component"
        assert pop.get("on_no") == "check_any_built"

    def test_terminal_states(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True
        assert data["states"]["failed"].get("terminal") is True

    def test_imports_common_fragments(self, data: dict) -> None:
        """Imports lib/common.yaml for the shell_exit fragment used by the worklist gates."""
        assert "lib/common.yaml" in data.get("import", [])

    def test_compose_isolation_and_cdn_knobs(self, data: dict) -> None:
        """Composition tradeoffs are exposed as context knobs."""
        ctx = data.get("context", {})
        assert "compose_isolation" in ctx
        assert "allow_cdn" in ctx
        assert "n_build" in ctx
        assert "n_final" in ctx
