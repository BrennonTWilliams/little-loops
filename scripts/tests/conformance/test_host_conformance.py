"""Host conformance harness for little-loops orchestration golden paths (FEAT-3455).

Two tiers, both parametrized over every host registered in
``_HOST_RUNNER_REGISTRY``:

- **Constructability** (``test_golden_path_invocation``): ``resolve_host() +
  build_streaming()`` produces a valid ``HostInvocation`` for one of the four
  orchestration golden paths — ``ll-auto``, ``ll-sprint``, ``ll-loop``,
  ``ll-action``. Never executes the prompt.
- **Behavioral** (``test_golden_path_behavior`` — Tier 1, plus the
  ``test_scripted_*`` cases — Tier 2): actually runs the invocation through
  ``run_claude_command`` and asserts observable stream-shape invariants.
  Tier 1 runs unconditionally for the fake host (FEAT-3454) and, for every
  other host, only behind ``LL_HOST_CONFORMANCE_LIVE=1`` (real tokens, real
  auth). Tier 2's scripted-exact scenarios run against the fake only, on
  every suite invocation, never skipping.

Run all conformance tests::

    pytest -m conformance scripts/tests/

Run for a specific host only::

    pytest -m conformance --conformance-host codex scripts/tests/

Run the live behavioral tier for a host that has a binary on PATH::

    LL_HOST_CONFORMANCE_LIVE=1 pytest -m conformance --conformance-host codex \\
        scripts/tests/conformance/

Deselect conformance tests from a full suite run::

    pytest -m "not conformance" scripts/tests/

Skip conditions (SKIP, not FAIL):
- Binary unavailable on PATH (e.g. ``claude`` not installed)
- Stub runner: ``build_streaming`` raises ``HostNotConfigured``
- Tier 1 on a non-fake host without ``LL_HOST_CONFORMANCE_LIVE=1``

The PASS/SKIP matrix maps directly to the "Orchestration CLI" table in
``docs/reference/HOST_COMPATIBILITY.md``:  PASS → ✓, SKIP(stub) → stub[^orch].

See ``docs/development/CONFORMANCE.md`` for the full tier breakdown.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pytest

from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    AutomationContext,
    CapabilityNotSupported,
    ClaudeCodeRunner,
    CodexRunner,
    FakeHostRunner,
    GeminiRunner,
    HostCapabilities,
    HostInvocation,
    HostNotConfigured,
    KimiRunner,
    OmpRunner,
    QwenRunner,
    _structured_output_args,
    resolve_host,
)
from little_loops.subprocess_utils import (
    TokenUsage,
    ToolCall,
    clear_shutdown,
    request_shutdown,
    run_claude_command,
)

# Every test in this module is a conformance test — constructability, Tier 1
# behavioral, Tier 2 scripted, and capability-argv alike — so `-m
# "not conformance"` cleanly deselects the whole module and `-m conformance`
# selects all of it, matching the module docstring's "Run all conformance
# tests" claim. Orthogonal to the `--conformance-host` filter (only Tier 1 /
# constructability read that option; Tier 2 and capability tests ignore it
# by design — see the Design Decision in FEAT-3455 on why those never skip).
pytestmark = pytest.mark.conformance

# Representative prompt for each orchestration tool golden path.  Content is
# illustrative — conformance only validates that a HostInvocation is
# constructable; it does not execute the prompt against a live host.
_GOLDEN_PATHS: list[tuple[str, str]] = [
    ("ll-auto", "Process the next open issue from the backlog using /ll:manage-issue."),
    ("ll-sprint", "Execute the current sprint plan using /ll:review-sprint."),
    ("ll-loop", "Run one FSM loop iteration using /ll:audit-loop-run."),
    ("ll-action", "/ll:check-code"),
]

# Binary name for each registered host — used to probe PATH availability.
_HOST_BINARY: dict[str, str] = {
    "claude-code": "claude",
    "codex": "codex",
    "opencode": "opencode",
    "pi": "pi",
    "gemini": "gemini",
    "omp": "omp",
    "kimi-code": "kimi",
    "qwen": "qwen",
    "fake": "ll-fake-host",
}

# Tier 1's single fixed prompt (FEAT-3455). Golden-path prompts instruct the
# host to run an orchestration slash command; live, that would be an
# agentic run per host, likely to exceed the suite's watchdog and spend real
# tokens on work this tier never inspects. One trivial prompt, parametrized
# over hosts only, keeps the live tier cheap and focused on stream shape.
_LIVE_PROMPT = "Reply with exactly: OK"

TerminalKind = Literal["result", "turn.completed"]

# (init event expected, terminal event kind) per registered host. Codex's
# `exec --json` emits thread.started/turn.started/item.*/turn.completed and
# no system/init; the consumer's turn.completed branch
# (subprocess_utils.py:698-717) never sets result_seen, so Codex drains to
# EOF instead of breaking early on a terminal event. Every other wired host
# speaks Claude's stream-json envelope (system/init + result). Stub hosts
# (opencode, pi) and the fake all default to the Claude shape; opencode/pi's
# row is never actually exercised (build_streaming raises HostNotConfigured
# before Tier 1 gets this far), but a row is still required by the
# `test_stream_shape_covers_registry` gate below.
_STREAM_SHAPE: dict[str, tuple[bool, TerminalKind]] = {
    "claude-code": (True, "result"),
    "codex": (False, "turn.completed"),
    "opencode": (True, "result"),
    "pi": (True, "result"),
    "gemini": (True, "result"),
    "omp": (True, "result"),
    "kimi-code": (True, "result"),
    "qwen": (True, "result"),
    "fake": (True, "result"),
}


def test_stream_shape_covers_registry() -> None:
    """`_STREAM_SHAPE` must have a row for every registered host (gate, like `_HOST_BINARY`)."""
    registry_keys = set(_HOST_RUNNER_REGISTRY)
    shape_keys = set(_STREAM_SHAPE)
    assert shape_keys == registry_keys, (
        f"_STREAM_SHAPE out of sync with _HOST_RUNNER_REGISTRY: "
        f"missing={registry_keys - shape_keys!r}, extra={shape_keys - registry_keys!r}"
    )


@dataclass
class Observed:
    """Everything a consumer of ``run_claude_command`` can observe, via callbacks.

    The consumer exposes no event list — every observation happens through
    callbacks, so ``kinds`` is the callback-derived sequence built up by
    ``_run_and_capture``: ``on_model_detected`` -> ``"init"``,
    ``on_tool_call`` -> ``"tool"``, ``stream_callback(is_stderr=False)`` ->
    ``"text"``, ``on_usage_detailed`` -> ``"usage"``. ``result_seen`` stays
    ``None`` (not ``False``) when ``run_claude_command`` raised
    ``TimeoutExpired`` — ``on_result_seen`` only fires on the normal-return
    path.
    """

    kinds: list[str] = field(default_factory=list)
    model: str | None = None
    session_id: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: list[TokenUsage] = field(default_factory=list)
    result_seen: bool | None = None
    process: subprocess.Popen[str] | None = None
    pgid: int | None = None
    completed: subprocess.CompletedProcess[str] | None = None
    error: BaseException | None = None


def _run_and_capture(
    host: str,
    prompt: str,
    *,
    timeout: int,
    automation: AutomationContext | None = None,
    post_stream_close_grace_seconds: int = 5,
    on_text: Callable[[str], None] | None = None,
    tmp_path: Path,
) -> Observed:
    """Drive ``run_claude_command`` unpatched against *host*, capturing every callback.

    Sets ``LL_HOST_CLI=host`` for the call's duration (restored in a
    ``finally``, mirroring the ``isolated_env`` fixture's scope but as a
    plain function since it isn't itself a fixture). ``on_text`` is the hook
    the abort scenario uses to call ``request_shutdown()`` from inside
    ``stream_callback`` — the read loop checks ``_shutdown_event`` at the
    top of each iteration, so a callback-fired shutdown is deterministic
    (unlike a timer thread).
    """
    obs = Observed()

    def _on_model(model: str) -> None:
        obs.model = model
        obs.kinds.append("init")

    def _on_session(session_id: str) -> None:
        obs.session_id = session_id

    def _on_tool(call: ToolCall) -> None:
        obs.tool_calls.append(call)
        obs.kinds.append("tool")

    def _on_text_line(line: str, is_stderr: bool) -> None:
        if is_stderr:
            return
        obs.kinds.append("text")
        if on_text is not None:
            on_text(line)

    def _on_usage(usage: TokenUsage) -> None:
        obs.usage.append(usage)
        obs.kinds.append("usage")

    def _on_result_seen(seen: bool) -> None:
        obs.result_seen = seen

    def _on_process_start(process: subprocess.Popen[str]) -> None:
        obs.process = process
        try:
            obs.pgid = os.getpgid(process.pid)
        except (OSError, AttributeError):
            obs.pgid = None

    prev_host_cli = os.environ.get("LL_HOST_CLI")
    os.environ["LL_HOST_CLI"] = host
    try:
        try:
            obs.completed = run_claude_command(
                prompt,
                timeout=timeout,
                working_dir=tmp_path,
                stream_callback=_on_text_line,
                on_process_start=_on_process_start,
                on_model_detected=_on_model,
                on_session_id_detected=_on_session,
                on_usage_detailed=_on_usage,
                on_result_seen=_on_result_seen,
                on_tool_call=_on_tool,
                automation=automation,
                post_stream_close_grace_seconds=post_stream_close_grace_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            obs.error = exc
    finally:
        if prev_host_cli is None:
            os.environ.pop("LL_HOST_CLI", None)
        else:
            os.environ["LL_HOST_CLI"] = prev_host_cli
    return obs


def assert_terminal_once(obs: Observed, *, host: str, case: str) -> None:
    """The terminal fires exactly once and is last in the observed kinds."""
    assert len(obs.usage) == 1, (
        f"[{host}/{case}] expected exactly one usage terminal, got {len(obs.usage)}: "
        f"kinds={obs.kinds!r}"
    )
    assert obs.kinds[-1] == "usage", (
        f"[{host}/{case}] usage must be the last observed kind: {obs.kinds!r}"
    )
    _, terminal_kind = _STREAM_SHAPE[host]
    expected_result_seen = terminal_kind == "result"
    assert obs.result_seen is expected_result_seen, (
        f"[{host}/{case}] expected on_result_seen({expected_result_seen}), got {obs.result_seen!r}"
    )


def assert_stderr_clean(obs: Observed, *, host: str) -> None:
    """``stderr == ""`` for the fake; no ``[result] ``-prefixed line for a live host."""
    stderr = obs.completed.stderr if obs.completed is not None else ""
    if host == "fake":
        assert stderr == "", f"[{host}] expected empty stderr, got {stderr!r}"
    else:
        bad_lines = [line for line in stderr.splitlines() if line.startswith("[result] ")]
        assert not bad_lines, (
            f"[{host}] unexpected `[result] `-prefixed stderr line(s): {bad_lines!r}"
        )


def assert_group_gone(obs: Observed) -> None:
    """The process group is fully reaped: ``wait()`` returns, ``killpg(pgid, 0)`` raises."""
    assert obs.process is not None, "on_process_start never fired"
    obs.process.wait(timeout=5)
    assert obs.pgid is not None, "process group id was never captured at process start"
    with pytest.raises(ProcessLookupError):
        os.killpg(obs.pgid, 0)


def assert_event_kinds(obs: Observed, expected: list[str], *, host: str, case: str) -> None:
    """Assert ``obs.kinds == expected``, diagnosing the first index of divergence."""
    actual = obs.kinds
    if actual == expected:
        return
    idx = next(
        (i for i, pair in enumerate(zip(actual, expected, strict=False)) if pair[0] != pair[1]),
        min(len(actual), len(expected)),
    )
    raise AssertionError(
        f"[{host}/{case}] event kind mismatch at index {idx}: "
        f"expected={expected!r} actual={actual!r}"
    )


@pytest.mark.conformance
@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))
@pytest.mark.parametrize(
    "golden_path,prompt",
    _GOLDEN_PATHS,
    ids=[p[0] for p in _GOLDEN_PATHS],
)
def test_golden_path_invocation(
    host: str,
    golden_path: str,
    prompt: str,
    tmp_path: Path,
    isolated_env: None,
    request: pytest.FixtureRequest,
) -> None:
    """``resolve_host() + build_streaming()`` produces a valid ``HostInvocation``.

    A PASS means the host runner is wired and can construct an invocation for
    the given golden path.  A SKIP means the host binary is absent or the
    runner is a stub (``HostNotConfigured``).

    Args:
        host: Registered host key (e.g. ``"codex"``, ``"claude-code"``).
        golden_path: Orchestration tool label (e.g. ``"ll-auto"``).
        prompt: Representative prompt string passed to ``build_streaming``.
        tmp_path: Temporary directory used as ``working_dir``.
        isolated_env: Clears ``LL_HOST_CLI`` / ``LL_HOOK_HOST`` before the test.
        request: Pytest fixture request (used to read the ``--host`` option).
    """
    # Honour the --conformance-host filter when supplied on the command line.
    host_filter: str | None = request.config.getoption("--conformance-host", default=None)
    if host_filter is not None and host != host_filter:
        pytest.skip(f"--host filter {host_filter!r} excludes {host!r}")

    # Skip when the host binary is not available on this machine.
    binary = _HOST_BINARY.get(host)
    if binary is not None and shutil.which(binary) is None:
        pytest.skip(f"{host!r} binary ({binary!r}) not found on PATH")

    runner = resolve_host(env={"LL_HOST_CLI": host})

    # Skip stub runners that raise HostNotConfigured on build_streaming().
    try:
        invocation = runner.build_streaming(prompt=prompt, working_dir=tmp_path)
    except HostNotConfigured as exc:
        pytest.skip(f"{host!r} is a stub runner: {exc}")

    assert invocation.binary, f"[{host}/{golden_path}] HostInvocation.binary must not be empty"
    assert invocation.args, f"[{host}/{golden_path}] HostInvocation.args must not be empty"


@pytest.mark.conformance
@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))
def test_golden_path_behavior(
    host: str,
    tmp_path: Path,
    isolated_env: None,
    live_conformance: bool,
    request: pytest.FixtureRequest,
) -> None:
    """Tier 1 (FEAT-3455): every registered host satisfies the same behavioral invariants.

    Runs unconditionally for the fake host (~150ms, FEAT-3454's default
    emission). For every other host this only runs live, behind
    ``LL_HOST_CONFORMANCE_LIVE=1`` (via the ``live_conformance`` fixture) —
    it spends real tokens and requires host auth.
    """
    host_filter: str | None = request.config.getoption("--conformance-host", default=None)
    if host_filter is not None and host != host_filter:
        pytest.skip(f"--host filter {host_filter!r} excludes {host!r}")

    if host != "fake":
        if not live_conformance:
            pytest.skip("live host behavioral tier requires LL_HOST_CONFORMANCE_LIVE=1")
        binary = _HOST_BINARY.get(host)
        if binary is not None and shutil.which(binary) is None:
            pytest.skip(f"{host!r} binary ({binary!r}) not found on PATH")
        runner = resolve_host(env={"LL_HOST_CLI": host})
        try:
            runner.build_streaming(prompt=_LIVE_PROMPT, working_dir=tmp_path)
        except HostNotConfigured as exc:
            pytest.skip(f"{host!r} is a stub runner: {exc}")

    expects_init, _ = _STREAM_SHAPE[host]
    obs = _run_and_capture(host, _LIVE_PROMPT, timeout=60, tmp_path=tmp_path)

    assert obs.error is None, f"[{host}] unexpected TimeoutExpired: {obs.error!r}"
    if expects_init:
        assert obs.kinds[:1] == ["init"], f"[{host}] expected init first in kinds: {obs.kinds!r}"
    assert_terminal_once(obs, host=host, case="golden_path_behavior")
    assert_stderr_clean(obs, host=host)
    assert obs.completed is not None
    assert obs.completed.returncode == 0, (
        f"[{host}] expected returncode 0, got {obs.completed.returncode}"
    )


def assert_capability_argv(invocation: HostInvocation, flag: str, *, marker_present: bool) -> None:
    """Directional capability-argv check (FEAT-3455): declared flag must match observed argv.

    Negative (flag False): marker_present must be False — under-declaring a
    capability is not the same bug as over-declaring, but absence of the
    marker is still required. Positive (flag True): marker_present must be True.
    The caller computes marker_present however fits that runner/flag (a
    literal `in invocation.args` check, or a substring check against the
    last positional arg for prompt-prefixed personas like Codex's).
    """
    declared = getattr(invocation.capabilities, flag)
    if declared:
        assert marker_present, (
            f"capability {flag}=True declared but no argv marker present: {invocation.args!r}"
        )
    else:
        assert not marker_present, (
            f"capability {flag}=False declared but argv marker present: {invocation.args!r}"
        )


# ── Capability argv tests (FEAT-3455) ─────────────────────────────────────
#
# `permission_skip`, `agent_select`, `tool_allowlist`, and `workspace_sandboxed`
# are tested here, both directions, against each *real* runner's own
# `build_streaming` — never the fake, since `FakeHostRunner.build_streaming()`
# always returns `args=[prompt]` regardless of the capabilities override, so a
# fake-based test for these four flags would be vacuous in both directions
# (see the issue's "Design Decision: capability assertions are argv facts, not
# event facts"). `structured_output` and `streaming` are exercised elsewhere
# against directly-constructed fake invocations (`_structured_output_args` /
# capability round-trip) and are out of scope for this section.
#
# `permission_skip` is True for every wired runner below — there is no real
# runner with `permission_skip=False`, so it is positive-direction-only per
# the issue. For `omp` and `kimi-code` the skip is *implicit* (no CLI flag
# exists at all — see each host's `report_rows` in `RUNTIME_HOST_CAPABILITIES`),
# so the marker is the `DANGEROUSLY_SKIP_PERMISSIONS` env signal every
# `build_streaming` call sets unconditionally, rather than an argv token.
#
# `workspace_sandboxed`'s marker is `--permission-mode` (the flag that
# *replaces* Claude Code's blanket `--dangerously-skip-permissions` bypass
# with a real jail), not `--add-dir`/`--include-directories` alone: kimi and
# qwen both accept `workspace_root` and emit a directory flag, but their own
# `RUNTIME_HOST_CAPABILITIES` report_rows say it "widens rather than confines
# access" (additive, not a jail) — `workspace_sandboxed` stays False there,
# so the marker must be something that is genuinely absent for them too.


class TestCapabilityArgvPermissionSkip:
    """Positive-only: no wired runner declares permission_skip=False."""

    def test_capability_argv_positive_claude_code_permission_skip(self) -> None:
        invocation = ClaudeCodeRunner().build_streaming(prompt="hi")
        assert_capability_argv(
            invocation,
            "permission_skip",
            marker_present="--dangerously-skip-permissions" in invocation.args,
        )

    def test_capability_argv_positive_codex_permission_skip(self) -> None:
        invocation = CodexRunner().build_streaming(prompt="hi")
        assert_capability_argv(
            invocation,
            "permission_skip",
            marker_present="--dangerously-bypass-approvals-and-sandbox" in invocation.args,
        )

    def test_capability_argv_positive_gemini_permission_skip(self) -> None:
        invocation = GeminiRunner().build_streaming(prompt="hi")
        assert_capability_argv(
            invocation,
            "permission_skip",
            marker_present="--approval-mode" in invocation.args and "yolo" in invocation.args,
        )

    def test_capability_argv_positive_omp_permission_skip(self) -> None:
        """omp: "implicit — print mode has no interactive approval prompts;
        no bypass flag exists or is needed" (report_rows); the only argv-
        adjacent marker is the env signal every build_streaming call sets."""
        invocation = OmpRunner().build_streaming(prompt="hi")
        assert_capability_argv(
            invocation,
            "permission_skip",
            marker_present=invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1",
        )

    def test_capability_argv_positive_kimi_code_permission_skip(self) -> None:
        """kimi-code: "implicit in -p print mode (auto permission policy);
        --yolo/--auto/--plan are rejected with -p" (report_rows) — same
        env-signal marker as omp."""
        invocation = KimiRunner().build_streaming(prompt="hi")
        assert_capability_argv(
            invocation,
            "permission_skip",
            marker_present=invocation.env.get("DANGEROUSLY_SKIP_PERMISSIONS") == "1",
        )

    def test_capability_argv_positive_qwen_permission_skip(self) -> None:
        invocation = QwenRunner().build_streaming(prompt="hi")
        assert_capability_argv(
            invocation, "permission_skip", marker_present="--yolo" in invocation.args
        )


class TestCapabilityArgvAgentSelect:
    def test_capability_argv_positive_claude_code_agent_select(self) -> None:
        invocation = ClaudeCodeRunner().build_streaming(prompt="hi", agent="general-purpose")
        assert_capability_argv(
            invocation, "agent_select", marker_present="--agent" in invocation.args
        )

    def test_capability_argv_positive_kimi_code_agent_select(self) -> None:
        invocation = KimiRunner().build_streaming(prompt="hi", agent="explore")
        assert_capability_argv(
            invocation, "agent_select", marker_present="--agent" in invocation.args
        )

    def test_capability_argv_negative_codex_agent_select(self, tmp_path: Path) -> None:
        """codex's agent_select bool is False even though a
        .codex/agents/<name>.toml can inject a persona prefix (partial
        support, ENH-1533); with no TOML present the fallback warns and the
        persona marker is absent (mirrors
        test_build_streaming_emits_warning_for_agent_when_toml_absent,
        test_host_runner.py:761-767)."""
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(
                prompt="hi", agent="ghost-agent", working_dir=tmp_path
            )
        assert_capability_argv(
            invocation, "agent_select", marker_present="[Persona:" in invocation.args[-1]
        )

    def test_capability_argv_negative_gemini_agent_select(self) -> None:
        runner = GeminiRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(prompt="hi", agent="general-purpose")
        assert_capability_argv(
            invocation, "agent_select", marker_present="--agent" in invocation.args
        )

    def test_capability_argv_negative_omp_agent_select(self) -> None:
        runner = OmpRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(prompt="hi", agent="general-purpose")
        assert_capability_argv(
            invocation, "agent_select", marker_present="--agent" in invocation.args
        )

    def test_capability_argv_negative_qwen_agent_select(self) -> None:
        runner = QwenRunner()
        with pytest.warns(CapabilityNotSupported, match="agent"):
            invocation = runner.build_streaming(prompt="hi", agent="explore")
        assert_capability_argv(
            invocation, "agent_select", marker_present="--agent" in invocation.args
        )


class TestCapabilityArgvToolAllowlist:
    def test_capability_argv_positive_claude_code_tool_allowlist(self) -> None:
        invocation = ClaudeCodeRunner().build_streaming(prompt="hi", tools=["Read", "Edit"])
        assert_capability_argv(
            invocation, "tool_allowlist", marker_present="--tools" in invocation.args
        )

    def test_capability_argv_positive_omp_tool_allowlist(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = OmpRunner().build_streaming(prompt="hi", tools=["read", "edit"])
        assert_capability_argv(
            invocation, "tool_allowlist", marker_present="--tools" in invocation.args
        )

    def test_capability_argv_negative_codex_tool_allowlist(self) -> None:
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            invocation = runner.build_streaming(prompt="hi", tools=["Read", "Edit"])
        assert_capability_argv(
            invocation, "tool_allowlist", marker_present="--tools" in invocation.args
        )

    def test_capability_argv_negative_gemini_tool_allowlist(self) -> None:
        runner = GeminiRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            invocation = runner.build_streaming(prompt="hi", tools=["Read", "Edit"])
        assert_capability_argv(
            invocation, "tool_allowlist", marker_present="--tools" in invocation.args
        )

    def test_capability_argv_negative_kimi_code_tool_allowlist(self) -> None:
        runner = KimiRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            invocation = runner.build_streaming(prompt="hi", tools=["Read", "Edit"])
        assert_capability_argv(
            invocation, "tool_allowlist", marker_present="--tools" in invocation.args
        )

    def test_capability_argv_negative_qwen_tool_allowlist(self) -> None:
        runner = QwenRunner()
        with pytest.warns(CapabilityNotSupported, match="tool"):
            invocation = runner.build_streaming(prompt="hi", tools=["read_file", "edit"])
        assert_capability_argv(
            invocation, "tool_allowlist", marker_present="--tools" in invocation.args
        )


class TestCapabilityArgvWorkspaceSandboxed:
    def test_capability_argv_positive_claude_code_workspace_sandboxed(self, tmp_path: Path) -> None:
        """FEAT-2878: workspace_root swaps the blanket
        --dangerously-skip-permissions bypass for --permission-mode
        acceptEdits + --add-dir; --permission-mode is the jail marker
        (--add-dir alone is not, per the class docstring above)."""
        invocation = ClaudeCodeRunner().build_streaming(prompt="hi", workspace_root=tmp_path)
        assert_capability_argv(
            invocation,
            "workspace_sandboxed",
            marker_present="--permission-mode" in invocation.args,
        )

    def test_capability_argv_negative_codex_workspace_sandboxed(self, tmp_path: Path) -> None:
        runner = CodexRunner()
        with pytest.warns(CapabilityNotSupported, match="workspace"):
            invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        assert_capability_argv(
            invocation,
            "workspace_sandboxed",
            marker_present="--permission-mode" in invocation.args,
        )

    def test_capability_argv_negative_gemini_workspace_sandboxed(self, tmp_path: Path) -> None:
        runner = GeminiRunner()
        with pytest.warns(CapabilityNotSupported, match="workspace"):
            invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        assert_capability_argv(
            invocation,
            "workspace_sandboxed",
            marker_present="--permission-mode" in invocation.args,
        )

    def test_capability_argv_negative_omp_workspace_sandboxed(self, tmp_path: Path) -> None:
        runner = OmpRunner()
        with pytest.warns(CapabilityNotSupported, match="workspace"):
            invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        assert_capability_argv(
            invocation,
            "workspace_sandboxed",
            marker_present="--permission-mode" in invocation.args,
        )

    def test_capability_argv_negative_kimi_code_workspace_sandboxed(self, tmp_path: Path) -> None:
        """kimi's --add-dir is additive, not a jail (report_rows) — no
        CapabilityNotSupported warning fires (the parameter IS honored as a
        directory grant), but no --permission-mode-style restriction flag
        exists either, so the sandboxed marker stays absent."""
        runner = KimiRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        assert "--add-dir" in invocation.args  # sanity: the directory IS widened
        assert_capability_argv(
            invocation,
            "workspace_sandboxed",
            marker_present="--permission-mode" in invocation.args,
        )

    def test_capability_argv_negative_qwen_workspace_sandboxed(self, tmp_path: Path) -> None:
        """qwen's --include-directories is additive, not a jail — same
        posture as kimi's --add-dir; no warning fires and no restriction
        flag is emitted."""
        runner = QwenRunner()
        with warnings.catch_warnings():
            warnings.simplefilter("error", CapabilityNotSupported)
            invocation = runner.build_streaming(prompt="hi", workspace_root=tmp_path)
        assert "--include-directories" in invocation.args  # sanity: widened, not jailed
        assert_capability_argv(
            invocation,
            "workspace_sandboxed",
            marker_present="--permission-mode" in invocation.args,
        )


class TestCapabilityArgvFakeOnly:
    """`structured_output`/`streaming` (FEAT-3455): the two flags exercisable on the fake.

    Every other flag is vacuous on `FakeHostRunner.build_streaming()` — it
    always returns `args=[prompt]` regardless of the capabilities override
    (see the module-level note above `TestCapabilityArgvPermissionSkip`).
    `structured_output` has an independent, spawn-free test path via
    `_structured_output_args()`, which reads `invocation.capabilities`
    directly rather than depending on `build_streaming()`'s own args list.
    `streaming` has no argv consumption anywhere; the fake executable never
    sees capabilities (what it emits is decided by the `@@fake` script), so
    the only assertion is that the override round-trips into
    `invocation.capabilities`.
    """

    def test_capability_argv_negative_structured_output(self, tmp_path: Path) -> None:
        runner = FakeHostRunner(capabilities=HostCapabilities(structured_output=False))
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        args = _structured_output_args(invocation, {"type": "object"})
        assert_capability_argv(
            invocation, "structured_output", marker_present="--json-schema" in args
        )

    def test_capability_argv_positive_structured_output(self, tmp_path: Path) -> None:
        runner = FakeHostRunner(capabilities=HostCapabilities(structured_output=True))
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        args = _structured_output_args(invocation, {"type": "object"})
        assert_capability_argv(
            invocation, "structured_output", marker_present="--json-schema" in args
        )

    def test_capability_argv_negative_streaming(self, tmp_path: Path) -> None:
        runner = FakeHostRunner(capabilities=HostCapabilities(streaming=False))
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        assert invocation.capabilities.streaming is False

    def test_capability_argv_positive_streaming(self, tmp_path: Path) -> None:
        runner = FakeHostRunner(capabilities=HostCapabilities(streaming=True))
        invocation = runner.build_streaming(prompt="hi", working_dir=tmp_path)
        assert invocation.capabilities.streaming is True


# ── Tier 2: scripted-exact scenarios (fake only, FEAT-3455) ───────────────
#
# Never skip: FEAT-3454's session-start PATH prepend makes `ll-fake-host`
# resolvable in every job, so a missing binary here is a failure, not a
# skip. Not filtered by --conformance-host <real-host> — these are the
# suite's spawn-path regression coverage, independent of which real host a
# maintainer is validating live.

_TIER2_TIMEOUT = 30


def test_scripted_ordering(tmp_path: Path, isolated_env: None) -> None:
    prompt = (
        '@@fake\ninit model=m session=s\ntext a\ntool T {"k":1}\ntext b\nresult in=1 out=2\n@@end\n'
    )
    obs = _run_and_capture("fake", prompt, timeout=_TIER2_TIMEOUT, tmp_path=tmp_path)
    assert_event_kinds(obs, ["init", "text", "tool", "text", "usage"], host="fake", case="ordering")
    assert obs.completed is not None
    assert obs.completed.stdout == "a\nb"
    assert obs.result_seen is True
    assert obs.completed.returncode == 0


def test_scripted_result_error(tmp_path: Path, isolated_env: None) -> None:
    prompt = "@@fake\ninit model=m session=s\nresult error=boom in=1 out=1\n@@end\n"
    obs = _run_and_capture("fake", prompt, timeout=_TIER2_TIMEOUT, tmp_path=tmp_path)
    assert obs.completed is not None
    assert obs.completed.stderr == "[result] boom"
    assert obs.result_seen is True
    assert obs.completed.returncode == 0


def test_scripted_exit_before_terminal(tmp_path: Path, isolated_env: None) -> None:
    prompt = "@@fake\ninit model=m session=s\ntext a\nexit 3\n@@end\n"
    obs = _run_and_capture("fake", prompt, timeout=_TIER2_TIMEOUT, tmp_path=tmp_path)
    assert obs.completed is not None
    assert obs.completed.returncode == 3
    assert obs.result_seen is False
    assert obs.completed.stdout == "a"


def test_scripted_failed_start(tmp_path: Path, isolated_env: None) -> None:
    prompt = "@@fake\nstderr no auth\nexit 1\n@@end\n"
    obs = _run_and_capture("fake", prompt, timeout=_TIER2_TIMEOUT, tmp_path=tmp_path)
    assert obs.completed is not None
    assert obs.completed.returncode == 1
    assert obs.completed.stderr == "no auth"
    assert obs.model is None
    assert "init" not in obs.kinds


def test_scripted_idle_timeout(tmp_path: Path, isolated_env: None) -> None:
    prompt = "@@fake\ninit model=m session=s\ntext working\nsleep 5\nresult in=1 out=1\n@@end\n"
    obs = _run_and_capture(
        "fake",
        prompt,
        timeout=_TIER2_TIMEOUT,
        tmp_path=tmp_path,
        automation=AutomationContext(idle_timeout=1),
    )
    assert isinstance(obs.error, subprocess.TimeoutExpired)
    assert obs.error.output == "idle_timeout"
    assert obs.result_seen is None
    assert "init" in obs.kinds and "text" in obs.kinds
    assert_group_gone(obs)


def test_scripted_abort_request_shutdown(tmp_path: Path, isolated_env: None) -> None:
    clear_shutdown()
    prompt = "@@fake\ninit model=m session=s\ntext working\nsleep 5\nresult in=1 out=1\n@@end\n"
    try:
        obs = _run_and_capture(
            "fake",
            prompt,
            timeout=_TIER2_TIMEOUT,
            tmp_path=tmp_path,
            on_text=lambda line: request_shutdown() if line == "working" else None,
        )
        assert isinstance(obs.error, subprocess.TimeoutExpired)
        assert obs.error.output == "interrupted"
        assert obs.result_seen is None
        assert_group_gone(obs)
    finally:
        clear_shutdown()


def test_scripted_hang_wall_clock(tmp_path: Path, isolated_env: None) -> None:
    prompt = "@@fake\ninit model=m session=s\nhang\n@@end\n"
    obs = _run_and_capture("fake", prompt, timeout=1, tmp_path=tmp_path)
    assert isinstance(obs.error, subprocess.TimeoutExpired)
    assert obs.error.output is None
    assert_group_gone(obs)


def test_scripted_result_then_hang_grace_kill(tmp_path: Path, isolated_env: None) -> None:
    prompt = "@@fake\ninit model=m session=s\nresult in=1 out=1\nhang\n@@end\n"
    obs = _run_and_capture(
        "fake",
        prompt,
        timeout=_TIER2_TIMEOUT,
        tmp_path=tmp_path,
        post_stream_close_grace_seconds=1,
    )
    assert obs.error is None
    assert obs.result_seen is True
    assert obs.completed is not None
    assert obs.completed.returncode < 0
    assert_group_gone(obs)
