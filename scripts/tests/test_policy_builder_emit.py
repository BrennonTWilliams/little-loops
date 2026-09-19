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

import pytest

from little_loops.cli.artifact import cmd_policy_builder, main_artifact
from little_loops.logger import Logger

GOLDEN = Path(__file__).parent / "fixtures" / "policy_builder" / "sample-decision-table.yaml"
GOLDEN_RUBRIC = Path(__file__).parent / "fixtures" / "policy_builder" / "sample-rubric.yaml"
GOLDEN_ISSUE_LIFECYCLE = (
    Path(__file__).parent / "fixtures" / "policy_builder" / "sample-issue-lifecycle.yaml"
)


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


def test_generator_version_is_stamped_from_package_version(tmp_path: Path) -> None:
    """ENH-3487: `window.__GENERATOR_VERSION__` seeds `BuilderProject.generatorVersion`."""
    from little_loops import __version__

    html = _emit_html(tmp_path)
    m = re.search(r'window\.__GENERATOR_VERSION__\s*=\s*"([^"]*)"', html)
    assert m, "window.__GENERATOR_VERSION__ assignment not found in emitted HTML"
    assert m.group(1) == __version__


def _extract_grammar(html: str) -> dict:
    m = re.search(r"window\.__GRAMMAR_SPEC__\s*=\s*(\{.*?\});", html, re.DOTALL)
    assert m, "grammar spec assignment not found in HTML"
    return json.loads(m.group(1))


def _extract_skill_catalog(html: str) -> list[dict]:
    """ENH-3491: extract the stamped skill catalog array.

    Regexes the ``window.__SKILL_CATALOG__ = [...]`` assignment (an array,
    unlike ``_extract_grammar``'s object-shaped pattern) out of the rendered
    HTML — the ``/*__SKILL_CATALOG_JSON__*/`` source-only placeholder token is
    replaced away at generation time and is never present to match.
    """
    m = re.search(r"window\.__SKILL_CATALOG__\s*=\s*(\[.*?\]);", html, re.DOTALL)
    assert m, "skill catalog assignment not found in HTML"
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


def _extract_confidence_gate(html: str) -> dict:
    """ENH-3492: extract the stamped `window.__CONFIDENCE_GATE__` object."""
    m = re.search(r"window\.__CONFIDENCE_GATE__\s*=\s*(\{.*?\});", html, re.DOTALL)
    assert m, "confidence gate assignment not found in HTML"
    return json.loads(m.group(1))


def test_emitted_confidence_gate_matches_config(tmp_path: Path) -> None:
    """ENH-3492: stamped confidence-gate JSON matches BRConfig, following the
    `test_emitted_grammar_matches_canonical` extract-and-compare pattern."""
    from little_loops.config.core import BRConfig

    html = _emit_html(tmp_path)
    stamped = _extract_confidence_gate(html)
    canonical = BRConfig(Path.cwd()).commands.confidence_gate

    assert stamped["enabled"] == canonical.enabled
    assert stamped["readiness_threshold"] == canonical.readiness_threshold
    assert stamped["outcome_threshold"] == canonical.outcome_threshold


def test_skill_catalog_stamps_args_hint(tmp_path: Path) -> None:
    """ENH-3491: `_load_skill_catalog` carries `HelpEntry.argument_hint` through
    as a nullable `args_hint` key on every stamped row, and a skill with a
    known hint stamps it verbatim.
    """
    html = _emit_html(tmp_path)
    catalog = _extract_skill_catalog(html)
    assert catalog, "expected a non-empty skill catalog"
    for row in catalog:
        assert "args_hint" in row
    known = next((row for row in catalog if row["name"] == "manage-issue"), None)
    assert known is not None, "expected 'manage-issue' in the stamped catalog"
    assert known["args_hint"] == "[type] [action] [issue-id]"


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


def test_golden_issue_lifecycle_yaml_validates() -> None:
    """FEAT-3474: issue_lifecycle is the third emit mode.

    Unlike ``test_golden_yaml_validates``/``test_golden_rubric_yaml_validates``
    (which filter to ERROR only), this asserts on *every* severity —
    ``validate_fsm(fsm) == []`` — per the issue's explicit "zero warnings of
    any rule" AC. Filtering to ERROR only would let the three warnings the
    issue calls out (BUG-2813 terminal-action, missing ``scope:``, MR-12
    pruning-profile) pass silently, leaving the zero-warnings AC unenforced.
    """
    from little_loops.fsm.validation import load_and_validate, validate_fsm

    fsm, _ = load_and_validate(GOLDEN_ISSUE_LIFECYCLE)
    errors = validate_fsm(fsm)
    assert errors == [], [e.message for e in errors]


