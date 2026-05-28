"""Tests for ENH-1768: multi-profile design-tokens system.

Covers:
- profile resolution under `<path>/profiles/<active>/`
- legacy flat-layout fallback (existing projects pre-ENH-1768)
- missing-profile fallback (warn + degrade to None)
- switching `active` changes resolved output
- typography + spacing layer loads alongside color tokens
- bundled templates ship 3 profiles, each with the full layer
- init/configure wiring references `active` and profiles
"""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.design_tokens import load_design_tokens

PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates" / "design-tokens"
PROFILES_TEMPLATE_DIR = TEMPLATES_DIR / "profiles"

PROFILE_NAMES = ("default", "editorial-mono", "warm-paper")
PROFILE_LAYER_FILES = (
    "primitives.json",
    "semantic.json",
    "typography.json",
    "spacing.json",
    "themes/light.json",
    "themes/dark.json",
)


def _write_profile(
    base: Path,
    name: str,
    *,
    primitives: dict | None = None,
    semantic: dict | None = None,
    typography: dict | None = None,
    spacing: dict | None = None,
    themes: dict[str, dict] | None = None,
) -> Path:
    """Write a profile directory under `<base>/.ll/design-tokens/profiles/<name>/`."""
    profile_dir = base / ".ll" / "design-tokens" / "profiles" / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "primitives.json").write_text(json.dumps(primitives or {}))
    (profile_dir / "semantic.json").write_text(json.dumps(semantic or {}))
    if typography is not None:
        (profile_dir / "typography.json").write_text(json.dumps(typography))
    if spacing is not None:
        (profile_dir / "spacing.json").write_text(json.dumps(spacing))
    themes_dir = profile_dir / "themes"
    themes_dir.mkdir(exist_ok=True)
    for theme_name, theme_data in (themes or {"light": {}}).items():
        (themes_dir / f"{theme_name}.json").write_text(json.dumps(theme_data))
    return profile_dir


def _make_config(project_root: Path, dt_overrides: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {"design_tokens": {"enabled": True}}
    if dt_overrides:
        cfg["design_tokens"].update(dt_overrides)
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    return BRConfig(project_root)


# ---------------------------------------------------------------------------
# Config schema + dataclass
# ---------------------------------------------------------------------------


class TestDesignTokensConfigProfileFields:
    """`DesignTokensConfig` has `active` and `profiles_dir` fields."""

    def test_active_default_is_default(self) -> None:
        from little_loops.config.features import DesignTokensConfig

        config = DesignTokensConfig.from_dict({})
        assert config.active == "default"

    def test_profiles_dir_default_is_none(self) -> None:
        from little_loops.config.features import DesignTokensConfig

        config = DesignTokensConfig.from_dict({})
        assert config.profiles_dir is None

    def test_active_loaded_from_dict(self) -> None:
        from little_loops.config.features import DesignTokensConfig

        config = DesignTokensConfig.from_dict({"active": "warm-paper"})
        assert config.active == "warm-paper"

    def test_profiles_dir_loaded_from_dict(self) -> None:
        from little_loops.config.features import DesignTokensConfig

        config = DesignTokensConfig.from_dict({"profiles_dir": "my-profiles"})
        assert config.profiles_dir == "my-profiles"


class TestBRConfigDesignTokensProfileRoundTrip:
    """BRConfig exposes `active`/`profiles_dir` via property + `to_dict()`."""

    def test_active_round_trip(self, tmp_path: Path) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": True, "active": "editorial-mono"}})
        )
        config = BRConfig(tmp_path)
        assert config.design_tokens.active == "editorial-mono"
        d = config.to_dict()
        assert d["design_tokens"]["active"] == "editorial-mono"

    def test_profiles_dir_round_trip(self, tmp_path: Path) -> None:
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": True, "profiles_dir": "themes"}})
        )
        config = BRConfig(tmp_path)
        assert config.design_tokens.profiles_dir == "themes"
        d = config.to_dict()
        assert d["design_tokens"]["profiles_dir"] == "themes"


# ---------------------------------------------------------------------------
# Loader: profile resolution
# ---------------------------------------------------------------------------


