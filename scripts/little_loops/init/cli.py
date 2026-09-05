"""ll-init: Headless project initialization CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess as _subprocess
import sys
from pathlib import Path
from typing import Any

from little_loops.init.codegraph import CODE_GRAPH_MODES
from little_loops.init.core import _TOGGLEABLE_FEATURES
from little_loops.issue_template import get_bundled_templates_dir
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# _TOGGLEABLE_FEATURES (re-exported from init/core.py) lists the feature keys
# toggleable via --enable/--disable in the headless path. These map to the
# ``*_enabled`` choice keys honored by build_config(). Sections with
# sub-config (parallel, documents, design_tokens, sync, confidence_gate, tdd)
# are written in their schema-default shapes when enabled; the TUI remains
# the place to fine-tune sub-values interactively (audit M-1).
__all__ = ["_TOGGLEABLE_FEATURES", "main_init"]

# Recognized host names for --hosts validation. Only hosts with install
# wiring (or an explicit graceful-degradation branch) in
# _dispatch_host_adapters belong here — it does NOT mirror
# _HOST_RUNNER_REGISTRY keys. omp (FEAT-2261) has a real adapter directory
# (scripts/little_loops/hooks/adapters/omp/) but, like opencode, no install
# wiring (Option B) — it still gets an info-only branch. gemini (FEAT-2186)
# has real install wiring via install_gemini_adapter().
_KNOWN_HOSTS: frozenset[str] = frozenset(
    {"claude-code", "codex", "opencode", "pi", "kimi-code", "qwen", "omp", "gemini"}
)


def _plugin_version() -> str:
    """Version the plugin manifest declares, falling back to the package version.

    Reading ``.claude-plugin/plugin.json`` (when the plugin root has one) makes
    ``validate_deps``'s package-vs-plugin comparison meaningful for plugin
    installs; comparing the package to its own ``__version__`` never fires.
    """
    from little_loops import __version__

    manifest = _plugin_root() / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return __version__
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else __version__


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


# Hosts that are recognised but whose adapter is not wired yet. They are
# still listed/detected (an info line explains the gap) but never become the
# *primary* host: a stray `pi` binary on PATH must not make pi the
# orchestration host for a Claude Code project.
_ADAPTER_PENDING_HOSTS: frozenset[str] = frozenset({"pi", "opencode", "omp"})

# Project-local marker directories that count as host evidence even when the
# binary is absent (a teammate initialised the project for that host).
_PROJECT_MARKER_DIRS: dict[str, str] = {
    "codex": ".codex",
    "kimi-code": ".kimi-code",
    "qwen": ".qwen",
    "gemini": ".gemini",
}

# Detection order. Append-only: the order decides the adapter list (and the
# primary fallback) when several host CLIs share PATH, so inserting mid-list
# would change resolution for existing users.
_DETECT_ORDER: tuple[str, ...] = (
    "claude-code",
    "codex",
    "opencode",
    "pi",
    "kimi-code",
    "qwen",
    "gemini",
    "omp",
)


def _host_binary(name: str) -> str | None:
    """Binary basename for a registered host, via the runner registry (no literals)."""
    from little_loops.host_runner import _HOST_RUNNER_REGISTRY

    runner_cls = _HOST_RUNNER_REGISTRY.get(name)
    if runner_cls is None:
        return None
    try:
        return runner_cls().describe_capabilities().binary
    except Exception:  # pragma: no cover - defensive: a runner without capabilities
        return None


def available_hosts(project_root: Path) -> dict[str, bool]:
    """Availability of every known host: binary on PATH or project marker dir present."""
    result: dict[str, bool] = {}
    for name in _DETECT_ORDER:
        binary = _host_binary(name)
        on_path = bool(binary and shutil.which(binary))
        marker = _PROJECT_MARKER_DIRS.get(name)
        in_project = bool(marker and (project_root / marker).exists())
        result[name] = on_path or in_project
    return result


def default_hosts(project_root: Path, existing_config: dict[str, Any] | None = None) -> list[str]:
    """Hosts to wire when ``--hosts`` is not given, primary first.

    Every available host is kept (adapters are cheap and project-local; the
    one user-global write, kimi, is announced before it happens). The primary
    slot — persisted as ``orchestration.host_cli`` — is chosen as:

    1. the existing config's ``orchestration.host_cli``;
    2. else ``resolve_host()`` (``LL_HOST_CLI``, then the runner probe order),
       provided it was detected and has a wired adapter;
    3. else the first detected host with a wired adapter;
    4. else ``claude-code``.
    """
    from little_loops.host_runner import HostNotConfigured, resolve_host

    available = available_hosts(project_root)
    detected = [name for name in _DETECT_ORDER if available.get(name)]

    primary: str | None = None
    configured = (existing_config or {}).get("orchestration", {}).get("host_cli")
    if isinstance(configured, str) and configured in _KNOWN_HOSTS:
        primary = configured
    else:
        try:
            resolved = resolve_host().name
        except HostNotConfigured:
            resolved = None
        if resolved in detected and resolved not in _ADAPTER_PENDING_HOSTS:
            primary = resolved
    if primary is None:
        primary = next((h for h in detected if h not in _ADAPTER_PENDING_HOSTS), None)
    if primary is None:
        primary = detected[0] if detected else "claude-code"
    return [primary, *[h for h in detected if h != primary]]


def _detect_hosts(project_root: Path) -> list[str]:
    """Backward-compatible alias for :func:`default_hosts` (no existing config)."""
    return default_hosts(project_root)


def _dispatch_host_adapters(
    hosts: list[str],
    project_root: Path,
    plugin_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Install adapters for each selected host; print per-host post-install notes."""
    from little_loops.cli.output import error, info, warning
    from little_loops.init.writers import (
        install_codex_adapter,
        install_gemini_adapter,
        install_host_mirrors,
        install_kimi_adapter,
        install_qwen_adapter,
    )

    for host in hosts:
        if host not in _KNOWN_HOSTS:
            error(f"Unknown host {host!r}; skipping. Known hosts: {sorted(_KNOWN_HOSTS)}")
            continue
        if host == "codex":
            installed = install_codex_adapter(
                project_root, plugin_root, force=force, dry_run=dry_run
            )
            if installed is None:
                warning(
                    "Codex: adapter template not found in package install; "
                    ".codex/hooks.json was not written."
                )
            elif installed and not dry_run:
                info("Codex: hook adapter installed to .codex/hooks.json")
                info(
                    "Codex: Codex will show a hook-trust dialog on next session start. "
                    "Hooks are silently skipped (HookRunStatus::Untrusted) until trusted."
                )
        elif host == "kimi-code":
            from little_loops.init.writers import kimi_config_path

            if not dry_run:
                warning(
                    f"Kimi: writing a managed hooks block to {kimi_config_path()} "
                    "(user-global, outside this project)."
                )
            installed = install_kimi_adapter(
                project_root, plugin_root, force=force, dry_run=dry_run
            )
            if installed is None:
                warning(
                    "Kimi: adapter template not found in package install; "
                    "kimi config.toml managed block was not written."
                )
            elif installed and not dry_run:
                info(f"Kimi: hook adapter installed to {kimi_config_path()} (managed block)")
                info(
                    "Kimi: hooks are user-level (kimi has no project-local hook "
                    "file) and take effect in new kimi sessions."
                )
        elif host == "qwen":
            installed = install_qwen_adapter(
                project_root, plugin_root, force=force, dry_run=dry_run
            )
            if installed is None:
                warning(
                    "Qwen: adapter template missing or .qwen/settings.json is "
                    "unparseable; managed hooks were not written."
                )
            elif installed and not dry_run:
                info("Qwen: hook adapter installed to .qwen/settings.json (managed entries)")
                info(
                    "Qwen: hooks take effect in new qwen sessions — interactive "
                    "and `qwen -p` headless alike."
                )
        elif host == "gemini":
            installed = install_gemini_adapter(
                project_root, plugin_root, force=force, dry_run=dry_run
            )
            if installed is None:
                warning(
                    "Gemini: adapter template missing or .gemini/settings.json is "
                    "unparseable; managed hooks were not written."
                )
            elif installed and not dry_run:
                info("Gemini: hook adapter installed to .gemini/settings.json (managed entries)")
                info(
                    "Gemini: SessionStart and PreCompress are advisory-only on Gemini "
                    "(cannot block); BeforeAgent/BeforeTool/AfterTool can block/deny."
                )
        elif host == "opencode":
            info("OpenCode: adapter not yet available — opencode orchestration not yet wired.")
        elif host == "pi":
            info("Pi: adapter not yet available — tracked in EPIC-1622.")
        elif host == "omp":
            info(
                "omp: adapter not yet available — hooks/adapters/omp/ requires manual "
                "bun install + hook registration (see hooks/adapters/omp/README.md)."
            )
        elif host == "claude-code":
            # No adapter file needed; plugin hooks fire when globally enabled.
            # Auto-install the plugin from the marketplace when it's absent —
            # resolve_host() honors LL_HOST_CLI/orchestration.host_cli, so in a
            # codex-configured project this probes the codex binary instead;
            # only meaningful when the active host is claude-code (same caveat
            # as detect_installation()).
            from little_loops.host_runner import HostNotConfigured, resolve_host
            from little_loops.init.install_check import plugin_installed

            try:
                binary: str | None = resolve_host().build_version_check().binary
            except HostNotConfigured:
                binary = None
            if binary and not dry_run and not plugin_installed(binary):
                source = (
                    str(plugin_root)
                    if (plugin_root / ".claude-plugin" / "plugin.json").exists()
                    else "BrennonTWilliams/little-loops"
                )
                info("Claude Code: installing the ll@little-loops plugin (may take a minute)...")
                try:
                    # Best-effort: fails benignly when the marketplace is
                    # already added (mirrors fetch_latest_plugin's precedent).
                    _subprocess.run(
                        [binary, "plugin", "marketplace", "add", source],
                        check=False,
                        timeout=120,
                    )
                except (_subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    pass
                try:
                    result = _subprocess.run(
                        [binary, "plugin", "install", "ll@little-loops", "-y"],
                        check=False,
                        timeout=120,
                    )
                except (_subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                    warning(f"Claude Code: plugin install failed: {exc}")
                else:
                    if result.returncode == 0:
                        info("Claude Code: installed ll@little-loops plugin from marketplace")
                    else:
                        warning(
                            "Claude Code: plugin install exited with code "
                            f"{result.returncode}; run 'claude plugin install "
                            "ll@little-loops' manually"
                        )

        # Copy the pre-built, git-tracked skill/command/agent mirrors (ENH-3389).
        # ll-adapt cannot target project_root (it writes beside the source
        # skills/commands dirs, i.e. into plugin_root), so this is a plain
        # copy rather than a re-run of the emitter pipeline. Unconditional on
        # host selection + adapter-writer outcome, following the FEAT-3372
        # claude-code auto-install precedent (no opt-out flag).
        if host in _ADAPTER_MIRROR_HOSTS:
            label = _ADAPTER_MIRROR_HOSTS[host]
            mirrored = install_host_mirrors(
                project_root, plugin_root, host, force=force, dry_run=dry_run
            )
            if mirrored is None:
                warning(
                    f"{label}: skill/command mirror source not found in package "
                    f"install; .{host}/ mirrors were not written."
                )
            elif mirrored and not dry_run:
                info(f"{label}: skill/command mirrors copied to .{host}/")


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
    from little_loops.cli.output import info
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
                info("Claude Code: updating project-scoped plugin ll@little-loops...")
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
            f"Warning: Codex adapter generated against {stamp}, package is now {installed} "
            "— re-run with --upgrade to regenerate .codex/hooks.json.",
            file=sys.stderr,
        )


def _is_git_repo(project_root: Path) -> bool:
    """Return whether a ``.git`` ancestor exists on the walk up from *project_root*.

    Mirrors :func:`little_loops.paths.find_project_root`'s ``.git`` semantics: checked
    with ``.exists()``, not ``.is_dir()``, since worktrees and submodules use a ``.git``
    *file* rather than a directory. Does not require an existing ``.ll/`` (unlike
    ``find_project_root``, which answers a different question).
    """
    for candidate in (project_root, *project_root.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _warn_config_drift(
    existing_config: dict[str, Any],
    introspection: Any,
    *,
    stream: Any = None,
) -> None:
    """Warn when a freshly-introspected declared value diverges from stored config.

    Warn-only, like :func:`_warn_adapter_staleness`: only ``declared`` provenance
    (a manifest unambiguously states the value) triggers a warning — ``inferred``
    values are too noisy to surface here. The existing config value is always
    kept (BUG-2310); this is purely informational.

    A stored command that runs the *same tool* as the declared one (``python -m
    pytest -q`` vs ``pytest``) is a stylistic variant, not drift, and is
    skipped via :func:`introspect.base_tool_token`.

    Args:
        stream: When given (``--plan``), print plain ``Warning:`` lines to that
            stream so stdout stays pure JSON. Otherwise emit through the shared
            ``cli.output.warning`` helper on stdout so the message lands in
            order with the rest of the run's output.
    """
    from little_loops.cli.output import warning
    from little_loops.init.introspect import base_tool_token

    for dotted_key, iv in introspection.values.items():
        if iv.provenance != "declared":
            continue
        section, field = dotted_key.split(".", 1)
        existing_value = existing_config.get(section, {}).get(field)
        if not existing_value or existing_value == iv.value:
            continue
        if (
            isinstance(existing_value, str)
            and isinstance(iv.value, str)
            and base_tool_token(existing_value) == base_tool_token(iv.value)
        ):
            continue
        msg = (
            f"config has {field} {existing_value!r} but {iv.evidence} declares "
            f"{iv.value!r} — keeping existing config value.\n"
            "  Review: ll-init --plan"
        )
        if stream is not None:
            print(f"Warning: {msg}", file=stream)
        else:
            warning(msg)


def _state_dir(project_root: Path) -> Path:
    """Directory that receives ``ll-config.json`` and the other init artifacts.

    Honors ``LL_STATE_DIR`` (relative to *project_root*) so the write side
    agrees with :func:`little_loops.config.core.resolve_config_path`, which
    already probes that directory first on the read side. Defaults to ``.ll``.
    """
    import os

    state = os.environ.get("LL_STATE_DIR")
    if state:
        return project_root / state
    return project_root / ".ll"


def _feature_choices_from_args(enable: list[str], disable: list[str]) -> dict[str, Any]:
    """Translate --enable/--disable feature names into build_config choice keys.

    Args:
        enable: Feature names to turn on.
        disable: Feature names to turn off.

    Returns:
        Mapping of ``{name}_enabled`` -> bool for recognized features.

    Raises:
        ValueError: If any name is not a known toggleable feature, or the
            same name is passed to both --enable and --disable (audit M-5:
            the contradiction previously resolved silently to disabled).
    """
    unknown = sorted({f for f in (*enable, *disable) if f not in _TOGGLEABLE_FEATURES})
    if unknown:
        raise ValueError(
            f"Unknown feature(s): {', '.join(unknown)}. "
            f"Valid features: {', '.join(sorted(_TOGGLEABLE_FEATURES))}"
        )
    conflicting = sorted(set(enable) & set(disable))
    if conflicting:
        raise ValueError(
            f"Conflicting flags for feature(s): {', '.join(conflicting)} "
            "— passed to both --enable and --disable."
        )
    choices: dict[str, Any] = {}
    for f in enable:
        choices[f"{f}_enabled"] = True
    for f in disable:
        choices[f"{f}_enabled"] = False
    return choices


def _print_introspection_summary(introspection: Any) -> None:
    """Print each non-default introspected value plus any unresolved ambiguity."""
    for dotted_key, iv in introspection.values.items():
        if iv.provenance == "default":
            continue
        field = dotted_key.split(".", 1)[1]
        print(f"  {field}: {iv.value}  ({iv.provenance}: {iv.evidence})")
    for ambiguity in introspection.ambiguities:
        print(
            f"  {ambiguity.field}: kept template default — "
            f"{len(ambiguity.candidates)} candidates found ({', '.join(ambiguity.candidates)})"
        )


def _persist_host_selection(config: dict[str, Any], hosts: list[str], explicit: bool) -> None:
    """Persist an explicit host selection into the config (audit rec-13).

    Init asks which hosts to wire; previously the answer landed only in
    filesystem side effects (adapter files) while the config keys that name
    the host (``hooks.host``, ``orchestration.host_cli``) stayed unset.
    Auto-detected hosts are NOT persisted: detection reflects the machine,
    not a user decision.
    """
    # ``explicit`` is retained for signature stability; since the 2026-09
    # audit the selection is persisted whether it came from --hosts, the
    # wizard, or auto-detection — otherwise resolve_host() could later pick
    # a different host than the one whose adapters were written.
    del explicit
    if not hosts:
        return
    from little_loops.init.core import schema_enum

    primary = hosts[0]
    config.setdefault("orchestration", {})["host_cli"] = primary
    # hooks.host's enum covers only hosts with a hook-intent adapter; skip
    # hosts outside it rather than write a schema-invalid value.
    if primary in schema_enum("hooks.host"):
        config.setdefault("hooks", {})["host"] = primary


_ADAPTER_MIRROR_HOSTS: dict[str, str] = {
    "gemini": "Gemini CLI",
    "kimi-code": "Kimi Code",
    "qwen": "Qwen Code",
}


def next_steps(
    config: dict[str, Any],
    *,
    hosts: list[str],
    codegraph: Any = None,
    is_git_repo: bool = True,
) -> list[tuple[str, str]]:
    """Onboarding hints tailored to what this run configured.

    Returns ``(command, description)`` pairs; :func:`_print_next_steps`
    aligns them. Shared by the headless completion footer and the wizard.
    """
    from little_loops.init.codegraph import manual_commands

    steps: list[tuple[str, str]] = [
        ('/ll:capture-issue "..."', "file your first issue from a plain-English description"),
        ("/ll:scan-codebase", "scan the codebase and file bug/enhancement/feature issues"),
    ]
    if codegraph is not None and not codegraph.index_present:
        cmds = [c for c in manual_commands(codegraph) if c != "ll-code status"]
        steps.append((" && ".join(cmds), "build the code-graph index that ll-code queries"))
    else:
        steps.append(("ll-code status", "check the code-graph index behind ll-code"))
    if not is_git_repo:
        steps.append(("git init", "enable auto-commit and worktree-based parallel work"))
    # gemini/kimi-code/qwen mirror automatically (ENH-3389, via
    # _ADAPTER_MIRROR_HOSTS as the auto-mirror gate in _dispatch_host_adapters);
    # codex is out of scope and still needs this manual follow-up.
    if "codex" in hosts:
        steps.append(("ll-adapt --host codex --apply", "mirror skills/commands for Codex CLI"))
    steps.append(("ll-doctor", "verify host integration and capabilities"))
    steps.append(("/ll:help", "browse every command and skill"))
    return steps


def _print_next_steps(steps: list[tuple[str, str]]) -> None:
    """Print the onboarding next-steps footer (audit U-3).

    Shared by every headless completion path; the TUI renders the same hints
    through rich. Follows cli/loop/info.py's dim-hint styling.
    """
    from little_loops.cli.output import colorize

    width = max((len(cmd) for cmd, _ in steps), default=0)
    print()
    print(colorize("Next steps:", "1"))
    for cmd, desc in steps:
        print(colorize(f"  {cmd.ljust(width)}  — {desc}", "90"))


def _render_headless_summary(
    config: dict[str, Any],
    project_root: Path,
    hosts: list[str],
    config_path: Path | None = None,
    dry_run: bool = False,
    codegraph: Any = None,
    is_git_repo: bool = True,
) -> None:
    """Print the completion summary for headless runs (audit rec-5/rec-11/U-4).

    Shares its row extraction with the TUI's rich summary panel
    (init/summary.py) so both paths report the same configuration, then adds
    the terminal statement a dry run previously lacked and the next-steps
    footer neither path had.
    """
    from little_loops.cli.output import info, status_block, success
    from little_loops.init.summary import summary_rows

    rows = summary_rows(config, project_root)
    rows.append(("Hosts", ", ".join(hosts) if hosts else "none"))
    if codegraph is not None:
        rows.append(
            (
                "Code graph",
                "indexed (.codegraph/)"
                if codegraph.index_present
                else "not indexed — see next steps",
            )
        )
    print()
    print(status_block(dict(rows)))
    print()
    if dry_run:
        success("Dry run complete — no files were written.")
    else:
        success(f"little-loops initialized in {project_root}")
        if config_path is not None:
            info(f"Config: {config_path}")
    _print_next_steps(next_steps(config, hosts=hosts, codegraph=codegraph, is_git_repo=is_git_repo))


_SETTINGS_FILES: dict[str, str] = {
    "local": ".claude/settings.local.json",
    "shared": ".claude/settings.json",
}


def _write_claude_surfaces(
    project_root: Path,
    config: dict[str, Any],
    hosts: list[str],
    *,
    settings_target: str,
    claude_md: bool,
    dry_run: bool,
    install_source: str | None,
    install_path: str | None,
    refresh: bool,
) -> None:
    """Write the Claude Code-specific artifacts when claude-code is a selected host.

    ``settings_target`` is ``local`` (``.claude/settings.local.json``,
    gitignored), ``shared`` (``.claude/settings.json``) or ``skip``;
    ``claude_md`` gates the ``## little-loops CLI Commands`` block.
    """
    from little_loops.init.writers import merge_settings, write_claude_md

    if "claude-code" not in hosts:
        return
    if settings_target in _SETTINGS_FILES:
        extra_permissions: list[str] | None = None
        if config.get("learning_tests", {}).get("enabled"):
            extra_permissions = ["Skill(ll:explore-api)"]
        merge_settings(
            project_root,
            settings_file=_SETTINGS_FILES[settings_target],
            extra_permissions=extra_permissions,
            dry_run=dry_run,
        )
    if claude_md:
        write_claude_md(
            project_root,
            dry_run=dry_run,
            install_source=install_source,
            install_path=install_path,
            refresh=refresh,
        )


def _run_yes(
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    force: bool,
    dry_run: bool,
    hosts: list[str],
    feature_choices: dict[str, Any] | None = None,
    upgrade: bool = False,
    hosts_explicit: bool = False,
    settings_target: str = "local",
    claude_md: bool = True,
    code_graph: str = "auto",
) -> int:
    """Execute the non-interactive --yes init flow."""
    from little_loops.logo import print_logo

    # Human-facing banner. The machine-readable --plan/apply paths live in
    # separate functions and never call this, so their JSON output stays clean.
    # Only emit on an interactive terminal so piped/redirected logs stay bare.
    if sys.stdout.isatty():
        print_logo()

    from little_loops.init.detect import format_detection_summary
    from little_loops.init.install_check import (
        InstallStatus,
        check_version,
        detect_installation,
        fetch_latest_pypi,
    )
    from little_loops.init.proposal import build_proposal
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        AGENTS_MD_HOSTS,
        deploy_design_tokens,
        deploy_goals,
        deploy_issue_templates,
        load_existing_config,
        make_issue_dirs,
        make_learning_tests_dir,
        set_display_root,
        update_gitignore,
        write_agents_md,
        write_config,
        write_gemini_md,
    )

    ll_dir = _state_dir(project_root)
    config_path = ll_dir / "ll-config.json"
    # Dry-run "write ..." lines render relative to the project root.
    set_display_root(project_root)

    # Load existing config as baseline for pre-population (and the merge below).
    existing_config = load_existing_config(project_root)

    if existing_config:
        # --force resets to template defaults; a plain re-init merges (BUG-2310).
        # Printed for dry runs too: the preview must show the same merge
        # disposition the real run will apply (audit U-4).
        print(
            "Overwriting existing configuration."
            if force
            else "Merging with existing configuration."
        )

    # Detect installation; notify-and-act (only with --upgrade) or warn-only.
    install_source, installed_version, install_path = detect_installation(project_root)
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
        _out_info("Checking PyPI for a newer little-loops release...")
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
                        if install_path:
                            try:
                                _subprocess.run(
                                    [
                                        sys.executable,
                                        "-m",
                                        "pip",
                                        "install",
                                        "-e",
                                        f"{install_path}[dev]",
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

    # One pipeline for every surface (headless, --plan, wizard): detection,
    # introspection, existing-config layering, feature defaults, flags, merge.
    proposal = build_proposal(
        project_root,
        templates_dir,
        feature_choices=feature_choices,
        force=force,
        existing_config=existing_config,
    )
    print(format_detection_summary(proposal.candidates))

    documents_categories = proposal.documents_categories
    if documents_categories:
        n_arch = len(documents_categories.get("architecture", {}).get("files", []))
        n_product = len(documents_categories.get("product", {}).get("files", []))
        print(f"Detected {n_arch} architecture docs, {n_product} product docs")

    _print_introspection_summary(proposal.introspection)
    if existing_config:
        _warn_config_drift(existing_config, proposal.introspection)

    config = proposal.config

    if install_source:
        config["install_source"] = install_source
    _persist_host_selection(config, hosts, explicit=hosts_explicit)

    # Code graph: index (or print the commands) before the config write so
    # the code_query block lands in the same write when an index exists.
    cg_status = _code_graph_step(code_graph, project_root, config, dry_run=dry_run)

    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    write_config(config, ll_dir, dry_run=dry_run)
    make_issue_dirs(issues_base, dry_run=dry_run)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir, dry_run=dry_run, force=force)

    if config.get("design_tokens", {}).get("enabled"):
        deploy_design_tokens(ll_dir, templates_dir, dry_run=dry_run, force=force)

    if config.get("issues", {}).get("deploy_templates"):
        deploy_issue_templates(ll_dir, templates_dir, dry_run=dry_run, force=force)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir, dry_run=dry_run, force=force)

    update_gitignore(project_root, dry_run=dry_run)

    # Claude-specific surfaces (tool permissions, CLAUDE.md) only when
    # claude-code is among the selected hosts; a codex-only project gets
    # AGENTS.md instead.
    _write_claude_surfaces(
        project_root,
        config,
        hosts,
        settings_target=settings_target,
        claude_md=claude_md,
        dry_run=dry_run,
        install_source=install_source,
        install_path=install_path,
        refresh=upgrade,
    )

    # AGENTS.md is the cross-tool convention read by codex / kimi-code / qwen
    # (AGENTS_MD_HOSTS); claude-specific content stays in CLAUDE.md.
    if any(h in AGENTS_MD_HOSTS for h in hosts):
        write_agents_md(
            project_root,
            dry_run=dry_run,
            install_source=install_source,
            install_path=install_path,
            refresh=upgrade,
        )

    # GEMINI.md is Gemini CLI's exact analog of CLAUDE.md (FEAT-2190).
    if "gemini" in hosts:
        write_gemini_md(
            project_root,
            dry_run=dry_run,
            install_source=install_source,
            install_path=install_path,
            refresh=upgrade,
        )

    if upgrade and not dry_run:
        # Host-parameterized surface refresh: force-regenerate adapters and run
        # the scope-aware claude-code plugin update (FEAT-2387).
        _dispatch_host_upgrade(hosts, project_root, plugin_root, install_source)
    else:
        _dispatch_host_adapters(hosts, project_root, plugin_root, force=force, dry_run=dry_run)
        if not dry_run:
            _warn_adapter_staleness(hosts, project_root)

    # Dependency validation is read-only and one of the things a dry-run
    # preview is most useful for, so it runs in both modes (audit U-4).
    _report_dependency_warnings(validate_deps(config, _plugin_version(), project_root))
    if not dry_run and not _is_git_repo(project_root):
        _out_warning(
            "This directory isn't a git repository; git-dependent features "
            "(auto-commit, worktree-based parallel epics) won't work until you run git init."
        )

    _render_headless_summary(
        config,
        project_root,
        hosts,
        config_path=config_path,
        dry_run=dry_run,
        codegraph=cg_status,
        is_git_repo=_is_git_repo(project_root),
    )
    return 0


def _code_graph_step(
    mode: str, project_root: Path, config: dict[str, Any], *, dry_run: bool
) -> Any:
    """Run the code-graph step and attach ``code_query`` to *config* when indexed."""
    from little_loops.init.codegraph import code_query_section, run_code_graph_step

    status, result = run_code_graph_step(mode, project_root, dry_run=dry_run)
    if status.index_present or (result is not None and result.ok):
        config.setdefault("code_query", code_query_section())
    return status


def _report_dependency_warnings(warnings: list[Any]) -> None:
    """Print the dependency-validation block: every warning, or a single success line."""
    from little_loops.cli.output import success

    print()
    print("Validating dependencies...")
    for w in warnings:
        _out_warning(w.message + (f"\n  Install/fix: {w.install_hint}" if w.install_hint else ""))
    if not warnings:
        success("All dependencies found")


def _out_info(msg: str) -> None:
    from little_loops.cli.output import info

    info(msg)


def _out_warning(msg: str) -> None:
    from little_loops.cli.output import warning

    warning(msg)


def _run_plan(
    project_root: Path,
    templates_dir: Path,
    feature_choices: dict[str, Any] | None = None,
    upgrade: bool = False,
    force: bool = False,
) -> int:
    """Emit a machine-readable JSON plan without writing anything.

    ``proposed_config`` runs the SAME merge preview ``apply`` performs
    (merge_with_existing against the current config, honoring --force), so
    the plan is the contract it claims to be: what lands on disk after
    ``apply``, not a pre-merge draft (audit M-6).
    """
    from little_loops.init.proposal import build_proposal
    from little_loops.init.writers import DEFAULT_SETTINGS_FILE

    proposal = build_proposal(
        project_root,
        templates_dir,
        feature_choices=feature_choices,
        force=force,
        plugin_version=_plugin_version(),
    )
    if proposal.existing_config:
        _warn_config_drift(proposal.existing_config, proposal.introspection, stream=sys.stderr)

    available = available_hosts(project_root)
    defaults = default_hosts(project_root, proposal.existing_config)
    host_options = {
        "available": available,
        "default": defaults,
        "primary": defaults[0],
        "has_claude_code": bool(shutil.which("claude")),
        "has_codex": bool(shutil.which("codex")),
        "has_opencode": bool(shutil.which("opencode")),
        "has_pi": bool(shutil.which("pi")),
        "has_kimi_code": bool(shutil.which("kimi")),
        "has_qwen": bool(shutil.which("qwen")),
        "suggested_settings_file": DEFAULT_SETTINGS_FILE,
    }
    plan = proposal.to_plan_dict(requested_upgrade=upgrade, host_options=host_options)
    print(json.dumps(plan, indent=2))
    return 0


def _run_apply(
    plan_config: str,
    project_root: Path,
    templates_dir: Path,
    plugin_root: Path,
    hosts: list[str],
    force: bool,
    dry_run: bool = False,
    hosts_explicit: bool = False,
    settings_target: str = "local",
    claude_md: bool = True,
    code_graph: str = "auto",
) -> int:
    """Apply writes from a --plan JSON (file path or raw JSON string).

    ``--dry-run`` previews the application without writing — the one place a
    preview is most valuable, since the plan may have been machine-edited
    (audit M-7). A ``requested_upgrade`` flag in the plan is honored by
    refreshing host integration surfaces after the writes, mirroring the
    ``--yes --upgrade`` post-write behavior.
    """
    from little_loops.cli.output import info, success
    from little_loops.init.install_check import detect_installation
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import (
        AGENTS_MD_HOSTS,
        deploy_design_tokens,
        deploy_goals,
        deploy_issue_templates,
        load_existing_config,
        make_issue_dirs,
        make_learning_tests_dir,
        merge_with_existing,
        set_display_root,
        update_gitignore,
        write_agents_md,
        write_config,
        write_gemini_md,
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
    ll_dir = _state_dir(project_root)
    set_display_root(project_root)

    # Preserve any config keys the plan does not model (BUG-2310); --force resets.
    config = merge_with_existing(config, load_existing_config(project_root), force)
    _persist_host_selection(config, hosts, explicit=hosts_explicit)

    # BUG-3380: resolve install_source/install_path unconditionally, before the
    # writer calls below, so the generated Install: line reflects how this
    # project actually installed little-loops. Reused at the requested_upgrade
    # branch further down instead of calling detect_installation() twice.
    install_source, _installed_version, install_path = detect_installation(project_root)
    if install_source:
        config["install_source"] = install_source

    cg_status = _code_graph_step(code_graph, project_root, config, dry_run=dry_run)

    issues_base_rel = config.get("issues", {}).get("base_dir", ".issues")
    issues_base = project_root / issues_base_rel

    write_config(config, ll_dir, dry_run=dry_run)
    make_issue_dirs(issues_base, dry_run=dry_run)

    if config.get("product", {}).get("enabled"):
        deploy_goals(ll_dir, templates_dir, dry_run=dry_run, force=force)

    # BUG-3274: section presence is the opt-in; key-level defaults (True) apply
    # within it. An absent section stays off — only .get() through a dict that
    # already exists on disk resolves the omitted-key default.
    design_tokens_section = config.get("design_tokens")
    if isinstance(design_tokens_section, dict) and design_tokens_section.get("enabled", True):
        deploy_design_tokens(ll_dir, templates_dir, dry_run=dry_run, force=force)

    if config.get("issues", {}).get("deploy_templates"):
        deploy_issue_templates(ll_dir, templates_dir, dry_run=dry_run, force=force)

    if config.get("learning_tests", {}).get("enabled"):
        make_learning_tests_dir(ll_dir, dry_run=dry_run, force=force)

    update_gitignore(project_root, dry_run=dry_run)

    # ENH-3382: requested_upgrade also refreshes an already-present commands
    # block in place (mirrors _run_yes()'s refresh=upgrade); a plan without
    # requested_upgrade stays a no-op so hand-edited blocks aren't clobbered.
    _refresh = bool(plan.get("requested_upgrade"))
    _write_claude_surfaces(
        project_root,
        config,
        hosts,
        settings_target=settings_target,
        claude_md=claude_md,
        dry_run=dry_run,
        install_source=install_source,
        install_path=install_path,
        refresh=_refresh,
    )

    # AGENTS.md is the cross-tool convention read by codex / kimi-code / qwen
    # (AGENTS_MD_HOSTS); claude-specific content stays in CLAUDE.md.
    if any(h in AGENTS_MD_HOSTS for h in hosts):
        write_agents_md(
            project_root,
            dry_run=dry_run,
            install_source=install_source,
            install_path=install_path,
            refresh=_refresh,
        )

    # GEMINI.md is Gemini CLI's exact analog of CLAUDE.md (FEAT-2190).
    if "gemini" in hosts:
        write_gemini_md(
            project_root,
            dry_run=dry_run,
            install_source=install_source,
            install_path=install_path,
            refresh=_refresh,
        )

    _dispatch_host_adapters(hosts, project_root, plugin_root, force=force, dry_run=dry_run)

    _report_dependency_warnings(validate_deps(config, _plugin_version(), project_root))

    if plan.get("requested_upgrade") and not dry_run:
        _dispatch_host_upgrade(hosts, project_root, plugin_root, install_source)

    if dry_run:
        success("Dry run complete — no files were written.")
        info("Re-run without --dry-run to apply this plan.")
    else:
        success(f"Applied init plan to {project_root}")
    _print_next_steps(
        next_steps(config, hosts=hosts, codegraph=cg_status, is_git_repo=_is_git_repo(project_root))
    )
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
  %(prog)s --yes --force              # Reset config and redeploy bundled artifacts
  %(prog)s --yes --upgrade            # Upgrade stale package/plugin automatically
  %(prog)s --plan                     # Emit JSON plan without writing
  %(prog)s apply --config plan.json   # Apply writes from a --plan output
  %(prog)s apply --config plan.json --dry-run   # Preview a plan application
  %(prog)s --yes --enable decisions --enable session_capture
  %(prog)s --yes --enable parallel --enable sync
  %(prog)s --yes --code-graph install  # Install codegraph and build the ll-code index
  %(prog)s --yes --hosts codex --no-claude-md

Feature flags (headless --yes / --plan only):
  --enable / --disable accept: product, analytics, context_monitor,
  learning_tests, decisions, scratch_pad, session_capture, session_digest,
  prompt_optimization, parallel, documents, design_tokens, sync,
  confidence_gate, tdd. Enabling a sub-config section writes its
  schema-default shape; use the interactive wizard to fine-tune sub-values.

Scope of --force:
  Resets .ll/ll-config.json to template defaults and redeploys bundled
  artifacts (goals, issue section templates, design-token profiles,
  learning-tests placeholder); regenerates host adapters. Does NOT rewrite
  a ## little-loops section already present in CLAUDE.md/AGENTS.md/GEMINI.md
  — use --upgrade for that (see below).

Exit codes:
  0   - Success
  1   - Error (template missing, unreadable config, etc.)
  2   - Usage error
  130 - Interrupted (Ctrl-C in the interactive wizard)
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
            help=(
                "Overwrite existing .ll/ll-config.json and redeploy bundled "
                "artifacts (goals, issue templates, design-token profiles)"
            ),
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
            action="append",
            metavar="HOST",
            default=None,
            help=(
                "Host harnesses to install adapters for "
                "(claude-code, codex, opencode, kimi-code, pi, qwen, gemini). Repeatable, "
                "and comma-separated values are accepted (--hosts claude-code,codex). "
                "Defaults to auto-detected hosts."
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
                "prompt_optimization, parallel, documents, design_tokens, "
                "sync, confidence_gate, tdd."
            ),
        )
        parser.add_argument(
            "--disable",
            action="append",
            default=[],
            metavar="FEATURE",
            help=(
                "Disable a feature in the headless config (repeatable). "
                "Same valid names as --enable. Passing the same name to both "
                "--enable and --disable is a usage error."
            ),
        )
        _color_group = parser.add_mutually_exclusive_group()
        _color_group.add_argument(
            "--color",
            action="store_true",
            help="Force colored output even when stdout is not a TTY",
        )
        _color_group.add_argument(
            "--no-color",
            action="store_true",
            help="Disable colored output (NO_COLOR is always honored too)",
        )
        parser.add_argument(
            "--upgrade",
            action="store_true",
            help=(
                "Act on version drift automatically (install or upgrade). "
                "Also refreshes an already-present ## little-loops CLI Commands "
                "section in CLAUDE.md/AGENTS.md/GEMINI.md wholesale (hand edits "
                "inside it are discarded). Default headless behaviour is warn-only."
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
        _settings_group = parser.add_mutually_exclusive_group()
        _settings_group.add_argument(
            "--settings",
            choices=("local", "shared", "skip"),
            default="local",
            help=(
                "Where to write ll tool permissions when claude-code is a host: "
                "local (.claude/settings.local.json, gitignored; default), "
                "shared (.claude/settings.json), or skip."
            ),
        )
        _settings_group.add_argument(
            "--no-settings",
            action="store_true",
            help="Alias for --settings skip.",
        )
        parser.add_argument(
            "--no-claude-md",
            action="store_true",
            help="Do not add the ## little-loops CLI Commands block to CLAUDE.md.",
        )
        parser.add_argument(
            "--code-graph",
            choices=CODE_GRAPH_MODES,
            default="auto",
            help=(
                "Code-graph index for ll-code (codegraph): auto (default; build the index "
                "when the codegraph binary is installed, otherwise print the commands), "
                "install (npm install -g @colbymchenry/codegraph, then index), index "
                "(build the index; uses npx if the binary is absent), commands (print "
                "the commands only), skip."
            ),
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
        # Distinct dests so the subparser defaults don't shadow values the
        # parent parser already parsed (BUG: ``ll-init --force apply`` used
        # to silently downgrade to a merge because this subparser's default
        # False overwrote the parent's True). Both positions are resolved by
        # OR-combining in main_init.
        apply_parser.add_argument(
            "--force",
            "-f",
            action="store_true",
            dest="apply_force",
            help="Overwrite existing configuration",
        )
        apply_parser.add_argument(
            "--dry-run",
            "-n",
            action="store_true",
            dest="apply_dry_run",
            help="Preview the plan application without writing files",
        )

        args = parser.parse_args(argv)

        # Shared output layer (audit U-1): ll-init previously bypassed
        # cli/output.py entirely, ignoring config color settings, NO_COLOR,
        # and FORCE_COLOR. The --color/--no-color flags refine the default
        # gate; NO_COLOR still wins over an explicit --color.
        import os as _os

        from little_loops.cli.output import configure_output, set_use_color

        configure_output()
        if args.no_color:
            set_use_color(False)
        elif args.color and _os.environ.get("NO_COLOR", "") == "":
            set_use_color(True)
        color_choice: bool | None = False if args.no_color else (True if args.color else None)

        try:
            project_root = (args.root or Path.cwd()).resolve()
            plug_root = _plugin_root()
            templates_dir = get_bundled_templates_dir()

            # Resolve hosts: --hosts takes precedence; --codex is a deprecated alias.
            # When neither is given, auto-detect from installed binaries / project dirs.
            # hosts_explicit distinguishes a user decision from machine
            # detection for config persistence (audit rec-13).
            if args.hosts:
                # Expand any comma-separated values (e.g. --hosts claude-code,codex)
                hosts: list[str] = []
                for h in args.hosts:
                    hosts.extend(h.split(","))
                hosts_explicit = True
            elif args.codex:
                hosts = ["codex"]
                hosts_explicit = True
            else:
                from little_loops.init.writers import load_existing_config

                hosts = default_hosts(project_root, load_existing_config(project_root))
                hosts_explicit = False
            settings_target = "skip" if args.no_settings else args.settings
            claude_md = not args.no_claude_md
            code_graph: str = args.code_graph

            if args.command == "apply":
                return _run_apply(
                    plan_config=args.plan_config,
                    project_root=project_root,
                    templates_dir=templates_dir,
                    plugin_root=plug_root,
                    hosts=hosts,
                    # OR-combined: both the parent flag position
                    # (ll-init --force apply) and the subparser position
                    # (ll-init apply --force) must work (audit H-1).
                    force=getattr(args, "force", False) or getattr(args, "apply_force", False),
                    dry_run=getattr(args, "dry_run", False)
                    or getattr(args, "apply_dry_run", False),
                    hosts_explicit=hosts_explicit,
                    settings_target=settings_target,
                    claude_md=claude_md,
                    code_graph=code_graph,
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
                return _run_plan(
                    project_root,
                    templates_dir,
                    feature_choices=feature_choices,
                    upgrade=args.upgrade,
                    force=args.force,
                )

            if args.yes or args.dry_run or args.upgrade:
                return _run_yes(
                    project_root=project_root,
                    templates_dir=templates_dir,
                    plugin_root=plug_root,
                    force=args.force,
                    dry_run=args.dry_run,
                    hosts=hosts,
                    feature_choices=feature_choices,
                    upgrade=args.upgrade,
                    hosts_explicit=hosts_explicit,
                    settings_target=settings_target,
                    claude_md=claude_md,
                    code_graph=code_graph,
                )

            from little_loops.init.tui import run_tui

            return run_tui(
                project_root=project_root,
                templates_dir=templates_dir,
                plugin_root=plug_root,
                force=args.force,
                hosts=hosts,
                color_choice=color_choice,
                code_graph=code_graph,
                settings_target=settings_target,
                claude_md=claude_md,
            )
        except KeyError as exc:
            # schema_default()/schema_enum() raise KeyError when the bundled
            # config-schema.json and build_config() disagree — an install
            # problem, not a user error, so say so instead of a traceback.
            print(
                f"Error: little-loops config schema is out of sync with this install "
                f"({exc}). Try: pip install --upgrade little-loops",
                file=sys.stderr,
            )
            return 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            # ValueError included: version strings compared during init come
            # from pip/plugin output and are external input (audit H-3).
            print(f"Error: {exc}", file=sys.stderr)
            return 1
