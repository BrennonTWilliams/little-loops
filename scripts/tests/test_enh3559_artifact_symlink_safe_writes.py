"""ENH-3559: artifact output writes replace a planted symlink instead of following it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.artifact import cmd_design_md_export, cmd_policy_builder
from little_loops.cli.artifact.extract import cmd_extract  # noqa: F401  (import smoke)
from little_loops.cli.artifact.render import render_to_disk
from little_loops.cli.artifact.templatize import _write_rejected_discovery
from little_loops.file_utils import atomic_write
from little_loops.logger import Logger


@pytest.fixture(autouse=True)
def _umask_022():
    old = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(old)


def _plant(out: Path, tmp_path: Path) -> Path:
    victim = tmp_path / "outside" / "victim.txt"
    victim.parent.mkdir(exist_ok=True)
    victim.write_text("untouched")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.symlink_to(victim)
    return victim


def _assert_replaced(out: Path, victim: Path) -> None:
    assert victim.read_text() == "untouched"
    assert out.is_file() and not out.is_symlink()
    assert (out.stat().st_mode & 0o777) == 0o644


def test_policy_builder_replaces_symlink(tmp_path: Path) -> None:
    out = tmp_path / "art" / "policy-router-builder.html"
    victim = _plant(out, tmp_path)
    args = argparse.Namespace(output=str(out.parent))
    assert cmd_policy_builder(args, Logger(use_color=False)) == 0
    _assert_replaced(out, victim)


def test_design_md_export_replaces_symlink(tmp_path: Path) -> None:
    from little_loops.config.core import BRConfig  # noqa: F401

    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps({"design_tokens": {"enabled": True}})
    )
    out = tmp_path / "DESIGN.md"
    victim = _plant(out, tmp_path)
    args = argparse.Namespace(profile=None, theme=None, output=str(out))
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        assert cmd_design_md_export(args, Logger(use_color=False)) == 0
    _assert_replaced(out, victim)


def test_render_to_disk_replaces_symlink(tmp_path: Path) -> None:
    from little_loops.config.core import BRConfig

    class _T:
        manifest = {"output": "page.html"}

    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    out = tmp_path / "art" / "page.html"
    victim = _plant(out, tmp_path)
    with patch("little_loops.cli.artifact.render.render_template", return_value="<html/>"):
        render_to_disk(_T(), {}, BRConfig(tmp_path), str(out.parent))  # type: ignore[arg-type]
    _assert_replaced(out, victim)


def test_data_json_bytes_are_utf8_unescaped(tmp_path: Path) -> None:
    data = {"name": "café ☃"}
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    atomic_write(tmp_path / "data.json", payload, encoding="utf-8", shared_mode=True)
    assert (tmp_path / "data.json").read_bytes() == payload.encode("utf-8")


def test_rejected_discovery_replaces_symlink(tmp_path: Path) -> None:
    rejected = tmp_path / "x.rejected"
    victim = _plant(rejected / "discovery.json", tmp_path)
    _write_rejected_discovery(rejected, {"a": 1}, None)
    assert victim.read_text() == "untouched"
    assert (rejected / "discovery.json").is_file()
    assert not (rejected / "discovery.json").is_symlink()
