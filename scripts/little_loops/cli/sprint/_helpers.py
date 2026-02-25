"""Shared helpers for ll-sprint CLI subcommands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.dependency_graph import DependencyGraph, WaveContentionNote
    from little_loops.logger import Logger


def _render_execution_plan(
    waves: list[list[Any]],
    dep_graph: DependencyGraph,
    contention_notes: list[WaveContentionNote | None] | None = None,
) -> str:
    """Render execution plan with wave groupings.

    Args:
        waves: List of execution waves from get_execution_waves()
        dep_graph: DependencyGraph for looking up blockers
        contention_notes: Optional per-wave contention annotations from
            refine_waves_for_contention(). Same length as waves.

    Returns:
        Formatted string showing wave structure
    """
    if not waves:
        return ""

    # Build logical wave groups: consecutive sub-waves from the same
    # parent_wave_index are grouped together.
    logical_waves: list[list[int]] = []  # each entry is list of indices into waves
    notes = contention_notes or [None] * len(waves)

    for idx in range(len(waves)):
        note = notes[idx] if idx < len(notes) else None
        if note is not None:
            # Check if this belongs to the same parent as the previous group
            if logical_waves and notes[logical_waves[-1][0]] is not None:
                prev_note = notes[logical_waves[-1][0]]
                if prev_note and prev_note.parent_wave_index == note.parent_wave_index:
                    logical_waves[-1].append(idx)
                    continue
            logical_waves.append([idx])
        else:
            logical_waves.append([idx])

    total_issues = sum(len(wave) for wave in waves)
    num_logical = len(logical_waves)
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 70)
    wave_word = "wave" if num_logical == 1 else "waves"
    lines.append(f"EXECUTION PLAN ({total_issues} issues, {num_logical} {wave_word})")
    lines.append("=" * 70)

    for logical_idx, group in enumerate(logical_waves):
        lines.append("")
        logical_num = logical_idx + 1
        group_issues = [issue for widx in group for issue in waves[widx]]
        group_count = len(group_issues)
        is_contention = len(group) > 1

        if is_contention:
            # Multiple sub-waves from overlap splitting
            lines.append(
                f"Wave {logical_num} ({group_count} issues, serialized \u2014 file overlap):"
            )
            step = 0
            for widx in group:
                for issue in waves[widx]:
                    step += 1
                    lines.append(f"  Step {step}/{group_count}:")

                    # Truncate title if too long
                    title = issue.title
                    if len(title) > 45:
                        title = title[:42] + "..."

                    lines.append(
                        f"    \u2514\u2500\u2500 {issue.issue_id}: {title} ({issue.priority})"
                    )

                    # Show blockers for this issue
                    blockers = dep_graph.blocked_by.get(issue.issue_id, set())
                    if blockers:
                        blockers_str = ", ".join(sorted(blockers))
                        lines.append(f"        blocked by: {blockers_str}")

            # Show contended files once at the end of the group
            first_note = notes[group[0]]
            if first_note:
                paths_str = ", ".join(first_note.contended_paths[:2])
                extra = len(first_note.contended_paths) - 2
                if extra > 0:
                    paths_str += f" +{extra} more"
                lines.append(f"  Contended files: {paths_str}")
        else:
            # Single wave (no overlap splitting)
            widx = group[0]
            wave = waves[widx]

            if logical_num == 1:
                parallel_note = "(parallel)" if len(wave) > 1 else ""
            else:
                parallel_note = f"(after Wave {logical_num - 1})"
                if len(wave) > 1:
                    parallel_note += " parallel"
            lines.append(f"Wave {logical_num} {parallel_note}:".strip())

            for i, issue in enumerate(wave):
                is_last = i == len(wave) - 1
                prefix = "  \u2514\u2500\u2500 " if is_last else "  \u251c\u2500\u2500 "

                # Truncate title if too long
                title = issue.title
                if len(title) > 45:
                    title = title[:42] + "..."

                lines.append(f"{prefix}{issue.issue_id}: {title} ({issue.priority})")

                # Show blockers for this issue
                blockers = dep_graph.blocked_by.get(issue.issue_id, set())
                if blockers:
                    blocker_prefix = (
                        "      \u2514\u2500\u2500 " if is_last else "  \u2502   \u2514\u2500\u2500 "
                    )
                    blockers_str = ", ".join(sorted(blockers))
                    lines.append(f"{blocker_prefix}blocked by: {blockers_str}")

    return "\n".join(lines)


def _build_issue_contents(issue_infos: list) -> dict[str, str]:
    """Build issue_id -> file content mapping for dependency analysis."""
    return {info.issue_id: info.path.read_text() for info in issue_infos if info.path.exists()}


def _render_dependency_analysis(
    report: Any,
    logger: Logger,
    issue_to_wave: dict[str, int] | None = None,
) -> None:
    """Display dependency analysis results in CLI format.

    Args:
        report: DependencyReport from analyze_dependencies()
        logger: Logger instance
        issue_to_wave: Optional mapping of issue_id -> wave index. When
            provided, proposals where the target already runs before the
            source in wave ordering are counted as "already handled".
    """
    if not report.proposals and not report.validation.has_issues:
        return

    logger.header("Dependency Analysis", char="-", width=60)

    if report.proposals:
        # Partition proposals into novel vs already-satisfied
        novel: list[Any] = []
        satisfied_count = 0
        for p in report.proposals:
            if issue_to_wave is not None:
                target_wave = issue_to_wave.get(p.target_id)
                source_wave = issue_to_wave.get(p.source_id)
                if (
                    target_wave is not None
                    and source_wave is not None
                    and target_wave < source_wave
                ):
                    satisfied_count += 1
                    continue
            novel.append(p)

        if novel:
            logger.warning(f"Found {len(novel)} potential missing dependency(ies):")
            for p in novel:
                if p.conflict_score >= 0.7:
                    conflict = "HIGH"
                elif p.conflict_score >= 0.4:
                    conflict = "MEDIUM"
                else:
                    conflict = "LOW"
                logger.warning(
                    f"  {p.source_id} may depend on {p.target_id} "
                    f"({conflict} conflict, {p.confidence:.0%} confidence)"
                )
                if p.overlapping_files:
                    files = ", ".join(p.overlapping_files[:3])
                    if len(p.overlapping_files) > 3:
                        files += " and more"
                    logger.info(f"    Shared files: {files}")

        if satisfied_count > 0:
            total = len(report.proposals)
            if not novel:
                dep_word = "dependency" if total == 1 else "dependencies"
                logger.info(f"All {total} potential {dep_word} already handled by wave ordering.")
            else:
                logger.info(f"({satisfied_count} additional already handled by wave ordering)")

    if report.validation.has_issues:
        v = report.validation
        if v.broken_refs:
            for issue_id, ref_id in v.broken_refs:
                logger.warning(f"  {issue_id}: references nonexistent {ref_id}")
        if v.stale_completed_refs:
            for issue_id, ref_id in v.stale_completed_refs:
                logger.warning(f"  {issue_id}: blocked by {ref_id} (completed)")
        if v.missing_backlinks:
            for issue_id, ref_id in v.missing_backlinks:
                logger.warning(f"  {issue_id} blocked by {ref_id}, but {ref_id} missing backlink")

    logger.info("Run /ll:map-dependencies to apply discovered dependencies")
    print()  # blank line separator
