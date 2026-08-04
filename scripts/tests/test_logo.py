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
        # The wordmark is letter-spaced ("l i t t l e   l o o p s"), so strip
        # whitespace before checking — a hardcoded contiguous substring is
        # exactly what d8b3a17d silently broke elsewhere (BUG-3025).
        compact = result.lower().replace(" ", "")
        assert "little" in compact or "loop" in compact or "ll" in compact, (
            "Logo content does not look like the expected CLI logo"
        )

    def test_full_logo_marker_is_non_empty(self) -> None:
        """Regression guard (BUG-3025): if the full-variant asset is ever
        emptied, a marker derived from its first line becomes "", and
        `assert marker in out`-style banner assertions would pass vacuously.
        """
        from little_loops.logo import get_logo

        marker = (get_logo("full") or "").strip().splitlines()[0]
        assert marker, "logo asset empty — banner assertions would pass vacuously"
