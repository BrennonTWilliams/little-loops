"""Tests for deploy_issue_templates() writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.init.writers import deploy_issue_templates
from little_loops.issue_template import get_bundled_templates_dir


@pytest.fixture
def templates_dir() -> Path:
    return get_bundled_templates_dir()


@pytest.fixture
def fake_templates_dir(tmp_path: Path) -> Path:
    """Minimal templates dir with one *-sections.json file."""
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "bug-sections.json").write_text('{"sections": []}')
    return tdir


class TestDeployIssueTemplates:
    def test_deploys_sections(self, tmp_path: Path, fake_templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_issue_templates(ll_dir, fake_templates_dir)
        assert created is True
        assert (ll_dir / "templates").is_dir()
        assert (ll_dir / "templates" / "bug-sections.json").exists()

    def test_deploys_only_sections_files(self, tmp_path: Path) -> None:
        tdir = tmp_path / "templates"
        tdir.mkdir()
        (tdir / "bug-sections.json").write_text("{}")
        (tdir / "python.json").write_text("{}")  # project-type JSON — should not be copied
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        deploy_issue_templates(ll_dir, tdir)
        dest = ll_dir / "templates"
        assert (dest / "bug-sections.json").exists()
        assert not (dest / "python.json").exists()

    def test_deploys_all_bundled_sections(self, tmp_path: Path, templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_issue_templates(ll_dir, templates_dir)
        assert created is True
        dest = ll_dir / "templates"
        section_files = list(dest.glob("*-sections.json"))
        assert len(section_files) >= 4

    def test_skips_if_already_exists(self, tmp_path: Path, fake_templates_dir: Path) -> None:
        ll_dir = tmp_path / ".ll"
        dest = ll_dir / "templates"
        dest.mkdir(parents=True)
        created = deploy_issue_templates(ll_dir, fake_templates_dir)
        assert created is False

    def test_dry_run(
        self, tmp_path: Path, fake_templates_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_issue_templates(ll_dir, fake_templates_dir, dry_run=True)
        assert created is True
        assert not (ll_dir / "templates").exists()
        assert "[write]" in capsys.readouterr().out

    def test_skips_if_no_section_files(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        tdir = tmp_path / "templates"
        tdir.mkdir()
        (tdir / "python.json").write_text("{}")  # no *-sections.json
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        created = deploy_issue_templates(ll_dir, tdir)
        assert created is False
        assert "Warning" in capsys.readouterr().err
