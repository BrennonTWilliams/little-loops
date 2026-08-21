"""Design token loader and renderers for little-loops artifact-generating loops.

Loads a multi-layer token system (primitives → semantic → typography →
spacing → theme) from JSON files configured in BRConfig.design_tokens,
resolves {token.reference} aliases, and provides rendering helpers for
prompts and CSS.

ENH-1768 introduced profiles: token files live under
`<path>/<profiles_dir or "profiles">/<active>/` and the loader transparently
falls back to the legacy flat `<path>/` layout when no profile directory
exists, so pre-ENH-1768 projects keep working.
"""

from __future__ import annotations

import json
import sys
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
    # Token root directory for a profile source, or the DESIGN.md file itself
    # when source == "design_md".
    source_path: Path
    # Prose body (frontmatter stripped) for a design_md source; "" otherwise.
    # Populated even on degraded design_md paths (ENH-3264/ENH-3267).
    guidance: str = ""
    # "profile" | "design_md" — public, not informational: cli/artifact.py's
    # _themed_css_vars() branches on it to decide whether a second themed
    # load is needed (DESIGN.md has no theme mechanism).
    source: str = "profile"


# DESIGN.md (https://github.com/google-labs-code/design.md, Apache-2.0) discovery
# constant. Case-exact, project-root only — not configurable (ENH-3264).
DESIGN_MD_FILENAME = "DESIGN.md"

# One namespace-mapping table drives every DESIGN.md -> profile-namespace rename.
_DESIGN_MD_NAMESPACE_MAP = {
    "colors": "color",
    "typography": "font",
    "spacing": "space",
    "rounded": "radius",
}

