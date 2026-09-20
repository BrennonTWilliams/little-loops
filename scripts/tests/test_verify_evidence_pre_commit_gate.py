"""Pre-commit plumbing for the ``ll-verify-evidence`` hook (ENH-3518).

The hook is warn-only (``|| true``), and pre-commit hides the output of passing
hooks unless ``verbose: true``. These tests gate that the entry is visible and
that entry / display name / comment agree on blocking policy, and (when
``pre-commit`` and the verifier are on PATH) that the real hook entry prints an
invalid staged quote's finding.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
HOOK_ID = "ll-verify-evidence"
PRE_COMMIT_TIMEOUT = 60

ARTIFACT_PATH = ".issues/enhancements/target.md"
ARTIFACT_TEXT = "The verifier keeps a warm cache of span verdicts between runs.\n"
VALID_QUOTE = "warm cache of span verdicts between runs"
INVALID_QUOTE = "this fabricated sentence appears nowhere in the artifact"


def _hook_block() -> str:
    text = CONFIG.read_text()
    match = re.search(rf"^( *)- id: {HOOK_ID}\n(.*?)(?=^\1- id: |\Z)", text, re.M | re.S)
    assert match, f"{HOOK_ID} entry missing from .pre-commit-config.yaml"
    return match.group(0)


def _is_warn_only(block: str) -> bool:
    return "|| true" in re.search(r"^ *entry: .*$", block, re.M).group(0)  # type: ignore[union-attr]


class TestHookConfiguration:
    def test_entry_is_verbose(self) -> None:
        assert re.search(r"^ *verbose: true$", _hook_block(), re.M)

    def test_policy_agrees_across_entry_name_and_comment(self) -> None:
        block = _hook_block()
        name = re.search(r"^ *name: (.*)$", block, re.M).group(1)  # type: ignore[union-attr]
        warn_only = _is_warn_only(block)
        assert ("warn-only" in name) == warn_only
        if warn_only:
            assert "non-blocking" in block

    def test_comment_says_findings_are_printed(self) -> None:
        assert "verbose" in _hook_block().split("name:")[0]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _issue(quote: str) -> str:
    return (
        "---\nid: BUG-9001\ntype: BUG\nstatus: open\n---\n\n# BUG-9001: t\n\n"
        f"## Current Behavior\n\nThe target says `{quote}` (`{ARTIFACT_PATH}`).\n"
    )


@pytest.fixture
def staged_repo(tmp_path: Path) -> Path:
    if shutil.which("pre-commit") is None or shutil.which(HOOK_ID) is None:
        pytest.skip("pre-commit or ll-verify-evidence not installed")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}\n")
    for d in ("bugs", "enhancements"):
        (tmp_path / ".issues" / d).mkdir(parents=True)
    (tmp_path / ARTIFACT_PATH).write_text(ARTIFACT_TEXT)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "artifact")
    return tmp_path


def _run_hook(repo: Path, quote: str) -> subprocess.CompletedProcess:
    rel = ".issues/bugs/P3-BUG-9001-quote.md"
    (repo / rel).write_text(_issue(quote))
    _git(repo, "add", rel)
    return subprocess.run(
        ["pre-commit", "run", HOOK_ID, "--config", str(CONFIG), "--files", rel],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=PRE_COMMIT_TIMEOUT,
    )


class TestInstalledHook:
    def test_invalid_quote_finding_is_printed(self, staged_repo: Path) -> None:
        result = _run_hook(staged_repo, INVALID_QUOTE)
        out = result.stdout + result.stderr
        assert INVALID_QUOTE in out, out
        assert "finding(s)" in out, out
        assert "Traceback" not in out, out
        expected = 0 if _is_warn_only(_hook_block()) else 1
        assert result.returncode == expected, out

    def test_valid_quote_is_clean_control(self, staged_repo: Path) -> None:
        result = _run_hook(staged_repo, VALID_QUOTE)
        out = result.stdout + result.stderr
        assert result.returncode == 0, out
        assert "finding(s)" not in out, out
        assert "Traceback" not in out, out
