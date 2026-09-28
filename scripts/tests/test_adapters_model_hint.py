"""Tests for frontmatter ``model_hint`` handling in the adapters (ENH-3533)."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.adapters.core import (
    AdapterError,
    _read_frontmatter,
    _resolve_frontmatter_model,
    _select_frontmatter_fields,
    _validate_model_decl,
    process_agents,
    process_commands,
    process_skills,
    resolve_emitter,
)
from little_loops.host_runner import (
    _BUILTIN_HINT_MAPPINGS,
    MODEL_HINTS,
    ModelHintError,
    ModelHintUnmappedError,
    resolve_model_hint,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _agent(root: Path, name: str, fm_extra: str = "") -> Path:
    agents = root / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / f"{name}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: |\n  Does {name} things.\n{fm_extra}---\n\nBody.\n"
    )
    return path


def _skill(root: Path, name: str, fm_extra: str = "") -> Path:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(f"---\ndescription: Use when doing {name}.\n{fm_extra}---\n\n# {name}\n")
    return path


class TestModelHintUnmappedError:
    def test_missing_mapping_raises_subclass(self) -> None:
        with pytest.raises(ModelHintUnmappedError):
            resolve_model_hint("coding", backend="codex")

    @pytest.mark.parametrize(
        ("hint", "backend"),
        [("bogus", "claude-code"), ("coding", "nonesuch"), ("coding", "opencode")],
    )
    def test_other_failures_are_plain_model_hint_errors(self, hint: str, backend: str) -> None:
        with pytest.raises(ModelHintError) as exc:
            resolve_model_hint(hint, backend=backend)
        assert not isinstance(exc.value, ModelHintUnmappedError)

    def test_config_disabled_is_plain_error(self) -> None:
        with pytest.raises(ModelHintError) as exc:
            resolve_model_hint(
                "coding", backend="claude-code", overrides={"claude-code": {"coding": False}}
            )
        assert not isinstance(exc.value, ModelHintUnmappedError)


class TestValidateModelDecl:
    def test_no_hint_is_valid(self) -> None:
        _validate_model_decl({"model": "sonnet"})
        _validate_model_decl({})

    def test_hint_without_pin_is_valid(self) -> None:
        _validate_model_decl({"model_hint": "coding"})

    @pytest.mark.parametrize("pin", ["sonnet", "Sonnet", " sonnet "])
    def test_agreeing_pin_is_valid(self, pin: str) -> None:
        _validate_model_decl({"model_hint": "coding", "model": pin})

    def test_unknown_hint_is_error(self) -> None:
        with pytest.raises(AdapterError, match="unknown model_hint"):
            _validate_model_decl({"model_hint": "turbo"})

    @pytest.mark.parametrize(
        "pin", ["haiku", "opus", "claude-sonnet-5", "claude-sonnet-5-5", "inherit"]
    )
    def test_disagreeing_pin_is_error(self, pin: str) -> None:
        with pytest.raises(AdapterError, match="disagrees"):
            _validate_model_decl({"model_hint": "coding", "model": pin})


class TestResolveFrontmatterModel:
    def test_no_hint_claude_alias_omitted(self) -> None:
        assert _resolve_frontmatter_model({"model": "sonnet"}, "codex") is None

    def test_no_hint_literal_passes_through(self) -> None:
        assert _resolve_frontmatter_model({"model": "gpt-5-codex"}, "codex") == "gpt-5-codex"

    def test_unmapped_omits_and_records(self) -> None:
        from collections import Counter

        omissions: Counter[tuple[str, str]] = Counter()
        assert _resolve_frontmatter_model({"model_hint": "coding"}, "codex", omissions) is None
        assert omissions == {("codex", "coding"): 1}

    def test_mapped_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(_BUILTIN_HINT_MAPPINGS, "codex", {h: f"x-{h}" for h in MODEL_HINTS})
        assert _resolve_frontmatter_model({"model_hint": "burst"}, "codex") == "x-burst"

    def test_unknown_backend_is_adapter_error(self) -> None:
        with pytest.raises(AdapterError):
            _resolve_frontmatter_model({"model_hint": "coding"}, "nonesuch")

    def test_ignores_config_overrides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / ".ll"
        cfg.mkdir()
        (cfg / "ll-config.json").write_text(
            '{"orchestration": {"model_hints": {"codex": {"coding": "from-config"}}}}'
        )
        monkeypatch.chdir(tmp_path)
        assert _resolve_frontmatter_model({"model_hint": "coding"}, "codex") is None


class TestSelectFrontmatterFieldsModelHint:
    CONTENT = "---\nname: a\nmodel: sonnet\nmodel_hint: coding\n---\n\nBody.\n"

    def test_hint_and_alias_stripped(self) -> None:
        new, changed = _select_frontmatter_fields(self.CONTENT, "a", ("name",))
        assert "model" not in new
        assert changed is True

    def test_resolved_model_written(self) -> None:
        new, _ = _select_frontmatter_fields(self.CONTENT, "a", ("name",), resolved_model="x-coding")
        fm = _read_frontmatter(new)
        assert fm == {"name": "a", "model": "x-coding"}
        assert new.endswith("---\n\nBody.\n")

    def test_strip_model_false_keeps_pin_and_hint(self) -> None:
        new, changed = _select_frontmatter_fields(self.CONTENT, "a", ("name",), strip_model=False)
        assert new == self.CONTENT
        assert changed is False


class TestProcessAgentsModelHint:
    def test_codex_unmapped_omits_model_and_warns_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        hint = "model_hint: coding\nmodel: sonnet\n"
        _agent(tmp_path, "one", hint)
        _agent(tmp_path, "two", hint)
        out = tmp_path / ".codex" / "agents"
        result = process_agents(resolve_emitter("codex"), tmp_path / "agents", out, True, False)
        assert result == (2, 0, 0)
        assert "model" not in (out / "one.toml").read_text().replace("developer", "")
        err = capsys.readouterr().err
        assert err.count("WARN") == 1
        assert "'coding'" in err and "codex" in err and "2 agents" in err

    def test_quiet_suppresses_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _agent(tmp_path, "one", "model_hint: coding\n")
        process_agents(resolve_emitter("codex"), tmp_path / "agents", tmp_path / "o", True, True)
        assert capsys.readouterr().err == ""

    def test_codex_mapped_writes_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setitem(_BUILTIN_HINT_MAPPINGS, "codex", {h: f"x-{h}" for h in MODEL_HINTS})
        _agent(tmp_path, "one", "model_hint: reasoning\nmodel: opus\n")
        out = tmp_path / "o"
        process_agents(resolve_emitter("codex"), tmp_path / "agents", out, True, False)
        assert 'model = "x-reasoning"' in (out / "one.toml").read_text()
        assert capsys.readouterr().err == ""

    def test_unknown_hint_is_counted_error(self, tmp_path: Path) -> None:
        _agent(tmp_path, "bad", "model_hint: turbo\n")
        result = process_agents(
            resolve_emitter("codex"), tmp_path / "agents", tmp_path / "o", True, True
        )
        assert result == (0, 0, 1)

    def test_pin_mismatch_is_counted_error(self, tmp_path: Path) -> None:
        _agent(tmp_path, "bad", "model_hint: coding\nmodel: haiku\n")
        result = process_agents(
            resolve_emitter("kimi-code"), tmp_path / "agents", tmp_path / "o", True, True
        )
        assert result == (0, 0, 1)

    @pytest.mark.parametrize("host", ["kimi-code", "qwen", "omp"])
    def test_native_agent_mirrors_strip_hint_and_emit_no_model(
        self, tmp_path: Path, host: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _agent(tmp_path, "one", "model_hint: coding\nmodel: sonnet\n")
        out = tmp_path / "o"
        assert process_agents(resolve_emitter(host), tmp_path / "agents", out, True, False) == (
            1,
            0,
            0,
        )
        text = (out / "one.md").read_text()
        assert "model" not in text.split("---")[1]
        assert capsys.readouterr().err == ""  # host doesn't read `model`: no warning

    def test_gemini_degraded_agent_carries_no_model(self, tmp_path: Path) -> None:
        _agent(tmp_path, "one", "model_hint: coding\nmodel: sonnet\n")
        out = tmp_path / "o"
        assert process_agents(resolve_emitter("gemini"), tmp_path / "agents", out, True, True) == (
            1,
            0,
            0,
        )
        text = (out / "one.md").read_text()
        assert "model_hint" not in text and "model:" not in text

    @pytest.mark.parametrize("host", ["kimi-code", "qwen", "omp"])
    def test_resolved_model_written_when_host_reads_model(
        self, tmp_path: Path, host: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = HOST_CAPABILITIES[host]
        monkeypatch.setitem(_BUILTIN_HINT_MAPPINGS, host, {h: f"x-{h}" for h in MODEL_HINTS})
        monkeypatch.setitem(
            HOST_CAPABILITIES,
            host,
            type(entry)(
                **{
                    **entry.__dict__,
                    "frontmatter_fields_read": (*entry.frontmatter_fields_read, "model"),
                }
            ),
        )
        _agent(tmp_path, "one", "model_hint: coding\nmodel: sonnet\n")
        out = tmp_path / "o"
        process_agents(resolve_emitter(host), tmp_path / "agents", out, True, True)
        fm = _read_frontmatter((out / "one.md").read_text()) or {}
        assert fm["model"] == "x-coding"
        assert "model_hint" not in fm


class TestProcessSkillsModelHint:
    @pytest.mark.parametrize("host", ["gemini", "kimi-code", "qwen", "omp"])
    def test_mirror_strips_hint_and_pin_without_warning(
        self, tmp_path: Path, host: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(tmp_path, "s", "model_hint: coding\nmodel: sonnet\n")
        assert process_skills(resolve_emitter(host), tmp_path / "skills", True, False) == (1, 0, 0)
        mirror = tmp_path / HOST_CAPABILITIES[host].config_dir / "skills" / "s" / "SKILL.md"
        assert "model" not in mirror.read_text().split("---")[1]
        assert capsys.readouterr().err == ""

    def test_gate_opens_when_host_reads_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = HOST_CAPABILITIES["qwen"]
        monkeypatch.setitem(_BUILTIN_HINT_MAPPINGS, "qwen", {h: f"x-{h}" for h in MODEL_HINTS})
        monkeypatch.setitem(
            HOST_CAPABILITIES,
            "qwen",
            type(entry)(
                **{
                    **entry.__dict__,
                    "frontmatter_fields_read": (*entry.frontmatter_fields_read, "model"),
                }
            ),
        )
        _skill(tmp_path, "s", "model_hint: burst\nmodel: haiku\n")
        process_skills(resolve_emitter("qwen"), tmp_path / "skills", True, True)
        fm = _read_frontmatter((tmp_path / ".qwen/skills/s/SKILL.md").read_text()) or {}
        assert fm["model"] == "x-burst"

    def test_codex_skill_rewrite_keeps_source_pin_and_hint(self, tmp_path: Path) -> None:
        path = _skill(tmp_path, "s", "model_hint: coding\nmodel: sonnet\n")
        process_skills(resolve_emitter("codex"), tmp_path / "skills", True, True)
        fm = _read_frontmatter(path.read_text()) or {}
        assert fm["model_hint"] == "coding" and fm["model"] == "sonnet"

    def test_invalid_hint_on_disabled_skill_still_errors(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "model_hint: turbo\ndisable-model-invocation: true\n")
        result = process_skills(resolve_emitter("qwen"), tmp_path / "skills", True, True)
        assert result == (0, 0, 1)

    def test_unknown_hint_is_counted_error(self, tmp_path: Path) -> None:
        _skill(tmp_path, "s", "model_hint: turbo\n")
        assert process_skills(resolve_emitter("gemini"), tmp_path / "skills", True, True) == (
            0,
            0,
            1,
        )


class TestCommandMirrorsNeverEmitHint:
    @pytest.mark.parametrize("host", ["codex", "gemini", "kimi-code", "qwen", "omp"])
    def test_hint_not_in_command_mirror(self, tmp_path: Path, host: str) -> None:
        cmds = tmp_path / "commands"
        cmds.mkdir()
        (cmds / "c.md").write_text(
            "---\ndescription: Run the thing.\nmodel_hint: coding\n---\n\nDo it.\n"
        )
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        result = process_commands(resolve_emitter(host), cmds, skills_dir, True, True)
        assert result[2] == 0
        written = [p for p in tmp_path.rglob("*") if p.is_file() and p.parent != cmds]
        assert written
        assert all("model_hint" not in p.read_text() for p in written)


class TestRealTreeModelDecls:
    """In-repo gate: every shipped agent/skill declares a valid hint + agreeing pin."""

    def _files(self) -> list[Path]:
        return sorted(PROJECT_ROOT.glob("agents/*.md")) + sorted(
            PROJECT_ROOT.glob("skills/*/SKILL.md")
        )

    def test_shipped_declarations_are_valid_and_pinned(self) -> None:
        for path in self._files():
            fm = _read_frontmatter(path.read_text()) or {}
            _validate_model_decl(fm)
            if fm.get("model_hint") is not None:
                assert fm.get("model") is not None, f"{path}: model_hint needs a Claude pin"
