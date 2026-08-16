"""Pin auto-refine-and-implement's closure accounting (ENH-3198).

The `finalize` state counts closures over the UNION of two paths: issues
reaching `status: done` in place, and legacy decomposed parents git-mv'd into
`.issues/completed/`. The in-place path is the one that carries every closure
today. The completed/ path is unreachable by default automation (no in-repo
caller passes `--move`) but still feeds `closed-now-union`, whose consumers
(NOT_CLOSED, ABANDONED, INFLIGHT_UNRESOLVED) drive the run verdict — and it
is NOT fully redundant with `ll-issues list --status done`: that command
already sees completed/ entries carrying explicit `status: done` frontmatter
(via `config.legacy_issue_dirs()`, BUG-2733), but a file parked in
completed/ with no `status:` field at all (true pre-ENH-1418 legacy) defaults
to "open" and is invisible to it. These tests pin both: the first would still
pass if the `completed/` branch were deleted; the second — using a
no-status-field legacy file — is the actual guard against that regression.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "auto-refine-and-implement.yaml"


def _load_finalize_script(run_dir: Path) -> str:
    with open(LOOP_FILE) as f:
        data = yaml.safe_load(f)
    script = data["states"]["finalize"]["action"]
    script = script.replace("${context.run_dir}", str(run_dir))
    script = script.replace("${captured.issue_set.output}", "")
    return script


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def _make_project(tmp_path: Path) -> Path:
    """Build a real mini project root: .ll/ll-config.json + .issues/bugs/.

    Without this, find_project_root finds nothing, `ll-issues list` returns
    non-zero, done_ids is silently empty, and closure assertions pass
    vacuously.
    """
    project = tmp_path / "project"
    project.mkdir()
    ll_dir = project / ".ll"
    ll_dir.mkdir()
    config = {
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            },
        },
    }
    (ll_dir / "ll-config.json").write_text(json.dumps(config))
    (project / ".issues" / "bugs").mkdir(parents=True)
    return project


def _seed_baselines(run_dir: Path) -> None:
    """Pre-create empty baseline files.

    `comm` fails on a missing operand and the `2>/dev/null` swallows it, so a
    missing baseline zeroes the closure count instead of erroring.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "auto-refine-and-implement-completed-baseline.txt").write_text("")
    (run_dir / "auto-refine-and-implement-done-baseline.txt").write_text("")


def test_finalize_counts_in_place_done_closure(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    (project / ".issues" / "bugs" / "BUG-9001-fixed.md").write_text(
        "---\nid: BUG-9001\ntype: BUG\ntitle: Fixed thing\nstatus: done\npriority: P3\n---\n\n"
        "# BUG-9001: Fixed thing\n"
    )
    run_dir = project / "run_dir"
    _seed_baselines(run_dir)

    script = _load_finalize_script(run_dir)
    result = _bash(script, cwd=project)

    summary_path = run_dir / "summary.json"
    assert summary_path.exists(), f"summary.json not written: {result.stderr}"
    summary = json.loads(summary_path.read_text())
    assert summary["closed"] >= 1, (
        f"in-place status:done closure not counted: {summary} stderr={result.stderr}"
    )


def test_finalize_excludes_legacy_completed_ids_from_not_closed(tmp_path: Path) -> None:
    # No `status:` field at all — true pre-ENH-1418 legacy shape (status used
    # to live in directory location, not frontmatter). `IssueInfo.status`
    # defaults to "open" when the field is absent, so `ll-issues list
    # --status done` (which DOES scan completed/ via config.legacy_issue_dirs(),
    # BUG-2733) does NOT surface this file — only the ls-based completed-now
    # snapshot does. A file with explicit `status: done` would already be
    # found by `ll-issues list` regardless of this branch, so it would not
    # exercise the gap this test pins.
    project = _make_project(tmp_path)
    completed_dir = project / ".issues" / "completed"
    completed_dir.mkdir(parents=True)
    (completed_dir / "BUG-9999-legacy.md").write_text(
        "---\nid: BUG-9999\ntype: BUG\ntitle: Legacy closure\npriority: P3\n---\n\n"
        "# BUG-9999: Legacy closure\n"
    )
    run_dir = project / "run_dir"
    _seed_baselines(run_dir)
    (run_dir / "autodev-passed.txt").write_text("BUG-9999\n")

    script = _load_finalize_script(run_dir)
    result = _bash(script, cwd=project)

    summary_path = run_dir / "summary.json"
    assert summary_path.exists(), f"summary.json not written: {result.stderr}"
    summary = json.loads(summary_path.read_text())
    assert summary["not_closed"] == 0, (
        "a legacy .issues/completed/ ID passed by autodev must not read as "
        f"not_closed (this is the completed/ branch's actual regression guard): {summary}"
    )
