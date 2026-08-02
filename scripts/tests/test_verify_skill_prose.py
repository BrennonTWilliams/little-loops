"""Tests for ll-verify-skill-prose — algorithm-as-prose lint gate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.verify_skill_prose import (
    PROSE_MARKERS,
    _lint_file,
    main_verify_skill_prose,
    scan_prose,
)

# EPIC-2938's frozen baseline: real skills/*/SKILL.md + commands/*.md hits as of
# ENH-2953's landing (re-counted 2026-08-02 via a live `ll-verify-skill-prose`
# run — do not trust a number cited in issue prose without re-running it).
# Every one of these is future work for a sibling child of EPIC-2938, not
# suppressed here — this test only guards against *growth*.
BASELINE_COUNT = 17


def _make_tree(tmp_path: Path) -> Path:
    (tmp_path / "skills").mkdir()
    (tmp_path / "commands").mkdir()
    return tmp_path


def _write_skill(base_dir: Path, name: str, body: str) -> Path:
    skill_dir = base_dir / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(f"---\nname: {name}\n---\n\n{body}\n", encoding="utf-8")
    return skill_file


def _write_command(base_dir: Path, name: str, body: str) -> Path:
    commands_dir = base_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    cmd_file = commands_dir / f"{name}.md"
    cmd_file.write_text(body + "\n", encoding="utf-8")
    return cmd_file


class TestMarkerFixtures:
    """One positive + one negative fixture per curated marker."""

    def test_jaccard_word_overlap_positive(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", "score = |words_A ∩ words_B| / |words_A ∪ words_B|")
        findings = _lint_file(f, PROSE_MARKERS)
        assert any(x.marker == "jaccard_word_overlap" for x in findings)

    def test_jaccard_word_overlap_negative(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", "Merge the two lists and dedupe by ID.")
        findings = _lint_file(f, PROSE_MARKERS)
        assert not any(x.marker == "jaccard_word_overlap" for x in findings)

    def test_inline_stopword_list_positive(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path,
            "x",
            "Exclude `the`, `and`, `for`, `with`, `from` from the word set.",
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert any(x.marker == "inline_stopword_list" for x in findings)

    def test_inline_stopword_list_negative(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", "Set `status: done` on the issue file.")
        findings = _lint_file(f, PROSE_MARKERS)
        assert not any(x.marker == "inline_stopword_list" for x in findings)

    def test_session_jsonl_scan_positive(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path,
            "x",
            "Scan `~/.claude/projects/<project>/` for session jsonl files matching the issue ID.",
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert any(x.marker == "session_jsonl_scan" for x in findings)

    def test_session_jsonl_scan_negative(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path, "x", "Auto memory lives under ~/.claude/projects/<project>/memory/."
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert not any(x.marker == "session_jsonl_scan" for x in findings)

    def test_inline_python_computation_positive(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path, "x", 'RESULT=$(echo "$json" | python3 -c "import json,sys; ...")'
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert any(x.marker == "inline_python_computation" for x in findings)

    def test_inline_python_computation_negative(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", "Run `ll-issues show ISSUE-ID --json`.")
        findings = _lint_file(f, PROSE_MARKERS)
        assert not any(x.marker == "inline_python_computation" for x in findings)

    def test_git_mv_glob_loop_positive(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", 'git mv "[category]/P[old]-[rest-of-name].md" \\')
        findings = _lint_file(f, PROSE_MARKERS)
        assert any(x.marker == "git_mv_glob_loop" for x in findings)

    def test_git_mv_glob_loop_negative(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", "Use `git mv` to preserve file history.")
        findings = _lint_file(f, PROSE_MARKERS)
        assert not any(x.marker == "git_mv_glob_loop" for x in findings)

    def test_union_find_cluster_merge_positive(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path, "x", "Merge overlapping issue pairs using union-find (or equivalent)."
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert any(x.marker == "union_find_cluster_merge" for x in findings)

    def test_union_find_cluster_merge_negative(self, tmp_path: Path) -> None:
        f = _write_command(tmp_path, "x", "Assign the issue to its parent EPIC.")
        findings = _lint_file(f, PROSE_MARKERS)
        assert not any(x.marker == "union_find_cluster_merge" for x in findings)


class TestSuppression:
    """`<!-- ll-prose-ok: reason -->` on the preceding line suppresses a match."""

    def test_suppressed_line_is_excluded(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path,
            "x",
            "<!-- ll-prose-ok: intentional example for documentation -->\n"
            'git mv "[category]/P[old]-[rest-of-name].md" \\',
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert findings == []

    def test_unsuppressed_line_still_found(self, tmp_path: Path) -> None:
        f = _write_command(
            tmp_path,
            "x",
            'Some other comment\ngit mv "[category]/P[old]-[rest-of-name].md" \\',
        )
        findings = _lint_file(f, PROSE_MARKERS)
        assert findings != []


class TestScanProse:
    """scan_prose() walks skills/*/SKILL.md and commands/*.md."""

    def test_clean_tree_returns_empty(self, tmp_path: Path) -> None:
        base = _make_tree(tmp_path)
        _write_skill(base, "clean-skill", "Nothing to see here.")
        _write_command(base, "clean-command", "Nothing to see here.")
        assert scan_prose(base) == []

    def test_finds_hit_in_skill_and_command(self, tmp_path: Path) -> None:
        base = _make_tree(tmp_path)
        _write_skill(base, "s", "Merge via union-find (or equivalent).")
        _write_command(base, "c", "Merge via union-find (or equivalent).")
        findings = scan_prose(base)
        assert len(findings) == 2

    def test_skips_disable_model_invocation_skill(self, tmp_path: Path) -> None:
        base = _make_tree(tmp_path)
        skill_dir = base / "skills" / "disabled-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: disabled-skill\ndisable-model-invocation: true\n---\n\n"
            "Merge via union-find (or equivalent).\n",
            encoding="utf-8",
        )
        assert scan_prose(base) == []

    def test_does_not_scan_companion_files(self, tmp_path: Path) -> None:
        base = _make_tree(tmp_path)
        skill_dir = base / "skills" / "s"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: s\n---\n\nClean.\n", encoding="utf-8")
        (skill_dir / "companion.md").write_text(
            "Merge via union-find (or equivalent).\n", encoding="utf-8"
        )
        assert scan_prose(base) == []


class TestMainEntryPoint:
    """CLI-level behavior of main_verify_skill_prose()."""

    def test_exits_zero_on_clean_tree(self, tmp_path: Path) -> None:
        base = _make_tree(tmp_path)
        _write_skill(base, "clean-skill", "Nothing to see here.")
        with patch("sys.argv", ["ll-verify-skill-prose", "-C", str(base)]):
            assert main_verify_skill_prose(["-C", str(base)]) == 0

    def test_exits_one_on_finding(self, tmp_path: Path) -> None:
        base = _make_tree(tmp_path)
        _write_command(base, "c", "Merge via union-find (or equivalent).")
        with patch("sys.argv", ["ll-verify-skill-prose", "-C", str(base)]):
            assert main_verify_skill_prose(["-C", str(base)]) == 1

    def test_json_output_reports_findings(self, tmp_path: Path, capsys) -> None:
        base = _make_tree(tmp_path)
        _write_command(base, "c", "Merge via union-find (or equivalent).")
        with patch("sys.argv", ["ll-verify-skill-prose"]):
            main_verify_skill_prose(["-C", str(base), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is False
        assert data["count"] == 1
        assert data["findings"][0]["marker"] == "union_find_cluster_merge"
        assert data["findings"][0]["line"] == 1


class TestBaselineNeverIncreases:
    """Guards EPIC-2938's core invariant against silent regression."""

    def test_current_tree_baseline_does_not_grow(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        findings = scan_prose(repo_root)
        assert len(findings) <= BASELINE_COUNT, (
            f"algorithm-as-prose findings grew from {BASELINE_COUNT} to {len(findings)}: "
            + ", ".join(f"{f.path}:{f.line} [{f.marker}]" for f in findings)
        )
