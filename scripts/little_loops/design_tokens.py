"""Design token loader and renderers for little-loops artifact-generating loops.

Loads a three-layer token system (primitives → semantic → theme) from JSON files
configured in BRConfig.design_tokens, resolves {token.reference} aliases, and
provides rendering helpers for prompts and CSS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config.core import BRConfig


@dataclass(frozen=True)
class DesignTokens:
    """Resolved design token set."""

    primitives: dict[str, Any]
    semantic: dict[str, Any]
    theme: dict[str, Any]
    resolved: dict[str, str]  # flat dotted-name -> concrete value, post reference-resolution
    source_path: Path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Recursively flatten a nested dict to dotted-key -> leaf-value pairs."""
    result: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            result.update(_flatten(value, full_key))
    else:
        result[prefix] = obj
    return result


def _resolve_references(
    flat: dict[str, Any],
    primitives_flat: dict[str, Any],
    *,
    _resolving: frozenset[str] | None = None,
) -> dict[str, str]:
    """Resolve {token.reference} placeholders in *flat* against *primitives_flat*.

    Returns a new dict mapping every key to its concrete string value.
    Raises ValueError on unknown references or circular references.
    """
    if _resolving is None:
        _resolving = frozenset()

    resolved: dict[str, str] = {}
    for key, raw in flat.items():
        resolved[key] = _resolve_value(key, raw, flat, primitives_flat, _resolving)
    return resolved


def _resolve_value(
    key: str,
    raw: Any,
    flat: dict[str, Any],
    primitives_flat: dict[str, Any],
    resolving: frozenset[str],
) -> str:
    value = str(raw)
    if not (value.startswith("{") and value.endswith("}")):
        return value

    ref_name = value[1:-1]
    if ref_name in resolving:
        raise ValueError(f"Circular token reference: {key} -> {ref_name}")

    # Look in primitives first, then the same layer
    if ref_name in primitives_flat:
        return str(primitives_flat[ref_name])
    if ref_name in flat:
        return _resolve_value(
            ref_name,
            flat[ref_name],
            flat,
            primitives_flat,
            resolving | {key},
        )
    raise ValueError(f"Unknown token reference '{ref_name}' in '{key}'")


def load_design_tokens(
    config: BRConfig,
    theme: str | None = None,
) -> DesignTokens | None:
    """Load and resolve design tokens from the project config.

    Returns None when design_tokens.enabled is False or the token path does not exist.
    Raises ValueError on circular or unknown token references.
    """
    dt_cfg = config.design_tokens
    if not dt_cfg.enabled:
        return None

    token_path = config.project_root / dt_cfg.path
    if not token_path.exists():
        return None

    primitives = _load_json(token_path / dt_cfg.primitives_file)
    semantic = _load_json(token_path / dt_cfg.semantic_file)

    active_theme = theme or dt_cfg.active_theme
    theme_file = token_path / dt_cfg.themes_dir / f"{active_theme}.json"
    theme_data = _load_json(theme_file)

    primitives_flat = _flatten(primitives)
    semantic_flat = _flatten(semantic)
    theme_flat = _flatten(theme_data)

    # Layer: theme overrides semantic, semantic is resolved against primitives
    merged_flat: dict[str, Any] = {**semantic_flat, **theme_flat}
    resolved = _resolve_references(merged_flat, primitives_flat)
    # Also include primitive leaf values in resolved
    for k, v in primitives_flat.items():
        if k not in resolved:
            resolved[k] = str(v)

    return DesignTokens(
        primitives=primitives,
        semantic=semantic,
        theme=theme_data,
        resolved=resolved,
        source_path=token_path,
    )


def render_as_prompt_context(tokens: DesignTokens) -> str:
    """Return a compact markdown snippet listing resolved token values."""
    lines = ["**Design tokens** (resolved values):"]
    lines.append("```")
    for name, value in sorted(tokens.resolved.items()):
        lines.append(f"{name}: {value}")
    lines.append("```")
    return "\n".join(lines)


def render_as_css_vars(tokens: DesignTokens) -> str:
    """Return a CSS :root { ... } block declaring all resolved tokens as custom properties."""
    lines = [":root {"]
    for name, value in sorted(tokens.resolved.items()):
        css_name = "--" + name.replace(".", "-")
        lines.append(f"  {css_name}: {value};")
    lines.append("}")
    return "\n".join(lines)
