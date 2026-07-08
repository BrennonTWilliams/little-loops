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
)


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
