"""Two deliberately divergent host-shaped fakes for the ENH-3456 spike.

Both classes structurally satisfy HostRunner (verified via
isinstance(x, HostRunner)) but deliberately disagree on:

- action vocabulary: VerboseFakeRunner accepts the full build_streaming
  kwarg surface; MinimalFakeRunner accepts only ``prompt`` and ``model``
- capability profile: VerboseFakeRunner reports all six HostCapabilities
  flags True; MinimalFakeRunner reports all six False
- binary name: distinct basenames so neither matches HOST_BINARY_NAMES
  (which would trip the live-spawn guard at
  scripts/tests/conftest.py:353-397)

The divergences exist so the composition test (test_host_compose.py) can
prove the executor touches ONLY the abstract HostRunner Protocol and
HostInvocation public fields — not any shape specific to either fake.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.host_runner import (
    AutomationContext,
    CapabilityEntry,
    CapabilityReport,
    HostCapabilities,
    HostInvocation,
    HostRunner,
)


# Distinct binary basenames — must NOT match HOST_BINARY_NAMES
# (host_runner.py:2028), which is derived from registered real runners.
# A basename collision would trip the _install_no_live_host_cli autouse
# guard (scripts/tests/conftest.py:353-397).
_VERBOSE_BINARY = "fake-verbose-divergent"
_MINIMAL_BINARY = "fake-minimal-divergent"

_VERBOSE_VERSION = "0.0.0-verbose-spike"
_MINIMAL_VERSION = "0.0.0-minimal-spike"


class VerboseFakeRunner:
    """Fake that consumes the full HostRunner action vocabulary.

    Satisfies HostRunner structurally (no explicit inheritance); reports
    every HostCapabilities flag True so any consumer branching on a
    capability sees a maximally-capable surface. The deliberately rich
    shape is the foil for MinimalFakeRunner.
    """

    name: str = "fake-verbose"

    def detect(self) -> bool:
        # Never claim PATH presence — spike is in-process.
        return False

    def build_streaming(
        self,
        *,
        prompt: str,
        working_dir: Path | None = None,
        resume: bool = False,
        agent: str | None = None,
        tools: list[str] | None = None,
        model: str | None = None,
        automation: AutomationContext | None = None,
        automation_profile: str | None = None,
        disable_background_tasks: bool = False,
        workspace_root: Path | None = None,
    ) -> HostInvocation:
        env: dict[str, str] = {}
        if automation is not None and automation.profile is not None:
            env["LL_AUTOMATION"] = "1"
            env["LL_AUTOMATION_PROFILE"] = automation.profile
        return HostInvocation(
            binary=_VERBOSE_BINARY,
            args=[
                _VERBOSE_BINARY,
                "--prompt",
                prompt,
                "--model",
                model or "default-verbose",
                "--resume" if resume else "--no-resume",
            ],
            env=env,
            capabilities=HostCapabilities(
                streaming=True,
                permission_skip=True,
                agent_select=True,
                tool_allowlist=True,
                structured_output=True,
                workspace_sandboxed=True,
            ),
        )

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
    ) -> HostInvocation:
        return HostInvocation(
            binary=_VERBOSE_BINARY,
            args=[_VERBOSE_BINARY, "--blocking", "--prompt", prompt],
            capabilities=HostCapabilities(
                structured_output=True,
            ),
        )

    def build_version_check(self) -> HostInvocation:
        return HostInvocation(
            binary=_VERBOSE_BINARY,
            args=[_VERBOSE_BINARY, "--version"],
        )

    def build_detached(self, prompt: str) -> HostInvocation:
        return HostInvocation(
            binary=_VERBOSE_BINARY,
            args=[_VERBOSE_BINARY, "--detached", "--prompt", prompt],
        )

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            host=self.name,
            binary=_VERBOSE_BINARY,
            version=_VERBOSE_VERSION,
            capabilities=[
                CapabilityEntry(name="streaming", status="full", note="verbose fake"),
                CapabilityEntry(name="permission_skip", status="full"),
                CapabilityEntry(name="agent_select", status="full"),
                CapabilityEntry(name="tool_allowlist", status="full"),
                CapabilityEntry(name="structured_output", status="full"),
                CapabilityEntry(name="workspace_sandboxed", status="full"),
            ],
        )


class MinimalFakeRunner:
    """Fake with deliberately slimmer action vocabulary and zero capabilities.

    Satisfies HostRunner structurally but exposes only ``prompt`` and
    ``model`` on build_streaming (accepts **only** those two kwargs; raises
    TypeError if any other kwarg is supplied). All six HostCapabilities
    flags are False. The deliberately poor shape is the foil for
    VerboseFakeRunner.
    """

    name: str = "fake-minimal"

    def detect(self) -> bool:
        return False

    def build_streaming(
        self,
        *,
        prompt: str,
        model: str | None = None,
    ) -> HostInvocation:
        # Deliberately slim: takes ONLY prompt + model. Any extra kwarg
        # would raise TypeError — that's the point. If a downstream
        # consumer assumes a richer surface (e.g. reads
        # ``automation.profile``), it breaks here, proving the consumer
        # touched shape-specific fields rather than the abstract
        # HostRunner Protocol.
        return HostInvocation(
            binary=_MINIMAL_BINARY,
            args=[_MINIMAL_BINARY, prompt],
            capabilities=HostCapabilities(),  # all six flags False
        )

    def build_blocking_json(
        self,
        *,
        prompt: str,
        model: str | None = None,
        json_schema: dict | None = None,
    ) -> HostInvocation:
        return HostInvocation(
            binary=_MINIMAL_BINARY,
            args=[_MINIMAL_BINARY, "--json", prompt],
            capabilities=HostCapabilities(),
        )

    def build_version_check(self) -> HostInvocation:
        return HostInvocation(
            binary=_MINIMAL_BINARY,
            args=[_MINIMAL_BINARY, "--version"],
        )

    def build_detached(self, prompt: str) -> HostInvocation:
        return HostInvocation(
            binary=_MINIMAL_BINARY,
            args=[_MINIMAL_BINARY, "--bg", prompt],
        )

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            host=self.name,
            binary=_MINIMAL_BINARY,
            version=_MINIMAL_VERSION,
            capabilities=[
                CapabilityEntry(name="streaming", status="unsupported"),
                CapabilityEntry(name="permission_skip", status="unsupported"),
                CapabilityEntry(name="agent_select", status="unsupported"),
                CapabilityEntry(name="tool_allowlist", status="unsupported"),
                CapabilityEntry(name="structured_output", status="unsupported"),
                CapabilityEntry(name="workspace_sandboxed", status="unsupported"),
            ],
        )


__all__ = ["VerboseFakeRunner", "MinimalFakeRunner", "HostRunner"]