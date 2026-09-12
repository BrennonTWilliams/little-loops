"""Tests for ll-verify-host-map (ENH-2873, runtime half ENH-3453)."""

import dataclasses
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
from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    RUNTIME_HOST_CAPABILITIES,
    TEST_ONLY_HOSTS,
    CapabilityEntry,
    HostCapabilities,
    RuntimeHostEntry,
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

    def test_omp_agents_true_matches_native_emission(self) -> None:
        # FEAT-3104: OmpEmitter.emit_agent is real (native, mirroring Kimi's
        # shape) — agents=True and subagents="native" now agree with the
        # emitter's actual behavior. FEAT-3105: emit_skill/emit_command are
        # also real now, so commands=True with a set command_output_format.
        entry = HOST_CAPABILITIES["omp"]
        assert entry.agents is True
        assert entry.subagents == "native"
        assert entry.agent_output_format is not None
        assert entry.commands is True
        assert entry.command_output_format is not None
        assert entry.skill_output_format is not None


class TestAdapterSectionHosts:
    def test_finds_documented_hosts(self) -> None:
        hosts = _adapter_section_hosts(_host_compat_md_path())
        assert hosts == {"codex", "gemini", "omp", "kimi-code", "claude-code", "qwen"}


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

    def test_runtime_registry_key_parity(self) -> None:
        # Mirrors TestHostCapabilities::test_keys_match_emitter_map above —
        # the runtime map is a strict superset covering every registry host
        # (opencode/pi included), unlike the build-time map. TEST_ONLY_HOSTS
        # (FEAT-3454) are exempt: they source capabilities from their own
        # constructor, not this map.
        assert set(RUNTIME_HOST_CAPABILITIES) == set(_HOST_RUNNER_REGISTRY) - TEST_ONLY_HOSTS

    def test_flags_missing_runtime_entry(self) -> None:
        bad_map = dict(RUNTIME_HOST_CAPABILITIES)
        del bad_map["gemini"]
        with patch("little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES", bad_map):
            errors = _check_runtime_contradiction()
        assert any("missing runtime entry for 'gemini'" in e for e in errors)

    def test_flags_flags_identity_mismatch(self) -> None:
        bad_map = dict(RUNTIME_HOST_CAPABILITIES)
        real = bad_map["gemini"]
        bad_map["gemini"] = dataclasses.replace(real, flags=HostCapabilities())
        with patch("little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES", bad_map):
            errors = _check_runtime_contradiction()
        assert any("gemini" in e and "not the same object" in e for e in errors)

    def test_flags_full_row_with_false_flag(self) -> None:
        # gemini.agent_select is False; its real row is "unsupported" —
        # flip the row to "full" to trip the "full while False" rule.
        bad_map = dict(RUNTIME_HOST_CAPABILITIES)
        real = bad_map["gemini"]
        assert real.flags.agent_select is False
        new_rows = tuple(
            CapabilityEntry("agent_select", "full") if row.name == "agent_select" else row
            for row in real.report_rows
        )
        bad_map["gemini"] = dataclasses.replace(real, report_rows=new_rows)
        with patch("little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES", bad_map):
            errors = _check_runtime_contradiction()
        assert any("gemini" in e and "agent_select" in e and "full" in e for e in errors)

    def test_flags_unsupported_row_with_true_flag(self) -> None:
        # gemini.streaming is True; its real row is "full" — flip the row to
        # "unsupported" to trip the "unsupported while True" rule.
        bad_map = dict(RUNTIME_HOST_CAPABILITIES)
        real = bad_map["gemini"]
        assert real.flags.streaming is True
        new_rows = tuple(
            CapabilityEntry("streaming", "unsupported") if row.name == "streaming" else row
            for row in real.report_rows
        )
        bad_map["gemini"] = dataclasses.replace(real, report_rows=new_rows)
        with patch("little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES", bad_map):
            errors = _check_runtime_contradiction()
        assert any("gemini" in e and "streaming" in e and "unsupported" in e for e in errors)

    def test_flags_test_only_hosts_exempt(self) -> None:
        # A test-only host registered in _HOST_RUNNER_REGISTRY with no runtime
        # entry must not trip key parity — host_runner.TEST_ONLY_HOSTS names
        # the exemption set (absent today; injected here to simulate landing).
        import little_loops.host_runner as host_runner_module

        class _FakeRunner:
            name = "fake"
            capabilities = HostCapabilities()

        bad_registry = dict(_HOST_RUNNER_REGISTRY)
        bad_registry["fake"] = _FakeRunner
        with (
            patch("little_loops.cli.verify_host_map._HOST_RUNNER_REGISTRY", bad_registry),
            patch.object(host_runner_module, "TEST_ONLY_HOSTS", frozenset({"fake"}), create=True),
        ):
            errors = _check_runtime_contradiction()
        assert not any("fake" in e for e in errors)

    def test_injected_fixture_host_entry_agrees(self) -> None:
        # Direct precedent: test_adapters.py:1271-1320's
        # TestFixtureHostRegistration injects a synthetic HostCapabilityEntry
        # into HOST_CAPABILITIES via patch.dict. This is the runtime-side
        # equivalent — a synthetic RuntimeHostEntry plus its matching runner
        # registered in _HOST_RUNNER_REGISTRY should agree cleanly.
        fixture_flags = HostCapabilities(streaming=True)

        class _FixtureRunner:
            name = "fixturehost"
            capabilities = fixture_flags

        fixture_entry = RuntimeHostEntry(
            host="fixturehost",
            binary="fixturehost",
            flags=fixture_flags,
            report_rows=(CapabilityEntry("streaming", "full"),),
        )
        bad_registry = dict(_HOST_RUNNER_REGISTRY)
        bad_registry["fixturehost"] = _FixtureRunner
        bad_map = dict(RUNTIME_HOST_CAPABILITIES)
        bad_map["fixturehost"] = fixture_entry
        with (
            patch("little_loops.cli.verify_host_map._HOST_RUNNER_REGISTRY", bad_registry),
            patch("little_loops.cli.verify_host_map.RUNTIME_HOST_CAPABILITIES", bad_map),
        ):
            errors = _check_runtime_contradiction()
        assert not any("fixturehost" in e for e in errors)


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

    def test_flags_commands_true_with_no_command_output_format(self) -> None:
        # FEAT-3105: commands=True with no command_output_format leaves
        # nothing for the claim to point at — checked across every host.
        bad_map = dict(HOST_CAPABILITIES)
        bad_map["gemini"] = HostCapabilityEntry(
            host="gemini",
            config_dir=".gemini",
            skill_output_format="SKILL.md",
            command_output_format=None,
            agent_output_format="Markdown",
            agents=True,
            commands=True,
            subagents="none",
        )
        with patch("little_loops.cli.verify_host_map.HOST_CAPABILITIES", bad_map):
            errors = _check_emitter_agreement()
        assert any("gemini" in e and "command_output_format" in e for e in errors)


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
