"""FEAT-3573: autodev post-implement quality gate.

Executes the real shell/python actions of `oracles/code-run-gate` (format stage,
aggregate, worktree PYTHONPATH) and autodev's gate states (`route_quality_gate`,
`mark_quality_*`, `record_quality_evidence`, `finalize_done`) against synthetic run
dirs and throwaway git repos, so the closure-credit contract is exercised end to end
rather than by string matching.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
AUTODEV = yaml.safe_load((LOOPS_DIR / "autodev.yaml").read_text())
ORACLE = yaml.safe_load((LOOPS_DIR / "oracles" / "code-run-gate.yaml").read_text())
PARENT = yaml.safe_load((LOOPS_DIR / "auto-refine-and-implement.yaml").read_text())

_REF = re.compile(r"\$\{(context|captured)\.([\w.]+)([^}]*)\}")


def render(
    action: str, ctx: dict[str, str] | None = None, cap: dict[str, str] | None = None
) -> str:
    """Interpolate `${context.*}` / `${captured.*}` refs the way the FSM does."""
    ctx = ctx or {}
    cap = cap or {}

    def sub(m: re.Match[str]) -> str:
        space, path, suffix = m.groups()
        source = ctx if space == "context" else cap
        default = ""
        d = re.search(r":default=(.*)", suffix)
        if d:
            default = d.group(1)
        value = source.get(path, default)
        return shlex.quote(value) if ":shell" in suffix else value

    return _REF.sub(sub, action).replace("$${", "${")


def bash(script: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "seed.py").write_text("x = 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "seed")
    return r


# --------------------------------------------------------------------------- oracle


class TestOracleFormatStage:
    def _setup(self, tmp_path: Path, fmt_cmd: str, files: list[str] | None) -> tuple[Path, Path]:
        run_dir = tmp_path / "oracle"
        run_dir.mkdir()
        (run_dir / "commands.json").write_text(json.dumps({"format_check_cmd": fmt_cmd}))
        fp = tmp_path / "files.txt"
        if files is not None:
            fp.write_text("".join(f + "\n" for f in files))
        return run_dir, fp

    def _run(self, run_dir: Path, fp: str) -> subprocess.CompletedProcess:
        action = ORACLE["states"]["run_format_check"]["action"]
        ctx = {"run_dir": str(run_dir), "changed_files_path": fp}
        return bash(render(action, ctx), run_dir)

    def test_skips_without_changed_files_path(self, tmp_path: Path) -> None:
        """Opt-in: every pre-existing caller (no path) gets SKIP even when configured."""
        run_dir, _ = self._setup(tmp_path, "false {files}", None)
        r = self._run(run_dir, "")
        assert r.returncode == 0
        assert (run_dir / "format-check.txt").read_text().startswith("SKIP")

    def test_skips_when_file_list_empty(self, tmp_path: Path) -> None:
        run_dir, fp = self._setup(tmp_path, "false {files}", [])
        assert self._run(run_dir, str(fp)).returncode == 0
        assert (run_dir / "format-check.txt").read_text().startswith("SKIP")

    def test_skips_when_command_unset(self, tmp_path: Path) -> None:
        run_dir, fp = self._setup(tmp_path, "", ["a.py"])
        assert self._run(run_dir, str(fp)).returncode == 0
        assert (run_dir / "format-check.txt").read_text().startswith("SKIP")

    def test_substitutes_shell_quoted_files(self, tmp_path: Path) -> None:
        run_dir, fp = self._setup(
            tmp_path, "printf '<%s>' {files}", ["a.py", "dir with space/b.py"]
        )
        r = self._run(run_dir, str(fp))
        assert r.returncode == 0, r.stderr
        text = (run_dir / "format-check.txt").read_text()
        assert "<a.py><dir with space/b.py>" in text
        assert text.rstrip().endswith("exit_code=0")

    def test_nonzero_exit_recorded(self, tmp_path: Path) -> None:
        run_dir, fp = self._setup(tmp_path, "false {files}", ["a.py"])
        # Like every run_* state, the script itself exits 0; the failure is the
        # recorded exit_code= line, which aggregate turns into GATE_FAILED.
        assert "exit_code=1" in self._run(run_dir, str(fp)).stdout
        assert "exit_code=1" in (run_dir / "format-check.txt").read_text()

    def test_state_timeout_and_budget(self) -> None:
        states = ORACLE["states"]
        assert states["run_format_check"]["timeout"] == 120
        total = sum(s.get("timeout", 0) for s in states.values())
        assert total < ORACLE["timeout"], "stage timeouts must sum under the loop timeout"
        assert states["run_format_check"].get("prepatch_check") is None

    def test_state_chain(self) -> None:
        s = ORACLE["states"]
        assert s["run_lint"]["on_yes"] == "run_format_check"
        assert s["run_format_check"]["on_yes"] == "service_health"


class TestOracleAggregate:
    def _aggregate(self, run_dir: Path, files_path: str = "") -> tuple[str, str]:
        action = ORACLE["states"]["aggregate"]["action"]
        ctx = {
            "run_dir": str(run_dir),
            "issue_id": "FEAT-1",
            "min_pass_rate": "1.0",
            "changed_files_path": files_path,
        }
        r = bash(render(action, ctx), run_dir)
        verdict = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        return verdict, r.stderr

    @staticmethod
    def _commands(run_dir: Path, **cmds: str) -> None:
        (run_dir / "commands.json").write_text(json.dumps(cmds))

    def test_pass(self, tmp_path: Path) -> None:
        (tmp_path / "test-results.txt").write_text("ok\npass_rate=1.0\nexit_code=0\n")
        self._commands(tmp_path, test_cmd="pytest")
        assert self._aggregate(tmp_path)[0] == "GATE_PASS"

    def test_all_skip(self, tmp_path: Path) -> None:
        (tmp_path / "test-results.txt").write_text("SKIP test_cmd=null\n")
        self._commands(tmp_path)
        assert self._aggregate(tmp_path)[0] == "GATE_SKIP"

    def test_killed_stage_without_exit_code_fails(self, tmp_path: Path) -> None:
        """Partial output, no exit_code= line: the state was killed at its timeout."""
        (tmp_path / "test-results.txt").write_text("collecting ...\n")
        self._commands(tmp_path, test_cmd="pytest")
        assert self._aggregate(tmp_path)[0] == "GATE_FAILED"

    def test_configured_but_absent_sidecar_fails(self, tmp_path: Path) -> None:
        self._commands(tmp_path, lint_cmd="ruff check .")
        assert self._aggregate(tmp_path)[0] == "GATE_FAILED"

    def test_unconfigured_absent_sidecar_is_not_a_failure(self, tmp_path: Path) -> None:
        (tmp_path / "lint.txt").write_text("ok\nexit_code=0\n")
        self._commands(tmp_path, lint_cmd="ruff check .")
        assert self._aggregate(tmp_path)[0] == "GATE_PASS"

    def test_format_sidecar_required_only_with_path_cmd_and_files(self, tmp_path: Path) -> None:
        self._commands(tmp_path, format_cmd_unused="x", format_check_cmd="fmt {files}")
        fp = tmp_path / "files.txt"
        fp.write_text("a.py\n")
        # path + cmd + files, sidecar absent → failure
        assert self._aggregate(tmp_path, str(fp))[0] == "GATE_FAILED"
        # no path passed (existing callers) → not required
        assert self._aggregate(tmp_path, "")[0] == "GATE_SKIP"
        # empty file list → not required
        fp.write_text("")
        assert self._aggregate(tmp_path, str(fp))[0] == "GATE_SKIP"

    def test_format_failure_fails_gate(self, tmp_path: Path) -> None:
        (tmp_path / "format-check.txt").write_text("would reformat a.py\nexit_code=1\n")
        self._commands(tmp_path, format_check_cmd="fmt {files}")
        assert self._aggregate(tmp_path)[0] == "GATE_FAILED"

    def test_relative_changed_files_path_resolved_before_cd(self, tmp_path: Path) -> None:
        """aggregate cd's into run_dir; a relative path must be resolved first."""
        run_dir = tmp_path / "oracle"
        run_dir.mkdir()
        (tmp_path / "files.txt").write_text("a.py\n")
        self._commands(run_dir, format_check_cmd="fmt {files}")
        action = ORACLE["states"]["aggregate"]["action"]
        ctx = {
            "run_dir": str(run_dir),
            "issue_id": "FEAT-1",
            "min_pass_rate": "1.0",
            "changed_files_path": "files.txt",
        }
        r = bash(render(action, ctx), tmp_path)  # cwd = tmp_path, path relative to it
        assert r.stdout.strip().splitlines()[-1] == "GATE_FAILED"  # sidecar absent → found file


