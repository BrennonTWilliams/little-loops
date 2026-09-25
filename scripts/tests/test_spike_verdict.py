"""Tests for ll-issues spike-verdict (BUG-3592) over real pytest-generated JUnit XML."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from little_loops.cli.issues.spike_verdict import (
    HOOK_BEGIN,
    SpikeReport,
    classify_spike_junit,
    emit_conftest,
)


def _run_pytest(cwd: Path, target: str, xml: Path, *extra: str) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            target,
            f"--junitxml={xml}",
            "--maxfail=0",
            "-p",
            "no:cacheprovider",
            "-q",
            *extra,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode


def _spike(tmp_path: Path, source: str, *, addopts: str | None = None) -> SpikeReport:
    """Write a spike test module + emitted conftest, run pytest, return the report."""
    if addopts is not None:
        (tmp_path / "pytest.ini").write_text(f"[pytest]\naddopts = {addopts}\n")
    spike = tmp_path / "spike"
    spike.mkdir()
    (spike / "__init__.py").write_text("")
    emit_conftest(spike / "conftest.py")
    (spike / "test_ac.py").write_text(source)
    xml = tmp_path / "spike-1.xml"
    code = _run_pytest(tmp_path, "spike/", xml)
    return SpikeReport("spike", xml, code)


GUARD = "\ndef test_guard_isolation():\n    assert True\n"


def test_all_pass_is_proven(tmp_path: Path) -> None:
    r = _spike(tmp_path, "def test_ac():\n    assert True\n" + GUARD)
    assert classify_spike_junit([r]).verdict == "PROVEN"


def test_bare_assert_is_refuted(tmp_path: Path) -> None:
    r = _spike(tmp_path, "def test_ac():\n    assert 1 == 2\n" + GUARD)
    v = classify_spike_junit([r])
    assert v.verdict == "REFUTED"
    assert "test_ac" in v.cause


def test_unittest_assert_equal_is_refuted(tmp_path: Path) -> None:
    src = (
        "import unittest\n\nclass TestX(unittest.TestCase):\n"
        "    def test_ac(self):\n        self.assertEqual(1, 2)\n" + GUARD
    )
    assert classify_spike_junit([_spike(tmp_path, src)]).verdict == "REFUTED"


def test_did_not_raise_is_refuted(tmp_path: Path) -> None:
    src = "import pytest\n\ndef test_ac():\n    with pytest.raises(ValueError):\n        pass\n"
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "REFUTED"


def test_bare_pytest_fail_is_inconclusive(tmp_path: Path) -> None:
    src = "import pytest\n\ndef test_ac():\n    pytest.fail('no env')\n"
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


@pytest.mark.parametrize("exc", ["ImportError", "OSError", "ModuleNotFoundError"])
def test_non_assertion_exception_is_inconclusive(tmp_path: Path, exc: str) -> None:
    src = f"def test_ac():\n    raise {exc}('x')\n"
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


def test_mixed_assertion_and_import_is_inconclusive(tmp_path: Path) -> None:
    src = (
        "def test_ac_a():\n    assert 1 == 2\n\n"
        "def test_ac_b():\n    import not_installed_mod_xyz\n"
    )
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


def test_fixture_error_is_inconclusive(tmp_path: Path) -> None:
    src = (
        "import pytest\n\n@pytest.fixture\ndef boom():\n    raise RuntimeError('x')\n\n"
        "def test_ac(boom):\n    assert True\n"
    )
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


def test_failing_guard_is_inconclusive(tmp_path: Path) -> None:
    src = "def test_ac():\n    assert 1 == 2\n\ndef test_guard_x():\n    assert False\n"
    assert classify_spike_junit([_spike(tmp_path, src)]).verdict == "INCONCLUSIVE"


def test_collection_error_is_inconclusive(tmp_path: Path) -> None:
    src = "import not_installed_mod_xyz\n\ndef test_ac():\n    assert True\n"
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


def test_no_tests_collected_is_inconclusive(tmp_path: Path) -> None:
    assert classify_spike_junit([_spike(tmp_path, "x = 1\n")]).verdict == "INCONCLUSIVE"


def test_one_ac_skipped_is_inconclusive(tmp_path: Path) -> None:
    src = (
        "import pytest\n\ndef test_ac_a():\n    assert True\n\n"
        "@pytest.mark.skip\ndef test_ac_b():\n    assert True\n"
    )
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


def test_all_ac_skipped_is_inconclusive(tmp_path: Path) -> None:
    src = "import pytest\n\n@pytest.mark.skip\ndef test_ac():\n    assert True\n"
    assert classify_spike_junit([_spike(tmp_path, src + GUARD)]).verdict == "INCONCLUSIVE"


def test_zero_ac_is_inconclusive(tmp_path: Path) -> None:
    assert classify_spike_junit([_spike(tmp_path, GUARD)]).verdict == "INCONCLUSIVE"


def test_zero_guard_is_inconclusive(tmp_path: Path) -> None:
    src = "def test_ac():\n    assert True\n"
    assert classify_spike_junit([_spike(tmp_path, src)]).verdict == "INCONCLUSIVE"


def test_nonzero_exit_with_all_pass_report_is_inconclusive(tmp_path: Path) -> None:
    r = _spike(tmp_path, "def test_ac():\n    assert True\n" + GUARD)
    assert classify_spike_junit([SpikeReport("spike", r.junit_path, 1)]).verdict == "INCONCLUSIVE"


def test_missing_report_is_inconclusive(tmp_path: Path) -> None:
    r = SpikeReport("spike", tmp_path / "nope.xml", 1)
    assert classify_spike_junit([r]).verdict == "INCONCLUSIVE"


def test_malformed_report_is_inconclusive(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuite")
    assert classify_spike_junit([SpikeReport("spike", bad, 1)]).verdict == "INCONCLUSIVE"


def test_regression_failure_is_inconclusive(tmp_path: Path) -> None:
    spike = _spike(tmp_path, "def test_ac():\n    assert 1 == 2\n" + GUARD)
    reg_dir = tmp_path / "reg"
    reg_dir.mkdir()
    (reg_dir / "test_reg.py").write_text("def test_r():\n    assert False\n")
    xml = tmp_path / "regression-1.xml"
    code = _run_pytest(tmp_path, "reg/", xml)
    v = classify_spike_junit([spike, SpikeReport("regression", xml, code)])
    assert v.verdict == "INCONCLUSIVE"


def test_regression_pass_keeps_refuted(tmp_path: Path) -> None:
    spike = _spike(tmp_path, "def test_ac():\n    assert 1 == 2\n" + GUARD)
    reg_dir = tmp_path / "reg"
    reg_dir.mkdir()
    (reg_dir / "test_reg.py").write_text("def test_r():\n    assert True\n")
    xml = tmp_path / "regression-1.xml"
    code = _run_pytest(tmp_path, "reg/", xml)
    assert classify_spike_junit([spike, SpikeReport("regression", xml, code)]).verdict == "REFUTED"


def test_addopts_x_still_runs_guard_tests(tmp_path: Path) -> None:
    src = "def test_ac():\n    assert 1 == 2\n" + GUARD
    r = _spike(tmp_path, src, addopts="-x")
    assert classify_spike_junit([r]).verdict == "REFUTED"


class TestEmitConftest:
    def test_appends_without_clobbering_existing_fixtures(self, tmp_path: Path) -> None:
        conf = tmp_path / "conftest.py"
        conf.write_text("import pytest\n\n@pytest.fixture\ndef mine():\n    return 1\n")
        emit_conftest(conf)
        text = conf.read_text()
        assert "def mine()" in text
        assert HOOK_BEGIN in text

    def test_second_run_replaces_block(self, tmp_path: Path) -> None:
        conf = tmp_path / "conftest.py"
        conf.write_text("X = 1\n")
        emit_conftest(conf)
        first = conf.read_text()
        emit_conftest(conf)
        assert conf.read_text() == first
        assert conf.read_text().count(HOOK_BEGIN) == 1
        assert "X = 1" in conf.read_text()


class TestCli:
    def test_exit_codes_and_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import argparse

        from little_loops.cli.issues.spike_verdict import cmd_spike_verdict

        r = _spike(tmp_path, "def test_ac():\n    assert 1 == 2\n" + GUARD)
        ns = argparse.Namespace(
            report=[f"spike:{r.junit_path}:{r.exit_code}"], emit_conftest=False, out=None
        )
        assert cmd_spike_verdict(None, ns) == 1  # type: ignore[arg-type]
        assert capsys.readouterr().out.startswith("REFUTED")
        ns.report = [f"spike:{tmp_path / 'nope.xml'}:1"]
        assert cmd_spike_verdict(None, ns) == 3  # type: ignore[arg-type]

    def test_usage_errors_exit_2(self) -> None:
        import argparse

        from little_loops.cli.issues.spike_verdict import cmd_spike_verdict

        ns = argparse.Namespace(report=["bogus:x.xml:0"], emit_conftest=False, out=None)
        assert cmd_spike_verdict(None, ns) == 2  # type: ignore[arg-type]
        ns = argparse.Namespace(report=None, emit_conftest=True, out=None)
        assert cmd_spike_verdict(None, ns) == 2  # type: ignore[arg-type]
