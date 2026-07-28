"""Tests for adapters.core, adapters.codex (FEAT-2391), and adapters.gemini (FEAT-2392)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.adapters.codex import _MARKER, CodexEmitter
from little_loops.adapters.core import (
    AdapterError,
    HostEmitter,
    _extract_body,
    _is_model_invocation_disabled,
    _read_frontmatter,
    process_agents,
    process_commands,
    process_skills,
    resolve_emitter,
)
from little_loops.adapters.gemini import GeminiEmitter

# =============================================================================
# Fixture helpers
# =============================================================================


def _make_skill(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for tasks.",
    extra_fm: str = "",
) -> Path:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\ndescription: {description}\n{extra_fm}---\n\n# {name.replace('-', ' ').title()}\n"
    )
    return skill_md


def _make_command(
    tmp_path: Path,
    stem: str,
    description: str = "Run this command to do stuff.",
    extra_fm: str = "",
) -> Path:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    cmd_md = commands_dir / f"{stem}.md"
    cmd_md.write_text(
        f"---\ndescription: {description}\n{extra_fm}---\n\n# {stem.replace('-', ' ').title()}\n"
    )
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


# =============================================================================
# resolve_emitter
# =============================================================================


class TestResolveEmitter:
    def test_codex_returns_codex_emitter(self) -> None:
        assert isinstance(resolve_emitter("codex"), CodexEmitter)

    def test_omp_returns_emitter_that_raises(self) -> None:
        emitter = resolve_emitter("omp")
        with pytest.raises(AdapterError):
            emitter.emit_skill({})

    def test_unknown_host_raises_adapter_error(self) -> None:
        with pytest.raises(AdapterError, match="not registered"):
            resolve_emitter("unknown-host")

    def test_returned_emitter_satisfies_protocol(self) -> None:
        assert isinstance(resolve_emitter("codex"), HostEmitter)


# =============================================================================
# _is_model_invocation_disabled
# =============================================================================


class TestIsModelInvocationDisabled:
    def test_bool_true(self) -> None:
        assert _is_model_invocation_disabled({"disable-model-invocation": True}) is True

    def test_string_true(self) -> None:
        assert _is_model_invocation_disabled({"disable-model-invocation": "true"}) is True

    def test_string_yes(self) -> None:
        assert _is_model_invocation_disabled({"disable-model-invocation": "yes"}) is True

    def test_string_1(self) -> None:
        assert _is_model_invocation_disabled({"disable-model-invocation": "1"}) is True

    def test_bool_false(self) -> None:
        assert _is_model_invocation_disabled({"disable-model-invocation": False}) is False

    def test_absent(self) -> None:
        assert _is_model_invocation_disabled({}) is False

    def test_none_value(self) -> None:
        assert _is_model_invocation_disabled({"disable-model-invocation": None}) is False


# =============================================================================
# _extract_body
# =============================================================================


class TestExtractBody:
    def test_returns_body_after_frontmatter(self) -> None:
        text = "---\nname: foo\n---\n# Body\n"
        assert "# Body" in _extract_body(text)

    def test_no_frontmatter_returns_empty(self) -> None:
        assert _extract_body("# No frontmatter") == ""

    def test_unclosed_frontmatter_returns_empty(self) -> None:
        assert _extract_body("---\nname: foo\n") == ""

    def test_multiline_frontmatter(self) -> None:
        text = "---\nname: foo\ndescription: bar\nmodel: sonnet\n---\n# My Agent\n\nBody here.\n"
        assert "# My Agent" in _extract_body(text)


# =============================================================================
# _read_frontmatter
# =============================================================================


class TestReadFrontmatter:
    def test_parses_simple_frontmatter(self) -> None:
        text = "---\nname: foo\nmodel: sonnet\n---\n# Body"
        fm = _read_frontmatter(text)
        assert fm is not None
        assert fm["name"] == "foo"
        assert fm["model"] == "sonnet"

    def test_no_frontmatter_returns_none(self) -> None:
        assert _read_frontmatter("# No frontmatter") is None

    def test_unclosed_returns_none(self) -> None:
        assert _read_frontmatter("---\nname: foo\n") is None


# =============================================================================
# Mock emitter for traversal tests
# =============================================================================


class _MockEmitter:
    name = "mock"

    def __init__(self, return_value: str = "adapted") -> None:
        self.skill_calls: list[dict] = []
        self.command_calls: list[dict] = []
        self.agent_calls: list[dict] = []
        self._return_value = return_value

    def emit_skill(self, meta: dict) -> str:
        self.skill_calls.append(meta)
        return self._return_value

    def emit_command(self, meta: dict) -> str:
        self.command_calls.append(meta)
        return self._return_value

    def emit_agent(self, meta: dict) -> str:
        self.agent_calls.append(meta)
        return self._return_value


# =============================================================================
# process_skills traversal
# =============================================================================


class TestProcessSkillsTraversal:
    def test_calls_emitter_for_each_skill(self, tmp_path: Path) -> None:
        for name in ["skill-a", "skill-b"]:
            _make_skill(tmp_path, name)
        emitter = _MockEmitter()
        adapted, skipped, errors = process_skills(emitter, tmp_path / "skills", False, True)
        assert len(emitter.skill_calls) == 2
        assert adapted == 2
        assert skipped == 0
        assert errors == 0

    def test_skips_skill_with_disable_model_invocation(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "disabled-skill", extra_fm="disable-model-invocation: true\n")
        _make_skill(tmp_path, "normal-skill")
        emitter = _MockEmitter()
        adapted, skipped, errors = process_skills(emitter, tmp_path / "skills", False, True)
        assert len(emitter.skill_calls) == 1  # only normal-skill
        assert skipped == 1
        assert adapted == 1

    def test_skill_meta_has_required_keys(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "my-skill")
        emitter = _MockEmitter()
        process_skills(emitter, tmp_path / "skills", False, True)
        meta = emitter.skill_calls[0]
        for key in ("skill_name", "skill_path", "content", "fm", "apply", "quiet"):
            assert key in meta

    def test_error_return_increments_errors(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "bad-skill")
        emitter = _MockEmitter(return_value="error")
        adapted, skipped, errors = process_skills(emitter, tmp_path / "skills", False, True)
        assert errors == 1
        assert adapted == 0


# =============================================================================
# process_commands traversal
# =============================================================================


class TestProcessCommandsTraversal:
    def test_calls_emitter_for_each_command(self, tmp_path: Path) -> None:
        for stem in ["help", "configure"]:
            _make_command(tmp_path, stem)
        emitter = _MockEmitter()
        adapted, skipped, errors = process_commands(
            emitter, tmp_path / "commands", tmp_path / "skills", False, True
        )
        assert len(emitter.command_calls) == 2
        assert adapted == 2

    def test_skips_command_with_disable_model_invocation(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "disabled-cmd", extra_fm="disable-model-invocation: true\n")
        _make_command(tmp_path, "normal-cmd")
        emitter = _MockEmitter()
        adapted, skipped, errors = process_commands(
            emitter, tmp_path / "commands", tmp_path / "skills", False, True
        )
        assert len(emitter.command_calls) == 1
        assert skipped == 1

    def test_command_meta_has_required_keys(self, tmp_path: Path) -> None:
        _make_command(tmp_path, "my-cmd")
        emitter = _MockEmitter()
        process_commands(emitter, tmp_path / "commands", tmp_path / "skills", False, True)
        meta = emitter.command_calls[0]
        for key in ("stem", "cmd_path", "content", "fm", "output_dir", "apply", "quiet"):
            assert key in meta

    def test_nonexistent_commands_dir_returns_zero(self, tmp_path: Path) -> None:
        emitter = _MockEmitter()
        adapted, skipped, errors = process_commands(
            emitter, tmp_path / "commands", tmp_path / "skills", False, True
        )
        assert adapted == skipped == errors == 0


# =============================================================================
# process_agents traversal
# =============================================================================


class TestProcessAgentsTraversal:
    def test_calls_emitter_for_each_agent(self, tmp_path: Path) -> None:
        for name in ["agent-a", "agent-b"]:
            _make_agent(tmp_path, name)
        emitter = _MockEmitter()
        adapted, _, errors = process_agents(
            emitter, tmp_path / "agents", tmp_path / ".codex" / "agents", False, True
        )
        assert len(emitter.agent_calls) == 2
        assert adapted == 2

    def test_only_filter_restricts_to_single_agent(self, tmp_path: Path) -> None:
        for name in ["agent-a", "agent-b", "agent-c"]:
            _make_agent(tmp_path, name)
        emitter = _MockEmitter()
        adapted, skipped, _ = process_agents(
            emitter,
            tmp_path / "agents",
            tmp_path / ".codex" / "agents",
            False,
            True,
            only="agent-b",
        )
        assert len(emitter.agent_calls) == 1
        assert emitter.agent_calls[0]["agent_name"] == "agent-b"
        assert adapted == 1
        assert skipped == 0  # non-matching agents silently dropped, not counted

    def test_agent_meta_has_required_keys(self, tmp_path: Path) -> None:
        _make_agent(tmp_path, "my-agent")
        emitter = _MockEmitter()
        process_agents(emitter, tmp_path / "agents", tmp_path / ".codex" / "agents", False, True)
        meta = emitter.agent_calls[0]
        for key in ("agent_name", "agent_path", "content", "fm", "output_dir", "apply", "quiet"):
            assert key in meta

    def test_adapter_error_from_emit_agent_counted_as_error(self, tmp_path: Path) -> None:
        class _RaisingEmitter(_MockEmitter):
            def emit_agent(self, meta: dict) -> str:
                raise AdapterError("preview feature")

        _make_agent(tmp_path, "stub-agent")
        emitter = _RaisingEmitter()
        adapted, skipped, errors = process_agents(
            emitter, tmp_path / "agents", tmp_path / ".codex" / "agents", False, True
        )
        assert errors == 1
        assert adapted == 0


# =============================================================================
# CodexEmitter: marker
# =============================================================================


class TestCodexEmitterMarker:
    def test_marker_string(self) -> None:
        assert _MARKER == "# generated by ll-adapt"


# =============================================================================
# CodexEmitter.emit_skill
# =============================================================================


class TestCodexEmitterEmitSkill:
    def _meta(self, tmp_path: Path, name: str, apply: bool = True, **kwargs: object) -> dict:
        skill_path = _make_skill(tmp_path, name, **kwargs)
        content = skill_path.read_text()
        fm = _read_frontmatter(content) or {}
        return {
            "skill_name": name,
            "skill_path": skill_path,
            "content": content,
            "fm": fm,
            "apply": apply,
            "quiet": True,
        }

    def test_inserts_name_into_frontmatter(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        CodexEmitter().emit_skill(meta)
        assert "name: my-skill" in meta["skill_path"].read_text()

    def test_inserts_short_description(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", description="Do great things.")
        CodexEmitter().emit_skill(meta)
        assert "short-description:" in meta["skill_path"].read_text()

    def test_creates_openai_yaml(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        CodexEmitter().emit_skill(meta)
        assert (meta["skill_path"].parent / "agents" / "openai.yaml").exists()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", apply=False)
        original = meta["content"]
        CodexEmitter().emit_skill(meta)
        assert meta["skill_path"].read_text() == original
        assert not (meta["skill_path"].parent / "agents" / "openai.yaml").exists()

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        assert CodexEmitter().emit_skill(meta) == "adapted"

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        CodexEmitter().emit_skill(meta)
        content2 = meta["skill_path"].read_text()
        meta2 = {**meta, "content": content2, "fm": _read_frontmatter(content2) or {}}
        assert CodexEmitter().emit_skill(meta2) == "skipped"

    def test_idempotent_no_double_insert(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        CodexEmitter().emit_skill(meta)
        content1 = meta["skill_path"].read_text()
        meta["content"] = content1
        meta["fm"] = _read_frontmatter(content1) or {}
        CodexEmitter().emit_skill(meta)
        content2 = meta["skill_path"].read_text()
        assert content1 == content2
        assert content2.count("name: my-skill") == 1


# =============================================================================
# CodexEmitter.emit_command
# =============================================================================


class TestCodexEmitterEmitCommand:
    def _meta(self, tmp_path: Path, stem: str, apply: bool = True, **kwargs: object) -> dict:
        cmd_path = _make_command(tmp_path, stem, **kwargs)
        content = cmd_path.read_text()
        fm = _read_frontmatter(content) or {}
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        return {
            "stem": stem,
            "cmd_path": cmd_path,
            "content": content,
            "fm": fm,
            "output_dir": skills_dir,
            "apply": apply,
            "quiet": True,
        }

    def test_creates_synthesized_skill_md(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        CodexEmitter().emit_command(meta)
        assert (meta["output_dir"] / "ll-my-cmd" / "SKILL.md").exists()

    def test_creates_openai_yaml(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        CodexEmitter().emit_command(meta)
        assert (meta["output_dir"] / "ll-my-cmd" / "agents" / "openai.yaml").exists()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", apply=False)
        CodexEmitter().emit_command(meta)
        assert not (meta["output_dir"] / "ll-my-cmd").exists()

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        assert CodexEmitter().emit_command(meta) == "adapted"

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        CodexEmitter().emit_command(meta)
        assert CodexEmitter().emit_command(meta) == "skipped"

    def test_skill_md_contains_command_name(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        CodexEmitter().emit_command(meta)
        content = (meta["output_dir"] / "ll-my-cmd" / "SKILL.md").read_text()
        assert "ll-my-cmd" in content

    def test_no_description_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "no-desc", description="")
        assert CodexEmitter().emit_command(meta) == "skipped"


# =============================================================================
# CodexEmitter.emit_agent
# =============================================================================


class TestCodexEmitterEmitAgent:
    def _meta(
        self,
        tmp_path: Path,
        name: str,
        apply: bool = True,
        tools: list[str] | None = None,
        **kwargs: object,
    ) -> dict:
        agent_path = _make_agent(tmp_path, name, tools=tools, **kwargs)
        content = agent_path.read_text()
        fm = _read_frontmatter(content) or {}
        codex_dir = tmp_path / ".codex" / "agents"
        return {
            "agent_name": name,
            "agent_path": agent_path,
            "content": content,
            "fm": fm,
            "output_dir": codex_dir,
            "apply": apply,
            "quiet": True,
        }

    def test_creates_toml_file(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        CodexEmitter().emit_agent(meta)
        assert (meta["output_dir"] / "my-agent.toml").exists()

    def test_toml_starts_with_marker(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        CodexEmitter().emit_agent(meta)
        assert (meta["output_dir"] / "my-agent.toml").read_text().startswith(_MARKER)

    def test_toml_contains_name(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        CodexEmitter().emit_agent(meta)
        assert 'name = "my-agent"' in (meta["output_dir"] / "my-agent.toml").read_text()

    def test_toml_contains_description(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", description="Use for tasks.")
        CodexEmitter().emit_agent(meta)
        assert (
            'description = "Use for tasks."' in (meta["output_dir"] / "my-agent.toml").read_text()
        )

    def test_toml_contains_model(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", model="opus")
        CodexEmitter().emit_agent(meta)
        assert 'model = "opus"' in (meta["output_dir"] / "my-agent.toml").read_text()

    def test_toml_contains_developer_instructions(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", body="Do the thing.")
        CodexEmitter().emit_agent(meta)
        content = (meta["output_dir"] / "my-agent.toml").read_text()
        assert 'developer_instructions = """' in content
        assert "Do the thing." in content

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", apply=False)
        CodexEmitter().emit_agent(meta)
        assert not (meta["output_dir"] / "my-agent.toml").exists()

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        assert CodexEmitter().emit_agent(meta) == "adapted"

    def test_user_authored_file_not_overwritten(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        toml_path = meta["output_dir"] / "my-agent.toml"
        toml_path.parent.mkdir(parents=True, exist_ok=True)
        user_content = '# user authored\nname = "my-agent"\n'
        toml_path.write_text(user_content)
        assert CodexEmitter().emit_agent(meta) == "skipped"
        assert toml_path.read_text() == user_content

    def test_up_to_date_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        CodexEmitter().emit_agent(meta)
        assert CodexEmitter().emit_agent(meta) == "skipped"

    def test_idempotent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        CodexEmitter().emit_agent(meta)
        content1 = (meta["output_dir"] / "my-agent.toml").read_text()
        CodexEmitter().emit_agent(meta)
        assert (meta["output_dir"] / "my-agent.toml").read_text() == content1

    # --- rich TOML fields (ENH-2121 absorbed) ---

    def test_sandbox_mode_read_only_for_read_only_tools(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "reader", tools=["Read", "Glob", "Grep"])
        CodexEmitter().emit_agent(meta)
        assert 'sandbox_mode = "read-only"' in (meta["output_dir"] / "reader.toml").read_text()

    def test_sandbox_mode_write_for_write_tools(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "writer", tools=["Read", "Edit", "Bash"])
        CodexEmitter().emit_agent(meta)
        assert 'sandbox_mode = "write-to-cwd"' in (meta["output_dir"] / "writer.toml").read_text()

    def test_sandbox_mode_omitted_when_no_tools(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agent_md = agents_dir / "no-tools.md"
        agent_md.write_text(
            "---\nname: no-tools\ndescription: |\n  Use when asked.\nmodel: sonnet\n---\n# Body\n"
        )
        content = agent_md.read_text()
        fm = _read_frontmatter(content) or {}
        meta = {
            "agent_name": "no-tools",
            "agent_path": agent_md,
            "content": content,
            "fm": fm,
            "output_dir": tmp_path / ".codex" / "agents",
            "apply": True,
            "quiet": True,
        }
        CodexEmitter().emit_agent(meta)
        toml = (meta["output_dir"] / "no-tools.toml").read_text()
        assert "sandbox_mode" not in toml

    def test_mcp_servers_emitted_for_mcp_tools(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "mcp-agent", tools=["mcp__github__list", "Read"])
        CodexEmitter().emit_agent(meta)
        content = (meta["output_dir"] / "mcp-agent.toml").read_text()
        assert "mcp_servers" in content
        assert "github" in content

    def test_mcp_servers_omitted_when_no_mcp_tools(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "plain", tools=["Read", "WebSearch"])
        CodexEmitter().emit_agent(meta)
        assert "mcp_servers" not in (meta["output_dir"] / "plain.toml").read_text()


# =============================================================================
# GeminiEmitter.emit_skill
# =============================================================================


def _make_skill_with_short_desc(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for tasks.",
    include_name: bool = False,
    include_short_desc: bool = False,
) -> Path:
    """Create a SKILL.md fixture with optional ``name:`` and ``metadata.short-description:``."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"

    name_line = f"name: {name}\n" if include_name else ""
    metadata_block = (
        f"metadata:\n  short-description: {description[:80]}\n" if include_short_desc else ""
    )
    skill_md.write_text(
        f"---\n{name_line}description: {description}\n{metadata_block}---\n\n# Body\n"
    )
    return skill_md


class TestGeminiEmitterEmitSkill:
    def _meta(
        self,
        tmp_path: Path,
        name: str,
        apply: bool = True,
        include_name: bool = False,
        include_short_desc: bool = False,
        description: str = "Use when user asks for tasks.",
    ) -> dict:
        skill_path = _make_skill_with_short_desc(
            tmp_path,
            name,
            description=description,
            include_name=include_name,
            include_short_desc=include_short_desc,
        )
        content = skill_path.read_text()
        fm = _read_frontmatter(content) or {}
        return {
            "skill_name": name,
            "skill_path": skill_path,
            "content": content,
            "fm": fm,
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, name: str) -> Path:
        return tmp_path / ".gemini" / "skills" / name / "SKILL.md"

    def test_writes_to_gemini_skills_dir(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        GeminiEmitter().emit_skill(meta)
        assert self._out_path(tmp_path, "my-skill").exists()

    def test_injects_name_when_absent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=False)
        GeminiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "name: my-skill" in content

    def test_does_not_duplicate_name_when_present(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=True)
        GeminiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert content.count("name: my-skill") == 1

    def test_strips_metadata_short_description(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_short_desc=True)
        GeminiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "short-description:" not in content

    def test_strips_empty_metadata_block(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_short_desc=True)
        GeminiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "metadata:" not in content

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        assert GeminiEmitter().emit_skill(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", apply=False)
        GeminiEmitter().emit_skill(meta)
        assert not self._out_path(tmp_path, "my-skill").exists()

    def test_dry_run_returns_adapted(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", apply=False)
        assert GeminiEmitter().emit_skill(meta) == "adapted"

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        GeminiEmitter().emit_skill(meta)
        assert GeminiEmitter().emit_skill(meta) == "skipped"

    def test_idempotent_no_double_name_insert(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        GeminiEmitter().emit_skill(meta)
        content1 = self._out_path(tmp_path, "my-skill").read_text()
        # Re-run using the already-written output as input
        meta2 = {**meta, "content": content1, "fm": _read_frontmatter(content1) or {}}
        GeminiEmitter().emit_skill(meta2)
        content2 = self._out_path(tmp_path, "my-skill").read_text()
        assert content1 == content2
        assert content2.count("name: my-skill") == 1


# =============================================================================
# GeminiEmitter.emit_command
# =============================================================================


class TestGeminiEmitterEmitCommand:
    def _meta(
        self,
        tmp_path: Path,
        stem: str,
        apply: bool = True,
        description: str = "Run this command.",
        body: str = "# My Command\n\nDo the thing.\n",
    ) -> dict:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(exist_ok=True)
        cmd_md = commands_dir / f"{stem}.md"
        cmd_md.write_text(f"---\ndescription: {description}\n---\n\n{body}")
        content = cmd_md.read_text()
        fm = _read_frontmatter(content) or {}
        return {
            "stem": stem,
            "cmd_path": cmd_md,
            "content": content,
            "fm": fm,
            "output_dir": tmp_path / "skills",  # ignored by GeminiEmitter
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, stem: str) -> Path:
        return tmp_path / ".gemini" / "commands" / f"{stem}.toml"

    def test_writes_to_gemini_commands_dir(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        GeminiEmitter().emit_command(meta)
        assert self._out_path(tmp_path, "my-cmd").exists()

    def test_toml_contains_description(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", description="Run this command.")
        GeminiEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert 'description = "Run this command."' in content

    def test_toml_contains_prompt(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", body="Do the thing.\n")
        GeminiEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "prompt" in content
        assert "Do the thing." in content

    def test_toml_omits_description_when_empty(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", description="")
        GeminiEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "description" not in content
        assert "prompt" in content

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        assert GeminiEmitter().emit_command(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", apply=False)
        GeminiEmitter().emit_command(meta)
        assert not self._out_path(tmp_path, "my-cmd").exists()

    def test_dry_run_returns_adapted(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", apply=False)
        assert GeminiEmitter().emit_command(meta) == "adapted"

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        GeminiEmitter().emit_command(meta)
        assert GeminiEmitter().emit_command(meta) == "skipped"

    def test_skips_when_no_body(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", body="")
        assert GeminiEmitter().emit_command(meta) == "skipped"
        assert not self._out_path(tmp_path, "my-cmd").exists()


# =============================================================================
# GeminiEmitter.emit_agent
# =============================================================================


class TestGeminiEmitterEmitAgent:
    """ENH-2874: degraded-mode inline-role emission (no more raise)."""

    def _meta(self, tmp_path: Path, name: str, apply: bool = True, **kwargs: object) -> dict:
        agent_md = _make_agent(tmp_path, name, **kwargs)  # type: ignore[arg-type]
        return {
            "agent_name": name,
            "agent_path": agent_md,
            "content": agent_md.read_text(),
            "fm": {},
            "output_dir": tmp_path / ".gemini" / "agents",
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, name: str) -> Path:
        return tmp_path / ".gemini" / "agents" / f"{name}.md"

    def test_does_not_raise(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        assert GeminiEmitter().emit_agent(meta) == "adapted"

    def test_writes_degraded_file(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", body="Do the thing.")
        GeminiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "Do the thing." in content

    def test_preamble_has_inline_execution_instruction(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        GeminiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "inline" in content.lower()
        assert "subagent" in content.lower()

    def test_preamble_has_disclosure_requirement(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        GeminiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "disclos" in content.lower()

    def test_body_matches_source_verbatim(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", body="Exact source body text.")
        GeminiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert content.endswith("Exact source body text.")

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", apply=False)
        assert GeminiEmitter().emit_agent(meta) == "adapted"
        assert not self._out_path(tmp_path, "my-agent").exists()

    def test_rerun_with_apply_skips_unchanged(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        GeminiEmitter().emit_agent(meta)
        assert GeminiEmitter().emit_agent(meta) == "skipped"

    def test_user_authored_file_without_marker_is_protected(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        out_path = self._out_path(tmp_path, "my-agent")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("# Hand-authored, no marker\n")
        assert GeminiEmitter().emit_agent(meta) == "skipped"
        assert out_path.read_text() == "# Hand-authored, no marker\n"


# =============================================================================
# resolve_emitter: gemini registration
# =============================================================================


class TestResolveEmitterGemini:
    def test_gemini_returns_gemini_emitter(self) -> None:
        assert isinstance(resolve_emitter("gemini"), GeminiEmitter)

    def test_gemini_emitter_satisfies_protocol(self) -> None:
        assert isinstance(resolve_emitter("gemini"), HostEmitter)


# =============================================================================
# process_agents: degraded-mode routing via the capability map (ENH-2874)
# =============================================================================


class TestProcessAgentsDegradedRouting:
    def test_gemini_writes_one_file_per_source_agent(self, tmp_path: Path) -> None:
        _make_agent(tmp_path, "agent-a")
        _make_agent(tmp_path, "agent-b")
        gemini_dir = tmp_path / ".gemini" / "agents"

        adapted, skipped, errors = process_agents(
            GeminiEmitter(), tmp_path / "agents", gemini_dir, apply=True, quiet=True
        )
        assert adapted == 2
        assert skipped == 0
        assert errors == 0
        assert (gemini_dir / "agent-a.md").exists()
        assert (gemini_dir / "agent-b.md").exists()

    def test_gemini_output_never_calls_native_emit_agent(self, tmp_path: Path) -> None:
        """process_agents must route via the degraded helper, not GeminiEmitter.emit_agent.

        Selection happens by capability flag, not by calling the emitter's
        own method and hoping it degrades — assert that directly by
        breaking the emitter's emit_agent and confirming the traversal
        still succeeds.
        """
        _make_agent(tmp_path, "agent-a")
        gemini_dir = tmp_path / ".gemini" / "agents"

        class ExplodingGeminiEmitter(GeminiEmitter):
            def emit_agent(self, agent_meta: dict) -> str:
                raise AssertionError("emit_agent should not be called for degraded hosts")

        adapted, skipped, errors = process_agents(
            ExplodingGeminiEmitter(), tmp_path / "agents", gemini_dir, apply=True, quiet=True
        )
        assert adapted == 1
        assert errors == 0


# =============================================================================
# Integration guard: real agents (post-apply validation, degraded hosts)
# =============================================================================


class TestRealAgentsDegradedCoverageGuard:
    """After ll-adapt --host gemini --apply, every agents/*.md has a degraded file.

    ``omp`` is explicitly excluded — its emitter is an all-stub (all
    ``emit_*`` raise) with no ``agent_output_format``, so ENH-2874's
    degraded path never selects it; there is no ``.omp/agents/`` coverage
    guard to add here.
    """

    def test_all_real_agents_have_gemini_degraded_files(self) -> None:
        agents_dir = Path(__file__).parent.parent.parent / "agents"
        gemini_agents_dir = Path(__file__).parent.parent.parent / ".gemini" / "agents"
        if not gemini_agents_dir.exists():
            return
        for agent_md in sorted(agents_dir.glob("*.md")):
            agent_name = agent_md.stem
            out_md = gemini_agents_dir / f"{agent_name}.md"
            assert out_md.exists(), (
                f".gemini/agents/{agent_name}.md missing. Run: ll-adapt --host gemini --apply"
            )

    def test_all_real_gemini_agent_files_have_marker(self) -> None:
        gemini_agents_dir = Path(__file__).parent.parent.parent / ".gemini" / "agents"
        if not gemini_agents_dir.exists():
            return
        for out_md in sorted(gemini_agents_dir.glob("*.md")):
            content = out_md.read_text()
            assert content.startswith("<!-- generated by ll-adapt"), (
                f".gemini/agents/{out_md.name}: missing degraded-mode marker comment"
            )

    def test_all_real_gemini_agent_files_have_preamble_requirements(self) -> None:
        gemini_agents_dir = Path(__file__).parent.parent.parent / ".gemini" / "agents"
        if not gemini_agents_dir.exists():
            return
        for out_md in sorted(gemini_agents_dir.glob("*.md")):
            content = out_md.read_text().lower()
            assert "inline" in content, f"{out_md.name}: missing inline-execution instruction"
            assert "disclos" in content, f"{out_md.name}: missing disclosure requirement"


# =============================================================================
# Idempotency: degraded emission (ENH-2874)
# =============================================================================


class TestDegradedAgentIdempotency:
    def test_rerun_with_apply_skips_unchanged(self, tmp_path: Path) -> None:
        _make_agent(tmp_path, "my-agent")
        gemini_dir = tmp_path / ".gemini" / "agents"

        adapted1, skipped1, _ = process_agents(
            GeminiEmitter(), tmp_path / "agents", gemini_dir, apply=True, quiet=True
        )
        assert adapted1 == 1
        assert skipped1 == 0

        adapted2, skipped2, errors2 = process_agents(
            GeminiEmitter(), tmp_path / "agents", gemini_dir, apply=True, quiet=True
        )
        assert adapted2 == 0
        assert skipped2 == 1
        assert errors2 == 0

    def test_changed_source_triggers_rewrite(self, tmp_path: Path) -> None:
        agent_md = _make_agent(tmp_path, "my-agent", body="Original body.")
        gemini_dir = tmp_path / ".gemini" / "agents"
        process_agents(GeminiEmitter(), tmp_path / "agents", gemini_dir, apply=True, quiet=True)

        agent_md.write_text(
            "---\nname: my-agent\ndescription: |\n  Use when user asks for stuff.\n"
            'model: sonnet\ntools: ["Read"]\n---\n\nUpdated body.'
        )

        adapted, skipped, _ = process_agents(
            GeminiEmitter(), tmp_path / "agents", gemini_dir, apply=True, quiet=True
        )
        assert adapted == 1
        assert skipped == 0
        content = (gemini_dir / "my-agent.md").read_text()
        assert "Updated body." in content
        assert "Original body." not in content


# =============================================================================
# Fixture-host registration (ENH-2883 AC #4): map entry + existing serializer,
# no new module under adapters/.
# =============================================================================


class TestFixtureHostRegistration:
    """A brand-new host can be registered through the capability map alone.

    Uses the additive ``patch.dict`` form (precedent:
    ``test_verify_host_map.py``'s ``TestCheckDocParity`` /
    ``TestCheckEmitterAgreement``) to inject one synthetic
    ``HostCapabilityEntry`` under a made-up host key, paired with the
    generic ``_MockEmitter`` (already Protocol-satisfying) as the "existing
    serializer." Proves ``process_skills``/``process_commands``/
    ``process_agents`` need nothing beyond a map entry + an emitter
    instance to support a new host — no ``adapters/fixturehost.py`` required.
    """

    def test_fixture_host_emits_skills_commands_and_agents(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from little_loops.adapters.capabilities import HostCapabilityEntry

        fixture_entry = HostCapabilityEntry(
            host="fixturehost",
            config_dir=".fixturehost",
            skill_output_format="SKILL.md (identity passthrough)",
            command_output_format="SKILL.md (identity passthrough)",
            agent_output_format="Markdown (identity passthrough)",
            frontmatter_fields_read=("description", "name"),
            agents=True,
            commands=True,
            hooks=False,
            subagents="native",
        )

        _make_skill(tmp_path, "fixture-skill")
        _make_command(tmp_path, "fixture-cmd")
        _make_agent(tmp_path, "fixture-agent")

        emitter = _MockEmitter()
        emitter.name = "fixturehost"

        with patch.dict(
            "little_loops.adapters.capabilities.HOST_CAPABILITIES",
            {"fixturehost": fixture_entry},
            clear=False,
        ):
            s_adapted, s_skipped, s_errors = process_skills(
                emitter, tmp_path / "skills", False, True
            )
            c_adapted, c_skipped, c_errors = process_commands(
                emitter, tmp_path / "commands", tmp_path / "skills", False, True
            )
            a_adapted, a_skipped, a_errors = process_agents(
                emitter, tmp_path / "agents", tmp_path / ".fixturehost" / "agents", False, True
            )

        assert (s_adapted, s_skipped, s_errors) == (1, 0, 0)
        assert (c_adapted, c_skipped, c_errors) == (1, 0, 0)
        assert (a_adapted, a_skipped, a_errors) == (1, 0, 0)
        # Native subagents means process_agents calls emitter.emit_agent
        # directly (no degraded-mode routing for this host).
        assert len(emitter.agent_calls) == 1
