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

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

JS_TEST_DIR = Path(__file__).parent / "js"
CORE_MODULE = (
    Path(__file__).parent.parent / "little_loops" / "templates" / "policy_builder_core.mjs"
)
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "policy_builder"


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


def _require_node() -> str:
    """Return the ``node`` executable path, skipping the test if unavailable.

    Mirrors ``test_node_conformance_suite_passes``'s skip-gracefully policy so
    contributors without a Node >= 22 toolchain aren't hard-blocked (this
    repo's environment ships Node 22, so the gate is fully enforced here).
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "node not installed; round-trip validate gate runs wherever Node >= 22 is available"
        )
    major = _node_major(node)
    if major is None or major < 22:
        pytest.skip(f"Node >= 22 required for node ESM import; found major version {major}")
    return node


def _serialize_with_node(node: str, model_path: Path) -> str:
    """Shell out to node, importing the real ``serializeLoopYaml`` and running
    it against *model_path* (a JSON-encoded builder model). Returns the
    generated YAML text.
    """
    script = textwrap.dedent(
        f"""
        import {{ serializeLoopYaml }} from {json.dumps(CORE_MODULE.as_posix())};
        import {{ readFileSync }} from "node:fs";
        const model = JSON.parse(readFileSync({json.dumps(str(model_path))}, "utf8"));
        process.stdout.write(serializeLoopYaml(model));
        """
    )
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"node serialize failed (exit {proc.returncode}): {proc.stderr}"
    return proc.stdout


@pytest.mark.parametrize(
    "model_fixture",
    ["sample-decision-table.model.json", "sample-rubric.model.json"],
)
def test_round_trip_yaml_validates_for_each_mode(tmp_path: Path, model_fixture: str) -> None:
    """FEAT-2301 Capability AC 2: node's ``serializeLoopYaml`` output for both
    modes must pass ``ll-loop validate`` with zero errors.

    This closes the 2026-07-25 re-baseline's "never actually run" gap: the
    engine's YAML shape was previously only checked against static golden
    fixtures (``test_golden_yaml_validates`` / the JS golden tests), never
    generated fresh and validated end-to-end in one gate. Skips gracefully
    when Node >= 22 is unavailable, per the existing node-gate pattern.
    """
    node = _require_node()
    model_path = FIXTURES_DIR / model_fixture
    assert model_path.exists(), f"missing fixture: {model_path}"

    yaml_text = _serialize_with_node(node, model_path)
    out_path = tmp_path / f"{model_fixture.replace('.model.json', '')}.yaml"
    out_path.write_text(yaml_text)

    from little_loops.cli.loop import main_loop

    argv = ["ll-loop", "validate", str(out_path)]
    with patch.object(sys, "argv", argv):
        rc = main_loop()
    assert rc == 0, f"ll-loop validate failed (exit {rc}) for {model_fixture}:\n{yaml_text}"
