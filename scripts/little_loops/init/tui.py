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
    ("GitHub sync  (ll-sync)", "github_sync"),
    ("Confidence gate", "confidence_gate"),
    ("TDD mode", "tdd"),
    ("Decisions & rules log  (ll-issues decisions)", "decisions"),
    ("Scratch pad  (automation context masking)", "scratch_pad"),
    ("Session event capture  (PreCompact handoff)", "session_capture"),
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
    "github_sync": "GitHub sync",
    "confidence_gate": "Confidence gate",
    "tdd": "TDD mode",
    "decisions": "Decisions & rules log",
    "scratch_pad": "Scratch pad",
    "session_capture": "Session event capture",
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

# Sentinel used in curated command menus for the free-text fallthrough
_CUSTOM_SENTINEL = "Custom…"

# Named design-token profiles (discovered from templates/design-tokens/profiles/)
_DESIGN_TOKEN_PROFILES: list[tuple[str, str]] = [
    ("Default", "default"),
    ("Editorial Mono", "editorial-mono"),
    ("Warm Paper", "warm-paper"),
    ("Custom path…", "_custom"),
]


def _ask_command(label: str, default: str, options: list[str] | None) -> str | None:
    """Ask for a command field using a curated menu when options are provided.

    Falls through to free-text if the user selects "Custom…" or if no options are given.
    Returns None on Ctrl-C.
    """
    if options:
        sel_default = default if default in options else options[0]
        choices = [questionary.Choice(o, value=o) for o in options]
        choices.append(questionary.Choice(_CUSTOM_SENTINEL, value=_CUSTOM_SENTINEL))
        chosen = questionary.select(label, choices=choices, default=sel_default).ask()
        if chosen is None:
            return None
        if chosen == _CUSTOM_SENTINEL:
            return questionary.text(f"{label} (enter custom value):", default=default).ask()
        return chosen
    return questionary.text(label, default=default).ask()


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
    cmd_options: dict[str, list[str]] = template.meta.get("command_options", {})

    console.print(
        f"\n[bold blue]little-loops setup[/bold blue] — detected [cyan]{template.name}[/cyan]\n"
    )

    default_hosts: frozenset[str] = frozenset(hosts or ["claude-code"])

    # --- Screen 1 / 6: Project Basics ---
    console.rule("[bold]1 / 6  Project Basics[/bold]")

    name = questionary.text("Project name:", default=project_root.name).ask()
    if name is None:
        return 130

    src_dir = questionary.text(
        "Source directory:", default=project_data.get("src_dir", "src/")
    ).ask()
    if src_dir is None:
        return 130

    test_cmd = _ask_command(
        "Test command:",
        default=project_data.get("test_cmd") or "",
        options=cmd_options.get("test_cmd"),
    )
    if test_cmd is None:
        return 130

    lint_cmd = _ask_command(
        "Lint command:",
        default=project_data.get("lint_cmd") or "",
        options=cmd_options.get("lint_cmd"),
    )
    if lint_cmd is None:
        return 130

    type_cmd = questionary.text(
        "Type-check command (optional):",
        default=project_data.get("type_cmd") or "",
    ).ask()
    if type_cmd is None:
        return 130

    format_cmd = _ask_command(
        "Format command (optional):",
        default=project_data.get("format_cmd") or "",
        options=cmd_options.get("format_cmd"),
    )
    if format_cmd is None:
        return 130

    # --- Screen 2 / 6: Scan ---
    console.print()
    console.rule("[bold]2 / 6  Scan[/bold]")

    _scan_data = template.data.get("scan", {})
    _default_focus = ", ".join(_scan_data.get("focus_dirs", ["src/"]))
    focus_dirs_str = questionary.text(
        "Focus directories (comma-separated):",
        default=_default_focus,
    ).ask()
    if focus_dirs_str is None:
        return 130

    add_excludes: bool | None = questionary.confirm(
        "Add custom exclude patterns?", default=False
    ).ask()
    if add_excludes is None:
        return 130

    custom_excludes_str = ""
    if add_excludes:
        custom_excludes_str = questionary.text(
            "Custom exclude patterns (comma-separated glob patterns):",
            default="",
        ).ask()
        if custom_excludes_str is None:
            return 130

    # --- Screen 3 / 6: Features ---
    console.print()
    console.rule("[bold]3 / 6  Features[/bold]")

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

    # Conditional: parallel worker count, worktree copy files, and feature-branch mode
    parallel_workers: int = 4
    worktree_copy_files: list[str] = []
    use_feature_branches: bool = False
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

        wt_files: list[str] | None = questionary.checkbox(
            "Copy these files into each worktree:",
            choices=[
                questionary.Choice(".env", value=".env"),
                questionary.Choice(".env.local", value=".env.local"),
                questionary.Choice(".secrets", value=".secrets"),
            ],
        ).ask()
        if wt_files is None:
            return 130
        worktree_copy_files = wt_files

        fb_val: bool | None = questionary.confirm(
            "Enable feature-branch mode (branch-per-issue)?", default=False
        ).ask()
        if fb_val is None:
            return 130
        use_feature_branches = fb_val

    # Conditional: design-token profile picker
    design_token_profile = "default"
    if "design_tokens" in selected_set:
        _profile: str | None = questionary.select(
            "Design-token profile:",
            choices=[questionary.Choice(label, value=val) for label, val in _DESIGN_TOKEN_PROFILES],
        ).ask()
        if _profile is None:
            return 130
        if _profile == "_custom":
            _custom_path = questionary.text("Custom profile path:").ask()
            if _custom_path is None:
                return 130
            design_token_profile = _custom_path
        else:
            design_token_profile = _profile

    # Session digest toggle (always asked)
    session_digest_enabled: bool | None = questionary.confirm(
        "Enable ambient session digest?", default=True
    ).ask()
    if session_digest_enabled is None:
        return 130

    # Prompt optimization opt-out (default-on feature; always asked)
    prompt_optimization_enabled: bool | None = questionary.confirm(
        "Enable automatic prompt optimization?", default=True
    ).ask()
    if prompt_optimization_enabled is None:
        return 130

    # --- Screen 4 / 6: Hosts ---
    console.print()
    console.rule("[bold]4 / 6  Hosts[/bold]")

    selected_hosts: list[str] | None = questionary.checkbox(
        "Which host harnesses should ll-init wire adapters for?",
        choices=[
            questionary.Choice(label, value=val, checked=(val in default_hosts))
            for label, val in _HOST_CHOICES
        ],
    ).ask()
    if selected_hosts is None:
        return 130

    # --- Screen 5 / 6: Settings target ---
    console.print()
    console.rule("[bold]5 / 6  Settings[/bold]")

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
            questionary.Choice(
                "Skip — don't write tool permissions",
                value="skip",
            ),
        ],
    ).ask()
    if settings_target is None:
        return 130

    # --- Screen 6 / 6: CLAUDE.md ---
    console.print()
    console.rule("[bold]6 / 6  CLAUDE.md[/bold]")

    _dot_claude_md = project_root / ".claude" / "CLAUDE.md"
    _root_claude_md = project_root / "CLAUDE.md"
    _claude_md_section_present = False
    _yes_label = "Yes, create .claude/CLAUDE.md"

    for _candidate in (_dot_claude_md, _root_claude_md):
        if _candidate.exists():
            if "## little-loops" in _candidate.read_text(encoding="utf-8"):
                _claude_md_section_present = True
            else:
                _rel = str(_candidate.relative_to(project_root))
                _yes_label = f"Yes, append to {_rel}"
            break

    claude_md_opt_in = False
    if _claude_md_section_present:
        console.print("[dim]CLAUDE.md already contains a ## little-loops section — skipping.[/dim]")
    else:
        _claude_md_choice: str | None = questionary.select(
            "Append ll- CLI commands to CLAUDE.md?",
            choices=[
                questionary.Choice(_yes_label, value="yes"),
                questionary.Choice("Skip", value="skip"),
            ],
            default="yes",
        ).ask()
        if _claude_md_choice is None:
            return 130
        claude_md_opt_in = _claude_md_choice == "yes"

    # --- Compute documents categories ---
    from little_loops.init.detect import detect_documents

    documents_categories: dict[str, Any] = {}
    if "documents" in selected_set:
        documents_categories = detect_documents(project_root)

    # --- Parse scan inputs ---
    scan_focus_dirs = [d.strip() for d in focus_dirs_str.split(",") if d.strip()]
    scan_custom_excludes = [p.strip() for p in custom_excludes_str.split(",") if p.strip()]

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
        scan_focus_dirs=scan_focus_dirs,
        scan_custom_excludes=scan_custom_excludes,
        worktree_copy_files=worktree_copy_files,
        use_feature_branches=use_feature_branches,
        design_token_profile=design_token_profile,
        documents_categories=documents_categories,
        session_digest_enabled=bool(session_digest_enabled),
        prompt_optimization_enabled=bool(prompt_optimization_enabled),
    )

    # --- Summary ---
    console.print()
    _render_summary(
        console,
        config,
        project_root,
        selected_set,
        selected_hosts,
        settings_target,
        claude_md_opt_in=claude_md_opt_in,
        claude_md_section_present=_claude_md_section_present,
    )
    console.print()

    confirmed: bool | None = questionary.confirm("Apply this configuration?", default=True).ask()
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
        claude_md_opt_in=claude_md_opt_in,
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
    scan_focus_dirs: list[str] | None = None,
    scan_custom_excludes: list[str] | None = None,
    worktree_copy_files: list[str] | None = None,
    use_feature_branches: bool = False,
    design_token_profile: str = "default",
    documents_categories: dict[str, Any] | None = None,
    session_digest_enabled: bool = True,
    prompt_optimization_enabled: bool = True,
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
            "decisions_enabled": "decisions" in selected_set,
            "scratch_pad_enabled": "scratch_pad" in selected_set,
            "session_capture_enabled": "session_capture" in selected_set,
            "session_digest_enabled": session_digest_enabled,
            "prompt_optimization_enabled": prompt_optimization_enabled,
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

    # Update scan section with TUI-provided values
    if scan_focus_dirs:
        config["scan"]["focus_dirs"] = scan_focus_dirs
    if scan_custom_excludes:
        existing = list(config["scan"].get("exclude_patterns", []))
        config["scan"]["exclude_patterns"] = existing + scan_custom_excludes

    # Optional sections from feature toggles
    if "parallel" in selected_set:
        parallel_section: dict[str, Any] = {}
        if parallel_workers != 4:
            parallel_section["max_workers"] = parallel_workers
        if worktree_copy_files:
            parallel_section["worktree_copy_files"] = list(worktree_copy_files)
        if use_feature_branches:
            parallel_section["use_feature_branches"] = True
        if parallel_section:
            config["parallel"] = parallel_section

    if "documents" in selected_set:
        doc_section: dict[str, Any] = {"enabled": True}
        if documents_categories:
            doc_section["categories"] = documents_categories
        config["documents"] = doc_section

    if "design_tokens" in selected_set:
        config["design_tokens"] = {"enabled": True, "active": design_token_profile}

    # GitHub sync
    if "github_sync" in selected_set:
        config["sync"] = {"enabled": True}

    # commands block (confidence_gate + tdd_mode)
    commands: dict[str, Any] = {}
    if "confidence_gate" in selected_set:
        commands["confidence_gate"] = {"enabled": True, "readiness_threshold": 85}
    if "tdd" in selected_set:
        commands["tdd_mode"] = True
    if commands:
        config["commands"] = commands

    return config


