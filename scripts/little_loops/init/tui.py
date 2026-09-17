"""Interactive TUI for ll-init using questionary and rich."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from little_loops.init.core import (
    _TOGGLEABLE_FEATURES,
    RECOMMENDED_FEATURES,
    existing_feature_choices,
    schema_default,
)

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

# Pre-checked on a fresh wizard run. Derived from the same recommended set
# the headless path applies so `ll-init --yes` and an accepted wizard run
# write the same feature config.
_DEFAULT_FEATURES: frozenset[str] = frozenset(RECOMMENDED_FEATURES)

# build_config choice key -> wizard feature key (they differ only for sync).
_CHOICE_TO_FEATURE: dict[str, str] = {
    f"{name}_enabled": ("github_sync" if name == "sync" else name) for name in _TOGGLEABLE_FEATURES
}

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

# Host display order + what selecting each one writes. Every _KNOWN_HOSTS
# entry appears here; availability ("detected" / "not on PATH") and the
# adapter-pending state are rendered at prompt time from init.cli.
_HOST_CHOICES: list[tuple[str, str]] = [
    ("Claude Code  (global plugin — no adapter file needed)", "claude-code"),
    ("Codex CLI  (writes .codex/hooks.json)", "codex"),
    ("Gemini CLI  (managed hooks in .gemini/settings.json)", "gemini"),
    ("Kimi Code  (managed block in ~/.kimi-code/config.toml — user-global)", "kimi-code"),
    ("Qwen Code  (managed hooks in .qwen/settings.json)", "qwen"),
    ("OpenCode  (adapter not yet available)", "opencode"),
    ("Pi  (adapter not yet available — EPIC-1622)", "pi"),
    ("omp  (adapter not yet available — manual setup)", "omp"),
]

_HOST_LABELS: dict[str, str] = {
    "claude-code": "Claude Code",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
    "kimi-code": "Kimi Code",
    "qwen": "Qwen Code",
    "opencode": "OpenCode",
    "pi": "Pi",
    "omp": "omp",
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


def _features_from_existing_config(cfg: dict[str, Any]) -> frozenset[str]:
    """Extract which TUI feature keys are enabled from an existing ll-config.json.

    Thin mapping over :func:`existing_feature_choices` so the wizard and the
    headless path agree on what "enabled" means for every section.
    """
    choices = existing_feature_choices(cfg)
    return frozenset(
        feature
        for choice_key, feature in _CHOICE_TO_FEATURE.items()
        if choices.get(choice_key) and feature in _FEATURE_LABELS
    )


def _ask_command(
    label: str, default: str, options: list[str] | None, evidence: str = ""
) -> str | None:
    """Ask for a command field using a curated menu when options are provided.

    A detected *default* that is not in the curated *options* is inserted at
    the top of the menu so the introspected value is what gets pre-selected.
    *evidence* (e.g. ``"declared: [tool.ruff] present"``) is shown as the
    prompt's instruction text. Falls through to free-text if the user selects
    "Custom…" or if no options are given. Returns None on Ctrl-C.
    """
    instruction = f"({evidence})" if evidence else None
    if options:
        menu = list(options)
        if default and default not in menu:
            menu.insert(0, default)
        sel_default = default if default in menu else menu[0]
        choices = [questionary.Choice(o, value=o) for o in menu]
        choices.append(questionary.Choice(_CUSTOM_SENTINEL, value=_CUSTOM_SENTINEL))
        chosen = questionary.select(
            label, choices=choices, default=sel_default, instruction=instruction
        ).ask()
        if chosen is None:
            return None
        if chosen == _CUSTOM_SENTINEL:
            return questionary.text(f"{label} (enter custom value):", default=default).ask()
        return chosen
    return questionary.text(label, default=default, instruction=instruction).ask()


def _ask_hosts(project_root: Path, default_hosts: frozenset[str]) -> list[str] | None:
    """Host multi-select with availability labels; confirms user-global writes.

    Returns the selected host list, or ``None`` on Ctrl-C.
    """
    from little_loops.init.cli import _ADAPTER_PENDING_HOSTS, available_hosts

    available = available_hosts(project_root)
    choices = []
    for label, val in _HOST_CHOICES:
        status = "detected" if available.get(val) else "not on PATH"
        choices.append(
            questionary.Choice(
                f"{label}  [{status}]",
                value=val,
                checked=(val in default_hosts),
                disabled="adapter not yet available" if val in _ADAPTER_PENDING_HOSTS else None,
            )
        )
    selected: list[str] | None = questionary.checkbox(
        "Which host harnesses should ll-init wire adapters for?", choices=choices
    ).ask()
    if selected is None:
        return None
    selected = list(selected)
    if "kimi-code" in selected:
        from little_loops.init.writers import kimi_config_path

        ok: bool | None = questionary.confirm(
            f"Kimi Code hooks are written to {kimi_config_path()} — user-global, outside "
            "this project. Continue?",
            default=False,
        ).ask()
        if ok is None:
            return None
        if not ok:
            selected.remove("kimi-code")
    return selected


def _ask_settings_target() -> str | None:
    return questionary.select(
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


def _ask_claude_md(console: Console, project_root: Path) -> tuple[bool, bool] | None:
    """Ask whether to add the CLI-commands block; returns (opt_in, section_present)."""
    _dot_claude_md = project_root / ".claude" / "CLAUDE.md"
    _root_claude_md = project_root / "CLAUDE.md"
    _yes_label = "Yes, create .claude/CLAUDE.md"

    for _candidate in (_dot_claude_md, _root_claude_md):
        if _candidate.exists():
            if "## little-loops" in _candidate.read_text(encoding="utf-8"):
                console.print(
                    "[dim]CLAUDE.md already contains a ## little-loops section — skipping.[/dim]"
                )
                return (False, True)
            _rel = str(_candidate.relative_to(project_root))
            _yes_label = f"Yes, append to {_rel}"
            break

    choice: str | None = questionary.select(
        "Append ll- CLI commands to CLAUDE.md?",
        choices=[
            questionary.Choice(_yes_label, value="yes"),
            questionary.Choice("Skip", value="skip"),
        ],
        default="yes",
    ).ask()
    if choice is None:
        return None
    return (choice == "yes", False)


def _ask_code_graph(console: Console, project_root: Path, mode: str) -> str | None:
    """Code-graph screen: offer to index/install codegraph, show commands, or skip.

    Returns the resolved ``--code-graph`` mode for ``_apply_config``, or
    ``None`` on Ctrl-C. An explicit CLI mode skips the question.
    """
    from little_loops.init.codegraph import (
        CODEGRAPH_PACKAGE,
        detect_codegraph,
        manual_commands,
    )

    console.print()
    console.rule("[bold]Code graph[/bold]")
    status = detect_codegraph(project_root)
    if mode != "auto":
        return mode
    if status.index_present:
        console.print("[dim]codegraph index found at .codegraph/ — ll-code will use it.[/dim]")
        return "auto"

    console.print(
        "[dim]codegraph gives ll-code (and the graph-seeded issue skills) an indexed call "
        "graph; without it a grep/AST fallback is used.[/dim]"
    )
    if status.binary:
        choice: str | None = questionary.select(
            "codegraph is installed but this project isn't indexed yet. Build the index now?",
            choices=[
                questionary.Choice("Index now  (codegraph init .)", value="index"),
                questionary.Choice("Show me the commands", value="commands"),
                questionary.Choice("Skip", value="skip"),
            ],
            default="index",
        ).ask()
    elif status.npm:
        choice = questionary.select(
            "codegraph isn't installed. Install it and index this project now?",
            choices=[
                questionary.Choice(
                    f"Install & index now  (npm install -g {CODEGRAPH_PACKAGE}, then codegraph init .)",
                    value="install",
                ),
                questionary.Choice("Show me the commands", value="commands"),
                questionary.Choice("Skip", value="skip"),
            ],
            default="install",
        ).ask()
    else:
        console.print("[dim]Node.js/npm not found — to add it later:[/dim]")
        for cmd in manual_commands(status):
            console.print(f"  [cyan]{cmd}[/cyan]")
        return "commands"
    if choice is None:
        return None
    return choice if choice in ("index", "install", "commands", "skip") else "skip"


@dataclass
class WizardAnswers:
    """Everything the wizard needs to build and apply a config.

    Seeded from the :class:`Proposal` (so the *Accept detected setup* path
    needs no prompts) and refined screen by screen on the *Customize* path.
    """

    name: str
    src_dir: str
    test_dir: str
    test_cmd: str
    lint_cmd: str
    type_cmd: str
    format_cmd: str
    build_cmd: str
    focus_dirs: list[str]
    custom_excludes: list[str] = field(default_factory=list)
    features: set[str] = field(default_factory=set)
    parallel_workers: int = 2
    worktree_copy_files: list[str] = field(default_factory=list)
    use_feature_branches: bool = False
    use_epic_branches: bool = False
    design_token_profile: str = "default"
    session_digest: bool = True
    prompt_optimization: bool = False
    loop_clear: bool = True
    loop_show_diagrams: str | None = "clean"
    hosts: list[str] = field(default_factory=list)
    settings_target: str = "local"
    claude_md_opt_in: bool = True
    claude_md_section_present: bool = False


def _claude_md_state(project_root: Path) -> tuple[bool, str]:
    """``(section_present, yes_label)`` for the CLAUDE.md screen / accept path."""
    for candidate in (project_root / ".claude" / "CLAUDE.md", project_root / "CLAUDE.md"):
        if candidate.exists():
            if "## little-loops" in candidate.read_text(encoding="utf-8"):
                return True, ""
            return False, f"Yes, append to {candidate.relative_to(project_root)}"
    return False, "Yes, create .claude/CLAUDE.md"


def _answers_from_proposal(
    proposal: Any,
    existing_config: dict[str, Any],
    hosts: list[str],
    *,
    project_root: Path,
    settings_target: str,
    claude_md: bool,
) -> WizardAnswers:
    """Seed the answers from the proposal, the existing config, and CLI flags."""
    template = proposal.template
    project_data = template.data.get("project", {})
    scan_data = template.data.get("scan", {})
    choices = proposal.choices

    def _seed(flat_key: str, fallback: str = "") -> str:
        value = choices.get(flat_key)
        return str(value) if value else fallback

    ex_parallel = existing_config.get("parallel", {})
    ex_loops = existing_config.get("loops", {}).get("run_defaults", {})
    section_present, _ = _claude_md_state(project_root)
    claude_selected = "claude-code" in hosts
    return WizardAnswers(
        name=_seed("project_name", project_root.name),
        src_dir=_seed("src_dir", project_data.get("src_dir", "src/")),
        test_dir=_seed("test_dir", project_data.get("test_dir", "tests")),
        test_cmd=_seed("test_cmd"),
        lint_cmd=_seed("lint_cmd"),
        type_cmd=_seed("type_cmd"),
        format_cmd=_seed("format_cmd"),
        build_cmd=_seed("build_cmd"),
        focus_dirs=list(choices.get("scan_focus_dirs") or scan_data.get("focus_dirs", ["src/"])),
        features=set(
            _features_from_existing_config(existing_config)
            if existing_config
            else _DEFAULT_FEATURES
        ),
        parallel_workers=int(
            ex_parallel.get("max_workers", schema_default("parallel.max_workers"))
        ),
        worktree_copy_files=list(ex_parallel.get("worktree_copy_files", [])),
        use_feature_branches=bool(ex_parallel.get("use_feature_branches", False)),
        use_epic_branches=bool(ex_parallel.get("epic_branches", {}).get("enabled", False)),
        design_token_profile=str(existing_config.get("design_tokens", {}).get("active", "default")),
        session_digest=bool(
            existing_config.get("history", {}).get("session_digest", {}).get("enabled", True)
        ),
        prompt_optimization=bool(
            existing_config.get("prompt_optimization", {}).get("enabled", False)
        ),
        loop_clear=bool(ex_loops.get("clear", True)),
        loop_show_diagrams=ex_loops.get("show_diagrams", "clean"),
        hosts=list(hosts),
        settings_target=settings_target if claude_selected else "skip",
        claude_md_opt_in=bool(claude_md and claude_selected and not section_present),
        claude_md_section_present=section_present,
    )


def _render_env_line(
    console: Console,
    *,
    install_source: str | None,
    installed_version: str | None,
    primary_host: str,
    is_git_repo: bool,
) -> None:
    """One dim status line: package version/source, primary host, git."""
    if install_source is None:
        pkg = "little-loops package not detected"
    else:
        version = f" v{installed_version}" if installed_version else ""
        pkg = f"little-loops{version} ({install_source})"
    git = "git: yes" if is_git_repo else "git: no (run git init for auto-commit / worktrees)"
    console.print(
        f"[dim]{pkg} · host: {_HOST_LABELS.get(primary_host, primary_host)} · {git}[/dim]",
        highlight=False,
    )


def _code_graph_status_text(codegraph: Any) -> str:
    if codegraph is None:
        return "unknown"
    if codegraph.index_present:
        return "indexed (.codegraph/) — ll-code will use it"
    if codegraph.binary:
        return "codegraph installed, project not indexed yet"
    return "not installed (grep/AST fallback) — optional"


def _render_detection_panel(console: Console, proposal: Any, answers: WizardAnswers) -> None:
    """What ll-init detected, with the evidence for every non-default value."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", min_width=14)
    table.add_column("Value")
    table.add_column("Evidence", style="dim")

    from rich.markup import escape

    from little_loops.init.detect import format_detection_summary

    table.add_row("Project type", escape(format_detection_summary(proposal.candidates)), "")
    table.add_row("Project", escape(answers.name), "")
    for label, value, evidence in proposal.provenance_rows(include_default=True):
        # evidence strings like "[tool.ruff] present" would otherwise be eaten as markup
        table.add_row(label, escape(value), escape(evidence))
    feature_labels = [_FEATURE_LABELS[k] for k in _FEATURE_LABELS if k in answers.features]
    table.add_row("Features", ", ".join(feature_labels) if feature_labels else "none", "")
    if proposal.documents_categories:
        n_docs = sum(len(c.get("files", [])) for c in proposal.documents_categories.values())
        table.add_row(
            "Documents", f"{n_docs} docs in {len(proposal.documents_categories)} categories", ""
        )
    table.add_row("Hosts", ", ".join(_HOST_LABELS.get(h, h) for h in answers.hosts), "")
    table.add_row("Code graph", _code_graph_status_text(proposal.codegraph), "")
    console.print(Panel(table, title="[bold]Detected setup[/bold]", border_style="blue"))


