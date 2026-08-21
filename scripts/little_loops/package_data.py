"""Package data registry — declarative manifest of runtime-read assets.

Every file the little_loops package reads at runtime must appear in
PACKAGE_DATA_ASSETS. The completeness check (test_package_data_manifest.py)
asserts each entry is accessible via importlib.resources.files("little_loops"),
so adding a new asset read without registering it here will not be caught —
but registering it and omitting it from the package source will fail the test.

Usage in the completeness check::

    from little_loops.package_data import PACKAGE_DATA_ASSETS, list_missing_assets

    missing = list_missing_assets()
    assert not missing, f"Assets not accessible: {missing}"
"""

from __future__ import annotations

import importlib.resources
from typing import Final

_PACKAGE: Final[str] = "little_loops"

# Declarative manifest: each entry is a tuple of path parts relative to
# the little_loops package root. Add an entry here whenever new package
# data is referenced at runtime. Omitting an entry gives a false-green
# completeness result — the check won't catch a missing asset it doesn't know about.
PACKAGE_DATA_ASSETS: Final[tuple[tuple[str, ...], ...]] = (
    ("assets", "ll-cli-logo.txt"),
    ("assets", "ll-cli-logo-small.txt"),
    ("config-schema.json",),
    ("hooks", "prompts", "optimize-prompt-hook.md"),
    ("hooks", "adapters", "codex", "hooks.json"),
    ("templates", "bug-sections.json"),
    ("templates", "enh-sections.json"),
    ("templates", "feat-sections.json"),
    ("templates", "epic-sections.json"),
    ("templates", "ll-goals-template.md"),
    ("templates", "generic.json"),
    ("templates", "python-generic.json"),
    ("templates", "javascript.json"),
    ("templates", "typescript.json"),
    ("templates", "rust.json"),
    ("templates", "go.json"),
    ("templates", "java-maven.json"),
    ("templates", "java-gradle.json"),
    ("templates", "dotnet.json"),
    ("session_store", "schema_manifest.json"),
    # ENH-3268: `ll-artifact design-md export --profile <name>` resolves a
    # packaged built-in profile via importlib.resources when it is not
    # materialized in the project. Manifest hygiene, not a shipping fix —
    # hatchling already ships these files (pyproject.toml `packages =
    # ["little_loops"]`); registering them keeps this completeness check
    # from being false-green about profile JSON specifically.
    ("templates", "design-tokens", "profiles", "default", "primitives.json"),
    ("templates", "design-tokens", "profiles", "default", "semantic.json"),
    ("templates", "design-tokens", "profiles", "default", "typography.json"),
    ("templates", "design-tokens", "profiles", "default", "spacing.json"),
    ("templates", "design-tokens", "profiles", "default", "themes", "light.json"),
    ("templates", "design-tokens", "profiles", "default", "themes", "dark.json"),
    ("templates", "design-tokens", "profiles", "warm-paper", "primitives.json"),
    ("templates", "design-tokens", "profiles", "warm-paper", "semantic.json"),
    ("templates", "design-tokens", "profiles", "warm-paper", "typography.json"),
    ("templates", "design-tokens", "profiles", "warm-paper", "spacing.json"),
    ("templates", "design-tokens", "profiles", "warm-paper", "themes", "light.json"),
    ("templates", "design-tokens", "profiles", "warm-paper", "themes", "dark.json"),
    ("templates", "design-tokens", "profiles", "editorial-mono", "primitives.json"),
    ("templates", "design-tokens", "profiles", "editorial-mono", "semantic.json"),
    ("templates", "design-tokens", "profiles", "editorial-mono", "typography.json"),
    ("templates", "design-tokens", "profiles", "editorial-mono", "spacing.json"),
    ("templates", "design-tokens", "profiles", "editorial-mono", "themes", "light.json"),
    ("templates", "design-tokens", "profiles", "editorial-mono", "themes", "dark.json"),
)

# BUG-3177: skills/ is force-included into the wheel by hatch_build.py rather than
# physically relocated under little_loops/ (Option A′ — skills/ stays host-plugin
# glue at the repo root, per FEAT-2274/BUG-938). It is therefore NOT accessible via
# importlib.resources in an editable/dev install (this manifest's assumption for
# every PACKAGE_DATA_ASSETS entry above) and must not be added there — doing so
# breaks list_missing_assets() in every dev checkout. Coverage for "did the wheel
# actually ship skills/" lives in the wheel-smoke integration test instead
# (test_wheel_smoke.py::TestWheelSmoke::test_skills_force_include_accessible),
# which builds a real wheel rather than asserting against the editable source tree.


def check_asset_accessible(parts: tuple[str, ...]) -> bool:
    """Return True if the asset is reachable via importlib.resources."""
    try:
        traversable = importlib.resources.files(_PACKAGE)
        for part in parts:
            traversable = traversable.joinpath(part)
        return traversable.is_file()  # type: ignore[return-value]
    except Exception:
        return False


def list_missing_assets() -> list[tuple[str, ...]]:
    """Return registered assets not accessible in the current installation."""
    return [parts for parts in PACKAGE_DATA_ASSETS if not check_asset_accessible(parts)]
