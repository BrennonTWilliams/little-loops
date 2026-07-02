"""ll-init: Headless project initialization CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess as _subprocess
import sys
from pathlib import Path
from typing import Any

from little_loops.issue_template import get_bundled_templates_dir
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# Feature keys toggleable via --enable/--disable in the headless path. These map
# to the ``*_enabled`` choice keys honored by build_config(). Richer features
# (parallel, sync, documents, design_tokens, confidence_gate, tdd) carry
# sub-config and remain interactive-only.
_TOGGLEABLE_FEATURES: frozenset[str] = frozenset(
    {
        "product",
        "analytics",
        "context_monitor",
        "learning_tests",
        "decisions",
        "scratch_pad",
        "session_capture",
        "session_digest",
        "prompt_optimization",
    }
)

# Recognized host names for --hosts validation; mirrors _HOST_RUNNER_REGISTRY keys.
_KNOWN_HOSTS: frozenset[str] = frozenset({"claude-code", "codex", "opencode", "pi"})


def _plugin_version() -> str:
    from little_loops import __version__

    return __version__


def _plugin_root() -> Path:
    """Return the little-loops project root (env-var-first resolver).

    Checks CLAUDE_PLUGIN_ROOT first so non-editable installs resolve correctly.
    Falls back to __file__-relative path for editable dev installs.
    """
    import os

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent.parent


def _detect_hosts(project_root: Path) -> list[str]:
    """Return list of detected host harnesses based on installed binaries and project dirs."""
    detected: list[str] = []
    if shutil.which("claude"):
        detected.append("claude-code")
    if shutil.which("codex") or (project_root / ".codex").exists():
        detected.append("codex")
    if shutil.which("opencode"):
        detected.append("opencode")
    if shutil.which("pi"):
        detected.append("pi")
    return detected or ["claude-code"]


def _dispatch_host_adapters(
    hosts: list[str],
    project_root: Path,
    plugin_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Install adapters for each selected host; print per-host post-install notes."""
    from little_loops.init.writers import install_codex_adapter

    for host in hosts:
        if host not in _KNOWN_HOSTS:
            print(
                f"[Warning] Unknown host {host!r}; skipping. Known hosts: {sorted(_KNOWN_HOSTS)}",
                file=sys.stderr,
            )
            continue
        if host == "codex":
            installed = install_codex_adapter(
                project_root, plugin_root, force=force, dry_run=dry_run
            )
            if installed is None:
                print(
                    "[Codex] Warning: adapter template not found in package install; "
                    ".codex/hooks.json was not written.",
                    file=sys.stderr,
                )
            elif installed and not dry_run:
                print("[Codex] Hook adapter installed to .codex/hooks.json")
                print(
                    "[Codex] Note: Codex will show a hook-trust dialog on next session start. "
                    "Hooks are silently skipped (HookRunStatus::Untrusted) until trusted."
                )
        elif host == "opencode":
            print("[OpenCode] Adapter not yet available — opencode orchestration not yet wired.")
        elif host == "pi":
            print("[Pi] Adapter not yet available — tracked in EPIC-1622.")
        # claude-code: no adapter file needed; plugin hooks fire when globally enabled


