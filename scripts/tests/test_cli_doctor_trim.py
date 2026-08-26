"""Tests for `ll-doctor --trim`'s context-residency verdicts."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from little_loops.cli.doctor_trim import (
    _split_h2_sections,
    collect_trim_report,
)


def _write_skill(root: Path, name: str, description: str, *, disabled: bool = False) -> None:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"description: {description}"]
    if disabled:
        lines.append("disable-model-invocation: true")
    lines += ["---", "", "# Body", "", "Body text that loads on demand only."]
    (skill_dir / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_command(root: Path, name: str, description: str) -> None:
    commands_dir = root / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / f"{name}.md").write_text(
        f"---\ndescription: {description}\n---\n\n# {name}\n", encoding="utf-8"
    )


def _write_history_db(root: Path, events: list[tuple[str, str, str]]) -> Path:
    """Create `.ll/history.db` with (ts, session_id, skill_name) skill_events rows."""
    db_path = root / ".ll" / "history.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE skill_events (ts TEXT, session_id TEXT, skill_name TEXT)")
        conn.executemany("INSERT INTO skill_events VALUES (?, ?, ?)", events)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _now_iso(days_ago: int = 0) -> str:
    return (datetime.now().astimezone() - timedelta(days=days_ago)).isoformat()


def _by_name(report, name: str):
    matches = [c for c in report.components if c.name == name]
    assert matches, f"{name} not in report: {[c.name for c in report.components]}"
    return matches[0]


class TestSectionSplitting:
    """`_split_h2_sections()` must account for every token in the file."""

    def test_splits_at_h2_boundaries(self) -> None:
        text = "# Title\n\nIntro.\n\n## One\n\nA\n\n## Two\n\nB\n"
        sections = _split_h2_sections(text)
        assert [h for h, _ in sections] == ["(preamble)", "One", "Two"]

    def test_frontmatter_is_stripped_before_splitting(self) -> None:
        text = "---\nkey: value\n---\n\n## Only\n\nBody\n"
        sections = _split_h2_sections(text)
        assert [h for h, _ in sections] == ["Only"]

    def test_file_without_h2_is_one_section(self) -> None:
        sections = _split_h2_sections("# Title\n\nJust prose, no H2 at all.\n")
        assert [h for h, _ in sections] == ["(whole file)"]

    def test_empty_file_yields_no_sections(self) -> None:
        assert _split_h2_sections("") == []

    def test_section_bodies_cover_whole_file(self) -> None:
        """No content may be dropped — costs must sum to the real resident cost."""
        text = "# Title\n\nIntro.\n\n## One\n\nA\n\n## Two\n\nB\n"
        assert "".join(body for _, body in _split_h2_sections(text)) == text


class TestUsageVerdicts:
    """Catalog entries are scored against recorded `skill_events` invocations."""

    def test_never_invoked_entry_is_trimmed(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "unused", "A" * 80)
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "something-else")])

        component = _by_name(collect_trim_report(tmp_path), "unused")
        assert component.verdict == "trim"
        assert component.invocations == 0
        assert component.resident_tokens == 20

    def test_frequently_invoked_entry_is_kept(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "hot", "A" * 80)
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "hot") for _ in range(10)])

        assert _by_name(collect_trim_report(tmp_path), "hot").verdict == "keep"

    def test_rarely_invoked_costly_entry_is_reviewed(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "rare", "A" * 200)
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "rare")])

        component = _by_name(collect_trim_report(tmp_path), "rare")
        assert component.verdict == "review"
        assert component.invocations == 1

    def test_rarely_invoked_cheap_entry_is_kept(self, tmp_path: Path) -> None:
        """Reclaiming a handful of tokens is not worth a review cycle."""
        _write_skill(tmp_path, "cheap", "Tiny.")
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "cheap")])

        assert _by_name(collect_trim_report(tmp_path), "cheap").verdict == "keep"

    def test_invocations_outside_window_do_not_count(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "stale", "A" * 80)
        _write_history_db(tmp_path, [(_now_iso(400), "s1", "stale")])

        component = _by_name(collect_trim_report(tmp_path, window_days=90), "stale")
        assert component.verdict == "trim"
        assert component.invocations == 0

    def test_ll_prefix_is_normalized_on_both_sides(self, tmp_path: Path) -> None:
        """`skill_events` records names unprefixed; the catalog dir may not be."""
        _write_skill(tmp_path, "ll-prefixed", "A" * 80)
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "prefixed") for _ in range(5)])

        assert _by_name(collect_trim_report(tmp_path), "prefixed").verdict == "keep"

    def test_commands_are_scored_alongside_skills(self, tmp_path: Path) -> None:
        _write_command(tmp_path, "unused-cmd", "A" * 80)
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "other")])

        component = _by_name(collect_trim_report(tmp_path), "unused-cmd")
        assert component.kind == "command"
        assert component.verdict == "trim"

    def test_model_invocation_disabled_entry_is_excluded(self, tmp_path: Path) -> None:
        """An opted-out skill costs no listing tokens, so it is out of scope."""
        _write_skill(tmp_path, "hidden", "A" * 80, disabled=True)
        _write_history_db(tmp_path, [])

        assert not [c for c in collect_trim_report(tmp_path).components if c.name == "hidden"]


class TestAbsentTelemetry:
    """No telemetry must not be mistaken for evidence of disuse."""

    def test_missing_db_scores_nothing_as_trim(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "unknown", "A" * 200)

        report = collect_trim_report(tmp_path)
        assert report.usage_available is False
        assert not [c for c in report.components if c.verdict == "trim"]
        assert _by_name(report, "unknown").invocations is None

    def test_db_without_skill_events_table_scores_nothing_as_trim(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "unknown", "A" * 200)
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(str(db_path)).close()

        report = collect_trim_report(tmp_path)
        assert report.usage_available is False
        assert not [c for c in report.components if c.verdict == "trim"]

    def test_empty_skill_events_table_does_score(self, tmp_path: Path) -> None:
        """A present-but-empty table is real evidence: nothing ran in the window."""
        _write_skill(tmp_path, "unused", "A" * 200)
        _write_history_db(tmp_path, [])

        report = collect_trim_report(tmp_path)
        assert report.usage_available is True
        assert _by_name(report, "unused").verdict == "trim"


class TestMemorySections:
    """Memory files are cost-reported, never auto-verdicted as trim."""

    def test_large_section_is_flagged_for_review(self, tmp_path: Path) -> None:
        claude_md = tmp_path / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text(f"# Title\n\n## Big\n\n{'word ' * 400}\n", encoding="utf-8")

        component = _by_name(collect_trim_report(tmp_path), ".claude/CLAUDE.md § Big")
        assert component.verdict == "review"
        assert component.kind == "memory"
        assert component.invocations is None

    def test_small_section_is_kept(self, tmp_path: Path) -> None:
        claude_md = tmp_path / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text("# Title\n\n## Small\n\nOne short line.\n", encoding="utf-8")

        assert (
            _by_name(collect_trim_report(tmp_path), ".claude/CLAUDE.md § Small").verdict == "keep"
        )

    def test_memory_never_verdicts_trim(self, tmp_path: Path) -> None:
        """Section cost is decidable; 'would the model work it out?' is not."""
        claude_md = tmp_path / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True)
        claude_md.write_text(f"## Huge\n\n{'word ' * 2000}\n", encoding="utf-8")
        _write_history_db(tmp_path, [])

        memory = [c for c in collect_trim_report(tmp_path).components if c.kind == "memory"]
        assert memory
        assert all(c.verdict != "trim" for c in memory)

    def test_absent_memory_file_is_skipped(self, tmp_path: Path) -> None:
        assert not [c for c in collect_trim_report(tmp_path).components if c.kind == "memory"]


class TestReportAggregates:
    """Report-level totals and ordering."""

    def test_reclaimable_counts_only_trim_verdicts(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "unused", "A" * 80)
        _write_skill(tmp_path, "hot", "A" * 80)
        _write_history_db(tmp_path, [(_now_iso(1), "s1", "hot") for _ in range(10)])

        report = collect_trim_report(tmp_path)
        assert report.reclaimable_tokens == 20
        assert report.total_resident_tokens == 40

    def test_trim_sorts_before_review_before_keep(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "unused", "A" * 80)
        _write_skill(tmp_path, "rare", "A" * 200)
        _write_skill(tmp_path, "hot", "A" * 80)
        _write_history_db(
            tmp_path,
            [(_now_iso(1), "s1", "rare")] + [(_now_iso(1), "s1", "hot") for _ in range(10)],
        )

        verdicts = [c.verdict for c in collect_trim_report(tmp_path).components]
        assert verdicts == sorted(verdicts, key=lambda v: {"trim": 0, "review": 1, "keep": 2}[v])

    def test_sessions_observed_counts_distinct_sessions(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "hot", "A" * 80)
        _write_history_db(
            tmp_path,
            [(_now_iso(1), "s1", "hot"), (_now_iso(1), "s1", "hot"), (_now_iso(1), "s2", "hot")],
        )

        assert collect_trim_report(tmp_path).sessions_observed == 2

    def test_empty_project_yields_empty_report(self, tmp_path: Path) -> None:
        report = collect_trim_report(tmp_path)
        assert report.components == ()
        assert report.reclaimable_tokens == 0


class TestExitCodeIsolation:
    """`--trim` is advisory: it must never fail the run."""

    def test_trim_findings_do_not_affect_exit_code(self, monkeypatch, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from little_loops.cli.doctor import main_doctor

        # Mock resolve_host at the host_runner module (its origin) so the local
        # re-import in cli/doctor.py picks up the fake. Provide describe_capabilities
        # because main_doctor uses it for capability inspection.
        fake_runner = MagicMock()
        fake_runner.describe_capabilities.return_value = MagicMock()
        monkeypatch.setattr("little_loops.host_runner.resolve_host", lambda: fake_runner)

        monkeypatch.chdir(tmp_path)
        _write_skill(tmp_path, "unused", "A" * 200)
        _write_history_db(tmp_path, [])

        without_trim = main_doctor([])
        with_trim = main_doctor(["--trim"])
        assert with_trim == without_trim
