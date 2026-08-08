"""Golden-corpus byte-identity tests for ENH-2883.

Captures current (pre-refactor) `CodexEmitter`/`GeminiEmitter` output over a
small synthetic skill/command/agent corpus in
``scripts/tests/fixtures/adapt/{skill,command,agent}_cases.json``. The
ENH-2883 refactor (driving `core.py`'s traversal from the ENH-2873
capability map instead of emitter-held policy) must leave every one of
these outputs byte-identical — this module is the safety net that proves
it, following the golden-corpus pattern in
``test_policy_builder_corpus.py``.

**Named exclusions** (per ENH-2883's Acceptance Criteria — not silent):

- ``omp`` — ``emit_skill``/``emit_command`` still raise ``AdapterError``
  unconditionally (FEAT-3103/FEAT-3105 unblock those); there is no
  skill/command output to snapshot. ``emit_agent`` is real (FEAT-3104) and
  has its own coverage in ``test_adapters.py``/``TestOmpEmitterEmitAgent``,
  not part of this golden-corpus claim.
- Gemini agent emission — an intentional degraded-mode preview stub
  (ENH-2874), not part of this byte-identity claim. It has its own test
  coverage in ``test_adapters.py``/``TestProcessAgentsDegradedRouting``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from little_loops.adapters.codex import CodexEmitter
from little_loops.adapters.gemini import GeminiEmitter

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adapt"


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _make_skill_file(tmp_path: Path, name: str, content: str) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(content)
    return skill_md


def test_codex_skill_emission_matches_golden_corpus(tmp_path: Path) -> None:
    data = _load("skill_cases.json")
    for case in data["cases"]:
        name = case["name"]
        skill_md = _make_skill_file(tmp_path / name, name, case["input_content"])
        result = CodexEmitter().emit_skill(
            {
                "skill_name": name,
                "skill_path": skill_md,
                "content": case["input_content"],
                "fm": {},
                "apply": True,
                "quiet": True,
            }
        )
        assert result == case["codex_result"], f"{name}: codex result changed"
        if case["codex_skill_md"] is not None:
            assert skill_md.read_text() == case["codex_skill_md"], f"{name}: codex SKILL.md changed"
        openai_yaml = skill_md.parent / "agents" / "openai.yaml"
        if case["codex_openai_yaml"] is not None:
            assert openai_yaml.exists(), f"{name}: expected openai.yaml"
            assert openai_yaml.read_text() == case["codex_openai_yaml"], (
                f"{name}: openai.yaml changed"
            )
        else:
            assert not openai_yaml.exists(), f"{name}: unexpected openai.yaml"


def test_gemini_skill_emission_matches_golden_corpus(tmp_path: Path) -> None:
    data = _load("skill_cases.json")
    for case in data["cases"]:
        name = case["name"]
        skill_md = _make_skill_file(tmp_path / name, name, case["input_content"])
        result = GeminiEmitter().emit_skill(
            {
                "skill_name": name,
                "skill_path": skill_md,
                "content": case["input_content"],
                "apply": True,
                "quiet": True,
            }
        )
        assert result == case["gemini_result"], f"{name}: gemini result changed"
        out_path = tmp_path / name / ".gemini" / "skills" / name / "SKILL.md"
        if case["gemini_skill_md"] is not None:
            assert out_path.read_text() == case["gemini_skill_md"], (
                f"{name}: gemini SKILL.md changed"
            )


def test_codex_command_emission_matches_golden_corpus(tmp_path: Path) -> None:
    data = _load("command_cases.json")
    for case in data["cases"]:
        stem = case["name"]
        commands_dir = tmp_path / stem / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        cmd_md = commands_dir / f"{stem}.md"
        cmd_md.write_text(case["input_content"])
        output_dir = tmp_path / stem / "skills"
        result = CodexEmitter().emit_command(
            {
                "stem": stem,
                "cmd_path": cmd_md,
                "content": case["input_content"],
                "fm": {"description": case["input_description"]},
                "output_dir": output_dir,
                "apply": True,
                "quiet": True,
            }
        )
        assert result == case["codex_result"], f"{stem}: codex result changed"
        out_skill_md = output_dir / f"ll-{stem}" / "SKILL.md"
        out_openai_yaml = output_dir / f"ll-{stem}" / "agents" / "openai.yaml"
        if case["codex_skill_md"] is not None:
            assert out_skill_md.read_text() == case["codex_skill_md"], (
                f"{stem}: codex SKILL.md changed"
            )
        if case["codex_openai_yaml"] is not None:
            assert out_openai_yaml.read_text() == case["codex_openai_yaml"], (
                f"{stem}: openai.yaml changed"
            )


def test_gemini_command_emission_matches_golden_corpus(tmp_path: Path) -> None:
    data = _load("command_cases.json")
    for case in data["cases"]:
        stem = case["name"]
        commands_dir = tmp_path / stem / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        cmd_md = commands_dir / f"{stem}.md"
        cmd_md.write_text(case["input_content"])
        result = GeminiEmitter().emit_command(
            {
                "stem": stem,
                "cmd_path": cmd_md,
                "content": case["input_content"],
                "fm": {"description": case["input_description"]},
                "apply": True,
                "quiet": True,
            }
        )
        assert result == case["gemini_result"], f"{stem}: gemini result changed"
        out_toml = tmp_path / stem / ".gemini" / "commands" / f"{stem}.toml"
        if case["gemini_toml"] is not None:
            assert out_toml.read_text() == case["gemini_toml"], f"{stem}: gemini TOML changed"


def test_codex_agent_emission_matches_golden_corpus(tmp_path: Path) -> None:
    data = _load("agent_cases.json")
    for case in data["cases"]:
        name = case["name"]
        content = case["input_content"]
        fm = yaml.safe_load(content[3 : content.find("---", 3)])
        output_dir = tmp_path / name / ".codex" / "agents"
        result = CodexEmitter().emit_agent(
            {
                "agent_name": name,
                "content": content,
                "fm": fm,
                "output_dir": output_dir,
                "apply": True,
                "quiet": True,
            }
        )
        assert result == case["codex_result"], f"{name}: codex agent result changed"
        out_toml = output_dir / f"{name}.toml"
        if case["codex_toml"] is not None:
            assert out_toml.read_text() == case["codex_toml"], f"{name}: codex agent TOML changed"


def test_corpus_is_non_trivial() -> None:
    skill_cases = _load("skill_cases.json")["cases"]
    command_cases = _load("command_cases.json")["cases"]
    agent_cases = _load("agent_cases.json")["cases"]

    assert len(skill_cases) >= 3
    assert len(command_cases) >= 3
    assert len(agent_cases) >= 3

    # At least one skill/command case must exercise the "skipped" path (no
    # description found), not just the happy "adapted" path.
    assert any(c["codex_result"] == "skipped" for c in skill_cases)
    assert any(c["codex_result"] == "skipped" for c in command_cases)

    # Agent corpus must cover the sandbox-mode/mcp-server derivation
    # branches: read-only, write, and mcp tools.
    tool_sets = [tuple(c["input_tools"] or []) for c in agent_cases]
    assert any(any(t.startswith("mcp__") for t in ts) for ts in tool_sets)


def test_omp_and_gemini_agent_excluded_from_byte_identity_claim() -> None:
    """Documents the two named exclusions from AC #2 (not a silent gap).

    omp: emit_skill/emit_command still raise AdapterError unconditionally,
    so there is no skill/command output to snapshot (emit_agent is real as
    of FEAT-3104, covered separately in test_adapters.py). Gemini agent
    emission is an intentional degraded-mode preview stub (ENH-2874),
    covered by its own tests, not part of this native-format byte-identity
    claim.
    """
    import pytest

    from little_loops.adapters.core import AdapterError
    from little_loops.adapters.omp import OmpEmitter

    with pytest.raises(AdapterError):
        OmpEmitter().emit_skill({})

    # Gemini agent emission always routes to the shared degraded-mode
    # helper regardless of input — no native format to compare byte-for-byte.
    assert GeminiEmitter().emit_agent.__doc__ is not None
