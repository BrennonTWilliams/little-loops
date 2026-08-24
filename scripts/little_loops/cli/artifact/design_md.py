"""``ll-artifact design-md export`` (ENH-3268).

A lossy export of a design-token profile to a valid DESIGN.md
(https://github.com/google-labs-code/design.md), for handoff to
Cursor / Copilot / another little-loops project.
"""

from __future__ import annotations

import argparse
import importlib.resources
import sys
from pathlib import Path

from little_loops.logger import Logger


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
