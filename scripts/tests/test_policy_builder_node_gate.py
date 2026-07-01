"""Node conformance gate for the policy-builder JS core (FEAT-2390).

The FEAT-2390 AC requires the JS logic half (``policy_builder_core.mjs``) to be
pinned against the shared conformance corpus at a *real, named, enforced*
location — "an unenforced gate does not count as met." This project has no
hosted CI (no GitHub Actions / paid runners by design); its single enforced,
cost-free test location is the local suite ``python -m pytest scripts/tests/``
(the configured ``project.test_cmd``).

This module makes the zero-dep ``node:test`` conformance suite run *as part of*
that pytest run by shelling out to ``node --test``. The Python drift-guard /
corpus / emit tests already run in the same suite (``test_policy_builder_*.py``),
so after this file the Python-and-JS gates share one named location.

The gate skips (rather than fails) when Node >= 22 is unavailable so it does not
break contributors without a Node toolchain; it is fully enforced wherever the
suite runs with Node present (this repo's environment ships Node 22).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TEST_DIR = Path(__file__).parent / "js"


def _node_major(node: str) -> int | None:
    """Return the major version of ``node``, or None if it cannot be probed."""
    try:
        proc = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = proc.stdout.strip().lstrip("v")
    head = raw.split(".", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def test_node_conformance_suite_passes() -> None:
    """Run ``node --test scripts/tests/js/*.test.mjs`` and require exit 0.

    ``node:test`` requires Node >= 22 (the ratified Option A); the suite is
    zero-dependency and consumes the same conformance corpus the Python fixtures
    pin, so a green run proves the JS core did not drift from canonical Python.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; JS conformance gate runs wherever Node >= 22 is available")
    major = _node_major(node)
    if major is None or major < 22:
        pytest.skip(f"Node >= 22 required for node:test; found major version {major}")

    test_files = sorted(JS_TEST_DIR.glob("*.test.mjs"))
    assert test_files, f"no .mjs test files found under {JS_TEST_DIR}"

    proc = subprocess.run(
        [node, "--test", *[str(p) for p in test_files]],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        "node:test conformance suite failed "
        f"(exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )
