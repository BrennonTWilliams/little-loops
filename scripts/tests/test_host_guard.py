"""Tests for the FSM host memory-pressure guard (ENH-2452 / ENH-2453)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.host_guard import (
    GuardDecision,
    HostGuard,
    HostGuardConfig,
    RssSampler,
    parse_meminfo,
    parse_vm_stat,
    read_memory_pressure,
    sample_rss_mb,
)
from little_loops.fsm.runners import DefaultActionRunner
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig
from little_loops.fsm.types import ActionResult
from little_loops.fsm.validation import validate_fsm

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

VM_STAT_SAMPLE = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               50000.
Pages active:                            200000.
Pages inactive:                          100000.
Pages speculative:                        10000.
Pages throttled:                              0.
Pages wired down:                         80000.
Pages purgeable:                           5000.
"Translation faults":                 123456789.
Pages copy-on-write:                    1234567.
Pages occupied by compressor:             60000.
Pages stored in compressor:              120000.
"""

MEMINFO_SAMPLE = """\
MemTotal:       16384000 kB
MemFree:         2048000 kB
MemAvailable:    4096000 kB
Buffers:          512000 kB
Cached:          3072000 kB
"""


@dataclass
class RssActionRunner:
    """Action runner returning a fixed peak RSS per call (ENH-2453 tests)."""

    peak_rss_mb: float | None = 500.0
    exit_code: int = 0
    calls: list[str] = field(default_factory=list)

    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        """Return a canned result carrying the configured peak RSS."""
        del timeout, is_slash_command, kwargs
        self.calls.append(action)
        return ActionResult(
            output="ok",
            stderr="",
            exit_code=self.exit_code,
            duration_ms=10,
            peak_rss_mb=self.peak_rss_mb,
        )


def make_prompt_fsm(host_guard: HostGuardConfig, **extra_states: StateConfig) -> FSMLoop:
    """Build a minimal FSM with one prompt-mode state routing to done."""
    states: dict[str, StateConfig] = {
        "check": StateConfig(
            action="/ll:some-skill",
            action_type="prompt",
            evaluate=EvaluateConfig(type="exit_code"),
            on_yes="done",
            on_no="failed",
        ),
        "done": StateConfig(terminal=True),
        "failed": StateConfig(terminal=True),
    }
    states.update(extra_states)
    return FSMLoop(name="test-guard", initial="check", states=states, host_guard=host_guard)


def collect_events(executor: FSMExecutor) -> list[dict[str, Any]]:
    """Attach an event collector to an executor and return the sink list."""
    events: list[dict[str, Any]] = []
    executor.event_callback = events.append
    return events


# ---------------------------------------------------------------------------
# HostGuardConfig
# ---------------------------------------------------------------------------


class TestHostGuardConfig:
    """Dataclass defaults and serialization."""

    def test_defaults(self) -> None:
        cfg = HostGuardConfig()
        assert cfg.enabled is True
        assert cfg.cooldown_ms == 500
        assert cfg.warn_pct == 75.0
        assert cfg.critical_pct == 85.0
        assert cfg.on_pressure == "cool_down"
        assert cfg.pressure_state is None
        assert cfg.max_cumulative_subproc_mb == 0
        assert cfg.on_budget_exceeded == "route"
        assert cfg.budget_state is None

    def test_to_dict_skips_defaults(self) -> None:
        assert HostGuardConfig().to_dict() == {}

    def test_roundtrip(self) -> None:
        cfg = HostGuardConfig(
            enabled=False,
            cooldown_ms=1000,
            warn_pct=60,
            critical_pct=90,
            on_pressure="route",
            pressure_state="paused",
            on_abort_route="failed",
            max_cumulative_subproc_mb=4096,
            on_budget_exceeded="abort",
            budget_state="out_of_resources",
        )
        assert HostGuardConfig.from_dict(cfg.to_dict()) == cfg

    def test_fsm_loop_roundtrip(self) -> None:
        fsm = FSMLoop(
            name="t",
            initial="a",
            states={"a": StateConfig(terminal=True)},
            host_guard=HostGuardConfig(on_pressure="abort", warn_pct=50.0),
        )
        data = fsm.to_dict()
        assert data["host_guard"] == {"warn_pct": 50.0, "on_pressure": "abort"}
        loaded = FSMLoop.from_dict(data)
        assert loaded.host_guard == fsm.host_guard

    def test_fsm_loop_default_omits_host_guard_key(self) -> None:
        fsm = FSMLoop(name="t", initial="a", states={"a": StateConfig(terminal=True)})
        assert "host_guard" not in fsm.to_dict()
        assert fsm.host_guard.enabled is True


