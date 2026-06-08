"""ll-init: Headless project initialization CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context


def _plugin_version() -> str:
    from little_loops import __version__

    return __version__


def _plugin_root() -> Path:
    """Return the little-loops project root (four parents above this file)."""
    return Path(__file__).parent.parent.parent.parent


def _run_yes(
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    force: bool,
    dry_run: bool,
    codex: bool,
) -> int:
    """Execute the non-interactive --yes init flow."""
    from little_loops.init.core import build_config
    from little_loops.init.detect import detect_project_type
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        deploy_goals,
        install_codex_adapter,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_settings,
        update_gitignore,
        write_config,
    )

    ll_dir = project_root / ".ll"
    config_path = ll_dir / "ll-config.json"

    if config_path.exists() and not force:
        print(
            f"Configuration already exists at {config_path}\n"
            "Use --force to overwrite, or edit the existing file directly.",
            file=sys.stderr,
        )
        return 1

    if config_path.exists() and force and not dry_run:
        print("Overwriting existing configuration.")

    template = detect_project_type(project_root, templates_dir)
    print(f"Detected project type: {template.name}")

    config = build_config(template, {"project_name": project_root.name})

    if dry_run:
        _print_dry_run(config, project_root, ll_dir, codex=codex)
        return 0

    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    write_config(config, ll_dir)
    make_issue_dirs(issues_base)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir)

    update_gitignore(project_root)
    merge_settings(project_root)

    if codex:
        installed = install_codex_adapter(project_root, plugin_root, force=force)
        if installed:
            print("[Codex] Hook adapter installed to .codex/hooks.json")
            print(
                "[Codex] Note: Codex will show a hook-trust dialog on next session start. "
                "Hooks are silently skipped (HookRunStatus::Untrusted) until trusted."
            )

    print("\nValidating dependencies...")
    warnings = validate_deps(config, _plugin_version(), project_root)
    for w in warnings:
        msg = f"Warning: {w.message}"
        if w.install_hint:
            msg += f"\n  Install/fix: {w.install_hint}"
        print(msg, file=sys.stderr)

    print(f"\n✓ little-loops initialized in {project_root}")
    print(f"  Config: {config_path}")
    return 0


def _print_dry_run(
    config: dict[str, Any],
    project_root: Path,
    ll_dir: Path,
    codex: bool,
) -> None:
    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    print("\n=== DRY RUN: ll-init ===\n")
    print("--- Configuration Preview (.ll/ll-config.json) ---")
    print(json.dumps(config, indent=2))
    print("\n--- Actions that would be taken ---")
    print(f"  [write]  {ll_dir / 'll-config.json'}")
    if config.get("product", {}).get("enabled"):
        print(f"  [write]  {ll_dir / 'll-goals.md'} (from ll-goals-template.md)")
    for sd in ("bugs", "features", "enhancements", "completed", "deferred"):
        print(f"  [mkdir]  {issues_base / sd}")
    print("  [update] .gitignore (add state file exclusions)")
    print("  [update] .claude/settings.local.json (add ll- CLI tool permissions)")
    if codex:
        print("  [write]  .codex/hooks.json (Codex CLI hook adapter)")
    print("\n=== END DRY RUN (no changes made) ===")


def _run_plan(project_root: Path, templates_dir: Path) -> int:
    """Emit a machine-readable JSON plan without writing anything."""
    from little_loops.init.core import build_config
    from little_loops.init.detect import detect_project_type
    from little_loops.init.validate import validate_deps

    template = detect_project_type(project_root, templates_dir)
    config = build_config(template, {"project_name": project_root.name})
    warnings = validate_deps(config, _plugin_version(), project_root)

    plan: dict[str, Any] = {
        "detected": {
            "template_name": template.filename,
            "project_type": template.name,
            "project_name": project_root.name,
        },
        "proposed_config": config,
        "host_options": {
            "has_claude_code": bool(shutil.which("claude")),
            "has_codex": bool(shutil.which("codex")),
            "suggested_settings_file": ".claude/settings.local.json",
        },
        "warnings": [
            {"message": w.message, "install_hint": w.install_hint} for w in warnings
        ],
    }
    print(json.dumps(plan, indent=2))
    return 0


def _run_apply(
    plan_config: str,
    project_root: Path,
    templates_dir: Path,
    force: bool,
) -> int:
    """Apply writes from a --plan JSON (file path or raw JSON string)."""
    from little_loops.init.writers import (
        deploy_goals,
        make_issue_dirs,
        merge_settings,
        update_gitignore,
        write_config,
    )

    # Accept a file path or a raw JSON string
    plan_path = Path(plan_config)
    if plan_path.exists():
        raw = plan_path.read_text(encoding="utf-8")
    else:
        raw = plan_config

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON: {exc}", file=sys.stderr)
        return 2

    config: dict[str, Any] = plan.get("proposed_config") or plan
    ll_dir = project_root / ".ll"
    config_path = ll_dir / "ll-config.json"

    if config_path.exists() and not force:
        print(
            f"Configuration already exists at {config_path}\nUse --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    write_config(config, ll_dir)
    make_issue_dirs(issues_base)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir)

    update_gitignore(project_root)
    merge_settings(project_root)

    print(f"✓ Applied init plan to {project_root}")
    return 0


def main_init(argv: list[str] | None = None) -> int:
    """Entry point for ll-init command.

    Returns:
        Exit code: 0 success, 1 error, 2 usage error.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-init", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-init",
            description="Initialize little-loops for a project",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --yes                      # Non-interactive full init with defaults
  %(prog)s --yes --dry-run            # Preview without writing files
  %(prog)s --yes --force              # Overwrite existing configuration
  %(prog)s --plan                     # Emit JSON plan without writing
  %(prog)s apply --config plan.json   # Apply writes from a --plan output

