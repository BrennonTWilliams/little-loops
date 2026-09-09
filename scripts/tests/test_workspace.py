"""Tests for little_loops.workspace module (FEAT-3409)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import yaml

from little_loops.workspace import WorkspaceMember, discover_workspace_members


def _write_manifest(
    dir_path: Path, members: list[dict], filename: str = "ll-workspace.yaml"
) -> Path:
    """Write a well-formed ll-workspace.yaml manifest and return its path."""
    dir_path.mkdir(parents=True, exist_ok=True)
    manifest_path = dir_path / filename
    manifest_path.write_text(yaml.dump({"members": members}), encoding="utf-8")
    return manifest_path


def _write_raw_manifest(dir_path: Path, content: str, filename: str = "ll-workspace.yaml") -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    manifest_path = dir_path / filename
    manifest_path.write_text(content, encoding="utf-8")
    return manifest_path


class TestDiscoverWorkspaceMembersHappyPath:
    def test_well_formed_manifest_parses_correctly(self, tmp_path: Path) -> None:
        sibling = tmp_path / "sibling-service"
        sibling.mkdir()
        manifest = _write_manifest(
            tmp_path,
            [
                {"repo": ".", "role": "primary"},
                {"repo": "sibling-service", "role": "service", "db_path": ".ll/history.db"},
            ],
        )
        members = discover_workspace_members(manifest)
        assert len(members) == 2
        assert members[0].repo_path == tmp_path.resolve()
        assert members[0].role == "primary"
        assert members[0].db_path == (tmp_path / ".ll" / "history.db").resolve()
        assert members[1].repo_path == sibling.resolve()
        assert members[1].db_path == (sibling / ".ll" / "history.db").resolve()

    def test_default_db_path_ignores_ll_history_db_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "elsewhere.db"))
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        repo_a.mkdir()
        repo_b.mkdir()
        manifest = _write_manifest(
            tmp_path,
            [
                {"repo": "a", "role": "primary"},
                {"repo": "b", "role": "service"},
            ],
        )
        members = discover_workspace_members(manifest)
        db_paths = {m.db_path for m in members}
        assert len(db_paths) == 2
        assert (tmp_path / "elsewhere.db") not in db_paths

    def test_explicit_db_path_alias_through_symlink_collides_with_default(
        self, tmp_path: Path
    ) -> None:
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        repo_a.mkdir()
        (repo_a / ".ll").mkdir()
        (repo_a / ".ll" / "history.db").touch()
        repo_b.mkdir()
        symlinked_ll = repo_b / "linked-ll"
        symlinked_ll.symlink_to(repo_a / ".ll")
        manifest = _write_manifest(
            tmp_path,
            [
                {"repo": "a", "role": "primary"},
                {"repo": "b", "role": "service", "db_path": "linked-ll/history.db"},
            ],
        )
        with pytest.raises(ValueError, match="Duplicate workspace member"):
            discover_workspace_members(manifest)


class TestWorkspaceMemberFrozen:
    def test_attribute_assignment_raises(self, tmp_path: Path) -> None:
        member = WorkspaceMember(repo_path=tmp_path, role="primary", db_path=tmp_path / "db")
        with pytest.raises(dataclasses.FrozenInstanceError):
            member.role = "service"  # type: ignore[misc]


class TestGracefulDegradationAbsent:
    """Ancestor walk finds nothing -> [] (not None), never raises."""

    def test_no_manifest_anywhere_returns_empty_list(self, tmp_path: Path) -> None:
        assert discover_workspace_members(start=tmp_path) == []

    def test_returns_empty_list_not_none(self, tmp_path: Path) -> None:
        result = discover_workspace_members(start=tmp_path)
        assert result is not None
        assert result == []


class TestDeclaredMissingRaises:
    def test_explicit_manifest_path_missing_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "ll-workspace.yaml"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            discover_workspace_members(missing)

    def test_config_key_missing_manifest_raises(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"workspace_manifest_path": "no-such-manifest.yaml"}})
        )
        (tmp_path / ".git").mkdir()
        with pytest.raises(FileNotFoundError, match="no-such-manifest.yaml"):
            discover_workspace_members(start=tmp_path)


class TestTildeExpansion:
    def test_repo_and_db_path_expand_tilde(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        sibling = home / "sibling"
        sibling.mkdir()
        manifest_dir = tmp_path / "primary"
        manifest = _write_manifest(
            manifest_dir,
            [{"repo": "~/sibling", "role": "service", "db_path": "~/custom.db"}],
        )
        members = discover_workspace_members(manifest)
        assert members[0].repo_path == sibling.resolve()
        assert members[0].db_path == (home / "custom.db").resolve()


class TestStartParam:
    def test_start_seeds_ancestor_walk_without_chdir(self, tmp_path: Path) -> None:
        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()
        member_repo = ws_dir / "repo"
        member_repo.mkdir()
        _write_manifest(ws_dir, [{"repo": "repo", "role": "primary"}])
        members = discover_workspace_members(start=ws_dir)
        assert len(members) == 1

    def test_start_ignored_when_manifest_path_explicit(self, tmp_path: Path) -> None:
        other_dir = tmp_path / "elsewhere"
        manifest_dir = tmp_path / "primary"
        member_repo = manifest_dir / "repo"
        member_repo.mkdir(parents=True)
        manifest = _write_manifest(manifest_dir, [{"repo": "repo", "role": "primary"}])
        members = discover_workspace_members(manifest, start=other_dir)
        assert len(members) == 1


class TestConfigKeyStep:
    def test_reads_through_brconfig_local_override_wins(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (tmp_path / ".git").mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"workspace_manifest_path": "base-manifest.yaml"}})
        )
        (ll_dir / "ll.local.md").write_text(
            "---\nhistory:\n  workspace_manifest_path: local-manifest.yaml\n---\n"
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_manifest(
            tmp_path, [{"repo": "repo", "role": "primary"}], filename="base-manifest.yaml"
        )
        _write_manifest(
            tmp_path, [{"repo": "repo", "role": "service"}], filename="local-manifest.yaml"
        )
        members = discover_workspace_members(start=tmp_path)
        assert len(members) == 1
        assert members[0].role == "service"

    def test_stray_ancestor_config_with_key_is_honored(self, tmp_path: Path) -> None:
        # No .git anywhere -> find_project_root falls back to nearest .ll-only ancestor.
        stray_ll = tmp_path / ".ll"
        stray_ll.mkdir()
        (stray_ll / "ll-config.json").write_text(
            json.dumps({"history": {"workspace_manifest_path": "manifest.yaml"}})
        )
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_manifest(tmp_path, [{"repo": "repo", "role": "primary"}], filename="manifest.yaml")
        subdir = tmp_path / "sub"
        subdir.mkdir()
        members = discover_workspace_members(start=subdir)
        assert len(members) == 1

    def test_stray_ancestor_no_config_falls_through_to_ancestor_walk(self, tmp_path: Path) -> None:
        stray_ll = tmp_path / ".ll"
        stray_ll.mkdir()
        ws_dir = tmp_path / "ws"
        repo = ws_dir / "repo"
        repo.mkdir(parents=True)
        _write_manifest(ws_dir, [{"repo": "repo", "role": "primary"}])
        members = discover_workspace_members(start=ws_dir)
        assert len(members) == 1


class TestValueTypeEdgeCases:
    def test_db_path_none_value_uses_default(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        manifest = _write_raw_manifest(
            tmp_path, "members:\n  - repo: repo\n    role: primary\n    db_path:\n"
        )
        members = discover_workspace_members(manifest)
        assert members[0].db_path == (repo / ".ll" / "history.db").resolve()

    def test_db_path_empty_string_uses_default(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        manifest = _write_manifest(tmp_path, [{"repo": "repo", "role": "primary", "db_path": ""}])
        members = discover_workspace_members(manifest)
        assert members[0].db_path == (repo / ".ll" / "history.db").resolve()

    def test_role_non_string_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"repo": "repo", "role": 1}])
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_repo_non_string_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"repo": 1, "role": "primary"}])
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_role_empty_string_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"repo": "repo", "role": ""}])
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_db_path_non_string_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"repo": "repo", "role": "primary", "db_path": 1}])
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_explicit_relative_manifest_path_yields_absolute_members(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_manifest(tmp_path, [{"repo": "repo", "role": "primary"}])
        monkeypatch.chdir(tmp_path)
        members = discover_workspace_members(Path("ll-workspace.yaml"))
        assert members[0].repo_path.is_absolute()
        assert members[0].db_path.is_absolute()

    def test_symlinked_member_repo_stored_by_real_path(self, tmp_path: Path) -> None:
        real_repo = tmp_path / "real-repo"
        real_repo.mkdir()
        link = tmp_path / "link-repo"
        link.symlink_to(real_repo)
        manifest = _write_manifest(tmp_path, [{"repo": "link-repo", "role": "primary"}])
        members = discover_workspace_members(manifest)
        assert members[0].repo_path == real_repo.resolve()


class TestRelativeDbPathBase:
    def test_db_path_resolves_against_entrys_own_repo_path(self, tmp_path: Path) -> None:
        sibling = tmp_path / "sibling"
        sibling.mkdir()
        manifest = _write_manifest(
            tmp_path, [{"repo": "sibling", "role": "service", "db_path": ".ll/history.db"}]
        )
        members = discover_workspace_members(manifest)
        assert members[0].db_path == (sibling / ".ll" / "history.db").resolve()
        assert members[0].db_path != (tmp_path / ".ll" / "history.db").resolve()


class TestDuplicateEmptyAndEmptyMembers:
    def test_duplicate_db_path_raises_value_error(self, tmp_path: Path) -> None:
        repo_a = tmp_path / "a"
        repo_b = tmp_path / "b"
        repo_a.mkdir()
        repo_b.mkdir()
        manifest = _write_manifest(
            tmp_path,
            [
                {"repo": "a", "role": "primary", "db_path": "shared.db"},
                {"repo": "b", "role": "service", "db_path": "../a/shared.db"},
            ],
        )
        with pytest.raises(ValueError, match="Duplicate workspace member"):
            discover_workspace_members(manifest)

    def test_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_raw_manifest(tmp_path, "")
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_members_empty_list_returns_empty(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [])
        assert discover_workspace_members(manifest) == []

    def test_nonexistent_repo_and_db_path_still_returned(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"repo": "does-not-exist", "role": "primary"}])
        members = discover_workspace_members(manifest)
        assert len(members) == 1
        assert not members[0].repo_path.exists()


class TestMalformedManifestPropagates:
    def test_bad_yaml_syntax_raises_yaml_error(self, tmp_path: Path) -> None:
        manifest = _write_raw_manifest(tmp_path, "members: [unterminated\n")
        with pytest.raises(yaml.YAMLError):
            discover_workspace_members(manifest)

    def test_missing_repo_raises_key_error(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"role": "primary"}])
        with pytest.raises(KeyError):
            discover_workspace_members(manifest)

    def test_missing_role_raises_key_error(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, [{"repo": "."}])
        with pytest.raises(KeyError):
            discover_workspace_members(manifest)

    def test_non_mapping_top_level_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_raw_manifest(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_members_not_a_list_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_raw_manifest(tmp_path, "members: not-a-list\n")
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)

    def test_non_mapping_entry_raises_value_error(self, tmp_path: Path) -> None:
        manifest = _write_raw_manifest(tmp_path, "members:\n  - just-a-string\n")
        with pytest.raises(ValueError):
            discover_workspace_members(manifest)


class TestManifestPathResolutionChain:
    def test_explicit_arg_wins_over_config_and_ancestor(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        explicit = _write_manifest(
            tmp_path, [{"repo": "repo", "role": "explicit"}], filename="explicit.yaml"
        )
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (tmp_path / ".git").mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"workspace_manifest_path": "config.yaml"}})
        )
        _write_manifest(tmp_path, [{"repo": "repo", "role": "config"}], filename="config.yaml")
        _write_manifest(tmp_path, [{"repo": "repo", "role": "ancestor"}])
        members = discover_workspace_members(explicit, start=tmp_path)
        assert members[0].role == "explicit"

    def test_config_key_wins_over_ancestor_walk(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (tmp_path / ".git").mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"workspace_manifest_path": "config.yaml"}})
        )
        _write_manifest(tmp_path, [{"repo": "repo", "role": "config"}], filename="config.yaml")
        _write_manifest(tmp_path, [{"repo": "repo", "role": "ancestor"}])
        members = discover_workspace_members(start=tmp_path)
        assert members[0].role == "config"

    def test_ancestor_walk_wins_with_no_config_key(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_manifest(tmp_path, [{"repo": "repo", "role": "ancestor"}])
        members = discover_workspace_members(start=tmp_path)
        assert members[0].role == "ancestor"

    def test_stray_ll_ancestor_does_not_defeat_ancestor_walk(self, tmp_path: Path) -> None:
        # tmp_path has a stray .ll/ (no .git) and its own manifest; a ws/
        # subdirectory (no .ll, no .git) has the manifest that must win.
        (tmp_path / ".ll").mkdir()
        _write_manifest(tmp_path, [{"repo": ".", "role": "stray"}])
        ws_dir = tmp_path / "ws"
        repo = ws_dir / "repo"
        repo.mkdir(parents=True)
        _write_manifest(ws_dir, [{"repo": "repo", "role": "ws"}])
        members = discover_workspace_members(start=ws_dir)
        assert len(members) == 1
        assert members[0].role == "ws"

    def test_walk_from_subdirectory_of_primary_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _write_manifest(tmp_path, [{"repo": "repo", "role": "primary"}])
        subdir = tmp_path / "src" / "nested"
        subdir.mkdir(parents=True)
        members = discover_workspace_members(start=subdir)
        assert len(members) == 1
        assert members[0].role == "primary"


class TestProvenanceMessages:
    def test_explicit_missing_names_path_and_provenance(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.yaml"
        with pytest.raises(FileNotFoundError) as exc_info:
            discover_workspace_members(missing)
        assert str(missing) in str(exc_info.value)
        assert "explicit manifest_path" in str(exc_info.value)

    def test_config_key_missing_names_provenance(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (tmp_path / ".git").mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"workspace_manifest_path": "missing.yaml"}})
        )
        with pytest.raises(FileNotFoundError) as exc_info:
            discover_workspace_members(start=tmp_path)
        assert "history.workspace_manifest_path" in str(exc_info.value)

    def test_no_config_and_no_ancestor_returns_empty(self, tmp_path: Path) -> None:
        assert discover_workspace_members(start=tmp_path) == []
