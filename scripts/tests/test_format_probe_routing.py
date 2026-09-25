"""ENH-3576: normalize_structure / precheck_format probe state-action tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"


def _run(state: str, tmp_path: Path, payload: str, counter: str | None) -> tuple[str, str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "ll-issues"
    fake.write_text(f"#!/bin/sh\ncat <<'EOF'\n{payload}\nEOF\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    ctr = tmp_path / "refine-to-ready-format-fallback"
    if counter is not None:
        ctr.write_text(counter)
    action = yaml.safe_load((LOOPS / "refine-to-ready-issue.yaml").read_text())["states"][state][
        "action"
    ]
    script = action.replace("${context.run_dir}", str(tmp_path))
    script = script.replace("${captured.issue_id.output:shell}", "ENH-9800")
    proc = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    return proc.stdout.strip(), proc.stderr, ctr.read_text() if ctr.exists() else ""


@pytest.mark.parametrize("state", ["normalize_structure", "precheck_format"])
def test_gaps_counter_zero_emits_count_and_arms(tmp_path: Path, state: str) -> None:
    out, _err, ctr = _run(state, tmp_path, '{"directive_gaps": ["Summary", "Use Case"]}', "0")
    assert out == "2"
    assert ctr == "1"


@pytest.mark.parametrize("state", ["normalize_structure", "precheck_format"])
def test_gaps_counter_spent_emits_zero_and_reports(tmp_path: Path, state: str) -> None:
    out, err, _ctr = _run(state, tmp_path, '{"directive_gaps": ["Summary"]}', "1")
    assert out == "0"
    assert "[STRUCT_GAP_REMAINS]" in err


@pytest.mark.parametrize("state", ["normalize_structure", "precheck_format"])
def test_no_gaps_emits_zero(tmp_path: Path, state: str) -> None:
    out, _err, ctr = _run(state, tmp_path, '{"directive_gaps": []}', "0")
    assert out == "0"
    assert ctr == "0"


@pytest.mark.parametrize("state", ["normalize_structure", "precheck_format"])
def test_probe_failure_fails_open(tmp_path: Path, state: str) -> None:
    out, _err, _ctr = _run(state, tmp_path, "not json", "0")
    assert out == "0"
