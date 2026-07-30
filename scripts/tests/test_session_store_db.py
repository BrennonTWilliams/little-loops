"""Tests for little_loops.session_store — db module."""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pytest

from little_loops.session_store import (
    ensure_db,
)

# ENH-2529: consolidate per-test temp dirs under one module-scoped parent to cut
# macOS launchservicesd/mds re-indexing churn during full-suite runs. Each test
# still gets a fresh, unique directory; only the parent dir consolidates.
_TMP_COUNTER = itertools.count()


@pytest.fixture(scope="module")
def _module_tmp_parent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One temp parent per module instead of one top-level dir per test."""
    return tmp_path_factory.mktemp("session_store")


@pytest.fixture
def tmp_path(_module_tmp_parent: Path, request: pytest.FixtureRequest) -> Path:
    """Override built-in tmp_path: unique fresh subdir of the module parent."""
    name = re.sub(r"\W", "_", request.node.name)[:30]
    path = _module_tmp_parent / f"{name}_{next(_TMP_COUNTER)}"
    path.mkdir()
    return path


class TestDbPathResolution:
    """ENH-2623: unified env → config → default DB-path precedence.

    ``resolve_history_db()`` and ``ensure_db()`` must agree for the same inputs
    (the historical divergence footgun), and the new ``history.db_path`` config
    key slots in as the middle precedence rung below ``LL_HISTORY_DB``.
    """

    def _resolvers(self):
        from little_loops.session_store import DEFAULT_DB_PATH, resolve_history_db

        return DEFAULT_DB_PATH, resolve_history_db

    def test_resolve_and_ensure_agree_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_history_db(p) == ensure_db(p) for {default, override} × {env set, unset}."""
        DEFAULT_DB_PATH, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        env_db = tmp_path / "env.db"
        override = tmp_path / "override.db"
        for path in (None, DEFAULT_DB_PATH, override):
            for env in (str(env_db), None):
                if env is None:
                    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
                else:
                    monkeypatch.setenv("LL_HISTORY_DB", env)
                assert resolve_history_db(path) == ensure_db(path), (
                    f"divergence for path={path!r} env={env!r}"
                )

    def test_explicit_override_wins_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A deliberate (non-default-shaped) path is honored verbatim over LL_HISTORY_DB."""
        _, resolve_history_db = self._resolvers()
        override = tmp_path / "override.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "env.db"))
        assert resolve_history_db(override) == override

    def test_env_wins_over_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """LL_HISTORY_DB beats history.db_path for a default-shaped path."""
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": str(tmp_path / "cfg.db")}}), encoding="utf-8"
        )
        env_db = tmp_path / "env.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(env_db))
        assert resolve_history_db(None) == env_db

    def test_config_used_when_env_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With env unset, history.db_path is the resolved path for a default-shaped input."""
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        cfg_db = tmp_path / "cfg.db"
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": str(cfg_db)}}), encoding="utf-8"
        )
        assert resolve_history_db(None) == cfg_db

    def test_config_relative_path_resolves_against_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A relative history.db_path resolves against the project root (cwd)."""
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": "data/hist.db"}}), encoding="utf-8"
        )
        assert resolve_history_db(None) == tmp_path / "data" / "hist.db"

    def test_default_when_neither_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No env, no config, no resolvable project root → cwd-absolute default (ENH-2927).

        ``tmp_path`` here has no ``.git``/``.ll`` anywhere on its walk, so
        ``resolve_ll_dir()`` can't find a project root; the fallback is a
        cwd-*absolute* form of the legacy relative ``DEFAULT_DB_PATH`` — same
        on-disk location, but no longer the bare relative constant (which
        would resolve against whatever cwd happens to be at connect-time).
        """
        DEFAULT_DB_PATH, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        assert resolve_history_db(None) == tmp_path / DEFAULT_DB_PATH

    def test_malformed_config_falls_back_to_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed ll-config.json must not raise; resolution falls through to default.

        ``tmp_path / .ll`` exists here, so it *does* resolve as a project root
        (ENH-2927) — the expected default is anchored there via
        ``resolve_ll_dir()``, not the bare relative ``DEFAULT_DB_PATH``.
        """
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text("{ not valid json", encoding="utf-8")
        assert resolve_history_db(None) == ll_dir / "history.db"
