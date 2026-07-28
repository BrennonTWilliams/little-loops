"""Tests for ll-verify-host-map (ENH-2873)."""

from unittest.mock import patch

from little_loops.adapters.capabilities import HOST_CAPABILITIES, HostCapabilityEntry
from little_loops.cli.verify_host_map import (
    _adapter_section_hosts,
    _check_doc_parity,
    _check_emitter_agreement,
    _check_runtime_contradiction,
    _host_compat_md_path,
    _run,
    main_verify_host_map,
)


class TestHostCapabilities:
    def test_keys_match_emitter_map(self) -> None:
        from little_loops.adapters.core import _EMITTER_MAP

        assert set(HOST_CAPABILITIES) == set(_EMITTER_MAP)

    def test_gemini_agents_true_matches_degraded_emission(self) -> None:
        # ENH-2874: GeminiEmitter.emit_agent no longer raises — it produces
        # degraded-mode inline-role output, so agents=True now agrees with
        # the emitter's actual behavior. subagents stays "none" (no native
        # spawn support), with agent_output_format describing the degraded
        # format.
        entry = HOST_CAPABILITIES["gemini"]
        assert entry.agents is True
        assert entry.subagents == "none"
        assert entry.agent_output_format is not None

    def test_omp_fully_unimplemented(self) -> None:
        entry = HOST_CAPABILITIES["omp"]
        assert entry.agents is False
        assert entry.commands is False


class TestAdapterSectionHosts:
    def test_finds_documented_hosts(self) -> None:
        hosts = _adapter_section_hosts(_host_compat_md_path())
        assert hosts == {"codex", "gemini", "omp"}


class TestCheckDocParity:
    def test_current_tree_has_no_mismatch(self) -> None:
        assert _check_doc_parity(_host_compat_md_path()) == []

    def test_flags_map_entry_missing_from_doc(self, tmp_path) -> None:
        doc = tmp_path / "HOST_COMPATIBILITY.md"
        doc.write_text("## Adapter Host Capabilities\n\n| Host | X |\n| - | - |\n| gemini | y |\n")
        with patch.dict(
            "little_loops.cli.verify_host_map.HOST_CAPABILITIES",
            {"codex": HOST_CAPABILITIES["codex"], "gemini": HOST_CAPABILITIES["gemini"]},
            clear=True,
        ):
            errors = _check_doc_parity(doc)
        assert any("codex" in e for e in errors)


class TestCheckRuntimeContradiction:
    def test_current_tree_has_no_contradiction(self) -> None:
        assert _check_runtime_contradiction() == []


class TestCheckEmitterAgreement:
    def test_current_tree_agrees(self) -> None:
        assert _check_emitter_agreement() == []

    def test_flags_gemini_agents_true_with_no_output_format(self) -> None:
        # agents=True under subagents="none" with no agent_output_format:
        # the degraded path has nowhere to write.
        bad_map = dict(HOST_CAPABILITIES)
        bad_map["gemini"] = HostCapabilityEntry(
            host="gemini",
            config_dir=".gemini",
            skill_output_format="SKILL.md",
            command_output_format="TOML",
            agent_output_format=None,
            agents=True,
            subagents="none",
        )
        with patch("little_loops.cli.verify_host_map.HOST_CAPABILITIES", bad_map):
            errors = _check_emitter_agreement()
        assert any("gemini" in e for e in errors)

    def test_flags_gemini_native_subagents_with_agents_false(self) -> None:
        # subagents="native" implies the host can spawn, so agents=False
        # would mean it's declared to emit nothing despite native support.
        bad_map = dict(HOST_CAPABILITIES)
        bad_map["gemini"] = HostCapabilityEntry(
            host="gemini",
            config_dir=".gemini",
            skill_output_format="SKILL.md",
            command_output_format="TOML",
            agent_output_format="TOML",
            agents=False,
            subagents="native",
        )
        with patch("little_loops.cli.verify_host_map.HOST_CAPABILITIES", bad_map):
            errors = _check_emitter_agreement()
        assert any("gemini" in e for e in errors)


class TestRun:
    def test_clean_state_returns_zero(self) -> None:
        exit_code, errors = _run()
        assert exit_code == 0
        assert errors == []


class TestMainVerifyHostMap:
    def test_clean_state_returns_zero(self) -> None:
        with patch("sys.argv", ["ll-verify-host-map"]):
            assert main_verify_host_map() == 0

    def test_dirty_state_returns_one_with_error(self, capsys) -> None:
        with (
            patch("sys.argv", ["ll-verify-host-map"]),
            patch(
                "little_loops.cli.verify_host_map._check_emitter_agreement",
                return_value=["synthetic drift for test"],
            ),
        ):
            ret = main_verify_host_map()
        captured = capsys.readouterr()
        assert ret == 1
        assert "synthetic drift for test" in captured.err