# Well-known DESIGN.md color names mapped onto the four semantic roles
# render_as_prompt_context() groups by. Matches the naming conventions used
# by the vendored spec example (Material-Design-style: on-*, surface*,
# outline*, primary/secondary/tertiary/error). Names that don't match any
# rule keep a plain color.<name> key (Resolved via the residual bucket).
def _classify_design_md_color_role(name: str) -> str | None:
    parts = name.split("-")
    if "on" in parts or name in ("text", "foreground"):
        return "text"
    if name.startswith(("surface", "background", "inverse-surface")):
        return "surface"
    if name.startswith("outline") or name == "border":
        return "border"
    if name.startswith(("primary", "secondary", "tertiary", "accent", "error")):
        return "action"
    return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Recursively flatten a nested dict to dotted-key -> leaf-value pairs.

    Supports both legacy flat layout (``{"key": "value"}``) and W3C DTCG
    format (``{"key": {"$value": "value"}}``). When a dict has a ``$value``
    key it is treated as a leaf and ``$``-prefixed metadata siblings
    (``$type``, ``$description``, etc.) are ignored.
    """
    result: dict[str, Any] = {}
    if isinstance(obj, dict):
        if "$value" in obj:
            result[prefix] = obj["$value"]
            return result
        for key, value in obj.items():
            if key.startswith("$"):
                continue
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
    # Fallback for legacy partially-flattened DTCG inputs where a reference
    # like {typography.fontFamily.heading} may need a .$value suffix lookup.
    dv_ref = ref_name + ".$value"
    if dv_ref in primitives_flat:
        return str(primitives_flat[dv_ref])
    if dv_ref in flat:
        return _resolve_value(
            dv_ref,
            flat[dv_ref],
            flat,
            primitives_flat,
            resolving | {key},
        )
    raise ValueError(f"Unknown token reference '{ref_name}' in '{key}'")


def _resolve_token_root(dt_cfg: Any, base_path: Path, *, quiet: bool = False) -> Path | None:
    """Resolve the directory that holds this project's active token files.

    Resolution order (ENH-1768):
      1. `<base_path>/<profiles_dir or "profiles">/<active>/` (new layout)
      2. `<base_path>/` (legacy flat layout — pre-ENH-1768 projects)

    Returns None when neither layout is materialized. When a profiles dir
    exists but the requested `active` profile is missing, emits a warning
    to stderr (unless `quiet=True`) and returns None (degrades cleanly, no
    crash). `quiet=True` is used by the `design_tokens.source: auto`
    materialization probe (ENH-3264), which must not print "degrading to
    no tokens" before it has even checked whether DESIGN.md can succeed.
    """
    profiles_subdir = dt_cfg.profiles_dir or "profiles"
    profiles_root = base_path / profiles_subdir
    active_root = profiles_root / dt_cfg.active

    if active_root.is_dir():
        return active_root

    if profiles_root.is_dir():
        # Multi-profile layout installed but the requested profile is missing.
        if not quiet:
            sys.stderr.write(
                f"[little-loops] Warning: design_tokens.active='{dt_cfg.active}' "
                f"but '{active_root}' does not exist; degrading to no tokens.\n"
            )
        return None

    # Legacy flat layout (pre-ENH-1768): treat <base_path> itself as the
    # token root. Missing files are loaded as empty dicts by _load_json.
    return base_path


def _find_design_md(project_root: Path) -> Path | None:
    """Case-exact lookup for a root DESIGN.md.

    Path.exists() is case-insensitive on APFS (macOS) and NTFS, so
    `(project_root / "DESIGN.md").exists()` would incorrectly match a file
    actually named `design.md`. Compare directory-listed names instead.
    """
    try:
        names = {p.name for p in project_root.iterdir() if p.is_file()}
    except OSError:
        return None
    if DESIGN_MD_FILENAME not in names:
        return None
    return project_root / DESIGN_MD_FILENAME


def _normalize_design_md_leaf(value: Any, *, list_mode: str) -> Any:
    """Normalize a DESIGN.md frontmatter leaf value before it reaches _flatten().

    A raw list is not a valid _flatten() leaf: it would be stored verbatim
    and str()'d into a Python repr downstream (`['Inter', 'sans-serif']`).
    `list_mode="join"` collapses a font-stack-style list into a single
    comma-separated string; `list_mode="index"` is handled by the caller
    (it expands into multiple <key>.0, <key>.1, ... entries instead).
    """
    if isinstance(value, list) and list_mode == "join":
        return ", ".join(str(v) for v in value)
    return value


def _rename_design_md_leaves(
    obj: Any, old_prefix: str, new_prefix: str, *, list_mode: str
) -> tuple[Any, dict[str, str]]:
    """Recursively rename a nested DESIGN.md block onto its new namespace.

    Returns the renamed structure plus a full old-dotted-key -> new-dotted-key
    map for every leaf, which drives the `{ref}` alias rewrite (a
    namespace-prefix-only rewrite is not sufficient once colors have been
    role-mapped two levels deeper).
    """
    key_map: dict[str, str] = {}
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            old_key = f"{old_prefix}.{key}"
            new_key = f"{new_prefix}.{key}"
            sub_result, sub_map = _rename_design_md_leaves(
                value, old_key, new_key, list_mode=list_mode
            )
            result[key] = sub_result
            key_map.update(sub_map)
        return result, key_map
    if isinstance(obj, list) and list_mode == "index":
        indexed: dict[str, Any] = {}
        for i, item in enumerate(obj):
            indexed[str(i)] = item
            key_map[f"{old_prefix}.{i}"] = f"{new_prefix}.{i}"
        return indexed, key_map
    key_map[old_prefix] = new_prefix
    return _normalize_design_md_leaf(obj, list_mode=list_mode), key_map


def _map_design_md_namespaces(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Rename DESIGN.md frontmatter namespaces onto profile namespaces.

    Drops `components` (structural guidance, not tokens — reaches the model
    via ENH-3267's prose channel instead). Applies the semantic-role mapping
    to well-known color names so render_as_prompt_context()'s role-grouping
    gate can fire for a DESIGN.md source. Returns the nested mapped dict —
    the caller both `_flatten()`s it for `resolved` and hands it to
    `DesignTokens.semantic` directly — plus the full old-key -> new-key map
    used to rewrite `{ref}` alias strings in the same step.
    """
    mapped: dict[str, Any] = {}
    key_map: dict[str, str] = {}

    for namespace, block in data.items():
        if namespace == "components":
            continue
        new_namespace = _DESIGN_MD_NAMESPACE_MAP.get(namespace, namespace)

        if namespace == "colors" and isinstance(block, dict):
            color_bucket: dict[str, Any] = {}
            for name, value in block.items():
                role = _classify_design_md_color_role(name)
                normalized = _normalize_design_md_leaf(value, list_mode="join")
                if role:
                    color_bucket.setdefault(role, {})[name] = normalized
                    key_map[f"{namespace}.{name}"] = f"{new_namespace}.{role}.{name}"
                else:
                    color_bucket[name] = normalized
                    key_map[f"{namespace}.{name}"] = f"{new_namespace}.{name}"
            mapped[new_namespace] = color_bucket
            continue

        list_mode = "join" if namespace == "typography" else "index"
        if isinstance(block, dict):
            renamed, sub_key_map = _rename_design_md_leaves(
                block, namespace, new_namespace, list_mode=list_mode
            )
            mapped[new_namespace] = renamed
            key_map.update(sub_key_map)
        else:
            mapped[new_namespace] = _normalize_design_md_leaf(block, list_mode="join")
            key_map[namespace] = new_namespace

    return mapped, key_map


