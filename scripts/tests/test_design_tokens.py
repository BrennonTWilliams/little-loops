"""Tests for scripts/little_loops/design_tokens.py (FEAT-1747)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.design_tokens import (
    DesignTokens,
    load_design_tokens,
    render_as_css_vars,
    render_as_css_vars_themed,
    render_as_prompt_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tokens(
    base: Path,
    *,
    primitives: dict | None = None,
    semantic: dict | None = None,
    theme: dict | None = None,
    theme_name: str = "dark",
) -> Path:
    """Create a minimal token directory under *base* and return its path."""
    token_dir = base / ".ll" / "design-tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "primitives.json").write_text(json.dumps(primitives or {}))
    (token_dir / "semantic.json").write_text(json.dumps(semantic or {}))
    themes_dir = token_dir / "themes"
    themes_dir.mkdir(exist_ok=True)
    (themes_dir / f"{theme_name}.json").write_text(json.dumps(theme or {}))
    return token_dir


def _make_config(project_root: Path, extra: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {"design_tokens": {"enabled": True}}
    if extra:
        cfg["design_tokens"].update(extra)
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    return BRConfig(project_root)


# ---------------------------------------------------------------------------
# load_design_tokens
# ---------------------------------------------------------------------------


class TestLoadDesignTokensHappyPath:
    def test_returns_design_tokens_instance(self, tmp_path: Path) -> None:
        _write_tokens(tmp_path, primitives={"color": {"brand": {"500": "#4F46E5"}}})
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert isinstance(result, DesignTokens)

    def test_flat_resolution_no_references(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}}},
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.brand.500"] == "#4F46E5"

    def test_semantic_reference_resolved(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}}},
            semantic={"color": {"primary": "{color.brand.500}"}},
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.primary"] == "#4F46E5"

    def test_source_path_set(self, tmp_path: Path) -> None:
        token_dir = _write_tokens(tmp_path)
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.source_path == token_dir


class TestLoadDesignTokensDtcgFormat:
    """DTCG $value format support (ENH-1769)."""

    def test_flat_dtcg_leaf_value_extracted(self, tmp_path: Path) -> None:
        """DTCG-format tokens with $value keys flatten correctly."""
        _write_tokens(
            tmp_path,
            primitives={
                "typography": {
                    "fontFamily": {
                        "heading": {"$value": "Inter"},
                        "body": {"$value": "System UI"},
                    }
                }
            },
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["typography.fontFamily.heading"] == "Inter"
        assert result.resolved["typography.fontFamily.body"] == "System UI"

    def test_dtcg_metadata_siblings_ignored(self, tmp_path: Path) -> None:
        """DTCG $type, $description, and other $metadata are ignored during flattening."""
        _write_tokens(
            tmp_path,
            primitives={
                "color": {
                    "brand": {
                        "500": {
                            "$value": "#4F46E5",
                            "$type": "color",
                            "$description": "Primary brand color",
                        }
                    }
                }
            },
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.brand.500"] == "#4F46E5"
        # $type and $description must NOT appear as resolved keys
        assert "color.brand.500.$type" not in result.resolved
        assert "color.brand.500.$description" not in result.resolved

    def test_dtcg_reference_resolves(self, tmp_path: Path) -> None:
        """References resolve correctly when source uses DTCG format."""
        _write_tokens(
            tmp_path,
            primitives={
                "typography": {
                    "fontFamily": {
                        "heading": {"$value": "Inter"},
                    }
                }
            },
            semantic={"typography": {"heading": {"fontFamily": "{typography.fontFamily.heading}"}}},
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["typography.heading.fontFamily"] == "Inter"

    def test_mixed_dtcg_and_legacy(self, tmp_path: Path) -> None:
        """Mixed DTCG and legacy formats coexist correctly."""
        _write_tokens(
            tmp_path,
            primitives={
                "color": {"brand": {"500": "#4F46E5"}},  # legacy flat
                "space": {"sm": {"$value": "4px"}},  # DTCG
            },
            semantic={
                "color": {"primary": "{color.brand.500}"},
                "space": {"gap": "{space.sm}"},
            },
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.primary"] == "#4F46E5"
        assert result.resolved["space.gap"] == "4px"


class TestLoadDesignTokensThemeOverride:
    def test_theme_value_overrides_semantic(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}, "dark": {"500": "#1E1B4B"}}},
            semantic={"color": {"surface": "{color.brand.500}"}},
            theme={"color": {"surface": "{color.dark.500}"}},
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.surface"] == "#1E1B4B"

    def test_theme_parameter_overrides_active_theme(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}}},
            theme_name="light",
            theme={"color": {"bg": "#FFFFFF"}},
        )
        dark_themes = tmp_path / ".ll" / "design-tokens" / "themes"
        (dark_themes / "dark.json").write_text(json.dumps({"color": {"bg": "#000000"}}))

        config = _make_config(tmp_path)
        result = load_design_tokens(config, theme="dark")
        assert result is not None
        assert result.resolved["color.bg"] == "#000000"


class TestLoadDesignTokensFallbacks:
    def test_disabled_returns_none(self, tmp_path: Path) -> None:
        _write_tokens(tmp_path)
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": False}})
        )
        config = BRConfig(tmp_path)
        assert load_design_tokens(config) is None

    def test_missing_path_returns_none(self, tmp_path: Path) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": True}})
        )
        config = BRConfig(tmp_path)
        # default path .ll/design-tokens does not exist
        assert load_design_tokens(config) is None

    def test_missing_primitives_file_uses_empty_dict(self, tmp_path: Path) -> None:
        token_dir = tmp_path / ".ll" / "design-tokens"
        token_dir.mkdir(parents=True)
        (token_dir / "semantic.json").write_text(json.dumps({}))
        (token_dir / "themes").mkdir()
        (token_dir / "themes" / "light.json").write_text("{}")
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.primitives == {}


class TestLoadDesignTokensErrors:
    def test_unknown_reference_raises(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={},
            semantic={"color": {"primary": "{color.nonexistent}"}},
        )
        config = _make_config(tmp_path)
        with pytest.raises(ValueError, match="Unknown token reference"):
            load_design_tokens(config)

    def test_cycle_detection_raises(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={},
            semantic={
                "color": {
                    "a": "{color.b}",
                    "b": "{color.a}",
                }
            },
        )
        config = _make_config(tmp_path)
        with pytest.raises(ValueError, match="Circular token reference"):
            load_design_tokens(config)


# ---------------------------------------------------------------------------
# render_as_prompt_context
# ---------------------------------------------------------------------------


class TestRenderAsPromptContext:
    def test_returns_markdown_snippet(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}}},
        )
        config = _make_config(tmp_path)
        tokens = load_design_tokens(config)
        assert tokens is not None
        output = render_as_prompt_context(tokens)
        assert "**Design tokens**" in output
        assert "color.brand.500" in output
        assert "#4F46E5" in output
        assert "```" in output

    def test_output_shape_header_and_code_fence(self, tmp_path: Path) -> None:
        _write_tokens(tmp_path, primitives={"size": {"sm": "4px"}})
        config = _make_config(tmp_path)
        tokens = load_design_tokens(config)
        assert tokens is not None
        lines = render_as_prompt_context(tokens).splitlines()
        assert lines[0].startswith("**Design tokens**")
        assert lines[1] == "```"
        assert lines[-1] == "```"


# ---------------------------------------------------------------------------
# render_as_css_vars
# ---------------------------------------------------------------------------


class TestRenderAsCssVars:
    def test_returns_root_block(self, tmp_path: Path) -> None:
        _write_tokens(
            tmp_path,
            primitives={"color": {"brand": {"500": "#4F46E5"}}},
        )
        config = _make_config(tmp_path)
        tokens = load_design_tokens(config)
        assert tokens is not None
        output = render_as_css_vars(tokens)
        assert output.startswith(":root {")
        assert output.strip().endswith("}")
        assert "--color-brand-500: #4F46E5;" in output

    def test_dotted_names_become_dashed_css_props(self, tmp_path: Path) -> None:
        _write_tokens(tmp_path, primitives={"a": {"b": {"c": "1rem"}}})
        config = _make_config(tmp_path)
        tokens = load_design_tokens(config)
        assert tokens is not None
        assert "--a-b-c: 1rem;" in render_as_css_vars(tokens)


# ---------------------------------------------------------------------------
# render_as_css_vars_themed
# ---------------------------------------------------------------------------


class TestRenderAsCssVarsThemed:
    def _load_light_dark(
        self, tmp_path: Path
    ) -> tuple[DesignTokens, DesignTokens]:
        """Write light + dark theme files and load both, returning (light, dark)."""
        token_dir = _write_tokens(
            tmp_path,
            primitives={"color": {"light": {"500": "#FFFFFF"}, "dark": {"500": "#000000"}}},
            semantic={
                "color": {"bg": "{color.light.500}"},
                # Metadata key (starts with `_`) must NOT leak into the CSS output.
                "_note": "internal annotation",
            },
            theme_name="light",
            theme={"color": {"bg": "{color.light.500}"}},
        )
        (token_dir / "themes" / "dark.json").write_text(
            json.dumps({"color": {"bg": "{color.dark.500}"}})
        )
        config = _make_config(tmp_path)
        light = load_design_tokens(config, theme="light")
        dark = load_design_tokens(config, theme="dark")
        assert light is not None and dark is not None
        return light, dark

    def test_emits_both_scoped_blocks(self, tmp_path: Path) -> None:
        light, dark = self._load_light_dark(tmp_path)
        output = render_as_css_vars_themed(light, dark)
        assert ":root {" in output
        assert "[data-theme=dark] {" in output

    def test_values_resolved_to_concrete_hex(self, tmp_path: Path) -> None:
        light, dark = self._load_light_dark(tmp_path)
        output = render_as_css_vars_themed(light, dark)
        # No unresolved alias text should survive.
        assert "{color" not in output
        assert "--color-bg: #FFFFFF;" in output
        assert "--color-bg: #000000;" in output

    def test_light_and_dark_distinct_for_shared_token(self, tmp_path: Path) -> None:
        light, dark = self._load_light_dark(tmp_path)
        assert light.resolved["color.bg"] != dark.resolved["color.bg"]
        output = render_as_css_vars_themed(light, dark)
        root_block, dark_block = output.split("[data-theme=dark] {")
        assert "--color-bg: #FFFFFF;" in root_block
        assert "--color-bg: #000000;" in dark_block

    def test_metadata_keys_skipped(self, tmp_path: Path) -> None:
        light, dark = self._load_light_dark(tmp_path)
        # The metadata key is present in the resolved tokens...
        assert "_note" in light.resolved
        # ...but must be filtered out of the stylesheet.
        output = render_as_css_vars_themed(light, dark)
        assert "_note" not in output
        assert "--_" not in output


# ---------------------------------------------------------------------------
# Integration — actual template files
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIntegration:
    """Integration tests against the actual bundled `default` profile."""

    _TEMPLATE_DIR = (
        Path(__file__).parent.parent
        / "little_loops"
        / "templates"
        / "design-tokens"
        / "profiles"
        / "default"
    )

    def _skip_if_absent(self) -> None:
        if not self._TEMPLATE_DIR.exists():
            pytest.skip("templates/design-tokens/profiles/default/ not found")

    def test_all_four_files_exist(self) -> None:
        self._skip_if_absent()
        for rel in (
            "primitives.json",
            "semantic.json",
            "themes/light.json",
            "themes/dark.json",
        ):
            assert (self._TEMPLATE_DIR / rel).exists(), f"Missing {rel}"

    def test_all_four_files_parse_as_json(self) -> None:
        self._skip_if_absent()
        for rel in (
            "primitives.json",
            "semantic.json",
            "themes/light.json",
            "themes/dark.json",
        ):
            with open(self._TEMPLATE_DIR / rel) as fh:
                data = json.load(fh)
            assert isinstance(data, dict), f"{rel} root must be a JSON object"

    def _make_config_from_template(self, tmp_path: Path, theme: str):
        """Wire a config that points at the bundled default profile."""
        import shutil

        # Copy the whole templates/design-tokens/ tree so the profiles dir
        # structure carries over and the loader resolves profiles/default/.
        src_root = Path(__file__).parent.parent / "little_loops" / "templates" / "design-tokens"
        dest = tmp_path / ".ll" / "design-tokens"
        shutil.copytree(src_root, dest)
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "ll-config.json").write_text(json.dumps({"design_tokens": {"enabled": True}}))
        from little_loops.config.core import BRConfig

        return BRConfig(tmp_path), theme

    def test_round_trip_light_theme(self, tmp_path: Path) -> None:
        self._skip_if_absent()
        config, theme = self._make_config_from_template(tmp_path, "light")
        tokens = load_design_tokens(config, theme=theme)
        assert tokens is not None
        assert tokens.resolved.get("color.surface.primary") is not None

    def test_round_trip_dark_theme(self, tmp_path: Path) -> None:
        self._skip_if_absent()
        config, theme = self._make_config_from_template(tmp_path, "dark")
        tokens = load_design_tokens(config, theme=theme)
        assert tokens is not None
        # dark theme remaps surface.primary to neutral.950
        assert tokens.resolved.get("color.surface.primary") == "#101214"

    def test_dark_theme_completes_border_action_shadow(self, tmp_path: Path) -> None:
        """ENH-2308: default dark theme must override border/action/shadow with
        dark-tuned values, not fall through to light-tuned semantic defaults."""
        self._skip_if_absent()
        config, theme = self._make_config_from_template(tmp_path, "dark")
        tokens = load_design_tokens(config, theme=theme)
        assert tokens is not None
        r = tokens.resolved

        # Borders recede into the near-black surface (dark neutral steps), not the
        # light-tuned neutral.200/neutral.400 gridlines.
        assert r.get("color.border.subtle") == "#343a40"  # neutral.800
        assert r.get("color.border.strong") == "#868e96"  # neutral.600

        # Action accent brightens for dark; destructive must NOT collide with primary.
        assert r.get("color.action.primary") == "#3b82f6"  # brand.500
        assert r.get("color.action.destructive") != r.get("color.action.primary")

        # Theme-scoped shadow reads on near-black (high-alpha black, not light-tuned).
        assert "rgba(0, 0, 0, 0.5)" in r.get("shadow.md", "")