def _ask_project(
    console: Console, proposal: Any, answers: WizardAnswers, cmd_options: dict[str, list[str]]
) -> bool:
    """Project basics screen. Returns False on Ctrl-C."""
    console.print()
    console.rule("[bold]Project[/bold]")

    def _hint(key: str) -> str:
        pf = proposal.field_for(key)
        return pf.label if pf is not None and pf.provenance != "default" else ""

    def _instruction(key: str) -> str | None:
        hint = _hint(key)
        return f"({hint})" if hint else None

    name = questionary.text("Project name:", default=answers.name).ask()
    if name is None:
        return False
    answers.name = name

    src_dir = questionary.text(
        "Source directory:", default=answers.src_dir, instruction=_instruction("project.src_dir")
    ).ask()
    if src_dir is None:
        return False
    answers.src_dir = src_dir

    test_cmd = _ask_command(
        "Test command:",
        default=answers.test_cmd,
        options=cmd_options.get("test_cmd"),
        evidence=_hint("project.test_cmd"),
    )
    if test_cmd is None:
        return False
    answers.test_cmd = test_cmd

    lint_cmd = _ask_command(
        "Lint command:",
        default=answers.lint_cmd,
        options=cmd_options.get("lint_cmd"),
        evidence=_hint("project.lint_cmd"),
    )
    if lint_cmd is None:
        return False
    answers.lint_cmd = lint_cmd

    type_cmd = questionary.text(
        "Type-check command (optional):",
        default=answers.type_cmd,
        instruction=_instruction("project.type_cmd"),
    ).ask()
    if type_cmd is None:
        return False
    answers.type_cmd = type_cmd

    format_cmd = _ask_command(
        "Format command (optional):",
        default=answers.format_cmd,
        options=cmd_options.get("format_cmd"),
        evidence=_hint("project.format_cmd"),
    )
    if format_cmd is None:
        return False
    answers.format_cmd = format_cmd
    return True