def _rewrite_design_md_aliases(obj: Any, key_map: dict[str, str]) -> Any:
    """Rewrite `{ref}` alias strings using the post-mapping key map first,
    falling back to a namespace-prefix rename for a reference naming
    something that was never an individual leaf key. A prefix-only rewrite
    is not sufficient on its own: role mapping relocates e.g.
    `colors.primary` to `color.action.primary`, so `{colors.primary}` must
    resolve via the key map, not a `{colors.X}` -> `{color.X}` swap.
    """
    if isinstance(obj, dict):
        return {k: _rewrite_design_md_aliases(v, key_map) for k, v in obj.items()}
    if isinstance(obj, str) and obj.startswith("{") and obj.endswith("}"):
        ref = obj[1:-1]
        if ref in key_map:
            return "{" + key_map[ref] + "}"
        for old_ns, new_ns in _DESIGN_MD_NAMESPACE_MAP.items():
            if ref == old_ns or ref.startswith(old_ns + "."):
                return "{" + new_ns + ref[len(old_ns) :] + "}"
        return obj
    return obj


def _load_design_md(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a DESIGN.md file into (nested_mapped_tokens, prose_body).

    Built on the house frontmatter helpers (`little_loops.frontmatter`) —
    no new YAML dependency, no bespoke parser. `nested_mapped_tokens` may
    legitimately be `{}` for a prose-only document (no frontmatter, or a
    frontmatter block containing only `components:`); that is a supported
    result, not an error — the caller constructs a token-empty
    `DesignTokens` that still carries `guidance`, not `None`.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter

    content = path.read_text()
    raw = parse_frontmatter(content)
    prose = strip_frontmatter(content)

    mapped, key_map = _map_design_md_namespaces(raw)
    mapped = _rewrite_design_md_aliases(mapped, key_map)
    return mapped, prose


def load_design_tokens(
    config: BRConfig,
    theme: str | None = None,
) -> DesignTokens | None:
    """Load and resolve design tokens from the project config.

    Returns None when design_tokens.enabled is False, the token path does
    not exist, or the active profile is missing (with a warning).
    Raises ValueError on circular or unknown token references.

    Token directory resolution (ENH-1768): the loader first looks for
    `<path>/<profiles_dir or "profiles">/<active>/`. If that profile
    directory doesn't exist but a sibling `profiles/` does, a warning is
    emitted and None is returned. Otherwise the loader falls back to the
    legacy flat `<path>/` layout for backward compatibility.
    """
    dt_cfg = config.design_tokens
    if not dt_cfg.enabled:
        return None

    source = getattr(dt_cfg, "source", "auto")
    base_path = config.project_root / dt_cfg.path

    def _load_profile(token_root: Path) -> DesignTokens:
        primitives = _load_json(token_root / dt_cfg.primitives_file)
        semantic = _load_json(token_root / dt_cfg.semantic_file)
        typography = _load_json(token_root / "typography.json")
        spacing = _load_json(token_root / "spacing.json")

        active_theme = theme or dt_cfg.active_theme
        theme_file = token_root / dt_cfg.themes_dir / f"{active_theme}.json"
        theme_data = _load_json(theme_file)

        primitives_flat = _flatten(primitives)
        # Layer order: semantic → typography → spacing → theme override.
        merged_flat: dict[str, Any] = {
            **_flatten(semantic),
            **_flatten(typography),
            **_flatten(spacing),
            **_flatten(theme_data),
        }
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
            source_path=token_root,
            guidance="",
            source="profile",
        )

    def _materialized_token_root() -> Path | None:
        """Silent `auto` probe: the token root, if it would yield >=1 token file.

        Deliberately stronger than "_resolve_token_root() is not None": an
        empty or leftover `.ll/design-tokens/` directory resolves to a real
        path (the legacy-flat fallback) but has no token files in it, and
        must not win over a root DESIGN.md (ENH-3264 AC 2b).
        """
        if not base_path.exists():
            return None
        token_root = _resolve_token_root(dt_cfg, base_path, quiet=True)
        if token_root is None:
            return None
        candidates = (
            dt_cfg.primitives_file,
            dt_cfg.semantic_file,
            "typography.json",
            "spacing.json",
        )
        if any((token_root / c).exists() for c in candidates):
            return token_root
        return None

    def _load_from_design_md(design_md_path: Path) -> DesignTokens:
        nested, prose = _load_design_md(design_md_path)
        flat = _flatten(nested)

        if theme is not None:
            sys.stderr.write(
                "[little-loops] Warning: design_tokens source is DESIGN.md, which "
                "has no theme mechanism; active_theme is ignored.\n"
            )

        if not flat:
            sys.stderr.write(
                f"[little-loops] Warning: '{design_md_path}' yielded no usable "
                "design tokens (empty/absent frontmatter, or only `components:`); "
                "using its prose guidance only.\n"
            )
            return DesignTokens(
                primitives={},
                semantic={},
                theme={},
                resolved={},
                source_path=design_md_path,
                guidance=prose,
                source="design_md",
            )

        try:
            resolved = _resolve_references(flat, {})
        except ValueError as exc:
            sys.stderr.write(
                f"[little-loops] Warning: {exc}; degrading '{design_md_path}' to "
                "no tokens (prose guidance is preserved).\n"
            )
            return DesignTokens(
                primitives={},
                semantic={},
                theme={},
                resolved={},
                source_path=design_md_path,
                guidance=prose,
                source="design_md",
            )

        return DesignTokens(
            primitives={},
            semantic=nested,
            theme={},
            resolved=resolved,
            source_path=design_md_path,
            guidance=prose,
            source="design_md",
        )

    if source == "profile":
        if not base_path.exists():
            return None
        token_root = _resolve_token_root(dt_cfg, base_path)
        if token_root is None:
            return None
        return _load_profile(token_root)

    if source == "design_md":
        design_md_path = _find_design_md(config.project_root)
        if design_md_path is None:
            sys.stderr.write(
                "[little-loops] Warning: design_tokens.source='design_md' but no "
                f"root {DESIGN_MD_FILENAME} was found; degrading to no tokens.\n"
            )
            return None
        return _load_from_design_md(design_md_path)

    # source == "auto": prefer a materialized profile; fall back to a root
    # DESIGN.md keyed on what's on disk, not on whether `active` is "set"
    # (it defaults to "default" in both the dataclass and from_dict, so
    # "unset" is not observable).
    token_root = _materialized_token_root()
    if token_root is not None:
        return _load_profile(token_root)

    # No materialized profile. Determine whether an explicit profile was
    # requested and is missing (warn accurately on fall-through) or nothing
    # was misconfigured (stay silent) — AC 2c.
    active_missing_warning: str | None = None
    active_root: Path | None = None
    if base_path.exists():
        profiles_subdir = dt_cfg.profiles_dir or "profiles"
        profiles_root = base_path / profiles_subdir
        active_root = profiles_root / dt_cfg.active
        if profiles_root.is_dir() and not active_root.is_dir():
            active_missing_warning = (
                f"[little-loops] Warning: design_tokens.active='{dt_cfg.active}' "
                f"not found; using root {DESIGN_MD_FILENAME} instead.\n"
            )

    design_md_path = _find_design_md(config.project_root)
    if design_md_path is None:
        if active_missing_warning is not None and active_root is not None:
            # Explicit profile requested and missing, and no DESIGN.md to
            # fall back to either: preserve today's exact degrade-to-None
            # warning (unchanged behavior for this sub-case).
            sys.stderr.write(
                f"[little-loops] Warning: design_tokens.active='{dt_cfg.active}' "
                f"but '{active_root}' does not exist; degrading to no tokens.\n"
            )
        return None

    if active_missing_warning is not None:
        sys.stderr.write(active_missing_warning)
    return _load_from_design_md(design_md_path)


