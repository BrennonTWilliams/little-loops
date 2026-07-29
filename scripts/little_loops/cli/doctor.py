"""ll-doctor: Host capability preflight check."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as importlib_metadata
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

if TYPE_CHECKING:
    from little_loops.host_runner import CapabilityReport, HostRunner

_STATUS_SYMBOLS: dict[str, str] = {
    "full": "✓",
    "partial": "○",
    "unsupported": "✗",
}


@dataclass(frozen=True)
class FindingDetail:
    """One per-finding action-severity breakdown within a `CheckResult`.

    Carries the `action_severity`/`route_owner` axis from `doc_counts.CountResult`
    and `link_checker.LinkResult` (ENH-2886) down into `--full` output, distinct
    from `CheckResult.severity`'s error/informational exit-code axis. `label`
    identifies the finding (a doc category name or a link URL).
    """

    label: str
    action_severity: Literal["auto", "mention", "route"]
    route_owner: str | None = None


@dataclass(frozen=True)
class CheckResult:
    """One registered doctor check's outcome.

    Mirrors `host_runner.CapabilityEntry`'s frozen-dataclass + closed-status
    shape. `severity` decides exit-code impact independently of `status`:
    an "error"-severity result with status "unsupported" fails the default
    exit code (the pre-registry host-capability behavior); "informational"
    results never do, regardless of status (for checks like an absent-but-
    optional subsystem). `findings` is an additive optional breakdown of
    per-finding action-severity (ENH-2887); it defaults to empty for every
    check that doesn't populate it, so only `_full_docs_check()`/
    `_full_check_links_check()` set it today.
    """

    name: str
    status: Literal["full", "partial", "unsupported"]
    note: str = ""
    severity: Literal["error", "informational"] = "error"
    findings: tuple[FindingDetail, ...] = ()


# Registered no-arg checks run unconditionally by main_doctor(). The host-
# capability report is not registered here because it needs the resolved
# HostRunner at call time; it is folded into the same CheckResult vocabulary
# via _capability_check_results() instead. New install-surface checks
# (FEAT-2794, FEAT-2795) register against this list.
_CHECKS: list[Callable[[], list[CheckResult]]] = []


def register_check(fn: Callable[[], list[CheckResult]]) -> Callable[[], list[CheckResult]]:
    """Register a no-arg check function returning a list of CheckResult."""
    _CHECKS.append(fn)
    return fn


# Capabilities that are optimizations rather than correctness requirements.
# An `unsupported` here is reported but must NOT fail the run: automation is
# fully functional without them, just more token-expensive. Folding these at
# "error" severity would make an honest `unsupported` (e.g. claude-code has no
# flag to skip CLAUDE.md) fail the primary host's own health check.
_ADVISORY_CAPABILITIES = frozenset({"claude_md_suppression"})


def _capability_check_results(report: CapabilityReport) -> list[CheckResult]:
    """Fold a CapabilityReport's entries into CheckResult.

    Error severity by default; advisory capabilities (see
    ``_ADVISORY_CAPABILITIES``) are informational so an unsupported
    optimization does not fail the exit code.
    """
    return [
        CheckResult(
            name=c.name,
            status=c.status,
            note=c.note,
            severity="informational" if c.name in _ADVISORY_CAPABILITIES else "error",
        )
        for c in report.capabilities
    ]


def _run_registered_checks() -> list[CheckResult]:
    """Run every check in `_CHECKS`, flattening their results."""
    results: list[CheckResult] = []
    for check in _CHECKS:
        results.extend(check())
    return results


def _exit_code_for(results: list[CheckResult]) -> int:
    """0 unless an error-severity result is 'unsupported'."""
    has_error = any(r.severity == "error" and r.status == "unsupported" for r in results)
    return 1 if has_error else 0


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


def _entry_points_data() -> list[dict[str, str]]:
    """One row per ``[project.scripts]`` entry point: name, status, note.

    Distinguishes "module not found" from "function renamed/removed" so a
    stale entry point produces an actionable note.

    Reads the *installed* distribution metadata rather than ``pyproject.toml``:
    the source file is absent from a wheel, so a ``__file__``-relative lookup
    would silently yield no rows for every non-editable install.
    """
    try:
        dist = importlib_metadata.distribution("little-loops")
    except importlib_metadata.PackageNotFoundError:
        return []
    scripts: dict[str, str] = {
        ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"
    }

    rows: list[dict[str, str]] = []
    for name, target in sorted(scripts.items()):
        module_path, _, func_name = target.partition(":")
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            rows.append({"name": name, "status": "unsupported", "note": f"module not found: {exc}"})
            continue
        if not hasattr(module, func_name):
            rows.append(
                {
                    "name": name,
                    "status": "unsupported",
                    "note": f"{module_path}.{func_name} not found (function renamed/removed)",
                }
            )
            continue
        rows.append({"name": name, "status": "full", "note": ""})
    return rows


def _print_entry_points_section() -> None:
    """Print the Entry Points section."""
    rows = _entry_points_data()
    print()
    print("Entry Points")
    print("─" * 40)
    if not rows:
        print("  (none found)")
        return
    for row in rows:
        symbol = _STATUS_SYMBOLS.get(row["status"], "?")
        note = f"  {row['note']}" if row["note"] else ""
        print(f"  {symbol}  {row['name']}{note}")


@register_check
def _entry_points_check() -> list[CheckResult]:
    """Registered check: each broken entry point is an error-severity result."""
    return [
        CheckResult(
            name=f"entry_point:{row['name']}",
            status="full" if row["status"] == "full" else "unsupported",
            note=row["note"],
        )
        for row in _entry_points_data()
    ]


def _skills_commands_data() -> dict:
    """Discoverability count via `assemble_tool_catalog()` (skills/commands/agents)."""
    from little_loops.tool_catalog import assemble_tool_catalog

    try:
        entries = assemble_tool_catalog(Path.cwd())
    except OSError as exc:
        return {"status": "unsupported", "note": f"catalog load failed: {exc}", "total": 0}
    return {"status": "full", "note": f"{len(entries)} tool(s) discovered", "total": len(entries)}


def _print_skills_commands_section() -> None:
    """Print the Skills & Commands section."""
    data = _skills_commands_data()
    print()
    print("Skills & Commands")
    print("─" * 40)
    symbol = _STATUS_SYMBOLS.get(data["status"], "?")
    print(f"  {symbol}  {data['note']}")


@register_check
def _skills_commands_check() -> list[CheckResult]:
    """Registered check for the skills/commands catalog."""
    data = _skills_commands_data()
    return [CheckResult(name="skills_commands", status=data["status"], note=data["note"])]


def _decisions_store_data() -> dict:
    """Two-pass health probe mirroring ``verify_decisions.py:_run()``.

    Absent (fresh install, no `.ll/decisions.yaml` or `.ll/decisions.d/`) is
    informational, not a failure — the decisions store is opt-in.
    """
    from little_loops.decisions import _entry_from_dict, _fragments_dir, load_decisions

    log_path = Path.cwd() / ".ll" / "decisions.yaml"
    frag_dir = _fragments_dir(log_path)

    if not log_path.exists() and not frag_dir.exists():
        return {
            "status": "unsupported",
            "severity": "informational",
            "note": "not configured (optional)",
        }

    if log_path.exists():
        try:
            load_decisions(log_path)
        except (yaml.YAMLError, KeyError, ValueError) as exc:
            return {
                "status": "unsupported",
                "severity": "error",
                "note": f"{log_path.name}: {type(exc).__name__}: {exc}",
            }

    if frag_dir.exists():
        for frag in sorted(frag_dir.glob("*.json")):
            try:
                frag_data = json.loads(frag.read_text(encoding="utf-8"))
                _entry_from_dict(frag_data)
            except (
                json.JSONDecodeError,
                KeyError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:
                return {
                    "status": "unsupported",
                    "severity": "error",
                    "note": f"{frag.name}: {type(exc).__name__}: {exc}",
                }

    return {"status": "full", "severity": "error", "note": "healthy"}


def _print_decisions_store_section() -> None:
    """Print the Decisions Store section."""
    data = _decisions_store_data()
    print()
    print("Decisions Store")
    print("─" * 40)
    symbol = _STATUS_SYMBOLS.get(data["status"], "?")
    print(f"  {symbol}  {data['note']}")


@register_check
def _decisions_store_check() -> list[CheckResult]:
    """Registered check for the decisions store."""
    data = _decisions_store_data()
    return [
        CheckResult(
            name="decisions_store",
            status=data["status"],
            note=data["note"],
            severity=data["severity"],
        )
    ]


def _history_db_data() -> dict:
    """Presence/readability probe for `.ll/history.db`.

    Must not create the DB: `session_store.connect()`/`ensure_db()` both
    create-on-demand, so a genuinely absent DB is probed via `Path.exists()`
    first and never passed through either function.
    """
    db_path = Path.cwd() / DEFAULT_DB_PATH
    if not db_path.exists():
        return {"status": "unsupported", "severity": "informational", "note": "not yet created"}

    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"status": "unsupported", "severity": "error", "note": f"unreadable: {exc}"}
    return {"status": "full", "severity": "error", "note": str(db_path)}


def _print_history_db_section() -> None:
    """Print the History DB section."""
    data = _history_db_data()
    print()
    print("History DB")
    print("─" * 40)
    symbol = _STATUS_SYMBOLS.get(data["status"], "?")
    print(f"  {symbol}  {data['note']}")


@register_check
def _history_db_check() -> list[CheckResult]:
    """Registered check for `.ll/history.db` presence/readability."""
    data = _history_db_data()
    return [
        CheckResult(
            name="history_db", status=data["status"], note=data["note"], severity=data["severity"]
        )
    ]


def _loop_validity_data() -> dict:
    """Aggregate `load_and_validate()` across every runnable loop YAML.

    Never executes a loop — purely a static-validation aggregation over the
    built-in loops directory plus a project-local `loops/` dir if present.
    """
    from little_loops.cli.loop._helpers import get_builtin_loops_dir
    from little_loops.fsm.validation import (
        ValidationSeverity,
        is_runnable_loop,
        load_and_validate,
    )

    loop_dirs = {get_builtin_loops_dir()}
    cwd_loops = Path.cwd() / "loops"
    if cwd_loops.exists():
        loop_dirs.add(cwd_loops)

    paths: list[Path] = []
    for loop_dir in loop_dirs:
        if loop_dir.exists():
            paths.extend(sorted(p for p in loop_dir.rglob("*.yaml") if is_runnable_loop(p)))

    if not paths:
        return {
            "status": "unsupported",
            "severity": "informational",
            "note": "no loops found",
            "total": 0,
            "invalid": [],
        }

    invalid: list[str] = []
    for path in paths:
        try:
            _, violations = load_and_validate(path, raise_on_error=False)
        except (FileNotFoundError, ValueError) as exc:
            invalid.append(f"{path.name}: {exc}")
            continue
        if any(v.severity == ValidationSeverity.ERROR for v in violations):
            invalid.append(path.name)

    if invalid:
        return {
            "status": "unsupported",
            "severity": "error",
            "note": f"{len(invalid)}/{len(paths)} invalid: {', '.join(invalid)}",
            "total": len(paths),
            "invalid": invalid,
        }
    return {
        "status": "full",
        "severity": "error",
        "note": f"{len(paths)} loop(s) valid",
        "total": len(paths),
        "invalid": [],
    }


def _print_loop_validity_section() -> None:
    """Print the FSM Loop Validity section."""
    data = _loop_validity_data()
    print()
    print("FSM Loop Validity")
    print("─" * 40)
    symbol = _STATUS_SYMBOLS.get(data["status"], "?")
    print(f"  {symbol}  {data['note']}")


@register_check
def _loop_validity_check() -> list[CheckResult]:
    """Registered check for FSM loop validity."""
    data = _loop_validity_data()
    return [
        CheckResult(
            name="loop_validity",
            status=data["status"],
            note=data["note"],
            severity=data["severity"],
        )
    ]


# --full-gated checks: one adapter per ll-verify-* / ll-check-links checker,
# aggregating the FEAT-2795 target family. Kept separate from `_CHECKS` so the
# default (non-`--full`) run never executes them.
_FULL_CHECKS: list[Callable[[], list[CheckResult]]] = []


def register_full_check(fn: Callable[[], list[CheckResult]]) -> Callable[[], list[CheckResult]]:
    """Register a no-arg check function that only runs under `--full`."""
    _FULL_CHECKS.append(fn)
    return fn


def _run_full_checks() -> list[CheckResult]:
    """Run every check in `_FULL_CHECKS`, flattening their results."""
    results: list[CheckResult] = []
    for check in _FULL_CHECKS:
        results.extend(check())
    return results


def _full_docs_data() -> dict:
    """Adapter over `verify_documentation()` (ll-verify-docs)."""
    from little_loops.doc_counts import verify_documentation

    result = verify_documentation(Path.cwd())
    if result.all_match:
        return {"status": "full", "note": f"{result.total_checked} categor(y/ies) match"}
    names = ", ".join(m.category for m in result.mismatches)
    return {
        "status": "unsupported",
        "note": f"mismatched: {names}",
        "findings": [
            FindingDetail(
                label=m.category,
                action_severity=m.action_severity,
                route_owner=m.route_owner,
            )
            for m in result.mismatches
        ],
    }


@register_full_check
def _full_docs_check() -> list[CheckResult]:
    data = _full_docs_data()
    return [
        CheckResult(
            name="full:docs",
            status=data["status"],
            note=data["note"],
            findings=tuple(data.get("findings", ())),
        )
    ]


def _full_skill_budget_data() -> dict:
    """Adapter over `check_skill_budget()` (ll-verify-skill-budget)."""
    from little_loops.doc_counts import check_skill_budget

    result = check_skill_budget(base_dir=Path.cwd())
    if result.under_budget:
        return {
            "status": "full",
            "note": f"{result.total_tokens}/{result.threshold_tokens} tokens",
        }
    return {
        "status": "unsupported",
        "note": f"over budget: {result.total_tokens}/{result.threshold_tokens} tokens",
    }


@register_full_check
def _full_skill_budget_check() -> list[CheckResult]:
    data = _full_skill_budget_data()
    return [CheckResult(name="full:skill_budget", status=data["status"], note=data["note"])]


def _full_skills_data() -> dict:
    """Adapter over `check_skill_sizes()` (ll-verify-skills)."""
    from little_loops.doc_counts import check_skill_sizes

    violations = check_skill_sizes(base_dir=Path.cwd())
    if not violations:
        return {"status": "full", "note": "all SKILL.md files within limit"}
    names = ", ".join(path.parent.name for path, _ in violations)
    return {"status": "unsupported", "note": f"over limit: {names}"}


@register_full_check
def _full_skills_check() -> list[CheckResult]:
    data = _full_skills_data()
    return [CheckResult(name="full:skills", status=data["status"], note=data["note"])]


def _full_triggers_data() -> dict:
    """Adapter over `_run_validation()`/`_any_failures()` (ll-verify-triggers)."""
    from little_loops.cli.verify_triggers import _any_failures, _run_validation

    skills_dir = Path.cwd() / "skills"
    if not skills_dir.is_dir():
        return {
            "status": "unsupported",
            "severity": "informational",
            "note": "skills directory not found",
        }
    results, collisions, thresholds = _run_validation(skills_dir)
    if _any_failures(
        results,
        collisions,
        thresholds["precision_threshold"],
        thresholds["recall_threshold"],
    ):
        return {
            "status": "unsupported",
            "severity": "error",
            "note": "one or more skills below threshold or collisions detected",
        }
    measured = sum(1 for r in results.values() if r.measured)
    return {
        "status": "full",
        "severity": "error",
        "note": f"{measured}/{len(results)} skill(s) measured",
    }


@register_full_check
def _full_triggers_check() -> list[CheckResult]:
    data = _full_triggers_data()
    return [
        CheckResult(
            name="full:triggers",
            status=data["status"],
            note=data["note"],
            severity=data.get("severity", "error"),
        )
    ]


def _full_decisions_data() -> dict:
    """Adapter over `verify_decisions._run()` (ll-verify-decisions)."""
    from little_loops.cli.verify_decisions import _resolve_log_path
    from little_loops.cli.verify_decisions import _run as _verify_decisions_run

    log_path = _resolve_log_path(None)
    exit_code, error_message = _verify_decisions_run(log_path)
    if exit_code == 0:
        return {"status": "full", "note": "clean"}
    return {"status": "unsupported", "note": error_message or "failed"}


@register_full_check
def _full_decisions_check() -> list[CheckResult]:
    data = _full_decisions_data()
    return [CheckResult(name="full:decisions", status=data["status"], note=data["note"])]


def _full_package_data_data() -> dict:
    """Adapter over `run_escape_lint()`/`run_manifest_check()` (ll-verify-package-data)."""
    from little_loops.cli.verify_package_data import (
        _find_pkg_root,
        run_escape_lint,
        run_manifest_check,
    )

    pkg_root = _find_pkg_root(Path.cwd())
    if pkg_root is None:
        return {"status": "unsupported", "note": "package root not found"}

    lint_results = run_escape_lint(pkg_root)
    missing_assets = run_manifest_check()
    if not lint_results and not missing_assets:
        return {"status": "full", "note": "no escapes, all assets accessible"}

    parts = []
    if lint_results:
        parts.append(f"{len(lint_results)} file(s) with escape violations")
    if missing_assets:
        parts.append(f"{len(missing_assets)} missing asset(s)")
    return {"status": "unsupported", "note": "; ".join(parts)}


@register_full_check
def _full_package_data_check() -> list[CheckResult]:
    data = _full_package_data_data()
    return [CheckResult(name="full:package_data", status=data["status"], note=data["note"])]


def _full_kinds_data() -> dict:
    """Adapter over `verify_kinds._run()` (ll-verify-kinds)."""
    from little_loops.cli.verify_kinds import _run as _verify_kinds_run

    exit_code, unregistered = _verify_kinds_run()
    if exit_code == 0:
        return {"status": "full", "note": "all tables registered"}
    return {"status": "unsupported", "note": f"unregistered: {', '.join(unregistered)}"}


@register_full_check
def _full_kinds_check() -> list[CheckResult]:
    data = _full_kinds_data()
    return [CheckResult(name="full:kinds", status=data["status"], note=data["note"])]


def _full_host_map_data() -> dict:
    """Adapter over `verify_host_map._run()` (ll-verify-host-map)."""
    from little_loops.cli.verify_host_map import _run as _verify_host_map_run

    exit_code, errors = _verify_host_map_run()
    if exit_code == 0:
        return {
            "status": "full",
            "note": "adapter host-capability map agrees with all cross-checks",
        }
    return {"status": "unsupported", "note": "; ".join(errors)}


@register_full_check
def _full_host_map_check() -> list[CheckResult]:
    data = _full_host_map_data()
    return [CheckResult(name="full:host_map", status=data["status"], note=data["note"])]


def _full_design_tokens_data() -> dict:
    """Adapter over `lint_profiles_dir()` (ll-verify-design-tokens)."""
    from little_loops.cli.verify_design_tokens import _find_profiles_dir, lint_profiles_dir

    profiles_dir = _find_profiles_dir(Path.cwd())
    if profiles_dir is None:
        return {
            "status": "unsupported",
            "severity": "informational",
            "note": "profiles directory not found",
        }
    results = lint_profiles_dir(profiles_dir)
    if not results:
        return {
            "status": "full",
            "severity": "error",
            "note": "all inverting themes complete",
        }
    themes = ", ".join(f"{r.profile}/{v.theme}" for r in results for v in r.violations)
    return {
        "status": "unsupported",
        "severity": "error",
        "note": f"half-flipped themes: {themes}",
    }


@register_full_check
def _full_design_tokens_check() -> list[CheckResult]:
    data = _full_design_tokens_data()
    return [
        CheckResult(
            name="full:design_tokens",
            status=data["status"],
            note=data["note"],
            severity=data.get("severity", "error"),
        )
    ]


def _full_des_audit_data() -> dict:
    """Adapter over `audit_tree()` (ll-verify-des-audit)."""
    from little_loops.cli.verify_des_audit import _find_source_dir
    from little_loops.observability.audit import audit_tree

    source_dir = _find_source_dir(Path.cwd())
    if source_dir is None:
        return {
            "status": "unsupported",
            "severity": "informational",
            "note": "source directory not found",
        }
    result = audit_tree(source_dir)
    if result.passed:
        return {
            "status": "full",
            "severity": "error",
            "note": f"{result.emit_sites_found} emit site(s) covered",
        }
    return {
        "status": "unsupported",
        "severity": "error",
        "note": f"uncovered event types: {', '.join(result.uncovered_event_types)}",
    }


@register_full_check
def _full_des_audit_check() -> list[CheckResult]:
    data = _full_des_audit_data()
    return [
        CheckResult(
            name="full:des_audit",
            status=data["status"],
            note=data["note"],
            severity=data.get("severity", "error"),
        )
    ]


def _full_check_links_data() -> dict:
    """Adapter over `check_markdown_links()` (ll-check-links)."""
    from little_loops.link_checker import check_markdown_links, load_ignore_patterns

    base_dir = Path.cwd()
    ignore_patterns = load_ignore_patterns(base_dir)
    result = check_markdown_links(base_dir, ignore_patterns)
    if result.broken_links > 0:
        return {
            "status": "unsupported",
            "severity": "error",
            "note": f"{result.broken_links} broken link(s)",
            "findings": [
                FindingDetail(
                    label=r.url,
                    action_severity=r.action_severity,
                    route_owner=r.route_owner,
                )
                for r in result.results
                if r.status == "broken"
            ],
        }
    if result.unreachable_links > 0:
        return {
            "status": "unsupported",
            "severity": "informational",
            "note": f"{result.unreachable_links} unreachable link(s) (network)",
            "findings": [
                FindingDetail(
                    label=r.url,
                    action_severity=r.action_severity,
                    route_owner=r.route_owner,
                )
                for r in result.results
                if r.status == "unreachable"
            ],
        }
    return {
        "status": "full",
        "severity": "error",
        "note": f"{result.valid_links} valid link(s)",
    }


@register_full_check
def _full_check_links_check() -> list[CheckResult]:
    data = _full_check_links_data()
    return [
        CheckResult(
            name="full:check_links",
            status=data["status"],
            note=data["note"],
            severity=data.get("severity", "error"),
            findings=tuple(data.get("findings", ())),
        )
    ]


def _print_full_section() -> None:
    """Print the `--full` aggregation section (one line per verifier).

    Verifiers that populate `CheckResult.findings` (ENH-2887) get an additional
    per-finding sub-line showing action-severity, without changing the existing
    one-line-per-verifier summary shape for every other check.
    """
    print()
    print("Full Verification (--full)")
    print("─" * 40)
    for result in _run_full_checks():
        symbol = _STATUS_SYMBOLS.get(result.status, "?")
        label = result.name.removeprefix("full:")
        note = f"  {result.note}" if result.note else ""
        print(f"  {symbol}  {label}{note}")
        for finding in result.findings:
            owner = f" -> {finding.route_owner}" if finding.route_owner else ""
            print(f"      - {finding.label}: {finding.action_severity}{owner}")


def _full_section_data() -> dict:
    """`--json --full`'s per-verifier section, keyed by verifier name."""
    return {
        result.name.removeprefix("full:"): {
            "status": result.status,
            "note": result.note,
            "findings": [
                {
                    "label": f.label,
                    "action_severity": f.action_severity,
                    "route_owner": f.route_owner,
                }
                for f in result.findings
            ],
        }
        for result in _run_full_checks()
    }


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
    full: bool = False,
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
            "entry_points": _entry_points_data(),
            "skills_commands": _skills_commands_data(),
            "decisions_store": _decisions_store_data(),
            "history_db": _history_db_data(),
            "loop_validity": _loop_validity_data(),
        }
        if full:
            data["full"] = _full_section_data()
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
        parser.add_argument(
            "--full",
            action="store_true",
            help="Also run the full ll-verify-* / ll-check-links checker family",
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
            full=args.full,
        )

        if not args.json:
            _print_capture_section(cfg.analytics_capture)
            _print_issues_section(cfg.issues)
            _print_entry_points_section()
            _print_skills_commands_section()
            _print_decisions_store_section()
            _print_history_db_section()
            _print_loop_validity_section()
            if args.full:
                _print_full_section()

        results = _capability_check_results(report) + _run_registered_checks()
        if args.full:
            results += _run_full_checks()
        return _exit_code_for(results)
