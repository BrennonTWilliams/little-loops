"""BUG-3481: a worker crash under --dist loadfile must fail fast, not wedge.

pytest-xdist 3.7.0's ``LoadScopeScheduling.remove_node`` re-queues a crashed
worker's entire ``assigned_work`` -- including files it already finished --
so the replacement worker gets a work unit with zero pending indices, never
reports completion, and both the controller and worker idle forever
(upstream #784/#1327, fixed by #1328/#1371, unreleased through 3.8.0).
``--max-worker-restart=0`` sidesteps the buggy re-queue path entirely by
reporting the crash and shutting down instead of cloning a replacement.

This test guards the *project config*, not xdist itself: it loads
``scripts/pyproject.toml``'s addopts (rather than passing
``--max-worker-restart=0`` explicitly) so it fails if the flag is ever
removed from the config.
"""

import os
import signal
import subprocess
import sys
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "scripts" / "pyproject.toml"
_PYTEST_INI = _REPO_ROOT / "pytest.ini"

_CRASH_TREE = {
    "pytest.ini": "[pytest]\naddopts = -p no:cacheprovider -p no:benchmark\n",
    "test_fast1.py": (
        "import pytest\n@pytest.mark.parametrize('n', range(10))\ndef test_fast(n): assert True\n"
    ),
    "test_fast2.py": (
        "import pytest\n@pytest.mark.parametrize('n', range(10))\ndef test_fast(n): assert True\n"
    ),
    "test_fast3.py": (
        "import pytest\n@pytest.mark.parametrize('n', range(10))\ndef test_fast(n): assert True\n"
    ),
    "test_crash_exit.py": (
        "import os, time\n"
        "def test_a(): pass\n"
        "def test_b():\n"
        "    time.sleep(2); os._exit(1)\n"
        "def test_c(): pass\n"
        "def test_d(): pass\n"
    ),
}


def _project_addopts() -> list[str]:
    config = tomllib.loads(_PYPROJECT.read_text())
    return list(config["tool"]["pytest"]["ini_options"]["addopts"])


def test_pytest_ini_stub_stays_in_sync_with_max_worker_restart() -> None:
    assert "--max-worker-restart=0" in _PYTEST_INI.read_text(), (
        "root pytest.ini stub's addopts must mirror "
        "scripts/pyproject.toml's --max-worker-restart=0 (BUG-3481)"
    )


def test_worker_crash_under_loadfile_fails_fast(tmp_path: Path) -> None:
    for name, content in _CRASH_TREE.items():
        (tmp_path / name).write_text(content)

    addopts = _project_addopts()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *addopts,
        "-n",
        "2",
        "-c",
        str(tmp_path / "pytest.ini"),
        "--rootdir",
        str(tmp_path),
        "-q",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, _ = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired as exc:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise AssertionError(
            "run wedged past 60s -- a crashed xdist worker under --dist "
            "loadfile is deadlocking the controller again (BUG-3481)"
        ) from exc

    assert proc.returncode != 0, (
        f"expected non-zero exit after a worker crash, got 0\nstdout:\n{stdout}"
    )
    assert "crashed while running 'test_crash_exit.py::test_b'" in stdout, (
        f"expected xdist's crash report naming the killed test\nstdout:\n{stdout}"
    )