class TestOracleResolve:
    def test_commands_json_survives_double_quotes(self, tmp_path: Path) -> None:
        action = ORACLE["states"]["resolve_commands"]["action"]
        # Config-file commands go through json.dumps; a `"` no longer yields invalid JSON.
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"test_cmd": 'pytest -k "a or b"'}})
        )
        ctx = {
            "run_dir": str(tmp_path),
            "issue_id": "FEAT-1",
            "project_root": str(tmp_path),
        }
        r = bash(render(action, ctx), tmp_path)
        assert r.returncode == 0, r.stderr
        cmds = json.loads((tmp_path / "commands.json").read_text())
        assert cmds["test_cmd"] == 'pytest -k "a or b"'

    def test_resolve_via_ll_config_uses_ll_config_and_records_src_dir(self, tmp_path: Path) -> None:
        """Opt-in: ll-config (which honors ll.local.md) is authoritative; file is ignored."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "ll-config").write_text(
            '#!/bin/sh\ncase "$2" in\n'
            "project.test_cmd) echo 'local-test';;\n"
            "project.format_check_cmd) echo 'fmt --check {files}';;\n"
            "project.src_dir) echo 'scripts/';;\nesac\n"
        )
        (bin_dir / "ll-config").chmod(0o755)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"project": {"test_cmd": "file-test", "lint_cmd": "file-lint"}})
        )
        action = ORACLE["states"]["resolve_commands"]["action"]
        ctx = {"run_dir": str(tmp_path), "issue_id": "X-1", "project_root": str(tmp_path)}
        env = {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
        # default: file-only resolution (existing callers)
        bash(render(action, ctx), tmp_path, env)
        cmds = json.loads((tmp_path / "commands.json").read_text())
        assert cmds["test_cmd"] == "file-test" and cmds["lint_cmd"] == "file-lint"
        assert cmds["format_check_cmd"] == "" and cmds["src_dir"] == ""
        # opt-in: ll-config wins; unset keys blank their stage
        bash(render(action, {**ctx, "resolve_via_ll_config": "1"}), tmp_path, env)
        cmds = json.loads((tmp_path / "commands.json").read_text())
        assert cmds["test_cmd"] == "local-test" and cmds["lint_cmd"] == ""
        assert cmds["format_check_cmd"] == "fmt --check {files}"
        assert cmds["src_dir"] == "scripts/"
        # explicit caller override still wins
        bash(
            render(action, {**ctx, "resolve_via_ll_config": "1", "test_cmd": "override"}),
            tmp_path,
            env,
        )
        assert json.loads((tmp_path / "commands.json").read_text())["test_cmd"] == "override"

    def test_declares_new_params(self) -> None:
        params = ORACLE["parameters"]
        for key in ("format_check_cmd", "changed_files_path", "src_dir", "resolve_via_ll_config"):
            assert key in params and params[key]["required"] is False


class TestOracleWorktreePythonPath:
    def _run_test_state(self, cwd: Path, run_dir: Path, src_dir: str) -> str:
        run_dir.mkdir(exist_ok=True)
        (run_dir / "commands.json").write_text(
            json.dumps(
                {
                    "test_cmd": "python3 -c \"import os; print('PP=' + os.environ.get('PYTHONPATH', ''))\"",
                    "src_dir": src_dir,
                }
            )
        )
        action = ORACLE["states"]["run_test"]["action"]
        bash(render(action, {"run_dir": str(run_dir)}), cwd, env={"PYTHONPATH": ""})
        return (run_dir / "test-results.txt").read_text()

    def test_prepended_only_in_linked_worktree_with_src_dir(
        self, repo: Path, tmp_path: Path
    ) -> None:
        wt = tmp_path / "wt"
        _git(repo, "worktree", "add", "-q", "-b", "wtb", str(wt))
        in_wt = self._run_test_state(wt, tmp_path / "r1", "scripts")
        assert f"PP={wt.resolve()}/scripts" in in_wt or f"PP={wt}/scripts" in in_wt
        # main worktree: no injection
        assert "PP=\n" in self._run_test_state(repo, tmp_path / "r2", "scripts")
        # linked worktree but no src_dir: no injection (existing callers unchanged)
        assert "PP=\n" in self._run_test_state(wt, tmp_path / "r3", "")


class TestOracleRunTestEnvScrub:
    """BUG-3689: run_test drops inherited LL_PYTHON / COLUMNS / LINES before test_cmd."""

    POLLUTED = {"LL_PYTHON": "/fake/python", "COLUMNS": "150", "LINES": "60"}
    PROBE = (
        'python3 -c "import os; '
        "print('ENV=' + ','.join(k + '=' + os.environ.get(k, '-') "
        "for k in ('LL_PYTHON', 'COLUMNS', 'LINES')) "
        "+ ';PP=' + os.environ.get('PYTHONPATH', '') "
        "+ ';GATE=' + os.environ.get('LL_VERIFY_GATE', '-'))\""
    )

    def _run(self, cwd: Path, run_dir: Path, test_cmd: str, src_dir: str = "", **env: str) -> str:
        run_dir.mkdir(exist_ok=True)
        (run_dir / "commands.json").write_text(
            json.dumps({"test_cmd": test_cmd, "src_dir": src_dir})
        )
        action = ORACLE["states"]["run_test"]["action"]
        bash(render(action, {"run_dir": str(run_dir)}), cwd, env={**self.POLLUTED, **env})
        return (run_dir / "test-results.txt").read_text()

    def test_inherited_overrides_removed_and_other_env_preserved(
        self, repo: Path, tmp_path: Path
    ) -> None:
        out = self._run(
            repo, tmp_path / "r1", self.PROBE, PYTHONPATH="/inherited", LL_VERIFY_GATE="1"
        )
        assert "ENV=LL_PYTHON=-,COLUMNS=-,LINES=-" in out
        assert ";PP=/inherited;GATE=1" in out

    def test_linked_worktree_pythonpath_prepended_after_scrub(
        self, repo: Path, tmp_path: Path
    ) -> None:
        wt = tmp_path / "wt"
        _git(repo, "worktree", "add", "-q", "-b", "wtb", str(wt))
        out = self._run(wt, tmp_path / "r1", self.PROBE, "scripts", PYTHONPATH="/inherited")
        assert "ENV=LL_PYTHON=-,COLUMNS=-,LINES=-" in out
        assert f"{wt.resolve()}/scripts:/inherited" in out or f"{wt}/scripts:/inherited" in out

    def test_explicit_assignment_in_test_cmd_wins(self, repo: Path, tmp_path: Path) -> None:
        out = self._run(repo, tmp_path / "r1", f"COLUMNS=120 LL_PYTHON=/mine {self.PROBE}")
        assert "ENV=LL_PYTHON=/mine,COLUMNS=120,LINES=-" in out

    def test_failing_command_still_gate_failed(self, repo: Path, tmp_path: Path) -> None:
        run_dir = tmp_path / "r1"
        out = self._run(repo, run_dir, "exit 7")
        assert "pass_rate=0.0" in out and out.rstrip().endswith("exit_code=7")
        aggregate = TestOracleAggregate()
        (run_dir / "commands.json").write_text(json.dumps({"test_cmd": "exit 7"}))
        assert aggregate._aggregate(run_dir)[0] == "GATE_FAILED"

    def test_yaml_unset_matches_shared_tuple(self) -> None:
        from little_loops.worktree_utils import HERMETIC_ENV_VARS

        action = ORACLE["states"]["run_test"]["action"]
        m = re.search(r"^\s*unset ([A-Z_ ]+)$", action, re.MULTILINE)
        assert m is not None
        assert tuple(m.group(1).split()) == HERMETIC_ENV_VARS
        assert action.index(m.group(0).strip()) < action.index('bash -c "$TEST_CMD"')


# --------------------------------------------------------------------------- autodev


def _stubs(tmp_path: Path, status: str = "Done", exts: str = "") -> dict[str, str]:
    """PATH stubs for ll-issues (status) and ll-config (format_check_extensions)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "ll-issues").write_text(
        f'#!/bin/sh\nif [ "$1" = "show" ]; then echo \'{{"status":"{status}"}}\'; fi\n'
    )
    (bin_dir / "exts.txt").write_text(exts)
    (bin_dir / "ll-config").write_text(f'#!/bin/sh\ncat "{bin_dir}/exts.txt"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}


class TestRouteQualityGate:
    def _run(
        self,
        repo: Path,
        run_dir: Path,
        env: dict[str, str],
        gate: str = "true",
        id_: str = "FEAT-1",
    ) -> subprocess.CompletedProcess:
        action = AUTODEV["states"]["route_quality_gate"]["action"]
        ctx = {"run_dir": str(run_dir), "quality_gate": gate}
        return bash(render(action, ctx, {"input.output": id_}), repo, env)

    def _snapshot(self, repo: Path, run_dir: Path, id_: str = "FEAT-1") -> None:
        q = run_dir / "quality"
        q.mkdir(parents=True, exist_ok=True)
        (q / f"{id_}.base").write_text(_git(repo, "rev-parse", "HEAD") + "\n")
        dirty = subprocess.run(
            "{ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u",
            shell=True,
            cwd=repo,
            capture_output=True,
            text=True,
        ).stdout
        (q / f"{id_}.base-dirty").write_text(dirty)

    def test_changed_set_scoping(self, repo: Path, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        (repo / "wip_tracked.py").write_text("w = 1\n")
        _git(repo, "add", "wip_tracked.py")
        _git(repo, "commit", "-q", "-m", "wip")
        (repo / "wip_tracked.py").write_text("w = 2\n")  # pre-existing tracked dirt
        (repo / "wip_untracked.py").write_text("u = 1\n")  # pre-existing untracked
        (repo / "gone.py").write_text("g = 1\n")
        _git(repo, "add", "gone.py")
        _git(repo, "commit", "-q", "-m", "add gone")
        self._snapshot(repo, run_dir)
        # "implementation": commit a change, delete a file, leave a new untracked file
        (repo / "new.py").write_text("n = 1\n")
        (repo / "notes.md").write_text("# n\n")
        _git(repo, "add", "new.py", "notes.md")
        _git(repo, "rm", "-q", "gone.py")
        _git(repo, "commit", "-q", "-m", "impl")
        (repo / "left_over.py").write_text("l = 1\n")

        r = self._run(repo, run_dir, _stubs(tmp_path, exts="['.py']"))
        assert r.returncode == 0, r.stderr
        q = run_dir / "quality"
        changed = (q / "FEAT-1.changed").read_text().split()
        assert sorted(changed) == ["left_over.py", "new.py", "notes.md"]
        assert "gone.py" not in changed  # deleted files dropped
        assert "wip_tracked.py" not in changed and "wip_untracked.py" not in changed
        assert (q / "FEAT-1.dirtyset").read_text().split() == ["left_over.py"]
        # extension filter applies to the format stage only
        assert sorted((q / "FEAT-1.format-files").read_text().split()) == [
            "left_over.py",
            "new.py",
        ]

    def test_committed_change_to_preexisting_dirty_file_still_included(
        self, repo: Path, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "run"
        (repo / "seed.py").write_text("x = 2\n")  # pre-existing dirt on a tracked file
        self._snapshot(repo, run_dir)
        (repo / "seed.py").write_text("x = 3\n")
        _git(repo, "commit", "-q", "-am", "impl touches seed")
        assert self._run(repo, run_dir, _stubs(tmp_path)).returncode == 0
        assert "seed.py" in (run_dir / "quality" / "FEAT-1.changed").read_text().split()

    def test_no_extension_filter_passes_every_file(self, repo: Path, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        self._snapshot(repo, run_dir)
        (repo / "a.md").write_text("x\n")
        _git(repo, "add", "a.md")
        _git(repo, "commit", "-q", "-m", "impl")
        assert self._run(repo, run_dir, _stubs(tmp_path, exts="")).returncode == 0
        assert (run_dir / "quality" / "FEAT-1.format-files").read_text().split() == ["a.md"]

    def test_cancelled_closure_skips_gate(self, repo: Path, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        self._snapshot(repo, run_dir)
        assert self._run(repo, run_dir, _stubs(tmp_path, status="Cancelled")).returncode == 1

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off"])
    def test_disabled_gate_skips(self, repo: Path, tmp_path: Path, value: str) -> None:
        run_dir = tmp_path / "run"
        self._snapshot(repo, run_dir)
        assert self._run(repo, run_dir, _stubs(tmp_path), gate=value).returncode == 1

    def test_missing_base_is_infra(self, repo: Path, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        assert self._run(repo, run_dir, _stubs(tmp_path)).returncode == 2

    def test_stale_evidence_cleared(self, repo: Path, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        self._snapshot(repo, run_dir)
        (run_dir / "quality" / "FEAT-1.json").write_text("{}")
        (run_dir / "quality" / "FEAT-1.route").write_text("pass")
        self._run(repo, run_dir, _stubs(tmp_path))
        assert not (run_dir / "quality" / "FEAT-1.json").exists()
        assert not (run_dir / "quality" / "FEAT-1.route").exists()

    def test_routing(self) -> None:
        s = AUTODEV["states"]
        assert s["verify_impl_closed"]["on_yes"] == "route_quality_gate"
        assert s["route_quality_gate"]["on_yes"] == "run_quality_gate"
        assert s["route_quality_gate"]["on_no"] == "dequeue_next"
        assert s["route_quality_gate"]["on_error"] == "mark_quality_infra"
        gate = s["run_quality_gate"]
        assert gate["loop"] == "oracles/code-run-gate"
        assert gate["on_success"] == "mark_quality_pass"
        assert gate["on_failure"] == "mark_quality_fail"
        assert gate["on_error"] == "mark_quality_infra"
        assert gate["with"]["min_pass_rate"] == 1.0
        for name in ("mark_quality_pass", "mark_quality_fail", "mark_quality_infra"):
            assert s[name]["next"] == "record_quality_evidence"
        assert s["record_quality_evidence"]["next"] == "dequeue_next"

    def test_snapshot_lines_precede_ll_auto(self) -> None:
        action = AUTODEV["states"]["implement_current"]["action"]
        assert action.index(".base-dirty") < action.index("ll-auto --only")
        assert action.index("rev-parse HEAD") < action.index("ll-auto --only")


class TestMarkQualityFail:
    @pytest.mark.parametrize(
        ("terminated_by", "expected"),
        [
            ("terminal", "fail"),
            ("timeout", "infra"),
            ("signal", "infra"),
            ("interrupted", "infra"),
            ("max_steps", "infra"),
            ("", "infra"),
        ],
    )
    def test_route_from_terminated_by(
        self, tmp_path: Path, terminated_by: str, expected: str
    ) -> None:
        (tmp_path / "quality").mkdir()
        action = AUTODEV["states"]["mark_quality_fail"]["action"]
        r = bash(
            render(
                action,
                {"run_dir": str(tmp_path)},
                {"input.output": "FEAT-1", "run_quality_gate.terminated_by": terminated_by},
            ),
            tmp_path,
        )
        assert r.returncode == 0, r.stderr
        assert (tmp_path / "quality" / "FEAT-1.route").read_text() == expected


def _record(run_dir: Path, route: str, **sidecars: str) -> dict[str, Any]:
    """Run record_quality_evidence against a synthetic oracle run dir."""
    q = run_dir / "quality"
    oracle = q / "FEAT-1"
    oracle.mkdir(parents=True, exist_ok=True)
    (oracle / "commands.json").write_text(
        json.dumps(
            {
                "test_cmd": "t",
                "lint_cmd": "l",
                "typecheck_cmd": "y",
                "format_check_cmd": "f {files}",
            }
        )
    )
    (oracle / "subloop_outcome_FEAT-1.txt").write_text("GATE_PASS\n")  # resolve_commands seed
    for name, text in sidecars.items():
        (oracle / name).write_text(text)
    (q / "FEAT-1.route").write_text(route)
    (q / "FEAT-1.base").write_text("abc123\n")
    (q / "FEAT-1.changed").write_text("a.py\n")
    (q / "FEAT-1.format-files").write_text("a.py\n")
    action = AUTODEV["states"]["record_quality_evidence"]["action"]
    r = bash(render(action, {"run_dir": str(run_dir)}, {"input.output": "FEAT-1"}), run_dir)
    assert r.returncode == 0, r.stderr
    return json.loads((q / "FEAT-1.json").read_text())


PASSING = {
    "test-results.txt": "ok\nexit_code=0\n",
    "lint.txt": "ok\nexit_code=0\n",
    "typecheck.txt": "ok\nexit_code=0\n",
    "format-check.txt": "ok\nexit_code=0\n",
}


class TestRecordQualityEvidence:
    def test_pass(self, tmp_path: Path) -> None:
        rec = _record(tmp_path, "pass", **PASSING)
        assert rec["verdict"] == "GATE_PASS" and rec["route"] == "pass"
        assert rec["test"] == rec["lint"] == rec["typecheck"] == rec["format_check"] == "pass"
        assert rec["base_sha"] == "abc123" and rec["changed_files"] == ["a.py"]
        assert set(rec) >= {"issue_id", "head_sha", "dirty", "prepatch", "route", "verdict"}
        assert not (tmp_path / "autodev-unverified.txt").exists()

    def test_verdict_from_route_not_token_file(self, tmp_path: Path) -> None:
        """subloop_outcome_<ID>.txt says GATE_PASS (resolve_commands seed); route says fail."""
        rec = _record(tmp_path, "fail", **{**PASSING, "test-results.txt": "boom\nexit_code=1\n"})
        assert rec["verdict"] == "GATE_FAILED"
        assert rec["test"] == "fail"
        assert (tmp_path / "autodev-unverified.txt").read_text() == "FEAT-1  quality_gate_failed\n"

    def test_route_fail_with_all_stages_passing_still_failed(self, tmp_path: Path) -> None:
        """e.g. prepatch_check flagged routes straight to the oracle's failed terminal."""
        (tmp_path / "quality" / "FEAT-1").mkdir(parents=True)
        (tmp_path / "quality" / "FEAT-1" / "prepatch_evidence_FEAT-1.json").write_text(
            json.dumps({"verdict": "flagged"})
        )
        rec = _record(tmp_path, "fail", **PASSING)
        assert rec["verdict"] == "GATE_FAILED" and rec["prepatch"] == "flagged"

    def test_infra(self, tmp_path: Path) -> None:
        rec = _record(tmp_path, "infra")
        assert rec["verdict"] == "GATE_INFRA"
        assert (tmp_path / "autodev-unverified.txt").read_text() == "FEAT-1  quality_gate_infra\n"

    def test_skip_when_every_stage_skips(self, tmp_path: Path) -> None:
        skips = {
            "test-results.txt": "SKIP test_cmd=null\n",
            "lint.txt": "SKIP lint_cmd=null\n",
            "typecheck.txt": "SKIP typecheck_cmd=null\n",
            "format-check.txt": "SKIP format_check_cmd=null\n",
        }
        assert _record(tmp_path, "pass", **skips)["verdict"] == "GATE_SKIP"

    def test_killed_and_absent_stages_reported(self, tmp_path: Path) -> None:
        rec = _record(
            tmp_path,
            "fail",
            **{"test-results.txt": "partial output\n", "lint.txt": "ok\nexit_code=0\n"},
        )
        assert rec["test"] == "killed"
        assert rec["typecheck"] == "absent" and rec["format_check"] == "absent"

    def test_dirty_flag_from_dirtyset(self, tmp_path: Path) -> None:
        (tmp_path / "quality").mkdir(parents=True)
        (tmp_path / "quality" / "FEAT-1.dirtyset").write_text("left.py\n")
        assert _record(tmp_path, "pass", **PASSING)["dirty"] is True

    def test_no_duplicate_ledger_line(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-unverified.txt").write_text("FEAT-1  impl_exit0_not_closed\n")
        _record(tmp_path, "fail", **PASSING)
        assert (tmp_path / "autodev-unverified.txt").read_text().count("FEAT-1") == 1


class TestFinalizeDonePromotion:
    """finalize_done's promotion, run through little_loops.autodev_summary (the
    module the state calls) against real issue files carrying *statuses*."""

    def _run(self, run_dir: Path, statuses: dict[str, str], gate: str = "true") -> tuple[dict, str]:
        import contextlib
        import io

        from little_loops import autodev_summary

        action = AUTODEV["states"]["finalize_done"]["action"]
        assert "python3 -m little_loops.autodev_summary" in action
        assert "--quality-gate ${context.quality_gate:shell:default=true}" in action
        project = run_dir / "project"
        (project / ".ll").mkdir(parents=True, exist_ok=True)
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps({"issues": {"base_dir": ".issues"}})
        )
        dirs = {"FEAT": "features", "BUG": "bugs", "ENH": "enhancements"}
        for issue_id, status in statuses.items():
            cat = project / ".issues" / dirs[issue_id.split("-")[0]]
            cat.mkdir(parents=True, exist_ok=True)
            (cat / f"P3-{issue_id}-t.md").write_text(
                f"---\nid: {issue_id}\nstatus: {status}\n---\n\n# {issue_id}: t\n"
            )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.returncode = autodev_summary.main(
                ["--run-dir", str(run_dir), "--quality-gate", gate, "--project-root", str(project)]
            )
        return json.loads((run_dir / "summary.json").read_text()), buf.getvalue()

    @staticmethod
    def _evidence(run_dir: Path, id_: str, verdict: str, head: str = "deadbeefcafe", dirty=False):
        q = run_dir / "quality"
        q.mkdir(exist_ok=True)
        (q / f"{id_}.json").write_text(
            json.dumps({"issue_id": id_, "verdict": verdict, "head_sha": head, "dirty": dirty})
        )

    def test_context_defaults(self) -> None:
        assert AUTODEV["context"]["quality_gate"] == "true"
        assert PARENT["context"]["quality_gate"] == "true"
        assert PARENT["states"]["delegate"]["with"]["quality_gate"] == "${context.quality_gate}"

    @pytest.mark.parametrize("verdict", ["GATE_PASS", "GATE_SKIP"])
    def test_evidence_promotes_done(self, tmp_path: Path, verdict: str) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\n")
        self._evidence(tmp_path, "FEAT-1", verdict)
        summary, _ = self._run(tmp_path, {"FEAT-1": "Done"})
        assert summary["verdict"] == "success" and summary["closed"] == 1
        assert summary["quality_failed"] == 0 and summary["quality_gate_infra"] == 0
        assert (tmp_path / "autodev-passed.txt").read_text().split() == ["FEAT-1"]

    def test_failed_gate_not_promoted_and_reported(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\nFEAT-2\n")
        (tmp_path / "autodev-unverified.txt").write_text("FEAT-2  quality_gate_failed\n")
        self._evidence(tmp_path, "FEAT-1", "GATE_PASS")
        self._evidence(tmp_path, "FEAT-2", "GATE_FAILED", head="0123456789ab", dirty=True)
        summary, out = self._run(tmp_path, {"FEAT-1": "Done", "FEAT-2": "Done"})
        assert summary["closed"] == 1
        assert summary["not_closed"] == 1
        assert summary["quality_failed"] == 1 and summary["quality_gate_infra"] == 0
        assert summary["verdict"] == "partial"
        assert "FEAT-2" not in (tmp_path / "autodev-passed.txt").read_text()
        qline = [ln for ln in out.splitlines() if ln.startswith("Quality-failed")]
        assert qline and "FEAT-2@01234567 (dirty)" in qline[0]
        assert "rerun will not re-gate" in qline[0]
        # not under the generic "re-queue to retry" Unverified line
        assert not [ln for ln in out.splitlines() if ln.startswith("Unverified")]

    def test_infra_gate_reported_separately(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\n")
        (tmp_path / "autodev-unverified.txt").write_text("FEAT-1  quality_gate_infra\n")
        self._evidence(tmp_path, "FEAT-1", "GATE_INFRA")
        summary, out = self._run(tmp_path, {"FEAT-1": "Done"})
        assert summary["quality_gate_infra"] == 1 and summary["quality_failed"] == 0
        assert summary["not_closed"] == 1 and summary["verdict"] == "phantom"
        assert self.returncode == 1
        assert any(ln.startswith("Quality-gate-infra [infra] (1)") for ln in out.splitlines())

    def test_all_gated_failed_prints_workaround_hint(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\n")
        (tmp_path / "autodev-unverified.txt").write_text("FEAT-1  quality_gate_failed\n")
        self._evidence(tmp_path, "FEAT-1", "GATE_FAILED")
        _, out = self._run(tmp_path, {"FEAT-1": "Done"})
        assert "quality_gate=false" in out

    def test_done_without_evidence_is_missing(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\n")
        summary, out = self._run(tmp_path, {"FEAT-1": "Done"})
        assert summary["closed"] == 0 and summary["not_closed"] == 1
        assert (
            tmp_path / "autodev-unverified.txt"
        ).read_text() == "FEAT-1  quality_evidence_missing\n"
        assert any(ln.startswith("Unverified") for ln in out.splitlines())

    def test_cancelled_promoted_without_evidence(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\n")
        summary, _ = self._run(tmp_path, {"FEAT-1": "Cancelled"})
        assert summary["closed"] == 1 and summary["closed_cancelled"] == 1

    def test_gate_off_restores_status_only_credit(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-staged.txt").write_text("FEAT-1\n")
        summary, _ = self._run(tmp_path, {"FEAT-1": "Done"}, gate="false")
        assert summary["closed"] == 1 and summary["verdict"] == "success"

    def test_summary_key_shape(self, tmp_path: Path) -> None:
        summary, _ = self._run(tmp_path, {})
        keys = list(summary)
        assert keys[-6:] == [
            "closed_implemented",
            "closed_cancelled",
            "quality_failed",
            "quality_gate_infra",
            "record_absent",
            "record_ledger_mismatch",
        ]


class TestParentAccounting:
    def test_quality_failed_done_issue_is_not_closed(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps(
                {
                    "issues": {
                        "base_dir": ".issues",
                        "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    }
                }
            )
        )
        bugs = project / ".issues" / "bugs"
        bugs.mkdir(parents=True)
        for n in ("9001", "9002"):
            (bugs / f"BUG-{n}-x.md").write_text(
                f"---\nid: BUG-{n}\ntype: BUG\ntitle: t\nstatus: done\npriority: P3\n---\n\n# t\n"
            )
        run_dir = project / "run_dir"
        run_dir.mkdir()
        (run_dir / "auto-refine-and-implement-completed-baseline.txt").write_text("")
        (run_dir / "auto-refine-and-implement-done-baseline.txt").write_text("")
        (run_dir / "autodev-passed.txt").write_text("BUG-9001\n")
        (run_dir / "autodev-unverified.txt").write_text("BUG-9002  quality_gate_failed\n")

        script = PARENT["states"]["finalize"]["action"]
        script = render(script, {"run_dir": str(run_dir)}, {"issue_set.output": ""})
        r = bash(script, project)
        summary = json.loads((run_dir / "summary.json").read_text())
        assert summary["closed"] == 1, (summary, r.stderr)
        assert summary["not_closed"] == 1
        assert summary["quality_failed"] == 1 and summary["quality_gate_infra"] == 0
        assert summary["verdict"] == "partial"
