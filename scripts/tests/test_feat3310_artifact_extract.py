"""Tests for FEAT-3310 Phase 2: `ll-artifact extract` and `ll-artifact refresh`."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.artifact_templates import ArtifactTemplate, ManifestError, load_manifest
from little_loops.cli.artifact.extract import (
    ExtractError,
    add_extract_parser,
    cmd_extract,
    cmd_refresh,
    extract_data,
)
from little_loops.cli.artifact.lockfile import (
    LockfileError,
    load_lockfile,
    lock_path_for,
    relativize_path,
    write_lockfile,
)
from little_loops.host_runner import BlockingJsonError, HostInvocation
from little_loops.logger import Logger

_FIXTURES = Path(__file__).parent / "fixtures" / "artifact_templates"


def _make_config(project_root: Path, artifacts_extra: dict | None = None):
    from little_loops.config.core import BRConfig

    config_dir = project_root / ".ll"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if artifacts_extra:
        cfg["artifacts"] = artifacts_extra
    (config_dir / "ll-config.json").write_text(json.dumps(cfg))
    return BRConfig(project_root)


def _copy_fixture(name: str, dest: Path) -> Path:
    target = dest / f"{name}.llat"
    shutil.copytree(_FIXTURES / f"{name}.llat", target)
    return target


def _with_extraction(root: Path, *, prompt: str | None = "Extract the report", **extra) -> None:
    """Rewrite a copied fixture's manifest.yaml to add `source`/`extraction`."""
    manifest_path = root / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    extraction: dict = {}
    if prompt is not None:
        extraction["prompt"] = prompt
    extraction.update(extra)
    manifest["extraction"] = extraction
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))


def _make_runner(name: str = "claude-code"):
    return type(
        "FakeRunner",
        (),
        {
            "name": name,
            "build_blocking_json": lambda self, *, prompt, model=None, json_schema=None: (
                HostInvocation(binary="claude", args=["-p", prompt])
            ),
        },
    )()


_VALID_DATA = {
    "title": "Q3 report",
    "sections": [{"heading": "Auth outage", "body": "details", "severity": "high"}],
}


# ---------------------------------------------------------------------------
# lockfile.py
# ---------------------------------------------------------------------------