def _ask_scan(console: Console, proposal: Any, answers: WizardAnswers) -> bool:
    """Scan screen (focus dirs + custom excludes). Returns False on Ctrl-C."""
    console.print()
    console.rule("[bold]Scan[/bold]")
    pf = proposal.field_for("scan.focus_dirs")
    hint = pf.label if pf is not None and pf.provenance != "default" else ""
    focus_dirs_str = questionary.text(
        "Focus directories (comma-separated):",
        default=", ".join(answers.focus_dirs),
        instruction=f"({hint})" if hint else None,
    ).ask()
    if focus_dirs_str is None:
        return False
    answers.focus_dirs = [d.strip() for d in focus_dirs_str.split(",") if d.strip()]

    add_excludes: bool | None = questionary.confirm(
        "Add custom exclude patterns?", default=False
    ).ask()
    if add_excludes is None:
        return False
    if add_excludes:
        custom = questionary.text(
            "Custom exclude patterns (comma-separated glob patterns):", default=""
        ).ask()
        if custom is None:
            return False
        answers.custom_excludes = [p.strip() for p in custom.split(",") if p.strip()]
    return True


def _ask_features(console: Console, answers: WizardAnswers) -> bool:
    """Features screen + the conditional parallel / design-token follow-ups."""
    console.print()
    console.rule("[bold]Features[/bold]")
    selected: list[str] | None = questionary.checkbox(
        "Enable features:",
        choices=[
            questionary.Choice(label, value=val, checked=(val in answers.features))
            for label, val in _FEATURE_CHOICES
        ],
    ).ask()
    if selected is None:
        return False
    answers.features = set(selected)

    if "parallel" in answers.features:
        default_workers = int(schema_default("parallel.max_workers"))
        workers_str = questionary.text(
            "Max parallel workers:", default=str(answers.parallel_workers)
        ).ask()
        if workers_str is None:
            return False
        try:
            answers.parallel_workers = int(workers_str)
            if answers.parallel_workers < 1:
                raise ValueError("must be positive")
        except ValueError:
            console.print(
                f"[yellow]Invalid worker count; defaulting to {default_workers}.[/yellow]"
            )
            answers.parallel_workers = default_workers

        current = set(answers.worktree_copy_files)
        wt_files: list[str] | None = questionary.checkbox(
            "Copy these files into each worktree:",
            choices=[
                questionary.Choice(name, value=name, checked=(name in current))
                for name in (".env", ".env.local", ".secrets")
            ],
        ).ask()
        if wt_files is None:
            return False
        answers.worktree_copy_files = list(wt_files)

        fb_val: bool | None = questionary.confirm(
            "Enable feature-branch mode (branch-per-issue)?", default=answers.use_feature_branches
        ).ask()
        if fb_val is None:
            return False
        answers.use_feature_branches = fb_val

        eb_val: bool | None = questionary.confirm(
            "Enable per-EPIC integration-branch mode (children of an EPIC share one branch)?",
            default=answers.use_epic_branches,
        ).ask()
        if eb_val is None:
            return False
        answers.use_epic_branches = eb_val

    if "design_tokens" in answers.features:
        profile: str | None = questionary.select(
            "Design-token profile:",
            choices=[questionary.Choice(label, value=val) for label, val in _DESIGN_TOKEN_PROFILES],
            default=(
                answers.design_token_profile
                if answers.design_token_profile in {v for _, v in _DESIGN_TOKEN_PROFILES}
                else "default"
            ),
        ).ask()
        if profile is None:
            return False
        if profile == "_custom":
            custom_path = questionary.text("Custom profile path:").ask()
            if custom_path is None:
                return False
            answers.design_token_profile = custom_path
        else:
            answers.design_token_profile = profile
    return True


