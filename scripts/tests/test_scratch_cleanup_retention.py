"""Retention and record-handling tests for hooks/scripts/scratch-cleanup.sh (ENH-3706).

Deterministic checks only, kept in an unmarked module so the push unit matrix
(GNU and BSD userland) exercises them. Large-directory timing evidence stays in
``test_hooks_integration.py``.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "hooks/scripts/scratch-cleanup.sh"
DEAD_PID = 2147483647  # 2**31-1: not a valid/alive process on any real system
DAY = 24.0


def _age(path: Path, hours: float) -> None:
    ts = time.time() - hours * 3600
    os.utime(path, (ts, ts), follow_symlinks=False)


def _bashes() -> list[str]:
    """Distinct bash interpreters: PATH ``bash`` plus darwin ``/bin/bash`` (3.2)."""
    found = [shutil.which("bash") or "bash"]
    if sys.platform == "darwin" and Path("/bin/bash").exists():
        if Path("/bin/bash").resolve() != Path(found[0]).resolve():
            found.append("/bin/bash")
    return found


def _run(
    root: Path,
    bash_bin: str = "bash",
    path_prefix: Path | None = None,
    timeout: float = 15.0,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [bash_bin, str(SCRIPT)],
        input="{}",
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
        timeout=timeout,
    )


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    d = tmp_path / ".loops/tmp/scratch"
    d.mkdir(parents=True)
    return d


def _sentinel(scratch: Path) -> Path:
    """Fresh file keeping the dir non-empty so rmdir cannot mask a survivor."""
    s = scratch / "sentinel.txt"
    s.touch()
    return s


def _find_shim(shims: Path, pass1_body: str, pass0_body: str | None = None) -> None:
    """Install a ``find`` shim. Pass 1 is identified by ``-print0``; pass 0 by ``-delete``.

    Any other invocation, or a pass with no body, execs the real ``find``.
    """
    real = shutil.which("find")
    shims.mkdir(exist_ok=True)
    shim = shims / "find"
    pass0 = pass0_body if pass0_body is not None else f'exec {real} "$@"'
    shim.write_text(
        "#!/bin/bash\n"
        'for a in "$@"; do\n'
        f'  [ "$a" = "-delete" ] && {{ {pass0}; }}\n'
        f'  [ "$a" = "-print0" ] && {{ {pass1_body}; }}\n'
        "done\n"
        f'exec {real} "$@"\n'
    )
    shim.chmod(0o755)


@pytest.mark.parametrize("bash_bin", _bashes())
class TestSevenDayTier:
    def test_no_suffix_file_removed_past_seven_days_kept_before(
        self, scratch: Path, bash_bin: str
    ) -> None:
        old, young = scratch / "test-results.txt", scratch / "notes.txt"
        edge_hi, edge_lo = scratch / "edge-hi.txt", scratch / "edge-lo.txt"
        for f, h in (
            (old, 8 * DAY),
            (young, 6 * DAY),
            (edge_hi, 7 * DAY + 1),
            (edge_lo, 7 * DAY - 1),
        ):
            f.touch()
            _age(f, h)
        _sentinel(scratch)
        result = _run(scratch.parent.parent.parent, bash_bin)
        assert result.returncode == 0
        assert not old.exists() and not edge_hi.exists()
        assert young.exists() and edge_lo.exists()

    def test_odd_names_removed_by_complete_path(self, scratch: Path, bash_bin: str) -> None:
        names = [".hidden", "with space.txt", "multi\nline.txt", "-dash.txt"]
        for n in names:
            f = scratch / n
            f.touch()
            _age(f, 8 * DAY)
        fresh = scratch / "fixed-name.txt"
        fresh.touch()
        result = _run(scratch.parent.parent.parent, bash_bin)
        assert result.returncode == 0
        assert [n for n in names if (scratch / n).exists()] == []
        assert fresh.exists()

    def test_pid_shaped_live_pid_removed_at_eight_days_kept_at_six(
        self, scratch: Path, bash_bin: str
    ) -> None:
        old, young = scratch / f"live-{os.getpid()}.txt", scratch / f"live2-{os.getpid()}.txt"
        for f, h in ((old, 8 * DAY), (young, 6 * DAY)):
            f.touch()
            _age(f, h)
        _sentinel(scratch)
        assert _run(scratch.parent.parent.parent, bash_bin).returncode == 0
        assert not old.exists()
        assert young.exists()

    def test_dead_pid_tier_around_24h(self, scratch: Path, bash_bin: str) -> None:
        old = scratch / f"a-{DEAD_PID}.txt"
        young = scratch / f"b-{DEAD_PID}.txt"
        for f, h in ((old, 25), (young, 23)):
            f.touch()
            _age(f, h)
        no_suffix = scratch / "plain.txt"
        no_suffix.touch()
        _age(no_suffix, 3 * DAY)
        assert _run(scratch.parent.parent.parent, bash_bin).returncode == 0
        assert not old.exists()
        assert young.exists() and no_suffix.exists()

    def test_newline_name_is_one_record_and_spares_fresh_file(
        self, scratch: Path, bash_bin: str
    ) -> None:
        """An old ``old\\nfresh-<pid>.txt`` must not select the separate fresh file."""
        old = scratch / f"old\nfresh-{DEAD_PID}.txt"
        old.touch()
        _age(old, 48)
        fresh = scratch / f"fresh-{DEAD_PID}.txt"
        fresh.touch()
        result = _run(scratch.parent.parent.parent, bash_bin)
        assert result.returncode == 0
        assert fresh.exists(), "fresh file was deleted via a split newline record"
        assert not old.exists(), "the complete old filename gets normal dead-PID handling"


class TestScopeAndSymlinks:
    def test_subdirs_nested_files_and_symlinks_preserved(
        self, scratch: Path, tmp_path: Path
    ) -> None:
        sub = scratch / "sub"
        sub.mkdir()
        nested = sub / "nested.txt"
        nested.touch()
        _age(nested, 30 * DAY)
        ext_dir = tmp_path / "external"
        ext_dir.mkdir()
        target = ext_dir / "target.txt"
        target.touch()
        _age(target, 30 * DAY)
        link = scratch / f"link-{DEAD_PID}.txt"
        link.symlink_to(target)
        _age(link, 30 * DAY)
        assert _run(tmp_path).returncode == 0
        assert nested.exists() and sub.exists()
        assert link.is_symlink() and target.exists()

    def test_symlinked_scratch_root_causes_no_target_deletion(self, tmp_path: Path) -> None:
        external = tmp_path / "external"
        external.mkdir()
        victims = [external / "old.txt", external / f"dead-{DEAD_PID}.txt"]
        for v in victims:
            v.touch()
            _age(v, 30 * DAY)
        nested = external / "dir"
        nested.mkdir()
        (nested / "deep.txt").touch()
        _age(nested / "deep.txt", 30 * DAY)
        root = tmp_path / "proj"
        (root / ".loops/tmp").mkdir(parents=True)
        (root / ".loops/tmp/scratch").symlink_to(external)
        assert _run(root).returncode == 0
        assert all(v.exists() for v in victims)
        assert (nested / "deep.txt").exists()


class TestCooperativeStopAndRestart:
    def test_deadline_checked_per_record_including_skips_and_batch_flushed(
        self, scratch: Path, tmp_path: Path
    ) -> None:
        """dead1 queued -> 4s stall -> keep (skipped) -> dead2: stop before keep."""
        dead1 = scratch / f"d1-{DEAD_PID}.txt"
        dead2 = scratch / f"d2-{DEAD_PID}.txt"
        keep = scratch / "keep.txt"
        for f in (dead1, dead2, keep):
            f.touch()
            _age(f, 48)
        d = ".loops/tmp/scratch"
        _find_shim(
            tmp_path / "shims",
            f'printf "{d}/d1-{DEAD_PID}.txt\\0"; sleep 4; '
            f'printf "{d}/keep.txt\\0{d}/d2-{DEAD_PID}.txt\\0"; exit 0',
        )
        result = _run(tmp_path, path_prefix=tmp_path / "shims")
        assert result.returncode == 0
        assert not dead1.exists(), "pending batch must be flushed after the cooperative stop"
        assert dead2.exists(), "records after the deadline must not be processed"
        assert keep.exists()

    def test_interrupted_sweep_keeps_progress_and_rerun_finishes(
        self, scratch: Path, tmp_path: Path
    ) -> None:
        old_pass0 = scratch / "ancient.txt"  # removed by pass 0 before the stall
        dead = scratch / f"d-{DEAD_PID}.txt"  # pass-1 work, never reached
        fresh = scratch / f"fresh-{DEAD_PID}.txt"
        old_pass0.touch()
        _age(old_pass0, 30 * DAY)
        dead.touch()
        _age(dead, 48)
        fresh.touch()
        _find_shim(tmp_path / "shims", "sleep 60; exit 0")
        env = {**os.environ, "PATH": f"{tmp_path / 'shims'}{os.pathsep}{os.environ['PATH']}"}
        proc = subprocess.Popen(
            ["bash", str(SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(tmp_path),
            env=env,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 10
            while old_pass0.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not old_pass0.exists(), "pass 0 never completed"
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        assert dead.exists() and fresh.exists()

        result = _run(tmp_path)  # real tools: continues where the killed run stopped
        assert result.returncode == 0
        assert not dead.exists()
        assert fresh.exists()


class TestForksAndErrors:
    def test_pass0_spawns_no_per_file_processes(self, scratch: Path, tmp_path: Path) -> None:
        for i in range(300):
            f = scratch / f"cmd{i}.txt"
            f.touch()
            _age(f, 10 * DAY)
        shims = tmp_path / "shims"
        shims.mkdir()
        log = tmp_path / "calls.log"
        for tool in ("rm", "basename", "sed", "stat"):
            real = shutil.which(tool)
            shim = shims / tool
            shim.write_text(f'#!/bin/bash\necho {tool} >> "{log}"\nexec {real} "$@"\n')
            shim.chmod(0o755)
        assert _run(tmp_path, path_prefix=shims).returncode == 0
        assert not log.exists(), f"unexpected forks: {log.read_text().split()}"
        assert not scratch.exists()

    def test_vanished_file_and_failing_pass0_do_not_fail_the_hook(
        self, scratch: Path, tmp_path: Path
    ) -> None:
        real_dead = scratch / f"real-{DEAD_PID}.txt"
        real_dead.touch()
        _age(real_dead, 48)
        d = ".loops/tmp/scratch"
        _find_shim(
            tmp_path / "shims",
            f'printf "{d}/gone-{DEAD_PID}.txt\\0{d}/real-{DEAD_PID}.txt\\0"; exit 0',
            pass0_body="echo find: boom >&2; exit 1",
        )
        result = _run(tmp_path, path_prefix=tmp_path / "shims")
        assert result.returncode == 0
        assert not real_dead.exists()
