"""Tests for adapters.core, adapters.codex (FEAT-2391), and adapters.gemini (FEAT-2392)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.adapters.claude_code import ClaudeCodeEmitter
from little_loops.adapters.codex import _MARKER, CodexEmitter
from little_loops.adapters.core import (
    AdapterError,
    HostEmitter,
    _extract_body,
    _is_model_invocation_disabled,
    _read_frontmatter,
    process_agents,
    process_commands,
    process_mcp_config,
    process_skills,
    resolve_emitter,
)
from little_loops.adapters.gemini import GeminiEmitter
from little_loops.adapters.kimi import KimiEmitter
from little_loops.adapters.omp import OmpEmitter
from little_loops.adapters.qwen import QwenEmitter

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

    def test_omp_returns_omp_emitter(self) -> None:
        assert isinstance(resolve_emitter("omp"), OmpEmitter)

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
        self.mcp_config_calls: list[dict] = []
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

    def emit_mcp_config(self, meta: dict) -> str:
        self.mcp_config_calls.append(meta)
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
# process_mcp_config traversal
# =============================================================================


class TestProcessMcpConfigTraversal:
    def test_calls_emitter_once(self, tmp_path: Path) -> None:
        emitter = _MockEmitter()
        process_mcp_config(emitter, tmp_path / ".codex", False, True)
        assert len(emitter.mcp_config_calls) == 1

    def test_meta_has_required_keys(self, tmp_path: Path) -> None:
        emitter = _MockEmitter()
        process_mcp_config(emitter, tmp_path / ".codex", True, True)
        meta = emitter.mcp_config_calls[0]
        for key in ("output_dir", "apply", "quiet"):
            assert key in meta

    def test_adapter_error_from_emit_mcp_config_counted_as_error(self, tmp_path: Path) -> None:
        class _RaisingEmitter(_MockEmitter):
            def emit_mcp_config(self, meta: dict) -> str:
                raise AdapterError("preview feature")

        emitter = _RaisingEmitter()
        adapted, skipped, errors = process_mcp_config(emitter, tmp_path / ".codex", False, True)
        assert (adapted, skipped, errors) == (0, 0, 1)

    def test_apply_and_dry_run_passthrough(self, tmp_path: Path) -> None:
        emitter = _MockEmitter()
        process_mcp_config(emitter, tmp_path / ".codex", True, False)
        assert emitter.mcp_config_calls[0]["apply"] is True
        assert emitter.mcp_config_calls[0]["quiet"] is False

    def test_buckets_result_string(self, tmp_path: Path) -> None:
        emitter = _MockEmitter(return_value="skipped")
        adapted, skipped, errors = process_mcp_config(emitter, tmp_path / ".codex", False, True)
        assert (adapted, skipped, errors) == (0, 1, 0)


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
# CodexEmitter.emit_mcp_config
# =============================================================================


class TestCodexEmitterEmitMcpConfig:
    def _meta(self, tmp_path: Path, apply: bool = True) -> dict:
        return {
            "output_dir": tmp_path / ".codex",
            "apply": apply,
            "quiet": True,
        }

    def test_creates_toml_file(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        CodexEmitter().emit_mcp_config(meta)
        assert (meta["output_dir"] / "ll-mcp.toml").exists()

    def test_toml_starts_with_marker(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        CodexEmitter().emit_mcp_config(meta)
        assert (meta["output_dir"] / "ll-mcp.toml").read_text().startswith(_MARKER)

    def test_toml_references_ll_mcp(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        CodexEmitter().emit_mcp_config(meta)
        content = (meta["output_dir"] / "ll-mcp.toml").read_text()
        assert 'mcp_servers = ["ll-mcp"]' in content

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, apply=False)
        CodexEmitter().emit_mcp_config(meta)
        assert not (meta["output_dir"] / "ll-mcp.toml").exists()

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        assert CodexEmitter().emit_mcp_config(meta) == "adapted"

    def test_user_authored_file_not_overwritten(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        out_toml = meta["output_dir"] / "ll-mcp.toml"
        out_toml.parent.mkdir(parents=True, exist_ok=True)
        user_content = "# user authored\nmcp_servers = []\n"
        out_toml.write_text(user_content)
        assert CodexEmitter().emit_mcp_config(meta) == "skipped"
        assert out_toml.read_text() == user_content

    def test_up_to_date_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        CodexEmitter().emit_mcp_config(meta)
        assert CodexEmitter().emit_mcp_config(meta) == "skipped"

    def test_idempotent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        CodexEmitter().emit_mcp_config(meta)
        content1 = (meta["output_dir"] / "ll-mcp.toml").read_text()
        CodexEmitter().emit_mcp_config(meta)
        assert (meta["output_dir"] / "ll-mcp.toml").read_text() == content1


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


class TestGeminiEmitterEmitMcpConfig:
    def test_returns_skipped(self, tmp_path: Path) -> None:
        meta = {"output_dir": tmp_path / ".gemini", "apply": True, "quiet": True}
        assert GeminiEmitter().emit_mcp_config(meta) == "skipped"


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

    ``omp`` is explicitly excluded — its ``subagents="native"`` (FEAT-3104)
    means ENH-2874's degraded path never selects it; ``OmpEmitter.emit_agent``
    is a native emitter, not a degraded one, so there is no ``.omp/agents/``
    coverage guard to add here.
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


# =============================================================================
# KimiEmitter.emit_skill (EPIC-2910, FEAT-2916)
# =============================================================================


class TestKimiEmitterEmitSkill:
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
        return tmp_path / ".kimi-code" / "skills" / name / "SKILL.md"

    def test_writes_to_kimi_skills_dir(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        KimiEmitter().emit_skill(meta)
        assert self._out_path(tmp_path, "my-skill").exists()

    def test_injects_name_when_absent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=False)
        KimiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "name: my-skill" in content

    def test_does_not_duplicate_name_when_present(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=True)
        KimiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert content.count("name: my-skill") == 1

    def test_strips_metadata_short_description(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_short_desc=True)
        KimiEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "short-description:" not in content

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        assert KimiEmitter().emit_skill(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", apply=False)
        KimiEmitter().emit_skill(meta)
        assert not self._out_path(tmp_path, "my-skill").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        KimiEmitter().emit_skill(meta)
        assert KimiEmitter().emit_skill(meta) == "skipped"


# =============================================================================
# KimiEmitter.emit_command — bridged into .kimi-code/skills/ll-<stem>/
# =============================================================================


class TestKimiEmitterEmitCommand:
    def _meta(
        self,
        tmp_path: Path,
        stem: str,
        apply: bool = True,
        description: str = "Run this command.",
        body: str = "# My Command\n\nDo the thing with $ARGUMENTS.\n",
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
            "output_dir": tmp_path / "skills",  # ignored by KimiEmitter
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, stem: str) -> Path:
        return tmp_path / ".kimi-code" / "skills" / f"ll-{stem}" / "SKILL.md"

    def test_bridges_into_kimi_skills_dir(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        KimiEmitter().emit_command(meta)
        assert self._out_path(tmp_path, "my-cmd").exists()

    def test_injects_ll_prefixed_name(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        KimiEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "name: ll-my-cmd" in content

    def test_body_passes_through_verbatim(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", body="Do the thing with $ARGUMENTS.\n")
        KimiEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "Do the thing with $ARGUMENTS." in content

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        assert KimiEmitter().emit_command(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", apply=False)
        KimiEmitter().emit_command(meta)
        assert not self._out_path(tmp_path, "my-cmd").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        KimiEmitter().emit_command(meta)
        assert KimiEmitter().emit_command(meta) == "skipped"


# =============================================================================
# KimiEmitter.emit_agent — native Claude-style agent files (no degraded mode)
# =============================================================================


class TestKimiEmitterEmitAgent:
    def _meta(self, tmp_path: Path, name: str, apply: bool = True, **kwargs: object) -> dict:
        agent_md = _make_agent(tmp_path, name, **kwargs)  # type: ignore[arg-type]
        return {
            "agent_name": name,
            "agent_path": agent_md,
            "content": agent_md.read_text(),
            "fm": {},
            "output_dir": tmp_path / ".kimi-code" / "agents",
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, name: str) -> Path:
        return tmp_path / ".kimi-code" / "agents" / f"{name}.md"

    def test_writes_native_agent_file(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", body="Do the thing.")
        KimiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "Do the thing." in content

    def test_not_degraded_no_inline_preamble(self, tmp_path: Path) -> None:
        """kimi spawns real subagents — output must NOT carry the ENH-2874 degraded preamble."""
        meta = self._meta(tmp_path, "my-agent")
        KimiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "degraded mode" not in content
        assert "inline" not in content.lower()

    def test_frontmatter_preserved(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        KimiEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert content.startswith("---\nname: my-agent")

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", apply=False)
        KimiEmitter().emit_agent(meta)
        assert not self._out_path(tmp_path, "my-agent").exists()

    def test_rerun_with_apply_skips_unchanged(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        KimiEmitter().emit_agent(meta)
        assert KimiEmitter().emit_agent(meta) == "skipped"


# =============================================================================
# resolve_emitter: kimi-code registration (suffixed key — see EPIC-2910 naming)
# =============================================================================


class TestResolveEmitterKimi:
    def test_kimi_returns_kimi_emitter(self) -> None:
        assert isinstance(resolve_emitter("kimi-code"), KimiEmitter)

    def test_kimi_emitter_satisfies_protocol(self) -> None:
        assert isinstance(resolve_emitter("kimi-code"), HostEmitter)

    def test_kimi_emitter_name_matches_runner_key(self) -> None:
        """Emitter key equals the host_runner registry key so ll-verify-host-map
        check 2 cross-validates kimi (deliberate break from the un-suffixed
        emitter convention)."""
        from little_loops.host_runner import _HOST_RUNNER_REGISTRY

        assert resolve_emitter("kimi-code").name == "kimi-code"
        assert "kimi-code" in _HOST_RUNNER_REGISTRY

    def test_process_agents_does_not_route_kimi_to_degraded(self, tmp_path: Path) -> None:
        """subagents="native" → process_agents calls emit_agent directly."""
        _make_agent(tmp_path, "agent-a")
        out_dir = tmp_path / ".kimi-code" / "agents"
        adapted, skipped, errors = process_agents(
            KimiEmitter(), tmp_path / "agents", out_dir, True, True
        )
        assert (adapted, skipped, errors) == (1, 0, 0)
        assert "degraded mode" not in (out_dir / "agent-a.md").read_text()


class TestKimiEmitterEmitMcpConfig:
    def test_returns_skipped(self, tmp_path: Path) -> None:
        meta = {"output_dir": tmp_path / ".kimi-code", "apply": True, "quiet": True}
        assert KimiEmitter().emit_mcp_config(meta) == "skipped"


# =============================================================================
# OmpEmitter.emit_agent (FEAT-3104): native, mirrors KimiEmitter.emit_agent
# =============================================================================


class TestOmpEmitterEmitAgent:
    def _meta(self, tmp_path: Path, name: str, apply: bool = True, **kwargs: object) -> dict:
        agent_md = _make_agent(tmp_path, name, **kwargs)  # type: ignore[arg-type]
        return {
            "agent_name": name,
            "agent_path": agent_md,
            "content": agent_md.read_text(),
            "fm": {},
            "output_dir": tmp_path / ".omp" / "agents",
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, name: str) -> Path:
        return tmp_path / ".omp" / "agents" / f"{name}.md"

    def test_writes_native_agent_file(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", body="Do the thing.")
        OmpEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "Do the thing." in content

    def test_not_degraded_no_inline_preamble(self, tmp_path: Path) -> None:
        """omp spawns real subagents — output must NOT carry the ENH-2874 degraded preamble."""
        meta = self._meta(tmp_path, "my-agent")
        OmpEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "degraded mode" not in content
        assert "inline" not in content.lower()

    def test_frontmatter_preserved(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        OmpEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert content.startswith("---\nname: my-agent")

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", apply=False)
        OmpEmitter().emit_agent(meta)
        assert not self._out_path(tmp_path, "my-agent").exists()

    def test_rerun_with_apply_skips_unchanged(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        OmpEmitter().emit_agent(meta)
        assert OmpEmitter().emit_agent(meta) == "skipped"


# =============================================================================
# OmpEmitter.emit_skill (FEAT-3105): native, mirrors KimiEmitter.emit_skill
# =============================================================================


class TestOmpEmitterEmitSkill:
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
        return tmp_path / ".omp" / "skills" / name / "SKILL.md"

    def test_writes_to_omp_skills_dir(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        OmpEmitter().emit_skill(meta)
        assert self._out_path(tmp_path, "my-skill").exists()

    def test_injects_name_when_absent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=False)
        OmpEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "name: my-skill" in content

    def test_does_not_duplicate_name_when_present(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=True)
        OmpEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert content.count("name: my-skill") == 1

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        assert OmpEmitter().emit_skill(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", apply=False)
        OmpEmitter().emit_skill(meta)
        assert not self._out_path(tmp_path, "my-skill").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        OmpEmitter().emit_skill(meta)
        assert OmpEmitter().emit_skill(meta) == "skipped"


# =============================================================================
# OmpEmitter.emit_command (FEAT-3105): flat .omp/commands/<stem>.md
# =============================================================================


class TestOmpEmitterEmitCommand:
    def _meta(
        self,
        tmp_path: Path,
        stem: str,
        apply: bool = True,
        description: str = "Run this command.",
        body: str = "# My Command\n\nDo the thing with $ARGUMENTS.\n",
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
            "output_dir": tmp_path / "skills",  # ignored by OmpEmitter
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, stem: str) -> Path:
        return tmp_path / ".omp" / "commands" / f"{stem}.md"

    def test_writes_flat_command_file(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        OmpEmitter().emit_command(meta)
        assert self._out_path(tmp_path, "my-cmd").exists()

    def test_body_passes_through_verbatim(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", body="Do the thing with $ARGUMENTS.\n")
        OmpEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "Do the thing with $ARGUMENTS." in content

    def test_description_passes_through_verbatim(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", description="A useful command.")
        OmpEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "description: A useful command." in content

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        assert OmpEmitter().emit_command(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", apply=False)
        OmpEmitter().emit_command(meta)
        assert not self._out_path(tmp_path, "my-cmd").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        OmpEmitter().emit_command(meta)
        assert OmpEmitter().emit_command(meta) == "skipped"

    def test_ignores_output_dir(self, tmp_path: Path) -> None:
        """omp self-derives its path (Gemini shape) — output_dir must be unused."""
        meta = self._meta(tmp_path, "my-cmd")
        OmpEmitter().emit_command(meta)
        assert not (tmp_path / "skills").exists()


class TestResolveEmitterOmp:
    def test_omp_returns_omp_emitter(self) -> None:
        assert isinstance(resolve_emitter("omp"), OmpEmitter)

    def test_omp_emitter_satisfies_protocol(self) -> None:
        assert isinstance(resolve_emitter("omp"), HostEmitter)

    def test_process_agents_does_not_route_omp_to_degraded(self, tmp_path: Path) -> None:
        """subagents="native" → process_agents calls emit_agent directly."""
        _make_agent(tmp_path, "agent-a")
        out_dir = tmp_path / ".omp" / "agents"
        adapted, skipped, errors = process_agents(
            OmpEmitter(), tmp_path / "agents", out_dir, True, True
        )
        assert (adapted, skipped, errors) == (1, 0, 0)
        assert "degraded mode" not in (out_dir / "agent-a.md").read_text()


class TestOmpEmitterEmitMcpConfig:
    def test_returns_skipped(self, tmp_path: Path) -> None:
        meta = {"output_dir": tmp_path / ".omp", "apply": True, "quiet": True}
        assert OmpEmitter().emit_mcp_config(meta) == "skipped"


# =============================================================================
# ClaudeCodeEmitter (FEAT-3139)
# =============================================================================


class TestResolveEmitterClaudeCode:
    def test_claude_code_returns_claude_code_emitter(self) -> None:
        assert isinstance(resolve_emitter("claude-code"), ClaudeCodeEmitter)

    def test_claude_code_emitter_satisfies_protocol(self) -> None:
        assert isinstance(resolve_emitter("claude-code"), HostEmitter)


class TestClaudeCodeEmitterStubs:
    def test_emit_skill_returns_skipped(self) -> None:
        assert ClaudeCodeEmitter().emit_skill({}) == "skipped"

    def test_emit_command_returns_skipped(self) -> None:
        assert ClaudeCodeEmitter().emit_command({}) == "skipped"

    def test_emit_agent_returns_skipped(self) -> None:
        assert ClaudeCodeEmitter().emit_agent({}) == "skipped"


class TestClaudeCodeEmitterEmitMcpConfig:
    def _meta(self, tmp_path: Path, apply: bool = True) -> dict:
        return {
            "output_dir": tmp_path,
            "apply": apply,
            "quiet": True,
        }

    def _mcp_path(self, tmp_path: Path) -> Path:
        return tmp_path / ".mcp.json"

    def test_creates_file_when_absent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        ClaudeCodeEmitter().emit_mcp_config(meta)
        assert self._mcp_path(tmp_path).exists()

    def test_written_entry_references_ll_mcp(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        ClaudeCodeEmitter().emit_mcp_config(meta)
        data = json.loads(self._mcp_path(tmp_path).read_text())
        assert data["mcpServers"]["ll-mcp"] == {"command": "ll-mcp"}

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, apply=False)
        ClaudeCodeEmitter().emit_mcp_config(meta)
        assert not self._mcp_path(tmp_path).exists()

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        assert ClaudeCodeEmitter().emit_mcp_config(meta) == "adapted"

    def test_up_to_date_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        ClaudeCodeEmitter().emit_mcp_config(meta)
        assert ClaudeCodeEmitter().emit_mcp_config(meta) == "skipped"

    def test_idempotent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path)
        ClaudeCodeEmitter().emit_mcp_config(meta)
        content1 = self._mcp_path(tmp_path).read_text()
        ClaudeCodeEmitter().emit_mcp_config(meta)
        assert self._mcp_path(tmp_path).read_text() == content1

    def test_merges_into_existing_sibling_entry(self, tmp_path: Path) -> None:
        mcp_path = self._mcp_path(tmp_path)
        mcp_path.write_text(json.dumps({"mcpServers": {"other-server": {"command": "foo"}}}))
        meta = self._meta(tmp_path)
        ClaudeCodeEmitter().emit_mcp_config(meta)
        data = json.loads(mcp_path.read_text())
        assert data["mcpServers"]["other-server"] == {"command": "foo"}
        assert data["mcpServers"]["ll-mcp"] == {"command": "ll-mcp"}

    def test_overwrites_stale_ll_mcp_entry(self, tmp_path: Path) -> None:
        mcp_path = self._mcp_path(tmp_path)
        mcp_path.write_text(json.dumps({"mcpServers": {"ll-mcp": {"command": "old-ll-mcp-path"}}}))
        meta = self._meta(tmp_path)
        result = ClaudeCodeEmitter().emit_mcp_config(meta)
        assert result == "adapted"
        data = json.loads(mcp_path.read_text())
        assert data["mcpServers"]["ll-mcp"] == {"command": "ll-mcp"}

    def test_tolerates_malformed_existing_json(self, tmp_path: Path) -> None:
        mcp_path = self._mcp_path(tmp_path)
        mcp_path.write_text("not valid json")
        meta = self._meta(tmp_path)
        assert ClaudeCodeEmitter().emit_mcp_config(meta) == "adapted"
        data = json.loads(mcp_path.read_text())
        assert data["mcpServers"]["ll-mcp"] == {"command": "ll-mcp"}


# =============================================================================
# QwenEmitter (EPIC-3154, FEAT-3159)
# =============================================================================


class TestQwenEmitterEmitSkill:
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
        return tmp_path / ".qwen" / "skills" / name / "SKILL.md"

    def test_writes_to_qwen_skills_dir(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        QwenEmitter().emit_skill(meta)
        assert self._out_path(tmp_path, "my-skill").exists()

    def test_injects_name_when_absent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=False)
        QwenEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "name: my-skill" in content

    def test_does_not_duplicate_name_when_present(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_name=True)
        QwenEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert content.count("name: my-skill") == 1

    def test_strips_metadata_short_description(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", include_short_desc=True)
        QwenEmitter().emit_skill(meta)
        content = self._out_path(tmp_path, "my-skill").read_text()
        assert "short-description:" not in content

    def test_tolerates_claude_only_frontmatter_keys(self, tmp_path: Path) -> None:
        """FEAT-3155 R7: allowed-tools etc. pass through; qwen tolerates them."""
        skill_md = _make_skill(
            tmp_path,
            "tolerant-skill",
            extra_fm="allowed-tools: read_file, glob\ndisable-model-invocation: false\n",
        )
        content = skill_md.read_text()
        meta = {
            "skill_name": "tolerant-skill",
            "skill_path": skill_md,
            "content": content,
            "fm": _read_frontmatter(content) or {},
            "apply": True,
            "quiet": True,
        }
        QwenEmitter().emit_skill(meta)
        out = self._out_path(tmp_path, "tolerant-skill").read_text()
        assert "allowed-tools: read_file, glob" in out

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        assert QwenEmitter().emit_skill(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill", apply=False)
        QwenEmitter().emit_skill(meta)
        assert not self._out_path(tmp_path, "my-skill").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-skill")
        QwenEmitter().emit_skill(meta)
        assert QwenEmitter().emit_skill(meta) == "skipped"


class TestQwenEmitterSkillCompanions:
    """BUG-3163: emit_skill mirrors ENH-494 companion files alongside SKILL.md."""

    def _meta(self, tmp_path: Path, name: str, apply: bool = True) -> dict:
        skill_md = _make_skill(tmp_path, name)
        content = skill_md.read_text()
        return {
            "skill_name": name,
            "skill_path": skill_md,
            "content": content,
            "fm": _read_frontmatter(content) or {},
            "apply": apply,
            "quiet": True,
        }

    def _mirror_dir(self, tmp_path: Path, name: str) -> Path:
        return tmp_path / ".qwen" / "skills" / name

    def test_companion_files_are_copied(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "my-skill")
        (skill_md.parent / "templates.md").write_text("template body\n")
        (skill_md.parent / "reference.md").write_text("reference body\n")
        QwenEmitter().emit_skill(self._meta(tmp_path, "my-skill"))
        mirror = self._mirror_dir(tmp_path, "my-skill")
        assert (mirror / "templates.md").read_text() == "template body\n"
        assert (mirror / "reference.md").read_text() == "reference body\n"

    def test_codex_only_agents_subtree_not_mirrored(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "my-skill")
        agents_dir = skill_md.parent / "agents"
        agents_dir.mkdir()
        (agents_dir / "openai.yaml").write_text("name: my-skill\n")
        QwenEmitter().emit_skill(self._meta(tmp_path, "my-skill"))
        assert not (self._mirror_dir(tmp_path, "my-skill") / "agents").exists()

    def test_companion_drift_is_repaired(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "my-skill")
        companion = skill_md.parent / "templates.md"
        companion.write_text("v1\n")
        emitter = QwenEmitter()
        assert emitter.emit_skill(self._meta(tmp_path, "my-skill")) == "adapted"
        assert emitter.emit_skill(self._meta(tmp_path, "my-skill")) == "skipped"
        companion.write_text("v2 changed\n")
        assert emitter.emit_skill(self._meta(tmp_path, "my-skill")) == "adapted"
        mirror_file = self._mirror_dir(tmp_path, "my-skill") / "templates.md"
        assert mirror_file.read_text() == "v2 changed\n"

    def test_stale_mirror_companion_is_pruned(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "my-skill")
        companion = skill_md.parent / "obsolete.md"
        companion.write_text("stale\n")
        emitter = QwenEmitter()
        emitter.emit_skill(self._meta(tmp_path, "my-skill"))
        mirror = self._mirror_dir(tmp_path, "my-skill")
        assert (mirror / "obsolete.md").exists()
        companion.unlink()
        assert emitter.emit_skill(self._meta(tmp_path, "my-skill")) == "adapted"
        assert not (mirror / "obsolete.md").exists()

    def test_dry_run_does_not_write_companions(self, tmp_path: Path) -> None:
        skill_md = _make_skill(tmp_path, "my-skill")
        (skill_md.parent / "templates.md").write_text("template body\n")
        result = QwenEmitter().emit_skill(self._meta(tmp_path, "my-skill", apply=False))
        assert result == "adapted"
        assert not (self._mirror_dir(tmp_path, "my-skill") / "templates.md").exists()


class TestQwenEmitterEmitCommand:
    def _meta(
        self,
        tmp_path: Path,
        stem: str,
        apply: bool = True,
        description: str = "Run this command.",
        body: str = "# My Command\n\nDo the thing with $ARGUMENTS.\n",
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
            "output_dir": tmp_path / "skills",  # ignored by QwenEmitter
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, stem: str) -> Path:
        return tmp_path / ".qwen" / "commands" / "ll" / f"{stem}.md"

    def test_writes_to_native_namespaced_commands_dir(self, tmp_path: Path) -> None:
        """FEAT-3155: .qwen/commands/ll/<stem>.md resolves as /ll:<stem>."""
        meta = self._meta(tmp_path, "my-cmd")
        QwenEmitter().emit_command(meta)
        assert self._out_path(tmp_path, "my-cmd").exists()

    def test_rewrites_arguments_to_args_placeholder(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", body="Do the thing with $ARGUMENTS.\n")
        QwenEmitter().emit_command(meta)
        content = self._out_path(tmp_path, "my-cmd").read_text()
        assert "$ARGUMENTS" not in content
        assert "{{args}}" in content

    def test_carries_description_frontmatter_only(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir(exist_ok=True)
        cmd_md = commands_dir / "rich.md"
        cmd_md.write_text(
            "---\ndescription: Rich command.\nargument-hint: '[x]'\n"
            "allowed-tools:\n  - Read\n---\n\nBody.\n"
        )
        content = cmd_md.read_text()
        meta = {
            "stem": "rich",
            "cmd_path": cmd_md,
            "content": content,
            "fm": _read_frontmatter(content) or {},
            "output_dir": tmp_path / "skills",
            "apply": True,
            "quiet": True,
        }
        QwenEmitter().emit_command(meta)
        out = self._out_path(tmp_path, "rich").read_text()
        assert "description: Rich command." in out
        assert "argument-hint" not in out
        assert "allowed-tools" not in out

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        assert QwenEmitter().emit_command(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd", apply=False)
        QwenEmitter().emit_command(meta)
        assert not self._out_path(tmp_path, "my-cmd").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-cmd")
        QwenEmitter().emit_command(meta)
        assert QwenEmitter().emit_command(meta) == "skipped"


class TestQwenEmitterEmitAgent:
    def _meta(self, tmp_path: Path, name: str, apply: bool = True) -> dict:
        agent_md = _make_agent(tmp_path, name)
        content = agent_md.read_text()
        fm = _read_frontmatter(content) or {}
        return {
            "agent_name": name,
            "agent_path": agent_md,
            "content": content,
            "fm": fm,
            "output_dir": tmp_path / ".qwen" / "agents",
            "apply": apply,
            "quiet": True,
        }

    def _out_path(self, tmp_path: Path, name: str) -> Path:
        return tmp_path / ".qwen" / "agents" / f"{name}.md"

    def test_writes_native_markdown_agent(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        QwenEmitter().emit_agent(meta)
        assert self._out_path(tmp_path, "my-agent").exists()

    def test_claude_frontmatter_passes_through_verbatim(self, tmp_path: Path) -> None:
        """Qwen documents CC 2.1.168 frontmatter compat; agents emit verbatim."""
        meta = self._meta(tmp_path, "my-agent")
        QwenEmitter().emit_agent(meta)
        content = self._out_path(tmp_path, "my-agent").read_text()
        assert "name: my-agent" in content
        assert "model: sonnet" in content
        assert "Agent instructions." in content

    def test_returns_adapted_on_first_run(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        assert QwenEmitter().emit_agent(meta) == "adapted"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent", apply=False)
        QwenEmitter().emit_agent(meta)
        assert not self._out_path(tmp_path, "my-agent").exists()

    def test_already_adapted_returns_skipped(self, tmp_path: Path) -> None:
        meta = self._meta(tmp_path, "my-agent")
        QwenEmitter().emit_agent(meta)
        assert QwenEmitter().emit_agent(meta) == "skipped"


class TestResolveEmitterQwen:
    def test_qwen_returns_qwen_emitter(self) -> None:
        assert isinstance(resolve_emitter("qwen"), QwenEmitter)

    def test_qwen_emitter_name_matches_runner_key(self) -> None:
        """One key at every seam (EPIC-3154 naming decision)."""
        from little_loops.host_runner import _HOST_RUNNER_REGISTRY

        assert QwenEmitter().name == "qwen"
        assert "qwen" in _HOST_RUNNER_REGISTRY


class TestQwenEmitterEmitMcpConfig:
    def test_mcp_stub_returns_skipped(self, tmp_path: Path) -> None:
        meta = {"output_dir": tmp_path, "apply": True, "quiet": True}
        assert QwenEmitter().emit_mcp_config(meta) == "skipped"