def _dispatch_host_upgrade(
    hosts: list[str],
    project_root: Path,
    plugin_root: Path,
    install_source: str | None,
) -> None:
    """Refresh every active host's integration surface after a package upgrade.

    Built once, host-parameterized (ARCHITECTURE-049): the claude-code surface
    is a versioned marketplace plugin (scope-aware update), while adapter hosts
    (codex today) get their generated files force-regenerated against the
    upgraded package dir so a stale gen-version stamp / template drift is
    corrected.

    Args:
        hosts: Active hosts (from --hosts / auto-detection).
        project_root: Project root directory.
        plugin_root: Plugin root (passed through to the adapter writer).
        install_source: install_source from detect_installation() — gates the
            claude-code scope-aware behavior ("project-claude-code" auto-updates;
            anything else is advise-only to avoid mutating shared global state).
    """
    from little_loops.host_runner import HostNotConfigured, resolve_host

    for host in hosts:
        if host != "claude-code":
            continue
        # Scope-aware plugin update: auto for project-scoped, advise otherwise.
        if install_source == "project-claude-code":
            try:
                binary = resolve_host().build_version_check().binary
            except HostNotConfigured:
                binary = None
            if binary:
                print("[Claude] Updating project-scoped plugin ll@little-loops...")
                # Best-effort (check=False): a missing/unauthenticated host must
                # never abort the init or config write.
                _subprocess.run(
                    [binary, "plugin", "update", "ll@little-loops"],
                    check=False,
                )
        else:
            print(
                "  Hint: claude plugin update ll@little-loops",
                file=sys.stderr,
            )

    # Adapter hosts: force-regenerate against the upgraded package dir. Reuses
    # the standard per-host dispatch (claude-code is a no-op there) so writers
    # introduced by later work (FEAT-2260: gemini/omp) are picked up for free.
    _dispatch_host_adapters(hosts, project_root, plugin_root, force=True)


def _warn_adapter_staleness(hosts: list[str], project_root: Path) -> None:
    """Warn when a generated adapter's gen-version stamp diverges from the package.

    Warn-only counterpart to :func:`_dispatch_host_upgrade`: run on a non-upgrade
    init so a developer learns their ``.codex/hooks.json`` was generated against
    an older package and should be refreshed with ``--upgrade``.
    """
    from little_loops.init.install_check import installed_package_version
    from little_loops.init.writers import read_adapter_gen_version

    if "codex" not in hosts:
        return
    stamp = read_adapter_gen_version(project_root)
    installed = installed_package_version()
    if stamp and installed and stamp != installed:
        print(
            f"[Codex] Adapter generated against {stamp}, package is now {installed} "
            "— re-run with --upgrade to regenerate .codex/hooks.json.",
            file=sys.stderr,
        )


def _feature_choices_from_args(enable: list[str], disable: list[str]) -> dict[str, Any]:
    """Translate --enable/--disable feature names into build_config choice keys.

    Args:
        enable: Feature names to turn on.
        disable: Feature names to turn off.

    Returns:
        Mapping of ``{name}_enabled`` -> bool for recognized features.

    Raises:
        ValueError: If any name is not a known toggleable feature.
    """
    choices: dict[str, Any] = {}
    unknown = sorted({f for f in (*enable, *disable) if f not in _TOGGLEABLE_FEATURES})
    if unknown:
        raise ValueError(
            f"Unknown feature(s): {', '.join(unknown)}. "
            f"Valid features: {', '.join(sorted(_TOGGLEABLE_FEATURES))}"
        )
    for f in enable:
        choices[f"{f}_enabled"] = True
    for f in disable:
        choices[f"{f}_enabled"] = False
    return choices


