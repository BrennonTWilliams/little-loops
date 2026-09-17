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


def _load_skill_catalog(project_root: Path) -> list[dict[str, str | None]]:
    """Enumerate installed skills + commands as ``{name, description, args_hint}`` dicts.

    BUG-3490: *project_root* is retained for caller compatibility but no
    longer selects plugin content — the catalog root is resolved via
    :func:`little_loops.skill_expander.resolve_plugin_content_root`
    (env `CLAUDE_PLUGIN_ROOT` > checkout > packaged content), so a normal
    pip-installed consumer sees the little-loops catalog rather than an
    empty scan of its own project root. A resolver returning ``None`` (no
    installed content found anywhere) yields an empty catalog.

    Projects over ``cli/help.py::collect_entries``, deduplicated by callable
    identity (``/ll:<name>``, skill-preferred on collision — matching
    ``_resolve_content_path()``'s skill-first lookup) and sorted by name.
    """
    from little_loops.cli.help import collect_entries
    from little_loops.skill_expander import resolve_plugin_content_root

    plugin_root = resolve_plugin_content_root()
    if plugin_root is None:
        return []

    entries = collect_entries(plugin_root)
    by_name: dict[str, dict[str, str | None]] = {}
    for entry in entries:
        existing = by_name.get(entry.name)
        if existing is not None and existing["kind"] == "skill":
            continue
        by_name[entry.name] = {
            "name": entry.name,
            "description": entry.description,
            "kind": entry.kind,
            "args_hint": entry.argument_hint,
        }

    return [
        {"name": row["name"], "description": row["description"], "args_hint": row["args_hint"]}
        for row in sorted(by_name.values(), key=lambda row: row["name"] or "")
    ]


def cmd_policy_builder(args: argparse.Namespace, logger: Logger) -> int:
    """Emit the self-contained policy-router builder HTML page.

    Returns 0 on success, 1 on error.
    """
    from little_loops import __version__
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
        html = html.replace("/*__GENERATOR_VERSION_JSON__*/", json.dumps(__version__))
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
