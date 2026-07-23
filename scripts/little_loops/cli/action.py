"""ll-action: Thin CLI wrapper for invoking ll skills as one-shot commands."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from little_loops.host_runner import resolve_host
from little_loops.output_parsing import extract_tagged_json
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    cli_event_context,
    record_verdict_event,
    skill_event_context,
)

__all__ = ["main_action"]

# Nine skill-bridged verifiers whose exit-code/output cmd_invoke() persists as
# a verdict_events row (ENH-2504). Others (e.g. capture-issue) are not
# verifiers and are intentionally excluded.
_VERIFIER_SKILLS = frozenset(
    {
        "ready-issue",
        "confidence-check",
        "go-no-go",
        "tradeoff-review-issues",
        "refine-issue",
        "format-issue",
        "verify-issues",
        "prioritize-issues",
        "align-issues",
    }
)

_TARGET_ID_RE = re.compile(r"\b(BUG|FEAT|ENH|EPIC)-\d+\b")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _record_verdict(
    *, skill: str, skill_args: list[str], exit_code: int, output_text: str, session_id: str | None
) -> None:
    """Best-effort verdict persistence for the 9 skill-bridged verifiers (ENH-2504).

    No skill currently emits a structured verdict dict at this call site, so
    the verdict defaults to a coarse exit-code read (0 -> "pass", else
    "fail"). A ``VERDICT_JSON: {...}`` tagged line (the existing
    :func:`extract_tagged_json` convention) overrides the coarse fields when
    present, letting precision improve as skills adopt the tag without a
    further schema change. Never raises — the caller wraps this best-effort.
    """
    if skill not in _VERIFIER_SKILLS:
        return

    verdict = "pass" if exit_code == 0 else "fail"
    target_kind: str | None = None
    target_id: str | None = None
    severity_counts: dict | None = None
    findings_count: int | None = None
    confidence: int | None = None

    match = _TARGET_ID_RE.search(" ".join(skill_args))
    if match:
        target_kind = "issue"
        target_id = match.group(0)

    tagged, _warning = extract_tagged_json(output_text, "VERDICT_JSON")
    if isinstance(tagged, dict):
        verdict = str(tagged.get("verdict", verdict))
        severity_counts = tagged.get("severity_counts")
        findings_count = tagged.get("findings_count")
        confidence = tagged.get("confidence")
        target_id = tagged.get("target_id", target_id)
        target_kind = tagged.get("target_kind", target_kind)

    record_verdict_event(
        DEFAULT_DB_PATH,
        ts=_now_iso(),
        session_id=session_id,
        verdict_kind=skill,
        target_kind=target_kind,
        target_id=target_id,
        verdict=verdict,
        severity_counts=severity_counts,
        findings_count=findings_count,
        confidence=confidence,
    )


def _emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def _find_plugin_root() -> Path:
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


def _read_skill_description(skill_md: Path) -> str:
    """Extract description from SKILL.md YAML frontmatter."""
    from little_loops.frontmatter import parse_skill_frontmatter

    try:
        content = skill_md.read_text()
    except OSError:
        return ""
    fm = parse_skill_frontmatter(content)
    return fm.get("description", "").strip().strip('"').strip("'")


def _load_skills() -> list[dict[str, str | None]]:
    """Return skill list with name, description, and args from skills/*/SKILL.md files."""
    from little_loops.frontmatter import parse_skill_frontmatter

    plugin_root = _find_plugin_root()
    skills_dir = plugin_root / "skills"
    skills = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        try:
            content = skill_md.read_text()
        except OSError:
            content = ""
        fm = parse_skill_frontmatter(content) if content else {}
        description = str(fm.get("description", "") or "").strip().strip('"').strip("'")
        # args: takes precedence over argument-hint: (aliasing for 19 existing skills)
        raw_args = fm.get("args") or fm.get("argument-hint")
        args: str | None = str(raw_args).strip().strip('"').strip("'") if raw_args else None
        skills.append({"name": name, "description": description, "args": args})
    return skills


def cmd_invoke(args: argparse.Namespace) -> int:
    from little_loops.runner_spec import ActionSpec, RunnerType, run_action

    skill = args.skill
    skill_args: list[str] = args.args or []
    timeout: int = args.timeout
    output_mode: str = args.output

    start_ms = int(time.time() * 1000)

    # Record the invocation as a skill_events row with completion metadata
    # (ENH-2460). skill_event_context is best-effort: a missing/locked
    # history.db never blocks the skill run.
    with skill_event_context(DEFAULT_DB_PATH, None, skill, " ".join(skill_args)) as completion:
        if output_mode == "stream-json":
            _emit({"event": "action_start", "ts": _now_iso(), "skill": skill, "args": skill_args})

            exit_code = 0
            stream_output_lines: list[str] = []

            def _stream_cb(line: str, is_stderr: bool) -> None:
                if not is_stderr:
                    stream_output_lines.append(line)
                    _emit({"event": "action_output", "ts": _now_iso(), "line": line})

            spec = ActionSpec(
                name=skill,
                runner=RunnerType.SKILL,
                target=skill,
                args={"runner_args": skill_args, "stream_callback": _stream_cb},
                timeout=timeout,
            )
            try:
                result = run_action(spec)
                exit_code = result.exit_code
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
            completion.exit_code = exit_code
            with suppress(Exception):
                _record_verdict(
                    skill=skill,
                    skill_args=skill_args,
                    exit_code=exit_code,
                    output_text="\n".join(stream_output_lines),
                    session_id=None,
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

            spec = ActionSpec(
                name=skill,
                runner=RunnerType.SKILL,
                target=skill,
                args={"runner_args": skill_args, "stream_callback": _stream_cb_json},
                timeout=timeout,
            )
            exit_code = 0
            try:
                result = run_action(spec)
                exit_code = result.exit_code
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
            completion.exit_code = exit_code
            with suppress(Exception):
                _record_verdict(
                    skill=skill,
                    skill_args=skill_args,
                    exit_code=exit_code,
                    output_text="\n".join(output_lines),
                    session_id=None,
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
                {"name": c.name, "status": c.status, "note": c.note} for c in report.capabilities
            ],
            "hooks": [{"name": h.name, "status": h.status, "note": h.note} for h in report.hooks],
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
    with cli_event_context(DEFAULT_DB_PATH, "ll-action", sys.argv[1:]):
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
