"""Emit / drift-guard / golden-validate tests for FEAT-2301 (ll-artifact).

All exercises invoke the emit logic programmatically (never the console script,
which would resolve to a different installed checkout in a worktree).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.artifact import cmd_policy_builder, main_artifact
from little_loops.logger import Logger

GOLDEN = (
    Path(__file__).parent
    / "fixtures"
    / "policy_builder"
    / "sample-decision-table.yaml"
)
GOLDEN_RUBRIC = (
    Path(__file__).parent
    / "fixtures"
    / "policy_builder"
    / "sample-rubric.yaml"
)


def test_emit_writes_html(tmp_path: Path) -> None:
    logger = Logger(use_color=False)
    args = argparse.Namespace(output=str(tmp_path))
    rc = cmd_policy_builder(args, logger)
    assert rc == 0

    out = tmp_path / "policy-router-builder.html"
    assert out.exists()
    html = out.read_text()

    assert "<html" in html
    assert "window.__GRAMMAR_SPEC__" in html
    # Core inlined (proves the .mjs was stamped, not just referenced).
    assert "serializeLoopYaml" in html
    # Themed CSS stamped.
    assert ":root {" in html
    assert "[data-theme=dark] {" in html
    # No leftover placeholders.
    assert "/*__" not in html


def _extract_grammar(html: str) -> dict:
    m = re.search(r"window\.__GRAMMAR_SPEC__\s*=\s*(\{.*?\});", html, re.DOTALL)
    assert m, "grammar spec assignment not found in HTML"
    return json.loads(m.group(1))


def test_emitted_grammar_matches_canonical(tmp_path: Path) -> None:
    from little_loops.fsm.policy_rules import (
        _PRED_PATTERN,
        _py_pattern_to_js,
        grammar_spec,
    )

    logger = Logger(use_color=False)
    args = argparse.Namespace(output=str(tmp_path))
    assert cmd_policy_builder(args, logger) == 0
    html = (tmp_path / "policy-router-builder.html").read_text()

    stamped = _extract_grammar(html)
    canonical = grammar_spec()

    # Operator sets must match canonical exactly.
    assert stamped["ordered_ops"] == canonical["ordered_ops"]
    assert stamped["all_ops"] == canonical["all_ops"]
    # The stamped predicate regex is the JS-translated form of the canonical.
    assert stamped["pred_pattern"] == _py_pattern_to_js(_PRED_PATTERN.pattern)


def test_golden_yaml_validates() -> None:
    from little_loops.fsm.validation import (
        ValidationSeverity,
        load_and_validate,
        validate_fsm,
    )

    fsm, _ = load_and_validate(GOLDEN)
    errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
    assert not errors, [e.message for e in errors]


def test_golden_rubric_yaml_validates() -> None:
    """Rubric mode is the second emit mode; the AC requires *each* mode to
    validate. Mirrors ``test_golden_yaml_validates`` for the decision-table mode.
    """
    from little_loops.fsm.validation import (
        ValidationSeverity,
        load_and_validate,
        validate_fsm,
    )

    fsm, _ = load_and_validate(GOLDEN_RUBRIC)
    errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
    assert not errors, [e.message for e in errors]


class TestArtifactCLIDispatch:
    """ll-artifact argparse dispatch (FEAT-2390). Mirrors the mock-handler
    dispatch convention (test_cli_loop_dispatch): the handler itself is tested
    directly elsewhere, so here we only prove argv routes to it and the return
    code propagates.
    """

    def test_policy_builder_dispatches_and_returns_code(self) -> None:
        argv = ["ll-artifact", "policy-builder", "-o", "build"]
        with (
            patch("sys.argv", argv),
            patch("little_loops.cli.artifact.cmd_policy_builder", return_value=0) as handler,
        ):
            assert main_artifact() == 0
        assert handler.call_count == 1
        ns = handler.call_args.args[0]
        assert ns.output == "build"

    def test_missing_subcommand_errors(self) -> None:
        # subparsers(required=True) → argparse exits non-zero with no command.
        with patch("sys.argv", ["ll-artifact"]):
            try:
                main_artifact()
            except SystemExit as exc:
                assert exc.code != 0
            else:  # pragma: no cover - defensive
                raise AssertionError("expected SystemExit for missing subcommand")
