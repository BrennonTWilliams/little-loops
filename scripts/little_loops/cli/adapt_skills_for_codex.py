"""ll-adapt-skills-for-codex: Add Codex Skills API frontmatter to all ll skills.

For each skills/*/SKILL.md, inserts `name:` (directory slug) and
`metadata.short-description:` (first line of existing description, ≤80 chars).
Also creates `agents/openai.yaml` per the Codex Skills API spec.

Additionally bridges `commands/*.md` to the Skills API by synthesizing a
`skills/ll-<stem>/SKILL.md` wrapper + `agents/openai.yaml` for each command,
so Codex CLI users can invoke `/ll:*` slash commands via the same discovery
path as adapted skills (FEAT-1493).

Dry-run by default. Use --apply to write changes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_adapt_skills_for_codex"]

_MAX_SHORT_DESC = 80
_FM_CLOSE_RE = re.compile(r"\n---\s*\n")


def _find_plugin_root() -> Path:
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


def _extract_short_desc(text: str) -> str:
    """Parse SKILL.md and return first non-empty description line, ≤80 chars.

    Uses yaml.safe_load for reading only — never writes back.
    Handles both single-line and block-scalar description fields.
    """
    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    fm_raw = text[3:end]
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        return ""
    desc = fm.get("description", "") or ""
    if not isinstance(desc, str):
        return ""
    for line in desc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_MAX_SHORT_DESC]
    return ""


def _insert_fields(content: str, name: str, short_desc: str) -> tuple[str, bool]:
    """Insert name: and metadata.short-description: into SKILL.md frontmatter.

    Uses targeted string manipulation — no yaml roundtrip — to preserve
    existing frontmatter formatting (block scalars, special chars, etc.).
    Returns (new_content, changed).
    """
    if not content.startswith("---\n"):
        return content, False

    m = _FM_CLOSE_RE.search(content[3:])
    if not m:
        return content, False

    # fm_text: lines between opening --- and closing ---\n (no trailing newline)
    fm_text = content[4 : 3 + m.start()]
    after = content[3 + m.start() :]  # starts with "\n---\n..."

    changed = False

    # Insert name: if absent
    if not re.search(r"^name\s*:", fm_text, re.MULTILINE):
        fm_text = f"name: {name}\n" + fm_text
        changed = True

    # Insert metadata.short-description: if absent
    if "short-description:" not in fm_text:
        if re.search(r"^metadata\s*:", fm_text, re.MULTILINE):
            fm_text = re.sub(
                r"^(metadata\s*:.*)$",
                lambda mtch: mtch.group(0) + f"\n  short-description: {short_desc}",
                fm_text,
                flags=re.MULTILINE,
                count=1,
            )
        else:
            fm_text += f"\nmetadata:\n  short-description: {short_desc}"
        changed = True

    return f"---\n{fm_text}{after}", changed


def _title_case(slug: str) -> str:
    """Convert skill slug to display name (e.g. 'capture-issue' → 'Capture Issue')."""
    return " ".join(word.capitalize() for word in slug.replace("-", " ").split())


def _make_openai_yaml(display_name: str, short_desc: str) -> str:
    """Generate agents/openai.yaml content for the Codex Skills API."""
    return f'interface:\n  display_name: "{display_name}"\n  short_description: "{short_desc}"\n'


def _process_skills(skills_dir: Path, apply: bool, quiet: bool) -> tuple[int, int, int]:
    """Process all skills; return (adapted, skipped, errors)."""
    adapted = skipped = errors = 0

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name
        try:
            text = skill_md.read_text()
        except OSError as exc:
            if not quiet:
                print(f"  ERROR  {skill_name}: cannot read: {exc}", file=sys.stderr)
            errors += 1
            continue

        short_desc = _extract_short_desc(text)
        if not short_desc:
            if not quiet:
                print(f"  SKIP   {skill_name}: no description found")
            skipped += 1
            continue

        new_text, skill_changed = _insert_fields(text, skill_name, short_desc)
        openai_yaml = skill_md.parent / "agents" / "openai.yaml"
        yaml_exists = openai_yaml.exists()

        if not skill_changed and yaml_exists:
            if not quiet:
                print(f"  SKIP   {skill_name}: already adapted")
            skipped += 1
            continue

        if apply:
            if skill_changed:
                skill_md.write_text(new_text)
            if not yaml_exists:
                openai_yaml.parent.mkdir(exist_ok=True)
                display_name = _title_case(skill_name)
                openai_yaml.write_text(_make_openai_yaml(display_name, short_desc))
            if not quiet:
                print(f"  APPLY  {skill_name}: {short_desc[:50]}")
        else:
            if not quiet:
                print(f"  DRY    {skill_name}: {short_desc[:50]}")

        adapted += 1

    return adapted, skipped, errors


def _read_command_frontmatter(text: str) -> dict | None:
    """Parse a command markdown file's YAML frontmatter. Returns None on failure."""
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm


