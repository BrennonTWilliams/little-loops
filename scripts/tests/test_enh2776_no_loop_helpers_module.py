"""ENH-2776: guard that cli/loop/_helpers.py never reappears.

The grab-bag module was dissolved into named modules (signals.py, feed.py,
header.py, queue.py, runner.py, summary.py, plus fsm/context_seed.py and
fsm/loop_paths.py) — see the issue for the full split rationale. This is the
"remove + permanent guard test" precedent (ENH-3097/ENH-3261): the file must
never exist again, and no source or test file may reference the old
``cli.loop._helpers`` import path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_helpers_module_does_not_exist() -> None:
    helpers_path = REPO_ROOT / "scripts" / "little_loops" / "cli" / "loop" / "_helpers.py"
    assert not helpers_path.exists(), (
        f"{helpers_path} must not exist — ENH-2776 dissolved it into named modules "
        "(signals/feed/header/queue/runner/summary + fsm/context_seed, fsm/loop_paths)."
    )


def test_no_references_to_old_import_path() -> None:
    banned = "cli" + ".loop._helpers"  # split so this guard's own source never self-matches
    result = subprocess.run(
        [
            "grep",
            "-rlF",
            "--include=*.py",
            f"--exclude={Path(__file__).name}",
            banned,
            "scripts/little_loops",
            "scripts/tests",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    # grep exit code 1 = no matches (expected); 0 = matches found (fail); >1 = error
    assert result.returncode != 0, (
        f"Found stale references to the deleted cli.loop._helpers import path:\n{result.stdout}"
    )
    assert result.returncode == 1, f"grep failed: {result.stderr}"
