"""Adaptive host memory-pressure guard for the FSM executor (ENH-2452 / ENH-2453).

Two tiers of host-pressure defense for long-running loops:

1. **Adaptive pressure gate** (ENH-2452): before each prompt-mode state the
   executor samples system memory via a lightweight probe (``vm_stat`` on
   macOS, ``/proc/meminfo`` on Linux — no psutil dependency). When usage
   exceeds ``warn_pct`` the runner sleeps an extra ``cooldown_ms`` on top of
   the ``--delay`` base floor; when it exceeds ``critical_pct`` the runner
   routes to ``pressure_state`` or aborts, per ``on_pressure``.
2. **Cumulative subprocess RSS budget** (ENH-2453): peak RSS of each spawned
   subprocess is sampled while it runs and accumulated across the run. When
   the sum exceeds ``max_cumulative_subproc_mb`` the runner routes to
   ``budget_state`` or aborts, per ``on_budget_exceeded``.

The guard is a *routing* signal, not a containment mechanism — macOS has no
cgroup/RLIMIT_RSS enforcement, so the loop reacts to measured pressure rather
than being hard-capped.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Event names emitted by the executor when the guard fires.
HOST_PRESSURE_EVENT: str = "host_pressure"
HOST_PRESSURE_RELIEVED_EVENT: str = "host_pressure_relieved"
HOST_PRESSURE_ABORT_EVENT: str = "host_pressure_abort"
HOST_COOLDOWN_EVENT: str = "host_cooldown"
HOST_SUBPROC_RSS_EVENT: str = "host_subproc_rss"
HOST_BUDGET_EXCEEDED_EVENT: str = "host_budget_exceeded"

# Valid values for HostGuardConfig.on_pressure.
ON_PRESSURE_VALUES: frozenset[str] = frozenset({"cool_down", "route", "abort"})
# Valid values for HostGuardConfig.on_budget_exceeded.
ON_BUDGET_VALUES: frozenset[str] = frozenset({"route", "abort"})

# Default probe timeout (seconds) for the vm_stat / ps shell-outs.
_PROBE_TIMEOUT: int = 5


@dataclass
class HostGuardConfig:
    """Configuration for the ``host_guard:`` loop YAML block.

    Attributes:
        enabled: Master switch (default True; disable with ``--no-host-guard``).
        cooldown_ms: Extra sleep (milliseconds) added on top of the base
            ``--delay`` floor when used memory >= ``warn_pct``.
        warn_pct: Host used-memory percentage that triggers the extra cooldown.
        critical_pct: Host used-memory percentage that triggers ``on_pressure``.
        on_pressure: Behavior at ``critical_pct``: ``"cool_down"`` (extra sleep
            only — the conservative default so undeclared loops are never
            re-routed), ``"route"`` (go to ``pressure_state``), or ``"abort"``
            (finish as ``host_pressure_abort``).
        pressure_state: Recovery state name; required when ``on_pressure="route"``.
        on_abort_route: Optional final state name recorded when
            ``on_pressure="abort"`` fires.
        max_cumulative_subproc_mb: Cap on summed peak subprocess RSS across the
            run (ENH-2453). 0 = disabled (default).
        on_budget_exceeded: ``"route"`` (go to ``budget_state``) or ``"abort"``.
        budget_state: Recovery state name; required when
            ``on_budget_exceeded="route"`` and the budget is enabled.
    """

    enabled: bool = True
    cooldown_ms: int = 500
    warn_pct: float = 75.0
    critical_pct: float = 85.0
    on_pressure: str = "cool_down"
    pressure_state: str | None = None
    on_abort_route: str | None = None
    max_cumulative_subproc_mb: int = 0
    on_budget_exceeded: str = "route"
    budget_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization (skip-if-default)."""
        result: dict[str, Any] = {}
        if not self.enabled:
            result["enabled"] = self.enabled
        if self.cooldown_ms != 500:
            result["cooldown_ms"] = self.cooldown_ms
        if self.warn_pct != 75.0:
            result["warn_pct"] = self.warn_pct
        if self.critical_pct != 85.0:
            result["critical_pct"] = self.critical_pct
        if self.on_pressure != "cool_down":
            result["on_pressure"] = self.on_pressure
        if self.pressure_state is not None:
            result["pressure_state"] = self.pressure_state
        if self.on_abort_route is not None:
            result["on_abort_route"] = self.on_abort_route
        if self.max_cumulative_subproc_mb != 0:
            result["max_cumulative_subproc_mb"] = self.max_cumulative_subproc_mb
        if self.on_budget_exceeded != "route":
            result["on_budget_exceeded"] = self.on_budget_exceeded
        if self.budget_state is not None:
            result["budget_state"] = self.budget_state
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HostGuardConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            enabled=data.get("enabled", True),
            cooldown_ms=data.get("cooldown_ms", 500),
            warn_pct=float(data.get("warn_pct", 75.0)),
            critical_pct=float(data.get("critical_pct", 85.0)),
            on_pressure=data.get("on_pressure", "cool_down"),
            pressure_state=data.get("pressure_state"),
            on_abort_route=data.get("on_abort_route"),
            max_cumulative_subproc_mb=data.get("max_cumulative_subproc_mb", 0),
            on_budget_exceeded=data.get("on_budget_exceeded", "route"),
            budget_state=data.get("budget_state"),
        )