def _synthesized_skill_md(stem: str, description: str) -> str:
    """Build a minimal synthesized SKILL.md for a bridged command.

    Writes the whole frontmatter block as a fresh document — never reuses
    `_insert_fields`, which is for editing existing frontmatter.
    Multi-line descriptions are emitted as YAML block scalars (`|`) so the
    resulting frontmatter parses cleanly with yaml.safe_load.
    """
    short_desc = ""
    for line in description.splitlines():
        stripped = line.strip()
        if stripped:
            short_desc = stripped[:_MAX_SHORT_DESC]
            break

    if "\n" in description.strip():
        # Emit as a literal block scalar to preserve multi-line content
        indented = "\n".join(f"  {line}" if line else "" for line in description.splitlines())
        desc_block = f"description: |\n{indented}"
    else:
        desc_block = f"description: {description.strip()}"

    return (
        f"---\n"
        f"name: ll-{stem}\n"
        f"{desc_block}\n"
        f"metadata:\n"
        f"  short-description: {short_desc}\n"
        f"---\n"
        f"\n"
        f"# {_title_case(stem)}\n"
        f"\n"
        f"Bridged from `commands/{stem}.md` for Codex Skills API discovery.\n"
        f"See the source command file for the full prompt body.\n"
    )


def _process_commands(
    commands_dir: Path, skills_dir: Path, apply: bool, quiet: bool
) -> tuple[int, int, int]:
    """Bridge commands/*.md into skills/ll-<stem>/ as Codex-discoverable skills.

    Returns (adapted, skipped, errors). Each command produces:
      skills/ll-<stem>/SKILL.md           (synthesized wrapper)
      skills/ll-<stem>/agents/openai.yaml (Codex Skills API contract)

    Skips commands carrying `disable-model-invocation: true` in their frontmatter,
    mirroring the contract of generate_skill_descriptions.py.
    """
    adapted = skipped = errors = 0

    if not commands_dir.exists():
        return adapted, skipped, errors

    for cmd_md in sorted(commands_dir.glob("*.md")):
        stem = cmd_md.stem
        try:
            text = cmd_md.read_text()
        except OSError as exc:
            if not quiet:
                print(f"  ERROR  ll-{stem}: cannot read: {exc}", file=sys.stderr)
            errors += 1
            continue

        fm = _read_command_frontmatter(text)
        if fm is None:
            if not quiet:
                print(f"  SKIP   ll-{stem}: no parseable frontmatter")
            skipped += 1
            continue

        # Skip commands explicitly opting out of model invocation
        # (string-lowered check, matches generate_skill_descriptions.py:107)
        dmi = fm.get("disable-model-invocation")
        if isinstance(dmi, str):
            dmi = dmi.strip().lower() in {"true", "yes", "1"}
        if dmi:
            if not quiet:
                print(f"  SKIP   ll-{stem}: disable-model-invocation: true")
            skipped += 1
            continue

        description = fm.get("description", "") or ""
        if not isinstance(description, str) or not description.strip():
            if not quiet:
                print(f"  SKIP   ll-{stem}: no description in frontmatter")
            skipped += 1
            continue

        short_desc = _extract_short_desc(text)
        if not short_desc:
            if not quiet:
                print(f"  SKIP   ll-{stem}: empty short description")
            skipped += 1
            continue

        out_dir = skills_dir / f"ll-{stem}"
        out_skill_md = out_dir / "SKILL.md"
        out_openai_yaml = out_dir / "agents" / "openai.yaml"

        skill_md_exists = out_skill_md.exists()
        yaml_exists = out_openai_yaml.exists()

        if skill_md_exists and yaml_exists:
            if not quiet:
                print(f"  SKIP   ll-{stem}: already adapted")
            skipped += 1
            continue

        if apply:
            out_dir.mkdir(parents=True, exist_ok=True)
            if not skill_md_exists:
                out_skill_md.write_text(_synthesized_skill_md(stem, description))
            if not yaml_exists:
                out_openai_yaml.parent.mkdir(exist_ok=True)
                display_name = _title_case(stem)
                out_openai_yaml.write_text(_make_openai_yaml(display_name, short_desc))
            if not quiet:
                print(f"  APPLY  ll-{stem}: {short_desc[:50]}")
        else:
            if not quiet:
                print(f"  DRY    ll-{stem}: {short_desc[:50]}")

        adapted += 1

    return adapted, skipped, errors


def main_adapt_skills_for_codex() -> int:
    """Entry point for ll-adapt-skills-for-codex CLI."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-adapt-skills-for-codex", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-adapt-skills-for-codex",
            description=(
                "Add Codex Skills API frontmatter to ll skill SKILL.md files and "
                "bridge commands/*.md into skills/ll-<name>/ entries for Codex CLI. "
                "Dry-run by default; use --apply to write changes."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-adapt-skills-for-codex            # Dry-run: preview proposed changes
  ll-adapt-skills-for-codex --apply    # Write skill frontmatter + bridge commands
  ll-adapt-skills-for-codex --quiet    # Suppress per-entry output
""",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes to SKILL.md files and create agents/openai.yaml (default: dry-run)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=False,
            help="Suppress per-skill output; only print final summary",
        )

        args = parser.parse_args()

        plugin_root = _find_plugin_root()
        skills_dir = plugin_root / "skills"
        commands_dir = plugin_root / "commands"

        if not skills_dir.exists():
            print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)
            return 1

        mode = "APPLY" if args.apply else "DRY-RUN"
        if not args.quiet:
            print(f"ll-adapt-skills-for-codex [{mode}]")
            print(f"Skills dir: {skills_dir}")
            print(f"Commands dir: {commands_dir}")
            print()

        s_adapted, s_skipped, s_errors = _process_skills(skills_dir, args.apply, args.quiet)
        c_adapted, c_skipped, c_errors = _process_commands(
            commands_dir, skills_dir, args.apply, args.quiet
        )

        adapted = s_adapted + c_adapted
        skipped = s_skipped + c_skipped
        errors = s_errors + c_errors

        print(f"\nDone: {adapted} adapted, {skipped} skipped, {errors} errors")
        return 0 if errors == 0 else 1
