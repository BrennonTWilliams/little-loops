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

import yaml

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


def _load_profile_from_root(dt_cfg: Any, token_root: Path, theme: str | None) -> DesignTokens:
    """Load a profile's `DesignTokens` from an already-resolved *token_root*.

    Shared by `load_design_tokens`'s project-config path and
    `load_profile_tokens_from_root` (ENH-3268), which resolves *token_root*
    from an explicit `--profile` name (project profile or packaged built-in)
    instead of the project's configured active profile.
    """
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


def load_profile_tokens_from_root(
    config: BRConfig, token_root: Path, theme: str | None = None
) -> DesignTokens:
    """Load a profile's `DesignTokens` from an explicit *token_root* directory,
    bypassing the project's configured active-profile resolution.

    Used by `ll-artifact design-md export --profile <name>` (ENH-3268), whose
    named profile may be a packaged built-in never materialized in the
    project (see `cli/artifact.py::_resolve_export_profile_root`).
    """
    return _load_profile_from_root(config.design_tokens, token_root, theme)


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

    source = dt_cfg.source
    base_path = config.project_root / dt_cfg.path

    def _load_profile(token_root: Path) -> DesignTokens:
        return _load_profile_from_root(dt_cfg, token_root, theme)

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


# ---------------------------------------------------------------------------
# DESIGN.md export (ENH-3268)
# ---------------------------------------------------------------------------

_DESIGN_MD_SEMANTIC_ROLES = ("surface", "text", "border", "action")

# Prose skeleton emitted when tokens.guidance is empty (a profile source has
# no prose body to round-trip). Headings match the vendored spec fixture.
_DESIGN_MD_SKELETON_SECTIONS = (
    "Overview",
    "Colors",
    "Typography",
    "Layout",
    "Elevation & Depth",
    "Shapes",
    "Components",
    "Do's and Don'ts",
)

# Pinned typography role table: (role name, font.size step, font.family key,
# font.line-height step, font.weight step). See ENH-3268 Program Design —
# this table is not derivable from the profiles; it is a design decision.
_DESIGN_MD_TYPOGRAPHY_ROLES: tuple[tuple[str, str, str, str, str], ...] = (
    ("display", "4xl", "heading", "tight", "bold"),
    ("headline-lg", "3xl", "heading", "tight", "bold"),
    ("headline-md", "2xl", "heading", "tight", "semibold"),
    ("title-lg", "xl", "heading", "tight", "semibold"),
    ("body-lg", "lg", "body", "relaxed", "normal"),
    ("body-md", "base", "body", "normal", "normal"),
    ("label-md", "sm", "body", "normal", "medium"),
    ("label-sm", "xs", "body", "normal", "medium"),
)

# Token groups with no home in the DESIGN.md spec frontmatter — always dropped.
_DESIGN_MD_UNSUPPORTED_PREFIXES = ("shadow.", "border.width.")


class DesignMdColorCollisionError(ValueError):
    """Two semantic color leaves exported to the same flat `colors:` name."""


def _export_color_name(role: str, leaf: str) -> str:
    """Map a semantic color leaf onto a DESIGN.md color name that
    `_classify_design_md_color_role` re-derives back into *role* on import.

    Generic per-role rule, not a per-leaf allowlist — see ENH-3268 "The key
    mapping must be classifier-aware".
    """
    if role == "surface":
        return "surface" if leaf == "primary" else f"surface-{leaf}"
    if role == "text":
        if leaf == "primary":
            return "on-surface"
        if leaf == "inverse":
            return "inverse-on-surface"
        return f"on-surface-{leaf}"
    if role == "border":
        return "outline" if leaf == "primary" else f"outline-{leaf}"
    if role == "action":
        return "primary" if leaf == "primary" else f"accent-{leaf}"
    raise ValueError(f"Unknown semantic color role: {role}")  # pragma: no cover - guarded by caller


def _export_colors(tokens: DesignTokens, primitive_keys: set[str]) -> dict[str, str]:
    colors: dict[str, str] = {}
    origin: dict[str, str] = {}
    for name, value in sorted(tokens.resolved.items()):
        if name in primitive_keys or name.startswith("_"):
            continue
        parts = name.split(".")
        if len(parts) < 3 or parts[0] != "color" or parts[1] not in _DESIGN_MD_SEMANTIC_ROLES:
            continue
        role = parts[1]
        leaf = "-".join(parts[2:])
        export_name = _export_color_name(role, leaf)
        if export_name in colors and origin[export_name] != name:
            raise DesignMdColorCollisionError(
                f"colors.{export_name}: '{origin[export_name]}' and '{name}' both "
                "export to this name"
            )
        colors[export_name] = value
        origin[export_name] = name
    return colors