_SHOW_DIAGRAMS_VALUES: tuple[str, ...] = ("clean", "summary", "layered", "inline")


def _ask_advanced(console: Console, answers: WizardAnswers) -> bool:
    """Advanced toggles, behind a single opt-in confirm. Returns False on Ctrl-C."""
    console.print()
    console.rule("[bold]Advanced[/bold]")
    wants: bool | None = questionary.confirm(
        "Configure advanced options (session digest, prompt optimization, ll-loop run defaults)?",
        default=False,
    ).ask()
    if wants is None:
        return False
    if not wants:
        return True

    session_digest: bool | None = questionary.confirm(
        "Enable ambient session digest?", default=answers.session_digest
    ).ask()
    if session_digest is None:
        return False
    answers.session_digest = session_digest

    prompt_opt: bool | None = questionary.confirm(
        "Enable automatic prompt optimization?", default=answers.prompt_optimization
    ).ask()
    if prompt_opt is None:
        return False
    answers.prompt_optimization = prompt_opt

    loop_clear: bool | None = questionary.confirm(
        "Enable --clear by default for ll-loop run? (recommended)", default=answers.loop_clear
    ).ask()
    if loop_clear is None:
        return False
    answers.loop_clear = loop_clear

    raw_sd: str | None = questionary.select(
        "Default diagram mode for ll-loop run:",
        choices=[
            questionary.Choice("clean  (recommended)", value="clean"),
            questionary.Choice("summary", value="summary"),
            questionary.Choice("layered", value="layered"),
            questionary.Choice("inline", value="inline"),
            questionary.Choice("Disabled", value="__disabled__"),
        ],
        default=(
            answers.loop_show_diagrams
            if answers.loop_show_diagrams in _SHOW_DIAGRAMS_VALUES
            else "clean"
        ),
    ).ask()
    if raw_sd is None:
        return False
    answers.loop_show_diagrams = None if raw_sd == "__disabled__" else raw_sd
    return True


