"""ll-doctor: Host capability preflight check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger

_STATUS_SYMBOLS: dict[str, str] = {
    "full": "✓",
    "partial": "○",
    "unsupported": "✗",
    "installed": "✓",
    "registered": "○",
    "deferred": "○",
    "absent": "✗",
}


def _print_capture_section(capture: object) -> None:
    """Print the Analytics Capture config-state section."""
    print()
    print("Analytics Capture")
    print("─" * 40)
    full = _STATUS_SYMBOLS["full"]
    skills = getattr(capture, "skills", ["*"])
    cli_commands = getattr(capture, "cli_commands", ["*"])
    corrections = getattr(capture, "corrections", True)
    file_events = getattr(capture, "file_events", True)
    print(f"  {full}  skills:        {skills}")
    print(f"  {full}  cli_commands:  {cli_commands}")
    corr_sym = _STATUS_SYMBOLS["full" if corrections else "unsupported"]
    print(f"  {corr_sym}  corrections:   {'enabled' if corrections else 'disabled'}")
    fe_sym = _STATUS_SYMBOLS["full" if file_events else "unsupported"]
    print(f"  {fe_sym}  file_events:   {'enabled' if file_events else 'disabled'}")


def _print_issues_section(issues_cfg: object) -> None:
    """Print the Issues config-state section."""
    print()
    print("Issues")
    print("─" * 40)
    auto_commit = getattr(issues_cfg, "auto_commit", False)
    auto_commit_prefix = getattr(issues_cfg, "auto_commit_prefix", "chore(issues)")
    ac_sym = _STATUS_SYMBOLS["full" if auto_commit else "unsupported"]
    print(f"  {ac_sym}  auto_commit:        {'enabled' if auto_commit else 'disabled'}")
    print(f"  {_STATUS_SYMBOLS['full']}  auto_commit_prefix: {auto_commit_prefix}")


def _print_report(report: object, *, json_mode: bool = False) -> None:
    """Print a CapabilityReport in text or JSON format."""
    from little_loops.host_runner import CapabilityReport

    assert isinstance(report, CapabilityReport)

    if json_mode:
        data = {
            "host": report.host,
            "binary": report.binary,
            "version": report.version or "(unknown)",
            "capabilities": [
                {"name": c.name, "status": c.status, "note": c.note} for c in report.capabilities
            ],
            "hooks": [{"name": h.name, "status": h.status, "note": h.note} for h in report.hooks],
        }
        print(json.dumps(data, indent=2))
        return

    version_display = report.version or "(unknown)"
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

    if report.hooks:
        print()
        print("Hooks")
        print("─" * 40)
        for hook in report.hooks:
            symbol = _STATUS_SYMBOLS.get(hook.status, "?")
            note = f"  {hook.note}" if hook.note else ""
            print(f"  {symbol}  {hook.name}{note}")


def main_doctor(argv: list[str] | None = None) -> int:
    """Entry point for ll-doctor command.

    Resolve the active host and print a ✓/✗/○ capability table covering
    invocation modes and per-hook installation status.

    Returns:
        Exit code (0 = all capabilities present, 1 = critical capability missing)
    """
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

    _print_report(report, json_mode=args.json)

    if not args.json:
        _print_capture_section(cfg.analytics_capture)
        _print_issues_section(cfg.issues)

    return 0 if not any(c.status == "unsupported" for c in report.capabilities) else 1
