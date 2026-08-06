"""Shared config-summary extraction for ll-init completion surfaces.

One extraction function feeds both renderers (audit rec-11): the headless
paths print the rows through ``cli.output.status_block``, and the TUI renders
the same rows into its rich Panel — the "what just happened" report is no
longer implemented twice in two rendering engines (audit U-2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def summary_rows(
    config: dict[str, Any],
    project_root: Path,
    include_features: bool = True,
) -> list[tuple[str, str]]:
    """Extract (key, value) summary rows from a built/merged init config.

    Rows reflect the config's settled values only; surfaces add their own
    path-specific rows (hosts, settings target, CLAUDE.md disposition).
    Pass ``include_features=False`` when the surface renders a richer
    features row of its own (the TUI derives it from the user's checkbox
    selection rather than the config).
    """
    proj = config.get("project", {})
    rows: list[tuple[str, str]] = [("Project", proj.get("name") or project_root.name)]
    if proj.get("src_dir"):
        rows.append(("Source dir", proj["src_dir"]))
    for field, label in (
        ("test_cmd", "Test"),
        ("lint_cmd", "Lint"),
        ("type_cmd", "Type-check"),
        ("format_cmd", "Format"),
    ):
        val = proj.get(field)
        if val:
            rows.append((label, str(val)))

    if include_features:
        features: list[str] = []
        # parallel carries no enabled key: section presence is the enablement
        # signal (matches tui._features_from_existing_config).
        if config.get("parallel") is not None:
            features.append("parallel")
        for section, label in (
            ("product", "product"),
            ("documents", "documents"),
            ("design_tokens", "design tokens"),
            ("learning_tests", "learning tests"),
            ("analytics", "analytics"),
            ("context_monitor", "context monitor"),
            ("sync", "GitHub sync"),
            ("decisions", "decisions"),
            ("scratch_pad", "scratch pad"),
            ("session_capture", "session capture"),
            ("prompt_optimization", "prompt optimization"),
        ):
            if config.get(section, {}).get("enabled"):
                features.append(label)
        cmds = config.get("commands", {})
        if cmds.get("confidence_gate", {}).get("enabled"):
            features.append("confidence gate")
        if cmds.get("tdd_mode"):
            features.append("TDD mode")
        if features:
            rows.append(("Features", ", ".join(features)))

    max_workers = config.get("parallel", {}).get("max_workers")
    if max_workers:
        rows.append(("Workers", str(max_workers)))

    dt = config.get("design_tokens", {})
    if dt.get("enabled") and dt.get("active"):
        rows.append(("Token profile", dt["active"]))

    doc_cats = config.get("documents", {}).get("categories", {})
    if doc_cats:
        rows.append(("Documents", f"{len(doc_cats)} categories detected"))

    wt_files = config.get("parallel", {}).get("worktree_copy_files", [])
    if wt_files:
        rows.append(("Worktree files", ", ".join(wt_files)))

    sd_enabled = config.get("history", {}).get("session_digest", {}).get("enabled", True)
    rows.append(("Session digest", "on" if sd_enabled else "off"))

    rd = config.get("loops", {}).get("run_defaults", {})
    rd_parts: list[str] = []
    if rd.get("clear"):
        rd_parts.append("--clear")
    if rd.get("show_diagrams"):
        rd_parts.append(f"--show-diagrams {rd['show_diagrams']}")
    rows.append(("Loop defaults", " ".join(rd_parts) if rd_parts else "none"))

    return rows
