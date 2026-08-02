"""File mutation helpers for headless ll-init."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from little_loops.file_utils import atomic_write, atomic_write_json
from little_loops.init.core import strip_none_leaves

# Entries added to .gitignore by ll-init (idempotently).
#
# ``.ll/`` follows the ``.claude/`` model: the **repo-root** directory is tracked and
# committed (the decisions log ``.ll/decisions.yaml`` + ``.ll/decisions.d/*.json``,
# the learning-test registry, ``templates/``, ``ll-goals.md`` — curated artifacts a
# team shares), with machine-local state ignored file-by-file. Every **nested**
# ``.ll/`` is ignored outright: those are strays created when an ``ll-*`` command or
# hook runs from a subdirectory (ENH-2927), never something to commit.
#
# Order is load-bearing: git is last-match-wins, so ``!/.ll/`` must follow ``**/.ll/``.
# The negation un-excludes the *directory entry*, so git still descends into the root
# ``.ll/`` and applies the per-file ignores above — git's "cannot re-include a file
# under an excluded parent" rule does not apply here.
#
# Glob forms (``.ll/history.db*``) rather than one entry per suffix: they cover the
# sqlite ``-shm``/``-wal`` siblings and keep each entry a non-substring of every other,
# which ``test_partial_entries_only_appends_missing`` relies on.
_GITIGNORE_COMMENT = "# little-loops state files"
_GITIGNORE_ENTRIES: tuple[str, ...] = (
    ".auto-manage-state.json",
    ".parallel-manage-state.json",
    ".ll/ll-context-state.json",
    ".ll/ll-sync-state.json",
    ".ll/ll-session-events.jsonl",
    ".ll/history.db*",
    ".ll/queue.db*",
    ".ll/*.lock",
    # Nested .ll/ strays — ignore at any depth, keep the repo-root .ll/ tracked.
    "**/.ll/",
    "!/.ll/",
)

# Canonical permission entries for .claude/settings*.json (Step 10 of the skill).
# Derived from scripts/pyproject.toml [project.scripts]: every ll- entry point
# except mcp-call (not part of the ll- CLI surface). Kept in sync with the
# "All ll- commands" preset in skills/configure/areas.md by ll-verify-cli-allowlist
# (BUG-2764).
_LL_PERMISSIONS: tuple[str, ...] = (
    "Bash(ll-action:*)",
    "Bash(ll-adapt:*)",
    "Bash(ll-adapt-agents-for-codex:*)",
    "Bash(ll-adapt-skills-for-codex:*)",
    "Bash(ll-artifact:*)",
    "Bash(ll-auto:*)",
    "Bash(ll-check-links:*)",
    "Bash(ll-code:*)",
    "Bash(ll-compact-session:*)",
    "Bash(ll-config:*)",
    "Bash(ll-create-extension:*)",
    "Bash(ll-ctx-stats:*)",
    "Bash(ll-deps:*)",
    "Bash(ll-doctor:*)",
    "Bash(ll-generate-schemas:*)",
    "Bash(ll-generate-skill-descriptions:*)",
    "Bash(ll-gitignore:*)",
    "Bash(ll-harness:*)",
    "Bash(ll-help:*)",
    "Bash(ll-history:*)",
    "Bash(ll-history-context:*)",
    "Bash(ll-init:*)",
    "Bash(ll-issues:*)",
    "Bash(ll-learning-tests:*)",
    "Bash(ll-logs:*)",
    "Bash(ll-loop:*)",
    "Bash(ll-messages:*)",
    "Bash(ll-migrate:*)",
    "Bash(ll-migrate-labels:*)",
    "Bash(ll-migrate-relationships:*)",
    "Bash(ll-migrate-status:*)",
    "Bash(ll-parallel:*)",
    "Bash(ll-queue:*)",
    "Bash(ll-session:*)",
    "Bash(ll-sprint:*)",
    "Bash(ll-sync:*)",
    "Bash(ll-verify-cli-allowlist:*)",
    "Bash(ll-verify-decisions:*)",
    "Bash(ll-verify-des-audit:*)",
    "Bash(ll-verify-design-tokens:*)",
    "Bash(ll-verify-docs:*)",
    "Bash(ll-verify-host-map:*)",
    "Bash(ll-verify-kinds:*)",
    "Bash(ll-verify-private-refs:*)",
    "Bash(ll-verify-package-data:*)",
    "Bash(ll-verify-skill-budget:*)",
    "Bash(ll-verify-skill-prose:*)",
    "Bash(ll-verify-skills:*)",
    "Bash(ll-verify-triggers:*)",
    "Bash(ll-workflows:*)",
    # Claude Code's file-permission check only consults Edit(path) rules; a single
    # Edit(...) rule covers every file-editing tool (Write, Edit, NotebookEdit).
    "Edit(.ll/ll-continue-prompt.md)",
)

# Retired canonical entries swept from ``permissions.allow`` on re-init so a
# project initialized by an older ll-init doesn't keep a dead rule (BUG-2758).
_LEGACY_LL_PERMISSIONS: tuple[str, ...] = ("Write(.ll/ll-continue-prompt.md)",)

_ISSUE_SUBDIRS: tuple[str, ...] = (
    "bugs",
    "features",
    "enhancements",
    "epics",
)

# Sentinel string used to detect whether the ll section already exists in
# CLAUDE.md / AGENTS.md
_CLAUDE_MD_SECTION_MARKER = "## little-loops"

# Host-generic ll-* CLI one-liners shared by the CLAUDE.md and AGENTS.md
# writers (FEAT-2915). write_claude_md applies _CLAUDE_MD_DESC_OVERRIDES so
# its emitted block stays byte-identical to the pre-shared-constant version;
# AGENTS.md (read by Codex, Kimi Code, and other non-Claude hosts) gets the
# generic text.
_LL_COMMANDS: tuple[tuple[str, str], ...] = (
    ("ll-action", "Invoke ll skills as one-shot commands with JSON-structured output"),
    (
        "ll-harness",
        "One-shot runner evaluation (skill, cmd, mcp, prompt, dsl) with exit-code and semantic criteria",
    ),
    ("ll-help", "List every command/skill catalog entry, generated from frontmatter"),
    ("ll-auto", "Process all backlog issues sequentially in priority order"),
    ("ll-parallel", "Process issues concurrently using isolated git worktrees"),
    ("ll-sprint", "Define and execute curated issue sets with dependency-aware ordering"),
    ("ll-loop", "Execute FSM-based automation loops"),
    ("ll-workflows", "Identify multi-step workflow patterns from user message history"),
    ("ll-messages", "Extract user messages from host session logs"),
    (
        "ll-history",
        "View completed issue statistics, analysis, rework-rate signals, and export "
        "topic-filtered excerpts from history",
    ),
    (
        "ll-history-context",
        "Render a `## Historical Context` block for an issue from `.ll/history.db`",
    ),
    ("ll-deps", "Cross-issue dependency analysis and validation"),
    ("ll-sync", "Sync local issues with GitHub Issues"),
    ("ll-verify-docs", "Verify documented counts match actual file counts"),
    ("ll-verify-package-data", "Lint __file__ escapes and verify manifest assets are in-wheel"),
    ("ll-verify-skills", "Check that no SKILL.md exceeds 500 lines"),
    ("ll-check-links", "Check markdown documentation for broken links"),
    (
        "ll-issues",
        "Issue management and visualization (next-id, list, show, path, sequence, "
        "impact-effort, refine-status, set-status, anchor-sweep, fingerprint, "
        "epic-progress, decisions)",
    ),
    ("ll-gitignore", "Suggest and apply `.gitignore` patterns based on untracked files"),
    ("ll-create-extension", "Scaffold a new little-loops extension project"),
    (
        "ll-generate-schemas",
        "Regenerate JSON Schema files for all LLEvent types (maintainer tool)",
    ),
    ("ll-learning-tests", "Query and manage the learning test registry (check/list/mark-stale)"),
    (
        "ll-logs",
        "Discover, extract, and analyze (sequences, scan-failures) ll-relevant "
        "log entries from host project logs",
    ),
    ("ll-doctor", "Check host CLI capability support for little-loops features"),
    (
        "ll-ctx-stats",
        "Show context-window analytics for the current project (per-tool byte vs. "
        "context savings; skill-health signals; waste view over token spend on "
        "no-artifact runs)",
    ),
    ("ll-adapt", "Generate host-specific artefacts for a given host (``--host codex``, etc.)"),
    (
        "ll-adapt-skills-for-codex",
        "Add Codex Skills API frontmatter to skills and bridge commands (alias for ll-adapt --host codex)",
    ),
    (
        "ll-adapt-agents-for-codex",
        "Generate `.codex/agents/*.toml` from `agents/*.md` (alias for ll-adapt --host codex)",
    ),
)

# Claude-specific description overrides — write_claude_md's emitted block is
# unchanged from before the shared-constant refactor (FEAT-2915).
_CLAUDE_MD_DESC_OVERRIDES: dict[str, str] = {
    "ll-messages": "Extract user messages from Claude Code logs",
    "ll-logs": (
        "Discover, extract, and analyze (sequences, scan-failures) ll-relevant "
        "log entries from Claude project logs"
    ),
}


def _render_commands_block(desc_overrides: dict[str, str] | None = None) -> str:
    """Render the canonical ## little-loops CLI Commands block."""
    overrides = desc_overrides or {}
    lines = ["", "## little-loops CLI Commands", ""]
    lines.extend(f"- `{name}` - {overrides.get(name, desc)}" for name, desc in _LL_COMMANDS)
    lines.extend(["", 'Install: `pip install -e "./scripts[dev]"`', ""])
    return "\n".join(lines)


