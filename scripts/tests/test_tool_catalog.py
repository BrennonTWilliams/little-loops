"""Tests for little_loops.tool_catalog (FEAT-2680)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.tool_catalog import (
    ToolDefinition,
    assemble_tool_catalog,
    to_anthropic_tools,
)


def _make_skill(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    extra_frontmatter: str = "",
    body: str = "# My Skill\n\nDoes stuff.",
) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\ndescription: {description}\n{extra_frontmatter}---\n\n{body}")
    return skill_md


def _make_command(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    extra_frontmatter: str = "",
    body: str = "# My Command\n\nDoes stuff.",
) -> Path:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    cmd_md = commands_dir / f"{name}.md"
    cmd_md.write_text(f"---\ndescription: {description}\n{extra_frontmatter}---\n\n{body}")
    return cmd_md


def _make_agent(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    model: str = "sonnet",
    body: str = "Agent instructions.",
    tools: list[str] | None = None,
) -> Path:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agents_dir / f"{name}.md"
    tools_line = f"tools: {json.dumps(tools)}\n" if tools is not None else 'tools: ["Read"]\n'
    agent_md.write_text(
        f"---\nname: {name}\ndescription: |\n  {description}\nmodel: {model}\n"
        f"{tools_line}---\n\n{body}"
    )
    return agent_md


class TestAssembleToolCatalogSkills:
    def test_skill_entry_has_name_and_description(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill", description='"My skill desc"')
        entries = assemble_tool_catalog(tmp_path)
        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, ToolDefinition)
        assert entry.name == "my-skill"
        assert entry.description == "My skill desc"

    def test_skill_without_args_gets_empty_properties_schema(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill")
        entries = assemble_tool_catalog(tmp_path)
        assert entries[0].input_schema == {"type": "object", "properties": {}, "required": []}

    def test_skill_with_args_gets_single_property_schema(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "my-skill",
            extra_frontmatter='args: "ISSUE_ID [--auto]"\n',
        )
        entries = assemble_tool_catalog(tmp_path)
        schema = entries[0].input_schema
        assert schema["type"] == "object"
        assert schema["properties"]["args"] == {
            "type": "string",
            "description": "ISSUE_ID [--auto]",
        }
        assert schema["required"] == []

    def test_skill_with_argument_hint_fallback(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "my-skill",
            extra_frontmatter='argument-hint: "[flags]"\n',
        )
        entries = assemble_tool_catalog(tmp_path)
        assert entries[0].input_schema["properties"]["args"]["description"] == "[flags]"

    def test_missing_skills_dir_yields_no_entries(self, tmp_path: Path) -> None:
        entries = assemble_tool_catalog(tmp_path)
        assert entries == []

    def test_unreadable_skill_file_degrades_to_empty_description(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_skill(tmp_path, "my-skill")
        real_read_text = Path.read_text

        def _boom(self: Path, *args: object, **kwargs: object) -> str:
            if self.name == "SKILL.md":
                raise OSError("boom")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _boom)
        entries = assemble_tool_catalog(tmp_path)
        assert len(entries) == 1
        assert entries[0].description == ""


class TestAssembleToolCatalogCommands:
    def test_command_entry_has_name_and_description(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "my-command", description='"My command desc"')
        entries = assemble_tool_catalog(tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "my-command"
        assert entries[0].description == "My command desc"

    def test_missing_commands_dir_yields_no_entries(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        entries = assemble_tool_catalog(tmp_path)
        assert entries == []


class TestAssembleToolCatalogAgents:
    def test_agent_entry_has_name_and_description(self, tmp_path: Path) -> None:
        _make_agent(tmp_path, "my-agent", description="Use when user asks for stuff.")
        entries = assemble_tool_catalog(tmp_path)
        assert len(entries) == 1
        assert entries[0].name == "my-agent"
        assert entries[0].description == "Use when user asks for stuff."

    def test_agent_gets_fixed_description_prompt_schema(self, tmp_path: Path) -> None:
        _make_agent(tmp_path, "my-agent", tools=["Read", "Glob"])
        entries = assemble_tool_catalog(tmp_path)
        schema = entries[0].input_schema
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"description", "prompt"}
        assert schema["properties"]["description"]["type"] == "string"
        assert schema["properties"]["prompt"]["type"] == "string"
        assert set(schema["required"]) == {"description", "prompt"}

    def test_missing_agents_dir_yields_no_entries(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        entries = assemble_tool_catalog(tmp_path)
        assert entries == []


class TestAssembleToolCatalogCombined:
    def test_walks_all_three_kinds_together(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "skill-a")
        _make_command(tmp_path, "command-a")
        _make_agent(tmp_path, "agent-a")
        entries = assemble_tool_catalog(tmp_path)
        assert {e.name for e in entries} == {"skill-a", "command-a", "agent-a"}

    def test_ordering_is_deterministic_within_each_kind(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "skill-b")
        _make_skill(tmp_path, "skill-a")
        entries = assemble_tool_catalog(tmp_path)
        skill_names = [e.name for e in entries if e.name.startswith("skill-")]
        assert skill_names == ["skill-a", "skill-b"]


class TestToAnthropicTools:
    def test_serializes_required_keys_only_when_no_cache_control(self) -> None:
        entry = ToolDefinition(
            name="my-tool",
            description="Does a thing.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        tools = to_anthropic_tools([entry])
        assert tools == [
            {
                "name": "my-tool",
                "description": "Does a thing.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        ]
        assert "cache_control" not in tools[0]

    def test_includes_cache_control_when_set(self) -> None:
        entry = ToolDefinition(
            name="my-tool",
            description="Does a thing.",
            input_schema={"type": "object", "properties": {}, "required": []},
            cache_control={"type": "ephemeral"},
        )
        tools = to_anthropic_tools([entry])
        assert tools[0]["cache_control"] == {"type": "ephemeral"}

    def test_empty_list_roundtrips(self) -> None:
        assert to_anthropic_tools([]) == []

    def test_no_defer_loading_when_threshold_unset(self) -> None:
        entries = [
            ToolDefinition(name="t0", description="d" * 20, input_schema={"type": "object"}),
            ToolDefinition(name="t1", description="d" * 20, input_schema={"type": "object"}),
        ]
        tools = to_anthropic_tools(entries)
        assert all("defer_loading" not in t for t in tools)

    def test_defer_loading_flag_set_above_threshold(self) -> None:
        entries = [
            ToolDefinition(name="t0", description="d" * 20, input_schema={"type": "object"}),
            ToolDefinition(name="t1", description="d" * 20, input_schema={"type": "object"}),
            ToolDefinition(name="t2", description="d" * 20, input_schema={"type": "object"}),
        ]
        tools = to_anthropic_tools(entries, defer_loading_threshold=1)
        assert "defer_loading" not in tools[0]
        assert tools[1]["defer_loading"] is True
        assert tools[2]["defer_loading"] is True

    def test_defer_loading_validates_against_installed_sdk(self) -> None:
        import pydantic
        from anthropic.types import ToolParam

        entries = [ToolDefinition(name="t0", description="d" * 20, input_schema={"type": "object"})]
        tools = to_anthropic_tools(entries, defer_loading_threshold=0)
        pydantic.TypeAdapter(ToolParam).validate_python(tools[0])