def _render_summary(
    console: Console,
    config: dict[str, Any],
    project_root: Path,
    selected_set: set[str],
    selected_hosts: list[str],
    settings_target: str,
    claude_md_opt_in: bool = False,
    claude_md_section_present: bool = False,
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

    # New: sync / commands
    if config.get("sync", {}).get("enabled"):
        table.add_row("Sync", "GitHub sync enabled")

    cmds = config.get("commands", {})
    cmd_parts = []
    if cmds.get("confidence_gate", {}).get("enabled"):
        cmd_parts.append("confidence gate")
    if cmds.get("tdd_mode"):
        cmd_parts.append("TDD mode")
    if cmd_parts:
        table.add_row("Commands", ", ".join(cmd_parts))

    # Design-token profile
    dt = config.get("design_tokens", {})
    if dt.get("enabled"):
        table.add_row("Design tokens", dt.get("active", "default"))

    # Documents categories
    doc_cats = config.get("documents", {}).get("categories", {})
    if doc_cats:
        table.add_row("Documents", f"{len(doc_cats)} categories detected")

    # Worktree copy files
    wt_files = config.get("parallel", {}).get("worktree_copy_files", [])
    if wt_files:
        table.add_row("Worktree files", ", ".join(wt_files))

    # Session digest
    sd_enabled = config.get("history", {}).get("session_digest", {}).get("enabled", True)
    table.add_row("Session digest", "on" if sd_enabled else "off")

    # Opt-in feature sections written by the new toggles
    if config.get("decisions", {}).get("enabled"):
        table.add_row("Decisions", "rules log enabled")
    if config.get("scratch_pad", {}).get("enabled"):
        table.add_row("Scratch pad", "enabled")
    if config.get("session_capture", {}).get("enabled"):
        table.add_row("Session capture", "enabled")

    # Prompt optimization (default-on; only written when opted out)
    if config.get("prompt_optimization", {}).get("enabled") is False:
        table.add_row("Prompt optim.", "off")

    if settings_target == "skip":
        sf = "Skip — no permissions written"
    elif settings_target == "local":
        sf = ".claude/settings.local.json"
    else:
        sf = ".claude/settings.json"
    table.add_row("Settings", sf)

    if claude_md_section_present:
        table.add_row("CLAUDE.md", "Already present — skipped")
    elif claude_md_opt_in:
        table.add_row("CLAUDE.md", "Append ll- CLI commands")
    else:
        table.add_row("CLAUDE.md", "Skip")

    console.print(Panel(table, title="[bold]Configuration Summary[/bold]", border_style="blue"))


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
    claude_md_opt_in: bool = False,
) -> None:
    """Write all ll-init artifacts to disk."""
    from little_loops import __version__
    from little_loops.init.cli import _dispatch_host_adapters
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        deploy_design_tokens,
        deploy_goals,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_settings,
        update_gitignore,
        write_claude_md,
        write_config,
    )

    issues_base = project_root / config.get("issues", {}).get("base_dir", ".issues")

    write_config(config, ll_dir)
    make_issue_dirs(issues_base)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir)

    if config.get("design_tokens", {}).get("enabled"):
        active_profile = config["design_tokens"].get("active", "default")
        deploy_design_tokens(ll_dir, templates_dir, active_profile=active_profile)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir)

    update_gitignore(project_root)

    if settings_target != "skip":
        settings_file = (
            ".claude/settings.local.json" if settings_target == "local" else ".claude/settings.json"
        )
        extra_permissions: list[str] | None = None
        if config.get("learning_tests", {}).get("enabled"):
            extra_permissions = ["Skill(ll:explore-api)"]
        merge_settings(
            project_root, settings_file=settings_file, extra_permissions=extra_permissions
        )

    if claude_md_opt_in:
        write_claude_md(project_root)

    _dispatch_host_adapters(hosts, project_root, plugin_root, force=force)

    warnings = validate_deps(config, __version__, project_root)
    for w in warnings:
        console.print(f"[yellow]Warning: {w.message}[/yellow]")
        if w.install_hint:
            console.print(f"  Install/fix: {w.install_hint}")

    console.print(f"\n[bold green]✓ little-loops initialized in {project_root}[/bold green]")
    console.print(f"  Config: [cyan]{config_path}[/cyan]")