# Canonical CLI Commands block appended/created by write_claude_md (Step 11 of the skill)
_CLAUDE_MD_COMMANDS_BLOCK = _render_commands_block(_CLAUDE_MD_DESC_OVERRIDES)

# Host-generic variant appended/created by write_agents_md (AGENTS.md is the
# cross-tool convention; Claude-specific wording stays in CLAUDE.md).
_AGENTS_MD_COMMANDS_BLOCK = _render_commands_block()

_CLAUDE_MD_NEW_FILE_CONTENT = "# Project Configuration\n" + _CLAUDE_MD_COMMANDS_BLOCK
_AGENTS_MD_NEW_FILE_CONTENT = "# Project Configuration\n" + _AGENTS_MD_COMMANDS_BLOCK


def load_existing_config(project_root: Path) -> dict[str, Any]:
    """Load the existing ll-config.json for *project_root* as a dict.

    Resolves via :func:`little_loops.config.core.resolve_config_path` (so host
    state dirs like ``.codex/`` are honored), returning ``{}`` when no config is
    present or the file cannot be parsed. Shared by every ll-init write path that
    pre-populates from — and now merges with — the existing config.
    """
    from little_loops.config.core import resolve_config_path

    existing_path = resolve_config_path(project_root)
    if existing_path is None:
        return {}
    try:
        data = json.loads(existing_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def merge_with_existing(
    new_config: dict[str, Any],
    existing_config: dict[str, Any],
    force: bool,
) -> dict[str, Any]:
    """Layer *new_config* over *existing_config*, preserving unmodeled keys.

    Fixes BUG-2310: re-running ll-init rebuilt only the keys ``build_config``
    models and overwrote the file wholesale, silently destroying every other key
    the user had set (sprints, commands, documents, scratch_pad sub-config,
    history.compaction, context_monitor threshold, …).

    When ``force`` is True (or there is no existing config) *new_config* is
    returned unchanged — the documented ``--force`` "reset to template defaults"
    contract. Otherwise the ``None``-stripped *new_config* is deep-merged over
    *existing_config* so unmodeled keys survive while modeled keys take the new
    values. Neither input is mutated.
    """
    if force or not existing_config:
        return new_config
    from little_loops.config.core import deep_merge

    return deep_merge(existing_config, strip_none_leaves(new_config))


def write_config(config: dict[str, Any], ll_dir: Path, dry_run: bool = False) -> None:
    """Write ll-config.json into *ll_dir*.

    Args:
        config: Config dict produced by build_config().
        ll_dir: Path to the .ll/ directory.
        dry_run: If True, print JSON to stdout; do not write files.
    """
    if dry_run:
        print(json.dumps(config, indent=2))
        return
    ll_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ll_dir / "ll-config.json", config)


