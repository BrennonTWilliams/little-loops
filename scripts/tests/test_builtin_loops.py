"""Tests for built-in loops shipped with the plugin."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.fragments import resolve_fragments
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
            "spike-gate",
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
                if cfg.get("terminal")
                and name in ("failed", "error", "aborted", "finalize_aborted")
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


class TestSubloopSidecarContract:
    """The sub-loop → parent outcome-channel sidecar contract (ENH-1977).

    `rn-implement`'s `classify_remediation` / `classify_decomposition` states read the
    child loop's real outcome from `${run_dir}/subloop_outcome_<ID>.txt` rather than from
    the child's terminal verdict (which collapses every non-`done` exit into `failed`).
    For that channel to be reliable, every state in a sub-loop that transitions into a
    terminal (`done` or `failed`) MUST write the sidecar token first — otherwise the
    parent `cat`s a missing file and silently falls back to `IMPLEMENT_FAILED`, losing the
    real outcome with no error (the BUG-2383-class silent-failure the audit flagged).

    This guards the load-bearing assumption confirmed across two `rn-implement` audit runs
    (2026-06-27 and 2026-06-29, Recommendation #4): a new `next: failed` / `on_error: failed`
    path added to a sub-loop without a paired sidecar write will fail here instead of
    silently corrupting parent classification at runtime.
    """

    # Sub-loops whose outcome the parent reads through the sidecar channel.
    # FEAT-2551/2552: oracles/code-run-gate.yaml writes its verdict to the
    # subloop_outcome_<ID>.txt sidecar directly, so the contract applies to it
    # too (the parent's run_code_gate dispatches to it and reads the sidecar).
    SUBLOOPS = ("rn-remediate", "rn-decompose", "oracles/code-run-gate")
    SIDECAR_MARKER = "subloop_outcome_"
    TERMINALS = {"done", "failed"}

    @staticmethod
    def _transition_targets(state: dict) -> set[str]:
        """All state names this state can transition to (next / on_* / route table)."""
        targets: set[str] = set()
        nxt = state.get("next")
        if isinstance(nxt, str):
            targets.add(nxt)
        for key, val in state.items():
            if key.startswith("on_") and isinstance(val, str):
                targets.add(val)
        route = state.get("route")
        if isinstance(route, dict):
            targets.update(v for v in route.values() if isinstance(v, str))
        return targets

    def test_terminal_routing_states_write_sidecar(self) -> None:
        """Every sub-loop state that routes to a terminal writes the outcome sidecar."""
        asserted = 0
        for name in self.SUBLOOPS:
            loop_file = BUILTIN_LOOPS_DIR / f"{name}.yaml"
            assert loop_file.exists(), f"Sub-loop not found: {loop_file}"
            data = resolve_fragments(yaml.safe_load(loop_file.read_text()), loop_file.parent)
            states = data.get("states", {})
            for state_name, cfg in states.items():
                if not isinstance(cfg, dict) or cfg.get("terminal"):
                    continue  # terminals themselves have no outbound transition
                if not (self._transition_targets(cfg) & self.TERMINALS):
                    continue  # does not reach a terminal directly
                action = cfg.get("action") or ""
                assert self.SIDECAR_MARKER in action, (
                    f"{name}.yaml: state '{state_name}' transitions to a terminal "
                    f"{self._transition_targets(cfg) & self.TERMINALS} but does not write "
                    f"'{self.SIDECAR_MARKER}<ID>.txt'. The parent's classify_remediation/"
                    f"classify_decomposition would read a missing sidecar and silently "
                    f"misclassify the outcome as IMPLEMENT_FAILED (ENH-1977 / audit Rec #4)."
                )
                asserted += 1
        # Vacuous-pass guard: if no state ever reached a terminal, the loop structure changed
        # out from under this regression guard — fail loudly rather than go green having
        # checked nothing.
        assert asserted > 0, (
            "No sub-loop state routed to a terminal; the sidecar-contract regression guard "
            "is vacuous (did rn-remediate/rn-decompose terminal structure change?)."
        )


class TestCodeRunGateOptionalParams:
    """Regression: code-run-gate must interpolate when *_cmd overrides are absent.

    rn-remediate's ``run_code_gate`` invokes ``oracles/code-run-gate`` with only
    ``issue_id`` / ``run_dir`` / ``min_pass_rate`` bound, expecting the oracle to
    resolve build/test/typecheck/lint/run commands from ``.ll/ll-config.json``.
    The optional ``*_cmd`` parameters are therefore ABSENT from the child context.

    A 2026-07-17 rn-implement run showed every gate-reaching issue (ENH-2497,
    ENH-2511) falsely tagged ``GATE_FAILED_INFRA``: ``resolve_commands`` assigned
    ``BUILD_CMD="${context.build_cmd}"`` with no ``:default=`` on the RHS. Because
    the FSM interpolates the whole action string BEFORE bash runs, the bash ``&&``
    guard does not protect the assignment — interpolation raised
    ``Path 'build_cmd' not found in context`` and the child died with an ``error``
    verdict, which ``record_gate_error`` laundered into GATE_FAILED_INFRA. Every
    ``*_cmd`` RHS must carry ``:default=``. Prior tests only exercised the
    override path (all commands supplied), so the config-resolution path regressed
    silently.
    """

    def test_resolve_commands_interpolates_without_cmd_overrides(self) -> None:
        from little_loops.fsm.interpolation import InterpolationContext, interpolate

        loop_file = BUILTIN_LOOPS_DIR / "oracles" / "code-run-gate.yaml"
        fsm, _ = load_and_validate(loop_file)
        action = fsm.states["resolve_commands"].action
        # Exactly what rn-remediate binds — no *_cmd overrides.
        child_ctx = {
            **fsm.context,
            "issue_id": "ENH-9999",
            "run_dir": "/tmp/gate-regression",
            "min_pass_rate": 0.95,
        }
        ctx = InterpolationContext(context=child_ctx, captured={}, prev=None)
        # Must not raise InterpolationError (the GATE_FAILED_INFRA root cause).
        interpolate(action, ctx)

    def test_resolve_commands_still_honours_cmd_overrides(self) -> None:
        from little_loops.fsm.interpolation import InterpolationContext, interpolate

        loop_file = BUILTIN_LOOPS_DIR / "oracles" / "code-run-gate.yaml"
        fsm, _ = load_and_validate(loop_file)
        action = fsm.states["resolve_commands"].action
        child_ctx = {
            **fsm.context,
            "issue_id": "ENH-9999",
            "run_dir": "/tmp/gate-regression",
            "min_pass_rate": 0.95,
            "build_cmd": "make build",
        }
        ctx = InterpolationContext(context=child_ctx, captured={}, prev=None)
        rendered = interpolate(action, ctx)
        assert 'BUILD_CMD="make build"' in rendered


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
        """ll-loop list includes built-in loops in the listing."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
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

    def test_sample_state_sources_refine_status_not_list(self, data: dict) -> None:
        """sample must pipe `refine-status --json` (BUG-2735), not `list --json`.

        `ll-issues list --json` never returns confidence_score/outcome_confidence/
        formatted, so the downstream Python permanently computed worst-case metrics.
        `refine-status --json` emits those keys verbatim per active issue.
        """
        action = data["states"].get("sample", {}).get("action", "")
        assert "ll-issues refine-status --json" in action
        assert "ll-issues list --json" not in action

    def test_sample_state_metrics_reflect_real_scores(self, data: dict) -> None:
        """The sample state's embedded Python must compute non-worst-case metrics
        when fed real confidence_score/outcome_confidence/formatted data, the
        shape `ll-issues refine-status --json` actually emits (BUG-2735)."""
        action = data["states"]["sample"]["action"]
        # Extract the python3 -c "..." heredoc-style script embedded in the shell action.
        match = re.search(r'python3 -c "(.*?)"\s*\n\s*ll-history', action, re.DOTALL)
        assert match, "Could not extract embedded python3 snippet from sample action"
        script = match.group(1)

        fixture_records = [
            {"confidence_score": 90, "outcome_confidence": 80, "formatted": True},
            {"confidence_score": 40, "outcome_confidence": 30, "formatted": False},
        ]
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps(fixture_records),
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
        assert "scored: 2" in output
        assert "unscored: 0" in output
        assert "unformatted: 1" in output
        assert "avg_confidence_score: 65.0" in output
        assert "below_threshold: 1" in output


class TestCuaAgentDesktopLoop:
    """Regression tests for cua-agent-desktop FSM loop.

    BUG-378: the `max_steps_summary` state prompt interpolates ${context.max_steps},
    which crashed when a parent loop forgot to forward `max_steps` via `with:`.
    Hardening: `max_steps` is now declared in the loop's `context:` block with a
    default, so the variable is always resolvable regardless of parent forwarding.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "cua-agent-desktop.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.fixture
    def context_vars(self, data: dict) -> set[str]:
        ctx = data.get("context") or {}
        return {k for k in ctx if isinstance(k, str)}

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

    def test_max_steps_in_context_block(self, context_vars: set[str]) -> None:
        """BUG-378 hardening: max_steps must be declared in context: with default 50.

        If a parent loop forgets to forward max_steps via with:, the
        max_steps_summary state prompt interpolates ${context.max_steps} and crashes
        the child. Defaulting here makes the variable always resolvable.
        """
        assert "max_steps" in context_vars, (
            "BUG-378 regression: `max_steps` is referenced by ${context.max_steps} in "
            "the max_steps_summary state but is not declared in the loop's "
            "`context:` block. Add `max_steps: 50` (matching the top-level "
            "max_steps: 50 FSM step cap) to prevent the child crash when a parent "
            "loop forgets to forward it via `with:`."
        )

    def test_max_steps_default_matches_top_level(self, data: dict) -> None:
        """context.max_steps default should mirror the FSM top-level max_steps cap.

        Keeps the prompt's reported "Max steps: N" consistent with the actual
        step cap that triggered max_steps_summary.
        """
        context = data.get("context") or {}
        top_level = data.get("max_steps")
        ctx_default = context.get("max_steps")
        assert ctx_default == top_level, (
            f"context.max_steps={ctx_default!r} should equal top-level "
            f"max_steps={top_level!r} so the summary reports the actual cap"
        )


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
        assert confidence_check.get("loop") == "oracles/verify-confidence-scores", (
            "confidence_check.loop should be 'oracles/verify-confidence-scores' (the oracle lives in "
            f"loops/oracles/ and must be referenced with the prefix), got {confidence_check.get('loop')!r}"
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

    def test_circuit_repeated_failure_configured(self, data: dict) -> None:
        """BUG-2685: the stall detector must be wired so a phantom-convergence loop
        (e.g. a sub-loop state retrying with no observable state-level progress) fires
        a distinct terminated_by: "stall_detected" and routes to diagnose, instead of
        silently burning the full max_steps budget behind a misleading
        final_state: "done" / terminated_by: "max_steps" combo."""
        repeated_failure = (data.get("circuit") or {}).get("repeated_failure") or {}
        assert repeated_failure.get("window") == 3, (
            f"circuit.repeated_failure.window should be 3, got {repeated_failure.get('window')!r}"
        )
        assert repeated_failure.get("on_repeated_failure") == "diagnose", (
            "circuit.repeated_failure.on_repeated_failure should be 'diagnose', got "
            f"{repeated_failure.get('on_repeated_failure')!r}"
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

    def test_check_epic_id_state_exists(self, data: dict) -> None:
        """check_epic_id guard state must exist (BUG-2638 defense-in-depth)."""
        assert "check_epic_id" in data["states"], (
            "State 'check_epic_id' not found — required so a stray EPIC id is decomposed, "
            "not refined as a leaf via /ll:refine-issue"
        )

    def test_resolve_issue_routes_to_check_epic_id(self, data: dict) -> None:
        """resolve_issue.next must route through the EPIC guard before check_lifetime_limit."""
        state = data["states"].get("resolve_issue", {})
        assert state.get("next") == "check_epic_id", (
            f"resolve_issue.next should be 'check_epic_id', got {state.get('next')!r}"
        )

    def test_check_epic_id_on_yes_routes_to_breakdown_issue(self, data: dict) -> None:
        """An EPIC id (exit 0 / on_yes) must route to breakdown_issue, never refine_issue."""
        state = data["states"].get("check_epic_id", {})
        assert state.get("on_yes") == "breakdown_issue", (
            f"check_epic_id.on_yes should be 'breakdown_issue', got {state.get('on_yes')!r}"
        )

    def test_check_epic_id_on_no_routes_to_check_lifetime_limit(self, data: dict) -> None:
        """A non-EPIC leaf id (exit 1 / on_no) must proceed to check_lifetime_limit."""
        state = data["states"].get("check_epic_id", {})
        assert state.get("on_no") == "check_lifetime_limit", (
            f"check_epic_id.on_no should be 'check_lifetime_limit', got {state.get('on_no')!r}"
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

    def test_diagnose_routes_to_classify_terminal(self, data: dict) -> None:
        """diagnose state must route to classify_terminal (ENH-2727), which emits the
        termination-class sentinel before reaching the `failed` terminal."""
        state = data["states"].get("diagnose", {})
        assert state.get("next") == "classify_terminal"

    def test_diagnose_is_not_terminal(self, data: dict) -> None:
        """diagnose state must not be a terminal state."""
        state = data["states"].get("diagnose", {})
        assert not state.get("terminal", False)

    # ------------------------------------------------------------------
    # ENH-2727: classify_terminal emits an infra-vs-quality sentinel that
    # autodev's skip path consumes to distinguish re-runnable infra kills
    # (SIGTERM/OOM/timeout) from genuine refine-quality failures.
    # ------------------------------------------------------------------

    def test_classify_terminal_state_exists(self, data: dict) -> None:
        """ENH-2727: classify_terminal must exist between diagnose and failed."""
        assert "classify_terminal" in data["states"], (
            "classify_terminal state not found in refine-to-ready-issue.yaml (ENH-2727)"
        )

    def test_classify_terminal_routes_to_failed(self, data: dict) -> None:
        """ENH-2727: classify_terminal must reach the failed terminal on next and
        on_error, preserving the child's failed-terminal outcome for the parent."""
        state = data["states"].get("classify_terminal", {})
        assert state.get("next") == "failed"
        assert state.get("on_error") == "failed"

    def test_classify_terminal_is_shell_action(self, data: dict) -> None:
        """ENH-2727: classify_terminal must be a non-LLM shell state (deterministic
        exit-code classification, no self-evaluation)."""
        state = data["states"].get("classify_terminal", {})
        assert state.get("action_type") == "shell"

    def test_classify_terminal_writes_sentinel(self, data: dict) -> None:
        """ENH-2727: classify_terminal must write refine-terminal-class under the
        shared run_dir so autodev's skip_inflight can consume it."""
        state = data["states"].get("classify_terminal", {})
        action = state.get("action", "")
        assert "refine-terminal-class" in action
        assert "${context.run_dir}" in action

    @pytest.mark.parametrize(
        "exit_codes,expected",
        [
            ("143 0 0", "infra"),   # SIGTERM in refine_issue
            ("0 137 0", "infra"),   # SIGKILL/OOM in refine_followup
            ("0 0 124", "infra"),   # timeout(1) kill
            ("2 0 0", "quality"),   # ll-issues tooling error (exit 2) — a real defect
            ("1 0 0", "quality"),   # ordinary non-zero
            ("", "quality"),        # no captures populated → default quality
        ],
    )
    def test_classify_terminal_classifies_by_exit_code(
        self, data: dict, tmp_path: Path, exit_codes: str, expected: str
    ) -> None:
        """ENH-2727: exit 143/137/124 (external kill) → infra; everything else →
        quality. Substitutes the first three captured exit-code refs with the given
        codes and the rest with '' (un-run states)."""
        state = data["states"].get("classify_terminal", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        codes = exit_codes.split()
        refs = [
            "${captured.refine_issue.exit_code?}",
            "${captured.refine_followup.exit_code?}",
            "${captured.breakdown_issue.exit_code?}",
        ]
        script = action
        for i, ref in enumerate(refs):
            script = script.replace(ref, codes[i] if i < len(codes) else "")
        # Remaining capture refs resolve to '' for un-run states.
        for ref in (
            "${captured.check_outcome.exit_code?}",
            "${captured.check_refine_limit.exit_code?}",
            "${captured.check_scores_from_file.exit_code?}",
            "${captured.issue_id.exit_code?}",
            "${captured.check_lifetime_limit.exit_code?}",
        ):
            script = script.replace(ref, "")
        script = script.replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"classify_terminal failed: {result.stderr}"
        sentinel = (run_dir / "refine-terminal-class").read_text().strip()
        assert sentinel == expected, (
            f"exit codes {exit_codes!r} should classify as {expected!r}, got {sentinel!r}"
        )

    # ------------------------------------------------------------------
    # BUG-2726: diagnose must carry concrete failure evidence into its prompt
    # instead of confabulating from an unrelated earlier run.
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose_source_states(data: dict) -> dict:
        """States that route into `diagnose` on failure (on_error / on_failure)."""
        return {
            name: st
            for name, st in data["states"].items()
            if st.get("on_error") == "diagnose" or st.get("on_failure") == "diagnose"
        }

    def test_diagnose_sources_all_carry_capture(self, data: dict) -> None:
        """BUG-2726 AC1: every state that routes to `diagnose` on failure must
        declare a `capture:` block so ${captured.<name>.stderr}/.output resolves
        for the failing state (a diagnose prompt with no failure evidence
        confabulates a diagnosis of an unrelated earlier run)."""
        sources = self._diagnose_source_states(data)
        # Sanity: the known failure-source set must be present so this test does
        # not silently pass on an empty set if the routing is refactored away.
        expected = {
            "resolve_issue",
            "check_lifetime_limit",
            "refine_issue",
            "confidence_check",
            "check_outcome",
            "check_refine_limit",
            "check_scores_from_file",
            "breakdown_issue",
        }
        assert expected <= set(sources), (
            f"diagnose-source states changed; expected at least {expected}, got {set(sources)}"
        )
        missing = [name for name, st in sources.items() if not st.get("capture")]
        assert not missing, (
            f"States routing to diagnose without a capture: block: {missing} "
            "(BUG-2726 — diagnose cannot surface their stderr/output without one)"
        )

    def test_diagnose_prompt_interpolates_failure_context(self, data: dict) -> None:
        """BUG-2726 AC2/AC3: the diagnose prompt must interpolate the failing
        state name, its exit code, and the current run dir — not just the issue
        ID (models test_diagnose_error_prompt_uses_run_dir)."""
        action = data["states"].get("diagnose", {}).get("action", "")
        assert isinstance(action, str)
        for ref in ("${prev.state", "${prev.exit_code", "${context.run_dir}"):
            assert ref in action, (
                f"diagnose prompt must interpolate {ref} so the diagnosis cites the "
                "failing state / exit code / run dir instead of guessing (BUG-2726)"
            )

    def test_diagnose_prompt_surfaces_captured_stderr(self, data: dict) -> None:
        """BUG-2726 AC2: the diagnose prompt must surface the captured stderr of
        the failure-source states, with confidence_check (a sub-loop with no
        .stderr key) falling back to its .output event stream."""
        action = data["states"].get("diagnose", {}).get("action", "")
        # resolve_issue captures under the `issue_id` key, not `resolve_issue`.
        for cap in ("issue_id", "refine_issue", "check_outcome", "check_scores_from_file"):
            assert f"${{captured.{cap}.stderr" in action, (
                f"diagnose prompt must reference ${{captured.{cap}.stderr}} (BUG-2726)"
            )
        # confidence_check sub-loop has no stderr channel — fall back to output.
        assert "${captured.confidence_check.output" in action, (
            "diagnose prompt must fall back to ${captured.confidence_check.output} for "
            "the confidence_check sub-loop, which has no .stderr key (BUG-2726)"
        )

    def test_diagnose_captured_refs_are_nullable(self, data: dict) -> None:
        """BUG-2726: because `diagnose` is shared across 8+ failure sources, only
        one capture is populated per run; every ${captured.<name>.*} ref in the
        prompt must use the `?` nullable suffix (or :default=) so an unpopulated
        capture resolves to '' instead of raising InterpolationError."""
        action = data["states"].get("diagnose", {}).get("action", "")
        refs = re.findall(r"\$\{captured\.[^}]*\}", action)
        offenders = [
            m for m in refs if not (m.rstrip("}").endswith("?") or ":default=" in m)
        ]
        assert not offenders, (
            f"diagnose ${{captured.*}} refs must be nullable (?/:default=): {offenders} "
            "(BUG-2726 — a bare ref to an unpopulated capture raises InterpolationError)"
        )

    def test_diagnose_prompt_confines_to_current_run(self, data: dict) -> None:
        """BUG-2726: the diagnose prompt must explicitly confine analysis to the
        current run (the reported bug analyzed an unrelated .loops/.history run)."""
        action = data["states"].get("diagnose", {}).get("action", "").lower()
        assert ".loops/.history" in action or "this run" in action, (
            "diagnose prompt must instruct the session to analyze only the current "
            "run (e.g. name .loops/.history to exclude, or say 'this run') — BUG-2726"
        )

    def test_check_outcome_surfaces_inner_stderr(self, data: dict) -> None:
        """BUG-2726 AC4: check_outcome wraps `ll-issues show` in a heredoc; on a
        real inner failure it must write the inner stderr to sys.stderr and exit
        with an error code (>=2 → verdict 'error' → on_error: diagnose), not let
        a bare json.loads traceback exit 1 (verdict 'no' → check_decision_needed,
        misclassifying an infra failure as a low outcome score)."""
        action = data["states"].get("check_outcome", {}).get("action", "")
        assert "r.stderr" in action and "sys.stderr" in action, (
            "check_outcome heredoc must forward the inner ll-issues stderr to "
            "sys.stderr so ${captured.check_outcome.stderr} carries the real "
            "failure (BUG-2726)"
        )
        assert "sys.exit(2" in action, (
            "check_outcome must sys.exit(2+) on inner failure so it routes to "
            "on_error: diagnose, not on_no (BUG-2726)"
        )

    def test_check_scores_from_file_surfaces_inner_stderr(self, data: dict) -> None:
        """BUG-2726 AC4: same inner-stderr surfacing requirement as check_outcome."""
        action = data["states"].get("check_scores_from_file", {}).get("action", "")
        assert "r.stderr" in action and "sys.stderr" in action, (
            "check_scores_from_file heredoc must forward the inner ll-issues "
            "stderr to sys.stderr (BUG-2726)"
        )
        assert "sys.exit(2" in action, (
            "check_scores_from_file must sys.exit(2+) on inner failure so it "
            "routes to on_error: diagnose (BUG-2726)"
        )

    def test_diagnose_prompt_renders_sigterm_exit_code(self, data: dict) -> None:
        """BUG-2726 AC5: a refine kill with exit 143 must produce a diagnose
        prompt that cites exit 143 and the failing state — and the unpopulated
        captures of the OTHER failure sources must resolve to '' (not raise),
        proving the nullable-suffix design holds at interpolation time."""
        from little_loops.fsm.interpolation import InterpolationContext, interpolate

        action = data["states"]["diagnose"]["action"]
        ctx = InterpolationContext(
            context={"run_dir": ".loops/.runs/2026-07-21T214941-autodev"},
            # Only refine_issue ran; every other failure-source capture is absent.
            captured={
                "issue_id": {"output": "ENH-2722", "stderr": "", "exit_code": 0},
                "refine_issue": {
                    "output": "…researching ENH-2722…",
                    "stderr": "Terminated",
                    "exit_code": 143,
                },
            },
            prev={"state": "refine_issue", "exit_code": 143, "output": "…researching ENH-2722…"},
        )
        # Must not raise despite the 6+ unpopulated ${captured.*.stderr?} refs.
        rendered = interpolate(action, ctx)
        assert "143" in rendered, "diagnose prompt must cite the SIGTERM exit code 143 (BUG-2726)"
        assert "refine_issue" in rendered, "diagnose prompt must name the failing state (BUG-2726)"
        assert "2026-07-21T214941-autodev" in rendered, (
            "diagnose prompt must cite the current run's run_dir (BUG-2726)"
        )
        assert "ENH-2722" in rendered

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
        """mark_wire_done.next must route to check_decision_mid_wire (BUG-2528).

        The mid-chain decision gate then routes to confidence_check on no.
        Mirrors the check_decision_mid_refine rewire at line 1309.
        """
        state = data["states"].get("mark_wire_done", {})
        assert state.get("next") == "check_decision_mid_wire", (
            f"mark_wire_done.next should be 'check_decision_mid_wire' (BUG-2528), "
            f"got {state.get('next')!r}"
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
        """context.readiness_threshold and outcome_threshold must be 85/65 to match next-action defaults (BUG-2035)."""
        ctx = data.get("context", {})
        assert ctx.get("readiness_threshold") == 85, (
            f"context.readiness_threshold should be 85 (matches next-action fallback), "
            f"got {ctx.get('readiness_threshold')!r}"
        )
        assert ctx.get("outcome_threshold") == 65, (
            f"context.outcome_threshold should be 65 (matches next-action fallback), "
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

    def test_refine_issue_next_is_check_decision_mid_refine(self, data: dict) -> None:
        """refine_issue.next must route to check_decision_mid_refine (BUG-2528).

        The mid-chain decision gate then routes to check_wire_done on no.
        """
        state = data["states"].get("refine_issue", {})
        assert state.get("next") == "check_decision_mid_refine", (
            f"refine_issue.next should be 'check_decision_mid_refine' (BUG-2528), "
            f"got {state.get('next')!r}"
        )

    def test_refine_followup_next_is_check_decision_mid_refine(self, data: dict) -> None:
        """refine_followup.next must route to check_decision_mid_refine (BUG-2528).

        The mid-chain decision gate then routes to check_wire_done on no.
        Identical routing to refine_issue.next — single consult per refine pass.
        """
        state = data["states"].get("refine_followup", {})
        assert state.get("next") == "check_decision_mid_refine", (
            f"refine_followup.next should be 'check_decision_mid_refine' (BUG-2528), "
            f"got {state.get('next')!r}"
        )

    # --- BUG-2528: mid-chain decision_needed gates ------------------------

    def test_check_decision_mid_refine_state_exists(self, data: dict) -> None:
        """check_decision_mid_refine state must exist as a mid-chain gate after refine (BUG-2528)."""
        assert "check_decision_mid_refine" in data["states"], (
            "State 'check_decision_mid_refine' not found in refine-to-ready-issue.yaml — "
            "required so a decision_needed flag set by /ll:refine-issue short-circuits "
            "before the remaining wire + confidence_check invocations (BUG-2528)"
        )

    def test_check_decision_mid_refine_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_decision_mid_refine must use shell_exit fragment to route on exit code."""
        state = data["states"].get("check_decision_mid_refine", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_mid_refine.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_decision_mid_refine_action_consults_decision_needed(self, data: dict) -> None:
        """check_decision_mid_refine.action must run ll-issues check-flag decision_needed."""
        state = data["states"].get("check_decision_mid_refine", {})
        action = state.get("action", "")
        assert "ll-issues check-flag" in action and "decision_needed" in action, (
            f"check_decision_mid_refine.action should run 'll-issues check-flag ... decision_needed', "
            f"got {action!r}"
        )

    def test_check_decision_mid_refine_on_yes_routes_to_done(self, data: dict) -> None:
        """check_decision_mid_refine.on_yes (decision_needed=true) must exit via done
        so the outer autodev loop's check_decision_after_refine routes to run_decide."""
        state = data["states"].get("check_decision_mid_refine", {})
        assert state.get("on_yes") == "done", (
            f"check_decision_mid_refine.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_decision_mid_refine_on_no_routes_to_check_wire_done(self, data: dict) -> None:
        """check_decision_mid_refine.on_no must route to check_wire_done (no flag → fall through)."""
        state = data["states"].get("check_decision_mid_refine", {})
        assert state.get("on_no") == "check_wire_done", (
            f"check_decision_mid_refine.on_no should be 'check_wire_done', "
            f"got {state.get('on_no')!r}"
        )

    def test_check_decision_mid_refine_on_error_routes_to_check_wire_done(self, data: dict) -> None:
        """check_decision_mid_refine.on_error must fall through to check_wire_done
        (a transient check-flag failure should not stall the sub-loop)."""
        state = data["states"].get("check_decision_mid_refine", {})
        assert state.get("on_error") == "check_wire_done", (
            f"check_decision_mid_refine.on_error should be 'check_wire_done', "
            f"got {state.get('on_error')!r}"
        )

    def test_check_decision_mid_wire_state_exists(self, data: dict) -> None:
        """check_decision_mid_wire state must exist as a mid-chain gate after wire (BUG-2528)."""
        assert "check_decision_mid_wire" in data["states"], (
            "State 'check_decision_mid_wire' not found in refine-to-ready-issue.yaml — "
            "required so a decision_needed flag set by /ll:wire-issue short-circuits "
            "before the confidence_check invocation (BUG-2528)"
        )

    def test_check_decision_mid_wire_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_decision_mid_wire must use shell_exit fragment to route on exit code."""
        state = data["states"].get("check_decision_mid_wire", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_mid_wire.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_decision_mid_wire_action_consults_decision_needed(self, data: dict) -> None:
        """check_decision_mid_wire.action must run ll-issues check-flag decision_needed."""
        state = data["states"].get("check_decision_mid_wire", {})
        action = state.get("action", "")
        assert "ll-issues check-flag" in action and "decision_needed" in action, (
            f"check_decision_mid_wire.action should run 'll-issues check-flag ... decision_needed', "
            f"got {action!r}"
        )

    def test_check_decision_mid_wire_on_yes_routes_to_done(self, data: dict) -> None:
        """check_decision_mid_wire.on_yes (decision_needed=true) must exit via done
        so the outer autodev/recursive-refine loop's post-return decision gate handles decide."""
        state = data["states"].get("check_decision_mid_wire", {})
        assert state.get("on_yes") == "done", (
            f"check_decision_mid_wire.on_yes should be 'done', got {state.get('on_yes')!r}"
        )

    def test_check_decision_mid_wire_on_no_routes_to_confidence_check(self, data: dict) -> None:
        """check_decision_mid_wire.on_no must route to confidence_check (no flag → fall through)."""
        state = data["states"].get("check_decision_mid_wire", {})
        assert state.get("on_no") == "confidence_check", (
            f"check_decision_mid_wire.on_no should be 'confidence_check', "
            f"got {state.get('on_no')!r}"
        )

    def test_check_decision_mid_wire_on_error_routes_to_confidence_check(self, data: dict) -> None:
        """check_decision_mid_wire.on_error must fall through to confidence_check
        (a transient check-flag failure should not stall the sub-loop)."""
        state = data["states"].get("check_decision_mid_wire", {})
        assert state.get("on_error") == "confidence_check", (
            f"check_decision_mid_wire.on_error should be 'confidence_check', "
            f"got {state.get('on_error')!r}"
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
        """context.parent must default to '' and init action must forward --parent.

        ENH-2481: the init action now forwards ``--parent`` to ``ll-issues list``
        (inheriting transitive descendant resolution) instead of post-filtering
        the JSON with an inline ``i.get('parent') == parent`` equality check.
        """
        assert data.get("context", {}).get("parent") == ""
        init_action = data["states"].get("init", {}).get("action", "")
        assert "${context.parent}" in init_action or "context.parent" in init_action
        # Must forward the CLI flag (transitive) rather than inline direct-only equality.
        assert "PARENT_ARG" in init_action
        assert "--parent" in init_action
        assert "i.get('parent') == parent" not in init_action

    def test_init_supports_ids_filter(self, data: dict) -> None:
        """context.ids must default to '' and init action must branch on it (ENH-2658).

        When ``context.ids`` is set (comma-separated), the init action must
        bypass the ``ll-issues list`` call and write the parsed IDs directly
        to ``pending.txt`` — overriding ``type``/``parent`` filters.
        """
        assert data.get("context", {}).get("ids") == ""
        init_action = data["states"].get("init", {}).get("action", "")
        assert "${context.ids}" in init_action or "context.ids" in init_action
        # The branch must write pending.txt directly when ids is set,
        # bypassing ll-issues list.
        assert "tr ',' '\\n'" in init_action or 'tr "," "\\n"' in init_action, (
            "init action must split ids on commas into pending.txt (ENH-2658)"
        )

    def test_mr3_no_loops_tmp_writes(self, data: dict) -> None:
        """No state writes to .loops/tmp/ (MR-3: per-instance run_dir isolation,
        ENH-2500). The pending list lives under ${context.run_dir}/pending.txt,
        not the shared .loops/tmp/ directory — concurrent instances would
        otherwise clobber each other's queues.
        """
        for name, state in data["states"].items():
            action = state.get("action", "")
            if isinstance(action, str):
                assert ".loops/tmp/" not in action, (
                    f"State '{name}' writes to .loops/tmp/ — use "
                    f"${{context.run_dir}}/ instead (ENH-2500)"
                )

    def test_diagnose_error_prompt_uses_run_dir(self, data: dict) -> None:
        """The diagnose_error LLM prompt must reference the per-run path,
        not the old .loops/tmp/prompt-across-issues-pending.txt (ENH-2500).
        """
        state = data["states"].get("diagnose_error", {})
        action = state.get("action", "")
        assert isinstance(action, str)
        assert ".loops/tmp/prompt-across-issues-pending.txt" not in action, (
            "diagnose_error prompt still references the shared pending path "
            "(ENH-2500). Replace with ${context.run_dir}/pending.txt."
        )
        assert "${context.run_dir}/pending.txt" in action, (
            "diagnose_error prompt must surface the per-run path "
            "${context.run_dir}/pending.txt (ENH-2500)."
        )

    def test_shared_state_ok_is_false(self, data: dict) -> None:
        """shared_state_ok must be false once pending.txt is per-instance
        (ENH-2500). Absence is treated equivalent to False (schema default).
        """
        assert data.get("shared_state_ok", False) is False, (
            "shared_state_ok must be False now that the pending path is per-instance (ENH-2500)."
        )

    def test_scope_declared(self, data: dict) -> None:
        """prompt-across-issues must declare scope: [${context.run_dir}] so
        concurrent LockManager instances on disjoint run_dirs do not conflict
        (ENH-2500).
        """
        scope = data.get("scope")
        assert scope is not None, (
            "prompt-across-issues.yaml must declare a 'scope' field for "
            "per-instance lock isolation (ENH-2500)."
        )
        assert isinstance(scope, list), f"scope must be a list, got {type(scope).__name__}"
        assert "${context.run_dir}" in scope, (
            f"scope must contain '${{context.run_dir}}' template, got {scope!r}"
        )

    def test_init_writes_under_run_dir(self, data: dict) -> None:
        """init state writes pending.txt under ${context.run_dir} (ENH-2500)."""
        init_action = data["states"].get("init", {}).get("action", "")
        assert "${context.run_dir}/pending.txt" in init_action, (
            "init state must write pending.txt under ${context.run_dir} (ENH-2500)."
        )

    def test_advance_writes_under_run_dir(self, data: dict) -> None:
        """advance state mutates pending.txt under ${context.run_dir} (ENH-2500)."""
        advance_action = data["states"].get("advance", {}).get("action", "")
        assert "${context.run_dir}/pending.txt" in advance_action, (
            "advance state must read/write pending.txt under ${context.run_dir} (ENH-2500)."
        )


class TestAutoRefineAndImplementLoop:
    """Structural tests for the auto-refine-and-implement FSM loop.

    The loop resolves an issue set (scope → SprintManager, else the ranked
    backlog) and delegates the interleaved per-issue refine+implement to the
    autodev engine, then computes a ground-truth closure verdict in finalize.
    """

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
        """All required states must be present (delegate-to-autodev structure)."""
        required = {
            "init",
            "resolve_set",
            "checkout_epic_branch",
            "delegate",
            "recheck_set",
            "verify",
            "record_error",
            "finalize",
            "done",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_legacy_two_phase_states_removed(self, data: dict) -> None:
        """The old refine-all-then-implement-all states must be gone — refinement and
        implementation are now interleaved per issue inside autodev."""
        states = set(data["states"].keys())
        for legacy in (
            "get_next_issue",
            "refine_issue",
            "implement_chain",
            "record_processed",
            "skip_refinement",
        ):
            assert legacy not in states, f"legacy state {legacy!r} must be removed"

    def test_init_state_is_shell_and_routes_to_resolve_set(self, data: dict) -> None:
        """init must be a shell action that unconditionally advances to resolve_set."""
        init = data["states"].get("init", {})
        assert init.get("action_type") == "shell"
        assert init.get("next") == "resolve_set"

    def test_done_state_is_terminal(self, data: dict) -> None:
        """done state must have terminal: true."""
        done_state = data["states"].get("done", {})
        assert done_state.get("terminal") is True

    def test_resolve_set_captures_issue_set(self, data: dict) -> None:
        """resolve_set must capture as 'issue_set' for the autodev sub-loop input."""
        state = data["states"].get("resolve_set", {})
        assert state.get("capture") == "issue_set"

    def test_resolve_set_routes(self, data: dict) -> None:
        """resolve_set routes a non-empty set to checkout_epic_branch (ENH-2601),
        an empty set to finalize."""
        state = data["states"].get("resolve_set", {})
        assert state.get("on_yes") == "checkout_epic_branch"
        assert state.get("on_no") == "finalize"

    def test_resolve_set_supports_scope_branching(self, data: dict) -> None:
        """resolve_set scoped path uses load_or_resolve + EPIC; backlog path uses
        ll-issues next-issues."""
        action = data["states"]["resolve_set"].get("action", "")
        assert "load_or_resolve" in action, (
            "resolve_set scoped path must use SprintManager.load_or_resolve"
        )
        assert "ll-issues next-issues" in action, (
            "resolve_set backlog path must use ll-issues next-issues"
        )
        assert "EPIC" in action, (
            "resolve_set scoped path must support EPIC IDs (BUG-2136 preservation)"
        )

    def test_delegate_uses_autodev_engine(self, data: dict) -> None:
        """delegate must run the autodev sub-loop with the resolved set as input."""
        state = data["states"].get("delegate", {})
        assert state.get("loop") == "autodev", (
            f"delegate.loop should be 'autodev', got {state.get('loop')!r}"
        )
        with_ = state.get("with", {})
        assert "issue_set" in with_.get("input", ""), (
            "delegate must pass the captured issue_set as autodev's input"
        )

    def test_delegate_crash_routes_to_record_error(self, data: dict) -> None:
        """on_error must route to a DISTINCT crash state (not finalize/verify directly)
        so an infrastructure crash is recorded, not laundered into a clean no-op
        (ENH-2005). on_success/on_failure route through recheck_set (ENH-2615) so
        mid-run decomposed descendants get re-dispatched before verify."""
        state = data["states"].get("delegate", {})
        assert state.get("on_success") == "recheck_set"
        assert state.get("on_failure") == "recheck_set"
        assert state.get("on_error") == "record_error"
        assert state.get("on_error") != state.get("on_success")

    def test_recheck_set_structure_and_routing(self, data: dict) -> None:
        """ENH-2615: recheck_set re-resolves the EPIC's descendant set after each
        delegate pass. New undispatched descendants → cycle back to delegate
        (re-entry re-attaches the epic-branch worktree); drained/none → verify."""
        state = data["states"].get("recheck_set", {})
        assert state.get("fragment") == "shell_exit"
        assert state.get("capture") == "issue_set", (
            "recheck_set must overwrite the issue_set capture so delegate "
            "re-reads the new batch on re-entry"
        )
        assert state.get("on_yes") == "delegate"
        assert state.get("on_no") == "verify"
        assert state.get("on_error") == "verify"

    def test_recheck_set_gates_on_epic_scope_and_caps_cycles(self, data: dict) -> None:
        """ENH-2615: re-resolution only applies to EPIC scopes (backlog/sprint
        scopes must NOT pick up unrelated new issues mid-run) and must be
        cycle-capped so a pathological set can't loop delegate forever."""
        action = data["states"].get("recheck_set", {}).get("action", "")
        assert "EPIC-" in action, "recheck_set must gate on an EPIC-NNN scope"
        assert "load_or_resolve" in action, (
            "recheck_set must re-resolve via SprintManager.load_or_resolve "
            "(now transitive, ENH-2615)"
        )
        assert "auto-refine-and-implement-dispatched.txt" in action, (
            "recheck_set must subtract already-dispatched IDs from the ledger"
        )
        assert "recheck-count" in action, "recheck_set must cap re-dispatch cycles"

    def test_recheck_set_folds_back_abandoned_residual(self, data: dict, tmp_path: Path) -> None:
        """ENH-2686: recheck_set must fold ${run_dir}/autodev-queue.txt residual
        IDs (abandoned mid-drain, ENH-2657's detection signal) into the
        re-dispatch batch — not just newly-detected descendants. Residual IDs
        are already present in dispatched.txt from the initial seed, so the
        comm -23 diff against dispatched.txt alone excludes them forever
        without this explicit union."""
        action = data["states"]["recheck_set"].get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        # dispatched.txt already contains both IDs from the initial seed.
        (run_dir / "auto-refine-and-implement-dispatched.txt").write_text("ENH-1\nENH-2\n")
        # ENH-1 was abandoned mid-drain (still sitting in the residual queue).
        (run_dir / "autodev-queue.txt").write_text("ENH-1\n")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        mock_python3 = bin_dir / "python3"
        # Stub SprintManager resolution to return the same descendant set as
        # before (no NEW descendants) — isolates the residual-fold behavior.
        mock_python3.write_text("#!/bin/bash\necho 'ENH-1,ENH-2'\n")
        mock_python3.chmod(0o755)
        script = action.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.scope}", "EPIC-9")
        script = f"export PATH={bin_dir}:$PATH\n" + script
        result = subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"recheck_set must exit 0 to re-dispatch the abandoned residual: {result.stderr}"
        )
        assert "ENH-1" in result.stdout, (
            f"abandoned residual ENH-1 must be re-dispatched: {result.stdout!r}"
        )
        dispatched = (run_dir / "auto-refine-and-implement-dispatched.txt").read_text()
        assert dispatched.count("ENH-1") == 1, (
            "residual ID already in dispatched.txt must not be appended a "
            f"second time (breaks later comm -23 dedup): {dispatched!r}"
        )

    def test_recheck_set_no_residual_no_new_exits(self, data: dict, tmp_path: Path) -> None:
        """A clean drain (no residual, no new descendants) must still exit 1
        (routes to verify) — ENH-2686 must not turn every recheck into a
        re-dispatch when there is genuinely nothing left to do."""
        action = data["states"]["recheck_set"].get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "auto-refine-and-implement-dispatched.txt").write_text("ENH-1\nENH-2\n")
        # No autodev-queue.txt at all — mirrors a fully-drained autodev run.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        mock_python3 = bin_dir / "python3"
        mock_python3.write_text("#!/bin/bash\necho 'ENH-1,ENH-2'\n")
        mock_python3.chmod(0o755)
        script = action.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${context.scope}", "EPIC-9")
        script = f"export PATH={bin_dir}:$PATH\n" + script
        result = subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)
        assert result.returncode == 1, (
            f"recheck_set must exit 1 when there is nothing new or residual: {result.stdout!r}"
        )

    def test_resolve_set_seeds_dispatched_ledger(self, data: dict) -> None:
        """ENH-2615: resolve_set must record the initially-dispatched IDs so
        recheck_set can diff later resolutions against what already ran."""
        action = data["states"]["resolve_set"].get("action", "")
        assert "auto-refine-and-implement-dispatched.txt" in action

    def test_finalize_input_size_prefers_dispatched_ledger(self, data: dict) -> None:
        """ENH-2615: with multiple delegate dispatches, the captured issue_set
        only holds the LAST batch — finalize's parked-rate denominator must
        prefer the cumulative dispatched ledger."""
        action = data["states"]["finalize"].get("action", "")
        assert "auto-refine-and-implement-dispatched.txt" in action

    def test_record_error_tracks_crash_and_finalizes(self, data: dict) -> None:
        """record_error writes a distinct errored.txt and routes to finalize."""
        state = data["states"].get("record_error", {})
        action = state.get("action", "")
        assert "auto-refine-and-implement-errored.txt" in action
        assert state.get("next") == "finalize"

    def test_has_optional_scope_parameter(self, data: dict) -> None:
        """scope must be in context with empty default (optional sprint/EPIC scoping)."""
        ctx = data.get("context", {})
        assert "scope" in ctx, "context must have a 'scope' field for sprint/EPIC scoping"
        assert ctx["scope"] == "", (
            "context.scope must default to empty string (backlog rank when unset)"
        )

    # --- ENH-2601: epic-branch checkout + post-implementation verify --------

    def test_checkout_epic_branch_routes_to_delegate(self, data: dict) -> None:
        """checkout_epic_branch is a best-effort gate that always continues to
        delegate, even on an unexpected error (never blocks the run)."""
        state = data["states"].get("checkout_epic_branch", {})
        assert state.get("action_type") == "shell"
        assert state.get("next") == "delegate"
        assert state.get("on_error") == "delegate"

    def test_checkout_epic_branch_gated_on_epic_scope_and_config(self, data: dict) -> None:
        """checkout_epic_branch must gate on scope being an EPIC id AND
        parallel.epic_branches.enabled, and must not switch the working tree
        (Option A — create-without-switch, no `git checkout`)."""
        action = data["states"].get("checkout_epic_branch", {}).get("action", "")
        assert "EPIC-" in action
        assert "epic_cfg.enabled" in action
        assert '"branch", branch, base' in action, (
            "must create via `git branch <name> <base>`, not `git checkout -b`"
        )
        assert "checkout" not in action.lower().replace("checkout_epic_branch", ""), (
            "Option A must not literally `git checkout` the epic branch"
        )

    def test_checkout_epic_branch_imports_and_calls_resolver(self, data: dict) -> None:
        """ENH-2656 Option B: the heredoc must import the shared resolvers from
        worktree_utils and derive name+base through them (not re-derive inline),
        so FEAT-2652 touches only resolve_epic_base()."""
        action = data["states"].get("checkout_epic_branch", {}).get("action", "")
        assert "resolve_epic_base" in action, (
            "must import/call resolve_epic_base (ENH-2656 Option B), not re-derive base inline"
        )
        assert "resolve_epic_branch_name" in action, (
            "must derive the branch name via resolve_epic_branch_name (ENH-2656)"
        )
        # The name is single-sourced now — no inline f-string format of the branch.
        assert 'f"{epic_cfg.prefix}' not in action, (
            "branch name must come from resolve_epic_branch_name, not an inline f-string"
        )

    def test_checkout_epic_branch_reuses_ensure_epic_branch_shape(self, data: dict) -> None:
        """Must mirror WorkerPool._ensure_epic_branch's idempotency checks (local
        rev-parse, then remote ls-remote) before creating the branch."""
        action = data["states"].get("checkout_epic_branch", {}).get("action", "")
        assert "rev-parse" in action
        assert "ls-remote" in action

    def test_verify_state_exists_and_routes_to_merge_epic_branch(self, data: dict) -> None:
        """verify runs unconditionally after delegate and always continues to
        merge_epic_branch (pass/fail is advisory, folded into summary.json,
        not gating). BUG-2614: merge_epic_branch was inserted between verify
        and finalize."""
        state = data["states"].get("verify", {})
        assert state.get("action_type") == "shell"
        assert state.get("next") == "merge_epic_branch"
        assert state.get("on_error") == "merge_epic_branch"

    def test_verify_reads_project_test_and_lint_cmd(self, data: dict) -> None:
        """verify must source project.test_cmd/lint_cmd from ll-config.json (no
        ${config.*} FSM namespace exists) and skip when test_cmd is unconfigured."""
        action = data["states"].get("verify", {}).get("action", "")
        assert "test_cmd" in action
        assert "lint_cmd" in action
        assert "'skipped'" in action

    # --- ENH-2609: worktree-per-delegate so commits land on the epic branch --

    def test_checkout_epic_branch_captures_branch_name(self, data: dict) -> None:
        """checkout_epic_branch must capture the branch name (stdout) as
        'epic_branch' so delegate's worktree: template can reference it; log
        lines are diverted to stderr so stdout is the branch name only."""
        state = data["states"].get("checkout_epic_branch", {})
        assert state.get("capture") == "epic_branch"
        assert "sys.stderr" in state.get("action", ""), (
            "log lines must go to stderr; stdout is reserved for the branch name"
        )

    def test_delegate_declares_worktree(self, data: dict) -> None:
        """delegate must attach a scratch worktree to the captured epic branch
        (empty capture → no-op) so autodev's commits land on the epic branch."""
        state = data["states"].get("delegate", {})
        assert state.get("worktree") == "${captured.epic_branch.output}"

    def test_verify_attaches_epic_worktree(self, data: dict) -> None:
        """verify must run test/lint against the epic branch's actual state via
        the shared verify_epic_branch_before_merge free function (BUG-2614:
        extracted from orchestrator._verify_epic_branch_before_merge, which
        internally does the checkout_existing=True/delete_branch=False scratch
        worktree dance) when epic-branch-name.txt exists — the main tree never
        has the commits. verify_before_merge=True since this state's checks
        run unconditionally, unlike merge_epic_branch's config-gated call."""
        action = data["states"].get("verify", {}).get("action", "")
        assert "epic-branch-name.txt" in action
        assert "verify_epic_branch_before_merge" in action
        assert "verify_before_merge=True" in action
        # BUG-2629: verify must isolate PYTHONPATH from editable-install .pth shadowing.
        assert "src_dir=" in action
        # ENH-2630: verify persists the epic branch tip so merge_epic_branch can
        # reuse this run's verdict instead of re-running the suite.
        assert "verify-sha.txt" in action

    def test_merge_epic_branch_reuses_fresh_verify_verdict(self, data: dict) -> None:
        """ENH-2630: merge_epic_branch must read the verify state's persisted
        verdict + SHA and skip its own re-run when the tip is unchanged."""
        action = data["states"].get("merge_epic_branch", {}).get("action", "")
        assert "verify-verdict.txt" in action
        assert "verify-sha.txt" in action

    def test_merge_epic_branch_forwards_src_dir(self, data: dict) -> None:
        """BUG-2629: merge_epic_branch's verify_epic_branch_before_merge call must
        forward src_dir so its independent scratch-worktree run also isolates the
        import path from the editable-install .pth."""
        action = data["states"].get("merge_epic_branch", {}).get("action", "")
        assert "verify_epic_branch_before_merge" in action
        assert "src_dir=" in action

    def test_finalize_computes_closures_from_epic_branch(self, data: dict) -> None:
        """finalize must source completed/ and status:done snapshots from the epic
        branch when epic-branch-name.txt exists — closures live on the branch,
        not the main tree, so a successful epic run must not report phantom."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "epic-branch-name.txt" in action
        assert "ls-tree" in action

    # --- ENH-2376: partial-with-errors verdict -------------------------------

    def test_finalize_has_partial_with_errors_verdict(self, data: dict) -> None:
        """finalize must distinguish closed+crashed (partial-with-errors) from a clean
        partial so autodev crashes are not laundered into plain 'partial' (ENH-2376)."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "partial-with-errors" in action

    def test_finalize_sources_autodev_ledgers(self, data: dict) -> None:
        """finalize must read autodev's passed/skipped ledgers (shared run_dir)."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "autodev-passed.txt" in action
        assert "autodev-skipped.txt" in action

    _ID_PREFIX_TO_DIR = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}

    def _write_done_in_place_fixture(self, run_dir: Path, issue_id: str) -> None:
        """Write a status:done issue .md fixture under run_dir/.issues/<category>/.

        BUG-2403: leaf issues complete IN PLACE (no move to completed/), so the
        real `ll-issues list --json --status done` call in finalize's action must
        see them via a category-directory fixture, not a completed/ entry.
        """
        category = self._ID_PREFIX_TO_DIR.get(issue_id.split("-")[0], "enhancements")
        issues_dir = run_dir / ".issues" / category
        issues_dir.mkdir(parents=True, exist_ok=True)
        (issues_dir / f"P3-{issue_id}-x.md").write_text(f"---\nid: {issue_id}\nstatus: done\n---\n")

    def _run_finalize(
        self,
        data: dict,
        run_dir: Path,
        closed: tuple[str, ...] = (),
        passed: tuple[str, ...] = (),
        skipped: int = 0,
        errored: int = 0,
        baseline: tuple[str, ...] = (),
        done_in_place: tuple[str, ...] = (),
        done_baseline: tuple[str, ...] = (),
        gate_blocked: int = 0,
        decision_unresolved: int = 0,
        skipped_reasons: tuple[str, ...] = (),
        issue_set: tuple[str, ...] = (),
        verify_verdict: str | None = None,
        verify_returncode: str | None = None,
        inflight: str | None = None,
        queue: tuple[str, ...] = (),
    ) -> dict:
        """Execute finalize against ground-truth completed/ + done dirs; return summary.json.

        ENH-2385: finalize derives one half of CLOSED from a .issues/completed/ diff
        against the init baseline (`closed`/`baseline`, decomposed parents).
        BUG-2403: the other half comes from a status:done diff (`done_in_place`/
        `done_baseline`, leaf issues completed in place). CLOSED is the union;
        NOT_CLOSED is autodev-passed − that union. `passed` are autodev's passed
        (attempted-implementation) IDs.

        ENH-2404: `gate_blocked` (count) seeds autodev-gate-blocked.txt with bare
        IDs. `skipped_reasons` writes one "ID-{i}  {reason}" line per entry to
        autodev-skipped.txt (REASON-suffixed, overrides the bare-ID `skipped`
        write when non-empty) — used to exercise skipped_breakdown. `issue_set`
        substitutes ${captured.issue_set.output} so parked_rate has a denominator.

        ENH-2601: `verify_verdict`, when given, seeds verify-verdict.txt (the
        artifact the new verify state writes) so summary.json's verify_verdict
        key can be exercised; when omitted, the file is absent and finalize
        must default to "not_run".
        """
        p = "auto-refine-and-implement"
        if verify_verdict is not None:
            (run_dir / "verify-verdict.txt").write_text(verify_verdict + "\n")
        # ENH-2631: seed verify-returncode.txt (the flat-text exit-code artifact
        # the verify state writes on failure) so summary.json's verify_returncode
        # key can be exercised; when omitted the file is absent and finalize must
        # default the field to null.
        if verify_returncode is not None:
            (run_dir / "verify-returncode.txt").write_text(verify_returncode + "\n")
        (run_dir / f"{p}-completed-baseline.txt").write_text(
            "".join(f"{i}\n" for i in sorted(baseline))
        )
        completed_dir = run_dir / ".issues" / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        for cid in set(closed) | set(baseline):
            (completed_dir / f"P3-{cid}-x.md").write_text("done\n")
        # BUG-2403: done-baseline.txt mirrors completed-baseline.txt for the
        # in-place completion path — issues already status:done before the run.
        (run_dir / f"{p}-done-baseline.txt").write_text(
            "".join(f"{i}\n" for i in sorted(done_baseline))
        )
        for did in done_in_place:
            self._write_done_in_place_fixture(run_dir, did)
        # finalize sources autodev's ledgers under the shared run_dir.
        (run_dir / "autodev-passed.txt").write_text("".join(f"{i}\n" for i in passed))
        if skipped_reasons:
            skipped_text = "".join(
                f"ID-{i}  {reason}\n" for i, reason in enumerate(skipped_reasons)
            )
        else:
            skipped_text = "".join(f"ID-{i}\n" for i in range(skipped))
        (run_dir / "autodev-skipped.txt").write_text(skipped_text)
        (run_dir / "autodev-gate-blocked.txt").write_text(
            "".join(f"GB-{i}\n" for i in range(gate_blocked))
        )
        (run_dir / "autodev-decision-unresolved.txt").write_text(
            "".join(f"DU-{i}\n" for i in range(decision_unresolved))
        )
        (run_dir / f"{p}-errored.txt").write_text("".join(f"ID-{i}\n" for i in range(errored)))
        # BUG-2636: seed the autodev-inflight sentinel so finalize's
        # INFLIGHT_UNRESOLVED signal (and the phantom verdict it can trigger) is
        # exercisable. Absent by default → INFLIGHT_UNRESOLVED=0.
        if inflight is not None:
            (run_dir / "autodev-inflight").write_text(inflight)
        # ENH-2657: seed autodev-queue.txt with residual (undrained) IDs so
        # finalize's ABANDONED signal (and the incomplete-abandoned verdict it
        # triggers) is exercisable. Absent/empty by default → abandoned=0.
        if queue:
            (run_dir / "autodev-queue.txt").write_text("".join(f"{i}\n" for i in queue))
        action = data["states"]["finalize"].get("action", "")
        script = action.replace("${context.run_dir}", str(run_dir))
        script = script.replace("${captured.issue_set.output}", ",".join(issue_set))
        result = subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)
        summary = json.loads((run_dir / "summary.json").read_text())
        # BUG-2636: finalize routes the FSM terminal on the real verdict — a
        # `phantom` run exits non-zero (→ the `incomplete` terminal, rendered as
        # not-success by ll-loop) while every other verdict exits 0 (→ `done`).
        # summary.json is written before the routing exit, so it is always readable.
        expected_rc = 1 if summary["verdict"] in ("phantom", "incomplete-abandoned") else 0
        assert result.returncode == expected_rc, (
            f"finalize exit {result.returncode} != {expected_rc} for "
            f"verdict={summary['verdict']}: {result.stderr}"
        )
        return summary

    def test_finalize_verdict_table(self, data: dict, tmp_path: Path) -> None:
        """Shell-execution regression (ENH-2385/2376): the verdict reflects real
        closure (ground-truth completed/ diff), not an ll-auto exit proxy."""
        # (closed, passed, skipped, errored, expected_verdict)
        cases = [
            (("FEAT-1", "FEAT-2"), ("FEAT-1", "FEAT-2"), 0, 0, "success"),
            (("FEAT-1",), ("FEAT-1", "FEAT-2"), 0, 0, "partial"),  # FEAT-2 not closed
            (("FEAT-1",), ("FEAT-1",), 2, 0, "partial"),  # closed + skips
            (("FEAT-1",), ("FEAT-1",), 0, 2, "partial-with-errors"),
            ((), ("FEAT-2",), 0, 0, "phantom"),  # passed, closed nothing
            ((), (), 0, 2, "phantom"),  # crashed, closed nothing
            ((), (), 1, 0, "no-op"),  # only skips, nothing attempted
            ((), (), 0, 0, "no-op"),
        ]
        for i, (closed, passed, skip, err, expected) in enumerate(cases):
            run_dir = tmp_path / f"run-{i}"
            run_dir.mkdir()
            summary = self._run_finalize(
                data, run_dir, closed=closed, passed=passed, skipped=skip, errored=err
            )
            assert summary["verdict"] == expected, (
                f"closed={closed} passed={passed} skip={skip} err={err}: "
                f"expected {expected!r}, got {summary['verdict']!r} ({summary})"
            )

    def test_finalize_counts_decomposition_closure_as_closed(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2385: a decomposed umbrella that autodev git-mv'd into completed/ counts
        as CLOSED even though it never went through ll-auto / passed. Ground truth is
        the completed/ diff, not the implement ledger."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data, run_dir, closed=("EPIC-9",), passed=(), skipped=1, errored=0
        )
        assert summary["closed"] == 1, f"decomposition closure must count, got {summary}"

    def test_finalize_counts_done_in_place_leaf_as_closed(self, data: dict, tmp_path: Path) -> None:
        """BUG-2403: a leaf issue that reaches status: done IN PLACE (no move to
        completed/, per ENH-1418) must count as CLOSED and yield a non-phantom
        verdict. Previously CLOSED was computed strictly from a completed/ diff,
        so leaf closures (which never move) were silently dropped and a clean
        leaf sprint reported phantom on every run."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            passed=("FEAT-1",),
            done_in_place=("FEAT-1",),
        )
        assert summary["closed"] == 1, f"in-place leaf closure must count, got {summary}"
        assert summary["not_closed"] == 0, f"closed leaf must not also be not_closed: {summary}"
        assert summary["verdict"] in ("success", "partial"), (
            f"a closed leaf sprint must not report phantom, got {summary}"
        )

    def test_finalize_excludes_pre_existing_done_baseline_from_closed(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-2403: an issue that was ALREADY status:done before the run (in the
        done-baseline) must not be double-counted as newly closed just because
        it's still done at finalize time."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            passed=(),
            done_baseline=("FEAT-9",),
            done_in_place=("FEAT-9",),
        )
        assert summary["closed"] == 0, (
            f"pre-existing done issue must not count as newly closed: {summary}"
        )

    def test_finalize_combines_completed_and_done_in_place_closures(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-2403: CLOSED must be the UNION of the completed/ diff (decomposed
        parents) and the status:done diff (leaf issues) — a sprint with one of
        each must count both, not just one."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            closed=("EPIC-9",),
            passed=("FEAT-1",),
            done_in_place=("FEAT-1",),
        )
        assert summary["closed"] == 2, f"union of both closure paths expected: {summary}"

    def test_finalize_not_closed_excludes_completed_and_avoids_double_count(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2385: NOT_CLOSED = autodev-passed − completed. A passed issue that DID
        close is excluded; a passed issue still open is counted exactly once."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            closed=("FEAT-1",),
            passed=("FEAT-1", "FEAT-2"),
            skipped=0,
            errored=0,
        )
        assert summary["closed"] == 1 and summary["not_closed"] == 1, (
            f"FEAT-1 closed, FEAT-2 not-closed expected, got {summary}"
        )

    def test_finalize_not_closed_excludes_done_in_place_leaf(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-2403: NOT_CLOSED must exclude a leaf that closed via the
        done-in-place path (not just the completed/ path) — a passed issue
        still open is the only case that should count as not_closed."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            passed=("FEAT-1", "FEAT-2"),
            done_in_place=("FEAT-1",),
        )
        assert summary["closed"] == 1 and summary["not_closed"] == 1, (
            f"FEAT-1 closed in place, FEAT-2 not-closed expected, got {summary}"
        )

    def test_finalize_not_closed_excludes_pre_baseline_closure_in_passed(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-2403: NOT_CLOSED exclusion must use the FULL current closed set
        (completed-now ∪ done-now), not just this run's new closures. An issue
        that was already closed BEFORE the run (in the baseline) but reappears
        in autodev-passed is still closed — it must not be flagged not_closed.
        This preserves the pre-fix `completed-now` exclusion semantics for the
        completed/ path while extending it to the new done-in-place path."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            baseline=("FEAT-1",),
            passed=("FEAT-1",),
            done_baseline=("FEAT-2",),
            done_in_place=("FEAT-2",),
        )
        assert summary["closed"] == 0, f"neither closure is new this run: {summary}"
        assert summary["not_closed"] == 0, (
            f"FEAT-1 closed pre-baseline must not count as not_closed: {summary}"
        )

    def test_finalize_summary_has_closure_keys(self, data: dict, tmp_path: Path) -> None:
        """summary.json must report the full accounting keys (ENH-2385)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",))
        for key in ("verdict", "closed", "not_closed", "skipped", "errored"):
            assert key in summary, f"summary.json missing {key!r}: {summary}"

    # --- ENH-2404: gate-blocked surfacing, skipped_breakdown, parked_rate ----

    def test_finalize_summary_has_enh_2404_keys(self, data: dict, tmp_path: Path) -> None:
        """summary.json must additively report skipped_breakdown/gate_blocked/parked_rate."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",))
        for key in ("skipped_breakdown", "gate_blocked", "parked_rate"):
            assert key in summary, f"summary.json missing {key!r}: {summary}"

    # --- ENH-2601: verify_verdict additive key -------------------------------

    def test_finalize_sources_verify_verdict_artifact(self, data: dict) -> None:
        """finalize must read verify-verdict.txt — the artifact the new verify
        state writes."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "verify-verdict.txt" in action

    def test_finalize_surfaces_verify_verdict(self, data: dict, tmp_path: Path) -> None:
        """A run where verify passed/failed must surface that verdict verbatim."""
        for verdict in ("passed", "failed", "skipped"):
            run_dir = tmp_path / f"run-{verdict}"
            run_dir.mkdir()
            summary = self._run_finalize(
                data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",), verify_verdict=verdict
            )
            assert summary["verify_verdict"] == verdict, f"expected {verdict!r}, got {summary}"

    def test_finalize_verify_verdict_defaults_to_not_run(self, data: dict, tmp_path: Path) -> None:
        """When verify never ran (e.g. resolve_set's on_no/on_error path skipped
        straight to finalize), verify_verdict must default to 'not_run', not omit
        the key or crash."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir)
        assert summary["verify_verdict"] == "not_run", f"got {summary}"

    # --- ENH-2631: verify_returncode + collection_error verdict class ---------

    def test_finalize_sources_verify_returncode_artifact(self, data: dict) -> None:
        """finalize must read verify-returncode.txt — the flat-text exit-code
        artifact the verify state writes on failure (ENH-2631)."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "verify-returncode.txt" in action

    def test_finalize_surfaces_verify_returncode(self, data: dict, tmp_path: Path) -> None:
        """A verify failure must surface its exit code as a JSON number so a
        collection_error (exit 2) is triageable without a re-run (ENH-2631)."""
        for verdict, code in (
            ("failed", "1"),
            ("collection_error", "2"),
            ("config_error", "1"),
        ):
            run_dir = tmp_path / f"run-{verdict}"
            run_dir.mkdir()
            summary = self._run_finalize(
                data,
                run_dir,
                closed=("FEAT-1",),
                passed=("FEAT-1",),
                verify_verdict=verdict,
                verify_returncode=code,
            )
            assert summary["verify_verdict"] == verdict, f"got {summary}"
            assert summary["verify_returncode"] == int(code), f"got {summary}"

    def test_finalize_verify_returncode_defaults_to_null(self, data: dict, tmp_path: Path) -> None:
        """When verify passed/skipped/never-ran, no exit-code artifact exists —
        verify_returncode must be JSON null, not omitted or a crash (ENH-2631)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",), verify_verdict="passed"
        )
        assert summary["verify_returncode"] is None, f"got {summary}"

    def test_finalize_sources_gate_blocked_ledger(self, data: dict) -> None:
        """finalize must read autodev-gate-blocked.txt — previously never referenced,
        so a learning-gate block vanished from summary.json with no trace."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "autodev-gate-blocked.txt" in action, (
            "finalize must source autodev-gate-blocked.txt to surface gate_blocked"
        )

    def test_finalize_gate_blocked_count_surfaces(self, data: dict, tmp_path: Path) -> None:
        """A run with learning-gate blocks must report gate_blocked >= 1, not drop them."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",), gate_blocked=2
        )
        assert summary["gate_blocked"] == 2, f"expected gate_blocked=2, got {summary}"

    def test_finalize_gate_blocked_zero_when_no_ledger_entries(
        self, data: dict, tmp_path: Path
    ) -> None:
        """A run with no gate-blocks must report gate_blocked=0, not omit the key."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",))
        assert summary["gate_blocked"] == 0, f"expected gate_blocked=0, got {summary}"

    # --- BUG-2595: decision-unresolved surfacing (mirrors ENH-2404 gate_blocked) --

    def test_finalize_sources_decision_unresolved_ledger(self, data: dict) -> None:
        """finalize must read autodev-decision-unresolved.txt — previously never
        referenced, so a decision-unresolved issue vanished from summary.json
        with no trace (same failure mode ENH-2404 fixed for gate_blocked)."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "autodev-decision-unresolved.txt" in action, (
            "finalize must source autodev-decision-unresolved.txt to surface decision_unresolved"
        )

    def test_finalize_decision_unresolved_count_surfaces(self, data: dict, tmp_path: Path) -> None:
        """A run with decision-unresolved issues must report decision_unresolved
        >= 1, not drop them."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",), decision_unresolved=2
        )
        assert summary["decision_unresolved"] == 2, f"expected decision_unresolved=2, got {summary}"

    def test_finalize_decision_unresolved_zero_when_no_ledger_entries(
        self, data: dict, tmp_path: Path
    ) -> None:
        """A run with no decision-unresolved issues must report
        decision_unresolved=0, not omit the key."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",))
        assert summary["decision_unresolved"] == 0, f"expected decision_unresolved=0, got {summary}"

    def test_finalize_stale_inflight_counts_as_unresolved(self, data: dict, tmp_path: Path) -> None:
        """BUG-2636: an issue left in the autodev-inflight sentinel — dispatched
        but never landed in any passed/skipped/gate-blocked ledger — must surface
        as inflight_unresolved=1 (the exact hole that let run 20260713T190717 leave
        ENH-2578 in-flight yet report verdict=no-op / green "done")."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, issue_set=("ENH-2578",), inflight="ENH-2578")
        assert summary["inflight_unresolved"] == 1, f"expected inflight_unresolved=1, got {summary}"
        # Closed nothing + an unresolved in-flight issue ⇒ phantom, not no-op.
        assert summary["verdict"] == "phantom", (
            f"stale inflight must escalate the verdict to phantom, got {summary}"
        )

    def test_finalize_inflight_not_counted_when_issue_closed(
        self, data: dict, tmp_path: Path
    ) -> None:
        """BUG-2636: a sentinel that merely lingered after its issue actually
        closed (via either closure path) is NOT unresolved — finalize must exclude
        it, so a fully successful run is never mislabeled phantom."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            closed=("FEAT-1",),
            passed=("FEAT-1",),
            issue_set=("FEAT-1",),
            inflight="FEAT-1",
        )
        assert summary["inflight_unresolved"] == 0, (
            f"a closed issue's lingering sentinel must not count, got {summary}"
        )
        assert summary["verdict"] == "success", f"expected success, got {summary}"

    def test_finalize_abandoned_queue_counts_and_diverts_terminal(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2657: a non-empty residual autodev-queue.txt at finalize (autodev hit
        its timeout/max_steps mid-drain) must surface as abandoned>0, fold into
        parked_rate, and divert off the green `done` terminal via the
        incomplete-abandoned verdict — even when the run closed something (the exact
        18-of-27 case from EPIC-058 that rendered green `partial`)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            closed=("FEAT-1",),
            passed=("FEAT-1",),
            issue_set=("FEAT-1", "ENH-2", "ENH-3", "ENH-4"),
            queue=("ENH-2", "ENH-3", "ENH-4"),
        )
        assert summary["abandoned"] == 3, f"expected abandoned=3, got {summary}"
        assert summary["parked_rate"] > 0, f"abandoned must lift parked_rate, got {summary}"
        # Verdict names the abandonment (Option B) and diverts to incomplete even
        # though CLOSED > 0 — the whole point of the ENH.
        assert summary["verdict"] == "incomplete-abandoned", (
            f"an abandoned queue must not render as green partial, got {summary}"
        )
        assert (run_dir / "auto-refine-and-implement-abandoned.txt").exists(), (
            "abandoned artifact listing the residual IDs must be written"
        )

    def test_finalize_empty_queue_is_unaffected(self, data: dict, tmp_path: Path) -> None:
        """ENH-2657: a run that fully drained its queue (empty/absent
        autodev-queue.txt) is unchanged — abandoned=0 and the same verdict as today."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data, run_dir, closed=("FEAT-1", "FEAT-2"), passed=("FEAT-1", "FEAT-2")
        )
        assert summary["abandoned"] == 0, f"empty queue must report abandoned=0, got {summary}"
        assert summary["verdict"] == "success", f"drained run unaffected, got {summary}"

    def test_finalize_abandoned_zero_when_residual_all_closed(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2657 late-close race: residual queue entries that actually closed
        (present in the closed-now union) must NOT count as abandoned — the
        comm -23 subtraction holds."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            closed=("FEAT-1",),
            passed=("FEAT-1",),
            issue_set=("FEAT-1",),
            queue=("FEAT-1",),
        )
        assert summary["abandoned"] == 0, (
            f"a residual entry that actually closed must not count, got {summary}"
        )
        assert summary["verdict"] == "success", f"expected success, got {summary}"

    def test_finalize_zero_inflight_unresolved_by_default(self, data: dict, tmp_path: Path) -> None:
        """BUG-2636: with no sentinel present, inflight_unresolved must be 0 and
        present (never omitted) in summary.json."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, closed=("FEAT-1",), passed=("FEAT-1",))
        assert summary["inflight_unresolved"] == 0, f"expected 0, got {summary}"

    def test_finalize_phantom_routes_to_incomplete_terminal(self, data: dict) -> None:
        """BUG-2636: finalize routes the FSM terminal on the real verdict —
        on_yes→done (progress / benign no-op) and on_no→incomplete (phantom, exit
        non-zero). ll-loop derives success from the terminal state NAME, so a
        phantom run must land on a terminal != `done`."""
        state = data["states"].get("finalize", {})
        assert state.get("on_yes") == "done", "finalize must route success/no-op to done"
        assert state.get("on_no") == "incomplete", (
            "finalize must route a phantom (non-zero exit) to the incomplete terminal"
        )
        # shell_exit fragment supplies exit-code evaluation; a bare `next` would
        # ignore the routing entirely.
        assert state.get("fragment") == "shell_exit", (
            "finalize must use the shell_exit fragment so its exit code selects the terminal"
        )
        assert "next" not in state, "finalize must not keep an unconditional next: done"
        incomplete = data["states"].get("incomplete", {})
        assert incomplete.get("terminal") is True, "incomplete must be a terminal state"

    def test_finalize_skipped_breakdown_aggregates_by_reason(
        self, data: dict, tmp_path: Path
    ) -> None:
        """skipped_breakdown must distinguish decomposed (success) from refine_failed /
        low_readiness (failures) instead of collapsing all skips into one integer."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            passed=(),
            skipped_reasons=("decomposed", "refine_failed", "low_readiness", "low_readiness"),
        )
        breakdown = summary["skipped_breakdown"]
        assert breakdown == {"decomposed": 1, "refine_failed": 1, "low_readiness": 2}, (
            f"expected per-reason counts, got {breakdown}"
        )

    def test_finalize_skipped_breakdown_buckets_refine_failed_infra(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2727: the infra-class reason token refine_failed_infra must bucket
        distinctly in skipped_breakdown, separate from the quality refine_failed
        bucket — proving an infra kill is surfaced as re-runnable, not a quality
        defect."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            passed=(),
            skipped_reasons=(
                "refine_failed",
                "refine_failed_infra",
                "refine_failed_infra",
            ),
        )
        breakdown = summary["skipped_breakdown"]
        assert breakdown == {"refine_failed": 1, "refine_failed_infra": 2}, (
            f"refine_failed_infra must bucket distinctly from refine_failed, got {breakdown}"
        )

    def test_finalize_skipped_breakdown_back_compat_bare_id_lines(
        self, data: dict, tmp_path: Path
    ) -> None:
        """Legacy bare-ID skip lines (no REASON suffix) must not crash the breakdown
        parser — they fall back to an 'unspecified' bucket."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir, passed=(), skipped=3)
        assert summary["skipped"] == 3
        assert summary["skipped_breakdown"] == {"unspecified": 3}, (
            f"bare-ID lines should bucket under 'unspecified', got {summary['skipped_breakdown']}"
        )

    def test_finalize_parked_rate_computation(self, data: dict, tmp_path: Path) -> None:
        """parked_rate = (skipped + not_closed + gate_blocked) / input_size."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(
            data,
            run_dir,
            closed=("FEAT-1",),
            passed=("FEAT-1", "FEAT-2"),
            skipped_reasons=("low_readiness",),
            gate_blocked=1,
            issue_set=("FEAT-1", "FEAT-2", "FEAT-3", "FEAT-4"),
        )
        # not_closed = FEAT-2 (passed but not in closed-now-union) = 1
        # parked = skipped(1) + not_closed(1) + gate_blocked(1) = 3; input_size = 4
        assert summary["parked_rate"] == pytest.approx(0.75), f"got {summary}"

    def test_finalize_parked_rate_zero_when_input_size_unavailable(
        self, data: dict, tmp_path: Path
    ) -> None:
        """parked_rate must default to 0.0 (not crash / divide-by-zero) when
        issue_set was never captured (e.g. empty backlog)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        summary = self._run_finalize(data, run_dir)
        assert summary["parked_rate"] == 0.0, f"got {summary}"

    def test_init_snapshots_completed_baseline(self, data: dict, tmp_path: Path) -> None:
        """ENH-2385: init must snapshot the completed/ set so finalize can compute a
        ground-truth closure diff."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        completed = run_dir / ".issues" / "completed"
        completed.mkdir(parents=True)
        (completed / "P3-FEAT-1-x.md").write_text("done\n")
        action = data["states"]["init"].get("action", "")
        script = action.replace("${context.run_dir}", str(run_dir))
        subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)
        baseline = run_dir / "auto-refine-and-implement-completed-baseline.txt"
        assert baseline.exists() and "FEAT-1" in baseline.read_text(), (
            "init must snapshot existing completed/ issues into the baseline file"
        )

    def test_init_snapshots_done_baseline(self, data: dict, tmp_path: Path) -> None:
        """BUG-2403: init must snapshot the live status:done set so finalize can
        compute a ground-truth closure diff for issues that complete in place
        (ENH-1418) and never enter completed/."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        issues_dir = run_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (issues_dir / "P3-FEAT-1-x.md").write_text("---\nid: FEAT-1\nstatus: done\n---\n")
        action = data["states"]["init"].get("action", "")
        script = action.replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)
        assert result.returncode == 0, f"init action failed: {result.stderr}"
        baseline = run_dir / "auto-refine-and-implement-done-baseline.txt"
        assert baseline.exists() and "FEAT-1" in baseline.read_text(), (
            "init must snapshot existing status:done issues into the done-baseline file"
        )

    def test_finalize_writes_summary_json(self, data: dict) -> None:
        """finalize must emit summary.json + the subloop_outcome token (ENH-2005)."""
        action = data["states"].get("finalize", {}).get("action", "")
        assert "summary.json" in action
        assert "verdict" in action
        assert "subloop_outcome_auto-refine-and-implement" in action


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


