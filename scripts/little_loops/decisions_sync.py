"""Sync decisions log active rules to .ll/ll.local.md."""

from __future__ import annotations

from pathlib import Path

from little_loops.decisions import _DEFAULT_LOG_PATH, RuleEntry, list_entries, resolve_active
from little_loops.file_utils import atomic_write


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else Path.cwd() / _DEFAULT_LOG_PATH


def sync_to_local_md(path: Path | None = None) -> None:
    """Write active required rules to ## Active Rules in ll.local.md.

    `path` is the decisions YAML path (e.g. .ll/decisions.yaml).
    ll.local.md is resolved as path.parent / "ll.local.md".
    """
    decisions_path = _resolve_path(path)
    ll_local_path = decisions_path.parent / "ll.local.md"

    rules = [
        e
        for e in list_entries(decisions_path, type="rule")
        if getattr(e, "enforcement", None) == "required"
    ]
    active_rules = resolve_active(rules)

    rules_block = "\n".join(f"- {r.rule}" for r in active_rules if isinstance(r, RuleEntry))
    section = f"## Active Rules\n\n{rules_block}\n"

    content = ll_local_path.read_text(encoding="utf-8") if ll_local_path.exists() else ""
    if "## Active Rules" in content:
        idx = content.rfind("## Active Rules\n")
        end = content.find("\n##", idx + 1)
        content = content[:idx] + section + (content[end:] if end != -1 else "")
    else:
        content += f"\n\n{section}"
    atomic_write(ll_local_path, content)