# ---------------------------------------------------------------------------
# Memory probes
# ---------------------------------------------------------------------------


class TestProbes:
    """vm_stat / meminfo parsing and the platform dispatch."""

    def test_parse_vm_stat(self) -> None:
        pct = parse_vm_stat(VM_STAT_SAMPLE)
        assert pct is not None
        # used = active + wired + compressor = 340000; total = 500000
        assert abs(pct - 68.0) < 0.01

    def test_parse_vm_stat_unparseable(self) -> None:
        assert parse_vm_stat("garbage output") is None
        assert parse_vm_stat("") is None

    def test_parse_meminfo(self) -> None:
        pct = parse_meminfo(MEMINFO_SAMPLE)
        assert pct is not None
        # used fraction = 1 - 4096000/16384000 = 0.75
        assert abs(pct - 75.0) < 0.01

    def test_parse_meminfo_missing_available(self) -> None:
        assert parse_meminfo("MemTotal: 100 kB\n") is None
        assert parse_meminfo("") is None

    def test_read_memory_pressure_linux(self, tmp_path: Path) -> None:
        meminfo = tmp_path / "meminfo"
        meminfo.write_text(MEMINFO_SAMPLE)
        with patch("little_loops.fsm.host_guard.sys.platform", "linux"):
            pct = read_memory_pressure(meminfo_path=meminfo)
        assert pct is not None
        assert abs(pct - 75.0) < 0.01

    def test_read_memory_pressure_missing_meminfo(self, tmp_path: Path) -> None:
        with patch("little_loops.fsm.host_guard.sys.platform", "linux"):
            assert read_memory_pressure(meminfo_path=tmp_path / "nope") is None

    def test_read_memory_pressure_darwin(self) -> None:
        completed = MagicMock(returncode=0, stdout=VM_STAT_SAMPLE)
        with (
            patch("little_loops.fsm.host_guard.sys.platform", "darwin"),
            patch("little_loops.fsm.host_guard.subprocess.run", return_value=completed) as m,
        ):
            pct = read_memory_pressure()
        assert m.call_args.args[0] == ["vm_stat"]
        assert pct is not None
        assert abs(pct - 68.0) < 0.01

    def test_read_memory_pressure_darwin_probe_failure(self) -> None:
        with (
            patch("little_loops.fsm.host_guard.sys.platform", "darwin"),
            patch("little_loops.fsm.host_guard.subprocess.run", side_effect=OSError),
        ):
            assert read_memory_pressure() is None


class TestRssSampling:
    """sample_rss_mb and RssSampler."""

    def test_sample_rss_mb_own_pid_linux(self) -> None:
        import os

        if not Path("/proc").exists():  # pragma: no cover - macOS dev boxes
            return
        rss = sample_rss_mb(os.getpid())
        assert rss is not None
        assert rss > 0

    def test_sample_rss_mb_ps_fallback(self) -> None:
        completed = MagicMock(returncode=0, stdout=" 204800\n")
        with (
            patch("little_loops.fsm.host_guard.Path.exists", return_value=False),
            patch("little_loops.fsm.host_guard.subprocess.run", return_value=completed) as m,
        ):
            rss = sample_rss_mb(12345)
        assert m.call_args.args[0] == ["ps", "-o", "rss=", "-p", "12345"]
        assert rss == 200.0

    def test_sample_rss_mb_ps_dead_process(self) -> None:
        completed = MagicMock(returncode=1, stdout="")
        with (
            patch("little_loops.fsm.host_guard.Path.exists", return_value=False),
            patch("little_loops.fsm.host_guard.subprocess.run", return_value=completed),
        ):
            assert sample_rss_mb(99999999) is None

    def test_rss_sampler_tracks_peak(self) -> None:
        samples = iter([100.0, 300.0, 200.0])

        def fake_sample(pid: int) -> float | None:
            return next(samples, 150.0)

        sampler = RssSampler(pid=1, interval=0.01, sample_fn=fake_sample)
        sampler.start()
        import time

        time.sleep(0.05)
        peak = sampler.stop()
        assert peak == 300.0

    def test_rss_sampler_all_samples_fail(self) -> None:
        sampler = RssSampler(pid=1, interval=0.01, sample_fn=lambda pid: None)
        sampler.start()
        assert sampler.stop() is None


# ---------------------------------------------------------------------------
# HostGuard decisions
# ---------------------------------------------------------------------------


