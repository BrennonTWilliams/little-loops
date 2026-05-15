"""ll-generate-skill-descriptions: Auto-generate concise skill descriptions via Claude CLI.

For each skills/*/SKILL.md that does NOT have disable-model-invocation: true,
extract trigger keywords and body excerpt, prompt Claude (haiku) to produce a
description ≤100 characters, and optionally write it back to the frontmatter.

Dry-run by default. Use --apply to write back.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

__all__ = ["main_generate_skill_descriptions"]

_MAX_DESC_LEN = 100
_BODY_EXCERPT_CHARS = 500


def _find_plugin_root() -> Path:
    from little_loops.skill_expander import _find_plugin_root as _fpr

    return _fpr()


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_keys, body_text) from a SKILL.md string."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    body = text[end + 3 :].lstrip("\n")
    fm: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


def _extract_trigger_keywords(description: str) -> str:
    """Pull the 'Trigger keywords:' line from a description field value."""
    for line in description.splitlines():
        if line.strip().lower().startswith("trigger keywords"):
            return line.strip()
    return ""


def _build_prompt(skill_name: str, trigger_keywords: str, body_excerpt: str) -> str:
    return (
        f"Generate a single-line skill description for the '{skill_name}' skill.\n"
        f"Rules:\n"
        f"- Maximum {_MAX_DESC_LEN} characters total\n"
        f"- No bullet points or newlines\n"
        f"- Start with 'Use when' or a clear trigger phrase\n"
        f"- Include the most important trigger keywords\n"
        f"\nTrigger keywords: {trigger_keywords or '(none)'}\n"
        f"Skill body excerpt:\n{body_excerpt[:_BODY_EXCERPT_CHARS]}\n"
        f"\nRespond with ONLY the description text, nothing else."
    )


def _write_description_to_frontmatter(skill_md: Path, new_desc: str) -> None:
    """Replace the description: field in SKILL.md frontmatter with new_desc."""
    text = skill_md.read_text()
    if not text.startswith("---"):
        return
    end = text.find("---", 3)
    if end == -1:
        return
    fm_block = text[3:end]
    after = text[end:]

    # Replace existing description line (single-line only)
    new_fm_block = re.sub(
        r"^description:.*$",
        f"description: {new_desc}",
        fm_block,
        flags=re.MULTILINE,
    )
    skill_md.write_text("---" + new_fm_block + after)


def _process_skills(skills_dir: Path, apply: bool, quiet: bool) -> tuple[int, int, int]:
    """Process all skills; return (processed, skipped, errors)."""
    from little_loops.subprocess_utils import run_claude_command

    processed = skipped = errors = 0

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name
        try:
            text = skill_md.read_text()
        except OSError as exc:
            if not quiet:
                print(f"  ERROR  {skill_name}: cannot read file: {exc}", file=sys.stderr)
            errors += 1
            continue

        fm, body = _parse_frontmatter(text)

        if fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1"):
            if not quiet:
                print(f"  SKIP   {skill_name} (disable-model-invocation: true)")
            skipped += 1
            continue

        trigger_keywords = _extract_trigger_keywords(fm.get("description", ""))
        prompt = _build_prompt(skill_name, trigger_keywords, body)

        result = run_claude_command(
            command=prompt,
            timeout=60,
        )

        if result.returncode != 0:
            if not quiet:
                print(
                    f"  ERROR  {skill_name}: Claude returned exit {result.returncode}",
                    file=sys.stderr,
                )
            errors += 1
            continue

        new_desc = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""

        if len(new_desc) > _MAX_DESC_LEN:
            new_desc = new_desc[:_MAX_DESC_LEN]

        if not new_desc:
            if not quiet:
                print(f"  ERROR  {skill_name}: empty description from Claude", file=sys.stderr)
            errors += 1
            continue

        if apply:
            _write_description_to_frontmatter(skill_md, new_desc)
            if not quiet:
                print(f"  APPLY  {skill_name}: {new_desc}")
        else:
            if not quiet:
                print(f"  DRY    {skill_name}: {new_desc}")

        processed += 1

    return processed, skipped, errors


def main_generate_skill_descriptions() -> int:
    """Entry point for ll-generate-skill-descriptions CLI."""
    parser = argparse.ArgumentParser(
        prog="ll-generate-skill-descriptions",
        description=(
            "Auto-generate ≤100-char skill descriptions via Claude CLI. "
            "Dry-run by default; use --apply to write back to SKILL.md frontmatter."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ll-generate-skill-descriptions               # Dry-run: preview generated descriptions
  ll-generate-skill-descriptions --apply       # Write descriptions back to SKILL.md files
  ll-generate-skill-descriptions --quiet       # Suppress per-skill output
""",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write generated descriptions back to SKILL.md frontmatter (default: dry-run only)",
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

    if not skills_dir.exists():
        print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)
        return 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    if not args.quiet:
        print(f"ll-generate-skill-descriptions [{mode}]")
        print(f"Skills dir: {skills_dir}")
        print()

    processed, skipped, errors = _process_skills(skills_dir, args.apply, args.quiet)

    print(f"\nDone: {processed} generated, {skipped} skipped, {errors} errors")
    return 0 if errors == 0 else 1