def _run_yes(
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    force: bool,
    dry_run: bool,
    hosts: list[str],
    feature_choices: dict[str, Any] | None = None,
    upgrade: bool = False,
) -> int:
    """Execute the non-interactive --yes init flow."""
    from little_loops.logo import print_logo

    # Human-facing banner. The machine-readable --plan/apply paths live in
    # separate functions and never call this, so their JSON output stays clean.
    print_logo()

    from little_loops.init.core import build_config
    from little_loops.init.detect import detect_project_type
    from little_loops.init.install_check import (
        InstallStatus,
        check_version,
        detect_installation,
        fetch_latest_pypi,
    )
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        deploy_design_tokens,
        deploy_goals,
        deploy_issue_templates,
        load_existing_config,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_settings,
        merge_with_existing,
        update_gitignore,
        write_claude_md,
        write_config,
    )

    ll_dir = project_root / ".ll"
    config_path = ll_dir / "ll-config.json"

    # Load existing config as baseline for pre-population (and the merge below).
    existing_config = load_existing_config(project_root)

    if existing_config and not dry_run:
        # --force resets to template defaults; a plain re-init merges (BUG-2310).
        print(
            "Overwriting existing configuration."
            if force
            else "Merging with existing configuration."
        )

    # Detect installation; notify-and-act (only with --upgrade) or warn-only.
    install_source, installed_version, _install_path = detect_installation(project_root)
    if install_source is None:
        print("little-loops package not detected.", file=sys.stderr)
        if upgrade:
            print("  Installing...")
            try:
                _subprocess.run(
                    [sys.executable, "-m", "pip", "install", "little-loops"],
                    check=True,
                )
                install_source = "pypi"
            except _subprocess.CalledProcessError as exc:
                print(f"  Warning: auto-install failed: {exc}", file=sys.stderr)
        else:
            print(
                "  Hint: pip install little-loops  (pass --upgrade to act automatically)",
                file=sys.stderr,
            )
    elif installed_version is not None:
        _latest = fetch_latest_pypi()
        if _latest is not None:
            _status = check_version(installed_version, _latest)
            if _status == InstallStatus.OutOfDate:
                print(
                    f"little-loops version mismatch (installed: {installed_version!r}, "
                    f"latest: {_latest!r})",
                    file=sys.stderr,
                )
                if upgrade:
                    print("  Upgrading...")
                    if install_source == "local-editable":
                        # Resolve true editable path via pip show.
                        _pip_show = _subprocess.run(
                            [sys.executable, "-m", "pip", "show", "little-loops"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        _editable_line = next(
                            (
                                line
                                for line in _pip_show.stdout.splitlines()
                                if line.startswith("Editable project location:")
                            ),
                            None,
                        )
                        if _editable_line:
                            _editable_path = _editable_line.split(": ", 1)[1].strip()
                            try:
                                _subprocess.run(
                                    [
                                        sys.executable,
                                        "-m",
                                        "pip",
                                        "install",
                                        "-e",
                                        f"{_editable_path}[dev]",
                                    ],
                                    check=True,
                                )
                            except _subprocess.CalledProcessError as exc:
                                print(f"  Warning: auto-upgrade failed: {exc}", file=sys.stderr)
                        else:
                            print(
                                "  Warning: could not determine editable install path.",
                                file=sys.stderr,
                            )
                    else:
                        try:
                            _subprocess.run(
                                [
                                    sys.executable,
                                    "-m",
                                    "pip",
                                    "install",
                                    "--upgrade",
                                    "little-loops",
                                ],
                                check=True,
                            )
                        except _subprocess.CalledProcessError as exc:
                            print(f"  Warning: auto-upgrade failed: {exc}", file=sys.stderr)
                else:
                    print(
                        "  Hint: pip install --upgrade little-loops  (pass --upgrade to act automatically)",
                        file=sys.stderr,
                    )

    template = detect_project_type(project_root, templates_dir)
    print(f"Detected project type: {template.name}")

    # Build choices: start from existing config values, then apply CLI overrides.
    choices: dict[str, Any] = {"project_name": project_root.name}
    if existing_config:
        _ex_proj = existing_config.get("project", {})
        if _ex_proj.get("name"):
            choices["project_name"] = _ex_proj["name"]
        if _ex_proj.get("src_dir"):
            choices["src_dir"] = _ex_proj["src_dir"]
        choices.update(
            {
                "product_enabled": existing_config.get("product", {}).get("enabled", True),
                "analytics_enabled": existing_config.get("analytics", {}).get("enabled", True),
                "context_monitor_enabled": existing_config.get("context_monitor", {}).get(
                    "enabled", True
                ),
                "learning_tests_enabled": existing_config.get("learning_tests", {}).get(
                    "enabled", True
                ),
                "decisions_enabled": existing_config.get("decisions", {}).get("enabled", False),
                "scratch_pad_enabled": existing_config.get("scratch_pad", {}).get("enabled", False),
                "session_capture_enabled": existing_config.get("session_capture", {}).get(
                    "enabled", False
                ),
                "session_digest_enabled": existing_config.get("history", {})
                .get("session_digest", {})
                .get("enabled", True),
                "prompt_optimization_enabled": existing_config.get("prompt_optimization", {}).get(
                    "enabled", True
                ),
            }
        )
    if feature_choices:
        choices.update(feature_choices)
    config = build_config(template, choices)

    # Preserve any config keys build_config does not model (BUG-2310); --force
    # bypasses the merge to reset to template defaults.
    config = merge_with_existing(config, existing_config, force)

    if install_source:
        config["install_source"] = install_source

    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    write_config(config, ll_dir, dry_run=dry_run)
    make_issue_dirs(issues_base, dry_run=dry_run)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir, dry_run=dry_run)

    if config.get("design_tokens", {}).get("enabled"):
        deploy_design_tokens(ll_dir, templates_dir, dry_run=dry_run)

    if config.get("issues", {}).get("deploy_templates"):
        deploy_issue_templates(ll_dir, templates_dir, dry_run=dry_run)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir, dry_run=dry_run)

    update_gitignore(project_root, dry_run=dry_run)

    extra_permissions: list[str] | None = None
    if config.get("learning_tests", {}).get("enabled"):
        extra_permissions = ["Skill(ll:explore-api)"]
    merge_settings(project_root, extra_permissions=extra_permissions, dry_run=dry_run)

    write_claude_md(project_root, dry_run=dry_run)

    if upgrade and not dry_run:
        # Host-parameterized surface refresh: force-regenerate adapters and run
        # the scope-aware claude-code plugin update (FEAT-2387).
        _dispatch_host_upgrade(hosts, project_root, plugin_root, install_source)
    else:
        _dispatch_host_adapters(hosts, project_root, plugin_root, force=force, dry_run=dry_run)
        if not dry_run:
            _warn_adapter_staleness(hosts, project_root)

    if not dry_run:
        print("\nValidating dependencies...")
        warnings = validate_deps(config, _plugin_version(), project_root)
        for w in warnings:
            msg = f"Warning: {w.message}"
            if w.install_hint:
                msg += f"\n  Install/fix: {w.install_hint}"
            print(msg, file=sys.stderr)

    if not dry_run:
        print(f"\n✓ little-loops initialized in {project_root}")
        print(f"  Config: {config_path}")
    return 0


