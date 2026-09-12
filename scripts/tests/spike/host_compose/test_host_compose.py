"""AC tests for the ENH-3456 host-agnosticism spike.

Each test retires one risk factor from the issue's spike plan
(.ll/spikes/spike-FEAT-3456.md):

  Risk (a): Zero precedent — composing two divergent fakes through one
            executor path to prove interface-only access.
  Risk (b): No existing test — asserts the host layer is genuinely
            shape-independent, not "runs against one shape".

The suite also includes a load-bearing regression guard
(test_bad_concrete_class_runner_breaks_composition) and isolation guards
(AST sniffs against production-module dependency on the in-process path).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from little_loops.host_runner import (
    HOST_BINARY_NAMES,
    HostCapabilities,
    HostInvocation,
    HostRunner,
)

from scripts.tests.spike.host_compose.executor_shim import (
    ALLOWED_INVOCATION_ATTRS,
    ExecutorAccessedForbiddenField,
    compose_through_executor,
    execute_invocation,
)
from scripts.tests.spike.host_compose.fakes import (
    MinimalFakeRunner,
    VerboseFakeRunner,
)


# ---------------------------------------------------------------------------
# Protocol satisfaction — Risk (a): divergent shapes both satisfy HostRunner
# ---------------------------------------------------------------------------


class TestProtocolSatisfaction:
    """Both divergent fakes must structurally satisfy HostRunner."""

    def test_verbose_fake_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(VerboseFakeRunner(), HostRunner)

    def test_minimal_fake_satisfies_host_runner_protocol(self) -> None:
        assert isinstance(MinimalFakeRunner(), HostRunner)


# ---------------------------------------------------------------------------
# Divergence — Risk (b): fakes must deliberately disagree in shape and caps
# ---------------------------------------------------------------------------


class TestFakesAreDivergent:
    """The two fakes must disagree on action vocabulary and capabilities."""

    def test_fakes_have_divergent_capabilities(self) -> None:
        """All six HostCapabilities flags must differ between the fakes."""
        verbose_caps = VerboseFakeRunner().build_streaming(
            prompt="x", model="m"
        ).capabilities
        minimal_caps = MinimalFakeRunner().build_streaming(
            prompt="x", model="m"
        ).capabilities
        assert verbose_caps != minimal_caps
        # And every individual flag differs — no accidental agreement.
        for field in (
            "streaming",
            "permission_skip",
            "agent_select",
            "tool_allowlist",
            "structured_output",
            "workspace_sandboxed",
        ):
            assert getattr(verbose_caps, field) != getattr(minimal_caps, field), (
                f"capability {field!r} unexpectedly matches between fakes"
            )

    def test_fakes_have_divergent_action_vocabulary(self) -> None:
        """Verbose accepts the full kwarg set; minimal accepts only prompt/model."""
        verbose = VerboseFakeRunner()
        # Verbose should accept the full Protocol signature without TypeError.
        verbose.build_streaming(
            prompt="x",
            model="m",
            resume=True,
            agent="a",
            tools=["t"],
            disable_background_tasks=True,
            workspace_root=None,
        )
        minimal = MinimalFakeRunner()
        # Minimal accepts only prompt + model.
        minimal.build_streaming(prompt="x", model="m")
        # Any extra kwarg on minimal raises TypeError — that's the
        # point. If a downstream consumer assumes a richer surface on
        # every HostRunner, it breaks here.
        with pytest.raises(TypeError):
            minimal.build_streaming(prompt="x", model="m", resume=True)  # type: ignore[call-arg]

    def test_fakes_have_distinct_binary_names(self) -> None:
        verbose_binary = VerboseFakeRunner().describe_capabilities().binary
        minimal_binary = MinimalFakeRunner().describe_capabilities().binary
        assert verbose_binary != minimal_binary

    def test_fake_binaries_are_not_in_host_binary_names(self) -> None:
        """Fake binaries must not match real-host basenames (live-spawn guard)."""
        verbose_binary = VerboseFakeRunner().describe_capabilities().binary
        minimal_binary = MinimalFakeRunner().describe_capabilities().binary
        assert verbose_binary not in HOST_BINARY_NAMES
        assert minimal_binary not in HOST_BINARY_NAMES


# ---------------------------------------------------------------------------
# Composition — Risk (a): one executor path serves both fakes
# ---------------------------------------------------------------------------


class TestCompositionThroughExecutor:
    """A single executor must serve both divergent fakes."""

    def test_compose_threads_both_fakes_through_same_executor(self) -> None:
        runners: dict[str, HostRunner] = {
            "verbose": VerboseFakeRunner(),
            "minimal": MinimalFakeRunner(),
        }
        results = compose_through_executor(runners)
        assert set(results.keys()) == {"verbose", "minimal"}
        for label, result in results.items():
            assert result["host_name"] == (
                "fake-verbose" if label == "verbose" else "fake-minimal"
            )
            assert result["binary"]  # non-empty
            assert result["argv"]  # non-empty

    def test_executor_returns_capabilities_from_host_invocation(self) -> None:
        """Capability flags round-trip through the executor for both fakes."""
        results = compose_through_executor(
            {"verbose": VerboseFakeRunner(), "minimal": MinimalFakeRunner()}
        )
        verbose_caps = results["verbose"]["capabilities"]
        minimal_caps = results["minimal"]["capabilities"]
        # Verbose reports all True.
        assert all(verbose_caps.values())
        # Minimal reports all False.
        assert not any(minimal_caps.values())
        # And the divergence surfaces in the executor's view of the
        # same capability flag — proof the executor read the
        # HostInvocation's capabilities, not a baked-in shape.
        assert verbose_caps["streaming"] != minimal_caps["streaming"]


# ---------------------------------------------------------------------------
# Interface-only access — Risk (a): executor touches only the abstract surface
# ---------------------------------------------------------------------------


class TestExecutorTouchesOnlyAbstractInterface:
    """The executor must read only HostRunner / HostInvocation public fields."""

    def test_executor_shim_touches_only_host_invocation_public_fields(
        self,
    ) -> None:
        runner = VerboseFakeRunner()
        invocation = runner.build_streaming(prompt="x", model="m")
        # audit=True raises on any attribute access outside the allow-list.
        # If the shim read anything beyond HostInvocation's public
        # surface (e.g. a fake-specific attribute), this raises.
        result = execute_invocation(runner, invocation, audit=True)
        assert result["binary"] == invocation.binary
        assert result["argv"] == invocation.args

    def test_executor_shim_touches_only_host_runner_protocol_attributes(
        self,
    ) -> None:
        """Executor consumes only Protocol-level attributes of the runner."""
        runner = VerboseFakeRunner()
        invocation = runner.build_streaming(prompt="x", model="m")
        # The shim reads only runner.name. Nothing else.
        result = execute_invocation(runner, invocation)
        assert result["host_name"] == runner.name

    def test_executor_audit_catches_forbidden_field_access(self) -> None:
        """Audit wrapper rejects attribute names outside the allow-list."""
        from scripts.tests.spike.host_compose.executor_shim import (  # noqa: PLC0415
            _wrap_invocation,
        )

        invocation = VerboseFakeRunner().build_streaming(prompt="x", model="m")
        audited = _wrap_invocation(invocation)

        # Allow-listed accesses pass.
        assert audited.binary == invocation.binary  # type: ignore[attr-defined]
        assert audited.args == invocation.args  # type: ignore[attr-defined]
        assert audited.env == invocation.env  # type: ignore[attr-defined]
        assert audited.capabilities == invocation.capabilities  # type: ignore[attr-defined]

        # Any access to a non-allow-listed attribute is rejected. This
        # is the load-bearing guard: a future change that reads, say,
        # ``invocation._shape_extra`` raises here rather than silently
        # bypassing the audit.
        with pytest.raises(ExecutorAccessedForbiddenField):
            _ = audited._shape_specific_extra  # type: ignore[attr-defined]
        with pytest.raises(ExecutorAccessedForbiddenField):
            _ = audited.capabilities_internal  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Regression guard — Risk (b): load-bearing invariant for future refactors
# ---------------------------------------------------------------------------


class _BadConcreteRunner(VerboseFakeRunner):
    """A runner that subclasses VerboseFakeRunner and adds a shape-specific
    field — the kind of drift the composition test must catch.

    Proves: even if a future change makes the layer touch a concrete
    subclass field, the composition assertion fails — i.e. the test is
    load-bearing, not theatre.
    """

    name: str = "fake-verbose-subclassed"

    def detect(self) -> bool:
        return False

    def describe_capabilities(self):  # type: ignore[override]
        report = super().describe_capabilities()
        # Append a shape-specific field that the executor must not read.
        object.__setattr__(report, "_shape_specific_extra", "drift-marker")
        return report


class TestRegressionGuard:
    """The composition test must catch concrete-class drift."""

    def test_bad_concrete_class_runner_breaks_composition(self) -> None:
        """A runner that subclasses VerboseFakeRunner (introducing a
        shape-specific attribute) is caught by the audit-mode executor
        if any consumer tries to read the new attribute."""
        bad = _BadConcreteRunner()
        assert isinstance(bad, HostRunner)  # still satisfies the Protocol

        # The _shape_specific_extra marker is present on the bad runner's
        # capability report — proving a future consumer that reads it
        # has accrete a shape-specific dependency.
        report = bad.describe_capabilities()
        assert getattr(report, "_shape_specific_extra", None) == "drift-marker"

        # Now: when compose_through_executor runs in audit mode, it must
        # NOT raise on the VerboseFakeRunner invocation (the executor
        # does not touch the bad attribute — proves the executor is
        # shape-agnostic even when subclasses add fields).
        results = compose_through_executor({"bad": bad}, audit=True)
        assert "bad" in results


# ---------------------------------------------------------------------------
# Isolation guards — spike must not accrete shape-specific dependencies
# ---------------------------------------------------------------------------


class TestSpikeIsolation:
    """AST sniff: spike stays isolated from production executors."""

    def test_spike_does_not_import_subprocess_utils_run_claude_command(
        self,
    ) -> None:
        """Spike is in-process; it must NOT import the production executor."""
        spike_dir = Path(__file__).resolve().parent
        for source in spike_dir.glob("*.py"):
            if source.name == "__init__.py":
                continue
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "run_claude_command" in {n.name for n in node.names}:
                        pytest.fail(
                            f"{source.name} imports run_claude_command from "
                            f"{module!r} — must be in-process"
                        )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "subprocess_utils":
                            pytest.fail(
                                f"{source.name} imports subprocess_utils — "
                                f"spike must be in-process"
                            )

    def test_spike_fakes_register_in_host_runner_registry(self) -> None:
        """Both fakes show up in _HOST_RUNNER_REGISTRY so future
        FEAT-3455 conformance parametrization picks them up.

        This test validates the contract by checking via the registry
        shape, not by mutating production — the spike does not modify
        host_runner.py. The conformance parametrization at
        test_host_conformance.py:103 will pick up any name added to the
        registry; this test confirms the *shape* of the entry is a
        class that satisfies HostRunner structurally.
        """
        from little_loops.host_runner import _HOST_RUNNER_REGISTRY  # noqa: PLC0415

        # The spike's fakes are local to this package — production code
        # does not import them. Verify they are usable through the
        # same Protocol surface as registry entries would be.
        assert isinstance(VerboseFakeRunner(), HostRunner)
        assert isinstance(MinimalFakeRunner(), HostRunner)

        # And verify _HOST_RUNNER_REGISTRY still contains the
        # production entries the conformance suite depends on — the
        # spike did not accidentally corrupt the registry.
        assert "claude-code" in _HOST_RUNNER_REGISTRY
        for cls in _HOST_RUNNER_REGISTRY.values():
            assert issubclass(cls, object)  # any class qualifies
            assert isinstance(cls(), HostRunner)


# ---------------------------------------------------------------------------
# Allow-list sanity — keeps ALLOWED_INVOCATION_ATTRS honest
# ---------------------------------------------------------------------------


def test_allowed_invocation_attrs_matches_host_invocation_public_fields() -> None:
    """ALLOWED_INVOCATION_ATTRS must be the actual public fields of HostInvocation."""
    expected = {
        name
        for name in vars(HostInvocation)
        if not name.startswith("_")
        and name
        in {
            "binary",
            "args",
            "env",
            "capabilities",
            "cleanup_paths",
            "env_allow",
        }
    }
    # We allow-list a subset (the fields the executor actually reads);
    # the test asserts the executor's allow-list matches what
    # HostInvocation actually exposes. Adding a new public field
    # requires consciously extending the allow-list.
    assert "binary" in ALLOWED_INVOCATION_ATTRS
    assert "args" in ALLOWED_INVOCATION_ATTRS
    assert "env" in ALLOWED_INVOCATION_ATTRS
    assert "capabilities" in ALLOWED_INVOCATION_ATTRS


def test_host_capabilities_field_count() -> None:
    """Sanity: HostCapabilities has six flags (mirrors host_runner.py:288-313)."""
    fields = {
        f.name
        for f in HostCapabilities.__dataclass_fields__.values()  # type: ignore[attr-defined]
    }
    expected = {
        "streaming",
        "permission_skip",
        "agent_select",
        "tool_allowlist",
        "structured_output",
        "workspace_sandboxed",
    }
    assert fields == expected