Exit codes:
  0 - Success
  1 - Error (config exists, template missing, etc.)
  2 - Usage error
""",
        )
        parser.add_argument(
            "--yes",
            "-y",
            action="store_true",
            help="Accept all defaults; run non-interactively",
        )
        parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help="Overwrite existing .ll/ll-config.json",
        )
        parser.add_argument(
            "--dry-run",
            "-n",
            action="store_true",
            help="Preview actions without writing files",
        )
        parser.add_argument(
            "--plan",
            action="store_true",
            help=(
                "Emit JSON plan {detected, proposed_config, host_options, warnings} "
                "without writing anything"
            ),
        )
        parser.add_argument(
            "--codex",
            action="store_true",
            help="Install the Codex CLI hook adapter (.codex/hooks.json)",
        )
        parser.add_argument(
            "--root",
            "-C",
            type=Path,
            default=None,
            dest="root",
            help="Project root directory (default: current directory)",
        )

        subparsers = parser.add_subparsers(dest="command")
        apply_parser = subparsers.add_parser(
            "apply",
            help="Apply writes from a --plan JSON output",
        )
        apply_parser.add_argument(
            "--config",
            "-c",
            required=True,
            dest="plan_config",
            help="Path to plan JSON file, or raw JSON string",
        )
        apply_parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            help="Overwrite existing configuration",
        )

        args = parser.parse_args(argv)

        project_root = (args.root or Path.cwd()).resolve()
        plug_root = _plugin_root()
        templates_dir = plug_root / "templates"

        # Auto-detect codex if not explicitly requested
        if not args.codex:
            if shutil.which("codex") or (project_root / ".codex").exists():
                args.codex = True

        if args.command == "apply":
            return _run_apply(
                plan_config=args.plan_config,
                project_root=project_root,
                templates_dir=templates_dir,
                force=getattr(args, "force", False),
            )

        if args.plan:
            return _run_plan(project_root, templates_dir)

        if args.yes or args.dry_run:
            return _run_yes(
                project_root=project_root,
                templates_dir=templates_dir,
                plugin_root=plug_root,
                force=args.force,
                dry_run=args.dry_run,
                codex=args.codex,
            )

        from little_loops.init.tui import run_tui

        return run_tui(
            project_root=project_root,
            templates_dir=templates_dir,
            plugin_root=plug_root,
            force=args.force,
            codex=args.codex,
        )
