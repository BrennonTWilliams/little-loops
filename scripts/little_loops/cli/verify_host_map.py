"""ll-verify-host-map: assert the adapter host-capability map agrees with its cross-checks (ENH-2873).

Three checks, all against ``little_loops.adapters.capabilities.HOST_CAPABILITIES``:

1. Every map key has a row in ``docs/reference/HOST_COMPATIBILITY.md``'s
   adapter-host section, and vice versa (a documented adapter host with no
   map entry).
2. Hosts present in both the adapter map and `host_runner`'s
   ``HostCapabilities`` do not contradict each other on any field name the
   two dataclasses share.
3. Each entry's own ``agents``/``subagents``/``agent_output_format`` fields
   are mutually consistent (ENH-2883: since ``core.py``'s traversal
   functions dispatch from the map itself, there is no independent emitter
   behavior left to compare against — this is a same-dataclass
   self-consistency check, not a map-vs-emitter one). It flags
   ``agents=True`` with ``subagents == "none"`` but no ``agent_output_format``
   set (nothing for the degraded path to point at), or
   ``subagents == "native"`` with ``agents=False`` (a host that can spawn
   but is declared not to emit). ``omp`` must stay ``False``/``False`` to
   match its all-stub emitter, which has no degraded path either
   (``agent_output_format`` is ``None``).

Exit codes:
    0 - all three checks pass
    1 - one or more checks found drift
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from little_loops.adapters.capabilities import HOST_CAPABILITIES, HostCapabilityEntry
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
    """Return error strings where a shared host's map/runtime fields disagree.

    Compares field names common to both `HostCapabilityEntry` and
    `host_runner.HostCapabilities` (deliberately none today — see the Option
    B docstring in `capabilities.py`) for hosts registered on both sides.
    A future field-name collision between the build-time and runtime
    surfaces is exactly the drift this check exists to catch.
    """
    from little_loops.host_runner import _HOST_RUNNER_REGISTRY, HostCapabilities

    entry_fields = {f.name for f in dataclasses.fields(HostCapabilityEntry)}
    runtime_fields = {f.name for f in dataclasses.fields(HostCapabilities)}
    shared_fields = entry_fields & runtime_fields

    errors = []
    shared_hosts = set(HOST_CAPABILITIES) & set(_HOST_RUNNER_REGISTRY)
    for host in sorted(shared_hosts):
        entry = HOST_CAPABILITIES[host]
        runtime_caps = getattr(_HOST_RUNNER_REGISTRY[host], "capabilities", HostCapabilities())
        for field_name in sorted(shared_fields):
            entry_val = getattr(entry, field_name)
            runtime_val = getattr(runtime_caps, field_name)
            if entry_val != runtime_val:
                errors.append(
                    f"host '{host}' field '{field_name}' disagrees: "
                    f"map={entry_val!r} runtime={runtime_val!r}"
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
    if omp_entry is not None and (omp_entry.agents or omp_entry.commands):
        errors.append(
            "map entry 'omp' declares working agents/commands support but OmpEmitter "
            "is an all-stub emitter (all emit_* raise AdapterError)"
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
                "HOST_COMPATIBILITY.md, host_runner.HostCapabilities, and the "
                "emitters' actual behavior — including that a host declaring "
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
