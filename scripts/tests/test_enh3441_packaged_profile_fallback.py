"""ENH-3441: packaged built-in profile fallback for `load_design_tokens`.

On a clean checkout the gitignored `.ll/design-tokens/` mirror (ENH-3275) is
absent, so every consumer of `load_design_tokens` silently rendered tokenless
and `test_policy_builder_renders_byte_identically_to_golden_fixture` failed at
byte 299. These tests pin the last-resort fallback to the packaged built-ins
and the precedence that keeps a project's own sources in charge:

    source == "auto":    mirror -> root DESIGN.md -> packaged built-in -> None
    source == "profile": mirror -> packaged built-in -> None
"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

import pytest

from little_loops.config.features import DesignTokensConfig
from little_loops.design_tokens import (
    _resolve_packaged_profile_root,
    load_design_tokens,
)

PACKAGED_PROFILES = ("default", "warm-paper", "editorial-mono")

# Proven values from the vendored spec fixture (test_design_tokens.py AC 4/4b),
# used to prove a root DESIGN.md outranks the packaged fallback.
_DESIGN_MD_FIXTURE = (
    Path(__file__).parent / "fixtures" / "design_md" / "paws_and_paths_DESIGN.md"
).read_text()


def _make_config(project_root: Path, extra: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {"design_tokens": {"enabled": True}}
    if extra:
        cfg["design_tokens"].update(extra)
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    config = BRConfig(project_root)
    if extra and "source" in extra:
        config.design_tokens.source = extra["source"]
    return config


def _write_mirror_profile(project_root: Path, active: str = "default") -> None:
    """Materialize a minimal mirror profile with a locally-unique value."""
    profile_dir = project_root / ".ll" / "design-tokens" / "profiles" / active
    profile_dir.mkdir(parents=True)
    (profile_dir / "primitives.json").write_text(
        json.dumps({"color": {"brand": {"500": "#local-override"}}})
    )
    (profile_dir / "semantic.json").write_text("{}")
    (profile_dir / "themes").mkdir()
    (profile_dir / "themes" / "dark.json").write_text("{}")


def _packaged_profiles_root() -> Path:
    return Path(
        str(
            importlib.resources.files("little_loops").joinpath(
                "templates", "design-tokens", "profiles"
            )
        )
    )


# ---------------------------------------------------------------------------
# Fallback: clean checkout (no mirror, no root DESIGN.md)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile_name", PACKAGED_PROFILES)
@pytest.mark.parametrize("source", ["auto", "profile"])
def test_clean_checkout_resolves_packaged_profile(
    tmp_path: Path, source: str, profile_name: str
) -> None:
    """The reported symptom: absent mirror must not mean absent tokens."""
    config = _make_config(tmp_path, {"source": source, "active": profile_name})
    result = load_design_tokens(config)
    assert result is not None
    assert result.source == "profile"
    assert result.resolved
    assert result.source_path.name == profile_name
    assert _packaged_profiles_root() in result.source_path.parents


@pytest.mark.parametrize("source", ["auto", "profile"])
def test_unknown_active_genuinely_absent_returns_none(tmp_path: Path, source: str) -> None:
    """No packaged built-in carries the active name -> still degrades to None."""
    config = _make_config(tmp_path, {"source": source, "active": "nonexistent"})
    assert load_design_tokens(config) is None


# ---------------------------------------------------------------------------
# Precedence: the project's own sources outrank the packaged built-in
# ---------------------------------------------------------------------------


def test_mirror_wins_over_packaged_fallback(tmp_path: Path) -> None:
    """A materialized mirror (even with local-only content) is never
    replaced by the packaged built-in."""
    _write_mirror_profile(tmp_path)
    config = _make_config(tmp_path)
    result = load_design_tokens(config)
    assert result is not None
    assert result.source == "profile"
    assert result.resolved["color.brand.500"] == "#local-override"
    assert tmp_path in result.source_path.parents


def test_design_md_outranks_packaged_fallback(tmp_path: Path) -> None:
    """The single most important precedence pin (corrected ordering): a root
    DESIGN.md with no mirror resolves the project's own tokens, NOT generic
    built-in defaults."""
    (tmp_path / "DESIGN.md").write_text(_DESIGN_MD_FIXTURE)
    config = _make_config(tmp_path, {"source": "auto"})
    result = load_design_tokens(config)
    assert result is not None
    assert result.source == "design_md"
    assert result.resolved["color.action.primary"] == "#855300"


# ---------------------------------------------------------------------------
# Fallback strength and visibility
# ---------------------------------------------------------------------------


def test_empty_packaged_dir_cannot_satisfy_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same >=1-token-file strength as `_materialized_token_root`: an empty
    packaged profile directory must not satisfy the fallback."""
    empty_profile = tmp_path / "templates" / "design-tokens" / "profiles" / "default"
    empty_profile.mkdir(parents=True)
    monkeypatch.setattr(importlib.resources, "files", lambda _pkg: tmp_path)
    assert _resolve_packaged_profile_root(DesignTokensConfig()) is None