class TestFeat3504BuilderEmitsSupportedMode:
    """FEAT-3504 Step 0: builder-emitted issue_lifecycle YAML must pass
    ``validate_policy_revision`` (mode acceptance), not just the pre-existing
    structural ``validate_fsm`` golden checks above.
    """

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "sample-issue-lifecycle.yaml",
            "sample-issue-lifecycle-verification.yaml",
            "sample-issue-lifecycle-destinations.yaml",
        ],
    )
    def test_golden_lifecycle_yaml_passes_validate_policy_revision(
        self, tmp_path: Path, fixture_name: str
    ) -> None:
        from little_loops.cli.artifact.policy_revision import validate_policy_revision

        fixture_path = Path(__file__).parent / "fixtures" / "policy_builder" / fixture_name
        outcome = validate_policy_revision(fixture_path.read_bytes(), project_root=tmp_path)
        assert outcome.ok is True, outcome.errors
        assert outcome.mode == "issue_lifecycle"


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
        assert "del" not in fallback_row.group(0), (
            "fallback footer must have no delete/remove control"
        )
        assert "<input" not in fallback_row.group(0), "fallback footer must have no free-text input"

    def test_yaml_is_collapsed_behind_details(self, tmp_path: Path) -> None:
        html = _emit_html(tmp_path)
        m = re.search(r'<details[^>]*id="yaml-details"[^>]*>', html)
        assert m, 'expected a <details id="yaml-details"> wrapper around the YAML preview'
        assert "open" not in m.group(0), "YAML <details> must be collapsed by default (no `open`)"
        assert "<summary>" in html
        details_block = re.search(
            r'<details[^>]*id="yaml-details"[^>]*>.*?</details>', html, re.DOTALL
        )
        assert details_block is not None
        assert 'id="yaml-preview"' in details_block.group(0), (
            "the <pre> YAML preview must be nested inside the collapsed <details>"
        )
        assert 'id="yaml-summary"' in html, (
            "a plain-summary element must exist alongside the details"
        )

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

    def test_persistence_and_history_affordances_present(self, tmp_path: Path) -> None:
        """ENH-3487: undo/redo, Save/Open project, and live-region feedback."""
        html = _emit_html(tmp_path)
        assert 'id="undo-btn"' in html
        assert 'id="redo-btn"' in html
        assert 'id="save-project-btn"' in html
        assert 'id="open-project-btn"' in html
        assert 'id="open-project-input"' in html
        assert 'id="live-status"' in html
        assert 'aria-live="polite"' in html

    def test_connected_panel_announcers_and_focus_targets(self, tmp_path: Path) -> None:
        """BUG-3512: static announcers + focus targets; no live semantics on rebuilt logs."""
        html = _emit_html(tmp_path)

        def tag(el_id: str) -> str:
            m = re.search(rf'<[a-z]+\b[^>]*\bid="{el_id}"[^>]*>', html)
            assert m, f"missing #{el_id}"
            return m.group(0)

        live = tag("conn-live")
        assert 'role="status"' in live and 'aria-live="polite"' in live
        assert 'role="alert"' in tag("conn-alert")
        assert 'role="status"' in tag("conn-review-info")
        status = tag("conn-status")
        assert 'tabindex="-1"' in status and 'role="group"' in status
        assert "aria-label=" in status
        assert 'tabindex="-1"' in tag("conn-unavailable")
        assert 'button[aria-disabled="true"]' in html
        for rebuilt in ("conn-status", "conn-notices"):
            assert "aria-live" not in tag(rebuilt)
            assert 'role="alert"' not in tag(rebuilt)
        assert 'role="status"' not in tag("conn-notices")
        assert 'role="status"' not in status

    def test_advanced_action_details_collapsed_by_default(self, tmp_path: Path) -> None:
        """ENH-3491: action editors and the max-steps budget are collapsed by
        default behind an advanced `<details>`, and rules/try-it precede it in
        the markup (Fields, Rules, Try it, Export ordering)."""
        html = _emit_html(tmp_path)
        m = re.search(r'<details[^>]*id="advanced-details"[^>]*>', html)
        assert m, 'expected a <details id="advanced-details"> wrapper'
        assert "open" not in m.group(0), "advanced <details> must be collapsed by default"
        details_block = re.search(
            r'<details[^>]*id="advanced-details"[^>]*>.*?</details>', html, re.DOTALL
        )
        assert details_block is not None
        assert 'id="outcomes-fieldset"' in details_block.group(0)
        assert 'id="f-maxsteps"' in details_block.group(0)
        assert html.index('id="rules-fieldset"') < html.index('id="advanced-details"')
        assert html.index('id="tryit-fieldset"') < html.index('id="advanced-details"')

    def test_task_preset_buttons_present_grouped_with_start_blank(self, tmp_path: Path) -> None:
        """ENH-3491: preset buttons render (via taskPresets()) grouped with
        Start blank, in every mode (not gated behind a mode check in markup)."""
        html = _emit_html(tmp_path)
        assert 'id="preset-row"' in html
        preset_row = re.search(r'<div class="row" id="preset-row"[^>]*>.*?</div>', html, re.DOTALL)
        assert preset_row is not None
        assert 'id="start-blank-btn"' in preset_row.group(0)
        assert "renderPresetButtons()" in html
        assert "taskPresets()" in html


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