def update_gitignore(project_root: Path, dry_run: bool = False) -> bool:
    """Idempotently append ll state-file patterns to .gitignore.

    Only missing entries are appended; existing entries are never duplicated.

    Args:
        project_root: Project root directory.
        dry_run: If True, print planned changes; do not modify files.

    Returns:
        True if the file was created or modified; False if no changes needed.
    """
    gitignore_path = project_root / ".gitignore"
    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    existing_lines = set(existing.splitlines())

    missing = [e for e in _GITIGNORE_ENTRIES if e not in existing_lines]
    if not missing:
        return False

    if dry_run:
        print(f"[update] .gitignore (+{len(missing)} entries)")
        return True

    block = _GITIGNORE_COMMENT + "\n" + "\n".join(missing) + "\n"
    if existing and not existing.endswith("\n"):
        new_content = existing + "\n\n" + block
    elif existing:
        new_content = existing + "\n" + block
    else:
        new_content = block

    atomic_write(gitignore_path, new_content)
    return True


def merge_settings(
    project_root: Path,
    settings_file: str = ".claude/settings.local.json",
    extra_permissions: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Merge ll- CLI tool permissions into a Claude Code settings file.

    Idempotency sweep: removes stale ``Bash(ll-*`` and
    ``Edit(.ll/ll-continue-prompt.md)`` entries before re-appending the
    canonical list, plus any retired entry in ``_LEGACY_LL_PERMISSIONS``.

    Args:
        project_root: Project root directory.
        settings_file: Relative path to target settings JSON file.
        extra_permissions: Additional entries inserted before the trailing
            ``Edit(.ll/ll-continue-prompt.md)`` entry.
        dry_run: If True, print the target path; do not write.
    """
    target = project_root / settings_file
    if target.exists():
        try:
            data: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    perms: dict[str, Any] = data.setdefault("permissions", {})
    allow: list[str] = list(perms.get("allow", []))

    # Idempotency sweep — remove only canonical ll entries; preserve user-added Bash(ll-*) permissions.
    allow = [e for e in allow if e not in _LL_PERMISSIONS]
    # Migration sweep — drop entries this writer used to emit but no longer does.
    allow = [e for e in allow if e not in _LEGACY_LL_PERMISSIONS]
    if extra_permissions:
        allow = [e for e in allow if e not in extra_permissions]

    # Build canonical list (insert extras before trailing handoff-prompt entry)
    canonical = list(_LL_PERMISSIONS)
    if extra_permissions:
        canonical = canonical[:-1] + list(extra_permissions) + [canonical[-1]]

    allow.extend(canonical)
    perms["allow"] = allow
    data["permissions"] = perms

    if dry_run:
        print(f"[update] {settings_file}")
        if extra_permissions:
            for perm in extra_permissions:
                print(f"  + {perm}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target, data)


def make_issue_dirs(base_dir: Path, dry_run: bool = False) -> None:
    """Create the standard issue-tracking subdirectories under *base_dir*.

    Args:
        base_dir: Root issues directory (e.g., .issues/).
        dry_run: If True, print planned mkdirs; do not create directories.
    """
    if dry_run:
        for sd in _ISSUE_SUBDIRS:
            print(f"[mkdir] {base_dir / sd}")
        return
    for sd in _ISSUE_SUBDIRS:
        (base_dir / sd).mkdir(parents=True, exist_ok=True)


def make_learning_tests_dir(ll_dir: Path, dry_run: bool = False) -> bool:
    """Create .ll/learning-tests/ with a .gitkeep placeholder.

    Args:
        ll_dir: The .ll/ directory.
        dry_run: If True, print planned mkdir; do not create directories.

    Returns:
        True if the directory was created; False if it already existed.
    """
    lt_dir = ll_dir / "learning-tests"
    if lt_dir.exists():
        return False
    if dry_run:
        print(f"[mkdir] {lt_dir}")
        return True
    lt_dir.mkdir(parents=True, exist_ok=True)
    (lt_dir / ".gitkeep").touch()
    return True


def deploy_goals(ll_dir: Path, templates_dir: Path, dry_run: bool = False) -> bool:
    """Deploy the goals template to .ll/ll-goals.md (skip if already present).

    Args:
        ll_dir: The .ll/ directory.
        templates_dir: templates/ directory containing ll-goals-template.md.
        dry_run: If True, print planned write; do not copy files.

    Returns:
        True if deployed; False if already existed or source not found.
    """
    dest = ll_dir / "ll-goals.md"
    if dest.exists():
        return False
    src = templates_dir / "ll-goals-template.md"
    if not src.exists():
        print(f"  Warning: goals template source not found at {src}", file=sys.stderr)
        return False
    if dry_run:
        print(f"[write] {dest} (from {src.name})")
        return True
    ll_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, src.read_text(encoding="utf-8"))
    return True


def deploy_design_tokens(
    ll_dir: Path,
    templates_dir: Path,
    active_profile: str = "default",
    dry_run: bool = False,
) -> bool:
    """Mirror templates/design-tokens/profiles/ into .ll/design-tokens/profiles/.

    Skips silently if the destination already exists.

    Args:
        ll_dir: The .ll/ directory.
        templates_dir: templates/ directory containing design-tokens/profiles/.
        active_profile: Name of the active profile (for display only; not
            written to config by this function).
        dry_run: If True, print planned write; do not copy files.

    Returns:
        True if deployed; False if already existed or source not found.
    """
    src_profiles = templates_dir / "design-tokens" / "profiles"
    dest_profiles = ll_dir / "design-tokens" / "profiles"
    if dest_profiles.exists():
        return False
    if not src_profiles.exists():
        print(
            f"  Warning: design-token profiles source not found at {src_profiles}",
            file=sys.stderr,
        )
        return False
    if dry_run:
        print(f"[write] {dest_profiles}/ (design-token profiles)")
        return True
    shutil.copytree(src_profiles, dest_profiles)
    return True


def deploy_issue_templates(ll_dir: Path, templates_dir: Path, dry_run: bool = False) -> bool:
    """Copy bundled *-sections.json files to .ll/templates/ (skip if already present).

    Args:
        ll_dir: The .ll/ directory.
        templates_dir: templates/ directory containing *-sections.json files.
        dry_run: If True, print planned write; do not copy files.

    Returns:
        True if deployed; False if already existed or no section files found.
    """
    dest = ll_dir / "templates"
    if dest.exists():
        return False
    section_files = list(templates_dir.glob("*-sections.json"))
    if not section_files:
        print(f"Warning: no *-sections.json files found in {templates_dir}", file=sys.stderr)
        return False
    if dry_run:
        print(f"[write] {dest}/ (issue section templates)")
        return True
    dest.mkdir(parents=True, exist_ok=True)
    for f in section_files:
        shutil.copy2(f, dest / f.name)
    return True


def write_claude_md(project_root: Path, dry_run: bool = False) -> bool:
    """Append the canonical ## little-loops CLI Commands block to CLAUDE.md.

    Detection order: .claude/CLAUDE.md, then CLAUDE.md. If neither exists,
    creates .claude/CLAUDE.md. Idempotent: returns False without writing if
    the section is already present.

    Args:
        project_root: Project root directory.
        dry_run: If True, print planned action; do not write files.

    Returns:
        True if the file was created or modified; False if no changes needed.
    """
    dot_claude = project_root / ".claude" / "CLAUDE.md"
    root_claude = project_root / "CLAUDE.md"

    if dot_claude.exists():
        target = dot_claude
    elif root_claude.exists():
        target = root_claude
    else:
        target = dot_claude

    rel = str(target.relative_to(project_root))

    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _CLAUDE_MD_SECTION_MARKER in existing:
            return False
        if dry_run:
            print(f"[update] {rel} (append ## little-loops CLI Commands)")
            return True
        new_content = existing.rstrip("\n") + "\n" + _CLAUDE_MD_COMMANDS_BLOCK
        atomic_write(target, new_content)
    else:
        if dry_run:
            print(f"[write] {rel} (ll- CLI command documentation)")
            return True
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, _CLAUDE_MD_NEW_FILE_CONTENT)

    return True


# Hosts whose primary instructions file is AGENTS.md (the cross-tool
# convention). ll-init writes AGENTS.md only when one of these hosts is
# selected; Claude-specific content stays in CLAUDE.md (write_claude_md).
AGENTS_MD_HOSTS: tuple[str, ...] = ("codex", "kimi-code")


def write_agents_md(project_root: Path, dry_run: bool = False) -> bool:
    """Append the canonical ## little-loops CLI Commands block to AGENTS.md.

    AGENTS.md is the cross-tool instructions convention read by Codex, Kimi
    Code, and other non-Claude hosts (see AGENTS_MD_HOSTS). Detection order:
    .kimi-code/AGENTS.md, then AGENTS.md. If neither exists, creates root
    AGENTS.md. Idempotent: returns False without writing if the section is
    already present.

    Args:
        project_root: Project root directory.
        dry_run: If True, print planned action; do not write files.

    Returns:
        True if the file was created or modified; False if no changes needed.
    """
    dot_kimi = project_root / ".kimi-code" / "AGENTS.md"
    root_agents = project_root / "AGENTS.md"

    if dot_kimi.exists():
        target = dot_kimi
    elif root_agents.exists():
        target = root_agents
    else:
        target = root_agents

    rel = str(target.relative_to(project_root))

    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _CLAUDE_MD_SECTION_MARKER in existing:
            return False
        if dry_run:
            print(f"[update] {rel} (append ## little-loops CLI Commands)")
            return True
        new_content = existing.rstrip("\n") + "\n" + _AGENTS_MD_COMMANDS_BLOCK
        atomic_write(target, new_content)
    else:
        if dry_run:
            print(f"[write] {rel} (ll- CLI command documentation)")
            return True
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, _AGENTS_MD_NEW_FILE_CONTENT)

    return True


def _codex_template_path() -> Path:
    """Return the in-package path to the Codex adapter hooks.json template."""
    return Path(__file__).parent.parent / "hooks" / "adapters" / "codex" / "hooks.json"


def install_codex_adapter(
    project_root: Path,
    plugin_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> bool | None:
    """Write .codex/hooks.json from the in-package Codex adapter template.

    Reads ``little_loops/hooks/adapters/codex/hooks.json`` from the installed
    package, substitutes ``{{LL_PLUGIN_ROOT}}`` with the ``little_loops``
    package directory, and writes the result to ``<project_root>/.codex/hooks.json``.

    Args:
        project_root: Project root directory.
        plugin_root: Unused; kept for call-site compatibility.
        force: If True, overwrite an existing .codex/hooks.json.
        dry_run: If True, print planned write; do not modify files.

    Returns:
        True if written; False if skipped (dest already exists without --force);
        None if the source template is missing (package install corrupted).
    """
    template_path = _codex_template_path()
    dest = project_root / ".codex" / "hooks.json"

    if not template_path.exists():
        return None

    if dest.exists() and not force:
        return False

    from little_loops.init.install_check import installed_package_version

    package_root = str(Path(__file__).parent.parent)
    gen_version = installed_package_version() or ""
    rendered = (
        template_path.read_text(encoding="utf-8")
        .replace("{{LL_PLUGIN_ROOT}}", package_root)
        .replace("{{LL_GEN_VERSION}}", gen_version)
    )

    if dry_run:
        print("[write] .codex/hooks.json")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, rendered)
    return True


def _kimi_template_path() -> Path:
    """Return the in-package path to the Kimi adapter hooks.toml template."""
    return Path(__file__).parent.parent / "hooks" / "adapters" / "kimi" / "hooks.toml"


def kimi_config_path() -> Path:
    """Return the user-level Kimi Code config.toml path.

    Honors the ``KIMI_CODE_HOME`` env var (default ``~/.kimi-code``). Kimi
    has no project-local hook file, so this user-level config is the only
    hook install target.
    """
    home = os.environ.get("KIMI_CODE_HOME")
    base = Path(home) if home else Path.home() / ".kimi-code"
    return base / "config.toml"


# Markers delimiting the little-loops managed block in the kimi config.toml.
# install_kimi_adapter never modifies content outside them.
_KIMI_BLOCK_BEGIN = "# >>> little-loops kimi hooks (managed, do not edit)"
_KIMI_BLOCK_END = "# <<< little-loops kimi hooks"
_KIMI_GEN_VERSION_PREFIX = "# ll-gen-version:"


def _kimi_block_span(content: str) -> tuple[int, int] | None:
    """Return the (start, end) span of the managed block in *content*.

    ``end`` is exclusive and covers the END marker itself (not its trailing
    newline). Returns None when the block is absent or the markers are
    unpaired — the caller treats that as "not installed" and appends a
    fresh block.
    """
    begin = content.find(_KIMI_BLOCK_BEGIN)
    end = content.find(_KIMI_BLOCK_END)
    if begin == -1 or end == -1 or end <= begin:
        return None
    return begin, end + len(_KIMI_BLOCK_END)


def _kimi_block_gen_version(content: str, span: tuple[int, int]) -> str | None:
    """Return the ``ll-gen-version`` stamped inside the managed block, or None."""
    for line in content[span[0] : span[1]].splitlines():
        if line.startswith(_KIMI_GEN_VERSION_PREFIX):
            return line[len(_KIMI_GEN_VERSION_PREFIX) :].strip()
    return None


def install_kimi_adapter(
    project_root: Path,
    plugin_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> bool | None:
    """Install the Kimi hook adapter as a managed block in the user-level config.toml.

    **Note:** *project_root* is deliberately unused for the destination —
    Kimi Code has no project-local hook file (``.kimi-code/local.toml`` only
    supports ``[workspace]``), so hooks are installed into the **user-level**
    ``$KIMI_CODE_HOME/config.toml`` (default ``~/.kimi-code/config.toml``,
    honoring the ``KIMI_CODE_HOME`` env var). The parameter is kept only for
    signature parity with :func:`install_codex_adapter`.

    Reads ``little_loops/hooks/adapters/kimi/hooks.toml`` from the installed
    package, substitutes ``{{LL_PLUGIN_ROOT}}`` with the ``little_loops``
    package directory and ``{{LL_GEN_VERSION}}`` with the installed package
    version, and inserts the result as a marker-delimited managed block::

        # >>> little-loops kimi hooks (managed, do not edit)
        ...rendered [[hooks]] entries...
        # <<< little-loops kimi hooks

    Idempotent: a managed block whose ``# ll-gen-version:`` stamp matches the
    installed package is left untouched (returns False). A block stamped with
    a different version is replaced in place — this is the update path. The
    file (and parent directory) is created when missing. Content outside the
    markers is never modified.

    Args:
        project_root: Project root directory. Unused for the destination
            (hooks are user-level for kimi — see above).
        plugin_root: Unused; kept for call-site compatibility.
        force: If True, replace an existing managed block even when its gen
            version already matches.
        dry_run: If True, print planned write; do not modify files.

    Returns:
        True if written (or would be, for dry_run); False if already
        installed at the same gen version without ``force``; None if the
        source template is missing (package install corrupted).
    """
    template_path = _kimi_template_path()
    if not template_path.exists():
        return None

    from little_loops.init.install_check import installed_package_version

    package_root = str(Path(__file__).parent.parent)
    gen_version = installed_package_version() or ""
    rendered = (
        template_path.read_text(encoding="utf-8")
        .replace("{{LL_PLUGIN_ROOT}}", package_root)
        .replace("{{LL_GEN_VERSION}}", gen_version)
    )
    block = f"{_KIMI_BLOCK_BEGIN}\n{rendered.rstrip()}\n{_KIMI_BLOCK_END}\n"

    dest = kimi_config_path()
    existing = dest.read_text(encoding="utf-8") if dest.exists() else ""
    span = _kimi_block_span(existing)

    if span is not None and not force and _kimi_block_gen_version(existing, span) == gen_version:
        return False

    if dry_run:
        action = "replace little-loops managed block" if span is not None else "add little-loops managed block"
        print(f"[write] {dest} ({action})")
        return True

    if span is not None:
        remainder = existing[span[1] :]
        if remainder.startswith("\n"):
            remainder = remainder[1:]
        new_content = existing[: span[0]] + block + remainder
    elif existing and not existing.endswith("\n"):
        new_content = existing + "\n\n" + block
    elif existing:
        new_content = existing + "\n" + block
    else:
        new_content = block

    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, new_content)
    return True


def read_adapter_gen_version(project_root: Path) -> str | None:
    """Return the gen-version stamp embedded in ``.codex/hooks.json``.

    Reads the ``"_ll_gen_version"`` field written by
    :func:`install_codex_adapter`. Used by the warn-only staleness check and
    the TUI Screen-1 staleness row.

    Returns:
        The stamped version string, or None if the adapter is absent, malformed,
        or carries no (string) stamp.
    """
    dest = project_root / ".codex" / "hooks.json"
    if not dest.exists():
        return None
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    stamp = data.get("_ll_gen_version") if isinstance(data, dict) else None
    return stamp if isinstance(stamp, str) and stamp else None