def _ask_claude_surfaces(console: Console, project_root: Path, answers: WizardAnswers) -> bool:
    """Settings target + CLAUDE.md screens (claude-code selected only)."""
    if "claude-code" not in answers.hosts:
        answers.settings_target = "skip"
        answers.claude_md_opt_in = False
        return True
    console.print()
    console.rule("[bold]Claude Code[/bold]")
    settings = _ask_settings_target()
    if settings is None:
        return False
    answers.settings_target = settings
    claude = _ask_claude_md(console, project_root)
    if claude is None:
        return False
    answers.claude_md_opt_in, answers.claude_md_section_present = claude
    return True


def _render_install_status(
    console: Console,
    *,
    install_source: str | None,
    installed_version: str | None,
    selected_hosts: frozenset[str],
    project_root: Path,
) -> bool | None:
    """Plugin/package staleness block. Returns True to continue, False to abort, None on Ctrl-C."""
    from little_loops.init.install_check import (
        InstallStatus,
        check_version,
        fetch_latest_plugin,
        fetch_latest_pypi,
    )

    needs_install = install_source is None
    pkg_outdated = plugin_outdated = adapter_stale = False
    pkg_latest: str | None = None
    plugin_latest: str | None = None
    adapter_stamp: str | None = None

    if install_source in ("local-editable", "pypi") and installed_version is not None:
        with console.status("Checking PyPI for a newer release…"):
            pkg_latest = fetch_latest_pypi()
        if pkg_latest is not None:
            pkg_outdated = check_version(installed_version, pkg_latest) == InstallStatus.OutOfDate

    if "claude-code" in selected_hosts and install_source in (
        "global-claude-code",
        "project-claude-code",
    ):
        with console.status("Checking the plugin marketplace…"):
            plugin_latest = fetch_latest_plugin()
        if installed_version is not None and plugin_latest is not None:
            plugin_outdated = (
                check_version(installed_version, plugin_latest) == InstallStatus.OutOfDate
            )

    # Adapter-staleness rows for non-Claude hosts (codex today), symmetric with
    # the package/plugin rows above (FEAT-2387).
    if "codex" in selected_hosts and installed_version is not None:
        from little_loops.init.writers import read_adapter_gen_version

        adapter_stamp = read_adapter_gen_version(project_root)
        adapter_stale = adapter_stamp is not None and adapter_stamp != installed_version

    if not (needs_install or pkg_outdated or plugin_outdated or adapter_stale):
        return True

    console.print()
    console.rule("[bold]Plugin Install[/bold]")
    if needs_install:
        console.print(
            "[yellow]little-loops package not detected.[/yellow] "
            "ll-* CLI tools require the pip package to be installed."
        )
        console.print("  Install: [cyan]pip install little-loops[/cyan]")
    if pkg_outdated:
        console.print(
            f"[yellow]Package outdated:[/yellow] installed [cyan]{installed_version}[/cyan], "
            f"latest [cyan]{pkg_latest}[/cyan]."
        )
        if install_source == "local-editable":
            console.print("  Upgrade: [cyan]pip install -e <editable-path>[dev][/cyan]")
        else:
            console.print("  Upgrade: [cyan]pip install --upgrade little-loops[/cyan]")
    if plugin_outdated:
        console.print(
            f"[yellow]Plugin outdated:[/yellow] installed [cyan]{installed_version}[/cyan], "
            f"latest [cyan]{plugin_latest}[/cyan]."
        )
        console.print(
            "  Upgrade: [cyan]claude plugin marketplace update little-loops "
            "&& claude plugin update ll@little-loops[/cyan]"
        )
    if adapter_stale:
        console.print(
            f"[yellow]Codex adapter outdated:[/yellow] generated against "
            f"[cyan]{adapter_stamp}[/cyan], package is [cyan]{installed_version}[/cyan]."
        )
        console.print("  Refresh: [cyan]ll-init --upgrade[/cyan]")

    proceed: bool | None = questionary.confirm(
        "Proceed with wizard? (install/upgrade separately after)", default=True
    ).ask()
    if proceed is None:
        return None
    return bool(proceed)


