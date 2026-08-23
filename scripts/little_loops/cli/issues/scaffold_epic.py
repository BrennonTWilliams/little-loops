"""ll-issues scaffold-epic: EPIC + pre-wired child stubs, atomically (FEAT-2947).

Composes :func:`little_loops.cli.issues.create.create_issue`: assemble every
file's content in memory first, then write them all; on any failure, unlink
every path this call created and re-raise (D5) — every file it touches is one
it just created, so ``Path.unlink()`` is a complete undo.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.issues.create import (
    _VALID_TYPES,
    CreatedIssue,
    IssueSpec,
    _append_child_to_epic_children,
    _category_key_for_type,
    _render_issue_content,
    _stage,
)
from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig


@dataclass
class ChildSpec:
    """One child issue to scaffold alongside the EPIC."""

    type: str
    title: str
    priority: str
    summary: str = ""


def scaffold_epic(
    config: BRConfig,
    title: str,
    children: list[ChildSpec],
    priority: str = "P2",
    stage: bool = False,
    now: datetime | None = None,
) -> tuple[CreatedIssue, list[CreatedIssue]]:
    """Create an EPIC and its pre-wired child stubs, atomically.

    Args:
        config: Project configuration.
        title: EPIC title.
        children: Child issues to scaffold, each wired with `parent: EPIC-N`
            and a bullet in the EPIC's ``## Children`` section.
        priority: Priority applied to the EPIC and, unless overridden per
            child, inherited by each child.
        stage: If True, `git add` every created file in one call on success.
        now: Injectable current time for tests.

    Returns:
        The created EPIC and its created children, in the order given.

    Raises:
        ValueError: if any child's type has no configured category.
    """
    from little_loops.file_utils import acquire_lock
    from little_loops.issue_parser import (
        get_next_issue_number,
        id_alloc_highwater_path,
        slugify,
        write_id_alloc_highwater,
    )
    from little_loops.paths import resolve_main_worktree_root

    for child in children:
        if child.type not in _VALID_TYPES:
            raise ValueError(f"Unknown issue type: {child.type!r}")

    now = now or datetime.now(UTC)
    # BUG-3303: relocate the id-alloc lock to the main checkout when running
    # inside a linked worktree, so allocation is serialized across trees.
    main_root = resolve_main_worktree_root(config.project_root)
    lock_base = main_root if main_root is not None else config.project_root
    lock_path = lock_base / config.issues.base_dir / ".id-alloc.lock"
    highwater_path = id_alloc_highwater_path(config)

    written: list[tuple[str, Path]] = []  # (issue_id, Path)
    try:
        with acquire_lock(lock_path, timeout=10.0):
            epic_category = _category_key_for_type(config, "EPIC")
            epic_dir = config.get_issue_dir(epic_category)
            epic_dir.mkdir(parents=True, exist_ok=True)
            epic_num = get_next_issue_number(config)
            epic_id = f"EPIC-{epic_num:03d}"
            epic_slug = slugify(title)
            epic_path = epic_dir / f"{priority}-EPIC-{epic_num:03d}-{epic_slug}.md"
            if epic_path.exists():
                raise FileExistsError(str(epic_path))

            epic_spec = IssueSpec(type="EPIC", title=title, priority=priority, variant="full")
            epic_content = _render_issue_content(config, epic_spec, epic_id, now)

            child_results: list[CreatedIssue] = []
            child_contents: list[str] = []
            child_paths: list[Path] = []
            next_num = epic_num + 1
            for child in children:
                category_key = _category_key_for_type(config, child.type)
                child_dir = config.get_issue_dir(category_key)
                child_dir.mkdir(parents=True, exist_ok=True)
                child_slug = slugify(child.title)
                child_id = f"{child.type}-{next_num:03d}"
                child_path = (
                    child_dir / f"{child.priority}-{child.type}-{next_num:03d}-{child_slug}.md"
                )
                if child_path.exists():
                    raise FileExistsError(str(child_path))
                child_spec = IssueSpec(
                    type=child.type,
                    title=child.title,
                    priority=child.priority,
                    body=child.summary or None,
                    parent=epic_id,
                    variant="minimal",
                )
                child_content = _render_issue_content(config, child_spec, child_id, now)
                updated = _append_child_to_epic_children(epic_content, child_id, child.title)
                if updated is not None:
                    epic_content = updated

                child_results.append(CreatedIssue(id=child_id, path=child_path))
                child_contents.append(child_content)
                child_paths.append(child_path)
                next_num += 1

            with open(epic_path, "x", encoding="utf-8") as f:
                f.write(epic_content)
            written.append((epic_id, epic_path))

            for child_path, child_content in zip(child_paths, child_contents, strict=True):
                with open(child_path, "x", encoding="utf-8") as f:
                    f.write(child_content)
                written.append(("", child_path))

            write_id_alloc_highwater(highwater_path, next_num - 1)
    except Exception:
        for _, path in written:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise

    epic_created = CreatedIssue(id=epic_id, path=epic_path)
    if stage:
        all_paths = [str(epic_path)] + [str(c.path) for c in child_results]
        _stage(all_paths, config.project_root)

    return epic_created, child_results


def add_scaffold_epic_parser(subs: argparse._SubParsersAction) -> None:
    """Register the ``scaffold-epic`` sub-command parser."""
    from little_loops.cli_args import VALID_PRIORITIES, add_config_arg

    se = subs.add_parser(
        "scaffold-epic",
        help="Create an EPIC and pre-wired child stubs atomically",
    )
    se.set_defaults(command="scaffold-epic")
    se.add_argument("--title", required=True, help="EPIC title")
    se.add_argument(
        "--children",
        required=True,
        help="JSON array of {type,title,priority,summary} objects, or @file to read from",
    )
    se.add_argument(
        "--priority",
        "-p",
        choices=sorted(VALID_PRIORITIES),
        default="P2",
        help="EPIC priority (default: P2)",
    )
    se.add_argument(
        "--stage",
        action="store_true",
        default=False,
        help="git add every created file in one call on success",
    )
    se.add_argument("--json", "-j", action="store_true", default=False, dest="json_output")
    add_config_arg(se)


def cmd_scaffold_epic(config: BRConfig, args: argparse.Namespace) -> int:
    """Execute the ``scaffold-epic`` sub-command.

    Args:
        config: Project configuration.
        args: Parsed arguments (.title, .children, .priority, .stage, .json_output).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    raw = args.children
    if raw.startswith("@"):
        file_arg = raw[1:]
        text = sys.stdin.read() if file_arg == "-" else open(file_arg, encoding="utf-8").read()
    else:
        text = raw

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"Error: --children is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, list) or not payload:
        print("Error: --children must be a non-empty JSON array", file=sys.stderr)
        return 1

    try:
        children = [
            ChildSpec(
                type=item["type"],
                title=item["title"],
                priority=item.get("priority", args.priority),
                summary=item.get("summary", ""),
            )
            for item in payload
        ]
    except (KeyError, TypeError) as exc:
        print(f"Error: each child needs 'type' and 'title': {exc}", file=sys.stderr)
        return 1

    try:
        epic, kids = scaffold_epic(
            config,
            title=args.title,
            children=children,
            priority=args.priority,
            stage=args.stage,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print_json({"epic": epic.to_dict(), "children": [c.to_dict() for c in kids]})
    else:
        print(f"{epic.id} {epic.path}")
        for c in kids:
            print(f"  {c.id} {c.path}")
    return 0
