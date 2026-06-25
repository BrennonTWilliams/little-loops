"""Manifest completeness check — verifies all declared assets are accessible.

Asserts every entry in PACKAGE_DATA_ASSETS is reachable via importlib.resources
in the current installation (editable or non-editable). A missing asset here
means either the file was not committed to scripts/little_loops/ or hatchling's
wheel include rule was changed to exclude it.
"""

from __future__ import annotations

import pytest

from little_loops.package_data import (
    PACKAGE_DATA_ASSETS,
    check_asset_accessible,
    list_missing_assets,
)


class TestPackageDataManifest:
    """Every registered asset must be accessible in the current install."""

    def test_no_missing_assets(self) -> None:
        """High-level: list_missing_assets() returns empty in dev install."""
        missing = list_missing_assets()
        assert not missing, (
            f"Assets registered in PACKAGE_DATA_ASSETS but NOT accessible "
            f"via importlib.resources: {missing}"
        )

    @pytest.mark.parametrize("parts", list(PACKAGE_DATA_ASSETS), ids=["/".join(p) for p in PACKAGE_DATA_ASSETS])
    def test_individual_asset_accessible(self, parts: tuple[str, ...]) -> None:
        """Each registered asset is individually accessible."""
        assert check_asset_accessible(parts), (
            f"Asset not accessible: little_loops/{'/'.join(parts)}"
        )

    def test_registry_is_non_empty(self) -> None:
        """Sanity: the registry must declare at least one asset."""
        assert len(PACKAGE_DATA_ASSETS) > 0

    def test_all_entries_are_tuples_of_strings(self) -> None:
        """Registry entries must be tuples of non-empty strings."""
        for parts in PACKAGE_DATA_ASSETS:
            assert isinstance(parts, tuple)
            assert all(isinstance(p, str) and p for p in parts)

    def test_no_duplicate_entries(self) -> None:
        """Registry must not contain duplicate asset paths."""
        seen: set[tuple[str, ...]] = set()
        for parts in PACKAGE_DATA_ASSETS:
            assert parts not in seen, f"Duplicate asset in registry: {parts}"
            seen.add(parts)
