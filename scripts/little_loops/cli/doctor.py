"""ll-doctor: Host capability preflight check."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

if TYPE_CHECKING:
    from little_loops.host_runner import HostRunner

_STATUS_SYMBOLS: dict[str, str] = {
    "full": "✓",
    "partial": "○",
    "unsupported": "✗",
}


def _capture_section_data(capture: object) -> dict:
    """Gather the Analytics Capture config-state fields as a plain dict."""
    return {
        "skills": getattr(capture, "skills", ["*"]),
        "cli_commands": getattr(capture, "cli_commands", ["*"]),
        "corrections": getattr(capture, "corrections", True),
        "file_events": getattr(capture, "file_events", True),
        "correction_patterns": getattr(capture, "correction_patterns", []),
    }


def _issues_section_data(issues_cfg: object) -> dict:
    """Gather the Issues config-state fields as a plain dict."""
    return {
        "auto_commit": getattr(issues_cfg, "auto_commit", False),
        "auto_commit_prefix": getattr(issues_cfg, "auto_commit_prefix", "chore(issues)"),
    }


def _print_capture_section(capture: object) -> None:
    """Print the Analytics Capture config-state section."""
    data = _capture_section_data(capture)
    print()
    print("Analytics Capture")
    print("─" * 40)
    full = _STATUS_SYMBOLS["full"]
    skills = data["skills"]
    cli_commands = data["cli_commands"]
    corrections = data["corrections"]
    file_events = data["file_events"]
    correction_patterns = data["correction_patterns"]
    print(f"  {full}  skills:               {skills}")
    print(f"  {full}  cli_commands:         {cli_commands}")
    corr_sym = _STATUS_SYMBOLS["full" if corrections else "unsupported"]
    print(f"  {corr_sym}  corrections:          {'enabled' if corrections else 'disabled'}")
    fe_sym = _STATUS_SYMBOLS["full" if file_events else "unsupported"]
    print(f"  {fe_sym}  file_events:          {'enabled' if file_events else 'disabled'}")
    print(
        f"  {full}  correction_patterns:  {correction_patterns if correction_patterns else '(none)'}"
    )


def _print_issues_section(issues_cfg: object) -> None:
    """Print the Issues config-state section."""
    data = _issues_section_data(issues_cfg)
    print()
    print("Issues")
    print("─" * 40)
    auto_commit = data["auto_commit"]
    auto_commit_prefix = data["auto_commit_prefix"]
    ac_sym = _STATUS_SYMBOLS["full" if auto_commit else "unsupported"]
    print(f"  {ac_sym}  auto_commit:        {'enabled' if auto_commit else 'disabled'}")
    print(f"  {_STATUS_SYMBOLS['full']}  auto_commit_prefix: {auto_commit_prefix}")


def _probe_version(runner: HostRunner) -> str:
    """Probe the host binary's version, swallowing all failures to "".

    Mirrors cmd_capabilities()'s probe shape (cli/action.py) — probing here
    in the CLI layer keeps describe_capabilities() pure and I/O-free.
    """
    from little_loops.host_runner import HostNotConfigured

    try:
        if not runner.detect():
            return ""
        invocation = runner.build_version_check()
        result = subprocess.run(
            [invocation.binary, *invocation.args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, HostNotConfigured):
        return ""


def _print_report(
    report: object,
    *,
    version: str = "",
    json_mode: bool = False,
    capture: object = None,
    issues_cfg: object = None,
) -> None:
    """Print a CapabilityReport in text or JSON format."""
    from little_loops.host_runner import CapabilityReport

    assert isinstance(report, CapabilityReport)

    if json_mode:
        data = {
            "host": report.host,
            "binary": report.binary,
            "version": version or "(unknown)",
            "capabilities": [
                {"name": c.name, "status": c.status, "note": c.note} for c in report.capabilities
            ],
            "analytics_capture": _capture_section_data(capture),
            "issues": _issues_section_data(issues_cfg),
        }
        print_json(data)
        return

    version_display = version or "(unknown)"
    print(f"Host:    {report.host}")
    print(f"Binary:  {report.binary}  {version_display}")

    if report.capabilities:
        print()
        print("Capabilities")
        print("─" * 40)
        for cap in report.capabilities:
            symbol = _STATUS_SYMBOLS.get(cap.status, "?")
            note = f"  {cap.note}" if cap.note else ""
            print(f"  {symbol}  {cap.name}{note}")


def main_doctor(argv: list[str] | None = None) -> int:
    """Entry point for ll-doctor command.

    Resolve the active host and print a ✓/✗/○ capability table covering
    invocation modes.

    Returns:
        Exit code (0 = all capabilities present, 1 = critical capability missing)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-doctor", sys.argv[1:]):
        from little_loops.config import BRConfig
        from little_loops.host_runner import apply_host_cli_from_config, resolve_host

        parser = argparse.ArgumentParser(
            prog="ll-doctor",
            description="Check host CLI capability support for little-loops features",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s           # Print capability table
  %(prog)s --json    # Output as JSON

Exit codes:
  0 - All capabilities present
  1 - One or more capabilities unsupported
""",
        )
        parser.add_argument(
            "-j",
            "--json",
            action="store_true",
            help="Output as JSON",
        )

        args = parser.parse_args(argv)
        configure_output()
        Logger(use_color=use_color_enabled())

        cfg = BRConfig(Path.cwd())
        apply_host_cli_from_config(cfg)
        runner = resolve_host()
        report = runner.describe_capabilities()
        version = _probe_version(runner)

        _print_report(
            report,
            version=version,
            json_mode=args.json,
            capture=cfg.analytics_capture,
            issues_cfg=cfg.issues,
        )

        if not args.json:
            _print_capture_section(cfg.analytics_capture)
            _print_issues_section(cfg.issues)

        return 0 if not any(c.status == "unsupported" for c in report.capabilities) else 1