# ---------------------------------------------------------------------------
# Memory probes (no psutil)
# ---------------------------------------------------------------------------

_VM_STAT_PAGE_SIZE_RE = re.compile(r"page size of (\d+) bytes")
_VM_STAT_LINE_RE = re.compile(r"^\s*(?:Pages\s+)?\"?([A-Za-z -]+?)\"?\s*:\s*(\d+)\.?\s*$")


def parse_vm_stat(output: str) -> float | None:
    """Parse macOS ``vm_stat`` output into a used-memory percentage.

    Used = active + wired + compressor pages; total additionally includes
    free, inactive, and speculative pages. Returns None when the output is
    unparseable.
    """
    pages: dict[str, int] = {}
    for line in output.splitlines():
        m = _VM_STAT_LINE_RE.match(line)
        if m:
            pages[m.group(1).strip().lower()] = int(m.group(2))

    def _page(name: str) -> int:
        return pages.get(name, 0)

    free = _page("free")
    active = _page("active")
    inactive = _page("inactive")
    speculative = _page("speculative")
    wired = _page("wired down")
    compressed = _page("occupied by compressor")
    total = free + active + inactive + speculative + wired + compressed
    if total <= 0:
        return None
    used = active + wired + compressed
    return 100.0 * used / total


def parse_meminfo(text: str) -> float | None:
    """Parse Linux ``/proc/meminfo`` content into a used-memory percentage.

    Uses ``MemAvailable`` (kernel's estimate of reclaimable memory) against
    ``MemTotal``. Returns None when either field is missing or invalid.
    """
    fields: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[key.strip()] = int(parts[0])
    total = fields.get("MemTotal", 0)
    available = fields.get("MemAvailable")
    if total <= 0 or available is None:
        return None
    return 100.0 * (1.0 - available / total)


def read_memory_pressure(meminfo_path: Path = Path("/proc/meminfo")) -> float | None:
    """Return the host's used-memory percentage, or None when unavailable.

    macOS: shells out to ``vm_stat``. Linux: reads ``/proc/meminfo``.
    Any probe failure (missing binary, timeout, parse error) returns None so
    the guard degrades to a no-op rather than breaking the loop.
    """
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=_PROBE_TIMEOUT
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        return parse_vm_stat(proc.stdout)
    try:
        text = meminfo_path.read_text()
    except OSError:
        return None
    return parse_meminfo(text)


# ---------------------------------------------------------------------------
# Per-subprocess RSS sampling (ENH-2453)
# ---------------------------------------------------------------------------


def sample_rss_mb(pid: int) -> float | None:
    """Sample a live process's resident memory in MB, or None when unavailable.

    Linux: prefers ``VmHWM`` (peak RSS) from ``/proc/<pid>/status``, falling
    back to ``VmRSS``. Other platforms (macOS): ``ps -o rss= -p <pid>`` which
    reports current RSS in KB — callers should track the max across samples.
    """
    status_path = Path(f"/proc/{pid}/status")
    if status_path.exists():
        try:
            text = status_path.read_text()
        except OSError:
            return None
        current: float | None = None
        for line in text.splitlines():
            if line.startswith(("VmHWM:", "VmRSS:")):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    if line.startswith("VmHWM:"):
                        return int(parts[1]) / 1024.0
                    current = int(parts[1]) / 1024.0
        return current
    try:
        proc = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip()
    if proc.returncode != 0 or not value:
        return None
    try:
        return float(value) / 1024.0
    except ValueError:
        return None


class RssSampler:
    """Background thread sampling a subprocess's RSS while it runs.

    Samples every ``interval`` seconds via ``sample_fn`` (default
    :func:`sample_rss_mb`) and tracks the peak. Start it right after spawning
    the subprocess and call :meth:`stop` after the process exits; ``peak_mb``
    then holds the highest observed sample (None when no sample succeeded).
    """

    def __init__(
        self,
        pid: int,
        interval: float = 1.0,
        sample_fn: Callable[[int], float | None] = sample_rss_mb,
    ) -> None:
        """Initialize the sampler for ``pid`` without starting the thread."""
        self.pid = pid
        self.interval = interval
        self.sample_fn = sample_fn
        self.peak_mb: float | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Take an immediate first sample and begin periodic sampling."""
        self._record_sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> float | None:
        """Stop sampling, take a final sample, and return the peak in MB."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1.0)
            self._thread = None
        self._record_sample()
        return self.peak_mb

    def _record_sample(self) -> None:
        sample = self.sample_fn(self.pid)
        if sample is not None and (self.peak_mb is None or sample > self.peak_mb):
            self.peak_mb = sample

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            self._record_sample()