def render_as_prompt_context(tokens: DesignTokens) -> str:
    """Return a compact markdown snippet listing resolved token values,
    grouped by semantic role with contrast guardrails.

    When semantic color tokens exist, raw primitives (color.*) are excluded
    and the output is grouped so the LLM knows which tokens are for surfaces,
    text, borders, and actions. Falls back to a flat sorted list when
    semantic tokens are absent (legacy profiles).
    """
    has_semantic_colors = (
        isinstance(tokens.semantic, dict)
        and "color" in tokens.semantic
        and isinstance(tokens.semantic["color"], dict)
        and any(k in tokens.semantic["color"] for k in ("surface", "text", "border", "action"))
    )

    if not has_semantic_colors:
        lines: list[str] = [
            "**Design tokens** (resolved values):",
            "",
            "Contrast guardrail: pair color.text.* tokens ON color.surface.* tokens. "
            "Never use a surface color for text, or a text color for backgrounds.",
            "",
            "```",
        ]
        for name, value in sorted(tokens.resolved.items()):
            if name.startswith("_"):
                continue
            lines.append(f"{name}: {value}")
        lines.append("```")
        return "\n".join(lines)

    surfaces: dict[str, str] = {}
    text_colors: dict[str, str] = {}
    border_colors: dict[str, str] = {}
    actions: dict[str, str] = {}
    typography: dict[str, str] = {}
    layout: dict[str, str] = {}
    residual: dict[str, str] = {}

    # Semantic color tokens are flattened as color.<role>.<name>.
    _SEMANTIC_ROLE_PREFIXES = {
        "color.surface.": surfaces,
        "color.text.": text_colors,
        "color.border.": border_colors,
        "color.action.": actions,
    }
    # Raw primitives to exclude (only semantic color tokens are shown).
    _PRIMITIVE_COLOR_PREFIXES = (
        "color.neutral.",
        "color.brand.",
        "color.accent.",
        "color.success.",
        "color.warning.",
        "color.danger.",
    )

    for name, value in sorted(tokens.resolved.items()):
        if name.startswith("_"):
            continue
        matched = False
        for prefix, bucket in _SEMANTIC_ROLE_PREFIXES.items():
            if name.startswith(prefix):
                bucket[name] = value
                matched = True
                break
        if matched:
            continue
        if name.startswith("font."):
            typography[name] = value
        elif any(name.startswith(p) for p in ("space.", "radius.", "shadow.", "border.width.")):
            layout[name] = value
        elif tokens.primitives and name.startswith(_PRIMITIVE_COLOR_PREFIXES):
            continue  # raw primitive — covered by semantic tokens above
        else:
            residual[name] = value

    lines = [
        "**Design tokens** (semantic — each token's role is noted; use the token name, not a raw hex value)",
        "",
        "Contrast guardrail: pair color.text.* tokens ON color.surface.* tokens. "
        "Never use a surface color for text, or a text color for backgrounds.",
        "",
    ]

    def _emit_group(heading: str, items: dict[str, str]) -> None:
        if not items:
            return
        lines.append(f"**{heading}**")
        lines.append("```")
        for n, v in items.items():
            lines.append(f"  {n}: {v}")
        lines.append("```")
        lines.append("")

    _emit_group("Surfaces (backgrounds)", surfaces)
    _emit_group("Text", text_colors)
    _emit_group("Borders", border_colors)
    _emit_group("Actions (buttons, links, interactive)", actions)
    _emit_group("Typography", typography)
    _emit_group("Layout (spacing, radii, shadows)", layout)
    _emit_group("Other", residual)

    return "\n".join(lines)


def render_as_css_vars(tokens: DesignTokens) -> str:
    """Return a CSS :root { ... } block declaring all resolved tokens as custom properties."""
    lines = [":root {"]
    for name, value in sorted(tokens.resolved.items()):
        css_name = "--" + name.replace(".", "-")
        lines.append(f"  {css_name}: {value};")
    lines.append("}")
    return "\n".join(lines)


def render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str:
    """Return two scoped CSS blocks (`:root` for light, `[data-theme=dark]` for dark)
    declaring all resolved tokens as custom properties, with all alias chains
    already resolved to concrete values.

    Metadata keys (names starting with `_`, e.g. `_wcag_spot_check`) are skipped
    so they do not leak into the stylesheet. Used by the FEAT-2301 HTML builder
    to inline a live light/dark toggle.
    """

    def _block(scope: str, tokens: DesignTokens) -> str:
        lines = [f"{scope} {{"]
        for name, value in sorted(tokens.resolved.items()):
            if name.startswith("_"):
                continue
            lines.append(f"  --{name.replace('.', '-')}: {value};")
        lines.append("}")
        return "\n".join(lines)

    return _block(":root", light) + "\n" + _block("[data-theme=dark]", dark)