def run_tui(
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    force: bool = False,
    hosts: list[str] | None = None,
    color_choice: bool | None = None,
    code_graph: str = "auto",
    settings_target: str = "local",
    claude_md: bool = True,
) -> int:
    """Run the interactive wizard for ll-init.

    Express-first: after a one-line environment status and a *Detected
    setup* panel (every value labelled with its evidence), the user picks
    **Accept detected setup** (writes immediately) or **Customize** (walks
    the Project → Scan → Features → Hosts → Claude Code → Advanced screens).
    Both paths end with the Code graph screen, a summary, and a confirm.

    Args:
        hosts: Detection-seeded default host list shown pre-checked.
               When None, defaults to ["claude-code"].
        color_choice: Explicit --color/--no-color from the parser. True
            forces rich terminal output, False forces no_color, None lets
            rich auto-detect (which itself honors NO_COLOR).
        code_graph: ``--code-graph`` mode; ``auto`` asks interactively on the
            Code graph screen, any explicit mode skips the question.
        settings_target: ``--settings`` value used by the accept path.
        claude_md: ``--no-claude-md`` inverse, used by the accept path.

    Returns:
        0 on success, 1 on user-abort/error, 130 on Ctrl-C. When stdin is
        not a TTY the headless ``--yes`` flow runs instead (same defaults the
        accept path would write) and its exit code is returned.
    """
    hosts = list(hosts or ["claude-code"])
    if not sys.stdin.isatty():
        from little_loops.cli.output import info
        from little_loops.init.cli import _run_yes

        info("stdin is not a TTY — running non-interactive setup (same as ll-init --yes).")
        return _run_yes(
            project_root=project_root,
            templates_dir=templates_dir,
            plugin_root=plugin_root,
            force=force,
            dry_run=False,
            hosts=hosts,
            settings_target=settings_target,
            claude_md=claude_md,
            code_graph=code_graph,
        )

    from little_loops.logo import print_logo

    if sys.stdout.isatty():
        print_logo()

    from little_loops.init.cli import _state_dir
    from little_loops.init.install_check import detect_installation
    from little_loops.init.proposal import build_proposal
    from little_loops.init.writers import load_existing_config

    if color_choice is False:
        console = Console(no_color=True)
    elif color_choice is True:
        console = Console(force_terminal=True)
    else:
        console = Console()

    ll_dir = _state_dir(project_root)
    config_path = ll_dir / "ll-config.json"
    existing_config = load_existing_config(project_root)

    # --- Environment: package / plugin / adapter staleness -----------------
    install_source, installed_version, install_path = detect_installation(project_root)
    with console.status("Detecting project…"):
        proposal = build_proposal(
            project_root, templates_dir, force=force, existing_config=existing_config
        )
    _render_env_line(
        console,
        install_source=install_source,
        installed_version=installed_version,
        primary_host=hosts[0],
        is_git_repo=proposal.is_git_repo,
    )
    proceed = _render_install_status(
        console,
        install_source=install_source,
        installed_version=installed_version,
        selected_hosts=frozenset(hosts),
        project_root=project_root,
    )
    if proceed is None:
        return 130
    if not proceed:
        console.print("[yellow]Aborted — no changes made.[/yellow]")
        return 1

    answers = _answers_from_proposal(
        proposal,
        existing_config,
        hosts,
        project_root=project_root,
        settings_target=settings_target,
        claude_md=claude_md,
    )
    template = proposal.template
    cmd_options: dict[str, list[str]] = template.meta.get("command_options", {})

    # --- Detected setup + fork ------------------------------------------------
    console.print()
    _render_detection_panel(console, proposal, answers)
    console.print()
    fork: str | None = questionary.select(
        "How do you want to proceed?",
        choices=[
            questionary.Choice("Accept detected setup", value="accept"),
            questionary.Choice("Customize", value="customize"),
            questionary.Choice("Cancel", value="cancel"),
        ],
        default="accept",
    ).ask()
    if fork is None:
        return 130
    if fork == "cancel":
        console.print("[yellow]Aborted — no changes made.[/yellow]")
        return 1

    if fork != "accept":
        if not _ask_project(console, proposal, answers, cmd_options):
            return 130
        if not _ask_scan(console, proposal, answers):
            return 130
        if not _ask_features(console, answers):
            return 130
        console.print()
        console.rule("[bold]Hosts[/bold]")
        selected_hosts = _ask_hosts(project_root, frozenset(answers.hosts))
        if selected_hosts is None:
            return 130
        answers.hosts = selected_hosts
        if not _ask_claude_surfaces(console, project_root, answers):
            return 130
        if not _ask_advanced(console, answers):
            return 130

    # --- Code graph (both paths) ---------------------------------------------
    code_graph_mode = _ask_code_graph(console, project_root, code_graph)
    if code_graph_mode is None:
        return 130

    # --- Build config ---------------------------------------------------------
    from little_loops.init.detect import detect_documents

    documents_categories: dict[str, Any] = {}
    if "documents" in answers.features:
        documents_categories = detect_documents(project_root)

    config = _build_final_config(
        template=template,
        name=answers.name,
        src_dir=answers.src_dir,
        test_dir=answers.test_dir,
        test_cmd=answers.test_cmd,
        lint_cmd=answers.lint_cmd,
        type_cmd=answers.type_cmd,
        format_cmd=answers.format_cmd,
        build_cmd=answers.build_cmd,
        selected_set=answers.features,
        parallel_workers=answers.parallel_workers,
        scan_focus_dirs=answers.focus_dirs,
        scan_custom_excludes=answers.custom_excludes,
        worktree_copy_files=answers.worktree_copy_files,
        use_feature_branches=answers.use_feature_branches,
        use_epic_branches=answers.use_epic_branches,
        design_token_profile=answers.design_token_profile,
        documents_categories=documents_categories,
        session_digest_enabled=answers.session_digest,
        prompt_optimization_enabled=answers.prompt_optimization,
        loop_clear_default=answers.loop_clear,
        loop_show_diagrams_default=answers.loop_show_diagrams,
    )
    if install_source:
        config["install_source"] = install_source

    # --- Summary + confirm ----------------------------------------------------
    console.print()
    _render_summary(
        console,
        config,
        project_root,
        answers.features,
        answers.hosts,
        answers.settings_target,
        claude_md_opt_in=answers.claude_md_opt_in,
        claude_md_section_present=answers.claude_md_section_present,
    )
    console.print()

    confirmed: bool | None = questionary.confirm("Apply this configuration?", default=True).ask()
    if confirmed is None:
        return 130
    if not confirmed:
        console.print("[yellow]Aborted — no changes made.[/yellow]")
        return 1

    _apply_config(
        config=config,
        project_root=project_root,
        ll_dir=ll_dir,
        config_path=config_path,
        templates_dir=templates_dir,
        plugin_root=plugin_root,
        hosts=answers.hosts,
        settings_target=answers.settings_target,
        force=force,
        console=console,
        claude_md_opt_in=answers.claude_md_opt_in,
        existing_config=existing_config,
        install_source=install_source,
        install_path=install_path,
        code_graph=code_graph_mode,
    )
    return 0


