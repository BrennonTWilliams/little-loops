"""In-process executor shim that reads ONLY HostInvocation public fields.

Mirrors the field-access contract of subprocess_utils.run_claude_command
(host_runner / subprocess_utils.py:516-680) without spawning a subprocess.
The shim's job is to prove that a single executor path can serve two
deliberately divergent HostInvocation shapes — proving the layer is
shape-agnostic. The shim reads ONLY:

- invocation.binary
- invocation.args
- invocation.env
- invocation.capabilities (the HostCapabilities dataclass public surface)

It deliberately does NOT read any class-specific attribute, nor does it
type-check against any concrete runner subclass. A test that asserts the
shim's field-access surface is contained to those four paths is the load-
bearing regression guard for ENH-3456's "host-agnostic" invariant.
"""

from __future__ import annotations

from typing import Any

from little_loops.host_runner import HostInvocation, HostRunner


# The set of HostInvocation public attributes the shim is permitted to
# touch. Anything outside this set in the shim's body is a violation.
ALLOWED_INVOCATION_ATTRS: frozenset[str] = frozenset(
    {"binary", "args", "env", "capabilities"}
)

# The set of HostRunner Protocol attribute names the shim is permitted to
# read. The shim may call any HostRunner-typed object through these names
# without taking a dependency on a concrete runner class.
ALLOWED_RUNNER_PROTOCOL_ATTRS: frozenset[str] = frozenset(
    {
        "name",
        "detect",
        "build_streaming",
        "build_blocking_json",
        "build_version_check",
        "build_detached",
        "describe_capabilities",
    }
)


class ExecutorAccessedForbiddenField(Exception):
    """Raised by execute_invocation in audit mode when the shim touches
    a HostInvocation attribute outside ALLOWED_INVOCATION_ATTRS.

    The audit-mode wrapper is what makes the "touches only the abstract
    interface" assertion mechanically checkable rather than a code-review
    judgment call.
    """


def _wrap_invocation(invocation: HostInvocation) -> HostInvocation:
    """Wrap HostInvocation so any attribute access outside the allow-list
    raises. Used only in audit-mode (audit=True)."""

    class _AuditedInvocation:
        def __init__(self, real: HostInvocation) -> None:
            self._real = real

        def __getattr__(self, name: str) -> Any:
            if name not in ALLOWED_INVOCATION_ATTRS:
                raise ExecutorAccessedForbiddenField(
                    f"executor_shim touched forbidden attribute {name!r} "
                    f"on HostInvocation; allowed={sorted(ALLOWED_INVOCATION_ATTRS)}"
                )
            return getattr(self._real, name)

    return _AuditedInvocation(invocation)  # type: ignore[return-value]


def execute_invocation(
    runner: HostRunner,
    invocation: HostInvocation,
    *,
    audit: bool = False,
) -> dict[str, Any]:
    """Drive an invocation through the in-process executor contract.

    Reads ONLY HostInvocation public fields (binary, args, env,
    capabilities) and the runner's Protocol-level attributes (name,
    detect, build_*). Mirrors what run_claude_command would do at the
    subprocess boundary — construct argv from ``args``, set env from
    ``env``, and read the host's capability surface — without spawning.

    Args:
        runner: The HostRunner that produced invocation. Used only for
            ``runner.name`` and ``runner.describe_capabilities()`` (Protocol
            surface; no concrete-class dispatch).
        invocation: The HostInvocation to execute.
        audit: When True, every attribute access on ``invocation`` is
            validated against ALLOWED_INVOCATION_ATTRS. Production callers
            leave this False; tests use True to mechanically assert the
            shim touched only the abstract surface.

    Returns:
        Dict describing what the executor consumed — useful for asserting
        capability round-trip in the composition test.
    """
    target = _wrap_invocation(invocation) if audit else invocation

    # Executor step 1: read the binary basename + argv (HostInvocation
    # public fields only — never inspects a concrete runner subclass).
    binary = target.binary  # type: ignore[attr-defined]
    argv = target.args  # type: ignore[attr-defined]

    # Executor step 2: merge env into the would-be child env. The shim
    # does not actually spawn, so this is a no-op — but the read pattern
    # mirrors what run_claude_command does.
    env = target.env  # type: ignore[attr-defined]

    # Executor step 3: read the capability surface to decide whether
    # streaming / structured output / sandboxing paths are wired. This is
    # the load-bearing step: a consumer that read a non-public attribute
    # (e.g. ``invocation._verbose_extra``) would silently miss the
    # invariant. audit=True catches this.
    caps = target.capabilities  # type: ignore[attr-defined]

    # Executor step 4: identify the host by name (Protocol surface).
    host_name = runner.name

    return {
        "host_name": host_name,
        "binary": binary,
        "argv": list(argv),
        "env_keys": sorted(env.keys()),
        "capabilities": {
            "streaming": caps.streaming,
            "permission_skip": caps.permission_skip,
            "agent_select": caps.agent_select,
            "tool_allowlist": caps.tool_allowlist,
            "structured_output": caps.structured_output,
            "workspace_sandboxed": caps.workspace_sandboxed,
        },
    }


def compose_through_executor(
    runners: dict[str, HostRunner],
    *,
    audit: bool = False,
) -> dict[str, dict[str, Any]]:
    """Compose multiple runners through the same executor path.

    For each runner, builds one ``build_streaming`` invocation and drives
    it through ``execute_invocation``. The composition test asserts that
    this single executor path serves both the verbose and minimal fakes
    — proving the layer is shape-agnostic, not just "runs against one
    shape".

    Args:
        runners: Mapping of label → HostRunner. Each runner is exercised
            once.
        audit: Forwarded to ``execute_invocation``; when True, every
            HostInvocation attribute access is checked against the
            allow-list.

    Returns:
        Mapping of label → executor result dict.
    """
    results: dict[str, dict[str, Any]] = {}
    for label, runner in runners.items():
        invocation = runner.build_streaming(prompt=f"compose-{label}")
        results[label] = execute_invocation(runner, invocation, audit=audit)
    return results


__all__ = [
    "ALLOWED_INVOCATION_ATTRS",
    "ALLOWED_RUNNER_PROTOCOL_ATTRS",
    "ExecutorAccessedForbiddenField",
    "compose_through_executor",
    "execute_invocation",
]