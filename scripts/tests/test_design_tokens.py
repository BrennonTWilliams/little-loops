"""Tests for scripts/little_loops/design_tokens.py (FEAT-1747)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.design_tokens import (
    DesignTokens,
    load_design_tokens,
    render_as_css_vars,
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
    theme_name: str = "light",
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
