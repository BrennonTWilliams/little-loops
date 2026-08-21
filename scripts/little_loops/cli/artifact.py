"""ll-artifact: Generate self-contained human-facing artifacts.

Provides:
- ``policy-builder`` (FEAT-2301): a single self-contained HTML page for
  visually authoring policy-router / rubric FSM loop YAML. The page works
  over ``file://`` with no runtime fetch: project-derived data (design-token
  CSS vars, the canonical predicate grammar, and the skill/command catalog)
  is stamped into the template at generation time.
- ``design-md export`` (ENH-3268): a lossy export of a design-token profile
  to a valid DESIGN.md (https://github.com/google-labs-code/design.md), for
  handoff to Cursor / Copilot / another little-loops project.
"""

from __future__ import annotations

import argparse
import importlib.resources
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

    DESIGN.md sources (ENH-3264) have no theme mechanism, so entering
    load_design_tokens() twice would both duplicate work and emit its
    theme-degradation warning twice. Enter it once, branch on the returned
    DesignTokens.source, and only make the second themed call for a profile
    source.
    """
    from little_loops.design_tokens import load_design_tokens, render_as_css_vars_themed

    light = load_design_tokens(config, theme="light")  # type: ignore[arg-type]
    if light is None:
        # Neutral fallback: empty scoped blocks (CSS fallbacks in the template
        # supply concrete colors).
        return ":root {\n}\n[data-theme=dark] {\n}"
    if light.source == "design_md":
        dark = light
    else:
        dark = load_design_tokens(config, theme="dark")  # type: ignore[arg-type]
        if dark is None:
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


def _resolve_export_profile_root(config: object, profile_name: str) -> Path | None:
    """Resolve a named profile's token root for `design-md export --profile`.

    Resolution order (ENH-3268): (1) the project's configured profiles
    directory, so a locally-authored profile wins; (2) the packaged
    built-in (`default`/`warm-paper`/`editorial-mono`) via
    `importlib.resources`, the wheel-safe accessor for a profile never
    materialized in the project. `_resolve_token_root` (design_tokens.py)
    reads `dt_cfg.active` directly and has no profile-name override, so it
    is not reusable unchanged for an explicit `--profile` name.
    """
    dt_cfg = config.design_tokens  # type: ignore[attr-defined]
    base_path = config.project_root / dt_cfg.path  # type: ignore[attr-defined]
    profiles_subdir = dt_cfg.profiles_dir or "profiles"
    project_root_candidate = base_path / profiles_subdir / profile_name
    if project_root_candidate.is_dir():
        return project_root_candidate

    packaged = importlib.resources.files("little_loops").joinpath(
        "templates", "design-tokens", "profiles", profile_name
    )
    packaged_path = Path(str(packaged))
    if packaged_path.is_dir():
        return packaged_path
    return None


def _dropped_theme_names(token_root: Path, themes_dir: str, active_theme: str) -> list[str]:
    """Sibling theme files under *token_root* other than *active_theme*.

    Requires listing the filesystem, which is why this lives in the CLI
    layer rather than in the pure `render_as_design_md` (ENH-3268).
    """
    themes_path = token_root / themes_dir
    if not themes_path.is_dir():
        return []
    return sorted(p.stem for p in themes_path.glob("*.json") if p.stem != active_theme)


def cmd_design_md_export(args: argparse.Namespace, logger: Logger) -> int:
    """Export a design-token profile as a single-theme DESIGN.md document.

    Returns 0 on success, 1 on error (no design tokens available, an
    unresolvable ``--profile``, or a color-name collision in the export).
    """
    from little_loops.config.core import BRConfig
    from little_loops.design_tokens import (
        DesignMdColorCollisionError,
        DesignTokens,
        _design_md_dropped_groups,
        load_design_tokens,
        load_profile_tokens_from_root,
        render_as_design_md,
    )

    try:
        config = BRConfig(Path.cwd())
        dt_cfg = config.design_tokens

        dropped_themes: list[str] = []
        tokens: DesignTokens | None
        if args.profile:
            token_root = _resolve_export_profile_root(config, args.profile)
            if token_root is None:
                logger.error(
                    f"Profile '{args.profile}' was not found in the project's "
                    "profiles directory or the packaged built-ins "
                    "(default, warm-paper, editorial-mono)."
                )
                return 1
            active_theme = args.theme or dt_cfg.active_theme
            tokens = load_profile_tokens_from_root(config, token_root, theme=args.theme)
            dropped_themes = _dropped_theme_names(token_root, dt_cfg.themes_dir, active_theme)
        else:
            tokens = load_design_tokens(config, theme=args.theme)
            if tokens is None:
                logger.error(
                    "No design tokens available: design_tokens.enabled is false, "
                    "the token path is missing, or the active profile is missing."
                )
                return 1
            if tokens.source == "profile":
                active_theme = args.theme or dt_cfg.active_theme
                dropped_themes = _dropped_theme_names(
                    tokens.source_path, dt_cfg.themes_dir, active_theme
                )

        try:
            document = render_as_design_md(tokens)
        except DesignMdColorCollisionError as exc:
            logger.error(str(exc))
            return 1

        notes = _design_md_dropped_groups(tokens)
        if tokens.source == "profile":
            active_theme = args.theme or dt_cfg.active_theme
            theme_note = f"exported theme '{active_theme}'"
            if dropped_themes:
                theme_note += f"; dropped theme(s): {', '.join(dropped_themes)}"
            notes.insert(0, theme_note)

        if notes:
            sys.stderr.write(
                f"[little-loops] Warning: design-md export dropped: {'; '.join(notes)}\n"
            )

        if args.output:
            out_path = Path(args.output)
            if not out_path.is_absolute():
                out_path = config.project_root / out_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(document)
            logger.success(f"Wrote DESIGN.md export to {out_path}")
        else:
            sys.stdout.write(document)

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
            description="Generate self-contained human-facing artifacts",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s policy-builder                  # Write policy-router-builder.html to the default output dir
  %(prog)s policy-builder -o build/        # Write to a custom directory
  %(prog)s design-md export                # Print the project's active profile as DESIGN.md to stdout
  %(prog)s design-md export -o DESIGN.md   # Write to a file
  %(prog)s design-md export --profile warm-paper --theme dark -o DESIGN.md

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

        design_md = subparsers.add_parser(
            "design-md",
            help="DESIGN.md interop for the project's design-token profiles",
        )
        design_md_subparsers = design_md.add_subparsers(dest="subcommand", required=True)

        dme = design_md_subparsers.add_parser(
            "export",
            help="Export a design-token profile as a single-theme DESIGN.md document",
        )
        dme.add_argument(
            "--profile",
            type=str,
            default=None,
            help=(
                "Named profile to export (project profiles dir first, then the "
                "packaged built-ins). Default: the project's active/configured source."
            ),
        )
        dme.add_argument(
            "--theme",
            type=str,
            default=None,
            help="Theme to flatten into the single-theme output (default: active_theme)",
        )
        dme.add_argument(
            "-o",
            "--output",
            type=str,
            default=None,
            help="Output file (default: stdout). The dropped-groups note always goes to stderr.",
        )

        args = parser.parse_args()

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        if args.command == "policy-builder":
            return cmd_policy_builder(args, logger)
        if args.command == "design-md" and args.subcommand == "export":
            return cmd_design_md_export(args, logger)
        parser.error(f"unknown command: {args.command}")
        return 1
