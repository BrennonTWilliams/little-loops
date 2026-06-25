"""Tests for CLI logo asset resolution (BUG-2276).

Validates that ll-cli-logo.txt is bundled inside the package and that
get_logo() resolves it correctly from the in-package path.
"""

from __future__ import annotations

from pathlib import Path

LOGO_PATH = Path(__file__).parent.parent / "little_loops" / "assets" / "ll-cli-logo.txt"


class TestLogoAssetResolution:
    def test_logo_asset_exists_in_package(self) -> None:
        assert LOGO_PATH.exists(), f"Logo asset not found in package: {LOGO_PATH}"

    def test_get_logo_returns_non_none(self) -> None:
        from little_loops.logo import get_logo

        result = get_logo()
        assert result is not None, "get_logo() returned None — path fix not applied"

    def test_get_logo_returns_logo_content(self) -> None:
        from little_loops.logo import get_logo

        result = get_logo()
        assert result is not None
        assert len(result) > 0, "get_logo() returned empty string"
        assert "little" in result.lower() or "loop" in result.lower() or "ll" in result.lower(), (
            "Logo content does not look like the expected CLI logo"
        )
