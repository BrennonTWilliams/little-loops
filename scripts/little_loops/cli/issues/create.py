"""ll-issues create: atomic issue-file creation (FEAT-2947).

Replaces the prose ID-allocation / slugify / template-assembly dance that
every issue-creating skill (``capture-issue``, ``scope-epic``) previously
restated. See ``.issues/features/P2-FEAT-2947-*.md`` for design rationale
(D1-D5) — notably why frontmatter is built via
``little_loops.frontmatter.update_frontmatter("", {...})`` rather than
``issue_template.assemble_issue_markdown``'s hand-built frontmatter loop.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_VALID_TYPES = ("BUG", "FEAT", "ENH", "EPIC")

# Matches the "## Children" heading in an EPIC's body (Program Design).
_CHILDREN_HEADING = "## Children"


@dataclass
class IssueSpec:
    """Input to :func:`create_issue`."""

    type: str
    title: str
    priority: str = "P2"
    body: str | None = None
    parent: str | None = None
    labels: list[str] = field(default_factory=list)
    stage: bool = False
    variant: str = "minimal"


@dataclass
class CreatedIssue:
    """Output of :func:`create_issue`."""

    id: str
    path: Path

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "path": str(self.path)}


def _category_key_for_type(config: BRConfig, issue_type: str) -> str:
    """Return the config category key (e.g. ``"features"``) for a TYPE prefix."""
    for key, cat in config.issues.categories.items():
        if cat.prefix == issue_type:
            return key
    raise ValueError(f"No configured category for issue type {issue_type!r}")


def _stage(paths: list[str], repo_root: Path) -> bool:
    """``git add -- <paths>``, unstaging on failure. Never ``git add -A`` (BUG-2421)."""
    try:
        result = subprocess.run(
            ["git", "add", "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False
    if result.returncode != 0:
        subprocess.run(
            ["git", "reset", "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return False
    return True


def _append_child_to_epic_children(content: str, child_id: str, child_title: str) -> str | None:
    """Append a child bullet to an EPIC's ``## Children`` section.

    Returns the updated content, or None if no ``## Children`` heading is
    found (create() then skips this wiring silently — only EPIC parents have
    this section).
    """
    lines = content.splitlines()
    heading_idx = None
    for i, line in enumerate(lines):
        if line.strip() == _CHILDREN_HEADING:
            heading_idx = i
            break
    if heading_idx is None:
        return None

    insert_at = len(lines)
    for j in range(heading_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            insert_at = j
            break

    # Trim trailing blank lines within the section before inserting, then
    # keep exactly one blank line after the new bullet.
    while insert_at > heading_idx + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    bullet = f"- **{child_id}** — {child_title} (open)"
    new_lines = lines[:insert_at] + [bullet, ""] + lines[insert_at:]
    return "\n".join(new_lines)


def _render_issue_content(
    config: BRConfig,
    spec: IssueSpec,
    issue_id: str,
    now: datetime,
) -> str:
    from little_loops.frontmatter import update_frontmatter
    from little_loops.issue_template import assemble_issue_body, load_issue_sections

    frontmatter: dict[str, object] = {
        "id": issue_id,
        "type": spec.type,
        "title": spec.title,
        "priority": spec.priority,
        "status": "open",
        "discovered_by": "ll-issues-create",
        "discovered_date": now.strftime("%Y-%m-%d"),
        "captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if spec.parent:
        frontmatter["parent"] = spec.parent
    if spec.labels:
        frontmatter["labels"] = list(spec.labels)

    sections_data = load_issue_sections(spec.type)
    content = {"Summary": spec.body} if spec.body else {}
    body = assemble_issue_body(
        sections_data=sections_data,
        issue_type=spec.type,
        variant=spec.variant,
        issue_id=issue_id,
        title=spec.title,
        content=content,
    )
    return update_frontmatter("", frontmatter) + "\n" + body


#: Stand-in for the issue ID in a dry-run render. Deliberately not a *predicted* ID:
#: allocation happens inside :func:`create_issue`'s lock hold, so any ID produced before
#: apply is a guess with no binding force (FEAT-3149 Decision 1).
ID_PLACEHOLDER = "<assigned-at-apply>"


def render_issue_preview(
    config: BRConfig, spec: IssueSpec, now: datetime | None = None
) -> dict[str, str]:
    """Describe the file :func:`create_issue` *would* write, without writing it.

    Added for FEAT-3149's dry-run-by-default guard. Per Decision 1 the return value
    carries **no issue ID**, not even a predicted one — the ID does not exist until
    apply allocates it under the lock, and a host that echoed a predicted ID would be
    wrong exactly when it matters (when something else allocated concurrently).

    Args:
        config: Project configuration.
        spec: The issue that would be created.
        now: Injectable current time for tests; defaults to ``datetime.now(UTC)``.

    Returns:
        The resolved ``type``, ``priority``, ``slug``, target ``directory``, and the
        ``rendered_body`` with :data:`ID_PLACEHOLDER` standing in for the ID.

    Raises:
        ValueError: if ``spec.type`` is not a valid issue type or has no configured
            category — the same failures :func:`create_issue` raises, so a dry-run
            surfaces them before apply rather than after.
    """
    from little_loops.issue_parser import slugify

    if spec.type not in _VALID_TYPES:
        raise ValueError(f"Unknown issue type: {spec.type!r}")

    now = now or datetime.now(UTC)
    category_key = _category_key_for_type(config, spec.type)
    return {
        "type": spec.type,
        "priority": spec.priority,
        "slug": slugify(spec.title),
        "directory": str(config.get_issue_dir(category_key)),
        "rendered_body": _render_issue_content(config, spec, ID_PLACEHOLDER, now),
    }


def create_issue(config: BRConfig, spec: IssueSpec, now: datetime | None = None) -> CreatedIssue:
    """Atomically allocate an ID and write a new issue file.

    Under a single ``acquire_lock`` hold: allocates the next globally unique
    issue number (retrying on a filesystem collision), slugs the title,
    selects the type directory, and writes frontmatter + template body via
    exclusive-create (``open(path, "x")``) so a racer that bypasses the lock
    still fails loudly rather than clobbering (D3).

    If ``spec.parent`` is set, writes `parent:` in the child's frontmatter
    (always) and appends a bullet to the parent's ``## Children`` section if
    one exists (silently skipped otherwise — non-EPIC parents have no such
    section).

    Args:
        config: Project configuration.
        spec: Issue contents and creation options.
        now: Injectable current time for tests; defaults to
            ``datetime.now(UTC)``.

    Returns:
        The created issue's id and path.

    Raises:
        ValueError: if ``spec.type`` has no configured category.
        FileExistsError: if 5 collision retries are exhausted.
    """
    from little_loops.file_utils import acquire_lock
    from little_loops.issue_parser import get_next_issue_number, slugify

    if spec.type not in _VALID_TYPES:
        raise ValueError(f"Unknown issue type: {spec.type!r}")

    now = now or datetime.now(UTC)
    issues_dir = config.project_root / config.issues.base_dir
    category_key = _category_key_for_type(config, spec.type)
    type_dir = config.get_issue_dir(category_key)
    type_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(spec.title)

    lock_path = issues_dir / ".id-alloc.lock"
    path: Path | None = None
    issue_id = ""
    last_error: FileExistsError | None = None
    with acquire_lock(lock_path, timeout=10.0):
        for _ in range(5):
            num = get_next_issue_number(config)
            issue_id = f"{spec.type}-{num:03d}"
            filename = f"{spec.priority}-{spec.type}-{num:03d}-{slug}.md"
            candidate = type_dir / filename
            content = _render_issue_content(config, spec, issue_id, now)
            try:
                with open(candidate, "x", encoding="utf-8") as f:
                    f.write(content)
                path = candidate
                break
            except FileExistsError as exc:
                last_error = exc
                continue
        if path is None:
            assert last_error is not None
            raise last_error

    created = CreatedIssue(id=issue_id, path=path)
    staged_paths = [str(path)]

    if spec.parent:
        from little_loops.cli.issues.show import _resolve_issue_id

        parent_path = _resolve_issue_id(config, spec.parent)
        if parent_path is not None:
            parent_content = parent_path.read_text(encoding="utf-8")
            updated = _append_child_to_epic_children(parent_content, issue_id, spec.title)
            if updated is not None:
                parent_path.write_text(updated, encoding="utf-8")
                staged_paths.append(str(parent_path))

    if spec.stage:
        _stage(staged_paths, config.project_root)

    return created


def add_create_parser(subs: argparse._SubParsersAction) -> None:
    """Register the ``create`` sub-command parser."""
    from little_loops.cli_args import VALID_PRIORITIES, add_config_arg

    cr = subs.add_parser(
        "create",
        help="Atomically allocate an ID and write a new issue file",
    )
    cr.set_defaults(command="create")
    cr.add_argument("--type", "-T", required=True, choices=_VALID_TYPES, help="Issue type")
    cr.add_argument("--title", required=True, help="Issue title")
    cr.add_argument(
        "--priority",
        "-p",
        choices=sorted(VALID_PRIORITIES),
        default="P2",
        help="Issue priority (default: P2)",
    )
    cr.add_argument(
        "--body-file",
        metavar="PATH",
        default=None,
        dest="body_file",
        help="Path to file with Summary body content, or '-' for stdin",
    )
    cr.add_argument("--parent", default=None, help="Parent EPIC ID to wire (both directions)")
    cr.add_argument(
        "--labels",
        default=None,
        help="Comma-separated labels",
    )
    cr.add_argument(
        "--variant",
        choices=("minimal", "full", "legacy"),
        default="minimal",
        help="Template variant (default: minimal)",
    )
    cr.add_argument(
        "--stage",
        action="store_true",
        default=False,
        help="git add the created (and any rewired parent) file(s)",
    )
    cr.add_argument("--json", "-j", action="store_true", default=False, dest="json_output")
    add_config_arg(cr)


def cmd_create(config: BRConfig, args: argparse.Namespace) -> int:
    """Execute the ``create`` sub-command.

    Args:
        config: Project configuration.
        args: Parsed arguments (.type, .title, .priority, .body_file, .parent,
            .labels, .variant, .stage, .json_output).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    body: str | None = None
    if args.body_file:
        if args.body_file == "-":
            body = sys.stdin.read()
        else:
            body_path = Path(args.body_file)
            if not body_path.exists():
                print(f"Error: --body-file not found: {args.body_file}", file=sys.stderr)
                return 1
            body = body_path.read_text(encoding="utf-8")

    labels = (
        [label.strip() for label in args.labels.split(",") if label.strip()] if args.labels else []
    )

    spec = IssueSpec(
        type=args.type,
        title=args.title,
        priority=args.priority,
        body=body,
        parent=args.parent,
        labels=labels,
        stage=args.stage,
        variant=args.variant,
    )
    try:
        created = create_issue(config, spec)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print_json(created.to_dict())
    else:
        print(f"{created.id} {created.path}")
    return 0
