"""Shared artifact template kit (ENH-3035).

Single home for the parts of an artifact template that are genuinely
artifact-agnostic: design-token stamping, and the page-shell placeholders
every design-token-aware template shares. Extracted from `policy-builder`
(FEAT-2301), the first consumer, so the sql.js dashboard (FEAT-3304) and
future artifact templates build on one convention instead of each copying
and drifting from `policy-builder`.

Artifact-specific stamping (grammar JSON, skill catalogs, inlined core JS,
...) stays with its owning template; only the shell/token-stamping parts
common across templates belong here.
"""

from __future__ import annotations


def themed_css_vars(config: object) -> str:
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
    from little_loops.design_tokens import (
        DesignTokens,
        load_design_tokens,
        render_as_css_vars_themed,
    )

    dark: DesignTokens | None
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


def stamp_page_shell(template_text: str, *, active_theme: str, css_vars: str) -> str:
    """Stamp the shared page-shell placeholders into *template_text*.

    Handles the two stamping points common to every design-token-aware
    artifact template: the root `data-theme` attribute and the
    `/*__THEMED_CSS_VARS__*/` CSS placeholder. Artifact-specific placeholders
    (grammar JSON, skill catalogs, inlined core JS, ...) are stamped by the
    caller after this.

    A *template_text* that carries neither placeholder (e.g. a
    `ll-artifact templatize`-produced body whose token values were baked in
    as literals rather than authored with stamp points) is accepted
    unchanged — `str.replace` with no match is a no-op, not an error. This
    is the narrow reading of the templatize-reachability AC (ENH-3035
    Decisions, 2026-08-25): the stamping unit must not require a body
    authored with stamp points, not that baked-in literals get rewritten.
    """
    html = template_text.replace('data-theme="light"', f'data-theme="{active_theme}"', 1)
    html = html.replace("/*__THEMED_CSS_VARS__*/", css_vars)
    return html