class TestHostGuardDecisions:
    """pre_state() threshold ladder."""

    def _guard(self, cfg: HostGuardConfig, pct: float | None) -> HostGuard:
        return HostGuard(cfg, probe=lambda: pct)

    def test_below_warn_is_ok(self) -> None:
        decision = self._guard(HostGuardConfig(), 50.0).pre_state()
        assert decision == GuardDecision(action="ok", used_pct=50.0)

    def test_probe_failure_is_ok(self) -> None:
        decision = self._guard(HostGuardConfig(), None).pre_state()
        assert decision.action == "ok"
        assert decision.used_pct is None

    def test_warn_triggers_cooldown(self) -> None:
        decision = self._guard(HostGuardConfig(cooldown_ms=250), 80.0).pre_state()
        assert decision.action == "cooldown"
        assert decision.cooldown_seconds == 0.25

    def test_critical_default_cool_down(self) -> None:
        decision = self._guard(HostGuardConfig(), 90.0).pre_state()
        assert decision.action == "cooldown"

    def test_critical_route(self) -> None:
        cfg = HostGuardConfig(on_pressure="route", pressure_state="paused")
        decision = self._guard(cfg, 90.0).pre_state()
        assert decision.action == "route"
        assert decision.target == "paused"

    def test_critical_route_without_pressure_state_degrades_to_cooldown(self) -> None:
        decision = self._guard(HostGuardConfig(on_pressure="route"), 90.0).pre_state()
        assert decision.action == "cooldown"

    def test_critical_abort(self) -> None:
        cfg = HostGuardConfig(on_pressure="abort", on_abort_route="failed")
        decision = self._guard(cfg, 90.0).pre_state()
        assert decision.action == "abort"
        assert decision.target == "failed"

    def test_relieved_latch(self) -> None:
        readings = iter([90.0, 60.0, 60.0])
        guard = HostGuard(HostGuardConfig(), probe=lambda: next(readings))
        first = guard.pre_state()
        assert first.action == "cooldown"
        second = guard.pre_state()
        assert second.action == "ok"
        assert second.relieved is True
        third = guard.pre_state()
        assert third.relieved is False  # latch cleared after one relief

    def test_budget_accumulator_fires_once(self) -> None:
        cfg = HostGuardConfig(max_cumulative_subproc_mb=1000)
        guard = HostGuard(cfg, probe=lambda: 10.0)
        assert guard.record_subproc_rss("a", 500.0) is False
        assert guard.record_subproc_rss("b", 600.0) is True  # crosses 1000
        assert guard.record_subproc_rss("c", 600.0) is False  # fires only once
        assert guard.cumulative_subproc_mb == 1700.0
        assert guard.subproc_samples == [("a", 500.0), ("b", 600.0), ("c", 600.0)]

    def test_budget_disabled_never_fires(self) -> None:
        guard = HostGuard(HostGuardConfig(), probe=lambda: 10.0)
        assert guard.budget_enabled is False
        assert guard.record_subproc_rss("a", 99999.0) is False


# ---------------------------------------------------------------------------
# Executor integration (ENH-2452)
# ---------------------------------------------------------------------------


