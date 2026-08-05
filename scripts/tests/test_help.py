"""Tests for ll-help (FEAT-2940)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.cli.help import HelpEntry, collect_entries, main_help, render_catalog


class TestCollectEntries:
    def test_collects_command_and_skill(self, tmp_path: Path) -> None:
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "foo.md").write_text(
            '---\ndescription: "Foo command"\nargument-hint: "[x]"\n---\n'
        )
        skill_dir = tmp_path / "skills" / "bar"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text('---\ndescription: "Bar skill"\nargs: "Y"\n---\n')

        entries = collect_entries(tmp_path)

        by_name = {e.name: e for e in entries}
        assert by_name["foo"] == HelpEntry(
            name="foo", kind="command", description="Foo command", argument_hint="[x]", area="Other"
        )
        assert by_name["bar"] == HelpEntry(
            name="bar", kind="skill", description="Bar skill", argument_hint="Y", area="Other"
        )

    def test_bridge_stub_skill_excluded_when_command_exists(self, tmp_path: Path) -> None:
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "foo.md").write_text('---\ndescription: "Foo command"\n---\n')
        skill_dir = tmp_path / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            '---\ndescription: "Foo command"\ndisable-model-invocation: true\n---\n'
        )

        entries = collect_entries(tmp_path)

        assert [e.kind for e in entries if e.name == "foo"] == ["command"]

    def test_standalone_disabled_skill_kept_when_no_matching_command(self, tmp_path: Path) -> None:
        (tmp_path / "commands").mkdir()
        skill_dir = tmp_path / "skills" / "init"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            '---\ndescription: "Init"\ndisable-model-invocation: true\n---\n'
        )

        entries = collect_entries(tmp_path)

        assert [e.name for e in entries] == ["init"]

    def test_structured_arguments_list_used_when_no_argument_hint(self, tmp_path: Path) -> None:
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "foo.md").write_text(
            "---\n"
            'description: "Foo command"\n'
            "arguments:\n"
            "  - name: flags\n"
            "    description: some flags\n"
            "    required: false\n"
            "---\n"
        )
        (tmp_path / "skills").mkdir()

        entries = collect_entries(tmp_path)

        assert entries[0].argument_hint == "[flags]"

    def test_missing_dirs_return_empty(self, tmp_path: Path) -> None:
        assert collect_entries(tmp_path) == []


class TestRenderCatalog:
    def test_json_format(self) -> None:
        entries = [
            HelpEntry(name="foo", kind="command", description="d", argument_hint=None, area="A")
        ]
        out = render_catalog(entries, None, "json")
        assert json.loads(out) == [
            {
                "name": "foo",
                "kind": "command",
                "description": "d",
                "argument_hint": None,
                "area": "A",
            }
        ]

    def test_area_filter(self) -> None:
        entries = [
            HelpEntry(name="foo", kind="command", description="d", argument_hint=None, area="A"),
            HelpEntry(name="bar", kind="command", description="d", argument_hint=None, area="B"),
        ]
        out = render_catalog(entries, "B", "md")
        assert "bar" in out
        assert "foo" not in out

    def test_md_includes_command_prefix(self) -> None:
        entries = [
            HelpEntry(name="foo", kind="command", description="d", argument_hint=None, area="A"),
            HelpEntry(name="bar", kind="skill", description="d", argument_hint=None, area="A"),
        ]
        out = render_catalog(entries, None, "md")
        assert "/ll:foo" in out
        assert "`bar`" in out
        assert "/ll:bar" not in out


class TestMainHelp:
    def test_pip_only_install_exits_nonzero_without_crashing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        exit_code = main_help(["-C", str(tmp_path)])
        assert exit_code == 1
        assert "no plugin catalog found" in capsys.readouterr().err

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "foo.md").write_text('---\ndescription: "Foo"\n---\n')

        exit_code = main_help(["-C", str(tmp_path), "--json"])

        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data == [
            {
                "name": "foo",
                "kind": "command",
                "description": "Foo",
                "argument_hint": None,
                "area": "Other",
            }
        ]


class TestCatalogDriftGate:
    def test_collect_entries_covers_real_plugin_root(self) -> None:
        """Every commands/*.md and non-bridge skills/*/SKILL.md is in the catalog."""
        from little_loops.skill_expander import _find_plugin_root

        plugin_root = _find_plugin_root()
        commands_dir = plugin_root / "commands"
        if not commands_dir.is_dir():
            pytest.skip("plugin repo not available (pip-only install)")

        entries = collect_entries(plugin_root)
        names = {e.name for e in entries}

        expected_commands = {p.stem for p in commands_dir.glob("*.md")}
        assert expected_commands <= names
