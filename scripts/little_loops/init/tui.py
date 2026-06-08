"""Interactive TUI for ll-init using questionary and rich."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Feature choices in display order for the multi-select screen
_FEATURE_CHOICES: list[tuple[str, str]] = [
    ("Parallel processing  (ll-parallel)", "parallel"),
    ("Product analysis  (ll-scan-product)", "product"),
    ("Document tracking", "documents"),
    ("Design tokens", "design_tokens"),
    ("Learning tests registry", "learning_tests"),
    ("Analytics capture", "analytics"),
    ("Context monitor  (auto-handoff)", "context_monitor"),
]

_DEFAULT_FEATURES: frozenset[str] = frozenset(
    {"parallel", "product", "learning_tests", "analytics", "context_monitor"}
)

_FEATURE_LABELS: dict[str, str] = {
    "parallel": "Parallel processing",
    "product": "Product analysis",
    "documents": "Document tracking",
    "design_tokens": "Design tokens",
    "learning_tests": "Learning tests",
    "analytics": "Analytics",
    "context_monitor": "Context monitor",
}

# Host choices for the multi-select screen
_HOST_CHOICES: list[tuple[str, str]] = [
    ("Claude Code  (global plugin — no adapter file needed)", "claude-code"),
    ("Codex CLI  (writes .codex/hooks.json)", "codex"),
    ("Pi  (not yet available — EPIC-1622)", "pi"),
]

_HOST_LABELS: dict[str, str] = {
    "claude-code": "Claude Code",
    "codex": "Codex CLI",
    "pi": "Pi",
}


def run_tui(
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    force: bool = False,
    hosts: list[str] | None = None,
) -> int:
    """Run the interactive TUI for ll-init.

    Args:
        hosts: Detection-seeded default host list shown pre-checked.
               When None, defaults to ["claude-code"].

    Returns:
        0 on success, 1 on user-abort/config-exists/error, 130 on Ctrl-C.
    """
    if not sys.stdin.isatty():
        print(
            "stdin is not a TTY. Run 'll-init --yes' for non-interactive setup.",
            file=sys.stderr,
        )
        return 1

    from little_loops.init.detect import detect_project_type

    console = Console()
    ll_dir = project_root / ".ll"
    config_path = ll_dir / "ll-config.json"

    if config_path.exists() and not force:
        print(
            f"Configuration already exists at {config_path}\n"
            "Use --force to overwrite, or edit the existing file directly.",
            file=sys.stderr,
        )
        return 1

    template = detect_project_type(project_root, templates_dir)
    project_data = template.data.get("project", {})

    console.print(
        f"\n[bold blue]little-loops setup[/bold blue]"
        f" — detected [cyan]{template.name}[/cyan]\n"
    )

    default_hosts: frozenset[str] = frozenset(hosts or ["claude-code"])

    # --- Screen 1: Project basics ---
    console.rule("[bold]1 / 4  Project Basics[/bold]")

    name = questionary.text("Project name:", default=project_root.name).ask()
    if name is None:
        return 130

    src_dir = questionary.text(
        "Source directory:", default=project_data.get("src_dir", "src/")
    ).ask()
    if src_dir is None:
        return 130

    test_cmd = questionary.text(
        "Test command:", default=project_data.get("test_cmd") or ""
    ).ask()
    if test_cmd is None:
        return 130

    lint_cmd = questionary.text(
        "Lint command:", default=project_data.get("lint_cmd") or ""
    ).ask()
    if lint_cmd is None:
        return 130

    type_cmd = questionary.text(
        "Type-check command (optional):",
        default=project_data.get("type_cmd") or "",
    ).ask()
    if type_cmd is None:
        return 130

    format_cmd = questionary.text(
        "Format command (optional):",
        default=project_data.get("format_cmd") or "",
    ).ask()
    if format_cmd is None:
        return 130

    # --- Screen 2: Features ---
    console.print()
    console.rule("[bold]2 / 4  Features[/bold]")

    selected_features: list[str] | None = questionary.checkbox(
        "Enable features:",
        choices=[
            questionary.Choice(label, value=val, checked=(val in _DEFAULT_FEATURES))
            for label, val in _FEATURE_CHOICES
        ],
    ).ask()
    if selected_features is None:
        return 130

    selected_set = set(selected_features)

    # Conditional: parallel worker count (only when parallel is selected)
    parallel_workers: int = 4
    if "parallel" in selected_set:
        workers_str = questionary.text("Max parallel workers:", default="4").ask()
        if workers_str is None:
            return 130
        try:
            parallel_workers = int(workers_str)
            if parallel_workers < 1:
                raise ValueError("must be positive")
        except ValueError:
            console.print("[yellow]Invalid worker count; defaulting to 4.[/yellow]")
            parallel_workers = 4

    # --- Screen 3: Hosts ---
    console.print()
    console.rule("[bold]3 / 4  Hosts[/bold]")

    selected_hosts: list[str] | None = questionary.checkbox(
        "Which host harnesses should ll-init wire adapters for?",
        choices=[
            questionary.Choice(label, value=val, checked=(val in default_hosts))
            for label, val in _HOST_CHOICES
        ],
    ).ask()
    if selected_hosts is None:
        return 130

    # --- Screen 4: Settings target ---
    console.print()
    console.rule("[bold]4 / 4  Settings[/bold]")

    settings_target: str | None = questionary.select(
        "Where should ll tool permissions be written?",
        choices=[
            questionary.Choice(
                ".claude/settings.local.json  (recommended — gitignored)",
                value="local",
            ),
            questionary.Choice(
                ".claude/settings.json  (shared with team)",
                value="shared",
            ),
        ],
    ).ask()
    if settings_target is None:
        return 130

    # --- Build config ---
    config = _build_final_config(
        template=template,
        name=name,
        src_dir=src_dir,
        test_cmd=test_cmd,
        lint_cmd=lint_cmd,
        type_cmd=type_cmd,
        format_cmd=format_cmd,
        selected_set=selected_set,
        parallel_workers=parallel_workers,
    )

    # --- Summary ---
    console.print()
    _render_summary(console, config, project_root, selected_set, selected_hosts, settings_target)
    console.print()

    confirmed: bool | None = questionary.confirm(
        "Apply this configuration?", default=True
    ).ask()
    if confirmed is None:
        return 130
    if not confirmed:
        console.print("[yellow]Aborted — no changes made.[/yellow]")
        return 1

    # --- Apply ---
    _apply_config(
        config=config,
        project_root=project_root,
        ll_dir=ll_dir,
        config_path=config_path,
        templates_dir=templates_dir,
        plugin_root=plugin_root,
        hosts=selected_hosts,
        settings_target=settings_target,
        force=force,
        console=console,
    )
    return 0


def _build_final_config(
    template: Any,
    name: str,
    src_dir: str,
    test_cmd: str,
    lint_cmd: str,
    type_cmd: str,
    format_cmd: str,
    selected_set: set[str],
    parallel_workers: int,
) -> dict[str, Any]:
    """Build the ll-config.json dict from TUI answers."""
    from little_loops.init.core import build_config

    config = build_config(
        template,
        {
            "project_name": name,
            "src_dir": src_dir,
            "product_enabled": "product" in selected_set,
            "analytics_enabled": "analytics" in selected_set,
            "context_monitor_enabled": "context_monitor" in selected_set,
            "learning_tests_enabled": "learning_tests" in selected_set,
        },
    )

    # Apply command overrides (None for cleared/empty fields)
    for key, val in [
        ("test_cmd", test_cmd),
        ("lint_cmd", lint_cmd),
        ("type_cmd", type_cmd),
        ("format_cmd", format_cmd),
    ]:
        config["project"][key] = val or None

    # Optional sections from feature toggles
    if "parallel" in selected_set and parallel_workers != 4:
        config["parallel"] = {"max_workers": parallel_workers}

    if "documents" in selected_set:
        config["documents"] = {"enabled": True}

    if "design_tokens" in selected_set:
        config["design_tokens"] = {"enabled": True}

    return config


def _render_summary(
    console: Console,
    config: dict[str, Any],
    project_root: Path,
    selected_set: set[str],
    selected_hosts: list[str],
    settings_target: str,
) -> None:
    """Render a rich bordered summary panel of the proposed configuration."""
    proj = config.get("project", {})

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", min_width=14)
    table.add_column("Value")

    table.add_row("Project", proj.get("name", project_root.name))
    table.add_row("Source dir", proj.get("src_dir", ""))

    for field, label in [
        ("test_cmd", "Test"),
        ("lint_cmd", "Lint"),
        ("type_cmd", "Type-check"),
        ("format_cmd", "Format"),
    ]:
        val = proj.get(field)
        if val:
            table.add_row(label, str(val))

    enabled = [_FEATURE_LABELS[k] for k in _FEATURE_LABELS if k in selected_set]
    if enabled:
        table.add_row("Features", ", ".join(enabled))

    host_labels = [_HOST_LABELS.get(h, h) for h in selected_hosts]
    table.add_row("Hosts", ", ".join(host_labels) if host_labels else "none")

    sf = (
        ".claude/settings.local.json"
        if settings_target == "local"
        else ".claude/settings.json"
    )
    table.add_row("Settings", sf)

    console.print(
        Panel(table, title="[bold]Configuration Summary[/bold]", border_style="blue")
    )


def _apply_config(
    config: dict[str, Any],
    project_root: Path,
    ll_dir: Path,
    config_path: Path,
    templates_dir: Path,
    plugin_root: Path,
    hosts: list[str],
    settings_target: str,
    force: bool,
    console: Console,
) -> None:
    """Write all ll-init artifacts to disk."""
    from little_loops import __version__
    from little_loops.init.cli import _dispatch_host_adapters
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        deploy_goals,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_settings,
        update_gitignore,
        write_config,
    )

    issues_base = project_root / config.get("issues", {}).get("base_dir", ".issues")

    write_config(config, ll_dir)
    make_issue_dirs(issues_base)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir)

    update_gitignore(project_root)

    settings_file = (
        ".claude/settings.local.json"
        if settings_target == "local"
        else ".claude/settings.json"
    )
    merge_settings(project_root, settings_file=settings_file)

    _dispatch_host_adapters(hosts, project_root, plugin_root, force=force)

    warnings = validate_deps(config, __version__, project_root)
    for w in warnings:
        console.print(f"[yellow]Warning: {w.message}[/yellow]")
        if w.install_hint:
            console.print(f"  Install/fix: {w.install_hint}")

    console.print(
        f"\n[bold green]✓ little-loops initialized in {project_root}[/bold green]"
    )
    console.print(f"  Config: [cyan]{config_path}[/cyan]")