class TestRelativizePath:
    def test_inside_project_root_is_relative_posix(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "dir" / "file.txt"
        assert relativize_path(target, tmp_path) == "sub/dir/file.txt"

    def test_outside_project_root_is_absolute(self, tmp_path: Path) -> None:
        other_root = tmp_path / "project"
        other_root.mkdir()
        outside = tmp_path / "elsewhere" / "file.txt"
        assert relativize_path(outside, other_root) == str(outside.resolve())

    def test_only_reachable_via_dotdot_is_stored_absolute(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        sibling = tmp_path / "sibling" / "source.md"
        result = relativize_path(sibling, project_root)
        assert not result.startswith("..")
        assert result == str(sibling.resolve())


class TestLockfileRoundTrip:
    def test_missing_file_returns_empty_structure(self, tmp_path: Path) -> None:
        data = load_lockfile(tmp_path / "nope.lock")
        assert data == {"version": 1, "renders": {}}

    def test_write_then_load(self, tmp_path: Path) -> None:
        path = tmp_path / "t.llat.lock"
        write_lockfile(
            path,
            {
                "docs/a.md": {
                    "sha256": "abc",
                    "rendered_at": "2026-08-25T00:00:00Z",
                    "output": "out/a.html",
                }
            },
        )
        data = load_lockfile(path)
        assert data["renders"]["docs/a.md"]["sha256"] == "abc"

    def test_merges_preserving_other_sources(self, tmp_path: Path) -> None:
        path = tmp_path / "t.llat.lock"
        write_lockfile(path, {"docs/a.md": {"sha256": "a", "rendered_at": "t", "output": "o/a"}})
        write_lockfile(path, {"docs/b.md": {"sha256": "b", "rendered_at": "t", "output": "o/b"}})
        data = load_lockfile(path)
        assert set(data["renders"].keys()) == {"docs/a.md", "docs/b.md"}

    def test_unparseable_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "t.llat.lock"
        path.write_text(": : :\nnot: [valid")
        with pytest.raises(LockfileError):
            load_lockfile(path)

    def test_unknown_version_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "t.llat.lock"
        path.write_text(yaml.safe_dump({"version": 99, "renders": {}}))
        with pytest.raises(LockfileError):
            load_lockfile(path)

    def test_missing_renders_key_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "t.llat.lock"
        path.write_text(yaml.safe_dump({"version": 1}))
        with pytest.raises(LockfileError):
            load_lockfile(path)

    def test_lock_path_for(self, tmp_path: Path) -> None:
        root = tmp_path / "my-report.llat"
        assert lock_path_for(root) == tmp_path / "my-report.llat.lock"


# ---------------------------------------------------------------------------
# load_manifest: source/extraction inner-shape validation
# ---------------------------------------------------------------------------


class TestLoadManifestSourceExtractionShape:
    def test_mapping_shaped_source_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest_path = root / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["source"] = {"path": "docs/x.md"}
        manifest_path.write_text(yaml.safe_dump(manifest))
        with pytest.raises(ManifestError):
            load_manifest(root)

    def test_non_mapping_extraction_rejected(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        manifest_path = root / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["extraction"] = "not-a-mapping"
        manifest_path.write_text(yaml.safe_dump(manifest))
        with pytest.raises(ManifestError):
            load_manifest(root)

    def test_scalar_source_and_mapping_extraction_load_fine(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root, prompt="do it")
        manifest = load_manifest(root)
        assert manifest["extraction"]["prompt"] == "do it"

    def test_neither_key_present_still_loads(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        load_manifest(root)  # no source/extraction declared — must not raise


# ---------------------------------------------------------------------------
# extract_data
# ---------------------------------------------------------------------------


class TestExtractData:
    def _template(self, tmp_path: Path, **extraction_kwargs) -> ArtifactTemplate:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root, **extraction_kwargs)
        return ArtifactTemplate(root=root, manifest=load_manifest(root))

    def test_successful_extraction(self, tmp_path: Path) -> None:
        template = self._template(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# Q3 report\nAuth outage happened.")
        config = _make_config(tmp_path)

        with (
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            data, source_bytes = extract_data(template, source, config, model=None, timeout=180)
        assert data == _VALID_DATA
        assert source_bytes == source.read_bytes()

    def test_schema_violating_response_fails_loud(self, tmp_path: Path) -> None:
        template = self._template(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# report")
        config = _make_config(tmp_path)

        with (
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch(
                "little_loops.cli.artifact.extract.run_blocking_json", return_value={"title": "x"}
            ),
        ):
            with pytest.raises(ExtractError, match="schema validation"):
                extract_data(template, source, config, model=None, timeout=180)

    def test_host_call_failure_translated(self, tmp_path: Path) -> None:
        template = self._template(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# report")
        config = _make_config(tmp_path)

        with (
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch(
                # extract.py imports run_blocking_json by reference
                # (`from little_loops.host_runner import ... run_blocking_json`),
                # so it must be patched where it's bound, not at its
                # definition site — patching `little_loops.host_runner.
                # run_blocking_json` leaves extract.py's already-bound name
                # untouched and the call falls through to the real function,
                # which spawns the real host CLI (caught by FEAT-3329's
                # live-spawn guard).
                "little_loops.cli.artifact.extract.run_blocking_json",
                side_effect=BlockingJsonError("boom", {"error": "boom"}),
            ),
        ):
            with pytest.raises(ExtractError, match="extraction call failed"):
                extract_data(template, source, config, model=None, timeout=180)

    def test_missing_extraction_prompt_fails_loud(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root, prompt=None, method="llm_discovery")
        template = ArtifactTemplate(root=root, manifest=load_manifest(root))
        source = tmp_path / "source.md"
        source.write_text("# report")
        config = _make_config(tmp_path)

        with pytest.raises(ExtractError, match="extraction.prompt"):
            extract_data(template, source, config, model=None, timeout=180)

    def test_oversized_source_rejected_before_host_call(self, tmp_path: Path) -> None:
        template = self._template(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("x" * 100)
        config = _make_config(tmp_path, {"templatize_max_input_bytes": 10})

        with patch("little_loops.cli.artifact.extract.resolve_host") as resolve_mock:
            with pytest.raises(ExtractError, match="templatize_max_input_bytes"):
                extract_data(template, source, config, model=None, timeout=180)
        resolve_mock.assert_not_called()

    def test_model_precedence_cli_wins(self, tmp_path: Path) -> None:
        template = self._template(tmp_path, model="manifest-model")
        source = tmp_path / "source.md"
        source.write_text("# report")
        config = _make_config(tmp_path)

        captured = {}

        def _build(self, *, prompt, model=None, json_schema=None):
            captured["model"] = model
            return HostInvocation(binary="claude", args=["-p", prompt])

        runner = type("R", (), {"name": "claude-code", "build_blocking_json": _build})()
        with (
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=runner),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            extract_data(template, source, config, model="cli-model", timeout=180)
        assert captured["model"] == "cli-model"

    def test_model_precedence_manifest_wins_over_default(self, tmp_path: Path) -> None:
        template = self._template(tmp_path, model="manifest-model")
        source = tmp_path / "source.md"
        source.write_text("# report")
        config = _make_config(tmp_path)

        captured = {}

        def _build(self, *, prompt, model=None, json_schema=None):
            captured["model"] = model
            return HostInvocation(binary="claude", args=["-p", prompt])

        runner = type("R", (), {"name": "claude-code", "build_blocking_json": _build})()
        with (
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=runner),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            extract_data(template, source, config, model=None, timeout=180)
        assert captured["model"] == "manifest-model"

    def test_model_precedence_default_when_nothing_set(self, tmp_path: Path) -> None:
        from little_loops.fsm.schema import DEFAULT_LLM_MODEL

        template = self._template(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# report")
        config = _make_config(tmp_path)

        captured = {}

        def _build(self, *, prompt, model=None, json_schema=None):
            captured["model"] = model
            return HostInvocation(binary="claude", args=["-p", prompt])

        runner = type("R", (), {"name": "claude-code", "build_blocking_json": _build})()
        with (
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=runner),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            extract_data(template, source, config, model=None, timeout=180)
        assert captured["model"] == DEFAULT_LLM_MODEL


# ---------------------------------------------------------------------------
# cmd_extract
# ---------------------------------------------------------------------------


class TestCmdExtract:
    def test_happy_path_writes_data_json(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root)
        _make_config(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# Q3 report")
        args = argparse.Namespace(
            template=str(root), source=str(source), data=None, model=None, timeout=180
        )
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            code = cmd_extract(args, Logger(use_color=False, verbose=True))
        assert code == 0
        data_path = root / "data.json"
        assert json.loads(data_path.read_text()) == _VALID_DATA

    def test_schema_violation_exits_1_and_writes_nothing(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root)
        original_data = (root / "data.json").read_text()
        _make_config(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# Q3 report")
        args = argparse.Namespace(
            template=str(root), source=str(source), data=None, model=None, timeout=180
        )
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch(
                "little_loops.cli.artifact.extract.run_blocking_json", return_value={"title": "x"}
            ),
        ):
            code = cmd_extract(args, Logger(use_color=False, verbose=True))
        assert code == 1
        assert (root / "data.json").read_text() == original_data

    def test_data_flag_writes_to_custom_path(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root)
        _make_config(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# Q3 report")
        out_data = tmp_path / "out" / "data.json"
        args = argparse.Namespace(
            template=str(root), source=str(source), data=str(out_data), model=None, timeout=180
        )
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            code = cmd_extract(args, Logger(use_color=False, verbose=True))
        assert code == 0
        assert json.loads(out_data.read_text()) == _VALID_DATA

    def test_no_o_flag_registered(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_extract_parser(subparsers)
        with pytest.raises(SystemExit):
            parser.parse_args(["extract", "tmpl", "src.md", "-o", "out/"])


# ---------------------------------------------------------------------------
# cmd_refresh
# ---------------------------------------------------------------------------


class TestCmdRefresh:
    def _setup(self, tmp_path: Path, source_rel: str = "docs/source.md"):
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root)
        manifest_path = root / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["source"] = source_rel
        manifest_path.write_text(yaml.safe_dump(manifest))
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Q3 report")
        _make_config(tmp_path)
        return root, source

    def test_default_source_from_manifest_and_lockfile_written(self, tmp_path: Path) -> None:
        root, source = self._setup(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            template=str(root),
            source=None,
            data=None,
            output=str(out_dir),
            model=None,
            timeout=180,
        )
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            code = cmd_refresh(args, Logger(use_color=False, verbose=True))
        assert code == 0
        assert (out_dir / "report.html").is_file()

        lock_path = root.parent / f"{root.name}.lock"
        data = load_lockfile(lock_path)
        assert "docs/source.md" in data["renders"]
        entry = data["renders"]["docs/source.md"]
        assert entry["sha256"] == __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        assert entry["output"].endswith("report.html")
        assert entry["rendered_at"].endswith("Z")

    def test_unresolvable_default_source_fails_loud(self, tmp_path: Path) -> None:
        root = _copy_fixture("simple", tmp_path)
        _with_extraction(root)
        manifest_path = root / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["source"] = "docs/does-not-exist.md"
        manifest_path.write_text(yaml.safe_dump(manifest))
        _make_config(tmp_path)
        args = argparse.Namespace(
            template=str(root), source=None, data=None, output=None, model=None, timeout=180
        )
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            code = cmd_refresh(args, Logger(use_color=False, verbose=True))
        assert code == 1

    def test_merge_preserves_other_sources_entry(self, tmp_path: Path) -> None:
        root, source = self._setup(tmp_path)
        lock_path = root.parent / f"{root.name}.lock"
        write_lockfile(
            lock_path,
            {
                "docs/other.md": {
                    "sha256": "prior",
                    "rendered_at": "2026-01-01T00:00:00Z",
                    "output": "o/other.html",
                }
            },
        )
        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            template=str(root),
            source=None,
            data=None,
            output=str(out_dir),
            model=None,
            timeout=180,
        )
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
        ):
            code = cmd_refresh(args, Logger(use_color=False, verbose=True))
        assert code == 0
        data = load_lockfile(lock_path)
        assert "docs/other.md" in data["renders"]
        assert data["renders"]["docs/other.md"]["sha256"] == "prior"
        assert "docs/source.md" in data["renders"]

    def test_lockfile_write_failure_reports_render_succeeded(self, tmp_path: Path) -> None:
        root, source = self._setup(tmp_path)
        out_dir = tmp_path / "out"
        args = argparse.Namespace(
            template=str(root),
            source=None,
            data=None,
            output=str(out_dir),
            model=None,
            timeout=180,
        )
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("little_loops.cli.artifact.extract.resolve_host", return_value=_make_runner()),
            patch("little_loops.cli.artifact.extract.run_blocking_json", return_value=_VALID_DATA),
            patch(
                "little_loops.cli.artifact.extract.write_lockfile",
                side_effect=OSError("disk full"),
            ),
        ):
            logger = Logger(use_color=False, verbose=True)
            code = cmd_refresh(args, logger)
        assert code == 1
        assert (out_dir / "report.html").is_file()

    def test_data_flag_resolves_against_project_root_not_cwd(self, tmp_path: Path) -> None:
        # `BRConfig(Path.cwd())` has no upward search in this codebase — the
        # invocation directory *is* `config.project_root` for every
        # `ll-artifact` subcommand. What must hold regardless is that
        # `_resolve_data_path` keys off `config.project_root`, never a
        # separately-tracked cwd, so extract's write and (in FEAT-3311)
        # render's read can never diverge.
        from little_loops.cli.artifact.extract import _resolve_data_path

        class _FakeConfig:
            project_root = tmp_path / "actual-root"

        root = tmp_path / "template.llat"
        resolved = _resolve_data_path("rel-data.json", root, _FakeConfig())
        assert resolved == tmp_path / "actual-root" / "rel-data.json"

    def test_data_flag_default_is_under_template_root(self, tmp_path: Path) -> None:
        from little_loops.cli.artifact.extract import _resolve_data_path

        class _FakeConfig:
            project_root = tmp_path

        root = tmp_path / "template.llat"
        resolved = _resolve_data_path(None, root, _FakeConfig())
        assert resolved == root / "data.json"


# ---------------------------------------------------------------------------
# templatize: source normalization
# ---------------------------------------------------------------------------


class TestTemplatizeSourceNormalization:
    def _run(self, argv):
        old_argv = sys.argv
        sys.argv = ["ll-artifact"] + argv
        try:
            from little_loops.cli.artifact import main_artifact

            return main_artifact()
        finally:
            sys.argv = old_argv

    def test_source_inside_project_root_stored_relative(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        artifact = tmp_path / "out" / "index.html"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"<h1>Hello</h1>\n")
        source = tmp_path / "docs" / "SRC.md"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"# Hello\n")
        regions_path = tmp_path / "map.json"
        regions_path.write_text(
            json.dumps({"regions": [{"start": 4, "end": 9, "expr": "title"}], "groups": []})
        )
        out_dir = tmp_path / "artifacts" / "templates" / "greet.llat"

        code = self._run(
            [
                "templatize",
                "out/index.html",
                "docs/SRC.md",
                "-o",
                str(out_dir),
                "--regions",
                str(regions_path),
            ]
        )

        assert code == 0
        manifest = load_manifest(out_dir)
        assert manifest["source"] == "docs/SRC.md"

    def test_source_reachable_only_via_dotdot_stored_absolute(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # `BRConfig(Path.cwd())` has no upward search — the invocation
        # directory *is* `config.project_root`. A source reachable only via
        # `..` from there must be stored absolute, never as a `../…` chain
        # (§ Pre-implementation decisions, third review).
        project_root = tmp_path / "root"
        project_root.mkdir()
        artifact = project_root / "out" / "index.html"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"<h1>Hello</h1>\n")
        sibling_source = tmp_path / "sibling" / "SRC.md"
        sibling_source.parent.mkdir(parents=True)
        sibling_source.write_bytes(b"# Hello\n")
        regions_path = project_root / "map.json"
        regions_path.write_text(
            json.dumps({"regions": [{"start": 4, "end": 9, "expr": "title"}], "groups": []})
        )
        out_dir = project_root / "artifacts" / "templates" / "greet.llat"

        monkeypatch.chdir(project_root)
        code = self._run(
            [
                "templatize",
                "out/index.html",
                str(Path("..") / "sibling" / "SRC.md"),
                "-o",
                str(out_dir),
                "--regions",
                str(regions_path),
            ]
        )

        assert code == 0
        manifest = load_manifest(out_dir)
        assert not manifest["source"].startswith("..")
        assert manifest["source"] == str(sibling_source.resolve())
