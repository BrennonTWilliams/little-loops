"""Real-Git fixtures for the scoped-activity loader (FEAT-3713 step 2).

Every fixture shares one skip gate: the installed Git must accept the enforcing global
``--no-lazy-fetch`` option (Git >= 2.45.0, per that release's notes), so a contributor with an
older Git is not hard-blocked. Fake-stream contracts in ``test_feat3713_scan_activity.py`` run
unconditionally.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.next_arena.scan_activity import MIN_GIT_VERSION, load_scope_activity
from tests.scan_support import (
    AS_OF,
    AS_OF_EPOCH,
    DAY,
    commit_at,
    git,
    git_available,
    init_repo,
    scope_for,
)

pytestmark = pytest.mark.skipif(
    not git_available(),
    reason=f"installed Git does not accept --no-lazy-fetch ({MIN_GIT_VERSION}+)",
)

NOW = AS_OF_EPOCH - DAY  # inside the 30-day window
OLD = AS_OF_EPOCH - 90 * DAY
FUTURE = AS_OF_EPOCH + 5 * DAY


def activity(root: Path, focus=("src",), exclude=(), *, threshold: int = 20):
    scope = scope_for(root, focus, exclude)
    return load_scope_activity(root, scope, as_of=AS_OF, threshold=threshold, lookback_days=30)


def test_installed_git_accepts_the_enforcing_lazy_fetch_option() -> None:
    assert git_available()  # the gate itself: documents the 2.45.0 minimum


def test_exact_count_over_root_merge_rename_delete_and_unusual_dates(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    commit_at(repo, OLD, "root", files={"src/a.py": "1", "docs/readme.md": "r"})  # old: no
    commit_at(repo, NOW, "docs only", files={"docs/readme.md": "2"})  # out of scope
    commit_at(repo, NOW + 10, "edit", files={"src/a.py": "2"})  # 1
    git(repo, "mv", "src/a.py", "docs/a.py")  # rename out of scope: src deletion counts
    commit_at(repo, NOW + 20, "rename out")  # 2
    git(repo, "mv", "docs/a.py", "src/b.py")  # rename into scope: src addition counts
    commit_at(repo, NOW + 30, "rename in")  # 3
    git(repo, "checkout", "-q", "-b", "side")
    commit_at(repo, NOW + 40, "side", files={"src/s.py": "s"})  # 4 (reachable side branch)
    git(repo, "checkout", "-q", "main")
    commit_at(repo, NOW + 50, "main only", files={"docs/readme.md": "3"})
    git(
        repo,
        "merge",
        "-q",
        "--no-ff",
        "side",
        "-m",
        "merge",
        env={"GIT_AUTHOR_DATE": f"{NOW + 60} +0000", "GIT_COMMITTER_DATE": f"{NOW + 60} +0000"},
    )  # 5
    commit_at(repo, FUTURE, "future dated", files={"src/f.py": "f"})  # future: excluded
    commit_at(repo, NOW - DAY, "backdated child", files={"src/old.py": "o"})  # 6, parent newer
    git(repo, "rm", "-q", "src/old.py")
    commit_at(repo, NOW + 70, "deletion")  # 7
    result = activity(repo)
    assert result.available and result.complete and not result.saturated
    assert result.scoped_commit_count == 7
    assert result.head == git(repo, "rev-parse", "HEAD") and result.shallow is False
    assert result.git_calls == 2


def test_saturation_reports_a_lower_bound(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    for i in range(6):
        commit_at(repo, NOW + i, f"c{i}", files={"src/a.py": str(i)})
    result = activity(repo, threshold=4)
    assert result.saturated and result.lower_bound == 4 and result.scoped_commit_count is None


def test_a_quiet_long_history_completes_with_an_exact_count(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    for i in range(12):
        commit_at(repo, OLD - i * DAY, f"old{i}", files={"src/a.py": f"old{i}"})
    for i in range(3):
        commit_at(repo, NOW + i, f"new{i}", files={"src/a.py": f"new{i}"})
    result = activity(repo)
    assert result.complete and result.scoped_commit_count == 3
    # --since-as-filter dropped the out-of-window records from the stream entirely
    assert result.records_visited == 3


def test_literal_backslash_and_newline_names_are_not_separators(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    literal = "src/a\\b.py"
    newline = "src/new\nline.py"
    commit_at(repo, NOW, "literal backslash", files={literal: "x"})
    commit_at(repo, NOW + 1, "newline name", files={newline: "x"})
    commit_at(repo, NOW + 2, "different path", files={"src/a/b.py": "y"})
    # excluding the slash-separated path must not suppress the literal-backslash commit
    result = activity(repo, exclude=("src/a/b.py",))
    assert result.complete and result.scoped_commit_count == 2
    # a newline filename is one literal path, matched by a basename glob
    assert activity(repo, exclude=("src/new*",)).scoped_commit_count == 2
    assert activity(repo, exclude=("src/*.py",)).scoped_commit_count == 0


def test_a_filename_shaped_like_the_old_sentinel_cannot_forge_commits(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    forged = f"src/\x01{'f' * 40}\x02{NOW}"
    commit_at(repo, NOW, "sentinel name", files={forged: "x"})
    commit_at(repo, NOW + 1, "docs", files={"docs/x": "x"})
    result = activity(repo)
    assert result.complete and result.scoped_commit_count == 1 and result.records_visited == 2


def test_nested_project_uses_project_relative_paths(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    project = repo / "services" / "api"
    (project / ".ll").mkdir(parents=True)
    commit_at(repo, NOW, "outside only", files={"src/x.py": "x", "services/other/src/y.py": "y"})
    commit_at(repo, NOW + 1, "inside", files={"services/api/src/a.py": "a"})
    git(repo, "checkout", "-q", "-b", "side")
    commit_at(repo, NOW + 2, "inside side", files={"services/api/src/s.py": "s"})
    git(repo, "checkout", "-q", "main")
    git(
        repo,
        "merge",
        "-q",
        "--no-ff",
        "side",
        "-m",
        "merge",
        env={"GIT_AUTHOR_DATE": f"{NOW + 3} +0000", "GIT_COMMITTER_DATE": f"{NOW + 3} +0000"},
    )
    # ambient diff.relative=false must not change the coordinates
    git(repo, "config", "diff.relative", "false")
    result = activity(project)
    assert result.complete
    assert result.scoped_commit_count == 3  # inside, inside side and the merge that brings it in
    assert result.records_visited == 4  # the outside-only commit is a retained empty-path record


def test_nested_project_below_a_newline_directory_name(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    project = repo / "weird\nname"
    (project / ".ll").mkdir(parents=True)
    commit_at(repo, NOW, "inside", files={"weird\nname/src/a.py": "a", "other/src/b.py": "b"})
    commit_at(repo, NOW + 1, "outside", files={"other/src/c.py": "c"})
    result = activity(project)
    assert result.complete and result.scoped_commit_count == 1 and result.records_visited == 2


def test_non_git_directory_and_unborn_head_are_unavailable_never_zero(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    (plain / "src").mkdir(parents=True)
    result = activity(plain)
    assert not result.available and result.unavailable_reason in {
        "not_a_git_repository",
        "git_failed",
    }
    assert result.scoped_commit_count is None and result.git_calls == 1
    unborn = init_repo(tmp_path / "unborn")
    assert not activity(unborn).available


def test_shallow_clone_below_threshold_is_flagged(tmp_path: Path) -> None:
    origin = init_repo(tmp_path / "origin")
    for i in range(4):
        commit_at(origin, NOW + i, f"c{i}", files={"src/a.py": str(i)})
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "2", f"file://{origin}", str(clone)], check=True
    )
    result = activity(clone, threshold=20)
    assert result.shallow is True and result.complete
    assert result.scoped_commit_count == 2  # the available history only; gate treats it partial


def test_partial_clone_missing_objects_is_unavailable_and_fetches_nothing(tmp_path: Path) -> None:
    origin = init_repo(tmp_path / "origin")
    git(origin, "config", "uploadpack.allowFilter", "true")
    commit_at(origin, NOW, "c1", files={"src/a.py": "1"})
    commit_at(origin, NOW + 1, "c2", files={"src/a.py": "2"})
    clone = tmp_path / "clone"
    done = subprocess.run(
        ["git", "clone", "-q", "--filter=tree:0", "--no-checkout", f"file://{origin}", str(clone)],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        pytest.skip("this Git cannot make a tree-less partial clone")
    packs = sorted(p.name for p in (clone / ".git" / "objects" / "pack").iterdir())
    result = activity(clone)
    assert not result.available and result.unavailable_reason == "git_failed"
    assert result.scoped_commit_count is None and result.lower_bound is None
    assert sorted(p.name for p in (clone / ".git" / "objects" / "pack").iterdir()) == packs


def test_trace_targets_and_helpers_never_run_or_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path / "repo")
    commit_at(repo, NOW, "c", files={"src/a.py": "x", ".gitattributes": "*.py diff=spy\n"})
    marker = tmp_path / "helper-ran"
    helper = tmp_path / "helper.sh"
    helper.write_text(f'#!/bin/sh\ntouch {marker}\ncat "$1"\n')
    helper.chmod(0o755)
    git(repo, "config", "diff.spy.textconv", str(helper))
    git(repo, "config", "diff.external", str(helper))
    git(repo, "config", "log.showSignature", "true")
    trace_env = tmp_path / "trace-env"
    trace_cfg = tmp_path / "trace-config"
    git(repo, "config", "trace2.eventTarget", str(trace_cfg))
    for var in (
        "GIT_TRACE",
        "GIT_TRACE2",
        "GIT_TRACE2_EVENT",
        "GIT_TRACE2_PERF",
        "GIT_TRACE_SETUP",
    ):
        monkeypatch.setenv(var, str(trace_env))
    result = activity(repo)
    assert result.complete and result.scoped_commit_count == 1  # signature setting kept framing
    assert not marker.exists()
    assert not trace_env.exists() and not trace_cfg.exists()


def test_an_unknown_global_option_exits_129_like_an_old_git() -> None:
    # An older Git rejects --no-lazy-fetch exactly like any unknown global option: exit 129,
    # which the loader maps to git_unsupported (see the injected-result test in the fake suite).
    done = subprocess.run(
        ["git", "--no-such-global-option", "rev-parse", "HEAD"], capture_output=True, text=True
    )
    assert done.returncode == 129