class TestProfileResolution:
    """Loader resolves from `<path>/profiles/<active>/` first."""

    def test_default_profile_resolved(self, tmp_path: Path) -> None:
        _write_profile(
            tmp_path,
            "default",
            primitives={"color": {"brand": {"500": "#3b82f6"}}},
            semantic={"color": {"primary": "{color.brand.500}"}},
        )
        config = _make_config(tmp_path)  # active defaults to "default"
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.primary"] == "#3b82f6"

    def test_active_profile_switch_changes_output(self, tmp_path: Path) -> None:
        _write_profile(
            tmp_path,
            "default",
            primitives={"color": {"brand": {"500": "#3b82f6"}}},
            semantic={"color": {"primary": "{color.brand.500}"}},
        )
        _write_profile(
            tmp_path,
            "warm-paper",
            primitives={"color": {"brand": {"500": "#c2410c"}}},
            semantic={"color": {"primary": "{color.brand.500}"}},
        )
        config = _make_config(tmp_path, {"active": "warm-paper"})
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.primary"] == "#c2410c"

    def test_source_path_points_at_profile_dir(self, tmp_path: Path) -> None:
        profile_dir = _write_profile(tmp_path, "default", primitives={"a": "1"})
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.source_path == profile_dir


class TestProfileTypographyAndSpacing:
    """Loader merges typography + spacing into resolved tokens."""

    def test_typography_layer_loaded(self, tmp_path: Path) -> None:
        _write_profile(
            tmp_path,
            "default",
            primitives={"font": {"sans": "Inter, sans-serif"}},
            typography={"font": {"body": "{font.sans}"}},
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["font.body"] == "Inter, sans-serif"

    def test_spacing_layer_loaded(self, tmp_path: Path) -> None:
        _write_profile(
            tmp_path,
            "default",
            primitives={"size": {"4": "1rem"}},
            spacing={"space": {"md": "{size.4}"}},
        )
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["space.md"] == "1rem"


# ---------------------------------------------------------------------------
# Loader: fallbacks
# ---------------------------------------------------------------------------


class TestLegacyFlatLayoutFallback:
    """Existing projects on FEAT-1746/1747 (flat layout) keep working."""

    def test_legacy_flat_layout_resolves(self, tmp_path: Path) -> None:
        # No profiles/ dir; primitives.json at the flat top level
        token_dir = tmp_path / ".ll" / "design-tokens"
        token_dir.mkdir(parents=True)
        (token_dir / "primitives.json").write_text(
            json.dumps({"color": {"brand": {"500": "#legacy"}}})
        )
        (token_dir / "semantic.json").write_text(
            json.dumps({"color": {"primary": "{color.brand.500}"}})
        )
        (token_dir / "themes").mkdir()
        (token_dir / "themes" / "light.json").write_text("{}")
        config = _make_config(tmp_path)
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved["color.primary"] == "#legacy"


class TestMissingProfileFallback:
    """Missing active profile must NOT crash; degrades to None."""

    def test_missing_profile_returns_none(self, tmp_path: Path) -> None:
        # profiles/ exists but the active profile dir doesn't
        _write_profile(tmp_path, "default")
        config = _make_config(tmp_path, {"active": "nonexistent"})
        result = load_design_tokens(config)
        assert result is None

    def test_completely_absent_path_returns_none(self, tmp_path: Path) -> None:
        # Config enabled, but no design-tokens dir at all
        from little_loops.config.core import BRConfig

        (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": True}})
        )
        config = BRConfig(tmp_path)
        assert load_design_tokens(config) is None


# ---------------------------------------------------------------------------
# Bundled templates: 3 profiles, full layer
# ---------------------------------------------------------------------------


class TestBundledProfileTemplates:
    """`templates/design-tokens/profiles/` ships 3 profiles with the full layer."""

    def test_profiles_dir_exists(self) -> None:
        assert PROFILES_TEMPLATE_DIR.is_dir(), (
            f"{PROFILES_TEMPLATE_DIR} must exist after ENH-1768 restructure"
        )

    def test_three_profiles_shipped(self) -> None:
        installed = {p.name for p in PROFILES_TEMPLATE_DIR.iterdir() if p.is_dir()}
        for name in PROFILE_NAMES:
            assert name in installed, f"Profile '{name}' must ship in templates"

    def test_each_profile_has_full_layer(self) -> None:
        for name in PROFILE_NAMES:
            profile = PROFILES_TEMPLATE_DIR / name
            for rel in PROFILE_LAYER_FILES:
                assert (profile / rel).exists(), (
                    f"Profile '{name}' missing required layer file: {rel}"
                )

    def test_each_profile_parses_as_json(self) -> None:
        for name in PROFILE_NAMES:
            profile = PROFILES_TEMPLATE_DIR / name
            for rel in PROFILE_LAYER_FILES:
                with open(profile / rel) as fh:
                    json.load(fh)  # raises if not valid JSON


class TestBundledProfilesLoadEndToEnd:
    """Every shipped profile can be loaded by the runtime loader."""

    def _copy_templates(self, tmp_path: Path) -> None:
        import shutil

        dest = tmp_path / ".ll" / "design-tokens"
        shutil.copytree(TEMPLATES_DIR, dest)

    def _make_config(self, tmp_path: Path, active: str):
        from little_loops.config.core import BRConfig

        config_dir = tmp_path / ".ll"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "ll-config.json").write_text(
            json.dumps({"design_tokens": {"enabled": True, "active": active}})
        )
        return BRConfig(tmp_path)

    def test_default_profile_loads(self, tmp_path: Path) -> None:
        self._copy_templates(tmp_path)
        config = self._make_config(tmp_path, "default")
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved.get("color.surface.primary") is not None

    def test_editorial_mono_loads(self, tmp_path: Path) -> None:
        self._copy_templates(tmp_path)
        config = self._make_config(tmp_path, "editorial-mono")
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved.get("color.surface.primary") is not None

    def test_warm_paper_loads(self, tmp_path: Path) -> None:
        self._copy_templates(tmp_path)
        config = self._make_config(tmp_path, "warm-paper")
        result = load_design_tokens(config)
        assert result is not None
        assert result.resolved.get("color.surface.primary") is not None

    def test_profile_outputs_diverge(self, tmp_path: Path) -> None:
        """Different active profiles produce visually distinct token output."""
        self._copy_templates(tmp_path)
        action_colors: dict[str, str] = {}
        body_fonts: dict[str, str] = {}
        for name in PROFILE_NAMES:
            config = self._make_config(tmp_path, name)
            result = load_design_tokens(config)
            assert result is not None
            action_colors[name] = result.resolved["color.action.primary"]
            body_fonts[name] = result.resolved["font.family.body"]

        # Each profile's action.primary (the most visible brand color) is distinct.
        assert len(set(action_colors.values())) == len(PROFILE_NAMES), (
            f"action.primary must differ across profiles, got {action_colors}"
        )
        # Each profile's body font also differs (typography is part of the profile).
        assert len(set(body_fonts.values())) == len(PROFILE_NAMES), (
            f"font.family.body must differ across profiles, got {body_fonts}"
        )


