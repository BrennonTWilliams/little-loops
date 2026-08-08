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

GOLDEN = Path(__file__).parent / "fixtures" / "policy_builder" / "sample-decision-table.yaml"
GOLDEN_RUBRIC = Path(__file__).parent / "fixtures" / "policy_builder" / "sample-rubric.yaml"


def _strip_script_style_comments(html: str) -> str:
    """Strip ``<script>``/``<style>`` blocks and HTML comments, leaving visible markup.

    FEAT-2301's jargon-denylist extraction rule: the serializer legitimately
    emits tokens like ``policy_rules`` / ``context.subject`` inside the inlined
    ``<script>`` block, so a naive whole-file grep for denylisted tokens would
    false-positive on them. No such stripping helper existed in this codebase
    before this issue.
    """
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    return html


def _emit_html(tmp_path: Path) -> str:
    logger = Logger(use_color=False)
    args = argparse.Namespace(output=str(tmp_path))
    assert cmd_policy_builder(args, logger) == 0
    return (tmp_path / "policy-router-builder.html").read_text()


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


class TestFeat2301UsabilityStructural:
    """Structurally-gated usability ACs (FEAT-2301) — static-markup assertions
    over the emitted page.

    No jsdom/DOM is available in this codebase (no npm deps, Node stdlib
    only), so these assertions are regex/string checks over the raw HTML text
    per the issue's jargon-denylist extraction rule (strip script/style/
    comments before scanning visible markup).
    """

    def test_no_internal_jargon_in_visible_markup(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        visible = _strip_script_style_comments(html)
        denylist = ["Axis A", "Axis B", "context.subject", "policy_rules", "predicate"]
        for token in denylist:
            assert token not in visible, f"jargon token {token!r} leaked into visible markup"

    def test_fallback_footer_is_structured_not_free_text(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        assert 'id="fallback-row"' in html
        assert '<select id="f-fallback"' in html
        assert '<input type="text" id="f-fallback"' not in html
        fallback_row = re.search(r'<div class="row fallback-row"[^>]*>.*?</div>', html, re.DOTALL)
        assert fallback_row, "fallback-row element not found"
        assert "del" not in fallback_row.group(0), "fallback footer must have no delete/remove control"
        assert "<input" not in fallback_row.group(0), "fallback footer must have no free-text input"

    def test_yaml_is_collapsed_behind_details(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        m = re.search(r'<details[^>]*id="yaml-details"[^>]*>', html)
        assert m, 'expected a <details id="yaml-details"> wrapper around the YAML preview'
        assert "open" not in m.group(0), "YAML <details> must be collapsed by default (no `open`)"
        assert "<summary>" in html
        details_block = re.search(r'<details[^>]*id="yaml-details"[^>]*>.*?</details>', html, re.DOTALL)
        assert details_block is not None
        assert 'id="yaml-preview"' in details_block.group(0), (
            "the <pre> YAML preview must be nested inside the collapsed <details>"
        )
        assert 'id="yaml-summary"' in html, "a plain-summary element must exist alongside the details"

    def test_theme_resolution_order_is_stored_stamped_os_light(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        m = re.search(r"function initTheme\(\)\s*\{.*?\n\}", html, re.DOTALL)
        assert m, "initTheme() not found in emitted script"
        body = m.group(0)
        stored_idx = body.index("stored")
        active_theme_idx = body.index("__ACTIVE_THEME__")
        matchmedia_idx = body.index("matchMedia")
        assert stored_idx < active_theme_idx < matchmedia_idx, (
            "initTheme() must resolve stored toggle -> stamped active_theme -> "
            "OS preference -> light, in that order"
        )

    def test_single_mode_toggle(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        assert html.count('id="mode-switch"') == 1

    def test_seed_and_blank_wiring_present(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        assert "seedExample()" in html
        assert "blankModel()" in html
        assert 'id="start-blank-btn"' in html

    def test_rubric_mode_has_no_dt_only_affordances(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        visible = _strip_script_style_comments(html)
        assert "weight" not in visible.lower(), "Rubric mode must not offer weight inputs"
        assert html.count('id="f-thigh"') == 1
        assert html.count('id="f-tmed"') == 1
        # DT-only affordances (add-rule, reorder, per-outcome authoring,
        # conjunctions) live inside fieldsets that are hidden whenever
        # mode === "rubric" (see applyModeVisibility() in the emitted script).
        assert 'id="rules-fieldset"' in html
        assert 'id="outcomes-fieldset"' in html
        assert 'id="tryit-fieldset"' in html
        assert 'state.mode === "rubric"' in html


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
