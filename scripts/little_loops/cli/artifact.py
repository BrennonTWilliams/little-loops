"""ll-artifact: Generate self-contained human-facing HTML artifacts.

Currently provides the ``policy-builder`` subcommand (FEAT-2301), which emits a
single self-contained HTML page for visually authoring policy-router / rubric
FSM loop YAML. The page works over ``file://`` with no runtime fetch: project-
derived data (design-token CSS vars, the canonical predicate grammar, and the
skill/command catalog) is stamped into the template at generation time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _load_skill_catalog(project_root: Path) -> list[dict[str, str]]:
    """Enumerate skills + commands as ``{name, description}`` dicts.

    Mirrors ``cli/action.py:_load_skills`` globbing precedent. Missing
    directories yield an empty contribution (never raises).
    """
    from little_loops.frontmatter import parse_skill_frontmatter

    catalog: list[dict[str, str]] = []

    skills_dir = project_root / "skills"
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        try:
            content = skill_md.read_text()
        except OSError:
            content = ""
        fm = parse_skill_frontmatter(content) if content else {}
        description = str(fm.get("description", "") or "").strip().strip('"').strip("'")
        catalog.append({"name": name, "description": description})

    commands_dir = project_root / "commands"
    for cmd_md in sorted(commands_dir.glob("*.md")):
        name = cmd_md.stem
        try:
            content = cmd_md.read_text()
        except OSError:
            content = ""
        fm = parse_skill_frontmatter(content) if content else {}
        description = str(fm.get("description", "") or "").strip().strip('"').strip("'")
        catalog.append({"name": name, "description": description})

    return catalog


def _themed_css_vars(config: object) -> str:
    """Return themed CSS custom properties, degrading gracefully to ``""``.

    Loads light + dark design tokens; if either is unavailable (no tokens
    configured for the project), emits empty/neutral scoped blocks so the page
    still renders and the data-theme toggle keeps working.
    """
    from little_loops.design_tokens import load_design_tokens, render_as_css_vars_themed

    light = load_design_tokens(config, theme="light")  # type: ignore[arg-type]
    dark = load_design_tokens(config, theme="dark")  # type: ignore[arg-type]
    if light is None or dark is None:
        # Neutral fallback: empty scoped blocks (CSS fallbacks in the template
        # supply concrete colors).
        return ":root {\n}\n[data-theme=dark] {\n}"
    return render_as_css_vars_themed(light, dark)


def cmd_policy_builder(args: argparse.Namespace, logger: Logger) -> int:
    """Emit the self-contained policy-router builder HTML page.

    Returns 0 on success, 1 on error.
    """
    from little_loops.config.core import BRConfig
    from little_loops.fsm.policy_rules import _py_pattern_to_js, grammar_spec

    try:
        config = BRConfig(Path.cwd())

        css_vars = _themed_css_vars(config)

        spec = grammar_spec()
        # Stamp a JS-translated predicate regex source alongside the spec so the
        # browser builds the same RegExp the canonical Python grammar defines.
        pred_pattern = spec["pred_pattern"]
        spec_for_js = dict(spec)
        if isinstance(pred_pattern, str):
            spec_for_js["pred_pattern"] = _py_pattern_to_js(pred_pattern)
        grammar_json = json.dumps(spec_for_js)

        catalog = _load_skill_catalog(config.project_root)
        catalog_json = json.dumps(catalog)

        template = (_TEMPLATES_DIR / "policy-router-builder.html.tmpl").read_text()
        core_js = (_TEMPLATES_DIR / "policy_builder_core.mjs").read_text()

        # Stamp the configured default theme onto the root <html> element so the
        # page opens in the project's active theme (read into window.__ACTIVE_THEME__
        # by the inline bootstrap, used as the fallback when the OS expresses no
        # prefers-color-scheme). Omitting this was the FEAT-2301 worktree theme bug.
        active_theme = config.design_tokens.active_theme or "light"

        html = template
        html = html.replace('data-theme="light"', f'data-theme="{active_theme}"', 1)
        html = html.replace("/*__THEMED_CSS_VARS__*/", css_vars)
        html = html.replace("/*__GRAMMAR_SPEC_JSON__*/", grammar_json)
        html = html.replace("/*__SKILL_CATALOG_JSON__*/", catalog_json)
        html = html.replace("/*__BUILDER_CORE_JS__*/", core_js)

        output_dir = Path(args.output) if args.output else Path(config.artifacts.default_output_dir)
        if not output_dir.is_absolute():
            output_dir = config.project_root / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "policy-router-builder.html"
        out_path.write_text(html)

        logger.success(f"Wrote policy-router builder to {out_path}")
        return 0
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def main_artifact() -> int:
    """Entry point for the ``ll-artifact`` command.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-artifact", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-artifact",
            description="Generate self-contained human-facing HTML artifacts",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s policy-builder                  # Write policy-router-builder.html to the default output dir
  %(prog)s policy-builder -o build/        # Write to a custom directory

Exit codes:
  0 - Artifact generated successfully
  1 - Error occurred
""",
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        pb = subparsers.add_parser(
            "policy-builder",
            help="Emit the self-contained policy-router / rubric loop builder HTML",
        )
        pb.add_argument(
            "-o",
            "--output",
            type=str,
            default=None,
            help="Output directory (default: config.artifacts.default_output_dir)",
        )

        args = parser.parse_args()

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        if args.command == "policy-builder":
            return cmd_policy_builder(args, logger)
        parser.error(f"unknown command: {args.command}")
        return 1
