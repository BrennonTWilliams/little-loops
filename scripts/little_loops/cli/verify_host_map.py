"""ll-verify-host-map: assert the adapter host-capability map agrees with its cross-checks (ENH-2873).

Three checks:

1. Every ``little_loops.adapters.capabilities.HOST_CAPABILITIES`` (build-time)
   key has a row in ``docs/reference/HOST_COMPATIBILITY.md``'s adapter-host
   section, and vice versa (a documented adapter host with no map entry).
2. ``host_runner.RUNTIME_HOST_CAPABILITIES`` (the runtime half, ENH-3453) does
   not drift from ``host_runner._HOST_RUNNER_REGISTRY``: every built-in
   registry host (excluding any ``host_runner.TEST_ONLY_HOSTS``, which are
   exempt from the runtime map) has exactly one runtime entry, that entry's
   ``host`` matches its key and its ``flags`` is identically the runner
   class's ``capabilities`` attribute, and no report row named after one of
   the six ``HostCapabilities`` flags is ``"full"`` while that flag is
   ``False``, nor ``"unsupported"`` while that flag is ``True`` (``"partial"``
   is legal in either direction). The build-time and runtime maps are
   disjoint by field name by design (see the Option B docstring in
   ``capabilities.py``), so this is not a field-agreement comparison.
3. Each entry's own ``agents``/``subagents``/``agent_output_format`` fields
   are mutually consistent (ENH-2883: since ``core.py``'s traversal
   functions dispatch from the map itself, there is no independent emitter
   behavior left to compare against — this is a same-dataclass
   self-consistency check, not a map-vs-emitter one). It flags
   ``agents=True`` with ``subagents == "none"`` but no ``agent_output_format``
   set (nothing for the degraded path to point at), or
   ``subagents == "native"`` with ``agents=False`` (a host that can spawn
   but is declared not to emit). ``omp`` declares ``agents=True`` /
   ``subagents="native"`` since FEAT-3104 (``OmpEmitter.emit_agent`` is a
   real native emitter). The same self-consistency shape applies to
   ``commands``/``command_output_format`` (FEAT-3105): every entry declaring
   ``commands=True`` must have a non-``None`` ``command_output_format``
   (nothing for a "True" commands claim to point at otherwise), across all
   hosts, not just ``omp``/``gemini`` by name.

Exit codes:
    0 - all three checks pass
    1 - one or more checks found drift
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from little_loops import host_runner as _host_runner_module
from little_loops.adapters.capabilities import HOST_CAPABILITIES
from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    RUNTIME_HOST_CAPABILITIES,
    HostCapabilities,
)
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

_HOST_COMPAT_MD = "docs/reference/HOST_COMPATIBILITY.md"
_ADAPTER_SECTION_HEADING = "## Adapter Host Capabilities"


def _host_compat_md_path() -> Path:
    """Return the path to ``docs/reference/HOST_COMPATIBILITY.md``.

    Resolved via the shared plugin-root helper so this works whether running
    from a source checkout or an installed package where the doc file is not
    adjacent to this module.
    """
    from little_loops.skill_expander import _find_plugin_root

    return _find_plugin_root() / _HOST_COMPAT_MD


def _adapter_section_hosts(doc_path: Path) -> set[str]:
    """Return the adapter-host names documented under `_ADAPTER_SECTION_HEADING`.

    Reads the section's markdown table, taking the first column of each data
    row (skipping the header and separator rows) as a host name.
    """
    text = doc_path.read_text(encoding="utf-8")
    idx = text.find(_ADAPTER_SECTION_HEADING)
    if idx == -1:
        return set()
    rest = text[idx + len(_ADAPTER_SECTION_HEADING) :]
    next_heading = rest.find("\n## ")
    section = rest if next_heading == -1 else rest[:next_heading]

    hosts: set[str] = set()
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        first = cells[0]
        if first.lower() == "host" or set(first) <= {"-", ":"}:
            continue
        hosts.add(first.strip("`"))
    return hosts


def _check_doc_parity(doc_path: Path) -> list[str]:
    """Return error strings for map/doc key-set mismatches."""
    map_hosts = set(HOST_CAPABILITIES)
    doc_hosts = _adapter_section_hosts(doc_path)

    errors = []
    for host in sorted(map_hosts - doc_hosts):
        errors.append(f"map entry '{host}' has no HOST_COMPATIBILITY.md adapter-host row")
    for host in sorted(doc_hosts - map_hosts):
        errors.append(f"HOST_COMPATIBILITY.md documents '{host}' with no map entry")
    return errors


def _check_runtime_contradiction() -> list[str]:
    """Return error strings where the runtime capability map drifts (ENH-3453).

    Three rules against ``host_runner.RUNTIME_HOST_CAPABILITIES`` and
    ``host_runner._HOST_RUNNER_REGISTRY``:

    (a) key parity — every built-in registry host has exactly one runtime
        entry, excluding any host named in ``host_runner.TEST_ONLY_HOSTS``
        (test-only hosts register in the registry but are exempt from the
        runtime map). Extension-registered runners (none exist today; the
        registry is structural, not closed) are also exempt — an extension
        runner keeps its own ``describe_capabilities()``/``capabilities``
        literal and is not held to key parity.
    (b) identity — each entry's ``host`` matches its registry key, and its
        ``flags`` is *identically* (``is``) the runner class's
        ``capabilities`` attribute — not merely equal, since the whole point
        of the collapse is that both read from the same object.
    (c) flag/row consistency, both directions — no report row named after one
        of the six ``HostCapabilities`` flags is ``"full"`` while that flag is
        ``False``, nor ``"unsupported"`` while that flag is ``True``.
        ``"partial"`` is legal in either direction.
    """
    test_only_hosts: frozenset[str] = getattr(_host_runner_module, "TEST_ONLY_HOSTS", frozenset())

    errors: list[str] = []

    registry_hosts = set(_HOST_RUNNER_REGISTRY) - test_only_hosts
    runtime_hosts = set(RUNTIME_HOST_CAPABILITIES)

    for host in sorted(registry_hosts - runtime_hosts):
        errors.append(f"missing runtime entry for '{host}'")
    for host in sorted(runtime_hosts - registry_hosts):
        errors.append(f"runtime entry '{host}' has no registered runner")

    flag_names = {f.name for f in dataclasses.fields(HostCapabilities)}

    for host in sorted(registry_hosts & runtime_hosts):
        entry = RUNTIME_HOST_CAPABILITIES[host]
        runner_cls = _HOST_RUNNER_REGISTRY[host]

        if entry.host != host:
            errors.append(f"runtime entry keyed '{host}' declares host={entry.host!r}")

        runner_flags = getattr(runner_cls, "capabilities", HostCapabilities())
        if entry.flags is not runner_flags:
            errors.append(
                f"host '{host}' runtime entry's flags is not the same object as "
                f"{runner_cls.__name__}.capabilities"
            )

        for row in entry.report_rows:
            if row.name not in flag_names:
                continue
            flag_value = getattr(entry.flags, row.name)
            if row.status == "full" and not flag_value:
                errors.append(
                    f"host '{host}' report row '{row.name}' is 'full' but the flag is False"
                )
            elif row.status == "unsupported" and flag_value:
                errors.append(
                    f"host '{host}' report row '{row.name}' is 'unsupported' but the flag is True"
                )

    return errors


def _check_emitter_agreement() -> list[str]:
    """Return error strings for internal contradictions within a map entry.

    Reframed by ENH-2883: since ``core.py``'s traversal functions
    (``process_skills``/``process_commands``/``process_agents``) now
    dispatch from ``HOST_CAPABILITIES`` themselves (the same
    capability-flag-driven pattern ``process_agents`` pioneered for
    ENH-2874), there is no longer any *independent* emitter behavior left
    for the map to drift against — an emitter's dispatch-relevant behavior
    (agent support, degraded routing) *is* the map now. This check is a
    same-dataclass self-consistency assertion: it flags a
    ``HostCapabilityEntry`` whose own fields contradict each other, not a
    map-vs-emitter comparison. Concretely: declaring ``agents=True`` under
    ``subagents == "none"`` with no ``agent_output_format`` for the
    degraded path to target, and declaring ``subagents == "native"`` while
    ``agents=False`` (a host that can spawn natively but is marked as
    emitting nothing). The function name and the ``ll-verify-host-map``
    check list above are kept for compatibility; read "emitter" here as
    "this entry's own declared behavior."
    """
    errors = []

    gemini_entry = HOST_CAPABILITIES.get("gemini")
    if gemini_entry is not None:
        if (
            gemini_entry.agents
            and gemini_entry.subagents == "none"
            and gemini_entry.agent_output_format is None
        ):
            errors.append(
                "map entry 'gemini' declares agents=True with subagents='none' but no "
                "agent_output_format is set — degraded emission has nowhere to write"
            )
        if gemini_entry.subagents == "native" and not gemini_entry.agents:
            errors.append("map entry 'gemini' declares subagents='native' but agents=False")

    omp_entry = HOST_CAPABILITIES.get("omp")
    if omp_entry is not None:
        if (
            omp_entry.agents
            and omp_entry.subagents == "none"
            and omp_entry.agent_output_format is None
        ):
            errors.append(
                "map entry 'omp' declares agents=True with subagents='none' but no "
                "agent_output_format is set — degraded emission has nowhere to write"
            )
        if omp_entry.subagents == "native" and not omp_entry.agents:
            errors.append("map entry 'omp' declares subagents='native' but agents=False")

    # FEAT-3105: the `commands` half of the same self-consistency shape —
    # declaring commands=True with no command_output_format leaves nothing
    # for a "this host emits commands" claim to point at. Checked across
    # every host entry (not name-hardcoded like the agents checks above),
    # since this is a two-field consistency rule with no per-host nuance.
    for host, entry in sorted(HOST_CAPABILITIES.items()):
        if entry.commands and entry.command_output_format is None:
            errors.append(
                f"map entry '{host}' declares commands=True but command_output_format "
                "is None — nothing for the commands claim to point at"
            )

    return errors


def _run() -> tuple[int, list[str]]:
    """Return ``(exit_code, error_messages)`` across all three checks."""
    errors: list[str] = []

    doc_path = _host_compat_md_path()
    if doc_path.is_file():
        errors.extend(_check_doc_parity(doc_path))
    else:
        print(
            f"SKIP: {doc_path} not found (plugin repo not available); "
            "checking runtime/emitter agreement only.",
            file=sys.stderr,
        )

    errors.extend(_check_runtime_contradiction())
    errors.extend(_check_emitter_agreement())

    exit_code = 1 if errors else 0
    return exit_code, errors


def main_verify_host_map() -> int:
    """Entry point for ``ll-verify-host-map``."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-host-map", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-host-map",
            description=(
                "Assert the adapter host-capability map agrees with "
                "HOST_COMPATIBILITY.md, host_runner.RUNTIME_HOST_CAPABILITIES "
                "(the runtime capability map, ENH-3453), and the emitters' "
                "actual behavior — including that a host declaring "
                "subagents='none' with agents=True has a working degraded-mode "
                "agent_output_format (ENH-2874). Exits 1 on drift (ENH-2873)."
            ),
        )
        parser.parse_args()

        exit_code, errors = _run()
        if exit_code == 0:
            print("OK: adapter host-capability map agrees with all cross-checks.")
            return 0

        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main_verify_host_map())
