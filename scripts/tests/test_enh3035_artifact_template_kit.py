"""Tests for the shared artifact template kit (ENH-3035).

Covers: the kit module exists with a documented entry point, design-token
stamping is a separately callable unit, `policy-builder` renders
byte-identically to a pre-port golden fixture after being ported onto the
kit, and the kit's stamping unit accepts a body whose token values were
baked in as literals by a real `ll-artifact templatize` output (the narrow
reading of the templatize-reachability AC — see the issue's Decisions).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops import artifact_template_kit
from little_loops.cli.artifact import main_artifact
from little_loops.cli.artifact.policy_builder import cmd_policy_builder
from little_loops.logger import Logger

GOLDEN = Path(__file__).parent / "fixtures" / "policy_builder" / "golden_policy_router_builder.html"


def test_kit_module_has_documented_entry_point() -> None:
    assert artifact_template_kit.__doc__
    assert artifact_template_kit.themed_css_vars.__doc__
    assert artifact_template_kit.stamp_page_shell.__doc__


def test_themed_css_vars_is_separately_callable() -> None:
    from little_loops.config.core import BRConfig

    # No template/body involved at all — proves it is its own unit, not
    # inlined into a stamping pass. This repo's own design_tokens config
    # (warm-paper + dark) exercises the themed branch, not the degraded one.
    config = BRConfig(Path.cwd())
    css = artifact_template_kit.themed_css_vars(config)
    assert ":root {" in css
    assert "[data-theme=dark] {" in css


def test_stamp_page_shell_stamps_theme_and_css_placeholders() -> None:
    template = '<html data-theme="light"><style>/*__THEMED_CSS_VARS__*/</style></html>'
    html = artifact_template_kit.stamp_page_shell(
        template, active_theme="dark", css_vars=":root{--x:1}"
    )
    assert 'data-theme="dark"' in html
    assert ":root{--x:1}" in html
    assert "/*__THEMED_CSS_VARS__*/" not in html


def test_stamp_page_shell_accepts_body_without_placeholders() -> None:
    # Narrow reading of the templatize-reachability AC: a body carrying no
    # stamp points (e.g. baked-in literal token values) must not raise —
    # str.replace with no match is a no-op.
    body = "<html><body>hello [[= greeting =]]</body></html>"
    html = artifact_template_kit.stamp_page_shell(body, active_theme="dark", css_vars="x")
    assert html == body


def test_policy_builder_renders_byte_identically_to_golden_fixture(tmp_path: Path) -> None:
    logger = Logger(use_color=False)
    args = argparse.Namespace(output=str(tmp_path))
    assert cmd_policy_builder(args, logger) == 0
    actual = (tmp_path / "policy-router-builder.html").read_bytes()
    expected = GOLDEN.read_bytes()
    assert actual == expected


class TestKitAcceptsTemplatizedBody:
    """Third-consumer AC: a real `ll-artifact templatize` output run through the kit."""

    def _run(self, argv: list[str]) -> int:
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            return main_artifact()
        finally:
            sys.argv = old_argv

    def test_templatized_body_with_baked_in_token_literal_stamps_without_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        # A loop-generated HTML artifact whose author baked a design-token
        # color value in as a literal (via prompt-time design_tokens_context)
        # instead of a `var(--...)` reference — the shape this AC targets.
        artifact_html = (
            '<html><body style="background:#fdfbf6"><h1>Report for ACME</h1></body></html>'
        )
        artifact = tmp_path / "out" / "index.html"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(artifact_html.encode())

        source = tmp_path / "docs" / "SRC.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"# ACME\n")

        start = artifact_html.index("ACME")
        regions_map = tmp_path / "map.json"
        regions_map.write_text(
            f'{{"regions": [{{"start": {start}, "end": {start + len("ACME")}, "expr": "company"}}]}}'
        )

        out_dir = tmp_path / "artifacts" / "templates" / "report.llat"
        code = self._run(
            [
                "templatize",
                str(artifact),
                str(source),
                "-o",
                str(out_dir),
                "--regions",
                str(regions_map),
            ]
        )
        assert code == 0

        body = (out_dir / "template.html.j2").read_text()
        # The baked-in literal survived templatize unchanged — no
        # `var(--...)` rewriting (narrow reading, ENH-3035 Decisions).
        assert "#fdfbf6" in body
        assert "[[= company =]]" in body

        # The kit's stamping unit accepts this body — carrying no stamp
        # points of its own — without raising.
        stamped = artifact_template_kit.stamp_page_shell(
            body, active_theme="dark", css_vars=":root{--surface-primary:#fdfbf6}"
        )
        assert stamped == body
