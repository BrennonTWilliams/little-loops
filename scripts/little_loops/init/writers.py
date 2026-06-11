"""File mutation helpers for headless ll-init."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from little_loops.file_utils import atomic_write, atomic_write_json

# Entries added to .gitignore by ll-init (idempotently)
_GITIGNORE_COMMENT = "# little-loops state files"
_GITIGNORE_ENTRIES: tuple[str, ...] = (
    ".auto-manage-state.json",
    ".parallel-manage-state.json",
    ".ll/ll-context-state.json",
    ".ll/ll-sync-state.json",
)

# Canonical permission entries for .claude/settings*.json (Step 10 of the skill)
_LL_PERMISSIONS: tuple[str, ...] = (
    "Bash(ll-action:*)",
    "Bash(ll-issues:*)",
    "Bash(ll-auto:*)",
    "Bash(ll-parallel:*)",
    "Bash(ll-sprint:*)",
    "Bash(ll-loop:*)",
    "Bash(ll-workflows:*)",
    "Bash(ll-messages:*)",
    "Bash(ll-history:*)",
    "Bash(ll-history-context:*)",
    "Bash(ll-deps:*)",
    "Bash(ll-sync:*)",
    "Bash(ll-verify-docs:*)",
    "Bash(ll-verify-skills:*)",
    "Bash(ll-check-links:*)",
    "Bash(ll-gitignore:*)",
    "Bash(ll-create-extension:*)",
    "Bash(ll-learning-tests:*)",
    "Bash(ll-logs:*)",
    "Bash(ll-session:*)",
    "Bash(ll-doctor:*)",
    "Bash(ll-ctx-stats:*)",
    "Bash(ll-adapt-skills-for-codex:*)",
    "Bash(ll-adapt-agents-for-codex:*)",
    "Bash(ll-harness:*)",
    "Write(.ll/ll-continue-prompt.md)",
)

_ISSUE_SUBDIRS: tuple[str, ...] = (
    "bugs",
    "features",
    "enhancements",
    "completed",
    "deferred",
)

# Sentinel string used to detect whether the ll section already exists in CLAUDE.md
_CLAUDE_MD_SECTION_MARKER = "## little-loops"

# Canonical CLI Commands block appended/created by write_claude_md (Step 11 of the skill)
_CLAUDE_MD_COMMANDS_BLOCK = """\

## little-loops CLI Commands

- `ll-action` - Invoke ll skills as one-shot commands with JSON-structured output
- `ll-harness` - One-shot runner evaluation (skill, cmd, mcp, prompt, dsl) with exit-code and semantic criteria
- `ll-auto` - Process all backlog issues sequentially in priority order
- `ll-parallel` - Process issues concurrently using isolated git worktrees
- `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
- `ll-loop` - Execute FSM-based automation loops
- `ll-workflows` - Identify multi-step workflow patterns from user message history
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
- `ll-history-context` - Render a `## Historical Context` block for an issue from `.ll/history.db`
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-verify-skills` - Check that no SKILL.md exceeds 500 lines
- `ll-check-links` - Check markdown documentation for broken links
- `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, set-status, anchor-sweep, fingerprint, epic-progress, decisions)
- `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files
- `ll-create-extension` - Scaffold a new little-loops extension project
- `ll-generate-schemas` - Regenerate JSON Schema files for all LLEvent types (maintainer tool)
- `ll-learning-tests` - Query and manage the learning test registry (check/list/mark-stale)
- `ll-logs` - Discover, extract, and analyze (sequences, scan-failures) ll-relevant log entries from Claude project logs
- `ll-doctor` - Check host CLI capability support for little-loops features
- `ll-ctx-stats` - Show context-window analytics for the current project (per-tool byte vs. context savings)
- `ll-adapt-skills-for-codex` - Add Codex Skills API frontmatter to skills and bridge commands for Codex discovery
- `ll-adapt-agents-for-codex` - Generate `.codex/agents/*.toml` from `agents/*.md` for Codex agent-select support

Install: `pip install -e "./scripts[dev]"`
"""

_CLAUDE_MD_NEW_FILE_CONTENT = "# Project Configuration\n" + _CLAUDE_MD_COMMANDS_BLOCK


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
    ``Write(.ll/ll-continue-prompt.md)`` entries before re-appending the
    canonical list.

    Args:
        project_root: Project root directory.
        settings_file: Relative path to target settings JSON file.
        extra_permissions: Additional entries inserted before the trailing
            ``Write(.ll/ll-continue-prompt.md)`` entry.
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

    # Idempotency sweep
    allow = [e for e in allow if not e.startswith("Bash(ll-")]
    allow = [e for e in allow if e != "Write(.ll/ll-continue-prompt.md)"]
    if extra_permissions:
        allow = [e for e in allow if e not in extra_permissions]

    # Build canonical list (insert extras before trailing Write entry)
    canonical = list(_LL_PERMISSIONS)
    if extra_permissions:
        canonical = canonical[:-1] + list(extra_permissions) + [canonical[-1]]

    allow.extend(canonical)
    perms["allow"] = allow
    data["permissions"] = perms

    if dry_run:
        print(f"[update] {settings_file}")
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
        return False
    if dry_run:
        print(f"[write] {dest_profiles}/ (design-token profiles)")
        return True
    shutil.copytree(src_profiles, dest_profiles)
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


def install_codex_adapter(
    project_root: Path,
    plugin_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Write .codex/hooks.json from the Codex adapter template.

    Reads ``hooks/adapters/codex/hooks.json`` (plugin-relative), substitutes
    the ``{{LL_PLUGIN_ROOT}}`` placeholder with the absolute *plugin_root*
    path, and writes the result to ``<project_root>/.codex/hooks.json``.

    Args:
        project_root: Project root directory.
        plugin_root: Absolute path to the little-loops plugin root.
        force: If True, overwrite an existing .codex/hooks.json.
        dry_run: If True, print planned write; do not modify files.

    Returns:
        True if written; False if skipped (already exists without --force, or
        template not found).
    """
    template_path = plugin_root / "hooks" / "adapters" / "codex" / "hooks.json"
    dest = project_root / ".codex" / "hooks.json"

    if not template_path.exists():
        return False

    if dest.exists() and not force:
        return False

    rendered = template_path.read_text(encoding="utf-8").replace(
        "{{LL_PLUGIN_ROOT}}", str(plugin_root)
    )

    if dry_run:
        print("[write] .codex/hooks.json")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, rendered)
    return True
