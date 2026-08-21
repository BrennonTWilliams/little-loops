"""Tests for `render_as_design_md` / `ll-artifact design-md export` (ENH-3268)."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.config.features import DesignTokensConfig
from little_loops.design_tokens import (
    DesignMdColorCollisionError,
    DesignTokens,
    _design_md_dropped_groups,
    _load_design_md,
    _load_profile_from_root,
    load_profile_tokens_from_root,
    render_as_design_md,
)

_BUILT_INS = ("default", "warm-paper", "editorial-mono")
_TEMPLATE_PROFILES_DIR = (
    Path(__file__).parent.parent / "little_loops" / "templates" / "design-tokens" / "profiles"
)


def _skip_if_absent() -> None:
    if not _TEMPLATE_PROFILES_DIR.exists():
        pytest.skip("templates/design-tokens/profiles/ not found")


def _load_built_in(name: str, theme: str = "light") -> DesignTokens:
    dt_cfg = DesignTokensConfig()
    root = _TEMPLATE_PROFILES_DIR / name
    return _load_profile_from_root(dt_cfg, root, theme)


def _reimport(document: str) -> tuple[dict, str]:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "DESIGN.md"
        path.write_text(document)
        return _load_design_md(path)


# ---------------------------------------------------------------------------
# AC 1/2 — round trip by value and by role, over every built-in
# ---------------------------------------------------------------------------


class TestColorRoundTrip:
    @pytest.mark.parametrize("profile", _BUILT_INS)
    def test_every_semantic_leaf_round_trips_by_value_and_role(self, profile: str) -> None:
        _skip_if_absent()
        tokens = _load_built_in(profile)
        document = render_as_design_md(tokens)
        mapped, _prose = _reimport(document)

        for role in ("surface", "text", "border", "action"):
            bucket = mapped.get("color", {}).get(role, {})
            for leaf in tokens.semantic["color"][role]:
                resolved_value = tokens.resolved[f"color.{role}.{leaf}"]
                assert resolved_value in bucket.values(), (
                    f"{profile}: color.{role}.{leaf}={resolved_value!r} missing from "
                    f"reimported role bucket {bucket!r}"
                )

    @pytest.mark.parametrize("profile", _BUILT_INS)
    def test_no_semantic_color_lands_in_residual_bucket(self, profile: str) -> None:
        """AC 2 — action.destructive is the leaf a naive role-name mapping drops."""
        _skip_if_absent()
        tokens = _load_built_in(profile)
        document = render_as_design_md(tokens)
        mapped, _prose = _reimport(document)
        extra_roles = set(mapped.get("color", {})) - {"surface", "text", "border", "action"}
        assert not extra_roles, f"{profile}: residual color roles: {extra_roles}"

    @pytest.mark.parametrize("profile", _BUILT_INS)
    def test_space_and_radius_round_trip_by_value(self, profile: str) -> None:
        _skip_if_absent()
        tokens = _load_built_in(profile)
        document = render_as_design_md(tokens)
        mapped, _prose = _reimport(document)
        for name, value in tokens.resolved.items():
            if name.startswith("space."):
                key = name[len("space.") :]
                assert mapped["space"][key] == value
            elif name.startswith("radius."):
                key = name[len("radius.") :]
                assert mapped["radius"][key] == value


# ---------------------------------------------------------------------------
# AC 3 — typography is shape-asserted
# ---------------------------------------------------------------------------


class TestTypographyShape:
    @pytest.mark.parametrize("profile", _BUILT_INS)
    def test_every_role_has_family_and_size(self, profile: str) -> None:
        _skip_if_absent()
        tokens = _load_built_in(profile)
        document = render_as_design_md(tokens)
        fm = yaml.safe_load(document.split("---\n")[1])
        expected_roles = {
            "display",
            "headline-lg",
            "headline-md",
            "title-lg",
            "body-lg",
            "body-md",
            "label-md",
            "label-sm",
        }
        assert set(fm["typography"]) == expected_roles
        for role in fm["typography"].values():
            assert "fontFamily" in role
            assert "fontSize" in role

    def test_truncated_size_scale_skips_role_and_reports_it(self, tmp_path: Path) -> None:
        """AC 16 — no built-in reaches the skip path; a synthetic fixture must."""
        primitives = _write_synthetic_profile(
            tmp_path,
            typography_size={"xs": "0.75rem", "sm": "0.875rem", "base": "1rem"},
        )
        tokens = _load_profile_from_root(DesignTokensConfig(), primitives, "light")
        typography = yaml.safe_load(render_as_design_md(tokens).split("---\n")[1])["typography"]
        # Only label-sm/label-md/body-md resolve (xs/sm/base); larger steps are absent.
        assert "display" not in typography
        assert "label-sm" in typography

        notes = _design_md_dropped_groups(tokens)
        assert any("display" in n for n in notes)


# ---------------------------------------------------------------------------
# AC 4 — primitives excluded structurally
# ---------------------------------------------------------------------------


class TestPrimitivesExcluded:
    def test_warm_paper_primitives_absent_from_export(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        document = render_as_design_md(tokens)
        fm = yaml.safe_load(document.split("---\n")[1])
        del fm["name"]  # the profile name legitimately contains "paper"
        dumped = json.dumps(fm)
        assert "paper" not in dumped
        assert "terracotta" not in dumped


# ---------------------------------------------------------------------------
# AC 5/6 — dropped-groups note
# ---------------------------------------------------------------------------


class TestDroppedGroupsNote:
    def test_shadow_and_border_width_reported(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        notes = _design_md_dropped_groups(tokens)
        assert "shadow" in notes
        assert "border.width" in notes

    def test_metadata_keys_absent_from_note_and_export(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        notes = _design_md_dropped_groups(tokens)
        joined = " ".join(notes)
        assert "_note" not in joined
        assert "_wcag_spot_check" not in joined
        assert "_note" not in render_as_design_md(tokens)

    def test_components_reported_only_for_design_md_source(self) -> None:
        profile_tokens = _load_built_in("warm-paper")
        assert not any("components" in n for n in _design_md_dropped_groups(profile_tokens))

        design_md_tokens = DesignTokens(
            primitives={},
            semantic={"color": {"surface": {"primary": "#fff"}}},
            theme={},
            resolved={"color.surface.primary": "#fff"},
            source_path=Path("/tmp/DESIGN.md"),
            guidance="prose",
            source="design_md",
        )
        assert any("components" in n for n in _design_md_dropped_groups(design_md_tokens))


# ---------------------------------------------------------------------------
# AC 7 — name + prose body
# ---------------------------------------------------------------------------


class TestNameAndProse:
    def test_name_key_present(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        fm = yaml.safe_load(render_as_design_md(tokens).split("---\n")[1])
        assert fm["name"] == "warm-paper"

    def test_design_md_source_round_trips_prose(self) -> None:
        tokens = DesignTokens(
            primitives={},
            semantic={"color": {"surface": {"primary": "#fff"}}},
            theme={},
            resolved={"color.surface.primary": "#fff"},
            source_path=Path("/tmp/some/DESIGN.md"),
            guidance="## Overview\n\nHand-authored prose.\n",
            source="design_md",
        )
        document = render_as_design_md(tokens)
        body = document.split("---\n", 2)[2]
        assert body.strip() == "## Overview\n\nHand-authored prose.".strip()

    def test_profile_source_emits_skeleton_when_guidance_empty(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        assert tokens.guidance == ""
        document = render_as_design_md(tokens)
        body = document.split("---\n", 2)[2]
        assert "## Overview" in body
        assert "## Colors" in body


# ---------------------------------------------------------------------------
# AC 12 — quoting/typing for a yaml.safe_load consumer
# ---------------------------------------------------------------------------


class TestQuotingAndTyping:
    def test_scalars_and_keys_survive_safe_load_as_strings(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        fm = yaml.safe_load(render_as_design_md(tokens).split("---\n")[1])
        for key, value in fm["rounded"].items():
            assert isinstance(key, str)
            assert isinstance(value, str)
        for key in fm["spacing"]:
            assert isinstance(key, str)
        for role in fm["typography"].values():
            assert isinstance(role["fontWeight"], str)

    def test_font_family_with_quotes_and_commas_round_trips_byte_identical(self) -> None:
        _skip_if_absent()
        tokens = _load_built_in("warm-paper")
        expected = tokens.resolved["font.family.body"]
        assert "'" in expected and "," in expected
        fm = yaml.safe_load(render_as_design_md(tokens).split("---\n")[1])
        assert fm["typography"]["body-md"]["fontFamily"] == expected


# ---------------------------------------------------------------------------
# AC 15 — collision guard
# ---------------------------------------------------------------------------


class TestColorCollision:
    def test_colliding_export_names_raise(self, tmp_path: Path) -> None:
        # "color.action.primary.hover" (nested) and "color.action.primary-hover"
        # (flat) both reduce to leaf "primary-hover" -> export "accent-primary-hover".
        semantic = {
            "color": {
                "surface": {"primary": "#111111"},
                "text": {"primary": "#222222"},
                "border": {"primary": "#333333"},
                "action": {
                    "primary": {"hover": "#444444"},
                    "primary-hover": "#555555",
                },
            }
        }
        root = _write_synthetic_profile(tmp_path, semantic=semantic)
        tokens = _load_profile_from_root(DesignTokensConfig(), root, "light")
        with pytest.raises(DesignMdColorCollisionError):
            render_as_design_md(tokens)


# ---------------------------------------------------------------------------
# Helpers for synthetic profiles
# ---------------------------------------------------------------------------


def _write_synthetic_profile(
    base: Path,
    *,
    semantic: dict | None = None,
    typography_size: dict | None = None,
) -> Path:
    root = base / "synthetic-profile"
    root.mkdir(parents=True, exist_ok=True)
    (root / "primitives.json").write_text(json.dumps({}))
    (root / "semantic.json").write_text(
        json.dumps(
            semantic
            or {
                "color": {
                    "surface": {"primary": "#fff"},
                    "text": {"primary": "#000"},
                    "border": {"primary": "#ccc"},
                    "action": {"primary": "#00f"},
                }
            }
        )
    )
    typography = {
        "font": {
            "family": {"body": "Body Sans", "heading": "Heading Sans"},
            "weight": {"normal": "400", "medium": "500", "semibold": "600", "bold": "700"},
            "size": typography_size
            or {
                "xs": "0.75rem",
                "sm": "0.875rem",
                "base": "1rem",
                "lg": "1.125rem",
                "xl": "1.25rem",
                "2xl": "1.5rem",
                "3xl": "1.875rem",
                "4xl": "2.25rem",
            },
            "line-height": {"tight": "1.1", "normal": "1.5", "relaxed": "1.7"},
        }
    }
    (root / "typography.json").write_text(json.dumps(typography))
    (root / "spacing.json").write_text(json.dumps({"space": {"0": "0"}, "radius": {"none": "0"}}))
    (root / "themes").mkdir(exist_ok=True)
    (root / "themes" / "light.json").write_text(json.dumps({}))
    return root


# ---------------------------------------------------------------------------
# CLI: cmd_design_md_export
# ---------------------------------------------------------------------------


def _make_config(project_root: Path, extra: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {"design_tokens": {"enabled": True}}
    if extra:
        cfg["design_tokens"].update(extra)
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    return BRConfig(project_root)


class TestCmdDesignMdExport:
    def test_none_token_load_exits_1_with_reason(self, tmp_path: Path, capsys) -> None:
        from little_loops.cli.artifact import cmd_design_md_export
        from little_loops.logger import Logger

        _make_config(tmp_path, {"enabled": False})
        args = argparse.Namespace(profile=None, theme=None, output=None)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_design_md_export(args, Logger(use_color=False, verbose=True))
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "design_tokens.enabled" in captured.err or "No design tokens" in captured.err

    def test_unresolvable_profile_exits_1(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact import cmd_design_md_export
        from little_loops.logger import Logger

        _make_config(tmp_path)
        args = argparse.Namespace(profile="does-not-exist", theme=None, output=None)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_design_md_export(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_packaged_built_in_profile_exports_to_stdout(self, tmp_path: Path, capsys) -> None:
        _skip_if_absent()
        from little_loops.cli.artifact import cmd_design_md_export
        from little_loops.logger import Logger

        _make_config(tmp_path)
        args = argparse.Namespace(profile="warm-paper", theme="light", output=None)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_design_md_export(args, Logger(use_color=False, verbose=True))
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out.startswith("---\n")
        assert "warm-paper" in captured.out
        assert "Warning: design-md export dropped" in captured.err
        assert "exported theme 'light'" in captured.err

    def test_output_file_gets_clean_document(self, tmp_path: Path, capsys) -> None:
        _skip_if_absent()
        from little_loops.cli.artifact import cmd_design_md_export
        from little_loops.logger import Logger

        _make_config(tmp_path)
        out_file = tmp_path / "out" / "DESIGN.md"
        args = argparse.Namespace(profile="warm-paper", theme="light", output=str(out_file))
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_design_md_export(args, Logger(use_color=False, verbose=True))
        assert code == 0
        assert out_file.read_text().startswith("---\n")
        captured = capsys.readouterr()
        assert "Warning: design-md export dropped" in captured.err


class TestArtifactCLIDispatchDesignMd:
    def test_design_md_export_dispatches(self) -> None:
        from little_loops.cli.artifact import main_artifact

        argv = ["ll-artifact", "design-md", "export", "--profile", "warm-paper"]
        with (
            patch("sys.argv", argv),
            patch("little_loops.cli.artifact.cmd_design_md_export", return_value=0) as handler,
        ):
            assert main_artifact() == 0
        assert handler.call_count == 1
        ns = handler.call_args.args[0]
        assert ns.profile == "warm-paper"


# ---------------------------------------------------------------------------
# load_profile_tokens_from_root
# ---------------------------------------------------------------------------


class TestLoadProfileTokensFromRoot:
    def test_loads_a_profile_directly_by_root(self, tmp_path: Path) -> None:
        root = _write_synthetic_profile(tmp_path)
        config = _make_config(tmp_path)
        tokens = load_profile_tokens_from_root(config, root, theme="light")
        assert tokens.source == "profile"
        assert tokens.resolved["color.surface.primary"] == "#fff"
