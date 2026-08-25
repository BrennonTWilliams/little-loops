"""``ll-artifact policy-builder`` (FEAT-2301).

Emits a single self-contained HTML page for visually authoring
policy-router / rubric FSM loop YAML. The page works over ``file://`` with
no runtime fetch: project-derived data (design-token CSS vars, the
canonical predicate grammar, and the skill/command catalog) is stamped
into the template at generation time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from little_loops.logger import Logger

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


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


def cmd_policy_builder(args: argparse.Namespace, logger: Logger) -> int:
    """Emit the self-contained policy-router builder HTML page.

    Returns 0 on success, 1 on error.
    """
    from little_loops.artifact_template_kit import stamp_page_shell, themed_css_vars
    from little_loops.config.core import BRConfig
    from little_loops.fsm.policy_rules import _py_pattern_to_js, grammar_spec

    try:
        config = BRConfig(Path.cwd())

        css_vars = themed_css_vars(config)

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

        html = stamp_page_shell(template, active_theme=active_theme, css_vars=css_vars)
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