def test_fallback_notice_emitted_once_per_root_and_active(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One stderr notice per (project_root, active) per process: the light +
    dark double call in `_cached_themed_tokens` yields exactly one notice."""
    config = _make_config(tmp_path)
    assert load_design_tokens(config) is not None
    assert load_design_tokens(config, theme="light") is not None
    err = capsys.readouterr().err
    assert err.count("packaged built-in profile 'default'") == 1


def test_fallback_notice_re_notices_for_distinct_roots(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    root_a = tmp_path_factory.mktemp("proj_a")
    root_b = tmp_path_factory.mktemp("proj_b")
    assert load_design_tokens(_make_config(root_a)) is not None
    assert load_design_tokens(_make_config(root_b)) is not None
    assert capsys.readouterr().err.count("packaged built-in profile") == 2


# ---------------------------------------------------------------------------
# Drift gates
# ---------------------------------------------------------------------------


def _collect_profile_drift(packaged_root: Path, other_root: Path) -> list[str]:
    """Byte-compare every packaged profile JSON against *other_root*'s copy."""
    offenders: list[str] = []
    for profile in PACKAGED_PROFILES:
        packaged_dir = packaged_root / profile
        other_dir = other_root / profile
        packaged_files = (
            sorted(p.relative_to(packaged_dir).as_posix() for p in packaged_dir.rglob("*.json"))
            if packaged_dir.is_dir()
            else []
        )
        other_files = (
            sorted(p.relative_to(other_dir).as_posix() for p in other_dir.rglob("*.json"))
            if other_dir.is_dir()
            else []
        )
        for rel in sorted(set(packaged_files) - set(other_files)):
            offenders.append(f"{profile}: missing {rel}")
        for rel in sorted(set(other_files) - set(packaged_files)):
            offenders.append(f"{profile}: stale {rel}")
        for rel in sorted(set(packaged_files) & set(other_files)):
            if (packaged_dir / rel).read_bytes() != (other_dir / rel).read_bytes():
                offenders.append(f"{profile}: drifted {rel}")
    return offenders


def test_deploy_design_tokens_matches_packaged_profiles(tmp_path: Path) -> None:
    """Primary drift gate (runs everywhere, never skips).

    Materializes the mirror via `deploy_design_tokens` into a tmp_path from
    the templates/ tree ll-init resolves, then byte-compares every packaged
    profile JSON against that copy. Honest scope: deploy is a
    `shutil.copytree` from the same in-package tree the fallback reads, so
    this verifies deploy-path consistency and completeness (and
    `CLAUDE_PLUGIN_ROOT`-rooted divergence), not mirror drift — CI has no
    ambient mirror to be stale.
    """
    from little_loops.init.writers import deploy_design_tokens
    from little_loops.issue_template import _default_templates_dir

    assert deploy_design_tokens(tmp_path, _default_templates_dir())
    deployed_root = tmp_path / "design-tokens" / "profiles"
    offenders = _collect_profile_drift(_packaged_profiles_root(), deployed_root)
    assert not offenders, (
        "Deployed design-token profiles diverge from the packaged built-ins "
        "the ENH-3441 fallback reads: "
        + "; ".join(offenders)
        + ". Regenerate with: ll-init (deploy_design_tokens)"
    )


def test_ambient_mirror_matches_packaged_profiles() -> None:
    """Secondary drift gate (local-only signal; skips when the gitignored
    ambient mirror is absent — CI never has one).

    The only check that can detect a stale or hand-edited local mirror.
    """
    repo_root = Path(__file__).resolve().parents[2]
    ambient_root = repo_root / ".ll" / "design-tokens" / "profiles"
    if not ambient_root.is_dir():
        pytest.skip("no ambient .ll/design-tokens mirror on this machine")
    offenders = _collect_profile_drift(_packaged_profiles_root(), ambient_root)
    assert not offenders, (
        "Ambient .ll/design-tokens/profiles mirror drifted from the packaged "
        "built-ins: "
        + "; ".join(offenders)
        + ". Regenerate with: ll-init (deploy_design_tokens --force reset)"
    )
