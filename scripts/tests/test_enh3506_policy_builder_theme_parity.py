"""ENH-3506: policy-builder design-token / theme parity and readability.

Every `var(--x, ...)` the builder template references must be declared in both
stamped theme blocks (`:root` light, `[data-theme=dark]`) for each packaged
profile, with values matching `load_design_tokens(...).resolved`. Paired
foreground/background colors must stay readable (>= 4.5:1), including for
degraded token sources, where the template-local default blocks (placed before
the stamp point) supply the values. Browser/computed-style checks are not
pytest: see `.loops/verify-enh-3506-theme.yaml`.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

import little_loops
from little_loops.cli.artifact.policy_builder import render_policy_builder_html
from little_loops.config.core import BRConfig
from little_loops.design_tokens import load_design_tokens

PROFILES = ("default", "editorial-mono", "warm-paper")
THEMES = ("light", "dark")
PACKAGED_PROFILES_DIR = (
    Path(little_loops.__file__).parent / "templates" / "design-tokens" / "profiles"
)
DESIGN_MD_FIXTURE = Path(__file__).parent / "fixtures" / "design_md" / "paws_and_paths_DESIGN.md"

STAMP_MARKER = "/* Stamped design-token CSS custom properties"
BLOCK_RE = re.compile(r"(:root|\[data-theme=dark\])\s*\{(.*?)\n\}", re.S)
DECL_RE = re.compile(r"^\s*(--[\w-]+):\s*(.*?);\s*$", re.M)

# (foreground, background) token-name pairs that must stay readable.
PAIRS = [
    ("--color-action-primary-text", "--color-action-primary"),
    ("--color-status-success-text", "--color-status-success-bg"),
    ("--color-status-warning-text", "--color-status-warning-bg"),
    ("--color-status-error-text", "--color-status-error-bg"),
    ("--color-status-info-text", "--color-status-info-bg"),
    ("--color-text-primary", "--color-status-success-bg"),  # .rule-winner inherited text
    ("--color-text-secondary", "--color-surface-secondary"),  # pre (YAML output)
    ("--color-text-primary", "--color-surface-primary"),
    ("--color-text-primary", "--color-surface-raised"),
]


def _make_config(project: Path, dt: dict) -> BRConfig:
    (project / ".ll").mkdir(parents=True, exist_ok=True)
    (project / ".ll" / "ll-config.json").write_text(json.dumps({"design_tokens": dt}))
    config = BRConfig(project)
    if "source" in dt:
        config.design_tokens.source = dt["source"]
    return config


def _materialize_mirror(project: Path, profile: str) -> Path:
    dest = project / ".ll" / "design-tokens" / "profiles" / profile
    shutil.copytree(PACKAGED_PROFILES_DIR / profile, dest)
    return dest


def _split(html: str) -> tuple[str, str]:
    """Return (template-local defaults + rules region, stamped region)."""
    head, _, tail = html.partition(STAMP_MARKER)
    stamped, _, _ = tail.partition("* { box-sizing")
    return head, stamped


def _blocks(css: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for scope, body in BLOCK_RE.findall(css):
        out[scope] = dict(DECL_RE.findall(body))
    return out


def _defaults(html: str) -> dict[str, dict[str, str]]:
    head, _, _ = html.partition(STAMP_MARKER)
    return _blocks(head.split("<style>", 1)[1])


def _stamped(html: str) -> dict[str, dict[str, str]]:
    return _blocks(_split(html)[1])


def _template_refs() -> set[str]:
    tmpl = (
        Path(little_loops.__file__).parent / "templates" / "policy-router-builder.html.tmpl"
    ).read_text()
    rules = tmpl.split("* { box-sizing", 1)[1].split("</style>", 1)[0]
    return set(re.findall(r"var\((--[\w-]+)", rules))


def _effective(html: str, theme: str) -> dict[str, str]:
    """Custom properties in effect for *theme*: defaults overridden by stamped."""
    scope = "[data-theme=dark]" if theme == "dark" else ":root"
    dflt, stamped = _defaults(html), _stamped(html)
    values = dict(dflt.get(":root", {}))
    if theme == "dark":
        values.update(dflt.get(scope, {}))
    values.update(stamped.get(":root", {}))
    if theme == "dark":
        values.update(stamped.get(scope, {}))
    return values


def _lum(hex_color: str) -> float:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    chans = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _assert_readable(values: dict[str, str], label: str) -> None:
    for fg, bg in PAIRS:
        assert fg in values and bg in values, f"{label}: {fg}/{bg} undeclared"
        ratio = _contrast(values[fg], values[bg])
        assert ratio >= 4.5, f"{label}: {fg} on {bg} = {ratio:.2f}:1"


class TestPackagedProfileParity:
    @pytest.mark.parametrize("mirror", [False, True], ids=["packaged", "mirror"])
    @pytest.mark.parametrize("profile", PROFILES)
    def test_refs_declared_with_resolved_values(self, tmp_path, monkeypatch, profile, mirror):
        monkeypatch.chdir(tmp_path)
        if mirror:
            _materialize_mirror(tmp_path, profile)
        config = _make_config(tmp_path, {"enabled": True, "source": "profile", "active": profile})
        html = render_policy_builder_html(config)
        stamped = _stamped(html)
        refs = _template_refs()
        for theme, scope in (("light", ":root"), ("dark", "[data-theme=dark]")):
            tokens = load_design_tokens(config, theme=theme)
            assert tokens is not None and tokens.source != "design_md"
            block = stamped[scope]
            missing = sorted(refs - set(block))
            assert not missing, f"{profile}/{theme}: undeclared refs {missing}"
            expected = {
                "--" + k.replace(".", "-"): v
                for k, v in tokens.resolved.items()
                if not k.startswith("_")
            }
            assert block == expected

    @pytest.mark.parametrize("profile", PROFILES)
    @pytest.mark.parametrize("theme", THEMES)
    def test_paired_colors_readable(self, tmp_path, monkeypatch, profile, theme):
        monkeypatch.chdir(tmp_path)
        config = _make_config(tmp_path, {"enabled": True, "source": "profile", "active": profile})
        html = render_policy_builder_html(config)
        _assert_readable(
            _stamped(html)["[data-theme=dark]" if theme == "dark" else ":root"],
            f"{profile}/{theme}",
        )


class TestCompatibility:
    def test_template_local_defaults_are_readable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        html = render_policy_builder_html(_make_config(tmp_path, {"enabled": False}))
        assert not any(_stamped(html).values())
        for theme in THEMES:
            _assert_readable(_effective(html, theme), f"disabled/{theme}")

    def test_defaults_precede_stamp_point(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        html = render_policy_builder_html(_make_config(tmp_path, {"enabled": False}))
        head, _ = _split(html)
        assert "--color-status-success-bg" in head
        assert "color-scheme: light;" in head and "color-scheme: dark;" in head
        assert "color-scheme: light dark" not in html

    @pytest.mark.parametrize("theme", THEMES)
    def test_old_mirror_missing_new_keys_keeps_custom_values(self, tmp_path, monkeypatch, theme):
        monkeypatch.chdir(tmp_path)
        mirror = _materialize_mirror(tmp_path, "warm-paper")
        for rel in ("semantic.json", "themes/dark.json"):
            path = mirror / rel
            data = json.loads(path.read_text())
            data["color"].pop("status", None)
            data["color"]["action"].pop("primary-text", None)
            data["color"]["action"]["primary"] = "#123456"  # custom value
            path.write_text(json.dumps(data))
        config = _make_config(
            tmp_path,
            {"enabled": True, "source": "profile", "active": "warm-paper", "active_theme": theme},
        )
        html = render_policy_builder_html(config)
        assert "--color-status-success-bg" not in json.dumps(_stamped(html))
        values = _effective(html, theme)
        assert values["--color-action-primary"] == "#123456"
        assert "--color-status-success-bg" in values  # from template-local defaults
        for fg, bg in PAIRS[1:6]:
            assert _contrast(values[fg], values[bg]) >= 4.5

    @pytest.mark.parametrize("source", ["design_md", "auto"])
    def test_partial_design_md_renders_with_readable_status(self, tmp_path, monkeypatch, source):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "DESIGN.md").write_text(DESIGN_MD_FIXTURE.read_text())
        config = _make_config(tmp_path, {"enabled": True, "source": source})
        html = render_policy_builder_html(config)
        stamped = _stamped(html)
        # design_md: both blocks intentionally match (no per-theme resolution).
        assert stamped[":root"] == stamped["[data-theme=dark]"]
        for theme in THEMES:
            values = _effective(html, theme)
            for fg, bg in PAIRS[1:5]:
                assert _contrast(values[fg], values[bg]) >= 4.5, (source, theme, fg, bg)