def _run_plan(
    project_root: Path,
    templates_dir: Path,
    feature_choices: dict[str, Any] | None = None,
) -> int:
    """Emit a machine-readable JSON plan without writing anything."""
    from little_loops.init.core import build_config
    from little_loops.init.detect import detect_project_type
    from little_loops.init.validate import validate_deps

    template = detect_project_type(project_root, templates_dir)
    choices: dict[str, Any] = {"project_name": project_root.name}
    if feature_choices:
        choices.update(feature_choices)
    config = build_config(template, choices)
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
            "has_pi": bool(shutil.which("pi")),
            "suggested_settings_file": ".claude/settings.local.json",
        },
        "warnings": [{"message": w.message, "install_hint": w.install_hint} for w in warnings],
    }
    print(json.dumps(plan, indent=2))
    return 0


def _run_apply(
    plan_config: str,
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    hosts: list[str],
    force: bool,
) -> int:
    """Apply writes from a --plan JSON (file path or raw JSON string)."""
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        deploy_design_tokens,
        deploy_goals,
        deploy_issue_templates,
        load_existing_config,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_settings,
        merge_with_existing,
        update_gitignore,
        write_claude_md,
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

    # Preserve any config keys the plan does not model (BUG-2310); --force resets.
    config = merge_with_existing(config, load_existing_config(project_root), force)

    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    write_config(config, ll_dir)
    make_issue_dirs(issues_base)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir)

    if config.get("design_tokens", {}).get("enabled"):
        deploy_design_tokens(ll_dir, templates_dir)

    if config.get("issues", {}).get("deploy_templates"):
        deploy_issue_templates(ll_dir, templates_dir)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir)

    update_gitignore(project_root)

    extra_permissions: list[str] | None = None
    if config.get("learning_tests", {}).get("enabled"):
        extra_permissions = ["Skill(ll:explore-api)"]
    merge_settings(project_root, extra_permissions=extra_permissions)

    write_claude_md(project_root)

    _dispatch_host_adapters(hosts, project_root, plugin_root, force=force)

    warnings = validate_deps(config, _plugin_version(), project_root)
    for w in warnings:
        msg = f"Warning: {w.message}"
        if w.install_hint:
            msg += f"\n  Install/fix: {w.install_hint}"
        print(msg, file=sys.stderr)

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
  %(prog)s --yes --upgrade            # Upgrade stale package/plugin automatically
  %(prog)s --plan                     # Emit JSON plan without writing
  %(prog)s apply --config plan.json   # Apply writes from a --plan output
  %(prog)s --yes --enable decisions --enable session_capture
  %(prog)s --yes --disable prompt_optimization