def _build_final_config(
    template: Any,
    name: str,
    src_dir: str,
    test_dir: str,
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
    use_epic_branches: bool = False,
    design_token_profile: str = "default",
    documents_categories: dict[str, Any] | None = None,
    session_digest_enabled: bool = True,
    prompt_optimization_enabled: bool = False,
    loop_clear_default: bool = True,
    loop_show_diagrams_default: str | None = "clean",
    build_cmd: str = "",
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
            "loop_clear_default": loop_clear_default,
            "loop_show_diagrams_default": loop_show_diagrams_default,
        },
    )

    # Apply command overrides (None for cleared/empty fields)
    for key, val in [
        ("test_cmd", test_cmd),
        ("lint_cmd", lint_cmd),
        ("type_cmd", type_cmd),
        ("format_cmd", format_cmd),
        ("build_cmd", build_cmd),
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
        if parallel_workers != schema_default("parallel.max_workers"):
            parallel_section["max_workers"] = parallel_workers
        if worktree_copy_files:
            parallel_section["worktree_copy_files"] = list(worktree_copy_files)
        if use_feature_branches:
            parallel_section["use_feature_branches"] = True
        if use_epic_branches:
            parallel_section["epic_branches"] = {"enabled": True}
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
        commands["confidence_gate"] = {
            "enabled": True,
            "readiness_threshold": schema_default("commands.confidence_gate.readiness_threshold"),
            "outcome_threshold": schema_default("commands.confidence_gate.outcome_threshold"),
        }
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
    """Render a rich bordered summary panel of the proposed configuration.

    Config-derived rows come from the shared init/summary.py extraction
    (audit rec-11) — the same rows the headless completion summary prints —
    with the Features row rendered from the user's checkbox selection and
    the wizard-only rows (Hosts, Settings, CLAUDE.md) appended.
    """
    from little_loops.init.summary import summary_rows

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", min_width=14)
    table.add_column("Value")

    for key, value in summary_rows(config, project_root, include_features=False):
        table.add_row(key, value)

    enabled = [_FEATURE_LABELS[k] for k in _FEATURE_LABELS if k in selected_set]
    if enabled:
        table.add_row("Features", ", ".join(enabled))

    host_labels = [_HOST_LABELS.get(h, h) for h in selected_hosts]
    table.add_row("Hosts", ", ".join(host_labels) if host_labels else "none")

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
    existing_config: dict[str, Any] | None = None,
    install_source: str | None = None,
    install_path: str | None = None,
    code_graph: str = "auto",
) -> None:
    """Write all ll-init artifacts to disk."""
    from little_loops import __version__
    from little_loops.init.cli import (
        _code_graph_step,
        _dispatch_host_adapters,
        _is_git_repo,
        _persist_host_selection,
        next_steps,
    )
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        AGENTS_MD_HOSTS,
        deploy_design_tokens,
        deploy_goals,
        deploy_issue_templates,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_settings,
        merge_with_existing,
        update_gitignore,
        write_agents_md,
        write_claude_md,
        write_config,
        write_gemini_md,
    )

    # The wizard's host question is always an explicit user selection —
    # persist it to hooks.host / orchestration.host_cli (audit rec-13).
    _persist_host_selection(config, hosts, explicit=True)

    # Preserve any config keys the wizard does not model (BUG-2310); --force resets.
    config = merge_with_existing(config, existing_config or {}, force)

    issues_base = project_root / config.get("issues", {}).get("base_dir", ".issues")

    if code_graph in ("index", "install"):
        with console.status("Building the codegraph index…"):
            cg_status = _code_graph_step(code_graph, project_root, config, dry_run=False)
    else:
        cg_status = _code_graph_step(code_graph, project_root, config, dry_run=False)

    write_config(config, ll_dir)
    make_issue_dirs(issues_base)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir)

    if config.get("design_tokens", {}).get("enabled"):
        active_profile = config["design_tokens"].get("active", "default")
        deploy_design_tokens(ll_dir, templates_dir, active_profile=active_profile)

    if config.get("issues", {}).get("deploy_templates"):
        deploy_issue_templates(ll_dir, templates_dir)

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
        write_claude_md(project_root, install_source=install_source, install_path=install_path)

    # AGENTS.md is the cross-tool convention read by codex / kimi-code / qwen
    # (AGENTS_MD_HOSTS); claude-specific content stays in CLAUDE.md.
    if any(h in AGENTS_MD_HOSTS for h in hosts):
        write_agents_md(project_root, install_source=install_source, install_path=install_path)

    # GEMINI.md is Gemini CLI's exact analog of CLAUDE.md (FEAT-2190).
    if "gemini" in hosts:
        write_gemini_md(project_root, install_source=install_source, install_path=install_path)

    _dispatch_host_adapters(hosts, project_root, plugin_root, force=force)

    warnings = validate_deps(config, __version__, project_root)
    for w in warnings:
        console.print(f"[yellow]Warning: {w.message}[/yellow]")
        if w.install_hint:
            console.print(f"  Install/fix: {w.install_hint}")

    is_git_repo = _is_git_repo(project_root)
    if not is_git_repo:
        console.print(
            "[yellow]Note: this directory isn't a git repository; git-dependent "
            "features (auto-commit, worktree-based parallel epics) won't work "
            "until you run git init.[/yellow]"
        )

    # Gated glyph: the ✓ must not leak into piped/CI output (audit U-1).
    _mark = "✓ " if console.color_system else ""
    console.print(f"\n[bold green]{_mark}little-loops initialized in {project_root}[/bold green]")
    console.print(f"  Config: [cyan]{config_path}[/cyan]")

    # Next steps — the same hints the headless paths print (audit U-3).
    steps = next_steps(config, hosts=hosts, codegraph=cg_status, is_git_repo=is_git_repo)
    width = max((len(cmd) for cmd, _ in steps), default=0)
    console.print()
    console.print("[bold]Next steps:[/bold]")
    for cmd, desc in steps:
        console.print(f"  [dim]{cmd.ljust(width)}  — {desc}[/dim]")
