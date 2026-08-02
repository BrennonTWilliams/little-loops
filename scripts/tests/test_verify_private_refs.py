"""Tests for ll-verify-private-refs, plus the repo-wide CI gate.

The gate at the bottom (:class:`TestRepoGate`) is the pytest transport for this
check — this project has no hosted CI, so `python -m pytest scripts/tests/` is
the enforced boundary (see .claude/CLAUDE.md § Testing & CI Policy).

Fixtures here deliberately contain literal machine paths, which is why this file
is on the checker's own exclusion list.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from little_loops.cli.verify_private_refs import (
    BASELINE_PATH,
    LOCAL_PATTERNS_PATH,
    STRUCTURAL_RULES,
    counts_by_file,
    load_baseline,
    load_local_rules,
    main_verify_private_refs,
    regressions,
    scan_file,
    scan_paths,
    staged_added_lines,
    write_baseline,
)

# Assembled rather than written literally so this constant does not trip a
# naive grep over the test suite.
_HOME = "/" + "Users" + "/alice"


class TestStructuralRules:
    """Built-in, name-free rules."""

    def test_absolute_home_path_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "issue.md"
        f.write_text(f"See {_HOME}/Projects/secret-app/main.py for the call site.\n")
        findings = scan_file(f, STRUCTURAL_RULES)
        assert len(findings) == 1
        assert findings[0].rule == "abs_user_path"
        assert findings[0].line == 1

    def test_linux_home_path_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Run from /home/bob/work/thing/ and retry.\n")
        assert len(scan_file(f, STRUCTURAL_RULES)) == 1

    def test_windows_home_path_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(r"Path: C:\Users\carol\code\app" + "\n")
        assert len(scan_file(f, STRUCTURAL_RULES)) == 1

    def test_host_session_path_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "log.md"
        f.write_text("Trace in ~/.claude/projects/-Users-alice-work/abc.jsonl\n")
        findings = scan_file(f, STRUCTURAL_RULES)
        assert [x.rule for x in findings] == ["host_session_path"]

    def test_repo_relative_path_not_flagged(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.md"
        f.write_text("See scripts/little_loops/fsm/executor.py:120 for the guard.\n")
        assert scan_file(f, STRUCTURAL_RULES) == []

    def test_generic_tilde_claude_path_not_flagged(self, tmp_path: Path) -> None:
        """~/.claude/settings.json is ordinary documentation, not a leak."""
        f = tmp_path / "docs.md"
        f.write_text("Edit ~/.claude/settings.json to add the permission.\n")
        assert scan_file(f, STRUCTURAL_RULES) == []

    def test_binary_file_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "blob.bin"
        f.write_bytes(b"\x00\x01" + _HOME.encode() + b"/x")
        assert scan_file(f, STRUCTURAL_RULES) == []

    @pytest.mark.parametrize(
        "rel",
        [".ll/ll-continue-prompt.md", ".ll/private-refs.local.txt"],
    )
    def test_machine_local_scratch_files_excluded(self, tmp_path: Path, rel: str) -> None:
        """These are gitignored by ll-init and expected to hold absolute paths."""
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"See {_HOME}/Projects/secret-app/main.py for the call site.\n")
        assert scan_paths(tmp_path, [Path(rel)], STRUCTURAL_RULES) == []


class TestSuppression:
    def test_same_line_marker_suppresses(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(f"Path {_HOME}/x <!-- ll-private-ok: illustrative example -->\n")
        assert scan_file(f, STRUCTURAL_RULES) == []

    def test_preceding_line_marker_suppresses(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(f"<!-- ll-private-ok: reviewed -->\nPath {_HOME}/x\n")
        assert scan_file(f, STRUCTURAL_RULES) == []

    def test_hash_comment_marker_suppresses(self, tmp_path: Path) -> None:
        f = tmp_path / "x.py"
        f.write_text(f'# ll-private-ok: fixture\nHOME = "{_HOME}/x"\n')
        assert scan_file(f, STRUCTURAL_RULES) == []

    def test_marker_two_lines_up_does_not_suppress(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(f"<!-- ll-private-ok: r -->\nfiller\nPath {_HOME}/x\n")
        assert len(scan_file(f, STRUCTURAL_RULES)) == 1


class TestRedaction:
    def test_excerpt_does_not_reproduce_the_path(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(f"trace at {_HOME}/AIProjects/private-thing/run.log here\n")
        (finding,) = scan_file(f, STRUCTURAL_RULES)
        assert "alice" not in finding.excerpt
        assert "<redacted>" in finding.excerpt

    def test_trailing_session_slug_also_redacted(self, tmp_path: Path) -> None:
        """A second reference in the trailing context must not survive."""
        f = tmp_path / "x.md"
        f.write_text(f"log `{_HOME}/.claude/projects/-Users-alice-work/a.jsonl`\n")
        findings = scan_file(f, STRUCTURAL_RULES)
        assert findings
        for finding in findings:
            assert "alice" not in finding.excerpt


class TestLocalRules:
    def test_absent_file_yields_no_rules(self, tmp_path: Path) -> None:
        assert load_local_rules(tmp_path) == ()

    def test_patterns_loaded_and_matched(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / LOCAL_PATTERNS_PATH).write_text("# comment\n\n\\bsecret-proj\\b\n")
        rules = load_local_rules(tmp_path)
        assert len(rules) == 1
        f = tmp_path / "x.md"
        f.write_text("Observed in the secret-proj repo.\n")
        findings = scan_file(f, STRUCTURAL_RULES + rules)
        assert [x.rule for x in findings] == ["private_name"]

    def test_invalid_regex_skipped_not_fatal(self, tmp_path: Path, capsys) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / LOCAL_PATTERNS_PATH).write_text("[unclosed\n\\bok-name\\b\n")
        rules = load_local_rules(tmp_path)
        assert len(rules) == 1, "a broken line must not discard the valid ones"
        assert "invalid regex" in capsys.readouterr().err


class TestBaseline:
    def test_roundtrip(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text(f"{_HOME}/x\n{_HOME}/y\n")
        findings = scan_file(f, STRUCTURAL_RULES, rel_path=Path("a.md"))
        write_baseline(tmp_path, findings)
        assert load_baseline(tmp_path) == {"a.md": 2}

    def test_at_baseline_is_clean(self) -> None:
        findings = _fake_findings("a.md", 2)
        assert regressions(findings, {"a.md": 2}) == []

    def test_increase_is_a_regression(self) -> None:
        findings = _fake_findings("a.md", 3)
        assert len(regressions(findings, {"a.md": 2})) == 3

    def test_new_file_is_a_regression(self) -> None:
        findings = _fake_findings("new.md", 1)
        assert len(regressions(findings, {"a.md": 5})) == 1

    def test_decrease_is_clean(self) -> None:
        findings = _fake_findings("a.md", 1)
        assert regressions(findings, {"a.md": 5}) == []

    def test_malformed_baseline_reads_as_empty(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / BASELINE_PATH).write_text("{not json")
        assert load_baseline(tmp_path) == {}

    def test_baseline_stores_counts_not_matched_text(self, tmp_path: Path) -> None:
        f = tmp_path / "a.md"
        f.write_text(f"{_HOME}/secret-project/x\n")
        findings = scan_file(f, STRUCTURAL_RULES, rel_path=Path("a.md"))
        path = write_baseline(tmp_path, findings)
        text = path.read_text()
        assert "alice" not in text
        assert "secret-project" not in text


def _fake_findings(path: str, n: int):
    from little_loops.cli.verify_private_refs import PrivateRefFinding

    return [
        PrivateRefFinding(
            path=Path(path), line=i + 1, rule="abs_user_path", rationale="r", excerpt="<redacted>"
        )
        for i in range(n)
    ]


class TestCLI:
    def test_paths_mode_exit_1_on_finding(self, tmp_path: Path, capsys) -> None:
        f = tmp_path / "x.md"
        f.write_text(f"{_HOME}/x\n")
        rc = main_verify_private_refs(["-C", str(tmp_path), "x.md"])
        assert rc == 1
        assert "alice" not in capsys.readouterr().out

    def test_paths_mode_exit_0_when_clean(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text("scripts/little_loops/x.py:1\n")
        assert main_verify_private_refs(["-C", str(tmp_path), "x.md"]) == 0

    def test_paths_mode_ignores_baseline(self, tmp_path: Path) -> None:
        """Changed-files mode is the forward-only gate: no grandfathering."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / BASELINE_PATH).write_text(json.dumps({"counts": {"x.md": 99}}))
        (tmp_path / "x.md").write_text(f"{_HOME}/x\n")
        assert main_verify_private_refs(["-C", str(tmp_path), "x.md"]) == 1

    def test_excluded_dir_not_scanned(self, tmp_path: Path) -> None:
        d = tmp_path / "postmortems"
        d.mkdir()
        (d / "run.md").write_text(f"{_HOME}/x\n")
        assert main_verify_private_refs(["-C", str(tmp_path), "postmortems/run.md"]) == 0

    def test_json_output_shape(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "x.md").write_text(f"{_HOME}/x\n")
        rc = main_verify_private_refs(["-C", str(tmp_path), "x.md", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert payload["ok"] is False
        assert payload["count"] == 1
        assert payload["findings"][0]["rule"] == "abs_user_path"

    def test_requires_paths_or_all(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            main_verify_private_refs(["-C", str(tmp_path)])

    def test_update_baseline_requires_all(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            main_verify_private_refs(["-C", str(tmp_path), "--update-baseline", "x.md"])


def _git_repo(tmp_path: Path) -> Path:
    """Init a throwaway repo with one committed file carrying a private ref."""
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    target = tmp_path / "f.md"
    target.write_text(f"line1\nold {_HOME}/pre/x\nline3\n")
    subprocess.run(["git", "add", "f.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return target


class TestAddedOnly:
    """The pre-commit gate must judge added lines, not whole files.

    Without this, editing any of the ~800 grandfathered files is rejected for
    pre-existing content the author never touched — which punishes unrelated
    work and trains people to bypass the gate.
    """

    def test_unrelated_edit_to_grandfathered_file_passes(self, tmp_path: Path) -> None:
        target = _git_repo(tmp_path)
        target.write_text(f"line1 EDITED\nold {_HOME}/pre/x\nline3\n")
        subprocess.run(["git", "add", "f.md"], cwd=tmp_path, check=True)
        assert main_verify_private_refs(["-C", str(tmp_path), "--added-only", "f.md"]) == 0

    def test_newly_added_reference_is_still_caught(self, tmp_path: Path) -> None:
        """The fix must not make the gate toothless."""
        target = _git_repo(tmp_path)
        target.write_text(f"line1\nold {_HOME}/pre/x\nline3\nnew {_HOME}/brand/new\n")
        subprocess.run(["git", "add", "f.md"], cwd=tmp_path, check=True)
        assert main_verify_private_refs(["-C", str(tmp_path), "--added-only", "f.md"]) == 1

    def test_brand_new_file_is_fully_scanned(self, tmp_path: Path) -> None:
        _git_repo(tmp_path)
        (tmp_path / "g.md").write_text(f"ref {_HOME}/new/file\n")
        subprocess.run(["git", "add", "g.md"], cwd=tmp_path, check=True)
        assert main_verify_private_refs(["-C", str(tmp_path), "--added-only", "g.md"]) == 1

    def test_without_flag_whole_file_is_judged(self, tmp_path: Path) -> None:
        """Plain changed-files mode keeps its stricter contract (the hook uses it)."""
        target = _git_repo(tmp_path)
        target.write_text(f"line1 EDITED\nold {_HOME}/pre/x\nline3\n")
        subprocess.run(["git", "add", "f.md"], cwd=tmp_path, check=True)
        assert main_verify_private_refs(["-C", str(tmp_path), "f.md"]) == 1

    def test_added_line_numbers_parsed_from_hunks(self, tmp_path: Path) -> None:
        target = _git_repo(tmp_path)
        target.write_text(f"line1\nold {_HOME}/pre/x\nline3\nadded4\n")
        subprocess.run(["git", "add", "f.md"], cwd=tmp_path, check=True)
        assert staged_added_lines(tmp_path, [Path("f.md")]) == {"f.md": {4}}

    def test_no_git_fails_closed(self, tmp_path: Path) -> None:
        """Not a repo → None, which callers must read as 'scan everything'."""
        (tmp_path / "f.md").write_text(f"{_HOME}/x\n")
        assert staged_added_lines(tmp_path, [Path("f.md")]) is None
        # and the CLI still reports the finding rather than silently passing
        assert main_verify_private_refs(["-C", str(tmp_path), "--added-only", "f.md"]) == 1

    def test_added_only_rejected_with_all(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            main_verify_private_refs(["-C", str(tmp_path), "--all", "--added-only"])


class TestRepoGate:
    """The CI gate: this repo is public and must gain no new private references.

    Fails when a tracked file's private-reference count exceeds the baseline in
    .ll/private-refs-baseline.json. Regenerate deliberately, never reflexively:

        ll-verify-private-refs --all --update-baseline

    Raising the baseline publishes the reference. Prefer a repo-relative path or
    a generic placeholder.
    """

    def test_no_new_private_references(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        if not (repo_root / ".git").exists():
            pytest.skip("not a git checkout; nothing to enumerate")

        result = subprocess.run(
            ["ll-verify-private-refs", "--all", "--json", "-C", str(repo_root)],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode not in (0, 1):
            pytest.skip(f"ll-verify-private-refs unavailable (rc={result.returncode})")

        payload = json.loads(result.stdout)
        if payload["ok"]:
            return

        detail = "\n".join(
            f"  {f['file']}:{f['line']} [{f['rule']}] {f['excerpt']}"
            for f in payload["findings"][:20]
        )
        pytest.fail(
            f"{payload['count']} private-codebase reference(s) beyond baseline.\n"
            f"{detail}\n\n"
            "This repo is public. Use a repo-relative path or a placeholder, or "
            "suppress a reviewed false positive with 'll-private-ok: <reason>'."
        )

    def test_baseline_is_tracked_and_parseable(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        baseline = repo_root / BASELINE_PATH
        assert baseline.is_file(), f"{BASELINE_PATH} must be tracked for the gate to mean anything"
        assert load_baseline(repo_root), (
            "baseline parsed empty — every file would read as regressed"
        )

    def test_local_patterns_file_is_not_tracked(self) -> None:
        """The opt-in name list must never be committed to this public repo."""
        repo_root = Path(__file__).resolve().parents[2]
        if not (repo_root / ".git").exists():
            pytest.skip("not a git checkout")
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(LOCAL_PATTERNS_PATH)],
            capture_output=True,
            cwd=repo_root,
        )
        assert result.returncode != 0, (
            f"{LOCAL_PATTERNS_PATH} is tracked — it lists private project names "
            "and would publish exactly what the check exists to withhold"
        )


def test_counts_by_file_aggregates() -> None:
    findings = _fake_findings("a.md", 2) + _fake_findings("b.md", 1)
    assert counts_by_file(findings) == {"a.md": 2, "b.md": 1}