Feature flags (headless --yes / --plan only):
  --enable / --disable accept: product, analytics, context_monitor,
  learning_tests, decisions, scratch_pad, session_capture, session_digest,
  prompt_optimization. Richer features (parallel, sync, documents,
  design_tokens, confidence_gate, tdd) carry sub-config and are
  interactive-only.

Exit codes:
  0 - Success
  1 - Error (template missing, stdin not a TTY, etc.)
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
            "--hosts",
            nargs="+",
            metavar="HOST",
            default=None,
            help=(
                "Host harnesses to install adapters for "
                "(claude-code, codex, pi). Defaults to auto-detected hosts."
            ),
        )
        parser.add_argument(
            "--enable",
            action="append",
            default=[],
            metavar="FEATURE",
            help=(
                "Enable a feature in the headless config (repeatable). "
                "Valid: decisions, scratch_pad, session_capture, product, "
                "analytics, context_monitor, learning_tests, session_digest, "
                "prompt_optimization."
            ),
        )
        parser.add_argument(
            "--disable",
            action="append",
            default=[],
            metavar="FEATURE",
            help=(
                "Disable a feature in the headless config (repeatable). "
                "Same valid names as --enable."
            ),
        )
        parser.add_argument(
            "--upgrade",
            action="store_true",
            help=(
                "Act on version drift automatically (install or upgrade). "
                "Default headless behaviour is warn-only."
            ),
        )
        parser.add_argument(
            "--codex",
            action="store_true",
            help=argparse.SUPPRESS,  # deprecated alias for --hosts codex
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
        templates_dir = get_bundled_templates_dir()

        # Resolve hosts: --hosts takes precedence; --codex is a deprecated alias.
        # When neither is given, auto-detect from installed binaries / project dirs.
        if args.hosts:
            # Expand any comma-separated values (e.g. --hosts claude-code,codex)
            hosts: list[str] = []
            for h in args.hosts:
                hosts.extend(h.split(","))
        elif args.codex:
            hosts = ["codex"]
        else:
            hosts = _detect_hosts(project_root)

        if args.command == "apply":
            return _run_apply(
                plan_config=args.plan_config,
                project_root=project_root,
                templates_dir=templates_dir,
                plugin_root=plug_root,
                hosts=hosts,
                force=getattr(args, "force", False),
            )

        # Resolve --enable/--disable feature flags (headless / plan paths only).
        try:
            feature_choices = _feature_choices_from_args(args.enable, args.disable)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        if feature_choices and not (args.plan or args.yes or args.dry_run):
            print(
                "Error: --enable/--disable require --yes, --dry-run, or --plan "
                "(the interactive wizard uses its own feature checkboxes).",
                file=sys.stderr,
            )
            return 2

        if args.plan:
            return _run_plan(project_root, templates_dir, feature_choices=feature_choices)

        if args.yes or args.dry_run:
            return _run_yes(
                project_root=project_root,
                templates_dir=templates_dir,
                plugin_root=plug_root,
                force=args.force,
                dry_run=args.dry_run,
                hosts=hosts,
                feature_choices=feature_choices,
                upgrade=args.upgrade,
            )

        from little_loops.init.tui import run_tui

        return run_tui(
            project_root=project_root,
            templates_dir=templates_dir,
            plugin_root=plug_root,
            force=args.force,
            hosts=hosts,
        )