# ---------------------------------------------------------------------------
# Guard runtime
# ---------------------------------------------------------------------------


@dataclass
class GuardDecision:
    """Outcome of a single pre-state guard check.

    Attributes:
        action: One of ``"ok"``, ``"cooldown"``, ``"route"``, ``"abort"``.
        used_pct: Sampled used-memory percentage (None = probe unavailable).
        cooldown_seconds: Extra sleep to apply when ``action="cooldown"``.
        target: Route target (``pressure_state``) or abort final state
            (``on_abort_route``) when set.
        relieved: True when pressure previously crossed ``critical_pct`` and
            has now dropped back below ``warn_pct``.
    """

    action: str
    used_pct: float | None = None
    cooldown_seconds: float = 0.0
    target: str | None = None
    relieved: bool = False


class HostGuard:
    """Runtime companion to :class:`HostGuardConfig`.

    Holds the per-run pressure latch (for ``host_pressure_relieved``) and the
    cumulative subprocess RSS accumulator (ENH-2453). The executor owns event
    emission and sleeping; this class only decides.
    """

    def __init__(
        self,
        config: HostGuardConfig,
        probe: Callable[[], float | None] = read_memory_pressure,
    ) -> None:
        """Initialize the guard.

        Args:
            config: The loop's ``host_guard:`` configuration.
            probe: Used-memory percentage sampler (injectable for tests).
        """
        self.config = config
        self._probe = probe
        self._pressure_active = False
        self.cumulative_subproc_mb: float = 0.0
        self.subproc_samples: list[tuple[str, float]] = []
        self._budget_fired = False

    def pre_state(self) -> GuardDecision:
        """Sample host memory and decide what the executor should do.

        Returns a :class:`GuardDecision`; probe failures yield an ``"ok"``
        decision with ``used_pct=None`` so the loop proceeds unimpeded.
        """
        used_pct = self._probe()
        if used_pct is None:
            return GuardDecision(action="ok")

        relieved = self._pressure_active and used_pct < self.config.warn_pct
        if relieved:
            self._pressure_active = False

        cooldown_seconds = max(self.config.cooldown_ms, 0) / 1000.0

        if used_pct >= self.config.critical_pct:
            self._pressure_active = True
            if self.config.on_pressure == "route" and self.config.pressure_state:
                return GuardDecision(
                    action="route", used_pct=used_pct, target=self.config.pressure_state
                )
            if self.config.on_pressure == "abort":
                return GuardDecision(
                    action="abort", used_pct=used_pct, target=self.config.on_abort_route
                )
            # cool_down (or route with a missing pressure_state): sleep extra.
            return GuardDecision(
                action="cooldown", used_pct=used_pct, cooldown_seconds=cooldown_seconds
            )

        if used_pct >= self.config.warn_pct:
            return GuardDecision(
                action="cooldown",
                used_pct=used_pct,
                cooldown_seconds=cooldown_seconds,
                relieved=relieved,
            )

        return GuardDecision(action="ok", used_pct=used_pct, relieved=relieved)

    @property
    def budget_enabled(self) -> bool:
        """True when the cumulative subprocess RSS budget is active."""
        return self.config.max_cumulative_subproc_mb > 0

    def record_subproc_rss(self, label: str, peak_rss_mb: float) -> bool:
        """Accumulate one subprocess's peak RSS into the run total.

        Args:
            label: Identifier for the sample (state name or PID string).
            peak_rss_mb: Peak resident memory of the subprocess in MB.

        Returns:
            True exactly once — when the cumulative sum first crosses
            ``max_cumulative_subproc_mb`` (and the budget is enabled).
        """
        self.cumulative_subproc_mb += peak_rss_mb
        self.subproc_samples.append((label, peak_rss_mb))
        if (
            self.budget_enabled
            and not self._budget_fired
            and self.cumulative_subproc_mb > self.config.max_cumulative_subproc_mb
        ):
            self._budget_fired = True
            return True
        return False


__all__ = [
    "HOST_BUDGET_EXCEEDED_EVENT",
    "HOST_COOLDOWN_EVENT",
    "HOST_PRESSURE_ABORT_EVENT",
    "HOST_PRESSURE_EVENT",
    "HOST_PRESSURE_RELIEVED_EVENT",
    "HOST_SUBPROC_RSS_EVENT",
    "GuardDecision",
    "HostGuard",
    "HostGuardConfig",
    "RssSampler",
    "parse_meminfo",
    "parse_vm_stat",
    "read_memory_pressure",
    "sample_rss_mb",
]
