"""Tests for ll-verify-design-tokens — half-flipped design-token theme lint.

All fixtures are synthetic temp-dir profile trees (per ENH-2308) so pass/fail is
independent of the bundled-template state (notably the known-incomplete
``editorial-mono`` profile).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.verify_design_tokens import (
    _find_profiles_dir,
    lint_profile,
    lint_profiles_dir,
    main_verify_design_tokens,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

# A complete light-tuned semantic layer: the four color groups every inverting
# theme must override.
_SEMANTIC = {
    "color": {
        "surface": {"primary": "#ffffff"},
        "text": {"primary": "#000000"},
        "border": {"subtle": "#eeeeee", "strong": "#cccccc"},
        "action": {"primary": "#0000ff", "destructive": "#ff0000"},
    }
}

# Half-flipped: inverts surface+text but omits border+action.
_DARK_HALF_FLIPPED = {
    "color": {
        "surface": {"primary": "#000000"},
        "text": {"primary": "#ffffff"},
    }
}

# Complete dark theme: overrides every semantic color group.
_DARK_COMPLETE = {
    "color": {
        "surface": {"primary": "#000000"},
        "text": {"primary": "#ffffff"},
        "border": {"subtle": "#222222", "strong": "#444444"},
        "action": {"primary": "#66aaff", "destructive": "#ff6666"},
    }
}

# Light theme that only restates surface (does not invert) — must be exempt.
_LIGHT_SURFACE_ONLY = {"color": {"surface": {"primary": "#ffffff"}}}


def _make_profile(profiles_dir: Path, name: str, themes: dict[str, dict]) -> Path:
    """Create a profile dir with a semantic.json and the given themes/*.json."""
    profile = profiles_dir / name
    (profile / "themes").mkdir(parents=True)
    (profile / "semantic.json").write_text(json.dumps(_SEMANTIC))
    for theme_name, doc in themes.items():
        (profile / "themes" / f"{theme_name}.json").write_text(json.dumps(doc))
    return profile


def _profiles_root(tmp_path: Path) -> Path:
    root = tmp_path / "profiles"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# lint_profile
# ---------------------------------------------------------------------------


class TestLintProfile:
    def test_half_flipped_dark_is_flagged(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        profile = _make_profile(
            root, "warm", {"light": _LIGHT_SURFACE_ONLY, "dark": _DARK_HALF_FLIPPED}
        )
        result = lint_profile(profile)
        assert result.has_violations
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.theme == "dark"
        assert v.missing_groups == ["action", "border"]

    def test_complete_dark_passes(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        profile = _make_profile(root, "ok", {"light": _LIGHT_SURFACE_ONLY, "dark": _DARK_COMPLETE})
        result = lint_profile(profile)
        assert not result.has_violations

    def test_light_surface_only_theme_is_exempt(self, tmp_path: Path) -> None:
        """A non-inverting theme (surface only, no text) is not required to be complete."""
        root = _profiles_root(tmp_path)
        profile = _make_profile(root, "exempt", {"light": _LIGHT_SURFACE_ONLY})
        result = lint_profile(profile)
        assert not result.has_violations

    def test_profile_without_semantic_is_skipped(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        profile = root / "nosem"
        (profile / "themes").mkdir(parents=True)
        (profile / "themes" / "dark.json").write_text(json.dumps(_DARK_HALF_FLIPPED))
        result = lint_profile(profile)
        assert not result.has_violations

    def test_profile_without_themes_dir_is_skipped(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        profile = root / "nothemes"
        profile.mkdir()
        (profile / "semantic.json").write_text(json.dumps(_SEMANTIC))
        result = lint_profile(profile)
        assert not result.has_violations

    def test_theme_missing_only_action_is_flagged(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        partial = {
            "color": {
                "surface": {"primary": "#000"},
                "text": {"primary": "#fff"},
                "border": {"subtle": "#222"},
            }
        }
        profile = _make_profile(root, "partial", {"dark": partial})
        result = lint_profile(profile)
        assert result.violations[0].missing_groups == ["action"]


# ---------------------------------------------------------------------------
# lint_profiles_dir
# ---------------------------------------------------------------------------


class TestLintProfilesDir:
    def test_clean_dir_returns_empty(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        _make_profile(root, "a", {"light": _LIGHT_SURFACE_ONLY, "dark": _DARK_COMPLETE})
        _make_profile(root, "b", {"dark": _DARK_COMPLETE})
        assert lint_profiles_dir(root) == []

    def test_mixed_dir_reports_only_offenders(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        _make_profile(root, "good", {"dark": _DARK_COMPLETE})
        _make_profile(root, "bad", {"dark": _DARK_HALF_FLIPPED})
        results = lint_profiles_dir(root)
        assert len(results) == 1
        assert results[0].profile == "bad"


# ---------------------------------------------------------------------------
# _find_profiles_dir
# ---------------------------------------------------------------------------


class TestFindProfilesDir:
    def test_finds_user_project_layout(self, tmp_path: Path) -> None:
        target = tmp_path / ".ll" / "design-tokens" / "profiles"
        target.mkdir(parents=True)
        assert _find_profiles_dir(tmp_path) == target

    def test_finds_source_repo_layout(self, tmp_path: Path) -> None:
        target = tmp_path / "scripts" / "little_loops" / "templates" / "design-tokens" / "profiles"
        target.mkdir(parents=True)
        assert _find_profiles_dir(tmp_path) == target

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert _find_profiles_dir(tmp_path) is None


# ---------------------------------------------------------------------------
# main_verify_design_tokens (CLI entry point)
# ---------------------------------------------------------------------------


class TestMain:
    def test_clean_profiles_dir_returns_zero(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        _make_profile(root, "ok", {"dark": _DARK_COMPLETE})
        with (
            patch("sys.argv", ["ll-verify-design-tokens", "--profiles-dir", str(root)]),
            patch("builtins.print"),
        ):
            assert main_verify_design_tokens() == 0

    def test_half_flipped_returns_one(self, tmp_path: Path) -> None:
        root = _profiles_root(tmp_path)
        _make_profile(root, "bad", {"dark": _DARK_HALF_FLIPPED})
        with (
            patch("sys.argv", ["ll-verify-design-tokens", "--profiles-dir", str(root)]),
            patch("builtins.print"),
        ):
            assert main_verify_design_tokens() == 1

    def test_missing_profiles_dir_returns_one(self, tmp_path: Path) -> None:
        with (
            patch(
                "sys.argv",
                ["ll-verify-design-tokens", "-C", str(tmp_path / "nope")],
            ),
            patch("builtins.print"),
        ):
            assert main_verify_design_tokens() == 1

    def test_json_output_is_parseable(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        root = _profiles_root(tmp_path)
        _make_profile(root, "bad", {"dark": _DARK_HALF_FLIPPED})
        with patch(
            "sys.argv",
            ["ll-verify-design-tokens", "--profiles-dir", str(root), "--json"],
        ):
            ret = main_verify_design_tokens()
        data = json.loads(capsys.readouterr().out)
        assert ret == 1
        assert data["passed"] is False
        assert data["violations"][0]["profile"] == "bad"
        assert data["violations"][0]["missing_groups"] == ["action", "border"]

    def test_json_output_clean_passes(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        root = _profiles_root(tmp_path)
        _make_profile(root, "ok", {"dark": _DARK_COMPLETE})
        with patch(
            "sys.argv",
            ["ll-verify-design-tokens", "--profiles-dir", str(root), "--json"],
        ):
            ret = main_verify_design_tokens()
        data = json.loads(capsys.readouterr().out)
        assert ret == 0
        assert data["passed"] is True
        assert data["violations"] == []