# ---------------------------------------------------------------------------
# Schema + config-schema.json
# ---------------------------------------------------------------------------


class TestConfigSchemaProfileFields:
    """`config-schema.json` declares `active` and `profiles_dir`."""

    def test_active_declared_in_schema(self) -> None:
        schema = json.loads((PROJECT_ROOT / "config-schema.json").read_text())
        props = schema["properties"]["design_tokens"]["properties"]
        assert "active" in props
        assert props["active"]["type"] == "string"
        assert props["active"]["default"] == "default"

    def test_profiles_dir_declared_in_schema(self) -> None:
        schema = json.loads((PROJECT_ROOT / "config-schema.json").read_text())
        props = schema["properties"]["design_tokens"]["properties"]
        assert "profiles_dir" in props


# ---------------------------------------------------------------------------
# Init + configure doc wiring
# ---------------------------------------------------------------------------


class TestInitWiringForProfiles:
    """Init must materialize profiles dir and write `active`."""

    def test_init_skill_references_profiles_dir(self) -> None:
        content = (PROJECT_ROOT / "skills" / "init" / "SKILL.md").read_text()
        assert "profiles/" in content or "profiles" in content, (
            "skills/init/SKILL.md must reference the profiles directory in materialization"
        )

    def test_init_skill_references_active(self) -> None:
        content = (PROJECT_ROOT / "skills" / "init" / "SKILL.md").read_text()
        assert "design_tokens.active" in content or '"active"' in content, (
            "skills/init/SKILL.md must write design_tokens.active during materialization"
        )

    def test_init_round_7_offers_profile_picker(self) -> None:
        content = (PROJECT_ROOT / "skills" / "init" / "interactive.md").read_text()
        for name in PROFILE_NAMES:
            assert name in content, (
                f"interactive.md Round 7 must list profile '{name}' in the picker"
            )


class TestConfigureWiringForProfiles:
    """Configure must expose `active` + show installed profiles."""

    def test_configure_areas_references_active(self) -> None:
        content = (PROJECT_ROOT / "skills" / "configure" / "areas.md").read_text()
        assert "design_tokens.active" in content, (
            "configure/areas.md design_tokens area must reference `design_tokens.active`"
        )

    def test_configure_show_references_active(self) -> None:
        content = (PROJECT_ROOT / "skills" / "configure" / "show-output.md").read_text()
        assert "design_tokens.active" in content, (
            "configure/show-output.md design_tokens --show must reference `design_tokens.active`"
        )
