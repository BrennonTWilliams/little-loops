"""ll-verify-host-map: assert the adapter host-capability map agrees with its cross-checks (ENH-2873).

Three checks, all against ``little_loops.adapters.capabilities.HOST_CAPABILITIES``:

1. Every map key has a row in ``docs/reference/HOST_COMPATIBILITY.md``'s
   adapter-host section, and vice versa (a documented adapter host with no
   map entry).
2. Hosts present in both the adapter map and `host_runner`'s
   ``HostCapabilities`` do not contradict each other on any field name the
   two dataclasses share.
3. The map's ``agents``/``commands`` flags agree with what the emitters
   actually do (``gemini.agents`` must be ``False`` to match the
   unconditional ``AdapterError`` in ``GeminiEmitter.emit_agent``; ``omp``
   must be ``False``/``False`` to match its all-stub emitter).

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
    """Return error strings where a map entry misdescribes its emitter's actual behavior."""
    errors = []

    gemini_entry = HOST_CAPABILITIES.get("gemini")
    if gemini_entry is not None and gemini_entry.agents:
        errors.append(
            "map entry 'gemini' declares agents=True but GeminiEmitter.emit_agent "
            "unconditionally raises AdapterError (preview-feature stub)"
        )

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
                "emitters' actual behavior. Exits 1 on drift (ENH-2873)."
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