def _export_typography(tokens: DesignTokens) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Synthesize the spec's role-organized `typography:` block per the
    pinned role table. Returns (typography_block, skipped_role_names).
    """
    typography: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for role_name, size_step, family_key, lh_step, weight_step in _DESIGN_MD_TYPOGRAPHY_ROLES:
        size = tokens.resolved.get(f"font.size.{size_step}")
        family = tokens.resolved.get(f"font.family.{family_key}")
        if size is None or family is None:
            skipped.append(role_name)
            continue
        role: dict[str, str] = {"fontFamily": family, "fontSize": size}
        line_height = tokens.resolved.get(f"font.line-height.{lh_step}")
        if line_height is not None:
            role["lineHeight"] = line_height
        weight = tokens.resolved.get(f"font.weight.{weight_step}")
        if weight is not None:
            role["fontWeight"] = weight
        typography[role_name] = role
    return typography, skipped


def _unused_typography_axes(tokens: DesignTokens) -> list[str]:
    """Font axis values the pinned role table never reads, named in the
    dropped-groups note: the whole `letter-spacing` axis, plus any
    size/family/line-height/weight step no role in the table consumes.
    """
    used_size_steps = {row[1] for row in _DESIGN_MD_TYPOGRAPHY_ROLES}
    used_family_keys = {row[2] for row in _DESIGN_MD_TYPOGRAPHY_ROLES}
    used_lh_steps = {row[3] for row in _DESIGN_MD_TYPOGRAPHY_ROLES}
    used_weight_steps = {row[4] for row in _DESIGN_MD_TYPOGRAPHY_ROLES}

    unused: list[str] = []
    for name in sorted(tokens.resolved):
        if name.startswith("font.letter-spacing."):
            unused.append(name)
        elif name.startswith("font.size.") and name.split(".")[2] not in used_size_steps:
            unused.append(name)
        elif name.startswith("font.family.") and name.split(".")[2] not in used_family_keys:
            unused.append(name)
        elif name.startswith("font.line-height.") and name.split(".")[2] not in used_lh_steps:
            unused.append(name)
        elif name.startswith("font.weight.") and name.split(".")[2] not in used_weight_steps:
            unused.append(name)
    return unused


def _export_spacing_and_rounded(
    tokens: DesignTokens, primitive_keys: set[str]
) -> tuple[dict[str, str], dict[str, str]]:
    """`space.*` -> flat `spacing:` (emitted verbatim, numeric scale — see
    ENH-3268 "spacing deliberately does not follow the typography ruling"),
    `radius.*` -> flat `rounded:`.
    """
    spacing: dict[str, str] = {}
    rounded: dict[str, str] = {}
    for name, value in sorted(tokens.resolved.items()):
        if name in primitive_keys or name.startswith("_"):
            continue
        if name.startswith("space."):
            spacing[name[len("space.") :]] = value
        elif name.startswith("radius."):
            rounded[name[len("radius.") :]] = value
    return spacing, rounded


def _design_md_dropped_groups(tokens: DesignTokens) -> list[str]:
    """Pure computation of every dropped-group note line (ENH-3268 AC 5/6),
    excluding the dropped-theme note.

    `render_as_design_md` matches the other `render_as_*` renderers' shape
    (`DesignTokens` in, `str` out, no I/O), so it cannot itself write the
    stderr note. This function is the shared source of truth the CLI layer
    (the only caller with I/O) calls to build that note. It also excludes
    the dropped-theme note: that requires listing sibling theme files on
    disk, which is outside what a single `DesignTokens` can see.
    """
    notes: list[str] = []
    for prefix in _DESIGN_MD_UNSUPPORTED_PREFIXES:
        if any(name.startswith(prefix) for name in tokens.resolved):
            notes.append(prefix.rstrip("."))

    _typography, skipped_roles = _export_typography(tokens)
    if skipped_roles:
        notes.append(f"typography roles (missing size/family): {', '.join(skipped_roles)}")
    unused_axes = _unused_typography_axes(tokens)
    if unused_axes:
        notes.append(f"typography axes not used by the role table: {', '.join(unused_axes)}")

    if tokens.source == "design_md":
        notes.append("components (dropped on import; nothing to re-export)")

    return notes


def _design_md_skeleton() -> str:
    return "\n\n".join(f"## {section}" for section in _DESIGN_MD_SKELETON_SECTIONS) + "\n"


def render_as_design_md(tokens: DesignTokens) -> str:
    """Render *tokens* as a single-theme DESIGN.md document (ENH-3268).

    Lossy by construction: the spec has no theme mechanism and no home for
    several token groups little-loops profiles carry. Raw primitives are
    excluded structurally (any key in `_flatten(tokens.primitives)`), colors
    are exported under classifier-recognized names so a re-import recovers
    the original role, and typography is synthesized into the spec's
    role-organized shape per the pinned role table — see
    `_design_md_dropped_groups` for what does not survive.

    Raises `DesignMdColorCollisionError` if two semantic leaves would export
    to the same flat `colors:` name.
    """
    primitive_keys = set(_flatten(tokens.primitives))

    frontmatter: dict[str, Any] = {
        "name": tokens.source_path.stem if tokens.source == "design_md" else tokens.source_path.name
    }

    colors = _export_colors(tokens, primitive_keys)
    if colors:
        frontmatter["colors"] = colors

    typography, _skipped = _export_typography(tokens)
    if typography:
        frontmatter["typography"] = typography

    spacing, rounded = _export_spacing_and_rounded(tokens, primitive_keys)
    if rounded:
        frontmatter["rounded"] = rounded
    if spacing:
        frontmatter["spacing"] = spacing

    yaml_block = yaml.dump(frontmatter, default_style='"', sort_keys=False, allow_unicode=True)
    body = tokens.guidance if tokens.guidance else _design_md_skeleton()
    return f"---\n{yaml_block}---\n\n{body}"