class TestCheckoutEpicBranchConfigReadShell:
    """ENH-2601 end-to-end: exercise checkout_epic_branch's config-gated branch
    creation against a real git repo (mirrors
    test_rn_implement.py::TestCheckLearningReadyConfigReadShell)."""

    def _run(
        self, tmp_path: Path, *, scope: str, epic_branches_enabled: bool
    ) -> subprocess.CompletedProcess:
        if not (tmp_path / ".git").exists():
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
            (tmp_path / "README.md").write_text("x\n")
            subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"parallel": {"epic_branches": {"enabled": epic_branches_enabled}}})
        )
        issues_dir = tmp_path / ".issues" / "epics"
        issues_dir.mkdir(parents=True, exist_ok=True)
        (issues_dir / "P3-EPIC-42-my-epic.md").write_text(
            "---\nid: EPIC-42\ntitle: My Epic Title\n---\n# EPIC-42: My Epic Title\n"
        )

        run_dir = tmp_path / "run"
        run_dir.mkdir(exist_ok=True)

        loop = yaml.safe_load((BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())
        action = loop["states"]["checkout_epic_branch"]["action"]
        action = action.replace("${context.scope}", scope).replace(
            "${context.run_dir}", str(run_dir)
        )
        return subprocess.run(
            ["bash", "-c", action], cwd=tmp_path, capture_output=True, text=True, timeout=30
        )

    def _branches(self, tmp_path: Path) -> str:
        return subprocess.run(
            ["git", "branch", "--list"], cwd=tmp_path, capture_output=True, text=True
        ).stdout

    def test_creates_branch_when_epic_scope_and_enabled(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, scope="EPIC-42", epic_branches_enabled=True)
        assert result.returncode == 0, result.stderr
        assert "epic/epic-42-my-epic-title" in self._branches(tmp_path), result.stdout

    def test_no_branch_when_config_disabled(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, scope="EPIC-42", epic_branches_enabled=False)
        assert result.returncode == 0, result.stderr
        assert "epic/" not in self._branches(tmp_path), result.stdout

    def test_no_branch_when_scope_is_not_an_epic(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, scope="my-sprint", epic_branches_enabled=True)
        assert result.returncode == 0, result.stderr
        assert "epic/" not in self._branches(tmp_path), result.stdout

    def test_does_not_switch_working_tree(self, tmp_path: Path) -> None:
        """Option A: creates the branch but never checks it out — the main tree
        must stay on whatever branch was already active."""
        result = self._run(tmp_path, scope="EPIC-42", epic_branches_enabled=True)
        assert result.returncode == 0, result.stderr
        current = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert current == "main", f"main tree must stay on main, got {current!r}"

    def test_idempotent_on_second_run(self, tmp_path: Path) -> None:
        """Running twice must not error (mirrors _ensure_epic_branch's local
        rev-parse idempotency check)."""
        first = self._run(tmp_path, scope="EPIC-42", epic_branches_enabled=True)
        assert first.returncode == 0, first.stderr
        second = self._run(tmp_path, scope="EPIC-42", epic_branches_enabled=True)
        assert second.returncode == 0, second.stderr


class TestVerifyStateConfigReadShell:
    """ENH-2601 end-to-end: exercise verify's project.test_cmd/lint_cmd config
    read against a stubbed command (mirrors
    test_general_task_loop.py::test_falls_back_to_config_test_cmd)."""

    def _run(self, tmp_path: Path, *, test_cmd: str | None, lint_cmd: str | None = None) -> str:
        (tmp_path / ".ll").mkdir()
        project: dict = {}
        if test_cmd is not None:
            project["test_cmd"] = test_cmd
        if lint_cmd is not None:
            project["lint_cmd"] = lint_cmd
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps({"project": project}))

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        loop = yaml.safe_load((BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())
        action = loop["states"]["verify"]["action"].replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(
            ["bash", "-c", action], cwd=tmp_path, capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stderr
        return (run_dir / "verify-verdict.txt").read_text().strip()

    def test_skipped_when_test_cmd_unconfigured(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, test_cmd=None) == "skipped"

    def test_passed_when_test_cmd_succeeds(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, test_cmd="true") == "passed"

    def test_failed_when_test_cmd_fails(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, test_cmd="false") == "failed"

    def test_collection_error_when_test_cmd_exits_2(self, tmp_path: Path) -> None:
        """ENH-2631: exit 2 (pytest collection/usage error) yields the distinct
        collection_error verdict class, not a plain 'failed'."""
        assert self._run(tmp_path, test_cmd="sh -c 'exit 2'") == "collection_error"

    def test_config_error_when_stderr_reports_missing_script(self, tmp_path: Path) -> None:
        """ENH-2742: a "missing script" stderr (e.g. npm test run from the wrong
        directory) is a config/usage error, not a real test failure — it must
        yield the distinct config_error verdict, not a plain 'failed'."""
        cmd = 'sh -c \'echo "npm error Missing script: \\"test\\"" >&2; exit 1\''
        assert self._run(tmp_path, test_cmd=cmd) == "config_error"

    def test_failure_persists_returncode_and_detail_artifacts(self, tmp_path: Path) -> None:
        """ENH-2631: a verify failure must persist the exit code and a detail
        snippet as flat-text artifacts in the run_dir for post-hoc triage."""
        assert self._run(tmp_path, test_cmd="sh -c 'echo boom >&2; exit 1'") == "failed"
        run_dir = tmp_path / "run"
        assert (run_dir / "verify-returncode.txt").read_text().strip() == "1"
        assert "boom" in (run_dir / "verify-detail.txt").read_text()

    def test_passed_leaves_no_detail_artifact(self, tmp_path: Path) -> None:
        """A passing verify writes no detail file (only failures carry detail)."""
        assert self._run(tmp_path, test_cmd="true") == "passed"
        assert not (tmp_path / "run" / "verify-detail.txt").exists()

    def test_detail_keeps_failure_summary_past_leading_warnings(self, tmp_path: Path) -> None:
        """ENH-2641: when leading stderr warnings precede the stdout FAILED
        summary (the BUG-2640 shape), verify-detail.txt must retain the summary
        tail, not just the warnings. A first-500-char prefix of `stderr or
        stdout` would keep only the warnings and drop the FAILED lines."""
        # 60 stderr warning lines, then a stdout FAILED/summary block, then exit 1.
        cmd = (
            "sh -c '"
            "for i in $(seq 1 60); do echo PytestBenchmarkWarning line $i >&2; done; "
            'echo "=== short test summary info ==="; '
            'echo "FAILED test_issues_cli.py::test_case_1"; '
            'echo "1 failed, 100 passed in 71.02s"; '
            "exit 1'"
        )
        assert self._run(tmp_path, test_cmd=cmd) == "failed"
        detail = (tmp_path / "run" / "verify-detail.txt").read_text()
        assert "short test summary info" in detail
        assert "FAILED test_issues_cli.py::test_case_1" in detail
        assert "1 failed, 100 passed" in detail

    def test_failed_when_lint_cmd_fails(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, test_cmd="true", lint_cmd="false") == "failed"

    def test_lint_cmd_optional(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, test_cmd="true", lint_cmd=None) == "passed"

    def test_config_error_on_epic_branch_path(self, tmp_path: Path) -> None:
        """ENH-2742: the epic-branch call site (verify_epic_branch_before_merge's
        `message`, not raw stderr) must also classify a "missing script" failure
        as config_error — this path had zero coverage of classify() before."""
        epic_branch = "epic/epic-42-my-epic-title"
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("x\n")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "branch", epic_branch], cwd=tmp_path, check=True)

        (tmp_path / ".ll").mkdir()
        cmd = 'sh -c \'echo "npm error Missing script: \\"test\\"" >&2; exit 1\''
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"test_cmd": cmd}})
        )

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "epic-branch-name.txt").write_text(epic_branch)

        loop = yaml.safe_load((BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())
        action = (
            loop["states"]["verify"]["action"]
            .replace("${context.run_dir}", str(run_dir))
            .replace("${context.scope}", "EPIC-42")
        )
        result = subprocess.run(
            ["bash", "-c", action], cwd=tmp_path, capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "verify-verdict.txt").read_text().strip() == "config_error"


class TestMergeEpicBranchConfigReadShell:
    """BUG-2614 end-to-end: exercise merge_epic_branch's config-gated merge-back
    against a real git repo (mirrors TestCheckoutEpicBranchConfigReadShell's
    technique — extract the state's raw action, substitute FSM placeholders,
    run via bash -c, assert on real git state)."""

    _EPIC_BRANCH = "epic/epic-42-my-epic-title"

    def _setup_repo(self, tmp_path: Path, *, conflict: bool = False) -> None:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "README.md").write_text("x\n")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

        subprocess.run(["git", "branch", self._EPIC_BRANCH], cwd=tmp_path, check=True)
        subprocess.run(["git", "checkout", "-q", self._EPIC_BRANCH], cwd=tmp_path, check=True)
        (tmp_path / "feature.txt").write_text("epic work\n")
        subprocess.run(["git", "add", "feature.txt"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "epic work"], cwd=tmp_path, check=True)
        if conflict:
            # ENH-2643: force a real merge-back conflict — diverging edits to the
            # same file on the epic branch and on main (mirrors test_worktree_utils
            # test_conflicting_merge_returns_false_and_aborts).
            (tmp_path / "README.md").write_text("epic version\n")
            subprocess.run(["git", "commit", "-q", "-am", "epic README"], cwd=tmp_path, check=True)
        subprocess.run(["git", "checkout", "-q", "main"], cwd=tmp_path, check=True)
        if conflict:
            (tmp_path / "README.md").write_text("main version\n")
            subprocess.run(["git", "commit", "-q", "-am", "main README"], cwd=tmp_path, check=True)

    def _write_issues(self, tmp_path: Path, child_statuses: dict[str, str]) -> None:
        subdir = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
        epics_dir = tmp_path / ".issues" / "epics"
        epics_dir.mkdir(parents=True, exist_ok=True)
        (epics_dir / "P3-EPIC-42-my-epic.md").write_text(
            "---\nid: EPIC-42\ntitle: My Epic Title\nstatus: in_progress\n---\n"
            "# EPIC-42: My Epic Title\n"
        )
        for cid, status in child_statuses.items():
            sub = subdir[cid.split("-")[0]]
            (tmp_path / ".issues" / sub).mkdir(parents=True, exist_ok=True)
            (tmp_path / ".issues" / sub / f"P3-{cid}-child.md").write_text(
                f"---\nid: {cid}\nstatus: {status}\nparent: EPIC-42\n---\n# {cid}: Child\n"
            )

    def _run(
        self,
        tmp_path: Path,
        *,
        child_statuses: dict[str, str],
        merge_to_base_on_complete: bool = True,
        open_pr: bool = False,
        verify_before_merge: bool = False,
        write_branch_file: bool = True,
        test_cmd: str | None = None,
        seed_verdict: str | None = None,
        seed_sha: str | None = None,
        branch_statuses: dict[str, str] | None = None,
        conflict: bool = False,
    ) -> tuple[subprocess.CompletedProcess, Path]:
        self._setup_repo(tmp_path, conflict=conflict)
        self._write_issues(tmp_path, child_statuses)
        # BUG-2637: model a child whose `done` status was committed on the epic
        # branch tip but not on the base working tree. Commit the base (open)
        # issue tree to main so the working tree is stable, then commit the
        # `branch_statuses` variant onto the epic branch tip.
        if branch_statuses is not None:
            subprocess.run(["git", "add", ".issues"], cwd=tmp_path, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "issues base"], cwd=tmp_path, check=True)
            subprocess.run(["git", "checkout", "-q", self._EPIC_BRANCH], cwd=tmp_path, check=True)
            # Descend the epic branch from the base issue tree so the tip's
            # `done` override is a clean 3-way merge back to base (no phantom
            # add/add conflict on files that only ever changed on the branch).
            subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=tmp_path, check=True)
            self._write_issues(tmp_path, branch_statuses)
            subprocess.run(["git", "add", ".issues"], cwd=tmp_path, check=True)
            subprocess.run(
                ["git", "commit", "-q", "--allow-empty", "-m", "epic tip statuses"],
                cwd=tmp_path,
                check=True,
            )
            subprocess.run(["git", "checkout", "-q", "main"], cwd=tmp_path, check=True)

        (tmp_path / ".ll").mkdir(exist_ok=True)
        config: dict = {
            "parallel": {
                "base_branch": "main",
                "epic_branches": {
                    "enabled": True,
                    "merge_to_base_on_complete": merge_to_base_on_complete,
                    "open_pr": open_pr,
                    "verify_before_merge": verify_before_merge,
                },
            }
        }
        if test_cmd is not None:
            config["project"] = {"test_cmd": test_cmd}
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(config))

        run_dir = tmp_path / "run"
        run_dir.mkdir(exist_ok=True)
        if write_branch_file:
            (run_dir / "epic-branch-name.txt").write_text(self._EPIC_BRANCH + "\n")
        (run_dir / "base-branch-name.txt").write_text("main\n")
        # ENH-2630: seed the verify state's artifacts to exercise merge_epic_branch's
        # reuse-of-fresh-verdict path. seed_sha="MATCH" resolves the current epic tip.
        if seed_verdict is not None:
            (run_dir / "verify-verdict.txt").write_text(seed_verdict + "\n")
        if seed_sha is not None:
            if seed_sha == "MATCH":
                seed_sha = subprocess.run(
                    ["git", "rev-parse", "--verify", self._EPIC_BRANCH],
                    cwd=tmp_path,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            (run_dir / "verify-sha.txt").write_text(seed_sha + "\n")

        loop = yaml.safe_load((BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())
        action = loop["states"]["merge_epic_branch"]["action"]
        action = action.replace("${context.scope}", "EPIC-42").replace(
            "${context.run_dir}", str(run_dir)
        )
        result = subprocess.run(
            ["bash", "-c", action], cwd=tmp_path, capture_output=True, text=True, timeout=30
        )
        return result, run_dir

    def _branches(self, tmp_path: Path) -> str:
        return subprocess.run(
            ["git", "branch", "--list"], cwd=tmp_path, capture_output=True, text=True
        ).stdout

    def test_merges_when_all_children_done(self, tmp_path: Path) -> None:
        result, run_dir = self._run(
            tmp_path, child_statuses={"FEAT-010": "done", "FEAT-020": "done"}
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "merged"
        assert self._EPIC_BRANCH not in self._branches(tmp_path)
        log = subprocess.run(
            ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True
        ).stdout
        assert "epic work" in log
        assert (tmp_path / "feature.txt").exists()
        # ENH-2643: a clean merge leaves no failure-diagnostic artifacts behind.
        assert not (run_dir / "merge-detail.txt").exists()
        assert not (run_dir / "merge-returncode.txt").exists()

    def test_merge_failed_persists_diagnostic_artifacts(self, tmp_path: Path) -> None:
        """ENH-2643: a real merge-back conflict emits `merge_failed` AND persists
        merge-detail.txt / merge-returncode.txt / merge-conflicts.txt under run_dir,
        mirroring the verify gate's verify-detail.txt pair."""
        result, run_dir = self._run(
            tmp_path,
            child_statuses={"FEAT-010": "done", "FEAT-020": "done"},
            conflict=True,
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "merge_failed"
        assert self._EPIC_BRANCH in self._branches(tmp_path)
        assert (run_dir / "merge-detail.txt").exists()
        assert (run_dir / "merge-returncode.txt").read_text().strip() != "0"
        assert "README.md" in (run_dir / "merge-conflicts.txt").read_text()

    def test_held_open_when_child_not_done(self, tmp_path: Path) -> None:
        result, run_dir = self._run(
            tmp_path, child_statuses={"FEAT-010": "done", "FEAT-020": "in_progress"}
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "held_open"
        assert self._EPIC_BRANCH in self._branches(tmp_path)

    def test_skipped_when_merge_to_base_on_complete_false(self, tmp_path: Path) -> None:
        result, run_dir = self._run(
            tmp_path,
            child_statuses={"FEAT-010": "done"},
            merge_to_base_on_complete=False,
            open_pr=False,
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "skipped"
        assert self._EPIC_BRANCH in self._branches(tmp_path)

    def test_skipped_when_no_epic_branch_file(self, tmp_path: Path) -> None:
        """Non-EPIC scope runs never write epic-branch-name.txt — must no-op."""
        result, run_dir = self._run(
            tmp_path, child_statuses={"FEAT-010": "done"}, write_branch_file=False
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "skipped"

    def test_idempotent_when_branch_already_merged(self, tmp_path: Path) -> None:
        """A second run after the branch is already merged/deleted must no-op,
        not error — the git-existence check is the sole idempotency guard
        (BUG-2614 FSM Plumbing Design: no persisted marker needed)."""
        first, run_dir = self._run(tmp_path, child_statuses={"FEAT-010": "done"})
        assert first.returncode == 0, first.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "merged"

        loop = yaml.safe_load((BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())
        action = loop["states"]["merge_epic_branch"]["action"]
        action = action.replace("${context.scope}", "EPIC-42").replace(
            "${context.run_dir}", str(run_dir)
        )
        second = subprocess.run(
            ["bash", "-c", action], cwd=tmp_path, capture_output=True, text=True, timeout=30
        )
        assert second.returncode == 0, second.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "skipped"

    # --- ENH-2630: reuse the verify state's fresh verdict, skip the re-run -----

    def test_reuses_fresh_verify_verdict_and_skips_rerun(self, tmp_path: Path) -> None:
        """When verify-verdict.txt=passed and verify-sha.txt matches the current
        epic tip, merge_epic_branch must reuse that verdict and skip its own
        re-run. Discriminator: a failing test_cmd — if the re-run happened, the
        gate would fail (verify_failed); reuse merges instead (ENH-2630)."""
        result, run_dir = self._run(
            tmp_path,
            child_statuses={"FEAT-010": "done"},
            verify_before_merge=True,
            test_cmd="false",
            seed_verdict="passed",
            seed_sha="MATCH",
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "merged"
        assert self._EPIC_BRANCH not in self._branches(tmp_path)

    def test_reruns_when_verify_sha_is_stale(self, tmp_path: Path) -> None:
        """A recorded SHA that no longer matches the epic tip must force the
        binding gate to re-run — proven by the failing test_cmd producing
        verify_failed rather than a reused pass (ENH-2630)."""
        result, run_dir = self._run(
            tmp_path,
            child_statuses={"FEAT-010": "done"},
            verify_before_merge=True,
            test_cmd="false",
            seed_verdict="passed",
            seed_sha="0" * 40,
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "verify_failed"
        assert self._EPIC_BRANCH in self._branches(tmp_path)

    def test_reruns_when_verify_verdict_missing(self, tmp_path: Path) -> None:
        """No seeded verdict/SHA (e.g. the verify state never ran on this tip)
        must fall through to the binding gate, which re-runs and fails on the
        failing test_cmd (ENH-2630)."""
        result, run_dir = self._run(
            tmp_path,
            child_statuses={"FEAT-010": "done"},
            verify_before_merge=True,
            test_cmd="false",
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "verify_failed"

    # --- BUG-2637: final-child status lives only on the epic-branch tip --------

    def test_merges_when_final_child_done_only_on_branch_tip(self, tmp_path: Path) -> None:
        """The run that completes the FINAL child writes `status: done` inside
        the epic-branch worktree, so the base working tree still reads `open`.
        merge_epic_branch must read the child status from the epic-branch tip
        (unioned over base) and merge, not report held_open (BUG-2637)."""
        result, run_dir = self._run(
            tmp_path,
            # base working tree: the completing child still reads `open`
            child_statuses={"FEAT-010": "done", "FEAT-020": "open"},
            # epic-branch tip: the completing child is `done`
            branch_statuses={"FEAT-010": "done", "FEAT-020": "done"},
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "merged"
        assert self._EPIC_BRANCH not in self._branches(tmp_path)

    def test_held_open_when_sibling_open_on_both_base_and_tip(self, tmp_path: Path) -> None:
        """A genuinely-open sibling — open on both the base tree and the epic
        branch tip — must still report held_open even with the tip-read (AC-3)."""
        result, run_dir = self._run(
            tmp_path,
            child_statuses={"FEAT-010": "done", "FEAT-020": "open"},
            branch_statuses={"FEAT-010": "done", "FEAT-020": "open"},
        )
        assert result.returncode == 0, result.stderr
        assert (run_dir / "epic-merge-verdict.txt").read_text().strip() == "held_open"
        assert self._EPIC_BRANCH in self._branches(tmp_path)


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
            "check_spike_needed",
            "run_spike",
            "rerun_confidence_after_spike",
            "implement_current",
            # BUG-2734: guard-2 "ready but atomic" earn-the-pass/honest-deferral chain.
            "check_guard2_verdict",
            "check_readiness_for_atomic_remediation",
            "remediate_oversized_atomic",
            "rerun_confidence_after_atomic_remediation",
            "regate_after_atomic_remediation",
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

    def test_dequeue_next_routes_to_check_decision_at_dequeue(self, data: dict) -> None:
        """BUG-2513: dequeue_next must route to check_decision_at_dequeue on success
        (NOT directly to refine_current) so the decision_needed gate intercepts every
        dequeue. check_decision_at_dequeue then routes to refine_current on_no/on_error
        after consulting ll-issues check-flag."""
        state = data["states"].get("dequeue_next", {})
        assert state.get("on_yes") == "check_decision_at_dequeue"

    def test_check_decision_at_dequeue_on_yes_routes_to_check_decision_decidable(
        self, data: dict
    ) -> None:
        """BUG-2605: check_decision_at_dequeue.on_yes (decision_needed=true) must route to
        check_decision_decidable, not directly to run_decide, so a fresh dequeue gets the
        deposit_options detour before decide-issue is asked to choose an option."""
        state = data["states"].get("check_decision_at_dequeue", {})
        assert state.get("on_yes") == "check_decision_decidable", (
            f"check_decision_at_dequeue.on_yes should be 'check_decision_decidable', "
            f"got {state.get('on_yes')!r}"
        )

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

    def test_refine_current_error_routes_to_skip_inflight_infra(self, data: dict) -> None:
        """refine_current.on_error must route to skip_inflight_infra (ENH-2727).
        on_error fires only when the sub-loop raised a runtime exception / was
        signalled — a crash that produced no refine verdict — which is an infra-class,
        re-runnable failure, not a refine-quality defect. It must therefore be ledgered
        as refine_failed_infra, not laundered as refine_failed (ENH-1679's
        on_error == on_no collapse). The evidenced exit-143 case, by contrast, reaches
        the sub-loop's `failed` terminal and is handled via on_failure's
        sentinel-driven skip_inflight path."""
        state = data["states"].get("refine_current", {})
        assert state.get("on_error") == "skip_inflight_infra", (
            f"refine_current.on_error should be 'skip_inflight_infra', got {state.get('on_error')!r}"
        )

    def test_refine_current_has_no_explicit_on_no(self, data: dict) -> None:
        """BUG-2611: refine_current must NOT declare a raw on_no key. schema.py's
        `on_no = on_no or on_failure` means an explicit on_no here silently shadows
        on_failure, permanently dead-coding the skip_inflight route — every
        refine_current crash routed straight to dequeue_next with no ledger write.
        Leaving on_no unset lets it correctly fall back to on_failure's value."""
        state = data["states"].get("refine_current", {})
        assert "on_no" not in state, (
            "refine_current must not set on_no directly — it shadows on_failure "
            "(BUG-2611); the skip_inflight route depends on on_no falling back to "
            "on_failure via schema.py's StateConfig.from_dict"
        )

    def test_refine_current_compiled_on_no_resolves_to_skip_inflight(self, data: dict) -> None:
        """BUG-2611 regression: verify the *compiled* schema, not just the raw YAML dict —
        on_no must resolve to skip_inflight (matching on_failure) so a crashed sub-loop's
        terminal-but-not-done result actually reaches the ledger-writing state."""
        from little_loops.fsm.schema import StateConfig

        state = StateConfig.from_dict(data["states"]["refine_current"])
        assert state.on_no == "skip_inflight", (
            f"refine_current's compiled on_no should resolve to 'skip_inflight' "
            f"(via the on_failure fallback), got {state.on_no!r} — a crashed "
            f"refine-to-ready-issue sub-loop would silently skip the ledger write"
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
        """skip_inflight (a quality/infra classifier since ENH-2727) must route the
        quality path (exit 0 → on_yes) and error path to dequeue_next, and the
        infra path (exit 1 → on_no) to skip_inflight_infra. It uses the shell_exit
        fragment, so routing is on_yes/on_no, not `next` (ENH-1679, ENH-2727)."""
        state = data["states"].get("skip_inflight", {})
        assert state.get("fragment") == "shell_exit", (
            f"skip_inflight should use the shell_exit fragment to classify by exit "
            f"code (ENH-2727), got fragment={state.get('fragment')!r}"
        )
        assert state.get("on_yes") == "dequeue_next", (
            f"skip_inflight.on_yes (quality path, already ledgered) should be "
            f"'dequeue_next', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "skip_inflight_infra", (
            f"skip_inflight.on_no (infra path) should be 'skip_inflight_infra' so the "
            f"infra kill is ledgered distinctly (ENH-2727), got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "dequeue_next", (
            f"skip_inflight.on_error should be 'dequeue_next', got {state.get('on_error')!r}"
        )

    # ------------------------------------------------------------------
    # ENH-2727: infra-vs-quality termination-class ledgering
    # ------------------------------------------------------------------

    def test_skip_inflight_infra_state_exists(self, data: dict) -> None:
        """ENH-2727: skip_inflight_infra sibling of skip_inflight must exist as the
        on_no (infra) target, so an external SIGTERM/OOM/timeout kill is ledgered
        distinctly rather than collapsed into refine_failed (the on_error == on_no
        laundering ENH-1679 left un-fixed)."""
        assert "skip_inflight_infra" in data["states"], (
            "skip_inflight_infra state not found — add it as skip_inflight's on_no "
            "(infra) target (ENH-2727)"
        )

    def test_skip_inflight_infra_is_shell_action(self, data: dict) -> None:
        """ENH-2727: skip_inflight_infra must use action_type: shell."""
        state = data["states"].get("skip_inflight_infra", {})
        assert state.get("action_type") == "shell", (
            f"skip_inflight_infra.action_type should be 'shell', got {state.get('action_type')!r}"
        )

    def test_skip_inflight_infra_writes_infra_reason(self, data: dict) -> None:
        """ENH-2727: skip_inflight_infra must ledger the distinct refine_failed_infra
        reason token (not refine_failed) to autodev-skipped.txt."""
        state = data["states"].get("skip_inflight_infra", {})
        action = state.get("action", "")
        assert "refine_failed_infra" in action, (
            "skip_inflight_infra must write the 'refine_failed_infra' reason token"
        )
        assert "autodev-skipped.txt" in action, (
            "skip_inflight_infra must record the skipped issue ID in autodev-skipped.txt"
        )

    def test_skip_inflight_infra_clears_autodev_inflight(self, data: dict) -> None:
        """ENH-2727: skip_inflight_infra must clear autodev-inflight like skip_inflight
        so BUG-1226's done-state stale-inflight warning is not triggered."""
        state = data["states"].get("skip_inflight_infra", {})
        action = state.get("action", "")
        assert "autodev-inflight" in action, (
            "skip_inflight_infra must clear autodev-inflight (BUG-1226)"
        )

    def test_skip_inflight_infra_routes_to_dequeue_next(self, data: dict) -> None:
        """ENH-2727: skip_inflight_infra must route to dequeue_next on next and on_error."""
        state = data["states"].get("skip_inflight_infra", {})
        assert state.get("next") == "dequeue_next", (
            f"skip_inflight_infra.next should be 'dequeue_next', got {state.get('next')!r}"
        )
        assert state.get("on_error") == "dequeue_next", (
            f"skip_inflight_infra.on_error should be 'dequeue_next', got {state.get('on_error')!r}"
        )

    def test_skip_inflight_quality_path_writes_refine_failed(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2727: with no termination-class sentinel (or class=quality), skip_inflight
        writes refine_failed, clears autodev-inflight, and exits 0 (→ on_yes: dequeue_next)."""
        state = data["states"].get("skip_inflight", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0007")
        (run_dir / "autodev-skipped.txt").write_text("")
        script = action.replace("${captured.input.output}", "ENH-0007")
        script = script.replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"quality path must exit 0 (on_yes), got {result.returncode}: {result.stderr}"
        )
        skipped = (run_dir / "autodev-skipped.txt").read_text()
        assert "ENH-0007  refine_failed" in skipped
        assert "refine_failed_infra" not in skipped, (
            "quality path must NOT write the infra reason token"
        )
        assert not (run_dir / "autodev-inflight").exists()

    def test_skip_inflight_infra_sentinel_routes_to_on_no(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2727: when refine-terminal-class == 'infra', skip_inflight exits 1
        (→ on_no: skip_inflight_infra) WITHOUT writing refine_failed itself — the
        infra ledger write is deferred to skip_inflight_infra."""
        state = data["states"].get("skip_inflight", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0008")
        (run_dir / "autodev-skipped.txt").write_text("")
        (run_dir / "refine-terminal-class").write_text("infra")
        script = action.replace("${captured.input.output}", "ENH-0008")
        script = script.replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 1, (
            f"infra path must exit 1 (on_no → skip_inflight_infra), got {result.returncode}"
        )
        skipped = (run_dir / "autodev-skipped.txt").read_text()
        assert skipped.strip() == "", (
            f"infra path must defer the ledger write to skip_inflight_infra, got {skipped!r}"
        )

    def test_skip_inflight_infra_shell_action_writes_infra_reason(
        self, data: dict, tmp_path: Path
    ) -> None:
        """ENH-2727: skip_inflight_infra shell action appends 'ID  refine_failed_infra'
        to autodev-skipped.txt and removes autodev-inflight. Modelled on
        test_skip_inflight_shell_action_writes_skipped_and_clears_inflight."""
        state = data["states"].get("skip_inflight_infra", {})
        action = state.get("action", "")
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "autodev-inflight").write_text("ENH-0009")
        (run_dir / "autodev-skipped.txt").write_text("")
        script = action.replace("${captured.input.output}", "ENH-0009")
        script = script.replace("${context.run_dir}", str(run_dir))
        result = subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"skip_inflight_infra action failed: {result.stderr}"
        skipped = (run_dir / "autodev-skipped.txt").read_text()
        assert "ENH-0009  refine_failed_infra" in skipped, (
            f"skip_inflight_infra must write 'ID  refine_failed_infra', got {skipped!r}"
        )
        assert not (run_dir / "autodev-inflight").exists()

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

    def test_implement_current_on_no_routes_to_check_learning_gate(self, data: dict) -> None:
        """On non-zero exit (exit 1), route to check_learning_gate FIRST so a learning-gate
        block (LEARNING_GATE_BLOCKED) is distinguished from a generic failure / auth failure."""
        state = data["states"].get("implement_current", {})
        assert state.get("on_no") == "check_learning_gate", (
            f"implement_current.on_no should be 'check_learning_gate', got {state.get('on_no')!r}"
        )

    def test_implement_current_on_error_routes_to_check_learning_gate(self, data: dict) -> None:
        """On fatal error, route to check_learning_gate first (then auth) before terminating."""
        state = data["states"].get("implement_current", {})
        assert state.get("on_error") == "check_learning_gate", (
            f"implement_current.on_error should be 'check_learning_gate', got {state.get('on_error')!r}"
        )

    def test_check_learning_gate_routes_to_auth_check_on_no(self, data: dict) -> None:
        """check_learning_gate detects a gate block (on_yes → mark_gate_blocked) and otherwise
        falls through to check_impl_auth (on_no), preserving the ENH-2353 auth fast-fail."""
        state = data["states"].get("check_learning_gate", {})
        assert state.get("fragment") == "ll_auto_learning_gate_check", (
            f"check_learning_gate should use the ll_auto_learning_gate_check fragment, "
            f"got {state.get('fragment')!r}"
        )
        assert state.get("on_yes") == "mark_gate_blocked", (
            f"check_learning_gate.on_yes should be 'mark_gate_blocked', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "check_impl_auth", (
            f"check_learning_gate.on_no should fall through to 'check_impl_auth', "
            f"got {state.get('on_no')!r}"
        )

    def test_check_learning_gate_on_error_does_not_crash_loop(self, data: dict) -> None:
        """BUG-2594: a residual shell fault in the gate check must degrade to the
        next check (check_impl_auth), not terminate the loop with 'No valid transition'."""
        state = data["states"].get("check_learning_gate", {})
        assert state.get("on_error") == "check_impl_auth", (
            f"check_learning_gate.on_error should be 'check_impl_auth', got {state.get('on_error')!r}"
        )

    def test_check_impl_auth_on_error_does_not_crash_loop(self, data: dict) -> None:
        """BUG-2594: a residual shell fault in the auth check must degrade to the
        queue-drain path, not terminate the loop with 'No valid transition'."""
        state = data["states"].get("check_impl_auth", {})
        assert state.get("on_error") == "dequeue_next", (
            f"check_impl_auth.on_error should be 'dequeue_next', got {state.get('on_error')!r}"
        )

    def test_mark_gate_blocked_advances_queue_without_failing(self, data: dict) -> None:
        """mark_gate_blocked records the issue distinctly and returns to dequeue_next so the
        queue keeps draining (the issue re-surfaces once its deps are proven)."""
        state = data["states"].get("mark_gate_blocked", {})
        action = state.get("action", "")
        assert "autodev-gate-blocked.txt" in action, (
            "mark_gate_blocked should record the issue to autodev-gate-blocked.txt"
        )
        assert "/ll:explore-api" in action, (
            "mark_gate_blocked should point the operator at /ll:explore-api"
        )
        assert state.get("next") == "dequeue_next"

    def test_mark_gate_blocked_defers_via_set_status(self, data: dict) -> None:
        """ENH-2666: mark_gate_blocked aligns to rn-implement's mark_deferred model —
        stamps an automation deferral instead of leaving the issue open for retry."""
        action = data["states"].get("mark_gate_blocked", {}).get("action", "")
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason gate_blocked" in action

    def test_record_decision_unresolved_defers_via_set_status(self, data: dict) -> None:
        """ENH-2666: record_decision_unresolved aligns to rn-implement's mark_deferred
        model — stamps an automation deferral instead of leaving the issue open."""
        action = data["states"].get("record_decision_unresolved", {}).get("action", "")
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason decision_unresolved" in action

    def test_recheck_after_size_review_defers_low_readiness_via_set_status(
        self, data: dict
    ) -> None:
        """ENH-2666: recheck_after_size_review's low_readiness skip path aligns to
        rn-implement's mark_deferred model — stamps an automation deferral instead of
        leaving the issue open for retry."""
        action = data["states"].get("recheck_after_size_review", {}).get("action", "")
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason low_readiness" in action

    def test_recheck_after_size_review_honors_outcome_gate_waived(self, data: dict) -> None:
        """BUG-2734: recheck_after_size_review must bypass the outcome half of the gate
        when the issue's frontmatter carries outcome_gate_waived: true."""
        action = data["states"].get("recheck_after_size_review", {}).get("action", "")
        assert "outcome_gate_waived" in action

    def test_regate_after_atomic_remediation_defers_oversized_atomic_via_set_status(
        self, data: dict
    ) -> None:
        """BUG-2734: a still-failing outcome gate after the earn-the-pass remediation
        attempt defers with the oversized_atomic reason code, never low_readiness —
        readiness already passed to reach this state."""
        action = data["states"].get("regate_after_atomic_remediation", {}).get("action", "")
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason oversized_atomic" in action
        assert "low_readiness" not in action

    def test_regate_after_atomic_remediation_honors_outcome_gate_waived(self, data: dict) -> None:
        """BUG-2734: the remediation re-gate must also honor outcome_gate_waived."""
        action = data["states"].get("regate_after_atomic_remediation", {}).get("action", "")
        assert "outcome_gate_waived" in action

    def test_check_guard2_verdict_detects_guard2_marker_not_guard1(self, data: dict) -> None:
        """BUG-2734: check_guard2_verdict's pattern must match guard-2's
        '[ID] skipped: score X (ambiguous)' verdict (X >= 8) but not guard-1's
        qualitative-skip line, which uses different wording ('structural score N
        ... qualitative')."""
        import re

        state = data["states"].get("check_guard2_verdict", {})
        evaluate = state.get("evaluate", {})
        pattern = evaluate.get("pattern", "")
        assert evaluate.get("source") == "${captured.size_review_output.output}"
        assert re.search(pattern, "[BUG-2731] skipped: score 11 (ambiguous)")
        assert re.search(pattern, "[BUG-2731] skipped: score 8 (ambiguous)")
        assert not re.search(pattern, "[BUG-2731] skipped: score 6 (ambiguous)")
        assert not re.search(
            pattern,
            "[BUG-2731] skipped: structural score 12 but outcome_confidence low is "
            "qualitative (ambiguity: 18, complexity: 20) — suggest /ll:refine-issue",
        )

    def test_check_guard2_verdict_routes_to_remediation_chain(self, data: dict) -> None:
        """BUG-2734: guard-2 verdict routes to the readiness gate before remediation;
        no-match falls through unchanged to recheck_after_size_review."""
        state = data["states"].get("check_guard2_verdict", {})
        assert state.get("on_yes") == "check_readiness_for_atomic_remediation"
        assert state.get("on_no") == "recheck_after_size_review"
        assert state.get("on_error") == "recheck_after_size_review"

        readiness_state = data["states"].get("check_readiness_for_atomic_remediation", {})
        assert readiness_state.get("on_yes") == "remediate_oversized_atomic"
        assert readiness_state.get("on_no") == "recheck_after_size_review"

        remediate_state = data["states"].get("remediate_oversized_atomic", {})
        assert remediate_state.get("next") == "rerun_confidence_after_atomic_remediation"
        assert "/ll:wire-issue" in remediate_state.get("action", "")

        rerun_state = data["states"].get("rerun_confidence_after_atomic_remediation", {})
        assert rerun_state.get("next") == "regate_after_atomic_remediation"
        assert "/ll:confidence-check" in rerun_state.get("action", "")

        regate_state = data["states"].get("regate_after_atomic_remediation", {})
        assert regate_state.get("on_yes") == "decide_current"
        assert regate_state.get("on_no") == "dequeue_next"

    def test_check_reconcile_needed_routes_through_guard2_verdict(self, data: dict) -> None:
        """BUG-2734: check_reconcile_needed's on_no must now route through
        check_guard2_verdict instead of straight to recheck_after_size_review, so
        the guard-2 shape gets a chance at remediation before the low_readiness skip."""
        state = data["states"].get("check_reconcile_needed", {})
        assert state.get("on_no") == "check_guard2_verdict"

    def test_run_size_review_captures_output(self, data: dict) -> None:
        """BUG-2734: run_size_review must capture its status-line output so
        check_guard2_verdict can detect the guard-2 verdict without re-running
        size-review."""
        state = data["states"].get("run_size_review", {})
        assert state.get("capture") == "size_review_output"
        assert state.get("action_type") == "slash_command"
        assert "/ll:issue-size-review" in state.get("action", "")
        assert "--auto" in state.get("action", "")

    def test_implement_current_threads_skip_learning_gate(self, data: dict) -> None:
        """implement_current must append --skip-learning-gate when the skip context is set,
        for parity with `ll-auto --skip-learning-gate`."""
        state = data["states"].get("implement_current", {})
        action = state.get("action", "")
        assert "${context.skip_learning_gate}" in action
        assert "--skip-learning-gate" in action

    def test_copy_broke_down_routes_to_check_decision_after_refine(self, data: dict) -> None:
        """copy_broke_down must route to check_decision_after_refine so decision_needed is
        checked immediately after confidence-check (via sub-loop) completes."""
        state = data["states"].get("copy_broke_down", {})
        assert state.get("next") == "check_decision_after_refine", (
            f"copy_broke_down.next should be 'check_decision_after_refine', got {state.get('next')!r}"
        )

    def test_check_decision_after_refine_routes_correctly(self, data: dict) -> None:
        """check_decision_after_refine must route to check_decision_decidable (on_yes, BUG-2605)
        and check_passed (on_no/on_error)."""
        state = data["states"].get("check_decision_after_refine", {})
        assert state.get("on_yes") == "check_decision_decidable", (
            f"check_decision_after_refine.on_yes should be 'check_decision_decidable', "
            f"got {state.get('on_yes')!r}"
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
        """check_broke_down.on_yes (flag=0 OR no children) routes through the
        BUG-2729 parent-resolved gate, which falls through to recheck_scores on
        unresolved parents and recovers sub-loop children on resolved ones."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_yes") == "check_parent_resolved", (
            f"check_broke_down.on_yes should be 'check_parent_resolved', got {state.get('on_yes')!r}"
        )
        gate = data["states"].get("check_parent_resolved", {})
        assert gate.get("on_no") == "recheck_scores", (
            "check_parent_resolved must fall through to recheck_scores on unresolved parents"
        )
        assert gate.get("on_yes") == "recover_subloop_children", (
            "check_parent_resolved.on_yes must route to recover_subloop_children"
        )

    def test_check_broke_down_on_no_routes_to_enqueue_or_skip(self, data: dict) -> None:
        """check_broke_down.on_no (flag=1 AND children exist) must route to enqueue_or_skip."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_no") == "enqueue_or_skip", (
            f"check_broke_down.on_no should be 'enqueue_or_skip', got {state.get('on_no')!r}"
        )

    def test_check_broke_down_on_error_routes_to_recheck_scores(self, data: dict) -> None:
        """check_broke_down.on_error must route through the parent-resolved gate
        (fail-safe: treat as not broken down)."""
        state = data["states"].get("check_broke_down", {})
        assert state.get("on_error") == "check_parent_resolved", (
            f"check_broke_down.on_error should be 'check_parent_resolved', got {state.get('on_error')!r}"
        )

    def test_recover_subloop_children_recovers_by_parent_frontmatter(self, data: dict) -> None:
        """BUG-2729: recover_subloop_children must match children by frontmatter
        parent field, prepend them to the queue, and never set-status the parent."""
        state = data["states"].get("recover_subloop_children", {})
        action = state.get("action", "")
        assert "i.get('parent')" in action, (
            "recover_subloop_children must match children via the parent frontmatter field"
        )
        assert "autodev-queue.txt" in action
        assert "set-status" not in action, (
            "recover_subloop_children must never change the parent's status"
        )
        assert state.get("next") == "dequeue_next"

    def test_child_detection_matches_parent_frontmatter(self, data: dict) -> None:
        """BUG-2729: detect_children and enqueue_or_skip must match provenance on
        the frontmatter parent: line (deterministic), not only the exact prose
        marker — 'Decomposed from [[ID]]' wiki-link drift defeated the literal grep."""
        for name in ("detect_children", "enqueue_or_skip"):
            action = data["states"].get(name, {}).get("action", "")
            assert "^parent:" in action, (
                f"{name} must grep the frontmatter parent: line for child provenance"
            )
            assert "Decomposed from (\\[\\[)?" in action, (
                f"{name}'s prose fallback must tolerate wiki-link drift"
            )

    def test_defer_sites_guard_resolved_status(self, data: dict) -> None:
        """BUG-2729: every automation defer site must check current status and
        never flip an already done/cancelled issue to deferred."""
        for name in (
            "recheck_after_size_review",
            "mark_gate_blocked",
            "record_decision_unresolved",
        ):
            action = data["states"].get(name, {}).get("action", "")
            assert "set-status" in action, f"{name} should still own its defer transition"
            assert '"$STATUS" = "done"' in action and '"$STATUS" = "cancelled"' in action, (
                f"{name} must guard set-status deferred behind a done/cancelled status check"
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
        """enqueue_or_skip.on_no (no children) routes through the BUG-2729
        parent-resolved gate, then the decide-path spike gate, before
        recheck_after_size_review (BUG-1230 skip path, gated by BUG-2654's
        check_spike_needed_before_skip which itself falls through to
        recheck_after_size_review via check_reconcile_needed)."""
        state = data["states"].get("enqueue_or_skip", {})
        assert state.get("on_no") == "check_parent_resolved_post_size_review", (
            f"enqueue_or_skip.on_no should be 'check_parent_resolved_post_size_review', "
            f"got {state.get('on_no')!r}"
        )
        resolved_gate = data["states"].get("check_parent_resolved_post_size_review", {})
        assert resolved_gate.get("on_no") == "check_spike_needed_before_skip", (
            "check_parent_resolved_post_size_review must preserve the BUG-2654 spike "
            "gate on unresolved parents"
        )
        assert resolved_gate.get("on_yes") == "recover_subloop_children", (
            "check_parent_resolved_post_size_review.on_yes must route to recover_subloop_children"
        )
        gate = data["states"].get("check_spike_needed_before_skip", {})
        assert gate.get("on_no") == "check_reconcile_needed", (
            "ENH-2689: the spike gate's no-match edge now routes through "
            "check_reconcile_needed (which itself falls through to "
            "recheck_after_size_review) before the BUG-1230 leaf-skip"
        )
        reconcile_gate = data["states"].get("check_reconcile_needed", {})
        assert reconcile_gate.get("on_no") == "check_guard2_verdict", (
            "BUG-2734: check_reconcile_needed's no-plateau edge now routes through "
            "check_guard2_verdict (which itself falls through to "
            "recheck_after_size_review on no guard-2 match) before the BUG-1230 leaf-skip"
        )
        guard2_gate = data["states"].get("check_guard2_verdict", {})
        assert guard2_gate.get("on_no") == "recheck_after_size_review", (
            "check_guard2_verdict must preserve the BUG-1230 leaf-skip by "
            "falling through to recheck_after_size_review on no guard-2 match"
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

    def test_enqueue_children_calls_finalize_decomposition(self, data: dict) -> None:
        """ENH-2615: enqueue_children must close the decomposed parent via
        `ll-issues finalize-decomposition --children-file` (which owns the
        completed/ move AND repoints the children's parent: to the EPIC) instead
        of a raw git mv that leaves the EPIC linkage stale. Mirrors
        rn-decompose's finalize_parent WARN-not-fail shape."""
        action = data["states"].get("enqueue_children", {}).get("action", "")
        assert "ll-issues finalize-decomposition" in action
        assert "--children-file" in action
        assert "autodev-new-children.txt" in action
        assert "git mv" not in action, "the completed/ move is owned by finalize-decomposition now"
        assert "WARN" in action, "CLI failure must degrade to a WARN, not fail the state"

    def test_enqueue_or_skip_calls_finalize_decomposition(self, data: dict) -> None:
        """ENH-2615: enqueue_or_skip's children-found branch must finalize the
        decomposed parent via the CLI, same as enqueue_children."""
        action = data["states"].get("enqueue_or_skip", {}).get("action", "")
        children_branch = action.split("else")[0] if "else" in action else action
        assert "ll-issues finalize-decomposition" in children_branch
        assert "--children-file" in children_branch
        assert "git mv" not in action, "the completed/ move is owned by finalize-decomposition now"

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

    def test_recheck_scores_on_error_routes_to_check_decision_before_size_review(
        self, data: dict
    ) -> None:
        """BUG-2519: recheck_scores.on_error (check-readiness failure) must route to
        check_decision_before_size_review — closes the inbound-edge symmetry gap with
        the on_no edge covered at line 2836."""
        state = data["states"].get("recheck_scores", {})
        assert state.get("on_error") == "check_decision_before_size_review", (
            f"recheck_scores.on_error should be 'check_decision_before_size_review', "
            f"got {state.get('on_error')!r}"
        )

    def test_check_decision_before_size_review_uses_shell_exit_fragment(self, data: dict) -> None:
        """check_decision_before_size_review must use shell_exit fragment to route on exit code."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_before_size_review.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_decision_before_size_review_on_yes_routes_to_check_decision_decidable(
        self, data: dict
    ) -> None:
        """check_decision_before_size_review.on_yes (decision_needed=true) must route to
        check_decision_decidable (BUG-2605), not straight to run_decide."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("on_yes") == "check_decision_decidable", (
            f"check_decision_before_size_review.on_yes should be 'check_decision_decidable', "
            f"got {state.get('on_yes')!r}"
        )

    def test_check_decision_before_size_review_on_no_routes_to_run_size_review(
        self, data: dict
    ) -> None:
        """check_decision_before_size_review.on_no (no decision needed) must route to run_size_review."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("on_no") == "run_size_review", (
            f"check_decision_before_size_review.on_no should be 'run_size_review', got {state.get('on_no')!r}"
        )

    def test_check_decision_before_size_review_on_error_routes_to_run_size_review(
        self, data: dict
    ) -> None:
        """BUG-2519: check_decision_before_size_review must define on_error to close the latent
        dead-end (shell_exit exit_code 2 returns None from _route). Mirrors
        check_decision_after_refine.on_error precedent at autodev.yaml:173."""
        state = data["states"].get("check_decision_before_size_review", {})
        assert state.get("on_error") == "run_size_review", (
            f"check_decision_before_size_review.on_error should be 'run_size_review', "
            f"got {state.get('on_error')!r}"
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

    def test_triage_outcome_failure_on_no_routes_to_check_spike_needed(self, data: dict) -> None:
        """ENH-2640: triage_outcome_failure.on_no (not a decision) must route to the
        check_spike_needed gate, which falls through to check_missing_artifacts on no match."""
        state = data["states"].get("triage_outcome_failure", {})
        assert state.get("on_no") == "check_spike_needed", (
            f"triage_outcome_failure.on_no should be 'check_spike_needed', got {state.get('on_no')!r}"
        )

    def test_check_spike_needed_falls_through_to_check_missing_artifacts(self, data: dict) -> None:
        """ENH-2640: check_spike_needed.on_no must preserve the existing wire/size-review
        chain by falling through to check_missing_artifacts."""
        state = data["states"].get("check_spike_needed", {})
        assert state.get("on_no") == "check_missing_artifacts", (
            f"check_spike_needed.on_no should be 'check_missing_artifacts', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "check_missing_artifacts", (
            f"check_spike_needed.on_error should be 'check_missing_artifacts', got {state.get('on_error')!r}"
        )

    def test_check_spike_needed_routes_to_run_spike(self, data: dict) -> None:
        """ENH-2640: check_spike_needed.on_yes (spike_needed AND NOT spike_attempted) → run_spike."""
        state = data["states"].get("check_spike_needed", {})
        assert state.get("on_yes") == "run_spike", (
            f"check_spike_needed.on_yes should be 'run_spike', got {state.get('on_yes')!r}"
        )
        assert state.get("fragment") == "shell_exit", (
            f"check_spike_needed.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_spike_needed_predicate_reads_both_flags(self, data: dict) -> None:
        """ENH-2640: predicate must be a two-field condition (spike_needed AND NOT
        spike_attempted) so an attempted spike never re-runs."""
        action = data["states"].get("check_spike_needed", {}).get("action", "")
        assert "spike_needed" in action, "check_spike_needed must read spike_needed"
        assert "spike_attempted" in action, (
            "check_spike_needed must read spike_attempted for the one-shot guard"
        )

    def test_run_spike_action_and_routing(self, data: dict) -> None:
        """ENH-2640: run_spike invokes /ll:spike --auto and routes to the confidence rerun."""
        state = data["states"].get("run_spike", {})
        assert "/ll:spike" in state.get("action", ""), "run_spike must invoke /ll:spike"
        assert "--auto" in state.get("action", ""), "run_spike must pass --auto"
        assert state.get("action_type") == "slash_command"
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "rerun_confidence_after_spike"
        assert state.get("on_error") == "rerun_confidence_after_spike"
        assert state.get("on_rate_limit_exhausted") == "done"

    def test_rerun_confidence_after_spike_routing(self, data: dict) -> None:
        """ENH-2640: rerun_confidence_after_spike re-scores and routes to enqueue_or_skip
        (mirrors rerun_confidence_after_wire, not the decide path's recheck state)."""
        state = data["states"].get("rerun_confidence_after_spike", {})
        assert "/ll:confidence-check" in state.get("action", "")
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "enqueue_or_skip"
        assert state.get("on_error") == "enqueue_or_skip"
        assert state.get("on_rate_limit_exhausted") == "done"

    def test_enqueue_or_skip_on_no_routes_to_decide_path_spike_gate(self, data: dict) -> None:
        """BUG-2654: enqueue_or_skip.on_no (no children) must still reach the
        decide-path spike gate before any low_readiness skip — now via the
        BUG-2729 parent-resolved gate, whose on_no preserves the spike gate edge."""
        state = data["states"].get("enqueue_or_skip", {})
        assert state.get("on_no") == "check_parent_resolved_post_size_review", (
            f"enqueue_or_skip.on_no should be 'check_parent_resolved_post_size_review', "
            f"got {state.get('on_no')!r}"
        )
        resolved_gate = data["states"].get("check_parent_resolved_post_size_review", {})
        assert resolved_gate.get("on_no") == "check_spike_needed_before_skip", (
            "the parent-resolved gate must fall through to check_spike_needed_before_skip "
            "so spike_needed issues keep their one shot at run_spike"
        )

    def test_decide_path_spike_gate_routes_to_run_spike(self, data: dict) -> None:
        """BUG-2654: check_spike_needed_before_skip.on_yes (spike_needed AND NOT
        spike_attempted) must reach run_spike (AC 1)."""
        state = data["states"].get("check_spike_needed_before_skip", {})
        assert state.get("on_yes") == "run_spike", (
            f"check_spike_needed_before_skip.on_yes should be 'run_spike', got {state.get('on_yes')!r}"
        )
        assert state.get("fragment") == "shell_exit"
        action = state.get("action", "")
        assert "spike_needed" in action and "spike_attempted" in action, (
            "gate predicate must read both spike flags for the one-shot guard (AC 2)"
        )

    def test_decide_path_spike_gate_falls_through_to_low_readiness_skip(self, data: dict) -> None:
        """BUG-2654: on no match, the decide-path gate must preserve the existing
        low_readiness leaf-skip — NOT the triage-path check_missing_artifacts
        fall-through (AC 3). ENH-2689 interposes check_reconcile_needed on the
        on_no edge (a pass-through for non-plateau issues), while on_error still
        skips straight to recheck_after_size_review."""
        state = data["states"].get("check_spike_needed_before_skip", {})
        assert state.get("on_no") == "check_reconcile_needed", (
            f"check_spike_needed_before_skip.on_no should be 'check_reconcile_needed' "
            f"(ENH-2689), got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "recheck_after_size_review", (
            f"check_spike_needed_before_skip.on_error should be 'recheck_after_size_review', "
            f"got {state.get('on_error')!r}"
        )

    # ENH-2689: post-spike reconcile plateau states — check_reconcile_needed
    # detects a bit-identical pre/post-spike Readiness plateau and routes one
    # /ll:reconcile-issue pass before the low_readiness deferral.

    def test_reconcile_states_exist(self, data: dict) -> None:
        """The three ENH-2689 reconcile states must be present."""
        states = data.get("states", {})
        for name in (
            "check_reconcile_needed",
            "reconcile_current",
            "rerun_confidence_after_reconcile",
        ):
            assert name in states, f"{name} missing from autodev.yaml (ENH-2689)"

    def test_spike_gates_snapshot_pre_spike_readiness(self, data: dict) -> None:
        """Both spike guards must snapshot the pre-spike Readiness score to the
        run_dir file that check_reconcile_needed reads (ENH-2689)."""
        for gate in ("check_spike_needed", "check_spike_needed_before_skip"):
            action = data["states"].get(gate, {}).get("action", "")
            assert "autodev-pre-spike-readiness.txt" in action, (
                f"{gate} must snapshot pre-spike Readiness for the reconcile plateau check"
            )
            assert "confidence" in action, (
                f"{gate} must write confidence into the pre-spike snapshot"
            )

    def test_check_reconcile_needed_predicate_reads_snapshot_and_guard(self, data: dict) -> None:
        """Predicate is a two-condition one-shot: pre-spike snapshot == current
        Readiness AND NOT reconcile_attempted."""
        state = data["states"].get("check_reconcile_needed", {})
        action = state.get("action", "")
        assert state.get("fragment") == "shell_exit"
        assert "autodev-pre-spike-readiness.txt" in action, (
            "check_reconcile_needed must read the pre-spike snapshot"
        )
        assert "confidence" in action, "must compare against current confidence"
        assert "reconcile_attempted" in action, (
            "check_reconcile_needed must read reconcile_attempted for the one-shot guard"
        )

    def test_check_reconcile_needed_routing(self, data: dict) -> None:
        """on_yes → reconcile_current; on_no → check_guard2_verdict (BUG-2734,
        itself falling through to recheck_after_size_review); on_error →
        recheck_after_size_review directly (non-plateau issues fall through
        unchanged, AC 4)."""
        state = data["states"].get("check_reconcile_needed", {})
        assert state.get("on_yes") == "reconcile_current"
        assert state.get("on_no") == "check_guard2_verdict"
        assert state.get("on_error") == "recheck_after_size_review"

    def test_reconcile_current_invokes_reconcile_skill(self, data: dict) -> None:
        """reconcile_current calls /ll:reconcile-issue and routes to the rerun."""
        state = data["states"].get("reconcile_current", {})
        assert "/ll:reconcile-issue" in state.get("action", "")
        assert state.get("action_type") == "slash_command"
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "rerun_confidence_after_reconcile"
        assert state.get("on_error") == "rerun_confidence_after_reconcile"
        assert state.get("on_rate_limit_exhausted") == "done"

    def test_rerun_confidence_after_reconcile_routing(self, data: dict) -> None:
        """After reconcile, re-score once, then fall to recheck_after_size_review."""
        state = data["states"].get("rerun_confidence_after_reconcile", {})
        assert "/ll:confidence-check" in state.get("action", "")
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "recheck_after_size_review"
        assert state.get("on_error") == "recheck_after_size_review"
        assert state.get("on_rate_limit_exhausted") == "done"

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

    def test_decide_current_on_yes_routes_to_check_decision_decidable(self, data: dict) -> None:
        """ENH-2443: decide_current.on_yes (decision_needed=true) must route to
        check_decision_decidable (parity insertion mirroring rn-remediate), which then
        routes to run_decide once the issue has enumerable options to decide between."""
        state = data["states"].get("decide_current", {})
        assert state.get("on_yes") == "check_decision_decidable", (
            f"decide_current.on_yes should be 'check_decision_decidable', got "
            f"{state.get('on_yes')!r}"
        )

    def test_check_decision_decidable_state_exists_and_routes(self, data: dict) -> None:
        """ENH-2443: check_decision_decidable uses the deterministic ll-issues
        check-decidable companion CLI and routes yes->run_decide, no->deposit_options."""
        state = data["states"].get("check_decision_decidable", {})
        assert state.get("fragment") == "shell_exit"
        assert "ll-issues check-decidable" in state.get("action", "")
        assert state.get("on_yes") == "run_decide"
        assert state.get("on_no") == "deposit_options"
        assert state.get("on_error") == "run_decide"

    def test_deposit_options_state_exists_and_routes(self, data: dict) -> None:
        """ENH-2443: deposit_options runs /ll:refine-issue --auto and routes success
        through record_options_deposited back to check_decision_decidable (via
        check_open_question_progress as of ENH-2446)."""
        do = data["states"].get("deposit_options", {})
        assert do.get("fragment") == "with_rate_limit_handling"
        assert do.get("action_type") == "slash_command"
        assert "/ll:refine-issue" in do.get("action", "")
        assert "--auto" in do.get("action", "")
        assert do.get("on_yes") == "record_options_deposited"
        assert do.get("on_partial") == "record_options_deposited"
        assert do.get("on_no") == "run_decide"
        assert do.get("on_error") == "run_decide"

        rod = data["states"].get("record_options_deposited", {})
        assert rod.get("action_type") == "shell"
        # ENH-2446: routes through check_open_question_progress (progress gate)
        # before reaching check_decision_decidable — lets deposit_options re-fire
        # while open-question counts are still strictly decreasing.
        assert rod.get("next") == "check_open_question_progress"
        assert "autodev-decide-options-deposited" in rod.get("action", "")

    def test_check_decision_decidable_chains_coverage_probe(self, data: dict) -> None:
        """ENH-2446: chains check-open-questions before check-decidable for
        coverage-aware decidability detection (mixed resolved-options + open-questions)."""
        action = data["states"]["check_decision_decidable"].get("action", "")
        assert "check-open-questions" in action
        assert action.index("check-open-questions") < action.index("check-decidable")

    def test_check_open_question_progress_state_exists(self, data: dict) -> None:
        """ENH-2446: progress-gated re-fire between record_options_deposited and
        check_decision_decidable; uses open_question_stall_gate fragment."""
        cop = data["states"].get("check_open_question_progress", {})
        assert cop.get("fragment") == "open_question_stall_gate"
        assert cop.get("on_yes") == "check_decision_decidable"
        assert cop.get("on_no") == "run_decide"
        assert cop.get("on_error") == "run_decide"

    def test_dequeue_next_clears_decide_options_deposited_marker(self, data: dict) -> None:
        """ENH-2443: the deposit-options marker must be cleared per-issue (mirrors the
        existing autodev-decide-ran clear) so the retry is bounded to one per issue."""
        dq = data["states"].get("dequeue_next", {})
        assert "autodev-decide-options-deposited" in dq.get("action", "")

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
        """ENH-2717: run_decide.on_error must route to check_decision_after_decide_error, which
        short-circuits to record_decision_unresolved if decision_needed is still true rather than
        falling through to a redundant run_size_review."""
        state = data["states"].get("run_decide", {})
        assert state.get("on_error") == "check_decision_after_decide_error"

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
        assert "ENH-0001  refine_failed" in skipped, (
            "skip_inflight must write 'ID  REASON' (two-space-delimited, ENH-2404) "
            f"to autodev-skipped.txt, got {skipped!r}"
        )
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

    def test_autodev_yaml_declares_singleton_true(self, data: dict) -> None:
        """autodev must declare singleton: true to serialize the implementation-phase race (BUG-2526).

        Two `ll-loop run autodev` invocations reach implement_current on disjoint
        `${context.run_dir}` scopes; without singleton: true, LockManager does not
        serialize them and both shell to `ll-auto --only` on the main working tree.
        The singleton predicate forces a loop-name conflict regardless of scope.
        """
        assert data.get("singleton") is True, (
            "autodev.yaml must declare singleton: true to serialize the "
            "implementation-phase race (BUG-2526). Without it, two concurrent "
            "autodev instances both shell to `ll-auto --only` on the main tree."
        )


class TestAutodevRnImplementDeferralParity:
    """ENH-2666: autodev.yaml and rn-implement.yaml must produce the same
    lifecycle (status: deferred, deferred_by/deferred_reason shape) for their
    respective not-ready exits, so behavior is predictable regardless of which
    orchestrator runs."""

    AUTODEV_FILE = BUILTIN_LOOPS_DIR / "autodev.yaml"
    RN_IMPLEMENT_FILE = BUILTIN_LOOPS_DIR / "rn-implement.yaml"

    # autodev's three not-ready exits that were aligned to rn-implement's
    # mark_deferred model; excludes `decomposed` exits (already close via
    # finalize-decomposition → status: done) and skip_inflight's
    # refine_failed (a sub-loop failure, not a not-ready reason).
    AUTODEV_NOT_READY_STATES = (
        "mark_gate_blocked",
        "record_decision_unresolved",
        "recheck_after_size_review",
    )

    @pytest.fixture
    def autodev_data(self) -> dict:
        return yaml.safe_load(self.AUTODEV_FILE.read_text())

    @pytest.fixture
    def rn_implement_data(self) -> dict:
        return yaml.safe_load(self.RN_IMPLEMENT_FILE.read_text())

    @pytest.mark.parametrize("state_name", AUTODEV_NOT_READY_STATES)
    def test_autodev_not_ready_exit_matches_mark_deferred_shape(
        self, state_name: str, autodev_data: dict, rn_implement_data: dict
    ) -> None:
        """Each autodev not-ready exit uses the same set-status shape as
        rn-implement's mark_deferred: ll-issues set-status <ID> deferred
        --by automation --reason <code>."""
        autodev_action = autodev_data["states"][state_name]["action"]
        mark_deferred_action = rn_implement_data["states"]["mark_deferred"]["action"]

        for action in (autodev_action, mark_deferred_action):
            assert "ll-issues set-status" in action
            assert "deferred" in action
            assert "--by automation" in action
            assert "--reason" in action


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

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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
        assert data.get("input_key") == "input"
        assert isinstance(data.get("states"), dict)

    def test_required_states_exist(self, data: dict) -> None:
        """All required states must be present."""
        required = {"init", "plan", "generate", "evaluate", "score", "done", "failed"}
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing states: {missing}"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_context_has_targets_csv(self, data: dict) -> None:
        """ENH-2405: context must declare targets_csv for the registered-targets path."""
        assert "targets_csv" in data.get("context", {}), (
            f"context must declare 'targets_csv', got {list(data.get('context', {}).keys())}"
        )

    def test_check_issue_file_routes_to_check_targets_csv(self, data: dict) -> None:
        """ENH-2405: check_issue_file.on_yes must route to check_targets_csv (not gate
        directly), so a populated targets_csv can bypass assumption-firewall."""
        state = data["states"].get("check_issue_file", {})
        assert state.get("on_yes") == "check_targets_csv", (
            f"check_issue_file.on_yes should be 'check_targets_csv', got {state.get('on_yes')!r}"
        )

    def test_check_targets_csv_uses_shell_exit_fragment(self, data: dict) -> None:
        """ENH-2405: check_targets_csv must use the shell_exit fragment."""
        state = data["states"].get("check_targets_csv", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_targets_csv.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_check_targets_csv_routes_to_gate_direct_and_gate(self, data: dict) -> None:
        """ENH-2405: a populated targets_csv routes to gate_direct (skipping
        assumption-firewall); an absent one falls back to gate (assumption-firewall)."""
        state = data["states"].get("check_targets_csv", {})
        assert state.get("on_yes") == "gate_direct", (
            f"check_targets_csv.on_yes should be 'gate_direct', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "gate", (
            f"check_targets_csv.on_no should be 'gate', got {state.get('on_no')!r}"
        )

    def test_gate_direct_delegates_to_ready_to_implement_gate_with_targets_csv(
        self, data: dict
    ) -> None:
        """ENH-2405: gate_direct must prove the registered list directly via
        ready-to-implement-gate, bypassing assumption-firewall's extract_assumptions."""
        state = data["states"].get("gate_direct", {})
        assert state.get("loop") == "ready-to-implement-gate", (
            f"gate_direct.loop should be 'ready-to-implement-gate', got {state.get('loop')!r}"
        )
        with_ = state.get("with", {})
        assert with_.get("targets") == "${context.targets_csv}", (
            f"gate_direct.with.targets should be '${{context.targets_csv}}', got {with_.get('targets')!r}"
        )

    def test_gate_direct_routes_to_run_impl_and_blocked(self, data: dict) -> None:
        """ENH-2405: gate_direct must route success to run_impl, failure/error to blocked
        (mirroring the gate state's existing terminal routing)."""
        state = data["states"].get("gate_direct", {})
        assert state.get("on_success") == "run_impl", (
            f"gate_direct.on_success should be 'run_impl', got {state.get('on_success')!r}"
        )
        assert state.get("on_failure") == "blocked", (
            f"gate_direct.on_failure should be 'blocked', got {state.get('on_failure')!r}"
        )
        assert state.get("on_error") == "blocked", (
            f"gate_direct.on_error should be 'blocked', got {state.get('on_error')!r}"
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


class TestSpikeGateLoop:
    """Tests that spike-gate.yaml has correct structure and routing (ENH-2641)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "spike-gate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_description_is_nonempty(self, data: dict) -> None:
        """Loop must have a non-empty description."""
        assert data.get("description"), "spike-gate must have a non-empty description"

    def test_category_is_gate(self, data: dict) -> None:
        """spike-gate is a gate loop, matching proof-first-task/assumption-firewall."""
        assert data.get("category") == "gate", (
            f"category should be 'gate', got {data.get('category')!r}"
        )

    def test_top_level_template_keys(self, data: dict) -> None:
        """Top-level keys mirror the proof-first-task gate template."""
        assert data.get("initial") == "check_issue_file"
        assert data.get("max_steps") == 150
        assert data.get("timeout") == 7200
        assert data.get("on_handoff") == "spawn"
        assert "lib/common.yaml" in data.get("import", [])

    def test_context_declares_issue_id_and_impl_loop(self, data: dict) -> None:
        """Context must declare issue_id (the spike/check-flag handle) and impl_loop."""
        ctx = data.get("context", {})
        assert "issue_id" in ctx, f"context must declare 'issue_id', got {list(ctx.keys())}"
        assert "task" in ctx, f"context must declare 'task', got {list(ctx.keys())}"
        assert ctx.get("impl_loop") == "general-task", (
            f"impl_loop default should be 'general-task', got {ctx.get('impl_loop')!r}"
        )

    def test_check_issue_file_uses_shell_exit_and_skips_when_absent(self, data: dict) -> None:
        """No issue_id → skip the gate and run the impl loop directly (proof-first parity)."""
        state = data["states"].get("check_issue_file", {})
        assert state.get("fragment") == "shell_exit", (
            f"check_issue_file.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )
        assert state.get("on_yes") == "check_spike_needed", (
            f"check_issue_file.on_yes should be 'check_spike_needed', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "run_impl", (
            f"check_issue_file.on_no should be 'run_impl', got {state.get('on_no')!r}"
        )

    def test_check_spike_needed_gates_on_flag(self, data: dict) -> None:
        """check_spike_needed uses check-flag; no spike_needed → skip to run_impl."""
        state = data["states"].get("check_spike_needed", {})
        assert state.get("fragment") == "shell_exit"
        assert "check-flag" in state.get("action", "")
        assert "spike_needed" in state.get("action", "")
        assert state.get("on_yes") == "check_spike_completed", (
            f"check_spike_needed.on_yes should be 'check_spike_completed', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "run_impl", (
            f"check_spike_needed.on_no should be 'run_impl', got {state.get('on_no')!r}"
        )

    def test_check_spike_completed_short_circuits(self, data: dict) -> None:
        """Already-proven spike (spike_completed:true) short-circuits straight to run_impl."""
        state = data["states"].get("check_spike_completed", {})
        assert state.get("fragment") == "shell_exit"
        assert "spike_completed" in state.get("action", "")
        assert state.get("on_yes") == "run_impl", (
            f"check_spike_completed.on_yes should be 'run_impl', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "gate", (
            f"check_spike_completed.on_no should be 'gate', got {state.get('on_no')!r}"
        )

    def test_gate_runs_spike_check_via_slash_command(self, data: dict) -> None:
        """gate invokes /ll:spike --check as a slash command, evaluated by exit code."""
        state = data["states"].get("gate", {})
        assert state.get("action_type") == "slash_command", (
            f"gate.action_type should be 'slash_command', got {state.get('action_type')!r}"
        )
        action = state.get("action", "")
        assert "/ll:spike" in action and "--check" in action, (
            f"gate.action should invoke '/ll:spike ... --check', got {action!r}"
        )
        assert state.get("evaluate", {}).get("type") == "exit_code", (
            f"gate.evaluate.type should be 'exit_code', got {state.get('evaluate')!r}"
        )

    def test_gate_routing(self, data: dict) -> None:
        """Pass → run_impl; fail → run_spike_auto (one remediation); error → blocked."""
        state = data["states"].get("gate", {})
        assert state.get("on_yes") == "run_impl", (
            f"gate.on_yes should be 'run_impl', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "run_spike_auto", (
            f"gate.on_no should be 'run_spike_auto', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "blocked", (
            f"gate.on_error should be 'blocked', got {state.get('on_error')!r}"
        )

    def test_run_spike_auto_runs_auto_then_rechecks(self, data: dict) -> None:
        """run_spike_auto invokes /ll:spike --auto once, then routes to recheck."""
        state = data["states"].get("run_spike_auto", {})
        assert state.get("action_type") == "slash_command"
        action = state.get("action", "")
        assert "/ll:spike" in action and "--auto" in action, (
            f"run_spike_auto.action should invoke '/ll:spike ... --auto', got {action!r}"
        )
        assert state.get("next") == "recheck", (
            f"run_spike_auto.next should be 'recheck', got {state.get('next')!r}"
        )
        assert state.get("on_error") == "blocked"

    def test_recheck_blocks_on_persistent_failure(self, data: dict) -> None:
        """recheck re-runs --check; still failing → blocked, passing → run_impl."""
        state = data["states"].get("recheck", {})
        assert state.get("action_type") == "slash_command"
        assert "--check" in state.get("action", "")
        assert state.get("evaluate", {}).get("type") == "exit_code"
        assert state.get("on_yes") == "run_impl", (
            f"recheck.on_yes should be 'run_impl', got {state.get('on_yes')!r}"
        )
        assert state.get("on_no") == "blocked", (
            f"recheck.on_no should be 'blocked', got {state.get('on_no')!r}"
        )
        assert state.get("on_error") == "blocked"

    def test_run_impl_uses_dynamic_loop(self, data: dict) -> None:
        """run_impl delegates to the caller-supplied impl_loop with the task as input."""
        state = data["states"].get("run_impl", {})
        assert state.get("loop") == "${context.impl_loop}", (
            f"run_impl.loop should be '${{context.impl_loop}}', got {state.get('loop')!r}"
        )
        assert "input" in state.get("with", {}), (
            f"run_impl.with must bind 'input', got {list(state.get('with', {}).keys())}"
        )
        assert state.get("on_success") == "done"
        assert state.get("on_failure") == "impl_failed"
        assert state.get("on_error") == "impl_failed"

    def test_terminals_are_terminal(self, data: dict) -> None:
        """done / blocked / impl_failed must all be terminal."""
        for name in ("done", "blocked", "impl_failed"):
            state = data["states"].get(name, {})
            assert state.get("terminal") is True, f"{name}.terminal should be True"


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

    def test_check_stall_routes_through_score_stall(self, data: dict) -> None:
        """ENH-2428: check_stall must use the score_stall gate (score-plateau signal)."""
        from little_loops.fsm.fragments import resolve_fragments

        resolved = resolve_fragments(yaml.safe_load(self.LOOP_FILE.read_text()), BUILTIN_LOOPS_DIR)
        state = resolved["states"].get("check_stall", {})
        assert state.get("evaluate", {}).get("type") == "score_stall", (
            "check_stall must route through the score_stall evaluator"
        )

    def test_records_score_history_under_run_dir(self, data: dict) -> None:
        """ENH-2428: a record_score state persists scores under run_dir (MR-3)."""
        states = data.get("states", {})
        assert "record_score" in states, "record_score state missing"
        action = states["record_score"].get("action", "")
        assert ".score_history" in action, "record_score must write .score_history"
        assert "${context.run_dir}" in action, "score history must live under run_dir"
        assert ".loops/tmp/" not in action, "must not write to bare .loops/tmp/ (MR-3)"

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


class TestCodeRunGateOracle:
    """Structural tests for the code-run-gate oracle sub-loop (FEAT-2551).

    Reusable Tier-1 deterministic oracle: runs the project's build/test/
    typecheck/lint/service_health command matrix and emits GATE_PASS /
    GATE_FAILED / GATE_SKIP via the parent↔sub-loop token channel.

    MR-1 trivial: only exit_code / output_numeric / classify evaluators.
    MR-3 compliant: all artifacts written under ${context.run_dir}/.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/code-run-gate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    # --- Required top-level fields ---------------------------------------

    def test_required_top_level_fields(self, data: dict) -> None:
        """name, initial, states must be present and match FEAT-2551 topology."""
        assert data.get("name") == "code-run-gate"
        assert data.get("initial") == "resolve_commands"
        assert data.get("visibility") == "internal"
        assert data.get("on_handoff") == "spawn"
        assert isinstance(data.get("states"), dict)

    # --- Parameters block ------------------------------------------------

    def test_has_parameters_block(self, data: dict) -> None:
        """parameters must declare run_dir, issue_id + the six command fields."""
        params = data.get("parameters", {})
        required = {
            "run_dir",
            "issue_id",
            "min_pass_rate",
            "health_bound_seconds",
            "build_cmd",
            "test_cmd",
            "typecheck_cmd",
            "lint_cmd",
            "run_cmd",
            "health_url",
        }
        missing = required - set(params)
        assert not missing, f"parameters block missing: {sorted(missing)}"
        assert params["run_dir"].get("required") is True
        assert params["issue_id"].get("required") is True

    # --- Required states exist -------------------------------------------

    def test_required_states_exist(self, data: dict) -> None:
        """All 9 states from FEAT-2551:135-138 topology must be present."""
        states = data.get("states", {})
        required = {
            "resolve_commands",
            "run_build",
            "run_test",
            "run_typecheck",
            "run_lint",
            "service_health",
            "aggregate",
            "done",
            "failed",
        }
        missing = required - set(states)
        assert not missing, f"Missing states: {sorted(missing)}"

    # --- MR-1 trivial: no LLM evaluators ---------------------------------

    def test_only_uses_non_llm_evaluators(self, data: dict) -> None:
        """All evaluators must be Tier-1 (exit_code / output_numeric / classify / etc).

        Per scripts/little_loops/fsm/validation.py:84-88 NON_LLM_EVALUATOR_TYPES,
        any non-LLM evaluator makes MR-1 trivially satisfied.
        """
        non_llm = {
            "exit_code",
            "output_numeric",
            "output_json",
            "output_contains",
            "convergence",
            "diff_stall",
            "score_stall",
            "open_question_stall",
            "action_stall",
            "mcp_result",
            "harbor_scorer",
            "classify",
        }
        forbidden = {"llm_structured", "comparator", "contract"}
        states = data.get("states", {})
        for state_name, state in states.items():
            evaluator = state.get("evaluate")
            if evaluator is None:
                continue
            etype = evaluator.get("type")
            assert etype in non_llm, (
                f"State {state_name!r} uses evaluator type {etype!r} which is LLM-judged; "
                f"FEAT-2551 oracle must use only Tier-1 deterministic evaluators."
            )
            assert etype not in forbidden, (
                f"State {state_name!r} uses forbidden evaluator {etype!r}"
            )

    # --- MR-3: no bare .loops/tmp/ writes -------------------------------

    def test_no_writes_to_bare_loops_tmp(self, data: dict) -> None:
        """All artifacts must live under ${context.run_dir}/ (MR-3, ENH-2500)."""
        states = data.get("states", {})
        for state_name, state in states.items():
            action = state.get("action", "")
            if not isinstance(action, str):
                continue
            assert ".loops/tmp/" not in action, (
                f"State {state_name!r} writes to bare .loops/tmp/ — "
                f"use ${{context.run_dir}}/ instead (MR-3, ENH-2500)"
            )

    # --- resolve_commands writes commands.json + subloop_outcome --------

    def test_resolve_commands_uses_run_dir(self, data: dict) -> None:
        """resolve_commands must write commands.json and subloop_outcome under run_dir."""
        action = data["states"]["resolve_commands"].get("action", "")
        assert "${context.run_dir}" in action or "run_dir" in action, (
            "resolve_commands must reference ${context.run_dir} for artifact writes"
        )
        assert "commands.json" in action, (
            "resolve_commands must write commands.json sidecar (F2a → F2b contract)"
        )
        assert "subloop_outcome" in action, (
            "resolve_commands must write subloop_outcome_<ID>.txt for F2b's reader"
        )

    # --- aggregate: classify + route table with default -----------------

    def test_aggregate_uses_classify_with_default_route(self, data: dict) -> None:
        """aggregate must use classify evaluator with route: table including _:."""
        state = data["states"]["aggregate"]
        evaluator = state.get("evaluate", {})
        assert evaluator.get("type") == "classify", (
            f"aggregate must use classify evaluator, got {evaluator.get('type')!r}"
        )
        route = state.get("route", {})
        # _ is the canonical default per scripts/little_loops/fsm/validation.py:1975-2006
        assert "_" in route, "aggregate route: must include '_' default fallback"
        assert "_error" in route, "aggregate route: must include '_error' fallback"
        assert route.get("GATE_PASS") == "done", "aggregate route: GATE_PASS must map to done"
        assert route.get("GATE_FAILED") == "failed", (
            "aggregate route: GATE_FAILED must map to failed"
        )
        assert route.get("GATE_SKIP") == "done", (
            "aggregate route: GATE_SKIP must map to done (treated like pass by F2b)"
        )

    # --- All run_* states route forward (chain) --------------------------

    def test_run_states_chain_forward_and_terminate_at_aggregate(self, data: dict) -> None:
        """Every run_* state must route on_yes / on_no / on_error forward in the chain.

        The chain is: resolve_commands → run_build → run_test → run_typecheck →
        run_lint → service_health → aggregate. Each state self-skips when its
        command is null (writing SKIP to its sidecar) so the chain never
        dead-ends. Pre-empts MR-4 partial-route dead-end (validation.py:1575-1616).
        """
        chain = (
            "run_build",
            "run_test",
            "run_typecheck",
            "run_lint",
            "service_health",
            "aggregate",
        )
        states = data["states"]
        # Each state routes all three outcomes to the SAME next state (no fork).
        for i, state_name in enumerate(chain[:-1]):
            next_state = chain[i + 1]
            state = states.get(state_name, {})
            assert state.get("on_yes") == next_state, (
                f"{state_name}.on_yes must be '{next_state}', got {state.get('on_yes')!r}"
            )
            assert state.get("on_no") == next_state, (
                f"{state_name}.on_no must be '{next_state}', got {state.get('on_no')!r}"
            )
            assert state.get("on_error") == next_state, (
                f"{state_name}.on_error must be '{next_state}', got {state.get('on_error')!r}"
            )
        # service_health must terminate the chain at aggregate
        sh = states["service_health"]
        assert sh.get("on_yes") == "aggregate"
        assert sh.get("on_no") == "aggregate"
        assert sh.get("on_error") == "aggregate"

    # --- service_health: PID + teardown ---------------------------------

    def test_service_health_writes_pid_and_tears_down(self, data: dict) -> None:
        """service_health must track the service PID and kill it on teardown."""
        action = data["states"]["service_health"].get("action", "")
        assert "service.pid" in action, "service_health must write ${context.run_dir}/service.pid"
        assert "curl" in action or "wget" in action, (
            "service_health must probe the health URL with curl or wget"
        )
        # Teardown: either explicit kill or trap-based cleanup
        has_kill = "kill" in action and "service.pid" in action
        has_trap = "trap" in action
        assert has_kill or has_trap, (
            "service_health must tear down the service via kill or trap to "
            "prevent orphaned processes"
        )

    # --- Alias resolution per ARCHITECTURE-123 ---------------------------

    def test_resolve_commands_alias_resolution(self, data: dict) -> None:
        """resolve_commands must accept both type_cmd/typecheck_cmd and run_cmd/start_cmd.

        Per ARCHITECTURE-123 (Option A — accept both names; canonical layer
        stays at type_cmd/run_cmd).
        """
        action = data["states"]["resolve_commands"].get("action", "")
        assert "typecheck_cmd" in action, (
            "resolve_commands must read typecheck_cmd (alias for type_cmd)"
        )
        assert "type_cmd" in action, "resolve_commands must read type_cmd (canonical key)"
        # start_cmd is the alias for run_cmd per ARCHITECTURE-123
        assert "start_cmd" in action or "run_cmd" in action, (
            "resolve_commands must read run_cmd and/or start_cmd per ARCHITECTURE-123"
        )

    # --- meta_self_eval_ok NOT set (MR-1 enforced) -----------------------

    def test_meta_self_eval_ok_is_false(self, data: dict) -> None:
        """meta_self_eval_ok must be False (MR-1 is enforced; oracle is not meta)."""
        assert data.get("meta_self_eval_ok", False) is False

    def test_partial_route_ok_is_false(self, data: dict) -> None:
        """partial_route_ok must be False — aggregate routes full table."""
        assert data.get("partial_route_ok", False) is False

    def test_shared_state_ok_is_false(self, data: dict) -> None:
        """shared_state_ok must be False — artifacts are per-run (MR-3)."""
        assert data.get("shared_state_ok", False) is False

    # --- Terminal states ------------------------------------------------

    def test_done_is_terminal(self, data: dict) -> None:
        """done state must be terminal."""
        state = data["states"]["done"]
        assert state.get("terminal") is True, "done.terminal should be True"

    def test_failed_is_terminal(self, data: dict) -> None:
        """failed state must be terminal."""
        state = data["states"]["failed"]
        assert state.get("terminal") is True, "failed.terminal should be True"


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
        # ENH-2565: the serial synth_pop/integrate_node/snapshot_node trio was
        # replaced by a fan-out dispatch that background-spawns the
        # oracles/integrate-node worker sub-loop over the shared queue.
        states = data.get("states", {})
        for s in (
            "build_synth",
            "synth_dispatch",
            "synth_failure_record",
            "assemble",
            "final_score",
        ):
            assert s in states, f"missing synthesis state: {s}"
        assert data.get("states", {}).get("build_synth", {}).get("next") == "synth_dispatch"
        # ENH-2691: synth_dispatch gates on worker/per-node failure instead of
        # falling through unconditionally.
        assert data.get("states", {}).get("synth_dispatch", {}).get("on_yes") == "assemble"
        assert (
            data.get("states", {}).get("synth_dispatch", {}).get("on_no") == "synth_failure_record"
        )
        assert data.get("states", {}).get("synth_failure_record", {}).get("next") == "assemble"
        # The serial states must be gone — the worker owns pop/integrate/snapshot now.
        for s in ("synth_pop", "integrate_node", "snapshot_node"):
            assert s not in states, f"serial synthesis state {s} should be removed (ENH-2565)"

    def test_resume_routes_into_synthesis(self, data: dict) -> None:
        # ENH-2565: init -> check_resume; a resume invocation skips refinement and
        # rebuilds the synth queue from on-disk final.md completion markers.
        states = data.get("states", {})
        assert states.get("init", {}).get("next") == "check_resume"
        assert states.get("resume_build_synth", {}).get("next") == "synth_dispatch"

    def test_resume_three_way_routing(self, data: dict) -> None:
        # BUG-2610: check_resume must distinguish walk-resume (RESUME_WALK ->
        # resume_reconcile -> dequeue_next) from synth-resume (RESUME_SYNTH ->
        # resume_build_synth) and fresh runs (FRESH -> dequeue_next), since the
        # two-way RESUME_MODE gate treated a mid-walk kill as fully refined.
        states = data.get("states", {})
        assert states.get("check_resume", {}).get("on_yes") == "resume_reconcile"
        assert states.get("check_resume", {}).get("on_no") == "route_resume_synth"
        assert states.get("route_resume_synth", {}).get("on_yes") == "resume_build_synth"
        assert states.get("route_resume_synth", {}).get("on_no") == "dequeue_next"
        assert states.get("resume_reconcile", {}).get("next") == "dequeue_next"

    def test_init_refuses_reseed_without_resume_flag(self, data: dict) -> None:
        # BUG-2610: pointing run_dir at a populated prior tree without
        # --context resume=1 must refuse (exit 1 with a hint), not re-seed and
        # destroy completed node work.
        action = data.get("states", {}).get("init", {}).get("action", "")
        assert "resume=1" in action
        assert "exit 1" in action

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

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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

    def test_decide_on_no_routes_to_emit_needs_manual_review(self, data: dict) -> None:
        """decide.on_no must route to emit_needs_manual_review (BUG-2396: un-auto-resolvable decision ≠ implement failure)."""
        state = data["states"].get("decide", {})
        assert state.get("on_no") == "emit_needs_manual_review", (
            f"decide.on_no should be 'emit_needs_manual_review', got {state.get('on_no')!r}"
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

    # format_issue state tests (BUG-2433)

    def test_format_issue_trims_rate_limit_max_wait(self, data: dict) -> None:
        """format_issue must opt out of the fragment's 6h long-wait budget (BUG-2433: a
        cheap fail-open pre-pass should not park the loop for hours on a 429)."""
        state = data["states"].get("format_issue", {})
        assert state.get("rate_limit_max_wait_seconds") == 1, (
            f"format_issue.rate_limit_max_wait_seconds should be 1, "
            f"got {state.get('rate_limit_max_wait_seconds')!r}"
        )

    def test_format_issue_trims_rate_limit_long_wait_ladder(self, data: dict) -> None:
        """format_issue must override the long-wait ladder to a single ~1s rung (BUG-2433)."""
        state = data["states"].get("format_issue", {})
        assert state.get("rate_limit_long_wait_ladder") == [1], (
            f"format_issue.rate_limit_long_wait_ladder should be [1], "
            f"got {state.get('rate_limit_long_wait_ladder')!r}"
        )

    def test_format_issue_on_rate_limit_exhausted_routes_to_assess(self, data: dict) -> None:
        """format_issue.on_rate_limit_exhausted must route to assess (fail-open, matches
        this state's existing on_no/on_error/on_partial intent — BUG-2433)."""
        state = data["states"].get("format_issue", {})
        assert state.get("on_rate_limit_exhausted") == "assess", (
            f"format_issue.on_rate_limit_exhausted should be 'assess', "
            f"got {state.get('on_rate_limit_exhausted')!r}"
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
        """route_rem_scores_missing matches SCORES_MISSING and routes it to record_scores_missing;
        everything else falls through to route_rem_env_not_ready (ENH-2353) before record_failure."""
        state = data["states"]["route_rem_scores_missing"]
        assert state["evaluate"]["type"] == "output_contains"
        assert state["evaluate"]["pattern"] == "SCORES_MISSING"
        assert "${captured.rem_outcome.output}" in state["evaluate"]["source"]
        assert state["on_yes"] == "record_scores_missing"
        assert state["on_no"] == "route_rem_env_not_ready", (
            "route_rem_scores_missing.on_no must route to route_rem_env_not_ready "
            "so ENV_NOT_READY aborts the queue before falling through to record_failure"
        )
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
        mirroring the record_sub_loop_crash convention.

        Note: FEAT-2552's `record_gate_error` is in rn-remediate.yaml (parent of
        the gate), not rn-implement.yaml, so it is covered by
        `TestCodeRunGateOracleWiring` below.
        """
        state = data["states"][state_name]
        assert state["action_type"] == "shell"
        assert tag in state["action"]
        assert "failures.txt" in state["action"]
        assert state["next"] == "dequeue_next"

    def test_report_tallies_diagnostics_separately_from_failures(self, data: dict) -> None:
        """report subtracts SCORES_MISSING and SIZE_REVIEW_FAILED from the headline
        failure count and surfaces them as distinct summary.json keys.

        ENH-2533: the shell `grep -c` substrings were replaced with a Python
        `_grep_count` helper inside the JSON-aggregation heredoc. The semantic
        invariant — separate tally + headline subtraction + distinct summary
        keys — is preserved.

        FEAT-2552: GATE_FAILED_CODE_QUALITY (tagged by the parent's record_failure
        when the sidecar carries GATE_FAILED) and GATE_FAILED_INFRA (tagged by
        rn-remediate's record_gate_error) are added to the diagnostic tally so
        the gate's failure rate is visible in summaries.
        """
        action = data["states"]["report"]["action"]
        assert "SCORES_MISSING" in action
        assert "SIZE_REVIEW_FAILED" in action
        assert "scores_missing" in action
        assert "size_review_failed" in action
        # The headline FAILED counter must subtract these from the total.
        assert "SUB_LOOP_CRASHES" in action
        assert "LEARNING_GATE_BLOCKED_TOTAL" in action
        # FEAT-2552: gate failure tags are also subtracted from the headline.
        assert "GATE_FAILED_CODE_QUALITY" in action
        assert "GATE_FAILED_INFRA" in action
        assert "gate_failed_code_quality" in action
        assert "gate_failed_infra" in action


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
        "unsafe-context-interp": "interpolates user-controlled context raw into a shell body",
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
        ("autodev", "capture-ordering"): {
            # Bucket A (BUG-2734): check_guard2_verdict is reachable via
            # check_broke_down's shortcut branch (sub-loop already decomposed via
            # breakdown_issue), which bypasses run_size_review's capture. That
            # shortcut only fires when children were actually found
            # (autodev-new-children.txt non-empty), so enqueue_or_skip always takes
            # its on_yes (children-found) branch on that path and never reaches
            # check_guard2_verdict at runtime — a runtime invariant the static
            # validator can't see. On genuinely uncaptured runs, evaluate.source
            # falls back to raw_output (empty), which simply fails to match and
            # falls through to recheck_after_size_review — a safe no-op.
            "states.check_guard2_verdict.action",
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


class TestBuiltinLoopReferencesResolve:
    """Every static loop: reference in every built-in loop must resolve to a real file.

    Regression guard for the sprint-refine-and-implement audit: refine-to-ready-issue's
    confidence_check referenced the bare name 'verify-confidence-scores' while the oracle
    lives in loops/oracles/ and must be referenced as 'oracles/verify-confidence-scores'.
    resolve_loop_path raised FileNotFoundError, the validator emitted only a (then
    allowlisted) WARNING, and the loop's on_error route swallowed the failure — two
    multi-hour sprint runs produced zero implementations. This test exercises the same
    resolver the executor uses, so a missing oracles/ prefix (or any unresolvable static
    loop: ref) fails CI at definition time instead of at hour two of a run.
    """

    @pytest.fixture
    def builtin_loops(self) -> list[Path]:
        files = sorted(p for p in BUILTIN_LOOPS_DIR.rglob("*.yaml") if is_runnable_loop(p))
        assert files, "No built-in loop files found"
        return files

    def test_all_static_loop_references_resolve(self, builtin_loops: list[Path]) -> None:
        """load_and_validate (which now errors on unresolvable loop: refs) must not flag any."""
        unresolved: list[str] = []
        for loop_file in builtin_loops:
            _, diagnostics = load_and_validate(loop_file, raise_on_error=False)
            for d in diagnostics:
                if (
                    d.severity is ValidationSeverity.ERROR
                    and "does not resolve to any file" in d.message
                ):
                    unresolved.append(
                        f"{loop_file.relative_to(BUILTIN_LOOPS_DIR)}: {d.path} — {d.message}"
                    )
        assert not unresolved, (
            "Built-in loop(s) reference a loop: target that does not resolve. Oracle sub-loops "
            "must be referenced with the 'oracles/' prefix (e.g. 'oracles/verify-confidence-scores'):\n"
            + "\n".join(unresolved)
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

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        """init action must echo an absolute path so file:// URIs are valid."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        """init must not double an already-absolute ${context.run_dir} (BUG-2435)."""
        state = data["states"].get("init", {})
        action = state.get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action

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


class TestAutodevAuthGuard:
    """Auth-failure fast-fail guard for autodev.implement_current (ENH-2353)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "autodev.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_implement_current_captures_ll_auto_output(self, data: dict) -> None:
        """implement_current must capture output as ll_auto_output for auth-check."""
        state = data["states"]["implement_current"]
        assert state.get("capture") == "ll_auto_output", (
            f"implement_current must set capture: ll_auto_output, got {state.get('capture')!r}"
        )

    def test_implement_current_routes_to_check_learning_gate_then_auth(self, data: dict) -> None:
        """implement_current.on_no/on_error route to check_learning_gate, which falls through
        to check_impl_auth on a non-gate failure — the auth fast-fail stays reachable."""
        state = data["states"]["implement_current"]
        assert state.get("on_no") == "check_learning_gate"
        assert state.get("on_error") == "check_learning_gate"
        gate = data["states"]["check_learning_gate"]
        assert gate.get("on_no") == "check_impl_auth", (
            "check_learning_gate must fall through to check_impl_auth so the ENH-2353 "
            "auth fast-fail still runs on a non-gate failure"
        )

    def test_check_impl_auth_state_exists(self, data: dict) -> None:
        """check_impl_auth state must be defined in autodev."""
        assert "check_impl_auth" in data["states"], "check_impl_auth state missing from autodev"

    def test_check_impl_auth_uses_ll_auto_auth_check_fragment(self, data: dict) -> None:
        """check_impl_auth must use the ll_auto_auth_check fragment."""
        state = data["states"]["check_impl_auth"]
        assert state.get("fragment") == "ll_auto_auth_check"

    def test_check_impl_auth_on_yes_aborts_queue(self, data: dict) -> None:
        """check_impl_auth.on_yes (auth detected) must route to abort_env_not_ready."""
        state = data["states"]["check_impl_auth"]
        assert state.get("on_yes") == "abort_env_not_ready"

    def test_check_impl_auth_on_no_drains_queue(self, data: dict) -> None:
        """check_impl_auth.on_no (no auth failure) must continue draining the queue."""
        state = data["states"]["check_impl_auth"]
        assert state.get("on_no") == "dequeue_next"

    def test_abort_env_not_ready_state_exists(self, data: dict) -> None:
        """abort_env_not_ready state must be defined in autodev."""
        assert "abort_env_not_ready" in data["states"], (
            "abort_env_not_ready state missing from autodev"
        )

    def test_abort_env_not_ready_has_diagnostic_echo(self, data: dict) -> None:
        """abort_env_not_ready must echo a user-actionable diagnostic message."""
        action = data["states"]["abort_env_not_ready"].get("action", "")
        assert "echo" in action


class TestRnImplementAuthFastFail:
    """rn-implement ENV_NOT_READY routing aborts the queue on auth failure (ENH-2353)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-implement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_route_rem_scores_missing_on_no_routes_to_env_not_ready_router(
        self, data: dict
    ) -> None:
        """route_rem_scores_missing.on_no must hand off to route_rem_env_not_ready
        so ENV_NOT_READY aborts the queue before falling through to record_failure."""
        state = data["states"]["route_rem_scores_missing"]
        assert state["on_no"] == "route_rem_env_not_ready", (
            f"route_rem_scores_missing.on_no should be 'route_rem_env_not_ready', "
            f"got {state.get('on_no')!r}"
        )

    def test_route_rem_env_not_ready_state_exists(self, data: dict) -> None:
        """route_rem_env_not_ready state must be defined in rn-implement."""
        assert "route_rem_env_not_ready" in data["states"], (
            "route_rem_env_not_ready state missing from rn-implement"
        )

    def test_route_rem_env_not_ready_detects_token(self, data: dict) -> None:
        """route_rem_env_not_ready must match the ENV_NOT_READY outcome token."""
        state = data["states"]["route_rem_env_not_ready"]
        assert state["evaluate"]["type"] == "output_contains"
        assert state["evaluate"]["pattern"] == "ENV_NOT_READY"
        assert "${captured.rem_outcome.output}" in state["evaluate"]["source"]

    def test_route_rem_env_not_ready_aborts_on_yes(self, data: dict) -> None:
        """route_rem_env_not_ready.on_yes must route to abort_env_not_ready to stop the queue."""
        state = data["states"]["route_rem_env_not_ready"]
        assert state["on_yes"] == "abort_env_not_ready"

    def test_route_rem_env_not_ready_falls_through_to_learning_gate_on_no(self, data: dict) -> None:
        """route_rem_env_not_ready.on_no must hand off to route_rem_learning_gate so a
        LEARNING_GATE_BLOCKED outcome is recorded distinctly before the generic failure bucket."""
        state = data["states"]["route_rem_env_not_ready"]
        assert state["on_no"] == "route_rem_learning_gate", (
            f"route_rem_env_not_ready.on_no should be 'route_rem_learning_gate', "
            f"got {state.get('on_no')!r}"
        )

    def test_abort_env_not_ready_state_exists(self, data: dict) -> None:
        """abort_env_not_ready state must be defined in rn-implement."""
        assert "abort_env_not_ready" in data["states"], (
            "abort_env_not_ready state missing from rn-implement"
        )

    def test_abort_env_not_ready_has_diagnostic_echo(self, data: dict) -> None:
        """abort_env_not_ready must echo a user-actionable diagnostic message."""
        action = data["states"]["abort_env_not_ready"].get("action", "")
        assert "echo" in action


class TestRnImplementEpicFlag:
    """ENH-2660: --context epic=EPIC-NNN seeds the queue with the EPIC's
    parent:-linked children instead of a comma-separated ID list. The direct-ID
    path is unchanged (epic defaults to '')."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-implement.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_epic_context_var_defaults_empty(self, data: dict) -> None:
        """context.epic must default to '' (opt-in; direct-ID path unchanged)."""
        assert data.get("context", {}).get("epic") == ""

    def test_init_branches_on_epic(self, data: dict) -> None:
        """init action must branch on ${context.epic}."""
        init_action = data["states"]["init"].get("action", "")
        assert "${context.epic}" in init_action

    def test_init_resolves_children_via_ll_issues_list_parent(self, data: dict) -> None:
        """The epic branch resolves children through ll-issues list --parent
        (reuses the existing transitive-descendant primitive)."""
        init_action = data["states"]["init"].get("action", "")
        assert "ll-issues list --parent" in init_action

    def test_init_action_errors_on_missing_epic(self, data: dict) -> None:
        """A non-resolvable --epic target aborts init with a not-found error."""
        init_action = data["states"]["init"].get("action", "")
        assert "ERROR" in init_action
        assert "not found" in init_action

    def test_init_action_errors_on_epic_with_no_children(self, data: dict) -> None:
        """An EPIC with zero (open) children aborts init with a no-children error
        that points the operator at auto-decompose / scope-epic."""
        init_action = data["states"]["init"].get("action", "")
        assert "no children" in init_action

    def test_epic_branch_seeds_queue_txt(self, data: dict) -> None:
        """The epic branch seeds queue.txt directly (shares the shared
        tracking-file/config.json init downstream, wiring #10)."""
        init_action = data["states"]["init"].get("action", "")
        assert "queue.txt" in init_action


class TestLearningGateConsistency:
    """The three core implementation loops route a learning-gate block (ENH-2319)
    consistently through the same `ll-auto --only` choke point: a distinct
    LEARNING_GATE_BLOCKED outcome (not a generic failure) plus a uniform
    `skip_learning_gate` knob threaded down to the inner ll-auto call."""

    @pytest.fixture
    def common(self) -> dict:
        return yaml.safe_load((BUILTIN_LOOPS_DIR / "lib" / "common.yaml").read_text())

    @pytest.fixture
    def rn_remediate(self) -> dict:
        return yaml.safe_load((BUILTIN_LOOPS_DIR / "rn-remediate.yaml").read_text())

    @pytest.fixture
    def rn_implement(self) -> dict:
        return yaml.safe_load((BUILTIN_LOOPS_DIR / "rn-implement.yaml").read_text())

    @pytest.fixture
    def autodev(self) -> dict:
        return yaml.safe_load((BUILTIN_LOOPS_DIR / "autodev.yaml").read_text())

    @pytest.fixture
    def auto_refine(self) -> dict:
        return yaml.safe_load((BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())

    @pytest.fixture
    def sprint_refine(self) -> dict:
        return yaml.safe_load((BUILTIN_LOOPS_DIR / "sprint-refine-and-implement.yaml").read_text())

    # --- shared fragment -----------------------------------------------------

    def test_fragment_defined_and_matches_marker(self, common: dict) -> None:
        """The shared ll_auto_learning_gate_check fragment greps for the
        LEARNING_GATE_BLOCKED marker and exposes it via output_contains."""
        frag = common["fragments"]["ll_auto_learning_gate_check"]
        assert "LEARNING_GATE_BLOCKED" in frag["action"]
        assert frag["evaluate"]["type"] == "output_contains"
        assert frag["evaluate"]["pattern"] == "GATE_BLOCKED"

    # --- rn-remediate (rn-implement's leaf implementer) ----------------------

    def test_rn_remediate_implement_routes_to_learning_gate_first(self, rn_remediate: dict) -> None:
        """implement on_no/on_error → check_learning_gate (before auth/failure)."""
        impl = rn_remediate["states"]["implement"]
        assert impl["on_no"] == "check_learning_gate"
        assert impl["on_error"] == "check_learning_gate"

    def test_rn_remediate_check_learning_gate_falls_through_to_auth(
        self, rn_remediate: dict
    ) -> None:
        gate = rn_remediate["states"]["check_learning_gate"]
        assert gate["fragment"] == "ll_auto_learning_gate_check"
        assert gate["on_yes"] == "emit_learning_gate_blocked"
        assert gate["on_no"] == "check_impl_auth"

    def test_rn_remediate_check_learning_gate_on_error_does_not_crash_loop(
        self, rn_remediate: dict
    ) -> None:
        """BUG-2594: a residual shell fault must degrade to check_impl_auth, not crash."""
        gate = rn_remediate["states"]["check_learning_gate"]
        assert gate.get("on_error") == "check_impl_auth"

    def test_rn_remediate_check_impl_auth_on_error_does_not_crash_loop(
        self, rn_remediate: dict
    ) -> None:
        """BUG-2594: a residual shell fault must degrade to emit_implement_failed, not crash."""
        auth = rn_remediate["states"]["check_impl_auth"]
        assert auth.get("on_error") == "emit_implement_failed"

    def test_rn_remediate_emits_distinct_token(self, rn_remediate: dict) -> None:
        emit = rn_remediate["states"]["emit_learning_gate_blocked"]
        assert "LEARNING_GATE_BLOCKED" in emit["action"]
        assert "subloop_outcome_${context.issue_id}.txt" in emit["action"]
        assert emit["next"] == "failed"

    def test_rn_remediate_threads_skip_flag(self, rn_remediate: dict) -> None:
        impl = rn_remediate["states"]["implement"]["action"]
        assert "${context.skip_learning_gate}" in impl
        assert "--skip-learning-gate" in impl
        assert "skip_learning_gate" in rn_remediate["context"]
        assert "skip_learning_gate" in rn_remediate["parameters"]

    # --- rn-implement (parent classifier) ------------------------------------

    def test_rn_implement_routes_learning_gate_before_failure(self, rn_implement: dict) -> None:
        """The env-not-ready router hands off to route_rem_learning_gate, which
        routes a LEARNING_GATE_BLOCKED outcome through prove_rem_learning_gate
        (ENH-2487 gate-site-2 auto-prove) before recording the block, and only a
        non-learning outcome falls through to the next router.

        FEAT-2552: the non-learning fall-through now lands in
        `route_rem_gate_failed` (the GATE_FAILED diagnostic router) before
        `record_failure`, so a GATE_FAILED outcome can be triaged distinctly
        from a genuine IMPLEMENT_FAILED.
        """
        assert (
            rn_implement["states"]["route_rem_env_not_ready"]["on_no"] == "route_rem_learning_gate"
        )
        router = rn_implement["states"]["route_rem_learning_gate"]
        assert router["evaluate"]["pattern"] == "LEARNING_GATE_BLOCKED"
        assert "${captured.rem_outcome.output}" in router["evaluate"]["source"]
        # ENH-2487: on_yes now goes through the config-gated prove step, not straight
        # to record_learning_gate_blocked.
        assert router["on_yes"] == "prove_rem_learning_gate"
        # FEAT-2552: non-learning outcome falls through to route_rem_gate_failed
        # (GATE_FAILED diagnostic triage) before record_failure.
        assert router["on_no"] == "route_rem_gate_failed"

    def test_rn_implement_record_state_tags_and_advances(self, rn_implement: dict) -> None:
        rec = rn_implement["states"]["record_learning_gate_blocked"]
        action = rec["action"]
        assert "LEARNING_GATE_BLOCKED" in action
        assert "failures.txt" in action
        assert "/ll:explore-api" in action
        assert rec["next"] == "dequeue_next"

    def test_rn_implement_report_tallies_separately(self, rn_implement: dict) -> None:
        """report must count LEARNING_GATE_BLOCKED out of the generic FAILURES bucket
        and surface it in summary.json."""
        report = rn_implement["states"]["report"]["action"]
        assert "LEARNING_GATE_BLOCKED" in report
        assert "- LEARNING_GATE_BLOCKED" in report  # subtracted from FAILURES
        assert "learning_gate_blocked" in report  # summary.json key

    def test_rn_implement_pre_dequeue_tag_does_not_double_count(self, rn_implement: dict) -> None:
        """ENH-2406: mark_learning_blocked's LEARNING_GATE_BLOCKED_PRE_DEQUEUE tag is a
        substring superset of the post-remediation safety-net's LEARNING_GATE_BLOCKED tag —
        report must count pre-dequeue catches in their own summary.json key and subtract
        them out of the generic LEARNING_GATE_BLOCKED tally, not double-count both.

        ENH-2533: the shell `grep -c` substrings were replaced with Python
        `_grep_count` helper calls inside the JSON-aggregation heredoc. The
        semantic invariant — pre-dequeue count is its own counter and is
        subtracted from the generic LEARNING_GATE_BLOCKED total — is preserved.
        """
        mlb = rn_implement["states"]["mark_learning_blocked"]
        assert "LEARNING_GATE_BLOCKED_PRE_DEQUEUE" in mlb["action"]

        report = rn_implement["states"]["report"]["action"]
        # Both tokens must be read from failures.txt (substring-superset
        # handling requires both matches).
        assert "LEARNING_GATE_BLOCKED_PRE_DEQUEUE" in report
        assert "LEARNING_GATE_BLOCKED_TOTAL" in report
        # Distinct summary.json key for the pre-dequeue counter.
        assert "learning_gate_blocked_pre_dequeue" in report
        # The generic count must be derived by subtracting the pre-dequeue
        # count from the raw total — not by reusing the raw total verbatim.
        # Strip whitespace to allow for multi-line Python expressions.
        compact = " ".join(report.split())
        assert "LEARNING_GATE_BLOCKED_TOTAL - LEARNING_GATE_BLOCKED_PRE_DEQUEUE" in compact, (
            "report must subtract LEARNING_GATE_BLOCKED_PRE_DEQUEUE from "
            "LEARNING_GATE_BLOCKED_TOTAL to avoid double-counting"
        )

    def test_rn_implement_threads_skip_to_remediate(self, rn_implement: dict) -> None:
        assert "skip_learning_gate" in rn_implement["context"]
        with_block = rn_implement["states"]["run_remediation"]["with"]
        assert with_block["skip_learning_gate"] == "${context.skip_learning_gate}"

    def test_rn_implement_report_consumes_learning_unproven_sidecars(
        self, rn_implement: dict
    ) -> None:
        """ENH-2533: the report action must glob `learning_unproven_*.txt` to aggregate
        per-issue learning followups into summary.json."""
        action = rn_implement["states"]["report"]["action"]
        assert "learning_unproven_" in action, (
            "report must consume learning_unproven_<ID>.txt sidecars to "
            "build the per-issue learning_followups array"
        )

    def test_rn_implement_report_consumes_subloop_outcome_sidecars(
        self, rn_implement: dict
    ) -> None:
        """ENH-2533: the report action must glob `subloop_outcome_*.txt` to aggregate
        per-issue outcomes into summary.json."""
        action = rn_implement["states"]["report"]["action"]
        assert "subloop_outcome_" in action, (
            "report must consume subloop_outcome_<ID>.txt sidecars to build the per_issue array"
        )

    # --- autodev / auto-refine / sprint-refine skip threading ----------------

    def test_skip_flag_threads_through_sprint_chain(
        self, autodev: dict, auto_refine: dict, sprint_refine: dict
    ) -> None:
        """sprint-refine → auto-refine → autodev → inner ll-auto all forward the knob."""
        assert "skip_learning_gate" in sprint_refine["context"]
        assert (
            sprint_refine["states"]["delegate"]["with"]["skip_learning_gate"]
            == "${context.skip_learning_gate}"
        )
        assert "skip_learning_gate" in auto_refine["context"]
        assert (
            auto_refine["states"]["delegate"]["with"]["skip_learning_gate"]
            == "${context.skip_learning_gate}"
        )
        assert "skip_learning_gate" in autodev["context"]
        assert "--skip-learning-gate" in autodev["states"]["implement_current"]["action"]


class TestCanvasSketchGeneratorInitAbsolutePath:
    """init absolute-path guard coverage for canvas-sketch-generator (BUG-2435)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "canvas-sketch-generator.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action


class TestVegaVizInitAbsolutePath:
    """init absolute-path guard coverage for vega-viz (BUG-2435)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "vega-viz.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action


class TestCliAnythingBootstrapInitAbsolutePath:
    """init absolute-path guard coverage for cli-anything-bootstrap (BUG-2435)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "cli-anything-bootstrap.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action


class TestGenerativeArtInitAbsolutePath:
    """init absolute-path guard coverage for generative-art (BUG-2435)."""

    LOOP_FILE = BUILTIN_LOOPS_DIR / "generative-art.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, (
            f"init.action must use $(pwd) for an absolute path, got: {action!r}"
        )

    def test_init_action_guards_against_already_absolute_run_dir(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert 'case "$DIR" in' in action, (
            f"init.action must branch on whether $DIR is already absolute, got: {action!r}"
        )
        assert "/*)" in action


class TestTaskTemplatesInitAbsolutePath:
    """init absolute-path guard coverage for generated task-loop templates (BUG-2435).

    These .tmpl files contain {{jinja}}-style substitution placeholders and are
    not valid YAML, so the init action is matched with regex against raw text
    instead of yaml.safe_load.
    """

    TEMPLATE_DIR = BUILTIN_LOOPS_DIR / "lib" / "task-templates"
    TEMPLATE_NAMES = [
        "stateful-service-task.yaml.tmpl",
        "data-lib-task.yaml.tmpl",
        "desktop-gui-task.yaml.tmpl",
    ]

    @pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
    def test_init_action_uses_absolute_path(self, template_name: str) -> None:
        path = self.TEMPLATE_DIR / template_name
        assert path.exists(), f"Template not found: {path}"
        text = path.read_text()
        assert "$(pwd)" in text, f"{template_name} init action must use $(pwd)"

    @pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
    def test_init_action_guards_against_already_absolute_run_dir(self, template_name: str) -> None:
        path = self.TEMPLATE_DIR / template_name
        assert path.exists(), f"Template not found: {path}"
        text = path.read_text()
        assert 'case "$DIR" in' in text, (
            f"{template_name} init action must branch on whether $DIR is already absolute"
        )
        assert "/*)" in text


# ---------------------------------------------------------------------------
# TestCodeRunGateOracleWiring — FEAT-2552: code-run-gate oracle wired into
# rn-remediate (parent-side wiring).
# ---------------------------------------------------------------------------


class TestCodeRunGateOracleWiring:
    """FEAT-2552: F2b wires the code-run-gate oracle (FEAT-2551) into
    `rn-remediate` so an `IMPLEMENTED` verdict requires the gate to pass; a
    failing build / test / typecheck / lint / health route to
    `record_gate_failure` and increment the remediation counter.

    These are parent-side tests; FEAT-2551 owns the oracle's behavior tests.
    The oracle writes its verdict to `subloop_outcome_<ID>.txt` directly
    (verified by `TestSubloopSidecarContract` against
    `oracles/code-run-gate.yaml`), so the parent's `record_gate_failure` /
    `record_gate_error` states only need to forward / transform the verdict
    for routing back to the implement path.
    """

    LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-remediate.yaml"
    ORACLE_FILE = BUILTIN_LOOPS_DIR / "oracles" / "code-run-gate.yaml"

    @pytest.fixture
    def data(self) -> dict:
        assert self.LOOP_FILE.exists(), f"Loop file not found: {self.LOOP_FILE}"
        return yaml.safe_load(self.LOOP_FILE.read_text())

    @pytest.fixture
    def oracle_data(self) -> dict:
        assert self.ORACLE_FILE.exists(), f"Oracle not found: {self.ORACLE_FILE}"
        return yaml.safe_load(self.ORACLE_FILE.read_text())

    def test_rn_remediate_validates_after_gate_wiring(self, data: dict) -> None:
        """Confirm `ll-loop validate rn-remediate` exits 0 after F2b's state
        insertions (no `ValidationSeverity.ERROR` findings). The validate
        check is non-vacuous: it includes static `loop:` resolution
        (`_validate_loop_references`) and `with:` binding cross-validation
        (`_validate_with_bindings`) against the oracle's declared parameters.
        """
        from little_loops.fsm.validation import (
            ValidationSeverity,
            load_and_validate,
            validate_fsm,
        )

        fsm, _warnings = load_and_validate(self.LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, (
            f"rn-remediate has validation errors after FEAT-2552 wiring: "
            f"{[str(e) for e in error_list]}"
        )

    def test_code_run_gate_oracle_exists(self, oracle_data: dict) -> None:
        """F2b's `loop: code-run-gate` reference must resolve — without the
        oracle on disk, `_validate_loop_references` raises ERROR-severity
        and blocks the parent loop's load."""
        assert oracle_data.get("name") == "code-run-gate"

    def test_oracle_declares_required_parameters(self, oracle_data: dict) -> None:
        """The oracle's `parameters` block must declare `issue_id` and `run_dir`
        as `required: true` (matches the `with:` bindings F2b sends). The
        `min_pass_rate` parameter is optional with a default (F2b still
        passes it for forward-compat / per-issue override)."""
        params = oracle_data.get("parameters", {})
        for key in ("run_dir", "issue_id"):
            assert params[key]["required"] is True, (
                f"Oracle parameter {key!r} must be required: true"
            )
        assert "min_pass_rate" in params
        assert params["min_pass_rate"]["required"] is False

    def test_oracle_min_pass_rate_has_default(self, oracle_data: dict) -> None:
        """`min_pass_rate` is `required: false` on the oracle; without a
        `context.defaults.min_pass_rate` block the dispatch would fail
        context-resolution for issues that don't override it. FEAT-2551's
        oracle sets a default of 0.95; the parent (F2b) overrides to 1.0
        for strict pass on greenfield issues."""
        ctx = oracle_data.get("context", {})
        assert "min_pass_rate" in ctx, "Oracle context.defaults must include min_pass_rate"

    def test_oracle_writes_sidecar_terminal(self, oracle_data: dict) -> None:
        """The oracle's `aggregate` state writes
        `subloop_outcome_<ID>.txt` so F2b's reader (record_gate_failure /
        record_gate_error) can dispatch on the verdict. Verify the action
        body references the sidecar marker — this is the FEAT-2551 contract
        that locks in option (a) for F2b's
        `TestSubloopSidecarContract` coverage."""
        states = oracle_data.get("states", {})
        agg = states.get("aggregate", {})
        action = agg.get("action", "")
        assert "subloop_outcome_" in action, (
            "code-run-gate.aggregate must write subloop_outcome_<ID>.txt "
            "(FEAT-2551 contract for FEAT-2552 reader)"
        )

    def test_rn_remediate_run_code_gate_state_present(self, data: dict) -> None:
        states = data.get("states", {})
        assert "run_code_gate" in states, "rn-remediate must add run_code_gate (FEAT-2552)"
        assert "record_gate_failure" in states, (
            "rn-remediate must add record_gate_failure (FEAT-2552)"
        )
        assert "record_gate_error" in states, (
            "rn-remediate must add record_gate_error (FEAT-2552 — ENH-2005 mirror)"
        )

    def test_rn_remediate_min_pass_rate_default_is_one(self, data: dict) -> None:
        """rn-remediate's `context.defaults` defines `min_pass_rate: 1.0`
        (strict pass — greenfield issues must build, test, typecheck, lint
        cleanly to be considered IMPLEMENTED). FEAT-2552 refine-issue finding:
        the oracle reads `min_pass_rate` from context; without this default
        sub-loop dispatch fails context-resolution for issues that don't
        override it.
        """
        ctx = data.get("context", {})
        assert ctx.get("min_pass_rate") == 1.0, (
            f"rn-remediate.context.min_pass_rate must be 1.0 (strict pass), "
            f"got {ctx.get('min_pass_rate')!r}"
        )

    def test_record_gate_error_tags_failures_txt_with_infra(self, data: dict) -> None:
        """FEAT-2552: rn-remediate's `record_gate_error` writes GATE_FAILED_INFRA
        to failures.txt so the parent's report can tally gate infrastructure
        failures separately from generic IMPLEMENT_FAILED records. Mirrors the
        record_sub_loop_crash / record_scores_missing / record_size_review_failed
        convention in rn-implement.yaml.
        """
        rec = data["states"]["record_gate_error"]
        assert rec["action_type"] == "shell"
        assert "GATE_FAILED_INFRA" in rec["action"]
        assert "failures.txt" in rec["action"]