class TestExecutorPressureGate:
    """FSMExecutor pre-state pressure routing/abort/cooldown."""

    def test_route_to_pressure_state(self) -> None:
        cfg = HostGuardConfig(on_pressure="route", pressure_state="paused")
        fsm = make_prompt_fsm(cfg, paused=StateConfig(terminal=True))
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        events = collect_events(executor)
        assert executor._host_guard is not None
        executor._host_guard._probe = lambda: 90.0

        result = executor.run()

        assert result.final_state == "paused"
        assert result.terminated_by == "terminal"
        pressure = [e for e in events if e["event"] == "host_pressure"]
        assert pressure and pressure[0]["action"] == "route:paused"
        routes = [e for e in events if e["event"] == "route" and e.get("reason") == "host_pressure"]
        assert routes and routes[0]["to"] == "paused"

    def test_abort_on_pressure(self) -> None:
        cfg = HostGuardConfig(on_pressure="abort", on_abort_route="failed")
        fsm = make_prompt_fsm(cfg)
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        events = collect_events(executor)
        assert executor._host_guard is not None
        executor._host_guard._probe = lambda: 95.0

        result = executor.run()

        assert result.terminated_by == "host_pressure_abort"
        assert result.final_state == "failed"
        names = [e["event"] for e in events]
        assert "host_pressure" in names
        assert "host_pressure_abort" in names

    def test_cooldown_emits_event_and_completes(self) -> None:
        cfg = HostGuardConfig(cooldown_ms=10)
        fsm = make_prompt_fsm(cfg)
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        events = collect_events(executor)
        assert executor._host_guard is not None
        executor._host_guard._probe = lambda: 80.0

        result = executor.run()

        assert result.final_state == "done"
        cooldowns = [e for e in events if e["event"] == "host_cooldown"]
        assert cooldowns
        assert cooldowns[0]["cooldown_seconds"] == 0.01
        assert cooldowns[0]["used_pct"] == 80.0

    def test_relieved_event_emitted(self) -> None:
        cfg = HostGuardConfig(cooldown_ms=1)
        fsm = FSMLoop(
            name="t",
            initial="a",
            states={
                "a": StateConfig(
                    action="/ll:x",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="b",
                ),
                "b": StateConfig(
                    action="/ll:y",
                    action_type="prompt",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
            host_guard=cfg,
        )
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        events = collect_events(executor)
        readings = iter([90.0, 50.0])
        assert executor._host_guard is not None
        executor._host_guard._probe = lambda: next(readings, 50.0)

        result = executor.run()

        assert result.final_state == "done"
        assert any(e["event"] == "host_pressure_relieved" for e in events)

    def test_disabled_guard_never_probes(self) -> None:
        cfg = HostGuardConfig(enabled=False)
        fsm = make_prompt_fsm(cfg)
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        events = collect_events(executor)

        assert executor._host_guard is None
        result = executor.run()

        assert result.final_state == "done"
        assert not [e for e in events if e["event"].startswith("host_")]

    def test_shell_states_skip_probe(self) -> None:
        calls: list[int] = []

        def probe() -> float:
            calls.append(1)
            return 99.0

        fsm = FSMLoop(
            name="t",
            initial="a",
            states={
                "a": StateConfig(action="echo hi", on_yes="done", on_no="done"),
                "done": StateConfig(terminal=True),
            },
            host_guard=HostGuardConfig(on_pressure="abort"),
        )
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        assert executor._host_guard is not None
        executor._host_guard._probe = probe

        result = executor.run()

        assert result.final_state == "done"
        assert calls == []  # shell action — guard never sampled

    def test_probe_failure_proceeds(self) -> None:
        fsm = make_prompt_fsm(HostGuardConfig(on_pressure="abort"))
        executor = FSMExecutor(fsm, action_runner=RssActionRunner())
        assert executor._host_guard is not None
        executor._host_guard._probe = lambda: None

        result = executor.run()

        assert result.final_state == "done"


# ---------------------------------------------------------------------------
# Executor integration (ENH-2453)
# ---------------------------------------------------------------------------


def make_budget_fsm(host_guard: HostGuardConfig) -> FSMLoop:
    """Three sequential prompt states plus terminal + recovery states."""
    return FSMLoop(
        name="t-budget",
        initial="a",
        states={
            "a": StateConfig(
                action="/ll:a",
                action_type="prompt",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="b",
            ),
            "b": StateConfig(
                action="/ll:b",
                action_type="prompt",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="c",
            ),
            "c": StateConfig(
                action="/ll:c",
                action_type="prompt",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
            ),
            "done": StateConfig(terminal=True),
            "out_of_resources": StateConfig(terminal=True),
        },
        host_guard=host_guard,
    )


class TestExecutorRssBudget:
    """Cumulative subprocess RSS budget routing and events."""

    def _low_pressure(self, executor: FSMExecutor) -> None:
        assert executor._host_guard is not None
        executor._host_guard._probe = lambda: 10.0

    def test_budget_route(self) -> None:
        cfg = HostGuardConfig(
            max_cumulative_subproc_mb=1200,
            on_budget_exceeded="route",
            budget_state="out_of_resources",
        )
        executor = FSMExecutor(make_budget_fsm(cfg), action_runner=RssActionRunner(500.0))
        events = collect_events(executor)
        self._low_pressure(executor)

        result = executor.run()

        # 500 + 500 = 1000 (ok), third spawn pushes to 1500 > 1200 → route
        assert result.final_state == "out_of_resources"
        assert result.terminated_by == "terminal"
        rss_events = [e for e in events if e["event"] == "host_subproc_rss"]
        assert len(rss_events) == 3
        assert rss_events[0]["peak_rss_mb"] == 500.0
        assert rss_events[2]["cumulative_mb"] == 1500.0
        assert rss_events[2]["budget_mb"] == 1200
        exceeded = [e for e in events if e["event"] == "host_budget_exceeded"]
        assert len(exceeded) == 1
        assert exceeded[0]["action"] == "route:out_of_resources"

    def test_budget_abort(self) -> None:
        cfg = HostGuardConfig(max_cumulative_subproc_mb=800, on_budget_exceeded="abort")
        executor = FSMExecutor(make_budget_fsm(cfg), action_runner=RssActionRunner(500.0))
        events = collect_events(executor)
        self._low_pressure(executor)

        result = executor.run()

        assert result.terminated_by == "host_budget_exceeded"
        assert result.error is not None
        assert "800" in result.error
        exceeded = [e for e in events if e["event"] == "host_budget_exceeded"]
        assert exceeded and exceeded[0]["action"] == "abort"

    def test_budget_disabled_no_rss_events(self) -> None:
        executor = FSMExecutor(make_budget_fsm(HostGuardConfig()), action_runner=RssActionRunner())
        events = collect_events(executor)
        self._low_pressure(executor)

        result = executor.run()

        assert result.final_state == "done"
        assert not [e for e in events if e["event"] == "host_subproc_rss"]

    def test_budget_enables_runner_sampling(self) -> None:
        cfg = HostGuardConfig(max_cumulative_subproc_mb=1000, budget_state="out_of_resources")
        executor = FSMExecutor(make_budget_fsm(cfg))
        assert isinstance(executor.action_runner, DefaultActionRunner)
        assert executor.action_runner.sample_rss is True

    def test_no_budget_leaves_runner_sampling_off(self) -> None:
        executor = FSMExecutor(make_budget_fsm(HostGuardConfig()))
        assert isinstance(executor.action_runner, DefaultActionRunner)
        assert executor.action_runner.sample_rss is False


class TestDefaultRunnerRssSampling:
    """DefaultActionRunner reports peak RSS when sampling is enabled."""

    def test_shell_action_samples_peak_rss(self) -> None:
        if not Path("/proc").exists():  # pragma: no cover - needs /proc
            return
        runner = DefaultActionRunner(sample_rss=True)
        result = runner.run("sleep 0.05; echo hi", timeout=10, is_slash_command=False)
        assert result.exit_code == 0
        assert result.peak_rss_mb is not None
        assert result.peak_rss_mb > 0

    def test_shell_action_sampling_disabled(self) -> None:
        runner = DefaultActionRunner()
        result = runner.run("echo hi", timeout=10, is_slash_command=False)
        assert result.peak_rss_mb is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestHostGuardValidation:
    """validate_fsm checks for the host_guard block."""

    def _fsm(self, cfg: HostGuardConfig) -> FSMLoop:
        return FSMLoop(
            name="t",
            initial="a",
            states={
                "a": StateConfig(action="echo", on_yes="done", on_no="done"),
                "done": StateConfig(terminal=True),
            },
            host_guard=cfg,
        )

    def _messages(self, cfg: HostGuardConfig) -> list[str]:
        return [str(e) for e in validate_fsm(self._fsm(cfg)) if "host_guard" in str(e)]

    def test_defaults_valid(self) -> None:
        assert self._messages(HostGuardConfig()) == []

    def test_route_requires_pressure_state(self) -> None:
        msgs = self._messages(HostGuardConfig(on_pressure="route"))
        assert any("pressure_state is required" in m for m in msgs)

    def test_pressure_state_must_be_declared(self) -> None:
        msgs = self._messages(HostGuardConfig(on_pressure="route", pressure_state="nope"))
        assert any("unknown state 'nope'" in m for m in msgs)

    def test_invalid_on_pressure_value(self) -> None:
        msgs = self._messages(HostGuardConfig(on_pressure="explode"))
        assert any("on_pressure" in m for m in msgs)

    def test_critical_below_warn(self) -> None:
        msgs = self._messages(HostGuardConfig(warn_pct=90, critical_pct=50))
        assert any("must be >= warn_pct" in m for m in msgs)

    def test_pct_out_of_range(self) -> None:
        msgs = self._messages(HostGuardConfig(warn_pct=150))
        assert any("between 0 and 100" in m for m in msgs)

    def test_budget_route_requires_budget_state(self) -> None:
        msgs = self._messages(HostGuardConfig(max_cumulative_subproc_mb=100))
        assert any("budget_state is required" in m for m in msgs)

    def test_budget_state_must_be_declared(self) -> None:
        msgs = self._messages(HostGuardConfig(max_cumulative_subproc_mb=100, budget_state="ghost"))
        assert any("unknown state 'ghost'" in m for m in msgs)

    def test_on_abort_route_must_be_declared(self) -> None:
        msgs = self._messages(HostGuardConfig(on_pressure="abort", on_abort_route="ghost"))
        assert any("on_abort_route" in m for m in msgs)

    def test_invalid_on_budget_exceeded(self) -> None:
        msgs = self._messages(
            HostGuardConfig(max_cumulative_subproc_mb=100, on_budget_exceeded="explode")
        )
        assert any("on_budget_exceeded" in m for m in msgs)
