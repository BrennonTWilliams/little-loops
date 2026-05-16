"""ll-action: Thin CLI wrapper for invoking ll skills as one-shot commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from little_loops.host_runner import resolve_host

__all__ = ["main_action"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _find_plugin_root() -> Path:
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


def _read_skill_description(skill_md: Path) -> str:
    """Extract description from SKILL.md YAML frontmatter."""
    try:
        content = skill_md.read_text()
    except OSError:
        return ""
    if not content.startswith("---"):
        return ""
    end = content.find("---", 3)
    if end == -1:
        return ""
    frontmatter = content[3:end]
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            return line[len("description:") :].strip().strip('"').strip("'")
    return ""


def _load_skills() -> list[dict[str, str]]:
    """Return skill list with name and description from skills/*/SKILL.md files."""
    plugin_root = _find_plugin_root()
    skills_dir = plugin_root / "skills"
    skills = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        description = _read_skill_description(skill_md)
        skills.append({"name": name, "description": description})
    return skills


def cmd_invoke(args: argparse.Namespace) -> int:
    from little_loops.subprocess_utils import run_claude_command

    skill = args.skill
    skill_args: list[str] = args.args or []
    timeout: int = args.timeout
    output_mode: str = args.output

    command = f"/ll:{skill}"
    if skill_args:
        command += " " + " ".join(skill_args)

    start_ms = int(time.time() * 1000)

    if output_mode == "stream-json":
        _emit({"event": "action_start", "ts": _now_iso(), "skill": skill, "args": skill_args})

        exit_code = 0

        def _stream_cb(line: str, is_stderr: bool) -> None:
            if not is_stderr:
                _emit({"event": "action_output", "ts": _now_iso(), "line": line})

        try:
            result = run_claude_command(
                command=command,
                timeout=timeout,
                stream_callback=_stream_cb,
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124

        duration_ms = int(time.time() * 1000) - start_ms
        _emit(
            {
                "event": "action_complete",
                "ts": _now_iso(),
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            }
        )
        return exit_code

    else:  # --output json
        from little_loops.cli.output import print_json

        output_lines: list[str] = []
        stderr_lines: list[str] = []

        def _stream_cb_json(line: str, is_stderr: bool) -> None:
            if is_stderr:
                stderr_lines.append(line)
            else:
                output_lines.append(line)

        exit_code = 0
        try:
            result = run_claude_command(
                command=command,
                timeout=timeout,
                stream_callback=_stream_cb_json,
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124

        duration_ms = int(time.time() * 1000) - start_ms
        print_json(
            {
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "output": "\n".join(output_lines),
                "error": "\n".join(stderr_lines) if stderr_lines else None,
            }
        )
        return exit_code


def cmd_capabilities(args: argparse.Namespace) -> int:
    from little_loops.cli.output import print_json

    runner = resolve_host()
    report = runner.describe_capabilities()

    available = runner.detect()
    version = ""
    if available:
        try:
            invocation = runner.build_version_check()
            version_result = subprocess.run(
                [invocation.binary, *invocation.args],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = version_result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            available = False

    print_json(
        {
            "host": report.host,
            "binary": report.binary,
            "version": version,
            "capabilities": [
                {"name": c.name, "status": c.status, "note": c.note}
                for c in report.capabilities
            ],
            "hooks": [
                {"name": h.name, "status": h.status, "note": h.note}
                for h in report.hooks
            ],
        }
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from little_loops.cli.output import print_json

    skills = _load_skills()
    print_json(skills)
    return 0


def main_action() -> int:
    """Entry point for ll-action CLI."""
    parser = argparse.ArgumentParser(
        prog="ll-action",
        description="Invoke ll skills as one-shot commands with JSON-structured output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ll-action invoke refine-issue --args P2-ENH-1229
  ll-action invoke confidence-check --args FEAT-042 --timeout 120
  ll-action invoke refine-issue --args P2-ENH-1229 --output json
  ll-action capabilities
  ll-action list
""",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # invoke subcommand
    invoke_parser = subparsers.add_parser(
        "invoke",
        help="Invoke a skill and stream output as NDJSON events",
        description="Invoke a skill and stream output as NDJSON events (default) or collect and print as JSON",
    )
    invoke_parser.add_argument("skill", help="Skill name (e.g. refine-issue, confidence-check)")
    invoke_parser.add_argument(
        "--args",
        nargs="+",
        metavar="ARG",
        help="Arguments to pass to the skill",
    )
    invoke_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Timeout in seconds (default: 300)",
    )
    invoke_parser.add_argument(
        "--output",
        choices=["stream-json", "json"],
        default="stream-json",
        dest="output",
        help="Output format: stream-json (default, streaming NDJSON) or json (collect then print)",
    )

    # capabilities subcommand
    cap_parser = subparsers.add_parser(
        "capabilities",
        help="Emit full CapabilityReport as JSON (host, binary, version, capabilities, hooks)",
        description="Call describe_capabilities() and serialize the full CapabilityReport to JSON",
    )
    cap_parser.add_argument(
        "--output",
        choices=["json"],
        default="json",
        dest="output",
        help="Output format (json only)",
    )

    # list subcommand
    list_parser = subparsers.add_parser(
        "list",
        help="List all available skills with descriptions",
        description="List all available skills with names and descriptions from plugin manifest",
    )
    list_parser.add_argument(
        "--output",
        choices=["json"],
        default="json",
        dest="output",
        help="Output format (json only)",
    )

    parsed = parser.parse_args()

    if parsed.command == "invoke":
        return cmd_invoke(parsed)
    elif parsed.command == "capabilities":
        return cmd_capabilities(parsed)
    elif parsed.command == "list":
        return cmd_list(parsed)
    else:
        parser.print_help()
        return 1
